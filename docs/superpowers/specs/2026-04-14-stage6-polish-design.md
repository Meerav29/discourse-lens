# Stage 6: Polish — Design Spec

**Date:** 2026-04-14
**Stage:** 6 of 6
**Theme:** "You'd show this to someone"

---

## Scope

Stage 6 adds one headline feature (Obsidian export) and one small fix (chat retry). Existing progress bars, loading states, and error handling on the main pipeline are adequate and remain unchanged.

---

## 1. Export Backend

### Endpoint

```
GET /api/export
```

Returns a zip file as a binary response with header:
```
Content-Disposition: attachment; filename="discourse-<topic-slug>.zip"
```

The topic slug is derived from the most recent completed job's topic string (spaces → hyphens, lowercased, max 40 chars).

### Zip structure

```
discourse-<topic-slug>/
  cluster-map.canvas        ← Obsidian Canvas JSON
  vault/
    _index.md               ← cluster summary note with article counts and links
    <article-slug>.md       ← one file per article where status = 'ok'
```

### Canvas file (`cluster-map.canvas`)

Obsidian Canvas format is a JSON file with `nodes` and `edges` arrays.

**Nodes:** One node per article. Fields:
- `id`: article ID (string)
- `type`: `"text"`
- `x`, `y`: UMAP coordinates scaled to canvas pixel space. Scale factor: multiply each coordinate by 200. Center the layout by subtracting the mean x/y before scaling.
- `width`: 200, `height`: 80 (fixed card size)
- `text`: `"**{title}**\n{domain}"` (markdown inside the card)
- `color`: one of Obsidian's 6 named canvas colors (`"1"` through `"6"`), assigned by `cluster_id % 6`

**Edges:** None. Spatial proximity communicates cluster membership.

Data source: `projections` JOIN `articles` — uses the `x`, `y`, `cluster_id`, `cluster_label` columns already populated by Stage 3.

### Vault files

**Article notes (`vault/<slug>.md`):**

Slug: article title lowercased, spaces/punctuation → hyphens, max 60 chars, with article ID suffix to guarantee uniqueness.

Content:
```markdown
---
title: "{title}"
url: "{url}"
domain: "{domain}"
cluster: "{cluster_label}"
publish_date: "{publish_date}"
word_count: {word_count}
---
```

Body is empty. Frontmatter is Dataview-compatible so users can query across the vault (e.g. `TABLE cluster, domain FROM "vault" SORT publish_date`).

**Index note (`vault/_index.md`):**

```markdown
# {topic}

Analysed {article_count} articles across {cluster_count} clusters.

## Clusters

| Cluster | Articles |
|---------|----------|
| Neural Scaling Laws | 14 |
| ...     | ...      |

## Articles by cluster

### Neural Scaling Laws
- [[article-slug-1]]
- [[article-slug-2]]
...
```

Uses Obsidian `[[wikilink]]` syntax so the graph view connects the index to every article note.

---

## 2. Frontend Export Button

**Location:** Results top bar, between the metadata span and the "New analysis" button.

**Behavior:**
1. User clicks "Export"
2. Button switches to "Exporting…" and is disabled
3. Frontend calls `GET /api/export` and receives a blob
4. A temporary `<a>` element with `href = URL.createObjectURL(blob)` is programmatically clicked to trigger the browser download
5. Button returns to "Export" state

**Error:** If the request fails, button returns to normal state and a brief inline error message appears next to it (e.g. "Export failed"). No modal.

---

## 3. Chat Panel Retry

**Current behavior:** On a failed chat request, the error message (red text) is shown with no recovery path.

**Change:** Store the last submitted query in a `lastQuery` variable. When `error` is set, show a "Try again" button below the error text. Clicking it re-calls `submit(lastQuery)`.

No other changes to `ChatPanel.svelte`.

---

## 4. Out of Scope

- Export options/filters (which clusters to include, file format choice)
- Canvas preview before download
- Progress bar improvements (existing implementation is adequate)
- Toast notification system
- Any changes to pipeline stages 1–5

---

## Verification Criteria

Stage 6 is done when:
1. Clicking "Export" in the results view downloads a valid zip
2. Unzipping reveals `cluster-map.canvas` and a `vault/` folder with one `.md` per article
3. Opening `cluster-map.canvas` in Obsidian shows article cards spatially arranged by UMAP position, color-coded by cluster
4. Opening `vault/` as an Obsidian vault and running a Dataview query against frontmatter fields returns results
5. A failed chat request shows a "Try again" button that successfully re-submits
