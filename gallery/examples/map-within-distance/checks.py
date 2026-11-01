"""Browser checks for map-within-distance (docs/CONTRACT.md §42): hospitals within a distance of a facility match a haversine oracle, and the slider re-answers. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-within-distance"

ROWS = rows(HERE, "../map-catchments/sites.json")
FAC = [val(r["location"]) for r in ROWS if r["role"] == "facility" and isinstance(val(r["location"]), list)]
HOSP = [val(r["location"]) for r in ROWS if r["role"] == "hospital" and isinstance(val(r["location"]), list)]
NEAREST = [min(km(h, f) for f in FAC) for h in HOSP]


def within(d):
    return sum(1 for x in NEAREST if x <= d)


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    ans = legend(page)["answer"]
    check("within: 15 km, the count a haversine to the nearest facility gives", ans == f"{within(15)} of {len(HOSP)} hospitals within 15 km", f"{ans!r}; oracle {within(15)}")
    solid = len([f for f in source_features(page, "dvl-0") if f["_in"] == 1])
    check("within: the solid points are those hospitals", solid == within(15), solid)
    page.evaluate("(s) => { const r = document.querySelector(s + ' .dv-map-within input'); r.value = '40'; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); }", scope(False))
    ctx.until(page, "(want) => (document.querySelector('#example .dv-map-answer') || {}).textContent === want", f"{within(40)} of {len(HOSP)} hospitals within 40 km")
    ans = legend(page)["answer"]
    check("within: the slider at 40 km re-answers, and the distance is part of the view (in its entry)", ans == f"{within(40)} of {len(HOSP)} hospitals within 40 km" and page.evaluate("() => document.querySelector('#example').view.layers[0].km") == 40, ans)
    page.context.close()
    themes(ctx, path, CASE)
