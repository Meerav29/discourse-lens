import hashlib
import time
from urllib.parse import urlparse

import trafilatura
from langdetect import detect, LangDetectException


def extract_article(url: str, html: str) -> dict | None:
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
        no_fallback=False,
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
    article_id = hashlib.sha256(url.encode()).hexdigest()[:16]

    return {
        "id": article_id,
        "url": url,
        "domain": domain,
        "title": title,
        "raw_text": text,
        "word_count": len(words),
        "language": lang,
        "crawl_ts": int(time.time()),
        "status": "ok",
    }
