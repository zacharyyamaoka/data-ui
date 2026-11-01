"""Capture the map report's media from the built site (dist/site), headless: the hero video of the real map in a
dashboard (pan, select a district, the KPI and the trend cross-filter, select another, clear) and a still of every map
case's first view, light and dark, plus two phone captures.

    ~/psu-atlas/.venv/bin/python docs/capture_map.py ~/data-ui/reports/media/map

Serves dist/site on a free 127.0.0.1 port and stops it when done. ffmpeg turns the recording into an mp4 and a GIF."""

import json
import pathlib
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "browser"))
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CASES = sorted(p.name for p in (ROOT / "gallery" / "examples").iterdir() if p.name.startswith("map-") and (p / "views.base").exists())
SETTLE = """(s) => { const e = document.querySelector(s); const m = e && e.dvMap; return m && m.loaded() && !m.isMoving() && m.areTilesLoaded(); }"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page, sel="#example .dv-view-map", extra=900):
    page.wait_for_selector(f"{sel}[data-zoom]", timeout=30000)
    page.wait_for_function(SETTLE, arg=sel, timeout=30000)
    page.wait_for_timeout(extra)


def click_region(page, sel, rd):
    """Click a pixel deep inside the region whose rd is `rd` (its ±3 px neighbours are the same feature)."""
    at = page.evaluate("""([s, rd]) => { const m = document.querySelector(s).dvMap, c = m.getCanvas().getBoundingClientRect();
      for (let y = 10; y < c.height - 10; y += 4) for (let x = 10; x < c.width - 10; x += 4) {
        const f = m.queryRenderedFeatures([x, y], { layers: ['dvl-0'] })[0];
        if (!f || f.properties.rd !== rd) continue;
        if ([[-3, 0], [3, 0], [0, -3], [0, 3]].every(([dx, dy]) => { const g = m.queryRenderedFeatures([x + dx, y + dy], { layers: ['dvl-0'] })[0]; return g && g.id === f.id; })) return [c.x + x, c.y + y];
      } return null; }""", [sel, rd])
    page.mouse.move(*at, steps=12)
    page.wait_for_timeout(250)
    page.mouse.click(*at)


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT / "dist" / "site")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    time.sleep(0.8)
    meta = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            # ---- the hero: the map in a dashboard, cross-filtering a KPI and a trend chart
            raw = OUT / "raw"
            raw.mkdir(exist_ok=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(raw), record_video_size={"width": 1440, "height": 900})
            page = ctx.new_page()
            t_rec = time.monotonic()
            page.goto(f"{base}/gallery/map-dashboard/index.html")
            sel = "#example .dd-panel .dv-view-map"
            settle(page, sel, 300)
            page.evaluate("() => { const el = document.querySelector('#example'); window.scrollTo(0, el.getBoundingClientRect().top + scrollY - 70); }")
            page.wait_for_timeout(600)
            # WHY a cut: the recording starts at page load; the hero starts once the dashboard is drawn and in view
            start = max(0.0, time.monotonic() - t_rec - 0.4)
            page.wait_for_timeout(600)
            box = page.locator(sel + " .dv-map-stage").bounding_box()
            cx, cy = box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.55
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx - 140, cy - 60, steps=30)
            page.mouse.up()
            page.wait_for_timeout(700)
            page.mouse.move(cx, cy)
            for _ in range(3):
                page.mouse.wheel(0, -120)
                page.wait_for_timeout(180)
            page.wait_for_function(SETTLE, arg=sel, timeout=30000)
            page.wait_for_timeout(700)
            click_region(page, sel, "capital")
            page.wait_for_timeout(2400)
            meta["kpi_capital"] = page.inner_text("#example data-kpi .dv-kpi-value").split("\n")[0]
            click_region(page, sel, "metro-vancouver")
            page.wait_for_timeout(2400)
            meta["kpi_metro"] = page.inner_text("#example data-kpi .dv-kpi-value").split("\n")[0]
            click_region(page, sel, "metro-vancouver")
            page.wait_for_timeout(1800)
            meta["kpi_all"] = page.inner_text("#example data-kpi .dv-kpi-value").split("\n")[0]
            webm = page.video.path()
            ctx.close()
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-ss", f"{start:.2f}", "-vf", "setpts=PTS/1.3,scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "30", "-preset", "slow", "-movflags", "+faststart", "-an", str(OUT / "hero.mp4")], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(webm), "-vf", "setpts=PTS/1.3,fps=5,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=48[p];[b][p]paletteuse=dither=bayer:bayer_scale=5", str(OUT / "hero.gif")], check=True)
            meta["hero_seconds"] = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(OUT / "hero.mp4")], capture_output=True, text=True).stdout.strip())

            # ---- a still of each case's first view, light and dark
            for dark in (False, True):
                ctx = b.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark" if dark else "light")
                for case in CASES:
                    page = ctx.new_page()
                    page.goto(f"{base}/gallery/{case}/index.html")
                    dash = case in ("map-dashboard", "map-region-filter")
                    s = "#example .dd-panel .dv-view-map" if dash else "#example .dv-view-map"
                    if case == "map-small-multiples":
                        page.wait_for_function("() => [...document.querySelectorAll('#example .dv-map-cell')].length === 6 && [...document.querySelectorAll('#example .dv-map-cell')].every((c) => c.dvMap && c.dvMap.loaded() && c.dvMap.areTilesLoaded())", timeout=30000)
                        page.wait_for_timeout(1200)
                    else:
                        settle(page, s)
                    if case == "map-swipe":
                        page.wait_for_timeout(800)
                    name = f"{case}-{'dark' if dark else 'light'}"
                    page.locator("#example").screenshot(path=str(OUT / f"{name}.png"))
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / f"{name}.png"), "-vf", "scale=560:-1", "-q:v", "7", str(OUT / f"{name}.jpg")], check=True)
                    meta.setdefault("answers", {})[case] = page.evaluate("(s) => { const a = document.querySelector(s + ' .dv-map-answer'); return a ? a.textContent : ''; }", s)
                    page.close()
                ctx.close()
            # ---- two phone captures
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
            for case in ("map-bc-disposal", "map-service-rings"):
                page = ctx.new_page()
                page.goto(f"{base}/gallery/{case}/index.html")
                settle(page)
                page.evaluate("() => { const el = document.querySelector('#example'); window.scrollTo(0, el.getBoundingClientRect().top + scrollY - 60); }")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUT / f"phone-{case}.png"))
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / f"phone-{case}.png"), "-vf", "scale=390:-1", "-q:v", "5", str(OUT / f"phone-{case}.jpg")], check=True)
                page.close()
            ctx.close()
            b.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in meta.items() if k != "answers"}))


if __name__ == "__main__":
    main()
