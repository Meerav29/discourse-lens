"""
LanceDB read/write for embeddings.

Table schema (per PLANNING.md §4.2):
  chunk_id, article_id, vector, child_text, domain, publish_date, cluster_id
"""

from __future__ import annotations

import os

import lancedb
import pyarrow as pa

LANCE_PATH = os.getenv("LANCE_PATH", "./data/vectors")
TABLE_NAME = "embeddings"
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "120"))


def _get_table(db: lancedb.DBConnection) -> lancedb.table.Table:
    names = db.table_names()
    if TABLE_NAME in names:
        return db.open_table(TABLE_NAME)
    return None


def write_embeddings(rows: list[dict]) -> None:
    """
    rows: list of dicts with keys:
      chunk_id, article_id, vector, child_text, domain, publish_date, cluster_id
    Creates or appends to the LanceDB embeddings table.
    """
    if not rows:
        return

    db = lancedb.connect(LANCE_PATH)
    table = _get_table(db)

    if table is None:
        # Infer dim from first row
        dim = len(rows[0]["vector"])
        schema = pa.schema(
            [
                pa.field("chunk_id", pa.string()),
                pa.field("article_id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
                pa.field("child_text", pa.string()),
                pa.field("domain", pa.string()),
                pa.field("publish_date", pa.string()),
                pa.field("cluster_id", pa.int32()),
            ]
        )
        # Normalise rows to correct types
        normalised = _normalise(rows)
        db.create_table(TABLE_NAME, data=normalised, schema=schema)
    else:
        normalised = _normalise(rows)
        table.add(normalised)


def read_all_embeddings() -> list[dict]:
    """Return all rows from the embeddings table as a list of dicts."""
    db = lancedb.connect(LANCE_PATH)
    table = _get_table(db)
    if table is None:
        return []
    return table.to_pandas().to_dict(orient="records")


def update_cluster_ids(chunk_cluster_map: dict[str, int]) -> None:
    """
    Update the cluster_id column for each chunk_id.
    LanceDB doesn't support in-place updates; we reload and overwrite.
    """
    if not chunk_cluster_map:
        return

    db = lancedb.connect(LANCE_PATH)
    table = _get_table(db)
    if table is None:
        return

    df = table.to_pandas()
    df["cluster_id"] = df["chunk_id"].map(
        lambda cid: chunk_cluster_map.get(cid, df.loc[df["chunk_id"] == cid, "cluster_id"].iloc[0])
    )
    # Overwrite table
    db.drop_table(TABLE_NAME)
    dim = len(df["vector"].iloc[0])
    schema = pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("article_id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
            pa.field("child_text", pa.string()),
            pa.field("domain", pa.string()),
            pa.field("publish_date", pa.string()),
            pa.field("cluster_id", pa.int32()),
        ]
    )
    import pyarrow as pa2
    records = []
    for _, row in df.iterrows():
        records.append({
            "chunk_id": str(row["chunk_id"]),
            "article_id": str(row["article_id"]),
            "vector": [float(v) for v in row["vector"]],
            "child_text": str(row["child_text"]),
            "domain": str(row["domain"]) if row["domain"] else "",
            "publish_date": str(row["publish_date"]) if row["publish_date"] else "",
            "cluster_id": int(row["cluster_id"]) if row["cluster_id"] is not None else -1,
        })
    db.create_table(TABLE_NAME, data=records, schema=schema)


def _normalise(rows: list[dict]) -> list[dict]:
    """Ensure all fields have correct Python types for Arrow ingestion."""
    out = []
    for r in rows:
        out.append(
            {
                "chunk_id": str(r.get("chunk_id", "")),
                "article_id": str(r.get("article_id", "")),
                "vector": [float(v) for v in r["vector"]],
                "child_text": str(r.get("child_text", "")),
                "domain": str(r.get("domain", "") or ""),
                "publish_date": str(r.get("publish_date", "") or ""),
                "cluster_id": int(r.get("cluster_id", -1)),
            }
        )
    return out
