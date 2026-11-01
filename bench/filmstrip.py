"""A filmstrip of one cold load: what the reader sees, frame by frame, from navigation start.

    <python with playwright> bench/filmstrip.py SCENARIO OUT_DIR [--dist DIR]

Chromium's trace with its screenshot category (what Lighthouse's filmstrip reads) holds a frame each time one is
presented; time zero is the page's navigationStart. Frames are saved as OUT_DIR/<ms>.jpg with OUT_DIR/filmstrip.json listing
{t_ms, file} plus the page's milestones (FCP, data-ui marks, first useful paint) on the same clock, the way
Lighthouse and WebPageTest draw theirs. One run only: it is a picture of the chain, not a measurement (the KPI
numbers come from runner.py's N runs).
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runner  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("out")
    ap.add_argument("--dist", default=str(runner.ROOT / "dist"))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    [t] = runner.load_scenarios([args.scenario])
    runner.Handler.dist = pathlib.Path(args.dist).resolve()
    runner.prepare(t)
    runner.Handler.pages[f"{t['target']}.html"] = runner.page_html(t)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), runner.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/page/{t['target']}.html"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(viewport=runner.VIEWPORT, device_scale_factor=1)
                page = ctx.new_page()
                page.add_init_script(runner.HARNESS)
                page.goto("about:blank")
                browser.start_tracing(page=page, screenshots=True, categories=["devtools.timeline", "disabled-by-default-devtools.screenshot", "blink.user_timing", "loading"])
                page.goto(url, wait_until="load")
                page.evaluate("window.__bench.interactive(500, 30000)")
                time.sleep(0.3)
                trace = json.loads(browser.stop_tracing())
                info = page.evaluate("""() => { const B = window.__bench;
                  return { fcp: B.paints['first-contentful-paint'] ?? null, first_useful_paint: B.firstUsefulPaint,
                           marks: B.marks.map((m) => ({ name: m.name, t: m.t })), lcp: B.lcp.length ? B.lcp[B.lcp.length - 1].t : null }; }""")
                ctx.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    events = trace["traceEvents"] if isinstance(trace, dict) else trace
    # time zero is the bench page's own navigationStart, found by its URL. WHY not the latest: a map view starts
    # navigations of its own (MapLibre's frames, empty loader URL), and taking the max put frames before zero
    nav = [e["ts"] for e in events if e.get("name") == "navigationStart"
           and "/page/" in ((e.get("args") or {}).get("data") or {}).get("documentLoaderURL", "")]
    t0 = max(nav) if nav else min(e["ts"] for e in events if e.get("ts"))
    listed = []
    for e in events:
        if e.get("name") != "Screenshot" or e["ts"] < t0:
            continue
        ms = round((e["ts"] - t0) / 1000)
        name = f"{ms:05d}.jpg"
        (out / name).write_bytes(base64.b64decode(e["args"]["snapshot"]))
        listed.append({"t_ms": ms, "file": name})
    (out / "filmstrip.json").write_text(json.dumps({"scenario": t["target"], "frames": listed, **info}, indent=1))
    print(f"{len(listed)} frames to {out}")


if __name__ == "__main__":
    main()
