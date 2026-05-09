import math
from config import get_db


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


def score_branch(branch, params):
    score = 0.0

    if params.get("cuisine") and branch["cuisine"]:
        b_c = branch["cuisine"].lower()
        p_c = params["cuisine"].lower()
        if b_c == p_c or p_c in b_c or b_c in p_c:
            score += 40

    party_size = params.get("party_size", 1)
    if branch["capacity"] and branch["capacity"] >= party_size:
        score += 20

    if branch["rating"]:
        score += max(0, min(10, (branch["rating"] - 3.8) / 1.0 * 10))

    if params.get("latitude") and params.get("longitude") and branch["latitude"] and branch["longitude"]:
        dist_km = haversine(params["latitude"], params["longitude"], branch["latitude"], branch["longitude"])
        score += max(0, 20 * (1 - dist_km / 10.0))

    if params.get("location_hint"):
        hint = params["location_hint"].lower()
        if hint in (branch["neighborhood"] or "").lower() or hint in (branch["name"] or "").lower():
            score += 25

    for flag in ["vegetarian", "vegan", "gluten_free", "halal", "kosher"]:
        if params.get(f"dietary_{flag}") and branch[f"dietary_{flag}"]:
            score += 15

    if params.get("price_range") and branch["price_range"]:
        if int(params["price_range"]) == int(branch["price_range"]):
            score += 10

    return score


def search_branches(params, db_path=None):
    """Search active GoodFoods locations and return top 3 with scores, distance, and menu highlights."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM branches WHERE is_active = 1")
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return []

    user_lat = params.get("latitude")
    user_lon = params.get("longitude")

    scored = []
    for r in rows:
        b = dict(r)
        s = score_branch(b, params)
        if user_lat and user_lon and b["latitude"] and b["longitude"]:
            b["distance_km"] = round(haversine(user_lat, user_lon, b["latitude"], b["longitude"]), 2)
        else:
            b["distance_km"] = None
        scored.append((s, b))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for s, branch in scored[:3]:
        branch["match_score"] = round(s, 1)
        # Attach top 3 popular menu items — prioritise Mains > Starters > Desserts/Drinks
        # so signature dishes (not puddings/teas) are shown in recommendations.
        cursor.execute(
            """SELECT name, price, category FROM menu_items
               WHERE branch_id = ? AND is_available = 1
               ORDER BY is_popular DESC,
                        CASE category
                            WHEN 'Mains'    THEN 1
                            WHEN 'Starters' THEN 2
                            WHEN 'Desserts' THEN 3
                            WHEN 'Drinks'   THEN 4
                            ELSE 5
                        END,
                        price DESC
               LIMIT 3""",
            (branch["id"],),
        )
        branch["menu_highlights"] = [dict(m) for m in cursor.fetchall()]
        results.append(branch)

    conn.close()
    return results
