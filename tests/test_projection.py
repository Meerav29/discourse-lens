"""run_projection end to end on synthetic embeddings, with the Claude call stubbed."""

import json

from conftest import add_analysis, prose
from test_topics import blobs

from backend.db import connect
from backend.embedding import project, store

MARKERS = ["alphaword", "betaword", "gammaword"]  # letters only: numbers never become terms


def _seed(analysis_id="an1", centers=3, n_per=8):
    """Articles in `centers` well-separated groups, two chunks each, embedded."""
    X, truth = blobs(n_per=n_per, centers=centers, dim=16)
    add_analysis(analysis_id)
    conn = connect()
    rows = []
    for i, (vec, group) in enumerate(zip(X, truth, strict=True)):
        aid = f"a{i}"
        conn.execute(
            "INSERT INTO articles (id, analysis_id, url, title, raw_text, status) VALUES (?,?,?,?,?,?)",
            (aid, analysis_id, f"https://x.test/{i}", f"Article {i}",
             f"{MARKERS[group]} " * 60 + prose(int(group)), "ok"),
        )
        for c in range(2):
            rows.append({"chunk_id": f"{aid}#{c}", "article_id": aid, "vector": vec.tolist()})
    conn.commit()
    conn.close()
    store.write_embeddings(analysis_id, rows)
    return truth


def _fake_complete(prompt, **kwargs):
    ids = sorted({int(line.split()[1]) for line in prompt.splitlines() if line.startswith("Topic ")})
    return json.dumps({"topics": [
        {"id": t, "label": f"Camp {t}", "description": f"About camp {t}."} for t in ids
    ]})


def test_projection_writes_placements_and_named_clusters(isolated, monkeypatch):
    truth = _seed()
    monkeypatch.setattr("backend.claude_client.complete", _fake_complete)
    labelled = []

    project.run_projection("an1", on_label=lambda label, n: labelled.append((label, n)))

    conn = connect()
    placements = conn.execute("SELECT article_id, cluster_id FROM placements").fetchall()
    clusters = [dict(r) for r in conn.execute("SELECT * FROM clusters ORDER BY cluster_id")]
    conn.close()

    assert len(placements) == len(truth)
    assert [c["label"] for c in clusters] == ["Camp 0", "Camp 1", "Camp 2"]
    assert all(c["description"].startswith("About camp") for c in clusters)
    assert sum(c["article_count"] for c in clusters) == len(truth)
    # each topic's strongest key term is its marker word (possibly as a bigram)
    tops = [json.loads(c["terms"])[0][0] for c in clusters]
    assert sorted(next(m for m in MARKERS if m in t) for t in tops) == MARKERS
    assert labelled == [(c["label"], c["article_count"]) for c in clusters]


def test_naming_failure_falls_back_to_key_terms(isolated, monkeypatch):
    _seed()

    def boom(*a, **k):
        raise RuntimeError("API down")

    monkeypatch.setattr("backend.claude_client.complete", boom)
    project.run_projection("an1")

    conn = connect()
    labels = [r[0] for r in conn.execute("SELECT label FROM clusters")]
    conn.close()
    assert len(labels) == 3
    assert all("word" in label.lower() for label in labels)


def test_rerun_replaces_previous_results(isolated, monkeypatch):
    _seed()
    monkeypatch.setattr("backend.claude_client.complete", _fake_complete)
    project.run_projection("an1")
    project.run_projection("an1")
    conn = connect()
    n_clusters = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
    n_placements = conn.execute("SELECT COUNT(*) FROM placements").fetchone()[0]
    conn.close()
    assert (n_clusters, n_placements) == (3, 24)


def test_name_topics_fills_gaps_from_terms(monkeypatch):
    monkeypatch.setattr(
        "backend.claude_client.complete",
        lambda *a, **k: json.dumps({"topics": [{"id": 0, "label": "Named", "description": "D."}]}),
    )
    named = project.name_topics({
        0: {"terms": ["a"], "examples": [], "size": 3},
        1: {"terms": ["roofs", "albedo"], "examples": [], "size": 2},
    })
    assert named == {0: ("Named", "D."), 1: ("Roofs, albedo", None)}
