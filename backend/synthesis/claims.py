"""
Claim-level consensus: where the sources agree and where they disagree.

Runs on demand (it costs Claude requests, so maps don't do it automatically):
  1. extract — Claude reads each article's opening, BATCH articles per request,
     and lists up to MAX_CLAIMS claims the article argues or reports.
  2. group   — one request gathers claims from different articles into shared
     propositions and marks each claim as agreeing with, qualifying or
     disputing its proposition. Only propositions at least two articles take a
     position on are kept.

Progress and the outcome live on the analysis row (claims_status,
claims_detail); a server restart marks a running job as interrupted.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from backend.claude_client import complete
from backend.db import connect, update_analysis

log = logging.getLogger(__name__)

BATCH = 10
WORKERS = 4
MAX_CLAIMS = 4
OPENING_WORDS = 500
MAX_PROPOSITIONS = 15
STANCES = ("agrees", "qualifies", "disputes")

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article": {"type": "string"},
                    "claims": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["article", "claims"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["articles"],
    "additionalProperties": False,
}

GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "propositions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                # A number, not a label: given "C17" the model
                                # tends to echo the claim's text back instead.
                                "claim": {"type": "integer"},
                                "stance": {"type": "string", "enum": list(STANCES)},
                            },
                            "required": ["claim", "stance"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["statement", "claims"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["propositions"],
    "additionalProperties": False,
}

_running: set[str] = set()
_lock = threading.Lock()


class AlreadyRunning(RuntimeError):
    pass


def start(analysis_id: str) -> None:
    """Find claims in a background thread. Raises AlreadyRunning if it's underway."""
    with _lock:
        if analysis_id in _running:
            raise AlreadyRunning
        _running.add(analysis_id)
    update_analysis(analysis_id, claims_status="running", claims_detail="Starting")
    _launch(analysis_id)


def _launch(analysis_id: str) -> None:
    threading.Thread(target=_run, args=(analysis_id,), daemon=True).start()


def is_running(analysis_id: str) -> bool:
    return analysis_id in _running


def _run(analysis_id: str) -> None:
    try:
        articles = _load_articles(analysis_id)
        if len(articles) < 2:
            raise RuntimeError("This map needs at least two readable articles to compare.")

        def on_batch(done: int) -> None:
            update_analysis(analysis_id, claims_detail=f"Read {done} of {len(articles)} articles")

        claims = extract_claims(articles, on_batch)
        update_analysis(analysis_id, claims_detail=f"Comparing {len(claims)} claims")
        propositions = group_claims(claims)
        _save(analysis_id, claims, propositions)
        update_analysis(analysis_id, claims_status="done",
                        claims_detail=f"{len(propositions)} shared claims from {len(claims)}")
    except Exception as e:
        log.exception("Finding claims failed for %s", analysis_id)
        update_analysis(analysis_id, claims_status="error", claims_detail=str(e) or type(e).__name__)
    finally:
        with _lock:
            _running.discard(analysis_id)


def _load_articles(analysis_id: str) -> list[dict]:
    """Articles on the map (placed, so duplicates and filtered pages are left out)."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT a.id, a.title, a.domain, a.raw_text FROM articles a "
            "JOIN placements p ON p.article_id = a.id "
            "WHERE a.analysis_id = ? AND a.raw_text IS NOT NULL ORDER BY a.id",
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def opening(text: str, words: int = OPENING_WORDS) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + (" …" if len(parts) > words else "")


# ── 1. extract ───────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """Below are the openings of {n} articles about the same subject.

For each article, list up to {max_claims} claims it argues for or reports as findings: \
the points a reader should come away with. Write each claim as one plain, self-contained \
sentence (under 30 words) that names its subject, so it can be compared with claims from \
other articles. Leave out background facts nobody would dispute, and don't invent claims \
the text doesn't make. An article with nothing substantive gets an empty list.

Return every article by its label.

{articles}"""


def extract_claims(articles: list[dict], on_batch=None) -> list[dict]:
    """[{id, article_id, position, text}] for every article, BATCH per request."""
    batches = [articles[i : i + BATCH] for i in range(0, len(articles), BATCH)]
    claims: list[dict] = []
    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for batch, found in zip(batches, pool.map(_extract_batch, batches), strict=True):
            for article in batch:
                for i, text in enumerate(found.get(article["id"], [])[:MAX_CLAIMS]):
                    claims.append({"id": f"{article['id']}:{i}", "article_id": article["id"],
                                   "position": i, "text": text})
            done += len(batch)
            if on_batch:
                on_batch(done)
    return claims


def _extract_batch(batch: list[dict]) -> dict[str, list[str]]:
    labels = {f"A{i + 1}": a for i, a in enumerate(batch)}
    blocks = "\n\n".join(
        f'<article label="{label}">\nTitle: {a["title"] or "(untitled)"} ({a["domain"]})\n'
        f"{opening(a['raw_text'])}\n</article>"
        for label, a in labels.items()
    )
    prompt = EXTRACT_PROMPT.format(n=len(batch), max_claims=MAX_CLAIMS, articles=blocks)
    data = json.loads(complete(prompt, max_tokens=8000, effort="low", json_schema=EXTRACT_SCHEMA))
    out: dict[str, list[str]] = {}
    for item in data["articles"]:
        article = labels.get(item["article"].strip())
        if article:
            out[article["id"]] = [c.strip() for c in item["claims"] if c.strip()]
    return out


# ── 2. group ─────────────────────────────────────────────────────────────────

GROUP_PROMPT = """These claims come from different articles on one subject. Each line is \
a claim number, the article it came from, and the claim.

Find the questions the articles actually take sides on, or the points several of them \
independently make. For each, write a proposition: one neutral, specific sentence \
that a claim can agree with, qualify (agree in part, or with conditions) or dispute. \
Then list the claims that take a position on it, by number, with their stance.

Rules:
- A proposition needs claims from at least two different articles.
- Use each claim at most once, and only where it directly addresses the proposition.
- Prefer propositions where articles disagree, then those many articles share.
- At most {max_props} propositions; most important first.

{claims}"""


def group_claims(claims: list[dict]) -> list[dict]:
    """[{statement, claims: [{claim_id, stance}]}] — validated against the input."""
    if not claims:
        return []
    labels = {i + 1: c for i, c in enumerate(claims)}
    article_labels: dict[str, str] = {}
    for c in claims:
        article_labels.setdefault(c["article_id"], f"A{len(article_labels) + 1}")
    lines = "\n".join(
        f"{n}. [{article_labels[c['article_id']]}] {c['text']}" for n, c in labels.items()
    )
    prompt = GROUP_PROMPT.format(max_props=MAX_PROPOSITIONS, claims=lines)
    data = json.loads(complete(prompt, max_tokens=16000, effort="medium", json_schema=GROUP_SCHEMA))
    return validate_groups(data["propositions"], labels)


def validate_groups(raw: list[dict], labels: dict[int, dict]) -> list[dict]:
    """Drop unknown or reused claims and propositions fewer than two articles address."""
    used: set[str] = set()
    out = []
    for p in raw:
        members = []
        for m in p["claims"]:
            claim = labels.get(m["claim"])
            if claim is None or claim["id"] in used or m["stance"] not in STANCES:
                continue
            members.append({"claim_id": claim["id"], "article_id": claim["article_id"],
                            "stance": m["stance"]})
        # One stance per article: keep each article's first claim.
        seen_articles: set[str] = set()
        members = [m for m in members
                   if not (m["article_id"] in seen_articles or seen_articles.add(m["article_id"]))]
        statement = p["statement"].strip()
        if len(members) >= 2 and statement:
            used.update(m["claim_id"] for m in members)
            out.append({"statement": statement, "claims": members})
    return out[:MAX_PROPOSITIONS]


# ── storage ──────────────────────────────────────────────────────────────────

def _save(analysis_id: str, claims: list[dict], propositions: list[dict]) -> None:
    """Replace the analysis's claims and propositions in one transaction."""
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM propositions WHERE analysis_id = ?", (analysis_id,))
            conn.execute("DELETE FROM claims WHERE analysis_id = ?", (analysis_id,))
            conn.executemany(
                "INSERT INTO claims (id, analysis_id, article_id, position, text) "
                "VALUES (?,?,?,?,?)",
                [(c["id"], analysis_id, c["article_id"], c["position"], c["text"])
                 for c in claims],
            )
            for position, p in enumerate(propositions):
                cur = conn.execute(
                    "INSERT INTO propositions (analysis_id, position, statement) VALUES (?,?,?)",
                    (analysis_id, position, p["statement"]),
                )
                conn.executemany(
                    "INSERT INTO proposition_claims (proposition_id, claim_id, stance) "
                    "VALUES (?,?,?)",
                    [(cur.lastrowid, m["claim_id"], m["stance"]) for m in p["claims"]],
                )
    finally:
        conn.close()


def load(analysis_id: str) -> list[dict]:
    """Saved propositions in order, each with its claims (and their articles)."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT p.id, p.statement, pc.stance, c.id AS claim_id, c.article_id, c.text "
            "FROM propositions p "
            "JOIN proposition_claims pc ON pc.proposition_id = p.id "
            "JOIN claims c ON c.id = pc.claim_id "
            "WHERE p.analysis_id = ? ORDER BY p.position, pc.rowid",
            (analysis_id,),
        ).fetchall()
    finally:
        conn.close()
    by_id: dict[int, dict] = {}
    for r in rows:
        p = by_id.setdefault(r["id"], {"id": r["id"], "statement": r["statement"], "claims": []})
        p["claims"].append({"claim_id": r["claim_id"], "article_id": r["article_id"],
                            "text": r["text"], "stance": r["stance"]})
    return list(by_id.values())


def claim_count(analysis_id: str) -> int:
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM claims WHERE analysis_id = ?", (analysis_id,)
        ).fetchone()[0]
    finally:
        conn.close()

