# Autopilot queue: discourse-lens skill

Design: `grid-prophet/docs/superpowers/specs/2026-09-19-autopilot-design.md` (branch model, review contract, PR template in section 9).
Window: 2026-10-20 → 10-26. Base branch: `auto/queue`. Tracking issue: #4.
Rotation: Wed, Fri, Sun.

## The brief (from Meerav, 2026-10-20)

Condense what discourse-lens does into a **skill people can use in Claude.ai chat**. It should still produce the same kind of visualization: a map of the conversation around a topic, its camps, and where sources agree and disagree. How to draw that visualization without the app's backend is the open problem. Target surface: **Claude.ai chat**, chosen over Claude Code. So there's no local Python service, no LanceDB and no bundled embedding model. Whatever Claude.ai provides is what's available: web search and fetch, the code-execution sandbox, and artifacts.

Read [README.md](../../README.md) for what the app's six views do, and `skill/fixtures/reference-map-jevons.json` for a real output to match.

Status values: `todo` → `in-progress` → `in-review` → `merged`.
Terminal: `held` (owner vetoed), `blocked` (review rejected).

Rules for every slice:

- Touch only `skill/`, this file and `docs/autopilot/decisions.md`. Never touch `backend/`, `frontend/` or `tests/`.
- No full article text in the repo. Titles, URLs, and short paraphrased claims are fine.
- These slices are docs and prototypes, so "tests that fail without the change" doesn't apply. Each slice's own checks below replace it. The 600-line cap applies to hand-written files. A generated or fixture JSON file doesn't count, but say how big it is.
- Ambiguity policy as usual: decide, then record the decision in the PR body and in decisions.md.

---

## slice-1: design doc

Status: in-review

Write `skill/design.md`, a design a builder could implement the skill from without asking Meerav anything.

Acceptance:

- [ ] Says which of the app's views survive in chat (map, claims and stances, key terms, timeline, ask, reader) and which are dropped or merged, with a reason for each.
- [ ] **Answers the open problem: how does the map get drawn?** Compare at least three approaches. For example: Claude assigns topics and the artifact computes a force layout; embeddings plus UMAP or PCA in the code-execution sandbox; Claude places the points directly. For each, check feasibility against what Claude.ai actually offers. Say plainly which capabilities you could verify from docs and which you're assuming. Pick one, and say why.
- [ ] Defines the data contract between the research step and the artifact: a JSON schema compatible in spirit with `reference-map-jevons.json`.
- [ ] Gives a source budget (how many searches and pages fit in one chat turn or a few) and says what happens to map quality at that size compared with the app's ~50-100.
- [ ] Says how the skill avoids reproducing copyrighted text (claims paraphrased, short quotes only).
- [ ] Lists what the prototype (slice-2) must prove, as checkable statements.
- [ ] Non-goals and anti-goals are stated.

Review checks each box against the doc text. It doesn't check whether the design is right.

## slice-2: visualization prototype

Status: todo

Build the visualization the design picked, as a **single self-contained HTML file** (the shape a Claude.ai artifact takes): `skill/prototype/map.html`, rendering `skill/fixtures/reference-map-jevons.json` inlined into it.

Acceptance:

- [ ] Shows at least the map (points by topic, labelled topics, hover or click for title and domain) and the claims view (propositions with agree/qualify/dispute counts, expandable to the articles), per design.md.
- [ ] Works with the layout approach design.md chose. If that approach computes positions in the browser, it ignores the fixture's `x`/`y` and computes its own. The PR includes a side-by-side shot against the fixture's placements.
- [ ] Self-contained: no network requests except script libraries from cdnjs or jsdelivr at pinned versions. Under 1 MB.
- [ ] Renders without console errors in headless Chromium at 1440 px and 390 px wide. The PR includes both screenshots. (Chromium: `npx -y playwright@1.48.2 install --with-deps chromium`.)
- [ ] Includes a small generator script or documented step that turns any contract-shaped JSON into the page, so the skill can reuse it.
- [ ] `skill/prototype/FINDINGS.md`: what worked, what didn't, and a go/no-go for slice-3, with reasons. Each "must prove" statement from design.md is marked proven, not proven, or not tested.

## slice-3: skill draft, or findings

Status: todo

**If FINDINGS.md says go:** write the skill at `skill/discourse-lens/`, following the Agent Skills format (`SKILL.md` with name and description frontmatter, plus any `references/` and `assets/`). The artifact template from slice-2 goes in `assets/`.

**If it says no-go:** don't write a skill. Extend FINDINGS.md with what would have to change, such as a different surface, a different visualization, or a smaller scope. Mark this slice merged with that as its deliverable.

Acceptance (go path):

- [ ] SKILL.md under ~500 lines. Its description says when to trigger ("map the debate around X", "what are the camps on Y").
- [ ] Walks Claude through research, then grouping and claims, then building the contract JSON, then the artifact, within the design's source budget.
- [ ] Includes one worked example and 3 eval prompts in `skill/discourse-lens/evals/evals.json`.
- [ ] Dry run: follow the skill yourself in this sandbox on one topic (using your own web search and fetch), produce the contract JSON and the HTML, commit them under `skill/examples/<topic>/`, and attach screenshots. Say honestly where the sandbox differs from Claude.ai.
