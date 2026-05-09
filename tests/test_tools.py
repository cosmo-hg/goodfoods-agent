"""
Unit tests for core tools using an in-memory (temp-file) SQLite database.
Run: pytest tests/test_tools.py -v
"""

import pytest
import tempfile
import os

from config import init_db
from tools.search_branches import search_branches, score_branch, haversine
from tools.check_availability import check_availability, get_all_slots, time_to_minutes
from tools.make_reservation import make_reservation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Temporary SQLite DB initialised with the full schema."""
    path = str(tmp_path / "test_goodfoods.db")
    init_db(path)
    return path


@pytest.fixture
def db_with_branch(db_path):
    """DB with one branch (Italian, capacity=50, Downtown)."""
    from config import get_db
    conn = get_db(db_path)
    conn.execute(
        """
        INSERT INTO branches
            (name, neighborhood, cuisine, capacity, rating,
             latitude, longitude, price_range,
             dietary_vegetarian, dietary_vegan, dietary_gluten_free,
             dietary_halal, dietary_kosher, parking, outdoor_seating)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Bella Cucina Downtown", "Downtown", "Italian", 50, 4.5,
            40.7128, -74.0060, 2,
            1, 0, 1, 0, 0, 1, 1,
        ),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def branch_id(db_with_branch):
    from config import get_db
    conn = get_db(db_with_branch)
    row = conn.execute("SELECT id FROM branches LIMIT 1").fetchone()
    conn.close()
    return row["id"]


# ---------------------------------------------------------------------------
# search_branches scoring tests
# ---------------------------------------------------------------------------

class TestSearchBranchesScoring:
    def _make_branch(self, **kwargs):
        base = dict(
            id=1, name="Test", neighborhood="Downtown", cuisine="Italian",
            capacity=50, rating=4.0, latitude=40.71, longitude=-74.00,
            price_range=2, dietary_vegetarian=0, dietary_vegan=0,
            dietary_gluten_free=0, dietary_halal=0, dietary_kosher=0,
            parking=0, outdoor_seating=0,
        )
        base.update(kwargs)
        return base

    def test_cuisine_match_scores_40(self):
        branch = self._make_branch(cuisine="Italian")
        s = score_branch(branch, {"cuisine": "Italian"})
        assert s >= 40

    def test_cuisine_mismatch_no_cuisine_points(self):
        branch = self._make_branch(cuisine="Italian")
        s_match = score_branch(branch, {"cuisine": "Italian"})
        s_miss = score_branch(branch, {"cuisine": "Mexican"})
        assert s_match - s_miss == 40

    def test_cuisine_case_insensitive(self):
        branch = self._make_branch(cuisine="Italian")
        s = score_branch(branch, {"cuisine": "italian"})
        assert s >= 40

    def test_capacity_fit_scores_20(self):
        branch = self._make_branch(capacity=10)
        s_fit = score_branch(branch, {"party_size": 10})
        s_over = score_branch(branch, {"party_size": 11})
        assert s_fit - s_over == 20

    def test_rating_normalised_to_10_pts(self):
        # 4.8 → 10 pts; 3.8 → 0 pts
        branch_high = self._make_branch(rating=4.8, cuisine=None)
        branch_low = self._make_branch(rating=3.8, cuisine=None)
        diff = score_branch(branch_high, {}) - score_branch(branch_low, {})
        assert abs(diff - 10) < 0.01

    def test_location_hint_match_scores_25(self):
        branch = self._make_branch(neighborhood="Downtown")
        s_match = score_branch(branch, {"location_hint": "Downtown"})
        s_miss = score_branch(branch, {"location_hint": "Uptown"})
        assert s_match - s_miss == 25

    def test_dietary_vegetarian_scores_15(self):
        branch = self._make_branch(dietary_vegetarian=1)
        s_match = score_branch(branch, {"dietary_vegetarian": True})
        s_no = score_branch(branch, {})
        assert s_match - s_no == 15

    def test_dietary_vegan_scores_15(self):
        branch = self._make_branch(dietary_vegan=1)
        s = score_branch(branch, {"dietary_vegan": True})
        s0 = score_branch(branch, {})
        assert s - s0 == 15

    def test_dietary_flag_not_set_no_points(self):
        branch = self._make_branch(dietary_halal=0)
        s = score_branch(branch, {"dietary_halal": True})
        s0 = score_branch(branch, {})
        assert s == s0

    def test_price_range_match_scores_10(self):
        branch = self._make_branch(price_range=3)
        s_match = score_branch(branch, {"price_range": 3})
        s_miss = score_branch(branch, {"price_range": 1})
        assert s_match - s_miss == 10

    def test_proximity_scores_up_to_20(self):
        # Same coordinates → max proximity (20 pts)
        branch = self._make_branch(latitude=40.71, longitude=-74.00)
        s = score_branch(branch, {"latitude": 40.71, "longitude": -74.00})
        # Without lat/lon → 0 pts for proximity
        s0 = score_branch(branch, {})
        assert s - s0 == pytest.approx(20.0, abs=0.1)

    def test_haversine_zero_distance(self):
        assert haversine(40.71, -74.00, 40.71, -74.00) == pytest.approx(0.0, abs=1e-6)

    def test_haversine_known_distance(self):
        # NYC to London ≈ 5570 km
        dist = haversine(40.7128, -74.0060, 51.5074, -0.1278)
        assert 5500 < dist < 5650

    def test_returns_top_3(self, db_with_branch):
        from config import get_db
        conn = get_db(db_with_branch)
        # Add two more branches
        conn.executemany(
            """
            INSERT INTO branches
                (name, neighborhood, cuisine, capacity, rating, latitude, longitude,
                 price_range, dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                 dietary_halal, dietary_kosher, parking, outdoor_seating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Midtown Grill", "Midtown", "American", 40, 4.0, 40.75, -73.99, 2, 0,0,0,0,0,0,0),
                ("Sakura Ramen Bar Uptown", "Uptown", "Japanese", 30, 4.2, 40.78, -73.97, 2, 0,0,0,0,0,0,0),
                ("Lotus Garden East", "East Side", "Thai", 60, 4.6, 40.72, -73.96, 1, 1,1,0,0,0,0,0),
            ],
        )
        conn.commit()
        conn.close()

        results = search_branches({"cuisine": "Italian"}, db_with_branch)
        assert len(results) <= 3
        assert len(results) >= 1

    def test_results_sorted_by_score(self, db_with_branch):
        results = search_branches({"cuisine": "Italian", "party_size": 2}, db_with_branch)
        scores = [r["match_score"] for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# check_availability tests
# ---------------------------------------------------------------------------

class TestCheckAvailability:
    def test_slots_start_at_1100(self):
        slots = get_all_slots()
        assert slots[0] == "11:00"

    def test_slots_end_at_2230(self):
        slots = get_all_slots()
        assert slots[-1] == "22:30"

    def test_slot_count(self):
        # 11:00 to 22:30 in 30-min increments = 24 slots
        slots = get_all_slots()
        assert len(slots) == 24

    def test_all_slots_available_empty_day(self, db_with_branch, branch_id):
        available = check_availability(branch_id, "2026-12-01", party_size=2,
                                       db_path=db_with_branch)
        assert isinstance(available, list)
        assert len(available) == 24
        assert "11:00" in available
        assert "22:30" in available

    def test_full_capacity_blocks_slot(self, db_with_branch, branch_id):
        from config import get_db
        conn = get_db(db_with_branch)
        # Fill entire capacity at 12:00
        conn.execute(
            """INSERT INTO reservations
               (reference_number, branch_id, user_name, user_email, user_phone,
                party_size, date, time, status)
               VALUES ('GF-T00001', ?, 'A', 'a@b.com', '555', 50, '2026-12-01', '12:00', 'confirmed')""",
            (branch_id,),
        )
        conn.commit()
        conn.close()

        available = check_availability(branch_id, "2026-12-01", party_size=1,
                                       db_path=db_with_branch)
        # 12:00 slot must be gone
        assert "12:00" not in available

    def test_partial_capacity_still_available(self, db_with_branch, branch_id):
        from config import get_db
        conn = get_db(db_with_branch)
        conn.execute(
            """INSERT INTO reservations
               (reference_number, branch_id, user_name, user_email, user_phone,
                party_size, date, time, status)
               VALUES ('GF-T00002', ?, 'B', 'b@c.com', '555', 20, '2026-12-02', '14:00', 'confirmed')""",
            (branch_id,),
        )
        conn.commit()
        conn.close()

        # 30 seats still free — slot should appear for party_size=10
        available = check_availability(branch_id, "2026-12-02", party_size=10,
                                       db_path=db_with_branch)
        assert "14:00" in available

    def test_90_minute_window_blocks_overlapping_slots(self, db_with_branch, branch_id):
        from config import get_db
        conn = get_db(db_with_branch)
        # Fill capacity at 12:00 → occupies 12:00–13:30
        conn.execute(
            """INSERT INTO reservations
               (reference_number, branch_id, user_name, user_email, user_phone,
                party_size, date, time, status)
               VALUES ('GF-T00003', ?, 'C', 'c@d.com', '555', 50, '2026-12-03', '12:00', 'confirmed')""",
            (branch_id,),
        )
        conn.commit()
        conn.close()

        available = check_availability(branch_id, "2026-12-03", party_size=1,
                                       db_path=db_with_branch)
        # 11:30 overlaps with 12:00–13:30 (11:30+90=13:00 > 12:00)
        assert "11:30" not in available
        # 13:00 overlaps (13:00 < 13:30)
        assert "13:00" not in available
        # 13:30 does NOT overlap (13:30 is not < 13:30)
        assert "13:30" in available

    def test_cancelled_reservation_not_counted(self, db_with_branch, branch_id):
        from config import get_db
        conn = get_db(db_with_branch)
        conn.execute(
            """INSERT INTO reservations
               (reference_number, branch_id, user_name, user_email, user_phone,
                party_size, date, time, status)
               VALUES ('GF-T00004', ?, 'D', 'd@e.com', '555', 50, '2026-12-04', '18:00', 'cancelled')""",
            (branch_id,),
        )
        conn.commit()
        conn.close()

        available = check_availability(branch_id, "2026-12-04", party_size=50,
                                       db_path=db_with_branch)
        assert "18:00" in available

    def test_nonexistent_branch_returns_error(self, db_path):
        result = check_availability(9999, "2026-12-01", party_size=2, db_path=db_path)
        assert isinstance(result, dict)
        assert "error" in result

    def test_time_to_minutes(self):
        assert time_to_minutes("11:00") == 660
        assert time_to_minutes("22:30") == 1350
        assert time_to_minutes("12:30") == 750


# ---------------------------------------------------------------------------
# make_reservation conflict detection tests
# ---------------------------------------------------------------------------

class TestMakeReservation:
    def test_successful_reservation_returns_gf_reference(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Jane Doe",
            user_email="jane@example.com",
            user_phone="555-0001",
            party_size=4,
            date="2026-12-10",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is True
        assert result["reference_number"].startswith("GF-")
        assert len(result["reference_number"]) == 9  # GF-XXXXXX

    def test_reference_number_format(self, db_with_branch, branch_id):
        import re
        result = make_reservation(
            branch_id=branch_id,
            user_name="John Smith",
            user_email="john@example.com",
            user_phone="555-0002",
            party_size=2,
            date="2026-12-11",
            time="20:00",
            db_path=db_with_branch,
        )
        assert re.match(r"^GF-[A-Z0-9]{6}$", result["reference_number"])

    def test_conflict_detection_same_slot_full_capacity(self, db_with_branch, branch_id):
        # First booking fills capacity
        r1 = make_reservation(
            branch_id=branch_id,
            user_name="A Guest",
            user_email="a@example.com",
            user_phone="555-1000",
            party_size=50,
            date="2026-12-15",
            time="13:00",
            db_path=db_with_branch,
        )
        assert r1["success"] is True

        # Second booking at same slot should fail
        r2 = make_reservation(
            branch_id=branch_id,
            user_name="B Guest",
            user_email="b@example.com",
            user_phone="555-2000",
            party_size=1,
            date="2026-12-15",
            time="13:00",
            db_path=db_with_branch,
        )
        assert r2["success"] is False
        assert "not available" in r2["error"].lower()

    def test_non_overlapping_slot_succeeds_after_full_booking(self, db_with_branch, branch_id):
        # Fill 13:00
        r1 = make_reservation(
            branch_id=branch_id,
            user_name="A Guest",
            user_email="a2@example.com",
            user_phone="555-3000",
            party_size=50,
            date="2026-12-16",
            time="13:00",
            db_path=db_with_branch,
        )
        assert r1["success"] is True

        # 14:30 does not overlap with 13:00–14:30 window (14:30 starts exactly at window end)
        r2 = make_reservation(
            branch_id=branch_id,
            user_name="B Guest",
            user_email="b2@example.com",
            user_phone="555-4000",
            party_size=50,
            date="2026-12-16",
            time="14:30",
            db_path=db_with_branch,
        )
        assert r2["success"] is True

    def test_reservation_with_occasion_triggers_crm(self, db_with_branch, branch_id):
        from config import get_db
        result = make_reservation(
            branch_id=branch_id,
            user_name="Birthday Person",
            user_email="bday@example.com",
            user_phone="555-5000",
            party_size=6,
            date="2026-12-20",
            time="19:30",
            occasion="birthday",
            db_path=db_with_branch,
        )
        assert result["success"] is True

        conn = get_db(db_with_branch)
        row = conn.execute(
            "SELECT * FROM occasion_crm WHERE reservation_id = ?",
            (result["reservation_id"],),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["occasion"] == "birthday"

    def test_invalid_slot_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Night Owl",
            user_email="owl@example.com",
            user_phone="555-6000",
            party_size=2,
            date="2026-12-22",
            time="23:30",  # outside operating hours
            db_path=db_with_branch,
        )
        assert result["success"] is False

    def test_user_record_upserted(self, db_with_branch, branch_id):
        from config import get_db
        make_reservation(
            branch_id=branch_id,
            user_name="Loyal Guest",
            user_email="loyal@example.com",
            user_phone="555-7000",
            party_size=2,
            date="2026-12-25",
            time="12:00",
            db_path=db_with_branch,
        )
        conn = get_db(db_with_branch)
        user = conn.execute(
            "SELECT total_reservations FROM users WHERE email = 'loyal@example.com'"
        ).fetchone()
        conn.close()
        assert user is not None
        assert user["total_reservations"] == 1


# ---------------------------------------------------------------------------
# Input validation tests (date, party size, email, branch active)
# ---------------------------------------------------------------------------

class TestMakeReservationValidation:
    """Validate that make_reservation rejects bad inputs before touching the DB."""

    def test_past_date_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Time Traveller",
            user_email="back@future.com",
            user_phone="555-0000",
            party_size=2,
            date="2020-01-01",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "past" in result["error"].lower()

    def test_zero_party_size_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Ghost",
            user_email="ghost@example.com",
            user_phone="555-0001",
            party_size=0,
            date="2030-06-01",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "party size" in result["error"].lower()

    def test_negative_party_size_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Negative Nancy",
            user_email="neg@example.com",
            user_phone="555-0002",
            party_size=-3,
            date="2030-06-01",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "party size" in result["error"].lower()

    def test_oversized_party_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Mass Event",
            user_email="mass@example.com",
            user_phone="555-0003",
            party_size=501,
            date="2030-06-01",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "500" in result["error"]

    def test_invalid_email_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Bad Email",
            user_email="not-an-email",
            user_phone="555-0004",
            party_size=2,
            date="2030-06-01",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "email" in result["error"].lower()

    def test_invalid_date_format_rejected(self, db_with_branch, branch_id):
        result = make_reservation(
            branch_id=branch_id,
            user_name="Oops",
            user_email="oops@example.com",
            user_phone="555-0005",
            party_size=2,
            date="15/06/2030",
            time="19:00",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "date" in result["error"].lower()

    def test_inactive_branch_rejected(self, db_path):
        from config import get_db
        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO branches
               (name, neighborhood, cuisine, capacity, rating,
                latitude, longitude, price_range,
                dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                dietary_halal, dietary_kosher, parking, outdoor_seating, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Closed Branch", "Midtown", "French", 40, 4.0,
             40.75, -73.98, 3, 0, 0, 0, 0, 0, 0, 0, 0),
        )
        conn.commit()
        inactive_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        result = make_reservation(
            branch_id=inactive_id,
            user_name="Hopeful Guest",
            user_email="hopeful.guest@realemail.com",
            user_phone="555-0006",
            party_size=2,
            date="2030-06-01",
            time="19:00",
            db_path=db_path,
        )
        assert result["success"] is False
        assert "closed" in result["error"].lower() or "not accepting" in result["error"].lower()


class TestCheckAvailabilityEdgeCases:
    """Edge cases for the updated check_availability."""

    def test_inactive_branch_returns_error(self, db_path):
        from config import get_db
        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO branches
               (name, neighborhood, cuisine, capacity, rating,
                latitude, longitude, price_range,
                dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                dietary_halal, dietary_kosher, parking, outdoor_seating, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Inactive Branch", "Uptown", "Thai", 30, 4.1,
             40.78, -73.97, 2, 0, 0, 0, 0, 0, 0, 0, 0),
        )
        conn.commit()
        bid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        result = check_availability(bid, "2030-06-01", party_size=2, db_path=db_path)
        assert isinstance(result, dict)
        assert "error" in result

    def test_branch_with_custom_hours_limits_slots(self, db_path):
        from config import get_db
        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO branches
               (name, neighborhood, cuisine, capacity, rating,
                latitude, longitude, price_range,
                dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                dietary_halal, dietary_kosher, parking, outdoor_seating,
                opening_time, closing_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Late Night Branch", "Arts Quarter", "Korean", 50, 4.3,
             40.73, -74.00, 2, 0, 0, 0, 0, 0, 0, 0,
             "18:00", "23:00"),
        )
        conn.commit()
        bid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        slots = check_availability(bid, "2030-07-01", party_size=2, db_path=db_path)
        assert isinstance(slots, list)
        assert "11:00" not in slots
        assert "18:00" in slots
        assert "22:30" in slots
        assert "23:00" in slots

    def test_null_branch_id_returns_error(self, db_path):
        result = check_availability(None, "2030-06-01", party_size=2, db_path=db_path)
        assert isinstance(result, dict)
        assert "error" in result


class TestModifyReservationValidation:
    """Validate that modify_reservation rejects invalid inputs."""

    def _book(self, db_with_branch, branch_id):
        return make_reservation(
            branch_id=branch_id,
            user_name="Test Guest",
            user_email="test@example.com",
            user_phone="555-9999",
            party_size=4,
            date="2030-08-01",
            time="19:00",
            db_path=db_with_branch,
        )

    def test_modify_to_past_date_rejected(self, db_with_branch, branch_id):
        from tools.modify_cancel import modify_reservation
        r = self._book(db_with_branch, branch_id)
        assert r["success"] is True

        result = modify_reservation(
            reference_number=r["reference_number"],
            date="2020-01-01",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "past" in result["error"].lower()

    def test_modify_invalid_date_format_rejected(self, db_with_branch, branch_id):
        from tools.modify_cancel import modify_reservation
        r = self._book(db_with_branch, branch_id)
        assert r["success"] is True

        result = modify_reservation(
            reference_number=r["reference_number"],
            date="not-a-date",
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "date" in result["error"].lower()

    def test_modify_zero_party_size_rejected(self, db_with_branch, branch_id):
        from tools.modify_cancel import modify_reservation
        r = self._book(db_with_branch, branch_id)
        assert r["success"] is True

        result = modify_reservation(
            reference_number=r["reference_number"],
            party_size=0,
            db_path=db_with_branch,
        )
        assert result["success"] is False
        assert "party size" in result["error"].lower()


class TestBranchSlots:
    """Tests for get_branch_slots with custom hours."""

    def test_custom_opening_time(self):
        from tools.check_availability import get_branch_slots
        slots = get_branch_slots("18:00", "22:00")
        assert slots[0] == "18:00"
        assert slots[-1] == "22:00"

    def test_custom_closing_before_default(self):
        from tools.check_availability import get_branch_slots
        slots = get_branch_slots("11:00", "20:00")
        assert "11:00" in slots
        assert "20:00" in slots
        assert "22:30" not in slots

    def test_bad_time_format_falls_back_to_defaults(self):
        from tools.check_availability import get_branch_slots
        slots = get_branch_slots("bad", "time")
        assert "11:00" in slots
        assert "22:30" in slots
