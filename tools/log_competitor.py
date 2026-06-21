from __future__ import annotations

"""
log_competitor_mention — LLM-callable competitor capture.

When a guest references another restaurant ("we usually go to Toscano",
"as good as Olive?", "we love Smoke House Deli"), the agent calls this tool
so the mention becomes structured business data — feeding the Admin
analytics dashboard.

Why this exists as a tool (not just passive scanning):
  Passive scanning only catches names we listed. The LLM-callable tool also
  catches paraphrases ("the Italian place on Church Street") and intent
  ("I'm comparing you to a few others"), giving Operations richer signal.
"""
from config import get_db


def log_competitor_mention(
    competitor_name: str,
    context: str | None = None,
    session_id: str | None = None,
    db_path=None,
) -> dict:
    """
    Persist a competitor mention to the competitor_mentions table.

    Arguments:
      competitor_name — the brand or restaurant the guest referenced
      context         — the surrounding sentence/phrase (max 500 chars)
      session_id      — the conversation session, for grouping

    Returns: {"logged": bool, "competitor": str, "id": int|None}
    """
    if not competitor_name or not str(competitor_name).strip():
        return {"logged": False, "competitor": competitor_name, "id": None,
                "error": "competitor_name is required."}

    name = str(competitor_name).strip()[:100]
    ctx  = (str(context or "")[:500]) or None

    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO competitor_mentions
               (competitor_name, mention_context, session_id)
               VALUES (?, ?, ?)""",
            (name.lower(), ctx, session_id),
        )
        conn.commit()
        new_id = cursor.lastrowid
    finally:
        conn.close()

    return {
        "logged":     True,
        "competitor": name,
        "id":         new_id,
        "message":    f"Logged competitor mention: {name}",
    }
