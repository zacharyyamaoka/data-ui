"""Record the dashboard editor's hero from the real page: the Servo gallery case on the built site, the same page a reader opens.

    ~/psu-atlas/.venv/bin/python docs/capture_dashboard_editor.py [OUT_DIR]     # after npm run build

Serves dist/site on a free 127.0.0.1 port, stops it when done, and writes OUT_DIR (default ~/data-ui/reports/media/
dash-editor-hero): raw/*.webm, Playwright's own screencast at 1280 x 800, marks.json, hero.mp4 and hero.gif. One take: Edit, drag a
panel, reorder in the outline, place a queued item, Save with the diff. Nothing is drawn on it but the pointer, which headless
video does not show. Then ffmpeg trims the page load off the head, with no speed change.
"""

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("~/data-ui/reports/media/dash-editor-hero")
(OUT / "raw").mkdir(parents=True, exist_ok=True)
PAGE = "/gallery/robotics-servo/index.html"
W, H = 1280, 800
D = "#example"
OUTLINE = '[data-dde-pane="outline"]'
OPTIONS = '[data-dde-pane="options"]'
marks = {}
t0 = None


def mark(name):
    marks[name] = round(time.monotonic() - t0, 2)
    print(f"{marks[name]:6.2f}s  {name}", flush=True)


CURSOR = """
addEventListener('DOMContentLoaded', () => {
  const d = document.createElement('div'); d.id = '__cur';
  d.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
    'background:rgba(220,38,38,.35);border:2px solid rgba(220,38,38,.9);z-index:2147483647;pointer-events:none;transition:transform .12s';
  document.body.appendChild(d);
  const at = (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; };
  addEventListener('mousemove', at, true);
  addEventListener('dragover', at, true);
  addEventListener('mousedown', () => { d.style.transform = 'scale(.6)'; }, true);
  addEventListener('mouseup', () => { d.style.transform = ''; }, true);
  addEventListener('dragend', () => { d.style.transform = ''; }, true);
});"""


def center(page, sel):
    b = page.locator(sel).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def glide(page, x, y, steps=18, pause=12):
    """The pointer moves like a hand: small steps, a few milliseconds each."""
    for _ in range(1):
        page.mouse.move(x, y, steps=steps)
    page.wait_for_timeout(pause)


def press(page, sel):
    x, y = center(page, sel)
    glide(page, x, y)
    page.wait_for_timeout(160)
    page.mouse.down()
    page.mouse.up()


def order(page):
    return page.evaluate(f"""() => [...document.querySelector('{D} .dd-grid').gridstack.engine.nodes].sort((a, b) => a.y - b.y || a.x - b.x).map((n) => n.id)""")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def take(browser, base):
    global t0
    ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light", record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H})
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()
    t0 = time.monotonic()
    page.goto(base + PAGE)
    page.wait_for_selector(f'{D}[data-view="dashboard"] [data-act="edit"]', timeout=30000)
    page.wait_for_function(f"""() => [...document.querySelectorAll('{D} .dd-panel data-views')].every((e) => e.dataset.view)""", timeout=30000)
    page.evaluate(f"() => window.scrollTo(0, document.querySelector('{D}').getBoundingClientRect().top + scrollY - 62)")
    page.wait_for_timeout(1300)
    mark("start")
    # Edit
    press(page, f'{D} [data-act="edit"]')
    page.wait_for_selector(f"{D}[data-editing] {OUTLINE}", timeout=15000)
    page.wait_for_selector(f"{D} .dd-grid.grid-stack .grid-stack-item", timeout=15000)
    page.wait_for_function(f"""() => [...document.querySelectorAll('{D} .dd-panel data-views')].every((e) => e.dataset.view)""", timeout=30000)
    page.wait_for_timeout(1100)
    mark("editing")
    # drag a panel: Playback, by its grip, up over Runs (closed loop: the grid previews the outcome)
    page.hover(f'{D} .dd-panel[data-panel="playback"]')
    g = page.locator(f'{D} .dd-panel[data-panel="playback"] .dde-grip').bounding_box()
    x, y = g["x"] + 60, g["y"] + g["height"] / 2
    glide(page, x, y)
    page.wait_for_timeout(250)
    page.mouse.down()
    page.mouse.move(x + 6, y - 6, steps=4)
    x, y = x + 6, y - 6
    for _ in range(40):
        y -= 14
        page.mouse.move(x, y, steps=2)
        page.wait_for_timeout(28)
        o = order(page)
        if o.index("playback") + 1 < len(o) and o[o.index("playback") + 1] == "runs":
            break
    page.wait_for_timeout(350)
    page.mouse.up()
    page.wait_for_timeout(1000)
    mark("canvas drag")
    # the outline: Velocity above Angle, by hand; the canvas follows at once
    src = f'{OUTLINE} .dde-row[data-key="velocity"]'
    dst = page.locator(f'{OUTLINE} .dde-row[data-key="angle"]').bounding_box()
    sx, sy = center(page, src)
    glide(page, sx, sy)
    page.wait_for_timeout(250)
    page.mouse.down()
    page.mouse.move(sx, sy - 6, steps=3)
    page.mouse.move(dst["x"] + 80, dst["y"] + 4, steps=22)
    page.wait_for_timeout(350)
    page.mouse.up()
    page.wait_for_timeout(1100)
    mark("outline drag")
    # the queue: drag a saved item onto the grid, before Runs
    item = f'{OUTLINE} .dde-q[data-item="held-out-runs"]'
    target = page.locator(f'{D} .dd-panel[data-panel="runs"]').bounding_box()
    sx, sy = center(page, item)
    glide(page, sx, sy)
    page.wait_for_timeout(250)
    page.mouse.down()
    page.mouse.move(sx + 8, sy - 4, steps=3)
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + 10, steps=26)
    page.wait_for_timeout(450)
    page.mouse.up()
    page.wait_for_timeout(1300)
    mark("queue drag")
    # Save: the diff first
    press(page, f'{D} [data-act="edit-save"]')
    page.wait_for_selector(f"{OPTIONS} .dde-diff", timeout=15000)
    page.wait_for_timeout(2600)
    mark("review")
    press(page, f'{OPTIONS} [data-dde="save-go"]')
    page.wait_for_function(f"""() => /^Saved/.test(document.querySelector('{D} .dde-status').textContent)""", timeout=15000)
    page.wait_for_timeout(1500)
    mark("saved")
    video = page.video
    ctx.close()
    return Path(video.path())


def encode(raw):
    a, b = marks["start"] - 0.4, marks["saved"]
    mp4, gif = OUT / "hero.mp4", OUT / "hero.gif"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-vf", f"trim=start={a}:end={b},setpts=PTS-STARTPTS,fps=20,format=yuv420p",
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "veryslow", "-crf", "27", "-tune", "animation", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-vf",
                    "fps=4,scale=520:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=32:stats_mode=diff[p];[s1][p]paletteuse=dither=none:diff_mode=rectangle", str(gif)], check=True)
    print(f"hero.mp4 {mp4.stat().st_size / 1e3:.0f} KB, {b - a:.1f} s; hero.gif {gif.stat().st_size / 1e3:.0f} KB", flush=True)


def main():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT / "dist" / "site")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + PAGE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            raw = take(browser, base)
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    (OUT / "marks.json").write_text(json.dumps(marks, indent=1) + "\n", encoding="utf-8")
    encode(raw)


if __name__ == "__main__":
    main()
