#!/usr/bin/env python3
"""Publish the browser checks' gate numbers to Vibe Tracks (the data-ui track's producer folder, vt-kpi/1).

    python3 tools/publish_checks.py [CHECKS_JSON] [--to ~/vt/zach/producers/data-ui] [--sha SHA]

`npm test` runs it after the browser checks (tools/test-all.mjs), so every run adds a point; set DATA_UI_KPI_PUBLISH=0
to skip. Today it publishes one KPI, read from the check's own value, never recomputed:

  mesh_first_frame_outline_pct  "3D first-frame vs thumbnail outline error (%)": the worst |width or height ratio - 1|
                                of the live model's frame-0 silhouette against its poster's, over the object-db-shelf
                                case's 10 cards (CONTRACT §29; gallery/examples/object-db-shelf/checks.py camera_match).
                                Lower is better; 3 % is the gate.

WHY here and not in bench/publish.py: the bench publishes timings from bench runs; this number is a correctness gate
the test suite measures, so the suite feeds it. Both write the same catalog (bench/kpi_catalog.json, which lists this
KPI), so neither publisher drops the other's KPIs. Stdlib only; writes only kpi_catalog.json and kpi_series.jsonl in
the producer folder; a missing folder or check is said and skipped, never an error for the test run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import socket
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bench" / "kpi_catalog.json"
KPIS = {
    # kpi id: (the check whose value carries it, the value key)
    "mesh_first_frame_outline_pct": ("3D camera: the live model's frame 0 matches its poster", "worst_pct"),
}


def sha() -> str:
    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()
    head = git("rev-parse", "--short", "HEAD") or "unknown"
    return head + ("+dirty" if git("status", "--porcelain", "--untracked-files=no") else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("checks", nargs="?", default=str(ROOT / "reports" / "media" / "phase0" / "checks.json"))
    ap.add_argument("--to", default=os.path.expanduser("~/vt/zach/producers/data-ui"))
    ap.add_argument("--sha")
    args = ap.parse_args(argv)
    out, checks_path = pathlib.Path(args.to), pathlib.Path(args.checks)
    if os.environ.get("DATA_UI_KPI_PUBLISH") == "0":
        print("publish_checks: DATA_UI_KPI_PUBLISH=0, nothing written")
        return 0
    if not out.is_dir():
        print(f"publish_checks: no producer folder {out}; nothing written")
        return 0
    if not checks_path.is_file():
        print(f"publish_checks: no {checks_path}; nothing written")
        return 0
    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    t = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    labels = {"lane": "chromium-desktop", "host": socket.gethostname(), "producer": "npm test (tools/publish_checks.py)"}
    points = []
    for kpi, (prefix, key) in KPIS.items():
        found = [c for c in checks if c["name"].startswith(prefix)]
        if not found:
            points.append({"schema": "vt-kpi-point/1", "kpi": kpi, "t": t, "value": None, "n": 0, "status": "not_measured",
                           "labels": {**labels, "why": f"no check named {prefix!r} in {checks_path.name}"}, "source": {"code_sha": args.sha or sha()}})
            continue
        c = found[-1]
        value = c["value"].get(key) if isinstance(c["value"], dict) else None
        points.append({"schema": "vt-kpi-point/1", "kpi": kpi, "t": t, "value": value, "n": c["value"].get("n", 0) if isinstance(c["value"], dict) else 0,
                       "status": "measured" if value is not None else "not_measured", "pass": bool(c["ok"]),
                       "labels": labels if value is not None else {**labels, "why": "the check's value has no " + key},
                       "source": {"code_sha": args.sha or sha(), "check": c["name"]}})
    catalog = dict(json.loads(CATALOG.read_text(encoding="utf-8")), generated_at=t)
    (out / "kpi_catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")
    with (out / "kpi_series.jsonl").open("a") as f:
        for p in points:
            f.write(json.dumps(p) + "\n")
    for p in points:
        print(f"publish_checks: {p['kpi']} = {p['value']} ({p['status']}{', pass' if p.get('pass') else ''}) -> {out / 'kpi_series.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
