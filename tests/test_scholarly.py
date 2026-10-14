import httpx
import pytest

from backend.ingestion import scholarly
from backend.ingestion.scholarly import Identifier, identify

# ── identify ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://doi.org/10.1093/jsh/shaf109", ("doi", "10.1093/jsh/shaf109")),
        ("https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2024GL109634/full",
         ("doi", "10.1029/2024GL109634")),
        ("https://www.frontiersin.org/journals/x/articles/10.3389/fenvs.2026.1770260/xml",
         ("doi", "10.3389/fenvs.2026.1770260")),
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC6458494/", ("pmcid", "PMC6458494")),
        ("https://pubmed.ncbi.nlm.nih.gov/31234567/", ("pmid", "31234567")),
        ("https://www.sciencedirect.com/science/article/pii/S0360132322001234",
         ("pii", "S0360132322001234")),
        ("https://arxiv.org/abs/2404.14082", ("doi", "10.48550/arXiv.2404.14082")),
        ("https://www.mdpi.com/2073-4433/16/7/791", ("mdpi", "2073-4433/16/7/791")),
    ],
)
def test_identify_from_url(url, expected):
    found = identify(url)
    assert (found.kind, found.value) == expected


def test_identify_from_citation_meta_tags():
    html = '<head><meta name="citation_doi" content="doi:10.1016/j.uclim.2023.101234"></head>'
    assert identify("https://example.org/article/123", html) == Identifier("doi", "10.1016/j.uclim.2023.101234")
    html = '<meta name="citation_pmid" content="31234567">'
    assert identify("https://example.org/a", html) == Identifier("pmid", "31234567")


def test_ordinary_pages_have_no_identifier():
    assert identify("https://www.nytimes.com/2024/07/01/climate/heat.html", "<p>hi</p>") is None


# ── helpers ──────────────────────────────────────────────────────────────────


def test_abstract_rebuilt_from_inverted_index():
    inv = {"Cities": [0], "trap": [1], "heat": [2, 5], "and": [3], "release": [4]}
    assert scholarly.abstract_text(inv) == "Cities trap heat and release heat"
    assert scholarly.abstract_text(None) == ""


def test_pdf_text_cleanup_joins_lines_and_drops_references():
    body = "Urban heat is meas-\nured by satellites.\nIt varies by block.\n\n" + "Text. " * 50
    text = scholarly.clean_pdf_text(body + "\nReferences\n1. Smith J. Heat. 2020.")
    assert "measured by satellites. It varies by block." in text
    assert "Smith" not in text


# ── recovery paths (stubbed web) ─────────────────────────────────────────────

ARTICLE = " ".join(["cool roofs reduce urban heat"] * 150)  # 750 words


def client_for(routes):
    """A client whose requests are answered by `routes[(host, path-prefix)]`."""

    def handler(request: httpx.Request) -> httpx.Response:
        for (host, prefix), make in routes.items():
            if request.url.host == host and request.url.path.startswith(prefix):
                return make(request)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def work(**over):
    return {
        "title": "Cool roofs in hot cities",
        "publication_date": "2024-05-02",
        "ids": {},
        "best_oa_location": {"is_oa": True, "pdf_url": "https://journal.test/paper.pdf"},
        "locations": [],
        "abstract_inverted_index": {w: [i] for i, w in enumerate("word" + str(i) for i in range(80))},
        **over,
    }


def test_doi_with_open_access_pdf(monkeypatch):
    monkeypatch.setattr(scholarly, "pdf_text", lambda url, client: ARTICLE)
    client = client_for({("api.openalex.org", "/works/doi:"): lambda r: httpx.Response(200, json=work())})
    got = scholarly.recover("https://doi.org/10.1234/abc", client=client)
    assert got.title == "Cool roofs in hot cities"
    assert got.publish_date == "2024-05-02"
    assert got.note == "Open-access PDF from journal.test"
    assert len(got.text.split()) == 750


def test_blocked_pdf_falls_back_to_abstract(monkeypatch):
    monkeypatch.setattr(scholarly, "pdf_text", lambda url, client: None)
    client = client_for({("api.openalex.org", "/works/doi:"): lambda r: httpx.Response(200, json=work())})
    got = scholarly.recover("https://doi.org/10.1234/abc", client=client)
    assert got.note.startswith("Abstract only")
    assert got.text.split()[:2] == ["word0", "word1"]


def test_tries_other_open_access_locations(monkeypatch):
    tried = []

    def fake_pdf(url, client):
        tried.append(url)
        return ARTICLE if "repository" in url else None

    monkeypatch.setattr(scholarly, "pdf_text", fake_pdf)
    w = work(locations=[{"is_oa": True, "pdf_url": "https://repository.test/copy.pdf"}])
    client = client_for({("api.openalex.org", "/works/doi:"): lambda r: httpx.Response(200, json=w)})
    got = scholarly.recover("https://doi.org/10.1234/abc", client=client)
    assert tried == ["https://journal.test/paper.pdf", "https://repository.test/copy.pdf"]
    assert got.note == "Open-access PDF from repository.test"


PMC_XML = """<article><front><article-meta><title-group>
<article-title>Heat and health</article-title></title-group></article-meta></front>
<body><sec><title>Introduction</title><p>Heat kills more people than floods.</p>
<p>Cities are hotter.</p></sec></body><back><ref-list><ref>Smith 2020</ref></ref-list></back></article>"""


def test_pmc_page_uses_europe_pmc_full_text():
    client = client_for({
        ("www.ebi.ac.uk", "/europepmc/webservices/rest/PMC1234567/fullTextXML"):
            lambda r: httpx.Response(200, text=PMC_XML),
    })
    got = scholarly.recover("https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/", client=client)
    assert got.title == "Heat and health"
    assert got.text == "Introduction\n\nHeat kills more people than floods.\n\nCities are hotter."
    assert got.note == "Full text from Europe PMC"


def test_elsevier_pii_resolved_through_crossref(monkeypatch):
    monkeypatch.setattr(scholarly, "pdf_text", lambda url, client: ARTICLE)
    seen = []

    def openalex(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=work())

    client = client_for({
        ("api.crossref.org", "/works"): lambda r: httpx.Response(
            200, json={"message": {"items": [{"DOI": "10.1016/j.x.2024.1"}]}}),
        ("api.openalex.org", "/works/doi:"): openalex,
    })
    got = scholarly.recover("https://www.sciencedirect.com/science/article/pii/S0360132322001234",
                            client=client)
    assert seen == ["/works/doi:10.1016/j.x.2024.1"]
    assert got is not None


def test_unknown_work_and_unidentifiable_pages_recover_nothing():
    client = client_for({})
    assert scholarly.recover("https://doi.org/10.1234/missing", client=client) is None
    assert scholarly.recover("https://blog.test/post", client=client) is None


def test_network_errors_are_contained():
    def boom(request):
        raise httpx.ConnectError("down")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    assert scholarly.recover("https://doi.org/10.1234/abc", client=client) is None


def test_plain_pdf_links_are_read_directly(monkeypatch):
    monkeypatch.setattr(scholarly, "pdf_text", lambda url, client: ARTICLE)
    got = scholarly.recover("https://city.gov/reports/heat-plan.pdf", client=client_for({}))
    assert (got.note, got.title) == ("Read from the PDF", None)
