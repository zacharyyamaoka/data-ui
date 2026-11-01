"""day.json: the synthetic routes (routes.json) and their stops (stops.json) as one dataset, so one .base view can
draw both (data-ui reads one data file per view). kind: route | depot | pickup. Run after build.py.

    python3 gallery/examples/map-collection-routes/source/combine.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
routes = json.loads((HERE / "routes.json").read_text())
stops = json.loads((HERE / "stops.json").read_text())
props = {**stops["properties"], **routes["properties"]}
props["kind"] = {"type": "text", "label": "Kind"}
props["name"] = {"type": "text", "label": "Name"}
rows = []
for r in routes["rows"]:
    rows.append({**r, "kind": "route", "name": f"{r['truck']} route"})
for s in stops["rows"]:
    rows.append({**s, "name": f"{s['truck']} · {s['stop']}"})
out = {"id": "map-collection-day", "title": "Food-court collection routes and stops, 14 Oct 2026 (synthetic)", "titleProperty": "name", "source": "synthetic routes over real places: OSM food courts and the Vancouver South Transfer Station (© OpenStreetMap contributors, ODbL); routes.json and stops.json joined by source/combine.py", "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"}, "properties": props, "rows": rows}
(HERE / "day.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
print(f"day.json: {len(rows)} rows")
