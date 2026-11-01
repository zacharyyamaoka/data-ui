"""Write this case's data: one row per (model, run) of the CAN 14 twin-error comparison, from the robotparts table
lane's snapshot.

    python3 gallery/examples/models-benches/source/build.py

Input: source/models-runs.json, copied unchanged from robotparts lane/tables @ ab5ba92
(design/tables-2026-10-25/snapshots/models-runs.json, itself read from lane/datasheet @ ec9a13c:
docs/proposals/build_models_report_r2.py, CAN 14 on suite bam-rack/1). One record per model and run: the twin's
joint-angle error, q RMS in mrad, against what the rack measured. Models with no run yet (M0, M1, most of M3, M5)
keep one row with q RMS null, so a pivot shows them as "—", not measured.

`variant` names a model and, where one model ran on several backends (M4.ripple), the backend, so a chart has one
row per thing that was scored. The floor (`floor_mrad`, 5 identical repeats of one tape) is written into the
dataset's source line; the twin-grade line in views.base is 1.5 x floor (lane/datasheet docs/proposals/models-2026-10-25.md §6: twin-grade means
held-out error at most 1.5 x the floor, 1.62 mrad).
"""

from __future__ import annotations

import collections
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]


def main() -> None:
    snap = json.loads((HERE / "source" / "models-runs.json").read_text(encoding="utf-8"))
    backends = collections.defaultdict(set)
    for r in snap["records"]:
        backends[r["model"]].add(r["backend"])
    rows = []
    for i, r in enumerate(snap["records"]):
        suffix = r["backend"].replace("MuJoCo + plugin", "").strip(" ,+") or "plugin"
        variant = r["model"] if len(backends[r["model"]]) == 1 else f"{r['model']} ({suffix})"
        rows.append({"id": f"r{i:03d}", "variant": variant, **{k: r[k] for k in ("model", "backend", "family", "rung", "about", "suite", "test", "run")},
                     "q_rms_mrad": None if r["q_rms_mrad"] is None else round(r["q_rms_mrad"], 4),
                     "x_floor": None if r["x_floor"] is None else round(r["x_floor"], 3),
                     "bench_steps": r["bench_steps"], "bench_min": r["bench_min"], "sensors_missing": r["sensors_missing"],
                     "model_order": r["model_order"]})
    floor = snap["floor_mrad"]
    data = {
        "id": "models-benches", "title": "Models × benches (CAN 14)", "titleProperty": "variant",
        "source": f"{snap['from']}; floor {floor:.4f} mrad (5 repeats of one tape), twin-grade = 1.5 x floor = {1.5 * floor:.2f} mrad",
        "properties": {
            "variant": {"type": "text", "width": 230}, "model": {"type": "text", "width": 160}, "backend": {"type": "text", "width": 250},
            "family": {"type": "text", "width": 230}, "rung": {"type": "text", "width": 60}, "about": {"type": "text", "width": 240},
            "suite": {"type": "text", "width": 170}, "test": {"type": "text", "width": 110}, "run": {"type": "text", "width": 300},
            "q_rms_mrad": {"type": "number", "unitText": "mrad", "decimals": 2, "width": 110, "better": "lower"},
            "x_floor": {"type": "number", "unitText": "× floor", "decimals": 2, "width": 100, "derived": f"q RMS / the {floor:.3f} mrad floor"},
            "bench_steps": {"type": "list", "width": 280}, "bench_min": {"type": "number", "unitText": "min", "width": 90},
            "sensors_missing": {"type": "list", "width": 220}, "model_order": {"type": "number", "hidden": True},
        },
        "records": {"columns": [{"id": "suite", "label": "Suite"}, {"id": "test", "label": "Test"}, {"id": "run", "label": "Run"},
                                {"id": "q_rms_mrad", "label": "q RMS (mrad)"}, {"id": "x_floor", "label": "× floor"}]},
        "rows": rows,
    }
    out = HERE / "models.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[2])}: {len(rows)} rows, {out.stat().st_size:,} bytes; floor {floor:.4f}, twin-grade {1.5 * floor:.4f} mrad")


if __name__ == "__main__":
    main()
