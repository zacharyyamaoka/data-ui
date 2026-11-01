# Actuators side by side

Four integrated actuators from robotparts.dev's catalog in columns, one line per spec: the better value of each spec
marked by its direction, "Differences only", the robotparts photos in a slider, and a column you can drop or add from
the six in the file.

- **App:** robotparts
- **Replaces:** robotparts' hand-rolled compare page, `/search/compare/` (`site/static/site.js` in `~/robotparts`,
  `compare()`, about 150 lines, and `build/site_pages.py`, `compare_page()`): a fetch per part, a table built by
  hand, a "(remove)" link that rewrites the query string. Here the same side by side is a `compare` view in a
  `.base` file, and a pick is a view you can save.
- **Shows:** `type: compare` (best values by `better`, differences only, the photo slider, add and remove), `type:
  record` with sections (the part page), a table of the same six rows.
- **Data:** `compare.json`, six rows written by `source/make.py` from robotparts' `dist/site/v2/catalog.json`
  (release 2026.10.25.1) through robotparts' own build helpers; each value keeps its basis and source. The photos
  (`photos/*.webp`, relative to `compare.json`) are robotparts' hosted copies, copied here so nothing loads from another
  site.
- **Skin:** `skin.css` is robotparts' token mapping (the actuators case's), light and dark.
