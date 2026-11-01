"""The Servo template's difference table (PEP 0010 P1d): diff_samples.json, difference(a, b) of samples.json for every
pair the trajectory contract names (gallery/robotics/CONTRACT.md §5: each situation against the target, each sim
situation against each real one; here real and twin against the target, and the twin against real; b − a), computed
by the one shared implementation, gallery/robotics/difference.py, which reproduces the contract's fixture. Standard
library only:

    python3 -B -I gallery/examples/robotics-servo/source/build_diff.py

Each number is written to 6 decimals (1e-6 of its unit: the display projection); tools/test_robotics_difference.py
recomputes every row from samples.json and finds exactly these."""

from __future__ import annotations

import json
import pathlib
import sys

CASE = pathlib.Path(__file__).resolve().parent.parent
ROBOTICS = CASE.parents[1] / "robotics"
sys.path.insert(0, str(ROBOTICS))
from difference import difference  # noqa: E402  the one difference(a, b)

DIGITS = 6


def pairs(rows):
    """(a, b): each situation against each target, then each sim situation against each real one."""
    family = {}
    for r in rows:
        family.setdefault(r["situation"], r["source"])
    sits = sorted(family)
    return [(a, b) for b in sits if family[b] == "target" for a in sits if a != b] + \
        [(a, b) for a in sits if family[a] == "sim" for b in sits if family[b] == "real"]


def diff_table(rows):
    out = []
    for a, b in pairs(rows):
        out += difference([r for r in rows if r["situation"] == a], [r for r in rows if r["situation"] == b])
    return [{k: (round(v, DIGITS) if isinstance(v, float) else v) for k, v in r.items()} for r in out]


def write(path, title, source, fields, rows):
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def main() -> int:
    samples = json.loads((CASE / "samples.json").read_text(encoding="utf-8"))
    rows = diff_table(samples["rows"])
    contract = json.loads((ROBOTICS / "schemas" / "diff_samples.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]
    have = {k for r in rows for k in r}
    labels = next((f.get("labels") for f in samples["schema"]["fields"] if f["name"] == "run"), None)
    fields = [({**f, "labels": labels} if f["name"] == "run" and labels else f) for f in contract if f["name"] in have]
    write(CASE / "diff_samples.json", "Difference: each situation against the target, and the twin against real (b − a)",
          "difference(a, b) of samples.json (gallery/robotics/difference.py); written by gallery/examples/robotics-servo/source/build_diff.py",
          fields, rows)
    counts = {}
    for r in rows:
        pair = f"{r['situation']} against {r['reference']}"
        counts[pair] = counts.get(pair, 0) + 1
    print(json.dumps({"rows": len(rows), "pairs": counts, "bytes": (CASE / "diff_samples.json").stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
