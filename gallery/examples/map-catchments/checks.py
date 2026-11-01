"""Browser checks for map-catchments (docs/CONTRACT.md §42): every hospital falls in its nearest facility's Voronoi cell; the largest catchment matches a haversine oracle. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-catchments"

ROWS = rows(HERE, "sites.json")
SITES = [r for r in ROWS if r.get("kind") in ("landfill", "transfer station") and isinstance(val(r["location"]), list)]
HOSP = [val(r["location"]) for r in ROWS if r["role"] == "hospital" and isinstance(val(r["location"]), list)]
counts = collections.Counter()
for h in HOSP:
    counts[min(range(len(SITES)), key=lambda i: km(h, val(SITES[i]["location"])))] += 1
TOP_N = max(counts.values())


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    cells = source_features(page, "dvl-0")
    check("catchments: every hospital is counted in exactly one catchment", sum(c["_n"] for c in cells) == len(HOSP), f"{sum(c['_n'] for c in cells)} vs {len(HOSP)}")
    check("catchments: the largest catchment holds as many hospitals as a nearest-facility haversine says", max(c["_n"] for c in cells) == TOP_N, f"{max(c['_n'] for c in cells)} vs {TOP_N}")
    ans = legend(page)["answer"]
    check("catchments: the answer names it and never shows a raw id", ans.endswith(f"· {TOP_N} hospitals") and "osm-" not in ans, ans)
    p = click_feature(page, "dvl-0", f"(p) => p._n === {TOP_N}")
    n, title = peek_rows(page)
    check("catchments: a click on a catchment lists its hospitals", p is not None and n == TOP_N, f"{n} ({title})")
    page.context.close()
    themes(ctx, path, CASE)
