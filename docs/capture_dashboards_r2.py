"""Captures for the round-2 dashboards report (reports/data-ui-dashboards-r2-2026-10-26.html), from the REAL built pages.

    ~/psu-atlas/.venv/bin/python docs/capture_dashboards_r2.py hero      # the hero video (PID tuning playing)
    ~/psu-atlas/.venv/bin/python docs/capture_dashboards_r2.py shots     # every dashboard, light and dark, full width
    ~/psu-atlas/.venv/bin/python docs/capture_dashboards_r2.py onion     # the onion card with its opacity slider

Serves dist/site on a free port (stopped at the end), drives headless Chromium, writes into
~/data-ui/reports/media/dashboards-r2/ (gitignored media). ffmpeg makes the mp4 and the GIF fallback."""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "dist" / "site"
OUT = Path("~/data-ui/reports/media/dashboards-r2")
CASES = [c for c in __import__("os").environ.get("CASES", "").split(",") if c] or ["pid-tuning", "sim-to-real", "trajectory-tracking", "vibetracks-dashboard", "vibetracks-runs", "vibetracks-track", "dashboard-cards", "playback-proposals"]
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--autoplay-policy=no-user-gesture-required"]


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return srv, f"http://127.0.0.1:{port}"


def ready(page):
    page.wait_for_function("() => { const d = document.querySelector('#example'); return d && d.dataset.view && [...d.querySelectorAll('.dd-panel data-views')].every((e) => e.dataset.view); }", timeout=60000)
    # wake every lazy card (videos, WebGL) by scrolling the page through once
    h = page.evaluate("document.body.scrollHeight")
    for y in range(0, h, 600):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(150)
    page.wait_for_timeout(800)
    # every meshed robot drawn (scene3d.robot), not its stick fallback while the GLB loads
    try:
        page.wait_for_function("""() => [...document.querySelectorAll('#example .dv-scene3d')].every((r) => { const h = r.scene3d;
          const rob = h && h.robot && h.robot(); return !rob || rob.state === 'idle' && !rob.url || rob.state === 'failed' || (rob.state === 'ready' && rob.drawn) || !rob.url; })""", timeout=20000)
    except Exception:  # noqa: BLE001
        pass


def smooth(page, y, ms=1200):
    page.evaluate("""([y, ms]) => new Promise((done) => { const y0 = scrollY, t0 = performance.now();
      const step = (now) => { const f = Math.min(1, (now - t0) / ms), e = f < .5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
        scrollTo(0, y0 + (y - y0) * e); if (f < 1) requestAnimationFrame(step); else done(); }; requestAnimationFrame(step); })""", [y, ms])


def top_of(page, key):
    return page.evaluate(f"() => document.querySelector('#example [data-panel=\"{key}\"]').getBoundingClientRect().top + scrollY")


def hero(base, b):
    vid_dir = OUT / "hero-raw"
    vid_dir.mkdir(parents=True, exist_ok=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark", record_video_dir=str(vid_dir), record_video_size={"width": 1440, "height": 1000})
    page = ctx.new_page()
    page.goto(f"{base}/gallery/pid-tuning/index.html")
    ready(page)
    page.evaluate("() => document.querySelector('#example').clock.seek(0)")
    t_rec = time.time()
    page.evaluate(f"window.scrollTo(0, {top_of(page, 'stop-p90-tuned') - 14})")
    page.wait_for_timeout(500)
    page.click("#example [data-panel=playback] [data-act=play]")
    page.wait_for_timeout(6500)
    smooth(page, top_of(page, "error-over-time") - 14, 1300)
    page.wait_for_timeout(3000)
    ov = "#example [data-panel='factory-vs-tuned-sim']"
    for mode in ("Onion", "Difference", "Side", "Wipe"):
        page.locator(f"{ov} button[data-mode={mode.lower()}]").click()
        page.wait_for_timeout(1500)
    page.click("#example [data-panel=playback] [data-act=play]")
    page.wait_for_timeout(600)
    lead = time.time() - t_rec
    path = page.video.path()
    ctx.close()
    raw = Path(path)
    # trim the load and the lazy scroll before the hero starts: keep the last `lead` seconds
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)]).decode().strip())
    start = max(0.0, dur - lead)
    mp4 = OUT / "hero.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(raw), "-vf", "scale=1280:-2", "-c:v", "libx264", "-crf", "26", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=8,scale=720:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(OUT / "hero.gif")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3", "-i", str(mp4), "-frames:v", "1", "-q:v", "3", str(OUT / "hero-poster.jpg")], check=True)
    print("hero", mp4, f"{lead:.1f} s", mp4.stat().st_size // 1024, "KB")


def shots(base, b):
    for case in CASES:
        for dark in (False, True):
            ctx = b.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark" if dark else "light")
            page = ctx.new_page()
            r = page.goto(f"{base}/gallery/{case}/index.html")
            if not r or not r.ok:
                ctx.close()
                continue
            ready(page)
            page.evaluate("() => { const d = document.querySelector('#example'); d.clock && d.clock.seek(3.2); scrollTo(0, 0); }")
            page.wait_for_timeout(900)
            png = OUT / f"{case}-{'dark' if dark else 'light'}.png"
            page.locator("#example").screenshot(path=str(png))
            jpg = png.with_suffix(".jpg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-vf", "scale=1200:-2", "-q:v", "4", str(jpg)], check=True)
            png.unlink()
            print(jpg, jpg.stat().st_size // 1024, "KB")
            ctx.close()


def onion(base, b):
    for dark in (False, True):
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, color_scheme="dark" if dark else "light", device_scale_factor=2)
        page = ctx.new_page()
        page.goto(f"{base}/gallery/dashboard-cards/index.html")
        ready(page)
        page.evaluate("() => document.querySelector('#example').clock.seek(3.2)")
        ov = page.locator("#example [data-panel='overlay']")
        ov.scroll_into_view_if_needed()
        page.locator("#example [data-panel='overlay'] button[data-mode=onion]").click()
        page.locator("#example [data-panel='overlay'] input[type=range]").fill("0.35")
        page.wait_for_timeout(700)
        ov.screenshot(path=str(OUT / f"onion-{'dark' if dark else 'light'}.png"))
        ctx.close()
    print("onion shots")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    srv, base = serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=ARGS)
            for what in sys.argv[1:] or ["hero", "shots", "onion"]:
                {"hero": hero, "shots": shots, "onion": onion}[what](base, b)
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
