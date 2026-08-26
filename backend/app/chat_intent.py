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
from app.llm_client import generate_json, is_llm_configured
from app.text_extraction import (
    CATEGORY_KEYWORDS,
    PRODUCT_TYPE_KEYWORDS,
    extract_category,
    extract_deadline_days,
    extract_price_paise,
    extract_product_keywords,
)

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


_FOLLOWUP_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "persona": {"type": "STRING", "enum": list(PERSONA_WEIGHTS.keys()), "nullable": True},
        "category": {"type": "STRING", "enum": list(CATEGORY_KEYWORDS.keys()), "nullable": True},
        "budget_cap_paise": {"type": "INTEGER", "nullable": True},
        "deadline_days": {"type": "INTEGER", "nullable": True},
        "product_keywords": {
            "type": "ARRAY", "nullable": True,
            "items": {"type": "STRING", "enum": sorted(set(PRODUCT_TYPE_KEYWORDS.values()))},
        },
    },
    "required": ["persona", "category", "budget_cap_paise", "deadline_days", "product_keywords"],
}

_FOLLOWUP_PROMPT_TEMPLATE = """You are parsing one follow-up message in an ongoing shopping chat with an autonomous buyer agent.

Message: {message!r}

Identify ONLY what this specific message changes about the buyer's request. Every field must be null unless the message actually mentions or clearly implies that dimension — a field being null means "keep whatever was already set", so guessing when nothing was said would incorrectly reset it.

- persona: which named buyer priority the message expresses, from {personas}, or null if it doesn't express one.
- category: a new product category from {categories} if the message is redirecting to a different kind of product, else null.
- budget_cap_paise: a new budget in Indian paise (1 rupee = 100 paise) if one is stated, else null.
- deadline_days: a new deadline in days if one is stated, else null.
- product_keywords: specific product types mentioned, chosen only from {product_keywords}, else null."""


def _parse_followup_llm(message: str) -> dict | None:
    if not is_llm_configured():
        return None
    prompt = _FOLLOWUP_PROMPT_TEMPLATE.format(
        message=message,
        personas=", ".join(PERSONA_WEIGHTS.keys()),
        categories=", ".join(CATEGORY_KEYWORDS.keys()),
        product_keywords=", ".join(sorted(set(PRODUCT_TYPE_KEYWORDS.values()))),
    )
    result = generate_json(prompt, _FOLLOWUP_RESPONSE_SCHEMA)
    if result is None:
        return None
    if result.get("persona") is not None and result["persona"] not in PERSONA_WEIGHTS:
        return None
    if result.get("category") is not None and result["category"] not in CATEGORY_KEYWORDS:
        return None
    return result


def parse_followup(message: str) -> dict:
    """Tries an LLM-backed parse first when configured (catches phrasing the
    keyword-trigger lists in PERSONA_TRIGGERS/PRODUCT_TYPE_KEYWORDS miss
    entirely), falling back per-field to the regex/trigger extractors below
    — same discipline as intent_agent.extract_intent. `None` in any field
    means "this message didn't touch that dimension", from either path."""
    llm_result = _parse_followup_llm(message)
    persona = (llm_result and llm_result.get("persona")) or detect_persona(message)
    return {
        "persona": persona,
        "weights": dict(PERSONA_WEIGHTS[persona]) if persona else None,
        "category": (llm_result and llm_result.get("category")) or extract_category(message),
        "budget_cap_paise": (llm_result and llm_result.get("budget_cap_paise")) or extract_price_paise(message),
        "deadline_days": (llm_result and llm_result.get("deadline_days")) or extract_deadline_days(message),
        "product_keywords": (llm_result and llm_result.get("product_keywords")) or extract_product_keywords(message) or None,
    }
