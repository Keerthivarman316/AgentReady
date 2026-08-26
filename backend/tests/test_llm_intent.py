from app.llm_intent import extract_intent_llm


def test_returns_none_when_unconfigured():
    # GEMINI_API_KEY absent by default via conftest.py's autouse fixture.
    assert extract_intent_llm("earbuds under 2000") is None


def test_returns_parsed_result_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.llm_intent.generate_json",
        lambda prompt, schema, **kw: {"category": "Electronics", "budget_cap_paise": 200_000, "deadline_days": 7},
    )
    result = extract_intent_llm("something to block outside noise while working")
    assert result == {"category": "Electronics", "budget_cap_paise": 200_000, "deadline_days": 7}


def test_returns_none_when_the_call_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.llm_intent.generate_json", lambda *a, **kw: None)
    assert extract_intent_llm("earbuds under 2000") is None


def test_rejects_a_category_outside_the_known_set_even_if_returned(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.llm_intent.generate_json",
        lambda *a, **kw: {"category": "Groceries", "budget_cap_paise": 100_000, "deadline_days": 2},
    )
    assert extract_intent_llm("something under 1000") is None
