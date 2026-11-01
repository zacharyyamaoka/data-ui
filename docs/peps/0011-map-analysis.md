# PEP 0011: the map as an analysis surface

- **Status:** accepted; landed on main 2026-10-30 from `lane/map` through `lane/map-land`. The CONTRACT amendment is §42
  (drafted as §32, which the 3D amendment took first).
- **Asked by:** Zach, daily note 2026-10-28: "build out the map panel to like show locations, highlight regions and
  do much more kinda like analysis there … make like 20 different examples of visualization you can do with the Map?
  and upgrade the map to support them?"
- **Prior decisions this keeps:** MapLibre is the one map engine, with no API key and no paid basemap (Vibe Tracks
  storyboard note, 2026-10-10, which rejected d3-geo, OpenLayers, ECharts, Leaflet and Vega-Lite geoshape); missing data
  never draws as 0; nothing loads from another origin (CONTRACT §1).

## Criteria (weighted, for this kit)

| Criterion | Weight | Why |
|---|---|---|
| Stock part per element, ours only the glue | 25 | Zach's rule: never hand-roll what a library does |
| One declarative key set an agent can write and the checker can check | 20 | the `.base` file is the API (SPEC) |
| Truthful: units, class method, no-data never 0, derived numbers say so | 20 | `feedback_truthful_property_rendering` |
| Works offline / same-origin, light and dark, at 390 px | 15 | CONTRACT §1, §4, the gallery's checks |
| Bundle cost paid only by views that use a feature | 10 | a table page must not pay for H3 |
| Plays with dashboards (cross-filter) without a dashboard change | 10 | §17's `select:` |

## Decision

1. **Layers on MapLibre, not a second engine.** Every analysis is a `layers:` entry that becomes MapLibre sources and
   layers (circle, heatmap, fill, fill-extrusion, line, symbol). deck.gl would add about 1 MB for arcs, hexagons and
   heatmaps that MapLibre already draws; a GeoJSON arc from Turf is enough at the scale of a region.
2. **Analysis from Turf, H3 and simple-statistics, in one pure module** (`analysis.js`, unit-tested in Node): rings,
   Voronoi catchments, nearest and within, point in polygon, arcs, path length, H3 bins, class breaks.
3. **Clicks reuse `host.open(id, {records})`.** A region or hexagon opens its rows; inside a dashboard that same call
   is a `select:` selection, so the map cross-filters charts and KPIs with no dashboard change. Marks come back through
   §39's `selected(set)`, by feature-state, so a pick from the URL or another tab marks a feature as a click does, and a
   row hidden in a cluster or under a heatmap stands on a small mark layer over it (§42 lists every layer).
4. **Basemap: self-hosted PMTiles, bundled countries underneath.** OpenFreeMap is free and keyless, but it is another
   origin (§1, and the browser checks fail any foreign request). A Protomaps extract (4.4 MB for Metro Vancouver to
   z11 and BC to z6) is served from the site; where it has no tiles the bundled Natural Earth countries show.
5. **Non-geographic space by scale, not a second CRS.** A floor plan's metres are drawn near 0°, where one degree is
   111,320 m both ways, so pan, zoom, the scale bar and every layer type work on a sorting line.
6. **The swipe on the slider the compare view already ships.** `@maplibre/maplibre-gl-compare` (2021, CommonJS) needs
   Node's `events` and does not bundle; `img-comparison-slider` with `handle` gives the same divider over two maps.

## Stock-part map

| Element | Before | Off-the-shelf part | Behaviour that must survive |
|---|---|---|---|
| Map engine | MapLibre GL 6.16.0 | unchanged | the parked map adopted across view switches; no other origin |
| Markers | HTML markers, rows at one point counted | unchanged (stock seam) | a view with no `layers:` draws exactly as before |
| Clusters | none | MapLibre GeoJSON `cluster` + `getClusterExpansionZoom` | every row counted once; a click zooms in |
| Heatmap | none | MapLibre `heatmap` layer | single rows reachable past zoom 13 |
| Hexagons | none | `h3-js` 4.5.0 | equal-area bins; counts add up to the rows |
| Class breaks | none | `simple-statistics` 7.12.1 (`quantile`, `equalIntervalBreaks`, `ckmeans`) | the method and unit stated in the legend |
| Regions, 3D | none | MapLibre `fill`, `fill-extrusion`, feature-state | the selected region highlighted |
| Buffers, catchments, nearest, inside, arcs | none | `@turf/turf` 7.4.0 (`circle`, `voronoi`, `distance`, `booleanPointInPolygon`, `bezierSpline`) | straight-line distance said as such |
| Drawing an area | none | Terra Draw 1.37.0 + MapLibre adapter 1.5.0 | the drawn rows open in the peek |
| Swipe | none | `img-comparison-slider` 8.0.7, with a two-line sheet in its shadow root (its overlay took every pointer event right of the divider) | both maps still pan and pick; one camera |
| Basemap | bundled countries | `pmtiles` 4.5.0 + `@protomaps/basemaps` 5.7.2 | countries underneath; tokens colour it |
| Labels | none | MapLibre symbol layers, Noto Sans glyphs (OFL) | Latin, Latin-1 and punctuation ship; other ranges answer empty |
| Legend panel width | none | core `makeResizable` (§11) | drag, remember, double-click reset, fold |
| Credit | MapLibre's compact control, folded at the first drag | MapLibre `AttributionControl` with `compact: false` and `customAttribution` from the data file's `attribution` | OpenStreetMap credited on the map itself, on every map of its data (docs/MAP-DATA.md) |
| Time | none | MapLibre `setFilter`; core's clock when the dashboard declares `clock:` | exact rows in the trail window |
| Ours | | `plan.js` (rows to layers, legend model), token-mixed ramps and the bivariate grid, the panel, camera sync | |

## What this does not do (yet)

Routing on roads (an OSRM or Valhalla engine is a server; routes here are stored paths); drive-time isochrones (rings
are straight-line); a choropleth of time-varying values animated by the clock (playback filters points and lines);
basemaps beyond the one Metro Vancouver extract; labels in scripts outside the shipped glyph ranges; editing
geometry back into the data; a keyboard path to a WebGL feature (markers, callouts and legend entries have one); a pick from
a cluster, which zooms instead.
