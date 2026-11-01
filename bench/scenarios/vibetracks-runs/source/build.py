#!/usr/bin/env python3
"""Flatten Vibe Tracks' vt-run/1 lines (one per producer run) into one row per run. Stdlib only.
Usage: python3 build.py [runs_table.jsonl] [out.json]

A row is run_id, t, every facets.* key, every metrics.* key. `items` (the per-sample file) and `media` are dropped.
"""
import json
import pathlib
import sys

RUNS = "~/vt/zach/producers/aruco-studio/runs_table.jsonl"
OUT = pathlib.Path(__file__).resolve().parent.parent / "runs.json"


def flatten(run: dict) -> dict:
    row = {"run_id": run["run_id"], "t": run["t"]}
    row.update(run.get("facets") or {})
    row.update(run.get("metrics") or {})
    return row


def main() -> None:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else RUNS)
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    rows = [flatten(json.loads(line)) for line in src.read_text().splitlines() if line.strip()]
    props = {"run_id": {"type": "text", "width": 360}, "t": {"type": "datetime", "width": 170}}
    for key, value in rows[0].items():
        if key in props:
            continue
        props[key] = {"type": "number" if isinstance(value, (int, float)) else "text"}
        if key.endswith("_ms_sum"):
            props[key].update(unitText="ms", decimals=1)
    data = {"id": "runs", "title": "Runs", "titleProperty": "run_id", "properties": props, "rows": rows}
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(rows)} rows -> {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
