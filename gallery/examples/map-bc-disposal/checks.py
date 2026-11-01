"""Browser checks for map-bc-disposal (docs/CONTRACT.md §42): regions join their 2024 row, no-data is hatched and counted, the answer names the highest, a click opens the row, the legend drags. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-bc-disposal"

import json
ROWS = [r for r in rows(HERE, "disposal.json") if r["year"] == 2024]
GEO = json.loads((HERE / "districts.geojson").read_text())["features"]
VALUE = {r["rd"]: val(r["kg_per_capita"]) for r in ROWS}
WITH = [f for f in GEO if VALUE.get(f["properties"]["rd"]) is not None]
TOP = max(WITH, key=lambda f: VALUE[f["properties"]["rd"]])


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    feats = source_features(page, "dvl-0")
    coloured = [f for f in feats if f["_k"] >= 0]
    check("choropleth: every district with a 2024 value is coloured; the rest are no data", len(coloured) == len(WITH) and len(feats) == len(GEO),
          f"{len(coloured)} coloured of {len(feats)} shapes; oracle {len(WITH)} of {len(GEO)}")
    leg = legend(page)
    g = leg["groups"][0]
    check("choropleth: the legend counts no-data shapes apart (hatched), never as 0", g["none"] == len(GEO) - len(WITH) and sum(n for _, n in g["rows"]) == len(WITH),
          f"classes {[n for _, n in g['rows']]}, no data {g['none']}")
    check("choropleth: the legend says its unit and how the classes were cut", "kg/person/yr" in g["title"] and "quantiles, 5 classes" in page.inner_text(f"{V} .dv-map-panel"), g["title"])
    want = f"Highest: {TOP['properties']['name']} · {VALUE[TOP['properties']['rd']]:,.0f} kg/person/yr"
    check("choropleth: one answer first, the highest district and its value", leg["answer"] == want, f"{leg['answer']!r} vs {want!r}")
    p = click_feature(page, "dvl-0", f"(p) => p.rd === {json.dumps(TOP['properties']['rd'])}")
    n, title = peek_rows(page)
    check("choropleth: a click on a district opens its row", p is not None and TOP["properties"]["name"].split()[0] in title, title)
    page.keyboard.press("Escape")
    drag_panel(ctx, page, CASE)
    page.context.close()
    # without JavaScript: the page shows the captured picture of the first view, and the .base and data as text
    nojs = ctx.browser.new_context(java_script_enabled=False, viewport={"width": 1280, "height": 900})
    pg = nojs.new_page()
    pg.goto(f"{ctx.base}/{path}")
    pg.wait_for_load_state("load")
    shot = pg.evaluate("() => { const i = document.querySelector('.noscript-shot img'); return i ? [i.naturalWidth, i.getBoundingClientRect().height] : null; }")
    text = pg.inner_text(".case-files")
    check("no JS: the case page shows a picture of the map and its .base and data as text", bool(shot) and shot[0] > 400 and shot[1] > 100 and "regions" in text and "kg_per_capita" in text, shot)
    nojs.close()
    themes(ctx, path, CASE)
