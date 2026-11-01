# Food places as 3D columns

The H3 hexagon counts of Metro Vancouver's food places raised into columns, tilted at 50°: height and colour both say how many places a hexagon holds, so the downtown peninsula and the Richmond strip stand up out of the map. Drag with the right mouse button (or two fingers) to turn it.

- **App:** Map
- **Replaces:** kepler.gl's 3D hexagon layer.
- **Shows:** `{type: hexbin, extrude: {max}}`: MapLibre fill-extrusion, height ∝ count (derived), pitch from the view's `pitch:`.
- **Data:** `../map-food-heatmap/food.json`: 6,933 OpenStreetMap places with amenity restaurant, fast_food, cafe or food_court in the Metro Vancouver box (49.0–49.45 N, 123.3–122.4 W), via the Overpass API on 2026-10-28; names dropped, kind and OSM id kept. © OpenStreetMap contributors, ODbL 1.0.
