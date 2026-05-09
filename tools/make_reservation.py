import re
import random
import sqlite3
import string
import datetime as _dt
from config import get_db
from tools.check_availability import check_availability
from intelligence.occasion_crm import schedule_occasion_followup
from intelligence.demand_signal import check_and_alert_procurement

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
    """Require at least 7 digits — catches 'abc', '555', and similar non-phones."""
    digits = _PHONE_DIGITS_RE.findall(str(phone))
    return len(digits) >= 7


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
        return {"success": False, "error": f"'{user_phone}' does not look like a valid phone number. Please provide at least 7 digits."}
    if phone_str.lower() in _FAKE_PHONES:
        return {"success": False, "error": f"'{user_phone}' looks like a placeholder. Please collect the guest's real phone number."}

    # ── Availability check ─────────────────────────────────────────────────────
    available = check_availability(branch_id, date, party_size, db_path)
    if isinstance(available, dict) and "error" in available:
        return {"success": False, "error": available["error"]}
    if time not in available:
        return {
            "success": False,
            "error": (
                f"Time slot {time} is not available for a party of {party_size} "
                f"at branch {branch_id} on {date}."
            ),
        }

    # ── Atomic INSERT with collision-safe retry ────────────────────────────────
    # Using INSERT + IntegrityError catch eliminates the SELECT-then-INSERT race
    # window: if two concurrent sessions generate the same reference, exactly one
    # INSERT succeeds and the other retries with a fresh candidate.
    conn = get_db(db_path)
    cursor = conn.cursor()

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
            # Only retry on reference_number UNIQUE violations; re-raise everything else.
            if "reference_number" in str(exc).lower() or "unique" in str(exc).lower():
                continue
            conn.close()
            raise

    if not reference:
        conn.close()
        return {"success": False, "error": "Could not generate a unique reference. Please try again."}

    reservation_id = cursor.lastrowid

    # Upsert user record
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

    conn.commit()

    # Fetch branch name for downstream modules
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

    # Trigger demand signal check (procurement alert)
    check_and_alert_procurement(
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
        "message": (
            f"Reservation confirmed! Your reference number is {reference}. "
            f"We look forward to welcoming you to {branch_name} on {date} at {time}."
        ),
    }
