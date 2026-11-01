"""Write spec-tree.json of the vibetracks-feature-tree case: Vibe Tracks' own feature tree, as rows.

    python3 gallery/examples/vibetracks-feature-tree/source/make.py      # VIBETRACKS=~/vibetracks by default

Runs Vibe Tracks' own read-only `python3 -m vibetracks spec tree` (vibetracks/spec/tree.py, vt-spec-tree/1: track ->
area -> feature -> check, every state computed from each suite's latest run; it writes nothing without --write) in
the Vibe Tracks checkout, keeps four of its areas (AREAS), and flattens the tree into one row per node. A feature
note can sit under several areas (`vibe-areas`), so a row's id is its path from the track; `parent` is the row above
it. Every state and count is the tree's own (passed / total over distinct tests, a failure rolling up), carried as
data and never recomputed (docs/CONTRACT.md §2). The repo is public and so are its feature notes and test names.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
VIBETRACKS = pathlib.Path(os.environ.get("VIBETRACKS", "~/vibetracks"))
AREAS = ["area:sidebar", "area:home", "area:review", "area:track-page"]


def message(m) -> str | None:
    """A check's failure message: the runner's text, or its lines joined; an empty one is none."""
    if isinstance(m, list):
        m = "; ".join(str(x) for x in m if x)
    return m or None


def main() -> None:
    out = subprocess.run([sys.executable, "-m", "vibetracks", "spec", "tree"], cwd=VIBETRACKS, capture_output=True, text=True, check=True)
    doc = json.loads(out.stdout)
    root = doc["root"]
    rows = []

    def add(node: dict, parent: str | None, path: str) -> None:
        f = node.get("feature") if isinstance(node.get("feature"), dict) else {"id": node.get("feature")}
        last = node.get("last_run") or {}
        rows.append({
            "id": path, "parent": parent, "kind": node["kind"], "title": node.get("purpose") if node["kind"] == "check" and node.get("purpose") else node["title"],
            "name": node["title"] if node["kind"] == "check" else None, "feature": f.get("id"),
            "state": node.get("state"), "passed": node.get("passed"), "total": node.get("total"),
            "tests": f"{node['passed']}/{node['total']}" if node["kind"] != "check" and node.get("total") else None,
            "status": f.get("status"), "priority": f.get("priority"), "description": f.get("description"),
            "suite": node.get("suite"), "file": node.get("file"), "message": message(node.get("message")),
            "stale": bool(node.get("stale")) if node["kind"] == "check" else None,
            "last_run": (node.get("run_t") or last.get("t") or "")[:10] or None, "sha": (node.get("sha") or last.get("sha") or "")[:7] or None,
            "also": [a["title"] for a in node.get("also") or []] or None,
        })
        for child in node.get("children") or []:
            add(child, path, f"{path}/{child['id']}")

    rows.append(None)
    for area in root["children"]:
        if area["id"] in AREAS:
            add(area, "track", f"track/{area['id']}")
    rows[0] = {"id": "track", "parent": None, "kind": "track", "title": root["title"], "name": None, "feature": None, "state": root["state"],
               "passed": root["passed"], "total": root["total"], "tests": f"{root['passed']}/{root['total']}", "status": None, "priority": None,
               "description": f"the whole track: {len(root['children'])} areas; {len(AREAS)} of them below", "suite": None, "file": None,
               "message": None, "stale": None, "last_run": None, "sha": doc["head"]["short"][:7], "also": None}
    STATE = {"pass": 6, "fail": 8, "notrun": 4, "notests": 0}
    props = {
        "title": {"type": "text", "label": "Node"}, "parent": {"type": "text", "label": "Parent", "hidden": True},
        "kind": {"type": "text", "label": "Kind", "display": "badge", "colors": {"track": 7, "area": 1, "feature": 3, "check": 0}},
        "name": {"type": "text", "label": "Test"}, "feature": {"type": "text", "label": "Feature id"},
        "state": {"type": "text", "label": "State", "display": "badge", "colors": STATE, "labels": {"pass": "pass", "fail": "fail", "notrun": "not run yet", "notests": "no tests"},
                  "note": "computed from each suite's latest run; a failure rolls up to every ancestor"},
        "tests": {"type": "text", "label": "Passed / total", "align": "right"},
        "passed": {"type": "number", "label": "Passed", "hidden": True}, "total": {"type": "number", "label": "Tests", "hidden": True},
        "status": {"type": "text", "label": "Note status", "display": "badge",
                   "colors": {"done": 3, "review": 5, "running": 1, "waiting": 4, "ready": 7, "todo": 0, "backlog": 0, "archived": 0}, "note": "the feature note's vibe-status, as written"},
        "priority": {"type": "text", "label": "Priority"}, "description": {"type": "text", "label": "Description"},
        "suite": {"type": "text", "label": "Suite"}, "file": {"type": "text", "label": "File"}, "message": {"type": "text", "label": "Failure"},
        "stale": {"type": "boolean", "label": "Ran before the latest change"}, "last_run": {"type": "date", "label": "Last run"},
        "sha": {"type": "text", "label": "Commit"}, "also": {"type": "list", "label": "Also under"},
    }
    data = {"id": "vibetracks-spec-tree", "title": "Vibe Tracks feature tree", "titleProperty": "title",
            "source": f"vibetracks spec tree (vt-spec-tree/1) at {doc['head']['short']}, generated {doc['generated_at']}; areas {', '.join(AREAS)}",
            "properties": props, "rows": rows}
    (CASE / "spec-tree.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    kinds = {k: sum(r["kind"] == k for r in rows) for k in ("area", "feature", "check")}
    print(f"spec-tree.json: {len(rows)} rows {kinds}; failing: {[r['title'] for r in rows if r['state'] == 'fail' and r['kind'] != 'check']}")


if __name__ == "__main__":
    main()
