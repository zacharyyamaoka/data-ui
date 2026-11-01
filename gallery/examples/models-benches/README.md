# Models × benches

The rack comparison Zach keeps rebuilding: every friction and drivetrain model of the GIM4305-10 (CAN 14) scored on
the bam-rack/1 suite by its twin's joint-angle error, q RMS. The pivot is models × tests with each cell's median and
spread; two charts put every run, and each model's median, against the twin-grade lines (held-out error at most
1.5 × the 1.08 mrad floor, 1.62 mrad, and at most 2.16 mrad in every motion class). The chart shows the report's
verdict at a glance: M4.ripple with the moteus-c1 driver twin sits at about 1 × the floor on the Oct 23 tapes and
at 8.2 × on the Oct 24 cycle runs, so no model is twin-grade yet.

- **App:** robotparts
- **Replaces:** the hand-built HTML tables and SVG strips of robotparts' models report
  (`lane/datasheet` `docs/proposals/build_models_report_r2.py`: `dist_svg`, the per-test rows, the floor and twin-grade
  lines drawn by hand) and the table lane's `models.html` prototype (`design/tables-2026-10-25/presets/models.base`).
- **Shows:** `type: pivot` (models grouped by family x suite / test, median with its distribution, click a cell for
  its runs); a strip `chart` of every run per model on a log axis, coloured by suite, with the floor and the
  twin-grade line as `guides: rule`; a bar `chart` of each model's median (hover a bar for the rows behind it,
  click to list them); the runs table. Models with no run yet show "—" in the pivot and are counted out of the
  charts, said so in the status line.
- **Data:** `models.json`, written by `source/build.py` from `source/models-runs.json`, the table lane's snapshot
  (robotparts lane/tables @ ab5ba92, from lane/datasheet @ ec9a13c), unchanged.
