"""The gallery's pictures: every view of every case, light and dark, captured from the built site in headless Chromium.

    ~/psu-atlas/.venv/bin/python ~/data-ui/site/capture-thumbs.py [--force] [--only SLUG,...]

Run after `npm run build` (it reads dist/site/gallery/gallery.json and renders dist/site/gallery/thumb.html, the
landing page's own way of drawing a view: <data-views view=… toolbar=none>). Writes site/.thumbs/<case>/<i>-<theme>-
<480|960>.webp (gitignored: binaries stay out of git) and copies them into dist/site/gallery/thumbs/, so no rebuild is
needed; the next build copies them again. A case is skipped while its views.base, data file, skin and README hash the
same as when it was captured (site/.thumbs/manifest.json); --force recaptures everything (after a kit change).
WHY 720 x 450 drawn at 2x, 960/480 kept as WebP at q62: the landing page's thumbnails draw a view at twice the box
and scale it down, which Zach liked (2026-10-26); a view drawn any wider is unreadable at five columns. Sharp at 2-3 columns, ~10-25 KB each at 5, a few MB in all, well
under Cloudflare's 25 MiB-per-file and 20,000-file limits (data-ui.dev).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "dist" / "site"
CACHE = ROOT / "site" / ".thumbs"
EXAMPLES = ROOT / "gallery" / "examples"
WIDTHS = (960, 480)
QUALITY = 62
PARALLEL = 4
WAIT = 45000


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def case_key(row: dict) -> str:
    """What a case's pictures depend on, besides the kit: its .base, data, skin and README."""
    here = EXAMPLES / row["slug"]
    digest = hashlib.sha256()
    for path in [here / "views.base", (here / row["data"]).resolve(), here / "skin.css", here / "README.md"]:
        digest.update(path.name.encode())
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


async def capture_view(browser, base: str, row: dict, index: int, theme: str, folder: pathlib.Path) -> dict:
    view = row["views"][index]
    context = await browser.new_context(viewport={"width": 720, "height": 450}, color_scheme=theme, device_scale_factor=2)
    page = await context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    query = urllib.parse.urlencode({"case": row["slug"], "view": view["name"], "theme": theme, **({"skin": "1"} if row["skin"] else {})})
    started = time.time()
    try:
        await page.goto(f"{base}/gallery/thumb.html?{query}", wait_until="load", timeout=WAIT)
        await page.wait_for_function("() => window.__thumbRendered > 0", timeout=WAIT)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # charts, maps and graphs finish drawing a beat after the render event (Vega, MapLibre, React Flow)
        await page.wait_for_timeout(900 if view["type"] in ("chart", "map", "graph", "timeline", "calendar") else 350)
        png = await page.locator("#stage").screenshot(type="png")
    finally:
        await context.close()
    image = Image.open(io.BytesIO(png)).convert("RGB")
    sizes = {}
    for width in WIDTHS:
        out = folder / f"{index}-{theme}-{width}.webp"
        image.resize((width, round(width * image.height / image.width)), Image.LANCZOS).save(out, "WEBP", quality=QUALITY, method=6)
        sizes[width] = out.stat().st_size
    return {"view": view["name"], "theme": theme, "ms": round((time.time() - started) * 1000), "bytes": sizes, "errors": errors[:2]}


async def run(rows: list[dict], base: str, force: bool) -> dict:
    manifest_path = CACHE / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    todo = []
    for row in rows:
        key = case_key(row)
        folder = CACHE / row["slug"]
        have = all((folder / f"{i}-{t}-{w}.webp").exists() for i in range(len(row["views"])) for t in ("light", "dark") for w in WIDTHS)
        if not force and have and manifest.get(row["slug"], {}).get("key") == key and manifest[row["slug"]].get("views") == [v["name"] for v in row["views"]]:
            continue
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        todo.append((row, key, folder))
    print(f"{len(rows) - len(todo)} cases current, {len(todo)} to capture", flush=True)
    gate = asyncio.Semaphore(PARALLEL)
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        async def one(row, index, theme, folder):
            async with gate:
                try:
                    shot = await capture_view(browser, base, row, index, theme, folder)
                    print(f"  {row['slug']} · {shot['view']} · {theme}: {shot['ms']} ms, {shot['bytes'][480] // 1024}+{shot['bytes'][960] // 1024} KB", flush=True)
                    return shot
                except Exception as error:  # a view that never draws is reported, and its card is drawn live instead
                    print(f"  FAIL {row['slug']} · {row['views'][index]['name']} · {theme}: {error}".splitlines()[0], flush=True)
                    return {"view": row["views"][index]["name"], "theme": theme, "failed": str(error)[:200]}

        for row, key, folder in todo:
            shots = await asyncio.gather(*(one(row, i, t, folder) for i in range(len(row["views"])) for t in ("light", "dark")))
            manifest[row["slug"]] = {"key": key, "views": [v["name"] for v in row["views"]], "captured": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "failed": [f"{s['view']} · {s['theme']}" for s in shots if s.get("failed")]}
            if manifest[row["slug"]]["failed"]:
                manifest[row["slug"]]["key"] = None  # retried next run
        await browser.close()
    live = {r["slug"] for r in rows}
    for slug in [s for s in manifest if s not in live]:
        manifest.pop(slug)
        shutil.rmtree(CACHE / slug, ignore_errors=True)
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="recapture every case (after a kit change)")
    parser.add_argument("--only", default="", help="comma-separated case slugs")
    args = parser.parse_args()
    data = SITE / "gallery" / "gallery.json"
    if not data.exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    rows = json.loads(data.read_text())["rows"]
    only = {s for s in args.only.split(",") if s}
    CACHE.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/gallery/thumb.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        manifest = asyncio.run(run([r for r in rows if not only or r["slug"] in only] if only else rows, base, args.force))
    finally:
        server.terminate()
        server.wait(timeout=10)
    target = SITE / "gallery" / "thumbs"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CACHE, target)
    files = [f for f in CACHE.rglob("*.webp")]
    total = sum(f.stat().st_size for f in files)
    failed = [f"{slug}: {', '.join(m['failed'])}" for slug, m in manifest.items() if m.get("failed")]
    print(f"{len(files)} pictures, {total / 1024 / 1024:.1f} MB, largest {max((f.stat().st_size for f in files), default=0) // 1024} KB; copied to {target}")
    if failed:
        print("not captured (drawn live instead): " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used in capture_view)
    sys.exit(main())
