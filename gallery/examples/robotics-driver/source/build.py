"""The BLDC driver template's data (PEP 0010 P4, docs/peps/0010-robotics-playback.md §6, the bldc-driver.png mock): the
1-DOF rack's moteus boards on CAN 12, 13 and 14, Oct 23-25 2026, as the trajectory contract's tables
(gallery/robotics/CONTRACT.md): runs.json, samples.json, events.json, devices.json and coverage_samples.csv (+ its
.schema.json) beside this folder. Every number is the board's own log; nothing is simulated.

    python3 -B -I gallery/examples/robotics-driver/source/build.py        (numpy only; the archive is read-only)

Inputs (read-only): RACK (default /archive/datasets/bam_rig), rack_2026-10-23, -24 and -25: every run npz under a
runs/ folder (t, wall, q, qd, i_q, i_d, voltage, temp_c, power_w, mode, fault, …) and its sidecar .json (can_id, kind),
kept when the board is CAN 12, 13 or 14 and the run has at least 20 samples (PEP 0010's rack count rule): 221, 254 and 57
runs. The boards' limits come from that day's electrical survey (rack_2026-10-23/electrical/0607623A_after_restart.json
and 272813EF_after_recal.json: servo.max_current_A).

What it writes:
  - samples.json: the PLAYBACK runs (`pick_runs`: per board every run in which the board reported a limiter or fault,
    then the newest run of each kind, then the newest others, up to PER_BOARD), every STRIDE-th logged row plus the last
    and every row where mode or fault changes, never averaged: i_q_a, i_d_a, v_bus_v, temp_c, power_w as logged; mode and fault as moteus names them (text).
    Situation `real`, family `real`: there is no twin of the board's currents (the twin replays torque, not current).
  - events.json: each playback run's mode changes and fault-register changes at FULL rate (the first logged row of each
    new state), kind `mode` or `fault`, label the state entered ("position", "limiter 99 · max current", "none").
  - coverage_samples.csv: EVERY kept run of the three boards (532), on a uniform COVERAGE_HZ time grid (w = 1, so a
    count is time spent: count / COVERAGE_HZ s) plus each run's argmin and argmax row of i_q, qd, temp_c and voltage
    (w = 0): histograms sum w and stay unbiased, min and max over rows stay exact (CONTRACT §4, M4 weighted).
  - runs.json: one row per playback run; devices.json: the three boards.
Self-checks before writing (the build stops when one fails): every written i_q equals the npz at its row; every
coverage run's extremes are in its rows exactly; the playback runs' labels are unique.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import pathlib
import re
import sys
from collections import Counter
from zoneinfo import ZoneInfo

import numpy as np

CASE = pathlib.Path(__file__).resolve().parents[1]
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
DAYS = ("rack_2026-10-23", "rack_2026-10-24", "rack_2026-10-25")
BOARDS = (12, 13, 14)
MIN_SAMPLES = 20
PER_BOARD = 9
MAX_PLAYBACK_S = 25.0   # WHY: the rack's 70-80 s staircases would take a third of the budget; a longer run still counts in coverage
STRIDE = 3            # WHY 3: ~31 Hz of the ~94 Hz log keeps the current's texture and the 30 runs inside the case's budget
COVERAGE_HZ = 4.0     # WHY 4: 532 runs (3,807 s) at 4 Hz is ~15k grid rows plus ~3.7k kept extremes, a CSV inside the budget
LOCAL = ZoneInfo("America/Vancouver")   # the rig's wall clock: started reads as the log says it happened
DEPLOYMENT = "1-DOF rack"
SURVEYS = (RACK / "rack_2026-10-23" / "electrical" / "0607623A_after_restart.json", RACK / "rack_2026-10-23" / "electrical" / "272813EF_after_recal.json")

# moteus's mode register (moteus protocol.py Mode; 2-4 are the firmware's "preparing to operate" states)
MODES = {0: "stopped", 1: "fault", 2: "preparing", 3: "preparing", 4: "preparing", 5: "pwm", 6: "voltage", 7: "voltage foc",
         8: "voltage dq", 9: "current", 10: "position", 11: "timeout", 12: "zero velocity", 13: "stay within",
         14: "measure inductance", 15: "brake"}
# moteus's fault register (fw 1.x error.h): 32-48 faults; 96-105 in a running mode are LIMITERS, the reason the output
# is being limited, not a fault (bam_ws traj_integration_tests dog_leg_hardware.py and bam_gravity_comp's notes)
FAULTS = {32: "calibration fault", 33: "motor driver fault", 34: "over voltage", 35: "encoder fault", 36: "motor not configured",
          37: "pwm cycle overrun", 38: "over temperature", 39: "outside position limit", 40: "under voltage", 41: "configuration changed",
          42: "theta invalid", 43: "position invalid", 44: "driver enable fault", 45: "stop position deprecated", 46: "timing violation",
          47: "bemf feedforward without accel", 48: "invalid position limits"}
LIMITERS = {96: "max velocity", 97: "max power", 98: "max voltage", 99: "max current", 100: "board temperature", 101: "motor temperature",
            102: "commanded max torque", 103: "position bounds", 104: "flux braking", 105: "field weakening"}


def fault_text(code: float) -> str | None:
    """The fault register as words: null when 0 (the contract: "null when none")."""
    code = int(code)
    if code == 0:
        return None
    if code in LIMITERS:
        return f"limiter {code} · {LIMITERS[code]}"
    return f"fault {code} · {FAULTS.get(code, 'unknown')}"


def fault_colors(samples: list[dict]) -> dict:
    """Each fault text's slot: the limiters present amber, pink and purple in code order (never green, never the sim
    orange), a fault the red slot. WHY slots, not tones: the chart colours a column's values from its `colors` (docs/CONTRACT.md §4)."""
    texts = sorted({s["fault"] for s in samples if s["fault"]}, key=lambda x: int(x.split()[1]))
    limiters = [x for x in texts if x.startswith("limiter")]
    assert len(limiters) <= 3, "more limiters than distinct non-status slots: give them more"
    # WHY no entry for a null cell (the register at 0): a chart draws it as its column's empty label ("No fault"), muted
    # by the kit itself (CONTRACT §25, kit gap 6), so the strip spans the whole run and reads "none" where it was 0
    return {x: 8 if x.startswith("fault") else (4, 5, 7)[limiters.index(x)] for x in texts}


def mode_text(code: float) -> str:
    return MODES.get(int(code), f"mode {int(code)}")


def num(v, digits):
    """A float rounded for display, or None for a missing value (never 0)."""
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


def run_id(npz: pathlib.Path) -> str:
    """day/folder…/sNN: rack_2026-10-24/session_27/runs/s09_can12_sine.npz -> 10-24/session_27/s09 (the servo case's ids)."""
    rel = npz.relative_to(RACK)
    day = rel.parts[0].removeprefix("rack_2026-")
    folders = [p for p in rel.parts[1:-1] if p != "runs"]
    m = re.match(r"(s\d+)_", npz.stem)
    return "/".join([day, *folders, m.group(1) if m else npz.stem])


WORDS = {"dataset": "", "dataset_rotor": "rotor", "floors": "floors", "ff": "ff", "pid_autotune": "autotune", "sessions": "",
         "verify": "verify", "cogging_phase": "cogging", "batch2": "", "warm": "warm"}


def label(rec: dict) -> str:
    """The rail's name for a run, its session and kind first (the mock's "s09 · waypoints · 10-25"):
    s09 · sine · 10-24 session 27 · CAN 12."""
    day, *folder, session = rec["run"].split("/")
    words = []
    for part in folder:
        if re.fullmatch(r"can\d+", part):
            continue
        part = re.sub(r"^(reid_)?can\d+[_-]?", "", part)
        part = WORDS.get(part, part)
        m = re.fullmatch(r"session_0*(\w+)", part)
        words.append(f"session {m.group(1)}" if m else part)
    where = " ".join([day, *[w for w in words if w]])
    return f"{session} · {rec['kind']} · {where} · CAN {rec['can']}"


def load_runs() -> list[dict]:
    out = []
    for day in DAYS:
        for npz in sorted((RACK / day).rglob("runs/*.npz")):
            meta_path = npz.with_suffix(".json")
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if meta.get("can_id") not in BOARDS:
                continue
            with np.load(npz) as a:
                if a["t"].size < MIN_SAMPLES:
                    continue
                arrays = {k: np.asarray(a[k], float) for k in ("t", "wall", "qd", "i_q", "i_d", "voltage", "temp_c", "power_w", "mode", "fault")}
            rec = {"npz": npz, "can": int(meta["can_id"]), "kind": meta.get("kind") or "unknown", "arrays": arrays}
            rec["run"] = run_id(npz)
            out.append(rec)
    # WHY a longer id only where needed: a tape run's three speeds share their sNN (s05_can14_tape_fast / _medium /
    # _slow), so those ids keep the rest of the stem without the board (10-23/session_01c/s05_tape_fast)
    ids = Counter(r["run"] for r in out)
    for r in out:
        if ids[r["run"]] > 1:
            r["run"] = r["run"].rsplit("/", 1)[0] + "/" + re.sub(r"_can\d+", "", r["npz"].stem)
    ids = Counter(r["run"] for r in out)
    assert all(n == 1 for n in ids.values()), f"run ids collide: {[k for k, n in ids.items() if n > 1][:3]}"
    return out


def pick_runs(runs: list[dict]) -> list[dict]:
    """Per board, up to PER_BOARD playback runs of at most MAX_PLAYBACK_S: every run whose fault register was ever
    non-zero (limiters and faults: what a driver page is for), then the newest run of each kind not yet picked, then the
    newest others."""
    chosen = []
    for can in BOARDS:
        mine = sorted((r for r in runs if r["can"] == can and r["arrays"]["t"][-1] - r["arrays"]["t"][0] <= MAX_PLAYBACK_S),
                      key=lambda r: -r["arrays"]["wall"][0])
        picked = [r for r in mine if np.any(r["arrays"]["fault"] != 0)][:PER_BOARD]
        for kind in dict.fromkeys(r["kind"] for r in mine):
            if len(picked) >= PER_BOARD:
                break
            r = next(r for r in mine if r["kind"] == kind)
            if r not in picked:
                picked.append(r)
        for r in mine:
            if len(picked) >= PER_BOARD:
                break
            if r not in picked:
                picked.append(r)
        chosen += picked
    return chosen


def changes(values: np.ndarray) -> list[int]:
    """Row indices where a register takes a new value (row 0 included: the state the run starts in)."""
    v = np.asarray(values)
    return [0] + [int(i) for i in np.flatnonzero(v[1:] != v[:-1]) + 1]


def write(path: pathlib.Path, title: str, source: str, fields: list[dict], rows: list[dict]) -> None:
    """{title, source, schema, rows}, one row per line: a regenerated file diffs row by row."""
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def csv_cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, str):
        return '"' + v.replace('"', '""') + '"' if ("," in v or '"' in v) else v
    return repr(v) if isinstance(v, float) else str(v)


def limits() -> dict[int, float]:
    out = {}
    for path in SURVEYS:
        boards = json.loads(path.read_text(encoding="utf-8"))["boards"]
        for can, b in boards.items():
            v = b.get("servo.max_current_A")
            if int(can) in BOARDS and isinstance(v, (int, float)):
                out[int(can)] = float(v)
    return out


def main() -> int:
    runs = load_runs()
    counts = Counter(r["can"] for r in runs)
    print("kept runs per board:", dict(sorted(counts.items())))
    play = pick_runs(runs)
    src = (f"/archive/datasets/bam_rig {', '.join(DAYS)}: the rack's own run logs (moteus registers as logged), CAN 12, 13 and 14; "
           "written by gallery/examples/robotics-driver/source/build.py")
    labels = {}
    runs_rows, samples, events = [], [], []
    worst_iq = 0.0
    for rec in sorted(play, key=lambda r: r["arrays"]["wall"][0]):
        a = rec["arrays"]
        n = a["t"].size
        # WHY the change rows too: a limiter can hold for two logged rows (22 ms), which every-STRIDE-th row would skip; the
        # row where mode or fault takes a new value is kept, so every state the board reported draws from its exact start
        picks = np.array(sorted(set(range(0, n, STRIDE)) | {n - 1} | set(changes(a["mode"])) | set(changes(a["fault"]))))
        t = a["t"] - a["t"][0]
        device = f"CAN {rec['can']}"
        hz = (n - 1) / (t[-1] - t[0])
        started = datetime.datetime.fromtimestamp(a["wall"][0], tz=datetime.timezone.utc).astimezone(LOCAL)
        rec["label"] = label(rec)
        labels[rec["run"]] = rec["label"]
        limited = sorted({fault_text(c) for c in np.unique(a["fault"]) if c != 0})
        runs_rows.append({
            "run": rec["run"], "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
            "duration_s": round(float(t[picks[-1]]), 4), "kind": rec["kind"], "devices": [device], "device": device,
            "situations": ["real"], "rate_hz": round(hz, 2), "display_hz": round(hz / STRIDE, 2), "label": rec["label"],
            "basis": "real: the board's own log", "note": ("the fault register reported " + "; ".join(limited)) if limited else "no limiter or fault reported",
            "npz": str(rec["npz"].relative_to(RACK)),
        })
        for k in picks:
            iq = num(a["i_q"][k], 4)
            worst_iq = max(worst_iq, abs(iq - a["i_q"][k]))
            samples.append({"t": round(float(t[k]), 4), "run": rec["run"], "situation": "real", "source": "real", "device": device,
                            "i_q_a": iq, "i_d_a": num(a["i_d"][k], 4), "v_bus_v": num(a["voltage"][k], 2), "temp_c": num(a["temp_c"][k], 2),
                            "power_w": num(a["power_w"][k], 4), "mode": mode_text(a["mode"][k]), "fault": fault_text(a["fault"][k])})
        for kind, reg, text in (("mode", a["mode"], mode_text), ("fault", a["fault"], fault_text)):
            for i in changes(reg):
                if kind == "fault" and i == 0 and reg[0] == 0:
                    continue   # a run that starts with no fault has no fault event at 0
                events.append({"t": round(float(t[i]), 4), "run": rec["run"], "device": device, "kind": kind, "label": text(reg[i]) or "none"})
    assert worst_iq <= 5e-5 + 1e-12, f"a written i_q is {worst_iq} A off its npz row"
    assert len(set(labels.values())) == len(labels), "every run's label is its own"

    # ---- coverage: every kept run of the three boards
    cov = []
    for rec in sorted(runs, key=lambda r: r["arrays"]["wall"][0]):
        a = rec["arrays"]
        t = a["t"] - a["t"][0]
        grid = np.arange(0.0, t[-1], 1.0 / COVERAGE_HZ)
        picks = np.unique(np.clip(np.searchsorted(t, grid), 0, t.size - 1))
        qd = np.degrees(a["qd"])
        extremes = set()
        for v in (a["i_q"], qd, a["temp_c"], a["voltage"]):
            if np.isfinite(v).any():
                extremes.update([int(np.nanargmin(v)), int(np.nanargmax(v))])
        extremes -= set(picks.tolist())
        device = f"CAN {rec['can']}"
        for i, w in [(int(i), 1) for i in picks] + [(i, 0) for i in sorted(extremes)]:
            cov.append([round(float(t[i]), 4), rec["run"], "real", "real", device, rec["kind"], num(a["i_q"][i], 4), num(qd[i], 3),
                        num(a["temp_c"][i], 2), num(a["voltage"][i], 2), w])
        # self-check: the run's extremes are in its rows, exactly (to the written digits)
        mine = [r for r in cov if r[1] == rec["run"]]
        for col, v, d in ((6, a["i_q"], 4), (7, qd, 3), (8, a["temp_c"], 2), (9, a["voltage"], 2)):
            vals = [r[col] for r in mine if r[col] is not None]
            assert min(vals) == num(np.nanmin(v), d) and max(vals) == num(np.nanmax(v), d), f"{rec['run']}: extremes of column {col}"

    # ---- write
    write(CASE / "runs.json", f"Runs: {len(runs_rows)} real rack runs of CAN 12, 13 and 14, their driver channels", src, [
        {"name": "run", "type": "string", "title": "Run", "labels": labels, "description": "day/folder/session under the rack's archive: a stable, unique id"},
        {"name": "deployment", "type": "string", "title": "Deployment"},
        {"name": "started", "type": "datetime", "title": "Started at", "description": "ISO 8601, the rig's local time with its offset"},
        {"name": "when", "type": "string", "title": "Started", "description": "started, as a table shows it (the rig's local time)"},
        {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration", "decimals": 2},
        {"name": "kind", "type": "string", "title": "Run kind"},
        {"name": "devices", "type": "array", "title": "Devices"},
        {"name": "device", "type": "string", "title": "Driver", "description": "the run's one board (the rack runs one board at a time): the rail's Driver and the coverage panels' link"},
        {"name": "situations", "type": "array", "title": "Situations"},
        {"name": "rate_hz", "type": "number", "unit": "Hz", "title": "Logged at", "decimals": 1},
        {"name": "display_hz", "type": "number", "unit": "Hz", "title": "Shown at", "decimals": 1},
        {"name": "label", "type": "string", "title": "Label"},
        {"name": "basis", "type": "string", "title": "Basis"},
        {"name": "note", "type": "string", "title": "Note"},
        {"name": "npz", "type": "string", "title": "Run file", "description": "the run's npz under /archive/datasets/bam_rig"},
    ], runs_rows)
    write(CASE / "samples.json", "Samples: the boards' driver channels, run by run", src, [
        {"name": "t", "type": "number", "unit": "s", "description": "seconds from the run's first logged row"},
        {"name": "run", "type": "string", "title": "Run", "labels": labels},
        {"name": "situation", "type": "string", "title": "Situation"},
        {"name": "source", "type": "string", "title": "Family"},
        {"name": "device", "type": "string", "title": "Driver"},
        {"name": "i_q_a", "type": "number", "unit": "A", "title": "q-axis current", "description": "the board's i_q register, as logged"},
        {"name": "i_d_a", "type": "number", "unit": "A", "title": "d-axis current"},
        {"name": "v_bus_v", "type": "number", "unit": "V", "title": "Bus voltage", "description": "the board's voltage register (0.5 V steps)"},
        {"name": "temp_c", "type": "number", "unit": "°C", "title": "Board temperature", "description": "the board's temperature register: its FET / board temperature (sim2real's catalog: driver.board_temp), not the winding's"},
        {"name": "power_w", "type": "number", "unit": "W", "title": "Power"},
        {"name": "mode", "type": "string", "title": "Mode", "description": "moteus's mode register, by name (position = 10)",
         "colors": {"position": 1, "stopped": 0, "preparing": 7, "fault": 8, "timeout": 4}},
        {"name": "fault", "type": "string", "title": "Fault", "description": "moteus's fault register: a limiter (96-105, why the output is being limited) or a fault (32-48); null when none",
         "colors": fault_colors(samples)},
    ], samples)
    write(CASE / "events.json", "Events: each run's mode and fault-register changes, at the log's full rate", src, [
        {"name": "t", "type": "number", "unit": "s", "description": "seconds from the run's first logged row: the first row of the new state"},
        {"name": "run", "type": "string", "title": "Run", "labels": labels},
        {"name": "device", "type": "string", "title": "Driver"},
        {"name": "kind", "type": "string", "title": "Kind", "description": "mode or fault"},
        {"name": "label", "type": "string", "title": "State entered"},
    ], events)
    lim = limits()
    devices = [{"device": f"CAN {c}", "type": "driver", "label": f"CAN {c} · moteus board", "parent": DEPLOYMENT, "order": i + 1,
                "i_max_a": lim.get(c)} for i, c in enumerate(BOARDS)]
    write(CASE / "devices.json", "Devices: the rack's three moteus boards here", src, [
        {"name": "device", "type": "string"}, {"name": "type", "type": "string"}, {"name": "label", "type": "string"},
        {"name": "parent", "type": "string"}, {"name": "order", "type": "integer"},
        {"name": "i_max_a", "type": "number", "unit": "A", "description": "servo.max_current_A, the 10-23 electrical survey"},
    ], devices)
    cols = ["t", "run", "situation", "source", "device", "kind", "i_q_a", "qd_deg_s", "temp_c", "v_bus_v", "w"]
    (CASE / "coverage_samples.csv").write_text(",".join(cols) + "\n" + "".join(",".join(csv_cell(v) for v in r) + "\n" for r in cov), encoding="utf-8")
    # WHY `path`: the .base names this sidecar, which names its rows (CONTRACT §3), so every reader types the CSV alike
    sidecar = {"title": f"Coverage: all {len(runs)} rack runs of CAN 12, 13 and 14 (Oct 23-25), decimated", "source": src, "path": "coverage_samples.csv",
               "description": (f"Every kept run on a uniform {COVERAGE_HZ:g} Hz time grid (w = 1: a count is time spent, count / {COVERAGE_HZ:g} s) "
                               "plus each run's argmin and argmax row of i_q, qd, temp_c and voltage (w = 0): sum w for a histogram; min and max over rows are exact."),
               "schema": {"fields": [
                   {"name": "t", "type": "number", "unit": "s"}, {"name": "run", "type": "string", "title": "Run"},
                   {"name": "situation", "type": "string"}, {"name": "source", "type": "string", "title": "Family"},
                   {"name": "device", "type": "string", "title": "Driver"}, {"name": "kind", "type": "string", "title": "Run kind", "description": "the run's kind (runs.json's): a box per kind reads its own rows, never a join"},
                   {"name": "i_q_a", "type": "number", "unit": "A", "title": "i_q"}, {"name": "qd_deg_s", "type": "number", "unit": "deg/s", "title": "qd", "description": "the board's velocity, its output frame"},
                   {"name": "temp_c", "type": "number", "unit": "°C", "title": "Board temperature"}, {"name": "v_bus_v", "type": "number", "unit": "V", "title": "Bus voltage"},
                   {"name": "w", "type": "integer", "title": "Weight", "description": "1 on the time grid, 0 for a kept extreme"}]}}
    (CASE / "coverage_samples.schema.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sizes = {p.name: p.stat().st_size for p in sorted(CASE.iterdir()) if p.is_file() and p.suffix in (".json", ".csv")}
    print(json.dumps({"runs": len(runs_rows), "samples": len(samples), "events": len(events), "coverage rows": len(cov), "coverage runs": len(runs), "bytes": sizes}))
    print("playback runs:", json.dumps([[r["run"], r["kind"], r["device"], r["duration_s"], r["note"]] for r in runs_rows]))
    print("order (newest first):", json.dumps([r["run"] for r in sorted(runs_rows, key=lambda r: r["started"], reverse=True)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
