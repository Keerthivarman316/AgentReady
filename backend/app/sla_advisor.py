"""SLA Advisor: recommends what delivery SLA a merchant should declare based
on its own historical COD delivery performance — so it claims what it can
actually hit, rather than over-promising (which the promise-keeping score
punishes) or under-promising (which costs it ranking for no reason)."""

from __future__ import annotations

import math
import statistics
from datetime import timedelta

SLA_GRACE_DAYS = 0.5
DEFAULT_TARGET_PERCENTILE = 0.85
OVER_PROMISING_RATE_MARGIN = 0.10
UNDER_PROMISING_LOW_VIOLATION_RATE = 0.02
UNDER_PROMISING_MARGIN_DAYS = 1.0


def fetch_delivery_days(cur, merchant_id: str) -> list[float]:
    cur.execute(
        """
        SELECT order_created_at, payment_captured_at
        FROM transactions
        WHERE merchant_id = %s AND payment_method = 'cod'
          AND status = 'captured' AND payment_captured_at IS NOT NULL
        """,
        (merchant_id,),
    )
    return [
        (captured_at - created_at) / timedelta(days=1)
        for created_at, captured_at in cur.fetchall()
    ]


def recommend_sla_days(delivery_days: list[float], current_declared_days: int,
                        percentile: float = DEFAULT_TARGET_PERCENTILE) -> dict:
    """Pure: recommends a declared SLA at the given percentile of actual
    historical delivery time, and assesses the current declaration by the
    violation rate it actually produces — not just its distance from the
    median, since a heavy-tailed delivery distribution can sit a declared
    SLA right at the median while still missing it close to a third of the
    time (a real case this caught: median 2.16 days, but 30.8% of orders
    landed past a 2-day declared SLA)."""
    if not delivery_days:
        return {
            "current_declared_sla_days": current_declared_days,
            "recommended_sla_days": current_declared_days,
            "assessment": "insufficient_data",
            "sample_size": 0,
        }

    sorted_days = sorted(delivery_days)
    idx = min(math.ceil(percentile * len(sorted_days)) - 1, len(sorted_days) - 1)
    recommended = max(1, math.ceil(sorted_days[idx]))
    median_actual = statistics.median(sorted_days)

    def violation_rate(declared_days: int) -> float:
        return sum(1 for d in delivery_days if d > declared_days + SLA_GRACE_DAYS) / len(delivery_days)

    current_rate = violation_rate(current_declared_days)
    target_violation_rate = 1 - percentile

    if current_rate > target_violation_rate + OVER_PROMISING_RATE_MARGIN:
        assessment = "over_promising"
    elif (current_rate <= UNDER_PROMISING_LOW_VIOLATION_RATE
          and current_declared_days > recommended + UNDER_PROMISING_MARGIN_DAYS):
        assessment = "under_promising"
    else:
        assessment = "well_calibrated"

    return {
        "current_declared_sla_days": current_declared_days,
        "recommended_sla_days": recommended,
        "median_actual_delivery_days": round(median_actual, 2),
        "current_violation_rate": round(violation_rate(current_declared_days), 3),
        "projected_violation_rate": round(violation_rate(recommended), 3),
        "assessment": assessment,
        "sample_size": len(delivery_days),
    }


def advise_sla(cur, merchant_id: str) -> dict:
    cur.execute("SELECT declared_sla_days FROM merchants WHERE id = %s", (merchant_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"merchant {merchant_id} not found")
    current_declared_days = row[0]

    delivery_days = fetch_delivery_days(cur, merchant_id)
    return recommend_sla_days(delivery_days, current_declared_days)
