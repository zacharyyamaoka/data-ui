# Sources: map-bivariate

Rebuild: `node gallery/examples/map-bivariate/source/build.mjs <RAW_DIR>` (Node, `@turf/turf` from the repo's
node_modules, `unzip` on PATH). `<RAW_DIR>` holds the downloads below, each in its own folder. Retrieved 2026-10-28.

## provinces.geojson

- **Source:** Natural Earth 1:50m Cultural Vectors, Admin 1 – States, Provinces, v5.1.2.
- **URL:** https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/ne_50m_admin_1_states_provinces.geojson
  (saved as `ne-admin1/ne_50m_admin_1_states_provinces.geojson`)
- **Licence:** public domain. Attribution (courtesy, not required): "Made with Natural Earth."
- **Transformations:** features with `adm0_a3 = CAN` (13); `turf.simplify` (tolerance 0.02°, `highQuality: true`;
  not topology-preserving); coordinates rounded to 4 decimals. Properties: `code` (Natural Earth `postal`), `name`
  (English name as used in provinces.json, e.g. `Quebec` for Natural Earth's `Québec`).

## provinces.json (13 rows)

| field | source |
|---|---|
| `code`, `province` | Natural Earth `postal`; English name |
| `diversion_2002`, `diversion_2022` (%) | ECCC, Canadian Environmental Sustainability Indicators, *Solid waste diversion and disposal*, figure 5 "Solid waste diversion rate from all sources by jurisdiction, Canada, 2002 and 2022": https://www.canada.ca/content/dam/eccc/documents/csv/cesindicators/solid-waste/2024-nov/figure-5-en.csv (saved as `cesi/figure-5-en.csv`; byte-identical to the copy cached on 2026-10-10). Indicator page: https://www.canada.ca/en/environment-climate-change/services/environmental-indicators/solid-waste-diversion-disposal.html |
| `change_pts` | derived: `diversion_2022 − diversion_2002`, percentage points, 1 decimal; null when either is suppressed |
| `disposal_t` (t), `disposal_year` | Statistics Canada, Table 38-10-0032-01 *Disposal of waste, by source*, "All sources of waste for disposal", latest reference year in the table (2024): https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3810003201 ; full-table CSV https://www150.statcan.gc.ca/n1/tbl/csv/38100032-eng.zip (saved as `statcan-disposal/38100032-eng.zip`). |
| `population` (persons) | Statistics Canada, Table 17-10-0009-01 *Population estimates, quarterly*, reference date 2024-07-01: https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710000901 ; full-table CSV https://www150.statcan.gc.ca/n1/tbl/csv/17100009-eng.zip (saved as `statcan-pop/17100009-eng.zip`). |
| `kg_per_capita` | derived: `disposal_t / population × 1000`, rounded to whole kg |
| `location` | Natural Earth admin-1 `latitude` / `longitude` (its label point), `[lat, lng]` |

- **Licence (CESI):** Open Government Licence – Canada (its open.canada.ca record, "Solid waste diversion and disposal").
  Attribution: "Contains information licensed under the Open Government Licence – Canada."
- **Licence (Statistics Canada):** the Statistics Canada Open Licence, https://www.statcan.gc.ca/en/reference/licence, not the OGL.
  `disposal_t` and `population` are the tables' figures and `kg_per_capita` is worked out from them, so the acknowledgement
  is its adapted form: "Adapted from Statistics Canada, *Disposal of waste, by source*, Table 38-10-0032-01, 2024, and
  *Population estimates, quarterly*, Table 17-10-0009-01, 2024-07-01. This does not constitute an endorsement by
  Statistics Canada of this product."
- **Caveats:**
  - **Suppressed:** CESI publishes no diversion rate for Prince Edward Island or the territories in either year
    ("n/a"; CESI note [A]: data not available). Those cells are `{"value": null, "why": "suppressed by Statistics
    Canada"}`, and `change_pts` is null for them.
  - **Territories combined:** Statistics Canada publishes one disposal figure for "Yukon, Northwest Territories and
    Nunavut" (92,006 t in 2024). It is not split: `disposal_t` and `kg_per_capita` are null for YT, NT and NU, and
    the combined figure is quoted in the reason. Population is per territory.
  - **Different years:** diversion is 2002 and 2022 (the only two CESI periods); disposal and population are 2024.
  - CESI's own national total (21.6% → 27.1%) and Statistics Canada's Canada disposal row are not used: no national
    row is in the file.
  - CESI's diversion = diverted / (diverted + disposed); disposal includes landfill and incineration, energy from
    waste included.
