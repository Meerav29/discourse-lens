"""
Create a small, fully synthetic demo map — no crawling, no API keys.

Used by the end-to-end tests, and handy for trying the interface before
setting up search, embedding and Claude keys.

    uv run python -m scripts.seed_demo                      # into the configured database
    DB_PATH=/tmp/e2e.db LANCE_PATH=/tmp/e2e-vectors uv run python -m scripts.seed_demo --reset
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from backend.config import settings
from backend.db import connect, init_db
from backend.embedding import store

DEMO_ID = "demo-0000-0000-0000-000000000001"
DEMO_TOPIC = "Demo: urban heat and city design"

# (cluster, title, domain, publish date, x, y, distance)
ARTICLES = [
    (0, "Cool roofs lower rooftop temperatures", "roofs.example", "2023-06", 1.0, 1.2, 0.08),
    (0, "White paint versus green roofs", "roofs.example", "2024-02", 1.3, 0.9, 0.10),
    (0, "Measuring albedo on city blocks", "albedo.example", "2024-07", 0.8, 1.5, 0.12),
    (0, "Reflective pavements in practice", "streets.example", "2025-01", 1.6, 1.4, 0.31),
    (1, "Street trees and shade equity", "canopy.example", "2022-08", -1.2, 0.4, 0.09),
    (1, "Canopy cover maps for planners", "canopy.example", "2023-03", -1.0, 0.1, 0.11),
    (1, "Parks as cool islands", "parks.example", "2024-05", -1.5, 0.7, 0.14),
    (1, "Watering trees in drought summers", "parks.example", "2025-04", -0.7, -0.1, 0.27),
    (2, "Who lives in the hottest neighbourhoods", "justice.example", "2021-07", 0.2, -1.4, 0.07),
    (2, "Heat, redlining and health", "justice.example", "2023-09", 0.5, -1.1, 0.12),
    (2, "Cooling centres and outreach", "health.example", "2024-08", -0.1, -1.7, 0.18),
    (-1, "A history of urban climatology", "history.example", "2019-05", 2.4, -0.6, 0.45),
]

CLUSTERS = [
    (0, "Reflective surfaces", "Articles on cool roofs, albedo and reflective pavements as a fast way to cut surface heat.",
     [["cool roofs", 0.31], ["albedo", 0.24], ["reflective", 0.19], ["pavement", 0.12]]),
    (1, "Trees and green space", "Articles on canopy, parks and the upkeep that makes trees an effective cooling strategy.",
     [["canopy", 0.33], ["shade", 0.22], ["parks", 0.18], ["drought", 0.09]]),
    (2, "Heat and inequality", "Articles on who is most exposed to urban heat and how cities respond.",
     [["redlining", 0.29], ["exposure", 0.21], ["health", 0.17], ["outreach", 0.08]]),
]


def body(title: str, n: int) -> str:
    """Placeholder article text (synthetic; long enough to read as an article)."""
    lines = [f"{title}. This is demo text for Discourse Lens, not a real article."]
    lines += [f"Paragraph {i + 1} discusses {title.lower()} in a fictional city, "
              "with figures invented for the demo." for i in range(n)]
    return "\n\n".join(lines)


def seed(reset: bool = False) -> str:
    if reset:
        Path(settings.db_path).unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(settings.db_path + suffix).unlink(missing_ok=True)
        shutil.rmtree(settings.lance_path, ignore_errors=True)
    init_db()
    now = int(time.time())
    conn = connect()
    try:
        conn.execute("DELETE FROM analyses WHERE id = ?", (DEMO_ID,))
        conn.execute(
            "INSERT INTO analyses (id, topic, status, progress, stage_detail, article_count, "
            "created_ts, updated_ts) VALUES (?,?,?,?,?,?,?,?)",
            (DEMO_ID, DEMO_TOPIC, "done", 100, f"Indexed {len(ARTICLES)} articles",
             len(ARTICLES), now, now),
        )
        vectors = []
        for i, (cluster, title, domain, date, x, y, dist) in enumerate(ARTICLES):
            aid = f"demo-article-{i:02d}"
            text = body(title, 6)
            conn.execute(
                "INSERT INTO articles (id, analysis_id, url, domain, title, publish_date, crawl_ts, "
                "word_count, language, raw_text, status, source_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, DEMO_ID, f"https://{domain}/{aid}", domain, title, date, now,
                 len(text.split()), "en", text, "ok",
                 "Abstract only: the full text isn't openly available" if i == 2 else None),
            )
            conn.execute(
                "INSERT INTO chunks (id, analysis_id, article_id, parent_id, parent_text, child_text, "
                "chunk_index, token_count, is_duplicate) VALUES (?,?,?,?,?,?,?,?,0)",
                (f"{aid}#p0c0", DEMO_ID, aid, f"{aid}#p0", text, text, 0, len(text.split())),
            )
            conn.execute(
                "INSERT INTO placements (article_id, analysis_id, x, y, cluster_id, distance) "
                "VALUES (?,?,?,?,?,?)",
                (aid, DEMO_ID, x, y, cluster, dist),
            )
            vectors.append({"chunk_id": f"{aid}#p0c0", "article_id": aid, "child_text": text,
                            "domain": domain, "publish_date": date,
                            "vector": [float(cluster == k) for k in (0, 1, 2)] + [x, y]})
        for cid, label, description, terms in CLUSTERS:
            size = sum(1 for a in ARTICLES if a[0] == cid)
            conn.execute(
                "INSERT INTO clusters (analysis_id, cluster_id, label, description, article_count, terms) "
                "VALUES (?,?,?,?,?,?)",
                (DEMO_ID, cid, label, description, size, json.dumps(terms)),
            )
        for kind, message in [("stage", "Crawling 14 pages"), ("article", ARTICLES[0][1]),
                              ("skip", "Too short (40 words)"), ("stage", "Done")]:
            conn.execute(
                "INSERT INTO analysis_events (analysis_id, ts, kind, message) VALUES (?,?,?,?)",
                (DEMO_ID, now, kind, message),
            )
        sources = [
            {"n": 1, "chunk_id": "demo-article-00#p0c0", "article_id": "demo-article-00",
             "url": "https://roofs.example/demo-article-00", "title": ARTICLES[0][1],
             "domain": "roofs.example", "publish_date": "2023-06", "cited": True},
            {"n": 2, "chunk_id": "demo-article-04#p0c0", "article_id": "demo-article-04",
             "url": "https://canopy.example/demo-article-04", "title": ARTICLES[4][1],
             "domain": "canopy.example", "publish_date": "2022-08", "cited": True},
            {"n": 3, "chunk_id": "demo-article-08#p0c0", "article_id": "demo-article-08",
             "url": "https://justice.example/demo-article-08", "title": ARTICLES[8][1],
             "domain": "justice.example", "publish_date": "2021-07", "cited": False},
        ]
        conn.execute(
            "INSERT INTO chat_messages (analysis_id, role, text, sources, created_ts) "
            "VALUES (?, 'user', ?, NULL, ?)",
            (DEMO_ID, "Do cool roofs or trees cool cities more?", now),
        )
        conn.execute(
            "INSERT INTO chat_messages (analysis_id, role, text, sources, created_ts) "
            "VALUES (?, 'assistant', ?, ?, ?)",
            (DEMO_ID,
             "The demo articles disagree. Cool roofs act fastest on surface heat [1], while "
             "trees also bring shade along streets [2].", json.dumps(sources), now),
        )
        conn.commit()
    finally:
        conn.close()
    store.drop_embeddings(DEMO_ID)
    store.write_embeddings(DEMO_ID, vectors)
    return DEMO_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--reset", action="store_true",
                        help="delete the database and vectors first (only for throwaway paths)")
    args = parser.parse_args()
    print(f"Seeded demo map {seed(args.reset)} into {settings.db_path}")


if __name__ == "__main__":
    main()
