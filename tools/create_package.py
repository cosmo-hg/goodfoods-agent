import json
from config import get_db

OCCASION_PACKAGES = {
    "birthday": {
        "includes": ["Birthday cake with candles", "Table balloon arrangement", "Happy Birthday sash", "Complimentary photo printout"],
        "default_extras": "A surprise dessert is included on us!",
    },
    "anniversary": {
        "includes": ["Rose petal table setting", "Champagne on arrival", "Personalised anniversary card", "Couples dessert platter"],
        "default_extras": "We will dim the lights and arrange soft background music.",
    },
    "proposal": {
        "includes": ["Rose petal arrangement", "Champagne", "Private corner table reserved", "Photographer coordination available"],
        "default_extras": "Our team will keep it completely secret until the moment.",
    },
    "business dinner": {
        "includes": ["Private dining area (subject to availability)", "Branded menus", "Pre-set amuse-bouche", "Dedicated server"],
        "default_extras": "AV equipment available on request.",
    },
    "graduation": {
        "includes": ["Congratulations cake", "Festive table decor", "Complimentary group photo"],
        "default_extras": "A congratulatory message from the GoodFoods team.",
    },
}

DEFAULT_PACKAGE = {
    "includes": ["Personalised welcome note", "Complimentary petit fours", "Dedicated server"],
    "default_extras": "Our team will make this occasion extra special.",
}


def _resolve_occasion_key(occasion: str) -> str:
    """
    Fuzzy-match `occasion` against known package keys so that variants like
    'birthday dinner', 'wedding anniversary', or 'business lunch' resolve
    to the correct package instead of falling back to DEFAULT_PACKAGE.
    """
    occ = occasion.lower().strip()
    # Exact hit first
    if occ in OCCASION_PACKAGES:
        return occ
    # Substring: known key inside the user string ("birthday dinner" → "birthday")
    for key in OCCASION_PACKAGES:
        if key in occ:
            return key
    # Reverse substring: user string inside a known key ("biz" won't hit, but "proposal" would)
    for key in OCCASION_PACKAGES:
        if occ in key:
            return key
    return occ  # no match → falls through to DEFAULT_PACKAGE


def create_experience_package(
    reference_number, occasion, preferences=None, budget=None, db_path=None
):
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, branch_id, user_name FROM reservations WHERE reference_number = ?",
        (reference_number,),
    )
    reservation = cursor.fetchone()

    if not reservation:
        conn.close()
        return {"success": False, "error": f"Reservation {reference_number} not found"}

    resolved_key = _resolve_occasion_key(occasion)
    package = OCCASION_PACKAGES.get(resolved_key, DEFAULT_PACKAGE)

    guest_prefs = preferences or "None specified"
    pkg_budget  = budget or "Standard"

    # Persist the package so it can be retrieved in future sessions.
    cursor.execute(
        """
        INSERT INTO packages
            (reference_number, occasion, includes, extras, guest_preferences, budget)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            reference_number,
            occasion,
            json.dumps(package["includes"]),
            package["default_extras"],
            guest_prefs,
            pkg_budget,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "reference_number": reference_number,
        "occasion": occasion,
        "package": {
            "includes": package["includes"],
            "extras": package["default_extras"],
            "guest_preferences": guest_prefs,
            "budget": pkg_budget,
        },
        "message": (
            f"Experience package for '{occasion}' has been created for {reference_number}. "
            "Our branch team will be briefed 24 hours before the reservation."
        ),
    }
