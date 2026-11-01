"""Capture the dashboards report's media from the built site (dist/site), headless: the hero video of the real Vibe
Tracks dashboard (filter the rail, cross-filter by clicking a chart bar, drill into a run) and full-width stills of
each dashboard case, light and dark.

    ~/psu-atlas/.venv/bin/python docs/capture_dashboards.py ~/data-ui/reports/media/dashboards

Serves dist/site on a free 127.0.0.1 port and stops it when done. ffmpeg turns the recording into an mp4 and a GIF."""

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
CASES = ["vibetracks-dashboard", "vibetracks-runs", "vibetracks-track", "pid-tuning", "sim-to-real", "trajectory-tracking"]


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ready(page):
    page.wait_for_function("""() => { const els = [...document.querySelectorAll('#example .dd-panel data-views')];
      return els.length && els.every((e) => e.dataset.view && /of/.test(e.querySelector('.dv-status').textContent)); }""", timeout=30000)
    page.wait_for_timeout(1200)


def bar(page, value):
    return page.evaluate("""(value) => {
      const el = document.querySelector('#example [data-panel="runs-by-track"] .dv-view-chart'); const view = el.vegaView;
      const c = el.querySelector('canvas').getBoundingClientRect(); const o = view.origin(); let hit = null;
      const walk = (n, ox, oy) => { if (!n || hit) return; for (const it of n.items || []) {
        if (it.datum && it.datum.track_title === value && it.mark && it.mark.marktype === 'rect') { hit = { it, ox, oy }; return; }
        if (it.items) walk(it, ox + (it.x || 0), oy + (it.y || 0)); } };
      walk(view.scenegraph().root, 0, 0); if (!hit) return null; const b = hit.it.bounds;
      return { x: c.left + o[0] + hit.ox + (b.x1 + b.x2) / 2, y: c.top + o[1] + hit.oy + (b.y1 + b.y2) / 2 }; }""", value)


def glide(page, x, y, steps=18):
    page.mouse.move(x, y, steps=steps)


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
            # ---- the hero: a 1440 x 900 recording of the real case page
            raw = OUT / "raw"
            raw.mkdir(exist_ok=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(raw), record_video_size={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(f"{base}/gallery/vibetracks-dashboard/index.html")
            ready(page)
            page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + scrollY - 8)")
            page.wait_for_timeout(1400)
            box = page.locator("data-facets[data-dataset=tracks] input[data-p=health][data-value=green]").bounding_box()
            glide(page, box["x"] + 6, box["y"] + 6)
            page.mouse.click(box["x"] + 6, box["y"] + 6)
            log.append(("rail: health = green", page.evaluate("document.querySelector('#example [data-panel=tracks] .dv-status').textContent")))
            page.wait_for_timeout(2200)
            page.mouse.click(box["x"] + 6, box["y"] + 6)
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.querySelector('#example [data-panel=tracks]').getBoundingClientRect().top + scrollY - 120)")
            page.wait_for_timeout(1000)
            at = bar(page, "Vibe Tracks")
            glide(page, at["x"], at["y"], steps=25)
            page.wait_for_timeout(500)
            page.mouse.click(at["x"], at["y"])
            page.wait_for_timeout(1800)
            log.append(("cross-filter: bar Vibe Tracks", page.inner_text("#example .dd-chips")))
            page.evaluate("window.scrollTo(0, document.querySelector('#example [data-panel=runs]').getBoundingClientRect().top + scrollY - 160)")
            page.wait_for_timeout(1200)
            row = page.locator("#example [data-panel=runs] tr.dv-row").nth(1).bounding_box()
            glide(page, row["x"] + 200, row["y"] + 12)
            page.mouse.click(row["x"] + 200, row["y"] + 12)
            page.wait_for_timeout(2600)
            log.append(("drill", page.inner_text("#example .dd-drill .dv-peek h2")))
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            page.wait_for_timeout(1200)
            video = page.video.path()
            ctx.close()
            webm = OUT / "hero.webm"
            shutil.move(video, webm)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "slow", "-movflags", "+faststart", "-an", str(OUT / "hero.mp4")], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf", "fps=8,scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(OUT / "hero.gif")], check=True)
            webm.unlink()
            shutil.rmtree(raw, ignore_errors=True)
            # ---- stills: the dashboard element, full width, light and dark
            for case in CASES:
                for dark in (False, True):
                    c = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark" if dark else "light")
                    pg = c.new_page()
                    pg.goto(f"{base}/gallery/{case}/index.html")
                    ready(pg)
                    name = f"{case}-{'dark' if dark else 'light'}"
                    pg.locator("#example").screenshot(path=str(OUT / f"{name}.png"))
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / f"{name}.png"), "-q:v", "4", str(OUT / f"{name}.jpg")], check=True)
                    (OUT / f"{name}.png").unlink()
                    c.close()
            # ---- a 390 px phone still of the main case
            c = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
            pg = c.new_page()
            pg.goto(f"{base}/gallery/vibetracks-dashboard/index.html")
            ready(pg)
            pg.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + scrollY - 8)")
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / "phone.png"))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "phone.png"), "-q:v", "4", str(OUT / "phone.jpg")], check=True)
            (OUT / "phone.png").unlink()
            c.close()
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    (OUT / "capture.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print(json.dumps(log, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
