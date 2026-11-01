# data-ui contract (frozen 2026-10-25, phase 0)

This is what every view lane builds against. The why is `docs/peps/0001-data-ui-shape.md`; the design is
`docs/SPEC.md`; the per-view build spec (library, version, keys) is `docs/VIEWS.md`. The code is the reference:
`packages/core/src/` and the reference plugin `packages/views/table/`.

**Changing this file is a barrier.** A lane that needs a new host call, input field, token or `.base` key stops and
asks; the change lands alone, first, and every lane rebases on it. Adding keys *inside a view's own entry* that the
schema already lists is not a change.

## 0. Layout

```
packages/core/            the core: framework-free, one bundle (dist/data-ui.js + dist/data-ui.css)
  src/grammar.js          filters, summaries, pivot, view YAML, URL encoding (the lane's, fixed)
  src/base.js             .base read / write (YAML subset; python/data_ui_base.py is the stdlib twin)
  src/rowmodel.js         the ONE row model (§2)
  src/data.js             the input contract (§3)
  src/registry.js         registerView / loadView (§1)
  src/tokens.js           resolved tokens (§4)
  src/format.js           esc, fmtNum, valueHtml, BASIS, groupLabel, hueOf
  src/facets.js           the rail <-> filter-tree projection
  src/check.js            data-ui check (Node only; bin/data-ui.mjs)
  src/elements/           <data-views>, <data-facets>, <data-value>
  styles/                 tokens.css, core.css
packages/views/<folder>/  one folder per view = one lazy bundle, dist/views/<folder>.js
gallery/examples/<case>/  one folder per gallery case (§8)
site/                     the docs site builder (landing, gallery, views)
schemas/view.schema.json  the grammar for agents; both checkers read their key and type lists from it
```

Commands: `npm run build` (everything into `dist/`), `npm test` (build, unit, Python, browser), `npm run serve`,
`node bin/data-ui.mjs check FILE.base [--data DATA.json]`.

## 1. The view plugin

**A view is a folder** `packages/views/<folder>/`:

| File | What |
|---|---|
| `manifest.json` | `{entry, status, views: [{type, name, icon, summary}], npm: ["pkg@version"]}`. The build registers each `type` (two folders may not register one type). `status: "built"` once it works. |
| `src/index.js` (the `entry`) | the module (below) |
| `src/*.css` | imported as text (`import css from './x.css'`), exported as `css` |
| `README.md` | what it draws, its keys, its stock part |

**The module:**

```js
import { Virtualizer, esc, valueHtml, cellValue, groupLabel /* … */ } from '@data-ui/core';   // never a second copy
import css from './cards.css';
export { css };                                   // the host adds it to the document once, on first load
export function options(view, columns) {         // optional: the view's settings, shown in the Layout menu
  return [{ type: 'property', key: 'image', displayName: 'Image', none: 'none' },
          { type: 'slider', key: 'cardSize', displayName: 'Card size', min: 50, max: 800, step: 10 }];
}
export default class CardsView {
  constructor(host, el) {}  // el: a fresh <div class="dv-view dv-view-<type>"> inside the host; yours alone
  update(input) {}          // §2; may return a promise; called on every data, view, filter, search or theme change
  destroy() {}              // remove listeners you put outside el (e.g. on host.element)
  peeked(peek) {}           // optional: the host's peek opened ({id, row, column}) or closed (null)
  selected(set) {}          // optional: the ids to mark changed (§15's selection and a host's picks, §39); repaint, no redraw
}
```

Option types are Obsidian's: `dropdown {options: {value: label}, default}`, `property {none?, filter?: 'number'}`,
`slider {min, max, step}`, `text`, `toggle`, `multitext`. `key` is a path into the view entry (`value.summary`,
`splitBy.0`); an empty value removes the key.

**Registering by hand** (a host's own view): `registerView(type, {name, icon, load: () => import('./x.js'), options?})`.
`load()` resolves to the module or the class. A second registration of a type throws.

**`host`** (frozen; the only way back):

| Call | Does |
|---|---|
| `host.setView(patch)` | merges keys into this view's entry (`null` removes one), re-renders, returns the new entry. On a static site it lands in the URL and the user's presets; a file host writes the `.base` file. Never `data`/`datasets`. |
| `host.propose({id, set})` | asks for a data edit; resolves `{ok, reason}`. A `derived` or `readOnly` property refuses; then the page's `acceptEdit` hook decides, else an `editable` page applies it in memory, else it refuses ("read-only"). On `ok` the host re-renders with the edited rows. Draw the edit only after `ok`. |
| `host.open(id, {column?, records?, title?, row?})` | opens the shared record peek: the row's fields, every value behind it (`dataset.detail`), and `records` (a pivot cell's, a group's) as a table. Pass `row` for a synthetic row (a pivot row). |
| `host.setStatus(html)` | your part of the status line, after "N of M rows" (the table puts Unfold all / Fold all there). `''` clears it. |
| `host.element` | the `<data-views>` element (for listeners; remove them in `destroy()`) |

**Rules:** never mutate `rows`; never fetch data; never write outside your view entry; never load code, tiles,
fonts or images from another origin (everything is in `dist/`); colours only from tokens; light DOM, classes
`dv-<type>-*`.

**A React island** (graph): `load()` imports `react`, `react-dom/client` and `@xyflow/react` inside your bundle; the
constructor calls `createRoot(el)`, `update()` calls `root.render(…)`, `destroy()` calls `root.unmount()`. The build
compiles `.jsx` (`jsx: automatic`) and defines `process.env.NODE_ENV="production"`.

**An unknown or planned type** draws the table with a one-line notice ("The calendar view is planned … showing the
table"), so a `.base` file written before its view exists still shows its rows.


**Amendment 2026-10-26 (additive, from the cards lane):**
- A manifest may list `"covers": ["<View name in docs/VIEWS.md>"]`. A docs/VIEWS.md row whose type cell isn't a single plain type (e.g. "Image / media grid" = `cards` + `lightbox:`) shows as built when a built manifest covers its name.
- A manifest may list `"assets": [{"from": "<repo path>", "to": "<path under dist/views>"}]` for files a library loads beside its bundle at run time (MapLibre's worker); the build copies them as-is.
- A relative image or file path in a data cell resolves against the **data file's URL** (the `.base` file's `data:` resolved against the `.base` URL), never against the page.

**Amendment 2026-10-26 (additive, build only, from lane/perf-views):** a manifest may set `"split": true`. A dynamic
`import()` inside that view then becomes its own file beside the bundle, `dist/views/<folder>-<name>-<hash>.js`, listed
in `dist/manifest.json` (so a host that copies the manifest's files gets it) and fetched the first time it is used
(the cards' PhotoSwipe lightbox). Without `split` the build inlines a dynamic import, so the view stays one file.

## 2. The row model: what `update(input)` receives

The host computes one model per change (`rowModel(dataset, base, view, {query, filters})`):

```
dataset rows -> filter (the all-views filter AND the view's filters) -> search (the view's visible properties)
             -> sort (a group level with a direction first, then `sort`) -> group (groupBy, then subGroupBy;
                groupOrder orders the top level) -> limit -> pivot (type: pivot only)
```

| Field | Shape |
|---|---|
| `rows` | the records, after filters, search, sort and limit, **in the order the table draws them** (group order). The same objects as `dataset.rows`; read a cell with `cellValue(row[p])`. |
| `groups` | `null`, or `[{key, property, rows, groups?}]`: top level in `groupOrder` (a named group with no rows is still there, `rows: []`), then the rest; `groups` nests one level for `subGroupBy`. `key` is the raw value (`null` = no value; `groupLabel(columns, property, key)` says "No form"). |
| `columns` | `{id: {id, label, type: text \| number \| list \| boolean \| date, unitText?, decimals?, labels?, unit?, values?, display?, colors?, derived?, readOnly?, better?, hidden?, facet?, media?, basis?, width?, align?, note?}}`; `label` comes from the `.base` file's `properties.<p>.displayName`. |
| `view` | a frozen copy of this view's entry (Bases keys plus data-ui's) |
| `tokens` | §4, resolved to `rgb()` text |
| `total` | `dataset.rows.length` |
| `matched` | the rows before `limit` |
| `table` | the TanStack Table (table-core 9.3.1) instance behind `rows`/`groups`, all groups open. Views that fold groups may call `setExpanded` on it; never `setData`. |
| `pivot` | `null`, or for `type: pivot`: `{rows, columns: [{id: '@a / b', path, order}], properties, groups, table}`; a pivot cell is `row[col.id] = {v, values, records}`. `rows` above stay the records. |
| `query` | the search box's text |
| `filters` | the all-views filter (what the rail edits) |
| `dataset` | `{id, title, titleProperty, linkProperty, imageProperty, detail, records, url, attribution, raw, originOf, origin}` (`url`: amendment 2026-10-26 (core pass); `raw`, `originOf`, `origin`: §15; `attribution`: §42) |

**Cells.** A cell is a scalar, a list, or a rich cell `{value, unit?, basis?, source?, asOf?, low?, high?, n?, note?,
why?, text?}` (`text`: §22). Filtering, sorting, grouping, summaries and the rail read `.value` (`cellValue()`); draw a rich cell with
`valueHtml(cell, column)` so it carries its unit, basis mark and hover. Missing is `null` (or `{value: null, why}`),
drawn "—" with its reason, never 0.

**Sort order** (2026-10-30): numbers and lists of numbers are one sequence, a list by its smallest number and a tie by its
largest (a range `[15, 30]` sorts between 2 and 32, not after every number); then text by the collator; an empty value is
last both ways. `rowmodel.js` (`numericSpan`) and `order.js` sort alike. [tests/unit/sort-ranges.test.mjs]

**Summaries** in a view are view summaries ("max of 10 rows · from rows"); a headline number is the producer's,
carried in the data, never recomputed.

## 3. Data in

`el.data` (or the `.base` file's `data:`, relative to it) accepts: the runtime shape `{id, title, titleProperty,
linkProperty?, imageProperty?, properties, rows, detail?, records?, attribution?}` (`attribution`: §42); a Frictionless Table Schema `{schema: {fields},
rows}` or a sidecar whose `path` names the rows (types `number integer string array boolean date datetime`, plus
data-ui's `unit display facet media basis derived`); a bare list of objects (types inferred); `.csv` / `.tsv` /
`.jsonl` with an optional `<name>.schema.json` beside it; one object (a property sheet). Rows get `id` if they have
none. Rules: numbers are numbers, dates ISO 8601 text, lists arrays, missing `null`.

## 4. Tokens

Hosts set **`--data-*`** (or nothing). Each defaults to shadcn's variable, then a literal (light and dark):

| Token | Default | Role |
|---|---|---|
| `--data-bg` / `--data-fg` | `--background` / `--foreground` | surface / text |
| `--data-muted` | `--muted-foreground` | secondary text |
| `--data-subtle` | `--muted` | header and group fill |
| `--data-border` / `--data-rule` | `--border` | borders / row rules |
| `--data-hover` | `--accent` | hover fill (shadcn's meaning of accent) |
| `--data-accent` / `--data-on-accent` | `--primary` / `--primary-foreground` | links, selection, primary button |
| `--data-warn` | `--destructive` | filter errors |
| `--data-good` / `--data-bad` | muted (calm) | KPI deltas outside the neutral band |
| `--data-radius`, `--data-font`, `--data-mono` | `--radius`, `--font-sans`, `--font-mono` | shape, type |
| `--data-row`, `--data-height` | 30px, 70vh | row height; `<data-views>` height |
| `--data-series-1` … `-8` | `--chart-1` … `-5`, then data-ui's | categorical colours (the validated palette) |
| `--data-basis-<basis>` | fg (measured), muted (others) | basis marks (§7) |

Elements resolve these into private `--dv-*` properties (`styles/tokens.css`); never set or read `--dv-*` from a host.
Inside the kit, CSS uses `var(--dv-*)`. A badge's colour is a slot: `colors: {value: 0-8}` on a column, `0` muted,
`1-8` the series; `hueOf(text)` gives a stable slot. **In JS**, `input.tokens` is
`{bg, fg, muted, subtle, border, rule, hover, accent, onAccent, warn, good, bad, radius, font, mono, row, height,
series: [8], basis: {measured, …}, css: {'data-bg': …, 'data-series-3': …}, dark}`, colours as `rgb()` text. A view
entry may write a colour as `var(--data-series-3)`; resolve it from `tokens.css`. The host re-renders with new tokens
when the page's theme changes (a class / `data-theme` / `style` on `<html>` or `<body>`, or the system scheme).

## 5. `.base` keys by view type

Top level: Bases' `filters`, `formulas` (one runs, for display columns: §36), `properties.<p>.displayName` (and data-ui's `type`, `icon`, `description` and type options, §28), `summaries`, `views`;
data-ui's `data` (the data file, relative) and `facets` (the rail: a property or `{property, as: values | range |
has, label}`). Every view: `type`, `name`, `filters`, `order`, `sort`, `groupBy`, `groupOrder`, `limit`.

| `type` | Status | Bases keys | data-ui keys | Required |
|---|---|---|---|---|
| `table` | built | `columnSize`, `rowHeight: short\|medium\|tall\|extra`, `summaries` | `subGroupBy`, `display {p: text\|number\|bar\|dist\|sparkline\|badge\|image\|link\|value\|range\|stats\|markdown\|status (§35)\|media (§37)}`, `addRow`, `cellEdit` (§37), `units: column\|inline`, `fold: open\|closed`, `tree {parent} \| {path, separator}`, `rollup`, `columnGroups`, `stats`, `intro` (§16), `freeze`, `wrap`, `dist`, `before`, `after` (§28) | |
| `pivot` | built | `summaries` | `splitBy [p]`, `value {property, summary, per, display}`, `subGroupBy`, `fold`, `display`, `units`, `rollup`, `intro` (§16), `freeze`, `wrap`, `dist`, `before`, `after` (§28) | `splitBy` |
| `list` | planned | `markers: bullet\|number\|none`, `indentProperties`, `separator` | `subGroupBy`, `tree` | |
| `cards` | planned | `cardSize` 50-800, `image`, `imageFit: cover\|contain`, `imageAspectRatio` | `masonry`, `sketch {diameter, length}`, `hover {image, title, fields}`, `lightbox`, `media`, `caption [p]` | |
| `kanban` | planned | `columnWidth` 200-500, `image`, `imageFit`, `imageAspectRatio` | `subGroupBy` (swimlanes) | |
| `chart` | planned | | `chart` (Vega-Lite minus `data`, `datasets`, `$schema`, `config`; an `encoding` alone is enough), `guides [rule \| envelope \| indexLine]`, `hover` | `chart` |
| `kpi` | planned | | `kpi {label, value, compare {against, better: higher\|lower\|<property>, neutral}, spark {x, y, window}, target, gate}` | `kpi` |
| `calendar` | planned | | `start`, `end`, `title`, `calendarView: month\|week\|day\|list\|resourceTimeline` | `start` |
| `timeline` | planned | | `start`, `end`, `title`, `subGroupBy`, `color`, `zoom {min, max}` | `start` |
| `map` | built (§42) | `coordinates`, `markerIcon`, `markerColor`, `center`, `defaultZoom`, `minZoom`, `maxZoom`, `mapHeight`, `mapTiles`, `mapTilesDark` (the Maps plugin's) | `layers`, `space`, `time`, `multiples`, `swipe`, `draw`, `drawBy`, `drawSum`, `legend`, `pitch` (§42); basemap: a self-hosted `.pmtiles` | |
| `graph` | built | | `edges {property, label}`, `layout {engine: flow\|mermaid, algorithm: dagre, direction: LR\|TB\|RL\|BT}` | `edges` |
| `record` | planned | | `record {sections: [{name, properties}]}`, `edit`, `hover` | |
| `compare` | planned | | `compare {rows: [ids] \| selection, better {p: higher\|lower}, diffOnly}` | |
| `source` | built (§15) | | `rows: all\|filtered` (the view's `order` does not pick its columns) | |

`schemas/view.schema.json` is the machine version: both checkers read their key and type lists from it, so every key
above is already known (an unknown key is a warning, never an error, since Bases keeps keys it does not know). A
property-valued key (`start`, `image`, `edges.property`, `caption[i]`, …) is checked against the data.

## 6. `<data-views>`

- **Properties:** `data` (any form of §3), `base` (the parsed document), `presets` (a `views:` list), `baseText`
  (the file's text; ⋯ then copies the whole file), `filters` (the all-views filter), `acceptEdit` (async
  `({id, set, row}) => ({ok, reason})`); read-only: `view`, `model`, `host`, `peeked`.
- **Attributes:** `src` (a `.base` URL), `data` (a data URL), `view` (a view's name), `toolbar="full|compact|none"`,
  `status="on|off"` and `controls="on|off"` (§18),
  `no-url`, `editable`, `theme="light|dark"`.
- **Methods:** `setView(patch)`, `propose(edit)`, `openPeek(id, opts)`, `closePeek()`, `openMenu(name)` (`layout
  group sort filter properties save more`), `closeMenu()`, `row(id)`, `tokens()`, `viewYaml()`, `reload()`.
- **Events:** `data-views-change {view, name, dirty, filters}` (every change), `data-views-render {type, ms, rows}`
  (after the view drew), `data-views-open {row, column, records}`, `data-views-propose {id, set, row, result}`.
- **State:** the view in the hash (`#view=<unique slug>[&v=<changed view>][&f=<custom filters>]`), the rail's part
  as readable search params (`?brand=A,B&peak_torque=10..20&has=photo`), the user's presets in localStorage under
  `data-views/<data.id>`; every read and write in try/catch.
- Light DOM: a server-rendered `<table>` inside it is the no-JS fallback; the element replaces it when it starts.

## 7. `<data-facets>` and `<data-value>`

- `<data-facets for="views-id">`: the facets of the `.base` file's `facets:` (else fields with `facet:`); values with
  disjunctive counts and a find box, ranges with min / max, "has a value". It edits only the facet-shaped part of the
  all-views filter; the rest shows as "+N custom filters · Edit". On a phone it is a closed disclosure.
- `<data-value value unit basis source as-of low high n note why decimals>`: one value with provenance; its text
  content is the no-JS truth. `.cell = {value, …}` sets it from script. Bases: `measured ●`, `datasheet D`,
  `seller S`, `derived ~`, `estimate ○`, `assumed A`, `chosen C`, `sampled ≈`, `stand-in ◌`, `claimed ”`
  (`BASIS` in format.js). Absence is not a basis: `why="not measured"`.

**Amendment 2026-10-26 (filters; additive):** the rail's standard kinds. A `facets:` entry is a property, or
`{property, as: <kind>, …options}`; `as:` is one of the kinds below (an unknown one draws as `values` and warns, never
breaks). Every kind reads and writes the one all-views filter through `facets.js` (`toRail(filters, railConfig(specs))`
/ `fromRail`): with the rail's config the facet normal form widens to `{not: [p == v, …]}` (exclude), text bounds
(`listed >= "2026-10-19"`), `{or: [!a.isEmpty(), !b.isEmpty()]}` (has, any of) and `p.contains("x")` / an `{or:}` of
them over several properties (search); a clause no facet of this rail can draw (a property it has no facet for, two
values under a single choice, a max under "& up") stays custom, verbatim. Each kind copies one site's widget
(`KINDS` in facets.js; gallery/examples/filters-gallery/kinds.html cites them).

| `as:` | Draws | Writes | Kind's options |
|---|---|---|---|
| `values` | checkboxes, counts, Show N more, find box | `p == v` / `{or:}`; `.contains` on a list | `limit`, `sort: count\|alpha\|value`, `order`, `searchable`, `exclude: true` (a ⊘ per value: `{not: […]}`) |
| `select` | Any + radios, or a dropdown | one `p == v` | `any`, `dropdown` |
| `toggle` | a switch | `p == <value>` | `value` (default `true`; Algolia's `on`, renamed: YAML 1.1 reads `on:` as true), `text` |
| `has` | "Has a value" per property | `!p.isEmpty()` each, or `{or:}` of them | `properties`, `match: all\|any` (the reader can switch) |
| `range` | min / max boxes (dates on a date property) | `p >= a`, `p <= b` | `unit`, `choices` (dropdown pairs) |
| `slider` / `slider-histogram` | two thumbs; the second with the distribution above (bars outside the range dim) | `p >= a`, `p <= b` | `log`, `bins`, `unit` |
| `buckets` | preset ranges as chips | `p >= a`, `p < b` | `buckets: [edges] \| [{label, min, max}]` (default nice edges), `log`, `unit` |
| `rating` / `min-level` | "★★★☆ & up" / "Level ≥ N" | `p >= N` | `max`, `min`, `style: stars\|steps` |
| `date` | from / until, presets, "Older than" | `p >= "date"`, `p < "date"` | `presets: [7d, 30d, 6m, 1y, year]`, `older: […]` (relative presets are stored as the ISO date they mean when picked) |
| `chips`, `swatch`, `gallery`, `picture-list`, `grid` | pressable values: tags; logos / colours / monograms; picture tiles; a drawing per row; a compact grid | as `values` | `images: {value: path}` or `image: <property>`, `colors`, `columns`, `limit`, `sort` |
| `listbox` | a native multi-select (Digi-Key) | as `values` | `size` |
| `tree` | a hierarchical menu | one `p == v` per level | `levels: [outer, inner, …]` |
| `search` | a text box | `p.contains("x")`, `{or:}` over properties, or `.startsWith` | `properties`, `match: contains\|startsWith`, `placeholder` |
| `popular` | named shortcuts with counts | each option's clause | `options: [expr \| {label, filter}]` |
| `current` | every pick as a removable chip, Clear all | (removes) | |

Every kind also takes `label`, `info` (the ⓘ; default `properties.<p>.description`, then the field's note), `diagram`
(a drawing at the top of the facet; a path relative to the `.base` file, as `images` are; a `.svg` is drawn in the text
colour, so one file reads in light and dark) and `collapsed`. **A view may carry `facets:`** (a recipe): while it is
open the rail is that list (`[]`: none, the Filter menu edits the tree). **The URL** stays readable: `?p=a,b`,
`p!=a` (exclude), `p=a..b` with `>` / `<` marking an exclusive bound (`price=50..<100`), `p~=text` (search; `p^=`
starts with), `has=p,q`, `hasany=p,q`; links written before this amendment read the same. **Keyboard and screen
readers:** native controls or buttons with `aria-pressed` / `aria-expanded`, each group labelled, the match count a
polite live region, focus kept across a redraw. **Phone:** the rail is a closed disclosure under 700 px. Both checkers
validate every kind and option (did you mean …) and that a kind fits its property's type. [tests/unit/facets.test.mjs;
tools/test_check_facets.py; gallery/examples/filters-gallery/checks.py]

**Addendum 2026-10-28 (PEP 0010 P0; sim2real gaps #9, #14):** one string of clauses joined by `&&` at its top level
(`run_set == "held-out" && device == "J3 elbow"`, as a dataset's `filters:` may be written) is read clause by clause
(`conjuncts` in facets.js): each clause the rail can draw is the rail's, the others stay custom one by one, and a string
none of whose clauses it can draw stays whole, as written; a top-level `||`, an open quote or bracket keep it whole. It
used to read as one custom clause, so every facet counted under both picks and a picker listed only its own pick. The
rail writes it back as `{and: […]}`, the same rows. Each `<data-facets>` names its radio groups and heading ids for
itself, so two rails over one property on a page (a dashboard's servo and camera `device`) each keep their own pick
checked. [tests/unit/facets-conjuncts.test.mjs; tests/browser/p0_checks.py]

**Addendum 2026-10-29 (kit gap 8; PEP 0010 §8):** a facet may name **`parent: <property>`**, another facet of its rail
whose pick its values nest under (a run under its device: Grafana's chained variables, Kibana's parent control). The
parent's counts leave out its children's picks (and theirs), so it lists every value while a child is picked; the
child's counts apply the parent's pick, as before. A parent pick that a child's pick no longer fits moves a single pick
(select) to the child's first listed value that fits (its `order`, else most rows first), and keeps a multi-value
pick's values that fit (none left: no pick), in the same change: one filter, one redraw, one URL. A link keeps what it
says (a moment that pairs a run with another device draws nothing). `settleChildren` and `descendants` in facets.js.
Both checkers refuse a parent that names no facet of the rail (did you mean) or the facet itself. WHY: the robotics
templates' Driver and Servo listed only the picked run's board, so another board took a reset of Run first.
[tests/unit/kit-gaps.test.mjs, check-kit-gaps.test.mjs; tests/browser/kit_gaps_checks.py]

## 8. A gallery case

```
gallery/examples/<case>/
  README.md            "# Title", a one-paragraph summary (the gallery card), then bullets: Replaces, Shows, Data
  views.base           the views; `data:` names the data file in this folder
  <data>.json|csv|...  the data (public-safe only: never private track figures)
  <data>.schema.json   optional field schema (§3)
  skin.css             optional: the app's tokens mapped onto --data-*, scoped to .data-ui-skin, light and dark
  checks.py            optional: run(ctx, path) browser checks (tests/browser/checks.py calls it; see the two cases)
  snapshot / source    optional: how the data was made (gallery/tools/build_examples.py for the robotparts cases)
```

The site lists a case as soon as its folder has a `views.base`; its page shows the live views beside every file.
`checks.py` gets `ctx.page(path, width, height, dark, mobile)`, `ctx.check(name, ok, value)`, `ctx.shot(page, name)`
and `ctx.base`; the page's `<data-views>` is `#example`.


**Amendment 2026-10-26:**
- A case folder may hold subfolders (photos, SVGs, stills). The site copies every subfolder except `source/`, which holds only the scripts that rebuild the data.
- A case may add `site.json` with page options that aren't view config: `{"editable": true}` renders `<data-views editable>`, so a board drag or form edit lands on the site.
- The browser helper `ctx.page()` waits for every `<data-views>`' status line, not for a table row, so a case whose first view is cards, kanban or a chart loads correctly.

## 9. What a view lane may touch

- **Yours:** `packages/views/<your folder>/`, new `gallery/examples/<your case>/` folders (a case may point its
  `data:` at a sibling's file, `../robotparts-actuators/actuators.json`), and their `checks.py`.
- **Not yours:** `packages/core/`, this file, `schemas/`, `package.json` and the lockfile (every library in
  docs/VIEWS.md is installed; ask, do not install), `build.mjs`, `site/`, the two existing gallery cases (the
  orchestrator folds your views into them after merge), `tests/browser/checks.py`.
- **Done means:** `npm test` green, your manifest `status: "built"`, the Views page shows it built, your case's
  checks pass light and dark at 1280 and 390 px, nothing from another origin.

## 10. Amendment 2026-10-26 (core pass; additive)

Closes the gaps the four view lanes reported. Nothing here removes or renames a host call, an input field or a key;
each item has a test (named in brackets).

- **Trees are TanStack sub-rows, in the core.** `rowModel` nests the rows of a `table` or `list` view with `tree:
  {parent} | {path, separator}` through table-core's `getSubRows` and expanding feature, so `input.table` holds the
  outline and a view folds it with `setExpanded` / `row.toggleExpanded()` as it folds groups. The core exports
  `treeSpec(view, columns)`, `treeRows(rows, spec)` -> `{roots, children}` and `isHeading(original)`. Rules: rows
  keep the sort among their siblings; a row whose parent is not among the rows starts at the top level; a parent
  cycle is cut where it closes; a path's missing ancestors are headings (`{id: '@a.b', _heading: 'b', _path, _first}`)
  that are in `input.table` but never in `input.rows` or `groups`; with `groupBy`, a group holds the top of each
  tree. The table view now honours `tree:`; the list view's own nesting (`packages/views/tree`) is gone. Other types
  ignore the key. [tests/unit/rowmodel.test.mjs "tree:"; the dataclass-viewer case's "tree on a table" and outline checks]
- **The side peek reads `record.sections` and `edit`.** `host.open` lays the fields out in the current view's
  `record.sections` (each section's properties, in order, "—" for a missing one), else as before; with `edit: true`
  on the view the peek is the record view's form and proposes the changed fields through `propose`. The form module
  moved into the core (`fieldHtml`, `readEdits`, `lockedBecause` from `@data-ui/core`; `packages/views/form` is gone).
  Both keys were already valid on every view. [the dataclass-viewer case's browser checks "peek:"]
- **`input.dataset.url` and `mediaUrl(src, dataset)`.** `dataset.url` is the data file's URL (the `data` attribute,
  or the `.base` file's `data:` against the `.base` URL; a dataset set from script may carry `url`, else the page's
  URL; `el.dataUrl` reads it). `mediaUrl(src, input.dataset)` resolves a relative image or file path against it, as
  the 2026-10-26 amendment (§1) says. Every view that draws an image calls it (cards, kanban, chart's hover card,
  compare, record, list, table); the per-view workarounds are gone. [tests/unit/format.test.mjs; the actuator-charts
  case's hover check, whose photos now live beside the data, not beside the page]
- **KPI direction per card: `kpi.compare.better` may name a property.** `better: higher | lower | <property>`; with a
  property, each card reads `higher` or `lower` from its newest row (no direction: the delta is drawn neutral). This
  replaces the kpi lane's implicit rule (a column that happens to be called `better` overrode `compare.better`). WHY
  a named key, not a reserved column: the `.base` file is the API, so the rule is visible in it and checked against
  the data like `against:`, and no dataset changes meaning because of a column's name. [tests/unit/check.test.mjs;
  the Vibe Tracks KPI case's delta check]
- **Join, not adopted.** The actuator-charts case needed `photo` on robotparts' actuator rows; `photo` is now a column
  of those rows (`gallery/tools/build_examples.py`, with its 150 photos in `robotparts-actuators/photos/`), and the
  chart case's `data:` points at them. WHY no `.base` join: a column the data needs belongs in the data's producer;
  a join is a second data model in the view grammar, and stock Bases has none.
- **A chart needs an `encoding`, a `mark` or a `layer`.** With no mark, the chart view's Show Me defaults pick one
  from the encoded fields' types (SPEC §8.5), so `chart: {encoding: {x: {field: mass}, y: {field: peak_torque}}}`
  checks clean. [tests/unit/check.test.mjs]
- **A case names its app.** A gallery case's README may carry `- **App:** <app>` beside Replaces, Shows and Data
  (§8); the site groups and filters the gallery by it, and the landing page's Replaces table lists every case's
  Replaces bullet under its app. [tests/browser/checks.py "gallery:", "landing:"]
- **`<data-kpi>` and `<data-sparkline>` on a plain page.** Load `data-ui.css` and `dist/views/kpi.js` (package export
  `data-ui/kpi`); the bundle defines both elements and adds its own stylesheet, under the name the registry uses, so
  a page that also opens a `type: kpi` view gets one copy. [dist/site/plain/kpi.html, tests/browser/checks.py
  "plain page:"]


## 11. Amendment 2026-10-26 (resizable side panels; additive)

Every side panel is resizable by dragging, on by default. WHY (Zach, 2026-10-26, memory `feedback_resizable_panels`):
he always wants resizable, remembered side panels, asked for them before, and the 2026.10.25 and .26 robotparts
releases still shipped fixed ones. The code is `packages/core/src/resize.js` and `styles/resize.css`.

- **The kit's own panels.** When a `<data-views>` starts, its side peek gets a handle on its left edge (min 320 px,
  max 1200 px and never closer than 160 px to the element's left edge), and every `<data-facets for="<its id>">` rail
  gets one on its right edge (180-560 px, leaving 320 px beside it). The peek still closes with ✕ or Escape. Widths are
  stored per panel in localStorage under `data-ui/panel-width/peek:<views id>` and `…/rail:<views id>` (try/catch).
- **Opting out:** `data-resizable="off"` on the `<data-views>`, the `<data-facets>` or any ancestor. A rail inside a
  host panel that is itself `[data-resizable]` gets no handle of its own (the host's panel is the one that resizes).
- **A host's own panel:** `data-resizable="left|right"` (the edge the handle sits on) on any element, with optional
  `data-resizable-min`, `data-resizable-max` (px, default 160 / 640) and `data-resizable-key` (the storage name;
  default the element's id). data-ui.js gives every such element its handle when it loads; a page that loads nothing
  else of the kit loads **`dist/resize.js`** (a module of about 5 KB with its stylesheet inside), which does the same.
  From script: `makeResizable(el, {edge, min, max, keep, key, label})` → `{handle, width, set(px), reset(), destroy()}`,
  `autoResize(root)`, `resizeKit(viewsEl)`, all exported from the core (and the first two from `resize.js`).
- **The host owns the layout.** The width is written as `--data-panel-width: <n>px` on the panel, and only once one is
  set (dragged or remembered); the panel also gets `dv-resizable`, and `dv-sized` while a width is set. A host panel
  reads it in the host's CSS, `width: var(--data-panel-width, <default>)`, and a grid track holding it is `auto`. The
  kit's peek and `<data-facets>` read it in `resize.css` above 700 px; below, they keep core.css's phone layout.
- **The handle:** `.dv-splitter` (`.dv-splitter-left|right`; not `.dv-resize`, the table's column resizer), a sibling of the panel, absolutely placed on its edge (not a child, so it does not scroll away with
  a panel that scrolls), `role="separator"`, focusable, a visible 1px line that turns 3px in the accent on hover, focus
  and drag. Pointer drag with capture; ← / → move the edge 16 px; a double-click resets to the host's default and
  forgets the stored width. It hides while the panel is hidden or fills its parent (a phone's stacked layout), so it
  never widens a page sideways.
- [tests/browser/checks.py "plain page: resize.js alone"; the robotparts-actuators case's "resize peek:", "resize
  rail:" and "resize at 390 px" checks, each measured with getBoundingClientRect]

## 12. Amendment 2026-10-26 (frame; additive)

How a `<data-views>` sits in its page. Zach on robotparts.dev/actuator/: "I don't like how the table and gallery seem
like separate component. I think it's caused by the additional border etc." Nothing changes unless a host opts in:
no attribute is `boxed`, today's look, pixel for pixel. The why of each frame is `packages/core/src/frame.js`; the look
is `packages/core/styles/frame.css` (in `dist/data-ui.css`). [tests/browser/frame_checks.py, 72 measured checks]

- **Attribute `frame="boxed|flush|tabs|sheet|page|bleed"`** on `<data-views>`; an unknown value is `boxed`. It may
  change on a live element: the view is re-made on the new scroller and keeps its view, filters and search.

  | frame | border | surface | tabs | toolbar | scroll | width | rows | gallery |
  |---|---|---|---|---|---|---|---|---|
  | `boxed` | 1 px box | header band | widget header | beside the tabs | the box's own | content | rules | bordered cards |
  | `flush` | none | none | widget header | beside the tabs | the box's own | content | rules, no header fill | bordered cards |
  | `tabs` | none | none | the page's nav (rule across the column) | a row under the tabs | the box's own | content | zebra | borderless tiles |
  | `sheet` | none | tinted header, tinted well | pills | beside the tabs | the box's own | content | rules | white tiles on the tint |
  | `page` | none | none | sticky | sticky, beside the tabs | **the page's** | content | rules | bordered cards |
  | `bleed` | none | tinted sticky band | sticky | sticky, beside the tabs | **the page's** | edge to edge | zebra | borderless tiles |

- **`page` and `bleed` scroll with the page.** The element is as tall as its rows; the nearest scrolling ancestor (else
  the window) scrolls them. The band (tabs, toolbar, count) sticks to the scroller's top, the table's column header
  sticks under it (a scroll-driven animation; a scroll listener where unsupported), a wide table's sideways scrollbar
  is pinned to the scroller's bottom, a list view virtualises against the page (TanStack's scroll margin), a view that
  is not a list (chart, board, map, …) fills the scroller's visible height under the band, the side peek is pinned to
  the scroller's visible box, and a new tab opened from deep in the rows starts at its own top.
- **Two host tokens, both optional:** `--data-sticky-top` (a host's own sticky header above the scroller; default 0) and
  `--data-bleed` (the side padding of the host's column, which `bleed` reaches across; default 0).
- **`host.scroller`** (read-only; added to §1's host): the element or `window` that scrolls the rows under `page` /
  `bleed`, else `null` (the view's own box). A view that virtualises builds its Virtualizer with
  `scrollOptions(host, () => ownBox, virtualCore)`, keeps its scroll margin with `syncMargin(host, virt, listEl,
  fallback)` and positions items at `start - scrollMargin`; "back to the top" is `scrollToStart(host, ownBox)`. The
  table, cards and list views do; a view that does not virtualise needs nothing. Exported from `@data-ui/core`:
  `FRAMES, frameOf, scrollParent, offsetIn, scrollOptions, syncMargin, scrollToStart`.
- **The table's `tbody[data-p]`** is the first drawn row's parity (0 or 1), so a zebra stripes by row number while the
  virtualiser recycles rows.

## 13. Amendment 2026-10-26 (open modes; additive)

How a record opens is one setting per view, with three modes. WHY three and one setting (Notion's per-view "Open pages
in"; Atlassian had to un-force its preview panel): `docs/peps/0003-open-modes.md`. The code is `packages/core/src/open.js`
and `styles/open.css`; nothing here removes or renames a host call, an input field or a key.

- **The key.** `open:` on a view, at the top of the `.base` file (every view that does not say), and the attribute
  `open="expand|side|link"` on `<data-views>`. Short form `open: side`; long form `open: {mode, splitAt, url}`. Field by
  field, the view's key wins over the attribute, which wins over the file's top level; with nothing set it is
  `{mode: side, splitAt: 1100}`. Both checkers know it: an unknown mode (`open: sideways`) is an error, and with data
  that names no `linkProperty`, `link` with no `url:` is a warning (it falls back to `side`). `openSetting(view, base,
  attr)` in `open.js` is the rule.
- **The page URL.** A record's page is its `open.url` property's value, else the dataset's `linkProperty` (robotparts'
  rows: `url`); a relative one resolves against the data file's URL, as a photo's path does (§1 amendment). The key
  names a property (a formula is for display columns: §36, SPEC §5.6). **No URL, no drill-down:** no title link, no "Open
  page", and a double-click or Enter does only the mode's own thing.
- **Every mode, with a URL:** the title cell (the view's first column; a card's title) is a real `<a href>`: a plain
  click is routed by the mode, a ⌘/Ctrl/Shift/middle click is the browser's. A double-click (the second click of two
  on the same record) or Enter on a focused row or card calls `location.assign(url)`; a double-click selects no text.
  Rows and cards are `touch-action: manipulation`.
- **`expand`** (a table or cards view): a click or Space toggles a band under the row, several at once: the photo (the
  view's `image`, else `imageProperty`; none, no square), the title and kind, up to six key-spec chips, every visible
  property in a compact grid, and "Open page ↗" when there is a URL. The band is part of its row's virtual item
  (`estimateSize` per index, re-measured once drawn), so rows below move by exactly its height and it survives
  scrolling away and back. A card grows in place as a taller item of its lane (the lanes reflow; nothing overlaps).
  Bands are not in the URL.
- **`side`** (the default, and every view that is not a table or cards): a click opens the side peek with the rich
  record header (photo, title as a link, kind, `‹ n of N ›`, "Open page ↗", key-spec chips, Specs / Sources tabs when
  a field carries a basis or source) over the host's own fields, so `record.sections`, `edit: true`'s form and "every
  value behind it" (`dataset.detail`) are unchanged. Responsive, one setting: when the `<data-views>` element is at least
  `splitAt` px wide the pane docks on the right under the toolbar and the list narrows beside it (`dv-split`; nothing
  is covered); narrower, the pane is today's overlay; at a viewport of 640 px or less it is full screen with a "‹ Back"
  (`dv-full`). The pane keeps §11's handle and remembered width (`data-ui/panel-width/peek:<id>`) in split and overlay.
  A pivot cell or a group still opens "the records behind" in the same pane.
- **`link`** (a table or cards view, with a URL; else `side`): a plain click anywhere on the row or card goes to the
  page (a click that ends a text selection does not); Ctrl/⌘-click and a middle click open a new tab; a checkbox before
  the title selects without navigating, and the status line says "N selected · Clear".
- **Keyboard:** with the peek open on a record, ↑/↓ and j/k (on a row or in the peek) step to the next or previous row
  in the view's order (`input.rows`); the pane, its `n of N` and the row's focus and highlight follow. Escape closes.
  Enter on a row opens the page (no URL: the mode's own action); Space opens or closes the peek, toggles a band, or
  ticks the row in link mode.
- **URL params:** the peek on a record is `peek=<id>` in the hash: pushed when it opens, replaced while stepping, so
  Back closes it, and a link with `peek=<id>` reopens it. A records peek (a pivot cell) is not in the URL; `no-url`
  turns it off.
- **For views and hosts:** `host.opener` is the controller while the view is a table or cards (else null); a view
  that draws records reads `titleHtml(row, html)`, `rowClass(id)`, and for a table `bandHeight(id)`,
  `setBandHeight(id, px)`, `bandHtml(row, ncols)`, for cards `cardExtra(row)`, `cardMoreHtml(row)`, and may define
  `openMarks()` (a band opened or closed) and `reveal(id)` (scroll a record into view). Rows and cards carry
  `data-id`. The element carries `data-open="expand|side|link"` (the current view's mode) and, while the peek is open,
  `dv-split` or `dv-full`.
- **Lifecycle:** what open modes holds outside the element (the window's popstate, the phone query, its
  ResizeObservers, a page scroller's scroll) is released when the element leaves the page and made once when it is
  put back, as are the side panels' drag handles (src/resize.js). [tests/browser/lifecycle_checks.py "open modes:"]
- **Addendum 2026-10-29 (PEP 0010 P5):** a `record.sections[]` entry may embed a `view` bound to the peeked row, and a field the
  view displays as `link` or `status` is drawn so in the peek (§35).
- [tests/unit/open.test.mjs; tests/unit/check.test.mjs "open modes"; tools/test_check_views.py `test_open_modes`; the
  robotparts-actuators case's "open expand", "open side, split / overlay / resize / URL / keyboard", "open side on a
  phone", "open link", "open, no URL" and "open expand (light / dark)" checks, measured with getBoundingClientRect. The
  case's "resize at 390 px" check now expects the full-screen peek on a phone.]

## 14. Amendment 2026-10-26 (time groups and peek trail; additive)

Two capabilities, each failing-first tested. Nothing here removes or renames a host call, an input field or a key.

**Time groups.** A group level (`groupBy`, `subGroupBy`, in every view and in the pivot) may carry `by: day | week |
month | quarter | year` and `gaps: true`: `groupBy: {property: started, by: week}`. The code is `grammar.js`
(`TIME_GRAINS`, `timeBucket`, `bucketLabel`, `bucketStart`, `nextBucket`, exported from `@data-ui/core`) and
`rowmodel.js`.

- **Buckets.** A bucket's key is text that sorts in time order: day `2026-10-20`, week `2026-10-19` (its Monday: ISO
  weeks start on Monday), month `2026-10`, quarter `2026-Q4`, year `2026`. Labels: `Tue 20 Oct 2026`, `Week of 19 Oct
  2026`, `Oct 2026`, `Q4 2026`, `2026` (English month names, on every machine).
- **The date is the one written.** A date-only value has no time zone and is never shifted. A datetime is bucketed by
  the calendar date written in it, in its own offset: `2026-09-30T23:30:00-07:00` is 30 Sep (1 Oct in UTC), `…Z` is
  its UTC date; it is never converted to the viewer's zone. A value that is not ISO date text (a number, a list, a
  date that does not exist such as `2026-02-30`) has no bucket and falls in "No <property>", last.
- **Order.** A time level is always in time order, oldest first, newest first with `direction: DESC`. Its rows tie,
  so the view's `sort` orders the rows inside a bucket, also a sort on the same date (`rowmodel.js`'s twin column).
- **Empty buckets** are left out. `gaps: true` keeps every bucket from the first to the last, an empty one as a group
  with `rows: []` in `input.groups` (in the level's order, at either level). The table and the list draw TanStack's
  groups, which have no empty ones; the views that read `input.groups` (cards, kanban, kpi, calendar, timeline, graph)
  show them.
- **What a view receives (§2).** A time level's group is `{key: <bucket key>, property, by, rows}`; the model's
  `columns[property].by` names the grain, and `groupLabel(columns, property, keyOrRowValue)` writes the bucket's label
  from a key or from a row's date, so a view that labels groups from a leaf (the table, the list) needs no change. A
  pivot makes one row per bucket (its cell for the property holds the bucket's key).
- **The chart's time axis.** A date channel may carry `by:` too: `x: {field: started, by: week}` plots each row in its
  bucket, one band per bucket labelled as the table labels it ("Week of 21 Sep 2026"), every bucket from the whole
  data's first to its last in time order, so an empty week is an empty band and the axis holds still while filtering
  (Tableau's discrete date); `y: {aggregate: count}` then draws one mark per bucket. A row with no date is not drawn,
  and the status line says so. WHY not Vega-Lite's `timeUnit`: its weeks start on Sunday and it reads dates in the
  viewer's zone, so its buckets would differ from the table's.
- **The Group menu** offers "Dates by: each date | day | week (from Monday) | month | quarter | year" when the level's
  property is a date (or already has `by:`); a new property starts without a grain. The Group button reads
  "Group: Started by week".
- **Both checkers** (schema `$defs.group.by` / `gaps`, `$defs.timeGrain`, `$defs.channel.by`): an unknown grain is an
  error with a suggestion (`by: weekly` → did you mean 'week'?), `gaps` must be a yes/no, and with the data's types a
  grain on a property that is not a date warns.
- [tests/unit/time-groups.test.mjs (counts per week, month, quarter, year and day against an independent day count over
  Vibe Tracks' 120 runs, in a +14 h time zone); tools/test_check_views.py `test_time_groups`; the ml-experiments case's
  "ML runs by week" and "ML runs per week" checks (Python's datetime as the oracle; the Group menu's grain picker)]

**The peek's trail.** Notion's side peek keeps the path of pages opened from inside it, with "Open as page" (⤢); so
does data-ui's. The code is `open.js` (`relationProps`, `OpenModes.follow / jump / back / relationHtml`) and
`styles/open.css`.

- **A relation is declared, never guessed** (feedback_do_not_invent_undefined_relationships): a column the data marks
  `relation: true` (a field schema passes `relation` through), or a property any view of the `.base` file names as
  `edges.property` (a graph's edges) or `tree.parent`. Its values are ids of rows of the same data.
- **In the peek** a relation's value is a link per record it names (the record's title; an id no row has stays as
  written), in the fields and the key-spec chips. Its `href` is the record's page (`open.url`), else this page with
  that record's peek. A plain click opens the record in the same peek and adds it to the trail; a modified or middle
  click is the browser's. A link in the peek to another record's page URL does the same.
- **The trail** shows over the title once there are two records: `Supply › Regen clamp › XT30 junction`, every crumb
  before the current one a button that jumps back (dropping the steps after it), the current one `aria-current`. A
  long title ends in an ellipsis; the whole title is its tooltip. Opening a record any other way (a row, ↑/↓, a view
  change) starts a new trail.
- **Back.** Escape and the peek's ‹ Back step back one record before they close the peek. The browser's Back still
  closes the peek: following a relation replaces the history entry, as stepping with ↑/↓ does (§13: Back is not a
  record-by-record undo).
- **The URL** is `peek=<current>&trail=<first>&trail=<second>…` in the hash, replaced on every step; a reload or a
  shared link reopens the same record with the same trail (a step that names no row is dropped). `no-url` leaves it
  alone.
- **⤢ (Open as page)**, in the peek's header beside ✕, is a real link to the current record's page when it has one
  (§13's page URL), else absent.
- **Every mode**: split, overlay and a phone's full screen (where ‹ Back is shown).
- **For hosts and views:** `host.open(id)` is unchanged; `el._open.relationHtml(row, column)` is the seam the host's
  peek fields call.
- [tests/unit/peek-trail.test.mjs; the rack-wiring case's "peek trail" checks (split at 1600 px, overlay at 1000 px,
  phone at 390 px: three crumbs measured inside the pane, the first crumb, Escape and ‹ Back, peek= and trail=, reload,
  ⤢); tests/browser/lifecycle_checks.py "peek trail:" (removed and put back five times, nothing held)]

## 15. Amendment 2026-10-26 (toolbar: the bar, its variants, the query bar and selection; additive)

(Numbered 15: §13 is open modes and §14 time groups and the peek's trail, which landed first; §16 (explain the data)
was numbered around this one, and the dashboards lane, which had been promised §14, takes the next free number. This
amendment and its notes were written as §13 on lane/toolbar-mix and renumbered when they landed after open modes.)

Zach's pick of 2026-10-26 ("Definitely yes I like the mix"; his notes and twelve references are in
`zach_brain/Sources/Daily Notes/Daily Note - Oct 26 2026.md`): P6's Shopify pill bar, Obsidian Bases' view menu
inside the view chip, filter pills and the rail showing the same state both ways, and a Layout row in the settings.
One change from the proposals: **the host page's header search stays the site's global search**; the table gets its
own query bar inside the bar. The why and the forks are `docs/peps/0002-toolbar.md`. Nothing here removes or renames
an attribute, method, event, host call or key: `toolbar="full"` stays the default and draws what it drew.

**Attributes** (each is read live: changing one redraws the chrome and keeps the view, the filters, the query and the
selection):

| Attribute | Values (default first) | Does |
|---|---|---|
| `toolbar` | `full \| bar \| compact \| none` | `bar` is the new chrome: one row (view chip or tabs · query bar · filter control · display button), plus a pill row and a bulk bar when they have something to show. |
| `views` | `auto \| dropdown \| tabs` | `bar` only. `dropdown`: one chip, the current view's icon and name and an up/down chevron that lights on hover; its menu is Bases' (find box, a ✓ on the current view, a › per view that opens its configuration, "Add view" with a Notion-style grid of layout types). `tabs`: every view as a tab and a `+`, overflow into "N more…" (Notion). `auto`: tabs while they all fit on one line, else the dropdown; re-decided on resize (a ResizeObserver). |
| `filters` | a space-separated set of `pills`, `expanded`, `query-tokens`, `rail` (default `pills`) | `pills` (Notion, compact): one Filter button with a count; every clause of the all-views filter shows as a removable pill in a row under the bar ("Brand: Steadywin, CubeMars ✕", "+ Filter", "Clear"). `expanded` (Obsidian, spread out): Sort · Group · Filter · Properties as labelled words in the bar, each opening its menu; it replaces `pills`' single button (both given: `expanded` wins). `query-tokens`: every clause shows as a token inside the query bar instead of in a pill row. `rail`: the bar gets a "Filters" toggle that shows and hides the linked `<data-facets for="<this id>">` (remembered under `data-ui/rail-open/<id>`). Whichever is on, they all read and write the **one** all-views filter (`el.filters`) the rail edits, so a pick in any of them shows in all the others at once. |
| `display` | `panel \| popover` | Where the view settings open from the bar's Display button. `panel` (Notion's View settings, the default): a side panel inside the element, on its right edge, resizable (§11; min 260, max 640 px, key `data-ui/panel-width/settings:<id>`), with the view's name, Layout ›, Property visibility ›, Filter ›, Sort ›, Group ›, Copy link to view, Copy view as .base. `popover` (Linear's Display): the same rows in one popover anchored to the button. Below 700 px either opens as a full-width sheet. |
| `selectable` | absent \| present | Rows can be selected: a checkbox column in the table, a check on each card in the gallery. Click a row's checkbox: toggle; shift-click: the range from the last clicked row, in drawn order; ctrl/cmd-click (also on the row body): add or remove one; shift+ctrl/cmd: add the range to the selection. The header checkbox selects every **filtered** row (`model.rows`), or clears. A selection survives a re-sort and a view switch; rows a new filter hides leave it. |
| `query` | text | The query bar's text (below). Set it and the element parses it; the element never writes this attribute back (read `el.queryText`). |

**The query bar** (Shopify's query builder, Bases' advanced filter). One text box in the bar, `/` focuses it (when
focus is not already in a text field), placeholder "Search or filter… (try brand:)". What is typed is two things:

- **Clauses**, each one Bases expression in the all-views filter (an `{and: [...]}` item, exactly what the rail,
  the Filter menu and an agent writing the `.base` file produce):
  `prop:value` → `prop == "value"` (on a list property `prop.contains("value")`), `prop:a,b` → `{or: [...]}`,
  `-prop:value` → `prop != "value"` (`{not: [...]}` for several), `prop:>10` `>=` `<` `<=` → `prop > 10`,
  `prop:10..20` → `prop >= 10` and `prop <= 20` (`..<` exclusive, as the URL writes it), `has:prop` →
  `!prop.isEmpty()`, `prop~:text` → `prop.contains("text")`, and any Bases expression in parentheses or backticks
  (`(peak_torque / mass > 5)`) verbatim. A value with spaces is quoted (`brand:"T-Motor AK"`). Property names
  match the id or the label, case-insensitive (`peak_torque:` and `"Peak torque":`).
- **Words**: everything else is the free-text search over the view's visible properties (`el.query`, as the old
  search box).

Hints and autocomplete (a listbox under the box, `role="combobox"`/`listbox`, arrows move, Enter or Tab accepts,
Escape closes): on an empty or partial word it suggests **properties** (label, id, type icon, a sample value); after
`prop:` it suggests **operators** for its type (number: `>` `<` `..`; text: values) and **values** with their counts
under the current filters (the rail's disjunctive counts), top 12, filtered as you type; after a complete clause it
offers the next property. A clause that does not parse shows a red underline and the reason, and is not applied.
`el.queryText` is the canonical text of the current state (the filters' clauses in token form, then the words), so
the bar, the rail, the pills and the URL are the same state. `query-tokens` draws the clauses as tokens (✕ removes
one, Backspace at the start of the box removes the last). The words go in the hash as `q=`; the clauses go in the URL
as the rail's readable params already do (§7), the rest in `f=`.

**Methods** (new): `selectView(name)` (a preset's or a user view's name; returns true if found), `addView(view)` (a
view entry; saved as a user view and selected; a missing `name` becomes "<Type> N"; returns the name), `saveView(name?)`
(saves the current view as the user view `name`, default the current user view's name or "<name> (mine)"),
`search(words)` (the free text only), `setQuery(text)` (parses clauses and words, as typing does), `select(ids,
{mode: 'replace' | 'add' | 'toggle' | 'remove'})`, `selectAll()` (the filtered rows), `clearSelection()`.
`openMenu(name)` also takes `views`, `settings`, `query`, `add-view`. **Read-only properties:** `queryText`,
`selection` (the selected ids, in drawn order), `selectedRows`.

**Bulk actions.** With a selection, a bulk bar replaces the pill row (Shopify): "☑ N selected ▾" (Select all N
filtered · Select none), then the actions, then "Show only selected" (a toggle; it narrows the view to the selection
without changing the filter). `el.actions = [{id, label, icon?, min?, max?, run(rows, el)}]` sets the host's actions
(an action outside its `min`/`max` selection count is disabled with the reason in its title). The defaults, used when
the host sets none and kept when the host lists their ids as strings (`el.actions = ['compare', {...}, 'export-csv']`):
`compare` (2-6 rows: switches to a `compare` view of them, `compare.rows: [ids]`), `copy-ids` (the ids, one per line,
to the clipboard), `export-csv` (the selected rows' visible properties as a `.csv` download named after the view),
`clear`. Escape clears the selection (after an open menu and an open peek, in that order).

**Per-layout settings** (each one key of the view entry, listed in `schemas/view.schema.json`, shown under Layout in
the settings): table `rowHeight: short|medium|tall|extra` (Bases'), `wrap: true` (cells wrap instead of clipping with
an ellipsis), `freeze: 0|1` (the first column stays put while the table scrolls sideways; default 1); cards
`maxColumns: 1-12` (the gallery never lays out more than this many columns, however wide), `cardSize`, `imageFit`,
`imageAspectRatio`, `image`, and the shown fields are Property visibility (`order`); list `markers`, `separator`;
chart: its existing `chart`/`guides` keys.

**Events** (new): `data-views-select {ids, rows}` after every selection change; `data-views-action {id, ids, rows}`
before an action runs (cancelable: `preventDefault()` skips the action's own `run`).

**Light DOM classes** for hosts that skin it: `.dv-bar`, `.dv-viewchip`, `.dv-viewtabs`, `.dv-query`, `.dv-qtoken`,
`.dv-suggest`, `.dv-pills`, `.dv-pill`, `.dv-bulk`, `.dv-settings` (panel or popover), `.dv-sel` (a selected row or
card). Colours only from tokens; light and dark; at 390 px the bar wraps to two lines (the query bar full width) and
never scrolls the page sideways.

[tests/unit/query.test.mjs; tests/browser/checks.py "bar:" checks; gallery/examples/robotparts-actuators "bar" page]

**§15 note, 2026-10-26 (lane A, the bar; additive, no public name changed):**
- `views="auto"`'s "while they all fit on one line" is the bar's whole line: the tabs, the query box's 200 px minimum
  and the tools. A bar narrower than 640 px is two lines (the query box takes the second), so there auto always shows
  the chip; `views="tabs"` still shows the tabs that fit there, then "N more…".
- Under `toolbar="bar"`, `openMenu('group' | 'sort' | 'filter' | 'properties')` opens under the bar's own word when
  `filters` has `expanded` (the Filter menu under the Filter button otherwise), else View settings at that page;
  `openMenu('layout')` opens View settings at Layout; `'save'` and `'more'` open under Save view or Display.
- "Show only selected" is `rowModel(dataset, base, view, {query, filters, only})`: `only`, a Set of ids, narrows the
  rows after the search and before sort and group; `el._onlySelected` (lane B's toggle) turns it on, and the status
  line adds "showing N selected".
- More light DOM classes the bar uses: `.dv-viewmenu` (the chip's menu, a `.dv-pop`), `.dv-vtab`, `.dv-layouts` /
  `.dv-layout` (the layout grid), `.dv-settings-panel` / `.dv-settings-pop`, `.dv-pill-x`; every bar control carries
  `data-bar="…"`.
- **Name clash, open:** the table view's bar cells also use `.dv-bar` (`packages/views/table/src/table.css`: `.dv-bar
  {position: absolute}`, `.dv-bar span {display: block; height: 100%; background: …}`). The bar undoes those rules on
  itself and on its own views and tools (toolbar.css), not inside `.dv-bar-query` (lane B's spans there still get
  them), until the table's are scoped to its cells (e.g. `.dv-table .dv-bar`); scoping them is the table's owner's
  change.

**§15 note 2026-10-26 (lane B, query + selection; additive except the first item):**
- `-prop:value` is `{not: [prop == "value"]}` for one value as for several, not `prop != "value"`: that is the rail's
  exclude (facets.js normal form), so a typed `-brand:KST` ticks the rail's ⊘ and reads `?brand!=KST` in the URL, and
  `prop != "v"` stays custom there. The two read the same rows. A `prop != "v"` the Filter menu wrote shows as the raw
  token `(brand != "KST")`, so the round-trip law (`parseQuery(formatQuery(f, w))` gives back `f`'s clauses and `w`)
  still holds.
- The grammar also reads `prop^:text` → `prop.startsWith("text")` (the rail's search with `match: startsWith`; the URL's
  `p^=`), `has:a,b` → `{or: [!a.isEmpty(), !b.isEmpty()]}` (the rail's has-any; a comma in the bar always means "or"),
  `c1 OR c2` → `{or: [c1, c2]}` (each one expression; the rail's search over several properties) and `-(expr)` →
  `{not: [expr]}`. With these every clause `fromRail` writes has a token form (tests/unit/query.test.mjs).
- The example `(peak_torque / mass > 5)` does not compile: grammar.js has no arithmetic; `(peak_torque > 10 || mass < 100)` does.
- The table's bar-display cell is `.dv-barfill` (was `.dv-bar`, which §15 gives to the toolbar; the cell's
  `position: absolute` laid the bar over the view).
- `resolveActions(list, count)` takes the selection size and returns each action with `disabled` and `reason`;
  `runAction(el, action)` dispatches `data-views-action` and runs it (both in toolbar/selection.js).

**§15 note, 2026-10-26 (lane A, the reader's Frame; additive):** View settings (panel and popover) has a **Frame ›**
row after Layout: the six frames of §12 (`boxed flush tabs sheet page bleed`), each with a one-line hint. A pick sets
the element's `frame` attribute live and is kept under `data-ui/frame/<id>` (try/catch); on start a kept pick overrides
the host's `frame`; "Reset to page default" forgets it and puts the host's value back. **Attribute
`settings-frame="off"`** hides the row (and a kept pick is then ignored). The list is frame.js's `FRAMES`.

**§15 note, 2026-10-26 (the bar under each frame, §12; additive):** under `toolbar="bar"` the band a frame styles is
`.dv-bar` and `.dv-subbar`, not the hidden `.dv-head` (styles/toolbar.css repeats each frame's look for them). Under
`page` / `bleed` the bar sticks at `--data-sticky-top`, the pill / bulk row under it, then the status line; frame.js
measures `--dv-head-h` (bar + subbar) and a new `--dv-bar-h` from them. View settings' side panel is pinned to the
scroller's visible box as the peek is, its top right under the bar; its popover follows the stuck Display button.
Under `frame="tabs"` the bar's view tabs (`views="tabs"`, or `auto` when they fit) take a line of their own over a rule,
the open one underlined, the query box and tools a row beneath. A frame set while the element starts (a kept reader
pick) does not re-make the view: `_start` frames it once.

**§15 note, 2026-10-26 (the bar beside open modes, §13; additive):** View settings and the record pane never cover
each other. With the pane split (`dv-split`) the settings panel docks on the pane's left; with an overlay or full-screen
pane the newer of the two closes the other (opening View settings closes the pane; opening a record closes the
settings). Under `toolbar="bar"` an overlay pane starts under the bar (`--dv-bar-bottom`), so the bar stays usable while
a record is open. A row's or card's selection checkbox (`.dv-selbox`) is the selection's in every open mode: it never
opens a record, toggles a band or navigates. Escape closes a menu, then View settings, then the pane, then clears the
selection. A slider among a layout's settings shows its value, or its option's `none` text while unset ("no cap"); a
property select lists the selected property even when the table hides it.

**§15 note, 2026-10-26 (the record pane under a page frame; additive):** under `toolbar="bar"` and `frame="page|bleed"`
the overlay record pane is fixed to the window, as §12 has it, but starts at the bar's bottom in the window
(`--dv-pane-top`, which bar.js keeps as the page scrolls: the scroller's top plus `--data-sticky-top` once the bar is
stuck, lower while a heading above the views is still in view), so the bar's controls are never under it. View
settings does the same. The split pane keeps §13's dock; the phone's full-screen pane is the whole screen by design;
under `toolbar="full"` the peek keeps §12's place (the scroller's visible box; frame_checks.py measures that).

**§15 note, 2026-10-26 (the band's bottom; additive):** every surface pinned under the bar (the overlay record pane,
View settings) starts at the bottom of the whole band: the bar, and the pill or bulk row under it while that row shows.
bar.js measures it once (`bandBottom()`; `--dv-band-bottom` in the element, `--dv-pane-top` in the window under a page
frame, replacing `--dv-bar-bottom`) and again when the row appears or goes (a ResizeObserver on `.dv-subbar`) and as the
page scrolls. The query box's suggestions open over the band from inside the bar and are not pinned.

**§15 note, 2026-10-26 (the Notion pattern: `search`, and the filters default; additive):** **views visible ⇒ filters
folded; views in a dropdown ⇒ filters may expand.** With no `filters` attribute the bar's filter control follows how the
views are drawn: as tabs (`views="tabs"`, or `auto` showing tabs) it is `pills` (one Filter button, pills only once a
filter is set); as the chip (`dropdown`, or `auto` showing the chip) it is `expanded` (Sort · Group · Filter · Properties
as words). Under `auto` it re-decides when auto flips (whether the tabs fit is asked with the folded control). An
explicit `filters` attribute always wins; every gallery case sets one, so none changes. Zach, 2026-10-26: "If you have
these quick-switch views visible, then usually the pattern should be to make the filters more hidden (this is the Notion
pattern)." **Attribute `search="box|icon"`** (default `box`, the box as before): `icon` folds the query box behind a
Search icon button in the tools (`aria-label="Search"`, `aria-expanded`); a click or `/` grows the box in place and
focuses it (its slot keeps its room, so nothing else in the bar moves; on a two-line bar the folded box takes no line);
it stays open while it holds words or tokens, folds on blur when empty, and Escape on the empty box folds it (after
the suggestions' own Escape, when they are open). View settings stays the home for everything else.

**§15 note, 2026-10-26 (the bar is one row; supersedes the two-line bar above and §15's earlier `views="auto"` rule):**
the bar is always one row and never wraps, at any width and under every frame (frame="tabs" included: its tabs stay on
the row, underlined). As the bar's own width shrinks (a ResizeObserver on the bar, so a table in a narrow split pane
folds too), it takes these steps in order until it fits, each keeping the ones before (bar.js `DEGRADE`): the view tabs
show as many as fit and fold the rest into "N more…"; labels drop to icons (Filters, Properties, Group, Sort, Filter,
Display; each keeps its `aria-label` and `title`); Reset, Filters, Properties and Group move into a "…" menu
(`[data-bar=overflow]`, `role=menu`; arrows, Home, End, Enter, Escape); the query box folds to its Search icon (it then
opens over the views, up to the tools, when the row has no room for it); Sort and Save view move into "…"; the tabs
fold to the view chip (`views="auto"`; a pinned `tabs` stays at "N more", a pinned `dropdown` is the chip throughout);
the Filter count drops; Filter moves into "…"; the chip drops its name. The view selector and Display never leave the
row. Widths are measured once per content (and per font load), then fitted in arithmetic and written once per frame.
The pill / bulk row under the bar is a second row by design, as are the status line and the rail. Zach, 2026-10-26:
"How the table toolbar folds to two lines? I don't like that… I feel it should be 1 bar." The prior art is
docs/peps/0002-toolbar.md (addendum, one row).

**§15 note, 2026-10-26 (one model for the controls: Display holds everything, `promote`, `labels`, one Filter, the
bulk band; additive, `filters="expanded"` becomes an alias):**
- **Display holds everything.** The right-most control, Display (View settings), always holds layout, frame, property
  visibility, filter, sort and group. **Attribute `promote`** (a set of `sort group filter properties`, drawn in that
  order; `promote=""` promotes none) puts any of those sections on the bar as well; a promoted control is the same
  control (the same state, the same menu body as its View settings page, opened anchored to it), never a second
  implementation. Default, when `promote` is absent: `filters="expanded"` (kept as an alias) promotes all four; any
  other `filters` value promotes Filter; with no `filters` either, the views decide: tabs ⇒ Filter, the chip ⇒ all four.
  Presets: Shopify, `views="dropdown" promote=""` (three elements: the chip, the search, Display; gallery case
  toolbar-shopify); Notion, `views="tabs" promote=""` (toolbar-notion); Obsidian, `views="dropdown" promote="sort group
  filter properties"` (toolbar-obsidian).
- **One Filter.** The bar never has two filter entry points. With `filters` holding `rail` and a linked `<data-facets>`,
  the one Filter button shows and hides the rail (`aria-pressed`; remembered as before), and View settings' Filter page
  carries the same switch; otherwise Filter opens the filter menu. The rail's own "Filters" toggle is gone. `pills` still
  adds the pill row under the bar; the count badge stays on Filter.
- **Attribute `labels="auto|icons"`** (default `auto`): `icons` keeps every tool's label off (each keeps its
  `aria-label` and `title`); `auto` drops labels first as the bar narrows, before anything moves into "…" or folds.
  The open tab is elastic before that (it shrinks with an ellipsis down to 88 px, its full name as its `title` and
  `aria-label`; nothing may overlap); "+" (Add view) moves into "…" right after Reset.
- **The bulk band** (Shopify's): while rows are selected the bulk bar (`.dv-bulk`, now a child of the element, not of
  `.dv-subbar`) lies over the view's column header row, at its top and height, the header covered; a view with no header
  (the gallery) gets the band at its top and moves down under it (`dv-bulk-on`, `dv-bulk-top`, `--dv-bulk-h`). Its tint is
  **`--data-selection-band`** (new host token), default `--dv-accent-bg`, i.e. shadcn's `--primary` at 12% over
  `--background`, distinct from the bar (`--dv-bg`) and the header (`--dv-subtle`). Contents unchanged: "☑ N selected ▾",
  the actions, "…", "Show only selected" at the right; one row at every width (actions fold into "…"). The pill row
  stays under the bar while rows are selected. Pinned surfaces (the overlay record pane, View settings) start below the
  bulk band while it shows.

**§15 note, 2026-10-26 (a narrow table: the element's floor, the name column, the expand band; additive):** Zach's
robotparts /psu/ screenshot (open: expand in a narrow box) read "Advan…" and cut the band off at the right.
- **`<data-views>` keeps `min-width: 280px`** (core.css, a type selector a host can still override). A host that squeezes
  it further overflows its own box; the table scrolls sideways in its own box, as always. 280 fits a 320 px phone with
  16 px gutters.
- **The name column beside the checkboxes keeps ≥ 120 px** (`selectable`, the first column): a stored or dragged
  `columnSize` below it is drawn at 120, and a drag stops there; the table scrolls sideways instead.
- **The expand band** still spans every column (its colspan includes the checkbox column); its content sticks to the
  scroll box's visible left and is as wide as the visible box (100cqw), whatever the sideways scroll. Its fields wrap
  into as many columns as fit (one in a narrow box), the photo goes above them under 520 px of box (a container query,
  not the window's width), and every label and value, the title and the key-spec chips carry a `title`. Nothing in
  the band, the headers or the cells is clipped without an ellipsis and a title.
- In split, the bulk band stops at the docked record pane (it had covered the pane's top).

**§15 note, 2026-10-26 (the bar beside §16's intro and roll-up; additive):** the bar is one row with an intro under
it, measured at every width. **View settings has a Roll up row** (table and pivot; its value names what is rolled
away) that opens §16's Roll up menu as its page: the old toolbar's Roll up button is hidden under the bar, and View
settings holds everything. **An intro ends the band:** while a view's intro shows under the bar, the bulk band lies
over the column header below it, so the pinned surfaces (View settings, the overlay record pane) start right under the
bar and its pill row, and the bulk band stops at their left edge instead (its count, actions and Show only selected
stay in reach). Without an intro, or once it has scrolled under a sticky bar, the bulk band is part of the band as
before. [toolbar-bar checks.py `explain_beside_the_bar`: robotparts-models' Leaderboard at 1280 and 900 px, and the
one-row checks at 1440–375 px with the intro present]

## 16. Amendment 2026-10-26 (explain the data: intro, roll-up, column groups, readable cells; additive)

Numbered 16: §14 is time groups and the peek trail (on main), §15 is reserved for lane/toolbar-mix, and lane/dashboards'
amendment takes the next free number when it lands. WHY (Zach, 2026-10-26, on the actuator-models
views): "with data-ui as the base it's really about making these dashboards that really explain the data"; "there
should be a roll-up option so I can roll up across the actuator dimension"; the distribution strips were "hard to
read"; "do we support sub-headers? … I think we should"; "I don't like how things are not aligned". Nothing here
removes or renames a key, a host call or an input field; a view that uses none of it draws as before, except that
numeric cells now sit in fixed slots (below) and a table's `dist` column shares one scale.

- **`intro: {text, kpi}`** on any view: its answer first, above the status line. `text` is markdown (the core's
  `md.js`: headings, lists, code, fenced blocks, pipe tables, bold, italic, links; escaped). `kpi` is an inline view
  entry drawn as `type: kpi` (its own `filters`, `groupBy`, `kpi:`), over the same data and the same rail filter, with a
  host that opens the shared peek and writes nothing. WHY not a second dashboard: lane/dashboards (unmerged; it drafted its amendment as §14) lays
  several panels on a grid across datasets; an intro is one view's caption and cards inside its tab. When the dashboards amendment lands,
  its text panels import `md.js` (it is grown from that lane's `md.js`).
- **`rollup: {keep, agg, dims}`** on a `table` or a `pivot` (grammar.js `rollup`, `rollupKeep`, `rollupDims`,
  `rolledAway`): one row per combination of the kept dimensions, every other dimension aggregated. Group levels and a
  pivot's `splitBy` are always kept. Per property: a number becomes a rich cell `{value, n, low: min, high: max,
  values, basis: derived, summary, note}` with `agg[p]` (median default; mean, min, max, count, spread = max − min, sum;
  Bases names work too); a list concatenates; any other property keeps its value when the rows agree, else `{value:
  null, rolled: N, why}` (drawn "N values", never a made-up value). A rolled row is `{id: '@r<n>', _rollup: true,
  _records}`: a click opens the rows behind it in the peek. In a pivot the kept dimensions are the row key and
  `agg[value.property]` the cell summary; a cell's click lists its records as before. `rowModel` returns `rolled: {from,
  keep, away}` (`away`: the offered dimensions that really varied inside a rolled row) and, for a pivot, `pivot.order`
  (its row properties) and `pivot.urlProperty`. The toolbar's **Roll up** menu (table and pivot) ticks the dimensions
  to keep and picks each number column's aggregate; the button reads "Rolled up: Actuator"; the status line says
  "rolled up across …". The change is the view's, so it rides in the URL's view blob and in Save view like any other.
  Prior art: OLAP roll-up / drill-down, Excel and Sheets pivot "Summarize values by", Tableau's Aggregate Measures and
  level of detail, Notion's and Airtable's group summaries.
- **`summaries` / `value.summary`:** `Spread` (max − min) joins Bases' names; lowercase aliases `median`, `mean`,
  `min`, `max`, `count`, `spread`, `sum` are accepted wherever a summary is (`SUMMARY_ALIASES`, `summaryName`).
- **`columnGroups: {label: [properties]}`** on a `table`: a header over its columns. The table draws one header row
  per level (columnGroups and a pivot's column groups at the top, a property's label and its sub-column's at the
  bottom; equal neighbours under equal parents merge), the same markup and style for a table and a pivot
  (`packages/views/table/src/columns.js` `leafColumns`, `headerRows`). Rows group as before beside them.
- **Displays** (`display: {p: …}`, `value.display`): `stats` splits one property into sub-columns under its label:
  median | min | max | n | runs (its distribution) for a column of values, value | low | high | basis for rich cells;
  `stats: {p: [parts] | {parts, labels}}` picks and names them (`labels: {low: "95% CI low"}`). `range`: the value
  with its low–high muted beside it in its own slot (the default for a rich cell that has one). `value`: the value and
  its basis mark, the range in the hover. `markdown`: a text property rendered as a document in the peek and a record,
  its first line in a table cell. `dist` (now readable): one scale down the column (log past two decades of positive
  values, symmetric log for a heavy tail across zero), its ends and middle drawn in an axis row of the header, points
  light, the min–max line thin, the median a tall dark tick, the header's tooltip saying how to read it and the cell's
  listing median, min, max, n and the values. Only a column whose rows carry their own unit (`p.unit`) keeps a per-row
  scale.
- **Fixed slots.** A numeric cell is a grid `[number][range][mark][count]` whose slot widths are the column's, so
  down a column the numbers' right edges and the marks' left edges share one x whatever the digits, a count or a
  missing value ("—" sits in the number slot). Tabular numerals throughout.
- **Open, for a pivot row:** the effective `open.url` (view, else the file's top level) rides along on a pivot row when
  every record behind it agrees, and its title cell is a real link to that page.
- [tests/unit/rollup.test.mjs, md.test.mjs, columns.test.mjs, kpi-delta.test.mjs; the robotparts-models case's checks:
  roll-up cells against the rack's raw budget files, the Roll up menu, per-column aggregate, drill-down, sub-header
  spans and alignment measured with getBoundingClientRect, the model peek and page showing the README read with git]

## 17. Amendment 2026-10-26 (dashboards; additive)

A dashboard is a `.base` file with `layout:`; `<data-dashboard src="x.base">` draws it (docs/peps/0004-dashboards.md,
which holds the criteria, the prior art and the rules below in full). Numbered 17 when it landed: main had §12 frame,
§13 open modes and §14 time groups and §16 explain-the-data (models-views); §15 is reserved by toolbar-mix (unmerged). Nothing here changes `<data-views>`, a host call, an input field or a token.

- **New top-level keys** (schemas/view.schema.json; both checkers read them):
  - `datasets: {<name>: <path> | {data, label, facets, filters, tree: {parent}, rollup}}`. An entry whose `data:` is
    the top-level `data:` describes the default dataset; otherwise the default is named by its file stem.
  - `links: [{from: <dataset>.<property>, to: <dataset>.<property>}]`: undirected, chainable semi-joins. A link
    filters rows; it never adds a column (CONTRACT §10, "Join, not adopted", still holds).
  - `layout: {columns: 12, rowHeight: 110, panels: [{view | views | text, w, h, title, toolbar: none|compact|full}]}`.
  - `rollup: {from, latest: {by, per}, values: {<column>: {property, summary, per}}}` on a dataset: computed columns
    through its `tree:`, one direct link to `from`; cells `{value, basis: derived, n, note}`; `summary` is a Bases name
    or `Ratio` (Σproperty / Σper).
- **New view keys:** `from: <dataset>` (default: the default dataset) and `select: <property>` (a click on this view
  selects the clicked rows' values of that property for the whole dashboard).
- **Rules** (PEP 0004 §5): a panel's filter is its dataset's rail AND every other panel's selection on that dataset AND
  one semi-join per other restricted dataset with a link path to it; the emitting panel ignores its own selection; a
  roll-up reads only its source dataset's own filters; the views of one panel read one dataset.
- **The element:** `<data-dashboard src>` (attribute `no-url`; methods `load(base, datasets)`, `reload()`,
  `setRail(name, filter)`, `select(panelKey, property, values)`, `clearSelections()`, `drill(...)`, `panelFilters()`;
  event `data-dashboard-change {state}`). Each panel is a plain `<data-views no-url>` driven through `data`, `base`,
  `filters`, `data-views-change` and an instance-level `openPeek`, so a change to `<data-views>` reaches every panel.
  Each rail is a stock `<data-facets for>` bound to a `<data-dashboard-source>` (the target interface `<data-facets>`
  already reads: `data, base, view, filters, model, dataUrl, openMenu`, event `data-views-change`).
- **State in the URL:** each dataset's rail as readable params (`?health=green&runs.kind=tests`), custom clauses in
  `#f.<dataset>=`, selections `#s.<panel>=<property>:<v1>,<v2>`, a panel's tab `#p.<panel>=<view>`.
- **Delivery:** `dist/dashboard.js` (about 10 KB gzipped), importing `./data-ui.js`; a page without a dashboard
  pays nothing. Side panels: the rail drags and remembers (`dash-rail:<id>`), the one drill peek is a `<data-views>`
  peek with its own handle (§11).
- **Declared rounding (landed with §17):** a number may be written with `digits` (significant figures; an integer
  part is never cut) and `compact` (26,512 as 26.5K, Intl's compact notation). They are opt-in and declared in the
  `.base`: on a `properties:` entry (with `decimals`), or on a KPI view's `kpi.format: {digits, compact}`. The stored
  value stays one hover away (`title`, `data-exact`). A KPI summary and a delta are computed, not stored, so they
  default to 4 and 3 significant figures. `fmtNum(v, decimals, {digits, compact})` and `numOpts(...)` are exported
  from `@data-ui/core`; with no options `fmtNum` is unchanged (every stored digit). [tests/unit/numformat.test.mjs;
  vibetracks-dashboard "numbers:"]
- **Addendum 2026-10-29 (declared rounding reaches every cell):** a property's `digits` and `compact` are read wherever its
  number is written, not only by the KPI cards: a table cell (plain, rich, range, stats parts and their hovers), its
  summary row, a group header over the number, the peek's fields, its "records behind" table and the tables a
  `record.sections` entry embeds (they carry the outer `properties:`), the rail's range text and chips, a KPI card's
  range and provenance, a histogram's bin edges, and a dashboard's selection chip. `decimals` still wins where no digits
  are declared; a group over a number with neither reads its key as stored. A plain table cell keeps the stored number in
  its `title`.
  [tests/unit/declared-digits.test.mjs; tests/browser/digits_checks.py, digits_sweep_checks.py]
- [tests/unit/dashboard.test.mjs; the six dashboard cases' checks.py: vibetracks-dashboard, vibetracks-runs,
  vibetracks-track, pid-tuning, sim-to-real, trajectory-tracking]
- **Addendum 2026-10-28 (PEP 0010 P0; sim2real gap #13):** `src` may be set at any time, as the attribute or the
  element's `src` property, and the element loads that file; it used to reload only after a first load, so a host that
  set src after putting the element on the page got nothing. Another file is a new document: its own default filters,
  the URL read as a fresh load reads it, and a new clock with its own `clock:` keys. `reload()` of the same file keeps
  the rails, selections, tabs and clock, as before. Of srcs set in a row the last is drawn, whichever file answers
  last; a src set while the element is off the page loads when it is put back. [tests/browser/p0_checks.py]
- **Addendum 2026-10-29 (PEP 0010 P1a; §32):** two rules above widen. A 3D view's layer may read another dataset of the
  dashboard, so "the views of one panel read one dataset" becomes one dataset per panel plus one per layer, each layer's
  rows filtered as a panel on that dataset with the same panel key would be. And two datasets linked directly are
  joined on every link between them (one semi-join clause per link, ANDed); a dataset with no direct link still joins
  along the fewest-hops path. A dashboard with one link per pair of datasets (every one before this) filters exactly as
  before. [tests/unit/dashboard.test.mjs, its P1a tests]
- **Addendum 2026-10-29 (PEP 0010 P3; §33):** a link may say `direction: one-way` (the from side's picks narrow the to
  side, never back; two-way stays the default), a dataset's `data:` may name a placeholder (`runs/{run}.json`: read per
  pick), a view's `selected:` presets its `select:`, a `select:` on its rail's one-choice facet moves that pick, and a
  pick is a history entry. §33 holds the rules. [tests/unit/p3-nav.test.mjs; tests/browser/p3_checks.py]
- **Addendum 2026-10-29 (§34):** a reader adds a panel from any view to the bottom of a dashboard (appendPanel; the host
  saves the text); every panel has a ⋯ menu, and a layout panel's `t:` pins it at an instant. §34 holds the rules.
- **Addendum 2026-10-29 (RobotDx PEP 0001 §18.4, ask 2; additive):** on live data (§26) a roll-up reads the rows as of the
  dashboard clock's t: each key's newest version at t (every key), or an append dataset's newest 2,000 rows at or before t,
  of its source and of its own dataset, whose rows at t get the cells (a live tree's versions at t; model.js `rowsAsOf`,
  `applyRollups(dash, data, state, {t, only})`). It is computed again whenever t moves and whenever a live dataset it
  reads has news (a late row at or before t, a retention drop), before the frame's views draw, and a panel on it is
  handed its data again when a cell moved: at once while paused, at most every 250 ms while the clock plays or follows
  (live.js `watchRollups`). So it follows and rewinds with the clock. A roll-up over files is as before, and with no t
  (a host's own call) a live dataset's newest rows are read, as before. WHY: it read the newest rows, once per rail
  click, so on live data it neither followed nor rewound. Not yet: a panel pinned at an instant (§34) shows the cells as
  of its dashboard's t, not its own (one roll-up in place per dashboard). [tests/unit/dx-asks-2.test.mjs;
  tests/browser/dx_asks_2_checks.py: a tree from a file and a live tree against an oracle over the gates' newest
  versions at t, following, paused at four t's, back to live]

## 18. Amendment 2026-10-26 (embedded chrome: `status` and `controls`; additive)

How a host that embeds one view as a part of its own page turns off the kit's own chrome around it. WHY (Zach,
2026-10-26, on Vibe Tracks hiding `.dv-status` and `.dv-chart-bar` with its own CSS: "can you please provide first class
support for this so we don't need to do hacky css"): a KPI head or a history strip inside a host's page has the host's
words around it, and "119 of 119 rows · 9 groups" or an Encode button there is noise; a host that reaches into the kit's
class names breaks the day they are renamed. Nothing changes for a host that says nothing: both default to on.
Numbered 18: §15 is reserved for lane/toolbar-mix and §17 is the dashboards landing (on main before this).

- **`status`**: the status line under the view ("119 of 119 rows · 9 groups", a view's own `setStatus` text, a filter
  error). Off, it is `hidden` and takes no space, under every `frame=`.
- **`controls`**: the view's own control bar, inside the view's slot. Today that is the chart's Encode / Rows bar and
  its popover; the plot keeps its height and the bar's height goes back to the page. A view type with no bar of its own
  draws as before. A new view type that adds a bar hides it under `.dv-view[data-controls="off"]`.
- **Where it is said**, per key, first wins: the view's entry in the `.base` (`status: false`, `controls: false`; a boolean,
  or `on | off | show | hide | none`, schemas/view.schema.json), then the attribute on `<data-views>`
  (`status="off"`, `controls="off"`), then the default, on. Both attributes are observed: a change applies at once.
- **Read back:** `el.chrome()` → `{status, controls}` (booleans); the element mirrors them as `data-status` and
  `data-controls` (`on|off`), and the view's slot (`.dv-stage > .dv-view`) carries `data-controls`.
- **Not touched:** `toolbar=` (the tabs and the toolbar above the view) keeps its meaning; a host that wants a bare part
  writes `toolbar="none" status="off" controls="off"`. The side peek, the rail and the intro are not chrome here.
- [tests/browser/chrome_checks.py, 43 checks: the default; each attribute off, measured (the status line's and the bar's
  boxes are 0 px, the view is shorter by exactly the bar, the rows and the plot still draw); both off under every
  frame; live attribute changes both ways; the view key winning over the attribute both ways; the checker accepting
  both keys and refusing `status: sometimes`. Mutation: a chrome() that always says on fails 22 of them.]

## 19. Amendment 2026-10-26 (analyses: the third tier; additive)

Numbered 19: §15 is the toolbar, §16 explain-the-data, §17 dashboards and §18 embedded chrome, all on main before
it. WHY (Zach, 2026-10-26, on robotparts.dev's
analysis pages): "I actually feel this analysis format should be part of data-ui. I definitely see me reusing this in
many apps … So data-ui now has the normal dataset views, then the dashboards, and now the analysis pages." The design,
the prior art and the criteria are docs/peps/0007-analyses.md. Nothing here changes a view, a .base key or a host call.

- **The tiers:** `<data-views>` (one dataset, many views) → `<data-dashboard>` (many views over linked datasets, a
  `.base` with `layout:`, §17) → **`<data-analysis>`** (a report: prose, views and dashboards, a decision, from one
  Markdown file) and **`<data-analyses>`** (the list of reports, a `<data-views>` over their frontmatter).
- **The file** (`packages/analysis/src/format.js`; its Python twin `dist/python/data_ui_analysis.py`):
  - YAML frontmatter, read with the core's `parseBase`. `title` and `question` are required. `status` is one of draft,
    open, decided or superseded. `parts` is a list of ids, and `decision` must be one of them. `date` is YYYY-MM-DD.
    `author`, `tags` and `visibility` are optional. Unknown keys are kept.
  - Markdown prose: the core's `md.js`, after `[[target]]` / `[[target|label]]` / `[[target\|label]]` become links
    through the host's `resolveLink`.
  - A ` ```base ` fence is an inline `.base`. `![[name.base]]` / `![[name.base#View]]` on its own line embeds a file,
    looked for beside the analysis and then in each `embeds=` folder. A `.base` with `layout:` is drawn as
    `<data-dashboard>`; any other is a `<data-views>` (no-url, compact toolbar).
  - `this.<key>` in any filter (the file's, a view's, a dataset's) is the analysis's frontmatter, as Obsidian binds
    `this` in an embedded base. `this.k.contains(x)` becomes `(x == "a" || …)`, `this.k.isEmpty()` becomes true or
    false, and `this.k` becomes its value. Text inside quotes is untouched.
  - `> [!type]± Title` callouts. `[!decision]` is the verdict box. `[!illustrative]` marks what is assumed. `[!ai]` sets
    a judgement apart from the numbers. Any other type is a plain callout.
  - Relative data paths are beside the `.base` that names them; a path from `/` is a URL.
- **`<data-analysis src="x.md">`** (or `.text`). Hooks: `resolveLink`, `missingLink`, `readFile(path)` (files not on
  the web, e.g. a synced folder), `source` ({kind, label, note, path, rawUrl, filename}), `dir`, `embeds`,
  `heading="2"`.
  - It draws a contents column of the prose's headings and the decision. The column is sticky, drag-resizable and
    remembered (§11). Indentation is relative to the shallowest heading used.
  - Then the header: status, question, the parts (with photos when resolved), the decision, the file, and Copy as
    Markdown / Download / Open the file.
  - Then the body, with every problem listed by line.
  - Ids: the body is `<id>-body` with `data-state="loading|drawing|ready"`, and the contents are `<id>-toc`.
  - A new `.text` redraws, but reuses every block whose source did not change.
  - Event: `data-analysis-render` {problems, embeds}.
- **`<data-analyses src="index.json">`** (`data_ui_analysis.build_index`'s file), or `.rows`, or `base="x.base"` whose
  `data:` holds the rows. Its default presets are Gallery, Table and Board by status, and a click opens the row's
  `url`. `.data` and `.model` pass through to the inner `<data-views>`. Its `data-*` attributes are copied onto that
  `<data-views>`, and its `data-view` mirrors the open view.
- **`data-ui check FILE.md [--root DIR] [--embeds DIR]`** checks the frontmatter's rules, then every fence and every
  embed through `checkText` against the data each names, with problems at their line in the `.md`. A path from `/` is
  checked under `--root`, or warned about without it. `.base` files on the same command line are checked as before.
- **Loads:** `dist/analysis.js` imports the page's one core (`./data-ui.js`) and fetches `./dashboard.js` only for the
  first dashboard it meets. A page with neither element loads none of it.
- **A gallery case** whose `site.json` says `{"analyses": true}` is a list. Its `views.base` holds the list's presets
  over the analyses' rows, and the site writes `<slug>.html` beside each `<slug>.md` (gallery/examples/analyses).
- [tests/unit/analysis.test.mjs (the reader, `this`, links, rows, the checker on tests/fixtures/analysis);
  tools/test_analysis_py.py (the two readers agree; the gallery's rows are current); gallery/examples/analyses/checks.py
  (the list against the files on disk, the contents against each file's headings, the fence's rows against
  actuators.json, the embedded dashboards' panels, the contents drag measured, light and dark, 1280 and 390 px)]

## 28. Amendment 2026-10-26, landed 2026-10-31 (property types, Notion's column menu, the table's lines; additive)

Numbered 28 at landing, the number kept for it (drafted as 17, 20, then 31): every other section here landed on main first.
The decision record, and what this has to do with §40's column menu: docs/peps/0018-property-types.md.
WHY (Zach, 2026-10-26): "Notion calls it Type, and each type has different formatting options… I don't think we
support that as first class yet", "I like how in Notion you can pick the icon or the name for the column!", "In terms
of interacting with the table, let's just use Notion as the UX/UI reference", on roll-up "another generic table
operation that belongs where you have sort, filter, group", on the intro "I generally don't like how this text looks
just there… put it before or after, or support a Markdown block… or use tooltips", "add a VIOLIN option", and on the
sub-headers "make sure you are drawing all the lines correctly". Prior art (cited): `~/zach_brain/World Model/Chunks &
Concepts/C - Table property types and cell formatting (prior art).md`. Nothing here removes or renames a key, a host call
or an input field; a file that uses none of it draws as before, except the table's lines and header alignment (below)
and the header click, which now opens the column menu (shift-click still sorts).

- **`properties.<p>.type`** (the `.base` file's top level; core `src/types.js`): one of Notion's types — `text`,
  `number`, `select`, `multi_select`, `status`, `date`, `person`, `files`, `checkbox`, `url`, `phone`, `email` — or
  `rating`, `currency`, `percent`, `duration`, `relation`, `rollup`, `formula`, `id`, `created_time`, `edited_time`. With
  it: `icon` (an icon name or an emoji; the header shows it, else the type's icon), `description` (the header's
  tooltip), and the type's options: number `format` (number_with_commas | number | percent | currency), `currency`,
  `decimals`, `abbreviate`, `showAs` (number | bar | ring) with `color` (Notion's ten), `divideBy`, `showNumber`;
  select/multi-select/status `options` ([{value, color, group}] or {value: color}; status groups todo | in_progress |
  done); date `dateFormat` (full | short | mdy | dmy | ymd | relative) and `timeFormat` (none | 12h | 24h); checkbox
  `showAs` (check | toggle); status `showAs` (select | checkbox); rating `max`, `ratingIcon`, `color`; duration
  `durationUnit`, `durationFormat`; url `urlDisplay`; id `prefix`; number `dist` (strip | box | violin). In the row
  model the type is the column's **`kind`**; the storage `type` (text | number | list | boolean | date) is untouched, so
  filters, sorts, groups and the rail read the values as before. **A type changes only how a value is drawn**, never the
  value: a percent 0.25 reads "25.00%" (Notion's Percent), its hover says 0.25; a bar drawn full past its divide-by
  still prints its number. A type is never guessed from values (a "%" unit does not make a percent); a column without
  one is inferred from its storage and display as before (boolean → checkbox, list → multi-select, badge → select).
  A relation's records are buttons when the view can open them (Tab reaches each, Enter or a click opens it in the
  peek; `relationContext(el, dataset)` gives any view their titles and that), plain text when the record is not in the data.
  `formatText`, `typedHtml`, `typeIconHtml`, `typeOf`, `colorOf`, `statusGroup`, `PROPERTY_TYPES`, `TYPE_PICKER` are
  exported; `valueText` / `valueHtml` draw a typed column's type (the peek, cards, the record view), byte-for-byte as
  before for an untyped one.
- **A property only the `.base` file has** (the menu's Insert and Duplicate): a typed entry with no data behind it is a
  column whose cells read "—" with the reason; `from: <property>` reads that property's values under its own name, type
  and options (the rows the model hands a view carry the copy; the data is never written). `hidden: true` (the menu's
  Delete on a property the data keeps) takes it out of every view.
- **Host calls** (§1's host object gains two): `host.writable` (the element has `editable`) and
  `host.editProperty({action: 'set', id, patch} | {action: 'insert', at, side: 'left' | 'right', type} | {action:
  'duplicate', id} | {action: 'delete', id})` → the id it touched or made. It changes `el.base.properties` (every view
  redraws with it), `el.baseText` line by line (core `src/propedit.js` `propertiesInText`: every other line and comment
  stays; ⋯ "Copy the whole file" carries it) and fires **`data-views-base`** `{action, id, patch, properties, text}`.
  Throws on a read-only element. `el.editProperty(edit)` is the same call.
- **The column menu** (table and pivot; `packages/views/table/src/colmenu.js`), Notion's items in Notion's order: name
  and icon, Edit property ›, Change type › (file items, writable hosts only), Filter ›, Sort ›, Calculate ›, Roll up ›,
  Distribution › (a distribution column), Freeze, Hide, Wrap in view, then Insert left / right, Duplicate property,
  Delete property (asks once). Keyboard: a header is a tab stop; Enter, Space or ↓ open its menu; ↑/↓ move, → opens a
  page, ← or Escape go back, then close; focus returns to the header. View items write view keys through
  `host.setView` (so Save view, the URL and ⋯ Copy carry them): `filters`, `sort`, `summaries`, `rollup`, `dist`,
  `freeze`, `order`, `wrap`.
- **Beside §15 (merged 2026-10-27):** §15's `freeze: 0 | 1` (a count) and `wrap: true` (every cell wraps, each drawn row
  measured) keep working; §28 adds `freeze: <property>` and `wrap: [p]` (those columns only, clamped to the row's lines).
  The two forms read as one: under `wrap: true` the column menu shows every column wrapped, unchecking one writes the
  list of the others, and a list that covers every shown column is written `wrap: true`; the Layout toggle "Wrap cell
  text" is on only for `wrap: true`, and "Freeze columns" names a property freeze ("Through Owner"), never "None".
  With `selectable` the checkbox column is frozen at the left edge and the frozen columns follow it; the column menu's
  "All roll-up settings…" opens §15's Display panel at its Roll up page (the older toolbar's Roll up menu without the bar).
- **New view keys:** `freeze` (a property: the columns through it stay put when the table scrolls sideways — Notion's
  Freeze; `false` none; default the first column; frozen columns never take more than half the visible width),
  `wrap: [p]` (Notion's Wrap in view: the rows go tall, a wrapped cell shows three lines; every column not listed stays
  on one line — only `rowHeight: medium` and up wraps every cell, and then the menu shows Wrap checked with why), `dist: {p: strip | box |
  violin}` (a distribution column's drawing; a pivot's under its value property), `before` / `after` (below).
- **Calculate** (Notion's footer): a table or pivot with `summaries` draws a sticky footer row, each column's summary
  over every row the view shows; group rows keep theirs. Summaries gain Notion's `Percent empty`, `Percent filled`,
  `Checked`, `Unchecked`, `Earliest`, `Latest` (grammar.js `summarize`; `CALCULATIONS` lists the menu's names per kind
  of column).
- **Roll up in the column menu:** on a dimension, "Roll up across <p>" / "Show every <p> again" (edits
  `rollup.keep`); on a number, its aggregate when rolled up (`rollup.agg`); "All roll-up settings…" opens the toolbar's
  Roll up menu, whose body lane/toolbar-mix's Display panel lists as a page (`rollup` in its page titles) when it lands.
- **Text around a view** (core `src/notes.js`): `before:` / `after:` (the file's top level, or a view's own, which wins)
  are Markdown blocks drawn as documents above the tabs and below the rows. **`intro.text` is no longer drawn inline**:
  it is the view's About note (ⓘ About this view in the status line opens it); `intro.kpi` cards stay where they were.
- **The table's lines and alignment** (the 2026-10-26 header/divider review, `reports/media/audits/2026-10-26-table-
  headers-judge-r1.md`): every cell draws a 1 px right and bottom divider, header and body alike, the table's last
  column leaving its right edge to the frame (`sheet` draws none, by its design); a header cell is never blank — a label
  spans down over the levels it lacks (`columns.js headerCells`, rowspans) — and never spans the frozen edge; a
  distribution's title (with its unit) is centred over its strip; a column's unit is a muted "(unit)" caption after its
  name, said once over a stats column's parts; a numeric header's text ends where its numbers end (a cell's slots are
  only the tracks its column uses, `slotTemplate`); `basis` is left-aligned; a column is never drawn or dragged
  narrower than what it holds (`minWidth`). A header's words are no part of that: they widen a column nobody has sized, up to 240 px, and hold no
  drag and no stored width; past that they end in an ellipsis, whole on hover (robotparts' source columns came out at 156 / 603 / 284 px, and the 603 would not drag).
- [tests/unit/types.test.mjs, propedit.test.mjs, columns.test.mjs; tests/browser/types_checks.py with types_cases.py:
  the six review findings measured in boxed and bleed, light and dark; every type and option drawn and measured; every
  menu action and the .base text it writes; a read-only host's menu; keyboard; 375 px]

## 22. Amendment 2026-10-26 (sources of a value; additive)

Numbered 22 at merge (drafted as 19): §15-§19 were on main before it, and §20 and §21 are reserved for lane/collection
and lane/lineage. WHY (Zach, 2026-10-26): any shown value should answer
"where does this come from?" with a right-click, and the same for a photo or a file, without every host writing its own
popover. Nothing here removes or renames a key, a host call or an input field; a page that loads none of it draws as
before.

- **Three new cell fields** (a rich cell `{value, basis, source, asOf, note, …}` may also carry): `sourceUrl` (the page the
  value was read from), `sourcePage` (the host's own page about that source) and `record` (a record or field id, e.g.
  `aifitlab-8541438771336 · specs.rated_torque_nm`). `<data-value>` reads them as `source-url`, `source-page`, `record`.
- **`text`, a display string** (a rich cell `{value: [15, 60], text: "15 to 60"}` may also carry; RobotParts stores a
  range as a list and must show "15 to 60", where a table joins a list with commas). WHY (Zach, 2026-10-29): the producer
  knows how its value reads, and a host that redrew those cells after render was fragile. The rule:
  - **Every place that draws the cell shows `text` exactly as written** (Zach's truthful-rendering rule: never trimmed,
    rounded, re-cased or re-joined): the table (a text, number or list column, and a badge column as one chip), list,
    cards, kanban, compare, record, the peek's field and its records-behind table, a title wherever a row is named
    (a card, the peek header and trail, a selection chip), and the right-click popover's value line. A unit still follows it.
  - **`value` keeps every other job**: sorting, filtering, the rail, grouping, summaries, the roll-up, Copy (CSV export,
    Copy citation), the URL and `data-provenance.value`. The hover title's first line is the stored value.
  - **`text` is a string, or it is ignored**: a number, list, object, `null` or `""` draws the cell's value as before. It
    decorates a value and never makes one: a cell with no `value` still draws "—" with its `why`. A display that is not
    about the value's words (`link`, `image`, `markdown`, `status`, `clock`, `age`) keeps drawing the value.
  - `valueText(cell, column)` returns the text for a rich cell; `cellText(cell)` (`format.js`, exported) is the string or
    `null`; `provenanceAttr` adds a `text` key beside `value` only when it differs. A plain cell is unchanged.
  - Neither checker (schemas/view.schema.json, check_views.py, check.js) reads cells: they check a `.base` file, never the
    rows, so there is no cell schema for `text` to join. The loader (data.js) does not validate rich-cell fields either.
  [tests/unit/cell-text.test.mjs; tests/browser/cell_text_checks.py against tests/browser/fixtures/cell-text/]
- **`display: link`** (2026-10-30): a value is an `<a>` only when it is an http(s) URL or a relative path, query or fragment (`isLinkTarget`), labelled by the cell's `text` when it has one, else by the value; any other value (`account:…`, a bare id, `javascript:`) is that label as plain text, no `<a>`, in every view, the side peek and the popover's Source and URL rows (`linkCell`, format.js; WHY: a private source has no address). [tests/unit/link-display.test.mjs; tests/browser/link_text_checks.py]
- **`data-provenance`**: one attribute holding JSON, `{value, text, unit, basis, source, sourceUrl, sourcePage, asOf, record,
  note}`, every key optional (empty ones are left out). `value` is the value as formatted (the stored value; `text` is the display string above, present only when the cell has one and it differs); `unit` its unit
  even when the column hides it. `valueHtml` (`format.js`; `provenanceAttr` is the one builder, exported) writes it on a
  rich cell's `<span class="dv-value">` when the cell has any of `source`, `sourceUrl`, `sourcePage`, `asOf`, `record` or
  `basis`, and on nothing else (the JSON is only built then, so a page of plain values costs what it did). The table's
  numeric rich cells draw their own slots, not `valueHtml`, so there the attribute sits on the `<td>`. A host marks any
  element the same way (an `<img>`, `<a>`, `<figure>`, `<td>`): that is how photos and files get their sources.
- **`dist/sources.js`** (`packages/core/src/sources-menu.js`; about 12 KB, its stylesheet inside, one `style[data-ui-sources]`):
  `<script type="module" src="sources.js">` attaches to the `document` unless `<html data-sources-menu="off">`. Exports
  `attachSourcesMenu(root = document, {resolve})` → `{close, destroy}` (`resolve(el) → provenance | null` supplies
  provenance for an element without the attribute) and `provenanceOf(el)` (the closest `[data-provenance]`, parsed, or null).
- **Triggers:** `contextmenu` on or inside an element with provenance opens it at the pointer and prevents the native menu;
  an element without provenance gets the native menu; **Shift + right-click always gets the native menu**. A touch or pen
  press held 550 ms opens it (cancelled by a move over 10 px, lifting, or a scroll) and the click that ends it is
  swallowed. The `ContextMenu` key or Shift+F10 opens it for the text selection's anchor, else `document.activeElement`
  (its closest provenance, else its first descendant that has one), under that element, with focus on the first action.
- **The popover** is one light-DOM `div.dv-srcmenu[role=dialog][aria-label="Where this value comes from"]` on `<body>`,
  clamped inside the viewport (a phone under 480 px: full width less 16 px gutters). Top to bottom: the value and unit in
  bold; the basis (robotparts' word, Stated for datasheet / seller / claimed, Measured, Derived for derived / estimate,
  then `BASIS`' mark, label and meaning); rows Source (a link to `sourcePage` when there is one), URL (host and path,
  ellipsised, the full address in its title), Accessed (`asOf` and "(N days ago)" when it is a date), Record, Note; the
  actions **Open URL ↗**, **Source page** and **Copy citation** (`{value}{ unit} — {source}, {sourceUrl}, accessed
  {asOf}. Record {record}.`, missing parts skipped; the button reads "Copied" for 1.5 s); a muted footer, "Shift + right-click
  for the browser's menu". A missing field omits its row, never "undefined". Only `http:` and `https:` addresses become links.
- **Behaviour:** one open at a time; Escape closes it and returns focus; a click outside, a window resize or a scroll closes
  it; arrows and Tab move between the actions. Opening dispatches a bubbling **`data-sources-open`** `CustomEvent` on the
  element that carries the provenance (`detail`: the provenance object), for hosts and tests.
- **Style:** `--data-*` tokens only (bg, fg, muted, border, accent, radius, font, mono) with the §4 fallbacks, light and
  dark as `tokens.css` switches them (system scheme, `html[data-theme]`); no `--dv-*`, because the popover sits outside every
  data-ui element.
- [tests/unit/provenance.test.mjs; tests/browser/sources_checks.py against site/plain/sources.html: right-click, Shift
  + right-click, Shift+F10, ContextMenu key, selection anchor, Escape, outside click, resize, scroll, arrows and Tab, copy
  with and without `navigator.clipboard`, `resolve`, `destroy`, long-press and its cancels, the clamp and the 375 px layout
  measured with getBoundingClientRect, light and dark computed colours]

## 23. Amendment 2026-10-26 (3D models; additive)

Numbered 23 at merge (drafted as 14, lane/object-db-public 809e9b2); §24 is its raw source view and §29 its first-frame gate.

A 3D model is a media kind, shown poster first, from ONE WebGL renderer per page. WHY (Zach, 2026-10-26: "data-ui
will likely need to be extended to support 3D gallery thumbnails ... and potentially even interactive ones"): BAM's
object library is meshes, and a gallery of 2,000 cards cannot give each card a WebGL context (Chromium keeps 16, then
drops the oldest; measured: 40 per-card renderers left 24 cards blank). The engine is three's "multiple elements"
pattern and `<model-viewer>`'s `Renderer` singleton. Report: `reports/data-ui-object-db-2026-10-26.html`.
[tests/unit/mesh.test.mjs; gallery/examples/object-db-shelf/checks.py, measured in the page]

- **`media: mesh`** on a field (beside `image | video | file`): its value is a model URL (`.glb` / `.gltf`, the format
  to ship; `.obj` / `.stl` / `.ply` load too), relative to the data file like an image (§1, `mediaUrl`).
- **`<data-mesh src poster interact fit alt>`** (core; `DataMesh`, `meshEngine` exported). It draws `poster` (an
  `<img>`, lazy) and nothing else until a model is wanted, then loads `dist/views/mesh.js` (three 0.186.1, 171 KB
  gzipped) once for the page and shows live frames in its own 2D canvas, copied from the one shared renderer.
  `interact`: `hover` (default: a turntable while the pointer is over it; drag turns it; leaving freezes the angle),
  `click` (live from a click or Enter), `orbit` (live while on screen, turning until touched; drag orbits, wheel zooms,
  double-click resets), `none` (the poster). A drag never becomes a click on its container. At most `MAX_LIVE` (4)
  animate at once (the oldest freezes on its last frame); parsed models are kept to `MAX_MODELS` (48), least recently
  used disposed. No motion of its own under `prefers-reduced-motion`. `customElements.get('data-mesh').stats()` →
  `{contexts, contextsMade, live, liveMax, models, bytes, frames, renderMs, firstModelMs}`.
- **Cards:** `mesh: <property>` draws the card's image well as a `<data-mesh>` with `image` as its poster (a card looks
  the same until hovered); `meshInteract: hover | click | none` (default `hover`). Both are in the Layout menu and the
  schema; the checker checks `mesh` against the data.
- **The peek:** the current view's `mesh:` property, else the first property whose field says `media: mesh`, is drawn
  first in the side peek as an `orbit` viewer (`.dv-peek-mesh`), poster from the view's `image` or the dataset's
  `imageProperty`. The peek's splitter (§11) widens it.
- **The poster's camera and backdrop (`meshView`, `meshBackground`).** WHY (Zach, 2026-10-26, on the dark-mode
  gallery: "the background is also white/lighter so it better matches"; "the 3D view starts at the same location the
  thumbnail photo is taken from; right now it is often a bit smaller"). `meshView: <property>` on cards (and read by the
  peek) names a per-row `{dir: [x, y, z], fov, box?: [x0, y0, x1, y1], dist?}`: the poster camera's direction from the
  model's centre (glTF frame, +Y up), its vertical FOV in degrees, the poster's silhouette box (0-1, y down) and
  optionally the renderer's distance in metres. `<data-mesh view="…">` looks along `dir` with `fov`, projects the model
  and scales and shifts the projection once (per size) so its silhouette lands on `box`: frame 0 is the poster's
  framing whatever crop or padding made the poster; the turntable keeps that scale; double-click returns to it.
  Without a view: render_thumbs.py's camera ((0.9, 0.8, 1.1), 30 deg, half-diagonal / sin 15 deg x 1.05), framed as a
  contained square poster. `meshBackground: match | light | theme` (and `<data-mesh background>`): match (default)
  paints the live frames and the element on the poster's own backdrop (its corner pixel), light is white, theme is
  transparent. [tests/unit/mesh.test.mjs "meshView:"; object-db-shelf/checks.py "3D camera" (frame 0's silhouette
  within 3 % of the poster's, scans and MuJoCo primitives) and "3D background"]
- **`note.x` in a view's property keys.** `image`, `media`, `mesh`, `start`, `end`, `title`, `color`, `coordinates`,
  `markerIcon`, `markerColor`, `order`, `caption`, `groupBy.property` and `sort[].property` read `note.x` as `x` when
  `x` is a column (Bases' meaning; filters and `properties:` already did). WHY: the object library's
  Obsidian-written `Objects.base` (`image: note.thumbnail`) drew cards with no image. `bareView(view, columns)` in
  `rowmodel.js`; the host passes the bare entry to views and to `rowModel`.

## 24. Amendment 2026-10-26 (raw source view; additive)

Numbered 24 at merge (drafted as 15).

A view of the data itself, for debugging. WHY (Zach, 2026-10-26): "One view I haven't seen yet in data-ui is a raw
source view: almost a plain Excel chart of what the data set is behind it. Helpful for debugging." It is a normal view
type, so every host has it. Nothing here removes or renames a host call, an input field or a key. The view is
`packages/views/source/`; the provenance is `packages/core/src/data.js`. [tests/unit/source.test.mjs;
gallery/examples/raw-source/checks.py, over that case's CSV and the object-db-shelf case's JSON, measured in the page]

- **`type: source`** draws a grid whose columns are the union of the rows' keys in first-seen order (hidden,
  undeclared and `_` keys, and `id`, marked when the core assigned it); the view's `order` does not pick them. Each value
  is literal: strings as stored (`white-space: pre`), `""`, `null` and an absent key told apart, numbers as `String(v)`,
  lists and objects (rich cells too) as compact JSON; no units, badges or links. A clipped value shows an ellipsis and is
  whole in its title and in the panel. Under each key, its type from `input.columns`, or "undeclared". Its one key:
  **`rows: all | filtered`** (default `all`: every row as loaded, which is the element's `data.rows` (§6); `filtered`:
  `input.rows`). An info strip names the data file, the `.base` file, the format as loaded, the bytes, rows and
  columns; Copy and Export CSV write the rows shown, every column, RFC 4180, each value as the grid writes it.
- **The source panel** (a row's Source button, or Enter on the row) sits inside the view's element, with §11's handle
  (`data-ui/panel-width/source:<views id>`); ✕ or Escape closes it. It shows the row's **origin file** when the data
  declares one, else `originOf(row)`.
- **A dataset's `origin` key** (new, optional, in the runtime shape or a schema sidecar): `origin: {url: "<template>"}`,
  each `{property}` replaced by the row's value (one URL path segment), resolved against the data file's URL with
  `mediaUrl` (§10), e.g. `{"origin": {"url": "sources/{id}.md"}}` for a library built from one Markdown note per row.
  Normalisation passes it through; `input.dataset.origin` carries it.
- **`input.dataset.raw`** `{url, format, bytes, schema?}`: the file the rows were read from (a sidecar's `path` file;
  `schema` is then the sidecar), `format` one of `runtime | frictionless | csv | tsv | jsonl | list | object`, `bytes`
  the UTF-8 size of its text as read (`null` for data set from script). **`input.dataset.originOf(row)`** →
  `{kind: json | jsonl | csv | tsv, line?, text, header?: {line, text}, idAssigned}` for a row of the dataset (else
  `null`): JSON, the row object as parsed before normalisation, pretty-printed; JSONL, the same plus its line; CSV / TSV,
  the record's lines verbatim (a quoted field may span lines) with its first line's number, and the header line. Both are
  non-enumerable properties of the normalised dataset (`withOrigin(dataset, raw, at)` in data.js). Memory: a CSV, TSV or
  JSONL keeps its text once plus three numbers per row; a JSON row keeps its parsed object only where normalisation
  replaced it (an `id` added); `text` is made when read.
- **The one exception to "never fetch data" (§1):** the source view may fetch a row's declared origin file, on demand
  (when its panel opens), from the page's own origin only; another origin is refused with a message, never fetched.

## 29. Amendment 2026-10-26 (3D: the first frame is the thumbnail; spec + gate)

Numbered 29 at merge (drafted as 16; §25-§28 were reserved for dashboard-cards, live, app-rail and types).

WHY (Zach, 2026-10-26: "the 3D view starts from exactly where the thumbnail was taken… please add this as a spec and
test gate to data-ui, it should appear in vibetracks so we don't regress on this"). §23 says how; this section is the
promise every host can rely on, and the gate that holds it.

- **The spec.** When a 3D card or viewer (`<data-mesh>`: a card's image well, the peek's viewer, a host's stage) opens
  from a thumbnail, its first frame uses the thumbnail's camera: the same direction and lens, so the pose is the same,
  and the same framing, so the outline is the same. The outline (the silhouette's bounding box in the element) agrees
  with the thumbnail's within **3 %** in width and in height. Where the camera comes from: the row's `meshView`
  (`{dir, fov, box?, dist?}`, §23), produced beside the posters by whatever rendered them; a host without one gets
  render_thumbs.py's camera framed as a contained square poster, which the spec does not promise to match.
- **The background follows the setting.** `meshBackground` (default `match`): the first frame sits on the poster's own
  backdrop colour, `light` on white, `theme` on the card's colour.
- **The gate.** `npm test` runs it (tests/browser/checks.py → gallery/examples/object-db-shelf/checks.py `camera_match`):
  10 cards (5 real scans with cropped white posters, 5 MuJoCo primitives with uncropped studio-gradient posters), frame 0
  under `prefers-reduced-motion` (no turntable), the poster drawn as the card draws it and the live canvas, each
  silhouette found per pixel row against the row's backdrop line; the worst width or height error must be ≤ 3 %. A
  miss fails the run. Mutation-proved red on 2026-10-26 (default camera, wrong distance / zoom, wrong FOV; the report
  `reports/data-ui-object-db-r2-2026-10-26.html` lists each mutation's measured error).
- **The KPI.** Vibe Tracks, data-ui track: `mesh_first_frame_outline_pct` ("3D first-frame vs thumbnail outline error
  (%)", lower is better, target 3), listed in bench/kpi_catalog.json and appended by tools/publish_checks.py from the
  check's own value on every `npm test` (DATA_UI_KPI_PUBLISH=0 skips).

## 21. Amendment 2026-10-27 (lineage: the tree of life view; additive)

Numbered 21 at merge (drafted as 20): §15-§19 and §22-§24 were on main before it, and §20 is lane/collection's. Zach,
2026-10-27: "this tree of life is just another view over data … It's data that basically has like parent child
relationship and then we are just displaying it … using data ui then for free we automatically get all of the filters
and navigation." Nothing here removes or renames a key, a host call or an input field. The code is
`packages/views/lineage/` (README there); the stock parts are d3-hierarchy 3.1.2, d3-shape 3.2.0, d3-zoom 3.0.0 and
d3-selection 3.0.0, now declared in package.json (all four were already installed under vega and React Flow).

- **A new type, `type: lineage`, not a `layout` of `graph`.** WHY: its keys mean nothing to the graph (an ordinal x
  axis, a focus trunk, kept/extinct, radial rings), its drawing is a different stock part (d3-hierarchy's `cluster` on
  SVG, not dagre in React Flow), and `layout` is already the graph's `{algorithm, direction}` object in the schema, so
  `layout: radial` beside it would be two meanings for one key. One folder, one type (§1).
- **One block, `lineage:`**, as `kpi:`, `chart:` and `compare:` are blocks: `lineage: {parents, x, xLabel, image,
  label, focus, kept, extinct, layout}`. Only `parents` is required. Bases' own `order` stays the visible properties
  (the peek's fields and the search box's scope), so the x axis is `x`, not `order`.

  | key | value | default | does |
  |---|---|---|---|
  | `parents` | a property (a list of ids) | required | the only source of edges; the first listed id is the tree parent, every further one a splice (the same curve, dashed) |
  | `x` | a property | the depth | one column (radial: one ring) per distinct value, numbers in numeric order, text in natural order; a row with no value sits one right of its tree parent |
  | `xLabel` | a property | the x value | the column's label when every row at that x agrees (`round: R5` for `round_n: 5`) |
  | `image` | a property | none | a picture per mark (a path resolves against the data file, §1 amendment); a row with none draws its label |
  | `label` | a property | the data's `titleProperty` | a mark's label and the panel's step names; cut to the column with "…", the full text one hover away |
  | `focus` | a row id | none | that row and every ancestor over all parents draw as the trunk (the accent, the widest line); the path panel lists them oldest first |
  | `kept` | `{property: [values]}` | none (nothing is extinct) | a row is alive when it is kept, on the trunk, or has an alive child over any parent; otherwise extinct |
  | `extinct` | `show \| collapse` | `collapse` | `show`: extinct lines as hairline stubs; `collapse`: each node's extinct children (whole subtrees) fold into one "+N" |
  | `layout` | `rectangular \| radial` | `rectangular` | x left to right, or a ring per x value around the forest's root |

- **One link shape.** Every link (a tree edge, a "+N" stub, a splice) is the same curve, d3-shape's `linkHorizontal`
  (`linkRadial` in the radial layout): one `M` and one cubic `C`. Zach, 2026-10-28: "I am just not a fan of how you are
  using different line shapes like straight vs curved." A curve, not an elbow, because a splice drawn as an elbow runs
  back along its sibling edge, where a dashed line hides under a solid one. **Dashed is data**: only a splice is dashed
  (a row's further parents, `parents[1:]`); width and colour say trunk, branch or extinct. **Extinct lines are folded
  into "+N" by default** (`extinct: collapse`; Zach, 2026-10-28), shown as stubs only on `extinct: show` or the bar's
  Show extinct.
- **Edges are declared, never inferred** (feedback_do_not_invent_undefined_relationships): an edge is drawn for every
  `parents` id that names a shown row and for nothing else. Roots hang from an undrawn root (no line joins two trees);
  an id no shown row has is dropped and counted in the status line ("2 parents not shown"); a parent cycle is cut where
  it closes, in row order, as the table's `tree:` does (§10). A "+N" hangs from its parent by a stub
  (`.dv-lineage-stub`), which is not an edge of the data. `lineage.parents` is a relation for the peek's trail (§14):
  `relationProps` now reads it beside `edges.property` and `tree.parent`.
- **A row in its parent's own column** (three rung-4 models in a chain) stacks below it in that column, its edge drawn
  from its real parent, so no two marks share a spot. A mark's size is at most 22 px and at most 85 % of the axis gap
  to its nearest neighbour in its column (ring).
- **Everything else is the host's.** The rows are `input.rows` (the all-views filter, the view's filters and the
  search box apply); a mark opens `host.open(id)` (§13's side peek in every mode), a "+N" opens the rows it stands for
  as records; the bar (Rectangular | Radial, Show extinct, Focus selection, Fit) writes the view entry through
  `host.setView`, so it rides in the URL's `v=` and in Save view. "Focus selection" makes the peeked mark the `focus`.
- **The path panel** is a side panel by §11: a handle on its left edge (180-520 px, leaving 320 px for the tree),
  `--data-panel-width`, remembered under `data-ui/panel-width/lineage:<views id>`, double-click resets to 260 px; ⟩
  folds it to a 32 px strip (remembered under `data-ui/lineage-fold/<views id>`) and the handle goes; under 700 px of
  view width it stacks under the tree, full width.
- **Pan and zoom:** d3-zoom (wheel about the pointer, drag, pinch). The first view of a rectangular layout fits the whole
  tree when that needs 0.5x or more (so 18 rounds of picture marks open whole, not clipped at the left), else shows 0.6x
  centred on the focus; a radial one always fits the whole tree; Fit
  shows everything. In the rectangular layout the
  column pitch follows the stage's width (56-200 px; 96 px at least for label marks).
- **Both checkers** know the block (schema `$defs.lineage`; `type: lineage` requires `lineage`, which requires
  `parents`; the enums; every property-valued key, `kept`'s properties included, checked against the data).
- [tests/unit/lineage.test.mjs (the layout against hand-written oracles: edges, splices, cycle cut, trunk, alive,
  "+N" counts, columns, rings, stacking); tests/unit/check-lineage.test.mjs and tools/test_check_lineage.py; the
  brand-lineage and model-lineage cases' checks.py, measured in the page against an oracle computed in Python from the
  case JSON: edges equal the data's pairs, path ends on the marks, dashed splices, the trunk, collapse counts, both
  layouts, no two marks on one spot, peek, Focus selection in `v=`, "+N" records, rail and search filters, the panel's
  drag / reload / reset / fold, pan and zoom, light and dark at 1280 and 390 px]

## 30. Amendment 2026-10-27 (graph layout engines: React Flow and Mermaid; additive)

Numbered 30 at merge (written unnumbered; §20 and §25-§28 are reserved for lanes still in the queue). WHY (Zach, 2026-10-27, on
Vibe Tracks' Decisions page): "we should support using mermaid js for doing simple layouts, and also reactflow for more
interactive layouts (as we are currently doing)". Nothing here removes or renames a key, a host call or an input
field; a graph view with no `engine` draws exactly as before.

- **The key.** `layout: {engine: flow | mermaid, direction: LR | TB | RL | BT}` on a `type: graph` view. `flow` (the
  default, also when `engine` is absent) is React Flow laid out by dagre, as today. `mermaid` is a static Mermaid
  flowchart. Both checkers read the enum from `schemas/view.schema.json`: any other engine is an error naming the two
  (`"mermiad" is not one of flow, mermaid (did you mean 'mermaid'?)`). The view's Layout menu offers Engine beside
  Direction.
- **Same graph, either engine.** Nodes, edges, groups (`groupBy`; a Mermaid `subgraph` each) and the status line ("N
  nodes · M edges · K edges to rows not shown") come from the one pure `toGraph(input)` the flow engine uses
  (`packages/views/graph/src/index.js`); an edge exists only where `edges.property` lists a row id, never inferred, and
  the Mermaid text never names an id that is not a drawn node (Mermaid would draw it as a node of its own). The text is
  `flowchartText(model)` (`src/flowchart-text.js`): ids are generated (`n0`, `n1`, … in row order; `g0`, … per group)
  and mapped back to row ids; a label is the row's title property, every ASCII character other than a letter, digit
  or space written as Mermaid's `#<code>;` entity and a line break as `<br>`, so `"`, brackets, `#`, `;`, backticks,
  `<script>` and markdown show as written. A labelled edge (`edges.label`) carries its label and its colour slot.
- **Drawing.** `securityLevel: 'strict'`, `startOnLoad: false`, `theme: 'base'` with `themeVariables` from
  `input.tokens` (so light and dark follow the host's tokens and the drawing is redone when they change), the host's
  font, Mermaid's dagre layout and classic look (Mermaid 12 defaults to ELK, a 1.5 MB chunk, and to the neo look,
  whose drop shadow is not a token colour). The SVG fits the view's width down to 45% of its own size (the flow
  engine's phone floor) and scrolls inside the view past that, never the page. A node is `role="button"`,
  `tabindex="0"`, `aria-label` its title, a pointer; a click, Enter or Space calls `host.open(rowId)`; the peeked
  record's node is marked. `update()` may be called repeatedly, the last call wins; `destroy()` and a switch to the
  flow engine leave no listener, no SVG and none of the render containers Mermaid appends to `document.body`.
- **Loading.** The view imports Mermaid with a dynamic `import('mermaid')`, and the graph manifest sets `"split":
  true` (§1, amendment 2026-10-26), so Mermaid is its own files beside the bundle (`dist/views/graph-*.js`, listed in
  `dist/manifest.json`), fetched only when a mermaid-engine view first draws; a React Flow reader downloads none of
  them. With `split`, the d3 modules React Flow and Mermaid share also move out of `graph.js` into two small chunks
  `graph.js` imports.
- [tests/unit/graph-mermaid.test.mjs; tests/unit/check.test.mjs and tools/test_check_views.py "layout engine"; the
  vibetracks-decisions case's checks: 15 nodes and 23 edges counted in the SVG and on the React Flow canvas, every
  label equal to its title, click and Enter open the peek, no Mermaid download for a flow reader, titles full of
  Mermaid / HTML syntax drawn literally, light and dark at 1280 and 390 px]

## 20. Amendment 2026-10-27 (grouped gallery: sections, tiles, nav rail, groupings, bins; additive)

Numbered 20 at merge, as drafted (lane/collection-public da01556); §15-§19 and §21-§24, §29 and §30 were on main
before it. The cards view as a catalogue home: big section titles, a second
heading level only where the data has one, a tile per sub-category, a left rail that filters to one group and a live
grouping switcher. WHY (Zach, 2026-10-27): "This home page feels like a Shopify 'collection'. It's almost like a
particular view of the table where we make the subheaders big and the children gallery cards." / "The left bar should
work more like a filter, actually, instead of going to the position on the screen. That is how McMaster does it! If you
unclick it, all the different areas come back." / "we can also support an H2 header as well … in McMaster you see
Fastening & Joining, then Fasteners / Adhesives & Tape … But Pipe, Tubing, Hose & Fittings has no other layer of
breakdown." / "I think it's just the Gallery View, but showing headers and subheaders." Prior art: McMaster-Carr's
catalogue (category titles, sub-category picture tiles with counts, the "Choose a Category" rail that narrows the page
and gives every section back), Shopify's collections (a collection page of product tiles, collections of
collections), Notion's gallery grouped by a property, Obsidian Bases' cards with `groupBy`. Nothing here removes or
renames a key, a host call or an input field; a view that uses none of it draws as before. ObjectDB's home page is the
first host.

- **Numeric bins on any group level** (`grammar.js` `binsOf`, `binKey`; `facets.js` `groupBuckets`, `fmtUnit`;
  `rowmodel.js`): the number twin of §14's `by:`. `groupBy: {property: bbox_volume_ml, bins: [250, 1000, 5000, 50000]
  | [{label, min, max}] | auto, log?: true, unit?: "mL"}`. A row falls in the half-open bucket [min, max) (a value on an
  edge goes to the upper bucket). The buckets are the rail's own machinery (`bucketsFrom`, `autoEdges`, `nice`; `log`
  as the `buckets` kind reads it), made once per model over the whole dataset, so they hold still while filtering. A
  bucket's key is text that sorts in the buckets' order (`01:250..1000`); labels read "< 250 mL", "250 mL – 1 L", "≥ 50
  L" (each edge scaled along its unit's ladder: mL/L/m³, mg/g/kg/t, mm/m/km, ms/s, mN/N/kN, mW/W/kW; `unit` defaults to
  the column's `unitText`), or the given `label`. Buckets come in ascending order (`direction: DESC` reverses), "No
  <property>" last, empty buckets left out; the view's `sort` orders the rows inside a bucket. The model's
  `columns[property].bins` holds `[{key, label, min?, max?, maxOpen?}]` and `groupLabel(columns, property, keyOrNumber)`
  writes the bucket's label from a key or a row's number. A pivot makes one row per bucket. Both checkers validate
  `bins` (shape; `bins` with `by:` is an error; with the data's types, bins on a property that is not a number warn).
- **Groupings, resolved in core** (`grammar.js` `groupingOf`, `effectiveView`): `groupings: [{id, label?, groupBy?,
  subGroupBy?, tiles?}]` and `grouping: <id>` on a view entry. When `grouping` names an entry, that entry's `groupBy`,
  `subGroupBy` and `tiles` replace the view's own for the row model and every view (`input.view` is the effective
  view; an entry is a whole grouping, so a key it leaves out is none: "type" with no `tiles` draws the rows). An unknown
  id keeps the view's own and the checkers warn (did you mean …); an id used twice is an error. A host's own switcher
  calls `el.setView({grouping: 'size'})`. `MODEL_KEYS` gains `grouping` and `groupings`. The hash carries
  `group=<id>` beside `view=` (read back on load, so a reload or a pasted link keeps it; `v=` carries only other
  changes), and `data-views-change` reports `grouping` (the id in effect, or null). The Group menu shows the effective
  levels; changing them there leaves the grouping for the view's own levels. Switching the grouping clears a nav pick on
  the previous grouping's `groupBy` property (McMaster resets), unless the view sets `keepFilter: true`.
- **Cards: sections** (`sections: true`, implied by `tiles`): `groupBy` draws as a section title (`role="heading"
  aria-level="2"`, 22 px bold in the text colour, its row count, a rule under it), `subGroupBy` as a sub-header
  (`aria-level="3"`, 15 px bold). A sub-group whose key is null draws its children straight under the title, with no
  sub-header and before the named ones, so a section whose rows all lack the second level has no second layer. The
  core's `sectionsOf(groups, columns)` returns `[{key, property, label, rows, count, subs: [{key, property, label |
  null, rows, count}]}]` in that order (a list key reads in each value's label: `groupText`). Headings stay
  lane-spanning items of the one virtualiser.
- **Cards: tiles** (`tiles: {property, image?, link?, all?, limit?, size?}`): inside each (sub-)section one tile per
  distinct value of `property` among its rows instead of a card per row: a picture from the first of the value's rows
  (in view order) that has one (`image`, default the view's `image`; a quiet monogram where none), the value's label and
  its count "(265)"; most rows first, then by label. `all: true` puts "All <group> (N)" first (under a section's no-value
  rows it stands for the whole section). `limit: N` keeps N value tiles while more than one section shows and ends
  with "Every <property label> (M)", M the number of values; once the reader has drilled to one section every tile
  shows. A click goes to `link`'s value on the tile's first row (a real `<a href>`, resolved as a photo's path is);
  otherwise it drills through `host.setFacet`: the section's group, the sub-header's for All and Every, and the tile's
  value, so the page shows only those rows; while the all-views filter picks a value of the tiles' property the
  sections hold the rows as cards. `size` is the tile's width in px (default 120). Tiles are buttons or links; the
  arrow keys move between them as between cards. Counts in titles are the group's rows; a tile's are rows per value.
- **Cards: a built-in switcher** (`switcher: tabs | segmented | dropdown | none`, default none): above the grid, labelled
  "Group by", one entry per `groupings` item (its `label`, else its id), calling `host.setView({grouping})`. For a page
  that draws no switcher of its own.
- **Host seam: `host.setFacet(property, facet | null)`**, and the element method `setFacet` (added to §1's host and
  §6's methods): sets or clears one property's facet-shaped part of the all-views filter, read and written through
  `facets.js`' `toRail` / `fromRail` as `<data-facets>` does (with a rail that can draw any facet, so a second call
  replaces the first; anything not facet-shaped stays verbatim). `facet` is the rail's state of one property:
  `{values, match}`, `{min, max, minOpen, maxOpen}`, `{exclude}`, `{has}`, `{text}`. The rail, the URL's search
  params (`?family=plastic`, `?bbox_volume_ml=250..<1000`) and every view follow; `null` clears it. `groupFacet(columns,
  property, key)` gives the state that picks one group: a value -> `{values: [v], match}`, a bin -> its range, a time
  bucket -> its days; null for "No …" (and for a list row's several values at once).
- **The rail as a filter: `as: nav`** (`KINDS.nav`; `<data-facets>`), McMaster's "Choose a Category": a title (`label`,
  default "Choose a <property label>") and one row per group the view draws, in its order and words: a link-styled
  name and its count "(100)". Counts are disjunctive (`rowmodel.js` `groupEntries(dataset, base, view, {filters})` with
  every pick but the nav's own), so every row keeps its count while one is picked. Single-select: a click writes the
  group's facet (`p == v`, or a bin's `p >= a`, `p < b`), the row is marked (a warm tint from the series' amber mixed
  into the surface, the text colour, `aria-current="true"`), and a click on it again clears it and every group comes
  back. `clear: true | "<text>"` puts an "All <property label>" row at the top. With no `property` (or `follow:
  groupBy`) it follows the views' effective `groupBy` and redraws when the grouping switches; a group no facet can pick
  ("No …") is not listed. The URL round-trips it like every kind: `allSpecs` stands a following nav over every
  grouping's property and a view's tiles (and its second level) over theirs, so `?bbox_volume_ml=250..<1000` or
  `?type_name=…` reads back whichever grouping the page opens on. Under 700 px it is the rail's closed disclosure. Both
  checkers accept a nav facet without `property`.
- [tests/unit/collection.test.mjs (bins against a loop over ObjectDB's public sample, 366 objects of open-licence scans and BAM's generated primitives, edges, nulls, DESC, labelled
  and auto bins; H1/H2 sections with the null sub-group first; groupings resolution and fallback; group -> facet ->
  filter tree -> URL -> back for a value and a bin; both checkers alike); tools/test_check_collection.py;
  gallery/examples/object-collection/checks.py (headings, tiles and rail rows found by scrolling the virtualised grid
  and measured with getBoundingClientRect against a Python oracle over objects.json: H1/H2 nesting, the nav pick,
  `?family=metal` on load, a tile's drill and arrow keys, the switcher by size, shape, type and source with the hash
  and a reload, light, dark and a 375 px phone with contrast ≥ 4.5); tests/unit/perf-oracle.golden.json rebaselined
  for the new case (its `_collection` note)]

## 27. Amendment 2026-10-27 (app rail; additive)

Numbered 27 at merge (drafted as 22, which is value sources; §27 was reserved for this lane). WHY (Zach, 2026-10-27): data-ui had no app navigation sidebar, and
every app on it (RobotDx first) needs one: "with the text and without text, or with the icon and text center (figma
style)… similar to how shopify does it". The three styles are Clank's, ported from clank-workbench @ 7ba2041
(`src/workbench/store.ts`, `shells/shadcn/ShadcnRibbon.tsx`); the rail is a framework-free element, not React.
Decision record: `docs/peps/0009-app-rail.md`. The code is `packages/core/src/rail/` and `styles/rail.css`.

- **The element `<data-rail>`**: an app's left navigation. Light-DOM children are its destinations and the no-JS
  truth (a server writes them; they are plain links until the kit draws them):
  `<a href="#fleet" data-id="fleet" data-group="Data" data-end data-icon="F"><svg>…</svg>Fleet</a>`. `href` is the
  link (a real one: ⌘/middle-click work); `data-id` is its name (default: the label lower-cased, dashes); `data-group`
  heads a run of destinations (a label in the wide style, a hairline in the two narrow ones); `data-end` puts it in
  the footer (Settings); the icon is the first `<svg>` or `<img>` child, else the `data-icon` text, else the label's
  first letter. The label is the anchor's text. A child `[data-brand-icon]` (any markup) is the header's mark.
- **The three styles**, set by `mode` (never keyed on any `data-state`): `collapsed`, icons only, **3rem**;
  `expanded`, Figma's, each icon with its label centred under it, **4.5rem**; `wide`, Shopify's, rows of icon then
  label, **15rem** by default and the only one that resizes. An unknown `mode`, stored or set, is `collapsed`.
- **Attributes:** `mode` (reflected; the initial style is the stored one, else this attribute, else `collapsed`, so
  markup sets a default and a person's choice wins); `open-mode` (`expanded` | `wide`; the style the toggle opens when
  nothing is stored, default `expanded`); `storage-key` (default the element's id, else `rail`); `brand` (the header's
  name; shown in `wide`, a tooltip otherwise); `label` (the `<nav>`'s accessible name, default `brand`); `search` (adds
  the wide style's search field; the value is its placeholder, default "Search") with `search-keys` (the shortcut shown
  in it, text only); `current` (a destination's `data-id`; it gets `aria-current="page"`); `hotkey` (default
  `mod+alt+r`; `off` for a second rail on the page). Properties: `mode`, `lastOpen` (read-only), `current`,
  `destinations` (`[{id, label, href, icon, group, end}]`; `icon` is trusted markup or text), `toggle()`.
- **Toggle, not a cycle.** `toggle()` goes collapsed ↔ the last open style (`expanded` or `wide`), never round the
  three. The last open style is kept under its own key, so it survives a reload while collapsed. WHY: "collapse it"
  must be one press from any open style; which open style you get is the setting's choice.
- **Persistence, immediate.** A mode change writes localStorage before it returns (and again on `pagehide`), never
  through a debounce. Keys: `data-ui/rail/<storage-key>` (the mode), `data-ui/rail/<storage-key>.lastOpen`, and the
  width `data-ui/panel-width/app-rail:<storage-key>` (§11). Every access is try/catch; without storage the choice
  lasts the visit.
- **Events** (all bubble, composed): `data-rail-mode-change` `{mode, previous, lastOpen}` (any change, from the
  setting, the toggle, the collapse button or the key; not on first draw); `data-rail-navigate` `{id, href, label,
  event}`, cancelable, fired when a destination is activated by pointer or key, and the rail marks it current; a host
  that routes itself calls `preventDefault()` and the link is not followed; `data-rail-search` `{via: "click" |
  "key"}`, fired by the wide style's search field on click, Enter or Space, and never on focus (opening on focus would
  trap Tab inside a dialog that hands focus back to the field). The field is a read-only `role="button"` input.
- **Keys:** Ctrl+Alt+R (Cmd+Alt+R) toggles; ↑ / ↓ / Home / End move among the destinations. The collapse button
  (top right of the wide style, the footer's toggle in the narrow two) is the same `toggle()`.
- **The wide style is a side panel (§11).** Its right edge is the splitter: pointer drag, ← / → by 16 px, 200-400 px
  (`data-resizable-min|max` override), width remembered, a double-click resets to 15rem and forgets it,
  `data-resizable="off"` opts out. The splitter is hidden in the two fixed-width styles. The width is
  `--data-panel-width`, honoured only in `wide`.
- **CSS tokens:** `--data-rail-bg` (default `--dv-group`), `--data-rail-width-collapsed` (3rem),
  `--data-rail-width-expanded` (4.5rem), `--data-rail-width-wide` (15rem). The rest are the §4 tokens.
- **Truthful labels.** Every label is drawn whole or with an explicit ellipsis, and its full text is its `title`:
  the narrow label column breaks a camelCase name at its seams (`<wbr>` between a lower-case letter and a capital),
  clamps to two lines, and `overflow-wrap: anywhere` is only the last resort.
- **The settings select:** `RAIL_MODE_OPTIONS` (`[{value, label}]`: "Obsidian: icon rail", "Figma: labels under
  icons", "Shopify: wide list") and `bindRailSelect(select, rail)`: fills an empty `<select>` with the options, shows
  `rail.mode`, sets `rail.mode` on change (an unknown value is `collapsed`) and follows `data-rail-mode-change`;
  returns an unbind function. Also exported from the core: `DataRail`, `RAIL_MODES`, `isRailMode`; and from
  `packages/core/src/rail/model.js`, `createRail({key, mode, openMode, storage})` → `{mode, lastOpen, setMode(),
  toggle(), flush()}`, the element's whole state without a DOM (what the unit test runs).
- [tests/unit/rail.test.mjs; tests/browser/rail_checks.py: widths, label geometry, the toggle, reload, a measured drag,
  double-click reset, fold, the search field's keys; the gallery page `gallery/app-rail/`]

## 25. Amendment 2026-10-26 (dashboard cards, the clock, dashboard styling; additive)

The card catalog, the clock and the `style:` keys of docs/peps/0005-dashboard-cards.md (which holds the keys of every
card, the data shapes and the reasons). Numbered 25 at merge (drafted as 20; §25 was reserved for this lane): §17 is dashboards (PEP 0004), §18 embedded
chrome (status / controls), §19 analyses (PEP 0007), and §20-§24, §27, §29 and §30 were on main before it.

- **A card is a view type.** New types: `timeseries`, `trajectory` (in the chart bundle: one Vega-Lite engine per
  page), `scene3d` (three.js), `video`, `video-compare`, `image` (the media bundle), `gauge`, `bullet`, `barlist`,
  `tracker` (the kpi bundle: SVG/CSS, no engine), `playback` (the clock's control). Each has one key block of the
  same name (`video-compare` uses `overlay:`; `image` reuses Bases' `image: <property>` and `caption:`; the tracker is `tracker`, since §18 made `status:` the status-line key); schemas/view.schema.json is the reference. Each also works in a plain
  `<data-views>` outside a dashboard.
- **One driver** (docs/peps/0008-one-clock-driver.md): `clock.primary`, else the first `video.primary: true` card in
  layout order, drives t; `setDriver` enforces it, and a `clock.primary` naming no video card is a checker error.
- **The clock** (`packages/core/src/clock.js`, exported from `@data-ui/core`: `Clock, clockFor, followVideo, fmtTime,
  seriesColor`). A time-aware view gets its clock with `clockFor(host.element)` (the `<data-dashboard>`'s, else the
  page's one document clock), reports its data span with `clock.extent(t0, t1)`, listens for `time` (`{t, source}`),
  `state` and `hover`, and removes its listeners in `destroy()`. Only the clock's methods change t (`seek`, `play`,
  `pause`, `toggle`, `step`, `setRate`, `setLoop`, `setRange`, `setWindow`, `setHover`, `drive`). Events fire
  synchronously, so on a seek every follower is placed in the same task. A primary video drives t with `drive(t,
  id)` from `requestVideoFrameCallback`; every other video calls `followVideo(video, clock, t0)` on each `time`
  event. A time series honours `clock.window` as its x-domain and sets it from a brush; a pointer move over one
  calls `setHover`. A view marks its moving parts for checks: `[data-playhead]` (a positioned element whose centre x
  is t), `[data-marker]`, `video[data-t0]`.
- **`input.view.style`** is the resolved style of the panel (the dashboard's `style:`, then the panel's, then the
  view's own `style:`): `{theme, surface, radius, pad, gap, title, density, chrome, numbers, palette}`. A view
  reads `chrome` (minimal: no domain line, ticks or vertical grid; a faint horizontal grid), `numbers` (the default
  `{digits, compact}` under a property's and a card's own `format:`), and colours a named series with
  `seriesColor(name, input)` (the palette, else a stable slot). The dashboard draws `surface`, `radius`, `pad`,
  `gap`, `title`, `density` and `theme` itself; a view never draws its own card box inside a dashboard.
  Inside a card that is not a list (a KPI, a chart, a video…), the dashboard clips the panel's status line to a
  screen-reader-only box (the count stays readable by assistive tech); §18's `status: false` on a view hides it
  entirely, and `controls: false` folds a chart's Encode bar, as anywhere.
- **New top-level keys:** `clock: {data, time, rate, loop, fps, primary}`, `style: {…}`, `rerun: {rrd, sdk}`; a
  dataset may say `refresh: 10s`; a layout panel may carry `style:` and `key:`, and `layout.arrange: false` hides
  Arrange. The URL adds `#t=<seconds>` and `#tr=<a>,<b>` (the range).
- **Addendum 2026-10-27 (additive; docs/peps/0005-dashboard-cards.md §4's addendum):** the clock also has
  `setDriver(id)` (the one video allowed to drive t; a dashboard resolves `clock.primary`, else its first
  `video.primary: true` card in layout order, `Clock.primaryDriver(spec, views)`), `release(id)`, `driverId`,
  `fallback` (a driver stalled past `STALL`, 3 s) and `gen` (the seek generation: `drive(t, id, gen)` ignores a frame
  armed before the latest seek). A driver keeps t while it buffers or seeks; t never jumps backward. `setRange` is
  intersected with the span (empty: no range). A dashboard applies `#t=` / `#tr=` edited after load (hashchange,
  popstate); with several dashboards on a page each uses `#t.<key>=` / `#tr.<key>=` (its id, else a slug of its src)
  and falls back to the plain ones.
- **Addendum 2026-10-28 (additive; PEP 0005 §4's round-2 addendum):** a loop wrap fires `time` with source `loop` and
  bumps `gen`. `setDriver` takes a driver key, `<panel key>/<view name>` (`driverKey(scope, name)`); a dashboard
  designates `driverInstance(primaryDriver(spec, views), panels)`, one card instance. A navigation (hashchange,
  popstate) gives what a fresh load of the URL gives (`clockNavigation(params, key)`: an absent t is `clock.home()`,
  an absent or empty tr no range, a malformed value leaves that part) and writes nothing back. New named exports of
  `@data-ui/core`: `driverKey`, `driverInstance`, `clockNavigation`.
- **Addendum 2026-10-28, round 3 (PEP 0005 §4):** URL keys never depend on position: an id as written, else a slug of
  the src when unique on the page; repeated or slug-colliding sources need explicit unique ids, and without them (or
  with a repeated id) the clock stays out of the URL and the problem is listed on every parse. `data-ui check
  FILE.html` reports each such `<data-dashboard>` at its line. `clock.restore(link)` places t for a fresh load and a
  navigation alike; an untouched clock follows `home()` as spans arrive; `clock.atHome`, `clock.note` /
  `setNote(text)`. `driverInstance(name, panels, shown)` designates only a panel whose open tab shows the video.
- **Addendum 2026-10-28 (PEP 0010 P0; sim2real gap #1):** a dashboard's `clock: {data, time}` spans `time` over the
  rows of `data` that its filters leave: that dataset's rail, every selection (the clock is no panel, so none is its
  own) and the links, as `clockSpan(dash, data, state)` in packages/dashboard/src/model.js computes it, set again on
  every change of them. It used to span every row, so a picked 4.5 s run played on the 36 s staircase's clock. When
  no row is left the span is empty: `setSpan(null, null)`, `start` and `end` null, the playback card's empty state.
  t moves by the one rule above (the asked instant, clamped; an untouched clock goes home). The range is cut to the
  span as before; the zoom `window` is dropped while it misses the span and kept as asked while it overlaps; the
  asked instant, range and window come back when a span reaches them again. A live `clock.data` keeps §26's own span.
  [tests/unit/clock-filters.test.mjs; tests/browser/p0_checks.py]
- **Addendum 2026-10-29 (the kit gaps the PEP 0010 template lanes found):**
  - **Annotations from data (gap 2).** `timeseries.annotations` items are `{x: <number>, label, tone}` as before, or
    `{data, x: <column>, label: <column>, tone}`: one mark per row whose x is a time (and whose label, when named, is
    not empty), of `data` (another dataset of the dashboard, handed in as a layer and filtered as a panel on it,
    §32; so a run pick moves the marks) or of the view's own rows. `tone` (good, warn, bad, muted, neutral; default
    muted) colours a mark and its label. The Vega card draws them as one rule layer and two label layers over the
    dataset `marks` ({x, label, tone, color, row, align, ly}); the interactive (uPlot) card draws the same rows.
    `annotationRows(input)` in chart/src/timeseries.js reads them.
  - **Labels never overlap (gap 7).** A label sits 4 px right of its mark (left of it near the plot's right edge), in
    the first of three rows 13 px apart whose last label ends 6 px before it, measured as Vega measures text
    (`labelRows`); a label with no room is left off the plot and read in the hover readout, which lists every mark
    within 6 px of the pointer.
  - **A chart on the clock (gap 3).** A `type: chart` whose x is the clock's own time column, raw (the dashboard's
    `clock.time`, else `t`; a number in seconds, its unit `s` or none: never a duration such as a run's compute time)
    follows the clock as a time series does: its x domain is its rows' time, exact, or the
    clock's zoom window; it reports that span (`clock.extent`); it draws the clock's t as a `[data-playhead]`; its
    compile carries `meta.time = {extent, domain}`. A time series and such a chart keep a y gutter of at least 44 px
    (`GUTTER`, overlay.js) and the same padding, and leave off an x label that would run past the plot's end, so in a
    dashboard column each t sits at the same x (a y label wider than the gutter widens it, never clips; the uPlot cards
    are not lined up yet). Such a chart clips its marks to the plot (a zoom puts spans outside it). A layered chart's own `transform` now
    runs before its layers (it was dropped), and a field a transform makes no longer drops the rows a chart draws.
  - **Media empty text (gap 9).** A view's **`empty: <text>`** is what a video, video-compare or image card says when the
    view leaves it no row (default "No rows match this view.").
  - **Colours (gap 6).** A column's `colors` map takes a slot 1-8, `muted` or 0, `var(--data-…)` or a CSS colour in a
    chart (families.colors' rule, §32). A null cell is muted in a chart, whatever the map or the palette say: its label
    ("No fault") is never a category with a hue, and it takes no slot from the palette's other values.
  - **Aggregates after a swap (gap 1).** A chart swaps a pick's rows in place (`swapData`); when its spec aggregates
    with an op Vega cannot update in place (median, q1, q3, ci0, ci1, min, max, argmin, argmax, product, or a
    boxplot, errorbar or errorband: `freshCells`), the old rows leave first, so every cell is built from the new
    rows. WHY: Vega 6.4's TupleStore memoises extent, quartiles and bootstrap CI under one key (a boxplot's whiskers
    stayed CAN 13's on CAN 12's page), and a product divides out what leaves (0 / 0).
  [tests/unit/kit-gaps.test.mjs, check-kit-gaps.test.mjs; tests/browser/kit_gaps_checks.py]
- **Addendum 2026-10-29 (PEP 0010 P5):** the tracker's matrix mode (`tracker.column`, `columns`, `order`), its glyphs, and
  `kpi.target` naming a property are §35's.
- [tests/unit/clock.test.mjs, tests/unit/media-clip.test.mjs; the dashboard-cards case's checks (every card light and
  dark, the clock sync measured within one frame, overlay modes, one WebGL context, 390 px; one driver, sub-ms paused
  seeks, the URL after load and two dashboards on one page; round 2: loop wraps, one view on two panels, Back /
  Forward against a fresh load, id-less and repeated-id dashboards)]

## 31. Amendment 2026-10-28 (interactive legends; additive)

Every chart that draws a series legend makes it interactive, by default and with no `.base` key. WHY (Zach, 2026-10-28,
on a sim2real time-series card with 8 servo lines): "where there is a legend there is like no reason to not make that
legend interactive… ensure this feature is in data-ui charts by default." Numbered 31 at merge (drafted as 21, beside the cards' §20, now §25): §20-§25, §27, §29 and §30 were taken
before it, and §26 and §28 are reserved for live data and types.

- **The rule** (`packages/core/src/legend.js`, exported from `@data-ui/core`: `legendClick, legendPress, nextHidden,
  hiddenAfter, hiddenOf, encodeHidden, decodeHidden, legendKey, readLegendParams, writeLegendParams, SeriesLegend`;
  the chart bundle's `plotkit.js` re-exports `legendClick`): a click shows or hides a series; a double-click or Alt +
  click shows only it, and again on the one left shows all (Rerun's; a double-click's two clicks never leave a toggle
  behind); a quiet Reset beside the entries while anything drawn is hidden. Each entry is `<button type="button"
  aria-pressed>` (pressed = shown; Tab, Enter, Space as on any button); a hidden one is greyed and struck through.
- **Axes:** y rescales to the series still shown; x stays put. WHY: a hidden outlier must not flatten the rest (Plotly's,
  Grafana's and uPlot's default). A trajectory refits both axes to the paths shown (equal aspect ties them); scene3d keeps
  its camera (no y axis).
- **Truthful:** a hidden series leaves the drawing only. Rows, counts, the status line and the other series' readouts
  are unchanged; nothing stored changes.
- **The seam, for views:** `input.hiddenSeries` (frozen list of series names) and `host.setHiddenSeries(names)` (the view
  has drawn it already; the host keeps it, writes the URL and fires `data-views-legend {hidden}`; it never re-renders).
  `SeriesLegend.sync(input)` takes the host's set when it changed since the host last said (Back / Forward, a link), else
  keeps the legend's own. A host without the call: the view keeps its own set.
- **The element:** `el.hiddenSeries` (get; set redraws the view with it), event `data-views-legend {hidden}`. **The URL:**
  `l=<name>,<name>` in a `<data-views>`'s hash (each name URI-encoded, comma-joined; absent = all shown), re-applied on
  hashchange / popstate. In a `<data-dashboard>`, `l.<panel>=` beside `s.` and `p.` (`writeHash` / `readHash`), scoped as
  the clock is: `l.<key>.<panel>=` with several dashboards on a page (`_clockKey()`), none with `no-url` or no unique key;
  its hashchange / popstate listener re-applies it. Written with replaceState, as the rest of the view state; Back /
  Forward restore the set of the entry they land on.
- **Per view:** `type: chart` hides Vega's colour legend and draws the HTML one; the hidden set is a Vega param
  (`dvHidden`) read by a `filter` on every series layer, and an invisible layer (`dv_legend_ghost`, on while anything is
  hidden) holds x and the colour domain, so neither moves; set with `view.signal(...).runAsync()`, never a re-embed. WHY
  not Vega-Lite's legend-bound selection: its entries are canvas (no button, focus or aria-pressed), it has no
  double-click isolate or Reset, and it dims instead of rescaling y. The time series card leaves hidden series' samples
  out of the drawn data (a date x then pins its domain); the interactive card calls uPlot's `setSeries`; trajectory and
  the playback range's overview leave them out; scene3d hides each series' group. The KPI tracker's legend names states
  (a static colour key) and is unchanged.
- [tests/unit/legend.test.mjs; tests/browser/legend_checks.py: the sim-to-real case's own 8-motor `type: chart` and a
  variant .base adding two 8-motor time series cards over its runs.json, measured from Vega's scenegraph and scales and
  uPlot's canvas and scales; the URL, reload, Back / Forward, keyboard; a standalone `<data-views>`; trajectory, scene3d,
  the range overview]
- **Addendum 2026-10-29 (§34):** a legend entry has an item menu (Show only, Add to dashboard…), and a view's
  `hiddenSeries:` is its legend's hidden set when it opens and the URL names none.
- **Addendum 2026-10-29 (RobotDx PEP 0001 §17.1, ask 1):** the live `plot` card (§26) draws this legend too, the last
  chart with a static key: one button per series, uPlot's `setSeries` hides one (y rescales to the series shown, x stays
  the clock's window; a hidden series' property rules, bands and §35 limits leave the drawing with it, and its line
  leaves the crosshair's readout), the set held through live frames, `l.<panel>=` / `l=` both ways, and the series' item
  menu with Add to dashboard… (§34: the plot with every other series hidden). [tests/browser/dx_asks_checks.py: the
  live dashboard and a recording, measured from uPlot's show flags, its scales and its canvas]

## 26. Amendment 2026-10-27 (live data and rewind; additive)

Live data: a dataset that is still growing, drawn by the same views as of the clock's time, with Rerun's follow and
rewind (docs/peps/0012-live-data.md holds the reasons, the prior art and the numbers). Numbered 26 at merge (drafted as 21;
§26 was reserved for this lane): §20-§25, §27, §29, §30 and §31 were taken before it, and §28 is reserved for types. Nothing here
removes or renames a key, a host call, an input field or a token; a page with no live dataset behaves as before.

- **`LiveDataset`** (`packages/core/src/live/store.js`, exported from `@data-ui/core` and `dist/data-ui.js` with
  everything below): `new LiveDataset({id, title, titleProperty, properties, rows?, time, stream?, key?, retention?:
  {bytes, age}, stale?})`. `time` (seconds) is required; `key` makes it keyed (rows replace by key), else it is an
  append dataset (`stream` partitions it). Methods: `append(rows)`, `appendColumns({<property>: array}, {stream})`,
  `upsert(rows)`, `remove(keys, t?)`, `setStatus(state, detail?)`, `finish()`, `clear()`, `latestAt(t, stream?)`,
  `range(a, b, {stream?, columns?})` → `[{stream, t, cols, from, to}]` (typed-array slices, (a, b]), `snapshot(t, {at,
  limit, filter})` → the newest rows at t, newest first (a view's input puts them back in time order), `streams()`. Read-only: `start`, `end`, `rowCount`, `bytes`, `late`, `status {state, since, detail,
  lastData, tries}`, `recorded`, `live` (true). Events: `change` once per animation frame (`{start, end, appended,
  upserted, removed, dropped, streams}`), `status`. A row without its time gets the arrival time; ids are the row's
  `id`, else its key, else its arrival number. `setLiveBudget(bytes)` / `liveBudget()`: the page's buffer (default
  256 MB). `isLiveDataset(x)`.
- **Retention:** over the page budget or a dataset's `bytes` / `age`, the oldest sealed chunk goes first; the newest
  chunk of a stream and the newest version of a key always stay; chunks within 60 s before a paused clock's t go last.
- **`LiveClock`** (`packages/core/src/live/clock.js`) extends §25's `Clock`, which is unchanged except that `fmtTime(t)`
  writes a wall-clock time for t ≥ 10⁹ s. Adds `following`, `live`, `lag`, `liveStart`, `liveEnd`, `goLive()`,
  `bind(dataset)`, `unbind(dataset)`, `datasets`, `status()`, and the event **`live`** (`{following, lag, start, end,
  status}`). A scrub that starts while following ends paused at the scrubbed t (a playback card's "resume after the
  drag" does not replay). `start` / `end` follow the data while the clock plays and hold still while it is paused (the data's own span
  is `liveStart` / `liveEnd`; `lag = liveEnd − t`). Any `seek` (except the clock's
  own), `step`, `setRange`, `setLoop(true)` leaves following; `setWindow` does not; `toggle()` while following pauses at
  t; `play()` replays from t and rejoins following when it reaches end. `time` events carry `source: 'live'` while
  following. With no live dataset bound it is exactly a `Clock`. `<data-dashboard>` makes its clock a `LiveClock`.
- **The `.base`:**
  - top level `retention: {bytes: 256MB}` sets the page budget (bytes as a number or `64MB`, `1.5GB`).
  - a dataset may carry **`live: {time, stream | key, sse, events, poll, every, since, cursor, rows, retention: {bytes,
    age}, stale, recorded}`**: with `sse:` an EventSource (relative to the `.base`; `Last-Event-ID` is the browser's), with
    `poll:` a fetch every `every` (`since` names the query parameter that carries the last `cursor`; `rows` is a dotted
    path to the rows in the body, arrays flattened), with neither the page pushes rows (`dashboard.datasets.<name>`), and
    with `recorded: true` the `data:` rows are a finished recording. `data:` stays required: its properties and rows are
    the schema and the backlog.
  - every view may carry **`at: latest | all | <duration>`** (`30s`, `5m`, `500ms`): what it shows at t (PEP 0012 §5.1
    table). Defaults: keyed `latest`; `plot`, `levels` `30s` live and `all` recorded; others `all`. A row-reading view
    gets the newest rows at t that pass its filters and search, at most its `limit`, else 2,000, in time order (oldest
    first, as a file's rows are); its own `sort:` orders them (`sort: [{property: t, direction: DESC}]` for newest on
    top).
- **What a view receives (§2):** on a live dataset `input.rows` is the snapshot at t (filtered, searched, sorted, capped)
  and **`input.live`** is `{dataset, clock, t, following, at: [a, b] | 'latest', start, end}` (null otherwise), so a
  view can read the store itself. `total` is the rows retained up to t, `matched` the snapshot's. A view never fetches.
  Views that read no rows (`playback`) get no live redraws.
- **`<data-views>`:** `data` may be a `LiveDataset`; the element redraws at most once per animation frame, and only when
  its snapshot changed. Paused (or replaying) at t, only news at or before t can change it: a row, version or removal
  written at or before t inside its window, or retention taking a row it read at t (a `plot` or `levels`: any sample in
  its span); retention taking rows at t it did not read updates only the status line's count; data after t never
  redraws it (PEP 0012 §8). Its own inputs (filters, search, size, theme) redraw it as always. A table or list on an append dataset is a **tail**: scrolled more than a row away from its
  newest end (the top when it sorts by time descending, else the bottom) or with a row open, it holds its rows and shows
  "N new · Resume" (`.dv-live-new`); the element carries `data-live="following | paused | held"` (held: the tail holds
  while the clock follows). Event **`data-views-live`** `{t, following, rows, ms, frame}` after each live draw
  (`frame`: the live frame loop's number, the same for every view drawn in one animation frame).
- **`<data-dashboard>`:** a dataset with `live:` becomes a `LiveDataset` in `dashboard.datasets`; the event
  **`data-dashboard-live`** `{datasets}` fires once they exist (a host's JavaScript pushes rows after it). Keys add End
  and Ctrl/Cmd+Shift+→ (go live), Home and Ctrl/Cmd+Shift+← (the oldest data). The URL writes `#t=live` while following,
  `#t=<seconds>` while paused; `#t=live` opens following. The bar shows a `<data-live-status>`.
  At merge (2026-10-28), with §25's one rule for a link (`clock.restore(link)`, the same on a fresh load and on Back /
  Forward): a live clock's `restore` pauses at a link's moment or range and follows on `live` or no t
  (`LiveClock.restore`; the dashboard keeps `live` through §25's `clockNavigation` with `liveNavigation`), and while it
  follows the clock's asked instant is the newest data, so a range, span or link change re-places t from there.
- **New view types** (`packages/views/live/`, `dist/views/live.js`, uPlot 1.6.32 inside): **`plot`** (key block
  `plot: {x, y, series, only, unit, dash, rules, bands, legend, height}`; min/max per pixel column; `[data-playhead]`;
  `data-points` on its view element is the number of points drawn)
  and **`levels`** (key block `levels: {state, by, label, order, tones, bar}`; the worst level per time bin, a bin
  being (start, end] so the newest reading at t is in the last one; one `[data-strip="<value>"]` per strip, its
  `[data-bin]` children carry `data-level` (empty: no data), the view element carries `data-t0` / `data-t1`). Both
  work on plain datasets too. At merge `plot`'s legend was its own static key; since 2026-10-29 it is §31's (§31's
  addendum of that date).
  **Addendum 2026-10-29 (kit gap 4):** `levels` on a recording (not live) shows what this § promised, the whole of it:
  the clock's zoom window, else its span, else its rows' own (which it reports to the clock); its strips stand still
  and a `[data-playhead]` marks t. `at: <duration>` (or `latest`: 30 s) keeps the window ending at t. A live dataset
  is unchanged.
- **The playback card** shows **● LIVE** (`.dv-pb-live`, `aria-pressed` = following, the lag as text while paused) when
  its clock is live; a click goes live. Its readout and ticks write wall-clock times for t ≥ 10⁹ s.
- **`<data-live-status [for=id]>`:** one line of connection state for the clock of the element `for` names (else the
  nearest dashboard, else the page's): `data-state="live | connecting | reconnecting | stale | paused | closed |
  recorded"`.
- **Sources:** `connectSSE(dataset, url, {events, map, withCredentials})` and `connectPoll(dataset, url, {every, since,
  cursor, rows, map})` return `{close()}`. SSE `data` is `{"rows": [...]}`, `{"remove": [...]}`, `{"status", "detail"}`
  or a bare array; `event: reset` clears the dataset (the dashboard then reads its `data:` backlog again).
- **Time as a clock or an age:** a property may say `display: clock` (Unix seconds drawn as the reader's wall-clock
  time, `14:03:21.358`; `fmtClock(t)` from `@data-ui/core`); a live dataset gives its time property that display once
  its values are Unix seconds, unless the data says otherwise. The table draws it; `valueText` writes it; a KPI whose
  spark x is such a column says "as of 14:03:21.358". **`display: age`** (on a property or in a view's `display:`)
  draws how long ago ("2.4 s ago", `fmtAge(seconds)`): against the wall clock while the clock follows, so it keeps
  growing with no new row (a live view with an age column redraws once a second), and against t while paused (the age
  at that moment). `$defs.display` lists `clock` and `age`.
- **Reduction helpers** (`@data-ui/core`): `minMaxColumns`, `alignSeries` (min / max per pixel column in time order)
  and `ColumnCache` (the same, kept between frames on an absolute time grid; what `plot` uses on a live dataset).
- **A gallery case's page script:** `site.json` may name `script` (a `*.js` file beside the case); the case page loads
  it as a module after the site's own (the live-robot case's in-page simulator).
- **Addendum 2026-10-29 (PEP 0010 P5):** `levels`' default order and tones are §35's status vocabulary; `plot.limits` is §35's.
- **Addendum 2026-10-29 (RobotDx PEP 0001 §17.1, asks 1 and 3; additive):** `plot`'s legend is §31's (§31's addendum).
  `LiveClock.restore` also remembers a moment or a range asked while nothing live is bound: binding live data later
  leaves the clock paused there, as a link to a moment never follows (`live`, `home` or no t follows the next live
  data, as before). §34's pinned panel is such a clock. [tests/unit/dx-asks.test.mjs; tests/browser/dx_asks_checks.py]
- **Addendum 2026-10-29 (RobotDx PEP 0001 §18.4, asks 1 and 4; additive):** a rich cell (`{value, unit, …}`, §2) in a
  typed number column of an append dataset keeps its unit and the rest of it: the typed array holds its value (`range()`,
  the plots) and a row read back (`snapshot`, `latestAt`, `newRows`) carries the cell as it came, as a file's row does, so
  the KPI card, the table and the peek write its unit, the cell's own before the column's (§2). `appendColumns` keeps such
  cells too, and a keyed dataset's `range()` reads a number column's values, never its cell objects. WHY: a KPI card lost
  the unit of a typed reading, so RobotDx left its column untyped. With it, a table with `units: inline` writes a rich
  cell's own unit in a typed number column, on a file as on live data (its row's unit column first, then the cell's, then
  the column's: the peek's order); `units: column` is as before. The `plot` draws §35's limits and its rules and bands
  from a property on live data too (§35's addendum). [tests/unit/dx-asks-2.test.mjs; tests/browser/dx_asks_2_checks.py]
- [tests/unit/live-store.test.mjs, live-clock.test.mjs, live-model.test.mjs, live-sources.test.mjs;
  tests/browser/live_checks.py (follow → scrub → paused at t with the playhead measured while data appends, back to live,
  frame times on append, the byte cap, the tail); the live-robot case's checks; bench/live.py]

## 32. Amendment 2026-10-29 (3D layers and stage, trajectory3d, voxels, families, layer datasets; additive)

The contract of robotics playback (docs/peps/0010-robotics-playback.md holds the criteria, the prior art and the
reasons; its §15 lists what this amendment settled). Zach, 2026-10-28: "the library feature just allows you to like
draw frames draw arrows etc. And now this is a very particular viewer for a very particular dataclass." Layer 1 is
`scene3d`'s primitives, drawn from any columns; Layer 2 is `trajectory3d`, a thin binding of the trajectory contract
(gallery/robotics/CONTRACT.md) onto them; data-ui knows no robotics word. Numbered 32: §31 is interactive legends, and
lane/map and lane/admin-look each draft a §32 too (unmerged), so whichever lands after this renumbers. Nothing here
removes or renames a key, a host call, an input field or a token: scene3d's PEP 0005 keys (x, y, z, series, target, t,
skeleton, robot, up) draw as before, and a dashboard with one link per pair of datasets filters as before. P1b builds
scene3d's stage and layers and trajectory3d, P2 builds voxels; until then a view of either new type draws the table with
its notice (§1).

- **The stage** (scene3d, trajectory3d, voxels). Every change a view makes to these keys goes through `host.setView`, so
  it rides in the URL (`v=`) and in Save view, and a filter change never resets it.

  | Key | Values | Default | Means |
  |---|---|---|---|
  | `unit` | `m`, `cm`, `mm` | `m`; trajectory3d `mm` | the length unit of every column the view reads; a glTF model (metres, by its spec) is scaled to it |
  | `up` | `z`, `y` | `z` | the scene's up axis; the faces are named from it |
  | `projection` | `perspective`, `top`, `bottom`, `front`, `back`, `left`, `right`, `{dir: [x, y, z], up: [x, y, z]}` | `perspective` | perspective orbits; a face or a `{dir}` is orthographic: drag pans, the wheel zooms, nothing rotates, scale equal by construction. `dir` is the direction the camera looks; `up` the screen's up (default the scene's up axis, or +y when `dir` lies along it) |
  | `axes` | `auto`, `none` | `auto` | ticks in `unit` on a face-aligned view, titled with the axis and the frame |
  | `workspace` | `{model, opacity}` or `{box: [[x0, y0, z0], [x1, y1, z1]], opacity}` | none | the reachable volume, a translucent fill and its edges; `model` relative to the view's data file |
  | `t` | a column | `t` | the time every primitive is windowed by (scene3d, trajectory3d) |
  | `show` | `all`, `trail` | `all` | every time step, or the trail (Zach: "Show all time steps" \| "Decay") |
  | `decay` | seconds ≥ 0, or `inf` | `inf` | the trail's reach behind t: `[t − decay, t]`, `inf` everything up to t, `0` the current sample; never in samples |
  | `fade` | `true`, `false` | `true` | the trail fades with age |
  | `density` | ≥ 1 | `20` | markers per path (points, frames, arrows, arcs): at samples 0, s, 2s, … with `s = ⌊n / density⌋`, plus the last (564 samples at 20: 22 markers); the dial runs 4 to 400, log |

  The faces, for `up: z`: `top` looks along −z (screen up +y), `bottom` along +z (up +y), `front` along +y (up +z),
  `back` along −y, `left` along +x, `right` along −x (up +z for the four sides). With `up: y` each is turned by the
  standard (x, y, z) → (x, z, −y): `top` looks along −y, `front` along −z, `right` along −x, as three.js's ViewHelper
  names them. The trail is Rerun's visible time range (`all` is [−∞, +∞], a trail never shows the future); primitives
  draw at `clock.hover ?? clock.t`.
- **`scene3d.layers: [{primitive, …}]`**: any number, each one primitive drawn in one draw call, named as Rerun's
  archetypes are. A scene3d needs `x`, `y` and `z` (a path) or `layers`. Keys every layer takes: `data` (another dataset
  of the dashboard, below; default the view's own rows, `input.rows`), `color` (the column whose value picks the colour
  through `seriesColor`; default the first `by` column), `t` (default the stage's), `density`, `opacity`.

  | `primitive` | Rerun | Reads (columns) | Its keys |
  |---|---|---|---|
  | `points` | Points3D | `x`, `y`, `z` | |
  | `lines` | LineStrips3D | `x`, `y`, `z` | `by` (a column or a list: one path per distinct value, in time order), `dash` (values of the colour column drawn dashed) |
  | `frames` | TransformAxes3D | `x`, `y`, `z`, `quat` (four columns, w x y z) | `axes: xyz` (X red, Y green, Z blue) or `z` (Z alone, in the series' colour), `length` |
  | `arrows` | Arrows3D | `from` and `to` (three columns each) | `scale` (drawn that many times as long, display only; the card says so) |
  | `arcs` | (traj_compare's Z-arc) | `at` (three), `from` and `to` (four each: the own and the reference quaternion) | `length`; own Z in colour, reference Z muted, the arc between |
  | `meshes` | Asset3D | `links`: each row's `<link>_x/_y/_z` (the scene's unit) and `<link>_qw/_qx/_qy/_qz` | `model` (a GLB, relative to the layer's data file), `by` (one model per value) |
  | `boxes` | Boxes3D | `min` and `max` (three columns each) | |
- **`type: trajectory3d`** (block `trajectory3d:`): one shape, one viewer; every key defaults to the trajectory
  contract's name, so a template may write the block empty. `poses: {x: x_mm, y: y_mm, z: z_mm, quat: [quat_w, quat_x,
  quat_y, quat_z], frame: frame, body: body}`; `series: situation` (one trajectory per value); `family` (default
  `style.families.property`, else `source`); `run: run` (many runs per series draw at `opacity: auto`); `t: t`;
  `target` (the reference series value: dashed, muted, the robot's ghost, Compare's default b; default the series whose
  family is `target`); `modes: {<series>: [line | points | frames | frames-z]}` (default `[line]`); `compare: {data,
  pairs: [[a, b]], scale}` (`data` the difference dataset, required; `pairs` default every pair present whose b is the
  target; `scale` display only, default 1): arrows from a(t) to b(t), and Z-arcs where a series draws `frames-z`, reading
  a's columns as `poses` names them, b's as `ref_<column>`, b's name from `reference`; `robots: {data, model, links,
  series: {<series>: {color: series | muted | 1-8 | a CSS colour, opacity, show}}}` (one robot per series, posed at t;
  the producer runs forward kinematics); `opacity: auto | 0-1` (auto is exactly 1/n over a family's n paths, no floor: dense regions read darker; past about 200 runs an 8-bit framebuffer rounds one path's alpha to nothing, so count a whole rack with `voxels` and `value: runs`); and
  the stage keys. Rows of one body in two frames draw nothing, and the card names both.
- **`type: voxels`** (block `voxels:`; reserved, built in P2, its keys fixed here so P2 needs no barrier): `x`, `y`, `z`
  and `cell` (the cell's edge in `unit`) required; `value: count` (default) `| time | runs | <property>` (time is
  Σ `w` ÷ `hz` seconds and needs `hz`; runs counts distinct `run` values; a property reads pre-gridded rows),
  `summary` (Bases' names: `Average` default, `Median`, `Min`, `Max`, `Sum`), `scale: sequential | verdict` (verdict,
  bad to good, only in the gates overlay), `slice: {axis: x | y | z, at: <coordinate> | all}` (`all` sums through the
  depth), `min` (cells below it are not drawn), `w: w`, `run: run`, `hz`, and the stage keys. Colour: one family's rows
  use its ramp, mixed families grey, never red or green outside `verdict`.
- **`style.families: {property, colors: {<value>: <slot 1-8 | muted | 0 | a CSS colour>}}`**, beside `style.palette`.
  `seriesColor` (P1b) resolves a series' colour: its `palette` entry wins; else its family (its rows' value of
  `property`; a series with two values is unclassified) picks its `colors` entry; a family the map does not list is
  muted, dotted and "unclassified" in the legend (never a hashed slot, which can land on green or red). A family's
  members, in natural order of their names, draw solid, then long dash 8 4, then dash-dot 8 3 2 3; four or more draw
  one hue at `opacity: auto` with one legend entry ("real · 37 runs"). Frame axes are RGB = XYZ, the one red and green
  outside status, always labelled, never a series. `resolveStyle` merges `families` as it merges `palette`: `property`
  replaced, `colors` key by key, dashboard then panel then view. Nothing in data-ui says "real".
- **Layer datasets.** A scene3d layer's `data:`, trajectory3d's `compare.data` and `robots.data` name another dataset of
  the dashboard (a name that is none is a `readDashboard` problem, with its path). Each is filtered exactly as a panel on
  that dataset with the same panel key would be (§17's rules): its rail, every other panel's selections, the links; so a
  layer hears what a panel there hears, and the panel that made a selection does not narrow its own layers. No rows are
  joined (§10's "join, not adopted" holds). The panel's `<data-views>` gets them as the new property **`el.layers =
  {<dataset>: {dataset, rows}}`** and its view as **`input.layers[<dataset>] = {rows, columns, total, url}`** (frozen;
  `rows` the dataset's own row objects that pass, in file order; `columns` shaped as `input.columns`). A layer naming the
  view's own dataset reads `input.rows`. A plain `<data-views>` has `input.layers` `{}` unless a host sets `el.layers`
  (a layer naming a dataset there draws nothing, and both checkers warn). A layers change redraws the view once, after
  the current task, so a click that also changes the filter draws once. `<data-dashboard>` adds `layerFilters()`
  (`{<panel>: {<dataset>: filter}}`); model.js exports `layerRefs`, `layerNames`, `layerFilters`, `panelLayers` and
  `panelFilters` (the element's `panelFilters()`, pure), and `readDashboard` gives each panel its `layers`. Not yet: a
  live dataset read as a layer is handed as the rows it holds when the panel draws, and is not redrawn on news.
- **Links, refined (§17):** two datasets linked directly are joined on every link between them, one semi-join clause
  per link, ANDed (samples and diff_samples on `run`, `device` and `situation`); a dataset with no direct link joins
  along the fewest-hops path as before. WHY: the one-path rule carried only the first link, so a device pick on a
  samples rail left every device's error in a panel on diff_samples, and a series hidden on the rail kept its arrows.
- **The trajectory contract** is gallery/robotics/CONTRACT.md (version 1, a barrier like this file): the tables a
  producer writes (`runs`, `samples`, `poses`, `diff_poses`, `diff_samples`, `links`, `media`, `devices`, `events`,
  `coverage_*`, `grid`, `frames`), their `schemas/*.schema.json` sidecars and `schemas/channels.json` (device channels,
  unit suffixes), and `difference(a, b)`, specified in full with a fixture (`fixtures/difference/`, computed with numpy
  and scipy) that a trajectory library's tests and the gallery checks both read through `gallery/robotics/fixture.py`.
  data-ui reads rows: it never imports a robot type and never computes a difference, a metric or a gate.
- **The checkers, addendum 2026-10-29 (kit gaps 2, 5):** a chart field a transform makes is no missing column, in the
  scope the transform runs in (the chart's own transform reaches every layer, a layer's only that layer; after a pivot
  nothing in that scope is named): calculate, timeUnit, bin and stack `as` (one name also makes `<as>_end`), aggregate,
  joinaggregate and window ops' `as`, fold (key, value), density (value, density), quantile (prob, value), lookup.
  A timeseries annotation with `data:` is a layer dataset like a 3D layer's (unknown: an error; in a file with no
  datasets: a warning), and its x and label columns are checked in that dataset (the Python proof: own rows only).
- **The checkers** (both read the keys from schemas/view.schema.json) accept every key above and refuse, each at its line
  with a sentence that says what was probably meant: a projection (a face misspelt; `diagonal`, `iso` → `{dir: [-1, -1,
  -1], up: [0, 0, 1]}`; `plan`, `xy` → `top`; `xz` → `front`; `yz` → `right`), a decay (`-1` → `inf`; another negative
  → its size; `0.5s` → `0.5`; `.inf` → `inf`), `axes` (`off`, false → `none`), a primitive (the enum's "did you
  mean"), a scene3d with neither a path nor layers, a workspace with neither or both of model and box, a projection
  whose `dir` is [0, 0, 0] or whose `up` lies along `dir`, and a layer naming a dataset the dashboard does not have (in a
  file with no datasets, a warning). The Node checker names every column a layer, the trajectory3d binding (given, or
  the contract's name it defaults to), compare's difference columns, a robot link's `<link>_x` and voxels read that the
  dataset it is read from lacks; the Python proof does so for the default dataset.
- **Settled with this amendment** (PEP 0010 §13 and §15): decay is seconds (Q2); the contract is plain columns and
  difference(a, b) is the fixture's, wherever the library lives (Q7; the home of the types stays Zach's); no key
  depends on the view cube's look (Q1: a corner or edge view is a `{dir}`). The per-series robot keys sit under
  `robots.series` and the family colours under `families.colors`, since a series or family named like a fixed key
  would collide; `axes: none`, not `off`, and `decay: inf`, not `.inf`, because YAML 1.1 reads those two as false and a
  float; voxels' summary uses Bases' `Average`.
- **Addendum 2026-10-29 (PEP 0010 P5):** `trajectory3d.color` and `tolerance` (path_overlay) and `voxels.scale: verdict` with
  `better` are built per §35.
- [tests/unit/dashboard.test.mjs (P1a: layer datasets against panelFilters() under a rail pick, a selection, a link and
  all three; the emitting panel; two links per pair; families), layers.test.mjs, check-robotics.test.mjs,
  robotics-contract.test.mjs; tools/test_check_robotics.py, tools/test_robotics_fixture.py]

## 33. Amendment 2026-10-29 (navigation: a dataset read per pick, one-way links, presets, pickers, history; additive)

PEP 0010 P3 (docs/peps/0010-robotics-playback.md §8, §16; the decision record is docs/peps/0013-navigation.md): Zach's
levels, deployments → runs → one run's playback, on one `<data-dashboard>`, with sim2real's gaps #7 (a selection preset
in the `.base`) and #8 (one-way links). Numbered 33: §32 is 3D layers and stage (lane/map and lane/admin-look each draft
a §32, unmerged; whichever lands later renumbers). Nothing here removes or renames a key, a host call, an input field
or a token; a dashboard that writes none of the keys below filters and draws as before. One behaviour changes for every
dashboard: a pick is now a history entry (History, below).

- **A dataset read per pick.** A `datasets:` entry whose `data:` names a placeholder, `{<property>}` (`runs/{run}.json`;
  several are allowed: `data/{deployment}/runs/{run}.json`), is read one file at a time: the file named by the one value
  of each placeholder that the dashboard's picks leave. The value comes through the links, by the semi-join rules
  (§17, §32): each other dataset that is restricted (its rail, a selection made on it) and reaches this one along links
  that end on `<dataset>.<property>` (every direct link that carries that way, else the fewest hops along the links'
  directions) carries the keys of its rows that pass its own filter, and the sets are met; a selection another panel
  makes on the dataset's own column counts too. With exactly one value per placeholder the file is fetched (each value
  one URL path segment, `encodeURIComponent`, §24's `origin.url` rule; relative to the `.base`), once: the files read
  are kept (the last 12) and a fetch in flight is shared, so flipping back to a run fetches nothing. Otherwise (nothing
  picked, two or more, picks that leave none) the dataset has no rows. model.js exports `placeholders(path)`,
  `fillPath(path, values)` and `templateFile(dash, data, state, name)` → `{path, values, choices}` (`choices[p]`: the
  values left, the first source's row order, or null when nothing restricts p).
  - **Its rows are one pick's:** they narrow no other dataset (a link out of it carries nothing, except to a dataset read
    for the same placeholders), so its rail (Show) never empties the runs. Every row of such a file carries the value it
    is read for (the semi-join keeps only those).
  - **Its panels**, while it has no file, show a line over the view (the view hidden, not removed, so it keeps its size):
    "**Pick one run**" (the placeholder's name, `_` read as a space) with why ("none is picked", "2 are picked: a, b",
    "the picks leave no run"), "Loading run …", or "Could not load runs/x.json"; the panel carries
    `data-wait="pick | loading | error"`, the line is `.dd-wait` (`role=status`). The clock, the layers, the rail and the
    roll-ups read what it holds, as for any dataset: with no file the clock has no span (§25's empty state).
  - The file's own `data:` is read before anything is picked, so it is never a template; a dataset read per pick is not
    `refresh:`ed or `live:`. A host that hands such a dataset in (`load(base, datasets)`) keeps it: no file is read.
- **One-way links** (sim2real gap #8): `links: [{from, to, direction: one-way | two-way}]`, default two-way (as before).
  One-way: the from dataset's picks narrow the to dataset; the to side's never narrow the from side (Power BI's single
  cross-filter direction). Paths follow the directions (`linkPath(links, a, b, {directed: true})`); when two datasets
  are linked directly only the direct links that carry that way count (a one-way link from b to a carries nothing from
  a, and no detour stands in for it). A roll-up's join and a chip's name read links either way. The rail's counts, the
  clock's span and the layer datasets follow, since they read `panelFilter`.
- **Presets** (sim2real gap #7): a view's **`selected: first | <value> | [<values>]`** beside its `select:` is the
  selection its panel makes when the page opens with no `s.<panel>=` in the URL (a fresh load, and Back / Forward to such
  a URL). `first` is the first row the view draws (its sort, groups and own filters, under its panel's filter): with
  `sort: started DESC`, the newest run. Presets resolve in layout order, each applied before the next (a deployment's
  `first` narrows the runs a later `first` picks from); a list or a value is literal (`[first]` is the value "first").
  The preset is written into the hash as the selection it made (`s.runs=run:<id>`), so a link names the run, never
  "first"; a reader who clears it writes `s.<panel>=` (empty), which `readHash` returns as `cleared`, so a reload does
  not bring it back. model.js exports `presets(dash, data, state, skip)` → `{select, rail}`, `presetSelections` and
  `presetValues`.
- **Pickers.** A view whose `select: p` names a property its dataset's rail picks one value of (`{property: p, as:
  select}`) is that pick's second editor: a click sets the rail's pick, as its radio does (one value; the facets nested
  under it settle, §7's `parent:`), and the panel lists every value the rest of the rail leaves (its own pick is left out
  of its filter, as a facet leaves its own pick out of its counts). `selected:` on a picker presets the rail's pick when
  the rail picks nothing on `p` yet (so a template need not write its newest run into `filters:`). Under a facet that
  picks several values (`as: values`) a `select:` is a selection, as before. model.js exports `pickRail(dash, data, rail,
  dataset, p, value)` and `railPicks`; the panel says "click to pick" (`data-pick`).
- **Selections:** a ctrl / cmd-click adds what it clicked to the panel's selection, or takes it out (Power BI's
  multi-select); a plain click replaces it, as before. A table panel marks its selected rows, and a picker its picked
  ones (`--dd-mark`, a `<style data-dd-marks>` in the panel, by row id).
- **History:** a pick (a rail change, a selection, a picker's click) is one history entry (`pushState`); typing in a
  search facet, t, the range, a tab, the legend and a file arriving replace the entry they are on. On Back / Forward
  (`popstate`, `hashchange`) the rails, selections, tabs, clock and legend become what a fresh load of that URL gives
  (presets where it names no selection), and nothing is written back; the clock is placed after the picks, so t lands
  in the span they leave (a file read before swaps in at once; a new one arrives and the clock re-places t from the
  URL's instant, as for a link). WHY: Back restores a pick (PEP 0010 §11 P3), as McMaster's rail does.
- **Chips and labels** name a selected value by its row's title only where the value is a key: the dataset's own rows
  (its `titleProperty`), else across a link to a key column. (It named the first row that shared the value:
  "selected: 0" for a run, through its samples.)
- **The checkers** (both read `direction` and `selected` from schemas/view.schema.json) refuse, each at its line: a
  direction that is neither one-way nor two-way (did you mean); `selected:` with no `select:`; a placeholder no link ends
  on; a dataset read per pick with `refresh:` or `live:`; the file's own `data:` as a template. They warn on a link into
  a dataset read per pick written two-way, and on one out of it. The Node checker also reads the first file a template
  names (any one stands for all): a placeholder that is none of its columns is an error, no such file a warning (the
  views reading it are then not checked), and a literal `selected:` value that the view's dataset does not hold, a
  warning. `data-ui check` reports the file it read (`runs/<run>.json`).
- [tests/unit/p3-nav.test.mjs (the model), check-p3.test.mjs and tools/test_check_p3.py (the checkers, on
  tests/fixtures/p3/); tests/browser/p3_checks.py: gallery/examples/robotics-deployments (the network log, the clock's
  span, two picks, Back and Forward, the presets and the URL), tests/browser/fixtures/p3/ (one-way against two-way, the
  rail's counts on both sides; a literal preset and a cleared one), the kit gaps' driver fixture, the robotics
  templates' runs tables; light and dark at 1280 and 390 px]

## 34. Amendment 2026-10-29 (Add to dashboard; additive)

Zach, 2026-10-29 (relayed by RobotDx): "Dashboards are built with data-ui. Humans curate, AI builds." People reorder a
dashboard (Arrange, §25) and add to one from any view of the data, "like the amazon thing of adding to a saved list"; the
item goes to the bottom of the chosen dashboard, to be arranged later. "This is a standard feature you can support in
data-ui, shouldn't be specific to robotdx." Numbered 34: §33 is navigation, and lane/p5-gates takes §35. Nothing here
removes or renames a key, a host call, an input field or a token. **data-ui never writes a file:** as with `propose`
(§1), the host saves the text it is handed, and the kit says what the host answered.

- **Where.** "Add to dashboard…" is on a `<data-views>`' ⋯ menu (`toolbar="full|compact"`, `[data-add-dashboard]`) and
  in View settings (`toolbar="bar"`, `[data-act=add-dashboard]`, after Copy view as .base); on every `<data-dashboard>`
  panel's own menu (`.dd-panel-menu`, ⋯ at the panel's top right, quiet until the panel is hovered or focused and always
  shown on a touch screen, its item in `.dd-panel-pop`; not on the playback bar; a panel with no title row whose
  toolbar has its own ⋯ keeps that one); and on an item menu (`.dv-itemmenu`, role=menu: a right-click, a long-press, the
  ContextMenu key or Shift+F10) on a legend's series (`Show only “J2”`, the legend's Alt + click, and `Add “J2” to
  dashboard…`), on a card of a `type: kpi` view, and on a field of the record peek (a record's cell). Shift + right-click
  keeps the browser's menu, and a value with `data-provenance` keeps §22's. `toolbar="none"` has no ⋯: the host calls
  **`el.addToDashboard(target?, {anchor?})`** from its own control (`anchor`: the element the picker opens beside, a
  point `{x, y}`, or a function that finds the element, asked each time the picker places itself: a bar redraws its
  buttons, a legend its entries; the item menu's keyboard route keeps one for its item).
- **What is added: `el.panelSpec(target?, {t?})`** → `{kind, title, view, dataset: {name, data, label?}, properties?,
  h?, t?}`, what the reader sees. `view` is the view's entry with the reader's changes (a sort, a grouping), its
  `filters:` the AND of the view's own, the all-views filter (the rail and the query's clauses; in a dashboard the
  panel's rail, the other panels' selections and the links' semi-joins, §17), the words searched (`.contains` clauses
  over the visible properties when they keep exactly the searched rows, else those rows' ids) and "Show only selected"
  (the ids); its `hiddenSeries` is the legend's hidden set. Left out: `from` (appendPanel sets it), `selected:` (a preset
  would narrow the target's other panels when it opens) and a dashboard's resolved `style` (the view's own is kept).
  `dataset.data` is the data file, its path from the site's root on the page's origin, else its URL; rows set from
  script with no `url` have no file, and the picker says so. `properties` are the `.base`'s `properties:` entries for the
  data's columns. In a dashboard `dataset.name` and `label` are the dataset's and `h` the panel's height (`w` is never
  carried: below). The targets: `{kind: 'view'}` (default); `{kind: 'series', name, names}`, the view with every other
  series of that legend hidden (`hiddenSeries`; drawing state, never a filter: rows and counts stay the view's, §31);
  `{kind: 'value', group: i}`, a KPI card: the view narrowed to its group by a clause on the group's value (a time
  bucket's span, `.isEmpty()`, `.contains` on a list), checked to keep exactly the card's rows, else their ids;
  `{kind: 'value', id, property}`, a record's cell: a `type: kpi` card of a number (`kpi.value.property`) or a
  `type: record` of that one field, filtered to `id == …`. "At this moment", offered when the view's clock
  (`clockFor`, §25) has a span, adds `t`, the clock's t to the millisecond.
- **The picker** (`.dv-addpick`, role=dialog, in the light DOM of the `<data-views>` it comes from, fixed to the window,
  so it takes that element's tokens; a sheet with 8 px gutters under 480 px): what is added ("“Runs” · 7 rows"), "At
  this moment" (`input[name=at-moment]`, with the instant), the dashboards the host lists (`[data-dashboard-id]`), "New
  dashboard…" (`[data-dashboard-new]`; a name, `input[name=dashboard-title]`; `[data-dashboard-create]`), and a status
  (`.dv-addpick-status`, role=status, `data-state` = `adding | added | copied | error`). Escape, ✕ or a press outside
  closes it and focus goes back. `.dv-addpick` and `.dv-itemmenu` are the light DOM classes a host may skin.
- **The host hook `dashboards()`** (optional; Amazon's list of lists): a function on the element or any ancestor (a
  `<data-dashboard>`, `<body>`, `<html>`) that resolves `[{id, title, url?, text?}]`. `text` is the dashboard's text when
  the host holds it; else `url` is read (`cache: no-store`) and is the `base` its data path is written against. A
  rejection is said in the picker, and New dashboard… stays. No hook: no list, New dashboard… only.
- **`appendPanel(text, panel, {title?, base?})`** (pure; exported from `@data-ui/core`; `packages/core/src/
  add-to-dashboard.js`) → the dashboard's new text, the panel at the bottom of `layout.panels`. Every line of `text` is
  kept, unchanged and in order, and lines are only inserted: a `datasets:` entry after the last one, the view after the
  last view, the panel after the last panel (before a comment that follows it), and a block the file lacks before the
  next block it has (`datasets:` and `properties:` before `views:`, `views:` before `layout:`, `layout:` at the end).
  The one exception: a block written in flow style (`datasets: {a: x.json}`, `layout: {panels: […]}`) is rewritten in
  block style, its entries as they were. CRLF stays CRLF; a file with no final newline still has none. **Datasets are
  matched by file**, resolved against `base` (the top level's `data:` counts, through its name, §17), so one file is never
  added twice; a new dataset whose name another file holds becomes `name_2`, and is written relative to `base` on the
  same origin (absolute on another; as given with no `base`). A view whose name is taken becomes "Name (2)" (the panel
  keeps the clean `title`), and a panel whose derived key is taken writes a `key:` of its own, so moving it never swaps
  two panels' URL state. The panel has **no `w`**: full width, it sits below every panel, however the last row is
  filled; it carries `h`, `t` and `title` (when it is not the view's name). `properties:` entries are added only where
  the dashboard has none (its own stay as written). An empty text (or comments only) is a new dashboard: `# <title>` on
  the first line, then `datasets:`, `views:`, `layout:`. A text that is not a `.base` (a list, a syntax error) is
  refused with the reason, and the result is read back before it is returned, so a broken file is never handed out.
- **The event `data-add-to-dashboard`** (bubbles, composed, cancelable), fired on the `<data-views>` the panel comes from,
  detail `{dashboard: {id, title, url, new}, panel, text, respondWith(promise)}` (`new`: made by New dashboard…, `id`
  null; `text` null for a listed dashboard with neither `text` nor `url`: the host appends `panel` itself). A host that
  saves calls **`respondWith(promise)`** while the event is dispatched (FetchEvent's: one listener claims the add and
  reports the save, so the kit knows at once whether anyone listens, with no timeout); it marks the event handled. The
  promise resolves (anything, or `{ok: true, title?, href?}`: "Added to <title>", with "Open ↗" to `href`) or rejects /
  resolves `{ok: false, reason}` ("Could not add to <title>: <reason>"). `preventDefault()` with no `respondWith`: the
  host took it over, and the picker closes. Neither: **the text goes to the clipboard** (a new dashboard's own when the
  host gave nothing to append to), and the picker says so ("Copied the new dashboard “Scratch” to the clipboard: save it
  as a .base file"); with no clipboard it shows the text to copy. The kit reloads nothing: a host that saved reloads the
  dashboard it shows (`dash.reload()`).
- **In `<data-dashboard>`.** An added panel is drawn at the bottom on the next load, and Arrange moves it like any other
  (a saved arrangement puts panels it does not name last, §25). Each panel's `<data-views>` gets **`el.dashboardPanel`**
  (`{key, title, dataset, label, h, views}`: the views as written, so the spec carries the view's own `style`, not the
  resolved one). A view's `hiddenSeries` is the panel's hidden set when the URL names none (`l.<panel>=`, §31). A panel's
  **`t`** pins it: the panel's section holds a `Clock` of its own, paused at `t` (`restore({t})`), which its views find
  first (`clockFor` walks up), never the dashboard's clock, its keys or its URL; its title says "at t = 1.2 s"
  (`.dd-at`); its video never drives the dashboard's clock. Arrange keeps the page where it was: turning the grid into
  gridstack's (and back) collapsed it for a moment, so a dashboard lower on its page jumped to the top (found here: a
  panel added at the bottom left the screen when the reader pressed Arrange).
- **Addendum 2026-10-29 (RobotDx PEP 0001 §17.1, asks 2-5; additive; found wiring /dx/'s Add to dashboard):**
  - **The declared file.** In a `<data-dashboard>`, `panelSpec()`'s `dataset.data` is the file the dashboard declares
    for the panel's dataset: its `data:` resolved where the .base lives (`src`, else the host's `baseUrl`, else the page:
    the rule a per-pick file already had), a per-pick dataset's the one file its picks read; the rows' own url only
    when there is none. `el.dashboardPanel.file` says it (read when asked); `declaredFile(dash, name, {base, picked})` in
    packages/dashboard/src/model.js computes it. WHY: a host may hand one dataset object to several declared files
    (/dx/ hands every board one config dataset), so the object's url is whichever binding made it first, and a panel
    saved from another board read that board's settings. A host that draws a .base itself with `load()` sets
    `baseUrl` to where it lives.
  - **A pinned panel on live data stands at its t.** The panel's clock is a `LiveClock` (exactly a `Clock` while nothing
    live is bound) restored at `t` before its views bind their live data, so it stays paused there (`following` false)
    while the dashboard's clock follows; it lets go of data a reload replaced, and goes when the panel's `t` does. WHY:
    a view of live data that found a plain `Clock` made a `LiveClock` of its own and followed it (measured on /dx/: 4.3 s
    past t).
  - **The picker outlives a redraw of its dashboard** (`reload()`, or `load()` as /dx/ draws its dashboards): when the
    `<data-views>` it came from leaves the page, it waits off the page (up to 2 s) for the element of the same id the
    redraw makes, moves into it where it was (its anchor gone, it keeps its place inside the viewport), takes back the
    focus the redraw dropped, says how the add went, and adds through that element from then on (`panelSpec` and the
    event); with no such element it closes. An item menu still closes. So a host that saved may reload the dashboard it
    shows at once, before or after it answers.
  - **t as the clock writes it.** The picker's "At this moment" and the pinned panel's `.dd-at` write t with the
    playback bar's formatter (`fmtTime`: `14:03:21.36` for a live clock's Unix seconds, `1.20 s` on a recording);
    the exact seconds are the element's title (`t = 1792631514.923 s`).
  [tests/unit/dx-asks.test.mjs; tests/browser/dx_asks_checks.py on tests/browser/fixtures/dx_asks/ (101 checks: two
  host-drawn boards sharing a dataset, a src board; At this moment from a following live dashboard, loaded where the
  same live data keeps arriving, through a reload; the picker through reload() before and after the answer and
  through load(), a second add, the keyboard; light and dark at 1280 and 390 px)]
- **New keys** (schemas/view.schema.json; both checkers read them and refuse the wrong shape at its line): a view's
  **`hiddenSeries: [<series name>]`**, the series its legend hides when it opens and nothing else names a hidden set (no
  `l=` in the URL, none set by the host; a reader's toggles still win; a plain `<data-views>` reads it on its first
  start); a layout panel's **`t: <seconds>`**, the instant it stands at.
- **Not carried** as keys of the new dataset entry: a dataset's `facets`, `filters`, `tree`, `rollup`, `refresh` and `live`
  (the target's rail and roll-ups are its own curation; the source rail's state at that moment is already in the view's
  `filters:`); a per-pick dataset is added as the one file its pick read, so the panel stays on that run, and a live
  dataset as its file. Without `base` a file is matched by its path as written, so a host that knows where
  the dashboard lives passes it.
- [tests/unit/add-to-dashboard.test.mjs (appendPanel: insert-only, flow blocks, CRLF, the open last line, dedup by file
  and through `data:`, renames, keys under a reorder, an empty text, paths, `properties:`, refusals, both checkers on the
  output and on the two keys), tools/test_check_add_to_dashboard.py; tests/browser/add_to_dashboard_checks.py on
  tests/browser/fixtures/add_to_dashboard/ (70 checks: the item on every surface, the round trip of a `<data-views>` under
  a rail pick, a search and a sort and of dashboard panels under another panel's selection and a link, measured against
  the fixture's files; below every panel, getBoundingClientRect; Arrange; a series, a KPI card, "At this moment";
  insert-only, dedup and rename after four adds; both checkers; the clipboard with no host; a host's errors and
  take-over; light and dark at 1280 and 390 px)]

## 35. Amendment 2026-10-29 (diagnostics and gates: the view hints; additive)

PEP 0010 P5 (docs/peps/0010-robotics-playback.md §10, §11 P5). Zach, 2026-10-28: "Data-UI should have standard views
for showing diagnostics data. Also for showing gates, and KPIs etc. RobotDx should be using those stock parts and now so
can sim 2 real." A diagnostic in a producer's catalog carries a `hint`; each hint is an existing view type plus keys, and
no new type is added. data-ui computes no gate, metric or verdict: producers (RobotDx's `robotdx.diagnostics`,
bam_rack_twin's acceptance, sim2real) write them as rows (PEP 0010 §10's diagnostic row). Numbered 35: §34 is taken by
lane/add-to-dashboard. Nothing here removes or renames a key, a host call, an input field or a token; a view that uses
none of it draws as before, except that a tracker block wide enough for one carries its state's glyph.

| Hint | Expressed as |
|---|---|
| `gate_matrix` | `tracker` + `tracker.column` (matrix mode, below) |
| `threshold_band` | `timeseries` / `plot` + `limits: {warn, error}` (below) |
| `kpi_trend` | `kpi` with `spark` and `target` (a number or, new, a property) |
| `rollup_tree` | `table` + `tree: {parent}` + a §17 dataset roll-up (`Max` of `rank`) + `display: status` |
| `evidence` | the side peek: `record.sections[].view` (an embedded view bound to the peeked row) and `display: link` |
| `distribution` | `chart` (§5.4 of the PEP); unchanged |
| `level_history` | `levels` (§26); its default order now ranks the gates' words too |
| `path_overlay` | `trajectory3d` + `color: <property>` and `tolerance` |
| (coverage verdicts) | `voxels` + `scale: verdict` (reserved in §32, built here) and `better` |

- **The status vocabulary** (`packages/core/src/status.js`, no imports; exported from `@data-ui/core`: `STATUS`,
  `STATUS_ORDER`, `TONE_GLYPH`, `statusOf`, `worstStatus`, `statusHtml`). One word list for the gates' verdicts and
  RobotDx's levels (ROS diagnostics'), so one view draws either feed:

  | Words | Tone | Glyph |
  |---|---|---|
  | `pass`, `ok` | good | ✓ |
  | `warn`, `warning`, `partial` | warn | ! |
  | `fail`, `error` | bad | ✕ |
  | `not_run`, `not run` | muted | – |
  | `unknown` | muted | ? |
  | `stale` | muted | ◷ |

  A word the list does not hold is `neutral` (glyph •); a missing value is muted and reads "no value". The tone is the
  first of: the view's own map (`tracker.tones`, `levels.tones`), the column's `tones` (a field schema key beside
  `labels` and `colors`, data.js passes it through), the list. A value is looked up as stored, then as its label, so a
  rank column labelled `{0: pass, 4: fail}` reads as those words. `STATUS_ORDER` is best to worst (`ok`, `pass`, `warn`,
  `warning`, `partial`, `unknown`, `not_run`, `not run`, `stale`, `error`, `fail`: RobotDx's ranks, ok 0 < warn 1 < unknown
  and not run 2 < stale 3 < error and fail 4); `worstStatus(values, order)` is the worst by it (a word it does not hold ranks best). Green and
  red mean status only and always come with a glyph and a word (PEP 0010 §7). Tone colours are core tokens now
  (`--dv-tone-good|warn|bad|muted|neutral`, from `--data-good|warn|bad` with a quiet green, amber and red under them, as
  the KPI bundle had them), and `input.tokens.tone` holds them resolved.
- **`display: status`** (`display: {p: status}` on a view, or `display: status` on the field): the value as a badge,
  its glyph (`aria-hidden`) and its word (the label when the column has one) in its tone: `<span class="dv-state
  dv-tone-<tone>" data-state="<value>"><span class="dv-state-glyph" aria-hidden="true">✓</span><span
  class="dv-state-word">pass</span></span>`. A list draws one badge per value. The table draws it, and so does every
  place a cell is written with `valueHtml` (the side peek, the record view, the cards' fields). WHY (sim2real gap #12,
  generalised): text badges could not be colour-mapped, and a colour alone never says pass.
- **`display: link`** in the side peek: a field the view displays as a link (`display: {p: link}`) is a real `<a
  href>` (`.dv-peek-link`), resolved against the data file's URL as a photo's path is; the table already drew it.
- **The gate matrix: `tracker.column: <property>`** (matrix mode; gap #11). One row per group (`groupBy`, in
  `groupOrder`), one column per value of `column`: `tracker.columns: [values]` fixes their order (each drawn even when no
  row has it), else the order the view's sorted rows first show them. The header names each column by its value's text
  (`labels` applied); the row header by its group's. The matrix is one CSS grid (`[role=grid]`; each row `[role=row]` a
  subgrid; header cells `[role=columnheader][data-column]`, row headers `[role=rowheader]`), so a column's cells share one
  x and one width in every row; the row headers' column is at least `min(7.5em, 28%)` and at most its longest name (a
  name cut short ends in an ellipsis, whole in its hover), a gate column at least 18 px; past the panel's width it scrolls
  inside the panel, never the page, and a header narrower than 64 px turns on its side. A cell is `[role=gridcell]` with `data-column`, `data-state`, its tone, a glyph
  (`.dv-tracker-glyph`, the vocabulary's) and `aria-label="<row> · <column>: <word>"`. A cell no row reaches is `n/a`
  (`data-na`, an empty outline, glyph –, not clickable): a gate that does not apply is never drawn as one that passed. A
  cell several rows reach draws the worst of them (`STATUS_ORDER`, or `levels`-style `tracker.order`) and its label adds
  "worst of N rows". A cell of one row carries `data-id` and a click or Enter opens that row as a record (the side peek's
  rich record, its sections, its evidence link); several rows open as the records behind the cell; arrow keys, Home and
  End move between cells. `tracker.label` names the column a cell's hover adds. Without `column:` a tracker draws as
  before, its blocks carrying a glyph when 12 px or wider; the legend's keys carry their glyph as generated content, so a
  key's text stays its word.
- **threshold_band: `limits: {warn: [lo, hi], error: [lo, hi]}`** on `timeseries` and `plot` (RobotDx's `Limits`; the
  diagnostic row's `warn_lo`, `warn_hi`, `error_lo`, `error_hi`). Each end is a number, a property (read per series from
  the rows the view draws, as §32's property rules are: a device's own limit follows the rail's pick, a split by device
  draws each device's own), or null (no limit on that side). Per series it draws a dashed rule at each limit present
  (warn in the warn tone, error in the bad tone; the label "! warn" or "✕ error" once per line) and the zones beyond them:
  between a warn and an error limit in the warn tone, from an error limit (or a warn limit with no error beyond it) to the
  plot's edge in its own tone. A limit that changes over time is a step line, as a property rule is. The Vega card's
  dataset `guides` holds `{guide: 'limit:<warn_lo | warn_hi | error_lo | error_hi>', series, x, value}` per rule point,
  one set per series even where series share a line (each device's own), and `{guide: 'zone:<bound>', series, x, lo, hi}`
  per zone point, an edge null; one layer per limit and per zone. With limits the card sets its y domain itself: the drawn
  values, every limit and every numeric rule or band, padded by 6 % (nice off), because a Vega-Lite area cannot end at
  the plot's edge in pixels and an open zone ends at the domain's (core guides.js `limitGuides`). The live plot's
  `plotView.guides` hold the limits and zones with their `shared` series, and its y range takes the limits in. The
  interactive (uPlot) time series does not draw limits yet.
- **kpi_trend:** `kpi.target` may name a property (the newest row's value, as the gauge reads `min`, `max` and `target`):
  the card's "target" line, `compare.against: target` and the history's target rule follow it. Otherwise the KPI card is
  as built: `spark: {x, y}` is the trend (a line; points while sparse), `compare` the delta, `select:` in a dashboard
  narrows the other panels as on any view.
- **rollup_tree:** a dataset with `tree: {parent}` and a §17 roll-up `values: {<column>: {property: rank, summary: Max}}`
  from the gate rows gives every node the worst rank under it; the field's `labels` (rank → word) and `display: status`
  draw it as the worst word with its glyph. No new key. RobotDx's causal roll-up (the spider tolerating one leg) stays in
  RobotDx and arrives as rows.
- **level_history:** `levels`' default order is `STATUS_ORDER` (it was `ok, warn, unknown, stale, error`, whose order is
  unchanged), so a bin holding a warn and a fail shows the fail; its default tones are the vocabulary's.
- **evidence: `record.sections[]: {name, properties?, view?}`.** A section may carry `view`, an inline view entry (any
  type; `from:` names a dataset of the dashboard, else the view's own) drawn in the side peek under the section's fields,
  over that dataset's rows as its file holds them (no rail, selection or link: the evidence is the row's, whatever the
  page has picked), its `filters` with `this.<column>` bound to the peeked row's values (the analyses' rule, §19:
  `bindThis`, now `@data-ui/core`'s). It is a `<data-views no-url toolbar="none" status="off" controls="off">` inside
  `.dv-peek-view[data-section]`, 240 px tall, on the page's clock, with the outer view's resolved `style` (families,
  numbers) unless its entry has one; it opens no peek of its own, and the keys pressed in it stay in it (Escape still
  closes the peek). A dashboard hands its drill peek those datasets (`el.sections = {<dataset>: dataset}`); a plain
  `<data-views>` reads its own data, or what a host sets in `el.sections`. With `display: {evidence: link}` the row's
  `evidence` URL (a producer's `…#t=t0&tr=t0,t1`) is the link that opens the playback at the evidence window. Fixed with
  it: the split peek's margin is its element's own stage's (`data-views.dv-split > .dv-stage`); a descendant rule drew a
  nested view 0 px wide.
- **path_overlay:** `trajectory3d.color: <property>` paints each path (not the target) by a number its rows carry, per
  vertex, on the 2D card's sequential ramp (series 1 to the warn tone) over the drawn rows' min..max, with the ramp's bar
  and its ends in the card; `trajectory3d.tolerance: <number>` (the stage's unit) draws the target's path again as a
  translucent tube of that radius (three's `TubeGeometry` along the path; in a face view its projection is a band 2 ×
  tolerance wide), and the legend says "± <tolerance> <unit>". The producer writes the number (an error column is the
  difference rows' `err_mm`, written onto the pose rows): the view never computes an error.
- **voxels: `scale: verdict`** colours the cells from the bad tone through the warn tone to the good tone over the
  domain (OKLab, as the sequential ramp), `better: higher` (default; BAM Reach's reach score) or `lower`; the ramp's bar
  carries ✕ at its bad end and ✓ at its good end. Only in a gates overlay (§32).
- **Live:** a keyed `LiveDataset` (§26) of diagnostic rows feeds the same views as a file does (RobotDx's checks: rows
  keyed by subject and diagnostic, newest version per key as of the clock's t); nothing here is live-only.
- **The gallery:** each robotics template has a "Playback + Gates" twin (`gallery/examples/robotics-<part>-gates/`,
  README `- **Use case:** Robotics · Playback + Gates`): its `.base` holds every dataset and view of the template
  unchanged, reading the template's files (`../robotics-<part>/…`), plus the gate datasets its `source/` writes from the
  archive (RobotDx's library on the real runs; stand-in rows say `basis: stand-in`) and the overlay's views. The seam
  between the two is a file diff. `gallery/robotics/gates.py` holds what the producers share.
- **The checkers** (both read the keys from schemas/view.schema.json; `$defs.limits`, `$defs.limitPair`) accept every key
  above and refuse, each at its line: a display that is no display (`statuss`: did you mean 'status'), a `limits` side
  that is neither `warn` nor `error` (`warning`: an unknown key), a `limits` side that is not a pair, `scale` and
  `better` values outside their enums, and a section with neither `properties` nor `view`. An embedded section view is
  checked as a view (its type, its keys, the same warnings as a top-level view), and the Node checker refuses a section
  view's `from:` that names no dataset of the dashboard (did you mean). The Node checker names, at its line, a
  `tracker.column`, a `limits` end, a property `kpi.target`, a `trajectory3d.color` and an embedded section view's
  columns that the dataset they are read from lacks, and a `this.<column>` that the outer view's dataset lacks.
- [tests/unit/p5-status.test.mjs, p5-matrix.test.mjs, p5-limits.test.mjs, p5-peek.test.mjs, p5-scene.test.mjs,
  check-p5.test.mjs; tools/test_check_p5.py; tests/browser/p5_checks.py: the six twins (every matrix's columns aligned
  within 0.5 px, its header the column values, every cell a glyph and an accessible name, a cell click opening the peek
  on its row and the evidence link landing on its window), the deployments twin's limits per station within 1 px, its
  roll-up against an oracle, the KPI trend's points against the rows, a keyed live dataset feeding the deployments
  twin's matrix (tests/browser/fixtures/p5/), the arm twin's path overlay and verdict voxels; light and dark at 1280 and
  390 px]
- **Addendum 2026-10-29 (RobotDx PEP 0001 §18.4, ask 1; additive):** on a live dataset the `plot` holds no rows (it reads
  the store's typed arrays, §26), so its limits, and its rules and bands from a property, are read from the store as of t:
  each drawn stream's samples in the window ending at t, a few per run of a guide column's values (a stream's first and
  last, and both sides of every change; core live/window.js `guideRows`, its changes found once per sealed chunk), which
  draw what every row in the window would. They draw by number and by property per series, follow, and rewind with the
  clock; `plotView.guides` holds them as on a file. A limit's line is snapped to the device-pixel grid (one crisp row in
  its status tone, within half a pixel of its value; a fractional y blended with a grid line's grey). With limits drawn,
  the plot's y also takes in every numeric rule and band (the time series' rule above), and a series `only:` leaves out
  draws no limit. WHY: RobotDx's threshold_band plot showed its readings and no limit (`input.rows` 0, 45 readings in the
  store). [tests/unit/dx-asks-2.test.mjs: the guides from `guideRows` equal those from every row in the window;
  tests/browser/dx_asks_2_checks.py: `plotView.guides` against an oracle over the window's rows, each line's pixels at its
  value's y within 1 px, the zones, y, a hidden series, three t's across a limit that changes]
- **Addendum 2026-10-29 (RobotDx PEP 0001 §18.4, ask 3; additive):** a `record.sections` entry with nothing for the
  peeked row is not drawn: no field with a value (0 and false are values; `{value: null, why}` is a reason, which is
  something to show) and no row in its view (counted as the embedded view will draw it: a file's rows through its bound
  filters, a live dataset's at its clock's t in the view's window). A section that is drawn keeps its empty fields as "—",
  as before, and the edit form draws every section. No key: hiding is the rule (`peekSections(view, props, row,
  {rowsOf})`; without `rowsOf` every section stays, as before). WHY: one table holds plain checks beside stock
  diagnostics, and a plain check's peek drew three sections of dashes and an empty table. [tests/unit/dx-asks-2.test.mjs;
  tests/browser/dx_asks_2_checks.py: a live dashboard's drill peek and a plain <data-views>]

## 36. Amendment 2026-10-30, reworked 2026-10-31 (source columns: one property per source, and a formula over them)

Zach, 2026-10-31: "its just like a column roll up where the left most take precencde. And then to hide them it simply like a view with
thoose columns hidden. The roll up itsself is also then just like a formula.. almost like FIRST Value(of cells, x, y, ...)", and "Desired
is notions: pattern where you have 1 property per cell". The why, the criteria and what became of each earlier behaviour are
`docs/peps/0021-source-columns.md`, which supersedes `docs/peps/0015-source-precedence.md`; the pure half is
`packages/core/src/precedence.js`. What a producer may change, and when: `docs/migrations/source-columns.md`. No data file changes; data
with no list of sources and no formula is the same object, and draws as before.

- **A cell's sources** (the data): a rich cell may carry `sources: [{source, value, text?, unit?, basis?, note?, asOf?,
  sourceUrl?, sourcePage?, record?}]`, each entry a §22 rich cell one source states. `source` names one of the dataset's
  sources (an undeclared name is a source of its own). An entry with no value states nothing. A cell with `sources`
  reads as its nominal: its own `value` and `text` are not used. `unit` and `why` on the cell are the entries' defaults.
- **A dataset's sources and ladder** (optional, keys of the runtime shape, §3): `sources: {<id>: {name, kind?,
  rung?, date?, url?, page?, basis?}}` and `ladder: [{id, label}]`, best first.
- **One property per source.** The reader unfolds each value's list into columns: **`<property>@<source id>`**, an ordinary column in every
  way, typed as its value, labelled with the source's name (`<label> · <name>` when two values have sources), its `kind` and `date`
  in its hover. A source with no entry for a row is an empty cell. A row's plain §22 cell sits under the source it names, by id or
  by name. These columns are `hidden: true` and `offered: true`: no view shows one unless it names it, and Property visibility and
  the inspector offer it. `el.data` holds them, and every entry still in the nominal's `sources`, the same objects.
- **The formula.** The value itself, `<property>`, is the first non-empty of its source columns, in the list's order: the winner exactly as
  stated, its source's `name` as `source`, the source's `url` / `page` / `date` / `basis` as `sourceUrl` / `sourcePage` / `asOf` /
  `basis` where the entry has none (`resolveCell`). 0 and `false` are values; `""`, `[]`, `{}`, null and absent are not, as Bases' `isEmpty()`.
  So sorting, filtering, the rail, groups, summaries, every view, the peek, Copy and the right-click read it. **Truthful:** nothing
  edits, drops, merges, rounds or averages a stated value. `formula.<property>` is Bases' name for the same column, in any key.
- **A formula in a `.base`,** over any columns, with no `sources` list anywhere: `formulas: {nominal: '[datasheet, citation, measured].filter(!value.isEmpty())[0]'}`,
  a column `formula.nominal` (`properties.formula.nominal.displayName` labels it). The second spelling, `.filter(value.isType("boolean") ||
  !value.isEmpty())[0]`, is the one to write when a boolean may be among the values: Obsidian errors on the first there. Names read as in
  a filter: `x`, `note.x`, `note["nominal@bench"]`. `parseCoalesce` reads these two and nothing else; WHY: Bases has no coalesce, a
  name of ours is an error in Obsidian, and formulas run for display columns only. Any other formula is a column that draws "—" and says
  it needs Obsidian. A `kpi` naming `formula.*` draws no number: a headline stays the producer's. Written on a value with `sources`
  (`formulas: {nominal: '[note["nominal@chat"], …]…'}`), the file states its default order. In Obsidian (1.12.7, run): the formula runs over
  the notes' properties; `data:`, `sourceColumn` and `<p>@*` are ignored, and a column no note has is empty.
- **The list and the columns.** One list, `order`, the sources best first. The default is the ladder's (`ladderOrder`: by `rung`, a tie in
  declaration order, off the ladder last); a file's formula states it, else the first view that names two sources, left to right;
  either way a source neither names keeps its ladder place. **A view gives the slots, the list fills them** (`slotOrder`), so
  the left-most of a value's columns is always the winner. **A reorder of the same columns moves the list** (`orderAfter`), through the
  one way a view changes: the header drag, Alt+← / Alt+→ on a header, Property visibility's ↑ ↓, `setView`. **A hide or a show is no
  reorder, and a hidden source keeps its place** (`inPlace`), so hiding changes no value; shown again it goes back beside the others (`placeShown`). Two formulas may read one column in opposite
  orders: each reads its own list until a reader moves one (`formulaView`), the column drawing in the first's place.
- **`<property>@*`** in `order` is every source of it, in the list's order: how one `.base` names the sources of a thousand parts.
- **`<property>@source`**, an ordinary column ("`<label> source`", `display: source`): the source that won, a link (`a.dv-src-link`) when its
  address is a link target (§22), else a plain label (`.dv-src-label`); a derived value says so (below). It is what a table
  draws after the value in **a view that names the value and no column of it**, the alias an existing `.base` needs; a view with `sourceColumn:
  false`, which a reader's hide writes, does not get it. A view may name it anywhere. It sorts and filters by name.
- **The Sources view.** A file that names no source column, and no view called Sources, gets one after its own: its first table with the
  value in it, each `<property>@source` given up for `<property>@*`. It is a view: a tab, `el.selectView('Sources')`, `el.presets`.
- **The pill** (a cell of the formula, `td[data-col="<property>"] button.dv-src-dd`, `data-conflict` when they disagree): "+3 · 2 differ", "+2
  agree", on a value two or more sources state, whichever columns are shown; `agreement(cell, view, id)` is its pure half. It opens the
  value's sources, the menu below. A row chosen by hand has `.dv-src-pin` beside it. The side peek and the record say the same words,
  `.dv-src-note`. A formula's cell draws no basis mark (`valueHtml(…, {mark: false})`), its source being named beside it; the hover
  and the menu keep the basis. A source column's cell is a one-source cell and has §22's mark. A table holds a formula's cell whole: its
  floor is the widest value and pill.
- **A cell of a column a formula reads** has `data-src-state="shown | differs | agrees | none"` (`data-override` on a row's pick) and an
  `aria-description` saying so: outlined when taken, tinted with `--dv-tone-warn-tint` when it differs (a host sets `--data-warn-tint`),
  over the row's own fill. Derived from the columns, in every view of them.
- **A row's pick:** `ov: {<row id>: <source id>}`, the row's own head of the list, this reader's and not data. The pick wins when its source
  states the cell. **conflict:** the stated values differ, by value and unit (as JSON: a list element by element, a number never
  its text; no unit conversion). A difference of `text` alone is not a conflict. Independent of the order.
- **State:** `{order, ov}` per `<data-views>` (every view of it reads the same nominal). In the hash (§31's readable way):
  `sources=<id>,<id>` when the order is not the default, `picks=<row>:<source>,…` (each part URI-encoded). Per viewer: localStorage
  `data-ui/sources/<page path>/<data id>` (try/catch), removed when the state is the default. Read in that order: the URL (when it
  names either key), the storage, the default. A `no-url` element keeps storage only. hashchange re-applies what the fragment names.
  With `el.persistView`, a moved list is written into the file's formula, its spelling and every other line kept, and is then the default.
- **The element:** `el.precedence` → `{order, default, ov, ids, sources, ladder, properties}` (copies) or `null`; setting
  it, or **`el.setPrecedence({order?, ov?})`**: `order` replaces the order (`null`: the default), `ov` merges one row's
  pick (a `null` source removes it; `ov: null` removes every pick). Event **`data-views-precedence`** `{order, default, ov, changed,
  held}` (`changed`: the row ids whose shown value changed; `held`: those an override kept from changing).
- **The host and the view:** `host.sourcesMenu(pill)`; `host.setPrecedence(patch)`; `input.precedence` = `null` or `{order, default, ov, ids,
  sources, ladder, properties, members, lists}` (`properties`: the formulas; `members`: `{<column id>: {formula, source}}`).
- **The status line:** "Precedence changed from default · Reset" (`[data-sources-reset]`), "N chosen by hand · Clear"
  (`[data-sources-clear]`), and what the last change did ("4 values changed · 1 kept by its override").
- **Editing** (§40). An edit of a source's column lands on that source's statement, and the host hears the stored property, whole: `set:
  {nominal: {sources: […]}}`, so `acceptEdit`, undo and the event see the cell the file holds (`foldEdit`, `setSourceValue`). The entry's old
  `text` goes, and everything else it says stays. A source with no entry gains one, last. Cleared, it states nothing and the next source
  is nominal. A plain cell in the column of the source it names is that cell; in another source's it stays, a statement of its own. A
  pasted block lands column by column. A formula's cell refuses, with its reason; a plain cell in its column stays a plain cell.
- **Exported** from `@data-ui/core`: `isMultiSource, entryOf, stated, conflict, differs, byPrecedence, pick, agreement, changed, held, inPlace,
  ladderOrder, sourceIds, fieldsOf, normalizeOrder, normalizePicks, entryCell, resolveCell, resolveDataset, precedenceOf, unfoldDataset,
  columnId, formulaView, slotOrder, orderAfter, placeShown, ownColumns, sourcesView, setSourceValue, foldEdit, encodeOrder, decodeOrder, encodePicks,
  decodePicks`, `grammar.parseCoalesce`, `grammar.coalesceText`, and `openItemMenu` (an item may be a `menuitemradio` with `checked` and `html`;
  `opts.title`, `opts.label`).
- **The source popover:** a right-click on a value two or more sources state, its pill, or the ContextMenu key / Shift+F10 on its focused
  row, card or field, opens its item menu (the §34 item menu, `openItemMenu`; no second menu system) listing every source. In the table, the
  cards, the record page and the side peek; other views keep §22's popover. A touch long-press reaches it through `sources.js`, which
  hands it over as a `contextmenu` (iOS fires none); Shift + right-click is the browser's menu. A cell of a source's own column is a
  one-source cell, and keeps §22's popover.
  - **The mark:** a view writes `format.js sourcesAttr(cell, rowId, property, {focusable?})` on the element that draws
    such a value: ` data-src-row data-src-p` (the table's `td`, the card's `.dv-cards-prop`, the record's and the peek's
    field `tr`, those two with `tabindex="0"`: the menu key needs a tab stop). '' for a value with one source or none
    and for every plain cell, whose markup is unchanged. `sources.js` leaves a marked element to `<data-views>`.
  - **The menu** (`.dv-itemmenu.dv-src-pop[role=menu]`, `aria-label` "Sources of <row> · <property>", its title "…, N
    sources, in precedence order"): one `button[role=menuitemradio][data-source][data-src-state="shown | differs |
    agrees"]` per source that states the value, in precedence order (`precedence.js sourceRows`, the nominal one
    `aria-checked`), each with its rank, `.dv-src-pop-name`, `.dv-src-pop-rung` (its rung's label on the ladder),
    `.dv-src-pop-val` (the entry's text, else its value, and its unit: the entry's, else the cell's, the row's unit
    column, the column's), `.dv-src-pop-basis[data-basis]`, `.dv-src-pop-asof`, `.dv-src-pop-note`, and a private
    address as plain text (`.dv-src-pop-addr`, §22's link rule). Marks: `.dv-src-pop-nominal` ("nominal") on the row in
    use, `.dv-src-pop-differs` ("differs", the row tinted with `--dv-tone-warn-tint`) on one
    that disagrees, `.dv-src-pin` on a row picked by hand. A source whose address is a link target has its link as a
    menu item of its own right after its row (`a[role=menuitem][data-src-link]`, a new tab, labelled by the address
    without `http(s)://`, a relative one resolved against the data file). `[data-src-back]` "Back to precedence" heads
    it while the row is picked by hand. A value of a row that has another value with several sources says "Picking a
    source applies to every value of <row> it states" (`.dv-itemmenu-note`: `ov` is the row's). The element's own items
    (a peek field's Add to dashboard…) follow, after a `[role=separator]`.
  - **Picking** a row: `el.setPrecedence({ov: {<row>: <source>}})`; the precedence's own source clears the pick (`null`), the row in use
    changes nothing; the focus goes back to the pill, row, card or field. Keys: the arrows, Home and End move through every item (radios
    and links), Enter picks or follows, Space follows a link, Escape closes it and gives the focus back; a `contextmenu` with button 0
    within 300 ms of a menu key's menu is that key's and is swallowed.
  - **Exported:** `sourceRows`, `sourcedProperties`, `sourceColumnOf`, `nominalSource` (`precedence.js`), `sourcesAttr`
    (`format.js`), `sourcesMenu`, `PIN` (`source-popover.js`);
    `openItemMenu` items may also be links (`href`) or `{separator: true}`, and `opts.note` adds a line under the title.
  - [tests/unit/source-popover.test.mjs; tests/browser/source_popover_checks.py on tests/browser/fixtures/source-popover/
    (the source-precedence part.json unchanged, and parts.json: a record per part) against
    tests/browser/source_popover_oracle.mjs (the fixtures' JSON with `pick()` / `conflict()`); light and dark at 1280
    and 390 px]
- **`sourceColumn`** (a key of the runtime shape, §3). **`true`**: every property whose cells name a source (several; or a §22 rich cell with
  `source`, `sourceUrl` or `sourcePage`) has its `<property>@source`, and a table draws it after the view's first such property, else after
  the first property after the title, even when no value has several sources. A one-source cell shows its source under §22's link
  rule; nothing named, "—". There is no precedence then: `el.precedence` stays null, and there is no Sources view. **`false`**: no view gets
  the column unasked, even beside values with several sources; it stays a column a view may name, and the Sources view stays.
  **Undeclared**: the column follows a value with several sources only. WHY declared and not detected: 30 gallery data files carry one §22
  `source` per cell (robotparts-actuators' 1,077 sourced peak torques, the KPI and sim-to-real tables), and detection would grow a column on
  every such table and move the table oracle. [tests/unit/source-column.test.mjs; tests/browser/source_column_checks.py on
  tests/browser/fixtures/source-column/servo.json]
- **A derived value names its source:** data-ui computes no value, so a derived one arrives by its basis (`'derived'`: an entry's own, else
  its declared source's, which `entryCell` fills in), and what it came from is what the cell names. `<property>@source` names it as any
  other (a value with several sources: the picked entry's source; a §22 cell: its `source`, else the address it names, `sourceUrl` then
  `sourcePage`, labelled as `linkCell` labels a link) and adds a quiet `.dv-src-derived` "derived"; "—" stays only where nothing names a
  source. The mark follows the value shown (a pick of a stated source drops it). `precedence.js nominalSource(cell, view, id, info)` →
  `{source, name, address, derived}` or null is the pure half. Not marked: a property declared `derived` (its cells' basis is what marks
  them). [tests/unit/source-derived.test.mjs; tests/browser/source_derived_checks.py on tests/browser/fixtures/source-column/derived.json]
- **Not yet:** a live dataset's multi-source cells (a live snapshot is not unfolded), the row-model worker for data with sources (built on
  the main thread), a pick per value rather than per row (the menu says so).
- [tests/browser/source_columns_checks.py and tests/unit/source-columns.test.mjs, frozen before the code: the oracle reads the fixtures' JSON,
  the left-most rule is read off the page, the formula's truth table is what real Obsidian drew; on tests/browser/fixtures/source-precedence/
  (unchanged) and source-columns/ (robotparts' real JMC datasheet and its own `.base`, and plain columns with a formula); light and dark at 1280
  and 390 px. tools/test_check_source_columns.py for the checkers. tests/browser/source_precedence_checks.py on the same fixture.]

## 37. Amendment 2026-10-30 (the editable sheet: cells, media, the add row, kept view changes; additive)

Zach, 2026-10-30: "lets make this the last time I design a data UI... I am just repating the exact same things Over and over
agian!!!" and "The core underlying model on all of these things in like aunderlying dataset, and then views on that dataset."
So everything a page used to hand-roll a `<table>` for is here. Nothing below changes a page that does not ask for it.

**Editing in place.** On an `editable` page (the attribute), a click on a table cell of an editable property edits it, in an
editor laid over the cell: Enter or leaving it commits through `host.propose({id, set})`, Esc cancels, Tab and Shift+Tab move to
the next editable cell (along the row, then the next rows), F2 on a focused row opens its first one; Shift+Enter is a new line.
A refusal keeps the editor, what was typed and the host's reason. The editor uses `fieldHtml`'s controls (a `<select>` for a
property with `labels` or `constraints.enum`, committing on change; number, date, list); a rich cell keeps its other keys.
- **Not editable:** a `derived` or `readOnly` property (a click opens the record, and `propose` refuses, as before), a `stats`
  part, a pivot, a rolled-up cell, a row with `_readOnly: true`, a view with `edit: true` (its edits are the peek's form) or
  `cellEdit: false`. A click on a link in a cell follows the link; dragging out a text selection does not start an edit.
- **`cycle: true`** on a property with `labels` or `constraints.enum`: a click steps to the next value and proposes it at once,
  no editor (a two-way ±). A boolean flips the same way.
- `tr` carries `data-id` on an editable page; a new row keeps its place by id through any redraw. New data arriving mid-word
  leaves the editor, what is typed and the focus alone (WHY an overlay: rows are rebuilt from strings).

**`display: media`.** A cell of words and any number of images and videos: `{value: "words", attachments: [{url, kind: image |
video, name?, caption?, missing?}]}`. `.value` is what filters, sorts, groups, search and Copy read, as for every rich cell (§2).
Drawn compact: the words as typed, wrapped and never clipped (`white-space: pre-wrap`), small thumbnails under them, and on an
editable cell a quiet "+ image or video" at its bottom right, shown on hover. A view with a media column measures its rows as
`wrap: true` does. A thumbnail opens large: the bubbling, cancelable **`data-views-media`** `{list, index}` first, so a host may use
its own viewer (`preventDefault`), else the kit's `<dialog>`. `missing: true` (or no `url`) reads "N not on this machine yet", never
a broken image. In the side peek the cell draws the same way. Paste, drop or the picker take a file through:

- **`el.acceptFile`**, async `({file, id, property}) => ({ok, attachment, reason})`. **data-ui stores no bytes:** the host stores the
  file and answers with the attachment to name. No hook: no "+ image or video". `id` is null in the add row.

**The add row.** `addRow: true` on a table view, or the `add-row` attribute (the view's key wins): the same cells above the rows
(in the `<thead>`, one `<tr>` kept across redraws, so typing survives them), a box per editable property, the `cycle` value as a
button (first value, or the property's `addDefault`), a column of choices its dropdown, Add under the first locked column; a
property with `addRow: false` has no cell there (what a row gets later, not at birth). Enter walks the boxes and files from
the last one; Shift+Enter is a new line. It files through **`el.acceptAdd`**, async `({set}) => ({ok, id?, reason})`; an `editable` page with no
hook keeps the row in memory; else it refuses. A view reads `host.add(set)`; the element's `addRow(set)` is the same call and
fires `data-views-add {set, result}`. `input` gains `editable`, `addRow`, `canAdd`, `canAttach`; `host` gains `add`, `attach(file,
{id, property})`, `showMedia(list, index)`.

**Kept view changes.** Width, order, sort, grouping, filters and the open view are one state, and each change can be kept three
ways, any together:
- **The URL**, as before (§6). A `no-url` host has no such path.
- **`persist="local"`**: this viewer's storage, under `data-views/<data.id>/state`, read back on load. A kept view applies only
  while the file's entry for it is the one it was changed from; Reset forgets it.
- **`persist="page"`**: the same, with the scope split: the open view, its changes and the filters under `data-views/<page path>/<data.id>/state`, the
  widths under `data-views/<data.id>/widths`, by view name. WHY (robotparts: 2,103 part pages, one data id): `local` opened a preset chosen on one page on the
  next, 0 of its 16 rows, while a column dragged wider is wanted on every page. Reset forgets both. The scope precedence already has (§36).
- **`el.persistView`**, async `({text, name, kind, view, selected, filters}) => ({ok, reason})`, the page's hook: `text` is the
  `.base` file's new text (`el.baseText` with what changed rewritten, its comments and every other view as written; `replaceViewInText`,
  and **`replaceKeyInText(text, key, value)`** for a top-level key), so a host writes one plain file. Changes are batched (200 ms) and
  flushed before a view switch or a removal. With a hook a change is never "dirty": Reset and Save view hide, and Save as new view adds a
  view to the file, not to this browser. A failed write says so in the status line and fires `data-views-persist {name, text, result}`,
  as a good one does.

Two top-level `.base` keys: **`defaultView: <name>`**, the view the page opens on (the order: the URL, a re-start's open view, `persist`'s,
the `view` attribute, this key, the first; the hook writes it, and removes it for the first view). A host that hands in a new
`base` whose `defaultView` changed opens on it. **`sharedColumns: true`**: `order` and `columnSize` written from a table view go to
every table view of the file. WHY: a sheet with eight views is one sheet; a width that resets on each tab is the same work eight times.

A view's `columnSize`, once set, is that width: the table no longer spreads to fill its box (WHY: under `min-width: 100%` a stored
120 drew 240, and a drag moved a column twice as far as the pointer). The first drag freezes every column at the width it draws
now, so only that edge moves.

**`view-counts`** (attribute): each view tab ends in how many rows its filters leave. **`el.peekExtra`**, `(row) => html`: the host's own
controls at the foot of a record's side peek. WHY first-class: reaching into `.dv-peek` breaks the day the kit renames it.

`gallery/examples/feedback-sheet` is the case. [tests/browser/editable_cells_checks.py; tests/unit/replace-key.test.mjs]

## 38. Amendment 2026-10-30 (a record as a page: long properties under the short ones; additive)

Zach, 2026-10-30: "yes you can kinda like open each of thoose rows and look at them individually in detail" and "mabye are best
done with like H1 headers on a page" (Notion's side page). In a real record's side peek, a property that is `display: media` (the
view's or its own) or `long: true` is not a field row: short properties stay rows at the top, and each long one is a full-width
section under them, its name a heading (`h2.dv-page-h`), in `record.sections`' order or the data's. On an `editable` page (and a
property that is not locked, a row not `_readOnly`, a view without `edit: true`) the section is its own editor, shown even when empty,
so there is always somewhere to write: you just type; leaving it, or Cmd/Ctrl+Enter, commits through `propose`; Esc puts back what the
row says; Enter is a new line; a media section takes paste, drop and "+ image or video" through `acceptFile`, and its thumbnails
have × . A read-only page draws the words and thumbnails, and leaves an empty section out. A view with no long property draws exactly as before. A
title in a rich cell reads as its words. On a sheet whose cells take a click, a hover shows a quiet **Open** in the row's first text
column, the way into the record (Notion's OPEN); a click on a locked cell still opens it, Enter on a focused row too.
**`el.refreshPeek()`** draws the open record again with new data, unless something in the peek is being written.
[tests/browser/editable_cells_checks.py]

## 39. Amendment 2026-10-30 (a map that picks: a panel's picks reach its view, a counted marker asks, presets settle; additive)

Zach, 2026-10-30: "I basically want like a list of deployments that I can navigate … one view of that data is the global view
that lets me visualize the data on a map right. So yes I need to be able to like click on this particular robot". The case is
`gallery/examples/robotics-fleet`. Nothing here removes or renames a key, a host call, an input field or a token, and a
view with no `select:` draws and behaves as before. One behaviour widens for a panel that writes `selected:` (below).

What was already true, and stays: a marker's click is `host.open`, and on a dashboard a panel's instance `openPeek` turns any
`host.open` into a selection (§17, §33), so a `select:` on a map panel picked before this amendment, ctrl / cmd included.
A table's pick takes that same path; `host.select` is §15's selection, a different set.

- **`el.picked`** on `<data-views>`: the ids of the rows a host has picked (read and write; a list). A view marks them beside
  §15's selection, and they do nothing else: no bulk bar, no `data-views-select`, not in `el.selection`, nothing narrowed,
  no redraw of a view without `selected(set)`. WHY not `el.select()`: a panel's pick belongs to the dashboard, and a bulk
  bar's Clear there could not clear it. WHY on the element and not sent to the view: a pick outlives a tab switch, and a
  view's bundle may still be loading.
- **`selected(set)`** (optional, §1): the ids to mark changed, the selection and the picks together; repaint, no redraw.
  **`input.selected`** is the same Set for a view drawing from scratch. A `selectable` table and a view without the method
  behave as before.
- **A dashboard hands its picks over** in `_markRows`: a panel holding a `map` or `cards` view gets the row ids its
  selection (or its picker's rail pick) names as `el.picked`, under §33's bound (more than 500 rows is a filter: unmarked).
  A table keeps §33's stylesheet: on a dashboard it is not `selectable`, so its `selected(set)` paints nothing.
- **The map marks them:** `.dv-map-marker.dv-sel`, a ring and not a colour (the colour is the row's), lifted over its
  neighbours; a counted marker when any of its rows is marked. On a view with `select:`, `aria-pressed` says so on every
  marker. With no `select:` a marker carries no new attribute. **Cards** mark them with `.dv-sel`, `selectable` or not.
- **A counted marker asks** when `select:` is set and its rows hold more than one value of that property: `aria-expanded` on
  the marker, and a click opens `.dv-map-choose` (`role=group`), MapLibre's Popup with one `.dv-map-choose-row` per row at
  the point (`data-id`, `aria-pressed`, the row's own marker colour, since a counted marker shows only its most common
  value's). Nothing is picked until a row is. A row goes through `host.open`, so plain, ctrl / cmd and clearing are what they
  are for any click; a plain pick closes the chooser and a ctrl / cmd-click leaves it open. Keyboard: Enter or Space on the
  marker opens it on its first row, ↑ ↓ move, Enter or Space picks, Escape closes it and returns to the marker. A click on the
  map, a redraw or a tab switch closes it. Rows that share one value are one pick: no question. With no `select:` a counted
  marker lists its rows in the peek, as before. WHY not that peek list: it is a read-only table under one arbitrary row's
  fields, across the page from the point.
- **Presets settle.** §33's `selected:` applied when a page opens; it now also applies when a pick or a rail leaves that
  panel's selection naming no row it still draws: in layout order, the panel picks again by its preset, or holds nothing when
  the preset names no row either. model.js exports `settledSelections(dash, data, state)` → the new `select` map;
  `<data-dashboard>` runs it in `select()` and `setRail()` (not for a word typed in a search facet, which is transient and a
  moment later gone), so the robot and its newest run are one pick, one history entry and one URL. A selection that still names a row stays (an added robot leaves the run alone), a panel the reader cleared
  stays cleared, a panel with no `selected:` keeps what it has as before, a picker is its rail's, a per-pick or live dataset
  is left alone (its `.rows` are not what its panel draws), and the URL still wins on a load. WHY: the second robot picked left the first robot's run selected, so no file loaded and the playback said "the
  picks leave no run". `robotics-deployments` never met it: it has one deployment.
- **The clock's keys step aside** on a map's marker and chooser (`_key`), as on a legend entry: Space picks there, and the
  arrows are the map's or the chooser's.
- Not yet: Space on a focused tab or chip still goes to the clock (Enter works on both), and a run picked by mouse keeps
  focus on its row, so Space there unpicks it rather than playing. Both are older than this amendment. `:focus-visible`
  cannot tell the two apart: Chromium turns it on for a mouse-focused element as the key arrives, before any handler runs.
  (The map's legend for `markerColor`, which this list named, came with §42.)
- [tests/browser/fleet_map_checks.py, on gallery/examples/robotics-fleet and tests/browser/fixtures/fleet_map/: a real mouse,
  keyboard and touch at each thing's on-screen position, the runs, files, clock span and plotted points against the case's
  files, Web Mercator worked out in the check; tests/unit/fleet-map.test.mjs (the case's data, settledSelections);
  tests/unit/settled-live.test.mjs; tests/browser/settle_search_checks.py]


## 40. Amendment 2026-10-30 (the notion table: Edit / View, delete, undo, paste, columns; additive)

Zach, 2026-10-30: "We 100% need to add the features where we can actually edit the data ourselves inside data UI, so it becomes even
more like a Notion table. And of course we can support toggling on an edit and view mode if we want." Decisions and criteria:
docs/peps/0016-notion-table.md. **Nothing below changes a page that does not set `edit-toggle`,** with one exception, which fixes a
loss on every page (a value that comes from its sources, below): an `editable` page with no `edit-toggle` draws and behaves exactly as
in §37 (Vibe Tracks depends on that), and a page with neither has no switch.

**`edit-toggle` (attribute).** The toolbar gains a quiet switch, `[data-edit-switch]`, `role="switch"`: in the full toolbar's tools, in
the bar's tools (`data-tool="edit"`, which moves into "…" when the bar is narrow, as a `menuitemcheckbox`). A dashboard panel asks
with `editToggle: true` (its toolbar then defaults to `compact`, so the switch has somewhere to live).
- `edit-toggle="edit"` opens in Edit for a viewer who has not chosen: a page made to be written in, as the `notion-table` gallery case is.
- **View**, where the page opens otherwise: nothing is editable, no add row, no hover affordances. The table's drawn HTML is the HTML of a page
  with neither attribute. `propose`, `addRow`, `deleteRows`, `batch` and `editProperty` refuse, hooks or not.
- **Edit:** §37's `editable` behaviour, with or without the `editable` attribute, plus everything below.
- The choice: `el.editing` (a boolean; setting it is the switch). Read in this order: the URL (`#edit=1`, `#edit=0`; a `no-url` host has
  no such path), this viewer's storage (`data-views/<data.id>/edit`), View. Written to both on every change, and **`data-views-edit-mode`
  `{editing}`** fires. Turning Edit off commits an open cell editor first. `input` gains `editTools` (Edit on an `edit-toggle`
  page: what the table's delete, paste and column menu read) and `viewOnly` (View on an `edit-toggle` page: a form view stands down).

**A value that comes from its sources takes no hand edit** (every page). A value set on a multi-source cell (`isMultiSource`: any
non-empty `sources` list, a list of one included) is refused in `_decide`, on the row as loaded, before any hook runs, in a table
cell, a peek or record form, a page section, a kanban move or a script's `propose`. WHY: the cell is a formula over its sources' columns, so a
`value` set beside them resolves straight back (§36): the reader sees nothing change while a host may save it. An edit of a source's own column
goes through, as the stored property, whole, and so does a whole new `sources` list: that is the data itself (§36, Editing). The refusal takes the existing
path: the editor stays open with what was typed and says "<Label> comes from its sources. Pick a source from its menu, or edit
a source."; Tab does not leave it, and turning Edit off keeps Edit on. A form holding one such field refuses whole. A §22 cell
naming one `source`, a plain rich cell and a plain cell of the same row or column stay editable. **`el.isSourced(id, property)`**,
`host.isSourced`, says which. A paste counts these cells as locked; a `batch` leaves them out and answers `skipped`; an undo or
redo reaching a cell that has come to have sources since leaves it out, counts it in the toast, and takes it off the step, so the key
never sticks on it. A rich cell's edit keeps its other keys, not `text`, which said how the old value was written and would draw over the
new one, nor `sources` (`withValue`). Whether a hand edit should become a top-ranked "hand" source is open (PEP 0016).

**Deleting rows.** **`el.deleteRows(ids)`**, async, `{ok, reason}`; `host.deleteRows(ids)` is the same call. **`el.acceptDelete`**, async
`({ids}) => ({ok, reason})`, decides; an editable page with no hook deletes in memory, as the add row does; else it refuses. A row
with `_readOnly: true` refuses. On `ok` the element drops the rows from the data it holds (a host that hands in new data
replaces them anyway). Fires `data-views-delete {ids, result}`. In Edit: a row's right-click, the ContextMenu key or Shift+F10 (Delete
row, or Delete N rows on a selected row), and Delete in the bulk bar. No confirm dialog: a toast (`.dv-toast`) says what happened
and holds **Undo**, as Notion does.

**Undo and redo.** Ctrl/Cmd+Z and Shift+Ctrl/Cmd+Z, or **`el.undo()`**, **`el.redo()`**, `el.canUndo`, `el.canRedo`: this session's cell
edits, adds, deletes, pastes and column changes on an `edit-toggle` page, in Edit. A key inside an open text editor, the add row, a
page section or a query box is that editor's own. Undo goes through the same hooks with the old values, so the host stays the owner of
the data: an edit through `acceptEdit` with the old cells, an add through `acceptDelete`, a delete through `acceptAdd` with
**`{set, id, restore: true, index}`** (the row's old cells, its id and its place in the data; a host that answers another `id` is followed through the stack).
A host's refusal stays on the stack, the toast says why, and only what the host took moves, so the stack never claims what did not
happen. An undo whose row is gone says so and leaves the stack. An add a host answers with no `id` cannot be undone, and is
not recorded.

**Pasting a block.** With a cell's editor open in Edit, or a row focused, a paste of tab-separated text, or of several lines with an
HTML `<table>` beside them on the clipboard (Excel, Sheets, Notion), fills the cells across and down from that cell (a focused row: its
first editable one). Plain words, multi-line or not, go into the open editor as words. Quoting is RFC 4180's (`parseRecords` in
data.js, the CSV reader's scanner). A value lands by position: a locked cell or a column past the last is skipped, and the toast
says how many. A number that reads as one is a number; anything else is kept as written, as is a value that does not fit its
column. Past the last row the block adds rows only where `canAdd` holds and the view does not say `addRow: false`. One paste is one undo
step.

**`el.acceptBatch`** (the additive extension), async `({edits: [{id, set}], adds: [{set, id?, restore?, index?, at?}], deletes: [id]}) => ({ok,
reason, ids?})`, all or nothing, `ids` the new rows' in `adds` order: a paste, an undo or a redo is then one call. On `ok` the element applies
it to the rows it holds. With no such hook each item goes through `acceptEdit`, `acceptAdd` and `acceptDelete`, and what a host
refuses is reported and left out of the undo step. **`el.batch(plan)`** and `host.batch(plan)` are the same call. An add from a paste
carries `at: 'end'`, and in memory goes after the last row.

**Columns.** In Edit the table's header has a menu: `[data-col-menu]` on hover or focus, a right-click, the ContextMenu key. It holds the
property's name and type, Hide, Delete and Add a property. **`el.editProperty({op, property, …})`**, async `{ok, reason, property?}`,
is the same call; **`el.acceptProperty`** decides; an editable page with no hook does it in memory; on `ok` the element applies
it to what it holds. Fires `data-views-property {op, property, result}`. The ops:

| `op` | Also carries | What it does |
|---|---|---|
| `add` | `label`, `kind`, `definition`, `after` | a new property (its key from the name, `due_date`, unique; a host may answer another `property`) |
| `rename` | `label`, `from` | the display name only (`.base` `properties.<id>.displayName`). Stored keys never change |
| `retype` | `kind`, `definition`, `from` | the property's definition only. **Stored values are never rewritten**; a value that does not fit is drawn as written, and opens in a text box as written, so reading it changes nothing |
| `delete` | | the property and its values. Undoable |
| `restore` | `definition`, `label`, `values: {id: cell}` | how undo of a delete, and redo of an add, comes back |

Kinds: `text`, `number`, `date`, `select` (a badge; free words with the column's values offered, or the data's `enum`), `checkbox`
(`type: boolean`, `display: checkbox`, a real box; a missing value is an empty box), `link`, `media`. **Hide** is a view change, not a data
one: `order`, through `setView`. A `derived` or `readOnly` property cannot be retyped or deleted, and the title property cannot be
deleted. Where `persistView` is set, what the `.base` owns goes through it: the display name (`properties:`, rewritten with
`replaceKeyInText`), `order`, and the view's other keys. Row data and property definitions are the host's (`acceptProperty`).

**Filtering by hand** (in View and Edit, on an `edit-toggle` page). No query to write: a column's control, fitted to its type: a select is a choice
list (the data's `enum` or `labels`, then what the rows hold, so a value typed a moment ago is there), a checkbox Checked or Not checked, a
number or a date a From and To, words a Contains box, and every column has Is empty. Reached from the column's menu ("Filter by this
column"), a header's right-click (in View, the way in that leaves the table's HTML as it is), the toolbar's Filter menu ("Filter by", `[data-filter-by]`, any
column, one added a minute ago included), and a pill, which opens its column's control showing what is set. **It keeps no state:** it reads and
writes the one all-views filter, `el.filters`, in the rail's own forms, so the pills, the query box, the rail and the URL all follow. On an
`edit-toggle` page a pill reads any column in words ("Status: todo, doing", "Owner is empty"). `columnFilter`, `setColumnFilter` and `choicesOf` are the pure half.

**A row edited out of a filter stays where it is** until the view refreshes, as in Notion: a row must not vanish under the hand editing it. A row edited,
added, pasted or restored in Edit is kept, by id (`matchedRows`' `keep`), past the filters and the search. The status line says "1 edited row no longer
matches" and holds **Refresh** (`[data-rows-refresh]`, `el.refreshRows()`). A change of the filter, the search or the view, leaving Edit and a reload
all refresh. Undo that makes it match again takes the note away. `editable` alone keeps §37: the row leaves at once.

**Starting from nothing.** A dataset of no rows and one column opens as a live table, in View and Edit; in Edit it says "No rows yet: type in the row
above.". Rows are typed in, columns of every kind added by hand. A table is never a dead end in Edit: its last visible column cannot be hidden (`A table keeps at
least one column.`), and a table with no column to draw (no properties, or a view whose columns have gone) offers `[data-col-first]`, Add a property;
the first property of a dataset with none becomes its title. A block pasted into the add row's box becomes rows, from that box's column. In Edit a word in a number's add box
stays that word (§37's `Number()` stored `NaN` as null).

In a `selectable` table with no stored widths the last column takes the slack, so the checkbox column stays 32 px however few columns there are.

**`display: checkbox`**, on any boolean. `el.deleteRows`, `el.batch` and `el.editProperty` also work from a script on an `editable` page
with no `edit-toggle`; only the `edit-toggle` page draws their controls and keeps undo.

`gallery/examples/notion-table` is the page to play with, partly filled, with New blank table and Reset to the sample; `tests/browser/fixtures/notion-table/` is what the checks read. [tests/browser/notion_table_checks.py; tests/unit/sheet-paste.test.mjs,
tests/unit/edit-history.test.mjs, tests/unit/sheet-columns.test.mjs]

## 41. Amendment 2026-10-30 (the dashboard editor; additive)

Zach on the babble (2026-10-29): V1 Edit mode and V2 Blueprint "feel quite related", so support both; "Cool idea how you kinda like
queue up these things to be added to the dashboard". One editor (docs/peps/0017-dashboard-editor.md): the dashboard is the canvas,
the outline its tree, one options pane, a short queue. **A `<data-dashboard>` with no `editor` attribute draws exactly as before**
(`tests/browser/fixtures/dash_editor/reading.golden.json`, written from main before this code), Arrange included. As §34: **data-ui
never writes a file.**

- **Opting in.** `<data-dashboard editor>` shows **Edit** (`[data-act=edit]`) in the bar, in place of Arrange. `dist/dashboard-edit.js`
  loads on that press and only then (with `dist/dashboard-arrange.js`: gridstack is one bundle's). A host that vendors the kit
  copies it with the rest. `el.edit()` turns the editor on, `el.edit(false)` off (asking about unsaved edits), `el.editing` says which.
  It needs the file's text, **`el.baseText`**: a dashboard read from `src` has it; a host that calls `load()` itself sets it, or Edit
  is not offered (a parsed document has lost its comments). With `editor`, a reader's kept arrangement (§25) is not drawn, because
  what Edit shows must be what Save writes. `layout.arrange: false` hides Arrange and not Edit: the attribute is the host's word.
- **While editing** the element has `data-editing`, and `data-dashboard-edit` (bubbles, composed; detail `{editing}`) fires on the way
  in and out. Its bar is the status (`.dde-status`, role=status), Undo, Redo, Add ▾ (`[data-act=edit-add]`: a view of a dataset, a
  note), Filters (`[data-act=edit-filters]`, only with a rail), Exit edit, Save. Panels stay live, and a press selects one; a click no
  longer opens the drill peek, and §34's ⋯ steps aside. The filter rail folds away (Filters brings it back, with its handle).
- **The canvas.** gridstack through `arrange.js` `liveGrid`, the one grid path, in its `list` mode: a drag by the panel's top edge
  (`.dde-grip`) reorders the list and the rows reflow under it; the east, south and corner handles resize. After every drop the panels
  stand where the file draws them. An east edge dragged past the grid's right side asks for that width, and the panel lands on the next row.
- **The panes** (`aside.dde-pane[data-dde-pane=outline|options]`, made only by `edit/pane.js`, children of the element, kept
  through a redraw): a boundary (`.dv-splitter`, §11) that drags, a width kept under `data-ui/panel-width/dash-edit-<name>`, a double-click
  that resets, and a fold (`button.dde-fold`, `aria-expanded`; `data-folded`; 28 px; kept under `data-ui/dash-edit/folded/<name>`). Ctrl+B
  folds the outline, Ctrl+Alt+B the options. Under 700 px of the element's own width (`data-dde-narrow`) they stack in the page, folded,
  there is no gridstack, and Move up / Move down reorder. Both are sticky under `--data-sticky-top`.
- **The outline.** `.dde-tree` (role=tree), a `.dde-row[data-key]` per layout entry in the file's order, hidden ones greyed in place
  (`data-hidden`), a panel's tabs as `.dde-row[data-tab]`. Drag a row to reorder; onto another row's middle to make one panel of tabs
  (one dataset, no note, no playback bar); `[data-dde-hide]` and `[data-dde-ungroup]` on a row. Keys: ↑ / ↓ select, Alt+↑ / Alt+↓ move.
- **The options pane.** Exactly one: the selected panel's Title, Show as (`typesFor`: only the types that can draw it; a type with no
  conversion offers itself), Plots, Width, Height, Position, Visible, Duplicate, Remove; a note's text. Each is `[data-dde=…]`.
- **Save.** Save or Ctrl+S turns the options pane into the review: the change in words (`.dde-changes`), the diff with its context
  (`.dde-diff`), a message; a file that changed since Edit is said (`.dde-moved`). Only its own Save fires **`data-dashboard-save`**
  (bubbles, composed, cancelable) on the element, detail `{dashboard: {id, title, url}, text, before, changes, message, asCopy,
  respondWith(promise)}`: §34's rule to the word (one listener calls `respondWith` during dispatch; `{ok: false, reason}` or a rejection is
  shown and the draft stays; `preventDefault()` alone, the host took it over; neither, the clipboard, said). `before` is the text the edits
  started from, for a host that refuses a file that moved. `asCopy` is `{title}` for Save as copy, and the file on screen stays dirty.
  The kit reloads nothing, and a `reload()` while editing keeps the draft. Exit with unsaved edits asks Save, Discard or Cancel.
- **The queue.** An entry of §34's `dashboards()` with **`queue: true`** is the queue: its panels are listed under the tree as "To place"
  (`.dde-queue`, `.dde-q[data-item]`; nothing when empty), and Add to dashboard fills it as any dashboard. A click or Enter places an
  item after the selected panel, else at the bottom; a drag onto a panel's edge places it before or after, onto the grid's gaps at the
  bottom. After the dashboard is saved, placed items leave that file: a second `data-dashboard-save` with `dashboard` that entry, the file
  read again first. Undo and Discard give an item back.
- **Every edit is a text edit** (`packages/dashboard/src/edit/ops.js`, `yaml.js`; pure): an entry that moves keeps its lines and the
  comments right above it; a value that changes touches only its tokens; comments, quotes, spacing, key order, CRLF and an open last line
  stay. A list in flow style is rewritten in block style, §34's exception. Every result reads back.
- **New key** (schemas/view.schema.json; both checkers read it): a layout panel's **`hidden: true`**: it stays in the file in its place,
  with its key, and is not drawn. `readDashboard()` lists it in `hidden`, not `panels`.
- [tests/unit/dash-editor-ops.test.mjs; tests/browser/dash_editor_checks.py on tests/browser/fixtures/dash_editor/: real mouse and
  keyboard, expected text built from the fixture's lines; every pane found on the page, measured with getBoundingClientRect; the keyboard
  alone; light and dark at 1280 and 390 px; the Servo gallery case]

## 42. Amendment 2026-10-28, landed 2026-10-30 (map: layers, analysis, time, space; additive)

The map view grows from markers into an analysis surface. WHY (Zach, daily note 2026-10-28): "build out the map panel
to like show locations, highlight regions and do much more kinda like analysis there", shown as 20 gallery cases on
BAM-shaped public data (`gallery/examples/map-*`). Numbered 42 at landing: drafted as 32 on lane/map, which §32 (3D) took
first; §40 is the notion table's, §41 the dashboard editor's, and §28 stays reserved for lane/types. The decision record is
docs/peps/0011-map-analysis.md. Nothing here changes a host call or a token, and one input field is added
(`dataset.attribution`, §2). A map view with no new key draws as before (Bases' Maps markers), with a scale bar, the credit
open, and a legend when `markerColor` is a property.

- **`layers: [{type, …}]`** on a `type: map` view, drawn bottom to top. Types and their keys
  (schemas/view.schema.json `$defs/mapLayer`, a closed key set: a misspelt key is an error with its line):

  | `type` | Draws | Keys (property-valued ones are checked against the data) |
  |---|---|---|
  | `markers` | Bases' HTML markers (the default with no `layers:`) | |
  | `points` | WebGL circles; clusters; proportional symbols | `color` (property / colour / `var()`), `size {property, max}` (area ∝ value), `cluster: true \| {radius, maxZoom}`, `label`, `radius`, `filter` |
  | `heatmap` | kernel density | `weight`, `radius`, `intensity`, `points` (singles past zoom 13) |
  | `hexbin` | H3 hexagons | `resolution`, `value {property, summary: count\|sum\|mean\|max}`, `classes`, `extrude: true \| {max}` |
  | `regions` | a GeoJSON file joined to rows: choropleth, bivariate, outline or plan | `geometry` (relative to the `.base`), `key` (feature), `join` (row; `id` allowed), `value`, `summary`, `classes {method: quantile\|equal\|jenks\|manual, count, breaks, scheme}`, `bivariate {x, y, count}`, `extrude`, `label` (feature property), `color` (feature property) |
  | `flows` | arcs origin → destination | `from`, `to` (position properties), `width {property, max}` (∝ √value), `color`, `bow` |
  | `lines` | a path property | `path` (a list of positions), `color`, `width`, `dashed` |
  | `rings` | buffers around sites, demand per band | `of` (filter: the sites), `count` (filter: what is counted), `km: [..]` |
  | `catchments` | Voronoi cells of the sites, demand per cell | `of`, `count`, `classes` |
  | `within` | demand within a distance of the nearest site; a slider | `of`, `count`, `km`, `min`, `max`, `step` |
  | `labels` | HTML callouts with a leader line | `text`, `detail` (property or list), `dx`, `dy` (properties), `notes: [{at, text, detail, dx, dy}]` |

  Every layer also takes `title`, `filter` (a Bases expression), `coordinates`, `opacity`, `ink` (series slot 0-7).
- **View keys:** `space: geo | local` (local: positions are `[x, y]` metres, drawn near 0° where a degree is 111,320 m
  both ways, scale bar in metres, no basemap); `time: <property> | {property, trail, speed, zone, format}` (a play and
  scrub bar that filters on the GPU; on a dashboard whose `.base` declares `clock:` it follows that clock, and otherwise
  plays by its own `speed:`, the whole span in 12 s by default. WHY not every clock: core's `clockFor` always answers,
  and an idle clock runs at one second a second, so a day of rows would take a day);
  `multiples: {by, values?, columns?, limit?}` (one map per value, classes shared, one camera); `swipe: {left: {filter,
  label}, right: {filter, label}}` (two maps under a draggable divider, classes and camera shared); `draw: true` with
  `drawBy` / `drawSum` (draw a polygon; the panel counts and sums what is inside and opens those rows); `legend: open |
  closed | off`; `pitch` (tilt for extruded layers).
- **Truthful rendering.** A missing value is never 0: a region, hexagon or row with no value is "no data" (hatched,
  counted on its own legend line). Every legend states its property, its unit and how its classes were cut
  ("quantiles, 5 classes"); a number the map computed (a count per hexagon or catchment, a distance, a length) says
  `~ derived`. A small multiple or swipe side is classed against the same breaks as the rest. Rows without a position
  are counted in the status line with their reason, as before.
- **The legend panel** is the view's own side panel: one answer first ("Highest: Peace River · 763 kg/person/yr"),
  then the legend, layer toggles and the tool's results. It is resizable with core's `makeResizable` (§11; min 200,
  max 520, `data-ui/panel-width/map-panel:<views id>`, double-click resets), folds away (› / Legend), and sits under
  the map below 700 px.
- **Clicks go through the host.** A row opens with `host.open(id)`; a region, hexagon, catchment, cluster member list,
  ring band or drawn area with `host.open(firstId, {records, title})`, so in a dashboard a map with `select: <p>`
  cross-filters every other panel (§17) with no dashboard change. Only the top-most clickable feature under the
  pointer answers a click. A cluster click zooms in. The within slider writes the view's `layers` through
  `host.setView`, so the distance rides in the URL and in Save view.
- **`select:` reaches every clickable layer (§39).** The dashboard's pick is the click above; ctrl / cmd adds and takes out, a
  plain click on the one pick clears. The marks come back through `selected(set)` and `input.selected`, wherever the pick came
  from (a click, the URL, `selected:`, a table tab, `el.picked`), on every small multiple and swipe side that draws the row. A
  feature is marked when any row behind it is picked, as a counted marker is. On a view with `select:`, a click leaves no
  highlight of its own; with no `select:` the clicked region, hexagon or catchment is highlighted, as before.

  | Layer | A click | The mark |
  |---|---|---|
  | `markers` | picks its row; a counted marker asks (§39) | `.dv-sel`, `aria-pressed` |
  | `points`, proportional or not | picks its row | `sel` feature-state: an accent ring |
  | `points` with `cluster` | a cluster zooms in and **never picks**; a single point picks its row | a ring on the layer `<id>-m`, at the row's own point, over the cluster, at every zoom |
  | `heatmap` | the density is **not clickable**; past `pointsFrom` a single point picks its row | the same mark layer, at every zoom |
  | `hexbin`, flat or raised | picks every row in the hexagon | `sel`: the outline, or a raised column's colour |
  | `regions`, choropleth, bivariate, plan or raised | picks every row joined to the region | `sel`: the outline, or a raised region's colour |
  | `catchments` | picks the rows it counts | `sel`: the outline; its site's row marks it too |
  | `flows`, `lines` | picks its row | `sel`: the accent colour |
  | `within` | a dot, demand or site, picks its row | `sel`: an accent ring |
  | `labels` | a callout picks its row | `.dv-sel`, `aria-pressed` |
  | `rings` | the rings are **not clickable**; a band in the legend picks its rows | `.dv-sel`, `aria-pressed` on the band |

  An area picks all its rows: the area is what the reader pointed at, so it asks nothing. **Keyboard:** markers, callouts and
  legend entries are focusable and pick with Enter; a WebGL feature is not focusable (not yet). A drawn area's "Open these
  rows" picks them too, and marks what the map draws of them.
- **A legend for `markerColor`.** A property's colours are explained without a sentence on the page: each value, its colour, its
  count, the rows behind it a click away (`host.open(firstId, {records, title})`), and a note when a counted marker hides a
  value (it takes its most common value's colour). A marker map with nothing to explain has no side panel.
- **The credit.** A data file's `attribution` (`{text, url}`, text, or a list of those) is `input.dataset.attribution`; the map
  draws it in its credit beside the basemap's, with `url` as a link. The credit stays open at every width and after a drag
  (MapLibre's `compact: false`), on small multiples and swipe sides too. A file holding OpenStreetMap data carries
  `{text: "© OpenStreetMap contributors", url: "https://www.openstreetmap.org/copyright"}`: OpenStreetMap must be credited on
  the map itself, whether it draws tiles or rows. Every map case's sources and licences are docs/MAP-DATA.md.
- **Basemap.** The bundled Natural Earth countries stay (never another origin, §1). `mapTiles:` / `mapTilesDark:` name a
  `.pmtiles` file on the same site, relative to the `.base` (the element's `src`, or its dashboard's, else the data
  file's URL): Protomaps' OpenStreetMap layers recoloured from tokens are drawn over the countries, and where the file
  has no tiles the countries still show. It is read by HTTP range, or whole when the server ignores Range.
  `packages/views/map/assets/build_basemap.py` cuts an extract from a Protomaps daily build; labels use Noto Sans
  (OFL) shipped beside the bundle (`dist/views/map-glyphs/`), and a glyph range not shipped answers empty, not 404.
- **Readable from outside:** the view's element carries `data-zoom`, `data-pitch` and `dvMap` (the MapLibre instance;
  for browser checks and hosts that need it; small multiples and the swipe's second map carry `dvMap` on their mount).
- **New npm** (one install, lane/map): `@turf/turf@7.4.0`, `h3-js@4.5.0`, `simple-statistics@7.12.1`,
  `terra-draw@1.37.0`, `terra-draw-maplibre-gl-adapter@1.5.0`, `@protomaps/basemaps@5.7.2`; already installed and now
  used: `pmtiles@4.5.0`, `img-comparison-slider@8.0.7`. The manifest is `split: true`: H3, Terra Draw, the swipe and the
  PMTiles basemap load on first use.
- **No JS:** a case page shows the capture of its first view (site/build-site.mjs `noscript()`) above its `.base`
  and data.
- [tests/unit/map.test.mjs (14, hand oracles; 3 mutations caught); the 20 `gallery/examples/map-*/checks.py` with
  tests/browser/map_helpers.py (oracles: haversine on Turf's radius, ray-cast point in polygon); both checkers'
  property walks (`mapNames` / `map_names`); tests/browser/map_select_checks.py and tests/unit/map-select.test.mjs (a real
  mouse per layer, the mark in the feature-state and the pixels, which come back byte for byte); tests/browser/map_credit_checks.py
  and tests/unit/map-data.test.mjs (the credit on screen on every map of OSM data, every data file listed)]

## 43. Amendment 2026-10-28, landed 2026-10-31 (the admin look: summary card, card frame, Search and filter; additive)

Numbered 43 at landing (drafted as 32). New keys, a new element, a new frame, a new `search` value, two rail attributes and a core
export; a page that uses none of them draws as before. WHY (Zach, 2026-10-28, on Tycoon's S6 shell, which copies Shopify admin):
"Can you please rebuild tycoon using data ui? I like the layout of the app … you may need a new summary card for this:
when I look at this I essentially just see a dashboard with 2 primary card elements." The proof is the gallery case
`admin-shopify` (its `app/` page is Tycoon's Organizations and Deals screens, invented data) and its checks.py.

- **`summary:` and `type: summary`.** One rounded card of cells side by side, hairlines between them; each cell a label
  (dotted underline; its `note` is the tooltip shown on hover and keyboard focus), the value, and only when the cell
  has a series, a sparkline and its change against the bucket before. Keys (schemas/view.schema.json `$defs/summary`):
  `summary: {scope: all | filtered, cells: [{label, note?, filters?, when?: {property, is: today | this-week |
  this-month | this-quarter | this-year | past | upcoming}, value?: count | {property, summary}, spark?: {x, grain},
  format?: {digits, compact}}]}`. `value` defaults to the count of the cell's rows; `summary` is any Bases summary or
  alias plus **Earliest / Latest** for a date. Counts are computed from the rows, never stored; a click opens the cell's
  rows in the peek. A bad cell draws "—" and says why (status line, cell title). Code: `packages/views/summary/`
  (`src/model.js` is pure; tests/unit/summary.test.mjs).
  - At the **top level** of a `.base` it configures **`<data-summary for="<views id>">`** (defined by
    `dist/views/summary.js`, as `<data-kpi>` is by kpi.js): the summary card of that element's file, placed by the host
    outside the element (above the table card). It counts the file's rows (`scope: all`, default; the file's own
    `filters:` apply) or the rows the all-views filter leaves (`scope: filtered`); never the search. The open view's own
    `summary:` wins while it is open (as a view's `facets:` wins over the file's). Read-only `cells`; event
    `data-summary-render {cells}`. WHY its own element and not a view in the file: the table card's view chip lists the
    file's views, and the totals are not one of them.
  - On a **view** (`type: summary`), it is a view like any other: a dashboard panel or a tab, counting that view's rows.
- **`frame="card"`** (§12's seventh frame, `FRAMES` in frame.js; View settings › Frame lists it): one card,
  `--data-card-radius` (new host token, default twice `--data-radius`), as tall as its rows up to `--data-height`, the
  bar inside its top, Polaris' table (12 px cell padding, no rule after the frozen column, the primary column semibold,
  one line per row whatever `rowHeight`, `wrap: true` still wraps), Shopify's picker chip (bordered, no layout icon).
  The table's pager floats 12 px under the card, outside it (the card's surface is a `::before` that stops above it).
  CSS only (styles/frame.css); the element never shrinks in a flex column (`flex: none`).
- **`search="expand"`** (§15's `search`, a third value; `src/toolbar/expand.js`): Polaris' IndexFilters. At rest the
  query box is a borderless "Search and filter"; on focus it reads "Searching all <noun>" (attribute `search-noun`, else
  the data's `title`, lower-cased), Cancel takes Display's place, and a row under the bar holds one "+ <label>" chip per
  categorical facet of the file; a chip opens its values with counts under the other filters, and a tick writes the one
  all-views filter (so the rail, the pills, the URL and the query read it). A set chip reads "Kind: Customer ✕". Cancel
  clears the words and those facet filters and folds the box. No hint list opens on focus while the box is empty (it does
  once the reader types or presses ↓). Classes `.dv-search-expand`, `.dv-search-active`, `.dv-qcancel`, `.dv-fchips`,
  `.dv-fchip`, `.dv-fchip-menu`.
- **Table keys and displays:** `display: {p: avatar}` (an initials chip before the semibold name; its colour from the
  view's `avatar: {color: <property>, colors: {value: 0-8}}`, else that column's badge colours, else a stable hue);
  `display: {p: date}` (the core's new export `shortDate(value, now)`: "Today", "Yesterday", "Tomorrow", "Apr 10" in the
  reader's year, "Jul 25, 2023" otherwise; the stored text is the cell's title); `maxBadges: N` (a badge list shows N
  then "+K", every value in the title); `pageSize: N` (a flat table shows N rows a page with Shopify's "‹ 1–14 ›" pager
  under the rows; the page is the reader's place, never written back, and resets on a new view, sort, filter or search;
  a grouped or nested table is not paged).
- **`<data-rail>` (§27):** `data-badge="4"` on a destination (a count at the row's end, wide style; in the accessible
  name) and `data-parent="<id>"` (a sub-destination drawn under its parent without an icon, only while that section is
  open; the open section's parent row keeps the current fill, `.dv-rail-section`; hidden in the two narrow styles and
  skipped by ↑/↓). `destinations` carry `badge` and `parent`.
- **Checkers:** both read the new keys from the schema; `summary` is a known top-level key; `avatar.color` and each
  cell's `filters`, `when.property`, `value.property` and `spark.x` are checked against the data in both (a file
  with one wrong name in each of the four places gets the same 4 errors from each). **Changed ruler:** gallery/examples/toolbar-bar/checks.py's Frame list now
  expects seven frames.
- [tests/unit/summary.test.mjs (8 tests; two mutations of model.js caught); gallery/examples/admin-shopify/checks.py
  (36 checks: the summary against the data files read in Python, hairlines, tooltip, the card and pager measured,
  avatars, +N, dates against Python's own formatter, search="expand" end to end, the view chip, the Deals summary
  against today, the rail's count and subs, a measured sidebar drag, 390 px without sideways scroll, the gallery page)]

## 44. Amendment 2026-10-31 (the inspector: one property per row; additive)

Zach, 2026-10-31: "I don't like how when I look at the inspector menu its not a 1:1 coorespondance with the fields I am seeing",
"Desired is notions: pattern where you have 1 property per cell" and "you have control over what property visibilty in the inspector
or in the row". The why, the criteria and the options are `docs/peps/0019-inspector.md`; the pure half is
`packages/core/src/inspector.js`. A real record, in the side peek and in `type: record`, reads as follows; a pivot row or a group's
records draw as before.

- **The list.** One property per row (`tr[data-p]`, one label, one value): the view's visible columns, in their order, under the
  labels the table gives them (the table's unit stays beside the value), then the rest. The title property is the heading, not a row. No key-spec
  chips and no Specs / Sources tabs (the `.dv-open-chips` of the `expand` band stays). An empty value in a visible column is its row,
  a dash. A property `hidden: true` and a unit column no view draws are not offered, as Property visibility does not offer them.
- **`N more properties`** (`button[data-prop-more]`, `aria-expanded`, "1 more property", once open "Hide N properties"): what is not
  shown, in `.dv-prop-rest`, opened in place with nothing redrawn. It stays open through the records and folds when the peek closes.
- **`record.visibility`**, a view key, `{<property>: show | hideEmpty | hide}`: `show` always, `hideEmpty` only with a value (0, false and a
  `why` count), `hide` behind N more. A property with no word follows its column. So the row (`order`) and the inspector are set
  apart, both ways. Saved in the view like any view key: the URL, Save view, `persist`, `persistView`'s `.base` text. Both checkers
  read it; a key beginning `@` is a pivot's column, which a file may name and the checkers do not look up.
- **The controls.** `button[data-prop-vis]` in a label cell (on hover or focus, always on touch) opens In the inspector (Always show, Hide when
  empty, Always hide) and In the row (Show as a column). View settings' Property visibility has a second select per
  property, `[data-k=inspector]`. Neither shows under `toolbar="none"` or `controls="off"`, nor in a form.
- **`record.sections`** stands as the author's layout and takes the columns' place in the list; `record.visibility` applies inside
  it, and everything it does not list waits behind N more.
- **A form** (`edit: true`) lists every field, columns first: a required input behind a fold could not report itself.
- **A long property** (§38) stays a section of the page with no column, unless the view says `hide`; a long title is a section too.
- **The slot.** `.dv-peek-slot`, under the properties, in both surfaces: the page (§38), every value behind it (`dataset.detail`), the
  records behind it, a folded Sources pane (`details.dv-peek-pane`, the old tab), then `el.peekExtra`'s `.dv-peek-extra`, now also on
  the record view. A host's own pane goes there, through `peekExtra`. The source popover (§36) stays on the field.
- **Add a property** (`button[data-prop-add]`, after N more): only with `el.acceptProperty`, and not in View. It is §40's add, through that hook.
- **A view's columns:** an optional view method **`drawnColumns()`** → `[{id, label}]`, one per property, in drawn order. With none, a
  view's `order` is its columns. `table` reports its leaves, so "Nominal source" and each source's column are rows, with no source code
  in core; a source's column no view shows waits behind N more (`offered`). An open inspector follows a change of them.
- The boundary keeps §12's drag, remembered width and close. [tests/browser/inspector_checks.py; tests/unit/inspector.test.mjs]

## 45. Amendment 2026-10-31 (column resize, nested groups; additive)

PEP 0020 has the why. Existing views and files mean what they meant.

**Resize, on every table and pivot.** Every leaf header, a source's column included, has a
`.dv-resize` handle. A drag sets that column's width in the view's `columnSize` under the column's id;
a press that does not move writes nothing, and the drag never sorts or moves precedence. The minimum is what the column holds, never its header's words (`minWidth`, CONTRACT §28), `NAME_MIN` for the first column beside checkboxes. Over a handle and through a drag, `.dv-resize-guide` draws the boundary down the table.
A double-click writes the width that fits the column's widest value, over every record up to 2,000 and an even sample past that,
at most 1,600 px. A value cut off by its column shows an ellipsis, and `.dv-cliptip` shows it whole on hover.

**`path` on a group level** (`groupBy`, `subGroupBy`, a `groupings:` entry's levels):

```yaml
groupBy: { property: section, path: dotted }   # servo.pid_position sits inside servo
groupBy: { property: area, path: "/" }         # any other word is the separator
groupBy: { property: trail, path: dotted }     # a list cell is a path as declared, whatever the separator
```

- Levels nest as deep as the rows go; only text is split. A row sits at its whole path, direct rows before child groups; empty
  segments go. A row with no value is in "No <property>" at the top.
- `model.groups` entries gain `path` (their segments) and nest in `groups` to any depth; each `rows` holds everything under it, in
  drawn order, as `model.rows` does. A group with child groups and rows of its own lists those first, as `{key: null, rows, direct: true}`.
- Table and list draw every level, each folding on its own; Unfold all and Fold all take them all. Cards draw H1 and H2 with deeper
  levels rolled into H2. Kanban, nav facets, timeline, calendar, KPI and pivot keep whole values (`viewPath()`), and `tree:` wins over `path`.
- `path` beside `by` or `bins` is a checker error. A path view is built by `rowModel()`, never the worker or the fast order.
- The Group menu offers it as Nest, for a level of text or lists. A nested group row's `title` is its whole path.


## 46. Amendment 2026-10-31 (a record's page, laid out apart from the table; notes as rows; additive)

Zach, 2026-10-31: "Important the visibiliy and order of the properties on the page doesn't nessarily need to be the same as on the table! (by default can
be but then you get full control to customize)", "thoose things move around as "blocks" so you cannot mix things together", "Markdown already has this structure though if
you look at the outline view", and, on the same day, replacing a first design of `h1`..`h4` places: "If I saw each column is associated with an H1 then its simpler... and then you see all of the sub headers inside the cell
basically and if you have space even like a preview mabye of the first couple lines or like a media attachments etc." His rule: if you'd sort or filter by it, it's a property; if you'd read it, it's a section. Nothing
below changes a page whose `.base` has no `page:` key and whose data has no `pageBody` property: its record draws as §38 says.

**One column, one H1.** A section property is always an H1, and everything under it, its H2s and H3s included, is that one cell. There is no choice of level. WHY: a level choice made a heading both a column and a place in a hierarchy, and every note then needed a rule for which H2s were columns.

**The page layout: `page:`, a top-level `.base` key.** A list, in page order, one entry per property: `{property, place?, visible?}`.

```yaml
page:
  - { property: status }                       # place: top, the property list
  - { property: copied_from, visible: false }
  - { property: observed, place: section }     # a block on the page, under its H1
  - { property: desired, place: section }
```

`place` is `top` or `section`. **Default follows the table:** a property the key does not name comes after the named ones in the view's `order`, shown when the view
shows it; a `long` or `display: media` one is a section. A section (the data's `section: true`) is always shown: a heading someone typed is words someone means to read. A
property the data lacks stays in the file, untouched. Stored with `replaceKeyInText`, the rest of the file as written. `data-ui check` and the schema know the key.

**The free text: `pageBody: true`** on one property. Always last on the page, under a rule, with no heading and no menu; it is never in `page:`.

**What the page draws.** The title, the property list, the blocks, the free text; comment-free. Each property has a menu (its name; a block's ⋯): Property list, Section,
Move up, Move down, Hide on the page. Hidden ones sit behind "N hidden properties". A block is one `<section>`: words draw as markdown (`markdown(text, {image, breaks})`,
`el.resolveMedia(src, {row, embed})` finding a path, a video drawn as one) and become a plain textarea on a click or Enter; leaving it, or Cmd/Ctrl+Enter, commits through `propose`, Esc
puts it back. In the list a value keeps its typed control. Paste or drop takes a file through `acceptFile`; the answer's `attachment.ref` (else `url`) goes in as `![name](ref)`.
On a grip, or the menu: a drag (real pointer, Escape cancels) or ↑ ↓ moves it among its own kind. A block never lands among rows, so sections cannot be mixed.
⤢ opens the record full-page: `el.pageFull`, `full=1` in the link, Esc or ✕ leaves. §11's panel handle and remembered width are unchanged.

**A place change: `el.acceptPlace`**, async `({property, from, to, dry, text, layout}) => ({ok, changes, total, note?, layoutOnly?, reason?, refused?})`. `text` is the `.base` with the
new layout in it, `layout` the key's value. The menu asks first with `dry: true`, shows `note` ("Observed moves to an H1 section in 14 of 14 files"), and only Apply asks without it. With no hook a place is the layout's alone. A hook
owns the move and the file write together, so a layout never names a place the data has not reached. **`el.previewPlace(id, to)`**, **`el.setPlace(id, to)`**,
**`el.movePage(id, index)`**, **`el.stepPage(id, delta)`**, **`el.showOnPage(id, on)`**. A change that is the layout's alone goes through `persistView` with `kind: 'page'`; with neither hook it lasts this visit. `data-views-place {property, to, result}`.

**A section's table cell is generated: `display: outline` and `display: preview`.** Per column, on the view (`display: { dp: preview }`) or the property. `.value` is the whole text, so sort, filter, group and search read all of it.
- **`outline`**, a section's default: its sub-headings as written, H3 indented under H2, a source's own numbers kept, the way Zach's hand-made FRDPARRC DP cells list their DPs. **A section with no sub-headings falls back to its first lines.**
- **`preview`**: its first lines, whatever it holds.
- **Media:** thumbnails under the words when there is room, else `[image]` or `[video]` where it was.
- **The view's row height decides how much shows:** `short` 1 line, `medium` 3, `tall` 6, `extra` 10, unset 3; thumbnails take two lines' room. A row with section cells is as tall as they draw. What does not fit is counted (`… +4`), and a line too wide ends in an ellipsis: nothing is clipped silently. `sectionCell`, `outlineOf`, `mediaOf` in format.js.
- **An outline cell is derived** (`isDerivedCell`), so outside the `markdown` type it is not edited in place: a click opens that section on the page, in view, with its box open; a paste skips it. A first-lines cell is the value, and takes §37's editor.

**Table first, page later: one piece of information.** Zach, 2026-10-31: "I can also start as a table view... fill it in top level, and then when I need to expand on it more. I basically go to the page view.. its all one linked piece of information! vs a summary and something else".
The cell and the page are the same value. A row in the add row is a new note; typing in an empty section's cell writes that H1 into the file, in the layout's order; a section nobody typed in stays out of the file. An H2 added on the page is inside the one H1, and the cell then draws it as an outline. Only a cell showing a generated outline opens the page to edit.

**Open in Obsidian, and wikilinks.** Zach, 2026-10-31: "I see like being able to do it in the app but I also see like a open in obsidna option". Obsidian gives him wikilinks, voice dictation and his editor for free, so the page only has to get him there; there is no wikilink autocomplete here, on purpose.
- **`el.openElsewhere`**, `(row) => ({label, href}) | null`: the host names another app for a record, `label` its name. Drawn on its page ("Open in Obsidian") and in its row's Open in menu; `null` draws nothing, never a greyed control. A menu item with `app: true` opens in no new tab.
- **`el.resolveLink`**, `(target, {row}) => url | null`. In a block `[[note]]`, `[[note|alias]]` and `[[note#heading]]` render as links (`markdown(text, {wikilink})`); `![[image.png]]` draws the picture. With no url, a target that is a row's title opens that row here, and anything else stays its words. In backticks they are words. The text is never rewritten: a section keeps every form byte for byte.

**The `markdown` property type.** Zach, 2026-10-31: "in data-ui. we have an option that basically converts the H1s into columns and then summarises there contents inside. I call it a markdown property type"; "instead of rendering the embded media and files as large... render them as smaller but when you click it and edit it raw I think you can like see the raw contents inside".
- `type: markdown` (a `.base` property, or `kind: markdown` in the data; stored as text). The value is raw markdown. Its cell is a summary, `display: outline` by default, `summary: preview` for first lines, drawn as above: small thumbnails for `![](x)` and `![[x]]`, or `[image]` where there is no room. A click edits that section's raw text, `##` marks and embeds as written, in **the Sheet**: a side panel on the right that follows the cell you are on. Clicking a cell in another row (or another section column) moves the panel to it without closing; what is typed saves by itself 0.7 s after the last key, on leaving the panel and on Cmd/Ctrl+Enter, so there is no save step (Enter is a newline; Esc saves and closes). The panel's left edge drags, its width is remembered (`data-ui/panel-width/cell-sheet:<id>`, double-click resets), and the table gives up that width, so the cell being edited is never behind it. Zach, 2026-10-31: "Ok go ahead with Sheet it shall work for now!" **Autosave is safe**: a save names one property, so it touches that section's bytes alone; and the panel keeps the text it loaded, so when the row holds anything else (a change made elsewhere) it does not save over it: it says so, keeps what was typed, and offers *Use theirs* or *Keep mine*; a host's own refusal (`acceptEdit` answering `{ok: false, reason}`) is shown the same way, in the host's words. A clean panel follows a change made elsewhere. The previous way, the row growing to hold a box in the cell, stays as an option: `el.cellSurface = 'grow'` or the attribute `cell-surface="grow"`. A file pasted or dropped there goes through `acceptFile` and lands in the text at the caret, as the answer's `attachment.embed` says. Zach, 2026-10-31: "that is the goal as well for the actual one to be two ways". A save names one property, so it touches that section's bytes alone (a markdown cell is the exception to "an outline cell is not edited in place").
- **`el.cellSurface`**, how a markdown cell is edited, one swappable piece (`cell-surface.js`): absent or `'sheet'` is the Sheet (`cell-sheet.js`, above); `'grow'` (or the attribute `cell-surface="grow"`) is `growInPlace`, the row growing to hold the box; or a function `({cell, form, box, row, property, measure}) => ({fit(), close()})` for a host's own, which gets the in-cell form: the editor keeps its commit, cancel and files, `fit` runs on opening, on each keystroke and after each redraw of the rows. WHY a hook: how compact-to-edit should look was still being chosen when this was written; the Sheet is the pick (Zach, 2026-10-31).
- **The summary is `section-summary.js`**, pure and with no import, so another host can take that one file.
- **`columns: h1`** on such a property (`headings: [Observed, Desired, Why]` to list some first and keep them when a row lacks one): the note stays one value and each H1 in it is a column of `kind: markdown`, named from its words. `h1Sections`, `setH1`, `expandH1`, `liftH1` in `markdown-columns.js`, pure. An edit of such a cell reaches `acceptEdit` as the one property with that section spliced in; every other byte stays. A heading matching a property the data already has is `<property>_<heading>`, so nothing is overwritten.

**`defaultSort`** on a dataset, `[{property, direction}]`: the order of a view that names no sort it can follow. WHY on the data: a folder of notes reads newest first until someone says otherwise, and a view whose sort names a property that went away falls back to it rather than to file order. `tools/serve-md.mjs` sets it from the first of `added`, `created`, `date_created`, `date`, `filed` a folder holds.

**Open in.** On a table whose host set `el.openElsewhere` or `el.pageRenderer`, a right-click anywhere on a row, or its menu key: the item menu (§34) with **Open in ›**, Notion's shape, then what else the row has (Delete row in Edit). With neither hook the menu is what it was. Its submenu lists **Side peek**, and the app `el.openElsewhere` names, so `label` is the app's name ("Obsidian"). No such app: Side peek alone, never a greyed item. A box being typed in keeps the browser's menu. An item menu's item with `items: [...]` holds a submenu: it opens on hover, click, Enter or →; ← or Escape comes back to its item; in a phone's sheet it opens under its item. Later items go in the same list; nothing is listed before it works.

**`el.pageRenderer`**, `(host, {row, id, close}) => ({update?(row), destroy?()}) | void`: a host draws a record's page itself, in the side panel, in its own style (Vibe Tracks: its Obsidian-parity viewer). The panel, its handle, its remembered width, ‹ › and ✕ stay the kit's; the panel's title moves to the host (`.dv-peek-hosted`, still read by a screen reader). The one `host` element is kept across the panel's redraws of a record, `update(row)` says the row changed, and a redraw never takes the focus from an `[contenteditable]` in it; `destroy()` when the panel closes or moves to another record.

**A type that does not fit a section.** A number, a date, a checkbox, a select (`enum` or `labels`, or `display: badge`), a list and a link stay typed. Choosing Section for one is allowed and says so:
the preview reads "Status is a select: you sort and filter by it, so its value stays in the frontmatter of every file. The page draws it as a section; 0 files change." The block is its heading and its typed
control, no place to write, and sort and filter keep working. WHY not refuse: a date under a heading is a fair way to lay out a page, and refusing costs him the layout to protect the data. WHY not move
it: a heading's body is free text, and one typed "about 12" turns a number column into words, or a hand edit into a silent loss of type. A heading typed by hand into a note is words, whatever it says: `# Cost` over `12` reads as text.

**Block order is the layout's, and rewrites no file.** Reordering blocks changes the `.base` alone. Defended: (1) the page order is a view of the notes and the separation is the point: a person's note keeps the order they wrote it in;
(2) a view preference must not make an N-file diff, a sync of every note and a conflict with whoever has one open, when one line in one file says it; (3) rows need not agree, since notes hold different headings in different orders, and the layout gives them
one order without touching any; (4) undo is one line. The cost, stated: Obsidian's outline keeps showing the file's order. A section written new goes where the layout says, so a new note reads in page order.

### The first backend: one row = one `.md` file

`tools/serve-md.mjs <folder> [<folder> ...] [--port N] [--vault <name> --vault-root <path>]` (`tools/md-notes.mjs` the format, pure; `tools/md-page/` the page's hooks). data-ui stays storage-blind: the kit reads a dataset, and calls `acceptEdit`, `acceptAdd`, `acceptFile`, `acceptPlace` and `persistView`. Not implemented: delete, renaming a note, adding a property from the page. Deliberately: a name is a file name, and Obsidian's rename keeps the links to it right.

- **A row** is a file, its id the path without `.md`, its title the file's name (read-only). `README.md`, `attachments/` and dot folders are not rows.
- **Frontmatter** is short properties. **Each H1 is a section property**, its body the cell's value (any markdown). **What comes before the first H1, an H2 included, is `page`**, the free text. Any H1 found is a column, offered in the Properties menu, with no declaring; `.base` `properties.<id>` adds `displayName`, `type`, `enum`, `display`.
- Fenced code holds no headings. ATX only: a setext heading stays words.
- A heading twice is `x` and `x_2`, and a heading with a frontmatter key's name likewise: nothing is dropped. The ids `id`, `name` and `page` are the row's own, so such a key is `note_id`, `note_name`, `note_page`.
- **Every edit is a splice.** Bytes not edited stay: unknown keys, unknown headings, comments, blank lines, CRLF, a BOM, quoting. A value set to itself writes nothing. YAML beyond `base.js`'s subset reads as its text and refuses a write. A `# ` line typed into a section is a new section: that is what the file now says.
- **A move** splices too, and each file's result is read back before anything is written: every other value must read the same, or the whole move is refused and names the file (a value holding an H1 would split). An H2 inside moves with it. A frontmatter key's name and a heading's words carry across (with a `displayName`, the id and the name). A value that has more than one line goes in a `|-` block. `|` with a trailing line end loses that line end in a heading.
- **Writes:** temp file and rename, so a reader never sees half a file. A write re-reads the file first, so a hand edit a moment ago survives, and an edit whose value changed on disk since the page read it is refused.
- **Safety:** binds 127.0.0.1; answers only its own Host; takes a POST only from its own `Origin`, as JSON or octets; refuses `..`, dot segments and symlinks that lead out of the folder; serves only media from the folder.
- **A vault:** `--vault` names the Obsidian vault at `--vault-root`. Only a folder inside that root gets `obsidian://open?vault=…&file=…` links, as `openElsewhere` and `resolveLink`; outside it, or with no option, neither.
- **Live:** a watcher per folder, 60 ms debounce, SSE `change`; a slow read every 2 s as a net. A file saved outside, in place or by rename as editors do, reaches the table within a second; measured on the browser check, under 0.2 s. WHY not `recursive: true`: `_watchDirs` in tools/serve-md.mjs.

`gallery/md-pages` is the case: real rows, so not on the site or in the public export (its README). [tests/unit/md-notes.test.mjs, tests/unit/serve-md.test.mjs, tests/unit/page-layout.test.mjs, tests/browser/md_pages_checks.py]

### A list cell, and a width kept

A `list` cell opens as one line, `a, b, c`, with the browser's datalist offering what the column holds (its `options`, its `enum`, the values in its rows) for the word being typed. `fieldHtml` never draws a list as a `<select>`: a select holds one value, so choosing in it would replace all of a list's but one. A dragged panel width stays stored when the window cannot hold it: it is drawn smaller and comes back with the room (§11).
