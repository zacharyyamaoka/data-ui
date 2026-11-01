"""Arrange keeps every panel its rows tall (packages/dashboard/src/arrange.js), measured in headless Chromium on the built kit.

    ~/psu-atlas/.venv/bin/python tests/browser/arrange_checks.py [OUT_DIR]     # after npm run build

The bug (2026-10-29): pressing Arrange on a <data-dashboard> collapsed the panels that are one grid row tall (the Playback
panel, a note) to 0 px, because the gridstack items had `height: auto` and gridstack writes an inline height only for h > 1.
Fixture: tests/browser/fixtures/arrange_fix/views.base, one-row panels beside taller ones. Every claim is
getBoundingClientRect: each panel's height is above 0 and equals its grid h x cell height (the dashboard's row height plus
its gap) within 2 px, on pressing Arrange and again after a drag. Serves the repo root on a free 127.0.0.1 port, stops that
server when done, writes OUT_DIR/arrange-checks.json (default reports/media/arrange) and exits 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "arrange"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = "/tests/browser/fixtures/arrange_fix/page.html"
WAIT = 30000
TOLERANCE = 2  # px
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{json.dumps(value, default=str, ensure_ascii=False)[:600]}]" if value is not None else ""), flush=True)


@contextlib.contextmanager
def guard(what):
    try:
        yield
    except Exception as e:  # noqa: BLE001 -- reported, never hidden
        check(f"{what}: could not be measured", False, f"{type(e).__name__}: {str(e)[:300]}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory, probe):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + probe, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return proc, base


MEASURE = """() => {
  const dash = document.getElementById('example');
  const gap = parseFloat(getComputedStyle(dash).getPropertyValue('--dd-gap')) || 12;
  const cell = dash.dash.rowHeight + gap;
  return { cell, panels: [...dash.querySelectorAll('.dd-panel[data-panel]')].map((s) => {
    return { key: s.dataset.panel, type: s.dataset.type, gridH: s.gridstackNode ? s.gridstackNode.h : null, height: s.getBoundingClientRect().height };
  }) };
}"""


def measure(page, label):
    m = page.evaluate(MEASURE)
    cell, panels = m["cell"], m["panels"]
    check(f"{label}: there are panels and one-row ones among them", len(panels) >= 6 and any(p["gridH"] == 1 for p in panels), [(p["key"], p["gridH"]) for p in panels])
    check(f"{label}: every panel is taller than 0 px", all(p["height"] > 0 for p in panels), [(p["key"], round(p["height"], 1)) for p in panels])
    off = [(p["key"], p["gridH"], round(p["height"], 1), p["gridH"] * cell) for p in panels if not p["gridH"] or abs(p["height"] - p["gridH"] * cell) > TOLERANCE]
    check(f"{label}: every panel's height is its grid h x cell height ({cell:g} px) within {TOLERANCE} px", not off, off or [(p["key"], p["gridH"], round(p["height"], 1)) for p in panels])
    return panels


def arranging(browser, base):
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = ctx.new_page()
    page.goto(base + PAGE)
    page.wait_for_function("window.kitReady === true", timeout=WAIT)
    page.wait_for_function("""() => { const d = document.getElementById('example'); if (!d || !d.dash) return false;
      const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length >= 4 && els.every((e) => e.dataset.view); }""", timeout=WAIT)
    page.wait_for_timeout(600)
    check("the fixture has a playback panel and a note", page.evaluate("""() => !!document.querySelector('#example .dd-panel[data-type="playback"]')
      && !!document.querySelector('#example .dd-panel-text')"""))
    page.locator("#example [data-act=arrange]").click()
    page.wait_for_function("() => document.querySelector('#example .dd-grid.grid-stack .grid-stack-item')", timeout=10000)
    page.wait_for_timeout(600)
    before = measure(page, "after pressing Arrange")
    page.screenshot(path=str(OUT / "arrange-pressed.png"))
    # drag the Playback panel (one row) onto the top; every panel is measured again once gridstack has settled
    box = page.locator("#example .dd-panel[data-type=playback]").bounding_box()
    top = page.locator("#example .dd-panel").first.bounding_box()
    # WHY the panel's middle: its left end is the play button, which gridstack's drag ignores
    sx, sy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx, sy - 40, steps=6)
    page.mouse.move(sx, top["y"] + 4, steps=14)
    page.wait_for_timeout(300)
    page.mouse.up()
    page.wait_for_timeout(700)
    first = page.evaluate("() => document.querySelector('#example .dd-panel[data-type=playback]').gridstackNode.y")
    check("the drag moved the playback panel to the top row", first == 0, first)
    measure(page, "after a drag")
    page.screenshot(path=str(OUT / "arrange-dragged.png"))
    ctx.close()
    return before


def main() -> int:
    if not (ROOT / "dist" / "data-ui.js").exists() or not (ROOT / "dist" / "dashboard.js").exists():
        print("the kit is not built: npm run build")
        return 1
    proc, base = serve(ROOT, PAGE)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            with guard("Arrange on a dashboard with a playback panel and a note"):
                arranging(browser, base)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (OUT / "arrange-checks.json").write_text(json.dumps(checks, indent=1, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"\n{len(checks) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
