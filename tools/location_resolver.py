"""
location_resolver — turn raw GPS coords into a structured location decision.

Given a latitude/longitude (from the browser's Geolocation API), this resolves:
  1. whether the user is inside our Bangalore service area
  2. which of our 25 served neighbourhoods they're nearest to
  3. how far they are from the city centre (so we can phrase the UI honestly)
  4. (NEW) the actual city/country name via reverse geocoding so the UI can
     say "You're in Mumbai" instead of "You're 840 km from Bangalore" —
     much more debuggable and trustworthy.

The output drives three things in the app:
  • whether to pass lat/lon to search_branches at all
  • how to label distances in the UI ("3.2 km" vs "~3.2 km")
  • what to tell the LLM in user_context

Kept in its own module so it's easy to unit test without touching Streamlit.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from config import NEIGHBORHOOD_COORDS

# Bangalore centroid — close to MG Road / Vidhana Soudha.
# Used only to decide "are you in/near the city" vs "are you in another city".
_BLR_CENTROID_LAT = 12.9716
_BLR_CENTROID_LON = 77.6094

# Anything beyond this radius from the city centre is treated as "outside Bangalore"
# for the purpose of distance-based ranking. 30 km comfortably covers Devanahalli
# (airport area), Electronic City, and the outer ring of suburbs.
_OUT_OF_CITY_KM = 30.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


def nearest_neighborhood(lat: float, lon: float) -> tuple[str, float]:
    """
    Return (canonical_name, distance_km) of the closest served neighbourhood
    to the given coordinates. Only 25 candidates — O(n) scan is fine.
    """
    best_name = None
    best_dist = float("inf")
    for name, (nlat, nlon) in NEIGHBORHOOD_COORDS.items():
        d = _haversine(lat, lon, nlat, nlon)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name, best_dist


# ── Reverse geocoding (free, no API key) ───────────────────────────────────────
#
# We use OpenStreetMap's Nominatim. It's totally free, no signup. Their fair-use
# policy: max 1 req/sec, set a meaningful User-Agent, cache results.
#
# We satisfy all three: an in-memory cache keyed by rounded lat/lon (~1km
# granularity), a global lock-protected sleep to enforce the 1 req/sec ceiling,
# and a descriptive User-Agent. Fall back silently on any error — the resolver
# still works without a city name.

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {
    "User-Agent": "GoodFoods-Concierge/1.0 (contact@goodfoods.local)",
    "Accept-Language": "en",
}
_GEOCODE_CACHE: dict[tuple, dict] = {}
_GEOCODE_LOCK = threading.Lock()
_LAST_GEOCODE_TS = 0.0
_MIN_INTERVAL_S = 1.05   # >1s between calls, with margin


def _cache_key(lat: float, lon: float) -> tuple:
    """Round to 2 decimal places (~1 km) so nearby coords share a cache entry."""
    return (round(float(lat), 2), round(float(lon), 2))


def reverse_geocode_city(lat: float, lon: float, timeout: float = 8.0) -> dict:
    """
    Resolve lat/lon to a human-readable place. Free; uses Nominatim.

    Returns:
      {
        "city":      str | None,   # most specific locality found
        "state":     str | None,   # admin level above city
        "country":   str | None,   # country name
        "display":   str | None,   # "Mumbai, India" / "Singapore" / None
        "ok":        bool,         # True iff Nominatim returned a usable result
      }

    Never raises. On network failure / timeout / parse error, returns a dict
    with ok=False and all fields None — caller falls back gracefully.
    """
    blank = {"city": None, "state": None, "country": None, "display": None, "ok": False}
    if lat is None or lon is None:
        return blank

    key = _cache_key(lat, lon)
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    global _LAST_GEOCODE_TS
    with _GEOCODE_LOCK:
        # Enforce 1 req/sec fair-use ceiling
        delta = time.time() - _LAST_GEOCODE_TS
        if delta < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - delta)
        _LAST_GEOCODE_TS = time.time()

    params = {
        "lat":             f"{lat}",
        "lon":             f"{lon}",
        "format":          "json",
        "zoom":            "10",        # city-level
        "addressdetails":  "1",
    }
    url = f"{_NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_NOMINATIM_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, TimeoutError, OSError):
        # Cache the failure briefly to avoid hammering Nominatim
        _GEOCODE_CACHE[key] = blank
        return blank

    addr = data.get("address", {}) or {}

    # Walk down specificity — prefer "city" but fall back to smaller admin levels
    city = (addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or addr.get("suburb")
            or addr.get("county") or addr.get("state_district"))
    state = addr.get("state")
    country = addr.get("country")

    display_parts = [p for p in (city, country) if p]
    display = ", ".join(display_parts) if display_parts else None

    result = {
        "city":    city,
        "state":   state,
        "country": country,
        "display": display,
        "ok":      bool(city or state or country),
    }
    _GEOCODE_CACHE[key] = result
    return result


def resolve_user_location(lat: float, lon: float, *, with_geocode: bool = True) -> dict:
    """
    Classify a real GPS reading.

    Returns a dict:
      {
        "in_bangalore":              bool,     # inside our service area?
        "city_centre_distance_km":   float,    # honest "how far from BLR" number
        "nearest_neighborhood":      str,      # closest of our 25 areas
        "nearest_neighborhood_km":   float,    # how far from that area's centre
        "geo":                       dict,     # reverse-geocoded city/country (see above)
        "lat":                       float,
        "lon":                       float,
      }

    `with_geocode=False` skips the Nominatim call — useful in tests where we
    don't want network access.
    """
    centre_dist = _haversine(lat, lon, _BLR_CENTROID_LAT, _BLR_CENTROID_LON)
    name, nd = nearest_neighborhood(lat, lon)
    geo = reverse_geocode_city(lat, lon) if with_geocode else \
          {"city": None, "state": None, "country": None, "display": None, "ok": False}
    return {
        "in_bangalore":            centre_dist <= _OUT_OF_CITY_KM,
        "city_centre_distance_km": round(centre_dist, 1),
        "nearest_neighborhood":    name,
        "nearest_neighborhood_km": round(nd, 2),
        "geo":                     geo,
        "lat":                     lat,
        "lon":                     lon,
    }
