from app.buyer_agent import apply_hard_constraints, compute_counter_offer, real_time_optimize


def _candidate(product_id, price, sla_days, score=None, product_name=None):
    c = {
        "product_id": product_id,
        "merchant_id": f"m-{product_id}",
        "merchant_name": f"Merchant {product_id}",
        "product_name": product_name or f"Product {product_id}",
        "price_paise": price,
        "declared_sla_days": sla_days,
    }
    if score is not None:
        c["composite_score"] = score
    return c


def test_hard_constraints_filters_over_budget():
    candidates = [_candidate("a", 100, 3), _candidate("b", 500, 3)]
    survivors, rejected = apply_hard_constraints(candidates, budget_cap_paise=200, deadline_days=5)
    assert [c["product_id"] for c in survivors] == ["a"]
    assert rejected[0]["rejected_reasons"] == ["over_budget"]


def test_hard_constraints_filters_missed_deadline():
    candidates = [_candidate("a", 100, 10)]
    survivors, rejected = apply_hard_constraints(candidates, budget_cap_paise=200, deadline_days=5)
    assert survivors == []
    assert rejected[0]["rejected_reasons"] == ["misses_deadline"]


def test_hard_constraints_can_reject_for_both_reasons():
    candidates = [_candidate("a", 500, 10)]
    _, rejected = apply_hard_constraints(candidates, budget_cap_paise=200, deadline_days=5)
    assert set(rejected[0]["rejected_reasons"]) == {"over_budget", "misses_deadline"}


def test_hard_constraints_rejects_wrong_product_type():
    candidates = [
        _candidate("a", 100, 3, product_name="Wireless Earbuds Pro"),
        _candidate("b", 100, 3, product_name="USB-C Fast Charger 65W"),
    ]
    survivors, rejected = apply_hard_constraints(
        candidates, budget_cap_paise=200, deadline_days=5, product_keywords=["earbud"]
    )
    assert [c["product_id"] for c in survivors] == ["a"]
    assert rejected[0]["rejected_reasons"] == ["wrong_product_type"]


def test_hard_constraints_no_product_keywords_keeps_everything_in_category():
    candidates = [
        _candidate("a", 100, 3, product_name="Wireless Earbuds Pro"),
        _candidate("b", 100, 3, product_name="USB-C Fast Charger 65W"),
    ]
    survivors, _ = apply_hard_constraints(candidates, budget_cap_paise=200, deadline_days=5, product_keywords=[])
    assert {c["product_id"] for c in survivors} == {"a", "b"}


def test_real_time_optimize_no_tie_keeps_order():
    ranked = [_candidate("a", 100, 3, score=0.9), _candidate("b", 100, 3, score=0.5)]
    result = real_time_optimize(ranked)
    assert [c["product_id"] for c in result] == ["a", "b"]


def test_real_time_optimize_breaks_tie_by_live_price():
    ranked = [_candidate("a", 300, 3, score=0.80), _candidate("b", 100, 3, score=0.79)]

    def live_price_lookup(product_id, fallback):
        return {"a": 300, "b": 100}[product_id]

    result = real_time_optimize(ranked, live_price_lookup=live_price_lookup, epsilon=0.02)
    assert result[0]["product_id"] == "b"


def test_real_time_optimize_does_not_tie_break_beyond_epsilon():
    ranked = [_candidate("a", 300, 3, score=0.90), _candidate("b", 100, 3, score=0.50)]

    def live_price_lookup(product_id, fallback):
        return {"a": 300, "b": 100}[product_id]

    result = real_time_optimize(ranked, live_price_lookup=live_price_lookup, epsilon=0.02)
    assert result[0]["product_id"] == "a"


def test_real_time_optimize_empty_input():
    assert real_time_optimize([]) == []


def _scored_candidate(product_id, price, composite_score, payment_trust=0.9, promise_keeping=0.9, reputation=0.8):
    c = _candidate(product_id, price, sla_days=3)
    c["composite_score"] = composite_score
    c["trust_components"] = {
        "payment_trust": payment_trust,
        "promise_keeping": promise_keeping,
        "price_fit": 0.5,
        "reputation": reputation,
    }
    return c


def test_compute_counter_offer_finds_minimal_sufficient_discount():
    # band 100_000-200_000; runner priced near band_max so price_fit has
    # plenty of room to improve as the price drops.
    runner_up = _scored_candidate("runner", price=180_000, composite_score=0.745)
    winner = _scored_candidate("winner", price=150_000, composite_score=0.76)

    offer = compute_counter_offer(runner_up, winner, band_min=100_000, band_max=200_000)

    assert offer is not None
    assert offer["discount_pct"] == 0.06
    assert offer["countered_price_paise"] == 169_200
    assert offer["new_composite_score"] > winner["composite_score"]


def test_compute_counter_offer_none_when_gap_exceeds_epsilon():
    runner_up = _scored_candidate("runner", price=180_000, composite_score=0.745)
    winner = _scored_candidate("winner", price=150_000, composite_score=0.95)

    assert compute_counter_offer(runner_up, winner, band_min=100_000, band_max=200_000) is None


def test_compute_counter_offer_none_when_even_max_discount_is_not_enough():
    # Runner already sits near band_min, so a price cut has almost nowhere
    # left to move price_fit — the achievable improvement is smaller than
    # the gap it needs to close.
    runner_up = _scored_candidate("runner", price=110_000, composite_score=0.885)
    winner = _scored_candidate("winner", price=150_000, composite_score=0.91)

    assert compute_counter_offer(runner_up, winner, band_min=100_000, band_max=200_000) is None
