# Notion table fixture

Made-up data (`rows.json`: a launch checklist, no real people or tickets) for the Edit / View toggle, deleting rows, undo and
redo, pasting a block and the column menu (docs/CONTRACT.md §40, docs/peps/0016-notion-table.md). `tests/browser/notion_table_checks.py`
reads these files as its oracle; `sourced.json` and `sourced.base` are the same checks' values several sources state. `index.html`
is the page to open by hand, and `page.js` its made-up host: every hook, in this page's memory, no storage of the rows, so a reload
starts over.
