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
mandate — no re-prompting the human — logging every attempt.

```
POST /intent          {"consumer_id": "...", "goal_text": "earbuds under 2000 within 3 days"}
POST /buyer/purchase   {"mandate_id": "...", "w_price_fit": 0.5, ...}   # weights optional
GET  /audit/{mandate_id}
```

Run the full unit test suite (no DB required — Postgres-backed code paths like
`rank_by_trust`, `fetch_candidates`, and the mandate/audit tables are exercised
against a live DB, not unit-tested):

```
pip install -r requirements-dev.txt
pytest tests/ -v
```
