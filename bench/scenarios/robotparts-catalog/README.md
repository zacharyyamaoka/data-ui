# robotparts whole parts catalog (2,068 rows: actuators, cameras, power supplies)

The whole robotparts v2 catalog, 2,068 parts across actuators, cameras and power supplies, as one flat table and two grouped tables. It exercises a wide, sparse table (many empty cells in the spec columns), rich cells, a list column (bus) and grouping by a low-cardinality and a mid-cardinality column. The part photos are remote URLs, so there is no cards view: the bench never touches the network. `source/build.py` rebuilds `catalog.json` from robotparts' build output.

- **App:** robotparts
- **Base:** `views.base` (opens on its first view)
- **Rows:** 2,068

## Provenance

- **From:** ~/robotparts/dist/site/v2/catalog.json (robotparts/2 release 2026.10.26.5 @ robotparts c32ab1f), flattened by source/build.py
- **sha256 of the data file:** `9f27be296f3c165fe7b34e12a217e3c723bca41271f11074105dac9b8b9d9f48`
- **Copied:** 2026-10-26
- **Note:** Every part in robotparts' v2 catalog, one slim row each (peak torque, mass and rated power as rich cells); written by this scenario's source/build.py from robotparts' build output.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/robotparts-catalog/views.base --data bench/scenarios/robotparts-catalog/catalog.json`
