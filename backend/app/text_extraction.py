"""Shared rule-based text extraction used by both the Intent Agent (parsing a
buyer's natural-language goal) and the Readiness Agent (parsing a merchant's
raw catalog text). Both need the same category-keyword matching and currency
extraction; isolated here so a real LLM-backed parser can replace either
caller independently later.
"""

from __future__ import annotations

import re

CATEGORY_KEYWORDS = {
    "Electronics": [
        "earbud", "headphone", "speaker", "camera", "charger", "tracker",
        "electronics", "gadget", "bluetooth",
    ],
    "Fashion": [
        "shirt", "jeans", "sneaker", "shoe", "wallet", "sweater", "tote",
        "fashion", "clothing", "bag",
    ],
    "Home & Kitchen": [
        "kettle", "cookware", "pillow", "pan", "dinner", "lamp", "kitchen",
        "home", "plate", "cutlery",
    ],
}

_PRICE_PATTERNS = [
    re.compile(r"(?:price|mrp|priced\s+at|cost)\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*([\d,]+)(k)?", re.I),
    re.compile(r"(?:under|below|max(?:imum)?|budget(?:\s+of)?|up\s+to)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)(k)?", re.I),
    re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+)(k)?", re.I),
]


def extract_category(text: str) -> str | None:
    lowered = text.lower()
    best_match = None
    best_hits = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_hits = hits
            best_match = category
    return best_match


def extract_price_paise(text: str) -> int | None:
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            amount = int(match.group(1).replace(",", ""))
            if match.group(2):
                amount *= 1000
            return amount * 100
    return None
