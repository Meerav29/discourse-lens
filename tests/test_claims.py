import json
import re

import pytest
from conftest import add_analysis, add_article
from fastapi.testclient import TestClient

from backend.api import main
from backend.db import connect, init_db
from backend.synthesis import claims

# ── validation ───────────────────────────────────────────────────────────────


def _labels(*pairs):
    """1, 2, ... -> claim dicts, from (article_id, text) pairs."""
    return {i + 1: {"id": f"{a}:{i}", "article_id": a, "text": t}
            for i, (a, t) in enumerate(pairs)}


def test_groups_drop_unknown_reused_and_single_article_claims():
    labels = _labels(("a", "x"), ("b", "y"), ("a", "z"), ("c", "w"))
    raw = [
        {"statement": "P1", "claims": [{"claim": 1, "stance": "agrees"},
                                       {"claim": 2, "stance": "disputes"},
                                       {"claim": 99, "stance": "agrees"}]},
        # claim 1 is used already, which leaves one article
        {"statement": "P2", "claims": [{"claim": 1, "stance": "agrees"},
                                       {"claim": 3, "stance": "agrees"}]},
        # two claims from article a: only the first counts, so one article: dropped
        {"statement": "P3", "claims": [{"claim": 3, "stance": "agrees"},
                                       {"claim": 3, "stance": "qualifies"}]},
        {"statement": " P4 ", "claims": [{"claim": 3, "stance": "qualifies"},
                                         {"claim": 4, "stance": "agrees"}]},
    ]
    out = claims.validate_groups(raw, labels)
    assert [p["statement"] for p in out] == ["P1", "P4"]
    assert [(m["claim_id"], m["stance"]) for m in out[0]["claims"]] == [
        ("a:0", "agrees"), ("b:1", "disputes")]


def test_one_stance_per_article_within_a_proposition():
    labels = _labels(("a", "x"), ("a", "y"), ("b", "z"))
    raw = [{"statement": "P", "claims": [{"claim": 1, "stance": "agrees"},
                                         {"claim": 2, "stance": "disputes"},
                                         {"claim": 3, "stance": "agrees"}]}]
    out = claims.validate_groups(raw, labels)
    assert [m["claim_id"] for m in out[0]["claims"]] == ["a:0", "b:2"]


def test_opening_keeps_the_first_words():
    assert claims.opening("one two three", words=2) == "one two …"
    assert claims.opening("one two", words=2) == "one two"


# ── extraction and grouping with a stubbed Claude ────────────────────────────


def fake_claude(prompt, *, json_schema, **_):
    """Two claims per article; then one proposition from the first claim of each article."""
    if json_schema is claims.EXTRACT_SCHEMA:
        labels = re.findall(r'<article label="(A\d+)">', prompt)
        return json.dumps({"articles": [
            {"article": label, "claims": [f"{label} claim one", f"{label} claim two", " "]}
            for label in labels] + [{"article": "A99", "claims": ["ghost"]}]})
    firsts = [int(n) for n in re.findall(r"^(\d+)\. \[A\d+\] A\d+ claim one$", prompt, re.M)]
    return json.dumps({"propositions": [{
        "statement": "Cool roofs lower temperatures",
        "claims": [{"claim": c, "stance": "disputes" if i == 1 else "agrees"}
                   for i, c in enumerate(firsts)],
    }]})


def test_extract_maps_labels_back_to_articles(monkeypatch):
    monkeypatch.setattr(claims, "complete", fake_claude)
    articles = [{"id": f"art{i}", "title": "T", "domain": "x.test", "raw_text": "words " * 50}
                for i in range(12)]
    progress = []
    found = claims.extract_claims(articles, on_batch=progress.append)
    assert len(found) == 24  # blank claims and unknown labels dropped
    assert found[0] == {"id": "art0:0", "article_id": "art0", "position": 0,
                        "text": "A1 claim one"}
    assert found[-1]["article_id"] == "art11"  # second batch labels restart at A1
    assert progress == [10, 12]


# ── API: find, poll, read ────────────────────────────────────────────────────


@pytest.fixture
def client(isolated, monkeypatch):
    monkeypatch.setattr(claims, "complete", fake_claude)
    monkeypatch.setattr(claims, "_launch", claims._run)  # inline, so tests don't race a thread
    return TestClient(main.app)


def _seed(analysis_id="an1", n=3):
    add_analysis(analysis_id)
    for i in range(n):
        add_article(analysis_id, f"art{i}")
    conn = connect()
    conn.execute("UPDATE articles SET raw_text = 'Some article text.', domain = 'x.test'")
    conn.commit()
    conn.close()


def test_find_claims_then_read_them(client):
    _seed()
    assert client.get("/api/analyses/an1/claims").json() == {
        "status": None, "detail": None, "claim_count": 0, "propositions": []}

    r = client.post("/api/analyses/an1/claims")
    assert r.status_code == 202

    body = client.get("/api/analyses/an1/claims").json()
    assert body["status"] == "done"
    assert body["claim_count"] == 6
    [p] = body["propositions"]
    assert p["statement"] == "Cool roofs lower temperatures"
    assert [(c["article_id"], c["stance"], c["text"]) for c in p["claims"]] == [
        ("art0", "agrees", "A1 claim one"),
        ("art1", "disputes", "A2 claim one"),
        ("art2", "agrees", "A3 claim one"),
    ]


def test_running_again_replaces_the_previous_claims(client):
    _seed()
    client.post("/api/analyses/an1/claims")
    client.post("/api/analyses/an1/claims")
    body = client.get("/api/analyses/an1/claims").json()
    assert body["claim_count"] == 6 and len(body["propositions"]) == 1


def test_too_few_articles_is_an_error_not_a_crash(client):
    _seed(n=1)
    client.post("/api/analyses/an1/claims")
    body = client.get("/api/analyses/an1/claims").json()
    assert body["status"] == "error"
    assert "at least two" in body["detail"]


def test_unfinished_map_cannot_find_claims(client):
    add_analysis("an2", status="crawling")
    assert client.post("/api/analyses/an2/claims").status_code == 409


def test_already_running_is_a_conflict(isolated, monkeypatch):
    _seed()
    monkeypatch.setattr(claims, "_running", {"an1"})
    assert TestClient(main.app).post("/api/analyses/an1/claims").status_code == 409


def test_restart_marks_a_running_job_interrupted(isolated):
    _seed()
    conn = connect()
    conn.execute("UPDATE analyses SET claims_status = 'running'")
    conn.commit()
    conn.close()
    init_db()
    body = TestClient(main.app).get("/api/analyses/an1/claims").json()
    assert body["status"] == "error"
    assert body["detail"] == "Interrupted by a server restart"


def test_deleting_the_analysis_removes_its_claims(client):
    _seed()
    client.post("/api/analyses/an1/claims")
    assert client.delete("/api/analyses/an1").status_code == 204
    conn = connect()
    counts = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("claims", "propositions", "proposition_claims")]
    conn.close()
    assert counts == [0, 0, 0]
