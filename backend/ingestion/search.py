import logging
import time
from collections.abc import Callable

import httpx

from backend.claude_client import complete
from backend.config import settings

log = logging.getLogger(__name__)


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


def brave_search(query: str, count: int = 20, max_retries: int = 3) -> list[str]:
    """Call Brave Search API and return a list of result URLs.

    Retries with exponential backoff on rate limiting (429) and transient
    server/network errors; other 4xx errors fail immediately.
    """
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.brave_api_key,
    }
    params = {"q": query, "count": count, "text_decorations": "false"}

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params=params,
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("web", {}).get("results", [])
            return [r["url"] for r in results if "url" in r]
        except (httpx.HTTPStatusError, httpx.TransportError):
            if attempt == max_retries:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return []


def collect_urls(
    topic: str,
    on_query: Callable[[int, int, str, int | None], None] | None = None,
) -> list[str]:
    """
    Generate queries, search each, return deduplicated URLs up to the article cap.

    on_query(done, total, query, new_urls) is called after each search;
    new_urls is None when that search failed.
    """
    queries = generate_queries(topic)
    seen: set[str] = set()
    urls: list[str] = []
    for i, query in enumerate(queries, start=1):
        new: int | None = 0
        try:
            for url in brave_search(query):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                    new += 1
        except Exception:
            log.warning("Search failed for %r", query, exc_info=True)
            new = None  # failed query — skip, don't crash
        if on_query:
            on_query(i, len(queries), query, new)
    return urls[:settings.max_articles]
