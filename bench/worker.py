"""Interaction latency on a big table, the row model's worker's before/after: timed in Chromium against any build.

    <python with playwright> bench/worker.py [--dist DIR] [--scenario large-table@100000] [--runs 5] [--json OUT]

For each run, a cold load in a new browser context, then on that page, once its rail has counted (and the build's
row-model worker, if it has one, holds the data):
  cold     data parsed (data-ui:data), the first model built, the first useful paint (data-ui:first-render: the
           view drew its rows), and the longest main-thread gap between the data and the rows (rAF frame gaps)
  sort     a click on the Peak torque header, four times (desc, asc, ...): click to the view's data-views-render,
           the longest frame gap while the model computes, and whether the previous rows stayed in the DOM (the
           first row's id sampled every frame) until the new ones landed
  rail     a tick on a brand and its untick: click to the rail's new match count, the longest frame gap, and the
           rail's own data-ui:rail measures
WHY its own script: bench/runner.py's interactions report click-to-render only; the worker's point is that the page
keeps drawing frames while a model computes, which needs the frame gaps and the rows on screen sampled per frame.
Pin it away from the page's own work on a loaded machine (taskset -c 0-3) and run the two builds back to back.
"""

from __future__ import annotations

import argparse
import http.server
import json
import pathlib
import statistics
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

# from the first script on the page: every frame's time, and the longest gap in any window
INIT = """(() => {
  window.__f = [];
  const tick = () => { __f.push(performance.now()); requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  window.__gap = (from, to) => {
    const fs = __f.filter((t) => t >= from && t <= to);
    let worst = 0, prev = from;
    for (const t of fs) { worst = Math.max(worst, t - prev); prev = t; }
    return Math.max(worst, to - prev);
  };
})()"""

COLD = """() => {
  const m = (n) => performance.getEntriesByName(n);
  const data = m('data-ui:data')[0], first = m('data-ui:first-render')[0];
  const model = m('data-ui:model').find((e) => !e.detail || !e.detail.reused);
  return { data: data && data.startTime, model: model && model.startTime + model.duration, modelMs: model && model.duration,
    firstPaint: first && first.startTime, gap: data && first ? __gap(data.startTime, first.startTime) : null };
}"""

READY = """() => {
  const v = document.querySelector('data-views'), rail = document.querySelector('data-facets');
  const worker = v._rm ? !!v._rm.ready : true; // a build without the worker is ready as it is
  return !!(v.model && v.querySelector('.dv-view tbody tr[data-i]') && (!rail || rail.querySelector('.df-n')) && worker);
}"""

FIRST = "(v) => { const tr = v.querySelector('.dv-view tbody tr[data-i]:not(.dv-group)'); return tr ? (tr.dataset.id || tr.textContent.slice(0, 40)) : null; }"

SORT = """async (prop) => {
  const v = document.querySelector('data-views');
  const first = %s;
  const th = v.querySelector(`th[data-col="${prop}"] .dv-th`);
  const before = first(v);
  const seen = [];
  let on = true;
  const sample = () => { if (!on) return; seen.push(first(v)); requestAnimationFrame(sample); };
  const done = new Promise((r) => v.addEventListener('data-views-render', () => r(performance.now()), { once: true }));
  const t0 = performance.now();
  requestAnimationFrame(sample);
  if (th) th.click(); else v.setView({ sort: [{ property: prop, direction: 'DESC' }] });
  const t1 = await done;
  on = false;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const after = first(v);
  const during = seen.slice(0, -1);
  return { ms: t1 - t0, gap: __gap(t0, t1), frames: during.length, kept: during.every((x) => x === before), blank: during.some((x) => x === null),
    changed: before !== after, sort: JSON.stringify(v.view.sort) };
}""" % FIRST

RAIL = """async (brand) => {
  const v = document.querySelector('data-views'), rail = document.querySelector('data-facets');
  const box = rail.querySelector(`input[data-p="brand"][data-value="${brand}"]`);
  const n0 = rail.querySelector('.df-n').textContent;
  const marks0 = performance.getEntriesByName('data-ui:rail').length;
  const t0 = performance.now();
  box.click();
  while (rail.querySelector('.df-n').textContent === n0) await new Promise((r) => setTimeout(r, 2));
  const t1 = performance.now();
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  const rails = performance.getEntriesByName('data-ui:rail').slice(marks0).map((e) => Math.round(e.duration));
  return { ms: t1 - t0, gap: __gap(t0, t1), rails, n: rail.querySelector('.df-n').textContent };
}"""


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="large-table@100000")
    ap.add_argument("--dist", default=str(runner.ROOT / "dist"))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--sort", default="peak_torque")
    ap.add_argument("--brand", default="Feetech")
    ap.add_argument("--json")
    args = ap.parse_args()
    [t] = runner.load_scenarios([args.scenario])
    runner.Handler.dist = pathlib.Path(args.dist).resolve()
    runner.prepare(t)
    runner.Handler.pages[f"{t['target']}.html"] = runner.page_html(t)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), runner.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/page/{t['target']}.html"
    out = {"scenario": t["target"], "dist": args.dist, "cold": [], "sort": [], "rail": []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for _ in range(args.runs):
                    ctx = browser.new_context(viewport=runner.VIEWPORT)
                    ctx.add_init_script(INIT)
                    page = ctx.new_page()
                    page.goto(url)
                    page.wait_for_function("() => performance.getEntriesByName('data-ui:first-render').length", timeout=180000)
                    out["cold"].append(page.evaluate(COLD))
                    page.wait_for_function(READY, timeout=180000)
                    for _ in range(4):
                        out["sort"].append(page.evaluate(SORT, args.sort))
                    for _ in range(2):
                        out["rail"].append(page.evaluate(RAIL, args.brand))
                    ctx.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    summary = {
        "cold": {k: med([c[k] for c in out["cold"]]) for k in ("data", "model", "modelMs", "firstPaint", "gap")},
        "sort": {"ms": med([s["ms"] for s in out["sort"]]), "gap": med([s["gap"] for s in out["sort"]]),
                 "kept": all(s["kept"] and not s["blank"] for s in out["sort"]), "changed": all(s["changed"] for s in out["sort"])},
        "rail": {"ms": med([r["ms"] for r in out["rail"]]), "gap": med([r["gap"] for r in out["rail"]]),
                 "measure": med([x for r in out["rail"] for x in r["rails"]])},
    }
    out["summary"] = summary
    print(json.dumps(summary, indent=1))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
