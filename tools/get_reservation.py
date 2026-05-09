from config import get_db


def get_reservation(reference_number, db_path=None):
    """
    Look up a GoodFoods reservation by its GF-XXXXXX reference number.
    Returns full booking details including branch info, or an error if not found.
    """
    if not reference_number or not str(reference_number).strip():
        return {"found": False, "error": "Reference number is required."}

    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            r.reference_number, r.user_name, r.user_email, r.user_phone,
            r.party_size, r.date, r.time, r.occasion, r.special_requests,
            r.status, r.created_at,
            b.name  AS branch_name,
            b.address,
            b.phone AS branch_phone,
            b.cuisine,
            b.neighborhood
        FROM reservations r
        LEFT JOIN branches b ON r.branch_id = b.id
        WHERE r.reference_number = ?
        """,
        (str(reference_number).strip().upper(),),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "found": False,
            "error": (
                f"No reservation found with reference {reference_number}. "
                "Please double-check the reference number."
            ),
        }

    return {"found": True, **dict(row)}
