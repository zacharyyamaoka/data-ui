# Vibe Tracks · run explorer

The run is the atomic record; the cards, the chart, the leaderboard, the table, the pivot and the grouped table are
views over that one dataset. A ratio-of-sums KPI per run kind, every run over time, and a leaderboard that is the
track tree's roll-up.

- **App:** Vibe Tracks
- **Replaces:** the Results tab's FINOS Perspective pivot over a track's runs (PEP 0006, `vibetracks~/pivot.js`)
  and the hand-built run lists; Perspective stays only as the million-row escape hatch (SPEC §8.10).
- **Shows:** `type: kpi` in summary mode (`summary: Ratio, per: checks`: Σ passed / Σ checks, never a mean of ratios);
  a chart whose point click selects a track for the whole page; a leaderboard read from the `tracks` dataset's
  `rollup:` (newest run per suite, through child tracks); a panel with three presets as tabs and the full toolbar; a
  rail over two linked datasets (run facets plus the tracks' area); a pass-rate slider with its histogram.
- **Data:** `../vibetracks-dashboard/runs.json` and `tracks.json` (real, from the owner bundle; see that case's README).
- **Skin:** `skin.css`, Vibe Tracks' tokens.

## Layout (round 2)

The four ratio-of-sums KPI tiles (tests is the headline, with its history), then a **Checks passing** gauge (Σ passed /
Σ checks over the runs the rail keeps; a bar, since the arc's fill above one half is drawn the long way today), **Runs
per week** as a line per kind, and **Check runs per track** as a bar list; then every run over time beside the
leaderboard, and the runs panel. Run-kind colours match `../vibetracks-dashboard`.
