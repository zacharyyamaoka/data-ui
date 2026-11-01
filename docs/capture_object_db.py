#!/usr/bin/env python3
"""Capture the object-database report's media from the built site (dist/site): the hero clip of the 3D shelf
(hover turns a model, a drag turns it, a click opens the peek's orbit viewer), and full-width stills of the five
proposals on the prototype page, light and dark, plus the peek and the phone.

    npm --prefix ~/data-ui/.wt/object-db run build
    ~/psu-atlas/.venv/bin/python docs/capture_object_db.py [OUT_DIR]   # default ~/data-ui/reports/media/object-db

Serves dist/site on a free 127.0.0.1 port and stops it when done. The browser runs with the GPU when headless can
reach it (the clip is smoother), else SwiftShader; which one is written to capture.json. Needs Playwright (the
psu-atlas venv), Pillow and ffmpeg.
"""

from __future__ import annotations

import io
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "dist" / "site"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("~/data-ui/reports/media/object-db")
PROTO = "gallery/object-db-shelf/prototype/index.html"
GPU = ["--enable-gpu", "--ignore-gpu-blocklist", "--use-angle=vulkan", "--enable-features=Vulkan", "--enable-precise-memory-info"]
PROPOSALS = ["shelf", "ledger", "tree", "streams", "lab"]
# WHY setpts=PTS/1.15 below: the clip plays 15 % fast to stay under 20 s with every beat in it
# WHY a drawn cursor: a recorded page has no pointer, and the clip is about where the pointer is
CURSOR = """
addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(37,99,235,.35);border:2px solid rgba(37,99,235,.9);z-index:2147483647;pointer-events:none;transition:transform .08s';
  document.body.append(c);
  addEventListener('pointermove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('pointerdown', () => { c.style.transform = 'scale(.7)'; }, true);
  addEventListener('pointerup', () => { c.style.transform = ''; }, true);
});
"""


def webp(png: bytes, path: pathlib.Path, quality: int = 88) -> None:
    Image.open(io.BytesIO(png)).save(path, "WEBP", quality=quality, method=6)


def wait_views(page, timeout=20000):
    page.wait_for_function("() => { const v = document.querySelectorAll('#stage data-views'), s = [...document.querySelectorAll('#stage data-views .dv-status')]; "
                           "return v.length && s.length === v.length && s.every(e => e.textContent.trim()); }", timeout=timeout)


def glide(page, x0, y0, x1, y1, ms=500):
    steps = max(4, ms // 16)
    for i in range(1, steps + 1):
        page.mouse.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        page.wait_for_timeout(16)


def centre(page, locator):
    b = locator.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def hero(browser, base, info):
    vid = OUT / "video-tmp"
    shutil.rmtree(vid, ignore_errors=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(vid), record_video_size={"width": 1440, "height": 900}, color_scheme="light")
    ctx.add_init_script("try { localStorage.setItem('object-db/proposal', 'shelf'); localStorage.removeItem('data-ui-site-theme'); } catch {}")
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    page.goto(f"{base}/{PROTO}")
    wait_views(page)
    page.wait_for_function("[...document.querySelectorAll('#p1 .dv-cards-card .dv-mesh-poster')].slice(0, 12).every(i => i.complete && i.naturalWidth)", timeout=20000)
    meshes = page.locator("#p1 .dv-cards-card data-mesh")
    x, y = 720, 860
    page.mouse.move(x, y)
    page.wait_for_timeout(700)
    t0 = time.time()
    # 1-2: hover two real scans: each turns while the pointer is over it, then freezes where it was left
    for i in (0, 1):
        nx, ny = centre(page, meshes.nth(i))
        glide(page, x, y, nx, ny, 450)
        x, y = nx, ny
        page.wait_for_timeout(1500)
    # 3: drag a third one around by hand
    nx, ny = centre(page, meshes.nth(2))
    glide(page, x, y, nx, ny, 400)
    page.wait_for_timeout(500)
    page.mouse.down()
    glide(page, nx, ny, nx + 90, ny - 20, 500)
    glide(page, nx + 90, ny - 20, nx - 70, ny + 25, 700)
    page.mouse.up()
    x, y = nx - 70, ny + 25
    page.wait_for_timeout(700)
    # 4: hover a fourth, then click its title: the peek opens on an orbit viewer that turns by itself
    nx, ny = centre(page, meshes.nth(3))
    glide(page, x, y, nx, ny, 400)
    page.wait_for_timeout(900)
    tx, ty = centre(page, page.locator("#p1 .dv-cards-card .dv-cards-title").nth(3))
    glide(page, nx, ny, tx, ty, 300)
    page.mouse.click(tx, ty)
    page.wait_for_selector("#p1 .dv-peek data-mesh.dv-mesh-live", timeout=8000)
    page.wait_for_timeout(1400)
    # 5: orbit and zoom in the peek
    px, py = centre(page, page.locator("#p1 .dv-peek data-mesh"))
    glide(page, tx, ty, px, py, 500)
    page.mouse.down()
    glide(page, px, py, px + 120, py + 30, 700)
    glide(page, px + 120, py + 30, px + 40, py - 20, 500)
    page.mouse.up()
    for _ in range(6):
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(90)
    page.wait_for_timeout(900)
    # 6: back on the grid, another card turns beside the open peek (the same one renderer serves both)
    # WHY index 6: the first row's right-hand cards sit under the open peek; the second row's first card is in view
    nx, ny = centre(page, meshes.nth(6))
    glide(page, px + 40, py - 20, nx, ny, 500)
    page.wait_for_timeout(1600)
    stats = page.evaluate("customElements.get('data-mesh').stats()")
    gl_name = page.evaluate("""(() => { const c = document.createElement('canvas').getContext('webgl'); const e = c && c.getExtension('WEBGL_debug_renderer_info'); return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unknown'; })()""")
    info["hero"] = {"seconds": round(time.time() - t0 + 0.7, 1), "renderer": gl_name, "stats": stats}
    video = page.video.path()
    ctx.close()
    webm = pathlib.Path(video)
    mp4 = OUT / "hero.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-ss", "0.8", "-vf", "setpts=PTS/1.15", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "27", "-preset", "slow", "-an", "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4", str(OUT / "hero.gif")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "6", "-i", str(mp4), "-frames:v", "1", str(OUT / "hero-poster.png")], check=True)
    webp((OUT / "hero-poster.png").read_bytes(), OUT / "hero-poster.webp")
    (OUT / "hero-poster.png").unlink()
    shutil.rmtree(vid, ignore_errors=True)


def stills(browser, base, info):
    info["stills"] = {}
    for dark in (False, True):
        for pid in PROPOSALS:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark" if dark else "light")
            ctx.add_init_script(f"try {{ localStorage.setItem('object-db/proposal', '{pid}'); localStorage.removeItem('data-ui-site-theme'); localStorage.removeItem('object-db/stream'); }} catch {{}}")
            page = ctx.new_page()
            page.goto(f"{base}/{PROTO}")
            wait_views(page)
            page.wait_for_timeout(1500)
            if pid == "shelf":
                m = page.locator("#p1 .dv-cards-card data-mesh").nth(1)
                page.mouse.move(*centre(page, m))
                page.wait_for_selector("#p1 .dv-cards-card data-mesh.dv-mesh-live", timeout=8000)
                page.wait_for_timeout(700)
            if pid == "tree":
                page.wait_for_selector("#p3-stage data-mesh.dv-mesh-live", timeout=10000)
                page.wait_for_timeout(900)
            if pid == "streams":
                page.select_option("#p4-pick", "household-blue-bin")
                wait_views(page)
                page.wait_for_timeout(1500)
            name = f"{pid}-{'dark' if dark else 'light'}"
            webp(page.screenshot(), OUT / f"{name}.webp")
            info["stills"][name] = page.evaluate("[...document.querySelectorAll('#stage data-views .dv-status')].map(e => e.textContent.split(' · ')[0])")
            if pid == "shelf":
                page.mouse.move(2, 2)
                page.locator("#p1 .dv-cards-card .dv-cards-title").nth(1).click()
                page.wait_for_selector("#p1 .dv-peek data-mesh.dv-mesh-live", timeout=8000)
                page.wait_for_timeout(1400)
                webp(page.screenshot(), OUT / f"shelf-peek-{'dark' if dark else 'light'}.webp")
            if pid == "ledger":
                page.locator(".proto-tabs [data-tab='1']").click()
                wait_views(page)
                page.wait_for_timeout(900)
                webp(page.screenshot(), OUT / f"ledger-types-{'dark' if dark else 'light'}.webp")
            ctx.close()
    # the phone: the shelf and its peek
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script("try { localStorage.setItem('object-db/proposal', 'shelf'); } catch {}")
    page = ctx.new_page()
    page.goto(f"{base}/{PROTO}")
    wait_views(page)
    page.wait_for_timeout(1200)
    page.locator("#p1").scroll_into_view_if_needed()
    webp(page.screenshot(), OUT / "shelf-390.webp")
    page.locator("#p1 .dv-cards-card .dv-cards-title").first.tap()
    page.wait_for_selector("#p1 .dv-peek data-mesh.dv-mesh-live", timeout=8000)
    page.wait_for_timeout(1200)
    webp(page.screenshot(), OUT / "shelf-390-peek.webp")
    ctx.close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    info = {}
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=GPU)
            hero(browser, base, info)
            stills(browser, base, info)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "capture.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(json.dumps(info["hero"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
