import re
import random
import sqlite3
import string
import datetime as _dt
from config import get_db
from tools.check_availability import time_to_minutes
from intelligence.occasion_crm import schedule_occasion_followup
from intelligence.demand_signal import check_and_alert_procurement

# Indian phone format: optional +91, optional space/dash, then 10 digits.
# Accepts:  +91 98450 12345 / 91 9845012345 / 9845012345 / +91-98450-12345
_INDIAN_PHONE_RE = re.compile(
    r"^(?:\+?91[\s\-]?)?[6-9]\d{9}$"
)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE_DIGITS_RE = re.compile(r'\d')

# Names the LLM might invent when it doesn't actually have the guest's name
_FAKE_NAMES = {
    "guest", "unknown", "n/a", "na", "user", "customer",
    "name", "your name", "full name", "firstname lastname", "first last",
    "test", "test user", "anonymous", "placeholder", "sample",
}

# Email user-parts the LLM tends to fabricate
_FAKE_EMAIL_USERS = {"unknown", "guest", "placeholder", "noreply", "nobody", "noone"}

# Phone values the LLM or users submit that are clearly not real
_FAKE_PHONES = {"0000000", "1111111", "1234567", "7654321", "n/a", "na", "none", "tbd", "xxx"}


def _generate_reference():
    chars = string.ascii_uppercase + string.digits
    return "GF-" + "".join(random.choices(chars, k=6))


def _is_valid_phone(phone: str) -> bool:
    """
    Accept Indian phone formats. The chain is Bangalore-only, so loose
    "≥7 digits" rules let through obviously-invalid international numbers.
    Indian mobiles are 10 digits, starting 6-9, optionally prefixed +91.
    """
    s = str(phone).strip()
    # Normalise common separators (space, dash, dot) for the regex match
    normalised = re.sub(r"[\s\-\.\(\)]", "", s)
    return bool(_INDIAN_PHONE_RE.match(normalised))


def make_reservation(
    branch_id,
    user_name,
    user_email,
    user_phone,
    party_size,
    date,
    time,
    occasion=None,
    special_requests=None,
    corporate_account_id=None,
    db_path=None,
):
    # Coerce phone: 8B model sometimes passes an integer (e.g. 4397394703)
    if user_phone is not None:
        user_phone = str(user_phone).strip()

    # ── Date validation ────────────────────────────────────────────────────────
    try:
        reservation_date = _dt.date.fromisoformat(str(date))
        if reservation_date < _dt.date.today():
            return {"success": False, "error": "Cannot book a reservation for a past date. Please choose a future date."}
    except ValueError:
        return {"success": False, "error": f"Invalid date format '{date}'. Use YYYY-MM-DD (e.g. 2026-06-15)."}

    # ── Party size validation ──────────────────────────────────────────────────
    try:
        party_size = int(party_size)
    except (TypeError, ValueError):
        return {"success": False, "error": "Party size must be a whole number."}
    if party_size < 1:
        return {"success": False, "error": "Party size must be at least 1."}
    if party_size > 500:
        return {"success": False, "error": "For events over 500 guests please contact our events team directly."}

    # ── Name validation ────────────────────────────────────────────────────────
    name_clean = str(user_name).strip().lower() if user_name else ""
    if not name_clean:
        return {"success": False, "error": "Guest name is required. Please ask the guest for their full name."}
    if name_clean in _FAKE_NAMES:
        return {"success": False, "error": f"'{user_name}' looks like a placeholder. Please collect the guest's real full name before booking."}

    # ── Email validation ───────────────────────────────────────────────────────
    if not user_email or not str(user_email).strip():
        return {"success": False, "error": "Guest email is required."}
    email_str = str(user_email).strip()
    if not _EMAIL_RE.match(email_str):
        return {"success": False, "error": f"'{user_email}' does not look like a valid email address."}
    _eparts = email_str.lower().split("@")
    if len(_eparts) == 2 and _eparts[0] in _FAKE_EMAIL_USERS:
        return {"success": False, "error": f"'{user_email}' looks like a placeholder email. Please use the guest's real address."}

    # ── Phone validation ───────────────────────────────────────────────────────
    if not user_phone or not str(user_phone).strip():
        return {"success": False, "error": "Guest phone number is required. Please ask the guest for their contact number."}
    phone_str = str(user_phone).strip()
    if not _is_valid_phone(phone_str):
        return {"success": False, "error": f"'{user_phone}' is not a valid Indian phone number. Please provide a 10-digit mobile (optionally prefixed with +91)."}
    if phone_str.lower() in _FAKE_PHONES:
        return {"success": False, "error": f"'{user_phone}' looks like a placeholder. Please collect the guest's real phone number."}

    # ── Atomic check + insert ──────────────────────────────────────────────────
    # Previously this function did `check_availability(...)` (its own connection)
    # then `INSERT` (separate connection). Two concurrent guests booking the
    # last seat both passed the check and both inserted — overbooking.
    #
    # Fix: a single connection running BEGIN IMMEDIATE wraps the capacity
    # query AND the INSERT. SQLite holds a RESERVED lock for the duration,
    # serializing concurrent writers. busy_timeout = 5s means racers wait
    # briefly instead of failing fast.
    conn = get_db(db_path)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        # 1) Re-read branch state inside the transaction
        cursor.execute(
            "SELECT capacity, opening_time, closing_time, is_active "
            "FROM branches WHERE id = ?",
            (branch_id,),
        )
        branch_row = cursor.fetchone()
        if not branch_row:
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Branch {branch_id} not found."}
        if not branch_row["is_active"]:
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Branch {branch_id} is temporarily closed and not accepting reservations."}

        capacity = branch_row["capacity"]
        opening  = branch_row["opening_time"] or "12:00"
        closing  = branch_row["closing_time"] or "23:00"

        # 2) Time validation — must be within branch hours
        try:
            slot_min = time_to_minutes(time)
        except (ValueError, AttributeError):
            conn.rollback()
            conn.close()
            return {"success": False, "error": f"Invalid time format '{time}'. Use HH:MM."}
        slot_end = slot_min + 90
        open_min = time_to_minutes(opening)
        close_min = time_to_minutes(closing)
        if slot_min < open_min or slot_min > close_min:
            conn.rollback()
            conn.close()
            return {
                "success": False,
                "error": f"Time {time} is outside branch hours ({opening}–{closing}).",
            }

        # 3) Compute overlapping confirmed reservations (90-minute occupancy window)
        cursor.execute(
            """SELECT time, party_size FROM reservations
               WHERE branch_id = ? AND date = ? AND status = 'confirmed'""",
            (branch_id, date),
        )
        overlapping = 0
        for r in cursor.fetchall():
            r_min = time_to_minutes(r["time"])
            r_end = r_min + 90
            if r_min < slot_end and r_end > slot_min:
                overlapping += r["party_size"]

        if capacity - overlapping < party_size:
            conn.rollback()
            conn.close()
            return {
                "success": False,
                "error": (
                    f"Time slot {time} is not available for a party of {party_size} "
                    f"at branch {branch_id} on {date}. "
                    f"({overlapping}/{capacity} seats already booked in that window.)"
                ),
            }

        # 4) Generate reference + INSERT (collision-safe retry inside same txn)
        reference = None
        for _ in range(10):
            candidate = _generate_reference()
            try:
                cursor.execute(
                    """
                    INSERT INTO reservations
                        (reference_number, branch_id, user_name, user_email, user_phone,
                         party_size, date, time, occasion, special_requests,
                         corporate_account_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
                    """,
                    (
                        candidate, branch_id, user_name, user_email, user_phone,
                        party_size, date, time, occasion, special_requests,
                        corporate_account_id,
                    ),
                )
                reference = candidate
                break
            except sqlite3.IntegrityError as exc:
                if "reference_number" in str(exc).lower() or "unique" in str(exc).lower():
                    continue
                conn.rollback()
                conn.close()
                raise

        if not reference:
            conn.rollback()
            conn.close()
            return {"success": False, "error": "Could not generate a unique reference. Please try again."}

        reservation_id = cursor.lastrowid

        # 5) Upsert user (same transaction)
        if user_email:
            cursor.execute(
                """
                INSERT INTO users (email, name, phone, total_reservations)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    phone = excluded.phone,
                    total_reservations = total_reservations + 1
                """,
                (user_email, user_name, user_phone),
            )

        # 6) Popularity nudge (same transaction)
        cursor.execute(
            """UPDATE branches
               SET popularity_score = MIN(100.0, popularity_score + 0.3)
               WHERE id = ?""",
            (branch_id,),
        )

        conn.commit()

    except sqlite3.OperationalError as e:
        # Lock timeout — another booking is in flight. Surface a retryable error.
        conn.rollback()
        conn.close()
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            return {
                "success": False,
                "error": "Another booking is in progress for this slot. Please retry in a moment.",
            }
        raise

    # ── Outside the transaction — read-only branch fetch for downstream ────────
    cursor.execute("SELECT * FROM branches WHERE id = ?", (branch_id,))
    branch = cursor.fetchone()
    conn.close()

    branch_name = branch["name"] if branch else f"Branch #{branch_id}"

    # Trigger occasion CRM follow-up scheduling
    if occasion:
        schedule_occasion_followup(
            reservation_id=reservation_id,
            occasion=occasion,
            user_email=user_email,
            user_name=user_name,
            branch_name=branch_name,
            date=date,
            db_path=db_path,
        )

    # Trigger demand signal check (procurement alert). The previous version
    # discarded this return value — we now persist it so the dashboard's
    # T-72h demand pipeline reflects every confirmed booking.
    procurement_alert = check_and_alert_procurement(
        branch_id=branch_id,
        branch_name=branch_name,
        date=date,
        db_path=db_path,
    )

    return {
        "success": True,
        "reference_number": reference,
        "reservation_id": reservation_id,
        "branch_name": branch_name,
        "date": date,
        "time": time,
        "party_size": party_size,
        "procurement_alert": procurement_alert,   # None unless threshold crossed
        "message": (
            f"Reservation confirmed! Your reference number is {reference}. "
            f"We look forward to welcoming you to {branch_name} on {date} at {time}."
        ),
    }
