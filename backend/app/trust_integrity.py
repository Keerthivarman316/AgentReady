"""Trust Integrity Monitor: flags a merchant whose reputation score sits well
above what its own payment/promise-keeping data supports — a pattern
consistent with inflated or purchased reviews. Nothing in the composite score
itself resists gaming; this is the layer that watches the trust signal
rather than just computing it.

Pure: takes the same `components` dict trust_engine.score_merchant() already
computes, no DB access of its own.
"""

from __future__ import annotations

# Only flag genuinely high reputation — a mediocre score that's merely a bit
# above middling operational data isn't suspicious, it's just optimistic.
MIN_REPUTATION_TO_FLAG = 0.80

# How far reputation has to sit above the average of payment_trust and
# promise_keeping before the gap looks manufactured rather than earned.
REPUTATION_MISMATCH_THRESHOLD = 0.18


def assess_trust_integrity(components: dict) -> dict:
    reputation = components["reputation"]
    operational_average = (components["payment_trust"] + components["promise_keeping"]) / 2
    gap = reputation - operational_average

    flagged = reputation >= MIN_REPUTATION_TO_FLAG and gap >= REPUTATION_MISMATCH_THRESHOLD

    reason = None
    if flagged:
        reason = (
            f"Reputation ({reputation:.2f}) sits well above what payment and promise-keeping "
            f"data supports ({operational_average:.2f}) — a pattern consistent with inflated "
            f"or purchased reviews."
        )

    return {
        "flagged": flagged,
        "reputation": reputation,
        "operational_average": operational_average,
        "gap": gap,
        "reason": reason,
    }
