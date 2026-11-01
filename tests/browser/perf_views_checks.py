"""The view-side performance changes (lane/perf-views, review 2026-10-26 items 7 and 8), proved unchanged in output.

    ~/psu-atlas/.venv/bin/python tests/browser/perf_views_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/lifecycle.html, dist/, gallery/), stops it when
done, writes OUT_DIR/perf-views-checks.json (default reports/media/perf-r2) and exits 1 if any check fails.

The oracle for the table's keyed rows is the table's own full redraw: after every scroll step the tbody the keyed draw
left behind must equal, byte for byte, the tbody a from-scratch draw makes for the same window. So a row kept from the
last frame can never differ from what a fresh draw would show (rows, order, parity, spacers, marks, bands). Every other
claim is a number read from the page (a node's identity, a request, getBoundingClientRect), never a class's presence.
Kept out of tests/browser/checks.py so a lane editing that file never meets this one (tools/test-all.mjs runs both).
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "perf-r2"
OUT.mkdir(parents=True, exist_ok=True)
ACTUATORS = "/gallery/examples/robotparts-actuators/views.base"
PHOTOS = "/gallery/examples/robotparts-photos/views.base"
KPIS = "/gallery/examples/vibetracks-kpis/views.base"
WAIT = 30000  # ms: a ceiling for a state to arrive on a loaded machine, not a pause
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_page(browser, base):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(base + "/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady === true", timeout=WAIT)
    return page


def add_views(page, src, attrs="", view=None):
    """One <data-views> in the page (and, for a page frame, inside a scrolling pane)."""
    page.evaluate("""([src, attrs, view]) => {
      const el = document.createElement('data-views');
      el.id = 'v'; el.setAttribute('src', src); el.setAttribute('no-url', '');
      if (view) el.setAttribute('view', view);
      for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
      window.v = el;
      document.body.append(el);
    }""", [src, attrs or {}, view])


def two_frames(page):
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


# the scroll step, then the keyed draw's tbody against a from-scratch draw of the same window
ORACLE_STEP = """async ([dy]) => {
  const el = window.v, plugin = el._plugin, tbody = el.querySelector('.dv-view tbody');
  const box = el.host && el.host.scroller ? (el.host.scroller === window ? document.scrollingElement : el.host.scroller) : el.querySelector('.dv-scroll');
  const all = tbody.querySelectorAll('tr[data-i]'), kept = all[Math.floor(all.length / 2)];
  box.scrollTop += dy;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const keyed = tbody.innerHTML, p = tbody.dataset.p, first = (tbody.querySelector('tr[data-i]') || {}).dataset?.i;
  const sameNode = kept && kept.isConnected;
  plugin._invalidate(); plugin._drawBody();
  const full = tbody.innerHTML, pFull = tbody.dataset.p;
  return { equal: keyed === full && p === pFull, first, p, sameNode, len: keyed.length, top: box.scrollTop,
           diffAt: keyed === full ? -1 : [...keyed].findIndex((c, i) => c !== full[i]) };
}"""


def keyed_rows_match_full_redraw(browser, base, frame, label):
    page = open_page(browser, base)
    if frame in ("page", "bleed"):
        page.evaluate("() => { const pane = document.createElement('div'); pane.id = 'pane'; pane.style.cssText = 'height:700px;overflow:auto'; pane.innerHTML = '<p style=\"height:120px\">intro</p>'; document.body.append(pane); }")
        page.evaluate(f"""() => {{
          const el = document.createElement('data-views');
          el.id = 'v'; el.setAttribute('src', '{ACTUATORS}'); el.setAttribute('no-url', ''); el.setAttribute('frame', '{frame}');
          window.v = el; document.getElementById('pane').append(el);
        }}""")
    else:
        add_views(page, ACTUATORS, {"frame": frame} if frame else {})
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-i]')", timeout=WAIT)
    two_frames(page)
    steps = []
    for dy in [120] * 14 + [37, 1, 0, -240, -600, 3000, -90] + [120] * 6:
        steps.append(page.evaluate(ORACLE_STEP, [dy]))
    bad = [s for s in steps if not s["equal"]]
    moved = len({s["first"] for s in steps})
    check(f"table keyed rows ({label}): after each of {len(steps)} scroll steps the tbody equals a full redraw of the same window (rows, order, parity, spacers)",
          not bad and moved > 5, {"steps": len(steps), "windows": moved, "first mismatch": bad[:1]})
    kept = [s["sameNode"] for s in steps[:14]]
    check(f"table keyed rows ({label}): the middle row of the window, still in it after a 120 px step, is the same <tr>, not a rebuilt one",
          sum(kept) == len(kept), {"kept on 14 steps": sum(kept)})
    errors = page.errors
    page.context.close()
    return errors


def keyed_rows_behaviour(browser, base):
    """Focus, peek marks, an expand band and the column resize, through scrolls of the keyed table."""
    page = open_page(browser, base)
    add_views(page, ACTUATORS, {"open": "expand"})
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-i]')", timeout=WAIT)
    two_frames(page)
    # a scroll inside the same window adds nothing; a 120 px step adds a handful of rows, not the whole window
    got = page.evaluate("""async () => {
      const el = window.v, tbody = el.querySelector('.dv-view tbody'), box = el.querySelector('.dv-scroll');
      let added = 0;
      const mo = new MutationObserver((ms) => { for (const m of ms) added += [...m.addedNodes].filter((n) => n.nodeName === 'TR' && n.hasAttribute('data-i')).length; });
      mo.observe(tbody, { childList: true });
      const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      box.scrollTop += 1; await frame(); await new Promise((r) => setTimeout(r, 0));
      const within = added; added = 0;
      box.scrollTop += 120; await frame(); await new Promise((r) => setTimeout(r, 0));
      const step = added;
      mo.disconnect();
      return { within, step, drawn: tbody.querySelectorAll('tr[data-i]').length };
    }""")
    check("table keyed rows: a 1 px scroll that keeps the window adds no row; a 120 px step adds only the rows that came in (was the whole window)",
          got["within"] == 0 and 0 < got["step"] <= 10 and got["drawn"] > 20, got)

    # focus: a focused row stays focused (the same element) through a scroll that keeps it in the window
    got = page.evaluate("""async () => {
      const el = window.v, box = el.querySelector('.dv-scroll');
      const rows = [...el.querySelectorAll('.dv-view tbody tr.dv-row[data-i]')];
      const row = rows[Math.min(20, rows.length - 1)];
      row.focus({ preventScroll: true });
      box.scrollTop += 60;
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      return { same: document.activeElement === row, connected: row.isConnected, i: row.dataset.i };
    }""")
    check("table keyed rows: the focused row keeps focus through a scroll (the same <tr>)", got["same"] and got["connected"], got)

    # the peek marks its row, and the mark survives scrolling it out and back in; the drawn rows equal a full redraw
    got = page.evaluate("""async () => {
      const el = window.v, plugin = el._plugin, box = el.querySelector('.dv-scroll'), tbody = el.querySelector('.dv-view tbody');
      const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      box.scrollTop = 0; await frame();
      const id = el.querySelector('.dv-view tbody tr.dv-row[data-id]').dataset.id;
      el.openPeek(id); await frame();
      const marked = !!tbody.querySelector(`tr.dv-active[data-id="${CSS.escape(id)}"]`);
      box.scrollTop = 4000; await frame(); box.scrollTop = 0; await frame();
      const back = !!tbody.querySelector(`tr.dv-active[data-id="${CSS.escape(id)}"]`);
      const keyed = tbody.innerHTML; plugin._invalidate(); plugin._drawBody();
      const equal = keyed === tbody.innerHTML;
      el.closePeek && el.closePeek();
      return { marked, back, equal };
    }""")
    check("table keyed rows: the peeked row is marked, still marked after scrolling away and back, and equals a full redraw",
          got["marked"] and got["back"] and got["equal"], got)

    # open: expand: a band under a row; scrolling with it open still equals a full redraw at every step
    page.evaluate("() => { const r = document.querySelector('#v .dv-view tbody tr.dv-row[data-id] td:nth-child(2)'); r.click(); }")
    page.wait_for_function("() => document.querySelector('#v tbody tr.dv-open-band')", timeout=WAIT)
    two_frames(page)
    steps = [page.evaluate(ORACLE_STEP, [dy]) for dy in [10, 30, 120, 120, 120, -400, 0]]
    band = page.evaluate("() => !!document.querySelector('#v tbody tr.dv-open-band')")
    check("table keyed rows: with an expand band open, every scroll step equals a full redraw, and the band is back at the top",
          all(s["equal"] for s in steps) and band, {"steps": [s["equal"] for s in steps], "band": band})

    # the column resize: drag an edge 60 px wider, measured
    got = page.evaluate("""async () => {
      const th = document.querySelector('#v thead th[data-col]:nth-child(2)');
      const h = th.querySelector('.dv-resize');
      const r = h.getBoundingClientRect(), w0 = th.getBoundingClientRect().width;
      const at = { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true, pointerId: 1 };
      h.dispatchEvent(new PointerEvent('pointerdown', at));
      window.dispatchEvent(new PointerEvent('pointermove', { ...at, clientX: at.clientX + 60 }));
      window.dispatchEvent(new PointerEvent('pointerup', { ...at, clientX: at.clientX + 60 }));
      await new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
      const th2 = document.querySelector(`#v thead th[data-col="${th.dataset.col}"]`);
      return { w0, w1: th2.getBoundingClientRect().width, stored: (window.v.view.columnSize || {})[th.dataset.col] };
    }""")
    check("table: dragging a column edge 60 px makes it 60 px wider (getBoundingClientRect) and stores the width", abs(got["w1"] - got["w0"] - 60) <= 2 and got["stored"], got)
    errors = page.errors
    page.context.close()
    return errors


def cards_lightbox_on_demand(browser, base):
    page = open_page(browser, base)
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    add_views(page, PHOTOS)
    page.wait_for_function("() => document.querySelector('#v .dv-cards-card [data-zoom]')", timeout=WAIT)
    two_frames(page)
    before = [u for u in requests if "/dist/views/" in u]
    check("cards: drawing a media grid fetches cards.js and not the lightbox (PhotoSwipe loads on first open)",
          any(u.endswith("/views/cards.js") for u in before) and not any("cards-lightbox" in u for u in before),
          [u.rsplit("/", 1)[-1] for u in before])
    page.evaluate("() => document.querySelector('#v .dv-cards-card [data-zoom]').click()")
    page.wait_for_function("() => document.querySelector('#v .pswp') && document.querySelector('#v .pswp img, #v .pswp video')", timeout=WAIT)
    got = page.evaluate("""() => ({ styles: document.querySelectorAll('style[data-ui-view="cards-lightbox"]').length,
      shown: getComputedStyle(document.querySelector('#v .pswp')).position, caption: (document.querySelector('#v .dv-cards-caption') || {}).textContent || '' })""")
    loads = [u for u in requests if "cards-lightbox" in u]
    check("cards: the first photo opened loads the lightbox once and shows it full screen with its caption",
          len(loads) == 1 and got["styles"] == 1 and got["shown"] == "fixed" and got["caption"], {**got, "loads": len(loads)})
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#v .pswp')", timeout=WAIT)
    page.evaluate("() => document.querySelectorAll('#v .dv-cards-card [data-zoom]')[1].click()")
    page.wait_for_function("() => document.querySelector('#v .pswp')", timeout=WAIT)
    again = page.evaluate("() => document.querySelectorAll('style[data-ui-view=\"cards-lightbox\"]').length")
    check("cards: a second photo opens without fetching the lightbox again, and its css is added once",
          len([u for u in requests if "cards-lightbox" in u]) == 1 and again == 1, {"loads": len([u for u in requests if 'cards-lightbox' in u]), "styles": again})
    errors = page.errors
    page.context.close()

    # the lightbox cannot load: the status line says so, the card stays, nothing throws
    page = open_page(browser, base)
    page.route("**/views/cards-lightbox*", lambda route: route.abort())
    add_views(page, PHOTOS)
    page.wait_for_function("() => document.querySelector('#v .dv-cards-card [data-zoom]')", timeout=WAIT)
    page.evaluate("() => document.querySelector('#v .dv-cards-card [data-zoom]').click()")
    page.wait_for_function("() => /photo viewer did not load/.test(document.querySelector('#v .dv-status').textContent)", timeout=WAIT)
    got = page.evaluate("() => ({ pswp: !!document.querySelector('#v .pswp'), busy: !!document.querySelector('#v [data-zoom][aria-busy]'), cards: document.querySelectorAll('#v .dv-cards-card').length })")
    check("cards: when the lightbox fails to load, the status line says so and the grid stays as it was",
          not got["pswp"] and not got["busy"] and got["cards"] > 0 and not page.errors, {**got, "errors": page.errors[:2]})
    errors += [e for e in page.errors]
    page.context.close()
    return errors


def kpi_history_after_headline(browser, base):
    page = open_page(browser, base)
    page.evaluate("""() => {
      window.order = [];
      new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name.endsWith('/views/chart.js')) window.order.push('chart requested'); }).observe({ type: 'resource', buffered: true });
    }""")
    add_views(page, KPIS)
    page.evaluate("() => window.v.addEventListener('data-views-render', () => { window.order.push('render:' + (document.querySelector('#v data-kpi .dv-kpi-num') ? 'cards' : 'none')); }, { once: true })")
    page.wait_for_function("() => document.querySelector('#v data-kpi.dv-kpi-has-history .dv-kpi-history .dv-view-chart :is(svg, canvas)')", timeout=WAIT)
    page.wait_for_function("() => window.order.includes('chart requested')", timeout=WAIT)
    got = page.evaluate("() => ({ order: window.order, busy: !!document.querySelector('#v data-kpi[aria-busy]'), cards: document.querySelectorAll('#v data-kpi').length })")
    check("kpi: the view's first render fires with the cards drawn and before the chart bundle is requested; the history then draws",
          got["order"][:2] == ["render:cards", "chart requested"] and not got["busy"] and got["cards"] > 1, got)
    errors = page.errors
    page.context.close()

    # the chart bundle cannot load: the sparkline stays, the reason shows, the cards are drawn
    page = open_page(browser, base)
    page.route("**/views/chart.js", lambda route: route.abort())
    add_views(page, KPIS)
    page.wait_for_function("() => document.querySelector('#v data-kpi.dv-kpi-history-failed')", timeout=WAIT)
    got = page.evaluate("""() => { const h = document.querySelector('#v data-kpi.dv-kpi-history-failed');
      const spark = h.querySelector('.dv-kpi-spark-fallback, data-sparkline, svg');
      return { spark: !!spark && spark.getBoundingClientRect().height > 0, said: h.querySelector('.dv-kpi-history').textContent.slice(0, 40),
               shown: h.querySelector('.dv-kpi-history').getBoundingClientRect().height > 0, busy: h.hasAttribute('aria-busy') }; }""")
    check("kpi: when the chart bundle fails, the headline keeps its sparkline and says why under it",
          got["spark"] and got["shown"] and got["said"].startswith("history:") and not got["busy"], got)
    errors += page.errors
    page.context.close()

    # removed while the history waits for its frame: no error, nothing drawn into the removed view
    page = open_page(browser, base)
    add_views(page, KPIS)
    page.evaluate("() => new Promise((r) => window.v.addEventListener('data-views-render', () => { window.v.remove(); r(); }, { once: true }))")
    page.wait_for_timeout(1500)
    check("kpi: a <data-views> removed right after its first render draws no history and throws nothing",
          not page.errors and not page.evaluate("() => !!document.querySelector('data-kpi.dv-kpi-has-history')"), page.errors[:2])
    errors += page.errors
    page.context.close()
    return errors


def row_model_worker(browser, base):
    """The row-model worker prototype (review item 10): a real round trip equals rowModel(), a superseded request is
    never drawn, and terminate() removes the worker thread (the host's disconnectedCallback will call it)."""
    page = open_page(browser, base)
    got = page.evaluate(f"""async () => {{
      const kit = window.kit;
      const ds = await kit.loadDataset('/gallery/examples/robotparts-actuators/actuators.json');
      const b = kit.parseBase(await (await fetch('{ACTUATORS}')).text());
      const view = b.views.find((v) => v.groupBy && v.type === 'table');
      const want = kit.rowModel(ds, b, view, {{ query: 'gim' }});
      const w = kit.createRowModelWorker(ds);
      const got = await w.model(b, view, {{ query: 'gim' }});
      const sig = (m) => JSON.stringify([m.rows.map((r) => r.id), (m.groups || []).map((g) => [g.key, g.rows.length]), m.matched, m.total,
        m.table.getRowModel().rows.map((r) => r.getIsGrouped() ? 'g' + r.groupingValue : r.original.id)]);
      // three requests at once: only the newest is answered with a model
      const many = await Promise.all([w.model(b, view, {{ query: 'a' }}), w.model(b, view, {{ query: 'ak' }}), w.model(b, view, {{ query: 'gim' }})]);
      w.terminate();
      let after = null;
      try {{ await w.model(b, view, {{}}); after = 'answered'; }} catch (err) {{ after = err.message; }}
      return {{ same: sig(got) === sig(want), rows: got.rows.length, superseded: many.map((m) => m === null), last: many[2] && sig(many[2]) === sig(want), after }};
    }}""")
    check("row-model worker: a real round trip returns rowModel()'s rows, groups, counts and table (search 'gim' on the grouped actuators)",
          got["same"] and got["rows"] > 0, got)
    check("row-model worker: of three requests in flight only the newest is answered; the older two resolve null (never drawn)",
          got["superseded"] == [True, True, False] and got["last"], got)
    page.wait_for_timeout(300)
    alive = len(page.workers)
    check("row-model worker: after terminate() no worker thread is left and a request is refused",
          alive == 0 and "terminated" in str(got["after"]), {"workers": alive, "after": got["after"]})
    errors = page.errors
    page.context.close()
    return errors


def run(browser, base):
    errors = []
    errors += keyed_rows_match_full_redraw(browser, base, None, "boxed, grouped actuators")
    errors += keyed_rows_match_full_redraw(browser, base, "bleed", "frame=bleed, page scroll, zebra")
    errors += keyed_rows_behaviour(browser, base)
    errors += cards_lightbox_on_demand(browser, base)
    errors += kpi_history_after_headline(browser, base)
    errors += row_model_worker(browser, base)
    check("perf-views checks: no script errors", not errors, errors[:3])


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
    (OUT / "perf-views-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} perf-views checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
