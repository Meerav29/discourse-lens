"""
Rebuild the map and topics of finished analyses from their stored embeddings,
without crawling again. Use after changing the topic model, or to upgrade maps
made by older versions.

    uv run python -m scripts.recluster <analysis-id> [<analysis-id> ...]
    uv run python -m scripts.recluster --all

Each run makes one Claude request per analysis (to name its topics).
"""

from __future__ import annotations

import argparse
import sys

from backend.db import connect, init_db
from backend.embedding.project import run_projection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ids", nargs="*", help="analysis ids (prefixes are fine)")
    parser.add_argument("--all", action="store_true", help="every finished analysis")
    args = parser.parse_args(argv)
    if not args.ids and not args.all:
        parser.error("give analysis ids or --all")

    init_db()
    conn = connect()
    done = conn.execute(
        "SELECT id, topic FROM analyses WHERE status = 'done' ORDER BY created_ts"
    ).fetchall()
    conn.close()
    targets = done if args.all else [
        a for a in done if any(a["id"].startswith(prefix) for prefix in args.ids)
    ]
    if not targets:
        print("No matching finished analyses.", file=sys.stderr)
        return 1

    for a in targets:
        print(f"\n{a['topic']} ({a['id'][:8]})")
        run_projection(
            a["id"],
            on_step=lambda _f, detail: print(f"  {detail}"),
            on_label=lambda label, n: print(f"    {label} ({n} articles)"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
