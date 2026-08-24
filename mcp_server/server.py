"""AgentReady MCP server: exposes the Composite Trust Engine, Growth Advisor,
and Buyer Agent ranking as live tools any MCP-compatible AI agent (Claude
Desktop, Claude Code, or any other MCP client) can call directly — not just
this project's own Buyer Agent.

Runs in its own venv (mcp_server/.venv), isolated from backend/.venv: the
`mcp` SDK pulls in a newer starlette/pydantic than the pinned FastAPI backend
tolerates, and installing it into backend/.venv broke uvicorn/FastAPI outright
(TypeError: Router.__init__() got an unexpected keyword argument 'on_startup').
This process only ever reads app/*.py's pure business-logic modules (trust
scoring, growth advice, benchmarking) — none of which import fastapi or
pydantic — so it never needs the backend's dependency set at all.

Read-only by design: every tool here queries or scores, never writes a
mandate or attempts checkout. An external agent gets AgentReady's trust
intelligence to *decide* with; actually transacting still goes through
POST /buyer/purchase on the real API, mandate-bound and audit-logged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from mcp.server.fastmcp import FastMCP

from app.benchmark_agent import benchmark_merchant
from app.buyer_agent import apply_hard_constraints, fetch_candidates, rank_by_trust, real_time_optimize
from app.buyer_weight_profiles import get_weight_profile_signal
from app.db import get_connection
from app.growth_advisor import advise_growth
from app.lost_sale_signal import get_lost_sale_signal
from app.text_extraction import extract_product_keywords
from app.trust_mirror import build_trust_mirror

mcp = FastMCP("agentready-trust")


def _category_id_by_name(cur, name: str) -> str | None:
    cur.execute("SELECT id FROM categories WHERE name ILIKE %s", (name,))
    row = cur.fetchone()
    return str(row[0]) if row else None


def _merchant_category_id(cur, merchant_id: str) -> str | None:
    cur.execute("SELECT category_id FROM merchants WHERE id = %s", (merchant_id,))
    row = cur.fetchone()
    return str(row[0]) if row else None


@mcp.tool()
def list_categories() -> list[dict]:
    """List every product category AgentReady has merchants in, with each
    category's id (needed by other tools) and name."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM categories ORDER BY name")
        return [{"id": str(r[0]), "name": r[1]} for r in cur.fetchall()]


@mcp.tool()
def list_merchants(category_name: str) -> list[dict]:
    """List merchants in a category by name (e.g. 'Electronics'), with their
    id (needed by other tools), name, and declared SLA in days."""
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _category_id_by_name(cur, category_name)
        if category_id is None:
            return []
        cur.execute(
            "SELECT id, name, declared_sla_days FROM merchants WHERE category_id = %s ORDER BY name",
            (category_id,),
        )
        return [{"id": str(r[0]), "name": r[1], "declared_sla_days": r[2]} for r in cur.fetchall()]


@mcp.tool()
def get_merchant_trust_score(merchant_id: str) -> dict:
    """Get a merchant's live Composite Trust Engine score: the four
    components (payment_trust, promise_keeping, price_fit, reputation), the
    weighted composite, which signal is weakest/strongest, and whether the
    Trust Integrity Monitor has flagged this merchant's reputation as
    inconsistent with its own operational data (a flagged merchant is
    quarantined out of real buyer rankings)."""
    with get_connection() as conn, conn.cursor() as cur:
        return build_trust_mirror(cur, merchant_id)


@mcp.tool()
def get_category_benchmark(merchant_id: str) -> dict:
    """Get a merchant's trust-score rank and gap against its category's
    median — how it stacks up against every other merchant selling in the
    same category, with no named competitors surfaced."""
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _merchant_category_id(cur, merchant_id)
        if category_id is None:
            return {"error": f"merchant {merchant_id} not found"}
        return benchmark_merchant(cur, merchant_id, category_id)


@mcp.tool()
def get_growth_advice(merchant_id: str) -> dict:
    """Get a merchant's ranked, specific fix list (which trust component to
    improve for the biggest score impact) plus how it would rank under five
    named AI-buyer priority profiles (Balanced, Trust-First, Fast-Shipper,
    Budget Hunter, Reputation-Led) instead of one fixed weighting."""
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _merchant_category_id(cur, merchant_id)
        if category_id is None:
            return {"error": f"merchant {merchant_id} not found"}
        return advise_growth(cur, merchant_id, category_id)


@mcp.tool()
def get_lost_sale_signal_tool(merchant_id: str) -> dict:
    """Get why real AI buyer agents have passed on this merchant: a
    breakdown of actual hard-constraint rejection reasons (over budget,
    misses deadline, wrong product type) logged across real purchase
    evaluations. Empty until real buyer runs have evaluated this merchant."""
    with get_connection() as conn, conn.cursor() as cur:
        return get_lost_sale_signal(cur, merchant_id)


@mcp.tool()
def get_buyer_weight_profiles(merchant_id: str) -> dict:
    """Get what kind of AI buyer has actually been evaluating this merchant
    — real purchase-ranking runs bucketed by which of the four trust
    components the buyer weighted highest (e.g. '62% Budget Hunters, avg
    rank 4'), not a synthetic benchmark."""
    with get_connection() as conn, conn.cursor() as cur:
        return get_weight_profile_signal(cur, merchant_id)


@mcp.tool()
def rank_merchants_for_purchase(category_name: str, budget_paise: int, deadline_days: int,
                                 goal_text: str = "") -> dict:
    """Run AgentReady's real Buyer Agent decision pipeline read-only: hard
    constraints (budget/deadline/product-type cutoff) then Composite Trust
    Engine ranking, for every merchant selling in `category_name`. Returns
    the ranked candidates an autonomous purchase would choose from — this
    is advisory only, it does not create a mandate or attempt checkout.
    `goal_text` is optional free text (e.g. 'wireless earbuds') used to
    filter out the wrong product type within the category."""
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _category_id_by_name(cur, category_name)
        if category_id is None:
            return {"error": f"no category named {category_name!r}"}

        candidates = fetch_candidates(cur, category_id)
        keywords = extract_product_keywords(goal_text) if goal_text else None
        survivors, rejected = apply_hard_constraints(candidates, budget_paise, deadline_days, keywords)
        if not survivors:
            return {"status": "no_candidates", "rejected_count": len(rejected)}

        ranked, quarantined = rank_by_trust(cur, survivors)
        optimized = real_time_optimize(ranked)

        return {
            "status": "ranked",
            "ranking": [
                {
                    "merchant_id": c["merchant_id"], "merchant_name": c["merchant_name"],
                    "product_id": c["product_id"], "product_name": c["product_name"],
                    "price_paise": c.get("live_price_paise", c["price_paise"]), "composite_score": c["composite_score"],
                    "trust_components": c["trust_components"],
                }
                for c in optimized
            ],
            "rejected_count": len(rejected),
            "quarantined_count": len(quarantined),
        }


if __name__ == "__main__":
    mcp.run()
