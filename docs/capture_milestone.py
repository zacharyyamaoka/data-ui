#!/usr/bin/env python3
"""Capture the milestone report's media from the real built site (dist/site), headless, into
reports/media/milestone-2026-10-26/ (gitignored):

    npm --prefix ~/data-ui run build
    ~/psu-atlas/.venv/bin/python ~/data-ui/docs/capture_milestone.py

- hero.mp4 / hero.gif: the landing hero switching table -> cards -> chart (a dot hovered) -> kanban -> graph, then
  the rack-wiring case's React Flow graph and the actuator-charts case's hover card. Recorded by Playwright from the
  running pages, re-encoded by ffmpeg (H.264, muted; a GIF fallback).
- view-<type>.png: each of the thirteen views on its gallery case, the live element alone, light, 1280 px wide;
  view-<type>-dark.png for four of them; landing-*.png, gallery-*.png.
It serves dist/site on a free 127.0.0.1 port and stops that server when it is done.
"""

from __future__ import annotations

import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "dist" / "site"
OUT = ROOT / "reports" / "media" / "milestone-2026-10-26"

# (type, case, preset): the thirteen views, the same presets the landing page's thumbnails show
VIEWS = [
    ("table", "robotparts-actuators", "By brand"), ("pivot", "models-benches", "Benchmarks"),
    ("list", "vibetracks-feature-tree", "Spec tree"), ("record", "dataclass-viewer", "Edit"),
    ("compare", "robotparts-compare", "Side by side"), ("cards", "robotparts-photos", "Actuators"),
    ("kanban", "vibetracks-board", "By status"), ("chart", "actuator-charts", "Ashby · torque vs mass"),
    ("kpi", "vibetracks-kpis", "KPIs"), ("calendar", "robotparts-calendar", "Month"),
    ("timeline", "robotparts-timeline", "Lanes by kind"), ("graph", "rack-wiring", "Wiring"),
    ("map", "robotparts-sellers-map", "Where sellers ship"),
]
DARK = {"table", "chart", "graph", "kanban"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def settle(page, ms=600):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def hover_dot(page, scope: str) -> bool:
    """Move the mouse onto a drawn dot of the chart under `scope` (a row with a photo when there is one)."""
    dot = page.evaluate("""(scope) => {
      const el = document.querySelector(scope + ' .dv-view-chart'); const view = el && el.vegaView; if (!view) return null;
      const rows = document.querySelector(scope).data.rows; const photo = new Set(rows.filter((r) => r.photo).map((r) => String(r.id)));
      const box = el.querySelector('canvas').getBoundingClientRect(); const [ox0, oy0] = view.origin(); const pad = view.padding();
      const dots = [];
      const walk = (mark, gx, gy) => { for (const item of mark.items || []) {
        if (mark.marktype === 'group') { for (const m of item.items || []) walk(m, gx + (item.x || 0), gy + (item.y || 0)); }
        else if (mark.marktype === 'symbol' && item.datum && item.datum._id !== undefined) dots.push({ id: String(item.datum._id), x: box.left + ox0 + pad.left + gx + item.x, y: box.top + oy0 + pad.top + gy + item.y }); } };
      walk(view.scenegraph().root, 0, 0);
      const alone = dots.filter((d) => photo.has(d.id) && dots.every((o) => o === d || Math.hypot(o.x - d.x, o.y - d.y) > 9));
      return alone.sort((a, b) => b.y - a.y)[Math.floor(alone.length / 2)] || null; }""", scope)
    if not dot:
        return False
    page.mouse.move(dot["x"] - 40, dot["y"] - 20, steps=8)
    page.mouse.move(dot["x"], dot["y"], steps=12)
    return True


def main() -> int:
    if not (SITE / "index.html").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()

            # ---- the hero video: one continuous recording across three pages
            raw = OUT / "raw"
            shutil.rmtree(raw, ignore_errors=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 760}, record_video_dir=str(raw), record_video_size={"width": 1280, "height": 760})
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/index.html")
            settle(page, 300)
            page.evaluate("window.scrollTo(0, document.querySelector('.hero-demo').getBoundingClientRect().top + scrollY - 70)")
            page.wait_for_timeout(1400)
            for name, hold in (("Cards", 1700), ("Chart", 900), ("Kanban", 1700), ("Graph", 2200)):
                page.click(f".hero-demo .segmented button[data-name='{name}']")
                page.wait_for_timeout(hold)
                if name == "Chart":
                    page.wait_for_selector("#hero .dv-view-chart[data-drawn]")
                    hover_dot(page, "#hero")
                    page.wait_for_timeout(1500)
                    page.mouse.move(5, 5)
            page.goto(f"{base}/gallery/rack-wiring/index.html")
            settle(page, 200)
            page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + scrollY - 70)")
            page.wait_for_timeout(1200)
            node = page.locator("#example .react-flow__node[data-id='psu']")
            node.hover()
            page.wait_for_timeout(500)
            node.click()
            page.wait_for_selector("#example .dv-peek:not([hidden])")
            page.wait_for_timeout(1800)
            page.goto(f"{base}/gallery/actuator-charts/index.html")
            settle(page, 200)
            page.evaluate("window.scrollTo(0, document.querySelector('#example').getBoundingClientRect().top + scrollY - 70)")
            page.wait_for_selector("#example .dv-view-chart[data-drawn]")
            page.wait_for_timeout(600)
            hover_dot(page, "#example")
            page.wait_for_timeout(2000)
            video = page.video.path()
            ctx.close()
            mp4, gif = OUT / "hero.mp4", OUT / "hero.gif"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26",
                            "-vf", "scale=1280:-2", "-movflags", "+faststart", str(mp4)], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vf",
                            "fps=8,scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer", str(gif)], check=True)
            shutil.rmtree(raw, ignore_errors=True)

            # ---- each view, alone
            for kind, case, preset in VIEWS:
                for dark in (False, True) if kind in DARK else (False,):
                    vctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark" if dark else "light")
                    page = vctx.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(f"{base}/gallery/{case}/index.html#view={slug(preset)}")
                    page.wait_for_selector("#example[data-view]", timeout=20000)
                    settle(page, 1800)
                    page.locator(".live").screenshot(path=str(OUT / f"view-{kind}{'-dark' if dark else ''}.png"))
                    vctx.close()

            # ---- the landing page and the gallery
            for name, path, w, h, dark, full in (("landing", "index.html", 1280, 900, False, False), ("landing-dark", "index.html", 1280, 900, True, False),
                                                 ("landing-phone", "index.html", 390, 844, False, False), ("gallery", "gallery/index.html?type=chart", 1280, 900, False, False),
                                                 ("case-compare", "gallery/robotparts-compare/index.html", 1280, 900, False, True)):
                vctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme="dark" if dark else "light", device_scale_factor=2 if w < 400 else 1, is_mobile=w < 400)
                page = vctx.new_page()
                page.goto(f"{base}/{path}")
                settle(page, 1500)
                page.locator(".hero-play").click() if path == "index.html" else None
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
                vctx.close()
            vctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = vctx.new_page()
            page.goto(f"{base}/index.html")
            settle(page, 300)
            for _ in range(10):
                page.mouse.wheel(0, 700)
                page.wait_for_timeout(300)
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, document.querySelector('.thumbs').getBoundingClientRect().top + scrollY - 70)")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / "landing-thumbs.png"))
            vctx.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    for f in sorted(OUT.iterdir()):
        print(f"{f.name}: {f.stat().st_size:,} bytes")
    print("page errors:", errors[:5] or "none")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
