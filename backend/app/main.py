from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import get_connection
from app.graph import ping_graph
from app.trust_engine import DEFAULT_WEIGHTS, score_merchant

app = FastAPI(title="AgentReady API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
