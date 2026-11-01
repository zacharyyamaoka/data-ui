"""The credit on the map itself (docs/MAP-DATA.md): OpenStreetMap must be credited on any map that draws its data, whether as
tiles or as rows, and the credit must stay. Measured in headless Chromium on the built site.

    ~/psu-atlas/.venv/bin/python tests/browser/map_credit_checks.py [OUT_DIR]     # after npm run build

The expected list is written out here by hand from the sources each case names, never read from the page: twelve cases draw
OSM data. For each, at 1280 and 390 px, light and dark:
  - the credit is on screen, inside the map, and it is what the browser hits at its own centre (nothing lies over it);
  - it says OpenStreetMap and links to its copyright page;
  - it reads at 4.5:1 or better against the kit's surface;
  - it stays: a real drag on the map leaves it open. WHY measured: MapLibre's compact control folds at the first drag.
The other eight must not claim it. A small multiple and a swipe side, whose first map is hidden or clipped, carry the credit of
the rows they draw.

Serves dist/site on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/map-credit-checks.json (default
reports/media/map-credit) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "map-credit"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
WAIT = int(os.environ.get("MAP_CREDIT_WAIT_MS", 30000))
FIXTURE = "/tests/browser/fixtures/map_select/"
checks: list[dict] = []

# OSM data on the map: tiles from metro-vancouver.pmtiles, rows from food.json, recycling.json, sites.json, day.json, flows.json, facts.json
OSM = ["map-3d-columns", "map-annotations", "map-catchments", "map-collection-routes", "map-draw-select", "map-food-heatmap", "map-food-hexbin", "map-playback",
       "map-recycling-clusters", "map-service-rings", "map-waste-flows", "map-within-distance"]
NOT_OSM = ["map-bc-disposal", "map-bivariate", "map-bubbles", "map-dashboard", "map-region-filter", "map-small-multiples", "map-sorting-line", "map-swipe"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:300]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    try:
        yield
    except Exception as error:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(error).__name__}: {str(error)[:300]}")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def serve(directory, path):
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origin = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(origin + path, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return server, origin


CREDIT = """() => { const out = [];
  for (const c of document.querySelectorAll('#example .maplibregl-ctrl-attrib')) { const map = c.closest('.maplibregl-map');
    const inner = c.querySelector('.maplibregl-ctrl-attrib-inner'), r = inner.getBoundingClientRect(), m = map.getBoundingClientRect();
    // WHY a grid, not the centre: a time bar over the credit's top line left its centre clear
    const spots = []; for (const fx of [0.02, 0.25, 0.5, 0.75, 0.98]) for (const fy of [0.1, 0.5, 0.9]) spots.push([r.x + r.width * fx, r.y + r.height * fy]);
    const hit = r.width && r.height && spots.every(([x, y]) => { const e = document.elementFromPoint(x, y); return !!e && !!e.closest('.maplibregl-ctrl-attrib'); });
    const scale = map.querySelector('.maplibregl-ctrl-scale'), b = scale && scale.getBoundingClientRect();
    const s = getComputedStyle(inner);
    out.push({ text: inner.textContent.trim(), links: [...inner.querySelectorAll('a')].map((a) => a.href), open: c.hasAttribute('open'), compact: c.classList.contains('maplibregl-compact'),
      rect: [r.x, r.y, r.right, r.bottom], map: [m.x, m.y, m.right, m.bottom], hit: !!hit, clear: !b || b.right <= r.x || b.left >= r.right || b.bottom <= r.y || b.top >= r.bottom, visible: s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0,
      colour: s.color }); }
  return out; }"""
SETTLED = """() => { const e = document.querySelector('#example .dv-view-map'); const m = e && e.dvMap; return !!m && m.loaded() && !m.isMoving(); }"""
RGB = """(css) => { const c = document.createElement('canvas').getContext('2d'); c.fillStyle = '#000'; c.fillStyle = css; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data].slice(0, 3); }"""
SURFACE = """() => document.querySelector('#example').tokens().bg"""


def luminance(rgb):
    channels = [c / 255 for c in rgb]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one, two):
    a, b = sorted((luminance(one), luminance(two)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def until(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def open_case(browser, site, case, width, dark):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, color_scheme="dark" if dark else "light", device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.goto(f"{site}/gallery/{case}/index.html")
    until(page, "() => !!document.querySelector('#example .dv-view-map[data-zoom]')")
    page.evaluate("() => document.querySelector('#example .dv-view-map').scrollIntoView({ block: 'center', behavior: 'instant' })")
    until(page, SETTLED)
    until(page, "() => { const c = document.querySelector('#example .maplibregl-ctrl-attrib-inner'); return !!c && c.textContent.trim().length > 0; }", timeout=10000)
    page.wait_for_timeout(200)
    return page


def credited(entry):
    return "OpenStreetMap" in entry["text"] and any(link.startswith("https://www.openstreetmap.org/copyright") for link in entry["links"])


def osm_case(browser, site, case, width, dark):
    tag = f"{case}, {'dark' if dark else 'light'}, {width} px"
    page = open_case(browser, site, case, width, dark)
    entries = page.evaluate(CREDIT)
    shown = [entry for entry in entries if credited(entry)]
    check(f"{tag}: the map credits OpenStreetMap, with a link to its copyright page", bool(shown), [entry["text"] for entry in entries])
    if shown:
        entry = shown[0]
        x0, y0, x1, y1 = entry["rect"]
        mx0, my0, mx1, my1 = entry["map"]
        check(f"{tag}: the credit stands inside the map, open, not folded", entry["open"] and not entry["compact"] and entry["visible"] and x0 >= mx0 - 1 and y0 >= my0 - 1 and x1 <= mx1 + 1 and y1 <= my1 + 1, entry)
        check(f"{tag}: nothing lies over it: the browser hits the credit all across its box", entry["hit"], entry["rect"])
        check(f"{tag}: the scale bar stands clear of it", entry["clear"], entry["rect"])
        surface = page.evaluate(RGB, page.evaluate(SURFACE))
        text = page.evaluate(RGB, entry["colour"])
        check(f"{tag}: it reads at 4.5:1 or better on the kit's surface", contrast(text, surface) >= 4.5, round(contrast(text, surface), 2))
    box = page.locator("#example .dv-view-map canvas.maplibregl-canvas").first.bounding_box()
    x, y = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.35
    if width > 500:
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x - 60, y + 24, steps=6)
        page.mouse.up()
        page.mouse.move(1, 1)
    else:
        # the control folds on MapLibre's `drag` event, which a touch fires too; a page script stands in for a finger
        page.evaluate("() => document.querySelector('#example .dv-view-map').dvMap.fire('drag')")
    page.wait_for_timeout(250)
    after = [entry for entry in page.evaluate(CREDIT) if credited(entry)]
    check(f"{tag}: it stays after the map is dragged", bool(after) and after[0]["open"] and after[0]["visible"] and not after[0]["compact"], after[:1])
    check(f"{tag}: no page error", not page.errors, page.errors[:3])
    page.context.close()


def other_case(browser, site, case):
    page = open_case(browser, site, case, 1280, False)
    text = " ".join(entry["text"] for entry in page.evaluate(CREDIT))
    check(f"{case}: draws no OSM data and does not claim to", "OpenStreetMap" not in text, text)
    page.context.close()


SPLIT = """(sel) => [...document.querySelectorAll(sel)].map((m) => { const c = m.querySelector('.maplibregl-ctrl-attrib-inner'); return c ? c.textContent : null; })"""


def several_maps(browser, origin):
    """A credit on the data reaches a map that is not the view's first: the fixture's places, with a credit added in the page."""
    for name, sel in (("multiples", "#dash .dv-map-cell"), ("swipe", "#dash .dv-map-after")):
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        page = context.new_page()

        def credit(route):
            doc = json.loads(pathlib.Path(ROOT / FIXTURE.strip("/") / "places.json").read_text(encoding="utf-8"))
            doc["attribution"] = {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(doc))

        page.route("**/places.json", credit)
        page.goto(origin + FIXTURE + "page.html")
        until(page, "() => window.kitReady")
        page.evaluate("""async (src) => { document.body.innerHTML = ''; const el = document.createElement('data-dashboard'); el.id = 'dash'; el.setAttribute('src', src); document.body.append(el); }""", FIXTURE + name + ".base")
        until(page, f"(s) => !!document.querySelector(s + ' .maplibregl-ctrl-attrib-inner') && document.querySelector(s + ' .maplibregl-ctrl-attrib-inner').textContent.includes('OpenStreetMap')", sel, timeout=15000)
        texts = page.evaluate(SPLIT, sel)
        check(f"{name}: every map beyond the first carries the data's credit", bool(texts) and all(text and "OpenStreetMap" in text for text in texts), texts)
        context.close()


def main():
    server, site = serve(SITE, "/index.html")
    repo, origin = serve(ROOT, FIXTURE + "page.html")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for case in OSM:
                for width, dark in ((1280, False), (390, True)):
                    with guard(f"{case} at {width} px"):
                        osm_case(browser, site, case, width, dark)
            for width, dark in ((1280, True), (390, False)):
                # the two tightest maps again, in the other theme: a time bar and a draw bar stand near the credit
                for case in ("map-playback", "map-draw-select"):
                    with guard(f"{case} at {width} px"):
                        osm_case(browser, site, case, width, dark)
            for case in NOT_OSM:
                with guard(case):
                    other_case(browser, site, case)
            with guard("several maps"):
                several_maps(browser, origin)
            browser.close()
    finally:
        for process in (server, repo):
            process.terminate()
            process.wait(timeout=10)
    (OUT / "map-credit-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    passed = sum(1 for item in checks if item["ok"])
    print(f"{passed}/{len(checks)} map credit checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
