"""
Recover academic articles the crawler couldn't read.

Publishers (ScienceDirect, PMC, MDPI, Wiley, …) often serve a headless browser
a bot check or paywall instead of the article. Many of those articles are
openly available elsewhere, and scholarly indexes know where:

1. Identify the work: a DOI, PMC id, PubMed id or Elsevier PII in the URL,
   MDPI's ISSN/volume/issue/article URL scheme, or citation meta tags in the
   page we did get.
2. Look it up in OpenAlex (free, no key). Elsevier PIIs go via Crossref.
3. Get text, best first: Europe PMC full text (PMC articles); an open-access
   PDF from OpenAlex's locations; otherwise the abstract.

Measured on the 126 pages real maps skipped as "too short", about 40% are
recoverable this way (mostly full text).
"""

from __future__ import annotations

import io
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx

log = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)  # font-encoding chatter, irrelevant to text

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
USER_AGENT = "discourse-lens/0.2 (open-source research tool)"

MIN_ABSTRACT_WORDS = 60
MAX_PDF_PAGES = 40
MAX_WORDS = 8000  # a paper's substance; keeps a few long papers from dominating answers
MAX_PDF_ATTEMPTS = 3


@dataclass
class Identifier:
    kind: str  # doi | pmcid | pmid | pii | mdpi
    value: str


@dataclass
class Recovered:
    title: str | None
    text: str
    publish_date: str | None  # YYYY-MM-DD
    note: str  # where the text came from, shown to the reader


def new_client() -> httpx.Client:
    return httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT})


# ── identify ─────────────────────────────────────────────────────────────────

_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#&\"'<>]+)")
_DOI_SUFFIXES = re.compile(r"(/(full|abstract|pdf|xml|epdf|meta|html|fulltext))+/?$", re.I)
_META = re.compile(
    r"<meta[^>]+name=[\"'](citation_doi|dc\.identifier|prism\.doi|citation_pmid)[\"'][^>]*"
    r"content=[\"']([^\"']+)[\"']",
    re.I,
)


def _clean_doi(doi: str) -> str:
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
    return _DOI_SUFFIXES.sub("", doi.rstrip("/."))


def identify(url: str, html: str | None = None) -> Identifier | None:
    """Find a scholarly identifier in the URL, else in the page's citation meta tags."""
    u = unquote(url)
    host = urlparse(u).netloc.lower()
    if m := _DOI.search(u):
        return Identifier("doi", _clean_doi(m.group(1)))
    if m := re.search(r"\b(PMC\d{4,9})\b", u):
        return Identifier("pmcid", m.group(1))
    if "pubmed.ncbi.nlm.nih.gov" in host and (m := re.search(r"/(\d{5,9})\b", u)):
        return Identifier("pmid", m.group(1))
    if m := re.search(r"/pii/(S?[0-9X]{15,17})", u, re.I):
        return Identifier("pii", m.group(1).upper())
    if "arxiv.org" in host and (m := re.search(r"(\d{4}\.\d{4,5})", u)):
        return Identifier("doi", f"10.48550/arXiv.{m.group(1)}")
    if m := re.search(r"mdpi\.com/(\d{4}-\d{3}[\dX])/(\d+)/(\d+)/(\d+)", u):
        return Identifier("mdpi", "/".join(m.groups()))
    for name, content in _META.findall(html or ""):
        if name.lower() == "citation_pmid" and content.strip().isdigit():
            return Identifier("pmid", content.strip())
        if (m := _DOI.search(content)) is not None:
            return Identifier("doi", _clean_doi(m.group(1)))
    return None


# ── resolve ──────────────────────────────────────────────────────────────────

def lookup_work(ident: Identifier, client: httpx.Client) -> dict | None:
    """The OpenAlex work for an identifier, or None."""
    if ident.kind == "pii":
        r = client.get(f"{CROSSREF}/works", params={"filter": f"alternative-id:{ident.value}", "rows": 1})
        items = r.json().get("message", {}).get("items", []) if r.status_code == 200 else []
        if not items:
            return None
        ident = Identifier("doi", items[0]["DOI"])
    if ident.kind == "mdpi":
        issn, vol, issue, art = ident.value.split("/")
        r = client.get(f"{OPENALEX}/works", params={"filter": (
            f"primary_location.source.issn:{issn},biblio.volume:{vol},"
            f"biblio.issue:{issue},biblio.first_page:{art}")})
        results = r.json().get("results", []) if r.status_code == 200 else []
        return results[0] if results else None
    r = client.get(f"{OPENALEX}/works/{ident.kind}:{ident.value}")
    return r.json() if r.status_code == 200 else None


def abstract_text(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not inverted_index:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


# ── full text ────────────────────────────────────────────────────────────────

def europe_pmc_text(pmcid: str, client: httpx.Client) -> tuple[str | None, str] | None:
    """(title, body text) from Europe PMC's open-access XML, or None."""
    r = client.get(f"{EUROPE_PMC}/{pmcid}/fullTextXML")
    if r.status_code != 200 or not r.text.lstrip().startswith("<"):
        return None
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return None
    title_el = root.find(".//article-meta//article-title")
    title = " ".join("".join(title_el.itertext()).split()) if title_el is not None else None
    body = root.find(".//body")
    if body is None:
        return None
    paragraphs = []
    for el in body.iter():
        if el.tag in ("title", "p"):
            text = " ".join("".join(el.itertext()).split())
            if text:
                paragraphs.append(text)
    return title, "\n\n".join(paragraphs)


def pdf_text(url: str, client: httpx.Client) -> str | None:
    """Text of an open-access PDF, or None if it's blocked or unreadable."""
    from pypdf import PdfReader

    try:
        r = client.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    try:
        reader = PdfReader(io.BytesIO(r.content))
        pages = [(p.extract_text() or "") for p in reader.pages[:MAX_PDF_PAGES]]
    except Exception:
        log.warning("Couldn't read PDF %s", url, exc_info=True)
        return None
    return clean_pdf_text("\n".join(pages))


_REFERENCES = re.compile(r"^\s*(references|bibliography|literature cited)\s*$", re.I | re.M)


def clean_pdf_text(text: str) -> str:
    """Rejoin hyphenated line breaks, collapse lines, drop the reference list."""
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    matches = list(_REFERENCES.finditer(text))
    if matches and matches[-1].start() > len(text) * 0.5:
        text = text[: matches[-1].start()]
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    # PDF line breaks are layout, not structure: join them; blank lines stay paragraph breaks.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _cap(text: str) -> str:
    words = text.split()
    return text if len(words) <= MAX_WORDS else " ".join(words[:MAX_WORDS])


def _date(work: dict) -> str | None:
    d = work.get("publication_date")
    return d if d and re.match(r"\d{4}-\d{2}-\d{2}$", d) else None


def recover(url: str, html: str | None = None, client: httpx.Client | None = None) -> Recovered | None:
    """Best available text for a blocked academic page or a PDF link, or None."""
    ident = identify(url, html)
    is_pdf = urlparse(url).path.lower().endswith(".pdf")
    if ident is None and not is_pdf:
        return None
    own_client = client is None
    client = client or new_client()
    try:
        found = _recover(ident, client) if ident else None
        if found is None and is_pdf:
            # The crawler doesn't open PDFs; read the file itself.
            text = pdf_text(url, client)
            if text and len(text.split()) >= 500:
                return Recovered(None, _cap(text), None, "Read from the PDF")
        return found
    except (httpx.HTTPError, ValueError):
        log.warning("Recovering %s failed", url, exc_info=True)
        return None
    finally:
        if own_client:
            client.close()


def _recover(ident: Identifier, client: httpx.Client) -> Recovered | None:
    if ident.kind == "pmcid":
        found = europe_pmc_text(ident.value, client)
        if found and found[1]:
            return Recovered(found[0], _cap(found[1]), None, "Full text from Europe PMC")
        work = lookup_work(ident, client)
    else:
        work = lookup_work(ident, client)
        pmcid = ((work or {}).get("ids") or {}).get("pmcid")
        if pmcid:
            found = europe_pmc_text(pmcid.rsplit("/", 1)[-1], client)
            if found and found[1]:
                return Recovered(found[0] or work.get("title"), _cap(found[1]), _date(work),
                                 "Full text from Europe PMC")
    if not work:
        return None

    title = work.get("title") or work.get("display_name")
    pdfs = []
    for loc in [work.get("best_oa_location") or {}, *(work.get("locations") or [])]:
        if loc.get("is_oa") is not False and loc.get("pdf_url") and loc["pdf_url"] not in pdfs:
            pdfs.append(loc["pdf_url"])
    for pdf_url in pdfs[:MAX_PDF_ATTEMPTS]:
        text = pdf_text(pdf_url, client)
        if text and len(text.split()) >= 500:
            host = urlparse(pdf_url).netloc.removeprefix("www.")
            return Recovered(title, _cap(text), _date(work), f"Open-access PDF from {host}")

    abstract = abstract_text(work.get("abstract_inverted_index"))
    if len(abstract.split()) >= MIN_ABSTRACT_WORDS:
        return Recovered(title, abstract, _date(work), "Abstract only: the full text isn't openly available")
    return None
