# robotparts actuator charts (1,149 rows, Ashby scatter)

Six Ashby-style charts over robotparts' 1,149 actuators (log-log scatter, hulls and an index line, a size-encoded scatter, a faceted scatter, a median bar) and a rows table; the rail filters every chart, and hover cards draw `photos/`. It exercises the chart view's scale, guide and hover paths over a thousand points.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 1,149

## Provenance

- **From:** ~/data-ui/gallery/examples/actuator-charts/views.base @ main 0dbc3d4 + ~/data-ui/gallery/examples/robotparts-actuators/actuators.json @ main 0dbc3d4
- **sha256 of the data file:** `60684a21507c5fcf082c517cb8fc8c7302fd01856bb8229cc5a3df01a803d510`
- **Copied:** 2026-10-26
- **Note:** Ashby-style Vega-Lite charts over robotparts' actuators; same rows as robotparts-actuators, photos feed the hover.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/actuator-charts/views.base --data bench/scenarios/actuator-charts/actuators.json`
