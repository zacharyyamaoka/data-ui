"""Browser checks for map-sorting-line (docs/CONTRACT.md §42): local space is metres both ways, robots sized by picks per hour, the fault robot stands apart. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-sorting-line"

import math
import re
ROWS = rows(HERE, "line.json")
ROBOTS = [r for r in ROWS if r["kind"] == "robot"]
TOP = max(ROBOTS, key=lambda r: r["picks_per_hour"])


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    a, b = ROWS[0]["xy"], ROBOTS[-1]["xy"]
    px = page.evaluate("""([s, a, b]) => { const m = document.querySelector(s).dvMap, P = (x, y) => m.project([x / 111320, y / 111320]);
      const pa = P(...a), pb = P(...b), o = P(0, 0), ex = P(10, 0), ey = P(0, 10);
      return { ab: Math.hypot(pa.x - pb.x, pa.y - pb.y), x10: Math.hypot(ex.x - o.x, ex.y - o.y), y10: Math.hypot(ey.x - o.x, ey.y - o.y) }; }""", [scope(False), a, b])
    metres = math.hypot(a[0] - b[0], a[1] - b[1])
    check("floor plan: 10 m east and 10 m north are the same length on screen (within 0.1%)", abs(px["x10"] / px["y10"] - 1) < 1e-3, px)
    check("floor plan: a distance on screen ÷ pixels per metre is the distance in metres (within 0.5%)", abs(px["ab"] / (px["x10"] / 10) - metres) / metres < 5e-3, f"{px['ab'] / (px['x10'] / 10):.3f} vs {metres:.3f} m")
    scale = page.inner_text(f"{V} .maplibregl-ctrl-scale")
    check("floor plan: the scale bar reads in metres", re.search(r"\d\s*m$", scale.strip()) is not None, scale)
    pts = source_features(page, "dvl-1")
    cols = {f["_col"] for f in pts if ROWS_BY_I(page, f)["status"] == "fault"}
    run_cols = {f["_col"] for f in pts if ROWS_BY_I(page, f)["status"] == "running"}
    check("floor plan: the faulted robot's colour is not the running ones'", cols and not (cols & run_cols), f"fault {cols}, running {run_cols}")
    check("floor plan: the answer names the busiest robot", legend(page)["answer"].startswith(f"Largest: {TOP['name']} · "), legend(page)["answer"])
    page.context.close()
    themes(ctx, path, CASE)


def ROWS_BY_I(page, f):  # noqa: N802
    return next(r for r in ROWS if r["id"] == model_row(page, f["_i"])["id"])
