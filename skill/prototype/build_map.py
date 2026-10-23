#!/usr/bin/env python3
"""Validate a discourse-lens contract JSON and inline it into the map template.

    python build_map.py contract.json map.html     # validate, then write the page
    python build_map.py --check contract.json      # validate only

Standard library only (the Claude.ai sandbox may not have jsonschema). Checks the
schema in skill/contract.schema.json plus the cross-field rules in design.md
section 5. Exits 1 and lists every problem when the contract is invalid.
Same input, same bytes out.
"""
import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
PLACEHOLDER = "__CONTRACT_JSON__"
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
URL = re.compile(r"^https?://")


def validate(c):
    errs = []

    def need(obj, keys, where):
        for k in keys:
            if k not in obj:
                errs.append(f"{where}: missing '{k}'")
        return all(k in obj for k in keys)

    def typ(v, t, where, nullable=False):
        if v is None and nullable:
            return True
        ok = isinstance(v, t) and not (t in (int, (int, float)) and isinstance(v, bool))
        if not ok:
            errs.append(f"{where}: expected {getattr(t, '__name__', 'number')}, got {type(v).__name__}")
        return ok

    def maxlen(v, n, where):
        if isinstance(v, str) and len(v) > n:
            errs.append(f"{where}: {len(v)} chars, max {n}")

    def enum(v, allowed, where):
        if v not in allowed:
            errs.append(f"{where}: {v!r} not one of {sorted(allowed)}")

    if not isinstance(c, dict):
        return ["top level: expected an object"]
    if not need(c, ["topic", "article_count", "clusters", "articles", "propositions"], "top level"):
        return errs
    if "schema_version" in c and c["schema_version"] != 1:
        errs.append("schema_version: must be 1")
    if typ(c["topic"], str, "topic") and not c["topic"]:
        errs.append("topic: empty")
    typ(c["article_count"], int, "article_count")
    for k, q in enumerate(c.get("queries") or []):
        w = f"queries[{k}]"
        if typ(q, dict, w) and need(q, ["q"], w):
            typ(q["q"], str, w + ".q")
            if "purpose" in q:
                enum(q["purpose"], {"overview", "facet", "dissent", "recent", "user"}, w + ".purpose")

    clusters, articles, props = c["clusters"], c["articles"], c["propositions"]
    if not (typ(clusters, list, "clusters") and typ(articles, list, "articles") and typ(props, list, "propositions")):
        return errs

    cids = set()
    for k, cl in enumerate(clusters):
        w = f"clusters[{k}]"
        if not (typ(cl, dict, w) and need(cl, ["cluster_id", "label", "description", "article_count", "terms"], w)):
            continue
        if typ(cl["cluster_id"], int, w + ".cluster_id"):
            if cl["cluster_id"] < 0:
                errs.append(f"{w}.cluster_id: must be >= 0")
            if cl["cluster_id"] in cids:
                errs.append(f"{w}.cluster_id: duplicate {cl['cluster_id']}")
            cids.add(cl["cluster_id"])
        typ(cl["label"], str, w + ".label")
        maxlen(cl["label"], 40, w + ".label")
        typ(cl["description"], str, w + ".description")
        maxlen(cl["description"], 300, w + ".description")
        typ(cl["article_count"], int, w + ".article_count")
        if typ(cl["terms"], list, w + ".terms"):
            if len(cl["terms"]) > 12:
                errs.append(f"{w}.terms: {len(cl['terms'])} items, max 12")
            for j, t in enumerate(cl["terms"]):
                ok = isinstance(t, str) or (
                    isinstance(t, list) and len(t) == 2 and isinstance(t[0], str)
                    and isinstance(t[1], (int, float)) and not isinstance(t[1], bool))
                if not ok:
                    errs.append(f"{w}.terms[{j}]: expected a string or [term, weight]")
        for j, r in enumerate(cl.get("related") or []):
            rw = f"{w}.related[{j}]"
            if typ(r, dict, rw) and need(r, ["cluster_id", "strength"], rw):
                if typ(r["strength"], (int, float), rw + ".strength") and not 0 <= r["strength"] <= 1:
                    errs.append(f"{rw}.strength: must be 0..1")
    for k, cl in enumerate(clusters):
        for j, r in enumerate((cl.get("related") or []) if isinstance(cl, dict) else []):
            if isinstance(r, dict) and r.get("cluster_id") not in cids:
                errs.append(f"clusters[{k}].related[{j}]: unknown cluster_id {r.get('cluster_id')}")

    ids, members = set(), {}
    for k, a in enumerate(articles):
        w = f"articles[{k}]"
        if not (typ(a, dict, w) and need(a, ["id", "url", "domain", "title", "cluster_id"], w)):
            continue
        if typ(a["id"], str, w + ".id"):
            if not a["id"]:
                errs.append(f"{w}.id: empty")
            if a["id"] in ids:
                errs.append(f"{w}.id: duplicate {a['id']!r}")
            ids.add(a["id"])
        if typ(a["url"], str, w + ".url") and not URL.match(a["url"]):
            errs.append(f"{w}.url: must start with http:// or https://")
        typ(a["domain"], str, w + ".domain")
        typ(a["title"], str, w + ".title", nullable=True)
        pd = a.get("publish_date")
        if typ(pd, str, w + ".publish_date", nullable=True) and pd is not None and not DATE.match(pd):
            errs.append(f"{w}.publish_date: {pd!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
        if typ(a["cluster_id"], int, w + ".cluster_id"):
            cid = a["cluster_id"]
            if cid != -1 and cid not in cids:
                errs.append(f"{w}.cluster_id: unknown cluster {cid}")
            members[cid] = members.get(cid, 0) + 1
        for f in ("x", "y"):
            if f in a:
                typ(a[f], (int, float), f"{w}.{f}")
        if "fit" in a:
            enum(a["fit"], {"core", "edge"}, w + ".fit")
        if "also_cluster_id" in a:
            if a["also_cluster_id"] not in cids:
                errs.append(f"{w}.also_cluster_id: unknown cluster {a['also_cluster_id']}")
            elif a["also_cluster_id"] == a["cluster_id"]:
                errs.append(f"{w}.also_cluster_id: same as cluster_id")
        if "read_depth" in a:
            enum(a["read_depth"], {"full", "snippet"}, w + ".read_depth")
        if "source_type" in a:
            enum(a["source_type"], {"news", "explainer", "academic", "report", "blog", "reference", "other"}, w + ".source_type")
        for f, n in (("summary", 300), ("quote", 120)):
            if f in a and typ(a[f], str, f"{w}.{f}"):
                maxlen(a[f], n, f"{w}.{f}")

    if isinstance(c["article_count"], int) and c["article_count"] != len(articles):
        errs.append(f"article_count: {c['article_count']} but {len(articles)} articles")
    for k, cl in enumerate(clusters):
        if isinstance(cl, dict) and isinstance(cl.get("article_count"), int):
            have = members.get(cl.get("cluster_id"), 0)
            if cl["article_count"] != have:
                errs.append(f"clusters[{k}].article_count: {cl['article_count']} but {have} articles have cluster_id {cl.get('cluster_id')}")

    for k, p in enumerate(props):
        w = f"propositions[{k}]"
        if not (typ(p, dict, w) and need(p, ["position", "statement", "stances"], w)):
            continue
        if typ(p["position"], int, w + ".position") and p["position"] != k:
            errs.append(f"{w}.position: {p['position']}, expected {k} (0..n-1 in order)")
        typ(p["statement"], str, w + ".statement")
        maxlen(p["statement"], 250, w + ".statement")
        if not typ(p["stances"], list, w + ".stances"):
            continue
        if len(p["stances"]) < 2:
            errs.append(f"{w}.stances: {len(p['stances'])} stance(s), need at least 2")
        seen = set()
        for j, s in enumerate(p["stances"]):
            sw = f"{w}.stances[{j}]"
            if not (typ(s, dict, sw) and need(s, ["article_id", "stance", "claim"], sw)):
                continue
            if s["article_id"] not in ids:
                errs.append(f"{sw}.article_id: {s['article_id']!r} is not an article id")
            if s["article_id"] in seen:
                errs.append(f"{sw}.article_id: {s['article_id']!r} has two stances on this proposition")
            seen.add(s["article_id"])
            enum(s["stance"], {"agrees", "qualifies", "disputes"}, sw + ".stance")
            if typ(s["claim"], str, sw + ".claim"):
                maxlen(s["claim"], 250, sw + ".claim")
    return errs


def render(contract):
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise SystemExit("template.html must contain the placeholder exactly once")
    data = json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
    # Keep the JSON inert inside <script>: no '</' or '<!--' can end or confuse the block.
    data = data.replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return template.replace(PLACEHOLDER, data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("contract")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args(argv)
    try:
        contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read {args.contract}: {e}", file=sys.stderr)
        return 1
    errs = validate(contract)
    if errs:
        print(f"error: {args.contract} is not a valid contract ({len(errs)} problem(s)):", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    if args.check or not args.out:
        print(f"ok: {args.contract} ({len(contract['articles'])} articles, {len(contract['clusters'])} topics, "
              f"{len(contract['propositions'])} propositions)")
        return 0
    html = render(contract)
    Path(args.out).write_bytes(html.encode("utf-8"))
    print(f"wrote {args.out} ({len(html.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
