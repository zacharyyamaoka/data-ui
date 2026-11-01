"""The Servo "Playback + Gates" twin's gate rows (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35): checks.json
and windows.json beside this folder, computed from the 40 real rack runs robotics-servo plays (its runs.json names each run's
npz in /archive/datasets/bam_rig) with RobotDx's library, as §10's diagnostic rows. data-ui computes none of it.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-servo-gates/source/build.py

Read-only: the template's runs.json / samples.json, each run's npz, bam_rack_twin's tape parameter block (deployment record's
package: hardware/tape.py TAPE_STATIONS, for each station's speed ceiling and q window) and the newest acceptance file
(gates.newest_acceptance: its T1 floor per station).

checks.json, one row per run and check (the matrix's columns, gates.ORDER):
  Tracking     stock.tracking_error, real q vs q_target on the rows in position mode; a reading (no limit), as sim2real reads it
  Twin error   the twin's q RMS (runs.json q_rms_mrad, bam_rack_twin's replay) judged at most 1.5 x the station's T1 floor
  Board temp   stock.box on temp_c, warn 60 / error 70 (sim2real's BOARD_TEMP)
  Faults       stock.fault_codes
  Rate         stock.sample_rate against the board's 100 Hz
windows.json: stream.monitor, 1 s windows stepping 0.5 s, per run: Speed (a box on |qd|, error above the station's speed ceiling)
and, for a station with a q window (CAN 12), Angle (a box on q, error outside the window).
The runs' t is the template's: seconds from the first kept row (a runner's prelude is dropped on some 10-25 runs), found by
gates.align_start and checked against the template's own samples.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import pathlib

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-servo"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits, evaluate  # noqa: E402
from robotdx.diagnostics.stock import BoxConfig, FaultCodesConfig, RateConfig, TrackingErrorConfig  # noqa: E402
from robotdx.diagnostics.stock.health import Stamps  # noqa: E402

BOARD_TEMP = BoxConfig(channel="temp_c", unit="Cel", max=Limits.at_most(70.0, warn=60.0))  # sim2real's BOARD_TEMP numbers (its max)
TWIN_GATE = 1.5   # the ruler: twin error <= 1.5 x the device's own floor (bam_rack_twin's T2; sim2real's FIDELITY_GATE)


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    samples, _ = gates.read_table(TEMPLATE / "samples.json")
    shown = {}
    for s in samples:
        if s["situation"] == "real":
            shown.setdefault(s["run"], []).append(s)
    labels = gates.run_labels(runs_doc)
    acceptance_path, acceptance = gates.newest_acceptance()
    stations = gates.tape_stations()
    checks, windows = [], []
    for r in runs_doc["rows"]:
        device = r["devices"][0]
        can = int(device.split()[1])
        run, started = r["run"], r["started"]
        subject = f"{r['deployment']}/{device}"
        npz = pathlib.Path(r["npz"])
        rel = npz.relative_to(gates.RACK)
        with np.load(npz) as z:
            t_raw = np.asarray(z["t"], float)
            k = gates.align_start(t_raw, r["duration_s"])
            t = t_raw[k:] - t_raw[k]
            col = {n: np.asarray(z[n], float)[k:] for n in ("q", "q_target", "qd", "mode", "fault", "temp_c")}
        # self-check: the aligned log is the template's real angle, row for row (interpolated at the template's 20 Hz picks)
        mine = shown[run]
        gap = np.abs(np.interp([s["t"] for s in mine], t, np.degrees(col["q"])) - [s["q_deg"] for s in mine]).max()
        assert gap < 0.2, f"{run}: the aligned npz is {gap:.3f} deg off the template's samples"
        span = gates.span_of([s["t"] for s in mine])
        whole = gates.window3(span[0], span[1], span)
        common = dict(subject=subject, device=device, run=run, started=started, link=gates.link_run, basis="derived")
        full = gates.traj(t, col["q"], q_target_rad=col["q_target"], qd_rad_s=col["qd"], mode=col["mode"], fault=col["fault"], temp_c=col["temp_c"], run=run)

        def add(res, title, *, window=whole, hint="gate_matrix", **kw):
            checks.append(gates.row(res, id=f"{run}#{title}", title=title, window=window, hint=hint, parent=subject, **{**common, **kw}))

        keep = lambda res, key: f"{rel} · {(res.evidence[0].key if res.evidence else key)}"  # noqa: E731
        res = evaluate("stock.tracking_error", TrackingErrorConfig(controlled_only=True), [full], subject=subject)
        add(res, "Tracking", window=gates.window3(res.t0, res.t1, span) if res.t0 is not None else whole,
            message=res.message + " (no limit set: a reading, not a gate)", record=keep(res, "q_rad - q_target_rad"))

        floor = gates.floor_mrad(acceptance, can)
        gate = TWIN_GATE * floor
        if r["q_rms_mrad"] is None:
            res = gates.not_run({"gate": f"{TWIN_GATE:g} x floor"}, diagnostic="servo.twin_error", subject=subject, title="Twin error", unit="mrad",
                                message="no twin replay of this run", code="NoTwin")
        else:
            res = gates.custom({"gate": f"at most {TWIN_GATE:g} x the station's T1 floor", "floor_mrad": floor}, diagnostic="servo.twin_error", subject=subject,
                               value=r["q_rms_mrad"], unit="mrad", metric="q_rms", limits=Limits.at_most(gate), title="Twin error",
                               message=(f"twin q RMS {r['q_rms_mrad']:.4g} mrad (bam_rack_twin's replay, runs.json) against {gate:.4g} mrad = {TWIN_GATE:g} x {device}'s "
                                        f"T1 floor {floor:.4g} mrad ({acceptance_path.name})"),
                               why="open the window in playback: where the twin leaves the real angle is the term the twin lacks")
        add(res, "Twin error", hint="kpi_trend", record=f"{rel} · q - twin_q", source=f"bam_rack_twin · {acceptance_path.name} T1 floor, runs.json q_rms_mrad")

        res = gates.two_sided(evaluate("stock.box", BOARD_TEMP, [full], subject=subject), BOARD_TEMP)
        add(res, "Board temp", record=keep(res, "temp_c"))

        res = evaluate("stock.fault_codes", FaultCodesConfig(), [full], subject=subject)
        add(res, "Faults", window=gates.fault_window(t, col["fault"], col["mode"], span), record=keep(res, "fault"))

        res = evaluate("stock.sample_rate", RateConfig(expected_hz=100.0), [Stamps(t, run)], subject=subject)
        add(res, "Rate", record=f"{rel} · t")

        # ---- windows
        ceiling = stations[can]["speed_ceiling_deg_s"]
        speed = BoxConfig(channel="qd_rad_s", unit="deg/s", max=Limits(error_high=ceiling))
        # WHY the carrier column: stock.box reads one named channel, so |qd| in deg/s rides in qd_rad_s and the Result says deg/s
        carried = gates.traj(t, col["q"], qd_rad_s=np.abs(np.degrees(col["qd"])), run=run)
        for n, (end, res) in enumerate(gates.windowed("stock.box", speed, carried, subject=subject)):
            res = gates.two_sided(res, speed)
            windows.append(gates.row(res, id=f"{run}#Speed#{n}", title="Speed", window=gates.window3(end - gates.WINDOW_S, end, span), hint="threshold_band",
                                     parent=subject, record=f"{rel} · qd", message=f"max |qd| {res.value:.4g} deg/s in the 1 s window ending {end:g} s; "
                                     f"{device}'s speed ceiling {ceiling:g} deg/s (bam_rack_twin TAPE_STATIONS)", **common))
        window = stations[can]["q_window_deg"]
        if window:
            angle = BoxConfig(channel="q_rad", unit="deg", min=Limits(error_low=window[0]), max=Limits(error_high=window[1]))
            carried = gates.traj(t, np.degrees(col["q"]), run=run)  # WHY degrees in q_rad: the box reads q_rad; the Result says deg
            for n, (end, res) in enumerate(gates.windowed("stock.box", angle, carried, subject=subject)):
                res = gates.two_sided(res, angle)
                windows.append(gates.row(res, id=f"{run}#Angle#{n}", title="Angle", window=gates.window3(end - gates.WINDOW_S, end, span), hint="threshold_band",
                                         parent=subject, record=f"{rel} · q", message=f"q {res.value:.4g} deg ({res.metric} of the 1 s window ending {end:g} s); "
                                         f"{device}'s window {window[0]:g} to {window[1]:g} deg (bam_rack_twin TAPE_STATIONS, board frame)", **common))
    src = (f"/archive/datasets/bam_rig rack_2026-10-24 and rack_2026-10-25 (real runs, the npz robotics-servo's runs.json names), judged by "
           f"robotdx.diagnostics (io-diagnostics); twin error from robotics-servo/runs.json q_rms_mrad against {TWIN_GATE:g} x the T1 floor of "
           f"{acceptance_path} (generated_at {acceptance['generated_at']}); station limits from bam_rack_twin hardware/tape.py TAPE_STATIONS; "
           "written by gallery/examples/robotics-servo-gates/source/build.py")
    gates.write_table(CASE / "checks.json", f"Checks: {len(checks)} gate rows of {len(runs_doc['rows'])} real rack runs of CAN 12 and CAN 14", src, gates.field_list(labels), checks)
    gates.write_table(CASE / "windows.json", f"Windows: Speed and Angle per 1 s window of {len(runs_doc['rows'])} real rack runs", src, gates.field_list(labels), windows)
    print({"checks": len(checks), "windows": len(windows), "acceptance": acceptance_path.name})
    return 0


if __name__ == "__main__":
    sys.exit(main())
