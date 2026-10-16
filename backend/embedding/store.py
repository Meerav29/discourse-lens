"""
LanceDB read/write for embeddings — one table per analysis.

Table schema:
  chunk_id, article_id, vector, child_text, domain, publish_date
"""

from __future__ import annotations

import lancedb
import pyarrow as pa

from backend.config import settings

# Single global table used before analyses existed (schema v1).
LEGACY_TABLE_NAME = "embeddings"

_COLUMNS = ["chunk_id", "article_id", "vector", "child_text", "domain", "publish_date"]


def table_name(analysis_id: str) -> str:
    return "emb_" + analysis_id.replace("-", "")


def _connect() -> lancedb.DBConnection:
    return lancedb.connect(settings.lance_path)


def table_exists(db: lancedb.DBConnection, name: str) -> bool:
    """list_tables() is paginated — walk every page."""
    page_token = None
    while True:
        resp = db.list_tables(page_token=page_token)
        if name in resp.tables:
            return True
        page_token = resp.page_token
        if not page_token:
            return False


def open_table(analysis_id: str) -> lancedb.table.Table | None:
    db = _connect()
    name = table_name(analysis_id)
    return db.open_table(name) if table_exists(db, name) else None


def _schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("article_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
            pa.field("child_text", pa.string()),
            pa.field("domain", pa.string()),
            pa.field("publish_date", pa.string()),
        ]
    )


def write_embeddings(analysis_id: str, rows: list[dict]) -> None:
    """
    rows: dicts with chunk_id, article_id, vector, child_text, domain, publish_date.
    Creates the analysis's table or appends to it.
    """
    if not rows:
        return
    normalised = _normalise(rows)
    table = open_table(analysis_id)
    if table is None:
        _connect().create_table(
            table_name(analysis_id), data=normalised, schema=_schema(len(rows[0]["vector"]))
        )
    else:
        table.add(normalised)


def read_all_embeddings(analysis_id: str) -> list[dict]:
    """Return all rows of the analysis's table as a list of dicts."""
    table = open_table(analysis_id)
    if table is None:
        return []
    return table.to_pandas().to_dict(orient="records")


def drop_embeddings(analysis_id: str) -> None:
    db = _connect()
    name = table_name(analysis_id)
    if table_exists(db, name):
        db.drop_table(name)


def adopt_legacy_table(analysis_id: str) -> None:
    """Copy the pre-analyses global table into the analysis's own table (idempotent)."""
    db = _connect()
    if not table_exists(db, LEGACY_TABLE_NAME):
        return
    data = db.open_table(LEGACY_TABLE_NAME).to_arrow().select(_COLUMNS)
    db.create_table(table_name(analysis_id), data=data, mode="overwrite")


def drop_legacy_table() -> None:
    db = _connect()
    if table_exists(db, LEGACY_TABLE_NAME):
        db.drop_table(LEGACY_TABLE_NAME)


def _normalise(rows: list[dict]) -> list[dict]:
    """Ensure all fields have correct Python types for Arrow ingestion."""
    return [
        {
            "chunk_id": str(r.get("chunk_id", "")),
            "article_id": str(r.get("article_id", "")),
            "vector": [float(v) for v in r["vector"]],
            "child_text": str(r.get("child_text", "")),
            "domain": str(r.get("domain", "") or ""),
            "publish_date": str(r.get("publish_date", "") or ""),
        }
        for r in rows
    ]
