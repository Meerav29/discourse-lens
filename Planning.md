# Discourse Lens — Full Project Documentation
> Research Intelligence Tool | v1.0

---

## Table of Contents
1. [Product Overview](#1-product-overview)
2. [Product Requirements Document](#2-product-requirements-document-prd)
3. [System Architecture](#3-system-architecture)
4. [Data Models](#4-data-models)
5. [API Reference](#5-api-reference)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Environment Setup](#7-environment-setup)
8. [Instructions for Claude Code](#8-instructions-for-claude-code)

---

## 1. Product Overview

Discourse Lens takes a topic string as input, automatically crawls and indexes ~100 relevant articles from the web, and surfaces patterns in the discourse through semantic visualization. The goal is to give a researcher a full map of a topic in under 10 minutes — showing not just what is being said, but how the conversation is structured, where the consensus lies, what has changed over time, and what is being underexplored.

**Core loop:** type a topic → wait ~5 minutes → explore a living semantic map of the discourse.

### 1.1 Problem Statement

Reading deeply on a new topic currently requires hours of manual research. You open 30 tabs, read 15 articles, and still feel like you might be missing the key debates. Existing tools (Google, Perplexity, NotebookLM) help you retrieve and summarize, but none give you a birds-eye structural view of the full discourse — who is saying what, what camps exist, and where the genuinely novel ideas live.

### 1.2 Target Users

- Researchers exploring a new domain
- Journalists looking for angles that haven't been written
- Writers who want to understand the full landscape before publishing
- Analysts who need to get up to speed on a topic fast

### 1.3 Core Views (MVP)

| View | What it shows | Primary use case |
|------|--------------|-----------------|
| Cluster map | UMAP scatter of all articles, colored by semantic cluster | Orient in an unfamiliar topic |
| Temporal drift | How the semantic centroid of the discourse shifts month by month | Track how a topic has evolved |
| Outlier finder | Articles ranked by distance from the cluster centroid | Find novel / fringe takes |
| Consensus detector | Claims that appear across many articles vs. few | Identify received wisdom vs. debate |

---

## 2. Product Requirements Document (PRD)

### 2.1 Goals

- **G1:** A user can go from topic string to fully indexed, visualized corpus in under 10 minutes
- **G2:** The cluster map must handle 50–200 articles without performance degradation
- **G3:** All four views must be available and interlinked (clicking a cluster filters the outlier list, etc.)
- **G4:** The LLM synthesis layer must be able to answer natural language questions about the corpus
- **G5:** The tool must run fully locally — no cloud infrastructure required beyond API calls

### 2.2 Non-Goals (v1)

- No user accounts or saved sessions (local state only)
- No real-time crawling updates after initial index
- No multi-topic comparison (single topic per session)
- No PDF or video ingestion (web articles only)
- No mobile support

### 2.3 Functional Requirements

#### FR1 — Ingestion
1. User enters a topic string in the UI
2. System generates 5–8 search queries from the topic using Claude
3. System crawls top 15–20 results per query via Brave Search API
4. Playwright scrapes each URL; Readability/trafilatura extracts clean article text
5. Articles under 200 words or non-English are filtered out
6. Deduplicated corpus stored to SQLite

#### FR2 — Processing
1. Each article is cleaned (unicode normalize, collapse whitespace, strip boilerplate)
2. Two-level chunking: parent chunks ~1500 tokens, child chunks ~300 tokens with 50-token overlap
3. MinHash deduplication run on child chunks (threshold: 0.85 Jaccard similarity)
4. All chunks stored with metadata: `url`, `domain`, `publish_date`, `parent_id`, `chunk_index`

#### FR3 — Embedding & Storage
1. Child chunks embedded with `nomic-embed-text` (local) or `text-embedding-3-small` (API)
2. Vectors stored in LanceDB with full metadata
3. UMAP projection pre-computed server-side (Python) and stored as 2D coordinates
4. Cluster labels generated via k-means (k=5–10, auto-selected by silhouette score)

#### FR4 — Visualization
1. Cluster map: D3 force-directed scatter, nodes colored by cluster, size by article word count
2. Hover reveals article title, domain, date; click opens article sidebar
3. Temporal drift: animated centroid path overlaid on scatter, scrubable time slider
4. Outlier finder: ranked list sorted by `distance_from_centroid`, with semantic diff summary
5. Consensus detector: term/claim frequency bar chart, colored by how many clusters it appears in
6. Cross-view filtering: clicking a cluster in map filters the outlier list

#### FR5 — LLM Synthesis
1. Chat interface accepts natural language questions about the corpus
2. RAG retrieval over LanceDB returns top-k child chunks; parent context passed to Claude
3. Preset queries: "Summarize the main camps", "What is underexplored?", "What has changed recently?"
4. Responses cite specific articles with links

### 2.4 Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Ingestion time (100 articles) | < 8 minutes |
| Embedding time (100 articles) | < 3 min (local) / < 1 min (API) |
| UMAP computation | < 30 seconds |
| UI render (200 nodes) | < 2 seconds initial load |
| RAG query response | < 5 seconds |
| Storage footprint (100 articles) | < 200MB |

---

## 3. System Architecture

### 3.1 Repository Structure

```
discourse-lens/
├── backend/
│   ├── ingestion/
│   │   ├── search.py          # Brave API query generation + search
│   │   ├── crawler.py         # Playwright scraping
│   │   └── extractor.py       # trafilatura + cleaning
│   ├── processing/
│   │   ├── chunker.py         # Two-level chunking
│   │   ├── dedup.py           # MinHash deduplication
│   │   └── metadata.py        # Date extraction, domain parsing
│   ├── embedding/
│   │   ├── embed.py           # nomic-embed or OpenAI embeddings
│   │   ├── store.py           # LanceDB read/write
│   │   └── project.py         # UMAP + k-means clustering
│   ├── synthesis/
│   │   ├── rag.py             # Retrieval + context assembly
│   │   └── prompts.py         # All Claude prompt templates
│   ├── api/
│   │   └── main.py            # FastAPI app
│   └── db/
│       └── schema.sql         # SQLite schema
├── frontend/
│   ├── src/
│   │   ├── routes/
│   │   │   └── +page.svelte   # Main app shell
│   │   ├── components/
│   │   │   ├── ClusterMap.svelte
│   │   │   ├── TemporalDrift.svelte
│   │   │   ├── OutlierFinder.svelte
│   │   │   ├── ConsensusBars.svelte
│   │   │   ├── ArticleSidebar.svelte
│   │   │   └── ChatPanel.svelte
│   │   └── lib/
│   │       ├── d3helpers.js
│   │       └── api.js         # Frontend API client
│   └── package.json
├── data/                      # gitignored — DB and vector files live here
├── .env                       # gitignored
├── .env.example
├── requirements.txt
├── PLANNING.md                # this file
└── README.md
```

### 3.2 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Search | Brave Search API | Clean results, no Google auth complexity |
| Crawling | Playwright (Python) | Handles JS-rendered pages |
| Text extraction | trafilatura | Best-in-class boilerplate removal |
| Cleaning / chunking | Python + tiktoken | Accurate token counting |
| Deduplication | datasketch (MinHash) | Fast approximate dedup |
| Embeddings | nomic-embed-text (local) / text-embedding-3-small | Flexible: free local or fast API |
| Vector store | LanceDB | Zero infra, embedded, fast ANN |
| Relational store | SQLite | Simple, zero infra, sufficient at this scale |
| Dim reduction | umap-learn (Python, server-side) | Stable, well-tested |
| Clustering | scikit-learn k-means | Simple, explainable |
| API | FastAPI | Fast, async, auto-docs at /docs |
| Frontend | SvelteKit | Lightweight, reactive, great DX |
| Visualization | D3 v7 | Full control over scatter / animations |
| LLM | Claude API (`claude-sonnet-4-20250514`) | Best reasoning for synthesis |

### 3.3 Data Flow

```
User types topic
      │
      ▼
Claude generates 6 search queries
      │
      ▼
Brave Search API → 15-20 URLs per query → ~100 URLs total
      │
      ▼
Playwright scrapes each URL → raw HTML
      │
      ▼
trafilatura extracts clean text → filter short / non-English
      │
      ▼
SQLite: articles table
      │
      ▼
Two-level chunker → parent (1500 tok) + children (300 tok)
      │
      ▼
MinHash dedup → mark duplicates
      │
      ▼
SQLite: chunks table
      │
      ▼
Embed child chunks (batched, 32 at a time)
      │
      ▼
LanceDB: vectors table
      │
      ▼
UMAP (server-side Python) → 2D coords
k-means clustering → cluster_id, cluster_label
distance from centroid → outlier score
      │
      ▼
SQLite: projections table
      │
      ▼
FastAPI serves /api/corpus → SvelteKit + D3 renders views
      │
      ▼
User asks question → RAG retrieval → Claude → cited answer
```

---

## 4. Data Models

### 4.1 SQLite Schema

```sql
-- Articles: one row per crawled URL
CREATE TABLE articles (
  id           TEXT PRIMARY KEY,   -- sha256(url)[:16]
  url          TEXT NOT NULL UNIQUE,
  domain       TEXT,
  title        TEXT,
  publish_date TEXT,               -- ISO date string, nullable
  crawl_ts     INTEGER,            -- unix timestamp
  word_count   INTEGER,
  language     TEXT DEFAULT 'en',
  raw_text     TEXT,
  status       TEXT DEFAULT 'ok'   -- ok | filtered | error
);

-- Chunks: one row per child chunk
CREATE TABLE chunks (
  id           TEXT PRIMARY KEY,   -- {article_id}#p{i}c{j}
  article_id   TEXT REFERENCES articles(id),
  parent_id    TEXT,               -- {article_id}#p{i}
  parent_text  TEXT,               -- full parent chunk text (for RAG context)
  child_text   TEXT,
  chunk_index  INTEGER,
  token_count  INTEGER,
  is_duplicate INTEGER DEFAULT 0
);

-- Projections: 2D UMAP coords + cluster info per chunk
CREATE TABLE projections (
  chunk_id                TEXT PRIMARY KEY REFERENCES chunks(id),
  x                       REAL,
  y                       REAL,
  cluster_id              INTEGER,
  cluster_label           TEXT,    -- LLM-generated 2-3 word label
  distance_from_centroid  REAL
);

-- Jobs: track ingestion pipeline state
CREATE TABLE jobs (
  id           TEXT PRIMARY KEY,   -- uuid4
  topic        TEXT,
  status       TEXT,               -- queued | crawling | processing | embedding | projecting | done | error
  progress     INTEGER DEFAULT 0,  -- 0-100
  article_count INTEGER DEFAULT 0,
  error_msg    TEXT,
  created_ts   INTEGER,
  updated_ts   INTEGER
);
```

### 4.2 LanceDB Schema

Table name: `embeddings`

```python
{
  "chunk_id":    str,    # matches chunks.id in SQLite
  "article_id":  str,
  "vector":      list[float],  # 768-dim for nomic, 1536-dim for text-embedding-3-small
  "child_text":  str,
  "domain":      str,
  "publish_date": str,
  "cluster_id":  int
}
```

---

## 5. API Reference

All endpoints return `Content-Type: application/json`. Errors return `{ "error": string, "code": string }`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs` | Start ingestion. Body: `{ "topic": string }`. Returns: `{ "job_id": string }` |
| `GET` | `/api/jobs/:id` | Job status. Returns: `{ "status", "progress", "article_count", "error_msg" }` |
| `GET` | `/api/corpus` | All articles + projections for active session. Returns array of point objects |
| `GET` | `/api/clusters` | Cluster summaries + centroids. Returns: `[{ "id", "label", "size", "centroid_x", "centroid_y" }]` |
| `GET` | `/api/outliers?cluster_id=N` | Articles ranked by distance from centroid. Optional filter by cluster |
| `POST` | `/api/chat` | RAG query. Body: `{ "query": string }`. Returns: `{ "answer": string, "citations": [{ "url", "title", "domain" }] }` |
| `GET` | `/api/articles/:id` | Full article. Returns: `{ "id", "url", "title", "domain", "publish_date", "raw_text", "word_count" }` |
| `GET` | `/api/health` | Health check. Returns: `{ "status": "ok" }` |

### Corpus Point Object

```json
{
  "chunk_id": "abc123#p0c2",
  "article_id": "abc123",
  "url": "https://example.com/article",
  "title": "Article Title",
  "domain": "example.com",
  "publish_date": "2024-03",
  "x": 3.42,
  "y": -1.87,
  "cluster_id": 2,
  "cluster_label": "mechanistic circuits",
  "distance_from_centroid": 0.341,
  "word_count": 1840
}
```

---

## 6. Implementation Roadmap

> **Rule:** Each stage is independently testable. Do not start Stage N+1 until Stage N passes its verification command.

---

### Stage 0 — Project Scaffold
**Time estimate:** ~2 hours  
**Goal:** Repo exists, backend serves `/health`, frontend shell renders in browser.

**Tasks:**
- [ ] Init git repo, create full directory structure per Section 3.1
- [ ] `python -m venv venv && pip install -r requirements.txt`
- [ ] `npm create svelte@latest frontend` (choose skeleton, TypeScript: no, ESLint: yes)
- [ ] Create `.env` from `.env.example`, fill in API keys
- [ ] FastAPI `main.py` with single `GET /api/health` endpoint
- [ ] SvelteKit `+page.svelte` with topic input form (no logic yet)
- [ ] CORS configured so frontend on `:5173` can call backend on `:8000`
- [ ] `data/` directory created and added to `.gitignore`

**Verification:**
```bash
curl localhost:8001/api/health
# → {"status":"ok"}
# AND: browser at localhost:5173 shows input form without console errors
```

---

### Stage 1 — Ingestion Pipeline
**Time estimate:** ~4 hours  
**Goal:** Type a topic, get 70+ cleaned article rows in SQLite.

**Tasks:**
- [ ] `db/schema.sql` — create all four tables; `main.py` runs schema on startup
- [ ] `search.py` — call Claude to generate 6 diverse search queries from topic string
- [ ] `search.py` — call Brave Search API for each query, collect unique URLs (dedupe by URL)
- [ ] `crawler.py` — Playwright headless scrape, 10s timeout, skip URLs ending in `.pdf`
- [ ] `extractor.py` — trafilatura extract; filter: word_count < 200 OR language != 'en'
- [ ] `metadata.py` — extract publish_date: try `<meta>` tags → URL date slug → None
- [ ] `main.py` — `POST /api/jobs` triggers full pipeline as FastAPI `BackgroundTask`
- [ ] `main.py` — `GET /api/jobs/:id` returns current job status from DB

**Verification:**
```bash
# Start a job via API:
curl -X POST localhost:8001/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"topic": "mechanistic interpretability"}'

# Poll until done, then:
sqlite3 data/discourse.db "SELECT COUNT(*) FROM articles WHERE status='ok'"
# → 70 or more
```

---

### Stage 2 — Processing Pipeline
**Time estimate:** ~3 hours  
**Goal:** Chunks table populated with parent/child pairs, duplicates marked.

**Tasks:**
- [ ] `chunker.py` — tiktoken-based splitter; 1500-token parents with 100-token overlap; 300-token children with 50-token overlap
- [ ] `chunker.py` — chunk IDs follow format `{article_id}#p{i}c{j}`; parent_text stored on every child row
- [ ] `dedup.py` — MinHash LSH (128 permutations, threshold 0.85) on child chunks; mark `is_duplicate=1` for near-dupes
- [ ] Wire processing into the job pipeline after ingestion completes
- [ ] Update job status to `processing` while this runs

**Verification:**
```bash
sqlite3 data/discourse.db "SELECT COUNT(*) FROM chunks WHERE is_duplicate=0"
# → 300 or more

sqlite3 data/discourse.db "SELECT COUNT(*) FROM chunks WHERE is_duplicate=1"
# → some number > 0 (proves dedup is working)
```

---

### Stage 3 — Embedding & Projection
**Time estimate:** ~4 hours  
**Goal:** Projections table populated with x, y, cluster_id, cluster_label for every non-duplicate chunk.

**Tasks:**
- [ ] `embed.py` — batch embed child chunks (batch size 32); respect `EMBEDDING_MODE` env var
- [ ] `embed.py` — if `local`: call Ollama `nomic-embed-text`; if `openai`: call `text-embedding-3-small`
- [ ] `store.py` — write vectors to LanceDB with full metadata schema from Section 4.2
- [ ] `project.py` — load all vectors from LanceDB, run UMAP (`n_components=2`, `n_neighbors=15`, `min_dist=0.1`)
- [ ] `project.py` — k-means clustering; try k=5,7,10; pick k with highest silhouette score
- [ ] `project.py` — for each chunk, compute Euclidean distance to its cluster centroid
- [ ] `project.py` — call Claude once per cluster: pass top-10 chunks by centrality, ask for a 2–3 word label
- [ ] `project.py` — write x, y, cluster_id, cluster_label, distance to `projections` table
- [ ] `main.py` — implement `GET /api/corpus` returning full projection data joined with article metadata

**Verification:**
```bash
curl localhost:8001/api/corpus | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} points, clusters: {set(p[\"cluster_id\"] for p in d)}')"
# → "312 points, clusters: {0, 1, 2, 3, 4, 5, 6}" (numbers will vary)
```

---

### Stage 4 — Visualization Layer
**Time estimate:** ~6 hours  
**Goal:** All four views render correctly, cross-view filtering works.

**Tasks:**
- [ ] `api.js` — typed fetch wrapper for all API endpoints
- [ ] `ClusterMap.svelte` — D3 SVG scatter; nodes colored by `cluster_id`; size by `word_count`; zoom + pan; hover tooltip with title/domain/date; click dispatches `selectArticle` event
- [ ] `TemporalDrift.svelte` — group projections by `publish_date` month; compute monthly centroid; draw animated path; time range slider filters visible points
- [ ] `OutlierFinder.svelte` — list of articles sorted by `distance_from_centroid` DESC; shows cluster label + distance score; filters when cluster selected in map
- [ ] `ConsensusBars.svelte` — extract top 20 noun phrases per cluster using simple TF-IDF; horizontal bar chart colored by cluster; width = frequency
- [ ] `ArticleSidebar.svelte` — slides in on article click; shows title, date, domain, word count, first 500 chars of text, link to original URL
- [ ] `ChatPanel.svelte` — message thread; preset query buttons; citation links rendered below each answer
- [ ] `+page.svelte` — four-panel layout; shared `selectedCluster` and `selectedArticle` stores drive cross-view filtering

**Verification:**
- Open browser at `localhost:5173`
- All four views render without console errors on a real corpus
- Clicking a cluster in ClusterMap filters OutlierFinder to that cluster
- Clicking a node opens ArticleSidebar with correct article data

---

### Stage 5 — LLM Synthesis
**Time estimate:** ~3 hours  
**Goal:** Natural language questions answered with cited sources from the corpus.

**Tasks:**
- [ ] `rag.py` — embed user query; retrieve top-15 child chunks from LanceDB by cosine similarity
- [ ] `rag.py` — fetch `parent_text` for each retrieved chunk from SQLite (richer context)
- [ ] `rag.py` — assemble context: `[{url, title, domain, publish_date, text: parent_text}]`
- [ ] `prompts.py` — system prompt instructs Claude to: answer from context only, cite by URL, flag if answer is not in corpus
- [ ] `main.py` — `POST /api/chat` endpoint calls `rag.py` then Claude, returns `{ answer, citations }`
- [ ] `ChatPanel.svelte` — wire up to `/api/chat`; render citations as clickable links; add preset buttons: "What are the main camps?", "What is underexplored?", "What has changed over time?"

**Verification:**
```bash
curl -X POST localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the main camps in this debate?"}'
# → response where citations array has length >= 3
```

---

### Stage 6 — Polish & Robustness
**Time estimate:** ~4 hours  
**Goal:** The tool handles errors gracefully and feels finished enough to show someone.

**Tasks:**
- [ ] SSE endpoint `GET /api/jobs/:id/stream` — push progress updates to frontend in real time
- [ ] Progress bar UI showing pipeline stage: Searching → Crawling → Processing → Embedding → Projecting → Done
- [ ] Graceful error handling: failed scrapes logged but don't stop the pipeline; rate limit retries with backoff
- [ ] If < 30 articles scraped successfully, surface a warning with suggestions to broaden the topic
- [ ] Export button: download full corpus as `corpus.json` (all article metadata + projections)
- [ ] `README.md` with setup instructions, example topics, and screenshots

---

## 7. Environment Setup

### 7.1 Prerequisites

- Python 3.11+
- Node.js 20+
- Brave Search API key — [brave.com/search/api](https://brave.com/search/api) (free tier: 2000 queries/month)
- Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
- Optional: OpenAI API key (only needed if `EMBEDDING_MODE=openai`)
- Optional: [Ollama](https://ollama.ai) installed locally with `nomic-embed-text` pulled

### 7.2 requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
playwright==1.45.0
trafilatura==1.12.0
tiktoken==0.7.0
datasketch==1.6.5
langdetect==1.0.9
lancedb==0.9.0
umap-learn==0.5.6
scikit-learn==1.5.0
anthropic==0.34.0
openai==1.40.0
httpx==0.27.0
python-dotenv==1.0.1
```

### 7.3 .env.example

```bash
# Required
BRAVE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# Embeddings — choose one mode
EMBEDDING_MODE=local            # local | openai
OLLAMA_BASE_URL=http://localhost:11434
OPENAI_API_KEY=your_key_here    # only needed if EMBEDDING_MODE=openai

# Storage paths
DB_PATH=./data/discourse.db
LANCE_PATH=./data/vectors

# Optional tuning
MAX_ARTICLES=120                # cap on total articles to crawl
UMAP_N_NEIGHBORS=15
KMEANS_K=auto                   # auto | integer (e.g. 7)
RAG_TOP_K=15
```

### 7.4 First-Run Commands

```bash
# Clone and set up backend
git clone <repo>
cd discourse-lens
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Set up frontend
cd frontend && npm install && cd ..

# Copy and fill in env
cp .env.example .env
# → edit .env with your API keys

# If using local embeddings
ollama pull nomic-embed-text

# Start backend
uvicorn backend.api.main:app --reload --port 8001

# Start frontend (separate terminal)
cd frontend && npm run dev
# → open localhost:5173
```

---

## 8. Instructions for Claude Code

> This section is written to be used directly in Claude Code sessions.

### 8.1 How to Start Each Stage

Paste this at the start of each Claude Code session, replacing N:

```
I am building Discourse Lens, a research intelligence tool.
The full spec is in PLANNING.md — please read it before writing any code.
I am now working on Stage N: [stage name].
Implement Stage N exactly as specified. Do not implement anything from later stages.
Ask me before making any architectural decision not covered in the spec.
```

### 8.2 Invariants — Never Violate These

- **UMAP always runs server-side** (Python/`project.py`) — never in the browser
- **All embedding calls must be batched** at max 32 chunks at a time
- **Frontend never calls Anthropic directly** — always proxied through FastAPI
- **Chunk IDs must follow the format:** `{article_id}#p{parent_index}c{child_index}`
- **publish_date extraction has three fallbacks:** `<meta>` tag → URL date slug → `None` (never crash)
- **All API errors return:** `{ "error": string, "code": string }` — never raw stack traces
- **Data only lives in two places:** SQLite (`data/discourse.db`) and LanceDB (`data/vectors/`)

### 8.3 Stage Verification Commands

Run these after each stage before proceeding. Expected outputs are approximate.

```bash
# Stage 0
curl localhost:8001/api/health
# → {"status":"ok"}

# Stage 1
sqlite3 data/discourse.db "SELECT COUNT(*) FROM articles WHERE status='ok'"
# → 70+

# Stage 2
sqlite3 data/discourse.db "SELECT COUNT(*) FROM chunks WHERE is_duplicate=0"
# → 300+

# Stage 3
curl localhost:8001/api/corpus | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(len(d), 'points')"
# → 300+ points

# Stage 4
# Manual: open localhost:5173, verify all views render, test cross-filtering

# Stage 5
curl -X POST localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"what are the main camps in this debate?"}'
# → citations array length >= 3

# Stage 6
# Manual: run full pipeline on a new topic, verify progress bar and error handling
```

### 8.4 Suggested Test Topic

Use this topic for all development testing — it has rich, well-structured web coverage:

```
mechanistic interpretability in large language models
```

Other good test topics:
- `longevity science and aging reversal` — many camps, clear consensus vs. fringe
- `urban heat islands and city design` — good temporal drift, recent policy debate