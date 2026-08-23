"""Shared rule-based text extraction used by both the Intent Agent (parsing a
buyer's natural-language goal) and the Readiness Agent (parsing a merchant's
raw catalog text). Both need the same category-keyword matching and currency
extraction; isolated here so a real LLM-backed parser can replace either
caller independently later.
"""

from __future__ import annotations

import re

# Used only to decide which category a goal belongs to (broad recall) — includes
# generic category synonyms alongside product-type words. Keep in sync with the
# categories in db/schema.sql / scripts/seed_synthetic_data.py.
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
    "Beauty & Personal Care": [
        "serum", "trimmer", "hair mask", "cleansing brush", "sunscreen",
        "toothbrush", "beauty", "skincare", "personal care", "skin",
    ],
    "Sports & Outdoors": [
        "yoga mat", "dumbbell", "backpack", "water bottle", "resistance band",
        "tent", "camping", "trekking", "gym", "sports", "outdoor",
    ],
}

# Used to narrow candidates down to the specific product type asked for, once a
# category has already been inferred — e.g. "earbuds" should never surface a
# charger just because both are Electronics. Key: substring to look for in the
# goal text. Value: substring to require in a candidate product's name. Keep in
# sync with PRODUCT_POOL in scripts/seed_synthetic_data.py.
PRODUCT_TYPE_KEYWORDS = {
    # Electronics
    "earbud": "earbud",
    "headphone": "headphone",
    "speaker": "speaker",
    "camera": "camera",
    "charger": "charger",
    "fitness tracker": "fitness tracker",
    "tracker": "tracker",
    # Fashion
    "shirt": "shirt",
    "jeans": "jeans",
    "sneaker": "sneaker",
    "wallet": "wallet",
    "sweater": "sweater",
    "tote": "tote",
    # Home & Kitchen
    "kettle": "kettle",
    "cookware": "cookware",
    "pillow": "pillow",
    "frying pan": "frying pan",
    "dinner set": "dinner set",
    "lamp": "lamp",
    # Beauty & Personal Care
    "serum": "serum",
    "trimmer": "trimmer",
    "hair mask": "hair mask",
    "cleansing brush": "cleansing brush",
    "sunscreen": "sunscreen",
    "toothbrush": "toothbrush",
    # Sports & Outdoors
    "yoga mat": "yoga mat",
    "dumbbell": "dumbbell",
    "backpack": "backpack",
    "water bottle": "water bottle",
    "resistance band": "resistance band",
    "tent": "tent",
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


def extract_product_keywords(text: str) -> list[str]:
    """Returns the distinct product-name substrings implied by the goal text.
    Triggers are checked longest-first so a multi-word match (e.g. "fitness
    tracker") is kept and the shorter trigger it contains ("tracker") is
    dropped as redundant rather than added as a separate, looser match."""
    lowered = text.lower()
    matched: list[str] = []
    for trigger, product_substring in sorted(PRODUCT_TYPE_KEYWORDS.items(), key=lambda kv: -len(kv[0])):
        if trigger not in lowered:
            continue
        if any(product_substring in existing or existing in product_substring for existing in matched):
            continue
        matched.append(product_substring)
    return matched


def extract_price_paise(text: str) -> int | None:
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            amount = int(match.group(1).replace(",", ""))
            if match.group(2):
                amount *= 1000
            return amount * 100
    return None
