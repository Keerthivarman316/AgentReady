from app.benchmark_agent import summarize_benchmark


def _score(merchant_id, composite, components):
    return {"merchant_id": merchant_id, "composite_score": composite, "components": components}


def test_summarize_benchmark_computes_rank_and_gap():
    scores = [
        _score("a", 0.9, {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.9, "reputation": 0.9}),
        _score("b", 0.5, {"payment_trust": 0.5, "promise_keeping": 0.5, "price_fit": 0.5, "reputation": 0.5}),
        _score("c", 0.3, {"payment_trust": 0.3, "promise_keeping": 0.3, "price_fit": 0.3, "reputation": 0.3}),
    ]
    result = summarize_benchmark(scores, "b")
    assert result["rank"] == 2
    assert result["total_in_category"] == 3
    assert result["category_median_score"] == 0.5
    assert result["gap_to_median"] == 0.0
    assert result["component_medians"]["payment_trust"] == 0.5


def test_summarize_benchmark_merchant_not_in_scores():
    scores = [_score("a", 0.9, {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.9, "reputation": 0.9})]
    result = summarize_benchmark(scores, "missing")
    assert result["rank"] is None
    assert result["composite_score"] is None


def test_summarize_benchmark_never_surfaces_competitor_identities():
    scores = [
        _score("a", 0.9, {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.9, "reputation": 0.9}),
        _score("b", 0.5, {"payment_trust": 0.5, "promise_keeping": 0.5, "price_fit": 0.5, "reputation": 0.5}),
    ]
    result = summarize_benchmark(scores, "b")
    assert "a" not in str(result["rank"])
    assert set(result.keys()).isdisjoint({"competitor_ids", "competitor_names"})
