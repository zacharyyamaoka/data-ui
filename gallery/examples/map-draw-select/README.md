# Draw an area, count what's inside

Draw a polygon around any part of Metro Vancouver and the panel says how many food places are inside it and of which kinds, with a button that opens exactly those rows. A catchment sketched by hand: "how much input is within this neighbourhood".

- **App:** Map
- **Replaces:** kepler.gl's polygon filter, or exporting points to a GIS to count them.
- **Shows:** `draw: true` (Terra Draw's polygon mode on MapLibre) with `drawBy: kind`; the count is Turf point-in-polygon, derived; "Open these rows" hands the records to the peek (in a dashboard, a selection).
- **Data:** `../map-food-heatmap/food.json`: 6,933 OpenStreetMap places with amenity restaurant, fast_food, cafe or food_court in the Metro Vancouver box (49.0–49.45 N, 123.3–122.4 W), via the Overpass API on 2026-10-28; names dropped, kind and OSM id kept. © OpenStreetMap contributors, ODbL 1.0.
