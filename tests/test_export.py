import pytest
from backend.export import article_slug, build_canvas, build_vault_files


# ── article_slug ────────────────────────────────────────────────────────────

def test_slug_basic():
    assert article_slug("Hello World", "abcdef123456") == "hello-world-123456"


def test_slug_special_chars():
    slug = article_slug("AI: The Future?", "abcdef123456")
    assert slug == "ai-the-future-123456"


def test_slug_long_title():
    long_title = "word " * 20   # 100 chars
    slug = article_slug(long_title, "abcdef123456")
    # base capped at 60 chars + "-" + 6 suffix = 67 max
    assert len(slug) <= 67


# ── build_canvas ─────────────────────────────────────────────────────────────

def test_canvas_empty():
    assert build_canvas([]) == {"nodes": [], "edges": []}


def test_canvas_single_node():
    rows = [{"article_id": "a1", "title": "T", "domain": "x.com", "x": 0.0, "y": 0.0, "cluster_id": 0}]
    result = build_canvas(rows)
    assert len(result["nodes"]) == 1
    assert result["edges"] == []
    node = result["nodes"][0]
    assert node["id"] == "a1"
    assert node["type"] == "text"
    assert node["color"] == "1"


def test_canvas_centering():
    # mean is (0, 0) so coords just get scaled by CANVAS_SCALE (200)
    # NODE_WIDTH=200 → x offset = -100; NODE_HEIGHT=80 → y offset = -40
    rows = [
        {"article_id": "a1", "title": "T1", "domain": "x.com", "x": 2.0, "y": 4.0, "cluster_id": 0},
        {"article_id": "a2", "title": "T2", "domain": "y.com", "x": -2.0, "y": -4.0, "cluster_id": 1},
    ]
    result = build_canvas(rows)
    nodes = {n["id"]: n for n in result["nodes"]}
    # a1: cx=400, x=400-100=300; cy=800, y=800-40=760
    assert nodes["a1"]["x"] == pytest.approx(300)
    assert nodes["a1"]["y"] == pytest.approx(760)
    # a2: cx=-400, x=-400-100=-500; cy=-800, y=-800-40=-840
    assert nodes["a2"]["x"] == pytest.approx(-500)
    assert nodes["a2"]["y"] == pytest.approx(-840)


def test_canvas_color_cycles():
    rows = [
        {"article_id": f"a{i}", "title": f"T{i}", "domain": "d.com",
         "x": float(i), "y": 0.0, "cluster_id": i}
        for i in range(7)
    ]
    result = build_canvas(rows)
    colors = [n["color"] for n in result["nodes"]]
    assert colors[0] == "1"   # cluster 0 → index 0 → "1"
    assert colors[5] == "6"   # cluster 5 → index 5 → "6"
    assert colors[6] == "1"   # cluster 6 wraps back to index 0 → "1"


# ── build_vault_files ────────────────────────────────────────────────────────

def _sample_rows():
    return [
        {
            "article_id": "aaa111",
            "title": "Test Article",
            "url": "https://x.com/1",
            "domain": "x.com",
            "cluster_label": "Cluster A",
            "publish_date": "2023-01",
            "word_count": 500,
        }
    ]


def _sample_clusters():
    return [{"cluster_label": "Cluster A", "article_count": 1}]


def test_vault_has_index():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    assert "_index.md" in files


def test_vault_has_article_file():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    article_files = [k for k in files if k != "_index.md"]
    assert len(article_files) == 1


def test_vault_frontmatter_fields():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    article_files = [k for k in files if k != "_index.md"]
    content = files[article_files[0]]
    assert 'title: "Test Article"' in content
    assert 'cluster: "Cluster A"' in content
    assert 'domain: "x.com"' in content
    assert 'publish_date: "2023-01"' in content
    assert 'word_count: 500' in content


def test_vault_index_contains_wikilink():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    index = files["_index.md"]
    assert "[[" in index
    assert "test-article" in index


def test_vault_index_topic_header():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "my topic")
    assert files["_index.md"].startswith("# my topic")
