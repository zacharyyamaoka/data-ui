"""The embedded-chrome checks (docs/CONTRACT.md §18): `status` and `controls`, measured in headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/chrome_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/chrome.html: a table and a chart embedded in a host
page), stops it when done, writes OUT_DIR/chrome-checks.json (default reports/media/chrome) and exits 1 if any check
fails. Every claim is a number read from the page (getBoundingClientRect, getComputedStyle, the canvas's height), never
the presence of an attribute: a status line that was only marked hidden but still took 25 px would fail here.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "chrome"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
FRAMES = ["boxed", "flush", "tabs", "sheet", "page", "bleed"]


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


MEASURE = """(id) => {
  const v = document.getElementById(id);
  const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return {h: Math.round(r.height), w: Math.round(r.width), display: cs.display, visible: r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'}; };
  const status = v.querySelector(':scope > .dv-status');
  const bar = v.querySelector('.dv-chart-bar');
  const canvas = v.querySelector('.dv-chart-canvas canvas');
  return { status: box(status), statusText: status ? status.textContent.trim() : null, bar: box(bar), plot: canvas ? Math.round(canvas.getBoundingClientRect().height) : null,
    view: Math.round(((v.querySelector('.dv-stage > .dv-view') || {getBoundingClientRect: () => ({height: 0})}).getBoundingClientRect()).height),
    rows: v.querySelectorAll('tbody tr[data-i]').length, data: {status: v.dataset.status, controls: v.dataset.controls},
    slot: (v.querySelector('.dv-stage > .dv-view') || {dataset: {}}).dataset.controls || null, chrome: v.chrome ? v.chrome() : null };
}"""


def open_page(browser, base, query=""):
    context = browser.new_context(viewport={"width": 1280, "height": 1100})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/tests/browser/fixtures/chrome.html{query}")
    page.wait_for_function("() => document.querySelector('#t tbody tr[data-i]') && document.querySelector('#c .dv-chart-canvas canvas')", timeout=20000)
    page.wait_for_timeout(500)
    return page


def m(page, id_):
    return page.evaluate(MEASURE, id_)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/tests/browser/fixtures/chrome.html", timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            # 1. the default: everything shows (nothing changes for a host that says nothing)
            page = open_page(browser, base)
            t, c = m(page, "t"), m(page, "c")
            check("default: the table's status line shows", t["status"]["visible"] and t["status"]["h"] >= 20, t["status"])
            check("default: the chart's status line shows", c["status"]["visible"], c["status"])
            check("default: the chart's Encode / Rows bar shows", c["bar"]["visible"] and c["bar"]["h"] >= 28, c["bar"])
            check("default: chrome() says on, on and the element mirrors it", t["chrome"] == {"status": True, "controls": True} and t["data"] == {"status": "on", "controls": "on"}, t["chrome"])
            default_plot, default_bar, default_view = c["plot"], c["bar"]["h"], c["view"]
            check("default: no page error", not page.errors, page.errors[:2])
            page.screenshot(path=str(OUT / "default.png"), full_page=True)
            page.context.close()

            # 2. status="off": the line is gone (no box), the rows and the chart still draw
            page = open_page(browser, base, "?status=off")
            t, c = m(page, "t"), m(page, "c")
            check("status=off: the table's status line takes no space", not t["status"]["visible"] and t["status"]["h"] == 0, t["status"])
            check("status=off: the chart's status line takes no space", not c["status"]["visible"] and c["status"]["h"] == 0, c["status"])
            check("status=off: the table still draws its rows", t["rows"] > 5, t["rows"])
            check("status=off: the chart's bar still shows (controls are separate)", c["bar"]["visible"], c["bar"])
            check("status=off: the element says data-status=off", t["data"]["status"] == "off", t["data"])
            page.context.close()

            # 3. controls="off": the chart's bar is gone, the plot takes its height back; the status line stays
            page = open_page(browser, base, "?controls=off")
            t, c = m(page, "t"), m(page, "c")
            check("controls=off: the chart's Encode / Rows bar takes no space", not c["bar"]["visible"] and c["bar"]["h"] == 0, c["bar"])
            # the bar's height is given back: the view is shorter by exactly the bar (no blank band where it was), and the
            # plot keeps at least its own height (here the view sizes to its content, so the page gets the space)
            check("controls=off: the view is shorter by the bar's height (no blank band left)", abs((default_view - c["view"]) - default_bar) <= 2, [default_view, c["view"], default_bar])
            check("controls=off: the plot keeps its height", c["plot"] >= default_plot, [default_plot, c["plot"]])
            check("controls=off: the view's slot says data-controls=off", c["slot"] == "off", c["slot"])
            check("controls=off: the status line still shows", c["status"]["visible"], c["status"])
            check("controls=off: a table (no control bar of its own) draws as before", t["rows"] > 5 and t["status"]["visible"], t["rows"])
            check("controls=off: no page error", not page.errors, page.errors[:2])
            page.screenshot(path=str(OUT / "controls-off.png"), full_page=True)
            page.context.close()

            # 4. both off, under every frame (frame.css gives the status line a display; off must still win)
            for frame in FRAMES:
                page = open_page(browser, base, f"?status=off&controls=off&frame={frame}")
                t, c = m(page, "t"), m(page, "c")
                check(f"frame={frame}, both off: no status line on either", t["status"]["h"] == 0 and c["status"]["h"] == 0, [t["status"]["h"], c["status"]["h"]])
                check(f"frame={frame}, both off: no chart bar", c["bar"]["h"] == 0, c["bar"]["h"])
                check(f"frame={frame}, both off: the rows and the plot still draw", t["rows"] > 5 and (c["plot"] or 0) > 100, [t["rows"], c["plot"]])
                page.context.close()

            # 5. live: the attribute changes on a running element, both ways
            page = open_page(browser, base)
            page.evaluate("() => { document.getElementById('t').setAttribute('status', 'off'); document.getElementById('c').setAttribute('controls', 'off'); }")
            page.wait_for_timeout(300)
            t, c = m(page, "t"), m(page, "c")
            check("live: status set to off hides the line at once", t["status"]["h"] == 0, t["status"])
            check("live: controls set to off hides the bar at once", c["bar"]["h"] == 0, c["bar"])
            page.evaluate("() => { document.getElementById('t').removeAttribute('status'); document.getElementById('c').removeAttribute('controls'); }")
            page.wait_for_timeout(300)
            t, c = m(page, "t"), m(page, "c")
            check("live: removing the attributes brings both back", t["status"]["visible"] and c["bar"]["visible"], [t["status"], c["bar"]])
            page.context.close()

            # 6. the view's own key wins over the attribute, both ways
            page = open_page(browser, base, "?status=off")
            page.evaluate("() => document.getElementById('t').setView({status: 'on'})")
            page.wait_for_timeout(400)
            t = m(page, "t")
            check("view key status: on wins over status=\"off\"", t["status"]["visible"], t["status"])
            page.context.close()
            page = open_page(browser, base)
            page.evaluate("() => { document.getElementById('c').setView({controls: false}); document.getElementById('t').setView({status: 'off'}); }")
            page.wait_for_timeout(600)
            t, c = m(page, "t"), m(page, "c")
            check("view key controls: false hides the chart's bar with no attribute", c["bar"]["h"] == 0, c["bar"])
            check("view key status: off hides the table's status line with no attribute", t["status"]["h"] == 0, t["status"])
            page.context.close()
            browser.close()

        # 7. the .base file: both keys are known to the checker (no unknown-key warning), a wrong value is an error
        with tempfile.TemporaryDirectory() as tmp:
            good = pathlib.Path(tmp) / "good.base"
            good.write_text("views:\n  - type: chart\n    name: C\n    status: off\n    controls: off\n    chart: {encoding: {x: {field: a}, y: {field: b}}}\n", encoding="utf-8")
            bad = pathlib.Path(tmp) / "bad.base"
            bad.write_text("views:\n  - type: table\n    name: T\n    status: sometimes\n", encoding="utf-8")
            ok = subprocess.run(["node", str(ROOT / "bin" / "data-ui.mjs"), "check", str(good)], capture_output=True, text=True)
            no = subprocess.run(["node", str(ROOT / "bin" / "data-ui.mjs"), "check", str(bad)], capture_output=True, text=True)
            text = ok.stdout + ok.stderr
            check(".base: status: off and controls: off check clean (no unknown-key warning)", ok.returncode == 0 and "unknown" not in text.lower() and "status" not in text and "controls" not in text, text.strip()[:200])
            check(".base: status: sometimes is refused", no.returncode != 0 or "status" in (no.stdout + no.stderr), (no.stdout + no.stderr).strip()[:200])
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "chrome-checks.json").write_text(json.dumps(checks, indent=1) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} chrome checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
