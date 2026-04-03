import re

import trafilatura


# URL date slug patterns, most specific first
_URL_DATE_PATTERNS = [
    r"/(\d{4})/(\d{1,2})/(\d{1,2})",   # /2024/03/15/
    r"/(\d{4})-(\d{2})-(\d{2})",        # /2024-03-15
    r"/(\d{4})(\d{2})(\d{2})(?=/|$|\.)",  # /20240315
    r"/(\d{4})/(\d{2})(?=/|$)",          # /2024/03 (month only)
]


def extract_publish_date(html: str, url: str) -> str | None:
    """
    Extract article publish date with three fallbacks:
    1. trafilatura metadata (parses <meta> tags, JSON-LD, etc.)
    2. URL date slug (regex)
    3. None — never crashes.
    """
    # Fallback 1: trafilatura metadata
    try:
        meta = trafilatura.extract_metadata(html, default_url=url)
        if meta and meta.date:
            date = meta.date.strip()
            m = re.match(r"(\d{4}-\d{2}-\d{2})", date)
            if m:
                return m.group(1)
            m = re.match(r"(\d{4}-\d{2})", date)
            if m:
                return m.group(1)
    except Exception:
        pass

    # Fallback 2: URL date slug
    try:
        for pattern in _URL_DATE_PATTERNS:
            m = re.search(pattern, url)
            if m:
                groups = m.groups()
                if len(groups) >= 3:
                    year, month, day = groups[:3]
                    if 1990 <= int(year) <= 2030:
                        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                elif len(groups) == 2:
                    year, month = groups
                    if 1990 <= int(year) <= 2030:
                        return f"{year}-{month.zfill(2)}"
    except Exception:
        pass

    # Fallback 3: give up
    return None
