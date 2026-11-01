"""sites.json: BC waste facilities (facilities.json) and hospitals (hospitals.json) as one dataset with a `role`
(facility | hospital), so one view can ask "which hospitals are near a facility" (rings, catchments, within).

    python3 gallery/examples/map-catchments/source/combine.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
fac = json.loads((HERE / "facilities.json").read_text())
hos = json.loads((HERE / "hospitals.json").read_text())
props = {**fac["properties"], **hos["properties"]}
props["role"] = {"type": "text", "label": "Role"}
props["kind"] = {"type": "text", "label": "Kind"}
rows = [{**r, "role": "facility"} for r in fac["rows"]] + [{**r, "role": "hospital", "kind": "hospital"} for r in hos["rows"]]
out = {"id": "map-bc-sites", "title": "Waste facilities and hospitals in British Columbia (OpenStreetMap)", "titleProperty": "name", "source": "© OpenStreetMap contributors, ODbL; facilities.json and hospitals.json joined by source/combine.py", "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"}, "properties": props, "rows": rows}
(HERE / "sites.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
print(f"sites.json: {len(rows)} rows")
