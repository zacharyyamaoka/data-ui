# Sources: map-collection-routes

Rebuild: `python3 -I gallery/examples/map-collection-routes/source/build.py` (Python 3 stdlib). Reads two files of
this repo, so build map-food-heatmap and map-catchments first. Built 2026-10-28.

## stops.json (31 rows) and routes.json (3 rows) — SYNTHETIC

Both titles say "synthetic". **The places are real; the trucks, routes, times and weights are invented.**

- **Real inputs:**
  - the 25 OSM food courts (`kind: "food court"`) of `../map-food-heatmap/food.json` — every one is a stop;
  - the depot, Vancouver South Transfer Station, OSM way 1207315845, from `../map-catchments/facilities.json`.
  - Both from OpenStreetMap via the Overpass API (see those folders' SOURCES.md), retrieved 2026-10-28.
    Licence: ODbL 1.0; attribution "© OpenStreetMap contributors, ODbL".
- **Invented, deterministic (no clock or unseeded randomness):**
  - trucks: `Truck A`, `Truck B`, `Truck C`. Food courts are sorted by compass bearing from the depot, the sweep
    starts after the widest empty wedge, and the list is cut into runs of 9, 8 and 8 (angle sweep).
  - order: nearest neighbour from the depot (ties by OSM id), then back to the depot.
  - `at`: leave the depot 2026-10-14T06:00:00-07:00; travel at 25 km/h along straight lines (haversine, mean Earth
    radius 6,371.0088 km); 6 min at each pickup; times to the whole second (fractions dropped). Depot rows are `kind: "depot"` (leave, seq 0;
    return, last seq); pickups `kind: "pickup"`, `stop: "Stop N"` per truck.
  - `kg`: `random.Random(20261014).randint(20, 180)` per food court, drawn in OSM-id order. Depot rows have no kg.
  - stops.json keeps each pickup's `osm_id` so it can be joined back to food.json.
- **routes.json:** `path` = depot, pickups in visiting order, depot (`[lat, lng]`); `km` derived (sum of the
  straight-line legs, rich cell with `basis: "derived"`); `stops` = pickups; `kg` = sum of the invented weights.
- **Caveats:** straight-line distance ignores roads, bridges and water (Truck B crosses to Point Grey; Truck C crosses
  Burrard Inlet), so real driving distances and times would be longer. Food courts stand in for big food-waste
  generators; nothing says who collects them in reality.
