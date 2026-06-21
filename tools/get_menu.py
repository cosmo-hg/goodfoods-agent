from config import get_db


def get_branch_menu(branch_id, category=None, dietary_filter=None, db_path=None):
    """Return menu items for a GoodFoods location with optional filters."""
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name, cuisine, address, phone FROM branches WHERE id = ?", (branch_id,))
    branch = cursor.fetchone()
    if not branch:
        conn.close()
        return {"error": f"Branch {branch_id} not found"}

    query = "SELECT * FROM menu_items WHERE branch_id = ? AND is_available = 1"
    params = [branch_id]

    if category:
        query += " AND category = ?"
        params.append(category)

    dietary_map = {
        "vegetarian":  "is_vegetarian",
        "vegan":       "is_vegan",
        "gluten_free": "is_gluten_free",
        "halal":       "is_halal",
        "jain":        "is_jain",
    }
    if dietary_filter and dietary_filter.lower() in dietary_map:
        query += f" AND {dietary_map[dietary_filter.lower()]} = 1"

    query += " ORDER BY category, is_popular DESC, name"
    cursor.execute(query, params)
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()

    grouped: dict = {}
    for item in items:
        cat = item["category"] or "Other"
        grouped.setdefault(cat, []).append({
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "price": item["price"],
            "popular": bool(item["is_popular"]),
            "vegetarian": bool(item["is_vegetarian"]),
            "vegan": bool(item["is_vegan"]),
            "gluten_free": bool(item["is_gluten_free"]),
            "halal": bool(item["is_halal"]),
            "calories": item["calories"],
        })

    return {
        "branch_id": branch_id,
        "branch_name": branch["name"],
        "cuisine": branch["cuisine"],
        "address": branch["address"],
        "menu": grouped,
        "total_items": len(items),
    }
