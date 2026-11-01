"""Browser checks for map-3d-columns (docs/CONTRACT.md §42): columns are fill-extrusions, tilted, the tallest is the busiest hexagon. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-3d-columns"

ROWS = rows(HERE, "../map-food-heatmap/food.json")


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    pitch = page.get_attribute(f"{V} .dv-view-map", "data-pitch")
    kind = page.evaluate("(s) => document.querySelector(s).dvMap.getLayer('dvl-0').type", scope(False))
    check("3D: the hexagons are fill-extrusion columns under a 50° camera", kind == "fill-extrusion" and pitch == "50", f"{kind}, pitch {pitch}")
    cells = source_features(page, "dvl-0")
    top = max(cells, key=lambda c: c["_n"])
    check("3D: the counts add up to every row, and the tallest column is the busiest hexagon at the full 3,000 m",
          sum(c["_n"] for c in cells) == len(ROWS) and top["_h"] == 3000 and all(c["_h"] <= 3000 for c in cells), f"{sum(c['_n'] for c in cells)} rows; tallest {top['_h']} m holds {top['_n']}")
    page.context.close()
    themes(ctx, path, CASE)
