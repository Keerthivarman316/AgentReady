"""Buyer Weight Profiles: turns the weights_used real Buyer Agent runs already
log per ranking into merchant-facing intelligence about *what kind of buyer*
evaluates them and how they do under each. Not synthetic — it only reflects
mandates real buyer runs actually scored this merchant against (the same
`heuristics` audit layer buyer_agent.py writes on every ranked pipeline run),
so it starts empty on a fresh database and grows with real usage, the same
pattern as lost_sale_signal.py.

A buyer's weights are adjustable per-purchase (the UI sliders, or a future
agent that reasons about its own priorities) — the four Composite Trust
Engine components can be weighted toward price, trust, delivery speed, or
left at the platform default. This module buckets any weight vector into one
of a few named personas by its dominant component, so a merchant sees "62% of
buyers who considered you this week were Budget Hunters, and you rank #4 with
them" instead of a single opaque default-weighted score.
"""

from __future__ import annotations

from collections import defaultdict

from app.trust_engine import DEFAULT_WEIGHTS

# Tolerance for treating a weight vector as "the platform default" rather
# than a deliberately adjusted persona.
BALANCED_TOLERANCE = 0.02

PERSONA_LABELS = {
    "payment_trust": "Trust-First",
    "promise_keeping": "Fast-Shipper",
    "price_fit": "Budget Hunter",
    "reputation": "Reputation-Led",
}

PERSONA_DESCRIPTIONS = {
    "Balanced (default)": "Weighs all four trust signals at the platform default — no strong preference.",
    "Trust-First": "Weighs payment trust (failed-payment/refund history) above everything else.",
    "Fast-Shipper": "Weighs promise-keeping (on-time delivery vs. declared SLA) above everything else.",
    "Budget Hunter": "Weighs price fit above everything else — the cheapest trustworthy option wins.",
    "Reputation-Led": "Weighs self-reported reputation above everything else.",
}

# Representative weight vectors for each persona, used to drive Growth
# Advisor's multi-persona what-if simulation. These aren't the only weight
# vectors that would classify into a given persona (classify_weights buckets
# by dominant component, not exact match) — they're one concrete example of
# each, run through normalize_weights() like any other caller-supplied
# weights (so "Reputation-Led" ends up capped at REPUTATION_WEIGHT_CAP, same
# as a real buyer's would).
PERSONA_WEIGHTS = {
    "Balanced (default)": dict(DEFAULT_WEIGHTS),
    "Trust-First": {"payment_trust": 0.55, "promise_keeping": 0.20, "price_fit": 0.15, "reputation": 0.10},
    "Fast-Shipper": {"payment_trust": 0.20, "promise_keeping": 0.55, "price_fit": 0.15, "reputation": 0.10},
    "Budget Hunter": {"payment_trust": 0.20, "promise_keeping": 0.20, "price_fit": 0.50, "reputation": 0.10},
    "Reputation-Led": {"payment_trust": 0.20, "promise_keeping": 0.20, "price_fit": 0.10, "reputation": 0.50},
}


def classify_weights(weights: dict) -> str:
    """Pure: buckets a resolved weight vector into a named persona by its
    dominant component, unless it's within tolerance of the platform
    default."""
    if all(abs(weights.get(k, 0) - v) <= BALANCED_TOLERANCE for k, v in DEFAULT_WEIGHTS.items()):
        return "Balanced (default)"
    dominant = max(PERSONA_LABELS, key=lambda k: weights.get(k, 0))
    return PERSONA_LABELS[dominant]


def fetch_weight_events(cur, merchant_id: str) -> list[dict]:
    """One entry per real Buyer Agent ranking run that scored this merchant —
    the weights it used, this merchant's rank in that run, and how many
    candidates it was ranked against."""
    cur.execute(
        """
        SELECT a.payload -> 'weights_used', (r.value ->> 'rank')::int, jsonb_array_length(a.payload -> 'ranking')
        FROM audit_trail a, jsonb_array_elements(a.payload -> 'ranking') AS r
        WHERE a.layer = 'heuristics' AND r.value ->> 'merchant_id' = %s
        """,
        (merchant_id,),
    )
    return [{"weights": row[0], "rank": row[1], "field_size": row[2]} for row in cur.fetchall()]


def summarize_weight_profiles(events: list[dict]) -> dict:
    """Pure: weight events in, per-persona breakdown out — share of buyers,
    and how this merchant fares (avg rank, avg field size) under each."""
    sample_size = len(events)
    if sample_size == 0:
        return {"sample_size": 0, "profile_breakdown": {}}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        persona = classify_weights(event["weights"])
        grouped[persona].append(event)

    breakdown = {}
    for persona, group in grouped.items():
        breakdown[persona] = {
            "share": len(group) / sample_size,
            "avg_rank": sum(e["rank"] for e in group) / len(group),
            "avg_field_size": sum(e["field_size"] for e in group) / len(group),
            "description": PERSONA_DESCRIPTIONS[persona],
        }

    return {"sample_size": sample_size, "profile_breakdown": breakdown}


def get_weight_profile_signal(cur, merchant_id: str) -> dict:
    events = fetch_weight_events(cur, merchant_id)
    return summarize_weight_profiles(events)
