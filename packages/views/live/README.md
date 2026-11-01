# live: the plot and levels cards

The live cards of [PEP 0012](../../../docs/peps/0012-live-data.md) (CONTRACT §26). Both read a live dataset's store
through `input.live` (typed arrays, never a row object per sample) and draw the window ending at the clock's t; both
also draw a plain dataset's rows.

- **`type: plot`**: dense signals over time. uPlot 1.6.32 (MIT), the minimum and maximum of every pixel column in time
  order (`@data-ui/core`'s `alignSeries`), following live at a frame a draw. Keys: `plot: {x, y, series, only, unit,
  dash, rules, bands, legend, height}` and `at:` (default `30s` live, `all` recorded). `[data-playhead]` marks t,
  `data-points` on the view element is the number of x positions drawn. A click seeks, a drag zooms (`clock.window`),
  a double-click un-zooms, hover is the shared crosshair. `series:` names the dataset's stream property (or nothing).
  A rule's `y` or a band's bounds may name a property (PEP 0010 P2, sim2real gap #6; `@data-ui/core`'s `guidesFrom`):
  from the rows the view holds (a live dataset's snapshot at t), a constant across x or a step line where it changes,
  inside the y range; `el.plotView.guides` lists what is drawn. `limits: {warn: [lo, hi], error: [lo, hi]}` (CONTRACT §35,
  threshold_band; `@data-ui/core`'s `limitGuides`): a dashed rule per limit in its status tone and the zones beyond it.
  Its legend is every chart's (CONTRACT §31, the core's `SeriesLegend`): a click hides a series (uPlot's `setSeries`,
  so y rescales to the series shown and a hidden series' rules and limits go too), a double-click or Alt + click
  shows only it, Reset; the hidden set is `l.<panel>=` in a dashboard's URL and `l=` on a `<data-views>`, and a series'
  item menu has Show only and Add to dashboard… (CONTRACT §34; RobotDx PEP 0001 §17.1, 2026-10-29: it was a static key).
- **`type: levels`**: one strip per stream, one bar per time bin, the worst level held in the bin; a bin with no data is
  an empty outline. Keys: `levels: {state, by, label, order, tones, bar}`; the default order and tones are the status
  vocabulary's (CONTRACT §35: the gates' pass, partial, not_run and fail beside RobotDx's levels). `[data-strip]`, `[data-bin][data-level]`,
  `data-t0` / `data-t1` on the view element. Colours: the host tokens `--data-level-ok | warn | error | stale`.
  On a recording (a plain dataset, not live) it shows the whole of it, as its default `at: all` says: the clock's zoom
  window, else its span, else its rows' own (which it reports to the clock), with a `[data-playhead]` at t; the strips
  stand still while t moves (kit gap 4, 2026-10-29: it showed only the 30 s before t). `at: 30s` keeps the window
  ending at t.

Decided 2026-10-27: uPlot for the live time series only; every other chart stays Vega-Lite (bench/live.py measured it).
