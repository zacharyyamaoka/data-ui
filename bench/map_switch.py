"""What switching table -> map costs: the map tab clicked after the table, timed to the map's first settled frame.

    taskset -c 20-23 <python with playwright> bench/map_switch.py [--dist DIR] [--runs 10] [--webgl gpu|software] [--json OUT]

On the bench's own page, data and server (runner.py) for robotparts-sellers-map: start on the map, then N times click
"By country" (a table), let it settle, and click "Where sellers ship" (a map). Each switch is timed from the click to
  - render_ms: data-views-render (the view's update() has returned; a fresh map's returns on MapLibre's `load`)
  - settled_ms: the first frame after that in which the map has nothing left to draw: its style and sources loaded
    (map.loaded()), not moving, no repaint queued (MapLibre's own _frameRequest), then the next presented frame.
WHY settled and not `load` or `idle`: a map kept alive across switches never fires `load` again, and a fresh map
fires `idle` in the same frame as `load`, before data-views-render, so neither event exists on both paths; "nothing
left to draw" does. It also counts the maplibre Maps the page built (WebGL contexts made) to show reuse.
The map runs on the GPU like the bench's map scenarios (runner.GPU_ARGS, checked by its renderer string), and the
renderer is printed and stored. Against any build (--dist), so before and after run back to back.
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

TABLE, MAP = "By country", "Where sellers ship"

# WebGL contexts made: one per maplibre Map (MapLibre makes one canvas context per map)
COUNT_CONTEXTS = """(() => {
  window.__glMade = 0;
  const get = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
    const had = this.__glCounted;
    const ctx = get.call(this, kind, ...rest);
    if (ctx && /webgl/.test(kind) && !had) { this.__glCounted = true; window.__glMade++; }
    return ctx;
  };
})()"""

SWITCH = """async ([name, isMap]) => {
  const v = document.querySelector('data-views');
  const frame = () => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
  const tab = v.querySelector(`.dv-tab[data-name="${name}"]`);
  const rendered = new Promise((r) => v.addEventListener('data-views-render', () => r(performance.now()), { once: true }));
  const t0 = performance.now();
  tab.click();
  const tRender = await rendered;
  if (!isMap) { await frame(); return { render_ms: tRender - t0 }; }
  const map = v._plugin && v._plugin.map;
  if (!map) return { render_ms: tRender - t0, settled_ms: null, error: 'no map on the view' };
  for (let i = 0; i < 600; i++) {
    if (map.loaded() && !map.isMoving() && !map._frameRequest) break;
    await frame();
  }
  await frame();
  return { render_ms: tRender - t0, settled_ms: performance.now() - t0, made: window.__glMade,
           canvas: [map.getCanvas().clientWidth, map.getCanvas().clientHeight] };
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", default=str(runner.ROOT / "dist"))
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--webgl", choices=("gpu", "software"), default="gpu")
    ap.add_argument("--json")
    args = ap.parse_args()
    [t] = runner.load_scenarios(["robotparts-sellers-map"])
    runner.Handler.dist = pathlib.Path(args.dist).resolve()
    runner.prepare(t)
    runner.Handler.pages[f"{t['target']}.html"] = runner.page_html(t)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), runner.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/page/{t['target']}.html"
    out = {"scenario": t["target"], "dist": args.dist, "switches": []}
    try:
        with sync_playwright() as pw:
            flags = runner.BROWSER_ARGS + (runner.GPU_ARGS if args.webgl == "gpu" else [])
            browser = pw.chromium.launch(headless=True, args=flags)
            try:
                got = runner.webgl_renderer(browser)
                out["renderer"] = {"kind": runner.renderer_kind(got), "string": got, "args": flags}
                print(f"renderer: {out['renderer']['kind']} ({got})")
                if args.webgl == "gpu" and out["renderer"]["kind"] != "gpu":
                    print("  no hardware WebGL: these are software numbers")
                page = browser.new_context(viewport=runner.VIEWPORT).new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script(COUNT_CONTEXTS)
                page.goto(url)
                page.wait_for_function("() => document.querySelector('data-views')?.dataset.view === 'map'", timeout=120000)
                page.wait_for_timeout(500)
                for _ in range(args.runs):
                    page.evaluate(SWITCH, [TABLE, False])
                    page.wait_for_timeout(150)
                    out["switches"].append(page.evaluate(SWITCH, [MAP, True]))
                    page.wait_for_timeout(150)
                out["errors"] = errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    sw = out["switches"]
    for k in ("render_ms", "settled_ms"):
        xs = [x[k] for x in sw if x.get(k) is not None]
        out[k + "_median"] = round(statistics.median(xs), 1) if xs else None
        out[k + "_all"] = [round(x, 1) for x in xs]
    out["maps_made"] = sw[-1].get("made") if sw else None
    print(f"table -> map, {len(sw)} switches on {args.dist}")
    print(f"  data-views-render median {out['render_ms_median']} ms   {out['render_ms_all']}")
    print(f"  settled frame     median {out['settled_ms_median']} ms   {out['settled_ms_all']}")
    print(f"  maplibre Maps made (WebGL contexts): {out['maps_made']} (1 for the first load, +1 per switch when nothing is reused)")
    if out.get("errors"):
        print(f"  page errors: {out['errors'][:3]}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
