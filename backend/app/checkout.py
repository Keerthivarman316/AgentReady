"""Checkout Executor: attempts Razorpay test-mode checkout against the
Buyer Agent's ranked candidates in order. If the top choice fails at
execution time, it falls back to the next-ranked merchant within the same
mandate — no re-prompting the human — and logs every attempt and failure.
"""

from __future__ import annotations

import os

import razorpay

from app.audit_trail import log_audit


def get_razorpay_client() -> razorpay.Client:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not configured")
    return razorpay.Client(auth=(key_id, key_secret))


def create_test_order(candidate: dict, receipt: str) -> dict:
    client = get_razorpay_client()
    return client.order.create({
        "amount": candidate["price_paise"],
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
    })


def checkout_with_fallback(cur, mandate_id: str, ranked_candidates: list[dict], create_order_fn=None) -> dict:
    if create_order_fn is None:
        create_order_fn = lambda candidate: create_test_order(candidate, receipt=f"{mandate_id}-{candidate['product_id']}")

    for rank, candidate in enumerate(ranked_candidates):
        log_audit(cur, mandate_id, "checkout_attempt", {
            "rank": rank, "merchant_name": candidate["merchant_name"], "product_name": candidate["product_name"],
        })
        try:
            order = create_order_fn(candidate)
        except Exception as exc:
            log_audit(cur, mandate_id, "checkout_failure", {
                "rank": rank, "merchant_name": candidate["merchant_name"], "error": str(exc),
            })
            if rank + 1 < len(ranked_candidates):
                log_audit(cur, mandate_id, "checkout_fallback", {
                    "from_rank": rank, "to_rank": rank + 1,
                    "to_merchant": ranked_candidates[rank + 1]["merchant_name"],
                })
            continue

        log_audit(cur, mandate_id, "checkout_success", {
            "rank": rank, "merchant_name": candidate["merchant_name"], "order_id": order.get("id"),
        })
        return {
            "status": "success", "rank": rank,
            "merchant_id": candidate["merchant_id"], "product_id": candidate["product_id"], "order": order,
        }

    log_audit(cur, mandate_id, "checkout_exhausted", {"attempted": len(ranked_candidates)})
    return {"status": "exhausted", "attempted": len(ranked_candidates)}
