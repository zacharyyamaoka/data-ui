"""Browser checks for map-collection-routes (docs/CONTRACT.md §42): three routes with their straight-line lengths, every pickup drawn. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-collection-routes"

import re
ROWS = rows(HERE, "day.json")
ROUTES = [r for r in ROWS if r["kind"] == "route"]
PICKUPS = [r for r in ROWS if r["kind"] == "pickup"]


def length(path):
    return sum(km(path[i - 1], path[i]) for i in range(1, len(path)))


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    leg = legend(page)["groups"][0]
    drawn = {re.sub(r" route.*", "", label): float(re.search(r"([\d.]+) km", label).group(1)) for label, _ in leg["rows"]}
    want = {r["truck"]: length(r["path"]) for r in ROUTES}
    check("routes: each truck's straight-line length matches a haversine over its stored path (±0.05 km)", drawn.keys() == want.keys() and all(abs(drawn[k] - want[k]) <= 0.05 for k in want), f"{drawn} vs { {k: round(v, 2) for k, v in want.items()} }")
    pts = source_features(page, "dvl-1")
    check("routes: every pickup is a point", len(pts) == len(PICKUPS), f"{len(pts)} vs {len(PICKUPS)}")
    total = sum(want.values())
    check("routes: the answer gives the routes and their total length", legend(page)["answer"] == f"{len(ROUTES)} routes · {total:.1f} km in all", legend(page)["answer"])
    page.context.close()
    themes(ctx, path, CASE)
