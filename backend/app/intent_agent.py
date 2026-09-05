"""Intent Agent: resolves a natural-language goal into a structured intent
(category, budget, deadline) and issues a signed AP2-style mandate. Never
touches money — it hands the mandate to the Buyer Agent and stops.

Intent extraction is a rule-based parser today; it is isolated behind
`extract_intent` so a Gemini-backed parser can replace it later without
touching mandate issuance or the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from app.ap2_mandate import MandateDraft, build_mandate
from app.llm_intent import extract_intent_llm
from app.text_extraction import extract_category, extract_deadline_days, extract_price_paise

DEFAULT_DEADLINE_DAYS = 7


@dataclass
class ExtractedIntent:
    category: str | None
    budget_cap_paise: int | None
    deadline_days: int


def extract_intent(goal_text: str, hint: dict | None = None) -> ExtractedIntent:
    """Tries the LLM extractor first when `GEMINI_API_KEY` is configured —
    it catches phrasings the regex extractors structurally can't ("something
    to block outside noise while working" implies Electronics/earbuds with
    no keyword or price pattern present). Falls back to the regex
    extractors per-field: an LLM response that gets the category right but
    misses a genuinely ambiguous budget still keeps the correct category
    rather than being discarded wholesale.

    `hint` lets a caller that already resolved category+budget by other
    means (the buyer chat's per-turn `parse_followup`, which just paid for
    its own Gemini call on nearly the same text) skip this function's LLM
    call entirely instead of re-deriving the same fields a second time."""
    if hint and hint.get("category") is not None and hint.get("budget_cap_paise") is not None:
        return ExtractedIntent(
            category=hint["category"],
            budget_cap_paise=hint["budget_cap_paise"],
            deadline_days=hint.get("deadline_days") or DEFAULT_DEADLINE_DAYS,
        )
    llm_result = extract_intent_llm(goal_text)
    return ExtractedIntent(
        category=(llm_result and llm_result.get("category")) or extract_category(goal_text),
        budget_cap_paise=(llm_result and llm_result.get("budget_cap_paise")) or extract_price_paise(goal_text),
        deadline_days=(llm_result and llm_result.get("deadline_days")) or extract_deadline_days(goal_text) or DEFAULT_DEADLINE_DAYS,
    )


class IntentResolutionError(ValueError):
    pass


class IntentGraphState(TypedDict, total=False):
    consumer_id: str
    goal_text: str
    category_id_lookup: Callable[[str], str | None]
    hint: dict | None
    intent: ExtractedIntent
    category_id: str | None
    error: str | None
    mandate: MandateDraft | None


def _node_extract(state: IntentGraphState) -> dict:
    return {"intent": extract_intent(state["goal_text"], state.get("hint"))}


def _route_after_extract(state: IntentGraphState) -> str:
    intent = state["intent"]
    if intent.category is None:
        return "error_category"
    if intent.budget_cap_paise is None:
        return "error_budget"
    return "resolve_category"


def _node_error_category(state: IntentGraphState) -> dict:
    return {"error": f"could not infer a product category from: {state['goal_text']!r}"}


def _node_error_budget(state: IntentGraphState) -> dict:
    return {"error": f"could not infer a budget from: {state['goal_text']!r}"}


def _node_resolve_category(state: IntentGraphState) -> dict:
    intent = state["intent"]
    category_id = state["category_id_lookup"](intent.category)
    if category_id is None:
        return {"error": f"unknown category: {intent.category!r}"}
    return {"category_id": category_id}


def _route_after_resolve(state: IntentGraphState) -> str:
    return "error" if state.get("error") else "build_mandate"


def _node_build_mandate(state: IntentGraphState) -> dict:
    intent = state["intent"]
    mandate = build_mandate(
        consumer_id=state["consumer_id"],
        category_id=state["category_id"],
        budget_cap_paise=intent.budget_cap_paise,
        deadline_days=intent.deadline_days,
        goal_text=state["goal_text"],
    )
    return {"mandate": mandate}


def _build_intent_graph():
    graph = StateGraph(IntentGraphState)
    graph.add_node("extract", _node_extract)
    graph.add_node("error_category", _node_error_category)
    graph.add_node("error_budget", _node_error_budget)
    graph.add_node("resolve_category", _node_resolve_category)
    graph.add_node("build_mandate", _node_build_mandate)

    graph.set_entry_point("extract")
    graph.add_conditional_edges("extract", _route_after_extract, {
        "error_category": "error_category", "error_budget": "error_budget", "resolve_category": "resolve_category",
    })
    graph.add_edge("error_category", END)
    graph.add_edge("error_budget", END)
    graph.add_conditional_edges("resolve_category", _route_after_resolve, {
        "error": END, "build_mandate": "build_mandate",
    })
    graph.add_edge("build_mandate", END)
    return graph.compile()


intent_graph = _build_intent_graph()


def resolve_intent_to_mandate(consumer_id: str, goal_text: str, category_id_lookup, hint: dict | None = None) -> MandateDraft:
    """`category_id_lookup(category_name) -> str | None` resolves a category
    name to its DB id; kept injectable so this stays testable without a DB.
    `hint` is forwarded to `extract_intent` — see its docstring."""
    result = intent_graph.invoke({
        "consumer_id": consumer_id, "goal_text": goal_text, "category_id_lookup": category_id_lookup, "hint": hint,
    })
    if result.get("error"):
        raise IntentResolutionError(result["error"])
    return result["mandate"]
