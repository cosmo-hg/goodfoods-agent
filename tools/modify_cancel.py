"""
Modify and cancel flows for existing reservations.

Both functions are now race-safe (atomic where it matters) and refuse to act
on bookings whose date has already passed — you can't legitimately modify or
cancel something that's already happened.
"""
import sqlite3
import datetime as _dt
from config import get_db
from tools.check_availability import time_to_minutes
from intelligence.missed_booking import log_dropoff


def _today() -> _dt.date:
    """Indirection so tests can monkeypatch if ever needed."""
    return _dt.date.today()


def _is_past(date_str: str) -> bool:
    """True iff the given ISO date is strictly before today."""
    try:
        return _dt.date.fromisoformat(str(date_str)) < _today()
    except (ValueError, TypeError):
        return False   # don't block on malformed dates; handled elsewhere


def modify_reservation(
    reference_number,
    date=None,
    time=None,
    party_size=None,
    special_requests=None,
    db_path=None,
):
    """
    Update date / time / party_size / special_requests on an existing booking.

    Race-safe: capacity check and UPDATE happen inside a BEGIN IMMEDIATE
    transaction. Refuses to modify a booking whose existing date is already
    in the past.
    """
    conn = get_db(db_path)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT * FROM reservations WHERE reference_number = ?",
            (reference_number,),
        )
        reservation = cursor.fetchone()

        if not reservation:
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Reservation {reference_number} not found."}

        if reservation["status"] == "cancelled":
            conn.rollback()
            conn.close()
            return {"success": False, "error": "Cannot modify a cancelled reservation."}

        # Refuse to modify a booking whose original date is already in the past.
        if _is_past(reservation["date"]):
            conn.rollback()
            conn.close()
            return {
                "success": False,
                "error": (
                    f"Reservation {reference_number} was for {reservation['date']}, "
                    "which is already in the past and cannot be modified."
                ),
            }

        old_date  = reservation["date"]
        old_time  = reservation["time"]
        old_party = reservation["party_size"]

        new_date     = date or old_date
        new_time     = time or old_time
        new_party    = party_size if party_size is not None else old_party
        new_requests = (special_requests if special_requests is not None
                        else reservation["special_requests"])

        # Validate the new date
        if new_date != old_date:
            try:
                new_date_obj = _dt.date.fromisoformat(str(new_date))
                if new_date_obj < _today():
                    conn.rollback()
                    conn.close()
                    return {"success": False, "error": "Cannot move a reservation to a past date."}
            except ValueError:
                conn.rollback()
                conn.close()
                return {"success": False, "error": f"Invalid date format '{new_date}'. Use YYYY-MM-DD."}

        # Validate the new party size
        if party_size is not None:
            try:
                new_party = int(new_party)
            except (TypeError, ValueError):
                conn.rollback()
                conn.close()
                return {"success": False, "error": "Party size must be a whole number."}
            if new_party < 1:
                conn.rollback()
                conn.close()
                return {"success": False, "error": "Party size must be at least 1."}
            if new_party > 500:
                conn.rollback()
                conn.close()
                return {"success": False, "error": "For events over 500 guests please contact our events team."}

        # Validate the new time format
        try:
            new_time_min = time_to_minutes(new_time)
        except (ValueError, AttributeError):
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Invalid time format '{new_time}'. Use HH:MM."}

        # ── Inline capacity check (inside the transaction) ─────────────────────
        date_or_time_changed = (new_date != old_date) or (new_time != old_time)
        party_increased      = new_party > old_party

        if date_or_time_changed or party_increased:
            cursor.execute(
                "SELECT capacity, opening_time, closing_time, is_active "
                "FROM branches WHERE id = ?",
                (reservation["branch_id"],),
            )
            branch_row = cursor.fetchone()
            if not branch_row or not branch_row["is_active"]:
                conn.rollback()
                conn.close()
                return {"success": False, "error": "Branch is no longer active."}

            opening = branch_row["opening_time"] or "12:00"
            closing = branch_row["closing_time"] or "23:00"
            if new_time_min < time_to_minutes(opening) or new_time_min > time_to_minutes(closing):
                conn.rollback()
                conn.close()
                return {"success": False, "error": f"Time {new_time} is outside branch hours ({opening}–{closing})."}

            # Sum overlapping confirmed bookings on the target date, EXCLUDING
            # this same reservation so its current seats aren't double-counted.
            cursor.execute(
                """SELECT time, party_size FROM reservations
                   WHERE branch_id = ? AND date = ? AND status = 'confirmed'
                     AND reference_number != ?""",
                (reservation["branch_id"], new_date, reference_number),
            )
            slot_end = new_time_min + 90
            overlapping = 0
            for r in cursor.fetchall():
                r_min = time_to_minutes(r["time"])
                r_end = r_min + 90
                if r_min < slot_end and r_end > new_time_min:
                    overlapping += r["party_size"]

            if branch_row["capacity"] - overlapping < new_party:
                conn.rollback()
                conn.close()
                return {
                    "success": False,
                    "error": (
                        f"{new_time} on {new_date} doesn't have room for a party of {new_party}. "
                        f"({overlapping}/{branch_row['capacity']} seats already booked.)"
                    ),
                }

        # ── UPDATE inside the same transaction ─────────────────────────────────
        cursor.execute(
            """UPDATE reservations
               SET date = ?, time = ?, party_size = ?, special_requests = ?
               WHERE reference_number = ?""",
            (new_date, new_time, new_party, new_requests, reference_number),
        )
        conn.commit()

    except sqlite3.OperationalError as e:
        conn.rollback()
        conn.close()
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            return {
                "success": False,
                "error": "Another booking change is in progress for this slot. Please retry in a moment.",
            }
        raise

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
    """
    Cancel a reservation by reference number.

    Refuses to cancel a booking whose date is already in the past — that's a
    contradictory operation and would confuse downstream dropoff/CRM pipelines.
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM reservations WHERE reference_number = ?",
        (reference_number,),
    )
    reservation = cursor.fetchone()

    if not reservation:
        conn.close()
        return {"success": False, "error": f"Reservation {reference_number} not found."}

    if reservation["status"] == "cancelled":
        conn.close()
        return {"success": False, "error": "Reservation is already cancelled."}

    if _is_past(reservation["date"]):
        conn.close()
        return {
            "success": False,
            "error": (
                f"Reservation {reference_number} was for {reservation['date']}, "
                "which is already in the past. There's nothing to cancel."
            ),
        }

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
