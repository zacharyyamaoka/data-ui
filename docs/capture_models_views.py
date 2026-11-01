#!/usr/bin/env python3
"""Capture round 2 of the actuator-models report from the built site (dist/site): the stills of each feedback point
(1440 px, light and dark), a zoom on an aligned column, and one clip from the real page: roll up across actuators,
drill back down, then open a model's page with its README.

    npm --prefix ~/data-ui/.wt/models-views run build
    ~/psu-atlas/.venv/bin/python docs/capture_models_views.py [OUT_DIR]   # default reports/media/models-views-r2

Round 1's stills (reports/media/models-views) are the "before" of this round; this script does not touch them.
Serves dist/site on a free 127.0.0.1 port and stops it when done. Needs Playwright (psu-atlas venv), Pillow, ffmpeg.
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
import urllib.parse
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "dist" / "site"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "models-views-r2"
W, H = 1440, 900
V = "#example"
CASE = "gallery/robotparts-models/index.html"
PAGE = "gallery/robotparts-model/index.html?variant=" + urllib.parse.quote("M4.ripple.c1", safe="")
HELD = "Held-out tapes · Oct 23"


def webp(png: bytes, path: pathlib.Path, quality: int = 55, width: int | None = None) -> None:
    # WHY 55: the report inlines every still and must stay under 1.9 MB; text stays legible at 1440 px
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(path, "WEBP", quality=quality, method=6)


def ready(page):
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(f"{V} .dv-status", timeout=20000)
    page.wait_for_function("() => document.querySelector('#example .dv-status').textContent.trim()", timeout=20000)
    page.wait_for_timeout(800)


def to_live(page):
    page.evaluate("window.scrollTo(0, document.querySelector('section.live').getBoundingClientRect().top + window.scrollY - 64)")
    page.wait_for_timeout(300)


def tab(page, name):
    page.click(f"{V} .dv-tab[data-name='{name}']")
    page.wait_for_function(f"() => document.querySelector('#example').view.name === {json.dumps(name)} && document.querySelector('#example').dataset.view")
    page.wait_for_timeout(900)


def cell(page, variant, col):
    return page.evaluate_handle(f"""() => {{ const tr = [...document.querySelectorAll('#example tbody tr.dv-row')].find((t) => (t.querySelector('td[data-col=variant]') || {{}}).textContent?.trim() === {json.dumps(variant)});
      return tr ? tr.querySelector(`td[data-col="${{CSS.escape({json.dumps(col)})}}"]`) : null; }}""").as_element()


def shot(page, media, name, what, clip=None):
    webp(page.screenshot(clip=clip) if clip else page.screenshot(), OUT / f"{name}.webp", 70 if clip else 55)
    media[name] = what


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    media: dict[str, str] = {}
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for dark in (False, True):
                tone = "dark" if dark else "light"
                ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=tone)
                page = ctx.new_page()
                page.goto(f"{base}/{CASE}")
                ready(page)
                to_live(page)
                shot(page, media, f"benches-{tone}", f"Benches (the pivot, first tab): its intro (KPI cards per bench, how to read it), rolled up across actuators, one scale per column with its axis; {tone}")
                if not dark:
                    page.click(f"{V} .dv-tools [data-menu=rollup]")
                    page.wait_for_timeout(500)
                    shot(page, media, "rollup-menu-light", "The Roll up menu: tick the dimensions to keep; every other one is aggregated (pick each column's aggregate)")
                    page.check(f"{V} .dv-pop [data-dim=actuator]")
                    page.wait_for_timeout(700)
                    page.keyboard.press("Escape")
                    page.click(f"{V} .dv-reset")
                    page.wait_for_timeout(600)
                    cell(page, "M2.coulomb_viscous", f"@{HELD} / staircase").click()
                    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-peektable")
                    page.wait_for_timeout(500)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    # a zoom on one column: numbers, strips and counts aligned (a crop, 2x readable)
                    box = page.evaluate(f"""() => {{ const th = document.querySelector('#example thead th[data-col="@{HELD} / staircase"]').getBoundingClientRect();
                      const body = document.querySelector('#example .dv-scroll').getBoundingClientRect(); return {{ x: th.left - 4, y: th.top - 30, w: th.width + 260, h: Math.min(430, body.bottom - th.top + 30) }}; }}""")
                    shot(page, media, "aligned-zoom-light", "One pivot column up close: numbers right-aligned in one slot, strips in one slot on one scale, counts in their own slot",
                         clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]})
                tab(page, "Parameters")
                if not dark:
                    shot(page, media, f"parameters-{tone}", f"Parameters: Friction, Capture, Drivetrain and Driver over their terms; values with their basis mark in fixed slots, the CI on hover; {tone}")
                    tab(page, "Parameters · with CI")
                    shot(page, media, "parameters-ci-light", "Parameters · with CI: each friction term split into value | 95% CI low | high | basis, under its own header")
                tab(page, "What each rung adds")
                if not dark:
                    shot(page, media, f"rung-adds-{tone}", f"What each rung adds: the strip on one symmetric-log scale down the column, its axis in the header, median a tall tick; {tone}")
                    tab(page, "What each rung adds · columns")
                    shot(page, media, "rung-adds-columns-light", "The same distribution as columns: median | min | max | n | runs under Error added")
                    tab(page, "Leaderboard")
                    page.check("data-facets input[data-p=actuator][data-value='CAN 14 · GIM4305-10']")
                    page.click(f"{V} .dv-tools [data-menu=rollup]")
                    page.click(f"{V} .dv-pop [data-roll=none]")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    cell(page, "M4.ripple.c1", "rung").click()
                    page.wait_for_selector(f"{V} .dv-peek:not([hidden]) .dv-md")
                    page.wait_for_timeout(500)
                    shot(page, media, "peek-light", "Click a model: the side peek with what it is (contract kind and equation), its error, its fit commit and the README")
                ctx.close()
                ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=tone)
                page = ctx.new_page()
                page.goto(f"{base}/{PAGE}")
                ready(page)
                to_live(page)
                shot(page, media, f"model-page-{tone}", f"A model's page (?variant=M4.ripple.c1): its record, the rail picking the model; {tone}")
                if not dark:
                    page.evaluate("document.querySelector('#example .dv-record-sheet .dv-md h2') && [...document.querySelectorAll('#example .dv-record-sheet .dv-md h2')].pop().scrollIntoView({block: 'start'})")
                    page.wait_for_timeout(500)
                    shot(page, media, "model-readme-light", "Further down the same page: the twin code's README at the fit commit, rendered as markdown")
                ctx.close()

            # the clip: roll up, un-roll, roll back, drill down, open a model's page and its README
            vdir = OUT / "_video"
            shutil.rmtree(vdir, ignore_errors=True)
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light", record_video_dir=str(vdir), record_video_size={"width": W, "height": H})
            t0 = time.monotonic()
            page = ctx.new_page()
            page.goto(f"{base}/{CASE}")
            ready(page)
            to_live(page)
            start = time.monotonic() - t0
            page.wait_for_timeout(1800)
            page.click(f"{V} .dv-tools [data-menu=rollup]")
            page.wait_for_timeout(900)
            page.check(f"{V} .dv-pop [data-dim=actuator]")
            page.wait_for_timeout(1800)
            page.uncheck(f"{V} .dv-pop [data-dim=actuator]")
            page.wait_for_timeout(1200)
            page.keyboard.press("Escape")
            cell(page, "M2.coulomb_viscous", f"@{HELD} / staircase").click()
            page.wait_for_timeout(2200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            link = page.evaluate_handle("""() => [...document.querySelectorAll('#example tbody td[data-col=variant] a')].find((a) => a.textContent.trim() === 'M4.ripple.c1')""").as_element()
            link.scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            link.click()
            ready(page)
            to_live(page)
            page.wait_for_timeout(1500)
            page.evaluate("[...document.querySelectorAll('#example .dv-record-sheet .dv-md h2')].pop().scrollIntoView({block: 'start', behavior: 'smooth'})")
            page.wait_for_timeout(2200)
            ctx.close()
            raw = next(vdir.glob("*.webm"))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(raw), "-vf", "scale=1100:-2", "-r", "10", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "39", "-preset", "slow", "-movflags", "+faststart", "-an", str(OUT / "clip.mp4")], check=True)
            webp(subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{start + 0.5:.2f}", "-i", str(raw), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                                check=True, capture_output=True).stdout, OUT / "clip-poster.webp", 40, 600)
            shutil.rmtree(vdir, ignore_errors=True)
            media["clip.mp4"] = "roll up across actuators, un-roll and roll back, drill a cell down to its runs, open a model's page and its README"
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    (OUT / "media.json").write_text(json.dumps(media, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = 0
    for f in sorted(OUT.iterdir()):
        total += f.stat().st_size
        print(f"{f.name}: {f.stat().st_size:,} bytes")
    print(f"total {total:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
