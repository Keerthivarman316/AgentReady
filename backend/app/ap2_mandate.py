"""AP2-style mandate: a signed, scoped, expiring object authorizing the Buyer
Agent to act — budget cap, category, deadline — issued by the Intent Agent
and never touched by anything downstream of it.

The functions below this module's original `sign_mandate`/`build_mandate`
pair produce payloads that are literally shaped to match Google's Agent
Payments Protocol JSON Schemas (vendored in `app/ap2_schemas/`, fetched
from github.com/google-agentic-commerce/AP2 — the spec moved to a two-pair
SD-JWT verifiable-credential model: an "open" mandate stating pre-purchase
constraints, and a "closed" mandate for the concrete, final transaction).
What's *not* implemented is the spec's actual signing chain: real AP2
mandates are SD-JWTs signed with ES256 over per-role keys, with selective
disclosure and `cnf` key-binding. This project has no PKI, so every mandate
below reuses the same HMAC secret as the original mandate as its stand-in
signature — a shape-conformant, not signature-conformant, implementation.
That gap is called out in every function below, not hidden.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_SIGNING_SECRET = "dev-only-insecure-signing-secret"


def _signing_secret() -> str:
    return os.environ.get("AP2_SIGNING_SECRET", DEFAULT_SIGNING_SECRET)


def _canonical_payload(consumer_id: str, category_id: str, budget_cap_paise: int,
                        deadline_days: int, issued_at: datetime, expires_at: datetime) -> str:
    return "|".join([
        consumer_id,
        category_id,
        str(budget_cap_paise),
        str(deadline_days),
        issued_at.isoformat(),
        expires_at.isoformat(),
    ])


def sign_mandate(consumer_id: str, category_id: str, budget_cap_paise: int,
                  deadline_days: int, issued_at: datetime, expires_at: datetime) -> str:
    payload = _canonical_payload(consumer_id, category_id, budget_cap_paise, deadline_days, issued_at, expires_at)
    return hmac.new(_signing_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_mandate(consumer_id: str, category_id: str, budget_cap_paise: int, deadline_days: int,
                    issued_at: datetime, expires_at: datetime, mandate_hash: str) -> bool:
    expected = sign_mandate(consumer_id, category_id, budget_cap_paise, deadline_days, issued_at, expires_at)
    return hmac.compare_digest(expected, mandate_hash)


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now >= expires_at


@dataclass
class MandateDraft:
    consumer_id: str
    category_id: str
    budget_cap_paise: int
    deadline_days: int
    goal_text: str
    issued_at: datetime
    expires_at: datetime
    mandate_hash: str


def build_mandate(consumer_id: str, category_id: str, budget_cap_paise: int, deadline_days: int,
                   goal_text: str, ttl: timedelta = timedelta(hours=1)) -> MandateDraft:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + ttl
    mandate_hash = sign_mandate(consumer_id, category_id, budget_cap_paise, deadline_days, issued_at, expires_at)
    return MandateDraft(
        consumer_id=consumer_id,
        category_id=category_id,
        budget_cap_paise=budget_cap_paise,
        deadline_days=deadline_days,
        goal_text=goal_text,
        issued_at=issued_at,
        expires_at=expires_at,
        mandate_hash=mandate_hash,
    )


# ---- AP2 spec-shaped mandates -------------------------------------------
#
# Everything below issues the same information the functions above already
# capture, reshaped to literally match AP2's vendored JSON Schemas. See the
# module docstring for what "conformant" does and doesn't mean here.

_NO_KEY_BINDING_CNF = {
    "note": "HMAC-signed mandate; no JWK key-binding implemented (see app/ap2_mandate.py module docstring).",
}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _canonical_json_bytes(obj) -> bytes:
    return _json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_b64url_digest(obj) -> str:
    return _b64url(hashlib.sha256(_canonical_json_bytes(obj)).digest())


def build_open_checkout_mandate(category_name: str, product_keywords: list[str],
                                 issued_at: datetime, expires_at: datetime) -> dict:
    """AP2 `mandate.checkout.open.1`: pre-purchase constraints on what an
    eventual Checkout Mandate must contain. We don't know the exact SKU yet
    at intent time (that's what the Buyer Agent's ranking resolves), so the
    `checkout.line_items` constraint lists the acceptable product-type
    keywords the goal implied, or the category itself when the goal was too
    vague to imply any (matches how `apply_hard_constraints`'
    `wrong_product_type` check already treats an empty keyword list — no
    keywords means "anything in this category")."""
    acceptable_items = (
        [{"id": kw, "title": kw} for kw in product_keywords]
        if product_keywords
        else [{"id": category_name, "title": category_name}]
    )
    return {
        "vct": "mandate.checkout.open.1",
        "constraints": [
            {
                "type": "checkout.line_items",
                "items": [{"id": "item-1", "acceptable_items": acceptable_items, "quantity": 1}],
            },
        ],
        "cnf": dict(_NO_KEY_BINDING_CNF),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def build_open_payment_mandate(open_checkout_mandate: dict, budget_cap_paise: int, deadline_days: int,
                                issued_at: datetime, expires_at: datetime) -> dict:
    """AP2 `mandate.payment.open.1`. The spec requires the `constraints`
    array to contain a `payment.reference` entry pointing at a digest of the
    associated Open Checkout Mandate — computed here as a canonical-JSON
    SHA-256, our stand-in for the spec's SD-JWT `sd_hash`.

    `payment.budget.max` is documented only as "maximum amount for the
    budget", without the minor-units note `types/amount.json` has for
    payment_amount — treated here as whole rupees (unlike `payment_amount`,
    which is minor units/paise per the vendored schema)."""
    not_after = (issued_at + timedelta(days=deadline_days)).date().isoformat()
    return {
        "vct": "mandate.payment.open.1",
        "constraints": [
            {"type": "payment.reference", "conditional_transaction_id": _sha256_b64url_digest(open_checkout_mandate)},
            {"type": "payment.budget", "max": budget_cap_paise / 100, "currency": "INR"},
            {"type": "payment.execution_date", "not_after": not_after},
        ],
        "cnf": dict(_NO_KEY_BINDING_CNF),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def build_checkout_mandate(mandate_id: str, merchant_id: str, merchant_name: str, product_id: str,
                            product_name: str, price_paise: int,
                            issued_at: datetime | None = None, ttl: timedelta = timedelta(hours=1)) -> dict:
    """AP2 `mandate.checkout.1`, issued once the Buyer Agent has picked a
    winner and the Checkout Executor is about to attempt it. `checkout_jwt`
    stands in for the spec's merchant-signed JWT: a canonical-JSON payload
    plus an HMAC-SHA256 signature (same secret as `sign_mandate`), base64url
    packed together — not a real JWS, but inspectable and tamper-evident the
    same way. `checkout_hash` is what `payment_mandate.transaction_id`
    references, exactly as the spec describes."""
    issued_at = issued_at or datetime.now(timezone.utc)
    expires_at = issued_at + ttl
    payload = {
        "mandate_id": mandate_id, "merchant_id": merchant_id, "merchant_name": merchant_name,
        "product_id": product_id, "product_name": product_name, "price_paise": price_paise,
    }
    signature = hmac.new(_signing_secret().encode(), _canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    checkout_jwt = _b64url(_canonical_json_bytes({"payload": payload, "signature": signature}))
    checkout_hash = _b64url(hashlib.sha256(checkout_jwt.encode("ascii")).digest())
    return {
        "vct": "mandate.checkout.1",
        "checkout_jwt": checkout_jwt,
        "checkout_hash": checkout_hash,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def build_payment_mandate(checkout_mandate: dict, merchant_id: str, merchant_name: str,
                           price_paise: int, order_id: str, simulated: bool) -> dict:
    """AP2 `mandate.payment.1` — the final, concrete payment authorization,
    issued alongside a successful Razorpay order. `transaction_id` is the
    associated Checkout Mandate's `checkout_hash`, per spec."""
    return {
        "vct": "mandate.payment.1",
        "transaction_id": checkout_mandate["checkout_hash"],
        "payee": {"id": merchant_id, "name": merchant_name},
        "payment_amount": {"amount": price_paise, "currency": "INR"},
        "payment_instrument": {
            "id": order_id,
            "type": "razorpay_order",
            "description": "Simulated demo order (Razorpay not configured)" if simulated else "Razorpay test-mode order",
        },
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
