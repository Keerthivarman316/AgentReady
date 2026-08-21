"""Trust Mirror: the merchant-facing view of exactly what the Buyer Agent
sees — same components, same weights, plus which signal is dragging the
score down and which is carrying it."""

from __future__ import annotations

from app.trust_engine import score_merchant


def build_trust_mirror(cur, merchant_id: str, product_id: str | None = None,
                        weights: dict | None = None) -> dict:
    result = score_merchant(cur, merchant_id, product_id=product_id, weights=weights)
    components = result["components"]
    resolved_weights = result["weights"]
    contributions = {k: components[k] * resolved_weights[k] for k in components}

    return {
        **result,
        "contributions": contributions,
        "weakest_signal": min(components, key=components.get),
        "strongest_signal": max(components, key=components.get),
    }
