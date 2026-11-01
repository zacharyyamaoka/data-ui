# robotparts actuators

Every actuator in robotparts.dev's catalog (1,149 rows, release 2026.10.25) in one `.base` file: seven tables, a cards
gallery of the 150 photographed parts and two pivots over the same rows, with the McMaster rail on the left. Tick a
brand and every view reads the same rows.

- **App:** robotparts
- **Replaces:** robotparts' hand-rolled category table, its Rows view and its left rail (`site.js`), and the table
  lane's prototype page.
- **Shows:** grouping two levels deep with fold and summaries, bars in cells, Bases filter expressions, pivots
  (counts, and a median with its distribution), rich cells (peak torque and mass carry their basis and source),
  the rail's disjunctive counts and readable URL.
- **Data:** `actuators.json`, written by `gallery/tools/build_examples.py` from robotparts' catalog. Mass comes from
  each spec's own unit, so the CubeMars AKE40-6 KV90 reads 140 g (the lane's prototype read 140,000 g). `photo` (hidden)
  names 150 of robotparts' primary photos in `photos/`; the actuator-charts case reads these same rows.
- **Skin:** `skin.css` maps robotparts' own tokens onto `--data-*`, light and dark.
- **How a record opens** (`open:`, docs/CONTRACT.md amendment 2026-10-26 (open modes)): the file's default is
  `open: { mode: side, splitAt: 1100 }`, so a click opens the side peek, docked beside the table when the element is at
  least 1100 px wide, over it when narrower, full screen on a phone; ↑/↓ step through the rows and Back closes it.
  *Expand in place* and the *Gallery* say `open: expand` (a band under the row; the card grows), *Row links* says
  `open: { mode: link, url: url }` (the row is a link to the part's robotparts.dev page). Everywhere the part's name is
  a real link, and a double-click or Enter opens its page.
