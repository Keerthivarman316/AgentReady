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

Run the scoring math's unit tests (no DB required):

```
pip install -r requirements-dev.txt
pytest tests/ -v
```
