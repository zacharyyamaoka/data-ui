"""Browser checks for this case (run by tests/browser/checks.py): the map view on robotparts' sellers. MapLibre's
worker ships beside the bundle, nothing comes from a tile server, rows at one point count together, markerColor from
a property or a token, markers open their records, the map pans, light / dark at 1280 and 390 px."""

V = "#example"
CASE = "robotparts-sellers-map"


def _open(ctx, path, view, **kw):
    """ctx.page() waits for the status line; then wait for the view the element says it drew."""
    page = ctx.page(path, **kw)
    page.wait_for_selector(f"{V}[data-view='{view}'] .dv-map-marker", timeout=15000)
    page.wait_for_timeout(500)
    return page


def _frame(page):
    """Scroll the view to the top of the window, below the site's sticky header, for a screenshot."""
    page.evaluate("""() => {
      const el = document.querySelector('#example'), bar = document.querySelector('header.top, .top');
      window.scrollTo(0, el.getBoundingClientRect().top + scrollY - (bar ? bar.offsetHeight : 0) - 8);
    }""")
    page.wait_for_timeout(150)


def run(ctx, path):
    check = ctx.check
    worker = ctx.page(path)
    loaded = worker.evaluate("performance.getEntriesByType('resource').map(e => e.name.split('/').slice(-2).join('/')).filter(n => n.includes('maplibre'))")
    worker.context.close()
    check("map: MapLibre's worker ships beside the map bundle (dist/views/maplibre-gl-worker.mjs)", "views/maplibre-gl-worker.mjs" in loaded, loaded or "the worker was not requested")
    if "views/maplibre-gl-worker.mjs" not in loaded:
        return

    page = _open(ctx, path, "map")
    markers = page.locator(f"{V} .dv-map-marker").count()
    counted = page.locator(f"{V} .dv-map-marker.dv-map-many").count()
    status = page.inner_text(f"{V} .dv-status")
    check("map: 243 'ships to' rows at 155 points, counted where sellers share a country; the rest say why they have no point",
          markers == 155 and counted > 0 and "72 without coordinates (too small for Natural Earth 1:110m)" in status, status)
    canvas = page.evaluate("(() => { const c = document.querySelector('#example canvas.maplibregl-canvas'); return c ? [c.width, c.height] : null; })()")
    check("map: the bundled Natural Earth basemap draws on a WebGL canvas, with no tile server", bool(canvas) and canvas[0] > 300, canvas)
    colours = page.evaluate("[...new Set([...document.querySelectorAll('#example .dv-map-marker')].map(e => e.style.getPropertyValue('--dv-pin')))]")
    check("map: markerColor: seller gives the sellers their own colours", len(colours) >= 2, colours)
    many = page.locator(f"{V} .dv-map-marker.dv-map-many").first
    n = int(many.inner_text())
    many.click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable")
    listed = page.locator(f"{V} .dv-peek .dv-peektable tbody tr").count()
    check("map: a counted marker lists the rows at that point", listed == n, f"marker reads {n}, peek lists {listed}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    _frame(page)
    page.click(f"{V} .maplibregl-ctrl-zoom-in")
    page.wait_for_timeout(600)
    m = page.locator(f"{V} .dv-map-marker").first.bounding_box()
    box = page.locator(f"{V} .dv-map-mount").bounding_box()
    page.mouse.move(box["x"] + 30, box["y"] + box["height"] - 40)
    page.mouse.down()
    page.mouse.move(box["x"] + 150, box["y"] + box["height"] - 80, steps=10)
    page.mouse.up()
    page.wait_for_timeout(400)
    m2 = page.locator(f"{V} .dv-map-marker").first.bounding_box()
    check("map: a drag pans the map and the markers move with it", abs(m2["x"] - m["x"]) > 50, f"first marker x {m['x']:.0f} -> {m2['x']:.0f}")

    page.click(f"{V} .dv-tab[data-name='Where sellers are based']")
    page.wait_for_timeout(800)
    based = page.locator(f"{V} .dv-map-marker").all()
    page.locator(f"{V} .dv-map-marker[title='Hong Kong']").click()
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    peek = page.inner_text(f"{V} .dv-peek")
    check("map: a single marker opens its row (Hong Kong's hand-entered point is marked assumed)", len(based) == 3 and "aifitlab.com" in peek, page.inner_text(f"{V} .dv-peek h2"))
    page.keyboard.press("Escape")
    page.click(f"{V} .dv-tab[data-name='Ships to, one colour']")
    page.wait_for_timeout(800)
    one = page.evaluate("[...new Set([...document.querySelectorAll('#example .dv-map-marker')].map(e => e.style.getPropertyValue('--dv-pin')))]")
    want = page.evaluate("document.querySelector('#example').tokens().series[2]")
    check("map: markerColor: var(--data-series-3) resolves from the tokens", one == [want], f"{one} vs series-3 {want}")
    page.context.close()

    for dark in (False, True):
        for width, mobile in ((1280, False), (390, True)):
            page = _open(ctx, path, "map", width=width, height=900 if width > 400 else 844, dark=dark, mobile=mobile)
            scheme = "dark" if dark else "light"
            scroll = page.evaluate("document.scrollingElement.scrollWidth")
            drawn = page.locator(f"{V} .dv-map-marker").count()
            check(f"map, {scheme}, {width} px: markers on the map, no sideways page scroll", drawn == 155 and scroll <= width, f"{drawn} markers, scrollWidth {scroll}")
            _frame(page)
            page.wait_for_timeout(300)
            ctx.shot(page, f"{CASE}-{scheme}-{width}")
            page.context.close()
