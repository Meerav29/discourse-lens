# Decisions made by autopilot

Every design call a routine made because the brief or design did not settle it. Newest at the bottom.

Format:

```
## <date> slice-<n> <topic>, PR #<pr>
Question: ...
Chosen: ...
Rejected: ...
Blast radius: ...
```

---

## 2026-10-21 slice-1 how the map is drawn, PR #5
Question: Without the app's embeddings, how does the skill place sources on the map?
Chosen: Claude makes discrete judgments (topic, core/edge fit, optional bridge topic, shared propositions). The artifact computes a seeded force layout in the browser: topics that share more propositions sit closer. The fixture check: the topic with the most shared propositions is the UMAP nearest neighbour for 4 of 6 topics, plus 1 tie.
Rejected: embeddings + UMAP in the sandbox (no bundled model, Hugging Face not on the default egress list); Claude writing x/y directly (precise-looking, meaningless, not reproducible); TF-IDF + SVD over Claude's notes (needs scikit-learn, which isn't documented for the claude.ai sandbox, and is a weak signal at 30 docs). The last is kept as a possible later "alternative layout".
Blast radius: slice-2 builds this layout; the map stops encoding text similarity and must say it is schematic.

## 2026-10-21 slice-1 which views survive, PR #5
Question: Which of the app's views does the chat skill keep?
Chosen: Map and Claims kept (Claims runs by default, not opt-in); Key terms merged into the topic panel; Timeline becomes a strip shown only when ≥50% of sources are dated; Ask moves into the chat; Reader becomes a source card with a link out; Source review becomes an optional chat checkpoint; Outliers become `fit: edge`; Table kept as a tab.
Rejected: an in-artifact Ask via AI-powered artifacts (no access to sources without embedding article text); a full Reader (copyright); keeping Claims opt-in (Claude has already read the pages, so the extra cost is small).
Blast radius: what slice-2 and slice-3 render.

## 2026-10-21 slice-1 source budget, PR #5
Question: How many sources fit in chat?
Chosen: 8–12 searches (including 1–2 labelled dissent queries), 15 pages read fully per turn, up to 3 turns with notes kept in a sandbox file, so ~35–45 sources on the map (25–30 read fully, the rest snippet-only). One-turn fallback: ~20–25.
Rejected: matching the app's 50–100 (doesn't fit the context window if pages are held in context); a single turn only (too few sources for more than 3 camps).
Blast radius: map quality. Small camps merge, and 2-source propositions drop out. Context-window and sandbox-persistence figures are unverified assumptions (design.md §1 A4, A6).

## 2026-10-21 slice-1 data contract shape, PR #5
Question: How close to the fixture should the contract be?
Chosen: A strict superset of the fixture (skill/contract.schema.json). All new fields are optional, `title` and `publish_date` may be null, and `terms` may be strings or [term, weight]. The fixture validates with 0 errors.
Rejected: a fresh schema (it would break comparison with the app's export).
Blast radius: slice-2's renderer and slice-3's build script.

## 2026-10-21 slice-1 no runtime JS dependency, PR #5
Question: Use d3 from a CDN or hand-written JS for the layout?
Chosen: vanilla JS and SVG with no CDN dependency, so the page doesn't depend on chat artifacts having the same CSP as Claude Code artifacts (unverified). d3-force from cdnjs at a pinned version is the fallback.
Rejected: d3 by default.
Blast radius: slice-2 implementation effort.
