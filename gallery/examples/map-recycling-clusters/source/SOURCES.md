# Sources: map-recycling-clusters

Rebuild: `python3 -I gallery/examples/map-recycling-clusters/source/build.py <RAW_DIR>` (Python 3 stdlib). Retrieved
2026-10-28.

## recycling.json (805 rows)

- **Source:** OpenStreetMap, via the Overpass API.
- **URL:** https://overpass-api.de/api/interpreter, POST of `recycling.overpassql` (beside this file): every
  `amenity=recycling` node/way/relation inside the area `ISO3166-2=CA-BC`, `admin_level=4`; `out center tags`.
  Saved as `osm-recycling/overpass.json`; OSM data timestamp 2026-10-28T15:19:18Z. (The first four attempts got
  HTTP 502 "server at capacity"; the fifth, after backoff, succeeded.)
- **Licence:** Open Database License (ODbL) 1.0. Attribution: "© OpenStreetMap contributors, ODbL".
  recycling.json is a derived database of OSM and is itself under the ODbL.
- **Transformations:**
  - `id` = `osm-n|w|r<id>`; `location` = node point or Overpass `center`, `[lat, lng]`, 5 decimals.
  - `type` from `recycling_type`: `centre` (169), `container` (573), anything else or untagged → `other` (63).
    `label` = "Recycling centre" / "Recycling container" / "Recycling point" (the title property).
  - `accepts` = the materials whose `recycling:<material>=yes`, `_` → space ("glass_bottles" → "glass bottles"),
    sorted; `n_materials` = their count. When no material is tagged (457 rows) both are
    `{"value": null, "why": "no recycling:<material>=yes tags in OSM"}`, never an empty list or 0.
  - `name`: only on recycling centres whose name passes the public-depot rule shared with map-catchments
    (`public_name`: a public operator, or a facility-style name with no business marker); 25 rows. Every container,
    every other point and every business (bottle depots, Return-It, scrap dealers) carries no name field.
  - **Dropped:** operator, brand, phone, email, website, contact:*, addr:*, opening hours and every other tag.
- **Caveats:** volunteer-mapped and uneven: dense in cities, sparse in the north. Materials are tagged on fewer than
  half of the points. A centre and its containers can both be mapped and appear as separate points.
