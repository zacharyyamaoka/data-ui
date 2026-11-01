"""The Camera template's own checks, run by tests/browser/checks.py on the built site (PEP 0010 §6; the trajectory
contract's §6). The full measurement (the frame-interval histogram and the dropped frames against numpy over the
archive's hw_ms, the clip within one frame, both themes and widths) is tests/browser/p4_checks.py; here:

  - units: frame_dt_ms is ms (channels.json's camera channel), media.json's and runs.json's columns keep the contract's;
  - honest media: every rgb clip is real-camera, and no depth or band row pretends to exist;
  - the page: the dashboard draws its panels, the clock spans the newest session's stamps, the RGB card plays its clip.
Oracles from the case's files, never from the page's model."""

import csv
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[1] / "robotics" / "schemas"
TABLES = {"runs": "runs.json", "samples": "samples.schema.json", "media": "media.json", "devices": "devices.json"}
KEYS = ["playback", "rgb", "depth", "band", "interval-hist", "dropped"]


def doc(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def unit_problems():
    channels = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]["camera"]
    bad = []
    for table, name in TABLES.items():
        want = {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{table}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
        for f in doc(name)["schema"]["fields"]:
            if f["name"] in want and f.get("unit") != want[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, the contract's {want[f['name']]!r}")
            if table == "samples" and f["name"] in channels and f.get("unit") != channels[f["name"]]:
                bad.append(f"{name} {f['name']}: {f.get('unit')!r}, channels.json's {channels[f['name']]!r}")
    return bad


def run(ctx, path):
    bad = unit_problems()
    ctx.check("robotics-camera: every column's unit is the contract's, frame_dt_ms channels.json's", not bad, bad[:3] or None)
    media = doc("media.json")["rows"]
    ctx.check("robotics-camera: every rgb clip is real-camera and there is no depth or band row (none captured yet)",
              media and all(m["basis"] == "real-camera" and m["kind"] == "rgb" for m in media), [(m["kind"], m["basis"]) for m in media])
    runs = doc("runs.json")["rows"]
    newest = max(runs, key=lambda r: r["started"])["run"]
    with open(HERE / "samples.csv", newline="", encoding="utf-8") as fh:
        ts = [float(r["t"]) for r in csv.DictReader(fh) if r["run"] == newest]
    clip = next(m for m in media if m["run"] == newest)
    page = ctx.page(path, width=1280, height=1000)
    drawn = ctx.until(page, """(keys) => { const d = document.querySelector('#example'); if (!d || !d.dash) return false;
      return keys.every((k) => { const p = d.querySelector(`.dd-panel[data-panel='${k}'] data-views`); return p && p.dataset.view; }); }""", KEYS)
    page.locator("#example .dd-panel[data-panel='rgb']").scroll_into_view_if_needed()
    ctx.until(page, "(s) => { const v = document.querySelector(\"#example .dd-panel[data-panel='rgb'] video[data-t0]\"); return !!v && (v.dataset.src || '').endsWith(s); }", clip["src"])
    got = page.evaluate("""() => { const c = document.querySelector('#example').clock; const v = document.querySelector("#example .dd-panel[data-panel='rgb'] video[data-t0]");
      return { span: [c.start, c.end], src: v ? v.dataset.src : null }; }""")
    ctx.check(f"robotics-camera: the dashboard draws its panels, its clock spans the newest session's stamps ({newest}) and the RGB card plays its clip",
              drawn and got["span"] == [min(ts), max(ts)] and (got["src"] or "").endswith(clip["src"]), got)
    page.context.close()
