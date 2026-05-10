<div align="center">

<img src="https://img.shields.io/badge/Model-Llama--3.1--8B%20via%20Groq-orange?style=for-the-badge" />
<img src="https://img.shields.io/badge/Stack-Python%20%2B%20Streamlit-blue?style=for-the-badge" />
<img src="https://img.shields.io/badge/Protocol-MCP%20JSON--RPC%202.0-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/DB-SQLite%20%2F%20PostgreSQL-lightgrey?style=for-the-badge" />

# 🍽️ GoodFoods AI Reservation Agent

**Sage** — An autonomous, tool-calling AI concierge for GoodFoods restaurant chain.
From natural-language intent to confirmed booking in under 90 seconds, zero human intervention.

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
| **Locations** | Browse all 75 branches on a map | ✅ Every customer |
| **Dashboard** | Live booking analytics, revenue KPIs, demand signals | 🔒 Restaurant management only |
| **Admin** | Search failures, competitor mentions, occasion CRM pipeline | 🔒 Internal operations team only |

In a real deployment the **Dashboard** and **Admin** tabs would sit behind staff authentication and never be visible to guests. They are surfaced here so reviewers can inspect the full intelligence layer — demand signals, competitor tracking, and occasion CRM — without needing database access.

---

## Setup Instructions

### Prerequisites

- Python 3.9+
- A free [Groq API key](https://console.groq.com/) (llama-3.1-8b-instant, free tier is sufficient)

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
# Seed 50 branches + full menus (required)
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
│   ├── search_branches.py    # Haversine distance + multi-factor weighted scoring
│   ├── check_availability.py # 30-min slot generation + occupancy calculation
│   ├── make_reservation.py   # Booking writer with duplicate guard
│   ├── modify_cancel.py      # Modify and cancel flows
│   ├── get_reservation.py    # Lookup by GF-XXXXXX reference number
│   ├── get_user_profile.py   # Returning guest recognition by email
│   ├── create_package.py     # Occasion experience package builder
│   ├── get_menu.py           # Menu fetcher with dietary filters
│   ├── log_search_failure.py # Demand-intelligence signal logger
│   └── corporate_accounts.py # B2B account lookup
│
├── intelligence/
│   ├── competitor_tracker.py # NL competitor mention logging
│   ├── demand_signal.py      # T-48h procurement signal generator
│   ├── missed_booking.py     # Drop-off re-engagement pipeline
│   └── occasion_crm.py       # T+364d anniversary follow-up scheduler
│
├── scripts/
│   ├── seed_data.py          # Branch + menu seed data (50 branches, 12 cuisines)
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
│  ┌──────────────────┐  │ ──────► │  llama-3.1-8b        │
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
| Identity & Scope | Sage, GoodFoods only, NYC — anchors the model |
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

### Journey 1 — Italian restaurant search and booking

```
User:   Find me a good Italian spot in Downtown for 4 people this Saturday at 7pm

Sage:   [→ search_branches(cuisine="Italian", location_hint="Downtown", party_size=4,
           latitude=40.7128, longitude=-74.0060)]

        Here are our top Downtown Italian kitchens for 4 this Saturday:

        🍽️ GoodFoods Downtown — Italian Kitchen
        📍 0.3 km · ⭐ 4.7 · $$$ · 80 seats · 11:00–22:30
        Popular: Truffle Rigatoni $28 · Branzino al Forno $34
        🥗 Vegetarian  🌾 Gluten-Free options

        [two more options presented]

        Which one catches your eye? I can check availability and lock in a table.

User:   The first one, please.

Sage:   [→ check_availability(branch_id=3, date="2026-05-09", party_size=4)]

        Great choice! Available Saturday slots for 4:
        Dinner: 18:00 · 18:30 · 19:00 · 19:30 · 20:00

        Could I grab your email to check for a profile?

User:   harsh@example.com

Sage:   [→ get_user_profile(email="harsh@example.com")]  → found: false

        No problem. To lock in 19:00 I just need your full name and phone.

User:   Harsh Gupta, 9876543210

Sage:   Here's what I'll book:
        📍 GoodFoods Downtown — Italian Kitchen
        📅 Saturday, May 09 2026  ·  🕐 19:00  ·  👥 4 guests
        👤 Harsh Gupta  ·  ✉ harsh@example.com  ·  📞 9876543210
        Shall I confirm?

User:   Yes!

Sage:   [→ make_reservation(branch_id=3, user_name="Harsh Gupta",
           user_email="harsh@example.com", user_phone="9876543210",
           party_size=4, date="2026-05-09", time="19:00")]

        ✅ Confirmed! Ref: GF-A7X2KP
        See you at our Downtown Italian Kitchen this Saturday at 19:00. 🍽️
```

---

### Journey 2 — Returning guest (one-click booking)

```
User:   Italian dinner for 2 tomorrow at 8pm

Sage:   [→ search_branches(cuisine="Italian", party_size=2)]
        [presents results]

        Could I grab your email to check if you have a profile with us?

User:   alex@company.com

Sage:   [→ get_user_profile(email="alex@company.com")]
        → found: true  ·  name="Alex Chen"  ·  phone="2125550199"  ·  visits=8

        Welcome back, Alex! You've dined with us 8 times.
        Shall I use your details on file (Alex Chen / ••••0199)?

User:   Yes, and the Downtown Italian please.

Sage:   [→ check_availability(branch_id=3, date="2026-05-06", party_size=2)]
        [→ make_reservation(...using saved profile...)]

        ✅ Confirmed! Ref: GF-BQ9L4M
        See you tomorrow at 20:00, Alex! 🍽️
```

---

### Journey 3 — Anniversary dinner with experience package

```
User:   Book our anniversary dinner — French, 2 people, next Friday evening

Sage:   [→ search_branches + check_availability + pre-booking summary]

        Shall I confirm?

User:   Yes

Sage:   [→ make_reservation(..., occasion="anniversary")]
        [→ create_experience_package(reference_number="GF-RX3MQ7",
           occasion="anniversary")]

        ✅ Confirmed! Ref: GF-RX3MQ7 🎉

        I've put together an Anniversary Experience:
        ✓ Candlelit table for two
        ✓ Personalised dessert with your names
        ✓ Complimentary sparkling wine on arrival
        ✓ Dedicated server for the evening
```

---

### Journey 4 — Modify then cancel

```
User:   Change my booking GF-A7X2KP to 20:00

Sage:   [→ get_reservation(reference_number="GF-A7X2KP")]
        [→ check_availability(branch_id=3, date="2026-05-09", party_size=4)]

        20:00 is available. I'll update GF-A7X2KP: 19:00 → 20:00. Shall I apply that?

User:   Actually just cancel it

Sage:   Are you sure you'd like to cancel GF-A7X2KP at GoodFoods Downtown
        on May 09? This cannot be undone.

User:   Yes, cancel it.

Sage:   [→ cancel_reservation(reference_number="GF-A7X2KP")]

        Done. GF-A7X2KP has been cancelled. Just say the word if you'd like to rebook.
```

---

### Journey 5 — Search failure (business intelligence signal)

```
User:   Find me Ethiopian food near Midtown

Sage:   [→ search_branches(cuisine="Ethiopian", location_hint="Midtown")] → []
        [→ log_search_failure(query="Ethiopian food near Midtown",
           cuisine="Ethiopian", neighborhood="Midtown", reason="no_cuisine_match")]

        We don't have an Ethiopian kitchen in Midtown yet — I've logged this
        so our expansion team can see the demand.

        Alternatively, our Mediterranean and Middle Eastern kitchens nearby
        share similar flavour profiles. Shall I show you those?
```

> This `log_search_failure` call appears in **Admin → Analytics → Recent Search Failures** and feeds the site-selection intelligence dashboard.

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

## Assumptions, Limitations & Future Enhancements

### Assumptions Made

| Assumption | Detail |
|-----------|--------|
| In-process MCP transport | Production would use stdio or HTTP/SSE transport for cross-process/cross-machine tools |
| SQLite as dev database | PostgreSQL with `SELECT FOR UPDATE` row-level locking required for concurrent production writes |
| Mock reminder pipeline | T-24h/T-2h reminder logic is wired; actual dispatch requires WhatsApp Business API HSM template pre-approval |
| NYC neighbourhood coordinates | Representative lat/lng centroids, not address-level GPS |
| English only (Phase 1) | Hindi/Indic language support requires a multilingual model; a translation shim alone does not work for agentic tool-call systems where structured intent must be extracted in the source language |

### Known Limitations

- **8B model context window:** Very long sessions use sliding-window history compression after 16 turns. Tool results are summarised in the digest, not dropped.
- **Groq free-tier rate limits:** ~30 RPM per key. Multi-key rotation handles burst traffic; sustained high load requires paid-tier keys.
- **WhatsApp HSM approval lead time:** Reminder template copy must be frozen and submitted to Meta 1-7 days before Phase 2 launch. Any copy change requires re-approval.
- **No real payment gateway:** Experience packages and corporate billing are schema-complete but require a payment integration (Razorpay/Stripe) in production.
- **SQLite concurrent writes:** Suitable for demo and single-user testing. Multi-user production requires PostgreSQL with proper connection pooling.

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
| LLM | llama-3.1-8b-instant via Groq | — |
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
