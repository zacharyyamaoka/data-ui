"""The lifecycle checks: what an element owns is released when it leaves the page and made again when it comes back,
and async work never lands late; and the views' own extents hold on 150,000 rows. Measured in headless Chromium on
tests/browser/fixtures/lifecycle.html.

    ~/psu-atlas/.venv/bin/python tests/browser/lifecycle_checks.py [OUT_DIR]     # after npm run build

From the RISK findings of the 2026-10-26 performance review (reports/media/audits/2026-10-26-data-ui-performance-
findings.md). Every wait is on a state the page reaches (a drawn row, a settled promise, a counter), never a fixed
sleep, so machine load slows these checks down but cannot flip them. Serves the repo root on a free 127.0.0.1 port,
stops it when done, writes OUT_DIR/lifecycle-checks.json (default reports/media/lifecycle) and exits 1 if any check
fails. Kept out of tests/browser/checks.py so a lane editing that file never meets this one (tools/test-all.mjs runs
it).
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "lifecycle"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
ACTUATORS = "/gallery/examples/robotparts-actuators/views.base"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_page(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


def views_removed_and_readded(browser, base):
    """<data-views> removed from the page: its plugin is destroyed and its document listeners go; put back: the view,
    the document listeners and the theme watch are made again, once."""
    page = open_page(browser, base)
    page.evaluate(f"""() => {{
      window.before = liveDocListeners();
      const el = document.createElement('data-views');
      el.id = 'v'; el.setAttribute('src', '{ACTUATORS}'); el.setAttribute('no-url', '');
      window.v = el;
      document.body.append(el);
    }}""")
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-i]')", timeout=WAIT)
    got = page.evaluate("""() => {
      const el = window.v;
      const first = liveDocListeners();
      const plugin = el._plugin;
      window.oldPlugin = plugin;
      window.destroyed = 0;
      const destroy = plugin.destroy.bind(plugin);
      plugin.destroy = () => { window.destroyed++; return destroy(); };
      el.remove();
      return { before, first, after: liveDocListeners(), destroyed: window.destroyed, plugin: el._plugin === null };
    }""")
    check("data-views removed: its view plugin is destroyed once, and every document listener it added is removed",
          got["destroyed"] == 1 and got["plugin"] and got["after"] == got["before"] and got["first"] != got["before"], got)

    page.evaluate("() => document.body.append(window.v)")
    page.wait_for_function("() => { const el = window.v; return el._plugin && el._plugin !== window.oldPlugin && el.querySelector('.dv-view tbody tr[data-i]'); }", timeout=WAIT)
    again = page.evaluate("""() => {
      const el = window.v;
      return { listeners: liveDocListeners(), rows: el.querySelectorAll('.dv-view tbody tr[data-i]').length, status: el.querySelector('.dv-status').textContent, view: el.dataset.view };
    }""")
    check("data-views put back: a new view draws the rows, with the same document listeners as the first time (not twice)",
          again["listeners"] == got["first"] and again["rows"] > 0 and "of 1,149 rows" in again["status"] and again["view"] == "table",
          {"first": got["first"], "again": again["listeners"], "rows": again["rows"], "status": again["status"][:40]})

    # the document's Esc still closes the peek, and a theme flip on <html> still redraws
    page.evaluate("() => { const el = window.v; el.openPeek(el.model.rows[0].id); }")
    page.wait_for_function("() => !document.querySelector('#v .dv-peek').hidden", timeout=WAIT)
    page.evaluate("() => document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    closed = page.evaluate("() => document.querySelector('#v .dv-peek').hidden")
    page.evaluate("""() => { window.redraws = 0; window.v.addEventListener('data-views-render', () => window.redraws++);
      document.documentElement.setAttribute('data-theme', 'dark'); }""")
    try:
        page.wait_for_function("() => window.redraws > 0", timeout=WAIT)
        redrawn = True
    except Exception:
        redrawn = False
    check("data-views put back: Esc on the page closes its peek, and a dark theme on <html> redraws it in the new tokens",
          closed and redrawn, {"peek closed": closed, "redrawn on theme": redrawn})
    errors = page.errors
    page.context.close()
    return errors


def bar_removed_and_readded(browser, base):
    """toolbar="bar" (CONTRACT §15) under frame="bleed", with its rail, the View settings panel open and a selection:
    removed, every document listener, window listener and ResizeObserver it made is released; put back, the bar, its
    query box, the settings and the view are made again, once, and '/' and Esc still work."""
    page = open_page(browser, base)
    page.evaluate(f"""() => {{
      // window listeners and ResizeObservers, live, from here on (the fixture counts the document's)
      window.winListeners = new Map();
      const wadd = window.addEventListener.bind(window), wremove = window.removeEventListener.bind(window);
      window.addEventListener = (type, fn, opts) => {{ if (!winListeners.has(type)) winListeners.set(type, new Set()); winListeners.get(type).add(fn); return wadd(type, fn, opts); }};
      window.removeEventListener = (type, fn, opts) => {{ if (winListeners.has(type)) winListeners.get(type).delete(fn); return wremove(type, fn, opts); }};
      window.liveWinListeners = () => Object.fromEntries([...winListeners].map(([t, s]) => [t, s.size]).filter(([, n]) => n));
      window.liveObservers = new Set();
      const RO = window.ResizeObserver;
      window.ResizeObserver = class extends RO {{ constructor(cb) {{ super(cb); this.targets = []; liveObservers.add(this); }}
        observe(t, o) {{ this.targets.push(t); return super.observe(t, o); }} disconnect() {{ liveObservers.delete(this); return super.disconnect(); }} }};
      // observers still watching something inside the element (or the element): what it should have let go
      window.mine = () => [...liveObservers].filter((o) => o.targets.some((t) => t === window.b || window.b.contains(t))).length;
      // window listeners of the page's other parts (the rail's drag handle) stay; the element's own must go
      window.before = {{ doc: liveDocListeners(), win: liveWinListeners() }};
      const el = document.createElement('data-views');
      el.id = 'b'; el.setAttribute('src', '{ACTUATORS}'); el.setAttribute('no-url', '');
      for (const [k, v] of Object.entries({{ toolbar: 'bar', views: 'auto', filters: 'pills rail', display: 'panel', selectable: '', frame: 'bleed' }})) el.setAttribute(k, v);
      const rail = document.createElement('data-facets'); rail.setAttribute('for', 'b');
      window.b = el;
      document.body.append(rail, el);
    }}""")
    page.wait_for_function("() => document.querySelector('#b .dv-view tbody tr[data-i]') && document.querySelector('#b .dv-bar [data-bar=display]')", timeout=WAIT)
    # with a record open in open modes' split pane too (CONTRACT §13): both features let go together
    page.evaluate("() => { const el = window.b; el.openPeek(el.model.rows[0].id); el.select(el.model.rows.slice(0, 2).map((r) => r.id)); el.querySelector('.dv-bar [data-bar=display]').click(); }")
    page.wait_for_function("() => !document.querySelector('#b .dv-settings').hidden && window.b.classList.contains('dv-split')", timeout=WAIT)
    first = page.evaluate("() => ({ doc: liveDocListeners(), win: liveWinListeners(), observers: mine() })")
    page.evaluate("() => { window.oldBar = window.b._barUi; window.b.remove(); }")
    gone = page.evaluate("""() => ({ doc: liveDocListeners(), win: liveWinListeners(), observers: mine(),
      ui: ['_barUi', '_queryUi', '_settingsUi', '_bulkUi'].filter((k) => window.b[k]) })""")
    # WHY resize <= 1 left: the rail stays in the page, and its own drag handle keeps its one window resize listener
    check("bar removed (a record open in the split pane, View settings open): every document listener, window scroll listener and ResizeObserver its bar, query box, bulk bar, View settings, frame and open modes made is released (the rail's handle keeps its one resize listener)",
          gone["doc"] == page.evaluate("() => before.doc") and not gone["win"].get("scroll") and not gone["win"].get("popstate") and gone["win"].get("resize", 0) <= 1 and not gone["ui"]
          and first["observers"] > 0 and gone["observers"] == 0,
          {"before": page.evaluate("() => before"), "open": first, "removed": gone})
    page.evaluate("() => document.body.append(window.b)")
    page.wait_for_function("() => { const el = window.b; return el._barUi && el._barUi !== window.oldBar && el.querySelector('.dv-view tbody tr[data-i]') && el.querySelector('.dv-bar [data-bar=display]'); }", timeout=WAIT)
    page.evaluate("() => { const el = window.b; el.openPeek(el.model.rows[0].id); el.querySelector('.dv-bar [data-bar=display]').click(); }")
    page.wait_for_function("() => !document.querySelector('#b .dv-settings').hidden && window.b.classList.contains('dv-split')", timeout=WAIT)
    again = page.evaluate("() => ({ doc: liveDocListeners(), win: liveWinListeners(), settings: document.querySelectorAll('#b .dv-settings').length, bars: document.querySelectorAll('#b .dv-bar').length, frame: window.b.dataset.scroll || null })")
    page.evaluate("() => document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    closed = page.evaluate("() => document.querySelector('#b .dv-settings').hidden")
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); document.body.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })); }")
    slash = page.evaluate("() => !!(document.activeElement && document.activeElement.closest('#b .dv-bar-query'))")
    check("bar put back (a record opened again): one bar and one View settings again, the same document and window listeners as the first time, still framed; Esc closes the settings and '/' focuses its query box",
          again["doc"] == first["doc"] and again["win"] == first["win"] and again["settings"] == 1 and again["bars"] == 1 and again["frame"] == "page" and closed and slash,
          {"first": first, "again": again, "esc closed": closed, "/ focused": slash})
    errors = page.errors
    page.context.close()
    return errors


def rail_removed_and_readded(browser, base):
    """<data-facets> attached, removed, attached again: its own four handlers once, one data-views-change listener."""
    page = open_page(browser, base)
    page.evaluate(f"""() => {{
      const v = document.createElement('data-views');
      v.id = 'v'; v.setAttribute('src', '{ACTUATORS}'); v.setAttribute('no-url', '');
      const rail = document.createElement('data-facets');
      rail.setAttribute('for', 'v');
      // count what the rail adds to itself, and what is listening on its target
      window.own = [];
      const add = rail.addEventListener.bind(rail);
      rail.addEventListener = (type, fn, opts) => {{ own.push(type); return add(type, fn, opts); }};
      window.onTarget = new Set();
      const tadd = v.addEventListener.bind(v), tremove = v.removeEventListener.bind(v);
      v.addEventListener = (type, fn, opts) => {{ if (type === 'data-views-change') onTarget.add(fn); return tadd(type, fn, opts); }};
      v.removeEventListener = (type, fn, opts) => {{ if (type === 'data-views-change') onTarget.delete(fn); return tremove(type, fn, opts); }};
      window.v = v; window.rail = rail;
      document.body.append(rail, v);
    }}""")
    page.wait_for_function("() => window.v.model && window.rail.querySelector('details') && window.rail.querySelector('input[type=checkbox]')", timeout=WAIT)
    first = page.evaluate("() => ({ own: own.length, onTarget: onTarget.size })")
    page.evaluate("() => { rail.remove(); rail.innerHTML = ''; document.body.prepend(rail); }")
    page.wait_for_function("() => window.rail.querySelector('input[type=checkbox]')", timeout=WAIT)
    again = page.evaluate("() => ({ own: own.slice().sort(), onTarget: onTarget.size })")
    check("data-facets attached, removed and attached again: its change, input, click and keydown handlers are added once (4, not 8), one listener on its <data-views>",
          first["own"] == 4 and again["own"] == ["change", "click", "input", "keydown"] and again["onTarget"] == 1, {"first": first, "again": again})
    page.evaluate("() => { window.changes = 0; v.addEventListener('data-views-change', () => changes++); rail.querySelector('input[type=checkbox]').click(); }")
    page.wait_for_function("() => window.changes > 0 && !window.v.querySelector('.dv-status').textContent.startsWith('1,149 of')", timeout=WAIT)
    after = page.evaluate("() => ({ changes, status: v.querySelector('.dv-status').textContent, filters: JSON.stringify(v.filters) })")
    check("data-facets attached again: one tick filters its <data-views> once", after["changes"] == 1 and "of 1,149 rows" in after["status"], after)
    errors = page.errors
    page.context.close()
    return errors


def older_fetch_lands_late(browser, base):
    """data= changed twice; the first file answers after the second: the second file's rows stay."""
    page = open_page(browser, base)
    page.evaluate("""() => {
      const dataset = (title, n) => new Response(JSON.stringify({ title, rows: Array.from({ length: n }, (_, i) => ({ id: `${title}${i}`, name: `${title} ${i}` })) }));
      const real = window.fetch;
      window.oldAborted = false;
      // race-old.json answers only when the check releases it (or rejects, as fetch does, when its request is aborted)
      window.fetch = (url, opts = {}) => {
        const u = String(url);
        if (u.endsWith('/race-old.json')) return new Promise((resolve, reject) => {
          window.releaseOld = () => resolve(dataset('Old', 3));
          if (opts.signal) opts.signal.addEventListener('abort', () => { window.oldAborted = true; reject(new DOMException('The request was aborted', 'AbortError')); });
        });
        if (u.endsWith('/race-new.json')) return Promise.resolve(dataset('New', 5));
        return real(url, opts);
      };
      const v = document.createElement('data-views');
      v.setAttribute('no-url', '');
      v.base = { views: [{ type: 'table', name: 'Rows' }] };
      window.v = v;
      document.body.append(v);
      v.setAttribute('data', 'race-old.json');
      window.first = v._loading;
      v.setAttribute('data', 'race-new.json');
      window.second = v._loading;
    }""")
    got = page.evaluate("""async () => {
      await second;
      const drawnNew = v.data && v.data.title;
      if (window.releaseOld) releaseOld();
      await first;
      return { drawnNew, title: v.data && v.data.title, aborted: oldAborted, error: !!v.querySelector('.dv-err') };
    }""")
    page.wait_for_function("() => /of \\d+ rows/.test((window.v.querySelector('.dv-status') || {}).textContent || '')", timeout=WAIT)
    status = page.evaluate("() => window.v.querySelector('.dv-status').textContent")
    check("data-views: an older data= request that answers after a newer one never replaces the newer rows (and is aborted)",
          got["drawnNew"] == "New" and got["title"] == "New" and got["aborted"] and "5 of 5 rows" in status and not got["error"], {**got, "status": status})
    errors = page.errors
    page.context.close()
    return errors


def chart_coalesces_and_cancels(browser, base):
    """The chart view: 20 updates in one go draw once, from the last input; destroyed with a draw in flight and another
    queued, nothing more draws into it."""
    page = open_page(browser, base)
    page.evaluate("""() => {
      const v = document.createElement('data-views');
      v.setAttribute('src', '/gallery/examples/actuator-charts/views.base'); v.setAttribute('view', 'Torque vs mass'); v.setAttribute('no-url', '');
      window.v = v;
      document.body.append(v);
    }""")
    page.wait_for_function("() => window.v.dataset.view === 'chart' && window.v.querySelector('.dv-view-chart canvas')", timeout=WAIT)
    got = page.evaluate("""async () => {
      const chart = v._plugin;
      await chart._job;
      // only the updates below ask for a draw (the plot's ResizeObserver would add its own)
      chart._resize.disconnect();
      clearTimeout(chart._resizeTimer);
      const draws = [];
      let started = () => {};
      const draw = chart._draw.bind(chart);
      chart._draw = () => { draws.push(chart.input); started(); return draw(); };
      const inputs = Array.from({ length: 20 }, () => v._input());
      let last;
      for (const x of inputs) last = chart.update(x);
      await last;
      const burst = { draws: draws.length, fromLast: draws[draws.length - 1] === inputs[19] };
      draws.length = 0;
      chart._key = null; // the next draw embeds again: the long, awaited path
      const begun = new Promise((r) => { started = r; });
      const errors = [];
      const inflight = chart.update(v._input()).catch((e) => errors.push(String(e)));
      await begun;
      const queued = chart.update(v._input()).catch((e) => errors.push(String(e)));
      chart.destroy();
      delete chart.el.dataset.drawn;
      chart.el.vegaView = undefined;
      await inflight;
      await queued;
      return { ...burst, afterDestroy: draws.length, drawn: chart.el.dataset.drawn ?? null, vega: !!chart.el.vegaView, html: chart.el.innerHTML.length, errors };
    }""")
    check("chart: 20 updates in one go draw once, from the last input (it drew 20 times)", got["draws"] == 1 and got["fromLast"], {"draws": got["draws"], "from the last input": got["fromLast"]})
    check("chart: destroyed with one draw in flight and one queued, the queued one never starts and the in-flight one draws nothing into the destroyed view",
          got["afterDestroy"] == 1 and got["drawn"] is None and not got["vega"] and got["html"] == 0 and not got["errors"],
          {k: got[k] for k in ("afterDestroy", "drawn", "vega", "html", "errors")})
    errors = page.errors
    page.context.close()
    return errors


def views_on_150k_rows(browser, base):
    """The views' own extents on 150,000 rows: Math.min(...rows) overflows the stack past ~120k arguments, so the
    chart's log-scale test, the map's bounds, the sparkline's scale and the timeline's lanes take them with a loop.
    The view bundles' pure parts, called directly (the facets' extents are tests/unit/rail-large.test.mjs)."""
    page = open_page(browser, base)
    got = page.evaluate("""async () => {
      const N = 150000;
      const run = async (name, fn) => { try { return [name, await fn()]; } catch (e) { return [name, 'threw: ' + e.message]; } };
      const rows = Array.from({ length: N }, (_, i) => ({ id: `r${i}`, mass: 1 + (i % 1000), torque: 0.5 + i, at: `2026-01-01`, g: 'all' }));
      const columns = { mass: { id: 'mass', type: 'number', label: 'Mass' }, torque: { id: 'torque', type: 'number', label: 'Torque' }, at: { id: 'at', type: 'date', label: 'At' }, g: { id: 'g', type: 'text', label: 'G' } };
      const tokens = kit.resolveTokens(document.body);
      const dataset = { id: 'big', title: 'Big', titleProperty: 'id' };
      return Object.fromEntries(await Promise.all([
        run('chart', async () => {
          const { compile } = await import('/dist/views/chart.js');
          const view = { type: 'chart', name: 'c', chart: { mark: 'point', encoding: { x: { field: 'mass' }, y: { field: 'torque' } } } };
          const out = compile({ rows, columns, view, tokens, dataset }, { whole: rows });
          return { y: out.spec.encoding ? (out.spec.encoding.y.scale || {}).type : JSON.stringify(out.spec).includes('"log"') ? 'log' : null };
        }),
        run('map', async () => {
          const MapView = (await import('/dist/views/map.js')).default;
          let bounds = null;
          const stub = { map: { fitBounds: (b) => { bounds = b; }, jumpTo() {} }, el: { clientWidth: 800 } };
          MapView.prototype._frame.call(stub, {}, rows.map((r, i) => ({ lng: -170 + (i % 340), lat: -80 + (i % 160) })));
          return bounds;
        }),
        run('sparkline', async () => {
          const { sparkSvg } = await import('/dist/views/kpi.js');
          return sparkSvg(rows.map((r) => ({ y: r.torque }))).startsWith('<svg');
        }),
        run('timeline', async () => {
          const { toTimeline } = await import('/dist/views/timeline.js');
          const view = { type: 'timeline', name: 't', start: 'at', groupBy: { property: 'g' }, subGroupBy: { property: 'id' } };
          const groups = [{ property: 'g', key: 'all', rows, groups: rows.map((r) => ({ property: 'id', key: r.id, rows: [r] })) }];
          const out = toTimeline({ rows, columns, view, tokens, dataset, groups });
          return out.groups.length;
        }),
      ]));
    }""")
    check("chart: the log-scale test reads 150,000 rows' extent with a loop (torque spans 6 decades: log)", got["chart"] == {"y": "log"}, got["chart"])
    check("map: the bounds of 150,000 points, with a loop", got["map"] == [[-170, -80], [169, 79]], got["map"])
    check("kpi: a sparkline of 150,000 points draws", got["sparkline"] is True, got["sparkline"])
    check("timeline: 150,000 sub-group lanes under one group", got["timeline"] == 150001, got["timeline"])
    errors = page.errors
    page.context.close()
    return errors


# what an element holds outside itself and outside the document: window listeners (popstate, resize), MediaQueryList
# listeners and ResizeObserver targets, live (added minus removed; a disconnect() drops all of an observer's targets)
HELD = """(() => {
  const live = { window: new Map(), media: 0, observed: 0 };
  const add = EventTarget.prototype.addEventListener, remove = EventTarget.prototype.removeEventListener;
  const isMedia = (t) => typeof MediaQueryList !== 'undefined' && t instanceof MediaQueryList;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    if (this === window) { if (!live.window.has(type)) live.window.set(type, new Set()); live.window.get(type).add(fn); }
    else if (isMedia(this)) { this.__dvFns = this.__dvFns || new Set(); if (!this.__dvFns.has(fn)) { this.__dvFns.add(fn); live.media++; } }
    return add.call(this, type, fn, opts);
  };
  EventTarget.prototype.removeEventListener = function (type, fn, opts) {
    if (this === window && live.window.has(type)) live.window.get(type).delete(fn);
    else if (isMedia(this) && this.__dvFns && this.__dvFns.delete(fn)) live.media--;
    return remove.call(this, type, fn, opts);
  };
  const RO = window.ResizeObserver;
  window.ResizeObserver = class extends RO {
    constructor(cb) { super(cb); this.__dvTargets = new Set(); }
    observe(t, o) { if (!this.__dvTargets.has(t)) { this.__dvTargets.add(t); live.observed++; } return super.observe(t, o); }
    unobserve(t) { if (this.__dvTargets.delete(t)) live.observed--; return super.unobserve(t); }
    disconnect() { live.observed -= this.__dvTargets.size; this.__dvTargets.clear(); return super.disconnect(); }
  };
  window.heldNow = () => ({ window: Object.fromEntries([...live.window].map(([t, s]) => [t, s.size]).filter(([, n]) => n)), media: live.media, observed: live.observed,
    document: window.liveDocListeners ? liveDocListeners() : null });
})()"""


def open_modes_removed_and_readded(browser, base, cycles=5):
    """<data-views> with the side pane open (split) and an expand band open, removed and put back `cycles` times: what
    open modes holds outside the element (popstate, the phone query, the element's and the pane's ResizeObservers, a
    page scroller's scroll) is released each time it leaves and made once when it is back, and the pane still works."""
    context = browser.new_context(viewport={"width": 1500, "height": 900})
    context.add_init_script(HELD)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(f"""() => {{
      window.empty = heldNow();
      const el = document.createElement('data-views');
      el.id = 'v'; el.setAttribute('src', '{ACTUATORS}'); el.setAttribute('view', 'Expand in place');
      window.v = el;
      document.body.append(el);
    }}""")
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-id]')", timeout=WAIT)
    # both surfaces open: a band under the second row (open: expand), and the side pane on the first (split at 1468 px)
    opened = """() => { const el = window.v; const rows = [...el.querySelectorAll('tbody tr.dv-row[data-id]')];
      if (!el.querySelector('tr.dv-open-band')) rows[1].querySelector('td:nth-child(4)').click();
      el.openPeek(rows[0].dataset.id);
      return { band: !!el.querySelector('tr.dv-open-band'), split: el.classList.contains('dv-split'), peek: !el.querySelector('.dv-peek').hidden }; }"""
    first = page.evaluate(opened)
    page.wait_for_function("() => window.v.querySelector('tr.dv-open-band')", timeout=WAIT)
    attached = page.evaluate("heldNow()")
    gone, back, states = [], [], []
    for i in range(cycles):
        gone.append(page.evaluate("() => { window.v.remove(); return heldNow(); }"))
        page.evaluate("() => document.body.append(window.v)")
        page.wait_for_function("() => window.v._plugin && window.v.querySelector('.dv-view tbody tr[data-id]')", timeout=WAIT)
        states.append(page.evaluate(opened))
        page.wait_for_function("() => window.v.querySelector('tr.dv-open-band')", timeout=WAIT)
        back.append(page.evaluate("heldNow()"))
    check(f"open modes: a <data-views> with the side pane and an expand band open, removed {cycles} times, holds nothing outside itself each time (window, media-query and ResizeObserver counts back to the empty page's)",
          all(g["window"] == gone[0]["window"] and g["media"] == empty_media(page) and g["observed"] == gone[0]["observed"] for g in gone)
          and gone[0]["window"] == page.evaluate("window.empty.window") and gone[0]["observed"] == page.evaluate("window.empty.observed"),
          {"empty page": page.evaluate("window.empty"), "attached": attached, "removed (1st, last)": [gone[0], gone[-1]]})
    check(f"open modes: put back {cycles} times, it holds what it held the first time, not more (no listener or observer piles up)",
          all(b == attached for b in back), {"first": attached, "after each put-back": back})
    # the re-armed listeners work: the split pane follows the element, Back closes a pane that was pushed
    page.evaluate("() => { const el = window.v; el.closePeek(); el.openPeek(el.querySelector('tbody tr.dv-row[data-id]').dataset.id); }")
    page.wait_for_function("() => !window.v.querySelector('.dv-peek').hidden && location.hash.includes('peek=')", timeout=WAIT)
    page.set_viewport_size({"width": 1000, "height": 900})
    page.wait_for_function("() => !window.v.classList.contains('dv-split')", timeout=WAIT)
    page.evaluate("() => history.back()")
    page.wait_for_function("() => window.v.querySelector('.dv-peek').hidden", timeout=WAIT)
    check(f"open modes: after {cycles} put-backs the pane still works (it opened split, a narrower window made it an overlay, Back closed it), and so did both surfaces each time",
          first["band"] and first["split"] and first["peek"] and all(s["band"] and s["peek"] and s["split"] for s in states), {"first": first, "each put-back": states})
    errors = page.errors
    page.context.close()
    return errors


RACK = "/gallery/examples/rack-wiring/views.base"


def peek_trail_removed_and_readded(browser, base, cycles=5):
    """The peek's trail (amendment 2026-10-26 (time groups and peek trail)): a <data-views> showing a 3-record trail,
    removed and put back `cycles` times, holds nothing outside itself each time and no more than the first time when
    back; the trail still follows a relation after each put-back; and a record with no page URL has no ⤢."""
    context = browser.new_context(viewport={"width": 1500, "height": 900})
    context.add_init_script(HELD)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(f"""() => {{
      window.empty = heldNow();
      const el = document.createElement('data-views');
      el.id = 'v'; el.setAttribute('src', '{RACK}'); el.setAttribute('view', 'Parts');
      window.v = el;
      document.body.append(el);
    }}""")
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-id=psu]')", timeout=WAIT)
    # supply -> clamp -> XT30 junction through the peek's own relation links, as a reader clicks them
    walk = """async () => { const el = window.v; const wait = (id) => new Promise((done) => { const t = () => (el.querySelector('.dv-peek .dv-open-rec')?.dataset.id === id ? done() : requestAnimationFrame(t)); t(); });
      el.closePeek(); el.openPeek('psu'); await wait('psu');
      for (const id of ['clamp', 'xt30_junction']) { el.querySelector(`.dv-peek .dv-fields a[data-open-rel="${id}"]`).click(); await wait(id); }
      return [...el.querySelectorAll('.dv-peek .dv-open-trail li button, .dv-peek .dv-open-trail [aria-current]')].map((n) => n.textContent.trim()).length; }"""
    first = page.evaluate(walk)
    attached = page.evaluate("heldNow()")
    gone, back, trails = [], [], []
    for _ in range(cycles):
        gone.append(page.evaluate("() => { window.v.remove(); return heldNow(); }"))
        page.evaluate("() => document.body.append(window.v)")
        page.wait_for_function("() => window.v._plugin && window.v.querySelector('.dv-view tbody tr[data-id]')", timeout=WAIT)
        trails.append(page.evaluate(walk))
        back.append(page.evaluate("heldNow()"))
    check(f"peek trail: a <data-views> with a 3-record trail open, removed {cycles} times, holds nothing outside itself each time (window, media-query and ResizeObserver counts back to the empty page's)",
          all(g["window"] == page.evaluate("window.empty.window") and g["media"] == empty_media(page) and g["observed"] == page.evaluate("window.empty.observed") for g in gone),
          {"empty page": page.evaluate("window.empty"), "attached": attached, "removed (1st, last)": [gone[0], gone[-1]]})
    check(f"peek trail: put back {cycles} times, it holds what it held the first time, and the trail still follows the wires to 3 crumbs",
          all(b == attached for b in back) and first == 3 and trails == [3] * cycles, {"first": attached, "after each put-back": back, "crumbs": [first, *trails]})
    expand = page.evaluate("""async () => {
      const before = location.hash; // the other element's peek= and trail=; a no-url element must leave them alone
      const el = document.createElement('data-views');
      el.id = 'nourl'; el.setAttribute('no-url', '');
      document.body.append(el);
      el.base = { views: [{ type: 'table', name: 'T', edges: { property: 'next' } }] };
      el.data = { id: 'chain', titleProperty: 'name', properties: { name: { type: 'text' }, next: { type: 'text', relation: true } },
        rows: [{ id: 'a', name: 'A', next: 'b' }, { id: 'b', name: 'B', next: null }] };
      await new Promise((done) => { const t = () => (el.querySelector('tbody tr[data-id=a]') ? done() : requestAnimationFrame(t)); t(); });
      el.openPeek('a');
      const rel = el.querySelector('.dv-peek .dv-fields a[data-open-rel=b]');
      rel.click();
      const out = { expand: !!el.querySelector('.dv-peek a.dv-open-expand'), shown: el.querySelector('.dv-peek .dv-open-rec').dataset.id, href: rel.getAttribute('href'), sameHash: location.hash === before };
      el.remove();
      return out;
    }""")
    check("peek trail: a record with no page URL has no ⤢; its relation links still follow in the peek (and no-url leaves the URL alone)",
          expand["expand"] is False and expand["shown"] == "b" and expand["href"] == "#" and expand["sameHash"], expand)
    errors = page.errors
    page.context.close()
    return errors


def empty_media(page):
    return page.evaluate("window.empty.media")


# every Worker the page makes, live (made minus terminated), from the first script on the page
WORKERS = """(() => {
  const W = window.Worker;
  window.workers = { made: 0, live: 0 };
  window.Worker = class extends W {
    constructor(...args) { super(...args); workers.made++; workers.live++; }
    terminate() { if (!this.__ended) { this.__ended = true; workers.live--; } return super.terminate(); }
  };
})()"""


def views_worker_removed_and_readded(browser, base):
    """<data-views> over 60,000 rows makes a row-model worker; removed from the page, the worker is terminated (no
    live Worker is left, with its copy of the rows); put back, a new one is made, takes the data and answers a sort."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(WORKERS)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate("""() => {
      const rows = Array.from({ length: 60000 }, (_, i) => ({ id: 'r' + i, name: 'part ' + (i % 997), n: (i * 7919) % 60013 }));
      const v = document.createElement('data-views');
      v.id = 'big'; v.setAttribute('no-url', '');
      v.base = { views: [{ type: 'table', name: 'All', order: ['name', 'n'], sort: [{ property: 'n', direction: 'DESC' }] }] };
      document.body.append(v);
      v.data = { properties: { name: { type: 'text' }, n: { type: 'number' } }, rows };
      window.big = v;
    }""")
    page.wait_for_function("() => big.querySelector('.dv-view tbody tr.dv-row') && big._rm && big._rm.ready", timeout=120000)
    attached = page.evaluate("() => ({ ...workers })")
    gone = page.evaluate("() => { big.remove(); return { ...workers, rm: big._rm }; }")
    check("data-views (60,000 rows) removed: its row-model worker is terminated, no Worker is left live",
          attached == {"made": 1, "live": 1} and gone["live"] == 0 and gone["rm"] is None, {"attached": attached, "removed": gone})
    page.evaluate("() => document.body.append(big)")
    page.wait_for_function("() => big._rm && big._rm.ready && big.querySelector('.dv-view tbody tr.dv-row')", timeout=120000)
    back = page.evaluate("""async () => {
      const done = new Promise((r) => big.addEventListener('data-views-render', r, { once: true }));
      big.setView({ sort: [{ property: 'n', direction: 'ASC' }] });
      await done;
      const m = performance.getEntriesByName('data-ui:model').filter((e) => e.detail && e.detail.worker).pop();
      const rows = big.model.rows;
      return { ...workers, worker: !!m, first: rows[0].n, ascending: rows.length === 60000 && rows.every((r, i) => i === 0 || rows[i - 1].n <= r.n) };
    }""")
    check("data-views put back: one new worker (two made, one live) takes the rows and answers the next sort (n ascending from 0)",
          back["made"] == 2 and back["live"] == 1 and back["worker"] and back["first"] == 0 and back["ascending"], back)
    errors = page.errors
    context.close()
    return errors


def run(browser, base):
    errors = []
    errors += open_modes_removed_and_readded(browser, base)
    errors += peek_trail_removed_and_readded(browser, base)
    errors += views_removed_and_readded(browser, base)
    errors += bar_removed_and_readded(browser, base)
    errors += rail_removed_and_readded(browser, base)
    errors += older_fetch_lands_late(browser, base)
    errors += chart_coalesces_and_cancels(browser, base)
    errors += views_on_150k_rows(browser, base)
    errors += views_worker_removed_and_readded(browser, base)
    check("lifecycle checks: no script errors", not errors, errors[:3])


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
            run(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "lifecycle-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} lifecycle checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
