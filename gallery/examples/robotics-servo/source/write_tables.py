"""The Servo template's display projection (gallery/robotics/CONTRACT.md §2-§4): runs.json, samples.json and devices.json
from build.py's full-rate replays (the --cache folder). Apart from build.py so the tables can be rewritten without
MuJoCo: `python3 -B -I gallery/examples/robotics-servo/source/write_tables.py CACHE` (numpy only, from any venv)."""

from __future__ import annotations

import datetime
import json
import math
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import numpy as np

CASE = pathlib.Path(__file__).resolve().parent.parent
DISPLAY_HZ = 20.0  # WHY 20: three situations and three difference pairs of 40 runs stay inside the case's 5 MB at this rate
LOCAL = ZoneInfo("America/Vancouver")  # the rig's wall clock: runs.started reads as the log says it happened
DEPLOYMENT = "1-DOF rack"
DEVICES = {
    12: {"device": "CAN 12", "type": "servo", "label": "CAN 12 · JMC 60ASM200 + moteus r4.11, 10:1", "parent": DEPLOYMENT, "order": 1, "part": "jmc-60asm200"},
    14: {"device": "CAN 14", "type": "servo", "label": "CAN 14 · SteadyWin GIM4305-10 + moteus c1, 10:1", "parent": DEPLOYMENT, "order": 2, "part": "steadywin-gim4305-10"},
}
SITUATIONS = [("target", "target"), ("real", "real"), ("twin", "sim")]
NOTE_DAY = {"10-24": "rack_2026-10-24", "10-25": "rack_2026-10-25"}


def num(v, digits):
    """A float rounded for display, or None for a missing value (never 0)."""
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


# the folder words a label keeps (the motor is named once, at the end; a day's own dataset folder says nothing more)
WORDS = {"dataset": "", "dataset_rotor": "", "floors": "floors", "cogging_phase": "cogging"}


def label(record) -> str:
    """The rail's and the table's name for a run, its session and kind first (the mock's "s09 · waypoints · 10-25"):
    s03 · sine · 10-25 rest2 · CAN 12."""
    day, *folder, session = record["run"].split("/")
    words = []
    for part in folder:
        if re.fullmatch(r"can\d+", part):
            continue
        part = re.sub(r"^can\d+_", "", part)
        part = WORDS.get(part, part)
        m = re.fullmatch(r"session_0*(\d+)", part)
        words.append(f"session {m.group(1)}" if m else part)
    where = " ".join([day, *[w for w in words if w]])
    return f"{session} · {record['kind']} · {where} · CAN {record['can']}"


def write(path: pathlib.Path, title: str, source: str, fields: list[dict], rows: list[dict]) -> None:
    """{title, source, schema, rows}, one row per line: a regenerated file diffs row by row."""
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    path.write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def write_tables(cache: pathlib.Path, records: list[dict], case: pathlib.Path = CASE, display_hz: float = DISPLAY_HZ) -> dict:
    records = sorted(records, key=lambda r: r["started_utc"])
    runs, samples = [], []
    for rec in records:
        a = np.load(pathlib.Path(cache) / (rec["run"].replace("/", "__") + ".npz"))
        stride = max(1, math.ceil(rec["native_hz"] / display_hz - 1e-9))
        picks = np.arange(0, a["t"].size, stride)
        # WHY the last row too: the display spans the run as logged, so the clock, the table's duration and the file agree
        if picks[-1] != a["t"].size - 1:
            picks = np.append(picks, a["t"].size - 1)
        device = DEVICES[rec["can"]]["device"]
        started = datetime.datetime.fromisoformat(rec["started_utc"].replace("Z", "+00:00")).astimezone(LOCAL)
        held = rec["held_out"]
        note = (f"held out: the twin's q RMS {rec['q_rms_mrad']:.3f} mrad reproduces the dataset file's {rec['expected_q_rms_mrad']:.3f} mrad "
                f"(rack_replays.py's oracle: {rec['oracle']})" if held else "not a held-out row of the dataset file: no file value to reproduce")
        runs.append({
            "run": rec["run"], "deployment": DEPLOYMENT, "started": started.isoformat(timespec="seconds"), "when": started.strftime("%b %d %H:%M"),
            "duration_s": round(float(a["t"][picks[-1]]), 4), "kind": rec["kind"], "devices": [device],
            "situations": [s for s, _ in SITUATIONS], "rate_hz": round(rec["native_hz"], 2), "display_hz": round(rec["native_hz"] / stride, 2),
            "label": label(rec), "basis": "real rack run; twin = bam_rack_twin replay", "note": note,
            "twin": rec["twin_version"], "q_rms_mrad": None if rec["q_rms_mrad"] is None else round(rec["q_rms_mrad"], 4),
            "held_out": held, "npz": rec["npz"],
        })
        cols = {
            "real": (a["q"], a["qd"], a["tau"]),
            "twin": (a["twin_q"], a["twin_qd"], a["twin_tau"]),
            "target": (a["q_target"], a["qd_target"], None),
        }
        for k in picks:
            t = round(float(a["t"][k]), 4)
            for situation, source in SITUATIONS:
                q, qd, tau = cols[situation]
                samples.append({"t": t, "run": rec["run"], "situation": situation, "source": source, "device": device,
                                "q_deg": num(np.degrees(q[k]), 4), "qd_deg_s": num(np.degrees(qd[k]), 3), "tau_nm": None if tau is None else num(tau[k], 4)})
    labels = {r["run"]: r["label"] for r in runs}
    assert len(set(labels.values())) == len(runs), "every run's label is its own"
    src = ("/archive/datasets/bam_rig rack_2026-10-24 and rack_2026-10-25 (real runs), replayed through each motor's twin by "
           "sim2real dashboards/source/rack_replays.py (bam_rack_twin); written by gallery/examples/robotics-servo/source/build.py")
    write(case / "runs.json", "Runs: 40 real rack runs of CAN 12 and CAN 14", src, [
        {"name": "run", "type": "string", "title": "Run", "labels": labels, "description": "day/folder/session under the rack's archive: a stable, unique id"},
        {"name": "deployment", "type": "string", "title": "Deployment"},
        {"name": "started", "type": "datetime", "title": "Started at", "description": "ISO 8601, the rig's local time with its offset"},
        {"name": "when", "type": "string", "title": "Started", "description": "started, as the table shows it (the rig's local time)"},
        {"name": "duration_s", "type": "number", "unit": "s", "title": "Duration", "decimals": 2},
        {"name": "kind", "type": "string", "title": "Kind"},
        {"name": "devices", "type": "array", "title": "Servo"},
        {"name": "situations", "type": "array", "title": "Situations"},
        {"name": "rate_hz", "type": "number", "unit": "Hz", "title": "Logged at", "decimals": 1},
        {"name": "display_hz", "type": "number", "unit": "Hz", "title": "Shown at", "decimals": 1},
        {"name": "label", "type": "string", "title": "Label"},
        {"name": "basis", "type": "string", "title": "Basis"},
        {"name": "note", "type": "string", "title": "Note"},
        {"name": "twin", "type": "string", "title": "Twin", "description": "the twin's version, rebuilt as its motor's dataset file names it"},
        {"name": "q_rms_mrad", "type": "number", "unit": "mrad", "title": "Twin q RMS", "decimals": 2,
         "description": "real − twin, RMS over the rows both were in position mode (scorecard.score_replay's), at the full logged rate"},
        {"name": "held_out", "type": "boolean", "title": "Held out", "description": "a held-out row of its motor's dataset file (whose twin_q_rms_mrad.full the replay reproduces)"},
        {"name": "npz", "type": "string", "title": "Run file", "description": "the run's npz in the rack's archive"},
    ], runs)
    write(case / "samples.json", "Samples: q, qd and τ of each run, real, twin and target", src, [
        {"name": "t", "type": "number", "unit": "s", "description": "seconds from the run's first kept row"},
        {"name": "run", "type": "string", "title": "Run", "labels": labels},
        {"name": "situation", "type": "string", "title": "Situation"},
        {"name": "source", "type": "string", "title": "Family"},
        {"name": "device", "type": "string", "title": "Servo"},
        {"name": "q_deg", "type": "number", "unit": "deg", "title": "Angle", "description": "joint angle, output frame (bam_rack_twin.evidence.to_output_frame)"},
        {"name": "qd_deg_s", "type": "number", "unit": "deg/s", "title": "Velocity"},
        {"name": "tau_nm", "type": "number", "unit": "N·m", "title": "Torque", "description": "the board's reported torque (real) or the twin's requested torque; none for the target"},
    ], samples)
    write(case / "devices.json", "Devices: the rack's two servos here", src, [
        {"name": "device", "type": "string"}, {"name": "type", "type": "string"}, {"name": "label", "type": "string"},
        {"name": "parent", "type": "string"}, {"name": "order", "type": "integer"}, {"name": "part", "type": "string"},
    ], [DEVICES[c] for c in sorted({r["can"] for r in records})])
    sizes = {n: (case / f"{n}.json").stat().st_size for n in ("runs", "samples", "devices")}
    print(json.dumps({"runs": len(runs), "samples": len(samples), "bytes": sizes}))
    return {"runs": runs, "order": [r["run"] for r in sorted(runs, key=lambda r: r["started"], reverse=True)]}


if __name__ == "__main__":
    cache = pathlib.Path(sys.argv[1])
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cache.glob("*.json"))]
    out = write_tables(cache, recs)
    print("order:", json.dumps(out["order"]))
