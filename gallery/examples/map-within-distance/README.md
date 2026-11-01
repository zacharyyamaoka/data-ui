# Hospitals within a distance of a facility

Pick a distance on the slider and every BC hospital turns solid when a landfill, transfer station or recycling centre is within it, hollow when none is. The panel leads with the count; the distance is part of the view, so it sits in the URL and in Save view.

- **App:** Map
- **Replaces:** a one-off "which customers are within X km of a depot" query in a GIS or a spreadsheet of haversines.
- **Shows:** `{type: within, of, count, km}` with a slider that writes the view's `km` through `host.setView`; distances are Turf's straight-line ones, derived.
- **Data:** `../map-catchments/sites.json`: OpenStreetMap waste facilities (amenity=waste_transfer_station, landuse=landfill, recycling centres) and hospitals (amenity=hospital) in British Columbia, via the Overpass API on 2026-10-28, joined by `source/combine.py`; names kept only for public infrastructure and hospitals. © OpenStreetMap contributors, ODbL 1.0. OSM's coverage is what volunteers mapped: a facility missing from OSM is missing here.
