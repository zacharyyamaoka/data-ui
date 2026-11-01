"""The Arm "Playback + Gates" twin's gate rows (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35): checks.json,
windows.json and poses_error.json beside this folder. **STAND-IN**: robotics-arm's data is simulation (sim2real's perturbed MuJoCo
UR5e, whose "real" is a synthetic plant, and pidtuna's tuning ladder), so every row says `basis: stand-in`, and so do the tolerances
below: they are this twin's illustrative choice until a real arm run and a real tolerance exist.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-arm-gates/source/build.py

Read-only: the template's runs.json, poses.json and diff_poses.json (the difference of each situation against the target, which
`source/build_diff.py` computed with gallery/robotics/difference.py; this producer reads those numbers and recomputes none).

checks.json, one row per run, non-target situation and check (each situation against the target):
  Path error  RMS of err_mm (the tool point's distance to the target's at the same t), stand-in tolerance warn 5 mm / error 10 mm
  Path max    the largest err_mm, the same tolerance; the evidence window is 1 s around it
  Rotation    the largest err_rot_mrad, stand-in tolerance warn 20 mrad / error 50 mrad; the window is 1 s around it
windows.json: Path error (RMS of err_mm) per 0.5 s window (not overlapping), the same 5 / 10 mm.
poses_error.json: the template's poses.json rows, every column kept, plus err_mm taken from diff_poses.json (reference == target)
at the same (run, situation, body, t), null for the target's own rows and where the difference has no row. trajectory3d's
`color: err_mm` paints each path by it and `tolerance` draws the target's tube; the view computes no error.
`device` is the situation (the rows' gate matrix groups by it; every situation name is one run's) and `situation` repeats it.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import pathlib

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-arm"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits  # noqa: E402

POSITION = Limits.at_most(10.0, warn=5.0)    # mm, stand-in
ROTATION = Limits.at_most(50.0, warn=20.0)   # mrad, stand-in
STAND_IN = {"position": "stand-in tolerance warn 5 mm / error 10 mm", "rotation": "stand-in tolerance warn 20 mrad / error 50 mrad"}
WINDOW_S = 0.5
EXTRA = [("situation", "string")]
PRODUCER = "robotics-arm-gates/source/build.py"


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    poses, poses_doc = gates.read_table(TEMPLATE / "poses.json")
    diff, _ = gates.read_table(TEMPLATE / "diff_poses.json")
    labels = gates.run_labels(runs_doc)
    err = {}
    by = {}
    for d in diff:
        if d["reference"] == "target":
            err[(d["run"], d["situation"], d["body"], d["t"])] = d
            by.setdefault((d["run"], d["situation"]), []).append(d)
    # ---- poses_error.json: the template's rows, plus err_mm
    out = []
    for p in poses:
        d = err.get((p["run"], p["situation"], p["body"], p["t"]))
        out.append({**p, "err_mm": None if d is None else d["err_mm"]})
    fields = [*poses_doc["schema"]["fields"], {"name": "err_mm", "type": "number", "unit": "mm", "title": "Path error",
                                                "description": "the tool point's distance to the target's at the same t (diff_poses.json err_mm, reference target); null for the target itself"}]
    src = ("STAND-IN, simulation only: robotics-arm/poses.json with err_mm from robotics-arm/diff_poses.json (difference(a, b) of gallery/robotics/difference.py, "
           f"each situation against the target); written by gallery/examples/{PRODUCER}")
    gates.write_table(CASE / "poses_error.json", "Tool poses with their error (stand-in): the template's poses plus err_mm against the target", src, fields, out)

    checks, windows = [], []
    for r in runs_doc["rows"]:
        run, started = r["run"], r["started"]
        span = gates.span_of([p["t"] for p in poses if p["run"] == run and p["situation"] == "target"])
        for situation in (s for s in r["situations"] if s != "target"):
            rows = sorted(by[(run, situation)], key=lambda d: d["t"])
            t = np.array([d["t"] for d in rows])
            e = np.array([d["err_mm"] for d in rows], float)
            rot = np.array([np.nan if d["err_rot_mrad"] is None else d["err_rot_mrad"] for d in rows], float)
            subject = f"{r['deployment']}/{situation}"
            common = dict(subject=subject, device=situation, run=run, started=started, link=gates.link_run, basis="stand-in", parent=subject,
                          record=f"diff_poses.json · {run} · {situation} vs target", extra={"situation": situation})
            say = lambda v, unit, what, tol: f"{what} {v:.4g} {unit} of {situation} against the target; {tol}"  # noqa: E731
            whole = gates.window3(span[0], span[1], span)
            around = lambda i: gates.window3(t[i] - 0.5, t[i] + 0.5, span)  # noqa: E731

            rms = float(np.sqrt(np.mean(e ** 2)))
            res = gates.custom({"tolerance": STAND_IN["position"]}, diagnostic="arm.path_error", subject=subject, value=rms, unit="mm", metric="rms", limits=POSITION,
                               title="Path error", message=say(rms, "mm", "RMS path error", STAND_IN["position"]),
                               why="open the window in playback: the path overlay paints where along the path the error is")
            checks.append(gates.row(res, id=f"{run}#{situation}#Path error", title="Path error", window=whole, hint="path_overlay", source=f"{PRODUCER} · arm.path_error", **common))
            i = int(np.argmax(e))
            res = gates.custom({"tolerance": STAND_IN["position"]}, diagnostic="arm.path_max", subject=subject, value=float(e[i]), unit="mm", metric="max", limits=POSITION,
                               title="Path max", message=say(float(e[i]), "mm", f"largest path error, at t = {t[i]:g} s,", STAND_IN["position"]),
                               why="open the window in playback: the path overlay paints where along the path the error is")
            checks.append(gates.row(res, id=f"{run}#{situation}#Path max", title="Path max", window=around(i), hint="path_overlay", source=f"{PRODUCER} · arm.path_max", **common))
            if np.isfinite(rot).any():
                j = int(np.nanargmax(rot))
                res = gates.custom({"tolerance": STAND_IN["rotation"]}, diagnostic="arm.rotation", subject=subject, value=float(rot[j]), unit="mrad", metric="max", limits=ROTATION,
                                   title="Rotation", message=say(float(rot[j]), "mrad", f"largest tool rotation error, at t = {t[j]:g} s,", STAND_IN["rotation"]),
                                   why="open the window in playback and compare the tool's axes against the target's")
                window = around(j)
            else:
                res = gates.not_run({"tolerance": STAND_IN["rotation"]}, diagnostic="arm.rotation", subject=subject, title="Rotation", unit="mrad", message="no orientation in the poses")
                window = None
            checks.append(gates.row(res, id=f"{run}#{situation}#Rotation", title="Rotation", window=window, hint="gate_matrix", source=f"{PRODUCER} · arm.rotation", **common))

            end = WINDOW_S
            n = 0
            while end <= span[1] + 1e-9:
                keep = (t >= end - WINDOW_S) & (t < end)
                if keep.sum() >= 2:
                    v = float(np.sqrt(np.mean(e[keep] ** 2)))
                    res = gates.custom({"tolerance": STAND_IN["position"]}, diagnostic="arm.path_error", subject=subject, value=v, unit="mm", metric="rms", limits=POSITION,
                                       title="Path error", message=say(v, "mm", f"RMS path error in the {WINDOW_S:g} s window ending {end:g} s,", STAND_IN["position"]))
                    windows.append(gates.row(res, id=f"{run}#{situation}#Path error#{n}", title="Path error", window=gates.window3(end - WINDOW_S, end, span), hint="threshold_band",
                                             source=f"{PRODUCER} · arm.path_error", **common))
                    n += 1
                end = round(end + WINDOW_S, 6)
    src = ("STAND-IN, simulation only: robotics-arm/diff_poses.json (each situation against the target; sim2real's perturbed MuJoCo UR5e and pidtuna's replay), judged against "
           f"the stand-in tolerances said in each row; written by gallery/examples/{PRODUCER}")
    gates.write_table(CASE / "checks.json", f"Checks (stand-in): {len(checks)} gate rows, each non-target situation of the UR5e runs against the target", src,
                      gates.field_list(labels, extra=EXTRA), checks)
    gates.write_table(CASE / "windows.json", "Windows (stand-in): path error per 0.5 s window", src, gates.field_list(labels, unit="mm", extra=EXTRA), windows)
    print({"checks": len(checks), "windows": len(windows), "poses_error": len(out), "with err": sum(o["err_mm"] is not None for o in out)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
