import asyncio
import hashlib
import io
import json as json_lib
import os
import re
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./data/discourse.db")

app = FastAPI(title="Discourse Lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    schema = (Path(__file__).parent.parent / "db" / "schema.sql").read_text()
    conn = get_db()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def update_job(job_id: str, **kwargs) -> None:
    kwargs["updated_ts"] = int(time.time())
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn = get_db()
    conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    Path("data").mkdir(exist_ok=True)
    init_db()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


class JobRequest(BaseModel):
    topic: str


@app.post("/api/jobs")
def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    now = int(time.time())
    conn = get_db()
    conn.execute(
        "INSERT INTO jobs (id, topic, status, progress, created_ts, updated_ts) VALUES (?,?,?,?,?,?)",
        (job_id, req.topic, "queued", 0, now, now),
    )
    conn.commit()
    conn.close()
    background_tasks.add_task(run_pipeline, job_id, req.topic)
    return {"job_id": job_id}


@app.get("/api/corpus")
def get_corpus():
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT
                p.chunk_id,
                c.article_id,
                a.url,
                a.title,
                a.domain,
                a.publish_date,
                p.x,
                p.y,
                p.cluster_id,
                p.cluster_label,
                p.distance_from_centroid,
                a.word_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE a.status = 'ok'
            ORDER BY p.cluster_id, p.distance_from_centroid
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/clusters")
def get_clusters():
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT p.cluster_id, p.cluster_label,
                   COUNT(DISTINCT c.article_id) AS article_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            GROUP BY p.cluster_id, p.cluster_label
            ORDER BY p.cluster_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/outliers")
def get_outliers(cluster_id: int | None = None):
    conn = get_db()
    try:
        if cluster_id is not None:
            rows = conn.execute(
                """
                SELECT p.chunk_id, p.cluster_id, p.cluster_label,
                       p.distance_from_centroid,
                       c.article_id, a.title, a.domain, a.publish_date
                FROM projections p
                JOIN chunks c ON c.id = p.chunk_id
                JOIN articles a ON a.id = c.article_id
                WHERE a.status = 'ok' AND p.cluster_id = ?
                ORDER BY p.distance_from_centroid DESC
                LIMIT 50
                """,
                (cluster_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.chunk_id, p.cluster_id, p.cluster_label,
                       p.distance_from_centroid,
                       c.article_id, a.title, a.domain, a.publish_date
                FROM projections p
                JOIN chunks c ON c.id = p.chunk_id
                JOIN articles a ON a.id = c.article_id
                WHERE a.status = 'ok'
                ORDER BY p.distance_from_centroid DESC
                LIMIT 50
                """
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "Article not found"})
    return dict(row)


class ChatRequest(BaseModel):
    query: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    from backend.synthesis.rag import query_corpus
    return query_corpus(req.query)


@app.get("/api/export")
def export_obsidian():
    from fastapi.responses import StreamingResponse
    from backend.export import build_canvas, build_vault_files

    conn = get_db()
    try:
        job_row = conn.execute(
            "SELECT topic FROM jobs WHERE status='done' ORDER BY updated_ts DESC LIMIT 1"
        ).fetchone()
        topic = job_row["topic"] if job_row else "discourse"

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
            WHERE a.status = 'ok'
            GROUP BY a.id, a.title, a.url, a.domain, a.publish_date, a.word_count
            ORDER BY MIN(p.cluster_id)
            """
        ).fetchall()
        rows = [dict(r) for r in rows]

        clusters = conn.execute(
            """
            SELECT p.cluster_label, COUNT(DISTINCT c.article_id) AS article_count
            FROM projections p
            JOIN chunks c ON c.id = p.chunk_id
            JOIN articles a ON a.id = c.article_id
            WHERE a.status = 'ok'
            GROUP BY p.cluster_label
            ORDER BY MIN(p.cluster_id)
            """
        ).fetchall()
        clusters = [dict(r) for r in clusters]
    finally:
        conn.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={"error": "No corpus found. Run an analysis first."},
        )

    canvas = build_canvas(rows)
    vault_files = build_vault_files(rows, clusters, topic)

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    zip_name = f"discourse-{slug}.zip"
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
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "Job not found", "code": "NOT_FOUND"},
        )
    return dict(row)


# ---------------------------------------------------------------------------
# Ingestion pipeline (background task)
# ---------------------------------------------------------------------------

async def run_pipeline(job_id: str, topic: str) -> None:
    """Full ingestion + processing pipeline: search → crawl → extract → chunk → dedup."""
    from backend.ingestion.search import collect_urls
    from backend.ingestion.crawler import crawl_urls
    from backend.ingestion.extractor import extract_article
    from backend.processing.metadata import extract_publish_date
    from backend.processing.chunker import chunk_article
    from backend.processing.dedup import mark_duplicates

    try:
        # Step 1: generate queries and search Brave
        update_job(job_id, status="crawling", progress=5)
        urls = await asyncio.to_thread(collect_urls, topic)

        # Step 2: Playwright scrape all URLs — runs in a thread with a fresh event loop
        update_job(job_id, progress=20)
        crawled = await asyncio.to_thread(crawl_urls, urls)

        # Step 3: extract clean text, filter, persist to SQLite
        update_job(job_id, status="processing", progress=60)

        def _extract_and_store() -> tuple[int, list[dict]]:
            ok_count = 0
            ok_articles: list[dict] = []
            conn = sqlite3.connect(DB_PATH)
            try:
                for item in crawled:
                    url = item["url"]
                    html = item["html"]
                    try:
                        article = extract_article(url, html)
                        if article is None:
                            aid = hashlib.sha256(url.encode()).hexdigest()[:16]
                            conn.execute(
                                "INSERT OR IGNORE INTO articles "
                                "(id, url, status, crawl_ts) VALUES (?,?,?,?)",
                                (aid, url, "filtered", int(time.time())),
                            )
                            continue

                        publish_date = extract_publish_date(html, url)
                        conn.execute(
                            "INSERT OR IGNORE INTO articles "
                            "(id, url, domain, title, publish_date, crawl_ts, "
                            " word_count, language, raw_text, status) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (
                                article["id"], article["url"], article["domain"],
                                article["title"], publish_date, article["crawl_ts"],
                                article["word_count"], article["language"],
                                article["raw_text"], "ok",
                            ),
                        )
                        ok_count += 1
                        ok_articles.append({"id": article["id"], "raw_text": article["raw_text"]})
                    except Exception:
                        continue  # individual failure — log and keep going
                conn.commit()
            finally:
                conn.close()
            return ok_count, ok_articles

        ok_count, ok_articles = await asyncio.to_thread(_extract_and_store)

        # Step 4: chunk + dedup all successfully extracted articles
        update_job(job_id, progress=75)

        def _chunk_and_dedup(articles: list[dict]) -> None:
            conn = sqlite3.connect(DB_PATH)
            try:
                for art in articles:
                    if not art.get("raw_text"):
                        continue
                    chunks = chunk_article(art["id"], art["raw_text"])
                    chunks = mark_duplicates(chunks)
                    conn.executemany(
                        "INSERT OR IGNORE INTO chunks "
                        "(id, article_id, parent_id, parent_text, child_text, "
                        " chunk_index, token_count, is_duplicate) "
                        "VALUES (:id, :article_id, :parent_id, :parent_text, :child_text, "
                        " :chunk_index, :token_count, :is_duplicate)",
                        chunks,
                    )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_chunk_and_dedup, ok_articles)

        # Step 5: embed non-duplicate child chunks
        update_job(job_id, status="embedding", progress=80)

        def _embed_and_store() -> None:
            from backend.embedding.embed import embed_chunks
            from backend.embedding.store import write_embeddings

            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT c.id, c.child_text, c.article_id, "
                    "       a.domain, a.publish_date "
                    "FROM chunks c "
                    "JOIN articles a ON a.id = c.article_id "
                    "WHERE c.is_duplicate = 0"
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                return

            chunks_for_embed = [
                {
                    "id": r["id"],
                    "child_text": r["child_text"],
                    "article_id": r["article_id"],
                    "domain": r["domain"] or "",
                    "publish_date": r["publish_date"] or "",
                }
                for r in rows
            ]

            embeddings = embed_chunks(chunks_for_embed)

            # Build full rows for LanceDB (merge embed result with metadata)
            meta_by_id = {c["id"]: c for c in chunks_for_embed}
            lance_rows = []
            for e in embeddings:
                m = meta_by_id[e["chunk_id"]]
                lance_rows.append(
                    {
                        "chunk_id": e["chunk_id"],
                        "article_id": m["article_id"],
                        "vector": e["vector"],
                        "child_text": m["child_text"],
                        "domain": m["domain"],
                        "publish_date": m["publish_date"],
                        "cluster_id": -1,
                    }
                )
            write_embeddings(lance_rows)

        await asyncio.to_thread(_embed_and_store)

        # Step 6: UMAP + k-means + cluster labels → projections table
        update_job(job_id, status="projecting", progress=90)

        def _project() -> None:
            from backend.embedding.project import run_projection
            run_projection(db_path=DB_PATH)

        await asyncio.to_thread(_project)

        update_job(job_id, status="done", progress=100, article_count=ok_count)

    except Exception as e:
        import traceback
        traceback.print_exc()
        update_job(job_id, status="error", error_msg=str(e))
