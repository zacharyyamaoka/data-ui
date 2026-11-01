# lineage

A tree of life over rows that name their parents: x is an ordinal property (a round, a rung, a generation), each row
hangs from its first parent, every link is one curve (a splice's further parents dashed), the focus row and its every ancestor are the
bold trunk, and lines with no kept descendant either thin to stubs or fold into "+N". Rectangular or radial; pan and
zoom; a mark opens its record in the shared peek, a "+N" lists the rows it stands for; the path panel lists the
trunk, oldest first, and is resizable, remembered and foldable (§11).

- **Keys** (one block, docs/CONTRACT.md §21): `lineage: {parents (required), x, xLabel, image, label, focus, kept:
  {property: [values]}, extinct: show | collapse, layout: rectangular | radial}`. Edges come only from `parents`; no
  edge is inferred. Bases' `filters`, `sort`, `order` (the peek's fields and the search's scope) work as in any view.
- **Bar:** Rectangular | Radial, Show extinct, Focus selection (the peeked mark becomes `focus`), Fit. Each writes the
  view entry through `host.setView`, so it rides in the URL and Save view.
- **Stock:** `d3-hierarchy` 3.1.2 (`cluster`), `d3-shape` 3.2.0 (`linkHorizontal`, `linkRadial`), `d3-zoom` 3.0.0 on
  `d3-selection` 3.0.0, the core's `makeResizable`. Ported from Brandbook's v3-phylogeny
  (`~/brandbook/src/variants/v3-phylogeny/layout.ts`, React): the heaviest child in the middle, alive over any
  parent, folded fans counted by subtree.
- **Files:** `src/layout.js` (pure: rows -> laid-out tree; `tests/unit/lineage.test.mjs`), `src/index.js` (the SVG,
  zoom, bar and panel), `src/lineage.css`.
