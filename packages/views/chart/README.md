# chart

Any Vega-Lite chart of the view's rows (docs/SPEC.md §8). The view's `chart:` block **is** a Vega-Lite unit or layer
spec minus `data`, `datasets`, `$schema` and `config`; this folder supplies the rest.

- **Keys:** `chart` (Vega-Lite; `mark` or `layer` required), `guides` (`rule {x|y}`, `envelope <property>` with
  `shape: hull | ellipse`, `indexLine {slope, through}`, each with an optional `label`), `hover {image, title, fields}`.
  Bases' `filters`, `sort`, `limit` apply as in every view.
- **What it adds:** each channel's `type` and title (label and unit) from the field schema; Show Me defaults for what
  the view leaves out (a log axis only when the positive values span two decades over the whole data, colour from the
  first small rail facet); colours from `input.tokens` (`range.category` = `--data-series-*`); dot-free field names;
  rows a channel cannot place (no value, or not positive on a log axis) counted out in the status line. Past eight
  values of a nominal colour, the commonest seven keep a colour and the rest read "Other (N)". A dot whose y cell's
  basis is estimate, stand-in, assumed or claimed draws hollow (Vibe Tracks' convention); a line with `point: true`
  is two layers so its points hover.
- **Around the plot:** Encode (mark, x, y with linear / log, colour, size, opacity, shape, small multiples, the hover
  card's fields; each change is `host.setView({chart})`), Rows (the same rows in the table view under the chart),
  the hover card (image resolved against the data file's URL, title, values through `valueHtml`), click to
  `host.open` (an aggregate's bar lists the rows behind it), a ring around the peeked dot.
- **Envelopes:** convex hulls (padded 6 %) or 2-sigma ellipses, in log space on log axes, drawn as a Vega-Lite `line`
  with `interpolate: linear-closed` and a fill: Vega-Lite has no polygon mark, but a closed line fills (Vega 6.4
  writes the path's fill and fill-opacity). Groups under three dots get none, and the status line says so.
- **Speed:** the spec is keyed without its data; a filter or search swaps the named datasets (`view.data(name, rows)`)
  instead of re-embedding. 1,149 rows redraw in about 10 ms (the actuator-charts case measures it).
- **Stock:** vega 6.4.0, vega-lite 6.5.0, vega-embed 7.3.0 (BSD-3-Clause), canvas renderer, in this bundle only
  (about 294 KB gzipped), so a page pays for it when a chart first shows. `el.vegaView` on the view's element is the
  Vega View, for tests.
- **Bare mode:** an element with `data-bare` gets the plot alone (no bar, rows or status); the kpi view uses it for
  its headline's history.
- **`style:` in a dashboard** (docs/peps/0005-dashboard-cards.md §5): `chrome: minimal` (a dashboard's default) drops
  axis domain lines, ticks and gridlines (a faint horizontal grid stays on line charts), puts the legend on top as
  small dots, draws heatmaps as tiles in the first series hue, levels category labels and hides the Encode / Rows bar
  (a dashboard card is a figure, not an editor). A nominal colour whose values `style.palette` names takes the
  palette (`seriesColor`), so "tuned" is one colour on every card. Outside a dashboard (no `style:`) nothing changes.

**Two P2 fixes in the chart's own drawing** (PEP 0010 P2's coverage checks found both; tests/unit/chart-extent.test.mjs):
- *A histogram's empty bins are 0, not missing bars.* A one-series bar histogram (x `bin` by `maxbins`, y a `sum` or a
  `count`) bins through explicit transforms with Vega's own bins (vega-statistics' `bin()` over the drawn values, then
  fixed), imputing 0 in every empty bin from the first to the last. A bar's datum stays Vega-Lite's own
  (`bin_maxbins_<n>_<field>`, `…_end`, `sum_<field>`; never a stack's `…_start` / `…_end`, and an empty bin also carries
  Vega's `_impute`), and the hover card and the click read it through the encoding as written. Its bars have square
  ends: Vega-Lite 6.5 drops a ranged bar's x under any corner radius. A colour split or a line keeps Vega-Lite's own
  binning for now.
- *A min or a max never goes stale after a filter.* Vega 6.4 memoises an aggregate cell's extent under its accessor
  alone, so from a view's second data swap on, a boxplot's whiskers (or a `min` / `max` rule) were read back from the
  memo while its median moved. When the spec aggregates an extent (`extentAggregates`), the fast path empties the
  datasets before it swaps them, so new cells start with fresh stores.

**The kit gaps, 2026-10-29** (the PEP 0010 template lanes found them; tests/unit/kit-gaps.test.mjs,
tests/browser/kit_gaps_checks.py):
- *Every aggregate after a swap, not only an extent.* The root cause is one memo key: vega-transforms' `TupleStore`
  keeps its extent, its quartiles and its bootstrap CI under the field's accessor alone, `values()` clears that key once
  per pulse, and the first statistic recomputed sets it back, so every other statistic of the same field reads its memo
  from before the swap (unchanged on vega main, 2026-10-29). P2's empty-first swap is the right seam; it now covers every
  op that hits it (`freshCells`: median, q1, q3, ci0, ci1, min, max, argmin, argmax, and product, which Vega updates by
  dividing out what leaves, 0 / 0 being NaN) and every composite mark, measured against a fresh view of the same rows
  for every Vega-Lite op, composite mark and transform (`swapData`). Sums, counts, means, windows and bins swap in one
  pulse as before.
- *A time on x follows the clock.* A chart whose x is the clock's time column (a dashboard's `clock.time`, else `t`; a
  number in seconds, never a duration column such as ml-experiments' compute per run) takes its rows' time (or the
  clock's zoom window) as an exact x domain through the signals `dvXmin` / `dvXmax`, reports the span, and draws the
  clock's t as a `[data-playhead]` (`.dv-chart-playhead`); with the time series it keeps a 44 px y gutter (`GUTTER`,
  overlay.js) and the same padding, and both leave off an x label that would run past the plot's end (`labelBound`), so
  a state strip under a time series in a dashboard column lines up with it. Its marks clip to the plot: a zoom puts
  spans outside it, and Vega's autosize fit would otherwise shrink the plot to hold them.
- *Fields a transform makes.* A layered chart's own `transform` runs before its layers (it was dropped), and a field a
  transform makes never drops a row from the drawing (it was read from the rows, where it is not yet).
- *Colours.* A column's `colors` map takes a slot, `muted` or 0, a token or a CSS colour (`mapColor`); a null cell is
  muted, never the hue of its label, and takes no palette slot.

## timeseries (same bundle: one Vega engine per page)

`timeseries: {x, y, series, mark: line|area|step, scale: linear|log|symlog, unit, dash, rules, bands, limits, annotations,
legend: top|none, height}` (PEP 0005 §2b; `limits: {warn: [lo, hi], error: [lo, hi]}` is CONTRACT §35's threshold_band: a
dashed rule per limit in its status tone, the zones beyond it, each device's own when the ends name properties). Several `y` columns are long-formatted to `{x, value, series}`: the series
name is the split value, `"<value> · <column label>"` with several columns, or the column label. Colours are the
palette by name (an explicit Vega scale domain/range), else a stable slot; a series named `target` (or listed in
`dash:` by name, value or column) is dashed and muted. Tremor's look: 1.5 px lines, no points, a faint horizontal grid,
no axis lines or ticks, compact tick numbers, the legend (dots, a dash for dashed) and the unit as HTML above the plot,
a crosshair readout instead of a tooltip. Rules and bands take a `tone` (good, warn, bad, muted, neutral: tokens);
annotations are labelled vertical rules, as written (`{x: 1.61, label: contact}`) or one per row whose x is a time:
`{data: events, x: t, label: label, tone}` reads another dataset of the dashboard (a layer, filtered as a panel on it),
`{x: t, label: event}` the view's own rows (`annotationRows`). Their labels are staggered into up to three rows so
none overlaps another, measured as Vega measures text (`labelRows`); one with no room is read in the crosshair
readout, which lists every mark within 6 px of the pointer. A rule's `y`, or a band's `y` bounds, may name a property instead of a number
(PEP 0010 P2, sim2real gap #6; `@data-ui/core`'s `guidesFrom`): read from the drawn rows per series, one value is a
constant across the data's x (a device's own limit, so it follows the rail's device pick) and a value that changes is
a step line through it; series that draw the same line share it. Those points are Vega's dataset `guides`. Past 3,000 points in the window a series is min/max-decimated per pixel
column for drawing only (the readout reads every sample; the status line says so).

On the clock (x in seconds): `clock.extent` with the data's span; a `[data-playhead]` element moved on every `time`
event through Vega's own x scale and plot offset (padding + origin), never a Vega run; a pointer move sets
`clock.hover`, and every time series draws a `[data-hover]` rule there with each series' nearest value; a horizontal
drag sets `clock.window`, which every time series takes as its x domain (two signals and the window's samples: the
dataflow runs on a window change only, never per tick); a double-click clears it; a click seeks. A date `x` is a plain
time series: no clock, no playhead, no crosshair.

## trajectory

`trajectory: {x, y, series, target, color, tolerance, t, trail}`. Equal aspect: the domains are fitted to the plot
Vega laid out (an axis's width depends on its labels, so it fits again until 1 unit is the same px on both axes,
within 0.2 %). The `target` series is dashed and muted; `tolerance` draws it again behind as a translucent tube 2 ×
tolerance wide in px on that scale. `color` colours the other paths by a numeric column (segments, a sequential scale
from the series-1 to the warn token, its legend on top); start (ring) and end (dot) marks on every path. With a `t`
column (default `t`): a `[data-marker]` per series at the clock's t, interpolated along t, and with `trail: true` each
moving path faint with its part up to t drawn solid (an SVG path redrawn per tick from vertices computed after each
Vega run). With `color`, the coloured path stays whole (the marker still moves).

Pure parts (naming, palette, dash, windowing, decimation, nearest sample, interpolation, equal aspect) are
`src/series.js`, unit-tested with the compilers in tests/unit/timeseries.test.mjs. Browser checks:
gallery/examples/dashboard-cards/checks_chart.py.

## timeseries `interactive: true` (uPlot, a lazy chunk)

The Foxglove/Rerun plot Zach asked for on 2026-10-26 ("the simple chart is fine, but also support a Foxglove/Rerun-style
interactive plot"; "we 100% don't need to build any of these views from scratch"). The same keys and the same series
naming, colours and dash rule as the simple time series (`src/series.js`); `interactive: true` swaps the engine.

| Control (Rerun's "?" list) | Gesture |
|---|---|
| Pan | drag (both axes) |
| Horizontal pan | Shift + wheel |
| Zoom | Ctrl + wheel (Cmd on a Mac; a trackpad pinch) |
| Zoom X-axis / Y-axis | Ctrl + Shift + wheel / Ctrl + Alt + wheel |
| Zoom to selection | right-drag or Shift + drag (x only when the box is under 6 px tall) |
| Move time cursor | click (seeks the dashboard clock) |
| Reset view | double-click (the data's span, y back to auto, clock.window cleared) |
| Hide/show series | click its legend entry |
| Hide/show other series | Alt + click (again: all shown) |

A plain wheel is left to the page (it scrolls, as on every other card). Any pan or zoom turns y's auto-fit off until a
reset (egui_plot's rule, the plot Rerun is built on). The "?" button opens that list as a popover; the maximise button
puts the card in the top layer filling the viewport (no ancestor's overflow or transform can clip it), Esc restores.
On the clock: `[data-playhead]` (Rerun's line and triangle) moves by a transform per tick through uPlot's `valToPos`,
never a redraw; a pointer sets `clock.hover` and every time series draws the rule; the x range *is* `clock.window`
both ways (a pan or zoom writes it once per frame, a window set elsewhere becomes the x range). `el.uplot` is the uPlot
instance and `data-plots` counts the instances made, for tests.

### The choice: uPlot over Vega-Lite's own interaction (measured 2026-10-26)

Headless Chromium (Playwright), 4 series × 10,000 points, 800 × 300 px canvas, on this machine under load (load
average 40-50 on 24 CPUs, so absolute numbers are pessimistic; the ratio is the point). Bench:
`scratchpad/plotbench/bench.js` + `run_bench.py` (not in the repo).

| | Vega-Lite 6.5 (`bind: scales`) | uPlot 1.6.32 |
|---|---|---|
| first draw | 301-377 ms | 18-38 ms |
| one pan redraw (median / p95) | 57.7 / 84.7 ms (the dataflow evaluations a real drag triggers that re-render; 121 of them) | 0.9 / 2.1 ms (`setScale('x')` in `batch`) |
| one wheel-zoom redraw (median / p95) | 64.5 / 94.6 ms | 1.1 / 2.0 ms |
| frame interval during a 60-step drag (median / p95 / max) | 16.7 / 116.6 / 333 ms | 16.7 / 16.8 / 33 ms |
| bytes added to a page that has the chart bundle | 0 (Vega is already in it) | 29.3 KB gzipped (the `chart-plot-*.js` chunk: uPlot 22.7 KB + the card; uPlot's few layout rules are in chart.css) |

On the card itself (3 series × 396 samples, `checks_plot.py`): a pan redraw is 0.6 ms median; a real drag runs at a
16.7 ms median frame.

What Vega-Lite's interaction cannot do here, beyond the 55× redraw cost:
- **Per-axis zoom on modifiers.** One interval selection binds a scale; a second and third `bind: scales` param with
  `encodings: [x]` / `[y]` and their own `zoom` filters compile, but only the last one is bound to the domains
  (vega-lite 6.5 output: `domainRaw: zb["x"]`, `zb["v"]`; `zx` and `zy` are dropped). Ctrl + Shift / Ctrl + Alt cannot
  be declared.
- **Box zoom alongside pan.** `bind: scales` owns the left drag; a box needs a second interval selection plus a signal
  listener that writes the domain back, which is our code on Vega's dataflow either way.
- **Rerun's legend.** `bind: legend` selects (click isolates, Shift + click adds); a click that hides one and an Alt +
  click that isolates are not its semantics.
- **Driving the window from outside.** Setting `grid_x` from outside does not move the domain (it routes through
  `grid_store`), so following `clock.window` means re-embedding or editing the store.

**PEP 0001 §4 (one chart engine per page):** uPlot is the dense-time-series exception, as React Flow is for graphs. It
loads only when a card says `interactive: true`: `manifest.json` has `split: true`, so `import('./plot.js')` is its own
file (`dist/views/chart-plot-<hash>.js`), fetched on first use; a page of simple charts never requests it (checked on
actuator-charts). The split also puts the modules both files share (`series.js`, `overlay.js`, 3 KB) in a
`chart-chunk-<hash>.js` that `chart.js` imports.

Browser checks: gallery/examples/dashboard-cards/checks_plot.py. Pure parts (gestures, pan and zoom on linear, log and
symlog, the legend rule, alignment through `uPlot.join`): `src/plotkit.js`, tests/unit/plot.test.mjs.
