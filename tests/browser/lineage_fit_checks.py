"""The lineage view's first view (docs/CONTRACT.md §21), measured in headless Chromium.

    ~/psu-atlas/.venv/bin/python tests/browser/lineage_fit_checks.py [OUT_DIR]     # after npm run build

Serves the repo root on a free 127.0.0.1 port (tests/browser/fixtures/lineage-fit.html: one <data-views> 936 px wide, over
18 rounds of 24 marks with the focus at the last), stops it when done, writes OUT_DIR/lineage-fit-checks.json (default
reports/media/lineage-fit) and exits 1 if any check fails. Every claim is a rect read from the page
(getBoundingClientRect on each mark, the view's svg and the bar), never the presence of a transform.

  fits       picture marks (columns no closer than 56 px): the whole tree needs 0.5x-0.6x, and the first view already shows it
  centres    label marks (96 px columns): the whole tree needs under 0.5x, so the first view is 0.6x centred on the focus
  boundary   a stage that needs exactly 0.5x opens whole; one that needs 0.49x opens at 0.6x on the focus
  radial     a ring layout's first view is still the whole tree, the same view Fit gives
  kept       the reader's own zoom and pan survive a peek; only the Fit button fits again
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "media" / "lineage-fit"
OUT.mkdir(parents=True, exist_ok=True)
checks: list[dict] = []
FIXTURE = "tests/browser/fixtures/lineage-fit.html"
BAR_RESERVED = 44  # px: packages/views/lineage/src/index.js fit() `top`, the bar over the tree's top-left
MARKS = 24  # tests/browser/fixtures/lineage-fit.json: a chain of 18 and 6 side branches


def check(name, ok, value=None):
    checks.append({"name": name, "ok": bool(ok), "value": value})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{value}]" if value is not None else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# the view's svg and bar, each mark's box, the focus mark's centre, and the world's transform
MEASURE = """() => {
  const root = document.querySelector('#v .dv-lineage');
  const r = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, right: b.right, top: b.top, bottom: b.bottom }; };
  const svg = root.querySelector('svg.dv-lineage-svg');
  const focus = root.querySelector('g.dv-lineage-node.dv-focus .dv-lineage-dot');
  const fb = focus && focus.getBoundingClientRect();
  const t = (root.querySelector('.dv-lineage-world').getAttribute('transform') || '').match(/-?[\\d.]+(?:e-?\\d+)?/g).map(Number);
  return { view: r(svg), bar: r(root.querySelector('.dv-lineage-bar')),
    marks: [...root.querySelectorAll('g.dv-lineage-node')].map((g) => ({ id: g.dataset.id, ...r(g.querySelector('.dv-lineage-dot')) })),
    focus: fb && { x: fb.left + fb.width / 2, y: fb.top + fb.height / 2 }, tx: t[0], ty: t[1], k: t[2], layout: root.dataset.layout };
}"""


def open_page(browser, base, query):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{base}/{FIXTURE}{query}")
    page.wait_for_selector("#v .dv-lineage g.dv-lineage-node", timeout=20000)
    # two frames so the first draw's view has settled (the panel, the zoom transform)
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    return page


def outside(m):
    """The marks whose box is not wholly inside the view's rect."""
    v = m["view"]
    return [k["id"] for k in m["marks"] if k["left"] < v["left"] or k["right"] > v["right"] or k["top"] < v["top"] or k["bottom"] > v["bottom"]]


def fit(page):
    page.click("#v .dv-lineage-bar [data-act=fit]")
    page.wait_for_timeout(450)  # the Fit button animates 250 ms
    return page.evaluate(MEASURE)


def main() -> int:
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/" + FIXTURE, timeout=1)
                break
            except Exception:  # noqa: BLE001 - not up yet
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            # ---- picture marks: the whole tree needs 0.5x-0.6x, the first view shows all of it
            page = open_page(browser, base, "?base=image")
            first = page.evaluate(MEASURE)
            page.screenshot(path=str(OUT / "image-first-view.png"))
            after = fit(page)
            picture_fit_k = after["k"]
            check("fixture (picture marks): the Fit button needs a zoom of at least 0.5 and under 0.6 (so the fixture sits between the two thresholds)",
                  0.5 <= after["k"] < 0.6 and len(after["marks"]) == MARKS, f"Fit zoom {after['k']:.3f}, {len(after['marks'])} marks")
            check("lineage first view, picture marks, focus at the last round, 1440x900: every mark's box lies inside the view's rect",
                  len(first["marks"]) == MARKS and not outside(first),
                  f"{len(first['marks'])} marks span x {min(k['left'] for k in first['marks']):.0f}-{max(k['right'] for k in first['marks']):.0f} in a view {first['view']['left']:.0f}-{first['view']['right']:.0f}; outside: {outside(first)[:8]}")
            check("lineage first view, picture marks: it is the Fit button's view (same zoom, same offset), not a second fit",
                  abs(first["k"] - after["k"]) < 0.002 and abs(first["tx"] - after["tx"]) < 1 and abs(first["ty"] - after["ty"]) < 1,
                  f"first k {first['k']:.3f} at ({first['tx']:.1f}, {first['ty']:.1f}); Fit k {after['k']:.3f} at ({after['tx']:.1f}, {after['ty']:.1f})")
            check("lineage first view, picture marks: no page error", not page.errors, page.errors[:2])
            page.context.close()

            # ---- label marks: fitting needs under 0.5x, so 0.6x centred on the focus
            page = open_page(browser, base, "?base=label")
            first = page.evaluate(MEASURE)
            page.screenshot(path=str(OUT / "label-first-view.png"))
            after = fit(page)
            check("fixture (label marks): the Fit button needs a zoom under 0.5", after["k"] < 0.5 and len(after["marks"]) == MARKS, f"Fit zoom {after['k']:.3f}, {len(after['marks'])} marks")
            v, f = first["view"], first["focus"]
            # WHY svg.top + 44: fit() reserves 44 px for the bar over the tree's top-left and centres the focus in the rest;
            # the bar's own measured bottom is a few px off that, so it is not the oracle
            mid_x, mid_y = (v["left"] + v["right"]) / 2, v["top"] + BAR_RESERVED + (v["bottom"] - v["top"] - BAR_RESERVED) / 2
            check("lineage first view, a tree needing under 0.5x: the zoom is 0.6",
                  abs(first["k"] - 0.6) < 0.002, f"zoom {first['k']:.3f}")
            check("lineage first view, a tree needing under 0.5x: the focus mark's centre is at the view's centre across and at the middle below the bar's 44 px down (within 3 px, so a 12 px shift fails)",
                  f is not None and abs(f["x"] - mid_x) <= 3 and abs(f["y"] - mid_y) <= 3,
                  f"focus ({f['x']:.1f}, {f['y']:.1f}) vs centre ({mid_x:.1f}, {mid_y:.1f})" if f else "no focus mark")
            page.context.close()

            # ---- the boundary: a stage sized so the whole tree needs exactly 0.5x (fits, inclusive) and just under it (0.6x on the focus)
            # picture marks sit 56 px apart, so 18 rounds are 19 * 56 + 20 = 1084 px wide: a stage of 590 px needs (590 - 48) / 1084 = 0.5
            probe = open_page(browser, base, "?base=image")
            base_stage = probe.evaluate("() => document.querySelector('#v svg.dv-lineage-svg').clientWidth")
            probe.context.close()
            for stage, whole, label in ((590, True, "exactly 0.5x"), (579, False, "0.49x")):
                page = open_page(browser, base, f"?base=image&w={936 + stage - base_stage}")
                got = page.evaluate("() => document.querySelector('#v svg.dv-lineage-svg').clientWidth")
                first = page.evaluate(MEASURE)
                after = fit(page)
                want_k = (stage - 48) / 1084
                check(f"fixture ({label}): a {stage} px stage makes the Fit button's zoom {want_k:.5f}",
                      got == stage and abs(after["k"] - want_k) < 1e-6 and len(after["marks"]) == MARKS, f"stage {got} px, Fit zoom {after['k']:.6f}")
                if whole:
                    check(f"lineage first view, a tree needing {label}: it opens whole (the threshold is inclusive and is 0.5), the Fit button's view",
                          len(first["marks"]) == MARKS and not outside(first) and abs(first["k"] - after["k"]) < 1e-6
                          and abs(first["tx"] - after["tx"]) < 1 and abs(first["ty"] - after["ty"]) < 1,
                          f"first zoom {first['k']:.6f}; outside {outside(first)[:5]}")
                else:
                    v, f = first["view"], first["focus"]
                    mid_y = v["top"] + BAR_RESERVED + (v["bottom"] - v["top"] - BAR_RESERVED) / 2
                    check(f"lineage first view, a tree needing {label}: it opens at 0.6 on the focus, not whole",
                          abs(first["k"] - 0.6) < 1e-6 and abs(f["x"] - (v["left"] + v["right"]) / 2) <= 3 and abs(f["y"] - mid_y) <= 3 and bool(outside(first)),
                          f"first zoom {first['k']:.6f}; focus ({f['x']:.1f}, {f['y']:.1f}); {len(outside(first))} marks outside")
                page.context.close()

            # ---- radial: unchanged, the whole tree, the Fit view
            page = open_page(browser, base, "?base=image&view=Rings")
            first = page.evaluate(MEASURE)
            after = fit(page)
            check("lineage first view, radial: the whole tree is inside the view and it is the Fit button's view",
                  first["layout"] == "radial" and len(first["marks"]) == MARKS and not outside(first)
                  and abs(first["k"] - after["k"]) < 0.002 and abs(first["tx"] - after["tx"]) < 1 and abs(first["ty"] - after["ty"]) < 1,
                  f"radial first k {first['k']:.3f}, Fit k {after['k']:.3f}; outside {outside(first)[:5]}")
            page.context.close()

            # ---- the reader's own zoom and pan survive; Fit fits again
            page = open_page(browser, base, "?base=image")
            first = page.evaluate(MEASURE)
            page.mouse.move(first["focus"]["x"], first["focus"]["y"])
            page.mouse.wheel(0, -600)
            page.wait_for_timeout(300)
            zoomed = page.evaluate(MEASURE)
            page.mouse.move(zoomed["view"]["left"] + 200, zoomed["view"]["bottom"] - 80)
            page.mouse.down()
            page.mouse.move(zoomed["view"]["left"] + 260, zoomed["view"]["bottom"] - 120, steps=5)
            page.mouse.up()
            page.wait_for_timeout(150)
            moved = page.evaluate(MEASURE)
            page.evaluate("(id) => document.querySelector(`#v g.dv-lineage-node[data-id=\"${id}\"]`).dispatchEvent(new MouseEvent('click', {bubbles: true}))", "c9")
            page.wait_for_selector("#v .dv-peek:not([hidden])", timeout=5000)
            page.wait_for_timeout(300)
            peeked = page.evaluate(MEASURE)
            check("lineage first view: the reader's zoom and pan stand after a peek opens (no re-fit after the first draw)",
                  moved["k"] > first["k"] * 1.3 and abs(peeked["k"] - moved["k"]) < 0.002 and abs(peeked["tx"] - moved["tx"]) < 1 and abs(peeked["ty"] - moved["ty"]) < 1,
                  f"first k {first['k']:.3f}, zoomed k {moved['k']:.3f}, after the peek k {peeked['k']:.3f}")
            page.keyboard.press("Escape")
            again = fit(page)
            check("lineage first view: the Fit button fits the whole tree again", len(again["marks"]) == MARKS and not outside(again) and abs(again["k"] - picture_fit_k) < 0.002,
                  f"k {again['k']:.3f}; outside {outside(again)[:5]}")
            page.context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    (OUT / "lineage-fit-checks.json").write_text(json.dumps(checks, indent=1) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"{len(checks) - len(failed)}/{len(checks)} lineage fit checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
