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

import razorpay

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


def checkout_with_fallback(cur, mandate_id: str, ranked_candidates: list[dict], create_order_fn=None,
                            force_fail_ranks: set[int] | None = None) -> dict:
    if create_order_fn is None:
        # Razorpay caps `receipt` at 56 chars; two full UUIDs joined ("mandate-product") is 73,
        # so truncate the mandate id down to keep the receipt under the limit.
        create_order_fn = lambda candidate: create_test_order(candidate, receipt=f"{mandate_id[:8]}-{candidate['product_id']}")
    force_fail_ranks = force_fail_ranks or set()

    for rank, candidate in enumerate(ranked_candidates):
        log_audit(cur, mandate_id, "checkout_attempt", {
            "rank": rank, "merchant_name": candidate["merchant_name"], "product_name": candidate["product_name"],
        })
        try:
            if rank in force_fail_ranks:
                raise SimulatedCheckoutFailure("scripted failure (demo): forced for this rank")
            order = create_order_fn(candidate)
        except Exception as exc:
            log_audit(cur, mandate_id, "checkout_failure", {
                "rank": rank, "merchant_name": candidate["merchant_name"], "error": str(exc),
                "simulated": isinstance(exc, SimulatedCheckoutFailure),
            })
            if rank + 1 < len(ranked_candidates):
                log_audit(cur, mandate_id, "checkout_fallback", {
                    "from_rank": rank, "to_rank": rank + 1,
                    "to_merchant": ranked_candidates[rank + 1]["merchant_name"],
                })
            continue

        log_audit(cur, mandate_id, "checkout_success", {
            "rank": rank, "merchant_name": candidate["merchant_name"], "order_id": order.get("id"),
            "simulated": bool(order.get("simulated")),
            "settlement_note": order.get("settlement_note"),
        })
        return {
            "status": "success", "rank": rank,
            "merchant_id": candidate["merchant_id"], "product_id": candidate["product_id"], "order": order,
        }

    log_audit(cur, mandate_id, "checkout_exhausted", {"attempted": len(ranked_candidates)})
    return {"status": "exhausted", "attempted": len(ranked_candidates)}
