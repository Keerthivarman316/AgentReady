from app.trust_integrity import assess_trust_integrity


def _components(payment_trust, promise_keeping, price_fit, reputation):
    return {
        "payment_trust": payment_trust,
        "promise_keeping": promise_keeping,
        "price_fit": price_fit,
        "reputation": reputation,
    }


def test_flags_flashy_risky_shaped_profile():
    # High reputation, but the operational signals it should track (payment
    # trust, promise keeping) don't back it up.
    result = assess_trust_integrity(_components(0.60, 0.55, 0.8, 0.94))
    assert result["flagged"] is True
    assert result["reason"] is not None


def test_does_not_flag_trusted_leader_shaped_profile():
    result = assess_trust_integrity(_components(0.95, 0.93, 0.8, 0.92))
    assert result["flagged"] is False
    assert result["reason"] is None


def test_does_not_flag_low_reputation_even_with_a_gap():
    # Below MIN_REPUTATION_TO_FLAG entirely — nothing suspicious about a
    # merchant that just has middling everything.
    result = assess_trust_integrity(_components(0.40, 0.35, 0.8, 0.60))
    assert result["flagged"] is False


def test_does_not_flag_high_reputation_backed_by_real_data():
    # High reputation AND high operational average — no gap, no flag.
    result = assess_trust_integrity(_components(0.85, 0.88, 0.8, 0.90))
    assert result["flagged"] is False


def test_flag_boundary_is_inclusive():
    # reputation exactly at MIN_REPUTATION_TO_FLAG, gap exactly at threshold.
    result = assess_trust_integrity(_components(0.62, 0.62, 0.8, 0.80))
    assert result["flagged"] is True
