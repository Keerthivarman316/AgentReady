from app.text_extraction import extract_product_keywords


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
