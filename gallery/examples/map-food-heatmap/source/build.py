"""Build food.json: places that generate food waste in Metro Vancouver, from OpenStreetMap. No names.

    python3 -I gallery/examples/map-food-heatmap/source/build.py [RAW_DIR]

RAW_DIR (argument, else $RAW_DIR, else ./raw) holds osm-food/overpass.json, the answer to food.overpassql (beside
this script) from https://overpass-api.de/api/interpreter. Every amenity=restaurant|fast_food|cafe|food_court node,
way and relation in the bbox (south 49.0, west -123.3, north 49.45, east -122.4); ways and relations at their Overpass
`center`. Only the kind, the OSM id, the point and the `capacity` tag are kept: business names stay out of a public
dataset.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
RAW = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAW_DIR", "raw"))
KIND = {"restaurant": "restaurant", "fast_food": "fast food", "cafe": "cafe", "food_court": "food court"}
PREFIX = {"node": "n", "way": "w", "relation": "r"}


def seats(tags: dict) -> object:
    raw = tags.get("capacity")
    if raw is None:
        return {"value": None, "why": "not tagged in OSM"}
    try:
        return int(raw.strip())
    except ValueError:
        return {"value": None, "why": f"capacity tag is not a number ({raw!r})"}


def main() -> None:
    answer = json.loads((RAW / "osm-food" / "overpass.json").read_text())
    rows = []
    for element in answer["elements"]:
        point = element if element["type"] == "node" else element["center"]
        rows.append({
            "id": f"osm-{PREFIX[element['type']]}{element['id']}",
            "kind": KIND[element["tags"]["amenity"]],
            "location": [round(point["lat"], 5), round(point["lon"], 5)],
            "seats": seats(element["tags"]),
        })
    rows.sort(key=lambda row: row["id"])
    doc = {
        "id": "metro-vancouver-food-places",
        "title": "Food-waste generators in Metro Vancouver (OpenStreetMap)",
        "titleProperty": "kind",
        "source": f"© OpenStreetMap contributors, ODbL; Overpass API, OSM data as of {answer['osm3s']['timestamp_osm_base']}",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "kind": {"type": "text", "label": "Kind"},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "seats": {"type": "number", "label": "Seats (OSM capacity)", "unitText": "seats", "decimals": 0},
        },
        "rows": rows,
    }
    out = HERE / "food.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"food.json: {len(rows)} rows, {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
