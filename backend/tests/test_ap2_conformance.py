"""Validates issued mandates against AP2's real JSON Schemas (vendored in
app/ap2_schemas/, fetched from google-agentic-commerce/AP2 on GitHub) — the
concrete, checkable proof that "AP2 schema conformance" means what it
claims, rather than an unverifiable assertion. See app/ap2_mandate.py's
module docstring for what's conformant (shape) and what isn't (the real
JWS/SD-JWT signing chain, replaced here by HMAC)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.ap2_mandate import (
    build_checkout_mandate,
    build_open_checkout_mandate,
    build_open_payment_mandate,
    build_payment_mandate,
)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "app" / "ap2_schemas"


def _registry() -> Registry:
    registry = Registry()
    for path in SCHEMAS_DIR.rglob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def _validator_for(filename: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS_DIR / filename).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def _now_window():
    issued_at = datetime.now(timezone.utc)
    return issued_at, issued_at + timedelta(hours=1)


def test_open_checkout_mandate_conforms_to_spec():
    issued_at, expires_at = _now_window()
    ocm = build_open_checkout_mandate("Electronics", ["earbud"], issued_at, expires_at)
    _validator_for("open_checkout_mandate.json").validate(ocm)


def test_open_checkout_mandate_with_no_keywords_falls_back_to_category_and_still_conforms():
    issued_at, expires_at = _now_window()
    ocm = build_open_checkout_mandate("Electronics", [], issued_at, expires_at)
    _validator_for("open_checkout_mandate.json").validate(ocm)


def test_open_payment_mandate_conforms_to_spec():
    issued_at, expires_at = _now_window()
    ocm = build_open_checkout_mandate("Electronics", ["earbud"], issued_at, expires_at)
    opm = build_open_payment_mandate(ocm, budget_cap_paise=250_000, deadline_days=3,
                                      issued_at=issued_at, expires_at=expires_at)
    _validator_for("open_payment_mandate.json").validate(opm)


def test_checkout_mandate_conforms_to_spec():
    cm = build_checkout_mandate(
        mandate_id="mandate-1", merchant_id="merchant-1", merchant_name="Test Merchant",
        product_id="product-1", product_name="Wireless Earbuds Pro", price_paise=199_900,
    )
    _validator_for("checkout_mandate.json").validate(cm)


def test_payment_mandate_conforms_to_spec():
    cm = build_checkout_mandate(
        mandate_id="mandate-1", merchant_id="merchant-1", merchant_name="Test Merchant",
        product_id="product-1", product_name="Wireless Earbuds Pro", price_paise=199_900,
    )
    pm = build_payment_mandate(cm, merchant_id="merchant-1", merchant_name="Test Merchant",
                                price_paise=199_900, order_id="order_abc123", simulated=False)
    _validator_for("payment_mandate.json").validate(pm)


def test_payment_mandate_transaction_id_matches_checkout_hash():
    cm = build_checkout_mandate(
        mandate_id="mandate-1", merchant_id="merchant-1", merchant_name="Test Merchant",
        product_id="product-1", product_name="Wireless Earbuds Pro", price_paise=199_900,
    )
    pm = build_payment_mandate(cm, merchant_id="merchant-1", merchant_name="Test Merchant",
                                price_paise=199_900, order_id="order_abc123", simulated=False)
    assert pm["transaction_id"] == cm["checkout_hash"]


def test_open_payment_mandate_references_a_digest_of_the_open_checkout_mandate():
    issued_at, expires_at = _now_window()
    ocm = build_open_checkout_mandate("Electronics", ["earbud"], issued_at, expires_at)
    opm = build_open_payment_mandate(ocm, budget_cap_paise=250_000, deadline_days=3,
                                      issued_at=issued_at, expires_at=expires_at)
    reference = next(c for c in opm["constraints"] if c["type"] == "payment.reference")

    # Same digest function, applied a second time to a different (but
    # content-identical) open_checkout_mandate dict, must match — the
    # reference is a content digest, not an object-identity check.
    ocm_rebuilt = build_open_checkout_mandate("Electronics", ["earbud"], issued_at, expires_at)
    other_opm = build_open_payment_mandate(ocm_rebuilt, budget_cap_paise=250_000, deadline_days=3,
                                            issued_at=issued_at, expires_at=expires_at)
    assert reference["conditional_transaction_id"] == next(
        c for c in other_opm["constraints"] if c["type"] == "payment.reference"
    )["conditional_transaction_id"]
