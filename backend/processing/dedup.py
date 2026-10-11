"""
MinHash LSH deduplication for child chunks.

Uses 128 permutations and a Jaccard similarity threshold of 0.85.
Near-duplicate chunks (all but one per duplicate set) are marked is_duplicate=1.
"""

from __future__ import annotations

import re

from datasketch import MinHash, MinHashLSH

NUM_PERM = 128
THRESHOLD = 0.85


def _shingles(text: str, k: int = 5) -> set[bytes]:
    """Character k-shingles as bytes (fast, language-agnostic)."""
    text = re.sub(r"\s+", " ", text.lower().strip())
    return {text[i : i + k].encode("utf-8") for i in range(len(text) - k + 1)}


def _make_minhash(text: str) -> MinHash:
    m = MinHash(num_perm=NUM_PERM)
    for shingle in _shingles(text):
        m.update(shingle)
    return m


def mark_duplicates(chunks: list[dict]) -> list[dict]:
    """
    Given a list of chunk dicts (as returned by chunker.chunk_article),
    mark near-duplicates in-place: sets is_duplicate=1 for all but the
    first occurrence in each near-duplicate set.

    Returns the same list (mutated).
    """
    lsh = MinHashLSH(threshold=THRESHOLD, num_perm=NUM_PERM)
    minhashes: dict[str, MinHash] = {}

    for chunk in chunks:
        cid = chunk["id"]
        text = chunk["child_text"]
        if len(text.strip()) < 20:
            # Too short to meaningfully dedup — leave as-is
            continue
        m = _make_minhash(text)
        minhashes[cid] = m

        candidates = lsh.query(m)
        if candidates:
            # A near-duplicate already exists — mark this one
            chunk["is_duplicate"] = 1
        else:
            lsh.insert(cid, m)

    return chunks


def chunk_and_dedup(articles: list[dict]) -> list[dict]:
    """
    Chunk every article (dicts with 'id' and 'raw_text'), then dedup across the
    whole corpus in one pass so syndicated copies of the same story on different
    sites are caught. Earlier articles keep their chunks; later copies are marked.
    """
    from backend.processing.chunker import chunk_article

    chunks: list[dict] = []
    for art in articles:
        if art.get("raw_text"):
            chunks.extend(chunk_article(art["id"], art["raw_text"]))
    return mark_duplicates(chunks)
