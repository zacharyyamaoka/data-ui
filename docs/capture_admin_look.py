"""Capture the admin-look report's media from the built site (dist/site), headless: the hero video of the admin-shopify
app page (Organizations: hover a summary label, open Search and filter, + Kind › Customer, Cancel; then the rail to
Deals and the view chip to Won), stills of both screens light and dark at 2000 x 1010 (the size of Zach's screenshots),
the search open, the 390 px phone, and the gallery page.

    ~/psu-atlas/.venv/bin/python docs/capture_admin_look.py ~/data-ui/reports/media/admin-look

Serves dist/site on a free 127.0.0.1 port and stops it when done. ffmpeg turns the recording into an mp4 and a GIF.
Zach's four reference screenshots are copied in by the report builder, not here."""

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
APP = "gallery/admin-shopify/app/index.html"


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ready(page):
    page.wait_for_function("() => { const s = document.querySelector('data-summary'); return s && s.cells.length && document.querySelector('#list .dv-row'); }", timeout=30000)
    page.wait_for_timeout(500)


def jpg(png):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-q:v", "3", str(png.with_suffix(".jpg"))], check=True)
    png.unlink()


def glide(page, sel, dx=0.5, dy=0.5, steps=18):
    box = page.locator(sel).first.bounding_box()
    x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
    page.mouse.move(x, y, steps=steps)
    return x, y


def main():
    p_ = port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(p_), "--bind", "127.0.0.1", "--directory", str(ROOT / "dist" / "site")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{p_}"
    time.sleep(0.8)
    log = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            # ---- the hero: 1440 x 900, dark (his screenshots are dark)
            raw = OUT / "raw"
            raw.mkdir(exist_ok=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark", record_video_dir=str(raw), record_video_size={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(f"{base}/{APP}?theme=dark#organizations")
            ready(page)
            page.wait_for_timeout(900)
            glide(page, "data-summary .dv-summary-cell:nth-child(2) .dv-summary-label")
            page.wait_for_timeout(1500)
            x, y = glide(page, "#list .dv-qinput", 0.1)
            page.mouse.click(x, y)
            page.wait_for_timeout(900)
            x, y = glide(page, "#list .dv-fchip-body[data-p=kind]")
            page.mouse.click(x, y)
            page.wait_for_timeout(700)
            x, y = glide(page, "#list .dv-fchip-menu input[value=Customer]")
            page.mouse.click(x, y)
            page.wait_for_timeout(1500)
            log.append(("+ Kind › Customer", page.evaluate("() => [document.querySelectorAll('#list tbody tr.dv-row').length, document.querySelector('#list .dv-fchip-on').textContent.trim()]")))
            page.keyboard.press("Escape")
            x, y = glide(page, "#list .dv-qcancel")
            page.mouse.click(x, y)
            page.wait_for_timeout(1000)
            x, y = glide(page, "#nav .dv-rail-dest[data-id=deals]")
            page.mouse.click(x, y)
            ready(page)
            page.wait_for_timeout(1300)
            log.append(("Deals summary", page.evaluate("() => document.querySelector('data-summary').cells.map((c) => [c.label, c.value])")))
            x, y = glide(page, "#list .dv-viewchip")
            page.mouse.click(x, y)
            page.wait_for_timeout(900)
            row = page.locator("#list .dv-viewmenu .dv-vm-row", has_text="Won").first
            if row.count():
                bx = row.bounding_box()
                page.mouse.move(bx["x"] + 40, bx["y"] + bx["height"] / 2, steps=12)
                page.mouse.click(bx["x"] + 40, bx["y"] + bx["height"] / 2)
            page.wait_for_timeout(1300)
            log.append(("chip › Won", page.evaluate("() => [document.querySelector('#list .dv-viewchip').textContent.trim(), document.querySelector('#nav [aria-current=page]').dataset.id]")))
            x, y = glide(page, "#nav .dv-rail-dest[data-id=customers]")
            page.mouse.click(x, y)
            ready(page)
            page.wait_for_timeout(1200)
            video = page.video.path()
            ctx.close()
            webm = OUT / "hero.webm"
            shutil.move(video, webm)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "slow", "-movflags", "+faststart", "-an", str(OUT / "hero.mp4")], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf", "fps=8,scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(OUT / "hero.gif")], check=True)
            webm.unlink()
            shutil.rmtree(raw, ignore_errors=True)
            # ---- stills at his screenshots' size, both screens, both themes
            for screen in ("organizations", "pipeline"):
                for theme in ("dark", "light"):
                    c = b.new_context(viewport={"width": 2000, "height": 1010}, color_scheme=theme)
                    pg = c.new_page()
                    pg.goto(f"{base}/{APP}?theme={theme}#{screen}")
                    ready(pg)
                    shot = OUT / f"{screen}-{theme}.png"
                    pg.screenshot(path=str(shot))
                    jpg(shot)
                    if screen == "organizations" and theme == "dark":
                        # the summary card alone, as his crop (3.webp)
                        pg.locator("data-summary").screenshot(path=str(OUT / "summary-dark.png"))
                        jpg(OUT / "summary-dark.png")
                        pg.click("#list .dv-qinput")
                        pg.click("#list .dv-fchip-body[data-p=kind]")
                        pg.check("#list .dv-fchip-menu input[value=Customer]")
                        pg.wait_for_timeout(500)
                        pg.screenshot(path=str(OUT / "search-dark.png"))
                        jpg(OUT / "search-dark.png")
                    c.close()
            # ---- the phone, the rail folded to icons
            c = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
            pg = c.new_page()
            pg.goto(f"{base}/{APP}?theme=light#organizations")
            ready(pg)
            pg.evaluate("() => { document.querySelector('#nav').mode = 'collapsed'; }")
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / "phone.png"))
            jpg(OUT / "phone.png")
            c.close()
            # ---- the gallery page (the same file, the kit's own case page)
            c = b.new_context(viewport={"width": 1440, "height": 1000})
            pg = c.new_page()
            pg.goto(f"{base}/gallery/admin-shopify/index.html")
            pg.wait_for_function("() => { const s = document.querySelector('data-summary'); return s && s.cells.length && document.querySelector('#example .dv-row'); }", timeout=30000)
            pg.evaluate("window.scrollTo(0, document.querySelector('.live').getBoundingClientRect().top + scrollY - 8)")
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / "gallery-light.png"))
            jpg(OUT / "gallery-light.png")
            c.close()
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    (OUT / "capture.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(json.dumps(log, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
