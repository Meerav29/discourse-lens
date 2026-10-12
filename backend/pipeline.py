"""
The analysis pipeline: search → crawl → extract → chunk/dedup → embed → project.

Each run writes only rows tagged with its own analysis_id, so analyses are
independent and several can exist side by side.

Runs are cancellable. Work happens in worker threads, which can't be killed,
so cancellation is cooperative: each stage checks the run's cancel flag
between units of work (a search query, a page, an article, an embedding
batch, a cluster label) and stops there. A cancelled run's partial data is
deleted; the analysis row stays, with status 'cancelled'.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from backend.db import add_event, connect, update_analysis

log = logging.getLogger(__name__)

LOW_YIELD_THRESHOLD = 30

# Progress bands (percent) for each stage.
SEARCH = (0, 10)
CRAWL = (10, 55)
EXTRACT = (55, 65)
CHUNK = (65, 68)
EMBED = (68, 88)
PROJECT = (88, 99)

_PROGRESS_WRITE_INTERVAL = 0.5  # seconds between throttled progress writes


class Cancelled(BaseException):  # noqa: N818 — mirrors asyncio.CancelledError
    """
    Raised inside a stage when the run is cancelled. A BaseException, like
    asyncio.CancelledError, so the stages' `except Exception` handlers (which
    skip a single bad page or query) don't swallow it.
    """


class RunContext:
    """Progress reporting, event logging and the cancel flag for one run."""

    def __init__(self, analysis_id: str):
        self.analysis_id = analysis_id
        self._cancel = threading.Event()
        self._last_write = 0.0

    # -- cancellation --
    def cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    # -- reporting --
    def stage(self, status: str, band: tuple[int, int], detail: str) -> None:
        self.check()
        update_analysis(self.analysis_id, status=status, progress=band[0], stage_detail=detail)
        self.event("stage", detail)

    def progress(self, band: tuple[int, int], fraction: float, detail: str) -> None:
        """Map fraction (0-1) of a stage onto its band; writes are throttled."""
        now = time.monotonic()
        if fraction < 1 and now - self._last_write < _PROGRESS_WRITE_INTERVAL:
            return
        self._last_write = now
        lo, hi = band
        pct = lo + (hi - lo) * min(max(fraction, 0.0), 1.0)
        update_analysis(self.analysis_id, progress=int(pct), stage_detail=detail)

    def event(self, kind: str, message: str, url: str | None = None) -> None:
        add_event(self.analysis_id, kind, message, url)


# ---------------------------------------------------------------------------
# Registry of running analyses (this process only)
# ---------------------------------------------------------------------------

_runs: dict[str, tuple[asyncio.Task, RunContext]] = {}


def start(analysis_id: str, topic: str) -> None:
    """Start a run on the current event loop."""
    ctx = RunContext(analysis_id)
    task = asyncio.get_running_loop().create_task(run_pipeline(ctx, topic))
    _runs[analysis_id] = (task, ctx)
    task.add_done_callback(lambda _t: _runs.pop(analysis_id, None))


def cancel(analysis_id: str) -> bool:
    """Ask a running analysis to stop. Returns False if it isn't running here."""
    entry = _runs.get(analysis_id)
    if entry is None:
        return False
    entry[1].cancel()
    return True


def cancel_all() -> None:
    for _task, ctx in list(_runs.values()):
        ctx.cancel()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(ctx: RunContext, topic: str) -> None:
    analysis_id = ctx.analysis_id
    try:
        urls = await asyncio.to_thread(_search, ctx, topic)
        crawled = await asyncio.to_thread(_crawl, ctx, urls)
        ok_articles = await asyncio.to_thread(_extract_and_store, ctx, crawled)
        await asyncio.to_thread(_chunk_and_store, ctx, ok_articles)
        await asyncio.to_thread(_embed_and_store, ctx)
        await asyncio.to_thread(_project, ctx)

        ok_count = len(ok_articles)
        warning = None
        if ok_count < LOW_YIELD_THRESHOLD:
            warning = (
                f"Only {ok_count} articles were successfully indexed. "
                "Results may be sparse — try a broader or more general topic."
            )
            ctx.event("warning", warning)
        update_analysis(
            analysis_id, status="done", progress=100, article_count=ok_count,
            warning=warning, stage_detail=f"Indexed {ok_count} articles",
        )
        ctx.event("stage", "Done")
    except Cancelled:
        await asyncio.to_thread(_discard_partial_data, analysis_id)
        update_analysis(analysis_id, status="cancelled", stage_detail="Cancelled")
        ctx.event("stage", "Cancelled")
    except Exception as e:
        log.exception("Pipeline failed for analysis %s", analysis_id)
        update_analysis(analysis_id, status="error", error_msg=str(e))
        ctx.event("error", str(e))


def _search(ctx: RunContext, topic: str) -> list[str]:
    from backend.ingestion.search import collect_urls

    ctx.stage("crawling", SEARCH, "Generating search queries")

    def on_query(done: int, total: int, query: str, new_urls: int | None) -> None:
        if new_urls is None:
            ctx.event("warning", f"Search failed: {query}")
        else:
            ctx.event("query", f"{query} ({new_urls} new results)")
        ctx.progress(SEARCH, done / total, f"Searched {done} of {total} queries")
        ctx.check()

    urls = collect_urls(topic, on_query=on_query)
    if not urls:
        raise RuntimeError("Search returned no results — check BRAVE_API_KEY or try another topic.")
    return urls


def _crawl(ctx: RunContext, urls: list[str]) -> list[dict]:
    from backend.ingestion.crawler import crawl_urls

    ctx.stage("crawling", CRAWL, f"Crawling {len(urls)} pages")
    done = 0
    lock = threading.Lock()

    # Called from the crawler's own event loop: must not raise.
    def on_page(url: str, ok: bool) -> None:
        nonlocal done
        with lock:
            done += 1
            n = done
        if not ok:
            ctx.event("skip", "Could not load page", url)
        ctx.progress(CRAWL, n / len(urls), f"Crawled {n} of {len(urls)} pages")

    crawled = crawl_urls(urls, on_page=on_page, should_stop=ctx.cancelled)
    ctx.check()
    return crawled


def _extract_and_store(ctx: RunContext, crawled: list[dict]) -> list[dict]:
    from backend.ingestion.extractor import SkipArticle, article_id, extract_article
    from backend.processing.metadata import extract_publish_date

    analysis_id = ctx.analysis_id
    ctx.stage("processing", EXTRACT, f"Extracting text from {len(crawled)} pages")
    ok_articles: list[dict] = []
    conn = connect()
    try:
        for i, item in enumerate(crawled, start=1):
            ctx.check()
            url, html = item["url"], item["html"]
            try:
                article = extract_article(analysis_id, url, html)
            except SkipArticle as skip:
                conn.execute(
                    "INSERT OR IGNORE INTO articles (id, analysis_id, url, status, crawl_ts) "
                    "VALUES (?,?,?,?,?)",
                    (article_id(analysis_id, url), analysis_id, url, "filtered",
                     int(time.time())),
                )
                # Commit before reporting: events and progress are written on
                # their own connections and would wait on this transaction.
                conn.commit()
                ctx.event("skip", str(skip).capitalize(), url)
                continue
            except Exception:
                log.warning("Extraction failed for %s", url, exc_info=True)
                ctx.event("skip", "Extraction failed", url)
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
            conn.commit()
            ok_articles.append({
                "id": article["id"], "url": url, "raw_text": article["raw_text"],
                "title": article["title"] or article["domain"],
            })
            ctx.event("article", article["title"] or article["domain"], url)
            ctx.progress(EXTRACT, i / len(crawled), f"Extracted {i} of {len(crawled)} pages")
    finally:
        conn.close()
    if not ok_articles:
        raise RuntimeError("No pages passed the quality filters — try a broader topic.")
    return _drop_duplicate_articles(ctx, ok_articles)


def _drop_duplicate_articles(ctx: RunContext, articles: list[dict]) -> list[dict]:
    """Mark near-copies of an earlier article (e.g. syndicated stories) and drop them."""
    from backend.processing.dedup import find_duplicate_articles

    duplicates = find_duplicate_articles(articles)
    if not duplicates:
        return articles
    by_id = {a["id"]: a for a in articles}
    conn = connect()
    try:
        conn.executemany(
            "UPDATE articles SET status = 'duplicate' WHERE id = ?", [(d,) for d in duplicates]
        )
        conn.commit()
    finally:
        conn.close()
    for dup, original in duplicates.items():
        ctx.event("skip", f"Near-copy of “{by_id[original]['title']}”", by_id[dup]["url"])
    return [a for a in articles if a["id"] not in duplicates]


def _chunk_and_store(ctx: RunContext, articles: list[dict]) -> None:
    from backend.processing.dedup import chunk_and_dedup

    ctx.stage("processing", CHUNK, f"Chunking and deduplicating {len(articles)} articles")
    chunks = [{**c, "analysis_id": ctx.analysis_id} for c in chunk_and_dedup(articles)]
    dupes = sum(c["is_duplicate"] for c in chunks)
    if dupes:
        ctx.event("stage", f"Removed {dupes} near-duplicate chunks")
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


def _embed_and_store(ctx: RunContext) -> None:
    from backend.embedding.embed import embed_chunks
    from backend.embedding.store import write_embeddings

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT c.id, c.child_text, c.article_id, a.domain, a.publish_date "
            "FROM chunks c JOIN articles a ON a.id = c.article_id "
            "WHERE c.analysis_id = ? AND c.is_duplicate = 0",
            (ctx.analysis_id,),
        ).fetchall()
    finally:
        conn.close()

    ctx.stage("embedding", EMBED, f"Embedding {len(rows)} chunks")
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

    def on_batch(done: int, total: int) -> None:
        ctx.progress(EMBED, done / total, f"Embedded {done} of {total} chunks")
        ctx.check()

    embeddings = embed_chunks(chunks, kind="document", on_batch=on_batch)
    meta_by_id = {c["id"]: c for c in chunks}
    write_embeddings(
        ctx.analysis_id,
        [{**meta_by_id[e["chunk_id"]], "chunk_id": e["chunk_id"], "vector": e["vector"]}
         for e in embeddings],
    )


def _project(ctx: RunContext) -> None:
    from backend.embedding.project import run_projection

    ctx.stage("projecting", PROJECT, "Mapping and clustering")

    def on_step(fraction: float, detail: str) -> None:
        ctx.check()
        ctx.progress(PROJECT, fraction, detail)

    def on_label(label: str, n_articles: int) -> None:
        ctx.event("cluster", f"{label} ({n_articles} articles)")

    run_projection(ctx.analysis_id, on_step=on_step, on_label=on_label)


def _discard_partial_data(analysis_id: str) -> None:
    from backend.embedding.store import drop_embeddings

    conn = connect()
    try:
        for table in ("placements", "clusters", "chunks", "articles"):
            conn.execute(f"DELETE FROM {table} WHERE analysis_id = ?", (analysis_id,))
        conn.commit()
    finally:
        conn.close()
    drop_embeddings(analysis_id)
