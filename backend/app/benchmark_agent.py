"""Benchmark Agent: places a merchant's trust score against its category's
median — turning an abstract score into a concrete competitive gap. No named
competitors are ever surfaced, even in the synthetic data — only the
aggregate median and the merchant's own rank position."""

from __future__ import annotations

import statistics

from app.trust_engine import score_merchant


def compute_category_scores(cur, category_id: str, weights: dict | None = None) -> list[dict]:
    cur.execute("SELECT DISTINCT merchant_id FROM products WHERE category_id = %s", (category_id,))
    merchant_ids = [str(row[0]) for row in cur.fetchall()]

    scores = []
    for merchant_id in merchant_ids:
        result = score_merchant(cur, merchant_id, product_id=None, weights=weights)
        scores.append({
            "merchant_id": merchant_id,
            "composite_score": result["composite_score"],
            "components": result["components"],
        })
    return scores


def summarize_benchmark(scores: list[dict], merchant_id: str) -> dict:
    """Pure: turns a list of {merchant_id, composite_score, components} into
    the merchant's rank, gap-to-median, and per-component category medians."""
    ranked = sorted(scores, key=lambda s: s["composite_score"], reverse=True)
    rank = next((i + 1 for i, s in enumerate(ranked) if s["merchant_id"] == merchant_id), None)
    mine = next((s for s in scores if s["merchant_id"] == merchant_id), None)

    composite_values = [s["composite_score"] for s in scores]
    median_score = statistics.median(composite_values) if composite_values else 0.0

    component_medians = {}
    if scores:
        for key in scores[0]["components"]:
            component_medians[key] = statistics.median(s["components"][key] for s in scores)

    return {
        "merchant_id": merchant_id,
        "composite_score": mine["composite_score"] if mine else None,
        "components": mine["components"] if mine else None,
        "category_median_score": median_score,
        "gap_to_median": (mine["composite_score"] - median_score) if mine else None,
        "rank": rank,
        "total_in_category": len(scores),
        "component_medians": component_medians,
    }


def benchmark_merchant(cur, merchant_id: str, category_id: str, weights: dict | None = None) -> dict:
    scores = compute_category_scores(cur, category_id, weights=weights)
    return summarize_benchmark(scores, merchant_id)
