import datetime as _dt
from config import get_db
from tools.check_availability import check_availability
from intelligence.missed_booking import log_dropoff


def modify_reservation(
    reference_number,
    date=None,
    time=None,
    party_size=None,
    special_requests=None,
    db_path=None,
):
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM reservations WHERE reference_number = ?",
        (reference_number,),
    )
    reservation = cursor.fetchone()

    if not reservation:
        conn.close()
        return {"success": False, "error": f"Reservation {reference_number} not found"}

    if reservation["status"] == "cancelled":
        conn.close()
        return {"success": False, "error": "Cannot modify a cancelled reservation"}

    old_date = reservation["date"]
    old_time = reservation["time"]
    old_party = reservation["party_size"]

    new_date = date or old_date
    new_time = time or old_time
    new_party = party_size if party_size is not None else old_party
    new_requests = special_requests if special_requests is not None else reservation["special_requests"]

    # Validate new date if it changed
    if new_date != old_date:
        try:
            new_date_obj = _dt.date.fromisoformat(str(new_date))
            if new_date_obj < _dt.date.today():
                conn.close()
                return {"success": False, "error": "Cannot move a reservation to a past date."}
        except ValueError:
            conn.close()
            return {"success": False, "error": f"Invalid date format '{new_date}'. Use YYYY-MM-DD."}

    # Validate new party size if it changed
    if party_size is not None:
        try:
            new_party = int(new_party)
        except (TypeError, ValueError):
            conn.close()
            return {"success": False, "error": "Party size must be a whole number."}
        if new_party < 1:
            conn.close()
            return {"success": False, "error": "Party size must be at least 1."}
        if new_party > 500:
            conn.close()
            return {"success": False, "error": "For events over 500 guests please contact our events team."}

    date_or_time_changed = (new_date != old_date) or (new_time != old_time)
    party_increased = new_party > old_party

    if date_or_time_changed:
        # Moving to a different slot: need full new_party seats available there
        available = check_availability(reservation["branch_id"], new_date, new_party, db_path)
        if isinstance(available, dict) and "error" in available:
            conn.close()
            return {"success": False, "error": available["error"]}
        if new_time not in available:
            conn.close()
            return {
                "success": False,
                "error": (
                    f"{new_time} on {new_date} is not available "
                    f"for a party of {new_party}."
                ),
            }
    elif party_increased:
        # Same slot, larger party: only the DELTA needs to fit within remaining capacity.
        # check_availability already counts this reservation's current seats, so
        # asking for (new_party - old_party) correctly measures the extra seats needed.
        delta = new_party - old_party
        available = check_availability(reservation["branch_id"], new_date, delta, db_path)
        if isinstance(available, dict) and "error" in available:
            conn.close()
            return {"success": False, "error": available["error"]}
        if new_time not in available:
            conn.close()
            return {
                "success": False,
                "error": (
                    f"Not enough capacity at {new_time} to increase the party "
                    f"from {old_party} to {new_party}."
                ),
            }

    cursor.execute(
        """
        UPDATE reservations
        SET date = ?, time = ?, party_size = ?, special_requests = ?
        WHERE reference_number = ?
        """,
        (new_date, new_time, new_party, new_requests, reference_number),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "reference_number": reference_number,
        "date": new_date,
        "time": new_time,
        "party_size": new_party,
        "message": f"Reservation {reference_number} has been updated successfully.",
    }


def cancel_reservation(reference_number, reason=None, db_path=None):
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM reservations WHERE reference_number = ?",
        (reference_number,),
    )
    reservation = cursor.fetchone()

    if not reservation:
        conn.close()
        return {"success": False, "error": f"Reservation {reference_number} not found"}

    if reservation["status"] == "cancelled":
        conn.close()
        return {"success": False, "error": "Reservation is already cancelled"}

    cursor.execute(
        "UPDATE reservations SET status = 'cancelled' WHERE reference_number = ?",
        (reference_number,),
    )
    conn.commit()
    conn.close()

    # Log freed slot for waitlist notification
    log_dropoff(
        branch_id=reservation["branch_id"],
        reservation_id=reservation["id"],
        slot_date=reservation["date"],
        slot_time=reservation["time"],
        party_size=reservation["party_size"],
        db_path=db_path,
    )

    return {
        "success": True,
        "reference_number": reference_number,
        "message": (
            f"Reservation {reference_number} has been cancelled. "
            "We hope to welcome you back soon."
        ),
    }
