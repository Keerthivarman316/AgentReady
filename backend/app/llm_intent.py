"""LLM-backed intent extraction: attempts what `text_extraction.py`'s regex
extractors structurally can't — a goal with no recognized keyword or price
pattern at all ("something to block outside noise while working, budget of
a couple thousand rupees, need it in a week" has no substring any regex in
this project matches, but a real category/budget/deadline are obviously
implied).

Returns a plain dict (or None), not `ExtractedIntent` — kept decoupled from
`intent_agent.py`'s dataclass so this module can be imported from there
without a circular import; `intent_agent.extract_intent` is the only
caller and does the wrapping.
"""

from __future__ import annotations

from app.llm_client import generate_json, is_llm_configured
from app.text_extraction import CATEGORY_KEYWORDS

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING", "enum": list(CATEGORY_KEYWORDS.keys()), "nullable": True},
        "budget_cap_paise": {"type": "INTEGER", "nullable": True},
        "deadline_days": {"type": "INTEGER", "nullable": True},
    },
    "required": ["category", "budget_cap_paise", "deadline_days"],
}

_PROMPT_TEMPLATE = """You are parsing a shopping goal for an autonomous buyer agent into structured fields.

Goal: {goal_text!r}

Valid categories: {categories}

Extract:
- category: the single best matching category from the valid list, or null if none plausibly applies.
- budget_cap_paise: the buyer's maximum budget in Indian paise (1 rupee = 100 paise). "under 2000" -> 200000. "budget of 2k" -> 200000. null if no budget is stated or implied.
- deadline_days: how many days the buyer is willing to wait, as an integer. "tomorrow"/"today" -> 1. "within a week"/"next week" -> 7. null if no deadline is stated or implied.

Only use information actually present or clearly implied by the goal text. Do not invent a category or budget that isn't supported by the text."""


def extract_intent_llm(goal_text: str) -> dict | None:
    """Returns {"category": str|None, "budget_cap_paise": int|None,
    "deadline_days": int|None}, or None if the LLM is unconfigured or the
    call/parse failed in any way. Never raises."""
    if not is_llm_configured():
        return None
    prompt = _PROMPT_TEMPLATE.format(goal_text=goal_text, categories=", ".join(CATEGORY_KEYWORDS.keys()))
    result = generate_json(prompt, _RESPONSE_SCHEMA)
    if result is None:
        return None
    if result.get("category") is not None and result["category"] not in CATEGORY_KEYWORDS:
        # Structured output should make this impossible via `enum`, but
        # never trust an external response enough to skip the check.
        return None
    return result
