<div align="center">

<img src="https://img.shields.io/badge/Model-Llama--3.3--70B%20via%20Groq-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/Stack-Python%20%2B%20Streamlit-blue?style=for-the-badge" />
<img src="https://img.shields.io/badge/Protocol-MCP%20JSON--RPC%202.0-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/DB-SQLite%20%2F%20PostgreSQL-lightgrey?style=for-the-badge" />

# 🍽️ GoodFoods AI Reservation Agent

**Sage** — An autonomous, tool-calling AI concierge for the GoodFoods continental restaurant group, with 72 locations across Bangalore.
From natural-language intent ("best pizza in Indiranagar for 4 this Saturday") to confirmed booking in under 90 seconds, zero human intervention.

### 🚀 [Live Demo → https://cosmo-hg-goodfoods-agent-app-nnadpw.streamlit.app/](https://cosmo-hg-goodfoods-agent-app-nnadpw.streamlit.app/)

[Demo Video](#demo-video) · [Setup](#setup-instructions) · [Architecture](#architecture) · [Prompt Engineering](#prompt-engineering) · [Example Conversations](#example-conversations) · [Business Strategy](#business-strategy-summary)

</div>

---

## Demo Video

> 📹 **[Watch the full demo → https://www.loom.com/share/6e4135a8c59b4ec28db33910f3195b66]**

### What you see in the demo vs. what a real user sees

The live app and demo expose **all four tabs** for evaluation purposes:

| Tab | What it is | Who sees it in production |
|-----|-----------|--------------------------|
| **Concierge** | The guest-facing AI chat | ✅ Every customer |
| **Locations** | Browse all 72 Bangalore branches by area and cuisine | ✅ Every customer |
| **Dashboard** | Live booking analytics, revenue KPIs, demand signals | 🔒 Restaurant management only |
| **Admin** | Search failures, competitor mentions, occasion CRM pipeline | 🔒 Internal operations team only |

In a real deployment the **Dashboard** and **Admin** tabs would sit behind staff authentication and never be visible to guests. They are surfaced here so reviewers can inspect the full intelligence layer — demand signals, competitor tracking, and occasion CRM — without needing database access.

---

## Setup Instructions

### Prerequisites

- Python 3.9+
- A free [Groq API key](https://console.groq.com/) (llama-3.3-70b-versatile)

### 1 — Clone and install

```bash
git clone https://github.com/cosmo-hg/goodfoods-agent.git
cd goodfoods-agent
pip install -r requirements.txt
```

### 2 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your key(s):

```env
# Required — primary key
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx

# Optional — automatic key rotation on rate-limit (add up to 5 keys)
GROQ_API_KEY_2=gsk_yyyyyyyyyyyyyyyyyyyy
GROQ_API_KEY_3=gsk_zzzzzzzzzzzzzzzzzzzz
```

> **Multi-key rotation:** The agent automatically switches to the next available key the moment a `429 RateLimitError` is returned — no delay, no dropped conversation history.

### 3 — Seed the database

```bash
# Seed 72 Bangalore branches + full continental menus (required)
python scripts/seed_data.py

# Pre-populate demo bookings for the dashboard (optional)
python scripts/seed_demo_reservations.py
```

### 4 — Run

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

### Running the test suite

```bash
pytest tests/ -v
```

---

## Project Structure

```
goodfoods-agent/
│
├── app.py                    # Streamlit UI — 4 tabs: Concierge, Locations, Dashboard, Admin
├── config.py                 # DB schema init, API keys, neighbourhood GPS coordinates
├── requirements.txt
│
├── agent/
│   ├── loop.py               # Agentic loop — LLM calls + tool execution + key rotation
│   ├── prompts.py            # System prompt for Sage (semantic intent labels: BROWSE/BOOKING/MENU/MANAGE/GREET)
│   └── history.py            # Sliding-window conversation compressor
│
├── mcp/
│   ├── server.py             # In-process MCP JSON-RPC 2.0 server
│   ├── client.py             # MCP client — bridges server to agent loop
│   ├── registry.py           # Tool registry — schema + handler co-located (single source of truth)
│   └── protocol.py           # Protocol dataclasses (Request, Response, ToolDefinition)
│
├── tools/
│   ├── search_branches.py    # Filters-as-filters search; popularity ranking; dish-level matching; per-result confidence
│   ├── is_served_area.py     # Pre-search sanity check — refuses "best pizza in Brooklyn" honestly
│   ├── check_availability.py # 30-min slot generation + occupancy calculation
│   ├── make_reservation.py   # Booking writer with duplicate guard + popularity nudge
│   ├── modify_cancel.py      # Modify and cancel flows
│   ├── get_reservation.py    # Lookup by GF-XXXXXX reference number
│   ├── get_user_profile.py   # Returning guest recognition by email
│   ├── create_package.py     # Occasion experience package builder
│   ├── get_menu.py           # Menu fetcher with dietary filters
│   ├── log_search_failure.py # Demand-intelligence signal logger
│   ├── log_competitor.py     # LLM-callable competitor mention capture
│   └── corporate_accounts.py # B2B account lookup
│
├── intelligence/
│   ├── competitor_tracker.py # NL competitor mention logging
│   ├── demand_signal.py      # T-48h procurement signal generator
│   ├── missed_booking.py     # Drop-off re-engagement pipeline
│   └── occasion_crm.py       # T+364d anniversary follow-up scheduler
│
├── scripts/
│   ├── seed_data.py          # Bangalore continental chain — 72 branches × 8 cuisines, popularity-derived ratings
│   └── seed_demo_reservations.py
│
├── tests/
│   ├── conftest.py
│   ├── test_tools.py         # Unit tests for individual tools
│   └── test_loop.py          # Integration tests for the agent loop
│
└── data/
    └── goodfoods.db          # SQLite database (auto-created on first run)
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   Streamlit UI  (app.py)                    │
│  ┌───────────┐  ┌────────────┐  ┌───────────┐  ┌────────┐ │
│  │ Concierge │  │ Locations  │  │ Dashboard │  │ Admin  │ │
│  └─────┬─────┘  └────────────┘  └───────────┘  └────────┘ │
└────────┼───────────────────────────────────────────────────┘
         │ user message
         ▼
┌────────────────────────┐
│     Agent Loop         │   agent/loop.py
│   run_agent(...)       │
│  ┌──────────────────┐  │
│  │  System Prompt   │  │   agent/prompts.py
│  │  + Today's date  │  │
│  │  + Session refs  │  │
│  └──────────────────┘  │
│          │              │         ┌──────────────────────┐
│          ▼              │         │  Groq API            │
│  ┌──────────────────┐  │ ──────► │  llama-3.3-70b       │
│  │  _call_api()     │  │ ◄────── │  → stop OR           │
│  │  (key rotation)  │  │         │    tool_call(s)       │
│  └──────────────────┘  │         └──────────────────────┘
│          │ tool_calls   │
│          ▼              │
│  ┌──────────────────┐  │
│  │   MCP Client     │  │   mcp/client.py
│  │  call_tool(name, │  │
│  │    arguments)    │  │
│  └────────┬─────────┘  │
└───────────┼─────────────┘
            │ JSON-RPC 2.0  {"method": "tools/call", ...}
            ▼
┌────────────────────────┐
│    MCP Server          │   mcp/server.py + mcp/registry.py
│  (in-process)          │
│  ┌──────────────────┐  │
│  │  Tool Registry   │  │
│  │  search_branches │  │
│  │  check_avail.    │  │
│  │  make_reservation│  │
│  │  get_user_profile│  │
│  │  ... 11 tools    │  │
│  └────────┬─────────┘  │
└───────────┼─────────────┘
            │ Python function call
            ▼
┌────────────────────────┐
│    SQLite Database     │   config.py (schema) + data/goodfoods.db
│  branches              │
│  reservations          │
│  users                 │
│  search_failures       │
│  occasion_crm          │
│  competitor_mentions   │
│  chat_sessions         │
└────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **MCP (Model Context Protocol)** | Tool schemas and handlers co-located; LLM gets an accurate, machine-readable contract of exactly what each tool accepts and returns. No intent routing anywhere in agent code. |
| **In-process transport** | Zero network latency. Upgrading to stdio or SSE transport requires only swapping the transport layer — all method logic is identical. |
| **OpenAI-compatible client** | Groq exposes an OpenAI-compatible endpoint. Swapping LLM providers means changing one base URL string, nothing else. |
| **Key pool with 60s cooldown** | Up to 5 Groq keys; on `RateLimitError` the exhausted key is cooled for 60s and the loop immediately tries the next available key. Conversation history is unaffected. |
| **Tool-first, memory-free** | The model **never** answers factual questions from training data. Every branch detail, availability slot, and profile comes from a live tool call. This eliminates hallucination on real-world restaurant data. |
| **Sliding-window history** | After 16 turns the history is compressed; prevents context overflow on the 8B model without losing booking context. |

---

## Prompt Engineering

### Philosophy

Sage's system prompt is built on three principles:

**1. Intent-first, not keyword-matching.**
The prompt gives the LLM a decision tree with five semantic labels — `BROWSE`, `BOOKING`, `MENU`, `MANAGE`, `GREET` — and instructs it to silently identify the guest's intent before choosing an action. Each label is a meaningful word, not an arbitrary symbol, so it carries weight from the model's training: seeing `BOOKING` activates everything the model knows about reservations, dates, party sizes, and confirmation flows — reducing classification drift under long or ambiguous conversations. The model resolves intent privately and acts immediately, which eliminates filler responses like "What are you in the mood for?" — when a search would serve the guest better, the model calls `search_branches` without prompting.

**2. Tool-first, never invent.**
Every factual response must go through a tool call. The prompt contains an explicit hard rule: *"Never invent branch details, menus, or availability — always use tools."* Combined with `TEMPERATURE=0.3`, this virtually eliminates hallucination on restaurant-specific data.

**3. Progressive disclosure.**
The prompt collects only what is needed at the right moment. Email is requested only when the guest is ready to book, not on greeting. Multiple missing fields are batched into a single message, not dripped one at a time ("I need your name… [pause] …and your phone…").

### System Prompt Sections

| Section | Purpose |
|---------|---------|
| Identity & Scope | Sage, GoodFoods Bangalore-only, 8 continental concepts — anchors the model |
| Voice & Tone | Warm, specific, decisive; cite real data from tools |
| Intent Decision Tree | Semantic label (BROWSE/BOOKING/MENU/MANAGE/GREET) resolved silently; model acts immediately |
| Email & Profile Timing | Collect only when booking-ready, not on greeting |
| Search Flow | `search_branches` first, present all results with specifics |
| Booking Workflow | 7-step checklist + mandatory pre-booking summary |
| Booking Checklist | 7 required fields, none invented |
| No Availability | Always offer 2+ alternatives |
| Error Handling | Surface exact errors, no silent retry |
| Cancellation Safety | Explicit guest confirmation required |
| Modification Flow | `check_availability` before `modify_reservation` |
| Lookup Flow | GF-XXXXXX reference → `get_reservation` |
| Duplicate Booking Guard | Session-level de-duplication injected at runtime |
| Returning Guest Flow | Welcome back + use saved details with confirmation |
| Hard Rules | 4 absolute constraints capitalised for LLM attention |

### Tool Schema Design Patterns

```python
# Pattern 1 — Union types for LLM robustness
# The 8B model sometimes emits integer phone numbers.
# Union type prevents schema validation rejection.
"user_phone": {
    "type": ["string", "number"],
    "description": "Guest's REAL phone number. NEVER invent."
}

# Pattern 2 — Nullable optional fields
# Prevents the LLM from blocking a booking because it lacks an optional value.
"occasion":         {"type": ["string", "null"]},
"special_requests": {"type": ["string", "null"]},

# Pattern 3 — Capitalised constraints in descriptions
# Uppercase signals a hard-stop rule that the LLM treats as non-negotiable.
"user_name": {
    "description": "Guest's real full name. NEVER invent or use 'Guest'/'Unknown'."
}

# Pattern 4 — Stray-argument stripping in the server
# The LLM occasionally adds fields not in the schema (e.g. "reference_number"
# in make_reservation). The server strips unknown keys before dispatch.
known_props = tool_def.input_schema.get("properties", {})
arguments = {k: v for k, v in arguments.items() if k in known_props}
```

### Technique Summary

| Technique | Where applied | Effect |
|-----------|--------------|--------|
| Role + scope anchoring | Line 1 of system prompt | Eliminates off-topic responses |
| Intent classification tree | Section 2 | Removes unnecessary clarifying questions |
| Capitalised NEVER constraints | Booking checklist | LLM treats uppercase as hard-stop rules |
| Pre-booking summary template | Booking step 4 | Forces structured review before `make_reservation` |
| Session-level duplicate guard | Runtime injection | Prevents double-booking on page rerun |
| Today's date injection | Runtime, not prompt | Always accurate; prevents date confusion loops |
| `TEMPERATURE=0.3` | `config.py` | Reduces creative improvisation on factual fields |
| Union type nullable fields | `mcp/registry.py` | Prevents schema validation errors on optional args |
| Stray-key filtering | `mcp/server.py` | Prevents `unexpected keyword argument` TypeErrors |

---

## Example Conversations

### Journey 1 — Italian search + booking in Indiranagar

```
User:   best pizza in Indiranagar for 4 this Saturday at 8pm

Sage:   [→ is_served_area(location="Indiranagar")] → served=true
        [→ search_branches(cuisine="Italian", dish="pizza",
           location_hint="Indiranagar", party_size=4)]

        Our Indiranagar Italian Kitchen is one of the strongest matches:

        🍽️ GoodFoods Indiranagar — Italian Kitchen
        ⭐ 4.5 (820 reviews) · ₹₹₹ · 80 seats · 12:00–23:00
        Known for: Margherita Pizza ₹450 · Funghi e Tartufo Pizza ₹640
        🥗 Vegetarian  🌱 Vegan options  Jain-friendly

        Shall I check Saturday availability and lock you in?

User:   Yes, 8pm please

Sage:   [→ check_availability(branch_id=12, date="2026-06-13", party_size=4)]

        20:00 is open for 4. Could I grab your email — I'll check if you
        already have a profile with us.

User:   harsh@example.com

Sage:   [→ get_user_profile(email="harsh@example.com")] → found: false

        To lock in 20:00 on Saturday I just need your full name and phone.

User:   Harsh Gupta, +91 98450 12345

Sage:   Here's what I'll book:
        📍 GoodFoods Indiranagar — Italian Kitchen
        📅 Saturday, 13 June 2026  ·  🕐 20:00  ·  👥 4 guests
        👤 Harsh Gupta  ·  ✉ harsh@example.com  ·  📞 +91 98450 12345
        Shall I confirm?

User:   Yes!

Sage:   [→ make_reservation(...)]

        ✅ Confirmed! Ref: GF-A7X2KP
        See you at our Indiranagar Italian Kitchen this Saturday at 20:00. 🍽️
```

---

### Journey 2 — Returning guest (one-click booking)

```
User:   French Bistro for 2 tomorrow at 8pm

Sage:   [→ search_branches(cuisine="French", party_size=2)]
        [presents 3 high-confidence Bistro branches in Bangalore]

        Could I grab your email to check if you already have a profile?

User:   sneha.reddy@flipkart.com

Sage:   [→ get_user_profile(email="sneha.reddy@flipkart.com")]
        → found: true · name="Sneha Reddy" · phone="••••5678" · visits=6

        Welcome back, Sneha! You've dined with us 6 times.
        Shall I use your details on file?

User:   Yes, and the UB City French Bistro please.

Sage:   [→ check_availability + make_reservation using saved profile]

        ✅ Confirmed! Ref: GF-BQ9L4M
        See you tomorrow at 20:00, Sneha! 🍽️
```

---

### Journey 3 — Anniversary with experience package

```
User:   Book our anniversary — Steakhouse, 2 people, next Friday evening

Sage:   [→ is_served_area("Bangalore") → served=true (no specific area)]
        [→ search_branches(cuisine="Steakhouse", party_size=2)
         → check_availability → pre-booking summary]

        Shall I confirm?

User:   Yes

Sage:   [→ make_reservation(..., occasion="anniversary")]
        [→ create_experience_package(reference_number="GF-RX3MQ7",
           occasion="anniversary")]

        ✅ Confirmed! Ref: GF-RX3MQ7 🎉

        Anniversary Experience put together at our Grillroom:
        ✓ Candle-lit corner table for two
        ✓ Personalised dessert plate with your names
        ✓ Complimentary glass of bubbly on arrival
        ✓ Dedicated server for the evening
```

---

### Journey 4 — Modify then cancel

```
User:   Change my booking GF-A7X2KP to 20:30

Sage:   [→ get_reservation("GF-A7X2KP")]
        [→ check_availability(branch_id=12, date="2026-06-13", party_size=4)]

        20:30 is available. I'll update GF-A7X2KP: 20:00 → 20:30. Apply that?

User:   Actually just cancel it

Sage:   Are you sure you'd like to cancel GF-A7X2KP at our Indiranagar
        Italian Kitchen on 13 June? This cannot be undone.

User:   Yes, cancel it.

Sage:   [→ cancel_reservation(reference_number="GF-A7X2KP")]

        Done. GF-A7X2KP has been cancelled. Just say the word if you'd like to rebook.
```

---

### Journey 5 — Out-of-area refusal (and what it teaches the business)

```
User:   best pizza in Brooklyn, any distance is ok

Sage:   [→ is_served_area("Brooklyn")] → served=false

        GoodFoods is a Bangalore-only chain — we're not in Brooklyn.
        I can show you our top pizza spots in Bangalore instead, if you like.

User:   Find me a French Bistro in Pune

Sage:   [→ is_served_area("Pune")] → served=false
        [→ log_search_failure(query="French Bistro in Pune",
           cuisine="French", reason="off_city")]

        We don't operate in Pune yet — GoodFoods is a Bangalore chain.
        I've logged this so our expansion team sees the demand.
        Are you visiting Bangalore? I can find you a French Bistro here instead.
```

> Search failures appear in **Admin → Analytics → Recent Search Failures** and feed the site-selection intelligence pipeline. The `is_served_area` check is what stops the agent from inventing a Brooklyn branch — a class of failure that earlier versions did make.

---

## Business Strategy Summary

### The Core Problem

GoodFoods customers currently: call individual branches (hold time, human cost), use Dineout/EazyDiner (7.5-10% commission + zero data ownership), or simply abandon the booking. All three paths cost GoodFoods money or data.

### What Sage Actually Does

This is not a chatbot. It is GoodFoods' **primary customer relationship layer** and a **live business intelligence engine** that makes the business smarter with every conversation.

| Layer | What it delivers |
|-------|----------------|
| Booking layer | Natural-language → confirmed reservation in <90 seconds |
| Intelligence layer | Every failed search, competitor mention, and occasion becomes structured business data |
| Revenue layer | Experience packages, corporate accounts, missed-booking re-engagement |
| CRM layer | T+364d anniversary follow-ups, returning guest recognition |

### Non-Obvious Business Opportunities

1. **Search failures as site selection signals.** Every unmet search is demand data — aggregate "Ethiopian food near Midtown" queries and you have a real-intent expansion map.
2. **T-48h demand → procurement signal.** 48-hour booking visibility triggers inventory alerts, reducing estimated 8-12% food waste from last-minute procurement variance.
3. **Competitor mentions from natural language.** "Something like Social" is competitive benchmarking captured at scale, automatically, at zero cost.
4. **Occasion CRM without a CRM team.** A cron job + DB lookup re-engages customers 364 days later with perfect personalisation.
5. **Missed booking re-engagement.** Drop-off users notified within 90 minutes of a slot opening — consistent with e-commerce intent-decay patterns.

### Competitive Advantages

1. **Zero platform tax + owned data.** No 7.5-10% Dineout/EazyDiner commission. GoodFoods owns the relationship, preference history, and occasion context permanently.
2. **Demand intelligence flywheel.** Dataset compounds over time — every conversation adds signal that competitors who adopt later cannot buy.
3. **Domain-first tool architecture.** Edge cases (allergy flags, corporate invoicing, anniversary packages, B2B accounts) live in the tool schema. General LLM wrappers structurally cannot handle them because those edge cases require domain data.

---

## Production-grade safeguards

What's hardened — every item below is enforced in code and has at least one regression test:

| Concern | How it's closed |
|---|---|
| **Overbooking under concurrent writes** | `make_reservation` runs check + insert inside a single `BEGIN IMMEDIATE` transaction. SQLite holds a RESERVED lock, serialising racers. `busy_timeout = 5000ms` lets writers wait briefly instead of failing fast. Tested with 10 concurrent threads booking the last 4 seats — exactly 4 succeed. |
| **Modify under concurrent writes** | Same atomic transaction pattern. Capacity re-checked inside the lock; UPDATE happens in the same txn. Tested with two threads trying to move into the same slot — one wins, one is rejected cleanly. |
| **Modify / cancel on past bookings** | Both functions read the reservation date and return a user-friendly error if it's already in the past. Tested. |
| **LLM date math** | Deterministic date resolver pre-computes the next 14 days with weekday names + common relative phrases ("this saturday", "next weekend", "tomorrow"). Injected into user_context every turn. The LLM looks up; it never calculates. Tested for edge cases (today = Saturday, "this Saturday" = today). |
| **Indian phone validation** | Strict regex accepts only valid Indian mobile formats (10 digits starting 6-9, optional +91 prefix, optional separators). Tested with 10 valid + 8 invalid cases. |
| **Schema migrations on legacy databases** | `init_db()` is fully idempotent via `_safe_add_column()` — checks `PRAGMA table_info` before `ALTER TABLE ADD COLUMN`. New columns added in later schema versions land cleanly on old DBs without data loss. Indexes that reference new columns are created AFTER the migration step. Tested by simulating a legacy DB and upgrading it. |
| **Time outside branch hours** | Validated inside the booking transaction — rejected before any write. Tested for early-morning and late-night attempts. |
| **Session persistence across browser refresh** | `?session=<uuid>` URL param pins the conversation. Slot state, intent, agent history, and identified-guest data are saved to `chat_sessions` after every turn and restored on resume. Tested via save/load round-trip. |
| **Hallucinated coordinates** | The MCP registry wrapper for `search_branches` drops any lat/lon outside Bangalore's bounding box (12.7-13.2 N, 77.3-77.9 E) before reaching the search code. Defence against LLM invention. |
| **TPM exhaustion crashes** | `RuntimeError("All keys rate-limited")` is caught at the app layer and surfaced as a friendly retry message — conversation state preserved. |
| **Hallucinated slot values** | `make_reservation` validates against `_FAKE_NAMES`, `_FAKE_EMAILS`, `_FAKE_PHONES` denylists. Bad submissions are rejected with specific error messages rather than written to the DB. |
| **"Re-asking the guest" memory failures** | Slot state (`agent/slots.py`) is the authoritative record of what's been collected. Injected into user_context every turn with explicit "do NOT re-ask" instructions. The LLM physically sees what's filled vs. missing. |

### Assumptions retained

| Assumption | Detail |
|-----------|--------|
| In-process MCP transport | Production at scale would use stdio or HTTP/SSE for cross-process/cross-machine tools. Method-handler logic is unchanged either way. |
| Bangalore neighbourhood coordinates | Real lat/lng centroids for 25 served areas. Branch coordinates jittered ±400m around centroids; distances from manual area picks labelled "approximate" in the UI vs "real" for actual GPS reads. |
| Popularity-derived ratings | Long-tail distribution at seed time, nudged on every confirmed booking. "Best of" queries return defensible, stable answers. |
| English only (Phase 1) | Hindi/Indic support requires a multilingual model; a translation shim doesn't work for agentic tool-calling where structured intent must be extracted in the source language. |
| Mock WhatsApp reminders | T-24h / T-2h pipeline is wired; actual dispatch needs Meta HSM template approval. Out of MVP scope. |
| No payment gateway | Experience packages and corporate billing are schema-complete; integration with Razorpay/Stripe is post-MVP. |

### Streamlit architectural limits (not closable in code)

- Server-side rendering only — no token-by-token streaming
- No native cookies — session persistence works via URL param
- Limited mobile responsiveness — desktop-first

These would only be solved by moving the frontend to Next.js (laid out in Option B of an earlier discussion).

### Future Enhancements

| Feature | Phase |
|---------|-------|
| PostgreSQL migration + PgBouncer connection pooling | 2 |
| WhatsApp Business API real integration (HSM templates) | 2 |
| Hindi / Indic language support via multilingual model | 2 |
| Corporate account billing + Razorpay integration | 3 |
| Demand-to-procurement API integration | 3 |
| Franchise governance dashboard (no-show rates by branch) | 3 |
| No-show prediction model | 4 |
| Dynamic slot-blocking for peak demand management | 4 |
| Voice input (STT → Sage → TTS via IVR) | 4 |
| White-label SaaS for adjacent verticals (salons, clinics, golf) | 5 |

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| UI | Streamlit | 1.32+ |
| LLM | llama-3.3-70b-versatile via Groq | — |
| API Client | openai (OpenAI-compatible, Groq endpoint) | 1.12+ |
| Tool Protocol | MCP — in-process JSON-RPC 2.0 | — |
| Database | SQLite (dev) | built-in |
| Scoring | Haversine + weighted multi-factor | — |
| Testing | pytest | 8.0+ |
| Data | pandas | 2.0+ |

---

<div align="center">
All code is original · Built from scratch with no agent frameworks
</div>
