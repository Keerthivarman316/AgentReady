"""Chat Intent: turns one follow-up message in a multi-turn buyer chat into a
structured diff against the conversation's current state — reusing the same
rule-based extractors the Intent Agent already uses for the opening message
(extract_category, extract_price_paise, extract_deadline_days), so "actually
keep it under 1500" parses the budget exactly like an opening goal would.

Every field in the diff is None when the message didn't mention that
dimension, so the caller knows to keep the conversation's existing value
rather than reset it — the one thing that makes this safe to call on every
turn instead of just the first.

The weight side reuses buyer_weight_profiles.PERSONA_WEIGHTS: a buyer saying
"actually get me the cheapest one" and a merchant seeing "62% of buyers who
evaluated you were Budget Hunters" are the same named priority profile, not
two different concepts — the chat is just how a human triggers what any
buyer agent's weights could already do.
"""

from __future__ import annotations

from app.buyer_weight_profiles import PERSONA_WEIGHTS
from app.text_extraction import extract_category, extract_deadline_days, extract_price_paise, extract_product_keywords

PERSONA_TRIGGERS = {
    "Budget Hunter": ["cheap", "cheaper", "cheapest", "budget", "less expensive", "lower price", "save money", "affordable"],
    "Trust-First": ["trust", "trusted", "reliable", "safe", "safest", "verified", "genuine", "legit"],
    "Fast-Shipper": ["fast", "faster", "fastest", "quick", "quicker", "quickest", "asap", "soonest", "sooner", "hurry"],
    "Reputation-Led": ["rated", "rating", "reviews", "popular", "well-reviewed", "well reviewed", "highly reviewed"],
    "Balanced (default)": ["balanced", "no preference", "default weights", "doesn't matter", "either is fine"],
}


def detect_persona(message: str) -> str | None:
    """Pure: first matching persona wins — dict order above is the tie-break,
    most specific/actionable signals (price, trust, speed) before the softer
    reputation and reset triggers."""
    lowered = message.lower()
    for persona, triggers in PERSONA_TRIGGERS.items():
        if any(trigger in lowered for trigger in triggers):
            return persona
    return None


def parse_followup(message: str) -> dict:
    """Pure: a follow-up chat message in, a structured diff out."""
    persona = detect_persona(message)
    return {
        "persona": persona,
        "weights": dict(PERSONA_WEIGHTS[persona]) if persona else None,
        "category": extract_category(message),
        "budget_cap_paise": extract_price_paise(message),
        "deadline_days": extract_deadline_days(message),
        "product_keywords": extract_product_keywords(message) or None,
    }
