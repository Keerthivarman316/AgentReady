"""Confirms the three pipelines that are pitched as LangGraph-backed
(README claim) actually compile to real LangGraph StateGraphs and preserve
the exact behavior their plain-function predecessors had — not just that
the wrapper functions still work."""

from langgraph.graph.state import CompiledStateGraph

from app.checkout import checkout_graph, checkout_with_fallback
from app.buyer_agent import buyer_decision_graph
from app.intent_agent import IntentResolutionError, intent_graph, resolve_intent_to_mandate


def test_intent_graph_is_a_compiled_langgraph():
    assert isinstance(intent_graph, CompiledStateGraph)


def test_buyer_decision_graph_is_a_compiled_langgraph():
    assert isinstance(buyer_decision_graph, CompiledStateGraph)


def test_checkout_graph_is_a_compiled_langgraph():
    assert isinstance(checkout_graph, CompiledStateGraph)


def test_intent_graph_error_state_never_leaks_a_mandate():
    with_error = intent_graph.invoke({
        "consumer_id": "user-1", "goal_text": "no budget or category here",
        "category_id_lookup": lambda name: "id",
    })
    assert with_error["error"] is not None
    assert with_error.get("mandate") is None


def test_resolve_intent_to_mandate_still_raises_through_the_graph():
    with __import__("pytest").raises(IntentResolutionError):
        resolve_intent_to_mandate("user-1", "no budget here", category_id_lookup=lambda name: "id")


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def _candidate(product_id):
    return {
        "product_id": product_id, "merchant_id": f"m-{product_id}", "merchant_name": f"Merchant {product_id}",
        "product_name": f"Product {product_id}", "price_paise": 1000,
    }


def test_checkout_with_empty_candidates_goes_straight_to_exhausted():
    cur = FakeCursor()
    result = checkout_with_fallback(cur, "mandate-1", [], create_order_fn=lambda c: {"id": "unused"})
    assert result == {"status": "exhausted", "attempted": 0}
    layers = [call[1][1] for call in cur.calls]
    assert layers == ["checkout_exhausted"]


def test_checkout_fallback_loop_survives_more_candidates_than_default_recursion_limit():
    # LangGraph's default recursion_limit is 25 supersteps; a real category
    # can have ~50 merchants, so every failed attempt must not hit
    # GraphRecursionError before checkout_with_fallback's override applies.
    candidates = [_candidate(str(i)) for i in range(40)]
    cur = FakeCursor()

    def create_order_fn(candidate):
        if candidate["product_id"] == "39":
            return {"id": "order_last"}
        raise RuntimeError("fails")

    result = checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=create_order_fn)
    assert result["status"] == "success"
    assert result["rank"] == 39
