"""The Servo template's coverage (PEP 0010 P2; §4.4's rules and §6's coverage panels): every rack run of its servos,
decimated for the coverage panels and written as the trajectory contract's coverage_samples (gallery/robotics/
CONTRACT.md; schemas/coverage_samples.schema.json): coverage_samples.csv and its coverage_samples.schema.json sidecar.

    python3 -B -I gallery/examples/robotics-servo/source/build_coverage.py
        the case's file: every CAN 12 and CAN 14 run of Oct 23-25 (278), at 1 Hz plus each run's extremes
    python3 -B -I gallery/examples/robotics-servo/source/build_coverage.py --deployment DIR
        the deployment's file, into DIR (never the case): every rack run (1,000, eight servos) at the largest whole
        display rate that keeps it ≤ 150,000 rows (PEP 0010 §4.4's budget). tests/browser/p2_checks.py draws the
        template's own coverage panels over it and times a rail click; it is not committed (Zach's source-only rule)

numpy only (any venv). Read-only: /archive/datasets/bam_rig/rack_2026-10-2{3,4,5} (every runs/*.npz with ≥ 20 samples
and its json: can_id, kind) and bam_rack_twin's deployment record (records/one-dof-test-rack/deployment.json in the
sim-to-real worktree, or $BAM_RACK_TWIN_RECORD) for each board's frame when the run started. It writes nothing there.

The display projection (CONTRACT §4.4):
  - rows picked on a uniform time grid (display_hz; the first logged row at or after each grid time), weight w = 1, so
    Σ w ÷ display_hz is the seconds a servo spent in a bin; never averaged;
  - plus each run's argmin and argmax row of every channel written (q, qd), w = 0, so a histogram (Σ w) stays
    unbiased while the min and max over rows are the full-rate min and max exactly (the box plot's whiskers;
    Jugel et al.'s M4, weighted);
  - q_deg and qd_deg_s in the joint's output frame: the board's radians × output_per_board of its config at the run's
    start (bam_rack_twin.stations.Station.at's rule, read from the record), in degrees, rounded to the decimals the
    sidecar declares (q 0.001°, qd 0.01°/s);
  - t in s from the run's first logged row; one situation per run, `real` (family real): the board's own log.
WHY 1 Hz in the case: the case publishes at most 5 MB (tests/unit/robotics-templates.test.mjs) and the playback tables
take 4.6 MB of it; 1 Hz over CAN 12's and CAN 14's 2,071 s keeps the coverage to about a quarter of a MB.
The run id is the Servo template's (source/build.py's run_id: day/folder/session, e.g. 10-24/dataset/can14/s01) plus
the stem's words after its kind, so a session's tape_fast, tape_medium and tape_slow stay three runs (s05-fast)."""

from __future__ import annotations

import argparse
import csv
import datetime
import glob
import json
import math
import os
import pathlib
import sys

import numpy as np

sys.dont_write_bytecode = True

CASE = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = pathlib.Path("/archive/datasets/bam_rig")
DAYS = ("rack_2026-10-23", "rack_2026-10-24", "rack_2026-10-25")
RECORD = pathlib.Path(os.environ.get("BAM_RACK_TWIN_RECORD", str(pathlib.Path.home() / "bam_ws" / ".claude" / "worktrees" / "sim-to-real-motor-models-f1ee43"
                                                                 / "src" / "dev" / "bam_rack_twin" / "records" / "one-dof-test-rack" / "deployment.json")))
CASE_CANS = (12, 14)
CASE_HZ = 1.0
MAX_ROWS = 150_000
MIN_SAMPLES = 20
# file column -> (npz array, decimals): the channels the coverage panels read (angle, velocity)
CHANNELS = {"q_deg": ("q", 3), "qd_deg_s": ("qd", 2)}


def run_id(npz: pathlib.Path) -> str:
    rel = npz.relative_to(ARCHIVE)
    day = rel.parts[0].removeprefix("rack_2026-")
    folder = [p for p in rel.parts[1:-1] if p != "runs"]
    parts = npz.stem.split("_")
    tail = "-".join(parts[3:])
    return "/".join([day, *folder, parts[0] + (f"-{tail}" if tail else "")])


def frames(path: pathlib.Path) -> dict[int, list[tuple[str | None, float]]]:
    """{can_id: [(since_utc, output_per_board)…]} oldest first, from the deployment record; {} when it is not there."""
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for c in doc.get("components", []):
        if c.get("can_id") is None:
            continue
        hist = c.get("config_history") or []
        if hist:
            out[int(c["can_id"])] = [(h.get("since_utc"), float((h.get("frame") or {}).get("output_per_board", 1.0))) for h in hist]
        else:
            out[int(c["can_id"])] = [(None, float((c.get("frame") or {}).get("output_per_board", 1.0)))]
    return out


def output_per_board(table, can: int, utc: str) -> float:
    """The board's frame when the run started: its newest config whose since_utc is at or before it (the first before
    any), as bam_rack_twin.stations.Station.at reads the record."""
    hist = table.get(can)
    if not hist:
        return 1.0
    k = hist[0][1]
    for since, v in hist:
        if since is None or since <= utc:
            k = v
    return k


def rack_runs(cans=None) -> list[dict]:
    out = []
    for day in DAYS:
        for meta_path in sorted(glob.glob(str(ARCHIVE / day / "**" / "runs" / "*.json"), recursive=True)):
            try:
                meta = json.loads(pathlib.Path(meta_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            npz = pathlib.Path(meta_path).with_suffix(".npz")
            can = meta.get("can_id")
            if not npz.exists() or can is None or (cans is not None and can not in cans):
                continue
            out.append({"npz": npz, "run": run_id(npz), "can": int(can), "kind": meta.get("kind") or "?"})
    return out


def load(run: dict, table) -> dict | None:
    with np.load(run["npz"]) as a:
        t = np.asarray(a["t"], float)
        if t.size < MIN_SAMPLES:
            return None
        utc = datetime.datetime.fromtimestamp(float(a["wall"][0]), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        k = output_per_board(table, run["can"], utc)
        cols = {name: np.degrees(np.asarray(a[src], float) * k) for name, (src, _) in CHANNELS.items()}
    return {**run, "t": t - t[0], "cols": cols, "utc": utc, "output_per_board": k}


def picks(t: np.ndarray, hz: float) -> np.ndarray:
    """The first logged row at or after each time of a uniform grid at hz."""
    grid = np.arange(0.0, t[-1] + 1e-9, 1.0 / hz)
    return np.unique(np.clip(np.searchsorted(t, grid), 0, t.size - 1))


def extremes(run: dict, kept: np.ndarray) -> list[int]:
    out = set()
    for v in run["cols"].values():
        if np.isfinite(v).any():
            out.update((int(np.nanargmin(v)), int(np.nanargmax(v))))
    return sorted(out - set(kept.tolist()))


def num(v: float, digits: int):
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


def write(out_dir: pathlib.Path, runs: list[dict], hz: float, note: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with (out_dir / "coverage_samples.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        cols = ["t", "run", "situation", "source", "device", "kind", *CHANNELS, "w"]
        w.writerow(cols)
        for run in runs:
            kept = picks(run["t"], hz)
            for i, weight in [(int(i), 1) for i in kept] + [(i, 0) for i in extremes(run, kept)]:
                w.writerow([num(run["t"][i], 3), run["run"], "real", "real", f"CAN {run['can']}", run["kind"],
                            *[num(run["cols"][c][i], d) for c, (_, d) in CHANNELS.items()], weight])
                n += 1
    fields = [
        {"name": "t", "type": "number", "unit": "s", "description": "seconds from the run's first logged row"},
        {"name": "run", "type": "string", "title": "Run", "description": "day/folder/session under the rack's archive (the Servo template's run id)"},
        {"name": "situation", "type": "string", "title": "Situation"},
        {"name": "source", "type": "string", "title": "Family"},
        {"name": "device", "type": "string", "title": "Servo"},
        {"name": "kind", "type": "string", "title": "Run kind"},
        {"name": "q_deg", "type": "number", "unit": "deg", "title": "Angle", "decimals": 3, "description": "joint angle, the output frame"},
        {"name": "qd_deg_s", "type": "number", "unit": "deg/s", "title": "Velocity", "decimals": 2},
        {"name": "w", "type": "number", "title": "Weight", "description": "1 on the time grid (display_hz), 0 on a run's kept argmin / argmax rows: a histogram sums w, min and max over rows are the full-rate ones"},
    ]
    servos = ", ".join(f"CAN {c}" for c in sorted({r["can"] for r in runs}))
    side = {
        "name": "coverage_samples", "title": f"Coverage: {len(runs)} rack runs of {servos}",
        "source": "/archive/datasets/bam_rig rack_2026-10-23, -24 and -25 (every runs/*.npz with ≥ 20 samples), read-only; written by "
                  "gallery/examples/robotics-servo/source/build_coverage.py",
        "display_hz": hz, "runs": len(runs), "frame": note, "schema": {"fields": fields},
    }
    (out_dir / "coverage_samples.schema.json").write_text(json.dumps(side, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deployment", type=pathlib.Path, help="write every rack run (≤ 150,000 rows) into this folder instead of the case")
    args = ap.parse_args(argv)
    table = frames(RECORD)
    note = ("the joint's output frame: board radians × output_per_board of the board's config at the run's start "
            "(bam_rack_twin records/one-dof-test-rack/deployment.json)") if table else \
        "board radians as logged: the bam_rack_twin record was not found, so no frame was applied"
    cans = None if args.deployment else CASE_CANS
    runs = [r for r in (load(r, table) for r in rack_runs(cans)) if r is not None]
    runs.sort(key=lambda r: (r["utc"], r["run"]))
    ids = [r["run"] for r in runs]
    assert len(set(ids)) == len(ids), "every run id is its own"
    if args.deployment:
        # the largest whole display rate that keeps every run ≤ MAX_ROWS rows (extremes included)
        hz = 20.0
        while hz > 1:
            total = 0
            for r in runs:
                kept = picks(r["t"], hz)
                total += kept.size + len(extremes(r, kept))
            if total <= MAX_ROWS:
                break
            hz -= 1.0
        n = write(args.deployment, runs, hz, note)
    else:
        hz = CASE_HZ
        n = write(CASE, runs, hz, note)
    print(json.dumps({"runs": len(runs), "rows": n, "display_hz": hz, "frames": "record" if table else "none",
                      "not output frame": sorted({r["run"] for r in runs if r["output_per_board"] != 1.0})[:20]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
