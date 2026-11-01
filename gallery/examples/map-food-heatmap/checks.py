"""Browser checks for map-food-heatmap (docs/CONTRACT.md §42): the self-hosted PMTiles basemap draws OpenStreetMap features, the heatmap is a heatmap layer, single places appear past zoom 13. Expected numbers come from this case's JSON through the
plain-Python oracles in tests/browser/map_helpers.py; measurements from the running map."""

import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "tests" / "browser"))
from map_helpers import V, camera, click_feature, drag_panel, inside, km, legend, model_row, open_case, peek_rows, ready, rendered, rows, scope, source_features, themes, val  # noqa: E402,F401

CASE = "map-food-heatmap"

ROWS = rows(HERE, "food.json")


def run(ctx, path):
    check = ctx.check
    page = open_case(ctx, path)
    base = page.evaluate("""(s) => { const m = document.querySelector(s).dvMap; const ids = m.getStyle().layers.map((l) => l.id).filter((i) => i.startsWith('dvb-'));
      return { layers: ids.length, features: m.queryRenderedFeatures({ layers: ids }).length, src: m.getSource('dvb') && m.getSource('dvb').type }; }""", scope(False))
    check("basemap: metro-vancouver.pmtiles draws OpenStreetMap water, roads and places (vector tiles, same site)", base["src"] == "vector" and base["features"] > 100, base)
    kind = page.evaluate("(s) => document.querySelector(s).dvMap.getLayer('dvl-0').type", scope(False))
    check("heatmap: the density is MapLibre's heatmap layer", kind == "heatmap", kind)
    page.evaluate("(s) => document.querySelector(s).dvMap.jumpTo({ center: [-123.1207, 49.2827], zoom: 14.5 })", scope(False))
    ready(ctx, page)
    pts = rendered(page, ["dvl-0-p"])
    check("heatmap: past zoom 13 the single places draw as points, each a real row", 0 < len(pts) < len(ROWS) and all(isinstance(p.get("_i"), int) for p in pts), f"{len(pts)} points downtown")
    page.context.close()
    themes(ctx, path, CASE)
