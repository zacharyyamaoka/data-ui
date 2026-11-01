# PEP 0003: how a record opens (open modes)

- **Status:** accepted, 2026-10-26 (shipping approved by the coordinator; lands with lane/open-modes)
- **Decided by:** Zach, on the open-patterns prototype (data-ui lane/open-patterns @ fd607ff, five switchable patterns,
  report `~/robotparts/reports/media/data-ui-open-patterns-2026-10-26.html`) and the cited sweep in the vault
  note *C - Peek vs Drill-down (record opening patterns)* (2026-10-26)
- **Code:** packages/core/src/open.js, packages/core/styles/open.css; docs/CONTRACT.md §13 (amendment 2026-10-26 (open
  modes)); the robotparts-actuators gallery case

## Context

Every list of records has to answer one question: what does touching an item do? data-ui had one answer, a click opens
the side peek, with no way to reach the record's own page, no URL for the peek and no answer on a phone. robotparts
needs a real page link (McMaster muscle memory: part pages, Back to results), the spec-heavy views want the specs in
the list, and other hosts want the peek they have today. The prototype lane built five ways a record opens behind a
switch so Zach could compare them in place.

## Decision

1. **One setting, three modes, per view.** `open: expand | side | link` on a view, with a file-level default (a
   top-level `open:` and the `<data-views open="…">` attribute) and `side` when nothing is set. Like Notion's per-view
   "Open pages in" [2](https://www.notion.com/releases/2022-07-20), [1](https://www.notion.com/help/views-filters-and-sorts),
   because forcing one peek mode on every list backfires: Atlassian made the work-item preview panel mandatory and had
   to add an opt-out [38](https://jira.atlassian.com/browse/JRACLOUD-96809).
   - **expand**: a band under the row, several at once (McMaster's in-place detail; AG Grid master/detail).
   - **side**: the side peek with a "full page" link inside it, the convergent default of Notion, Jira, Attio and
     HubSpot [3](https://www.notion.com/help/intro-to-databases), [36](https://support.atlassian.com/jira-software-cloud/docs/preview-work-items-in-jira-search-and-the-list-view/),
     [42](https://attio.com/help/reference/managing-your-data/records/create-and-view-records), [41](https://knowledge.hubspot.com/records/preview-a-record).
   - **link**: the row is a link to the record's page (Shopify's IndexTable [25](https://raw.githubusercontent.com/Shopify/polaris-react/main/polaris-react/src/components/IndexTable/components/Row/Row.tsx);
     Baymard's answer for spec-driven lists, where quick views are mostly ignored [B3](https://baymard.com/blog/ecommerce-quick-views)).
2. **side is responsive, not a fourth mode.** One setting covers the width: a split view (the list narrows beside the
   pane) when the element is at least `splitAt` px wide (default 1100), the overlay below that, full screen with a Back
   on a phone, as Material 3's list-detail and Windows' list/details stack on narrow windows
   [G2](https://developer.android.com/develop/ui/compose/layouts/adaptive/canonical-layouts), [MS1](https://learn.microsoft.com/en-us/windows/apps/design/controls/list-details).
3. **A real link underneath every mode.** When a record has a page URL (`open.url`, else the dataset's `linkProperty`)
   its title is a real `<a href>`, so ⌘/middle-click and "copy link" work: people park pages in tabs to compare them
   [N2](https://www.nngroup.com/articles/multi-tab-page-parking/), and a click handler on a `<tr>` can never offer that
   [T1](https://tempertemper.net/blog/clickable-table-rows-are-a-bad-idea), [R1](https://adrianroselli.com/2023/11/dont-turn-a-table-into-an-aria-grid-just-for-a-clickable-row.html),
   [P1](https://inclusive-components.design/cards/). A double-click and Enter open the page; no URL, no drill-down.
4. **Double-click is only an accelerator.** It repeats or advances the single-click action and always has a keyboard
   equivalent (Enter), because a pointer-only handler fails WCAG 2.1.1 [W1](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html);
   nobody's web docs use double-click to open a record, and many people double-click links anyway, so every open is
   idempotent [N1](https://www.nngroup.com/articles/when-to-open-web-based-applications-in-a-new-window/), [B1](https://baymard.com/research-articles/people-still-double-click-online).
   Rows are `touch-action: manipulation` [M1](https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action).
5. **The peek is in the URL and Back closes it.** `peek=<id>` is pushed on open and replaced while stepping, because
   people press Back to leave anything that looks like a new place [N3](https://www.nngroup.com/articles/user-control-and-freedom/),
   [N4](https://www.nngroup.com/articles/overuse-of-overlays/), [B2](https://baymard.com/blog/mobile-desktop-quick-views),
   and GitHub Projects and Airtable deep-link to the peeked record [21](https://github.blog/changelog/2023-01-05-github-issues-january-5th-update/).
   ↑/↓ (and j/k) walk the records inside it, with "n of N", as Linear, Notion, Airtable and Attio do
   [14](https://linear.app/docs/peek), [4](https://www.notion.com/help/keyboard-shortcuts), [7](https://support.airtable.com/docs/airtable-keyboard-shortcuts).

## The two patterns dropped

- **Select + Quick Look** (Finder, Linear): a click only selects and Space opens a centred dialog
  [AS1](https://support.apple.com/guide/mac-help/open-documents-mchl971293e1/mac), [AS2](https://support.apple.com/guide/mac-help/view-and-edit-files-with-quick-look-mh14119/mac).
  On the web a click that "does nothing" reads as broken, and Space is the only way in, which nobody discovers; it is
  a desktop file-manager idiom.
- **Always-on split view** (Mail): the pane is open from the start whatever the width. It costs the list its width on
  every visit, which is what Atlassian's forced preview panel did before its opt-out [38](https://jira.atlassian.com/browse/JRACLOUD-96809).
  The split survives as `side`'s wide layout, opened by a click, closed by Esc or Back.
- Also gone from the prototype: the kit's own full-page record view (`rec=`; the page is the host's real URL now) and
  the temporary switcher on the gallery page.

## Consequences

- One key a host can set per view; robotparts configures `side` for browsing, `expand` where specs matter in the
  list, `link` for spec catalogs, without forking the kit.
- The peek's content is richer for every view (photo, `n of N`, key specs, Open page), and still the host's own fields
  underneath, so `record.sections`, `edit: true` and the records behind a pivot cell are unchanged.
- A phone's side peek is now full screen (it used to fill only the element); the actuators case's 390 px resize check
  was updated to say so.
- A view plugin that draws records reads `host.opener` (CONTRACT §13) for the title link, the row marks and expand's
  band; the table and cards views do, others open the side peek as before.
- The checkers know `open:`: an unknown mode is an error; `link` with no URL anywhere warns and falls back to `side`.
- Not decided here: a formula as the URL (formulas are not evaluated in v1), and selection doing anything beyond
  "N selected" in link mode.

## Alternatives considered

The five prototypes (side peek, select + Quick Look, row is a link, split view, expand in place) were built and
compared in the open-patterns report; the vault note's table scores their axes (single-click, page, where the detail
sits, selection, URL / Back, phone). Keeping a single fixed peek (today's) was the null option.
