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

from typing import Any, Callable, TypedDict

from langgraph.graph import END, StateGraph

from app.audit_trail import log_audit
from app.text_extraction import extract_product_keywords
from app.trust_engine import (
    bulk_fetch_merchant_stats,
    compute_composite,
    compute_price_fit_score,
    fetch_price_band,
    score_merchant,
)

REAL_TIME_TIE_EPSILON = 0.02

# A search with no real constraint (huge budget, no product keyword) can
# match every product in a category -- at a 100x-scale dataset that's tens
# of thousands of candidates, which is never a reasonable ranking to hand a
# buyer (or a browser) regardless of how fast scoring them all is. Capped
# post-sort, so it's always the genuine top scorers that survive, not an
# arbitrary DB-order slice.
MAX_RANKED_RESULTS = 200

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
    trust score should let the wrong product type outrank the right one.

    A semantic-similarity fallback for the empty-keywords case was tried and
    reverted: live testing against the real embeddings found similarity
    scores don't reliably separate "the goal implies one specific product"
    from "genuinely vague category browse" — a vague query ("electronics
    under 4000") scored *higher* against one arbitrary product than a
    genuinely specific one did, so no threshold could safely narrow one
    without also wrongly narrowing the other. Semantic search is real and
    available (see app/semantic_search.py, GET /products/search) but stays
    an explicit, opt-in capability rather than an automatic hard-constraint
    filter here."""
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
    # All candidates here are already scoped to one category (fetch_candidates
    # filters by category_id), so their price band is identical -- shared
    # across every score_merchant call instead of re-querying it once per
    # candidate. And a merchant with several surviving products (up to a
    # dozen, one per product type) would otherwise get its
    # payment/promise/reputation stats recomputed once per product. Both
    # matter once a search has thousands of survivors -- but even scoped to
    # one merchant per lookup, thousands of *merchants* means thousands of
    # round trips; bulk_fetch_merchant_stats prefetches all of them in a
    # handful of GROUP BY queries instead, so score_merchant's cache lookups
    # below are always hits, never a fallback per-merchant query.
    price_band_cache: dict[str, tuple[int, int]] = {}
    merchant_stats_cache = bulk_fetch_merchant_stats(cur, list({c["merchant_id"] for c in candidates}))
    for c in candidates:
        result = score_merchant(cur, c["merchant_id"], product_id=c["product_id"], weights=weights,
                                 price_band_cache=price_band_cache, merchant_stats_cache=merchant_stats_cache)
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
    return ranked[:MAX_RANKED_RESULTS], quarantined


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


class BuyerDecisionState(TypedDict, total=False):
    """Carries a live `cur` through the graph the same way it was threaded
    through the old direct call chain — this graph runs in-process with no
    checkpointer, so nothing here is ever serialized."""
    cur: Any
    mandate_id: str
    category_id: str
    budget_cap_paise: int
    deadline_days: int
    goal_text: str
    weights: dict | None
    live_price_lookup: Callable | None
    candidates: list[dict]
    product_keywords: list[str]
    survivors: list[dict]
    ranked: list[dict]
    quarantined: list[dict]
    optimized: list[dict]
    final_ranking: list[dict]
    counter_offer: dict | None
    status: str


def _node_fetch_and_constrain(state: BuyerDecisionState) -> dict:
    cur, mandate_id = state["cur"], state["mandate_id"]
    candidates = fetch_candidates(cur, state["category_id"])
    product_keywords = extract_product_keywords(state.get("goal_text") or "")
    survivors, rejected = apply_hard_constraints(
        candidates, state["budget_cap_paise"], state["deadline_days"], product_keywords
    )
    log_audit(cur, mandate_id, "hard_constraints", {
        "candidates_in": len(candidates), "survivors": len(survivors),
        "rejected": rejected, "product_keywords": product_keywords,
    })
    return {"candidates": candidates, "product_keywords": product_keywords, "survivors": survivors}


def _route_after_constraints(state: BuyerDecisionState) -> str:
    return "rank" if state["survivors"] else "no_candidates"


def _node_rank(state: BuyerDecisionState) -> dict:
    cur, mandate_id = state["cur"], state["mandate_id"]
    ranked, quarantined = rank_by_trust(cur, state["survivors"], state["weights"])
    log_audit(cur, mandate_id, "trust_integrity", {
        "quarantined_count": len(quarantined),
        "reasons": [
            {"merchant_name": c["merchant_name"], "product_name": c["product_name"], "reason": c["integrity_reason"]}
            for c in quarantined
        ],
    })
    return {"ranked": ranked, "quarantined": quarantined}


def _route_after_rank(state: BuyerDecisionState) -> str:
    return "optimize" if state["ranked"] else "no_candidates"


def _node_optimize(state: BuyerDecisionState) -> dict:
    cur, mandate_id, ranked = state["cur"], state["mandate_id"], state["ranked"]
    log_audit(cur, mandate_id, "heuristics", {
        "weights_used": ranked[0]["weights_used"],
        "ranking": [
            {
                "merchant_id": c["merchant_id"], "merchant_name": c["merchant_name"],
                "product_name": c["product_name"], "composite_score": c["composite_score"], "rank": i + 1,
            }
            for i, c in enumerate(ranked)
        ],
    })
    optimized = real_time_optimize(ranked, state.get("live_price_lookup"))
    log_audit(cur, mandate_id, "real_time_optimize", {
        "final_order": [
            {"merchant_name": c["merchant_name"], "product_name": c["product_name"]}
            for c in optimized
        ],
    })
    return {"optimized": optimized}


def _node_counter_offer(state: BuyerDecisionState) -> dict:
    cur, mandate_id = state["cur"], state["mandate_id"]
    final_ranking, counter_offer = apply_counter_offer(
        cur, state["optimized"], state["category_id"], state["weights"]
    )
    if counter_offer:
        log_audit(cur, mandate_id, "counter_offer", counter_offer)
    return {"final_ranking": final_ranking, "counter_offer": counter_offer, "status": "ranked"}


def _node_no_candidates(state: BuyerDecisionState) -> dict:
    log_audit(state["cur"], state["mandate_id"], "decision", {"status": "no_candidates"})
    result = {"status": "no_candidates", "final_ranking": []}
    if "quarantined" in state:
        result["quarantined_count"] = len(state["quarantined"])
    return result


def _build_buyer_decision_graph():
    graph = StateGraph(BuyerDecisionState)
    graph.add_node("fetch_and_constrain", _node_fetch_and_constrain)
    graph.add_node("rank", _node_rank)
    graph.add_node("optimize", _node_optimize)
    graph.add_node("apply_counter_offer_step", _node_counter_offer)
    graph.add_node("no_candidates", _node_no_candidates)

    graph.set_entry_point("fetch_and_constrain")
    graph.add_conditional_edges("fetch_and_constrain", _route_after_constraints, {
        "rank": "rank", "no_candidates": "no_candidates",
    })
    graph.add_conditional_edges("rank", _route_after_rank, {
        "optimize": "optimize", "no_candidates": "no_candidates",
    })
    graph.add_edge("optimize", "apply_counter_offer_step")
    graph.add_edge("apply_counter_offer_step", END)
    graph.add_edge("no_candidates", END)
    return graph.compile()


buyer_decision_graph = _build_buyer_decision_graph()


def run_buyer_pipeline(cur, mandate: dict, weights: dict | None = None, live_price_lookup=None) -> dict:
    result = buyer_decision_graph.invoke({
        "cur": cur,
        "mandate_id": mandate["id"],
        "category_id": mandate["category_id"],
        "budget_cap_paise": mandate["budget_cap_paise"],
        "deadline_days": mandate["deadline_days"],
        "goal_text": mandate.get("goal_text") or "",
        "weights": weights,
        "live_price_lookup": live_price_lookup,
    })

    output = {"status": result["status"], "ranking": result["final_ranking"]}
    if result["status"] == "ranked":
        output["quarantined_count"] = len(result.get("quarantined", []))
        output["counter_offer"] = result.get("counter_offer")
    elif "quarantined_count" in result:
        output["quarantined_count"] = result["quarantined_count"]
    return output
