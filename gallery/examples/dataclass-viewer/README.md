# Dataclass viewer: a synthetic facility

A synthetic facility's inputs, `DEMO_FACILITY` and the belt and pick move it references (made-up example values,
not real data), as an outline that folds, a sheet per field with its range, basis and source, a form that edits a value inside its range, and the
viewer's Rows table.

- **App:** dataclass viewer
- **Replaces:** the hand-rolled data views of py_dataclass_viewer (`static/app.js` in `~/py_dataclass_viewer`):
  the Outline (`outlineView`, `treeNodes`), the Sheet and the Controls (`controlsView`, `ctlRow`). The viewer keeps
  its file tree, its CodeMirror source and its byte-splice writes; the views over the values are the kit's.
- **Shows:** `type: list` with `tree: {parent}` (an outline; references and nested classes fold),
  `indentProperties`, the same outline as a table (`type: table` with `tree:`), `type: record` with sections (each `Value(...)` as a value, its range, basis mark and source),
  and `edit: true`: a number input bounded by the Value's own `low` / `high`, structural fields read-only. This case's `site.json` makes the page
  `editable`, so a save lands in memory and shows in every view; a read-only host refuses it and says why. In the
  viewer, the host's `acceptEdit` would be its `apply()`. The Rows table carries the same `record.sections` and
  `edit: true`, so a row's side peek is that form too (the viewer's Controls beside its rows).
- **Data:** `facility.json`, 16 rows written by `source/make.py`. Every value, range, source and "measured by" is
  SYNTHETIC: made up for this example and labelled so, in the shape of the viewer's `Value(...)` fields (an instance,
  a referenced belt and pick move, their fields). No real facility or simulation input is published here.
