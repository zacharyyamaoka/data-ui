# Notion table

A simple tracker, partly filled in, to play with: edit it, filter it, add columns, or start a blank table.

- **App:** data-ui
- **Replaces:** a hand-rolled admin table: its own Edit button, undo stack, paste parser, filter dialog and column dialogs.
- **Shows:** `edit-toggle` (opening in Edit, `edit-toggle="edit"`); cells, rows and columns edited by hand; `el.undo`; a pasted block; a column's filter by hand, on
  the one filter and its pills; a table started from nothing (`docs/CONTRACT.md` §40). Measured in `tests/browser/notion_table_checks.py`.
- **Data:** `rows.json`, made up for this case, some cells left blank on purpose. `sheet.js` keeps what is typed in this browser's localStorage; Reset to the sample
  forgets it.
