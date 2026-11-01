# robotparts actuators table (1,149 rows, rich cells)

robotparts.dev's actuator catalog in one `.base`: five tables (two of them grouped, one two levels deep with folding) and two pivots over 1,149 rows. It exercises the table's hot path: rich cells (peak torque and mass carry basis and source), badges, bars and distributions in cells, group summaries, Bases filter expressions, the facet rail, and the record peek. `photos/` is the 150 thumbnails the peek draws (the table itself shows no images).

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 1,149

## Provenance

- **From:** ~/data-ui/gallery/examples/robotparts-actuators/actuators.json @ main 0dbc3d4
- **sha256 of the data file:** `60684a21507c5fcf082c517cb8fc8c7302fd01856bb8229cc5a3df01a803d510`
- **Copied:** 2026-10-26
- **Note:** robotparts.dev's actuator catalog, release 2026.10.25, written by gallery/tools/build_examples.py; peak torque and mass are rich cells.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/robotparts-actuators/views.base --data bench/scenarios/robotparts-actuators/actuators.json`
