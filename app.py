import os, uuid, re, math, json, random, sys
import datetime as _dt_d
from collections import defaultdict
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="GoodFoods", page_icon="🍽️", layout="wide", initial_sidebar_state="expanded")

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
                    GROQ_API_KEYS)
from agent.loop import run_agent
from tools.search_branches import haversine
from tools.check_availability import get_branch_slots, time_to_minutes as _t2m

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
    return True

_bootstrap()

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Sidebar */
[data-testid="stSidebar"] { background: #111827; border-right: 1px solid #1f2937; }
[data-testid="stSidebar"] * { color: #e5e7eb !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label { color: #9ca3af !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.05em; }
[data-testid="stSidebar"] .stButton > button {
    background: #1f2937; border: 1px solid #374151; color: #d1d5db !important;
    border-radius: 6px; font-size: 12px; text-align: left; padding: 6px 10px;
    width: 100%; margin: 1px 0; transition: all 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover { background: #dc2626; border-color: #dc2626; color: #fff !important; }
[data-testid="stSidebar"] .stMetric { background: #1f2937; border-radius: 8px; padding: 8px; margin: 2px; }
[data-testid="stSidebar"] [data-testid="metric-container"] { background: #1f2937; border-radius: 6px; padding: 8px; }

/* Main area */
.main .block-container { padding-top: 1rem; max-width: 1200px; }

/* Header */
.gf-header { display: flex; align-items: center; gap: 12px; padding: 0 0 16px 0; border-bottom: 2px solid #f3f4f6; margin-bottom: 20px; }
.gf-logo { width: 36px; height: 36px; background: #dc2626; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 16px; }
.gf-title { font-size: 20px; font-weight: 700; color: #111827; letter-spacing: -0.02em; }
.gf-subtitle { font-size: 12px; color: #6b7280; font-weight: 400; }

/* Tab styling */
[data-testid="stTabs"] button { font-size: 13px; font-weight: 500; color: #6b7280; padding: 8px 16px; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #dc2626; border-bottom-color: #dc2626; }

/* Chat messages */
[data-testid="stChatMessage"] { border-radius: 10px; margin: 4px 0; }

/* Branch card */
.branch-card {
    background: white; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 16px; margin-bottom: 12px; position: relative;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: box-shadow 0.2s;
}
.branch-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.branch-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.branch-name { font-size: 15px; font-weight: 600; color: #111827; }
.branch-code { font-size: 11px; color: #9ca3af; font-weight: 500; margin-top: 2px; }
.branch-score { background: #dc2626; color: white; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 20px; }
.branch-meta { display: flex; gap: 12px; font-size: 12px; color: #4b5563; margin: 8px 0; flex-wrap: wrap; align-items: center; }
.branch-meta span { display: flex; align-items: center; gap: 4px; }
.branch-dist { color: #dc2626; font-weight: 600; }
.badge { display: inline-block; font-size: 10px; font-weight: 500; padding: 2px 7px; border-radius: 4px; margin: 2px 2px 2px 0; }
.badge-veg  { background: #d1fae5; color: #065f46; }
.badge-vegan{ background: #a7f3d0; color: #064e3b; }
.badge-gf   { background: #fef3c7; color: #92400e; }
.badge-halal{ background: #dbeafe; color: #1e40af; }
.badge-kosh { background: #ede9fe; color: #5b21b6; }
.badge-park { background: #f3f4f6; color: #374151; }
.badge-out  { background: #ecfdf5; color: #065f46; }
.dish-list { font-size: 12px; color: #374151; margin-top: 8px; border-top: 1px solid #f3f4f6; padding-top: 8px; }
.dish-list strong { color: #6b7280; font-weight: 500; }
.dish-item { display: inline-block; margin-right: 10px; }
.dish-price { color: #dc2626; font-weight: 600; }

/* Reservation confirm card */
.confirm-card {
    background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
    border-radius: 12px; padding: 20px; color: white; margin: 12px 0;
}
.confirm-ref { font-size: 22px; font-weight: 700; letter-spacing: 0.05em; font-family: monospace; }
.confirm-detail { font-size: 13px; opacity: 0.9; margin-top: 4px; }

/* Location grid */
.loc-card {
    background: white; border: 1px solid #e5e7eb; border-radius: 10px;
    padding: 14px; margin-bottom: 10px; height: 100%;
}
.loc-cuisine-tag { display: inline-block; font-size: 10px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em; padding: 3px 8px;
    border-radius: 4px; margin-bottom: 8px; background: #fee2e2; color: #dc2626; }
.loc-name { font-size: 14px; font-weight: 600; color: #111827; line-height: 1.3; }
.loc-meta { font-size: 11px; color: #6b7280; margin-top: 6px; }
.star { color: #f59e0b; }

/* Menu table */
.menu-cat { font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.07em; color: #6b7280; margin: 14px 0 6px; }
.menu-row { display: flex; justify-content: space-between; align-items: baseline;
    padding: 6px 0; border-bottom: 1px solid #f9fafb; font-size: 13px; }
.menu-row:last-child { border-bottom: none; }
.menu-item-name { color: #1f2937; font-weight: 500; }
.menu-item-desc { color: #9ca3af; font-size: 11px; }
.menu-item-price { color: #dc2626; font-weight: 600; white-space: nowrap; margin-left: 12px; }
.popular-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #f59e0b; margin-right: 5px; vertical-align: middle; }

/* Info strip */
.info-strip { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: #374151; }

/* Live Dashboard */
.dash-kpi { background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; text-align: center; }
.dash-kpi-value { font-size: 28px; font-weight: 700; color: #111827; letter-spacing: -0.03em; }
.dash-kpi-label { font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }
.dash-kpi-sub { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.slot-badge { display:inline-flex; flex-direction:column; align-items:center; border-radius:7px; padding:5px 5px; margin:2px; min-width:52px; font-size:10px; font-weight:600; cursor:default; border:1px solid rgba(0,0,0,.06); }
.slot-badge .st { font-size:10px; font-weight:700; }
.slot-badge .sc { font-size:9px; font-weight:400; margin-top:1px; opacity:.85; }
.branch-dash-card { background:white; border:1px solid #e5e7eb; border-radius:12px; padding:16px; margin-bottom:10px; }
.branch-dash-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
.branch-dash-name { font-size:14px; font-weight:600; color:#111827; }
.branch-dash-meta { font-size:11px; color:#6b7280; margin-top:2px; }
.branch-dash-stats { display:flex; gap:12px; font-size:12px; }
.res-row { display:flex; gap:10px; align-items:center; padding:6px 10px; border-radius:6px; background:#f9fafb; margin:3px 0; font-size:12px; flex-wrap:wrap; }
.res-ref { font-family:monospace; color:#dc2626; font-weight:700; font-size:11px; min-width:88px; }
.res-guest { color:#111827; font-weight:600; flex:1; min-width:100px; }
.res-detail { color:#6b7280; }
.res-badge { display:inline-block; background:#fee2e2; color:#dc2626; font-size:10px; padding:1px 6px; border-radius:4px; font-weight:600; }
.legend-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; font-size:11px; color:#6b7280; }
.legend-item { display:flex; align-items:center; gap:4px; }
.legend-dot { width:12px; height:12px; border-radius:3px; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

if "agent_history"          not in st.session_state: st.session_state.agent_history = []
if "display_messages"       not in st.session_state: st.session_state.display_messages = []
if "session_id"             not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "booking_refs"           not in st.session_state: st.session_state.booking_refs = []
if "branch_results"         not in st.session_state: st.session_state.branch_results = []
if "last_reservation"       not in st.session_state: st.session_state.last_reservation = None
if "last_experience_package" not in st.session_state: st.session_state.last_experience_package = None
if "_inject"                not in st.session_state: st.session_state._inject = None
if "user_lat"               not in st.session_state: st.session_state.user_lat = None
if "user_lon"               not in st.session_state: st.session_state.user_lon = None
if "user_location_name"     not in st.session_state: st.session_state.user_location_name = None
# Guest identity — populated once get_user_profile returns a hit
if "guest_name"             not in st.session_state: st.session_state.guest_name = None
if "guest_email"            not in st.session_state: st.session_state.guest_email = None
if "guest_phone"            not in st.session_state: st.session_state.guest_phone = None
if "guest_total_visits"     not in st.session_state: st.session_state.guest_total_visits = 0
if "dash_show_pii"          not in st.session_state: st.session_state.dash_show_pii = False

CUISINES = ["Italian","Indian","Mexican","Japanese","Chinese","Mediterranean",
            "Thai","American","French","Korean","Middle Eastern","Vietnamese"]
NEIGHBORHOODS = list(NEIGHBORHOOD_COORDS.keys())
PRICE_LABELS = {1: "$  Budget", 2: "$$  Moderate", 3: "$$$  Upscale", 4: "$$$$  Fine Dining"}

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
    return "$"*pr + "<span style='color:#d1d5db'>"+"$"*(4-pr)+"</span>"

def _dietary_badges(b):
    parts=[]
    if b.get("dietary_vegetarian"): parts.append('<span class="badge badge-veg">Vegetarian</span>')
    if b.get("dietary_vegan"):      parts.append('<span class="badge badge-vegan">Vegan</span>')
    if b.get("dietary_gluten_free"):parts.append('<span class="badge badge-gf">Gluten-Free</span>')
    if b.get("dietary_halal"):      parts.append('<span class="badge badge-halal">Halal</span>')
    if b.get("dietary_kosher"):     parts.append('<span class="badge badge-kosh">Kosher</span>')
    if b.get("parking"):            parts.append('<span class="badge badge-park">Parking</span>')
    if b.get("outdoor_seating"):    parts.append('<span class="badge badge-out">Outdoor</span>')
    return " ".join(parts)

def _branch_card_html(b, show_score=True):
    dist_html = ""
    if b.get("distance_km") is not None:
        dist_html = f'<span class="branch-dist">📍 {b["distance_km"]:.1f} km</span>'
    elif st.session_state.user_lat and b.get("latitude"):
        d = haversine(st.session_state.user_lat, st.session_state.user_lon, b["latitude"], b["longitude"])
        dist_html = f'<span class="branch-dist">📍 {d:.1f} km</span>'

    score_html = f'<span class="branch-score">{b.get("match_score",0):.0f} pts</span>' if show_score else ""

    dishes = ""
    if b.get("menu_highlights"):
        items = "  ·  ".join(
            f'<span class="dish-item">{m["name"]} <span class="dish-price">${m["price"]:.0f}</span></span>'
            for m in b["menu_highlights"]
        )
        dishes = f'<div class="dish-list"><strong>Popular dishes: </strong>{items}</div>'

    return f"""
<div class="branch-card">
  <div class="branch-card-header">
    <div>
      <div class="branch-name">{b["name"]}</div>
      <div class="branch-code">{b.get("branch_code","")}{" · " + b.get("address","") if b.get("address") else ""}</div>
    </div>
    {score_html}
  </div>
  <div class="branch-meta">
    {dist_html}
    <span>⭐ {b["rating"]:.1f} <span style="color:#9ca3af">({b.get("review_count",0)} reviews)</span></span>
    <span>{_price_dots(b.get("price_range",2))}</span>
    <span>🪑 {b["capacity"]} seats</span>
    <span>🕐 {b.get("opening_time","11:00")}–{b.get("closing_time","22:30")}</span>
    {f'<span>📞 {b["phone"]}</span>' if b.get("phone") else ""}
  </div>
  <div>{_dietary_badges(b)}</div>
  {dishes}
</div>"""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 8px">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:32px;height:32px;background:#dc2626;border-radius:7px;
             display:flex;align-items:center;justify-content:center;
             font-weight:700;font-size:15px;color:white">G</div>
        <div>
          <div style="font-weight:700;font-size:15px;letter-spacing:-0.02em">GoodFoods</div>
          <div style="font-size:10px;color:#6b7280">Reservation System</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    st.divider()

    # Location selector
    st.markdown('<p style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:4px">Your Location</p>', unsafe_allow_html=True)
    hood_choice = st.selectbox("Your neighbourhood", ["— Not set —"] + NEIGHBORHOODS, label_visibility="collapsed", key="loc_select")
    if hood_choice != "— Not set —":
        lat, lon = NEIGHBORHOOD_COORDS[hood_choice]
        st.session_state.user_lat = lat
        st.session_state.user_lon = lon
        st.session_state.user_location_name = hood_choice
        st.markdown(f'<p style="font-size:11px;color:#6b7280;margin-top:-8px">📍 {hood_choice} · {lat:.4f}°N, {abs(lon):.4f}°W</p>', unsafe_allow_html=True)
    else:
        st.session_state.user_lat = None
        st.session_state.user_lon = None
        st.session_state.user_location_name = None

    st.divider()

    # Returning guest banner
    if st.session_state.guest_name:
        visits = st.session_state.guest_total_visits
        st.markdown(
            f'<div style="background:#1f2937;border:1px solid #374151;border-radius:8px;'
            f'padding:10px 12px;margin-bottom:8px">'
            f'<div style="font-size:10px;text-transform:uppercase;letter-spacing:.07em;'
            f'color:#f59e0b;font-weight:700;margin-bottom:3px">👋 Returning Guest</div>'
            f'<div style="font-size:13px;font-weight:600;color:#f3f4f6">{st.session_state.guest_name}</div>'
            f'<div style="font-size:11px;color:#9ca3af">{st.session_state.guest_email}</div>'
            f'<div style="font-size:10px;color:#6b7280;margin-top:2px">'
            f'{visits} previous visit{"s" if visits != 1 else ""}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Metrics
    tot, act, mis = _db_metrics()
    col1, col2 = st.columns(2)
    col1.metric("Locations", act)
    col2.metric("Bookings", tot)
    col1.metric("Missed Today", mis)

    st.divider()

    # Quick prompts
    st.markdown('<p style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:6px">Quick Prompts</p>', unsafe_allow_html=True)
    SAMPLES = [
        "Find an Italian spot in Downtown for 4 this Saturday at 7pm",
        "Book our anniversary — French, 2 people, next Friday evening",
        "What's on the menu at your Japanese locations?",
        "I need a halal restaurant for 8 people this weekend",
        "Business dinner for 12, Financial District, under Apex Consulting",
    ]
    for s in SAMPLES:
        label = (s[:45]+"…") if len(s)>45 else s
        if st.button(label, use_container_width=True, key=f"q_{s[:15]}"):
            st.session_state._inject = s
            st.rerun()

    st.divider()

    # Recent bookings
    recents = _recent_reservations()
    if recents:
        st.markdown('<p style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9ca3af;margin-bottom:6px">Recent Bookings</p>', unsafe_allow_html=True)
        for r in recents:
            icon = "●" if r["status"]=="confirmed" else "○"
            color = "#22c55e" if r["status"]=="confirmed" else "#ef4444"
            st.markdown(
                f'<div style="font-size:11px;padding:3px 0;color:#d1d5db">'
                f'<span style="color:{color}">{icon}</span> '
                f'<code style="font-size:10px;color:#f59e0b">{r["reference_number"]}</code> '
                f'{r["date"]} {r["time"]} · {r["party_size"]}pax</div>',
                unsafe_allow_html=True
            )

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        for k in ("agent_history", "display_messages", "booking_refs", "branch_results"):
            st.session_state[k] = []
        for k in ("last_reservation", "last_experience_package"):
            st.session_state[k] = None
        for k in ("guest_name", "guest_email", "guest_phone"):
            st.session_state[k] = None
        st.session_state.guest_total_visits = 0
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_locations, tab_dashboard, tab_admin = st.tabs(["💬  Concierge", "🗺️  Our Locations", "📊  Live Dashboard", "⚙️  Admin"])

# ════════════════════════════════════════════════════════════════
# CONCIERGE TAB
# ════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("""
    <div class="gf-header">
      <div class="gf-logo">G</div>
      <div>
        <div class="gf-title">Sage — GoodFoods Concierge</div>
        <div class="gf-subtitle">Your private dining assistant across all 75 GoodFoods locations</div>
      </div>
    </div>""", unsafe_allow_html=True)

    if st.session_state.user_location_name:
        st.markdown(
            f'<div class="info-strip">📍 Searching from <strong>{st.session_state.user_location_name}</strong> — '
            f'distances to each GoodFoods location are calculated in real time.</div>',
            unsafe_allow_html=True
        )

    chat_col, panel_col = st.columns([3, 2])

    with chat_col:
        if not st.session_state.display_messages:
            st.markdown("""
            <div style="text-align:center;padding:36px 20px 28px;color:#6b7280">
              <div style="font-size:44px;margin-bottom:14px">🍽️</div>
              <div style="font-size:17px;font-weight:700;color:#111827;margin-bottom:6px">
                Welcome to GoodFoods</div>
              <div style="font-size:13px;line-height:1.7;color:#6b7280">
                I'm <strong style="color:#dc2626">Sage</strong>, your personal dining concierge.<br>
                Tell me what you're in the mood for and I'll find<br>
                the perfect table across our 75 NYC locations.
              </div>
              <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:18px">
                <span style="background:#fee2e2;color:#dc2626;font-size:11px;font-weight:600;
                      padding:4px 10px;border-radius:20px">🔍 Find a restaurant</span>
                <span style="background:#f0fdf4;color:#15803d;font-size:11px;font-weight:600;
                      padding:4px 10px;border-radius:20px">📅 Make a reservation</span>
                <span style="background:#eff6ff;color:#1d4ed8;font-size:11px;font-weight:600;
                      padding:4px 10px;border-radius:20px">🍜 Browse menus</span>
                <span style="background:#faf5ff;color:#7e22ce;font-size:11px;font-weight:600;
                      padding:4px 10px;border-radius:20px">✨ Plan an occasion</span>
              </div>
            </div>""", unsafe_allow_html=True)

        for msg in st.session_state.display_messages:
            with st.chat_message(msg["role"], avatar="👤" if msg["role"]=="user" else "🍽️"):
                st.markdown(msg["content"])

        inject = st.session_state._inject
        st.session_state._inject = None
        prompt = st.chat_input("Ask about locations, menus, availability…") or inject

        if prompt:
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            st.session_state.display_messages.append({"role":"user","content":prompt})

            # Build user context: location + identified guest
            ctx_parts = []
            if st.session_state.user_lat:
                ctx_parts.append(
                    f"[Guest location: {st.session_state.user_location_name} "
                    f"(lat={st.session_state.user_lat:.4f}, lon={st.session_state.user_lon:.4f}). "
                    f"Always pass these coordinates in search_branches calls so distance is shown.]"
                )
            if st.session_state.guest_email:
                ctx_parts.append(
                    f"[IDENTIFIED GUEST: name={st.session_state.guest_name}, "
                    f"email={st.session_state.guest_email}, "
                    f"phone={st.session_state.guest_phone}. "
                    f"Profile already loaded — do NOT ask for name or phone again unless the guest wants to change them.]"
                )
            user_context = " ".join(ctx_parts) if ctx_parts else None

            # Persist the user message
            save_message(st.session_state.session_id, "user", prompt)

            with st.spinner("Sage is thinking…"):
                try:
                    response, new_history, side_effects = run_agent(
                        prompt,
                        st.session_state.agent_history,
                        st.session_state.session_id,
                        user_context,
                        existing_refs=st.session_state.booking_refs or None,
                    )
                    st.session_state.agent_history = new_history

                    if side_effects["branch_results"]:
                        st.session_state.branch_results = side_effects["branch_results"]

                    if side_effects["reservation"]:
                        st.session_state.last_reservation = side_effects["reservation"]
                        ref = side_effects["reservation"].get("reference_number")
                        if ref and ref not in st.session_state.booking_refs:
                            st.session_state.booking_refs.append(ref)

                    if side_effects.get("experience_package"):
                        st.session_state.last_experience_package = side_effects["experience_package"]

                    # Cache guest identity when a profile is found
                    if side_effects.get("user_profile"):
                        prof = side_effects["user_profile"]
                        st.session_state.guest_name  = prof.get("name") or st.session_state.guest_name
                        st.session_state.guest_email = prof.get("email") or st.session_state.guest_email
                        st.session_state.guest_phone = prof.get("phone") or st.session_state.guest_phone
                        st.session_state.guest_total_visits = prof.get("total_reservations", 0)
                        update_session_guest(
                            st.session_state.session_id,
                            email=st.session_state.guest_email,
                            name=st.session_state.guest_name,
                            phone=st.session_state.guest_phone,
                        )

                except Exception as e:
                    response = f"Something went wrong — please try again. *(Error: {e})*"
                    side_effects = {"branch_results": [], "reservation": None, "user_profile": None, "experience_package": None}

            # Persist the assistant response
            save_message(st.session_state.session_id, "assistant", response)

            with st.chat_message("assistant", avatar="🍽️"):
                st.markdown(response)
            st.session_state.display_messages.append({"role":"assistant","content":response})
            st.rerun()

    with panel_col:
        # ── Reservation confirmation card ──────────────────────────────────────
        if st.session_state.last_reservation:
            res        = st.session_state.last_reservation
            guest_name = res.get("user_name") or st.session_state.guest_name or ""
            party      = res.get("party_size", 1)
            ref        = res.get("reference_number", "")

            st.markdown(f"""
            <div class="confirm-card">
              <div style="font-size:11px;opacity:.7;text-transform:uppercase;
                   letter-spacing:.08em;margin-bottom:4px">Booking Confirmed ✓</div>
              <div class="confirm-ref">{ref}</div>
              {f'<div class="confirm-detail" style="margin-top:10px">👤 {guest_name}</div>' if guest_name else '<div style="margin-top:10px"></div>'}
              <div class="confirm-detail">📍 {res.get("branch_name","")}</div>
              <div class="confirm-detail">📅 {res.get("date","")} &nbsp; 🕐 {res.get("time","")}</div>
              <div class="confirm-detail">👥 {party} guest{"s" if party != 1 else ""}</div>
            </div>""", unsafe_allow_html=True)

            # Quick-action buttons
            qa1, qa2, qa3 = st.columns(3)
            if qa1.button("✏️ Modify", key="qa_mod", use_container_width=True):
                st.session_state._inject = f"I'd like to modify my booking {ref}"
                st.rerun()
            if qa2.button("🔍 Details", key="qa_det", use_container_width=True):
                st.session_state._inject = f"Can you show me the full details for {ref}?"
                st.rerun()
            if qa3.button("✕ Cancel", key="qa_can", use_container_width=True):
                st.session_state._inject = f"I need to cancel booking {ref}"
                st.rerun()

            # Session multi-booking summary
            if len(st.session_state.booking_refs) > 1:
                st.markdown('<p style="font-size:10px;text-transform:uppercase;'
                            'letter-spacing:.07em;color:#9ca3af;margin:12px 0 4px">This Session</p>',
                            unsafe_allow_html=True)
                for r in st.session_state.booking_refs:
                    dot_color = "#22c55e" if r == ref else "#9ca3af"
                    st.markdown(
                        f'<div style="font-size:11px;padding:2px 0;color:#374151">'
                        f'<span style="color:{dot_color}">●</span> '
                        f'<code style="font-size:11px">{r}</code></div>',
                        unsafe_allow_html=True,
                    )

        # ── Experience package card ────────────────────────────────────────────
        if st.session_state.last_experience_package:
            pkg     = st.session_state.last_experience_package
            p       = pkg.get("package", {})
            inc     = p.get("includes", [])
            extras  = p.get("extras", "")
            occasion = pkg.get("occasion", "")
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#7c3aed 0%,#4c1d95 100%);
                 border-radius:12px;padding:16px;color:white;margin:10px 0">
              <div style="font-size:10px;opacity:.7;text-transform:uppercase;
                   letter-spacing:.08em;margin-bottom:4px">Experience Package</div>
              <div style="font-size:15px;font-weight:700;margin-bottom:8px;
                   text-transform:capitalize">{occasion} ✨</div>
              {''.join(f'<div style="font-size:12px;opacity:.9;margin:2px 0">✓ {item}</div>' for item in inc)}
              {f'<div style="font-size:11px;opacity:.7;margin-top:8px;font-style:italic">{extras}</div>' if extras else ''}
            </div>""", unsafe_allow_html=True)

        # ── Branch recommendation cards ────────────────────────────────────────
        if st.session_state.branch_results:
            st.markdown('<p style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;'
                        'color:#9ca3af;margin-bottom:8px">Recommended Locations</p>',
                        unsafe_allow_html=True)
            for b in st.session_state.branch_results:
                st.markdown(_branch_card_html(b), unsafe_allow_html=True)
        elif not st.session_state.last_reservation:
            st.markdown("""
            <div style="padding:30px 16px;text-align:center;color:#9ca3af;
                 border:1px dashed #e5e7eb;border-radius:10px">
              <div style="font-size:24px;margin-bottom:8px">🗺️</div>
              <div style="font-size:12px">Recommended GoodFoods locations<br>will appear here when you search.</div>
            </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# LOCATIONS TAB
# ════════════════════════════════════════════════════════════════
with tab_locations:
    st.markdown("### Our 75 GoodFoods Locations")

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
                dist_str = f'<span style="color:#dc2626;font-weight:600">📍 {b["_dist"]:.1f} km</span>  · '
            dietary_str = _dietary_badges(b)
            price_str = "$" * b.get("price_range", 2)

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
                  🪑 {b['capacity']} seats &nbsp; 🕐 {b.get('opening_time','11:00')}–{b.get('closing_time','22:30')}
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
                              <div class="menu-item-price">${it['price']:.2f}</div>
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
    adm1, adm2, adm3, adm4, adm5 = st.tabs(["All Branches", "Add Location", "Edit Location", "Analytics", "🔍 Agent Traces"])

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
                c2.write(f"**Price:** {'$'*b.get('price_range',2)}")
                c2.write(f"**Hours:** {b.get('opening_time','11:00')}–{b.get('closing_time','22:30')}")
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
        st.markdown("#### Add a New GoodFoods Location")
        with st.form("add_form", clear_on_submit=True):
            c1,c2 = st.columns(2)
            new_hood = c1.selectbox("Neighbourhood *", NEIGHBORHOODS)
            new_cui  = c2.selectbox("Cuisine *", CUISINES)
            from scripts.seed_data import CUISINE_LABEL
            auto_name = f"GoodFoods {new_hood} — {CUISINE_LABEL.get(new_cui, new_cui)}"
            new_name = st.text_input("Branch Name", value=auto_name)
            new_addr = st.text_input("Street Address", placeholder="123 Main St, Downtown")
            new_phone= st.text_input("Phone", placeholder="+1 (212) 555-0000")

            c3,c4,c5 = st.columns(3)
            new_cap  = c3.number_input("Capacity (seats)", 10, 500, 60, 10)
            new_rat  = c4.slider("Initial Rating", 3.8, 5.0, 4.2, 0.1)
            new_pr   = c5.select_slider("Price Range", [1,2,3,4], 2, format_func=lambda x:"$"*x)

            c6,c7 = st.columns(2)
            new_open = c6.text_input("Opens", "11:00")
            new_clos = c7.text_input("Closes", "22:30")

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
                (branch_code,name,neighborhood,address,latitude,longitude,capacity,tables,cuisine,
                 rating,review_count,price_range,dietary_vegetarian,dietary_vegan,dietary_gluten_free,
                 dietary_halal,dietary_kosher,parking,outdoor_seating,valet,is_active,
                 opening_time,closing_time,phone,description)
                VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
                (code,new_name,new_hood,new_addr or None,lat,lon,new_cap,new_cap//4,new_cui,
                 new_rat,new_pr,int(nv),int(nvegan),int(ngf),int(nhal),int(nkos),
                 int(npark),int(nout),int(nval),new_open,new_clos,new_phone or None,new_desc or None))
            # Seed menu items for new branch from template
            from scripts.seed_data import MENUS
            price_factor = {1:0.8,2:1.0,3:1.2,4:1.5}.get(new_pr,1.0)
            branch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for item in MENUS.get(new_cui,[]):
                nm,desc,cat,bp,veg,vegan,gf,halal,pop,cal = item
                conn.execute("""INSERT INTO menu_items
                    (branch_id,name,description,category,price,is_available,is_vegetarian,
                     is_vegan,is_gluten_free,is_halal,is_popular,calories)
                    VALUES(?,?,?,?,?,1,?,?,?,?,?,?)""",
                    (branch_id,nm,desc,cat,round(bp*price_factor,2),int(veg),int(vegan),int(gf),int(halal),int(pop),cal))
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
            epr  = c5.select_slider("Price", [1,2,3,4], int(b.get("price_range") or 2), format_func=lambda x:"$"*x)
            c6,c7 = st.columns(2)
            eopen= c6.text_input("Opens", b.get("opening_time","11:00"))
            eclos= c7.text_input("Closes", b.get("closing_time","22:30"))
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
