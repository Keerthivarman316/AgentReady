from app.sla_advisor import recommend_sla_days


def test_recommend_sla_insufficient_data():
    result = recommend_sla_days([], current_declared_days=3)
    assert result["assessment"] == "insufficient_data"
    assert result["recommended_sla_days"] == 3


def test_recommend_sla_flags_over_promising():
    # Declares 2 days but historically delivers around 5-6 days.
    delivery_days = [5.0, 5.2, 5.5, 5.8, 6.0, 6.2, 5.1, 5.4, 5.9, 6.1]
    result = recommend_sla_days(delivery_days, current_declared_days=2)
    assert result["assessment"] == "over_promising"
    assert result["recommended_sla_days"] >= 6


def test_recommend_sla_flags_under_promising():
    # Declares 10 days but historically delivers reliably in ~2 days.
    delivery_days = [1.8, 2.0, 2.1, 1.9, 2.2, 2.0, 1.9, 2.1, 2.0, 1.8]
    result = recommend_sla_days(delivery_days, current_declared_days=10)
    assert result["assessment"] == "under_promising"
    assert result["recommended_sla_days"] <= 3


def test_recommend_sla_well_calibrated():
    delivery_days = [2.8, 3.0, 3.1, 2.9, 3.2, 3.0, 2.9, 3.1, 3.0, 3.3]
    result = recommend_sla_days(delivery_days, current_declared_days=3)
    assert result["assessment"] == "well_calibrated"


def test_recommend_sla_projected_violation_rate_lower_at_recommended_when_over_promising():
    delivery_days = [4.0, 4.5, 5.0, 4.2, 4.8, 5.2, 4.1, 4.6, 4.9, 5.1]
    result = recommend_sla_days(delivery_days, current_declared_days=2)
    assert result["projected_violation_rate"] <= result["current_violation_rate"]


def test_recommend_sla_flags_over_promising_even_when_declared_sits_at_median():
    # Regression: a heavy-tailed distribution (most orders on time, a chunk
    # badly late) can put the declared SLA right at the median while still
    # missing it ~30% of the time — the median-distance check alone missed
    # this; the violation-rate check catches it.
    on_time = [2.0, 2.1, 1.9, 2.0, 2.2, 1.8, 2.1]
    late = [5.0, 6.0, 5.5]
    delivery_days = on_time + late
    result = recommend_sla_days(delivery_days, current_declared_days=2)
    assert result["current_violation_rate"] > 0.25
    assert result["assessment"] == "over_promising"
