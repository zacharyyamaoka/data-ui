# data-ui: file-first data views (spec, 2026-10-25)

> Working name **data-ui** (Zach, 2026-10-25). The repo is `~/data-ui` (renamed from
> `~/data-ui` on 2026-10-25). Local git, no remote. Status: spec plus two small proofs (`tools/`), no app code. It builds on
> the table lane (robotparts `lane/tables` @ `ab5ba92`, not merged) and the reuse survey
> (`~/robotparts/reports/media/reusable-components-2026-10-25.html`).

## 1. The answer

**data-ui is a drop-in kit, not an app.** It is framework-free custom elements, one view grammar and one token
contract. Every view of any data in Zach's apps comes from those three parts. A static gallery doubles as its docs
and its test suite.

1. **It is not new work: it converges five partial copies.** These are:
   - the table lane's `<data-views>` (landed, 22/22 checks);
   - the survey's KPI kit and atlas kit (proposed);
   - robotparts' hand-rolled Rows / Gallery / Chart and McMaster rail;
   - Vibe Tracks' views, cards and Perspective pivot;
   - Clank's `clank.base` plugin.

   The risk is not failing to build it. The risk is building a sixth copy.
2. **Shape:**
   - custom elements under one `data-` prefix (`<data-views>`, `<data-facets>`, `<data-value>`, `<data-kpi>`, `<data-sparkline>`);
   - Obsidian Bases `.base` files as the view grammar, with Vega-Lite's vocabulary inside a `chart:` block;
   - `--data-*` tokens that default to shadcn's variable names.

   React apps use the same tags.
3. **Stock engines, thin glue:**
   - TanStack Table v9 for tables and pivots (landed).
   - Vega-Lite for every chart: one engine, not three.
   - Plain JS arrays in the browser. DuckDB runs only at build time.
4. **Clank:** data-ui is neither a Clank plugin nor a standalone app. Clank and Obsidian become thin hosts later, so no new shell.
5. **The files are the agent interface.** There is no AI inside. A JSON Schema and a checker make a `.base` file safe for Claude Code or Codex to write, and the page re-renders when the file changes.

Zach's framing, which this spec builds on (2026-10-25):

- "It's for file-first design software. It's functional. What goes in is csv, or some type of file, and then I can view it in any number of possible views."
- "Why dataset? It should work for any data."
- "I don't think I'll ever use it as a standalone application. It's basically a drop-in shadcn-type thing for my applications."
- "There's a set number of things I can learn and then reuse for the rest of my days."
- "Instead of integrating the AI, I can just use my normal Claude Code, and if it's local, like Obsidian, it can edit it locally."

## 2. What the brief assumes, and where I disagree

| The brief says | What the code and the vault say | So |
|---|---|---|
| "A generic library I make for myself" | Most of it already exists, in five places:<br>• the table lane's `views/` (grammar.js 277 lines, views.js 782, 36 KB gz);<br>• robotparts' `site.js` (1,033 lines: rail, Rows/Gallery/Chart, scatter);<br>• Vibe Tracks' `views.js` / `cards.js` / `pivot.js` (1,863 lines);<br>• Clank's `src/plugins/base/` (2,735 lines incl. tests, a third Bases evaluator);<br>• the survey's proposed `bam-kpi` and atlas kit. | data-ui is the place these converge. The first step is a move, not a build. |
| "The shadcn model" | Copy-in is how drift happens here:<br>• Tycoon copied 30 Clank kit parts at `9859de0`;<br>• shadcn exists seven times across the apps (survey). | Take shadcn's **token contract** and its **registry delivery**. Copy-in is only for skins and recipes. The engine and grammar are one pinned copy, re-vendored to update, never edited in place (§10). |
| "A standalone app; its gallery page shows the cases" | Zach: "I don't think I'll ever use it as a standalone application." An app that opens arbitrary data files is a new shell, the thing Clank's rule forbids. | The gallery is a static docs site (data-ui.dev if he buys it) of real cases. Opening local files is a later Clank or Obsidian host (§12). |
| "CSV may not be sufficient for images" | Images are a column type, not a file format. | A CSV with a `photo` column of paths, typed `format: uri, media: image` in the field schema (§4). |
| "Filters like Obsidian, or McMaster's left bar" | These are not alternatives. They are two editors of one filter, but the rail can only draw part of a filter. | One stored filter. The rail edits its facet-shaped part, and the rest stays custom, never dropped. Proved (§6). |
| "Any number of possible views", "almost like Excel" | The lane found that Notion-style freedom costs decisiveness: each reader rebuilds the view. | Seven layouts, presets first, customisation as the escape hatch. A new layout needs a gallery case that none of the seven can serve (§14). |
| Chart engine: the survey says ECharts | The Vibe Tracks drill-down and three atlases use ECharts. But the vault chose Vega-Lite for configurable charts on Oct 5 (model canvas), partly because "the spec has a published JSON Schema (v6), so an AI can write a chart and have it validated". | One engine for every data-ui chart: **Vega-Lite**, because the chart lives in a file an agent edits (§8). ECharts stays inside Vibe Tracks' fixed drill-down until a measured reason to move. |
| Tokens: the survey says vanilla apps alias shadcn's names | robotparts' and Vibe Tracks' `--accent` is a strong blue (`#0a5bb5`, `#2a78d6`). shadcn's and Clank's `--accent` is a hover fill (`#e5e5e5`, `focus:bg-accent`). Aliasing at `:root` would break one of them. | A private `--data-*` layer that *defaults to* shadcn's names. A shadcn app needs zero lines; a vanilla app maps `--data-*` from its own names (§10). |

## 3. Criteria (weighted, before any option)

| # | Criterion | Weight | Why, in Zach's words or his rules |
|---|---|---|---|
| C1 | Learn once: one grammar for every view of any data | 20 | "a set number of things I can learn and then reuse for the rest of my days" |
| C2 | Runs where the views live. That means:<br>• Python-built static robotparts (no React, no other origin, a complete no-JS page);<br>• vanilla Vibe Tracks;<br>• React apps;<br>• Obsidian. | 20 | The two most active data apps are non-React (survey; `git log` of both on Oct 25) |
| C3 | Stock engines, the smallest glue | 15 | about-me: off-the-shelf first |
| C4 | Files are the interface: a documented grammar, a schema, readable errors, re-render on change | 15 | "bring your own AI agent" (Oct 25) |
| C5 | One copy of the engine and grammar, never frozen forks | 10 | Clank's C1: "every copied shell froze at one version" |
| C6 | Truthful and calm: presets first, "not measured" never 0, basis shown, view numbers labelled "from rows" | 10 | calm UI; truthful rendering; Vibe Tracks' "never computes a headline" |
| C7 | Fits a phone page: bytes, no sideways scroll | 5 | robotparts' tests |
| C8 | A first slice that proves it in days, on real data | 5 | speed |

## 4. Input contract: any data that reads as records

"It should work for any data." The contract is the smallest thing every form shares: **records (objects) with
fields**. A field schema is optional, and inference is the fallback.

### 4.1 Forms

| Form | Typical source | How records arrive |
|---|---|---|
| JSON: a list of objects, or `{schema, rows}`, or the element's runtime shape `{properties, rows}` | Python builds (robotparts), producers | read as is |
| CSV / TSV / JSONL plus an optional `<name>.schema.json` | benches, scripts, exports | a ~2 KB loader; types from the schema, else inferred |
| One object (a single part, a config) | a part's specs, a dataclass | one record per key: a property sheet, which is what the datasheet view is |
| A folder of `.md` notes with frontmatter | the vault, a Clank workspace | the host lists the files (Obsidian's Bases, Clank's `/api/fs`); `file.*` properties come from the host |
| Parquet | later, past ~50k rows | `hyparquet` (MIT, pure JS, ~291 kB unpacked) |

Rules:
- numbers are numbers;
- dates are ISO 8601;
- lists are arrays;
- missing is `null`, never `0` and never `""`.

### 4.2 The field schema: Frictionless Table Schema plus six keys

- **Fields:** each field is described with Frictionless Table Schema's vocabulary:
  - `name`, `type` (string, number, integer, boolean, date, datetime, array, object);
  - `format` (`uri` for links and media), `title`, `description`, `constraints`, `missingValues`.
  - Source: datapackage.org v2, the stock standard for "a CSV plus types". It needs no dependency to read or write.
- **data-ui adds six keys:**
  - `unit`;
  - `display` (the default cell display);
  - `facet` (`values | range | has | none`);
  - `media` (`image | video | file`, on a `format: uri` field);
  - `basis` (a column default, §9.2);
  - `derived` (a note saying how the producer computed it).
- **Example:** `examples/actuators.schema.json`.
- **Images:** a path relative to the data file, or a URL. robotparts' photos and drawings, and bench failure media, are all just columns.

### 4.3 Rich cells: a value with provenance

A cell is a scalar or `{value, unit?, basis?, source?, sourceUrl?, sourcePage?, asOf?, record?, low?, high?, n?, note?, text?}`.

- Grouping, sorting and filtering read `.value`. `text` is a display string the producer wrote ("15 to 60" for `[15, 60]`): every view draws it as written and nothing else reads it (CONTRACT §22).
- A missing value carries its reason, `{value: null, why: "not measured" | "not published" | "not found"}`. It renders "—" with the reason on hover.
- This is the survey's "value with provenance": built 9 times in 7 vocabularies. Here it is built once, as `<data-value>` (§9).
- A value several sources state is `{sources: [<rich cell + source id>, …]}`; the dataset may name its `sources` and an evidence `ladder`. Every view reads one nominal: the row's own pick, else the first source in precedence order (the ladder's by default) that states it. The table names the nominal's source beside it and can show one column per source to reorder them (CONTRACT §36, PEP 0015).

### 4.4 Where computing happens

- **In the browser, on plain arrays: filter, sort, group, pivot and summaries.** The lane measured 41 ms to regroup 1,149 rows. Up to ~50k rows is an estimate to measure, not a fact.
- **At build time: joins and heavy aggregation.** This is Python, with DuckDB's Python package where a producer needs it.
- **DuckDB-wasm is never on a public page.** Its `eh` build is 35.66 MB raw (jsDelivr listing, 1.29.0). It is an opt-in adapter for local hosts with big Parquet.
- **The truthfulness boundary (Vibe Tracks P6):** a data-ui summary is a *view* summary, labelled with its aggregation and n ("median of 14 runs · from rows"). A headline KPI is the producer's number, carried in the data and never recomputed by a view.

## 5. The view grammar

### 5.1 One file, Obsidian's grammar

A page's views live in one `<name>.base` YAML file.

- **Every Obsidian Bases file is a data-ui view file.** Proved: the schema accepts all 109 `.base` files in Zach's vault, with 0 errors and 0 warnings.
- **Obsidian keeps data-ui's extra keys when it rewrites the file.** I read this from Obsidian 1.14.5's own serializers (`~/.config/obsidian/obsidian-1.14.5.asar`):
  - unknown top-level keys go into `unrecognizedData` and are written back first;
  - per-property and per-view unknown keys are written back too.

  Runtime round-trip is not tested yet; it is in the first slice's checks.
- **Obsidian drops YAML comments when it rewrites.** data-ui's own writer keeps them, editing the YAML document in place the way Clank's `baseModel.ts` already does.

### 5.2 Bases keys (their Bases meaning)

- **Top level:** `filters`, `formulas`, `properties.<p>.displayName`, `summaries`, `views`.
- **Per view:** `type`, `name`, `filters`, `order`, `sort: [{property, direction}]`, `groupBy: {property, direction}`, `groupOrder`, `columnSize`, `rowHeight`, `summaries`, `limit`.
- **Cards (read from Obsidian 1.14.5's code):** `image`, `imageFit` (`contain`, else cover), `imageAspectRatio`, `cardSize` (50–800, default 200).
- **Types:** `table`, `cards` (1.9), `list` (1.10), `kanban` (1.14, built in), `map` (1.10, needs the Maps plugin).

### 5.3 The table lane's extensions (landed; names frozen)

- `subGroupBy`: a second group level.
- `path:` on a group level: nest to any depth from a dotted path, another separator or a list cell, on table, list and cards (CONTRACT §45).
- `splitBy` and `value: {property, summary, display}`: the pivot.
- `display: {property: number | bar | dist | sparkline | badge}`.
- `units: column | inline`.
- `fold: open | closed`.
- `type: pivot`.

### 5.4 data-ui's extensions (proposed)

- **Top level:**
  - `data:` the data this file views, relative to the file;
  - `facets:` the rail, top to bottom, each a property or `{property, as: values | range | has}`;
  - `open:` how a record opens in every view that does not say (below).
- **`properties.<p>`:** `facet` and `display` defaults.
- **Per view:**
  - `open: expand | side | link`, or `open: {mode, splitAt, url}`: how a record opens: a band under the row, the side
    peek (docked beside the list from `splitAt` px, default 1100; over it below; full screen on a phone), or the row as a
    link to the record's page (`url:` names the property, default the dataset's `linkProperty`). Default `side`. The
    view's key wins over the `<data-views open="…">` attribute, which wins over the file's top-level `open:`
    (docs/CONTRACT.md amendment 2026-10-26 (open modes); docs/peps/0003-open-modes.md);
  - `by:` and `gaps:` on a `groupBy` / `subGroupBy` level: group a date by its day, ISO week, month, quarter or year,
    in time order, keeping empty buckets with `gaps: true` (docs/CONTRACT.md amendment 2026-10-26 (time groups and
    peek trail));
  - `chart:` a Vega-Lite block (§8);
  - `guides:` `rule`, `envelope` or `indexLine` (§8.8);
  - `hover: {image, title, fields}`;
  - `kpi:` (§9).
- **New summary:** `value.summary: Ratio` with `per:`, so a cell is Σproperty / Σper. This is Vibe Tracks' ratio-of-sums KPI from PEP 0005, about 10 lines in grammar.js (the lane's estimate).
- **New types:** `chart`, `kpi`.
- **New displays:** `image`, `link`, `value`.

### 5.5 The seven layouts

| `type` | From | Draws | Stock part |
|---|---|---|---|
| `table` | Bases | rows, nested groups with summaries, sticky header, 30 px rows | TanStack Table v9 + Virtual (landed) |
| `pivot` | lane | groups × split columns, one value per cell, the records behind a cell in the peek | the lane's ~70-line transform, then the table |
| `cards` | Bases | a grid of cards with an image | CSS grid; Bases' own keys |
| `kanban` | Bases 1.14 | one column per `groupBy` value | CSS columns; drag-to-move later |
| `list` | Bases 1.10 | a compact list | later |
| `chart` | data-ui | any Vega-Lite unit or layer spec | vega-embed, lazy (§8) |
| `kpi` | data-ui | one card, or one per group | `<data-kpi>` + `<data-sparkline>` (§9) |

`map` stays Bases'; data-ui does not draw it in v1. The detail peek is a component, not a layout (§7).

The stock library for each further view type (calendar, timeline, graph, map, tree, forms, lightbox) is catalogued by another lane in `docs/VIEWS.md` (in progress, with its own measurements in `docs/views/`). These seven layouts are the core set; the catalogue says what to adopt when a case needs more.

### 5.6 Not in v1

- **Bases `formulas`:** a computed column comes from the producer, which is truthful and testable. One runs in the browser, for display columns only: the first non-empty of a list of columns, in Bases' own spelling (CONTRACT §36, PEP 0021; the Notion survey's §16, decision 1). A headline KPI stays the producer's. A view naming any other `formula.x` draws a dash that says it needs Obsidian.
- **`file.*` functions:** only for notes; the host provides them.
- **Bases' `this`:** the embedding note.

### 5.7 The agent interface (no AI inside)

- **What an agent edits:** the `.base` file. A producer edits the data and its schema.
- **What it gets:**
  - `schemas/view.schema.json` (JSON Schema 2020-12). Add `# yaml-language-server: $schema=…` for editor autocomplete.
  - The gallery's cases, as worked examples.
  - The checker, `data-ui check`, which prints one line per mistake with file, line, path and a suggestion (proof below).
  - The same errors inline on the page: the lane's status line already shows filter errors.
- **The loop:**
  1. Open the page and explore.
  2. ⋯ → "Copy as .base".
  3. Tell Claude "make this the default preset".
  4. The agent edits the file.
  5. The host re-renders: robotparts' Preview rebuilds, the gallery's dev server reloads, Clank's session or Obsidian watches the file.
- **Live control of an open page** (scroll it, open a peek) is another lane's job: "5 proposals for local-agent ↔ website bridges", `~/robotparts/reports/media/agent-bridge-proposals-2026-10-25.html` (not on disk when this was written). data-ui designs no bridge.
- **The shipped checker is a Node CLI** importing the same `grammar.js` the element runs, so the browser and the checker never disagree about an expression. The Python proof here (`tools/check_views.py`) checks shape and names only.

Proof, `python3 tools/check_views.py examples/broken.base --data examples/actuators.schema.json`:

```
examples/broken.base:3: error: filters: unknown key 'AND' (did you mean 'and'?)
examples/broken.base:11: error: views[0].chart.encoding: unknown key 'colour' (did you mean 'color'?)
examples/broken.base:12: error: views[0].chart.encoding.x.scale.type: "logarithmic" is not one of linear, log, … (did you mean 'log'?)
examples/broken.base:10: error: views[0].chart.mark: "dots" is not one of arc, area, bar, image, line, point, …
examples/broken.base:19: error: views[1].sort[0].direction: "desc" is not one of ASC, DESC (did you mean 'DESC'?)
examples/broken.base:21: error: views[2]: needs 'chart'
examples/broken.base:7: warning: views[0].type: data-ui cannot draw type 'chrat' (did you mean 'chart'?) …
examples/broken.base:17: warning: views[1].groupby: unknown view key 'groupby' (did you mean 'groupBy'?) …
examples/broken.base:12: error: views[0].chart.encoding.x.field: 'mas' is not a property of actuators.schema.json (did you mean 'mass'?)
examples/broken.base:20: error: views[1].order[1]: 'peak_torq' is not a property of actuators.schema.json (did you mean 'peak_torque'?)
checked 1 file against actuators.schema.json: 8 errors, 2 warnings
```

### 5.8 An example view file (trimmed from `examples/actuators.base`)

```yaml
data: actuators.schema.json
facets: [brand, form, drivetrain, buses, level, { property: peak_torque, as: range }, { property: mass, as: range }, { property: price, as: range }]
views:
  - type: table                      # the lane's preset, verbatim
    name: By brand
    order: [model, form, peak_torque, rated_torque, max_speed, mass, gear_ratio, voltage, od, length, buses, price]
    groupBy: { property: brand, direction: ASC }
    sort:
      - { property: peak_torque, direction: DESC }
    summaries: { peak_torque: Max, mass: Min, price: Min }
  - type: cards                      # Bases' own cards keys
    name: Gallery
    order: [model, brand, peak_torque, mass, price]
    image: photo
    imageFit: contain
    imageAspectRatio: 0.75
  - type: chart                      # inside chart: it is Vega-Lite
    name: Torque vs mass
    chart:
      mark: { type: point, filled: true }
      encoding:
        x: { field: mass, scale: { type: log }, title: Mass (g) }
        y: { field: peak_torque, scale: { type: log }, title: Peak torque (N·m) }
        color: { field: brand }
    hover: { image: photo, title: name }
  - type: chart
    name: Ashby · torque vs mass
    chart:
      mark: { type: point, filled: true, size: 18 }
      encoding:
        x: { field: mass, scale: { type: log } }
        y: { field: peak_torque, scale: { type: log } }
        color: { field: drivetrain }
    guides:
      - { envelope: drivetrain, shape: hull }
      - { indexLine: { slope: 1, through: median }, label: "constant N·m per g" }
```

## 6. Filters: one model, two editors

- **The model is the Bases `filters` tree:** an expression string, or `{and | or | not: [...]}`.
- **The builder (Obsidian style) edits any tree:**
  - groups of All / Any / None;
  - rows of property · operator · value;
  - "+ group", with a raw-expression box for anything else.

  The lane's flat Filter menu grows into this.
- **The rail (McMaster style) edits the facet-shaped part.** That part is a top-level AND of clauses, each about one property:
  - a value, or several (an or-group of `==`, or `.contains()` for a list);
  - a numeric range (`>=`, `>`, `<=`, `<`);
  - "has a value" (`!p.isEmpty()`).

  Anything else (`!=`, an `||` inside one string, a top-level or/not, two value clauses on one property) stays custom. The rail shows "+N custom filters · Edit" and never drops it.
- **The rail edits the filter that applies to every view.** That is Bases' top-level `filters`, the "All views" scope Obsidian's own filter menu offers. So a tick survives switching from the table to the chart, which is what Zach asked for: "as you filter it applies to the chart". The builder edits either "All views" or "This view".
- **Counts are disjunctive.** A facet's counts apply every other facet's selection but not its own (McMaster, Algolia).
- **Readable URLs for the facet part:** `?brand=Steadywin,CubeMars&peak_torque=10..&has=photo`. Anything else rides in the lane's base64 view blob.

**Proof:** `tools/facets.mjs` plus `node --test`, 8 of 8 pass. The oracle test does 300 seeded random rail selections on the 1,149 real actuators (the lane's built rows). Each picks exactly the rows the lane's own Bases evaluator picks, and each projects back unchanged. Changing an inclusive bound to an exclusive one turns it red (mutation run, 6 pass, 1 fail).

**Found on the way, in the lane's `grammar.js` (measured):**
- negative literals fail (`temp_min > -20` → `cannot read the filter at " -20"`);
- the bracket form `note["vibe-status"]` that Zach's own `Kanban cards.base` uses fails.

Fix both before filtering the datasheet's "Δ vs datasheet" column or any vault notes. The rail module already handles both.

## 7. Components (the public surface)

| Element / module | What it does | Status |
|---|---|---|
| `<data-views>` | The container. It holds:<br>• toolbar: view tabs; Layout, Group, Sort, Filter, Properties, **Encode** (charts), Units; search; Reset / Save view; ⋯ Copy as `.base`;<br>• the status line;<br>• the seven layouts;<br>• the peek.<br>Properties `.data` and `.views`; attributes `src`, `views` (a `.base` URL; YAML parsed in a lazy chunk), `view`, `toolbar="full\|compact\|none"`, `no-url`, `theme`; events `data-views-change {view, name, dirty}` and `data-views-open {row, column}`. | table and pivot landed; cards, kanban, chart, kpi to build |
| `<data-facets for="id">` | The McMaster rail for a `<data-views>`:<br>• facet groups with counts;<br>• a find box over long value lists;<br>• min/max boxes and "has";<br>• its own scroll, and a disclosure on a phone. | build: port robotparts' `facet_values` / `filterColumn` |
| filter builder | the All/Any/None tree editor inside Filter | build: grow the lane's menu |
| `<data-value>` | A value with provenance: number, unit, basis mark, range; source and as-of on hover. Its text content is the no-JS truth: the server writes `<data-value basis="datasheet" source="…" as-of="2026-10-22">3.82 N·m</data-value>`. | build |
| `<data-kpi>` | a KPI card (§9) | build: extract from Vibe Tracks' tiles |
| `<data-sparkline>` | ~60-line SVG line / bar / dist; no chart engine (the survey: ECharts is too heavy for twenty on a page) | extract the lane's `_sparkSvg` / `_distSvg` |
| hover card + peek | One card used by a chart's hover, a gallery card and a table row. The peek lists "every value behind it" (lane) and the media, for the drill path pivot cell → runs → media. | peek landed; hover card to build |
| `grammar.js` | filters, summaries (+ Ratio), pivot, YAML out, URL | landed; fix negatives, `note["…"]`, add Ratio |
| `facets.js` | the rail ↔ tree projection | proved here |
| `data.js` | the field schema, the loaders (JSON, JSONL, CSV), rich cells | build |
| `data-ui check` | a Node CLI over `grammar.js` + `schemas/view.schema.json` | proved in Python here |
| `data_ui_static.py` | A stdlib helper for Python-built pages. It writes:<br>• the data JSON;<br>• the no-JS `<table>` inside `<data-views>`;<br>• `<data-value>` text. | build: robotparts' `site_pages.py` already has most of it |

Not data-ui: app shells, sidebars, command palettes, trees and report pages. These are the survey's other kits; app chrome for React is the `@bam` registry.

**Light DOM, not shadow DOM, for `<data-views>`.** It hosts the server-rendered fallback table, and robotparts' tests and search engines read that text. It wears the page's fonts. Classes are `dv-*` (private); tokens are the contract.

### 7.1 The bar: `toolbar="bar"` and its variants (2026-10-26)

Zach's pick of the six toolbar proposals ("Definitely yes I like the mix"): P6's Shopify pill bar, Obsidian Bases'
view menu inside the view chip, filter pills and the rail showing one state both ways, and Notion's View settings
panel. The header search of a host page stays the site's search; the table gets its own query bar inside the bar. The
API is docs/CONTRACT.md §15; the why and the forks are docs/peps/0002-toolbar.md.

- **One quiet row, always:** the view chip or tabs · the query bar (lane B's `toolbar/query.js`) · the filter control ·
  Display. It never wraps: as the bar narrows, tabs fold into "N more", labels drop to icons, controls move into "…", the
  query box folds to its icon, the tabs fold to the chip (one priority table, bar.js `DEGRADE`; Obsidian's and Shopify's
  one-row bars). A pill row shows only while a filter exists; with a selection the bulk bar takes its place.
- **Variants are attributes**, read live (switching one keeps the view, filters, query and selection):
  - `views="auto|dropdown|tabs"`: the chip (its up/down chevron lights on hover; its menu has a find box, a ✓ on the
    open view, a › per view for Configure view, and Add view with the layout grid), the tabs (what fits, then
    "N more…" and +), or tabs while the whole bar fits on one line (re-decided on resize).
  - `filters="pills expanded query-tokens rail"`, a set: removable pills under the bar ("Brand: Steadywin, KST ✕",
    + Filter, Clear); Sort · Group · Filter · Properties as words that say what is set ("Sort: Peak torque"); the
    clauses as tokens inside the query box; a Filters toggle that hides the linked `<data-facets>` (remembered).
  - `display="panel|popover"`: View settings as a resizable side panel (the default; 260-640 px, remembered,
    double-click resets) or a popover under Display; a full-width sheet below 700 px. Rows: the name, Layout ›
    (the layout grid plus the layout's own `options()`), Property visibility N ›, Filter ›, Sort ›, Group ›, Copy link
    to view, Copy view as .base. The sub-pages are the toolbar's own menu bodies.
- **Views visible ⇒ filters folded; views in a dropdown ⇒ filters may expand:** with no `filters` attribute, tabs give
  one Filter button and the chip gives the four words (Notion's pattern; re-decided as `auto` flips). `search="icon"`
  folds the query box behind a Search icon that grows it in place (click or `/`). Case: `toolbar-search`.
- **Display holds everything; `promote` puts sections on the bar:** `promote="sort group filter properties"` (any of
  them; `""` none) shows those View settings sections on the bar too, as the same controls. One Filter: with a linked
  rail it shows and hides the rail. `labels="icons"` keeps the labels off. Presets: Shopify (`promote=""`), Notion
  (tabs, `promote=""`), Obsidian (dropdown, all four). Selecting rows lays a tinted bulk band over the column header row.
- **One filter tree:** the query bar, the pills, the rail, the Filter menu and the URL all edit `el.filters`; a pill is
  the rail's projection of it, so a pick anywhere shows everywhere at once.
- **Keyboard:** `/` focuses the bar's query box (when focus is not in a text field); Escape closes a menu, then the
  View settings, then the peek, then clears the selection.
- **Cases:** `gallery/examples/toolbar-bar` (auto + pills + rail + panel, selectable), `toolbar-notion` (tabs + pills
  + panel), `toolbar-obsidian` (dropdown + expanded + panel); each case's `checks.py` measures its claims.

## 8. The chart view

### 8.1 What Zach asked for (Oct 25), and where each ask lives

| Ask | In the grammar |
|---|---|
| "Quickly switch to a chart, and as you filter it applies to the chart" | `type: chart` is one more view over the same rows; the rail's filter applies to every view (§6) |
| Multiple charts, or chart presets to switch between | each preset is a view in the same `.base`; the tabs switch them |
| Hover a dot: photo, name, key values | `hover: {image, title, fields}` → the shared hover card |
| Colour, size, opacity bound to fields | `chart.encoding.color / size / opacity / shape` (Vega-Lite channels) |
| Log vs linear | `encoding.x.scale.type: log \| linear \| symlog` |
| Ashby-style charts | log-log + `guides: envelope / indexLine` (§8.8) |
| "Full customisation but also presets and good defaults" | the Encode menu writes `chart:`; changes show Reset / Save view (lane); defaults follow Show Me's rules (§8.5) |
| "An option to see the raw data" | every non-table layout has **Rows**: the same filtered rows as a table, one click |

### 8.2 One engine: Vega-Lite (scores, of 100)

| Criterion | Weight | Vega-Lite (vega-embed) | ECharts 6 | Observable Plot | Graphic Walker | Perspective charts | today's hand SVG |
|---|---|---|---|---|---|---|---|
| R1 The file's chart block renders with no translator | 25 | 5 | 1 | 2 | 3 | 1 | 1 |
| R2 Covers the asks above (channels, log, facets, guides, image hover, click) | 20 | 4 | 5 | 3 | 3 | 2 | 2 |
| R3 Agents already fluent; a published JSON Schema to validate against | 15 | 5 | 3 | 3 | 2 | 2 | 1 |
| R4 One engine across data-ui and his apps (in use today) | 15 | 2 | 5 | 1 | 1 | 3 | 2 |
| R5 Interaction at 1k–100k points | 10 | 3 | 5 | 2 | 3 | 5 | 2 |
| R6 Bytes on a phone page (lazy) | 10 | 3 | 3 | 4 | 1 | 1 | 5 |
| R7 Licence, maintenance | 5 | 5 | 5 | 5 | 4 | 5 | 3 |
| **Total** | 100 | **79** | 70 | 51 | 48 | 45 | 39 |

Why Vega-Lite wins:
- The chart is configured *by a file an agent writes*. With Vega-Lite the `chart:` block is the spec: no translator, no second meaning, and its own JSON Schema validates it.
- ECharts would need a hand-written Vega-Lite-to-ECharts compiler: the custom layer data-ui exists to avoid.

What ECharts has, which is why it is a close second:
- incumbency, in Vibe Tracks' drill-down and three atlases;
- interaction at scale.

Facts behind the scores:
- **Bytes** (jsDelivr builds, gzip -9, measured 2026-10-25): vega 6.4.0 180 KB + vega-lite 6.5.0 82 KB + vega-embed 7.3.0 21 KB, about 282 KB. It loads only when a chart view first shows. Plot 0.6.17 + d3 7.9.0 is 161 KB, but Plot's tip cannot show an image (its tip takes text).
- **An independent check:** the views-catalog lane's esbuild bundles (`docs/views/measurements.json`, in progress) measure 289 KB for the same Vega stack. The same file shows an ECharts *subset* bundle at 221 KB and ECharts in full at 383 KB, so ECharts can be the lighter one. That is why R6 is a tie, not a Vega-Lite win.
- **Vega-Lite's tooltip:** vega-tooltip's README documents an `image` key, and data-ui replaces the handler with its own hover card anyway.
- **Static render:** `vl-convert-python` (BSD-3, ~33 MB wheel, no Node) can render the same spec to static SVG at build time. Not in v1.

### 8.3 The `chart:` block

It is a Vega-Lite unit or layer spec without `data`, `datasets`, `$schema` or `config`. data-ui:
- fills each channel's `type` from the field schema when it is left out;
- injects the view's filtered rows;
- builds `config` from the page's tokens (§10);
- sizes it to the container.

Known trap (vault, Oct 5): a point selection on an escaped dotted field name records nothing. So data-ui passes dot-free field names to Vega-Lite internally.

### 8.4 Presets and full customisation together

- The first view in the file is the page's default; "Save as preset" works as the lane built it.
- The **Encode** menu sets:
  - X, Y, Colour, Size, Opacity, Shape, Facet (row/column), Tooltip;
  - Linear / Log per axis;
  - Mark: point, line, bar, tick, area.
- Each change edits `chart:`, so the view reads "changed" and Save writes the same grammar the agent writes.
- Out of scope: drag-and-drop shelves (Tableau, Graphic Walker).

### 8.5 Good defaults: Tableau's Show Me, as about ten rules

| Fields picked | Default |
|---|---|
| quantitative × quantitative | points |
| nominal × quantitative | bars of the median for 20 or fewer categories, else ticks |
| time × quantitative | a line (points below 10 rows) |
| time bucket (`by: day…year`) × a number or a count | a line over every bucket, points while 40 or fewer; a count is 0 in an empty bucket, `gaps: true` breaks the line there (Zach, 2026-10-26: change over time is a line; bars stay `mark: bar`) |
| one quantitative | a histogram |
| one nominal | bars of count |
| colour | the first `facets` property with 10 or fewer values, or none |

**Log axes:** log only when the field's positive values span at least two decades over the whole data, not the filtered rows. Two reasons:
- Zach's Oct 19 research found log axes "add nothing" across a 2–3× shortlist.
- Deciding over the whole data means the axis never flips while filtering.

A rule fills in only what the view leaves out. Once Zach sets a channel, it is stored. Sources: Mackinlay, Hanrahan and Stolte 2007; CompassQL and Voyager (§15).

### 8.6 Hover and click

- vega-embed's tooltip handler is replaced by data-ui's hover card: the photo, the title, the encoded fields as `<data-value>` with units and basis.
- A click emits `data-views-open`. robotparts opens the part page; other hosts open the peek.

### 8.7 Raw data

Rows opens the same filtered rows in a table under the chart: Tableau's "View Data", one click away.

### 8.8 Guides, compiled to Vega-Lite layers

- **`rule: {x | y}`:** a reference line.
- **`envelope: <property>`:** one envelope per value, around its points, in log space on log axes. This is Granta's "bubble-like envelopes" around each material family.
  - `shape: hull | ellipse`. Granta's own geometry is undocumented; one secondary source says ellipses.
  - Whether Vega-Lite can fill a closed outline (`interpolate: linear-closed`) is to prove in the Ashby gallery case. The fallback is outlines.
- **`indexLine: {slope, through}`:** on log-log axes, a line of constant y / x^slope. This is Ashby's performance index, as Granta Selector draws it. A slider to move it comes later.

### 8.9 Graphic Walker: evaluated, not adopted for the chart view

What it is:
- `@kanaries/graphic-walker` 0.5.3, Apache-2.0, a peer dependency on React 19 or later, 71 dependencies (styled-components, mobx, tailwindcss, leaflet, vega, Plot, i18next…);
- a 5.5 MB ESM, with no non-React embed in its README;
- its own `IChart` spec format, its own filters, and a natural-language box.

Why not:
- It fails robotparts' static, no-React page.
- It would be a second grammar and a second filter model beside the `.base` file.

Kept as a later option: an "Explore in Graphic Walker" button in React hosts, handing over the current filtered rows. Its `normalize()` accepts "Vega-Lite-like specs", so choosing Vega-Lite keeps that door open. Its natural-language box is out: there is no AI in data-ui.

### 8.10 Perspective and ECharts

- **Perspective** stays only as an escape hatch for million-row data. Vibe Tracks' Results pivot becomes a `type: pivot` preset once `Ratio` lands (the lane's estimate: about 10 lines).
- **ECharts** stays in Vibe Tracks' `<vt-kpi-progress>` drill-down (a fixed app chart, ~650 lines) until a side-by-side shows a Vega-Lite preset can replace it. data-ui does not extract it.

### 8.11 The gate in the first slice

On robotparts' actuators page, vega-embed must re-render the 1,149-point chart after a filter change in under 100 ms at 390 px wide.

Zach also picks between today's hand-SVG chart and the Vega-Lite one in a side-by-side. If either fails, I revisit ECharts with a translator for the small subset.

## 9. The KPI card and value with provenance

### 9.1 `type: kpi` and `<data-kpi>`

The card shows:
- the label and the value (`<data-value>`);
- a delta against the comparison: `previous` window, `target` or a property. It is coloured only outside the `neutral` band, and by the declared `better: higher | lower`, never by the sign;
- a sparkline;
- the basis badge;
- "from rows · n" or "from the producer";
- the gate or target.

The vocabulary comes from Evidence's BigValue: `comparison`, `down_is_good` becomes `better`, `neutral_range` becomes `neutral`, plus `sparkline`. A view with `groupBy` gives one card per group, so a KPI strip is a grouped summary. This replaces the survey's 13 hand-rolled KPI cards in 7 apps, and its `<bam-kpi-card>`. Example: `examples/runs.base`.

### 9.2 One "how sure" vocabulary (proposed; confirm per app)

| Basis | Mark | Means | Each app's words today (survey) |
|---|---|---|---|
| `measured` | ● | measured on a bench or in a run | robotparts, Tycoon, dataclass viewer, Vibe Tracks: measured |
| `datasheet` | D | the maker's published spec | robotparts datasheet; atlases manufacturer, transcribed; Tycoon datasheet |
| `seller` | S | a seller's listing | robotparts seller; atlases distributor, retailer, aifitlab-text; dataclass viewer market |
| `derived` | ~ | computed from other values | atlases, Tycoon: derived |
| `estimate` | ○ | modelled or estimated | atlases estimated; Tycoon estimate; Vibe Tracks estimate |
| `assumed` | A | an assumption | Tycoon guess; dataclass viewer assumed |
| `chosen` | C | a design choice, set on purpose | dataclass viewer chosen |
| `sampled` | ≈ | drawn from a distribution | dataclass viewer sampled |
| `stand-in` | ◌ | a placeholder for the real value | Vibe Tracks stand-in |
| `claimed` | ” | asserted, not computed (an agent's claim) | Vibe Tracks claimed (styled apart) |

Absence is not a basis: `{value: null, why: "not measured" | "not published" | "not found"}`.

## 10. Tokens: the shadcn model done right

- **Delivery:**
  - The engine (elements, grammar) is one pinned copy, vendored, never edited in an app. Updating means re-vendoring.
  - **Skins** (token blocks) and **recipes** (page compositions with their `.base`) are copy-in, owned by the app, shadcn style.
  - React apps get all three through a shadcn registry (`registry.json`, items `registry:lib` / `registry:style` / `registry:block`, installed with `npx shadcn add @data-ui/<item>`).
  - Vanilla and Python-static apps get the same files through a vendor script, with a version and sha manifest (the way `stable_preview_switcher` ships).
- **The contract is `--data-*`.** Elements never declare these on their own selector; they read `var(--data-fg, var(--foreground, #18181b))`. So a host may set them at `:root`, and a shadcn app needs no lines at all.

| Token | Role | Default chain (shadcn name, then a literal) |
|---|---|---|
| `--data-bg` / `--data-fg` | surface / text | `--background` / `--foreground` |
| `--data-muted` | secondary text | `--muted-foreground` |
| `--data-subtle` | header and group fill | `--muted` |
| `--data-border` / `--data-rule` | borders / row rules | `--border` |
| `--data-hover` | hover fill | `--accent` (shadcn's meaning) |
| `--data-accent` / `--data-on-accent` | links, selection, primary button | `--primary` / `--primary-foreground` |
| `--data-warn` | filter errors | `--destructive` |
| `--data-radius`, `--data-font`, `--data-mono`, `--data-row` | shape and type | `--radius`, `--font-sans`, `--font-mono`, 30px |
| `--data-series-1…8` | categorical colours (charts, badges) | `--chart-1…5`, then three of data-ui's |
| `--data-good` / `--data-bad` | KPI deltas outside the neutral band | none (calm: grey otherwise) |
| `--data-basis-<name>` | basis marks (§9.2) | none |

"Change the tokens to match your site" means one block:

```css
/* robotparts (site.css names; the lane already mapped these) */
:root { --data-bg: var(--bg); --data-fg: var(--ink); --data-muted: var(--ink2); --data-subtle: var(--bg2);
        --data-border: var(--rule); --data-rule: var(--rule2); --data-hover: var(--hover); --data-accent: var(--accent);
        --data-on-accent: var(--on-accent); --data-warn: var(--warn); --data-font: var(--sans); --data-mono: var(--mono); }
/* Vibe Tracks (Claude Desktop names, tokens.css) */
:root { --data-bg: var(--surface); --data-fg: var(--ink); --data-muted: var(--ink-2); --data-subtle: var(--alpha-1);
        --data-border: var(--line); --data-rule: var(--alpha-1); --data-hover: var(--hover); --data-accent: var(--accent);
        --data-warn: var(--warn-ink); --data-font: var(--font); --data-mono: var(--mono); --data-radius: var(--radius); }
/* a shadcn app: nothing */
```

More on tokens:
- **Dark mode:** the host flips its own tokens. data-ui's literal fallbacks carry a dark set under `prefers-color-scheme` for a host that defines nothing.
- **Charts:** at render, data-ui reads the computed tokens into Vega-Lite's `config` (font, axis and grid colours, `range.category` from `--data-series-*`). It re-renders when the theme changes.
- **The rename:** the lane's `--dv-*` become `--data-*` in the barrier step (§11). There are zero consumers today, and it is one sed. The lane's eight badge hue pairs become `--data-series-*` and their inks.

## 11. The first slice (exact)

**What it proves:** one file of data plus one `.base` file give a table, cards, a chart and the rail, in a live app (robotparts actuators, 1,149 rows) and in the gallery.

0. **Barrier (alone, first).**
   - Move the lane's `views/` (`ab5ba92`) into this repo with a provenance commit.
   - Rename its tokens to `--data-*`.
   - Fix negatives and `note["…"]` in `grammar.js`.
   - Freeze three things: the `el.data` shape, the grammar keys of §5.3–5.4, and the token names.

   robotparts must then vendor `dist/` from here, not from `design/`. Otherwise the first integration is already a fork.
1. **Cards:** `type: cards` with Bases' keys, plus the shared hover card and a minimal `<data-value>` (number, unit, basis mark, source on hover).
2. **Chart:** `type: chart` with:
   - vega-embed as a lazy chunk and the `chart:` block;
   - tokens → `config`;
   - the hover card and click → open;
   - the Encode menu (X, Y, colour, size, opacity, shape; log/linear);
   - Rows, and the Show Me defaults.
3. **robotparts** (on a robotparts lane, Preview only, not merged):
   - the actuators data gains `photo` and rich cells for its specs. The build already has photos and `source_kind`, and `tools/test_check_views.py` flips when it lands.
   - `presets/actuators.base` gains Gallery, Torque vs mass and Density vs price.
   - The category page renders `<data-views>` and `<data-facets>`, with today's server table inside as the no-JS fallback.
4. **The rail:** `<data-facets>` on the all-views filter (brand, form, drivetrain, bus, level, peak torque, mass, price) with disjunctive counts. Its selection persists across layouts and travels in readable URL params.
5. **The gallery:** two cases from the same files. robotparts actuators in robotparts' skin, and the rack's models × benches pivot in the shadcn neutral skin. Each has a checks script.
6. **`data-ui check`** as a Node CLI, a port of the Python proof onto `grammar.js`.

**Acceptance.** These checks are measured and frozen before the build, and builders may not edit them.

- The same 1,149 rows in all three layouts.
- One rail tick changes the table's row count, the gallery's card count and the chart's dot count to the same number.
- The rail's selection survives a layout switch and a reload (URL).
- Editing `actuators.base` on disk, as an agent would, changes the page on the next Preview build.
- The vega chunk loads only when a chart first shows. A filter change re-renders the 1,149-point chart in under 100 ms at 390 px.
- A dot's hover shows the photo when there is one, and its click opens the part page.
- Nothing loads from another origin, and there are no script errors.
- Light and dark come from robotparts' tokens, with no sideways scroll at 390 px.
- Obsidian 1.14.5 (headless) opens `actuators.base`, draws its table and cards views, and keeps the `chart:` keys after a sort is changed there.
- A side-by-side of today's hand-SVG chart and the Vega-Lite one, for Zach to pick.

**Not in the first slice:** kanban, kpi, Ashby guides, the pivot's Ratio, Vibe Tracks, the Clank and Obsidian hosts, formulas (one has run since, §5.6), Parquet, accounts.

**Later slices:**
- **Slice 2:** `type: kpi` + `<data-value>` in full + Ratio. Vibe Tracks' Results tab becomes a `type: pivot` preset and its tiles `type: kpi`, on its fixture bundle (gallery case 3).
- **Slice 3:** Ashby guides, kanban, and the three atlases onto data-ui.
- **Slice 4:** the Obsidian Bases view plugin and the Clank viewer.

### 11.1 What this needs from the table lane

The lane has landed. Three things are still open.

1. **Zach's yes on the lane's own question** ("Adopt TanStack + `<data-views>` + Bases presets site-wide?"). Its default is to integrate on the actuators page first, which is step 3 here.
2. **One home for the code.** The lane recommended `~/data-views`; this spec says this repo (to become `~/data-ui`). They must be the same place, and the integration must wait for the barrier.
3. **No new keys on the lane's side without this spec**, so the grammar stays one grammar.

## 12. Hosts

| Host | Stack | How it gets data-ui | Without JavaScript |
|---|---|---|---|
| robotparts.dev | Python-built static HTML, no React, no other origin | vendored ESM at `site/static/vendor/data-ui/<version>/` with a sha manifest; a module script on list pages only | the full server-rendered table, `<data-value>` text |
| Vibe Tracks | vanilla JS served by Python | vendored under `vibetracks/home/static/vendor/` | n/a |
| React 19 apps (Tycoon, claude-hub, Aruco, pyblocks) | React 19: 100% on custom-elements-everywhere | the tags directly; an optional typed wrapper from the registry | n/a |
| Clank (later) | React workbench | a `clank-data-ui` plugin repo: `option` viewers for `.csv` / `.jsonl` / `.json` (CodeMirror keeps them as text by default) that also replaces `clank.base` | n/a |
| Obsidian (later) | Bases, plugin views since 1.10 (`registerBasesView`) | a plugin adding `chart`, `pivot` and `kpi` over notes | stock Bases draws table, cards and kanban; the extra keys survive |
| Reports | Python builders | `<data-value>` / `<data-kpi>` tags plus static data | text |

**Clank status (for this decision):**
- The workbench's last commit is `9859de0` on Oct 5.
- Plugins kept shipping until Oct 20: clank-cad2robot Oct 14, clank-daisychain Oct 20.
- Vibe Tracks removed its Clank plugin on Oct 25, on Zach's word: "a completely standalone application that shouldn't know about clank".

So Clank is dormant, not dead. data-ui must not depend on it.

## 13. The gallery = the docs site

- **What it is:** a static site built from case folders. It is the docs (data-ui.dev, if Zach buys it), the catalogue an agent copies for case n+1, and the test suite.
- **A case:** `gallery/cases/<slug>/` holds:
  - `case.md`: the project, what it proves, the views, the skin;
  - the data, or a snapshot script (data stays out of git);
  - `views.base`;
  - `skin.css`, the token block.
- **A case page:** the real components on the real data in its site's skin, plus a Files tab with the `.base` and the token block, copyable.
- **Tests:** a headless journey per case, with measured assertions and a screenshot.
- **The cases, in order:**
  1. robotparts actuators: rail, table, gallery, charts.
  2. The rack's models × benches: pivot, leaderboard.
  3. Vibe Tracks runs: pivot with Ratio, KPI strip, chart over time. Fixture bundle only.
  4. The GIM4305-10 datasheet: groups, distributions, a kanban of "to measure next".
  5. A BAM KPI strip.
  6. An image gallery: robotparts photos, bench failure media.
  7. robotparts sources: grouped sums.
  8. A vault folder of notes: the notes input form.
- **Data rule:** public-safe data only. Private track figures (grasping) never enter the gallery. That is Vibe Tracks' public-repo trap.
- **Not Storybook first:** the case page is what Zach wants to look at. Storybook can wrap the same folders later for component states.

## 14. Scope traps

1. A sixth copy: the lane's code and the survey's kits land here, or nowhere.
2. "Any number of views": seven layouts. A new layout needs a case none of them can serve.
3. A Tableau / Graphic Walker clone: the Encode menu, presets and the agent are enough. No drag-and-drop shelves.
4. Bases formulas in the browser: producers compute. The one exception is the first non-empty of a list of columns, for display (§5.6).
5. A query engine on public pages (DuckDB-wasm).
6. Editing data in cells: views are read-only, and data changes at its source (file-first).
7. A shell: file trees and tabs are Clank's.
8. Accounts and synced presets: localStorage and the URL now; Simple Hosted Files later.
9. Two chart engines inside data-ui.
10. Per-component theming knobs: tokens only.

## 15. Prior art for "file in, many views out" (accessed 2026-10-25)

**Gate:** a whole product is adoptable only if it runs inside a Python-built static page with no React and no other origin (C2).

| Product | What it is | Gate | What data-ui takes | Source |
|---|---|---|---|---|
| Obsidian Bases | `.base` YAML views over notes: table, cards, list, kanban (1.14), map; plugin views since 1.10 | ✗ (vault notes only, no websites) | **the grammar**, the cards keys, kanban | https://obsidian.md/help/bases/syntax · https://obsidian.md/help/bases/views · https://docs.obsidian.md/Reference/TypeScript+API/Plugin/registerBasesView |
| Notion databases | 7 layouts incl. Chart; per-view filter/sort/group; AND/OR groups 3 deep; views not exportable as files | ✗ (hosted) | per-view settings; sub-group | https://www.notion.com/help/views-filters-and-sorts · https://www.notion.com/help/export-your-content |
| Airtable | 8 view types; attachment field type; condition groups 3 deep | ✗ (hosted) | attachment = a typed column | https://support.airtable.com/docs/getting-started-with-airtable-views · https://support.airtable.com/docs/filtering-records-using-conditions |
| WordPress DataViews | React `DataViews`: a `view` object (type, fields, sort, filters, groupBy, layout); table/grid/list/activity; GPL-2.0+; ~436 kB gz | ✗ (React, GPL) | validates the view-object + fields decomposition | https://developer.wordpress.org/block-editor/reference-guides/packages/packages-dataviews/ · https://bundlephobia.com/package/@wordpress/dataviews |
| Grist | spreadsheet-database, a SQLite-based `.grist` file, linked widgets; Apache-2.0 core; `grist-static` | ✗ (an app) | linked widgets ≈ one filter for every view | https://support.getgrist.com/widget-table/ |
| Datasette (+ Lite) | SQLite → table pages; column/array/date **facets**; metadata units; Lite on Pyodide | ✗ (Pyodide, MBs) | facets as URL params; units in metadata | https://docs.datasette.io/en/stable/facets.html · https://github.com/simonw/datasette-lite |
| VisiData | terminal sheets (frequency, pivot), 25+ formats; sessions replay as `.vdj` | ✗ (terminal) | the cmdlog idea: views as replayable text | https://www.visidata.org/docs/save-restore/ |
| Evidence.dev | markdown + SQL → static site; BigValue (sparkline, comparison, down_is_good); DuckDB-wasm | ✗ (its own site generator) | **BigValue's vocabulary** for the KPI card | https://docs.evidence.dev/components/big-value/ · https://evidence.dev/blog/why-we-built-usql/ |
| Observable Framework + Plot | data loaders in any language → static site; Plot ISC ~69 KB gz (+ d3 92 KB) | ✗ (its own site generator; per the survey, "not developing new features", Mar 2026) | build-time loaders = robotparts' build | https://github.com/observablehq/framework · https://github.com/observablehq/plot |
| Rill | DuckDB; metrics views and explore dashboards in YAML | ✗ (a running service) | dashboards as YAML files | https://docs.rilldata.com/reference/project-files/metrics-views |
| Lightdash | metrics in dbt YAML, "BI as code" | ✗ (server) | — | https://docs.lightdash.com/guides/how-to-create-metrics |
| Grafana | dashboard JSON; Table cells incl. sparkline/image; Stat panel sparkline | ✗ (server, AGPL) | cell display types | https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/table/ |
| Malloy | `# bar_chart`, `# big_value`, `# image` tags choose the view; renders with Vega-Lite | ✗ (needs an engine) | tags-in-the-file; Vega-Lite as renderer | https://docs.malloydata.dev/documentation/visualizations/overview |
| Perspective 5.6 | `<perspective-viewer>` custom element; pivot + charts; Arrow; ~4.3–4.9 MB wasm | ✓ but fails C6 ("too technical") and C7 | `split_by` → the lane's `splitBy` | https://github.com/perspective-dev/perspective |
| DuckDB-wasm / DuckDB UI / Tad | SQL over CSV/Parquet in the browser (35.66 MB raw eh build) / a local notebook UI / a desktop pivot viewer | ✗ for public pages | build-time DuckDB | https://duckdb.org/2025/03/12/duckdb-ui.html · https://www.tadviewer.com/ |
| Mosaic (vgplot) | linked views over DuckDB, JSON/YAML specs, BSD-3 | ✗ (DuckDB-bound) | cross-filtering = one filter, many views | https://github.com/uwdata/mosaic |
| Tremor / shadcn charts and blocks | copy-paste React KPI/chart blocks; Vercel acquired Tremor (Jan 2025) | ✗ (React) | the KPI card look; blocks as recipes | https://vercel.com/blog/vercel-acquires-tremor · https://ui.shadcn.com/docs/components/chart |
| shadcn registry | `registry.json` items (lib, block, style, file…); namespaces `@acme/x`; CSS-variable themes | n/a (delivery) | **registry delivery + the token names** | https://ui.shadcn.com/docs/registry/registry-item-json · https://ui.shadcn.com/docs/theming |
| TanStack Table 9.3.1 + Virtual 3.19.7 | headless table core, MIT | ✓ | **the table engine** (landed) | https://github.com/TanStack/table/releases |
| Vega-Lite 6.5 | a grammar of graphics in JSON with a published schema; BSD-3 | ✓ | **the chart engine and vocabulary** | https://vega.github.io/schema/vega-lite/v6.json · https://github.com/vega/vega-tooltip |
| Graphic Walker 0.5.3 / PyGWalker | Tableau-like React explorer on Vega-Lite; Apache-2.0 | ✗ (React, 5.5 MB) | later: "Explore" in React hosts | https://raw.githubusercontent.com/Kanaries/graphic-walker/main/README.md · https://github.com/Kanaries/pygwalker |
| Voyager / CompassQL / Draco 2 | chart recommendation from field types; Draco as weighted constraints | n/a | the Show Me rule table (§8.5) | https://github.com/vega/voyager · https://github.com/uwdata/compassql · https://github.com/cmudig/draco2 |
| Tableau "Show Me" (2007) | "Automatic Marks" rules from field roles and types | n/a | the defaults idea | https://www.tableau.com/research/publications/show-me-automatic-presentation-visual-analysis |
| Superset / Metabase / RAWGraphs | chart control panels; Metabase log scale; RAWGraphs maps dimensions to visual variables (no server; Apache-2.0) | ✗ (servers) / RAWGraphs n/a | Encode menu ≈ RAWGraphs' mapping | https://www.metabase.com/docs/latest/questions/visualizations/line-bar-and-area-charts · https://www.rawgraphs.io/learning/how-to-map-the-dimensions-of-your-data-with-the-chart-variables |
| Plotly Chart Studio | shut down 31 Oct 2025; react-chart-editor MIT, last release 2023-11 | n/a | a warning: a chart editor is a product | https://plotly.com/chart-studio-updates/ |
| Ansys Granta EduPack / Selector | Ashby charts: log-log property charts, family envelopes, index lines of slope s, Maximise/Minimise | n/a | **`envelope`, `indexLine`** | https://ansyshelp.ansys.com/public/Views/Secured/Granta/v261/en/Selector/sel_edu/adding_index_line.html · …/family_envelopes.html |
| Frictionless Table Schema | field descriptors for CSV + types; `format: uri` | n/a | **the field schema** | https://datapackage.org/standard/table-schema/ |
| W3C DTCG tokens 2025.10 | first stable design-tokens format (Oct 2025) | n/a | an optional `.tokens.json` export later | https://www.designtokens.org/tr/2025.10/format/ |

**Verdict:** nothing passes the gate as a whole product except Perspective, which fails Zach's "too technical" and the phone budget. data-ui is therefore glue, roughly the lane's ~1,050 lines plus cards, kanban, chart, kpi and the rail, on TanStack, Vega-Lite, the Bases grammar and Table Schema.

Vault prior art: Vibe Tracks' Oct 14 tables and pivots research recommended keeping Perspective. Zach's Oct 25 "too technical" and the lane's 92 vs 74 supersede it.

## 16. Decision tables

### 16.1 How data-ui relates to Clank (criteria §3, scores 1–5, of 100)

| Option | C1 20 | C2 20 | C3 15 | C4 15 | C5 10 | C6 10 | C7 5 | C8 5 | Total |
|---|---|---|---|---|---|---|---|---|---|
| (a) a Clank plugin for data files | 3 | 1 | 3 | 4 | 3 | 3 | 2 | 2 | 53 |
| (b) a standalone app | 3 | 2 | 3 | 3 | 2 | 3 | 3 | 3 | 54 |
| **(c) a kit: custom elements + `.base` grammar + tokens + gallery; Clank and Obsidian as thin hosts later** | 5 | 5 | 4 | 5 | 5 | 4 | 4 | 5 | **94** |
| (d) a shadcn React registry only | 4 | 2 | 4 | 4 | 2 | 4 | 3 | 4 | 67 |

(c) wins on C2: robotparts and Vibe Tracks are where the data views live, and neither is React or Clank. Zach's Oct 25 words close (b).

### 16.2 The element prefix

| Option | Survives (40) | Says what it is (25) | Already in landed code (20) | No clash (15) | Total |
|---|---|---|---|---|---|
| **`data-*` (`<data-views>`, `<data-value>`…) + `--data-*`** | 5 | 5 | 5 (`<data-views>`) | 4 (no `--data-*` variable in 14 repos; one `<data-home` string, in Vibe Tracks' retiring remote hub; `data-*` attributes look alike) | **97** |
| `bam-*` (the survey) | 4 | 2 (whose, not what) | 1 | 3 (a BAM brand on vibetracks.dev and Jidoka pages) | 55 |
| `dv-*` | 4 | 3 | 3 (classes, tokens) | 5 | 74 |

The reconciliation:
- the survey's `<bam-value>` / `<bam-kpi-card>` / `<bam-sparkline>` become `<data-value>` / `<data-kpi>` / `<data-sparkline>`;
- `<bam-kpi-history>` becomes a `type: chart` preset;
- `bam`/`@bam` stays for the survey's React app-chrome registry (shell, palette), which is not data-ui.

Custom-element attributes never start with `data-` (that namespace is the page author's).

## 17. Names (RDAP via `domain-check.py`, 2026-10-25; no registrar token, so prices and premium status are unknown)

Zach picked **data-ui** on Oct 25. The full check, as the brief asked:

| Name | .com | .dev | .app | Notes |
|---|---|---|---|---|
| **data-ui** (picked) | taken (2026-03-29; a live "Data UI" site) | **available** | **available** | hyphenated; a live data-ui.com product shares the name |
| datakit | taken (1997; live: "DATAKIT", CAD 2D/3D file conversion, a collision in CAD) | taken (2022) | taken (2020) | — |
| dataviewer | taken (2003) | taken (2025-09; a live "Data Viewer" site) | taken (2026-01) | near Obsidian's Dataview plugin |
| datawrangler | taken (2008) | taken (2025-07) | taken (2026-07) | Microsoft's Data Wrangler is a VS Code extension |
| datadog | taken (1997) | taken (2019) | taken (2018) | Datadog, Inc. |
| dataviews | taken (1994) | taken (2025-07) | available | WordPress's `@wordpress/dataviews` |
| viewkit | taken (for sale on HugeDomains) | available | taken (2026-07) | — |
| manyviews | taken (2005) | available | available | the thesis in a word |
| rowkit | taken | taken | taken | — |
| fileviews | taken (2010) | available | available | — |
| viewsheet | taken (2021) | available | available | — |
| glancekit | taken (2026-04; a live App Store screenshot tool) | available | available | — |
| viewbook | taken (2003) | available | taken (2026-09) | — |
| viewbase | taken (1999; redirects to a casino spam site) | available | available | echoes Bases |
| tablekit | taken | taken | taken | — |

Buying `data-ui.dev` is a purchase, so it is Zach's call. It would host the gallery and the registry (`https://data-ui.dev/r/{name}.json`).

## 18. Open questions for Zach (each with my recommendation and the default if silent)

1. **One home.** Should this repo hold the lane's `<data-views>` and the survey's KPI kit, instead of `~/data-views` plus `~/bam-kpi`? *Recommend yes. Default: yes; the barrier step moves the code.*
2. **One chart engine: Vega-Lite**, not ECharts, for every data-ui chart, behind the first slice's speed and look gate. *Default: Vega-Lite.*
3. **Element prefix `data-*`, tokens `--data-*`.** The lane's `--dv-*` are renamed in the barrier. *Default: yes.*
4. **First slice on robotparts' actuators page**, as one lane together with the table lane's own integration step, on Preview only. *Default: yes, after the barrier.*
5. **Vibe Tracks' KPI history chart:** a Vega-Lite preset (slice 2 side-by-side) instead of extracting the ECharts one. *Default: Vega-Lite preset; the ECharts drill-down stays until the side-by-side.*
6. **`data-ui.dev`:** buy it for the docs site? *Default: not bought; the gallery runs locally.*
7. **A `PROJECT - data-ui` note?** *Default: no. The design note links the three PROJECT notes until you journal on it.*
8. **Clank's `clank.base`:** retire it in favour of a `clank-data-ui` viewer when Clank is next touched. *Default: yes, when touched.*

## 19. What would change my mind, and what I could not verify

**What would change my mind:**
- **vega-embed fails the gate** (over 100 ms re-render at 390 px, or a look Zach rejects beside today's chart). Then ECharts with a translator for the small subset.
- **Obsidian at runtime drops the extension keys** (the code says it keeps them). Then the extensions move to a sidecar `.views` file.
- **Zach wants local-file viewing now.** Then a single-page `data-ui open <file>` (no shell) comes before the Clank plugin.
- **Another lane builds the KPI kit on ECharts first.** Then data-ui's charts follow it, to keep one engine. Decide before either is built.
- **A common case needs more than ~50k rows.** Then the DuckDB-wasm adapter becomes first-class.

**Not verified:**
- Obsidian's runtime behaviour (only its code was read).
- vega-embed's speed on 1,149 points.
- Filled hulls in Vega-Lite.
- Granta's envelope geometry.
- React 19's binding for hyphenated custom events (`data-views-change`); the fallback is a ref listener.
- Domain prices and premium status.
- The ~50k-row browser ceiling.

## 20. Evidence in this repo, and how to run it

- `node --test`: `tools/facets.test.mjs`, 8 of 8, including the oracle on 1,149 real rows (it is skipped, never faked, when the lane's files are absent).
- `python3 -m unittest discover -s tools -p 'test_*.py'`: 5 of 5. It covers:
  - Zach's 109 `.base` files pass;
  - the lane's 4 presets pass against their rows;
  - the examples pass;
  - `broken.base` gets 8 named errors and 2 warnings;
  - the missing `photo` column is caught.
- `python3 tools/check_views.py <file.base> --data <rows or schema>`: the checker.
- `examples/`: `actuators.base` + `actuators.schema.json`, `runs.base` + `runs.schema.json` (experiment tracking, KPI strip), `datasheet-board.base` (Bases kanban), `broken.base`.
- `schemas/view.schema.json`: the grammar for agents.
- The report: `reports/data-ui-design-2026-10-25.html` (the diagram, the decision tables, the names).
