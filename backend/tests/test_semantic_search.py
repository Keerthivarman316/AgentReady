import numpy as np

from app.semantic_search import _cosine_similarities, find_similar_products, is_semantic_search_available


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self._rows


def test_is_semantic_search_available_false_when_unconfigured():
    # GEMINI_API_KEY absent by default via conftest.py's autouse fixture.
    assert is_semantic_search_available() is False


def test_cosine_similarities_identical_vector_scores_one():
    query = np.array([1.0, 0.0, 0.0])
    matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    scores = _cosine_similarities(query, matrix)
    assert scores[0] == 1.0
    assert scores[1] == 0.0


def test_cosine_similarities_handles_zero_vector_row_without_dividing_by_zero():
    query = np.array([1.0, 0.0])
    matrix = np.array([[0.0, 0.0], [1.0, 0.0]])
    scores = _cosine_similarities(query, matrix)
    assert scores[0] == 0.0
    assert scores[1] == 1.0


def test_find_similar_products_returns_empty_when_unconfigured():
    cur = FakeCursor([("p1", "Wireless Earbuds Pro", 199900, [1.0, 0.0])])
    assert find_similar_products(cur, "earbuds", "cat-1") == []


def test_find_similar_products_returns_empty_when_no_embedded_products(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    cur = FakeCursor([])
    assert find_similar_products(cur, "earbuds", "cat-1") == []


def test_find_similar_products_ranks_and_filters_by_similarity(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.semantic_search.embed_texts", lambda texts: [[1.0, 0.0]])
    rows = [
        ("p-close", "Noise Cancelling Headphones", 249900, [0.99, 0.14]),   # near-identical direction
        ("p-far", "USB-C Fast Charger", 99900, [0.0, 1.0]),                 # orthogonal -> filtered out
    ]
    cur = FakeCursor(rows)
    results = find_similar_products(cur, "something to block outside noise", "cat-1", min_similarity=0.5)
    assert [r["product_id"] for r in results] == ["p-close"]
    assert results[0]["similarity"] > 0.9


def test_find_similar_products_returns_empty_when_embedding_call_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.semantic_search.embed_texts", lambda texts: None)
    cur = FakeCursor([("p1", "Wireless Earbuds Pro", 199900, [1.0, 0.0])])
    assert find_similar_products(cur, "earbuds", "cat-1") == []
