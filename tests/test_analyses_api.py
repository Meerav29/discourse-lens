import pytest
from conftest import add_analysis, add_article, add_cluster
from fastapi.testclient import TestClient

from backend.api import main
from backend.db import add_event, connect
from backend.embedding import store


@pytest.fixture
def client(isolated, monkeypatch):
    started = []
    monkeypatch.setattr(
        main.pipeline, "start",
        lambda analysis_id, topic, review=False: started.append((analysis_id, topic))
    )
    with TestClient(main.app) as c:
        c.started = started
        yield c


def test_create_and_list(client):
    r = client.post("/api/analyses", json={"topic": "  urban heat islands  "})
    assert r.status_code == 201
    created = r.json()
    assert created["topic"] == "urban heat islands"
    assert created["status"] == "queued"
    assert client.started == [(created["id"], "urban heat islands")]

    listed = client.get("/api/analyses").json()
    assert [a["id"] for a in listed] == [created["id"]]


def test_blank_topic_rejected(client):
    assert client.post("/api/analyses", json={"topic": ""}).status_code == 422


def test_unknown_analysis_is_404_with_string_detail(client):
    r = client.get("/api/analyses/nope/articles")
    assert r.status_code == 404
    assert r.json() == {"detail": "Analysis not found"}


def test_articles_are_scoped_to_analysis(client):
    add_analysis("an1")
    add_analysis("an2")
    add_article("an1", "a1", x=1.5, y=-2.0, distance=0.3)
    add_article("an2", "b1")

    articles = client.get("/api/analyses/an1/articles").json()
    assert [a["article_id"] for a in articles] == ["a1"]
    assert articles[0] | {"url": None} == {
        "article_id": "a1", "url": None, "title": "A1", "domain": None,
        "publish_date": None, "word_count": None, "x": 1.5, "y": -2.0,
        "cluster_id": 0, "distance": 0.3,
    }


def test_clusters_carry_terms_and_description(client):
    add_analysis("an1")
    add_cluster("an1", 1, "Heat equity", 4, [["gentrification", 0.12]], "Who bears the heat.")
    add_cluster("an1", 0, "Cool roofs", 9)

    clusters = client.get("/api/analyses/an1/clusters").json()
    assert [c["label"] for c in clusters] == ["Cool roofs", "Heat equity"]
    assert clusters[1] == {
        "cluster_id": 1, "label": "Heat equity", "description": "Who bears the heat.",
        "article_count": 4, "terms": [{"term": "gentrification", "weight": 0.12}],
    }


def test_article_must_belong_to_analysis(client):
    add_analysis("an1")
    add_analysis("an2")
    add_article("an1", "a1")
    assert client.get("/api/analyses/an1/articles/a1").status_code == 200
    assert client.get("/api/analyses/an2/articles/a1").status_code == 404


def test_delete_cascades_rows_and_vectors(client):
    add_analysis("an1")
    add_analysis("an2")
    add_article("an1", "a1")
    add_cluster("an1", 0, "Zero")
    add_article("an2", "b1")
    store.write_embeddings("an1", [{"chunk_id": "a1#0", "article_id": "a1", "vector": [0.1, 0.2]}])

    assert client.delete("/api/analyses/an1").status_code == 204

    conn = connect()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE analysis_id='an1'").fetchone()[0]
        for t in ("articles", "chunks", "placements", "clusters")
    }
    other = conn.execute("SELECT COUNT(*) FROM chunks WHERE analysis_id='an2'").fetchone()[0]
    conn.close()
    assert counts == {"articles": 0, "chunks": 0, "placements": 0, "clusters": 0}
    assert other == 1
    assert store.open_table("an1") is None
    assert client.get("/api/analyses/an1").status_code == 404


def test_cannot_delete_running_analysis(client):
    add_analysis("an1", status="embedding")
    assert client.delete("/api/analyses/an1").status_code == 409


def test_restart_fails_interrupted_analyses(isolated):
    from backend.db import init_db

    add_analysis("an1", status="crawling")
    init_db()
    conn = connect()
    row = conn.execute("SELECT status, error_msg FROM analyses WHERE id='an1'").fetchone()
    conn.close()
    assert row["status"] == "error"
    assert "restart" in row["error_msg"]


def test_cancel_requires_running_analysis(client):
    add_analysis("an1", status="done")
    assert client.post("/api/analyses/an1/cancel").status_code == 409


def test_cancel_running_analysis(client, monkeypatch):
    add_analysis("an1", status="crawling")
    cancelled = []
    monkeypatch.setattr(main.pipeline, "cancel", lambda aid: cancelled.append(aid) or True)
    r = client.post("/api/analyses/an1/cancel")
    assert r.status_code == 202
    assert cancelled == ["an1"]


def test_events_endpoint_pages_with_after(client):
    add_analysis("an1")
    add_event("an1", "stage", "Crawling")
    add_event("an1", "article", "Title", "https://x")
    events = client.get("/api/analyses/an1/events").json()
    assert [e["kind"] for e in events] == ["stage", "article"]
    later = client.get(f"/api/analyses/an1/events?after={events[0]['id']}").json()
    assert [e["message"] for e in later] == ["Title"]


def _sse(text):
    """Parse an SSE body into a list of {event, id, data} dicts."""
    out = []
    for block in text.strip().split("\n\n"):
        msg = {"event": "message"}
        for line in block.splitlines():
            key, _, value = line.partition(": ")
            msg[key] = value
        out.append(msg)
    return out


def test_stream_sends_log_events_and_resumes(client):
    add_analysis("an1", status="done")
    for i in range(3):
        add_event("an1", "stage", f"step {i}")

    msgs = _sse(client.get("/api/analyses/an1/stream").text)
    logs = [m for m in msgs if m["event"] == "log"]
    assert len(logs) == 3
    assert msgs[-1]["event"] == "message" and '"status":"done"' in msgs[-1]["data"]

    resumed = _sse(
        client.get("/api/analyses/an1/stream", headers={"Last-Event-ID": logs[0]["id"]}).text
    )
    assert [m["data"] for m in resumed if m["event"] == "log"] == [
        logs[1]["data"], logs[2]["data"]
    ]
