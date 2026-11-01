"""The kit gaps the PEP 0010 template lanes found (P4, P2: gallery/examples/robotics-{servo,arm,driver,camera,arm-gripper}),
measured in headless Chromium on the built kit and site against the files. Written red, before the fixes; never edited
after. The pure halves are tests/unit/kit-gaps.test.mjs and check-kit-gaps.test.mjs.

    ~/psu-atlas/.venv/bin/python tests/browser/kit_gaps_checks.py [OUT_DIR]     # after npm run build

  1  a chart's rows swapped in place by a pick: every aggregate is what numpy says of the new rows (box plots min-max and
     1.5 IQR, a median beside a max, argmin/argmax, an IQR error bar, a product), CAN 13 → 12 → 14 → 13 → 12 over the
     BLDC driver's coverage file (fixtures/kit_gaps/swap.base); the driver template's box per run kind is Vega-Lite's
     boxplot (extent: min-max, PEP 0010 §5.4's key) and its whiskers numpy's per kind on every board
  2  timeseries annotations from data: from a dataset (filtered as a panel there, so a run pick moves them), from the
     view's own rows, as written (fixtures/kit_gaps/marks.base); the driver's fault and mode changes from its events.json
     (driver-marks.base); the Arm + gripper template's contact, grasp and release read from its events.json
  3  a chart whose x is a time in seconds follows the clock: a playhead at t, its x domain the time series' (and the
     clock's zoom window), its plot lined up with the time series above it within 1 px (the driver's Mode and Fault strips
     under v_bus and temperature); strip.base in a plain page
  4  levels on a recording (not live) shows the whole recording, with a playhead at t; `at: 30s` the 30 s ending at t
  5  a layered chart's own transform reaches its layers (a state strip's span ends: strip.base)
  6  a column's colors map takes muted (and 0, a slot, a token, a CSS colour); a null cell is muted
  7  annotation labels never overlap (Vega's own text bounds), each inside the plot, every one drawn when there is room
     (the gripper's contact and grasp 0.3 s apart, at 1280 and 390 px); a label with no room is read in the hover readout
  8  a rail facet nested under another (`parent:`): the driver's Driver and the servo's Servo list every board while a
     run is picked; picking another board moves the run to that board's newest
  9  a media card with no row says its view's own `empty:` text (the camera's depth and hyperspectral cards)
Light and dark, 1280 and 390 px where a thing is drawn. Oracles: numpy and the files, never the page's model.

Serves the repo root (the fixtures, /dist/, the cases' files) and dist/site (the case pages) on free 127.0.0.1 ports, stops
both when done, writes OUT_DIR/kit-gaps-checks.json (default reports/media/kit-gaps) with screenshots, exits 1 if any
check fails. A part that cannot be measured is one failing check in its own words, never a silent pass."""

from __future__ import annotations

import contextlib
import csv
import json
import math
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "kit-gaps"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
FIX = ROOT / "tests" / "browser" / "fixtures" / "kit_gaps"
PAGE = "/tests/browser/fixtures/kit_gaps/kit_gaps.html"
FIXURL = "/tests/browser/fixtures/kit_gaps/"
EX = ROOT / "gallery" / "examples"
DRIVER, SERVO, GRIPPER, CAMERA = "robotics-driver", "robotics-servo", "robotics-arm-gripper", "robotics-camera"
WAIT = 45000                # ms: a ceiling for a state to arrive on a loaded machine, not a pause
FRAME = 1.0 / 30            # one camera frame: "within one frame"
LOOKS = ((1280, False), (1280, True), (390, False), (390, True))
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:600]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A part that cannot run (nothing drawn, a file missing) is one failing check in its own words."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:400]}")


def tag(width, dark):
    return f"{width} px {'dark' if dark else 'light'}"


# ------------------------------------------------------------------------------------------------- files
def doc(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def rows(path):
    d = doc(path)
    return d["rows"] if isinstance(d, dict) else d


def csv_table(path):
    """A CSV read with its <name>.schema.json sidecar's types (numbers as floats, empty as None)."""
    path = pathlib.Path(path)
    side = doc(path.with_name(path.stem + ".schema.json"))
    kinds = {f["name"]: f.get("type") for f in side["schema"]["fields"]}
    out = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append({k: (None if v == "" else float(v) if kinds.get(k) in ("number", "integer") else v) for k, v in r.items()})
    return out


def base_of(case):
    return data_ui_base.loads((EX / case / "views.base").read_text(encoding="utf-8"))


def view_of(case, name):
    return next((v for v in base_of(case).get("views") or [] if v.get("name") == name), None)


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def close(a, b, tol=1e-9):
    return num(a) and num(b) and abs(a - b) <= tol * max(1.0, abs(b))


def hexc(c):
    """A colour ('#rrggbb', 'rgb(r, g, b)', 'rgba(…)') as '#rrggbb'."""
    if not isinstance(c, str):
        return None
    c = c.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return c
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    m = re.findall(r"[\d.]+", c)
    return "#%02x%02x%02x" % tuple(round(float(x)) for x in m[:3]) if len(m) >= 3 else c


# ------------------------------------------------------------------------------------------------- pages
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"


def settle(page, n=2):
    for _ in range(n):
        page.evaluate(SETTLE)


def wait(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- the state never came: the caller's check says so
        return False


def new_page(browser, *, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if not mobile else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    return page


def open_fixture(browser, base, **kw):
    page = new_page(browser, **kw)
    page.goto(f"{base}{PAGE}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


MOUNT_DASH = """([id, src]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const d = document.createElement('data-dashboard');
  d.id = id; d.setAttribute('no-url', ''); d.setAttribute('src', src);
  document.body.append(d);
  return true;
}"""
MOUNT_VIEWS = """([id, src, view]) => {
  for (const old of document.querySelectorAll('data-dashboard, data-views')) old.remove();
  const v = document.createElement('data-views');
  v.id = id; v.className = 'boxed';
  v.setAttribute('toolbar', 'none'); v.setAttribute('no-url', '');
  if (view) v.setAttribute('view', view);
  v.setAttribute('src', src);
  document.body.append(v);
  return true;
}"""
# every listed panel of a dashboard has drawn: its <data-views> has a view, every Vega view embedded
READY = """([root, keys]) => {
  const d = document.querySelector(root); if (!d || !d.dash) return false;
  for (const k of keys) { const p = d.querySelector(`.dd-panel[data-panel='${k}']`); if (!p) return false;
    const v = p.querySelector('data-views'); if (!v || !v.dataset.view) return false;
    const e = p.querySelector('.dv-view-chart, .dv-view-timeseries'); if (e && !e.vegaView) return false; }
  return true; }"""
# a Vega view's drawn items (marks only: never axes, grids or legends), its x scale, and where its plot sits on screen
ITEMS = """(sel) => { const e = document.querySelector(sel); const v = e && e.vegaView; if (!v) return null; const out = [];
  const clean = (d) => JSON.parse(JSON.stringify(d, (k, x) => (typeof x === 'number' && !Number.isFinite(x) ? String(x) : x)));
  const walk = (n) => { if (n.marktype && n.role === 'mark') for (const i of n.items || []) out.push({ type: n.marktype, name: n.name || null,
    x: i.x ?? null, x2: i.x2 ?? null, y: i.y ?? null, y2: i.y2 ?? null, text: i.text ?? null, fill: i.fill ?? null, stroke: i.stroke ?? null, opacity: i.opacity ?? null,
    b: i.bounds ? [i.bounds.x1, i.bounds.y1, i.bounds.x2, i.bounds.y2] : null, datum: i.datum && typeof i.datum === 'object' ? clean(i.datum) : null });
    for (const i of n.items || []) if (i.items) walk(i); };
  walk(v.scenegraph().root);
  let dom = null, rng = null; try { const s = v.scale('x'); dom = s.domain(); rng = s.range(); } catch (err) { /* no x scale */ }
  const c = e.querySelector('canvas'); const r = c ? c.getBoundingClientRect() : null;
  return { items: out, dom, rng, left: r ? r.left + v.padding().left + v.origin()[0] : null, top: r ? r.top + v.padding().top + v.origin()[1] : null,
    width: v.width(), height: v.height(), drawn: e.dataset.drawn ?? null }; }"""
XOF = "([sel, ts]) => { const e = document.querySelector(sel); const v = e && e.vegaView; if (!v) return null; const s = v.scale('x'); return ts.map((t) => s(t)); }"
PLAYHEAD = """(sel) => { const e = document.querySelector(sel); const p = e && e.querySelector('[data-playhead]');
  if (!p || p.hidden || getComputedStyle(p).display === 'none') return null; const r = p.getBoundingClientRect();
  return { cx: r.left + r.width / 2, top: r.top, height: r.height }; }"""


def items(page, sel):
    return page.evaluate(ITEMS, sel) or {"items": [], "dom": None, "rng": None, "left": None}


def stable_items(page, sel, tries=40):
    """A view's items once two reads 250 ms apart agree (a chart that re-embeds after a pick has finished)."""
    last = None
    for _ in range(tries):
        got = items(page, sel)
        if got == last and got["items"]:
            return got
        last = got
        time.sleep(0.25)
    return last or {"items": [], "dom": None, "rng": None, "left": None}


def panel(root, key, kind=".dv-view-chart, .dv-view-timeseries"):
    return f"{root} .dd-panel[data-panel='{key}'] :is({kind})"


def tokens(page, sel):
    t = page.evaluate("(sel) => { const el = document.querySelector(sel); return el && el.tokens ? el.tokens() : null; }", sel) or {}
    return {"series": [hexc(s) for s in t.get("series", [])], "muted": hexc(t.get("muted")), "bad": hexc((t.get("css") or {}).get("data-bad") or t.get("bad"))}


def radio(root, dataset, key, value):
    return f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio][data-value='{value}']"


def checked(page, root, dataset, key):
    return page.evaluate("([s]) => { const i = document.querySelector(s); return i ? i.dataset.value : null; }",
                         [f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]:checked"])


def listed(page, root, dataset, key):
    """{value: count} of a rail group's radios (Any left out)."""
    return page.evaluate("""([s]) => Object.fromEntries([...document.querySelectorAll(s)].filter((i) => i.dataset.value !== '')
      .map((i) => [i.dataset.value, Number((i.closest('label').querySelector('.df-count') || {}).textContent || NaN)]))""",
                         [f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] input[type=radio]"])


def pick(page, root, dataset, key, value, *, expect=None):
    """A rail radio, as a reader picks it ("Show N more" first when the value sits past the first ones)."""
    loc = page.locator(radio(root, dataset, key, value))
    if not loc.count():
        more = page.locator(f"{root} .dd-rail data-facets[data-dataset='{dataset}'] section.df-group[data-key='{key}'] [data-more]")
        if more.count():
            more.first.click()
            settle(page)
    loc = page.locator(radio(root, dataset, key, value))
    loc.scroll_into_view_if_needed()
    loc.check()
    wait(page, "([root, ds, v]) => { const d = document.querySelector(root); return JSON.stringify(d.state.rail[ds] || '').includes(v); }", [root, dataset, expect or value])
    settle(page, 4)


def until_drawn(page, sel, n):
    """Wait until a chart has drawn `n` rows (it writes data-drawn when a draw has run in Vega)."""
    wait(page, "([s, n]) => { const e = document.querySelector(s); return !!e && e.dataset.drawn === String(n); }", [sel, n])
    settle(page, 2)


def until_series(page, sel, n):
    """Wait until a time series draws `n` samples (its Vega dataset `series`)."""
    wait(page, "([s, n]) => { const e = document.querySelector(s); const v = e && e.vegaView; if (!v) return false; return v.data('series').length === n; }", [sel, n])
    settle(page, 2)


def no_sideways(page, width):
    return page.evaluate("() => document.scrollingElement.scrollWidth") <= width


def shot(page, name, sel=None):
    try:
        if sel:
            page.locator(sel).first.scroll_into_view_if_needed()
            settle(page)
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


def open_case(browser, site, case, keys, *, width=1280, dark=False):
    page = new_page(browser, width=width, dark=dark)
    page.goto(f"{site}/gallery/{case}/index.html")
    with contextlib.suppress(Exception):
        page.wait_for_selector("#example .dd-panel[data-panel]", timeout=WAIT)
        for k in keys:
            page.locator(f"#example .dd-panel[data-panel='{k}']").scroll_into_view_if_needed(timeout=5000)
    ok = wait(page, READY, ["#example", keys])
    wait(page, "() => [...document.querySelectorAll('#example .dd-rail data-facets')].every((f) => f.querySelector('details'))")
    settle(page, 3)
    return page, ok


# ------------------------------------------------------------------------------------------------- annotations
def annotation_items(got):
    """The annotation marks of a time series: its vertical rules (x and y2, as P4's checks read them) and its label texts
    (a datum from the marks dataset: label and row)."""
    its = got["items"]
    rules = [i for i in its if i["type"] == "rule" and num(i["x"]) and i["y2"] is not None]
    labels = [i for i in its if i["type"] == "text" and i["datum"] and "label" in i["datum"] and "row" in i["datum"] and i["text"]]
    return rules, labels


def overlapping(labels, tol=0.5):
    bad = []
    for a in range(len(labels)):
        for b in range(a + 1, len(labels)):
            p, q = labels[a]["b"], labels[b]["b"]
            if p and q and p[0] < q[2] - tol and q[0] < p[2] - tol and p[1] < q[3] - tol and q[1] < p[3] - tol:
                bad.append([labels[a]["text"], labels[b]["text"]])
    return bad


def marks_at(page, sel, want, got=None):
    """Each wanted (t, label): a rule within one frame of t's x, and the label's text there (when drawn). Returns problems,
    the drawn labels and the rules."""
    got = got or stable_items(page, sel)
    rules, labels = annotation_items(got)
    xs = page.evaluate(XOF, [sel, [t for t, _ in want] + [t + FRAME for t, _ in want]]) or []
    bad = []
    n = len(want)
    for j, (t, label) in enumerate(want):
        if len(xs) < 2 * n:
            bad.append("no x scale")
            break
        px, frame = xs[j], abs(xs[n + j] - xs[j])
        if not any(abs(r["x"] - px) <= frame + 1e-6 for r in rules):
            bad.append({"t": t, "label": label, "rule px": [round(r["x"], 1) for r in rules][:6], "want px": round(px, 1)})
    # Every drawn label sits on a wanted mark with its text (orchestrator fix: the first form failed any label text that
    # is drawn at one mark and hidden at another, which a repeated label such as 32 fault changes always is).
    if len(xs) >= 2 * n:
        for lab in labels:
            spots = [(xs[j], abs(xs[n + j] - xs[j])) for j, (_, lbl) in enumerate(want) if lbl == lab["text"]]
            if spots and not any(abs((lab["x"] or 0) - p) <= f + 1e-6 for p, f in spots):
                bad.append({"label": lab["text"], "at px": round(lab["x"] or 0, 1), "want px": [round(p, 1) for p, _ in spots][:6]})
    return bad, labels, rules, got


def in_plot(labels, width, tol=1.0):
    return [lab["text"] for lab in labels if lab["b"] and (lab["b"][0] < -tol or lab["b"][2] > width + tol)]


# ------------------------------------------------------------------------------------------------- gap 1: swaps
SWAP_BASE = FIXURL + "swap.base"
SWAP_KEYS = ["box", "box15", "medmax", "argext", "errbar", "product"]
SWAP_COL = {"box": "temp_c", "box15": "i_q_a", "medmax": "v_bus_v", "argext": "qd_deg_s", "errbar": "temp_c", "product": "w"}


def per_kind(rs, col):
    out = {}
    for r in rs:
        if num(r.get(col)):
            out.setdefault(r["kind"], []).append(r[col])
    return {k: np.asarray(v, float) for k, v in out.items()}


def swap_oracle(key, groups):
    """{kind: tuple} as each panel draws it, from numpy."""
    out = {}
    for k, v in groups.items():
        q1, med, q3 = np.quantile(v, [0.25, 0.5, 0.75])  # numpy's linear rule is d3's quantileSorted (Vega's)
        if key == "box":
            out[k] = (float(v.min()), float(v.max()))
        elif key == "box15":
            iqr = q3 - q1
            inside = v[(v >= q1 - 1.5 * iqr) & (v <= q3 + 1.5 * iqr)]
            out[k] = (float(q1), float(med), float(q3), float(inside.min()), float(inside.max()))
        elif key == "medmax":
            out[k] = (float(med), float(v.max()))
        elif key == "argext":
            out[k] = (float(v.min()), float(v.max()))
        elif key == "errbar":
            out[k] = (float(q1), float(q3))
        elif key == "product":
            out[k] = (float(np.prod(v)),)
    return out


def swap_drawn(key, got):
    col = SWAP_COL[key]
    out, parts = {}, {}
    for it in got["items"]:
        d = it["datum"] or {}
        k = d.get("kind")
        if k is None:
            continue
        if key == "box" and f"lower_whisker_{col}" in d:
            out[k] = (d[f"lower_whisker_{col}"], d[f"upper_whisker_{col}"])
        elif key == "box15":
            if f"mid_box_{col}" in d:
                parts.setdefault(k, {}).update(box=(d[f"lower_box_{col}"], d[f"mid_box_{col}"], d[f"upper_box_{col}"]))
            elif f"lower_whisker_{col}" in d:
                parts.setdefault(k, {}).update(whisk=(d[f"lower_whisker_{col}"], d[f"upper_whisker_{col}"]))
        elif key == "medmax" and f"median_{col}" in d:
            out[k] = (d[f"median_{col}"], d[f"max_{col}"])
        elif key == "argext" and "q_lo" in d:
            out[k] = (d["q_lo"], d["q_hi"])
        elif key == "errbar" and f"lower_{col}" in d:
            out[k] = (d[f"lower_{col}"], d[f"upper_{col}"])
        elif key == "product" and f"product_{col}" in d:
            out[k] = (d[f"product_{col}"],)
    for k, p in parts.items():
        if "box" in p and "whisk" in p:
            out[k] = (*p["box"], *p["whisk"])
    return out


def same_groups(drawn, want):
    bad = []
    for k in sorted(set(drawn) | set(want)):
        a, b = drawn.get(k), want.get(k)
        if a is None or b is None or len(a) != len(b) or not all(close(x, y) for x, y in zip(a, b)):
            bad.append({"kind": k, "drawn": a, "numpy": b})
    return bad


def swaps(browser, base):
    cov = csv_table(EX / DRIVER / "coverage_samples.csv")
    page = open_fixture(browser, base)
    page.evaluate(MOUNT_DASH, ["d", SWAP_BASE])
    ok = wait(page, READY, ["#d", SWAP_KEYS])
    check("gap 1: the swap fixture draws its six aggregate charts over the driver's coverage file", ok)
    for i, dev in enumerate(["CAN 13", "CAN 12", "CAN 14", "CAN 13", "CAN 12"]):
        if i:
            pick(page, "#d", "coverage", "device", dev)
        mine = [r for r in cov if r["device"] == dev]
        for key in SWAP_KEYS:
            col = SWAP_COL[key]
            sel = panel("#d", key, ".dv-view-chart")
            until_drawn(page, sel, len([r for r in mine if num(r.get(col))]))
            got = stable_items(page, sel)
            bad = same_groups(swap_drawn(key, got), swap_oracle(key, per_kind(mine, col)))
            check(f"gap 1: pick {i} ({dev}): panel {key} draws numpy's {key} of {col} per run kind over {dev}'s rows (no cell left from an earlier pick)",
                  not bad, bad[:3] or None)
    check("gap 1: the swap fixture: no page error", not page.errors, page.errors[:3])
    page.context.close()


def driver_box(browser, site):
    """The driver template's box per run kind: Vega-Lite's boxplot with min-max whiskers (PEP 0010 §5.4), numpy's per kind
    on each board's newest run in turn."""
    view = view_of(DRIVER, "Temperature by run kind") or {}
    mark = ((view.get("chart") or {}).get("mark")) or {}
    check("gap 1: the driver template draws its box per run kind with Vega-Lite's boxplot, extent: min-max (P4's three-layer stand-in gone)",
          isinstance(mark, dict) and mark.get("type") == "boxplot" and mark.get("extent") == "min-max", view.get("chart"))
    runs = rows(EX / DRIVER / "runs.json")
    cov = csv_table(EX / DRIVER / "coverage_samples.csv")
    newest = {}
    for r in sorted(runs, key=lambda r: r["started"], reverse=True):
        newest.setdefault(r["device"], r["run"])
    keys = ["iq", "temp-by-kind"]
    page, ok = open_case(browser, site, DRIVER, keys)
    sel = panel("#example", "temp-by-kind", ".dv-view-chart")
    for i, dev in enumerate(["CAN 13", "CAN 12", "CAN 14", "CAN 13"]):
        if i:
            pick(page, "#example", "runs", "run", newest[dev])
        board = [r for r in cov if r["device"] == dev]
        until_drawn(page, sel, len([r for r in board if num(r.get("temp_c"))]))
        got = stable_items(page, sel)
        drawn = {}
        for it in got["items"]:
            d = it["datum"] or {}
            if d.get("kind") is not None and "lower_whisker_temp_c" in d:
                drawn[d["kind"]] = (d["lower_whisker_temp_c"], d["upper_whisker_temp_c"])
        want = {k: (float(v.min()), float(v.max())) for k, v in per_kind(board, "temp_c").items()}
        bad = same_groups(drawn, want)
        check(f"gap 1: driver, {dev} ({newest[dev]}): the boxplot's whiskers are numpy's min and max of temp_c per run kind over {dev}'s coverage rows",
              ok and drawn and not bad, bad[:3] or {"kinds": len(drawn)})
    check("gap 1: driver: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- gaps 2 and 7: marks
MARKS_BASE = FIXURL + "marks.base"
MARK_KEYS = ["playback", "data", "own", "fixed", "mixed"]


def marks(browser, base):
    events = rows(FIX / "marks_events.json")
    samples = rows(FIX / "marks_samples.json")
    for width, dark in LOOKS:
        t = tag(width, dark)
        page = open_fixture(browser, base, width=width, dark=dark)
        page.evaluate(MOUNT_DASH, ["d", MARKS_BASE])
        ok = wait(page, READY, ["#d", MARK_KEYS])
        check(f"gap 2: {t}: the marks fixture draws its four time series", ok)
        tk = tokens(page, "#d data-views")
        own = sorted((r["t"], r["event"]) for r in samples if r["run"] == "A" and r.get("event"))
        evA = sorted((e["t"], e["label"]) for e in events if e["run"] == "A")
        cases = {"data": evA, "own": own, "fixed": [(1.61, "contact"), (1.91, "grasp"), (4.97, "release")], "mixed": sorted([(0.5, "start"), *evA])}
        for key, want in cases.items():
            sel = panel("#d", key, ".dv-view-timeseries")
            bad, labels, rules, got = marks_at(page, sel, want)
            check(f"gap 2: {t}: panel {key}: a vertical mark at each annotation's t within one frame ({len(want)}), and no other",
                  not bad and len(rules) == len(want), bad[:3] or {"rules": len(rules)})
            check(f"gap 7: {t}: panel {key}: every label is drawn ({', '.join(lab for _, lab in want)}), none overlaps another (Vega's text bounds), each inside the plot",
                  sorted(lab["text"] for lab in labels) == sorted(lab for _, lab in want) and not overlapping(labels) and not in_plot(labels, got["width"]),
                  {"drawn": [lab["text"] for lab in labels], "overlap": overlapping(labels), "outside": in_plot(labels, got["width"])})
            if key == "mixed":
                tone = {round(r["x"], 3): hexc(r["stroke"]) for r in rules}
                xs = page.evaluate(XOF, [sel, [0.5] + [e for e, _ in evA]]) or []
                strokes = [tone.get(round(x, 3)) for x in xs]
                check(f"gap 2: {t}: an annotation's tone colours its mark: the dataset's (tone: bad) the bad token, the written one muted",
                      strokes and strokes[0] == tk["muted"] and all(s == tk["bad"] for s in strokes[1:]), {"strokes": strokes, "muted": tk["muted"], "bad": tk["bad"]})
        if width == 1280 and not dark:
            shot(page, "marks-a-light-1280", "#d")
            # the run pick moves the dataset's marks (a layer: filtered as a panel on events)
            pick(page, "#d", "runs", "run", "B")
            evB = sorted((e["t"], e["label"]) for e in events if e["run"] == "B")
            sel = panel("#d", "data", ".dv-view-timeseries")
            until_series(page, sel, len([r for r in samples if r["run"] == "B"]))
            bad, labels, rules, got = marks_at(page, sel, evB)
            check(f"gap 2: picking run B moves the marks to B's {len(evB)} events (the events dataset filtered by the pick)", not bad and len(rules) == len(evB), bad[:3] or {"rules": len(rules)})
            check("gap 7: B's dense events (12 within 0.44 s): the labels drawn never overlap, each inside the plot, at most three rows",
                  labels and not overlapping(labels) and not in_plot(labels, got["width"]) and len({round(lab["y"] or 0, 1) for lab in labels}) <= 3,
                  {"drawn": len(labels), "rows": sorted({round(lab["y"] or 0, 1) for lab in labels}), "overlap": overlapping(labels)[:3]})
            hidden = [(tt, lab) for tt, lab in evB if lab not in {x["text"] for x in labels}]
            missing = []
            for tt, lab in hidden:
                page.evaluate("(t) => document.querySelector('#d').clock.setHover(t)", tt)
                settle(page, 1)
                read = page.evaluate("(sel) => { const e = document.querySelector(sel); const r = e && e.querySelector('.dv-timeseries-read'); return r ? r.textContent : ''; }", sel)
                if lab not in (read or ""):
                    missing.append({"t": tt, "label": lab, "readout": (read or "")[:120]})
            page.evaluate("() => document.querySelector('#d').clock.setHover(null)")
            check(f"gap 7: a label with no room ({len(hidden)} of {len(evB)}) is read in the hover readout at its mark", hidden and not missing, missing[:3] or {"hidden": len(hidden)})
            shot(page, "marks-b-dense-light-1280", "#d")
        check(f"gap 2: {t}: no sideways scroll, no page error", no_sideways(page, width) and not page.errors, page.errors[:3])
        page.context.close()


def driver_marks(browser, base):
    """The driver's mode and fault changes drawn from its events.json (gap 2: "the driver's mode/fault events")."""
    events = rows(EX / DRIVER / "events.json")
    samples = rows(EX / DRIVER / "samples.json")
    runs = rows(EX / DRIVER / "runs.json")
    page = open_fixture(browser, base)
    page.evaluate(MOUNT_DASH, ["d", FIXURL + "driver-marks.base"])
    ok = wait(page, READY, ["#d", ["iq", "vbus"]])
    check("gap 2: the driver's events fixture draws i_q and v_bus", ok)
    # The second pick is the newest run that has both kinds of change (orchestrator fix: the fixture's filtered faults and
    # modes datasets are linked to runs, and links are two-way (sim2real #8, P3), so a run with no fault is never offered).
    both = {e["run"] for e in events if e["kind"] == "fault"} & {e["run"] for e in events if e["kind"] == "mode"}
    newest = max((r for r in runs if r["run"] in both and r["run"] != "10-24/session_11/s07"), key=lambda r: r["started"])["run"]
    for i, run in enumerate(["10-24/session_11/s07", newest]):
        if i:
            pick(page, "#d", "runs", "run", run)
        until_series(page, panel("#d", "iq", ".dv-view-timeseries"), len([r for r in samples if r["run"] == run and num(r.get("i_q_a"))]))
        for key, kind in (("iq", "fault"), ("vbus", "mode")):
            want = sorted((e["t"], e["label"]) for e in events if e["run"] == run and e["kind"] == kind)
            bad, labels, rules, got = marks_at(page, panel("#d", key, ".dv-view-timeseries"), want)
            check(f"gap 2: driver {run}: panel {key} marks each of events.json's {len(want)} {kind} changes at its t within one frame, and no other",
                  not bad and len(rules) == len(want), bad[:3] or {"rules": len(rules)})
            check(f"gap 7: driver {run}: panel {key}: the labels drawn never overlap and stay in the plot", not overlapping(labels) and not in_plot(labels, got["width"]),
                  {"drawn": len(labels), "overlap": overlapping(labels)[:3]})
    shot(page, "driver-marks-light-1280", "#d")
    check("gap 2: the driver's events fixture: no page error", not page.errors, page.errors[:3])
    page.context.close()


GRIPPER_KEYS = ["playback", "eef", "width", "force"]


def gripper(browser, site):
    base = base_of(GRIPPER)
    ts = [v for v in base.get("views") or [] if v.get("type") == "timeseries"]
    wrote = [((v.get("timeseries") or {}).get("annotations")) for v in ts]
    check("gap 2: every Arm + gripper time series reads its marks from events.json (annotations: [{data: events, x: t, label: label}]), none written by hand",
          ts and all(a == [{"data": "events", "x": "t", "label": "label"}] for a in wrote), wrote)
    events = sorted((e["t"], e["label"]) for e in rows(EX / GRIPPER / "events.json"))
    for width, dark in LOOKS:
        t = tag(width, dark)
        page, ok = open_case(browser, site, GRIPPER, GRIPPER_KEYS, width=width, dark=dark)
        for key in ("eef", "width", "force"):
            sel = panel("#example", key, ".dv-view-timeseries")
            bad, labels, rules, got = marks_at(page, sel, events)
            check(f"gap 2: gripper, {t}: panel {key} marks contact, grasp and release at events.json's t within one frame, and no other",
                  ok and not bad and len(rules) == len(events), bad[:3] or {"rules": len(rules)})
            check(f"gap 7: gripper, {t}: panel {key}: contact, grasp and release are all drawn, none overlaps another, each inside the plot",
                  sorted(lab["text"] for lab in labels) == sorted(lab for _, lab in events) and not overlapping(labels) and not in_plot(labels, got["width"]),
                  {"drawn": [[lab["text"], lab["b"]] for lab in labels], "overlap": overlapping(labels)})
        shot(page, f"gripper-{'dark' if dark else 'light'}-{width}")
        check(f"gap 2: gripper, {t}: no sideways scroll, no page error", no_sideways(page, width) and not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- gap 3: the clock
DRIVER_KEYS = ["playback", "iq", "id", "vbus", "temp", "mode", "fault"]


def lined_up(page, a_sel, b_sel, ts):
    """Screen x of each t in two views (their plot's left + their own x scale) and their playheads."""
    xa = page.evaluate(XOF, [a_sel, ts]) or []
    xb = page.evaluate(XOF, [b_sel, ts]) or []
    ga, gb = items(page, a_sel), items(page, b_sel)
    if not xa or not xb or ga["left"] is None or gb["left"] is None:
        return None
    return {"a": [ga["left"] + x for x in xa], "b": [gb["left"] + x for x in xb], "dom": [ga["dom"], gb["dom"]],
            "ph": [page.evaluate(PLAYHEAD, a_sel), page.evaluate(PLAYHEAD, b_sel)]}


def driver_clock(browser, site):
    runs = rows(EX / DRIVER / "runs.json")
    samples = rows(EX / DRIVER / "samples.json")
    run = max(runs, key=lambda r: r["started"])["run"]
    ts = [r["t"] for r in samples if r["run"] == run]
    lo, hi = min(ts), max(ts)
    for width, dark in LOOKS:
        t = tag(width, dark)
        page, ok = open_case(browser, site, DRIVER, DRIVER_KEYS, width=width, dark=dark)
        mid = round((lo + hi) / 2, 3)
        page.evaluate("(t) => { const c = document.querySelector('#example').clock; c.pause(); c.seek(t); }", mid)
        settle(page, 3)
        # two columns at 1280 (mode under v_bus, fault under temperature); one column at 390 (every panel full width)
        pairs = (("mode", "vbus"), ("fault", "temp")) if width > 500 else (("mode", "iq"), ("fault", "iq"))
        for strip, series in pairs:
            a, b = panel("#example", strip, ".dv-view-chart"), panel("#example", series, ".dv-view-timeseries")
            got = lined_up(page, a, b, [lo, mid, hi])
            ph = got and got["ph"]
            check(f"gap 3: driver, {t}: the {strip} strip draws a playhead at t = {mid}, where its own x scale puts t (within 1 px)",
                  ok and ph and ph[0] and abs(ph[0]["cx"] - got["a"][1]) <= 1.0, got and {"playhead": ph[0], "x(t)": got["a"][1]})
            check(f"gap 3: driver, {t}: the {strip} strip spans the time series' x domain ({series}: the run's {lo}..{hi} s)",
                  got and got["dom"][0] and got["dom"][1] and all(close(x, y) for x, y in zip(got["dom"][0], got["dom"][1])) and close(got["dom"][0][0], lo) and close(got["dom"][0][1], hi),
                  got and got["dom"])
            check(f"gap 3: driver, {t}: the {strip} strip's time axis lines up with {series}'s: the start, t and the end within 1 px, and the playheads within 1 px",
                  got and all(abs(x - y) <= 1.0 for x, y in zip(got["a"], got["b"])) and ph and ph[0] and ph[1] and abs(ph[0]["cx"] - ph[1]["cx"]) <= 1.0,
                  got and {"strip": [round(x, 1) for x in got["a"]], "series": [round(x, 1) for x in got["b"]], "playheads": [p and round(p["cx"], 1) for p in ph]})
        if width == 1280 and not dark:
            # the clock's zoom window: the strips take it as the time series do
            win = [round(lo + (hi - lo) * 0.25, 3), round(lo + (hi - lo) * 0.75, 3)]
            page.evaluate("(w) => document.querySelector('#example').clock.setWindow(w)", win)
            wait(page, """(w) => ['mode', 'vbus'].every((k) => { const e = document.querySelector(`#example .dd-panel[data-panel='${k}'] :is(.dv-view-chart, .dv-view-timeseries)`);
              const d = e && e.vegaView && e.vegaView.scale('x').domain(); return d && Math.abs(d[0] - w[0]) < 1e-9 && Math.abs(d[1] - w[1]) < 1e-9; })""", win)
            settle(page, 2)
            got = lined_up(page, panel("#example", "mode", ".dv-view-chart"), panel("#example", "vbus", ".dv-view-timeseries"), [win[0], mid, win[1]])
            check(f"gap 3: driver: a zoom window {win} is the strips' x domain as the time series' (mode under v_bus lined up within 1 px)",
                  got and all(close(x, y) for x, y in zip(got["dom"][0], win)) and all(abs(x - y) <= 1.0 for x, y in zip(got["a"], got["b"])),
                  got and {"domains": got["dom"], "strip": [round(x, 1) for x in got["a"]], "series": [round(x, 1) for x in got["b"]]})
            page.evaluate("() => document.querySelector('#example').clock.setWindow(null)")
            settle(page, 2)
        shot(page, f"driver-{'dark' if dark else 'light'}-{width}")
        check(f"gap 3: driver, {t}: no sideways scroll, no page error", no_sideways(page, width) and not page.errors, page.errors[:3])
        page.context.close()


def spans_of(rs, col, end):
    """[(t, t_end, value)]: each run of one value from its first row, to the next span's first row (the last to `end`)."""
    rs = sorted(rs, key=lambda r: r["t"])
    starts = [r for i, r in enumerate(rs) if i == 0 or r[col] != rs[i - 1][col]]
    return [(s["t"], starts[i + 1]["t"] if i + 1 < len(starts) else end, s[col]) for i, s in enumerate(starts)]


def strip_plain(browser, base):
    """gaps 3 and 5 in a plain <data-views>: the chart's own transform reaches its layer; the strip follows the page's clock."""
    rs = rows(FIX / "strip.json")
    want = spans_of(rs, "mode", max(r["t"] for r in rs))
    for width, dark in ((1280, False), (390, True)):
        t = tag(width, dark)
        page = open_fixture(browser, base, width=width, dark=dark)
        page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "strip.base", "Strip"])
        sel = "#v .dv-view-chart"
        wait(page, "(s) => { const e = document.querySelector(s); return !!e && !!e.vegaView; }", sel)
        settle(page, 3)
        got = stable_items(page, sel)
        drawn = sorted((it["datum"]["t"], it["datum"].get("t_end"), it["datum"]["mode"]) for it in got["items"] if it["type"] == "rect" and it["datum"] and "mode" in it["datum"])
        check(f"gap 5: {t}: a layered chart's own transform reaches its layer: every span of strip.json's mode, to the next span's start (the last to the run's end, a joinaggregate of the chart)",
              drawn == want, {"drawn": drawn[:6], "file": want[:6]})
        page.evaluate("() => { const c = window.kit.clockFor(document.querySelector('#v')); c.pause(); c.seek(2); }")
        settle(page, 3)
        ph = page.evaluate(PLAYHEAD, sel)
        x = page.evaluate(XOF, [sel, [2.0]]) or [None]
        got = items(page, sel)
        check(f"gap 3: {t}: a time-x chart in a plain page spans its rows' time (0..4.5 s) and draws the page clock's t as a playhead, within 1 px",
              ph and x[0] is not None and got["left"] is not None and abs(ph["cx"] - (got["left"] + x[0])) <= 1.0 and got["dom"] and close(got["dom"][0], 0) and close(got["dom"][1], 4.5),
              {"playhead": ph, "x(2)": x[0] is not None and got["left"] is not None and got["left"] + x[0], "domain": got["dom"]})
        if width == 1280:
            shot(page, "strip-light-1280", "#v")
        check(f"gap 5: {t}: strip: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- gap 4: levels
ORDER = ["ok", "warn", "error"]


def level_bins(changes, before, a, b, n):
    """The worst level held in each of n bins over (a, b] (the level in force at a bin's start, and every change in it);
    None where nothing is in force. Changes: [(t, level)] in time order, those after a; before: the level at a."""
    w = (b - a) / n
    out, cur, i = [], before, 0
    for k in range(n):
        hi = b if k == n - 1 else a + (k + 1) * w
        held = [cur] if cur is not None else []
        while i < len(changes) and changes[i][0] <= hi:
            held.append(changes[i][1])
            cur = changes[i][1]
            i += 1
        out.append(max(held, key=ORDER.index) if held else None)
    return out


LEVELS = """(sel) => { const e = document.querySelector(sel); if (!e) return null;
  const strips = [...e.querySelectorAll('[data-strip]')].map((s) => { const bars = [...s.children]; const r0 = bars.length ? bars[0].getBoundingClientRect() : null;
    const r1 = bars.length ? bars[bars.length - 1].getBoundingClientRect() : null;
    return { name: s.dataset.strip, levels: bars.map((b) => b.dataset.level || null), left: r0 && r0.left, right: r1 && r1.right }; });
  const p = e.querySelector('[data-playhead]'); const pr = p && !p.hidden && getComputedStyle(p).display !== 'none' ? p.getBoundingClientRect() : null;
  return { t0: Number(e.dataset.t0), t1: Number(e.dataset.t1), strips, playhead: pr ? pr.left + pr.width / 2 : null }; }"""


def levels(browser, base):
    data = rows(FIX / "levels.json")
    lo, hi = min(r["t"] for r in data), max(r["t"] for r in data)
    by = {}
    for r in data:
        by.setdefault(r["stream"], []).append((r["t"], r["level"]))
    for width, dark in LOOKS:
        t = tag(width, dark)
        page = open_fixture(browser, base, width=width, dark=dark)
        page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "levels.base", "Whole"])
        sel = "#v .dv-view-levels"
        wait(page, "(s) => { const e = document.querySelector(s); return !!e && e.querySelectorAll('[data-strip]').length >= 2; }", sel)
        settle(page, 3)
        for at in (0.0, 60.0):
            if at:
                page.evaluate("(t) => { const c = window.kit.clockFor(document.querySelector('#v')); c.pause(); c.seek(t); }", at)
                settle(page, 3)
            got = page.evaluate(LEVELS, sel) or {}
            check(f"gap 4: {t}: at t = {at}, levels on a recording shows the whole recording, {lo}..{hi} s (its data-t0 / data-t1)",
                  close(got.get("t0"), lo) and close(got.get("t1"), hi), {"t0": got.get("t0"), "t1": got.get("t1")})
            bad = []
            for s in got.get("strips") or []:
                ch = sorted(by.get(s["name"], []))
                before = [lv for tt, lv in ch if tt <= lo]
                want = level_bins([(tt, lv) for tt, lv in ch if tt > lo], before[-1] if before else None, lo, hi, len(s["levels"]))
                if s["levels"] != want:
                    first = next(i for i, (x, y) in enumerate(zip(s["levels"], want)) if x != y) if len(s["levels"]) == len(want) else None
                    bad.append({"strip": s["name"], "first differing bin": first, "drawn": s["levels"][first] if first is not None else len(s["levels"]), "oracle": want[first] if first is not None else len(want)})
            check(f"gap 4: {t}: at t = {at}, every bin is the worst level held in it over the whole recording (numpy-side oracle, both streams)",
                  got.get("strips") and len(got["strips"]) == 2 and not bad, bad[:2] or {"bins": [len(s["levels"]) for s in got.get("strips") or []]})
        got = page.evaluate(LEVELS, sel) or {}
        s0 = (got.get("strips") or [{}])[0]
        want_x = s0.get("left") is not None and s0["left"] + (60.0 - lo) / (hi - lo) * (s0["right"] - s0["left"])
        check(f"gap 4: {t}: a playhead marks t = 60 on the strips, where t falls on the recording (within 1 px)",
              got.get("playhead") is not None and want_x and abs(got["playhead"] - want_x) <= 1.0, {"playhead": got.get("playhead"), "want": want_x})
        if width == 1280 and not dark:
            shot(page, "levels-whole-light-1280", "#v")
        page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "levels.base", "Window"])
        wait(page, "(s) => { const e = document.querySelector(s); return !!e && e.querySelectorAll('[data-strip]').length >= 1; }", sel)
        page.evaluate("(t) => { const c = window.kit.clockFor(document.querySelector('#v')); c.pause(); c.seek(t); }", 60.0)
        settle(page, 3)
        got = page.evaluate(LEVELS, sel) or {}
        check(f"gap 4: {t}: `at: 30s` on a recording still shows the 30 s ending at t (30..60 at t = 60)",
              close(got.get("t0"), 30.0) and close(got.get("t1"), 60.0), {"t0": got.get("t0"), "t1": got.get("t1")})
        check(f"gap 4: {t}: levels: no sideways scroll, no page error", no_sideways(page, width) and not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- gap 6: colours
def colours(browser, base):
    data = rows(FIX / "colors.json")
    for width, dark in LOOKS:
        t = tag(width, dark)
        page = open_fixture(browser, base, width=width, dark=dark)
        page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "colors.base", "Mapped"])
        sel = "#v .dv-view-chart"
        wait(page, "(s) => { const e = document.querySelector(s); return !!e && !!e.vegaView; }", sel)
        settle(page, 3)
        tk = tokens(page, "#v")
        want = {"ok": tk["series"][0] if tk["series"] else None, "idle": tk["muted"], "zero": tk["muted"], "hot": tk["bad"], "custom": "#7a3db8", None: tk["muted"]}
        got = stable_items(page, sel)
        fills = {}
        for it in got["items"]:
            if it["type"] == "rect" and it["datum"] and "v" in it["datum"]:
                fills[it["datum"]["v"]] = hexc(it["fill"])
        bad = [{"v": r["v"], "state": r["state"], "fill": fills.get(r["v"]), "want": want[r["state"]]} for r in data if fills.get(r["v"]) != want[r["state"]]]
        check(f"gap 6: {t}: a colors map's slot, muted, 0, token and CSS colour each colour their bars; a null state is muted",
              fills and not bad, bad[:4] or None)
        page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "colors.base", "Palette"])
        wait(page, "(s) => { const e = document.querySelector(s); return !!e && !!e.vegaView && e.dataset.drawn; }", sel)
        settle(page, 3)
        got = stable_items(page, sel)
        fills = {it["datum"]["v"]: hexc(it["fill"]) for it in got["items"] if it["type"] == "rect" and it["datum"] and "v" in it["datum"]}
        nulls = {fills.get(r["v"]) for r in data if r["other"] is None}
        named = {r["other"]: fills.get(r["v"]) for r in data if r["other"] is not None}
        check(f"gap 6: {t}: with no colors map a null cell is muted, never the hue of its label; a, b and c keep three palette colours",
              nulls == {tk["muted"]} and len(set(named.values())) == 3 and tk["muted"] not in named.values() and all(c in tk["series"] for c in named.values()),
              {"null": sorted(x for x in nulls if x), "named": named, "muted": tk["muted"]})
        if width == 1280:
            shot(page, f"colors-{'dark' if dark else 'light'}-1280", "#v")
        check(f"gap 6: {t}: colours: no page error", not page.errors, page.errors[:3])
        page.context.close()


def driver_fault_colour(browser, site):
    samples = rows(EX / DRIVER / "samples.json")
    values = {r["fault"] for r in samples if r.get("fault") is not None}
    for dark in (False, True):
        page, ok = open_case(browser, site, DRIVER, ["fault"], dark=dark)
        tk = tokens(page, "#example data-views")
        got = stable_items(page, panel("#example", "fault", ".dv-view-chart"))
        nulls = {hexc(it["fill"]) for it in got["items"] if it["type"] == "rect" and it["datum"] and "fault" in it["datum"] and it["datum"]["fault"] not in values}
        check(f"gap 6: driver, {'dark' if dark else 'light'}: the fault strip's no-fault spans (null cells) are muted",
              ok and nulls == {tk["muted"]}, {"null fills": sorted(x for x in nulls if x), "muted": tk["muted"]})
        page.context.close()


# ------------------------------------------------------------------------------------------------- gap 8: the rail
def rail(browser, site):
    for case, ds_key, dev_of, panel_key, col in ((DRIVER, "device", lambda r: [r["device"]], "iq", "i_q_a"), (SERVO, "devices", lambda r: r["devices"], "angle", "q_deg")):
        runs = rows(EX / case / "runs.json")
        samples = rows(EX / case / "samples.json")
        devices = sorted({d for r in runs for d in dev_of(r)})
        per = {d: sum(1 for r in runs if d in dev_of(r)) for d in devices}
        facets = (base_of(case).get("datasets") or {}).get("runs", {}).get("facets") or []
        run_facet = next((f for f in facets if isinstance(f, dict) and f.get("property") == "run"), {})
        check(f"gap 8: {case}: the Run facet is nested under the device facet (parent: {ds_key})", run_facet.get("parent") == ds_key, run_facet.get("parent"))
        page, ok = open_case(browser, site, case, ["playback", panel_key])
        first = max(runs, key=lambda r: r["started"])
        got = listed(page, "#example", "runs", ds_key)
        check(f"gap 8: {case}: with the newest run picked ({first['run']}), the device facet lists every device with its runs ({per})", ok and got == per, {"listed": got})
        for dev in [d for d in devices if d not in dev_of(first)] + [dev_of(first)[0]]:
            newest = max((r for r in runs if dev in dev_of(r)), key=lambda r: r["started"])["run"]
            pick(page, "#example", "runs", ds_key, dev)
            wait(page, "([root, v]) => { const i = document.querySelector(root); return JSON.stringify(document.querySelector('#example').state.rail.runs || '').includes(v); }", ["#example", newest])
            settle(page, 3)
            mine = [r for r in samples if r["run"] == newest and num(r.get(col))]
            sel = panel("#example", panel_key, ".dv-view-timeseries")
            until_series(page, sel, len(mine))
            n = page.evaluate("(s) => { const e = document.querySelector(s); return e && e.vegaView ? e.vegaView.data('series').length : null; }", sel)
            c = page.evaluate("() => { const c = document.querySelector('#example').clock; return [c.start, c.end]; }")
            ts = [r["t"] for r in samples if r["run"] == newest]
            check(f"gap 8: {case}: picking {dev} moves the run to its newest ({newest}): the Run radio checked, {panel_key} draws its {len(mine)} samples, the clock spans it",
                  checked(page, "#example", "runs", "run") == newest and checked(page, "#example", "runs", ds_key) == dev and n == len(mine) and c == [min(ts), max(ts)],
                  {"run": checked(page, "#example", "runs", "run"), "device": checked(page, "#example", "runs", ds_key), "samples": n, "clock": c})
            check(f"gap 8: {case}: with {dev} picked, the device facet still lists every device", listed(page, "#example", "runs", ds_key) == per, listed(page, "#example", "runs", ds_key))
        shot(page, f"rail-{case.removeprefix('robotics-')}-light-1280")
        check(f"gap 8: {case}: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- gap 9: empty text
EMPTY = """(sel) => [...document.querySelectorAll(sel)].map((e) => { const n = e.querySelector('.dv-media-none');
  return n && !n.hidden ? n.textContent.replace(/\\s+/g, ' ').trim() : null; })"""


def empties(browser, base, site):
    texts = {v["name"]: v.get("empty") for v in data_ui_base.loads((FIX / "empty.base").read_text(encoding="utf-8"))["views"]}
    for width, dark in ((1280, False), (390, True)):
        t = tag(width, dark)
        page = open_fixture(browser, base, width=width, dark=dark)
        for name in ("Depth", "Band", "Pair", "Generic"):
            page.evaluate(MOUNT_VIEWS, ["v", FIXURL + "empty.base", name])
            wait(page, "(s) => { const e = document.querySelector(s); return !!e && !!e.querySelector('.dv-media-none:not([hidden])'); }", "#v")
            settle(page, 2)
            got = (page.evaluate(EMPTY, "#v .dv-view") or [None])[0]
            want = texts[name] or "No rows match this view."
            check(f"gap 9: {t}: a {name} card with no row says {'its view' + chr(39) + 's own empty: text' if texts[name] else 'the generic sentence'} ({want!r})",
                  got is not None and got.endswith(want) and got.count(want) == 1, {"text": got})
        check(f"gap 9: {t}: no page error", not page.errors, page.errors[:3])
        page.context.close()
    # the camera template's depth and hyperspectral cards
    views = {v.get("name"): v for v in base_of(CAMERA).get("views") or []}
    d, b = views.get("Depth") or {}, views.get("Hyperspectral band") or {}
    check("gap 9: the camera template's Depth and Hyperspectral cards carry their none-captured text as empty:, not as an intro shown above data",
          isinstance(d.get("empty"), str) and isinstance(b.get("empty"), str) and "intro" not in d and "intro" not in b,
          {"Depth": {k: d.get(k) for k in ("empty", "intro")}, "Hyperspectral band": {k: b.get(k) for k in ("empty", "intro")}})
    page, ok = open_case(browser, site, CAMERA, ["depth", "band"])
    got = {k: page.evaluate(EMPTY, f"#example .dd-panel[data-panel='{k}'] .dv-view") for k in ("depth", "band")}
    want = {"depth": d.get("empty"), "band": b.get("empty")}
    check("gap 9: camera: the depth and hyperspectral cards say their own empty: text, once",
          ok and all(want[k] and got[k] and got[k][0] and got[k][0].endswith(want[k]) and page.evaluate(f"() => document.querySelector(\"#example .dd-panel[data-panel='{k}']\").textContent.split({json.dumps(want[k])}).length - 1") == 1 for k in want),
          {"drawn": got, "file": want})
    shot(page, "camera-empty-light-1280")
    check("gap 9: camera: no page error", not page.errors, page.errors[:3])
    page.context.close()


def main() -> int:
    if not (SITE / "index.html").exists() or not (ROOT / "dist" / "data-ui.js").exists():
        print("the kit and site are not built: npm --prefix ~/data-ui run build")
        return 1
    proc, base = serve(ROOT)
    sproc, site = serve(SITE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fn in (("gap 1: swaps", lambda: swaps(browser, base)), ("gap 1: the driver's box", lambda: driver_box(browser, site)),
                             ("gaps 2 and 7: marks", lambda: marks(browser, base)), ("gap 2: the driver's events", lambda: driver_marks(browser, base)),
                             ("gaps 2 and 7: the gripper", lambda: gripper(browser, site)), ("gap 3: the driver's clock", lambda: driver_clock(browser, site)),
                             ("gaps 3 and 5: the strip", lambda: strip_plain(browser, base)), ("gap 4: levels", lambda: levels(browser, base)),
                             ("gap 6: colours", lambda: colours(browser, base)), ("gap 6: the driver's fault strip", lambda: driver_fault_colour(browser, site)),
                             ("gap 8: the rail", lambda: rail(browser, site)), ("gap 9: empty text", lambda: empties(browser, base, site))):
                with guard(name):
                    fn()
            browser.close()
    finally:
        for p in (proc, sproc):
            p.terminate()
            p.wait(timeout=10)
    (OUT / "kit-gaps-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} kit gaps checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
