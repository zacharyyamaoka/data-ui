# PEP 0020: Column resize and nested groups

- **Status:** accepted 2026-10-31, lane/table-groups.
- **Contract:** CONTRACT §45.
- **Asked by:** Zach, PROJECT - Robot Parts, Oct 31: "I don't like how I cannot resize these columns for example I may want to
  read what is more inside here.." and "We should be able to support multiple nested things. For example here
  servo.pid_position should be within servo! not on the same flat level". Everything is in data-ui, so every host gets it.

## Why he could not resize

Reproduced on RobotParts Preview (`/actuator/jmc-60asm200-5-1024c/#datasheet`, vendoring 5e56f79), real mouse, 80 px drags: Field,
Nominal, Verdict and Measured all moved 80 px; **Nominal source stayed 236 -> 236**. `_srcHead` drew that one header by its own
code path and never emitted `.dv-resize`, so its edge was plain `th`. The name in it was cut from 577 px to 124 px, and neither the
name nor its cell had a `title`: the column that most needed widening was the one column that could not be, and nothing else
reached the value. Not the cause: a stale vendored copy, the header's `draggable`, a host's CSS. Two neighbours found on the way:
a press with no movement pinned every column into `columnSize`, and the handle was 6 px with nothing to see until it was hit.

## Decisions

1. **Every leaf header has the handle**, the synthetic source columns included, and the drag does not start Manage sources'
   precedence drag or end in a sort. A press that does not move writes nothing.
2. **The hover shows a line down the table on the boundary** (`.dv-resize-guide`) and the handle is 10 px. It sits inside the
   column's right edge, not astride it: a `th` clips, and a later sticky `th` paints over an earlier one.
3. **Double-click fits, measured off-screen by the browser on real cells**, over every record up to 2,000 and an even sample past
   that, up to 1,600 px. WHY not the drawn rows, as AG Grid does: a virtualised table's longest value is usually below the window.
4. **A cut-off value is one hover away** (`.dv-cliptip`): an ellipsis, and the whole value, only when it is really cut. `title`
   stays for everything else; it is lifted while the tip shows so two tooltips never stack. Keyboard and touch reach the value by
   the record's peek. There is no keyboard resize: a tab stop per column costs more than it gives; say so if that changes.
5. **The name gives way before the pill.** As a column narrows the name shrinks to nothing, then the pill, whose caret is pinned
   so it still reads as a menu and still opens at 56 px.
6. **`groupBy: {property, path: dotted}`.** One optional key on a level. `dotted` splits text at each `.`, any other word is the
   separator, and a list cell is a path as declared. A number is never split (1.5 is one group). `by` or `bins` beside it is an
   error. `subGroupBy` stays and takes `path` too, so nothing is renamed and every existing `.base` means what it meant.
7. **TanStack's grouping does the work.** One grouping column per segment gives counts (`getLeafRows`), sorting per depth, the fold,
   and summaries for free. TanStack has no variable depth, so the only code of ours is `settled()`: a level where a row has run out
   of segments dissolves, and its rows sit in the level above. `tree: {path}` was the other seam; its last segment is the row
   itself, its headings intermix with rows under a sort, and they have no summaries.
8. **Direct rows first, then child groups**, the rule sections already have (CONTRACT §20).
9. **Nesting is for table, list and cards.** Cards draw H1 and H2 and roll deeper levels into H2. A kanban keeps whole values: a drop
   writes the column's key, so a "servo" column would overwrite `servo.fw`. So do a nav facet (a pick filters on what a cell holds),
   timeline, calendar, KPI and pivot. `viewPath()` is the one place that says so.

## Prior art

| Part | What it does | Taken |
|---|---|---|
| [Notion table view](https://www.notion.com/en-gb/help/tables) | Hover a column's edge, drag | The drag and the hover. Double-click to fit is not in its help page |
| [AG Grid column sizing](https://www.ag-grid.com/javascript-data-grid/column-sizing/), Excel | Double-click a header's edge fits, AG Grid over rendered rows only | The gesture, not the limit |
| [AG Grid tree data](https://www.ag-grid.com/javascript-data-grid/tree-data-paths/) | `getDataPath` gives each row an array; missing levels become "filler groups" | Declared paths and generated parents |
| TanStack Table grouping | Fixed levels, one column each | The engine (`@tanstack/table-core`, already bundled) |

## What a producer changes

Nothing unless it wants the nest: add `path: dotted` to the level. RobotParts: `site/views/config.base`, "All parameters by section",
`groupBy: { property: section, path: dotted }`, then vendor this build.
