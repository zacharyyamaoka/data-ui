# Sources: map-waste-flows

Rebuild: `python3 -I gallery/examples/map-waste-flows/source/build.py <RAW_DIR>` (Python 3 stdlib; `pdftotext` on
PATH to re-check every published figure against its PDF page — the build stops if one is missing). Retrieved
2026-10-28.

## flows.json (17 rows: 2 published, 15 synthetic) — "synthetic split"

The title says "(synthetic split)". Each row says `basis: "published"` or `basis: "synthetic"`.

### Published figures (2024)

| figure | t | source, PDF page |
|---|---|---|
| garbage received, the station on fact sheet p. 2 (rows withheld, see below) | 123,170 | fact sheet p. 2 |
| garbage received, United Boulevard RWC | 263,736 | fact sheet p. 3 |
| garbage received, North Surrey RWC | 235,338 | fact sheet p. 4 |
| garbage received, Central Surrey RWC | 10,327 | fact sheet p. 5 |
| garbage received, Langley RWC | 7,601 | fact sheet p. 6 |
| garbage received, Maple Ridge RWC | 9,435 | fact sheet p. 7 |
| WTE Facility, "Transfer" (garbage arriving from the stations) | 84,196 | fact sheet p. 8 |
| Vancouver Landfill, waste "transferred through Metro Vancouver Recycling and Waste Centers" | 405,722 | landfill report p. 17 (printed p. 11), §5.1 |
| contingency disposal (out-of-region landfills), residential & commercial | 151,539 | biennial report p. 12 (printed p. 11), Table 2 |
| **row** VSTS → Vancouver Landfill, "transferred through the VSTS" | 140,013 | landfill report p. 17, §5.1 |
| **row** WTE Facility → Vancouver Landfill, bottom ash ("receives bottom ash from the regional Waste-To-Energy Facility") | 39,347 | landfill report p. 18 (printed p. 12), §5.1.4; also Table 6, p. 17 |

Sources:
- Metro Vancouver, *2024 Metro Vancouver Solid Waste System – Factsheets* (8 pp.),
  https://metrovancouver.org/services/solid-waste/Documents/solid-waste-system-fact-sheet.pdf
- City of Vancouver, *2024 Annual Report for the Vancouver Landfill* (71 pp., March 2025),
  https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf. A plain request to vancouver.ca got a
  Cloudflare block page, so the PDF was read from the Internet Archive's copy of that exact URL:
  https://web.archive.org/web/2026id_/https://vancouver.ca/files/cov/2024-annual-report-vancouver-landfill.pdf
  (saved as `cov-landfill-wayback/report.pdf`).
- Metro Vancouver, *2024 Integrated Solid Waste and Resource Management Plan Biennial Report* (marked DRAFT,
  73 pp., PDF dated 2026-10-02), https://metrovancouver.org/services/solid-waste/Documents/iswrmp-biennial-report-2024.pdf

Licence: none of these PDFs has an open licence (docs/MAP-DATA.md gives each one's terms). Only individual published
figures are restated, as facts, with attribution: "Source: Metro Vancouver; City of Vancouver." No document text or tables are
reproduced.

### Synthetic rows (15)

**Not published:** how each of the six Metro Vancouver stations splits its garbage between the Vancouver Landfill,
the WTE Facility and the contingency landfills. Invented as follows: each destination's published total is shared
across the six stations in proportion to each station's published garbage tonnes (largest-remainder rounding).
Over all six stations every destination sums exactly to its published total (405,722 / 84,196 / 151,539 t), and
every station sends out 98.7 % of what it received: the three destination totals add to 641,457 t, 8,150 t less
than the stations' 649,607 t (a gap the reports do not explain). The real split is unlikely to be uniform
(small-vehicle stations such as Langley and Maple Ridge may never ship to the WTE Facility). Each synthetic row's
`note` says this.

**One station withheld.** The station on fact sheet p. 2 (123,170 t) keeps its share of the split, so the other
five stations' numbers are unchanged, but its three rows are not written: its name is caught by data-ui's
public-data deny scan. So in flows.json the destination columns sum to the published totals less that station's
share: Vancouver Landfill 328,794 of 405,722 t, WTE Facility 68,232 of 84,196 t, contingency 122,806 of 151,539 t.

### Points

Facility points are OpenStreetMap (ODbL 1.0, "© OpenStreetMap contributors, ODbL"), from `flows.overpassql`
(beside this file; saved as `osm-flows/overpass.json`, OSM data timestamp 2026-10-28T15:22:21Z), `[lat, lng]`,
5 decimals, the Overpass `center` of each way/relation:

| facility | OSM element (as mapped) |
|---|---|
| United Boulevard Recycling and Waste Centre | way 585031799 |
| North Surrey Recycling and Waste Centre | way 448908717 ("Surrey Transfer Station", 192 Street) |
| Central Surrey Recycling and Waste Centre | way 1418179695 |
| Langley Recycling and Waste Centre | way 879884610 (272 Street) |
| Maple Ridge Recycling and Waste Centre | **not mapped** in OSM as a waste facility: `origin` is null with a reason |
| Vancouver South Transfer Station | way 1207315845 |
| Vancouver Landfill | relation 14118449 |
| Metro Vancouver Waste-to-Energy Facility | way 418204624 |
| contingency landfills | **not named** by Metro Vancouver: `destination` is null with a reason |

### Left out

- Direct haul: 143,182 t of garbage went straight to the WTE Facility by collection truck (fact sheet p. 8), and the
  landfill received direct-hauled loads too; their origins are not facilities, so they are not rows.
- Non-garbage streams at the landfill (demolition material, C&D residuals, soil, residuals from liquid waste
  treatment) other than the WTE bottom ash.
