# Click a district, filter the table

A dashboard: the 2024 disposal-per-person map selects a regional district on click (highlighted in the accent), and the table beside it narrows to that district's every year since 1990. Click it again to clear. The same rows, one selection, two panels.

- **App:** Map
- **Replaces:** a GIS map with a separate spreadsheet you filter by hand.
- **Shows:** a region click goes through `host.open(id, {records})`, which `<data-dashboard>`'s `select: rd` turns into a cross-filter (docs/peps/0004-dashboards.md); the map ignores its own selection and keeps the highlight.
- **Data:** `../map-bc-disposal/disposal.json`: BC Ministry of Environment, *Municipal Solid Waste Disposal* (catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc), kg per person per year as published; years published as 0 t are empty with the reason, never 0. Boundaries `districts.geojson`: BC regional districts (openmaps.gov.bc.ca WFS, ABMS_REGIONAL_DISTRICTS_SP), simplified. Open Government Licence – British Columbia ("Contains information licensed under the Open Government Licence – British Columbia"). Comox Valley and Strathcona share one published row and one shape (map-bc-disposal/source/SOURCES.md).
