# robotparts actuators pivot (1,149 rows, brand x form)

Pivots over robotparts' 1,149 actuators: peak torque max and a count by brand x form, a median with distribution cells, and a median with bars by brand x drivetrain. It exercises the pivot view's aggregation and its per-cell record lists on a wide row set. No photos are copied: nothing here draws one.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 1,149

## Provenance

- **From:** ~/data-ui/gallery/examples/robotparts-actuators/actuators.json @ main 0dbc3d4 (views.base written for the bench, pivots after robotparts-actuators)
- **sha256 of the data file:** `60684a21507c5fcf082c517cb8fc8c7302fd01856bb8229cc5a3df01a803d510`
- **Copied:** 2026-10-26
- **Note:** robotparts' actuators again, opened on pivots (max, count, median with distribution, median with bars).

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/actuator-pivot/views.base --data bench/scenarios/actuator-pivot/actuators.json`
