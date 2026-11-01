# PEP 0021: Source columns

- **Status:** accepted 2026-10-31, lane/source-columns. Supersedes [PEP 0015](0015-source-precedence.md), whose data shape stands.
- **Contract:** CONTRACT §36, reworked in place; §28 (a header sets no floor), §37 (`persist="page"`), §40 (a source's own column
  edits), §44, §45. Migration: [`docs/migrations/source-columns.md`](../migrations/source-columns.md).
- **Asked by:** Zach, 2026-10-31, on robotparts' datasheet: "I feel you did an adhoc thing for the Source roll up.. Instead I feel there
  is likely a more general pattern. its just like a column roll up where the left most take precencde. And then to hide them it simply
  like a view with thoose columns hidden. The roll up itsself is also then just like a formula.. almost like FIRST Value(of cells, x, y,
  ...)", and "Desired is notions: pattern where you have 1 property per cell".
- **Settled before this lane:** the Notion survey's §16, decisions 1 and 3: formulas run in the browser for display columns only and a
  headline KPI stays the producer's; the reader unfolds today's `sources` list, so no data file changes.

## The question under the question

PEP 0015 asked which of a cell's sources is nominal, and answered inside the cell: one cell, a list in it, a mode to look inside. Every
tool that followed (synthetic columns, their own header, their own drag, a toolbar button, a dropdown) existed because a cell held several
properties. Zach's frame moves the unit to the property. Then there is nothing to manage: sources are columns, and everything a column
already does (hide, width, sort, filter, Property visibility, the inspector) is done.

The brief's own line hid a trap: "default the visible column order left to right" read literally contradicts "to hide them it simply like
a view". If the visible columns were the list, hiding a source would change a value, and a view with no source column would have no list
at all. So the list and the view are two things that must agree, and most of the decisions below are how they agree.

## Criteria (weighted)

| Criterion | Weight |
|---|---|
| Truthful: a value is exactly as stated; hiding a column never changes a value; an edit is never silently lost | gate |
| Existing data files and `.base` files keep working, untouched (2,103 robotparts datasheets) | gate |
| One property per cell: a source is an ordinary column, with no source code where a column already works | 35 |
| Left-most wins, always, read off the page | 25 |
| The file says it: precedence is text in a `.base` that stays valid in Obsidian | 20 |
| Smallest surface, and the least code kept | 20 |

| Option | One property | Left-most | File | Surface | Score |
|---|---|---|---|---|---|
| **A. The reader unfolds `sources` into `<property>@<source>` columns; the value is a coalesce over them; a `.base` may state one over any columns** | 5 | 5 | 5 | 4 | 96 |
| B. Producers move to plain columns now, and `sources` goes | 5 | 5 | 5 | 5 | 100, fails the gate: every data file changes |
| C. Keep the synthetic columns and give them view keys | 2 | 3 | 2 | 2 | 46: the mode with a saved flag |
| D. Precedence per view, in each view's `order` | 4 | 5 | 3 | 5 | 80, fails the gate: Table and Cards would read different values, and a hidden source would forget its place |

B stays open to any producer at any time: plain columns and a formula work today, with no `sources` list anywhere.

## Decisions

1. **The reader unfolds.** Each `(property, source)` with a statement is a column `<property>@<source>`, typed as its value, its label
   the source's name. A row's plain §22 cell sits under the source it names, so its row is one property per cell too. `hidden` keeps
   a column out of a view that does not name it; `offered` keeps it in Property visibility and the inspector. WHY `@`: Bases reads it as no
   part of a name, so nothing can misread it; YAML takes it unquoted when not first; a formula writes `note["nominal@bench"]`, which
   Obsidian runs. It is not the first character because `@` there means a pivot column in this kit and is reserved in YAML.

2. **One formula, in Bases' spelling, and no language.** Bases has no coalesce, and a name of ours is an error in Obsidian: `coalesce(a, b)` and
   `first(a, b)` both draw `Cannot find function` in the cell (Obsidian 1.12.7, run in the isolated instance). Bases' own functions
   make it: `[a, b].filter(!value.isEmpty())[0]`. Run there, that spelling fails on a boolean (`Cannot find function "isEmpty" on type
   Boolean`), so the kit reads a second: `[a, b].filter(value.isType("boolean") || !value.isEmpty())[0]`, which ran on every type. WHY a
   reader of that shape and no evaluator: Survey §16 limits formulas to display columns, this lane needs nothing else, and the tokens
   are the filters' own. Stock parts considered: none earn a dependency for one shape. Any other formula draws a dash and says it needs
   Obsidian; the checker warns only on a file read with data, because a `.base` with none is Obsidian's own and any formula is right there.

3. **Hiding changes nothing: a hidden source keeps its place.** The list is stored apart from any view (`inPlace`). Rejected: hidden sources
   drop out of the coalesce, which would give a what-if tool at the price of the sentence Zach wrote. A reader who wants a source out
   picks another for the row, or writes a formula that leaves it out.

4. **The view's columns follow the list; a drag moves the list.** A view gives the slots, the list fills them (`slotOrder`), so left-most is
   true of every view whatever a file wrote. A reorder of the same columns, through the one way a view changes, moves the list
   (`orderAfter`). A hide or a show is no reorder: Property visibility appends, and a source shown again goes back to its place.

5. **One precedence state, the one that was there.** `{order, ov}`, `sources=`, `picks=`, `data-ui/sources/<page path>/<data id>`, `el.precedence`,
   `setPrecedence`, the event: unchanged, so old links and what a returning reader kept come back. WHY not a list per formula: a source
   has one place, and a reader's drag moves it for every value that reads it. A file's formulas keep their own lists until a reader
   drags (`formulaView`), so two formulas may read one column in opposite orders ("best case", "checked first") and mean what they say.

6. **The default.** The ladder; a file's formula states it; with none, the first view that names two sources, left to right. Either way
   the sources it does not name keep their ladder places: the rule that a stale order never hides a source.

7. **`<property>@source` is an ordinary column, and its alias is thin.** It names the source that won, so it filters and sorts by name. A
   view that names the value and no column of it keeps it, after the value: that is the one thing an existing `.base` needs. WHY a view
   key, `sourceColumn: false`: a reader's hide must survive being saved into a file whose `order` looks like an old one.

8. **Manage sources is a view.** A file with no source column gets an implied `Sources` view: its first table with the value in it, each
   `<property>@source` given up for `<property>@*`. WHY implied: a file written before this cannot reach the columns in one click, and one
   robotparts `.base` serves 2,103 parts with different sources, so it cannot name them; `@*` lets it. A file that names a column, or a
   view called Sources, has said what it wants.

9. **An edit goes to that source's own column.** The kit folds it into the stored cell, so a host, the undo stack and the event see the
   cell the file holds, and undo gives it back to the byte. The entry's old `text` goes, or it would contradict the value. A plain cell
   in another source's column keeps what was there as a statement of its own. A formula cell refuses, as before; a whole new list of
   sources is the data itself, nothing set beside it, and passes. Two silent losses surfaced and are fixed at one seam (`withValue`): a
   rich cell's `text` drew over an edit on every page, and a value typed in a formula's cell carried `sources` and passed for a new list.

10. **A headline KPI stays the producer's.** A `kpi` view naming `formula.*` draws no number and says why; the checker refuses it. A KPI on a
    value with several sources reads its nominal, as it always did: that is the data's value, not a browser's sum.

11. **A header's words set no floor** (found by robotparts adopting the kit: 156 / 603 / 284 px, and the 603 would not drag). They widen a
    column nobody has sized, up to 240 px, and hold no drag and no stored width; past that an ellipsis, the whole name on hover. One
    rule for every column, Notion's. It changes §28's "never narrower than its content": a column's content is what it holds, and
    `types_r2`'s r1 #6 drops header text from what it asserts.

12. **`persist="page"`** (found the same way: 2,103 pages, one data id, a preset chosen on JMC opened moteus on 0 of 16 rows). A second word for
    the attribute there is: the view per page path and data id, the scope precedence has; the widths per data id, because a column
    dragged wider is wanted on every part. `persist="local"` means what it meant.

## What became of each behaviour PEP 0015 froze

| Behaviour | Now | Why |
|---|---|---|
| The data shape: `sources` on a cell, `sources` and `ladder` on a dataset | **Kept**, to the byte | The reader unfolds it, and no data file changes |
| The host resolves before the row model | **Kept** | Sort, filter, rail, summaries and every view read the nominal with no change to any of them |
| pick, and a stale order never hiding a source | **Kept** | It is the coalesce, over an order |
| conflict, by value and unit | **Kept** | It is what the pill counts, now read off a formula's columns too |
| State `{order, ov}`, URL, storage, the event | **Kept** | Old links and kept state hold; a reader on a read-only page has nowhere else to put a list |
| The ladder default | **Kept** | It orders the list when no file states one; it fits as the default of a list |
| A row's own pick, "N chosen by hand · Clear", Back to precedence | **Kept** | The Survey's "one more column, first in the list": a head on that row's list, per viewer, not data |
| "Precedence changed from default · Reset", "4 values changed" | **Kept** | Reset is the distance between the reader's list and the file's |
| "`<label> source`" column, a link or a private label | **Kept**, as an ordinary column | Hide, width, sort and filter come with it |
| The pill, "+3 · 2 differ" | **Kept**, moved onto the formula's cell | Zach: the fact must survive every source column being hidden |
| Its own dropdown menu | **Dropped**: the pill opens the right-click's menu | One menu; it says more |
| Manage sources, `el.manageSources`, two toolbar buttons | **Dropped**: the Sources view | "to hide them it simply like a view" |
| The toolbar's count of rows that disagree | **Dropped** | The pills say it, row by row, and it had no button left to sit on |
| A source's header: rank, grip, kind, link | **Dropped**: an ordinary header; kind and date in its hover | Left-most is the rank; the link is on `<label> source` and in the menu |
| ‹ › on a header | **Dropped**: Alt+← / Alt+→ on any header, Property visibility's ↑ ↓ on a phone | The keyboard's way to reorder, for every column |
| The pointer-event header drag | **Dropped**: the ordinary drag | No second drag. A finger reorders from Property visibility |
| `tr[data-conflict]` | **Dropped**: the pill's `data-conflict` | The fact was the mode's |
| Conflict tint, the shown cell outlined, `--dv-tone-warn-tint` | **Kept**, on a column's cells | Derived from the columns, in any view that shows them |
| No basis mark on a value with several sources | **Kept** on the formula's cell | A source's own column is a one-source cell, so it has §22's mark |
| The popover: every source, rank, rung, basis, date, note | **Kept** | It is the pill's menu now too |
| `sourceColumn: true / false`, a derived value names its source | **Kept**; see the migration | `false` now stops the column being drawn unasked; a view may still name it |
| Refusing a hand edit of a multi-source cell | **Kept** for a value; a new list passes | An edit of a source's column arrives as one, and it is the data itself |
| `move()`, `manage`, `conflicts` on `input.precedence`, `input.sourceColumn` | **Dropped** | Nothing reads them; a drag is the view's order |

## Not done

- A per-formula `ov`: a pick is still the row's, and the menu says so when it moves two values.
- The kit does not write a hand pick into a file. A pick is a reader's; a value in a source's column is data.
- Live datasets are still not unfolded, and data with sources still builds its model on the main thread (`_ensureWorker`).
- A `.base` formula over plain columns gets no "`<label> source`" column; its pill and menu name the columns it read.

## What would change this

A second real formula: the moment a page needs more than this shape, the reader becomes a stock expression library, not a longer reader.
And if readers hide the top source and read that as dropping it, the alternative in decision 3 becomes a view key, not a change of meaning.
