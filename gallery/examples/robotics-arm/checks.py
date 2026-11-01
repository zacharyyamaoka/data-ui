"""The Robot arm template's own checks, run by tests/browser/checks.py on the built site (PEP 0010 §6; the trajectory
contract's §6: "each template's checks.py checks the sidecar's units against §3"). The full measurement of every panel,
the run picks and the use-case group is tests/browser/p1c_checks.py; here, what the gallery suite asks of every case:

  - units: every channel in samples.json is a servo channel of gallery/robotics/schemas/channels.json with that unit,
    every column the contract names keeps the contract's unit (runs, poses, samples, links, devices), and every link
    position is in the scene's unit (mm);
  - the page: the dashboard draws its panels, says it is a stand-in, and its clock spans the newest run's poses.
Oracles from the case's files, never from the page's model."""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[1] / "robotics" / "schemas"
TABLES = ("runs", "poses", "samples", "links", "devices")
KEYS = ["runs", "playback", "path-3d", "path-top", "joint-angle"]


def doc(name):
    return json.loads((HERE / f"{name}.json").read_text(encoding="utf-8"))


def unit_problems():
    """Each column whose unit is not the contract's, its device type's (channels.json) or the scene's, as text."""
    channels = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]["servo"]
    bad = []
    for table in TABLES:
        want = {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
        for f in doc(table)["schema"]["fields"]:
            name, unit = f["name"], f.get("unit")
            if name in want:
                if unit != want[name]:
                    bad.append(f"{table}.{name}: {unit!r}, the contract's {want[name]!r}")
            elif table == "links" and name[-2:] in ("_x", "_y", "_z") and unit != "mm":
                bad.append(f"links.{name}: {unit!r}, the scene's unit 'mm'")
            elif table == "links" and name[-3:] in ("_qw", "_qx", "_qy", "_qz") and unit is not None:
                bad.append(f"links.{name}: {unit!r}, a quaternion part has none")
    for f in doc("samples")["schema"]["fields"]:
        if f["name"] not in ("t", "run", "situation", "source", "device") and channels.get(f["name"], "?") != f.get("unit"):
            bad.append(f"samples.{f['name']}: {f.get('unit')!r}, a servo channel's {channels.get(f['name'], 'not a servo channel')!r}")
    return bad


def run(ctx, path):
    bad = unit_problems()
    ctx.check("robotics-arm: every column's unit is the contract's, every channel a servo channel's, every link position in mm", not bad, bad[:3] or None)
    runs, poses = doc("runs")["rows"], doc("poses")["rows"]
    newest = max(runs, key=lambda r: r["started"])["run"]
    ts = [r["t"] for r in poses if r["run"] == newest]
    page = ctx.page(path, width=1280, height=1000)
    drawn = ctx.until(page, """(keys) => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
      return keys.every((k) => { const p = d.querySelector(`.dd-panel[data-panel='${k}'] data-views`); return p && p.dataset.view; }); }""", KEYS)
    got = page.evaluate("() => { const d = document.querySelector('#example'); return { span: [d.clock.start, d.clock.end], text: d.textContent }; }")
    ctx.check(f"robotics-arm: the dashboard draws its panels, says stand-in, and its clock spans the newest run ({newest}) {[min(ts), max(ts)]}",
              drawn and "stand-in" in got["text"].lower() and got["span"] == [min(ts), max(ts)], {"clock": got["span"]})
    page.context.close()
