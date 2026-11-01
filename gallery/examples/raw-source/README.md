# Raw source: a CSV as it is

The data behind the views as a plain grid, for debugging: every key of every row, each value exactly as stored, and
a row's record as it sits in its file. Here a small CSV carries the values that usually go wrong between a file and
a view, and the table beside it shows the same rows as the kit normally draws them.

- **App:** data-ui
- **Replaces:** opening the data file in a text editor or a spreadsheet to see what a view is really drawing from
  (a spreadsheet re-reads `1.50` as 1.5 and trims spaces; an editor shows a 2,000-row JSON file as one line).
- **Shows:** `type: source` (docs/CONTRACT.md §24): the columns are the union of the rows' keys (the auto-assigned
  `id` and the undeclared `note` and `colour` too), `"  padded  "` with its spaces, `null` for an empty field, `"1.50"`
  kept as text by the schema, the record's two lines for the field with a line break; the info strip (data file,
  `.base`, CSV, bytes, rows, columns), Copy and Export CSV, and the source panel with the header line and the record's
  lines numbered. Then `type: table` over the same rows: the four declared columns, drawn as usual.
- **Data:** `parts.csv` (5 records, CRLF line ends, one quoted field over two lines) and `parts.schema.json` beside it,
  which types `price` as text and declares four of the six columns. Hand-written for this case.
