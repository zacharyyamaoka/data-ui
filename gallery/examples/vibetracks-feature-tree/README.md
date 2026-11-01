# Vibe Tracks feature tree

Vibe Tracks' own spec: each feature note under its area, the tests that prove it under the feature, and every state
computed from the latest runs (pass, fail, not run yet, no tests), a failure rolling up to the track. An outline that
folds, a "Failing" preset, a table of features by note status, and a page per node.

- **App:** Vibe Tracks
- **Replaces:** the Spec tab's hand-rolled tree in Vibe Tracks, `VT.ui.specTree` in
  `vibetracks/home/static/spec.js` in `~/vibetracks` (story: `SpecTree.stories.js`;
  docs/peps/0007 "the feature tree"). Vibe Tracks keeps computing the tree (`vt spec tree`) and running the suites;
  drawing it, folding it, filtering it and the side peek are the kit's.
- **Shows:** `type: list` with `tree: {parent}` (area -> feature -> test), state badges coloured by slot, a filter
  that keeps a failure's whole path (states roll up, so every ancestor of a failing test is failing too), a grouped
  table and `type: record` over the same rows; the rail filters every view by state, kind and note status.
- **Data:** `spec-tree.json`, 133 rows from four of the track's areas (Sidebar, Home, Review, Track page), written by
  `source/make.py`, which runs Vibe Tracks' read-only `python3 -m vibetracks spec tree` in `~/vibetracks` and
  flattens it. Counts and states are the tree's own; the track row's 1203/1216 covers all of its areas, not only
  these four. Vibe Tracks is a public repo: feature notes and test names, no private track figures.
