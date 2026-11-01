"""PEP 0010 P1c (docs/peps/0010-robotics-playback.md §6, §11): the Servo and Robot arm templates
(gallery/examples/robotics-servo, gallery/examples/robotics-arm) and their use-case group on the docs site, measured in
headless Chromium on the built site. Written red, before the templates.

    ~/psu-atlas/.venv/bin/python tests/browser/p1c_checks.py [OUT_DIR]     # after npm run build

What a template is, for these checks (PEP 0010 §6; the case's views.base): one <data-dashboard> (the case page's
#example) over the trajectory contract's tables (gallery/robotics/CONTRACT.md):
  - the `runs` dataset (runs.json) carries the rail's Run picker (`run`, as: select), the newest run (`started`) picked
    when the page opens; panel `runs` is the runs table, every run of runs.json, newest first;
  - the clock is `clock: {data: samples}` (servo) or `{data: poses}` (arm): a run pick spans that run's min..max t;
  - the playback panels, each over the picked run:
      servo  `angle` (q_deg), `velocity` (qd_deg_s), `torque` (tau_nm): timeseries over samples.json, series situation
      arm    `path-3d` (trajectory3d, show: trail) and `path-top` (projection top, show: all) over poses.json, with a
             robot per situation from links.json; `joint-angle` (q_deg over samples.json, the rail's joint)
Every expected number comes from the case's files, read here with Python (json; the oracle is the file, never the
page's model): the drawn timeseries points (Vega's own `series` dataset, after its decimation, which never fires
under 3,000 points a series), the 3D paths' segments read back from the GPU buffers (float32: equal to the file's
number within float32's rounding), each robot's link poses in world space at a sample of links.json, the runs table's
rows, the clock's span and the playback bar's readout. Then the docs site: both cases in the Examples page's Robotics
section, under a Playback use case; and each case page in light and dark at 1280 and 390 px, never scrolling sideways,
the real series in slot 1 of that theme. Screenshots go to OUT_DIR (default reports/media/robotics-p1cd, beside the
mocks of reports/media/robotics-plan).

Serves dist/site on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/p1c-checks.json and exits 1 if any check
fails.
"""

from __future__ import annotations

import contextlib
import json
import math
import pathlib
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "robotics-p1cd"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
EX = ROOT / "gallery" / "examples"
SERVO, ARM = "robotics-servo", "robotics-arm"
D = "#example"
WAIT = 45000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (a case missing, nothing drawn to measure) is one failing check in its own words."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def rows(case, name):
    doc = json.loads((EX / case / name).read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


def f32(x):
    """x as a float32 holds it: the GPU buffers' type."""
    return struct.unpack("f", struct.pack("f", x))[0]


def same32(got, want):
    """A coordinate read back from a float32 buffer against the file's number: equal once the file's is rounded the way
    the buffer rounds (the arrays the card builds are float64 until the upload)."""
    return got is not None and want is not None and abs(got - f32(want)) <= abs(f32(want)) * 2 ** -23 + 1e-9


# ------------------------------------------------------------------------------------------------- the oracles
def newest(runs):
    return max(runs, key=lambda r: r["started"])["run"]


def span(rs, run):
    ts = [r["t"] for r in rs if r["run"] == run and isinstance(r.get("t"), (int, float))]
    return [min(ts), max(ts)] if ts else None


def series_points(rs, run, y, *, device=None, situations=None, extra=None):
    """{situation: [(t, value)…]} of a run's rows, sorted by t, the nulls left out (a timeseries draws a gap there)."""
    out = {}
    for r in rs:
        if r["run"] != run or (device is not None and r.get("device") != device) or (situations is not None and r["situation"] not in situations):
            continue
        if extra and not all(r.get(k) == v for k, v in extra.items()):
            continue
        v = r.get(y)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(r.get("t"), (int, float)):
            out.setdefault(r["situation"], []).append((r["t"], v))
    for s in out.values():
        s.sort()
    return out


def compare_points(drawn, want):
    """drawn: {series: [(x, value)…]} as Vega holds them; want: the oracle. Every series, every point, exactly."""
    bad = []
    for s in sorted(set(drawn) | set(want)):
        d, w = sorted(drawn.get(s, [])), want.get(s, [])
        if len(d) != len(w):
            bad.append({"series": s, "drawn": len(d), "file": len(w)})
            continue
        off = [i for i, (a, b) in enumerate(zip(d, w)) if a[0] != b[0] or a[1] != b[1]]
        if off:
            i = off[0]
            bad.append({"series": s, "first differing point": i, "drawn": d[i], "file": w[i], "differing": len(off)})
    return bad


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
HOOK = f"(k) => {{ const p = ({PANEL})(k); const r = p && p.querySelector('.dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }}"
# every panel of the dashboard has drawn once, every rail has painted, every 3D card has rendered a frame
READY = f"""(keys) => {{
  const d = document.querySelector('#example'); if (!d || !d.dash) return false;
  const secs = keys.map((k) => ({PANEL})(k)); if (secs.some((s) => !s)) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; if (!els.length || !els.every((e) => e.dataset.view)) return false;
  if (![...d.querySelectorAll('.dd-rail data-facets')].every((f) => f.querySelector('details'))) return false;
  for (const s of secs) {{ const r = s.querySelector('.dv-scene3d'); if (r && !(r.scene3d && r.scene3d.renders() > 0)) return false;
    const v = s.querySelector('.dv-timeseries-plot'); if (v && !v.parentElement.vegaView) return false; }}
  return true; }}"""
# a timeseries panel's drawn points, from Vega's own dataset: {series: [[x, value]…]}
POINTS = f"""(k) => {{ const p = ({PANEL})(k); const plot = p && p.querySelector('.dv-timeseries-plot'); const v = plot && plot.parentElement.vegaView;
  if (!v) return null; const out = {{}}; for (const d of v.data('series')) (out[d.series] = out[d.series] || []).push([d.x, d.value]); return out; }}"""
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
    # WHY scroll each panel in: a 3D card starts WebGL only near the viewport (scene3d's IntersectionObserver)
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


def hook(page, key, call, *args):
    return page.evaluate(f"([k, args]) => {{ const h = ({HOOK})(k); try {{ return h ? h.{call}(...args) : null; }} catch (e) {{ return null; }} }}", [key, list(args)])


def rail_radio(dataset, key, value):
    return f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']"


def checked(page, dataset, key):
    return page.evaluate("([s]) => { const i = document.querySelector(s); return i ? i.dataset.value : null; }",
                         [f"{D} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]:checked"])


def pick_run(page, run):
    """The rail's Run radio, as a reader picks it ("Show N more" first when the run sits past the first ones)."""
    radio = page.locator(rail_radio("runs", "run", run))
    if not radio.count():
        more = page.locator(f"{D} .dd-rail data-facets[data-dataset='runs'] section.df-group[data-key='run'] [data-more]")
        if more.count():
            more.first.click()
            settle(page)
    radio = page.locator(rail_radio("runs", "run", run))
    radio.scroll_into_view_if_needed()
    radio.check()
    page.wait_for_function("(run) => { const d = document.querySelector('#example'); const f = d.state.rail.runs; return JSON.stringify(f || '').includes(run); }", arg=run, timeout=WAIT)
    settle(page, 4)


def seek(page, t):
    page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", t)
    settle(page, 2)


def fmt_time(t):
    """The playback bar's readout of a time (packages/core/src/clock.js fmtTime): 2 decimals under a minute."""
    if t is None:
        return None
    if abs(t) < 60:
        return f"{t:.2f} s"
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}"


def runs_table(page):
    return page.evaluate(f"""() => {{ const p = ({PANEL})('runs'); const el = p && p.querySelector('data-views'); const m = el && el.model;
      return m ? m.rows.map((r) => (r.run && typeof r.run === 'object' ? r.run.value : r.run)) : null; }}""")


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def tokens(page):
    t = page.evaluate("() => { const el = document.querySelector('#example data-views'); return el ? el.tokens() : null; }")
    hexes = lambda c: "#%02x%02x%02x" % tuple(round(float(x)) for x in re.findall(r"[\d.]+", c)[:3]) if c else None  # noqa: E731
    return {"series": [hexes(s) for s in (t or {}).get("series", [])], "muted": hexes((t or {}).get("muted"))}


def series_strokes(page, key):
    """A Vega timeseries panel's drawn line colours, from its scenegraph: {series: '#rrggbb'}."""
    out = page.evaluate(f"""(k) => {{ const p = ({PANEL})(k); const plot = p && p.querySelector('.dv-timeseries-plot'); const v = plot && plot.parentElement.vegaView; if (!v) return null;
      const got = {{}}; const walk = (n) => {{ if (!n) return; if (n.marktype === 'line') for (const i of n.items || []) {{ const s = i.datum && i.datum.series; if (s && i.stroke) got[s] = i.stroke; }}
        for (const i of n.items || []) if (i.items) walk(i); }}; walk(v.scenegraph().root); return got; }}""", key)
    return {k: _hex(v) for k, v in (out or {}).items()}


def _hex(colour):
    """Vega writes a resolved token as `rgb(r, g, b)`; the oracle is hex. Same colour, one spelling (orchestrator fix)."""
    if not isinstance(colour, str):
        return colour
    m = re.fullmatch(r"\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)\s*", colour)
    return "#%02x%02x%02x" % tuple(int(x) for x in m.groups()) if m else colour.lower()


def shot(page, name):
    try:
        page.evaluate("() => { const d = document.querySelector('#example'); if (d) window.scrollTo(0, d.getBoundingClientRect().top + window.scrollY - 60); }")
        settle(page)
        page.locator(D).screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- the files
def files():
    for case, clock_file in ((SERVO, "samples.json"), (ARM, "poses.json")):
        here = EX / case
        check(f"{case}: the case exists (views.base, README.md, runs.json, {clock_file})",
              all((here / f).exists() for f in ("views.base", "README.md", "runs.json", clock_file)), str(here.relative_to(ROOT)))
    runs = rows(SERVO, "runs.json")
    samples = rows(SERVO, "samples.json")
    devices = sorted({r["device"] for r in samples})
    per_run = {r["run"]: {s["situation"] for s in samples if s["run"] == r["run"]} for r in runs}
    check("servo: 40 runs of CAN 12 and CAN 14 (PEP 0010 P1c), each with real, twin and target samples",
          len(runs) == 40 and devices == ["CAN 12", "CAN 14"] and all(v >= {"real", "twin", "target"} for v in per_run.values()),
          {"runs": len(runs), "devices": devices, "short": [k for k, v in per_run.items() if not v >= {"real", "twin", "target"}][:3]})
    src = {(s["situation"], s["source"]) for s in samples}
    check("servo: real is family real, twin is sim, target is target (source)", src == {("real", "real"), ("twin", "sim"), ("target", "target")}, sorted(src))
    arm_runs = rows(ARM, "runs.json")
    readme = (EX / ARM / "README.md").read_text(encoding="utf-8") if (EX / ARM / "README.md").exists() else ""
    check("arm: labelled stand-in in its README and in every run of runs.json",
          "stand-in" in readme.lower() and arm_runs and all("stand-in" in json.dumps(r).lower() for r in arm_runs), [r.get("basis") or r.get("note") for r in arm_runs])


# ------------------------------------------------------------------------------------------------- the servo
SERVO_KEYS = ["runs", "playback", "angle", "velocity", "torque"]
SERVO_PANELS = {"angle": "q_deg", "velocity": "qd_deg_s", "torque": "tau_nm"}


def servo(browser, base):
    runs, samples = rows(SERVO, "runs.json"), rows(SERVO, "samples.json")
    page, ok = open_case(browser, base, SERVO, SERVO_KEYS)
    check("servo: every panel of the dashboard draws (runs, playback, angle, velocity, torque)", ok)
    first = newest(runs)
    check("servo: the rail's Run picker opens on the newest run (runs.json's latest `started`)", checked(page, "runs", "run") == first, {"checked": checked(page, "runs", "run"), "newest": first})
    want_order = [r["run"] for r in sorted(runs, key=lambda r: r["started"], reverse=True)]
    got_order = runs_table(page)
    check("servo: the runs table holds every run of runs.json, newest first", got_order == want_order,
          {"drawn": (got_order or [])[:3], "file": want_order[:3], "n": [len(got_order or []), len(want_order)]})
    # three picks: the newest (the default), the longest and the shortest run; each re-spans the clock to that run
    longest = max(runs, key=lambda r: (span(samples, r["run"]) or [0, 0])[1])["run"]
    shortest = min(runs, key=lambda r: (span(samples, r["run"]) or [0, 1e9])[1])["run"]
    for i, run in enumerate(dict.fromkeys([first, longest, shortest])):
        if i:
            pick_run(page, run)
        dev = next(r["device"] for r in samples if r["run"] == run)
        c = page.evaluate(CLOCK)
        want = span(samples, run)
        check(f"servo: a run pick ({run}) spans the clock to that run's min..max t in samples.json {want}",
              want is not None and [c["start"], c["end"]] == want, {"clock": [c["start"], c["end"]], "file": want})
        check(f"servo: the playback bar reads that run's end ({fmt_time(want[1]) if want else None})",
              want is not None and (c["readout"] or "").strip().endswith(fmt_time(want[1])), c["readout"])
        for key, y in SERVO_PANELS.items():
            drawn = {s: [tuple(p) for p in pts] for s, pts in (page.evaluate(POINTS, key) or {}).items()}
            bad = compare_points(drawn, series_points(samples, run, y, device=dev))
            check(f"servo {run}: panel {key} draws exactly samples.json's {y} of that run, every situation, every sample (Vega's own dataset)",
                  drawn and not bad, bad[:3] or {s: len(v) for s, v in drawn.items()})
    shot(page, "servo-light-1280")
    check("servo: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the arm
ARM_KEYS = ["runs", "playback", "path-3d", "path-top", "joint-angle"]


def segments_want(poses, run, situation, lo=None, hi=None):
    """The consecutive sample pairs of one situation's path in a run, in time order, that the window [lo, hi] shows
    (as the card's shader cuts it: a segment whose time span meets the window)."""
    rs = sorted((r for r in poses if r["run"] == run and r["situation"] == situation), key=lambda r: r["t"])
    out = []
    for a, b in zip(rs, rs[1:]):
        if (lo is not None and b["t"] < lo) or (hi is not None and a["t"] > hi):
            continue
        out.append(([a["x_mm"], a["y_mm"], a["z_mm"]], [b["x_mm"], b["y_mm"], b["z_mm"]], a["t"]))
    return out


def compare_segments(got, want):
    segs, times = (got or {}).get("segments") or [], (got or {}).get("times") or []
    if len(segs) != len(want):
        return [{"drawn": len(segs), "file": len(want)}], 0.0
    bad, worst = [], 0.0
    order = sorted(range(len(segs)), key=lambda i: times[i])
    for i, (a, b, t) in zip(order, want):
        s = segs[i]
        for got_p, want_p in ((s[0], a), (s[1], b)):
            for g, w in zip(got_p, want_p):
                worst = max(worst, abs(g - w))
                if not same32(g, w):
                    bad.append({"t": t, "drawn": s, "file": [a, b]})
                    break
    return bad[:3], worst


def arm(browser, base):
    runs, poses, samples, links = rows(ARM, "runs.json"), rows(ARM, "poses.json"), rows(ARM, "samples.json"), rows(ARM, "links.json")
    page, ok = open_case(browser, base, ARM, ARM_KEYS)
    check("arm: every panel of the dashboard draws (runs, playback, path-3d, path-top, joint-angle)", ok)
    text = page.evaluate("() => (document.querySelector('#example') || {}).textContent || ''")
    check("arm: the dashboard says stand-in where it is read", "stand-in" in text.lower(), None)
    first = newest(runs)
    check("arm: the rail's Run picker opens on the newest run", checked(page, "runs", "run") == first, {"checked": checked(page, "runs", "run"), "newest": first})
    want_order = [r["run"] for r in sorted(runs, key=lambda r: r["started"], reverse=True)]
    check("arm: the runs table holds every run of runs.json, newest first", runs_table(page) == want_order, {"drawn": runs_table(page), "file": want_order})
    for i, run in enumerate([first] + [r["run"] for r in runs if r["run"] != first]):
        if i:
            pick_run(page, run)
        c = page.evaluate(CLOCK)
        want = span(poses, run)
        check(f"arm: a run pick ({run}) spans the clock to that run's min..max t in poses.json {want}",
              want is not None and [c["start"], c["end"]] == want, {"clock": [c["start"], c["end"]], "file": want})
        situations = sorted({r["situation"] for r in poses if r["run"] == run})
        # the top view draws every time step (show: all): every segment of every situation's path
        worst_all, bad_all = 0.0, {}
        for s in situations:
            bad, worst = compare_segments(hook(page, "path-top", "geometry", s, "line"), segments_want(poses, run, s))
            worst_all = max(worst_all, worst)
            if bad:
                bad_all[s] = bad
        check(f"arm {run}: path-top draws every segment of every situation's tool path in poses.json ({', '.join(situations)}), each end within float32's rounding of the file",
              not bad_all, bad_all or {"worst mm": worst_all})
        # the 3D view draws the trail: at the run's middle, the segments inside [t − decay, t]
        mid = (want[0] + want[1]) / 2 if want else 0
        seek(page, mid)
        w = hook(page, "path-3d", "window") or {}
        bad_all, worst_all = {}, 0.0
        for s in situations:
            bad, worst = compare_segments(hook(page, "path-3d", "geometry", s, "line"), segments_want(poses, run, s, w.get("lo"), w.get("hi")))
            worst_all = max(worst_all, worst)
            if bad:
                bad_all[s] = bad
        check(f"arm {run}: path-3d at t = {mid:.3f} draws exactly the file's segments inside its trail window {[w.get('lo'), w.get('hi')]}",
              w.get("hi") is not None and abs(w["hi"] - mid) <= 1e-9 and not bad_all, bad_all or {"window": w, "worst mm": worst_all})
        # the robots: each situation's links at a links.json sample, in world space, where the file puts them
        lrows = sorted((r for r in links if r["run"] == run), key=lambda r: r["t"])
        if lrows:
            t_s = lrows[len(lrows) // 2]["t"]
            seek(page, t_s)
            page.wait_for_function(f"(k) => {{ const h = ({HOOK})(k); const r = h && h.robot(); return !!r && (r.state === 'ready' || r.state === 'failed'); }}", arg="path-3d", timeout=WAIT)
            settle(page, 2)
            got = (hook(page, "path-3d", "robot") or {}).get("links") or {}
            names = [k[:-2] for k in lrows[0] if k.endswith("_x")]
            bad, worst, n = [], 0.0, 0
            for s in situations:
                row = next((r for r in lrows if r["situation"] == s and r["t"] == t_s), None)
                if row is None or s not in got:
                    if row is not None:
                        bad.append({"situation": s, "robot": "not drawn"})
                    continue
                for link in names:
                    p = (got[s].get(link) or {}).get("p")
                    w3 = [row[f"{link}_x"], row[f"{link}_y"], row[f"{link}_z"]]
                    if p is None:
                        bad.append({"situation": s, "link": link, "drawn": None})
                        continue
                    d = max(abs(a - b) for a, b in zip(p, w3))
                    worst, n = max(worst, d), n + 1
                    if d > 0.01:
                        bad.append({"situation": s, "link": link, "drawn": p, "file": w3})
            check(f"arm {run}: at t = {t_s} every robot's links sit where links.json puts them (world space, within 0.01 mm)",
                  n > 0 and not bad, bad[:3] or {"links measured": n, "worst mm": worst})
        # the joint panel: the rail's joint, every situation
        dev = checked(page, "samples", "device")
        drawn = {s: [tuple(p) for p in pts] for s, pts in (page.evaluate(POINTS, "joint-angle") or {}).items()}
        bad = compare_points(drawn, series_points(samples, run, "q_deg", device=dev))
        check(f"arm {run}: joint-angle draws exactly samples.json's q_deg of the rail's joint ({dev}), every situation, every sample",
              dev is not None and drawn and not bad, bad[:3] or {s: len(v) for s, v in drawn.items()})
    shot(page, "arm-light-1280")
    check("arm: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the docs site
def site(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{base}/gallery/index.html")
    page.wait_for_selector("main.gallery[data-cols]", timeout=WAIT)
    got = page.evaluate("""() => { const s = document.querySelector('.type-group[data-group="Robotics"]');
      return { section: !!s, hidden: s ? s.hidden : null, heading: s ? s.querySelector('h2').textContent : null,
        cards: s ? [...s.querySelectorAll('.card')].map((c) => c.dataset.slug) : [],
        toc: [...document.querySelectorAll('.toc a.toc-group')].map((a) => a.textContent.trim()) }; }""")
    check("docs site: Examples has a Robotics section holding both templates (robotics-servo, robotics-arm)",
          got["section"] and not got["hidden"] and {SERVO, ARM} <= set(got["cards"]), got)
    check("docs site: the Examples contents list Robotics", any(t.startswith("Robotics") for t in got["toc"]), got["toc"])
    rows_ = json.loads((SITE / "gallery" / "gallery.json").read_text(encoding="utf-8"))["rows"]
    mine = {r["slug"]: r for r in rows_ if r["slug"] in (SERVO, ARM)}
    check("docs site: gallery.json files both under category Robotics, use case 'Robotics · Playback'",
          len(mine) == 2 and all(r.get("category") == "Robotics" and r.get("useCase") == "Robotics · Playback" for r in mine.values()),
          {k: [v.get("category"), v.get("useCase")] for k, v in mine.items()})
    for case in (SERVO, ARM):
        page.goto(f"{base}/gallery/{case}/index.html")
        crumbs = page.evaluate("() => (document.querySelector('.crumbs') || {}).textContent || ''")
        check(f"docs site: {case}'s page crumbs read Examples › Robotics › Playback", re.search(r"Examples\s*›\s*Robotics\s*›\s*Playback", crumbs) is not None, crumbs)
    check("docs site: no page error", not page.errors, page.errors[:3])
    context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
def looks(browser, base):
    for case, keys, key in ((SERVO, SERVO_KEYS, "angle"), (ARM, ARM_KEYS, "joint-angle")):
        for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
            tag = f"{case}, {width} px, {'dark' if dark else 'light'}"
            page, ok = open_case(browser, base, case, keys, width=width, dark=dark)
            tk = tokens(page)
            strokes = series_strokes(page, key)
            extra = {}
            if case == ARM:
                col = (hook(page, "path-3d", "colors") or {}).get("series") or {}
                extra = {"3D real": col.get("real")}
            check(f"{tag}: every panel draws, real is slot 1 of this theme ({key}{' and the 3D path' if case == ARM else ''}), the page never scrolls sideways",
                  ok and strokes.get("real") == tk["series"][0] and all(v == tk["series"][0] for v in extra.values()) and no_sideways(page, width),
                  {"real": strokes.get("real"), **extra, "slot 1": tk["series"][0], "scrollWidth": page.evaluate("() => document.scrollingElement.scrollWidth")})
            shot(page, f"{case.removeprefix('robotics-')}-{'dark' if dark else 'light'}-{width}")
            check(f"{tag}: no page error", not page.errors, page.errors[:3])
            page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    with guard("the files"):
        files()
    proc, base = serve(SITE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("the servo template", servo), ("the arm template", arm), ("the docs site", site), ("themes and widths", looks)):
                with guard(name):
                    fn(browser, base)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (OUT / "p1c-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} P1c checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
