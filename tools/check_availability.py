import datetime as _dt
from config import get_db


def time_to_minutes(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m


def minutes_to_time(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def get_all_slots():
    """All 30-minute slots from 11:00 to 22:30 (default operating hours)."""
    slots = []
    t = time_to_minutes("11:00")
    end = time_to_minutes("22:30")
    while t <= end:
        slots.append(minutes_to_time(t))
        t += 30
    return slots


def get_branch_slots(opening_time, closing_time):
    """All 30-minute slots within a branch's actual operating hours."""
    try:
        slots = []
        t = time_to_minutes(opening_time)
        end = time_to_minutes(closing_time)
        while t <= end:
            slots.append(minutes_to_time(t))
            t += 30
        return slots
    except (ValueError, AttributeError):
        return get_all_slots()


def check_availability(branch_id, date, party_size=1, db_path=None):
    """
    Returns list of available HH:MM slots for branch on date.
    Each reservation occupies a 90-minute window; slots overlap if windows intersect.
    Respects branch-specific opening/closing hours and active status.
    """
    if not branch_id:
        return {"error": "Invalid branch_id"}

    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT capacity, opening_time, closing_time, is_active FROM branches WHERE id = ?",
        (branch_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": f"Branch {branch_id} not found"}

    if not row["is_active"]:
        conn.close()
        return {"error": f"Branch {branch_id} is temporarily closed and not accepting reservations"}

    capacity = row["capacity"]
    opening = row["opening_time"] or "11:00"
    closing = row["closing_time"] or "22:30"

    cursor.execute(
        """
        SELECT time, party_size FROM reservations
        WHERE branch_id = ? AND date = ? AND status = 'confirmed'
        """,
        (branch_id, date),
    )
    reservations = cursor.fetchall()
    conn.close()

    # For today's date, calculate the earliest bookable slot (current time + 30 min buffer).
    today_str = str(_dt.date.today())
    if str(date) == today_str:
        now = _dt.datetime.now()
        earliest_min = (now.hour * 60 + now.minute) + 30  # 30-minute booking buffer
    else:
        earliest_min = 0  # future date — all slots eligible

    available = []
    for slot in get_branch_slots(opening, closing):
        slot_min = time_to_minutes(slot)

        # Skip slots that have already passed (or are too soon) for today
        if slot_min < earliest_min:
            continue

        slot_end = slot_min + 90

        occupied = 0
        for res in reservations:
            r_min = time_to_minutes(res["time"])
            r_end = r_min + 90
            if r_min < slot_end and r_end > slot_min:
                occupied += res["party_size"]

        if capacity - occupied >= party_size:
            available.append(slot)

    return available
