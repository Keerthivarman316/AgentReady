[AgentReady README.md](https://github.com/user-attachments/files/31301994/AgentReady.README.md)
# AgentReady

**A trust and growth layer for agentic commerce — where an AI buyer can verify who it's trusting, and an AI-ready merchant can grow because of it.**

Built for Razorpay Buildathon — Track 01: AI Growth & Agentic Commerce

---

## 1. The problem

Agentic commerce is arriving from two directions at once: buyer-side agents (ChatGPT Instant Checkout, Gemini shopping agents, Perplexity Shop) that purchase on a human's behalf, and a fast-consolidating stack of trust/authorization protocols (Google's AP2, OpenAI/Stripe's ACP, Coinbase's x402) that let those agents prove they're allowed to spend. Merchants sit in the middle, mostly unprepared: their catalogs and their trust signals are built for human eyes — marketing copy, star ratings, glossy photos — not for machine evaluation.

Razorpay's own track brief names this directly: *"grow the merchant's revenue, and make them sellable to AI buyers."* That's two separate problems wearing one label — a **buyer-agent trust** problem and a **merchant growth** problem. Most hackathon entries in this space solve only the first, and solve it shallowly: wire an LLM to a checkout API, call it agentic commerce.

AgentReady is a genuinely two-sided system. One side helps an AI buyer agent decide who to trust. The other side helps the merchant understand why it did — or didn't — win that trust, and what to fix. Both sides run off the same scoring engine, computed from data inside the actual transaction triangle: **buyer agent, merchant agent, and Razorpay** — no external logistics platforms, no scraped marketplace data.

## 2. The core design decision: composite trust, not one metric

Early in scoping this, we considered basing merchant trust purely on payment-processor telemetry (refunds, disputes, settlement reliability) on the theory that it's harder to fake than reviews. That's directionally right but incomplete on its own — reviews and reputation still carry real signal (they capture things payment data can't, like product-fit or service quality), and a buyer agent that ignores them entirely is throwing away information. So AgentReady computes a **weighted composite Trust Score**, not a single-source one:

| Signal group | Source | Default weighting rationale |
|---|---|---|
| **Payment trust** | Razorpay Payments/Refunds/Settlements API data | Hard to fake — generated as a byproduct of real transactions, not self-reported. Weighted highest. |
| **Promise-keeping trust** | Razorpay refund/dispute *reason codes* (e.g. `item_not_delivered`) vs. merchant's own declared SLA | Directly measures whether the merchant's claims survive contact with reality. Weighted high. |
| **Price-competitiveness** | Live price vs. category price band for the matched product | The traditional comparison factor — matters to the buyer, but shouldn't unilaterally override trust. Moderate weight. |
| **Reputation** | Review score / rating volume (synthetic in the demo, standing in for review-platform data in production) | Real signal, but self-reported and gameable — capped contribution, can't dominate the ranking on its own. |

All four signals feed one weighted scoring function in the Buyer Agent's heuristics layer — `score = w1·payment_trust + w2·promise_keeping + w3·price_fit + w4·reputation` — instead of price living outside the trust model as a pure tie-break. Weights are configurable per-run, which is also what makes the demo's core claim falsifiable rather than asserted: we can show the same merchant set re-rank live as the weights slide from "cheapest wins" toward "most trustworthy wins," and land on a sensible default where operational trust outweighs price and reputation but doesn't erase them. (This design is informed by — not a direct replication of — recent theoretical work on agentic commerce proposing that balanced AI buyer agents weight verifiable operational performance more heavily than accumulated reputation; we treat that as a hypothesis to demonstrate, not an assumed fact.)

The same source frames AI-mediated commerce as splitting a single historical role — "the shopper" — into two: the human who wants something (**consumer**) and the software that transacts (**shopper**). We use that split as a literal system boundary in the architecture below, not just a metaphor.

## 3. Architecture — two sides, one scoring engine

```
 BUYER SIDE                                                    SELLER SIDE
┌─────────────────┐   AP2    ┌──────────────────┐            ┌──────────────────┐
│  Intent Agent     │ mandate │  Buyer Agent       │            │  Readiness Agent   │
│  (consumer side)  │────────▶│  (shopper side)    │            │  catalog → agent-  │
│  captures goal,   │         │  3-layer decision: │            │  readable listing  │
│  budget, deadline  │         │  1. Hard Constraints│           └──────────────────┘
│  issues mandate    │         │  2. Learned         │                    │
└─────────────────┘           │     Heuristics       │                    ▼
                               │     (composite trust)│           ┌──────────────────┐
                               │  3. Real-Time Optimize│           │  Trust Mirror      │
                               └──────────────────┘           │  merchant-facing   │
                                        │                     │  view of own score │
                                        ▼                     └──────────────────┘
                               ┌──────────────────┐                    │
                               │ Razorpay Checkout  │                    ▼
                               │ (test-mode API)    │           ┌──────────────────┐
                               └──────────────────┘           │  Benchmark Agent   │
                                        │                     │  vs. category      │
                                        ▼                     │  median            │
                               ┌──────────────────┐           └──────────────────┘
                               │  Composite Trust    │                  │
                               │  Engine              │◀────────────────┘
                               │  (payment + promise- │                  │
                               │  keeping + reputation)│                 ▼
                               └──────────────────┘           ┌──────────────────┐
                                        │                     │ Growth Advisor     │
                                        ▼                     │ Agent — ranked     │
                               ┌──────────────────┐           │ fixes + what-if    │
                               │  Audit Trail Store  │           │ re-ranking sim    │
                               │  mandate hash, every │           └──────────────────┘
                               │  decision layer,      │                  │
                               │  failure + recovery   │                  ▼
                               └──────────────────┘           ┌──────────────────┐
                                                               │ SLA Advisor        │
                                                               │ recommends safe,   │
                                                               │ competitive SLA    │
                                                               └──────────────────┘
```

Both sides read from the same **Composite Trust Engine** — the seller side just gets to see it, question it, and act on it.

### Buyer side

**Intent Agent** — talks to the human, resolves a natural-language ask into a structured goal, and issues a signed AP2 mandate: budget cap, category, deadline, expiry. It never touches money.

**Buyer Agent** — can only act inside the bounds of the mandate it's holding. Three-layer decision pipeline:
1. **Hard Constraints** — reject anything outside the mandate's budget ceiling/deadline/category before scoring starts (a true cutoff, not a weight).
2. **Learned Heuristics** — rank survivors using the weighted composite score: payment trust + promise-keeping + price-competitiveness + capped reputation.
3. **Real-Time Optimization** — final tie-break on live stock/price movement at execution moment, for cases the weighted score leaves genuinely tied.

**Every step writes to the audit trail** — mandate hash, which layer made which cut, what data it used, and (deliberately, on one scripted case) how the system recovers when the top choice fails at execution time, falling back to the next-ranked merchant without re-prompting the human.

### Seller side

**Readiness Agent** — converts a merchant's raw catalog/checkout into the structured, machine-readable format the Buyer Agent actually evaluates. Without this a merchant is invisible to agent buyers regardless of how good their real metrics are — this is the entry point, not the differentiator.

**Trust Mirror** — merchant-facing dashboard showing exactly what the Buyer Agent sees: payment trust, promise-keeping score, reputation contribution, and which specific signals are driving each.

**Benchmark Agent** — places the merchant's scores against an anonymized category median, turning an abstract score into a concrete competitive gap (no named competitors, even in the synthetic data — a deliberate privacy-respecting design choice).

**Growth Advisor Agent** — the core revenue-growth deliverable. Turns the benchmark gap into a ranked, specific fix list, and can **re-run the Buyer Agent's own ranking pipeline as a what-if simulation**: "if your dispute rate dropped to the category median, you'd move from 4th to 1st in agent selection for this category." Same scoring engine as the buyer side, run in reverse — not a separate model.

**SLA Advisor** — recommends what delivery/service SLA to declare based on the merchant's own historical performance, so they claim what they can actually hit rather than over-promising (which the promise-keeping score punishes) or under-promising (which costs them ranking).

## 4. Where the trust signals actually come from — no external logistics platform

A genuine agent-to-agent system shouldn't depend on pulling in a courier API that neither agent agreed to trust. So every input to the Composite Trust Engine comes from inside the buyer↔seller↔Razorpay triangle:

- **Payment trust** — from Razorpay's Payments, Refunds, Settlements, and Disputes APIs: payment success rate, failure-reason breakdown, refund rate and speed, settlement reliability, dispute rate.
- **Promise-keeping trust** — the merchant agent declares an SLA (e.g. "delivers in ≤3 days"); we check it against refund/dispute *reason codes* (`item_not_delivered`, `item_not_received`) rather than any delivery-tracking API. For COD specifically, the gap between order-creation and payment-capture approximates delivery time, since capture only fires on delivery confirmation in that flow.
- **Reputation** — synthetic in the demo (standing in for a review-platform signal in production), deliberately capped in its contribution to the composite score so it can inform but not dominate.

For the demo, all of this is computed live from **scripted-but-real** Razorpay test-mode API calls against synthetic merchants — the transaction history is fabricated, the API responses and the scoring computation are not.

## 5. Why we're using AP2, not a bespoke consent object

We could have built our own "are you sure?" confirmation step. We're using **Google's Agent Payments Protocol (AP2)** mandate format instead:

- **It's the standard the industry is converging on** for exactly this layer — cryptographically signed mandates proving a human authorized a specific transaction, payment-method-agnostic, backed by a 60+ member coalition spanning card networks, PSPs, and crypto rails.
- **It directly answers the track's bar** — "every money action explainable, bounded and gated" — because AP2 mandates are designed to be exactly that: a signed, inspectable object scoping what the agent is allowed to do, for how much, and until when.
- **It reads as engineering maturity, not a hackathon shortcut.** We implemented the authorization layer using the protocol the market is standardizing on, rather than inventing our own.
- AP2 covers the Intent → Buyer authorization handoff specifically; settlement still runs through Razorpay's test-mode checkout APIs, since AP2 defines the authorization proof, not the settlement rail.

## 6. Why this stands out

| | Typical Track 1 submission | AgentReady |
|---|---|---|
| Consent/authorization | Ad-hoc "confirm to proceed" prompt | Signed AP2 mandate object, scoped and expiring, logged per transaction |
| Decision logic | Single LLM call picks a product | Explicit 3-layer pipeline, each layer's output logged separately |
| Ranking logic | Price sort, or star ratings / marketing copy | One weighted formula: PSP-verified payment trust + promise-keeping + price-competitiveness + capped reputation — weights are tunable and demoable live |
| Which side of the track it serves | Almost always buyer-only | Genuinely two-sided — a Buyer Agent that ranks, and a Growth Advisor that helps sellers win that ranking |
| The seller experience | Usually nonexistent | Trust Mirror + Benchmark + Growth Advisor with live what-if re-ranking simulation |
| Fulfillment data source | Often assumes courier API access nobody has for a demo | Derived entirely from payment-layer signals already available (refund reason codes, COD capture-gap) — no third-party dependency |
| Failure handling | Usually undemonstrated | One scripted failure, graceful fallback, fully logged, no human re-prompt |

The one-sentence pitch: **most entries build an agent that shops; we build the trust infrastructure an AI buyer needs to decide who to trust, and the growth infrastructure an AI-ready merchant needs to earn that trust — both computed from the same engine, both provably real, neither dependent on data nobody in a hackathon can actually get.**

## 7. Tech stack

- **Backend:** FastAPI + LangGraph — Intent Agent, Buyer Agent (3-node decision stack), Readiness Agent, Composite Trust Engine, Benchmark Agent, Growth Advisor Agent, SLA Advisor, Mandate Issuer, Checkout Executor
- **DB:** PostgreSQL — stores trust-score history per merchant for the Trust Mirror and Benchmark Agent. Product catalog embeddings (Gemini, 768-dim) power semantic search via cosine similarity computed in Python rather than pgvector, since this dev environment's Postgres has no pgvector extension available to install; see `db/schema.sql`
- **LLM:** Gemini (`gemini-3.6-flash` for text/structured extraction, `gemini-embedding-001` for vectors) — buyer intent parsing, chat follow-up parsing, growth-fix explanation generation, and product catalog embeddings; every call site falls back to a deterministic non-LLM path when unconfigured or on failure
- **Payments:** Razorpay test-mode Orders API for checkout (`order.create()` is the deliberate agent-side boundary — see `checkout.py`); a signature-verified webhook receiver (`app/webhooks.py`) ingests real `payment.captured`/`order.paid`/`refund.processed`/`payment.dispute.created` events into the same tables the Trust Engine reads, tagged `source='razorpay_live'` alongside the scripted synthetic history
- **Authorization:** Mandates shaped to match Google's Agent Payments Protocol (AP2) JSON Schemas verbatim (vendored in `backend/app/ap2_schemas/`, validated by a real `jsonschema` conformance test) for the Intent → Buyer → Checkout handoff; HMAC-signed rather than the spec's JWS/SD-JWT chain
- **Frontend:** Next.js + Tailwind — three surfaces: buyer chat with live decision trace, merchant Trust Mirror + Growth dashboard, audit trail viewer
- **Synthetic data:** 3–5 fake merchants per category with deliberately varied payment-trust, promise-keeping, and reputation profiles, plus declared SLAs some honor and some violate — grounded in realistic distributions, not arbitrary numbers

## 8. MCP server — trust intelligence any AI agent can call

The Composite Trust Engine, Growth Advisor, and Buyer Agent ranking are also exposed as an [MCP server](mcp_server/) — not just callable by this project's own Buyer Agent. Any MCP-compatible client (Claude Desktop, Claude Code, or any other agent that speaks MCP) can connect and call `get_merchant_trust_score`, `get_growth_advice`, `rank_merchants_for_purchase`, and five other tools directly, live, against the real Postgres-backed scoring engine. It's read-only by design — actually transacting still goes through the mandate-bound, audit-logged `/buyer/purchase` API — but it means AgentReady's trust intelligence isn't locked inside one demo app; it's a tool any agent in the 2026 agentic-commerce ecosystem could plug into, the same way MCP has become the protocol most AI shopping agents already depend on for tool access.

## 9. What we'll show at demo time

1. Onboard a merchant with a messy, marketing-only catalog → Readiness Agent scores it and generates the structured feed.
2. Give the Buyer Agent a natural-language goal → it issues a mandate, walks through its 3-layer reasoning live, and picks a merchant based on the weighted composite score — slide the weights (price up/trust down, then reverse) and show the ranking flip live, proving the trade-off is real and inspectable, not hardcoded.
3. Trigger the scripted failure → agent falls back gracefully within the same mandate, no re-prompt, fully logged.
4. Switch to the merchant view → Trust Mirror shows the losing merchant exactly why they ranked below a competitor, Benchmark Agent shows the category gap, Growth Advisor proposes a fix and re-runs the ranking live to show the merchant moving up.
5. Open the audit trail → mandate hash, every decision layer's output, the failure and recovery, end to end.
