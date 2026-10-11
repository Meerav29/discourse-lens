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
    "queued", "crawling", "processing", "embedding", "projecting", "done", "error", "cancelled"
]


class AnalysisCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)


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


class CorpusPoint(BaseModel):
    chunk_id: str
    article_id: str
    child_text: str | None
    url: str
    title: str | None
    domain: str | None
    publish_date: str | None
    x: float
    y: float
    cluster_id: int
    cluster_label: str | None
    distance_from_centroid: float
    word_count: int | None


class Cluster(BaseModel):
    cluster_id: int
    cluster_label: str | None
    article_count: int


class Outlier(BaseModel):
    chunk_id: str
    cluster_id: int
    cluster_label: str | None
    distance_from_centroid: float
    article_id: str
    title: str | None
    domain: str | None
    publish_date: str | None


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


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    url: str
    title: str
    domain: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


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


def fetch_outliers(
    conn: sqlite3.Connection, analysis_id: str, cluster_id: int | None = None, limit: int = 50
) -> list[dict]:
    """One row per article — its chunk furthest from its cluster centroid —
    ordered by that distance, optionally restricted to one cluster."""
    rows = conn.execute(
        """
        SELECT chunk_id, cluster_id, cluster_label, distance_from_centroid,
               article_id, title, domain, publish_date
        FROM (
            SELECT p.chunk_id, p.cluster_id, p.cluster_label,
                   p.distance_from_centroid,
                   c.article_id, a.title, a.domain, a.publish_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.article_id
                       ORDER BY p.distance_from_centroid DESC
                   ) AS rn
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE p.analysis_id = :aid AND a.status = 'ok'
              AND (:cid IS NULL OR p.cluster_id = :cid)
        )
        WHERE rn = 1
        ORDER BY distance_from_centroid DESC
        LIMIT :limit
        """,
        {"aid": analysis_id, "cid": cluster_id, "limit": limit},
    ).fetchall()
    return [dict(r) for r in rows]


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
    pipeline.start(analysis_id, topic)
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

@app.get("/api/analyses/{analysis_id}/corpus")
def get_corpus(analysis_id: str) -> list[CorpusPoint]:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        rows = conn.execute(
            """
            SELECT p.chunk_id, c.article_id, c.child_text, a.url, a.title, a.domain,
                   a.publish_date, p.x, p.y, p.cluster_id, p.cluster_label,
                   p.distance_from_centroid, a.word_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE p.analysis_id = ? AND a.status = 'ok'
            ORDER BY p.cluster_id, p.distance_from_centroid
            """,
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    return [CorpusPoint(**dict(r)) for r in rows]


@app.get("/api/analyses/{analysis_id}/clusters")
def get_clusters(analysis_id: str) -> list[Cluster]:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        rows = conn.execute(
            """
            SELECT p.cluster_id, p.cluster_label,
                   COUNT(DISTINCT c.article_id) AS article_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            WHERE p.analysis_id = ?
            GROUP BY p.cluster_id, p.cluster_label
            ORDER BY p.cluster_id
            """,
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    return [Cluster(**dict(r)) for r in rows]


@app.get("/api/analyses/{analysis_id}/outliers")
def get_outliers(analysis_id: str, cluster_id: int | None = None) -> list[Outlier]:
    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
        return [Outlier(**r) for r in fetch_outliers(conn, analysis_id, cluster_id)]
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


@app.post("/api/analyses/{analysis_id}/chat")
def chat(analysis_id: str, req: ChatRequest) -> ChatResponse:
    from backend.synthesis.rag import NoCorpusError, query_corpus

    conn = connect()
    try:
        _get_analysis(conn, analysis_id)
    finally:
        conn.close()
    try:
        return ChatResponse(**query_corpus(analysis_id, req.query))
    except NoCorpusError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chat failed: {e}") from e


@app.get("/api/analyses/{analysis_id}/export")
def export_obsidian(analysis_id: str):
    from backend.export import build_canvas, build_vault_files

    conn = connect()
    try:
        topic = _get_analysis(conn, analysis_id)["topic"]
        rows = conn.execute(
            """
            SELECT
                a.id AS article_id, a.title, a.url, a.domain,
                a.publish_date, a.word_count,
                AVG(p.x) AS x, AVG(p.y) AS y,
                MIN(p.cluster_id) AS cluster_id,
                MIN(p.cluster_label) AS cluster_label
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE p.analysis_id = ? AND a.status = 'ok'
            GROUP BY a.id, a.title, a.url, a.domain, a.publish_date, a.word_count
            ORDER BY MIN(p.cluster_id)
            """,
            (analysis_id,),
        ).fetchall()
        rows = [dict(r) for r in rows]

        clusters = conn.execute(
            """
            SELECT p.cluster_label, COUNT(DISTINCT c.article_id) AS article_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE p.analysis_id = ? AND a.status = 'ok'
            GROUP BY p.cluster_label
            ORDER BY MIN(p.cluster_id)
            """,
            (analysis_id,),
        ).fetchall()
        clusters = [dict(r) for r in clusters]
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
