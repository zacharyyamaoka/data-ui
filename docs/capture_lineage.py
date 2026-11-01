#!/usr/bin/env python3
"""Capture the lineage report's media from the real built site (dist/site), headless: the hero clip and the stills.

    ~/psu-atlas/.venv/bin/python docs/capture_lineage.py OUT_DIR

The hero clip is Playwright's own recording of the page (no animation of ours): the robotparts tab opens folded,
"Show extinct" grows it to every proposal, Fit, fold it again, click the shipped logo's mark, the peek opens, follow its
parent link to the proposal it came from. A small dot is drawn where the pointer is, since a recording has no cursor.
ffmpeg turns the recording into an MP4 (H.264, muted) and a GIF fallback. Every still is a locator screenshot of the
<data-views> element, light and dark."""

import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "dist" / "site"
V = "#example"
CURSOR = """(() => { if (window.__dot) return; const d = document.createElement('div'); window.__dot = d;
  Object.assign(d.style, { position: 'fixed', zIndex: 99999, width: '18px', height: '18px', margin: '-9px 0 0 -9px', borderRadius: '50%',
    background: 'rgba(229, 72, 77, .35)', border: '2px solid rgba(229, 72, 77, .9)', pointerEvents: 'none', left: '-40px', top: '-40px', transition: 'transform .12s' });
  document.documentElement.appendChild(d);
  addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { d.style.transform = 'scale(.7)'; }, true);
  addEventListener('mouseup', () => { d.style.transform = ''; }, true); })()"""


def serve():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/index.html", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return proc, base


def ready(page):
    page.wait_for_selector(f"{V} .dv-lineage g.dv-lineage-node", timeout=30000)
    page.wait_for_timeout(400)


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_timeout(500)
    ready(page)


def glide(page, sel, steps=18):
    box = page.locator(sel).first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
    page.wait_for_timeout(250)
    return box


def hero(browser, base, out):
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 860}, record_video_dir=str(raw), record_video_size={"width": 1440, "height": 860})
    page = ctx.new_page()
    page.goto(f"{base}/gallery/brand-lineage/index.html")
    ready(page)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 8)")
    page.evaluate(CURSOR)
    page.mouse.move(700, 500)
    page.wait_for_timeout(1400)
    glide(page, f"{V} [data-act=extinct]")
    page.click(f"{V} [data-act=extinct]")
    page.wait_for_timeout(1800)
    glide(page, f"{V} [data-act=fit]")
    page.click(f"{V} [data-act=fit]")
    page.wait_for_timeout(1800)
    glide(page, f"{V} [data-act=extinct]")
    page.click(f"{V} [data-act=extinct]")
    page.wait_for_timeout(1500)
    glide(page, f"{V} g.dv-lineage-node.dv-focus .dv-lineage-dot", steps=24)
    page.click(f"{V} g.dv-lineage-node.dv-focus .dv-lineage-dot")
    page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
    page.wait_for_timeout(1800)
    link = f"{V} .dv-peek .dv-open-rel"
    if page.locator(link).count():
        glide(page, link)
        page.click(link)
        page.wait_for_timeout(2000)
    ctx.close()
    webm = sorted(raw.glob("*.webm"))[-1]
    mp4, gif = out / "hero.mp4", out / "hero.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-an", "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "26", "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf",
                    "fps=8,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(gif)], check=True)
    shutil.rmtree(raw)


def still(browser, base, out, name, path, tabname=None, dark=False, width=1440, height=860, mobile=False, action=None):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light",
                              device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    page.goto(f"{base}/{path}")
    ready(page)
    if tabname:
        tab(page, tabname)
    if action:
        action(page)
    page.locator(V).evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 8)")
    page.wait_for_timeout(300)
    target = page.locator(".demo") if page.locator(".demo").count() and not mobile else page.locator(V)
    target.first.screenshot(path=str(out / f"{name}.png"))
    ctx.close()


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    proc, base = serve()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            hero(browser, base, out)
            bl, ml = "gallery/brand-lineage/index.html", "gallery/model-lineage/index.html"

            def extinct(page):
                page.click(f"{V} [data-act=extinct]")
                page.wait_for_timeout(600)

            def peek(page):
                page.click(f"{V} g.dv-lineage-node.dv-focus .dv-lineage-dot")
                page.wait_for_selector(f"{V} .dv-peek:not([hidden])")
                page.wait_for_timeout(500)

            for dark in (False, True):
                t = "dark" if dark else "light"
                still(browser, base, out, f"robotparts-collapse-{t}", bl, dark=dark)
                still(browser, base, out, f"robotparts-radial-{t}", bl, "robotparts radial", dark=dark)
                still(browser, base, out, f"model-ladder-{t}", ml, dark=dark)
                still(browser, base, out, f"phone-{t}", bl, dark=dark, width=390, height=844, mobile=True)
            still(browser, base, out, "robotparts-show-light", bl, action=extinct)
            still(browser, base, out, "robotparts-peek-light", bl, action=peek)
            still(browser, base, out, "every-brand-light", bl, "Every brand")
            still(browser, base, out, "model-radial-dark", ml, "Ladder, radial", dark=True)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    for f in sorted(out.iterdir()):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
