"""Readiness Agent: converts a merchant's raw, marketing-oriented catalog
text into the structured fields the Buyer Agent actually evaluates (price,
category), and scores how complete that conversion turned out to be.

Without this step a merchant is invisible to agent buyers regardless of how
good their real trust metrics are — it's the entry point, not the
differentiator, so it stays a thin rule-based pass today (same extraction
helpers as the Intent Agent) rather than a bespoke NLP pipeline.
"""

from __future__ import annotations

from app.text_extraction import extract_category, extract_price_paise

MIN_DESCRIPTION_LENGTH = 20


def assess_catalog_item(raw_text: str) -> dict:
    price_paise = extract_price_paise(raw_text)
    category = extract_category(raw_text)
    description_length_ok = len(raw_text.strip()) >= MIN_DESCRIPTION_LENGTH

    checks = {
        "has_price": price_paise is not None,
        "has_category": category is not None,
        "description_length_ok": description_length_ok,
    }
    gaps = []
    if not checks["has_price"]:
        gaps.append("no price detected")
    if not checks["has_category"]:
        gaps.append("could not infer a product category")
    if not checks["description_length_ok"]:
        gaps.append(f"description shorter than {MIN_DESCRIPTION_LENGTH} characters")

    return {
        "raw_text": raw_text,
        "extracted_price_paise": price_paise,
        "extracted_category": category,
        "checks": checks,
        "readiness_score": sum(checks.values()) / len(checks),
        "gaps": gaps,
    }


def assess_catalog(items: list[str]) -> dict:
    assessed_items = [assess_catalog_item(item) for item in items]
    overall_score = (
        sum(item["readiness_score"] for item in assessed_items) / len(assessed_items)
        if assessed_items else 0.0
    )
    return {
        "items": assessed_items,
        "overall_readiness_score": overall_score,
        "item_count": len(assessed_items),
    }
