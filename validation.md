# Discourse Lens — Validation Guide

This file explains how to run a fresh pipeline job and verify each completed stage.

---

## Prerequisites

```bash
# Activate the virtual environment (Windows/Git Bash)
source venv/Scripts/activate

# Start the backend (port 8001)
python -m uvicorn backend.api.main:app --reload --port 8001
```

The backend initialises the SQLite schema on startup — safe to restart at any time.

---

## Running a fresh job

If you want a clean slate before testing (e.g. to validate Stage 2 on a fresh corpus):

```bash
# Delete the existing database so all tables start empty
rm data/discourse.db
```

Then submit a new job:

```bash
curl -X POST localhost:8001/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"topic": "mechanistic interpretability in large language models"}'
```

**Windows PowerShell alternative:**

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/jobs `
  -ContentType "application/json" `
  -Body '{"topic": "mechanistic interpretability in large language models"}'
```

The response contains a `job_id`:

```json
{"job_id": "some-uuid-here"}
```

---

## Polling job status

```bash
curl localhost:8001/api/jobs/<job_id>
```

**Windows PowerShell alternative:**

```powershell
Invoke-RestMethod -Uri http://localhost:8001/api/jobs/<job_id>
```

The `status` field progresses through these values:

| Status | What is happening |
|--------|------------------|
| `queued` | Job created, not started yet |
| `crawling` | Generating search queries and scraping URLs |
| `processing` | Extracting text, chunking, deduplicating |
| `embedding` | Embedding non-duplicate chunks and writing to LanceDB |
| `projecting` | Running UMAP, k-means clustering, and labelling clusters |
| `done` | Pipeline complete |
| `error` | Something failed — check `error_msg` |

Poll every 10–15 seconds. The full pipeline typically takes 3–8 minutes depending on network speed and article count.

---

## Stage verification commands

Run these after the job reaches `status: "done"`.

### Stage 0 — Health check

```bash
curl localhost:8001/api/health
# Expected: {"status":"ok"}
```

**Windows PowerShell alternative:**

```powershell
Invoke-RestMethod -Uri http://localhost:8001/api/health
# Expected: status ok
```

### Stage 1 — Ingestion

```bash
sqlite3 data/discourse.db "SELECT COUNT(*) FROM articles WHERE status='ok';"
# Expected: 70 or more
```

To see a breakdown of all statuses:

```bash
sqlite3 data/discourse.db "SELECT status, COUNT(*) FROM articles GROUP BY status;"
```

### Stage 2 — Processing (chunking + deduplication)

```bash
# Unique (non-duplicate) child chunks — should be 300+
sqlite3 data/discourse.db "SELECT COUNT(*) FROM chunks WHERE is_duplicate=0;"

# Duplicate child chunks — should be > 0 (proves dedup ran)
sqlite3 data/discourse.db "SELECT COUNT(*) FROM chunks WHERE is_duplicate=1;"
```

To inspect a sample chunk:

```bash
sqlite3 data/discourse.db \
  "SELECT id, article_id, chunk_index, token_count, is_duplicate, substr(child_text,1,120) \
   FROM chunks LIMIT 5;"
```

To confirm parent/child structure is correct:

```bash
sqlite3 data/discourse.db \
  "SELECT article_id, COUNT(*) as total_chunks, \
          SUM(is_duplicate) as dupes \
   FROM chunks GROUP BY article_id LIMIT 10;"
```

### Stage 3 — Embeddings & projections

First confirm the job reached `status: "done"` with `embedding` and `projecting` stages completing (you can watch progress tick through 80% → 90% → 100% while polling).

**Check the projections table is populated:**

```bash
sqlite3 data/discourse.db "SELECT COUNT(*) FROM projections;"
# Expected: 300 or more rows
```

**Check cluster IDs are assigned (should see multiple distinct values):**

```bash
sqlite3 data/discourse.db \
  "SELECT cluster_id, cluster_label, COUNT(*) as chunks \
   FROM projections GROUP BY cluster_id ORDER BY cluster_id;"
# Expected: 5–10 rows, each with a 2-3 word label and a chunk count
```

**Check x/y coordinates look reasonable (should not all be 0.0):**

```bash
sqlite3 data/discourse.db \
  "SELECT MIN(x), MAX(x), MIN(y), MAX(y) FROM projections;"
# Expected: non-zero ranges spanning several units, e.g. -6.3 | 8.1 | -5.0 | 7.4
```

**Hit the /api/corpus endpoint and confirm shape:**

```bash
curl localhost:8001/api/corpus | python3 -c \
  "import sys,json; d=json.load(sys.stdin); \
   print(f'{len(d)} points, clusters: {set(p[\"cluster_id\"] for p in d)}')"
# Expected: 300+ points with multiple cluster IDs, e.g.:
# 412 points, clusters: {0, 1, 2, 3, 4, 5, 6}
```

**Windows PowerShell alternative:**

```powershell
$d = Invoke-RestMethod -Uri http://localhost:8001/api/corpus
Write-Host "$($d.Count) points"
$d | Select-Object -ExpandProperty cluster_id | Sort-Object -Unique
# Expected: 300+ points, several distinct cluster IDs listed
```

**Inspect a sample corpus point to confirm all fields are present:**

```bash
curl -s localhost:8001/api/corpus | python3 -c \
  "import sys,json; d=json.load(sys.stdin); import pprint; pprint.pprint(d[0])"
# Expected: dict with chunk_id, article_id, url, title, domain, publish_date,
#           x, y, cluster_id, cluster_label, distance_from_centroid, word_count
```

**Windows PowerShell alternative:**

```powershell
$d = Invoke-RestMethod -Uri http://localhost:8001/api/corpus
$d[0] | Format-List
# Expected: all fields listed above present on the first item
```

**Check LanceDB vectors directory was created:**

```bash
ls data/vectors/
# Expected: directory exists and contains LanceDB files (embeddings.lance/ etc.)
```

### Stage 6 — Polish (export + chat retry)

**Run the unit tests:**

```bash
source venv/Scripts/activate
pytest tests/test_export.py -v
# Expected: 12 passed
```

**Test the export endpoint directly:**

```bash
curl -o test-export.zip localhost:8001/api/export
# Expected: file downloads (non-zero size)
# If no corpus: {"error": "No corpus found. Run an analysis first."}

unzip -l test-export.zip
# Expected: entries like:
#   discourse-<topic>/cluster-map.canvas
#   discourse-<topic>/vault/_index.md
#   discourse-<topic>/vault/<article-slug>.md   (one per article)
```

**Windows PowerShell alternative:**

```powershell
Invoke-WebRequest -Uri http://localhost:8001/api/export -OutFile test-export.zip
# Then list the contents:
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::OpenRead("$PWD\test-export.zip").Entries | Select-Object FullName
# Expected: cluster-map.canvas, vault/_index.md, vault/<article-slug>.md entries
```

**Verify the canvas file is valid JSON:**

```bash
unzip -p test-export.zip "*/cluster-map.canvas" | python3 -c \
  "import sys, json; d=json.load(sys.stdin); \
   print(f'{len(d[\"nodes\"])} nodes, edges: {len(d[\"edges\"])}')"
# Expected: N nodes (one per article), 0 edges
```

**Verify a vault article has correct frontmatter:**

```bash
unzip -p test-export.zip "*/vault/_index.md" | head -20
# Expected: starts with "# <topic>", contains cluster table and [[wikilinks]]
```

**Test in Obsidian:**

1. Unzip the export
2. Open `cluster-map.canvas` in Obsidian — article cards should appear color-coded by cluster, spatially arranged by UMAP position
3. Open the `vault/` folder as an Obsidian vault — graph view should show `_index.md` linking to all article notes
4. Install the Dataview plugin and run: `TABLE cluster, domain FROM "vault" SORT publish_date` — should return rows with frontmatter fields

**Test chat retry:**

1. Stop the backend server
2. In the UI, submit a chat query — an error message should appear
3. A "Try again" button should appear below the error
4. Restart the backend and click "Try again" — query should re-submit successfully

---

## Useful ad-hoc queries

```bash
# Total tokens across all non-duplicate chunks
sqlite3 data/discourse.db \
  "SELECT SUM(token_count) FROM chunks WHERE is_duplicate=0;"

# Articles with the most chunks
sqlite3 data/discourse.db \
  "SELECT a.title, COUNT(c.id) as chunks \
   FROM chunks c JOIN articles a ON c.article_id=a.id \
   WHERE c.is_duplicate=0 \
   GROUP BY c.article_id ORDER BY chunks DESC LIMIT 10;"

# Duplicate rate per article
sqlite3 data/discourse.db \
  "SELECT article_id, \
          ROUND(100.0 * SUM(is_duplicate) / COUNT(*), 1) as dup_pct \
   FROM chunks GROUP BY article_id ORDER BY dup_pct DESC LIMIT 10;"
```

---

## Troubleshooting

**Job stuck at `crawling`** — Brave Search API key missing or quota exceeded. Check `.env` and `BRAVE_API_KEY`.

**`article_count` is 0 after `done`** — trafilatura filtered all articles. Try a broader topic with more web coverage.

**`chunks` table is empty after `done`** — The pipeline ran before Stage 2 was wired in. Delete the DB and run a fresh job.

**Job fails at `embedding` status** — If using `EMBEDDING_MODE=local`, confirm Ollama is running (`ollama serve`) and `nomic-embed-text` is pulled (`ollama pull nomic-embed-text`). If using `EMBEDDING_MODE=openai`, check `OPENAI_API_KEY` in `.env`.

**`projections` table is empty after `done`** — Embedding step may have produced no rows (check `data/vectors/` exists and has content). Also check `error_msg` on the job — UMAP requires at least `n_neighbors + 1` data points.

**Cluster labels are all `"cluster N"`** — Claude API call failed during labelling (likely missing or invalid `ANTHROPIC_API_KEY`). The projections are still valid; only the text labels fall back to the default.

**`sqlite3: command not found` (Windows)** — Use the SQLite CLI bundled with Git Bash, or install it via `winget install SQLite.SQLite`.
