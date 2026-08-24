from app.buyer_weight_profiles import PERSONA_WEIGHTS, classify_weights, summarize_weight_profiles
from app.trust_engine import DEFAULT_WEIGHTS


def test_classify_weights_default_is_balanced():
    assert classify_weights(DEFAULT_WEIGHTS) == "Balanced (default)"


def test_classify_weights_within_tolerance_is_balanced():
    nudged = {**DEFAULT_WEIGHTS, "payment_trust": DEFAULT_WEIGHTS["payment_trust"] + 0.01}
    assert classify_weights(nudged) == "Balanced (default)"


def test_classify_weights_price_dominant_is_budget_hunter():
    weights = {"payment_trust": 0.15, "promise_keeping": 0.15, "price_fit": 0.6, "reputation": 0.1}
    assert classify_weights(weights) == "Budget Hunter"


def test_classify_weights_payment_trust_dominant_is_trust_first():
    weights = {"payment_trust": 0.6, "promise_keeping": 0.15, "price_fit": 0.15, "reputation": 0.1}
    assert classify_weights(weights) == "Trust-First"


def test_classify_weights_promise_keeping_dominant_is_fast_shipper():
    weights = {"payment_trust": 0.15, "promise_keeping": 0.6, "price_fit": 0.15, "reputation": 0.1}
    assert classify_weights(weights) == "Fast-Shipper"


def test_summarize_weight_profiles_empty():
    assert summarize_weight_profiles([]) == {"sample_size": 0, "profile_breakdown": {}}


def test_summarize_weight_profiles_shares_and_avg_rank():
    events = [
        {"weights": PERSONA_WEIGHTS["Budget Hunter"], "rank": 1, "field_size": 10},
        {"weights": PERSONA_WEIGHTS["Budget Hunter"], "rank": 3, "field_size": 10},
        {"weights": DEFAULT_WEIGHTS, "rank": 5, "field_size": 10},
    ]
    result = summarize_weight_profiles(events)
    assert result["sample_size"] == 3
    assert result["profile_breakdown"]["Budget Hunter"]["share"] == 2 / 3
    assert result["profile_breakdown"]["Budget Hunter"]["avg_rank"] == 2
    assert result["profile_breakdown"]["Balanced (default)"]["share"] == 1 / 3
    assert result["profile_breakdown"]["Balanced (default)"]["avg_rank"] == 5
