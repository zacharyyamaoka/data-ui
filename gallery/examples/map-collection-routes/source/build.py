"""Build stops.json and routes.json: SYNTHETIC garbage collection routes for three trucks over real food courts.

    python3 -I gallery/examples/map-collection-routes/source/build.py

The places are real, the routes are not. Stops are the OSM food courts of ../map-food-heatmap/food.json; the depot is
the Vancouver South Transfer Station from ../map-catchments/facilities.json (both OpenStreetMap, ODbL). Everything
else is invented and deterministic:
- trucks: food courts sorted by compass bearing from the depot, starting after the widest empty wedge, cut into three
  runs of near-equal count (angle sweep)
- order: nearest neighbour from the depot, then back to the depot
- times: leave 06:00 (-07:00) on 2026-10-14, 25 km/h straight-line (haversine), 6 min at each stop
- kg: a seeded random pick, 20-180 kg per stop
"""

from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parents[1]
FOOD = HERE.parent / "map-food-heatmap" / "food.json"
FACILITIES = HERE.parent / "map-catchments" / "facilities.json"
DEPOT_ID = "osm-w1207315845"  # Vancouver South Transfer Station
TRUCKS = ["Truck A", "Truck B", "Truck C"]
SPEED_KMH = 25.0
DWELL = dt.timedelta(minutes=6)
START = dt.datetime(2026, 10, 14, 6, 0, tzinfo=dt.timezone(dt.timedelta(hours=-7)))
SEED = 20261014


def km(a: list[float], b: list[float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def bearing(origin: list[float], to: list[float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*origin, *to))
    y = math.sin(lng2 - lng1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lng2 - lng1)
    return math.degrees(math.atan2(y, x)) % 360


def main() -> None:
    courts = [row for row in json.loads(FOOD.read_text())["rows"] if row["kind"] == "food court"]
    if len(courts) < 24:
        raise SystemExit(f"only {len(courts)} food courts; the spec falls back to fast food below 24")
    depot = next(row for row in json.loads(FACILITIES.read_text())["rows"] if row["id"] == DEPOT_ID)
    home = depot["location"]
    rng = random.Random(SEED)
    weights = {row["id"]: rng.randint(20, 180) for row in sorted(courts, key=lambda row: row["id"])}

    swept = sorted(courts, key=lambda row: (bearing(home, row["location"]), row["id"]))
    # Start the sweep after the widest empty wedge, so no truck's run wraps across it.
    angles = [bearing(home, row["location"]) for row in swept]
    gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % 360 for i in range(len(angles))]
    start = (gaps.index(max(gaps)) + 1) % len(swept)
    swept = swept[start:] + swept[:start]
    size, extra = divmod(len(swept), len(TRUCKS))
    groups, at = [], 0
    for i in range(len(TRUCKS)):
        n = size + (1 if i < extra else 0)
        groups.append(swept[at:at + n])
        at += n

    stops, routes = [], []
    for truck, group in zip(TRUCKS, groups):
        key = truck.split()[-1].lower()
        left, here, order = list(group), home, []
        while left:
            nxt = min(left, key=lambda row: (km(here, row["location"]), row["id"]))
            order.append(nxt)
            left.remove(nxt)
            here = nxt["location"]
        clock, here, length = START, home, 0.0
        stops.append({"id": f"truck-{key}-depart", "truck": truck, "seq": 0, "kind": "depot", "stop": "Depot (leave)", "at": clock.isoformat(), "location": home})
        for seq, row in enumerate(order, start=1):
            leg = km(here, row["location"])
            length += leg
            clock += dt.timedelta(hours=leg / SPEED_KMH)
            stops.append({"id": f"truck-{key}-{seq:02d}", "truck": truck, "seq": seq, "kind": "pickup", "stop": f"Stop {seq}",
                          "at": clock.replace(microsecond=0).isoformat(), "location": row["location"], "kg": weights[row["id"]], "osm_id": row["id"]})
            clock += DWELL
            here = row["location"]
        leg = km(here, home)
        length += leg
        clock += dt.timedelta(hours=leg / SPEED_KMH)
        stops.append({"id": f"truck-{key}-return", "truck": truck, "seq": len(order) + 1, "kind": "depot", "stop": "Depot (return)", "at": clock.replace(microsecond=0).isoformat(), "location": home})
        routes.append({
            "id": f"truck-{key}",
            "truck": truck,
            "path": [home] + [row["location"] for row in order] + [home],
            "km": {"value": round(length, 2), "basis": "derived", "note": "sum of straight-line (haversine) legs, depot to depot"},
            "stops": len(order),
            "kg": sum(weights[row["id"]] for row in order),
        })

    common = "synthetic routes over real places: OSM food courts and the Vancouver South Transfer Station (© OpenStreetMap contributors, ODbL)"
    (HERE / "stops.json").write_text(json.dumps({
        "id": "collection-stops",
        "title": "Food-court collection stops, 14 Oct 2026 (synthetic)",
        "titleProperty": "stop",
        "source": common,
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "stop": {"type": "text", "label": "Stop"},
            "truck": {"type": "text", "label": "Truck"},
            "seq": {"type": "number", "label": "Sequence", "decimals": 0},
            "kind": {"type": "text", "label": "Kind"},
            "at": {"type": "date", "label": "Arrives"},
            "location": {"type": "list", "label": "Point (lat, lng)"},
            "kg": {"type": "number", "label": "Collected", "unitText": "kg", "decimals": 0},
            "osm_id": {"type": "text", "label": "OSM id"},
        },
        "rows": stops,
    }, indent=1) + "\n")
    (HERE / "routes.json").write_text(json.dumps({
        "id": "collection-routes",
        "title": "Food-court collection routes, 14 Oct 2026 (synthetic)",
        "titleProperty": "truck",
        "source": common,
        "attribution": {"text": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        "properties": {
            "truck": {"type": "text", "label": "Truck"},
            "path": {"type": "list", "label": "Path (lat, lng)"},
            "km": {"type": "number", "label": "Length (straight-line)", "unitText": "km", "decimals": 1},
            "stops": {"type": "number", "label": "Pickups", "decimals": 0},
            "kg": {"type": "number", "label": "Collected", "unitText": "kg", "decimals": 0},
        },
        "rows": routes,
    }, indent=1) + "\n")
    print(f"stops.json: {len(stops)} rows; routes.json: {len(routes)} rows; " + ", ".join(f"{r['truck']} {r['stops']} stops {r['km']['value']} km" for r in routes))


if __name__ == "__main__":
    main()
