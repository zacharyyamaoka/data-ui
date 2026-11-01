"""What the six "Playback + Gates" producers share (PEP 0010 P5, docs/peps/0010-robotics-playback.md §10; CONTRACT §35).

data-ui computes no gate, metric or verdict: the producers in gallery/examples/robotics-<part>-gates/source/ write them
as rows (§10's diagnostic row), from the real runs where the archive has them, with RobotDx's library
(robotdx.diagnostics, ~/io-diagnostics) as the calculation and `Limits` / `judge` as the threshold check.
Run a producer in an environment that carries the library (numpy comes with it):

    env -u VIRTUAL_ENV uv run --isolated --with "~/io-diagnostics[diagnostics]" python <producer>

Read-only on /archive/datasets/bam_rig, bam_rack_twin's deployment record and sim2real. This module holds: the columns of a
diagnostic row and its Frictionless field list, the three evidence-link spellings, the station limits (read from
bam_rack_twin's own tape parameter block), the newest acceptance file, the rounding of an evidence window to the 3
decimals a link writes, and the few RobotDx wrappers more than one twin needs (a two-sided box, a windowed monitor).
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # WHY first: the imports below must leave no __pycache__ in the library's or the archive's tree

import ast
import dataclasses
import datetime
import json
import math
import os
import pathlib
import urllib.parse

import numpy as np

from robotdx.diagnostics import Limits, Trajectory
from robotdx.diagnostics.core import RANK, direction
from robotdx.diagnostics.core import result as make_result
from robotdx.diagnostics.stream import monitor, windows as time_windows

HERE = pathlib.Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
RECORD = pathlib.Path(os.environ.get("BAM_RACK_TWIN_RECORD", str(pathlib.Path.home() / "bam_ws" / ".claude" / "worktrees" / "sim-to-real-motor-models-f1ee43" / "src" / "dev"
                                                                 / "bam_rack_twin" / "records" / "one-dof-test-rack" / "deployment.json")))
LIBRARY = "robotdx.diagnostics"
WINDOW_S, STEP_S = 1.0, 0.5   # RobotDx's window for the rack's streams: 1 s, stepping 0.5 s

# one column position per check title, the same in every twin (the matrix's column order); a title not here is a producer's bug
ORDER = {"Tracking": 0, "Twin error": 1, "Speed": 2, "Angle": 3, "Board temp": 4, "Bus voltage": 5, "Faults": 6, "Rate": 7, "Dropped": 8,
         "Frame interval": 9, "Path error": 10, "Path max": 11, "Rotation": 12, "Grip force": 13, "Grip width": 14}

COLUMNS = [("id", "string"), ("subject", "string"), ("device", "string"), ("diagnostic", "string"), ("title", "string"), ("verdict", "string"),
           ("rank", "integer"), ("value", "number"), ("unit", "string"), ("warn_lo", "number"), ("warn_hi", "number"), ("error_lo", "number"),
           ("error_hi", "number"), ("target", "number"), ("better", "string"), ("t", "number"), ("t0", "number"), ("t1", "number"),
           ("run", "string"), ("started", "datetime"), ("message", "string"), ("why", "string"), ("evidence", "string"), ("basis", "string"),
           ("source", "string"), ("sourceUrl", "string"), ("record", "string"), ("parent", "string"), ("hint", "string"), ("order", "integer")]
NUMBER_UNITS = ("value", "warn_lo", "warn_hi", "error_lo", "error_hi", "target")


# ------------------------------------------------------------------------------------------------- tables
def num(v, digits=6):
    """A float rounded for the file, or None for a missing or non-finite value (never 0)."""
    if v is None or isinstance(v, bool):
        return v
    v = float(v)
    return round(v, digits) if math.isfinite(v) else None


def field_list(run_labels=None, *, unit=None, extra=()):
    """The Frictionless fields of a diagnostic table. `run_labels` {run id: label} (the template's), `unit` for a table whose
    numbers all share one (the camera's ms), `extra` more (name, type) columns."""
    out = []
    for name, kind in [*COLUMNS, *extra]:
        f = {"name": name, "type": kind}
        if name == "verdict":
            f.update({"display": "status", "labels": {"not_run": "not run"}})
        elif name == "evidence":
            f["display"] = "link"
        elif name == "run" and run_labels:
            f["labels"] = dict(run_labels)
        elif name in ("t", "t0", "t1"):
            f["unit"] = "s"
        elif unit and name in NUMBER_UNITS:
            f["unit"] = unit
        out.append(f)
    return out


def write_table(path, title, source, fields, rows):
    """{title, source, schema, rows}, one row per line: a regenerated file diffs row by row; allow_nan=False so a NaN stops the build."""
    one = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False)  # noqa: E731
    head = one({"title": title, "source": source, "schema": {"fields": fields}})
    pathlib.Path(path).write_text(head[:-1] + ',"rows":[\n' + ",\n".join(one(r) for r in rows) + "\n]}\n", encoding="utf-8")


def read_table(path):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return doc["rows"], doc


def run_labels(runs_doc):
    """{run id: the run's label} for the runs the template's runs.json holds: the `run` field's labels, else each row's `label`."""
    rows = runs_doc["rows"]
    field = next((f for f in runs_doc["schema"]["fields"] if f["name"] == "run"), {})
    labels = field.get("labels") or {r["run"]: r["label"] for r in rows}
    return {r["run"]: labels[r["run"]] for r in rows}


# ------------------------------------------------------------------------------------------------- evidence links
def _fragment(t0, t1):
    return f"t={t0:.3f}&tr={t0:.3f},{t1:.3f}"


def link_run(run, t0, t1):
    """servo, driver, camera and arm: the rail picks `run` on the default `runs` dataset."""
    return f"index.html?run={urllib.parse.quote(run, safe='/~')}#{_fragment(t0, t1)}"


def link_single(run, t0, t1):
    """arm-gripper: one run, no run pick."""
    return f"index.html#{_fragment(t0, t1)}"


def link_select(run, t0, t1):
    """deployments: a selection on the Runs table."""
    return f"index.html#s.runs=run:{urllib.parse.quote(run, safe='~')}&{_fragment(t0, t1)}"


def window3(t0, t1, span=None):
    """(t0, t1) rounded to the 3 decimals a link writes and kept inside the run's span (its first and last t): the start
    rounds up and the end down at the span's edges, so the link never asks for a time the clock does not have."""
    a, b = round(float(t0), 3), round(float(t1), 3)
    if span is not None:
        lo, hi = math.ceil(span[0] * 1000 - 1e-6) / 1000, math.floor(span[1] * 1000 + 1e-6) / 1000
        a, b = min(max(a, lo), hi), min(max(b, lo), hi)
    return (a, b) if b >= a else (a, a)


# ------------------------------------------------------------------------------------------------- the diagnostic row
def row(res, *, id, subject, device, title, hint, basis, order=None, run=None, started=None, window=None, link=None, t=None, message=None,
        why=None, record=None, parent=None, source=None, extra=None):
    """One RobotDx Result as §10's diagnostic row. `window` (t0, t1) already through window3, or None: then no evidence link and
    no t0 / t1. `basis`: data-ui's (derived for anything computed from real data, stand-in for stand-in data); RobotDx's
    own "computed" is not one of data-ui's. `t`: the evaluation time (default the window's end)."""
    limits = res.limits
    t0, t1 = window if window else (None, None)
    better = res.better or None
    out = {
        "id": id, "subject": subject, "device": device, "diagnostic": res.diagnostic, "title": title, "verdict": res.verdict, "rank": RANK[res.verdict],
        "value": num(res.value), "unit": res.unit or None, "warn_lo": num(limits.warn_low), "warn_hi": num(limits.warn_high),
        "error_lo": num(limits.error_low), "error_hi": num(limits.error_high), "target": num(res.target), "better": better,
        "t": num(t if t is not None else t1, 4), "t0": t0, "t1": t1, "run": run, "started": started,
        "message": message if message is not None else res.message, "why": (why if why is not None else res.why) or None,
        "evidence": link(run, t0, t1) if (window and link and run) else None, "basis": basis,
        "source": source or f"{LIBRARY} · {res.diagnostic}", "sourceUrl": None, "record": record, "parent": parent, "hint": hint,
        "order": ORDER[title] if order is None else order,
    }
    if extra:
        out.update(extra)
    return out


def custom(config, *, diagnostic, subject, value, unit, metric, limits, title, message, why="", **rest):
    """A check RobotDx has no stock function for, built the way its stock ones are: `result` judges the value against the
    limits (judge: no value is not_run, no limits is a pass), the diagnostic's name rides on the Result."""
    res = make_result(config, value=value, unit=unit, metric=metric, limits=limits, title=title, message=message, why=why or "", **rest)
    return dataclasses.replace(res, diagnostic=diagnostic, subject=subject)


def not_run(config, *, diagnostic, subject, title, message, unit="", code="NoData"):
    return dataclasses.replace(make_result(config, value=None, unit=unit, metric="value", limits=Limits(), title=title, message=message, code=code),
                               diagnostic=diagnostic, subject=subject)


def two_sided(res, config):
    """stock.box headlines one statistic and judges min and max each against its own limits; the row shows one number against
    limits that are the whole story. So the value is the statistic nearer its tighter bound (the one that decided, when
    one did) and the limits are min's lower pair with max's upper pair."""
    if res.value is None:
        return res
    stats = {res.metric: res.value, **{m.key: m.value for m in res.measurements if m.key in ("min", "max", "mean", "std")}}
    lo, hi = config.min, config.max
    upper = [b for b in (hi.warn_high, hi.error_high) if b is not None]
    lower = [b for b in (lo.warn_low, lo.error_low) if b is not None]
    margin_hi = min(upper) - stats["max"] if upper and "max" in stats else math.inf
    margin_lo = stats["min"] - max(lower) if lower and "min" in stats else math.inf
    pick = res.metric if margin_hi == margin_lo == math.inf else ("max" if margin_hi <= margin_lo else "min")
    limits = Limits(error_low=lo.error_low, warn_low=lo.warn_low, warn_high=hi.warn_high, error_high=hi.error_high)
    better, target = direction(limits)
    return dataclasses.replace(res, value=stats[pick], metric=pick, limits=limits, better=better, target=target)


def traj(t, q, *, run="", **columns):
    """A RobotDx Trajectory on t (s from the run's start, rising) and q (rad); `columns` named as the library names them."""
    return Trajectory(t=np.asarray(t, float), q_rad=np.asarray(q, float), run=run, **{k: np.asarray(v, float) for k, v in columns.items()})


def windowed(name, config, trajectory, *, subject, window_s=WINDOW_S, step_s=STEP_S):
    """RobotDx's stream.monitor on a run: [(window end in s from the run's start, Result)] over timed windows
    [end - window_s, end) stepping by step_s. wall_start=0 makes each Result's stamp the window's end."""
    return [(res.stamp, res) for res, _record in monitor(name, config, trajectory, subject=subject, window_s=window_s, step_s=step_s, wall_start=0.0)]


def each_window(trajectory, evaluator, *, window_s=WINDOW_S, step_s=STEP_S):
    """[(window end in s from the run's start, evaluator(window))] for a check stream.monitor cannot call by name (the sample rate
    reads Stamps, not a Trajectory): the same timed windows, the same slicing."""
    return [(w.labels["window_end_s"], evaluator(w)) for w in time_windows(trajectory, window_s, step_s)]


# ------------------------------------------------------------------------------------------------- the rack
def four_digits(v):
    """4 significant digits, as sim2real's devices.json writes a station's window and ceiling (so both apps show one number)."""
    return float(f"{v:.4g}")


def shown(path) -> str:
    """A path as a published file may name it: the home folder as ~ (tests/unit/no-home-paths.test.mjs: nothing the site
    publishes carries a home path)."""

    text, home = str(path), str(pathlib.Path.home())
    return "~" + text[len(home):] if text.startswith(home) else text


def tape_stations(record=RECORD):
    """bam_rack_twin's own tape parameter block (hardware/tape.py TAPE_STATIONS), read as data, never executed or hard-coded:
    {can_id: {"speed_ceiling_deg_s": float, "q_window_deg": [lo, hi] | None, "frame": "output" | "rotor"}}, the envelope's speed
    ceiling and board-frame window in degrees."""
    tape = pathlib.Path(record).parents[2] / "bam_rack_twin" / "hardware" / "tape.py"
    tree = ast.parse(tape.read_text(encoding="utf-8"))
    block = next(n.value for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "TAPE_STATIONS")
    out = {}
    for can, spec in ast.literal_eval(block).items():
        env = spec["envelope"]
        window = env.get("absolute_rad")
        out[int(can)] = {"speed_ceiling_deg_s": four_digits(math.degrees(env["speed_ceiling_rad_s"])),
                         "q_window_deg": [four_digits(math.degrees(x)) for x in window] if window else None, "frame": spec.get("frame")}
    return out


def newest_acceptance(stations_needed=8):
    """(path, document) of the newest bam_rack_twin acceptance file (schema bam_rack_twin.acceptance/1, by its generated_at) that holds
    `stations_needed` stations, across rack_2026-10-2*/analysis/acceptance*.json. The acceptance_extra_* files are another shape
    (no schema, no generated_at) and are not candidates."""
    best = None
    for path in sorted(RACK.glob("rack_2026-10-2*/analysis/acceptance*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema") != "bam_rack_twin.acceptance/1" or not doc.get("generated_at") or len(doc.get("stations") or {}) < stations_needed:
            continue
        if best is None or doc["generated_at"] > best[1]["generated_at"]:
            best = (path, doc)
    return best


def floor_mrad(acceptance_doc, can):
    """The station's T1 floor (mrad) in an acceptance document."""
    gate = next(g for g in acceptance_doc["stations"][str(can)]["gates"] if g["id"] == "T1")
    return float(gate["value"])


def started_unix(started):
    return datetime.datetime.fromisoformat(started).timestamp()


def span_of(t):
    """The first and last of a run's displayed t, as the template's samples write them (4 decimals)."""
    return round(float(t[0]), 4), round(float(t[-1]), 4)


def fault_window(t, fault, mode, span, pad=0.25):
    """The evidence window of a fault check: from the first row a limiter or fault was reported (fault register non-zero, or mode
    fault / timeout) to the last, padded; the run's span when the register stayed 0."""
    hit = (np.asarray(fault) != 0) | np.isin(np.asarray(mode), (1, 11))
    if not hit.any():
        return window3(span[0], span[1], span)
    return window3(t[hit][0] - pad, t[hit][-1] + pad, span)


def align_start(t_raw, duration):
    """The index of the raw log's row where the template's t = 0 sits. The template drops a runner's prelude on some runs, and
    its duration_s is last row - first kept row, so the first kept row is the one whose distance to the last matches it."""
    k = int(np.argmin(np.abs((t_raw[-1] - t_raw) - duration)))
    if abs((t_raw[-1] - t_raw[k]) - duration) > 6e-4:
        raise ValueError(f"no raw row {duration} s before the last (nearest: {t_raw[-1] - t_raw[k]})")
    return k
