import hashlib
import time
from urllib.parse import urlparse

import trafilatura
from langdetect import LangDetectException, detect


def article_id(analysis_id: str, url: str) -> str:
    """Stable per-analysis id, so the same URL can appear in several analyses."""
    return hashlib.sha256(f"{analysis_id}:{url}".encode()).hexdigest()[:16]


def extract_article(analysis_id: str, url: str, html: str) -> dict | None:
    """
    Extract clean article text from raw HTML using trafilatura.
    Returns an article dict, or None if the article fails filtering:
      - extraction failed
      - word count < 200
      - language is not English
    """
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
    )
    if not text:
        return None

    words = text.split()
    if len(words) < 200:
        return None

    try:
        lang = detect(text[:2000])
    except LangDetectException:
        lang = "unknown"

    if lang != "en":
        return None

    meta = trafilatura.extract_metadata(html, default_url=url)
    title = meta.title if meta and meta.title else None
    domain = urlparse(url).netloc

    return {
        "id": article_id(analysis_id, url),
        "url": url,
        "domain": domain,
        "title": title,
        "raw_text": text,
        "word_count": len(words),
        "language": lang,
        "crawl_ts": int(time.time()),
        "status": "ok",
    }
