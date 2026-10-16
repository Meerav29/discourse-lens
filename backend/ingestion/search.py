"""
Turn a topic into candidate pages: Claude writes search queries, a search
provider runs them, and results are deduplicated up to the article cap.

Providers (SEARCH_PROVIDER): "brave" (Brave Search API, needs BRAVE_API_KEY)
or "searxng" (a SearXNG instance with the JSON format enabled, at SEARXNG_URL;
self-hostable, no key).
"""

from __future__ import annotations

import html
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from backend.claude_client import complete
from backend.config import settings

log = logging.getLogger(__name__)

RESULTS_PER_QUERY = 20

_TAG = re.compile(r"<[^>]+>")


def plain(text: str | None) -> str:
    """Titles and snippets arrive as HTML (<strong> around matches, &#x27;)."""
    return " ".join(html.unescape(_TAG.sub("", text or "")).split())


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    query: str


def generate_queries(topic: str) -> list[str]:
    """Use Claude to generate 6 diverse search queries for the topic."""
    text = complete(
        f"Generate 6 diverse search queries to comprehensively cover the topic: '{topic}'.\n"
        "The queries should approach the topic from different angles: historical context, "
        "current debates, key figures, recent research, criticism, and applications.\n"
        "Return ONLY the queries, one per line, no numbering or extra text.",
        max_tokens=4096,
        effort="low",
    )
    queries = [q.strip() for q in text.split("\n") if q.strip()]
    return queries[:6]


def _get_with_retries(
    url: str, *, params: dict, headers: dict, max_retries: int = 3
) -> httpx.Response:
    """GET with exponential backoff on rate limiting (429), 5xx and network errors."""
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, headers=headers, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if attempt == max_retries or not (code == 429 or code >= 500):
                raise
        except httpx.TransportError:
            if attempt == max_retries:
                raise
        time.sleep(2**attempt)  # 1s, 2s, 4s
    raise AssertionError("unreachable")


def brave_search(query: str, count: int = RESULTS_PER_QUERY) -> list[SearchResult]:
    resp = _get_with_retries(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count, "text_decorations": "false"},
        headers={"Accept": "application/json", "X-Subscription-Token": settings.brave_api_key},
    )
    return [
        SearchResult(r["url"], plain(r.get("title")), plain(r.get("description")), query)
        for r in resp.json().get("web", {}).get("results", [])
        if "url" in r
    ][:count]


def searxng_search(query: str, count: int = RESULTS_PER_QUERY) -> list[SearchResult]:
    if not settings.searxng_url:
        raise RuntimeError("SEARCH_PROVIDER=searxng needs SEARXNG_URL (e.g. http://localhost:8888)")
    resp = _get_with_retries(
        f"{settings.searxng_url.rstrip('/')}/search",
        params={"q": query, "format": "json", "language": "en"},
        headers={"Accept": "application/json"},
    )
    return [
        SearchResult(r["url"], plain(r.get("title")), plain(r.get("content")), query)
        for r in resp.json().get("results", [])
        if "url" in r
    ][:count]


def web_search(query: str) -> list[SearchResult]:
    if settings.search_provider == "searxng":
        return searxng_search(query)
    return brave_search(query)


def search_all(
    queries: list[str],
    on_query: Callable[[int, int, str, int | None], None] | None = None,
) -> list[SearchResult]:
    """
    Run each query; deduplicate by URL (first query wins) up to the article cap.
    on_query(done, total, query, new_results) fires after each search;
    new_results is None when that search failed.
    """
    seen: set[str] = set()
    results: list[SearchResult] = []
    for i, query in enumerate(queries, start=1):
        new: int | None = 0
        try:
            for r in web_search(query):
                if r.url not in seen:
                    seen.add(r.url)
                    results.append(r)
                    new += 1
        except Exception:
            log.warning("Search failed for %r", query, exc_info=True)
            new = None  # failed query: skip, don't crash
        if on_query:
            on_query(i, len(queries), query, new)
    return results[: settings.max_articles]


def collect_results(
    topic: str,
    on_query: Callable[[int, int, str, int | None], None] | None = None,
) -> tuple[list[str], list[SearchResult]]:
    queries = generate_queries(topic)
    return queries, search_all(queries, on_query)


def collect_urls(
    topic: str,
    on_query: Callable[[int, int, str, int | None], None] | None = None,
) -> list[str]:
    """Generate queries, search each, return deduplicated URLs up to the article cap."""
    return [r.url for r in collect_results(topic, on_query)[1]]
