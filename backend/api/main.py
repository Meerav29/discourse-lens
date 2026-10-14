import asyncio
import io
import json as json_lib
import re
import sqlite3
import sys
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import pipeline
from backend.config import settings
from backend.db import RUNNING_STATUSES, connect, init_db
from backend.embedding.store import drop_embeddings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield
    pipeline.cancel_all()


app = FastAPI(
    title="Discourse Lens API",
    lifespan=lifespan,
    # Operation ids = route function names, so the generated client reads
    # listAnalyses() rather than listAnalysesApiAnalysesGet().
    generate_unique_id_function=lambda route: route.name,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

AnalysisStatus = Literal[
    "queued", "crawling", "reviewing", "processing", "embedding", "projecting", "done", "error",
    "cancelled",
]


class AnalysisCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    # Pause after searching so the user can edit queries and choose pages.
    review: bool = False


class PlanResult(BaseModel):
    url: str
    title: str
    snippet: str
    query: str


class Plan(BaseModel):
    """What a paused analysis found: its queries and the pages they returned."""

    queries: list[str]
    results: list[PlanResult]


class PlanSearch(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=12)


class PlanApprove(BaseModel):
    urls: list[str] = Field(min_length=1)


class Analysis(BaseModel):
    id: str
    topic: str
    status: AnalysisStatus
    progress: int
    stage_detail: str | None
    article_count: int
    error_msg: str | None
    warning: str | None
    created_ts: int
    updated_ts: int


class AnalysisEvent(BaseModel):
    id: int
    ts: int
    kind: Literal["stage", "query", "article", "skip", "cluster", "warning", "error"]
    message: str
    url: str | None


class MapArticle(BaseModel):
    """An article as placed on the map."""

    article_id: str
    url: str
    title: str | None
    domain: str | None
    publish_date: str | None
    word_count: int | None
    x: float
    y: float
    cluster_id: int  # -1 = unclustered
    distance: float  # cosine distance to its topic's centre: the outlier score


class Term(BaseModel):
    term: str
    weight: float


class Cluster(BaseModel):
    cluster_id: int
    label: str
    description: str | None
    article_count: int
    terms: list[Term]


class Article(BaseModel):
    id: str
    analysis_id: str
    url: str
    domain: str | None
    title: str | None
    publish_date: str | None
    crawl_ts: int | None
    word_count: int | None
    language: str | None
    raw_text: str | None
    status: str
    source_note: str | None = None  # set when the text came from an open-access copy


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ChatSource(BaseModel):
    """An excerpt the answer could cite as [n]."""

    n: int
    article_id: str
    url: str
    title: str
    domain: str
    publish_date: str | None
    cited: bool | None = None  # set once the answer is complete


class ChatMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str
    sources: list[ChatSource] | None
    created_ts: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_analysis(conn: sqlite3.Connection, analysis_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return row


def fetch_events(conn: sqlite3.Connection, analysis_id: str, after: int = 0) -> list[AnalysisEvent]:
    rows = conn.execute(
        "SELECT id, ts, kind, message, url FROM analysis_events "
        "WHERE analysis_id = ? AND id > ? ORDER BY id",
        (analysis_id, after),
    ).fetchall()
    return [AnalysisEvent(**dict(r)) for r in rows]


def fetch_clusters(conn: sqlite3.Connection, analysis_id: str) -> list[Cluster]:
    rows = conn.execute(
        "SELECT cluster_id, label, description, article_count, terms FROM clusters "
        "WHERE analysis_id = ? ORDER BY cluster_id",
        (analysis_id,),
    ).fetchall()
    return [
        Cluster(
            cluster_id=r["cluster_id"],
            label=r["label"],
            description=r["description"],
            article_count=r["article_count"],
            terms=[Term(term=t, weight=w) for t, w in json_lib.loads(r["terms"])],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyses", status_code=201)
async def create_analysis(req: AnalysisCreate) -> Analysis:
    analysis_id = str(uuid.uuid4())
    now = int(time.time())
    topic = req.topic.strip()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO analyses (id, topic, status, progress, created_ts, updated_ts) "
            "VALUES (?,?,?,?,?,?)",
            (analysis_id, topic, "queued", 0, now, now),
        )
        conn.commit()
        row = _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    pipeline.start(analysis_id, topic, review=req.review)
    return Analysis(**dict(row))


@app.get("/api/analyses")
def list_analyses() -> list[Analysis]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM analyses ORDER BY created_ts DESC").fetchall()
    finally:
        conn.close()
    return [Analysis(**dict(r)) for r in rows]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> Analysis:
    conn = connect()
    try:
        return Analysis(**dict(_get_analysis(conn, analysis_id)))
    finally:
        conn.close()


@app.delete("/api/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str) -> Response:
    conn = connect()
    try:
        row = _get_analysis(conn, analysis_id)
        if row["status"] in RUNNING_STATUSES:
            raise HTTPException(status_code=409, detail="Analysis is still running")
        conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
        conn.commit()
    finally:
        conn.close()
    drop_embeddings(analysis_id)
    return Response(status_code=204)


@app.post("/api/analyses/{analysis_id}/cancel", status_code=202)
def cancel_analysis(analysis_id: str) -> Analysis:
    """Ask a running analysis to stop; it reaches status 'cancelled' shortly after."""
    conn = connect()
    try:
        row = _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    if row["status"] not in RUNNING_STATUSES or not pipeline.cancel(analysis_id):
        raise HTTPException(status_code=409, detail="Analysis is not running")
    return Analysis(**dict(row))


def _awaiting_review(analysis_id: str) -> pipeline.RunContext:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    ctx = pipeline.context(analysis_id)
    if ctx is None or not ctx.awaiting_review():
        raise HTTPException(status_code=409, detail="This analysis isn't waiting for review")
    return ctx


@app.get("/api/analyses/{analysis_id}/plan")
def get_plan(analysis_id: str) -> Plan:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    plan = pipeline.load_plan(analysis_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="This analysis has no search plan")
    return Plan(**plan)


@app.post("/api/analyses/{analysis_id}/plan/search")
def search_plan(analysis_id: str, req: PlanSearch) -> Plan:
    """Run edited queries again while the analysis waits for review."""
    from backend.ingestion.search import search_all

    _awaiting_review(analysis_id)
    queries = [q.strip() for q in req.queries if q.strip()]
    if not queries:
        raise HTTPException(status_code=422, detail="Give at least one search query")
    results = search_all(queries)
    plan = pipeline.save_plan(analysis_id, queries, results)
    from backend.db import add_event, update_analysis

    update_analysis(analysis_id, stage_detail=f"Waiting for you to review {len(results)} pages")
    add_event(analysis_id, "stage", f"Searched again: {len(results)} pages")
    return Plan(**plan)


@app.post("/api/analyses/{analysis_id}/plan/approve", status_code=202)
def approve_plan(analysis_id: str, req: PlanApprove) -> Analysis:
    """Continue the paused analysis with the chosen pages (search results or your own URLs)."""
    from urllib.parse import urlparse

    ctx = _awaiting_review(analysis_id)
    urls = list(dict.fromkeys(u.strip() for u in req.urls if u.strip()))
    bad = [u for u in urls if urlparse(u).scheme not in ("http", "https") or not urlparse(u).netloc]
    if bad:
        raise HTTPException(status_code=422, detail=f"Not a web address: {bad[0]}")
    if len(urls) > settings.max_articles:
        raise HTTPException(
            status_code=422,
            detail=f"Choose at most {settings.max_articles} pages (you chose {len(urls)})",
        )
    ctx.approve(urls)
    conn = connect()
    try:
        return Analysis(**dict(_get_analysis(conn, analysis_id)))
    finally:
        conn.close()


@app.get("/api/analyses/{analysis_id}/events")
def get_events(analysis_id: str, after: int = 0) -> list[AnalysisEvent]:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        return fetch_events(conn, analysis_id, after)
    finally:
        conn.close()


STREAM_POLL_SECONDS = 0.5


@app.get("/api/analyses/{analysis_id}/stream")
async def stream_analysis(analysis_id: str, last_event_id: int = Header(0)):
    """
    Server-sent events until the analysis stops running:
      default `message` events — the Analysis row, whenever it changes
      `log` events (with `id:`) — new rows from the event log; EventSource
      resends Last-Event-ID on reconnect, so the log resumes where it left off.
    """
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()

    async def event_generator():
        last_payload = None
        last_id = last_event_id
        while True:
            conn = connect()
            try:
                row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
                events = fetch_events(conn, analysis_id, last_id) if row else []
            finally:
                conn.close()

            if row is None:  # deleted while streaming
                yield f"event: error\ndata: {json_lib.dumps({'detail': 'Analysis not found'})}\n\n"
                return

            for ev in events:
                yield f"event: log\nid: {ev.id}\ndata: {ev.model_dump_json()}\n\n"
                last_id = ev.id

            payload = Analysis(**dict(row)).model_dump_json()
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload

            if row["status"] not in RUNNING_STATUSES:
                return

            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Analysis data
# ---------------------------------------------------------------------------

@app.get("/api/analyses/{analysis_id}/articles")
def list_articles(analysis_id: str) -> list[MapArticle]:
    """Every article on the map, with its position, topic and outlier score."""
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        rows = conn.execute(
            """
            SELECT p.article_id, a.url, a.title, a.domain, a.publish_date, a.word_count,
                   p.x, p.y, p.cluster_id, p.distance
            FROM placements p
            JOIN articles a ON a.id = p.article_id
            WHERE p.analysis_id = ?
            ORDER BY p.cluster_id, p.distance
            """,
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    return [MapArticle(**dict(r)) for r in rows]


@app.get("/api/analyses/{analysis_id}/clusters")
def get_clusters(analysis_id: str) -> list[Cluster]:
    """Topics, largest first, with their key terms. Unclustered articles have none."""
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        return fetch_clusters(conn, analysis_id)
    finally:
        conn.close()


@app.get("/api/analyses/{analysis_id}/articles/{article_id}")
def get_article(analysis_id: str, article_id: str) -> Article:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ? AND analysis_id = ?", (article_id, analysis_id)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return Article(**dict(row))


@app.get("/api/analyses/{analysis_id}/chat")
def get_chat(analysis_id: str) -> list[ChatMessage]:
    """The saved conversation for this analysis, oldest first."""
    from backend.synthesis.chat import load_history

    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    return [ChatMessage(**m) for m in load_history(analysis_id)]


@app.delete("/api/analyses/{analysis_id}/chat", status_code=204)
def clear_chat(analysis_id: str) -> Response:
    from backend.synthesis.chat import clear_history

    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    clear_history(analysis_id)
    return Response(status_code=204)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json_lib.dumps(data)}\n\n"


@app.post(
    "/api/analyses/{analysis_id}/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def ask(analysis_id: str, req: ChatRequest):
    """
    Ask a question; the answer streams as server-sent events:
      sources — the numbered excerpts the answer may cite (ChatSource[])
      delta   — {"text": ...}, a piece of the answer as it's written
      done    — the saved answer (ChatMessage), with each source's `cited` set
      error   — {"detail": ...}; nothing is saved
    The question and answer are saved together only when the answer completes.
    """
    from dataclasses import asdict

    from backend.synthesis.chat import NoCorpusError, answer_stream, load_history, save_turn

    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()

    question = req.question.strip()
    history = load_history(analysis_id)
    try:
        sources, text_stream = answer_stream(analysis_id, question, history)
    except NoCorpusError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Couldn't search the corpus: {e}") from e

    def events():
        yield _sse("sources", [{k: v for k, v in asdict(s).items() if k != "excerpt"}
                               for s in sources])
        parts: list[str] = []
        try:
            for piece in text_stream:
                parts.append(piece)
                yield _sse("delta", {"text": piece})
        except Exception as e:
            yield _sse("error", {"detail": f"The answer stopped early: {e}"})
            return
        message = save_turn(analysis_id, question, "".join(parts).strip(), sources)
        yield _sse("done", message)

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/analyses/{analysis_id}/export")
def export_obsidian(analysis_id: str):
    from backend.export import build_canvas, build_vault_files

    conn = connect()
    try:
        topic = _get_analysis(conn, analysis_id)["topic"]
        rows = conn.execute(
            """
            SELECT a.id AS article_id, a.title, a.url, a.domain, a.publish_date,
                   a.word_count, p.x, p.y, p.cluster_id,
                   COALESCE(c.label, 'Unclustered') AS cluster_label
            FROM placements p
            JOIN articles a ON a.id = p.article_id
            LEFT JOIN clusters c
              ON c.analysis_id = p.analysis_id AND c.cluster_id = p.cluster_id
            WHERE p.analysis_id = ?
            ORDER BY p.cluster_id < 0, p.cluster_id
            """,
            (analysis_id,),
        ).fetchall()
        rows = [dict(r) for r in rows]

        counts: dict[str, int] = {}
        for r in rows:
            counts[r["cluster_label"]] = counts.get(r["cluster_label"], 0) + 1
        clusters = [{"cluster_label": k, "article_count": n} for k, n in counts.items()]
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="This analysis has no corpus to export.")

    canvas = build_canvas(rows)
    vault_files = build_vault_files(rows, clusters, topic)

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    folder = f"discourse-{slug}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{folder}/cluster-map.canvas",
            json_lib.dumps(canvas, ensure_ascii=False, indent=2),
        )
        for path, content in vault_files.items():
            zf.writestr(f"{folder}/vault/{path}", content)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'},
    )


# ---------------------------------------------------------------------------
# Frontend (registered last so it never shadows an API route)
# ---------------------------------------------------------------------------

if (Path(settings.frontend_build)).is_dir():
    from backend.api.spa import spa_router

    app.include_router(spa_router(Path(settings.frontend_build)))
