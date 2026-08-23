from app.lost_sale_signal import summarize_lost_sale_signal


def test_empty_history_returns_zero_sample():
    result = summarize_lost_sale_signal([])
    assert result == {"sample_size": 0, "reason_breakdown": {}}


def test_single_reason_breakdown():
    result = summarize_lost_sale_signal([["over_budget"], ["over_budget"], ["misses_deadline"]])
    assert result["sample_size"] == 3
    assert result["reason_breakdown"]["over_budget"] == 2 / 3
    assert result["reason_breakdown"]["misses_deadline"] == 1 / 3


def test_multi_reason_rejection_counts_toward_each_reason():
    # A rejection with two reasons contributes to both — fractions need not
    # sum to 1.
    result = summarize_lost_sale_signal([["over_budget", "misses_deadline"], ["over_budget"]])
    assert result["sample_size"] == 2
    assert result["reason_breakdown"]["over_budget"] == 1.0
    assert result["reason_breakdown"]["misses_deadline"] == 0.5


def test_wrong_product_type_reason_tracked_like_any_other():
    result = summarize_lost_sale_signal([["wrong_product_type"], ["over_budget"]])
    assert result["reason_breakdown"]["wrong_product_type"] == 0.5
