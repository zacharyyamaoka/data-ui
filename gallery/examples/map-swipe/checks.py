"""Browser checks for map-swipe (docs/CONTRACT.md §42): two maps under one divider: the handle drags, the clip follows, both share a camera. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-swipe"

def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    ctx.until(page, "() => { const m = document.querySelector('#example .dv-map-after'); return m && m.dvMap && m.dvMap.loaded() && m.dvMap.getSource('dvl-0'); }")
    ctx.frames(page, 3)
    canv = page.evaluate("() => [...document.querySelectorAll('#example canvas.maplibregl-canvas')].map((c) => { const b = c.getBoundingClientRect(); return [b.width, b.height]; })")
    check("swipe: two maps, each the full size of the stage", len(canv) == 2 and canv[0] == canv[1] and canv[0][1] > 200, canv)
    exp = lambda: page.evaluate("() => document.querySelector('#example img-comparison-slider').shadowRoot.getElementById('first').style.getPropertyValue('--exposure')")
    e0 = exp()
    h = page.evaluate("() => { const b = document.querySelector('#example img-comparison-slider').shadowRoot.getElementById('handle').getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }")
    page.mouse.move(*h)
    page.mouse.down()
    page.mouse.move(h[0] - 150, h[1], steps=8)
    page.mouse.up()
    e1 = exp()
    check("swipe: dragging the handle moves the divider", e0 == "50%" and e1 != e0, f"--exposure {e0} -> {e1}")
    st = page.locator(f"{V} .dv-map-stage").bounding_box()
    start = camera(page, "#example .dv-map-after")
    page.mouse.move(st["x"] + st["width"] * 0.8, st["y"] + st["height"] * 0.5)
    page.mouse.down()
    page.mouse.move(st["x"] + st["width"] * 0.8 - 80, st["y"] + st["height"] * 0.5 + 40, steps=8)
    page.mouse.up()
    # WHY wait for both, and why `moved`: the two cameras are read one after the other, so a read during the pan's inertia sees two
    # frames; and with no pan at all (the slider took the pointer until 2026-10-30) they were equal because neither moved
    ctx.until(page, "() => ['#example .dv-view-map', '#example .dv-map-after'].every((s) => !document.querySelector(s).dvMap.isMoving())")
    ctx.frames(page, 3)
    a = camera(page, "#example .dv-view-map")
    b = camera(page, "#example .dv-map-after")
    moved = abs(b[0] - start[0]) > 1e-3
    check("swipe: panning the right map moves the left one too (one camera, two years)", moved and all(abs(x - y) < 1e-6 for x, y in zip(a, b)), f"{start} -> {b}, left {a}")
    page.context.close()
    themes(ctx, path, CASE)
