"""
RAG retrieval pipeline.

Steps:
1. Embed the user query using the same embedding mode as the corpus.
2. Search LanceDB for top-k most similar child chunks.
3. Fetch parent_text + article metadata from SQLite.
4. Deduplicate by article (max one excerpt per article).
5. Assemble context string and call Claude.
6. Return {"answer": str, "citations": [{"url", "title", "domain"}]}.
"""

from __future__ import annotations

import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "./data/discourse.db")
LANCE_PATH = os.getenv("LANCE_PATH", "./data/vectors")
TABLE_NAME = "embeddings"


def query_corpus(query: str, db_path: str | None = None, top_k: int | None = None) -> dict:
    _db_path = db_path or DB_PATH
    _top_k = top_k or int(os.getenv("RAG_TOP_K", "15"))

    # --- 1. Embed the query ---
    try:
        from backend.embedding.embed import embed_chunks
        embedded = embed_chunks([{"id": "query", "child_text": query}])
        query_vector = embedded[0]["vector"]
    except Exception as e:
        return {"answer": f"Embedding error: {e}", "citations": []}

    # --- 2. Search LanceDB ---
    try:
        import lancedb
        db = lancedb.connect(LANCE_PATH)
        if TABLE_NAME not in db.table_names():
            return {"answer": "No corpus indexed yet. Please run an analysis first.", "citations": []}
        table = db.open_table(TABLE_NAME)
        results_df = table.search(query_vector).limit(_top_k).to_pandas()
    except Exception as e:
        return {"answer": f"Vector search error: {e}", "citations": []}

    if results_df.empty:
        return {"answer": "No corpus indexed yet. Please run an analysis first.", "citations": []}

    chunk_ids = results_df["chunk_id"].tolist()

    # --- 3. Fetch parent_text + article metadata from SQLite ---
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id, c.parent_text, c.article_id,
                   a.url, a.title, a.domain, a.publish_date
            FROM chunks c
            JOIN articles a ON a.id = c.article_id
            WHERE c.id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()
    finally:
        conn.close()

    # --- 4. Deduplicate by article (keep first occurrence per article_id) ---
    seen_articles: set[str] = set()
    deduped = []
    for row in rows:
        if row["article_id"] not in seen_articles:
            seen_articles.add(row["article_id"])
            deduped.append(dict(row))

    if not deduped:
        return {"answer": "Could not retrieve context from the corpus.", "citations": []}

    # --- 5. Assemble context and call Claude ---
    from backend.synthesis.prompts import (
        SYSTEM_PROMPT, RAG_USER_TEMPLATE, CONTEXT_ITEM_TEMPLATE
    )
    from backend.claude_client import get_client, get_model

    context_parts = []
    for i, row in enumerate(deduped, start=1):
        text = (row.get("parent_text") or "")[:3000]
        context_parts.append(
            CONTEXT_ITEM_TEMPLATE.format(
                index=i,
                title=row.get("title") or "Untitled",
                domain=row.get("domain") or "",
                publish_date=row.get("publish_date") or "unknown date",
                url=row.get("url") or "",
                text=text,
            )
        )
    context_str = "\n\n".join(context_parts)

    user_message = RAG_USER_TEMPLATE.format(context=context_str, query=query)

    response = get_client().messages.create(
        model=get_model(),
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = response.content[0].text.strip()

    # --- 6. Build citations list ---
    citations = [
        {"url": r["url"], "title": r["title"] or "Untitled", "domain": r["domain"] or ""}
        for r in deduped
        if r.get("url")
    ]

    return {"answer": answer, "citations": citations}
