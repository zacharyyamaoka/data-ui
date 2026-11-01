"""Browser checks for the object library's 3D shelf (run by tests/browser/checks.py) and its prototype page.

What they hold the 3D cards to (docs/CONTRACT.md §13), each measured in the page, never assumed from the DOM:
  - posters first: the cards draw the library's own .webp renders; no 3D engine and no model is fetched before a
    hover, and no WebGL context exists;
  - one WebGL context for the page however many models have been shown; at most 4 animate at once;
  - hover turns the model (the card's canvas changes between frames); a drag turns it and does not open the peek;
  - the peek opens on an orbit viewer that goes live on its own; the wheel zooms it; its splitter drags;
  - 390 px and dark: the same, with no sideways page scroll;
  - the prototype page: all five proposals draw, the bottom-right switch is remembered across a reload, the URL never
    changes.
The numbers (first poster, engine load, first model, heap) are written into the check values: the speed KPIs."""

import json
import time

V = "#example"
# WHY read, not typed: the case's sample is rebuilt by source/build.py (409 rows, then 366 public-safe rows, 2026-10-27)
ROWS = len(json.loads((__import__("pathlib").Path(__file__).parent / "objects.json").read_text(encoding="utf-8"))["rows"])
COUNT_GL = """
(() => {
  window.__gl = { made: 0, canvases: new Set() };
  const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
    const ctx = orig.call(this, kind, ...rest);
    if (ctx && /webgl/.test(String(kind)) && !window.__gl.canvases.has(this)) { window.__gl.canvases.add(this); window.__gl.made++; }
    return ctx;
  };
})();
"""


def open_page(ctx, path, **kw):
    page = ctx.page(path, **kw)
    page.context.add_init_script(COUNT_GL)
    page.reload()
    page.wait_for_selector(f"{V} .dv-cards-card data-mesh", timeout=15000)
    page.wait_for_timeout(400)
    return page


def requests_of(page):
    return page.evaluate("performance.getEntriesByType('resource').map(e => e.name)")


def gl(page):
    return page.evaluate("window.__gl ? window.__gl.made : -1")


def stats(page):
    return page.evaluate("customElements.get('data-mesh').stats()")


def frame(page, sel):
    return page.evaluate(f"(() => {{ const m = document.querySelector('{sel}'); return m && m.canvas ? m.canvas.toDataURL('image/png').length + ':' + m.canvas.toDataURL('image/png').slice(-64) : null; }})()")


def hover_live(page, i, timeout=8000):
    card = page.locator(f"{V} .dv-cards-card data-mesh").nth(i)
    card.scroll_into_view_if_needed()
    card.hover()
    page.wait_for_function(f"(() => {{ const m = document.querySelectorAll('{V} .dv-cards-card data-mesh')[{i}]; return m && m.classList.contains('dv-mesh-live'); }})()", timeout=timeout)
    return card


SILHOUETTE = """
(el) => {
  // the object's box in element pixels: a pixel is object when it differs from its row's backdrop, read as the line
  // between the row's leftmost and rightmost pixels (white posters, MuJoCo's vertical gradient and a clear colour alike)
  const W = el.clientWidth, H = el.clientHeight;
  const box = (src, sx, sy, sw, sh, dx, dy, dw, dh) => {
    const c = document.createElement('canvas'); c.width = W; c.height = H;
    const x = c.getContext('2d', { willReadFrequently: true });
    x.fillStyle = getComputedStyle(el).backgroundColor || '#fff'; x.fillRect(0, 0, W, H);
    x.drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh);
    const d = x.getImageData(0, 0, W, H).data;
    let x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (let y = 0; y < H; y++) {
      const L = (y * W) * 4, R = (y * W + W - 1) * 4;
      for (let i = 0; i < W; i++) {
        const t = i / (W - 1), p = (y * W + i) * 4;
        let diff = 0;
        for (let k = 0; k < 3; k++) diff = Math.max(diff, Math.abs(d[p + k] - (d[L + k] * (1 - t) + d[R + k] * t)));
        if (diff > 24) { if (i < x0) x0 = i; if (i > x1) x1 = i; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
    }
    return x1 < 0 ? null : [x0, y0, x1 + 1, y1 + 1];
  };
  const img = el.poster, S = Math.min(W, H);
  const poster = box(img, 0, 0, img.naturalWidth, img.naturalHeight, (W - S) / 2, (H - S) / 2, S, S);
  const live = box(el.canvas, 0, 0, el.canvas.width, el.canvas.height, 0, 0, W, H);
  return { poster, live, W, H, camera: (JSON.parse(el.getAttribute('view') || '{}').camera) || 'default' };
}
"""


CAMERA_CHECK = ("3D camera: the live model's frame 0 matches its poster (silhouette width and height within 3 %, "
                "10 cards: scans and MuJoCo primitives; CONTRACT §29)")


def camera_match(ctx, path):
    """Zach (2026-10-26): the live 3D starts where the poster was taken. Frame 0 (reduced motion: no turntable) against
    the poster as the card draws it: the silhouette box's width and height within 3 %."""
    check = ctx.check
    page = ctx.page(path)
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    page.wait_for_selector(f"{V} .dv-cards-card data-mesh", timeout=15000)
    rows = []
    for view, n in (("Everything · real scans first", 5), ("Shelf · by type", 5)):
        page.locator(f"{V} .dv-tab, {V} [role=tab]").filter(has_text=view).first.click()
        page.wait_for_timeout(500)
        for i in range(n):
            m = page.locator(f"{V} .dv-cards-card data-mesh").nth(i)
            m.scroll_into_view_if_needed()
            page.wait_for_function(f"(() => {{ const i = document.querySelectorAll('{V} .dv-cards-card .dv-mesh-poster')[{i}]; return i && i.complete && i.naturalWidth; }})()", timeout=8000)
            m.hover()
            page.wait_for_function(f"document.querySelectorAll('{V} .dv-cards-card data-mesh')[{i}].classList.contains('dv-mesh-live')", timeout=10000)
            page.wait_for_timeout(120)
            r = m.evaluate(SILHOUETTE)
            if r["poster"] and r["live"]:
                pw, ph = r["poster"][2] - r["poster"][0], r["poster"][3] - r["poster"][1]
                lw, lh = r["live"][2] - r["live"][0], r["live"][3] - r["live"][1]
                rows.append((view.split(" ")[0], r["camera"], round(lw / pw - 1, 3), round(lh / ph - 1, 3),
                             round(((r["live"][0] + r["live"][2]) - (r["poster"][0] + r["poster"][2])) / 2 / r["W"], 3)))
            page.mouse.move(2, 2)
    worst = max((max(abs(w), abs(h)) for _, _, w, h, _ in rows), default=1)
    # WHY a dict value: tools/publish_checks.py reads `worst_pct` from checks.json into Vibe Tracks
    # (data-ui track, KPI mesh_first_frame_outline_pct; CONTRACT §29), so every `npm test` run updates the KPI
    check(CAMERA_CHECK, len(rows) >= 8 and worst <= 0.03,
          {"worst_pct": round(worst * 100, 2), "n": len(rows), "limit_pct": 3.0,
           "text": f"worst {worst:.1%}; " + "; ".join(f"{c} w{w:+.1%} h{h:+.1%} dx{x:+.1%}" for _, c, w, h, x in rows)})
    bgs = page.evaluate(f"[...document.querySelectorAll('{V} .dv-cards-card data-mesh')].slice(0, 4).map(m => [getComputedStyle(m).backgroundColor, m.getAttribute('background')])")
    check("3D background: match (the default) paints the live view on the poster's own backdrop", all(b[1] == "match" and b[0] not in ("", "rgba(0, 0, 0, 0)") for b in bgs), bgs)
    page.context.close()


def run(ctx, path):
    camera_match(ctx, path)
    check = ctx.check
    t0 = time.time()
    page = open_page(ctx, path)
    reqs = requests_of(page)
    posters = page.evaluate(f"[...document.querySelectorAll('{V} .dv-cards-card .dv-mesh-poster')].filter(i => i.complete).map(i => i.naturalWidth > 0)")
    cards = page.locator(f"{V} .dv-cards-card").count()
    status = page.inner_text(f"{V} .dv-status")
    timing = page.evaluate("""(() => { const nav = performance.getEntriesByType('navigation')[0];
      const imgs = performance.getEntriesByType('resource').filter(e => /thumbs\\/.*\\.webp/.test(e.name));
      return { domContentLoaded: Math.round(nav.domContentLoadedEventEnd), firstPoster: imgs.length ? Math.round(Math.min(...imgs.map(e => e.responseEnd))) : null,
               posters: imgs.length, posterBytes: imgs.reduce((s, e) => s + (e.transferSize || e.encodedBodySize || 0), 0),
               heapMB: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null }; })()""")
    check("3D shelf: posters first: the cards draw the library's own .webp renders, and no 3D engine, no model and no WebGL context exist before a hover",
          status.startswith(f"{ROWS} of {ROWS}") and cards >= 8 and posters and all(posters) and not any("/views/mesh.js" in r for r in reqs)
          and not any(r.endswith(".glb") for r in reqs) and gl(page) == 0,
          f"{status.split(' · ')[0]}; {cards} cards in the DOM; {sum(posters)} posters loaded; first poster at {timing['firstPoster']} ms; "
          f"{timing['posters']} posters, {timing['posterBytes'] // 1024} KB; heap {timing['heapMB']} MB; 0 .glb, engine not loaded, {gl(page)} WebGL contexts")

    # ---- hover: the engine loads once, the model turns
    t = time.time()
    hover_live(page, 0)
    engine_ms = round((time.time() - t) * 1000)
    a = frame(page, f"{V} .dv-cards-card data-mesh")
    page.wait_for_timeout(350)
    b = frame(page, f"{V} .dv-cards-card data-mesh")
    s = stats(page)
    check("3D shelf: hovering a card loads the 3D engine and that card's model, and turns it (its canvas changes between frames)",
          a and b and a != b and s["contexts"] == 1 and s["modelsLoaded"] == 1,
          f"hover → live in {engine_ms} ms (engine + first model; model parse {round(s['firstModelMs'] or 0)} ms); frame {round(s['renderMs'], 2)} ms; {s['bytes'] // 1024} KB fetched")

    # ---- many hovers: still one context, at most 4 live
    for i in range(1, 10):
        hover_live(page, i)
    page.mouse.move(2, 2)
    s = stats(page)
    glbs = [r for r in requests_of(page) if r.endswith(".glb")]
    check("3D shelf: after 10 cards were hovered the page holds ONE WebGL context, at most 4 models ever animated at once, and only the 10 hovered models were fetched",
          gl(page) == 1 and s["contexts"] == 1 and s["contextsMade"] == 1 and s["liveMax"] <= 4 and len(glbs) == 10,
          f"WebGL contexts created {gl(page)}; live max {s['liveMax']} (cap {s['maxLive']}); {len(glbs)} .glb, {s['bytes'] // 1024} KB; {s['models']} models cached")

    # ---- drag turns the model and does not open the peek
    m = page.locator(f"{V} .dv-cards-card data-mesh").nth(2)
    m.scroll_into_view_if_needed()
    box = m.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function(f"document.querySelectorAll('{V} .dv-cards-card data-mesh')[2].classList.contains('dv-mesh-live')", timeout=8000)
    sel = f"(() => document.querySelectorAll('{V} .dv-cards-card data-mesh')[2])()"
    f0 = page.evaluate(f"{sel}.canvas.toDataURL().slice(-80)")
    page.mouse.down()
    for k in range(1, 9):
        page.mouse.move(box["x"] + box["width"] / 2 + k * 12, box["y"] + box["height"] / 2 + k * 2)
    page.mouse.up()
    page.wait_for_timeout(120)
    f1 = page.evaluate(f"{sel}.canvas.toDataURL().slice(-80)")
    peeking = page.evaluate(f"document.querySelector('{V}').classList.contains('dv-peeking')")
    check("3D shelf: dragging a card's model turns it, and the drag does not open the card's peek", f0 != f1 and not peeking, f"frame changed: {f0 != f1}; peek open: {peeking}")

    # ---- click: the peek opens on an orbit viewer
    page.mouse.move(2, 2)
    page.locator(f"{V} .dv-cards-card .dv-cards-title").nth(4).click()
    page.wait_for_selector(f"{V} .dv-peek data-mesh.dv-peek-mesh.dv-mesh-live", timeout=8000)
    pk = page.locator(f"{V} .dv-peek data-mesh").bounding_box()
    z0 = frame(page, f"{V} .dv-peek data-mesh")
    page.mouse.move(pk["x"] + pk["width"] / 2, pk["y"] + pk["height"] / 2)
    page.mouse.wheel(0, -400)
    page.wait_for_timeout(150)
    z1 = frame(page, f"{V} .dv-peek data-mesh")
    s = stats(page)
    check("3D shelf: a click opens the peek on an orbit viewer that goes live by itself (no hover), the wheel zooms it, still one WebGL context",
          pk["height"] >= 200 and z0 != z1 and s["contexts"] == 1 and gl(page) == 1,
          f"viewer {pk['width']:.0f}×{pk['height']:.0f}; zoom changed the frame: {z0 != z1}; contexts {gl(page)}")

    # ---- the peek's splitter (Zach's standing rule: every side panel resizes; measured)
    peek = page.locator(f"{V} .dv-peek")
    w0 = peek.bounding_box()["width"]
    split = page.locator(f"{V} .dv-splitter-left").first
    sb = split.bounding_box()
    page.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + 200)
    page.mouse.down()
    page.mouse.move(sb["x"] - 120, sb["y"] + 200, steps=6)
    page.mouse.up()
    page.wait_for_timeout(200)
    w1 = peek.bounding_box()["width"]
    mw = page.locator(f"{V} .dv-peek data-mesh").bounding_box()["width"]
    check("3D shelf: dragging the peek's edge 120 px left widens it ~120 px, and its 3D viewer widens with it", 100 <= w1 - w0 <= 140 and mw > pk["width"] + 80,
          f"peek {w0:.0f} → {w1:.0f} px; viewer {pk['width']:.0f} → {mw:.0f} px")
    page.evaluate("localStorage.clear()")
    ctx.shot(page, "object-db-shelf-peek")
    page.context.close()

    # ---- 390 px and dark
    for dark in (False, True):
        page = open_page(ctx, path, width=390, height=844, mobile=True, dark=dark)
        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        tile = page.locator(f"{V} .dv-cards-card").first.bounding_box()
        page.locator(f"{V} .dv-cards-card .dv-cards-title").first.tap()
        page.wait_for_selector(f"{V} .dv-peek data-mesh.dv-mesh-live", timeout=8000)
        pk = page.locator(f"{V} .dv-peek data-mesh").bounding_box()
        bg = page.evaluate(f"getComputedStyle(document.querySelector('{V} .dv-peek')).backgroundColor")
        check(f"3D shelf at 390 px{' (dark)' if dark else ''}: cards fit, no sideways scroll; a tap opens the peek, whose 3D viewer goes live and fits the screen",
              over <= 0 and tile["width"] <= 390 and pk["width"] <= 390 and gl(page) == 1,
              f"overflow {over} px; card {tile['width']:.0f} px; viewer {pk['width']:.0f}×{pk['height']:.0f}; peek background {bg}")
        ctx.shot(page, f"object-db-shelf-390{'-dark' if dark else ''}")
        page.context.close()

    page = open_page(ctx, path, dark=True)
    hover_live(page, 0)
    page.wait_for_timeout(300)
    lum = page.evaluate(f"(() => {{ const c = getComputedStyle(document.querySelector('{V} .dv-cards-card')).backgroundColor.match(/\\d+/g).map(Number); return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]; }})()")
    check("3D shelf, dark: the cards follow the dark theme and a hovered model still goes live", lum < 60 and gl(page) == 1, f"card luminance {lum:.0f}")
    ctx.shot(page, "object-db-shelf-dark")
    page.context.close()

    prototype(ctx, path.replace("index.html", "prototype/index.html"))


def prototype(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    url0 = page.url
    drawn = {}
    for pid, n in (("shelf", 1), ("ledger", 2), ("tree", 3), ("streams", 4), ("lab", 5)):
        page.locator(f".proto-switch button[data-id='{pid}']").click()
        # WHY count both: [].every() is true before any status line exists
        page.wait_for_function("() => { const v = document.querySelectorAll('#stage data-views'), s = [...document.querySelectorAll('#stage data-views .dv-status')]; return v.length && s.length === v.length && s.every(e => e.textContent.trim()); }", timeout=20000)
        drawn[pid] = page.evaluate("[...document.querySelectorAll('#stage data-views .dv-status')].map(e => e.textContent.split(' · ')[0])")
    page.locator(".proto-switch button[data-id='tree']").click()
    page.wait_for_timeout(300)
    page.reload()
    page.wait_for_selector("#stage data-views", timeout=10000)
    remembered = page.evaluate("document.body.dataset.proposal")
    sw = page.locator(".proto-switch").bounding_box()
    vp = page.viewport_size
    check("prototype: the five proposals each draw their views; the bottom-right switch is remembered across a reload and never touches the URL",
          all(drawn[k] and all(x.strip() for x in drawn[k]) for k in drawn) and remembered == "tree" and page.url == url0
          and sw["x"] + sw["width"] > vp["width"] - 40 and sw["y"] + sw["height"] > vp["height"] - 40,
          json.dumps(drawn)[:300] + f"; after reload: {remembered}; url unchanged: {page.url == url0}")
    # the taxonomy stage: a full-height 3D pane that follows the selection, and resizes from its left edge
    page.wait_for_selector("#p3-stage data-mesh.dv-mesh-live", timeout=10000)
    st = page.locator("#p3-stage").bounding_box()
    handle = page.locator("#p3-stage + .dv-splitter, .dv-splitter-left").last.bounding_box()
    page.mouse.move(handle["x"] + handle["width"] / 2, handle["y"] + 300)
    page.mouse.down()
    page.mouse.move(handle["x"] - 100, handle["y"] + 300, steps=5)
    page.mouse.up()
    page.wait_for_timeout(200)
    st1 = page.locator("#p3-stage").bounding_box()
    check("prototype, proposal 3: the 3D stage beside the graph is live on the biggest node, and its left edge drags it ~100 px wider",
          st["height"] > 500 and 80 <= st1["width"] - st["width"] <= 120, f"stage {st['width']:.0f}×{st['height']:.0f} → {st1['width']:.0f} px wide")
    page.evaluate("localStorage.clear()")
    page.context.close()
