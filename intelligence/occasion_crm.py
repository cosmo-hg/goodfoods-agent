import datetime as _dt
from config import get_db


def schedule_occasion_followup(
    reservation_id,
    occasion,
    user_email,
    user_name,
    branch_name,
    date,
    db_path=None,
):
    """Write a follow-up entry to DB, scheduled for the day after the reservation."""
    try:
        reservation_date = date if isinstance(date, str) else str(date)
        followup = str(_dt.date.fromisoformat(reservation_date) + _dt.timedelta(days=1))
    except (ValueError, TypeError):
        followup = str(_dt.date.today() + _dt.timedelta(days=1))

    conn = get_db(db_path)
    conn.execute(
        """
        INSERT INTO occasion_crm
            (reservation_id, occasion, followup_date, user_email, user_name, branch_name, sent)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (reservation_id, occasion, followup, user_email, user_name, branch_name),
    )
    conn.commit()
    conn.close()


def send_due_followups(db_path=None):
    """
    Return all unsent follow-ups due today (followup_date == today).
    In production this triggers personalised emails; here it marks them sent and returns the list.
    """
    today = str(_dt.date.today())
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM occasion_crm WHERE followup_date = ? AND sent = 0",
        (today,),
    )
    due = [dict(row) for row in cursor.fetchall()]

    if due:
        ids = [r["id"] for r in due]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE occasion_crm SET sent = 1 WHERE id IN ({placeholders})", ids
        )
        conn.commit()

    conn.close()
    return due
