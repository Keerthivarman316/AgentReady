# AgentReady backend

FastAPI + LangGraph service.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

## Verify

```
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ping -H "Content-Type: application/json" -d "{\"message\": \"hi\"}"
```

## Database

Apply the schema against a Postgres instance with the `vector` extension available:

```
psql $DATABASE_URL -f ../db/schema.sql
```

## Synthetic data

Generates 12 merchants (4 trust archetypes x 3 categories), each with catalog products,
~90 days of transaction/refund/dispute history, and a reputation row.

```
python -m scripts.seed_synthetic_data --dry-run   # preview counts, no DB writes
python -m scripts.seed_synthetic_data              # insert into DATABASE_URL
```

## Composite Trust Engine

`app/trust_engine.py` computes the four weighted trust signals per merchant (payment
trust, promise-keeping, price-competitiveness, reputation) and combines them into one
composite score. Reputation's weight is hard-capped at 0.20 regardless of what a caller
requests, so it can inform the ranking but never dominate it.

```
GET  /merchants
GET  /merchants/{merchant_id}/trust-score?product_id=&w_payment_trust=&w_promise_keeping=&w_price_fit=&w_reputation=
GET  /merchants/{merchant_id}/trust-history
```

## Buyer side: Intent Agent, Buyer Agent, Checkout Executor

`app/intent_agent.py` resolves a natural-language goal into category/budget/deadline
(rule-based today, swappable for a Gemini-backed parser later) and issues a signed
AP2-style mandate (`app/ap2_mandate.py`, HMAC-signed, scoped, expiring).

`app/buyer_agent.py` runs the mandate through three layers, logging each to the audit
trail: hard constraints (budget/deadline cutoff) -> weighted heuristics (Composite Trust
Engine ranking) -> real-time optimization (live-price tie-break within a score epsilon).

`app/checkout.py` attempts Razorpay test-mode checkout on the ranked candidates in order;
if the top choice fails, it falls back to the next-ranked merchant within the same
mandate — no re-prompting the human — logging every attempt. Pass `simulate_failure_rank`
to `/buyer/purchase` to force a specific rank to fail deterministically (audit-logged with
`"simulated": true`) — this is what makes the fallback path demoable on cue instead of
depending on an incidental Razorpay rejection.

With real `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` set, checkout creates a real Razorpay
test-mode order and stops there — it deliberately does not attempt to capture a payment.
That's the correct AP2 boundary: an agent's job ends at a signed Payment Mandate; actual
capture is the payment network/wallet's job, against a credential the agent never sees raw.
(Razorpay also has no headless capture path for standard accounts — their S2S card API is
merchant-gated, and their hosted Checkout widget sits behind its own bot-detection stack,
which isn't something an agent should be built to defeat.) Without keys configured, checkout
runs in demo mode instead: it simulates a successful order (`"simulated": true`) so the
purchase flow is demoable without a Razorpay account.

```
POST /intent             {"consumer_id": "...", "goal_text": "earbuds under 2000 within 3 days"}
POST /buyer/rank-preview  {"mandate_id": "...", "w_price_fit": 0.5, ...}   # weights optional, no checkout side effect
POST /buyer/purchase      {"mandate_id": "...", "w_price_fit": 0.5, "simulate_failure_rank": 0, ...}   # runs checkout with fallback
GET  /audit/{mandate_id}
```

## Seller side: Readiness Agent, Trust Mirror, Benchmark Agent, Growth Advisor, SLA Advisor

`app/readiness_agent.py` scores how machine-readable a merchant's raw catalog text is
(price/category/description-length checks), reusing the same extraction helpers as the
Intent Agent (`app/text_extraction.py`) — without this step a merchant is invisible to
agent buyers regardless of its real trust metrics.

`app/trust_mirror.py` shows the merchant exactly what the Buyer Agent sees: the same
components, weights, and contributions, plus which signal is weakest/strongest.

`app/benchmark_agent.py` compares the merchant's score against its category's median —
rank and gap only, never named competitors, even in the synthetic data.

`app/growth_advisor.py` turns that gap into a ranked fix list (ranked by score *impact*,
gap size times weight — not raw gap size) and can re-run the same Composite Trust Engine
as a what-if simulation: override one component, see the rank shift.

`app/sla_advisor.py` recommends a declared SLA from the merchant's own historical COD
delivery times (85th percentile by default), flagging over- or under-promising.

```
POST /merchants/{id}/readiness              {"items": ["raw catalog text", ...]}
GET  /merchants/{id}/trust-mirror?product_id=&w_payment_trust=...
GET  /merchants/{id}/benchmark?w_payment_trust=...
GET  /merchants/{id}/growth-advisor?w_payment_trust=...
POST /merchants/{id}/growth-advisor/what-if  {"component": "payment_trust", "target_value": 0.9}
GET  /merchants/{id}/sla-advisor
```

Run the full unit test suite (no DB required — Postgres-backed code paths like
`rank_by_trust`, `fetch_candidates`, `compute_category_scores`, and the mandate/audit
tables are exercised against a live DB, not unit-tested):

```
pip install -r requirements-dev.txt
pytest tests/ -v
```
