"""
GoodFoods MCP tool registry — single source of truth.

Every tool is declared exactly once: its JSON Schema (what the LLM sees) and
its Python handler (what gets executed) live together under the same
@server.tool() decorator.  The LLM reads schemas via tools/list and decides
autonomously which tool to invoke and with what arguments — no intent routing
or hardcoded dispatch lives anywhere else.

Underlying tool implementations (tools/*.py) are unchanged; this file only
wires them into the MCP protocol layer.
"""
from __future__ import annotations

import threading

from mcp.server import MCPServer
from mcp.client import MCPClient

# ── Import underlying tool implementations (business logic unchanged) ─────────
from tools.search_branches    import search_branches         as _search_branches
from tools.get_menu           import get_branch_menu         as _get_branch_menu
from tools.check_availability import check_availability      as _check_availability
from tools.make_reservation   import make_reservation        as _make_reservation
from tools.modify_cancel      import modify_reservation      as _modify_reservation
from tools.modify_cancel      import cancel_reservation      as _cancel_reservation
from tools.log_search_failure import log_search_failure      as _log_search_failure
from tools.get_user_profile   import get_user_profile        as _get_user_profile
from tools.create_package     import create_experience_package as _create_experience_package
from tools.corporate_accounts import get_corporate_account   as _get_corporate_account
from tools.get_reservation    import get_reservation         as _get_reservation

# ── Server singleton ──────────────────────────────────────────────────────────
server = MCPServer("goodfoods-mcp", "2.0.0")


# ═══════════════════════════════════════════════════════════════════════════════
#  Tool registrations
# ═══════════════════════════════════════════════════════════════════════════════

@server.tool(
    name="search_branches",
    description=(
        "Search active GoodFoods locations by cuisine, neighbourhood, party size, "
        "dietary needs, and price range. Returns top 3 scored matches with distance "
        "and menu highlights."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cuisine":             {"type": "string",  "description": "Cuisine type (Italian, Indian, Japanese, etc.)"},
            "party_size":          {"type": "integer", "description": "Number of guests"},
            "location_hint":       {"type": "string",  "description": "Neighbourhood or area name"},
            "latitude":            {"type": "number",  "description": "Guest latitude for distance calculation"},
            "longitude":           {"type": "number",  "description": "Guest longitude for distance calculation"},
            "dietary_vegetarian":  {"type": "boolean"},
            "dietary_vegan":       {"type": "boolean"},
            "dietary_gluten_free": {"type": "boolean"},
            "dietary_halal":       {"type": "boolean"},
            "dietary_kosher":      {"type": "boolean"},
            "price_range":         {"type": "integer", "description": "1=budget, 2=moderate, 3=upscale, 4=fine dining"},
        },
        "required": [],
    },
)
def search_branches(**kwargs):
    # Underlying function takes a single `params` dict, not keyword args.
    return _search_branches(kwargs)


@server.tool(
    name="get_branch_menu",
    description=(
        "Get the full menu for a specific GoodFoods location. Use when a guest asks "
        "what's available, wants to know about specific dishes, or has dietary "
        "requirements to verify."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch_id":      {"type": "integer", "description": "Branch ID from search_branches result"},
            "category":       {"type": "string",  "description": "Filter by category: Starters, Mains, Desserts, Drinks"},
            "dietary_filter": {"type": "string",  "description": "Filter: vegetarian, vegan, gluten_free, halal"},
        },
        "required": ["branch_id"],
    },
)
def get_branch_menu(**kwargs):
    return _get_branch_menu(**kwargs)


@server.tool(
    name="check_availability",
    description=(
        "Check available 30-minute time slots (11:00–22:30) at a GoodFoods location "
        "on a given date for the requested party size."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch_id":  {"type": "integer"},
            "date":       {"type": "string",  "description": "YYYY-MM-DD"},
            "party_size": {"type": "integer"},
        },
        "required": ["branch_id", "date", "party_size"],
    },
)
def check_availability(**kwargs):
    # Underlying signature: check_availability(branch_id, date, party_size, db_path=None)
    return _check_availability(
        kwargs["branch_id"],
        kwargs["date"],
        kwargs.get("party_size", 1),
    )


@server.tool(
    name="make_reservation",
    description=(
        "Confirm a GoodFoods reservation. "
        "ONLY call this when you have obtained ALL seven required fields directly "
        "from the guest in this conversation — never invent or guess any value. "
        "Returns a GF-XXXXXX reference number."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch_id":            {"type": "integer", "description": "Branch ID from a search_branches result. Never guess."},
            "user_name":            {"type": "string",  "description": "Guest's real full name as they stated it. NEVER invent or use 'Guest'/'Unknown'."},
            "user_email":           {"type": "string",  "description": "Guest's real email address as they provided it. NEVER invent."},
            "user_phone":           {"type": ["string", "number"], "description": "Guest's real phone number as they provided it. NEVER invent."},
            "party_size":           {"type": "integer", "description": "Number of guests as explicitly stated."},
            "date":                 {"type": "string",  "description": "YYYY-MM-DD. Convert relative dates using today's date. Never assume."},
            "time":                 {"type": "string",  "description": "HH:MM slot confirmed available via check_availability. Never assume."},
            "occasion":             {"type": ["string", "null"]},
            "special_requests":     {"type": ["string", "null"]},
            "corporate_account_id": {"type": ["integer", "null"]},
        },
        "required": ["branch_id", "user_name", "user_email", "user_phone", "party_size", "date", "time"],
    },
)
def make_reservation(**kwargs):
    return _make_reservation(**kwargs)


@server.tool(
    name="modify_reservation",
    description="Modify date, time, party size, or special requests on an existing GoodFoods reservation.",
    input_schema={
        "type": "object",
        "properties": {
            "reference_number": {"type": "string"},
            "date":             {"type": "string"},
            "time":             {"type": "string"},
            "party_size":       {"type": "integer"},
            "special_requests": {"type": "string"},
        },
        "required": ["reference_number"],
    },
)
def modify_reservation(**kwargs):
    return _modify_reservation(**kwargs)


@server.tool(
    name="cancel_reservation",
    description="Cancel a GoodFoods reservation by reference number.",
    input_schema={
        "type": "object",
        "properties": {
            "reference_number": {"type": "string"},
            "reason":           {"type": "string"},
        },
        "required": ["reference_number"],
    },
)
def cancel_reservation(**kwargs):
    return _cancel_reservation(**kwargs)


@server.tool(
    name="log_search_failure",
    description=(
        "Log when no GoodFoods location matches the guest's search criteria. "
        "MUST be called whenever search_branches returns zero results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query":        {"type": "string"},
            "party_size":   {"type": "integer"},
            "date":         {"type": "string"},
            "time":         {"type": "string"},
            "cuisine":      {"type": "string"},
            "neighborhood": {"type": "string"},
            "reason":       {"type": "string"},
        },
        "required": ["query", "reason"],
    },
)
def log_search_failure(**kwargs):
    return _log_search_failure(**kwargs)


@server.tool(
    name="get_user_profile",
    description="Retrieve a returning GoodFoods guest's profile and reservation history by email.",
    input_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string"},
        },
        "required": ["email"],
    },
)
def get_user_profile(**kwargs):
    return _get_user_profile(**kwargs)


@server.tool(
    name="create_experience_package",
    description=(
        "Create an occasion experience package after booking. "
        "MUST be called after make_reservation when an occasion is given."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "reference_number": {"type": "string"},
            "occasion":         {"type": "string"},
            "preferences":      {"type": "string"},
            "budget":           {"type": "string"},
        },
        "required": ["reference_number", "occasion"],
    },
)
def create_experience_package(**kwargs):
    return _create_experience_package(**kwargs)


@server.tool(
    name="get_corporate_account",
    description=(
        "Look up a corporate account by code or company name for business bookings. "
        "You MUST provide at least one of account_code or company_name — "
        "calling with no arguments returns nothing. Ask the guest for their "
        "company name or account code before calling this tool."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "account_code": {"type": "string", "description": "Corporate account code (e.g. CORP-001)"},
            "company_name": {"type": "string", "description": "Full company name as registered"},
        },
        "required": [],
    },
)
def get_corporate_account(**kwargs):
    return _get_corporate_account(**kwargs)


@server.tool(
    name="get_reservation",
    description=(
        "Look up a GoodFoods reservation by its GF-XXXXXX reference number. "
        "Use whenever a guest wants to check, view, or manage an existing booking."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "reference_number": {
                "type": "string",
                "description": "The GF-XXXXXX reference number from the booking confirmation.",
            },
        },
        "required": ["reference_number"],
    },
)
def get_reservation(**kwargs):
    return _get_reservation(**kwargs)


# ── Client factory ────────────────────────────────────────────────────────────

_client: MCPClient | None = None
_client_lock = threading.Lock()


def get_mcp_client() -> MCPClient:
    """
    Return a lazily-initialised MCPClient bound to the global MCP server.

    Thread-safe via double-checked locking: the outer check avoids acquiring
    the lock on every call once the singleton exists; the inner check prevents
    a second initialisation if two threads race through the outer check
    simultaneously.

    DB_PATH is read at tool-call time (not import time) so monkeypatching in
    tests still works correctly.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MCPClient(server)
                _client.initialize()
    return _client
