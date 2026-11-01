# PEP 0016: The notion table

- **Status:** accepted 2026-10-30, lane/notion-table.
- **Contract:** CONTRACT §40, on top of §37 (the editable sheet) and §38 (a record as a page).
- **Asked by:** Zach, 2026-10-30: "We 100% need to add the features where we can actually edit the data ourselves inside data UI, so
  it becomes even more like a Notion table. And of course we can support toggling on an edit and view mode if we want."
- **First consumer:** the `notion-table` gallery case, the page Zach plays with. Vibe Tracks stays on §37 until it sets `edit-toggle`.

## The question under the question

§37 already edits a cell. What a sheet still lacks is everything that makes editing safe to do quickly: a way to not be
editing (the toggle), and a way to take any edit back (undo). Delete, paste and column changes are only comfortable once those
two exist, which is why Notion can delete a row with no dialog. So the frame is not five features; it is **one reversible edit
session** with five doors into it.

## Criteria (weighted)

| Criterion | Weight |
|---|---|
| `editable` with no `edit-toggle` behaves exactly as today (Vibe Tracks depends on it); the §37 checks and the goldens do not move | gate |
| Truthful: nothing a reader typed or stored is rewritten by a change of column, a paste or an undo | gate |
| The host owns the data: every write, undo included, goes through a hook when there is one; a refusal leaves the stack true | 30 |
| Zero relearning: Notion's and a spreadsheet's keys, gestures and wording | 25 |
| Small surface: fewest new names on the element, the data and the `.base` | 25 |
| Calm: View is a read-only table to the byte; no new side panel; no dialog | 20 |

| Option | Host owns | Relearning | Surface | Calm | Score |
|---|---|---|---|---|---|
| **A. A session in the element (`edit-session.js`): every write funnels through one plan; undo replays old values through the hooks** | 5 | 5 | 4 | 5 | 95 |
| B. The table keeps its own history of DOM cells | 2 | 5 | 3 | 5 | 73 |
| C. Hosts implement undo; the kit only draws the keys and the toast | 5 | 3 | 2 | 4 | 69 |
| D. An `editable` page gets all of this by default | 4 | 5 | 5 | 2 | 80, fails the gate |

## Decisions

1. **`edit-toggle` is the whole opt-in.** Delete, undo, paste and the column menu draw only on an `edit-toggle` page in Edit, and
   `editable` alone stays §37 to the byte. WHY: "behaves exactly as today" is a gate, and an opt-in with one name is the smallest
   surface. Vibe Tracks gets the rest by adding one attribute when it wants it.
2. **View is a read-only table, not a disabled one.** The check compares the drawn HTML with a page that has neither attribute.
3. **The session lives in the element, not the table** (`packages/core/src/edit-session.js`, the pure half in `sheet.js`). WHY: a page
   section, a form, a cycle flip and the kanban all go through `propose`; a history in the table would miss them.
4. **Undo is old values through the same hooks.** A delete comes back through `acceptAdd` with `{set, id, restore: true}`. WHY: the host
   stays the owner, and a host needs one more field to read, not one more hook.
5. **`acceptBatch` is additive and optional.** With it a paste is one call, all or nothing. Without it each row goes through its
   own hook, what is refused is reported, and the undo step holds only what landed. WHY: §37's hooks are one row each and a paste
   must not make a host wait for a thousand round trips, yet a host that wrote `acceptEdit` must not have to write anything new.
6. **On `ok` the element applies deletes, batches and property changes to what it holds**; `acceptEdit` and `acceptAdd` keep §37's rule
   (the host changes the row or hands in data). WHY: a row that stays on screen after a confirmed delete reads as a failure, and
   applying is idempotent when the host hands in new data.
7. **A block is a tab, or several lines with an HTML table beside them.** WHY: a paragraph pasted into a notes cell must stay one cell;
   every spreadsheet puts a `<table>` on the clipboard, so the single-column case is still caught. The scanner is the CSV
   reader's, extended with one mode: a quote opens a quoted cell only when it closes before a separator or a line end, because a pasted
   `"hello" world` is words, not CSV.
8. **Values land by position.** A locked column consumes its value and is reported, as Notion's read-only columns do. Shifting
   values past it would put them in the wrong columns.
9. **A value that does not fit stays as written**, in a paste and across a change of type. WHY: Zach's truthful-rendering rule. This
   needed a text box for such a cell: `<input type=number>` reads `"soon"` as empty, so opening and leaving the cell would
   have erased it.
10. **`select` has no options editor.** Free words with the column's own values offered (a native `<datalist>`), or the data's `enum`. WHY:
    stock part first, and options are one more surface nobody asked for.
11. **Rename is the `.base`'s `displayName`**, and never touches a key. Type and values are the host's, through `acceptProperty`.
12. **A column's delete takes its values with it**, kept in the undo step. WHY: left in the rows, they would still reach Copy and the raw
    source view of a property that no longer exists.

13. **A value that comes from its sources refuses a hand edit, on every page.** Found 2026-10-30, reproduced at d5ede93: `readEdits` keeps
    `sources` beside the new `value`, and `resolveCell` picks a source entry again, so the edit vanished for the reader while a host's
    `acceptEdit` may have saved it. A silent loss is worse than a refusal, so `_decide` refuses it before any hook, naming the
    property, and the editor keeps the typed text. WHY the one exception to decision 1: this is a bug fix, not a feature. A paste, a batch
    and an undo treat such a cell as locked and count it, because many cells must not fail for one.
14. **`isMultiSource` is the test, so a `sources` list of one entry refuses too.** It resolves back just the same. "Single-source" that stays
    editable is §22's cell naming one `source`, which has no list to resolve from.

15. **The hand filter keeps no state.** Zach, 2026-10-30: "just make a table and filter it and do it manually". It reads and writes `el.filters`
    through the rail's forms (`setColumnFilter`). WHY: a second filter would have to be reconciled with the pills, the query box, the rail and the URL
    forever. Is-empty is the one thing the rail's forms lack, so it is the plain clause `x.isEmpty()`, which a pill reads as words.
16. **In View it is reached with no mark on the table:** a header's right-click and the toolbar's Filter menu. WHY: "View is a read-only table to the byte" is a
    frozen check, and a filter changes what is shown, not the data, so it belongs in both modes without earning a button in every header.
17. **A row edited out of a filter stays until the view refreshes,** copying Notion, with a note and a Refresh, because a silent stale row is a lie of its own.
    What refreshes: a change of the filter, the search or the view, leaving Edit, a reload, or Refresh. Kept by id in the row model's own step, so sort, groups and counts
    all see the same rows. Only on an `edit-toggle` page: `editable` alone stays §37.

18. **The gallery case keeps one snapshot in localStorage, with no hooks.** Zach, 2026-10-30: "open up a simple example that shows a partially filled notion-like table
    where I can begin to play around with it". Nothing on that page owns the data, so there is nothing for a hook to decide, and one small `sheet.js` stays simple.
    New blank table writes a blank snapshot and reloads, so it is the same path as a return visit. It is written only once something changes, so an untouched page shows the sample.
19. **A new gallery case moves `perf-oracle.golden.json`, by construction:** the corpus digests every case the site lists. The coordinator took that decision on
    2026-10-30 (the brief had said the goldens must not move), for that file only: regenerated from main's code over the new gallery, never the code under test, with the proofs in its commit.

## Open decision

**Should a hand edit become a new top-ranked "hand" source?** Today a multi-source value refuses a hand edit (decision 13). The longer-term
choice is to let the reader type, recording what they typed as a source of its own, ranked above the others, so the sources stay truthful
and the override is visible and reversible (Clear puts the ladder's pick back). For: it is the edit a reader wants, and §36's picks already show
a hand-chosen source. Against: it adds a source id the data never declared, and a host must decide where it lives. Not built; the refusal is the
reversible default, because nothing is lost by it and a later "hand" source only widens what is allowed.

## Not done

Row drag-reorder, fill handle, formulas, relations, comments, real-time multi-user. Also: a second undo in another view of a hidden
column asks you to go back to that view; an in-memory rename or a new column is gone after a reload unless a host keeps it
(`acceptProperty`, `persistView`), which is what "in memory" says; a right-click on a value with one source (`data-provenance`) keeps
its "where this value comes from" menu, so Delete is reached from the rest of the row; the row menu is the table's, not the cards'.
A deleted column leaves the open view's `order`, sort, grouping, widths and summaries, and comes back with undo; a filter that names it
stays, as does another view's `display` of a retyped column. `persist="local"` keeps view state, not a rename; a rewrite of the
`.base`'s `properties:` block loses comments inside that block, and only there (`replaceKeyInText` rewrites one key).
