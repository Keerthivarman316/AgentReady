import hashlib
import hmac
import json

from app.webhooks import (
    _product_id_from_receipt,
    handle_dispute_created,
    handle_order_paid,
    handle_refund_processed,
    is_webhook_configured,
    log_event,
    verify_signature,
)


class FakeCursor:
    def __init__(self, fetchone_results=None):
        self.calls = []
        self._fetchone_results = list(fetchone_results or [])

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._fetchone_results.pop(0) if self._fetchone_results else None


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def test_is_webhook_configured_false_without_secret(monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    assert is_webhook_configured() is False


def test_is_webhook_configured_true_with_secret(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    assert is_webhook_configured() is True


def test_verify_signature_accepts_correctly_signed_body(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({"event": "order.paid"})
    assert verify_signature(body, _sign("whsec_test", body)) is True


def test_verify_signature_rejects_wrong_signature(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({"event": "order.paid"})
    assert verify_signature(body, "not-the-real-signature") is False


def test_verify_signature_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    body = json.dumps({"event": "order.paid"})
    assert verify_signature(body, _sign("whatever", body)) is False


def test_verify_signature_rejects_body_signed_with_a_different_secret(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec_test")
    body = json.dumps({"event": "order.paid"})
    assert verify_signature(body, _sign("a-different-secret", body)) is False


def test_product_id_from_receipt_round_trips_checkouts_format():
    # Matches checkout.py's f"{mandate_id[:8]}-{product_id}" exactly.
    mandate_id = "a3f9c1d2-1111-2222-3333-444455556666"
    product_id = "b7e8f001-aaaa-bbbb-cccc-ddddeeeeffff"
    receipt = f"{mandate_id[:8]}-{product_id}"
    assert _product_id_from_receipt(receipt) == product_id


def test_product_id_from_receipt_none_for_short_or_missing_receipt():
    assert _product_id_from_receipt(None) is None
    assert _product_id_from_receipt("") is None
    assert _product_id_from_receipt("short") is None


def test_log_event_inserts_into_razorpay_events():
    cur = FakeCursor()
    log_event(cur, "order.paid", {"event": "order.paid"})
    assert cur.calls[0][0].strip().startswith("INSERT INTO razorpay_events")


def test_handle_order_paid_inserts_transaction_when_product_found():
    product_id = "b7e8f001-aaaa-bbbb-cccc-ddddeeeeffff"
    mandate_id = "a3f9c1d2-1111-2222-3333-444455556666"
    receipt = f"{mandate_id[:8]}-{product_id}"
    cur = FakeCursor(fetchone_results=[("merchant-1",)])
    payload = {
        "order": {"entity": {"id": "order_abc", "receipt": receipt, "amount": 199900, "status": "paid"}},
        "payment": {"entity": {"id": "pay_abc", "amount": 199900, "method": "upi", "created_at": 1700000000}},
    }
    handle_order_paid(cur, payload)
    insert_call = next(c for c in cur.calls if c[0].strip().startswith("INSERT INTO transactions"))
    assert insert_call[1][0] == "merchant-1"
    assert insert_call[1][1] == product_id
    assert insert_call[1][2] == "pay_abc"
    assert insert_call[1][3] == 199900
    assert "razorpay_live" in insert_call[0]


def test_handle_order_paid_noop_when_receipt_does_not_resolve_to_a_known_product():
    cur = FakeCursor(fetchone_results=[None])
    payload = {
        "order": {"entity": {"id": "order_abc", "receipt": "aaaaaaaa-00000000-0000-0000-0000-000000000000", "amount": 100}},
        "payment": {"entity": {"id": "pay_abc", "amount": 100}},
    }
    handle_order_paid(cur, payload)
    assert not any(c[0].strip().startswith("INSERT INTO transactions") for c in cur.calls)


def test_handle_order_paid_noop_when_receipt_missing():
    cur = FakeCursor()
    handle_order_paid(cur, {"order": {"entity": {}}, "payment": {"entity": {}}})
    assert cur.calls == []


def test_handle_refund_processed_inserts_refund_when_transaction_found():
    cur = FakeCursor(fetchone_results=[("txn-1",)])
    payload = {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_abc", "amount": 50000, "status": "processed"}}}
    handle_refund_processed(cur, payload)
    insert_call = next(c for c in cur.calls if c[0].strip().startswith("INSERT INTO refunds"))
    assert insert_call[1][0] == "txn-1"
    assert insert_call[1][2] == 50000


def test_handle_refund_processed_noop_when_no_matching_transaction():
    cur = FakeCursor(fetchone_results=[None])
    payload = {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_unknown", "amount": 50000}}}
    handle_refund_processed(cur, payload)
    assert not any(c[0].strip().startswith("INSERT INTO refunds") for c in cur.calls)


def test_handle_dispute_created_inserts_dispute_when_transaction_found():
    cur = FakeCursor(fetchone_results=[("txn-1",)])
    payload = {"dispute": {"entity": {"id": "disp_1", "payment_id": "pay_abc", "reason_code": "processed_invalid_expired_card"}}}
    handle_dispute_created(cur, payload)
    insert_call = next(c for c in cur.calls if c[0].strip().startswith("INSERT INTO disputes"))
    assert insert_call[1][0] == "txn-1"
    assert insert_call[1][1] == "processed_invalid_expired_card"


def test_handle_dispute_created_noop_when_no_matching_transaction():
    cur = FakeCursor(fetchone_results=[None])
    payload = {"dispute": {"entity": {"id": "disp_1", "payment_id": "pay_unknown"}}}
    handle_dispute_created(cur, payload)
    assert not any(c[0].strip().startswith("INSERT INTO disputes") for c in cur.calls)
