"""
Ask the corpus: retrieval-augmented chat with numbered citations.

1. Retrieve: hybrid search over the analysis's chunks — vector similarity plus
   BM25 full-text, fused by reciprocal rank — keeping each article's best
   chunk. For follow-ups, the vector query includes the previous question.
2. Number sources across the whole conversation: the excerpts the previous
   answer cited come along again under the same numbers, and newly found
   articles continue the count, so "[6]" means one article throughout.
3. Prompt: recent conversation turns, then the numbered excerpts and the
   question. The model cites excerpts as [n].
3. Stream the answer; the caller saves the finished turn.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

from backend.config import settings
from backend.db import connect
from backend.embedding.embed import embed_chunks
from backend.embedding.store import open_table

MAX_SOURCES = 8  # articles per answer
EXCERPT_CHARS = 3000  # parent chunks are ~1500 tokens; cap keeps prompts bounded
HISTORY_TURNS = 4  # previous question/answer pairs sent with a new question

SYSTEM_PROMPT = """You help a researcher understand a collection of articles on one subject.

Answer only from the numbered excerpts provided with each question. After each claim, cite the excerpts it rests on with bracketed numbers, like [2] or [1][4]. Don't write URLs or titles in place of numbers. Numbers are stable for the whole conversation: an excerpt you cited before is shown again under the same number, and new excerpts get new numbers.

If the excerpts don't cover the question, say so plainly and say what they do cover instead. Don't speculate beyond them.

Be analytical: identify camps, tensions, evidence and gaps rather than summarising article by article. Use short headings and lists only when an answer is long enough to need them."""


class NoCorpusError(LookupError):
    """The analysis has no indexed vectors to search."""


@dataclass
class Source:
    n: int  # the number answers cite; stable for the whole conversation
    chunk_id: str  # which excerpt (lets a follow-up show the model the same text)
    article_id: str
    url: str
    title: str
    domain: str
    publish_date: str | None
    excerpt: str


def order_and_dedupe_by_article(rows: list[dict], ranked_chunk_ids: list[str]) -> list[dict]:
    """
    Put SQLite rows (which come back in arbitrary order) into search rank
    order, then keep only the highest-ranked chunk per article.
    """
    rank = {cid: i for i, cid in enumerate(ranked_chunk_ids)}
    ordered = sorted(rows, key=lambda r: rank.get(r["chunk_id"], len(rank)))
    seen_articles: set[str] = set()
    deduped = []
    for row in ordered:
        if row["article_id"] not in seen_articles:
            seen_articles.add(row["article_id"])
            deduped.append(row)
    return deduped


def _ensure_fts_index(table) -> None:
    """Full-text index on chunk text; built on first use (well under a second)."""
    from lancedb.index import FTS

    if not any(i.index_type == "FTS" for i in table.list_indices()):
        table.create_index("child_text", config=FTS(), replace=True)


def retrieve(
    analysis_id: str,
    question: str,
    previous_question: str | None = None,
    exclude_articles: frozenset[str] = frozenset(),
    first_n: int = 1,
) -> list[Source]:
    """Best excerpt per article, skipping `exclude_articles`, numbered from `first_n`."""
    from lancedb.rerankers import RRFReranker

    table = open_table(analysis_id)
    if table is None:
        raise NoCorpusError("This analysis has no indexed corpus yet.")
    _ensure_fts_index(table)

    # Follow-ups ("what about the second one?") need the earlier question's context.
    semantic_query = f"{previous_question}\n{question}" if previous_question else question
    vector = embed_chunks([{"id": "q", "child_text": semantic_query}], kind="query")[0]["vector"]
    hits = (
        table.search(query_type="hybrid")
        .vector(vector)
        .text(question)
        .rerank(RRFReranker())
        .limit(settings.rag_top_k)
        .to_pandas()
    )
    if hits.empty:
        raise NoCorpusError("This analysis has no indexed corpus yet.")
    chunk_ids = hits["chunk_id"].tolist()
    rows = [r for r in _chunk_rows(chunk_ids) if r["article_id"] not in exclude_articles]
    best = order_and_dedupe_by_article(rows, chunk_ids)[:MAX_SOURCES]
    return [_to_source(n, r) for n, r in enumerate(best, start=first_n)]


def _chunk_rows(chunk_ids: list[str]) -> list[dict]:
    if not chunk_ids:
        return []
    conn = connect()
    try:
        rows = conn.execute(
            f"""
            SELECT c.id AS chunk_id, c.parent_text, c.article_id,
                   a.url, a.title, a.domain, a.publish_date
            FROM chunks c JOIN articles a ON a.id = c.article_id
            WHERE c.id IN ({",".join("?" for _ in chunk_ids)})
            """,
            chunk_ids,
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _to_source(n: int, r: dict) -> Source:
    return Source(
        n=n,
        chunk_id=r["chunk_id"],
        article_id=r["article_id"],
        url=r["url"],
        title=r["title"] or r["domain"] or "Untitled",
        domain=r["domain"] or "",
        publish_date=r["publish_date"],
        excerpt=(r["parent_text"] or "")[:EXCERPT_CHARS],
    )


def carried_sources(history: list[dict]) -> list[Source]:
    """
    The excerpts the previous answer cited, under their original numbers, so
    a follow-up can build on (and check) them. Older stored answers without
    chunk ids can't be carried.
    """
    last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
    if not last or not last.get("sources"):
        return []
    keep = [s for s in last["sources"] if s.get("cited", True) and s.get("chunk_id")]
    rows = {r["chunk_id"]: r for r in _chunk_rows([s["chunk_id"] for s in keep])}
    return [_to_source(s["n"], rows[s["chunk_id"]]) for s in keep if s["chunk_id"] in rows]


def next_source_number(history: list[dict]) -> int:
    used = [s["n"] for m in history for s in (m.get("sources") or [])]
    return max(used, default=0) + 1


def build_messages(history: list[dict], question: str, sources: list[Source]) -> list[dict]:
    """
    Previous turns as plain text (their excerpts aren't resent — the answers
    already summarise them), then this turn's numbered excerpts and question.
    """
    messages = []
    for turn in history[-2 * HISTORY_TURNS :]:
        messages.append({"role": turn["role"], "content": turn["text"]})
    excerpts = "\n\n".join(
        f"[{s.n}] {s.title} ({s.domain}{', ' + s.publish_date if s.publish_date else ''})\n{s.excerpt}"
        for s in sources
    )
    messages.append({
        "role": "user",
        "content": f"Excerpts:\n\n{excerpts}\n\n---\n\nQuestion: {question}",
    })
    return messages


_CITATION = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")


def cited_numbers(text: str, available: set[int]) -> list[int]:
    """Source numbers the answer cites, in first-cited order: [2], [1][3], [1, 4], [2-4]."""
    seen: list[int] = []
    for group in _CITATION.findall(text):
        for part in re.split(r"\s*,\s*", group):
            bounds = [int(x) for x in re.split(r"\s*[–-]\s*", part)]
            for n in range(bounds[0], bounds[-1] + 1):
                if n in available and n not in seen:
                    seen.append(n)
    return seen


def answer_stream(
    analysis_id: str, question: str, history: list[dict]
) -> tuple[list[Source], Iterator[str]]:
    """Retrieve now (so errors surface before streaming starts); stream the answer lazily."""
    from backend.claude_client import stream_text

    previous = next((t["text"] for t in reversed(history) if t["role"] == "user"), None)
    carried = carried_sources(history)
    fresh = retrieve(
        analysis_id,
        question,
        previous,
        exclude_articles=frozenset(s.article_id for s in carried),
        first_n=next_source_number(history),
    )
    sources = carried + fresh
    text = stream_text(
        build_messages(history, question, sources),
        system=SYSTEM_PROMPT,
        max_tokens=8000,
        effort=settings.chat_effort,
    )
    return sources, text


# ── persistence ──────────────────────────────────────────────────────────────

def load_history(analysis_id: str) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, role, text, sources, created_ts FROM chat_messages "
            "WHERE analysis_id = ? ORDER BY id",
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {**dict(r), "sources": json.loads(r["sources"]) if r["sources"] else None} for r in rows
    ]


def save_turn(analysis_id: str, question: str, answer: str, sources: list[Source]) -> dict:
    """Store a finished question/answer pair; returns the stored answer message."""
    now = int(time.time())
    used = set(cited_numbers(answer, {s.n for s in sources}))
    stored = [asdict(s) | {"cited": s.n in used} for s in sources]
    for s in stored:
        del s["excerpt"]  # the reader fetches the full article; keep history small
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO chat_messages (analysis_id, role, text, sources, created_ts) "
            "VALUES (?, 'user', ?, NULL, ?)",
            (analysis_id, question, now),
        )
        cur = conn.execute(
            "INSERT INTO chat_messages (analysis_id, role, text, sources, created_ts) "
            "VALUES (?, 'assistant', ?, ?, ?)",
            (analysis_id, answer, json.dumps(stored), now),
        )
        conn.commit()
        message_id = cur.lastrowid
    finally:
        conn.close()
    return {"id": message_id, "role": "assistant", "text": answer, "sources": stored,
            "created_ts": now}


def clear_history(analysis_id: str) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM chat_messages WHERE analysis_id = ?", (analysis_id,))
        conn.commit()
    finally:
        conn.close()
