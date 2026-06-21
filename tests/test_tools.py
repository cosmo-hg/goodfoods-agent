"""
Unit tests for core tools using an in-memory (temp-file) SQLite database.
Run: pytest tests/test_tools.py -v
"""

import pytest
import tempfile
import os

from config import init_db
from tools.search_branches import search_branches, haversine
from tools.check_availability import check_availability, get_all_slots, time_to_minutes
from tools.make_reservation import make_reservation
from tools.is_served_area import is_served_area
from tools.location_resolver import resolve_user_location, nearest_neighborhood
# Test-only helper: skip the network call inside resolve_user_location
def resolve_user_location_offline(lat, lon):
    return resolve_user_location(lat, lon, with_geocode=False)



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
# search_branches behaviour tests (filters as filters)
# ---------------------------------------------------------------------------

class TestSearchBranchesBehaviour:
    """
    Confirms the bug that prompted the rewrite is fixed: cuisine and location
    are SQL filters, not fuzzy score bonuses. An unmatched query returns [].
    """

    def _seed_branches(self, db_path):
        """Seed two Italian and one American branch across known areas."""
        from config import get_db
        conn = get_db(db_path)
        conn.executemany(
            """INSERT INTO branches
               (name, neighborhood, cuisine, capacity, rating, latitude, longitude,
                price_range, popularity_score,
                dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                dietary_halal, dietary_kosher, parking, outdoor_seating)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("GoodFoods Indiranagar — Italian", "Indiranagar", "Italian", 80, 4.6,
                 12.9716, 77.6412, 3, 88.0, 1, 1, 0, 0, 0, 1, 0),
                ("GoodFoods Koramangala — Italian", "Koramangala", "Italian", 70, 4.3,
                 12.9352, 77.6245, 2, 65.0, 1, 0, 0, 0, 0, 1, 0),
                ("GoodFoods MG Road — American",    "MG Road",     "American", 90, 4.4,
                 12.9759, 77.6094, 3, 78.0, 1, 0, 0, 0, 0, 1, 0),
            ],
        )
        # Seed a pizza on the Indiranagar Italian branch so dish search has data.
        ids = conn.execute("SELECT id, cuisine FROM branches ORDER BY id").fetchall()
        for row in ids:
            if row["cuisine"] == "Italian":
                conn.execute(
                    """INSERT INTO menu_items
                       (branch_id, name, description, category, price, is_available,
                        is_vegetarian, is_vegan, is_gluten_free, is_halal, is_popular,
                        calories, dish_tags)
                       VALUES (?, 'Margherita Pizza', 'classic', 'Mains', 450, 1, 1, 0, 0, 1, 1, 720, 'pizza,italian,margherita,vegetarian')""",
                    (row["id"],),
                )
            elif row["cuisine"] == "American":
                conn.execute(
                    """INSERT INTO menu_items
                       (branch_id, name, description, category, price, is_available,
                        is_vegetarian, is_vegan, is_gluten_free, is_halal, is_popular,
                        calories, dish_tags)
                       VALUES (?, 'Classic Cheeseburger', 'beef', 'Mains', 520, 1, 0, 0, 0, 0, 1, 920, 'burger,american,beef,cheeseburger')""",
                    (row["id"],),
                )
        conn.commit()
        conn.close()

    def test_cuisine_is_a_hard_filter(self, db_path):
        """Asking for Italian must not return American — even if it scores high."""
        self._seed_branches(db_path)
        results = search_branches({"cuisine": "Italian", "party_size": 2}, db_path)
        assert len(results) >= 1
        assert all(r["cuisine"] == "Italian" for r in results)

    def test_location_outside_served_area_returns_empty(self, db_path):
        """The Brooklyn failure mode: a location not in our DB must return [].

        (is_served_area should have caught this earlier, but the search tool
        is the last line of defence.)"""
        self._seed_branches(db_path)
        results = search_branches({"cuisine": "Italian", "location_hint": "Brooklyn"}, db_path)
        assert results == []

    def test_dish_search_filters_to_branches_with_dish(self, db_path):
        """Searching for 'pizza' must only return branches whose menu has pizza."""
        self._seed_branches(db_path)
        results = search_branches({"dish": "pizza"}, db_path)
        assert len(results) >= 1
        for r in results:
            assert r["cuisine"] == "Italian"   # only Italians have pizza in fixture

    def test_dish_with_cuisine_match_yields_high_confidence(self, db_path):
        self._seed_branches(db_path)
        results = search_branches(
            {"cuisine": "Italian", "dish": "pizza", "location_hint": "Indiranagar"},
            db_path,
        )
        assert len(results) == 1
        assert results[0]["confidence"] == "high"

    def test_cuisine_synonym_resolves(self, db_path):
        """A dish-name synonym should resolve to its cuisine — 'pizza' → Italian."""
        self._seed_branches(db_path)
        results = search_branches({"cuisine": "pizza"}, db_path)
        assert len(results) >= 1
        assert all(r["cuisine"] == "Italian" for r in results)

    def test_popularity_drives_ranking_without_location(self, db_path):
        """Two Italian branches, top should be the one with higher popularity_score."""
        self._seed_branches(db_path)
        results = search_branches({"cuisine": "Italian"}, db_path)
        assert results[0]["popularity_score"] >= results[-1]["popularity_score"]

    def test_capacity_filter_drops_undersized(self, db_path):
        """A party of 100 won't fit any of our seeded branches → []."""
        self._seed_branches(db_path)
        results = search_branches({"cuisine": "Italian", "party_size": 200}, db_path)
        assert results == []

    def test_haversine_zero_distance(self):
        assert haversine(12.97, 77.59, 12.97, 77.59) == pytest.approx(0.0, abs=1e-6)

    def test_haversine_known_distance(self):
        # Bangalore (Indiranagar) to Mumbai ≈ 840 km
        dist = haversine(12.9716, 77.6412, 19.0760, 72.8777)
        assert 800 < dist < 900


# ---------------------------------------------------------------------------
# is_served_area tests
# ---------------------------------------------------------------------------

class TestIsServedArea:
    """The pre-search sanity check that stops the 'best pizza in Brooklyn' bug."""

    def test_canonical_neighbourhood_served(self):
        result = is_served_area("Indiranagar")
        assert result["served"] is True
        assert result["matched_neighborhood"] == "Indiranagar"

    def test_case_insensitive_match(self):
        result = is_served_area("KORAMANGALA")
        assert result["served"] is True
        assert result["matched_neighborhood"] == "Koramangala"

    def test_alias_resolves_to_canonical(self):
        result = is_served_area("Koramangala 5th Block")
        assert result["served"] is True
        assert result["matched_neighborhood"] == "Koramangala"

    def test_off_city_not_served(self):
        result = is_served_area("Brooklyn")
        assert result["served"] is False
        assert "Bangalore" in result["reason"]

    def test_other_indian_city_not_served(self):
        result = is_served_area("Pune")
        assert result["served"] is False

    def test_bangalore_unknown_neighbourhood_not_served(self):
        """City matches but neighbourhood doesn't — flagged honestly."""
        result = is_served_area("Electronic City Bangalore")
        # 'bangalore' appears → falls into the city-known-but-area-unknown branch
        assert result["served"] is False
        assert result["alternative_suggestion"] is not None

    def test_empty_location_treated_as_no_filter(self):
        result = is_served_area("")
        assert result["served"] is True
        assert result["matched_neighborhood"] is None


# ---------------------------------------------------------------------------
# location_resolver — turning raw GPS into a structured location decision
# ---------------------------------------------------------------------------

class TestLocationResolver:
    """
    Covers the four real-world cases:
      1. GPS inside Bangalore (Indiranagar)
      2. GPS on the city edge (Whitefield)
      3. GPS just outside the threshold (Electronic City area)
      4. GPS clearly outside the city (Pune, Mumbai)
    """

    def test_inside_bangalore_indiranagar(self):
        # 100ft Road, Indiranagar
        r = resolve_user_location_offline(12.9716, 77.6412)
        assert r["in_bangalore"] is True
        assert r["nearest_neighborhood"] == "Indiranagar"
        assert r["nearest_neighborhood_km"] < 1.0
        assert r["city_centre_distance_km"] < 10

    def test_inside_bangalore_whitefield(self):
        # Whitefield — far east but still in the chain's service area
        r = resolve_user_location_offline(12.9698, 77.7500)
        assert r["in_bangalore"] is True
        assert r["nearest_neighborhood"] == "Whitefield"

    def test_inside_bangalore_koramangala(self):
        r = resolve_user_location_offline(12.9352, 77.6245)
        assert r["in_bangalore"] is True
        assert r["nearest_neighborhood"] == "Koramangala"

    def test_pune_is_outside(self):
        # Pune — roughly 850 km from Bangalore
        r = resolve_user_location_offline(18.5204, 73.8567)
        assert r["in_bangalore"] is False
        assert r["city_centre_distance_km"] > 100

    def test_mumbai_is_outside(self):
        r = resolve_user_location_offline(19.0760, 72.8777)
        assert r["in_bangalore"] is False
        assert r["city_centre_distance_km"] > 100

    def test_delhi_is_outside(self):
        r = resolve_user_location_offline(28.6139, 77.2090)
        assert r["in_bangalore"] is False

    def test_just_within_threshold(self):
        # ~25 km north of MG Road — still treated as in-city
        r = resolve_user_location_offline(13.20, 77.6094)
        assert r["in_bangalore"] is True

    def test_just_outside_threshold(self):
        # ~50 km north — outside
        r = resolve_user_location_offline(13.45, 77.6094)
        assert r["in_bangalore"] is False

    def test_nearest_neighborhood_is_one_of_25(self):
        from config import NEIGHBORHOOD_COORDS
        # Any point inside the city should match one of the 25 served areas
        name, dist = nearest_neighborhood(12.9716, 77.6094)  # MG Road
        assert name in NEIGHBORHOOD_COORDS
        assert dist >= 0


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
            user_phone="9876543210",
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
            user_phone="9876543211",
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
            user_phone="9876543217",
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
            user_phone="9876543218",
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
            user_phone="9876543219",
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
            user_phone="9876543220",
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
            user_phone="9876543221",
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
            user_phone="9876543222",
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
            user_phone="9876543223",
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
            user_phone="9876543216",
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
            user_phone="9876543210",
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
            user_phone="9876543211",
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
            user_phone="9876543212",
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
            user_phone="9876543213",
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
            user_phone="9876543214",
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
            user_phone="9876543215",
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
            user_phone="9876543224",
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
