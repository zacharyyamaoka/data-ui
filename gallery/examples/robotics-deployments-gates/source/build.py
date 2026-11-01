"""The Deployments "Playback + Gates" twin's gate data (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35): gates.json,
checks.json, windows.json, components.json and live_checks.json beside this folder, from the 24 real rack runs robotics-deployments plays
(Oct 28-29, the rack's 8 stations; its runs.json `note` names each run's npz under /archive/datasets/bam_rig) and bam_rack_twin's acceptance
file, with RobotDx's library, as §10's diagnostic rows. data-ui computes none of it.

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python gallery/examples/robotics-deployments-gates/source/build.py

Read-only: the template's runs.json, deployments.json and runs/<run>.json, each run's npz, bam_rack_twin's deployment record and tape
parameter block (hardware/tape.py TAPE_STATIONS: each station's speed ceiling and board-frame q window), and the acceptance files.

  gates.json       the station gate matrix, one row per station x gate T1..T11, as the NEWEST bam_rack_twin acceptance file that holds all eight
                   stations judged them (gates.newest_acceptance: schema bam_rack_twin.acceptance/1, newest generated_at; the dataset's `source` names it)
  checks.json      per run (all 24), from its npz: Tracking, Speed, Angle, Board temp, Faults, Rate (RobotDx's stock functions); Angle is not_run on a
                   station with no q window (CAN 1, 14, 15: they turn freely)
  windows.json     per run, stream.monitor in 1 s windows stepping 0.5 s: Speed (|qd| box, error above the station's own speed ceiling), Angle (q box,
                   error outside the station's own window, stations that have one) and Board temp (warn above 60, error above 70)
  components.json  the rack as a tree for the roll-up: the rack, its plates, its stations (a station's id is its device name, as gates.json writes it);
                   `worst` is null in every row, the dashboard's roll-up fills it
  live_checks.json RobotDx's evaluations as a keyed feed: the newest run of each of the three newest stations, every check of checks.json (Angle only
                   on a station with a window) per 1 s window stepping 0.5 s; t = the run's wall-clock start (Unix s) + the window's end; id = <run>#<title>
The board frame is the output frame for every run here (the deployment record's output_per_board is 1 throughout Oct 28-29), which the producer asserts
against the template's own samples, so TAPE_STATIONS' board-frame numbers are the shown angle's.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import pathlib
import re

CASE = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = CASE.parent / "robotics-deployments"
sys.path.insert(0, str(CASE.parents[1] / "robotics"))

import numpy as np  # noqa: E402

import gates  # noqa: E402
from robotdx.diagnostics import Limits, evaluate  # noqa: E402
from robotdx.diagnostics.stock import BoxConfig, FaultCodesConfig, RateConfig, TrackingErrorConfig  # noqa: E402
from robotdx.diagnostics.stock.health import Stamps  # noqa: E402

BOARD_TEMP = BoxConfig(channel="temp_c", unit="Cel", max=Limits.at_most(70.0, warn=60.0))  # sim2real's BOARD_TEMP numbers (its max)
GATE_RANK = {"pass": 0, "warn": 1, "partial": 1, "not_run": 2, "fail": 4}   # RobotDx's ranks (partial is a gate word, ranked with warn)
LIVE_STATIONS = 3
WINDOW_TITLES = ("Speed", "Angle", "Board temp")


def load(r, stations):
    """One run, read from its npz: the Trajectory the checks take and the carrier trajectories for the two boxes."""
    npz = gates.RACK / r["note"]
    with np.load(npz) as z:
        t = np.asarray(z["t"], float) - float(z["t"][0])
        col = {n: np.asarray(z[n], float) for n in ("q", "q_target", "qd", "mode", "fault", "temp_c")}
    shown = json.loads((TEMPLATE / "runs" / f"{r['run']}.json").read_text(encoding="utf-8"))["rows"]
    real = [s for s in shown if s["situation"] == "real"]
    gap = np.abs(np.interp([s["t"] for s in real], t, np.degrees(col["q"])) - [s["q_deg"] for s in real]).max()
    assert gap < 0.1, f"{r['run']}: the npz is {gap:.3f} deg off the template's samples (a board frame other than the output's?)"
    can = int(r["device"].split()[1])
    st = stations[can]
    c = dict(r=r, run=r["run"], device=r["device"], can=can, started=r["started"], subject=f"{r['deployment']}/{r['device']}", rel=npz.relative_to(gates.RACK), t=t, col=col,
             span=gates.span_of([s["t"] for s in real]), ceiling=st["speed_ceiling_deg_s"], window=st["q_window_deg"])
    c["whole"] = gates.window3(c["span"][0], c["span"][1], c["span"])
    c["full"] = gates.traj(t, col["q"], q_target_rad=col["q_target"], qd_rad_s=col["qd"], mode=col["mode"], fault=col["fault"], temp_c=col["temp_c"], run=r["run"])
    c["speed_cfg"] = BoxConfig(channel="qd_rad_s", unit="deg/s", max=Limits(error_high=c["ceiling"]))
    # WHY the carrier columns: stock.box reads one named channel, so |qd| in deg/s rides in qd_rad_s and q in degrees in q_rad; the Results say deg/s and deg
    c["speed"] = gates.traj(t, col["q"], qd_rad_s=np.abs(np.degrees(col["qd"])), run=r["run"])
    c["angle_cfg"] = BoxConfig(channel="q_rad", unit="deg", min=Limits(error_low=c["window"][0]), max=Limits(error_high=c["window"][1])) if c["window"] else None
    c["angle"] = gates.traj(t, np.degrees(col["q"]), run=r["run"])
    return c


def around(c, t_event, pad=0.5):
    return gates.window3(t_event - pad, t_event + pad, c["span"])


def whole_run(c):
    """[(title, Result, window, hint, message | None, record key)] for the run as one stream."""
    out = []
    subject = c["subject"]
    res = evaluate("stock.tracking_error", TrackingErrorConfig(controlled_only=True), [c["full"]], subject=subject)
    out.append(("Tracking", res, gates.window3(res.t0, res.t1, c["span"]) if res.t0 is not None else c["whole"], res.message + " (no limit set: a reading, not a gate)", "q_rad - q_target_rad"))
    speed = np.abs(np.degrees(c["col"]["qd"]))
    res = gates.two_sided(evaluate("stock.box", c["speed_cfg"], [c["speed"]], subject=subject), c["speed_cfg"])
    out.append(("Speed", res, around(c, c["t"][int(np.argmax(speed))]),
                f"max |qd| {res.value:.4g} deg/s; {c['device']}'s speed ceiling {c['ceiling']:g} deg/s (bam_rack_twin TAPE_STATIONS)", "qd"))
    if c["angle_cfg"]:
        res = gates.two_sided(evaluate("stock.box", c["angle_cfg"], [c["angle"]], subject=subject), c["angle_cfg"])
        q = np.degrees(c["col"]["q"])
        at = c["t"][int(np.argmax(q) if res.metric == "max" else np.argmin(q))]
        out.append(("Angle", res, around(c, at), f"q {res.metric} {res.value:.4g} deg; {c['device']}'s window {c['window'][0]:g} to {c['window'][1]:g} deg "
                                                 "(bam_rack_twin TAPE_STATIONS, board frame)", "q"))
    else:
        res = gates.not_run({"window": None}, diagnostic="stock.box", subject=subject, title="Angle", unit="deg", code="NoWindow",
                            message=f"{c['device']} has no q window in bam_rack_twin's TAPE_STATIONS (it turns freely): nothing to judge the angle against")
        out.append(("Angle", res, None, None, "q"))
    res = gates.two_sided(evaluate("stock.box", BOARD_TEMP, [c["full"]], subject=subject), BOARD_TEMP)
    out.append(("Board temp", res, c["whole"], None, "temp_c"))
    res = evaluate("stock.fault_codes", FaultCodesConfig(), [c["full"]], subject=subject)
    out.append(("Faults", res, gates.fault_window(c["t"], c["col"]["fault"], c["col"]["mode"], c["span"]), None, "fault"))
    res = evaluate("stock.sample_rate", RateConfig(expected_hz=100.0), [Stamps(c["t"], c["run"])], subject=subject)
    out.append(("Rate", res, c["whole"], None, "t"))
    return out


def sliced(c):
    """[(title, end, Result, message | None)] in 1 s windows stepping 0.5 s: every check the run has (Angle only on a station with a window)."""
    subject, out = c["subject"], []
    for end, res in gates.windowed("stock.tracking_error", TrackingErrorConfig(controlled_only=True), c["full"], subject=subject):
        out.append(("Tracking", end, res, None))
    for end, res in gates.windowed("stock.box", c["speed_cfg"], c["speed"], subject=subject):
        res = gates.two_sided(res, c["speed_cfg"])
        out.append(("Speed", end, res, f"max |qd| {res.value:.4g} deg/s in the 1 s window ending {end:g} s; {c['device']}'s speed ceiling {c['ceiling']:g} deg/s (bam_rack_twin TAPE_STATIONS)"))
    if c["angle_cfg"]:
        for end, res in gates.windowed("stock.box", c["angle_cfg"], c["angle"], subject=subject):
            res = gates.two_sided(res, c["angle_cfg"])
            out.append(("Angle", end, res, f"q {res.metric} {res.value:.4g} deg in the 1 s window ending {end:g} s; {c['device']}'s window {c['window'][0]:g} to {c['window'][1]:g} deg "
                                           "(bam_rack_twin TAPE_STATIONS, board frame)"))
    for end, res in gates.windowed("stock.box", BOARD_TEMP, c["full"], subject=subject):
        res = gates.two_sided(res, BOARD_TEMP)
        out.append(("Board temp", end, res, f"board temp max {res.value:.4g} Cel in the 1 s window ending {end:g} s; warn above 60, error above 70 (sim2real's BOARD_TEMP)"))
    for end, res in gates.windowed("stock.fault_codes", FaultCodesConfig(), c["full"], subject=subject):
        out.append(("Faults", end, res, None))
    for end, res in gates.each_window(c["full"], lambda w: evaluate("stock.sample_rate", RateConfig(expected_hz=100.0), [Stamps(w.t, c["run"])], subject=subject)):
        out.append(("Rate", end, res, None))
    return out


def station_tree(record, runs_title):
    """components.json: the rack, its plates, its stations, from the deployment record's `station` text."""
    rows = [{"id": record["id"], "label": runs_title, "parent": None, "kind": "rack", "worst": None}]
    plates = {}
    for comp in sorted((c for c in record["components"] if c.get("can_id") is not None), key=lambda c: c["can_id"]):
        text = comp["station"]
        plate = "GIM43 plate" if "GIM43 plate" in text else re.match(r"(JMC60 plates)", text).group(1)
        if plate not in plates:
            plates[plate] = {"id": plate, "label": plate, "parent": record["id"], "kind": "plate", "worst": None}
        detail = text.split(", ", 1)[1] if ", " in text else text
        rows.append({"id": f"CAN {comp['can_id']}", "label": f"CAN {comp['can_id']} · {detail}", "parent": plate, "kind": "station", "worst": None})
    return [rows[0], *plates.values(), *rows[1:]]


def main() -> int:
    runs_doc = gates.read_table(TEMPLATE / "runs.json")[1]
    labels = gates.run_labels(runs_doc)
    record = json.loads(gates.RECORD.read_text(encoding="utf-8"))
    deployment = record["id"]
    stations = gates.tape_stations()
    acceptance_path, acceptance = gates.newest_acceptance()

    # ---- gates.json: bam_rack_twin's own judgement, station x T1..T11
    gate_rows = []
    for can in sorted(int(k) for k in acceptance["stations"]):
        device, subject = f"CAN {can}", f"{deployment}/CAN {can}"
        for g in acceptance["stations"][str(can)]["gates"]:
            k = int(g["id"][1:])
            verdict = g["status"]
            assert verdict in GATE_RANK, f"{device} {g['id']}: status {verdict!r} is not a gate word"
            value = g.get("value")
            gate_rows.append({
                "id": f"{device}#{g['id']}", "subject": subject, "device": device, "diagnostic": f"bam_rack_twin.{g['id']}", "title": f"{g['id']} {g['name']}",
                "verdict": verdict, "rank": GATE_RANK[verdict], "value": gates.num(value) if isinstance(value, (int, float)) else None, "unit": None,
                "warn_lo": None, "warn_hi": None, "error_lo": None, "error_hi": None, "target": None, "better": None, "t": None, "t0": None, "t1": None, "run": None,
                "started": None, "message": g.get("detail") or None, "why": None, "evidence": None, "basis": "derived", "source": str(acceptance_path), "sourceUrl": None,
                "record": f"{acceptance_path.name} · stations.{can}.gates.{g['id']}", "parent": subject, "hint": "gate_matrix", "order": k - 1,
                "target_text": g.get("target"), "value_text": None if isinstance(value, (int, float)) or value is None else str(value)})
    src_gates = (f"bam_rack_twin acceptance, the newest file that holds all eight stations: {acceptance_path} (schema {acceptance['schema']}, generated_at "
                 f"{acceptance['generated_at']}); written by gallery/examples/robotics-deployments-gates/source/build.py")
    gates.write_table(CASE / "gates.json", f"Gates: the rack's {len(acceptance['stations'])} stations x T1..T11, as {acceptance_path.name} judged them", src_gates,
                      gates.field_list(extra=[("target_text", "string"), ("value_text", "string")]), gate_rows)

    # ---- the runs
    checks, windows, loaded = [], [], []
    for r in runs_doc["rows"]:
        c = load(r, stations)
        loaded.append(c)
        common = dict(subject=c["subject"], device=c["device"], run=c["run"], started=c["started"], link=gates.link_select, basis="derived", parent=c["subject"])
        for title, res, window, message, key in whole_run(c):
            checks.append(gates.row(res, id=f"{c['run']}#{title}", title=title, window=window, hint="gate_matrix", record=f"{c['rel']} · {key}",
                                    message=message, **common))
        count = {}
        for title, end, res, message in sliced(c):
            if title in WINDOW_TITLES:
                n = count[title] = count.get(title, -1) + 1
                windows.append(gates.row(res, id=f"{c['run']}#{title}#{n}", title=title, window=gates.window3(end - gates.WINDOW_S, end, c["span"]),
                                         hint="threshold_band", record=f"{c['rel']} · {title}", message=message, **common))
    src = ("/archive/datasets/bam_rig rack_2026-10-28 and -29 (real runs, the npz robotics-deployments' runs.json names), judged by robotdx.diagnostics (io-diagnostics); "
           "each station's speed ceiling and q window from bam_rack_twin hardware/tape.py TAPE_STATIONS; written by gallery/examples/robotics-deployments-gates/source/build.py")
    gates.write_table(CASE / "checks.json", f"Checks: {len(checks)} gate rows of {len(runs_doc['rows'])} real rack runs", src, gates.field_list(labels), checks)
    gates.write_table(CASE / "windows.json", f"Windows: Speed, Angle and Board temp per 1 s window of {len(runs_doc['rows'])} real rack runs", src, gates.field_list(labels), windows)

    # ---- components.json
    deployments = json.loads((TEMPLATE / "deployments.json").read_text(encoding="utf-8"))
    tree = station_tree(record, deployments["rows"][0]["title"])
    fields = [{"name": "id", "type": "string"}, {"name": "label", "type": "string"}, {"name": "parent", "type": "string"}, {"name": "kind", "type": "string"},
              {"name": "worst", "type": "integer", "display": "status", "labels": {"0": "pass", "1": "warn", "2": "not run", "3": "stale", "4": "fail"}}]
    gates.write_table(CASE / "components.json", "Components: the rack, its plates and its stations (the roll-up's tree)",
                      f"bam_rack_twin deployment record {gates.shown(gates.RECORD)} (station text of each board); written by gallery/examples/robotics-deployments-gates/source/build.py", fields, tree)

    # ---- live_checks.json: the newest run of each of the three newest stations, one after another in time
    newest = {}
    for c in sorted(loaded, key=lambda c: c["started"], reverse=True):
        newest.setdefault(c["device"], c)
    picked = sorted(list(newest.values())[:LIVE_STATIONS], key=lambda c: gates.started_unix(c["started"]))
    live = []
    for c in picked:
        start = gates.started_unix(c["started"])
        common = dict(subject=c["subject"], device=c["device"], run=c["run"], started=c["started"], link=gates.link_select, basis="derived", parent=c["subject"])
        for title, end, res, message in sliced(c):
            live.append(gates.row(res, id=f"{c['run']}#{title}", title=title, window=gates.window3(end - gates.WINDOW_S, end, c["span"]), hint="gate_matrix",
                                  record=f"{c['rel']} · {title}", message=message, t=start + end, **common))
    live.sort(key=lambda x: (x["t"], x["order"]))
    gates.write_table(CASE / "live_checks.json", f"Live checks: {len(live)} windowed evaluations of {len(picked)} runs, a keyed feed (t = Unix s)",
                      src + f"; the runs: {', '.join(c['run'] for c in picked)}", gates.field_list(labels), live)
    print({"gates": len(gate_rows), "checks": len(checks), "windows": len(windows), "components": len(tree), "live": len(live), "acceptance": acceptance_path.name,
           "live runs": [c["run"] for c in picked]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
