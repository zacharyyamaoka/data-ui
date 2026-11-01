"""The BLDC driver template's own checks, run by tests/browser/checks.py on the built site (PEP 0010 §6; the trajectory
contract's §6: "each template's checks.py checks the sidecar's units against §3"). The full measurement (i_q against
the archive's npz, the state strips against events.json, the coverage against numpy, both themes and widths) is
tests/browser/p4_checks.py; here, what the gallery suite asks of every case:

  - units: every driver channel in samples.json and coverage_samples.csv has channels.json's unit (qd_deg_s, a servo
    channel the operating map reads, keeps its own), and every column the contract names keeps the contract's unit;
  - the page: the dashboard draws its panels, and its clock spans the newest run's samples (samples.json's min..max t).
Oracles from the case's files, never from the page's model."""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[1] / "robotics" / "schemas"
TABLES = {"runs": "runs.json", "samples": "samples.json", "events": "events.json", "devices": "devices.json", "coverage_samples": "coverage_samples.schema.json"}
KEYS = ["playback", "iq", "id", "vbus", "temp", "mode", "fault", "iq-coverage", "operating-map", "temp-by-kind"]


def doc(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def unit_problems():
    """Each column whose unit is not the contract's or channels.json's, as text."""
    types = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]
    known = {name: unit for chans in types.values() for name, unit in chans.items()}
    bad = []
    for table, name in TABLES.items():
        want = {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
        for f in doc(name)["schema"]["fields"]:
            if f["name"] in want and f.get("unit") != want[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, the contract's {want[f['name']]!r}")
            if table in ("samples", "coverage_samples") and f["name"] in known and f.get("unit") != known[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, channels.json's {known[f['name']]!r}")
    if not {f["name"] for f in doc("samples.json")["schema"]["fields"]} >= {"i_q_a", "i_d_a", "v_bus_v", "temp_c", "mode", "fault"}:
        bad.append("samples.json lacks a driver channel")
    return bad


def run(ctx, path):
    bad = unit_problems()
    ctx.check("robotics-driver: every column's unit is the contract's, every channel channels.json's", not bad, bad[:3] or None)
    runs, samples = doc("runs.json")["rows"], doc("samples.json")["rows"]
    newest = max(runs, key=lambda r: r["started"])["run"]
    ts = [r["t"] for r in samples if r["run"] == newest]
    page = ctx.page(path, width=1280, height=1000)
    drawn = ctx.until(page, """(keys) => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
      return keys.every((k) => { const p = d.querySelector(`.dd-panel[data-panel='${k}'] data-views`); return p && p.dataset.view; }); }""", KEYS)
    got = page.evaluate("() => { const c = document.querySelector('#example').clock; return [c.start, c.end]; }")
    ctx.check(f"robotics-driver: the dashboard draws its panels and its clock spans the newest run ({newest}) {[min(ts), max(ts)]}",
              drawn and got == [min(ts), max(ts)], {"clock": got})
    page.context.close()
