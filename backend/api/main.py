import asyncio
import hashlib
import os
import sqlite3
import time
import uuid
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
    """Full Stage 1 ingestion pipeline: search → crawl → extract → store."""
    from backend.ingestion.search import collect_urls
    from backend.ingestion.crawler import crawl_urls
    from backend.ingestion.extractor import extract_article
    from backend.processing.metadata import extract_publish_date

    try:
        # Step 1: generate queries and search Brave
        update_job(job_id, status="crawling", progress=5)
        urls = await asyncio.to_thread(collect_urls, topic)

        # Step 2: Playwright scrape all URLs — runs in a thread with a fresh event loop
        update_job(job_id, progress=20)
        crawled = await asyncio.to_thread(crawl_urls, urls)

        # Step 3: extract clean text, filter, persist to SQLite
        update_job(job_id, status="processing", progress=60)

        def _extract_and_store() -> int:
            ok_count = 0
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
                    except Exception:
                        continue  # individual failure — log and keep going
                conn.commit()
            finally:
                conn.close()
            return ok_count

        ok_count = await asyncio.to_thread(_extract_and_store)
        update_job(job_id, status="done", progress=100, article_count=ok_count)

    except Exception as e:
        update_job(job_id, status="error", error_msg=str(e))
