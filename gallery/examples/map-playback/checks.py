"""Browser checks for map-playback (docs/CONTRACT.md §42): the scrubber shows exactly the pickups in the trail window, play moves time forward. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-playback"

from datetime import datetime
ROWS = rows(HERE, "../map-collection-routes/day.json")
STOPS = [r for r in ROWS if r["kind"] != "route"]
T = sorted(datetime.fromisoformat(r["at"]).timestamp() * 1000 for r in STOPS)
TRAIL = 10800 * 1000


def shown_at(t):
    return sum(1 for x in T if t - TRAIL <= x <= t)


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    for frac in (0.15, 0.5, 1.0):
        t = T[0] + (T[-1] - T[0]) * frac
        page.evaluate("([s, t]) => { const r = document.querySelector(s + ' .dv-map-time input'); r.value = String(t); r.dispatchEvent(new Event('input')); }", [scope(False), t])
        ready(ctx, page)
        drawn = len(rendered(page, ["dvl-1"]))
        bar = int(page.get_attribute(f"{V} .dv-map-time", "data-shown"))
        check(f"playback at {frac:.0%} of the day: the map draws exactly the pickups of the last three hours", drawn == shown_at(t) == bar, f"drawn {drawn}, bar says {bar}, oracle {shown_at(t)}")
    page.evaluate("(s) => { const r = document.querySelector(s + ' .dv-map-time input'); r.value = r.min; r.dispatchEvent(new Event('input')); }", scope(False))
    t0 = float(page.input_value(f"{V} .dv-map-time input"))
    page.click(f"{V} .dv-map-play")
    ctx.until(page, "([s, t]) => Number(document.querySelector(s + ' .dv-map-time input').value) > t + 60000", [scope(False), t0])
    t1 = float(page.input_value(f"{V} .dv-map-time input"))
    check("playback: play moves the time forward", t1 > t0 + 60000, f"{t0} -> {t1}")
    page.context.close()
    themes(ctx, path, CASE)
