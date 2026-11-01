"""RobotDx's five asks of data-ui (RobotDx PEP 0001 §17.1, found wiring /dx/'s "Add to dashboard"; docs/CONTRACT.md §26,
§31, §34), measured in headless Chromium on the built kit. Written red, before the code; never edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/dx_asks_checks.py [OUT_DIR]     # after npm run build

The fixture is tests/browser/fixtures/dx_asks/: live.base (a live dashboard whose rows the page pushes on the wall clock,
t in Unix seconds as RobotDx's host sends them, with the live `plot` card), live-target.base (a dashboard already reading
the same live file), recorded.base (the plot card over a recording, in a plain <data-views>), boards/board-a.base and
board-b.base (drawn by the page's own load(), as /dx/ draws its dashboards, one shared dataset handed to both while each
declares its own file), src-board.base (the same drawn from its src) and self.base (the dashboard a reader adds to from
its own panel; this script's server keeps its text in memory and saves a PUT). The page plays the host.
  1. The live plot's legend is §31's: one <button aria-pressed> per series; a click hides a series (uPlot's series
     `show` and its pixels on the canvas), through live frames; Alt + click and a double-click isolate, again shows all;
     Reset; y rescales to the series shown, x stays; the hidden set in the URL (l.<panel>= in a dashboard, l= on a plain
     <data-views>) and read back from it; the series' item menu (right-click, Shift+F10) offers Show only and "Add “…”
     to dashboard…", whose panel is the plot with every other series hidden, drawn so where it is loaded.
  2. In a <data-dashboard> panelSpec() names the file the dashboard declares for the panel's dataset (board B's
     config.json?path=b), not the url of the dataset object the host shares across dashboards (board A's).
  3. "At this moment" from a following live dashboard: the saved panel, loaded where the same live data keeps arriving,
     stands at its t (its clock paused at t, following false; its plot's window ending at t), through a reload.
  4. The picker survives a reload of its own dashboard (the host saves and draws it again, before or after it answers,
     with reload() or with load() as /dx/ does): still there, where it was, saying "Added to Self"; a second add from it
     reaches the host; it closes when its dashboard leaves the page.
  5. On a clock whose time is an epoch, the picker's moment and the pinned panel's "at t = …" write t as the playback
     bar does (the kit's fmtTime: a wall-clock time), never "1792631514.923 s"; the exact seconds stay one step away (the
     element's title).
  Light and dark at 1280 and 390 px: the legend inside its panel, a hidden entry greyed and struck through, the item
  menu and the picker inside the viewport in the theme's colours, the pinned header inside its panel, no sideways scroll.
Serves the repo root on a free 127.0.0.1 port (its own server, for the PUT), stops it when done, writes
OUT_DIR/dx-asks-checks.json (default reports/media/dx-asks) with the screenshots, and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import os
import pathlib
import re
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "dx-asks"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "dx_asks"
URL = "/tests/browser/fixtures/dx_asks/"
PAGE = URL + "page.html"
SELF = URL + "self.base"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
JOINTS = ["base", "elbow", "shoulder", "wrist"]   # the legend's order (the store's streams, sorted)
OUTLIER = "base"                                   # 100 times the others' swing
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:400]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


# ------------------------------------------------------------------------------------------------- the server
MEM: dict[str, str] = {}      # path -> text: the dashboards the page's host saves (self.base)
PUTS: list[tuple[str, str]] = []


class Handler(http.server.SimpleHTTPRequestHandler):
    """The repo's files, plus self.base kept in memory: GET reads it, PUT saves it (a host's save). Nothing is cached:
    a reload reads what was saved."""

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _mem(self):
        return urllib.parse.urlsplit(self.path).path

    def do_GET(self):
        p = self._mem()
        if p in MEM:
            body = MEM[p].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_PUT(self):
        p = self._mem()
        n = int(self.headers.get("Content-Length") or 0)
        text = self.rfile.read(n).decode("utf-8")
        if p not in MEM:
            self.send_response(404)
            self.end_headers()
            return
        MEM[p] = text
        PUTS.append((p, text))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def reset_self():
    MEM[SELF] = (FIX / "self.base").read_text(encoding="utf-8")
    PUTS.clear()


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "(n) => new Promise((r) => { let k = n; const f = () => (--k > 0 ? requestAnimationFrame(f) : setTimeout(r, 40)); requestAnimationFrame(f); })"

# joint samples on the wall clock (t in Unix seconds), into a dashboard's live `samples`, looked up on every push (a
# reload makes a new dataset): `from` seconds of history first (a backfill), then every 30 ms the time since the last push
FEEDER = """() => {
  if (window.startFeed) return;
  // [swing, phase, offset]: the three small joints apart on y (no line covers another), base 100 times wider (make_fixture.py's)
  const amp = { shoulder: [1, 0, 8], elbow: [0.8, 1.1, 0], wrist: [0.6, 2.3, -8], base: [100, 0.5, 0] };
  const rowsBetween = (a, b) => { const rows = []; for (let t = a + 0.02; t <= b + 1e-9; t += 0.02) for (const [j, [s, ph, off]] of Object.entries(amp)) rows.push({ t, joint: j, position: off + s * Math.sin(t * 1.3 + ph) }); return rows; };
  window.feeds = {};
  window.startFeed = (id, from) => {
    const d = document.getElementById(id);
    let last = from;
    const push = () => { const now = Date.now() / 1000; const ds = d.datasets && d.datasets.samples; if (!ds || !ds.append || now <= last) return; ds.append(rowsBetween(last, now)); last = now; };
    push();
    window.feeds[id] = setInterval(push, 30);
  };
  window.stopFeed = (id) => { clearInterval(window.feeds[id]); delete window.feeds[id]; };
}"""

# the host: dashboards() on <html> lists cfg.list; the listener keeps what it is handed and answers through respondWith
HOST = """(cfg) => {
  window.hostCfg = cfg;
  document.documentElement.dashboards = async () => window.hostCfg.list;
  if (window.hostWired) return;
  window.hostWired = true;
  window.added = [];
  document.addEventListener('data-add-to-dashboard', (e) => {
    const c = window.hostCfg;
    const views = e.target.closest && e.target.closest('data-dashboard');
    window.added.push({ dashboard: e.detail.dashboard, panel: e.detail.panel, text: e.detail.text, connected: e.target.isConnected,
      target: e.target.id || null, current: !!(views && e.target === views.querySelector(`.dd-panel[data-panel="${e.target.dashboardPanel && e.target.dashboardPanel.key}"] data-views`)) });
    if (c.answer === 'save') e.detail.respondWith(window.hostSave(e.detail));
    else e.detail.respondWith(new Promise((yes) => setTimeout(() => yes(c.answer), 30)));
  });
}"""

# uPlot: canvas pixels near each series' own stroke colour inside the plot box, its scales and its series' show flags
UPLOT = """(sel) => {
  const el = document.querySelector(sel + ' .dv-view-plot');
  const u = el && el.uplot;
  if (!u) return null;
  const hex = (c) => { const m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(c); if (m) return [+m[1], +m[2], +m[3]];
    const h = c.replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); };
  const series = u.series.slice(1).map((s) => ({ label: s.label, show: s.show, rgb: hex(typeof s.stroke === 'function' ? s.stroke(u, 1) : s.stroke) }));
  const b = u.bbox, img = u.ctx.getImageData(b.left, b.top, b.width, b.height).data;
  const n = Object.fromEntries(series.map((s) => [s.label, 0]));
  for (let i = 0; i < img.length; i += 4) {
    if (img[i + 3] < 64) continue;   // un-premultiplied: an antialiased edge keeps its colour (the live plot does not snap lines to pixels)
    for (const s of series) { const w = s.rgb; if (Math.abs(img[i] - w[0]) + Math.abs(img[i + 1] - w[1]) + Math.abs(img[i + 2] - w[2]) < 24) n[s.label]++; }
  }
  const xs = u.data[0] || [];
  return { n, show: Object.fromEntries(series.map((s) => [s.label, s.show])), rgb: Object.fromEntries(series.map((s) => [s.label, s.rgb.join(',')])),
           y: [u.scales.y.min, u.scales.y.max], x: [u.scales.x.min, u.scales.x.max], points: xs.length, lastX: xs.length ? xs[xs.length - 1] : null };
}"""

KEYS = """(sel) => [...document.querySelectorAll(sel + ' .dv-view-plot .dv-legend-key')].map((b) => { const cs = getComputedStyle(b);
  return { name: b.dataset.legendSeries, tag: b.tagName, type: b.type, pressed: b.getAttribute('aria-pressed'),
           strike: cs.textDecorationLine, opacity: Number(cs.opacity) }; })"""
RESET = """(sel) => { const r = document.querySelector(sel + ' .dv-view-plot .dv-legend-reset'); if (!r) return null; const b = r.getBoundingClientRect();
  return { hidden: r.hidden, w: b.width, h: b.height, text: r.textContent.trim() }; }"""
STATUS = """(sel) => (document.querySelector(sel + ' data-views .dv-status') || {}).textContent || ''"""


def settle(page, n=3):
    page.evaluate(SETTLE, n)


def until(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def new_page(browser, base, *, width=1280, dark=False, hash_=""):
    mobile = width < 500
    context = browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844}, color_scheme="dark" if dark else "light",
                                  device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(base + PAGE + hash_)
    page.wait_for_function("window.kitReady === true", timeout=WAIT)
    page.evaluate(FEEDER)
    return page


def add_live(page, id_, src, *, no_url=True, back=6.0, from_t=None):
    """A live <data-dashboard> over `src`, fed on the wall clock from `back` seconds ago (or from `from_t`)."""
    page.evaluate("""([id, src, noUrl]) => new Promise((done) => { const d = document.createElement('data-dashboard'); d.id = id;
      if (noUrl) d.setAttribute('no-url', ''); d.addEventListener('data-dashboard-live', () => done(), { once: true });
      d.setAttribute('src', src); document.body.append(d); })""", [id_, src, no_url])
    page.evaluate("([id, from]) => startFeed(id, from)", [id_, from_t if from_t is not None else page.evaluate("() => Date.now() / 1000") - back])
    return until(page, """(id) => { const d = document.getElementById(id); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length === d.dash.panels.filter((p) => p.views.length).length
        && els.every((e) => e.dataset.view || (e.view && e.view.type === 'playback')) && [...d.querySelectorAll('.dv-view-plot')].every((v) => v.uplot && Number(v.dataset.points) > 0); }""", id_)


def add_dash(page, id_, src):
    page.evaluate("""([id, src]) => { const d = document.createElement('data-dashboard'); d.id = id; d.setAttribute('no-url', '');
      d.setAttribute('src', src); document.body.append(d); }""", [id_, src])
    return until(page, """(id) => { const d = document.getElementById(id); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length === d.dash.panels.filter((p) => p.views.length).length
        && els.every((e) => e.dataset.view && e.model); }""", id_)


def panel_sel(dash, key):
    return f"#{dash} .dd-panel[data-panel='{key}']"


def key_btn(page, sel, name):
    return page.locator(f"{sel} .dv-view-plot .dv-legend-key[data-legend-series={json.dumps(name)}]")


def press(page, sel, name, how="click"):
    """Press a legend entry; False (fast, no 30 s wait) when the entry is not a button there."""
    b = key_btn(page, sel, name)
    if b.count() != 1:
        return False
    if how == "click":
        b.click(timeout=5000)
    elif how == "alt":
        b.click(modifiers=["Alt"], timeout=5000)
    elif how == "dbl":
        b.dblclick(timeout=5000)
    return True


def drawn(m):
    """{series: drawn?}: a shown series with its own colour on the canvas (each joint has its own palette slot)."""
    if not m:
        return {}
    return {k: bool(m["show"][k]) and v > 3 for k, v in m["n"].items()}


def only(m, names):
    """Exactly `names` are drawn: shown and on the canvas; the rest neither."""
    d = drawn(m)
    return bool(d) and all(d.get(k) for k in names) and all((not d.get(k)) and m["n"][k] <= 3 and m["show"][k] is False for k in d if k not in names)


def span(y):
    return (y[1] - y[0]) if y and y[0] is not None and y[1] is not None else None


def hash_params(page):
    return urllib.parse.parse_qs(page.evaluate("location.hash.slice(1)"), keep_blank_values=True)


def hidden_in_url(page, param):
    v = hash_params(page).get(param)
    if not v:
        return []
    return [urllib.parse.unquote(x) for x in v[0].split(",") if x != ""]


def write_base(text, tag):
    """A text the host was handed, as a file beside the fixture (deleted at the end): its src."""
    path = FIX / f"_dx-{os.getpid()}-{tag}.base"
    path.write_text(text, encoding="utf-8")
    return path.name


def picker_box(page):
    return page.evaluate("""() => { const p = document.querySelector('.dv-addpick'); if (!p || !p.isConnected) return null; const r = p.getBoundingClientRect();
      const s = p.querySelector('.dv-addpick-status'); const bg = getComputedStyle(p).backgroundColor.match(/[\\d.]+/g).map(Number);
      return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight,
               state: s ? s.dataset.state : null, text: s ? s.textContent.trim() : null, lum: (0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]) / 255,
               focusInside: !!(document.activeElement && document.activeElement.closest && document.activeElement.closest('.dv-addpick')),
               inViews: p.parentElement && p.parentElement.tagName === 'DATA-VIEWS' ? p.parentElement.id : null, count: document.querySelectorAll('.dv-addpick').length }; }""")


def open_panel_menu(page, sel):
    page.locator(sel).hover()
    page.locator(f"{sel} .dd-panel-menu").first.click()
    item = page.locator(f"{sel} .dd-panel-pop [data-add-dashboard]").first
    item.wait_for(state="visible", timeout=WAIT)
    return item


def shot(page, name, sel=None):
    try:
        settle(page, 2)
        if sel:
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"))
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


def parse(text):
    return data_ui_base.loads(text)


def last_panel(doc):
    p = doc["layout"]["panels"][-1]
    name = p.get("view") or (p.get("views") or [None])[0]
    return p, next((v for v in doc.get("views") or [] if v.get("name") == name), None)


# ------------------------------------------------------------------------------------------------- 1. the live plot's legend
def live_legend(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [{"id": "live-target", "title": "Live target", "url": URL + "live-target.base"}], "answer": {"ok": True}})
    ok = add_live(page, "live", "live.base", no_url=False)
    sel = panel_sel("live", "joints")
    check("legend: the live dashboard draws its Joints plot over the pushed rows, following", ok and page.evaluate("() => document.getElementById('live').clock.following"))
    settle(page)
    keys = page.evaluate(KEYS, sel)
    check("legend: the live plot's legend is one <button type=button aria-pressed=true> per series (CONTRACT §31)",
          sorted(k["name"] for k in keys) == JOINTS and all(k["tag"] == "BUTTON" and k["type"] == "button" and k["pressed"] == "true" for k in keys),
          keys or page.evaluate("(sel) => (document.querySelector(sel + ' .dv-plot-legend') || {}).outerHTML", sel))
    reset = page.evaluate(RESET, sel)
    check("legend: no Reset while every series shows", reset is not None and reset["hidden"] and reset["w"] == 0, reset)
    m0 = page.evaluate(UPLOT, sel)
    check("legend: every series draws before any click (uPlot shows it, its colour is on the canvas)", m0 is not None and all(drawn(m0).get(n) for n in JOINTS), m0 and m0["n"])
    status0 = page.evaluate(STATUS, sel)

    # a click hides the outlier, while rows keep arriving
    pressed = press(page, sel, OUTLIER)
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check(f"legend: a click on {OUTLIER!r} hides exactly it (uPlot's show false, none of its colour on the canvas); the rest draw",
          pressed and only(m, [n for n in JOINTS if n != OUTLIER]), {"pressed": pressed, "n": m and m["n"], "show": m and m["show"]})
    k = {x["name"]: x for x in page.evaluate(KEYS, sel)}
    check("legend: the hidden entry reads aria-pressed=false, greyed and struck through; the others stay pressed",
          OUTLIER in k and k[OUTLIER]["pressed"] == "false" and "line-through" in k[OUTLIER]["strike"] and k[OUTLIER]["opacity"] < 0.9
          and all(k[n]["pressed"] == "true" for n in JOINTS if n != OUTLIER and n in k), k.get(OUTLIER))
    reset = page.evaluate(RESET, sel)
    check("legend: Reset appears beside the legend while a series is hidden", bool(reset) and not reset["hidden"] and reset["w"] > 0 and reset["text"] == "Reset", reset)
    check("legend: the hidden set is in the dashboard's URL (l.joints=base)", hidden_in_url(page, "l.joints") == [OUTLIER], page.evaluate("location.hash"))
    x1 = m and m["x"]
    page.wait_for_timeout(1200)
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("legend: hidden it stays hidden through live frames (1.2 s of rows later, the window moved on)",
          pressed and only(m, [n for n in JOINTS if n != OUTLIER]) and x1 is not None and m["x"][1] > x1[1] + 0.5,
          {"n": m and m["n"], "show": m and m["show"], "x before": x1, "x after": m and m["x"]})
    check("legend: the status line is the data's, unchanged by hiding", page.evaluate(STATUS, sel).replace(",", "") .split(" rows")[-1] == status0.replace(",", "").split(" rows")[-1],
          [status0, page.evaluate(STATUS, sel)])

    # the rows stop: y and x can be compared exactly
    page.evaluate("() => stopFeed('live')")
    settle(page, 4)
    hid = page.evaluate(UPLOT, sel)
    press(page, sel, OUTLIER)
    settle(page)
    full = page.evaluate(UPLOT, sel)
    check(f"legend: a second click draws {OUTLIER!r} again (every series drawn)", full is not None and all(drawn(full).get(n) for n in JOINTS), full and full["n"])
    check("legend: y rescales to the series shown (hiding the outlier shrinks y more than four times), x stays put",
          hid is not None and full is not None and span(hid["y"]) is not None and span(full["y"]) is not None and span(hid["y"]) * 4 < span(full["y"]) and hid["x"] == full["x"],
          {"y hidden": hid and hid["y"], "y full": full and full["y"], "x hidden": hid and hid["x"], "x full": full and full["x"]})
    check("legend: all shown again, the URL has no l.joints", hidden_in_url(page, "l.joints") == [], page.evaluate("location.hash"))

    # a double-click isolates; again shows all
    pressed = press(page, sel, "shoulder", "dbl")
    settle(page)
    m = page.evaluate(UPLOT, sel)
    keys = page.evaluate(KEYS, sel)
    check("legend: a double-click on 'shoulder' shows only it (net isolate, no toggle left behind)",
          pressed and only(m, ["shoulder"]) and [x["pressed"] for x in keys] == ["true" if x["name"] == "shoulder" else "false" for x in keys],
          {"n": m and m["n"], "pressed": [x["pressed"] for x in keys]})
    press(page, sel, "shoulder", "dbl")
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("legend: a double-click on the isolated one shows every series again, y the full one",
          pressed and only(m, JOINTS) and m["y"] == full["y"], {"n": m and m["n"], "y": m and m["y"], "full": full and full["y"]})

    # Alt + click isolates; again shows all
    pressed = press(page, sel, "elbow", "alt")
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("legend: Alt + click on 'elbow' shows only it", pressed and only(m, ["elbow"]), m and m["n"])
    press(page, sel, "elbow", "alt")
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("legend: Alt + click on the isolated one shows every series again", pressed and only(m, JOINTS), m and m["n"])

    # Reset
    press(page, sel, "wrist")
    press(page, sel, OUTLIER)
    settle(page)
    clicked = page.locator(f"{sel} .dv-view-plot .dv-legend-reset")
    if clicked.count() == 1 and clicked.is_visible():
        clicked.click(timeout=5000)
    settle(page)
    m = page.evaluate(UPLOT, sel)
    reset = page.evaluate(RESET, sel)
    check("legend: Reset shows every series and the full y again, and hides itself",
          clicked.count() == 1 and only(m, JOINTS) and m["y"] == full["y"] and bool(reset) and reset["hidden"], {"n": m and m["n"], "y": m and m["y"], "reset": reset})

    # the keyboard: each entry is a native button
    first = key_btn(page, sel, "elbow")
    if first.count() == 1:
        first.focus()
        page.keyboard.press("Enter")
        settle(page)
        a = page.evaluate(UPLOT, sel)
        page.keyboard.press("Space")
        settle(page)
        b = page.evaluate(UPLOT, sel)
        check("legend: Enter on a focused entry hides its series and Space shows it again",
              a is not None and a["show"]["elbow"] is False and not drawn(a)["elbow"] and b is not None and drawn(b)["elbow"], {"after Enter": a and a["show"], "after Space": b and b["show"]})
    else:
        check("legend: Enter on a focused entry hides its series and Space shows it again", False, "no legend button")
    shot(page, "legend-live-light-1280", sel)

    # the item menu: a right-click or Shift+F10 on a series
    with guard("legend: the series' item menu"):
        b = key_btn(page, sel, "elbow")
        menu = None
        if b.count() == 1:
            b.click(button="right")
            ok = until(page, "() => document.querySelector('.dv-itemmenu')", timeout=5000)
            menu = page.evaluate("() => [...document.querySelectorAll('.dv-itemmenu [role=menuitem]')].map((x) => x.textContent.trim())") if ok else None
        check("legend: a right-click on a series opens its item menu: Show only “elbow” and Add “elbow” to dashboard…",
              menu == ["Show only “elbow”", "Add “elbow” to dashboard…"], menu)
        page.keyboard.press("Escape")
        until(page, "() => !document.querySelector('.dv-itemmenu')", timeout=5000)
        menu = None
        s = key_btn(page, sel, "shoulder")
        if s.count() == 1:
            s.focus()
            page.keyboard.press("Shift+F10")
            ok = until(page, "() => document.querySelector('.dv-itemmenu')", timeout=5000)
            menu = page.evaluate("() => [...document.querySelectorAll('.dv-itemmenu [role=menuitem]')].map((x) => x.textContent.trim())") if ok else None
        check("legend: Shift+F10 on a focused series opens the same menu", menu == ["Show only “shoulder”", "Add “shoulder” to dashboard…"], menu)
        only_item = page.locator(".dv-itemmenu [data-legend-only]")
        if only_item.count() == 1:
            only_item.click()
        settle(page)
        m = page.evaluate(UPLOT, sel)
        check("legend: its Show only shows that series alone", only_item.count() <= 1 and only(m, ["shoulder"]), m and m["n"])
        if key_btn(page, sel, "shoulder").count() == 1:
            press(page, sel, "shoulder", "alt")
        settle(page)

    # Add “elbow” to dashboard…: the plot with every other series hidden
    with guard("legend: Add a series to a dashboard"):
        b = key_btn(page, sel, "elbow")
        got = None
        if b.count() == 1:
            b.click(button="right")
            item = page.locator(".dv-itemmenu [data-add-dashboard]")
            item.wait_for(state="visible", timeout=5000)
            item.click()
            picker = page.locator(".dv-addpick").first
            picker.wait_for(state="visible", timeout=WAIT)
            btn = picker.locator("[data-dashboard-id='live-target']")
            btn.wait_for(state="visible", timeout=WAIT)
            btn.click()
            until(page, "() => (window.added || []).length > 0")
            got = page.evaluate("() => window.added[window.added.length - 1]")
        panel = got and got["panel"]
        view = panel and panel["view"]
        check("legend: Add “elbow” to dashboard… hands the host the plot with every other series hidden (kind series)",
              bool(panel) and panel["kind"] == "series" and view["type"] == "plot" and sorted(view.get("hiddenSeries") or []) == ["base", "shoulder", "wrist"]
              and panel["title"] == "Joints · elbow" and panel["dataset"]["data"] == URL + "samples.json",
              panel and {"kind": panel["kind"], "title": panel["title"], "hidden": view.get("hiddenSeries"), "data": panel["dataset"]["data"]})
        page.keyboard.press("Escape")
        if got and got["text"]:
            src = write_base(got["text"], "series")
            ok = add_live(page, "series-out", src)
            key = page.evaluate("() => { const d = document.getElementById('series-out'); return d.dash.panels[d.dash.panels.length - 1].key; }")
            settle(page, 4)
            m = page.evaluate(UPLOT, panel_sel("series-out", key))
            check("legend: loaded where it was added, the series panel draws elbow alone (the others hidden, still in its legend)",
                  ok and only(m, ["elbow"]) and sorted(x["name"] for x in page.evaluate(KEYS, panel_sel("series-out", key))) == JOINTS,
                  {"n": m and m["n"], "show": m and m["show"]})
        else:
            check("legend: loaded where it was added, the series panel draws elbow alone (the others hidden, still in its legend)", False, "nothing was added")
    for id_ in ("live", "series-out"):
        page.evaluate("(id) => window.feeds && window.feeds[id] && stopFeed(id)", id_)
    check("legend: no page error", not page.errors, page.errors[:3])
    page.context.close()

    # the URL is read back: a link with l.joints=base opens with base hidden
    page = new_page(browser, base, hash_="#t=live&l.joints=base")
    ok = add_live(page, "live", "live.base", no_url=False)
    settle(page, 4)
    m = page.evaluate(UPLOT, sel)
    k = {x["name"]: x for x in page.evaluate(KEYS, sel)}
    check("legend: a link with l.joints=base opens with base hidden (show false, not drawn, its entry not pressed)",
          ok and only(m, [n for n in JOINTS if n != OUTLIER]) and OUTLIER in k and k[OUTLIER]["pressed"] == "false", {"n": m and m["n"], "keys": list(k.values())})
    page.evaluate("() => stopFeed('live')")
    check("legend: no page error on the link", not page.errors, page.errors[:3])
    page.context.close()


def plain_plot(browser, base):
    """The plot card over a recording in a plain <data-views>: the same legend, its set in the URL as l=."""
    page = new_page(browser, base)
    page.evaluate("""() => { const v = document.createElement('data-views'); v.id = 'rec'; v.setAttribute('src', 'recorded.base'); document.body.append(v); }""")
    ok = until(page, "() => { const v = document.querySelector('#rec .dv-view-plot'); return v && v.uplot && Number(v.dataset.points) > 0; }")
    sel = "#rec"
    settle(page)
    keys = page.evaluate(KEYS, sel)
    check("recording: the plot card's legend in a plain <data-views> is one button per series", ok and sorted(k["name"] for k in keys) == JOINTS and all(k["tag"] == "BUTTON" for k in keys), keys)
    full = page.evaluate(UPLOT, sel)
    pressed = press(page, sel, OUTLIER)
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("recording: a click hides the outlier and y rescales to the rest (four times smaller or more); x stays",
          pressed and only(m, [n for n in JOINTS if n != OUTLIER]) and span(m["y"]) * 4 < span(full["y"]) and m["x"] == full["x"],
          {"n": m and m["n"], "y": m and m["y"], "full y": full and full["y"]})
    check("recording: the hidden set is in the URL as l=base", hidden_in_url(page, "l") == [OUTLIER], page.evaluate("location.hash"))
    check("recording: no page error", not page.errors, page.errors[:3])
    page.context.close()
    page = new_page(browser, base, hash_="#l=base")
    page.evaluate("""() => { const v = document.createElement('data-views'); v.id = 'rec'; v.setAttribute('src', 'recorded.base'); document.body.append(v); }""")
    ok = until(page, "() => { const v = document.querySelector('#rec .dv-view-plot'); return v && v.uplot && Number(v.dataset.points) > 0; }")
    settle(page)
    m = page.evaluate(UPLOT, sel)
    check("recording: a link with l=base opens with base hidden", ok and only(m, [n for n in JOINTS if n != OUTLIER]), m and m["show"])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 2. the declared file
BOARDS = """async () => {
  const dir = new URL('boards/', location.href).href;
  // RobotDx's /dx/: one dataset object per kind for every board; its url is whichever binding made it first (board A's)
  const first = new URL('../config.json?path=a', dir).href;
  const shared = { ...(await kit.loadDataset(first)), url: first };
  for (const id of ['board-a', 'board-b']) {
    const text = await (await fetch(dir + id + '.base', { cache: 'no-store' })).text();
    const d = document.createElement('data-dashboard');
    d.id = id;
    d.setAttribute('no-url', '');
    d.baseUrl = dir;   // where the host's .base files live (CONTRACT §34: the base a host that loads a .base itself gives)
    document.body.append(d);
    d.baseText = text;
    d.load(kit.parseBase(text), { config: shared });
  }
}"""


def declared_file(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [{"id": "board-a", "title": "Board A", "url": URL + "boards/board-a.base"}], "answer": {"ok": True}})
    page.evaluate(BOARDS)
    ok = until(page, "() => ['board-a', 'board-b'].every((id) => { const v = document.querySelector(`#${id} .dd-panel data-views`); return v && v.model && v.dataset.view; })")
    specs = page.evaluate("""() => Object.fromEntries(['board-a', 'board-b'].map((id) => { const v = document.querySelector(`#${id} .dd-panel data-views`);
      const shared = document.getElementById(id).datasets.config === document.getElementById('board-a').datasets.config;
      try { const s = v.panelSpec(); return [id, { data: s.dataset.data, name: s.dataset.name, shared }]; }
      catch (e) { return [id, { error: e.message, shared }]; } }))""") if ok else None
    check("declared: the host draws boards A and B with one shared config dataset (its url board A's file)", ok and specs and specs["board-b"].get("shared") is True, specs)
    check("declared: board A's panel names board A's file (config.json?path=a)", bool(specs) and specs["board-a"].get("data") == URL + "config.json?path=a", specs and specs["board-a"])
    check("declared: board B's panel names the file board B declares (config.json?path=b), not the shared dataset's url",
          bool(specs) and specs["board-b"].get("data") == URL + "config.json?path=b", specs and specs["board-b"])
    check("declared: both name the dataset as their dashboards do (config)", bool(specs) and specs["board-a"].get("name") == "config" and specs["board-b"].get("name") == "config", specs)
    with guard("declared: an add from board B"):
        open_panel_menu(page, panel_sel("board-b", "settings")).click()
        picker = page.locator(".dv-addpick").first
        picker.wait_for(state="visible", timeout=WAIT)
        btn = picker.locator("[data-dashboard-id='board-a']")
        btn.wait_for(state="visible", timeout=WAIT)
        btn.click()
        until(page, "() => (window.added || []).length > 0")
        got = page.evaluate("() => window.added[window.added.length - 1]")
        check("declared: the host's event carries board B's file as the panel's data", bool(got) and got["panel"]["dataset"]["data"] == URL + "config.json?path=b",
              got and got["panel"]["dataset"])
        doc = parse(got["text"]) if got and got["text"] else {}
        ds = {k: (v if isinstance(v, str) else (v or {}).get("data")) for k, v in (doc.get("datasets") or {}).items()}
        p, view = last_panel(doc) if doc else (None, None)
        check("declared: appended to board A, the panel reads board B's file (a dataset ../config.json?path=b of its own; A's config kept)",
              ds.get("config") == "../config.json?path=a" and view is not None and ds.get(view.get("from")) == "../config.json?path=b", {"datasets": ds, "view from": view and view.get("from")})
        page.keyboard.press("Escape")
    ok = add_dash(page, "src-board", "src-board.base")
    spec = page.evaluate("() => { try { return document.querySelector('#src-board .dd-panel data-views').panelSpec().dataset; } catch (e) { return { error: e.message }; } }") if ok else None
    check("declared: a board drawn from its src names its declared file as before (config.json?path=a)", bool(spec) and spec.get("data") == URL + "config.json?path=a", spec)
    check("declared: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 3 and 5. At this moment, live
def at_this_moment(browser, base):
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [{"id": "live-target", "title": "Live target", "url": URL + "live-target.base"}], "answer": {"ok": True}})
    ok = add_live(page, "live", "live.base")
    sel = panel_sel("live", "joints")
    settle(page, 4)
    before = page.evaluate("() => ({ t: document.getElementById('live').clock.t, following: document.getElementById('live').clock.following })")
    check("moment: the source dashboard follows live data whose time is an epoch", ok and before["following"] and before["t"] > 1e9, before)
    open_panel_menu(page, sel).click()
    picker = page.locator(".dv-addpick").first
    picker.wait_for(state="visible", timeout=WAIT)
    after_open = page.evaluate("() => document.getElementById('live').clock.t")
    label = page.evaluate("() => { const s = document.querySelector('.dv-addpick .dv-addpick-t'); return s ? { text: s.textContent.trim(), title: s.getAttribute('title') || '' } : null; }")
    shot(page, "moment-picker-light-1280")
    has_moment = picker.locator("input[name='at-moment']").count() == 1
    if has_moment:
        picker.locator("input[name='at-moment']").check()
    btn = picker.locator("[data-dashboard-id='live-target']")
    btn.wait_for(state="visible", timeout=WAIT)
    btn.click()
    until(page, "() => (window.added || []).length > 0 && document.querySelector('.dv-addpick-status[data-state=added]')")
    got = page.evaluate("() => (window.added || []).slice(-1)[0] || null")
    saved = got and got["panel"].get("t")
    check("moment: \"At this moment\" on the following clock saves its t, to the millisecond, as the panel's t",
          has_moment and isinstance(saved, (int, float)) and before["t"] - 0.0006 <= saved <= after_open + 0.0006 and abs(saved * 1000 - round(saved * 1000)) < 1e-3,
          {"saved": saved, "clock before": before["t"], "clock at open": after_open})
    fmt = page.evaluate("(t) => [kit.fmtTime(t), String(t)]", saved) if isinstance(saved, (int, float)) else [None, None]
    check("moment (ask 5): the picker writes the moment as the playback bar writes t (\"t = \" + the kit's fmtTime), a wall-clock time",
          bool(label) and label["text"] == f"t = {fmt[0]}" and re.fullmatch(r"t = \d\d:\d\d:\d\d\.\d\d", label["text"] or "") is not None, {"label": label, "fmtTime": fmt[0]})
    check("moment (ask 5): the picker's moment never shows the raw Unix seconds; they stay one step away, in its title",
          bool(label) and str(int(saved or 0)) not in label["text"] and fmt[1] is not None and fmt[1] in label["title"], label)
    page.keyboard.press("Escape")
    page.evaluate("() => stopFeed('live')")
    doc = parse(got["text"]) if got and got["text"] else {}
    p, view = last_panel(doc) if doc else (None, None)
    check("moment: appended to the live target, the panel reuses its live samples dataset and stands at t",
          bool(p) and p.get("t") == saved and view is not None and view.get("from") == "samples" and view.get("type") == "plot", {"panel": p, "view": view and view.get("from")})
    if not got or not got["text"] or not isinstance(saved, (int, float)):
        check("moment: the pinned panel could be loaded", False, got)
        page.context.close()
        return
    # the saved text, loaded where the same live data keeps arriving: 8 s before t, and on past it
    src = write_base(got["text"], "pinned")
    ok = add_live(page, "pinned", src, from_t=saved - 8)
    key = page.evaluate("() => { const d = document.getElementById('pinned'); return d.dash.panels[d.dash.panels.length - 1].key; }")
    psel = panel_sel("pinned", key)
    until(page, "(t) => document.getElementById('pinned').clock.t > t + 1", saved)
    settle(page, 4)
    PIN = """([sel, t]) => { const d = document.getElementById('pinned'); const v = document.querySelector(sel + ' data-views'); const c = kit.clockFor(v);
      const pv = v.querySelector('.dv-view-plot'); const u = pv && pv.uplot; const at = document.querySelector(sel + ' .dd-at');
      return { t: c.t, following: c.following, playing: c.playing, own: c !== d.clock, live: v.dataset.live, dashT: d.clock.t, dashFollowing: d.clock.following,
               x: u ? [u.scales.x.min, u.scales.x.max] : null, lastX: u && u.data[0].length ? u.data[0][u.data[0].length - 1] : null, points: u ? u.data[0].length : 0,
               at: at ? at.textContent.trim() : null, atTitle: at ? at.getAttribute('title') || '' : null }; }"""
    m = page.evaluate(PIN, [psel, saved])
    check("moment: the dashboard it was added to follows its live data on past t", ok and m["dashFollowing"] and m["dashT"] > saved + 1, {"dash t - saved": m["dashT"] - saved, "following": m["dashFollowing"]})
    check("moment (ask 3): the pinned panel's views read a clock of their own, paused at t (following false, not playing, t exact)",
          m["own"] and m["following"] is False and m["playing"] is False and m["t"] == saved, {k: m[k] for k in ("own", "following", "playing", "t")} | {"saved": saved})
    check("moment (ask 3): the pinned panel says it is paused (data-live=paused) while the dashboard follows", m["live"] == "paused", m["live"])
    check("moment (ask 3): its plot's window ends at t (x max = t), and nothing after t is drawn",
          m["x"] is not None and abs(m["x"][1] - saved) < 1e-6 and m["points"] > 0 and m["lastX"] <= saved + 1e-6, {"x": m["x"], "lastX": m["lastX"], "saved": saved})
    check("moment (ask 5): the pinned header writes t as the playback bar does (\"at t = \" + fmtTime), never the raw seconds",
          m["at"] == f"at t = {fmt[0]}" and str(int(saved)) not in (m["at"] or ""), {"at": m["at"], "want": f"at t = {fmt[0]}"})
    check("moment (ask 5): the exact instant stays one step away, in the header's title", fmt[1] in (m["atTitle"] or ""), m["atTitle"])
    shot(page, "moment-pinned-light-1280", psel)
    page.wait_for_timeout(1500)
    settle(page)
    m2 = page.evaluate(PIN, [psel, saved])
    check("moment (ask 3): 1.5 s of rows later it still stands at t, its window still ending there",
          m2["following"] is False and m2["t"] == saved and m2["x"] is not None and abs(m2["x"][1] - saved) < 1e-6 and m2["dashT"] > m["dashT"],
          {"t": m2["t"], "x": m2["x"], "dash moved": m2["dashT"] - m["dashT"]})
    # the dashboard drawn again (a host that saved reloads it): the pin holds
    page.evaluate("() => stopFeed('pinned')")
    page.evaluate("() => new Promise((done) => { const d = document.getElementById('pinned'); d.addEventListener('data-dashboard-live', () => done(), { once: true }); d.reload(); })")
    page.evaluate("(t) => startFeed('pinned', t - 8)", saved)
    until(page, "([sel, t]) => { const v = document.querySelector(sel + ' .dv-view-plot'); return v && v.uplot && Number(v.dataset.points) > 0 && document.getElementById('pinned').clock.t > t + 1; }", [psel, saved])
    settle(page, 4)
    m3 = page.evaluate(PIN, [psel, saved])
    check("moment (ask 3): drawn again (reload), the pinned panel still stands at t", m3["following"] is False and m3["t"] == saved and m3["x"] is not None and abs(m3["x"][1] - saved) < 1e-6,
          {"t": m3["t"], "following": m3["following"], "x": m3["x"]})
    page.evaluate("() => stopFeed('pinned')")
    check("moment: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 4. the picker outlives a reload
SAVE = """(mode) => {
  // the host's save: PUT the text, then draw the dashboard again, before or after answering (CONTRACT §34: a host that
  // saved reloads the dashboard it shows); 'load' draws it with load(), as RobotDx's /dx/ does
  window.reloads = 0;
  window.hostSave = (detail) => (async () => {
    await fetch(detail.dashboard.url, { method: 'PUT', body: detail.text });
    const d = document.getElementById('self');
    const redraw = async () => {
      if (mode === 'load') { d.baseText = detail.text; d.load(kit.parseBase(detail.text), d.datasets, { keepState: true }); }
      else await d.reload();
      window.reloads += 1;
    };
    if (mode === 'after') { setTimeout(redraw, 150); return { ok: true, title: 'Self' }; }
    await redraw();
    return { ok: true, title: 'Self' };
  })();
}"""

SELF_LOAD = """async () => {
  const dir = new URL('./', location.href).href;
  const text = await (await fetch(dir + 'self.base', { cache: 'no-store' })).text();
  const config = { ...(await kit.loadDataset(dir + 'config.json')), url: dir + 'config.json' };
  const d = document.createElement('data-dashboard');
  d.id = 'self';
  d.setAttribute('no-url', '');
  d.baseUrl = dir;
  document.body.append(d);
  d.baseText = text;
  d.load(kit.parseBase(text), { config });
}"""


def panels_of(page):
    return page.evaluate("() => { const d = document.getElementById('self'); return d && d.dash ? d.dash.panels.length : 0; }")


def survives(browser, base):
    for mode, how in (("before", "reload() before it answers"), ("after", "reload() after it answered"), ("load", "load() as RobotDx draws it, before it answers")):
        reset_self()
        page = new_page(browser, base)
        page.evaluate(HOST, {"list": [{"id": "self", "title": "Self", "url": SELF}], "answer": "save"})
        page.evaluate(SAVE, mode)
        if mode == "load":
            page.evaluate(SELF_LOAD)
            ok = until(page, "() => { const v = document.querySelector('#self .dd-panel data-views'); return v && v.model && v.dataset.view; }")
        else:
            ok = add_dash(page, "self", SELF)
        sel = panel_sel("self", "settings")
        with guard(f"picker ({how})"):
            open_panel_menu(page, sel).click()
            picker = page.locator(".dv-addpick").first
            picker.wait_for(state="visible", timeout=WAIT)
            btn = picker.locator("[data-dashboard-id='self']")
            btn.wait_for(state="visible", timeout=WAIT)
            settle(page, 2)
            was = picker_box(page)
            btn.click()
            redrawn = until(page, "() => window.reloads >= 1")
            settle(page, 4)
            now = picker_box(page)
            check(f"picker ({how}): the host saved once and drew its dashboard again, one panel more", ok and redrawn and len(PUTS) == 1 and panels_of(page) == 2,
                  {"puts": len(PUTS), "panels": panels_of(page)})
            check(f"picker ({how}): the picker is still on the page after its dashboard was drawn again",
                  now is not None and now["count"] == 1 and now["w"] > 0 and now["h"] > 0, now)
            check(f"picker ({how}): it says \"Added to Self\"", bool(now) and now["state"] == "added" and (now["text"] or "").startswith("Added to Self"), now and {"state": now["state"], "text": now["text"]})
            check(f"picker ({how}): it stayed where it was (within 1 px) and inside the viewport",
                  bool(now) and bool(was) and abs(now["left"] - was["left"]) <= 1 and abs(now["top"] - was["top"]) <= 1 and now["right"] <= now["vw"] and now["bottom"] <= now["vh"] and now["top"] >= 0,
                  {"before": was and [was["left"], was["top"]], "after": now and [now["left"], now["top"]]})
            if mode == "before":
                # a second add from the same picker reaches the host from the panel drawn now
                n0 = page.evaluate("() => window.added.length")
                again = page.locator(".dv-addpick [data-dashboard-id='self']")
                if again.count() == 1:
                    again.click()
                until(page, "() => window.reloads >= 2", timeout=15000)
                settle(page, 4)
                ev = page.evaluate("(n) => window.added.length > n ? window.added[window.added.length - 1] : null", n0)
                now2 = picker_box(page)
                check(f"picker ({how}): a second add from it reaches the host, fired on the panel drawn now",
                      ev is not None and ev["connected"] and ev["current"] and len(PUTS) == 2 and panels_of(page) == 3, {"event": ev and {k: ev[k] for k in ("connected", "current", "target")}, "puts": len(PUTS), "panels": panels_of(page)})
                check(f"picker ({how}): and says \"Added to Self\" again", bool(now2) and now2["state"] == "added" and (now2["text"] or "").startswith("Added to Self"), now2 and now2["text"])
            if mode == "after":
                # from the keyboard: the dashboard's button, Enter; the focus stays in the picker through the redraw
                page.keyboard.press("Escape")
                until(page, "() => !document.querySelector('.dv-addpick')", timeout=5000)
                reloads = page.evaluate("() => window.reloads")
                page.locator(sel).hover()
                page.locator(f"{sel} .dd-panel-menu").first.focus()
                page.keyboard.press("Enter")
                page.locator(f"{sel} .dd-panel-pop [data-add-dashboard]").first.wait_for(state="visible", timeout=WAIT)
                page.keyboard.press("Enter")
                until(page, "() => document.activeElement && document.activeElement.matches && document.activeElement.matches(\".dv-addpick [data-dashboard-id='self']\")", timeout=WAIT)
                page.keyboard.press("Enter")
                until(page, "(n) => window.reloads > n", reloads, timeout=15000)
                settle(page, 4)
                k = picker_box(page)
                check(f"picker ({how}): added from the keyboard, after the redraw the focus is still in the picker, which says Added",
                      bool(k) and k["focusInside"] and k["state"] == "added", k and {"focusInside": k["focusInside"], "state": k["state"]})
            shot(page, f"picker-survives-{mode}")
            page.keyboard.press("Escape")
            gone = until(page, "() => !document.querySelector('.dv-addpick')", timeout=5000)
            check(f"picker ({how}): Escape closes it, and no picker is left on the page", gone)
        check(f"picker ({how}): no page error", not page.errors, page.errors[:3])
        page.context.close()
    # its dashboard leaves the page: the picker goes with it
    reset_self()
    page = new_page(browser, base)
    page.evaluate(HOST, {"list": [{"id": "self", "title": "Self", "url": SELF}], "answer": {"ok": True}})
    ok = add_dash(page, "self", SELF)
    with guard("picker: its dashboard leaves the page"):
        open_panel_menu(page, panel_sel("self", "settings")).click()
        page.locator(".dv-addpick").first.wait_for(state="visible", timeout=WAIT)
        page.evaluate("() => document.getElementById('self').remove()")
        gone = until(page, "() => !document.querySelector('.dv-addpick')", timeout=5000)
        page.wait_for_timeout(1500)
        check("picker: when its dashboard leaves the page the picker goes too, and does not come back", ok and gone and page.evaluate("() => !document.querySelector('.dv-addpick')"))
        page.keyboard.press("Escape")
        check("picker: no page error after it went", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- themes and widths
def looks(browser, base):
    for width, dark in ((1280, False), (1280, True), (390, False), (390, True)):
        tag = f"{width} px, {'dark' if dark else 'light'}"
        name = f"{'dark' if dark else 'light'}-{width}"
        page = new_page(browser, base, width=width, dark=dark)
        page.evaluate(HOST, {"list": [{"id": "live-target", "title": "Live target", "url": URL + "live-target.base"}], "answer": {"ok": True}})
        ok = add_live(page, "live", "live.base")
        sel = panel_sel("live", "joints")
        page.locator(sel).scroll_into_view_if_needed()
        settle(page, 4)
        with guard(f"{tag}: the legend"):
            press(page, sel, OUTLIER)
            settle(page)
            m = page.evaluate("""(sel) => { const panel = document.querySelector(sel).getBoundingClientRect();
              const keys = [...document.querySelectorAll(sel + ' .dv-view-plot .dv-legend-key')].map((b) => { const r = b.getBoundingClientRect(); const cs = getComputedStyle(b);
                return { name: b.dataset.legendSeries, left: r.left, right: r.right, top: r.top, bottom: r.bottom, w: r.width, strike: cs.textDecorationLine, opacity: Number(cs.opacity), pressed: b.getAttribute('aria-pressed') }; });
              const fg = getComputedStyle(document.querySelector(sel + ' .dv-view-plot .dv-legend-key') || document.body).color.match(/[\\d.]+/g).map(Number);
              return { panel: { left: panel.left, right: panel.right, top: panel.top, bottom: panel.bottom }, keys, lum: (0.2126 * fg[0] + 0.7152 * fg[1] + 0.0722 * fg[2]) / 255,
                       scroll: document.scrollingElement.scrollWidth, vw: innerWidth }; }""", sel)
            inside = len(m["keys"]) == 4 and all(k["w"] > 0 and k["left"] >= m["panel"]["left"] - 0.5 and k["right"] <= m["panel"]["right"] + 0.5 and k["top"] >= m["panel"]["top"] - 0.5 and k["bottom"] <= m["panel"]["bottom"] + 0.5 for k in m["keys"])
            check(f"{tag}: the legend's four buttons sit inside their panel and the page never scrolls sideways", ok and inside and m["scroll"] <= m["vw"], m)
            hid = next((k for k in m["keys"] if k["name"] == OUTLIER), None)
            check(f"{tag}: a hidden entry is greyed and struck through, in the theme's text colour (light text on dark, dark on light)",
                  bool(hid) and hid["pressed"] == "false" and "line-through" in hid["strike"] and hid["opacity"] < 0.9 and ((m["lum"] > 0.45) if dark else (m["lum"] < 0.55)), {"entry": hid, "lum": m["lum"]})
            shot(page, f"legend-{name}", sel)
            b = key_btn(page, sel, "elbow")
            menu = None
            if b.count() == 1:
                b.click(button="right")
                if until(page, "() => document.querySelector('.dv-itemmenu')", timeout=5000):
                    menu = page.evaluate("""() => { const p = document.querySelector('.dv-itemmenu'); const r = p.getBoundingClientRect();
                      const bg = getComputedStyle(p).backgroundColor.match(/[\\d.]+/g).map(Number);
                      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, vw: innerWidth, vh: innerHeight, lum: (0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]) / 255 }; }""")
            check(f"{tag}: a series' item menu opens inside the viewport in the theme's colours",
                  bool(menu) and menu["left"] >= 0 and menu["right"] <= menu["vw"] and menu["top"] >= 0 and menu["bottom"] <= menu["vh"] and ((menu["lum"] < 0.3) if dark else (menu["lum"] > 0.7)), menu)
            shot(page, f"itemmenu-{name}")
            add = page.locator(".dv-itemmenu [data-add-dashboard]")
            box = None
            if add.count() == 1:
                add.click()
                if until(page, "() => document.querySelector('.dv-addpick [data-dashboard-id]')", timeout=10000):
                    settle(page)
                    box = picker_box(page)
            check(f"{tag}: Add “elbow” to dashboard… opens the picker inside the viewport in the theme's colours",
                  bool(box) and box["left"] >= 0 and box["right"] <= box["vw"] and box["top"] >= 0 and box["bottom"] <= box["vh"] and ((box["lum"] < 0.3) if dark else (box["lum"] > 0.7)), box)
            shot(page, f"picker-{name}")
            page.keyboard.press("Escape")
        with guard(f"{tag}: the pinned header"):
            # a panel pinned at the live clock's t now, drawn from the target's text with a layout panel's t
            t = page.evaluate("() => Math.round(document.getElementById('live').clock.t * 1000) / 1000")
            text = (FIX / "live-target.base").read_text(encoding="utf-8").replace("    - { view: Latest, w: 12, h: 3 }", f"    - {{ view: Latest, w: 12, h: 3, t: {t} }}")
            src = write_base(text, f"look-{name}")
            add_live(page, "look", src, from_t=t - 8)
            page.locator("#look .dd-panel[data-panel='latest']").scroll_into_view_if_needed()
            settle(page, 3)
            h = page.evaluate("""(t) => { const sec = document.querySelector('#look .dd-panel[data-panel="latest"]'); const at = sec && sec.querySelector('.dd-at');
              if (!at) return null; const r = at.getBoundingClientRect(), p = sec.getBoundingClientRect();
              return { text: at.textContent.trim(), want: 'at t = ' + kit.fmtTime(t), left: r.left, right: r.right, pl: p.left, pr: p.right, scroll: document.scrollingElement.scrollWidth, vw: innerWidth }; }""", t)
            check(f"{tag}: the pinned panel's header says when, as a clock time, inside its panel",
                  bool(h) and h["text"] == h["want"] and h["left"] >= h["pl"] - 0.5 and h["right"] <= h["pr"] + 0.5 and h["scroll"] <= h["vw"], h)
            shot(page, f"pinned-{name}", "#look .dd-panel[data-panel='latest']")
        for id_ in ("live", "look"):
            page.evaluate("(id) => window.feeds && window.feeds[id] && stopFeed(id)", id_)
        check(f"{tag}: no page error", not page.errors, page.errors[:3])
        page.context.close()


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists() or not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit is not built: npm --prefix ~/data-ui run build")
        return 1
    reset_self()
    port = free_port()
    server = Server(("127.0.0.1", port), functools.partial(Handler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for name, fn in (("1. the live plot's legend", live_legend), ("1. the plot over a recording", plain_plot), ("2. the declared file", declared_file),
                                 ("3, 5. At this moment on live data", at_this_moment), ("4. the picker outlives a reload", survives), ("themes and widths", looks)):
                    with guard(name):
                        fn(browser, base)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        for stale in FIX.glob(f"_dx-{os.getpid()}-*.base"):
            stale.unlink(missing_ok=True)
    (OUT / "dx-asks-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} dx-asks checks pass; screenshots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
