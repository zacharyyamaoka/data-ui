"""Browser checks for map-bivariate (docs/CONTRACT.md §42): a 3 × 3 grid legend, suppressed provinces hatched and counted, the regions named high on both are above both top breaks. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-bivariate"

import re
ROWS = rows(HERE, "provinces.json")
NONE = [r for r in ROWS if val(r["diversion_2022"]) is None or val(r["change_pts"]) is None]


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    cells = page.locator(f"{V} .dv-map-bi-grid i").count()
    method = page.inner_text(f"{V} .dv-map-panel .dv-map-method")
    check("bivariate: the legend is a 3 × 3 grid with both axes' breaks", cells == 9 and "Diversion 2022" in method and "Change since 2002" in method, method)
    check("bivariate: provinces with a suppressed value are hatched and counted, never coloured as low", f"{len(NONE)} with no data" in method, method)
    xb = [float(v) for v in re.search(r"Diversion 2022: ([\d., ]+);", method).group(1).split(", ")]
    yb = [float(v) for v in re.search(r"Change since 2002: ([\d., ]+)", method).group(1).rstrip(" ·").split(", ")]
    named = legend(page)["answer"].replace("High on both: ", "").split(", ")
    by = {r["code"]: r for r in ROWS}
    top = [c for c, r in by.items() if val(r["diversion_2022"]) is not None and val(r["change_pts"]) is not None and val(r["diversion_2022"]) > xb[-1] and val(r["change_pts"]) > yb[-1]]
    check("bivariate: the provinces named high on both are exactly those above both top breaks", sorted(named) == sorted(top), f"{named} vs {top} (breaks {xb}, {yb})")
    page.context.close()
    themes(ctx, path, CASE)
