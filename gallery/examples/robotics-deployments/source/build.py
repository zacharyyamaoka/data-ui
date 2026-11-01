"""The navigation case's data (PEP 0010 P3, docs/peps/0010-robotics-playback.md §8): the deployments registry, its runs,
and one file per run, written beside this folder as the trajectory contract's tables (gallery/robotics/CONTRACT.md):

    ~/psu-atlas/.venv/bin/python -B -I gallery/examples/robotics-deployments/source/build.py     (numpy; read-only)

Inputs, read-only:
  - RACK (default /archive/datasets/bam_rig), rack_2026-10-28 and rack_2026-10-29: every run npz under a runs/ folder
    (t, wall, q, q_target, qd, qd_target, tau, i_q, …, the board's own log) and its sidecar .json (can_id, kind), kept
    when it has at least 20 samples (PEP 0010's rack rule) and lasts at most MAX_S;
  - bam_rack_twin's deployment record (~/bam_ws/.claude/worktrees/sim-to-real-motor-models-f1ee43/src/dev/bam_rack_twin/
    records/one-dof-test-rack/deployment.json, or $BAM_RACK_TWIN_RECORD): the deployment's id and kind, its stations, and
    each board's frame when a run started (output_per_board, as robotics-servo's build_coverage.py reads it);
  - sim2real's registry (~/sim2real/app/registry.json, or $SIM2REAL_REGISTRY): the deployment's title, where it stands
    and its one-line summary, as the sim2real host lists it.

What it writes (PER_STATION newest runs of each station: the case stays small):
  - deployments.json: the host's registry row (PEP 0010 §8 level 1), with this case's run count and its first and last run;
  - runs.json: one row per run, newest last in the file (the views sort it), `run` a path-safe id (day~folder…~step: the
    file name of its samples), the contract's columns plus `device` (the station) and `label`;
  - runs/<run>.json: that run's samples, picked on a uniform DISPLAY_HZ grid (the first logged row at or after each grid
    time, plus the last row; never averaged), two situations on the same rows: `real` (the board's log: q, qd, tau, i_q)
    and `target` (the commanded q_target and qd_target; no torque or current). q and qd in the joint's output frame
    (board radians × output_per_board), in degrees; t in s from the run's first logged row.
Self-checks before writing (the build stops when one fails): every written q equals the npz at its row; every run id is
its own and path-safe; every run's file holds only that run's rows.
"""

from __future__ import annotations

import datetime
import glob
import json
import math
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import numpy as np

CASE = pathlib.Path(__file__).resolve().parents[1]
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
DAYS = ("rack_2026-10-28", "rack_2026-10-29")
HOME = pathlib.Path.home()
RECORD = pathlib.Path(os.environ.get("BAM_RACK_TWIN_RECORD", str(HOME / "bam_ws" / ".claude" / "worktrees" / "sim-to-real-motor-models-f1ee43" / "src" / "dev"
                                                                 / "bam_rack_twin" / "records" / "one-dof-test-rack" / "deployment.json")))
REGISTRY = pathlib.Path(os.environ.get("SIM2REAL_REGISTRY", str(HOME / "sim2real" / "app" / "registry.json")))
PER_STATION = 3
MIN_SAMPLES = 20
MAX_S = 15.0         # WHY: a 70 s staircase would weigh as much as twenty waypoint runs; a short run shows the same navigation
DISPLAY_HZ = 25.0    # WHY 25: ~a quarter of the ~94 Hz log keeps each run's file near 25 KB and the curves' shape
LOCAL = ZoneInfo("America/Vancouver")   # the rig's wall clock: `started` reads as the log says it happened
SAFE = re.compile(r"^[A-Za-z0-9_.~-]+$")   # a run id names its file and rides in a URL as one path segment


def run_id(npz: pathlib.Path) -> str:
    """day~folder…~step: the archive path under the day folder without `runs`, the stem's step (and any words after its
    kind, so a session's tape_fast and tape_slow stay two runs), joined by ~ (unreserved in a URL, so the id is its own
    file name and one URL path segment as it is)."""
    rel = npz.relative_to(RACK)
    day = rel.parts[0].removeprefix("rack_2026-")
    folder = [p for p in rel.parts[1:-1] if p != "runs"]
    parts = npz.stem.split("_")
    tail = "-".join(parts[3:])
    return "~".join([day, *folder, parts[0] + (f"-{tail}" if tail else "")])


def frames(record: dict) -> dict[int, list[tuple[str | None, float]]]:
    """{can_id: [(since_utc, output_per_board)…]} oldest first (robotics-servo/source/build_coverage.py's reading)."""
    out = {}
    for c in record.get("components", []):
        if c.get("can_id") is None:
            continue
        hist = c.get("config_history") or []
        if hist:
            out[int(c["can_id"])] = [(h.get("since_utc"), float((h.get("frame") or {}).get("output_per_board", 1.0))) for h in hist]
        else:
            out[int(c["can_id"])] = [(None, float((c.get("frame") or {}).get("output_per_board", 1.0)))]
    return out


def output_per_board(table, can: int, utc: str) -> float:
    """The board's frame when the run started: its newest config whose since_utc is at or before it."""
    hist = table.get(can)
    if not hist:
        return 1.0
    k = hist[0][1]
    for since, v in hist:
        if since is None or since <= utc:
            k = v
    return k


def candidates() -> list[dict]:
    out = []
    for day in DAYS:
        for meta_path in sorted(glob.glob(str(RACK / day / "**" / "runs" / "*.json"), recursive=True)):
            try:
                meta = json.loads(pathlib.Path(meta_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            npz = pathlib.Path(meta_path).with_suffix(".npz")
            if not npz.exists() or meta.get("can_id") is None:
                continue
            try:
                with np.load(npz) as a:
                    t = np.asarray(a["t"], float)
                    wall0 = float(a["wall"][0])
            except (OSError, KeyError, ValueError):
                continue
            if t.size < MIN_SAMPLES or t[-1] - t[0] > MAX_S:
                continue
            out.append({"npz": npz, "run": run_id(npz), "can": int(meta["can_id"]), "kind": meta.get("kind") or "?", "wall0": wall0, "n": int(t.size)})
    return out


def picks(t: np.ndarray, hz: float) -> np.ndarray:
    """The first logged row at or after each time of a uniform grid at hz, and the last row."""
    grid = np.arange(0.0, t[-1] + 1e-9, 1.0 / hz)
    rows = np.clip(np.searchsorted(t, grid), 0, t.size - 1)
    return np.unique(np.append(rows, t.size - 1))


def num(v, digits):
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


def samples_of(run: dict, table) -> tuple[list[dict], dict]:
    with np.load(run["npz"]) as a:
        t = np.asarray(a["t"], float)
        utc = datetime.datetime.fromtimestamp(float(a["wall"][0]), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        k = output_per_board(table, run["can"], utc)
        cols = {"q": np.asarray(a["q"], float), "q_target": np.asarray(a["q_target"], float), "qd": np.asarray(a["qd"], float),
                "qd_target": np.asarray(a["qd_target"], float), "tau": np.asarray(a["tau"], float), "i_q": np.asarray(a["i_q"], float)}
    t0 = t - t[0]
    kept = picks(t0, DISPLAY_HZ)
    deg = lambda x: math.degrees(x * k)  # noqa: E731
    device = f"CAN {run['can']}"
    rows = []
    for i in kept:
        tt = num(t0[i], 4)
        rows.append({"t": tt, "run": run["run"], "situation": "real", "source": "real", "device": device,
                     "q_deg": num(deg(cols["q"][i]), 3), "qd_deg_s": num(deg(cols["qd"][i]), 2), "tau_nm": num(cols["tau"][i], 4), "i_q_a": num(cols["i_q"][i], 3)})
    for i in kept:
        rows.append({"t": num(t0[i], 4), "run": run["run"], "situation": "target", "source": "target", "device": device,
                     "q_deg": num(deg(cols["q_target"][i]), 3), "qd_deg_s": num(deg(cols["qd_target"][i]), 2), "tau_nm": None, "i_q_a": None})
    # self-check: every written real q is the npz's at its row, in degrees of the output frame
    for r, i in zip(rows, kept):
        assert r["q_deg"] == num(math.degrees(cols["q"][i] * k), 3), (run["run"], i)
    meta = {"duration_s": num(t0[-1], 3), "rate_hz": num((t.size - 1) / (t[-1] - t[0]), 1), "rows": len(kept), "output_per_board": k}
    return rows, meta


SAMPLE_FIELDS = [
    {"name": "t", "type": "number", "unit": "s", "description": "seconds from the run's first logged row"},
    {"name": "run", "type": "string", "description": "the run's stable, unique id (runs.json)"},
    {"name": "situation", "type": "string", "description": "real: the board's log; target: what it was commanded"},
    {"name": "source", "type": "string", "description": "the situation's family: real or target", "constraints": {"enum": ["real", "sim", "target"]}},
    {"name": "device", "type": "string", "description": "the station: its board's CAN id"},
    {"name": "q_deg", "type": "number", "unit": "deg", "decimals": 3, "description": "joint angle, the output frame"},
    {"name": "qd_deg_s", "type": "number", "unit": "deg/s", "decimals": 2, "description": "joint velocity"},
    {"name": "tau_nm", "type": "number", "unit": "N·m", "decimals": 4, "description": "joint torque, as the board reports it (real only)"},
    {"name": "i_q_a", "type": "number", "unit": "A", "decimals": 3, "description": "q-axis current (real only)"},
]

RUN_FIELDS = [
    {"name": "run", "type": "string", "title": "Run", "description": "day~folder~step under the rack's archive: the run's file is runs/<run>.json"},
    {"name": "deployment", "type": "string", "title": "Deployment"},
    {"name": "label", "type": "string", "title": "Run"},
    {"name": "started", "type": "datetime", "title": "Started", "description": "the run's first logged row, the rig's wall clock with its UTC offset"},
    {"name": "device", "type": "string", "title": "Station"},
    {"name": "devices", "type": "array", "title": "Devices"},
    {"name": "kind", "type": "string", "title": "Kind"},
    {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration"},
    {"name": "situations", "type": "array", "title": "Situations"},
    {"name": "rate_hz", "type": "number", "unit": "Hz", "title": "Logged at", "description": "the board's log rate"},
    {"name": "display_hz", "type": "number", "unit": "Hz", "title": "Drawn at", "description": "the rate written for display, by picking rows"},
    {"name": "basis", "type": "string", "title": "Basis"},
    {"name": "note", "type": "string", "title": "Archive file", "description": "the run's npz under /archive/datasets/bam_rig"},
]


def main() -> int:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reg = next(d for d in registry["deployments"] if d["id"] == record["id"])
    table = frames(record)
    stations = sorted(int(c["can_id"]) for c in record["components"] if c.get("can_id") is not None)
    found = candidates()
    chosen = []
    for can in stations:
        mine = sorted((r for r in found if r["can"] == can), key=lambda r: r["wall0"], reverse=True)[:PER_STATION]
        chosen.extend(mine)
    chosen.sort(key=lambda r: r["wall0"])
    ids = [r["run"] for r in chosen]
    assert len(set(ids)) == len(ids), "every run id is its own"
    assert all(SAFE.match(i) for i in ids), "every run id is path-safe"
    out_runs = CASE / "runs"
    out_runs.mkdir(exist_ok=True)
    for old in out_runs.glob("*.json"):
        old.unlink()
    runs = []
    for r in chosen:
        rows, meta = samples_of(r, table)
        assert all(x["run"] == r["run"] for x in rows)
        started = datetime.datetime.fromtimestamp(r["wall0"], LOCAL).isoformat(timespec="seconds")
        step = r["run"].rsplit("~", 1)[1]
        runs.append({"run": r["run"], "deployment": record["id"], "label": f"CAN {r['can']} · {r['kind']} · {step}", "started": started, "device": f"CAN {r['can']}",
                     "devices": [f"CAN {r['can']}"], "kind": r["kind"], "duration_s": meta["duration_s"], "situations": ["real", "target"],
                     "rate_hz": meta["rate_hz"], "display_hz": DISPLAY_HZ, "basis": "measured",
                     "note": str(r["npz"].relative_to(RACK))})
        doc = {"name": r["run"], "title": f"Samples of {r['run']}", "source": f"{r['npz'].relative_to(RACK)} under /archive/datasets/bam_rig, rows picked at {DISPLAY_HZ:g} Hz",
               "frame": f"the joint's output frame: board radians × {meta['output_per_board']:g} (the board's config when the run started)",
               "schema": {"fields": SAMPLE_FIELDS}, "rows": rows}
        (out_runs / f"{r['run']}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    runs_doc = {"name": "runs", "title": f"Runs of {reg['title']}", "primaryKey": "run", "titleProperty": "label",
                "source": f"/archive/datasets/bam_rig {', '.join(DAYS)} (every runs/*.npz with ≥ {MIN_SAMPLES} samples and ≤ {MAX_S:g} s), read-only; the newest {PER_STATION} of each station; "
                          "written by gallery/examples/robotics-deployments/source/build.py",
                "schema": {"fields": RUN_FIELDS}, "rows": runs}
    (CASE / "runs.json").write_text(json.dumps(runs_doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    deployments = {
        "id": "deployments", "title": "Deployments", "titleProperty": "title",
        "properties": {
            "deployment": {"type": "text", "label": "Deployment"}, "title": {"type": "text", "label": "Name"},
            "kind": {"type": "text", "label": "Kind"}, "where": {"type": "text", "label": "Where"},
            "stations": {"type": "number", "label": "Stations"}, "runs": {"type": "number", "label": "Runs here"},
            "first_run": {"type": "date", "label": "First run"}, "last_run": {"type": "date", "label": "Last run"},
            "summary": {"type": "text", "label": "What it is"}, "basis": {"type": "text", "label": "Basis"},
        },
        "rows": [{"id": record["id"], "deployment": record["id"], "title": reg["title"], "kind": reg.get("kind") or record.get("kind"), "where": reg.get("where"),
                  "stations": len(stations), "runs": len(runs), "first_run": runs[0]["started"], "last_run": runs[-1]["started"],
                  "summary": reg.get("summary"), "basis": "measured"}],
    }
    (CASE / "deployments.json").write_text(json.dumps(deployments, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sizes = sum(p.stat().st_size for p in out_runs.glob("*.json"))
    print(json.dumps({"runs": len(runs), "stations": [f"CAN {c}" for c in stations], "per-run files KB": round(sizes / 1024), "newest": runs[-1]["run"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
