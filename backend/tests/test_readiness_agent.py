from app.readiness_agent import assess_catalog, assess_catalog_item


def test_assess_catalog_item_full_signal():
    item = assess_catalog_item("Premium wireless earbuds with ANC — priced at ₹1999, best in class sound.")
    assert item["checks"]["has_price"] is True
    assert item["checks"]["has_category"] is True
    assert item["checks"]["description_length_ok"] is True
    assert item["readiness_score"] == 1.0
    assert item["gaps"] == []


def test_assess_catalog_item_missing_price():
    item = assess_catalog_item("Amazing wireless earbuds with incredible sound quality and long battery life")
    assert item["checks"]["has_price"] is False
    assert "no price detected" in item["gaps"]


def test_assess_catalog_item_missing_category():
    item = assess_catalog_item("Best product ever, only ₹999, you will love it so much")
    assert item["checks"]["has_category"] is False
    assert "could not infer a product category" in item["gaps"]


def test_assess_catalog_item_too_short():
    item = assess_catalog_item("earbuds ₹999")
    assert item["checks"]["description_length_ok"] is False


def test_assess_catalog_overall_score_averages_items():
    result = assess_catalog([
        "Premium wireless earbuds with ANC — priced at ₹1999, best in class sound.",
        "ok",
    ])
    assert result["item_count"] == 2
    assert 0.0 < result["overall_readiness_score"] < 1.0


def test_assess_catalog_empty_list():
    result = assess_catalog([])
    assert result["overall_readiness_score"] == 0.0
    assert result["item_count"] == 0
