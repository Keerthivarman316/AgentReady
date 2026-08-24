"""Trust Mirror: the merchant-facing view of exactly what the Buyer Agent
sees — same components, same weights, plus which signal is dragging the
score down and which is carrying it.

Merchants aren't data scientists — a raw 0.83 composite score doesn't tell
them what an AI buyer actually concludes from it or what to do next. This
adds a plain-language layer on top of the same numbers (a 0-100 score, an
Excellent/Good/Fair/Needs Improvement label, and a one-paragraph summary),
so a merchant can act on their trust score without first learning what a
weighted composite is."""

from __future__ import annotations

from app.trust_engine import score_merchant

COMPONENT_LABELS = {
    "payment_trust": "payment trust",
    "promise_keeping": "promise-keeping",
    "price_fit": "price competitiveness",
    "reputation": "reputation",
}

# Composite score is a 0-1 weighted sum of four 0-1 components, so these
# thresholds are on the same scale as the score itself (shown to merchants
# multiplied by 100 for readability).
_SCORE_BANDS = [
    (0.85, "Excellent"),
    (0.70, "Good"),
    (0.55, "Fair"),
]


def score_label(composite_score: float) -> str:
    for threshold, label in _SCORE_BANDS:
        if composite_score >= threshold:
            return label
    return "Needs Improvement"


def build_trust_mirror(cur, merchant_id: str, product_id: str | None = None,
                        weights: dict | None = None) -> dict:
    result = score_merchant(cur, merchant_id, product_id=product_id, weights=weights)
    components = result["components"]
    resolved_weights = result["weights"]
    contributions = {k: components[k] * resolved_weights[k] for k in components}
    weakest_signal = min(components, key=components.get)
    strongest_signal = max(components, key=components.get)
    label = score_label(result["composite_score"])

    summary = (
        f"{label} trust score — {round(result['composite_score'] * 100)}/100. "
        f"AI buyers weighing {COMPONENT_LABELS[strongest_signal]} will favor you most; "
        f"{COMPONENT_LABELS[weakest_signal]} is your biggest opportunity to close before the next buyer evaluates you."
    )
    if result["integrity"]["flagged"]:
        summary += (
            " This merchant is currently excluded from AI buyer rankings — its reputation score is "
            "inconsistent with its own payment and delivery history (see Trust Integrity Monitor)."
        )

    return {
        **result,
        "contributions": contributions,
        "weakest_signal": weakest_signal,
        "strongest_signal": strongest_signal,
        "score_out_of_100": round(result["composite_score"] * 100),
        "score_label": label,
        "summary": summary,
    }
