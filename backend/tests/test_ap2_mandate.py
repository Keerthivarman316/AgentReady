from datetime import timedelta

from app.ap2_mandate import build_mandate, is_expired, sign_mandate, verify_mandate


def test_build_mandate_is_self_consistent():
    mandate = build_mandate(
        consumer_id="user-1",
        category_id="cat-electronics",
        budget_cap_paise=200_000,
        deadline_days=5,
        goal_text="earbuds under 2000",
    )
    assert verify_mandate(
        mandate.consumer_id, mandate.category_id, mandate.budget_cap_paise,
        mandate.deadline_days, mandate.issued_at, mandate.expires_at, mandate.mandate_hash,
    )


def test_tampered_budget_fails_verification():
    mandate = build_mandate("user-1", "cat-electronics", 200_000, 5, "earbuds under 2000")
    tampered_budget = 999_999
    assert not verify_mandate(
        mandate.consumer_id, mandate.category_id, tampered_budget,
        mandate.deadline_days, mandate.issued_at, mandate.expires_at, mandate.mandate_hash,
    )


def test_different_inputs_produce_different_signatures():
    now = build_mandate("user-1", "cat-electronics", 200_000, 5, "x").issued_at
    expires = now + timedelta(hours=1)
    sig_a = sign_mandate("user-1", "cat-electronics", 200_000, 5, now, expires)
    sig_b = sign_mandate("user-2", "cat-electronics", 200_000, 5, now, expires)
    assert sig_a != sig_b


def test_is_expired():
    mandate = build_mandate("user-1", "cat-electronics", 200_000, 5, "x", ttl=timedelta(seconds=-1))
    assert is_expired(mandate.expires_at)
