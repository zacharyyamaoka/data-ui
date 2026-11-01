# Sources: map-food-heatmap

Rebuild: `python3 -I gallery/examples/map-food-heatmap/source/build.py <RAW_DIR>` (Python 3 stdlib). Retrieved
2026-10-28.

## food.json

- **Source:** OpenStreetMap, via the Overpass API.
- **URL:** https://overpass-api.de/api/interpreter, POST of `food.overpassql` (beside this file):
  `nwr["amenity"~"^(restaurant|fast_food|cafe|food_court)$"](49.0,-123.3,49.45,-122.4); out center tags;`
  (saved as `osm-food/overpass.json`; OSM data timestamp 2026-10-28T15:09:14Z).
- **Licence:** Open Database License (ODbL) 1.0. Attribution: "© OpenStreetMap contributors, ODbL".
  food.json is a derived database of OSM and is itself under the ODbL.
- **Transformations:**
  - every node, way and relation returned (6,933): ways and relations at the Overpass `center` of their geometry.
  - `id` = `osm-n<id>` / `osm-w<id>` / `osm-r<id>`; `kind` = amenity, readable (`fast_food` → `fast food`,
    `food_court` → `food court`); `location` = `[lat, lng]`, 5 decimals.
  - `seats` = the `capacity` tag when it is an integer; `{"value": null, "why": "not tagged in OSM"}` when absent
    (6,899 rows); null with the raw text as the reason when it is not a number (1 row, "About 14"). Two places tag
    `capacity=0`; it is kept as tagged.
  - **Dropped:** every name, brand, operator, address, phone, website, opening hours and other tag. Only kind,
    OSM id, point and seats remain.
- **Caveats:**
  - The box is a rectangle around Metro Vancouver, not the regional boundary, so places near its edges can sit just
    outside the region (18 rows lie east of 122.47° W, around the Langley–Abbotsford line).
  - OSM coverage is volunteer-mapped and uneven; it is a count of mapped places, not of businesses, and says nothing
    about how much waste each one makes.
  - Counts: 3,589 restaurants, 1,793 fast food, 1,526 cafes, 25 food courts.

## metro-vancouver.pmtiles

- **Source:** the Protomaps basemap, daily build 20261028 (https://build.protomaps.com/20261028.pmtiles, schema v4), cut by
  `packages/views/map/assets/build_basemap.py`: Metro Vancouver to z11, British Columbia to z6. 96 tiles.
- **Licence:** an Open Database License Produced Work of OpenStreetMap, as Protomaps distributes it: "Protomaps ©
  OpenStreetMap" on the map; the view writes "© OpenStreetMap contributors". The build's low zooms use Natural Earth (public
  domain). Its `landcover` layer (z0 to z7, 170 features here) is Daylight's, from ESA WorldCover, CC BY 4.0; the style has no
  layer for it, so it is carried and never drawn, and its credit is in docs/MAP-DATA.md.
