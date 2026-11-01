# Vibe Tracks KPI readings (161 rows, KPI cards and history charts)

Vibe Tracks' KPI section: one row per KPI reading from its synthetic grasp bench, drawn as headline cards with sparklines and deltas, two history charts (a line with points, and a faceted line) and a grouped readings table. It exercises the KPI view and line charts over rich cells that carry a CI, basis and source.

- **App:** vibetracks
- **Base:** `views.base` (opens on its first view)
- **Rows:** 161

## Provenance

- **From:** ~/data-ui/gallery/examples/vibetracks-kpis/kpis.json @ main 0dbc3d4
- **sha256 of the data file:** `6936abc0fe89251cef38a457805c36a28a0ba9e7a4a8aacba75f0ec3e75832e6`
- **Copied:** 2026-10-26
- **Note:** Vibe Tracks' KPI section: one row per reading from its synthetic grasp bench (committed fixture); values are rich cells with CI.

A frozen copy: the gallery or the source app may change, this folder does not. Check it from the worktree root:
`node bin/data-ui.mjs check bench/scenarios/vibetracks-kpis/views.base --data bench/scenarios/vibetracks-kpis/kpis.json`
