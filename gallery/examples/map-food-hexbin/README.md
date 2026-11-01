# Food places per hexagon

The same 6,933 food places binned into Uber's H3 hexagons (resolution 8, about 0.5 km a side) and coloured by count in five quantile classes. Hexagons are equal-area, so a dark one really holds more places; click one to list them.

- **App:** Map
- **Replaces:** deck.gl's H3HexagonLayer in a notebook.
- **Shows:** `{type: hexbin, resolution, value: {summary}}` with h3-js; the count is derived and the legend says so; empty hexagons are not drawn.
- **Data:** `../map-food-heatmap/food.json`: 6,933 OpenStreetMap places with amenity restaurant, fast_food, cafe or food_court in the Metro Vancouver box (49.0–49.45 N, 123.3–122.4 W), via the Overpass API on 2026-10-28; names dropped, kind and OSM id kept. © OpenStreetMap contributors, ODbL 1.0.
