"""Composite Trust Engine.

Computes the four AgentReady trust signals for a merchant (payment trust,
promise-keeping, price-competitiveness, reputation) and combines them into
one weighted composite score. Pure scoring math lives in functions that take
plain stats/dataclasses so it can be tested without a database; thin `fetch_*`
functions gather those stats from Postgres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from app.trust_integrity import assess_trust_integrity

# Reputation is real signal but self-reported and gameable — its weight is
# hard-capped so it can inform the ranking but never dominate it, regardless
# of what weight a caller (or a demo weight-slider) requests.
REPUTATION_WEIGHT_CAP = 0.20

DEFAULT_WEIGHTS = {
    "payment_trust": 0.35,
    "promise_keeping": 0.30,
    "price_fit": 0.20,
    "reputation": 0.15,
}

# Normalization ceilings: the rate at which a sub-signal bottoms out at 0.
REFUND_RATE_CEILING = 0.25
DISPUTE_RATE_CEILING = 0.08
DELIVERY_REFUND_CEILING = 0.15
COD_VIOLATION_CEILING = 0.40
SLA_GRACE_DAYS = 0.5


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class PaymentStats:
    captured: int
    failed: int
    refunds_processed: int
    disputes: int

    @property
    def total_attempts(self) -> int:
        return self.captured + self.failed


@dataclass
class PromiseStats:
    captured: int
    delivery_refunds: int
    cod_total: int
    cod_violations: int


def compute_payment_trust_score(stats: PaymentStats) -> float:
    if stats.total_attempts == 0:
        return 0.0
    success_rate = stats.captured / stats.total_attempts
    refund_rate = stats.refunds_processed / stats.captured if stats.captured else 0.0
    dispute_rate = stats.disputes / stats.captured if stats.captured else 0.0

    refund_component = 1 - _clamp01(refund_rate / REFUND_RATE_CEILING)
    dispute_component = 1 - _clamp01(dispute_rate / DISPUTE_RATE_CEILING)

    return _clamp01(0.5 * success_rate + 0.3 * refund_component + 0.2 * dispute_component)


def compute_promise_keeping_score(stats: PromiseStats) -> float:
    if stats.captured == 0:
        return 0.0
    delivery_refund_rate = stats.delivery_refunds / stats.captured
    delivery_refund_score = 1 - _clamp01(delivery_refund_rate / DELIVERY_REFUND_CEILING)

    if stats.cod_total == 0:
        return delivery_refund_score

    cod_violation_rate = stats.cod_violations / stats.cod_total
    cod_violation_score = 1 - _clamp01(cod_violation_rate / COD_VIOLATION_CEILING)

    return _clamp01(0.6 * delivery_refund_score + 0.4 * cod_violation_score)


def compute_reputation_score(avg_rating: float | None) -> float:
    if avg_rating is None:
        return 0.0
    return _clamp01(avg_rating / 5.0)


def compute_price_fit_score(price_paise: int, band_min: int, band_max: int) -> float:
    if band_max <= band_min:
        return 0.5
    position = (price_paise - band_min) / (band_max - band_min)
    return _clamp01(1 - position)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Clamp reputation's weight to its cap, then rescale all four so they sum to 1."""
    w = dict(weights)
    excess = max(0.0, w.get("reputation", 0.0) - REPUTATION_WEIGHT_CAP)
    if excess > 0:
        w["reputation"] = REPUTATION_WEIGHT_CAP
        others = [k for k in DEFAULT_WEIGHTS if k != "reputation"]
        other_total = sum(w.get(k, 0.0) for k in others)
        if other_total > 0:
            for k in others:
                w[k] = w.get(k, 0.0) + excess * (w.get(k, 0.0) / other_total)

    total = sum(w.get(k, 0.0) for k in DEFAULT_WEIGHTS)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: w.get(k, 0.0) / total for k in DEFAULT_WEIGHTS}


def compute_composite(components: dict[str, float], weights: dict[str, float] | None = None) -> tuple[float, dict[str, float]]:
    resolved_weights = normalize_weights(weights or DEFAULT_WEIGHTS)
    composite = sum(components[k] * resolved_weights[k] for k in DEFAULT_WEIGHTS)
    return _clamp01(composite), resolved_weights


# ---- DB-facing gathering functions -------------------------------------------------

def fetch_payment_stats(cur, merchant_id: str) -> PaymentStats:
    cur.execute(
        """
        SELECT
            count(*) FILTER (WHERE status = 'captured') AS captured,
            count(*) FILTER (WHERE status = 'failed') AS failed
        FROM transactions
        WHERE merchant_id = %s
        """,
        (merchant_id,),
    )
    captured, failed = cur.fetchone()

    cur.execute(
        """
        SELECT count(*)
        FROM refunds r JOIN transactions t ON t.id = r.transaction_id
        WHERE t.merchant_id = %s AND r.status = 'processed'
        """,
        (merchant_id,),
    )
    (refunds_processed,) = cur.fetchone()

    cur.execute(
        """
        SELECT count(*)
        FROM disputes d JOIN transactions t ON t.id = d.transaction_id
        WHERE t.merchant_id = %s
        """,
        (merchant_id,),
    )
    (disputes,) = cur.fetchone()

    return PaymentStats(captured=captured or 0, failed=failed or 0,
                         refunds_processed=refunds_processed or 0, disputes=disputes or 0)


def fetch_promise_stats(cur, merchant_id: str) -> PromiseStats:
    cur.execute(
        "SELECT count(*) FROM transactions WHERE merchant_id = %s AND status = 'captured'",
        (merchant_id,),
    )
    (captured,) = cur.fetchone()

    cur.execute(
        """
        SELECT count(*)
        FROM refunds r JOIN transactions t ON t.id = r.transaction_id
        WHERE t.merchant_id = %s AND r.status = 'processed'
          AND r.reason_code IN ('item_not_delivered', 'item_not_received')
        """,
        (merchant_id,),
    )
    (delivery_refunds,) = cur.fetchone()

    cur.execute(
        """
        SELECT t.order_created_at, t.payment_captured_at, m.declared_sla_days
        FROM transactions t JOIN merchants m ON m.id = t.merchant_id
        WHERE t.merchant_id = %s AND t.payment_method = 'cod'
          AND t.status = 'captured' AND t.payment_captured_at IS NOT NULL
        """,
        (merchant_id,),
    )
    rows = cur.fetchall()
    cod_total = len(rows)
    cod_violations = 0
    for order_created_at, payment_captured_at, declared_sla_days in rows:
        gap_days = (payment_captured_at - order_created_at) / timedelta(days=1)
        if gap_days > declared_sla_days + SLA_GRACE_DAYS:
            cod_violations += 1

    return PromiseStats(captured=captured or 0, delivery_refunds=delivery_refunds or 0,
                         cod_total=cod_total, cod_violations=cod_violations)


def fetch_reputation(cur, merchant_id: str) -> float | None:
    cur.execute("SELECT avg_rating FROM reputation WHERE merchant_id = %s", (merchant_id,))
    row = cur.fetchone()
    return float(row[0]) if row else None


def fetch_price_band(cur, category_id: str) -> tuple[int, int]:
    cur.execute(
        "SELECT min(price_paise), max(price_paise) FROM products WHERE category_id = %s",
        (category_id,),
    )
    band_min, band_max = cur.fetchone()
    return int(band_min or 0), int(band_max or 0)


def fetch_product(cur, product_id: str):
    cur.execute(
        "SELECT id, merchant_id, category_id, price_paise FROM products WHERE id = %s",
        (product_id,),
    )
    return cur.fetchone()


def score_merchant(cur, merchant_id: str, product_id: str | None = None,
                    weights: dict[str, float] | None = None,
                    price_band_cache: dict[str, tuple[int, int]] | None = None) -> dict:
    """`price_band_cache`, when given, is a caller-owned {category_id:
    (band_min, band_max)} dict this function reads from and writes to
    instead of re-querying fetch_price_band for a category it's already
    seen. A category's price band doesn't depend on which merchant is being
    scored, so a caller scoring many merchants in the same category in one
    pass (buyer_agent.rank_by_trust, benchmark_agent.compute_category_scores)
    should share one cache across the whole pass — without it, a category
    with thousands of merchants (or a merchant with many products) turns
    into thousands of near-identical round trips for the same answer.
    Callers scoring a single merchant in isolation can omit it; each lookup
    then costs one query, exactly as before this parameter existed."""
    def _price_band(category_id: str) -> tuple[int, int]:
        if price_band_cache is None:
            return fetch_price_band(cur, category_id)
        if category_id not in price_band_cache:
            price_band_cache[category_id] = fetch_price_band(cur, category_id)
        return price_band_cache[category_id]

    payment_trust = compute_payment_trust_score(fetch_payment_stats(cur, merchant_id))
    promise_keeping = compute_promise_keeping_score(fetch_promise_stats(cur, merchant_id))
    reputation = compute_reputation_score(fetch_reputation(cur, merchant_id))

    if product_id is not None:
        product = fetch_product(cur, product_id)
        if product is None:
            raise ValueError(f"product {product_id} not found")
        _, _, category_id, price_paise = product
        band_min, band_max = _price_band(category_id)
        price_fit = compute_price_fit_score(price_paise, band_min, band_max)
    else:
        cur.execute(
            "SELECT id, category_id, price_paise FROM products WHERE merchant_id = %s",
            (merchant_id,),
        )
        products = cur.fetchall()
        if not products:
            price_fit = 0.5
        else:
            fits = []
            for _, category_id, price_paise in products:
                band_min, band_max = _price_band(category_id)
                fits.append(compute_price_fit_score(price_paise, band_min, band_max))
            price_fit = sum(fits) / len(fits)

    components = {
        "payment_trust": payment_trust,
        "promise_keeping": promise_keeping,
        "price_fit": price_fit,
        "reputation": reputation,
    }
    composite, resolved_weights = compute_composite(components, weights)

    cur.execute(
        """
        INSERT INTO trust_score_history
            (merchant_id, payment_trust, promise_keeping, price_fit, reputation, composite_score, weights)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (merchant_id, payment_trust, promise_keeping, price_fit, reputation, composite,
         json.dumps(resolved_weights)),
    )

    return {
        "merchant_id": merchant_id,
        "product_id": product_id,
        "components": components,
        "weights": resolved_weights,
        "composite_score": composite,
        "integrity": assess_trust_integrity(components),
    }
