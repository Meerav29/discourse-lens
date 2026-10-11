"""
The analysis pipeline: search → crawl → extract → chunk/dedup → embed → project.

Each run writes only rows tagged with its own analysis_id, so analyses are
independent and several can exist side by side.
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.db import connect, update_analysis

log = logging.getLogger(__name__)

LOW_YIELD_THRESHOLD = 30


async def run_pipeline(analysis_id: str, topic: str) -> None:
    from backend.embedding.project import run_projection
    from backend.ingestion.crawler import crawl_urls
    from backend.ingestion.search import collect_urls

    try:
        # Step 1: generate queries and search
        update_analysis(analysis_id, status="crawling", progress=5)
        urls = await asyncio.to_thread(collect_urls, topic)

        # Step 2: Playwright scrape — runs in a thread with its own event loop
        update_analysis(analysis_id, progress=20)
        crawled = await asyncio.to_thread(crawl_urls, urls)

        # Step 3: extract clean text, filter, persist
        update_analysis(analysis_id, status="processing", progress=60)
        ok_articles = await asyncio.to_thread(_extract_and_store, analysis_id, crawled)

        # Step 4: chunk + dedup across the whole corpus
        update_analysis(analysis_id, progress=75)
        await asyncio.to_thread(_chunk_and_store, analysis_id, ok_articles)

        # Step 5: embed non-duplicate child chunks
        update_analysis(analysis_id, status="embedding", progress=80)
        await asyncio.to_thread(_embed_and_store, analysis_id)

        # Step 6: UMAP + clustering + labels → projections
        update_analysis(analysis_id, status="projecting", progress=90)
        await asyncio.to_thread(run_projection, analysis_id)

        ok_count = len(ok_articles)
        warning = None
        if ok_count < LOW_YIELD_THRESHOLD:
            warning = (
                f"Only {ok_count} articles were successfully indexed. "
                "Results may be sparse — try a broader or more general topic."
            )
        update_analysis(
            analysis_id, status="done", progress=100, article_count=ok_count, warning=warning
        )
    except Exception as e:
        log.exception("Pipeline failed for analysis %s", analysis_id)
        update_analysis(analysis_id, status="error", error_msg=str(e))


def _extract_and_store(analysis_id: str, crawled: list[dict]) -> list[dict]:
    from backend.ingestion.extractor import article_id, extract_article
    from backend.processing.metadata import extract_publish_date

    ok_articles: list[dict] = []
    conn = connect()
    try:
        for item in crawled:
            url, html = item["url"], item["html"]
            try:
                article = extract_article(analysis_id, url, html)
                if article is None:
                    conn.execute(
                        "INSERT OR IGNORE INTO articles (id, analysis_id, url, status, crawl_ts) "
                        "VALUES (?,?,?,?,?)",
                        (article_id(analysis_id, url), analysis_id, url, "filtered",
                         int(time.time())),
                    )
                    continue

                conn.execute(
                    "INSERT OR IGNORE INTO articles "
                    "(id, analysis_id, url, domain, title, publish_date, crawl_ts, "
                    " word_count, language, raw_text, status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        article["id"], analysis_id, article["url"], article["domain"],
                        article["title"], extract_publish_date(html, url), article["crawl_ts"],
                        article["word_count"], article["language"], article["raw_text"], "ok",
                    ),
                )
                ok_articles.append({"id": article["id"], "raw_text": article["raw_text"]})
            except Exception:
                log.warning("Extraction failed for %s", url, exc_info=True)
        conn.commit()
    finally:
        conn.close()
    return ok_articles


def _chunk_and_store(analysis_id: str, articles: list[dict]) -> None:
    from backend.processing.dedup import chunk_and_dedup

    chunks = [{**c, "analysis_id": analysis_id} for c in chunk_and_dedup(articles)]
    conn = connect()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO chunks "
            "(id, analysis_id, article_id, parent_id, parent_text, child_text, "
            " chunk_index, token_count, is_duplicate) "
            "VALUES (:id, :analysis_id, :article_id, :parent_id, :parent_text, :child_text, "
            " :chunk_index, :token_count, :is_duplicate)",
            chunks,
        )
        conn.commit()
    finally:
        conn.close()


def _embed_and_store(analysis_id: str) -> None:
    from backend.embedding.embed import embed_chunks
    from backend.embedding.store import write_embeddings

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT c.id, c.child_text, c.article_id, a.domain, a.publish_date "
            "FROM chunks c JOIN articles a ON a.id = c.article_id "
            "WHERE c.analysis_id = ? AND c.is_duplicate = 0",
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return

    chunks = [
        {
            "id": r["id"],
            "child_text": r["child_text"],
            "article_id": r["article_id"],
            "domain": r["domain"] or "",
            "publish_date": r["publish_date"] or "",
        }
        for r in rows
    ]
    embeddings = embed_chunks(chunks, kind="document")
    meta_by_id = {c["id"]: c for c in chunks}
    write_embeddings(
        analysis_id,
        [{**meta_by_id[e["chunk_id"]], "chunk_id": e["chunk_id"], "vector": e["vector"]}
         for e in embeddings],
    )
