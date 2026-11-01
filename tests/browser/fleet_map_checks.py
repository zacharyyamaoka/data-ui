"""The fleet map (docs/CONTRACT.md §39): a map view that picks, measured in headless Chromium on the built kit and site.
Written red, before the code; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/fleet_map_checks.py [OUT_DIR]     # after npm run build

The case is gallery/examples/robotics-fleet: one panel with Map, Table and Cards tabs over deployments.json, then the
picked robot's runs, its playback and two plots. Every expected value comes from the case's own files, read here with
Python (the oracle is the file, never the page): which row stands at which point, a robot's runs newest first, a run's
t span and its plotted points. Where a marker stands on screen is checked against Web Mercator worked out here, not
against MapLibre.

What is measured, with a real mouse, keyboard or touch at each thing's on-screen position (page.mouse, never el.click()):
  - a marker click picks its row: the state, the URL, the panel's label; the runs panel equals that deployment's rows,
    newest first; its newest run is picked with it (a second robot must not leave the first robot's run selected) and
    exactly runs/<run>.json is fetched; the clock spans that file's t and the plot draws that file's points;
  - a picked marker is marked (.dv-sel, aria-pressed), wherever the pick came from: the marker, the table tab, the cards
    tab, the URL, `selected:`, Back and Forward, and after a tab switch;
  - a ctrl / cmd-click adds and takes out, as the table's does;
  - a counted marker holding several values of `select:` asks which: a chooser lists the rows at that point and picks
    nothing until the reader names one; a plain click picks that row and closes it, a ctrl-click adds and keeps it open;
    Escape and a click on the map close it; rows sharing one value need no question;
  - the keyboard reaches all of it: Tab to a marker, Enter or Space, the chooser's arrows;
  - a pick survives every tab switch, a reload and Back / Forward, and each pick is one history entry;
  - light and dark at 1280 and 390 px: no sideways scroll, the mark and the chooser legible, the chooser on screen;
  - a map with no `select:` behaves as it always did: the peek opens, a counted marker lists its rows there, and a marker
    carries no new attribute;
  - `<data-views>.picked`, the host's marks: they reach selected(set) and input.selected, and touch nothing else (no
    selection, no bulk bar, no event).

Serves dist/site and the repo root on free 127.0.0.1 ports, stops both when done, writes OUT_DIR/fleet-map-checks.json
(default reports/media/fleet-map) and exits 1 if any check fails.
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
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "fleet-map"
OUT.mkdir(parents=True, exist_ok=True)
SITE = ROOT / "dist" / "site"
CASE = "robotics-fleet"
HERE = ROOT / "gallery" / "examples" / CASE
FIXTURE = "/tests/browser/fixtures/fleet_map/"
WAIT = int(os.environ.get("FLEET_MAP_WAIT_MS", 45000))  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
D = "#example"
checks: list[dict] = []


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


# ------------------------------------------------------------------------------------------------- the case's files
def file_rows(path):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return doc["rows"] if isinstance(doc, dict) else doc


FLEET = file_rows(HERE / "deployments.json")
RUNS = file_rows(HERE / "runs.json")
STATUS_SLOTS = json.loads((HERE / "deployments.json").read_text(encoding="utf-8"))["properties"]["status"]["colors"]


def runs_of(*deployments):
    """The runs of these deployments, newest first, as the runs table sorts them."""
    return [r["run"] for r in sorted((r for r in RUNS if r["deployment"] in deployments), key=lambda r: r["started"], reverse=True)]


def points():
    """The rows at each point, in file order: what a map draws as one marker (four decimals, as toPoints keys them)."""
    out = {}
    for row in FLEET:
        lat, lng = row["coordinates"]
        out.setdefault((f"{lat:.4f}", f"{lng:.4f}"), []).append(row)
    return list(out.values())


def title_of(rows_here):
    """A marker's title: the row's name, or the first row's name and the count."""
    return rows_here[0]["name"] if len(rows_here) == 1 else f"{rows_here[0]['name']} · {len(rows_here)} rows"


SINGLES = [rows_here[0] for rows_here in points() if len(rows_here) == 1]
RACK = next(row for row in FLEET if row["basis"] == "real")
ROBOT_A, ROBOT_B = [row for row in SINGLES if row is not RACK][:2]
COUNTED = [rows_here for rows_here in points() if len(rows_here) > 1]
COUNTED_ROWS = COUNTED[0]
LAST_COUNTED = COUNTED[-1]


def run_file(run):
    return HERE / "runs" / f"{run}.json"


def span(run):
    times = [r["t"] for r in file_rows(run_file(run))]
    return [min(times), max(times)]


def series_points(run, column):
    """{situation: [(t, value)…]} of a run's file, sorted by t, the nulls left out (a timeseries draws a gap there)."""
    out = {}
    for row in file_rows(run_file(run)):
        value = row.get(column)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.setdefault(row["situation"], []).append((row["t"], value))
    for series in out.values():
        series.sort()
    return out


def enc(value):
    """One URL path segment, as encodeURIComponent writes it (the template fills `{run}` so)."""
    return urllib.parse.quote(str(value), safe="-_.!~*'()")


def mercator(lat, lng):
    """Web Mercator on the unit square, worked out here: x east, y south."""
    return (lng + 180) / 360, (1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 60))))"
READY = """([root, keys]) => { const d = document.querySelector(root); if (!d || !d.dash) return false;
  if (keys.some((k) => !d.querySelector(`.dd-panel[data-panel='${k}']`))) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; return !!els.length && els.every((e) => e.dataset.view); }"""
MARKERS = """(root) => [...document.querySelectorAll(`${root} .dv-map-marker`)].map((m) => { const r = m.getBoundingClientRect();
  return { title: m.title, x: r.left + r.width / 2, y: r.top + r.height / 2, pin: m.style.getPropertyValue('--dv-pin').trim(), pressed: m.getAttribute('aria-pressed'),
    marked: m.classList.contains('dv-sel'), attributes: m.getAttributeNames().filter((a) => a.startsWith('aria-')).sort() }; })"""
MARKED = """(root) => [...document.querySelectorAll(`${root} .dv-map-marker.dv-sel`)].map((m) => m.title).sort()"""
WAIT_MARKED = """([root, want]) => JSON.stringify([...document.querySelectorAll(`${root} .dv-map-marker.dv-sel`)].map((m) => m.title).sort()) === JSON.stringify(want)"""
PRESSED = """(root) => [...document.querySelectorAll(`${root} .dv-map-marker[aria-pressed="true"]`)].map((m) => m.title).sort()"""
STANDS = """(title) => { const m = [...document.querySelectorAll('.dv-map-marker')].find((e) => e.title === title); if (!m) return null;
  (m.closest('.dd-panel') || m.closest('data-views')).scrollIntoView({ block: 'center' }); return true; }"""
HIT = """([x, y]) => { const e = document.elementFromPoint(x, y); const m = e && e.closest('.dv-map-marker'); return m ? m.title : null; }"""
CHOOSER = """(root) => { const c = document.querySelector(`${root} .dv-map-choose`); if (!c) return null; const r = c.getBoundingClientRect();
  return { role: c.getAttribute('role'), label: c.getAttribute('aria-label'), left: r.left, right: r.right, top: r.top, bottom: r.bottom,
    rows: [...c.querySelectorAll('.dv-map-choose-row')].map((b) => ({ id: b.dataset.id, text: b.textContent.trim(), pressed: b.getAttribute('aria-pressed') })) }; }"""
WAIT_CHOOSER = """(root) => !!document.querySelector(`${root} .dv-map-choose`)"""
NO_CHOOSER = """() => !document.querySelector('.dv-map-choose')"""
FOCUS = """() => { const a = document.activeElement; if (!a) return {}; return { marker: a.classList.contains('dv-map-marker') ? a.title : null, row: a.classList.contains('dv-map-choose-row') ? a.dataset.id : null }; }"""
STATE = """([root, key]) => { const s = document.querySelector(root).state.select[key]; return s ? s.values : null; }"""
WAIT_STATE = """([root, key, want]) => { const s = document.querySelector(root).state.select[key]; return JSON.stringify(s ? [...s.values].map(String).sort() : null) === JSON.stringify(want); }"""
DRAWN = """([root, key, column]) => { const el = document.querySelector(`${root} .dd-panel[data-panel='${key}'] data-views`); const m = el && el.model;
  return m ? m.rows.map((r) => (r[column] && typeof r[column] === 'object' && !Array.isArray(r[column]) ? r[column].value : r[column])) : null; }"""
WAIT_DRAWN = """([root, key, column, want]) => { const el = document.querySelector(`${root} .dd-panel[data-panel='${key}'] data-views`); const m = el && el.model;
  return !!m && JSON.stringify(m.rows.map((r) => r[column])) === JSON.stringify(want); }"""
LABEL = """([root, key]) => { const s = document.querySelector(`${root} .dd-panel[data-panel='${key}'] .dd-sel`); return s ? s.textContent : null; }"""
SPAN = """(root) => { const c = document.querySelector(root).clock; return [c.start, c.end]; }"""
WAIT_SPAN = """([root, want]) => { const c = document.querySelector(root).clock; return JSON.stringify([c.start, c.end]) === JSON.stringify(want); }"""
WAITING = """(root) => [...document.querySelectorAll(`${root} .dd-panel[data-wait]`)].map((s) => s.dataset.panel + ':' + s.dataset.wait)"""
POINTS = """([root, key]) => { const p = document.querySelector(`${root} .dd-panel[data-panel='${key}']`); const plot = p && p.querySelector('.dv-timeseries-plot'); const v = plot && plot.parentElement.vegaView;
  if (!v) return null; const out = {}; for (const d of v.data('series')) (out[d.series] = out[d.series] || []).push([d.x, d.value]); return out; }"""
ACTIVE_TAB = """([root, key]) => { const t = document.querySelector(`${root} .dd-panel[data-panel='${key}'] [role=tab][aria-selected=true]`); return t ? t.textContent.trim() : null; }"""
TABS = """([root, key]) => [...document.querySelectorAll(`${root} .dd-panel[data-panel='${key}'] [role=tab]`)].map((t) => t.textContent.trim())"""
WAIT_VIEW = """([root, key, name]) => { const el = document.querySelector(`${root} .dd-panel[data-panel='${key}'] data-views`); return !!el && !!el.view && el.view.name === name && el.dataset.view === el.view.type; }"""
TABLE_MARKS = """([root, key, column]) => { const el = document.querySelector(`${root} .dd-panel[data-panel='${key}'] data-views`);
  return [...el.querySelectorAll('tbody tr[data-i]')].map((tr) => [el.model.rows[Number(tr.dataset.i)][column], getComputedStyle(tr.querySelector('td')).backgroundColor]); }"""
CARDS = """([root, key]) => [...document.querySelectorAll(`${root} .dd-panel[data-panel='${key}'] .dv-cards-card[data-id]`)].map((c) => { const s = getComputedStyle(c);
  return { id: c.dataset.id, marked: c.classList.contains('dv-sel'), border: s.borderTopColor, fill: s.backgroundColor }; })"""
# any CSS colour as [r, g, b], through a canvas, so oklch(), lab() and color-mix() results compare as what is painted
RGB = """(css) => { const c = document.createElement('canvas').getContext('2d'); c.fillStyle = '#000'; c.fillStyle = css; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data].slice(0, 3); }"""
SIDEWAYS = "() => document.scrollingElement.scrollWidth"


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


def new_page(browser, *, width=1280, dark=False):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors, page.requests = [], []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on("console", lambda message: page.errors.append(f"console: {message.text}") if message.type == "error" else None)
    page.on("request", lambda request: page.requests.append(request.url))
    return page


def open_case(browser, site, *, width=1280, dark=False, fragment=""):
    page = new_page(browser, width=width, dark=dark)
    page.goto(f"{site}/gallery/{CASE}/index.html{fragment}")
    ready = until(page, READY, [D, ["deployments", "runs", "playback"]])
    ready = ready and until(page, f"() => document.querySelectorAll('{D} .dv-map-marker').length > 0 || !!document.querySelector('{D} [data-panel=\"deployments\"] tbody, {D} [data-panel=\"deployments\"] .dv-cards-card')")
    settle(page, 3)
    return page, ready


def run_files(page, since=0):
    """The per-run files the page asked for since request number `since`, as paths under the case."""
    return [url.split(f"/{CASE}/", 1)[1] for url in page.requests[since:] if f"/{CASE}/runs/" in url]


def foreign(page, *origins):
    return [url for url in page.requests if not url.startswith(tuple(origins)) and not url.startswith(("data:", "blob:"))]


def hash_selection(page, key):
    """The values the URL's s.<key>= names, as readHash reads them; None when absent, [] when empty."""
    fragment = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).fragment, keep_blank_values=True)
    if f"s.{key}" not in fragment:
        return None
    text = fragment[f"s.{key}"][0]
    if ":" not in text:
        return []
    return [urllib.parse.unquote(value) for value in text.split(":", 1)[1].split(",") if value != ""]


def hash_tab(page, key):
    fragment = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).fragment)
    return fragment[f"p.{key}"][0] if f"p.{key}" in fragment else None


def marker_spot(page, title):
    """Where a marker stands on screen, its panel in view: x, y and the marker the browser hit-tests there."""
    page.evaluate(STANDS, title)
    settle(page)
    box = page.locator(f'.dv-map-marker[title="{title}"]').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    return x, y, page.evaluate(HIT, [x, y])


def click_marker(page, title, *, keys=()):
    """A real click at the marker's on-screen position (a real tap on a touch page); True when the browser's hit-test
    there lands on that marker."""
    x, y, hit = marker_spot(page, title)
    for key in keys:
        page.keyboard.down(key)
    if page.evaluate("() => navigator.maxTouchPoints > 0"):
        page.touchscreen.tap(x, y)
    else:
        page.mouse.move(x, y)
        page.mouse.click(x, y)
        page.mouse.move(1, 1)
    for key in keys:
        page.keyboard.up(key)
    return hit == title


def click_chooser_row(page, row_id, *, keys=()):
    box = page.locator(f'.dv-map-choose-row[data-id="{row_id}"]').bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    for key in keys:
        page.keyboard.down(key)
    if page.evaluate("() => navigator.maxTouchPoints > 0"):
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)
        page.mouse.move(1, 1)
    for key in keys:
        page.keyboard.up(key)


def select_tab(page, name, key="deployments"):
    page.locator(f"{D} [data-panel='{key}'] [role=tab]", has_text=name).click()
    page.mouse.move(1, 1)
    arrived = until(page, WAIT_VIEW, [D, key, name])
    settle(page, 2)
    return arrived


def wait_state(page, key, values, root=D):
    return until(page, WAIT_STATE, [root, key, sorted(map(str, values)) if values is not None else None])


def wait_marked(page, titles, root=D):
    return until(page, WAIT_MARKED, [root, sorted(titles)], timeout=8000)


def wait_rows(page, key, column, want):
    return until(page, WAIT_DRAWN, [D, key, column, want])


def wait_points(page, run, panel="angle", column="q_deg", seconds=20):
    """The plot draws exactly the run's file: the same (t, value) pairs per situation; what differs if it never does."""
    want = series_points(run, column)
    deadline = time.monotonic() + seconds
    difference = None
    while time.monotonic() < deadline:
        drawn = page.evaluate(POINTS, [D, panel])
        difference = {series: [len((drawn or {}).get(series, [])), len(want.get(series, []))] for series in set(drawn or {}) | set(want)} or None
        if drawn is not None and {series: sorted(map(tuple, values)) for series, values in drawn.items()} == want:
            return None
        page.wait_for_timeout(100)
    return difference or "nothing drawn"


def table_row(page, key, column, value):
    """A real click on the table row holding `value` in `column`."""
    drawn = page.evaluate(DRAWN, [D, key, column])
    index = drawn.index(value)
    cell = page.locator(f"{D} [data-panel='{key}'] tbody tr[data-i='{index}'] td").first
    cell.scroll_into_view_if_needed()
    cell.click()
    page.mouse.move(1, 1)


def table_marked(page, key, column, value):
    """Only the row holding `value` wears the mark: its fill differs from every other row's, and those all match."""
    rows_drawn = page.evaluate(TABLE_MARKS, [D, key, column])
    picked = [fill for cell, fill in rows_drawn if cell == value]
    others = {fill for cell, fill in rows_drawn if cell != value}
    return len(picked) == 1 and len(others) == 1 and picked[0] not in others, rows_drawn[:4]


def luminance(rgb):
    channels = [c / 255 for c in rgb]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one, two):
    a, b = sorted((luminance(one), luminance(two)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def shot(page, name):
    # WHY the viewport, never full_page: Chromium's capture beyond the viewport garbles a WebGL canvas (measured on this case)
    try:
        page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as error:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {error})")


# ------------------------------------------------------------------------------------------------- opening
def opening(browser, site):
    page, ready = open_case(browser, site)
    check("the page opens: every panel drew", ready)
    check("the Deployments panel's tabs are Map, Table, Cards, and the map is open first",
          page.evaluate(TABS, [D, "deployments"]) == ["Map", "Table", "Cards"] and page.evaluate(ACTIVE_TAB, [D, "deployments"]) == "Map",
          page.evaluate(TABS, [D, "deployments"]))
    drawn = page.evaluate(MARKERS, D)
    want_titles = sorted(title_of(rows_here) for rows_here in points())
    check("one marker per point of deployments.json, each titled for its rows (a robot's name, or the first name and the count)",
          sorted(m["title"] for m in drawn) == want_titles, {"drawn": len(drawn), "points": len(want_titles)})
    # Web Mercator from the file: fit the scale and origin on the two farthest markers, then every marker must land there
    place = {title_of(rows_here): mercator(*rows_here[0]["coordinates"]) for rows_here in points()}
    on_screen = {m["title"]: (m["x"], m["y"]) for m in drawn}
    if len(on_screen) == len(place):
        west = min(place, key=lambda title: place[title][0])
        east = max(place, key=lambda title: place[title][0])
        scale = (on_screen[east][0] - on_screen[west][0]) / (place[east][0] - place[west][0])
        off = {}
        for title, (x, y) in place.items():
            off[title] = round(math.hypot(on_screen[west][0] + (x - place[west][0]) * scale - on_screen[title][0],
                                          on_screen[west][1] + (y - place[west][1]) * scale - on_screen[title][1]), 2)
        check("every marker stands where its row's coordinates say: Web Mercator worked out here, within 1.5 px of each one", max(off.values()) <= 1.5, off)
    else:
        check("every marker stands where its row's coordinates say: Web Mercator worked out here, within 1.5 px of each one", False, "not every marker drew")
    series = page.evaluate(f"() => document.querySelector('{D} .dd-panel[data-panel=\"deployments\"] data-views').tokens()")
    want_pin = {row["name"]: (series["series"][STATUS_SLOTS[row["status"]] - 1] if STATUS_SLOTS[row["status"]] else series["muted"]) for row in SINGLES}
    got_pin = {m["title"]: m["pin"] for m in drawn if m["title"] in want_pin}
    check("each robot's marker colour is its status's slot in deployments.json", got_pin == want_pin, {k: [got_pin.get(k), v] for k, v in list(want_pin.items())[:3]})
    check("selected: first picks the first row, the real rack: the state and the URL name it",
          page.evaluate(STATE, [D, "deployments"]) == [RACK["deployment"]] and hash_selection(page, "deployments") == [RACK["deployment"]], page.url)
    check("selected: marks the rack's marker, and no other", wait_marked(page, [RACK["name"]]), page.evaluate(MARKED, D))
    check("selected: presses the rack's marker for a screen reader (aria-pressed), and every other marker says false",
          page.evaluate(PRESSED, D) == [RACK["name"]] and all(m["pressed"] in ("true", "false") for m in page.evaluate(MARKERS, D)),
          {m["title"]: m["pressed"] for m in page.evaluate(MARKERS, D)})
    check("the runs panel opens on the rack's runs, newest first", page.evaluate(DRAWN, [D, "runs", "run"]) == runs_of(RACK["deployment"]), page.evaluate(DRAWN, [D, "runs", "run"]))
    newest = runs_of(RACK["deployment"])[0]
    check("the rack's newest run is picked and its file, only that one, is read", page.evaluate(STATE, [D, "runs"]) == [newest] and run_files(page) == [f"runs/{enc(newest)}.json"], run_files(page))
    check("the page says what is synthetic: the text panel, and the rack's plot says real", "Synthetic" in page.locator(f"{D} .dd-panel-text").inner_text() and "real" in page.locator(f"{D} [data-panel='angle']").inner_text(),
          page.locator(f"{D} .dd-panel-text").inner_text()[:90])
    check("opening: nothing from another origin, no page error", not foreign(page, site) and not page.errors, (foreign(page, site)[:2], page.errors[:3]))
    shot(page, "open-map")
    page.context.close()


# ------------------------------------------------------------------------------------------------- a marker picks
def picking(browser, site):
    page, ready = open_case(browser, site)
    for row in (ROBOT_A, ROBOT_B):
        name, deployment = row["name"], row["deployment"]
        before = {m["title"]: (m["x"], m["y"]) for m in page.evaluate(MARKERS, D)}
        since = len(page.requests)
        landed = click_marker(page, name)
        arrived = wait_state(page, "deployments", [deployment])
        check(f"{name}: a real click at its marker's on-screen position lands on that marker and picks its row, in the state and the URL",
              ready and landed and arrived and hash_selection(page, "deployments") == [deployment], {"hit": landed, "url": page.url})
        check(f"{name}: the panel's label names it", page.evaluate(LABEL, [D, "deployments"]) == f"selected: {name}", page.evaluate(LABEL, [D, "deployments"]))
        want_runs = runs_of(deployment)
        check(f"{name}: the runs panel equals that deployment's {len(want_runs)} rows of runs.json, newest first", wait_rows(page, "runs", "run", want_runs), page.evaluate(DRAWN, [D, "runs", "run"]))
        newest = want_runs[0]
        check(f"{name}: its newest run is picked with it, one pick (the first robot's run does not stay selected)",
              wait_state(page, "runs", [newest]) and hash_selection(page, "runs") == [newest], {"state": page.evaluate(STATE, [D, "runs"]), "url": page.url})
        check(f"{name}: the playback waits for nothing", until(page, "(root) => !document.querySelector(`${root} .dd-panel[data-wait]`)", D, timeout=8000), page.evaluate(WAITING, D))
        check(f"{name}: exactly that run's file is fetched", run_files(page, since) == [f"runs/{enc(newest)}.json"], run_files(page, since))
        check(f"{name}: the clock spans exactly that file's t", until(page, WAIT_SPAN, [D, span(newest)], timeout=8000), {"clock": page.evaluate(SPAN, D), "file": span(newest)})
        difference = wait_points(page, newest, seconds=8)
        check(f"{name}: the Angle plot draws that file's points", difference is None, difference)
        check(f"{name}: a synthetic run's plot says synthetic", "synthetic" in page.locator(f"{D} [data-panel='angle']").inner_text())
        check(f"{name}: its marker is the one marked and pressed", wait_marked(page, [name]) and page.evaluate(PRESSED, D) == [name], page.evaluate(MARKED, D))
        after = {m["title"]: (m["x"], m["y"]) for m in page.evaluate(MARKERS, D)}
        moved = {title: spot for title, spot in after.items() if math.hypot(spot[0] - before[title][0], spot[1] - before[title][1]) > 1}
        # the page scrolled the panel into view once: a pick itself leaves the camera where it was, so all move alike or none
        shift = {(round(after[t][0] - before[t][0]), round(after[t][1] - before[t][1])) for t in after}
        check(f"{name}: a pick leaves the map where it was (no marker moves against another)", len(shift) == 1, {"moved": len(moved), "shifts": sorted(shift)[:4]})
    shot(page, "picked-robot")

    # a picked run: a click on the older run reads that file
    runs_here = runs_of(ROBOT_B["deployment"])
    since = len(page.requests)
    table_row(page, "runs", "run", runs_here[1])
    check("a click on an older run picks it", wait_state(page, "runs", [runs_here[1]]))
    check("... and reads exactly its file; the clock spans it", until(page, WAIT_SPAN, [D, span(runs_here[1])], timeout=8000) and run_files(page, since) == [f"runs/{enc(runs_here[1])}.json"], run_files(page, since))

    # back to the real rack
    since = len(page.requests)
    click_marker(page, RACK["name"])
    newest = runs_of(RACK["deployment"])[0]
    check("back on the rack: its newest run is picked and its real plot draws, from the file read when the page opened (nothing fetched again)",
          wait_state(page, "runs", [newest]) and wait_points(page, newest, seconds=8) is None and run_files(page, since) == [], run_files(page, since))
    check("the rack's plot says real", "real" in page.locator(f"{D} [data-panel='angle']").inner_text() and "synthetic" not in page.locator(f"{D} [data-panel='angle']").inner_text())
    check("picking: no page error", not page.errors, page.errors[:3])
    page.context.close()


def adding(browser, site):
    page, ready = open_case(browser, site)
    name_a, name_b = ROBOT_A["name"], ROBOT_B["name"]
    click_marker(page, name_a)
    wait_state(page, "deployments", [ROBOT_A["deployment"]])
    both = [ROBOT_A["deployment"], ROBOT_B["deployment"]]
    held_run = runs_of(ROBOT_A["deployment"])[0]
    wait_state(page, "runs", [held_run])
    since = len(page.requests)
    click_marker(page, name_b, keys=["Control"])
    check("a ctrl-click adds a second robot, as the table's does: both in the state and the URL",
          wait_state(page, "deployments", both) and sorted(hash_selection(page, "deployments") or []) == sorted(both), page.url)
    check("... both markers are marked", wait_marked(page, [name_a, name_b]), page.evaluate(MARKED, D))
    check("... the runs panel lists both, newest first", wait_rows(page, "runs", "run", runs_of(*both)), page.evaluate(DRAWN, [D, "runs", "run"]))
    check("... the run picked before is still theirs, so it stays and nothing is fetched", page.evaluate(STATE, [D, "runs"]) == [held_run] and run_files(page, since) == [], run_files(page, since))
    click_marker(page, name_b, keys=["Meta"])
    check("a cmd-click on a picked robot takes it out", wait_state(page, "deployments", [ROBOT_A["deployment"]]) and wait_marked(page, [name_a]), page.evaluate(MARKED, D))
    click_marker(page, name_a)
    check("a plain click on the one picked robot clears it, as a table row's does: the URL says cleared, no marker is marked",
          wait_state(page, "deployments", None) and hash_selection(page, "deployments") == [] and wait_marked(page, []), {"url": page.url, "marked": page.evaluate(MARKED, D)})
    check("... the runs panel lists every run", wait_rows(page, "runs", "run", runs_of(*[row["deployment"] for row in FLEET])))
    check("adding: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- a counted marker
def counted(browser, site):
    page, ready = open_case(browser, site)
    first, second = COUNTED_ROWS[0], COUNTED_ROWS[1]
    title = title_of(COUNTED_ROWS)
    before = page.evaluate(STATE, [D, "deployments"])
    pressed_at_rest = next(m for m in page.evaluate(MARKERS, D) if m["title"] == title)
    check("a counted marker says it opens something (aria-expanded false)", "aria-expanded" in pressed_at_rest["attributes"], pressed_at_rest["attributes"])
    landed = click_marker(page, title)
    opened = until(page, WAIT_CHOOSER, D, timeout=8000)
    chooser = page.evaluate(CHOOSER, D)
    check("a click on a counted marker asks which: a chooser lists exactly the rows at that point, by name, in file order",
          ready and landed and opened and chooser is not None and [r["text"] for r in chooser["rows"]] == [row["name"] for row in COUNTED_ROWS]
          and [r["id"] for r in chooser["rows"]] == [row["id"] for row in COUNTED_ROWS], chooser)
    check("... it is a labelled group", bool(chooser) and chooser["role"] == "group" and bool(chooser["label"]), chooser and [chooser["role"], chooser["label"]])
    check("... no pick is made until the reader names a row", page.evaluate(STATE, [D, "deployments"]) == before, page.evaluate(STATE, [D, "deployments"]))
    check("... the marker says it is open (aria-expanded true)", page.locator(f'.dv-map-marker[title="{title}"]').get_attribute("aria-expanded") == "true")
    shot(page, "chooser")
    with guard("a pick from the chooser"):
        click_chooser_row(page, second["id"])
        check("a click on a row picks that row, not the other", wait_state(page, "deployments", [second["deployment"]]) and hash_selection(page, "deployments") == [second["deployment"]], page.url)
        check("... the runs panel equals that row's runs", wait_rows(page, "runs", "run", runs_of(second["deployment"])), page.evaluate(DRAWN, [D, "runs", "run"]))
        check("... the chooser closes and focus returns to the marker", until(page, NO_CHOOSER, timeout=8000) and page.evaluate(FOCUS).get("marker") == title, page.evaluate(FOCUS))
        check("... the counted marker is marked", wait_marked(page, [title]), page.evaluate(MARKED, D))
    with guard("a ctrl-click in the chooser"):
        click_marker(page, title)
        until(page, WAIT_CHOOSER, D, timeout=8000)
        pressed = {r["id"]: r["pressed"] for r in page.evaluate(CHOOSER, D)["rows"]}
        check("reopened, the chooser presses the picked row and not the other", pressed == {first["id"]: "false", second["id"]: "true"}, pressed)
        click_chooser_row(page, first["id"], keys=["Control"])
        both = [first["deployment"], second["deployment"]]
        check("a ctrl-click on a row adds it, and the chooser stays open", wait_state(page, "deployments", both) and page.evaluate(CHOOSER, D) is not None, page.evaluate(STATE, [D, "deployments"]))
        check("... both rows are pressed", until(page, "(root) => { const c = document.querySelector(`${root} .dv-map-choose`); return !!c && [...c.querySelectorAll('.dv-map-choose-row')].every((b) => b.getAttribute('aria-pressed') === 'true'); }", D, timeout=8000))
        click_chooser_row(page, first["id"], keys=["Control"])
        check("a second ctrl-click takes it out", wait_state(page, "deployments", [second["deployment"]]) and page.evaluate(CHOOSER, D) is not None, page.evaluate(STATE, [D, "deployments"]))
    with guard("closing the chooser"):
        page.keyboard.press("Escape")
        check("Escape closes the chooser, changes no pick and returns focus to the marker",
              until(page, NO_CHOOSER, timeout=8000) and page.evaluate(STATE, [D, "deployments"]) == [second["deployment"]] and page.evaluate(FOCUS).get("marker") == title, page.evaluate(FOCUS))
        click_marker(page, title)
        until(page, WAIT_CHOOSER, D, timeout=8000)
        mount = page.locator(f"{D} [data-panel='deployments'] .dv-map-mount").bounding_box()
        page.mouse.click(mount["x"] + mount["width"] / 2, mount["y"] + mount["height"] / 2)
        page.mouse.move(1, 1)
        check("a click on the map closes the chooser and changes no pick", until(page, NO_CHOOSER, timeout=8000) and page.evaluate(STATE, [D, "deployments"]) == [second["deployment"]], page.evaluate(STATE, [D, "deployments"]))
    with guard("the chooser across a tab switch"):
        click_marker(page, title)
        until(page, WAIT_CHOOSER, D, timeout=8000)
        select_tab(page, "Table")
        check("a tab switch closes the chooser: nothing of it stays on the page", page.evaluate(NO_CHOOSER))
        select_tab(page, "Map")
        settle(page, 3)
        check("back on the map, no chooser reopens", page.evaluate(NO_CHOOSER))
        landed = click_marker(page, ROBOT_A["name"])
        check("back on the map, the markers pick (the kept map's new markers call this view's host)", landed and wait_state(page, "deployments", [ROBOT_A["deployment"]]), page.evaluate(STATE, [D, "deployments"]))
    check("counted: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the keyboard
def tab_to(page, title, limit=60):
    """Real Tab presses from the map's canvas until the marker has focus; False when the keyboard never reaches it."""
    page.locator(f"{D} [data-panel='deployments'] canvas").first.focus()
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate(FOCUS).get("marker") == title:
            return True
    return False


def keyboard(browser, site):
    page, ready = open_case(browser, site)
    reached = tab_to(page, ROBOT_A["name"])
    check("Tab reaches a marker from the map", ready and reached, page.evaluate(FOCUS))
    page.keyboard.press("Enter")
    check("Enter on a marker picks its row", wait_state(page, "deployments", [ROBOT_A["deployment"]]) and wait_marked(page, [ROBOT_A["name"]]), page.evaluate(STATE, [D, "deployments"]))
    check("... and focus stays on the marker", page.evaluate(FOCUS).get("marker") == ROBOT_A["name"], page.evaluate(FOCUS))
    tab_to(page, ROBOT_B["name"])
    page.keyboard.press("Space")
    check("Space on a marker picks its row", wait_state(page, "deployments", [ROBOT_B["deployment"]]) and wait_marked(page, [ROBOT_B["name"]]), page.evaluate(STATE, [D, "deployments"]))
    title = title_of(COUNTED_ROWS)
    first, second = COUNTED_ROWS[0], COUNTED_ROWS[1]
    reached = tab_to(page, title)
    page.keyboard.press("Enter")
    opened = until(page, WAIT_CHOOSER, D, timeout=8000)
    check("Enter on a counted marker opens its chooser, focus on the first row", reached and opened and page.evaluate(FOCUS).get("row") == first["id"], page.evaluate(FOCUS))
    page.keyboard.press("ArrowDown")
    check("ArrowDown moves to the next row", page.evaluate(FOCUS).get("row") == second["id"], page.evaluate(FOCUS))
    page.keyboard.press("ArrowUp")
    check("ArrowUp moves back", page.evaluate(FOCUS).get("row") == first["id"], page.evaluate(FOCUS))
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    check("Enter on a row picks it, closes the chooser and returns focus to the marker",
          wait_state(page, "deployments", [second["deployment"]]) and until(page, NO_CHOOSER, timeout=8000) and page.evaluate(FOCUS).get("marker") == title,
          {"state": page.evaluate(STATE, [D, "deployments"]), "focus": page.evaluate(FOCUS)})
    check("keyboard: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- tabs, reload, history
def tabs(browser, site):
    page, ready = open_case(browser, site)
    click_marker(page, ROBOT_A["name"])
    wait_state(page, "deployments", [ROBOT_A["deployment"]])
    arrived = select_tab(page, "Table")
    check("map → table: the pick survives in the state and the URL, and the URL names the tab",
          ready and arrived and page.evaluate(STATE, [D, "deployments"]) == [ROBOT_A["deployment"]] and hash_selection(page, "deployments") == [ROBOT_A["deployment"]] and hash_tab(page, "deployments") == "table", page.url)
    ok, sample = table_marked(page, "deployments", "deployment", ROBOT_A["deployment"])
    check("... the table marks that row, and no other", ok, sample)
    shot(page, "table-tab")
    table_row(page, "deployments", "deployment", ROBOT_B["deployment"])
    check("a row picked in the table tab is the panel's pick", wait_state(page, "deployments", [ROBOT_B["deployment"]]) and wait_rows(page, "runs", "run", runs_of(ROBOT_B["deployment"])), page.url)
    check("... with its newest run", wait_state(page, "runs", [runs_of(ROBOT_B["deployment"])[0]]), page.evaluate(STATE, [D, "runs"]))
    select_tab(page, "Map")
    check("table → map: the marker of the row picked in the table is marked, and no other", until(page, f"() => document.querySelectorAll('{D} .dv-map-marker').length > 0") and wait_marked(page, [ROBOT_B["name"]]), page.evaluate(MARKED, D))
    check("... the pick is still in the state and the URL", page.evaluate(STATE, [D, "deployments"]) == [ROBOT_B["deployment"]] and hash_selection(page, "deployments") == [ROBOT_B["deployment"]], page.url)
    select_tab(page, "Cards")
    cards = page.evaluate(CARDS, [D, "deployments"])
    mine = [card for card in cards if card["id"] == ROBOT_B["id"]]
    others = [card for card in cards if card["id"] != ROBOT_B["id"]]
    check("map → cards: the picked robot's card is marked, and no other", len(mine) == 1 and mine[0]["marked"] and not any(card["marked"] for card in others), mine)
    check("... the mark is painted: its fill or border differs from every other card's",
          bool(mine) and bool(others) and (mine[0]["fill"], mine[0]["border"]) != (others[0]["fill"], others[0]["border"]) and len({(c["fill"], c["border"]) for c in others}) == 1,
          mine and [mine[0]["fill"], mine[0]["border"], others[0]["fill"], others[0]["border"]])
    shot(page, "cards-tab")
    page.locator(f"{D} [data-panel='deployments'] .dv-cards-card[data-id='{ROBOT_A['id']}']").click(position={"x": 12, "y": 60})
    page.mouse.move(1, 1)
    check("a card click is the panel's pick", wait_state(page, "deployments", [ROBOT_A["deployment"]]), page.evaluate(STATE, [D, "deployments"]))
    check("... the mark moves to that card, live", until(page, f"(id) => {{ const on = [...document.querySelectorAll('{D} .dv-cards-card.dv-sel')].map((c) => c.dataset.id); return on.length === 1 && on[0] === id; }}", ROBOT_A["id"], timeout=8000),
          [card["id"] for card in page.evaluate(CARDS, [D, "deployments"]) if card["marked"]])
    select_tab(page, "Map")
    check("cards → map: that robot's marker is marked", until(page, f"() => document.querySelectorAll('{D} .dv-map-marker').length > 0") and wait_marked(page, [ROBOT_A["name"]]), page.evaluate(MARKED, D))
    check("tabs: no page error", not page.errors, page.errors[:3])
    page.context.close()


def reloads(browser, site):
    page, ready = open_case(browser, site)
    click_marker(page, ROBOT_B["name"])
    wait_state(page, "deployments", [ROBOT_B["deployment"]])
    newest = runs_of(ROBOT_B["deployment"])[0]
    wait_state(page, "runs", [newest])
    since = len(page.requests)
    page.reload()
    came_back = until(page, READY, [D, ["deployments", "runs", "playback"]]) and until(page, f"() => document.querySelectorAll('{D} .dv-map-marker').length > 0")
    settle(page, 3)
    check("a reload restores the pick from the URL", ready and came_back and page.evaluate(STATE, [D, "deployments"]) == [ROBOT_B["deployment"]] and page.evaluate(STATE, [D, "runs"]) == [newest], page.url)
    check("... the restored pick's marker is marked, and no other", wait_marked(page, [ROBOT_B["name"]]), page.evaluate(MARKED, D))
    check("... the runs panel equals its rows and only its run's file is read", wait_rows(page, "runs", "run", runs_of(ROBOT_B["deployment"])) and run_files(page, since) == [f"runs/{enc(newest)}.json"], run_files(page, since))
    select_tab(page, "Table")
    page.reload()
    came_back = until(page, READY, [D, ["deployments", "runs", "playback"]])
    settle(page, 3)
    check("a reload on the table tab stays on it with the pick marked", came_back and page.evaluate(ACTIVE_TAB, [D, "deployments"]) == "Table" and table_marked(page, "deployments", "deployment", ROBOT_B["deployment"])[0], page.url)
    select_tab(page, "Map")
    check("... and the map tab marks it", until(page, f"() => document.querySelectorAll('{D} .dv-map-marker').length > 0") and wait_marked(page, [ROBOT_B["name"]]), page.evaluate(MARKED, D))
    check("reloads: no page error", not page.errors, page.errors[:3])
    page.context.close()
    linked, ready = open_case(browser, site, fragment=f"#s.deployments=deployment:{ROBOT_B['deployment']}")
    check("a link naming only the robot opens on it, its marker marked and its newest run picked by the preset",
          ready and wait_state(linked, "runs", [newest]) and wait_marked(linked, [ROBOT_B["name"]]), {"state": linked.evaluate(STATE, [D, "runs"]), "marked": linked.evaluate(MARKED, D)})
    linked.context.close()


def history(browser, site):
    page, ready = open_case(browser, site)
    length = page.evaluate("() => history.length")
    click_marker(page, ROBOT_A["name"])
    wait_state(page, "deployments", [ROBOT_A["deployment"]])
    wait_state(page, "runs", [runs_of(ROBOT_A["deployment"])[0]])
    check("a pick is one history entry", ready and page.evaluate("() => history.length") == length + 1, [length, page.evaluate("() => history.length")])
    click_marker(page, ROBOT_B["name"])
    wait_state(page, "deployments", [ROBOT_B["deployment"]])
    wait_state(page, "runs", [runs_of(ROBOT_B["deployment"])[0]])
    check("a second pick, with the run it brings, is one more", page.evaluate("() => history.length") == length + 2, [length, page.evaluate("() => history.length")])
    since = len(page.requests)
    page.go_back()
    check("Back restores the first pick: the state, its marker, its runs, its run",
          wait_state(page, "deployments", [ROBOT_A["deployment"]]) and wait_marked(page, [ROBOT_A["name"]]) and wait_rows(page, "runs", "run", runs_of(ROBOT_A["deployment"]))
          and wait_state(page, "runs", [runs_of(ROBOT_A["deployment"])[0]]), {"marked": page.evaluate(MARKED, D), "url": page.url})
    check("... the clock spans its file, read before (nothing fetched)", until(page, WAIT_SPAN, [D, span(runs_of(ROBOT_A["deployment"])[0])], timeout=8000) and run_files(page, since) == [], run_files(page, since))
    page.go_back()
    check("Back again restores the page as it opened: the rack, marked", wait_state(page, "deployments", [RACK["deployment"]]) and wait_marked(page, [RACK["name"]]), page.evaluate(MARKED, D))
    page.go_forward()
    page.go_forward()
    check("Forward twice returns to the second pick, marked", wait_state(page, "deployments", [ROBOT_B["deployment"]]) and wait_marked(page, [ROBOT_B["name"]]) and wait_state(page, "runs", [runs_of(ROBOT_B["deployment"])[0]]), page.evaluate(MARKED, D))
    check("history: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
def looks(browser, site):
    title = title_of(LAST_COUNTED)
    for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        page, ready = open_case(browser, site, width=width, dark=dark)
        check(f"{tag}: no sideways scroll", ready and page.evaluate(SIDEWAYS) <= width, page.evaluate(SIDEWAYS))
        with guard(f"{tag}: the mark"):
            tokens = page.evaluate(f"() => document.querySelector('{D} .dd-panel[data-panel=\"deployments\"] data-views').tokens()")
            ring = page.evaluate("""(title) => { const on = document.querySelector('#example .dv-map-marker.dv-sel'); const off = [...document.querySelectorAll('#example .dv-map-marker')].find((m) => !m.classList.contains('dv-sel'));
              if (!on || !off) return null; const a = getComputedStyle(on), b = getComputedStyle(off);
              return { style: a.outlineStyle, width: parseFloat(a.outlineWidth), colour: a.outlineColor, restStyle: b.outlineStyle, restWidth: parseFloat(b.outlineWidth) }; }""", title)
            land = page.evaluate(RGB, tokens["bg"])
            painted = page.evaluate(RGB, ring["colour"]) if ring else None
            check(f"{tag}: the picked marker wears a ring of at least 2 px, the others none", bool(ring) and ring["style"] != "none" and ring["width"] >= 2 and (ring["restStyle"] == "none" or ring["restWidth"] == 0), ring)
            check(f"{tag}: the ring reads against the land (at least 3:1)", bool(painted) and contrast(painted, land) >= 3, painted and round(contrast(painted, land), 2))
        with guard(f"{tag}: the chooser"):
            landed = click_marker(page, title)
            opened = until(page, WAIT_CHOOSER, D, timeout=8000)
            settle(page, 2)
            chooser = page.evaluate(CHOOSER, D)
            check(f"{tag}: a real {'tap' if width < 500 else 'click'} on a counted marker opens its chooser, wholly on screen", ready and landed and opened and chooser["left"] >= 0 and chooser["right"] <= width, chooser and [chooser["left"], chooser["right"]])
            check(f"{tag}: no sideways scroll with the chooser open", page.evaluate(SIDEWAYS) <= width, page.evaluate(SIDEWAYS))
            colours = page.evaluate("""() => { const b = document.querySelector('.dv-map-choose-row'); let e = b; let fill = 'rgba(0, 0, 0, 0)';
              while (e && fill === 'rgba(0, 0, 0, 0)') { fill = getComputedStyle(e).backgroundColor; e = e.parentElement; } return { text: getComputedStyle(b).color, fill }; }""")
            text, fill = page.evaluate(RGB, colours["text"]), page.evaluate(RGB, colours["fill"])
            check(f"{tag}: the chooser sits on the kit's surface", fill == land, [fill, land])
            check(f"{tag}: its text reads at 4.5:1 or better", contrast(text, fill) >= 4.5, round(contrast(text, fill), 2))
            shot(page, f"chooser-{'dark' if dark else 'light'}-{width}")
            second = LAST_COUNTED[1]
            click_chooser_row(page, second["id"])
            check(f"{tag}: a row in the chooser picks it", wait_state(page, "deployments", [second["deployment"]]) and wait_marked(page, [title]), page.evaluate(STATE, [D, "deployments"]))
            settle(page, 2)
            shot(page, f"picked-{'dark' if dark else 'light'}-{width}")
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()


# ------------------------------------------------------------------------------------------------- no select:, the host's marks
MOUNT = """async ([tag, src, attributes]) => {
  document.body.innerHTML = '';
  const el = document.createElement(tag); el.id = 'dash';
  for (const a of attributes) el.setAttribute(a, '');
  el.setAttribute('src', src);
  document.body.append(el); window.el = el;
}"""


def mount(page, origin, tag, name, attributes=()):
    page.goto(origin + FIXTURE + "page.html")
    until(page, "() => window.kitReady")
    page.evaluate(MOUNT, [tag, FIXTURE + name, list(attributes)])
    until(page, "() => document.querySelectorAll('#dash .dv-map-marker').length > 0")
    settle(page, 3)


def no_select(browser, origin):
    title = title_of(COUNTED_ROWS)
    page = new_page(browser)
    mount(page, origin, "data-dashboard", "no-select.base")
    drawn = page.evaluate(MARKERS, "#dash")
    check("no select: on a dashboard, one marker per point as ever", len(drawn) == len(points()), len(drawn))
    check("no select:, a marker has no aria-pressed and no aria-expanded: only its aria-label, as ever", all(m["attributes"] == ["aria-label"] for m in drawn), drawn[0]["attributes"] if drawn else None)
    landed = click_marker(page, ROBOT_A["name"])
    peeked = until(page, "() => { const p = document.querySelector('#dash .dd-drill .dv-peek'); return !!p && !p.hidden; }", timeout=8000)
    check("no select: on a dashboard, a marker click opens the peek on its row", landed and peeked and ROBOT_A["name"] in page.locator("#dash .dd-drill .dv-peek h2").first.inner_text(), peeked)
    check("... and selects nothing", page.evaluate("() => JSON.stringify(document.querySelector('#dash').state.select)") == "{}" and page.evaluate(MARKED, "#dash") == [])
    page.keyboard.press("Escape")
    click_marker(page, title)
    settle(page, 3)
    listed = page.locator("#dash .dd-drill .dv-peek .dv-peektable tbody tr").count()
    check("no select: on a dashboard, a counted marker lists its rows in the peek and opens no chooser", listed == len(COUNTED_ROWS) and page.evaluate(NO_CHOOSER), listed)
    check("no select: on a dashboard: no page error", not page.errors, page.errors[:3])
    page.context.close()

    page = new_page(browser)
    mount(page, origin, "data-views", "plain.base", ["no-url"])
    drawn = page.evaluate(MARKERS, "#dash")
    check("a plain <data-views> map: a marker has no aria-pressed and no aria-expanded", all(m["attributes"] == ["aria-label"] for m in drawn), drawn[0]["attributes"] if drawn else None)
    landed = click_marker(page, ROBOT_A["name"])
    peeked = until(page, "() => { const p = document.querySelector('#dash .dv-peek'); return !!p && !p.hidden; }", timeout=8000)
    check("a plain <data-views> map: a marker click opens the peek on its row", landed and peeked and ROBOT_A["name"] in page.locator("#dash .dv-peek h2").first.inner_text(), peeked)
    page.keyboard.press("Escape")
    click_marker(page, title)
    settle(page, 3)
    listed = page.locator("#dash .dv-peek .dv-peektable tbody tr").count()
    check("a plain <data-views> map: a counted marker lists its rows in the peek and opens no chooser", listed == len(COUNTED_ROWS) and page.evaluate(NO_CHOOSER), listed)
    check("a plain <data-views> map: no page error", not page.errors, page.errors[:3])
    page.context.close()


def same_value(browser, origin):
    """A counted marker whose rows hold one value of select: is one pick: nothing to ask."""
    site_name = COUNTED_ROWS[0]["site"]
    check("the fixture's premise: the rows at the counted point share one site", len({row["site"] for row in COUNTED_ROWS}) == 1, site_name)
    page = new_page(browser)
    mount(page, origin, "data-dashboard", "same-value.base")
    title = title_of(COUNTED_ROWS)
    landed = click_marker(page, title)
    check("select: site on a counted marker of one site picks that site at once, no chooser",
          landed and until(page, "(want) => { const s = document.querySelector('#dash').state.select.map; return !!s && JSON.stringify(s.values) === JSON.stringify(want); }", [site_name], timeout=8000) and page.evaluate(NO_CHOOSER),
          page.evaluate("() => document.querySelector('#dash').state.select"))
    check("... and its marker is marked", until(page, WAIT_MARKED, ["#dash", [title]], timeout=8000), page.evaluate(MARKED, "#dash"))
    check("same value: no page error", not page.errors, page.errors[:3])
    page.context.close()


def host_marks(browser, origin):
    page = new_page(browser)
    mount(page, origin, "data-views", "plain.base", ["no-url"])
    target = ROBOT_A
    page.evaluate("() => { window.events = 0; window.el.addEventListener('data-views-select', () => { window.events += 1; }); }")
    page.evaluate("(id) => { window.el.picked = [id]; }", target["id"])
    check("el.picked marks the row's marker through selected(set), without a redraw", wait_marked(page, [target["name"]], root="#dash"), page.evaluate(MARKED, "#dash"))
    check("... it reads back", page.evaluate("() => window.el.picked") == [target["id"]], page.evaluate("() => window.el.picked"))
    check("... it is not the selection: el.selection is empty, no bulk bar, no data-views-select",
          page.evaluate("() => window.el.selection.length") == 0 and page.evaluate("() => { const b = window.el.querySelector('.dv-bulk'); return !b || b.hidden; }") and page.evaluate("() => window.events") == 0)
    counted_id = COUNTED_ROWS[1]["id"]
    page.evaluate("(id) => { window.el.picked = [id]; }", counted_id)
    check("one picked row among several marks their counted marker", wait_marked(page, [title_of(COUNTED_ROWS)], root="#dash"), page.evaluate(MARKED, "#dash"))
    page.evaluate("(id) => { window.el.picked = [id]; window.el.filters = 'status != \"nothing\"'; }", target["id"])
    settle(page, 4)
    check("a redraw keeps the mark (input.selected)", wait_marked(page, [target["name"]], root="#dash"), page.evaluate(MARKED, "#dash"))
    page.evaluate("() => { window.el.selectView('Table'); }")
    until(page, "() => window.el.view.name === 'Table' && window.el.dataset.view === 'table'")
    page.evaluate("(id) => { window.el.picked = [id]; }", ROBOT_B["id"])
    page.evaluate("() => { window.el.selectView('Map'); }")
    until(page, "() => document.querySelectorAll('#dash .dv-map-marker').length > 0")
    check("marks set while another view shows reach the map when it draws (a new view reads input.selected)", wait_marked(page, [ROBOT_B["name"]], root="#dash"), page.evaluate(MARKED, "#dash"))
    page.evaluate("() => { window.el.picked = []; }")
    check("el.picked = [] clears the marks", wait_marked(page, [], root="#dash"), page.evaluate(MARKED, "#dash"))
    check("host marks: no page error", not page.errors, page.errors[:3])
    page.context.close()

    page = new_page(browser)
    mount(page, origin, "data-views", "plain.base", ["no-url", "selectable"])
    page.evaluate("(id) => { window.el.select([id]); }", ROBOT_B["id"])
    check("a map view marks the element's own selection too (§15: el.select, selected(set))", wait_marked(page, [ROBOT_B["name"]], root="#dash"), page.evaluate(MARKED, "#dash"))
    check("selection: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- the site
def gallery(browser, site):
    listed = next((row for row in json.loads((SITE / "gallery" / "gallery.json").read_text(encoding="utf-8"))["rows"] if row["slug"] == CASE), None)
    check("the gallery lists the case under Robotics · Navigation", bool(listed) and listed.get("category") == "Robotics" and listed.get("useCase") == "Robotics · Navigation", listed and [listed.get("category"), listed.get("useCase")])
    page = new_page(browser)
    page.goto(f"{site}/gallery/index.html")
    until(page, "() => !!document.querySelector('main.gallery[data-cols]')")
    check("the gallery index shows its card", page.locator(f".type-group[data-group='Robotics'] .card[data-slug='{CASE}']").count() == 1)
    page.context.close()


def main():
    site_server, site = serve(SITE, f"/gallery/{CASE}/index.html")
    repo_server, origin = serve(ROOT, FIXTURE + "page.html")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for name, section, where in (("opening", opening, site), ("picking", picking, site), ("adding", adding, site), ("counted", counted, site), ("keyboard", keyboard, site),
                                         ("tabs", tabs, site), ("reloads", reloads, site), ("history", history, site), ("looks", looks, site), ("no select", no_select, origin),
                                         ("same value", same_value, origin), ("host marks", host_marks, origin), ("gallery", gallery, site)):
                with guard(name):
                    section(browser, where)
            browser.close()
    finally:
        site_server.terminate()
        site_server.wait(timeout=10)
        repo_server.terminate()
        repo_server.wait(timeout=10)
    (OUT / "fleet-map-checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    passed = sum(1 for item in checks if item["ok"])
    print(f"{passed}/{len(checks)} fleet map checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
