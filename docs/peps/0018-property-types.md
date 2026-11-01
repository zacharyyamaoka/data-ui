# PEP 0018: Property types, and the two ways to edit a column

- **Status:** accepted 2026-10-28 by Zach on the lane's report, landed 2026-10-31 (lane/types @ 6e66395, seven judge rounds).
- **Contract:** CONTRACT §28, beside §37 and §40.
- **Asked by:** Zach, 2026-10-26: "Notion calls it Type, and each type has different formatting options… I don't think we support that as
  first class yet", "In terms of interacting with the table, let's just use Notion as the UX/UI reference". On the report, 2026-10-28:
  "This looks great merge it".
- **Why this record exists:** the merge was left staged when the account hit its weekly limit, and main moved 345 commits before it landed.
  §40 (the notion table) was built in that gap, so the kit reached landing with two column menus and two meanings of `el.editProperty`, neither
  knowing the other. A later rewrite will want to fold them; this says what each one is for.

## The question under the question

"Edit a column" is two different writes. **What the column is in the data** belongs to the host: its values, its definition, whether it exists
(§40, through `el.acceptProperty`). **How the file says to draw it** belongs to the `.base`: its name, icon, type and options, written line by line
so every other line and comment stays (§28, through `el.baseText` and `data-views-base`). A reader sees one column and one menu; the kit
holds two owners, and neither is wrong.

## Criteria (weighted)

| Criterion | Weight |
|---|---|
| What Zach approved stays what he gets: a header click opens Notion's menu, on every table | 35 |
| What main froze after it stays true: §40's checks, §37's, the goldens' proofs | 30 |
| Smallest landing: nothing rewritten that a lane already judged | 20 |
| One thing to learn for a reader, one name for a host | 15 |

| Option | Approved | Frozen | Small | One thing | Score |
|---|---|---|---|---|---|
| **A. Both menus stay; `editProperty` tells the two apart by its verb** | 5 | 4 | 5 | 2 | 85 |
| B. Fold §40's menu into Notion's now | 5 | 1 | 1 | 5 | 60 |
| C. Keep §40's menu, drop the lane's file items | 2 | 5 | 3 | 4 | 68 |
| D. A plain click keeps sorting, the menu moves to a button | 1 | 5 | 2 | 3 | 54 |

## Decisions

1. **A type changes how a value is drawn, never the value.** In the row model it is the column's `kind`, beside the storage `type` that filters, sorts and
   groups read. A hover and a peek say the value as stored. A type is never guessed from values.
2. **A header click opens the column menu; shift-click sorts.** Notion's own header. The one change here to a page that uses none of it,
   apart from the table's lines. Two checks written on main after this was approved assert the old click (`cell_text_checks`, `editable_cells_checks`); see
   their commit for what moved.
3. **`el.editProperty` is one name with two verbs.** `{op, property, …}` is §40's data edit; `{action, id, …}` is §28's file edit. WHY one name: both are what a caller
   means by editing a column, and at the merge two methods with this name sat in one class, the later silently winning. Told apart by the verb, neither
   can shadow the other.
4. **`host.writable` is `el.editing`.** Under §40, View on an `edit-toggle` page is read-only, and Edit needs no `editable` attribute; the attribute no longer answers.
5. **Main's rules win inside a typed cell.** A producer's `text` is drawn as written (§22); a multi-source cell draws no basis mark and keeps its source marks (§36);
   declared `digits` and `compact` reach every number (§17).
6. **The two menus share `.dv-colmenu`,** so the lane's rules say `:not(.dv-pop)`. A frozen cell holding its Open (§38) stays sticky.

## What would change this

Option B is the destination, not a rejected idea: one menu whose items write to whichever owner the item belongs to. It waits for §40's checks to
be rewritten against one menu, which is a decision for its own lane.

## Not done

- In Edit on an `edit-toggle` page a column has both menus: a header click opens Notion's, `[data-col-menu]` §40's.
- A file edit (`{action}`) is not on §40's undo stack.
- §40's `retype` changes the data's definition; a column the `.base` types keeps the `.base`'s drawing until the file changes.
- Vibe Tracks' sheets are `editable` with no `edit-toggle`: when it next vendors the kit, a header click there opens the menu instead of sorting (PEP 0016's gate
  held §37 to the byte; this is the one place it moves, by Zach's ruling above).
