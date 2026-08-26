"""Semantic product search: real embeddings, real cosine-similarity ranking
— computed in Python rather than via a Postgres `vector` column + ivfflat
index, because this project's dev Postgres has no pgvector extension
available to install (confirmed absent from `pg_available_extensions`, and
the install directory isn't writable from this environment). See
db/schema.sql's comment on `product_embeddings` for the same note.

Embeddings are looked up from `product_embeddings` (one row per distinct
product *type*, i.e. name) rather than a column on every product row —
every merchant in a category carries the identical catalog, so at a
100,000+ product scale, computing similarity once per distinct name (a
handful of rows) and only then fetching the (possibly many) matching
product rows keeps this fast without transferring a 768-float array once
per merchant listing.
"""

from __future__ import annotations

import numpy as np

from app.llm_client import embed_texts, is_llm_configured


def is_semantic_search_available() -> bool:
    return is_llm_configured()


def _cosine_similarities(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_norm = query_vec / (np.linalg.norm(query_vec) or 1.0)
    row_norms = np.linalg.norm(matrix, axis=1)
    row_norms[row_norms == 0] = 1.0
    normalized = matrix / row_norms[:, None]
    return normalized @ query_norm


def find_similar_products(cur, query_text: str, category_id: str, limit: int = 20,
                           min_similarity: float = 0.5) -> list[dict]:
    """Embeds `query_text`, ranks every distinct embedded product *type* in
    `category_id` by cosine similarity, then fetches the actual product rows
    for whichever types score at or above `min_similarity` (every row
    sharing a name shares that name's similarity — this is still "top N
    product rows", just computed via a handful of embedding comparisons
    instead of one per row). Returns [] (never raises) when the LLM isn't
    configured or nothing in the category has an embedded type yet —
    callers must treat that the same as "no semantic match", not an error."""
    if not is_llm_configured():
        return []

    cur.execute(
        """
        SELECT DISTINCT p.name, pe.embedding
        FROM products p JOIN product_embeddings pe ON pe.name = p.name
        WHERE p.category_id = %s
        """,
        (category_id,),
    )
    name_rows = cur.fetchall()
    if not name_rows:
        return []

    embedded = embed_texts([query_text])
    if not embedded:
        return []
    query_vec = np.array(embedded[0])

    names = [row[0] for row in name_rows]
    matrix = np.array([row[1] for row in name_rows])
    similarities = _cosine_similarities(query_vec, matrix)

    name_similarity = {name: float(sim) for name, sim in zip(names, similarities) if sim >= min_similarity}
    if not name_similarity:
        return []

    # Fetched name-by-name in similarity order (not `name = ANY(...)` +
    # SQL LIMIT) so the LIMIT is applied *after* ranking, not before it —
    # every row sharing a name is equally relevant, so pulling from the
    # highest-similarity name first and stopping once `limit` is reached
    # gives the true top-N without ever fetching more product rows than
    # asked for, regardless of how many merchants list a given type.
    results: list[dict] = []
    for name in sorted(name_similarity, key=name_similarity.get, reverse=True):
        if len(results) >= limit:
            break
        cur.execute(
            "SELECT id, price_paise FROM products WHERE category_id = %s AND name = %s LIMIT %s",
            (category_id, name, limit - len(results)),
        )
        results.extend(
            {"product_id": str(pid), "product_name": name, "price_paise": price, "similarity": name_similarity[name]}
            for pid, price in cur.fetchall()
        )
    return results
