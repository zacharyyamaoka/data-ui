"""The Camera "Playback + Gates" twin's gate rows (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35): checks.json
and windows.json beside this folder, computed from the hardware frame stamps (`hw_ms`) of the two RealSense cameras in the
three sessions robotics-camera plays (01a, 01c, 02 of rack_2026-10-23), with RobotDx's library, as §10's diagnostic rows.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-camera-gates/source/build.py

Read-only: the template's runs.json and each session's cameras/cam_<serial>.npz (only hw_ms; the frames are 2.4 GB a file).
`run` is the session id and `device` the camera. t is the template's: seconds from the session's first frame of either camera,
frame k at (hw_ms[k] - the session's first hw_ms) / 1000, which is how samples.csv writes it.

checks.json, one row per session and camera:
  Rate     stock.sample_rate with stamps_scale=1e-3 (the stamps are ms), expected 30 Hz
  Dropped  the frame intervals longer than 3 frame periods (100 ms), the count stock.sample_rate calls gaps; any warns, as the library does
windows.json: stream.monitor on the frame intervals, 1 s windows stepping 1 s, the window's largest interval in ms (title "Frame
interval"), warn above 50 ms and error above 100 ms. THESE TWO THRESHOLDS ARE THIS TWIN'S CHOICE (1.5 and 3 frame periods of
33.3 ms; the error one is RobotDx's own gap definition), not a RealSense specification; each row's message says so.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import pathlib

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-camera"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits, evaluate  # noqa: E402
from robotdx.diagnostics.stock import BoxConfig, RateConfig  # noqa: E402
from robotdx.diagnostics.stock.health import Stamps  # noqa: E402

DAY = "rack_2026-10-23"
EXPECTED_HZ = 30.0
WARN_MS, ERROR_MS = 50.0, 100.0


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    labels = gates.run_labels(runs_doc)
    checks, windows = [], []
    for r in runs_doc["rows"]:
        run, started = r["run"], r["started"]
        session = run.split("/")[1]
        cams = {}
        for name in r["devices"]:
            path = gates.RACK / DAY / session / "cameras" / f"cam_{name.split()[1]}.npz"
            with np.load(path) as z:
                cams[name] = (path, np.asarray(z["hw_ms"], float))
        origin = min(hw[0] for _, hw in cams.values())
        times = {name: np.round((hw[1:] - origin) / 1000.0, 4) for name, (_, hw) in cams.items()}   # frame k's t, k >= 1 (an interval's row)
        span = (min(t[0] for t in times.values()), max(t[-1] for t in times.values()))
        for name, (path, hw) in cams.items():
            subject, rel = f"{r['deployment']}/{name}", path.relative_to(gates.RACK)
            common = dict(subject=subject, device=name, run=run, started=started, link=gates.link_run, basis="derived")
            t = times[name]
            own = gates.window3(t[0], t[-1], span)

            res = evaluate("stock.sample_rate", RateConfig(expected_hz=EXPECTED_HZ, stamps_scale=1e-3), [Stamps(hw, str(rel))], subject=subject)
            checks.append(gates.row(res, id=f"{run}#{name}#Rate", title="Rate", window=own, hint="gate_matrix", parent=subject, record=f"{rel} · hw_ms", **common))

            dt = np.diff(hw)
            gap = int(next(m.value for m in res.measurements if m.key == "gaps"))
            longest = int(np.argmax(dt))
            where = gates.window3(t[longest] - dt[longest] / 1000.0 - 0.25, t[longest] + 0.25, span) if gap else own
            dropped = gates.custom({"gap_factor": 3.0, "expected_hz": EXPECTED_HZ}, diagnostic="stock.sample_rate", subject=subject, value=gap, unit="1", metric="gaps",
                                   limits=Limits(warn_high=0.0), title="Dropped",
                                   message=(f"{gap} frame intervals over {3000 / EXPECTED_HZ:g} ms (3 frame periods) in {hw.size} frames; the longest is {dt[longest]:.1f} ms "
                                            f"ending at t = {t[longest]:.3f} s"),
                                   why="open the longest interval in playback: a stall in the stamps is a stall in the clip")
            checks.append(gates.row(dropped, id=f"{run}#{name}#Dropped", title="Dropped", window=where, hint="gate_matrix", parent=subject, record=f"{rel} · hw_ms",
                                    **common))

            # WHY the carrier column: stock.box reads one named channel, so the interval (ms) rides in qd_rad_s and the Result says ms
            box = BoxConfig(channel="qd_rad_s", unit="ms", max=Limits.at_most(ERROR_MS, warn=WARN_MS))
            clip = gates.traj(t - t[0], np.zeros(t.size), qd_rad_s=dt, run=run)
            for n, (end, res) in enumerate(gates.windowed("stock.box", box, clip, subject=subject, window_s=1.0, step_s=1.0)):
                end += float(t[0])   # back onto the session's clock
                windows.append(gates.row(
                    res, id=f"{run}#{name}#Frame interval#{n}", title="Frame interval", window=gates.window3(end - 1.0, end, span), hint="threshold_band", parent=subject,
                    record=f"{rel} · hw_ms", message=(f"largest frame interval {res.value:.1f} ms in the 1 s window ending {end:.2f} s; warn above {WARN_MS:g} ms and error "
                                                      f"above {ERROR_MS:g} ms are this twin's choice (1.5 and 3 frame periods of {1000 / EXPECTED_HZ:.1f} ms), not RobotDx's or Intel's"),
                    **common))
    src = (f"/archive/datasets/bam_rig {DAY}: each session's cameras/cam_<serial>.npz (hw_ms, the hardware frame stamps; real), judged by robotdx.diagnostics "
           "(io-diagnostics); written by gallery/examples/robotics-camera-gates/source/build.py")
    gates.write_table(CASE / "checks.json", f"Checks: {len(checks)} gate rows of the two RealSense cameras in {len(runs_doc['rows'])} sessions of Oct 23", src,
                      gates.field_list(labels), checks)
    gates.write_table(CASE / "windows.json", f"Windows: the largest frame interval per 1 s window, {len(runs_doc['rows'])} sessions of Oct 23", src,
                      gates.field_list(labels, unit="ms"), windows)
    print({"checks": len(checks), "windows": len(windows)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
