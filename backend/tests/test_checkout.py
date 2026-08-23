import json

from app.checkout import checkout_with_fallback, create_test_order, is_razorpay_configured


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


def _candidate(product_id):
    return {
        "product_id": product_id,
        "merchant_id": f"m-{product_id}",
        "merchant_name": f"Merchant {product_id}",
        "product_name": f"Product {product_id}",
        "price_paise": 1000,
    }


def test_checkout_succeeds_on_top_candidate():
    cur = FakeCursor()
    candidates = [_candidate("a"), _candidate("b")]

    def create_order_fn(candidate):
        return {"id": f"order_{candidate['product_id']}"}

    result = checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=create_order_fn)

    assert result["status"] == "success"
    assert result["rank"] == 0
    assert result["order"]["id"] == "order_a"
    layers = [call[1][1] for call in cur.calls]
    assert "checkout_attempt" in layers
    assert "checkout_success" in layers
    assert "checkout_failure" not in layers


def test_checkout_falls_back_when_top_candidate_fails():
    cur = FakeCursor()
    candidates = [_candidate("a"), _candidate("b")]

    def create_order_fn(candidate):
        if candidate["product_id"] == "a":
            raise RuntimeError("simulated Razorpay failure")
        return {"id": "order_b"}

    result = checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=create_order_fn)

    assert result["status"] == "success"
    assert result["rank"] == 1
    assert result["merchant_id"] == "m-b"
    layers = [call[1][1] for call in cur.calls]
    assert layers.count("checkout_attempt") == 2
    assert "checkout_failure" in layers
    assert "checkout_fallback" in layers
    assert "checkout_success" in layers


def test_checkout_exhausted_when_all_candidates_fail():
    cur = FakeCursor()
    candidates = [_candidate("a"), _candidate("b")]

    def create_order_fn(candidate):
        raise RuntimeError("always fails")

    result = checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=create_order_fn)

    assert result["status"] == "exhausted"
    assert result["attempted"] == 2
    layers = [call[1][1] for call in cur.calls]
    assert layers.count("checkout_failure") == 2
    assert "checkout_exhausted" in layers
    # No fallback logged after the last candidate fails — nothing left to fall back to.
    assert layers.count("checkout_fallback") == 1


def test_checkout_force_fail_ranks_skips_real_order_creation():
    cur = FakeCursor()
    candidates = [_candidate("a"), _candidate("b")]
    real_order_attempts = []

    def create_order_fn(candidate):
        real_order_attempts.append(candidate["product_id"])
        return {"id": f"order_{candidate['product_id']}"}

    result = checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=create_order_fn, force_fail_ranks={0})

    assert result["status"] == "success"
    assert result["rank"] == 1
    assert real_order_attempts == ["b"]  # rank 0 never reached the real create_order_fn


def test_checkout_force_fail_ranks_marks_failure_as_simulated():
    cur = FakeCursor()
    candidates = [_candidate("a"), _candidate("b")]
    checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=lambda c: {"id": "ok"}, force_fail_ranks={0})

    failure_payloads = [
        json.loads(call[1][2]) for call in cur.calls if call[1][1] == "checkout_failure"
    ]
    assert len(failure_payloads) == 1
    assert failure_payloads[0]["simulated"] is True


def test_create_test_order_simulates_success_when_razorpay_not_configured(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)

    assert is_razorpay_configured() is False

    order = create_test_order(_candidate("a"), receipt="mandate-1-a")

    assert order["simulated"] is True
    assert order["id"].startswith("sim_")
    assert order["amount"] == 1000


def test_is_razorpay_configured_true_when_both_keys_present(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_x")
    assert is_razorpay_configured() is True


def test_is_razorpay_configured_false_when_only_one_key_present(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    assert is_razorpay_configured() is False


def test_checkout_success_marks_simulated_flag_from_order():
    cur = FakeCursor()
    candidates = [_candidate("a")]
    checkout_with_fallback(cur, "mandate-1", candidates, create_order_fn=lambda c: {"id": "sim_x", "simulated": True})

    success_payloads = [
        json.loads(call[1][2]) for call in cur.calls if call[1][1] == "checkout_success"
    ]
    assert success_payloads[0]["simulated"] is True
