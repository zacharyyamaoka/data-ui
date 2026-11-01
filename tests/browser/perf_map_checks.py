"""The map keeps one MapLibre instance across view switches (lane/perf-map), proved the same as a fresh build and leak-free.

    ~/psu-atlas/.venv/bin/python tests/browser/perf_map_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/lifecycle.html, dist/, gallery/), stops it when
done, writes OUT_DIR/perf-map-checks.json (default reports/media/perf-map) and exits 1 if any check fails.

The oracle for "the same map" is a fresh build: what a map view adopted from a parked instance draws (layer ids, the
basemap source, every marker's position, colour, size and label, the camera's bounds) must equal what a new
maplibregl.Map draws for the same view. Maps are counted by their WebGL contexts (one per maplibre Map; remove()
loses it), page bindings by the lifecycle checks' own window/document/ResizeObserver counters, and the theme by the
pixels of the drawn canvas, never by a class or a call being present.
Kept out of tests/browser/checks.py so a lane editing that file never meets this one (tools/test-all.mjs runs both).
"""

from __future__ import annotations

import io
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lifecycle_checks import HELD  # noqa: E402  the window / MediaQueryList / ResizeObserver counters

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "perf-map"
OUT.mkdir(parents=True, exist_ok=True)
SELLERS = "/gallery/examples/robotparts-sellers-map/views.base"
TABLE, MAP, MAP_CENTERED = "By country", "Where sellers ship", "Ships to, one colour"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
PARK_MS = 400  # the test's parking wait (the shipped one is 45 s): set through the module's exported `parking`
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# every WebGL context the page makes, kept so "live" is the ones not lost (MapLibre's remove() loses its context)
GL = """(() => {
  window.__gls = [];
  const get = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
    const ctx = get.call(this, kind, ...rest);
    if (ctx && /webgl/.test(kind) && !window.__gls.includes(ctx)) window.__gls.push(ctx);
    return ctx;
  };
  window.glNow = () => ({ made: window.__gls.length, live: window.__gls.filter((g) => !g.isContextLost()).length });
})()"""

# what the map draws, from MapLibre and the markers' DOM: the thing a fresh build and a reuse must agree on
SNAPSHOT = """() => {
  const v = window.v, map = v._plugin && v._plugin.map;
  if (!map) return null;
  const r = (x) => Math.round(x * 1000) / 1000;
  const b = map.getBounds();
  const style = map.getStyle();
  return {
    layers: style.layers.map((l) => l.id),
    sources: Object.keys(style.sources),
    countries: (style.sources.countries.data.features || []).length,
    bounds: [[r(b.getWest()), r(b.getSouth())], [r(b.getEast()), r(b.getNorth())]],
    zoom: r(map.getZoom()), minZoom: map.getMinZoom(), maxZoom: map.getMaxZoom(),
    canvas: [map.getCanvas().clientWidth, map.getCanvas().clientHeight],
    markers: [...v.querySelectorAll('.dv-map-marker')].map((m) => {
      // WHY not cssText: MapLibre adds `opacity: 1` to a marker on a later frame, a timing detail and not a drawing
      const ll = v._plugin.markers.find((x) => x.el === m).marker.getLngLat(), at = map.project(ll), box = m.getBoundingClientRect();
      return [m.getAttribute('aria-label'), m.style.getPropertyValue('--dv-pin').trim(), m.style.width, m.style.height, m.textContent,
              r(ll.lng), r(ll.lat), Math.round(at.x), Math.round(at.y), Math.round(box.width), Math.round(box.height)];
    }).sort((a, b) => (a[0] + a[3] + a[4]).localeCompare(b[0] + b[3] + b[4])),
  };
}"""


def differ(got, want):
    """The keys of two snapshots that differ, with the first two differing markers: what a FAIL prints."""
    out = {k: [got.get(k), want.get(k)] for k in want if k != "markers" and got.get(k) != want.get(k)}
    if got.get("markers") != want.get("markers"):
        out["markers"] = [len(got.get("markers") or []), len(want["markers"])] + [[a, b] for a, b in zip(got["markers"] or [], want["markers"]) if a != b][:2]
    return out


def open_page(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(HELD)
    context.add_init_script(GL)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(base + "/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady === true", timeout=WAIT)
    page.evaluate(f"async () => {{ window.mapMod = await import('/dist/views/map.js'); window.parking = window.mapMod.parking || {{}}; window.parking.ms = {PARK_MS}; window.empty = heldNow(); }}")
    return page


def add_views(page, view=None):
    page.evaluate("""([src, view]) => {
      const el = document.createElement('data-views');
      el.id = 'v'; el.setAttribute('src', src); el.setAttribute('no-url', '');
      if (view) el.setAttribute('view', view);
      window.v = el;
      document.body.append(el);
    }""", [SELLERS, view])


def settle(page, name):
    """Click the tab `name` and wait for its view, and for a map, for nothing left to draw."""
    page.evaluate("""async (name) => {
      const v = window.v;
      const done = new Promise((r) => v.addEventListener('data-views-render', r, { once: true }));
      v.querySelector(`.dv-tab[data-name="${name}"]`).click();
      await done;
    }""", name)
    wait_drawn(page)


def wait_drawn(page):
    page.wait_for_function("""() => {
      const v = window.v;
      if (!v || !v.dataset.view) return false;
      if (v.dataset.view !== 'map') return !!v.querySelector('.dv-view');
      const map = v._plugin && v._plugin.map;
      return !!map && map.loaded() && !map.isMoving() && !map._frameRequest && v.querySelectorAll('.dv-map-marker').length > 0;
    }""", timeout=WAIT)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def mean_rgb(page):
    """The drawn map's pixels (a screenshot of the canvas: WebGL that really reached the screen), mean RGB."""
    png = page.locator("#v .maplibregl-canvas").screenshot()
    img = Image.open(io.BytesIO(png)).convert("RGB").resize((64, 40))
    px = list(img.getdata())
    return [round(sum(p[i] for p in px) / len(px)) for i in range(3)]


def fresh_snapshot(page, view):
    """The oracle: a new <data-views> with nothing parked, so its map is a new maplibregl.Map, on `view`."""
    page.evaluate("() => { window.v && window.v.remove(); window.parking.max = 0; }")
    add_views(page, view)
    wait_drawn(page)
    snap = page.evaluate(SNAPSHOT)
    page.evaluate("() => { window.v.remove(); window.parking.max = 1; }")
    return snap


def reuse_is_a_fresh_map(browser, base):
    page = open_page(browser, base)
    # the oracles first, each on a map built from nothing
    fresh = fresh_snapshot(page, MAP)
    fresh_centered = fresh_snapshot(page, MAP_CENTERED)
    # the baselines, taken after MapLibre's module has run once (it keeps one document visibilitychange listener per
    # page, for its workers, whatever the maps do): the page with no element, and with an element showing the table
    page.evaluate("() => { window.empty = heldNow(); }")
    add_views(page, TABLE)
    wait_drawn(page)
    table_only = page.evaluate("heldNow()")
    page.evaluate("() => window.v.remove()")
    page.wait_for_timeout(50)
    gl0 = page.evaluate("glNow()")
    check("oracle: two fresh builds, two maps made, none left alive after remove()", gl0 == {"made": 2, "live": 0}, gl0)

    add_views(page, MAP)
    wait_drawn(page)
    first = page.evaluate(SNAPSHOT)
    check("the first map on the page draws what a fresh build draws", first == fresh, None if first == fresh else differ(first, fresh))
    check("the sellers map has markers to compare (the oracle is not empty)", len(fresh["markers"]) > 20 and fresh["layers"] == ["ocean", "land", "borders"],
          [len(fresh["markers"]), fresh["layers"]])

    # a marker of the view about to be destroyed: after the switch it must not open anything in the old view
    page.evaluate("() => { window.oldMarker = window.v.querySelector('.dv-map-marker'); window.opened = 0; window.v.addEventListener('data-views-open', () => window.opened++); }")
    snaps, made = [], []
    for i in range(5):
        # pan and zoom away first, so an adopted map that kept its old camera cannot pass for a re-framed one
        page.evaluate("() => window.v._plugin.map.jumpTo({ center: [120, -30], zoom: 5 })")
        settle(page, TABLE)
        if i == 0:
            page.evaluate("() => window.oldMarker.click()")
            parked_held = page.evaluate("() => ({ held: heldNow(), empty: window.empty, gl: glNow() })")
        settle(page, MAP)
        snaps.append(page.evaluate(SNAPSHOT))
        made.append(page.evaluate("glNow()"))
    bad = [i for i, s in enumerate(snaps) if s != fresh]
    check("table -> map 5 times: each map draws what a fresh build draws (layers, source, markers, bounds, zoom)", not bad,
          None if not bad else {"switch": bad[0], **differ(snaps[bad[0]], fresh)})
    check("table -> map 5 times: one maplibre Map made, one alive", [m["made"] - gl0["made"] for m in made] == [1] * 5 and all(m["live"] == 1 for m in made),
          [[m["made"] - gl0["made"], m["live"]] for m in made])
    check("a destroyed map view's marker opens nothing", page.evaluate("window.opened") == 0, page.evaluate("window.opened"))
    held, empty = parked_held["held"], parked_held["empty"]
    same_page = all(held[k] == table_only[k] for k in ("window", "document", "observed", "media"))
    check("while parked (the table showing), the page holds what a table that never had a map holds: no map listener or observer",
          same_page, None if same_page else {"parked": held, "table only": table_only})

    # a different map view adopts the same instance: its own center and zoom, as a fresh build of it
    settle(page, MAP_CENTERED)
    centered = page.evaluate(SNAPSHOT)
    check("a map view with its own center and zoom, adopted, draws what a fresh build of it draws", centered == fresh_centered,
          None if centered == fresh_centered else differ(centered, fresh_centered))

    # the theme still recolours an adopted map: the drawn pixels darken, and the land takes the dark --data-bg
    settle(page, TABLE)
    settle(page, MAP)
    light_px = mean_rgb(page)
    light_land = page.evaluate("() => window.v._plugin.map.getPaintProperty('land', 'fill-color')")
    page.evaluate("""async () => {
      const done = new Promise((r) => window.v.addEventListener('data-views-render', r, { once: true }));
      document.documentElement.dataset.theme = 'dark';
      await done;
    }""")
    wait_drawn(page)
    page.wait_for_timeout(100)
    dark_px = mean_rgb(page)
    dark = page.evaluate("() => ({ land: window.v._plugin.map.getPaintProperty('land', 'fill-color'), bg: window.v._plugin.input.tokens.bg, darkTokens: window.v._plugin.input.tokens.dark })")
    check("theme -> dark on an adopted map: the land takes the dark --data-bg", dark["darkTokens"] and dark["land"] == dark["bg"] and dark["land"] != light_land,
          {"light": light_land, **dark})
    check("theme -> dark on an adopted map: the drawn canvas darkens", sum(dark_px) < sum(light_px) - 150, {"light": light_px, "dark": dark_px})
    page.evaluate("() => { delete document.documentElement.dataset.theme; }")

    # removed entirely: the map waits parked for parking.ms, then is removed, and the page is back to empty
    page.evaluate("() => window.v.remove()")
    page.wait_for_timeout(50)
    parked = page.evaluate("() => ({ gl: glNow(), held: heldNow() })")
    check("<data-views> removed: its map is parked (one alive) and holds nothing on the page", parked["gl"]["live"] == 1
          and parked["held"]["window"] == empty["window"] and parked["held"]["document"] == empty["document"] and parked["held"]["observed"] == empty["observed"], parked)
    page.wait_for_timeout(PARK_MS + 400)
    after = page.evaluate("() => ({ gl: glNow(), held: heldNow() })")
    check(f"<data-views> removed: after the parking wait ({PARK_MS} ms here) no maplibre Map is alive", after["gl"]["live"] == 0, after["gl"])
    check("<data-views> removed: window, document and ResizeObserver counts back to the empty page's",
          after["held"]["window"] == empty["window"] and after["held"]["document"] == empty["document"] and after["held"]["observed"] == empty["observed"]
          and after["held"]["media"] == empty["media"], {"after": after["held"], "empty": empty})
    errors = page.errors
    page.context.close()
    return errors


def two_elements_one_parked(browser, base):
    """Two map elements on one page, both removed: the pool keeps at most one (parking.max), the other is removed now."""
    page = open_page(browser, base)
    page.evaluate("() => { window.parking.ms = 60000; }")
    for i in range(2):
        add_views(page, MAP)
        page.evaluate(f"() => {{ window.v.id = 'v{i}'; window['v{i}'] = window.v; }}")
        wait_drawn(page)
    page.evaluate("() => { window.v0.remove(); window.v1.remove(); }")
    page.wait_for_timeout(50)
    gl = page.evaluate("glNow()")
    check("two map elements removed: one map parked, the extra removed at once (parking.max = 1)", gl == {"made": 2, "live": 1}, gl)
    # a new map element adopts the parked one instead of building
    add_views(page, MAP)
    wait_drawn(page)
    gl2 = page.evaluate("glNow()")
    check("a map element added later adopts the parked map (no new map made)", gl2 == {"made": 2, "live": 1}, gl2)
    page.evaluate("() => { window.parking.ms = 1; window.v.remove(); }")
    page.wait_for_timeout(300)
    gl3 = page.evaluate("glNow()")
    check("...and is removed when that element goes and the wait passes", gl3["live"] == 0, gl3)
    errors = page.errors
    page.context.close()
    return errors


# judge r1 finding 5 (2026-10-27): an adopted map with nothing to frame kept the previous view's camera
CAMERA_VIEWS = """([which]) => {
  const el = document.createElement('data-views');
  el.id = 'v'; el.setAttribute('no-url', '');
  window.v = el;
  document.body.append(el);
  const rows = which === 'van'
    ? [{ id: 'a', name: 'A', at: [49.28, -123.12] }, { id: 'b', name: 'B', at: [49.25, -123.1] }, { id: 'c', name: 'C', at: [49.3, -123.0] }]
    : [{ id: 'z', name: 'Z', at: null }];
  el.base = { views: [{ type: 'map', name: 'M', coordinates: 'at', defaultZoom: 7 }] };
  el.data = { properties: { name: { type: 'text' }, at: { type: 'list' } }, rows };
}"""

CAMERA = """() => { const map = window.v._plugin && window.v._plugin.map; if (!map) return null;
  const c = map.getCenter(), r = (x) => Math.round(x * 100) / 100;
  return { center: [r(c.lng), r(c.lat)], zoom: r(map.getZoom()), bearing: r(map.getBearing()), pitch: r(map.getPitch()) }; }"""

MAP_IDLE = """() => { const v = window.v, map = v && v._plugin && v._plugin.map;
  return !!(v && v.dataset.view === 'map' && map && map.loaded() && !map.isMoving()); }"""


def adopted_empty_map_has_fresh_camera(browser, base):
    """A map framed on Vancouver at zoom 7 is parked; an empty map (no points, no center) that adopts it starts where a
    freshly built map starts ([0, 20], zoom 1), not at the last view's camera."""
    page = open_page(browser, base)
    # the oracle: the empty view on a fresh map (nothing parked)
    page.evaluate("() => { window.parking.max = 0; }")
    page.evaluate(CAMERA_VIEWS, ["empty"])
    page.wait_for_function(MAP_IDLE, timeout=WAIT)
    fresh = page.evaluate(CAMERA)
    page.evaluate("() => { window.v.remove(); window.parking.max = 1; }")
    # a map on Vancouver, then parked
    page.evaluate(CAMERA_VIEWS, ["van"])
    page.wait_for_function(MAP_IDLE, timeout=WAIT)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    van = page.evaluate(CAMERA)
    made = page.evaluate("() => glNow().made")
    page.evaluate("() => window.v.remove()")
    # the empty map adopts the parked one
    page.evaluate(CAMERA_VIEWS, ["empty"])
    page.wait_for_function(MAP_IDLE, timeout=WAIT)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    adopted = page.evaluate(CAMERA)
    reused = page.evaluate("() => glNow().made") == made
    check("map adopt: an empty map (no points, no center) that adopts a parked map starts at a fresh map's camera, not the last view's",
          reused and van["zoom"] >= 5 and adopted == fresh, {"fresh": fresh, "vancouver": van, "adopted": adopted, "reused": reused})
    errs = list(page.errors)
    page.context.close()
    return errs


def run(browser, base):
    errors = []
    errors += reuse_is_a_fresh_map(browser, base)
    errors += two_elements_one_parked(browser, base)
    errors += adopted_empty_map_has_fresh_camera(browser, base)
    check("perf-map checks: no script errors", not errors, errors[:3])


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists():
        print("dist/ is not built: npm --prefix ~/data-ui run build")
        return 1
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/lifecycle.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                run(browser, base)
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "perf-map-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} perf-map checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
