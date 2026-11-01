# Source columns: what a producer may change, and when

**You don't have to change anything in your data or your `.base` files.** A value's `sources` list keeps working. The kit unfolds it
into plain columns when it reads it. CONTRACT §36 has the detail, PEP 0021 the why.

Worked example throughout: robotparts' datasheet (`nominal.sources`, `sources`, `ladder`, `sourceColumn: true`, one `.base` for 2,103 parts).

## What a reader gets, on the same files

- **Nominal** is now a formula: the first filled source, left to right. Its header has a ƒ, and its hover says what it reads.
- **The agree / differs pill** ("+1 · 1 differs") moved from the Nominal source column onto the Nominal cell. It opens the same menu as a right-click.
- **A Sources tab** replaces Manage sources: that view with one column per source. It is an ordinary view.
- **Hiding a source changes no value.** Dragging one does, because column order is precedence. Alt+← and Alt+→ on a header do the same.

## When you re-vendor this build

These are things your page or tests reach into, not your data. None is needed before you upgrade, and all of them are needed on the day you do.

| What you have | What to do |
|---|---|
| `td[data-col="@source"]` | `td[data-col="nominal@source"]`, or `td[data-col$="@source"]` |
| `th[data-src]`, `td[data-col^="@src:"]` | `th[data-col^="nominal@"]`, without `nominal@source` |
| `[data-bar="sources"]`, `[data-sources]`, `el.manageSources` | `el.selectView('Sources')`, or the tab |
| `[data-src-move]` (‹ ›) | Alt+← / Alt+→ on the header, or `el.setPrecedence({order})` |
| `.dv-src-menu` | `.dv-src-pop` |
| `.dv-src-dd`, `.dv-src-pin` inside the source column | inside `td[data-col="nominal"]` |
| Reading a Nominal cell's text | Leave out `.dv-src-dd` and `.dv-src-pin`: they are in that cell now |
| `tr[data-conflict]` | `button.dv-src-dd[data-conflict]` |
| `columnSize: {'@source': n}`, `record.visibility: {'@source': …}` | `nominal@source`. Old keys are ignored, not an error |

In robotparts that is `site/static/part-overview.js:47`, the one line a reader would feel: `DATASHEET_CELLS` names `'@source'`, so until it says `nominal@source` a
right-click on that column finds no cell. Then `tests/site/datasheet_check.py`, `tests/site/source_precedence_check.py` and `docs/reports/capture_datasheet_report.py`.
`tests/site/test_data_ui.py` and `browser_check.py`, the journey, read none of these, so a green journey says nothing about them.

Old links (`#sources=…&picks=…`) and what a returning reader kept (`data-ui/sources/…`) still work.

## What you may change, any time

Each of these is optional, and each works on its own.

**Name the columns.** A view may place any of them. `nominal@*` is every source of the value, best first, which is how one `.base` serves parts with
different sources. `formula.nominal` and `nominal` are the same column.

**State the precedence in the file.** A `formulas:` entry on a value with `sources` sets its default order, in place of the ladder. The sources it
doesn't name keep their ladder places.

**Move to plain columns.** Write `datasheet`, `citation`, `measured` as ordinary properties and a formula over them. Then there is no `sources` list,
no unfolding and no `ladder`: the file says it all. Do it per dataset, whenever suits.

**Hide the source column in one view:** `sourceColumn: false` on the view. A reader's Hide writes the same key.

**Keep a reader's view per page:** `persist="page"`, below.

### Before and after

Before, and still right:

```yaml
views:
  - type: table
    name: Datasheet
    order: [field, nominal, verdict, measured, board, derived, status, n]
    groupBy: { property: section }
    rowHeight: short
    units: inline
```

After, if you want the file to say all of it:

```yaml
views:
  - type: table
    name: Datasheet
    order: [field, formula.nominal, nominal@source, verdict, measured, board, derived, status, n]
    groupBy: { property: section }
    rowHeight: short
    units: inline
  - type: table
    name: Sources
    order: [field, formula.nominal, nominal@*, verdict, measured, board, derived, status, n]
    groupBy: { property: section }
    rowHeight: short
    units: inline
```

Plain columns, with no `sources` list at all:

```yaml
data: part.json
formulas:
  nominal: '[datasheet, citation, measured].filter(value.isType("boolean") || !value.isEmpty())[0]'
properties:
  formula.nominal:
    displayName: Nominal
views:
  - type: table
    name: Datasheet
    order: [field, formula.nominal, verdict]
  - type: table
    name: Sources
    order: [field, datasheet, citation, measured]
```

## `sourceColumn`

| Dataset says | Now |
|---|---|
| `sourceColumn: true` | As before: a table draws "`<label> source`" after the first value that names a source, on one-source data too. It is `nominal@source` now, an ordinary column: a view can hide it, sort by it, filter on it |
| `sourceColumn: false` | No view gets it unasked. It is still a column a view may name, and the Sources tab still appears |
| Nothing | As before: the column follows a value with several sources only |

A view can also say `sourceColumn: false`, for that view alone.

## `basis: "derived"`

Unchanged. A derived value names what it came from in `nominal@source`, with the quiet word "derived", and "—" stays only where nothing names a source.
The word follows the value shown: pick a stated source and it goes. A cell with no `source`, `sourceUrl` or `sourcePage` still reads "—".

## Editing

A multi-source cell used to refuse every edit. Now:

- **A source's own column edits.** Your `acceptEdit` hears the stored property, whole: `set: {nominal: {sources: […]}}`, the one you already store. It doesn't
  hear `nominal@bench`. The entry's `text` is dropped, because it described the old value.
- **The Nominal cell still refuses,** with the same words.
- **A script may now set a whole new `sources` list.** It used to be refused. A plain value set on such a cell still is.

## Two things found adopting the kit

**`persist="page"`.** `persist="local"` keys on the data id, and your datasheets shared one id across 2,103 pages, so a preset chosen on JMC opened moteus on 0 of
16 rows. `persist="page"` keeps the view, sort and filters per page path and data id, and the widths per data id, so a column you widen stays wide on every part.
Reset forgets both. `persist="local"` is unchanged, and what it stored still reads.

While this was being built you gave each part its own id instead (robotparts `dfaa724`). That fixes the preset and costs the shared widths, and you accepted that
there, at `PART_KEPT`. Nothing needs to change: on a per-part id `persist="page"` gains nothing. To have the widths back, return to one id and use the tag below;
`tests/site/test_data_ui.py` pins the three ids, and what readers saved under the per-part ids is left behind.

```html
<data-views id="datasheet-views" src="/search/views/datasheet.base" data="…/jmc-60asm200-5-1024c.json" persist="page" no-url></data-views>
```

**A header no longer holds a column open.** A column's floor is what it holds. A header's words widen a column nobody has sized, up to 240 px, then end in an
ellipsis, whole on hover. This applies to every column on every table. Robotparts' source columns came out at 156 / 603 / 284 px, and the 603 wouldn't drag narrower.

## In Obsidian

Bases has no coalesce, so the file uses Bases' own list functions. Run in Obsidian 1.12.7:

- `[a, b].filter(!value.isEmpty())[0]` takes the first filled value: 0 wins, `""`, `[]` and a missing value don't.
- That spelling shows `Cannot find function "isEmpty" on type Boolean` when a boolean is in the list. `[a, b].filter(value.isType("boolean") || !value.isEmpty())[0]` doesn't.
- `coalesce(a, b)` and `first(a, b)` show `Cannot find function`. Don't write them.
- `note["nominal@bench"]`, a `data:` key, `sourceColumn` and `nominal@*` in `order` all load. Obsidian reads notes, so a column no note has is empty.
