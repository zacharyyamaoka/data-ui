# Vibe Tracks KPIs

Vibe Tracks' KPI section rebuilt from one `.base` file: the headline SPPM card with its run history, the smaller
cards beside it (computation time, grasp success, p95, bench score), filled marks for measured readings and hollow
ones for estimates. The history is a `chart` view (Vega-Lite), so the page has one chart engine.

- **App:** Vibe Tracks
- **Replaces:** Vibe Tracks' hand-rolled KPI section (`vibetracks/home/static/kpi-chart.js`: `<vt-kpi-progress>`,
  the headline and its driver tiles on ECharts, about 2,000 lines) and the tiles of `kpi-panel.js`
  (`VT.ui.kpiTile`, Storybook's `Components/KPI tile`).
- **Shows:** `type: kpi` grouped one card per KPI with `groupOrder` (the first is the headline); the producer's
  number, never recomputed, with its basis badge and "computed from 3 runs"; the delta against the previous reading,
  coloured by which way is better (picks per minute up, computation time down: `compare.better: better` names the
  rows' own `better` column, so each card reads its direction from its newest row); a gap
  where a reading was not taken; "—" with its reason for the bench score; click a card for the readings behind it.
  Two chart presets: SPPM history by model with the 30 picks/min reference line, and every KPI as small multiples.
- **Data:** `kpis.json`, written by `source/build.py` from Vibe Tracks' committed synthetic fixture
  (`storybook/fixtures/synthetic/kpi-doc.syn.json`): made-up models, no real track's figures. The fixture has no
  bench score, so that card says so.
- **Skin:** `skin.css` maps Vibe Tracks' tokens (Claude Desktop's) onto `--data-*`, with its success and danger inks
  as `--data-good` and `--data-bad`.
