"""
Pipeline orchestration with the network-bound stages stubbed out: search,
crawl, extraction, embeddings and projection are fakes; chunking, dedup,
SQLite and LanceDB are real.
"""

import asyncio
import time

import pytest
from conftest import add_analysis

from backend import pipeline
from backend.db import connect
from backend.embedding import store
from backend.ingestion.extractor import SkipArticle

WORDS = "rebound effects mean efficiency gains can raise total energy demand over time "


@pytest.fixture
def fakes(isolated, monkeypatch):
    """Stub every external stage; tests override individual pieces."""
    state = {"embed_hook": None, "crawl_hook": None}

    def collect_urls(topic, on_query=None):
        if on_query:
            on_query(1, 2, "query one", 3)
            on_query(2, 2, "query two", None)
        return ["https://a.test/1", "https://a.test/2", "https://a.test/short"]

    def crawl_urls(urls, on_page=None, should_stop=None):
        if state["crawl_hook"]:
            state["crawl_hook"](should_stop)
        out = []
        for u in urls:
            if should_stop and should_stop():
                break
            if on_page:
                on_page(u, True)
            out.append({"url": u, "html": "<html></html>"})
        return out

    def extract_article(analysis_id, url, html):
        if url.endswith("short"):
            raise SkipArticle("too short (12 words)")
        n = url.rsplit("/", 1)[1]
        return {
            "id": f"{analysis_id[:4]}-{n}", "url": url, "domain": "a.test",
            "title": f"Article {n}", "raw_text": (WORDS + n + " ") * 60,
            "word_count": 840, "language": "en", "crawl_ts": 0, "status": "ok",
        }

    def embed_chunks(chunks, kind="document", on_batch=None):
        if state["embed_hook"]:
            state["embed_hook"]()
        if on_batch:
            on_batch(len(chunks), len(chunks))
        return [{"chunk_id": c["id"], "vector": [float(i % 7), 1.0, 0.5]}
                for i, c in enumerate(chunks)]

    def run_projection(analysis_id, on_step=None, on_label=None):
        on_step(0.0, "Projecting")
        conn = connect()
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM chunks WHERE analysis_id=? AND is_duplicate=0", (analysis_id,))]
        conn.executemany(
            "INSERT INTO projections (chunk_id, analysis_id, x, y, cluster_id, cluster_label, "
            "distance_from_centroid) VALUES (?,?,0,0,0,'Rebound',1)",
            [(i, analysis_id) for i in ids],
        )
        conn.commit()
        conn.close()
        on_label("Rebound", len(ids))

    monkeypatch.setattr("backend.ingestion.search.collect_urls", collect_urls)
    monkeypatch.setattr("backend.ingestion.crawler.crawl_urls", crawl_urls)
    monkeypatch.setattr("backend.ingestion.extractor.extract_article", extract_article)
    monkeypatch.setattr("backend.embedding.embed.embed_chunks", embed_chunks)
    monkeypatch.setattr("backend.embedding.project.run_projection", run_projection)
    return state


def _analysis(aid):
    conn = connect()
    row = dict(conn.execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone())
    conn.close()
    return row


def _events(aid):
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT kind, message, url FROM analysis_events WHERE analysis_id=? ORDER BY id", (aid,))]
    conn.close()
    return rows


def _count(table, aid):
    conn = connect()
    n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE analysis_id=?", (aid,)).fetchone()[0]
    conn.close()
    return n


def _run(aid, topic="jevons"):
    asyncio.run(pipeline.run_pipeline(pipeline.RunContext(aid), topic))


def test_happy_path_records_progress_and_events(fakes):
    add_analysis("an1", status="queued")
    _run("an1")

    a = _analysis("an1")
    assert (a["status"], a["progress"], a["article_count"]) == ("done", 100, 2)
    assert a["warning"].startswith("Only 2 articles")
    assert a["stage_detail"] == "Indexed 2 articles"

    events = _events("an1")
    kinds = {e["kind"] for e in events}
    assert {"stage", "query", "article", "skip", "cluster", "warning"} <= kinds
    assert {"kind": "skip", "message": "Too short (12 words)",
            "url": "https://a.test/short"} in events
    assert any(e["kind"] == "warning" and "query two" in e["message"] for e in events)
    assert store.open_table("an1") is not None


def test_cancel_during_crawl_discards_data(fakes):
    add_analysis("an1", status="queued")

    def wait_for_cancel(should_stop):
        deadline = time.monotonic() + 5
        while not should_stop() and time.monotonic() < deadline:
            time.sleep(0.01)

    fakes["crawl_hook"] = wait_for_cancel

    async def scenario():
        pipeline.start("an1", "jevons")
        task, _ctx = pipeline._runs["an1"]
        while _analysis("an1")["stage_detail"] != "Crawling 3 pages":
            await asyncio.sleep(0.01)
        assert pipeline.cancel("an1") is True
        await task

    asyncio.run(scenario())
    a = _analysis("an1")
    assert a["status"] == "cancelled"
    assert _events("an1")[-1]["message"] == "Cancelled"
    assert _count("articles", "an1") == 0
    assert "an1" not in pipeline._runs


def test_cancel_inside_worker_thread_propagates(fakes):
    """Cancelled is raised in a to_thread worker (via on_batch) and must still land."""
    add_analysis("an1", status="queued")
    ctx = pipeline.RunContext("an1")
    fakes["embed_hook"] = ctx.cancel

    asyncio.run(pipeline.run_pipeline(ctx, "jevons"))

    assert _analysis("an1")["status"] == "cancelled"
    for table in ("articles", "chunks", "projections"):
        assert _count(table, "an1") == 0, table
    assert store.open_table("an1") is None


def test_no_search_results_is_an_error(fakes, monkeypatch):
    monkeypatch.setattr("backend.ingestion.search.collect_urls", lambda topic, on_query=None: [])
    add_analysis("an1", status="queued")
    _run("an1")
    a = _analysis("an1")
    assert a["status"] == "error"
    assert "no results" in a["error_msg"]
    assert _events("an1")[-1]["kind"] == "error"


def test_everything_filtered_is_an_error(fakes, monkeypatch):
    def skip_all(analysis_id, url, html):
        raise SkipArticle("not English (de)")

    monkeypatch.setattr("backend.ingestion.extractor.extract_article", skip_all)
    add_analysis("an1", status="queued")
    _run("an1")
    assert "quality filters" in _analysis("an1")["error_msg"]


def test_progress_maps_into_band_and_throttles(isolated):
    add_analysis("an1", status="crawling")
    ctx = pipeline.RunContext("an1")
    ctx.progress((10, 50), 0.5, "half")
    assert _analysis("an1")["progress"] == 30
    ctx.progress((10, 50), 0.6, "throttled")  # within the write interval
    assert _analysis("an1")["stage_detail"] == "half"
    ctx.progress((10, 50), 1.0, "finished")  # completion always writes
    assert (_analysis("an1")["progress"], _analysis("an1")["stage_detail"]) == (50, "finished")


def test_cancel_unknown_run_returns_false():
    assert pipeline.cancel("not-running") is False
