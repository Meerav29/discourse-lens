import sqlite3
from pathlib import Path

import pytest

from backend.processing.dedup import chunk_and_dedup
from backend.embedding import embed
from backend.synthesis.rag import order_and_dedupe_by_article
from backend.api.main import fetch_outliers


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
    monkeypatch.setattr(embed, "EMBEDDING_MODE", "local")
    assert embed.prepare_texts(["hi"], "document") == ["search_document: hi"]


def test_nomic_query_prefix(monkeypatch):
    monkeypatch.setattr(embed, "EMBEDDING_MODE", "local")
    assert embed.prepare_texts(["hi"], "query") == ["search_query: hi"]


def test_openai_has_no_prefix(monkeypatch):
    monkeypatch.setattr(embed, "EMBEDDING_MODE", "openai")
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


# ── outliers ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path(__file__).parent.parent / "backend" / "db" / "schema.sql"
    conn.executescript(schema.read_text())
    conn.executemany(
        "INSERT INTO articles (id, url, title, status) VALUES (?,?,?,?)",
        [("a1", "u1", "A1", "ok"), ("a2", "u2", "A2", "ok"), ("a3", "u3", "A3", "ok")],
    )
    chunks = [("a1#0", "a1"), ("a1#1", "a1"), ("a1#2", "a1"), ("a2#0", "a2"), ("a3#0", "a3")]
    conn.executemany("INSERT INTO chunks (id, article_id) VALUES (?,?)", chunks)
    conn.executemany(
        "INSERT INTO projections (chunk_id, cluster_id, cluster_label, distance_from_centroid) "
        "VALUES (?,?,?,?)",
        [
            ("a1#0", 0, "zero", 9.0),
            ("a1#1", 0, "zero", 8.0),
            ("a1#2", 0, "zero", 7.0),
            ("a2#0", 0, "zero", 1.0),
            ("a3#0", 1, "one", 5.0),
        ],
    )
    yield conn
    conn.close()


def test_outliers_one_row_per_article(db):
    rows = fetch_outliers(db)
    assert [r["article_id"] for r in rows] == ["a1", "a3", "a2"]
    assert rows[0]["chunk_id"] == "a1#0"
    assert rows[0]["distance_from_centroid"] == 9.0


def test_outliers_filtered_by_cluster(db):
    rows = fetch_outliers(db, cluster_id=1)
    assert [r["article_id"] for r in rows] == ["a3"]
