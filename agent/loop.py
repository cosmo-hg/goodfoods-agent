from __future__ import annotations

"""
Agentic loop — all intent determination is delegated entirely to the LLM.

The MCP client supplies tool schemas to the LLM; the model decides autonomously
which tool to call and with what arguments at every step.  No hardcoded routing,
keyword matching, or intent classification lives here.

API key management
──────────────────
Multiple Groq keys are supported (GROQ_API_KEY, GROQ_API_KEY_2, …).
On a RateLimitError the exhausted key is put in cooldown and the next
available key is tried immediately — the conversation history is unaffected
because it is decoupled from the transport layer.
"""
import json
import time
import threading
import datetime as _dt

from openai import OpenAI, RateLimitError

from config import GROQ_API_KEYS, GROQ_BASE_URL, MODEL, TEMPERATURE, log_agent_trace, log_agent_turn
from agent.prompts import SYSTEM_PROMPT
from agent.history import compress_history, _COMPRESS_TRIGGER
from agent.slots import (
    BookingSlots,
    update_from_tool_call,
    update_from_tool_result,
    intent_for_tool,
    DEFAULT_TURN_INTENT,
)
from tools.date_resolver import format_for_llm as format_date_ref
from mcp.registry import get_mcp_client

_IN_TURN_COMPRESS_THRESHOLD = 16

# How long (seconds) a rate-limited key sits in cooldown before being retried.
_KEY_COOLDOWN = 60


# ── Key pool ──────────────────────────────────────────────────────────────────

class _KeyPool:
    """
    Thread-safe API key pool with per-key rate-limit cooldown.

    On RateLimitError the caller marks the key as limited; the pool
    immediately returns the next key whose cooldown has expired.
    If all keys are cooling down, get_available() returns (None, None)
    and the caller surfaces a user-friendly error.
    """

    def __init__(self, keys: list) -> None:
        self._keys = list(keys)
        # monotonic timestamp after which each key may be used again (0 = always ready)
        self._cooldown_until: list = [0.0] * len(keys)
        self._lock = threading.Lock()

    def get_available(self):
        """Return (index, api_key) for the first ready key, or (None, None)."""
        now = time.monotonic()
        with self._lock:
            for i, key in enumerate(self._keys):
                if now >= self._cooldown_until[i]:
                    return i, key
        return None, None

    def mark_limited(self, index: int) -> None:
        """Put key[index] in cooldown for _KEY_COOLDOWN seconds."""
        with self._lock:
            self._cooldown_until[index] = time.monotonic() + _KEY_COOLDOWN

    def status(self) -> list:
        """Return a summary dict per key — useful for logging / diagnostics."""
        now = time.monotonic()
        with self._lock:
            return [
                {
                    "key_suffix":         f"…{k[-4:]}",
                    "available":          now >= cd,
                    "cooldown_remaining": round(max(0.0, cd - now), 1),
                }
                for k, cd in zip(self._keys, self._cooldown_until)
            ]


_key_pool = _KeyPool(GROQ_API_KEYS)

# Per-key OpenAI client cache.  OpenAI clients are stateless config wrappers,
# so sharing one instance per key across threads is safe.
_clients: dict = {}
_clients_lock = threading.Lock()


def _get_client(api_key: str) -> OpenAI:
    if api_key not in _clients:
        with _clients_lock:
            if api_key not in _clients:
                _clients[api_key] = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    return _clients[api_key]


# ── API call with key rotation ────────────────────────────────────────────────

def _call_api(messages: list, tools: list, temperature: float):
    """
    Call the LLM API, rotating to the next available key on every RateLimitError.

    Rotation is instant — no sleep between attempts — because we are switching
    to a fresh key, not retrying the same exhausted one.  If every key is in
    cooldown simultaneously a RuntimeError is raised with a user-friendly
    message; the conversation history is preserved and the user can retry.
    """
    n = len(_key_pool._keys)
    for _ in range(n + 1):           # +1 so we surface the "all exhausted" message
        key_index, api_key = _key_pool.get_available()
        if api_key is None:
            raise RuntimeError(
                f"All {n} API key(s) are currently rate-limited. "
                f"They will recover in up to {_KEY_COOLDOWN}s — please try again shortly."
            )
        try:
            # max_tokens cap matters on Groq's free tier — without it the
            # server reserves a huge output budget against the TPM limit,
            # blowing through the 6 000 tokens/min allowance after one turn.
            # 768 is comfortably more than any real agent reply needs.
            return _get_client(api_key).chat.completions.create(
                model=model_name(),
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=768,
            )
        except RateLimitError:
            _key_pool.mark_limited(key_index)
            # Immediately loop to the next available key; no delay needed.
        except Exception:
            raise

    # Unreachable in practice — the loop above always either returns or raises.
    raise RuntimeError("API key pool exhausted.")


def model_name() -> str:
    """Return MODEL — extracted so tests can monkeypatch without touching config."""
    return MODEL


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(
    user_message,
    history,
    session_id=None,
    user_context=None,
    existing_refs=None,
    slots: BookingSlots | None = None,
):
    """
    Run the agentic loop.

    Tool schemas are fetched from the MCP server via the MCP client and handed
    to the LLM.  The LLM decides which tools to call; we execute them via the
    same MCP client and feed results back.  No tool-routing logic lives here.

    API key rotation is handled transparently inside _call_api — a key switch
    mid-turn does not affect the history list passed in or returned.

    Slot tracking: pass the caller's BookingSlots instance — this function
    mutates it in place as tool calls and results flow through. The caller
    sees the updated state immediately. Pass None to opt out (legacy callers).

    Returns (response_text, updated_history, side_effects, turn_meta)
    side_effects keys:
      branch_results     — list from the last search_branches call (for UI)
      reservation        — dict from make_reservation if a booking was made
      user_profile       — dict from get_user_profile if a profile was found
      experience_package — dict from create_experience_package if created

    turn_meta keys:
      intent             — classified intent label for this turn (see slots.py)
      slot_delta         — {field: new_value} populated this turn
    """
    mcp = get_mcp_client()

    # Unique ID for this turn — used to group all trace steps belonging to one request
    turn_id = f"{session_id or 'anon'}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    _step   = 0   # increments with every logged event in this turn

    # Slot + intent tracking for this turn
    if slots is None:
        slots = BookingSlots()           # ephemeral; caller didn't pass one
    turn_intent: str | None = None       # first primary tool call wins
    slot_delta: dict = {}                # aggregated across all tool calls/results this turn

    # Inject a deterministic date reference. The LLM no longer has to compute
    # "this Saturday" from today's date — it looks the phrase up in a table.
    system = SYSTEM_PROMPT + "\n\n" + format_date_ref()

    if existing_refs:
        refs_str = ", ".join(existing_refs)
        system += (
            f"\n\n[SESSION BOOKINGS ALREADY CONFIRMED THIS CONVERSATION: {refs_str}. "
            "Do NOT call make_reservation again for the same dining occasion. "
            "Use modify_reservation if the guest wants to change any detail.]"
        )

    if user_context:
        system += "\n\n" + user_context

    history      = list(history) + [{"role": "user", "content": user_message}]
    tools        = mcp.get_llm_tools()
    side_effects = {
        "branch_results":    [],
        "reservation":       None,
        "user_profile":      None,
        "experience_package": None,
    }

    for _ in range(20):
        # In-loop compression: prevents context overflow during long tool chains.
        # Safe here because compress_history only cuts at user-turn boundaries.
        if len(history) > _IN_TURN_COMPRESS_THRESHOLD:
            history = compress_history(history)

        messages = [{"role": "system", "content": system}] + history
        response = _call_api(messages, tools, TEMPERATURE)
        choice   = response.choices[0]

        # ── LLM finished speaking ─────────────────────────────────────────────
        if choice.finish_reason == "stop":
            content = choice.message.content or ""
            history.append({"role": "assistant", "content": content})
            _step += 1
            log_agent_trace(session_id, turn_id, _step, "llm_stop",
                            result=content[:500] if content else None)
            if len(history) > _COMPRESS_TRIGGER:
                history = compress_history(history)
            # Finalise intent + log the turn
            final_intent = turn_intent or DEFAULT_TURN_INTENT
            log_agent_turn(session_id, turn_id, final_intent, slot_delta, slots.to_dict())
            return content, history, side_effects, {
                "intent": final_intent,
                "slot_delta": slot_delta,
                "turn_id": turn_id,
            }

        # ── LLM requested one or more tool calls ──────────────────────────────
        if choice.finish_reason in ("tool_calls", "function_call"):
            tool_calls = choice.message.tool_calls or []

            history.append({
                "role":       "assistant",
                "content":    choice.message.content,
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                try:
                    args = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
                except json.JSONDecodeError as e:
                    # Surface the parse failure as a tool result so the model
                    # knows what went wrong instead of silently receiving {}.
                    err_content = json.dumps({
                        "error": f"Tool arguments could not be parsed as JSON: {e}. "
                                 "Please retry with valid JSON arguments."
                    })
                    history.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      err_content,
                    })
                    _step += 1
                    log_agent_trace(session_id, turn_id, _step, "error",
                                    tool_name=tc.function.name,
                                    result=err_content)
                    continue

                # ── Slot + intent update from the tool CALL ────────────────────
                # Slot updates happen BEFORE execution so even a failing tool
                # call leaves a record of what the LLM tried to do.
                name = tc.function.name
                call_delta = update_from_tool_call(slots, name, args)
                slot_delta.update(call_delta)

                # First PRIMARY tool call wins the turn's intent classification.
                if turn_intent is None:
                    candidate = intent_for_tool(name)
                    if candidate:
                        turn_intent = candidate

                # Log the tool call before executing it
                _step += 1
                log_agent_trace(session_id, turn_id, _step, "tool_call",
                                tool_name=name, arguments=args)

                result_str = mcp.call_tool(name, args)

                # Log the tool result immediately after
                _step += 1
                log_agent_trace(session_id, turn_id, _step, "tool_result",
                                tool_name=name, result=result_str)

                history.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result_str,
                })

                try:
                    result_data = json.loads(result_str)

                    # ── Slot update from the tool RESULT ────────────────────────
                    # Examples: get_user_profile fills name/phone; make_reservation
                    # populates active_reference + branch_name.
                    result_delta = update_from_tool_result(slots, name, result_data)
                    slot_delta.update(result_delta)

                    # UI side-effects (unchanged)
                    if name == "search_branches" and isinstance(result_data, list):
                        side_effects["branch_results"] = result_data
                    elif name == "make_reservation" and isinstance(result_data, dict) and result_data.get("success"):
                        side_effects["reservation"] = result_data
                    elif name == "get_user_profile" and isinstance(result_data, dict) and result_data.get("found"):
                        side_effects["user_profile"] = result_data
                    elif name == "create_experience_package" and isinstance(result_data, dict) and result_data.get("success"):
                        side_effects["experience_package"] = result_data
                except Exception:
                    pass

            continue

        # ── Unexpected finish reason ──────────────────────────────────────────
        fallback = choice.message.content or "I encountered an issue. Please try again."
        history.append({"role": "assistant", "content": fallback})
        final_intent = turn_intent or DEFAULT_TURN_INTENT
        log_agent_turn(session_id, turn_id, final_intent, slot_delta, slots.to_dict())
        return fallback, history, side_effects, {
            "intent": final_intent, "slot_delta": slot_delta, "turn_id": turn_id,
        }

    msg = "I reached the maximum processing steps. Please try again."
    history.append({"role": "assistant", "content": msg})
    final_intent = turn_intent or DEFAULT_TURN_INTENT
    log_agent_turn(session_id, turn_id, final_intent, slot_delta, slots.to_dict())
    return msg, history, side_effects, {
        "intent": final_intent, "slot_delta": slot_delta, "turn_id": turn_id,
    }
