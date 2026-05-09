"""
Seed realistic demo reservations so the Live Dashboard shows rich data immediately.
Run:  python scripts/seed_demo_reservations.py [--clear]

  --clear  deletes ALL existing reservations before inserting (useful for a clean demo)
"""
import sys, random, string, datetime as _dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import init_db, get_db

random.seed(2026)

# ── Demo guest pool ────────────────────────────────────────────────────────────
GUESTS = [
    ("Aryan Mehta",     "aryan.mehta@gmail.com",      "+1-212-555-0101"),
    ("Priya Sharma",    "priya.sharma@outlook.com",   "+1-212-555-0102"),
    ("James O'Brien",   "james.obrien@corp.com",      "+1-646-555-0201"),
    ("Sofia Rossi",     "sofia.rossi@gmail.com",      "+1-718-555-0301"),
    ("Lena Fischer",    "lena.fischer@example.de",    "+1-212-555-0401"),
    ("Kevin Park",      "kevin.park@nyu.edu",         "+1-917-555-0501"),
    ("Aisha Thompson",  "aisha.t@hotmail.com",        "+1-212-555-0601"),
    ("Marco DeLuca",    "m.deluca@financeco.com",     "+1-646-555-0701"),
    ("Natasha Ivanova",  "n.ivanova@yahoo.com",       "+1-212-555-0801"),
    ("Chen Wei",        "chen.wei@techstartup.io",   "+1-917-555-0901"),
    ("Sarah Mitchell",  "s.mitchell@lawfirm.com",    "+1-212-555-1001"),
    ("Raj Patel",       "raj.patel@consulting.com",  "+1-646-555-1101"),
    ("Olivia Brown",    "olivia.b@design.co",        "+1-718-555-1201"),
    ("David Kim",       "d.kim@bankgroup.com",       "+1-212-555-1301"),
    ("Emma Wilson",     "emma.w@media.com",          "+1-917-555-1401"),
    ("Carlos Vega",     "c.vega@restaurant.com",     "+1-212-555-1501"),
    ("Hannah Lee",      "hannah.lee@startup.io",     "+1-646-555-1601"),
    ("Michael Torres",  "m.torres@realty.com",       "+1-212-555-1701"),
    ("Fatima Al-Rashid","f.alrashid@embassy.gov",    "+1-212-555-1801"),
    ("Lucas Dupont",    "lucas.d@frenchco.fr",       "+1-917-555-1901"),
]

OCCASIONS = [
    "birthday", "anniversary", "business dinner",
    "graduation", "proposal", None, None, None,
]

SPECIAL_REQUESTS = [
    "Window table preferred",
    "Nut allergy — please flag kitchen",
    "Wheelchair accessible seating required",
    "Quiet corner for an intimate celebration",
    "Cake ready to serve at 20:30",
    "High chair needed for toddler",
    "Kosher meal requested",
    "Anniversary card on table please",
    None, None, None, None,
]

PEAK_TIMES = ["12:00", "12:30", "13:00", "19:00", "19:30", "20:00", "20:30"]
ALL_TIMES   = ["11:00","11:30","12:00","12:30","13:00","13:30","14:00",
               "18:00","18:30","19:00","19:30","20:00","20:30","21:00","21:30"]


def _gen_ref(existing):
    chars = string.ascii_uppercase + string.digits
    for _ in range(100):
        ref = "GF-" + "".join(random.choices(chars, k=6))
        if ref not in existing:
            return ref
    raise RuntimeError("Could not generate unique ref")


def seed(clear=False):
    init_db()
    conn = get_db()

    if clear:
        print("  Clearing existing reservations…")
        conn.execute("DELETE FROM occasion_crm")
        conn.execute("DELETE FROM dropoffs")
        conn.execute("DELETE FROM reservations")
        conn.execute("DELETE FROM users")
        conn.commit()

    # Pick a diverse set of 12 branches
    rows = conn.execute(
        "SELECT id, name, capacity, neighborhood, cuisine "
        "FROM branches WHERE is_active=1 ORDER BY RANDOM() LIMIT 12"
    ).fetchall()
    branches = [dict(r) for r in rows]
    if not branches:
        print("No active branches found — run seed_data.py first.")
        return

    today      = _dt.date.today()
    demo_dates = [
        str(today),
        str(today + _dt.timedelta(days=1)),
        str(today + _dt.timedelta(days=2)),
        str(today + _dt.timedelta(days=3)),
        str(today + _dt.timedelta(days=7)),   # next week
    ]

    existing_refs = {
        r[0] for r in conn.execute("SELECT reference_number FROM reservations").fetchall()
    }
    existing_users = {
        r[0] for r in conn.execute("SELECT email FROM users").fetchall()
    }

    # How many bookings per date (heavier on today + tomorrow for demo impact)
    bookings_per_date = [10, 9, 7, 5, 4]

    total = 0
    for date_str, n_bookings in zip(demo_dates, bookings_per_date):
        for _ in range(n_bookings):
            branch   = random.choice(branches)
            guest    = random.choice(GUESTS)
            name, email, phone = guest
            party    = random.choice([2, 2, 2, 3, 4, 4, 6, 8, 10])
            # Bias toward peak times
            time_str = random.choice(PEAK_TIMES + ALL_TIMES)
            occasion = random.choice(OCCASIONS)
            special  = random.choice(SPECIAL_REQUESTS)

            # Skip if this would exceed capacity (rough check — just limit party ≤ capacity)
            if party > branch["capacity"]:
                party = max(2, branch["capacity"] // 4)

            ref = _gen_ref(existing_refs)
            existing_refs.add(ref)

            conn.execute("""
                INSERT INTO reservations
                    (reference_number, branch_id, user_name, user_email, user_phone,
                     party_size, date, time, occasion, special_requests, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
            """, (ref, branch["id"], name, email, phone,
                  party, date_str, time_str, occasion, special))

            # Upsert user
            if email not in existing_users:
                conn.execute("""
                    INSERT INTO users (email, name, phone, total_reservations)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(email) DO UPDATE SET
                        total_reservations = total_reservations + 1
                """, (email, name, phone))
                existing_users.add(email)
            else:
                conn.execute(
                    "UPDATE users SET total_reservations = total_reservations + 1 WHERE email = ?",
                    (email,)
                )

            # Occasion CRM
            if occasion:
                followup = str(_dt.date.fromisoformat(date_str) + _dt.timedelta(days=1))
                res_id = conn.execute(
                    "SELECT id FROM reservations WHERE reference_number=?", (ref,)
                ).fetchone()["id"]
                conn.execute("""
                    INSERT INTO occasion_crm
                        (reservation_id, occasion, followup_date, user_email, user_name, branch_name, sent)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (res_id, occasion, followup, email, name, branch["name"]))

            total += 1

    conn.commit()
    conn.close()
    print(f"  ✅ Seeded {total} demo reservations across {len(demo_dates)} dates.")
    print(f"  Dates: {', '.join(demo_dates)}")
    print("  Open the Live Dashboard tab and select any of these dates to see the data.")


if __name__ == "__main__":
    clear_flag = "--clear" in sys.argv
    print(f"Seeding demo reservations {'(clearing first)' if clear_flag else '(appending)'}…")
    seed(clear=clear_flag)
