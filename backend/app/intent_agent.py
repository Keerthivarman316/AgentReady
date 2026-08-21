"""Intent Agent: resolves a natural-language goal into a structured intent
(category, budget, deadline) and issues a signed AP2-style mandate. Never
touches money — it hands the mandate to the Buyer Agent and stops.

Intent extraction is a rule-based parser today; it is isolated behind
`extract_intent` so a Gemini-backed parser can replace it later without
touching mandate issuance or the API layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ap2_mandate import MandateDraft, build_mandate

CATEGORY_KEYWORDS = {
    "Electronics": [
        "earbud", "headphone", "speaker", "camera", "charger", "tracker",
        "electronics", "gadget", "bluetooth",
    ],
    "Fashion": [
        "shirt", "jeans", "sneaker", "shoe", "wallet", "sweater", "tote",
        "fashion", "clothing", "bag",
    ],
    "Home & Kitchen": [
        "kettle", "cookware", "pillow", "pan", "dinner", "lamp", "kitchen",
        "home", "plate", "cutlery",
    ],
}

DEFAULT_DEADLINE_DAYS = 7

_BUDGET_PATTERNS = [
    re.compile(r"(?:under|below|max(?:imum)?|budget(?:\s+of)?|up\s+to)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)(k)?", re.I),
    re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+)(k)?", re.I),
]

_DEADLINE_PATTERNS = [
    (re.compile(r"\btomorrow\b", re.I), 1),
    (re.compile(r"\btoday\b", re.I), 1),
    (re.compile(r"\bnext\s+week\b", re.I), 7),
    (re.compile(r"(?:within|in|by)\s+(\d+)\s*day", re.I), None),
]


@dataclass
class ExtractedIntent:
    category: str | None
    budget_cap_paise: int | None
    deadline_days: int


def _extract_category(text: str) -> str | None:
    lowered = text.lower()
    best_match = None
    best_hits = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_hits = hits
            best_match = category
    return best_match


def _extract_budget_paise(text: str) -> int | None:
    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(text)
        if match:
            amount = int(match.group(1).replace(",", ""))
            if match.group(2):
                amount *= 1000
            return amount * 100
    return None


def _extract_deadline_days(text: str) -> int:
    for pattern, fixed_days in _DEADLINE_PATTERNS:
        match = pattern.search(text)
        if match:
            if fixed_days is not None:
                return fixed_days
            return int(match.group(1))
    return DEFAULT_DEADLINE_DAYS


def extract_intent(goal_text: str) -> ExtractedIntent:
    return ExtractedIntent(
        category=_extract_category(goal_text),
        budget_cap_paise=_extract_budget_paise(goal_text),
        deadline_days=_extract_deadline_days(goal_text),
    )


class IntentResolutionError(ValueError):
    pass


def resolve_intent_to_mandate(consumer_id: str, goal_text: str, category_id_lookup) -> MandateDraft:
    """`category_id_lookup(category_name) -> str | None` resolves a category
    name to its DB id; kept injectable so this stays testable without a DB."""
    intent = extract_intent(goal_text)

    if intent.category is None:
        raise IntentResolutionError(f"could not infer a product category from: {goal_text!r}")
    if intent.budget_cap_paise is None:
        raise IntentResolutionError(f"could not infer a budget from: {goal_text!r}")

    category_id = category_id_lookup(intent.category)
    if category_id is None:
        raise IntentResolutionError(f"unknown category: {intent.category!r}")

    return build_mandate(
        consumer_id=consumer_id,
        category_id=category_id,
        budget_cap_paise=intent.budget_cap_paise,
        deadline_days=intent.deadline_days,
        goal_text=goal_text,
    )
