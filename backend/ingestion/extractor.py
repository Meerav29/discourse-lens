import hashlib
import time
from urllib.parse import urlparse

import trafilatura
from langdetect import LangDetectException, detect

MIN_WORDS = 200


class SkipArticle(Exception):
    """The page failed a quality filter; str(exc) is a human-readable reason."""


def article_id(analysis_id: str, url: str) -> str:
    """Stable per-analysis id, so the same URL can appear in several analyses."""
    return hashlib.sha256(f"{analysis_id}:{url}".encode()).hexdigest()[:16]


def extract_article(analysis_id: str, url: str, html: str) -> dict:
    """
    Extract clean article text from raw HTML using trafilatura.
    Raises SkipArticle if the page fails filtering:
      - no article text could be extracted
      - fewer than MIN_WORDS words
      - language is not English
    """
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
    )
    if not text:
        raise SkipArticle("no article text found")

    words = text.split()
    if len(words) < MIN_WORDS:
        raise SkipArticle(f"too short ({len(words)} words)")

    try:
        lang = detect(text[:2000])
    except LangDetectException:
        lang = "unknown"

    if lang != "en":
        raise SkipArticle(f"not English ({lang})")

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
