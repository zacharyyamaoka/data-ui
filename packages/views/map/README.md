# map

Rows with coordinates as markers on a world map (Bases' Maps keys, unchanged), and with `layers:` an analysis surface:
clusters, proportional symbols, heatmap, H3 hexagons, choropleth and bivariate regions, flows, routes, service rings,
Voronoi catchments, within-a-distance, callouts, 3D columns; `time:` playback, `multiples:`, `swipe:`, `draw:`; and
`space: local` for a floor plan in metres. The keys and rules are docs/CONTRACT.md §42; the decision is
docs/peps/0011-map-analysis.md; 20 gallery cases (`gallery/examples/map-*`) show each one on public BC/Canada data.
A click opens the row, or lists the rows at a counted point. On a dashboard, with `select:`, a click picks instead: the
marker is marked, wherever the pick came from, and a counted marker asks which row (docs/CONTRACT.md §39).

- **Keys (the Bases Maps plugin's):** `coordinates` (required: `[lat, lng]` or `'lat, lng'`), `markerColor` (a
  property, whose values take series slots from the column's `colors` else `hueOf`; or a colour; or
  `var(--data-series-N)`), `center` (`[lat, lng]`), `defaultZoom`, `minZoom`, `maxZoom`, `filters`. Not yet:
  `markerIcon`, `mapHeight` (the view fills `<data-views>`).
- **Picks (`select: <property>`, and `selected:`, docs/CONTRACT.md §33, §39, §42):** the click is `host.open`, which a dashboard
  turns into a selection, ctrl / cmd adds and takes out, as for any view. Marks arrive through `selected(set)` and
  `input.selected`: `.dv-sel` and `aria-pressed` on a marker, a callout or a legend entry; the `sel` feature-state on a WebGL
  feature; a mark layer (`<id>-m`) over a cluster or a heatmap. A counted marker whose rows hold several values of `select:`
  opens a chooser (MapLibre's `Popup`, `.dv-map-choose`); rows sharing one value are one pick. A cluster zooms and rings have no
  clickable feature (their legend band picks): §42 has the table. With no `select:` nothing here applies.
- **Legend:** a `markerColor` property has one (values, colours, counts, the rows a click away); `legend: off` removes it; a
  marker map with nothing to explain has no panel.
- **Credit:** the data file's `attribution` is drawn beside the basemap's, always open. OSM data must carry it, on the map
  itself: every map case's sources and licences are docs/MAP-DATA.md.
- **Basemap:** `assets/countries-110m.json` (173.8 KB, 54 KB gzipped), Natural Earth 1:110m admin-0 countries
  v5.1.2, public domain: name, ISO code and label point per country, coordinates to 2 decimals. Rebuild it with
  `assets/build_countries.py`. No glyphs, sprites or tiles are fetched.
- **Stock:** `maplibre-gl` 6.16.0 (BSD-3-Clause). Its worker, `maplibre-gl-worker.mjs`, must sit beside the bundle
  in `dist/views/`; `src/index.js` points `setWorkerUrl` there.
- **One map across view switches:** `<data-views>` builds a new view on every switch, and a new MapLibre map cost
  286-409 ms. So `destroy()` parks the map (at most `parking.max` = 1, removed after `parking.ms` = 45 s unused,
  holding no page listener or observer while parked) and the next map view adopts it: table -> map went from a
  median 290 ms to 58 ms to the settled frame (`bench/map_switch.py`). `tests/browser/perf_map_checks.py` proves a
  reused map draws what a fresh one draws and that nothing is left once the element is gone. The chooser closes in
  `destroy()`, so a parked map holds no popup.
- **Layers (§42):** `src/plan.js` turns a view's `layers:` into MapLibre sources and layers plus a legend; `src/analysis.js`
  (pure, `tests/unit/map.test.mjs`) does the geometry with Turf, H3 and simple-statistics. Turf is in the main bundle
  (about 80 KB); h3-js, Terra Draw, the swipe slider and the PMTiles basemap load on first use (`split: true`).
- **Basemap tiles:** `mapTiles: <file>.pmtiles` (same site, relative to the `.base`): Protomaps' OpenStreetMap layers,
  recoloured from tokens, over the bundled countries. `assets/build_basemap.py` cuts an extract from a Protomaps daily
  build by range requests (the Metro Vancouver one: `gallery/examples/map-food-heatmap/metro-vancouver.pmtiles`).
- **Glyphs:** Noto Sans Regular 0-255, 256-511 and 8192-8447 (OFL, `assets/glyphs/`), copied to
  `dist/views/map-glyphs/`; any other range answers empty through the `dvglyphs://` protocol, never a 404.
