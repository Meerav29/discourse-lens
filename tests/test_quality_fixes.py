import pytest
from conftest import prose

from backend.config import settings
from backend.embedding import embed
from backend.processing.dedup import chunk_and_dedup
from backend.synthesis.rag import order_and_dedupe_by_article

# ── cross-article dedup ──────────────────────────────────────────────────────

SYNDICATED = (
    "The central bank raised interest rates by a quarter point on Wednesday, "
    "citing persistent inflation in services and a resilient labour market. "
) * 20


def test_dedup_catches_duplicates_across_articles():
    articles = [
        {"id": "a1", "raw_text": SYNDICATED},
        {"id": "a2", "raw_text": SYNDICATED},
    ]
    chunks = chunk_and_dedup(articles)
    a1 = [c for c in chunks if c["article_id"] == "a1"]
    a2 = [c for c in chunks if c["article_id"] == "a2"]
    assert a1 and a2
    assert all(c["is_duplicate"] == 1 for c in a2)
    # the first copy keeps at least one chunk
    assert any(c["is_duplicate"] == 0 for c in a1)


def test_dedup_keeps_distinct_articles():
    articles = [
        {"id": "a1", "raw_text": SYNDICATED},
        {"id": "a2", "raw_text": "Coral reefs bleach when ocean temperatures stay high. " * 40},
    ]
    chunks = chunk_and_dedup(articles)
    assert any(c["is_duplicate"] == 0 for c in chunks if c["article_id"] == "a2")


def test_dedup_skips_empty_text():
    assert chunk_and_dedup([{"id": "a1", "raw_text": ""}]) == []


# ── nomic task prefixes ──────────────────────────────────────────────────────

def test_nomic_document_prefix(monkeypatch):
    monkeypatch.setattr(settings, "embedding_mode", "local")
    assert embed.prepare_texts(["hi"], "document") == ["search_document: hi"]


def test_nomic_query_prefix(monkeypatch):
    monkeypatch.setattr(settings, "embedding_mode", "local")
    assert embed.prepare_texts(["hi"], "query") == ["search_query: hi"]


def test_openai_has_no_prefix(monkeypatch):
    monkeypatch.setattr(settings, "embedding_mode", "openai")
    assert embed.prepare_texts(["hi"], "query") == ["hi"]


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        embed.prepare_texts(["hi"], "passage")


# ── RAG ranking order ────────────────────────────────────────────────────────

def test_rag_keeps_best_ranked_chunk_per_article():
    ranked_ids = ["a2#p0c1", "a1#p0c0", "a2#p0c0"]
    # SQLite returns rows in arbitrary order
    rows = [
        {"chunk_id": "a2#p0c0", "article_id": "a2", "parent_text": "worse"},
        {"chunk_id": "a1#p0c0", "article_id": "a1", "parent_text": "second"},
        {"chunk_id": "a2#p0c1", "article_id": "a2", "parent_text": "best"},
    ]
    out = order_and_dedupe_by_article(rows, ranked_ids)
    assert [r["chunk_id"] for r in out] == ["a2#p0c1", "a1#p0c0"]


# ── article-level dedup ──────────────────────────────────────────────────────

def test_syndicated_copy_with_different_intro_is_a_duplicate():
    from backend.processing.dedup import find_duplicate_articles

    story = prose(1)
    articles = [
        {"id": "orig", "raw_text": story},
        {"id": "copy", "raw_text": "Reprinted with permission from the Wire Service. " + story},
        {"id": "other", "raw_text": prose(2)},
    ]
    assert find_duplicate_articles(articles) == {"copy": "orig"}
