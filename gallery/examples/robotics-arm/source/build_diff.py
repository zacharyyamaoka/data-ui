"""The Robot arm template's difference tables (PEP 0010 P1d), on the stand-in: diff_poses.json (the tool, poses.json)
and diff_samples.json (the joints, samples.json), difference(a, b) for every pair the trajectory contract names
(gallery/robotics/CONTRACT.md §5: each situation against the target, each sim situation against each real one; b − a),
computed by the one shared implementation, gallery/robotics/difference.py, which reproduces the contract's fixture.
The suite's run gives real, real B and twin against the target and the twin against real and real B; pidtuna's run
gives factory, tuned and oracle against the target. Standard library only:

    python3 -B -I gallery/examples/robotics-arm/source/build_diff.py

Each number is written to 6 decimals (1e-6 of its unit: the display projection); tools/test_robotics_difference.py
recomputes every row from poses.json and samples.json and finds exactly these. Every situation shares its run's time
grid here, so b(tᵢ) is b's own sample: no row is interpolated."""

from __future__ import annotations

import json
import pathlib
import sys

CASE = pathlib.Path(__file__).resolve().parent.parent
ROBOTICS = CASE.parents[1] / "robotics"
sys.path.insert(0, str(ROBOTICS))
from difference import difference  # noqa: E402  the one difference(a, b)

DIGITS = 6
SOURCE = "STAND-IN, simulation only: difference(a, b) of {} (gallery/robotics/difference.py); written by gallery/examples/robotics-arm/source/build_diff.py"


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
    report = {}
    for src, dst, title in (("poses", "diff_poses", "Difference of the tool (stand-in): each situation against the target, the twin against real (b − a)"),
                            ("samples", "diff_samples", "Difference of the joints (stand-in): each situation against the target, the twin against real (b − a)")):
        doc = json.loads((CASE / f"{src}.json").read_text(encoding="utf-8"))
        rows = diff_table(doc["rows"])
        contract = json.loads((ROBOTICS / "schemas" / f"{dst}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]
        have = {k for r in rows for k in r}
        labels = next((f.get("labels") for f in doc["schema"]["fields"] if f["name"] == "run"), None)
        fields = [({**f, "labels": labels} if f["name"] == "run" and labels else f) for f in contract if f["name"] in have]
        write(CASE / f"{dst}.json", title, SOURCE.format(f"{src}.json"), fields, rows)
        counts = {}
        for r in rows:
            pair = f"{r['situation']} against {r['reference']}"
            counts[pair] = counts.get(pair, 0) + 1
        report[dst] = {"rows": len(rows), "pairs": counts, "bytes": (CASE / f"{dst}.json").stat().st_size}
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
