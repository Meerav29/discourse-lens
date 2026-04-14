# discourse-lens

Discourse Lens takes a topic string as input, crawls ~100 relevant articles from the web, and surfaces patterns in the discourse through semantic visualization. You get four views — a cluster map, temporal drift, outlier finder, and a chat interface — all running locally.

---

## Requirements

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) (for local embeddings) — or an OpenAI API key
- A [Brave Search API key](https://brave.com/search/api) (free tier: 2000 queries/month)
- An [Anthropic API key](https://console.anthropic.com) (for chat and cluster labelling)

---

## Setup

**1. Clone and install Python dependencies**

```bash
git clone https://github.com/Meerav29/discourse-lens.git
cd discourse-lens
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

**2. Install frontend dependencies**

```bash
cd frontend
npm install
cd ..
```

**3. Pull the embedding model** (skip if using OpenAI)

```bash
ollama pull nomic-embed-text
```

**4. Configure API keys**

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

Open two terminals.

**Terminal 1 — Backend:**

```bash
source venv/Scripts/activate   # Windows Git Bash / source venv/bin/activate on Mac/Linux
python -m uvicorn backend.api.main:app --reload --port 8001
```

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Using it

1. Type a topic into the input field (e.g. `mechanistic interpretability in large language models`) and click **Analyze Discourse**
2. The pipeline runs in the background — crawling, embedding, and clustering ~100 articles. This takes **3–8 minutes** depending on your connection and machine
3. A progress bar shows the current stage. Once complete, four panels appear:
   - **Cluster Map** — semantic clusters of the discourse, plotted in 2D
   - **Outliers** — articles furthest from any cluster centroid
   - **Temporal Drift** — how the discourse has shifted over time
   - **Consensus / Ask** — cluster breakdown by article count, and a chat interface to ask questions about the indexed corpus
4. Click any point on the cluster map to open the source article. Click a cluster to filter the outlier panel. Use the **Ask** tab to query the corpus with natural language
5. Click **Export** in the top bar to download an Obsidian-compatible zip — a Canvas file with all articles plotted at their UMAP positions, and a vault folder with one Markdown note per article

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

**Pipeline stalls at "Crawling"** — Check your `BRAVE_API_KEY` in `.env`.

**Cluster labels show as "cluster 0", "cluster 1"...** — The Anthropic API call for labelling failed. Check your `ANTHROPIC_API_KEY`.

**Embeddings are slow** — You're running Ollama on CPU. Switch to OpenAI embeddings by setting `EMBEDDING_MODE=openai` and `OPENAI_API_KEY=your_key` in `.env`.

**Chat returns "No corpus indexed yet"** — The analysis hasn't completed, or no articles passed the quality filter. Try re-running with a different topic.
