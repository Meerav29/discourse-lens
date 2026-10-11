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


def add_chunk(analysis_id, article_id, chunk_id, cluster_id=0, distance=1.0, label="zero"):
    """Insert an article (if new), one chunk and its projection."""
    conn = connect()
    conn.execute(
        "INSERT OR IGNORE INTO articles (id, analysis_id, url, title, status) VALUES (?,?,?,?,?)",
        (article_id, analysis_id, f"https://example.com/{article_id}", article_id.upper(), "ok"),
    )
    conn.execute(
        "INSERT INTO chunks (id, analysis_id, article_id, child_text) VALUES (?,?,?,?)",
        (chunk_id, analysis_id, article_id, f"text of {chunk_id}"),
    )
    conn.execute(
        "INSERT INTO projections (chunk_id, analysis_id, x, y, cluster_id, cluster_label, "
        "distance_from_centroid) VALUES (?,?,?,?,?,?,?)",
        (chunk_id, analysis_id, 0.0, 0.0, cluster_id, label, distance),
    )
    conn.commit()
    conn.close()
