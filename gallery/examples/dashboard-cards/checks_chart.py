"""The chart lane's checks on the card catalog: timeseries, trajectory and plain charts under style.chrome minimal
(docs/peps/0005-dashboard-cards.md §2b, §4, §5). Loaded by checks.py beside it (run(ctx, path, helpers)).

Every expected number comes from the case's JSON (helpers['rows']) or from Vega's own scales (view.scale, view.origin),
never from the card's overlay code: a playhead is right when its centre sits where Vega draws t."""

import bisect
import contextlib

FRAME = 1 / 30

# the panel's plot rectangle in page px: the canvas box + where Vega's renderer puts the plot (vega-view's offset():
# padding + origin; view.origin() alone leaves the padding out), and its scales
GEOM = """(key) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const v = el && el.vegaView;
  const c = el && el.querySelector('canvas');
  if (!v || !c) return null;
  const r = c.getBoundingClientRect(), p = v.padding(), o = [p.left + v.origin()[0], p.top + v.origin()[1]];
  const sx = v.scale('x'), sy = v.scale('y');
  return { type: el.className, left: r.left + o[0], top: r.top + o[1], w: v.width(), h: v.height(),
    xdomain: sx.domain(), ydomain: sy ? sy.domain() : null }; }"""

# x and y in page px of data values, through the panel's own Vega scales
AT = """([key, pts]) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const v = el.vegaView, r = el.querySelector('canvas').getBoundingClientRect(), p = v.padding(), o = [p.left + v.origin()[0], p.top + v.origin()[1]];
  return pts.map(([x, y]) => [r.left + o[0] + v.scale('x')(x), y === null ? null : r.top + o[1] + v.scale('y')(y)]); }"""

CENTRES = """([key, sel]) => [...document.querySelectorAll(`#example .dd-panel[data-panel="${key}"] ${sel}`)]
  .filter((e) => !e.hidden && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden')
  .map((e) => { const b = e.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2, series: e.dataset.series || null, text: e.textContent }; })"""

# every mark in the scenegraph: {name, marktype, role, items: [{datum, strokeDash, stroke, strokeWidth}]}
MARKS = """(key) => {
  const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`);
  const out = [];
  const walk = (node, axis) => {
    if (!node) return;
    if (node.marktype) {
      const role = node.role || '';
      const ax = role === 'axis' && node.items[0] ? node.items[0].orient : axis;
      out.push({ name: node.name || '', marktype: node.marktype, role, axis: ax, n: (node.items || []).length,
        items: (node.items || []).slice(0, 1).map((i) => ({ series: i.datum && i.datum.series, strokeDash: i.strokeDash || null, stroke: i.stroke || null, strokeWidth: i.strokeWidth })) });
      for (const i of node.items || []) walk(i, ax);
    } else if (node.items) for (const i of node.items) walk(i, axis);
  };
  walk(el.vegaView.scenegraph().root, null);
  return out; }"""

PANELS = ["step-response", "error-over-time", "kpi-history", "tool-path-xz", "tracking-rms-per-joint", "error-histogram", "gains-scatter", "error-heatmap"]


@contextlib.contextmanager
def guard(ctx, what):
    """A section that cannot run (its card is not drawn yet) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        ctx.check(f"chart lane: {what} could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


class Part:
    """ctx.shot(page, name) for one panel: a locator answering page.screenshot(path, full_page)."""

    def __init__(self, locator):
        self.locator = locator

    def screenshot(self, path, full_page=False):
        # centred, so the site's sticky header never covers the panel's top
        self.locator.evaluate("(e) => e.scrollIntoView({block: 'center'})")
        self.locator.page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        self.locator.screenshot(path=path)


def drawn(ctx, page, keys):
    """Every panel's Vega view exists and has a plot (the time series and trajectory need their second pass)."""
    return ctx.until(page, """(keys) => keys.every((k) => { const el = document.querySelector(`#example .dd-panel[data-panel="${k}"] .dv-view`);
      return el && el.vegaView && el.querySelector('canvas') && el.dataset.drawn; })""", keys)


def interp(rows, t, cols):
    """The row of a series at time t, linearly interpolated by the t column (the oracle for a marker)."""
    ts = [r["t"] for r in rows]
    i = bisect.bisect_left(ts, t)
    if i <= 0:
        return [rows[0][c] for c in cols]
    if i >= len(rows):
        return [rows[-1][c] for c in cols]
    a, b = rows[i - 1], rows[i]
    f = (t - a["t"]) / (b["t"] - a["t"]) if b["t"] != a["t"] else 0
    return [a[c] + (b[c] - a[c]) * f for c in cols]


def run(ctx, path, helpers):
    rows, ready, seek, clock, D = helpers["rows"], helpers["ready"], helpers["seek"], helpers["clock"], helpers["D"]
    samples = rows("samples.json")
    elbow = [r for r in samples if r["joint"] == "elbow_joint" and r["q_deg"] is not None]
    want_series = sorted({r["situation"] for r in elbow})
    tool = rows("tool.json")
    hist = [r for r in rows("series.json") if r["kpi"] in ("p2p_calc_time_ratio", "wp_calc_time_ratio")]

    page = ctx.page(path, width=1440, height=1000)
    ready(page)
    ok = drawn(ctx, page, PANELS)
    ctx.check("chart lane: the eight chart panels each drew a Vega view (timeseries, trajectory, plain charts)", ok,
              page.evaluate("(ks) => ks.map((k) => [k, (document.querySelector(`#example .dd-panel[data-panel=\"${k}\"] .dv-view`) || {}).className])", PANELS))

    # ---- Step response: exactly the oracle's series; target dashed
    with guard(ctx, 'Step response'):
        marks = page.evaluate(MARKS, "step-response")
        lines = [m for m in marks if m["marktype"] == "line" and m["items"] and m["items"][0]["series"]]
        got = sorted({m["items"][0]["series"] for m in lines})
        dash = {m["items"][0]["series"]: m["items"][0]["strokeDash"] for m in lines}
        ctx.check("timeseries: Step response draws exactly the oracle's series (elbow_joint: target, factory, tuned), target dashed, the others solid",
                  got == want_series and bool(dash.get("target")) and not any(dash.get(s) for s in want_series if s != "target"), {"drawn": got, "oracle": want_series, "dash": dash})
        pal = {"target": "#8b9099", "factory": "#e8743b", "tuned": "#2a78d6"}
        stroke = {m["items"][0]["series"]: m["items"][0]["stroke"] for m in lines}
        ctx.check("timeseries: each series wears the dashboard palette's colour by name", all((stroke.get(k) or "").lower() == v for k, v in pal.items()), stroke)

    # ---- the playhead in both time series, on Vega's own x scale, after three seeks
    with guard(ctx, "the playhead in both time series, on Vega's own x scale, after three seeks"):
        misses = []
        for t in (1.2, 3.65, 6.1):
            seek(page, t)
            for key in ("step-response", "error-over-time"):
                [[want, _]] = page.evaluate(AT, [key, [[t, None]]])
                ph = page.evaluate(CENTRES, [key, "[data-playhead]"])
                if len(ph) != 1 or abs(ph[0]["x"] - want) > 1:
                    misses.append({"t": t, "panel": key, "want": round(want, 2), "got": [round(p["x"], 2) for p in ph]})
        ctx.check("timeseries: after seek(1.2 / 3.65 / 6.1) the [data-playhead] of Step response and Error over time sits on Vega's x(t) within 1 px", not misses, misses or "6 of 6")

    # ---- the shared crosshair: hover over Step response draws a rule at the same t on Error over time
    with guard(ctx, 'the shared crosshair'):
        page.evaluate(f"() => document.querySelector(\"{D} .dd-panel[data-panel='step-response']\").scrollIntoView({{block: 'start'}})")
        ctx.frames(page)
        g = page.evaluate(GEOM, "step-response")
        px = g["left"] + 0.4 * g["w"]
        page.mouse.move(px, g["top"] + g["h"] / 2)
        ctx.frames(page)
        c = clock(page)
        hover = page.evaluate("() => document.querySelector('#example').clock.hover")
        [[at_src, _]] = page.evaluate(AT, ["step-response", [[hover or 0, None]]])
        [[at_err, _]] = page.evaluate(AT, ["error-over-time", [[hover or 0, None]]])
        rule = page.evaluate(CENTRES, ["error-over-time", "[data-hover]"])
        read = page.evaluate("() => [...document.querySelectorAll('#example .dd-panel[data-panel=\"error-over-time\"] [data-hover] [data-series]')].map((e) => e.dataset.series)")
        ctx.check("timeseries crosshair: a pointer over Step response sets clock.hover to the t under it, and Error over time draws its [data-hover] rule at its own x(t) within 1 px, with a readout per series",
                  hover is not None and abs(at_src - px) <= 1 and len(rule) == 1 and abs(rule[0]["x"] - at_err) <= 1 and sorted(read) == ["factory", "tuned"],
                  {"hover": hover, "pointer": round(px, 1), "x(hover)": round(at_src, 1), "rule": [round(r["x"], 1) for r in rule], "want": round(at_err, 1), "readout": read})
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='error-over-time']")), "chart-error-over-time-hover-light")
        page.mouse.move(5, 5)
        ctx.frames(page)
        gone = page.evaluate(CENTRES, ["error-over-time", "[data-hover]"])
        ctx.check("timeseries crosshair: leaving the plot clears clock.hover and the rule", page.evaluate("() => document.querySelector('#example').clock.hover") is None and not gone, gone)

    # ---- a click seeks
    with guard(ctx, 'a click seeks'):
        seek(page, 0.5)
        cx = g["left"] + 0.7 * g["w"]
        page.mouse.click(cx, g["top"] + g["h"] / 2)
        ctx.frames(page)
        want_t = g["xdomain"][0] + 0.7 * (g["xdomain"][1] - g["xdomain"][0])
        ctx.check("timeseries: a click on the plot seeks the clock to the t under it (within a frame)", abs(clock(page)["t"] - want_t) <= FRAME, {"t": clock(page)["t"], "want": want_t})

    # ---- brush to zoom: every time series takes clock.window as its x domain; double-click clears
    with guard(ctx, 'brush to zoom'):
        x1, x2 = g["left"] + 0.2 * g["w"], g["left"] + 0.6 * g["w"]
        span = g["xdomain"][1] - g["xdomain"][0]
        want_w = [g["xdomain"][0] + 0.2 * span, g["xdomain"][0] + 0.6 * span]
        y = g["top"] + g["h"] / 2
        page.mouse.move(x1, y)
        page.mouse.down()
        page.mouse.move((x1 + x2) / 2, y, steps=4)
        page.mouse.move(x2, y, steps=4)
        page.mouse.up()
        ctx.until(page, "() => { const el = document.querySelector('#example .dd-panel[data-panel=\"error-over-time\"] .dv-view'); const w = document.querySelector('#example').clock.window; return w && el.vegaView && Math.abs(el.vegaView.scale('x').domain()[0] - w[0]) < 1e-6; }", timeout=8000)
        ctx.frames(page)
        w = clock(page)["window"]
        other = page.evaluate(GEOM, "error-over-time")
        own = page.evaluate(GEOM, "step-response")
        ok = w is not None and all(abs(a - b) <= FRAME for a, b in zip(w, want_w)) and all(abs(a - b) <= 1e-6 for a, b in zip(other["xdomain"], w)) and all(abs(a - b) <= 1e-6 for a, b in zip(own["xdomain"], w))
        ctx.check("timeseries brush: dragging over Step response sets clock.window to the dragged span (±1 frame); Step response and Error over time both take it as their x domain",
                  ok, {"window": w, "dragged": want_w, "error-over-time x": other["xdomain"], "step-response x": own["xdomain"]})
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='step-response']")), "chart-step-response-zoomed-light")
        g2 = page.evaluate(GEOM, "step-response")   # the shot scrolled the page: measure again
        page.mouse.dblclick(g2["left"] + g2["w"] / 2, g2["top"] + g2["h"] / 2)
        ctx.until(page, "() => document.querySelector('#example').clock.window === null", timeout=8000)
        ctx.until(page, "() => { const el = document.querySelector('#example .dd-panel[data-panel=\"error-over-time\"] .dv-view'); return Math.abs(el.vegaView.scale('x').domain()[0]) < 1e-6; }", timeout=8000)
        other = page.evaluate(GEOM, "error-over-time")
        t_err = [r["t"] for r in samples if r["joint"] == "elbow_joint" and r["situation"] != "target" and r["err_mrad"] is not None]
        ctx.check("timeseries brush: a double-click clears clock.window and Error over time returns to its data's span",
                  clock(page)["window"] is None and abs(other["xdomain"][0] - min(t_err)) < 1e-6 and abs(other["xdomain"][1] - max(t_err)) < 1e-6, {"window": clock(page)["window"], "x": other["xdomain"], "data": [min(t_err), max(t_err)]})

    # ---- KPI history: a date x, two series, no playhead
    with guard(ctx, 'KPI history'):
        marks = page.evaluate(MARKS, "kpi-history")
        got = sorted({m["items"][0]["series"] for m in marks if m["marktype"] == "line" and m["items"] and m["items"][0]["series"]})
        ph = page.evaluate(CENTRES, ["kpi-history", "[data-playhead]"])
        ctx.check("timeseries: KPI history (date x) draws its 2 series and no playhead", got == sorted({r["label"] for r in hist}) and len(got) == 2 and not ph, {"drawn": got, "playheads": len(ph)})

    # ---- trajectory: markers on Vega's scales at the oracle's interpolated row, equal aspect, the tolerance tube
    with guard(ctx, 'trajectory'):
        by = {}
        for r in tool:
            by.setdefault(r["situation"], []).append(r)
        for s in by.values():
            s.sort(key=lambda r: r["t"])
        misses, n = [], 0
        for t in (0.8, 3.33, 6.5):
            seek(page, t)
            dots = page.evaluate(CENTRES, ["tool-path-xz", "[data-marker]"])
            for name, srows in by.items():
                x, z = interp(srows, t, ["px", "pz"])
                [[wx, wy]] = page.evaluate(AT, ["tool-path-xz", [[x, z]]])
                got = [d for d in dots if d["series"] == name]
                n += 1
                if len(got) != 1 or abs(got[0]["x"] - wx) > 1.5 or abs(got[0]["y"] - wy) > 1.5:
                    misses.append({"t": t, "series": name, "want": [round(wx, 1), round(wy, 1)], "got": [[round(d["x"], 1), round(d["y"], 1)] for d in got]})
        ctx.check("trajectory: after three seeks each series' [data-marker] sits on Vega's (x, y) of the oracle row interpolated at t, within 1.5 px", not misses and n == 9, misses or f"{n} of 9")
        a = page.evaluate("""() => { const v = document.querySelector('#example .dd-panel[data-panel="tool-path-xz"] .dv-view').vegaView;
          return [v.scale('x')(1) - v.scale('x')(0), v.scale('y')(0) - v.scale('y')(1)]; }""")
        ctx.check("trajectory: equal aspect: 1 unit in x and in y is the same number of px (within 1 %)", a[0] > 0 and abs(a[0] - a[1]) / a[0] <= 0.01, {"px per unit x": a[0], "y": a[1]})
        tube = [m for m in page.evaluate(MARKS, "tool-path-xz") if "tolerance" in m["name"] and m["n"]]
        want_px = 2 * 0.005 * a[0]
        ctx.check("trajectory: the tolerance tube is drawn around the target, 2 × 5 mm wide on the plot's own scale (within 0.5 px)",
                  len(tube) >= 1 and tube[0]["items"] and abs((tube[0]["items"][0]["strokeWidth"] or 0) - want_px) <= 0.5, {"tube": tube[:1], "want px": want_px})
        trail = page.evaluate(CENTRES, ["tool-path-xz", "[data-trail]"])
        ctx.check("trajectory: trail: true draws each moving series' path up to t (one [data-trail] per series)", len(trail) == len(by) or len(trail) == len(by) - 1, len(trail))

    # ---- chrome minimal: no domain lines or ticks; a faint horizontal grid on time series only
    with guard(ctx, 'chrome minimal'):
        report = {}
        for key in ("step-response", "error-over-time", "tracking-rms-per-joint", "error-histogram", "gains-scatter"):
            ms = page.evaluate(MARKS, key)
            has = lambda role, axis=None: sum(m["n"] for m in ms if m["role"] == role and (axis is None or m["axis"] in axis))
            report[key] = {"domain": has("axis-domain"), "tick": has("axis-tick"), "xgrid": has("axis-grid", ("bottom", "top")), "ygrid": has("axis-grid", ("left", "right"))}
        ts_ok = all(report[k]["domain"] == 0 and report[k]["tick"] == 0 and report[k]["xgrid"] == 0 and report[k]["ygrid"] > 0 for k in ("step-response", "error-over-time"))
        plain_ok = all(report[k]["domain"] == 0 and report[k]["tick"] == 0 and report[k]["xgrid"] == 0 and report[k]["ygrid"] == 0 for k in ("tracking-rms-per-joint", "error-histogram", "gains-scatter"))
        ctx.check("chrome minimal: no axis domain line or tick in the time series and the plain charts; the time series keep a faint horizontal grid, the bar, histogram and scatter none",
                  ts_ok and plain_ok, report)
        col = page.evaluate("""() => { const v = document.querySelector('#example .dd-panel[data-panel="tracking-rms-per-joint"] .dv-view').vegaView;
          const s = v.scale('color'); return { tuned: s('tuned'), factory: s('factory'), oracle: s('oracle') }; }""")
        ctx.check("palette: a plain chart's colour over situation uses the dashboard palette (tuned, factory, oracle)",
                  {k: (v or "").lower() for k, v in col.items()} == {"tuned": "#2a78d6", "factory": "#e8743b", "oracle": "#19a979"}, col)

    # ---- playing: the playheads and markers move every frame, and no Vega view runs again
    with guard(ctx, 'playing'):
        page.mouse.move(2, 2)
        seek(page, 1.0)
        keys = ["step-response", "error-over-time", "tool-path-xz"]
        page.evaluate("""(keys) => { window.__runs = 0; for (const k of keys) { const v = document.querySelector(`#example .dd-panel[data-panel="${k}"] .dv-view`).vegaView;
          for (const m of ['run', 'runAsync', 'resize']) { const f = v[m].bind(v); v[m] = (...a) => { window.__runs++; return f(...a); }; } } }""", keys)
        before = page.evaluate(CENTRES, ["step-response", "[data-playhead]"])
        mk0 = page.evaluate(CENTRES, ["tool-path-xz", "[data-marker][data-series=factory]"])
        page.evaluate("() => document.querySelector('#example').clock.play()")
        page.wait_for_timeout(600)
        page.evaluate("() => document.querySelector('#example').clock.pause()")
        ctx.frames(page)
        after = page.evaluate(CENTRES, ["step-response", "[data-playhead]"])
        mk1 = page.evaluate(CENTRES, ["tool-path-xz", "[data-marker][data-series=factory]"])
        runs = page.evaluate("() => window.__runs")
        moved = before and after and after[0]["x"] - before[0]["x"] > 5 and mk0 and mk1 and abs(mk1[0]["x"] - mk0[0]["x"]) + abs(mk1[0]["y"] - mk0[0]["y"]) > 1
        ctx.check("playing 0.6 s: the playhead and the trajectory marker move, and no Vega view runs again (overlays only, never a Vega run per tick)",
                  bool(moved) and runs == 0, {"playhead": [before and round(before[0]["x"]), after and round(after[0]["x"])], "marker moved": bool(mk0 and mk1 and mk1 != mk0), "vega runs": runs, "t": clock(page)["t"]})

    page.mouse.move(2, 2)
    seek(page, 3.2)
    for key in PANELS:
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{key}']")), f"chart-{key}-light")
    page.context.close()

    # ---- dark, and a phone
    page = ctx.page(path, width=1440, height=1000, dark=True)
    ready(page)
    drawn(ctx, page, PANELS)
    seek(page, 3.2)
    ctx.frames(page)
    for key in PANELS:
        ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='{key}']")), f"chart-{key}-dark")
    bg = page.evaluate("""(ks) => ks.map((k) => getComputedStyle(document.querySelector(`#example .dd-panel[data-panel="${k}"] .dv-view`)).backgroundColor)""", PANELS)
    ctx.check("chart lane, dark: every chart card fills its panel transparently (the dashboard draws the surface)", all(b in ("rgba(0, 0, 0, 0)", "transparent") for b in bg), bg)
    page.context.close()

    page = ctx.page(path, width=390, height=844, mobile=True)
    ready(page)
    drawn(ctx, page, ["step-response", "tool-path-xz"])
    sw = page.evaluate("document.scrollingElement.scrollWidth")
    over = page.evaluate("""(ks) => ks.filter((k) => { const el = document.querySelector(`#example .dd-panel[data-panel="${k}"]`); const c = el && el.querySelector('canvas');
      return c && c.getBoundingClientRect().right > el.getBoundingClientRect().right + 1; })""", PANELS)
    ctx.check("chart lane, 390 px: no sideways page scroll and no chart wider than its panel", sw <= 390 and not over, {"scrollWidth": sw, "over": over})
    page.locator(f"{D} .dd-panel[data-panel='step-response']").scroll_into_view_if_needed()
    ctx.frames(page)
    ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='step-response']")), "chart-step-response-390")
    ctx.shot(Part(page.locator(f"{D} .dd-panel[data-panel='tool-path-xz']")), "chart-tool-path-xz-390")
    page.context.close()
