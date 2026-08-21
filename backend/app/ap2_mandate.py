"""AP2-style mandate: a signed, scoped, expiring object authorizing the Buyer
Agent to act — budget cap, category, deadline — issued by the Intent Agent
and never touched by anything downstream of it.

Not a full implementation of Google's Agent Payments Protocol; it follows the
same shape (signed, inspectable, scoped authorization object) using an HMAC
signature in place of the coalition's cryptographic signing chain.
"""

from __future__ import annotations

import hashlib
import hmac
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
