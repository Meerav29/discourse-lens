"""
Embed child chunks using either:
  - local: Ollama nomic-embed-text
  - openai: text-embedding-3-small

Always batched at max 32 chunks at a time.
Returns list of dicts with chunk_id + vector.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

import httpx

from backend.config import settings

BATCH_SIZE = 32
OLLAMA_MODEL = "nomic-embed-text"

# nomic-embed-text is trained with task prefixes; without them retrieval and
# clustering quality drop. OpenAI models take raw text.
_NOMIC_PREFIXES = {"document": "search_document: ", "query": "search_query: "}


def _batched(items: list, size: int) -> Generator[list, None, None]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _embed_local(texts: list[str]) -> list[list[float]]:
    """Call Ollama embed endpoint. Tries /api/embed (>=0.1.33) then falls back to /api/embeddings."""
    url = f"{settings.ollama_base_url}/api/embed"
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
    url = f"{settings.ollama_base_url}/api/embeddings"
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

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in resp.data]


def prepare_texts(texts: list[str], kind: str) -> list[str]:
    """Apply the model's task prefix. kind is 'document' or 'query'."""
    if kind not in _NOMIC_PREFIXES:
        raise ValueError(f"kind must be 'document' or 'query', got {kind!r}")
    if settings.embedding_mode != "local":
        return texts
    prefix = _NOMIC_PREFIXES[kind]
    return [prefix + t for t in texts]


def embed_chunks(
    chunks: list[dict],
    kind: str = "document",
    on_batch: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """
    Takes a list of chunk dicts (must have 'id' and 'child_text').
    kind: 'document' for corpus chunks, 'query' for search queries.
    Returns list of dicts: {chunk_id, vector}.
    Processes in batches of BATCH_SIZE; on_batch(done, total) runs after each.
    """
    results: list[dict] = []

    embed_fn = _embed_local if settings.embedding_mode == "local" else _embed_openai

    for batch in _batched(chunks, BATCH_SIZE):
        texts = prepare_texts([c["child_text"] for c in batch], kind)
        vectors = embed_fn(texts)
        for chunk, vector in zip(batch, vectors, strict=True):
            results.append({"chunk_id": chunk["id"], "vector": vector})
        if on_batch:
            on_batch(len(results), len(chunks))

    return results
