"""The Servo template's own checks, run by tests/browser/checks.py on the built site (PEP 0010 §6; the trajectory
contract's §6: "each template's checks.py checks the sidecar's units against §3"). The full measurement of every panel,
the run picks and the use-case group is tests/browser/p1c_checks.py; here, what the gallery suite asks of every case:

  - units: every channel in samples.json is a servo channel of gallery/robotics/schemas/channels.json with that unit,
    and every column the contract names keeps the contract's unit (runs, samples, devices);
  - the page: the dashboard draws its panels and its clock spans the newest run's samples (samples.json's min..max t).
Oracles from the case's files, never from the page's model."""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[1] / "robotics" / "schemas"
TABLES = ("runs", "samples", "devices")
KEYS = ["runs", "playback", "angle", "velocity", "torque"]


def doc(name):
    return json.loads((HERE / f"{name}.json").read_text(encoding="utf-8"))


def unit_problems():
    """Each column whose unit is not the contract's or its device type's (channels.json), as text."""
    channels = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]["servo"]
    bad = []
    for table in TABLES:
        want = {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
        for f in doc(table)["schema"]["fields"]:
            if f["name"] in want and f.get("unit") != want[f["name"]]:
                bad.append(f"{table}.{f['name']}: {f.get('unit')!r}, the contract's {want[f['name']]!r}")
    for f in doc("samples")["schema"]["fields"]:
        if f["name"] not in ("t", "run", "situation", "source", "device") and channels.get(f["name"], "?") != f.get("unit"):
            bad.append(f"samples.{f['name']}: {f.get('unit')!r}, a servo channel's {channels.get(f['name'], 'not a servo channel')!r}")
    return bad


def run(ctx, path):
    bad = unit_problems()
    ctx.check("robotics-servo: every column's unit is the contract's, every channel a servo channel's (channels.json)", not bad, bad[:3] or None)
    runs, samples = doc("runs")["rows"], doc("samples")["rows"]
    newest = max(runs, key=lambda r: r["started"])["run"]
    ts = [r["t"] for r in samples if r["run"] == newest]
    page = ctx.page(path, width=1280, height=1000)
    drawn = ctx.until(page, """(keys) => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
      return keys.every((k) => { const p = d.querySelector(`.dd-panel[data-panel='${k}'] data-views`); return p && p.dataset.view; }); }""", KEYS)
    got = page.evaluate("() => { const c = document.querySelector('#example').clock; return [c.start, c.end]; }")
    ctx.check(f"robotics-servo: the dashboard draws its panels and its clock spans the newest run ({newest}) {[min(ts), max(ts)]}",
              drawn and got == [min(ts), max(ts)], {"clock": got})
    page.context.close()
