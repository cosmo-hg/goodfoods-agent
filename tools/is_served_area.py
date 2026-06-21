"""
is_served_area — sanity-check a location string before any branch search.

The LLM should call this whenever a guest mentions a place ("Whitefield",
"Pune", "Brooklyn", "Koramangala 5th Block"). The tool resolves aliases,
confirms the city, and either returns a canonical neighbourhood or tells the
LLM honestly that we don't serve that area.

This is the layer that stops the "best pizza in Brooklyn" failure mode:
without it, the search tool fuzzy-matches and returns plausibly-wrong results.
"""
from __future__ import annotations

from config import (
    NEIGHBORHOOD_COORDS,
    NEIGHBORHOOD_ALIASES,
    SERVED_CITY,
    SERVED_CITY_ALIASES,
)

# Pre-build a lowercase lookup of canonical neighbourhood names for fast contains-checks.
_CANONICAL = {n.lower(): n for n in NEIGHBORHOOD_COORDS.keys()}


def is_served_area(location: str | None = None) -> dict:
    """
    Resolve a free-form location string against GoodFoods' served Bangalore areas.

    Returns:
      {
        "served":                bool,           # True if we can serve this location
        "matched_neighborhood":  str | None,     # canonical name if matched
        "city":                  "Bangalore",
        "reason":                str,            # human-readable explanation
        "alternative_suggestion":str | None,     # suggestion when not served
      }
    """
    if not location or not str(location).strip():
        return {
            "served": True,   # no location specified → no constraint
            "matched_neighborhood": None,
            "city": SERVED_CITY,
            "reason": "No specific area provided — search will span all Bangalore branches.",
            "alternative_suggestion": None,
        }

    raw = str(location).strip()
    low = raw.lower()

    # 1. Direct canonical match
    if low in _CANONICAL:
        return _ok(_CANONICAL[low], "Served neighbourhood.")

    # 2. Alias match (e.g. "Koramangala 5th Block" → "Koramangala")
    if low in NEIGHBORHOOD_ALIASES:
        canonical = NEIGHBORHOOD_ALIASES[low]
        return _ok(canonical, f"Resolved '{raw}' to our {canonical} area.")

    # 3. Substring match against canonical names (handles "in koramangala please")
    for canon_low, canon_name in _CANONICAL.items():
        if canon_low in low or low in canon_low:
            return _ok(canon_name, f"Interpreted '{raw}' as {canon_name}.")

    # 4. Substring against aliases
    for alias_low, canonical in NEIGHBORHOOD_ALIASES.items():
        if alias_low in low:
            return _ok(canonical, f"Interpreted '{raw}' as our {canonical} area.")

    # 5. City-level check — Bangalore-only chain
    if any(c in low for c in SERVED_CITY_ALIASES):
        # User mentioned Bangalore but not a known neighbourhood.
        return {
            "served": False,
            "matched_neighborhood": None,
            "city": SERVED_CITY,
            "reason": (
                f"'{raw}' isn't one of our {len(NEIGHBORHOOD_COORDS)} Bangalore neighbourhoods. "
                f"Ask the guest to name a known area, or offer to show our nearest branches."
            ),
            "alternative_suggestion": ", ".join(list(_CANONICAL.values())[:6]) + " …",
        }

    # 6. Off-city — Pune, Mumbai, Delhi, Brooklyn, etc.
    return {
        "served": False,
        "matched_neighborhood": None,
        "city": SERVED_CITY,
        "reason": (
            f"GoodFoods is a Bangalore-only chain. We don't operate in '{raw}'. "
            f"Tell the guest honestly — never invent a branch."
        ),
        "alternative_suggestion": None,
    }


def _ok(canonical: str, reason: str) -> dict:
    return {
        "served": True,
        "matched_neighborhood": canonical,
        "city": SERVED_CITY,
        "reason": reason,
        "alternative_suggestion": None,
    }
