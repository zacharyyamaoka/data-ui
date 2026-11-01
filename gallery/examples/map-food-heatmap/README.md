# Where food waste is made: Metro Vancouver

Every restaurant, café, fast-food place and food court OpenStreetMap knows in Metro Vancouver, as a density heatmap over a self-hosted street basemap: where a food-waste sorting robot would sit closest to its input. Zoom past 13 and the heat gives way to the single places.

- **App:** Map
- **Replaces:** a kepler.gl heatmap on a Mapbox basemap (an API key and a tile CDN).
- **Shows:** `{type: heatmap}` (MapLibre's kernel density) and `mapTiles:`, the basemap is `metro-vancouver.pmtiles` (Protomaps' OpenStreetMap basemap, build 20261028, cut to Metro Vancouver to zoom 11 and British Columbia to zoom 6 by `packages/views/map/assets/build_basemap.py`; Protomaps © OpenStreetMap contributors, ODbL), served from this site.
- **Data:** `../map-food-heatmap/food.json`: 6,933 OpenStreetMap places with amenity restaurant, fast_food, cafe or food_court in the Metro Vancouver box (49.0–49.45 N, 123.3–122.4 W), via the Overpass API on 2026-10-28; names dropped, kind and OSM id kept. © OpenStreetMap contributors, ODbL 1.0. Basemap: Protomaps © OpenStreetMap contributors. Its landcover layer, carried and not drawn: © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium, CC BY 4.0 (docs/MAP-DATA.md).
