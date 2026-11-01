"""The Examples index's checks (gallery/): pictures, the column slider, filters and search, both groupings, the five
layouts, every case's page, the side panels, first paint.

    ~/psu-atlas/.venv/bin/python tests/browser/gallery_checks.py      # after npm run build

Its own file, as frame_checks.py is, so the gallery lane never meets the lanes editing checks.py. Every claim is
measured: column counts from card x positions, panel widths from getBoundingClientRect, pictures from naturalWidth.
Missing pictures are captured first (site/capture-thumbs.py; cached, so only a new or changed case costs time).
"""

from __future__ import annotations

import html
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE = ROOT / "dist" / "site"
LAYOUTS = ["index", "shadcn", "echarts", "antd", "storybook"]
DEFAULT = "index"
checks: list[dict] = []


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


COLS = "() => { const cs = [...document.querySelectorAll('.card:not([hidden])')].filter(c => c.getBoundingClientRect().width > 0);" \
       " const top = Math.min(...cs.map(c => Math.round(c.getBoundingClientRect().top)));" \
       " return cs.filter(c => Math.abs(c.getBoundingClientRect().top - top) < 4).length; }"
SHOWN = "() => document.querySelectorAll('.card:not([hidden])').length"


def run(browser, base: str, rows: list[dict]) -> None:
    def page(layout=None, width=1440, height=900, dark=False, storage=None):
        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme="dark" if dark else "light")
        if layout:
            context.add_init_script(f"try {{ if (!sessionStorage.getItem('seeded')) {{ localStorage.setItem('data-ui-gallery/layout', '{layout}'); sessionStorage.setItem('seeded', '1'); }} }} catch (e) {{}}")
        p = context.new_page()
        p.errors = []
        p.on("pageerror", lambda e: p.errors.append(str(e)))
        p.goto(base + "/gallery/index.html")
        p.wait_for_selector("main.gallery[data-cols]")
        return p

    def load_all(p):
        p.evaluate("async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } scrollTo(0, 0); }")
        p.wait_for_load_state("networkidle")
        return p.evaluate("""() => [...document.querySelectorAll('.card')].map(c => {
            const img = [...c.querySelectorAll('.shot img.t')].find(i => getComputedStyle(i).display !== 'none');
            return { slug: c.dataset.slug, ok: !!img && img.complete && img.naturalWidth > 0, src: img && img.currentSrc.split('/').slice(-2).join('/') }; })""")

    # ---- pictures: every card, both themes, every layout (light) and the default layout (dark)
    for layout, dark in [(l, False) for l in LAYOUTS] + [(DEFAULT, True)]:
        p = page(layout, dark=dark)
        shots = load_all(p)
        bad = [s["slug"] for s in shots if not s["ok"]]
        theme_ok = all(("-dark-" in s["src"]) == dark for s in shots if s["src"])
        check(f"{layout}, {'dark' if dark else 'light'}: every card has a loaded picture in the page's theme", len(shots) == len(rows) and not bad and theme_ok,
              f"{len(shots) - len(bad)}/{len(rows)} loaded; missing {bad[:4]}; sample {shots[0]['src']}")
        p.context.close()

    # ---- the slider: 2..6 columns, measured from where the cards sit; ± buttons; remembered per layout after a reload
    p = page(DEFAULT)
    seen = {}
    for n in range(2, 7):
        p.evaluate(f"() => {{ const r = document.querySelector('.cols-range'); r.value = '{n}'; r.dispatchEvent(new Event('input', {{ bubbles: true }})); }}")
        p.wait_for_timeout(80)
        seen[n] = p.evaluate(COLS)
    check("slider: 2, 3, 4, 5, 6 columns put 2..6 cards on the first row", all(seen[n] == n for n in seen), seen)
    p.focus(".cols-range")
    p.keyboard.press("Home")
    p.keyboard.press("ArrowRight")
    p.keyboard.press("ArrowRight")
    by_keys = p.evaluate(COLS)
    p.click(".cols-step[data-step='1']")
    by_button = p.evaluate(COLS)
    check("slider: keyboard (Home, →, →) gives 3 columns, the + button 4", by_keys == 3 and by_button == 4, {"keys": by_keys, "button": by_button})
    p.reload()
    p.wait_for_selector("main.gallery[data-cols]")
    after = {"cols": p.evaluate(COLS), "value": p.eval_on_selector(".cols-range", "e => e.value"), "layout": p.eval_on_selector("main.gallery", "e => e.dataset.layout")}
    check("slider: the column count survives a reload", after == {"cols": 4, "value": "4", "layout": DEFAULT}, after)
    # ctrl + wheel (a trackpad pinch) is Apple Photos' zoom: wheel up = fewer columns
    # WHY aim at a card, not a fixed (700, 500): the contents above the grid grow with the cases (toolbar-mix's six
    # put that point in the gap between the contents and the grid); the wheel must land on the grid itself
    p.eval_on_selector(".g-groups .card", "e => e.scrollIntoView({ block: 'center' })")
    box = p.locator(".g-groups .card").first.bounding_box()
    p.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    p.keyboard.down("Control")
    p.mouse.wheel(0, -120)
    p.keyboard.up("Control")
    p.wait_for_timeout(80)
    check("slider: ctrl + wheel over the grid zooms in a column", p.evaluate(COLS) == 3, p.evaluate(COLS))
    p.context.close()

    # ---- filters narrow to the right count, in every layout
    for layout in LAYOUTS:
        p = page(layout)
        want_app = sum(r["app"] == "Vibe Tracks" for r in rows)
        want_both = sum(r["app"] == "robotparts" and "chart" in r["types"] for r in rows)
        p.click(".chips[data-filter=app] .chip[data-value='Vibe Tracks']")
        got_app = p.evaluate(SHOWN)
        p.click(".chips[data-filter=app] .chip[data-value='robotparts']")
        p.click(".chips[data-filter=type] .chip[data-value='chart']")
        got_both = p.evaluate(SHOWN)
        said = p.inner_text(".filter-count span")
        check(f"{layout}: App and View filters narrow to the right cases (and say so)", got_app == want_app and got_both == want_both and said == str(want_both) and "type=chart" in p.url,
              f"Vibe Tracks {got_app}/{want_app}; robotparts x chart {got_both}/{want_both}; count says {said}")
        p.context.close()

    # ---- the switcher: bottom right, remembered, never in the URL
    p = page(DEFAULT)
    p.select_option(".layout-switch select", "antd")
    box = p.eval_on_selector(".layout-switch", "e => { const r = e.getBoundingClientRect(); return [Math.round(innerWidth - r.right), Math.round(innerHeight - r.bottom)]; }")
    p.reload()
    p.wait_for_selector("main.gallery[data-cols]")
    check("switcher: bottom right, the layout survives a reload, the URL has no flag",
          p.eval_on_selector("main.gallery", "e => e.dataset.layout") == "antd" and "layout" not in p.url and box[0] < 40 and box[1] < 40, {"layout": p.eval_on_selector("main.gallery", "e => e.dataset.layout"), "edge gap": box})
    p.context.close()

    # ---- hover flips a picture to another view, and the link opens that view
    p = page(DEFAULT)
    shot = p.locator(".card[data-slug='actuator-charts'] .shot")
    shot.scroll_into_view_if_needed()
    p.wait_for_timeout(200)
    b = shot.bounding_box()
    p.mouse.move(b["x"] + b["width"] * 0.92, b["y"] + b["height"] / 2)
    p.wait_for_timeout(100)
    flipped = p.evaluate("() => { const c = document.querySelector(\".card[data-slug='actuator-charts']\"); return { at: c.dataset.at, href: c.querySelector('.card-link').getAttribute('href'), view: c.querySelector('.shot-view').textContent }; }")
    check("hover: the right edge of a picture shows the case's last view and links to it", flipped["at"] == str(len(rows[0]["views"]) - 1) and "#view=" in flipped["href"], flipped)
    p.context.close()

    # ---- shadcn: Preview is the live kit, a view tab swaps it, .base shows the case's own source
    p = page("shadcn")
    p.wait_for_selector(".card[data-slug='dataclass-viewer'] .live-slot data-views[data-view]", timeout=30000)
    off_screen = p.evaluate("() => document.querySelectorAll('.live-slot data-views').length")
    p.locator(".card[data-slug='rack-wiring']").scroll_into_view_if_needed()
    p.wait_for_selector(".card[data-slug='rack-wiring'] .live-slot data-views[data-view]", timeout=30000)
    p.click(".card[data-slug='rack-wiring'] .tabs [data-i='1']")
    src = p.eval_on_selector(".card[data-slug='rack-wiring'] .shot img.t-light", "e => e.getAttribute('src')")
    live_view = p.eval_on_selector(".card[data-slug='rack-wiring'] .live-slot data-views", "e => e.getAttribute('view')")
    p.click(".card[data-slug='rack-wiring'] [data-pane='base']")
    p.wait_for_function("() => document.querySelector(\".card[data-slug='rack-wiring'] .src-pane code\").textContent.includes('views:')")
    shown = p.evaluate("""() => { const c = document.querySelector(".card[data-slug='rack-wiring']"); const r = c.querySelector('.src-pane').getBoundingClientRect(), f = c.querySelector('.frame').getBoundingClientRect();
        return { covers: Math.abs(r.width - f.width) <= 3 && Math.abs(r.height - f.height) <= 3, text: c.querySelector('.src-pane code').textContent.slice(0, 40) }; }""")
    on_disk = (ROOT / "gallery" / "examples" / "rack-wiring" / "views.base").read_text()[:40]
    check("shadcn: Preview is the live kit (mounted only near the screen), a view tab swaps picture and live view, .base shows the case's source over the preview",
          off_screen < len(rows) and src.endswith("rack-wiring/1-light-480.webp") and live_view == rows[[r["slug"] for r in rows].index("rack-wiring")]["views"][1]["name"] and shown["covers"] and shown["text"] == on_disk,
          {"live at first": off_screen, "picture": src.split("/")[-1], "live view": live_view, **shown})
    p.context.close()

    # ---- grouping: by view type first (Vega-Lite), by app one click away, remembered
    p = page(DEFAULT)
    by_type = p.evaluate("() => [...document.querySelectorAll('.type-group:not([hidden])')].map(s => [s.dataset.group, s.querySelectorAll('.card').length])")
    want_type = {}
    for r in rows:
        want_type[r["category"]] = want_type.get(r["category"], 0) + 1
    p.click(".group-by [data-group-by='app']")
    by_app = p.evaluate("() => [...document.querySelectorAll('.app-group:not([hidden])')].map(s => [s.dataset.group, s.querySelectorAll('.card').length])")
    want_app = {}
    for r in rows:
        want_app[r["app"]] = want_app.get(r["app"], 0) + 1
    p.reload()
    p.wait_for_selector("main.gallery[data-cols]")
    kept = p.eval_on_selector("main.gallery", "e => e.dataset.groupBy")
    p.click(".group-by [data-group-by='type']")
    check("grouping: by view type by default, every case in its type's section; by app puts each in its app's; the choice survives a reload",
          dict(by_type) == want_type and by_type[0][0] == "Table" and dict(by_app) == want_app and kept == "app", {"type": by_type, "app": by_app, "after reload": kept})
    p.fill(".g-search", "wiring")
    found = p.evaluate("() => [...document.querySelectorAll('.card:not([hidden]) h3')].map(e => e.textContent)")
    check("search: 'wiring' finds the rack wiring case and nothing else", found == ["1-DOF rack wiring"], found)
    p.context.close()

    # ---- every case has a page: the card's link answers, and that page names the case
    p = page(DEFAULT)
    links = p.evaluate("() => [...document.querySelectorAll('.card')].map(c => [c.querySelector('h3').textContent, c.querySelector('.card-link').href])")
    bad = []
    for title, href in links:
        r = p.request.get(href)
        # WHY unescape the page, not escape the title: the build writes ' as &#39; (esc), which html.escape(quote=False)
        # never produces, so a title with an apostrophe ("The bar: data-ui's toolbar") could not pass
        if r.status != 200 or title not in html.unescape(r.text()):
            bad.append((title, r.status))
    check("every case has a page: each card's link answers 200 and the page carries its title", len(links) == len(rows) and not bad, f"{len(links) - len(bad)}/{len(links)}; {bad[:3]}")
    p.context.close()

    # ---- Storybook: the sidebar and the Docs panel drag (measured), keep their width after a reload, and fold away
    p = page("storybook")
    p.wait_for_selector(".g-rail + .dv-splitter:not([hidden])")
    measure = "() => ({ rail: Math.round(document.querySelector('.g-rail').getBoundingClientRect().width), insp: Math.round(document.querySelector('.g-inspector').getBoundingClientRect().width), main: Math.round(document.querySelector('.g-main').getBoundingClientRect().width) })"
    a = p.evaluate(measure)
    h = p.locator(".g-rail + .dv-splitter").bounding_box()
    p.mouse.move(h["x"] + h["width"] / 2, h["y"] + 40)
    p.mouse.down()
    p.mouse.move(h["x"] + h["width"] / 2 + 60, h["y"] + 40, steps=6)
    p.mouse.up()
    h2 = p.locator(".g-inspector + .dv-splitter").bounding_box()
    p.mouse.move(h2["x"] + h2["width"] / 2, h2["y"] + 40)
    p.mouse.down()
    p.mouse.move(h2["x"] + h2["width"] / 2 - 50, h2["y"] + 40, steps=6)
    p.mouse.up()
    b2 = p.evaluate(measure)
    p.reload()
    p.wait_for_selector(".g-rail + .dv-splitter:not([hidden])")
    p.wait_for_timeout(150)
    c = p.evaluate(measure)
    check("storybook: dragging the sidebar's edge +60 px and the Docs panel's -50 px resizes both, and a reload keeps them",
          abs(b2["rail"] - a["rail"] - 60) <= 3 and abs(b2["insp"] - a["insp"] - 50) <= 3 and abs(c["rail"] - b2["rail"]) <= 1 and abs(c["insp"] - b2["insp"]) <= 1,
          {"before": a, "dragged": b2, "reloaded": c})
    p.locator(".card[data-slug='rack-wiring'] .shot").scroll_into_view_if_needed()
    p.hover(".card[data-slug='rack-wiring'] .shot")
    title = p.inner_text(".g-inspector h2")
    p.click(".g-inspector [data-fold]")
    folded = p.evaluate(measure)
    check("storybook: the Docs panel shows the hovered case and folds away", title == "1-DOF rack wiring" and folded["insp"] < 50, {"title": title, "folded width": folded["insp"]})
    p.click(".g-inspector [data-fold]")
    p.context.close()

    # ---- ECharts: the category sidebar lists the non-empty types, jumps to a section, and drags
    p = page("echarts")
    p.wait_for_selector(".g-rail + .dv-splitter:not([hidden])")
    toc = p.evaluate("() => [...document.querySelectorAll('.toc a.toc-group')].map(a => a.textContent.trim())")
    p.click(".toc a[href='#type-cards']")
    p.wait_for_timeout(1200)
    top = p.evaluate("() => Math.round(document.getElementById('type-cards').getBoundingClientRect().top)")
    w0 = p.evaluate("() => document.querySelector('.g-rail').getBoundingClientRect().width")
    h = p.locator(".g-rail + .dv-splitter").bounding_box()
    p.mouse.move(h["x"] + h["width"] / 2, h["y"] + 30)
    p.mouse.down()
    p.mouse.move(h["x"] + h["width"] / 2 + 40, h["y"] + 30, steps=5)
    p.mouse.up()
    w1 = p.evaluate("() => document.querySelector('.g-rail').getBoundingClientRect().width")
    cats = sorted({r["category"] for r in rows})
    check("echarts: the sidebar lists every non-empty type, jumps to its section, and its edge drags after the page has scrolled (the handle follows the sticky sidebar)",
          sorted(t.rsplit(" ", 1)[0] for t in toc) == cats and 0 <= top < 200 and abs(w1 - w0 - 40) <= 3, {"toc": toc, "Cards section top": top, "drag": [round(w0), round(w1)]})
    p.context.close()

    # ---- phones: no sideways scroll, in every layout
    for layout in LAYOUTS:
        p = page(layout, width=390, height=844)
        sw = p.evaluate("document.scrollingElement.scrollWidth")
        check(f"{layout}, 390 px: no sideways page scroll; {p.evaluate(COLS)} columns", sw <= 390, f"scrollWidth {sw}")
        p.context.close()

    # ---- first paint: the pictures are lazy, the other theme's are never fetched, and the first screen is light
    p = page(DEFAULT)
    p.wait_for_load_state("networkidle")
    first = p.evaluate("""() => { const pics = performance.getEntriesByType('resource').filter(e => e.name.endsWith('.webp'));
        const nav = performance.getEntriesByType('navigation')[0];
        return { pictures: pics.length, dark: pics.filter(e => e.name.includes('-dark-')).length, big: pics.filter(e => e.name.includes('-960')).length,
                 kb: Math.round(pics.reduce((s, e) => s + (e.transferSize || e.encodedBodySize || 0), 0) / 1024), domReady: Math.round(nav.domContentLoadedEventEnd),
                 lazy: [...document.querySelectorAll('.shot img.t')].every(i => i.loading === 'lazy') }; }""")
    check("first paint: every picture is lazy, none of the dark theme's are fetched in light, the 480 px size at five columns, under 600 KB",
          first["lazy"] and first["dark"] == 0 and first["big"] == 0 and first["kb"] < 600 and first["pictures"] <= len(rows), first)
    errors = p.errors
    p.context.close()
    check("no script errors on the gallery", not errors, errors[:3])


def main() -> int:
    if not (SITE / "gallery" / "gallery.json").exists():
        print("dist/site is not built: npm --prefix ~/data-ui run build")
        return 1
    # the pictures: captured once and cached; a fresh clone pays for them here
    r = subprocess.run([sys.executable, str(ROOT / "site" / "capture-thumbs.py")])
    check("site/capture-thumbs.py captured every view", r.returncode == 0, f"exit {r.returncode}")
    rows = json.loads((SITE / "gallery" / "gallery.json").read_text())["rows"]
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/gallery/index.html", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            run(browser, base, rows)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    passed = sum(c["ok"] for c in checks)
    print(f"{passed}/{len(checks)} gallery checks pass")
    out = ROOT / "reports" / "media" / "gallery"
    out.mkdir(parents=True, exist_ok=True)
    (out / "gallery-checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
