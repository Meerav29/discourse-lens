"""v1 (single global corpus + jobs table) → v2 (analyses)."""

import sqlite3

import lancedb

from backend.config import settings
from backend.db import connect, init_db
from backend.embedding import store

V1_SCHEMA = """
CREATE TABLE articles (id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, domain TEXT, title TEXT,
  publish_date TEXT, crawl_ts INTEGER, word_count INTEGER, language TEXT DEFAULT 'en',
  raw_text TEXT, status TEXT DEFAULT 'ok');
CREATE TABLE chunks (id TEXT PRIMARY KEY, article_id TEXT REFERENCES articles(id),
  parent_id TEXT, parent_text TEXT, child_text TEXT, chunk_index INTEGER,
  token_count INTEGER, is_duplicate INTEGER DEFAULT 0);
CREATE TABLE projections (chunk_id TEXT PRIMARY KEY REFERENCES chunks(id), x REAL, y REAL,
  cluster_id INTEGER, cluster_label TEXT, distance_from_centroid REAL);
CREATE TABLE jobs (id TEXT PRIMARY KEY, topic TEXT, status TEXT, progress INTEGER DEFAULT 0,
  article_count INTEGER DEFAULT 0, error_msg TEXT, warning TEXT, created_ts INTEGER,
  updated_ts INTEGER);
"""


def _make_v1(tmp_path, monkeypatch, with_corpus=True, warning_column=True):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "old.db"))
    monkeypatch.setattr(settings, "lance_path", str(tmp_path / "vectors"))
    conn = sqlite3.connect(settings.db_path)
    schema = V1_SCHEMA if warning_column else V1_SCHEMA.replace("warning TEXT, ", "")
    conn.executescript(schema)
    jobs = [
        ("old-job", "older topic", "done", 100, 10, None, None, 1, 2),
        ("job-1", "jevons paradox", "done", 100, 52, None, "sparse", 3, 4),
        ("job-err", "broken", "error", 20, 0, "boom", None, 5, 6),
    ]
    if warning_column:
        conn.executemany("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)", jobs)
    else:
        conn.executemany(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)", [j[:6] + j[7:] for j in jobs]
        )
    if with_corpus:
        conn.execute("INSERT INTO articles (id, url, title) VALUES ('a1', 'https://x/1', 'T')")
        conn.execute("INSERT INTO chunks (id, article_id, child_text) VALUES ('a1#p0c0', 'a1', 't')")
        conn.execute(
            "INSERT INTO projections VALUES ('a1#p0c0', 1.0, 2.0, 0, 'Label', 0.5)"
        )
        lancedb.connect(settings.lance_path).create_table(
            store.LEGACY_TABLE_NAME,
            data=[{"chunk_id": "a1#p0c0", "article_id": "a1", "vector": [0.1, 0.2],
                   "child_text": "t", "domain": "x", "publish_date": "", "cluster_id": 0}],
        )
    conn.commit()
    conn.close()


def test_corpus_becomes_latest_finished_job(tmp_path, monkeypatch):
    _make_v1(tmp_path, monkeypatch)
    init_db()

    conn = connect()
    analyses = [dict(r) for r in conn.execute("SELECT * FROM analyses")]
    assert len(analyses) == 1
    assert analyses[0]["id"] == "job-1"
    assert analyses[0]["topic"] == "jevons paradox"
    assert analyses[0]["warning"] == "sparse"
    for table in ("articles", "chunks", "projections"):
        ids = {r[0] for r in conn.execute(f"SELECT analysis_id FROM {table}")}
        assert ids == {"job-1"}, table
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "jobs" not in tables and "articles_v1" not in tables

    rows = store.read_all_embeddings("job-1")
    assert [r["chunk_id"] for r in rows] == ["a1#p0c0"]
    assert "cluster_id" not in rows[0]
    db = lancedb.connect(settings.lance_path)
    assert not store.table_exists(db, store.LEGACY_TABLE_NAME)
    assert (tmp_path / "old.db.v1.bak").exists()
    assert (tmp_path / "vectors.v1.bak").is_dir()


def test_empty_v1_database_migrates_to_no_analyses(tmp_path, monkeypatch):
    _make_v1(tmp_path, monkeypatch, with_corpus=False)
    init_db()
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0
    conn.close()


def test_migration_is_idempotent(tmp_path, monkeypatch):
    _make_v1(tmp_path, monkeypatch)
    init_db()
    init_db()
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
    conn.close()


def test_v1_without_warning_column(tmp_path, monkeypatch):
    # The `warning` column was added to v1 later; early databases lack it.
    _make_v1(tmp_path, monkeypatch, warning_column=False)
    init_db()
    conn = connect()
    row = conn.execute("SELECT id, warning FROM analyses").fetchone()
    conn.close()
    assert (row["id"], row["warning"]) == ("job-1", None)
