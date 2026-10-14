"""
SQLite access: connections, schema creation and migration.

Every connection enables foreign keys (so deleting an analysis cascades) and a
busy timeout, and the database runs in WAL mode so a pipeline writing in a
worker thread does not block API reads.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path

from backend.config import settings

log = logging.getLogger(__name__)

SCHEMA_VERSION = 6
_SCHEMA = Path(__file__).parent / "schema.sql"

# Chunk-level map rows used by schema v2/v3, before placements + clusters.
_LEGACY_PROJECTIONS = """
CREATE TABLE IF NOT EXISTS projections (
  chunk_id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, x REAL, y REAL,
  cluster_id INTEGER, cluster_label TEXT, distance_from_centroid REAL
)
"""

# Analyses still in one of these states are being worked on by a pipeline.
RUNNING_STATUSES = ("queued", "crawling", "processing", "embedding", "projecting")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create or migrate the schema, then fail any analysis a restart interrupted."""
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 2 and _table_exists(conn, "jobs"):
            conn.close()
            _migrate_v1_to_v2(path)
            conn = connect(path)
        # v2 -> v3: new events table (created by the schema script) + stage_detail.
        # v3 -> v4: clusters + placements tables (schema script), projections converted.
        # v4 -> v5: chat_messages table (schema script).
        conn.executescript(_SCHEMA.read_text())
        _ensure_column(conn, "analyses", "stage_detail", "TEXT")
        _ensure_column(conn, "articles", "source_note", "TEXT")  # v5 -> v6
        if _table_exists(conn, "projections"):
            _migrate_projections(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        placeholders = ",".join("?" for _ in RUNNING_STATUSES)
        conn.execute(
            f"UPDATE analyses SET status='error', error_msg=?, updated_ts=? "
            f"WHERE status IN ({placeholders})",
            ("Interrupted by a server restart", int(time.time()), *RUNNING_STATUSES),
        )
        conn.commit()
    finally:
        conn.close()


def _schema_statements() -> list[str]:
    """
    schema.sql as individual statements, for running inside an explicit
    transaction (executescript would commit first). Comments are stripped
    before splitting so a ';' in a comment can't break a statement.
    """
    lines = [line.split("--", 1)[0] for line in _SCHEMA.read_text().splitlines()]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def _migrate_projections(conn: sqlite3.Connection) -> None:
    """
    v3 -> v4: chunk-level projections become article placements plus a
    clusters table. Each article takes the cluster most of its chunks were in
    (ties: lower id), sits at the mean of those chunks, and keeps their largest
    distance. Key terms and descriptions are empty until the analysis is
    re-clustered (scripts/recluster.py).
    """
    rows = conn.execute(
        "SELECT p.analysis_id, c.article_id, p.x, p.y, p.cluster_id, p.cluster_label, "
        "p.distance_from_centroid AS distance "
        "FROM projections p JOIN chunks c ON c.id = p.chunk_id"
    ).fetchall()
    by_article: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_article.setdefault(r["article_id"], []).append(r)

    placements, labels, sizes = [], {}, {}
    for article_id, chunks in by_article.items():
        votes: dict[int, int] = {}
        for c in chunks:
            votes[c["cluster_id"]] = votes.get(c["cluster_id"], 0) + 1
        cluster = min(votes, key=lambda k: (-votes[k], k))
        mine = [c for c in chunks if c["cluster_id"] == cluster]
        analysis_id = mine[0]["analysis_id"]
        placements.append((
            article_id, analysis_id,
            sum(c["x"] for c in mine) / len(mine), sum(c["y"] for c in mine) / len(mine),
            cluster, max(c["distance"] for c in mine),
        ))
        key = (analysis_id, cluster)
        labels.setdefault(key, mine[0]["cluster_label"] or f"Cluster {cluster + 1}")
        sizes[key] = sizes.get(key, 0) + 1

    conn.executemany(
        "INSERT OR REPLACE INTO placements (article_id, analysis_id, x, y, cluster_id, distance) "
        "VALUES (?,?,?,?,?,?)",
        placements,
    )
    conn.executemany(
        "INSERT OR REPLACE INTO clusters (analysis_id, cluster_id, label, article_count) "
        "VALUES (?,?,?,?)",
        [(a, c, labels[(a, c)], n) for (a, c), n in sizes.items()],
    )
    conn.execute("DROP TABLE projections")
    log.info("Converted %d articles' map positions to placements", len(placements))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _migrate_v1_to_v2(path: str) -> None:
    """
    v1 had a single global corpus plus a `jobs` table. The corpus becomes one
    analysis, keyed by the most recent finished job. The old database file and
    vector directory are kept alongside as backups.
    """
    from backend.embedding import store

    backup = f"{path}.v1.bak"
    shutil.copy2(path, backup)
    if Path(settings.lance_path).exists():
        shutil.copytree(settings.lance_path, f"{settings.lance_path}.v1.bak", dirs_exist_ok=True)
    log.info("Migrating %s to schema v2 (backup at %s)", path, backup)

    conn = connect(path)
    try:
        has_corpus = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] > 0
        job = conn.execute(
            "SELECT * FROM jobs WHERE status='done' ORDER BY updated_ts DESC LIMIT 1"
        ).fetchone()
        # Older v1 databases lack columns that were added later (e.g. `warning`).
        job = dict(job) if job else {}
        analysis_id = None
        if has_corpus:
            now = int(time.time())
            analysis_id = job.get("id", "imported-corpus")
            analysis = {
                "id": analysis_id,
                "topic": job.get("topic") or "Imported corpus",
                "status": "done",
                "progress": 100,
                "article_count": job.get("article_count") or 0,
                "warning": job.get("warning"),
                "created_ts": job.get("created_ts") or now,
                "updated_ts": job.get("updated_ts") or now,
            }
            # Copy vectors first: non-destructive, and re-runnable if we crash
            # before the SQL migration commits.
            store.adopt_legacy_table(analysis_id)

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        for table in ("articles", "chunks", "projections"):
            conn.execute(f"ALTER TABLE {table} RENAME TO {table}_v1")
        for statement in _schema_statements():
            conn.execute(statement)
        # v2/v3 kept chunk-level map rows; the v3 -> v4 step converts them.
        conn.execute(_LEGACY_PROJECTIONS)

        if analysis_id:
            conn.execute(
                "INSERT INTO analyses (id, topic, status, progress, article_count, warning, "
                "created_ts, updated_ts) VALUES (:id, :topic, :status, :progress, "
                ":article_count, :warning, :created_ts, :updated_ts)",
                analysis,
            )
            conn.execute(
                "INSERT INTO articles (id, analysis_id, url, domain, title, publish_date, "
                "crawl_ts, word_count, language, raw_text, status) "
                "SELECT id, ?, url, domain, title, publish_date, crawl_ts, word_count, "
                "language, raw_text, status FROM articles_v1",
                (analysis_id,),
            )
            conn.execute(
                "INSERT INTO chunks (id, analysis_id, article_id, parent_id, parent_text, "
                "child_text, chunk_index, token_count, is_duplicate) "
                "SELECT id, ?, article_id, parent_id, parent_text, child_text, chunk_index, "
                "token_count, is_duplicate FROM chunks_v1",
                (analysis_id,),
            )
            conn.execute(
                "INSERT INTO projections (chunk_id, analysis_id, x, y, cluster_id, "
                "cluster_label, distance_from_centroid) "
                "SELECT chunk_id, ?, x, y, cluster_id, cluster_label, distance_from_centroid "
                "FROM projections_v1 WHERE chunk_id IN (SELECT id FROM chunks)",
                (analysis_id,),
            )

        for table in ("projections_v1", "chunks_v1", "articles_v1", "jobs"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    store.drop_legacy_table()


def add_event(analysis_id: str, kind: str, message: str, url: str | None = None) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO analysis_events (analysis_id, ts, kind, message, url) VALUES (?,?,?,?,?)",
            (analysis_id, int(time.time()), kind, message, url),
        )
        conn.commit()
    finally:
        conn.close()


def update_analysis(analysis_id: str, **fields) -> None:
    fields["updated_ts"] = int(time.time())
    sets = ", ".join(f"{k}=?" for k in fields)
    conn = connect()
    try:
        conn.execute(f"UPDATE analyses SET {sets} WHERE id=?", [*fields.values(), analysis_id])
        conn.commit()
    finally:
        conn.close()
