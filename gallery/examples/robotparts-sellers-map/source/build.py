"""Build sellers.json: where robotparts' sellers are based and where they ship. Read-only on robotparts.

    python3 gallery/examples/robotparts-sellers-map/source/build.py

Every price observation robotparts reads (parts/*/quotes.jsonl) records the seller's `seller_country` and the
`ships_to` list the seller published. One row per seller host and country: relation "based in" (seller_country) or
"ships to" (ships_to). A country's point is its Natural Earth label point, from the map view's own basemap
(packages/views/map/assets/countries-110m.json). A country too small for the 1:110m file has no point and says why;
Hong Kong, where the biggest seller is based, has its centre entered by hand and marked `assumed`.
Makers have no country in robotparts (makers.toml records domains only), so none is shown.
"""

from __future__ import annotations

import collections
import json
import pathlib

PARTS = pathlib.Path("~/robotparts/parts")
HERE = pathlib.Path(__file__).resolve().parents[1]
BASEMAP = HERE.parents[2] / "packages" / "views" / "map" / "assets" / "countries-110m.json"
OUT = HERE / "sellers.json"
BY_HAND = {"HK": ("Hong Kong", [22.32, 114.17], "Hong Kong is not a polygon in Natural Earth 1:110m; its centre entered by hand")}


def main() -> None:
    countries = {f["properties"]["iso"]: f["properties"] for f in json.loads(BASEMAP.read_text())["features"]}
    based, ships, listings, names = collections.defaultdict(set), collections.defaultdict(set), collections.Counter(), {}
    for path in sorted(PARTS.glob("*/quotes.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            q = json.loads(line)
            host = q["url"].split("/")[2]
            names.setdefault(host, q["seller"])
            listings[host] += 1
            if q.get("seller_country"):
                based[host].add(q["seller_country"])
            for c in q.get("ships_to") or []:
                ships[host].add(c)

    def point(iso):
        if iso in countries:
            lng, lat = countries[iso]["label"]
            return {"value": [lat, lng], "basis": "derived", "source": "Natural Earth 1:110m label point"}
        if iso in BY_HAND:
            return {"value": BY_HAND[iso][1], "basis": "assumed", "note": BY_HAND[iso][2]}
        return {"value": None, "why": "too small for Natural Earth 1:110m"}

    rows = []
    for relation, table in (("based in", based), ("ships to", ships)):
        for host in sorted(table):
            for iso in sorted(table[host]):
                rows.append({"id": f"{host}-{relation.replace(' ', '-')}-{iso.lower()}", "seller": host, "seller_name": names[host], "relation": relation,
                             "country": iso, "country_name": countries.get(iso, {}).get("name") or (BY_HAND[iso][0] if iso in BY_HAND else iso), "coordinates": point(iso), "listings": listings[host]})
    for host in sorted(set(listings) - set(based)):
        rows.append({"id": f"{host}-based-in-unknown", "seller": host, "seller_name": names[host], "relation": "based in", "country": None,
                     "country_name": None, "coordinates": {"value": None, "why": "the seller's listings publish no seller_country"}, "listings": listings[host]})
    out = {
        "id": "robotparts-sellers", "title": "Sellers by country", "titleProperty": "country_name",
        "source": "robotparts parts/*/quotes.jsonl (seller_country, ships_to) + Natural Earth 1:110m label points",
        "properties": {
            "country_name": {"type": "text", "label": "Country", "width": 180},
            "country": {"type": "text", "label": "ISO code"},
            "relation": {"type": "text", "label": "Relation", "display": "badge", "colors": {"based in": 8, "ships to": 1}},
            "seller": {"type": "text", "label": "Seller", "display": "badge", "colors": {h: i + 1 for i, (h, _n) in enumerate(listings.most_common(8))}},
            "seller_name": {"type": "text", "label": "Seller name"},
            "coordinates": {"type": "list", "label": "Point (lat, lng)"},
            "listings": {"type": "number", "label": "Listings (seller)"},
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    placed = sum(r["coordinates"]["value"] is not None for r in rows)
    print(f"wrote {OUT}: {len(rows)} rows ({placed} with a point), {len(listings)} sellers")


if __name__ == "__main__":
    main()
