"""
Two-level chunker: parent chunks (~1500 tokens) with 100-token overlap,
child chunks (~300 tokens) with 50-token overlap.

Chunk ID format: {article_id}#p{parent_index}c{child_index}
Parent ID format: {article_id}#p{parent_index}
"""

from __future__ import annotations

import re
from typing import Iterator

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")

PARENT_SIZE = 1500
PARENT_OVERLAP = 100
CHILD_SIZE = 300
CHILD_OVERLAP = 50


def _tokenize(text: str) -> list[int]:
    return _ENC.encode(text, disallowed_special=())


def _decode(tokens: list[int]) -> str:
    return _ENC.decode(tokens)


def _sliding_window(tokens: list[int], size: int, overlap: int) -> Iterator[list[int]]:
    step = size - overlap
    start = 0
    while start < len(tokens):
        chunk = tokens[start : start + size]
        yield chunk
        if start + size >= len(tokens):
            break
        start += step


def chunk_article(article_id: str, text: str) -> list[dict]:
    """
    Returns a flat list of child-chunk dicts, each containing:
      id, article_id, parent_id, parent_text, child_text,
      chunk_index (global, 0-based), token_count, is_duplicate (always 0 here)
    """
    text = _clean(text)
    tokens = _tokenize(text)

    if not tokens:
        return []

    rows: list[dict] = []
    global_child_index = 0

    for p_idx, parent_tokens in enumerate(_sliding_window(tokens, PARENT_SIZE, PARENT_OVERLAP)):
        parent_text = _decode(parent_tokens)
        parent_id = f"{article_id}#p{p_idx}"

        for c_idx, child_tokens in enumerate(_sliding_window(parent_tokens, CHILD_SIZE, CHILD_OVERLAP)):
            child_text = _decode(child_tokens)
            rows.append(
                {
                    "id": f"{article_id}#p{p_idx}c{c_idx}",
                    "article_id": article_id,
                    "parent_id": parent_id,
                    "parent_text": parent_text,
                    "child_text": child_text,
                    "chunk_index": global_child_index,
                    "token_count": len(child_tokens),
                    "is_duplicate": 0,
                }
            )
            global_child_index += 1

    return rows


def _clean(text: str) -> str:
    """Normalize unicode whitespace and collapse runs."""
    import unicodedata
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
