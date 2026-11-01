"""Browser checks for this case (run by tests/browser/checks.py): the chart view's asks, on 1,149 real rows. Presets
switch, the rail filters the chart (and the redraw is timed), the Encode menu writes `chart:` back, the hover card
shows a photo, a click opens the record, Rows shows the same rows, the Ashby envelopes are filled, light and dark
at 1280 and 390 px."""

V = "#example"

# the page coordinates of one drawn dot: a photo part's, and one no other dot covers (the top item is the one hovered)
DOT = """(wantPhoto) => {
  const el = document.querySelector('#example .dv-view-chart'); const view = el.vegaView;
  const rows = document.querySelector('#example').data.rows;
  const photo = new Set(rows.filter((r) => r.photo).map((r) => String(r.id)));
  const box = el.querySelector('canvas').getBoundingClientRect(); const [ox0, oy0] = view.origin(); const pad = view.padding(); const ox = ox0 + pad.left, oy = oy0 + pad.top;
  const dots = [];
  const walk = (mark, gx, gy) => {
    for (const item of mark.items || []) {
      if (mark.marktype === 'group') { for (const m of item.items || []) walk(m, gx + (item.x || 0), gy + (item.y || 0)); }
      else if (mark.marktype === 'symbol' && item.datum && item.datum._row !== undefined) dots.push({ id: String(item.datum._id), x: box.left + ox + gx + item.x, y: box.top + oy + gy + item.y });
    }
  };
  walk(view.scenegraph().root, 0, 0);
  const alone = dots.filter((d) => (!wantPhoto || photo.has(d.id)) && dots.every((o) => o === d || Math.hypot(o.x - d.x, o.y - d.y) > 9));
  return { n: dots.length, dot: alone[0] || null };
}"""

# the colour Vega drew the first axis label in, against the page's resolved muted token
AXIS_INK = """() => {
  const el = document.querySelector('#example'); const t = el.tokens();
  let fill = null;
  const walk = (mark) => { for (const item of mark.items || []) { if (fill) return; if (mark.role === 'axis-label' && item.fill) { fill = item.fill; return; } for (const m of item.items || []) walk(m); } };
  walk(el.querySelector('.dv-view-chart').vegaView.scenegraph().root);
  return { fill, muted: t.muted, dark: t.dark };
}"""


def drawn(page):
    page.wait_for_selector(f"{V}[data-view=chart] .dv-view-chart[data-drawn]", timeout=30000)
    page.ctx.frames(page)
    return int(page.get_attribute(f"{V} .dv-view-chart", "data-drawn"))


def show(page):
    """Scroll the live view to the top of the viewport, under the site's sticky header."""
    page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
    page.ctx.frames(page)


def status(page):
    return page.inner_text(f"{V} .dv-status")


def tab(page, name):
    """Open a view by its tab and wait until it has drawn (a state, not a pause: tests/browser/checks.py Ctx.drawn)."""
    page.ctx.drawn(page, lambda: page.click(f"{V} .dv-tab[data-name='{name}']"))


def run(ctx, path):
    check = ctx.check
    page = ctx.page(path, width=1280)
    n = drawn(page)
    check("actuator charts: the first preset is a chart of 1,021 dots, the 128 parts without torque or mass counted out aloud",
          n == 1021 and "128 without peak torque or mass" in status(page), status(page))
    names = page.eval_on_selector_all(f"{V} .dv-tab", "els => els.map((e) => e.dataset.name)")
    seen = {}
    for name in names:
        tab(page, name)
        page.wait_for_function("() => document.querySelector('#example').dataset.view", timeout=10000)
        seen[name] = page.get_attribute(V, "data-view")
    check("actuator charts: every preset draws (six charts and the Rows table, switched by tab)",
          list(seen.values()).count("chart") == 6 and seen.get("Rows") == "table", seen)

    # ---- the rail filters the chart; the redraw is timed (docs/SPEC.md §8.11: under 100 ms on 1,149 points)
    tab(page, "Torque vs mass")
    drawn(page)
    times = page.evaluate("""async () => {
      const el = document.querySelector('#example');
      const once = () => new Promise((done) => el.addEventListener('data-views-render', (e) => done(e.detail), { once: true }));
      const out = [];
      for (let i = 0; i < 8; i++) {
        let w = once(); el.filters = { and: ['brand == "Steadywin"'] }; out.push(['one brand', (await w).ms]);
        w = once(); el.filters = null; out.push(['all 1,149', (await w).ms]);
      }
      return out;
    }""")
    full = sorted(ms for what, ms in times if what == "all 1,149")
    # WHY load-aware: a fixed 100 ms flaked on this box under load (2026-10-26 review); ctx.budget enforces it while the
    # machine has CPUs to spare and reports it SOFT, with the load, when it does not
    ctx.budget("chart: a filter change redraws all 1,149 rows in under 100 ms (data-views-render, filter set to drawn, worst of 8 runs)", full[-1], 100,
               f"median {full[len(full) // 2]:.1f} ms; one brand worst {max(ms for w, ms in times if w == 'one brand'):.1f} ms")
    ctx.drawn(page, lambda: page.check("data-facets input[data-p=brand][data-value=Steadywin]"))
    check("chart: ticking a brand in the rail redraws the chart with that brand's dots only", drawn(page) < 100 and status(page).startswith("86 of 1,149"),
          f"{drawn(page)} dots; {status(page).split(' · ')[0]}")
    ctx.drawn(page, lambda: page.click("data-facets [data-clear]"))

    # ---- hover: the card with the photo; click: the record
    page.evaluate("document.querySelector('#example').scrollIntoView({ block: 'start' })")
    ctx.frames(page)
    hit = page.evaluate(DOT, True)
    dot = hit["dot"]
    page.mouse.move(dot["x"], dot["y"])
    ctx.until(page, "() => { const c = document.querySelector('#example .dv-chart-hover'); const img = c && c.querySelector('img'); return c && !c.hidden && img && img.complete && img.naturalWidth > 0; }")
    card = page.evaluate("""() => { const c = document.querySelector('#example .dv-chart-hover'); const img = c.querySelector('img');
      return { shown: !c.hidden, title: (c.querySelector('b') || {}).textContent, text: c.innerText, src: img && img.currentSrc, w: img ? img.naturalWidth : 0 }; }""")
    ctx.shot(page, "actuator-charts-hover-light-1280")
    check("chart: hovering a dot shows its card: the photo (loaded, resolved against the data file), the name and its values with units",
          card["shown"] and card["w"] > 0 and "/gallery/robotparts-actuators/photos/" in (card["src"] or "") and "N·m" in card["text"], f"{card['title']}: photo {card['w']} px wide")
    page.mouse.click(dot["x"], dot["y"])
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    peeked = page.evaluate("document.querySelector('#example').peeked")
    check("chart: clicking a dot opens that part's record in the peek", peeked and peeked["id"] == dot["id"] and card["title"] in page.inner_text(f"{V} .dv-peek h2"), page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")

    # ---- Encode: colour, scale; the view reads changed; Reset
    page.click(f"{V} .dv-chart-encode")
    ctx.drawn(page, lambda: page.select_option(f"{V} .dv-chart-pop select[data-ch=color]", "form"))
    ctx.drawn(page, lambda: page.select_option(f"{V} .dv-chart-pop select[data-scale=y]", "linear"))
    chart = page.evaluate("document.querySelector('#example').view.chart.encoding")
    legend = page.evaluate("document.querySelector('#example .dv-view-chart').vegaView.scale('color').domain()")
    ctx.shot(page, "actuator-charts-encode-light-1280")
    check("Encode: colour by form and a linear y axis are written into the view's chart: block; Reset and Save view appear",
          chart["color"]["field"] == "form" and chart["y"]["scale"]["type"] == "linear" and page.is_visible(f"{V} .dv-dirty") and "integrated actuator" in legend,
          f"color {chart['color']}, y {chart['y']}")
    page.click(f"{V} .dv-chart-encode")
    ctx.drawn(page, lambda: page.click(f"{V} .dv-reset"))
    check("Reset returns the preset's chart: block", page.evaluate("document.querySelector('#example').view.chart.encoding.color.field") == "brand")

    # ---- Rows: the same filtered rows, as the table
    ctx.drawn(page, lambda: page.check("data-facets input[data-p=brand][data-value=KST]"))
    page.click(f"{V} .dv-chart-rowsbtn")
    page.wait_for_selector(f"{V} .dv-chart-rows tbody tr[data-i]")
    rows = page.evaluate("document.querySelector('#example .dv-chart-rows .dv-scroll').scrollHeight")
    first = page.inner_text(f"{V} .dv-chart-rows tbody tr.dv-row")
    check("Rows: one click shows the chart's own rows (the rail's 95 KST parts) as the table under the chart", "KST" in first and status(page).startswith("95 of 1,149"),
          f"{status(page).split(' · ')[0]}; first row {first.split(chr(9))[:3]}; table {rows} px tall")
    ctx.shot(page, "actuator-charts-rows-light-1280")
    page.click(f"{V} .dv-chart-rowsbtn")
    ctx.drawn(page, lambda: page.click("data-facets [data-clear]"))

    # ---- the Ashby preset: envelopes filled, the index line drawn
    tab(page, "Ashby · torque vs mass")
    drawn(page)
    ashby = page.evaluate("""() => { const v = document.querySelector('#example .dv-view-chart').vegaView;
      const hull = v.data('env0'), idx = v.data('idx1');
      return { vertices: hull.length, families: new Set(hull.map((d) => d.drivetrain)).size, index: idx.length, legend: v.scale('color').domain() }; }""")
    check("Ashby: one filled envelope per drivetrain (hulls in log space) and an index line through the median",
          ashby["families"] >= 3 and ashby["index"] == 2 and "geared" in ashby["legend"], ashby)
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            p = ctx.page(path, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            drawn(p)
            scroll = p.evaluate("document.scrollingElement.scrollWidth")
            name = f"actuator-charts-{'dark' if dark else 'light'}-{width}"
            if width == 390:
                check(f"actuator charts, {'dark' if dark else 'light'}, 390 px: no sideways page scroll", scroll <= 390, f"scrollWidth {scroll}")
            ink = p.evaluate(AXIS_INK)
            check(f"actuator charts, {'dark' if dark else 'light'}, {width} px: the axis labels are drawn in the page's muted token",
                  ink["fill"] == ink["muted"] and ink["dark"] == dark, ink)
            show(p)
            ctx.shot(p, name)
            tab(p, "Ashby · torque vs mass")
            drawn(p)
            show(p)
            ctx.shot(p, name.replace("actuator-charts", "actuator-charts-ashby"))
            p.context.close()
