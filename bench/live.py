"""bench/live.py: the live tier's speed (docs/peps/0012-live-data.md §8, §9), in headless Chromium.

    ~/psu-atlas/.venv/bin/python bench/live.py                  # short: about 3 minutes
    ~/psu-atlas/.venv/bin/python bench/live.py --mode long      # + 10 minutes at 60 kHz into the 256 MB buffer
    … --no-build --out DIR --label "after X"

On bench/live/page.html (driver.js builds a live dashboard over synthetic streams; every row is made in the page):
  sweep      frame time while streaming N samples/s into M plot panels (5 streams each): M x rate in (1, 4, 12) x
             (100 Hz, 1 kHz); 12 x 1 kHz is Rerun's published load, 60,000 samples a second
  latency    ingest to pixel, p50 / p95: a batch's append, to the frame that shows its newest sample (rAF, then a task:
             bench/harness.js's "painted")
  scrub      clock.seek(t) inside the buffer, to every plot drawn at t and painted (30 seeks, at 60 kHz)
  goLive     back to live after a 2 s pause, to every plot drawn at the newest data and painted
  heap       the JS heap after a GC once the buffer is at its cap (short: a 64 MB cap; long: 10 min into 256 MB)
  firstPaint navigation to the first plot drawn with data
  engines    the coordinator's decided bench (2026-10-27): the same min/max columns of a 60 kHz window pushed into uPlot
             (setData) and into Vega (the timeseries card's View: data + runAsync), frame by frame
Each run records the host, the commit, the load and a calibration; a run is `noisy` when the calibration is over 1.3x
this host's best or the load per CPU is over 1.0 (runner.py's rules). Noisy runs are kept and labelled, never dropped:
bench/publish.py routes noisy points to kpi_diagnostics.jsonl. This script never publishes (the orchestrator wires the
KPIs). It serves dist/ and bench/live/ from its own server on a free port, and stops it and the browser before it exits.
Writes OUT/live-<stamp>.json and OUT/live-latest.json (default bench/.out/).
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import pathlib
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse

BENCH = pathlib.Path(__file__).resolve().parent
ROOT = BENCH.parent
sys.path.insert(0, str(BENCH))
import runner  # noqa: E402  (its statistics, calibration, host and trust helpers: one definition of "noisy")

from playwright.sync_api import sync_playwright  # noqa: E402


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        p = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        for prefix, root in (("/dist/", ROOT / "dist"), ("/bench/live/", BENCH / "live")):
            if p.startswith(prefix):
                f = (root / p[len(prefix):]).resolve()
                if root.resolve() in f.parents:
                    return str(f)
        return str(BENCH / "__none__")


Handler.extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".json": "application/json"}


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_page(browser, base):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.goto(f"{base}/bench/live/page.html")
    page.wait_for_function("() => window.__live && window.__live.loaded", timeout=30000)
    return page, ctx.new_cdp_session(page)


def heap(cdp):
    cdp.send("HeapProfiler.collectGarbage")
    return round(cdp.send("Runtime.getHeapUsage")["usedSize"] / 2**20, 1)


def sweep_point(browser, base, M, rate, extra=False, log=print):
    page, cdp = open_page(browser, base)
    try:
        page.evaluate("(o) => __live.setup(o)", {"M": M, "rate": rate, "at": "10s", "budgetMB": 256})
        page.evaluate("() => __live.start()")
        page.wait_for_timeout(2500)   # the windows fill before anything is measured
        m = page.evaluate("(ms) => __live.measure(ms)", 5000)
        m.update({"M": M, "rate": rate, "N": M * 5 * rate})
        if extra:
            m["firstPaint"] = page.evaluate("() => __live.firstPaint()")
            m["scrub"] = page.evaluate("(n) => __live.scrub(n)", 30)
            m["goLive"] = page.evaluate("(n) => __live.goLive(n, 2000)", 8)
        m["errors"] = page.evaluate("() => __live.errors")
        log(f"  M={M:>2} x {rate:>4} Hz = {M * 5 * rate:>6} samples/s: frame p50/p95 {m['frameP50']:.1f}/{m['frameP95']:.1f} ms, "
            f"live frame p95 {m['liveFrameP95']} ms, ingest-to-pixel p50/p95 {m['latencyP50']}/{m['latencyP95']} ms, "
            f"worst draws/view/frame {m['worstDrawsPerViewPerFrame']}")
        return m
    finally:
        page.evaluate("() => __live.stop && __live.stop()")
        page.context.close()


def heap_run(browser, base, budget_mb, minutes, log=print):
    """Stream 60 kHz into a `budget_mb` buffer; the heap after a GC once it is at the cap, and every 30 s after."""
    page, cdp = open_page(browser, base)
    try:
        h0 = heap(cdp)
        page.evaluate("(o) => __live.setup(o)", {"M": 12, "rate": 1000, "at": "10s", "budgetMB": budget_mb})
        page.evaluate("() => __live.start()")
        t0 = time.time()
        samples, reached = [], None
        while True:
            time.sleep(5)
            b = page.evaluate("() => __live.ds.bytes / 2 ** 20")
            el = time.time() - t0
            if reached is None and b >= budget_mb * 0.97:
                reached = el
            if reached is not None and (not samples or el - samples[-1]["s"] >= 30):
                samples.append({"s": round(el), "heapMB": heap(cdp), "bufferMB": round(b, 1), "rows": page.evaluate("() => __live.ds.rowCount")})
                log(f"  heap at {round(el)} s: {samples[-1]}")
            if reached is not None and (el >= minutes * 60 or (minutes == 0 and el - reached >= 10)):
                break
            if el > max(600, minutes * 60 + 300):
                break
        return {"budgetMB": budget_mb, "heapBeforeMB": h0, "capReachedS": round(reached) if reached else None, "samples": samples,
                "heapAtCapMB": samples[0]["heapMB"] if samples else None, "heapLastMB": samples[-1]["heapMB"] if samples else None,
                "errors": page.evaluate("() => __live.errors")}
    finally:
        page.evaluate("() => __live.stop && __live.stop()")
        page.context.close()


def engines_run(browser, base, log=print):
    page, cdp = open_page(browser, base)
    try:
        r = page.evaluate("(o) => __live.engines(o)", {"frames": 240, "series": 5, "rate": 12000, "windowS": 10, "width": 860})
        log(f"  engines at {r['load']['samplesPerSecond']} samples/s, {r['load']['pointsDrawn']} points a frame: reduce p95 {r['reduce']['p95']} ms, "
            f"uPlot p50/p95 {r['uplot']['p50']}/{r['uplot']['p95']} ms, Vega p50/p95 {r['vega']['p50']}/{r['vega']['p95']} ms")
        return r
    finally:
        page.context.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", choices=["short", "long"], default="short")
    ap.add_argument("--out", default=str(BENCH / ".out"))
    ap.add_argument("--label", default="")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--software", action="store_true", help="draw on the CPU (headless Chromium's default) instead of the GPU")
    args = ap.parse_args()
    # pinned like npm run bench (run.mjs): a fixed budget of cores, comparable run to run
    cpus = os.environ.get("DATA_UI_BENCH_CPUS", "4-11")
    if cpus != "all" and shutil.which("taskset") and not os.environ.get("_LIVE_BENCH_PINNED"):
        os.environ["_LIVE_BENCH_PINNED"] = "1"
        os.execvp("taskset", ["taskset", "-c", cpus, sys.executable, *sys.argv])
    if not args.no_build:
        subprocess.run(["node", "build.mjs"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = Server(("127.0.0.1", port), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    result = {"schema": "data-ui-live-bench/1", "stamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "mode": args.mode, "label": args.label}
    try:
        with sync_playwright() as p:
            # WHY the GPU when this box has one: twelve canvases redrawn every frame are raster work, and headless
            # Chromium's default rasterises on the CPU (SwiftShader), which is not what a reader's desktop does;
            # runner.py does the same for its map scenarios, and every result says which renderer drew it
            browser = None
            if not args.software:
                browser = p.chromium.launch(args=runner.BROWSER_ARGS + runner.GPU_ARGS)
                renderer = runner.webgl_renderer(browser)
                if runner.renderer_kind(renderer) != "gpu":
                    browser.close()
                    browser = None
            if browser is None:
                browser = p.chromium.launch(args=runner.BROWSER_ARGS)
                renderer = runner.webgl_renderer(browser)
            try:
                host = runner.host_info(browser)
                host["renderer"] = {"kind": runner.renderer_kind(renderer), "string": renderer}
                print(f"renderer: {host['renderer']['kind']} ({renderer})")
                sha, dirty, branch = runner.git_sha()
                load0 = runner.loadavg()
                calib0 = runner.calibrate(browser)
                print(f"live bench on {host['hostname']} ({host['cpu']}), {sha}{' (dirty)' if dirty else ''}, load {load0}")
                print("sweep: N samples/s into M plot panels (5 streams each)")
                sweep = []
                for M, rate in ((1, 1000), (4, 1000), (12, 100), (12, 1000)):
                    sweep.append(sweep_point(browser, base, M, rate, extra=(M == 12 and rate == 1000)))
                print("heap: the buffer at its cap")
                heapres = heap_run(browser, base, 256 if args.mode == "long" else 64, 10 if args.mode == "long" else 0)
                print("engines: uPlot against Vega on the same columns")
                eng = engines_run(browser, base)
                calib1 = runner.calibrate(browser)
                load1 = runner.loadavg()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    best = runner.best_calibration(host["hostname"], min(calib0, calib1))
    why = []
    if max(calib0, calib1) > runner.NOISY_CALIB * best:
        why.append(f"calibration {max(calib0, calib1):.1f} ms > {runner.NOISY_CALIB} x this host's best {best:.1f} ms")
    for la in (load0, load1):
        if la is not None and la / (host["cpus"] or 1) > runner.NOISY_LOAD:
            why.append(f"load {la:.1f} on {host['cpus']} CPUs")
            break
    top = next(s for s in sweep if s["M"] == 12 and s["rate"] == 1000)
    result.update({
        "host": host, "git": {"sha": sha, "dirty": dirty, "branch": branch},
        "trust": {"calibration_ms": [round(calib0, 2), round(calib1, 2)], "best_calibration_ms": round(best, 2), "load": [load0, load1],
                  "pinned_cpus": host.get("pinned_cpus"), "noisy": bool(why), "why": why},
        "kpis": {
            "ingest_to_pixel_p50_ms": top["latencyP50"], "ingest_to_pixel_p95_ms": top["latencyP95"],
            "frame_p95_ms_60k_x12": top["frameP95"], "live_frame_p95_ms_60k_x12": top["liveFrameP95"], "fps_60k_x12": top["fps"],
            "scrub_p95_ms": top["scrub"]["p95"], "go_live_p95_ms": top["goLive"]["p95"],
            "first_paint_ms": (top.get("firstPaint") or {}).get("navToPaintMs"),
            # WHY both: the buffer's typed arrays live outside the JS heap (ArrayBuffer backing stores), so the heap alone
            # would flatter the tier; buffer_mb_at_cap is the store's own count of them
            "heap_mb_at_cap": heapres["heapAtCapMB"], "buffer_mb_at_cap": (heapres["samples"][0]["bufferMB"] if heapres["samples"] else None),
            "buffer_budget_mb": heapres["budgetMB"], "renderer": host["renderer"]["kind"],
            "uplot_update_p95_ms": eng["uplot"]["p95"], "vega_update_p95_ms": eng["vega"]["p95"],
        },
        "sweep": sweep, "heap": heapres, "engines": eng,
    })
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out / f"live-{stamp}.json").write_text(json.dumps(result, indent=1))
    (out / "live-latest.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result["kpis"], indent=1))
    print(f"{'NOISY: ' + '; '.join(why) if why else 'trusted run'}; written {out / ('live-' + stamp + '.json')}")
    errs = [e for s in sweep for e in s.get("errors", [])] + heapres.get("errors", [])
    if errs:
        print("FAILED: script errors in the page:", errs[:3])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
