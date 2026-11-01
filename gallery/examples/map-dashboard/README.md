# BC garbage per person: map, trend and KPI

A dashboard on one dataset: the 2024 map of disposal per person, the 1990–2024 trend by district, and the province's 2024 total. Click a district on the map and the trend and the KPI narrow to it; the chip above the grid clears it.

- **App:** Map
- **Replaces:** a Power BI page with a shape map, a line chart and a card.
- **Shows:** the map as a dashboard panel with `select: rd`: a region click cross-filters a Vega-Lite chart and a KPI (docs/peps/0004-dashboards.md).
- **Data:** `../map-bc-disposal/disposal.json`: BC Ministry of Environment, *Municipal Solid Waste Disposal* (catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc), kg per person per year as published; years published as 0 t are empty with the reason, never 0. Boundaries `districts.geojson`: BC regional districts (openmaps.gov.bc.ca WFS, ABMS_REGIONAL_DISTRICTS_SP), simplified. Open Government Licence – British Columbia ("Contains information licensed under the Open Government Licence – British Columbia"). Comox Valley and Strathcona share one published row and one shape (map-bc-disposal/source/SOURCES.md).
