#!/usr/bin/env python3
"""One small pass of the kit in Firefox and WebKit, the engines tests/browser never touches: load a table, a map and a
dashboard from the built site, filter each, open a record. A red step is listed with what it saw, never hidden.

    python3 tools/cross-browser-smoke.py [--browser firefox --browser webkit] [--headed] [--json FILE] [--shots DIR]
    python3 tools/cross-browser-smoke.py --summary FILE       # a run's JSON as Markdown
    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s '-screen 0 1440x900x24 +extension GLX' python3 tools/cross-browser-smoke.py --browser firefox --headed

WHY --headed for Firefox: headless Firefox has no WebGL at all, so it cannot draw the map; under Xvfb it gets Mesa's software GL.

Needs dist/site (npm run build) and the browsers (python -m playwright install firefox webkit). Serves dist/site on a free
127.0.0.1 port and stops it when done. Exit 1 if any step failed. Every step reads a drawn state (a status line, a box, a
count), the same way tests/browser/ does, and a page error or console error in a case is a step of its own.
WHY small: Chromium carries the 4,000 checks; this answers one question, "does the kit work at all over there?", and each
line it lists is a finding to read (docs/CI.md), not a broken main.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "dist" / "site"
WAIT = 45000
V = "#example"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def serve():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        with contextlib.suppress(OSError):
            urllib.request.urlopen(base + "/", timeout=1).read(1)
            break
        time.sleep(0.1)
    try:
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=5)


class Run:
    def __init__(self, browser_name: str, browser, base: str, shots: pathlib.Path | None):
        self.name, self.browser, self.base, self.shots = browser_name, browser, base, shots
        self.steps: list[dict] = []

    def step(self, case: str, what: str, ok, detail=""):
        self.steps.append({"browser": self.name, "case": case, "step": what, "ok": bool(ok), "detail": str(detail)[:300]})
        print(f"{'PASS' if ok else 'FAIL'} {self.name} · {case}: {what}" + (f"  [{str(detail)[:200]}]" if detail else ""), flush=True)

    @contextlib.contextmanager
    def page(self, case: str, path: str):
        """A fresh page on the case; what it logged becomes the case's last step, and an exception one failing step."""
        context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        try:
            page.goto(f"{self.base}/{path}")
            yield page
        except Exception as e:  # noqa: BLE001 -- listed, never hidden
            self.step(case, "the case ran to its end", False, f"{type(e).__name__}: {e}")
        finally:
            if self.shots:
                with contextlib.suppress(Exception):
                    page.screenshot(path=str(self.shots / f"{self.name}-{case}.png"))
            self.step(case, "no page error, no console error", not errors, "; ".join(errors[:3]))
            context.close()


def status(page) -> str:
    return page.inner_text(f"{V} .dv-status")


def table(run: Run):
    case = "table"
    with run.page(case, "gallery/robotparts-actuators/") as page:
        page.wait_for_selector(f"{V} tbody tr[data-i]", timeout=WAIT)
        run.step(case, "1,149 rows, virtualised", "1,149 of 1,149" in status(page), status(page).split("·")[0])
        page.check("data-facets input[data-p=brand][data-value=Steadywin]")
        page.wait_for_function("(s) => document.querySelector(s).innerText.includes('86 of 1,149')", arg=f"{V} .dv-status", timeout=WAIT)
        run.step(case, "the rail filters to 86 rows", "86 of 1,149" in status(page), status(page).split("·")[0])
        page.locator(f"{V} tbody tr.dv-row").first.click()
        page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=WAIT)
        box = page.locator(f"{V} .dv-peek").bounding_box()
        run.step(case, "a row opens its record in the peek", box and box["width"] > 100 and box["height"] > 100, box)


def map_view(run: Run):
    case = "map"
    with run.page(case, "gallery/robotparts-sellers-map/") as page:
        # WHY first: MapLibre needs WebGL2, and a headless engine with no GL driver has none. That is the machine, not the
        # kit, so it reads as its own line, and the kit's job there is to say so in the view
        webgl = page.evaluate("!!document.createElement('canvas').getContext('webgl2')")
        run.step(case, "this engine has WebGL2", webgl)
        if not webgl:
            page.wait_for_function("(s) => /WebGL2 is required/.test(document.querySelector(s).innerText)", arg=V, timeout=WAIT)
            run.step(case, "without it the view says why, in its own place", True)
            return
        page.wait_for_selector(f"{V}[data-view='map'] .dv-map-marker", timeout=WAIT)
        before = page.locator(f"{V} .dv-map-marker").count()
        canvas = page.locator(f"{V} canvas.maplibregl-canvas")
        run.step(case, "MapLibre draws with its markers", before > 100 and canvas.count() == 1, f"{before} markers, {canvas.count()} canvas")
        # this case has no rail: its filter is the view's search box
        page.fill(f"{V} input[type=search]", "Canada")
        page.wait_for_function("(n) => document.querySelectorAll('#example .dv-map-marker').length < n", arg=before, timeout=WAIT)
        after = page.locator(f"{V} .dv-map-marker").count()
        run.step(case, "the search narrows the markers", 0 < after < before, f"{before} -> {after}")
        page.locator(f"{V} .dv-map-marker").first.click()
        page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=WAIT)
        run.step(case, "a marker opens its record", page.locator(f"{V} .dv-peek").is_visible())


def dashboard(run: Run):
    case = "dashboard"
    with run.page(case, "gallery/sim-to-real/") as page:
        page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
          return els.length > 3 && els.every((e) => e.dataset.view); }""", timeout=WAIT)
        panels = page.locator(f"{V} .dd-panel").count()
        run.step(case, "every panel draws", panels > 3, f"{panels} panels")
        rows = page.locator(f"{V} .dd-panel tbody tr.dv-row")
        before = rows.count()
        box = page.locator("data-facets input[type=checkbox]")
        run.step(case, "the rail has choices", box.count() > 0, f"{box.count()} checkboxes")
        box.first.check()
        page.wait_for_function("(n) => document.querySelectorAll('#example .dd-panel tbody tr.dv-row').length !== n", arg=before, timeout=WAIT)
        run.step(case, "the rail narrows the tables", rows.count() != before, f"{before} -> {rows.count()} rows")
        rows.first.click()
        page.wait_for_selector(f"{V} .dv-peek:not([hidden])", timeout=WAIT)
        run.step(case, "a row opens its record", page.locator(f"{V} .dv-peek:not([hidden])").first.is_visible())


def summary(path: str) -> int:
    steps = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    failed = [s for s in steps if not s["ok"]]
    print(f"### Cross-browser smoke: {len(steps) - len(failed)} of {len(steps)} steps\n")
    for s in failed:
        print(f"- **{s['browser']} · {s['case']}: {s['step']}** {s['detail']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--browser", action="append", choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--shots")
    ap.add_argument("--summary")
    args = ap.parse_args()
    if args.summary:
        return summary(args.summary)
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm run build")
        return 2
    from playwright.sync_api import sync_playwright

    shots = pathlib.Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    with serve() as base, sync_playwright() as p:
        for name in args.browser or ["firefox", "webkit"]:
            try:
                options = {"headless": not args.headed}
                if name == "firefox":
                    options["firefox_user_prefs"] = {"webgl.force-enabled": True}
                browser = getattr(p, name).launch(**options)
            except Exception as e:  # noqa: BLE001 -- listed, never hidden
                steps.append({"browser": name, "case": "launch", "step": "the browser starts", "ok": False, "detail": str(e)[:300]})
                print(f"FAIL {name}: the browser does not start: {str(e)[:200]}", flush=True)
                continue
            run = Run(name, browser, base, shots)
            for case in (table, map_view, dashboard):
                case(run)
            browser.close()
            steps += run.steps
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(steps, indent=1) + "\n", encoding="utf-8")
    failed = [s for s in steps if not s["ok"]]
    print(f"\n{len(steps) - len(failed)} of {len(steps)} steps pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
