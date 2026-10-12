import json

import pytest
from conftest import add_analysis
from fastapi.testclient import TestClient

from backend.api import main
from backend.db import connect
from backend.embedding import store
from backend.synthesis import chat
from backend.synthesis.chat import Source

# ── citations and prompt ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Cool roofs win [2]. Trees add humidity [1][3].", [2, 1, 3]),
        ("Grouped [1, 4] and ranged [2-3] and dashed [5–6].", [1, 4, 2, 3, 5, 6]),
        ("Repeats [2] keep first order [1] [2].", [2, 1]),
        ("Out of range [9] and [0] are ignored; years like [2024] too.", []),
        ("No citations at all.", []),
    ],
)
def test_cited_numbers(text, expected):
    assert chat.cited_numbers(text, available={1, 2, 3, 4, 5, 6}) == expected


def _source(n, article="a"):
    return Source(n=n, chunk_id=f"{article}{n}#0", article_id=f"{article}{n}",
                  url=f"https://x.test/{n}", title=f"T{n}", domain="x.test",
                  publish_date="2024-05", excerpt=f"excerpt {n}")


def test_messages_number_the_excerpts_and_keep_recent_history():
    history = []
    for i in range(10):
        history += [{"role": "user", "text": f"q{i}"}, {"role": "assistant", "text": f"a{i}"}]
    messages = chat.build_messages(history, "new question", [_source(1), _source(2)])

    assert len(messages) == 2 * chat.HISTORY_TURNS + 1
    assert messages[0] == {"role": "user", "content": f"q{10 - chat.HISTORY_TURNS}"}
    last = messages[-1]["content"]
    assert "[1] T1 (x.test, 2024-05)\nexcerpt 1" in last
    assert "[2] T2" in last
    assert last.endswith("Question: new question")


# ── retrieval (real LanceDB, stubbed embeddings) ─────────────────────────────


def _seed_corpus(analysis_id="an1"):
    """Three articles; the query vector points at article b, the keywords at article c."""
    add_analysis(analysis_id)
    conn = connect()
    texts = {
        "a": ["general background on city climate", "more background"],
        "b": ["semantic match chunk one", "semantic match chunk two"],
        "c": ["mentions NDVI and Landsat imagery explicitly", "unrelated filler"],
    }
    rows = []
    for art, chunks in texts.items():
        conn.execute(
            "INSERT INTO articles (id, analysis_id, url, title, domain, status) VALUES (?,?,?,?,?,?)",
            (art, analysis_id, f"https://x.test/{art}", f"Article {art}", "x.test", "ok"),
        )
        for i, text in enumerate(chunks):
            cid = f"{art}#{i}"
            conn.execute(
                "INSERT INTO chunks (id, analysis_id, article_id, parent_text, child_text) "
                "VALUES (?,?,?,?,?)",
                (cid, analysis_id, art, f"parent of {cid}", text),
            )
            vec = [1.0, 0.0, 0.0] if art == "b" else [0.0, 1.0, float(i)]
            rows.append({"chunk_id": cid, "article_id": art, "vector": vec, "child_text": text})
    conn.commit()
    conn.close()
    store.write_embeddings(analysis_id, rows)


@pytest.fixture
def corpus(isolated, monkeypatch):
    _seed_corpus()
    seen = []

    def fake_embed(chunks, kind="document", on_batch=None):
        seen.append((chunks[0]["child_text"], kind))
        return [{"chunk_id": c["id"], "vector": [1.0, 0.0, 0.0]} for c in chunks]

    monkeypatch.setattr(chat, "embed_chunks", fake_embed)
    return seen


def test_hybrid_retrieval_finds_semantic_and_keyword_matches(corpus):
    sources = chat.retrieve("an1", "NDVI Landsat")
    articles = [s.article_id for s in sources]
    assert "b" in articles  # nearest by vector
    assert "c" in articles  # only matched by keyword
    assert len(articles) == len(set(articles))  # one excerpt per article
    assert [s.n for s in sources] == list(range(1, len(sources) + 1))
    assert sources[0].excerpt.startswith("parent of ")


def test_followups_embed_the_previous_question_too(corpus):
    chat.retrieve("an1", "and the second one?", previous_question="compare cool roofs and trees")
    assert corpus[-1] == ("compare cool roofs and trees\nand the second one?", "query")


def test_retrieval_skips_excluded_articles_and_numbers_from_first_n(corpus):
    sources = chat.retrieve("an1", "NDVI Landsat", exclude_articles=frozenset({"b"}), first_n=7)
    assert "b" not in [s.article_id for s in sources]
    assert sources[0].n == 7


def test_followup_carries_cited_sources_and_continues_numbering(corpus):
    history = [
        {"role": "user", "text": "first question"},
        {"role": "assistant", "text": "Answer [2].", "sources": [
            {"n": 1, "chunk_id": "a#0", "article_id": "a", "cited": False},
            {"n": 2, "chunk_id": "b#1", "article_id": "b", "cited": True},
        ]},
    ]
    carried = chat.carried_sources(history)
    assert [(s.n, s.article_id, s.excerpt) for s in carried] == [(2, "b", "parent of b#1")]
    assert chat.next_source_number(history) == 3

    sources, _text = chat.answer_stream("an1", "NDVI Landsat", history)
    numbers = [s.n for s in sources]
    assert numbers[0] == 2  # the carried source keeps its number
    assert numbers[1:] == list(range(3, 3 + len(numbers) - 1))  # new ones continue the count
    assert [s.article_id for s in sources].count("b") == 1  # not retrieved twice


def test_retrieval_without_vectors_is_no_corpus(isolated):
    add_analysis("empty")
    with pytest.raises(chat.NoCorpusError):
        chat.retrieve("empty", "anything")


# ── API: streaming, saving, clearing ─────────────────────────────────────────


def _parse_sse(body: str) -> list[tuple[str, object]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


@pytest.fixture
def client(isolated, monkeypatch):
    add_analysis("an1")
    calls = []

    def fake_answer_stream(analysis_id, question, history):
        calls.append((question, [m["text"] for m in history]))
        return [_source(1), _source(2)], iter(["Roofs win ", "[2]."])

    monkeypatch.setattr("backend.synthesis.chat.answer_stream", fake_answer_stream)
    with TestClient(main.app) as c:
        c.calls = calls
        yield c


def test_answer_streams_then_saves_the_turn(client):
    r = client.post("/api/analyses/an1/chat", json={"question": "  Who wins?  "})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)

    assert [e for e, _ in events] == ["sources", "delta", "delta", "done"]
    assert [s["n"] for s in events[0][1]] == [1, 2]
    assert "excerpt" not in events[0][1][0]
    done = events[-1][1]
    assert done["text"] == "Roofs win [2]."
    assert [s["cited"] for s in done["sources"]] == [False, True]

    history = client.get("/api/analyses/an1/chat").json()
    assert [(m["role"], m["text"]) for m in history] == [
        ("user", "Who wins?"), ("assistant", "Roofs win [2].")
    ]

    client.post("/api/analyses/an1/chat", json={"question": "Why?"})
    assert client.calls[-1] == ("Why?", ["Who wins?", "Roofs win [2]."])


def test_failed_answer_reports_error_and_saves_nothing(client, monkeypatch):
    def broken(analysis_id, question, history):
        def text():
            yield "Partial"
            raise RuntimeError("connection reset")
        return [_source(1)], text()

    monkeypatch.setattr("backend.synthesis.chat.answer_stream", broken)
    events = _parse_sse(client.post("/api/analyses/an1/chat", json={"question": "Q"}).text)
    assert events[-1][0] == "error"
    assert "connection reset" in events[-1][1]["detail"]
    assert client.get("/api/analyses/an1/chat").json() == []


def test_no_corpus_is_409_before_streaming(client, monkeypatch):
    def none(*a):
        raise chat.NoCorpusError("This analysis has no indexed corpus yet.")

    monkeypatch.setattr("backend.synthesis.chat.answer_stream", none)
    r = client.post("/api/analyses/an1/chat", json={"question": "Q"})
    assert r.status_code == 409


def test_clear_chat(client):
    client.post("/api/analyses/an1/chat", json={"question": "Q"})
    assert client.delete("/api/analyses/an1/chat").status_code == 204
    assert client.get("/api/analyses/an1/chat").json() == []


def test_blank_question_rejected(client):
    assert client.post("/api/analyses/an1/chat", json={"question": ""}).status_code == 422
