"""Browser checks for map-small-multiples (docs/CONTRACT.md §42): six maps, one per year, one shared legend, one camera. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-small-multiples"

def run(ctx, path):
    check = ctx.check
    page = ctx.page(path)
    ctx.until(page, "() => [...document.querySelectorAll('#example .dv-map-cell')].length === 6 && [...document.querySelectorAll('#example .dv-map-cell')].every((c) => c.dvMap && c.dvMap.loaded() && c.dvMap.getSource('dvl-0'))")
    ctx.frames(page, 4)
    caps = page.locator(f"{V} .dv-map-cell figcaption").all_inner_texts()
    check("multiples: six maps in year order", caps == [f"Year: {y}" for y in (2000, 2005, 2010, 2015, 2020, 2024)], caps)
    check("multiples: one legend for all six", page.locator(f"{V} .dv-map-panel section").count() == 1)
    box = page.locator(f"{V} .dv-map-cell").first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 60, box["y"] + box["height"] / 2 + 30, steps=8)
    page.mouse.up()
    ctx.frames(page, 4)
    cams = page.evaluate("() => [...document.querySelectorAll('#example .dv-map-cell')].map((c) => { const p = c.dvMap.getCenter(); return [p.lng, p.lat, c.dvMap.getZoom()]; })")
    same = all(abs(c[0] - cams[0][0]) < 1e-6 and abs(c[1] - cams[0][1]) < 1e-6 and abs(c[2] - cams[0][2]) < 1e-6 for c in cams)
    check("multiples: panning one map moves all six (one camera)", same, [[round(v, 4) for v in c] for c in cams])
    page.context.close()
    themes(ctx, path, CASE)
