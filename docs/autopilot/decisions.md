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

## 2026-10-23 slice-2 browser and Playwright version for the checks, PR #6
Question: The routine says to install Chromium with `npx -y playwright@1.48.2 install --with-deps chromium`; this cloud environment says Chromium is preinstalled and not to run `playwright install`.
Chosen: the preinstalled Playwright 1.56.1 with Chromium 141.0.7390.37. `check.cjs` only uses the stable API (launch, newContext, screenshot, mouse, touchscreen), so it should run on 1.48.2 too, but that wasn't tried.
Rejected: downloading a second browser into the sandbox against the environment's instruction.
Blast radius: screenshots and timings come from Chromium 141. None of the checks depend on the version.

## 2026-10-23 slice-2 rotate the layout to fit the viewport, PR #6
Question: The computed layout is often taller than wide, which left half of a 1440 px map empty.
Chosen: at draw time, try 12 rotations (0° to 165°) and keep the one that gives the largest scale. A rotation changes no distances, so P2 to P4 are unaffected (they're measured on the unrotated positions).
Rejected: stretching x and y separately (distorts distances); a fixed tall map (wasted space on desktop).
Blast radius: the unclustered group, placed below the topics before rotation, can end up in a corner instead of at the bottom as design.md 4.3 says. It stays separate and labelled.

## 2026-10-23 slice-2 tap opens the source card, not a tooltip, PR #6
Question: design.md P6 asks that a tap at 390 px show title, domain and date. A tooltip and the card both did, so they showed the same thing twice.
Chosen: on touch, a tap opens the source card (title, domain, date, topic, summary, stances, link). Mouse hover still shows the tooltip.
Rejected: tooltip on tap and card on a second tap (two taps to read anything).
Blast radius: template interaction only.

## 2026-10-23 slice-2 what a selected topic does to the claims view, PR #6
Question: design.md says selecting a topic "filters" the claims view but not how.
Chosen: keep only stances from that topic's sources (including sources that bridge to it), hide propositions left with none, recount the bars, and show "(of N overall)". Ordering is recomputed on the filtered counts.
Rejected: highlighting without filtering (hard to read with 18-stance propositions).
Blast radius: template only.

## 2026-10-23 slice-2 point size and bar width, PR #6
Question: design.md says collision radius "scales with point size" without defining size, and the claims bars had no cross-proposition scale.
Chosen: point radius grows with the number of stances a source takes (4.5 + 0.75 per stance, capped at +3). Bar width is proportional to the proposition's stance count relative to the largest one.
Rejected: size by date or domain (meaningless for the map); full-width bars (hide that 18 sources take up one claim and 2 take up another).
Blast radius: template only.

## 2026-10-23 slice-2 generated test files not committed, PR #6
Question: Commit the test contracts and their rendered pages?
Chosen: commit the generators (`make_test_contracts.py`, `build_map.py`), `map.html`, `check-results.json` and the screenshots; gitignore `test-contracts/` and `out/`, which rebuild in seconds.
Rejected: committing about 200 KB of derived JSON and HTML.
Blast radius: a reviewer re-running checks runs the three commands in FINDINGS.md first.
