import numpy as np

from app.semantic_search import _cosine_similarities, find_similar_products, is_semantic_search_available


class FakeCursor:
    """Returns each entry in `fetchall_results` in order, one per `execute()`
    call — find_similar_products makes exactly two queries (distinct
    name+embedding, then matching product rows), in that order."""

    def __init__(self, fetchall_results):
        self._results = list(fetchall_results)
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchall(self):
        return self._results.pop(0) if self._results else []


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
    cur = FakeCursor([[("Wireless Earbuds Pro", [1.0, 0.0])]])
    assert find_similar_products(cur, "earbuds", "cat-1") == []


def test_find_similar_products_returns_empty_when_no_embedded_types(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    cur = FakeCursor([[]])
    assert find_similar_products(cur, "earbuds", "cat-1") == []


def test_find_similar_products_ranks_and_filters_by_similarity(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.semantic_search.embed_texts", lambda texts: [[1.0, 0.0]])
    name_rows = [
        ("Noise Cancelling Headphones", [0.99, 0.14]),   # near-identical direction
        ("USB-C Fast Charger", [0.0, 1.0]),               # orthogonal -> filtered out
    ]
    product_rows = [("p-close-1", 249900), ("p-close-2", 259900)]
    cur = FakeCursor([name_rows, product_rows])
    results = find_similar_products(cur, "something to block outside noise", "cat-1", min_similarity=0.5)
    assert {r["product_id"] for r in results} == {"p-close-1", "p-close-2"}
    assert all(r["similarity"] > 0.9 for r in results)
    # Only the matching name is ever queried for product rows -- the
    # filtered-out orthogonal name never reaches a second query.
    assert len(cur.queries) == 2
    assert cur.queries[1][1][:2] == ("cat-1", "Noise Cancelling Headphones")


def test_find_similar_products_stops_once_limit_is_reached_across_multiple_names(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.semantic_search.embed_texts", lambda texts: [[1.0, 0.0]])
    name_rows = [
        ("Best Match", [1.0, 0.0]),
        ("Second Match", [0.9, 0.1]),
    ]
    # "Best Match" alone fills the limit, so "Second Match" should never be queried.
    cur = FakeCursor([name_rows, [("p1", 100), ("p2", 200), ("p3", 300)]])
    results = find_similar_products(cur, "query", "cat-1", limit=3, min_similarity=0.5)
    assert len(results) == 3
    assert len(cur.queries) == 2
    assert all(r["product_name"] == "Best Match" for r in results)


def test_find_similar_products_returns_empty_when_embedding_call_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr("app.semantic_search.embed_texts", lambda texts: None)
    cur = FakeCursor([[("Wireless Earbuds Pro", [1.0, 0.0])]])
    assert find_similar_products(cur, "earbuds", "cat-1") == []
