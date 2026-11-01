"""The interactive legend every data-ui chart draws (packages/core/src/legend.js; docs/CONTRACT.md §31), measured in
headless Chromium on the built site.

    ~/psu-atlas/.venv/bin/python tests/browser/legend_checks.py [OUT_DIR]     # after npm run build

Zach, 2026-10-28, on a sim2real card with 8 servo lines: "where there is a legend there is like no reason to not make
that legend interactive… ensure this feature is in data-ui charts by default." The 8-series fixture is the sim-to-real
case's own data: its `type: chart` "Model ladder (10-23 runs)" as views.base writes it (8 motors), and a variant
views.base (answered by page.route) that adds two time series cards over the case's real runs.json (x: run order,
y: full twin RMS, one series per motor): the simple Vega card and the interactive uPlot card. Nothing is synthetic.

Every claim is measured from what the card drew: Vega's scenegraph items per series and its y scale's domain, uPlot's
canvas pixels per series colour and its y scale, the button's aria-pressed and computed style, the URL. Serves dist/site on a
free 127.0.0.1 port, stops that server when done, writes OUT_DIR/legend-checks.json (default reports/media/legend) and
exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "legend"
OUT.mkdir(parents=True, exist_ok=True)
CASE = ROOT / "gallery" / "examples" / "sim-to-real"
checks: list[dict] = []
WAIT = 30000

RUNS = json.loads((CASE / "runs.json").read_text(encoding="utf-8"))["rows"]
MODELS = json.loads((CASE / "models.json").read_text(encoding="utf-8"))["rows"]
cell = lambda c: c["value"] if isinstance(c, dict) else c
MOTORS = sorted({r["motor"] for r in RUNS})
# the oracle for the y rescale: the motor whose full-twin RMS reaches highest, and the highest of the rest
twin = {m: [cell(r["full_twin"]) for r in RUNS if r["motor"] == m and isinstance(cell(r["full_twin"]), (int, float))] for m in MOTORS}
OUTLIER = max(MOTORS, key=lambda m: max(twin[m] or [float("-inf")]))
REST_MAX = max(max(v) for m, v in twin.items() if m != OUTLIER and v)
ALL_MAX = max(twin[OUTLIER])
LADDER = sorted({m["motor"] for m in MODELS if m["family"] != "friction"})

TS_VIEWS = """  - type: timeseries
    name: "Twin error by run · time series"
    from: runs
    timeseries: { x: order, y: full_twin, series: motor }
  - type: timeseries
    name: "Twin error by run · interactive"
    from: runs
    timeseries: { x: order, y: full_twin, series: motor, interactive: true }
"""
TS_PANELS = """    - { view: "Twin error by run · time series", key: ts8, w: 6, h: 3 }
    - { view: "Twin error by run · interactive", key: plot8, w: 6, h: 3 }
"""


def variant_base() -> str:
    """The case's views.base with the two time series cards placed first after the playback bar (real data)."""
    text = (CASE / "views.base").read_text(encoding="utf-8")
    anchor = "    - { view: Playback, w: 12 }\n"
    assert anchor in text and "\nviews:\n" in text
    text = text.replace(anchor, anchor + TS_PANELS, 1)
    return text.replace("\nviews:\n", "\nviews:\n" + TS_VIEWS, 1)


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def panel(key):
    return f"#example .dd-panel[data-panel='{key}']"


# Vega: scenegraph items per series (the legend's colour field), every mark but the legend's own invisible x/colour keeper
VEGA = """([sel, field]) => {
  const el = document.querySelector(sel + ' .dv-view');
  const v = el && el.vegaView;
  if (!v) return null;
  const n = {};
  const walk = (node, ghost) => {
    if (!node) return;
    if (node.marktype) {
      const g = ghost || /dv_legend_ghost/.test(node.name || '');
      for (const i of node.items || []) {
        if (!g && i.datum && i.datum[field] !== undefined && node.marktype !== 'group') { const k = String(i.datum[field]); n[k] = (n[k] || 0) + 1; }
        walk(i, g);
      }
    } else if (node.items) for (const i of node.items) walk(i, ghost);
  };
  walk(v.scenegraph().root, false);
  return { n, y: v.scale('y').domain(), x: v.scale('x').domain() };
}"""

# uPlot: canvas pixels near each series' own stroke colour inside the plot box, its scales and its series' show flags
UPLOT = """(sel) => {
  const el = document.querySelector(sel + ' .dv-view');
  const u = el && el.uplot;
  if (!u) return null;
  const hex = (c) => { const m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(c); if (m) return [+m[1], +m[2], +m[3]];
    const h = c.replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };
  const series = u.series.slice(1).map((s) => ({ label: s.label, show: s.show, rgb: hex(typeof s.stroke === 'function' ? s.stroke(u, 1) : s.stroke) }));
  const b = u.bbox, img = u.ctx.getImageData(b.left, b.top, b.width, b.height).data;
  const n = Object.fromEntries(series.map((s) => [s.label, 0]));
  for (let i = 0; i < img.length; i += 4) {
    if (img[i + 3] < 220) continue;
    for (const s of series) { const w = s.rgb; if (Math.abs(img[i] - w[0]) + Math.abs(img[i + 1] - w[1]) + Math.abs(img[i + 2] - w[2]) < 24) n[s.label]++; }
  }
  return { n, show: Object.fromEntries(series.map((s) => [s.label, s.show])), rgb: Object.fromEntries(series.map((s) => [s.label, s.rgb.join(',')])),
           y: [u.scales.y.min, u.scales.y.max], x: [u.scales.x.min, u.scales.x.max] };
}"""

KEYS = """(sel) => [...document.querySelectorAll(sel + ' .dv-legend-key')].map((b) => { const cs = getComputedStyle(b);
  return { name: b.dataset.legendSeries, tag: b.tagName, type: b.type, pressed: b.getAttribute('aria-pressed'),
           strike: cs.textDecorationLine, opacity: Number(cs.opacity) }; })"""
RESET = """(sel) => { const r = document.querySelector(sel + ' .dv-legend-reset'); if (!r) return null; const b = r.getBoundingClientRect();
  return { hidden: r.hidden, w: b.width, h: b.height, text: r.textContent.trim() }; }"""
STATUS = """(sel) => (document.querySelector(sel + ' data-views .dv-status') || {}).textContent || ''"""


def rgb(text):
    """'#rrggbb' or 'rgb(r, g, b)' -> (r, g, b)."""
    m = re.findall(r"\d+", text) if text.startswith("rgb") else None
    return tuple(int(x) for x in m[:3]) if m else tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def settle(page, n=3):
    page.evaluate(f"() => new Promise((r) => {{ let k = {n}; const f = () => (--k ? requestAnimationFrame(f) : setTimeout(r, 60)); requestAnimationFrame(f); }})")


def key_btn(page, sel, name):
    return page.locator(f"{sel} .dv-legend-key[data-legend-series={json.dumps(name)}]")


def hidden_in_url(page, param):
    h = page.evaluate("location.hash.slice(1)")
    v = urllib.parse.parse_qs(h, keep_blank_values=True).get(param)
    if not v:
        return []
    return [urllib.parse.unquote(x) for x in v[0].split(",") if x != ""]


def drawn(m, kind):
    """{series: count drawn} from a measurement. uPlot: a hidden series (show false) is not drawn (uPlot draws only shown
    series); its pixel count is the measure only when no other series shares its colour (seriesColor's slots can
    collide), else it is the shown flag (1 or 0)."""
    if not m:
        return {}
    if kind == "vega":
        return m["n"]
    rgb = m["rgb"]
    unique = {k for k, c in rgb.items() if list(rgb.values()).count(c) == 1}
    # a few stray px of a neighbour's antialiased edge are not a drawn series
    return {k: ((v if v > 3 else 0) if k in unique else int(bool(m["show"][k]))) for k, v in m["n"].items()}


def measure(page, sel, kind, field="series"):
    return page.evaluate(VEGA, [sel, field]) if kind == "vega" else page.evaluate(UPLOT, sel)


def card_checks(page, sel, kind, label, names, field="series", outlier=None, url_param=None):
    """One card's legend, end to end: buttons, toggle, isolate (double-click and Alt + click), the y rescale, Reset."""
    page.locator(sel).scroll_into_view_if_needed()
    settle(page)
    keys = page.evaluate(KEYS, sel)
    check(f"{label}: one <button type=button aria-pressed=true> per series ({len(names)})",
          sorted(k["name"] for k in keys) == sorted(names) and all(k["tag"] == "BUTTON" and k["type"] == "button" and k["pressed"] == "true" for k in keys), keys)
    names = [k["name"] for k in keys]   # the legend's own order from here on
    reset = page.evaluate(RESET, sel)
    check(f"{label}: no Reset while everything shows", reset is not None and reset["hidden"] and reset["w"] == 0, reset)
    full = measure(page, sel, kind, field)
    base_n = drawn(full, kind)
    check(f"{label}: every series draws before any click", full is not None and all(base_n.get(n, 0) > 0 for n in names), base_n)
    status0 = page.evaluate(STATUS, sel)
    target = outlier or names[0]
    other = next(n for n in names if n != target)

    # click hides exactly that series; the rest draw as before
    key_btn(page, sel, target).click()
    settle(page)
    m = measure(page, sel, kind, field)
    n = drawn(m, kind)
    k = {x["name"]: x for x in page.evaluate(KEYS, sel)}
    if kind == "vega":
        same_rest = all(n.get(x, 0) == base_n[x] for x in names if x != target)
        gone = n.get(target, 0) == 0
    else:
        same_rest = all(n.get(x, 0) > 0 for x in names if x != target)
        gone = n.get(target, 0) == 0 and m["show"][target] is False
    check(f"{label}: a click on {target!r} removes exactly its marks; every other series still draws", gone and same_rest, {"before": base_n, "after": n})
    check(f"{label}: the hidden entry reads aria-pressed=false, greyed and struck through",
          k[target]["pressed"] == "false" and "line-through" in k[target]["strike"] and k[target]["opacity"] < 0.9 and k[other]["pressed"] == "true" and "line-through" not in k[other]["strike"], k[target])
    reset = page.evaluate(RESET, sel)
    check(f"{label}: Reset appears beside the legend while a series is hidden", reset and not reset["hidden"] and reset["w"] > 0 and reset["text"] == "Reset", reset)
    check(f"{label}: the status line is the data's, unchanged by hiding", page.evaluate(STATUS, sel) == status0, [status0, page.evaluate(STATUS, sel)])
    check(f"{label}: x stays put when a series is hidden", m["x"] == full["x"], {"before": full["x"], "after": m["x"]})
    if url_param:
        check(f"{label}: the hidden set is in the URL ({url_param}=)", hidden_in_url(page, url_param) == [target], page.evaluate("location.hash"))
    y_hidden = m["y"]

    # again: shown again, exactly as before
    key_btn(page, sel, target).click()
    settle(page)
    m = measure(page, sel, kind, field)
    check(f"{label}: a second click draws {target!r} again and the y domain is the full one again",
          all(drawn(m, kind).get(x, 0) > 0 for x in names) and m["y"] == full["y"], {"n": drawn(m, kind), "y": m["y"], "full y": full["y"]})
    if url_param:
        check(f"{label}: all shown again: the URL has no {url_param}=", hidden_in_url(page, url_param) == [], page.evaluate("location.hash"))

    # double-click isolates; again restores all
    key_btn(page, sel, other).dblclick()
    settle(page)
    m = measure(page, sel, kind, field)
    n = drawn(m, kind)
    keys = page.evaluate(KEYS, sel)
    check(f"{label}: a double-click on {other!r} shows only it (net isolate, no toggle left behind)",
          n.get(other, 0) > 0 and all(n.get(x, 0) == 0 for x in names if x != other)
          and [x["pressed"] for x in keys] == ["true" if x["name"] == other else "false" for x in keys], {"n": n, "pressed": [x["pressed"] for x in keys]})
    key_btn(page, sel, other).dblclick()
    settle(page)
    m = measure(page, sel, kind, field)
    check(f"{label}: a double-click on the isolated one shows every series again",
          all(drawn(m, kind).get(x, 0) > 0 for x in names) and all(x["pressed"] == "true" for x in page.evaluate(KEYS, sel)) and m["y"] == full["y"], drawn(m, kind))

    # Alt + click isolates; again restores all
    key_btn(page, sel, other).click(modifiers=["Alt"])
    settle(page)
    n = drawn(measure(page, sel, kind, field), kind)
    check(f"{label}: Alt + click on {other!r} shows only it", n.get(other, 0) > 0 and all(n.get(x, 0) == 0 for x in names if x != other), n)
    key_btn(page, sel, other).click(modifiers=["Alt"])
    settle(page)
    n = drawn(measure(page, sel, kind, field), kind)
    check(f"{label}: Alt + click on the isolated one shows every series again", all(n.get(x, 0) > 0 for x in names), n)

    # the y axis rescales to the visible series; Reset restores the full domain
    key_btn(page, sel, target).click()
    settle(page)
    m = measure(page, sel, kind, field)
    return {"full": full, "hidden_y": y_hidden, "m": m, "target": target, "names": names}


def reset_checks(page, sel, label, kind, field, full):
    page.locator(f"{sel} .dv-legend-reset").click()
    settle(page)
    m = measure(page, sel, kind, field)
    keys = page.evaluate(KEYS, sel)
    check(f"{label}: Reset shows every series and the full y domain again, and hides itself",
          all(k["pressed"] == "true" for k in keys) and m["y"] == full["y"] and page.evaluate(RESET, sel)["hidden"], {"y": m["y"], "full": full["y"]})


def keyboard_checks(page, sel, label, kind, field):
    """Tab reaches each entry in order; Enter and Space toggle (native buttons); the focus ring is visible."""
    names = [k["name"] for k in page.evaluate(KEYS, sel)]
    first = key_btn(page, sel, names[0])
    first.scroll_into_view_if_needed()
    # focus the element just before the legend in tab order, then Tab into it
    page.evaluate("""(sel) => { const b = document.querySelector(sel + ' .dv-legend-key');
      const all = [...document.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((e) => e.offsetParent !== null && !e.hidden && e.tabIndex >= 0);
      const i = all.indexOf(b); (i > 0 ? all[i - 1] : document.body).focus(); }""", sel)
    reached = []
    for _ in range(len(names)):
        page.keyboard.press("Tab")
        reached.append(page.evaluate("() => document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.legendSeries || null : null"))
    check(f"{label}: Tab reaches each entry in order", reached == names, reached)
    first.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    ring = page.evaluate("() => { const cs = getComputedStyle(document.activeElement); return { name: document.activeElement.dataset.legendSeries, style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), visible: document.activeElement.matches(':focus-visible') }; }")
    check(f"{label}: the focused entry shows a focus ring", ring["name"] == names[0] and ring["visible"] and ring["style"] != "none" and ring["width"] >= 1, ring)
    before = drawn(measure(page, sel, kind, field), kind)
    page.keyboard.press("Enter")
    settle(page)
    k = page.evaluate(KEYS, sel)[0]
    after = drawn(measure(page, sel, kind, field), kind)
    off = after.get(names[0], 0) == 0
    check(f"{label}: Enter on the focused entry hides it (aria-pressed false, its marks gone)", k["pressed"] == "false" and off, {"pressed": k["pressed"], "n": after.get(names[0])})
    page.keyboard.press("Space")
    settle(page)
    k = page.evaluate(KEYS, sel)[0]
    back = drawn(measure(page, sel, kind, field), kind)
    check(f"{label}: Space shows it again (aria-pressed true, its marks back)", k["pressed"] == "true" and back.get(names[0], 0) > 0, {"pressed": k["pressed"], "n": back.get(names[0])})


def dashboard_page(browser, base, routes, hash_=""):
    context = browser.new_context(viewport={"width": 1440, "height": 1300})
    def answer(body):
        return lambda route: route.fulfill(status=200, body=body, content_type="text/plain")
    for pattern, body in routes.items():
        context.route(pattern, answer(body))
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(f"{base}/gallery/sim-to-real/{hash_}")
    ready(page)
    return page


def ready(page):
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length && els.every((e) => e.dataset.view); }""", timeout=WAIT)
    page.wait_for_function("""() => ['ts8', 'plot8'].every((k) => { const s = document.querySelector(`#example .dd-panel[data-panel="${k}"] .dv-view`);
      return !document.querySelector(`#example .dd-panel[data-panel="${k}"]`) || (s && (s.vegaView || s.uplot)); })""", timeout=WAIT)
    page.wait_for_function("() => [...document.querySelectorAll('#example .dd-panel[data-type=chart] .dv-view')].every((v) => v.vegaView)", timeout=WAIT)
    settle(page, 4)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        routes = {f"{base}/gallery/sim-to-real/views.base": variant_base()}
        check("fixture: sim-to-real's runs.json has 8 motors (the 8-servo card), and the ladder chart 8", len(MOTORS) == 8 and len(LADDER) == 8, {"runs": MOTORS, "ladder": LADDER})
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = dashboard_page(browser, base, routes)
            ladder = page.evaluate("() => [...document.querySelectorAll('#example .dd-panel')].find((s) => /Model ladder/.test(s.getAttribute('aria-label') || '')).dataset.panel")

            # ---- the simple time series card (Vega): 8 servo series
            with guard("time series card (8 motors)"):
                sel = panel("ts8")
                r = card_checks(page, sel, "vega", "time series card", MOTORS, "series", OUTLIER, "l.ts8")
                check("time series card: hiding the outlier shrinks the y domain to the visible series (an outlier must not flatten the rest)",
                      r["m"]["y"][1] < r["full"]["y"][1] and r["m"]["y"][1] >= REST_MAX - 1e-9 and r["full"]["y"][1] >= ALL_MAX - 1e-9, {"full": r["full"]["y"], "hidden": r["m"]["y"], "rest max": REST_MAX, "all max": ALL_MAX})
                page.locator(sel).screenshot(path=str(OUT / "ts-one-hidden.png"))
                reset_checks(page, sel, "time series card", "vega", "series", r["full"])
                keyboard_checks(page, sel, "time series card", "vega", "series")

            # ---- the interactive card (uPlot): the same 8 series
            with guard("interactive time series card (8 motors)"):
                sel = panel("plot8")
                r = card_checks(page, sel, "uplot", "interactive card", MOTORS, "series", OUTLIER, "l.plot8")
                check("interactive card: hiding the outlier shrinks the y range to the visible series",
                      r["m"]["y"][1] < r["full"]["y"][1] and r["m"]["y"][1] >= REST_MAX - 1e-9, {"full": r["full"]["y"], "hidden": r["m"]["y"], "rest max": REST_MAX})
                reset_checks(page, sel, "interactive card", "uplot", "series", r["full"])
                keyboard_checks(page, sel, "interactive card", "uplot", "series")

            # ---- type: chart (Vega-Lite): the case's own Model ladder, x model, y error (log), colour motor
            with guard("type: chart (Model ladder)"):
                sel = panel(ladder)
                vega_legend = page.evaluate("(sel) => { const v = document.querySelector(sel + ' .dv-view').vegaView; const out = []; const walk = (n) => { if (!n) return; if (n.marktype === 'group' && /legend/.test(n.role || '')) out.push(n.role); for (const i of n.items || []) walk(i); }; walk(v.scenegraph().root); return out.length; }", sel)
                check("type: chart: Vega's own colour legend is not drawn (the HTML button legend replaces it)", vega_legend == 0, vega_legend)
                lad_err = {m: [cell(x["error"]) for x in MODELS if x["motor"] == m and x["family"] != "friction"] for m in LADDER}
                top = max(LADDER, key=lambda m: max(lad_err[m]))
                r = card_checks(page, sel, "vega", "type: chart", LADDER, "motor", top, f"l.{ladder}")
                rest = max(max(v) for m, v in lad_err.items() if m != top)
                check("type: chart: hiding the motor with the largest error keeps a y domain that holds every visible value",
                      r["m"]["y"][1] >= rest - 1e-9 and r["m"]["y"][0] <= min(min(v) for m, v in lad_err.items() if m != top) + 1e-9, {"full": r["full"]["y"], "hidden": r["m"]["y"], "rest max": rest})
                # WHY isolate the lowest: y is log with nice decades, so one series off the top can land on the same decade;
                # a motor whose errors stay low shows the rescale in the scale's own domain
                low = min(LADDER, key=lambda m: max(lad_err[m]))
                page.locator(f"{sel} .dv-legend-reset").click()
                settle(page)
                key_btn(page, sel, low).click(modifiers=["Alt"])
                settle(page)
                iso = measure(page, sel, "vega", "motor")
                check(f"type: chart: isolating {low!r} shrinks the y domain to its own values (measured from the scale), x stays",
                      iso["y"][1] < r["full"]["y"][1] and iso["y"][1] >= max(lad_err[low]) - 1e-9 and iso["y"][0] <= min(lad_err[low]) + 1e-9 and iso["x"] == r["full"]["x"],
                      {"full": r["full"]["y"], "isolated": iso["y"], "its range": [min(lad_err[low]), max(lad_err[low])], "x same": iso["x"] == r["full"]["x"]})
                key_btn(page, sel, low).click(modifiers=["Alt"])
                settle(page)
                key_btn(page, sel, top).click()
                settle(page)
                colors = page.evaluate("(sel) => { const v = document.querySelector(sel + ' .dv-view').vegaView; const s = v.scale('color'); return s.domain().map((d) => [String(d), s(d)]); }", sel)
                swatch = page.evaluate("(sel) => [...document.querySelectorAll(sel + ' .dv-legend-key')].map((b) => [b.dataset.legendSeries, getComputedStyle(b.querySelector('i')).getPropertyValue('--dv-ts-c').trim()])", sel)
                check("type: chart: a hidden motor keeps the colour scale (no colour shifts), and every swatch is its series' drawn colour",
                      sorted(c[0] for c in colors) == LADDER and [s[0] for s in swatch] == [c[0] for c in colors] and all(rgb(s[1]) == rgb(c[1]) for s, c in zip(swatch, colors)), {"scale": colors, "swatches": swatch})
                page.locator(sel).screenshot(path=str(OUT / "chart-one-hidden.png"))
                reset_checks(page, sel, "type: chart", "vega", "motor", r["full"])
                keyboard_checks(page, sel, "type: chart", "vega", "motor")

            # ---- URL: written, a reload keeps it, Back / Forward restore it (the dashboard's hashchange / popstate)
            with guard("dashboard URL"):
                sel = panel("ts8")
                key_btn(page, sel, OUTLIER).click()
                settle(page)
                url = page.url
                check("URL: hiding a series writes l.<panel>= (its name URI-encoded)", hidden_in_url(page, "l.ts8") == [OUTLIER] and "l.ts8=" in url, url)
                page.reload()
                ready(page)
                n = drawn(measure(page, sel, "vega"), "vega")
                check("URL: a reload keeps it hidden (pressed false, no marks), the others drawn",
                      n.get(OUTLIER, 0) == 0 and all(n.get(m, 0) > 0 for m in MOTORS if m != OUTLIER) and key_btn(page, sel, OUTLIER).get_attribute("aria-pressed") == "false", n)
                two = [m for m in MOTORS if m != OUTLIER][:2]
                enc = ",".join(urllib.parse.quote(m, safe="") for m in two)
                page.evaluate("(v) => { const h = new URLSearchParams(location.hash.slice(1)); h.set('l.ts8', v); location.hash = h.toString(); }", enc)
                settle(page, 4)
                n = drawn(measure(page, sel, "vega"), "vega")
                check("URL: a new hash (a navigation) applies its hidden set", all(n.get(m, 0) == 0 for m in two) and n.get(OUTLIER, 0) > 0, n)
                page.go_back()
                settle(page, 4)
                n = drawn(measure(page, sel, "vega"), "vega")
                check("URL: Back restores the previous hidden set", n.get(OUTLIER, 0) == 0 and all(n.get(m, 0) > 0 for m in two), n)
                page.go_forward()
                settle(page, 4)
                n = drawn(measure(page, sel, "vega"), "vega")
                check("URL: Forward restores the next one", all(n.get(m, 0) == 0 for m in two) and n.get(OUTLIER, 0) > 0, n)
                check("dashboard: no page error", not page.errors, page.errors[:3])
            page.context.close()

            # ---- a standalone <data-views> (the actuator-charts case): l= in its own hash
            with guard("standalone <data-views>"):
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.errors = []
                page.on("pageerror", lambda e: page.errors.append(str(e)))
                page.goto(f"{base}/gallery/actuator-charts/")
                page.wait_for_function("() => { const v = document.querySelector('#example .dv-view-chart'); return v && v.vegaView; }", timeout=WAIT)
                settle(page, 4)
                sel = "#example"
                names = [k["name"] for k in page.evaluate(KEYS, sel)]
                check("<data-views>: the chart draws a button legend", len(names) >= 3, names)
                field = page.evaluate("() => { const v = document.querySelector('#example .dv-view-chart').vegaView; const f = Object.keys(v.data('rows')[0] || {}).find((k) => k === 'brand'); return f || null; }")
                before = drawn(measure(page, sel, "vega", field), "vega")
                name = names[1]
                key_btn(page, sel, name).click()
                settle(page)
                after = drawn(measure(page, sel, "vega", field), "vega")
                check("<data-views>: a click hides exactly that brand's dots", after.get(name, 0) == 0 and before.get(name, 0) > 0 and all(after.get(k, 0) == v for k, v in before.items() if k != name), {"before": before, "after": after})
                check("<data-views>: its hash says l=<name>", hidden_in_url(page, "l") == [name], page.evaluate("location.hash"))
                page.reload()
                page.wait_for_function("() => { const v = document.querySelector('#example .dv-view-chart'); return v && v.vegaView; }", timeout=WAIT)
                settle(page, 4)
                after = drawn(measure(page, sel, "vega", field), "vega")
                check("<data-views>: a reload keeps it hidden", after.get(name, 0) == 0 and key_btn(page, sel, name).get_attribute("aria-pressed") == "false", after)
                page.evaluate("(v) => { const h = new URLSearchParams(location.hash.slice(1)); h.set('l', v); location.hash = h.toString(); }", urllib.parse.quote(names[2], safe=""))
                settle(page, 4)
                after = drawn(measure(page, sel, "vega", field), "vega")
                check("<data-views>: a navigated hash applies its l=", after.get(names[2], 0) == 0 and after.get(name, 0) > 0, after)
                page.go_back()
                settle(page, 4)
                after = drawn(measure(page, sel, "vega", field), "vega")
                check("<data-views>: Back restores the previous l=", after.get(name, 0) == 0 and after.get(names[2], 0) > 0, after)
                check("<data-views>: no page error", not page.errors, page.errors[:3])
                context.close()

            # ---- trajectory, scene3d (dashboard-cards) and the playback range's overview (playback-proposals)
            with guard("trajectory and scene3d"):
                context = browser.new_context(viewport={"width": 1440, "height": 1300})
                page = context.new_page()
                page.goto(f"{base}/gallery/dashboard-cards/")
                page.wait_for_function("() => document.querySelector(\"#example .dd-panel[data-panel='tool-path-xz'] .dv-view\")?.vegaView", timeout=WAIT)
                sel = panel("tool-path-xz")
                page.locator(sel).scroll_into_view_if_needed()
                settle(page, 4)
                names = [k["name"] for k in page.evaluate(KEYS, sel)]
                before = drawn(measure(page, sel, "vega", "series"), "vega")
                hide = next(n for n in names if n != "target")
                key_btn(page, sel, hide).click()
                settle(page, 4)
                after = drawn(measure(page, sel, "vega", "series"), "vega")
                marker = page.evaluate("([sel, n]) => { const m = [...document.querySelectorAll(sel + ' [data-marker]')].find((e) => e.dataset.series === n); return m ? getComputedStyle(m).display : null; }", [sel, hide])
                check("trajectory: a click hides that path's marks and its marker; the others draw as before",
                      len(names) >= 2 and before.get(hide, 0) > 0 and after.get(hide, 0) == 0 and all(after.get(k, 0) == v for k, v in before.items() if k != hide) and marker == "none", {"before": before, "after": after, "marker": marker})
                sel = panel("tool-path-3d")
                page.locator(sel).scroll_into_view_if_needed()
                page.wait_for_function("(sel) => { const r = document.querySelector(sel + ' .dv-scene3d'); return r && r.scene3d && Object.keys(r.scene3d.markers()).length; }", arg=sel, timeout=WAIT)
                names = [k["name"] for k in page.evaluate(KEYS, sel)]
                seen0 = page.evaluate("(sel) => Object.keys(document.querySelector(sel + ' .dv-scene3d').scene3d.visible())", sel)
                hide = names[-1]
                key_btn(page, sel, hide).click()
                settle(page, 4)
                seen = page.evaluate("(sel) => Object.keys(document.querySelector(sel + ' .dv-scene3d').scene3d.visible())", sel)
                check("scene3d: a click hides that series' path, marker and robot in the scene; the others stay",
                      len(names) >= 2 and sorted(seen0) == sorted(names) and sorted(seen) == sorted(n for n in names if n != hide), {"before": seen0, "after": seen})
                context.close()
            with guard("playback range overview"):
                context = browser.new_context(viewport={"width": 1440, "height": 1300})
                page = context.new_page()
                page.goto(f"{base}/gallery/playback-proposals/")
                sel = panel("range")
                page.wait_for_function("(sel) => document.querySelectorAll(sel + ' .dv-rg-spark path').length > 0", arg=sel, timeout=WAIT)
                page.locator(sel).scroll_into_view_if_needed()
                names = [k["name"] for k in page.evaluate(KEYS, sel)]
                paths = lambda: page.evaluate("(sel) => [...document.querySelectorAll(sel + ' .dv-rg-spark path')].map((p) => p.dataset.series)", sel)
                p0 = paths()
                key_btn(page, sel, names[0]).click()
                settle(page)
                p1 = paths()
                check("range overview: a click removes that line from the overview; the rest stay", len(names) >= 2 and sorted(p0) == sorted(names) and sorted(p1) == sorted(names[1:]), {"before": p0, "after": p1})
                context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "legend-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} legend checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
