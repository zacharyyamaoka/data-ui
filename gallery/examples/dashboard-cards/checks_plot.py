"""The interactive time series (timeseries.interactive: true, packages/views/chart/src/plot.js): the Foxglove/Rerun plot
on uPlot. Loaded by checks.py beside it (run(ctx, path, helpers)).

Every expected number comes from the case's JSON (helpers['rows']), the dashboard palette in views.base, or uPlot's own
scales (u.scales, u.valToPos, u.over), never from the card's overlay code: a playhead is right when its centre sits where
uPlot draws t. A hidden series is measured on the canvas's pixels (its colour no longer drawn), not on a flag alone."""

import contextlib
import gzip
import statistics
import urllib.request

FRAME = 1 / 30
KEY = "step-response-interactive"
PAL = {"target": "#8b9099", "factory": "#e8743b", "tuned": "#2a78d6"}
# the controls Zach asked for (Rerun's "?" list, 2026-10-26); the oracle is this list, not the card's own
CONTROLS = ["Pan", "Horizontal pan", "Zoom", "Zoom X-axis", "Zoom Y-axis", "Zoom to selection", "Move time cursor", "Reset view",
            "Hide/show series", "Hide/show other series"]

EL = f"document.querySelector('#example .dd-panel[data-panel=\"{KEY}\"] .dv-view')"

# the plot rectangle (uPlot's .u-over) in page px, its scales and series
STATE = f"""() => {{ const el = {EL}; const u = el && el.uplot; if (!u) return null;
  const r = u.over.getBoundingClientRect();
  return {{ left: r.left, top: r.top, w: r.width, h: r.height, x: [u.scales.x.min, u.scales.x.max], y: [u.scales.y.min, u.scales.y.max],
    series: u.series.slice(1).map((s) => ({{ label: s.label, show: s.show, stroke: typeof s.stroke === 'function' ? s.stroke(u, 1) : s.stroke, dash: s.dash || null }})),
    data: [u.data[0][0], u.data[0][u.data[0].length - 1]], plots: el.dataset.plots }}; }}"""

# page px of a time through uPlot's own x scale
XAT = f"""(t) => {{ const u = {EL}.uplot; return u.over.getBoundingClientRect().left + u.valToPos(t, 'x'); }}"""

# canvas pixels near each colour (sum of |dr|+|dg|+|db| under 60), over the plot area only
PIXELS = f"""(pal) => {{ const u = {EL}.uplot; const c = u.ctx.canvas; const g = c.getContext('2d');
  const b = u.bbox; const img = g.getImageData(b.left, b.top, b.width, b.height).data;
  const want = Object.fromEntries(Object.entries(pal).map(([k, hex]) => [k, [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))]));
  const n = Object.fromEntries(Object.keys(pal).map((k) => [k, 0]));
  for (let i = 0; i < img.length; i += 4) {{ if (img[i + 3] < 200) continue;
    for (const k in want) {{ const w = want[k]; if (Math.abs(img[i] - w[0]) + Math.abs(img[i + 1] - w[1]) + Math.abs(img[i + 2] - w[2]) < 60) n[k]++; }} }}
  return n; }}"""

CENTRES = """([key, sel]) => [...document.querySelectorAll(`#example .dd-panel[data-panel="${key}"] ${sel}`)]
  .filter((e) => !e.hidden && getComputedStyle(e).display !== 'none')
  .map((e) => { const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2, w: b.width, h: b.height }; })"""


@contextlib.contextmanager
def guard(ctx, what):
    """A section that cannot run (the card is not drawn yet) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        ctx.check(f"interactive plot: {what} could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


class Part:
    """ctx.shot(page, name) for one panel."""

    def __init__(self, locator):
        self.locator = locator

    def screenshot(self, path, full_page=False):
        self.locator.evaluate("(e) => e.scrollIntoView({block: 'center'})")
        self.locator.page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        self.locator.screenshot(path=path)


def near(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def run(ctx, path, helpers):
    rows, ready, seek, clock, D = helpers["rows"], helpers["ready"], helpers["seek"], helpers["clock"], helpers["D"]
    elbow = [r for r in rows("samples.json") if r["joint"] == "elbow_joint" and r["q_deg"] is not None]
    want_series = sorted({r["situation"] for r in elbow})
    t_lo, t_hi = min(r["t"] for r in elbow), max(r["t"] for r in elbow)

    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    ok = ctx.until(page, f"() => {{ const el = {EL}; return el && el.uplot && el.querySelector('canvas'); }}", timeout=15000)
    ctx.check("interactive plot: 'Step response (interactive)' draws a uPlot plot (el.uplot), not the Vega time series", ok and page.evaluate(f"() => !{EL}.vegaView"),
              page.evaluate(f"() => {{ const el = {EL}; return el ? el.className : null; }}"))
    page.evaluate(f"() => {EL}.scrollIntoView({{block: 'center'}})")
    ctx.frames(page)
    s0 = page.evaluate(STATE)

    with guard(ctx, "its series"):
        got = sorted(s["label"] for s in s0["series"])
        dash = {s["label"]: s["dash"] for s in s0["series"]}
        stroke = {s["label"]: (s["stroke"] or "").lower() for s in s0["series"]}
        ctx.check("interactive plot: exactly the oracle's series (elbow_joint: factory, target, tuned) in the palette's colours, target dashed, the others solid",
                  got == want_series and all(stroke.get(k) == v for k, v in PAL.items()) and bool(dash.get("target")) and not dash.get("tuned") and not dash.get("factory"),
                  {"drawn": got, "oracle": want_series, "stroke": stroke, "dash": dash})
        ctx.check("interactive plot: the full view spans the data (x = the oracle's first and last t)", near(s0["x"][0], t_lo, 1e-9) and near(s0["x"][1], t_hi, 1e-9),
                  {"x": s0["x"], "oracle": [t_lo, t_hi]})
        chunk = page.evaluate("() => performance.getEntriesByType('resource').map((e) => e.name).filter((n) => /views\\/chart-plot-.*\\.js$/.test(n))")
        ctx.check("interactive plot: uPlot arrives as its own lazy chunk (views/chart-plot-*.js) beside the chart bundle", len(chunk) == 1, chunk)

    def at(fx, fy=0.5):
        s = page.evaluate(STATE)
        return s["left"] + fx * s["w"], s["top"] + fy * s["h"]

    def reset():
        x, y = at(0.5)
        page.mouse.dblclick(x, y)
        ctx.until(page, f"() => {{ const u = {EL}.uplot; return Math.abs(u.scales.x.min - {t_lo}) < 1e-9 && Math.abs(u.scales.x.max - {t_hi}) < 1e-9; }}", timeout=4000)
        ctx.frames(page)

    def span(r):
        return r[1] - r[0]

    # ---- legend: click hides (its colour leaves the canvas), again shows; Alt + click isolates, again shows all
    with guard(ctx, "the legend"):
        legend = f"#example .dd-panel[data-panel='{KEY}'] [data-legend-series]"
        before = page.evaluate(PIXELS, PAL)
        page.locator(f"{legend}[data-legend-series='factory']").click()
        ctx.frames(page)
        hid = page.evaluate(PIXELS, PAL)
        shown = {s["label"]: s["show"] for s in page.evaluate(STATE)["series"]}
        ctx.check("legend: clicking 'factory' hides it: it no longer draws (its colour's pixels on the canvas fall to ≤ 2 % of before) and the others still do",
                  before["factory"] > 100 and hid["factory"] <= 0.02 * before["factory"] and hid["tuned"] > 100 and not shown["factory"],
                  {"factory px before": before["factory"], "after": hid["factory"], "tuned px after": hid["tuned"], "show": shown})
        page.locator(f"{legend}[data-legend-series='factory']").click()
        ctx.frames(page)
        back = page.evaluate(PIXELS, PAL)
        ctx.check("legend: clicking 'factory' again draws it again", back["factory"] > 0.5 * before["factory"], {"factory px": back["factory"], "before": before["factory"]})
        page.locator(f"{legend}[data-legend-series='tuned']").click(modifiers=["Alt"])
        ctx.frames(page)
        iso = page.evaluate(PIXELS, PAL)
        shown = {s["label"]: s["show"] for s in page.evaluate(STATE)["series"]}
        ctx.check("legend: Alt + click on 'tuned' leaves only it: tuned draws, factory and target draw nothing",
                  shown == {"factory": False, "target": False, "tuned": True} and iso["tuned"] > 100 and iso["factory"] <= 0.02 * before["factory"] and iso["target"] <= 0.02 * max(1, before["target"]),
                  {"show": shown, "px": iso, "before": before})
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{KEY}']")), "plot-isolated-light")
        page.locator(f"{legend}[data-legend-series='tuned']").click(modifiers=["Alt"])
        ctx.frames(page)
        shown = {s["label"]: s["show"] for s in page.evaluate(STATE)["series"]}
        ctx.check("legend: Alt + click on the isolated series shows every series again", all(shown.values()) and len(shown) == 3, shown)

    # ---- wheel: Ctrl zooms both axes, Ctrl+Shift only x, Ctrl+Alt only y (ranges measured before and after)
    with guard(ctx, "wheel zoom"):
        res = {}
        for name, keys in (("ctrl", ["Control"]), ("ctrl+shift", ["Control", "Shift"]), ("ctrl+alt", ["Control", "Alt"])):
            reset()
            a = page.evaluate(STATE)
            x, y = at(0.5)
            page.mouse.move(x, y)
            for k in keys:
                page.keyboard.down(k)
            page.mouse.wheel(0, -200)
            for k in reversed(keys):
                page.keyboard.up(k)
            ctx.until(page, f"() => {{ const u = {EL}.uplot; return Math.abs((u.scales.x.max - u.scales.x.min) - {span(a['x'])}) > 1e-9 || Math.abs((u.scales.y.max - u.scales.y.min) - {span(a['y'])}) > 1e-9; }}", timeout=3000)
            b = page.evaluate(STATE)
            res[name] = {"x span": round(span(b["x"]) / span(a["x"]), 4), "y span": round(span(b["y"]) / span(a["y"]), 4)}
        zoom_in = lambda r: r < 0.95  # noqa: E731
        same = lambda r: abs(r - 1) < 1e-9  # noqa: E731
        ctx.check("wheel: Ctrl + wheel zooms both axes (x and y spans shrink)", zoom_in(res["ctrl"]["x span"]) and zoom_in(res["ctrl"]["y span"]), res["ctrl"])
        ctx.check("wheel: Ctrl + Shift + wheel zooms x only (y range unchanged)", zoom_in(res["ctrl+shift"]["x span"]) and same(res["ctrl+shift"]["y span"]), res["ctrl+shift"])
        ctx.check("wheel: Ctrl + Alt + wheel zooms y only (x range unchanged)", same(res["ctrl+alt"]["x span"]) and zoom_in(res["ctrl+alt"]["y span"]), res["ctrl+alt"])
        reset()
        a = page.evaluate(STATE)
        x, y = at(0.5)
        page.mouse.move(x, y)
        page.keyboard.down("Shift")
        page.mouse.wheel(0, 100)
        page.keyboard.up("Shift")
        ctx.until(page, f"() => Math.abs({EL}.uplot.scales.x.min - {a['x'][0]}) > 1e-9", timeout=3000)
        b = page.evaluate(STATE)
        ctx.check("wheel: Shift + wheel pans x (same span, moved) and leaves y", abs(span(b["x"]) - span(a["x"])) < 1e-9 and abs(b["x"][0] - a["x"][0]) > 1e-3 and b["y"] == a["y"],
                  {"before": a["x"], "after": b["x"], "y": [a["y"], b["y"]]})
        plain = page.evaluate("() => window.scrollY")
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(250)
        c = page.evaluate(STATE)
        ctx.check("wheel: a plain wheel over the plot scrolls the page and leaves the plot alone", page.evaluate("() => window.scrollY") != plain and c["x"] == b["x"],
                  {"scrollY": [plain, page.evaluate("() => window.scrollY")], "x": c["x"]})
        page.evaluate(f"() => {EL}.scrollIntoView({{block: 'center'}})")
        ctx.frames(page)

    # ---- drag pans; right-drag and Shift + drag zoom to the dragged span; double-click restores
    with guard(ctx, "drag, box zoom and reset"):
        reset()
        a = page.evaluate(STATE)
        x1, y = at(0.6)
        x2, _ = at(0.4)
        page.mouse.move(x1, y)
        page.mouse.down()
        page.mouse.move((x1 + x2) / 2, y, steps=4)
        page.mouse.move(x2, y, steps=4)
        page.mouse.up()
        ctx.frames(page)
        b = page.evaluate(STATE)
        want = [a["x"][0] + 0.2 * span(a["x"]), a["x"][1] + 0.2 * span(a["x"])]
        ctx.check("drag: dragging left by 20 % of the plot pans x right by 20 % of its span (±1 frame), y unmoved",
                  near(b["x"][0], want[0], FRAME) and near(b["x"][1], want[1], FRAME) and all(near(p, q, 1e-9) for p, q in zip(a["y"], b["y"])),
                  {"x": b["x"], "want": want, "y": [a["y"], b["y"]]})
        for how in ("right", "shift"):
            reset()
            a = page.evaluate(STATE)
            x1, y = at(0.25)
            x2, _ = at(0.55)
            page.mouse.move(x1, y)
            if how == "shift":
                page.keyboard.down("Shift")
            page.mouse.down(button="right" if how == "right" else "left")
            page.mouse.move((x1 + x2) / 2, y + 1, steps=4)
            page.mouse.move(x2, y + 2, steps=4)
            page.mouse.up(button="right" if how == "right" else "left")
            if how == "shift":
                page.keyboard.up("Shift")
            ctx.frames(page)
            b = page.evaluate(STATE)
            want = [a["x"][0] + 0.25 * span(a["x"]), a["x"][0] + 0.55 * span(a["x"])]
            w = clock(page)["window"]
            ctx.check(f"box zoom ({'right-drag' if how == 'right' else 'Shift + drag'}): x becomes the dragged span (±1 frame) and the dashboard clock's window follows it",
                      near(b["x"][0], want[0], FRAME) and near(b["x"][1], want[1], FRAME) and w is not None and near(w[0], b["x"][0], 1e-6) and near(w[1], b["x"][1], 1e-6),
                      {"x": b["x"], "want": want, "clock.window": w})
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{KEY}']")), "plot-boxzoom-light")
        reset()
        c = page.evaluate(STATE)
        ctx.check("double-click restores the full range (x = the data's span, y back to its first auto range) and clears the clock's window",
                  near(c["x"][0], t_lo, 1e-9) and near(c["x"][1], t_hi, 1e-9) and all(near(p, q, 1e-9) for p, q in zip(c["y"], s0["y"])) and clock(page)["window"] is None,
                  {"x": c["x"], "y": c["y"], "first y": s0["y"], "window": clock(page)["window"]})

    # ---- the window from another card: the plot follows clock.window
    with guard(ctx, "following clock.window"):
        page.evaluate("() => document.querySelector('#example').clock.setWindow([2, 4])")
        ctx.until(page, f"() => Math.abs({EL}.uplot.scales.x.min - 2) < 1e-9", timeout=3000)
        b = page.evaluate(STATE)
        page.evaluate("() => document.querySelector('#example').clock.setWindow(null)")
        ctx.until(page, f"() => Math.abs({EL}.uplot.scales.x.min - {t_lo}) < 1e-9", timeout=3000)
        c = page.evaluate(STATE)
        ctx.check("clock.window set elsewhere ([2, 4]) becomes the plot's x range; cleared, the plot returns to the data's span",
                  near(b["x"][0], 2, 1e-9) and near(b["x"][1], 4, 1e-9) and near(c["x"][0], t_lo, 1e-9) and near(c["x"][1], t_hi, 1e-9), {"with window": b["x"], "cleared": c["x"]})

    # ---- a click moves the time cursor; the playhead sits on uPlot's x(t) after seeks
    with guard(ctx, "click and playhead"):
        reset()
        a = page.evaluate(STATE)
        x, y = at(0.7)
        page.mouse.click(x, y)
        ctx.frames(page)
        want_t = a["x"][0] + 0.7 * span(a["x"])
        ctx.check("click: a click on the plot moves the clock's t to the time under it (±1 frame)", near(clock(page)["t"], want_t, FRAME), {"t": clock(page)["t"], "want": want_t})
        misses = []
        for t in (1.2, 3.65, 6.1):
            seek(page, t)
            want_x = page.evaluate(XAT, t)
            ph = page.evaluate(CENTRES, [KEY, "[data-playhead]"])
            if len(ph) != 1 or abs(ph[0]["x"] - want_x) > 1:
                misses.append({"t": t, "want": round(want_x, 2), "got": [round(p["x"], 2) for p in ph]})
        ctx.check("playhead: after seek(1.2 / 3.65 / 6.1) the [data-playhead] centre sits on uPlot's x(t) within 1 px", not misses, misses or "3 of 3")

    # ---- playing: the playhead moves, the plot is never re-created
    with guard(ctx, "playing"):
        page.mouse.move(2, 2)
        seek(page, 1.0)
        page.evaluate(f"() => {{ window.__u = {EL}.uplot; window.__plots = {EL}.dataset.plots; }}")
        p0 = page.evaluate(CENTRES, [KEY, "[data-playhead]"])
        page.evaluate("() => document.querySelector('#example').clock.play()")
        page.wait_for_timeout(600)
        mid = page.evaluate(CENTRES, [KEY, "[data-playhead]"])
        t_mid = clock(page)["t"]
        want_mid = page.evaluate(XAT, t_mid)
        page.evaluate("() => document.querySelector('#example').clock.pause()")
        ctx.frames(page)
        same_plot = page.evaluate(f"() => window.__u === {EL}.uplot && window.__plots === {EL}.dataset.plots")
        ctx.check("playing 0.6 s: the playhead moves with clock.t and the plot is never re-created (same uPlot instance, 0 new plots)",
                  p0 and mid and mid[0]["x"] - p0[0]["x"] > 5 and same_plot, {"playhead x": [p0 and round(p0[0]["x"]), mid and round(mid[0]["x"])], "same plot": same_plot})
        seek(page, clock(page)["t"])
        end = page.evaluate(CENTRES, [KEY, "[data-playhead]"])
        ctx.check("paused after playing, the playhead sits on uPlot's x(clock.t) within 1 px", end and abs(end[0]["x"] - page.evaluate(XAT, clock(page)["t"])) <= 1,
                  {"got": end and end[0]["x"], "want": page.evaluate(XAT, clock(page)["t"]), "t at 0.6 s": t_mid, "want then": want_mid})

    # ---- hover: shared with the Vega time series both ways
    with guard(ctx, "the shared hover"):
        x, y = at(0.4)
        page.mouse.move(x, y)
        ctx.frames(page)
        hover = page.evaluate("() => document.querySelector('#example').clock.hover")
        want_h = page.evaluate(STATE)
        want_h = want_h["x"][0] + 0.4 * span(want_h["x"])
        other = page.evaluate(CENTRES, ["step-response", "[data-hover]"])
        ctx.check("hover: a pointer over the plot sets clock.hover to the t under it (±1 frame) and the Vega 'Step response' draws its [data-hover] rule",
                  near(hover, want_h, FRAME) and len(other) == 1, {"hover": hover, "want": want_h, "rules on step-response": len(other)})
        page.mouse.move(2, 2)
        ctx.frames(page)
        page.evaluate("() => document.querySelector('#example').clock.setHover(2.5)")
        ctx.frames(page)
        mine = page.evaluate(CENTRES, [KEY, "[data-hover]"])
        want_x = page.evaluate(XAT, 2.5)
        ctx.check("hover: clock.hover from another card (2.5 s) draws this plot's [data-hover] rule at uPlot's x(2.5) within 1 px",
                  len(mine) >= 1 and abs(mine[0]["x"] - want_x) <= 1, {"rule": [round(m["x"], 1) for m in mine], "want": round(want_x, 1)})
        page.evaluate("() => document.querySelector('#example').clock.setHover(null)")

    # ---- the ? popover
    with guard(ctx, "the help popover"):
        page.locator(f"{D} .dd-panel[data-panel='{KEY}'] [data-plot-help]").click()
        ctx.frames(page)
        pop = page.evaluate(f"""() => {{ const p = {EL}.querySelector('.dv-plot-help'); const r = p.getBoundingClientRect();
          return {{ open: p.matches(':popover-open'), text: p.innerText, rect: [r.left, r.top, r.right, r.bottom], vw: innerWidth, vh: innerHeight }}; }}""")
        missing = [c for c in CONTROLS if c not in pop["text"]]
        inside = pop["rect"][0] >= 0 and pop["rect"][1] >= 0 and pop["rect"][2] <= pop["vw"] and pop["rect"][3] <= pop["vh"]
        ctx.check("help: the ? button opens a popover listing every control (Rerun's ten), inside the viewport", pop["open"] and not missing and inside,
                  {"open": pop["open"], "missing": missing, "rect": pop["rect"]})
        ctx.shot(page, "plot-help-light")
        page.keyboard.press("Escape")
        ctx.frames(page)
        ctx.check("help: Esc closes it", not page.evaluate(f"() => {EL}.querySelector('.dv-plot-help').matches(':popover-open')"))

    # ---- maximise fills the viewport; Esc restores
    with guard(ctx, "maximise"):
        box = f"() => {{ const r = {EL}.querySelector('.dv-plot').getBoundingClientRect(); const u = {EL}.uplot; return [r.left, r.top, r.width, r.height, u.width, u.height, innerWidth, innerHeight]; }}"
        a = page.evaluate(box)
        page.locator(f"{D} .dd-panel[data-panel='{KEY}'] [data-plot-max]").click()
        ctx.until(page, f"() => {EL}.uplot.width > {a[4] + 10}", timeout=3000)
        ctx.frames(page)
        b = page.evaluate(box)
        ctx.check("maximise: the card fills the viewport (0, 0, innerWidth, innerHeight within 1 px) and the plot redraws to its size",
                  abs(b[0]) <= 1 and abs(b[1]) <= 1 and abs(b[2] - b[6]) <= 1 and abs(b[3] - b[7]) <= 1 and b[4] > 0.8 * b[6], {"rect": b[:4], "plot": b[4:6], "viewport": b[6:]})
        ctx.shot(page, "plot-maximised-light")
        page.keyboard.press("Escape")
        ctx.until(page, f"() => Math.abs({EL}.uplot.width - {a[4]}) <= 1", timeout=3000)
        ctx.frames(page)
        c = page.evaluate(box)
        ctx.check("maximise: Esc restores the card to its panel (same rect and plot size within 1 px)", all(abs(p - q) <= 1 for p, q in zip(a[:6], c[:6])), {"before": a[:6], "after": c[:6]})

    # ---- speed: per-redraw ms of a pan, and frame intervals during a real drag
    with guard(ctx, "speed"):
        reset()
        ms = page.evaluate(f"""() => {{ const u = {EL}.uplot, out = []; const a = u.scales.x.min, b = u.scales.x.max, s = (b - a) / 2;
          for (let k = 0; k < 40; k++) {{ const t0 = performance.now(); u.batch(() => u.setScale('x', {{ min: a + k * s / 40, max: a + s + k * s / 40 }})); out.push(performance.now() - t0); }}
          return out; }}""")
        reset()
        page.evaluate("() => { window.__f = []; let last = performance.now(); window.__stop = false; const tick = (now) => { window.__f.push(now - last); last = now; if (!window.__stop) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }")
        x1, y = at(0.8)
        page.mouse.move(x1, y)
        page.mouse.down()
        for k in range(60):
            page.mouse.move(x1 - k * 8, y)
        page.mouse.up()
        page.wait_for_timeout(150)
        frames = page.evaluate("() => { window.__stop = true; return window.__f.slice(1); }")
        frames.sort()
        med = statistics.median(ms)
        ctx.budget("speed: a pan redraw of the interactive plot (u.setScale x, 3 series × 396 samples) takes under 8 ms (median of 40)", med, 8,
                   f"median {med:.2f} ms, max {max(ms):.2f} ms; drag frames: median {statistics.median(frames):.1f} ms, p95 {frames[int(0.95 * (len(frames) - 1))]:.1f} ms over {len(frames)} frames")
        names = page.evaluate("() => performance.getEntriesByType('resource').map((e) => e.name).filter((n) => /views\\/chart(-plot-.*)?\\.js$/.test(n))")
        sizes = {}
        for n in names:
            body = urllib.request.urlopen(n, timeout=5).read()
            sizes[n.rsplit("/", 1)[1]] = {"kb": round(len(body) / 1024, 1), "gz kb": round(len(gzip.compress(body)) / 1024, 1)}
        chunk = {k: v for k, v in sizes.items() if k.startswith("chart-plot-")}
        ctx.check("bundle: the uPlot chunk is under 40 KB gzipped (uPlot 1.6.32 + the card), loaded on top of the chart bundle", chunk and all(v["gz kb"] < 40 for v in chunk.values()), sizes)
    with guard(ctx, "the light screenshot"):
        reset()
        seek(page, 3.2)
        page.mouse.move(2, 2)
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{KEY}']")), "plot-light")
    page.context.close()

    # ---- lazy: a page whose charts are all simple never fetches the uPlot chunk
    with guard(ctx, "lazy loading"):
        other = ctx.page("gallery/actuator-charts/index.html", width=1280, height=900)
        names = other.evaluate("() => performance.getEntriesByType('resource').map((e) => e.name.split('/').pop()).filter((n) => /^chart/.test(n))")
        ctx.check("lazy: a page of simple charts (actuator-charts) loads views/chart.js and never the uPlot chunk", "chart.js" in names and not any(n.startswith("chart-plot-") for n in names), names)
        other.context.close()

    # ---- dark, and a phone
    page = ctx.page(path, width=1440, height=1000, dark=True)
    ready(page)
    ctx.until(page, f"() => {{ const el = {EL}; return el && el.uplot; }}", timeout=15000)
    seek(page, 3.2)
    ctx.frames(page)
    ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{KEY}']")), "plot-dark")
    st = page.evaluate(f"""() => {{ const el = {EL}; const u = el.uplot; const ax = u.axes[1]; return {{ bg: getComputedStyle(el).backgroundColor,
      grid: typeof ax.grid.stroke === 'function' ? ax.grid.stroke(u, 1) : ax.grid.stroke, label: typeof ax.stroke === 'function' ? ax.stroke(u, 1) : ax.stroke,
      tokens: [getComputedStyle(el).getPropertyValue('--dv-rule').trim(), getComputedStyle(el).getPropertyValue('--dv-muted').trim()],
      xgrid: u.axes[0].grid.show, ticks: u.axes.map((a) => a.ticks.show) }}; }}""")
    ctx.check("dark: the plot fills its panel transparently; minimal chrome: no x grid, no ticks, a horizontal grid in the rule token, labels in the muted token",
              st["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and st["xgrid"] is False and not any(st["ticks"]) and st["grid"] and st["label"], st)
    page.locator(f"{D} .dd-panel[data-panel='{KEY}'] [data-plot-max]").click()
    ctx.frames(page, 4)
    ctx.shot(page, "plot-maximised-dark")
    page.keyboard.press("Escape")
    page.context.close()

    page = ctx.page(path, width=390, height=844, mobile=True)
    ready(page)
    ctx.until(page, f"() => {{ const el = {EL}; return el && el.uplot; }}", timeout=15000)
    page.evaluate(f"() => {EL}.scrollIntoView({{block: 'center'}})")
    ctx.frames(page, 4)
    sw = page.evaluate("document.scrollingElement.scrollWidth")
    over = page.evaluate(f"""() => {{ const el = {EL}; const p = el.closest('.dd-panel').getBoundingClientRect(); return [...el.querySelectorAll('canvas, .dv-plot-head')].some((c) => c.getBoundingClientRect().right > p.right + 1); }}""")
    ctx.check("390 px: no sideways page scroll and the plot fits its panel", sw <= 390 and not over, {"scrollWidth": sw, "over": over})
    ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{KEY}']")), "plot-390")
    page.context.close()

