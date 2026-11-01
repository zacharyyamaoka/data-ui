# Feedback sheet

One dataset and one `.base` file as a compact, editable sheet: click a cell to edit it, type in the row at the top to add
one, paste or drop a picture into a cell, drag a header to reorder and its edge to resize, and switch between views in
one click. Every change comes back on reload.

- **App:** data-ui
- **Replaces:** the hand-rolled editable `<table>` a page writes when the kit's table cannot edit a cell (Vibe Tracks' Feedback
  tab, PEP 0018).
- **Shows:** inline cell editing on an `editable` page (Enter or leaving commits through `host.propose`, Esc cancels, Tab
  moves on; `readOnly` stays locked); `display: media` (words plus images and videos in one cell, a thumbnail opens large);
  `addRow` and the page's `acceptAdd` and `acceptFile` hooks; `cycle: true` (a two-way column flips on a click); `persist="local"`
  (`docs/CONTRACT.md` §37); `sharedColumns` and `view-counts`.
- **Data:** `rows.json`, made up for this case; the page's `acceptFile` (`sheet.js`) keeps a file as a blob: URL in the page.
