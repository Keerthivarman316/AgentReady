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
