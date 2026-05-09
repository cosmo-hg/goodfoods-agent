import os
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
MODEL = "llama-3.1-8b-instant"
TEMPERATURE = 0.3

BASE_DIR = Path(__file__).parent
DB_PATH = str(BASE_DIR / "data" / "goodfoods.db")

NEIGHBORHOOD_COORDS = {
    "Downtown":           (40.7128, -74.0060),
    "Midtown":            (40.7549, -73.9840),
    "Uptown":             (40.7831, -73.9712),
    "West Side":          (40.7282, -74.0776),
    "East Side":          (40.7282, -73.9731),
    "North End":          (40.8004, -73.9496),
    "South Bay":          (40.6501, -74.0089),
    "Harbor View":        (40.6892, -74.0445),
    "Garden District":    (40.7614, -73.9776),
    "Financial District": (40.7075, -74.0113),
    "Arts Quarter":       (40.7267, -74.0020),
    "University District":(40.8075, -73.9626),
    "Riverside":          (40.8032, -73.9584),
    "Greenwood":          (40.6501, -73.9896),
    "Lakefront":          (40.6887, -73.9442),
}


def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    conn = get_db(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_code TEXT UNIQUE,
            name TEXT NOT NULL,
            neighborhood TEXT,
            address TEXT,
            city TEXT DEFAULT 'New York',
            latitude REAL,
            longitude REAL,
            capacity INTEGER,
            tables INTEGER,
            cuisine TEXT,
            rating REAL DEFAULT 4.0,
            review_count INTEGER DEFAULT 0,
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
            is_popular INTEGER DEFAULT 0,
            calories INTEGER,
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

        -- Performance indexes (CREATE INDEX IF NOT EXISTS is safe on existing DBs)
        CREATE INDEX IF NOT EXISTS idx_res_branch_date ON reservations(branch_id, date, status);
        CREATE INDEX IF NOT EXISTS idx_res_email       ON reservations(user_email);
        CREATE INDEX IF NOT EXISTS idx_res_ref         ON reservations(reference_number);
        CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);
        CREATE INDEX IF NOT EXISTS idx_sf_created      ON search_failures(created_at);
        CREATE INDEX IF NOT EXISTS idx_crm_followup    ON occasion_crm(followup_date, sent);
        CREATE INDEX IF NOT EXISTS idx_pkg_ref         ON packages(reference_number);
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
