# Map data: sources and licences

The 20 `gallery/examples/map-*` cases draw public data. **`LICENSE` (MIT) does not cover these files:** each keeps the licence
named here (docs/THIRD-PARTY-DATA.md lists the rest of the repository's). Checked 2026-10-30 against each licence's own page, and
held there by
`tests/unit/map-data.test.mjs` (every file listed, every case's credit) and `tests/browser/map_credit_checks.py` (the
credit on the map itself). None of this is legal advice.

| Source | Licence | Here | Credit it asks for | Where the credit is |
|---|---|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | rows and points (below), and the basemap's streets, water and places | "© OpenStreetMap" with a link to its copyright page, on or beside the map; share-alike on adapted data | on the map: a data file's `attribution` key (the control never folds); here; each case's README |
| [Protomaps](https://docs.protomaps.com/basemaps/downloads) basemap, build 20261028 | an ODbL Produced Work of OpenStreetMap | `metro-vancouver.pmtiles` | OpenStreetMap's, above | on the map (the tiles' own credit) |
| [ESA WorldCover](https://esa-worldcover.org) via [Daylight](https://daylightmap.org), inside the Protomaps build | CC BY 4.0 | the `landcover` layer of `metro-vancouver.pmtiles` (z0 to z7, 170 features). Carried, never drawn: the style has no such layer, so no map needs the credit, but the file does | "© ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium" | here |
| [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) v5.1.2 | public domain | `packages/views/map/assets/countries-110m.json`, `map-bivariate/provinces.geojson`, province label points, and the Protomaps build's low zooms | none ("Crediting the authors is unnecessary"); given anyway | on the map, case READMEs |
| [Statistics Canada](https://www.statcan.gc.ca/en/reference/licence) tables 38-10-0032-01 (2024) and 17-10-0009-01 (2024-07-01) | Statistics Canada Open Licence, **not** the OGL | `disposal_t`, `population`, and `kg_per_capita` worked out from them, in `map-bivariate/provinces.json` | "Adapted from Statistics Canada, *Disposal of waste, by source*, Table 38-10-0032-01, 2024, and *Population estimates, quarterly*, Table 17-10-0009-01, 2024-07-01. This does not constitute an endorsement by Statistics Canada of this product." | here, `map-bivariate` and `map-bubbles` READMEs |
| [CESI](https://open.canada.ca/en/open-government-licence-canada), Environment and Climate Change Canada, *Solid waste diversion and disposal*, figure 5 | Open Government Licence – Canada | `diversion_2002`, `diversion_2022`, `change_pts` in `map-bivariate/provinces.json` | "Contains information licensed under the Open Government Licence – Canada." | same |
| [BC Ministry of Environment and Parks](https://catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc); GeoBC's legally defined boundaries | [Open Government Licence – British Columbia](https://www2.gov.bc.ca/gov/content/data/policy-standards/open-data/open-government-licence-bc) | `map-bc-disposal/disposal.json`, `districts.geojson` | "Contains information licensed under the Open Government Licence – British Columbia." | READMEs of every case reading them |
| Metro Vancouver, *2024 Solid Waste System Factsheets* and the 2024 ISWRMP Biennial Report (marked draft); City of Vancouver, *2024 Annual Report for the Vancouver Landfill* | **no open licence.** Metro Vancouver's [notice](https://metrovancouver.org/documents/copyright-notice-disclaimer.pdf) allows personal, non-commercial, educational and informational copies, unaltered and attributed, and otherwise the Copyright Act; the City's terms of use keep site content to personal, educational or non-commercial use | single published figures, restated as facts, in `map-annotations/facts.json` and `map-waste-flows/flows.json`. No text, table or page is reproduced | their names | each row's `source` and page; READMEs |
| [Noto Sans](https://github.com/notofonts) Regular, as MapLibre glyph ranges from [protomaps/basemaps-assets](https://github.com/protomaps/basemaps-assets) | SIL Open Font License 1.1, no reserved font name | `packages/views/map/assets/glyphs/` (0-255, 256-511, 8192-8447) | the licence text beside the files | `glyphs/OFL.txt`, shipped beside them in `dist/views/map-glyphs/` |

**OpenStreetMap notice (ODbL 4.3).** Contains information from [OpenStreetMap](https://www.openstreetmap.org), which is made
available here under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/). The files below
marked ODbL are under that licence, whatever the licence of the code around them, and may be used only on its terms: keep
the notice, and share what you adapt from them alike. Their Overpass queries and build scripts are in each case's `source/`.

## File by file

| File | Holds | Licence |
|---|---|---|
| `map-food-heatmap/food.json` | 6,933 food places: kind, point, seats; names dropped | ODbL |
| `map-food-heatmap/metro-vancouver.pmtiles` | the Protomaps extract: Metro Vancouver to z11, BC to z6 | ODbL Produced Work; `landcover` CC BY 4.0 |
| `map-recycling-clusters/recycling.json` | 805 recycling points; names kept only for public centres | ODbL |
| `map-catchments/facilities.json`, `hospitals.json`, `sites.json` | 441 waste facilities and 108 hospitals in BC; names kept only for public infrastructure and hospitals | ODbL |
| `map-collection-routes/stops.json`, `routes.json`, `day.json` | SYNTHETIC trucks, times and weights over 25 OSM food courts and one OSM depot | ODbL (the places); the invented part has no third-party rights |
| `map-waste-flows/flows.json` | 2 published and 15 SYNTHETIC flows between OSM points | ODbL (the points); the figures as above |
| `map-annotations/facts.json` | 7 published figures at OSM points | ODbL (the points); the figures as above |
| `map-bc-disposal/disposal.json`, `districts.geojson` | disposal by regional district, 1990 to 2024, and simplified boundaries | OGL – British Columbia |
| `map-bivariate/provinces.json` | diversion, disposal and population by province | OGL – Canada and Statistics Canada Open Licence, as above |
| `map-bivariate/provinces.geojson` | Natural Earth admin-1 shapes | public domain |
| `map-sorting-line/line.json`, `plan.geojson` | an invented floor plan | written for data-ui, no third-party data |

`flows.json`, `facts.json`, and `stops.json` with `routes.json` and `day.json`, hold fewer than 100 OSM features, which the OSMF's
[Substantial guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Substantial_-_Guideline) treats as not a
substantial extract, so share-alike does not reach the figures and invented rows beside them. They carry the credit anyway.

No case holds non-public data: every source above is a public URL (each case's `source/SOURCES.md` lists it with its
retrieval date), no case reads a customer's or BAM's own records, and `tools/deny-scan.mjs --tree` passes over them. OSM names
of businesses, operators, addresses and contacts are dropped by each build; what is left of a place is what `File by file`
says.
