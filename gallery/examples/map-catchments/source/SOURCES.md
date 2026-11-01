# Sources: map-catchments

Rebuild: `python3 -I gallery/examples/map-catchments/source/build.py <RAW_DIR>` (Python 3 stdlib). Retrieved
2026-10-28.

Both files: **OpenStreetMap via the Overpass API**, https://overpass-api.de/api/interpreter.
**Licence:** Open Database License (ODbL) 1.0. Attribution: "© OpenStreetMap contributors, ODbL". Both files are
derived databases of OSM and are themselves under the ODbL.

`sites.json` is `facilities.json` and `hospitals.json` joined by `combine.py`, with each row's `role`.

## facilities.json (441 rows)

- **Query:** `facilities.overpassql` (beside this file): inside the area `ISO3166-2=CA-BC`, `admin_level=4`, every
  node/way/relation with `amenity=waste_transfer_station`, `landuse=landfill`, or `amenity=recycling` +
  `recycling_type=centre`; `out center tags`. Saved as `osm-facilities/overpass.json`; OSM data timestamp
  2026-10-28T15:10:09Z. `man_made=wastewater_plant` is not queried.
- **Transformations:**
  - `id` = `osm-n|w|r<id>`; `kind` = transfer station (48) / landfill (224) / recycling centre (169), in that order of
    precedence when an element carries two of the tags; `location` = node point or Overpass `center`, `[lat, lng]`,
    5 decimals; `in_metro_vancouver` = inside the box south 49.0, west −123.3, north 49.45, east −122.4 (77 rows).
  - `name`: kept (100 rows) only when it reads as public infrastructure: an `operator` or `operator:type` naming a
    public body (city, district, regional district, First Nation, the province…), or, with no operator, a name that
    names a facility ("… Transfer Station", "… Landfill", "Eco-Depot"…). Withheld, as `{"value": null, "why": ...}`:
    untagged names; business names (a `brand` tag, "Ltd", "Inc", "Services", "Bottle Depot", "Return-It", a
    possessive); privately operated sites; names that are not clearly public. The rule is `public_name` in build.py.
  - **Dropped tags:** operator, phone, email, website, contact:*, addr:*, opening hours, notes, and every other tag.
- **Caveats:**
  - OSM tags `landuse=landfill` on closed and abandoned dumps, compost sites and the odd mis-tag (two sewage
    sites are tagged as a landfill and a recycling centre); it is a map of mapped sites, not a permit register.
  - Some sites are mapped twice (e.g. two overlapping Langley Transfer Station ways) and appear twice.
  - Metro Vancouver's Maple Ridge Recycling and Waste Centre is not mapped as a waste facility in OSM, so it is absent.
  - The public-name rule is a heuristic and errs toward withholding: some sites that may be public lose their name (e.g. a
    landfill whose operator tag is an airport); a few kept names are generic ("Recycling Depot", "The Dump").

## hospitals.json (108 rows)

- **Query:** `hospitals.overpassql`: `amenity=hospital` inside `ISO3166-2=CA-BC`, `out center tags`. Saved as
  `osm-hospitals/overpass.json`; OSM data timestamp 2026-10-28T15:20:19Z.
- **Transformations:** `id` as above; `name` = OSM `name` (5 elements have none: null with a reason); `location` as
  above; `emergency` = the `emergency` tag when `yes` (68) or `no` (8), else null (32 untagged); `beds` = the `beds`
  tag as an integer (10 rows), else null with "not tagged in OSM". No other tag is carried.
- **Caveats:** `amenity=hospital` is whatever mappers tagged: it may include specialty or care sites, and one
  campus can be mapped as several elements. `beds` is volunteer-tagged and sparse (one value, 1,900, looks like a campus total).
