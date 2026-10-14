import httpx
import pytest

from backend.config import settings
from backend.ingestion import search


def _fake_get(payload, seen):
    def get(url, *, params, headers, max_retries=3):
        seen.append((url, params))
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))
    return get


def test_searxng_results_parsed(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "search_provider", "searxng")
    monkeypatch.setattr(settings, "searxng_url", "http://localhost:8888/")
    monkeypatch.setattr(search, "_get_with_retries", _fake_get(
        {"results": [{"url": "https://a.test", "title": "A", "content": "about A"}, {"title": "no url"}]},
        seen,
    ))
    results = search.web_search("cool roofs")
    assert results == [search.SearchResult("https://a.test", "A", "about A", "cool roofs")]
    assert seen == [("http://localhost:8888/search",
                     {"q": "cool roofs", "format": "json", "language": "en"})]


def test_searxng_needs_a_url(monkeypatch):
    monkeypatch.setattr(settings, "search_provider", "searxng")
    monkeypatch.setattr(settings, "searxng_url", "")
    with pytest.raises(RuntimeError, match="SEARXNG_URL"):
        search.web_search("x")


def test_brave_is_the_default(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "search_provider", "brave")
    monkeypatch.setattr(search, "_get_with_retries", _fake_get(
        {"web": {"results": [{"url": "https://b.test", "title": "B", "description": "about B"}]}}, seen,
    ))
    assert [r.url for r in search.web_search("q")] == ["https://b.test"]
    assert "brave.com" in seen[0][0]


def test_search_all_dedupes_and_survives_failed_queries(monkeypatch):
    def fake(query):
        if query == "broken":
            raise httpx.ConnectError("down")
        return [search.SearchResult(u, "", "", query) for u in ("https://x.test/1", "https://x.test/2")]

    monkeypatch.setattr(search, "web_search", fake)
    progress = []
    results = search.search_all(["one", "broken", "two"],
                                on_query=lambda d, t, q, n: progress.append((q, n)))
    assert [r.url for r in results] == ["https://x.test/1", "https://x.test/2"]
    assert [r.query for r in results] == ["one", "one"]
    assert progress == [("one", 2), ("broken", None), ("two", 0)]
