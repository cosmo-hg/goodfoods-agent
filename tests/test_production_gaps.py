"""
Tests that close every production gap I called out as a caveat.

Each test pins one piece of robust behaviour so the gap can't reopen.

Covered gaps:
  1. Overbooking race — concurrent bookings for the last seat
  2. Date resolution — relative phrases pre-resolved deterministically
  3. Modify on past dates blocked
  4. Cancel on past dates blocked
  5. Indian phone validation accepts/rejects correctly
  6. Schema migrations on databases missing the new columns
  7. Session state persistence + restoration
  8. Time outside branch hours blocked at booking time
  9. Make-reservation runs inside a single transaction (lock visibility)
"""
import datetime as _dt
import threading
import pytest

from unittest.mock import patch

from config import (
    init_db, get_db, _safe_add_column,
    save_session_state, load_session_state,
)
from tools.make_reservation import make_reservation, _is_valid_phone
from tools.modify_cancel import modify_reservation, cancel_reservation
from tools.date_resolver import build_date_reference, format_for_llm as format_date_ref
from tools.location_resolver import (
    reverse_geocode_city,
    resolve_user_location,
    _GEOCODE_CACHE,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "production_test.db")
    init_db(path)
    return path


@pytest.fixture
def small_branch(db_path):
    """A branch with capacity 4 so we can stress-test concurrent bookings."""
    conn = get_db(db_path)
    conn.execute(
        """INSERT INTO branches
           (name, neighborhood, cuisine, capacity, rating,
            latitude, longitude, price_range, popularity_score,
            dietary_vegetarian, dietary_vegan, dietary_gluten_free,
            dietary_halal, dietary_kosher, parking, outdoor_seating,
            opening_time, closing_time, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("Test Italian", "Indiranagar", "Italian", 4, 4.5,
         12.97, 77.64, 2, 75.0, 1, 0, 0, 0, 0, 0, 0, "12:00", "23:00", 1),
    )
    conn.commit()
    branch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return branch_id


# ─── Gap 1: Overbooking race ───────────────────────────────────────────────────

class TestOverbookingRace:
    """
    Concurrent bookings for the same slot must NOT exceed capacity.
    Pre-fix: two threads could both pass check_availability and both insert.
    Post-fix: BEGIN IMMEDIATE serializes them; exactly capacity/party seats sell.
    """

    def test_concurrent_bookings_never_exceed_capacity(self, db_path, small_branch):
        # Capacity = 4, each thread tries to book a party of 1 at the same slot.
        # 10 threads, only 4 should succeed.
        future_date = (_dt.date.today() + _dt.timedelta(days=7)).isoformat()
        successes = []
        failures = []
        lock = threading.Lock()

        def book(i):
            result = make_reservation(
                branch_id=small_branch,
                user_name=f"Guest{i}",
                user_email=f"g{i}@example.com",
                user_phone="9876543210",
                party_size=1,
                date=future_date,
                time="20:00",
                db_path=db_path,
            )
            with lock:
                (successes if result["success"] else failures).append(result)

        threads = [threading.Thread(target=book, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(successes) == 4, f"Expected exactly 4 bookings to succeed; got {len(successes)}. (Capacity is 4.)"
        assert len(failures)  == 6, f"Expected 6 failures; got {len(failures)}."
        for f in failures:
            assert "not available" in f["error"].lower() or "in progress" in f["error"].lower()

    def test_overlapping_90min_window_serialised(self, db_path, small_branch):
        # 20:00 booking occupies 20:00-21:30. A second party trying 21:00 must fail.
        future_date = (_dt.date.today() + _dt.timedelta(days=7)).isoformat()
        r1 = make_reservation(
            branch_id=small_branch, user_name="A", user_email="a@x.com",
            user_phone="9876543210", party_size=4, date=future_date, time="20:00",
            db_path=db_path,
        )
        assert r1["success"]
        r2 = make_reservation(
            branch_id=small_branch, user_name="B", user_email="b@x.com",
            user_phone="9876543210", party_size=1, date=future_date, time="21:00",
            db_path=db_path,
        )
        assert not r2["success"]
        assert "not available" in r2["error"].lower()


# ─── Gap 2: Deterministic date resolution ──────────────────────────────────────

class TestDateResolver:
    def test_today_returns_today(self):
        base = _dt.date(2026, 6, 4)   # Thursday
        ref  = build_date_reference(base)
        assert ref["today_iso"] == "2026-06-04"
        assert ref["today_weekday"] == "Thursday"

    def test_relative_phrases_resolve_correctly(self):
        base = _dt.date(2026, 6, 4)   # Thursday
        ref  = build_date_reference(base)
        assert ref["phrases"]["tomorrow"]      == "2026-06-05"
        assert ref["phrases"]["saturday"]      == "2026-06-06"
        assert ref["phrases"]["this saturday"] == "2026-06-06"
        assert ref["phrases"]["next saturday"] == "2026-06-13"
        assert ref["phrases"]["weekend"]       == "2026-06-06"
        assert ref["phrases"]["sunday"]        == "2026-06-07"

    def test_format_for_llm_emits_lookup_table(self):
        line = format_date_ref(_dt.date(2026, 6, 4))
        assert "Today: 2026-06-04" in line
        assert "Thursday" in line
        assert "saturday=2026-06-06" in line
        assert "Never compute dates yourself" in line

    def test_when_today_is_saturday_this_saturday_is_today(self):
        # Edge case: "this Saturday" said on a Saturday should mean today
        base = _dt.date(2026, 6, 6)   # Saturday
        ref  = build_date_reference(base)
        assert ref["phrases"]["saturday"]      == "2026-06-06"
        assert ref["phrases"]["this saturday"] == "2026-06-06"
        # "next Saturday" is the following week
        assert ref["phrases"]["next saturday"] == "2026-06-13"


# ─── Gap 3 & 4: Modify/cancel past bookings blocked ────────────────────────────

class TestPastDateGuards:
    def _seed_past_booking(self, db_path, branch_id):
        """Insert a confirmed booking for yesterday directly, bypassing make_reservation's past-date guard."""
        yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO reservations
               (reference_number, branch_id, user_name, user_email, user_phone,
                party_size, date, time, status)
               VALUES ('GF-PAST01', ?, 'X', 'x@y.com', '9876543210', 2, ?, '19:00', 'confirmed')""",
            (branch_id, yesterday),
        )
        conn.commit()
        conn.close()

    def test_modify_past_booking_rejected(self, db_path, small_branch):
        self._seed_past_booking(db_path, small_branch)
        result = modify_reservation(
            reference_number="GF-PAST01",
            time="20:00",
            db_path=db_path,
        )
        assert not result["success"]
        assert "past" in result["error"].lower()

    def test_cancel_past_booking_rejected(self, db_path, small_branch):
        self._seed_past_booking(db_path, small_branch)
        result = cancel_reservation(
            reference_number="GF-PAST01",
            db_path=db_path,
        )
        assert not result["success"]
        assert "past" in result["error"].lower()

    def test_modify_future_booking_allowed(self, db_path, small_branch):
        future = (_dt.date.today() + _dt.timedelta(days=14)).isoformat()
        r1 = make_reservation(
            branch_id=small_branch, user_name="A", user_email="a@x.com",
            user_phone="9876543210", party_size=2, date=future, time="19:00",
            db_path=db_path,
        )
        assert r1["success"]
        result = modify_reservation(
            reference_number=r1["reference_number"], time="20:00", db_path=db_path,
        )
        assert result["success"]
        assert result["time"] == "20:00"


# ─── Gap 5: Indian phone validation ────────────────────────────────────────────

class TestIndianPhoneValidation:
    @pytest.mark.parametrize("phone", [
        "+91 98450 12345", "9876543210", "+919876543210",
        "91-9876543210", "+91-98450-12345", "  9876543210  ",
        "9123456789", "8765432109", "7654321098", "6543210987",
    ])
    def test_valid_indian_numbers_accepted(self, phone):
        assert _is_valid_phone(phone), f"{phone} should be valid"

    @pytest.mark.parametrize("phone", [
        "12345",           # too short
        "9876543",         # 7 digits not enough
        "1234567890",      # starts with 1 — invalid mobile prefix
        "5876543210",      # starts with 5
        "abc 9876543210",  # alpha noise
        "+1 555-0123",     # US format
        "",                # empty
        "98765432101",     # too long
    ])
    def test_invalid_numbers_rejected(self, phone):
        assert not _is_valid_phone(phone), f"{phone} should be rejected"


# ─── Gap 6: Schema migrations on legacy databases ──────────────────────────────

class TestSchemaMigrations:
    def test_safe_add_column_is_idempotent(self, db_path):
        conn = get_db(db_path)
        # Adding an already-existing column should be a no-op (not raise)
        _safe_add_column(conn, "branches", "popularity_score", "REAL DEFAULT 50.0")
        _safe_add_column(conn, "branches", "popularity_score", "REAL DEFAULT 50.0")
        # The column must exist after migration
        cols = {row[1] for row in conn.execute("PRAGMA table_info(branches)").fetchall()}
        assert "popularity_score" in cols
        conn.close()

    def test_init_db_upgrades_legacy_db(self, tmp_path):
        """
        Simulate a DB created by an older schema (missing popularity_score,
        dish_tags, slots_json) and verify init_db migrates it cleanly.
        """
        path = str(tmp_path / "legacy.db")
        # Build a minimal legacy schema directly
        import sqlite3
        c = sqlite3.connect(path)
        c.execute("""CREATE TABLE branches (
            id INTEGER PRIMARY KEY, name TEXT, neighborhood TEXT,
            capacity INTEGER, cuisine TEXT, rating REAL DEFAULT 4.0,
            review_count INTEGER DEFAULT 0, price_range INTEGER DEFAULT 2,
            dietary_vegetarian INTEGER DEFAULT 0, dietary_vegan INTEGER DEFAULT 0,
            dietary_gluten_free INTEGER DEFAULT 0, dietary_halal INTEGER DEFAULT 0,
            dietary_kosher INTEGER DEFAULT 0, parking INTEGER DEFAULT 0,
            outdoor_seating INTEGER DEFAULT 0, valet INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            opening_time TEXT, closing_time TEXT, latitude REAL, longitude REAL,
            branch_code TEXT, tables INTEGER, address TEXT, phone TEXT, description TEXT
        )""")
        c.commit()
        c.close()

        # Now run init_db — it should add the missing columns without error
        init_db(path)

        # Verify columns are present
        c = sqlite3.connect(path)
        cols = {row[1] for row in c.execute("PRAGMA table_info(branches)").fetchall()}
        assert "popularity_score" in cols
        assert "city" in cols
        cols_sessions = {row[1] for row in c.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        assert "slots_json" in cols_sessions
        c.close()


# ─── Gap 7: Session persistence ────────────────────────────────────────────────

class TestSessionPersistence:
    def test_save_and_load_round_trip(self, db_path):
        slots = {"cuisine": "Italian", "party_size": 4, "user_name": "Harsh"}
        history = [
            {"role": "user", "content": "italian for 4"},
            {"role": "assistant", "content": "Found three options..."},
        ]
        save_session_state(
            "session-abc",
            slots_dict=slots,
            last_intent="BROWSE",
            agent_history=history,
            db_path=db_path,
        )
        restored = load_session_state("session-abc", db_path=db_path)
        assert restored["slots"]         == slots
        assert restored["last_intent"]   == "BROWSE"
        assert restored["agent_history"] == history

    def test_partial_update_preserves_other_fields(self, db_path):
        # Save full state, then update only slots — other fields must survive
        save_session_state(
            "session-xyz",
            slots_dict={"cuisine": "Italian"},
            last_intent="BROWSE",
            agent_history=[{"role": "user", "content": "hi"}],
            db_path=db_path,
        )
        save_session_state("session-xyz", slots_dict={"cuisine": "French"}, db_path=db_path)
        restored = load_session_state("session-xyz", db_path=db_path)
        assert restored["slots"]["cuisine"] == "French"
        assert restored["last_intent"]      == "BROWSE"   # unchanged
        assert restored["agent_history"]    == [{"role": "user", "content": "hi"}]

    def test_load_unknown_session_returns_blanks(self, db_path):
        r = load_session_state("never-existed", db_path=db_path)
        assert r["slots"] is None
        assert r["last_intent"] is None
        assert r["agent_history"] is None

    def test_load_empty_session_id_is_safe(self, db_path):
        r = load_session_state("", db_path=db_path)
        assert r["slots"] is None


# ─── Gap 8: Time-outside-hours blocked at booking ──────────────────────────────

class TestBookingTimeBounds:
    def test_time_before_opening_rejected(self, db_path, small_branch):
        # Opening is 12:00 → 11:00 must be rejected
        future = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
        r = make_reservation(
            branch_id=small_branch, user_name="A", user_email="a@x.com",
            user_phone="9876543210", party_size=2, date=future, time="11:00",
            db_path=db_path,
        )
        assert not r["success"]
        assert "outside branch hours" in r["error"].lower()

    def test_time_after_closing_rejected(self, db_path, small_branch):
        # Closing is 23:00 → 23:30 must be rejected
        future = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
        r = make_reservation(
            branch_id=small_branch, user_name="A", user_email="a@x.com",
            user_phone="9876543210", party_size=2, date=future, time="23:30",
            db_path=db_path,
        )
        assert not r["success"]
        assert "outside branch hours" in r["error"].lower()


# ─── Gap 10: Reverse geocoding for GPS verification ───────────────────────────

class TestReverseGeocoding:
    """
    Reverse geocoding turns lat/lon into a city name. This lets the UI
    *show* the user where their GPS thinks they are — critical for debugging
    cases like 'I'm in Singapore but it says outside Bangalore'.

    We mock the HTTP layer so these tests are deterministic and offline-safe.
    """

    def setup_method(self):
        # Reset cache between tests so each one is independent
        _GEOCODE_CACHE.clear()

    def test_reverse_geocode_returns_blank_on_none_coords(self):
        result = reverse_geocode_city(None, None)
        assert result["ok"] is False
        assert result["display"] is None

    def test_reverse_geocode_handles_network_failure_silently(self):
        # Simulate Nominatim being unreachable
        with patch("tools.location_resolver.urllib.request.urlopen",
                   side_effect=OSError("Connection refused")):
            result = reverse_geocode_city(12.97, 77.59)
        assert result["ok"] is False
        assert result["city"] is None
        assert result["display"] is None

    def test_reverse_geocode_caches_result(self):
        # Two calls with same rounded coords → one HTTP call only
        fake_resp_data = b'{"address": {"city": "Bengaluru", "country": "India"}}'

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return fake_resp_data

        with patch("tools.location_resolver.urllib.request.urlopen",
                   return_value=FakeResp()) as mock_open:
            r1 = reverse_geocode_city(12.9716, 77.6094)
            r2 = reverse_geocode_city(12.9716, 77.6094)
            r3 = reverse_geocode_city(12.97, 77.61)   # rounds to same key
        assert mock_open.call_count == 1
        assert r1 == r2 == r3
        assert r1["city"] == "Bengaluru"
        assert r1["display"] == "Bengaluru, India"

    def test_reverse_geocode_picks_most_specific_locality(self):
        # No "city" key but "town" present → should pick "town"
        fake_resp_data = b'{"address": {"town": "Yelahanka", "country": "India"}}'

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return fake_resp_data

        with patch("tools.location_resolver.urllib.request.urlopen", return_value=FakeResp()):
            result = reverse_geocode_city(13.10, 77.60)
        assert result["city"] == "Yelahanka"

    def test_reverse_geocode_empty_address_returns_blank(self):
        fake_resp_data = b'{"address": {}}'

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return fake_resp_data

        with patch("tools.location_resolver.urllib.request.urlopen", return_value=FakeResp()):
            result = reverse_geocode_city(0.0, 0.0)
        assert result["ok"] is False
        assert result["display"] is None

    def test_resolve_user_location_skips_geocode_when_requested(self):
        # with_geocode=False → no Nominatim call, geo block is blank
        with patch("tools.location_resolver.urllib.request.urlopen") as mock_open:
            r = resolve_user_location(12.9716, 77.6094, with_geocode=False)
        assert mock_open.call_count == 0
        assert r["geo"]["ok"] is False
        assert r["in_bangalore"] is True

    def test_resolve_user_location_includes_geo_block(self):
        fake_resp_data = b'{"address": {"city": "Mumbai", "country": "India"}}'

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return fake_resp_data

        with patch("tools.location_resolver.urllib.request.urlopen", return_value=FakeResp()):
            r = resolve_user_location(19.0760, 72.8777)
        assert r["geo"]["city"] == "Mumbai"
        assert r["geo"]["display"] == "Mumbai, India"
        assert r["in_bangalore"] is False


# ─── Gap 9: Concurrent modify is also serialised ───────────────────────────────

class TestConcurrentModify:
    def test_two_modifies_to_same_slot_dont_overbook(self, db_path, small_branch):
        """
        Two confirmed bookings (party 2 each in capacity-4 branch, different slots)
        BOTH try to move to a third slot. Only one should win — capacity 4 fits
        4 seats max in the target window.
        """
        future = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
        # Set up: branch capacity 4, two existing bookings at different non-overlapping times
        r1 = make_reservation(
            branch_id=small_branch, user_name="A", user_email="a@x.com",
            user_phone="9876543210", party_size=3, date=future, time="13:00",
            db_path=db_path,
        )
        r2 = make_reservation(
            branch_id=small_branch, user_name="B", user_email="b@x.com",
            user_phone="9876543210", party_size=3, date=future, time="16:00",
            db_path=db_path,
        )
        assert r1["success"] and r2["success"]

        # Both try to move to 20:00 (party 3 each = needs 6 seats, capacity 4)
        # → first one succeeds, second one must fail.
        results = []
        lock = threading.Lock()
        def attempt(ref):
            res = modify_reservation(reference_number=ref, time="20:00", db_path=db_path)
            with lock:
                results.append(res)

        t1 = threading.Thread(target=attempt, args=(r1["reference_number"],))
        t2 = threading.Thread(target=attempt, args=(r2["reference_number"],))
        t1.start(); t2.start()
        t1.join(); t2.join()

        successes = [r for r in results if r["success"]]
        failures  = [r for r in results if not r["success"]]
        assert len(successes) == 1
        assert len(failures)  == 1
