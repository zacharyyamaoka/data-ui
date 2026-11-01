"""Browser checks for map-waste-flows (docs/CONTRACT.md §42): one arc per flow with both ends known, width grows with tonnes, rows with a missing end are counted. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-waste-flows"

ROWS = rows(HERE, "flows.json")
BOTH = [r for r in ROWS if isinstance(val(r["origin"]), list) and isinstance(val(r["destination"]), list)]


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    arcs = source_features(page, "dvl-0")
    check("flows: one arc per row with both ends placed", len(arcs) == len(BOTH), f"{len(arcs)} vs {len(BOTH)}")
    check("flows: each arc carries its row's tonnes exactly", sorted(a["_v"] for a in arcs) == sorted(val(r["tonnes"]) for r in BOTH))
    by = sorted(arcs, key=lambda a: a["_v"])
    check("flows: a bigger flow is never drawn thinner", all(by[i]["_w"] <= by[i + 1]["_w"] for i in range(len(by) - 1)), [round(a["_w"], 2) for a in by])
    note = legend(page)["groups"][0]["note"]
    missing = len(ROWS) - len(BOTH)
    check("flows: the legend says how many rows have no position at one end", f"{missing} rows have no position" in note, note)
    on = rendered(page, ["dvl-0"])
    check("flows: every arc is on screen at the first frame (the frame fits both ends)", len(on) == len(BOTH), len(on))
    page.context.close()
    themes(ctx, path, CASE)
