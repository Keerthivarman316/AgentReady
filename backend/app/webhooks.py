"""Razorpay webhook receiver.

Real payment *capture* is blocked by Razorpay's own bot-detection on this
project's test account (Checkout.js sits behind hCaptcha + device
fingerprinting, and the S2S card API 404s for unapproved merchants — see
checkout.py's module docstring). `order.create()` remains the correct
agent-side boundary; that finding is unchanged by this module.

What this closes is the *other* half: actually receiving and using real
Razorpay event data when it does occur, instead of the Trust Engine only
ever reading our own seeded rows. `payment.captured`, `order.paid`,
`refund.processed`, and `payment.dispute.created` all get logged to
`razorpay_events` (every verified delivery, acted on or not); `order.paid`,
`refund.processed`, and `payment.dispute.created` additionally write into
the same `transactions`/`refunds`/`disputes` tables `trust_engine.py`
already reads, tagged `source='razorpay_live'` — no branching needed there,
live events just add to what's already aggregated.

`payment.captured` is logged but not separately materialized into
`transactions`: Razorpay delivers it as its own webhook call, separate from
`order.paid`, but `order.paid`'s payload already carries both the payment
and order entities (including `receipt`, which is what resolves an event
back to the product/merchant our checkout created it for) — handling both
would need a uniqueness constraint on `razorpay_payment_id` to avoid a
double-insert that isn't worth adding for an event this environment can't
even trigger in practice (see the note below).

**Verification constraint, stated plainly:** Razorpay's dashboard can only
deliver webhooks to a publicly reachable URL — this project doesn't set up
a tunnel (e.g. ngrok), so real deliveries from Razorpay's servers were
never attempted against this endpoint. What *is* verified: a payload
shaped exactly like Razorpay's documented samples, HMAC-SHA256-signed
exactly as Razorpay signs real deliveries, is accepted and correctly
updates the tables; a wrong or missing signature is rejected with 400. That
proves the code path is correct — it doesn't prove Razorpay's real
infrastructure can reach this machine.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import razorpay
from fastapi import APIRouter, HTTPException, Request

from app.db import get_connection

router = APIRouter()


def is_webhook_configured() -> bool:
    return bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET"))


def verify_signature(body: str, signature: str) -> bool:
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    client = razorpay.Client(auth=("", ""))
    try:
        return client.utility.verify_webhook_signature(body, signature, secret)
    except razorpay.errors.SignatureVerificationError:
        return False


def _product_id_from_receipt(receipt: str | None) -> str | None:
    """Undoes checkout.py's `f"{mandate_id[:8]}-{product_id}"` receipt
    format. `mandate_id[:8]` is always exactly 8 raw hex characters — a
    UUID string has no hyphen until index 8 — so the product_id is
    unambiguously everything after the 9th character (8 hex chars + the
    separating hyphen), regardless of the hyphens inside product_id's own
    UUID."""
    if not receipt or len(receipt) < 10:
        return None
    return receipt[9:]


def log_event(cur, event_type: str, payload: dict) -> None:
    cur.execute(
        "INSERT INTO razorpay_events (event_type, payload) VALUES (%s, %s)",
        (event_type, json.dumps(payload, default=str)),
    )


def handle_order_paid(cur, payload: dict) -> None:
    order = payload.get("order", {}).get("entity", {})
    payment = payload.get("payment", {}).get("entity", {})
    product_id = _product_id_from_receipt(order.get("receipt"))
    if product_id is None:
        return
    cur.execute("SELECT merchant_id FROM products WHERE id = %s", (product_id,))
    row = cur.fetchone()
    if row is None:
        return
    (merchant_id,) = row
    captured_at = datetime.fromtimestamp(payment["created_at"], tz=timezone.utc) if payment.get("created_at") else datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO transactions
            (merchant_id, product_id, razorpay_payment_id, amount_paise, payment_method,
             status, order_created_at, payment_captured_at, source)
        VALUES (%s, %s, %s, %s, %s, 'captured', %s, %s, 'razorpay_live')
        """,
        (merchant_id, product_id, payment.get("id"), payment.get("amount") or order.get("amount"),
         payment.get("method") or "card", captured_at, captured_at),
    )


def handle_refund_processed(cur, payload: dict) -> None:
    refund = payload.get("refund", {}).get("entity", {})
    payment_id = refund.get("payment_id")
    if not payment_id:
        return
    cur.execute(
        "SELECT id FROM transactions WHERE razorpay_payment_id = %s ORDER BY created_at DESC LIMIT 1",
        (payment_id,),
    )
    row = cur.fetchone()
    if row is None:
        return
    (transaction_id,) = row
    cur.execute(
        """
        INSERT INTO refunds (transaction_id, reason_code, amount_paise, status, source)
        VALUES (%s, %s, %s, 'processed', 'razorpay_live')
        """,
        (transaction_id, refund.get("notes", {}).get("reason") if isinstance(refund.get("notes"), dict) else "razorpay_refund",
         refund.get("amount") or 0),
    )


def handle_dispute_created(cur, payload: dict) -> None:
    dispute = payload.get("dispute", {}).get("entity", {})
    payment_id = dispute.get("payment_id")
    if not payment_id:
        return
    cur.execute(
        "SELECT id FROM transactions WHERE razorpay_payment_id = %s ORDER BY created_at DESC LIMIT 1",
        (payment_id,),
    )
    row = cur.fetchone()
    if row is None:
        return
    (transaction_id,) = row
    cur.execute(
        """
        INSERT INTO disputes (transaction_id, reason_code, status, source)
        VALUES (%s, %s, 'open', 'razorpay_live')
        """,
        (transaction_id, dispute.get("reason_code") or "unknown"),
    )


_ACTIONABLE_HANDLERS = {
    "order.paid": handle_order_paid,
    "refund.processed": handle_refund_processed,
    "payment.dispute.created": handle_dispute_created,
}

# Recognized but intentionally not separately materialized -- see module
# docstring (order.paid's payload already carries what payment.captured
# would give us).
_LOGGED_ONLY_EVENTS = {"payment.captured"}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    raw_body = (await request.body()).decode("utf-8")
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="invalid webhook signature")

    event = json.loads(raw_body)
    event_type = event.get("event", "")

    with get_connection() as conn, conn.cursor() as cur:
        log_event(cur, event_type, event)
        handler = _ACTIONABLE_HANDLERS.get(event_type)
        if handler is not None:
            handler(cur, event.get("payload", {}))
        conn.commit()

    return {"status": "ok", "event": event_type, "acted_on": event_type in _ACTIONABLE_HANDLERS}
