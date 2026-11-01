"""What the fixture's dashboard draws with no editor opted in, written from the kit BEFORE the editor existed, so the
editor's checks can say "renders exactly as today" against the old code and not against themselves.

    $DATA_UI_PYTHON tests/browser/fixtures/dash_editor/make_golden.py     # on a checkout of the code to pin, after npm run build

Serves the checkout's root on a free 127.0.0.1 port, loads reading.html at 1280 and 390 px, and writes reading.golden.json
beside this file: the bar's buttons, the element's children and attributes, and every panel's class, label and box to
half a pixel. tests/browser/dash_editor_checks.py reads MEASURE from here, so both sides measure the same way.
"""

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent
PAGE = "/tests/browser/fixtures/dash_editor/reading.html"

MEASURE = """() => {
  const d = document.getElementById('servo');
  const box = (e) => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height].map((v) => Math.round(v * 2) / 2); };
  return {
    actions: d.querySelector('.dd-actions').innerHTML.replace(/\\s+/g, ' ').trim(),
    bar: box(d.querySelector('.dd-bar')),
    grid: box(d.querySelector('.dd-grid')),
    rail: d.querySelector('.dd-rail') ? box(d.querySelector('.dd-rail')) : null,
    children: [...d.children].map((c) => c.localName + (c.className ? `.${String(c.className).trim().split(/\\s+/).sort().join('.')}` : '')),
    attributes: [...d.attributes].map((a) => a.name).filter((n) => !['id', 'src', 'edit-variant', 'edit-switcher', 'editor'].includes(n)).sort(),
    classes: [...d.classList].sort(),
    panels: [...d.querySelectorAll('.dd-panel')].map((s) => ({ key: s.dataset.panel, type: s.dataset.type || null, cls: s.className, label: s.getAttribute('aria-label'), box: box(s) })),
    styles: document.querySelectorAll('style[data-ui-dash-edit], style[data-ui-gridstack]').length,
  };
}"""

READY = """() => { const d = document.getElementById('servo'); if (!d || !d.dash) return false;
  const els = [...d.querySelectorAll('.dd-panel data-views')]; return els.length >= 7 && els.every((e) => e.dataset.view); }"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    from playwright.sync_api import sync_playwright

    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + PAGE, timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    out = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width, height in ((1280, 800), (390, 844)):
                ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light", reduced_motion="reduce")
                page = ctx.new_page()
                page.goto(base + PAGE)
                page.wait_for_function("window.kitReady === true", timeout=30000)
                page.wait_for_function(READY, timeout=30000)
                page.wait_for_timeout(800)
                out[str(width)] = page.evaluate(MEASURE)
                ctx.close()
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (HERE / "reading.golden.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", HERE / "reading.golden.json")


if __name__ == "__main__":
    main()
