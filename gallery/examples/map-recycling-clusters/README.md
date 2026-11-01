# Recycling drop-offs, clustered

805 recycling drop-off points across British Columbia from OpenStreetMap. At province scale they cluster into counted circles; a click on a cluster zooms into it, a click on a point opens its row. One answer first: how many points, and where they bunch.

- **App:** Map
- **Replaces:** a hand-made Google My Maps of depots, or a kepler.gl cluster layer, for "where can material be dropped off".
- **Shows:** `layers: [{type: points, cluster: true, color: type}]`: MapLibre clustering with counts in the bundled Noto Sans glyphs, colour from a property, legend with counts per value.
- **Data:** `recycling.json`: OpenStreetMap amenity=recycling in British Columbia (Overpass API, 2026-10-28); `accepts` lists the recycling:<material>=yes tags, empty with a reason when none are tagged; names kept only for recycling centres. © OpenStreetMap contributors, ODbL 1.0.
