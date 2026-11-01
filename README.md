# data-ui

A drop-in kit for viewing any data in Zach's apps:

- **framework-free custom elements**: `<data-views>`, `<data-facets>`, `<data-value>`, `<data-kpi>`, `<data-sparkline>`;
- **one view grammar**: Obsidian Bases `.base` files, with Vega-Lite inside `chart:`;
- **`--data-*` tokens** that default to shadcn's CSS variable names.

React apps use the same tags. A static gallery of real cases is its docs site and its test suite. It is not a standalone app.

**Status (2026-10-31):** version 0.1.0, moving fast, with no compatibility promise until 1.0. There are 30 view types
(table, pivot, list + tree, record + form, compare, cards + media grid, kanban, chart, KPI, calendar, timeline, graph via
React Flow, map and more) and 86 gallery cases. The site has a landing page with a live five-view hero and a gallery
grouped by app. Development happens in `~/data-ui`, a private repository. The public repository
(github.com/zacharyyamaoka/data-ui) is a snapshot of it, not its history; `docs/PUBLIC-REPO.md` says why.

- **The contract every view builds on:** [`docs/CONTRACT.md`](docs/CONTRACT.md). Why it is shaped so:
  [`docs/peps/0001-data-ui-shape.md`](docs/peps/0001-data-ui-shape.md).
- The design: [`docs/SPEC.md`](docs/SPEC.md); the per-view build spec: [`docs/VIEWS.md`](docs/VIEWS.md).
- The map gallery's data keep their own licences, not the code's: [`docs/MAP-DATA.md`](docs/MAP-DATA.md).
- Moved in from robotparts `lane/tables` @ `ab5ba92`: `grammar.js` (now the core's), the table and pivot (now
  `packages/views/table/`), the presets and the datasheet snapshot (now the gallery's cases).

## Use it

```
npm --prefix ~/data-ui run build      # dist/: data-ui.js, data-ui.css, views/, resize.js, sources.js, python/, LICENSES.md, manifest.json, site/
npm --prefix ~/data-ui test           # build, unit (node --test), Python, browser checks
npm --prefix ~/data-ui run serve      # the docs site on 127.0.0.1 (4610, or the next free port)
node ~/data-ui/tools/serve-md.mjs <folder> --port 4531   # a folder of .md notes as a table and pages (docs/CONTRACT.md §46)
npm --prefix ~/data-ui run deploy     # data-ui.dev: clean main, full suite, redact + scan, wrangler, live check
node ~/data-ui/bin/data-ui.mjs check views.base --data data.json
```

```html
<link rel="stylesheet" href="vendor/data-ui/data-ui.css">
<script type="module" src="vendor/data-ui/data-ui.js"></script>
<data-facets for="parts"></data-facets>
<data-views id="parts" src="actuators.base"></data-views>
```

## Use it in an app

Vendor a build into the app and pin it. A copy is replaced whole, never edited.

```
node ~/data-ui/bin/data-ui.mjs vendor main --into site/static/data-ui                       # everything
node ~/data-ui/bin/data-ui.mjs vendor 1.2.0 --into vendor/data-ui --views table,cards,chart  # a release, a few views
```

It builds from a clean archive of the commit and checks every file against the build's sha256 manifest, and it writes `VENDOR.json`
beside them. `docs/migrations/` has the move for each app. From 1.0 a page that works on 1.x keeps working on every later 1.x:
`docs/COMPATIBILITY.md` says what that covers, and `CHANGELOG.md` what changed. Third-party data keeps its own terms:
`docs/THIRD-PARTY-DATA.md`.

## Keeping it reliable

```
node tools/test-all.mjs --strict          # the whole suite; a suite that did not run is a failure
node tools/ci-local.mjs --ref main        # the same in a clean container shaped like a CI runner (docs/CI.md)
node tools/app-journeys.mjs --ref main    # each app's own main journey against this build, in a temporary copy
node tools/release.mjs minor              # version, changelog, commit; refuses unless all of it is green on a clean main
node tools/history-scan.mjs --ref main    # what a push would publish (docs/PUBLIC-REPO.md)
```

## Editing a dashboard

`<data-dashboard src="x.base" editor>` adds Edit: panels drag and resize where they sit, the outline beside them reorders, hides
and groups them, one options pane changes the selected one, and a short queue holds what Add to dashboard collected. Save shows
the diff first and hands the host the text (`data-dashboard-save`, docs/CONTRACT.md §41, docs/peps/0017-dashboard-editor.md);
data-ui never writes a file, and every edit keeps the file's comments and lines as written.

## The toolbar

`toolbar="full"` (the default) is the row of words it always was. `toolbar="bar"` is the newer chrome (docs/CONTRACT.md
§15, docs/peps/0002-toolbar.md): one quiet row with the view chip or tabs, the table's own query bar, the filter
control and Display, then filter pills or a bulk bar. Its variants are attributes:

```html
<data-facets for="parts"></data-facets>
<data-views id="parts" src="actuators.base" toolbar="bar" views="auto" filters="pills rail" display="panel" selectable></data-views>
```

- `views="auto|dropdown|tabs"`: Bases' chip with its view menu, Notion's tabs with "N more…", or tabs while they fit.
- `filters="pills expanded query-tokens rail"`: pills under the bar, Obsidian's Sort · Group · Filter · Properties
  words, tokens in the query box, a Filters toggle for the rail. All of them edit the one filter the rail and the URL
  carry.
- `display="panel|popover"`: Notion's resizable View settings panel, or a popover.

The gallery shows them as `toolbar-bar`, `toolbar-notion` and `toolbar-obsidian`.

## Editing

`editable` makes the table's cells editable in place (docs/CONTRACT.md §37). `edit-toggle` adds a quiet Edit / View switch and, in Edit, what
makes it a Notion table (§40): delete a row (no dialog, an Undo toast), undo and redo, paste a block from a spreadsheet, and add, rename,
retype, hide or delete a column from its header. The page opens in View, a read-only table to the byte. Every write goes through the
page's hooks (`acceptEdit`, `acceptAdd`, `acceptDelete`, `acceptProperty`, `acceptBatch`); with none, an editable page keeps it in memory.

## Layout

- `packages/core/`: the framework-free core (one bundle); `packages/core/python/data_ui_base.py` reads `.base` in a
  stdlib Python build.
- `packages/views/<view>/`: one folder and one lazy bundle per view; `table/` is the reference plugin.
- `gallery/examples/<case>/`: data + `views.base` + optional schema and skin + README (+ `checks.py`).
- `dist/sources.js` (`packages/core/src/sources-menu.js`): right-click / long-press / Shift+F10 on any `data-provenance` element (a rich cell's value, a photo, a file link) opens "where this value comes from"; load it beside the kit or alone (`docs/CONTRACT.md` §22).
- `packages/core/src/precedence.js`: a value several sources state (`{sources: [rich cell + source id, …]}`) unfolds to one ordinary column per source, and the value is a formula over them, the left-most filled one, by an evidence ladder or the reader's own column order and per-row picks. A `.base` can state the same formula over any columns (`docs/CONTRACT.md` §36, `docs/peps/0021-source-columns.md`, `docs/migrations/source-columns.md`).
- `site/`: the landing page (its hero is `site/hero.base`), the gallery and the views list (`dist/site/`).
- `schemas/view.schema.json` and `tools/check_views.py`: the grammar for agents and the Python checker.
- `examples/`: the SPEC's worked `.base` files (cards, charts, KPI, kanban).
- `docs/views/`: the views catalogue's builder and its demo (its own `node_modules`).
