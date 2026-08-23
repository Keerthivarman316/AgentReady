import logging

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("agentready")

from app.audit_trail import fetch_audit_trail, log_audit
from app.benchmark_agent import benchmark_merchant
from app.buyer_agent import run_buyer_pipeline
from app.checkout import checkout_with_fallback
from app.db import get_connection
from app.graph import ping_graph
from app.growth_advisor import advise_growth, simulate_what_if
from app.intent_agent import IntentResolutionError, resolve_intent_to_mandate
from app.lost_sale_signal import get_lost_sale_signal
from app.readiness_agent import assess_catalog
from app.sla_advisor import advise_sla
from app.trust_engine import DEFAULT_WEIGHTS, score_merchant
from app.trust_mirror import build_trust_mirror

app = FastAPI(title="AgentReady API")

@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    # Must be registered before CORSMiddleware below, so CORSMiddleware ends up
    # as the outer layer wrapping this one (Starlette applies the last-added
    # middleware outermost). An exception that escapes this handler and reaches
    # Starlette's own ServerErrorMiddleware instead never gets CORS headers, so
    # the browser reports an opaque "blocked by CORS policy" instead of the
    # real failure.
    try:
        return await call_next(request)
    except Exception:
        # Logged here because the client only ever gets a generic message —
        # without this, every unhandled error is invisible server-side too.
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _weights_from_query(w_payment_trust: float | None, w_promise_keeping: float | None,
                         w_price_fit: float | None, w_reputation: float | None) -> dict | None:
    if all(w is None for w in (w_payment_trust, w_promise_keeping, w_price_fit, w_reputation)):
        return None
    return {
        "payment_trust": w_payment_trust if w_payment_trust is not None else DEFAULT_WEIGHTS["payment_trust"],
        "promise_keeping": w_promise_keeping if w_promise_keeping is not None else DEFAULT_WEIGHTS["promise_keeping"],
        "price_fit": w_price_fit if w_price_fit is not None else DEFAULT_WEIGHTS["price_fit"],
        "reputation": w_reputation if w_reputation is not None else DEFAULT_WEIGHTS["reputation"],
    }


def _fetch_merchant_category_id(cur, merchant_id: str) -> str:
    cur.execute("SELECT category_id FROM merchants WHERE id = %s", (merchant_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"merchant {merchant_id} not found")
    return str(row[0])


class PingRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ping")
def ping(req: PingRequest):
    result = ping_graph.invoke({"message": req.message, "reply": ""})
    return {"reply": result["reply"]}


@app.get("/merchants")
def list_merchants():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.name, c.name, m.declared_sla_days
            FROM merchants m JOIN categories c ON c.id = m.category_id
            ORDER BY c.name, m.name
            """
        )
        rows = cur.fetchall()
    return [
        {"id": str(r[0]), "name": r[1], "category": r[2], "declared_sla_days": r[3]}
        for r in rows
    ]


@app.get("/merchants/{merchant_id}/trust-score")
def get_trust_score(
    merchant_id: str,
    product_id: str | None = None,
    w_payment_trust: float = Query(default=DEFAULT_WEIGHTS["payment_trust"]),
    w_promise_keeping: float = Query(default=DEFAULT_WEIGHTS["promise_keeping"]),
    w_price_fit: float = Query(default=DEFAULT_WEIGHTS["price_fit"]),
    w_reputation: float = Query(default=DEFAULT_WEIGHTS["reputation"]),
):
    weights = {
        "payment_trust": w_payment_trust,
        "promise_keeping": w_promise_keeping,
        "price_fit": w_price_fit,
        "reputation": w_reputation,
    }
    with get_connection() as conn, conn.cursor() as cur:
        try:
            result = score_merchant(cur, merchant_id, product_id=product_id, weights=weights)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        conn.commit()
    return result


@app.get("/merchants/{merchant_id}/trust-history")
def get_trust_history(merchant_id: str, limit: int = 20):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT payment_trust, promise_keeping, price_fit, reputation,
                   composite_score, weights, computed_at
            FROM trust_score_history
            WHERE merchant_id = %s
            ORDER BY computed_at DESC
            LIMIT %s
            """,
            (merchant_id, limit),
        )
        rows = cur.fetchall()
    return [
        {
            "payment_trust": float(r[0]),
            "promise_keeping": float(r[1]),
            "price_fit": float(r[2]),
            "reputation": float(r[3]),
            "composite_score": float(r[4]),
            "weights": r[5],
            "computed_at": r[6].isoformat(),
        }
        for r in rows
    ]


class IntentRequest(BaseModel):
    consumer_id: str
    goal_text: str


@app.post("/intent")
def create_intent(req: IntentRequest):
    with get_connection() as conn, conn.cursor() as cur:
        def category_id_lookup(name: str) -> str | None:
            cur.execute("SELECT id FROM categories WHERE name = %s", (name,))
            row = cur.fetchone()
            return str(row[0]) if row else None

        try:
            mandate = resolve_intent_to_mandate(req.consumer_id, req.goal_text, category_id_lookup)
        except IntentResolutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        cur.execute(
            """
            INSERT INTO mandates
                (consumer_id, category_id, budget_cap_paise, deadline_days, goal_text, mandate_hash, issued_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (mandate.consumer_id, mandate.category_id, mandate.budget_cap_paise, mandate.deadline_days,
             mandate.goal_text, mandate.mandate_hash, mandate.issued_at, mandate.expires_at),
        )
        (mandate_id,) = cur.fetchone()

        log_audit(cur, str(mandate_id), "intent", {
            "goal_text": mandate.goal_text,
            "category_id": mandate.category_id,
            "budget_cap_paise": mandate.budget_cap_paise,
            "deadline_days": mandate.deadline_days,
            "mandate_hash": mandate.mandate_hash,
        })
        conn.commit()

    return {
        "mandate_id": str(mandate_id),
        "category_id": mandate.category_id,
        "budget_cap_paise": mandate.budget_cap_paise,
        "deadline_days": mandate.deadline_days,
        "mandate_hash": mandate.mandate_hash,
        "issued_at": mandate.issued_at.isoformat(),
        "expires_at": mandate.expires_at.isoformat(),
    }


class PurchaseRequest(BaseModel):
    mandate_id: str
    w_payment_trust: float | None = None
    w_promise_keeping: float | None = None
    w_price_fit: float | None = None
    w_reputation: float | None = None
    simulate_failure_rank: int | None = None
    product_id: str | None = None


@app.post("/buyer/rank-preview")
def rank_preview(req: PurchaseRequest):
    """Runs the 3-layer decision pipeline without executing checkout, so a
    weight-slider UI can re-rank live without repeatedly attempting payment
    or consuming the mandate."""
    weights = _weights_from_query(req.w_payment_trust, req.w_promise_keeping, req.w_price_fit, req.w_reputation)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, category_id, budget_cap_paise, deadline_days, goal_text FROM mandates WHERE id = %s",
            (req.mandate_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="mandate not found")

        mandate_id, category_id, budget_cap_paise, deadline_days, goal_text = row
        mandate = {
            "id": str(mandate_id),
            "category_id": str(category_id),
            "budget_cap_paise": budget_cap_paise,
            "deadline_days": deadline_days,
            "goal_text": goal_text,
        }
        decision = run_buyer_pipeline(cur, mandate, weights=weights)
        conn.commit()

    return {"mandate_id": mandate["id"], "decision": decision}


@app.post("/buyer/purchase")
def purchase(req: PurchaseRequest):
    weights = _weights_from_query(req.w_payment_trust, req.w_promise_keeping, req.w_price_fit, req.w_reputation)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, category_id, budget_cap_paise, deadline_days, goal_text, expires_at, status FROM mandates WHERE id = %s",
            (req.mandate_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="mandate not found")

        mandate_id, category_id, budget_cap_paise, deadline_days, goal_text, expires_at, status = row
        if status != "active":
            raise HTTPException(status_code=409, detail=f"mandate is {status}, not active")

        mandate = {
            "id": str(mandate_id),
            "category_id": str(category_id),
            "budget_cap_paise": budget_cap_paise,
            "deadline_days": deadline_days,
            "goal_text": goal_text,
        }

        decision = run_buyer_pipeline(cur, mandate, weights=weights)
        if decision["status"] != "ranked":
            conn.commit()
            return {"mandate_id": mandate["id"], "decision": decision, "checkout": None}

        ranking = decision["ranking"]
        if req.product_id is not None:
            # Manual "buy this one" flow: attempt only the selected candidate, with
            # no fallback cascade to the rest of the ranking.
            ranking = [c for c in ranking if c["product_id"] == req.product_id]
            if not ranking:
                raise HTTPException(status_code=404, detail="product not in this mandate's ranked candidates")

        force_fail_ranks = {req.simulate_failure_rank} if req.simulate_failure_rank is not None else None
        checkout_result = checkout_with_fallback(cur, mandate["id"], ranking, force_fail_ranks=force_fail_ranks)

        new_status = "fulfilled" if checkout_result["status"] == "success" else "active"
        cur.execute("UPDATE mandates SET status = %s WHERE id = %s", (new_status, mandate["id"]))
        conn.commit()

    return {"mandate_id": mandate["id"], "decision": decision, "checkout": checkout_result}


@app.get("/audit/{mandate_id}")
def get_audit_trail(mandate_id: str):
    with get_connection() as conn, conn.cursor() as cur:
        trail = fetch_audit_trail(cur, mandate_id)
    return trail


class ReadinessRequest(BaseModel):
    items: list[str]


@app.post("/merchants/{merchant_id}/readiness")
def get_readiness(merchant_id: str, req: ReadinessRequest):
    return assess_catalog(req.items)


@app.get("/merchants/{merchant_id}/trust-mirror")
def get_trust_mirror(
    merchant_id: str,
    product_id: str | None = None,
    w_payment_trust: float | None = None,
    w_promise_keeping: float | None = None,
    w_price_fit: float | None = None,
    w_reputation: float | None = None,
):
    weights = _weights_from_query(w_payment_trust, w_promise_keeping, w_price_fit, w_reputation)
    with get_connection() as conn, conn.cursor() as cur:
        try:
            result = build_trust_mirror(cur, merchant_id, product_id=product_id, weights=weights)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        conn.commit()
    return result


@app.get("/merchants/{merchant_id}/benchmark")
def get_benchmark(
    merchant_id: str,
    w_payment_trust: float | None = None,
    w_promise_keeping: float | None = None,
    w_price_fit: float | None = None,
    w_reputation: float | None = None,
):
    weights = _weights_from_query(w_payment_trust, w_promise_keeping, w_price_fit, w_reputation)
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _fetch_merchant_category_id(cur, merchant_id)
        result = benchmark_merchant(cur, merchant_id, category_id, weights=weights)
        conn.commit()
    return result


@app.get("/merchants/{merchant_id}/growth-advisor")
def get_growth_advisor(
    merchant_id: str,
    w_payment_trust: float | None = None,
    w_promise_keeping: float | None = None,
    w_price_fit: float | None = None,
    w_reputation: float | None = None,
):
    weights = _weights_from_query(w_payment_trust, w_promise_keeping, w_price_fit, w_reputation)
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _fetch_merchant_category_id(cur, merchant_id)
        result = advise_growth(cur, merchant_id, category_id, weights=weights)
        conn.commit()
    return result


class WhatIfRequest(BaseModel):
    component: str
    target_value: float
    w_payment_trust: float | None = None
    w_promise_keeping: float | None = None
    w_price_fit: float | None = None
    w_reputation: float | None = None


@app.post("/merchants/{merchant_id}/growth-advisor/what-if")
def post_what_if(merchant_id: str, req: WhatIfRequest):
    if req.component not in DEFAULT_WEIGHTS:
        raise HTTPException(status_code=422, detail=f"unknown component: {req.component!r}")
    weights = _weights_from_query(req.w_payment_trust, req.w_promise_keeping, req.w_price_fit, req.w_reputation)
    with get_connection() as conn, conn.cursor() as cur:
        category_id = _fetch_merchant_category_id(cur, merchant_id)
        result = simulate_what_if(cur, merchant_id, category_id, req.component, req.target_value, weights=weights)
        conn.commit()
    return result


@app.get("/merchants/{merchant_id}/sla-advisor")
def get_sla_advisor(merchant_id: str):
    with get_connection() as conn, conn.cursor() as cur:
        try:
            result = advise_sla(cur, merchant_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@app.get("/merchants/{merchant_id}/lost-sale-signal")
def get_lost_sale_signal_endpoint(merchant_id: str):
    with get_connection() as conn, conn.cursor() as cur:
        result = get_lost_sale_signal(cur, merchant_id)
    return result
