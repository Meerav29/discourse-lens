# discourse-lens

Discourse Lens takes a topic, reads ~100 relevant articles from the web, and maps the conversation: which camps exist, how coverage has moved over time, which articles don't fit, and what each camp talks about. You can then ask questions answered only from those articles. Everything runs locally except web search and the Claude API calls.

---

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ (Vite 8)
- A [Brave Search API key](https://brave.com/search/api) (free tier: 2000 queries/month), or a self-hosted [SearXNG](https://docs.searxng.org) instance with the JSON format enabled (`SEARCH_PROVIDER=searxng`, `SEARXNG_URL=http://localhost:8888`)
- An [Anthropic API key](https://console.anthropic.com) (for chat and cluster labelling)

---

## Setup

**1. Clone and install Python dependencies**

```bash
git clone https://github.com/Meerav29/discourse-lens.git
cd discourse-lens
uv sync                        # creates .venv from uv.lock
uv run playwright install chromium
```

Using Vertex AI for Claude? `uv sync --extra vertex` instead.

**2. Build the frontend**

```bash
cd frontend
npm install
npm run build
cd ..
```

Embeddings run in-process with [fastembed](https://github.com/qdrant/fastembed) (nomic-embed-text v1.5, no GPU or PyTorch needed). The first map downloads the model once (about 520 MB) to `data/models`. Already running [Ollama](https://ollama.com)? `EMBEDDING_MODE=ollama` uses its `nomic-embed-text` instead. It's the same model with the same vectors, so maps work with either. `EMBEDDING_MODE=openai` uses OpenAI's API, but maps made that way can only be searched with OpenAI.

**3. Configure API keys**

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Open `.env` and set:

```
BRAVE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

---

## Running

```bash
uv run uvicorn backend.api.main:app --port 8001
```

Then open [http://localhost:8001](http://localhost:8001). The backend serves the built app and the API from one address.

**No API keys yet?** Load a small synthetic demo map to explore the interface:

```bash
uv run python -m scripts.seed_demo
```

### Working on the frontend

Run the backend as above, plus the Vite dev server with hot reload (it forwards `/api` to port 8001):

```bash
cd frontend
npm run dev
```

and open [http://localhost:5173](http://localhost:5173). After changing the backend API, regenerate the typed client:

```bash
uv run python -m scripts.export_openapi
cd frontend && npm run gen:api
```

How answers are found: `backend/synthesis/chat.py` (hybrid search: vector similarity plus BM25 keyword search, fused by reciprocal rank).

How maps are built: `backend/topics.py` (article vectors → UMAP → HDBSCAN → c-TF-IDF, BERTopic's recipe without PyTorch) and `backend/embedding/project.py` (naming topics with Claude).

Checks (CI runs all of these on every push and pull request):

```bash
uv run ruff check backend tests scripts
uv run pytest
cd frontend && npm run check && npm run lint && npx vitest run
```

End-to-end tests drive the real app (backend + built frontend) against the demo map in a throwaway `.e2e/` folder, with no network or API keys:

```bash
cd frontend && npm run build && npx playwright install chromium && npm run test:e2e
```

---

## Using it

1. On the home page, type a topic (e.g. `mechanistic interpretability in large language models`) and choose **Map this topic**. Tick **Let me check the sources before they're read** to see the searches and pages first: edit the searches, untick pages, or add your own before anything is read.
2. A map takes **3–8 minutes**. Academic publishers often block automated reading; for those pages (and for PDF links) Discourse Lens looks up an open-access copy or the abstract through OpenAlex and Europe PMC, and the article reader says where the text came from. You'll see each step as it happens: the search queries, pages crawled, articles kept or skipped (and why), and clusters as they're named. You can leave the page, or **Cancel this map**.
3. When it's done you get six views of the same map:
   - **Map**: articles that make similar arguments sit close together, grouped into topics (camps) with contour lines and a name for each. Switch to **Table** for a plain list.
   - **Timeline**: articles per month or year, by cluster.
   - **Outliers**: articles furthest from the middle of their cluster.
   - **Key terms**: each topic's one-line summary and the words it uses far more than the others.
   - **Claims**: the points two or more articles take a position on, and whether each article agrees, qualifies or disputes them, with the most debated first. Click a point to see each article's claim and open the article. This view runs only when you choose **Find claims**, because it costs Claude requests: about half a cent per article (roughly $0.30 for a 50-article map; about a minute).
   - **Ask**: questions answered only from this map's articles. Answers stream in as they're written, with numbered citations like **[3]**; click one to read that article. Follow-up questions build on earlier answers, and a citation number means the same article for the whole conversation. Conversations are saved with the map.
4. Pick a topic in the **Clusters** panel to focus every view on it (and read its summary). Articles that don't fit any topic well are grouped as **Unclustered** rather than forced into one. Click any article to read it in a side panel. The address bar keeps the view, cluster and open article, so links and reloads land in the same place.
5. **Export to Obsidian** downloads a vault: a Canvas of the map plus one note per article.
6. Every map is kept. **All maps** returns to the list, where you can open or delete them.

---

## Good topics to start with

| Topic | Why it works well |
|---|---|
| `mechanistic interpretability in large language models` | Rich, active discourse, clear camps |
| `longevity science and aging reversal` | Strong consensus vs. fringe split |
| `urban heat islands and city design` | Good temporal drift, recent policy debate |
| `jevons paradox and energy efficiency` | Older topic, good for testing the temporal view |

Avoid topics that are too broad (`AI`, `climate change`) or too narrow (fewer than ~20 articles exist on the web).

---

## Troubleshooting

**Don't want the open-access lookups?** Set `RECOVER_ACADEMIC=false` in `.env`; academic pages a publisher blocks are then skipped.

**Pipeline stalls at "Crawling"** — Check your `BRAVE_API_KEY` in `.env`.

**Cluster labels show as "cluster 0", "cluster 1"...** — The Anthropic API call for labelling failed. Check your `ANTHROPIC_API_KEY`.

**Embeddings are slow** — Local embedding runs on the CPU: about 3 seconds per 10 chunks, so a few minutes for a typical map. For speed, set `EMBEDDING_MODE=openai` and `OPENAI_API_KEY=your_key` in `.env` (new maps only; see Setup).

**Answers are slow to start or too brief** — `CHAT_EFFORT` in `.env` sets how much the model reasons before answering (`low`, `medium` (default), `high`). In testing, `medium` started answering in about a second, same as `low`.

**Chat says "This analysis has no indexed corpus yet"** — The analysis hasn't completed, or no articles passed the quality filter. Try re-running with a different topic.

**Upgrading from an older version** — On first start the backend migrates the database. Maps made before topic modelling keep their old clusters, without key terms or summaries, until you rebuild them from the stored embeddings (no re-crawl; one Claude request per map):

```bash
uv run python -m scripts.recluster --all
```

The very first migration (from the single-corpus version) copies `data/discourse.db` and `data/vectors/` to `*.v1.bak`; delete those once you're happy.
