# Number of messages that triggers compression
_COMPRESS_TRIGGER = 10
# Verbatim messages to keep after compression
_KEEP_RECENT = 8


def _splits_tool_pair(history, cut):
    """
    Return True if slicing at `cut` would orphan a tool_call or tool_result.

    Two unsafe positions:
      • history[cut] is a "tool" result — its paired assistant tool_call would be in
        the older (summarised) section.
      • history[cut] is an assistant message with tool_calls — its results are still
        in the recent section but the call itself would be summarised away.
    """
    if cut >= len(history):
        return False
    msg = history[cut]
    role = msg.get("role", "")
    if role == "tool":
        return True
    if role == "assistant" and msg.get("tool_calls"):
        return True
    return False


def compress_history(history, keep=_KEEP_RECENT):
    """
    Compress history when it grows beyond _COMPRESS_TRIGGER messages.

    Strategy:
    1. Attempt to cut at `len(history) - keep`.
    2. If that exact cut would split a tool_call / tool_result pair, walk
       backwards until reaching a safe user-message boundary.
    3. If no safe boundary exists (entire tail is a tool chain) skip
       compression rather than produce an orphaned tool_result that causes
       an API error.

    For pure user / assistant histories the target cut is always safe and no
    walking is needed, so count reduction is guaranteed when len > trigger.
    """
    if len(history) <= _COMPRESS_TRIGGER:
        return history

    target_cut = len(history) - keep
    cut = target_cut

    if _splits_tool_pair(history, cut):
        # Walk back to the nearest user-message (turn start) boundary.
        while cut > 0 and history[cut].get("role") != "user":
            cut -= 1
        if cut == 0:
            # No safe boundary — skip compression to avoid an orphaned pair.
            return history

    recent = history[cut:]
    older  = history[:cut]

    lines = []
    for msg in older:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            try:
                names = [
                    tc["function"]["name"]
                    for tc in msg["tool_calls"]
                    if isinstance(tc, dict) and "function" in tc
                ]
                if names:
                    lines.append(f"[assistant]: Called tools: {', '.join(names)}")
            except (KeyError, TypeError):
                pass
            continue

        if role == "tool":
            content = msg.get("content") or ""
            snippet = str(content)[:120].replace("\n", " ")
            if snippet:
                lines.append(f"[tool result]: {snippet}…")
            continue

        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        snippet = str(content)[:200].replace("\n", " ")
        if snippet:
            lines.append(f"[{role}]: {snippet}")

    summary = (
        "CONVERSATION SUMMARY (compressed earlier messages):\n"
        + "\n".join(lines)
    )

    return [
        {"role": "user", "content": summary},
        {
            "role": "assistant",
            "content": (
                "Understood. I have context from our earlier conversation "
                "and will continue helping you seamlessly."
            ),
        },
    ] + recent
