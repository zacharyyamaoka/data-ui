"""First useful paint of each dashboard (docs/peps/0005-dashboard-cards.md; the round-2 report's performance table).

    ~/psu-atlas/.venv/bin/python docs/measure_dashboards.py [cases…] > reports/media/dashboards-r2/paint.json

Serves the built dist/site and loads each case's page cold (a fresh browser context, no cache) N times in headless
Chromium. Two times, from the page's own navigation start (performance.now()):
  first useful paint  every panel that is not media or 3D has drawn: its <data-views> has data-view, a chart's Vega
                      view has drawn (data-drawn), and KPI cards exist; then one more frame (the paint)
  media ready         the first video in view has a decoded frame (readyState >= 2), when the dashboard has one
Lazy media and WebGL below the fold are not waited for (they start when scrolled near: that is the design).
Reported: the median and the spread of N runs. The page is the gallery's case page (it also shows the .base and
data listings), so it is an upper bound for the dashboard alone."""

import json
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "dist" / "site"
CASES = sys.argv[1:] or ["pid-tuning", "sim-to-real", "trajectory-tracking", "vibetracks-dashboard", "vibetracks-runs", "vibetracks-track", "dashboard-cards"]
N = 5

READY = """() => { const dash = document.querySelector('#example'); if (!dash || !dash.dash) return false;
  const secs = [...dash.querySelectorAll('.dd-panel:not(.dd-panel-text)')];
  for (const s of secs) {
    const t = s.dataset.type; if (['video', 'video-compare', 'image', 'scene3d'].includes(t)) continue;
    const dv = s.querySelector('data-views'); if (!dv || !dv.dataset.view) return false;
    const r = s.getBoundingClientRect(); if (r.top > innerHeight) continue;   // below the fold: lazy by design
    if (['chart', 'timeseries', 'trajectory'].includes(t) && !s.querySelector('[data-drawn]')) return false;
    if (t === 'kpi' && !s.querySelector('data-kpi')) return false;
  }
  return true; }"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            b = p.chromium.launch()
            for case in CASES:
                fups, media = [], []
                for _ in range(N):
                    ctx = b.new_context(viewport={"width": 1440, "height": 1000})
                    page = ctx.new_page()
                    page.goto(f"http://127.0.0.1:{port}/gallery/{case}/index.html", wait_until="commit")
                    page.wait_for_function(READY, timeout=60000, polling="raf")
                    fups.append(page.evaluate("() => new Promise((r) => requestAnimationFrame(() => r(performance.now())))"))
                    has = page.evaluate("() => !!document.querySelector('#example video')")
                    if has:
                        page.evaluate("() => { const v = document.querySelector('#example video'); v.scrollIntoView({ block: 'center' }); }")
                        page.wait_for_function("() => { const v = document.querySelector('#example video'); return v && v.readyState >= 2; }", timeout=60000)
                        media.append(page.evaluate("() => performance.now()"))
                    ctx.close()
                out[case] = {"first_useful_paint_ms": round(statistics.median(fups)), "spread_ms": [round(min(fups)), round(max(fups))],
                             "media_ready_ms": round(statistics.median(media)) if media else None, "runs": N}
                print(case, out[case], file=sys.stderr)
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
