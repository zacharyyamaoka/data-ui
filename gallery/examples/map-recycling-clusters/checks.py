"""Browser checks for map-recycling-clusters (docs/CONTRACT.md §42): clusters count every row once, a cluster click zooms in, a point opens its row. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-recycling-clusters"

ROWS = rows(HERE, "recycling.json")
WITH_AT = [r for r in ROWS if isinstance(val(r["location"]), list)]
BY_TYPE = collections.Counter(r["type"] for r in WITH_AT)


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    clusters = rendered(page, ["dvl-0-c"])
    singles = rendered(page, ["dvl-0"])
    drawn = sum(c["point_count"] for c in clusters) + len(singles)
    check("clusters: at the province view every row with a position is on screen once, in a cluster or alone",
          drawn == len(WITH_AT) and len(clusters) > 0, f"{len(clusters)} clusters + {len(singles)} points = {drawn}; rows with a position {len(WITH_AT)}")
    leg = legend(page)
    drawn_types = {label: n for label, n in leg["groups"][0]["rows"]}
    check("clusters: the legend counts each type as the data does", drawn_types == dict(BY_TYPE), f"{drawn_types} vs {dict(BY_TYPE)}")
    z0 = float(page.get_attribute(f"{V} .dv-view-map", "data-zoom"))
    clicked = click_feature(page, "dvl-0-c", "(p) => p.point_count >= 5")
    ctx.until(page, "([s, z]) => Number(document.querySelector(s).dataset.zoom) > z + 0.5", [scope(False), z0])
    ready(ctx, page)
    z1 = float(page.get_attribute(f"{V} .dv-view-map", "data-zoom"))
    check("clusters: a click on a cluster zooms into it (MapLibre's expansion zoom)", clicked is not None and z1 > z0 + 0.5, f"zoom {z0:.2f} -> {z1:.2f}")
    p = click_feature(page, "dvl-0", "(p) => true")
    n, title = peek_rows(page) if p else (0, "")
    want = next(r for r in ROWS if r["id"] == model_row(page, p["_i"])["id"]) if p else None
    check("clusters: a single point opens its own row in the peek", p is not None and want is not None and title.strip().startswith(str(val(want.get("name")) or want["label"])), title)
    page.context.close()
    themes(ctx, path, CASE)
