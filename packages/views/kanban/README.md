# kanban

Bases' kanban view (Obsidian 1.14). Columns are the values of `groupBy`, in `groupOrder` (a named value with no rows
is still a column); cards are rows, each column virtualised, its count in the header.

- **Bases keys:** `groupBy` (the columns), `groupOrder`, `columnWidth` (200–500, default 280), `image`, `imageFit`,
  `imageAspectRatio` (default 0.5, the image's height ÷ its width), `order` (the first is the card's title, the rest
  its lines), `sort` (the order inside a column), `filters`, `limit`.
- **Drag a column header** onto another column: `host.setView({groupOrder})`, the view's config, always allowed (in
  the URL and presets on a static page; a file host writes it to the `.base` file).
- **Drag a card** onto another column: `host.propose({id, set: {<groupBy property>: <column's value>}})`. The card
  moves only once the host says yes; a refusal shows its reason above the board. A `derived` or `readOnly` group
  property locks the board: cards do not drag, the status line says why, and the host would refuse anyway.
- **Keyboard and touch:** Tab to a card; ↑/↓ and ←/→ move between cards; Alt+←/→ moves the card to the next column;
  M (or the card's ⋯ button, always visible on touch screens, where HTML drag and drop does not run) opens a
  "Move to" menu; Enter opens the peek. On a focused column header, Alt+←/→ reorders the columns.
- **Not built:** `subGroupBy` swimlanes, a card's place inside a column (the column's order is the view's `sort`;
  a drop position would need an order property to write), and auto-scroll while dragging near an edge
  (`@atlaskit/pragmatic-drag-and-drop-auto-scroll` is not installed).

Stock: Pragmatic drag and drop 4.0.0 + hitbox 3.0.0 (Apache-2.0: headless, never moves a DOM node, so every move is
a proposal) and TanStack Virtual 3.19.7 (one list per column, the page's one copy from `@data-ui/core`). Moved from
the views report's demo (`docs/views/demo/views/kanban.mjs`).
