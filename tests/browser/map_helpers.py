"""Shared helpers for the map cases' checks.py (docs/CONTRACT.md §42). Every expected number a check compares with is
computed by the case from its own JSON with the plain-Python oracles here (haversine on Turf's earth radius, ray-cast
point in polygon), never with the map view's code. Measurements come from the running map: rendered features
(MapLibre's queryRenderedFeatures on `el.dvMap`), the camera, getBoundingClientRect, the legend's drawn counts and the
peek after a click."""

import json
import math
import pathlib

V = "#example"
R_KM = 6371.0088  # Turf's earth radius (meters / 1000), so a distance oracle and the map agree to the metre


def rows(here, name):
    return json.loads((pathlib.Path(here) / name).read_text(encoding="utf-8"))["rows"]


def val(cell):
    """A cell's value (a rich cell's .value), as data-ui's cellValue."""
    return cell.get("value") if isinstance(cell, dict) else cell


def km(a, b):
    """Great-circle km between two [lat, lng]."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(h))


def inside(pt, ring):
    """Ray-cast point-in-polygon; pt and ring vertices as [lng, lat]."""
    x, y = pt
    hit = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def scope(dash):
    """The map view's element: the page's own, or inside a dashboard panel."""
    return f"{V} .dd-panel .dv-view-map" if dash else f"{V} .dv-view-map"


def ready(ctx, page, dash=False, timeout=30000):
    """The map has drawn: its element carries the camera, MapLibre has loaded and settled, and its tiles are in."""
    sel = scope(dash)
    page.wait_for_selector(f"{sel}[data-zoom]", timeout=timeout)
    ok = ctx.until(page, """(s) => { const m = document.querySelector(s).dvMap;
      return m && m.loaded() && !m.isMoving() && m.areTilesLoaded(); }""", sel)
    ctx.frames(page, 3)
    return ok


def open_case(ctx, path, view=None, dash=False, **kw):
    page = ctx.page(path, **kw)
    if view:
        page.click(f"{V} .dv-tab[data-name='{view}']")
        page.wait_for_timeout(300)
    ready(ctx, page, dash)
    return page


def rendered(page, layers, dash=False):
    """Features drawn on screen by these layer ids (those that exist): a list of their properties, deduped by source
    and feature id (a polygon spanning tiles is reported once per tile by MapLibre)."""
    return page.evaluate("""([s, ids]) => { const m = document.querySelector(s).dvMap;
      const layers = ids.filter((id) => m.getLayer(id)); if (!layers.length) return [];
      const seen = new Map();
      for (const f of m.queryRenderedFeatures({ layers })) { const k = f.layer.id + ':' + (f.id ?? JSON.stringify(f.properties)); if (!seen.has(k)) seen.set(k, f.properties); }
      return [...seen.values()]; }""", [scope(dash), list(layers)])


def model_row(page, i, dash=False):
    """Row i of the view's own row model (what the map's feature indexes point at)."""
    return page.evaluate("([s, i]) => { const el = document.querySelector(s).closest('data-views'); const r = el.model.rows[i]; return r ? { id: r.id } : null; }", [scope(dash), i])


def source_features(page, source, dash=False):
    """Every feature of a GeoJSON source as the view gave it (all of them, on screen or not)."""
    return page.evaluate("""([s, id]) => { const src = document.querySelector(s).dvMap.getSource(id); const d = src && src._data;
      const fc = d && (d.geojson || d); return fc && fc.features ? fc.features.map((f) => f.properties) : null; }""", [scope(dash), source])


def click_feature(page, layer, test_js, dash=False):
    """Click the first rendered feature of `layer` for which `test_js` (a JS function of properties) is true, at a pixel
    inside it (a polygon's label point via queryRenderedFeatures hit-test, else its projected coordinate). Returns the
    properties clicked, or None."""
    # WHY instant: the site scrolls smoothly, and a click computed before the scroll ends lands on a neighbour
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center', behavior: 'instant' })", scope(dash))
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    at = page.evaluate("""([s, layer, test]) => { const el = document.querySelector(s), m = el.dvMap, ok = eval(test);
      const c = m.getCanvas().getBoundingClientRect();
      // a convex polygon (a hexagon, a Voronoi cell) of the source: click the mean of its vertices, which is inside it
      const src = m.getSource(m.getLayer(layer).source), d = src && src._data, fc = d && (d.geojson || d);
      for (const f of (fc && fc.features) || []) {
        if (!f.geometry || f.geometry.type !== 'Polygon' || !ok(f.properties) || !/^dvl-[0-9]+$/.test(layer) || !(f.properties._h3 || f.properties._site != null)) continue;
        const ring = f.geometry.coordinates[0].slice(0, -1), mx = ring.reduce((a, p) => a + p[0], 0) / ring.length, my = ring.reduce((a, p) => a + p[1], 0) / ring.length;
        const clickable = m.getStyle().layers.map((l) => l.id).filter((id) => /^dvl-/.test(id));
        for (const [px, py] of [[mx, my], ...ring.map((p) => [(p[0] + mx) / 2, (p[1] + my) / 2]), ...ring.map((p) => [(3 * mx + p[0]) / 4, (3 * my + p[1]) / 4])]) {
          const q = m.project([px, py]);
          if (q.x < 4 || q.y < 4 || q.x > c.width - 4 || q.y > c.height - 4) continue;
          const top = m.queryRenderedFeatures([q.x, q.y], { layers: clickable })[0];
          if (top && top.layer.id === layer && top.id === f.id) return { x: c.x + q.x, y: c.y + q.y, props: f.properties };
        }
      }
      // scan a grid of screen points for one whose top feature on this layer passes the test
      for (let y = 10; y < c.height - 10; y += 4) for (let x = 10; x < c.width - 10; x += 4) {
        const f = m.queryRenderedFeatures([x, y], { layers: [layer] })[0];
        if (!f || !ok(f.properties)) continue;
        // WHY a neighbourhood: a pixel on a shared border can resolve to the neighbour once sub-pixel offsets apply
        const deep = [[-3, 0], [3, 0], [0, -3], [0, 3]].every(([dx, dy]) => { const g = m.queryRenderedFeatures([x + dx, y + dy], { layers: [layer] })[0]; return g && g.id === f.id; });
        if (deep) return { x: c.x + x, y: c.y + y, props: f.properties };
      }
      return null; }""", [scope(dash), layer, test_js])
    if at:
        page.mouse.click(at["x"], at["y"])
    return at and at["props"]


def legend(page, dash=False):
    """The legend panel as drawn: {answer, groups: [{title, rows: [[label, n]], none}]}."""
    return page.evaluate("""(s) => { const p = document.querySelector(s).querySelector('.dv-map-panel'); if (!p) return null;
      const num = (t) => t ? Number(t.replace(/,/g, '')) : null;
      return { answer: p.querySelector('.dv-map-answer').textContent.trim(), groups: [...p.querySelectorAll('section')].map((sec) => ({
        title: (sec.querySelector('h4') || {}).textContent || '',
        rows: [...sec.querySelectorAll('.dv-map-classes li:not(.dv-map-none), .dv-map-bands tr')].map((li) => [li.querySelector('span, td').textContent.trim(), num((li.querySelector('.dv-map-n') || {}).textContent)]),
        none: num((sec.querySelector('.dv-map-none .dv-map-n') || {}).textContent), note: (sec.querySelector('.dv-map-note-text') || {}).textContent || '' })) }; }""", scope(dash))


def peek_rows(page):
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=10000)
    t = page.locator(f"{V} .dv-peek .dv-peektable tbody tr")
    return t.count(), page.inner_text(f"{V} .dv-peek h2")


def camera(page, sel):
    return page.evaluate("(s) => { const m = (document.querySelector(s) || {}).dvMap; if (!m) return null; const c = m.getCenter(); return [c.lng, c.lat, m.getZoom()]; }", sel)


def drag_panel(ctx, page, case, dash=False):
    """The legend panel's splitter: a drag changes its width, measured; a reload keeps it; a double-click resets."""
    check = ctx.check
    s = scope(dash)
    # a record peek left open by an earlier click lies over the panel's edge: close it, and bring the map into view
    if page.locator(f"{V} .dv-peek:not([hidden])").count():
        page.keyboard.press("Escape")
        ctx.until(page, "() => !document.querySelector('#example .dv-peek:not([hidden])')")
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center', behavior: 'instant' })", s)
    ctx.frames(page, 2)
    before = page.evaluate("(s) => document.querySelector(s + ' .dv-map-panel').getBoundingClientRect().width", s)
    h = page.locator(f"{s} .dv-splitter").first.bounding_box()
    if not h:
        check(f"{case}: the legend panel has a drag handle", False, "no .dv-splitter")
        return
    vh = page.viewport_size["height"]
    y = min(max(h["y"] + h["height"] / 2, h["y"] + 10, 20), h["y"] + h["height"] - 10, vh - 20)
    page.mouse.move(h["x"] + h["width"] / 2, y)
    page.mouse.down()
    page.mouse.move(h["x"] - 90, y, steps=8)
    page.mouse.up()
    ctx.frames(page, 2)
    after = page.evaluate("(s) => document.querySelector(s + ' .dv-map-panel').getBoundingClientRect().width", s)
    check(f"{case}: dragging the legend's left edge 90 px widens it by about 90 px", 70 <= after - before <= 110, f"{before:.0f} -> {after:.0f} px")
    page.reload()
    page.wait_for_selector(f"{s} .dv-map-panel", timeout=20000)
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center', behavior: 'instant' })", s)
    ctx.frames(page, 3)
    kept = page.evaluate("(s) => document.querySelector(s + ' .dv-map-panel').getBoundingClientRect().width", s)
    check(f"{case}: the legend's width is remembered across a reload", abs(kept - after) <= 2, f"{after:.0f} -> {kept:.0f} px")
    page.dblclick(f"{s} .dv-splitter")
    ctx.frames(page, 2)
    reset = page.evaluate("(s) => document.querySelector(s + ' .dv-map-panel').getBoundingClientRect().width", s)
    check(f"{case}: a double-click on the handle resets the width", abs(reset - before) <= 2, f"{reset:.0f} vs default {before:.0f} px")


def themes(ctx, path, case, view=None, dash=False, extra=None):
    """Light and dark at 1280 and 390 px: the map paints a canvas, the legend is beside it (1280) or under it (390)
    with a real size, no sideways page scroll; a screenshot each. `extra(page, scheme, width)` adds case checks."""
    check = ctx.check
    s = scope(dash)
    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = open_case(ctx, path, view, dash, width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            m = page.evaluate("""(s) => { const el = document.querySelector(s), r = (q) => { const e = el.querySelector(q); if (!e) return null; const b = e.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; };
              const big = [...el.querySelectorAll('canvas.maplibregl-canvas')].map((c) => c.getBoundingClientRect()).sort((a, b) => b.width * b.height - a.width * a.height)[0];
              return { stage: r('.dv-map-stage'), panel: r('.dv-map-panel'), canvas: big ? [big.x, big.y, big.width, big.height] : null, scroll: document.scrollingElement.scrollWidth,
                bg: getComputedStyle(el.querySelector('.dv-map-panel') || el).backgroundColor }; }""", s)
            st, pn = m["stage"], m["panel"]
            if width > 400:
                placed = pn is None or (pn[0] >= st[0] + st[2] - 1 and pn[3] > 100)
            else:
                placed = pn is None or (pn[1] >= st[1] + st[3] - 1 and pn[3] > 40 and pn[2] >= st[2] - 1)
            check(f"{case}, {scheme}, {width} px: the map paints, the legend sits {'beside' if width > 400 else 'under'} it, no sideways scroll",
                  bool(m["canvas"]) and m["canvas"][2] > 120 and m["canvas"][3] > 100 and placed and m["scroll"] <= width,
                  f"canvas {m['canvas'] and [round(v) for v in m['canvas'][2:]]}, stage {st and [round(v) for v in st]}, legend {pn and [round(v) for v in pn]}, scrollWidth {m['scroll']}")
            if dark:
                lum = sum(int(x) for x in m["bg"].replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3])
                check(f"{case}, dark, {width} px: the legend takes the dark surface", lum < 300, m["bg"])
            if extra:
                extra(page, scheme, width)
            page.evaluate("""() => { const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
              window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8); }""")
            ctx.frames(page, 2)
            ctx.shot(page, f"{case}-{scheme}-{width}")
            page.context.close()
