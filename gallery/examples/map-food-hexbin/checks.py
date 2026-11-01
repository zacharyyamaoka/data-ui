"""Browser checks for map-food-hexbin (docs/CONTRACT.md §42): every row lands in one H3 hexagon, the counts add up, a hexagon opens exactly its rows. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-food-hexbin"

ROWS = rows(HERE, "../map-food-heatmap/food.json")
WITH_AT = [r for r in ROWS if isinstance(val(r["location"]), list)]


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    cells = source_features(page, "dvl-0")
    check("hexbin: the hexagons' counts add up to every row with a position", sum(c["_n"] for c in cells) == len(WITH_AT), f"{sum(c['_n'] for c in cells)} vs {len(WITH_AT)} in {len(cells)} cells")
    leg = legend(page)["groups"][0]
    check("hexbin: the legend counts every drawn hexagon once and says it is derived", sum(n for _, n in leg["rows"]) == len(cells) and "derived" in leg["title"], [n for _, n in leg["rows"]])
    top = max(cells, key=lambda c: c["_n"])
    p = click_feature(page, "dvl-0", f"(p) => p._n === {top['_n']}")
    n, title = peek_rows(page)
    check("hexbin: a click on the busiest hexagon lists exactly its rows", p is not None and n == top["_n"], f"peek lists {n}, hexagon holds {top['_n']}")
    page.context.close()
    themes(ctx, path, CASE)
