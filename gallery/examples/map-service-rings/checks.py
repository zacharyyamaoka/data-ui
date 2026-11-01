"""Browser checks for map-service-rings (docs/CONTRACT.md §42): hospitals per ring band match a haversine nearest-station oracle; a band opens its hospitals. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-service-rings"

ROWS = rows(HERE, "../map-catchments/sites.json")
SITES = [val(r["location"]) for r in ROWS if r.get("kind") == "transfer station" and isinstance(val(r["location"]), list)]
HOSP = [val(r["location"]) for r in ROWS if r["role"] == "hospital" and isinstance(val(r["location"]), list)]
NEAREST = [min(km(h, s) for s in SITES) for h in HOSP]
BANDS = [sum(1 for d in NEAREST if d <= 10), sum(1 for d in NEAREST if 10 < d <= 25), sum(1 for d in NEAREST if 25 < d <= 50), sum(1 for d in NEAREST if d > 50)]


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    leg = legend(page)
    bands = [n for _, n in leg["groups"][0]["rows"]]
    check("rings: hospitals within 10, 25, 50 km and beyond, by nearest transfer station, as a haversine says", bands == BANDS, f"{bands} vs {BANDS}")
    check("rings: one answer first", leg["answer"] == f"{BANDS[0]} of {len(HOSP)} hospitals within 10 km of a transfer station", leg["answer"])
    page.click(f"{V} .dv-map-bands tr[data-band='1']")
    n, title = peek_rows(page)
    check("rings: a band row opens its hospitals", n == BANDS[1], f"{n} vs {BANDS[1]} ({title})")
    page.context.close()
    themes(ctx, path, CASE)
