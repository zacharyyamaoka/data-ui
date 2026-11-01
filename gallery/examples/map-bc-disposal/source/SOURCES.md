# Sources: map-bc-disposal

Rebuild: `node gallery/examples/map-bc-disposal/source/build.mjs <RAW_DIR>` (Node, `@turf/turf` from the repo's
node_modules). `<RAW_DIR>` holds the downloads below, each in its own folder. Retrieved 2026-10-28.

## disposal.json

- **Source:** BC Municipal Solid Waste Disposal Rates (CSV resource `BC_Municipal_Solid_Waste_Disposal`, last modified
  2026-09-01), BC Ministry of Environment and Parks, on the BC Data Catalogue.
- **URLs:**
  - dataset: https://catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc
  - file: https://catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc/resource/d2648733-e484-40f2-b589-48192c16686b/download/bc_municipal_solid_waste_disposal.csv
    (saved as `bc-msw/bc_municipal_solid_waste_disposal.csv`)
- **Licence:** Open Government Licence – British Columbia.
  Attribution: "Contains information licensed under the Open Government Licence – British Columbia."
- **Transformations:**
  - one row per CSV row: 27 reporting units × 35 years (1990–2024) = 945 rows. `id` = `<rd>-<year>`.
  - `rd` = the CSV's `Regional_District` lower-cased, non-alphanumerics to `-` (`Metro-Vancouver` → `metro-vancouver`,
    `qathet` → `qathet`). `district` is the CSV name, except `Metro-Vancouver` is shown as `Metro Vancouver`.
  - `population`, `disposal_t` (`Total_Disposed_Tonnes`), `kg_per_capita` (`Disposal_Rate_kg`) are the published
    values, unchanged and unrounded (some tonnes carry one decimal).
  - `location` = `turf.pointOnFeature` of that unit's simplified polygon in districts.geojson, as `[lat, lng]`,
    5 decimals (a label point, not a facility).
  - no BC-total row exists in the file, so there is no `bc-total.json`.
- **Caveats:**
  - **228 rows have no disposal report.** The CSV publishes `0` tonnes for a year with no report: 25–27 of the 27
    units in 1991–1995, 2008, 2009 and 2011; 11 units in 2006; North Coast 2003–2005; Central Coast, Kitimat-Stikine
    and Northern Rockies 2010; Central Coast and Northern Rockies 2012; Central Coast 2024. Those cells are
    `{"value": null, "why": ...}`, never 0. A blank population is `null` with a reason; a 0 or blank rate is `null`.
  - `kg_per_capita` is a disposal rate (lower is better), not a diversion rate.
  - The province's reporting units are not all regional districts: **Comox-Strathcona** reports Comox Valley RD and
    Strathcona RD together, and **Northern Rockies** is a regional municipality.

## districts.geojson

- **Source:** Regional Districts – Legally Defined Administrative Areas of BC (ABMS), and Municipalities – Legally
  Defined Administrative Areas of BC (for Northern Rockies only), GeoBC, via the openmaps WFS.
- **URLs:**
  - https://openmaps.gov.bc.ca/geo/pub/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_REGIONAL_DISTRICTS_SP&outputFormat=application/json&srsName=EPSG:4326
    (saved as `bc-rd/regional_districts.geojson`, 28 features)
  - https://openmaps.gov.bc.ca/geo/pub/wfs?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application/json&srsName=EPSG:4326&typeName=pub:WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP&CQL_FILTER=ADMIN_AREA_NAME%3D'Northern%20Rockies%20Regional%20Municipality'
    (saved as `bc-northern-rockies/northern_rockies.geojson`, 1 feature)
- **Licence:** Open Government Licence – British Columbia (attribution line as above).
- **Transformations:** Comox Valley RD and Strathcona RD dissolved with `turf.union`; every polygon simplified with
  `turf.simplify` (tolerance 0.003°, `highQuality: true`; not topology-preserving, so neighbouring borders can show
  hairline gaps or overlaps); coordinates rounded to 4 decimals. Properties: `rd` (same key as disposal.json),
  `name`. 28 features.
- **Name mapping (CSV → WFS `ADMIN_AREA_NAME`):** every name needed mapping, since the WFS uses full legal names
  ("Regional District of Nanaimo", "Capital Regional District"). The non-obvious ones:
  - `Metro-Vancouver` → Metro Vancouver Regional District
  - `Columbia-Shuswap` → Columbia Shuswap Regional District (no hyphen in the WFS)
  - `Comox-Strathcona` → Comox Valley Regional District ∪ Strathcona Regional District
  - `Northern Rockies` → Northern Rockies Regional Municipality (municipalities layer, not the RD layer)
  - `qathet` → qathet Regional District (formerly Powell River)
  - the rest: `X` → "Regional District of X" or "X Regional District" (full table in build.mjs `UNITS`).
- **Polygon with no rows:** Stikine Region (Unincorporated), `rd: "stikine"`; it is not a regional district and has
  no disposal rows. Kept so the province is covered; it should render as no data.
- **Rows with no polygon:** none.
