# PEP 0015: Source precedence

- **Status:** superseded 2026-10-31 by [PEP 0021](0021-source-columns.md). Zach: "I feel you did an adhoc thing for the Source roll up". The data
  shape below stands, to the byte: the reader now unfolds it into plain columns, and a formula takes the nominal. PEP 0021 goes through every behaviour
  this PEP froze, kept or dropped, each with why. Read this one for how the shape came to be. Was accepted 2026-10-30, lane/source-precedence.
- **Contract:** CONTRACT §36, reworked in place to the new model (and §22's `display: link` line, §2's sort line, landed beside it).
- **Asked by:** Zach, relayed by the orchestrator, 2026-10-30: a general pattern in data-ui for any record whose fields
  have values from several sources, and how to reconcile them, "more general than this use case". He picked the round-2
  prototypes' **V1 "Source ranking"** as the default (a toolbar toggle), with **V4's ladder default** (the order comes
  from an evidence ladder, shown as a change from it) and **V5's count** ("n chosen by hand"), and V2's source matrix as
  the conflict-management mode. Prototype: robotparts `reports/media/datasheet-sources-round2-src/` (reconcile.js, p1.js,
  p4.js); its gallery `datasheet-sources-round2-2026-10-29.html` scored V1, V3 and V4 within three points.
- **First consumers:** RobotParts' Datasheet (one part, its fields as rows) and a Tycoon CRM contact.

> **What stands:** decisions 1, 2, 3, 6 and 7: the data shape, the host resolving, pick and conflict, no mark on a value with several sources, the
> translucent tint. Decision 4's state stands, its URL and storage keys unchanged, but a drag writes it now. **What went:** decision 5's Manage sources, the
> synthetic columns, their header and second drag: every source is an ordinary column, and "Manage sources" below describes a mode that no longer exists.

## The question under the question

The prototype is one record whose fields are rows (`{sources, fields: [{id, v: {sourceId: value}}], ladder}`). Built as
that, it would be a datasheet widget. The general thing is a **value that several sources state**: it can sit in any
cell of any table (a parts table where each part's torque has three sources, a contact list), and every view, sort,
filter, summary and right-click should read *one* nominal value from it. So the unit is the cell, not the record.

## Criteria (weighted)

| Criterion | Weight |
|---|---|
| Truthful: the nominal is one source's value exactly as stated; nothing edited, merged, rounded or averaged; conflicts honest | gate |
| General: any table, any record, with only data changed (the datasheet and the CRM contact run the same code) | 25 |
| Reuses the contract: a multi-source value is built from §22 rich cells, so sort, filter, rail, summaries, other views and the popover get the nominal for free | 25 |
| Small surface: fewest new dataset, cell, view and element names | 20 |
| Buildable and testable now, nothing moves for data without it (goldens unchanged) | 20 |
| Free for data that does not use it | 10 |

| Option | General | Reuse | Surface | Now | Free | Score |
|---|---|---|---|---|---|---|
| **A. A cell carries `sources: [§22 cell + source id]`; the dataset declares `sources` and `ladder`; the host resolves each such cell to its nominal before the row model** | 5 | 5 | 4 | 4 | 4 | **92** |
| B. A record shape (`{sources, fields: [{v: {id: …}}]}`) as a new input form, normalised to rows | 2 | 3 | 3 | 4 | 5 | 60 |
| C. The table alone picks and draws the nominal; the row model keeps the raw cell | 4 | 1 | 5 | 5 | 5 | 72, fails the gate: a sort or filter would read a value the reader does not see |

## Decisions

1. **The data shape: §22 cells, one list per value.**
   - A cell may carry `sources: [{source, value, text?, unit?, basis?, note?, asOf?, sourceUrl?, sourcePage?, record?}]`.
     Each entry is a §22 rich cell that one source states; `source` names a dataset source (an undeclared one is named by
     that string, so a cell that already lists several sources reconciles with no dataset key at all).
   - The dataset may declare `sources: {<id>: {name, kind?, rung?, date?, url?, page?, basis?}}` and `ladder: [{id,
     label}]` (best first). The prototype's `s / d / n` map onto §22: `n` (compared) is `value`, `d` (drawn) is `text`,
     `at` / `page` / `s` (where and as stated) go in `note` or `record`.
   - WHY a list, not a map: order is the producer's (an integer-like key reorders in JS), and each entry is literally a
     §22 cell (`source` is §22's key). WHY no new value fields: every one the UI needs is §22's.
2. **The host resolves, before the row model.** `<data-views>` keeps the data as loaded and shows it resolved: each
   multi-source cell becomes its nominal (`resolveCell`: the picked entry's own fields as stated, its source's name as
   `source`, the source's url / page / date / basis only where the entry has none, every entry still in `sources`).
   Rows with none stay the same objects; data with none is the same dataset object, so nothing changes for it. WHY:
   sort, filter, the rail, groups, summaries, cards, the peek and the right-click popover all read the nominal, with no
   change to any of them.
3. **pick:** the row's override when its source states the cell, else the first source in the order that states it; a
   source the order lacks follows in the cell's order (a stale link never hides one); an entry with no value states
   nothing. **conflict:** the stated values differ by value and unit (JSON: a list element by element; no unit
   conversion; text alone is never a disagreement). Re-derived from reconcile.js, with these fixes: its `String(n)` key
   made `[15, 60]` equal `"15,60"` and every object equal; it counted an entry with no value as a statement; its
   `stated()` dropped a source a stale order lacked; `held()` did not check that the override was effective.
4. **State: `{order, ov}` per element, per dataset.** `ov` is keyed by row id (a field in a datasheet, a record in a
   records table: "this row from that source"). The URL carries it the §31 way (`#sources=<order>` when not the default,
   `#picks=<row>:<source>,…`), localStorage keeps it per viewer (`data-ui/sources/<page path>/<data id>`), the URL
   winning, then storage, then the ladder default. WHY the page path in the key: RobotParts gives every part's datasheet
   one dataset id; a reader's picks for one part must not land on another. WHY not view keys: precedence is about the
   data, so every view of the element reads the same nominal (switching Table to Cards must not change a value).
5. **The UI is Zach's pick.** The table puts "`<value label>` source" after the first multi-source property ("Nominal
   source", "Value source"): one source is a link (§22's link rule: a private source is a plain label), 2+ sources add
   a dropdown (every source in precedence order, the shown one checked, "Back to precedence" when the row is chosen by
   hand). "Manage sources" (the toolbar, both bars; the bar's "…" when narrow) swaps that column for one column per
   source in precedence order: drag a header (or its ‹ ›) to reorder every row; conflicting cells tinted amber, the
   shown one outlined. The status line says "Precedence changed from default · Reset" and "N chosen by hand · Clear".
6. **No basis mark on a multi-source value in the table.** Its source is named in the column beside it, as the round-2
   prototype drew it (its gate g4: "0 basis marks"); the basis stays in the hover and the right-click. Other views draw
   §22's mark as before.
7. **The conflict tint is a translucent token** (`--dv-tone-warn-tint`, a host sets `--data-warn-tint`), so it lies
   over a row's own fill.

## Not done

- A per-cell override for a second multi-source column in the same table: its popover (below) lists its sources and
  picks one, but a pick is the row's (`ov` is keyed by row), so it moves every value of the row that source states;
  the popover says so. A view key to pick or hide the Nominal source column, if a consumer needs one.
- ~~The right-click popover listing every source of a multi-source value~~: done 2026-10-30 (lane/source-popover,
  CONTRACT §36 "the source popover"). A right-click or the menu key on such a value in the table, the cards, the record
  page or the side peek opens the item menu with every source in precedence order, picked through
  `setPrecedence({ov})` as the dropdown does. Not done there: the other views (list, kanban, compare, …) keep §22's
  popover of the nominal; a long-press opens it only where `sources.js` is loaded (it hands the press over).
- Live datasets with multi-source cells (a live snapshot is not resolved), and the row-model worker for them (a
  multi-source dataset builds its model on the main thread).
- ~~The Nominal source column on data whose values have one source each~~: done 2026-10-30 (lane/source-popover,
  CONTRACT §36 "the source column on one-source data"), as a declaration: `sourceColumn: true` draws it, `false` never.
  Not done: drawing it, undeclared, wherever a cell carries one §22 `source`. WHY: 30 gallery data files do (sourced
  torques, KPIs), so every such table would grow a column it never asked for, and the table oracle would move; a
  consumer that wants it says so in its data (RobotParts' datasheet).
- ~~A derived nominal's source column read "—"~~: done 2026-10-30 (lane/source-popover, CONTRACT §36 "a derived value
  names its source"). A derived value names what it came from, with a quiet "derived"; "—" only where nothing names a
  source. RobotParts' side: its datasheet still writes `nominal: None` for a derived spec (the value goes to its own
  Derived column), so its pole pairs must become a nominal (an entry on its `derived` rung, as `source_entry` declares
  it) before the column can name the selection list.
- A gallery case (the fixture is tests/browser/fixtures/source-precedence/; a case would move the perf and table
  oracles).
- `linkProperty` and open-mode URLs still link any value; only `display: link` and source links follow the link rule.
