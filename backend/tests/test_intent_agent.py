import pytest

from app.intent_agent import IntentResolutionError, extract_intent, resolve_intent_to_mandate

# conftest.py clears GEMINI_API_KEY by default so these existing tests keep
# exercising the pure-regex path deterministically; the LLM-path tests below
# opt back in explicitly and mock the actual network call.


def test_extract_intent_budget_and_category_and_deadline():
    intent = extract_intent("I need wireless earbuds under ₹2000 within 3 days")
    assert intent.category == "Electronics"
    assert intent.budget_cap_paise == 200_000
    assert intent.deadline_days == 3


def test_extract_intent_k_shorthand_budget():
    intent = extract_intent("looking for a cookware set, budget of 2k")
    assert intent.category == "Home & Kitchen"
    assert intent.budget_cap_paise == 200_000


def test_extract_intent_tomorrow_deadline():
    intent = extract_intent("need running sneakers by tomorrow, max rs 1500")
    assert intent.category == "Fashion"
    assert intent.deadline_days == 1
    assert intent.budget_cap_paise == 150_000


def test_extract_intent_defaults_deadline_when_unspecified():
    intent = extract_intent("need a bluetooth speaker under 3000")
    assert intent.deadline_days == 7


def test_extract_intent_beauty_category():
    intent = extract_intent("looking for a vitamin c face serum under 500")
    assert intent.category == "Beauty & Personal Care"


def test_extract_intent_sports_category():
    intent = extract_intent("need a yoga mat under 1000 within 5 days")
    assert intent.category == "Sports & Outdoors"


def test_resolve_intent_to_mandate_success():
    mandate = resolve_intent_to_mandate(
        consumer_id="user-1",
        goal_text="earbuds under 2000 within 3 days",
        category_id_lookup=lambda name: "cat-electronics-id" if name == "Electronics" else None,
    )
    assert mandate.category_id == "cat-electronics-id"
    assert mandate.budget_cap_paise == 200_000
    assert mandate.deadline_days == 3


def test_resolve_intent_to_mandate_raises_on_missing_budget():
    with pytest.raises(IntentResolutionError):
        resolve_intent_to_mandate("user-1", "earbuds please", category_id_lookup=lambda name: "id")


def test_resolve_intent_to_mandate_raises_on_unknown_category():
    with pytest.raises(IntentResolutionError):
        resolve_intent_to_mandate("user-1", "earbuds under 2000", category_id_lookup=lambda name: None)


def test_extract_intent_uses_llm_result_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.intent_agent.extract_intent_llm",
        lambda goal_text: {"category": "Electronics", "budget_cap_paise": 200_000, "deadline_days": 7},
    )
    intent = extract_intent("something to block outside noise while working, budget of a couple thousand")
    assert intent.category == "Electronics"
    assert intent.budget_cap_paise == 200_000
    assert intent.deadline_days == 7


def test_extract_intent_falls_back_to_regex_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.intent_agent.extract_intent_llm", lambda goal_text: None)
    intent = extract_intent("earbuds under 2000 within 3 days")
    assert intent.category == "Electronics"
    assert intent.budget_cap_paise == 200_000
    assert intent.deadline_days == 3


def test_extract_intent_falls_back_per_field_on_partial_llm_result(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.intent_agent.extract_intent_llm",
        lambda goal_text: {"category": None, "budget_cap_paise": None, "deadline_days": None},
    )
    intent = extract_intent("earbuds under 2000 within 3 days")
    assert intent.category == "Electronics"
    assert intent.budget_cap_paise == 200_000
    assert intent.deadline_days == 3


def test_extract_intent_never_hits_the_network_when_unconfigured(monkeypatch):
    # GEMINI_API_KEY is already absent by default (conftest.py); confirms
    # is_llm_configured()'s check inside extract_intent_llm actually short-
    # circuits before generate_json (the network-touching call) runs.
    called = []
    monkeypatch.setattr("app.llm_intent.generate_json", lambda *a, **kw: called.append(a) or {})
    extract_intent("earbuds under 2000 within 3 days")
    assert called == []
