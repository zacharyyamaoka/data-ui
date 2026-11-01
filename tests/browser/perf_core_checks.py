"""The perf-core checks: the work the core skips is work that could not change what is on screen, and the work it moves
lands after the rows are painted. Measured in headless Chromium on robotparts' 1,149 actuators (the gallery case),
on tests/browser/fixtures/lifecycle.html (an empty page the checks fill).

    ~/psu-atlas/.venv/bin/python tests/browser/perf_core_checks.py [OUT_DIR]     # after npm run build

From the 2026-10-26 performance review, items 3 (the rail counts only when its inputs change, after the rows paint)
and 5 (the row model is reused while its inputs are the same; search keys coalesce). The output itself is held to
the code before the work by tests/unit/perf-oracle.test.mjs; these checks hold the scheduling and the cache's
invalidation: a reused model or a skipped recount must never leave a stale number on screen. Every wait is on a
state, never a fixed sleep. Writes OUT_DIR/perf-core-checks.json (default reports/media/perf-core) and exits 1 if any
check fails. Its own file, so lanes editing checks.py never meet it (tools/test-all.mjs runs it).
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "perf-core"
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


SETUP = """() => {
  // every frame's time from the start, and every data-ui measure / mark as it lands
  window.frames_ = [];
  const tick = (t) => { frames_.push(performance.now()); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  window.timeline = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name.startsWith('data-ui:')) timeline.push({ name: e.name, start: e.startTime, end: e.startTime + e.duration, detail: e.detail }); })
    .observe({ entryTypes: ['mark', 'measure'] });
  const v = document.createElement('data-views');
  v.id = 'v'; v.setAttribute('src', '%s'); v.setAttribute('no-url', ''); v.setAttribute('editable', '');
  const rail = document.createElement('data-facets');
  rail.setAttribute('for', 'v'); rail.id = 'rail';
  document.body.append(rail, v);
  window.v = v; window.rail = rail;
  // count the rail's recounts (the passes that ran railCounts) and its paints
  window.recounts = 0; window.paints = 0;
  const rc = rail._recount, pt = rail._paint;
  rail._recount = function () { const did = rc.call(this); if (did) recounts++; return did; };
  rail._paint = function () { paints++; return pt.call(this); };
}""" % ACTUATORS

STATE = """() => ({ recounts, paints, status: v.querySelector('.dv-status .dv-count')?.textContent,
  railN: rail.querySelector('.df-n')?.textContent, builds: timeline.filter((e) => e.name === 'data-ui:model' && !e.detail.reused).length,
  reuses: timeline.filter((e) => e.name === 'data-ui:model' && e.detail.reused).length,
  ids: [...v.querySelectorAll('.dv-view tbody tr[data-i]')].slice(0, 6).map((tr) => tr.dataset.id || tr.textContent.slice(0, 30)),
  brand: Object.fromEntries([...rail.querySelectorAll('[data-p=brand][data-value]')].map((i) => [i.dataset.value, i.closest('label')?.querySelector('.df-count')?.textContent])) })"""


def settle(page):
    """Two frames and a task: any change event's recount (a frame, then a task) has run."""
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0))))")
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)))")


def open_page(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(SETUP)
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-i]') && document.querySelector('#rail .df-group')", timeout=WAIT)
    settle(page)
    return page


def rail_first_count_after_rows_paint(page):
    t = page.evaluate("""() => {
      const first = timeline.find((e) => e.name === 'data-ui:first-render');
      const rail = timeline.find((e) => e.name === 'data-ui:rail');
      const between = frames_.filter((f) => first && rail && f > first.start && f < rail.start);
      return { firstRender: first && Math.round(first.start), railStart: rail && Math.round(rail.start), framesBetween: between.length };
    }""")
    check("rail: its first count starts after the view's first draw, with a frame (the paint of the rows) in between",
          t["firstRender"] is not None and t["railStart"] is not None and t["framesBetween"] >= 1, t)


def rail_local_actions_do_not_recount(page):
    before = page.evaluate(STATE)
    out = {}
    # fold the first group, and back
    page.click("#rail [data-act=fold] >> nth=0")
    out["fold"] = page.evaluate("() => document.querySelector('#rail [data-act=fold]').getAttribute('aria-expanded')")
    page.click("#rail [data-act=fold] >> nth=0")
    # help, if a facet has it
    if page.query_selector("#rail [data-act=info]"):
        page.click("#rail [data-act=info] >> nth=0")
        out["help"] = bool(page.query_selector("#rail .df-help"))
    # show more
    if page.query_selector("#rail [data-more]"):
        page.click("#rail [data-more] >> nth=0")
        out["more"] = True
    # a list's own search
    if page.query_selector("#rail .df-find"):
        page.fill("#rail .df-find >> nth=0", "st")
        out["find"] = page.evaluate("() => document.querySelector('#rail .df-find').value")
        page.fill("#rail .df-find >> nth=0", "")  # leave the list whole for the checks after this one
    settle(page)
    after = page.evaluate(STATE)
    out.update({"recounts": [before["recounts"], after["recounts"]], "paints": [before["paints"], after["paints"]]})
    check("rail: fold, help, Show more and a list's search repaint the rail without recounting (it painted each time)",
          after["recounts"] == before["recounts"] and after["paints"] > before["paints"] and out["fold"] == "false", out)


def presentation_reuses_model_and_counts(page):
    before = page.evaluate(STATE)
    page.evaluate("() => v.update((x) => { x.units = 'inline'; })")
    settle(page)
    page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
    page.wait_for_function("() => document.querySelector('#v .dv-view tbody tr[data-i]')", timeout=WAIT)
    settle(page)
    page.evaluate("() => v.update((x) => { x.units = 'column'; })")
    settle(page)
    page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
    settle(page)
    after = page.evaluate(STATE)
    got = {"builds": [before["builds"], after["builds"]], "reuses": [before["reuses"], after["reuses"]], "recounts": [before["recounts"], after["recounts"]],
           "rows same": before["ids"] == after["ids"], "status": after["status"]}
    check("model: units and theme re-render the view on the same model (no rebuild) and the rail does not recount; the rows are the same",
          after["builds"] == before["builds"] and after["reuses"] >= before["reuses"] + 2 and after["recounts"] == before["recounts"] and got["rows same"], got)


def sort_rebuilds_model_not_counts(page):
    before = page.evaluate(STATE)
    page.evaluate("() => v.update((x) => { x.sort = [{ property: 'mass', direction: 'ASC' }]; })")
    page.wait_for_function("(b) => timeline.filter((e) => e.name === 'data-ui:model' && !e.detail.reused).length > b", arg=before["builds"], timeout=WAIT)
    settle(page)
    after = page.evaluate(STATE)
    got = {"builds": [before["builds"], after["builds"]], "recounts": [before["recounts"], after["recounts"]], "first rows changed": before["ids"] != after["ids"],
           "rail match": after["railN"]}
    check("model: a sort rebuilds the model and reorders the rows; the rail's counts (which a sort cannot change) are not recounted",
          after["builds"] == before["builds"] + 1 and got["first rows changed"] and after["recounts"] == before["recounts"], got)


def tick_recounts(page):
    before = page.evaluate(STATE)
    page.click("#rail input[data-p=brand][data-value=Feetech]")
    page.wait_for_function("() => /97 of 1,149/.test(v.querySelector('.dv-status .dv-count')?.textContent || '')", timeout=WAIT)
    page.wait_for_function("(r) => recounts > r", arg=before["recounts"], timeout=WAIT)
    settle(page)
    after = page.evaluate(STATE)
    got = {"recounts": [before["recounts"], after["recounts"]], "status": after["status"], "rail": after["railN"], "Feetech": after["brand"].get("Feetech"),
           "checked": page.evaluate("() => document.querySelector('#rail input[data-p=brand][data-value=Feetech]').checked")}
    check("rail: a tick recounts once and shows the new match (97), the ticked brand keeping its own count (disjunctive)",
          after["recounts"] == before["recounts"] + 1 and "97" in (after["railN"] or "") and got["Feetech"] == "97" and got["checked"], got)
    # untick, to leave the page as it was
    page.click("#rail input[data-p=brand][data-value=Feetech]")
    page.wait_for_function("() => /1,149 of 1,149/.test(v.querySelector('.dv-status .dv-count')?.textContent || '')", timeout=WAIT)
    settle(page)


def edit_invalidates_both(page):
    """An edit changes a row in place: the model and the rail must see it (dataRevision), though no object changed."""
    before = page.evaluate(STATE)
    res = page.evaluate("""async () => {
      const row = v.data.rows.find((r) => r.brand !== 'Feetech' && r.brand !== 'ODrive');
      const was = row.brand;
      const rev = v.dataRevision;
      const result = await v.propose({ id: row.id, set: { brand: 'Feetech' } });
      return { id: row.id, was, result, rev: [rev, v.dataRevision] };
    }""")
    page.wait_for_function("(r) => recounts > r", arg=before["recounts"], timeout=WAIT)
    settle(page)
    after = page.evaluate(STATE)
    got = {"edit": res, "builds": [before["builds"], after["builds"]], "recounts": [before["recounts"], after["recounts"]],
           "Feetech": [before["brand"].get("Feetech"), after["brand"].get("Feetech")]}
    check("an edit (a row changed in place) bumps dataRevision, rebuilds the model and recounts: the rail's brand count moves by one",
          res["result"].get("ok") and res["rev"][1] == res["rev"][0] + 1 and after["builds"] > before["builds"]
          and after["recounts"] == before["recounts"] + 1 and int(after["brand"].get("Feetech", "0").replace(",", "")) == int(before["brand"].get("Feetech", "0").replace(",", "")) + 1, got)


def search_coalesces(page):
    before = page.evaluate(STATE)
    box = "#v .dv-search input"
    # three keys in one task: the box shows all three at once; the rows follow once
    echo = page.evaluate("""(sel) => {
      const el = document.querySelector(sel);
      const shown = [];
      for (const ch of 'gim') { el.value += ch; el.dispatchEvent(new Event('input', { bubbles: true })); shown.push(el.value); }
      return shown;
    }""", box)
    page.wait_for_function("() => /of 1,149 rows/.test(v.querySelector('.dv-status .dv-count')?.textContent || '') && v.query === 'gim'", timeout=WAIT)
    settle(page)
    after = page.evaluate(STATE)
    expect = page.evaluate("""() => { const q = 'gim'; return v.model.rows.length; }""")
    got = {"typed": echo, "builds": after["builds"] - before["builds"], "status": after["status"], "rows": expect}
    check("search: three keys typed in one go echo at once and rebuild the model once (not three times), to the rows the full query matches",
          echo == ["g", "gi", "gim"] and got["builds"] == 1 and "of 1,149 rows" in (after["status"] or "") and not after["status"].startswith("1,149 of"), got)
    page.fill(box, "")
    page.wait_for_function("() => /^1,149 of 1,149/.test(v.querySelector('.dv-status .dv-count')?.textContent || '')", timeout=WAIT)


def fresh(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    return page


SERVED = """() => {
  kit.registerView('slowtable', { name: 'Slow table', load: () => new Promise((r) => setTimeout(() => r(kit.loadView('table').then((m) => m.View)), 1200)) });
  const v = document.createElement('data-views');
  v.id = 's'; v.setAttribute('no-url', '');
  v.innerHTML = '<table class="srv"><tr><th>Name</th></tr><tr><td>Alpha</td></tr><tr><td>Beta</td></tr></table>';
  document.body.append(v);
  v.data = { properties: { name: { type: 'text' } }, rows: [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }] };
  v.base = { views: [{ type: 'slowtable', name: 'Slow', order: ['name'] }] };
  window.s = v;
}"""


def served_rows_kept_until_the_view_draws(browser, base):
    """A host's server-rendered table inside <data-views> stays on screen while the view's code loads (a view made slow
    on purpose), and goes when the view draws: the rows are never blank and never on the page twice."""
    page = fresh(browser, base)
    page.evaluate(SERVED)
    page.wait_for_function("() => s.querySelector('.dv-head')", timeout=WAIT)
    during = page.evaluate("""() => ({ served: !!s.querySelector('.dv-stage > .dv-served table.srv'),
      visible: (s.querySelector('table.srv')?.getBoundingClientRect().height || 0) > 0,
      loading: !!s.querySelector('.dv-loading'), busy: s.querySelector('.dv-stage').getAttribute('aria-busy'), view: !!s.querySelector('.dv-view') })""")
    page.wait_for_function("() => s.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    after = page.evaluate("""() => ({ served: !!s.querySelector('table.srv'), busy: s.querySelector('.dv-stage').getAttribute('aria-busy'),
      rows: [...s.querySelectorAll('.dv-view tbody tr[data-i]')].map((tr) => tr.textContent.trim()) })""")
    check("served rows: a host's own table stays visible (no Loading…) while the view's code loads, and is gone once the view draws its rows",
          during["served"] and during["visible"] and not during["loading"] and during["busy"] == "true" and not during["view"]
          and not after["served"] and after["busy"] is None and len(after["rows"]) == 2, {"during": during, "after": after})
    errs = list(page.errors)
    page.context.close()
    return errs


VIEW_TIMES = """() => {
  const res = performance.getEntriesByType('resource');
  const view = res.find((r) => /\\/dist\\/views\\/table\\.js/.test(r.name));
  const data = performance.getEntriesByName('data-ui:data')[0];
  return { viewRequested: view ? Math.round(view.startTime) : null, dataParsed: data ? Math.round(data.startTime) : null };
}"""

PAIR_TIMES = """() => {
  const res = performance.getEntriesByType('resource');
  const b = res.filter((r) => /views\\.base$/.test(r.name)).pop();
  const d = res.find((r) => /actuators\\.json\\?explicit$/.test(r.name));
  return { baseStart: b ? Math.round(b.startTime) : null, baseEnd: b ? Math.round(b.responseEnd) : null, dataStart: d ? Math.round(d.startTime) : null };
}"""


def view_code_beside_the_data(browser, base):
    """The view's code is requested once the .base names it, before the data has arrived and been parsed; an explicit
    data= URL is requested together with the .base."""
    page = fresh(browser, base)
    page.evaluate("(src) => { const v = document.createElement('data-views'); v.id = 'p'; v.setAttribute('src', src); v.setAttribute('no-url', ''); document.body.append(v); window.p = v; }", ACTUATORS)
    page.wait_for_function("() => p.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    t = page.evaluate(VIEW_TIMES)
    check("view code: the table's code is requested before the data has been parsed (it used to wait for the whole model)",
          t["viewRequested"] is not None and t["dataParsed"] is not None and t["viewRequested"] < t["dataParsed"], t)
    page.evaluate("(src) => { const v = document.createElement('data-views'); v.id = 'q'; v.setAttribute('src', src); v.setAttribute('data', src.replace('views.base', 'actuators.json') + '?explicit'); v.setAttribute('no-url', ''); document.body.append(v); window.q = v; }", ACTUATORS)
    page.wait_for_function("() => q.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    t2 = page.evaluate(PAIR_TIMES)
    check("explicit data: with src= and data= both set, the data request starts before the .base has arrived (together, not one after the other)",
          t2["dataStart"] is not None and t2["baseEnd"] is not None and t2["dataStart"] <= t2["baseEnd"], t2)
    errs = list(page.errors)
    page.context.close()
    return errs


BIG = """(n) => {
  window.frames_ = [];
  const tick = () => { frames_.push(performance.now()); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  window.seen = [];
  const v = document.createElement('data-views');
  v.id = 'b'; v.setAttribute('no-url', '');
  new MutationObserver(() => { const t = v.querySelector('.dv-status .dv-count')?.textContent; if (t && seen[seen.length - 1] !== t) seen.push(t); })
    .observe(v, { subtree: true, childList: true, characterData: true });
  document.body.append(v);
  const rows = Array.from({ length: n }, (_, i) => ({ id: 'r' + i, name: 'part ' + (i % 997), n: (i * 7919) % 1000 }));
  performance.clearMarks(); performance.clearMeasures();
  v.base = { views: [{ type: 'table', name: 'All', order: ['name', 'n'], sort: [{ property: 'n', direction: 'DESC' }] }] };
  v.data = { properties: { name: { type: 'text' }, n: { type: 'number' } }, rows };
  window.b = v;
}"""

BIG_TIMES = """() => {
  const start = performance.getEntriesByName('data-ui:start').pop();
  const model = performance.getEntriesByName('data-ui:model')[0];
  return { start: start && Math.round(start.startTime), model: model && Math.round(model.startTime),
    framesBetween: start && model ? frames_.filter((f) => f > start.startTime && f < model.startTime).length : null, seen };
}"""


def big_data_paints_the_toolbar_first(browser, base):
    """At 25,000 rows the toolbar and the row count paint before the first model is built (a frame in between); at
    1,149 the model is built in the same task (no frame spent)."""
    page = fresh(browser, base)
    page.evaluate(BIG, 25000)
    page.wait_for_function("() => b.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    t = page.evaluate(BIG_TIMES)
    check("big data: at 25,000 rows the toolbar paints with 'Loading 25,000 rows…' before the model is built, then the rows",
          t["framesBetween"] is not None and t["framesBetween"] >= 1 and "Loading 25,000 rows…" in t["seen"] and any(x.startswith("25,000 of 25,000") for x in t["seen"]), t)
    page.context.close()
    page = fresh(browser, base)
    page.evaluate(BIG, 1149)
    page.wait_for_function("() => b.querySelector('.dv-view tbody tr[data-i]')", timeout=WAIT)
    t = page.evaluate(BIG_TIMES)
    check("small data: at 1,149 rows the model is built in the toolbar's own task (no frame spent, no Loading line)",
          t["framesBetween"] == 0 and not any(x.startswith("Loading") for x in t["seen"]), t)
    errs = list(page.errors)
    page.context.close()
    return errs


# ------------------------------------------------------------------ the row-model worker (lane/perf-worker)
# 100,000 synthetic rows (name: 997 distinct texts with a running number, n: a number, kind: 7 texts), given from script
# (cloned to the worker in slices) or as a data URL (the worker parses the very bytes the page fetched).
WORKER_PAGE = """(how) => {
  window.frames_ = [];
  const tick = () => { frames_.push(performance.now()); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  window.gap = (from, to) => { let worst = 0, prev = from; for (const t of frames_) if (t >= from && t <= to) { worst = Math.max(worst, t - prev); prev = t; } return Math.max(worst, to - prev); };
  const rows = Array.from({ length: 100000 }, (_, i) => ({ id: 'r' + i, name: 'part ' + (i % 997) + ' #' + i, n: (i * 7919) % 100003, kind: 'k' + (i % 7) }));
  const data = { id: 'w', properties: { name: { type: 'text' }, n: { type: 'number' }, kind: { type: 'text' } }, rows };
  const v = document.createElement('data-views');
  v.id = 'w'; v.setAttribute('no-url', ''); v.setAttribute('editable', '');
  v.base = { views: [{ type: 'table', name: 'All', order: ['name', 'n', 'kind'], sort: [{ property: 'n', direction: 'DESC' }] }] };
  if (how === 'url') v.setAttribute('data', URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' })) + '#.json');
  document.body.append(v);
  if (how !== 'url') v.data = data;
  window.w = v;
}"""

FIRST_ROW = "() => { const tr = w.querySelector('.dv-view tbody tr.dv-row'); return tr ? tr.textContent : null; }"

# a model change at 100k: the frames keep coming while the worker computes, the previous rows stay until the new land
WORKER_SORT = """async (sort) => {
  const first = %s;
  const posts = [];
  const post = w._rm.worker.postMessage.bind(w._rm.worker);
  w._rm.worker.postMessage = (m, t) => { posts.push(m.type); return post(m, t); };
  // the same model built here, synchronously, on the page's rows: the oracle for the order, and the time it takes
  const s0 = performance.now();
  const want = kit.rowModel(w.data, w.base, { ...w.view, sort }, { query: w.query, filters: w.filters });
  const syncMs = performance.now() - s0;
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  const before = first(), seen = [];
  let on = true;
  const sample = () => { if (!on) return; seen.push(first()); requestAnimationFrame(sample); };
  const rendered = new Promise((r) => w.addEventListener('data-views-render', () => r(performance.now()), { once: true }));
  const t0 = performance.now();
  requestAnimationFrame(sample);
  w.setView({ sort });
  // a presentation-only change while the model is on its way: it must not ask the worker again
  w.update((x) => { x.units = 'inline'; });
  const t1 = await rendered;
  on = false;
  const model = performance.getEntriesByName('data-ui:model').filter((e) => e.detail && e.detail.worker).pop();
  const landed = model ? model.startTime + model.duration : t1;
  w._rm.worker.postMessage = post;
  return { syncMs: Math.round(syncMs), gap: Math.round(gap(t0, landed)), wall: Math.round(landed - t0), seen: seen.length,
    kept: seen.slice(0, -1).every((x) => x === before), changed: first() !== before, asked: posts.filter((t) => t === 'model').length,
    same: w.model.rows.length === want.rows.length && w.model.rows.every((r, i) => r === want.rows[i]), worker: !!(model && model.detail.worker),
    units: w.view.units };
}""" % FIRST_ROW


def worker_page(browser, base, how):
    page = fresh(browser, base)
    page.evaluate(WORKER_PAGE, how)
    page.wait_for_function("() => w.querySelector('.dv-view tbody tr.dv-row') && w._rm && w._rm.ready", timeout=120000)
    settle(page)
    return page


def worker_keeps_the_page_drawing(browser, base):
    """At 100,000 rows a sort's model comes from the worker: while it computes, the page keeps drawing frames (the
    longest gap is under half of what the same model takes on the main thread), the previous rows stay on screen
    until the new ones land, a units change made meanwhile does not ask the worker twice, and the rows that land are
    rowModel()'s, in order, the page's own objects."""
    page = worker_page(browser, base, "script")
    first = page.evaluate("""() => { const want = kit.rowModel(w.data, w.base, w.view, { query: w.query, filters: w.filters });
      const m = performance.getEntriesByName('data-ui:model')[0];
      return { same: w.model.rows.length === 100000 && w.model.rows.every((r, i) => r === want.rows[i]), worker: !!(m.detail && m.detail.worker),
        drawn: [...w.querySelectorAll('.dv-view tbody tr.dv-row')].slice(0, 3).map((tr) => tr.textContent),
        want: want.rows.slice(0, 3).map((r) => r.name) }; }""")
    check("worker: the page's first model is built on the main thread (order.js keys, the table rebuilt from them) and is rowModel()'s rows, drawn in order",
          first["same"] and not first["worker"] and all(d.startswith(n) for d, n in zip(first["drawn"], first["want"])), first)
    got = page.evaluate(WORKER_SORT, [{"property": "name", "direction": "ASC"}])
    check("worker: at 100,000 rows a sort computes off the main thread; the page keeps drawing (longest frame gap < half the synchronous model)",
          got["worker"] and got["gap"] < got["syncMs"] / 2, got)
    check("worker: the previous rows stay on screen until the new ones land, which are rowModel()'s rows in its order",
          got["kept"] and got["changed"] and got["same"] and got["seen"] >= 2, got)
    check("worker: a units change while the model computes reuses that request (one model asked, units applied when it lands)",
          got["asked"] == 1 and got["units"] == "inline", {"asked": got["asked"], "units": got["units"]})
    errs = list(page.errors)
    page.context.close()
    return errs


def worker_takes_edits_and_fetched_bytes(browser, base):
    """The worker's copy follows an edit (posted with the new dataRevision): a sort by the edited value puts the edited
    row first, from the worker. And data loaded from a URL goes to the worker as the bytes the page fetched: its
    models equal rowModel()'s."""
    page = worker_page(browser, base, "url")
    res = page.evaluate("""async () => {
      const row = w.data.rows[54321];
      const rendered = new Promise((r) => w.addEventListener('data-views-render', r, { once: true }));
      const result = await w.propose({ id: row.id, set: { n: 1e9 } });
      await Promise.race([rendered, new Promise((r) => setTimeout(r, 60000))]);
      const model = performance.getEntriesByName('data-ui:model').filter((e) => e.detail && e.detail.worker).pop();
      const want = kit.rowModel(w.data, w.base, w.view, { query: w.query, filters: w.filters });
      return { ok: result.ok, first: w.model.rows[0].id, worker: !!model, same: w.model.rows.every((r, i) => r === want.rows[i]), rev: w.dataRevision, rmRev: w._rm.rev };
    }""")
    check("worker: an edit reaches the worker's copy before the next model: the edited row (n = 1e9) leads the n-descending rows, from the worker",
          res["ok"] and res["first"] == "r54321" and res["worker"] and res["same"] and res["rev"] == res["rmRev"], res)
    got = page.evaluate(WORKER_SORT, [{"property": "kind", "direction": "DESC"}, {"property": "name", "direction": "ASC"}])
    check("worker: data from a URL (the worker parses the bytes the page fetched): a two-key sort lands as rowModel()'s rows",
          got["worker"] and got["same"] and got["kept"], got)
    errs = list(page.errors)
    page.context.close()
    return errs


RAIL_PAGE = """() => {
  const rows = Array.from({ length: 100000 }, (_, i) => ({ id: 'r' + i, name: 'part ' + (i % 997) + ' #' + i, n: (i * 7919) % 100003, kind: 'k' + (i % 7), size: ['S', 'M', 'L', 'XL'][(i * 13) % 4] }));
  const v = document.createElement('data-views');
  v.id = 'w'; v.setAttribute('no-url', '');
  v.base = { facets: ['kind', 'size', { property: 'n', as: 'range' }], views: [{ type: 'table', name: 'All', order: ['name', 'n', 'kind', 'size'], sort: [{ property: 'n', direction: 'DESC' }] }] };
  const rail = document.createElement('data-facets');
  rail.setAttribute('for', 'w'); rail.id = 'wr';
  document.body.append(rail, v);
  v.data = { id: 'wr', properties: { name: { type: 'text' }, n: { type: 'number' }, kind: { type: 'text' }, size: { type: 'text' } }, rows };
  window.w = v; window.wr = rail;
}"""


def rail_counts_from_the_worker(browser, base):
    """At 100,000 rows with a worker, a tick's recount runs in the worker: the rail shows the numbers railCounts()
    gives on the page's own rows (every facet: values, sizes, the range's extent), and its match count is the model's."""
    page = fresh(browser, base)
    page.evaluate(RAIL_PAGE)
    page.wait_for_function("() => w._rm && w._rm.ready && wr.querySelector('input[data-p=kind][data-value=k3]')", timeout=120000)
    settle(page)
    got = page.evaluate("""async () => {
      const box = wr.querySelector('input[data-p=kind][data-value=k3]');
      const marks = performance.getEntriesByName('data-ui:rail').length;
      box.click();
      const byWorker = () => performance.getEntriesByName('data-ui:rail').slice(marks).some((e) => e.detail && e.detail.worker);
      const t0 = performance.now();
      while ((!byWorker() || !/14,286 match/.test(wr.querySelector('.df-n').textContent)) && performance.now() - t0 < 60000) await new Promise((r) => setTimeout(r, 10));
      const specs = wr._specs;
      // the rail's inputs as <data-facets> computed them before the worker (the view has no filters of its own)
      const rail = kit.toRail(w.filters, kit.railConfig(specs));
      const restKeep = kit.compileFilters(rail.rest.length ? { and: rail.rest } : null) || (() => true);
      const want = kit.railCounts(w.data.rows, rail.facets, specs, restKeep);
      const shown = Object.fromEntries([...wr.querySelectorAll('input[data-p=size][data-value]')].map((i) => [i.dataset.value, i.closest('label')?.querySelector('.df-count')?.textContent]));
      return { same: JSON.stringify(wr._counts) === JSON.stringify(want), n: wr.querySelector('.df-n').textContent, shown,
        wantSize: want[specs.find((s) => s.property === 'size').key].counts, worker: byWorker() };
    }""")
    shown_ok = all(got["shown"].get(k) == f"{v:,}" for k, v in got["wantSize"].items())
    check("rail: at 100,000 rows a tick is recounted in the worker, to exactly railCounts() on the page's rows, and the rail shows those numbers",
          got["worker"] and got["same"] and "14,286 match" in got["n"] and shown_ok, got)
    errs = list(page.errors)
    page.context.close()
    return errs


INTRO = """(src) => {
  const v = document.createElement('data-views');
  v.id = 'iv'; v.setAttribute('src', src); v.setAttribute('view', 'Leaderboard'); v.setAttribute('no-url', '');
  document.body.append(v); window.iv = v;
}"""


def intro_model_reused(browser, base):
    """A view with intro KPI cards: units and theme keep the intro's model (no second rowModel per render); a filter
    change rebuilds it, and the cards follow."""
    page = fresh(browser, base)
    page.evaluate(INTRO, "/gallery/examples/robotparts-models/views.base")
    page.wait_for_function("() => iv.querySelector('.dv-view') && iv._introModel && iv.querySelector('.dv-intro-cards')", timeout=WAIT)
    settle(page)
    got = page.evaluate("""async () => {
      const frame = () => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
      const first = iv._introModel;
      iv.update((x) => { x.units = 'inline'; }); await frame();
      document.documentElement.setAttribute('data-theme', 'dark'); await frame(); await frame();
      const sameAfterPresentation = iv._introModel === first;
      document.documentElement.removeAttribute('data-theme');
      const before = first.rows.length;
      const brand = iv.data.rows.map((r) => r.family ?? r.rung).find((x) => x != null);
      const prop = iv.data.rows.some((r) => r.family != null) ? 'family' : 'rung';
      iv.filters = { and: [`${prop} == ${JSON.stringify(String(brand))}`] }; await frame(); await frame();
      return { sameAfterPresentation, rebuilt: iv._introModel !== first, rows: [before, iv._introModel.rows.length], prop, brand: String(brand) };
    }""")
    check("intro: units and theme keep the intro's KPI model; a filter rebuilds it (to the filtered rows)",
          got["sameAfterPresentation"] and got["rebuilt"] and got["rows"][1] < got["rows"][0], got)
    errs = list(page.errors)
    page.context.close()
    return errs


# ---------------------------------------------------------------- judge r1 (2026-10-27), findings 2 and 3

STALE = """async () => {
  kit.registerView('slowlist', { name: 'Slow list', load: () => new Promise((r) => setTimeout(() => r(kit.loadView('table').then((m) => m.View)), 1500)) });
  const v = document.createElement('data-views');
  v.id = 'sv'; v.setAttribute('no-url', '');
  document.body.append(v); window.sv = v;
  v.base = { views: [{ type: 'table', name: 'T', order: ['n'] }] };
  v.data = { properties: { n: { type: 'number' } }, rows: Array.from({ length: 5000 }, (_, i) => ({ id: 'r' + i, n: i })) };
}"""

STALE_RUN = """async () => {
  const v = window.sv;
  const frame = () => new Promise((r) => requestAnimationFrame(() => r()));
  // a new view type: its model comes from the worker, then its code is slow to load
  v.update((x) => { x.type = 'slowlist'; });
  while (v._pending) await frame();
  // the model landed and the view's code is still loading: now a filter, whose model goes to the worker and is held
  // back 3 s (a big model's real time; the judge's stand-in), so the view's code (1.5 s) arrives while it is pending
  const ask = v._rm.model.bind(v._rm);
  v._rm.model = (...a) => new Promise((r) => setTimeout(() => r(ask(...a)), 3000));
  const at = performance.now();
  v.filters = { and: ['n > 4995'] };
  const seen = [];
  while (performance.now() - at < 6000) {
    await frame();
    const view = v.querySelector('.dv-stage > .dv-view-slowlist');
    if (view) seen.push(view.querySelectorAll('tbody tr.dv-row').length);
    if (view && !v._pending && /^4 of 5,000/.test(v.querySelector('.dv-status .dv-count')?.textContent || '') && view.querySelectorAll('tbody tr.dv-row').length === 4) break;
  }
  return { worst: seen.length ? Math.max(...seen) : null, frames: seen.length, last: seen[seen.length - 1] ?? null,
    status: v.querySelector('.dv-status .dv-count')?.textContent || '', model: v.model.rows.length };
}"""


def stale_view_never_draws_an_old_model(browser, base):
    """Judge r1 finding 2: a view whose code is still loading must not mount the model it was started for once a newer
    model (a filter, from the worker) is on its way; under n > 4995 no frame shows more than the 4 rows that match."""
    page = fresh(browser, base)
    page.evaluate(STALE)
    page.wait_for_function("() => sv.querySelector('.dv-view tbody tr.dv-row') && sv._rm && sv._rm.ready", timeout=120000)
    got = page.evaluate(STALE_RUN)
    check("render: a view still loading never mounts an older model; under a newer filter (worker) no frame shows more than its 4 rows",
          got["worst"] is not None and got["worst"] <= 4 and got["last"] == 4 and got["status"].startswith("4 of 5,000"), got)
    errs = list(page.errors)
    page.context.close()
    return errs


SERVED_ASYNC = """(mode) => {
  class Late {
    constructor(host, el) { if (mode === 'ctor') throw new Error('ctor boom'); this.el = el; }
    update(input) {
      if (mode === 'reject') return new Promise((_, no) => setTimeout(() => no(new Error('update boom')), 600));
      return new Promise((r) => setTimeout(() => { this.el.innerHTML = '<table class="drawn"><tbody>' + input.rows.map((x) => '<tr class="dv-row"><td>' + x.name + '</td></tr>').join('') + '</tbody></table>'; r(); }, 1200));
    }
    destroy() {}
  }
  kit.registerView('late-' + mode, { name: 'Late', load: async () => Late });
  const v = document.createElement('data-views');
  v.id = 'lv'; v.setAttribute('no-url', '');
  v.innerHTML = '<table class="srv"><tr><th>Name</th></tr><tr><td>Alpha</td></tr><tr><td>Beta</td></tr></table>';
  document.body.append(v); window.lv = v;
  v.data = { properties: { name: { type: 'text' } }, rows: [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }] };
  v.base = { views: [{ type: 'late-' + mode, name: 'Late', order: ['name'] }] };
}"""

SERVED_STATE = """() => {
  const srv = lv.querySelector('table.srv');
  const box = srv ? srv.getBoundingClientRect() : null;
  const top = box && box.height ? document.elementFromPoint(box.left + 10, box.top + box.height / 2) : null;
  return { served: !!srv, onTop: !!(top && srv.contains(top)), mounted: !!lv.querySelector('.dv-stage > .dv-view'),
    busy: lv.querySelector('.dv-stage').getAttribute('aria-busy'), drawn: !!lv.querySelector('table.drawn'),
    err: lv.querySelector('.dv-stage .dv-err')?.textContent || '' };
}"""


def served_rows_kept_through_async_update(browser, base):
    """Judge r1 finding 3: a host's own rows stay visible (and on top) until the new view's update() resolves, not only
    until its code loads; a view whose update rejects, or whose constructor throws, leaves them under the message."""
    errs = []
    page = fresh(browser, base)
    page.evaluate(SERVED_ASYNC, "ok")
    page.wait_for_function("() => lv.querySelector('.dv-stage > .dv-view')", timeout=WAIT)
    during = page.evaluate(SERVED_STATE)
    page.wait_for_function("() => lv.querySelector('table.drawn')", timeout=WAIT)
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => r()))")
    after = page.evaluate(SERVED_STATE)
    check("served rows: kept visible and on top while the mounted view's update() is still running; gone once it resolves",
          during["served"] and during["onTop"] and during["mounted"] and during["busy"] == "true" and not during["drawn"]
          and not after["served"] and after["busy"] is None and after["drawn"], {"during": during, "after": after})
    errs += [e for e in page.errors if "boom" not in e]
    page.context.close()
    for mode in ("reject", "ctor"):
        page = fresh(browser, base)
        page.evaluate(SERVED_ASYNC, mode)
        try:
            page.wait_for_function("() => lv.querySelector('.dv-stage .dv-err')", timeout=8000)
        except Exception:  # noqa: BLE001  (no message at all is this check's failure, recorded below)
            pass
        got = page.evaluate(SERVED_STATE)
        check(f"served rows: a view whose {'update() rejects' if mode == 'reject' else 'constructor throws'} leaves the host's own rows on screen under the message",
              got["served"] and got["onTop"] and "boom" in got["err"] and got["busy"] is None, got)
        errs += [e for e in page.errors if "boom" not in e]
        page.context.close()
    return errs


# ---------------------------------------------------------------- judge r1 finding 4: the rail's date presets and the day

DATED = """() => {
  const v = document.createElement('data-views');
  v.id = 'dv'; v.setAttribute('no-url', '');
  const rail = document.createElement('data-facets');
  rail.setAttribute('for', 'dv'); rail.id = 'drail';
  document.body.append(rail, v);
  window.dv = v; window.drail = rail;
  v.base = { facets: [{ property: 'listed', as: 'date' }], views: [{ type: 'table', name: 'T', order: ['name', 'listed'] }] };
  v.data = { properties: { name: { type: 'text' }, listed: { type: 'date' } },
    rows: [{ id: 'a', name: 'old', listed: '2026-10-20' }, { id: 'b', name: 'older', listed: '2026-09-01' }] };
}"""

LAST7 = """() => { const b = drail.querySelector('button.df-chip[data-act=date-from]'); return b ? { min: b.dataset.date, n: b.querySelector('.df-count').textContent } : null; }"""


def rail_dates_follow_the_day(browser, base):
    """Judge r1 finding 4: the rail's counts are cached, but a date preset's bounds move with the calendar day; at local
    midnight the rail recounts ("Last 7 days" from 2026-10-20 with 1 row becomes 2026-10-21 with 0), and a rail put
    back on a later day counts again rather than showing its cached bounds."""
    context = browser.new_context(viewport={"width": 1280, "height": 900}, timezone_id="America/Vancouver")
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.clock.install(time="2026-10-27T23:59:00-07:00")
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(DATED)
    page.wait_for_function("() => drail.querySelector('button.df-chip[data-act=date-from]')", timeout=WAIT)
    before = page.evaluate(LAST7)
    page.clock.fast_forward("02:00")  # 00:01 on Oct 28
    page.clock.run_for(1000)
    try:
        page.wait_for_function("() => (drail.querySelector('button.df-chip[data-act=date-from]') || {}).dataset?.date === '2026-10-21'", timeout=5000)
    except Exception:  # noqa: BLE001  (a rail that never recounts is this check's failure, recorded below)
        pass
    after = page.evaluate(LAST7)
    check("rail dates: at local midnight the rail recounts its date presets (Last 7 days moves from 2026-10-20, 1 row, to 2026-10-21, 0 rows)",
          before == {"min": "2026-10-20", "n": "1"} and after == {"min": "2026-10-21", "n": "0"}, {"before": before, "after": after})
    # put back on a later day: removed, two days pass, attached again
    page.evaluate("() => { window.keepRail = drail; drail.remove(); }")
    page.clock.fast_forward("48:00:00")
    page.evaluate("() => { document.body.prepend(keepRail); }")
    page.clock.run_for(1000)
    try:
        page.wait_for_function("() => (drail.querySelector('button.df-chip[data-act=date-from]') || {}).dataset?.date === '2026-10-23'", timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    back = page.evaluate(LAST7)
    check("rail dates: a rail put back two days later counts its presets for that day (Last 7 days from 2026-10-23), not its cached bounds",
          back is not None and back["min"] == "2026-10-23", back)
    errs = list(page.errors)
    context.close()
    return errs


# ---------------------------------------------------------------- judge r2 finding 1: a stale failure never wipes a newer view

STALE_FAIL = """(mode) => {
  // A: fails late (its code, or its first update()); B: an ordinary table that draws at once
  if (mode === 'load') kit.registerView('fail-a', { name: 'A', load: () => new Promise((_, no) => setTimeout(() => no(new Error('A load boom')), 1500)) });
  if (mode === 'update') {
    class LateReject { constructor(host, el) { this.el = el; } update() { return new Promise((_, no) => setTimeout(() => no(new Error('A update boom')), 1500)); } destroy() {} }
    kit.registerView('fail-a', { name: 'A', load: async () => LateReject });
  }
  if (mode === 'same') {
    // one plugin: its first update() rejects late, its second resolves at once and draws
    class Flaky {
      constructor(host, el) { this.el = el; this.calls = 0; }
      update(input) {
        const n = ++this.calls;
        if (n === 1) return new Promise((_, no) => setTimeout(() => no(new Error('first update boom')), 1500));
        this.el.innerHTML = '<table class="flaky"><tbody>' + input.rows.map((x) => '<tr class="dv-row"><td>' + x.name + '</td></tr>').join('') + '</tbody></table>';
        return Promise.resolve();
      }
      destroy() {}
    }
    kit.registerView('fail-a', { name: 'A', load: async () => Flaky });
  }
  const v = document.createElement('data-views');
  v.id = 'fv'; v.setAttribute('no-url', '');
  document.body.append(v); window.fv = v;
  v.base = { views: [{ type: 'fail-a', name: 'A', order: ['name'] }, { type: 'table', name: 'B', order: ['name'] }] };
  v.data = { properties: { name: { type: 'text' } }, rows: [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }, { id: 'c', name: 'Gamma' }] };
}"""

STALE_FAIL_STATE = """() => ({ rows: [...fv.querySelectorAll('.dv-stage > .dv-view tbody tr.dv-row')].map((tr) => tr.textContent.trim()),
  err: fv.querySelector('.dv-stage .dv-err')?.textContent || '', views: fv.querySelectorAll('.dv-stage > .dv-view').length,
  pluginOnPage: !!(fv._plugin && fv._plugin.el && fv._plugin.el.isConnected) || !!fv.querySelector('.dv-stage > .dv-view'), view: fv.dataset.view || null })"""


def stale_failures_leave_the_newer_view(browser, base):
    """Judge r2 finding 1: A's code fails to load, or A's update() rejects, AFTER a newer draw (B) has succeeded: B stays
    on screen with its rows, no error is shown, and the plugin is still on the page. Also one plugin whose first update()
    rejects after its second has drawn."""
    errs = []
    for mode in ("load", "update", "same"):
        page = fresh(browser, base)
        page.evaluate(STALE_FAIL, mode)
        if mode == "same":
            # the first update() is pending; a filter makes the second, which draws
            page.wait_for_function("() => fv.querySelector('.dv-stage > .dv-view-fail-a')", timeout=WAIT)
            page.evaluate("(f) => { fv.filters = { and: [f] }; }", 'name != "Beta"')
            page.wait_for_function("() => fv.querySelectorAll('.dv-stage table.flaky tr.dv-row').length === 2", timeout=WAIT)
            want = ["Alpha", "Gamma"]
            rows_sel = "() => [...fv.querySelectorAll('.dv-stage table.flaky tr.dv-row')].map((tr) => tr.textContent.trim())"
        else:
            # A is still loading (or updating): switch to B, which draws
            page.wait_for_function("() => fv.querySelector('.dv-tab')", timeout=WAIT)
            page.evaluate("(n) => [...fv.querySelectorAll('.dv-tab')].find((t) => t.dataset.name === n).click()", "B")
            page.wait_for_function("() => fv.dataset.view === 'table' && fv.querySelectorAll('.dv-stage > .dv-view tbody tr.dv-row').length === 3", timeout=WAIT)
            want = ["Alpha", "Beta", "Gamma"]
            rows_sel = "() => [...fv.querySelectorAll('.dv-stage > .dv-view tbody tr.dv-row')].map((tr) => tr.textContent.trim())"
        page.wait_for_timeout(2200)  # A's failure (1.5 s) has landed
        got = page.evaluate(STALE_FAIL_STATE)
        got["rows"] = page.evaluate(rows_sel)
        label = {"load": "A's code fails to load", "update": "A's update() rejects", "same": "the plugin's first update() rejects"}[mode]
        check(f"stale failure: {label} after the newer draw succeeded; the newer rows stay, no error, the view is still on the page",
              got["rows"] == want and got["err"] == "" and got["views"] == 1 and got["pluginOnPage"], got)
        errs += [e for e in page.errors if "boom" not in e]
        page.context.close()
    return errs


# ---------------------------------------------------------------- judge r2 finding 2: date presets across DST, and local repaints

DATED_ROWS = """(listed) => {
  const v = document.createElement('data-views');
  v.id = 'dv'; v.setAttribute('no-url', '');
  const rail = document.createElement('data-facets');
  rail.setAttribute('for', 'dv'); rail.id = 'drail';
  document.body.append(rail, v);
  window.dv = v; window.drail = rail;
  v.base = { facets: [{ property: 'listed', as: 'date' }], views: [{ type: 'table', name: 'T', order: ['name', 'listed'] }] };
  v.data = { properties: { name: { type: 'text' }, listed: { type: 'date' } }, rows: [{ id: 'a', name: 'edge', listed }, { id: 'b', name: 'older', listed: '2025-01-01' }] };
}"""

LAST7_IS = """(d) => (drail.querySelector('button.df-chip[data-act=date-from]') || {}).dataset?.date === d"""


def dated_page(browser, base, at, listed):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, timezone_id="America/Vancouver")
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.clock.install(time=at)
    page.goto(f"{base}/tests/browser/fixtures/lifecycle.html")
    page.wait_for_function("() => window.kitReady", timeout=WAIT)
    page.evaluate(DATED_ROWS, listed)
    page.wait_for_function("() => drail.querySelector('button.df-chip[data-act=date-from]')", timeout=WAIT)
    return context, page


def wait_last7(page, d):
    try:
        page.wait_for_function(LAST7_IS, arg=d, timeout=5000)
    except Exception:  # noqa: BLE001  (a stale rail is the check's failure, recorded by the caller)
        pass
    return page.evaluate(LAST7)


def rail_dates_across_dst(browser, base):
    """Judge r2 finding 2: "Last 7 days" subtracts 7 x 24 h, so across a DST change its bound moves at 23:00 (fall) or
    01:00 (spring), not at midnight; the rail recounts at that moment. And a fold or help repaint after the bound moved
    (no timer fired) recounts rather than painting yesterday's bound."""
    errs = []
    # fall back: Vancouver leaves DST at 02:00 on 2026-11-01; at 23:00 that night Last 7 days moves from Oct 25 to 26
    context, page = dated_page(browser, base, "2026-11-01T22:58:00-08:00", "2026-10-25")
    before = page.evaluate(LAST7)
    page.clock.fast_forward("03:00")  # 23:01
    after = wait_last7(page, "2026-10-26")
    check("rail dates, fall DST: Last 7 days moves at 23:00 on 2026-11-01 (Oct 25, 1 row -> Oct 26, 0 rows), not at midnight",
          before == {"min": "2026-10-25", "n": "1"} and after == {"min": "2026-10-26", "n": "0"}, {"22:58": before, "23:01": after})
    errs += list(page.errors)
    context.close()
    # spring forward: DST starts at 02:00 on 2026-03-08; on 2026-03-09 Last 7 days moves at 01:00 (Mar 1 -> Mar 2)
    context, page = dated_page(browser, base, "2026-03-09T00:58:00-07:00", "2026-03-01")
    before = page.evaluate(LAST7)
    page.clock.fast_forward("03:00")  # 01:01
    after = wait_last7(page, "2026-03-02")
    check("rail dates, spring DST: Last 7 days moves at 01:00 on 2026-03-09 (Mar 1, 1 row -> Mar 2, 0 rows)",
          before == {"min": "2026-03-01", "n": "1"} and after == {"min": "2026-03-02", "n": "0"}, {"00:58": before, "01:01": after})
    errs += list(page.errors)
    context.close()
    # a local repaint (fold, then unfold) after the bound moved, with no timer fired: it recounts first
    context, page = dated_page(browser, base, "2026-11-01T22:58:00-08:00", "2026-10-25")
    before = page.evaluate(LAST7)
    page.clock.set_system_time("2026-11-01T23:01:00-08:00")  # the clock moves; no timer runs
    page.evaluate("() => { const f = drail.querySelector('.df-group[data-p=listed] [data-act=fold]'); f.click(); }")
    page.evaluate("() => { const f = drail.querySelector('.df-group[data-p=listed] [data-act=fold]'); f.click(); }")
    after = page.evaluate(LAST7)
    check("rail dates: a fold/unfold repaint after the bound moved (no timer fired) shows the new bound, not the cached one",
          before == {"min": "2026-10-25", "n": "1"} and after == {"min": "2026-10-26", "n": "0"}, {"before": before, "after fold": after})
    errs += list(page.errors)
    context.close()
    return errs


def run(browser, base):
    page = open_page(browser, base)
    rail_first_count_after_rows_paint(page)
    rail_local_actions_do_not_recount(page)
    presentation_reuses_model_and_counts(page)
    sort_rebuilds_model_not_counts(page)
    tick_recounts(page)
    edit_invalidates_both(page)
    search_coalesces(page)
    errors = list(page.errors)
    page.context.close()
    errors += served_rows_kept_until_the_view_draws(browser, base)
    errors += view_code_beside_the_data(browser, base)
    errors += big_data_paints_the_toolbar_first(browser, base)
    errors += intro_model_reused(browser, base)
    errors += worker_keeps_the_page_drawing(browser, base)
    errors += worker_takes_edits_and_fetched_bytes(browser, base)
    errors += rail_counts_from_the_worker(browser, base)
    errors += stale_view_never_draws_an_old_model(browser, base)
    errors += served_rows_kept_through_async_update(browser, base)
    errors += rail_dates_follow_the_day(browser, base)
    errors += stale_failures_leave_the_newer_view(browser, base)
    errors += rail_dates_across_dst(browser, base)
    check("perf-core checks: no script errors", not errors, errors[:3])


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
    (OUT / "perf-core-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False), encoding="utf-8")
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} perf-core checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
