# Brand lineage

Every logo and brand proposal from Brandbook's four brands as one table of rows, drawn as a tree of life: x is the
round, each proposal hangs off the one it came from, a splice's extra parents curve in dashed, robotparts' shipped
logo (R16-02) and its ancestors are the bold trunk, and the lines Zach never picked or liked thin out or fold into
"+N". Click a mark for its record, its round's reply and where its report lives; the rail's brand, status and score filters thin
the tree like any view.

- **App:** design work
- **Replaces:** Brandbook's hand-built phylogeny prototype (`~/brandbook/src/variants/v3-phylogeny/`, React +
  d3-hierarchy over one brand at a time) and the per-round logo galleries it links to.
- **Shows:** `type: lineage` (docs/CONTRACT.md §21): `lineage.parents` as the only source of edges, `x: round_n` as
  the ordinal axis with `xLabel`, image nodes from `thumb`, `focus` and its trunk, `kept: {status: [picked, liked]}`
  with `extinct: collapse` (the robotparts tab) and `extinct: show`, the rectangular and radial layouts, the path panel
  (resizable, remembered, folds), and the relation links in the peek (`parents` is `relation: true`).
- **Data:** `proposals.json` and `thumbs/`, written by `source/make.py` from Brandbook's `src/data/brands.json`
  (read-only; parents per its `src/lib/lineage.ts` rule, every claim's evidence in `tools/lineage-notes.md`). 319
  proposals: robotparts 205 over 18 rounds, ObjectDB 51 over 3, BAM 53 over 4, Jidoka 10. Gaps, as the extraction
  records them: robotparts round 1 and BAM's rounds are unscored ("—" with the reason); the two finals have no HTML
  report; `report_path` is the report's path on Zach's machine as plain text (never a link on the published site).
