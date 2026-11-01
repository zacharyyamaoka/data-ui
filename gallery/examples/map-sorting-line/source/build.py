"""Build line.json and plan.geojson: a SYNTHETIC floor plan of a small sorting line for mixed food-court waste.

    python3 -I gallery/examples/map-sorting-line/source/build.py

Nothing here is measured or published: the building, the layout, every rate, purity and status are invented to be
plausible, and fixed in this file (no randomness), so a rebuild is byte-identical. Coordinates are local metres from
the building's south-west inside corner, x east, y north; they are NOT longitude/latitude.

The building is 40 m x 18 m. Waste is tipped on the infeed floor at the west end, runs east on a 30 m conveyor past four
robot pick cells, each robot dropping into the bin on the south side opposite it (one cell sorts two streams),
what is left falls into the residue bin at the east end, and the baler sits north of the belt.
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[1]
W, H = 40.0, 18.0
BELT_Y, BELT_X0, BELT_X1 = 9.0, 8.0, 38.0


def box(x0: float, y0: float, x1: float, y1: float) -> list[list[list[float]]]:
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def centre(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)]


# id, name, kind, footprint (x0, y0, x1, y1), extra fields
ITEMS = [
    ("infeed", "Infeed tipping floor", "infeed", (0.0, 4.0, 8.0, 14.0), {"status": "running"}),
    ("robot-1", "Robot cell 1", "robot", (11.0, 7.0, 15.0, 11.0), {"picks_per_hour": 2340, "status": "running"}),
    ("robot-2", "Robot cell 2", "robot", (17.0, 7.0, 21.0, 11.0), {"picks_per_hour": 2110, "status": "running"}),
    ("robot-3", "Robot cell 3", "robot", (23.0, 7.0, 27.0, 11.0), {"picks_per_hour": 1860, "status": "fault"}),
    ("robot-4", "Robot cell 4", "robot", (29.0, 7.0, 33.0, 11.0), {"picks_per_hour": 2480, "status": "running"}),
    ("bin-organics", "Bin: organics", "bin", (11.0, 3.0, 13.0, 5.0), {"purity": 91.5, "status": "running"}),
    ("bin-pet", "Bin: PET", "bin", (14.0, 3.0, 16.0, 5.0), {"purity": 95.2, "status": "running"}),
    ("bin-aluminium", "Bin: aluminium", "bin", (17.5, 3.0, 19.5, 5.0), {"purity": 96.8, "status": "running"}),
    ("bin-paper", "Bin: paper", "bin", (23.5, 3.0, 25.5, 5.0), {"purity": 84.1, "status": "idle"}),
    ("bin-film", "Bin: film", "bin", (29.5, 3.0, 31.5, 5.0), {"purity": 82.6, "status": "running"}),
    ("bin-residue", "Bin: residue", "bin", (38.2, 8.0, 39.8, 10.0), {"purity": 88.0, "status": "running"}),
    ("baler", "Baler", "baler", (30.0, 13.0, 36.0, 16.5), {"status": "idle"}),
    ("control-room", "Control room", "room", (0.0, 15.0, 6.0, 18.0), {"status": "running"}),
]


def main() -> None:
    rows = [{"id": "conveyor", "name": "Conveyor", "kind": "conveyor", "xy": [round((BELT_X0 + BELT_X1) / 2, 2), BELT_Y], "status": "running"}]
    features = [
        {"type": "Feature", "properties": {"id": "walls", "kind": "wall", "name": "Building walls"}, "geometry": {"type": "Polygon", "coordinates": box(0.0, 0.0, W, H)}},
        {"type": "Feature", "properties": {"id": "control-room-walls", "kind": "wall", "name": "Control room walls"}, "geometry": {"type": "LineString", "coordinates": [[0.0, 15.0], [6.0, 15.0], [6.0, H]]}},
        {"type": "Feature", "properties": {"id": "door-infeed", "kind": "door", "name": "Truck door"}, "geometry": {"type": "LineString", "coordinates": [[0.0, 6.0], [0.0, 12.0]]}},
        {"type": "Feature", "properties": {"id": "conveyor", "kind": "conveyor", "name": "Conveyor"}, "geometry": {"type": "LineString", "coordinates": [[BELT_X0, BELT_Y], [BELT_X1, BELT_Y]]}},
    ]
    for item_id, name, kind, footprint, extra in ITEMS:
        rows.append({"id": item_id, "name": name, "kind": kind, "xy": centre(*footprint), **extra})
        features.append({"type": "Feature", "properties": {"id": item_id, "kind": kind, "name": name}, "geometry": {"type": "Polygon", "coordinates": box(*footprint)}})
    rows.sort(key=lambda row: (["infeed", "conveyor", "robot", "bin", "baler", "room"].index(row["kind"]), row["id"]))

    line = {
        "id": "sorting-line",
        "title": "Sorting line floor plan (synthetic)",
        "titleProperty": "name",
        "source": "synthetic: invented layout and figures, not a real facility",
        "properties": {
            "name": {"type": "text", "label": "Item"},
            "kind": {"type": "text", "label": "Kind"},
            "xy": {"type": "list", "label": "Position (x, y)", "unitText": "m"},
            "picks_per_hour": {"type": "number", "label": "Picks per hour", "unitText": "picks/h", "decimals": 0},
            "purity": {"type": "number", "label": "Bin purity", "unitText": "%", "decimals": 1},
            "status": {"type": "text", "label": "Status"},
        },
        "rows": rows,
    }
    plan = {
        "type": "FeatureCollection",
        "crs_note": "local metres, x east, y north, origin SW corner",
        "synthetic": True,
        "features": features,
    }
    (HERE / "line.json").write_text(json.dumps(line, indent=1) + "\n")
    (HERE / "plan.geojson").write_text(json.dumps(plan, indent=1) + "\n")
    print(f"line.json: {len(rows)} rows; plan.geojson: {len(features)} features")


if __name__ == "__main__":
    main()
