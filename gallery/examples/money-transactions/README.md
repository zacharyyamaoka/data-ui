# Money transactions (illustrative)

Transactions grouped by kind and category, a table with a sum per category, the same rows by entity, and a form that
recategorises one. **Illustrative rows only:** money's synthetic test fixture, never real account data.

- **App:** Money
- **Replaces:** money has no transaction list of its own: its Flask pages (`statements.html` and `home.html` in
  `~/money`, `src/money/templates`) show totals by category, and the transactions themselves are only in Fava's journal.
  This is the list those totals come from, grouped the way the statements group them, with the category as a field
  you can propose a change to (money's own fix is a rule in `rules.toml`).
- **Shows:** `type: list` with `groupBy` + `subGroupBy` (kind -> category) and numbered markers, a table grouped by
  category with Sum summaries (view summaries, from the rows), and `type: record` with `edit: true`: the category is
  a select over money's account list (`constraints.enum`), everything the bank reported is read-only. On this static
  page the host refuses the save, and says so.
- **Data:** `transactions.json`, 19 rows written by `source/make.py` from `tests/acceptance/fixture_home` in `~/money`
  (synthetic: ACME WASTE, account masks 9001 and 1234), booked by money's `src/money/ledger.py` (rules first, then
  matched transfers, then Plaid's category). Amounts are CAD, money in positive.
