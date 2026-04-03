import os

import httpx
import anthropic
from dotenv import load_dotenv

load_dotenv()

_anthropic = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
_MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "120"))


def generate_queries(topic: str) -> list[str]:
    """Use Claude to generate 6 diverse search queries for the topic."""
    response = _anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Generate 6 diverse search queries to comprehensively cover the topic: '{topic}'.\n"
                "The queries should approach the topic from different angles: historical context, "
                "current debates, key figures, recent research, criticism, and applications.\n"
                "Return ONLY the queries, one per line, no numbering or extra text."
            ),
        }],
    )
    text = response.content[0].text.strip()
    queries = [q.strip() for q in text.split("\n") if q.strip()]
    return queries[:6]


def brave_search(query: str, count: int = 20) -> list[str]:
    """Call Brave Search API and return a list of result URLs."""
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": _BRAVE_API_KEY,
    }
    params = {"q": query, "count": count, "text_decorations": "false"}
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
    data = resp.json()
    results = data.get("web", {}).get("results", [])
    return [r["url"] for r in results if "url" in r]


def collect_urls(topic: str) -> list[str]:
    """Generate queries, search each, return deduplicated URLs up to MAX_ARTICLES cap."""
    queries = generate_queries(topic)
    seen: set[str] = set()
    urls: list[str] = []
    for query in queries:
        try:
            for url in brave_search(query):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        except Exception:
            continue  # failed query — skip, don't crash
    return urls[:_MAX_ARTICLES]
