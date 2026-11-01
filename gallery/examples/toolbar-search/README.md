# The bar, Notion's pattern: visible views, folded filters, a search icon

robotparts' part pages put their views (Specs, User data, Config) on the bar as tabs. Zach: "If you have these
quick-switch views visible, then usually the pattern should be to make the filters more hidden (this is the Notion
pattern)." So with no `filters` attribute the bar folds the filters into one Filter button while the views show as tabs,
and spreads them out as Sort · Group · Filter · Properties when `views="auto"` turns the views into the chip; the
search waits behind an icon (`search="icon"`) and grows in place when clicked or on "/".

- **App:** robotparts
- **Replaces:** robotparts' part page header (its Specs / User data / Config tabs over a separate search box and
  filter words).
- **Shows:** `views="auto"` with four views, no `filters` attribute (the default follows the views), `search="icon"`,
  `display="panel"`, `selectable`.
- **Data:** `../robotparts-actuators/actuators.json` (the robotparts-actuators case's file).
