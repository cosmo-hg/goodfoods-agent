import os
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _st_secret(key: str) -> str:
    """Read a secret from Streamlit Cloud secrets, silently returning '' if unavailable."""
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        return ""


def _load_api_keys() -> list:
    """
    Collect every configured Groq key in declaration order.
    Reads from environment variables first (local .env),
    then falls back to Streamlit Cloud secrets for cloud deployments.
      GROQ_API_KEY   — primary (required)
      GROQ_API_KEY_2 — first fallback  (optional)
      GROQ_API_KEY_3 — second fallback (optional)
      … up to GROQ_API_KEY_5
    """
    keys = []
    for suffix in ["", "_2", "_3", "_4", "_5"]:
        env_key = f"GROQ_API_KEY{suffix}"
        val = (os.environ.get(env_key, "") or _st_secret(env_key)).strip()
        if val:
            keys.append(val)
    return keys


GROQ_API_KEYS = _load_api_keys()
GROQ_API_KEY  = GROQ_API_KEYS[0] if GROQ_API_KEYS else None   # backward-compat alias

# NOTE: We deliberately do NOT raise here at import time.
# On Streamlit Cloud the secrets are injected after the module is first parsed,
# so a hard raise would crash the process before st.secrets is accessible.
# app.py validates GROQ_API_KEYS after Streamlit is fully initialised.

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Why llama-3.3-70b-versatile: it's Groq's strongest free-tier model for the
# specific shape of our workload — agentic tool calling with short, grounded
# replies. The 8B-instant was faster but routinely fabricated tool args,
# misclassified intent, and emitted clumsy prose ("We don't operate in
# 'Italian for dinner saturday'"). 70B fixes all three. Same 6 000 TPM budget;
# latency goes from ~1s to ~2-3s per turn, which is fine for a concierge.
MODEL = "llama-3.3-70b-versatile"
TEMPERATURE = 0.3

BASE_DIR = Path(__file__).parent
DB_PATH = str(BASE_DIR / "data" / "goodfoods.db")

# Real Bangalore neighbourhood centroids (approximate; from public map data).
# These are the areas GoodFoods serves. The agent must refuse anything outside
# this list as "not in our service area" rather than fuzzy-matching.
NEIGHBORHOOD_COORDS = {
    "Indiranagar":        (12.9716, 77.6412),
    "Koramangala":        (12.9352, 77.6245),
    "HSR Layout":         (12.9116, 77.6473),
    "Whitefield":         (12.9698, 77.7500),
    "Marathahalli":       (12.9591, 77.6974),
    "Bellandur":          (12.9259, 77.6762),
    "Sarjapur Road":      (12.9010, 77.6873),
    "JP Nagar":           (12.9081, 77.5831),
    "Jayanagar":          (12.9293, 77.5825),
    "MG Road":            (12.9759, 77.6094),
    "Brigade Road":       (12.9716, 77.6072),
    "Church Street":      (12.9745, 77.6090),
    "Lavelle Road":       (12.9722, 77.5938),
    "UB City":            (12.9716, 77.5946),
    "Ulsoor":             (12.9831, 77.6217),
    "Frazer Town":        (12.9990, 77.6118),
    "Richmond Town":      (12.9598, 77.6029),
    "Domlur":             (12.9608, 77.6386),
    "Old Airport Road":   (12.9577, 77.6664),
    "Malleshwaram":       (13.0035, 77.5709),
    "Rajajinagar":        (12.9866, 77.5547),
    "Hebbal":             (13.0357, 77.5970),
    "Yelahanka":          (13.1007, 77.5963),
    "Kalyan Nagar":       (13.0297, 77.6420),
    "New BEL Road":       (13.0298, 77.5630),
}

# Common aliases / sub-areas that should resolve to one of the served neighbourhoods.
# Used by is_served_area to handle "Koramangala 5th Block", "Indiranagar 100ft Road" etc.
NEIGHBORHOOD_ALIASES = {
    "koramangala 1st block": "Koramangala", "koramangala 4th block": "Koramangala",
    "koramangala 5th block": "Koramangala", "koramangala 6th block": "Koramangala",
    "koramangala 7th block": "Koramangala", "koramangala 8th block": "Koramangala",
    "100 feet road": "Indiranagar", "100ft road": "Indiranagar",
    "cmh road": "Indiranagar", "old madras road": "Indiranagar",
    "hsr": "HSR Layout", "hsr sector 1": "HSR Layout", "hsr sector 2": "HSR Layout",
    "hsr sector 7": "HSR Layout",
    "ecc road": "Whitefield", "itpl": "Whitefield", "phoenix marketcity": "Whitefield",
    "outer ring road": "Marathahalli", "orr": "Marathahalli",
    "marathahalli bridge": "Marathahalli",
    "bellandur lake": "Bellandur", "ecospace": "Bellandur",
    "sarjapur": "Sarjapur Road", "sarjapur main road": "Sarjapur Road",
    "haralur": "Sarjapur Road",
    "jayanagar 4th block": "Jayanagar", "jayanagar 9th block": "Jayanagar",
    "jp nagar phase 1": "JP Nagar", "jp nagar phase 3": "JP Nagar",
    "jp nagar phase 7": "JP Nagar",
    "trinity": "MG Road", "trinity circle": "MG Road",
    "vittal mallya road": "UB City",
    "halasuru": "Ulsoor",
    "manyata tech park": "Hebbal", "manyata": "Hebbal",
    "yelahanka new town": "Yelahanka",
    "kammanahalli": "Kalyan Nagar", "banaswadi": "Kalyan Nagar",
    "mekhri circle": "New BEL Road", "rmv 2nd stage": "New BEL Road",
    "8th main": "Malleshwaram", "sampige road": "Malleshwaram",
    "mg road bangalore": "MG Road", "mg road bengaluru": "MG Road",
}

# City the chain serves. Anything outside is rejected by is_served_area.
SERVED_CITY = "Bangalore"
SERVED_CITY_ALIASES = {"bangalore", "bengaluru", "blr"}


def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _safe_add_column(conn, table: str, column: str, type_decl: str) -> None:
    """
    Idempotent column-add migration. SQLite has no ADD COLUMN IF NOT EXISTS,
    so we read PRAGMA table_info and check before issuing ADD COLUMN.

    This is what lets init_db be safely called on databases created by
    older versions of the schema — the new columns (popularity_score,
    dish_tags, slots_json, etc.) get added without recreating tables.
    """
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_decl}")


def init_db(db_path=None):
    conn = get_db(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_code TEXT UNIQUE,
            name TEXT NOT NULL,
            neighborhood TEXT,
            address TEXT,
            city TEXT DEFAULT 'Bangalore',
            latitude REAL,
            longitude REAL,
            capacity INTEGER,
            tables INTEGER,
            cuisine TEXT,
            rating REAL DEFAULT 4.0,
            review_count INTEGER DEFAULT 0,
            popularity_score REAL DEFAULT 50.0,
            price_range INTEGER DEFAULT 2,
            dietary_vegetarian INTEGER DEFAULT 0,
            dietary_vegan INTEGER DEFAULT 0,
            dietary_gluten_free INTEGER DEFAULT 0,
            dietary_halal INTEGER DEFAULT 0,
            dietary_kosher INTEGER DEFAULT 0,
            parking INTEGER DEFAULT 0,
            outdoor_seating INTEGER DEFAULT 0,
            valet INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            opening_time TEXT DEFAULT '11:00',
            closing_time TEXT DEFAULT '22:30',
            phone TEXT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            price REAL,
            is_available INTEGER DEFAULT 1,
            is_vegetarian INTEGER DEFAULT 0,
            is_vegan INTEGER DEFAULT 0,
            is_gluten_free INTEGER DEFAULT 0,
            is_halal INTEGER DEFAULT 0,
            is_jain INTEGER DEFAULT 0,
            is_popular INTEGER DEFAULT 0,
            calories INTEGER,
            -- Lowercase, comma-separated tags used by search_by_dish.
            -- Examples: "pizza,italian,vegetarian" or "burger,american,beef"
            dish_tags TEXT,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );

        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT UNIQUE NOT NULL,
            branch_id INTEGER,
            user_name TEXT,
            user_email TEXT,
            user_phone TEXT,
            party_size INTEGER,
            date TEXT,
            time TEXT,
            occasion TEXT,
            special_requests TEXT,
            corporate_account_id INTEGER,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            name TEXT,
            phone TEXT,
            preferences TEXT,
            dietary_requirements TEXT,
            total_reservations INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS corporate_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_name TEXT,
            contact_email TEXT,
            account_code TEXT UNIQUE,
            discount_percentage REAL DEFAULT 0,
            preferred_branches TEXT,
            credit_limit REAL DEFAULT 10000,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS search_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            party_size INTEGER,
            date TEXT,
            time TEXT,
            cuisine TEXT,
            neighborhood TEXT,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS occasion_crm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER,
            occasion TEXT,
            followup_date TEXT,
            user_email TEXT,
            user_name TEXT,
            branch_name TEXT,
            sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS dropoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER,
            reservation_id INTEGER,
            slot_date TEXT,
            slot_time TEXT,
            party_size INTEGER,
            notified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS competitor_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT,
            mention_context TEXT,
            session_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            guest_email TEXT,
            guest_name  TEXT,
            guest_phone TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversation_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT NOT NULL,
            occasion TEXT,
            includes TEXT,
            extras TEXT,
            guest_preferences TEXT,
            budget TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reference_number) REFERENCES reservations(reference_number) ON DELETE CASCADE
        );

        -- Agent trace log: every tool call + result + LLM decision, per step
        CREATE TABLE IF NOT EXISTS agent_traces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            turn_id     TEXT NOT NULL,
            step        INTEGER NOT NULL,
            event_type  TEXT NOT NULL,   -- 'tool_call' | 'tool_result' | 'llm_stop' | 'error'
            tool_name   TEXT,
            arguments   TEXT,            -- JSON string
            result      TEXT,            -- JSON string (capped at 2000 chars)
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_traces_session ON agent_traces(session_id, turn_id);

        -- One row per agent turn: the classified intent + the slot delta this
        -- turn produced. Drives intent analytics and lets us spot the slot at
        -- which sessions drop off (e.g. "60% of abandonments are at user_phone").
        CREATE TABLE IF NOT EXISTS agent_turns (
            turn_id      TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            intent       TEXT,            -- BROWSE | BOOK | MODIFY | CANCEL | LOOKUP | MENU | OCCASION | PROFILE_LOOKUP | CORPORATE | CONVERSATION
            slot_delta   TEXT,            -- JSON of {field: new_value} populated this turn
            slots_after  TEXT,            -- JSON snapshot of all slots after the turn
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_turns_session ON agent_turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_turns_intent  ON agent_turns(intent);
    """)

    # ── Idempotent column migrations for older databases ──────────────────────
    # These run on every init_db() but are no-ops once the columns exist. They
    # let users who created a DB from an earlier schema upgrade in place
    # without dropping data.
    _safe_add_column(conn, "branches",        "popularity_score", "REAL DEFAULT 50.0")
    _safe_add_column(conn, "branches",        "city",             "TEXT DEFAULT 'Bangalore'")
    _safe_add_column(conn, "menu_items",      "dish_tags",        "TEXT")
    _safe_add_column(conn, "menu_items",      "is_jain",          "INTEGER DEFAULT 0")
    _safe_add_column(conn, "branches",        "dietary_jain",     "INTEGER DEFAULT 0")
    # Auto-derive branch-level jain flag from menu_items so search can hard-filter.
    conn.execute("""
        UPDATE branches SET dietary_jain = 1
        WHERE id IN (
            SELECT DISTINCT branch_id FROM menu_items WHERE is_jain = 1
        ) AND dietary_jain = 0
    """)

    # Session-persistence columns — survive a page refresh / browser restart.
    # The Streamlit app saves slot state + intent + message history here
    # after each turn and reloads on session resume.
    _safe_add_column(conn, "chat_sessions",   "slots_json",         "TEXT")
    _safe_add_column(conn, "chat_sessions",   "last_intent",        "TEXT")
    _safe_add_column(conn, "chat_sessions",   "agent_history_json", "TEXT")

    # ── Indexes — created AFTER column migrations so they can safely reference
    # popularity_score / dish_tags etc. on legacy databases that didn't have
    # them at first init.
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_res_branch_date    ON reservations(branch_id, date, status);
        CREATE INDEX IF NOT EXISTS idx_res_email          ON reservations(user_email);
        CREATE INDEX IF NOT EXISTS idx_res_ref            ON reservations(reference_number);
        CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);
        CREATE INDEX IF NOT EXISTS idx_sf_created         ON search_failures(created_at);
        CREATE INDEX IF NOT EXISTS idx_crm_followup       ON occasion_crm(followup_date, sent);
        CREATE INDEX IF NOT EXISTS idx_pkg_ref            ON packages(reference_number);
        CREATE INDEX IF NOT EXISTS idx_branch_popularity  ON branches(popularity_score DESC);
        CREATE INDEX IF NOT EXISTS idx_branch_cuisine     ON branches(cuisine, is_active);
        CREATE INDEX IF NOT EXISTS idx_menu_branch        ON menu_items(branch_id, is_available);
    """)

    conn.commit()
    conn.close()


def save_message(session_id, role, content, db_path=None):
    """Persist a single visible chat message (user or assistant) to the DB."""
    if not content or not str(content).strip():
        return
    conn = get_db(db_path)
    # Parent row must exist before the FK-constrained child insert
    conn.execute(
        """INSERT INTO chat_sessions (session_id, last_active)
           VALUES (?, CURRENT_TIMESTAMP)
           ON CONFLICT(session_id) DO UPDATE SET last_active = CURRENT_TIMESTAMP""",
        (session_id,),
    )
    conn.execute(
        "INSERT INTO conversation_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, str(content)[:4000]),
    )
    conn.commit()
    conn.close()


def update_session_guest(session_id, email=None, name=None, phone=None, db_path=None):
    """Store the identified guest's details against this chat session."""
    conn = get_db(db_path)
    conn.execute(
        """INSERT INTO chat_sessions (session_id, guest_email, guest_name, guest_phone)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
               guest_email = COALESCE(excluded.guest_email, guest_email),
               guest_name  = COALESCE(excluded.guest_name,  guest_name),
               guest_phone = COALESCE(excluded.guest_phone, guest_phone),
               last_active = CURRENT_TIMESTAMP""",
        (session_id, email, name, phone),
    )
    conn.commit()
    conn.close()


def log_agent_trace(
    session_id, turn_id, step, event_type,
    tool_name=None, arguments=None, result=None, db_path=None
):
    """Persist one agentic step (tool call, tool result, or LLM stop) to agent_traces."""
    if not session_id:
        return
    try:
        conn = get_db(db_path)
        conn.execute(
            """INSERT INTO agent_traces
               (session_id, turn_id, step, event_type, tool_name, arguments, result)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                turn_id,
                step,
                event_type,
                tool_name,
                json.dumps(arguments) if arguments is not None else None,
                str(result)[:2000]   if result    is not None else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass   # tracing must never crash the main flow


def log_agent_turn(session_id, turn_id, intent, slot_delta, slots_after, db_path=None):
    """Persist one turn's classified intent and slot-delta snapshot."""
    if not session_id or not turn_id:
        return
    try:
        conn = get_db(db_path)
        conn.execute(
            """INSERT OR REPLACE INTO agent_turns
               (turn_id, session_id, intent, slot_delta, slots_after)
               VALUES (?, ?, ?, ?, ?)""",
            (
                turn_id,
                session_id,
                intent,
                json.dumps(slot_delta, default=str) if slot_delta else None,
                json.dumps(slots_after, default=str) if slots_after else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass   # turn logging must never crash the main flow


def save_session_state(session_id, slots_dict=None, last_intent=None,
                       agent_history=None, db_path=None):
    """
    Persist slot state + intent + agent history for a chat session.

    Idempotent — uses INSERT ... ON CONFLICT. Any field passed as None is
    left unchanged. Called by the app after each agent turn so a browser
    refresh restores the conversation deterministically.
    """
    if not session_id:
        return
    try:
        conn = get_db(db_path)
        # Ensure parent row exists with last_active bumped
        conn.execute(
            """INSERT INTO chat_sessions (session_id, last_active)
               VALUES (?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id) DO UPDATE SET last_active = CURRENT_TIMESTAMP""",
            (session_id,),
        )
        # COALESCE keeps existing values when caller passes None for a field
        conn.execute(
            """UPDATE chat_sessions
               SET slots_json         = COALESCE(?, slots_json),
                   last_intent        = COALESCE(?, last_intent),
                   agent_history_json = COALESCE(?, agent_history_json)
               WHERE session_id = ?""",
            (
                json.dumps(slots_dict, default=str) if slots_dict is not None else None,
                last_intent,
                json.dumps(agent_history, default=str) if agent_history is not None else None,
                session_id,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass   # persistence must never crash the main flow


def load_session_state(session_id, db_path=None):
    """
    Restore a previously-saved session.

    Returns:
      {
        "slots":          dict | None,
        "last_intent":    str  | None,
        "agent_history":  list | None,
        "guest_name":     str  | None,
        "guest_email":    str  | None,
        "guest_phone":    str  | None,
      }
    Any field that's not present returns None — caller decides what to fall
    back to.
    """
    blank = {"slots": None, "last_intent": None, "agent_history": None,
             "guest_name": None, "guest_email": None, "guest_phone": None}
    if not session_id:
        return blank
    try:
        conn = get_db(db_path)
        row = conn.execute(
            """SELECT slots_json, last_intent, agent_history_json,
                      guest_name, guest_email, guest_phone
               FROM chat_sessions WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
        conn.close()
        if not row:
            return blank
        return {
            "slots":         json.loads(row["slots_json"])         if row["slots_json"]         else None,
            "last_intent":   row["last_intent"],
            "agent_history": json.loads(row["agent_history_json"]) if row["agent_history_json"] else None,
            "guest_name":    row["guest_name"],
            "guest_email":   row["guest_email"],
            "guest_phone":   row["guest_phone"],
        }
    except Exception:
        return blank


def load_recent_messages(session_id, limit=40, db_path=None):
    """Return the most recent visible messages for a session (for display restoration)."""
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT role, content FROM conversation_messages
           WHERE session_id = ?
           ORDER BY id ASC LIMIT ?""",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
