"""Intent Agent: resolves a natural-language goal into a structured intent
(category, budget, deadline) and issues a signed AP2-style mandate. Never
touches money — it hands the mandate to the Buyer Agent and stops.

Intent extraction is a rule-based parser today; it is isolated behind
`extract_intent` so a Gemini-backed parser can replace it later without
touching mandate issuance or the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ap2_mandate import MandateDraft, build_mandate
from app.text_extraction import extract_category, extract_deadline_days, extract_price_paise

DEFAULT_DEADLINE_DAYS = 7


@dataclass
class ExtractedIntent:
    category: str | None
    budget_cap_paise: int | None
    deadline_days: int


def extract_intent(goal_text: str) -> ExtractedIntent:
    return ExtractedIntent(
        category=extract_category(goal_text),
        budget_cap_paise=extract_price_paise(goal_text),
        deadline_days=extract_deadline_days(goal_text) or DEFAULT_DEADLINE_DAYS,
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
