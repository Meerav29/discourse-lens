# discourse-lens as a Claude.ai skill: design

Written by the autopilot build routine, 2026-10-21 (slice-1). This is the spec slice-2 (prototype) and slice-3 (skill) build from. Calls made without Meerav are also logged in `docs/autopilot/decisions.md`.

## 0. The design in one paragraph

The user asks Claude in chat to map the debate on a topic. Claude runs about 8 to 12 web searches, reads 15 to 30 pages in full and keeps search-result snippets for up to 15 more. As it reads, it writes one compact note per source (metadata, a short paraphrased summary, 2 to 4 paraphrased claims) to a file in the code-execution sandbox, so the page text doesn't have to stay in its head. Once reading is done, Claude groups the sources into 3 to 6 named topics, groups the claims into shared propositions with an agree, qualify or dispute stance per source, and writes a **contract JSON** (section 5). A small stdlib-only Python script bundled with the skill checks the contract and inlines it into a **single HTML template**. That page is the artifact: a map, a claims view, and a sources table. **The map's geometry is computed in the browser from Claude's discrete judgments** (topic membership, how well each source fits, which topics share propositions), not from embeddings. Positions are schematic, and the page says so. Follow-up questions ("what do the critics say about X?") are answered in the chat itself, from the notes, with citations.

## 1. What Claude.ai offers today, and what I checked

Each row below is either **verified** (stated on the docs page cited, as read on 2026-10-21) or an **assumption** (not stated anywhere I could find; slice-3's dry run or Meerav has to confirm it in a real Claude.ai chat).

| # | Capability | Status | Source / reasoning |
|---|---|---|---|
| V1 | Web search in chat; Claude can also fetch the full content of specific URLs ("web fetch"); results carry citations; use counts toward plan usage limits; no published per-turn cap | verified | [Enable and use web search](https://support.claude.com/en/articles/10684626-enable-and-use-web-search) |
| V2 | Code execution and file creation: Free/Pro/Max on by default; Python and JavaScript; network egress is limited to approved package sources (npm, PyPI, GitHub, crates, Ubuntu, Yarn) by default; Team/Enterprise admins can switch egress off or widen it; 30 MB per file; task duration and container lifetime are limited (no numbers given) | verified | [Create and edit files with Claude](https://support.claude.com/en/articles/12111783) (updated 2026-08-06) |
| V3 | Artifacts on all plans, and they require code execution and file creation to be on; HTML pages and React apps; "Claude now uses the computing environment to create them" | verified | [What are artifacts](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them); [Create and edit files](https://support.claude.com/en/articles/12111783) |
| V4 | Artifacts can store data (20 MB, text) and can call Claude using the viewer's own account | verified | [What are artifacts](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) |
| V5 | Custom skills in claude.ai: uploaded as a zip under Settings > Features; Pro, Max, Team and Enterprise with code execution on; per user only; `SKILL.md` frontmatter `name` ≤ 64 chars (lowercase, digits, hyphens) and `description` ≤ 1024 chars; network access depends on user/admin settings | verified | [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) |
| V6 | Artifact pages run under a CSP: scripts only from cdnjs, unpkg, jsDelivr `/npm/`, the Tailwind and jQuery CDNs; fonts only from Google Fonts; `fetch`/XHR only to the page's own origin; no external images; 16 MiB page cap | verified **for artifacts published from Claude Code**, which are served from the same `claudeusercontent.com` viewer | [Claude Code: artifacts, Page constraints](https://code.claude.com/docs/en/artifacts#page-constraints) |
| A1 | The same CSP applies to artifacts made in a Claude.ai chat | assumption | Same viewer domain and the same audit-log family, but no chat-side doc says so. The design doesn't depend on it: the template has no runtime dependency (section 4.3). |
| A2 | The Claude.ai sandbox has numpy, pandas and scikit-learn preinstalled | assumption | That list is documented for the **API** code-execution tool ([pre-installed libraries](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool#pre-installed-libraries), 5 GiB RAM, 1 CPU, no network). The Claude.ai container isn't documented. The chosen design needs only the Python standard library. |
| A3 | An embedding model can't be downloaded in the sandbox by default | assumption, high confidence | Model weights come from Hugging Face or similar hosts, which aren't on the approved package-source list in V2. Admins on "All domains" egress would be the exception. |
| A4 | Files written in the sandbox survive across turns of the same chat, so the notes file can grow over 2 or 3 turns | assumption | Container lifetime is "limited" (V2), with no numbers. Fallback: Claude keeps the notes as a JSON block in the chat and pastes them back in. |
| A5 | An HTML file the bundled script writes can be shown as the artifact, rather than Claude re-typing the template | assumption, plausible from V3 | Fallback: Claude emits the artifact itself from the template. The template's size limit (section 8, P9) keeps that affordable. |
| A6 | Context window of at least 200k tokens; one fetched article costs roughly 2k to 10k tokens | assumption (estimate) | Not documented for chat. The source budget (section 6) is sized to fit within this, with a margin. |

## 2. The skill's flow

1. **Scope** (chat). Restate the topic in one line, and say how big the map will be (section 6) and how long it'll take. If the topic is too broad ("AI") or too narrow, propose a sharper one. Optional **source checkpoint**, the app's "Let me check the sources" step: if the user asked for it, show the query plan and the candidate sources before reading anything.
2. **Search.** 8 to 12 queries: 2 overview, 4 to 6 facets (one per likely angle), 1 or 2 **dissent** queries ("criticism of X", "X is overstated"), and 1 recent ("X 2026"). Log every query in `queries[]` with its purpose, so the map shows how the sample was drawn.
3. **Pick and read.** Dedupe by URL and by near-identical title. Prefer variety of domains: at most 3 sources per domain. Fetch the top 15 to 30 pages in full. Keep up to 15 more as `read_depth: "snippet"`, using the search snippet or abstract only. Skip paywalled, non-English and listicle or SEO-farm pages, and say how many were skipped and why.
4. **Note.** Right after each source, append one record to `notes.jsonl` in the sandbox: `id, url, domain, title, publish_date (or null), source_type, read_depth, summary (≤40 words, paraphrased), claims[2-4] (≤30 words each, paraphrased), quote? (≤15 words)`. After that, the page text isn't needed again.
5. **Group.** Read all the notes together, not one at a time. Name 3 to 6 topics whose labels contrast with each other (this is the app's single naming call). Assign each source to one topic, or to `-1` if it doesn't fit; a topic needs at least 3 sources, otherwise its sources go to `-1`. Mark each source `fit: core|edge`, and give `also_cluster_id` only for sources that clearly bridge two topics. Write a 1-sentence description and 5 to 8 distinctive terms per topic.
6. **Claims.** Group the per-source claims into propositions that **2 or more** sources take a position on. Give each stance `agrees|qualifies|disputes` plus that source's paraphrased claim. Snippet-only sources get a stance only when the snippet states the position outright. Order the propositions most debated first: by number of `qualifies + disputes`, descending, then by total stances.
7. **Build.** Write `contract.json`, then run `python build_map.py contract.json map.html`. The script validates the contract (section 5) and fails loudly on a dangling `article_id`, a count mismatch or an over-long field. Present `map.html` as the artifact.
8. **Report** (chat). Five lines at most: the camps, the most contested proposition, what the sample is thin on (for example "only 2 academic sources", "nothing before 2015"), and an invitation to ask follow-ups.
9. **Ask** (chat, any time after). Answer only from `notes.jsonl`, with numbered citations to source URLs. Re-fetch a page only if the user asks something the notes can't answer, and say when you do.

## 3. Which views survive

| App view | In the skill | Why |
|---|---|---|
| **Map** | **Kept**, as the hero of the artifact. Topic-coloured points, labelled topics, hover or tap for title, domain and date, click to open the source card. | It's the product's identity and what the brief asks for. The geometry changes (section 4); the reading of it doesn't. |
| **Claims and stances** | **Kept**, as the second tab of the artifact: propositions with agree, qualify and dispute bars, expandable to the sources and their paraphrased claims. Selecting a topic on the map filters it. **It runs by default**, not on request. | "Where sources agree and disagree" is half the brief. The app makes it opt-in because it costs extra API calls per article; in chat, Claude has already read every page, so the marginal cost is a few hundred tokens per source. |
| **Key terms** | **Merged** into the topic panel next to the map: each topic's label, description and 5 to 8 distinctive terms, without weights. | There's no corpus-wide c-TF-IDF without the backend. Claude-picked terms are a judgment, not a statistic, so they shouldn't get their own view or look like a measurement. |
| **Timeline** | **Merged** into a small strip under the map (sources per year, stacked by topic). Shown only when at least half the sources have a date. | With 25 to 45 sources a full view is mostly empty bins. Dates are often missing, and we never guess them. A strip still shows the "AI revived the topic in 2024–25" shape the fixture has. |
| **Ask** | **Moved** into the chat itself. | Chat is already a question-answer surface with citations (V1). An in-artifact Ask would need the article text inside the page (a copyright problem) or an AI-powered artifact call (V4) with no access to the sources. |
| **Reader** | **Dropped**, replaced by a **source card**: title, domain, date, source type, read depth, the paraphrased summary, the claims, and a link out. | The reader shows full article text. The skill must not store or reproduce it (section 7). Linking out is the honest replacement. |
| **Source review** | **Merged** into step 1 as an optional chat checkpoint. | It's a conversation step, and chat is good at it. |
| **Outliers / Table** | Outliers become `fit: edge`, drawn further out from their topic. Table is kept as the artifact's third tab (sortable sources list). | Same idea, without distance-from-centroid statistics. |
| **Obsidian export, saved maps, cancel** | **Dropped.** | Chat history and the artifact itself are the persistence. |

## 4. The open problem: how the map gets drawn

The app's map comes from geometry: chunk embeddings averaged per article, reduced with UMAP, clustered with HDBSCAN. Distance means textual similarity. In chat there's no LanceDB and no bundled embedding model. Four ways to get points on a page:

### 4.1 Approaches compared

**A. Claude decides membership; the artifact computes a force layout.** Claude outputs discrete judgments it's good at and can justify: which topic, core or edge fit, an optional bridge topic, and the propositions. The page runs a seeded force simulation. Each topic gets an anchor point, placed so that topics sharing more propositions sit closer. Sources are attracted to their anchor, bridges to both anchors, edge sources are pushed outward, and collision keeps the points apart.
- Feasibility: needs only an HTML artifact (V3) and plain JavaScript. No sandbox libraries, no network. A self-contained force sim for ≤ 150 nodes is about 100 lines and settles in well under a second (to be proven by P2).
- Risks: positions inside a topic carry no meaning, so the page must say the layout is schematic. The quality of the topic grouping rests entirely on Claude's reading.

**B. Embeddings plus UMAP or PCA in the code-execution sandbox** (the app's method, ported).
- Feasibility: **not feasible by default.** There's no bundled model. Downloading nomic-embed or a sentence-transformers model needs Hugging Face access, which isn't on the approved egress list (V2, A3); a PyTorch install also strains the sandbox. It works only for orgs whose admin sets egress to "All domains", and the skill can't rely on that. Even then, what would get embedded is Claude's notes (we don't keep page text), so it would be geometry over Claude's paraphrases.
- Verdict: rejected.

**C. Claude places the points directly** (writes `x`, `y` for every source).
- Feasibility: trivially feasible.
- Risks: numbers a model emits for 40 points aren't a measurement. They look exactly as precise as UMAP output while meaning nothing, you'd get a different layout every run, and labels overlap unless Claude is careful. It's the most misleading option at the same cost as A.
- Verdict: rejected.

**D. TF-IDF over Claude's notes, then truncated SVD and k-means in the sandbox** (a "lexical" stand-in for B).
- Feasibility: plausible. Needs scikit-learn in the sandbox (A2, unverified), runs on text Claude wrote, and needs no network.
- Risks: with 30 documents of about 120 words each, TF-IDF neighbours mostly reflect Claude's own word choice. It adds a dependency and a failure mode (a missing package) for a weak signal, and it still needs Claude to name the clusters.
- Verdict: not chosen for v1. Kept as a possible later addition: it could be offered as an "alternative layout" check without changing the contract.

### 4.2 Choice: A

A wins because it is the only approach that (1) works on every plan where artifacts and skills exist, with no sandbox package and no egress, (2) is deterministic (the same contract gives the same picture), and (3) is honest: it encodes exactly what was judged (membership, fit, bridges, shared claims) and nothing it can't back up.

**Evidence from the fixture** (computed 2026-10-21 on `reference-map-jevons.json`): for each of the 6 topics, I compared its nearest topic in the app's UMAP layout (centroid distance) with the topic it shares the most propositions with. They agree for **4 of 6 topics outright**, the 5th is a tie that includes the UMAP neighbour, and 1 misses (*AI's environmental footprint* shares the most propositions with *Jevons paradox explained*, while UMAP put it next to *Jevons and AI economics*). So shared propositions recover most of the app's large-scale arrangement without any embeddings. This is a check on one map, not a proof.

### 4.3 Layout rules (what the prototype implements)

- **Topic anchors**: relatedness between topics `i,j` = the number of propositions with stances from both, or `clusters[].related` if Claude supplied it. Anchors are placed on a circle in an order that maximizes adjacent relatedness (brute force for ≤ 6 topics), then nudged by a small spring pass so related pairs sit closer. Unclustered sources (`-1`) go to a neutral zone at the centre-bottom, the way the app lists them separately.
- **Points**: attraction to the anchor, with strength 1.0 for `core` and 0.5 for `edge` (edge sources settle at roughly 1.6× the core radius). Bridges get a 0.6 / 0.4 pull toward their two anchors. Collision radius scales with point size. The PRNG is seeded from the article id, so layouts are reproducible.
- **Fixture x/y are ignored** when present. The prototype shows a side-by-side against them as a sanity check only.
- **No runtime dependency.** Vanilla JS and inline SVG, with no CDN script, so A1 doesn't matter. If hand-rolling proves fragile, the fallback is d3-force at a pinned version from cdnjs or jsDelivr (V6). I couldn't reach either CDN from this sandbox to confirm a version; slice-2 picks one and checks that it exists.
- **Caption on the map**: "Positions are schematic: topics that share claims sit closer; within a topic, distance means nothing."

## 5. Data contract

The schema is in [`skill/contract.schema.json`](contract.schema.json) (JSON Schema 2020-12). It is a **strict superset of the fixture**. Every fixture field keeps its name and meaning, and every new field is optional, so the app's export is valid as-is. Checked on 2026-10-21 with `jsonschema` 4.26.0: `reference-map-jevons.json` → 0 errors; the same file with one date changed to `"May 2024"` → rejected.

Top level: `topic`, `article_count`, `clusters[]`, `articles[]`, `propositions[]` (all required, as in the fixture), plus optional `schema_version: 1`, `generated_at`, and `queries[] {q, purpose: overview|facet|dissent|recent|user, results_kept}`.

| Object | Fields from the fixture | New in the skill (optional) |
|---|---|---|
| cluster | `cluster_id`, `label` (≤40 chars), `description`, `article_count`, `terms` | `terms` may be plain strings instead of `[term, weight]`; `related[] {cluster_id, strength 0–1}` |
| article | `id`, `url`, `domain`, `title` (nullable), `publish_date` (nullable, `YYYY[-MM[-DD]]`), `cluster_id` (`-1` = unclustered), `x`, `y` (ignored) | `fit core\|edge`, `also_cluster_id`, `read_depth full\|snippet`, `source_type`, `summary` (≤300 chars), `quote` (≤120 chars) |
| proposition | `position`, `statement`, `stances[] {article_id, stance agrees\|qualifies\|disputes, claim}` (≥2 stances) | none |

Rules the schema can't express, which `build_map.py` must check: `article_count == len(articles)`; every `clusters[].article_count` matches its members; every `stances[].article_id` exists; ids are unique; `also_cluster_id != cluster_id`; at most one stance per article per proposition; `position` values are 0..n-1 in order. Slice-2 writes this checker in the standard library only (`json`, `re`), because `jsonschema` may not be in the sandbox (A2).

Sizes: the fixture is 41 KB for 52 articles and 74 stances. A 40-source skill contract with summaries is expected to be about 35 to 50 KB.

## 6. Source budget, and what it does to the map

| | App (fixture) | Skill, one turn | Skill, up to 3 turns ("continue") |
|---|---|---|---|
| Searches | 6 | 8 | up to 12 |
| Pages read in full | ~120 crawled, 52 kept | 12–15 | 25–30 |
| Snippet-only sources | 0 | up to 10 | up to 15 |
| Sources on the map | 52 | ~20–25 | ~35–45 |
| Topics | 6 (+4 unclustered) | 3–4 | 4–6 |
| Propositions / stances | 11 / 74 | ~4–6 / ~20–30 | ~7–10 / ~40–60 |

**Why these numbers.** Assuming A6 (≥ 200k context, 2k to 10k tokens per fetched page), 15 full fetches use roughly 60 to 120k tokens, which is the most one turn can hold with room left to reason and write the contract. Writing notes to the sandbox after each page (step 4) is what makes a second and third turn possible: those turns build on the compact notes, not on page text. If A4 fails, the skill works in one turn at ~20 to 25 sources. No usage limits are published (V1), so slice-3 has to measure how much of a Pro plan's usage a full 3-turn map consumes.

**What happens to map quality at this size, compared with the fixture.**
- **Small camps merge or vanish.** The fixture's two AI topics hold 4 and 3 of 52 sources (13%). Scaled to 30 sources that's about 2 each, below the 3-source minimum, so they'd merge into one "Jevons and AI" topic or go to unclustered. The skill sees the 3 to 5 big camps, not the long tail. The 1 to 2 dissent queries partly offset this, because they deliberately seek out minority positions, and `queries[]` shows that they did.
- **Two-source propositions are fragile.** The fixture has 11 propositions with 2 to 18 stances; at 25 read sources the ones with only 2 or 3 stances mostly fall below threshold. Expect the big agreements to survive and the niche ones to drop.
- **Disputes stay rare.** Only 2 of the fixture's 74 stances are `disputes`. At skill size, many maps will have zero. The artifact must say "no source in this sample disputes X", not imply consensus in the world.
- **The timeline gets coarse.** All 52 fixture sources are dated, but crawled metadata is better than what web fetch shows. Expect 50 to 80% dated, and yearly bins only.
- **Gains.** Every source on the map was actually read by the model that labels it, so there are no extraction failures and no boilerplate chunks. Claims come from the whole page, not the opening, and topic labels can be written knowing every member.

The map says its size in the header ("31 sources, 24 read in full, 9 searches") so nobody mistakes it for a 100-source map.

## 7. Copyright: no reproduced text

- **Nothing verbatim by default.** `summary`, `claims` and `statement` are Claude's paraphrases (≤40, ≤30 and ≤40 words). The schema's length caps make long copied passages fail validation.
- **One short quote per source at most**: optional, ≤15 words, in quotation marks, used only when the exact wording is the point (a coined term, a contested phrasing). Never song lyrics, poems, or a paywalled article's lede.
- **No page text in any file.** `notes.jsonl`, `contract.json` and the artifact hold metadata and paraphrase only. The page text lives only transiently in the turn that reads it. The repo rule (no full article text) applies to anything the skill commits under `skill/examples/`.
- **Attribution and links.** Every source card links to the original, and the Ask answers in chat cite URLs. Titles are reproduced as-is (factual metadata).
- **Paywalls.** If a fetch returns a paywall or login wall, the source is either snippet-only or skipped. The skill never tries to get around a paywall.

## 8. What the prototype (slice-2) must prove

Each item is a checkable statement. FINDINGS.md marks each proven, not proven, or not tested.

- **P1 Self-contained.** `skill/prototype/map.html` renders the fixture, inlined, with zero network requests (or only a pinned cdnjs/jsDelivr script if the d3 fallback was used); file size < 1 MB; no console errors in headless Chromium at 1440 px and 390 px.
- **P2 Layout computed in the browser.** The page ignores the fixture's `x`/`y`. Two loads produce identical positions (compare a hash of the rounded coordinates). The simulation settles in < 1 s for the 52-source fixture and < 2 s for a synthetic 150-source contract.
- **P3 Topics read as groups.** ≥ 90% of clustered sources lie closer to their own topic's centroid than to any other topic's; no two topic labels' bounding boxes overlap at 1440 px or 390 px.
- **P4 Arrangement versus the app.** A table gives each topic's nearest topic in the computed layout and in the fixture's UMAP layout. Proven if ≥ 4 of 6 match. Plus a side-by-side screenshot.
- **P5 Claims view is faithful.** It shows all 11 fixture propositions, ordered by section 2 step 6. The per-proposition agree, qualify and dispute counts sum to exactly 74, and each proposition expands to its sources and claims with working links.
- **P6 Interaction.** Hover (desktop) and tap (390 px) show title, domain and date. Clicking a topic filters the claims view and the sources table to it. A null title falls back to the domain (fixture article 18).
- **P7 Contract variants.** A generated variant (dates removed from half the sources, terms as strings, no x/y, one topic with `related`, a bridge source, an `edge` source, zero propositions) renders without errors. The timeline strip hides when < 50% of sources are dated.
- **P8 Generator.** `build_map.py contract.json out.html` uses only the Python standard library, rejects a contract with a dangling `article_id` (non-zero exit, clear message), and reproduces `map.html` byte-for-byte from the fixture.
- **P9 Fits a chat turn.** The template without data is ≤ 40 KB, so if A5 fails Claude can emit the whole artifact itself.

## 9. Non-goals and anti-goals

**Non-goals** (things we won't do, even though they'd be nice):
- Matching the app's 50 to 100 sources or its statistical clustering. The skill is a smaller, judged map.
- Embeddings, UMAP, HDBSCAN or c-TF-IDF in chat (see 4.1 B and D).
- Any article text in the artifact: no reader, no full-text search, no in-artifact Ask.
- Saved maps across chats, exports (Obsidian, CSV), cancel or progress UI. The chat is the progress UI.
- Running in Claude Code or the API as first-class targets. They might work, but the brief picked Claude.ai chat.
- Changing the app (`backend/`, `frontend/`, `tests/`), or installing or publishing the skill during the autopilot window.

**Anti-goals** (things the skill must actively avoid):
- **Invented sources.** Every URL must have come from a search or fetch result in this conversation. No URL is ever written from memory.
- **Invented dates.** Use `null`, never a guess from context.
- **Fake precision.** No coordinates from the model, no confidence numbers on stances, no "% agree" framed as public opinion. The map states its sample size and that the layout is schematic.
- **False balance or false consensus.** Don't manufacture a `disputes` stance to make the map look debated. Don't hide one either. Say when a proposition has no dissent in the sample.
- **Forcing fit.** A source that fits no topic goes to `-1` (shown as unclustered), not into the nearest topic.
- **Reproducing text** beyond section 7's limits, or getting around a paywall.
- **Quietly over-reading.** If the turn budget runs out, stop at the budget, build the map from what was read, and say so. Don't silently drop the claims step to save tokens.

## 10. For Meerav: what to confirm in a real Claude.ai chat

The design holds if A4 and A5 hold. If either fails it degrades rather than breaks (fallbacks given in section 1). Worth a 2-minute check in Claude.ai before slice-3:
1. Does a file written by Python in one turn still exist in the next turn of the same chat? (A4)
2. Can Claude present an HTML file the sandbox wrote as an artifact? (A5)
3. In a chat artifact, does a `<script src="https://cdnjs.cloudflare.com/...">` load? (A1; only matters if the prototype falls back to d3)
