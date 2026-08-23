"""Lost-Sale Signal: turns a merchant's real hard-constraint rejections —
already logged to the audit trail by every actual Buyer Agent run — into
demand intelligence the merchant can act on. Not a synthetic benchmark: it
only reflects mandates real buyer agents actually evaluated this merchant
against, so it starts empty on a fresh database and grows with real usage.
"""

from __future__ import annotations

from collections import Counter


def fetch_rejection_reasons(cur, merchant_id: str) -> list[list[str]]:
    """One entry per time this merchant was rejected in a hard_constraints
    audit layer, each entry the rejected_reasons list logged for that
    rejection (a rejection can carry more than one reason)."""
    cur.execute(
        """
        SELECT r.value -> 'rejected_reasons'
        FROM audit_trail a, jsonb_array_elements(a.payload -> 'rejected') AS r
        WHERE a.layer = 'hard_constraints' AND r.value ->> 'merchant_id' = %s
        """,
        (merchant_id,),
    )
    return [row[0] for row in cur.fetchall()]


def summarize_lost_sale_signal(rejection_reason_lists: list[list[str]]) -> dict:
    """Pure: reason lists in, breakdown out. Fractions are of rejections, not
    of reasons — a rejection with two reasons contributes to both, so
    fractions don't have to sum to 1."""
    sample_size = len(rejection_reason_lists)
    if sample_size == 0:
        return {"sample_size": 0, "reason_breakdown": {}}

    counts = Counter()
    for reasons in rejection_reason_lists:
        for reason in reasons:
            counts[reason] += 1

    reason_breakdown = {reason: count / sample_size for reason, count in counts.items()}
    return {"sample_size": sample_size, "reason_breakdown": reason_breakdown}


def get_lost_sale_signal(cur, merchant_id: str) -> dict:
    reasons = fetch_rejection_reasons(cur, merchant_id)
    return summarize_lost_sale_signal(reasons)
