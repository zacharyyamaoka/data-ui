"""Browser checks for map-bubbles (docs/CONTRACT.md §42): circle area is proportional to tonnes, rows with no value draw no circle, the answer names the largest. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-bubbles"

import math
ROWS = rows(HERE, "../map-bivariate/provinces.json")
DRAWN = [r for r in ROWS if val(r["disposal_t"]) is not None and isinstance(val(r["location"]), list)]
VMAX = max(val(r["disposal_t"]) for r in DRAWN)
TOP = max(DRAWN, key=lambda r: val(r["disposal_t"]))


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    feats = [f for f in source_features(page, "dvl-1") if f.get("_r") is not None]
    check("bubbles: one circle per province with a disposal figure (the territories' combined figure has no point)", len(feats) == len(DRAWN), f"{len(feats)} vs {len(DRAWN)}")
    worst = max(abs(f["_r"] - max(2, 34 * math.sqrt(f["_s"] / VMAX))) for f in feats)
    exact = sorted(f["_s"] for f in feats) == sorted(val(r["disposal_t"]) for r in DRAWN)
    check("bubbles: radius = 34 px × √(value ÷ largest): area ∝ tonnes, the values exactly as stored", worst < 1e-6 and exact, f"max radius error {worst:.2e}, values exact {exact}")
    on_screen = rendered(page, ["dvl-1"])
    check("bubbles: every circle is on screen at the first frame", len(on_screen) == len(DRAWN), len(on_screen))
    ans = legend(page)["answer"]
    want = f"Largest: {TOP['province']} · {val(TOP['disposal_t']):,} t"
    check("bubbles: the answer names the largest", ans == want, f"{ans!r} vs {want!r}")
    page.context.close()
    themes(ctx, path, CASE)
