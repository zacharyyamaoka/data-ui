# Each landfill's catchment

Every BC landfill and transfer station gets the area closer to it than to any other (a Voronoi diagram), shaded by how many hospitals fall inside. Click an area for its hospitals. The question it answers: which facility would a hospital's waste go to, if the nearest one took it.

- **App:** Map
- **Replaces:** a nearest-facility analysis in a GIS, kept as a static figure.
- **Shows:** `{type: catchments, of, count}`: Turf voronoi clipped to a padded box; counts derived; classes and units in the legend.
- **Data:** `sites.json`: OpenStreetMap waste facilities (amenity=waste_transfer_station, landuse=landfill, recycling centres) and hospitals (amenity=hospital) in British Columbia, via the Overpass API on 2026-10-28, joined by `source/combine.py`; names kept only for public infrastructure and hospitals. © OpenStreetMap contributors, ODbL 1.0. OSM's coverage is what volunteers mapped: a facility missing from OSM is missing here.
