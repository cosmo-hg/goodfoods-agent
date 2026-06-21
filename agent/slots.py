"""
Booking slot state — the deterministic layer underneath the LLM.

Why this exists
───────────────
LLMs are excellent at language understanding and generation but unreliable at
state tracking. Conversations that span many turns ("I want Italian", "for 4
people", "on Saturday", "actually make it 6") routinely break because the
model forgets, hallucinates, or re-asks for information already given.

This module owns the part of the system the LLM is bad at:
  • What information has the guest provided this session?
  • What's still missing for the current task?
  • Which tool calls represent which user intents?

The LLM still does the language work. We just refuse to let it be the source
of truth for the booking data itself.

How slots get populated
───────────────────────
Implicitly — through tool call args and tool results. There is NO separate
"slot extraction" LLM call. When the LLM invokes search_branches with
cuisine="Italian", that arg becomes a slot value. When make_reservation is
called with user_name="Harsh Gupta", the name slot fills.

This means slot state always reflects what was *structurally* captured by a
tool, never what the LLM merely "claimed" to know.

How slots feed back to the LLM
──────────────────────────────
On every turn, the app injects a [Already collected: …] line into the
user_context. The LLM sees what's filled and what's missing and stops re-asking.

How intent is logged
────────────────────
The first PRIMARY tool called per turn is the intent. Precursors
(is_served_area, log_search_failure, log_competitor_mention) don't count.
If the turn ends without any primary tool call, the intent is CONVERSATION.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from typing import Any, Optional


# ── Slot model ─────────────────────────────────────────────────────────────────

@dataclass
class BookingSlots:
    """
    Everything the system has learned about what the guest wants this session.

    Slot values are persisted in st.session_state and survive across turns
    until the user clicks "New conversation" or completes a flow.
    """
    # Search/browse preferences
    cuisine:              Optional[str]  = None
    dish:                 Optional[str]  = None
    location_hint:        Optional[str]  = None
    price_range:          Optional[int]  = None
    dietary_vegetarian:   Optional[bool] = None
    dietary_vegan:        Optional[bool] = None
    dietary_jain:         Optional[bool] = None
    dietary_halal:        Optional[bool] = None
    dietary_gluten_free:  Optional[bool] = None

    # The branch the guest has chosen (or is being recommended)
    selected_branch_id:   Optional[int]  = None
    selected_branch_name: Optional[str]  = None

    # Reservation specifics
    party_size:           Optional[int]  = None
    date:                 Optional[str]  = None    # YYYY-MM-DD
    time:                 Optional[str]  = None    # HH:MM
    occasion:             Optional[str]  = None
    special_requests:     Optional[str]  = None
    corporate_account_id: Optional[int]  = None

    # Guest identity
    user_name:            Optional[str]  = None
    user_email:           Optional[str]  = None
    user_phone:           Optional[str]  = None

    # For modify/cancel/lookup flows — the reservation the guest is acting on
    active_reference:     Optional[str]  = None    # GF-XXXXXX

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    def reset(self) -> None:
        """Clear all slots — used on 'New conversation'."""
        for f in fields(self):
            setattr(self, f.name, None)

    def is_booking_complete(self) -> bool:
        """True iff every field required by make_reservation is filled."""
        return all([
            self.selected_branch_id,
            self.party_size,
            self.date,
            self.time,
            self.user_name,
            self.user_email,
            self.user_phone,
        ])

    def missing_for_booking(self) -> list[str]:
        """Names of required booking fields still empty."""
        return [
            name for name, val in {
                "branch":     self.selected_branch_id,
                "party_size": self.party_size,
                "date":       self.date,
                "time":       self.time,
                "name":       self.user_name,
                "email":      self.user_email,
                "phone":      self.user_phone,
            }.items() if not val
        ]


# ── Intent map ─────────────────────────────────────────────────────────────────

# First PRIMARY tool called per turn = the turn's intent. Precursor / silent
# tools return None so they don't override a more meaningful classification.
_INTENT_BY_TOOL: dict[str, Optional[str]] = {
    "search_branches":            "BROWSE",
    "get_branch_menu":            "MENU",
    "check_availability":         "BROWSE",          # part of the browse-to-book flow
    "make_reservation":           "BOOK",
    "modify_reservation":         "MODIFY",
    "cancel_reservation":         "CANCEL",
    "get_reservation":            "LOOKUP",
    "get_user_profile":           "PROFILE_LOOKUP",
    "create_experience_package":  "OCCASION",
    "get_corporate_account":      "CORPORATE",
    # Silent / precursor
    "is_served_area":             None,
    "log_search_failure":         None,
    "log_competitor_mention":     None,
}

DEFAULT_TURN_INTENT = "CONVERSATION"   # No primary tool called this turn.


def intent_for_tool(tool_name: str) -> Optional[str]:
    """Return the intent label for a tool, or None if the tool is silent."""
    return _INTENT_BY_TOOL.get(tool_name)


# ── Slot updates from tool calls and results ───────────────────────────────────

def _set_if(slots: BookingSlots, delta: dict, field_name: str, value: Any) -> None:
    """Helper: update slot if `value` is non-None and changes the field."""
    if value is None:
        return
    current = getattr(slots, field_name)
    if current != value:
        setattr(slots, field_name, value)
        delta[field_name] = value


def update_from_tool_call(slots: BookingSlots, tool_name: str, args: dict) -> dict:
    """
    Apply slot updates derived from a tool call's arguments.

    Returns a delta dict {field: new_value} for analytics.

    The mapping below is the canonical "tool-arg → slot" contract — any new
    tool that carries booking-relevant info must be added here.
    """
    delta: dict = {}

    if tool_name == "search_branches":
        _set_if(slots, delta, "cuisine",             args.get("cuisine"))
        _set_if(slots, delta, "dish",                args.get("dish"))
        _set_if(slots, delta, "location_hint",       args.get("location_hint"))
        _set_if(slots, delta, "party_size",          args.get("party_size"))
        _set_if(slots, delta, "price_range",         args.get("price_range"))
        _set_if(slots, delta, "dietary_vegetarian",  args.get("dietary_vegetarian"))
        _set_if(slots, delta, "dietary_vegan",       args.get("dietary_vegan"))
        _set_if(slots, delta, "dietary_jain",        args.get("dietary_jain"))
        _set_if(slots, delta, "dietary_halal",       args.get("dietary_halal"))
        _set_if(slots, delta, "dietary_gluten_free", args.get("dietary_gluten_free"))

    elif tool_name == "check_availability":
        _set_if(slots, delta, "selected_branch_id", args.get("branch_id"))
        _set_if(slots, delta, "party_size",         args.get("party_size"))
        _set_if(slots, delta, "date",               args.get("date"))

    elif tool_name == "make_reservation":
        _set_if(slots, delta, "selected_branch_id",   args.get("branch_id"))
        _set_if(slots, delta, "user_name",            args.get("user_name"))
        _set_if(slots, delta, "user_email",           args.get("user_email"))
        # Phone may be int from the 8B-style models; normalise to string.
        phone = args.get("user_phone")
        if phone is not None:
            _set_if(slots, delta, "user_phone", str(phone))
        _set_if(slots, delta, "party_size",           args.get("party_size"))
        _set_if(slots, delta, "date",                 args.get("date"))
        _set_if(slots, delta, "time",                 args.get("time"))
        _set_if(slots, delta, "occasion",             args.get("occasion"))
        _set_if(slots, delta, "special_requests",     args.get("special_requests"))
        _set_if(slots, delta, "corporate_account_id", args.get("corporate_account_id"))

    elif tool_name == "modify_reservation":
        _set_if(slots, delta, "active_reference",   args.get("reference_number"))
        _set_if(slots, delta, "party_size",         args.get("party_size"))
        _set_if(slots, delta, "date",               args.get("date"))
        _set_if(slots, delta, "time",               args.get("time"))
        _set_if(slots, delta, "special_requests",   args.get("special_requests"))

    elif tool_name in ("cancel_reservation", "get_reservation"):
        _set_if(slots, delta, "active_reference",   args.get("reference_number"))

    elif tool_name == "get_user_profile":
        _set_if(slots, delta, "user_email",         args.get("email"))

    elif tool_name == "create_experience_package":
        _set_if(slots, delta, "active_reference",   args.get("reference_number"))
        _set_if(slots, delta, "occasion",           args.get("occasion"))

    return delta


def update_from_tool_result(slots: BookingSlots, tool_name: str, result: Any) -> dict:
    """
    Apply slot updates derived from a tool's RESULT (not just its args).

    Examples:
      • get_user_profile success returns name + phone → fill those slots
      • make_reservation success returns reference_number + branch_name
      • search_branches results don't directly fill a slot (no specific branch chosen yet)
    """
    delta: dict = {}
    if not isinstance(result, dict):
        return delta

    if tool_name == "get_user_profile" and result.get("found"):
        _set_if(slots, delta, "user_name",  result.get("name"))
        _set_if(slots, delta, "user_phone", result.get("phone"))
        _set_if(slots, delta, "user_email", result.get("email"))

    elif tool_name == "make_reservation" and result.get("success"):
        _set_if(slots, delta, "active_reference",     result.get("reference_number"))
        _set_if(slots, delta, "selected_branch_name", result.get("branch_name"))

    elif tool_name == "get_reservation" and result.get("found"):
        _set_if(slots, delta, "selected_branch_id",   result.get("branch_id"))
        _set_if(slots, delta, "selected_branch_name", result.get("branch_name"))
        _set_if(slots, delta, "date",                 result.get("date"))
        _set_if(slots, delta, "time",                 result.get("time"))
        _set_if(slots, delta, "party_size",           result.get("party_size"))

    return delta


# ── Slot view for the LLM ──────────────────────────────────────────────────────

def format_for_llm(slots: BookingSlots) -> str:
    """
    Render the current slot state as a single short line for user_context.

    Two sections:
      [Already collected ...]  — the LLM must NEVER re-ask for these
      [For booking, still need ...]  — only shown when the guest is mid-booking-flow
    """
    known_parts: list[str] = []

    # Compact, only filled fields
    if slots.cuisine:             known_parts.append(f"cuisine={slots.cuisine}")
    if slots.dish:                known_parts.append(f"dish={slots.dish}")
    if slots.location_hint:       known_parts.append(f"area={slots.location_hint}")
    if slots.price_range:         known_parts.append(f"price_tier={slots.price_range}")
    if slots.party_size:          known_parts.append(f"party_size={slots.party_size}")
    if slots.date:                known_parts.append(f"date={slots.date}")
    if slots.time:                known_parts.append(f"time={slots.time}")
    if slots.occasion:            known_parts.append(f"occasion={slots.occasion}")
    if slots.selected_branch_id:
        if slots.selected_branch_name:
            known_parts.append(f"chosen_branch_id={slots.selected_branch_id} ({slots.selected_branch_name})")
        else:
            known_parts.append(f"chosen_branch_id={slots.selected_branch_id}")
    if slots.user_name:           known_parts.append(f"name={slots.user_name}")
    if slots.user_email:          known_parts.append(f"email={slots.user_email}")
    if slots.user_phone:
        # Mask all but last 4 digits in the LLM context — defence in depth.
        last4 = slots.user_phone[-4:] if len(slots.user_phone) >= 4 else slots.user_phone
        known_parts.append(f"phone=••••{last4}")
    if slots.active_reference:    known_parts.append(f"working_with_ref={slots.active_reference}")

    if not known_parts:
        return ""   # First turn or fresh conversation — nothing to inject.

    line = (
        "[Already collected this session: "
        + ", ".join(known_parts)
        + ". Use these directly when calling tools — do NOT re-ask the guest "
        "for any field listed here. If the guest corrects a value, update it.]"
    )

    # Only mention the "still need" list if the guest is meaningfully into a
    # booking flow. We treat "selected_branch_id OR (cuisine AND party_size)"
    # as the trigger so it doesn't leak booking checklist talk into a pure browse.
    in_booking_flow = bool(
        slots.selected_branch_id
        or (slots.cuisine and slots.party_size)
        or slots.date
    )
    if in_booking_flow and not slots.is_booking_complete():
        missing = slots.missing_for_booking()
        if missing:
            line += (
                f" [For booking, still needs: {', '.join(missing)}. "
                "If the guest is ready to book, ask for ALL missing fields in ONE message.]"
            )

    return line
