from app.growth_advisor import _llm_fix_summary, _templated_fix_summary, generate_fix_list, rank_by_persona, rerank_with_override
from app.trust_engine import DEFAULT_WEIGHTS, compute_composite


def test_generate_fix_list_only_includes_below_median_components():
    benchmark = {
        "merchant_id": "m1",
        "components": {
            "payment_trust": 0.5,   # below median -> fix
            "promise_keeping": 0.9,  # above median -> no fix
            "price_fit": 0.4,       # below median -> fix
            "reputation": 0.6,      # equal -> no fix
        },
        "component_medians": {
            "payment_trust": 0.8,
            "promise_keeping": 0.6,
            "price_fit": 0.7,
            "reputation": 0.6,
        },
    }
    fixes = generate_fix_list(benchmark, DEFAULT_WEIGHTS)
    components_flagged = {f["component"] for f in fixes}
    assert components_flagged == {"payment_trust", "price_fit"}


def test_generate_fix_list_ranks_by_impact_not_just_gap_size():
    # price_fit has the bigger raw gap but a much lower weight than payment_trust,
    # so payment_trust's fix should still rank first by score impact.
    benchmark = {
        "merchant_id": "m1",
        "components": {"payment_trust": 0.70, "promise_keeping": 0.9, "price_fit": 0.1, "reputation": 0.6},
        "component_medians": {"payment_trust": 0.80, "promise_keeping": 0.6, "price_fit": 0.5, "reputation": 0.6},
    }
    fixes = generate_fix_list(benchmark, {"payment_trust": 0.9, "promise_keeping": 0.05, "price_fit": 0.02, "reputation": 0.03})
    assert fixes[0]["component"] == "payment_trust"


def test_generate_fix_list_empty_when_no_gaps():
    benchmark = {
        "merchant_id": "m1",
        "components": {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.9, "reputation": 0.9},
        "component_medians": {"payment_trust": 0.5, "promise_keeping": 0.5, "price_fit": 0.5, "reputation": 0.5},
    }
    assert generate_fix_list(benchmark, DEFAULT_WEIGHTS) == []


def _score(merchant_id, components):
    composite, _ = compute_composite(components, DEFAULT_WEIGHTS)
    return {"merchant_id": merchant_id, "composite_score": composite, "components": components}


def test_rerank_with_override_can_move_merchant_to_first():
    scores = [
        _score("leader", {"payment_trust": 0.6, "promise_keeping": 0.6, "price_fit": 0.6, "reputation": 0.6}),
        _score("laggard", {"payment_trust": 0.1, "promise_keeping": 0.6, "price_fit": 0.6, "reputation": 0.6}),
    ]
    result = rerank_with_override(scores, "laggard", "payment_trust", 0.9, DEFAULT_WEIGHTS)
    assert result["before_rank"] == 2
    assert result["after_rank"] == 1
    assert result["after_score"] > result["before_score"]


def test_rerank_with_override_does_not_mutate_input():
    scores = [
        _score("a", {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.5, "reputation": 0.8}),
        _score("b", {"payment_trust": 0.4, "promise_keeping": 0.4, "price_fit": 0.6, "reputation": 0.9}),
    ]
    rerank_with_override(scores, "b", "payment_trust", 0.95, DEFAULT_WEIGHTS)
    assert scores[0]["components"]["payment_trust"] == 0.9
    assert scores[1]["components"]["payment_trust"] == 0.4


def test_rank_by_persona_flips_rank_for_cheap_low_trust_merchant():
    # "budget" has a low trust score but the best price fit; under a
    # Budget Hunter's weights it should outrank "trusted", but under a
    # Trust-First buyer it should not.
    scores = [
        _score("trusted", {"payment_trust": 0.9, "promise_keeping": 0.9, "price_fit": 0.3, "reputation": 0.8}),
        _score("budget", {"payment_trust": 0.5, "promise_keeping": 0.5, "price_fit": 0.95, "reputation": 0.5}),
    ]
    breakdown = rank_by_persona(scores, "budget")
    assert breakdown["Budget Hunter"]["rank"] == 1
    assert breakdown["Trust-First"]["rank"] == 2
    assert breakdown["Budget Hunter"]["total_in_category"] == 2


def test_rank_by_persona_covers_every_named_persona():
    scores = [_score("only", {"payment_trust": 0.5, "promise_keeping": 0.5, "price_fit": 0.5, "reputation": 0.5})]
    breakdown = rank_by_persona(scores, "only")
    assert set(breakdown) == {"Balanced (default)", "Trust-First", "Fast-Shipper", "Budget Hunter", "Reputation-Led"}
    assert all(v["rank"] == 1 for v in breakdown.values())


def test_templated_fix_summary_when_no_gaps():
    assert "No gaps" in _templated_fix_summary([])


def test_templated_fix_summary_mentions_top_fix():
    fixes = [{"component": "payment_trust", "merchant_value": 0.5, "category_median": 0.8, "gap": 0.3, "impact": 0.1}]
    summary = _templated_fix_summary(fixes)
    assert "Payment trust" in summary or "payment trust" in summary.lower()


def test_llm_fix_summary_returns_none_when_unconfigured():
    fixes = [{"component": "payment_trust", "merchant_value": 0.5, "category_median": 0.8, "gap": 0.3, "impact": 0.1}]
    assert _llm_fix_summary(fixes, {"rank": 3, "total_in_category": 10}) is None


def test_llm_fix_summary_returns_none_when_no_fixes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    assert _llm_fix_summary([], {"rank": 1, "total_in_category": 10}) is None


def test_llm_fix_summary_uses_generated_text_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.growth_advisor.generate_text", lambda prompt, **kw: "Focus on payment trust first.")
    fixes = [{"component": "payment_trust", "merchant_value": 0.5, "category_median": 0.8, "gap": 0.3, "impact": 0.1}]
    assert _llm_fix_summary(fixes, {"rank": 3, "total_in_category": 10}) == "Focus on payment trust first."
