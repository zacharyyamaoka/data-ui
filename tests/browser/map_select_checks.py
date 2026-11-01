"""`select:` on every clickable map layer (docs/CONTRACT.md §39, §42), measured in headless Chromium on the built kit.
Written red, before the code.

    ~/psu-atlas/.venv/bin/python tests/browser/map_select_checks.py [OUT_DIR]     # after npm run build

§39 made HTML markers pick and mark; the WebGL layers of §42 went through host.open, so a click picked, but nothing came
back: a region stayed highlighted after it was cleared, a pick from the URL or a table tab marked nothing, and a row inside a
cluster or under a heatmap could not be seen. This file is the ruler for that seam, one fixture per layer
(tests/browser/fixtures/map_select/: invented places, a dashboard panel with `select: name`).

Expected values come from the fixture's JSON and GeoJSON, read here with plain Python; distances are the haversine on
Turf's radius (tests/browser/map_helpers.py's oracle), written out here. Every click is a real mouse click at the feature's
on-screen position (page.mouse, never el.click()). What is measured for each layer:
  - a click picks exactly the rows behind the feature: the dashboard's state and the URL;
  - the feature is marked (MapLibre's feature-state) and no other feature is, and the mark is painted: the pixels around it
    change, and come back byte for byte when the pick is cleared;
  - a ctrl-click adds, a second one takes out, a plain click on the one pick clears;
  - a pick that did not come from a click marks too: the URL on a load, `selected:`, a table tab, a host's el.picked;
  - a cluster never picks: it zooms; a row picked inside a cluster or under a heatmap is marked over it at every zoom;
  - rings have no clickable feature: their legend band picks; a legend entry on a marker map picks; both by keyboard;
  - small multiples and the swipe: the mark is on the map that draws the row;
  - with no `select:`, a click opens the peek and the clicked feature is highlighted, as before;
  - a `time:` bar follows a dashboard that declares `clock:`, and otherwise plays by its own `speed:`.

Serves the repo root on a free 127.0.0.1 port, stops it when done, writes OUT_DIR/map-select-checks.json (default
reports/media/map-select) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "map-select"
OUT.mkdir(parents=True, exist_ok=True)
FIXTURE = "/tests/browser/fixtures/map_select/"
HERE = ROOT / "tests" / "browser" / "fixtures" / "map_select"
WAIT = int(os.environ.get("MAP_SELECT_WAIT_MS", 30000))  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
R_KM = 6371.0088  # Turf's earth radius, as tests/browser/map_helpers.py
SEL = "#dash .dv-view-map"
checks: list[dict] = []

ROWS = json.loads((HERE / "places.json").read_text(encoding="utf-8"))["rows"]
BY = {row["name"]: row for row in ROWS}
SITES = [row for row in ROWS if row["kind"] == "site"]
DEMAND = [row for row in ROWS if row["kind"] == "demand"]
ZONES = {f["properties"]["id"]: f["geometry"]["coordinates"][0] for f in json.loads((HERE / "zones.geojson").read_text(encoding="utf-8"))["features"]}


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run is one failing check in its own words, and the next section still runs."""
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


def km(a, b):
    """Great-circle km between two [lat, lng]."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(h))


def nearest_site(row):
    return min(SITES, key=lambda site: km(row["at"], site["at"]))


def zone_centre(zone):
    ring = ZONES[zone][:-1]
    return [sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)]


def names(rows):
    return sorted(row["name"] for row in rows)


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
SETTLED = """(s) => { const e = document.querySelector(s); const m = e && e.dvMap; return !!m && m.loaded() && !m.isMoving() && m.areTilesLoaded(); }"""
MOUNT = """async ([tag, src, attributes]) => { document.body.innerHTML = ''; const el = document.createElement(tag); el.id = 'dash';
  for (const a of attributes) el.setAttribute(a, ''); el.setAttribute('src', src); document.body.append(el); window.el = el; }"""
SPOT = """([s, lat, lng]) => { const m = document.querySelector(s).dvMap; const c = m.getCanvas().getBoundingClientRect(); const p = m.project([lng, lat]); return [c.x + p.x, c.y + p.y]; }"""
# the panel's selection, whatever its key: each fixture's map is the page's one picking panel
STATE = """() => { const s = Object.values(document.querySelector('#dash').state.select)[0]; return s ? s.values : null; }"""
WAIT_STATE = """(want) => { const s = Object.values(document.querySelector('#dash').state.select)[0]; return JSON.stringify(s ? [...s.values].map(String).sort() : null) === JSON.stringify(want); }"""
# the rows behind every feature of a source that wears the mark, by each feature's own _i, _rows and _site
MARKED = """([s, source]) => { const el = document.querySelector(s), m = el.dvMap, src = m.getSource(source); if (!src) return null;
  const d = src._data, fc = d.geojson || d, rows = el.closest('data-views').model.rows, out = new Set();
  for (const f of fc.features) { if (!(m.getFeatureState({ source, id: f.id }) || {}).sel) continue;
    const p = f.properties; for (const i of [...(p._i != null ? [p._i] : []), ...(p._rows || [])]) out.add(rows[i].name); }
  return [...out].sort(); }"""
WAIT_MARKED = """([s, source, want]) => { const el = document.querySelector(s), m = el.dvMap, src = m.getSource(source); if (!src) return false;
  const d = src._data, fc = d.geojson || d, rows = el.closest('data-views').model.rows, out = new Set();
  for (const f of fc.features) { if (!(m.getFeatureState({ source, id: f.id }) || {}).sel) continue;
    const p = f.properties; for (const i of [...(p._i != null ? [p._i] : []), ...(p._rows || [])]) out.add(rows[i].name); }
  return JSON.stringify([...out].sort()) === JSON.stringify(want); }"""
OVERLAY = """([s, layer]) => { const m = document.querySelector(s).dvMap; if (!m.getLayer(layer)) return null;
  const rows = document.querySelector(s).closest('data-views').model.rows;
  return m.queryRenderedFeatures({ layers: [layer] }).map((f) => { const p = m.project(f.geometry.coordinates); return { name: rows[f.properties._i].name, x: p.x, y: p.y }; }); }"""
SCAN = """([s, layer, name]) => { const el = document.querySelector(s), m = el.dvMap, c = m.getCanvas().getBoundingClientRect(), rows = el.closest('data-views').model.rows;
  const hit = (x, y) => { const f = m.queryRenderedFeatures([x, y], { layers: [layer] })[0]; return f && rows[f.properties._i] && rows[f.properties._i].name === name; };
  for (let y = 12; y < c.height - 12; y += 3) for (let x = 12; x < c.width - 12; x += 3) {
    // WHY every neighbour: a mouse lands on whole pixels, up to a pixel off this one, so the spot must be well inside the line
    if (hit(x, y) && [[-2, 0], [2, 0], [0, -2], [0, 2]].every(([dx, dy]) => hit(x + dx, y + dy))) return [c.x + x, c.y + y]; }
  return null; }"""
# a point on the outline of the polygon behind a row, on screen: an area's mark is its outline, so its pixels are there and not at its centre
EDGE = """([s, source, name]) => { const el = document.querySelector(s), m = el.dvMap, src = m.getSource(source), d = src._data, fc = d.geojson || d, rows = el.closest('data-views').model.rows;
  const f = fc.features.find((x) => (x.properties._rows || []).some((i) => rows[i].name === name)); const c = m.getCanvas().getBoundingClientRect();
  const ring = f.geometry.coordinates[0];
  for (let i = 0; i + 1 < ring.length; i++) for (let t = 0; t < 1; t += 0.05) {
    const q = m.project([ring[i][0] + (ring[i + 1][0] - ring[i][0]) * t, ring[i][1] + (ring[i + 1][1] - ring[i][1]) * t]);
    if (q.x > 24 && q.y > 24 && q.x < c.width - 24 && q.y < c.height - 24) return [c.x + q.x, c.y + q.y]; }
  return null; }"""
CAMERA = """(s) => document.querySelector(s).dvMap.getZoom()"""
NOTHING_OPEN = """() => { const p = document.querySelector('#dash .dv-peek'); return !p || p.hidden; }"""


def settle(page, times=2):
    for _ in range(times):
        page.evaluate(SETTLE)


def until(page, js, arg=None, timeout=WAIT):
    """Wait for a state; False when it never comes (the check that reads it says so in its own words)."""
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def new_page(browser, width=1280, mobile=False):
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on("console", lambda message: page.errors.append(f"console: {message.text}") if message.type == "error" else None)
    return page


def mount(browser, origin, name, tag="data-dashboard", attributes=(), fragment="", sel=SEL, **kw):
    page = new_page(browser, **kw)
    page.goto(origin + FIXTURE + "page.html" + fragment)
    until(page, "() => window.kitReady")
    page.evaluate(MOUNT, [tag, FIXTURE + name + ".base", list(attributes)])
    until(page, f"() => !!document.querySelector('{SEL}[data-zoom]')")
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center', behavior: 'instant' })", SEL)
    until(page, SETTLED, sel)
    settle(page, 3)
    return page


def spot(page, row_or_point, sel=SEL):
    lat, lng = row_or_point["at"] if isinstance(row_or_point, dict) else row_or_point
    return page.evaluate(SPOT, [sel, lat, lng])


def click(page, x, y, keys=()):
    for key in keys:
        page.keyboard.down(key)
    page.mouse.move(x, y)
    page.mouse.click(x, y)
    page.mouse.move(1, 1)
    for key in keys:
        page.keyboard.up(key)


def clip(page, x, y, r=18):
    """The pixels around a point. WHY the viewport only: Chromium's capture beyond it garbles a WebGL canvas."""
    settle(page)
    return page.screenshot(clip={"x": x - r, "y": y - r, "width": 2 * r, "height": 2 * r})


def wait_state(page, values):
    return until(page, WAIT_STATE, sorted(values) if values is not None else None)


def wait_marked(page, source, want, sel=SEL):
    return until(page, WAIT_MARKED, [sel, source, sorted(want)], timeout=8000)


def marked(page, source, sel=SEL):
    return page.evaluate(MARKED, [sel, source])


def cycle(page, label, a, b, want_a, want_b, source="dvl-0", sel_a=SEL, sel_b=SEL, source_b=None, edge=None):
    """The whole round on one layer: a and b are (x, y) on screen, want_a and want_b the rows behind them; `edge` is where the
    mark shows when that is not at `a` (an area's outline)."""
    source_b = source_b or source
    apart = (sel_a, source) != (sel_b, source_b)   # two maps, or two sources: each holds its own mark
    paint = edge or a
    before = clip(page, *paint)
    click(page, *a)
    check(f"{label}: a real click picks exactly the rows behind the feature", wait_state(page, want_a), page.evaluate(STATE))
    check(f"{label}: ... that feature is marked, and no other", wait_marked(page, source, want_a, sel_a), marked(page, source, sel_a))
    check(f"{label}: ... the mark is painted: the pixels at the feature change", clip(page, *paint) != before)
    click(page, *b, keys=["Control"])
    both = [*want_a, *want_b]
    check(f"{label}: a ctrl-click adds, as a marker's does", wait_state(page, both), page.evaluate(STATE))
    check(f"{label}: ... both are marked", wait_marked(page, source_b, want_b if apart else both, sel_b) and wait_marked(page, source, want_a if apart else both, sel_a), [marked(page, source, sel_a), marked(page, source_b, sel_b)])
    click(page, *b, keys=["Control"])
    check(f"{label}: a second ctrl-click takes it out", wait_state(page, want_a) and wait_marked(page, source_b, [] if apart else want_a, sel_b), page.evaluate(STATE))
    click(page, *a)
    check(f"{label}: a plain click on the one pick clears it, in the state and on the map", wait_state(page, None) and wait_marked(page, source, [], sel_a), page.evaluate(STATE))
    check(f"{label}: ... and the pixels come back, byte for byte", clip(page, *paint) == before)
    check(f"{label}: no page error", not page.errors, page.errors[:3])


# ------------------------------------------------------------------------------------------------- one layer at a time
def points(browser, origin):
    page = mount(browser, origin, "points")
    cycle(page, "points", spot(page, BY["Cedar"]), spot(page, BY["Alder"]), ["Cedar"], ["Alder"])
    page.context.close()
    page = mount(browser, origin, "bubbles")
    cycle(page, "proportional points", spot(page, BY["Cedar"]), spot(page, BY["Alder"]), ["Cedar"], ["Alder"])
    page.context.close()


def hexagons(browser, origin):
    page = mount(browser, origin, "hexbin")
    cycle(page, "hexagons", spot(page, BY["Cedar"]), spot(page, BY["Dogwood"]), ["Cedar"], ["Dogwood", "Elm"], edge=page.evaluate(EDGE, [SEL, "dvl-0", "Cedar"]))
    page.context.close()
    page = mount(browser, origin, "columns")
    cycle(page, "raised hexagons", spot(page, BY["Cedar"]), spot(page, BY["Dogwood"]), ["Cedar"], ["Dogwood", "Elm"])
    page.context.close()


def regions(browser, origin):
    page = mount(browser, origin, "regions")
    zone = lambda z: [row["name"] for row in ROWS if row["zone"] == z]
    cycle(page, "regions", spot(page, zone_centre("B")), spot(page, zone_centre("C")), zone("B"), zone("C"), edge=page.evaluate(EDGE, [SEL, "dvl-0", "Cedar"]))
    page.context.close()


def lines(browser, origin):
    page = mount(browser, origin, "flows")
    a, b = page.evaluate(SCAN, [SEL, "dvl-0", "Cedar"]), page.evaluate(SCAN, [SEL, "dvl-0", "Alder"])
    check("flows: the arcs are on screen", bool(a and b), [a, b])
    cycle(page, "flows", a, b, ["Cedar"], ["Alder"])
    page.context.close()
    page = mount(browser, origin, "lines")
    a, b = page.evaluate(SCAN, [SEL, "dvl-0", "Cedar"]), page.evaluate(SCAN, [SEL, "dvl-0", "Alder"])
    check("lines: the routes are on screen", bool(a and b), [a, b])
    cycle(page, "lines", a, b, ["Cedar"], ["Alder"])
    page.context.close()


def distance_layers(browser, origin):
    page = mount(browser, origin, "catchments")
    served = lambda site: [row["name"] for row in DEMAND if nearest_site(row) is site]
    east, south = BY["Site East"], BY["Site South"]
    check("catchments: the fixture's premise: both sites have demand", bool(served(east) and served(south)), [served(east), served(south)])
    cycle(page, "catchments", spot(page, east), spot(page, south), served(east), served(south), edge=page.evaluate(EDGE, [SEL, "dvl-0", served(east)[0]]))
    page.context.close()
    page = mount(browser, origin, "within")
    cycle(page, "within: a demand dot and a site dot", spot(page, BY["Cedar"]), spot(page, BY["Site North"]), ["Cedar"], ["Site North"], source="dvl-0", source_b="dvl-0-s")
    page.context.close()


def callouts(browser, origin):
    page = mount(browser, origin, "labels")
    bubble = lambda name: page.locator(f"{SEL} .dv-map-bubble", has_text=name)
    box = bubble("Cedar").bounding_box()
    click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    check("callouts: a real click picks its row", wait_state(page, ["Cedar"]), page.evaluate(STATE))
    check("callouts: ... it says so: .dv-sel and aria-pressed", until(page, "(s) => { const b = [...document.querySelectorAll(s + ' .dv-map-bubble')].find((e) => e.textContent.includes('Cedar')); return b.getAttribute('aria-pressed') === 'true' && b.classList.contains('dv-sel'); }", SEL, timeout=8000))
    check("callouts: every other callout says false", page.evaluate("(s) => [...document.querySelectorAll(s + ' .dv-map-bubble')].filter((e) => !e.textContent.includes('Cedar')).every((e) => e.getAttribute('aria-pressed') === 'false' && !e.classList.contains('dv-sel'))", SEL))
    box = bubble("Alder").bounding_box()
    click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, keys=["Control"])
    check("callouts: a ctrl-click adds", wait_state(page, ["Cedar", "Alder"]), page.evaluate(STATE))
    bubble("Birch").focus()
    page.keyboard.press("Enter")
    check("callouts: the keyboard reaches them: Enter on one is a plain pick", wait_state(page, ["Birch"]), page.evaluate(STATE))
    check("callouts: no page error", not page.errors, page.errors[:3])
    page.context.close()


def legends(browser, origin):
    page = mount(browser, origin, "rings")
    bands = page.evaluate("(s) => [...document.querySelectorAll(s + ' tr[data-band]')].map((tr) => tr.textContent.trim())", SEL)
    first = names(row for row in DEMAND if km(row["at"], nearest_site(row)["at"]) <= 40)
    check("rings: the fixture's premise: the first band holds rows", bool(first), first)
    row = page.locator(f"{SEL} tr[data-band='0']")
    check("rings: the rings themselves are not clickable: a click at a ring's edge picks nothing", (lambda p: (click(page, *p), settle(page), page.evaluate(STATE))[2])(spot(page, BY["Site North"])) is None, page.evaluate(STATE))
    box = row.bounding_box()
    click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    check("rings: a click on a legend band picks the rows in that band", wait_state(page, first), {"state": page.evaluate(STATE), "bands": bands})
    check("rings: ... the band says so: .dv-sel and aria-pressed", until(page, "(s) => { const r = document.querySelector(s + \" tr[data-band='0']\"); return r.classList.contains('dv-sel') && r.getAttribute('aria-pressed') === 'true'; }", SEL, timeout=8000))
    page.locator(f"{SEL} tr[data-band='0']").focus()
    page.keyboard.press("Enter")
    check("rings: the keyboard reaches a band: Enter on the picked band clears it", wait_state(page, None), page.evaluate(STATE))
    check("rings: no page error", not page.errors, page.errors[:3])
    page.context.close()

    page = mount(browser, origin, "markers")
    entries = page.evaluate("(s) => [...document.querySelectorAll(s + ' .dv-map-panel li')].map((li) => li.textContent.trim())", SEL)
    check("markers: a markerColor property has a legend: one entry per value with its count", sorted(entries) == sorted([f"demand{len(DEMAND)}", f"site{len(SITES)}"]), entries)
    site = page.locator(f"{SEL} .dv-map-panel li", has_text="site")
    box = site.bounding_box()
    click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    check("markers: a legend entry picks its rows", wait_state(page, [row["name"] for row in SITES]), page.evaluate(STATE))
    check("markers: ... their markers are marked", until(page, "([s, n]) => document.querySelectorAll(s + ' .dv-map-marker.dv-sel').length === n", [SEL, len(SITES)], timeout=8000))
    check("markers: ... the entry says so", page.evaluate("(s) => { const li = [...document.querySelectorAll(s + ' .dv-map-panel li')].find((e) => e.textContent.includes('site')); return li.getAttribute('aria-pressed') === 'true' && li.classList.contains('dv-sel'); }", SEL))
    page.locator(f"{SEL} .dv-map-panel li", has_text="site").focus()
    page.keyboard.press("Enter")
    check("markers: Enter on the picked entry clears it", wait_state(page, None), page.evaluate(STATE))
    check("markers: no page error", not page.errors, page.errors[:3])
    page.context.close()


def dense(browser, origin):
    """What a density layer hides: a row in a cluster, a row under the heat."""
    elm = BY["Elm"]
    page = mount(browser, origin, "clusters")
    zoom = page.evaluate(CAMERA, SEL)
    counted = page.evaluate("(s) => { const m = document.querySelector(s).dvMap; return m.queryRenderedFeatures({ layers: ['dvl-0-c'] }).map((f) => f.properties.point_count); }", SEL)
    check("clusters: the fixture's premise: Dogwood and Elm draw as one cluster of 2", counted == [2], counted)
    click(page, *spot(page, elm))
    check("clusters: a click on a cluster zooms in", until(page, "([s, z]) => document.querySelector(s).dvMap.getZoom() > z + 0.5", [SEL, zoom], timeout=8000), page.evaluate(CAMERA, SEL))
    until(page, SETTLED, SEL)
    settle(page, 2)
    check("clusters: ... and picks nothing", page.evaluate(STATE) is None, page.evaluate(STATE))
    click(page, *spot(page, elm))
    check("clusters: the zoomed-in point picks its row", wait_state(page, ["Elm"]), page.evaluate(STATE))
    check("clusters: ... and is marked", until(page, "([s]) => { const m = document.querySelector(s).dvMap; return m.getLayer('dvl-0-m') && m.queryRenderedFeatures({ layers: ['dvl-0-m'] }).length === 1; }", [SEL], timeout=8000))
    check("clusters: no page error", not page.errors, page.errors[:3])
    page.context.close()

    page = mount(browser, origin, "clusters", fragment="#s.map=name:Elm")
    drawn = page.evaluate(OVERLAY, [SEL, "dvl-0-m"]) or []
    still = page.evaluate("(s) => { const m = document.querySelector(s).dvMap; return m.queryRenderedFeatures({ layers: ['dvl-0-c'] }).length; }", SEL)
    x, y = spot(page, elm)
    box = page.evaluate("(s) => { const c = document.querySelector(s).dvMap.getCanvas().getBoundingClientRect(); return [c.x, c.y]; }", SEL)
    check("clusters: a row picked from the URL, inside a cluster: its ring stands at the row's own point, over the cluster",
          [row["name"] for row in drawn] == ["Elm"] and still == 1 and math.hypot(drawn[0]["x"] + box[0] - x, drawn[0]["y"] + box[1] - y) < 2, drawn)
    page.context.close()

    page = mount(browser, origin, "heatmap", fragment="#s.map=name:Cedar")
    zoom = page.evaluate(CAMERA, SEL)
    check("heatmap: the fixture's premise: singles are not drawn at this zoom", zoom < 11 and page.evaluate("(s) => document.querySelector(s).dvMap.queryRenderedFeatures({ layers: ['dvl-0-p'] }).length", SEL) == 0, zoom)
    drawn = page.evaluate(OVERLAY, [SEL, "dvl-0-m"]) or []
    check("heatmap: a row picked from the URL is marked under the heat, at a zoom that draws no single row", [row["name"] for row in drawn] == ["Cedar"], drawn)
    page.context.close()

    page = mount(browser, origin, "heatmap")
    page.evaluate("([s, lat, lng]) => document.querySelector(s).dvMap.jumpTo({ center: [lng, lat], zoom: 12 })", [SEL, *BY["Cedar"]["at"]])
    until(page, SETTLED, SEL)
    settle(page, 2)
    before = clip(page, *spot(page, BY["Cedar"]))
    click(page, *spot(page, BY["Cedar"]))
    check("heatmap: a single row past pointsFrom picks", wait_state(page, ["Cedar"]), page.evaluate(STATE))
    check("heatmap: ... and its mark is painted", clip(page, *spot(page, BY["Cedar"])) != before)
    click(page, *spot(page, BY["Cedar"]))
    check("heatmap: a second click clears it, pixel for pixel", wait_state(page, None) and clip(page, *spot(page, BY["Cedar"])) == before, page.evaluate(STATE))
    check("heatmap: no page error", not page.errors, page.errors[:3])
    page.context.close()


def panels(browser, origin):
    """Maps that are more than one map: the mark is where the row is drawn."""
    page = mount(browser, origin, "multiples", sel="#dash .dv-map-cell:nth-of-type(3)")
    b, a = "#dash .dv-map-cell:nth-of-type(2)", "#dash .dv-map-cell:nth-of-type(1)"
    for sel in (a, b):
        until(page, SETTLED, sel)
    settle(page, 3)
    cycle(page, "small multiples", spot(page, BY["Cedar"], b), spot(page, BY["Alder"], a), ["Cedar"], ["Alder"], sel_a=b, sel_b=a)
    page.context.close()

    right = "#dash .dv-map-after"
    page = mount(browser, origin, "swipe", sel=right)
    until(page, SETTLED, right)
    settle(page, 4)
    # Elm, drawn over Dogwood 1.4 km away: the top feature under the pointer is the one that answers
    cycle(page, "swipe", spot(page, BY["Elm"], right), spot(page, BY["Site North"]), ["Elm"], ["Site North"], sel_a=right, sel_b=SEL)
    x, y = spot(page, BY["Elm"], right)
    x, y = x - 40, y - 200
    start = page.evaluate("(s) => document.querySelector(s).dvMap.getCenter().lng", right)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 80, y + 30, steps=8)
    page.mouse.up()
    page.mouse.move(1, 1)
    # both, and stopped: the two cameras are read one after the other, and a read during the pan's inertia sees two frames
    until(page, "(both) => both.every((s) => !document.querySelector(s).dvMap.isMoving())", [right, SEL])
    settle(page, 3)
    now = page.evaluate("(s) => document.querySelector(s).dvMap.getCenter().lng", right)
    left = page.evaluate("(s) => document.querySelector(s).dvMap.getCenter().lng", SEL)
    check("swipe: a real drag right of the divider pans the right map, and the left one with it", abs(now - start) > 0.01 and abs(now - left) < 1e-6, [start, now, left])
    page.context.close()


def elsewhere(browser, origin):
    """A pick that no click on this map made: the marks still arrive."""
    page = mount(browser, origin, "regions", fragment="#s.map=name:Cedar")
    check("the URL: a load naming a row marks its region", wait_marked(page, "dvl-0", ["Cedar"]), marked(page, "dvl-0"))
    page.context.close()

    page = mount(browser, origin, "tabs")
    first = ROWS[0]
    zone = [row["name"] for row in ROWS if row["zone"] == first["zone"]]
    check("selected: first: its row is marked on the points, and its region (a region is marked when any row behind it is)",
          wait_marked(page, "dvl-1", [first["name"]]) and wait_marked(page, "dvl-0", zone), [marked(page, "dvl-1"), marked(page, "dvl-0")])
    page.locator("#dash [role=tab]", has_text="Table").click()
    until(page, "() => !!document.querySelector('#dash tbody tr[data-i]')")
    settle(page, 2)
    page.locator("#dash tbody tr", has_text="Cedar").locator("td").first.click()
    page.mouse.move(1, 1)
    check("a pick in the table tab", wait_state(page, ["Cedar"]), page.evaluate(STATE))
    page.locator("#dash [role=tab]", has_text="Map").click()
    until(page, f"() => !!document.querySelector('{SEL}[data-zoom]')")
    until(page, SETTLED, SEL)
    settle(page, 3)
    check("table → map: the row picked in the table is marked on the map", wait_marked(page, "dvl-1", ["Cedar"]), marked(page, "dvl-1"))
    check("table → map: ... and no other", page.evaluate(MARKED, [SEL, "dvl-1"]) == ["Cedar"], marked(page, "dvl-1"))
    check("tabs: no page error", not page.errors, page.errors[:3])
    page.context.close()

    page = mount(browser, origin, "plain", tag="data-views", attributes=["no-url"])
    page.evaluate("() => { window.el.picked = ['cedar']; }")
    check("a host's el.picked marks every layer that draws the row", wait_marked(page, "dvl-1", ["Cedar"]) and wait_marked(page, "dvl-0", ["Cedar"]), [marked(page, "dvl-1"), marked(page, "dvl-0")])
    page.evaluate("() => { window.el.filters = 'kind != \"nothing\"'; }")
    until(page, SETTLED, SEL)
    settle(page, 4)
    check("a redraw keeps the marks (input.selected)", wait_marked(page, "dvl-1", ["Cedar"]) and wait_marked(page, "dvl-0", ["Cedar"]), [marked(page, "dvl-1"), marked(page, "dvl-0")])
    page.evaluate("() => { window.el.picked = []; }")
    check("el.picked = [] clears them", wait_marked(page, "dvl-1", []) and wait_marked(page, "dvl-0", []), [marked(page, "dvl-1"), marked(page, "dvl-0")])
    check("host marks: no page error", not page.errors, page.errors[:3])
    page.context.close()


def phone(browser, origin):
    page = mount(browser, origin, "regions", width=390, mobile=True)
    x, y = spot(page, zone_centre("B"))
    page.touchscreen.tap(x, y)
    check("390 px: a real tap on a region picks it, and it is marked", wait_state(page, [row["name"] for row in ROWS if row["zone"] == "B"]) and wait_marked(page, "dvl-0", [row["name"] for row in ROWS if row["zone"] == "B"]), page.evaluate(STATE))
    check("390 px: no sideways scroll", page.evaluate("() => document.scrollingElement.scrollWidth") <= 390, page.evaluate("() => document.scrollingElement.scrollWidth"))
    check("390 px: no page error", not page.errors, page.errors[:3])
    page.context.close()


def no_select(browser, origin):
    page = mount(browser, origin, "no-select")
    click(page, *spot(page, zone_centre("B")))
    peeked = until(page, "() => { const p = document.querySelector('#dash .dd-drill .dv-peek'); return !!p && !p.hidden; }", timeout=8000)
    check("no select: a region click opens the peek, as before", peeked and "Cedar" in page.locator("#dash .dd-drill .dv-peek").inner_text(), peeked)
    check("no select: ... selects nothing", page.evaluate("() => JSON.stringify(document.querySelector('#dash').state.select)") == "{}")
    check("no select: ... and highlights what was clicked, as before", wait_marked(page, "dvl-0", ["Cedar"]), marked(page, "dvl-0"))
    page.keyboard.press("Escape")
    until(page, "() => { const p = document.querySelector('#dash .dd-drill .dv-peek'); return !p || p.hidden; }", timeout=8000)
    click(page, *spot(page, zone_centre("C")))
    want = [row["name"] for row in ROWS if row["zone"] == "C"]
    check("no select: the next click moves the highlight", wait_marked(page, "dvl-0", want), marked(page, "dvl-0"))
    check("no select: no page error", not page.errors, page.errors[:3])
    page.context.close()


def clocks(browser, origin):
    stops = json.loads((HERE / "stops.json").read_text(encoding="utf-8"))["rows"]
    page = mount(browser, origin, "clock")
    until(page, f"() => !!document.querySelector('{SEL} .dv-map-time')")
    settle(page, 2)
    t0 = page.evaluate("(s) => Number(document.querySelector(s + ' .dv-map-time input').min)", SEL)
    page.evaluate("() => document.querySelector('#dash').clock.seek(7200)")
    check("clock: a dashboard's clock moves the map's bar", until(page, "([s, want]) => Number(document.querySelector(s + ' .dv-map-time input').value) === want", [SEL, t0 + 7200 * 1000], timeout=8000),
          page.evaluate("(s) => document.querySelector(s + ' .dv-map-time input').value", SEL))
    check("clock: ... and the map shows the rows up to that time", page.get_attribute(f"{SEL} .dv-map-time", "data-shown") == "3", page.get_attribute(f"{SEL} .dv-map-time", "data-shown"))
    page.evaluate("([s, t]) => { const r = document.querySelector(s + ' .dv-map-time input'); r.value = String(t); r.dispatchEvent(new Event('input')); }", [SEL, t0 + 3600 * 1000])
    check("clock: scrubbing the bar seeks the clock", until(page, "() => document.querySelector('#dash').clock.t === 3600", timeout=8000), page.evaluate("() => document.querySelector('#dash').clock.t"))
    page.evaluate("(s) => document.querySelector(s + ' .dv-map-play').click()", SEL)
    check("clock: the play button plays the clock, and says Pause", until(page, "(s) => document.querySelector('#dash').clock.playing && document.querySelector(s + ' .dv-map-play').getAttribute('aria-label') === 'Pause'", SEL, timeout=8000))
    page.evaluate("(s) => document.querySelector(s + ' .dv-map-play').click()", SEL)
    check("clock: ... and pauses it, and says Play", until(page, "(s) => !document.querySelector('#dash').clock.playing && document.querySelector(s + ' .dv-map-play').getAttribute('aria-label') === 'Play'", SEL, timeout=8000))
    page.evaluate("() => { document.querySelector('#dash .dd-panel data-views').filters = 'name == \"nobody\"'; }")
    check("clock: a filter that leaves no time takes the bar away", until(page, f"() => !document.querySelector('{SEL} .dv-map-time')", timeout=8000))
    page.evaluate("() => document.querySelector('#dash').clock.seek(1800)")
    settle(page, 2)
    check("clock: no page error, and the next tick writes to no bar", not page.errors, page.errors[:3])
    page.context.close()

    page = mount(browser, origin, "noclock")
    until(page, f"() => !!document.querySelector('{SEL} .dv-map-time')")
    settle(page, 2)
    low = page.evaluate("(s) => Number(document.querySelector(s + ' .dv-map-time input').min)", SEL)
    span = page.evaluate("(s) => Number(document.querySelector(s + ' .dv-map-time input').max)", SEL) - low
    page.evaluate("(s) => { const r = document.querySelector(s + ' .dv-map-time input'); r.value = r.min; r.dispatchEvent(new Event('input')); }", SEL)
    page.evaluate("(s) => document.querySelector(s + ' .dv-map-play').click()", SEL)
    check("no clock: declared: the bar plays by its own speed: the whole span in about 12 s, not one second a second",
          until(page, "([s, want]) => Number(document.querySelector(s + ' .dv-map-time input').value) > want", [SEL, low + span / 4], timeout=20000), span)
    check("no clock: no page error", not page.errors, page.errors[:3])
    page.context.close()
    check("stops: the fixture's premise: an hour between stops", len(stops) == 6)


def main():
    server, origin = serve(ROOT, FIXTURE + "page.html")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, section in (("points", points), ("hexagons", hexagons), ("regions", regions), ("lines", lines), ("distance layers", distance_layers), ("callouts", callouts),
                                  ("legends", legends), ("density layers", dense), ("several maps", panels), ("picks from elsewhere", elsewhere), ("a phone", phone),
                                  ("no select", no_select), ("clocks", clocks)):
                with guard(name):
                    section(browser, origin)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "map-select-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    passed = sum(1 for item in checks if item["ok"])
    print(f"{passed}/{len(checks)} map select checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
