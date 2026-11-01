# source

The raw source view (`type: source`, docs/CONTRACT.md §24): the dataset behind the views as a plain grid, for
debugging. Zach, 2026-10-26: "almost a plain Excel chart of what the data set is behind it."

What it draws:

- **Every column:** the union of the rows' keys in the order they are first seen, including properties marked
  `hidden`, keys the `properties` block does not declare, `_` keys and `id`. The view's `order` does not pick columns.
  Under each key, its type as the core read it (`input.columns`), or "undeclared"; an `id` the core made up for a
  record that had none is marked "assigned by data-ui".
- **Every value as stored:** strings with their spaces (`white-space: pre`), `""` and `null` written out (muted), an
  absent key an empty cell titled "absent", numbers as `String(v)` (no locale, no rounding, no units), `true` / `false`,
  lists and objects (rich cells too) as compact JSON. No badges, units or links. A value wider than its column ends
  in an ellipsis (a line break: its first line and "…"); the whole value is in the cell's title and in the panel.
- **The info strip:** the data file's URL, the `.base` file's, the format as loaded (runtime shape, Frictionless,
  CSV, TSV, JSONL, bare list, one object), its size in bytes, the rows loaded and the columns; "Only rows in the
  current filter"; Copy and Export CSV (RFC 4180, every column, the rows shown, each value as the grid writes it; the
  file is `<dataset id>.csv`).
- **The source panel:** a row's Source button (or Enter on the row) opens it beside the grid; its left edge drags
  (the core's `makeResizable`, width remembered under `data-ui/panel-width/source:<views id>`, double-click resets);
  ✕ or Escape closes it. It shows the file the dataset's `origin: {url: "sources/{id}.md"}` names for the row
  (fetched on demand, same origin only), else `input.dataset.originOf(row)`: the JSON object as parsed, the JSONL
  line, or the CSV / TSV header and the record's lines verbatim, numbered.

Keys:

| key | values | default |
|---|---|---|
| `rows` | `all` (every row as loaded) \| `filtered` (what the view's filters, search and limit leave) | `all` |

```yaml
views:
  - type: source
    name: Raw source
```

Stock: TanStack Virtual 3.19.7 (`@tanstack/virtual-core`, imported from `@data-ui/core` so the page loads it once),
twice: the rows, and the columns (`horizontal: true`), so only the cells on screen are in the DOM (2,196 rows × 52
columns: about 30 rows × 9 cells). The header keeps every column. The panel's handle is the core's `makeResizable`. Ours: the literal cell text
and the CSV writer (`src/literal.js`, tested in `tests/unit/source.test.mjs`), the info strip and the panel.
