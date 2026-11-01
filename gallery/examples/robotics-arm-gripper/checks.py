"""The Arm + gripper template's own checks, run by tests/browser/checks.py on the built site (PEP 0010 §6; the trajectory
contract's §6). The full measurement (the event marks within one frame, every panel against its file, the 3D path, both
themes and widths) is tests/browser/p4_checks.py; here:

  - units: width_mm and force_n are channels.json's gripper channels, poses' columns keep the contract's units;
  - the marks: each time series reads its annotations from the events dataset, which is events.json (CONTRACT §25:
    annotations from data, kit gap 2), so a mark is an events.json row and nothing is written twice; p4_checks.py and
    kit_gaps_checks.py measure the drawn marks against events.json;
  - the page: the dashboard draws its panels and its clock spans the run's poses.
Oracles from the case's files, never from the page's model."""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[1] / "robotics" / "schemas"
ROOT = HERE.parents[2]
TABLES = {"runs": "runs.json", "samples": "samples.json", "poses": "poses.json", "events": "events.json", "devices": "devices.json", "coverage_samples": "coverage_samples.json"}
KEYS = ["playback", "eef", "width", "width-at-grasp", "force", "path-3d"]


def doc(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def unit_problems():
    channels = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]["gripper"]
    bad = []
    for table, name in TABLES.items():
        want = {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
        for f in doc(name)["schema"]["fields"]:
            if f["name"] in want and f.get("unit") != want[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, the contract's {want[f['name']]!r}")
            if f["name"] in channels and f.get("unit") != channels[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, channels.json's {channels[f['name']]!r}")
    return bad


def marks_problems():
    """Each time series' annotations read events.json's rows (data: the events dataset, x: t, label: label), and
    nothing writes a mark by hand; every events.json row has a time and a label."""
    sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
    import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js
    base = data_ui_base.loads((HERE / "views.base").read_text(encoding="utf-8"))
    events = (base.get("datasets") or {}).get("events")
    events = events.get("data") if isinstance(events, dict) else events
    bad = [] if events == "events.json" else [{"events dataset": events, "want": "events.json"}]
    bad += [{"row": e} for e in doc("events.json")["rows"] if not isinstance(e.get("t"), (int, float)) or not e.get("label")]
    for v in base.get("views", []):
        if v.get("type") == "timeseries":
            got = (v.get("timeseries") or {}).get("annotations") or []
            if got != [{"data": "events", "x": "t", "label": "label"}]:
                bad.append({"view": v.get("name"), "annotations": got})
    return bad


def run(ctx, path):
    bad = unit_problems()
    ctx.check("robotics-arm-gripper: every column's unit is the contract's, the gripper's channels channels.json's", not bad, bad[:3] or None)
    try:
        marks = marks_problems()
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        marks = [f"{type(e).__name__}: {e}"]
    ctx.check("robotics-arm-gripper: every time series reads its contact, grasp and release marks from events.json (annotations from data)", not marks, marks[:2] or None)
    poses = doc("poses.json")["rows"]
    run_id = doc("runs.json")["rows"][0]["run"]
    ts = [r["t"] for r in poses if r["run"] == run_id]
    page = ctx.page(path, width=1280, height=1000)
    drawn = ctx.until(page, """(keys) => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
      return keys.every((k) => { const p = d.querySelector(`.dd-panel[data-panel='${k}'] data-views`); return p && p.dataset.view; }); }""", KEYS)
    got = page.evaluate("() => { const c = document.querySelector('#example').clock; return [c.start, c.end]; }")
    ctx.check(f"robotics-arm-gripper: the dashboard draws its panels and its clock spans the run's poses {[min(ts), max(ts)]}",
              drawn and got == [min(ts), max(ts)], {"clock": got})
    page.context.close()
