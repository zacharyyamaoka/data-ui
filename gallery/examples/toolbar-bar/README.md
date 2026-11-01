# The bar: data-ui's toolbar

robotparts' 1,149 actuators under `toolbar="bar"`: one row with the view chip (or tabs), the table's own query bar,
the filter control and Display, then the filter pills or the bulk bar. Every variant is an attribute of the element
(docs/CONTRACT.md §15).

- **App:** robotparts
- **Replaces:** the full toolbar's row of words (Layout, Group, Sort, Filter, Properties, Units, ⋯) and the toolbar
  proposals' six mocks (lane/toolbar-proposals @ 4481dfe).
- **Shows:** `views="auto"`, `filters="pills rail"`, `display="panel"`, `selectable`: Bases' view menu in the chip,
  Shopify's query builder with autocomplete, pills that mirror the rail, Notion's resizable View settings panel,
  shift / ctrl-click selection with a bulk bar.
- **Data:** `../robotparts-actuators/actuators.json` (the robotparts-actuators case's file).
