#!/usr/bin/env python3
"""Capture the Filters report's media from the built site (dist/site): a still of every facet kind in use, the whole
rail light and dark, the phone's disclosure, the four recipes, and the hero clip of picking filters while the table,
the cards and the chart follow.

    npm --prefix ~/data-ui/.wt/facets run build
    ~/psu-atlas/.venv/bin/python docs/capture_filters.py [OUT_DIR]     # default ~/data-ui/reports/media/filters

Serves dist/site on a free 127.0.0.1 port and stops it when done. Each kind is opened by its readable link
(gallery/examples/filters-gallery/source/kinds.json `try`), so a still shows the kind with its pick and the rows it
left (written to stills.json beside the images). Needs Playwright (the psu-atlas venv), Pillow and ffmpeg.
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
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("~/data-ui/reports/media/filters")
CASE = "gallery/filters-gallery/index.html"
KINDS = json.loads((ROOT / "gallery" / "examples" / "filters-gallery" / "source" / "kinds.json").read_text(encoding="utf-8"))["kinds"]
# kind -> the rail group that shows it (kind, property)
GROUP = {"values": ("values", "brand"), "values + exclude": ("values", "brand"), "select": ("select", "in_stock"), "toggle": ("toggle", "in_stock"),
         "has": ("has", "photo"), "range": ("range", "price"), "slider": ("slider", "mass"), "slider-histogram": ("slider-histogram", "peak_torque"),
         "buckets": ("buckets", "price"), "rating": ("rating", "level"), "min-level": ("min-level", "level"), "date": ("date", "listed"),
         "chips": ("chips", "buses"), "swatch": ("swatch", "brand"), "gallery": ("gallery", "form"), "picture-list": ("picture-list", "drivetrain"),
         "grid": ("grid", "gear_ratio"), "diagram (any kind)": ("range", "od"), "listbox": ("listbox", "voltage"), "tree": ("tree", "form"),
         "search": ("search", "model"), "popular": ("popular", "price"), "current": ("current", "")}


def webp(png: bytes, path: pathlib.Path, quality: int = 86) -> None:
    Image.open(io.BytesIO(png)).save(path, "WEBP", quality=quality, method=6)


def slug(kind: str) -> str:
    return "".join(c if c.isalnum() or c == "-" else "-" for c in kind).strip("-").replace("--", "-")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    stills = {}
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()

            def page(query="", dark=False, width=1280, height=900, scale=2, mobile=False, video=None):
                ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale, color_scheme="dark" if dark else "light",
                                          is_mobile=mobile, has_touch=mobile, **({"record_video_dir": str(video), "record_video_size": {"width": width, "height": height}} if video else {}))
                pg = ctx.new_page()
                pg.goto(f"{base}/{CASE}{query}")
                pg.wait_for_selector("data-facets .df-group", state="attached", timeout=20000)
                pg.wait_for_function("() => document.querySelector('#example .dv-status').textContent.trim()")
                pg.wait_for_timeout(500)
                return pg

            # ---- one still per kind, in use
            for k in KINDS:
                kind, prop = GROUP[k["kind"]]
                pg = page(k["try"])
                sel = f"data-facets .df-group.df-as-{kind}" + (f"[data-p='{prop}']" if prop else "")
                if k["kind"] == "slider":
                    pg.focus(f"{sel} input[data-side=min]")
                el = pg.locator(sel).first
                el.scroll_into_view_if_needed()
                pg.wait_for_timeout(200)
                name = f"kind-{slug(k['kind'])}"
                webp(el.screenshot(), OUT / f"{name}.webp")
                stills[k["kind"]] = {"file": f"{name}.webp", "status": pg.inner_text("#example .dv-status").split(" · ")[0], "url": pg.evaluate("decodeURIComponent(location.search)")}
                pg.context.close()
                print(name, stills[k["kind"]]["status"])

            # ---- the whole rail, light and dark, side by side with the table it drives
            for dark in (False, True):
                pg = page("?form=hobby%20servo&price=50..%3C100&buses=can", dark=dark, height=1000)
                pg.evaluate("document.querySelector('data-facets').style.maxHeight = 'none'")
                webp(pg.locator("data-facets").screenshot(), OUT / f"rail-{'dark' if dark else 'light'}.webp", 82)
                webp(pg.locator("section.live").screenshot(), OUT / f"page-{'dark' if dark else 'light'}.webp", 82)
                pg.context.close()
            # ---- the phone: a closed disclosure, then open
            pg = page(dark=False, width=390, height=844, scale=2, mobile=True)
            webp(pg.screenshot(), OUT / "phone-closed.webp", 82)
            pg.click("data-facets .df-box > summary")
            pg.wait_for_timeout(300)
            webp(pg.screenshot(), OUT / "phone-open.webp", 82)
            pg.context.close()

            # ---- the recipes
            for name in ("McMaster-style", "Amazon-style", "Digi-Key-style", "Obsidian-style"):
                pg = page(height=900)
                pg.click(f"#example .dv-tab[data-name='{name}']")
                pg.wait_for_timeout(500)
                if name == "McMaster-style":
                    pg.click("data-facets .df-as-gallery [data-value='integrated actuator']")
                    pg.wait_for_timeout(400)
                webp(pg.locator("section.live").screenshot(), OUT / f"recipe-{name.split('-')[0].lower()}.webp", 82)
                stills[name] = {"status": pg.inner_text("#example .dv-status").split(" · ")[0]}
                pg.context.close()

            # ---- the hero clip: pick filters; the table, then the cards, then the chart follow
            raw = OUT / "raw"
            shutil.rmtree(raw, ignore_errors=True)
            pg = page(width=1280, height=760, scale=1, video=raw)
            # the app alone, filling the frame: the site's header and the case's lede are not what the clip is about
            pg.add_style_tag(content="header.top, .crumbs, h1, .lede, .case-meta, .case-files, .replaces-case, footer { display: none !important; } main.wrap { padding-top: 8px !important; } .demo { --demo-height: 736px !important; }")
            pg.wait_for_timeout(400)
            steps = [
                lambda: pg.click("data-facets .df-as-gallery [data-value='integrated actuator']"),
                lambda: pg.click("data-facets .df-as-chips [data-value=can]"),
                lambda: (pg.focus("data-facets .df-as-slider-histogram input[data-side=min]"), [pg.keyboard.press("PageUp") for _ in range(3)]),
                lambda: pg.click("#example .dv-tab[data-name='Cards']"),
                lambda: pg.click("data-facets .df-as-swatch [data-value=Steadywin]"),
                lambda: pg.click("#example .dv-tab[data-name='Chart']"),
                lambda: pg.click("data-facets .df-as-current .df-chip:has-text('Steadywin')"),
                lambda: pg.click("data-facets .df-as-buckets[data-p=price] .df-chip:has-text('100–250')"),
            ]
            pg.wait_for_timeout(900)
            for step in steps:
                step()
                pg.wait_for_timeout(1350)
            pg.wait_for_timeout(600)
            video = pg.video.path()
            pg.context.close()
            browser.close()
        mp4 = OUT / "hero.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "scale=1280:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "30", "-preset", "slow", "-movflags", "+faststart", "-an", str(mp4)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "fps=5,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer:bayer_scale=3", str(OUT / "hero.gif")], check=True)
        webp(subprocess.run(["ffmpeg", "-loglevel", "error", "-sseof", "-1", "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], check=True, capture_output=True).stdout, OUT / "hero-poster.webp", 80)
        shutil.rmtree(raw, ignore_errors=True)
        (OUT / "stills.json").write_text(json.dumps(stills, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{len(stills)} stills, hero.mp4 {mp4.stat().st_size:,} bytes, hero.gif {(OUT / 'hero.gif').stat().st_size:,} bytes -> {OUT}")
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
