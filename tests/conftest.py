import json

import pytest

from backend.config import settings
from backend.db import connect, init_db


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the app at a fresh SQLite file and LanceDB directory."""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "lance_path", str(tmp_path / "vectors"))
    init_db()
    return tmp_path


def add_analysis(analysis_id, topic="topic", status="done"):
    conn = connect()
    conn.execute(
        "INSERT INTO analyses (id, topic, status, progress, created_ts, updated_ts) "
        "VALUES (?,?,?,?,?,?)",
        (analysis_id, topic, status, 100, 1, 1),
    )
    conn.commit()
    conn.close()


def add_article(analysis_id, article_id, cluster_id=0, distance=0.1, x=0.0, y=0.0, chunks=1):
    """Insert an article, `chunks` chunks of it, and its map placement."""
    conn = connect()
    conn.execute(
        "INSERT INTO articles (id, analysis_id, url, title, status) VALUES (?,?,?,?,?)",
        (article_id, analysis_id, f"https://example.com/{article_id}", article_id.upper(), "ok"),
    )
    conn.executemany(
        "INSERT INTO chunks (id, analysis_id, article_id, child_text) VALUES (?,?,?,?)",
        [(f"{article_id}#{i}", analysis_id, article_id, f"text {i}") for i in range(chunks)],
    )
    conn.execute(
        "INSERT INTO placements (article_id, analysis_id, x, y, cluster_id, distance) "
        "VALUES (?,?,?,?,?,?)",
        (article_id, analysis_id, x, y, cluster_id, distance),
    )
    conn.commit()
    conn.close()


def add_cluster(analysis_id, cluster_id, label, article_count=1, terms=(), description=None):
    conn = connect()
    conn.execute(
        "INSERT INTO clusters (analysis_id, cluster_id, label, description, article_count, terms) "
        "VALUES (?,?,?,?,?,?)",
        (analysis_id, cluster_id, label, description, article_count, json.dumps(list(terms))),
    )
    conn.commit()
    conn.close()


_VOCAB = (
    "energy efficiency demand rebound policy price carbon household city heat roof tree "
    "climate study report evidence cost growth consumption supply market tax standard data "
    "model risk exposure equity income region urban rural building water power grid fuel "
    "coal oil gas solar wind storage transport vehicle industry economy research analysis"
).split()


def prose(seed: int, words: int = 400) -> str:
    """Varied, article-length filler text (repeating one sentence is unrealistic:
    it has only a handful of distinct word sequences)."""
    import random

    rng = random.Random(seed)
    return " ".join(rng.choice(_VOCAB) for _ in range(words)) + "."
