from config import get_db


def log_dropoff(branch_id, reservation_id, slot_date, slot_time, party_size, db_path=None):
    """Record a cancelled reservation as a potential drop-off opportunity."""
    conn = get_db(db_path)
    conn.execute(
        """
        INSERT INTO dropoffs
            (branch_id, reservation_id, slot_date, slot_time, party_size, notified)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (branch_id, reservation_id, slot_date, slot_time, party_size),
    )
    conn.commit()
    conn.close()


def check_and_notify_dropoffs(db_path=None):
    """
    Find drop-offs created in the last 2 hours where the freed slot is still in the future.
    In production, this would trigger a waitlist notification.
    Returns a list of actionable drop-offs.
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT d.*, b.name AS branch_name
        FROM dropoffs d
        JOIN branches b ON d.branch_id = b.id
        WHERE d.notified = 0
          AND d.created_at >= datetime('now', '-2 hours')
          AND (d.slot_date > date('now')
               OR (d.slot_date = date('now') AND d.slot_time > time('now')))
        """,
    )
    dropoffs = [dict(row) for row in cursor.fetchall()]

    if dropoffs:
        ids = [r["id"] for r in dropoffs]
        conn.execute(
            f"UPDATE dropoffs SET notified = 1 WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        conn.commit()

    conn.close()
    return dropoffs
