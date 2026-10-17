# Discourse Lens — Personal Sanity Check
Last updated: October 2026, after the modernization (v0.2)

---

## What We're Building (Plain English)

You type a topic. The tool searches the web, reads ~100 articles, and builds a semantic map of the whole discourse. You get six views:

- **Map**: what camps / schools of thought exist, as named topics
- **Timeline**: how coverage has moved over time
- **Outliers**: the genuinely novel or fringe takes
- **Key terms**: what each camp talks about that the others don't
- **Claims**: where the sources agree, qualify or dispute each other
- **Ask**: questions answered only from the articles, with clickable citations

Everything runs locally. No accounts, no cloud infra beyond the search and Claude requests.

> **The insight:** most research tools help you *retrieve*. This one helps you *orient*. It answers "what is the shape of this conversation?" not just "what does this article say?"

---

## What's Running Where

| Thing | What it is | How to start it |
|-------|-----------|-----------------|
| FastAPI (Python) | Backend, and it serves the built app too | `uv run uvicorn backend.api.main:app --port 8001` |
| SvelteKit (Node) | Frontend UI, built into `frontend/build` | `cd frontend && npm run build` (or `npm run dev` on :5173 while editing) |
| SQLite | Maps, articles, chunks, claims, conversations | Auto-created at `data/discourse.db` |
| LanceDB | Embedding vectors, one table per map | Auto-created at `data/vectors/` |
| fastembed / nomic-embed-text | Turns text into vectors inside the app | Downloads itself once (~520 MB) to `data/models/` |
| Brave Search API (or SearXNG) | Finds articles to read | Free key at brave.com/search/api |
| Anthropic API | Queries, topic names, claims, answers | Your existing key |

---

## How It Was Built

The original six stages (scaffold → ingestion → processing → embedding → visualization → synthesis → polish) were finished in April 2026. In October 2026 it was overhauled in six steps (merged as PR #2):

| Step | What changed |
|------|--------------|
| 1 | Quality bug fixes: dedup, embedding prefixes, RAG ranking, outliers |
| 2 | Backend restructure: uv, many maps instead of one corpus, cancellable runs with a live feed |
| 3 | Frontend rebuilt: SvelteKit 3, Svelte 5, TypeScript, Tailwind 4 |
| 4 | Topic model: BERTopic's recipe without PyTorch, named topics with summaries |
| 5 | Ask: streaming answers, hybrid search, stable citations, saved conversations |
| 6 | Academic page recovery, source review, SearXNG, fastembed, Claims view, e2e tests + CI |

**Current state:** all done and merged to `main`.

---

## Decisions That Are Locked

Don't let Claude Code or yourself relitigate these. They're here for good reasons.

| Decision | Why it's locked |
|----------|----------------|
| UMAP and clustering run server-side in Python | Browser UMAP is slow and inconsistent |
| Cluster articles, not chunks | Chunk-level clustering just gave one topic per article |
| No PyTorch | BERTopic's recipe works without it; keeps installs small and CPU-only |
| Two-level chunking (1500 parent / 300 child) | Small chunks for retrieval precision, large context for the answer |
| LanceDB for vectors, SQLite for everything else | Zero infra, no Postgres, no Redis — keep it simple |
| Frontend never calls Anthropic directly | Keys stay on the server |
| Claims run only when asked | They cost Claude requests on every map |
| No user accounts | Local tool; state lives in the `data/` folder |

---

## Things That Will Probably Go Wrong

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Crawl keeps < 40 articles | Paywalls, bot detection, dead links | Academic pages are already recovered via OpenAlex / Europe PMC; try a broader topic or turn on source review and add pages |
| Map looks like one blob | Topic too broad or too few articles | Narrow the topic; articles that fit nowhere go to Unclustered on purpose |
| Embeddings are slow | Running on CPU | It's ~3 s per 10 chunks; `EMBEDDING_MODE=openai` is faster for new maps |
| Publish dates all null | Sites don't use standard meta tags | Check the URL fallback in `backend/processing/metadata.py` |
| Answers are vague | Not enough context | Raise `RAG_TOP_K`, or `CHAT_EFFORT=high` |
| Ask errors about a different model | Map made with another `EMBEDDING_MODE` | Set the mode the message names |
| A test passes on Windows but fails in CI | UMAP floating point differs by platform | Assert on the meaning, not exact labels |

---

## How to Work with Claude Code

- Start with: `"Read README.md and validation.md first."` They describe the current app; `Planning.md` is the original v1 plan.
- Keep sessions focused on **one change at a time**; context bleed causes drift
- If Claude Code suggests a different tech choice, ask it to justify it against the locked decisions above
- Run the checks in `validation.md` before calling something done
- If something breaks, share the error message **and** what you were doing

---

## API Keys

| Key | Where to get it | Free tier? | Status |
|-----|----------------|-----------|--------|
| `BRAVE_API_KEY` | brave.com/search/api | Yes — 2000 queries/month | `[ ]` |
| `ANTHROPIC_API_KEY` | console.anthropic.com | No — pay per token | `[ ]` |
| `OPENAI_API_KEY` | platform.openai.com | No — optional, only for `EMBEDDING_MODE=openai` | `[ ]` |

Rough costs: a map is a few cents of Claude; Claims is about half a cent per article; an Ask answer is a cent or two.

---

## Session Checklist

**Before each session:**
- [ ] `git pull` on `main`
- [ ] Backend running? (`uv run uvicorn backend.api.main:app --port 8001`)
- [ ] Frontend rebuilt if it changed? (`cd frontend && npm run build`)

**After each session:**
- [ ] `uv run pytest` and `cd frontend && npm run check && npm run lint`
- [ ] Commit on a branch, open a PR, let CI run
- [ ] Note anything surprising — it will matter later

---

## Good Test Topics

Start with these — they have clear discourse structure and good web coverage.

| Topic string | Why it's good |
|---|---|
| `mechanistic interpretability in large language models` | Rich, active, 2022–present, clear camps |
| `longevity science and aging reversal` | Real disagreements, great for Claims |
| `urban heat islands and city design` | Good timeline, recent policy debate |
| `jevons paradox and energy efficiency` | Older topic, long timeline |

**Avoid:** Topics too broad (`AI`, `climate change`) or too narrow (< 20 articles exist). The sweet spot is a specific sub-topic with 50–200 good articles.
