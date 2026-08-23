"""Buyer Agent: three-layer decision pipeline, bounded by the mandate it
holds.

1. Hard Constraints — reject anything outside budget/deadline before scoring.
2. Learned Heuristics — rank survivors by the Composite Trust Engine's score.
3. Real-Time Optimization — tie-break near-equal top scores on live price.

A merchant whose trust signal is quarantined (see trust_integrity.py) never
reaches layer 2. After layer 3, the runner-up gets one bounded shot at a
counter-offer if it's close enough to the winner — see
apply_counter_offer().

Every layer's output is written to the audit trail as it runs.
"""

from __future__ import annotations

from app.audit_trail import log_audit
from app.text_extraction import extract_product_keywords
from app.trust_engine import compute_composite, compute_price_fit_score, fetch_price_band, score_merchant

REAL_TIME_TIE_EPSILON = 0.02

# A runner-up only gets a counter-offer if it's within this of the winner's
# composite score — far enough behind and no discount should be able to
# rescue it.
COUNTER_OFFER_EPSILON = 0.03

# Discount steps tried smallest-first, so the runner-up offers the minimum
# cut that would actually win rather than an arbitrary maximum one. 10% caps
# how much margin a merchant is assumed willing to give up on the spot.
COUNTER_OFFER_DISCOUNT_STEPS_PCT = [0.02, 0.04, 0.06, 0.08, 0.10]


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


def rank_by_trust(cur, candidates: list[dict], weights: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Returns (ranked, quarantined). A candidate whose trust-integrity check
    flags it (reputation inconsistent with its own operational data) never
    reaches the buyer — quarantined, not merely ranked low."""
    ranked, quarantined = [], []
    for c in candidates:
        result = score_merchant(cur, c["merchant_id"], product_id=c["product_id"], weights=weights)
        enriched = {
            **c,
            "composite_score": result["composite_score"],
            "trust_components": result["components"],
            "weights_used": result["weights"],
        }
        if result["integrity"]["flagged"]:
            quarantined.append({**enriched, "integrity_reason": result["integrity"]["reason"]})
        else:
            ranked.append(enriched)
    ranked.sort(key=lambda c: c["composite_score"], reverse=True)
    return ranked, quarantined


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


def compute_counter_offer(runner_up: dict, winner: dict, band_min: int, band_max: int,
                           weights: dict | None = None) -> dict | None:
    """Pure: if `runner_up` is within COUNTER_OFFER_EPSILON of `winner`,
    finds the smallest bounded discount on runner_up's own price that would
    flip the ranking, by recomputing price_fit -> composite at each step.
    Returns None if too far behind, or if even the maximum discount isn't
    enough."""
    if winner["composite_score"] - runner_up["composite_score"] > COUNTER_OFFER_EPSILON:
        return None

    original_price = runner_up["price_paise"]
    for pct in COUNTER_OFFER_DISCOUNT_STEPS_PCT:
        candidate_price = int(original_price * (1 - pct))
        new_price_fit = compute_price_fit_score(candidate_price, band_min, band_max)
        new_components = {**runner_up["trust_components"], "price_fit": new_price_fit}
        new_composite, _ = compute_composite(new_components, weights)
        if new_composite > winner["composite_score"]:
            return {
                "merchant_id": runner_up["merchant_id"],
                "merchant_name": runner_up["merchant_name"],
                "product_id": runner_up["product_id"],
                "product_name": runner_up["product_name"],
                "original_price_paise": original_price,
                "countered_price_paise": candidate_price,
                "discount_pct": pct,
                "new_price_fit": new_price_fit,
                "new_composite_score": new_composite,
                "outcome": "won",
            }
    return None


def apply_counter_offer(cur, ranked_candidates: list[dict], category_id: str,
                         weights: dict | None = None) -> tuple[list[dict], dict | None]:
    """The runner-up (rank 2) gets one bounded shot at overtaking the winner
    before checkout. If it succeeds, it's promoted to rank 1 with its
    discounted price/score; both candidates are marked so the audit trail
    and UI can show what happened."""
    if len(ranked_candidates) < 2:
        return ranked_candidates, None

    winner, runner_up = ranked_candidates[0], ranked_candidates[1]
    band_min, band_max = fetch_price_band(cur, category_id)
    offer = compute_counter_offer(runner_up, winner, band_min, band_max, weights)
    if offer is None:
        return ranked_candidates, None

    promoted = {
        **runner_up,
        "price_paise": offer["countered_price_paise"],
        "live_price_paise": offer["countered_price_paise"],
        "composite_score": offer["new_composite_score"],
        "trust_components": {**runner_up["trust_components"], "price_fit": offer["new_price_fit"]},
        "countered": True,
    }
    displaced = {**winner, "countered_against": True}
    return [promoted, displaced] + ranked_candidates[2:], offer


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

    ranked, quarantined = rank_by_trust(cur, survivors, weights)
    log_audit(cur, mandate_id, "trust_integrity", {
        "quarantined_count": len(quarantined),
        "reasons": [
            {"merchant_name": c["merchant_name"], "product_name": c["product_name"], "reason": c["integrity_reason"]}
            for c in quarantined
        ],
    })

    if not ranked:
        log_audit(cur, mandate_id, "decision", {"status": "no_candidates"})
        return {"status": "no_candidates", "ranking": [], "quarantined_count": len(quarantined)}

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

    final_ranking, counter_offer = apply_counter_offer(cur, optimized, mandate["category_id"], weights)
    if counter_offer:
        log_audit(cur, mandate_id, "counter_offer", counter_offer)

    return {
        "status": "ranked",
        "ranking": final_ranking,
        "quarantined_count": len(quarantined),
        "counter_offer": counter_offer,
    }
