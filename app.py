import os, uuid, re, math, json, random, sys
import datetime as _dt_d
from collections import defaultdict
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="GoodFoods Concierge",
    page_icon="•",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"Get Help": None, "Report a bug": None, "About": None},
)

# Admin tools (Dashboard, branch operations, agent traces) are hidden by default.
# Add ?admin=true to the URL to reveal them. Guest-facing URL stays clean.
_ADMIN_MODE = st.query_params.get("admin") == "true"

# ── Inject Streamlit Cloud secrets into os.environ BEFORE importing config ───
# config.py reads GROQ_API_KEY* from os.environ at module-load time, so this
# block must run first. st.secrets is available immediately after set_page_config.
try:
    for _k in ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3",
               "GROQ_API_KEY_4", "GROQ_API_KEY_5"]:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # local dev — keys come from .env file, st.secrets is not available

# ── Now safe to import config and agent modules ───────────────────────────────
from config import (init_db, get_db, NEIGHBORHOOD_COORDS,
                    save_message, update_session_guest, load_recent_messages,
                    save_session_state, load_session_state,
                    GROQ_API_KEYS)
from agent.loop import run_agent
from agent.slots import BookingSlots, format_for_llm as format_slots_for_llm
from tools.search_branches import haversine
from tools.check_availability import get_branch_slots, time_to_minutes as _t2m
from tools.location_resolver import resolve_user_location, nearest_neighborhood

# Browser-geolocation bridge (free, MIT). Falls back gracefully if not installed
# — local dev / non-cloud users still get the manual area dropdown.
try:
    from streamlit_geolocation import streamlit_geolocation
    _GEO_AVAILABLE = True
except ImportError:
    _GEO_AVAILABLE = False

# ── API key guard ─────────────────────────────────────────────────────────────
if not GROQ_API_KEYS:
    st.error(
        "**⚠️ GROQ_API_KEY is not configured.**\n\n"
        "Go to **Manage app → Settings → Secrets** and add:\n\n"
        "```toml\nGROQ_API_KEY = \"gsk_...\"\n```\n\n"
        "Then click **Save** — the app will restart automatically."
    )
    st.stop()

# ── Auto-seed on cold start (required for cloud deployments with ephemeral FS) ─
@st.cache_resource(show_spinner="Setting up GoodFoods database…")
def _bootstrap():
    """Initialise schema and seed data if the database is empty."""
    init_db()
    conn = get_db()
    branch_count = conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0]
    conn.close()
    if branch_count == 0:
        sys.path.insert(0, str(Path(__file__).parent))
        from scripts.seed_data import main as _seed
        _seed()

    # Warm the Nominatim TLS connection in the background so the first GPS
    # click feels instant. Cold-start SSL handshake can take 4-6 seconds
    # from India → EU; doing it once at boot moves that cost off the
    # critical path.
    import threading
    def _warm_geocode():
        try:
            from tools.location_resolver import reverse_geocode_city
            reverse_geocode_city(12.97, 77.59)   # Bangalore centroid (cache-warm only)
        except Exception:
            pass
    threading.Thread(target=_warm_geocode, daemon=True).start()
    return True

_bootstrap()

# ── Global CSS — monochrome, ChatGPT-style typography ─────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Reset & typography ─────────────────────────────────────────────────── */
:root {
    --bg:        #ffffff;
    --bg-soft:   #fafafa;
    --bg-muted:  #f5f5f4;
    --border:    #e7e5e4;
    --border-strong: #d6d3d1;
    --text:      #18181b;
    --text-2:    #44403c;
    --text-3:    #78716c;
    --text-4:    #a8a29e;
    --accent:    #18181b;
    --accent-2:  #292524;
    --good:      #15803d;
    --warn:      #b45309;
    --link:      #0f172a;
}

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
    color: var(--text);
}

/* Hide all Streamlit chrome — menu, footer, top decoration */
#MainMenu               { visibility: hidden; }
footer                  { visibility: hidden; }
[data-testid="stHeader"]     { display: none; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stToolbar"]    { display: none; }

/* Main container — centred reading column */
.main .block-container {
    padding: 2rem 1rem 6rem;
    max-width: 800px;
}

/* Sidebar — quiet, light grey */
[data-testid="stSidebar"] {
    background: var(--bg-soft);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * { color: var(--text-2); }
[data-testid="stSidebar"] .stSelectbox label {
    color: var(--text-3) !important;
    font-size: 11px !important;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stSidebar"] .stButton > button {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text-2);
    border-radius: 6px;
    font-size: 13px;
    font-weight: 400;
    text-align: left;
    padding: 7px 11px;
    width: 100%;
    margin: 2px 0;
    transition: background .12s, border-color .12s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--bg-muted);
    border-color: var(--border-strong);
}

/* Tabs (admin mode only) */
[data-testid="stTabs"] button {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-3);
    padding: 8px 14px;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--text);
    border-bottom-color: var(--text);
}

/* ── Chat header ────────────────────────────────────────────────────────── */
.gf-app-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.01em;
    margin-bottom: 2px;
}
.gf-app-sub {
    font-size: 12px;
    color: var(--text-3);
    margin-bottom: 28px;
    font-weight: 400;
}

/* ── Empty state ────────────────────────────────────────────────────────── */
.gf-empty {
    padding: 80px 0 40px;
    text-align: center;
}
.gf-empty-title {
    font-size: 26px;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
    margin-bottom: 6px;
}
.gf-empty-sub {
    font-size: 14px;
    color: var(--text-3);
    margin-bottom: 32px;
    line-height: 1.6;
}
.gf-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    max-width: 640px;
    margin: 0 auto;
}

/* ── Chat messages ──────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    padding: 14px 0 !important;
    border: none !important;
    border-radius: 0 !important;
    margin: 0 !important;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
    font-size: 15px;
    line-height: 1.65;
    color: var(--text);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
    margin: 0 0 10px;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code {
    background: var(--bg-muted);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    color: var(--text);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong {
    font-weight: 600;
    color: var(--text);
}

/* Chat input — pin to bottom feel, clean */
[data-testid="stChatInput"] {
    border: 1px solid var(--border-strong);
    border-radius: 12px;
    background: var(--bg);
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
[data-testid="stChatInput"] textarea {
    font-size: 15px !important;
    font-family: inherit !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--text-2);
    box-shadow: 0 0 0 3px rgba(24,24,27,0.08);
}

/* ── Branch recommendation card ─────────────────────────────────────────── */
.gf-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
    margin: 10px 0;
    transition: border-color .15s;
}
.gf-card:hover { border-color: var(--border-strong); }

.gf-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 6px;
}
.gf-card-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.35;
}
.gf-card-sub {
    font-size: 12px;
    color: var(--text-3);
    margin-top: 2px;
}
.gf-conf {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 3px 8px;
    border-radius: 4px;
    white-space: nowrap;
}
.gf-conf-high   { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.gf-conf-medium { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.gf-conf-low    { background: var(--bg-muted); color: var(--text-3); border: 1px solid var(--border); }

.gf-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 12px;
    color: var(--text-2);
    margin: 8px 0;
}
.gf-meta-dist { color: var(--text); font-weight: 500; }
.gf-meta-star { color: var(--text-2); }

.gf-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.gf-tag {
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--bg-muted);
    color: var(--text-2);
    border: 1px solid var(--border);
}

.gf-dishes {
    border-top: 1px solid var(--border);
    margin-top: 10px;
    padding-top: 10px;
    font-size: 12px;
    color: var(--text-2);
}
.gf-dish-label {
    color: var(--text-3);
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}
.gf-dish-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
}
.gf-dish-price { color: var(--text); font-weight: 500; font-variant-numeric: tabular-nums; }

/* ── Confirmation card ──────────────────────────────────────────────────── */
.gf-confirm {
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-left: 3px solid var(--text);
    border-radius: 8px;
    padding: 16px 18px;
    margin: 12px 0;
}
.gf-confirm-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-3);
    margin-bottom: 6px;
}
.gf-confirm-ref {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 18px;
    font-weight: 600;
    color: var(--text);
    letter-spacing: 0.02em;
    margin-bottom: 10px;
}
.gf-confirm-row {
    display: flex;
    font-size: 13px;
    color: var(--text-2);
    padding: 3px 0;
}
.gf-confirm-key {
    color: var(--text-3);
    width: 64px;
    flex-shrink: 0;
}
.gf-confirm-val { color: var(--text); }

/* ── Experience package ─────────────────────────────────────────────────── */
.gf-package {
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    margin: 10px 0;
}
.gf-package-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-3);
}
.gf-package-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    text-transform: capitalize;
    margin: 2px 0 8px;
}
.gf-package li {
    font-size: 13px;
    color: var(--text-2);
    line-height: 1.7;
    list-style: none;
    padding-left: 14px;
    position: relative;
}
.gf-package li::before {
    content: '—';
    position: absolute;
    left: 0;
    color: var(--text-4);
}

/* ── Returning guest banner (sidebar) ───────────────────────────────────── */
.gf-guest {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    margin: 6px 0 10px;
}
.gf-guest-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-3);
    margin-bottom: 4px;
}
.gf-guest-name { font-size: 13px; font-weight: 600; color: var(--text); }
.gf-guest-meta { font-size: 11px; color: var(--text-3); margin-top: 1px; }

/* ── Section heading ────────────────────────────────────────────────────── */
.gf-section-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-3);
    margin: 18px 0 8px;
}

/* ── Admin mode: dashboard / locations / admin tab styles (unchanged feel) ── */
.dash-kpi { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; text-align: center; }
.dash-kpi-value { font-size: 24px; font-weight: 600; color: var(--text); letter-spacing: -0.02em; }
.dash-kpi-label { font-size: 10px; color: var(--text-3); text-transform: uppercase; letter-spacing: .07em; margin-top: 2px; font-weight: 600; }
.dash-kpi-sub { font-size: 11px; color: var(--text-4); margin-top: 2px; }
.slot-badge { display:inline-flex; flex-direction:column; align-items:center; border-radius:5px; padding:4px 5px; margin:2px; min-width:52px; font-size:10px; font-weight:500; border:1px solid var(--border); }
.slot-badge .st { font-size:10px; font-weight:600; }
.slot-badge .sc { font-size:9px; font-weight:400; margin-top:1px; opacity:.85; }
.branch-dash-card { background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:10px; }
.branch-dash-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
.branch-dash-name { font-size:14px; font-weight:600; color: var(--text); }
.branch-dash-meta { font-size:11px; color: var(--text-3); margin-top:2px; }
.res-row { display:flex; gap:10px; align-items:center; padding:6px 10px; border-radius:6px; background:var(--bg-soft); margin:3px 0; font-size:12px; flex-wrap:wrap; }
.res-ref { font-family: ui-monospace, monospace; color:var(--text); font-weight:600; font-size:11px; min-width:88px; }
.res-guest { color:var(--text); font-weight:500; flex:1; min-width:100px; }
.res-detail { color:var(--text-3); }
.res-badge { display:inline-block; background:var(--bg-muted); color:var(--text-2); font-size:10px; padding:1px 6px; border-radius:4px; font-weight:500; border:1px solid var(--border); }
.legend-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; font-size:11px; color:var(--text-3); }
.legend-item { display:flex; align-items:center; gap:4px; }
.legend-dot { width:12px; height:12px; border-radius:3px; }

/* Menu rows (admin Locations tab) */
.menu-cat { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--text-3); margin: 14px 0 6px; }
.menu-row { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--bg-muted); font-size: 13px; }
.menu-row:last-child { border-bottom: none; }
.menu-item-name { color: var(--text); font-weight: 500; }
.menu-item-desc { color: var(--text-4); font-size: 11px; }
.menu-item-price { color: var(--text); font-weight: 500; font-variant-numeric: tabular-nums; white-space: nowrap; margin-left: 12px; }
.popular-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: var(--text-2); margin-right: 6px; vertical-align: middle; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

# Session ID: use ?session=<uuid> from the URL if present so refreshes resume
# the same conversation. Otherwise create a new one and pin it to the URL so
# the next refresh continues from here. This is what makes slot state + history
# survive a hard reload without us shipping a separate cookie/auth layer.
def _resolve_session_id() -> tuple[str, bool]:
    """Return (session_id, was_resumed_from_url)."""
    qp_sess = st.query_params.get("session")
    if qp_sess and len(qp_sess) >= 8:
        return qp_sess, True
    new_id = str(uuid.uuid4())
    st.query_params["session"] = new_id
    return new_id, False

if "session_id" not in st.session_state:
    sid, _resumed = _resolve_session_id()
    st.session_state.session_id = sid
    # If we resumed from URL, hydrate slot state + history from the DB
    if _resumed:
        _saved = load_session_state(sid)
        if _saved["agent_history"]:
            st.session_state.agent_history = _saved["agent_history"]
        if _saved["slots"]:
            # Reconstitute BookingSlots from saved dict in a sec — once the
            # other session_state keys exist (further down in this file).
            st.session_state["_saved_slots_dict"] = _saved["slots"]
        if _saved["guest_email"]:
            st.session_state["_saved_guest"] = _saved
        if _saved["last_intent"]:
            st.session_state["_saved_intent"] = _saved["last_intent"]
        # Restore visible chat history (display messages) too
        prior = load_recent_messages(sid, limit=200)
        if prior:
            st.session_state["_saved_display"] = [
                {"role": m["role"], "content": m["content"]} for m in prior
            ]

if "agent_history"          not in st.session_state:
    st.session_state.agent_history = []
if "display_messages"       not in st.session_state:
    st.session_state.display_messages = st.session_state.pop("_saved_display", [])
if "booking_refs"           not in st.session_state: st.session_state.booking_refs = []
if "branch_results"         not in st.session_state: st.session_state.branch_results = []
if "last_reservation"       not in st.session_state: st.session_state.last_reservation = None
if "last_experience_package" not in st.session_state: st.session_state.last_experience_package = None
if "_inject"                not in st.session_state: st.session_state._inject = None
if "user_lat"               not in st.session_state: st.session_state.user_lat = None
if "user_lon"               not in st.session_state: st.session_state.user_lon = None
if "user_location_name"     not in st.session_state: st.session_state.user_location_name = None
# location_source: "gps" | "gps_outside" | "manual" | "none"
#   gps          — real GPS, user is inside Bangalore service area
#   gps_outside  — real GPS, user is NOT in Bangalore (Pune, Mumbai, etc.)
#   manual       — user picked an area from the dropdown (centroid only)
#   none         — no location info; rank purely by popularity
if "location_source"        not in st.session_state: st.session_state.location_source = "none"
if "in_bangalore"           not in st.session_state: st.session_state.in_bangalore = True
if "city_centre_distance_km" not in st.session_state: st.session_state.city_centre_distance_km = None
# Resolved city name when GPS is outside Bangalore (from Nominatim reverse geocode).
# Used to phrase user_context honestly ("Guest GPS resolves to Mumbai") and to
# show the user where their GPS actually thinks they are.
if "gps_outside_city"        not in st.session_state: st.session_state.gps_outside_city = None
# Guest identity — populated once get_user_profile returns a hit
if "guest_name"             not in st.session_state: st.session_state.guest_name = None
if "guest_email"            not in st.session_state: st.session_state.guest_email = None
if "guest_phone"            not in st.session_state: st.session_state.guest_phone = None
if "guest_total_visits"     not in st.session_state: st.session_state.guest_total_visits = 0
if "dash_show_pii"          not in st.session_state: st.session_state.dash_show_pii = False
# Booking-slot state machine — persists across turns in the same session,
# AND across browser refreshes via the ?session=<uuid> URL pin.
if "booking_slots" not in st.session_state:
    saved = st.session_state.pop("_saved_slots_dict", None)
    if saved:
        # Hydrate dataclass from previously-saved dict; unknown keys ignored.
        valid_keys = {f.name for f in __import__("dataclasses").fields(BookingSlots)}
        st.session_state.booking_slots = BookingSlots(**{
            k: v for k, v in saved.items() if k in valid_keys
        })
    else:
        st.session_state.booking_slots = BookingSlots()

if "last_intent" not in st.session_state:
    st.session_state.last_intent = st.session_state.pop("_saved_intent", None)

# Restore identified-guest data if we resumed a session
_saved_guest = st.session_state.pop("_saved_guest", None)
if _saved_guest:
    if "guest_name"  not in st.session_state or not st.session_state.get("guest_name"):
        st.session_state.guest_name  = _saved_guest.get("guest_name")
    if "guest_email" not in st.session_state or not st.session_state.get("guest_email"):
        st.session_state.guest_email = _saved_guest.get("guest_email")
    if "guest_phone" not in st.session_state or not st.session_state.get("guest_phone"):
        st.session_state.guest_phone = _saved_guest.get("guest_phone")

CUISINES = ["North Indian", "South Indian", "Biryani", "Indo-Chinese",
            "Mughlai", "Coastal", "Italian", "Continental"]
NEIGHBORHOODS = list(NEIGHBORHOOD_COORDS.keys())
PRICE_LABELS = {1: "₹  Budget", 2: "₹₹  Moderate", 3: "₹₹₹  Upscale", 4: "₹₹₹₹  Fine Dining"}

# Total active locations — used in UI strings. Dynamic so it stays correct if
# the chain adds/removes branches.
def _location_count() -> int:
    try:
        conn = get_db()
        n = conn.execute("SELECT COUNT(*) FROM branches WHERE is_active=1").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0

# ── Helpers ───────────────────────────────────────────────────────────────────
def _db_metrics():
    try:
        conn = get_db()
        tot = conn.execute("SELECT COUNT(*) FROM reservations WHERE status='confirmed'").fetchone()[0]
        act = conn.execute("SELECT COUNT(*) FROM branches WHERE is_active=1").fetchone()[0]
        mis = conn.execute("SELECT COUNT(*) FROM search_failures WHERE date(created_at)=date('now')").fetchone()[0]
        conn.close()
        return tot, act, mis
    except: return 0,0,0

def _mask_email(email: str) -> str:
    """Partially obscure an email address for non-authorised display."""
    if not email or '@' not in str(email):
        return str(email) if email else ''
    local, domain = str(email).split('@', 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return visible + '***@' + domain

def _mask_phone(phone: str) -> str:
    """Show only the last 4 digits of a phone number."""
    if not phone:
        return ''
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) < 4:
        return '****'
    return '••••' + digits[-4:]

def _all_branches(cuisine=None, hood=None, active_only=True):
    conn = get_db()
    q = "SELECT * FROM branches WHERE 1=1"
    p = []
    if active_only: q += " AND is_active=1"
    if cuisine:     q += " AND cuisine=?"; p.append(cuisine)
    if hood:        q += " AND neighborhood=?"; p.append(hood)
    q += " ORDER BY neighborhood, cuisine"
    rows = [dict(r) for r in conn.execute(q,p).fetchall()]
    conn.close()
    return rows

def _branch_menu(branch_id):
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM menu_items WHERE branch_id=? AND is_available=1 ORDER BY category, is_popular DESC",
        (branch_id,)).fetchall()]
    conn.close()
    grouped = {}
    for it in items:
        grouped.setdefault(it["category"],[]).append(it)
    return grouped

def _recent_reservations():
    try:
        conn = get_db()
        rows = conn.execute("""SELECT r.reference_number, r.date, r.time, r.party_size,
               b.name AS bname, r.status FROM reservations r
               LEFT JOIN branches b ON r.branch_id=b.id
               ORDER BY r.created_at DESC LIMIT 6""").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except: return []

def _stars(rating):
    full = int(rating); half = 1 if (rating-full)>=0.5 else 0
    return "★"*full + ("½" if half else "") + "☆"*(5-full-half)

def _price_dots(pr):
    """₹ symbols indicating price tier, with the unused tier in muted grey."""
    pr = int(pr or 2)
    return "₹"*pr + f"<span style='color:#d6d3d1'>{'₹'*(4-pr)}</span>"

def _dietary_badges(b):
    """Monochrome tags — no decorative colours, no emojis."""
    parts = []
    if b.get("dietary_vegetarian"): parts.append('<span class="gf-tag">Vegetarian</span>')
    if b.get("dietary_vegan"):      parts.append('<span class="gf-tag">Vegan</span>')
    if b.get("dietary_gluten_free"):parts.append('<span class="gf-tag">Gluten-Free</span>')
    if b.get("dietary_halal"):      parts.append('<span class="gf-tag">Halal</span>')
    if b.get("dietary_kosher"):     parts.append('<span class="gf-tag">Kosher</span>')
    if b.get("parking"):            parts.append('<span class="gf-tag">Parking</span>')
    if b.get("outdoor_seating"):    parts.append('<span class="gf-tag">Outdoor</span>')
    if b.get("valet"):              parts.append('<span class="gf-tag">Valet</span>')
    return " ".join(parts)

def _branch_card_html(b, show_score=True):
    """Branch recommendation card — monochrome, emoji-free, ChatGPT-style typography."""
    # Distance label depends on the location source:
    #   gps     → real GPS, show "X.X km" (no tilde, exact tooltip)
    #   manual  → centroid, show "~X.X km" (tilde, "approximate" tooltip)
    #   else    → suppressed; we don't show distance for outside-Bangalore or no-location
    src = st.session_state.get("location_source", "none")
    dist_html = ""

    if src in ("gps", "manual"):
        # Prefer the distance the search tool computed; fall back to live haversine.
        if b.get("distance_km") is not None:
            d = b["distance_km"]
        elif st.session_state.user_lat and b.get("latitude"):
            d = haversine(st.session_state.user_lat, st.session_state.user_lon,
                          b["latitude"], b["longitude"])
        else:
            d = None

        if d is not None:
            if src == "gps":
                dist_html = (
                    f'<span class="gf-meta-dist" title="From your GPS location">'
                    f'{d:.1f} km</span>'
                )
            else:  # manual
                dist_html = (
                    f'<span class="gf-meta-dist" title="Approximate — from your selected area centre">'
                    f'~{d:.1f} km</span>'
                )

    # Confidence pill — uses the search tool's honest signal
    conf = b.get("confidence")
    conf_html = ""
    if conf == "high":
        conf_html = '<span class="gf-conf gf-conf-high">strong match</span>'
    elif conf == "medium":
        conf_html = '<span class="gf-conf gf-conf-medium">partial match</span>'
    elif conf == "low":
        conf_html = '<span class="gf-conf gf-conf-low">approximate</span>'

    # Menu highlights — clean two-column rows
    dishes_html = ""
    if b.get("menu_highlights"):
        rows = "".join(
            f'<div class="gf-dish-row"><span>{m["name"]}</span>'
            f'<span class="gf-dish-price">₹{m["price"]:.0f}</span></div>'
            for m in b["menu_highlights"]
        )
        dishes_html = (
            f'<div class="gf-dishes">'
            f'<div class="gf-dish-label">Popular dishes</div>'
            f'{rows}</div>'
        )

    # Meta line — rating, price tier, capacity, hours, distance
    meta_bits = []
    if dist_html:
        meta_bits.append(dist_html)
    meta_bits.append(f'<span class="gf-meta-star">★ {b["rating"]:.1f} · {b.get("review_count",0)} reviews</span>')
    meta_bits.append(f'<span>{_price_dots(b.get("price_range",2))}</span>')
    meta_bits.append(f'<span>{b["capacity"]} seats</span>')
    meta_bits.append(f'<span>{b.get("opening_time","12:00")}–{b.get("closing_time","23:00")}</span>')

    sub_parts = []
    if b.get("branch_code"):  sub_parts.append(b["branch_code"])
    if b.get("neighborhood"): sub_parts.append(b["neighborhood"])
    sub_line = " · ".join(sub_parts)

    return f"""
<div class="gf-card">
  <div class="gf-card-head">
    <div>
      <div class="gf-card-name">{b["name"]}</div>
      <div class="gf-card-sub">{sub_line}</div>
    </div>
    {conf_html}
  </div>
  <div class="gf-meta">{' '.join(meta_bits)}</div>
  <div class="gf-tags">{_dietary_badges(b)}</div>
  {dishes_html}
</div>"""

# ── Sidebar — minimal: brand, area, returning guest, recent, clear ────────────
with st.sidebar:
    st.markdown(
        '<div style="padding:14px 0 4px">'
        '<div style="font-size:15px;font-weight:600;color:var(--text);letter-spacing:-0.01em">GoodFoods</div>'
        '<div style="font-size:11px;color:var(--text-3);margin-top:1px">Bangalore Concierge</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Location: GPS-first, dropdown fallback ───────────────────────────────
    st.markdown(
        '<p style="font-size:10px;text-transform:uppercase;letter-spacing:.07em;'
        'color:var(--text-3);margin-bottom:6px;font-weight:600">Your location</p>',
        unsafe_allow_html=True,
    )

    # 1) Browser geolocation button. Component renders an icon; user clicks,
    #    browser prompts, result flows back as a dict.
    gps_payload = None
    if _GEO_AVAILABLE:
        gps_payload = streamlit_geolocation()

    gps_lat = gps_payload.get("latitude")  if isinstance(gps_payload, dict) else None
    gps_lon = gps_payload.get("longitude") if isinstance(gps_payload, dict) else None
    has_gps = gps_lat is not None and gps_lon is not None

    # 2) Resolve GPS first (real coords win unless the user manually picks an area).
    gps_resolved = None
    if has_gps:
        gps_resolved = resolve_user_location(gps_lat, gps_lon)

    # 3) Manual area picker — always available as override or primary input.
    manual_label = "Or pick an area" if has_gps else "Pick an area"
    hood_choice = st.selectbox(
        manual_label,
        ["Auto"] + NEIGHBORHOODS,
        label_visibility="visible",
        key="loc_select",
        help="Manually select a Bangalore neighbourhood. Overrides GPS if set.",
    )
    manual_picked = hood_choice != "Auto"

    # 4) Decide which source wins and update session_state accordingly.
    if manual_picked:
        # Manual choice always wins — explicit user intent.
        lat, lon = NEIGHBORHOOD_COORDS[hood_choice]
        st.session_state.user_lat = lat
        st.session_state.user_lon = lon
        st.session_state.user_location_name = hood_choice
        st.session_state.location_source = "manual"
        st.session_state.in_bangalore = True
        st.session_state.city_centre_distance_km = None
        st.markdown(
            f'<p style="font-size:11px;color:var(--text-3);margin-top:-4px">'
            f'Area: <strong style="color:var(--text)">{hood_choice}</strong> · '
            f'manual · distances approximate from area centre.</p>',
            unsafe_allow_html=True,
        )

    elif gps_resolved and gps_resolved["in_bangalore"]:
        # Real GPS inside Bangalore — use as-is, distances will be real.
        st.session_state.user_lat = gps_resolved["lat"]
        st.session_state.user_lon = gps_resolved["lon"]
        st.session_state.user_location_name = gps_resolved["nearest_neighborhood"]
        st.session_state.location_source = "gps"
        st.session_state.in_bangalore = True
        st.session_state.city_centre_distance_km = gps_resolved["city_centre_distance_km"]
        st.session_state.gps_outside_city = None   # we're inside, no outside-city banner

        # Show resolved city name as confirmation GPS is working
        geo_display = gps_resolved["geo"].get("display")
        confirm_line = (f"GPS confirms: {geo_display}. " if geo_display else "")
        st.markdown(
            f'<p style="font-size:11px;color:var(--text-3);margin-top:-4px;line-height:1.5">'
            f'{confirm_line}'
            f'Near <strong style="color:var(--text)">{gps_resolved["nearest_neighborhood"]}</strong> · '
            f'{gps_resolved["nearest_neighborhood_km"]:.1f} km from area centre.'
            f'</p>',
            unsafe_allow_html=True,
        )

    elif gps_resolved and not gps_resolved["in_bangalore"]:
        # Real GPS, but outside our service area — suppress distance ranking.
        # Show the actual resolved city name so the user can verify GPS is working
        # (and override manually if it's wrong).
        st.session_state.user_lat = None
        st.session_state.user_lon = None
        st.session_state.user_location_name = None
        st.session_state.location_source = "gps_outside"
        st.session_state.in_bangalore = False
        st.session_state.city_centre_distance_km = gps_resolved["city_centre_distance_km"]
        # Cache the resolved city in session state so user_context can read it
        st.session_state.gps_outside_city = gps_resolved["geo"].get("display")

        if gps_resolved["geo"].get("display"):
            location_phrase = f'in <strong style="color:var(--text)">{gps_resolved["geo"]["display"]}</strong>'
        else:
            location_phrase = '<strong style="color:var(--text)">outside Bangalore</strong>'

        st.markdown(
            f'<p style="font-size:11px;color:var(--text-3);margin-top:-4px;line-height:1.5">'
            f'GPS says you are {location_phrase}. '
            f"We're a Bangalore-only chain — pick a Bangalore area above if you'll be visiting, "
            f"or just ask about a specific neighbourhood."
            f'</p>',
            unsafe_allow_html=True,
        )

    else:
        # No GPS click yet, no manual choice.
        st.session_state.user_lat = None
        st.session_state.user_lon = None
        st.session_state.user_location_name = None
        st.session_state.location_source = "none"
        st.session_state.in_bangalore = True   # default assumption
        st.session_state.city_centre_distance_km = None
        if _GEO_AVAILABLE:
            st.markdown(
                '<p style="font-size:11px;color:var(--text-3);margin-top:-4px">'
                'Click the location icon for real distances, or pick an area above.</p>',
                unsafe_allow_html=True,
            )

    # Returning guest banner (only when a profile is loaded)
    if st.session_state.guest_name:
        visits = st.session_state.guest_total_visits
        st.markdown(
            f'<div class="gf-guest">'
            f'<div class="gf-guest-label">Returning guest</div>'
            f'<div class="gf-guest-name">{st.session_state.guest_name}</div>'
            f'<div class="gf-guest-meta">{st.session_state.guest_email}</div>'
            f'<div class="gf-guest-meta">{visits} previous visit{"s" if visits != 1 else ""}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Recent bookings are staff-only — they list other guests' reference numbers
    # and party sizes, which leak booking activity. Show only in admin mode.
    if _ADMIN_MODE:
        recents = _recent_reservations()
        if recents:
            st.markdown(
                '<p style="font-size:10px;text-transform:uppercase;letter-spacing:.07em;'
                'color:var(--text-3);margin-bottom:6px;font-weight:600">Recent bookings (staff)</p>',
                unsafe_allow_html=True,
            )
            for r in recents:
                dot = "●" if r["status"] == "confirmed" else "○"
                dot_color = "var(--good)" if r["status"] == "confirmed" else "var(--text-4)"
                st.markdown(
                    f'<div style="font-size:11px;padding:2px 0;color:var(--text-2)">'
                    f'<span style="color:{dot_color}">{dot}</span> '
                    f'<code style="font-size:10px;color:var(--text-2);background:transparent;padding:0">{r["reference_number"]}</code> '
                    f'<span style="color:var(--text-3)">{r["date"]} · {r["party_size"]}p</span></div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    if st.button("New conversation", use_container_width=True):
        for k in ("agent_history", "display_messages", "booking_refs", "branch_results"):
            st.session_state[k] = []
        for k in ("last_reservation", "last_experience_package", "last_intent"):
            st.session_state[k] = None
        for k in ("guest_name", "guest_email", "guest_phone"):
            st.session_state[k] = None
        st.session_state.guest_total_visits = 0
        # Reset the slot state machine and rotate the URL session id so the
        # next refresh doesn't restore the old (just-cleared) conversation.
        st.session_state.booking_slots = BookingSlots()
        new_sid = str(uuid.uuid4())
        st.session_state.session_id = new_sid
        st.query_params["session"] = new_sid
        st.rerun()

    # ── Admin-only debug panel: current intent + filled slots ────────────────
    if _ADMIN_MODE:
        st.markdown(
            '<p style="font-size:10px;color:var(--text-4);margin-top:14px;'
            'text-transform:uppercase;letter-spacing:.06em;font-weight:600">'
            'Debug · admin mode</p>',
            unsafe_allow_html=True,
        )
        if st.session_state.last_intent:
            st.markdown(
                f'<p style="font-size:11px;color:var(--text-3);margin:2px 0">'
                f'Last intent: <code style="background:transparent;color:var(--text-2);font-size:11px">{st.session_state.last_intent}</code></p>',
                unsafe_allow_html=True,
            )
        # Filled slots (compact)
        _slots_dict = st.session_state.booking_slots.to_dict()
        _filled = {k: v for k, v in _slots_dict.items() if v is not None}
        if _filled:
            st.markdown(
                '<p style="font-size:11px;color:var(--text-3);margin:6px 0 2px">'
                'Slots filled:</p>',
                unsafe_allow_html=True,
            )
            for k, v in _filled.items():
                # Mask phone, truncate long strings
                display = v
                if k == "user_phone" and isinstance(v, str) and len(v) >= 4:
                    display = "••••" + v[-4:]
                elif isinstance(v, str) and len(v) > 30:
                    display = v[:27] + "…"
                st.markdown(
                    f'<div style="font-size:10px;color:var(--text-2);padding:1px 0">'
                    f'<code style="background:transparent;font-size:10px;color:var(--text-3)">{k}</code>: '
                    f'<span style="color:var(--text)">{display}</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<p style="font-size:11px;color:var(--text-4);margin:2px 0">'
                '(no slots filled yet)</p>',
                unsafe_allow_html=True,
            )

# ── Tabs ──────────────────────────────────────────────────────────────────────
# Default: clean chat-only experience.
# ?admin=true: full tabs including Locations, Dashboard, Admin tools.
if _ADMIN_MODE:
    tab_chat, tab_locations, tab_dashboard, tab_admin = st.tabs(
        ["Concierge", "Locations", "Dashboard", "Admin"]
    )
else:
    # Single phantom container so the rest of the `with tab_chat:` block works unchanged.
    tab_chat = st.container()
    tab_locations = tab_dashboard = tab_admin = None

# ════════════════════════════════════════════════════════════════
# CONCIERGE — main guest-facing chat
# ════════════════════════════════════════════════════════════════
with tab_chat:
    # ── Header — minimal, no logo block ────────────────────────────────────────
    st.markdown(
        '<div class="gf-app-title">GoodFoods Concierge</div>'
        '<div class="gf-app-sub">Multi-cuisine dining across Bangalore</div>',
        unsafe_allow_html=True,
    )

    # ── Empty state with suggestion chips ──────────────────────────────────────
    SAMPLES = [
        "Best biryani in Koramangala for 4 this Saturday",
        "Great dosa place near Malleshwaram for brunch",
        "Anniversary dinner — Mughlai kebabs, 2 people",
        "Manchurian and noodles for 6, HSR Layout",
    ]

    if not st.session_state.display_messages:
        st.markdown(
            '<div class="gf-empty">'
            '<div class="gf-empty-title">What can I help you with?</div>'
            '<div class="gf-empty-sub">Find a table, browse menus, plan an occasion, '
            'or manage an existing booking — across our 25 GoodFoods kitchens in Bangalore.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(2)
        for i, s in enumerate(SAMPLES):
            if chip_cols[i % 2].button(s, key=f"chip_{i}", use_container_width=True):
                st.session_state._inject = s
                st.rerun()

    # ── Conversation history ───────────────────────────────────────────────────
    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ─────────────────────────────────────────────────────────────
    inject = st.session_state._inject
    st.session_state._inject = None
    prompt = st.chat_input("Message GoodFoods Concierge…") or inject

    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.display_messages.append({"role": "user", "content": prompt})

        # ── Build user context: location-aware ─────────────────────────────────
        # The LLM gets one of four messages depending on what we know about
        # where the guest is. Each message tells it explicitly whether to pass
        # lat/lon to search_branches.
        ctx_parts = []
        src = st.session_state.location_source

        if src == "gps" and st.session_state.user_lat is not None:
            # Real GPS, user is inside Bangalore — pass real coords, real distances.
            ctx_parts.append(
                f"[Guest location (REAL GPS, inside Bangalore): nearest area = "
                f"{st.session_state.user_location_name}, "
                f"lat={st.session_state.user_lat:.4f}, lon={st.session_state.user_lon:.4f}. "
                f"Pass these coordinates to search_branches — distances returned will be real. "
                f"EXCEPTION: if the guest explicitly says distance is not a concern "
                f"('any distance', 'anywhere in Bangalore', 'distance doesn't matter', "
                f"'I can travel'), do NOT pass coordinates and don't mention distance.]"
            )

        elif src == "manual" and st.session_state.user_lat is not None:
            # Manual area pick — pass centroid; treat distances as approximate.
            ctx_parts.append(
                f"[Guest area (MANUAL pick): {st.session_state.user_location_name}, "
                f"centroid lat={st.session_state.user_lat:.4f}, lon={st.session_state.user_lon:.4f}. "
                f"Pass these coordinates to search_branches but describe distances as "
                f"'approximate' or 'around X km' in your reply. "
                f"EXCEPTION: if the guest says distance is not a concern, do NOT pass coordinates.]"
            )

        elif src == "gps_outside":
            # Real GPS but outside Bangalore. The LLM gets this as context BUT
            # is instructed to mention it ONLY when the guest's request actually
            # implies they want nearby results. "Best pizza in Indiranagar" or
            # "best italian in Bangalore" should be answered normally — the
            # guest already named where they want to eat.
            city_name = st.session_state.gps_outside_city or "outside Bangalore"
            ctx_parts.append(
                f"[Guest's GPS resolves to {city_name} (outside our Bangalore service area). "
                f"Their location is ALREADY verified — do NOT call is_served_area this turn. "
                f"Call search_branches directly with whatever cuisine/dish/area the guest "
                f"mentions; do NOT pass lat/lon — distance from outside the city is "
                f"meaningless. Rank by popularity. "
                f"IMPORTANT — mention they're outside Bangalore ONLY if the guest's CURRENT "
                f"message implies 'near me' / 'nearby' / 'closest'. If the guest names a "
                f"specific Bangalore area, cuisine, or asks a general question, answer "
                f"naturally — do NOT bring up their geography.]"
            )

        # src == "none" → no location context, LLM ranks by popularity by default

        # ── Slot state — the most important "don't re-ask" hint ──────────────
        slot_line = format_slots_for_llm(st.session_state.booking_slots)
        if slot_line:
            ctx_parts.append(slot_line)

        if st.session_state.guest_email:
            ctx_parts.append(
                f"[IDENTIFIED GUEST: name={st.session_state.guest_name}, "
                f"email={st.session_state.guest_email}, "
                f"phone={st.session_state.guest_phone}. "
                f"Profile already loaded — do NOT ask for name or phone again unless the guest wants to change them.]"
            )
        user_context = " ".join(ctx_parts) if ctx_parts else None

        save_message(st.session_state.session_id, "user", prompt)

        with st.spinner("Thinking…"):
            try:
                response, new_history, side_effects, turn_meta = run_agent(
                    prompt,
                    st.session_state.agent_history,
                    st.session_state.session_id,
                    user_context,
                    existing_refs=st.session_state.booking_refs or None,
                    slots=st.session_state.booking_slots,   # mutated in place
                )
                st.session_state.agent_history = new_history
                st.session_state.last_intent   = turn_meta.get("intent")

                if side_effects["branch_results"]:
                    st.session_state.branch_results = side_effects["branch_results"]

                if side_effects["reservation"]:
                    st.session_state.last_reservation = side_effects["reservation"]
                    ref = side_effects["reservation"].get("reference_number")
                    if ref and ref not in st.session_state.booking_refs:
                        st.session_state.booking_refs.append(ref)

                if side_effects.get("experience_package"):
                    st.session_state.last_experience_package = side_effects["experience_package"]

                if side_effects.get("user_profile"):
                    prof = side_effects["user_profile"]
                    st.session_state.guest_name  = prof.get("name")  or st.session_state.guest_name
                    st.session_state.guest_email = prof.get("email") or st.session_state.guest_email
                    st.session_state.guest_phone = prof.get("phone") or st.session_state.guest_phone
                    st.session_state.guest_total_visits = prof.get("total_reservations", 0)
                    update_session_guest(
                        st.session_state.session_id,
                        email=st.session_state.guest_email,
                        name=st.session_state.guest_name,
                        phone=st.session_state.guest_phone,
                    )

            except RuntimeError as e:
                # Friendly UX for "all API keys cooling down" — common on Groq free tier
                # when traffic bursts. The conversation state is preserved; the guest
                # can simply retry.
                if "rate-limited" in str(e).lower():
                    response = (
                        "I'm getting a lot of requests right now and our free-tier "
                        "API quota is briefly maxed out. Please retry in 30-60 seconds "
                        "— your conversation is saved."
                    )
                else:
                    response = f"Something went wrong — please try again. *(Error: {e})*"
                side_effects = {"branch_results": [], "reservation": None,
                                "user_profile": None, "experience_package": None}
                turn_meta = {"intent": "ERROR_RATE_LIMIT" if "rate-limited" in str(e).lower() else "ERROR",
                             "slot_delta": {}, "turn_id": None}
            except Exception as e:
                response = f"Something went wrong — please try again. *(Error: {e})*"
                side_effects = {"branch_results": [], "reservation": None,
                                "user_profile": None, "experience_package": None}
                turn_meta = {"intent": "ERROR", "slot_delta": {}, "turn_id": None}

        save_message(st.session_state.session_id, "assistant", response)

        # Persist the full session state to DB so a browser refresh resumes
        # exactly where we left off (slots, agent history, last intent, guest).
        save_session_state(
            st.session_state.session_id,
            slots_dict=st.session_state.booking_slots.to_dict(),
            last_intent=st.session_state.last_intent,
            agent_history=st.session_state.agent_history,
        )

        with st.chat_message("assistant"):
            st.markdown(response)
        st.session_state.display_messages.append({"role": "assistant", "content": response})
        st.rerun()

    # ── Inline structured output below the conversation ────────────────────────
    # Branch recommendations, confirmation card, and experience package render
    # in the same centred column, just below the chat input. No separate panel.

    if st.session_state.last_reservation:
        res        = st.session_state.last_reservation
        guest_name = res.get("user_name") or st.session_state.guest_name or ""
        party      = res.get("party_size", 1)
        ref        = res.get("reference_number", "")

        rows_html = ""
        rows_html += f'<div class="gf-confirm-row"><span class="gf-confirm-key">Branch</span><span class="gf-confirm-val">{res.get("branch_name","")}</span></div>'
        rows_html += f'<div class="gf-confirm-row"><span class="gf-confirm-key">Date</span><span class="gf-confirm-val">{res.get("date","")}</span></div>'
        rows_html += f'<div class="gf-confirm-row"><span class="gf-confirm-key">Time</span><span class="gf-confirm-val">{res.get("time","")}</span></div>'
        rows_html += f'<div class="gf-confirm-row"><span class="gf-confirm-key">Party</span><span class="gf-confirm-val">{party} guest{"s" if party != 1 else ""}</span></div>'
        if guest_name:
            rows_html += f'<div class="gf-confirm-row"><span class="gf-confirm-key">Guest</span><span class="gf-confirm-val">{guest_name}</span></div>'

        st.markdown(
            f'<div class="gf-confirm">'
            f'<div class="gf-confirm-label">Booking confirmed</div>'
            f'<div class="gf-confirm-ref">{ref}</div>'
            f'{rows_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Quick-action buttons — plain text labels
        qa1, qa2, qa3 = st.columns(3)
        if qa1.button("Modify booking", key="qa_mod", use_container_width=True):
            st.session_state._inject = f"I'd like to modify my booking {ref}"
            st.rerun()
        if qa2.button("View details", key="qa_det", use_container_width=True):
            st.session_state._inject = f"Can you show me the full details for {ref}?"
            st.rerun()
        if qa3.button("Cancel booking", key="qa_can", use_container_width=True):
            st.session_state._inject = f"I need to cancel booking {ref}"
            st.rerun()

        if len(st.session_state.booking_refs) > 1:
            st.markdown(
                '<p class="gf-section-label">This session</p>',
                unsafe_allow_html=True,
            )
            for r in st.session_state.booking_refs:
                dot_color = "var(--good)" if r == ref else "var(--text-4)"
                st.markdown(
                    f'<div style="font-size:12px;padding:2px 0;color:var(--text-2)">'
                    f'<span style="color:{dot_color}">●</span> '
                    f'<code style="font-size:12px;background:transparent;padding:0">{r}</code></div>',
                    unsafe_allow_html=True,
                )

    if st.session_state.last_experience_package:
        pkg      = st.session_state.last_experience_package
        p        = pkg.get("package", {})
        inc      = p.get("includes", [])
        extras   = p.get("extras", "")
        occasion = pkg.get("occasion", "")
        items_html = "".join(f"<li>{item}</li>" for item in inc)
        extras_html = (
            f'<div style="font-size:12px;color:var(--text-3);margin-top:8px;font-style:italic">{extras}</div>'
            if extras else ""
        )
        st.markdown(
            f'<div class="gf-package">'
            f'<div class="gf-package-label">Experience package</div>'
            f'<div class="gf-package-name">{occasion}</div>'
            f'<ul style="margin:0;padding:0">{items_html}</ul>'
            f'{extras_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.branch_results:
        st.markdown(
            '<p class="gf-section-label">Recommended locations</p>',
            unsafe_allow_html=True,
        )
        for b in st.session_state.branch_results:
            st.markdown(_branch_card_html(b), unsafe_allow_html=True)



# ── Admin-only tools (Dashboard, Locations grid, Admin) ─────────────────────
if _ADMIN_MODE:
    # ════════════════════════════════════════════════════════════════
    # LOCATIONS TAB (admin only)
    # ════════════════════════════════════════════════════════════════
    with tab_locations:
        st.markdown(f"### Our {_location_count()} GoodFoods Locations across Bangalore")

        fc1, fc2, fc3 = st.columns([2,2,1])
        f_cui  = fc1.selectbox("Cuisine", ["All"]+CUISINES, key="loc_cui")
        f_hood = fc2.selectbox("Neighbourhood", ["All"]+NEIGHBORHOODS, key="loc_hd")
        f_diet = fc3.selectbox("Dietary", ["All","Vegetarian","Vegan","Halal","Gluten-Free"], key="loc_diet")

        branches = _all_branches(
            cuisine=None if f_cui=="All" else f_cui,
            hood=None if f_hood=="All" else f_hood,
        )
        if f_diet == "Vegetarian":  branches = [b for b in branches if b["dietary_vegetarian"]]
        elif f_diet == "Vegan":     branches = [b for b in branches if b["dietary_vegan"]]
        elif f_diet == "Halal":     branches = [b for b in branches if b["dietary_halal"]]
        elif f_diet == "Gluten-Free":branches= [b for b in branches if b["dietary_gluten_free"]]

        if st.session_state.user_lat:
            for b in branches:
                if b.get("latitude"):
                    b["_dist"] = haversine(st.session_state.user_lat, st.session_state.user_lon, b["latitude"], b["longitude"])
            branches.sort(key=lambda x: x.get("_dist", 999))

        st.markdown(f'<p style="font-size:12px;color:#6b7280;margin-bottom:16px">{len(branches)} location(s) found</p>', unsafe_allow_html=True)

        # 3-column grid
        cols = st.columns(3)
        for i, b in enumerate(branches):
            with cols[i % 3]:
                dist_str = ""
                if b.get("_dist") is not None:
                    dist_str = f'<span style="color:#dc2626;font-weight:600">📍 ~{b["_dist"]:.1f} km</span>  · '
                dietary_str = _dietary_badges(b)
                price_str = "₹" * b.get("price_range", 2)

                with st.expander(f"**{b['name']}**  |  ⭐ {b['rating']}  ·  {price_str}"):
                    st.markdown(f"""
                    <div style="font-size:11px;color:#6b7280;margin-bottom:10px">
                      {dist_str}{b.get('address','')}
                    </div>
                    <div style="font-size:12px;color:#374151;margin-bottom:10px;line-height:1.5">
                      {b.get('description','')[:180]}{'…' if len(b.get('description',''))>180 else ''}
                    </div>
                    <div style="margin-bottom:8px">{dietary_str}</div>
                    <div style="font-size:11px;color:#6b7280">
                      🪑 {b['capacity']} seats &nbsp; 🕐 {b.get('opening_time','12:00')}–{b.get('closing_time','23:00')}
                      &nbsp; {'🅿️' if b.get('parking') else ''} {'🌿' if b.get('outdoor_seating') else ''}
                      <br>📞 {b.get('phone','—')}
                    </div>
                    """, unsafe_allow_html=True)

                    # Menu
                    menu = _branch_menu(b["id"])
                    if menu:
                        st.markdown("---")
                        for cat, items in menu.items():
                            st.markdown(f'<div class="menu-cat">{cat}</div>', unsafe_allow_html=True)
                            menu_html = ""
                            for it in items:
                                pop = '<span class="popular-dot" title="Popular"></span>' if it["is_popular"] else "&nbsp;&nbsp;&nbsp;"
                                diet_icons = ""
                                if it["is_vegan"]: diet_icons += "🌱"
                                elif it["is_vegetarian"]: diet_icons += "🥗"
                                if it["is_gluten_free"]: diet_icons += "🌾"
                                if it["is_halal"]: diet_icons += "☪"
                                menu_html += f"""
                                <div class="menu-row">
                                  <div>
                                    <span class="menu-item-name">{pop}{it['name']} {diet_icons}</span><br>
                                    <span class="menu-item-desc">{it.get('description','')[:70]}</span>
                                  </div>
                                  <div class="menu-item-price">₹{it['price']:.0f}</div>
                                </div>"""
                            st.markdown(menu_html, unsafe_allow_html=True)


    # ════════════════════════════════════════════════════════════════
    # LIVE DASHBOARD TAB
    # ════════════════════════════════════════════════════════════════
    with tab_dashboard:
        st.markdown("""
        <div class="gf-header">
          <div class="gf-logo" style="font-size:18px">📊</div>
          <div>
            <div class="gf-title">Live Booking Dashboard</div>
            <div class="gf-subtitle">Real-time slot availability and guest reservation details</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # ── Controls ───────────────────────────────────────────────────────────────
        ctrl1, ctrl2, ctrl3 = st.columns([3, 2, 2])
        sel_date = ctrl1.date_input(
            "Select date",
            value=_dt_d.date.today(),
            min_value=_dt_d.date.today() - _dt_d.timedelta(days=60),
            max_value=_dt_d.date.today() + _dt_d.timedelta(days=120),
            key="dash_date",
            label_visibility="collapsed",
        )
        show_all_b = ctrl2.toggle("Show all branches", value=False, key="dash_all")
        dash_hood  = ctrl3.selectbox("Filter neighbourhood", ["All"] + NEIGHBORHOODS, key="dash_hood", label_visibility="collapsed")
        sel_date_str = str(sel_date)

        # ── Fetch all data for the selected date ───────────────────────────────────
        _conn = get_db()
        _res_rows = _conn.execute("""
            SELECT r.id, r.reference_number, r.branch_id, r.user_name, r.user_email,
                   r.user_phone, r.party_size, r.time, r.occasion, r.special_requests,
                   r.status, r.created_at,
                   b.name AS branch_name, b.capacity, b.opening_time, b.closing_time,
                   b.neighborhood, b.cuisine, b.price_range, b.rating
            FROM reservations r
            JOIN branches b ON r.branch_id = b.id
            WHERE r.date = ? AND r.status = 'confirmed'
            ORDER BY b.neighborhood, b.name, r.time
        """, (sel_date_str,)).fetchall()
        _dash_res = [dict(r) for r in _res_rows]

        _cancel_today = _conn.execute(
            "SELECT COUNT(*) FROM reservations WHERE date=? AND status='cancelled'",
            (sel_date_str,)
        ).fetchone()[0]

        _active_branches = _conn.execute(
            "SELECT * FROM branches WHERE is_active=1 ORDER BY neighborhood, name"
        ).fetchall()
        _active_branches = [dict(b) for b in _active_branches]
        _conn.close()

        # ── KPI metrics ────────────────────────────────────────────────────────────
        total_bk    = len(_dash_res)
        total_guests = sum(r["party_size"] for r in _dash_res)
        uniq_branches = len(set(r["branch_id"] for r in _dash_res))
        total_active = len(_active_branches)

        # Average peak fill rate across all branches with bookings
        _br_res_map = defaultdict(list)
        for r in _dash_res:
            _br_res_map[r["branch_id"]].append(r)

        def _peak_fill(branch, res_list):
            cap = branch.get("capacity") or 1
            opening = branch.get("opening_time") or "11:00"
            closing  = branch.get("closing_time") or "22:30"
            peak = 0
            for slot in get_branch_slots(opening, closing):
                s_min = _t2m(slot); s_end = s_min + 90
                occ = sum(
                    r["party_size"] for r in res_list
                    if _t2m(r["time"]) < s_end and (_t2m(r["time"]) + 90) > s_min
                )
                peak = max(peak, occ)
            return min(100.0, peak / cap * 100)

        # Build a fast lookup: branch_id → branch dict
        _bid2b = {b["id"]: b for b in _active_branches}
        peak_fills = [
            _peak_fill(_bid2b[bid], rlist)
            for bid, rlist in _br_res_map.items()
            if bid in _bid2b
        ]
        avg_fill = sum(peak_fills) / len(peak_fills) if peak_fills else 0.0

        # Render KPIs
        k1, k2, k3, k4, k5 = st.columns(5)
        _day_label = "Today" if sel_date == _dt_d.date.today() else sel_date.strftime("%b %d")
        k1.markdown(f'<div class="dash-kpi"><div class="dash-kpi-value">{total_bk}</div><div class="dash-kpi-label">Confirmed Bookings</div><div class="dash-kpi-sub">{_day_label}</div></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="dash-kpi"><div class="dash-kpi-value">{total_guests}</div><div class="dash-kpi-label">Total Guests</div><div class="dash-kpi-sub">{_day_label}</div></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="dash-kpi"><div class="dash-kpi-value">{uniq_branches}</div><div class="dash-kpi-label">Branches Booked</div><div class="dash-kpi-sub">of {total_active} active</div></div>', unsafe_allow_html=True)
        k4.markdown(f'<div class="dash-kpi"><div class="dash-kpi-value">{avg_fill:.0f}%</div><div class="dash-kpi-label">Avg Peak Fill</div><div class="dash-kpi-sub">across booked branches</div></div>', unsafe_allow_html=True)
        k5.markdown(f'<div class="dash-kpi"><div class="dash-kpi-value">{_cancel_today}</div><div class="dash-kpi-label">Cancellations</div><div class="dash-kpi-sub">{_day_label}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── PII guard ──────────────────────────────────────────────────────────────
        st.warning("⚠️ This dashboard contains guest PII (name, email, phone). Authorised staff only.")
        _show_pii = st.checkbox(
            "Reveal full guest contact details",
            value=st.session_state.dash_show_pii,
            key="dash_pii_toggle",
        )
        st.session_state.dash_show_pii = _show_pii

        # ── Colour legend ──────────────────────────────────────────────────────────
        st.markdown("""
        <div class="legend-row">
          <span style="font-size:12px;font-weight:600;color:#374151;margin-right:4px">Slot fill:</span>
          <span class="legend-item"><span class="legend-dot" style="background:#f3f4f6;border:1px solid #d1d5db"></span> Empty</span>
          <span class="legend-item"><span class="legend-dot" style="background:#d1fae5"></span> ≤40%</span>
          <span class="legend-item"><span class="legend-dot" style="background:#fef3c7"></span> 41–70%</span>
          <span class="legend-item"><span class="legend-dot" style="background:#ffedd5"></span> 71–90%</span>
          <span class="legend-item"><span class="legend-dot" style="background:#dc2626"></span> >90%</span>
          <span style="margin-left:10px;font-size:11px;color:#9ca3af">Each badge = 30-min slot · number shows seats used / capacity</span>
        </div>""", unsafe_allow_html=True)

        # ── Slot fill colour helper ────────────────────────────────────────────────
        def _slot_color(pct):
            if pct == 0:      return "#f3f4f6", "#9ca3af"
            elif pct <= 40:   return "#d1fae5", "#065f46"
            elif pct <= 70:   return "#fef3c7", "#92400e"
            elif pct <= 90:   return "#ffedd5", "#9a3412"
            else:             return "#dc2626", "#ffffff"

        # ── Build slot HTML for one branch ────────────────────────────────────────
        def _slot_grid(branch, res_list):
            cap = branch.get("capacity") or 1
            opening = branch.get("opening_time") or "11:00"
            closing  = branch.get("closing_time") or "22:30"
            badges = []
            for slot in get_branch_slots(opening, closing):
                s_min = _t2m(slot); s_end = s_min + 90
                occ = sum(
                    r["party_size"] for r in res_list
                    if _t2m(r["time"]) < s_end and (_t2m(r["time"]) + 90) > s_min
                )
                pct = occ / cap * 100
                bg, fg = _slot_color(pct)
                badges.append(
                    f'<div class="slot-badge" style="background:{bg};color:{fg}" title="{slot}: {occ}/{cap} seats ({pct:.0f}%)">'
                    f'<span class="st">{slot}</span>'
                    f'<span class="sc">{occ}/{cap}</span>'
                    f'</div>'
                )
            return '<div style="display:flex;flex-wrap:wrap;gap:2px">' + "".join(badges) + "</div>"

        # ── Decide which branches to show ─────────────────────────────────────────
        if dash_hood != "All":
            _pool = [b for b in _active_branches if b["neighborhood"] == dash_hood]
        else:
            _pool = _active_branches

        if show_all_b:
            _display_branches = _pool
        else:
            _booked_ids = set(_br_res_map.keys())
            _display_branches = [b for b in _pool if b["id"] in _booked_ids]

        # ── Branch slot cards ──────────────────────────────────────────────────────
        st.markdown(f"#### Branch Slot Availability — {sel_date.strftime('%A, %B %d %Y')}")

        if not _display_branches:
            st.markdown(
                '<div style="text-align:center;padding:40px;color:#9ca3af;border:1px dashed #e5e7eb;border-radius:10px">'
                '<div style="font-size:24px;margin-bottom:8px">📅</div>'
                '<div style="font-size:13px">No bookings on this date.<br>'
                'Toggle <strong>Show all branches</strong> to see full availability.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            for _branch in _display_branches:
                _bid = _branch["id"]
                _bres = _br_res_map.get(_bid, [])
                _bk_count   = len(_bres)
                _guest_count = sum(r["party_size"] for r in _bres)
                _pf          = _peak_fill(_branch, _bres)
                _pfcolor     = _slot_color(_pf)[0]

                # Branch header
                _occasions = ", ".join(filter(None, {r.get("occasion") or "" for r in _bres}))
                _header = (
                    f'<div class="branch-dash-card">'
                    f'<div class="branch-dash-header">'
                    f'<div>'
                    f'<div class="branch-dash-name">{_branch["name"]}</div>'
                    f'<div class="branch-dash-meta">'
                    f'{_branch["neighborhood"]} · {_branch["cuisine"]} · '
                    f'⭐ {_branch["rating"]} · 🪑 {_branch["capacity"]} seats'
                    f'</div>'
                    f'</div>'
                    f'<div style="display:flex;gap:8px;align-items:center">'
                    f'<span style="background:{_pfcolor};color:{_slot_color(_pf)[1]};'
                    f'font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px">'
                    f'Peak {_pf:.0f}%</span>'
                    f'<span style="font-size:12px;color:#6b7280">'
                    f'{_bk_count} booking{"s" if _bk_count != 1 else ""} · {_guest_count} guest{"s" if _guest_count != 1 else ""}'
                    f'</span>'
                    f'</div>'
                    f'</div>'
                )

                st.markdown(_header, unsafe_allow_html=True)
                st.markdown(_slot_grid(_branch, _bres), unsafe_allow_html=True)

                # Reservation rows
                if _bres:
                    st.markdown('<div style="margin-top:10px;margin-bottom:4px;font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Reservations</div>', unsafe_allow_html=True)
                    for _r in sorted(_bres, key=lambda x: x["time"]):
                        _occ_html = f'<span class="res-badge">{_r["occasion"].title()}</span>' if _r.get("occasion") else ""
                        _req_html = f'<span class="res-detail" title="{_r.get("special_requests","")}">📝 {str(_r.get("special_requests",""))[:40]}{"…" if len(str(_r.get("special_requests","") or "")) > 40 else ""}</span>' if _r.get("special_requests") else ""
                        _email_disp = _r["user_email"] if _show_pii else _mask_email(_r["user_email"])
                        _phone_disp = _r["user_phone"] if _show_pii else _mask_phone(_r["user_phone"])
                        st.markdown(
                            f'<div class="res-row">'
                            f'<span class="res-ref">{_r["reference_number"]}</span>'
                            f'<span style="background:#f3f4f6;color:#374151;font-size:11px;font-weight:700;'
                            f'padding:2px 8px;border-radius:4px">🕐 {_r["time"]}</span>'
                            f'<span class="res-guest">👤 {_r["user_name"]}</span>'
                            f'<span class="res-detail">✉️ {_email_disp}</span>'
                            f'<span class="res-detail">📞 {_phone_disp}</span>'
                            f'<span style="background:#dbeafe;color:#1e40af;font-size:11px;font-weight:700;'
                            f'padding:2px 8px;border-radius:4px">👥 {_r["party_size"]}</span>'
                            f'{_occ_html}'
                            f'{_req_html}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown("")

        # ── Full reservations table ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown(f"#### All Reservations — {sel_date.strftime('%A, %B %d %Y')}")

        if _dash_res:
            _table_data = []
            for _r in sorted(_dash_res, key=lambda x: (x["time"], x["branch_name"])):
                _table_data.append({
                    "Ref #":           _r["reference_number"],
                    "Time":            _r["time"],
                    "Branch":          _r["branch_name"],
                    "Neighbourhood":   _r["neighborhood"],
                    "Guest":           _r["user_name"],
                    "Email":           _r["user_email"] if _show_pii else _mask_email(_r["user_email"]),
                    "Phone":           _r["user_phone"] if _show_pii else _mask_phone(_r["user_phone"]),
                    "Party":           _r["party_size"],
                    "Occasion":        _r.get("occasion") or "—",
                    "Special Requests":_r.get("special_requests") or "—",
                    "Booked At":       (_r.get("created_at") or "")[:16],
                })
            _df = pd.DataFrame(_table_data)
            st.dataframe(
                _df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ref #":    st.column_config.TextColumn("Ref #", width="small"),
                    "Time":     st.column_config.TextColumn("Time", width="small"),
                    "Party":    st.column_config.NumberColumn("Party", width="small"),
                    "Branch":   st.column_config.TextColumn("Branch", width="medium"),
                },
            )
            st.caption(f"{len(_dash_res)} confirmed reservation(s) · {sum(r['party_size'] for r in _dash_res)} total guests")
        else:
            st.info(f"No confirmed reservations for {sel_date.strftime('%B %d, %Y')}.")


    # ════════════════════════════════════════════════════════════════
    # ADMIN TAB
    # ════════════════════════════════════════════════════════════════
    with tab_admin:
        st.markdown("### Branch Administration")
        adm1, adm2, adm3, adm4, adm5 = st.tabs(["All Branches", "Add Location", "Edit Location", "Analytics", "Agent Traces"])

        with adm1:
            all_b = _all_branches(active_only=False)
            fc1, fc2, fc3 = st.columns(3)
            fa_cui  = fc1.selectbox("Cuisine", ["All"]+CUISINES, key="a_cui")
            fa_hood = fc2.selectbox("Neighbourhood", ["All"]+NEIGHBORHOODS, key="a_hd")
            fa_stat = fc3.selectbox("Status", ["All","Active","Inactive"], key="a_st")
            filtered = all_b
            if fa_cui  != "All": filtered = [b for b in filtered if b["cuisine"]==fa_cui]
            if fa_hood != "All": filtered = [b for b in filtered if b["neighborhood"]==fa_hood]
            if fa_stat == "Active":   filtered = [b for b in filtered if b["is_active"]]
            elif fa_stat == "Inactive": filtered = [b for b in filtered if not b["is_active"]]

            st.markdown(f"**{len(filtered)} location(s)**")
            for b in filtered:
                status = "🟢" if b["is_active"] else "🔴"
                with st.expander(f"{status} [{b.get('branch_code','?')}] {b['name']}  ·  ⭐{b['rating']}  ·  {b['capacity']} seats"):
                    c1,c2,c3 = st.columns(3)
                    c1.write(f"**Cuisine:** {b['cuisine']}")
                    c1.write(f"**Neighbourhood:** {b['neighborhood']}")
                    c1.write(f"**Capacity:** {b['capacity']} seats ({b.get('tables','?')} tables)")
                    c2.write(f"**Rating:** ⭐ {b['rating']} ({b.get('review_count',0)} reviews)")
                    c2.write(f"**Price:** {'₹'*b.get('price_range',2)}")
                    c2.write(f"**Hours:** {b.get('opening_time','12:00')}–{b.get('closing_time','23:00')}")
                    c3.write(f"**Phone:** {b.get('phone','—')}")
                    c3.write(f"**Parking:** {'Yes' if b.get('parking') else 'No'}  |  **Outdoor:** {'Yes' if b.get('outdoor_seating') else 'No'}")
                    c3.write(f"**Valet:** {'Yes' if b.get('valet') else 'No'}")
                    if b.get("address"): st.write(f"**Address:** {b['address']}")
                    st.write(f"**Dietary:** " + (", ".join(filter(None,[
                        "Vegetarian" if b.get("dietary_vegetarian") else None,
                        "Vegan" if b.get("dietary_vegan") else None,
                        "Gluten-Free" if b.get("dietary_gluten_free") else None,
                        "Halal" if b.get("dietary_halal") else None,
                        "Kosher" if b.get("dietary_kosher") else None,
                    ])) or "None specified"))

        with adm2:
            st.markdown("#### Add a New GoodFoods Bangalore Location")
            with st.form("add_form", clear_on_submit=True):
                c1,c2 = st.columns(2)
                new_hood = c1.selectbox("Neighbourhood *", NEIGHBORHOODS)
                new_cui  = c2.selectbox("Cuisine *", CUISINES)
                from scripts.seed_data import CUISINE_LABEL
                auto_name = f"GoodFoods {new_hood} — {CUISINE_LABEL.get(new_cui, new_cui)}"
                new_name = st.text_input("Branch Name", value=auto_name)
                new_addr = st.text_input("Street Address", placeholder="123 100ft Road, Indiranagar, Bangalore")
                new_phone= st.text_input("Phone", placeholder="+91 80 4123 5678")

                c3,c4,c5 = st.columns(3)
                new_cap  = c3.number_input("Capacity (seats)", 10, 500, 60, 10)
                new_rat  = c4.slider("Initial Rating", 3.8, 5.0, 4.2, 0.1)
                new_pr   = c5.select_slider("Price Range", [1,2,3,4], 2, format_func=lambda x:"₹"*x)

                c6,c7 = st.columns(2)
                new_open = c6.text_input("Opens", "12:00")
                new_clos = c7.text_input("Closes", "23:00")

                st.markdown("**Dietary options:**")
                d1,d2,d3,d4,d5 = st.columns(5)
                nv=d1.checkbox("Vegetarian"); nvegan=d2.checkbox("Vegan")
                ngf=d3.checkbox("Gluten-Free"); nhal=d4.checkbox("Halal"); nkos=d5.checkbox("Kosher")
                f1,f2,f3 = st.columns(3)
                npark=f1.checkbox("Parking"); nout=f2.checkbox("Outdoor"); nval=f3.checkbox("Valet")

                new_desc = st.text_area("Description (optional)", height=80)
                submitted = st.form_submit_button("➕ Add Location", use_container_width=True)

            if submitted:
                conn = get_db()
                from scripts.seed_data import NEIGHBORHOOD_ABBREV
                codes = {r[0] for r in conn.execute("SELECT branch_code FROM branches WHERE branch_code IS NOT NULL")}
                abbr  = NEIGHBORHOOD_ABBREV.get(new_hood, new_hood[:2].upper())
                seq   = 1
                while f"GF-{abbr}-{seq:02d}" in codes: seq+=1
                code  = f"GF-{abbr}-{seq:02d}"
                base_lat, base_lon = NEIGHBORHOOD_COORDS[new_hood]
                lat = round(base_lat + random.uniform(-0.006,0.006),6)
                lon = round(base_lon + random.uniform(-0.006,0.006),6)
                conn.execute("""INSERT INTO branches
                    (branch_code,name,neighborhood,address,city,latitude,longitude,capacity,tables,cuisine,
                     rating,review_count,popularity_score,price_range,
                     dietary_vegetarian,dietary_vegan,dietary_gluten_free,
                     dietary_halal,dietary_kosher,parking,outdoor_seating,valet,is_active,
                     opening_time,closing_time,phone,description)
                    VALUES(?,?,?,?,'Bangalore',?,?,?,?,?,?,0,50.0,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
                    (code,new_name,new_hood,new_addr or None,lat,lon,new_cap,new_cap//4,new_cui,
                     new_rat,new_pr,int(nv),int(nvegan),int(ngf),int(nhal),int(nkos),
                     int(npark),int(nout),int(nval),new_open,new_clos,new_phone or None,new_desc or None))
                # Seed menu items for new branch from template
                from scripts.seed_data import MENUS, _build_dish_tags
                price_factor = {1:0.85,2:1.0,3:1.15,4:1.30}.get(new_pr,1.0)
                branch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                for item in MENUS.get(new_cui,[]):
                    nm, desc, cat, bp, veg, vegan, gf, jain, pop, cal, raw_tags = item
                    tags = _build_dish_tags(nm, new_cui, raw_tags, bool(veg), bool(vegan), bool(gf))
                    conn.execute("""INSERT INTO menu_items
                        (branch_id,name,description,category,price,is_available,is_vegetarian,
                         is_vegan,is_gluten_free,is_halal,is_jain,is_popular,calories,dish_tags)
                        VALUES(?,?,?,?,?,1,?,?,?,1,?,?,?,?)""",
                        (branch_id, nm, desc, cat, round(bp*price_factor, 0),
                         int(veg), int(vegan), int(gf), int(jain), int(pop), cal, tags))
                conn.commit(); conn.close()
                st.success(f"✅ **{new_name}** added! Code: `{code}`. Menu seeded with {len(MENUS.get(new_cui,[]))} items.")
                st.rerun()

        with adm3:
            st.markdown("#### Edit or Deactivate a Location")
            all_b2 = _all_branches(active_only=False)
            options = {f"[{b.get('branch_code','?')}] {b['name']}": b for b in all_b2}
            sel = st.selectbox("Select location:", list(options.keys()), key="edit_sel")
            b = options[sel]

            with st.form("edit_form"):
                c1,c2 = st.columns(2)
                en   = c1.text_input("Name", b["name"])
                eact = c2.toggle("Active", value=bool(b["is_active"]))
                eaddr= st.text_input("Address", b.get("address") or "")
                ephon= st.text_input("Phone", b.get("phone") or "")
                c3,c4,c5 = st.columns(3)
                ecap = c3.number_input("Capacity", 10, 500, int(b["capacity"] or 60), 10)
                erat = c4.slider("Rating", 3.8, 5.0, float(b["rating"] or 4.2), 0.1)
                epr  = c5.select_slider("Price", [1,2,3,4], int(b.get("price_range") or 2), format_func=lambda x:"₹"*x)
                c6,c7 = st.columns(2)
                eopen= c6.text_input("Opens", b.get("opening_time","12:00"))
                eclos= c7.text_input("Closes", b.get("closing_time","23:00"))
                d1,d2,d3,d4,d5 = st.columns(5)
                ev=d1.checkbox("Vegetarian",bool(b["dietary_vegetarian"]))
                evegan=d2.checkbox("Vegan",bool(b["dietary_vegan"]))
                egf=d3.checkbox("Gluten-Free",bool(b["dietary_gluten_free"]))
                ehal=d4.checkbox("Halal",bool(b["dietary_halal"]))
                ekos=d5.checkbox("Kosher",bool(b["dietary_kosher"]))
                f1,f2,f3=st.columns(3)
                epark=f1.checkbox("Parking",bool(b.get("parking")))
                eout=f2.checkbox("Outdoor",bool(b.get("outdoor_seating")))
                eval_=f3.checkbox("Valet",bool(b.get("valet")))
                edesc=st.text_area("Description", b.get("description") or "", height=80)
                save=st.form_submit_button("💾 Save Changes", use_container_width=True)

            if save:
                conn=get_db()
                conn.execute("""UPDATE branches SET name=?,is_active=?,address=?,phone=?,
                    capacity=?,tables=?,rating=?,price_range=?,opening_time=?,closing_time=?,
                    dietary_vegetarian=?,dietary_vegan=?,dietary_gluten_free=?,
                    dietary_halal=?,dietary_kosher=?,parking=?,outdoor_seating=?,valet=?,description=?
                    WHERE id=?""",
                    (en,int(eact),eaddr or None,ephon or None,ecap,ecap//4,erat,epr,eopen,eclos,
                     int(ev),int(evegan),int(egf),int(ehal),int(ekos),int(epark),int(eout),int(eval_),
                     edesc or None, b["id"]))
                conn.commit(); conn.close()
                st.success(f"✅ **{en}** updated — {'active' if eact else 'deactivated'}.")
                st.rerun()

    # ── Analytics sub-tab ─────────────────────────────────────────────────────────
    with adm4:
        st.markdown("#### Reservation Analytics")

        try:
            conn = get_db()

            # ── Summary KPI row ──────────────────────────────────────────────────
            total_conf   = conn.execute("SELECT COUNT(*) FROM reservations WHERE status='confirmed'").fetchone()[0]
            total_cancel = conn.execute("SELECT COUNT(*) FROM reservations WHERE status='cancelled'").fetchone()[0]
            total_fails  = conn.execute("SELECT COUNT(*) FROM search_failures").fetchone()[0]
            crm_pending  = conn.execute("SELECT COUNT(*) FROM occasion_crm WHERE sent=0").fetchone()[0]
            crm_sent     = conn.execute("SELECT COUNT(*) FROM occasion_crm WHERE sent=1").fetchone()[0]

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Confirmed Bookings", total_conf)
            k2.metric("Cancellations", total_cancel)
            cancel_rate = f"{total_cancel/(total_conf+total_cancel)*100:.1f}%" if (total_conf+total_cancel) else "0%"
            k3.metric("Cancellation Rate", cancel_rate)
            k4.metric("Search Failures (all time)", total_fails)
            k5.metric("CRM Follow-ups Pending", crm_pending)

            st.markdown("---")

            # ── Bookings per cuisine ─────────────────────────────────────────────
            st.markdown("##### Bookings by Cuisine")
            cuisine_rows = conn.execute("""
                SELECT b.cuisine, COUNT(*) AS bookings
                FROM reservations r JOIN branches b ON r.branch_id = b.id
                WHERE r.status = 'confirmed'
                GROUP BY b.cuisine ORDER BY bookings DESC
            """).fetchall()
            if cuisine_rows:
                df_cuisine = pd.DataFrame([dict(r) for r in cuisine_rows])
                st.bar_chart(df_cuisine.set_index("cuisine")["bookings"])
            else:
                st.info("No confirmed bookings yet.")

            st.markdown("---")

            # ── Top 10 branches ──────────────────────────────────────────────────
            st.markdown("##### Top 10 Branches by Confirmed Bookings")
            branch_rows = conn.execute("""
                SELECT b.name, b.neighborhood, b.cuisine, COUNT(*) AS bookings
                FROM reservations r JOIN branches b ON r.branch_id = b.id
                WHERE r.status = 'confirmed'
                GROUP BY r.branch_id ORDER BY bookings DESC LIMIT 10
            """).fetchall()
            if branch_rows:
                df_top = pd.DataFrame([dict(r) for r in branch_rows])
                st.dataframe(df_top, use_container_width=True, hide_index=True)
            else:
                st.info("No confirmed bookings yet.")

            st.markdown("---")

            # ── Recent search failures ────────────────────────────────────────────
            st.markdown("##### Recent Search Failures (last 30)")
            fail_rows = conn.execute("""
                SELECT query, cuisine, neighborhood, reason, created_at
                FROM search_failures ORDER BY created_at DESC LIMIT 30
            """).fetchall()
            if fail_rows:
                df_fail = pd.DataFrame([dict(r) for r in fail_rows])
                st.dataframe(df_fail, use_container_width=True, hide_index=True)
            else:
                st.success("No search failures recorded.")

            st.markdown("---")

            # ── CRM pipeline ─────────────────────────────────────────────────────
            st.markdown("##### Occasion CRM Pipeline")
            crm_rows = conn.execute("""
                SELECT user_name, user_email, occasion, branch_name,
                       followup_date, CASE WHEN sent=1 THEN 'Sent' ELSE 'Pending' END AS status
                FROM occasion_crm ORDER BY followup_date DESC LIMIT 40
            """).fetchall()
            if crm_rows:
                df_crm = pd.DataFrame([dict(r) for r in crm_rows])
                st.dataframe(df_crm, use_container_width=True, hide_index=True)
            else:
                st.info("No occasion CRM records yet.")

            conn.close()
        except Exception as exc:
            st.error(f"Analytics error: {exc}")

    # ── Agent Traces sub-tab ───────────────────────────────────────────────────────
    with adm5:
        st.markdown("#### Agent Traces")
        st.caption("Step-by-step log of every tool call, result, and LLM decision — one row per agentic event.")

        try:
            conn = get_db()

            # ── Session picker ────────────────────────────────────────────────────
            sessions = conn.execute("""
                SELECT DISTINCT t.session_id,
                       MIN(t.created_at) AS first_event,
                       MAX(t.created_at) AS last_event,
                       COUNT(*)          AS total_steps,
                       cs.guest_name, cs.guest_email
                FROM agent_traces t
                LEFT JOIN chat_sessions cs ON cs.session_id = t.session_id
                GROUP BY t.session_id
                ORDER BY last_event DESC
                LIMIT 50
            """).fetchall()

            if not sessions:
                st.info("No agent traces recorded yet. Start a conversation in the Concierge tab.")
                conn.close()
            else:
                session_labels = {
                    row["session_id"]: (
                        f"{row['guest_name'] or 'Guest'} "
                        f"({'  ' + row['guest_email'] if row['guest_email'] else 'unknown email'}) "
                        f"· {row['total_steps']} steps · {row['last_event'][:16]}"
                    )
                    for row in sessions
                }
                selected_sid = st.selectbox(
                    "Select session",
                    options=list(session_labels.keys()),
                    format_func=lambda s: session_labels[s],
                    key="trace_session_picker"
                )

                st.markdown("---")

                # ── Turns for selected session ────────────────────────────────────
                turns = conn.execute("""
                    SELECT DISTINCT turn_id, MIN(created_at) AS turn_start
                    FROM agent_traces
                    WHERE session_id = ?
                    GROUP BY turn_id
                    ORDER BY turn_start ASC
                """, (selected_sid,)).fetchall()

                for t_idx, turn in enumerate(turns):
                    tid   = turn["turn_id"]
                    ttime = turn["turn_start"][:19].replace("T", " ")

                    steps = conn.execute("""
                        SELECT step, event_type, tool_name, arguments, result, created_at
                        FROM agent_traces
                        WHERE session_id = ? AND turn_id = ?
                        ORDER BY step ASC
                    """, (selected_sid, tid)).fetchall()

                    # Count tool calls in this turn for the summary line
                    tool_calls = [s for s in steps if s["event_type"] == "tool_call"]
                    tools_used = ", ".join(dict.fromkeys(s["tool_name"] for s in tool_calls)) or "—"
                    outcome    = next((s for s in reversed(steps) if s["event_type"] == "llm_stop"), None)

                    label = f"**Turn {t_idx + 1}** · {ttime} · tools: `{tools_used}`"
                    with st.expander(label, expanded=(t_idx == len(turns) - 1)):
                        for s in steps:
                            etype = s["event_type"]

                            if etype == "tool_call":
                                st.markdown(f"**🔧 Step {s['step']} — tool call: `{s['tool_name']}`**")
                                try:
                                    args_pretty = json.dumps(json.loads(s["arguments"]), indent=2) if s["arguments"] else "—"
                                except Exception:
                                    args_pretty = s["arguments"] or "—"
                                st.code(args_pretty, language="json")

                            elif etype == "tool_result":
                                st.markdown(f"**📥 Step {s['step']} — result: `{s['tool_name']}`**")
                                try:
                                    res_pretty = json.dumps(json.loads(s["result"]), indent=2) if s["result"] else "—"
                                except Exception:
                                    res_pretty = s["result"] or "—"
                                st.code(res_pretty, language="json")

                            elif etype == "llm_stop":
                                st.markdown(f"**✅ Step {s['step']} — LLM final response**")
                                st.markdown(f"> {s['result'] or '—'}")

                            elif etype == "error":
                                st.markdown(f"**❌ Step {s['step']} — error: `{s['tool_name']}`**")
                                st.error(s["result"] or "Unknown error")

                            st.markdown("<hr style='margin:4px 0;border-color:#f0f0f0'>", unsafe_allow_html=True)

            conn.close()
        except Exception as exc:
            st.error(f"Agent traces error: {exc}")
