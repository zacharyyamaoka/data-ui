"""The Servo template's data (PEP 0010 P1c, docs/peps/0010-robotics-playback.md §6): 40 real rack runs of CAN 12 and
CAN 14, each replayed through the twin its motor's dataset file calls "full", written as the trajectory contract's
tables (gallery/robotics/CONTRACT.md): runs.json, samples.json and devices.json beside this folder.

Run it with the bam_rack_twin package's own venv (it carries bam_rack_twin, bam_sim and MuJoCo); the replays are sim2real's
rack_replays.py, imported, never copied:

    PYTHONDONTWRITEBYTECODE=1 ~/bam_ws/.claude/worktrees/sim-to-real-motor-models-f1ee43/src/dev/bam_rack_twin/.venv/bin/python -B -I \\
        gallery/examples/robotics-servo/source/build.py [--cache DIR]

Read-only: /archive/datasets/bam_rig (the runs' npz and json, the dataset files, the twins' budgets), the bam_rack_twin
worktree and ~/sim2real/dashboards/source/rack_replays.py. It writes nothing there: -B and sys.dont_write_bytecode keep
Python's bytecode caches out of both, the twin scenes go to a temporary folder, and --cache (full-rate replays as .npz)
goes wherever it is pointed (default: a temporary folder, removed). It never opens a port or a bus.

Which runs (40, fixed below so a change in a study's run list cannot move them silently):
  CAN 12  the 13 runs round 7 replays with CAN 12's deployed twin (round7_study._runs('can12'): rack_2026-10-25's
          dataset_rotor, its rest sessions and the two cogging-phase gravity runs); 7 of them are the held-out rows of
          rack_2026-10-25/analysis/dataset_twin_can12.json
  CAN 14  27 runs of rack_2026-10-24, replayed with that day's envelope twin: dataset/can14 (12, every one a held-out row
          of rack_2026-10-24/analysis/dataset_twin_can14.json), floors/can14 (5 waypoint repeats) and the sine sessions
          09, 10 and 11 (10; session 11's two 2 rad sines, since session 30's 3 rad, 2.8 Hz sine
          drives CAN 14 into its 1.5 N·m cap and the twin's replay leaves it by 1.75 rad RMS: a twin outside its range, not a
          view of one)
The twin is the one rack_replays.py rebuilds for that motor (acceptance.json's dataset file, its twins.full), and the
oracle is rack_replays.py's: on a held-out run the replayed q RMS (real − twin, scorecard.score_replay's rows) must
reproduce the dataset file's twin_q_rms_mrad.full within 2 %. Other runs have no file value; runs.json says which.

The display projection (CONTRACT §4): t in s from the run's first kept row; q in degrees, qd in deg/s, τ in N·m, in the
joint's output frame as bam_rack_twin.evidence.to_output_frame writes it; three situations per run, real (the board's
log), twin (the replay, family sim) and target (the board's commanded q_target / qd_target, no torque); rows picked at
write_tables.py's DISPLAY_HZ (20) from the native ~95 Hz, the same rows in all three, never averaged. Missing is null.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import pathlib
import sys
import tempfile
import time

sys.dont_write_bytecode = True  # WHY first: the imports below must leave no __pycache__ in sim2real or bam_ws
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
RACK_REPLAYS = pathlib.Path(os.environ.get("RACK_REPLAYS", str(pathlib.Path.home() / "sim2real" / "dashboards" / "source")))
sys.path.insert(0, str(RACK_REPLAYS))

import numpy as np  # noqa: E402
import rack_replays as rr  # noqa: E402  sim2real's replay tooling: its picks, twin rebuilds and oracle

ARCHIVE = pathlib.Path("/archive/datasets/bam_rig")
R24, R25 = ARCHIVE / "rack_2026-10-24", ARCHIVE / "rack_2026-10-25"
DATASET_FILE = {12: R25 / "analysis" / "dataset_twin_can12.json", 14: R24 / "analysis" / "dataset_twin_can14.json"}
PRODUCER = {12: "round7_capture", 14: "envelope_twin"}
MAX_WORKERS = 4  # rack_replays.py's ceiling: the machine is shared

RUNS = {
    12: [R25 / p for p in (
        "cogging_phase/can12_a/runs/s01_can12_gravity.npz", "cogging_phase/can12_b/runs/s01_can12_gravity.npz",
        "dataset_rotor/can12/runs/s01_can12_waypoints.npz", "dataset_rotor/can12/runs/s03_can12_waypoints.npz",
        "dataset_rotor/can12/runs/s05_can12_waypoints.npz", "dataset_rotor/can12/runs/s07_can12_sine.npz",
        "dataset_rotor/can12/runs/s09_can12_waypoints.npz", "dataset_rotor/can12/runs/s11_can12_waypoints.npz",
        "dataset_rotor/can12_rest/runs/s01_can12_waypoints.npz", "dataset_rotor/can12_rest/runs/s03_can12_sine.npz",
        "dataset_rotor/can12_rest/runs/s05_can12_waypoints.npz", "dataset_rotor/can12_rest2/runs/s01_can12_waypoints.npz",
        "dataset_rotor/can12_rest2/runs/s03_can12_sine.npz")],
    14: [R24 / p for p in (
        *(f"dataset/can14/runs/s{k:02d}_can14_{'sine' if k in (7, 15, 23) else 'waypoints'}.npz" for k in range(1, 24, 2)),
        *(f"floors/can14/runs/s{k:02d}_can14_waypoints.npz" for k in (1, 3, 5, 7, 9)),
        *(f"session_09/runs/s{k:02d}_can14_sine.npz" for k in (9, 11, 13, 15)),
        *(f"session_10/runs/s{k:02d}_can14_sine.npz" for k in (7, 9, 11, 13)),
        *(f"session_11/runs/s{k:02d}_can14_sine.npz" for k in (1, 3)))],
}


def run_id(npz: pathlib.Path) -> str:
    """The run's stable, unique id: its day and folder under the rack's archive and its session number, e.g.
    10-24/dataset/can14/s01 for rack_2026-10-24/dataset/can14/runs/s01_can14_waypoints.npz. WHY not the whole path: it
    rides in every one of ~60,000 rows; runs.json keeps the npz path beside it."""
    rel = npz.relative_to(ARCHIVE)
    day = rel.parts[0].removeprefix("rack_2026-")
    folder = [p for p in rel.parts[1:-1] if p != "runs"]
    return "/".join([day, *folder, npz.stem.split("_")[0]])


def held_out_rows(can: int) -> dict[str, dict]:
    """{npz path: the dataset file's row} for the motor's held-out rows (the file's oracle numbers)."""
    path = DATASET_FILE[can]
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    return {str(rr.run_path_of(row, path)): row for row in rows}


def make_pick(can: int, npz: pathlib.Path, held: dict[str, dict]) -> rr.Pick:
    path = DATASET_FILE[can]
    document = json.loads(path.read_text(encoding="utf-8"))
    row = held.get(str(npz))
    kind = rr.kind_of(row or {}, npz)
    return rr.Pick(can=can, station_id=f"can{can}", dataset_twin_file=path, run_path=npz, kind=kind,
                   run_class=(row or {}).get("class"), seed=None if not row or row.get("seed") is None else int(row["seed"]),
                   expected_q_mrad=float(row["twin_q_rms_mrad"][rr.TWIN_NAME]) if row else math.nan,
                   expected_tau_nm=None, twin_label=str(document["twins"][rr.TWIN_NAME]), producer=PRODUCER[can])


def replay_one(pick: rr.Pick, scenes: str, cache: str) -> dict:
    """One run through its motor's twin (rack_replays.REPLAYERS), saved full-rate to the cache; returns its record."""
    out = pathlib.Path(cache) / (run_id(pick.run_path).replace("/", "__") + ".npz")
    meta_path = out.with_suffix(".json")
    if out.is_file() and meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    started = time.time()
    twin, run, replay, prelude_s = rr.REPLAYERS[pick.producer](pick, pathlib.Path(scenes))
    rms = rr.q_rms_mrad(run, replay)
    expected = pick.expected_q_mrad
    oracle = None
    if math.isfinite(expected):
        oracle = "ok" if math.isfinite(rms) and abs(rms - expected) / expected <= rr.ORACLE_TOLERANCE else "mismatch"
    np.savez_compressed(out, t=run.t - run.t[0], q=run.q, qd=run.qd, tau=run.tau, q_target=run.q_target, qd_target=run.qd_target,
                        mode=run.mode, twin_q=replay.q, twin_qd=replay.qd, twin_tau=replay.tau, twin_mode=replay.mode)
    record = {
        "can": pick.can, "npz": str(pick.run_path), "run": run_id(pick.run_path), "kind": pick.kind, "class": pick.run_class,
        "twin_version": twin.version, "twin_label": pick.twin_label, "producer": pick.producer, "prelude_dropped_s": prelude_s,
        "started_utc": str(run.run.started_utc) if getattr(run.run, "started_utc", None) else None,
        "native_hz": float(1.0 / np.median(np.diff(run.t))), "duration_s": float(run.t[-1] - run.t[0]), "rows": int(run.t.size),
        "q_rms_mrad": None if not math.isfinite(rms) else float(rms), "expected_q_rms_mrad": None if not math.isfinite(expected) else expected,
        "oracle": oracle, "held_out": math.isfinite(expected), "replay_wall_s": round(time.time() - started, 1),
    }
    meta_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=pathlib.Path, help="keep the full-rate replays here (default: a temporary folder, removed)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--replay-only", action="store_true", help="replay into --cache and stop")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="robotics_servo_") as tmp:
        cache = (args.cache or pathlib.Path(tmp) / "cache").resolve()
        cache.mkdir(parents=True, exist_ok=True)
        scenes = pathlib.Path(tmp) / "scenes"
        scenes.mkdir()
        picks = []
        for can, paths in RUNS.items():
            held = held_out_rows(can)
            picks += [make_pick(can, p, held) for p in paths]
        assert len(picks) == 40 and len({run_id(p.run_path) for p in picks}) == 40, "40 runs, each with its own id"
        records, failed = [], []
        with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, min(MAX_WORKERS, args.workers))) as pool:
            futures = {pool.submit(replay_one, p, str(scenes), str(cache)): p for p in picks}
            for f in concurrent.futures.as_completed(futures):
                p = futures[f]
                try:
                    records.append(f.result())
                    r = records[-1]
                    print(f"{r['run']:<34} {r['kind']:<10} {r['duration_s']:6.2f} s  q RMS {r['q_rms_mrad'] or float('nan'):8.3f} mrad"
                          f"  file {r['expected_q_rms_mrad'] or float('nan'):8.3f}  {r['oracle'] or '-':<8} {r['replay_wall_s']} s", flush=True)
                except (Exception, SystemExit) as error:  # noqa: BLE001 -- listed, never hidden
                    failed.append((run_id(p.run_path), f"{type(error).__name__}: {error}"))
                    print(f"FAILED {run_id(p.run_path)}: {failed[-1][1]}", flush=True)
        if failed:
            print(f"{len(failed)} run(s) did not replay; nothing written", file=sys.stderr)
            return 1
        if args.replay_only:
            return 0
        sys.path.insert(0, str(HERE))  # WHY: -I leaves the script's own folder off sys.path
        from write_tables import write_tables  # noqa: E402  the display projection, apart so it runs without MuJoCo
        write_tables(cache, records, CASE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
