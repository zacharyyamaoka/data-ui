"""What a presentation-only change costs: units, theme and a burst of search keys on a big table, timed in Chromium.

    <python with playwright> bench/presentation.py [--dist DIR] [--scenario large-table@100000] [--runs 5] [--json OUT]

The bench's interactions (runner.py) all change the rows; this times the renders that cannot: Units (inline <->
column) and a dark theme on <html>, each from the change to the view's data-views-render, and three search keys typed
in one go (model builds and time to the settled rows). WHY a separate script: the perf review's item 5 (reuse the row
model when its inputs have not changed) is invisible to the bench's scenario list; this is its before/after, on the
bench's own pages, data and server (runner.py), against any build (--dist).
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

TIMED = """async (what) => {
  const v = document.querySelector('data-views');
  const builds0 = performance.getEntriesByName('data-ui:model').filter((e) => !e.detail || !e.detail.reused).length;
  const done = new Promise((r) => v.addEventListener('data-views-render', () => r(), { once: true }));
  const t0 = performance.now();
  if (what === 'units') v.update((x) => { x.units = (x.units || 'column') === 'inline' ? 'column' : 'inline'; });
  else if (what === 'theme') { const h = document.documentElement; if (h.dataset.theme === 'dark') delete h.dataset.theme; else h.dataset.theme = 'dark'; }
  await done;
  const ms = performance.now() - t0;
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  return { ms, builds: performance.getEntriesByName('data-ui:model').filter((e) => !e.detail || !e.detail.reused).length - builds0 };
}"""

SEARCH = """async () => {
  const v = document.querySelector('data-views');
  const box = v.querySelector('.dv-search input');
  const builds0 = performance.getEntriesByName('data-ui:model').filter((e) => !e.detail || !e.detail.reused).length;
  const t0 = performance.now();
  for (const ch of 'ak8') { box.value += ch; box.dispatchEvent(new Event('input', { bubbles: true })); }
  while (v.model.rows.length === v.model.total || v.query !== 'ak8') await new Promise((r) => setTimeout(r, 5));
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  const ms = performance.now() - t0;
  const builds = performance.getEntriesByName('data-ui:model').filter((e) => !e.detail || !e.detail.reused).length - builds0;
  box.value = ''; box.dispatchEvent(new Event('input', { bubbles: true }));
  while (v.model.rows.length !== v.model.total) await new Promise((r) => setTimeout(r, 5));
  return { ms, builds };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="large-table@100000")
    ap.add_argument("--dist", default=str(runner.ROOT / "dist"))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--json")
    args = ap.parse_args()
    [t] = runner.load_scenarios([args.scenario])
    runner.Handler.dist = pathlib.Path(args.dist).resolve()
    runner.prepare(t)
    runner.Handler.pages[f"{t['target']}.html"] = runner.page_html(t)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), runner.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/page/{t['target']}.html"
    out = {"scenario": t["target"], "dist": args.dist, "units": [], "theme": [], "search": []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_context(viewport=runner.VIEWPORT).new_page()
                page.goto(url)
                page.wait_for_function("() => document.querySelector('data-views')?.dataset.view && document.querySelector('data-views .dv-view tbody tr')", timeout=120000)
                for _ in range(args.runs):
                    out["units"].append(page.evaluate(TIMED, "units"))
                    out["theme"].append(page.evaluate(TIMED, "theme"))
                    out["search"].append(page.evaluate(SEARCH))
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    for k in ("units", "theme", "search"):
        ms = [x["ms"] for x in out[k]]
        out[k + "_median_ms"] = round(statistics.median(ms), 1)
        out[k + "_builds"] = [x["builds"] for x in out[k]]
        print(f"{k:7s} median {out[k + '_median_ms']:8.1f} ms  model builds per change {out[k + '_builds']}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
