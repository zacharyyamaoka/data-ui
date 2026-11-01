# Admin (Shopify-like): a summary card and a table card

Tycoon's Shopify-style index page rebuilt from one `.base` file: the summary card on top (four counts of the rows, each label's dotted underline giving its definition), then the table card (the "All ⇅" view chip, "Search and filter" that opens into "Searching all organizations", Cancel and "+ Kind" filter chips, avatar chips, tag pills with "+2", dates as "Apr 10" and "Jul 25, 2023", and the "‹ 1–14 ›" pager under the card). Fourteen invented organizations here; the full app, with the dark sidebar and the Deals screen, is [app/index.html](app/index.html).

- **App:** tycoon
- **Replaces:** Tycoon's S6 shell (`tycoon-worktrees/shopify-shell/packages/shell/src/shells/s6/`), its Organizations and Deals index pages, which copy Shopify admin's (Polaris' IndexTable in a Card, IndexFilters, the metric strip); Zach's screenshots of 2026-10-28.
- **Shows:** `<data-summary for>` and the top-level `summary:` (counts, `filters`, `when`, Earliest), `frame="card"`, `search="expand"`, `views="dropdown" promote=""`, `selectable`, the `avatar` and `date` displays, `maxBadges`, `pageSize`, and `<data-rail>` with `data-badge` and sub-destinations (`data-parent`) on the app page. All of these are docs/CONTRACT.md §43, not landed.
- **Data:** `organizations.json` and `deals.json`, invented by `source/build_data.py` (no real organization, place or deal).
- **Skin:** `skin.css`, Polaris' light and dark tokens (as Tycoon's S6 copies them) mapped onto `--data-*`.
