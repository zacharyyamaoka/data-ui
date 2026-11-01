# summary

The summary card (docs/CONTRACT.md §43): one rounded card holding a few metrics side by
side, hairlines between them, as Shopify admin's metric strip and Tycoon's S6 shell draw it. Each cell is a label whose
dotted underline gives its definition (the cell's `note`), the value, and, only when the cell has a series, a sparkline
and its change against the bucket before. A click opens the cell's rows in the peek.

```yaml
summary:                       # at the top of the .base: <data-summary for="views-id">; on a view: type: summary
  scope: all                   # all (default): the file's rows; filtered: what the all-views filter leaves (never the search)
  cells:
    - label: Open deals
      note: Deals that are neither won nor lost.
      filters: 'stage != "Won" && stage != "Lost"'
    - label: Next due
      filters: 'stage != "Won" && stage != "Lost"'
      when: { property: due, is: upcoming }      # today | this-week | this-month | this-quarter | this-year | past | upcoming
      value: { property: due, summary: Earliest } # count (default) | {property, summary}: Bases' summaries, Earliest, Latest
    - label: New this year
      spark: { x: created, grain: month }        # the same value per month: a sparkline and "+2 vs Sep 2026"
```

**On a page:** load `data-ui.css`, `data-ui.js` and `views/summary.js`, then place
`<data-summary for="orgs"></data-summary>` beside `<data-views id="orgs" src="orgs.base">`. It reads that element's file
and redraws on its changes. **Stock part:** none (an SVG polyline); the numbers come from the core's grammar
(`compileFilters`, `summarize`, `timeBucket`). Tests: tests/unit/summary.test.mjs; the admin-shopify gallery case.
