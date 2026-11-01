# ML experiment tracking

Runs as rows, the way an experiment tracker keeps them: each run's model and parameters (environment, lane, bench
version, round) and its metrics (attempts, successes, compute, success rate). A leaderboard pivot, the metric
against the step per environment, one KPI card per model with its pooled success rate, and the runs table, all from
one `.base` file. Illustrative data: Vibe Tracks' synthetic grasp bench, made-up models.

- **App:** Vibe Tracks
- **Replaces:** Vibe Tracks' hand-rolled Results tab (the Perspective-based runs pivot and its leaderboard) and the
  per-experiment metric charts its tracks draw by hand; the same shape as W&B's or MLflow's runs table and charts.
- **Shows:** `type: pivot` model x environment with the median success rate as bars; a `chart` of success rate by
  round (the step), coloured by model, small multiples per environment, with the 55 % gate as a rule; `type: kpi`
  grouped by model with `summary: Ratio` (Σ successes / Σ attempts, pooled, not a mean of rates), a sparkline per
  model and the gate held or missed; compute vs success sized by attempts; the runs table grouped by model; the
  runs grouped by ISO week (`groupBy: {property: started, by: week}`) and a bar chart of runs per week
  (`x: {field: started, by: week}`).
- **Data:** `runs.json`, written by `source/build.py` from Vibe Tracks' committed fixture
  `runs_table.jsonl` (in its tests/fixtures/kpi/synthetic/, 120 runs). ILLUSTRATIVE: its models and numbers are made up for
  Vibe Tracks' tests; no real run log with per-run metrics is committed in Vibe Tracks or bam_ws. Success rate,
  compute per grasp and picks per minute are derived per run and marked so.
