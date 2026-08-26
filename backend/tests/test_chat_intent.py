from app.buyer_weight_profiles import PERSONA_WEIGHTS
from app.chat_intent import detect_persona, parse_followup


def test_detect_persona_budget_signal():
    assert detect_persona("actually get me the cheapest one") == "Budget Hunter"


def test_detect_persona_trust_signal():
    assert detect_persona("I only want a trusted, reliable seller") == "Trust-First"


def test_detect_persona_speed_signal():
    assert detect_persona("I need this as fast as possible") == "Fast-Shipper"


def test_detect_persona_none_when_no_trigger():
    assert detect_persona("okay sounds good") is None


def test_parse_followup_all_none_for_unrelated_message():
    diff = parse_followup("thanks, that works")
    assert diff["persona"] is None
    assert diff["weights"] is None
    assert diff["budget_cap_paise"] is None
    assert diff["deadline_days"] is None
    assert diff["product_keywords"] is None


def test_parse_followup_budget_change_only():
    diff = parse_followup("actually keep it under 1500 rupees")
    assert diff["budget_cap_paise"] == 150_000
    assert diff["persona"] is None
    assert diff["product_keywords"] is None


def test_parse_followup_persona_and_weights_match():
    diff = parse_followup("I want the cheapest option")
    assert diff["persona"] == "Budget Hunter"
    assert diff["weights"] == PERSONA_WEIGHTS["Budget Hunter"]


def test_parse_followup_product_redirect():
    diff = parse_followup("how about headphones instead")
    assert diff["product_keywords"] == ["headphone"]
    assert diff["category"] == "Electronics"


def test_parse_followup_deadline_change():
    diff = parse_followup("I need it within 2 days")
    assert diff["deadline_days"] == 2


def test_parse_followup_uses_llm_result_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.chat_intent.generate_json",
        lambda prompt, schema, **kw: {
            "persona": "Trust-First", "category": None, "budget_cap_paise": None,
            "deadline_days": None, "product_keywords": None,
        },
    )
    diff = parse_followup("only show me sellers I can actually trust")
    assert diff["persona"] == "Trust-First"
    assert diff["weights"] == PERSONA_WEIGHTS["Trust-First"]


def test_parse_followup_falls_back_to_regex_when_llm_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.chat_intent.generate_json", lambda *a, **kw: None)
    diff = parse_followup("actually keep it under 1500 rupees")
    assert diff["budget_cap_paise"] == 150_000


def test_parse_followup_rejects_unknown_persona_from_llm(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(
        "app.chat_intent.generate_json",
        lambda *a, **kw: {
            "persona": "Not A Real Persona", "category": None, "budget_cap_paise": None,
            "deadline_days": None, "product_keywords": None,
        },
    )
    diff = parse_followup("some message")
    assert diff["persona"] is None
