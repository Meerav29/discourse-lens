# Stage 6: Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Obsidian Canvas + vault export and a chat retry button so the app is presentable.

**Architecture:** A new `backend/export.py` module handles all data transformation (UMAP coords → canvas pixels, articles → markdown frontmatter). The FastAPI endpoint streams a zip. The frontend downloads it as a blob and triggers a browser save. Chat retry stores the last query and re-submits on button click.

**Tech Stack:** Python `zipfile` + `io.BytesIO` (stdlib), FastAPI `StreamingResponse`, Svelte reactive state, Obsidian Canvas JSON format.

---

## File Map

| File | Action |
|------|--------|
| `backend/export.py` | Create — canvas + vault builders |
| `tests/test_export.py` | Create — unit tests |
| `backend/api/main.py` | Modify — add `/api/export` endpoint |
| `frontend/src/lib/api.js` | Modify — add `exportZip()` |
| `frontend/src/routes/+page.svelte` | Modify — Export button |
| `frontend/src/components/ChatPanel.svelte` | Modify — retry button |

---

## Task 1: Backend export module

**Files:**
- Create: `backend/export.py`
- Create: `tests/test_export.py`

- [ ] **Step 1: Create `backend/export.py`**

```python
"""
Export utilities: Obsidian Canvas JSON and vault markdown files.
"""

from __future__ import annotations

import re
import statistics


CANVAS_SCALE = 200     # UMAP units → canvas pixels
NODE_WIDTH = 200
NODE_HEIGHT = 80
CLUSTER_COLORS = ["1", "2", "3", "4", "5", "6"]  # Obsidian canvas named colors


def article_slug(title: str, article_id: str) -> str:
    """Convert a title + id into a safe filename slug (max ~67 chars)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base[:60]
    suffix = article_id[-6:]
    return f"{base}-{suffix}"


def build_canvas(rows: list[dict]) -> dict:
    """
    Build Obsidian Canvas JSON from corpus rows.

    Each row must have: article_id, title, domain, x, y, cluster_id.
    Coordinates are centered (mean subtracted) then scaled by CANVAS_SCALE.
    Returns {"nodes": [...], "edges": []}.
    """
    if not rows:
        return {"nodes": [], "edges": []}

    mean_x = statistics.mean(r["x"] for r in rows)
    mean_y = statistics.mean(r["y"] for r in rows)

    nodes = []
    for r in rows:
        cx = round((r["x"] - mean_x) * CANVAS_SCALE)
        cy = round((r["y"] - mean_y) * CANVAS_SCALE)
        color = CLUSTER_COLORS[int(r["cluster_id"]) % len(CLUSTER_COLORS)]
        nodes.append({
            "id": r["article_id"],
            "type": "text",
            "text": f"**{r['title']}**\n{r['domain']}",
            "x": cx - NODE_WIDTH // 2,
            "y": cy - NODE_HEIGHT // 2,
            "width": NODE_WIDTH,
            "height": NODE_HEIGHT,
            "color": color,
        })

    return {"nodes": nodes, "edges": []}


def build_vault_files(
    rows: list[dict],
    clusters: list[dict],
    topic: str,
) -> dict[str, str]:
    """
    Build vault file contents.

    rows: each must have article_id, title, url, domain, cluster_label,
          publish_date, word_count.
    clusters: list of {cluster_label, article_count}.
    topic: the original topic string (used in _index.md header).
    Returns {relative_path: file_content} — no leading slash.
    """
    files: dict[str, str] = {}
    slug_map: dict[str, str] = {}

    for r in rows:
        slug = article_slug(r.get("title") or "untitled", r["article_id"])
        slug_map[r["article_id"]] = slug
        frontmatter = (
            "---\n"
            f'title: "{_esc(r.get("title") or "")}"\n'
            f'url: "{r.get("url") or ""}"\n'
            f'domain: "{r.get("domain") or ""}"\n'
            f'cluster: "{_esc(r.get("cluster_label") or "")}"\n'
            f'publish_date: "{r.get("publish_date") or ""}"\n'
            f'word_count: {r.get("word_count") or 0}\n'
            "---\n"
        )
        files[f"{slug}.md"] = frontmatter

    # Cluster table for index
    table_rows = "\n".join(
        f"| {c['cluster_label']} | {c['article_count']} |"
        for c in clusters
    )

    # Articles grouped by cluster for index sections
    by_cluster: dict[str, list[dict]] = {}
    for r in rows:
        label = r.get("cluster_label") or "Unclustered"
        by_cluster.setdefault(label, []).append(r)

    sections = []
    for label, arts in by_cluster.items():
        links = "\n".join(f"- [[{slug_map[a['article_id']]}]]" for a in arts)
        sections.append(f"### {label}\n{links}")

    index = (
        f"# {topic}\n\n"
        f"Analysed {len(rows)} articles across {len(clusters)} clusters.\n\n"
        "## Clusters\n\n"
        "| Cluster | Articles |\n"
        "|---------|----------|\n"
        f"{table_rows}\n\n"
        "## Articles by cluster\n\n"
        + "\n\n".join(sections)
    )
    files["_index.md"] = index

    return files


def _esc(s: str) -> str:
    """Escape double quotes for YAML inline strings."""
    return s.replace('"', '\\"')
```

- [ ] **Step 2: Create `tests/test_export.py`**

```python
import pytest
from backend.export import article_slug, build_canvas, build_vault_files


# ── article_slug ────────────────────────────────────────────────────────────

def test_slug_basic():
    assert article_slug("Hello World", "abcdef123456") == "hello-world-123456"


def test_slug_special_chars():
    slug = article_slug("AI: The Future?", "abcdef123456")
    assert slug == "ai-the-future-123456"


def test_slug_long_title():
    long_title = "word " * 20   # 100 chars
    slug = article_slug(long_title, "abcdef123456")
    # base capped at 60 chars + "-" + 6 suffix = 67 max
    assert len(slug) <= 67


# ── build_canvas ─────────────────────────────────────────────────────────────

def test_canvas_empty():
    assert build_canvas([]) == {"nodes": [], "edges": []}


def test_canvas_single_node():
    rows = [{"article_id": "a1", "title": "T", "domain": "x.com", "x": 0.0, "y": 0.0, "cluster_id": 0}]
    result = build_canvas(rows)
    assert len(result["nodes"]) == 1
    assert result["edges"] == []
    node = result["nodes"][0]
    assert node["id"] == "a1"
    assert node["type"] == "text"
    assert node["color"] == "1"


def test_canvas_centering():
    # mean is (0,0) so coords just get scaled
    rows = [
        {"article_id": "a1", "title": "T1", "domain": "x.com", "x": 2.0, "y": 4.0, "cluster_id": 0},
        {"article_id": "a2", "title": "T2", "domain": "y.com", "x": -2.0, "y": -4.0, "cluster_id": 1},
    ]
    result = build_canvas(rows)
    nodes = {n["id"]: n for n in result["nodes"]}
    # x is placed at center of node: cx - NODE_WIDTH//2 = (2.0 * 200) - 100 = 300
    assert nodes["a1"]["x"] == pytest.approx(300)
    assert nodes["a1"]["y"] == pytest.approx(700)
    assert nodes["a2"]["x"] == pytest.approx(-500)
    assert nodes["a2"]["y"] == pytest.approx(-900)


def test_canvas_color_cycles():
    rows = [
        {"article_id": f"a{i}", "title": f"T{i}", "domain": "d.com",
         "x": float(i), "y": 0.0, "cluster_id": i}
        for i in range(7)
    ]
    result = build_canvas(rows)
    colors = [n["color"] for n in result["nodes"]]
    assert colors[0] == "1"   # cluster 0 → color index 0 → "1"
    assert colors[5] == "6"   # cluster 5 → color index 5 → "6"
    assert colors[6] == "1"   # cluster 6 wraps back to index 0 → "1"


# ── build_vault_files ────────────────────────────────────────────────────────

def _sample_rows():
    return [
        {
            "article_id": "aaa111",
            "title": "Test Article",
            "url": "https://x.com/1",
            "domain": "x.com",
            "cluster_label": "Cluster A",
            "publish_date": "2023-01",
            "word_count": 500,
        }
    ]


def _sample_clusters():
    return [{"cluster_label": "Cluster A", "article_count": 1}]


def test_vault_has_index():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    assert "_index.md" in files


def test_vault_has_article_file():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    article_files = [k for k in files if k != "_index.md"]
    assert len(article_files) == 1


def test_vault_frontmatter_fields():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    article_files = [k for k in files if k != "_index.md"]
    content = files[article_files[0]]
    assert 'title: "Test Article"' in content
    assert 'cluster: "Cluster A"' in content
    assert 'domain: "x.com"' in content
    assert 'publish_date: "2023-01"' in content
    assert 'word_count: 500' in content


def test_vault_index_contains_wikilink():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "test topic")
    index = files["_index.md"]
    # Should contain a wikilink to the article slug
    assert "[[" in index
    assert "test-article" in index


def test_vault_index_topic_header():
    files = build_vault_files(_sample_rows(), _sample_clusters(), "my topic")
    assert files["_index.md"].startswith("# my topic")
```

- [ ] **Step 3: Run tests to verify they fail correctly**

```bash
cd C:/Users/meera/Github-Projects/discourse-lens
source venv/Scripts/activate
pytest tests/test_export.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `backend.export` doesn't exist yet (but we just created it, so this should actually pass). If all pass, continue.

- [ ] **Step 4: Commit**

```bash
git add backend/export.py tests/test_export.py
git commit -m "feat: add export module with canvas + vault builders"
```

---

## Task 2: Export endpoint

**Files:**
- Modify: `backend/api/main.py` (add import + endpoint after the `/api/chat` route)

- [ ] **Step 1: Add the `/api/export` endpoint to `backend/api/main.py`**

Add this import at the top of the file (after existing imports):

```python
import io
import json as json_lib
import re
import zipfile
```

Add this endpoint after the `chat` route (around line 208):

```python
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
```

- [ ] **Step 2: Verify the endpoint exists**

With the backend running (`python -m uvicorn backend.api.main:app --reload --port 8001`), hit the health check first:

```bash
curl localhost:8001/api/health
# Expected: {"status":"ok"}
```

Then confirm export route is registered:

```bash
curl -I localhost:8001/api/export
# Expected: HTTP 200 or HTTP 404 (if no corpus) — not HTTP 404 "Not Found" from routing
# A 404 with body {"error": "No corpus found..."} means the route is wired correctly
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/main.py
git commit -m "feat: add GET /api/export endpoint — returns Obsidian zip"
```

---

## Task 3: Frontend export button

**Files:**
- Modify: `frontend/src/lib/api.js`
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Add `exportZip` to `frontend/src/lib/api.js`**

Add this entry to the `api` object (after the `chat` entry):

```javascript
exportZip: () => fetch(`${BASE}/api/export`).then(async res => {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const e = await res.json(); msg = e.error || msg; } catch {}
    throw new Error(msg);
  }
  return res.blob();
}),
```

- [ ] **Step 2: Add export state variables to `+page.svelte`**

In the `<script>` block, after the `let activeTab = 'consensus';` line, add:

```javascript
// --- Export ---
let exporting = false;
let exportError = null;
```

- [ ] **Step 3: Add `handleExport` function to `+page.svelte`**

In the `<script>` block, after the `closeSidebar` function, add:

```javascript
async function handleExport() {
  exporting = true;
  exportError = null;
  try {
    const blob = await api.exportZip();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'discourse-export.zip';
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    exportError = e.message;
  } finally {
    exporting = false;
  }
}
```

- [ ] **Step 4: Add Export button to the results top bar in `+page.svelte`**

Find this block in the results phase HTML (around line 184):

```html
<header class="results-bar">
  <span class="results-topic">{currentTopic}</span>
  <span class="results-meta">{points.length} points · {[...new Set(points.map(p => p.cluster_id))].length} clusters</span>
  <button class="new-btn" on:click={resetToInput}>New analysis</button>
</header>
```

Replace it with:

```html
<header class="results-bar">
  <span class="results-topic">{currentTopic}</span>
  <span class="results-meta">{points.length} points · {[...new Set(points.map(p => p.cluster_id))].length} clusters</span>
  {#if exportError}
    <span class="export-error">{exportError}</span>
  {/if}
  <button class="export-btn" on:click={handleExport} disabled={exporting}>
    {exporting ? 'Exporting…' : 'Export'}
  </button>
  <button class="new-btn" on:click={resetToInput}>New analysis</button>
</header>
```

- [ ] **Step 5: Add styles for the new elements in `+page.svelte`**

Inside the `<style>` block, after the `.new-btn:hover` rule, add:

```css
.export-btn {
  background: none;
  border: 1px solid #2a2a40;
  border-radius: 5px;
  color: #666;
  font-size: 0.75rem;
  padding: 5px 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.1s, color 0.1s;
}
.export-btn:hover:not(:disabled) { background: #15151f; color: #c8c8d8; }
.export-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.export-error {
  font-size: 0.72rem;
  color: #ff6b6b;
  white-space: nowrap;
}
```

- [ ] **Step 6: Verify in browser**

With both servers running, load a completed analysis. Confirm:
- "Export" button appears in the top bar next to "New analysis"
- Clicking it briefly shows "Exporting…"
- Browser download dialog / auto-download triggers a `.zip` file

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/routes/+page.svelte
git commit -m "feat: add Export button — downloads Obsidian canvas + vault zip"
```

---

## Task 4: Chat panel retry button

**Files:**
- Modify: `frontend/src/components/ChatPanel.svelte`

- [ ] **Step 1: Add `lastQuery` variable in `ChatPanel.svelte`**

In the `<script>` block, change:

```javascript
let query = '';
let loading = false;
let answer = null;
let citations = [];
let error = null;
```

To:

```javascript
let query = '';
let lastQuery = '';
let loading = false;
let answer = null;
let citations = [];
let error = null;
```

- [ ] **Step 2: Store `lastQuery` before submitting in `ChatPanel.svelte`**

In the `submit` function, change:

```javascript
async function submit(q) {
  if (!q.trim() || loading) return;
  query = q;
  loading = true;
```

To:

```javascript
async function submit(q) {
  if (!q.trim() || loading) return;
  query = q;
  lastQuery = q;
  loading = true;
```

- [ ] **Step 3: Add retry button to the error state in `ChatPanel.svelte`**

Find this block in the template:

```html
{:else if error}
  <div class="error">{error}</div>
```

Replace it with:

```html
{:else if error}
  <div class="error">{error}</div>
  <button class="retry-btn" on:click={() => submit(lastQuery)}>Try again</button>
```

- [ ] **Step 4: Add retry button style in `ChatPanel.svelte`**

Inside the `<style>` block, after the `.error` rule, add:

```css
.retry-btn {
  margin-top: 8px;
  background: #1e1e2e;
  border: 1px solid #2e2e44;
  border-radius: 5px;
  color: #888;
  font-size: 0.75rem;
  padding: 5px 12px;
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
}
.retry-btn:hover { background: #28283e; color: #c8c8d8; }
```

- [ ] **Step 5: Verify in browser**

With the backend stopped (to force a chat error), submit a question and confirm:
- Red error text appears
- "Try again" button appears below it
- Clicking "Try again" re-submits the same query

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChatPanel.svelte
git commit -m "feat: add retry button to chat panel error state"
```

---

## Verification Checklist

Run these after all tasks are complete:

- [ ] `pytest tests/test_export.py -v` — all tests pass
- [ ] Click Export on a completed analysis — downloads a valid `.zip`
- [ ] Unzip and open `cluster-map.canvas` in Obsidian — cards appear, color-coded by cluster
- [ ] Open `vault/` as Obsidian vault — `_index.md` links to article notes
- [ ] Run a Dataview query in Obsidian: `TABLE cluster, domain FROM "vault" SORT publish_date` — returns rows
- [ ] Trigger a chat error and confirm "Try again" button appears and works
- [ ] `git log --oneline -6` shows 4 clean commits for this stage
