"""Checkout Executor: attempts Razorpay test-mode checkout against the
Buyer Agent's ranked candidates in order. If the top choice fails at
execution time, it falls back to the next-ranked merchant within the same
mandate — no re-prompting the human — and logs every attempt and failure.

`force_fail_ranks` exists solely to make that failure/fallback path
demoable on command: without it, a failure only happens when Razorpay
itself rejects the order, which isn't something a live demo can reliably
trigger on cue.

When RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET aren't configured, checkout runs in
demo mode: it simulates a *successful* order instead of hard-failing every
attempt, so the purchase flow is demoable without a Razorpay account. Every
simulated order is marked `"simulated": true` on the order and in the audit
log — nothing pretends to be a real payment. The moment real keys are set,
this path is never taken; every order goes through the real (test-mode) API.

With real keys, checkout stops at a real Razorpay order in `status: created`
— it deliberately does not attempt to capture a payment. That's not a missing
feature: under AP2 (Google's Agent Payments Protocol), an agent's job ends at
producing a signed Payment Mandate; the actual charge is the payment
network/wallet's job, executed against a credential the agent never sees raw.
Razorpay also has no headless capture path on a standard account — their
server-to-server card API 404s for unapproved merchants, and their hosted
Checkout widget sits behind its own bot-detection stack (hCaptcha + device
fingerprinting), which is exactly the kind of thing an agent shouldn't be
built to defeat. So `order.create()` is the correct boundary for this
project's agent, not a shortcut around one.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable, TypedDict

import razorpay
from langgraph.graph import END, StateGraph

from app.audit_trail import log_audit


class SimulatedCheckoutFailure(Exception):
    """Raised in place of a real checkout attempt for a rank in force_fail_ranks."""


def is_razorpay_configured() -> bool:
    return bool(os.environ.get("RAZORPAY_KEY_ID")) and bool(os.environ.get("RAZORPAY_KEY_SECRET"))


def get_razorpay_client() -> razorpay.Client:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not configured")
    return razorpay.Client(auth=(key_id, key_secret))


def create_test_order(candidate: dict, receipt: str) -> dict:
    if not is_razorpay_configured():
        return {
            "id": f"sim_{uuid.uuid4().hex[:16]}",
            "amount": candidate["price_paise"],
            "currency": "INR",
            "receipt": receipt,
            "status": "created",
            "simulated": True,
        }
    client = get_razorpay_client()
    order = client.order.create({
        "amount": candidate["price_paise"],
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
    })
    return {
        **order,
        "simulated": False,
        "settlement_note": (
            "Real Razorpay test-mode order. Payment Mandate authorized; capture is the "
            "payment network/wallet's responsibility per AP2, not the agent's."
        ),
    }


class CheckoutState(TypedDict, total=False):
    """Runs in-process with no checkpointer, same as buyer_agent's decision
    graph — `cur` and `create_order_fn` are live Python objects, never
    serialized. `rank` advances on every failed attempt, modeling the
    fallback cascade as a real conditional self-loop on `attempt` instead of
    a plain `for` loop."""
    cur: Any
    mandate_id: str
    candidates: list[dict]
    create_order_fn: Callable[[dict], dict]
    force_fail_ranks: set[int]
    rank: int
    result: dict


def _node_attempt(state: CheckoutState) -> dict:
    cur, mandate_id = state["cur"], state["mandate_id"]
    rank, candidates = state["rank"], state["candidates"]
    candidate = candidates[rank]

    log_audit(cur, mandate_id, "checkout_attempt", {
        "rank": rank, "merchant_name": candidate["merchant_name"], "product_name": candidate["product_name"],
    })
    try:
        if rank in state.get("force_fail_ranks", set()):
            raise SimulatedCheckoutFailure("scripted failure (demo): forced for this rank")
        order = state["create_order_fn"](candidate)
    except Exception as exc:
        log_audit(cur, mandate_id, "checkout_failure", {
            "rank": rank, "merchant_name": candidate["merchant_name"], "error": str(exc),
            "simulated": isinstance(exc, SimulatedCheckoutFailure),
        })
        if rank + 1 < len(candidates):
            log_audit(cur, mandate_id, "checkout_fallback", {
                "from_rank": rank, "to_rank": rank + 1, "to_merchant": candidates[rank + 1]["merchant_name"],
            })
        return {"rank": rank + 1}

    log_audit(cur, mandate_id, "checkout_success", {
        "rank": rank, "merchant_name": candidate["merchant_name"], "order_id": order.get("id"),
        "simulated": bool(order.get("simulated")), "settlement_note": order.get("settlement_note"),
    })
    return {"result": {
        "status": "success", "rank": rank,
        "merchant_id": candidate["merchant_id"], "product_id": candidate["product_id"], "order": order,
    }}


def _node_exhausted(state: CheckoutState) -> dict:
    log_audit(state["cur"], state["mandate_id"], "checkout_exhausted", {"attempted": len(state["candidates"])})
    return {"result": {"status": "exhausted", "attempted": len(state["candidates"])}}


def _route_entry(state: CheckoutState) -> str:
    return "attempt" if state["candidates"] else "exhausted"


def _route_after_attempt(state: CheckoutState) -> str:
    if "result" in state:
        return "done"
    return "attempt" if state["rank"] < len(state["candidates"]) else "exhausted"


def _build_checkout_graph():
    graph = StateGraph(CheckoutState)
    graph.add_node("attempt", _node_attempt)
    graph.add_node("exhausted", _node_exhausted)

    graph.set_conditional_entry_point(_route_entry, {"attempt": "attempt", "exhausted": "exhausted"})
    graph.add_conditional_edges("attempt", _route_after_attempt, {
        "attempt": "attempt", "exhausted": "exhausted", "done": END,
    })
    graph.add_edge("exhausted", END)
    return graph.compile()


checkout_graph = _build_checkout_graph()


def checkout_with_fallback(cur, mandate_id: str, ranked_candidates: list[dict], create_order_fn=None,
                            force_fail_ranks: set[int] | None = None) -> dict:
    if create_order_fn is None:
        # Razorpay caps `receipt` at 56 chars; two full UUIDs joined ("mandate-product") is 73,
        # so truncate the mandate id down to keep the receipt under the limit.
        create_order_fn = lambda candidate: create_test_order(candidate, receipt=f"{mandate_id[:8]}-{candidate['product_id']}")

    # Each fallback attempt is one graph superstep; the default recursion
    # limit (25) is too low for a category with more merchants than that.
    result = checkout_graph.invoke(
        {
            "cur": cur, "mandate_id": mandate_id, "candidates": ranked_candidates,
            "create_order_fn": create_order_fn, "force_fail_ranks": force_fail_ranks or set(), "rank": 0,
        },
        config={"recursion_limit": max(50, len(ranked_candidates) + 10)},
    )
    return result["result"]
