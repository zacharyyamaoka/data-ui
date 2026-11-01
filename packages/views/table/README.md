# table · pivot

The reference view plugin: copy this folder to start a new view (docs/CONTRACT.md §1).

- `manifest.json`: the types it registers (`table`, `pivot`), its entry, its status and the npm parts it bundles.
- `src/index.js`: `export default class` with `constructor(host, el)`, `update(input)`, `destroy()`, plus the optional
  `css` (its stylesheet, as text; the host adds it once) and `options(view, columns)` (the table's and the pivot's
  settings in the Layout menu).
- `src/table.css`: colours only from the private `--dv-*` tokens.

Stock: TanStack Table 9.3.1 (the host's own grouped, sorted instance, `input.table` / `input.pivot.table`) and
TanStack Virtual 3.19.7, both imported from `@data-ui/core` so the page loads them once. Moved from robotparts
`lane/tables` @ `ab5ba92` (`design/tables-2026-10-25/views/src/views.js`).

`tree: {parent}` or `{path, separator}` nests the rows as an outline (TanStack's sub-rows, built by the core into
`input.table`; CONTRACT amendment 2026-10-26 (core pass)): a parent's chevron folds it (or → ←), a path's missing
ancestors are heading rows, Unfold all / Fold all fold every parent, and the tree's own column is left out of the
columns because the indent shows it. With `groupBy`, a group holds the top of each tree.

```yaml
views:
  - type: table
    name: Outline
    tree: { parent: parent }
    order: [title, state, tests]
```

`display: {p: status}` (CONTRACT §35; sim2real gap #12) draws a status word as a badge, its glyph and its word in the
status vocabulary's tone (✓ pass / ok, ! warn / partial, ✕ fail / error, – not run, ? unknown, ◷ stale); a rank column
whose field has `labels` reads as its words. With `tree:` and a dataset roll-up of `Max` of `rank` it is PEP 0010's
rollup_tree: every node the worst word under it.

**Layout settings (docs/CONTRACT.md §15):** `rowHeight: short | medium | tall | extra` (Bases'), `wrap: true` (cells
wrap instead of ending in an ellipsis; each drawn row is measured, so the virtualised rows stay in place) and
`freeze: 0 | 1 | <property>` (default 1: the first column stays put while the table scrolls sideways; a property
freezes the columns through it, CONTRACT §28). `wrap: [p]` (§28, the column menu's Wrap in view) wraps those columns only,
clamped to the row's lines.

**Selection:** with `selectable` on the element a frozen checkbox column leads. A checkbox click toggles its row,
shift adds the range from the last click; on the row body ctrl/cmd-click toggles and shift-click takes the range
(shift+ctrl/cmd adds it); Space toggles the focused row. The header box selects every filtered row or none. The view
reports each click through `host.select(id, {shift, toggle})`, and repaints `.dv-sel` in its `selected(set)` hook
without a redraw. A pivot's rows are never selectable.

**Editing (docs/CONTRACT.md §37):** on an `editable` page a click on a cell of an editable property edits it in an overlay
(`src/edit.js`): Enter or leaving commits through `host.propose`, Esc cancels, Tab moves on. `display: media` draws words plus images
and videos in one cell; `addRow: true` draws the same cells above the rows, filing through `host.add`.

**The notion table (docs/CONTRACT.md §40):** on an `edit-toggle` page in Edit (`input.editTools`) the header has a menu (name, type, Hide,
Delete, Add a property; `src/index.js` draws `[data-col-menu]`, the core's `toolbar/column-menu.js` is the menu), a paste of a block
fills cells across and down (`_paste`, the core's `planPaste`), Tab stops on a checkbox or a two-way column instead of skipping it, and a
value its column's control cannot hold opens in a text box as written. `display: checkbox` draws a real box on any boolean. Every write
goes through the host; delete, undo and the toast are the core's (`edit-session.js`). A page with `editable` alone draws none of it.

**Property types and the column menu** (CONTRACT §28). A typed property (`.base` `properties.<p>.type`) draws through
the core's `typedHtml` (pills, a status dot, a bar or ring, a check, stars, links, thumbnails, avatars, relations) and
shows its type icon in the header; `src/colmenu.js` is Notion's column-header menu (a header click, or Enter on a
focused header; shift-click still sorts). Its file items (name, icon, Edit property, Change type, Insert, Duplicate,
Delete) call `host.editProperty` and show only on a writable host (`el.editing`); its view items write `filters`, `sort`,
`summaries` (the Calculate footer), `rollup`, `dist` (strip | box | violin), `freeze`, `order` and `wrap`.

```yaml
properties:
  status: { type: status, options: [{ value: Planning, color: blue, group: todo }, { value: Done, color: green, group: done }] }
  completion: { type: percent, decimals: 2, showAs: bar, color: green }
views:
  - type: table
    name: Projects
    order: [name, status, completion]
    freeze: name
    summaries: { completion: Average }
```

**Lines and headers** (the 2026-10-26 header/divider review): every cell draws its own right and bottom divider; the
header is `src/columns.js headerCells` (a label spans down over the levels it lacks, never across the frozen edge); a
numeric cell's slots are only the tracks its column uses (`slotTemplate`), shared with its header, so a header ends
where its numbers end and a distribution's title sits over its strip; `minWidth` holds a column to its content.

**The admin look (CONTRACT §43):** `display: {name: avatar}` draws an initials chip before
the semibold name, coloured by `avatar: {color: <property>, colors: {value: 0-8}}`; `display: {due: date}` writes
"Today", "Apr 10" or "Jul 25, 2023" (core `shortDate`), the stored date in the title; `maxBadges: 2` shows two badges
of a list and "+N", every value in the title; `pageSize: 50` pages a flat table with the "‹ 1–50 ›" pager under the
rows (under `frame="card"` it floats below the card). The gallery case `admin-shopify` uses all four.
