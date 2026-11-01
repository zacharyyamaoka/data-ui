# Vibe Tracks feature board

Vibe Tracks' 76 feature notes on a kanban board: one column per `vibe-status`, in Vibe Tracks' own order, each with
its count. Drag a card to another column to propose a new status; drag a column header to reorder the columns, which
rewrites the view's `groupOrder`. The proof board groups by a derived property, so its cards stay put.

- **App:** Vibe Tracks
- **Replaces:** the sunset Obsidian Vibe Kanban plugin's board (its `.base` files in Zach's vault now fall back to a
  stock table grouped by a `formula.status` that hard-codes the column order) and the Board display of Vibe Tracks'
  own home (VT-018), whose rule this board keeps: "derived columns still refuse drops: state is derived, never
  claimed" (VT-025).
- **Shows:** `type: kanban` with Bases' `groupBy`, `groupOrder` (a named status with no features, `frontier`, is
  still a column; a status the order does not name, `todo`, follows it) and `columnWidth`; a card drag as
  `host.propose()`, which lands here because `site.json` makes the page `editable` (the edit lives in memory until
  reload; a read-only page refuses it with its reason); a column drag as `host.setView({groupOrder})`; moving cards and columns from the
  keyboard (Alt+←/→, or M for the Move menu); a derived group property (`proof`) locking the board.
- **Data:** `features.json`, written by `source/make.py` from `~/vibetracks/features/VT-*.md` front matter
  (vibetracks @ 90b71b0). Feature notes carry no KPI figures.
