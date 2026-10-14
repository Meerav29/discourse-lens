"""The optional review step: pause after search, edit queries, approve pages."""

import asyncio

import pytest
from conftest import add_analysis
from fastapi.testclient import TestClient

from backend import pipeline
from backend.api import main
from backend.db import connect
from backend.ingestion.search import SearchResult


def _results(*urls, query="q1"):
    return [SearchResult(u, f"Title of {u}", "snippet", query) for u in urls]


def _status(aid):
    conn = connect()
    row = conn.execute("SELECT status, stage_detail FROM analyses WHERE id=?", (aid,)).fetchone()
    conn.close()
    return dict(row)


@pytest.fixture
def paused(isolated, monkeypatch):
    """A real pipeline run (search stubbed) that pauses for review, plus a client."""
    monkeypatch.setattr(
        "backend.ingestion.search.collect_results",
        lambda topic, on_query=None: (["q1"], _results("https://a.test/1", "https://a.test/2")),
    )
    crawled_with = []

    def fake_crawl(ctx, urls):
        crawled_with.append(urls)
        ctx.check()
        raise RuntimeError("stop after crawl")  # the rest of the pipeline is tested elsewhere

    monkeypatch.setattr(pipeline, "_crawl", fake_crawl)
    add_analysis("an1", status="queued")
    return crawled_with


def _run_with(client_actions):
    """Start the pipeline in the test client's loop; run actions while it waits."""
    with TestClient(main.app) as client:
        loop_runner = client.portal

        async def start():
            pipeline.start("an1", "topic", review=True)

        loop_runner.call(start)
        task = pipeline._runs["an1"][0]
        for _ in range(200):
            if _status("an1")["status"] == "reviewing":
                break
            loop_runner.call(asyncio.sleep, 0.02)
        client_actions(client)

        async def finish():
            await asyncio.wait_for(task, 5)

        loop_runner.call(finish)


def test_pauses_with_plan_then_crawls_only_approved_pages(paused):
    def actions(client):
        assert _status("an1") == {"status": "reviewing",
                                  "stage_detail": "Waiting for you to review 2 pages"}
        plan = client.get("/api/analyses/an1/plan").json()
        assert plan["queries"] == ["q1"]
        assert [r["url"] for r in plan["results"]] == ["https://a.test/1", "https://a.test/2"]

        r = client.post("/api/analyses/an1/plan/approve",
                        json={"urls": ["https://a.test/2", "https://mine.test/added", "https://a.test/2"]})
        assert r.status_code == 202

    _run_with(actions)
    assert paused == [["https://a.test/2", "https://mine.test/added"]]


def test_search_again_replaces_the_plan(paused, monkeypatch):
    monkeypatch.setattr("backend.ingestion.search.search_all",
                        lambda queries, on_query=None: _results("https://b.test/1", query=queries[0]))

    def actions(client):
        plan = client.post("/api/analyses/an1/plan/search", json={"queries": ["  better query  "]}).json()
        assert plan["queries"] == ["better query"]
        assert [r["url"] for r in plan["results"]] == ["https://b.test/1"]
        assert client.get("/api/analyses/an1/plan").json() == plan
        client.post("/api/analyses/an1/plan/approve", json={"urls": ["https://b.test/1"]})

    _run_with(actions)


def test_invalid_urls_are_rejected(paused):
    def actions(client):
        r = client.post("/api/analyses/an1/plan/approve", json={"urls": ["javascript:alert(1)"]})
        assert r.status_code == 422
        assert "Not a web address" in r.json()["detail"]
        client.post("/api/analyses/an1/plan/approve", json={"urls": ["https://a.test/1"]})

    _run_with(actions)


def test_cancel_while_paused(paused):
    def actions(client):
        assert client.post("/api/analyses/an1/cancel").status_code == 202

    _run_with(actions)
    assert _status("an1")["status"] == "cancelled"
    assert paused == []  # never crawled


def test_review_endpoints_need_a_paused_analysis(isolated):
    add_analysis("done1", status="done")
    with TestClient(main.app) as client:
        assert client.post("/api/analyses/done1/plan/approve",
                           json={"urls": ["https://a.test"]}).status_code == 409
        assert client.post("/api/analyses/done1/plan/search",
                           json={"queries": ["x"]}).status_code == 409
        assert client.get("/api/analyses/done1/plan").status_code == 404
