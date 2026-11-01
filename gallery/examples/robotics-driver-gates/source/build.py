"""The Driver "Playback + Gates" twin's gate rows (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35): checks.json
and windows.json beside this folder, computed from the 27 real rack runs robotics-driver plays (its runs.json names each run's
npz under /archive/datasets/bam_rig, the moteus boards' own logs) with RobotDx's library, as §10's diagnostic rows.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-driver-gates/source/build.py

Read-only: the template's runs.json / samples.json and each run's npz.

checks.json, one row per run and check:
  Board temp   stock.box on temp_c, warn 60 / error 70 (sim2real's BOARD_TEMP: moteus's temperature register is the board's FET temperature)
  Bus voltage  stock.box on v_bus_v with the limits sim2real's diagnostics_run_rack.py uses: nominal 36 V when the run's median bus
               reads above 30 V, else 24 V; error beyond 15 % and warn beyond 10 % of nominal (the message says which nominal)
  Faults       stock.fault_codes (a limiter engaged on > 2 % of rows warns; a hard fault or watchdog timeout fails); level_history
  Rate         stock.sample_rate against the board's 100 Hz
windows.json: stream.monitor, 1 s windows stepping 0.5 s, per run: Board temp (the box's max against 60 / 70) and Faults.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import pathlib

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-driver"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits, evaluate  # noqa: E402
from robotdx.diagnostics.stock import BoxConfig, FaultCodesConfig, RateConfig  # noqa: E402
from robotdx.diagnostics.stock.health import Stamps  # noqa: E402

BOARD_TEMP = BoxConfig(channel="temp_c", unit="Cel", max=Limits.at_most(70.0, warn=60.0))  # sim2real's BOARD_TEMP numbers (its max)


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    samples, _ = gates.read_table(TEMPLATE / "samples.json")
    shown = {}
    for s in samples:
        shown.setdefault(s["run"], []).append(s["t"])
    labels = gates.run_labels(runs_doc)
    checks, windows = [], []
    for r in runs_doc["rows"]:
        run, device, started = r["run"], r["device"], r["started"]
        subject = f"{r['deployment']}/{device}"
        rel = pathlib.PurePosixPath(r["npz"])
        with np.load(gates.RACK / r["npz"]) as z:
            t = np.asarray(z["t"], float) - float(z["t"][0])
            col = {n: np.asarray(z[n], float) for n in ("q", "mode", "fault", "temp_c", "voltage")}
        span = gates.span_of(shown[run])
        assert abs(span[1] - round(float(t[-1]), 4)) < 1e-9, f"{run}: the template's last t is not the npz's"
        whole = gates.window3(span[0], span[1], span)
        common = dict(subject=subject, device=device, run=run, started=started, link=gates.link_run, basis="derived")
        full = gates.traj(t, col["q"], mode=col["mode"], fault=col["fault"], temp_c=col["temp_c"], v_bus_v=col["voltage"], run=run)

        def add(res, title, *, window=whole, hint="gate_matrix", **kw):
            checks.append(gates.row(res, id=f"{run}#{title}", title=title, window=window, hint=hint, parent=subject, **{**common, **kw}))

        res = gates.two_sided(evaluate("stock.box", BOARD_TEMP, [full], subject=subject), BOARD_TEMP)
        add(res, "Board temp", record=f"{rel} · temp_c")

        nominal = 36.0 if np.nanmedian(col["voltage"]) > 30 else 24.0
        volts = BoxConfig(channel="v_bus_v", unit="V", headline="min", min=Limits.at_least(0.85 * nominal, warn=0.9 * nominal),
                          max=Limits.at_most(1.15 * nominal, warn=1.1 * nominal))
        res = gates.two_sided(evaluate("stock.box", volts, [full], subject=subject), volts)
        add(res, "Bus voltage", record=f"{rel} · voltage",
            message=f"{res.message}; nominal {nominal:g} V (the bus reads {np.nanmedian(col['voltage']):g} V), error beyond 15 % and warn beyond 10 % of it")

        res = evaluate("stock.fault_codes", FaultCodesConfig(), [full], subject=subject)
        add(res, "Faults", window=gates.fault_window(t, col["fault"], col["mode"], span), hint="level_history", record=f"{rel} · fault")

        res = evaluate("stock.sample_rate", RateConfig(expected_hz=100.0), [Stamps(t, run)], subject=subject)
        add(res, "Rate", record=f"{rel} · t")

        for n, (end, res) in enumerate(gates.windowed("stock.box", BOARD_TEMP, full, subject=subject)):
            res = gates.two_sided(res, BOARD_TEMP)
            windows.append(gates.row(res, id=f"{run}#Board temp#{n}", title="Board temp", window=gates.window3(end - gates.WINDOW_S, end, span), hint="threshold_band",
                                     parent=subject, record=f"{rel} · temp_c", message=f"board temp max {res.value:.4g} Cel in the 1 s window ending {end:g} s; "
                                     "warn above 60, error above 70 (sim2real's BOARD_TEMP)", **common))
        for n, (end, res) in enumerate(gates.windowed("stock.fault_codes", FaultCodesConfig(), full, subject=subject)):
            windows.append(gates.row(res, id=f"{run}#Faults#{n}", title="Faults", window=gates.window3(end - gates.WINDOW_S, end, span), hint="level_history",
                                     parent=subject, record=f"{rel} · fault", **common))
    src = ("/archive/datasets/bam_rig rack_2026-10-23, -24 and -25 (real runs, the moteus boards' own logs: the npz robotics-driver's runs.json names), "
           "judged by robotdx.diagnostics (io-diagnostics); limits as sim2real's diagnostics_run_rack.py; written by gallery/examples/robotics-driver-gates/source/build.py")
    gates.write_table(CASE / "checks.json", f"Checks: {len(checks)} gate rows of {len(runs_doc['rows'])} real rack runs of CAN 12, 13 and 14", src, gates.field_list(labels), checks)
    gates.write_table(CASE / "windows.json", f"Windows: Board temp and Faults per 1 s window of {len(runs_doc['rows'])} real rack runs", src, gates.field_list(labels), windows)
    print({"checks": len(checks), "windows": len(windows)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
