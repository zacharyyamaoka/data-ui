# Six years side by side

Disposal per person by BC regional district in 2000, 2005, 2010, 2015, 2020 and 2024, as six small maps that share one legend (classes cut over all six years) and one camera: pan one and the others follow. A district that turns lighter disposed less per person.

- **App:** Map
- **Replaces:** an animated GIF you cannot pause, or six separate maps with six different legends.
- **Shows:** `multiples: {by, values, columns}`: one MapLibre map per value, classes computed once over every year so colours compare across panels, cameras synced.
- **Data:** `../map-bc-disposal/disposal.json`: BC Ministry of Environment, *Municipal Solid Waste Disposal* (catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc), kg per person per year as published; years published as 0 t are empty with the reason, never 0. Boundaries `districts.geojson`: BC regional districts (openmaps.gov.bc.ca WFS, ABMS_REGIONAL_DISTRICTS_SP), simplified. Open Government Licence – British Columbia ("Contains information licensed under the Open Government Licence – British Columbia"). Comox Valley and Strathcona share one published row and one shape (map-bc-disposal/source/SOURCES.md).
