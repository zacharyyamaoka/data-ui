"""Measurements shared by the three Vibe Tracks dashboards' checks.py (this case, ../vibetracks-runs, ../vibetracks-track):
the stat cards and the Vega lines read back from the page, and the oracles' small arithmetic. Every expected number is
computed by the caller from the JSON files; nothing here reads the page's model."""

import datetime
import re


def cell(v):
    return v["value"] if isinstance(v, dict) else v


def when(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))


def sig3(x):
    """The dashboard's numbers: {digits: 3, compact: true}: 3 significant figures, thousands as K (1,390 -> 1.39K)."""
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= div:
            return f"{x / div:.3g}{suffix}"
    return f"{x:.3g}"


def week_of(t):
    """ISO week (from Monday) of the run's written date, never converted to another zone, as the row model buckets it."""
    day = datetime.date.fromisoformat(t[:10])
    start = day - datetime.timedelta(days=day.weekday())
    return f"Week of {start.day} {start.strftime('%b')} {start.year}", start


def weekly_oracle(runs, span=None):
    """{kind: {week label: count}} of `runs`, over every week from the first to the last of `span` (default: `runs`), 0 in
    an empty week. WHY a span: a filtered chart keeps the whole file's weeks on its axis (it never flips while filtering)."""
    weeks = {}
    for r in span or runs:
        label, start = week_of(r["t"])
        weeks[start] = label
    span, d = [], min(weeks)
    while d <= max(weeks):
        span.append(f"Week of {d.day} {d.strftime('%b')} {d.year}")
        d += datetime.timedelta(days=7)
    out = {k: {w: 0 for w in span} for k in {r["kind"] for r in runs}}
    for r in runs:
        out[r["kind"]][week_of(r["t"])[0]] += 1
    return out


GAUGE = """(key) => { const root = document.querySelector(`#example .dd-panel[data-panel='${key}'] .dv-gauge`); if (!root) return null;
  const track = root.querySelector('.dv-gauge-track'), fill = root.querySelector('.dv-gauge-fill');
  if (!track || !fill) return { missing: true };
  const arc = track instanceof SVGGeometryElement;
  return { shape: root.dataset.shape, arc, value: (root.querySelector('.dv-gauge-num') || {}).textContent,
    frac: arc ? fill.getTotalLength() / track.getTotalLength() : fill.getBoundingClientRect().width / track.getBoundingClientRect().width }; }"""


TRACKER = """(key) => [...document.querySelectorAll(`#example .dd-panel[data-panel='${key}'] .dv-tracker-row`)].map((r) => ({
  label: r.querySelector('.dv-tracker-label').textContent.trim(),
  blocks: [...r.querySelectorAll('.dv-tracker-block')].map((b) => ({ bg: getComputedStyle(b).backgroundColor, title: b.title, state: b.dataset.state, w: b.getBoundingClientRect().width })) }))"""


# every line the panel's Vega view draws: its series (or colour field) and its points read back through Vega's own scales
LINES = """([key, xf, cf]) => { const el = document.querySelector(`#example .dd-panel[data-panel="${key}"] .dv-view`); const v = el && el.vegaView; if (!v) return null;
  const out = { lines: [], rects: 0 };
  const walk = (n) => { if (!n) return;
    if (n.marktype === 'line' && n.role === 'mark' && n.items.length) {
      const d0 = n.items[0].datum || {};
      out.lines.push({ series: d0[cf] ?? d0.series ?? null, n: n.items.length,
        points: n.items.map((it) => [it.datum && it.datum[xf], Number.isFinite(it.y) && it.defined !== false ? Math.round(v.scale('y').invert(it.y) * 1e4) / 1e4 : null]) }); }
    if (n.marktype === 'rect' && n.role === 'mark') out.rects += n.items.length;
    (n.items || []).forEach(walk); };
  walk(v.scenegraph().root); return out; }"""


def probe(page, tone, scope):
    """The colour a tone token resolves to inside `scope` (a throwaway element wearing var(--dv-tone-<tone>))."""
    return page.evaluate("""([sel, tone]) => { const host = document.querySelector(sel); if (!host) return null; const p = document.createElement('i');
      p.style.cssText = `position:absolute;width:1px;height:1px;background:var(--dv-tone-${tone})`; host.append(p);
      const c = getComputedStyle(p).backgroundColor; p.remove(); return c; }""", [scope, tone])


def tile_theme(page):
    """The first card tile's background and the surface token it is made from (a probe wearing var(--dv-bg))."""
    return page.evaluate("""() => { const tile = document.querySelector('#example .dd-panel:not(.dd-panel-text)'), p = document.createElement('i');
      p.style.cssText = 'position:absolute;width:1px;height:1px;background:var(--dv-bg)'; tile.append(p); const token = getComputedStyle(p).backgroundColor; p.remove();
      return { tile: getComputedStyle(tile).backgroundColor, token }; }""")


def luminance(css):
    """0..1 from rgb(…) in 0-255, or color(srgb …) in 0-1 (a color-mix() token resolves to the latter)."""
    ch = [float(x) for x in re.findall(r"[\d.]+", css.replace("srgb", ""))[:3]]
    return (sum(ch) / 3 if "color(" in css else sum(ch) / (3 * 255)) if len(ch) == 3 else None


# the whole Vega drawing (axes, legends, every facet cell) inside its canvas, and the canvas inside its tile
FITS = """(key) => { const sec = document.querySelector(`#example .dd-panel[data-panel="${key}"]`), el = sec && sec.querySelector('.dv-view');
  const v = el && el.vegaView, c = el && el.querySelector('canvas'); if (!v || !c) return null;
  const b = v.scenegraph().root.bounds, o = v.origin(), cr = c.getBoundingClientRect(), tr = sec.getBoundingClientRect();
  return { drawn: Math.round(b.x2 + o[0]), canvas: Math.round(cr.width), right: Math.round(cr.right), tile: Math.round(tr.right) }; }"""


def looks(ctx, path, ready, name):
    """Light and dark at 1440 and 390 px: one column and no sideways scroll on a phone, side by side on a desktop, and the
    tiles follow the theme. WHY the tile, not <data-views>: inside a dashboard tile the view is transparent by design
    (PEP 0005 §5); the tile is the surface (the measure gallery/examples/sim-to-real/checks.py's looks() takes)."""
    for dark in (False, True):
        for width, mobile in ((1440, False), (390, True)):
            p = ctx.page(path, width=width, height=1000 if width > 400 else 844, dark=dark, mobile=mobile)
            ready(p)
            m = p.evaluate("""() => { const g = document.querySelector('#example .dd-grid').getBoundingClientRect();
              const ps = [...document.querySelectorAll('#example .dd-panel')].map((e) => Math.round(e.getBoundingClientRect().width));
              return { scroll: document.scrollingElement.scrollWidth, grid: Math.round(g.width), widths: ps }; }""")
            th = tile_theme(p)
            lum = luminance(th["tile"])
            tag = f"{name} {'dark' if dark else 'light'}, {width} px"
            if width == 390:
                ctx.check(f"{tag}: one column and no sideways page scroll", m["scroll"] <= 390 and all(abs(w - m["grid"]) <= 1 for w in m["widths"]), m)
            else:
                ctx.check(f"{tag}: panels side by side, no sideways scroll", len(set(m["widths"])) > 1 and m["scroll"] <= width, m["widths"])
            want = "rgb(26, 26, 26)" if dark else "rgb(255, 255, 255)"
            ctx.check(f"{tag}: the tiles are made from Vibe Tracks' surface token ({want}) and follow the theme",
                      th["token"] == want and lum is not None and (lum < 0.3) == dark and (dark or th["tile"] == want), th)
            p.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + window.scrollY - 70)")
            p.wait_for_timeout(200)
            ctx.shot(p, f"{name}-{'dark' if dark else 'light'}-{width}")
            p.context.close()
