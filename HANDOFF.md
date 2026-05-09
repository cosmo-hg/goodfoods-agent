# GoodFoods Agent — Session Handoff

## What This Project Is

A **private AI reservation concierge** for GoodFoods, a fictional premium restaurant chain with 75 branches across New York City. Each branch has a distinct cuisine and its own menu. This is an internal tool — Sage (the AI) only knows about GoodFoods locations and never recommends outside restaurants.

Built with: Python, Groq API (llama-3.3-70b-versatile), SQLite, Streamlit.

---

## Project Structure

```
goodfoods-agent/
├── app.py                        # Streamlit UI (3-tab layout)
├── config.py                     # DB schema, env vars, neighborhood coords
├── agent/
│   ├── loop.py                   # Agentic loop — iterates tool calls until stop
│   ├── prompts.py                # SYSTEM_PROMPT for Sage
│   └── history.py                # Compresses history after 10 turns
├── tools/
│   ├── registry.py               # 10 MCP-style tool schemas (JSON)
│   ├── executor.py               # Dispatches tool calls by name
│   ├── search_branches.py        # Search + haversine distance + menu highlights
│   ├── get_menu.py               # Full menu for a branch with filters
│   ├── check_availability.py     # 30-min slot availability (90-min windows)
│   ├── make_reservation.py       # Create booking, upsert user, trigger CRM
│   ├── modify_cancel.py          # Modify or cancel by reference number
│   ├── log_search_failure.py     # Log when search returns zero results
│   ├── get_user_profile.py       # Fetch returning guest profile
│   ├── create_package.py         # Occasion experience package after booking
│   └── corporate_accounts.py     # Look up corporate account by code/name
├── intelligence/
│   ├── occasion_crm.py           # Schedule day-after follow-up after occasion booking
│   ├── missed_booking.py         # Alert when a freed slot opens within 2h
│   ├── demand_signal.py          # Fire alert when branch hits 70% fill
│   └── competitor_tracker.py     # Regex scan for 30+ competitor brand names
├── scripts/
│   └── seed_data.py              # Seeds 75 branches + ~1143 menu items + 10 corporate accounts
├── tests/
│   ├── conftest.py               # Sets GROQ_API_KEY env var before imports
│   ├── test_tools.py             # 39 tests: search scoring, availability, reservations
│   └── test_loop.py              # 7 history compression + 6 executor dispatch tests
├── data/
│   └── goodfoods.db              # SQLite database (auto-created on first run)
├── USE_CASE.md                   # Business strategy doc (ROI, stakeholders, roadmap)
├── README.md                     # Architecture, prompt engineering, tool docs, examples
└── .env                          # GROQ_API_KEY=... (not committed)
```

---

## Database Schema (9 Tables)

| Table | Purpose |
|---|---|
| `branches` | 75 GoodFoods locations with coords, capacity, cuisine, hours |
| `menu_items` | ~1,143 items — 15-16 per branch, cuisine-specific |
| `reservations` | All bookings with reference numbers (GF-XXXXXX) |
| `users` | Guest profiles upserted on each booking |
| `corporate_accounts` | 10 seeded B2B accounts with discount % |
| `search_failures` | Logged when search returns zero results |
| `occasion_crm` | Day-after follow-up records |
| `dropoffs` | Freed slots from cancellations (for missed-booking alerts) |
| `competitor_mentions` | Competitor brand names detected in chat |

---

## 10 Tools Available to the Agent

1. `search_branches` — cuisine, neighbourhood, party size, dietary flags, price range, lat/lon
2. `get_branch_menu` — full menu grouped by category, with dietary/category filters
3. `check_availability` — 30-min slots between 11:00–22:30, respects 90-min dining windows
4. `make_reservation` — creates booking, upserts user, triggers occasion CRM
5. `modify_reservation` — change date/time/party size/requests by reference number
6. `cancel_reservation` — cancel by reference number, logs freed slot
7. `log_search_failure` — must be called when search returns zero results
8. `get_user_profile` — fetch returning guest history by email
9. `create_experience_package` — must be called after any occasion booking
10. `get_corporate_account` — look up B2B account by code or company name

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up env (one-time)
cp .env.example .env
# Add your Groq key: GROQ_API_KEY=gsk_...

# 3. Seed the database (run this if data/goodfoods.db doesn't exist or schema changed)
python scripts/seed_data.py

# 4. Run tests
python -m pytest tests/ -q

# 5. Start the app
streamlit run app.py
# Opens at http://localhost:8501
```

---

## Key Technical Decisions

### Agentic Loop (`agent/loop.py`)
- Hand-rolled — no LangChain. Iterates up to 20 steps.
- Returns `(response_text, updated_history, side_effects)` 3-tuple.
- `side_effects` carries `branch_results` and `reservation` for UI rendering without parsing text.
- `user_context` string injected into system prompt when user sets location (carries lat/lon).

### Distance (`search_branches.py`)
- Haversine formula computes `distance_km` from user lat/lon to each branch.
- User sets neighbourhood in sidebar → coords from `NEIGHBORHOOD_COORDS` dict in `config.py` → passed to agent as system context → LLM includes lat/lon in `search_branches` call.

### Menus Per Branch (`seed_data.py`)
- 12 cuisine templates in `MENUS` dict, each with 15-16 items (name, desc, category, base price, dietary flags, calories).
- Price adjusted by `price_factor = {1:0.8, 2:1.0, 3:1.2, 4:1.5}` per branch tier.
- Result: ~1,143 unique menu rows across 75 branches.

### Branch Scoring (`search_branches.py`)
- Cuisine match: 40 pts
- Capacity sufficient: 20 pts
- Rating (scaled): 10 pts
- Haversine proximity (≤1km=20, ≤3km=15, ≤5km=10, ≤10km=5): 20 pts
- Location hint match: 25 pts
- Each dietary flag match: 15 pts
- Price range match: 10 pts

### Availability (`check_availability.py`)
- Slots every 30 mins, 11:00–22:30.
- Slot is blocked if `SUM(party_size of overlapping confirmed reservations) + requested > capacity`.
- Overlap = reservations within 90 minutes of the slot.

### History Compression (`agent/history.py`)
- After 10 turns, keeps last 8 messages, summarizes older into a synthetic user+assistant pair.

---

## UI Layout (`app.py`)

4 tabs:
- **Concierge**: 2-column layout — chat on left, live branch recommendation panel on right. Shows branch cards (distance, rating, price dots, dietary badges, menu highlights) and reservation confirmation card (red gradient, GF-XXXXXX reference).
- **Our Locations**: 3-column grid of all 75 branches with expandable full menus.
- **Live Dashboard**: Real-time booking dashboard — date picker, 5 KPI cards, colour-coded 24-slot timeline per branch (empty→green→yellow→orange→red by fill %), per-slot guest detail rows (ref#, name, email, phone, party, occasion, requests), full sortable reservations table.
- **Admin**: 5 sub-tabs — All Branches, Add Location, Edit Location, Analytics, Competitor Signals.

Styling: Google Fonts Inter, dark sidebar (#111827), red accent (#dc2626), branch cards as raw HTML.

---

## Current State

- 75 branches seeded, ~1,143 menu items, 10 corporate accounts
- **62/62 tests passing** (46 original + 16 new edge-case tests)
- App running at http://localhost:8501
- Chat history is **in-memory only** (Streamlit session_state) — not persisted to DB
- README.md has a placeholder `YOUR_DEMO_VIDEO_LINK_HERE` that needs a real recording

---

## Known Bugs Fixed During Build

| Bug | Fix |
|---|---|
| Model `llama-3.3-8b-versatile` not found (404) | Changed to `llama-3.3-70b-versatile` |
| `occasion_crm.py` — `date` param shadowed `datetime.date` | Changed to `import datetime as _dt` |
| `modify_cancel.py` — party size increase skipped availability check | Added separate `elif party_increased:` branch with delta-based check |
| `demand_signal.py` — 70% threshold never fired | Changed denominator from `capacity*24` to `capacity*7` (7 dining turns/day) |
| Seed failed with FK constraint on branches | Delete reservations/occasion_crm/dropoffs before deleting branches |
| Old DB schema (no `tables` column) caused seed failure | Delete `data/goodfoods.db` and reseed |

---

## Edge-Case Hardening (second pass)

### `tools/check_availability.py`
- Added `get_branch_slots(opening_time, closing_time)` — slots now respect each branch's actual `opening_time`/`closing_time` from the DB instead of hardcoding 11:00–22:30
- Added `is_active` guard: inactive branches return `{"error": "..."}` immediately
- Added `null` branch_id guard

### `tools/make_reservation.py`
- **Past-date guard** — rejects bookings for any date before today
- **Party-size validation** — rejects `≤0` and `>500`
- **Email validation** — regex check on `user_email` before touching the DB
- **Required-field check** — explicit error if `user_name` or `user_phone` is blank
- Active-branch check now propagates cleanly via `check_availability`

### `tools/modify_cancel.py`
- **Past-date guard on modify** — rejects moving a reservation to a past date
- **Date format validation** on new date string
- **Party-size validation** when size is changed

### `agent/loop.py`
- **Today's date injected** into system prompt every turn — LLM can now correctly resolve relative dates ("this Saturday", "next Friday")
- **API retry with exponential backoff** — rate-limit errors (HTTP 429) are retried up to 3× with 1 s / 2 s delays before surfacing the error

### `agent/history.py`
- Compression now labels tool-call assistant messages as `[assistant]: Called tools: X, Y` instead of empty lines
- Tool result messages are truncated to 120 chars labeled `[tool result]: …` instead of raw JSON blobs

### `tools/search_branches.py`
- Cuisine matching upgraded to **partial substring match** (case-insensitive) — "Thai" now matches "Thai Fusion", "Thai Kitchen", etc.

### `app.py` — Admin tab
- Added **Analytics** sub-tab: 5 KPI metrics, bookings-by-cuisine bar chart, top-10 branches table, search-failures log, CRM pipeline table
- Added **Competitor Signals** sub-tab: mentions by competitor bar chart, summary table, raw mention log

---

## Demo Data

Run `python scripts/seed_demo_reservations.py` to seed 35 realistic reservations across today + 4 upcoming dates. Pass `--clear` to wipe and reseed.  
The Live Dashboard defaults to today — the slots will light up immediately.

## What Could Be Added Next

- Persist chat history to SQLite `conversations` table
- Real email sending for occasion CRM follow-ups
- Map view of branch locations in the UI
- Replace `YOUR_DEMO_VIDEO_LINK_HERE` in README with an actual recording
- Voice input via Whisper API
- Waitlist tool: let guests join a waitlist when no slot is available
