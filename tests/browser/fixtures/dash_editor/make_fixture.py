"""Writes the dashboard editor fixture's data (tests/browser/dash_editor_checks.py; the rows of the babble of 2026-10-29).

    python3 tests/browser/fixtures/dash_editor/make_fixture.py

A small dashboard built on the Servo template's own files (gallery/examples/robotics-servo): six of its forty real rack
runs, three of CAN 12 and three of CAN 14, and every sample of those six runs (real, twin and target), as the template
wrote them. Nothing is synthesised: rows are copied, and the schema's run labels are cut to the six runs kept.

WHY six runs and not forty: the editor checks load this dashboard dozens of times, and these files are committed,
so the data stays under ~400 KB raw.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SERVO = HERE.parents[3] / "gallery" / "examples" / "robotics-servo"
# newest first, as the template's rail orders them: three of CAN 12 (Oct 25) and three of CAN 14 (Oct 24)
KEEP = [
    "10-25/dataset_rotor/can12_rest2/s03",
    "10-25/dataset_rotor/can12/s07",
    "10-25/dataset_rotor/can12/s03",
    "10-24/floors/can14/s05",
    "10-24/dataset/can14/s07",
    "10-24/dataset/can14/s03",
]


def cut(doc, rows):
    """The file with only `rows`, its run labels cut to the runs kept, its source saying where it came from."""
    out = {k: v for k, v in doc.items() if k != "rows"}
    out["title"] = doc["title"].replace("40 real rack runs", "6 real rack runs")
    out["source"] = f"{doc['source']}; six runs of it copied by tests/browser/fixtures/dash_editor/make_fixture.py"
    fields = []
    for f in doc["schema"]["fields"]:
        f = dict(f)
        if "labels" in f:
            f["labels"] = {k: v for k, v in f["labels"].items() if k in KEEP}
        fields.append(f)
    out["schema"] = {**doc["schema"], "fields": fields}
    out["rows"] = rows
    return out


def main():
    runs = json.loads((SERVO / "runs.json").read_text(encoding="utf-8"))
    samples = json.loads((SERVO / "samples.json").read_text(encoding="utf-8"))
    by_run = {r["run"]: r for r in runs["rows"]}
    missing = [k for k in KEEP if k not in by_run]
    if missing:
        raise SystemExit(f"runs not in the Servo template: {missing}")
    kept_runs = [by_run[k] for k in KEEP]
    kept_samples = [s for s in samples["rows"] if s["run"] in KEEP]
    for name, doc in (("runs.json", cut(runs, kept_runs)), ("samples.json", cut(samples, kept_samples))):
        (HERE / name).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"runs.json: {len(kept_runs)} runs; samples.json: {len(kept_samples)} samples")


if __name__ == "__main__":
    main()
