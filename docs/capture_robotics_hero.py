"""Record the hero video: the robotics-arm template, then the servo Playback + Gates twin, on the real built site.

Usage (a static server on dist/site first, e.g. python3 -m http.server 47613 --bind 127.0.0.1 --directory dist/site):
    PLAYWRIGHT_BROWSERS_PATH=<a cache with chromium-1243> ~/psu-atlas/.venv/bin/python \
        docs/capture_robotics_hero.py http://127.0.0.1:47613 <out dir>
Writes <out dir>/raw/*.webm (Playwright's own screencast of the page, 1280 x 800) and <out dir>/marks.json (seconds
since the context opened for each step, so the encoder can trim the page-load head and the navigation gap).

The 2026-10-29 hero (reports/media/robotics-pep0010/hero.mp4) was cut from one take with two trims and a crop, no
speed change and nothing drawn on top:
    ffmpeg -i raw.webm -filter_complex "[0:v]trim=start=4.1:end=21.0,setpts=PTS-STARTPTS[a];
      [0:v]trim=start=25.1:end=28.55,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,crop=1000:800:272:0,fps=25,
      format=yuv420p[v]" -map "[v]" -c:v libx264 -profile:v high -preset slow -crf 30 -tune animation
      -movflags +faststart -an hero.mp4
    ffmpeg -i hero.mp4 -vf "fps=4,scale=440:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=32:
      stats_mode=diff[p];[s1][p]paletteuse=dither=none:diff_mode=rectangle" hero.gif
WHY a typed decay: the card's decay control is a text field in seconds (packages/views/scene3d/src/controls.js), there
is no drag handle, so the take types 0.2 then 3.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
(OUT / "raw").mkdir(parents=True, exist_ok=True)
HOOK = "(sel) => { const r = document.querySelector(sel + ' .dv-scene3d'); return r && r.scene3d ? r.scene3d : null; }"
W, H = 1280, 800

marks = {}
t0 = None


def mark(name):
    marks[name] = round(time.monotonic() - t0, 2)
    print(f"{marks[name]:6.2f}s  {name}", flush=True)


def cursor(page):
    # a visible pointer, so a reader sees where each click lands (headless video draws no cursor)
    page.add_init_script("""
      addEventListener('DOMContentLoaded', () => {
        const d = document.createElement('div'); d.id = '__cur';
        d.style.cssText = 'position:fixed;left:-40px;top:-40px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
          'background:rgba(220,38,38,.35);border:2px solid rgba(220,38,38,.9);z-index:2147483647;pointer-events:none;transition:transform .12s';
        document.body.appendChild(d);
        addEventListener('mousemove', (e) => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
        addEventListener('mousedown', () => { d.style.transform = 'scale(.6)'; }, true);
        addEventListener('mouseup', () => { d.style.transform = ''; }, true);
      });""")


def glide(page, x, y, steps=5):
    page.mouse.move(x, y, steps=steps)


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light",
                              record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H})
    page = ctx.new_page()
    t0 = time.monotonic()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    cursor(page)

    # ---- 1. the robotics-arm template ------------------------------------------------------------------------------
    page.goto(f"{BASE}/gallery/robotics-arm/", wait_until="networkidle")
    sel = ".dd-panel:nth-of-type(3)"
    page.wait_for_function(
        "() => [...document.querySelectorAll('.dv-scene3d')].some((r) => r.scene3d && r.scene3d.renders() > 0)", timeout=30000)
    page.wait_for_timeout(1500)
    # the playback bar at the top, Path 3D and Path top below it
    bar = page.locator(".dv-pb-play").first
    y_bar = page.evaluate("() => document.querySelector('.dv-pb-play').getBoundingClientRect().top + scrollY")
    page.evaluate(f"window.scrollTo(0, {max(0, y_bar - 70)})")
    page.wait_for_timeout(900)
    mark("arm ready")

    # 1. play the clock
    b = bar.bounding_box()
    glide(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    mark("play")
    page.wait_for_timeout(2000)

    # 2. the view cube's +Z ball on Path 3D (found from the camera, as tests/browser/p1b_checks.py's cube_click does)
    panel = page.locator(".dd-panel").filter(has=page.locator(".dv-scene3d")).first
    panel_handle = panel.element_handle()
    cube = page.evaluate("""(p) => { const r = p.querySelector('.dv-scene3d'); const h = r && r.scene3d; const c = p.querySelector('[data-cube]');
        if (!h || !c) return null; const cam = h.camera(); const b = c.getBoundingClientRect(); const v = cam.view;
        return { x: b.left + (v[8] / 2 + 1) / 2 * b.width, y: b.top + (1 - v[9] / 2) / 2 * b.height }; }""", panel_handle)
    glide(page, cube["x"], cube["y"])
    page.wait_for_timeout(150)
    page.mouse.click(cube["x"], cube["y"])
    mark("cube +Z")
    ortho = page.evaluate("""(p) => new Promise((res) => { const h = p.querySelector('.dv-scene3d').scene3d; const t = Date.now();
        const tick = () => { const c = h.camera(); if ((c.ortho && !c.animating) || Date.now() - t > 4000) res({ ortho: c.ortho, proj15: c.proj && c.proj[15] }); else requestAnimationFrame(tick); }; tick(); })""", panel_handle)
    mark("cube settled")
    page.wait_for_timeout(900)

    # 3. decay: a typed field in seconds (there is no drag handle), 0.6 → 2 → 0.25
    decay = panel.locator("[data-decay]")
    db = decay.bounding_box()
    glide(page, db["x"] + db["width"] / 2, db["y"] + db["height"] / 2)
    decay.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("0.2", delay=90)
    page.keyboard.press("Enter")
    mark("decay 0.2")
    page.wait_for_timeout(1500)
    decay.click()
    page.keyboard.press("Control+A")
    page.keyboard.type("3", delay=90)
    page.keyboard.press("Enter")
    mark("decay 3")
    page.wait_for_timeout(1700)

    # 4. compare's arrows: ×1 → ×30 (display only; the card labels it)
    scale = panel.locator("[data-compare-scale]")
    sb = scale.bounding_box()
    glide(page, sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
    scale.select_option(label="×30")
    mark("compare ×30")
    page.wait_for_timeout(2400)
    arm_state = page.evaluate(f"""(p) => {{ const h = p.querySelector('.dv-scene3d').scene3d; const w = h.window();
        const lab = p.querySelector('[data-compare-label]'); let arrows = null; try {{ arrows = (h.arrows() || []).length; }} catch (e) {{}}
        return {{ window: w, label: lab && lab.textContent, arrows }}; }}""", panel_handle)

    # ---- 5. the servo Playback + Gates twin: a gate cell opens the peek with its evidence ----------------------------
    page.goto(f"{BASE}/gallery/robotics-servo-gates/", wait_until="networkidle")
    page.wait_for_selector("[role=gridcell]", timeout=30000)
    page.wait_for_timeout(1200)
    y_grid = page.evaluate("() => document.querySelector('[role=gridcell]').getBoundingClientRect().top + scrollY")
    page.evaluate(f"window.scrollTo(0, {max(0, y_grid - 230)})")
    page.wait_for_timeout(700)
    mark("gates ready")
    cell = page.locator("[role=gridcell][aria-label*='Twin error']").nth(2)
    label = cell.get_attribute("aria-label")
    cb = cell.bounding_box()
    glide(page, cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2)
    page.wait_for_timeout(200)
    page.mouse.click(cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2)
    mark("gate cell")
    page.wait_for_timeout(2600)
    peek = page.evaluate("""() => { const p = [...document.querySelectorAll('.dv-peek, [class*=peek]')].find((e) => e.getBoundingClientRect().width > 200);
        if (!p) return null; const r = p.getBoundingClientRect(); return { cls: p.className, box: [r.x, r.y, r.width, r.height], text: p.textContent.trim().slice(0, 300) }; }""")
    # scroll the peek to its evidence
    page.wait_for_timeout(600)
    mark("end")

    video = page.video
    ctx.close()
    path = video.path()
    browser.close()

json.dump({"marks": marks, "ortho": ortho, "arm": arm_state, "cell": label, "peek": peek, "errors": errors, "video": str(path)},
          open(OUT / "marks.json", "w"), indent=1, default=str)
print(json.dumps({"ortho": ortho, "arm": arm_state, "cell": label, "peek": (peek or {}).get("cls"), "errors": errors[:3], "video": str(path)}, indent=1, default=str))
