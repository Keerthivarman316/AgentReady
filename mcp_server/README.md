# AgentReady MCP Server

Exposes the Composite Trust Engine, Growth Advisor, and Buyer Agent ranking
as live tools any MCP-compatible AI agent can call directly — Claude
Desktop, Claude Code, or any other MCP client — not just this project's own
Buyer Agent. Read-only: every tool queries or scores, it never creates a
mandate or attempts checkout. Actually transacting still goes through the
real API (`POST /buyer/purchase`), mandate-bound and audit-logged.

## Why a separate venv

`mcp[cli]` pulls in a newer starlette/pydantic than the pinned FastAPI
backend tolerates — installing it into `backend/.venv` broke uvicorn/FastAPI
outright. This server only imports `backend/app`'s pure business-logic
modules (trust scoring, growth advice, benchmarking), none of which import
FastAPI or pydantic, so it never needs the backend's dependency set. Keep
these two venvs separate.

## Setup

```
cd mcp_server
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt         # macOS/Linux
```

Reads `DATABASE_URL` from `../backend/.env` — no separate config needed as
long as the backend's database is seeded (`backend/scripts/seed_synthetic_data.py`).

## Tools

- `list_categories` / `list_merchants(category_name)` — discovery, since an
  external agent won't know AgentReady's internal merchant/category UUIDs.
- `get_merchant_trust_score(merchant_id)` — the four Composite Trust Engine
  components, weighted composite, weakest/strongest signal, and Trust
  Integrity Monitor flag status.
- `get_category_benchmark(merchant_id)` — rank and gap against the category
  median, no named competitors surfaced.
- `get_growth_advice(merchant_id)` — ranked fix list plus standing under
  five named AI-buyer priority profiles (Balanced, Trust-First,
  Fast-Shipper, Budget Hunter, Reputation-Led).
- `get_lost_sale_signal_tool(merchant_id)` — real hard-constraint rejection
  reasons logged across actual buyer evaluations.
- `get_buyer_weight_profiles(merchant_id)` — what kind of AI buyer has
  actually been evaluating this merchant, from real ranking runs.
- `rank_merchants_for_purchase(category_name, budget_paise, deadline_days, goal_text)`
  — runs the real Buyer Agent pipeline (hard constraints → Composite Trust
  Engine ranking) read-only, for every merchant in a category.

## Connecting a client

**Claude Code** (from the project root):

```
claude mcp add agentready-trust -- "E:\AgentReady\mcp_server\.venv\Scripts\python.exe" "E:\AgentReady\mcp_server\server.py"
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentready-trust": {
      "command": "E:\\AgentReady\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["E:\\AgentReady\\mcp_server\\server.py"]
    }
  }
}
```

Any other MCP client: run `.venv/Scripts/python.exe server.py` over stdio
with the same command/args shape.
