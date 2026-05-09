from config import get_db

FILL_RATE_THRESHOLD = 0.70  # alert when >= 70% of daily capacity is reserved
WINDOW_HOURS = 72

# 11:00–22:30 operating hours = 11.5 h; avg dining session = 90 min → ~7 effective turns per day
_EFFECTIVE_DAILY_TURNS = 7


def get_fill_rate(branch_id, date, db_path=None):
    """
    Fill rate = total reserved seats on `date` / (capacity × effective daily turns).
    Only counts bookings created within the last WINDOW_HOURS (T-72h window).
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT capacity FROM branches WHERE id = ?", (branch_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return 0.0

    capacity = row["capacity"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(party_size), 0) AS total_booked
        FROM reservations
        WHERE branch_id = ?
          AND date = ?
          AND status = 'confirmed'
          AND created_at >= datetime('now', ? || ' hours')
        """,
        (branch_id, date, f"-{WINDOW_HOURS}"),
    )
    result = cursor.fetchone()
    conn.close()

    total_booked = result["total_booked"] if result else 0
    max_daily_seats = capacity * _EFFECTIVE_DAILY_TURNS
    return total_booked / max_daily_seats if max_daily_seats > 0 else 0.0


def check_and_alert_procurement(branch_id, branch_name, date, db_path=None):
    """
    Returns a procurement alert dict when fill rate crosses the threshold, else None.
    A branch with capacity 50 has ~350 max daily seats (7 turns × 50).
    At 70% that's 245 seats — a genuinely high-demand signal.
    """
    fill_rate = get_fill_rate(branch_id, date, db_path)

    if fill_rate >= FILL_RATE_THRESHOLD:
        return {
            "alert": True,
            "branch_id": branch_id,
            "branch_name": branch_name,
            "date": date,
            "fill_rate_pct": round(fill_rate * 100, 1),
            "message": (
                f"PROCUREMENT ALERT: {branch_name} is at "
                f"{fill_rate * 100:.1f}% capacity for {date} "
                f"(T-{WINDOW_HOURS}h window). "
                "Consider pre-ordering additional stock."
            ),
        }

    return None
