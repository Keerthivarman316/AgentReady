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
