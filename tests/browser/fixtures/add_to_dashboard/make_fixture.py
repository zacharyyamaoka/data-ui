"""Writes the add-to-dashboard fixture's data (tests/browser/add_to_dashboard_checks.py, tests/unit/add-to-dashboard.test.mjs).

    python3 tests/browser/fixtures/add_to_dashboard/make_fixture.py

Synthetic and deterministic (a seeded generator, no clock): 36 runs over three robots, and every run's samples of three
joints over 2 s, so each kind of view a reader adds from has rows to draw: a table, a chart and KPI cards of the runs,
a time series and a 3D path of the samples (one series per joint), and a clock over the samples' t. Illustrative
numbers, said so in each file's `source`.
"""

import json
import math
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
rng = random.Random(20261029)
ROBOTS = ["A", "B", "C"]
JOINTS = ["J1", "J2", "J3"]
SOURCE = "synthetic: tests/browser/fixtures/add_to_dashboard/make_fixture.py (illustrative numbers)"


def write(name, doc):
    (HERE / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


runs = []
for i in range(36):
    run = f"r{i + 1:02d}"
    runs.append({
        "id": run, "run": run, "robot": ROBOTS[i % 3], "kind": "real" if i % 4 == 3 else "sim",
        "started": f"2026-10-{(i % 28) + 1:02d}", "success": round(0.5 + rng.random() * 0.49, 3), "duration_s": round(5 + rng.random() * 25, 1),
    })
write("runs.json", {
    "id": "a2d-runs", "title": "Runs", "titleProperty": "run", "source": SOURCE,
    "properties": {
        "run": {"type": "text", "label": "Run"}, "robot": {"type": "text", "label": "Robot"}, "kind": {"type": "text", "label": "Kind"},
        "started": {"type": "date", "label": "Started"}, "success": {"type": "number", "label": "Success rate", "decimals": 3},
        "duration_s": {"type": "number", "label": "Duration", "unitText": "s"},
    },
    "rows": runs,
})

samples = []
for r in runs[:6]:
    for j, joint in enumerate(JOINTS):
        for k in range(21):
            t = round(k * 0.1, 1)
            err = round(math.sin(t * 2 + j) * (j + 1) + rng.uniform(-0.2, 0.2), 3)
            samples.append({
                "id": f"{r['run']}-{joint}-{k:02d}", "run": r["run"], "joint": joint, "t": t, "err_mm": err,
                "x": round(0.2 + 0.1 * math.cos(t + j), 4), "y": round(0.1 * math.sin(t + j), 4), "z": round(0.3 + 0.05 * j + 0.02 * t, 4),
            })
write("samples.json", {
    "id": "a2d-samples", "title": "Samples", "titleProperty": "id", "source": SOURCE,
    "properties": {
        "run": {"type": "text", "label": "Run"}, "joint": {"type": "text", "label": "Joint"}, "t": {"type": "number", "label": "t", "unitText": "s"},
        "err_mm": {"type": "number", "label": "Error", "unitText": "mm"}, "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"},
    },
    "rows": samples,
})

# a different file the target dashboard already names `samples`: the source's samples, added there, are renamed
write("other-samples.json", {
    "id": "a2d-other", "title": "Other samples", "titleProperty": "id", "source": SOURCE,
    "rows": [{"id": f"o{k}", "run": "r01", "t": k * 0.5, "value": k} for k in range(5)],
})
