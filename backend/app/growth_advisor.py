"""Growth Advisor Agent: turns a benchmark gap into a ranked, specific fix
list, and re-runs the same Composite Trust Engine as a what-if simulation —
"if your dispute rate dropped to the category median, you'd move from 4th to
1st." Same scoring engine as the buyer side, run in reverse, not a separate
model.
"""

from __future__ import annotations

from app.benchmark_agent import compute_category_scores, summarize_benchmark
from app.buyer_weight_profiles import PERSONA_WEIGHTS
from app.trust_engine import DEFAULT_WEIGHTS, compute_composite, normalize_weights

FIX_MESSAGES = {
    "payment_trust": "Payment trust is below the category median — review failed-payment and processed-refund patterns; each one is pulling this signal down directly.",
    "promise_keeping": "Promise-keeping is below the category median — deliveries aren't consistently matching your declared SLA. Check delivery-related refund reasons, and see the SLA Advisor for a safer SLA to declare.",
    "price_fit": "Your price sits above the competitive range for this category relative to peers.",
    "reputation": "Reputation is below the category median — its weight is capped in the score, but it's still worth closing through service quality.",
}


def generate_fix_list(benchmark: dict, weights: dict | None = None) -> list[dict]:
    """Pure: takes a benchmark_agent.summarize_benchmark() result and ranks
    fixes by how much composite-score impact closing each gap would have."""
    resolved_weights = normalize_weights(weights or DEFAULT_WEIGHTS)
    components = benchmark.get("components") or {}
    fixes = []

    for component, median in benchmark["component_medians"].items():
        merchant_value = components.get(component)
        if merchant_value is None:
            continue
        gap = median - merchant_value
        if gap <= 0:
            continue
        fixes.append({
            "component": component,
            "merchant_value": merchant_value,
            "category_median": median,
            "gap": gap,
            "impact": gap * resolved_weights[component],
            "message": FIX_MESSAGES[component],
        })

    fixes.sort(key=lambda f: f["impact"], reverse=True)
    return fixes


def rerank_with_override(scores: list[dict], merchant_id: str, component: str,
                          target_value: float, weights: dict | None = None) -> dict:
    """Pure: re-scores `merchant_id` with one component overridden to
    `target_value`, and reports how its rank in `scores` shifts."""
    resolved_weights = normalize_weights(weights or DEFAULT_WEIGHTS)

    before_ranked = sorted(scores, key=lambda s: s["composite_score"], reverse=True)
    before_rank = next(i + 1 for i, s in enumerate(before_ranked) if s["merchant_id"] == merchant_id)
    before_score = next(s["composite_score"] for s in scores if s["merchant_id"] == merchant_id)

    updated = []
    for s in scores:
        if s["merchant_id"] == merchant_id:
            new_components = {**s["components"], component: target_value}
            new_composite, _ = compute_composite(new_components, resolved_weights)
            updated.append({**s, "composite_score": new_composite, "components": new_components})
        else:
            updated.append(s)

    after_ranked = sorted(updated, key=lambda s: s["composite_score"], reverse=True)
    after_rank = next(i + 1 for i, s in enumerate(after_ranked) if s["merchant_id"] == merchant_id)
    after_score = next(s["composite_score"] for s in updated if s["merchant_id"] == merchant_id)

    return {
        "merchant_id": merchant_id,
        "component": component,
        "target_value": target_value,
        "before_rank": before_rank,
        "after_rank": after_rank,
        "before_score": before_score,
        "after_score": after_score,
        "total_in_category": len(scores),
    }


def rank_by_persona(scores: list[dict], merchant_id: str) -> dict:
    """Pure: `scores` is a compute_category_scores() result (weight-independent
    components already computed once). Re-derives composite scores under each
    named buyer persona's weights without re-touching the database or writing
    another trust_score_history row per persona — components don't change
    with weights, only how they're combined."""
    breakdown = {}
    for persona, persona_weights in PERSONA_WEIGHTS.items():
        rescored = [
            {**s, "composite_score": compute_composite(s["components"], persona_weights)[0]}
            for s in scores
        ]
        ranked = sorted(rescored, key=lambda s: s["composite_score"], reverse=True)
        rank = next((i + 1 for i, s in enumerate(ranked) if s["merchant_id"] == merchant_id), None)
        mine = next((s for s in ranked if s["merchant_id"] == merchant_id), None)
        breakdown[persona] = {
            "rank": rank,
            "composite_score": mine["composite_score"] if mine else None,
            "total_in_category": len(scores),
        }
    return breakdown


def advise_growth(cur, merchant_id: str, category_id: str, weights: dict | None = None) -> dict:
    scores = compute_category_scores(cur, category_id, weights=weights)
    benchmark = summarize_benchmark(scores, merchant_id)
    fixes = generate_fix_list(benchmark, weights)
    persona_breakdown = rank_by_persona(scores, merchant_id)
    return {"benchmark": benchmark, "fixes": fixes, "persona_breakdown": persona_breakdown}


def simulate_what_if(cur, merchant_id: str, category_id: str, component: str,
                      target_value: float, weights: dict | None = None) -> dict:
    scores = compute_category_scores(cur, category_id, weights=weights)
    return rerank_with_override(scores, merchant_id, component, target_value, weights)
