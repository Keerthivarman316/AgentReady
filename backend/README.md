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
