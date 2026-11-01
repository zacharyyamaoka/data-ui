# robotparts sources

Every source robotparts.dev holds an asset from, grouped by kind, with a stale badge where an asset or a link check
has aged past its kind's threshold: the freshness table, in a `.base` file.

- **App:** robotparts
- **Replaces:** robotparts' hand-rolled `/sources/` page: `sources_page()` in `build/site_pages.py` in `~/robotparts`
  (the table, its facet form and its counts) and the freshness script in `site/static/site.js` that adds the
  "needs refresh" badges in the browser. Here the table, the grouping, the rail and the badges are the kit's.
- **Shows:** the table grouped by kind with Sum summaries, a badge column whose colour is a slot (`colors`), a preset
  that filters to what needs a refresh, the `list` view of the same rows, and the `record` view as a source page.
- **Data:** `sources.json`, 43 of the release's 196 sources (at most 8 per kind, oldest access first), written by
  `source/make.py` from robotparts' `dist/site/v2/sources.json` (release 2026.10.25.1). The verdict is
  computed once, there, with freshness.toml's thresholds, as of 2026-11-25: one month after the release, so prices
  and software readings (stale after 30 days) have aged out. On the release day itself every source reads fresh.
- **Skin:** `skin.css`, robotparts' token mapping.
