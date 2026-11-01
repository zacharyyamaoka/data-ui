# Changelog

What changed for a page or an app using data-ui. The promise each release keeps is in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md). `tools/release.mjs` turns **Unreleased** into a release: write here as you
land, one line per change a host could notice, and name the contract section.

## Unreleased

Everything since the kit began. 1.0.0 is the first release with a promise; until then `main` moves freely.

### Changed

- **Source columns (§36, PEP 0021, `docs/migrations/source-columns.md`).** A value's `sources` list unfolds to plain columns, `<property>@<source>`, and the value is a
  formula, the left-most filled one: hide, width, sort and filter are ordinary, a header drag is the precedence, and hiding a source changes no value. No data file changes.
  **Gone:** Manage sources, `el.manageSources`, its toolbar buttons and count, the ‹ › and the source header's rank and link: a `Sources` view takes their place, and Alt+arrows on any
  header move a column. **Moved:** the agree / differs pill is on the value's cell, `@source` is `<property>@source`. A reader's links and storage hold.
- `formulas:` runs one formula, for display columns: `[a, b].filter(!value.isEmpty())[0]` over any columns, in Bases' own spelling. Any other shows a dash and says it needs Obsidian.
- A source's own column edits; `acceptEdit` hears the stored property, whole. A whole new `sources` list is no longer refused; a value set on such a cell still is.
- A header's words no longer hold a column open: they widen a column nobody has sized, up to 240 px, and never block a drag (§28).

### Added

- `persist="page"`: the view per page path and data id, the widths per data id; for pages that share one data id (§37).
- A markdown cell edits in the Sheet by default: a side panel that follows the cell you click (another row moves it, it does not close), autosaves 0.7 s after the last key, drags on its left edge with the width remembered, and refuses to save over a change made elsewhere (*Use theirs* / *Keep mine*). `el.cellSurface = 'grow'` or `cell-surface="grow"` keeps the old grow-in-place (`docs/CONTRACT.md` §46).
- The inspector is one property per row, 1:1 with the view's columns, the rest behind "N more properties"; no chips, no Specs / Sources tabs (the
  Sources list is a folded pane). A visible column with an empty value now shows a dash. `record.visibility: {<property>: show | hideEmpty | hide}`
  sets the inspector apart from the row; `.dv-peek-slot` under the properties; an optional view method `drawnColumns()`; Add a property
  with `acceptProperty` (`docs/CONTRACT.md` §44).
- Tables: every column resizes, with a line on the boundary; double-click fits the widest value, and a cut-off value shows whole on hover (CONTRACT §45).
- `path:` on a group level: `groupBy: {property, path: dotted}` nests to any depth in table, list and cards, counts rolled up (CONTRACT §45).
- The `markdown` property type: a cell that summarises raw markdown (sub-headings or first lines, small thumbnails) and edits it raw on a click; `columns: h1` makes each H1 of one value a column; a dataset's `defaultSort`; Open in › on a table row's right-click menu, with submenus in the item menu; `el.pageRenderer`, a host's own page in the side panel (CONTRACT §46).
- A record's page, laid out apart from the table: the `.base` key `page:` gives each property its order, visibility and place (the property list,
  or a section, one H1), with a menu, drag and keys on the page; `el.acceptPlace`, `el.resolveMedia`, `el.resolveLink`, `el.openElsewhere`, `el.setPlace`, `el.pageFull`, `display: outline` and
  `display: preview` for a section's generated cell, and `pageBody: true` for the free text, always last. A page with no `page:` key and no `pageBody` draws as before. The first
  backend is `tools/serve-md.mjs`: one row = one `.md` file (`docs/CONTRACT.md` §46).
- `<data-dashboard editor>`: a dashboard's own editor. Edit in place of Arrange, drag and resize on the grid, an outline, one options
  pane, a queue from the `dashboards()` entry marked `queue: true`. Save shows the diff, then `data-dashboard-save` hands the host
  the text; `el.edit()`, `el.editing`, `el.baseText`; a layout panel's `hidden: true`; `dist/dashboard-edit.js`. A dashboard with no
  `editor` draws as before (`docs/CONTRACT.md` §41).

- Property types (§28): `.base` `properties.<p>.type`, Notion's types plus `rating`, `currency`, `percent`, `duration`, `relation`, `rollup`,
  `formula`, `id`, `created_time`, `edited_time`, with `icon`, `description` and each type's options. A type changes how a value is drawn,
  never the value: its hover and the peek say it as stored. `dist: strip | box | violin`, `freeze: <property>`, `wrap: [p]`, a Calculate
  footer from `summaries`, `before:` / `after:` Markdown blocks.
- Notion's column menu on every table and pivot (§28): Filter, Sort, Calculate, Roll up, Freeze, Hide, Wrap in view; on a page you can edit,
  name, icon, Edit property, Change type, Insert, Duplicate, Delete, written line by line into the `.base` text (`el.baseText`,
  `data-views-base`, `el.editProperty({action, …})`; `{op, …}` stays §40's). **A header click now opens it; shift-click sorts.**
- The table's lines (§28): every cell draws its dividers, a header cell is never blank, a column is never drawn narrower than its content.
  `intro.text` moves from the view into its ⓘ About note (status line); `intro.kpi` stays.
- The admin look (§43): `type: summary` and `<data-summary for>`, one card of cells counted from the rows; `frame="card"`; `search="expand"`;
  table `display: avatar | date`, `maxBadges`, `pageSize` with its pager; `<data-rail>` `data-badge` and `data-parent`; `shortDate`; the
  `admin-shopify` case.

### Map

- An analysis surface (CONTRACT §42, PEP 0011): `layers:`, `space:`, `time:`, `multiples:`, `swipe:`, `draw:`, `legend:`, `pitch:`,
  a self-hosted `.pmtiles` basemap, 20 `gallery/examples/map-*` cases. A map view with no new key gains a scale bar.
- `select:` picks and marks on every clickable layer; a cluster zooms, and rings pick from their legend (§39, §42).
- A `markerColor` property has a legend. A data file's `attribution` is drawn in the map's credit (`input.dataset.attribution`),
  which stays open: OpenStreetMap must be credited on the map (`docs/MAP-DATA.md`).

### Fixed

- An edit of a rich cell that carries `text` drew the old words over the new value; the edit is kept and the words go (`withValue`, §40).
- A lineage view draws every link as one curve, a tree edge, a "+N" stub and a splice alike; a splice stays dashed. Extinct lines stay
  folded by default, now pinned (§21).
- A long unbroken value in the side peek wraps in the fields and is cut with an ellipsis in its key chip, so the peek never scrolls sideways.
- `<data-views>`: a view still loading never mounts a model older than the one asked for (a filter typed during a slow load showed the old
  rows); a host's own rows stay until the new view has drawn; a failure that arrives after a newer draw leaves that draw alone.
- `<data-facets>`: a date preset's count moves when its bound does, at local midnight and across DST (23:00 / 01:00), never yesterday's.
- A `groupOrder` that repeats a name keeps an empty group last.

### Tooling

- `bench/`: a noisy machine is judged on the CPUs the bench is pinned to, per sample, not the host's load average; an unstable app is a
  result, not noise; a timing that had to be set aside fails `timing_valid` for that build. `bench/ab.py`: interleaved A/B runs with a
  verdict per metric.
- `data-ui vendor <version|ref> --into <path>`: one vendor command for every app, built from a clean archive of the ref,
  checked against the build's sha256 manifest, recorded in `VENDOR.json`, with view subsets. It replaces each app's own
  `tools/vendor_data_ui.py` (`docs/migrations/`).
- `tools/app-journeys.mjs`: each app's main journey against a candidate build, in a temporary copy.
- `tools/release.mjs`, this file and `docs/COMPATIBILITY.md`.
- CI: `.github/workflows/ci.yml`, `tools/ci-local.mjs`, `tools/cross-browser-smoke.py`, and `node tools/test-all.mjs --strict`.
- `tools/history-scan.mjs` and `tools/public-export.mjs`: what a push would publish, and a snapshot that is safe to
  (`docs/PUBLIC-REPO.md`). MIT `LICENSE`; `docs/THIRD-PARTY-DATA.md`.

## 0.1.0 (unreleased, 2026-10-25 to 2026-10-30)

The kit as five apps use it today, pinned by commit, with no version promise.

- **Elements:** `<data-views>`, `<data-facets>`, `<data-value>`, `<data-kpi>`, `<data-sparkline>`, `<data-dashboard>`,
  `<data-analysis>`, `<data-rail>`, `<data-mesh>`.
- **Grammar:** Obsidian Bases `.base` files, with Vega-Lite inside `chart:`; `schemas/view.schema.json`, `data-ui check`.
- **Views:** table, pivot, list and tree, record and form, compare, cards and media grid, kanban, chart, KPI, calendar,
  timeline, graph, map, lineage, source, live plot, playback, 3D scene, trajectory, voxels.
- **Contract:** `docs/CONTRACT.md` §0 to §38.
