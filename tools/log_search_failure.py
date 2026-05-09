from config import get_db


def log_search_failure(
    query,
    reason,
    party_size=None,
    date=None,
    time=None,
    cuisine=None,
    neighborhood=None,
    db_path=None,
):
    conn = get_db(db_path)
    conn.execute(
        """
        INSERT INTO search_failures
            (query, party_size, date, time, cuisine, neighborhood, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (query, party_size, date, time, cuisine, neighborhood, reason),
    )
    conn.commit()
    conn.close()
    return {"logged": True, "query": query, "reason": reason}
