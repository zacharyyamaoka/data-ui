# list

Bases' list view (Obsidian 1.10): one line per row, the title first, then its properties inline, under group headings.
The phone layout of a table. With `tree:` it is an outline: rows nest under their parent and fold.

```yaml
views:
  - type: list
    name: Recent
    order: [name, date, amount, category]   # the title (the dataset's titleProperty) is always first
    groupBy: { property: category }
    markers: number                           # bullet (default) | number | none
    separator: " · "                          # between inline properties (default ", ")
  - type: list
    name: Outline
    tree: { parent: parent }                  # or { path: path, separator: "." }
    indentProperties: true                    # each property on its own line, with its label
    fold: closed
```

- Keys: Bases' `markers`, `indentProperties`, `separator`, `order`, `sort`, `groupBy`, `limit`, `filters`; data-ui's
  `subGroupBy`, `tree`, `fold`, `display` (`badge`, `image`, `link` per property; everything else is the value with
  its unit and basis mark, `valueHtml`).
- A row opens the host's side peek (`host.open`); a group heading, an outline heading or a chevron folds. Keys: ↑ ↓
  move, Enter opens or folds, → ← unfold and fold. Unfold all / Fold all sit in the status line.
- Stock: TanStack Virtual 3.19.7 from `@data-ui/core` (the page's one copy). The outline is TanStack Table's
  sub-rows: with `tree:` the core nests the rows (`treeRows`, `getSubRows`) into the host's `input.table`, and the list
  folds them with the expanding feature, as the table view does (CONTRACT amendment 2026-10-26 (core pass)).
- `tree:` keys: `{parent: <property holding the parent row's id>}` or `{path: <property holding a dotted path>,
  separator: "."}`. Rows keep the row model's sort among their siblings; a row whose parent is filtered out starts at
  the top level; a parent cycle is cut where it closes; a path's missing ancestors are headings with no row behind
  them (never in `input.rows`). With `groupBy`, a group holds the top of each tree and children follow their parent.
- `manifest.json` `covers: ["Tree / hierarchy"]` (CONTRACT §1, amendment 2026-10-26): the Views page marks the Tree
  row built by this folder. The table view reads the same `tree:` key.
