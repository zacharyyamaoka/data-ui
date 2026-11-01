"""The Arm + gripper "Playback + Gates" twin's gate rows (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35):
checks.json and windows.json beside this folder. **STAND-IN**: robotics-arm-gripper's arm is simulation (sim2real's perturbed MuJoCo UR5e,
its "real" a synthetic plant) and its gripper is illustrative (made from a stated rule, never logged), so every row says `basis:
stand-in` and so do the tolerances below: this twin's illustrative choice until a real gripper log and a real tolerance exist.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-arm-gripper-gates/source/build.py

Read-only: the template's runs.json, poses.json, samples.json and events.json. The hold is the span from events.json's `grasp` to its
`release`; the gripper's `real` situation is judged against what the `target` situation commanded over the hold.

checks.json, one row per check (the one run):
  Grip force   mean real force over the hold against the commanded force: warn beyond 3 N, error beyond 5 N (device gripper)
  Grip width   mean real width over the hold against the commanded width: warn beyond 1.5 mm, error beyond 3 mm (device gripper)
  Path error   RMS distance of the real tool point to the target's at the same t over the run: warn 5 mm, error 10 mm (device tcp)
windows.json: the largest real grip force in each 0.5 s window (not overlapping), warn above 23 N and error above 25 N (the commanded
force plus 3 and 5 N; no lower limit, since the fingers are open and the force 0 outside the hold).
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import pathlib

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-arm-gripper"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits  # noqa: E402

PATH = Limits.at_most(10.0, warn=5.0)   # mm
FORCE_WARN_N, FORCE_ERROR_N = 3.0, 5.0
WIDTH_WARN_MM, WIDTH_ERROR_MM = 1.5, 3.0
WINDOW_S = 0.5
PRODUCER = "robotics-arm-gripper-gates/source/build.py"
SAY = "stand-in tolerance"


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    poses, _ = gates.read_table(TEMPLATE / "poses.json")
    samples, _ = gates.read_table(TEMPLATE / "samples.json")
    events, _ = gates.read_table(TEMPLATE / "events.json")
    labels = gates.run_labels(runs_doc)
    (r,) = runs_doc["rows"]
    run, started = r["run"], r["started"]
    grasp = next(e["t"] for e in events if e["run"] == run and e["kind"] == "grasp")
    release = next(e["t"] for e in events if e["run"] == run and e["kind"] == "release")

    def series(rows, situation, *keys):
        mine = sorted((x for x in rows if x["run"] == run and x["situation"] == situation), key=lambda x: x["t"])
        return np.array([x["t"] for x in mine]), [np.array([x[k] for x in mine], float) for k in keys]

    span = gates.span_of(series(poses, "target", "z_mm")[0])
    hold = gates.window3(grasp, release, span)
    t_real, (force, width) = series(samples, "real", "force_n", "width_mm")
    t_cmd, (force_cmd, width_cmd) = series(samples, "target", "force_n", "width_mm")
    inside = (t_real >= grasp) & (t_real <= release)
    commanded = (t_cmd >= grasp) & (t_cmd <= release)
    checks, windows = [], []

    def add(sink, res, id, title, device, window, hint, source):
        subject = f"{r['deployment']}/{device}"
        sink.append(gates.row(res, id=id, subject=subject, device=device, title=title, window=window, hint=hint, run=run, started=started, link=gates.link_single, basis="stand-in",
                              parent=subject, record=f"samples.json / poses.json / events.json · {run}", source=f"{PRODUCER} · {source}"))

    subject = f"{r['deployment']}/gripper"
    f_cmd = float(np.median(force_cmd[commanded]))
    f_limits = Limits(error_low=f_cmd - FORCE_ERROR_N, warn_low=f_cmd - FORCE_WARN_N, warn_high=f_cmd + FORCE_WARN_N, error_high=f_cmd + FORCE_ERROR_N)
    v = float(np.mean(force[inside]))
    res = gates.custom({"tolerance": SAY}, diagnostic="gripper.force_at_grasp", subject=subject, value=v, unit="N", metric="mean", limits=f_limits, title="Grip force", target=f_cmd,
                       message=(f"mean real grip force {v:.4g} N over the hold ({grasp:g} to {release:g} s) against the commanded {f_cmd:g} N; {SAY} warn beyond {FORCE_WARN_N:g} N, "
                                f"error beyond {FORCE_ERROR_N:g} N; the gripper is illustrative"), why="open the hold in playback and compare the force with the width")
    add(checks, res, f"{run}#Grip force", "Grip force", "gripper", hold, "gate_matrix", "gripper.force_at_grasp")

    w_cmd = float(np.median(width_cmd[commanded]))
    w_limits = Limits(error_low=w_cmd - WIDTH_ERROR_MM, warn_low=w_cmd - WIDTH_WARN_MM, warn_high=w_cmd + WIDTH_WARN_MM, error_high=w_cmd + WIDTH_ERROR_MM)
    v = float(np.mean(width[inside]))
    res = gates.custom({"tolerance": SAY}, diagnostic="gripper.width_at_grasp", subject=subject, value=v, unit="mm", metric="mean", limits=w_limits, title="Grip width", target=w_cmd,
                       message=(f"mean real finger width {v:.4g} mm over the hold ({grasp:g} to {release:g} s) against the commanded {w_cmd:g} mm; {SAY} warn beyond {WIDTH_WARN_MM:g} mm, "
                                f"error beyond {WIDTH_ERROR_MM:g} mm; the gripper is illustrative"), why="open the hold in playback and compare the width with the force")
    add(checks, res, f"{run}#Grip width", "Grip width", "gripper", hold, "gate_matrix", "gripper.width_at_grasp")

    tcp = f"{r['deployment']}/tcp"
    t_a, a = series(poses, "real", "x_mm", "y_mm", "z_mm")
    t_b, b = series(poses, "target", "x_mm", "y_mm", "z_mm")
    assert np.array_equal(t_a, t_b), "the real and target tool points share their t"
    dist = np.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    v = float(np.sqrt(np.mean(dist ** 2)))
    res = gates.custom({"tolerance": SAY}, diagnostic="arm.path_error", subject=tcp, value=v, unit="mm", metric="rms", limits=PATH, title="Path error",
                       message=f"RMS distance of the real tool point to the target's over the run {v:.4g} mm; {SAY} warn 5 mm, error 10 mm; the arm is simulation (a synthetic plant)",
                       why="open the run in playback: the arm's path panel shows where the real leaves the target")
    add(checks, res, f"{run}#Path error", "Path error", "tcp", gates.window3(span[0], span[1], span), "gate_matrix", "arm.path_error")

    limits = Limits(warn_high=f_cmd + FORCE_WARN_N, error_high=f_cmd + FORCE_ERROR_N)
    end, n = WINDOW_S, 0
    while end <= span[1] + 1e-9:
        keep = (t_real >= end - WINDOW_S) & (t_real < end)
        if keep.sum() >= 2:
            v = float(np.max(force[keep]))
            res = gates.custom({"tolerance": SAY}, diagnostic="gripper.force_at_grasp", subject=subject, value=v, unit="N", metric="max", limits=limits, title="Grip force",
                               message=f"largest real grip force {v:.4g} N in the {WINDOW_S:g} s window ending {end:g} s; {SAY} warn above {limits.warn_high:g} N, error above {limits.error_high:g} N")
            add(windows, res, f"{run}#Grip force#{n}", "Grip force", "gripper", gates.window3(end - WINDOW_S, end, span), "threshold_band", "gripper.force_at_grasp")
            n += 1
        end = round(end + WINDOW_S, 6)
    src = ("STAND-IN: the arm is sim2real's MuJoCo UR5e (synthetic real, never measured) and the gripper is illustrative (robotics-arm-gripper/source/build.py's stated rule); "
           f"judged against the stand-in tolerances said in each row; written by gallery/examples/{PRODUCER}")
    gates.write_table(CASE / "checks.json", f"Checks (stand-in): {len(checks)} gate rows of the one UR5e + illustrative gripper run", src, gates.field_list(labels), checks)
    gates.write_table(CASE / "windows.json", "Windows (stand-in): the largest grip force per 0.5 s window", src, gates.field_list(labels, unit="N"), windows)
    print({"checks": len(checks), "windows": len(windows)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
