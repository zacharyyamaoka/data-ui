# Vibe Tracks · one track

A track's own page as a dashboard. The rail's Track picker is the dashboard variable: change it and the KPI cards,
their history, the check runs and the evidence tables follow, through the links. Opens on Vibe Tracks' own track
(its spec runs: python, storybook, browser, clank).

- **App:** Vibe Tracks
- **Replaces:** the track page's Overview KPI section and its Spec tab's run list (`vibetracks~/track.js`,
  `kpi-panel.js`, the PEP 0012 history view's run list), for reading.
- **Shows:** a `select` facet with `dropdown: true` as Grafana's dashboard variable (the file's `filters:` picks the
  track it opens on); one KPI card per KPI of the picked track with its history; the KPI history as small multiples;
  pass rate per suite over time (click a suite to narrow the runs); a two-tab evidence panel.
- **Data:** `../vibetracks-dashboard/` (real; see that case).
- **Skin:** `skin.css`, Vibe Tracks' tokens.

## Layout (round 2)

The track's row, its KPI tiles, a **Checks passing** gauge (its runs' Σ passed / Σ checks) beside its **Last 30 days**
tracker row (`../vibetracks-dashboard/days.json`, linked to the track), the KPI history as small multiples (each KPI on
its own linear y), pass rate by suite beside **Runs per week** (a line per kind), and the evidence tables. Every card
follows the rail's Track picker.
