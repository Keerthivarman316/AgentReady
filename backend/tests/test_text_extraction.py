from app.text_extraction import extract_category, extract_deadline_days, extract_product_keywords


def test_extract_product_keywords_matches_earbuds():
    assert extract_product_keywords("wireless earbuds under 2000 within 3 days") == ["earbud"]


def test_extract_product_keywords_no_match_returns_empty():
    assert extract_product_keywords("something under 2000") == []


def test_extract_product_keywords_prefers_longer_phrase_over_substring():
    # "fitness tracker" should win over the shorter "tracker" trigger it contains.
    assert extract_product_keywords("need a fitness tracker under 3000") == ["fitness tracker"]


def test_extract_product_keywords_multiple_distinct_matches():
    keywords = extract_product_keywords("earbuds or a charger under 2000")
    assert set(keywords) == {"earbud", "charger"}


def test_extract_product_keywords_matches_monitor():
    assert extract_product_keywords("monitor under 10k") == ["monitor"]


def test_extract_category_infers_electronics_from_monitor():
    assert extract_category("monitor under 10k") == "Electronics"


def test_extract_product_keywords_matches_recently_added_items():
    assert extract_product_keywords("need a badminton set under 1500") == ["badminton"]
    assert extract_product_keywords("looking for an air fryer under 5000") == ["air fryer"]
    assert extract_product_keywords("want a nice perfume under 2000") == ["perfume"]


def test_extract_deadline_days_returns_none_when_unspecified():
    assert extract_deadline_days("monitor under 10k") is None


def test_extract_deadline_days_within_pattern():
    assert extract_deadline_days("need it within 5 days") == 5
