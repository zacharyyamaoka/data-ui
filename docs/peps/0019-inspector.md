# PEP 0019: The inspector, one property per row

- **Status:** accepted 2026-10-31, lane/inspector.
- **Contract:** CONTRACT §44, on top of §36 (the source popover), §37 (`peekExtra`) and §38 (a record as a page).
- **Asked by:** Zach, 2026-10-31: "I don't like how when I look at the inspector menu its not a 1:1 coorespondance with the fields I
  am seeing"; "Desired is notions: pattern where you have 1 property per cell"; "And then you have control over what property
  visibilty in the inspector or in the row".

## The question under the question

The peek had grown three lists of one record: key-spec chips, a Specs tab in the data's order, and a Sources tab. None was the list
the reader had just been looking at. So this is not a restyle; the inspector stops owning a property list and **reads the one the
view draws**. Everything else (visibility, the fold, the slot) follows from that. His third picture settles the one real fork: Text
is out of the table and on the page, Files & media the reverse, so the two visibilities are independent.

## Criteria (weighted)

| Criterion | Weight |
|---|---|
| Existing `.base` files keep working; `el.peekExtra` and `dataset.detail` keep their meaning | gate |
| 1:1 is literal: what the table draws, a column it adds itself included, with no source-specific code in core | 35 |
| Zero relearning: Notion's three words, its "N more properties" | 25 |
| Smallest grammar: fewest new keys in the `.base`; a file with none reads correctly | 25 |
| A later lane's plain per-source columns render with nothing changed here | 15 |

| Option | 1:1 | Relearning | Grammar | Sources later | Score |
|---|---|---|---|---|---|
| **A. `record.visibility: {id: show \| hideEmpty \| hide}`; no word follows the column; the view plugin reports its columns (`drawnColumns()`)** | 5 | 5 | 5 | 5 | 100 |
| B. Two lists, `record.order` and `record.hidden` | 3 | 3 | 2 | 4 | 58 |
| C. A word on `properties.<id>` (Notion's own scope: one setting per database) | 3 | 5 | 4 | 4 | 79 |
| D. Inspector reads `view.order` only, no plugin seam | 2 | 5 | 5 | 5 | 79 |

C loses because Zach asked for it "saved in the view". D is what `order` alone gives: it misses "Nominal source", which is in his
screenshot's table, and any per-source column Manage sources adds.

## Prior art

- **Notion** names exactly these three: Always show, Hide when empty, Always hide; hidden properties collect in one item at the bottom
  of the list ([Intro to databases](https://www.notion.com/en-gb/help/intro-to-databases)). Hiding a column is per view
  ([Database properties](https://www.notion.com/help/database-properties)).
- **Airtable** puts fields hidden from the grid behind an "x hidden fields" bar in the expanded record, and its users have asked for
  separate grid and record visibility ([community thread](https://community.airtable.com/other-questions-13/calendar-and-hide-or-show-fields-in-expanded-record-16221)).
  That is the default here, plus the separation they ask for.
- **Obsidian Bases:** `order` is the visible properties. Unchanged: `record` is data-ui's existing key.

## Decisions worth keeping

- **No word follows the column.** A visible column shows; everything else waits behind N more. So a file with no key is 1:1, and the
  key only records a difference.
- **An empty value in a visible column keeps its row**, a dash, as the cell is. This reverses the old peek, which dropped empties.
- **The title is the heading, not a row** (Notion's).
- **Sections stand.** `record.sections` is an author's layout, and it replaces the columns as the list; the rest wait behind N more.
- **A form lists every field.** A required input behind a fold cannot report itself.
- **A long property (§38) stays on the page without a column**, unless the view says `hide`: it is the page's body, not a row.
- **The slot is the existing one.** Under the properties sit, in order, the page, every value behind it, the records behind it, a
  folded Sources pane (the old tab), then `el.peekExtra`. No new host API; the extension point already existed.
- **One method on a view, `drawnColumns()`.** The table reports its leaves, one per property. The planned formula lane removes the
  synthetic column; the seam stays, and needs no change.
