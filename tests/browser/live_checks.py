"""The live tier's acceptance checks (docs/peps/0012-live-data.md, docs/CONTRACT.md §26), measured in headless Chromium
on tests/browser/fixtures/live.html: a live <data-dashboard> (fixtures/live/live.base) whose rows the page pushes at
real-time rates, plus one dataset served over server-sent events by this script's own server.

    ~/psu-atlas/.venv/bin/python tests/browser/live_checks.py [OUT_DIR]      # after npm run build

What it holds (every number measured, never a DOM-presence stand-in):
  - the page opens following; a scrub on the playback bar pauses at t, and while rows keep arriving the time cursor
    (the plot's playhead and the bar's thumb, getBoundingClientRect) and t hold still;
  - one click on ● LIVE goes back, timed from the click to the frame that shows it;
  - while streaming, no view draws twice in one frame, a paused view draws nothing, frame times stay in budget;
  - the byte budget holds under a flood, the newest of a quiet stream survives, the heap comes back;
  - the tail holds while scrolled and shows "N new · Resume";
  - Space pauses and never jumps live, a fast replay rejoins live, End / Home / Ctrl+Shift+arrows;
  - #t=live while following, #t=<seconds> while paused, a reload with #t=live follows;
  - the connection line reads live, stale and reconnecting, and an SSE drop resumes by Last-Event-ID with no gap;
  - the levels card's newest bin, the plot's points per pixel column and a one-sample spike, the KPI at t;
  - a display: age cell ticks with no new row and holds while paused (a8, added after the first commit of these checks).
  - paused, a view redraws only when what it shows at t can change: draws counted per panel while versions and rows
    arrive after t (none), a late one at or before t (the panels whose window holds it), retention reaching t (follow-up
    to bfc632f, found by the RobotDx lane; committed before its fix).
Committed before the code it tests (lane/live, Step 2). Writes OUT_DIR/live-checks.json (default
reports/media/live) and exits 1 if any check fails; a speed budget missed on an overloaded machine is SOFT.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import socket
import socketserver
import sys
import threading
import time
import urllib.request
from functools import partial

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "live"
OUT.mkdir(parents=True, exist_ok=True)
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []


def check(name, ok, value=None, soft=False):
    checks.append({"name": name, "ok": bool(ok), "value": value, **({"soft": True} if soft else {})})
    print(("SOFT " if soft else "PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def budget(name, ms, limit, value=None):
    """A speed budget that knows the machine: enforced while the 1-minute load average is under the CPU count; above it a
    miss is SOFT with the load beside it (tests/browser/checks.py's rule)."""
    load, cpus = os.getloadavg()[0], os.cpu_count() or 1
    note = f"{ms:.1f} ms (budget {limit} ms); load {load:.1f} on {cpus} CPUs" + (f"; {value}" if value else "")
    if ms < limit or load <= cpus:
        check(name, ms < limit, note)
    else:
        check(name, True, note + " -- OVERLOADED: budget not enforced on this run", soft=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ the server: files + one SSE feed with a ring
class Feed:
    """Rows n = 1, 2, … every 50 ms, kept (a host's ring), so a reconnect with Last-Event-ID k resumes at k + 1."""

    def __init__(self):
        self.rows: list[dict] = []
        self.lock = threading.Condition()
        self.running = True
        self.generation = 0          # bumped by /sse/drop: every open stream ends
        self.seen_ids: list[str] = []
        self.stop = False
        threading.Thread(target=self._make, daemon=True).start()

    def _make(self):
        while not self.stop:
            time.sleep(0.05)
            with self.lock:
                if self.running:
                    n = len(self.rows) + 1
                    self.rows.append({"t": time.time(), "n": n})
                    self.lock.notify_all()


FEED = Feed()


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/sse/rows":
            return self._sse()
        if path in ("/sse/pause", "/sse/resume", "/sse/drop", "/sse/log"):
            with FEED.lock:
                if path == "/sse/pause":
                    FEED.running = False
                elif path == "/sse/resume":
                    FEED.running = True
                elif path == "/sse/drop":
                    FEED.generation += 1
                FEED.lock.notify_all()
                body = json.dumps({"rows": len(FEED.rows), "seen": FEED.seen_ids, "running": FEED.running}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def _sse(self):
        last = self.headers.get("Last-Event-ID")
        with FEED.lock:
            FEED.seen_ids.append(last or "")
            gen = FEED.generation
        cursor = int(last) if last and last.isdigit() else len(FEED.rows)
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 300\n\n")
            self.wfile.flush()
            while True:
                with FEED.lock:
                    FEED.lock.wait_for(lambda: len(FEED.rows) > cursor or FEED.generation != gen or FEED.stop, timeout=1.0)
                    if FEED.generation != gen or FEED.stop:
                        return
                    batch = FEED.rows[cursor:]
                for row in batch:
                    cursor = row["n"]
                    self.wfile.write(f"id: {row['n']}\nevent: rows\ndata: {json.dumps({'rows': [row]})}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ------------------------------------------------------------------ the page
FEEDER = """() => {
  // rows at real time: joints at `hz` each, an event every 100 ms, a level per check every 500 ms, all with t = now
  window.feedStats = { appended: 0 };
  window.startFeed = ({ hz = 300, joints = ['shoulder', 'elbow', 'wrist'], quiet = true } = {}) => {
    const d = dash.datasets;
    let last = Date.now() / 1000, k = 0, ev = 0, lv = 0;
    if (quiet) d.samples.append([{ t: last - 0.001, joint: 'quiet', position: 42, current: 0 }]);
    const id = setInterval(() => {
      const now = Date.now() / 1000;
      const n = Math.max(1, Math.round((now - last) * hz));
      const rows = [];
      for (let i = 1; i <= n; i++) {
        const t = last + ((now - last) * i) / n;
        k++;
        for (const [j, joint] of joints.entries()) rows.push({ t, joint, position: Math.sin(k / 40 + j), current: 0.5 + 0.1 * Math.cos(k / 13) });
      }
      d.samples.append(rows);
      feedStats.appended += rows.length;
      if (now - ev >= 0.1) { ev = now; d.events.append([{ t: now, source: 'moteus/' + (k % 3), severity: ['info', 'warn', 'error'][k % 3], message: 'reading ' + k }]); }
      if (now - lv >= 0.5) { lv = now; d.levels.append(['motor', 'can', 'camera'].map((name, i) => ({ t: now, name, level: ['ok', 'warn', 'error', 'ok'][(Math.floor(now * 2) + i) % 4], message: name + ' check' }))); }
      last = now;
    }, 10);
    window.stopFeed = () => clearInterval(id);
  };
  // every live draw, per panel, and every frame boundary
  window.draws = []; window.frameMarks = [];
  for (const el of document.querySelectorAll('#dash data-views')) el.addEventListener('data-views-live', (e) => draws.push({ at: performance.now(), id: el.id, ms: e.detail.ms, frame: e.detail.frame }));
  const tick = () => { frameMarks.push(performance.now()); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}"""

PANEL = "(name) => document.querySelector(`#dash section[aria-label=\"${name}\"]`)"


def frames(page, n=2):
    page.evaluate("(n) => new Promise((done) => { const step = (k) => (k ? requestAnimationFrame(() => step(k - 1)) : done()); step(n); })", n)


def open_page(browser, base, hash_=""):
    context = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = context.new_page()
    page.errors = []
    page.foreign = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: page.foreign.append(r.url) if not r.url.startswith(base) and not r.url.startswith("data:") else None)
    page.goto(f"{base}/tests/browser/fixtures/live.html{hash_}")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate("""() => new Promise((done) => {
      const d = document.createElement('data-dashboard');
      d.id = 'dash';
      d.addEventListener('data-dashboard-live', () => done(), { once: true });
      d.setAttribute('src', '/tests/browser/fixtures/live/live.base');
      document.body.append(d);
      window.dash = d;
    })""")
    page.wait_for_function("() => document.querySelectorAll('#dash data-views').length >= 5", timeout=WAIT)
    page.evaluate(FEEDER)
    page.evaluate("() => startFeed()")
    page.wait_for_function("() => dash.datasets.samples.rowCount > 300 && document.querySelector('#dash .dv-view-plot [data-playhead]')", timeout=WAIT)
    frames(page, 3)
    return page


def playhead(page):
    return page.evaluate("""() => {
      const plot = document.querySelector('#dash section[aria-label="Joints"] .dv-view-plot');
      const ph = plot.querySelector('[data-playhead]').getBoundingClientRect();
      const box = plot.getBoundingClientRect();
      const thumb = document.querySelector('#dash .dv-pb-thumb').getBoundingClientRect();
      return { x: ph.left + ph.width / 2, hidden: plot.querySelector('[data-playhead]').hidden, plotRight: box.right,
               thumb: thumb.left + thumb.width / 2, t: dash.clock.t, end: dash.clock.liveEnd, following: dash.clock.following,
               hash: location.hash };
    }""")


def follows_on_open(page):
    s = playhead(page)
    check("live: the page opens following; the URL says #t=live", s["following"] and "t=live" in s["hash"], s)
    # following: t = the newest data, drawn at the plot's right edge (the window ends at t)
    check("live: following, the playhead sits at the plot's right edge", not s["hidden"] and abs(s["plotRight"] - s["x"]) < 40, s)


def scrub_pauses_and_holds(page):
    track = page.locator("#dash .dv-pb-track")
    box = track.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.95, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2, steps=8)
    page.mouse.up()
    frames(page, 2)
    a = playhead(page)
    first_row = page.evaluate("() => document.querySelector('#dash section[aria-label=\"Events\"] tbody tr[data-id]')?.dataset.id")
    newest_t = page.evaluate("() => { const r = dash.datasets.events.latestAt(dash.clock.t); return r ? r.t : null; }")
    page.wait_for_timeout(1200)
    frames(page, 2)
    b = playhead(page)
    first_row_b = page.evaluate("() => document.querySelector('#dash section[aria-label=\"Events\"] tbody tr[data-id]')?.dataset.id")
    check("live: a scrub leaves following; the URL says #t=<seconds>", not a["following"] and "t=live" not in a["hash"] and "t=" in a["hash"], a)
    check("live: paused, t holds while rows arrive (1.2 s of appends)", a["t"] == b["t"] and b["end"] - a["end"] > 0.8, {"t": [a["t"], b["t"]], "end": [a["end"], b["end"]]})
    check("live: paused, the plot's playhead does not move (getBoundingClientRect, 1.2 s of appends)", abs(a["x"] - b["x"]) <= 0.5, [a["x"], b["x"]])
    check("live: paused, the playback bar's thumb does not move either", abs(a["thumb"] - b["thumb"]) <= 0.5, [a["thumb"], b["thumb"]])
    check("live: paused, the event table holds its rows as of t", first_row == first_row_b and newest_t is not None and newest_t <= a["t"], [first_row, first_row_b, newest_t, a["t"]])
    lag = page.evaluate("() => { const b = document.querySelector('#dash .dv-pb-live'); return { text: b.textContent, pressed: b.getAttribute('aria-pressed') }; }")
    check("live: the ● LIVE control shows how far behind live the clock is", lag["pressed"] == "false" and "−" in lag["text"] and " s" in lag["text"], lag)


def paused_draws_nothing(page):
    page.evaluate("() => { window.drawsFrom = draws.length; }")
    page.wait_for_timeout(1000)
    n = page.evaluate("() => draws.slice(drawsFrom).length")
    check("live: paused in the past, no view redraws while rows arrive after t (1 s)", n == 0, n)


def back_to_live(page):
    ms = page.evaluate("""() => new Promise((done) => {
      const b = document.querySelector('#dash .dv-pb-live');
      const t0 = performance.now();
      b.click();
      const ok = () => {
        const plot = document.querySelector('#dash section[aria-label="Joints"] .dv-view-plot');
        const ph = plot.querySelector('[data-playhead]').getBoundingClientRect();
        return dash.clock.following && Math.abs(plot.getBoundingClientRect().right - (ph.left + ph.width / 2)) < 40;
      };
      // WHY a ceiling: a state that never comes must report FAIL, not hang the whole run (it did, ebd4534)
      const step = () => (ok() ? done(performance.now() - t0) : performance.now() - t0 > 5000 ? done(null) : requestAnimationFrame(step));
      requestAnimationFrame(step);
    })""")
    s = playhead(page)
    if ms is None:
        check("live: back to live, click → the frame that shows following at the newest data", False, {"never within 5 s": s})
    else:
        budget("live: back to live, click → the frame that shows following at the newest data", ms, 50)
    check("live: back to live, following and #t=live again; the control is pressed", s["following"] and "t=live" in s["hash"]
          and page.evaluate("() => document.querySelector('#dash .dv-pb-live').getAttribute('aria-pressed')") == "true", s)


def frame_budget_while_streaming(page):
    page.evaluate("() => { window.mark0 = performance.now(); window.d0 = draws.length; window.f0 = frameMarks.length; }")
    page.wait_for_timeout(3000)
    r = page.evaluate("""() => {
      const fr = frameMarks.slice(f0), ds = draws.slice(d0);
      const gaps = fr.slice(1).map((x, i) => x - fr[i]).sort((a, b) => a - b);
      const p95 = gaps[Math.floor(gaps.length * 0.95)] || 0;
      // draws per panel per frame: the live frame loop numbers its frames (data-views-live detail.frame)
      let worst = 0;
      const per = new Map();
      for (const d of ds) { const k = d.id + ':' + d.frame; per.set(k, (per.get(k) || 0) + 1); worst = Math.max(worst, per.get(k)); }
      const ms = ds.map((d) => d.ms).sort((a, b) => a - b);
      return { frames: fr.length, draws: ds.length, worst, p95, drawP95: ms[Math.floor(ms.length * 0.95)] || 0, rows: feedStats.appended };
    }""")
    check("live: streaming, no view draws twice in one animation frame", r["worst"] <= 1 and r["draws"] > 0, r)
    budget("live: streaming 900 rows/s into 5 panels, p95 frame interval", r["p95"], 25, r)
    budget("live: streaming, p95 time of one view's live draw", r["drawP95"], 8, r)


def plot_reduction_and_spike(page):
    r = page.evaluate("""() => new Promise((done) => {
      const plot = document.querySelector('#dash section[aria-label="Joints"] .dv-view-plot');
      dash.datasets.samples.append([{ t: Date.now() / 1000, joint: 'shoulder', position: 50, current: 0 }]);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const w = plot.getBoundingClientRect().width;
        const u = plot.uplot;
        done({ points: Number(plot.dataset.points), width: Math.round(w), ymax: u && u.scales.y.max,
               window: dash.datasets.samples.range(dash.clock.t - 10, dash.clock.t, { stream: 'shoulder' }).reduce((n, p) => n + p.t.length, 0) });
      }));
    })""")
    check("live: the plot draws at most 2 points per pixel column (x positions shared by its series), whatever the rate",
          r["points"] > 0 and r["points"] <= 2 * r["width"] + 4 and r["window"] > r["points"], r)
    check("live: a one-sample spike shows (the y scale reaches it)", r["ymax"] is not None and r["ymax"] >= 50, r)


def tail_holds_and_resumes(page):
    sel = '#dash section[aria-label="Events"]'
    page.wait_for_function(f"() => document.querySelectorAll('{sel} tbody tr[data-id]').length > 12", timeout=WAIT)
    top = page.evaluate(f"() => document.querySelector('{sel} tbody tr[data-id]').dataset.id")
    newest = page.evaluate("() => dash.datasets.events.latestAt(dash.clock.t).id")
    check("live: the event table follows, newest row on top", top == newest, [top, newest])
    page.evaluate(f"() => {{ const s = document.querySelector('{sel} .dv-scroll'); s.scrollTop = 4 * 30; s.dispatchEvent(new Event('scroll')); }}")
    frames(page, 2)
    held_first = page.evaluate(f"() => {{ const s = document.querySelector('{sel} .dv-scroll'); const r = s.getBoundingClientRect(); const rows = [...document.querySelectorAll('{sel} tbody tr[data-id]')].filter((tr) => tr.getBoundingClientRect().top >= r.top + 25); return rows[0] && rows[0].dataset.id; }}")
    page.wait_for_timeout(1000)
    frames(page, 2)
    s = page.evaluate(f"""() => {{
      const el = document.querySelector('{sel} data-views'); const s = el.querySelector('.dv-scroll'); const r = s.getBoundingClientRect();
      const rows = [...el.querySelectorAll('tbody tr[data-id]')].filter((tr) => tr.getBoundingClientRect().top >= r.top + 25);
      const pill = el.querySelector('.dv-live-new');
      return {{ live: el.dataset.live, first: rows[0] && rows[0].dataset.id, pill: pill && !pill.hidden ? pill.textContent : null, following: dash.clock.following }};
    }}""")
    check("live: scrolled away from the newest rows, the tail holds them (the clock still follows)", s["live"] == "held" and s["first"] == held_first and s["following"], {**s, "held_first": held_first})
    check("live: holding, it says how many rows are new: \"N new · Resume\"", bool(s["pill"]) and "new" in s["pill"] and "Resume" in s["pill"], s)
    page.click(f"{sel} .dv-live-new")
    frames(page, 3)
    r = page.evaluate(f"""() => {{ const el = document.querySelector('{sel} data-views');
      return {{ live: el.dataset.live, top: el.querySelector('tbody tr[data-id]').dataset.id, newest: dash.datasets.events.latestAt(dash.clock.t).id,
               scroll: el.querySelector('.dv-scroll').scrollTop, pill: el.querySelector('.dv-live-new') && !el.querySelector('.dv-live-new').hidden }}; }}""")
    check("live: Resume catches up: newest row on top, scrolled to it, the note gone", r["live"] == "following" and r["top"] == r["newest"] and r["scroll"] == 0 and not r["pill"], r)


def keys_and_replay(page):
    page.focus("#dash")
    page.keyboard.press("Space")
    frames(page, 1)
    a = page.evaluate("() => ({ following: dash.clock.following, playing: dash.clock.playing, t: dash.clock.t })")
    page.wait_for_timeout(600)
    b = page.evaluate("() => ({ following: dash.clock.following, t: dash.clock.t, lag: dash.clock.lag })")
    check("live: Space while following pauses at t (no jump, t holds)", not a["following"] and not a["playing"] and a["t"] == b["t"], [a, b])
    page.evaluate("() => dash.clock.setRate(4)")
    page.keyboard.press("Space")
    frames(page, 1)
    c = page.evaluate("() => ({ following: dash.clock.following, playing: dash.clock.playing })")
    check("live: Space while paused replays from t; it does not jump live", c["playing"] and not c["following"], c)
    page.wait_for_function("() => dash.clock.following", timeout=int(max(4000, (b["lag"] / 3 + 3) * 1000)))
    check("live: a 4x replay catches up and rejoins live (decided 2026-10-27)", page.evaluate("() => dash.clock.following && dash.clock.lag < 0.05"))
    page.evaluate("() => dash.clock.setRate(1)")
    page.keyboard.press("Home")
    frames(page, 1)
    h = page.evaluate("() => ({ following: dash.clock.following, t: dash.clock.t, start: dash.clock.start })")
    check("live: Home goes to the oldest data and pauses", not h["following"] and abs(h["t"] - h["start"]) < 1e-6, h)
    page.keyboard.press("End")
    frames(page, 1)
    check("live: End goes live", page.evaluate("() => dash.clock.following"))
    page.keyboard.press("Control+Shift+ArrowLeft")
    frames(page, 1)
    cl = page.evaluate("() => ({ following: dash.clock.following, t: dash.clock.t, start: dash.clock.start })")
    page.keyboard.press("Control+Shift+ArrowRight")
    frames(page, 1)
    cr = page.evaluate("() => dash.clock.following")
    check("live: Ctrl+Shift+← goes to the oldest data, Ctrl+Shift+→ goes live (Rerun's keys)", not cl["following"] and abs(cl["t"] - cl["start"]) < 1e-6 and cr, [cl, cr])


def levels_and_kpi(page):
    page.wait_for_timeout(700)
    r = page.evaluate("""() => {
      const card = document.querySelector('#dash section[aria-label="Health"] .dv-view-levels');
      const out = {};
      const order = ['ok', 'warn', 'unknown', 'stale', 'error'];
      const t0 = Number(card.dataset.t0), t1 = Number(card.dataset.t1);
      for (const name of ['motor', 'can', 'camera']) {
        const strip = card.querySelector(`[data-strip="${name}"]`);
        const bins = strip ? [...strip.querySelectorAll('[data-bin]')] : [];
        const w = (t1 - t0) / bins.length, a = t0 + (bins.length - 1) * w;
        // the oracle: the level in force when the last bin starts, and every change inside it; the worst of them
        const held = [dash.datasets.levels.latestAt(a, name)?.level, ...dash.datasets.levels.range(a, t1, { stream: name })
          .flatMap((p) => Array.from(p.cols.level))].filter(Boolean);
        const want = held.sort((x, y) => order.indexOf(x) - order.indexOf(y)).pop() || '';
        out[name] = { bins: bins.length, last: bins.length ? bins[bins.length - 1].dataset.level : null, want };
      }
      return out;
    }""")
    check("live: the levels card's newest bin holds the worst level of that bin (the oracle reads the dataset)",
          all(v["bins"] > 10 and v["last"] == v["want"] and v["want"] for v in r.values()), r)
    # the KPI at t: paused, each joint's card shows that joint's newest position at or before t
    page.evaluate("() => dash.clock.seek(dash.clock.liveEnd - 2)")
    frames(page, 3)
    k = page.evaluate("""() => [...document.querySelectorAll('#dash section[aria-label="Position"] .dv-kpi-card')].map((c) => {
      const label = c.querySelector('.dv-kpi-label').textContent.trim();
      const num = c.querySelector('.dv-kpi-num');
      const shown = num ? parseFloat(num.dataset.exact || num.getAttribute('title') || num.textContent) : null;
      const want = dash.datasets.samples.latestAt(dash.clock.t, label);
      return { label, shown, want: want && want.position };
    })""")
    check("live: paused at t, each KPI card shows its stream's newest value at or before t (latest-at)",
          len(k) >= 3 and all(x["want"] is not None and abs(x["shown"] - x["want"]) <= 1e-9 + 1e-9 * abs(x["want"]) for x in k), k)
    page.evaluate("() => dash.clock.goLive()")


def byte_budget_holds(page, cdp):
    cdp.send("HeapProfiler.collectGarbage")
    before = cdp.send("Runtime.getHeapUsage")["usedSize"]
    r = page.evaluate("""() => {
      kit.setLiveBudget(4 * 2 ** 20);
      const d = dash.datasets.samples;
      let peak = 0, t = d.liveEnd || d.end || Date.now() / 1000;
      const quiet = d.latestAt(d.end, 'quiet');
      for (let b = 0; b < 300; b++) {
        const rows = [];
        for (let i = 0; i < 5000; i++) { t += 0.0002; rows.push({ t, joint: ['shoulder', 'elbow', 'wrist'][i % 3], position: Math.sin(i), current: i / 5000 }); }
        d.append(rows);
        const total = Object.values(dash.datasets).reduce((n, x) => n + x.bytes, 0);
        peak = Math.max(peak, total);
      }
      return { peak, budget: 4 * 2 ** 20, start: d.start, quietBefore: quiet && quiet.position, quietAfter: d.latestAt(d.end, 'quiet')?.position, rows: d.rowCount };
    }""")
    frames(page, 2)
    cdp.send("HeapProfiler.collectGarbage")
    after = cdp.send("Runtime.getHeapUsage")["usedSize"]
    r["heapGrowthMB"] = round((after - before) / 2 ** 20, 1)
    check("live: 1.5 M rows (about 36 MB) into a 4 MB budget: the live data never holds more than the budget", r["peak"] <= r["budget"], r)
    check("live: the oldest data went, the newest of a stream that went quiet stayed", r["quietBefore"] == 42 and r["quietAfter"] == 42 and r["rows"] < 1_500_000, r)
    check("live: the JS heap comes back after the flood (growth under 32 MB)", r["heapGrowthMB"] < 32, r)
    page.evaluate("() => kit.setLiveBudget(256 * 2 ** 20)")


def connection_and_resume(page, base):
    page.wait_for_function("() => dash.datasets.sse.rowCount > 5", timeout=WAIT)
    st = lambda: page.evaluate("() => ({ line: document.querySelector('#dash data-live-status')?.dataset.state, sse: dash.datasets.sse.status.state })")
    check("live: the connection line reads live while rows arrive", st()["sse"] == "live" and st()["line"] == "live", st())
    urllib.request.urlopen(base + "/sse/pause").read()
    page.wait_for_function("() => dash.datasets.sse.status.state === 'stale'", timeout=6000)
    check("live: no data for longer than stale: (2 s) reads stale, on the dataset and on the line",
          page.evaluate("() => document.querySelector('#dash data-live-status').dataset.state") in ("stale",), st())
    urllib.request.urlopen(base + "/sse/resume").read()
    page.wait_for_function("() => dash.datasets.sse.status.state === 'live'", timeout=6000)
    page.evaluate("""() => { window.sseStates = []; dash.datasets.sse.addEventListener('status', () => sseStates.push(dash.datasets.sse.status.state)); }""")
    last_before = page.evaluate("() => dash.datasets.sse.latestAt(dash.datasets.sse.end).n")
    urllib.request.urlopen(base + "/sse/drop").read()
    page.wait_for_function(f"() => dash.datasets.sse.latestAt(dash.datasets.sse.end).n > {last_before} + 10", timeout=WAIT)
    log = json.loads(urllib.request.urlopen(base + "/sse/log").read())
    ns = page.evaluate("() => dash.datasets.sse.snapshot(dash.datasets.sse.end, { at: 'all', limit: 100000 }).map((r) => r.n).reverse()")
    gaps = [b for a, b in zip(ns, ns[1:]) if b != a + 1]
    states = page.evaluate("() => sseStates")
    check("live: an SSE drop reads reconnecting, then live", "reconnecting" in states and states[-1] == "live", states)
    check("live: the reconnect sent Last-Event-ID and the rows resume with no gap and no repeat",
          len(log["seen"]) >= 2 and log["seen"][-1].isdigit() and int(log["seen"][-1]) >= last_before and not gaps,
          {"seen": log["seen"][-3:], "gaps": gaps[:5], "n": [ns[0], ns[-1], len(ns)]})


def reload_live(browser, base):
    page = open_page(browser, base, "#t=live")
    check("live: a link with #t=live opens following", page.evaluate("() => dash.clock.following"))
    page.evaluate("() => stopFeed()")
    page.context.close()


def phone_width(browser, base):
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.goto(f"{base}/tests/browser/fixtures/live.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate("""() => new Promise((done) => { const d = document.createElement('data-dashboard'); d.id = 'dash';
      d.addEventListener('data-dashboard-live', () => done(), { once: true }); d.setAttribute('src', '/tests/browser/fixtures/live/live.base');
      document.body.append(d); window.dash = d; })""")
    page.evaluate(FEEDER)
    page.evaluate("() => startFeed()")
    page.wait_for_function("() => document.querySelector('#dash .dv-view-plot [data-playhead]')", timeout=WAIT)
    frames(page, 3)
    w = page.evaluate("() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth })")
    page.screenshot(path=str(OUT / "live-390.png"), full_page=True)
    check("live: at 390 px the live dashboard has no sideways scroll", w["scroll"] <= w["client"] + 1, w)
    page.evaluate("() => stopFeed()")
    context.close()


def ages_tick(browser, base):
    """a8: a time-derived cell (display: age) ticks with no new row, against the wall clock while following and holds
    against t while paused. A keyed dataset the check builds in the page: the 'heard' times of three checks."""
    context = browser.new_context(viewport={"width": 1100, "height": 700})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base}/tests/browser/fixtures/live.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate("""() => {
      const d = document.createElement('data-dashboard');
      d.id = 'ages'; d.setAttribute('no-url', '');
      document.body.append(d);
      const ds = new kit.LiveDataset({ id: 'heard', time: 't', key: 'name', properties: {
        name: { type: 'text', label: 'Check' }, t: { type: 'number', label: 'Heard', display: 'age' }, level: { type: 'text', label: 'Level' } } });
      d.load({ data: 'heard.json', datasets: { heard: { data: 'heard.json' } },
        layout: { columns: 12, rowHeight: 110, panels: [{ view: 'Heard', w: 12, h: 3 }] },
        views: [{ type: 'table', name: 'Heard', order: ['name', 't', 'level'] }] }, { heard: ds });
      const now = Date.now() / 1000;
      ds.upsert([{ name: 'motor', t: now, level: 'ok' }, { name: 'can', t: now - 5, level: 'warn' }]);
      window.ages = d; window.heard = ds;
    }""")
    read = """() => { const tr = [...document.querySelectorAll('#ages tbody tr[data-id]')].find((r) => r.dataset.id === 'motor');
      const td = tr && tr.querySelector('td[data-col="t"]'); return td ? td.textContent.trim() : null; }"""
    page.wait_for_function(f"() => ({read})() !== null", timeout=WAIT)
    first = page.evaluate(read)
    page.wait_for_timeout(2300)
    later = page.evaluate(read)
    num = lambda s: float(s.split()[0]) if s and s.split()[0].replace(".", "", 1).isdigit() else None
    check("live: a display: age cell ticks with no new row (\"0.0 s ago\" → about 2 s ago)", num(first) is not None and num(later) is not None
          and 1.6 <= num(later) - num(first) <= 3.2 and later.endswith("ago"), [first, later])
    page.evaluate("() => ages.clock.toggle()")   # Space: paused at t
    page.wait_for_timeout(300)
    held = page.evaluate(read)
    page.wait_for_timeout(1500)
    still = page.evaluate(read)
    check("live: paused, the age holds against t (it is the age at the clock's moment)", held == still and still is not None, [held, still])
    check("live: no script errors on the ages page", not errors, errors[:3])
    context.close()


PZ_PAGE = """() => {
  const d = document.createElement('data-dashboard');
  d.id = 'pz'; d.setAttribute('no-url', '');
  document.body.append(d);
  const num = (label) => ({ type: 'number', label }), text = (label) => ({ type: 'text', label });
  // RobotDx's three shapes: entities (keyed, no retention), the activity log (append), the summary (keyed, age retention)
  const state = new kit.LiveDataset({ id: 'state', time: 't', key: 'path', properties: { path: text('Path'), value: num('Value'), t: num('Time') } });
  const log = new kit.LiveDataset({ id: 'log', time: 't', properties: { t: num('Time'), source: text('Source'), n: num('N') } });
  const summary = new kit.LiveDataset({ id: 'summary', time: 't', key: 'host', retention: { age: 4 }, properties: { host: text('Host'), n: num('N'), t: num('Time') } });
  d.load({ data: 'state.json', datasets: { state: { data: 'state.json' }, log: { data: 'log.json' }, summary: { data: 'summary.json' } },
    layout: { columns: 12, rowHeight: 60, panels: [
      { view: 'State', w: 3, h: 5 }, { view: 'Log', w: 3, h: 5 }, { view: 'Recent', w: 3, h: 5 }, { view: 'Summary', w: 3, h: 5 },
      { view: 'Wave', w: 12, h: 3 }] },
    views: [
      { type: 'table', name: 'State', from: 'state', order: ['path', 'value', 't'] },
      { type: 'table', name: 'Log', from: 'log', order: ['t', 'source', 'n'], sort: [{ property: 't', direction: 'DESC' }] },
      { type: 'table', name: 'Recent', from: 'log', at: '5s', order: ['t', 'source', 'n'] },
      { type: 'table', name: 'Summary', from: 'summary', order: ['host', 'n', 't'] },
      { type: 'plot', name: 'Wave', from: 'log', at: '10s', plot: { y: ['n'] } }] }, { state, log, summary });
  const now = Date.now() / 1000;
  state.upsert(['p1', 'p2', 'p3'].map((path, i) => ({ path, value: i, t: now - 2 + i * 0.1 })));
  const rows = [];
  for (let i = 0; i < 40; i++) rows.push({ t: now - 4 + i * 0.1, source: 's' + (i % 3), n: i });
  log.append(rows);
  for (let i = 0; i < 40; i++) summary.upsert([{ host: 'rack', n: i, t: now - 10 + i * 0.25 }]);
  window.pz = d; window.pzSets = { state, log, summary };
  window.pzEl = (name) => document.querySelector(`#pz section[aria-label="${name}"] data-views`);
  // per panel: live draws (data-views-live) and full renders (data-views-render)
  window.pzDraws = {};
  window.pzZero = () => { for (const k of Object.keys(pzDraws)) pzDraws[k] = { live: 0, render: 0 }; };
  window.pzCount = () => JSON.parse(JSON.stringify(pzDraws));
  window.pzFrames = (n = 3) => new Promise((done) => { const step = (k) => (k ? requestAnimationFrame(() => step(k - 1)) : setTimeout(done, 60)); step(n); });
  window.pzN = (name) => { const m = pzEl(name).model; return m ? m.rows.map((r) => r.n) : null; };
  // the panels that should draw have drawn (a 3 s ceiling: one that never does reports FAIL), then 3 frames for any other
  window.pzSettle = async (names) => {
    const t0 = performance.now();
    while (performance.now() - t0 < 3000 && !names.every((n) => pzDraws[n].live + pzDraws[n].render > 0)) await pzFrames(1);
    await pzFrames(3);
  };
}"""

PZ_PANELS = ["State", "Log", "Recent", "Summary", "Wave"]


def paused_redraws_only_at_t(browser, base):
    """Paused, a view redraws only when what it shows at t can change (follow-up to bfc632f, found by the RobotDx lane:
    paused at t, every upsert to a keyed dataset redrew its views at the same t, 230-440 ms apart). Draws are counted per
    panel: data-views-live (a live draw) and data-views-render (a full render). Versions and rows after t draw nothing; a
    late version or row at or before t draws the panels whose window holds it, and only those, and they show it;
    retention taking older versions draws nothing, taking the record a view shows at t draws it once; the view's own
    filter still redraws it. Three datasets built in the page: keyed `state` (RobotDx's entities), append `log` (its
    activity log: a table of everything, a 5 s window, a 10 s plot) and keyed `summary` with age retention (its summary)."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/live.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(PZ_PAGE)
    page.wait_for_function("""() => ['State', 'Log', 'Recent', 'Summary', 'Wave'].every((n) => pzEl(n) && pzEl(n).model)
      && pzN('State').length === 3 && pzN('Summary').length === 1 && pz.clock.following""", timeout=WAIT)
    page.evaluate("""() => { for (const name of ['State', 'Log', 'Recent', 'Summary', 'Wave']) {
      const el = pzEl(name); pzDraws[name] = { live: 0, render: 0 };
      el.addEventListener('data-views-live', () => pzDraws[name].live++);
      el.addEventListener('data-views-render', () => pzDraws[name].render++);
    } }""")
    page.evaluate("() => pzFrames(3)")
    page.evaluate("() => pz.clock.toggle()")   # Space while following: paused at t
    page.evaluate("() => pzFrames(3)")
    at_t = page.evaluate("""() => ({ following: pz.clock.following, t: pz.clock.t, state: pzN('State'), summary: pzN('Summary'),
      shown: pzSets.summary.latestAt(pz.clock.t, 'rack').t })""")
    check("live, paused redraws: the page is paused at t with the records at t on screen", not at_t["following"]
          and at_t["state"] is not None and len(at_t["state"]) == 3 and at_t["summary"] == [39], at_t)
    t = at_t["t"]

    # 1. 1.5 s of news after t: a version of every record, a log row, a summary version, every 50 ms
    one = page.evaluate("""async (shown) => {
      const { state, log, summary } = pzSets;
      pzZero();
      const r0 = summary.rowCount;
      let k = 0, ups = 0;
      const t0 = performance.now();
      await new Promise((done) => {
        const id = setInterval(() => {
          const now = Date.now() / 1000;
          k++;
          state.upsert(['p1', 'p2', 'p3'].map((path, i) => ({ path, value: 100 * k + i, t: now })));
          log.append([{ t: now, source: 's' + (k % 3), n: 1000 + k }]);
          // WHY the guard: this phase's summary versions may only push out old ones, not yet the record at t
          if (now < shown + 4 - 0.6) { summary.upsert([{ host: 'rack', n: 1000 + k, t: now }]); ups++; }
          if (performance.now() - t0 > 1500) { clearInterval(id); done(); }
        }, 50);
      });
      await pzFrames(3);
      return { batches: k, summaryUpserts: ups, summaryDropped: r0 + ups - summary.rowCount, draws: pzCount(),
               t: pz.clock.t, end: pz.clock.liveEnd, state: pzN('State'), summary: pzN('Summary') };
    }""", at_t["shown"])
    d1 = one["draws"]
    check("live, paused redraws: 1.5 s of versions and rows after t — no panel draws (keyed, append, windowed, plot)",
          all(d1[n]["live"] == 0 and d1[n]["render"] == 0 for n in PZ_PANELS) and one["batches"] >= 10 and one["t"] == t,
          {"draws": d1, "batches": one["batches"], "t": [t, one["t"]], "end - t": round(one["end"] - t, 3)})
    check("live, paused redraws: the summary's retention took old versions meanwhile, and its record at t stays drawn",
          one["summaryDropped"] > 0 and d1["Summary"]["live"] == 0 and one["summary"] == [39],
          {"dropped": one["summaryDropped"], "upserts": one["summaryUpserts"], "draws": d1["Summary"], "shown": one["summary"]})

    # 2. late news, one write at a time: a version at t − 0.5, a log row at t − 0.2, a log row at t − 6
    late = page.evaluate("""async () => {
      const { state, log } = pzSets, t = pz.clock.t, out = {};
      pzZero();
      state.upsert([{ path: 'p1', value: 999, t: t - 0.5 }]);
      await pzSettle(['State']);
      out.version = { draws: pzCount(), state: pzEl('State').model.rows.map((r) => [r.path, r.value]) };
      pzZero();
      log.append([{ t: t - 0.2, source: 'late', n: 777 }]);
      await pzSettle(['Log', 'Recent', 'Wave']);
      out.row = { draws: pzCount(), log: pzN('Log'), recent: pzN('Recent') };
      pzZero();
      log.append([{ t: t - 6, source: 'late', n: 666 }]);
      await pzSettle(['Log', 'Wave']);
      out.old = { draws: pzCount(), log: pzN('Log'), recent: pzN('Recent'), want: log.snapshot(t, { at: 'all' }).map((r) => r.n).reverse() };
      return out;
    }""")
    v, r, o = late["version"], late["row"], late["old"]
    others = lambda d, names: all(d[n]["live"] == 0 and d[n]["render"] == 0 for n in names)
    check("live, paused redraws: a late version at t − 0.5 draws the keyed table, which shows it; nothing else draws",
          v["draws"]["State"]["live"] >= 1 and ["p1", 999] in v["state"] and others(v["draws"], ["Log", "Recent", "Summary", "Wave"]), v)
    check("live, paused redraws: a late row at t − 0.2 draws every panel whose window holds it, and they show it",
          all(r["draws"][n]["live"] >= 1 for n in ["Log", "Recent", "Wave"]) and others(r["draws"], ["State", "Summary"])
          and 777 in (r["log"] or []) and 777 in (r["recent"] or []), r)
    check("live, paused redraws: a late row at t − 6 draws the all-time table and the 10 s plot, not the 5 s window",
          o["draws"]["Log"]["live"] >= 1 and o["draws"]["Wave"]["live"] >= 1 and others(o["draws"], ["Recent", "State", "Summary"])
          and 666 not in (o["recent"] or []), o["draws"])
    check("live, paused redraws: the all-time table then shows exactly the rows at t (the late one in its place)",
          o["log"] is not None and sorted(o["log"]) == sorted(o["want"]) and 666 in o["log"],
          {"shown": len(o["log"] or []), "want": len(o["want"]), "has 666": 666 in (o["log"] or [])})

    # 3. the view's own inputs still redraw it while paused: a filter
    flt = page.evaluate("""async () => {
      pzZero();
      pzEl('Log').filters = 'source == "late"';
      await pzSettle(['Log']);
      const out = { draws: pzCount(), log: pzN('Log') };
      pzEl('Log').filters = null;
      await pzFrames(3);
      return out;
    }""")
    check("live, paused redraws: the view's own filter still redraws it at t", flt["draws"]["Log"]["render"] + flt["draws"]["Log"]["live"] >= 1
          and sorted(flt["log"] or []) == [666, 777], flt)

    # 4. retention reaches t: summary versions keep coming until end − 4 passes the record at t; it goes, the view draws
    four = page.evaluate("""async (shown) => {
      const { summary } = pzSets;
      pzZero();
      let k = 0;
      await new Promise((done) => {
        const id = setInterval(() => {
          const now = Date.now() / 1000;
          summary.upsert([{ host: 'rack', n: 2000 + ++k, t: now }]);
          if (now > shown + 4 + 0.3 || k > 60) { clearInterval(id); done(); }
        }, 250);
      });
      await pzFrames(3);
      return { draws: pzCount(), summary: pzN('Summary'), kept: summary.latestAt(pz.clock.t, 'rack') };
    }""", at_t["shown"])
    check("live, paused redraws: retention taking the record at t draws the view, which then shows nothing at t",
          four["draws"]["Summary"]["live"] == 1 and four["summary"] == [] and four["kept"] is None
          and others(four["draws"], ["State", "Log", "Recent", "Wave"]), four)
    check("live, paused redraws: no script errors", not errors, errors[:3])
    (OUT / "live-paused-draws.json").write_text(json.dumps({"after_t": one, "late": late, "filter": flt, "retention": four}, indent=1), encoding="utf-8")
    context.close()


def run(browser, base):
    page = open_page(browser, base)
    cdp = page.context.new_cdp_session(page)
    follows_on_open(page)
    page.screenshot(path=str(OUT / "live-following.png"), full_page=True)
    scrub_pauses_and_holds(page)
    paused_draws_nothing(page)
    page.screenshot(path=str(OUT / "live-paused.png"), full_page=True)
    back_to_live(page)
    frame_budget_while_streaming(page)
    plot_reduction_and_spike(page)
    tail_holds_and_resumes(page)
    keys_and_replay(page)
    levels_and_kpi(page)
    connection_and_resume(page, base)
    byte_budget_holds(page, cdp)
    page.evaluate("() => stopFeed()")
    check("live: no script errors", not page.errors, page.errors[:3])
    check("live: nothing loaded from another site", not page.foreign, page.foreign[:3])
    page.context.close()
    reload_live(browser, base)
    phone_width(browser, base)
    ages_tick(browser, base)
    paused_redraws_only_at_t(browser, base)


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists():
        print("dist/ is not built: npm --prefix ~/data-ui run build")
        return 1
    port = free_port()
    server = Server(("127.0.0.1", port), partial(Handler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/live.html", timeout=1)
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
        FEED.stop = True
        with FEED.lock:
            FEED.lock.notify_all()
        server.shutdown()
        server.server_close()
    (OUT / "live-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    soft = [c["name"] for c in checks if c.get("soft")]
    print(f"{passed}/{len(checks)} live checks pass; screenshots in {OUT}")
    if soft:
        print(f"{len(soft)} speed budget(s) not enforced: the machine was overloaded (SOFT above): " + "; ".join(soft))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
