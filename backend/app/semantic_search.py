"""Semantic product search: real embeddings, real cosine-similarity ranking
— computed in Python rather than via a Postgres `vector` column + ivfflat
index, because this project's dev Postgres has no pgvector extension
available to install (confirmed absent from `pg_available_extensions`, and
the install directory isn't writable from this environment). See
db/schema.sql's comment on `products.embedding` for the same note.

At this dataset's scale (a few thousand products, scoped to one category
per query) an in-Python cosine-similarity pass over a category's embeddings
is fast enough that a database-side index would be solving a scaling
problem this project doesn't have yet.
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
    """Embeds `query_text`, ranks every embedded product in `category_id` by
    cosine similarity, and returns the top `limit` scoring at or above
    `min_similarity`. Returns [] (never raises) when the LLM isn't
    configured or no products in the category have an embedding yet —
    callers must treat that the same as "no semantic match", not an error."""
    if not is_llm_configured():
        return []

    cur.execute(
        "SELECT id, name, price_paise, embedding FROM products WHERE category_id = %s AND embedding IS NOT NULL",
        (category_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return []

    embedded = embed_texts([query_text])
    if not embedded:
        return []
    query_vec = np.array(embedded[0])

    matrix = np.array([row[3] for row in rows])
    similarities = _cosine_similarities(query_vec, matrix)

    ranked = sorted(
        (
            {"product_id": str(rows[i][0]), "product_name": rows[i][1], "price_paise": rows[i][2],
             "similarity": float(similarities[i])}
            for i in range(len(rows))
        ),
        key=lambda r: r["similarity"], reverse=True,
    )
    return [r for r in ranked if r["similarity"] >= min_similarity][:limit]
