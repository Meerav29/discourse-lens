# discourse-lens

A local research app: type a topic, it reads ~50-100 web articles, and maps the conversation (topics, claims and stances, key terms, timeline, cited Q&A). [README.md](README.md) is the up-to-date description. [Planning.md](Planning.md) is the April v1 plan, kept for history only. [validation.md](validation.md) explains how to check the app.

**Stack:** FastAPI + SQLite + LanceDB backend (`backend/`), SvelteKit frontend (`frontend/`), in-process embeddings, Claude for labelling, claims and chat. Tests: `uv run pytest` (backend) and `npm test` in `frontend/`.

## What's happening now (Oct 2026)

The app is feature-complete. The new work is **turning its capability into a Claude skill that runs in Claude.ai chat**: no local backend, so Claude itself searches, reads, groups the sources and draws the map as an interactive artifact. Meerav decided on 2026-10-20 that chat is the target.

- All skill work lives in **`skill/`**:
  - `skill/fixtures/reference-map-jevons.json` is a real finished map exported from the app: 52 articles, 6 topics with 2D placements and terms, and 11 propositions with 74 per-article stances. No article text. It's the bar the skill's output is compared against.
  - `skill/design.md`: the skill design (written by autopilot, Oct 21).
  - `skill/prototype/`: a throwaway visualization prototype (Oct 23).
  - `skill/discourse-lens/`: the skill itself (Oct 25, only if the prototype held up).
- **Autopilot (Oct 20-26):** see [AUTOPILOT.md](AUTOPILOT.md) and `docs/autopilot/queue.md` on the `auto/queue` branch. Skill work lands on `auto/queue`, not `main`.

## Rules for skill work

- Don't change the app (`backend/`, `frontend/`, `tests/`) for the skill. The skill is a separate product that borrows the app's ideas.
- The fixture holds metadata and short extracted claims only. Don't add full article text to the repo.
- If you're asking a cloud session to continue the skill, branch from `auto/queue` and read `skill/design.md` first.
