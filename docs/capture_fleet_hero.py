"""Record the fleet map's hero video from the real built page: a click on a robot, its runs, a run's playback.

Usage (a static server on dist/site first, e.g. python3 -m http.server 47614 --bind 127.0.0.1 --directory dist/site):
    PLAYWRIGHT_BROWSERS_PATH=<a cache with chromium> ~/psu-atlas/.venv/bin/python \
        docs/capture_fleet_hero.py http://127.0.0.1:47614 <out dir>
Writes <out dir>/raw/*.webm (Playwright's own screencast of the page), <out dir>/marks.json (seconds since the context
opened for each step, and what the page said at that step) and, with ffmpeg on the PATH, hero.mp4 and hero.gif:
one take, its page-load head trimmed and cropped to the dashboard, no speed change and nothing drawn on top. The red ring
is a pointer this script adds, because a headless screencast draws no cursor.

WHY a tall viewport, not a scroll: the point of the take is that one click moves everything, so the map, the runs, the
playback and a plot are in one frame from the first second to the last.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
(OUT / "raw").mkdir(parents=True, exist_ok=True)
for old in (OUT / "raw").glob("*.webm"):
    old.unlink()
WIDTH, HEIGHT = 1280, 1460
CASE = "robotics-fleet"
D = "#example"

marks = {}
started = None


def mark(name, **said):
    marks[name] = {"at": round(time.monotonic() - started, 2), **said}
    print(f"{marks[name]['at']:6.2f}s  {name}  {said or ''}", flush=True)


CURSOR = """
  addEventListener('DOMContentLoaded', () => {
    const dot = document.createElement('div'); dot.id = '__cursor';
    dot.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
      'background:rgba(220,38,38,.35);border:2px solid rgba(220,38,38,.9);z-index:2147483647;pointer-events:none;transition:transform .12s';
    document.body.appendChild(dot);
    addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { dot.style.transform = 'scale(.6)'; }, true);
    addEventListener('mouseup', () => { dot.style.transform = ''; }, true);
  });"""
SAID = f"""() => {{ const d = document.querySelector('{D}'); const s = (k) => (d.state.select[k] || {{ values: [] }}).values;
  return {{ robot: s('deployments'), run: s('runs'), marked: [...d.querySelectorAll('.dv-map-marker.dv-sel')].map((m) => m.title), span: [d.clock.start, d.clock.end], t: d.clock.t }}; }}"""


def centre(page, selector):
    box = page.locator(selector).first.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def glide_click(page, selector, *, steps=26, hold=0.18):
    x, y = centre(page, selector)
    page.mouse.move(x, y, steps=steps)
    time.sleep(hold)
    page.mouse.click(x, y)


def wait_robot(page, deployment):
    page.wait_for_function(f"(want) => {{ const s = document.querySelector('{D}').state.select.deployments; return !!s && s.values.length === 1 && s.values[0] === want; }}", arg=deployment, timeout=8000)


def wait_marked(page, title):
    page.wait_for_function(f"(want) => [...document.querySelectorAll('{D} .dv-map-marker.dv-sel')].some((m) => m.title === want)", arg=title, timeout=8000)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, record_video_dir=str(OUT / "raw"), record_video_size={"width": WIDTH, "height": HEIGHT}, color_scheme="light")
    started = time.monotonic()
    page = context.new_page()
    page.add_init_script(CURSOR)
    page.goto(f"{BASE}/gallery/{CASE}/index.html")
    page.wait_for_selector(f"{D} .dv-map-marker.dv-sel", timeout=30000)
    page.wait_for_function(f"() => !!document.querySelector('{D} [data-panel=\"angle\"] .dv-timeseries-plot')", timeout=30000)
    page.evaluate(f"() => window.scrollTo(0, document.querySelector('{D}').getBoundingClientRect().top + window.scrollY - 12)")
    box = page.evaluate(f"() => {{ const r = document.querySelector('{D}').getBoundingClientRect(); return {{ top: r.top, bottom: r.bottom, left: r.left, right: r.right }}; }}")
    time.sleep(0.7)
    mark("open: the rack is picked, real", box=box, **page.evaluate(SAID))
    time.sleep(1.1)

    # a robot on the map
    glide_click(page, f'{D} .dv-map-marker[title="Gantry H1"]')
    wait_robot(page, "gantry-h1")
    wait_marked(page, "Gantry H1")
    time.sleep(0.35)
    mark("a click on a marker: its runs, its newest run, its plot", **page.evaluate(SAID))
    time.sleep(1.5)

    # a counted marker asks
    glide_click(page, f'{D} .dv-map-marker[title="Sorter A1 · 2 rows"]')
    page.wait_for_selector(f"{D} .dv-map-choose", timeout=8000)
    mark("a counted marker asks which robot")
    time.sleep(1.1)
    glide_click(page, f'{D} .dv-map-choose-row[data-id="sorter-a2"]', steps=14, hold=0.3)
    wait_robot(page, "sorter-a2")
    wait_marked(page, "Sorter A1 · 2 rows")
    time.sleep(0.35)
    mark("the second robot at that site", **page.evaluate(SAID))
    time.sleep(1.2)

    # an older run, then play it
    glide_click(page, f"{D} [data-panel='runs'] tbody tr[data-i='1'] td")
    time.sleep(0.6)
    mark("an older run", **page.evaluate(SAID))
    time.sleep(0.8)
    glide_click(page, f"{D} [data-panel='playback'] button[aria-label='Play'], {D} [data-panel='playback'] .dv-pb-play")
    mark("play")
    time.sleep(2.6)
    mark("playing", **page.evaluate(SAID))

    # the same pick in the table tab, and back
    glide_click(page, f"{D} [data-panel='deployments'] [role=tab]:has-text('Table')")
    time.sleep(1.2)
    mark("the table tab: the pick is marked", **page.evaluate(SAID))
    glide_click(page, f"{D} [data-panel='deployments'] tbody tr[data-i='9'] td")
    time.sleep(1.0)
    mark("a row in the table picks a robot", **page.evaluate(SAID))
    glide_click(page, f"{D} [data-panel='deployments'] [role=tab]:has-text('Map')")
    page.wait_for_selector(f"{D} .dv-map-marker.dv-sel", timeout=8000)
    time.sleep(1.6)
    mark("back on the map: its marker is marked", **page.evaluate(SAID))
    mark("end")
    path = page.video.path()
    context.close()
    browser.close()

(OUT / "marks.json").write_text(json.dumps(marks, indent=1) + "\n", encoding="utf-8")
print("raw:", path)

if shutil.which("ffmpeg"):
    head = marks["open: the rack is picked, real"]["at"] - 0.2
    length = marks["end"]["at"] - head
    # the dashboard only, scaled to a width that reads in the report: one trim, one crop, one scale
    box = marks["open: the rack is picked, real"]["box"]
    left, top = int(box["left"]), max(0, int(box["top"]))
    crop = f"crop={int(box['right'] - box['left'])}:{min(HEIGHT - top, int(box['bottom'] - box['top']))}:{left}:{top}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{head:.2f}", "-t", f"{length:.2f}", "-i", str(path), "-vf", f"{crop},fps=20,scale=860:-2:flags=lanczos,format=yuv420p",
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "31", "-tune", "animation", "-movflags", "+faststart", "-an", str(OUT / "hero.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "hero.mp4"), "-vf", "fps=3,scale=420:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=32:stats_mode=diff[p];[s1][p]paletteuse=dither=none:diff_mode=rectangle",
                    str(OUT / "hero.gif")], check=True)
    for name in ("hero.mp4", "hero.gif"):
        print(name, (OUT / name).stat().st_size)
