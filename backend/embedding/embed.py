"""
Embed child chunks using either:
  - local: Ollama nomic-embed-text
  - openai: text-embedding-3-small

Always batched at max 32 chunks at a time.
Returns list of dicts with chunk_id + vector.
"""

from __future__ import annotations

import os
from typing import Generator

import httpx

BATCH_SIZE = 32
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "local")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = "nomic-embed-text"


def _batched(items: list, size: int) -> Generator[list, None, None]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _embed_local(texts: list[str]) -> list[list[float]]:
    """Call Ollama embed endpoint. Tries /api/embed (>=0.1.33) then falls back to /api/embeddings."""
    url = f"{OLLAMA_BASE_URL}/api/embed"
    resp = httpx.post(
        url,
        json={"model": OLLAMA_MODEL, "input": texts},
        timeout=120.0,
    )
    if resp.status_code == 404:
        # Older Ollama: /api/embeddings takes one prompt at a time
        return _embed_local_legacy(texts)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _embed_local_legacy(texts: list[str]) -> list[list[float]]:
    """Ollama <0.1.33 fallback: /api/embeddings, one text at a time."""
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    results = []
    for text in texts:
        resp = httpx.post(
            url,
            json={"model": OLLAMA_MODEL, "prompt": text},
            timeout=120.0,
        )
        resp.raise_for_status()
        results.append(resp.json()["embedding"])
    return results


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in resp.data]


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes a list of chunk dicts (must have 'id' and 'child_text').
    Returns list of dicts: {chunk_id, vector}.
    Processes in batches of BATCH_SIZE.
    """
    results: list[dict] = []

    embed_fn = _embed_local if EMBEDDING_MODE == "local" else _embed_openai

    for batch in _batched(chunks, BATCH_SIZE):
        texts = [c["child_text"] for c in batch]
        vectors = embed_fn(texts)
        for chunk, vector in zip(batch, vectors):
            results.append({"chunk_id": chunk["id"], "vector": vector})

    return results
