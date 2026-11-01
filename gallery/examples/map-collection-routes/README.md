# Three collection routes

A synthetic day of food-court pickups: three trucks leave one transfer station at 06:00, visit their stops in nearest-neighbour order and come back. Each route is a line in its truck's colour with its straight-line length in the legend; each stop is a dot that opens its row.

- **App:** Map
- **Replaces:** a dispatcher's route sheet plus a Google Maps tab per truck.
- **Shows:** `{type: lines, path, color}` for a list-of-points property and `{type: points, filter}` for the stops, from one dataset; lengths derived with Turf.
- **Data:** `day.json` (from `routes.json` and `stops.json` by `source/combine.py`): SYNTHETIC trucks, times and kilograms; the stops are real OpenStreetMap food courts and the depot a real transfer station (© OpenStreetMap contributors, ODbL). Legs are straight lines, not road paths.
