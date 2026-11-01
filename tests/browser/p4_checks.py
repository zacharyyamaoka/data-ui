"""PEP 0010 P4 (docs/peps/0010-robotics-playback.md §6, §11 P4): the stock dashboards for the remaining part types,
gallery/examples/robotics-driver (BLDC driver), robotics-camera (Camera) and robotics-arm-gripper (Arm + gripper),
measured in headless Chromium on the built site. Written red, before the cases; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/p4_checks.py [OUT_DIR]     # after npm run build

What each case is, for these checks (PEP 0010 §6, the mocks reports/media/robotics-plan/{bldc-driver,camera,arm-gripper}.png):
one <data-dashboard> (the case page's #example) over the trajectory contract's tables (gallery/robotics/CONTRACT.md).
  driver      runs.json (rail: run as select, newest first and picked; device; kind), samples.json (real rows of the
              boards' driver channels), events.json (mode and fault-register changes), coverage_samples.csv + its
              .schema.json (every run of each board, w-weighted), devices.json. Panels: playback; iq, id, vbus, temp
              (timeseries of i_q_a, i_d_a, v_bus_v, temp_c); mode, fault (state strips: one rect per span of one state,
              datum {t, t_end, mode|fault}); iq-coverage (histogram, sum w), operating-map (2D bins qd_deg_s × i_q_a,
              sum w), temp-by-kind (box plot, extent min-max) over the picked run's board.
  camera      runs.json (rail: run = a recording session, as select, newest picked), media.json (rgb clips),
              samples.csv + samples.schema.json (every frame interval, frame_dt_ms), coverage = the same stamps, its
              rail's Camera (device, as select). Panels: playback; rgb (video.primary), depth, band (empty: none
              captured); interval-hist (histogram of frame_dt_ms), dropped (intervals over 50 ms per session).
  arm-gripper runs.json, poses.json (rail: situation), samples.json (the gripper: width_mm, force_n, grip), events.json
              (contact, grasp, release), coverage_samples.json (grasps), devices.json. Panels: playback; eef (z_mm),
              width, force (timeseries with each event as a mark); width-at-grasp (histogram, sum w); path-3d
              (trajectory3d of the tool path).
Every expected number is computed here, outside the page, with numpy: from the archive's own files where the case is
real (the rack's run npz for i_q and the driver channels, its mode and fault changes and its temperatures; the cameras'
cam_<serial>.npz hw_ms for the frame intervals), else from the case's files ("every panel draws its file's real rows").
The page side is read from what the views drew: Vega's own datasets and scenegraph items (bin edges, sums, whiskers,
rects, rules, texts, through each view's x scale), the video element, the clock, and the 3D card's GPU-buffer hook.

  - i_q equals the npz: every drawn i_q point of a picked run is the npz's i_q at the row with that t (and i_d, v_bus,
    temp likewise), to the file's written digits; one pick per board.
  - event marks sit at their t within one frame (1/30 s): the driver's mode and fault changes start a drawn span there,
    with the event's state; the gripper's contact, grasp and release are vertical marks there, with their labels. The
    driver's events are the npz's own changes, at full rate.
  - the frame-interval histogram equals numpy over cam_*.npz hw_ms: per drawn bar, the count of np.diff(hw_ms) in its
    bin over the case's sessions of the picked camera; dropped frames per session likewise (> 50 ms).
  - every panel draws its file's real rows; the box plot's whiskers equal the full-rate npz extremes of every kept run.
  - light and dark at 1280 and 390 px: every panel draws, the real series is slot 1 of that theme, no sideways scroll.
Screenshots go to OUT_DIR (default reports/media/robotics-p4, beside the mocks of reports/media/robotics-plan).

Serves dist/site on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/p4-checks.json and exits 1 if any check
fails. A part that cannot be measured is one failing check in its own words, never a silent pass.
"""

from __future__ import annotations

import contextlib
import csv
import json
import math
import os
import pathlib
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p4"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
EX = ROOT / "gallery" / "examples"
SCHEMAS = ROOT / "gallery" / "robotics" / "schemas"
RACK = pathlib.Path(os.environ.get("RACK", "/archive/datasets/bam_rig"))
DRIVER, CAMERA, GRIPPER = "robotics-driver", "robotics-camera", "robotics-arm-gripper"
D = "#example"
WAIT = 45000                # ms: a ceiling for a state to arrive on a loaded machine, not a pause
FRAME = 1.0 / 30            # one frame of the rack's cameras (30 fps nominal): "within one frame"
BUDGET = 5 * 1024 * 1024    # bytes a case publishes (every file but source/): "a few MB at most"
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:500]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A part that cannot run (a case missing, the archive absent, nothing drawn) is one failing check in its own words."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:400]}")


# ------------------------------------------------------------------------------------------------- the files
def doc(case, name):
    return json.loads((EX / case / name).read_text(encoding="utf-8"))


def rows(case, name):
    d = doc(case, name)
    return d["rows"] if isinstance(d, dict) else d


def fields(case, name):
    return {f["name"]: f for f in doc(case, name)["schema"]["fields"]}


def csv_rows(case, name):
    """A CSV table read with its <name>.schema.json sidecar's types (numbers as floats, empty as None)."""
    side = json.loads((EX / case / name.replace(".csv", ".schema.json")).read_text(encoding="utf-8"))
    types = {f["name"]: f.get("type") for f in side["schema"]["fields"]}
    out = []
    with open(EX / case / name, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append({k: (None if v == "" else float(v) if types.get(k) in ("number", "integer") else v) for k, v in r.items()})
    return out, side


def published_bytes(case):
    total = 0
    for p in (EX / case).rglob("*"):
        rel = p.relative_to(EX / case)
        if p.is_file() and rel.parts[0] != "source" and not rel.parts[0].startswith("."):
            total += p.stat().st_size
    return total


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def same32(got, want):
    return got is not None and want is not None and abs(got - f32(want)) <= abs(f32(want)) * 2 ** -23 + 1e-9


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def newest(runs):
    return max(runs, key=lambda r: r["started"])["run"]


def span_of(rs, run, key="run"):
    ts = [r["t"] for r in rs if r[key] == run and num(r.get("t"))]
    return [min(ts), max(ts)] if ts else None


# ------------------------------------------------------------------------------------------------- page helpers
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/index.html", timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
PANEL = "(k) => document.querySelector(`#example .dd-panel[data-panel='${k}']`)"
VEGA = f"(k) => {{ const p = ({PANEL})(k); const plot = p && p.querySelector('.dv-chart-plot, .dv-timeseries-plot'); return plot && plot.parentElement.vegaView ? plot.parentElement.vegaView : null; }}"
HOOK = f"(k) => {{ const p = ({PANEL})(k); const r = p && p.querySelector('.dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }}"
# every panel of the dashboard has drawn once, every rail painted, every Vega view embedded, every 3D card rendered
READY = f"""(keys) => {{
  const d = document.querySelector('#example'); if (!d || !d.dash) return false;
  const secs = keys.map((k) => ({PANEL})(k)); if (secs.some((s) => !s)) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; if (!els.length || !els.every((e) => e.dataset.view)) return false;
  if (![...d.querySelectorAll('.dd-rail data-facets')].every((f) => f.querySelector('details'))) return false;
  for (const s of secs) {{ const r = s.querySelector('.dv-scene3d'); if (r && !(r.scene3d && r.scene3d.renders() > 0)) return false;
    const v = s.querySelector('.dv-chart-plot, .dv-timeseries-plot'); if (v && !v.parentElement.vegaView) return false; }}
  return true; }}"""
# a timeseries panel's drawn points, from Vega's own dataset: {series: [[x, value]…]}
POINTS = f"""(k) => {{ const v = ({VEGA})(k); if (!v) return null; const out = {{}};
  for (const d of v.data('series')) (out[d.series] = out[d.series] || []).push([d.x, d.value]); return out; }}"""
# a Vega view's mark items: [{type, name, x, x2, y, y2, width, height, text, fill, stroke, datum}] for marks of role
# `mark` (the data marks, never axes, grids or legends), and the x scale's image of `ts`
ITEMS = f"""([k, ts]) => {{ const v = ({VEGA})(k); if (!v) return null; const out = [];
  const walk = (n) => {{ if (!n) return; if (n.marktype && n.role === 'mark') for (const i of n.items || []) out.push({{ type: n.marktype, name: n.name || null,
    x: i.x ?? null, x2: i.x2 ?? null, y: i.y ?? null, y2: i.y2 ?? null, width: i.width ?? null, height: i.height ?? null, text: i.text ?? null,
    fill: i.fill ?? null, stroke: i.stroke ?? null, opacity: i.opacity ?? null, datum: i.datum && typeof i.datum === 'object' ? JSON.parse(JSON.stringify(i.datum)) : null }});
    for (const i of n.items || []) if (i.items) walk(i); }};
  walk(v.scenegraph().root); let at = null; try {{ const s = v.scale('x'); at = (ts || []).map((t) => s(t)); }} catch (e) {{ at = null; }}
  // Vega-Lite's bins signals (<bin key>_bins): Vega's bin() result, a function carrying start, stop and step
  const bins = {{}}; const grab = (st) => {{ if (!st) return; for (const [k, b] of Object.entries(st.signals || {{}})) if (/_bins$/.test(k) && b && (typeof b === 'object' || typeof b === 'function') && Number.isFinite(b.step)) bins[k] = {{ start: b.start, stop: b.stop, step: b.step }};
    for (const c of st.subcontext || []) grab(c); }};
  try {{ grab(v.getState({{ signals: (n) => /_bins$/.test(n), data: () => false, recurse: true }})); }} catch (e) {{ /* no bins */ }}
  return {{ items: out, at, bins }}; }}"""
CLOCK = """() => { const d = document.querySelector('#example'); const c = d.clock; const pb = d.querySelector('.dd-panel[data-type="playback"]');
  return { start: c.start, end: c.end, t: c.t, readout: pb ? (pb.querySelector('.dv-pb-end') || {}).textContent || null : null }; }"""


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def open_case(browser, base, case, keys, *, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(f"{base}/gallery/{case}/index.html")
    # WHY scroll each panel in: a 3D card starts WebGL, and a video loads, only near the viewport
    with contextlib.suppress(Exception):
        page.wait_for_selector(f"{D} .dd-panel[data-panel]", timeout=WAIT)
        for k in keys:
            page.locator(f"{D} .dd-panel[data-panel='{k}']").scroll_into_view_if_needed(timeout=5000)
    ok = True
    try:
        page.wait_for_function(READY, arg=keys, timeout=WAIT)
    except Exception:  # noqa: BLE001 -- the check that reads the state says so
        ok = False
    settle(page, 3)
    return page, ok


def items(page, key, ts=None):
    return page.evaluate(ITEMS, [key, list(ts or [])]) or {"items": [], "at": None}


def points(page, key):
    return {s: [tuple(p) for p in pts] for s, pts in (page.evaluate(POINTS, key) or {}).items()}


def rail_radio(dataset, key, value):
    return f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']"


def checked(page, dataset, key):
    return page.evaluate("([s]) => { const i = document.querySelector(s); return i ? i.dataset.value : null; }",
                         [f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]:checked"])


def pick(page, dataset, key, value):
    """A rail radio, as a reader picks it ("Show N more" first when the value sits past the first ones)."""
    radio = page.locator(rail_radio(dataset, key, value))
    if not radio.count():
        more = page.locator(f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] [data-more]")
        if more.count():
            more.first.click()
            settle(page)
    radio = page.locator(rail_radio(dataset, key, value))
    radio.scroll_into_view_if_needed()
    radio.check()
    page.wait_for_function("([ds, v]) => { const d = document.querySelector('#example'); return JSON.stringify(d.state.rail[ds] || '').includes(v); }",
                           arg=[dataset, value], timeout=WAIT)
    settle(page, 4)


def until_points(page, key, counts):
    """Wait until a timeseries panel draws exactly `counts` ({series: n}) points: the panel has caught up with a pick."""
    with contextlib.suppress(Exception):
        page.wait_for_function(f"""([k, want]) => {{ const v = ({VEGA})(k); if (!v) return false; const got = {{}};
          for (const d of v.data('series')) got[d.series] = (got[d.series] || 0) + 1;
          return Object.keys(want).every((s) => got[s] === want[s]) && Object.keys(got).every((s) => s in want); }}""", arg=[key, counts], timeout=WAIT)
    settle(page, 2)


def until_rows(page, key, n):
    """Wait until a chart panel has drawn `n` rows: the chart writes data-drawn when a draw has run in Vega (its last
    step), so the items read after this are the new rows', never the last pick's."""
    with contextlib.suppress(Exception):
        page.wait_for_function(f"""([k, n]) => {{ const p = ({PANEL})(k); const plot = p && p.querySelector('.dv-chart-plot');
          return !!plot && plot.parentElement.dataset.drawn === String(n); }}""", arg=[key, n], timeout=WAIT)
    settle(page, 2)


def stable_items(page, key, ts=None, tries=40):
    """A Vega view's items once two reads 250 ms apart agree: a chart that re-embeds after a pick has finished."""
    last = None
    for _ in range(tries):
        got = items(page, key, ts)
        if got == last and got["items"]:
            return got
        last = got
        time.sleep(0.25)
    return last or {"items": [], "at": None}


def seek(page, t):
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", t)
    settle(page, 2)


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def tokens(page):
    t = page.evaluate("() => { const el = document.querySelector('#example data-views'); return el ? el.tokens() : null; }")
    hexes = lambda c: "#%02x%02x%02x" % tuple(round(float(x)) for x in re.findall(r"[\d.]+", c)[:3]) if c else None  # noqa: E731
    return {"series": [hexes(s) for s in (t or {}).get("series", [])], "muted": hexes((t or {}).get("muted"))}


def colour(c):
    """A Vega fill/stroke ('#rrggbb' or 'rgb(r, g, b)') as '#rrggbb'."""
    if not isinstance(c, str):
        return None
    if c.startswith("#"):
        return c.lower()
    nums = re.findall(r"[\d.]+", c)
    return "#%02x%02x%02x" % tuple(round(float(x)) for x in nums[:3]) if len(nums) >= 3 else c


def shot(page, name):
    try:
        page.evaluate("() => { const d = document.querySelector('#example'); if (d) window.scrollTo(0, d.getBoundingClientRect().top + window.scrollY - 60); }")
        settle(page)
        page.locator(D).screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


def compare_points(drawn, want):
    """drawn and want: {series: [(x, value)…]}. Every series, every point, exactly."""
    bad = []
    for s in sorted(set(drawn) | set(want)):
        d, w = sorted(drawn.get(s, [])), sorted(want.get(s, []))
        if len(d) != len(w):
            bad.append({"series": s, "drawn": len(d), "file": len(w)})
            continue
        off = [i for i, (a, b) in enumerate(zip(d, w)) if a[0] != b[0] or a[1] != b[1]]
        if off:
            bad.append({"series": s, "first differing point": off[0], "drawn": d[off[0]], "file": w[off[0]], "differing": len(off)})
    return bad


def series_points(rs, y, *, keep=lambda r: True, by="situation"):
    out = {}
    for r in rs:
        if keep(r) and num(r.get(y)) and num(r.get("t")):
            out.setdefault(r[by], []).append((r["t"], r[y]))
    return out


def bins_of(datum):
    """A binned mark's datum -> ({bin key: (start, end)}, value): Vega-Lite writes each bin as <key> and <key>_end, and
    the aggregate as sum_<field> or __count."""
    pairs = {k: (datum[k], datum[k + "_end"]) for k in datum if k + "_end" in datum and num(datum[k]) and num(datum[k + "_end"])}
    value = next((datum[k] for k in datum if (k.startswith("sum_") or k == "__count" or k.startswith("count")) and num(datum[k])), None)
    return pairs, value


def vega_bin(values, spec):
    """Each value's bin index as Vega's bin transform assigns it (vega-transforms Bin.js, with the start, stop and step
    of the bins signal Vega-Lite made): below start or past stop none (-1), else ⌊1e-14 + (min(v, stop − step) − start)
    / step⌋. WHY Vega's rule and not np.histogram's edges: the edges are floats (start + k·step); a value sitting on one
    must land where the drawing put it, and the counting is still numpy's."""
    v = np.asarray(values, float)
    start, stop, step = spec["start"], spec["stop"], spec["step"]
    k = np.floor(1e-14 + (np.clip(v, start, stop - step) - start) / step).astype(int)
    return np.where((v < start) | (v > stop) | ~np.isfinite(v), -1, k)


def bin_sums(values, weights, bars, spec):
    """numpy's sum of `weights` per drawn bar ([(start, end)…]) and the sum over every value inside the bins' range:
    ([sum per bar], total), or (None, None) when a value lands in a bin that is not drawn."""
    if not bars or not spec:
        return None, None
    k = vega_bin(values, spec)
    w = np.asarray(weights, float)
    idx_of = {round((lo - spec["start"]) / spec["step"]): j for j, (lo, hi) in enumerate(bars)}
    sums = [0.0] * len(bars)
    for kk, ww in zip(k[k >= 0], w[k >= 0]):
        j = idx_of.get(int(kk))
        if j is None:
            if ww:
                return None, None
            continue
        sums[j] += ww
    return sums, float(w[k >= 0].sum())


def spec_for(got, field):
    """The bins signal of a chart for one field (Vega-Lite names it <bin key>_bins, the key ending in the field)."""
    return next((b for k, b in (got.get("bins") or {}).items() if k.removesuffix("_bins").endswith(field)), None)


# ------------------------------------------------------------------------------------------------- the files' checks
def files():
    for case, tables in ((DRIVER, ("runs.json", "samples.json", "events.json", "devices.json", "coverage_samples.csv", "coverage_samples.schema.json")),
                         (CAMERA, ("runs.json", "media.json", "samples.csv", "samples.schema.json", "devices.json")),
                         (GRIPPER, ("runs.json", "poses.json", "samples.json", "events.json", "devices.json", "coverage_samples.json"))):
        here = EX / case
        readme = (here / "README.md").read_text(encoding="utf-8") if (here / "README.md").exists() else ""
        producers = sorted(p.name for p in (here / "source").glob("*.py")) if (here / "source").is_dir() else []
        missing = [f for f in ("views.base", "README.md", "checks.py", *tables) if not (here / f).exists()]
        check(f"{case}: the case's files exist (views.base, README.md, checks.py, its tables) and its producer is in source/",
              not missing and producers, {"missing": missing, "source": producers})
        check(f"{case}: its README files it under '- **Use case:** Robotics · Playback'",
              re.search(r"^- \*\*Use case:\*\* Robotics · Playback$", readme, re.M) is not None, readme[:120])
        size = published_bytes(case) if here.exists() else None
        check(f"{case}: it publishes a few MB at most (≤ 5 MB, source/ excluded)", size is not None and size <= BUDGET, {"MB": None if size is None else round(size / 1048576, 2)})
    # the units: every column the contract names keeps its unit, every channel is its device type's (channels.json)
    channels = json.loads((SCHEMAS / "channels.json").read_text(encoding="utf-8"))["types"]
    contract = {n: {f["name"]: f.get("unit") for f in json.loads((SCHEMAS / f"{n}.schema.json").read_text(encoding="utf-8"))["schema"]["fields"]}
                for n in ("runs", "samples", "events", "media", "devices", "poses", "coverage_samples")}
    for case, kind, tables in ((DRIVER, "driver", {"runs": "runs.json", "samples": "samples.json", "events": "events.json", "devices": "devices.json", "coverage_samples": "coverage_samples.schema.json"}),
                               (CAMERA, "camera", {"runs": "runs.json", "samples": "samples.schema.json", "media": "media.json", "devices": "devices.json"}),
                               (GRIPPER, "gripper", {"runs": "runs.json", "samples": "samples.json", "poses": "poses.json", "events": "events.json", "devices": "devices.json", "coverage_samples": "coverage_samples.json"})):
        with guard(f"{case}: units"):
            bad = []
            known = {}
            for chans in channels.values():
                known.update(chans)
            for table, name in tables.items():
                for f in doc(case, name)["schema"]["fields"]:
                    want = contract[table].get(f["name"], "?")
                    if want != "?" and f.get("unit") != want:
                        bad.append(f"{name} {f['name']}: {f.get('unit')!r}, the contract's {want!r}")
                    # a channel any device type names keeps that unit wherever it is written (an extra channel is allowed)
                    if table in ("samples", "coverage_samples") and f["name"] in known and f.get("unit") != known[f["name"]]:
                        bad.append(f"{name} {f['name']}: {f.get('unit')!r}, channels.json's {known[f['name']]!r}")
            own = {f["name"] for f in doc(case, tables["samples"])["schema"]["fields"]} & set(channels[kind])
            if not own:
                bad.append(f"{tables['samples']} carries none of the {kind} channels")
            check(f"{case}: every column keeps the contract's unit, every channel channels.json's, and the samples carry the {kind} channels ({', '.join(sorted(own))})", not bad, bad[:4] or None)
    # provenance, in the files
    with guard("provenance in the files"):
        runs = rows(DRIVER, "runs.json")
        check("driver: every run is real (basis) and names its npz in the archive", runs and all("real" in str(r.get("basis", "")).lower() and (RACK / r["npz"]).exists() for r in runs),
              [(r["run"], r.get("basis"), r.get("npz")) for r in runs[:2]])
        media = rows(CAMERA, "media.json")
        fake = [m for m in media if m.get("kind") in ("depth", "band") and m.get("basis") != "illustrative"]
        check("camera: every rgb clip is real-camera; a depth or band row, if any, is labelled illustrative",
              media and all(m.get("basis") == "real-camera" for m in media if m.get("kind") == "rgb") and not fake, {"rgb": [m.get("basis") for m in media if m.get("kind") == "rgb"], "unlabelled": fake[:2]})
        readme = (EX / GRIPPER / "README.md").read_text(encoding="utf-8").lower()
        g_runs = rows(GRIPPER, "runs.json")
        g_fields = fields(GRIPPER, "samples.json")
        check("arm-gripper: labelled stand-in (README, every run's basis) and the gripper's channels illustrative (README, samples' and coverage's schema)",
              "stand-in" in readme and "illustrative" in readme and g_runs and all("stand-in" in json.dumps(r).lower() for r in g_runs)
              and all("illustrative" in (g_fields[c].get("description") or "").lower() for c in ("width_mm", "force_n"))
              and all("illustrative" in (f.get("description") or "").lower() for f in doc(GRIPPER, "coverage_samples.json")["schema"]["fields"] if f["name"] in ("width_mm", "force_n")),
              [r.get("basis") for r in g_runs])


# ------------------------------------------------------------------------------------------------- the driver
DRIVER_KEYS = ["playback", "iq", "id", "vbus", "temp", "mode", "fault", "iq-coverage", "operating-map", "temp-by-kind"]
CHANNELS = {"iq": ("i_q_a", "i_q"), "id": ("i_d_a", "i_d"), "vbus": ("v_bus_v", "voltage"), "temp": ("temp_c", "temp_c")}


def npz_rows(path):
    a = np.load(path)
    t = np.asarray(a["t"], float)
    return {"t": t - t[0], **{k: np.asarray(a[k], float) for k in ("i_q", "i_d", "voltage", "temp_c", "mode", "fault", "qd")}}


def driver_runs_to_check(runs, events):
    """The newest run (the rail's default), then per board the run with the most events (its limiters and modes)."""
    out = [newest(runs)]
    by_dev = {}
    for e in events:
        by_dev.setdefault(e["device"], {}).setdefault(e["run"], 0)
        by_dev[e["device"]][e["run"]] += 1
    for dev in sorted(by_dev):
        run = max(by_dev[dev].items(), key=lambda kv: (kv[1], kv[0]))[0]
        if run not in out:
            out.append(run)
    return out


def spans_want(rs, col):
    """[(t_start, t_end, value)]: consecutive rows in one state merged, each span to the row after its last."""
    rs = sorted(rs, key=lambda r: r["t"])
    out = []
    for a, b in zip(rs, rs[1:]):
        if out and out[-1][2] == a.get(col):
            out[-1][1] = b["t"]
        else:
            out.append([a["t"], b["t"], a.get(col)])
    return [tuple(s) for s in out]


def driver(browser, base):
    runs, samples, events = rows(DRIVER, "runs.json"), rows(DRIVER, "samples.json"), rows(DRIVER, "events.json")
    cov, _ = csv_rows(DRIVER, "coverage_samples.csv")
    by_run = {r["run"]: r for r in runs}
    boards_seen = set()
    page, ok = open_case(browser, base, DRIVER, DRIVER_KEYS)
    check(f"driver: every panel of the dashboard draws ({', '.join(DRIVER_KEYS)})", ok)
    first = newest(runs)
    check("driver: the rail's Run picker opens on the newest run (runs.json's latest started)", checked(page, "runs", "run") == first,
          {"checked": checked(page, "runs", "run"), "newest": first})
    for i, run in enumerate(driver_runs_to_check(runs, events)):
        rec = by_run[run]
        dev = rec["device"]
        mine = [r for r in samples if r["run"] == run]
        if i:
            pick(page, "runs", "run", run)
        until_points(page, "iq", {s: len(v) for s, v in series_points(mine, "i_q_a").items()})
        tag = f"driver {run} ({dev})"
        # the clock spans the run
        c = page.evaluate(CLOCK)
        want = span_of(samples, run)
        check(f"{tag}: the clock spans that run's samples, min..max t {want}", want is not None and [c["start"], c["end"]] == want, {"clock": [c["start"], c["end"]]})
        # i_q (and the other channels) equal the npz, every drawn point
        a = npz_rows(RACK / rec["npz"])
        for key, (col, arr) in CHANNELS.items():
            drawn = points(page, key)
            pts = drawn.get("real", [])
            f = fields(DRIVER, "samples.json")[col]
            places = {"i_q_a": 4, "i_d_a": 4, "v_bus_v": 2, "temp_c": 2}[col]
            worst, bad, matched = 0.0, [], 0
            for x, v in pts:
                k = int(np.argmin(np.abs(a["t"] - x)))
                if abs(a["t"][k] - x) > 0.5e-4 + 1e-12:
                    bad.append({"t": x, "no npz row within 0.05 ms": float(a["t"][k])})
                    continue
                d = abs(v - a[arr][k])
                worst = max(worst, d)
                matched += 1
                if d > 0.5 * 10 ** -places + 1e-12:
                    bad.append({"t": x, "drawn": v, "npz": float(a[arr][k])})
            n_file = len([r for r in mine if num(r.get(col))])
            what = "i_q equals the npz" if key == "iq" else f"{col} equals the npz"
            check(f"{tag}: {what}: every drawn point of panel {key} is the npz's {arr} at its row ({rec['npz']}), to the file's {places} decimals; as many points as the file's rows",
                  pts and not bad and len(pts) == n_file == matched, bad[:3] or {"points": len(pts), "file rows": n_file, "worst": worst, "unit": f.get("unit")})
            # every panel draws its file's real rows (exact)
            bad2 = compare_points(drawn, series_points(mine, col))
            check(f"{tag}: panel {key} draws exactly samples.json's {col} of that run (Vega's own dataset)", drawn and not bad2, bad2[:2] or None)
        # the state strips: every span of mode and fault as the file has it, and every event where it happened
        evs = sorted((e for e in events if e["run"] == run), key=lambda e: e["t"])
        for key in ("mode", "fault"):
            until_rows(page, key, len(mine))
        for key, col in (("mode", "mode"), ("fault", "fault")):
            mine_ev = [e for e in evs if e["kind"] == col]
            got = stable_items(page, key, [e["t"] for e in mine_ev] + [e["t"] + FRAME for e in mine_ev])
            rects = [it for it in got["items"] if it["type"] == "rect" and it["datum"] and num(it["datum"].get("t")) and num(it["datum"].get("t_end"))]
            drawn = sorted((it["datum"]["t"], it["datum"]["t_end"], it["datum"].get(col)) for it in rects)
            want_spans = spans_want(mine, col)
            # a null (no fault) span is drawn under the column's empty label: any label that is not one of the file's values
            values = {v for _, _, v in want_spans if v is not None}
            same = len(drawn) == len(want_spans) and all(w[0] == d[0] and w[1] == d[1] and (w[2] == d[2] if w[2] is not None else d[2] not in values)
                                                       for w, d in zip(want_spans, drawn))
            check(f"{tag}: the {col} strip draws every span of samples.json's {col} of that run, from its first row to the row after its last",
                  rects and same, {"drawn": drawn[:4], "file": want_spans[:4], "n": [len(drawn), len(want_spans)]})
            # event marks sit at their t within one frame, with the event's state
            at = got["at"] or []
            bad = []
            for j, e in enumerate(mine_ev):
                if len(at) < 2 * len(mine_ev):
                    bad.append("no x scale")
                    break
                px, frame_px = at[j], abs(at[len(mine_ev) + j] - at[j])
                hit = [it for it in rects if abs((it["x"] or 0) - px) <= frame_px + 1e-6]
                label_ok = [it for it in hit if (it["datum"].get(col) == e["label"]) or (e["label"] == "none" and it["datum"].get(col) not in values)]
                if not label_ok:
                    bad.append({"t": e["t"], "label": e["label"], "spans within one frame": [(it["datum"]["t"], it["datum"].get(col)) for it in hit][:3]})
            check(f"{tag}: event marks sit at their t within one frame: each of the run's {len(mine_ev)} {col} events starts a drawn {col} span within 1/30 s, in its state",
                  mine_ev and not bad if col == "mode" else not bad, bad[:3] or {"events": len(mine_ev)})
        # the events are the npz's own changes, at full rate (the oracle: the archive)
        for col, arr in (("mode", "mode"), ("fault", "fault")):
            v = a[arr]
            idx = [0] + [int(i) for i in np.flatnonzero(v[1:] != v[:-1]) + 1]
            if col == "fault" and v[0] == 0:
                idx = idx[1:]
            want_t = [round(float(a["t"][i]), 4) for i in idx]
            got_t = [e["t"] for e in evs if e["kind"] == col]
            check(f"{tag}: events.json's {col} events are the npz's {arr} changes at full rate ({len(want_t)})", got_t == want_t,
                  {"events": got_t[:5], "npz": want_t[:5]})
        # coverage over the run's board: the histogram, the operating map, the box plot
        board = [r for r in cov if r["device"] == dev]
        for key in ("iq-coverage", "operating-map", "temp-by-kind"):
            until_rows(page, key, len(board))
        got = stable_items(page, "iq-coverage")
        bars = [bins_of(it["datum"]) for it in got["items"] if it["type"] == "rect" and it["datum"]]
        bars = sorted((list(p.values())[0], v) for p, v in bars if len(p) == 1 and num(v))
        vals = [(r["i_q_a"], r["w"]) for r in board if num(r["i_q_a"])]
        sums, _ = bin_sums([x for x, _ in vals], [w for _, w in vals], [b for b, _ in bars], spec_for(got, "i_q_a"))
        bad = [{"bin": b, "drawn": v, "numpy": want_v} for (b, v), want_v in zip(bars, sums or []) if want_v != v] if sums is not None else ["a value falls in an undrawn bin"]
        total = sum(v for _, v in bars)
        all_w = sum(w for _, w in vals)
        check(f"{tag}: the i_q coverage histogram's bars equal numpy's sum of w per bin over {dev}'s {len({r['run'] for r in board})} runs in coverage_samples.csv, and they hold every row",
              bars and not bad and total == all_w, bad[:3] or {"bars": len(bars), "sum w": total, "file": all_w})
        got = stable_items(page, "operating-map")
        cells = []
        for it in got["items"]:
            if it["type"] != "rect" or not it["datum"]:
                continue
            p, v = bins_of(it["datum"])
            qd = next((b for k, b in p.items() if "qd_deg_s" in k), None)
            iq = next((b for k, b in p.items() if "i_q_a" in k), None)
            if qd and iq and num(v):
                cells.append((qd, iq, v))
        bad, total = [], sum(v for _, _, v in cells)
        qspec, ispec = spec_for(got, "qd_deg_s"), spec_for(got, "i_q_a")
        if cells and qspec and ispec:
            # each axis binned as Vega bins it (its bins signals), the cells' sums counted by numpy
            pts = [(r["qd_deg_s"], r["i_q_a"], r["w"]) for r in board if num(r["qd_deg_s"]) and num(r["i_q_a"])]
            qk, ik = vega_bin([p[0] for p in pts], qspec), vega_bin([p[1] for p in pts], ispec)
            want_cells = {}
            for a_, b_, (_, _, w) in zip(qk, ik, pts):
                if a_ >= 0 and b_ >= 0:
                    want_cells[(int(a_), int(b_))] = want_cells.get((int(a_), int(b_)), 0.0) + w
            drawn_cells = {(round((q[0] - qspec["start"]) / qspec["step"]), round((i[0] - ispec["start"]) / ispec["step"])): v for q, i, v in cells}
            want_cells = {k: v for k, v in want_cells.items() if v or k in drawn_cells}
            bad = [{"cell": k, "drawn": drawn_cells.get(k), "numpy": want_cells.get(k)} for k in sorted(set(want_cells) | set(drawn_cells)) if drawn_cells.get(k) != want_cells.get(k)]
        else:
            bad = ["no cells or no bins signal"]
        all_w = sum(r["w"] for r in board if num(r["qd_deg_s"]) and num(r["i_q_a"]))
        check(f"{tag}: the operating map's cells equal numpy's 2D sum of w (qd × i_q) over {dev}'s coverage rows, and they hold every row",
              cells and not bad and total == all_w, bad[:3] or {"cells": len(cells), "sum w": total, "file": all_w})
        got = stable_items(page, "temp-by-kind")
        whiskers = {}
        for it in got["items"]:
            # a box plot's whisker ends, as Vega-Lite's boxplot mark (lower_whisker_* / upper_whisker_*) or a layered box
            # (a min-max rule: min_* / max_*) writes them in each mark's datum
            dm = it["datum"] or {}
            lo = next((dm[k] for k in dm if k.startswith("lower_whisker_") or k.startswith("min_")), None)
            hi = next((dm[k] for k in dm if k.startswith("upper_whisker_") or k.startswith("max_")), None)
            if dm.get("kind") is not None and num(lo) and num(hi):
                whiskers[dm["kind"]] = (lo, hi)
        want_w = {}
        for r in board:
            if num(r["temp_c"]):
                lo, hi = want_w.get(r["kind"], (math.inf, -math.inf))
                want_w[r["kind"]] = (min(lo, r["temp_c"]), max(hi, r["temp_c"]))
        check(f"{tag}: the box plot's whiskers are min and max of temp_c per run kind over {dev}'s coverage rows",
              whiskers and whiskers == want_w, {"drawn": whiskers, "file": want_w})
        if dev not in boards_seen:
            boards_seen.add(dev)
            with guard(f"{tag}: the box plot against the archive"):
                arch = archive_temp_extremes(dev)
                close = set(whiskers) == set(arch) and all(abs(whiskers[k][0] - arch[k][0]) <= 0.005 and abs(whiskers[k][1] - arch[k][1]) <= 0.005 for k in arch)
                check(f"{tag}: the box plot's whiskers are the full-rate npz min and max of temp_c per kind over every kept {dev} run in the archive (Oct 23-25, ≥ 20 samples), to the written 2 decimals",
                      whiskers and close, {"drawn": whiskers, "archive": arch})
    shot(page, "driver-light-1280")
    check("driver: no page error", not page.errors, page.errors[:3])
    page.context.close()


def archive_temp_extremes(device):
    """{kind: (min, max)} of temp_c over every rack run npz of the board (Oct 23-25) with at least 20 samples: the
    archive's own enumeration, independent of the producer."""
    can = int(device.split()[-1])
    out = {}
    for day in ("rack_2026-10-23", "rack_2026-10-24", "rack_2026-10-25"):
        for npz in sorted((RACK / day).rglob("runs/*.npz")):
            try:
                meta = json.loads(npz.with_suffix(".json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if meta.get("can_id") != can:
                continue
            with np.load(npz) as a:
                if a["t"].size < 20:
                    continue
                temp = np.asarray(a["temp_c"], float)
            kind = meta.get("kind") or "unknown"
            lo, hi = out.get(kind, (math.inf, -math.inf))
            out[kind] = (min(lo, float(np.nanmin(temp))), max(hi, float(np.nanmax(temp))))
    return out


# ------------------------------------------------------------------------------------------------- the camera
CAMERA_KEYS = ["playback", "rgb", "depth", "band", "interval-hist", "dropped"]


def session_npz(run, serial):
    """A camera session's stamps: run "10-23/session_01a" is /archive/…/rack_2026-10-23/session_01a/cameras/cam_<serial>.npz."""
    day, session = run.split("/", 1)
    return RACK / f"rack_2026-{day}" / session / "cameras" / f"cam_{serial}.npz"


def camera(browser, base):
    runs, media = rows(CAMERA, "runs.json"), rows(CAMERA, "media.json")
    stamps, side = csv_rows(CAMERA, "samples.csv")
    labels = next((f.get("labels") or {} for f in side["schema"]["fields"] if f["name"] == "run"), {})
    sessions = sorted({r["run"] for r in stamps})
    cameras = sorted({r["device"] for r in stamps})
    page, ok = open_case(browser, base, CAMERA, CAMERA_KEYS)
    check(f"camera: every panel of the dashboard draws ({', '.join(CAMERA_KEYS)})", ok)
    first = newest(runs)
    check("camera: the rail's Session picker opens on the newest session", checked(page, "runs", "run") == first, {"checked": checked(page, "runs", "run"), "newest": first})
    # the frame-interval histogram and the dropped frames, per camera, against numpy over the archive's hw_ms
    for j, cam in enumerate(cameras):
        if j or checked(page, "coverage", "device") != cam:
            pick(page, "coverage", "device", cam)
        serial = cam.split()[-1]
        diffs = {s: np.diff(np.load(session_npz(s, serial))["hw_ms"].astype(float)) for s in sessions}
        every = np.concatenate([diffs[s] for s in sessions])
        for key in ("interval-hist", "dropped"):
            until_rows(page, key, len([r for r in stamps if r["device"] == cam]))
        got = stable_items(page, "interval-hist")
        bars = []
        for it in got["items"]:
            if it["type"] == "rect" and it["datum"]:
                p, v = bins_of(it["datum"])
                if len(p) == 1 and num(v):
                    bars.append((list(p.values())[0], v))
        bars.sort()
        sums, _ = bin_sums(every, np.ones(every.size), [b for b, _ in bars], spec_for(got, "frame_dt_ms"))
        bad = [{"bin": b, "drawn": v, "numpy": want} for (b, v), want in zip(bars, sums or []) if want != v] if sums is not None else ["an interval falls in an undrawn bin"]
        total = sum(v for _, v in bars)
        lo_all, hi_all = (bars[0][0][0], bars[-1][0][1]) if bars else (None, None)
        in_range = int(np.count_nonzero((every >= lo_all) & (every <= hi_all))) if bars else None
        check(f"camera {cam}: the frame-interval histogram equals numpy over cam_{serial}.npz hw_ms ({len(sessions)} sessions, {every.size} intervals): every bar's count, and every interval in its range drawn",
              bars and not bad and total == in_range, bad[:3] or {"bars": len(bars), "drawn": total, "numpy in range": in_range, "range": [lo_all, hi_all]})
        rest = len([r for r in stamps if r["device"] == cam]) - (total or 0)
        check(f"camera {cam}: every interval of samples.csv is in the histogram or past its range ({rest} past it), and samples.csv holds numpy's every interval",
              rest == int(np.count_nonzero(every > (hi_all if hi_all is not None else math.inf))) and len([r for r in stamps if r["device"] == cam]) == every.size,
              {"file rows": len([r for r in stamps if r["device"] == cam]), "numpy": int(every.size)})
        got = stable_items(page, "dropped")
        drawn = {}
        for it in got["items"]:
            dm = it["datum"] or {}
            v = next((dm[k] for k in dm if (k == "__count" or k.startswith("count") or k.startswith("sum_")) and num(dm[k])), None)
            if dm.get("run") is not None and num(v):
                drawn[dm["run"]] = v
        want = {labels.get(s, s): int(np.count_nonzero(diffs[s] > 50)) for s in sessions if np.count_nonzero(diffs[s] > 50)}
        check(f"camera {cam}: dropped frames per session (intervals over 50 ms) equal numpy over each session's cam_{serial}.npz hw_ms",
              drawn and drawn == want, {"drawn": drawn, "numpy": want})
    # each session: the clip, the clock, the video within one frame
    for i, run in enumerate(sorted((r["run"] for r in runs), key=lambda x: x != first)):
        if i:
            pick(page, "runs", "run", run)
        tag = f"camera {run}"
        clip = next((m for m in media if m["run"] == run and m["kind"] == "rgb"), None)
        with contextlib.suppress(Exception):
            page.wait_for_function("""(s) => { const v = document.querySelector("#example .dd-panel[data-panel='rgb'] video[data-t0]");
              return v && (v.dataset.src || '').endsWith(s) && v.readyState >= 2 && !v.seeking; }""", arg=clip["src"] if clip else "", timeout=WAIT)
        vid = page.evaluate("""() => [...document.querySelectorAll("#example .dd-panel[data-panel='rgb'] video[data-t0]")].map((v) => ({ src: v.dataset.src || null, t0: Number(v.dataset.t0) }))""")
        check(f"{tag}: the RGB card plays that session's clip from media.json ({clip['src'] if clip else None}) with its t0",
              clip and len(vid) == 1 and (vid[0]["src"] or "").endswith(clip["src"]) and abs(vid[0]["t0"] - clip["t0"]) < 1e-9, {"video": vid, "file": clip and [clip["src"], clip["t0"]]})
        c = page.evaluate(CLOCK)
        want = span_of(stamps, run)
        check(f"{tag}: the clock spans that session's frame stamps, min..max t {want}", want is not None and [c["start"], c["end"]] == want, {"clock": [c["start"], c["end"]]})
        if clip and want:
            t = round((want[0] + want[1]) / 2, 3)
            seek(page, t)
            with contextlib.suppress(Exception):
                page.wait_for_function("""() => { const v = document.querySelector("#example .dd-panel[data-panel='rgb'] video[data-t0]"); return v && v.readyState >= 2 && !v.seeking; }""", timeout=WAIT)
            cur = page.evaluate("""() => { const v = document.querySelector("#example .dd-panel[data-panel='rgb'] video[data-t0]"); return v ? v.currentTime : null; }""")
            check(f"{tag}: a paused seek to t = {t} lands the RGB clip on t − t0 within one frame (1/30 s)", cur is not None and abs(cur - (t - clip["t0"])) <= FRAME + 1e-6,
                  {"currentTime": cur, "want": t - clip["t0"]})
    empty = page.evaluate("""() => Object.fromEntries(['depth', 'band'].map((k) => { const p = document.querySelector(`#example .dd-panel[data-panel='${k}']`);
      return [k, { media: p ? [...p.querySelectorAll('video, img')].filter((m) => m.dataset.src || m.getAttribute('src')).length : null, text: p ? p.textContent : '' }]; }))""")
    check("camera: the depth and hyperspectral cards play nothing and say none is captured yet",
          empty["depth"]["media"] == 0 and empty["band"]["media"] == 0 and re.search(r"no depth", empty["depth"]["text"], re.I) and re.search(r"no hyperspectral", empty["band"]["text"], re.I),
          {k: {"media": v["media"], "text": re.sub(r"\s+", " ", v["text"])[:140]} for k, v in empty.items()})
    shot(page, "camera-light-1280")
    check("camera: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the arm + gripper
GRIPPER_KEYS = ["playback", "eef", "width", "width-at-grasp", "force", "path-3d"]


def gripper(browser, base):
    poses, samples, events = rows(GRIPPER, "poses.json"), rows(GRIPPER, "samples.json"), rows(GRIPPER, "events.json")
    cov = rows(GRIPPER, "coverage_samples.json")
    run = newest(rows(GRIPPER, "runs.json"))
    page, ok = open_case(browser, base, GRIPPER, GRIPPER_KEYS)
    check(f"arm-gripper: every panel of the dashboard draws ({', '.join(GRIPPER_KEYS)})", ok)
    text = page.evaluate("() => (document.querySelector('#example') || {}).textContent || ''")
    titles = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#example .dd-panel[data-panel]')].map((p) => [p.dataset.panel, (p.querySelector('.dd-title, h2, h3, header') || p).textContent.trim().slice(0, 160)]))""")
    check("arm-gripper: the page says stand-in, and every gripper panel says ILLUSTRATIVE where it is read",
          "stand-in" in text.lower() and all("illustrative" in (titles.get(k) or "").lower() for k in ("width", "force", "width-at-grasp")), titles)
    c = page.evaluate(CLOCK)
    want = span_of(poses, run)
    check(f"arm-gripper: the clock spans the run's poses, min..max t {want}", want is not None and [c["start"], c["end"]] == want, {"clock": [c["start"], c["end"]]})
    evs = sorted((e for e in events if e["run"] == run), key=lambda e: e["t"])
    for key, data, col in (("eef", poses, "z_mm"), ("width", samples, "width_mm"), ("force", samples, "force_n")):
        mine = [r for r in data if r["run"] == run]
        drawn = points(page, key)
        bad = compare_points(drawn, series_points(mine, col))
        check(f"arm-gripper: panel {key} draws exactly the file's {col} of the run, every situation, every sample (Vega's own dataset)", drawn and not bad, bad[:2] or {s: len(v) for s, v in drawn.items()})
        got = stable_items(page, key, [e["t"] for e in evs] + [e["t"] + FRAME for e in evs])
        at = got["at"] or []
        rules = [it for it in got["items"] if it["type"] == "rule" and num(it["x"]) and (it["y2"] is not None)]
        texts = [it for it in got["items"] if it["type"] == "text" and it["text"]]
        bad = []
        for j, e in enumerate(evs):
            if len(at) < 2 * len(evs):
                bad.append("no x scale")
                break
            px, frame_px = at[j], abs(at[len(evs) + j] - at[j])
            if not any(abs(r["x"] - px) <= frame_px + 1e-6 for r in rules):
                bad.append({"event": e["kind"], "t": e["t"], "rules at px": [round(r["x"], 1) for r in rules], "want px": round(px, 1)})
            if not any(abs((tx["x"] or 0) - px) <= frame_px + 1e-6 and tx["text"] == e["label"] for tx in texts):
                bad.append({"event": e["kind"], "label": e["label"], "texts": [(tx["text"], round(tx["x"] or 0, 1)) for tx in texts][:4]})
        check(f"arm-gripper: event marks sit at their t within one frame on panel {key}: a vertical mark and its label for each of events.json's {len(evs)} events ({', '.join(e['kind'] for e in evs)}), and no other",
              evs and not bad and len(rules) == len(evs), bad[:3] or {"marks": len(rules)})
    # the grasp coverage
    got = stable_items(page, "width-at-grasp")
    bars = sorted((list(p.values())[0], v) for p, v in (bins_of(it["datum"]) for it in got["items"] if it["type"] == "rect" and it["datum"]) if len(p) == 1 and num(v))
    vals = [(r["width_mm"], r["w"]) for r in cov if num(r["width_mm"])]
    sums, _ = bin_sums([x for x, _ in vals], [w for _, w in vals], [b for b, _ in bars], spec_for(got, "width_mm"))
    bad = [{"bin": b, "drawn": v, "numpy": want_v} for (b, v), want_v in zip(bars, sums or []) if want_v != v] if sums is not None else ["a value falls in an undrawn bin"]
    total = sum(v for _, v in bars)
    check("arm-gripper: the grip-width-at-grasp histogram's bars equal numpy's sum of w per bin over coverage_samples.json, and hold every row",
          bars and not bad and total == sum(r["w"] for r in cov if num(r["width_mm"])), bad[:3] or {"bars": len(bars), "sum w": total})
    # the tool path in 3D: every segment of every situation, from the GPU buffers
    for s in sorted({r["situation"] for r in poses if r["run"] == run}):
        rs = sorted((r for r in poses if r["run"] == run and r["situation"] == s), key=lambda r: r["t"])
        want_segs = [([a["x_mm"], a["y_mm"], a["z_mm"]], [b["x_mm"], b["y_mm"], b["z_mm"]]) for a, b in zip(rs, rs[1:])]
        g = page.evaluate(f"([k, s]) => {{ const h = ({HOOK})(k); try {{ return h ? h.geometry(s, 'line') : null; }} catch (e) {{ return null; }} }}", ["path-3d", s]) or {}
        segs, times = g.get("segments") or [], g.get("times") or []
        order = sorted(range(len(segs)), key=lambda i: times[i]) if len(times) == len(segs) else range(len(segs))
        ok3 = len(segs) == len(want_segs) and all(all(same32(gv, wv) for gp, wp in zip(segs[i], w) for gv, wv in zip(gp, wp)) for i, w in zip(order, want_segs))
        check(f"arm-gripper: the 3D tool path of {s} draws every segment of poses.json's run, each end within float32's rounding",
              ok3, {"drawn": len(segs), "file": len(want_segs)})
    shot(page, "arm-gripper-light-1280")
    check("arm-gripper: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
LOOKS = ((DRIVER, DRIVER_KEYS, "iq", "line"), (CAMERA, CAMERA_KEYS, "interval-hist", "rect"), (GRIPPER, GRIPPER_KEYS, "eef", "line"))


def looks(browser, base):
    for case, keys, key, mark in LOOKS:
        for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
            tag = f"{case}, {width} px, {'dark' if dark else 'light'}"
            page, ok = open_case(browser, base, case, keys, width=width, dark=dark)
            tk = tokens(page)
            got = stable_items(page, key)["items"]
            if mark == "line":
                real = next((colour(it["stroke"]) for it in got if it["type"] == "line" and (it["datum"] or {}).get("series") == "real"), None)
            else:
                real = next((colour(it["fill"]) for it in got if it["type"] == "rect"), None)
            slot1 = tk["series"][0] if tk["series"] else None
            check(f"{tag}: every panel draws, the real series is slot 1 of this theme (panel {key}), the page never scrolls sideways",
                  ok and real is not None and real == slot1 and no_sideways(page, width),
                  {"real": real, "slot 1": slot1, "scrollWidth": page.evaluate("() => document.scrollingElement.scrollWidth")})
            shot(page, f"{case.removeprefix('robotics-')}-{'dark' if dark else 'light'}-{width}")
            check(f"{tag}: no page error", not page.errors, page.errors[:3])
            page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    with guard("the files"):
        files()
    if not RACK.exists():
        check(f"the archive is readable at {RACK} (the oracles for i_q, the events, the box plot and the frame intervals)", False, "set RACK=")
    proc, base = serve(SITE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("the driver", driver), ("the camera", camera), ("the arm + gripper", gripper), ("themes and widths", looks)):
                with guard(name):
                    fn(browser, base)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (OUT / "p4-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P4 checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
