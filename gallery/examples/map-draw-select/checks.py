"""Browser checks for map-draw-select (docs/CONTRACT.md §42): a drawn polygon counts exactly the rows inside it (ray-cast oracle) and opens them. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-draw-select"

ROWS = rows(HERE, "../map-food-heatmap/food.json")


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    page.click(f"{V} .dv-map-draw-btn")
    page.wait_for_timeout(500)
    st = page.locator(f"{V} .dv-map-stage").bounding_box()
    cx, cy = st["x"] + st["width"] * 0.5, st["y"] + st["height"] * 0.5
    pts = [(cx - 90, cy - 70), (cx + 100, cy - 60), (cx + 80, cy + 80), (cx - 70, cy + 60)]
    for x, y in pts:
        page.mouse.click(x, y)
        page.wait_for_timeout(120)
    page.mouse.click(*pts[0])
    ctx.until(page, "() => document.querySelector('#example .dv-map-drawn-n')")
    ring = page.evaluate("([s, pts, ox, oy]) => { const m = document.querySelector(s).dvMap, c = m.getCanvas().getBoundingClientRect(); return pts.map(([x, y]) => { const p = m.unproject([x - c.x, y - c.y]); return [p.lng, p.lat]; }); }", [scope(False), pts, 0, 0])
    want = sum(1 for r in ROWS if isinstance(val(r["location"]), list) and inside([val(r["location"])[1], val(r["location"])[0]], ring))
    got = int(page.inner_text(f"{V} .dv-map-drawn-n").replace(",", ""))
    check("draw: the panel counts exactly the places inside the drawn polygon (± 1 for a point on the edge)", want > 0 and abs(got - want) <= 1, f"panel {got}, ray-cast oracle {want}")
    page.click(f"{V} .dv-map-drawn-open")
    n, title = peek_rows(page)
    check("draw: Open these rows lists the same rows", n == got, f"{n} vs {got} ({title})")
    page.context.close()
    themes(ctx, path, CASE)
