# Garbage per person, by BC regional district

How much garbage each BC regional district sends to disposal per person, 2024, as a choropleth: five quantile classes, the unit and the method in the legend, and districts with no published value hatched rather than drawn as zero. The answer leads: which district disposes the most per person.

- **App:** Map
- **Replaces:** the BC disposal-rate table and the province's static PDF map; a QGIS choropleth.
- **Shows:** `layers: [{type: regions, geometry, key, join, value, classes}]`: rows joined to shapes by key, classes from simple-statistics (quantile, equal or Jenks), labels from the bundled glyphs; the 2024 filter keeps one row per district.
- **Data:** `../map-bc-disposal/disposal.json`: BC Ministry of Environment, *Municipal Solid Waste Disposal* (catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc), kg per person per year as published; years published as 0 t are empty with the reason, never 0. Boundaries `districts.geojson`: BC regional districts (openmaps.gov.bc.ca WFS, ABMS_REGIONAL_DISTRICTS_SP), simplified. Open Government Licence – British Columbia ("Contains information licensed under the Open Government Licence – British Columbia"). Comox Valley and Strathcona share one published row and one shape (map-bc-disposal/source/SOURCES.md).
