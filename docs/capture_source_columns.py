"""Capture the source columns' review: the hero take and the stills, from the built kit, on robotparts' real datasheet.

    ~/psu-atlas/.venv/bin/python docs/capture_source_columns.py <out dir> [<a build from before this lane>]

The take is one cut of the real page: hide the source that is winning (no value moves), then drag another to the front (the values move).
The dot is only the pointer, which a recording leaves out. `before` serves an older build's dist/ over the same fixture, so its picture
of Manage sources is that build, not a reconstruction."""

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1])
OLD = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
OUT.mkdir(parents=True, exist_ok=True)
FIX = "/tests/browser/fixtures/source-columns"
JMC = f"{FIX}/page.html?src=jmc.base&data=jmc.json&no-url&views=tabs"
DOT = """() => { const d = document.createElement('div'); d.id = 'dot'; d.style.cssText = 'position:fixed;z-index:99999;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:rgba(37,99,235,.55);box-shadow:0 0 0 2px rgba(255,255,255,.9);pointer-events:none;left:-40px;top:-40px;transition:transform .12s';
  document.body.append(d); const at = (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }; addEventListener('mousemove', at, true); addEventListener('dragover', at, true); addEventListener('mousedown', () => { d.style.transform = 'scale(.7)'; }, true); addEventListener('mouseup', () => { d.style.transform = ''; }, true); addEventListener('dragend', () => { d.style.transform = ''; }, true); }"""
NOMINALS = """() => Object.fromEntries([...document.querySelectorAll('#v tbody tr[data-id]')].map((tr) => { const c = tr.querySelector('td[data-col="nominal"]').cloneNode(true); for (const x of c.querySelectorAll('.dv-src-dd, .dv-src-pin, .dv-basis')) x.remove(); return [tr.dataset.id, c.textContent.replace(/\\s+/g, ' ').trim()]; }))"""


def serve(root):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}{FIX}/page.html", timeout=1)
            break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.1)
    return server, base


def glide(page, box, x, y, steps=14):
    page.mouse.move(x, y, steps=steps)
    page.wait_for_timeout(120)


def centre(box):
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def hero(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 620}, record_video_dir=str(OUT / "take"), record_video_size={"width": 1280, "height": 620})
    page = context.new_page()
    page.goto(f"{base}{JMC}")
    page.wait_for_selector("#v tbody tr[data-id]")
    page.evaluate(DOT)
    page.wait_for_timeout(1200)
    tab = page.locator('#v [role=tab]:visible', has_text="Sources")
    glide(page, None, *centre(tab.bounding_box()))
    page.mouse.down(); page.mouse.up()
    page.wait_for_timeout(1400)
    facts = {"before": page.evaluate(NOMINALS)}
    # hide the source that is winning: no value moves
    heads = page.evaluate("() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col^=\"nominal@\"]')].map((t) => t.dataset.col)")
    winner = next(c for c in heads if c.startswith("nominal@private:"))
    th = page.locator(f'#v thead th[data-col="{winner}"]')
    glide(page, None, *centre(th.bounding_box()))
    page.mouse.down(); page.mouse.up()
    page.wait_for_selector('[data-act="hide"]')
    page.wait_for_timeout(700)
    glide(page, None, *centre(page.locator('[data-act="hide"]').first.bounding_box()))
    page.mouse.down(); page.mouse.up()
    page.wait_for_timeout(1700)
    facts["hidden"] = page.evaluate(NOMINALS)
    page.evaluate("(c) => window.v.setView({ order: [...window.v.view.order, c] })", winner)
    page.wait_for_timeout(1100)
    # drag another to the front: the values move
    heads = page.evaluate("() => [...document.querySelectorAll('#v thead tr.dv-hleaf th[data-col^=\"nominal@\"]')].map((t) => t.dataset.col)")
    drawing = next(c for c in heads if "for 60ASM400" in c)
    src, dst = page.locator(f'#v thead th[data-col="{drawing}"]').bounding_box(), page.locator(f'#v thead th[data-col="{heads[0]}"]').bounding_box()
    glide(page, None, *centre(src))
    page.wait_for_timeout(300)
    page.mouse.down()
    x0, y0 = centre(src)
    for i in range(1, 25):
        page.mouse.move(x0 + (dst["x"] + 8 - x0) * i / 24, y0)
        page.wait_for_timeout(26)
    page.wait_for_timeout(300)
    page.mouse.up()
    # WHY away from the header: a scripted drop leaves the real pointer where the drag began, and a hover tip would come up there
    page.mouse.move(640, 560)
    page.wait_for_timeout(2600)
    facts["dragged"] = page.evaluate(NOMINALS)
    facts["order"] = page.evaluate("() => window.v.precedence.order")
    page.screenshot(path=str(OUT / "after-drag.png"))
    video = page.video
    context.close()
    shutil.move(video.path(), OUT / "hero.webm")
    (OUT / "hero-facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def stills(browser, base):
    for scheme in ("light", "dark"):
        context = browser.new_context(viewport={"width": 1280, "height": 620}, color_scheme=scheme)
        page = context.new_page()
        page.goto(f"{base}{JMC}")
        page.wait_for_selector("#v tbody tr[data-id]")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"datasheet-{scheme}.png"))
        page.locator('#v [role=tab]:visible', has_text="Sources").click()
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f"sources-{scheme}.png"))
        context.close()
    context = browser.new_context(viewport={"width": 1280, "height": 620})
    page = context.new_page()
    page.goto(f"{base}{JMC}")
    page.wait_for_selector("#v tbody tr[data-id]")
    page.locator('#v tbody tr[data-id="peak_torque"] button.dv-src-dd').click()
    page.wait_for_selector(".dv-src-pop")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "pill-menu.png"), clip={"x": 200, "y": 90, "width": 700, "height": 400})
    context.close()


def before(browser, base):
    context = browser.new_context(viewport={"width": 1280, "height": 620})
    context.route("**/dist/**", lambda r: r.fulfill(path=str(OLD / r.request.url.split("/dist/", 1)[1].split("?")[0])))
    page = context.new_page()
    page.goto(f"{base}{JMC}")
    page.wait_for_selector("#v tbody tr[data-id]")
    page.evaluate("() => { window.v.manageSources = true; }")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "before-manage.png"))
    widths = page.evaluate("() => [...document.querySelectorAll('#v thead th[data-src]')].map((t) => Math.round(t.getBoundingClientRect().width))")
    (OUT / "before-widths.json").write_text(json.dumps(widths) + "\n", encoding="utf-8")
    context.close()


def main():
    server, base = serve(ROOT)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            hero(browser, base)
            stills(browser, base)
            if OLD:
                before(browser, base)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
