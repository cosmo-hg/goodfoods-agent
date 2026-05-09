import re
from config import get_db

COMPETITORS = [
    "olive garden",
    "applebee's",
    "applebees",
    "chili's",
    "chilis",
    "tgi fridays",
    "tgi friday",
    "outback steakhouse",
    "outback",
    "red lobster",
    "denny's",
    "dennys",
    "ihop",
    "cheesecake factory",
    "buffalo wild wings",
    "bdubs",
    "panera bread",
    "panera",
    "shake shack",
    "five guys",
    "chipotle",
    "sweetgreen",
    "nandos",
    "nando's",
    "wagamama",
    "pizza express",
    "harvester",
]


def check_competitor_mentions(text, session_id=None, db_path=None):
    """Scan text for competitor brand mentions and log them."""
    if not text:
        return []

    lower_text = text.lower()
    found = []

    for competitor in COMPETITORS:
        pattern = r"\b" + re.escape(competitor) + r"\b"
        if re.search(pattern, lower_text):
            found.append(competitor)

    if found:
        conn = get_db(db_path)
        for competitor in found:
            conn.execute(
                """
                INSERT INTO competitor_mentions (competitor_name, mention_context, session_id)
                VALUES (?, ?, ?)
                """,
                (competitor, text[:500], session_id),
            )
        conn.commit()
        conn.close()

    return found
