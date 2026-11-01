# The query bar: tokens, autocomplete and bulk actions

robotparts' 1,149 actuators with the bar's query box in token mode: type `brand:` and it suggests the brands with
their counts, Enter makes the clause a token, and a tick in the rail shows up as a token too, because both edit the one
filter. Shift-click a range of rows, ctrl-click to add one, and Shopify's bulk bar offers Compare, Copy IDs and Export
CSV (docs/CONTRACT.md §15).

- **App:** robotparts
- **Replaces:** Shopify admin's order search (its query builder suggesting properties, operators and values) and its
  bulk bar ("2 selected ▾ · actions · ⋯ · Show all selected"); Obsidian Bases' advanced filter expression.
- **Shows:** `filters="query-tokens rail"`, `views="dropdown"`, `display="popover"`, `selectable`: tokens in the box,
  red underlines for a clause that does not parse, value counts under the current filters, shift / ctrl ranges in the
  table and the gallery, the table's `wrap` and `freeze`, the gallery's `maxColumns`.
- **Data:** `../robotparts-actuators/actuators.json` (the robotparts-actuators case's file).
