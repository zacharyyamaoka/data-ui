"""RobotDx's second round of asks of data-ui (RobotDx PEP 0001 §18.4, found drawing each stock diagnostic in its view;
docs/CONTRACT.md §17, §26, §35), measured in headless Chromium on the built kit. Written red, before the code; never
edited after.

    ~/psu-atlas/.venv/bin/python tests/browser/dx_asks_2_checks.py [OUT_DIR]     # after npm run build

The fixture is tests/browser/fixtures/dx_asks_2/ (make_fixture.py writes its data; the page plays the host and pushes the
rows, t in Unix seconds from T0):
  1. Live plot limits (live.base): a `plot` on a live dataset draws §35's `limits: {warn, error}` from the readings it
     holds as of t, read per series from properties (board_temp's warn_hi steps from 60 to 65 at T0 + 20 s; supply_v
     has both sides) and as numbers (one rule shared by both series): `plotView.guides` equals an oracle computed here
     from the rows in the plot's window, each limit's dashed line is drawn on the canvas at the y of its value on the
     plot's own scale within 1 px, its zones are there, y takes every limit in, a hidden series takes its limits away,
     and paused at earlier t's the limits rewind with the clock (60 before the step, the step line across it, 65 after).
  2. Roll-up as of t (rollup.base): §17's roll-up (Max of rank) over live keyed gate rows, onto a tree from a file and
     onto a live tree whose station C moves at T0 + 25 s: each node's worst gate equals an oracle over the gates' newest
     versions at t (and the tree at t), following and paused at four earlier t's, and back to live.
  3. Empty peek sections (peek.base): a section with no field value and no row in its view is not drawn (the plain
     check: Level and Notes only, Notes because its note says why it has no value); a stock diagnostic keeps all five,
     its embedded table its three rows; a section with only its view's rows stays. In the live dashboard's drill peek and
     in a plain <data-views> over the files.
  4. A unit on a typed number column (live.base, readings.json): `reading` is typed number and its cells are
     {value, unit}: on live data the KPI cards, the inline-unit table and the peek show each cell's unit, and the two
     plots of it draw its numbers (an append and a keyed dataset); on the file, the inline-unit table shows it too.
Serves the repo root on a free 127.0.0.1 port (its own server), stops it when done, writes OUT_DIR/dx-asks-2-checks.json
(default reports/media/dx-asks-2) with the screenshots, and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import math
import pathlib
import socket
import socketserver
import sys
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "dx-asks-2"
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / "tests" / "browser" / "fixtures" / "dx_asks_2"
URL = "/tests/browser/fixtures/dx_asks_2/"
PAGE = URL + "page.html"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
T0 = 1792631000.0
BOUNDS = ["warn_lo", "warn_hi", "error_lo", "error_hi"]
checks: list[dict] = []

sys.path.insert(0, str(ROOT / "packages" / "core" / "python"))
import data_ui_base  # noqa: E402  the stdlib .base reader, the Python twin of base.js


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:500]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    """A section that cannot run (nothing drawn to measure) is one failing check in its own words, not a crash."""
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def view_of(base_name, view_name):
    base = data_ui_base.loads((FIX / base_name).read_text(encoding="utf-8"))
    return next(v for v in base["views"] if v["name"] == view_name)


def empty(v):
    return v is None or v == "" or v == []


def cellv(v):
    return v.get("value") if isinstance(v, dict) and "value" in v else v


# ------------------------------------------------------------------------------------------------- the server
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------------------------------------- page helpers
SETTLE = "(n) => new Promise((r) => { let k = n; const f = () => (--k > 0 ? requestAnimationFrame(f) : setTimeout(r, 60)); requestAnimationFrame(f); })"

# the panel section whose <data-views> shows the view `name` (a dashboard's panel keys are its own)
PANEL = """([dash, name]) => { const s = [...document.querySelectorAll(`#${dash} .dd-panel[data-panel]`)].find((x) => { const e = x.querySelector(':scope > data-views'); return e && e.view && e.view.name === name; });
  return s ? s.dataset.panel : null; }"""

# a plot's state: its guides, its scales, the clock's t, its tone colours
PLOT = """(sel) => { const el = document.querySelector(sel + ' .dv-view-plot'); const u = el && el.uplot, v = el && el.plotView;
  if (!u || !v) return null;
  return { guides: JSON.parse(JSON.stringify(v.guides || [])), x: [u.scales.x.min, u.scales.x.max], y: [u.scales.y.min, u.scales.y.max],
           t: v.input && v.input.live ? v.input.live.t : null, rows: v.input ? (v.input.rows || []).length : null, points: Number(el.dataset.points),
           tone: (v.input && v.input.tokens && v.input.tokens.tone) || null, dpr: devicePixelRatio,
           data: u.data.map((a) => Array.from(a || [])) }; }"""

# where a horizontal limit line is drawn: the alpha-weighted mean row of the canvas pixels in the limit's tone, within
# 6 canvas px of where the plot's own y scale puts the value, over the x span [xa, xb] (its label's end left out).
# WHY the tone colour and an alpha floor: the line is drawn at 0.95 in its status tone; the zones under it are 0.09 to
# 0.11 (left out by the floor), the series lines are other colours and far from the limits in this fixture
LINE_Y = """([sel, v, xa, xb, tone]) => { const el = document.querySelector(sel + ' .dv-view-plot'); const u = el && el.uplot, pv = el && el.plotView;
  if (!u || !pv) return null;
  const text = ((pv.input.tokens || {}).tone || {})[tone] || '';
  const m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(text); let rgb;
  if (m) rgb = [+m[1], +m[2], +m[3]]; else { const h = text.replace('#', ''); rgb = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  const want = u.valToPos(v, 'y', true);
  const b = u.bbox;
  let x0 = Math.max(Math.ceil(u.valToPos(xa, 'x', true)) + 6, Math.ceil(b.left) + 2);
  let x1 = Math.min(Math.floor(u.valToPos(xb, 'x', true)) - 6, Math.floor(b.left + b.width) - 70);
  if (x1 - x0 < 8) return { want, got: null, n: 0, why: 'segment too short', x: [x0, x1] };
  const y0 = Math.max(Math.ceil(b.top), Math.floor(want) - 6), y1 = Math.min(Math.floor(b.top + b.height) - 1, Math.ceil(want) + 6);
  if (y1 < y0) return { want, got: null, n: 0, why: 'off the plot', y: [b.top, b.top + b.height] };
  const w = x1 - x0, img = u.ctx.getImageData(x0, y0, w, y1 - y0 + 1).data;
  let sw = 0, sy = 0, n = 0;
  for (let yy = 0; yy <= y1 - y0; yy++) for (let xx = 0; xx < w; xx++) {
    const i = 4 * (yy * w + xx), a = img[i + 3];
    if (a < 60) continue;
    if (Math.abs(img[i] - rgb[0]) + Math.abs(img[i + 1] - rgb[1]) + Math.abs(img[i + 2] - rgb[2]) > 60) continue;
    sw += a; sy += a * (y0 + yy + 0.5); n++;
  }
  return { want, got: n ? sy / sw : null, n, cols: w, dpr: devicePixelRatio, rgb }; }"""

TREE = """([dash, key]) => { const s = document.querySelector(`#${dash} .dd-panel[data-panel="${key}"]`); if (!s) return null;
  return [...s.querySelectorAll('tbody tr[data-id]')].map((tr) => { const td = tr.querySelector('td[data-col="worst"]'); const b = td && td.querySelector('.dv-state');
    return { id: tr.dataset.id, state: b ? b.dataset.state : null, word: b ? ((b.querySelector('.dv-state-word') || {}).textContent || null) : null, none: !!(td && td.querySelector('.dv-none')) }; }); }"""

PEEK = """(sel) => { const p = document.querySelector(sel); if (!p || p.hidden) return null;
  return { sections: [...p.querySelectorAll('h3.dv-peek-section')].map((h) => h.textContent.trim()),
           fields: [...p.querySelectorAll('tr.dv-peek-field')].filter((tr) => !tr.closest('.dv-prop-rest')).map((tr) => tr.dataset.p),
           dashes: [...p.querySelectorAll('tr.dv-peek-field')].filter((tr) => !tr.closest('.dv-prop-rest')).filter((tr) => (tr.querySelector('td') || {}).textContent.trim() === '—').map((tr) => tr.dataset.p),
           views: [...p.querySelectorAll('.dv-peek-view[data-section]')].map((s) => { const e = s.querySelector('data-views');
             return { key: s.dataset.section, drawn: !!(e && e.dataset.view && e.model), rows: e && e.model ? e.model.rows.length : null, empty: !!s.querySelector('.dv-empty') }; }) }; }"""

KPI = """(sel) => [...document.querySelectorAll(sel + ' data-kpi')].map((k) => ({ label: ((k.querySelector('.dv-kpi-label') || {}).textContent || '').trim(),
  num: ((k.querySelector('.dv-kpi-num') || {}).textContent || '').trim(), unit: ((k.querySelector('.dv-kpi-unit') || {}).textContent || '').trim() }))"""

CELLS = """([sel, col]) => [...document.querySelectorAll(sel + ' tbody tr[data-id]')].map((tr) => ({ id: tr.dataset.id, text: ((tr.querySelector(`td[data-col="${col}"]`) || {}).textContent || '').trim() }))"""


def settle(page, n=3):
    page.evaluate(SETTLE, n)


def until(page, js, arg=None, timeout=WAIT):
    try:
        page.wait_for_function(js, arg=arg, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def new_page(browser, base, *, width=1280, dark=False):
    context = browser.new_context(viewport={"width": width, "height": 1000}, color_scheme="dark" if dark else "light", device_scale_factor=1)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.goto(base + PAGE)
    page.wait_for_function("window.kitReady === true", timeout=WAIT)
    return page


def add_dash(page, id_, src, *, live=True):
    """A <data-dashboard> over `src` (no-url), its panels drawn; a live one once its datasets exist."""
    page.evaluate("""([id, src, live]) => new Promise((done) => { const d = document.createElement('data-dashboard'); d.id = id; d.setAttribute('no-url', '');
      if (live) d.addEventListener('data-dashboard-live', () => done(), { once: true }); d.setAttribute('src', src); document.body.append(d); if (!live) done(); })""", [id_, URL + src, live])
    return until(page, """(id) => { const d = document.getElementById(id); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length === d.dash.panels.filter((p) => p.views.length).length && els.every((e) => e.dataset.view); }""", id_)


def push(page, id_, name, rows, how="append"):
    page.evaluate("([id, name, rows, how]) => document.getElementById(id).datasets[name][how](rows)", [id_, name, rows, how])


def seek(page, id_, t):
    page.evaluate("([id, t]) => { const c = document.getElementById(id).clock; c.pause(); c.seek(t); }", [id_, t])


def panel(page, dash, name):
    return page.evaluate(PANEL, [dash, name])


def shot(page, name, sel=None):
    try:
        settle(page, 2)
        if sel:
            page.locator(sel).first.screenshot(path=str(OUT / f"{name}.png"))
        else:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001 -- a missing picture is not a failed behaviour; say so
        print(f"(screenshot {name} not taken: {e})")


# ------------------------------------------------------------------------------------------------- 1. live plot limits
def ends_of(limits):
    out = {}
    for side in ("warn", "error"):
        pair = limits.get(side)
        if isinstance(pair, list):
            out[f"{side}_lo"], out[f"{side}_hi"] = pair[0], pair[1]
    return out


def value_of(row, end):
    if isinstance(end, str):
        v = cellv(row.get(end))
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return end if isinstance(end, (int, float)) and not isinstance(end, bool) else None


def steps(pairs, same):
    """guides.js's step line, written again: the first pair, each change, the last x."""
    out = []
    for p in pairs:
        if not out or not same(out[-1][1], p[1]):
            out.append(p)
    if out and out[-1][0] != pairs[-1][0]:
        out.append(pairs[-1])
    return out


def limit_oracle(rows, limits, series):
    """§35's limits over `rows` (the readings in the plot's window), written from the contract's words: per series a rule
    at each limit present (a constant spans the drawn rows' x, a change is a step line, a missing value skipped), series
    drawing the same line sharing it, and the zones beyond them. {('limit:b', points): [series…]}, {('zone:b', lo, hi): [series…]}."""
    ends = ends_of(limits)
    live = [b for b in BOUNDS if ends.get(b) is not None]
    groups = {}
    for r in sorted(rows, key=lambda r: r["t"]):
        groups.setdefault(r[series] if series else None, []).append(r)
    if not groups:
        return {}, {}
    x0, x1 = min(r["t"] for r in rows), max(r["t"] for r in rows)

    def shape(pairs, same):
        pts = steps(pairs, same)
        if all(same(p[1], pts[0][1]) for p in pts):
            return [(x0, pts[0][1]), (x1, pts[0][1])]
        return pts
    rules, zones = {}, {}
    for b in live:
        for s, g in groups.items():
            pairs = [(r["t"], value_of(r, ends[b])) for r in g if value_of(r, ends[b]) is not None]
            if pairs:
                rules.setdefault((f"limit:{b}", tuple(shape(pairs, lambda a, c: a == c))), []).append(s)
    present = {s: {b for b in live if any(value_of(r, ends[b]) is not None for r in g)} for s, g in groups.items()}
    zone_of = {"warn_hi": lambda h: ("warn_hi", "error_hi" if "error_hi" in h else None), "error_hi": lambda h: ("error_hi", None),
               "warn_lo": lambda h: ("error_lo" if "error_lo" in h else None, "warn_lo"), "error_lo": lambda h: (None, "error_lo")}
    for b in live:
        for s, g in groups.items():
            if b not in present[s]:
                continue
            lo_end, hi_end = zone_of[b](present[s])
            pairs = []
            for r in g:
                lo = None if lo_end is None else value_of(r, ends[lo_end])
                hi = None if hi_end is None else value_of(r, ends[hi_end])
                if (lo_end is not None and lo is None) or (hi_end is not None and hi is None):
                    continue
                pairs.append((r["t"], (lo, hi)))
            if pairs:
                pts = shape(pairs, lambda a, c: a == c)
                zones.setdefault((f"zone:{b}", tuple((p[0], p[1][0]) for p in pts), tuple((p[0], p[1][1]) for p in pts)), []).append(s)
    return rules, zones


def drawn_guides(guides):
    rules, zones = {}, {}
    for g in guides or []:
        name = str(g.get("guide", ""))
        who = sorted(str(x) for x in (g.get("shared") or [g.get("series")]))
        if name.startswith("limit:"):
            rules[(name, tuple((p[0], p[1]) for p in g.get("points") or []))] = who
        elif name.startswith("zone:"):
            zones[(name, tuple((p[0], p[1]) for p in g.get("lo") or []), tuple((p[0], p[1]) for p in g.get("hi") or []))] = who
    return rules, zones


def norm(d):
    return {k: sorted(str(x) for x in v) for k, v in d.items()}


def show(d):
    return [[k[0], [list(p) for p in k[1]], v] for k, v in list(d.items())[:8]]


def measure_plot(page, tag, sel, view, rows):
    """The plot's limits against the oracle over the rows in its window, each limit line's pixels, its y range."""
    st = page.evaluate(PLOT, sel)
    if not st:
        check(f"{tag}: the plot is drawn", False, None)
        return None
    a, b = st["x"]
    p = view["plot"]
    only = set(p.get("only") or [])
    inwin = [r for r in rows if a < r["t"] <= b and (not only or r[p["series"]] in only)]
    want_r, want_z = limit_oracle(inwin, p["limits"], p.get("series"))
    got_r, got_z = drawn_guides(st["guides"])
    check(f"{tag}: the limits drawn (plotView.guides) are §35's over the {len(inwin)} readings in the window ({len(want_r)} rules)",
          bool(want_r) and norm(got_r) == norm(want_r), {"drawn": show(got_r), "want": show(want_r), "window": [a, b], "rows held": st["rows"]})
    check(f"{tag}: the zones beyond them are there ({len(want_z)}: between warn and error in the warn tone, from the error limit to the edge)",
          bool(want_z) and norm(got_z) == norm(want_z), {"drawn": [list(k) for k in got_z][:6], "want": [list(k) for k in want_z][:6]})
    # each limit's line on the canvas: every horizontal run of its step line, at its value on the plot's own y scale
    bad, seen = [], 0
    tone_of = {"warn": "warn", "error": "bad"}
    for (name, pts), _who in want_r.items():
        tone = tone_of[name[6:].split("_")[0]]
        for i in range(len(pts) - 1):
            xa, xb, v = pts[i][0], pts[i + 1][0], pts[i][1]
            if xb - xa < 0.6:
                continue
            m = page.evaluate(LINE_Y, [sel, v, xa, xb, tone])
            seen += 1
            if not m or m.get("got") is None or abs(m["got"] - m["want"]) > m.get("dpr", 1):
                bad.append({"limit": name, "value": v, "x": [xa, xb], "measured": m})
    check(f"{tag}: each limit's dashed line is on the canvas at its value's y within 1 px ({seen} runs measured from the pixels)",
          seen > 0 and not bad, bad[:3] or {"runs": seen})
    vals = [pt[1] for (name, pts) in want_r for pt in pts]
    check(f"{tag}: y takes every limit in ({min(vals) if vals else None} … {max(vals) if vals else None} inside {st['y']})",
          bool(vals) and st["y"][0] is not None and st["y"][0] <= min(vals) and st["y"][1] >= max(vals), {"y": st["y"], "limits": [min(vals), max(vals)] if vals else None})
    return st


def plot_limits(browser, base):
    page = new_page(browser, base)
    rows = load("readings.json")["rows"]
    ok = add_dash(page, "live", "live.base")
    check("limits: the live dashboard draws its panels", ok)
    push(page, "live", "measures", rows)
    push(page, "live", "latest", [r for r in rows if r["check"] == "board_temp"], "upsert")
    end = max(r["t"] for r in rows)
    keys = {n: panel(page, "live", n) for n in ("Board temperature", "Supply voltage", "Both against numbers")}
    sels = {n: f"#live .dd-panel[data-panel='{k}']" for n, k in keys.items()}
    ok = until(page, """([sels, end]) => sels.every((s) => { const el = document.querySelector(s + ' .dv-view-plot'); return el && el.uplot && Math.abs(el.uplot.scales.x.max - end) < 1e-6; })""", [list(sels.values()), end])
    settle(page, 4)
    check("limits: following, every plot's window ends at the newest reading (t = T0 + 40 s)", ok and page.evaluate("() => document.getElementById('live').clock.following"),
          {n: (page.evaluate(PLOT, s) or {}).get("x") for n, s in sels.items()})
    for name in ("Board temperature", "Supply voltage", "Both against numbers"):
        with guard(f"limits, following: {name}"):
            measure_plot(page, f"limits, following: {name}", sels[name], view_of("live.base", name), rows)
    shot(page, "limits-following", sels["Board temperature"])

    # a series the legend hides takes its limits with it (CONTRACT §31's addendum), and shows them again
    with guard("limits: a hidden series"):
        sel = sels["Board temperature"]
        key = page.locator(f"{sel} .dv-view-plot .dv-legend-key[data-legend-series='board_temp']")
        hidden = again = None
        if key.count() == 1:
            key.click(timeout=5000)
            settle(page)
            hidden = page.evaluate(PLOT, sel)
            key.click(timeout=5000)
            settle(page)
            again = page.evaluate(PLOT, sel)
        before = [g["guide"] for g in (page.evaluate(PLOT, sel) or {}).get("guides") or [] if str(g.get("guide", "")).startswith(("limit:", "zone:"))]
        check("limits: hiding board_temp in its legend takes its limits off the drawing; showing it brings them back",
              hidden is not None and not [g for g in hidden["guides"] if str(g.get("guide", "")).startswith(("limit:", "zone:"))] and bool(before)
              and len([g for g in again["guides"] if str(g.get("guide", "")).startswith(("limit:", "zone:"))]) == len(before),
              {"hidden": hidden and [g["guide"] for g in hidden["guides"]], "shown": before})

    # rewind: paused before the step, across it, after it; each window's limits as of its t
    page.evaluate("() => document.getElementById('live').clock.pause()")
    for t, what in ((T0 + 15.25, "before warn_hi steps up (60)"), (T0 + 25.25, "across the step (60 then 65)"), (T0 + 38.25, "after it (65)")):
        with guard(f"limits, paused at T0 + {t - T0:g} s"):
            seek(page, "live", t)
            ok = until(page, """([sels, t]) => sels.every((s) => { const el = document.querySelector(s + ' .dv-view-plot'); return el && el.uplot && Math.abs(el.uplot.scales.x.max - t) < 1e-6; })""", [list(sels.values()), t])
            settle(page, 4)
            check(f"limits, paused at T0 + {t - T0:g} s: every plot's window ends at t", ok, {n: (page.evaluate(PLOT, s) or {}).get("x") for n, s in sels.items()})
            for name in ("Board temperature", "Supply voltage", "Both against numbers"):
                with guard(f"limits, paused at T0 + {t - T0:g} s: {name}"):
                    measure_plot(page, f"limits, paused at T0 + {t - T0:g} s ({what}): {name}", sels[name], view_of("live.base", name), rows)
            st = page.evaluate(PLOT, sels["Board temperature"]) or {}
            warn = [g for g in st.get("guides") or [] if g.get("guide") == "limit:warn_hi"]
            vals = sorted({p[1] for g in warn for p in g.get("points") or []})
            want = {T0 + 15.25: [60], T0 + 25.25: [60, 65], T0 + 38.25: [65]}[t]
            check(f"limits, paused at T0 + {t - T0:g} s: board_temp's warn limit rewound with the clock: {want}", vals == want, vals)
            shot(page, f"limits-paused-{int(t - T0)}", sels["Board temperature"])
    page.evaluate("() => document.getElementById('live').clock.goLive()")
    ok = until(page, """([s, end]) => { const el = document.querySelector(s + ' .dv-view-plot'); return el && el.uplot && Math.abs(el.uplot.scales.x.max - end) < 1e-6; }""", [sels["Board temperature"], end])
    settle(page, 3)
    with guard("limits, back to live"):
        check("limits: back to live, the window ends at the newest reading again", ok)
        measure_plot(page, "limits, back to live: Board temperature", sels["Board temperature"], view_of("live.base", "Board temperature"), rows)
    check("limits: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 2. roll-up as of t
GATES = [  # (t from T0, device, rank): each a new version of its device's one gate
    (1, "stationA", 0), (1, "stationB", 0), (1, "stationC", 0),
    (10, "stationB", 1),
    (20, "stationC", 4),
    (30, "stationB", 0),
]
MOVE_AT = 25  # s from T0: station C's node moves under plate 1 (a new version of the live tree's row)


def gate_rows():
    return [{"id": f"{d}#temp", "t": T0 + dt, "device": d, "gate": "temp", "rank": r} for dt, d, r in GATES]


def rollup_oracle(tree_rows, gates, t):
    """Each node's worst rank at t: the newest version per gate at or before t, over the node and every node under it
    (the tree as of t: the newest version per node at or before t). None where no gate is under it."""
    newest = {}
    for g in gates:
        if g["t"] <= t and (g["id"] not in newest or g["t"] >= newest[g["id"]]["t"]):
            newest[g["id"]] = g
    nodes = {}
    for n in tree_rows:
        if n.get("t", -math.inf) <= t and (n["id"] not in nodes or n.get("t", -math.inf) >= nodes[n["id"]].get("t", -math.inf)):
            nodes[n["id"]] = n
    kids = {}
    for n in nodes.values():
        if not empty(n.get("parent")):
            kids.setdefault(n["parent"], []).append(n["id"])

    def under(i, seen):
        if i in seen:
            return []
        seen.add(i)
        return [i] + [x for k in kids.get(i, []) for x in under(k, seen)]
    out = {}
    for i in nodes:
        ids = set(under(i, set()))
        ranks = [g["rank"] for g in newest.values() if g["device"] in ids]
        out[i] = max(ranks) if ranks else None
    return out


def rollup(browser, base):
    page = new_page(browser, base)
    ok = add_dash(page, "roll", "rollup.base")
    check("roll-up: the dashboard draws its two trees", ok)
    gates = gate_rows()
    push(page, "roll", "gates", gates, "upsert")
    push(page, "roll", "nodes", [{"id": "stationC", "t": T0 + MOVE_AT, "label": "Station C", "parent": "plate1"}], "upsert")
    comp = load("components.json")["rows"]
    nodes = load("nodes.json")["rows"] + [{"id": "stationC", "t": T0 + MOVE_AT, "label": "Station C", "parent": "plate1"}]
    keys = {"Components": panel(page, "roll", "Components"), "Nodes": panel(page, "roll", "Nodes")}
    labels = load("components.json")["properties"]["worst"]["labels"]
    end = T0 + max(g[0] for g in GATES)

    def drawn(name):
        got = page.evaluate(TREE, ["roll", keys[name]]) or []
        return {r["id"]: (None if r["none"] else r["state"]) for r in got}, got

    def want_of(name, t):
        o = rollup_oracle(comp if name == "Components" else nodes, gates, t)
        return {i: (None if v is None else str(v)) for i, v in o.items()}

    def measure(t, what):
        for name in ("Components", "Nodes"):
            with guard(f"roll-up, {what}: {name}"):
                want = want_of(name, t)
                # the tree redraws when the roll-up's cells move: wait for it (a ceiling, not a pause), then read once
                until(page, """([dash, key, want]) => { const s = document.querySelector(`#${dash} .dd-panel[data-panel="${key}"]`); if (!s) return false;
                  const rows = [...s.querySelectorAll('tbody tr[data-id]')]; if (rows.length !== Object.keys(want).length) return false;
                  return rows.every((tr) => { const td = tr.querySelector('td[data-col="worst"]'); const b = td && td.querySelector('.dv-state'); const got = td && td.querySelector('.dv-none') ? null : b ? b.dataset.state : undefined; return got === want[tr.dataset.id]; }); }""",
                      ["roll", keys[name], want], timeout=8000)
                got, raw = drawn(name)
                words = {r["id"]: r["word"] for r in raw if r["state"] is not None}
                check(f"roll-up, {what}: {name}: each node's worst gate is the gates' newest versions at t under it ({len(want)} nodes)",
                      got == want, {"drawn": got, "want": want})
                check(f"roll-up, {what}: {name}: each worst reads as its status word",
                      bool(words) and all(words[i] == labels.get(got[i], got[i]) for i in words), words)

    ok = until(page, "(end) => { const c = document.getElementById('roll').clock; return c.following && Math.abs(c.t - end) < 1e-6; }", end)
    check("roll-up: following, the clock is at the newest gate (T0 + 30 s)", ok, page.evaluate("() => { const c = document.getElementById('roll').clock; return { t: c.t, following: c.following }; }"))
    measure(end, "following at T0 + 30 s")
    shot(page, "rollup-following", "#roll .dd-grid")
    for dt in (5.5, 15.5, 22.5, 27.5):
        seek(page, "roll", T0 + dt)
        settle(page, 4)
        measure(T0 + dt, f"paused at T0 + {dt:g} s")
        if dt in (15.5, 27.5):
            shot(page, f"rollup-paused-{int(dt)}", "#roll .dd-grid")
    page.evaluate("() => document.getElementById('roll').clock.goLive()")
    settle(page, 4)
    measure(end, "back to live")
    check("roll-up: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 3. empty peek sections
PEEK_WANT = {
    # the plain check: its level, and a note that says why it has no value; nothing else has anything for it
    "plain": {"sections": ["Level", "Notes"], "views": {}},
    # a stock diagnostic: every section, its evidence table its three parts
    "stock": {"sections": ["Level", "Measured", "Evidence", "Stock diagnostic", "Notes"], "views": {"Evidence": 3}},
    # no evidence fields, but its view has rows: the section stays
    "evidence": {"sections": ["Level", "Evidence"], "views": {"Evidence": 2}},
}


def peek_measure(page, tag, sel):
    with guard(tag):
        until(page, """(sel) => { const p = document.querySelector(sel); if (!p || p.hidden) return false; return [...p.querySelectorAll('.dv-peek-view[data-section] data-views')].every((e) => e.dataset.view && e.model); }""", sel, timeout=10000)
        settle(page, 3)
        return page.evaluate(PEEK, sel)


def peek_checks(tag, rid, got):
    want = PEEK_WANT[rid]
    checks_rows = {r["id"]: r for r in load("checks.json")["rows"]}
    row = checks_rows[rid]
    view = view_of("peek.base", "Checks")
    secs = view["record"]["sections"]
    gone = [s for s in secs if s["name"] not in want["sections"]]
    got = got or {}
    check(f"{tag}: '{rid}' peek draws exactly the sections with something for it: {want['sections']}", got.get("sections") == want["sections"], got.get("sections"))
    gone_fields = [p for s in gone for p in s.get("properties") or []]
    check(f"{tag}: '{rid}': no field of an absent section is drawn ({len(gone_fields)} fields)", not set(gone_fields) & set(got.get("fields") or []), got.get("fields"))
    views = {v["key"]: v for v in got.get("views") or []}
    check(f"{tag}: '{rid}': an embedded view only where its section is drawn, each with its rows: {want['views']}",
          set(views) == set(want["views"]) and all(views[k]["drawn"] and views[k]["rows"] == n for k, n in want["views"].items()),
          got.get("views"))
    shown = [p for s in secs if s["name"] in want["sections"] for p in s.get("properties") or []]
    # a field with no value draws "—" (with its reason on hover when it has one), as before, in a section that is drawn
    dashes = [p for p in shown if empty(cellv(row.get(p)))]
    check(f"{tag}: '{rid}': a drawn section keeps its own empty fields as '—' ({dashes})", sorted(got.get("dashes") or []) == sorted(dashes), got.get("dashes"))


def peeks(browser, base):
    page = new_page(browser, base)
    ok = add_dash(page, "peekdash", "peek.base")
    check("peek: the live dashboard draws its checks table", ok)
    key = panel(page, "peekdash", "Checks")
    for rid in ("plain", "stock", "evidence"):
        with guard(f"peek, live dashboard: '{rid}'"):
            cell = page.locator(f"#peekdash .dd-panel[data-panel='{key}'] tbody tr[data-id='{rid}'] td[data-col='name']").first
            cell.click(timeout=10000)
            got = peek_measure(page, f"peek, live dashboard: '{rid}'", "#peekdash .dd-drill .dv-peek")
            peek_checks("peek, live dashboard", rid, got)
            shot(page, f"peek-live-{rid}", "#peekdash .dd-drill .dv-peek")
    check("peek, live dashboard: no page error", not page.errors, page.errors[:3])
    # the same view in a plain <data-views> over the files (its sections' dataset handed in el.sections)
    with guard("peek, plain <data-views>"):
        page.evaluate("""async ([url, view]) => { const el = document.createElement('data-views'); el.id = 'plainpeek'; el.setAttribute('no-url', '');
          const [checks, parts] = await Promise.all([kit.loadDataset(url + 'checks.json'), kit.loadDataset(url + 'parts.json')]);
          el.base = { views: [view] }; el.data = checks; el.sections = { parts }; document.body.append(el); }""", [URL, view_of("peek.base", "Checks")])
        until(page, "() => { const e = document.getElementById('plainpeek'); return !!e && !!e.dataset.view && !!e.model; }")
        for rid in ("plain", "stock", "evidence"):
            page.evaluate("(id) => document.getElementById('plainpeek').openPeek(id)", rid)
            got = peek_measure(page, f"peek, plain <data-views>: '{rid}'", "#plainpeek .dv-peek")
            peek_checks("peek, plain <data-views>", rid, got)
        shot(page, "peek-plain-plain", "#plainpeek .dv-peek")
    check("peek: no page error", not page.errors, page.errors[:3])
    page.context.close()


# ------------------------------------------------------------------------------------------------- 4. a unit on a typed number column
def num_of(text):
    try:
        return float(str(text).split()[0].replace(",", ""))
    except (ValueError, IndexError):
        return None


def units(browser, base):
    page = new_page(browser, base)
    rows = load("readings.json")["rows"]
    ok = add_dash(page, "live", "live.base")
    check("units: the live dashboard draws its panels", ok)
    push(page, "live", "measures", rows)
    push(page, "live", "latest", [r for r in rows if r["check"] == "board_temp"], "upsert")
    end = max(r["t"] for r in rows)
    until(page, "(end) => { const c = document.getElementById('live').clock; return Math.abs(c.t - end) < 1e-6; }", end)
    settle(page, 6)
    newest = {}
    for r in rows:
        newest[r["check"]] = r
    with guard("units: the KPI cards"):
        sel = f"#live .dd-panel[data-panel='{panel(page, 'live', 'Readings')}']"
        until(page, "(sel) => document.querySelectorAll(sel + ' data-kpi .dv-kpi-num').length >= 2", sel, timeout=10000)
        cards = {c["label"]: c for c in page.evaluate(KPI, sel)}
        want = {c: (r["reading"]["value"], r["reading"]["unit"]) for c, r in newest.items()}
        check("units, live: each KPI card shows its newest reading's own unit (°C, V) beside its number",
              set(cards) >= set(want) and all(cards[c]["unit"] == u and num_of(cards[c]["num"]) is not None and abs(num_of(cards[c]["num"]) - v) < 0.06 for c, (v, u) in want.items()),
              {"drawn": cards, "want": want})
        shot(page, "units-kpi", sel)
    with guard("units: the inline-unit table on live data"):
        sel = f"#live .dd-panel[data-panel='{panel(page, 'live', 'Reading rows')}']"
        until(page, "(sel) => document.querySelectorAll(sel + ' tbody tr[data-id]').length > 0", sel, timeout=10000)
        cells = page.evaluate(CELLS, [sel, "reading"])
        by_id = {r["id"]: r for r in rows}
        bad = [c for c in cells if c["id"] not in by_id or not c["text"].endswith(" " + by_id[c["id"]]["reading"]["unit"])
               or num_of(c["text"]) is None or abs(num_of(c["text"]) - by_id[c["id"]]["reading"]["value"]) > 1e-6]
        check(f"units, live: units: inline writes each reading cell's own unit beside its number ({len(cells)} drawn rows)", bool(cells) and not bad, bad[:3] or cells[:2])
        shot(page, "units-table-live", sel)
        rid = cells[0]["id"] if cells else None
        if rid:
            page.locator(f"{sel} tbody tr[data-id='{rid}'] td[data-col='check']").first.click(timeout=10000)
            until(page, "() => { const p = document.querySelector('#live .dd-drill .dv-peek'); return !!p && !p.hidden; }", timeout=10000)
            settle(page, 2)
            text = page.evaluate("() => { const tr = document.querySelector('#live .dd-drill .dv-peek tr[data-p=\"reading\"] td'); return tr ? tr.textContent.trim() : null; }")
            u = by_id[rid]["reading"]["unit"]
            check(f"units, live: the peek of a reading row writes its unit ({u})", bool(text) and text.endswith(u) and num_of(text) is not None, text)
            page.keyboard.press("Escape")
    with guard("units: the plots of a typed number column of {value, unit} cells"):
        for name, ds_rows in (("Reading plot", rows), ("Newest reading", [r for r in rows if r["check"] == "board_temp"])):
            sel = f"#live .dd-panel[data-panel='{panel(page, 'live', name)}']"
            st = page.evaluate(PLOT, sel) or {}
            a, b = (st.get("x") or [None, None])
            ys = [y for col in (st.get("data") or [[]])[1:] for y in col if y is not None]
            want = sorted(round(r["reading"]["value"], 4) for r in ds_rows if a is not None and a < r["t"] <= b)
            check(f"units, live: '{name}' draws the readings' numbers ({len(want)} in its window), never a cell object",
                  bool(ys) and all(isinstance(y, (int, float)) and not isinstance(y, bool) for y in ys) and sorted(round(y, 4) for y in ys) == want,
                  {"drawn": sorted(ys)[:6] if all(isinstance(y, (int, float)) for y in ys) else [str(y)[:40] for y in ys[:4]], "want": want[:6], "n": [len(ys), len(want)]})
    check("units, live: no page error", not page.errors, page.errors[:3])
    # the file: the same rows, the same inline-unit table, in a plain <data-views>
    with guard("units: the inline-unit table over the file"):
        page.evaluate("""async ([url, view]) => { const el = document.createElement('data-views'); el.id = 'plainunits'; el.setAttribute('no-url', '');
          el.base = { views: [view] }; el.data = await kit.loadDataset(url + 'readings.json'); document.body.append(el); }""",
                      [URL, {k: v for k, v in view_of("live.base", "Reading rows").items() if k not in ("from", "at")}])
        until(page, "() => { const e = document.getElementById('plainunits'); return !!e && !!e.dataset.view && e.querySelectorAll('tbody tr[data-id]').length > 0; }")
        cells = page.evaluate(CELLS, ["#plainunits", "reading"])
        by_id = {r["id"]: r for r in rows}
        bad = [c for c in cells if c["id"] not in by_id or not c["text"].endswith(" " + by_id[c["id"]]["reading"]["unit"])]
        check(f"units, file: units: inline writes each typed number cell's own unit ({len(cells)} drawn rows)", bool(cells) and not bad, bad[:3] or cells[:2])
        shot(page, "units-table-file", "#plainunits")
    check("units: no page error", not page.errors, page.errors[:3])
    page.context.close()


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists() or not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit is not built: npm --prefix ~/data-ui run build")
        return 1
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
                for name, fn in (("1. live plot limits", plot_limits), ("2. roll-up as of t", rollup), ("3. empty peek sections", peeks), ("4. a unit on a typed number column", units)):
                    with guard(name):
                        fn(browser, base)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    (OUT / "dx-asks-2-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} dx-asks-2 checks pass; screenshots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
