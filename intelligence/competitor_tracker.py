import re
from config import get_db

# Bangalore continental-dining competitors that guests typically reference.
# This list is used (a) for ambient passive scanning of guest messages, and
# (b) by the log_competitor_mention tool when the LLM explicitly flags one.
COMPETITORS = [
    # Italian
    "toscano", "fenny's", "fennys", "little italy", "pizza express",
    "california pizza kitchen", "cpk", "pizza hut", "domino's", "dominos",
    # Continental / European cafes
    "smoke house deli", "smoke house", "shd",
    "cafe noir", "the leela cafe", "olive beach", "olive bistro", "olive",
    "sly granny", "toast & tonic", "toast and tonic",
    "ttk", "the fatty bao", "monkey bar", "monkey",
    # American / Burgers / BBQ
    "hard rock cafe", "hard rock", "tgif", "tgi fridays", "tgi friday",
    "the smoke co", "smoke co", "burgs by burgundy", "burgundy",
    "plan b", "smally's resto cafe",
    "shake shack", "five guys",
    # Steakhouse
    "the grand smoke", "outback steakhouse", "outback",
    # Mexican
    "sancho's", "sanchos", "mamagoto",
    # Mediterranean / Lebanese
    "byg brewski", "big brewsky", "byg ventures",
    "the levantine", "open box",
    # Generic / aggregators
    "zomato", "swiggy dineout", "dineout", "eazydiner",
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
