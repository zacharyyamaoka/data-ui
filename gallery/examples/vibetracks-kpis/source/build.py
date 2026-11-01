"""Write this case's data: Vibe Tracks' KPI points, one row per KPI reading, from its committed synthetic fixture.

    python3 gallery/examples/vibetracks-kpis/source/build.py

Input (read-only): VIBETRACKS (default ~/vibetracks) storybook/fixtures/synthetic/kpi-doc.syn.json, the
document Vibe Tracks' KPI panel reads for its synthetic grasp bench (vt-kpi-doc/1, written through its real read
API by storybook/scripts/make_kpi_fixtures.py). The models are made up ("a made-up grasp model"), so the case is
public-safe; no real track's figures are read.

Each row is one champion reading of one KPI (references and per-slice points are left out): the value is a rich
cell, {value, unit, basis, n, low, high, source, asOf}, with basis measured or estimate as the producer wrote it
(its `status`), n the runs behind it, low/high its confidence interval. Success rate is written in percent. The
fixture has no bench score, so that card's one row is {value: null, why}: shown as "—" with the reason, never 0.
`better` per row is the catalog's direction, so one KPI view holds KPIs that point both ways.
"""

from __future__ import annotations

import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
VT = pathlib.Path(os.environ.get("VIBETRACKS", "~/vibetracks"))
FIXTURE = VT / "storybook" / "fixtures" / "synthetic" / "kpi-doc.syn.json"
KPIS = {  # id -> (card title, unit, scale): the four the KPI section draws, in its order
    "sppm": ("Successful picks per minute (SPPM)", "picks/min", 1),
    "compute_mean_s": ("Computation time", "s", 1),
    "success_rate": ("Grasp success", "%", 100),
    "compute_p95_s": ("Computation time p95", "s", 1),
}


def main() -> None:
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    catalog = {k["id"]: k for k in doc["catalog"]["kpis"]}
    rows = []
    for p in doc["series"]:
        labels = p.get("labels") or {}
        if p["kpi"] not in KPIS or p.get("slice") or labels.get("role") != "champion":
            continue
        title, unit, scale = KPIS[p["kpi"]]
        runs = p["source"].get("run_ids") or []
        if p["value"] is None:  # a reading the producer did not take: a gap in the line, never 0
            cell = {"value": None, "unit": unit, "why": "not reported for this build", "asOf": p["t"]}
        else:
            cell = {"value": round(p["value"] * scale, 4), "unit": unit, "basis": p["status"], "n": len(runs),
                    "source": f"{doc['catalog']['title']}: {', '.join(runs)}", "asOf": p["t"]}
        if p.get("ci"):
            cell["low"], cell["high"] = round(p["ci"][0] * scale, 4), round(p["ci"][1] * scale, 4)
        rows.append({"id": f"{p['kpi']}-{len([r for r in rows if r['kpi'] == p['kpi']]) + 1:02d}", "kpi": p["kpi"], "label": title,
                     "t": p["t"], "value": cell, "better": catalog[p["kpi"]]["direction"], "model": labels.get("model"),
                     "lane": labels.get("lane"), "bench": p["source"].get("bench_version"), "commit": p["source"].get("code_sha"),
                     "runs": len(runs), "run_ids": runs})
    latest = max(r["t"] for r in rows)
    rows.append({"id": "bench_score-01", "kpi": "bench_score", "label": "Bench score", "t": latest,
                 "value": {"value": None, "why": "not in the synthetic fixture (the real one is the grasp bench's scoreboard)"},
                 "better": "higher", "model": None, "lane": None, "bench": None, "commit": None, "runs": 0, "run_ids": []})
    data = {
        "id": "vibetracks-kpis", "title": "Vibe Tracks KPIs (synthetic grasp bench)", "titleProperty": "label",
        "source": f"vibetracks {FIXTURE.relative_to(VT)} (vt-kpi-doc/1, synthetic: made-up models)",
        "properties": {
            "label": {"type": "text", "width": 240}, "kpi": {"type": "text", "hidden": True},
            "t": {"type": "date", "width": 190}, "value": {"type": "number", "width": 150},
            "better": {"type": "text", "width": 70}, "model": {"type": "text", "width": 120, "display": "badge"},
            "lane": {"type": "text", "width": 90}, "bench": {"type": "text", "width": 70}, "commit": {"type": "text", "width": 90},
            "runs": {"type": "number", "width": 60}, "run_ids": {"type": "list", "width": 380},
        },
        "rows": rows,
    }
    out = HERE / "kpis.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[2])}: {len(rows)} rows, {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
