# Hospitals within 10, 25 and 50 km of a transfer station

Rings of 10, 25 and 50 km around every transfer station OpenStreetMap knows in BC, and how many of the province's hospitals fall in each band of their nearest station. The table under the legend is the answer; click a band for its hospitals.

- **App:** Map
- **Replaces:** a buffer analysis in QGIS exported as a screenshot and a spreadsheet.
- **Shows:** `{type: rings, of, count, km: [10, 25, 50]}`: Turf geodesic circles; each hospital counted once in the smallest ring of its nearest station; straight-line distance, said in the legend.
- **Data:** `../map-catchments/sites.json`: OpenStreetMap waste facilities (amenity=waste_transfer_station, landuse=landfill, recycling centres) and hospitals (amenity=hospital) in British Columbia, via the Overpass API on 2026-10-28, joined by `source/combine.py`; names kept only for public infrastructure and hospitals. © OpenStreetMap contributors, ODbL 1.0. OSM's coverage is what volunteers mapped: a facility missing from OSM is missing here.
