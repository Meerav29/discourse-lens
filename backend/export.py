"""
Export utilities: Obsidian Canvas JSON and vault markdown files.
"""

from __future__ import annotations

import re
import statistics


CANVAS_SCALE = 200     # UMAP units → canvas pixels
NODE_WIDTH = 200
NODE_HEIGHT = 80
CLUSTER_COLORS = ["1", "2", "3", "4", "5", "6"]  # Obsidian canvas named colors


def article_slug(title: str, article_id: str) -> str:
    """Convert a title + id into a safe filename slug (max ~67 chars)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base[:60]
    suffix = article_id[-6:]
    return f"{base}-{suffix}"


def build_canvas(rows: list[dict]) -> dict:
    """
    Build Obsidian Canvas JSON from corpus rows.

    Each row must have: article_id, title, domain, x, y, cluster_id.
    Coordinates are centered (mean subtracted) then scaled by CANVAS_SCALE.
    Returns {"nodes": [...], "edges": []}.
    """
    if not rows:
        return {"nodes": [], "edges": []}

    mean_x = statistics.mean(r["x"] for r in rows)
    mean_y = statistics.mean(r["y"] for r in rows)

    nodes = []
    for r in rows:
        cx = round((r["x"] - mean_x) * CANVAS_SCALE)
        cy = round((r["y"] - mean_y) * CANVAS_SCALE)
        color = CLUSTER_COLORS[int(r["cluster_id"]) % len(CLUSTER_COLORS)]
        nodes.append({
            "id": r["article_id"],
            "type": "text",
            "text": f"**{r['title']}**\n{r['domain']}",
            "x": cx - NODE_WIDTH // 2,
            "y": cy - NODE_HEIGHT // 2,
            "width": NODE_WIDTH,
            "height": NODE_HEIGHT,
            "color": color,
        })

    return {"nodes": nodes, "edges": []}


def build_vault_files(
    rows: list[dict],
    clusters: list[dict],
    topic: str,
) -> dict[str, str]:
    """
    Build vault file contents.

    rows: each must have article_id, title, url, domain, cluster_label,
          publish_date, word_count.
    clusters: list of {cluster_label, article_count}.
    topic: the original topic string (used in _index.md header).
    Returns {relative_path: file_content} — no leading slash.
    """
    files: dict[str, str] = {}
    slug_map: dict[str, str] = {}

    for r in rows:
        slug = article_slug(r.get("title") or "untitled", r["article_id"])
        slug_map[r["article_id"]] = slug
        frontmatter = (
            "---\n"
            f'title: "{_esc(r.get("title") or "")}"\n'
            f'url: "{r.get("url") or ""}"\n'
            f'domain: "{r.get("domain") or ""}"\n'
            f'cluster: "{_esc(r.get("cluster_label") or "")}"\n'
            f'publish_date: "{r.get("publish_date") or ""}"\n'
            f'word_count: {r.get("word_count") or 0}\n'
            "---\n"
        )
        files[f"{slug}.md"] = frontmatter

    # Cluster table for index
    table_rows = "\n".join(
        f"| {c['cluster_label']} | {c['article_count']} |"
        for c in clusters
    )

    # Articles grouped by cluster for index sections
    by_cluster: dict[str, list[dict]] = {}
    for r in rows:
        label = r.get("cluster_label") or "Unclustered"
        by_cluster.setdefault(label, []).append(r)

    sections = []
    for label, arts in by_cluster.items():
        links = "\n".join(f"- [[{slug_map[a['article_id']]}]]" for a in arts)
        sections.append(f"### {label}\n{links}")

    index = (
        f"# {topic}\n\n"
        f"Analysed {len(rows)} articles across {len(clusters)} clusters.\n\n"
        "## Clusters\n\n"
        "| Cluster | Articles |\n"
        "|---------|----------|\n"
        f"{table_rows}\n\n"
        "## Articles by cluster\n\n"
        + "\n\n".join(sections)
    )
    files["_index.md"] = index

    return files


def _esc(s: str) -> str:
    """Escape double quotes for YAML inline strings."""
    return s.replace('"', '\\"')
