"""
RAG retrieval pipeline.

Steps:
1. Embed the user query using the same embedding mode as the corpus.
2. Search LanceDB for top-k most similar child chunks.
3. Fetch parent_text + article metadata from SQLite.
4. Deduplicate by article (max one excerpt per article).
5. Assemble context string and call Claude.
6. Return {"answer": str, "citations": [{"url", "title", "domain"}]}.

Errors propagate to the caller; an analysis with no vectors raises NoCorpusError.
"""

from __future__ import annotations

from backend.config import settings
from backend.db import connect
from backend.embedding.embed import embed_chunks
from backend.embedding.store import open_table


class NoCorpusError(LookupError):
    """The analysis has no indexed vectors to search."""


def order_and_dedupe_by_article(rows: list[dict], ranked_chunk_ids: list[str]) -> list[dict]:
    """
    Put SQLite rows (which come back in arbitrary order) into vector-search rank
    order, then keep only the highest-ranked chunk per article.
    """
    rank = {cid: i for i, cid in enumerate(ranked_chunk_ids)}
    ordered = sorted(rows, key=lambda r: rank.get(r["chunk_id"], len(rank)))
    seen_articles: set[str] = set()
    deduped = []
    for row in ordered:
        if row["article_id"] not in seen_articles:
            seen_articles.add(row["article_id"])
            deduped.append(row)
    return deduped


def query_corpus(analysis_id: str, query: str, top_k: int | None = None) -> dict:
    _top_k = top_k or settings.rag_top_k

    table = open_table(analysis_id)
    if table is None:
        raise NoCorpusError("This analysis has no indexed corpus yet.")

    # --- 1. Embed the query ---
    query_vector = embed_chunks([{"id": "query", "child_text": query}], kind="query")[0]["vector"]

    # --- 2. Search LanceDB ---
    results_df = table.search(query_vector).limit(_top_k).to_pandas()
    if results_df.empty:
        raise NoCorpusError("This analysis has no indexed corpus yet.")

    chunk_ids = results_df["chunk_id"].tolist()

    # --- 3. Fetch parent_text + article metadata from SQLite ---
    conn = connect()
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

    # --- 4. Deduplicate by article, keeping each article's best-ranked chunk ---
    deduped = order_and_dedupe_by_article([dict(r) for r in rows], chunk_ids)

    if not deduped:
        return {"answer": "Could not retrieve context from the corpus.", "citations": []}

    # --- 5. Assemble context and call Claude ---
    from backend.claude_client import complete
    from backend.synthesis.prompts import CONTEXT_ITEM_TEMPLATE, RAG_USER_TEMPLATE, SYSTEM_PROMPT

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

    answer = complete(user_message, system=SYSTEM_PROMPT, max_tokens=16000, effort="medium")

    # --- 6. Build citations list ---
    citations = [
        {"url": r["url"], "title": r["title"] or "Untitled", "domain": r["domain"] or ""}
        for r in deduped
        if r.get("url")
    ]

    return {"answer": answer, "citations": citations}
