# Property types · Notion's table

Notion's "Projects" table rebuilt from one `.base` file: every column says its *type* (Notion's word) and the type's
formatting options, so a status is a dot and its label, a select a coloured pill, a completion a percent with its bar,
a person an avatar, a date in its format. Click any column header for Notion's column menu.

- **App:** data-ui
- **Replaces:** Notion's database properties and their column menu (Zach's screenshots 2026-10-26: the Projects
  template, the "Select type" picker and the header dropdown), and the per-app cell renderers data-ui's hosts would
  otherwise write by hand (robotparts' badge cells, Vibe Tracks' status chips).
- **Shows:** `properties.<p>.type` for every type in Notion's picker (text, number, select, multi-select, status, date,
  person, files & media, checkbox, URL, phone, email) and the advanced ones (rating, currency, percent, duration,
  relation, rollup, ID, edited time), each with its options (number format, show as bar or ring with colour and
  divide-by, option colours, status groups, date format, rating max and icon); the header's type icon; the column
  menu (rename, icon, edit property, change type, filter, sort, calculate, roll up, freeze, hide, wrap, insert,
  duplicate, delete), whose file edits land in the `.base` text because this page is `editable`; the Calculate row;
  an `after:` Markdown block below the views.
- **Data:** `projects.json`, written by `source/build.py`: the four projects of Notion's template screenshot and six
  made-up ones. Public-safe, invented names.
