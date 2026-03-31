# Discourse Lens — Personal Sanity Check
Last updated: v1.0

---

## What We're Building (Plain English)

You type a topic. The tool searches the web, reads ~100 articles, and builds a semantic map of the whole discourse. You get four views:

- **Cluster map** — what camps / schools of thought exist
- **Temporal drift** — how the topic has evolved over time
- **Outlier finder** — the genuinely novel or fringe takes
- **Chat interface** — ask questions, get answers with cited sources

Everything runs locally. No accounts, no cloud infra beyond API calls.

> **The insight:** most research tools help you *retrieve*. This one helps you *orient*. It answers "what is the shape of this conversation?" not just "what does this article say?"

---

## What's Running Where

| Thing | What it is | How to start it |
|-------|-----------|-----------------|
| FastAPI (Python) | Backend — all the heavy lifting | `uvicorn backend.api.main:app --reload` |
| SvelteKit (Node) | Frontend UI | `cd frontend && npm run dev` |
| SQLite | Stores articles + chunks as text | Auto-created at `data/discourse.db` |
| LanceDB | Stores embedding vectors | Auto-created at `data/vectors/` |
| Brave Search API | Finds articles to crawl | Get free key → brave.com/search/api |
| Anthropic API | Powers the chat synthesis | Your existing key |
| Ollama / nomic-embed-text | Turns text into vectors locally | `ollama pull nomic-embed-text` |

---

## The Six Stages

| Stage | Name | What gets built | Done when... |
|-------|------|----------------|--------------|
| 0 | Scaffold | Folder structure, env vars, health endpoint | `curl /health` returns 200 |
| 1 | Ingestion | Crawls ~100 articles from topic string | 70+ rows in `articles` table |
| 2 | Processing | Chunks + deduplicates article text | 300+ rows in `chunks` table |
| 3 | Embedding | Embeds chunks, runs UMAP, labels clusters | Scatter plot shows distinct clusters |
| 4 | Visualization | All 4 views working in browser | Cross-view filtering works |
| 5 | Synthesis | RAG chat answers questions with citations | Chat cites 3+ articles |
| 6 | Polish | Progress bars, error handling, export | You'd show this to someone |

**Current stage:** `[ fill this in ]`

---

## Decisions That Are Locked

Don't let Claude Code or yourself relitigate these. They're in the spec for good reasons.

| Decision | Why it's locked |
|----------|----------------|
| UMAP runs server-side in Python | Browser UMAP is slow and inconsistent for 200+ points |
| Two-level chunking (1500 parent / 300 child) | Small chunks for retrieval precision, large context for LLM |
| LanceDB for vectors, SQLite for everything else | Zero infra, no Postgres, no Redis — keep it simple |
| Frontend never calls Anthropic directly | Security + easier to add auth later |
| Embedding mode is configurable via `EMBEDDING_MODE` | Free local (Ollama) or fast API (OpenAI) |
| No user accounts in v1 | Single active session. State lives in DB files. |

---

## Things That Will Probably Go Wrong

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Crawl gets < 50 articles | Paywalls, bot detection, dead links | Increase query count; add retry logic; use archive.org fallback |
| UMAP clusters look like a blob | Not enough articles or topic too broad | Try 150+ articles; narrow the topic string |
| Embeddings are slow | Running local model on CPU | Switch to `EMBEDDING_MODE=openai` temporarily |
| Publish dates all null | Sites don't use standard meta tags | Check URL slug extraction fallback in `metadata.py` |
| RAG answers are vague | Chunks too small or context window too short | Increase parent chunk size to 2000 tokens; raise `RAG_TOP_K` to 20 |
| D3 scatter is slow at 200+ nodes | Too many SVG DOM nodes | Switch cluster map to canvas renderer |

---

## How to Work with Claude Code

- Start each session: `"I am working on Stage N of Discourse Lens. Read PLANNING.md first."`
- Keep sessions focused on **one stage at a time** — context bleed causes drift
- If Claude Code suggests a different tech choice, ask it to justify against the spec before agreeing
- Always run the stage verification command before moving to the next stage
- If something breaks, share the error message **and** the relevant section of `PLANNING.md` together

---

## API Keys

| Key | Where to get it | Free tier? | Status |
|-----|----------------|-----------|--------|
| `BRAVE_API_KEY` | brave.com/search/api | Yes — 2000 queries/month | `[ ]` |
| `ANTHROPIC_API_KEY` | console.anthropic.com | No — pay per token | `[ ]` |
| `OPENAI_API_KEY` | platform.openai.com | No — optional anyway | `[ ]` |

---

## Session Checklist

**Before each session:**
- [ ] Backend running? (`uvicorn backend.api.main:app --reload`)
- [ ] Frontend running? (`cd frontend && npm run dev`)
- [ ] Which stage am I on?
- [ ] Did I verify the previous stage's output?

**After each session:**
- [ ] Run the stage verification command
- [ ] `git commit -m "Stage N complete: [what works]"`
- [ ] Note anything surprising — it will matter later

---

## Good Test Topics

Start with these — they have clear discourse structure and good web coverage.

| Topic string | Why it's good |
|---|---|
| `mechanistic interpretability in large language models` | Rich, active, 2022–present, clear camps |
| `longevity science and aging reversal` | Lots of camps, clear consensus vs. fringe |
| `urban heat islands and city design` | Good temporal drift, recent policy debate |
| `jevons paradox and energy efficiency` | Older topic, good for testing temporal view |

**Avoid:** Topics too broad (`AI`, `climate change`) or too narrow (< 20 articles exist). The sweet spot is a specific sub-topic with 50–200 good articles.