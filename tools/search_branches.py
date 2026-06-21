"""
Branch search — filters first, ranking second.

Earlier versions of this tool treated cuisine and location as score *bonuses*,
which meant a search for "Italian in Brooklyn" would happily return French
branches in Midtown because nothing was actually filtered. That's fixed: hard
filters apply at the SQL layer and only matched branches are scored.

Ranking signal:
  popularity_score   (real, persistent — the long-tail "reputation")
  + distance penalty (only if the user gave real coordinates)
  + dish-level boost (if `dish` was passed and the branch's menu matches)
  + dietary match    (small)
  + price match      (small)

Confidence is reported per result so the LLM can be honest with the guest:
  "high"   — strong cuisine + (location OR dish) + dietary match
  "medium" — matched cuisine OR location OR dish, but not all
  "low"    — fuzzy fallback only
"""
from __future__ import annotations

import math
from config import get_db


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


# How close a branch must be (km) to count as a strong "near user" signal.
_NEAR_KM = 5.0


def _normalise_cuisine(raw: str) -> str | None:
    """
    Map user-typed cuisine words to our canonical 8 concepts (Indian-majority).
    Returns None if the word doesn't map — caller treats that as no cuisine filter.

    The mapping below covers the synonyms Bangalore guests actually type:
      • Cuisine names      ("biryani", "south indian", "mughlai")
      • Iconic dish names  ("dosa" → South Indian, "manchurian" → Indo-Chinese)
      • Regional pointers  ("punjabi" → North Indian, "mangalorean" → Coastal)
    """
    if not raw:
        return None
    r = raw.strip().lower()
    direct = {
        # North Indian
        "north indian":  "North Indian",
        "punjabi":       "North Indian",
        "north":         "North Indian",
        "tandoor":       "North Indian",
        "tandoori":      "North Indian",
        "butter chicken":"North Indian",
        "paneer":        "North Indian",
        "dal":           "North Indian",
        # South Indian
        "south indian":  "South Indian",
        "south":         "South Indian",
        "dosa":          "South Indian",
        "idli":          "South Indian",
        "vada":          "South Indian",
        "tiffin":        "South Indian",
        "udupi":         "South Indian",
        "andhra":        "South Indian",
        "chettinad":     "South Indian",
        "tamil":         "South Indian",
        "kerala":        "South Indian",
        # Biryani
        "biryani":       "Biryani",
        "biriyani":      "Biryani",
        "hyderabadi":    "Biryani",
        "donne":         "Biryani",
        "lucknowi biryani":"Biryani",
        # Indo-Chinese
        "indo-chinese":  "Indo-Chinese",
        "indo chinese":  "Indo-Chinese",
        "chinese":       "Indo-Chinese",
        "manchurian":    "Indo-Chinese",
        "schezwan":      "Indo-Chinese",
        "noodles":       "Indo-Chinese",
        "fried rice":    "Indo-Chinese",
        "hakka":         "Indo-Chinese",
        "chilli chicken":"Indo-Chinese",
        # Mughlai
        "mughlai":       "Mughlai",
        "moghlai":       "Mughlai",
        "awadhi":        "Mughlai",
        "lucknowi":      "Mughlai",
        "kebab":         "Mughlai",
        "kebabs":        "Mughlai",
        "galouti":       "Mughlai",
        "nihari":        "Mughlai",
        # Coastal
        "coastal":       "Coastal",
        "mangalorean":   "Coastal",
        "mangalore":     "Coastal",
        "udupi mangalore":"Coastal",
        "karavalli":     "Coastal",
        "ghee roast":    "Coastal",
        "neer dosa":     "Coastal",
        # Italian
        "italian":       "Italian",
        "pizza":         "Italian",
        "pasta":         "Italian",
        "risotto":       "Italian",
        # Continental
        "continental":   "Continental",
        "european":      "Continental",
        "cafe":          "Continental",
        "café":          "Continental",
        "burger":        "Continental",
        "burgers":       "Continental",
        "american":      "Continental",
        "brunch":        "Continental",
        "sandwich":      "Continental",
    }
    # "indian" alone is ambiguous — leave it None so the search runs across all
    # Indian cuisines ranked by popularity rather than picking one arbitrarily.
    if r == "indian":
        return None
    return direct.get(r)


def _normalise_dish(raw: str) -> str | None:
    """Lowercase, strip; returned to be matched against the dish_tags column."""
    if not raw:
        return None
    return raw.strip().lower() or None


def search_branches(params, db_path=None):
    """
    Filtered, ranked branch search.

    params (all optional, free-form from the LLM):
      cuisine             — one of our 8 concepts (or a synonym)
      dish                — free-text dish name ("pizza", "burger", "paella")
      location_hint       — neighbourhood string (must match a served area)
      latitude, longitude — real or area-centroid; used for distance ranking only
      party_size          — for capacity filter (drops branches too small)
      dietary_vegetarian / dietary_vegan / dietary_gluten_free / dietary_halal / dietary_jain
      price_range         — 1..4

    Returns: list of branch dicts (top-3) OR an empty list.
    Each result includes:  distance_km (or None), match_score, confidence,
                           match_reasons (list of strings),
                           menu_highlights (top 3 dishes; if dish was given,
                           the matching dishes appear first).
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    cuisine_filter = _normalise_cuisine(params.get("cuisine") or "")
    dish_filter    = _normalise_dish(params.get("dish") or "")
    location_hint  = (params.get("location_hint") or "").strip()
    party_size     = int(params.get("party_size") or 1)
    user_lat       = params.get("latitude")
    user_lon       = params.get("longitude")
    price_filter   = params.get("price_range")

    # ── Build SQL WHERE clauses ────────────────────────────────────────────────
    # Hard filters: cuisine, location, capacity.  Soft filters (dietary, price)
    # are applied as ranking signals so we don't over-prune.
    where = ["b.is_active = 1", "b.capacity >= ?"]
    args: list = [party_size]

    if cuisine_filter:
        where.append("b.cuisine = ?")
        args.append(cuisine_filter)

    if location_hint:
        # Exact neighbourhood match (case-insensitive). is_served_area should
        # have run already to resolve aliases like "Koramangala 5th Block"
        # to "Koramangala", but we accept either form here defensively.
        where.append("LOWER(b.neighborhood) = ?")
        args.append(location_hint.lower())

    sql = f"SELECT * FROM branches b WHERE {' AND '.join(where)}"
    rows = cursor.execute(sql, args).fetchall()

    # ── Dish filter: requires a JOIN, applied as a second pass ─────────────────
    # If a dish was specified, restrict to branches whose menu has a matching
    # dish_tags entry. We score the match strength too so "pizza" → branches
    # with actual pizzas rank above branches that merely tagged "italian".
    dish_match_by_branch: dict = {}   # branch_id → [matching menu rows]
    if dish_filter:
        dish_rows = cursor.execute(
            """SELECT mi.branch_id, mi.id, mi.name, mi.price, mi.category,
                      mi.is_popular, mi.is_vegetarian, mi.is_vegan,
                      mi.dish_tags
               FROM menu_items mi
               WHERE mi.is_available = 1
                 AND (LOWER(mi.dish_tags) LIKE ?
                      OR LOWER(mi.name)   LIKE ?)""",
            (f"%{dish_filter}%", f"%{dish_filter}%"),
        ).fetchall()
        for r in dish_rows:
            dish_match_by_branch.setdefault(r["branch_id"], []).append(dict(r))

        # Restrict to branches that actually have the dish on the menu.
        rows = [r for r in rows if r["id"] in dish_match_by_branch]

    if not rows:
        conn.close()
        return []

    # ── Score & rank ──────────────────────────────────────────────────────────
    scored = []
    for r in rows:
        b = dict(r)
        score = 0.0
        reasons: list = []

        # 1. Popularity is the dominant signal (0..50 points).
        pop = float(b.get("popularity_score") or 50.0)
        score += pop * 0.5
        if pop >= 85:
            reasons.append("flagship location")
        elif pop >= 65:
            reasons.append("popular branch")

        # 2. Distance: closer = better, only when real coords were passed.
        if user_lat is not None and user_lon is not None and b["latitude"] and b["longitude"]:
            dist_km = haversine(user_lat, user_lon, b["latitude"], b["longitude"])
            b["distance_km"] = round(dist_km, 2)
            # 0 km → +20 points, 10 km → 0 points, capped at 0
            score += max(0.0, 20.0 * (1.0 - dist_km / 10.0))
            if dist_km <= _NEAR_KM:
                reasons.append(f"only {dist_km:.1f} km away")
        else:
            b["distance_km"] = None

        # 3. Cuisine match was a hard filter — log it as a reason.
        if cuisine_filter:
            reasons.append(f"{cuisine_filter} kitchen")

        # 4. Dish match boost
        matched_dishes = dish_match_by_branch.get(b["id"], []) if dish_filter else []
        if matched_dishes:
            # Boost based on count: 1 match → +8, 3+ matches → +20
            boost = min(20.0, 8.0 + (len(matched_dishes) - 1) * 4.0)
            score += boost
            popular_match = any(d.get("is_popular") for d in matched_dishes)
            if popular_match:
                score += 5.0
                reasons.append(f"known for {dish_filter}")
            else:
                reasons.append(f"serves {dish_filter}")

        # 5. Dietary alignment — soft, additive
        diet_matches = 0
        for flag in ("vegetarian", "vegan", "gluten_free", "halal", "kosher"):
            if params.get(f"dietary_{flag}") and b.get(f"dietary_{flag}"):
                score += 4.0
                diet_matches += 1
        if params.get("dietary_jain") and b.get("dietary_vegan"):
            # Jain is approximated via the vegan flag (no onion/garlic is stricter,
            # but vegan menus are the closest signal we have).
            score += 3.0
            diet_matches += 1

        # 6. Price match
        if price_filter and b.get("price_range") and int(price_filter) == int(b["price_range"]):
            score += 3.0

        # ── Confidence ─────────────────────────────────────────────────────────
        # High:    cuisine + (location OR dish) match, OR dish match with popular dish
        # Medium:  cuisine match only, or location match only, or dish-only
        # Low:     nothing was specified (browse fallback)
        if cuisine_filter and (location_hint or matched_dishes):
            confidence = "high"
        elif cuisine_filter and any(d.get("is_popular") for d in matched_dishes):
            confidence = "high"
        elif cuisine_filter or location_hint or matched_dishes:
            confidence = "medium"
        else:
            confidence = "low"
        b["confidence"]    = confidence
        b["match_reasons"] = reasons
        b["match_score"]   = round(score, 1)

        # ── Menu highlights ────────────────────────────────────────────────────
        # If a dish was searched, surface the matching dishes first.
        if matched_dishes:
            # Sort: popular first, then by category Mains > Starters > others.
            cat_rank = {"Mains": 1, "Tapas": 1, "Starters": 2, "Breakfast": 2, "Sides": 3, "Desserts": 4, "Drinks": 5}
            matched_dishes.sort(key=lambda d: (not d["is_popular"], cat_rank.get(d["category"], 9), d["name"]))
            b["menu_highlights"] = [
                {"name": d["name"], "price": d["price"], "category": d["category"]}
                for d in matched_dishes[:3]
            ]
        else:
            cursor.execute(
                """SELECT name, price, category FROM menu_items
                   WHERE branch_id = ? AND is_available = 1
                   ORDER BY is_popular DESC,
                            CASE category
                                WHEN 'Mains'      THEN 1
                                WHEN 'Tapas'      THEN 1
                                WHEN 'Starters'   THEN 2
                                WHEN 'Breakfast'  THEN 2
                                WHEN 'Sides'      THEN 3
                                WHEN 'Desserts'   THEN 4
                                WHEN 'Drinks'     THEN 5
                                ELSE 6
                            END,
                            price DESC
                   LIMIT 3""",
                (b["id"],),
            )
            b["menu_highlights"] = [dict(m) for m in cursor.fetchall()]

        scored.append((score, b))

    conn.close()

    # Sort by score desc, then popularity desc as tiebreak
    scored.sort(key=lambda x: (x[0], x[1].get("popularity_score") or 0), reverse=True)

    # Trim each result to ONLY the fields the LLM needs to compose a reply.
    # The full branch row has ~25 columns (description paragraph, address,
    # dietary_* flags, parking/valet/etc., raw lat/lon) that bloat the tool
    # result and burn Groq's 6 000 tokens/min budget. Side-effect mapping in
    # the agent loop only cares about a small subset — keep that consistent.
    SLIM_FIELDS = (
        "id", "branch_code", "name", "neighborhood", "cuisine",
        "rating", "review_count", "price_range", "capacity",
        "opening_time", "closing_time", "phone",
        "dietary_vegetarian", "dietary_vegan", "dietary_gluten_free",
        "dietary_halal", "dietary_jain",
        "distance_km", "confidence", "match_reasons", "menu_highlights",
        "popularity_score", "latitude", "longitude",
    )
    out = []
    for _, b in scored[:3]:
        out.append({k: b[k] for k in SLIM_FIELDS if k in b})
    return out
