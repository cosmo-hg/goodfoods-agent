from config import get_db


def get_user_profile(email, db_path=None):
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return {"found": False, "email": email}

    user_dict = dict(user)

    cursor.execute(
        """
        SELECT r.reference_number, r.date, r.time, r.party_size,
               r.occasion, r.status, b.name AS branch_name, b.cuisine
        FROM reservations r
        LEFT JOIN branches b ON r.branch_id = b.id
        WHERE r.user_email = ?
        ORDER BY r.date DESC, r.time DESC
        LIMIT 5
        """,
        (email,),
    )
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    user_dict["recent_reservations"] = history
    user_dict["found"] = True
    return user_dict
