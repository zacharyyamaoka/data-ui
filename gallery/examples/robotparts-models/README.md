# Actuator models · benches, leaderboard, parameters

Every actuator model BAM's rack has scored, one file of configuration: the model × bench pivot first, then the
leaderboard and the parameters, as tabs of one `.base`. Each tab opens with its answer (KPI cards and how to read it),
rolls up across actuators by default (Roll up in the toolbar brings them back), and links every model to its own page.

- **App:** robotparts
- **Replaces:** the hand-built tables of robotparts' models proposal round 2 (lane/datasheet @ ec9a13c,
  `docs/proposals/build_models_report_r2.py`: `compare_table`, `model_rows`, `dist_svg`, the verdict cards), the rack's
  hand-rendered model cards (`model_cards/can<N>.md`), the table lane's `models.base` and Vibe Tracks' Perspective
  results pivot.
- **Shows:** `intro:` (markdown + an inline `type: kpi`) on every tab; `rollup: {keep, dims}` on the pivot and the
  leaderboard (the Roll up menu, a rolled-up row's records on click); `type: pivot` with distribution cells on one
  scale per column (axis in the header); `columnGroups:` over the parameter columns; `display: stats` splitting a term
  into value | 95 % CI low | high | basis and a distribution into median | min | max | n | runs; `display: value`
  (CI on hover); numbers and marks in fixed slots; `open: {mode: side, url: page}` so a model opens in the side peek
  with its README and its page. The rail: actuator, rung, family, bench.
- **Data:** `models.json`, written by `source/build.py` from BAM's rack analysis (`/archive/datasets/bam_rig`: the
  Oct 23 budget and model cards, the Oct 24 dataset and floors, the Oct 25 twin rounds), the twin code's README read
  with `git show` at each fit commit from `~/bam_ws`, and contract 2.3's model kinds from robotparts
  `contract/v2.3`. Real numbers only; models that ran nothing read "—". `source/oracle.py` recomputes the checks'
  expected numbers from the archive.
- **Skin:** robotparts' prototype "Catalog" light and "Signal" dark (lane/colors @ 2b5bf9f) mapped onto `--data-*`.
