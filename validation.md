# Discourse Lens — Validation Guide

How to check that Discourse Lens works: the automated checks first, then a real map built step by step through the API, with what to look for at each stage.

---

## 1. Automated checks

These need no API keys and no network. CI runs all of them on every push and pull request.

```bash
uv run ruff check backend tests scripts   # lint
uv run pytest                              # backend: ~130 tests
cd frontend
npm run check && npm run lint              # types and formatting
npx vitest run                             # frontend unit tests
npm run build && npm run test:e2e          # browser tests against the demo map
```

The browser tests start their own backend on port 8011 with a throwaway `.e2e/` data folder, so they never touch your maps.

---

## 2. Look around without keys

```bash
uv run python -m scripts.seed_demo         # add --reset to rebuild it
uv run uvicorn backend.api.main:app --port 8001
```

Open [http://localhost:8001](http://localhost:8001) and open **Demo: urban heat and city design**. It has 12 made-up articles in three topics plus one unclustered article, a saved conversation and two claims. Every view should render; Ask can show the saved conversation but can't answer new questions without keys.

---

## 3. Build a real map

With `BRAVE_API_KEY` and `ANTHROPIC_API_KEY` in `.env` and the backend running:

```bash
curl -X POST localhost:8001/api/analyses \
  -H "Content-Type: application/json" \
  -d '{"topic": "mechanistic interpretability in large language models"}'
```

**Windows PowerShell:**

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8001/api/analyses `
  -ContentType "application/json" `
  -Body '{"topic": "mechanistic interpretability in large language models"}'
```

The response is the new analysis; keep its `id`. Add `"review": true` to pause after searching (see [Source review](#source-review)).

### Watch it run

```bash
curl localhost:8001/api/analyses/<id>            # status, progress (0-100), stage_detail
curl localhost:8001/api/analyses/<id>/events     # every step so far
```

The app shows the same feed live (it streams `/api/analyses/<id>/stream`). `status` moves through:

| Status | Progress | What is happening |
|---|---|---|
| `queued` | 0 | Created, about to start |
| `crawling` | 0–55 | Claude writes 6 search queries, the search provider runs them, then pages are loaded |
| `reviewing` | 10 | Only with `"review": true`: waiting for you to approve pages |
| `processing` | 55–68 | Extracting text, recovering blocked academic pages, dropping duplicates, chunking |
| `embedding` | 68–88 | Embedding chunks into LanceDB |
| `projecting` | 88–99 | Topic model, map layout, one Claude request to name the topics |
| `done` | 100 | Finished; `article_count` is the number of articles on the map |
| `error` / `cancelled` | | `error_msg` says what went wrong |

A map takes 3 to 8 minutes. Cancel with `curl -X POST localhost:8001/api/analyses/<id>/cancel`.

### Check each stage

These use Python's built-in `sqlite3`, so no extra tools are needed. Replace `<id>` in each.

```bash
uv run python - <<'EOF'
import sqlite3
db = sqlite3.connect("data/discourse.db")
a = "<id>"
q = lambda sql: db.execute(sql, (a,)).fetchall()

print("articles by status:", q("SELECT status, COUNT(*) FROM articles WHERE analysis_id=? GROUP BY status"))
print("recovered:", q("SELECT source_note, COUNT(*) FROM articles WHERE analysis_id=? AND source_note IS NOT NULL GROUP BY source_note"))
print("chunks (unique, duplicate):", q("SELECT SUM(is_duplicate=0), SUM(is_duplicate=1) FROM chunks WHERE analysis_id=?"))
print("placed on the map:", q("SELECT COUNT(*) FROM placements WHERE analysis_id=?"))
print("topics:", q("SELECT cluster_id, label, article_count FROM clusters WHERE analysis_id=? ORDER BY cluster_id"))
print("unclustered:", q("SELECT COUNT(*) FROM placements WHERE analysis_id=? AND cluster_id=-1"))
EOF
```

What good looks like:

- **Ingestion:** 40 or more articles with status `ok`. `filtered` pages were too short, not English or unreadable; `duplicate` ones repeated another article. On academic topics, some articles have a `source_note` such as "Full text from Europe PMC".
- **Chunks:** usually a few thousand unique chunks (around 50 per article).
- **Map:** every `ok` article has a placement. 2 to 8 topics, each with a short descriptive name (not a list of words, which means naming fell back to key terms), plus a handful unclustered at most.
- **Vectors:** `data/vectors/` contains a table named `emb_<id without dashes>`.

Over the API, `GET /api/analyses/<id>/articles` returns each article's position and topic, and `GET /api/analyses/<id>/clusters` returns topic names, summaries and key terms.

### Source review

Create the analysis with `"review": true`. When `status` is `reviewing`:

```bash
curl localhost:8001/api/analyses/<id>/plan       # {queries, results[{url, title, snippet, query}]}
```

In the app, untick a group and add one of your own addresses, then **Read N pages**. The events should say `Approved N pages`, then `Crawling N pages` with the same N. Titles and snippets should be plain text (no `&#x27;` or `<strong>`).

---

## 4. Check the views

Open the map in the app and go through each view:

- **Map:** dots grouped by topic with contour lines and names. Drag, zoom, click a dot to open the reader. **Table** lists every article.
- **Clusters panel:** picking a topic fades the others in every view and shows its summary; the address bar gains `?cluster=`.
- **Timeline:** bars per year or month, coloured by topic.
- **Outliers:** articles sorted by distance from their topic's centre.
- **Key terms:** one block per topic with a summary and weighted terms.
- **Claims:** choose **Find claims** (about half a cent per article). Progress shows "Read N of M articles", then "Comparing N claims". When it's done, each point has a bar and counts, the most debated first; expanding one lists each article's claim, and clicking an article opens it.
- **Ask:** ask a question. Sources appear first, then the answer streams in with numbered citations; a citation and the punctuation after it never split across lines. Clicking a citation opens that article. Ask a follow-up: new sources continue the numbering. Reload: the conversation is still there.
- **Export to Obsidian:** downloads `discourse-<topic>.zip` containing `discourse-<topic>/cluster-map.canvas` and `discourse-<topic>/vault/` (an `_index.md` plus one note per article). Opening the canvas in Obsidian shows article cards coloured by topic, laid out like the map.
- **Theme:** the moon/sun button switches dark and light, and the choice survives a reload.

---

## Troubleshooting

**Fails or finds nothing while searching** — Check `BRAVE_API_KEY` (or `SEARXNG_URL`) in `.env`, and your Brave quota.

**`article_count` is 0 after `done`** — Every page was filtered. Try a topic with more coverage on the web.

**Fails while embedding** — With `EMBEDDING_MODE=fastembed`, the first run downloads the model (about 520 MB); check your connection and disk space. With `ollama`, confirm Ollama is running and `nomic-embed-text` is pulled. With `openai`, check `OPENAI_API_KEY`.

**Topic names are lists of words** — Naming with Claude failed and the app fell back to key terms. Check `ANTHROPIC_API_KEY`; `uv run python -m scripts.recluster <id>` renames without re-crawling.

**Ask says the map was embedded with a different model** — The map's vectors came from another `EMBEDDING_MODE`; the message says which one to set.
