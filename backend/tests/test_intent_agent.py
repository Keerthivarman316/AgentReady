import pytest

from app.intent_agent import IntentResolutionError, extract_intent, resolve_intent_to_mandate


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
