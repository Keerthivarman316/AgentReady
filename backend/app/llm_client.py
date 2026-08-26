"""Thin Gemini REST client — no SDK dependency, just `httpx` (already a
transitive dependency of langchain-core/langgraph; listed explicitly in
requirements.txt for clarity).

Every caller of `generate_json` must treat `None` as "fall through to the
deterministic non-LLM path", the same discipline `checkout.py` already
applies to `is_razorpay_configured()`: this project never becomes
hard-dependent on an external API key being present, and a network hiccup
never surfaces as a user-facing error.
"""

from __future__ import annotations

import json
import os

import httpx

TEXT_MODEL = "gemini-3.6-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# gemini-3.6-flash thinks by default (no supported way to disable it on this
# model — a thinkingBudget: 0 request 400s) and that routinely pushes even a
# short structured-extraction prompt past 8s, let alone a longer summary
# prompt. 20s keeps the LLM path from being timed out into its own fallback
# more often than an actual failure warrants.
_DEFAULT_TIMEOUT = 20.0


def is_llm_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate_json(prompt: str, response_schema: dict, *, model: str = TEXT_MODEL,
                   timeout: float = _DEFAULT_TIMEOUT) -> dict | None:
    """Returns a parsed JSON object matching `response_schema` (Gemini's
    OpenAPI-subset schema format — uppercase types: OBJECT/STRING/INTEGER),
    or None on any failure: unconfigured, network error, non-200, or a
    response that doesn't parse as JSON. Never raises."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            f"{_BASE_URL}/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": response_schema,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        return json.loads(text)
    except Exception:
        return None


def generate_text(prompt: str, *, model: str = TEXT_MODEL, timeout: float = _DEFAULT_TIMEOUT) -> str | None:
    """Plain-text generation (no structured schema) — returns None on any
    failure, same discipline as generate_json."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            f"{_BASE_URL}/models/{model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except Exception:
        return None


def embed_texts(texts: list[str], *, output_dimensionality: int = 768,
                 model: str = EMBEDDING_MODEL, timeout: float = 30.0) -> list[list[float]] | None:
    """Batch-embeds up to 100 texts in one call via Gemini's
    batchEmbedContents. Returns None (never a partial list) on any failure —
    callers must fall back to leaving embeddings unset for the whole batch,
    not attempt to mix embedded/unembedded rows from a partial success."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not texts:
        return None
    try:
        resp = httpx.post(
            f"{_BASE_URL}/models/{model}:batchEmbedContents",
            params={"key": api_key},
            json={
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": output_dimensionality,
                    }
                    for t in texts
                ]
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        embeddings = resp.json()["embeddings"]
        return [e["values"] for e in embeddings]
    except Exception:
        return None
