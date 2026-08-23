"""Buyer Agent: three-layer decision pipeline, bounded by the mandate it
holds.

1. Hard Constraints — reject anything outside budget/deadline before scoring.
2. Learned Heuristics — rank survivors by the Composite Trust Engine's score.
3. Real-Time Optimization — tie-break near-equal top scores on live price.

Every layer's output is written to the audit trail as it runs.
"""

from __future__ import annotations

from app.audit_trail import log_audit
from app.text_extraction import extract_product_keywords
from app.trust_engine import score_merchant

REAL_TIME_TIE_EPSILON = 0.02


def fetch_candidates(cur, category_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT p.id, p.merchant_id, m.name, p.name, p.price_paise, m.declared_sla_days
        FROM products p JOIN merchants m ON m.id = p.merchant_id
        WHERE p.category_id = %s
        """,
        (category_id,),
    )
    return [
        {
            "product_id": str(r[0]),
            "merchant_id": str(r[1]),
            "merchant_name": r[2],
            "product_name": r[3],
            "price_paise": r[4],
            "declared_sla_days": r[5],
        }
        for r in cur.fetchall()
    ]


def apply_hard_constraints(candidates: list[dict], budget_cap_paise: int, deadline_days: int,
                            product_keywords: list[str] | None = None):
    """`product_keywords`, when non-empty, rejects any candidate whose product
    name doesn't contain at least one of them — e.g. a goal that says
    "earbuds" must never surface a charger just because both are Electronics.
    A true cutoff before scoring starts, same as budget/deadline: no amount of
    trust score should let the wrong product type outrank the right one."""
    survivors, rejected = [], []
    for c in candidates:
        reasons = []
        if c["price_paise"] > budget_cap_paise:
            reasons.append("over_budget")
        if c["declared_sla_days"] > deadline_days:
            reasons.append("misses_deadline")
        if product_keywords and not any(kw in c["product_name"].lower() for kw in product_keywords):
            reasons.append("wrong_product_type")
        if reasons:
            rejected.append({**c, "rejected_reasons": reasons})
        else:
            survivors.append(c)
    return survivors, rejected


def rank_by_trust(cur, candidates: list[dict], weights: dict | None = None) -> list[dict]:
    ranked = []
    for c in candidates:
        result = score_merchant(cur, c["merchant_id"], product_id=c["product_id"], weights=weights)
        ranked.append({
            **c,
            "composite_score": result["composite_score"],
            "trust_components": result["components"],
            "weights_used": result["weights"],
        })
    ranked.sort(key=lambda c: c["composite_score"], reverse=True)
    return ranked


def real_time_optimize(ranked_candidates: list[dict], live_price_lookup=None,
                        epsilon: float = REAL_TIME_TIE_EPSILON) -> list[dict]:
    if not ranked_candidates:
        return []
    if live_price_lookup is None:
        live_price_lookup = lambda product_id, fallback_price: fallback_price

    top_score = ranked_candidates[0]["composite_score"]
    tied = [c for c in ranked_candidates if top_score - c["composite_score"] <= epsilon]
    for c in tied:
        c["live_price_paise"] = live_price_lookup(c["product_id"], c["price_paise"])
    tied.sort(key=lambda c: c["live_price_paise"])

    return tied + ranked_candidates[len(tied):]


def run_buyer_pipeline(cur, mandate: dict, weights: dict | None = None, live_price_lookup=None) -> dict:
    mandate_id = mandate["id"]
    candidates = fetch_candidates(cur, mandate["category_id"])
    product_keywords = extract_product_keywords(mandate.get("goal_text") or "")

    survivors, rejected = apply_hard_constraints(
        candidates, mandate["budget_cap_paise"], mandate["deadline_days"], product_keywords
    )
    log_audit(cur, mandate_id, "hard_constraints", {
        "candidates_in": len(candidates),
        "survivors": len(survivors),
        "rejected": rejected,
        "product_keywords": product_keywords,
    })

    if not survivors:
        log_audit(cur, mandate_id, "decision", {"status": "no_candidates"})
        return {"status": "no_candidates", "ranking": []}

    ranked = rank_by_trust(cur, survivors, weights)
    log_audit(cur, mandate_id, "heuristics", {
        "ranking": [
            {"merchant_name": c["merchant_name"], "product_name": c["product_name"], "composite_score": c["composite_score"]}
            for c in ranked
        ],
    })

    optimized = real_time_optimize(ranked, live_price_lookup)
    log_audit(cur, mandate_id, "real_time_optimize", {
        "final_order": [
            {"merchant_name": c["merchant_name"], "product_name": c["product_name"]}
            for c in optimized
        ],
    })

    return {"status": "ranked", "ranking": optimized}
