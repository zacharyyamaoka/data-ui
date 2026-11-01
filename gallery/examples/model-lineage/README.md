# Model lineage

The GIM4305-10 actuator model ladder, M0 to M5, as a tree of life: x is the rung, each model hangs off the model it
adds physics to, the c1 soft-friction twin splices in M2's soft friction, the four models with bench runs stay alive
and the five with none fold into "+N". Labels instead of pictures: the same lineage view as the brand case, over
another kind of data.

- **App:** robotparts
- **Replaces:** the ladder drawn in prose in robotparts' models proposal (`docs/proposals/models-2026-10-25.md`, "Rung k
  adds a layer of physics") and the rung column of the models-benches pivot.
- **Shows:** `type: lineage` with label nodes (no `image`), `x: rung` with `xLabel`, a splice, `kept: {status:
  [measured]}` with `extinct: collapse`, the radial layout, and the peek's `parents_why` saying where each edge comes from.
- **Data:** `ladder.json`, written by `source/make.py` from the models-benches case's runs (robotparts lane/datasheet @
  ec9a13c), one row per model variant with its run count and median q RMS. `parents` is authored in `make.py`, each
  edge with the sentence of the models proposal that names it; M5.dcmotor's base is never named, so it has none.
