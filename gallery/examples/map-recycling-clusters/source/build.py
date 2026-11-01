"""Build recycling.json: recycling drop-off points in British Columbia, from OpenStreetMap.

    python3 -I gallery/examples/map-recycling-clusters/source/build.py [RAW_DIR]

RAW_DIR (argument, else $RAW_DIR, else ./raw) holds osm-recycling/overpass.json, the answer to recycling.overpassql
(beside this script) from https://overpass-api.de/api/interpreter: every amenity=recycling node, way and relation inside
ISO3166-2=CA-BC, ways and relations at their Overpass `center`. Kept: type, accepted materials, point. A name is kept
only on a recycling centre whose name reads as a public depot (the same rule as map-catchments); containers and
private businesses carry no name. No operator, phone, email, website, contact or address.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]
RAW = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RAW_DIR", "raw"))
PREFIX = {"node": "n", "way": "w", "relation": "r"}
TYPE = {"centre": "centre", "container": "container"}
LABEL = {"centre": "Recycling centre", "container": "Recycling container", "other": "Recycling point"}

PUBLIC_OPERATOR = re.compile(
    r"\b(city|district|regional|metro vancouver|town|village|municipality|township|county|first nation|nation|band|"
    r"government|province|ministry|islands trust|landfill|crd|rdn|rdck|rdco|rdos|rdek|rdkb|rdffg|rdbn|rdks|tnrd|cvrd|csrd|"
    r"slrd|fvrd|prrd|scrd|qrd|rdno|rdmw|rdac)\b",
    re.I,
)
FACILITY_WORDS = re.compile(
    r"\b(transfer (station|site|facility)|land ?fill( site)?|disposal facility|recycling (centre|center|depot|facility)|eco[- ]?depot|"
    r"waste (management|disposal|transfer|site|facility|centre|center)|refuse (site|disposal|station)|"
    r"resource recovery|recycling (and|&) waste|solid waste|dump|garbage)\b",
    re.I,
)
BUSINESS_WORDS = re.compile(r"\b(ltd|inc|corp|services|industries|enterprises|company|co\.|bottles?|return-it|recycle-it|power)\b|['’]s\b", re.I)


def public_name(tags: dict) -> str | None:
    name = tags.get("name")
    if not name or tags.get("brand") or BUSINESS_WORDS.search(name):
        return None
    operator = tags.get("operator")
    if tags.get("operator:type") in ("public", "government") or (operator and PUBLIC_OPERATOR.search(operator)):
        return name
    if operator:
        return None
    return name if FACILITY_WORDS.search(name) else None


def main() -> None:
    answer = json.loads((RAW / "osm-recycling" / "overpass.json").read_text())
    rows = []
    for element in answer["elements"]:
        tags = element["tags"]
        kind = TYPE.get(tags.get("recycling_type"), "other")
        accepts = sorted(key.split(":", 1)[1].replace("_", " ") for key, value in tags.items() if key.startswith("recycling:") and value == "yes")
        p = element if element["type"] == "node" else element["center"]
        untagged = {"value": None, "why": "no recycling:<material>=yes tags in OSM"}
        row = {
            "id": f"osm-{PREFIX[element['type']]}{element['id']}",
            "label": LABEL[kind],
            "type": kind,
            "accepts": accepts or untagged,
            "n_materials": len(accepts) or untagged,
            "location": [round(p["lat"], 5), round(p["lon"], 5)],
        }
        if kind == "centre" and (name := public_name(tags)):
            row["name"] = name
        rows.append(row)
    rows.sort(key=lambda row: row["id"])
    doc = {
        "id": "bc-recycling-points",
        "title": "Recycling drop-off points in British Columbia (OpenStreetMap)",
        "titleProperty": "label",
        "source": f"© OpenStreetMap contributors, ODbL; Overpass API, OSM data as of {answer['osm3s']['timestamp_osm_base']}",
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "label": {"type": "text", "label": "Recycling point"},
            "type": {"type": "text", "label": "Type"},
            "accepts": {"type": "list", "label": "Accepts"},
            "n_materials": {"type": "number", "label": "Materials accepted", "unitText": "materials", "decimals": 0},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "name": {"type": "text", "label": "Depot (public centres only)"},
        },
        "rows": rows,
    }
    out = HERE / "recycling.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"recycling.json: {len(rows)} rows, {sum('name' in r for r in rows)} named, {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
