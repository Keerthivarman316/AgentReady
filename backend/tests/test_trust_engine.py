import pytest

from app.trust_engine import (
    DEFAULT_WEIGHTS,
    REPUTATION_WEIGHT_CAP,
    PaymentStats,
    PromiseStats,
    compute_composite,
    compute_payment_trust_score,
    compute_price_fit_score,
    compute_promise_keeping_score,
    compute_reputation_score,
    normalize_weights,
)


def test_payment_trust_perfect_record():
    stats = PaymentStats(captured=100, failed=0, refunds_processed=0, disputes=0)
    assert compute_payment_trust_score(stats) == pytest.approx(1.0)


def test_payment_trust_no_attempts_is_zero():
    stats = PaymentStats(captured=0, failed=0, refunds_processed=0, disputes=0)
    assert compute_payment_trust_score(stats) == 0.0


def test_payment_trust_penalizes_disputes_more_than_refunds_per_unit():
    refund_heavy = PaymentStats(captured=100, failed=0, refunds_processed=10, disputes=0)
    dispute_heavy = PaymentStats(captured=100, failed=0, refunds_processed=0, disputes=10)
    # Disputes have a tighter ceiling (0.08 vs 0.25), so the same 10% rate hurts more.
    assert compute_payment_trust_score(dispute_heavy) < compute_payment_trust_score(refund_heavy)


def test_promise_keeping_perfect_record():
    stats = PromiseStats(captured=50, delivery_refunds=0, cod_total=20, cod_violations=0)
    assert compute_promise_keeping_score(stats) == pytest.approx(1.0)


def test_promise_keeping_no_cod_falls_back_to_delivery_refund_score():
    stats = PromiseStats(captured=50, delivery_refunds=0, cod_total=0, cod_violations=0)
    assert compute_promise_keeping_score(stats) == pytest.approx(1.0)


def test_promise_keeping_punishes_sla_violations():
    stats = PromiseStats(captured=50, delivery_refunds=2, cod_total=20, cod_violations=10)
    score = compute_promise_keeping_score(stats)
    assert 0.0 <= score < 0.8


def test_reputation_score_scales_with_rating():
    assert compute_reputation_score(5.0) == pytest.approx(1.0)
    assert compute_reputation_score(2.5) == pytest.approx(0.5)
    assert compute_reputation_score(None) == 0.0


def test_price_fit_cheapest_wins():
    assert compute_price_fit_score(100, 100, 200) == pytest.approx(1.0)
    assert compute_price_fit_score(200, 100, 200) == pytest.approx(0.0)
    assert compute_price_fit_score(150, 100, 200) == pytest.approx(0.5)


def test_price_fit_degenerate_band_returns_neutral():
    assert compute_price_fit_score(100, 100, 100) == 0.5


def test_normalize_weights_sums_to_one():
    weights = normalize_weights(DEFAULT_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_normalize_weights_caps_reputation_even_if_caller_overrides():
    # A caller (or demo weight-slider) tries to push reputation to 0.9 — the cap
    # must hold regardless, since an ungameable trust score is the whole point.
    weights = normalize_weights({"payment_trust": 0.05, "promise_keeping": 0.03,
                                  "price_fit": 0.02, "reputation": 0.9})
    assert weights["reputation"] == pytest.approx(REPUTATION_WEIGHT_CAP)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_composite_score_rewards_operational_trust_over_reputation():
    """The README's central, falsifiable claim: under default weights, a merchant
    with excellent payment/promise-keeping trust but middling reputation should
    outrank a merchant with flashy reputation but poor operational trust."""
    trusted_leader = {
        "payment_trust": 0.95,
        "promise_keeping": 0.92,
        "price_fit": 0.6,
        "reputation": 0.80,
    }
    flashy_risky = {
        "payment_trust": 0.55,
        "promise_keeping": 0.45,
        "price_fit": 0.6,
        "reputation": 0.98,
    }
    leader_score, _ = compute_composite(trusted_leader, DEFAULT_WEIGHTS)
    risky_score, _ = compute_composite(flashy_risky, DEFAULT_WEIGHTS)
    assert leader_score > risky_score


def test_composite_score_weight_slider_can_flip_ranking_toward_price():
    """Sliding weight fully onto price should be able to flip the ranking —
    proving the trade-off is a real, inspectable computation, not hardcoded."""
    cheap_but_untrusted = {"payment_trust": 0.3, "promise_keeping": 0.3, "price_fit": 1.0, "reputation": 0.5}
    trusted_but_pricier = {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.2, "reputation": 0.5}

    default_cheap, _ = compute_composite(cheap_but_untrusted, DEFAULT_WEIGHTS)
    default_trusted, _ = compute_composite(trusted_but_pricier, DEFAULT_WEIGHTS)
    assert default_trusted > default_cheap

    price_first_weights = {"payment_trust": 0.05, "promise_keeping": 0.05, "price_fit": 0.8, "reputation": 0.1}
    price_cheap, _ = compute_composite(cheap_but_untrusted, price_first_weights)
    price_trusted, _ = compute_composite(trusted_but_pricier, price_first_weights)
    assert price_cheap > price_trusted
