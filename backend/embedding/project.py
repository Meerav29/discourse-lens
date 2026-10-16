"""
Map + topics for one analysis.

1. Load the analysis's chunk vectors; average them into one vector per article.
2. Topic model (backend.topics): UMAP → HDBSCAN → merge/assign/cap → 2D map.
3. Key terms per topic by c-TF-IDF over the articles' text.
4. One Claude call names every topic at once, so names are distinct.
5. Replace the analysis's rows in `placements` and `clusters`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import numpy as np

from backend import topics
from backend.db import connect
from backend.embedding.store import read_all_embeddings

log = logging.getLogger(__name__)

TERMS_PER_TOPIC = 10
EXCERPT_CHARS = 400

LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["id", "label", "description"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def run_projection(
    analysis_id: str,
    on_step: Callable[[float, str], None] | None = None,
    on_label: Callable[[str, int], None] | None = None,
) -> None:
    """
    Build the map and topics for an analysis whose chunks are embedded.

    on_step(fraction_done, detail) reports progress; on_label(label, n_articles)
    fires once per topic after naming.
    """

    def step(fraction: float, detail: str) -> None:
        if on_step:
            on_step(fraction, detail)

    rows = read_all_embeddings(analysis_id)
    if not rows:
        raise RuntimeError("No embeddings found for this analysis — run the embedding step first.")
    ids, X = topics.article_vectors(
        np.array([r["vector"] for r in rows], dtype=np.float32),
        [r["article_id"] for r in rows],
    )

    step(0.0, f"Finding topics among {len(ids)} articles")
    labels, coords, dist = topics.model_topics(X)

    step(0.6, "Finding each topic's key terms")
    articles = _load_articles(analysis_id, ids)
    terms = topics.topic_terms(
        [articles[i]["raw_text"] or "" for i in ids], labels, top_n=TERMS_PER_TOPIC
    )
    reps = topics.representatives(X, labels, k=3)

    step(0.75, f"Naming {len(terms)} topics")
    named = name_topics(
        {
            t: {
                "terms": [w for w, _ in terms.get(t, [])],
                "examples": [articles[ids[i]] for i in reps.get(t, [])],
                "size": int(np.sum(labels == t)),
            }
            for t in sorted(terms)
        }
    )

    conn = connect()
    try:
        conn.execute("DELETE FROM placements WHERE analysis_id = ?", (analysis_id,))
        conn.execute("DELETE FROM clusters WHERE analysis_id = ?", (analysis_id,))
        conn.executemany(
            "INSERT INTO placements (article_id, analysis_id, x, y, cluster_id, distance) "
            "VALUES (?,?,?,?,?,?)",
            [
                (aid, analysis_id, float(coords[i, 0]), float(coords[i, 1]),
                 int(labels[i]), float(dist[i]))
                for i, aid in enumerate(ids)
            ],
        )
        conn.executemany(
            "INSERT INTO clusters (analysis_id, cluster_id, label, description, article_count, terms) "
            "VALUES (?,?,?,?,?,?)",
            [
                (analysis_id, t, named[t][0], named[t][1], int(np.sum(labels == t)),
                 json.dumps([[w, round(s, 6)] for w, s in terms.get(t, [])]))
                for t in sorted(terms)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    if on_label:
        for t in sorted(terms):
            on_label(named[t][0], int(np.sum(labels == t)))


def _load_articles(analysis_id: str, ids: list[str]) -> dict[str, dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, title, domain, raw_text FROM articles WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    found = {r["id"]: dict(r) for r in rows}
    return {i: found.get(i, {"id": i, "title": None, "domain": None, "raw_text": ""}) for i in ids}


def name_topics(topics_in: dict[int, dict]) -> dict[int, tuple[str, str | None]]:
    """
    Name every topic in one request so the names contrast with each other —
    naming topics one at a time gave near-identical names to neighbours.
    Falls back to the top key terms if the request fails.
    """
    from backend.claude_client import complete

    fallback = {
        t: (", ".join(info["terms"][:3]).capitalize() or f"Topic {t + 1}", None)
        for t, info in topics_in.items()
    }
    if not topics_in:
        return {}

    blocks = []
    for t, info in topics_in.items():
        examples = "\n".join(
            f"  - {(a['title'] or a['domain'] or 'Untitled')}: "
            f"{' '.join((a['raw_text'] or '').split())[:EXCERPT_CHARS]}"
            for a in info["examples"]
        )
        blocks.append(
            f"Topic {t} ({info['size']} articles)\n"
            f"Key terms: {', '.join(info['terms'])}\n"
            f"Most typical articles:\n{examples}"
        )
    prompt = (
        "These topics were found by clustering articles about one subject. For each topic, "
        "write a label of 2 to 4 words naming the angle or camp it represents, and one "
        "sentence (under 25 words) describing what its articles argue or cover.\n\n"
        "Labels must be clearly different from each other: they will sit side by side on a "
        "map, so name what sets each topic apart rather than the subject they all share. "
        "Use sentence case.\n\n" + "\n\n".join(blocks)
    )
    try:
        data = json.loads(complete(prompt, max_tokens=8000, effort="low", json_schema=LABEL_SCHEMA))
        named = {int(item["id"]): (item["label"].strip(), item["description"].strip())
                 for item in data["topics"]}
    except Exception:
        log.warning("Naming topics failed; using key terms instead", exc_info=True)
        return fallback
    return {t: named.get(t) or fallback[t] for t in topics_in}
