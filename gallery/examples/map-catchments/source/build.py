"""Build facilities.json and hospitals.json: waste facilities and hospitals in British Columbia, from OpenStreetMap.

    python3 -I gallery/examples/map-catchments/source/build.py [RAW_DIR]

RAW_DIR (argument, else $RAW_DIR, else ./raw) holds the answers of the two Overpass queries beside this script:
    osm-facilities/overpass.json   facilities.overpassql: amenity=waste_transfer_station, landuse=landfill and
                                   amenity=recycling + recycling_type=centre inside ISO3166-2=CA-BC
    osm-hospitals/overpass.json    hospitals.overpassql: amenity=hospital inside ISO3166-2=CA-BC
Ways and relations sit at their Overpass `center`. A facility keeps its OSM name only when it reads as public
infrastructure (see `public_name`); a private business name is withheld with a reason. Hospitals keep their names.
Nothing else from the tags is carried: no operator, phone, email, website, contact or address.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
RAW = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAW_DIR", "raw"))
METRO_VANCOUVER = (49.0, -123.3, 49.45, -122.4)  # south, west, north, east
PREFIX = {"node": "n", "way": "w", "relation": "r"}

# A public body in an `operator` tag: municipalities, regional districts, First Nations, the province.
PUBLIC_OPERATOR = re.compile(
    r"\b(city|district|regional|metro vancouver|town|village|municipality|township|county|first nation|nation|band|"
    r"government|province|ministry|islands trust|landfill|crd|rdn|rdck|rdco|rdos|rdek|rdkb|rdffg|rdbn|rdks|tnrd|cvrd|csrd|"
    r"slrd|fvrd|prrd|scrd|qrd|rdno|rdmw|rdac)\b",
    re.I,
)
# A name that names the facility rather than a business.
FACILITY_WORDS = re.compile(
    r"\b(transfer (station|site|facility)|land ?fill( site)?|disposal facility|recycling (centre|center|depot|facility)|eco[- ]?depot|"
    r"waste (management|disposal|transfer|site|facility|centre|center)|refuse (site|disposal|station)|"
    r"resource recovery|recycling (and|&) waste|solid waste|dump|garbage)\b",
    re.I,
)
BUSINESS_WORDS = re.compile(r"\b(ltd|inc|corp|services|industries|enterprises|company|co\.|bottles?|return-it|recycle-it|power)\b|['’]s\b", re.I)


def kind(tags: dict) -> str:
    if tags.get("amenity") == "waste_transfer_station":
        return "transfer station"
    if tags.get("landuse") == "landfill":
        return "landfill"
    return "recycling centre"


def public_name(tags: dict) -> object:
    name = tags.get("name")
    if not name:
        return {"value": None, "why": "no name tagged in OSM"}
    if tags.get("brand") or BUSINESS_WORDS.search(name):
        return {"value": None, "why": "a business name: withheld from the public dataset"}
    operator = tags.get("operator")
    if tags.get("operator:type") in ("public", "government") or (operator and PUBLIC_OPERATOR.search(operator)):
        return name
    if operator:
        return {"value": None, "why": "privately operated: name withheld from the public dataset"}
    if FACILITY_WORDS.search(name):
        return name
    return {"value": None, "why": "not clearly public infrastructure: name withheld from the public dataset"}


def point(element: dict) -> list[float]:
    p = element if element["type"] == "node" else element["center"]
    return [round(p["lat"], 5), round(p["lon"], 5)]


def number(tags: dict, key: str) -> object:
    raw = tags.get(key)
    if raw is None:
        return {"value": None, "why": "not tagged in OSM"}
    try:
        return int(raw.strip())
    except ValueError:
        return {"value": None, "why": f"{key} tag is not a number ({raw!r})"}


def write(name: str, doc: dict) -> None:
    out = HERE / name
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(f"{name}: {len(doc['rows'])} rows, {out.stat().st_size} bytes")


def main() -> None:
    south, west, north, east = METRO_VANCOUVER
    answer = json.loads((RAW / "osm-facilities" / "overpass.json").read_text())
    rows = []
    for element in answer["elements"]:
        tags = element["tags"]
        lat, lng = point(element)
        rows.append({
            "id": f"osm-{PREFIX[element['type']]}{element['id']}",
            "name": public_name(tags),
            "kind": kind(tags),
            "location": [lat, lng],
            "in_metro_vancouver": south <= lat <= north and west <= lng <= east,
        })
    rows.sort(key=lambda row: row["id"])
    write("facilities.json", {
        "id": "bc-waste-facilities",
        "title": "Waste facilities in British Columbia (OpenStreetMap)",
        "titleProperty": "name",
        "source": f"© OpenStreetMap contributors, ODbL; Overpass API, OSM data as of {answer['osm3s']['timestamp_osm_base']}",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "name": {"type": "text", "label": "Facility"},
            "kind": {"type": "text", "label": "Kind"},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "in_metro_vancouver": {"type": "boolean", "label": "In Metro Vancouver bbox"},
        },
        "rows": rows,
    })

    answer = json.loads((RAW / "osm-hospitals" / "overpass.json").read_text())
    rows = []
    for element in answer["elements"]:
        tags = element["tags"]
        emergency = tags.get("emergency")
        rows.append({
            "id": f"osm-{PREFIX[element['type']]}{element['id']}",
            "name": tags.get("name") or {"value": None, "why": "no name tagged in OSM"},
            "location": point(element),
            "emergency": emergency if emergency in ("yes", "no") else None,
            "beds": number(tags, "beds"),
        })
    rows.sort(key=lambda row: row["id"])
    write("hospitals.json", {
        "id": "bc-hospitals",
        "title": "Hospitals in British Columbia (OpenStreetMap)",
        "titleProperty": "name",
        "source": f"© OpenStreetMap contributors, ODbL; Overpass API, OSM data as of {answer['osm3s']['timestamp_osm_base']}",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "name": {"type": "text", "label": "Hospital"},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "emergency": {"type": "text", "label": "Emergency department (OSM)"},
            "beds": {"type": "number", "label": "Beds (OSM)", "unitText": "beds", "decimals": 0},
        },
        "rows": rows,
    })


if __name__ == "__main__":
    main()
