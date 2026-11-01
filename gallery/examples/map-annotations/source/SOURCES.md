# Sources: map-annotations

Rebuild: `python3 -I gallery/examples/map-annotations/source/build.py <RAW_DIR>` (Python 3 stdlib; `pdftotext` on
PATH re-checks each figure's sentence on its cited PDF page and stops the build if it is missing). Retrieved
2026-10-28.

## facts.json (7 rows)

Every figure is published and was read from the primary PDF (no row is `claimed`). `page` is the PDF's page index,
1-based, not the printed page number.

| id | figure | PDF page | text checked on that page |
|---|---|---|---|
| landfill-disposed | 733,196 t | landfill report p. 3 | "In 2024, 733,196 tonnes of waste were disposed" |
| landfill-cap | 750,000 t/yr | landfill report p. 3 | "authorized to accept up to 750,000 tonnes of MSW for disposal each year" |
| vsts-transferred | 140,013 t | landfill report p. 17 (printed p. 11) | "140,013 tonnes were transferred through the VSTS" |
| wte-processed | 243,169 t | fact sheet p. 8 | "Total Processed (2024): 243,169 tonnes" |
| wte-electricity | 180,000 MWh/yr (approximate) | fact sheet p. 8 | "approximately 180,000 MWh / year" |
| united-boulevard-garbage | 263,736 t | fact sheet p. 3 | "Garbage 188,634 263,736" (customers, tonnes) |
| north-surrey-garbage | 235,338 t | fact sheet p. 4 | "Garbage 143,986 235,338" |

- **Sources:**
  - City of Vancouver, *2024 Annual Report for the Vancouver Landfill* (March 2025),
    https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf. vancouver.ca answered a plain request
    with a Cloudflare block page, so the PDF was read from the Internet Archive's copy of that exact URL:
    https://web.archive.org/web/2026id_/https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf
  - Metro Vancouver, *2024 Metro Vancouver Solid Waste System – Factsheets*,
    https://metrovancouver.org/services/solid-waste/Documents/solid-waste-system-fact-sheet.pdf
  - The Metro Vancouver 2022 waste composition study was not used (not looked up).
- **Licence:** neither PDF has an open licence (docs/MAP-DATA.md gives each one's terms). Only individual published
  figures are restated, as facts, with attribution: "Source: City of Vancouver; Metro Vancouver." No text, table or page
  is copied. `source` on each row is the original URL.
- **Points:** OpenStreetMap (ODbL 1.0, "© OpenStreetMap contributors, ODbL"), from
  `../../map-waste-flows/source/flows.overpassql` (saved as `osm-flows/overpass.json`, OSM data timestamp
  2026-10-28T15:22:21Z), Overpass `center`, `[lat, lng]`, 5 decimals; `osm_id` names the element. The two landfill
  facts share one point, as do the two WTE facts.
- **Caveats:**
  - The landfill's 733,196 t is MSW + bottom ash + demolition material; the report states the 750,000 t cap for
    MSW, so the two are not strictly like for like.
  - Station tonnages are garbage only (not paid or free recycling).
  - One station's row (fact sheet p. 2) is left out: its name is caught by data-ui's public-data deny scan.
