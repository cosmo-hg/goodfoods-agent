# GoodFoods AI Reservation Agent — Use Case Document

> Prepared for: GoodFoods Restaurant Chain
> Solution: Conversational AI Reservation & Guest Intelligence Platform

---

## 1. Executive Summary

GoodFoods operates a growing multi-location restaurant chain with increasing pressure on reservation management, guest experience consistency, and operational efficiency. This document presents a conversational AI agent — **Sage** — that transforms reservation management from a cost centre into a revenue-generating, intelligence-gathering asset.

The solution goes beyond booking automation. It creates a system that learns guest preferences, anticipates demand, protects margin through supplier chain signals, and generates competitive intelligence — all within a single conversational interface that guests can access 24/7.

**Expected impact (Year 1):**
- 30–40% reduction in phone reservation workload
- 15–25% improvement in table utilisation through intelligent slot recommendations
- 8–12% reduction in no-shows via CRM follow-up system
- Incremental revenue through upsell occasion packages on 20%+ of bookings

---

## 2. Problem Statement

### 2.1 Current Pain Points

| Problem | Business Impact |
|---|---|
| Manual phone/email reservations consume front-desk staff time | 2–3 FTE hours per branch per day lost to reservation management |
| No centralised guest profile → zero personalisation | Loyal guests feel like strangers every visit |
| No demand forecasting tied to reservations | Kitchen over/under-orders, food waste 8–12% of COGS |
| No-shows average 15–20% industry-wide | Direct revenue loss; empty tables on booked nights |
| Special occasions go unrecognised | Missed upsell of packages (cakes, decorations, champagne) worth £25–80/booking |
| Zero insight into competitive landscape | GoodFoods doesn't know which competitor a declined guest went to instead |
| Corporate accounts managed in spreadsheets | Inconsistent discounts, missed billing, poor client relationships |

### 2.2 Root Cause

GoodFoods' reservation infrastructure was built for scale-down (single location) and never redesigned for a multi-location chain. The current system treats reservations as administrative events rather than guest relationship touchpoints.

---

## 3. Solution Overview

**Sage** is a conversational AI concierge deployed on a Streamlit web interface (extensible to WhatsApp, SMS, and in-app). It uses a hand-rolled agentic loop powered by **Llama 3.3-70b-versatile** (via Groq API) with 9 purpose-built tools covering the full reservation lifecycle.

### What Sage does

```
Guest intent → Branch recommendation → Availability check → Booking → 
Occasion package → Post-visit CRM → Demand signal → Competitive intelligence
```

### What Sage does NOT do (by design)

- Invent data it doesn't have (hard constraint in system prompt)
- Complete a booking without all required fields
- Share one guest's information with another

---

## 4. Key Business Problems & Opportunities

### 4.1 Beyond Basic Reservation: Identified Opportunities

#### Opportunity 1: Procurement Signal as a Margin Driver
The demand signal module alerts procurement when a branch crosses 70% fill rate within a 72-hour booking window. Most restaurant operators react to food waste after the fact; this system gives the kitchen team 72 hours to adjust orders. **Estimated impact: 3–5% reduction in food waste costs.**

#### Opportunity 2: Occasion Packaging as an Upsell Engine
Every reservation with an occasion (birthday, anniversary, proposal) automatically triggers a curated experience package. The average birthday package (cake, decorations, champagne) generates £40–80 in incremental revenue. If 20% of bookings include an occasion and the upsell rate is 60%, that's meaningful incremental revenue at near-zero marginal cost.

#### Opportunity 3: Competitive Intelligence Flywheel
The competitor tracker logs every mention of a competitor brand in guest conversations. Week-over-week analysis reveals: which competitors are mentioned most, in which neighbourhoods, and by what guest profile. This is market research that typically costs thousands per quarter — here it's a by-product of normal operations.

#### Opportunity 4: Waitlist Monetisation
When a cancellation frees a slot, the missed_booking module surfaces it within 2 hours. In production, this triggers a push notification to waitlisted guests — converting what would have been an empty table into a confirmed booking. Industry data suggests waitlist conversion of 40–60% of freed premium slots.

#### Opportunity 5: Corporate Account Expansion
The 10 pre-seeded corporate accounts represent a blueprint for a structured B2B revenue stream. Corporate clients typically book 3–5x more frequently, have higher average spend, and require less acquisition cost than individual diners. The agent can apply discounts, track spend against credit limits, and flag accounts approaching their limit.

#### Opportunity 6: Guest Lifetime Value through CRM Follow-ups
Post-visit follow-up messages sent on occasions (1 day after a birthday dinner) have industry-leading open rates (70%+ vs. 20% for generic marketing). This creates a high-quality touchpoint for loyalty programme invitations, repeat booking incentives, and feedback collection.

---

## 5. Success Metrics & ROI

### 5.1 Operational Metrics

| Metric | Baseline (estimated) | Target (Year 1) | Measurement |
|---|---|---|---|
| Reservation conversion rate (chat → booked) | N/A (new channel) | ≥ 65% | Agent logs |
| Time-to-book (minutes from first message) | 8–12 min (phone) | < 3 min | Session duration |
| No-show rate | 15–20% | ≤ 10% | Reservations vs. visits |
| Staff time on reservations | 2–3 hrs/branch/day | < 45 min/day | Time tracking |
| Occasion package attach rate | 0% (not offered) | ≥ 20% | create_experience_package calls |

### 5.2 Financial Metrics

| Metric | Calculation | Estimated Annual Value |
|---|---|---|
| Staff cost savings | 1.5 hrs/day × £15/hr × 365 days × N branches | £8,200 per branch |
| No-show reduction | 5% reduction × avg £35/cover × avg 2 covers/booking × 10 bookings/day × 365 days | £12,800 per branch/year |
| Occasion upsell | 20% attach × £50 avg package × 10 bookings/day × 365 days | £36,500 per branch/year |
| Food waste reduction | 4% COGS reduction × £2,000 avg weekly COGS | £4,160 per branch/year |
| **Total estimated value** | | **~£61,660 per branch/year** |

### 5.3 Strategic Metrics

- **Guest profile coverage**: % of guests with email on file (enables personalisation)
- **Competitor mention rate**: weekly trend in competitor brand mentions
- **Corporate account utilisation**: credit consumed vs. credit limit ratio
- **Fill rate distribution**: % of branches hitting the 70% procurement alert

---

## 6. Key Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| GoodFoods HQ / Owners | Decision maker | ROI, brand consistency, data ownership |
| Branch Managers | Day-to-day operator | Less phone interruptions, accurate demand forecasting |
| Front-of-House Staff | End beneficiary | Freed from manual booking entry |
| Kitchen / Procurement | Indirect beneficiary | Better demand signals reduce waste |
| Corporate Clients | Power user | Self-service booking against account, consistent discounts |
| End Customers (Diners) | Primary user | Instant 24/7 booking, occasion recognition |
| Marketing Team | Data consumer | Occasion CRM data, competitor intelligence |

---

## 7. Implementation Timeline

### Phase 1: Foundation (Weeks 1–4)
- Deploy Sage with core booking tools (search, availability, make, modify, cancel)
- Integrate with existing POS/reservation system via API adapter
- Train staff on escalation path (Sage → human agent handoff)
- **Milestone**: First 100 AI-assisted reservations

### Phase 2: Intelligence Activation (Weeks 5–8)
- Activate occasion CRM follow-up emails (integrate with SendGrid/Mailchimp)
- Enable demand signal → procurement team Slack/email alerts
- Launch waitlist notification for freed slots
- **Milestone**: First procurement alert acted on; first CRM email batch sent

### Phase 3: Multi-Channel Expansion (Weeks 9–12)
- WhatsApp Business API integration (same agent loop, new transport)
- Embed in GoodFoods mobile app via iframe or native SDK
- SMS fallback for guests without WhatsApp
- **Milestone**: 3+ channels live; cross-channel guest profile unification

### Phase 4: Analytics & Optimisation (Weeks 13–16)
- Internal dashboard: fill-rate heatmaps, conversion funnels, competitor intelligence reports
- A/B test occasion package offerings and messaging
- Personalisation: use guest history to pre-populate preferences
- **Milestone**: First monthly competitive intelligence report to management

---

## 8. Vertical Expansion Potential

The core architecture — agentic loop + tool registry + SQLite schema — is domain-agnostic. The same system can be rebranded and redeployed with new tools for:

| Vertical | Adaptation Required | Addressable Market |
|---|---|---|
| **Hotel concierge** | Replace branch → room; add check-in/out tools | Global hospitality ($4.7T industry) |
| **Healthcare appointments** | Replace reservation → appointment; add provider matching | GP surgeries, specialist clinics, dental |
| **Salon & spa bookings** | Add stylist/therapist matching; service duration as "party size" | Beauty and wellness ($190B global) |
| **Event venues** | Add capacity tiers, AV requirements, catering packages | Corporate events, weddings |
| **Co-working spaces** | Replace table → desk/meeting room; add recurring bookings | Remote work infrastructure |
| **Other restaurant chains** | White-label: rebrand Sage, reseed branches, deploy | Any multi-location F&B operator |

**Most compelling near-term expansion**: other restaurant chains in adjacent geographies. The system is fully multi-tenant by design (all queries are branch-scoped). A single deployment can serve multiple brands by adding a `brand_id` column to the branches table.

---

## 9. Competitive Advantages

### Advantage 1: Occasion Intelligence as a Moat
Most reservation systems (OpenTable, Resy) capture occasion data but don't act on it within the booking flow. Sage's occasion CRM creates a virtuous cycle: detect occasion → arrange package → follow-up → loyalty → rebooking. This is a differentiator that compounds over time as the CRM database grows.

### Advantage 2: Procurement Integration (unique in the sector)
No consumer-facing reservation system currently signals to the kitchen/procurement team in real time. This bridges a gap that exists in almost every restaurant operation and creates stickiness — once the procurement team relies on the 72-hour alert, the system is deeply embedded in operations.

### Advantage 3: Fully Explainable AI
Unlike black-box recommendation engines, every Sage decision is traceable: the scoring formula is documented, tool calls are logged, and the agent can explain why it recommended Branch X over Branch Y. This matters for staff trust, regulatory compliance, and debugging.

---

## 10. Potential Customers & Go-to-Market

### Direct customers (restaurant chains):
- Independent multi-location chains (5–50 branches) — underserved by enterprise software
- Fast-casual brands looking to add a premium reservation experience
- Hotel restaurant groups wanting unified guest profiles across properties

### Platform play (SaaS resale):
- White-label to restaurant tech providers (Seven Rooms, Tripleseat) who lack native AI
- Integrate with POS systems (Square, Toast) as an AI layer on top of existing infrastructure

### Pricing model:
- Per-branch SaaS fee (£150–300/branch/month)
- Revenue share on occasion packages (5–10% of package value)
- Enterprise licence for chains with 50+ locations

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM hallucination inventing availability | Low | High | Hard rule in system prompt + tool verification before booking |
| Data privacy (GDPR) | Medium | High | Guest email is the only PII collected; add data deletion endpoint in Phase 2 |
| Groq API downtime | Low | High | Circuit breaker with fallback to human agent handoff message |
| Guest adoption (prefers phone) | Medium | Medium | Phone still works; AI handles overflow and after-hours; gradual shift |
| Model context limit on long conversations | Low | Low | History compression after 10 turns; mitigates for 99%+ of sessions |
| Competitor scraping our branch data | Very Low | Low | No public API exposed; data is internal-only |
