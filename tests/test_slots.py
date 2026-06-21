"""
Tests for the slot-filling state layer.

Covers:
  • Tool-call args → slot updates (the main slot-population path)
  • Tool-result fields → slot updates (profile lookup, booking confirmation)
  • Intent classification from tool names
  • format_for_llm output shape (the "don't re-ask" hint)
  • Booking completeness + missing-field accounting
  • Reset behaviour ("New conversation" must wipe state)
  • Corrections (party_size 4 → 6 across two tool calls)
"""
from agent.slots import (
    BookingSlots,
    update_from_tool_call,
    update_from_tool_result,
    format_for_llm,
    intent_for_tool,
    DEFAULT_TURN_INTENT,
)


# ── Slot update from tool CALLS ────────────────────────────────────────────────

class TestUpdateFromToolCall:
    def test_search_branches_fills_browse_slots(self):
        s = BookingSlots()
        delta = update_from_tool_call(s, "search_branches", {
            "cuisine": "Italian", "dish": "pizza", "location_hint": "Indiranagar",
            "party_size": 4, "dietary_vegan": True,
        })
        assert s.cuisine == "Italian"
        assert s.dish == "pizza"
        assert s.location_hint == "Indiranagar"
        assert s.party_size == 4
        assert s.dietary_vegan is True
        assert delta == {
            "cuisine": "Italian", "dish": "pizza", "location_hint": "Indiranagar",
            "party_size": 4, "dietary_vegan": True,
        }

    def test_null_args_dont_overwrite_existing_slots(self):
        s = BookingSlots(cuisine="Italian", party_size=4)
        update_from_tool_call(s, "search_branches", {
            "cuisine": None, "party_size": None, "dish": "pizza",
        })
        # Existing values must survive null args
        assert s.cuisine == "Italian"
        assert s.party_size == 4
        assert s.dish == "pizza"

    def test_check_availability_records_branch_and_date(self):
        s = BookingSlots()
        update_from_tool_call(s, "check_availability", {
            "branch_id": 12, "date": "2026-06-13", "party_size": 4,
        })
        assert s.selected_branch_id == 12
        assert s.date == "2026-06-13"
        assert s.party_size == 4

    def test_make_reservation_fills_all_required_fields(self):
        s = BookingSlots()
        update_from_tool_call(s, "make_reservation", {
            "branch_id": 12, "user_name": "Harsh", "user_email": "h@x.com",
            "user_phone": "+91 98450 12345", "party_size": 4,
            "date": "2026-06-13", "time": "20:00",
        })
        assert s.is_booking_complete()
        assert s.user_name == "Harsh"

    def test_make_reservation_normalises_int_phone_to_string(self):
        s = BookingSlots()
        update_from_tool_call(s, "make_reservation", {
            "branch_id": 1, "user_phone": 9876543210, "user_name": "X",
            "user_email": "x@y.com", "party_size": 2, "date": "2030-01-01", "time": "19:00",
        })
        assert s.user_phone == "9876543210"
        assert isinstance(s.user_phone, str)

    def test_correction_updates_party_size(self):
        s = BookingSlots(cuisine="Italian", party_size=4)
        # Guest says "actually 6 people" → LLM re-searches with new size
        delta = update_from_tool_call(s, "search_branches", {"party_size": 6})
        assert s.party_size == 6
        assert delta == {"party_size": 6}

    def test_modify_reservation_records_active_ref(self):
        s = BookingSlots()
        update_from_tool_call(s, "modify_reservation", {
            "reference_number": "GF-A7X2KP", "time": "20:30",
        })
        assert s.active_reference == "GF-A7X2KP"
        assert s.time == "20:30"

    def test_cancel_records_active_ref(self):
        s = BookingSlots()
        update_from_tool_call(s, "cancel_reservation", {"reference_number": "GF-X"})
        assert s.active_reference == "GF-X"

    def test_get_user_profile_records_email_being_looked_up(self):
        s = BookingSlots()
        update_from_tool_call(s, "get_user_profile", {"email": "h@x.com"})
        assert s.user_email == "h@x.com"


# ── Slot update from tool RESULTS ──────────────────────────────────────────────

class TestUpdateFromToolResult:
    def test_profile_hit_fills_name_phone_email(self):
        s = BookingSlots()
        delta = update_from_tool_result(s, "get_user_profile", {
            "found": True, "name": "Aryan Mehta",
            "phone": "+91 98450 12345", "email": "aryan@x.com",
        })
        assert s.user_name == "Aryan Mehta"
        assert s.user_phone == "+91 98450 12345"
        assert s.user_email == "aryan@x.com"
        assert "user_name" in delta

    def test_profile_miss_does_nothing(self):
        s = BookingSlots()
        update_from_tool_result(s, "get_user_profile", {"found": False})
        assert s.user_name is None

    def test_reservation_success_records_ref_and_branch_name(self):
        s = BookingSlots()
        update_from_tool_result(s, "make_reservation", {
            "success": True, "reference_number": "GF-A7X2KP",
            "branch_name": "GoodFoods Indiranagar — Italian Kitchen",
        })
        assert s.active_reference == "GF-A7X2KP"
        assert s.selected_branch_name == "GoodFoods Indiranagar — Italian Kitchen"

    def test_non_dict_result_handled_safely(self):
        # search_branches returns a list, not a dict — must not crash
        s = BookingSlots()
        delta = update_from_tool_result(s, "search_branches", [{"name": "X"}])
        assert delta == {}


# ── Intent classification ─────────────────────────────────────────────────────

class TestIntentMapping:
    def test_primary_tools_map_to_intents(self):
        assert intent_for_tool("search_branches")   == "BROWSE"
        assert intent_for_tool("make_reservation")  == "BOOK"
        assert intent_for_tool("modify_reservation") == "MODIFY"
        assert intent_for_tool("cancel_reservation") == "CANCEL"
        assert intent_for_tool("get_reservation")    == "LOOKUP"
        assert intent_for_tool("get_branch_menu")    == "MENU"

    def test_silent_tools_return_none(self):
        # Precursors don't override a primary intent
        assert intent_for_tool("is_served_area")        is None
        assert intent_for_tool("log_search_failure")    is None
        assert intent_for_tool("log_competitor_mention") is None

    def test_unknown_tool_returns_none(self):
        assert intent_for_tool("nonexistent_tool") is None


# ── format_for_llm — the "don't re-ask" hint ───────────────────────────────────

class TestFormatForLLM:
    def test_empty_slots_returns_empty_string(self):
        s = BookingSlots()
        assert format_for_llm(s) == ""

    def test_filled_slots_emit_collected_line(self):
        s = BookingSlots(cuisine="Italian", party_size=4, date="2026-06-13")
        line = format_for_llm(s)
        assert "Already collected this session" in line
        assert "cuisine=Italian" in line
        assert "party_size=4" in line
        assert "date=2026-06-13" in line
        assert "do NOT re-ask" in line.lower() or "NEVER" in line or "re-ask" in line

    def test_booking_flow_emits_still_needs_line(self):
        # Cuisine + party_size triggers the booking-flow hint
        s = BookingSlots(cuisine="Italian", party_size=4)
        line = format_for_llm(s)
        assert "still needs" in line
        # Should list the missing booking-required fields
        for missing in ("branch", "date", "time", "name", "email", "phone"):
            assert missing in line

    def test_complete_booking_does_not_emit_still_needs(self):
        s = BookingSlots(
            selected_branch_id=12, party_size=4, date="2026-06-13", time="20:00",
            user_name="X", user_email="x@y.com", user_phone="9999",
        )
        line = format_for_llm(s)
        assert "still needs" not in line.lower()

    def test_phone_is_masked_in_llm_view(self):
        s = BookingSlots(user_phone="+91 98450 12345")
        line = format_for_llm(s)
        assert "•" in line   # masked
        assert "98450" not in line   # body of phone not shown


# ── Booking completeness ───────────────────────────────────────────────────────

class TestBookingCompleteness:
    def test_empty_is_incomplete(self):
        assert BookingSlots().is_booking_complete() is False

    def test_all_seven_required_marks_complete(self):
        s = BookingSlots(
            selected_branch_id=1, party_size=2, date="2030-01-01", time="19:00",
            user_name="A", user_email="a@b.com", user_phone="9999",
        )
        assert s.is_booking_complete() is True

    def test_missing_for_booking_lists_only_empty_required(self):
        s = BookingSlots(cuisine="Italian", party_size=4)
        missing = s.missing_for_booking()
        assert "branch" in missing
        assert "date" in missing
        assert "time" in missing
        assert "name" in missing
        assert "email" in missing
        assert "phone" in missing
        # party_size IS filled, so it should NOT be listed
        assert "party_size" not in missing


# ── Reset ──────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_wipes_all_fields(self):
        s = BookingSlots(
            cuisine="Italian", party_size=4, user_name="X", active_reference="GF-X",
        )
        s.reset()
        assert s.cuisine is None
        assert s.party_size is None
        assert s.user_name is None
        assert s.active_reference is None


# ── Integration: a realistic multi-turn flow ──────────────────────────────────

class TestMultiTurnFlow:
    """Simulates what happens across a 3-turn booking conversation."""

    def test_browse_then_pick_then_book(self):
        slots = BookingSlots()

        # Turn 1: guest says "best italian in indiranagar for 4 saturday"
        update_from_tool_call(slots, "search_branches", {
            "cuisine": "Italian", "location_hint": "Indiranagar", "party_size": 4,
        })
        assert format_for_llm(slots).startswith("[Already collected")
        assert slots.missing_for_booking() != []   # not complete yet

        # Turn 2: guest picks one → LLM calls check_availability
        update_from_tool_call(slots, "check_availability", {
            "branch_id": 12, "date": "2026-06-13", "party_size": 4,
        })
        assert slots.selected_branch_id == 12
        assert slots.date == "2026-06-13"

        # Turn 3: guest gives name/email/phone, LLM books
        update_from_tool_call(slots, "make_reservation", {
            "branch_id": 12, "user_name": "Harsh", "user_email": "h@x.com",
            "user_phone": "9876543210", "party_size": 4,
            "date": "2026-06-13", "time": "20:00",
        })
        update_from_tool_result(slots, "make_reservation", {
            "success": True, "reference_number": "GF-A7X2KP",
            "branch_name": "GoodFoods Indiranagar — Italian Kitchen",
        })
        assert slots.is_booking_complete()
        assert slots.active_reference == "GF-A7X2KP"
        assert slots.selected_branch_name == "GoodFoods Indiranagar — Italian Kitchen"
