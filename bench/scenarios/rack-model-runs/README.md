# Rack model runs (623 rows: models, runs and terms, 15 views)

The 1-DOF test rack's actuator models: 67 models, 489 runs and 67 term ablations in one file (`kind` = model | run | term), with the leaderboard, pivot and parameters cases' fifteen views in one `.base` (KPI cards, ranked tables with bars and distributions, a line and a bar chart, five pivots, five parameter tables). It exercises the mixed-kind filter path (every view filters to its own kind), pivots with split-by over two properties, grouped and sub-grouped tables with summaries, and rich cells carrying CIs. The scenario opens on `Ranked`, not the base's first view (`Best per actuator`, a KPI view).

- **App:** robotparts
- **Base:** `views.base` (opens on `Ranked`)
- **Rows:** 623

## Provenance

- **From:** ~/data-ui lane/models-views @ a163e1a: gallery/examples/robotparts-models-leaderboard/models.json (views: leaderboard + pivot + parameters cases)
- **sha256 of the data file:** `6df86e2b88bcab6125606cd026d288a7b33bfdc9fa8206493c93fe6640f2a637`
- **Copied:** 2026-10-26
- **Note:** Fitted actuator models on the 1-DOF test rack: model, run and term rows in one file (kind = model | run | term), produced by the models-views lane from robotparts' rack reports.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/rack-model-runs/views.base --data bench/scenarios/rack-model-runs/models.json`
