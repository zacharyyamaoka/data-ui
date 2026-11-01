# 2000 against 2024: swipe to compare

Disposal per person by regional district in 2000 on the left and 2024 on the right, one map split by a divider you drag. Both sides share classes and a camera, so the colour under the divider is a like-for-like comparison.

- **App:** Map
- **Replaces:** Mapbox's swipe example or two screenshots in a slide.
- **Shows:** `swipe: {left: {filter, label}, right: {filter, label}}` on img-comparison-slider (the compare view's slider) with drag-by-handle, so both maps still pan; one shared class set.
- **Data:** `../map-bc-disposal/disposal.json`: BC Ministry of Environment, *Municipal Solid Waste Disposal* (catalogue.data.gov.bc.ca/dataset/d21ed158-0ac7-4afd-a03b-ce22df0096bc), kg per person per year as published; years published as 0 t are empty with the reason, never 0. Boundaries `districts.geojson`: BC regional districts (openmaps.gov.bc.ca WFS, ABMS_REGIONAL_DISTRICTS_SP), simplified. Open Government Licence – British Columbia ("Contains information licensed under the Open Government Licence – British Columbia"). Comox Valley and Strathcona share one published row and one shape (map-bc-disposal/source/SOURCES.md).
