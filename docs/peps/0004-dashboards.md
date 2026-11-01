# PEP 0004: dashboards — many views and KPI cards over linked datasets, from one `.base` file

- **Status:** accepted; landed on main 2026-10-26 (from `lane/dashboards`). The CONTRACT amendment is §17 of
  docs/CONTRACT.md.
- **Asked by:** Zach, 2026-10-26: "One thing I think needs to be improved with data UI is the dashboard building
  capabilities… we have the ability to have a single view of a lot of data with the table, but to make this work for
  Vibe Tracks we may need to extend the functionality a bit. Definitely most of Vibe Tracks is just KPI tracking so
  very easy. You can also build out pages for PID tuning to view the results, our sim-to-real work, trajectory
  tracking… all of these things."
- **Code:** `packages/dashboard/` (`<data-dashboard>`, `dist/dashboard.js`), the six gallery cases
  `vibetracks-dashboard`, `vibetracks-runs`, `vibetracks-track`, `pid-tuning`, `sim-to-real`, `trajectory-tracking`.

## 1. The answer

**A dashboard is a `.base` file with a `layout:`.** Every panel is an ordinary view of that file: a KPI strip, a
chart, a table or a pivot, with every key it already has. Four keys go next to `views:`. `datasets:` names more data
files, `links:` says how their rows relate, `layout:` places views and markdown blocks on a 12-column grid, and a
view's `from:` picks its dataset. One more view key, `select:`, makes a click on that view filter every other panel.
`<data-dashboard src="x.base">` draws it. One rail (the file's `facets:`, and each dataset's own) drives every panel.
Clicking a bar, a card or a row cross-filters the rest, and the whole state lives in the URL. A dataset may declare a
`rollup:`, a computed column summed up its own `tree:` (child track → parent).

Obsidian opens the same file and shows the panels as tabs (it keeps the unknown keys; SPEC §5.1). The checker, the
schema, ⋯ Copy as `.base` and every view plugin are reused unchanged. The new code is one element and one pure module,
about 700 lines, with no new dependency.

## 2. What the brief assumes, and where I disagree

| The brief says | What I found | So |
|---|---|---|
| "Most of Vibe Tracks is just KPI tracking, so very easy" | `type: kpi` already draws Vibe Tracks' cards (the vibetracks-kpis case). What was missing is everything *between* views: one filter over several datasets, a click in one view narrowing another, a parent's number computed from its children. | The capability is composition, not another view type. No new layout in the view grammar (SPEC §14, trap 2). |
| "Joins or lookups between datasets" | CONTRACT §10 refused a `.base` join on 2026-10-26: "a column the data needs belongs in the data's producer". | **Links filter; they never add columns.** A link is a semi-join, "show the runs of the tracks that pass the rail", and it reaches the panel as an ordinary Bases filter (`track == "a" \|\| …`), visible in that panel's Filter menu. A producer still writes every column a view draws. The one computed exception is the roll-up, which is labelled derived (§5.4). |
| "A `.dashboard` file, or `layout:` inside a .base" | Scored below (§3). A separate file needs a second grammar and still has to point at `.base` files for every view. | `layout:` inside the `.base`. |
| "gridstack, react-grid-layout" | Both exist to let a *reader* drag and resize panels. Here the file is the editor (the agent writes it), and react-grid-layout fails the no-React hosts (SPEC C2). | CSS grid alone: 0 bytes. Drag-to-arrange is in the gap list, with gridstack (MIT, framework-free) the part to take if Zach wants it. |
| Prior art: Evidence, Observable Framework | Both were ruled out as *products* on Sep 30 (Evidence now needs a live database; Framework gets no new features; vault: Personal KPI Dashboard landscape). Their *ideas* are the best fit: a dashboard is a text file, and components are placed in reading order. | Take the ideas (file-first, reading-order layout, BigValue), not the products. |

## 3. Criteria, then options

| # | Criterion | Weight | Why |
|---|---|---|---|
| D1 | Learn once: a panel is a view, with no second grammar | 25 | "a set number of things I can learn and then reuse" (SPEC C1) |
| D2 | Covers the asks: shared rail, cross-filter, links, roll-ups, markdown, per-panel presets, URL state | 20 | the brief |
| D3 | Agent-writable and checkable: one file, a schema, line-numbered errors | 15 | SPEC C4, "bring your own agent" |
| D4 | Runs in every host: static Python pages, vanilla, React, Obsidian degrades gracefully | 15 | SPEC C2 |
| D5 | Stock parts, smallest glue | 10 | about-me: off-the-shelf first |
| D6 | Phone: reflows to one column, no sideways scroll | 10 | SPEC C7 |
| D7 | Truthful: derived numbers say so, a link never invents a value | 5 | SPEC C6 |

Scores 1-5, weighted to 100:

| Option | D1 25 | D2 20 | D3 15 | D4 15 | D5 10 | D6 10 | D7 5 | Total |
|---|---|---|---|---|---|---|---|---|
| **A. `layout:` + `datasets:` + `links:` inside the `.base`** | 5 | 4 | 5 | 5 | 5 | 5 | 5 | **96** |
| B. a `.dashboard` YAML that places several `.base` files (Grafana JSON, W&B reports) | 3 | 4 | 3 | 3 | 4 | 5 | 4 | 68 |
| C. a markdown page with ` ```base ` fences and frontmatter (Evidence, Observable, Quarto, Obsidian's embedded bases) | 3 | 3 | 3 | 4 | 3 | 4 | 4 | 66 |
| D. hand-placed `<data-views>` in host HTML plus page JS (Streamlit's model, today's status quo) | 2 | 2 | 1 | 4 | 4 | 3 | 3 | 49 |

Why A wins: each panel *is* a `views:` entry, so the checker, schema, menus and ⋯ Copy as `.base` work on it already. A
whole dashboard is one file an agent edits. Obsidian still opens it (as tabs). C is the close second: it is how
Obsidian embeds bases in notes, and it is better at long prose. It loses because a grid, a shared rail and the links
would need a frontmatter grammar of their own, and markdown parsing would be a new dependency. A `text:` panel covers
the prose a dashboard needs, and an Obsidian note can embed the dashboard's `.base` with `![[x.base]]`.

### The prior art, and what each one contributes

| Tool | How it composes many views | Taken | Not taken |
|---|---|---|---|
| Grafana dashboards ([docs](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/), [variables](https://grafana.com/docs/grafana/latest/dashboards/variables/)) | a JSON `panels[]` with `gridPos {x,y,w,h}` on 24 columns; dashboard *variables* feed every panel's query | panels placed on a column grid with `w`/`h`; a variable is a rail facet (`as: select`) | absolute x/y (reading order is enough); its query languages |
| Weights & Biases panels and reports ([docs](https://docs.wandb.ai/guides/app/features/panels/)) | panel sections over the runs table; one run set (filter) drives every panel in a section | **one filtered run set drives every panel** | workspace drag-arrange |
| Observable Framework ([docs](https://observablehq.com/framework/)) | markdown pages, a `grid grid-cols-4` class and `card` divs; data loaders | reading-order layout; `w` = column span | a JS page runtime |
| Evidence.dev ([docs](https://docs.evidence.dev/core-concepts/)) | markdown + SQL; `<Grid cols>`; BigValue; inputs filter queries | BigValue (already `type: kpi`); inputs = the rail | SQL in the page; DuckDB-wasm (SPEC §4.4) |
| Notion dashboards / linked databases ([docs](https://www.notion.com/help/guides/using-linked-databases)) | a page holding several linked views of one database, each with its own filter | per-panel presets (a panel lists several views, shown as tabs) | page-builder editing |
| Obsidian Bases embedded in notes ([docs](https://obsidian.md/help/bases/create-base)) | ` ```base ` blocks and `![[x.base#View]]` in a note | the file stays a Bases file | nothing: it is option C's host |
| Metabase ([cross-filtering](https://www.metabase.com/docs/latest/dashboards/interactive#cross-filtering)), Superset ([cross-filtering](https://superset.apache.org/docs/using-superset/exploring-data/#cross-filtering)) | dashboard filters mapped to each card's column; clicking a bar sets a filter on the others; the emitting chart is not filtered by itself | **`select:` cross-filters; the emitting panel ignores its own selection** (Superset's rule); chips above the grid show and clear each one | the server, the per-card filter-to-column wiring UI |
| Mosaic / vgplot ([docs](https://idl.uw.edu/mosaic/)) | crossfilter selections shared by many views, resolved per client, excluding the source | the same rule, on plain arrays | DuckDB |
| Streamlit ([layouts](https://docs.streamlit.io/develop/api-reference/layout)) | `st.columns` in script order | reading-order rows | a Python server and reruns |

## 4. The grammar

```yaml
data: tracks.json                 # the default dataset (unchanged)
facets: [area, health, state]     # its rail (unchanged)
datasets:                         # more data, by name; an entry whose data: is the default's file describes the default
  tracks:
    data: tracks.json
    tree: { parent: parent }      # the hierarchy roll-ups climb (the table's own tree: key)
    rollup:                       # computed columns: a summary of another dataset's rows, through the tree
      from: runs                  # needs a link runs.<col> → tracks.<key>
      latest: { by: t, per: suite }   # optional: only the newest row per (track, suite)
      values:
        checks_passed: { property: passed, summary: Sum }
        pass_rate: { property: passed, summary: Ratio, per: checks }
  runs:
    data: runs.json
    facets: [kind, { property: t, as: date }]   # this dataset's part of the rail
links:                            # how rows relate (many-to-one); a filter on either side narrows the other
  - { from: runs.track, to: tracks.id }
layout:
  columns: 12                     # default 12; one column under 900 px
  rowHeight: 110                  # px per h unit (default 110)
  panels:                         # reading order
    - { text: "## Every track\nComputed from …", w: 12 }
    - { view: Headlines, w: 12, h: 3 }
    - { view: Tracks, w: 7, h: 5 }
    - { view: Runs by track, w: 5, h: 5, title: Check runs }
    - { views: [Latest runs, Pass rate pivot], w: 12, h: 5 }    # per-panel presets: tabs inside the panel
views:
  - { type: kpi, name: Headlines, from: kpis, select: track, … }
  - { type: chart, name: Runs by track, from: runs, select: track, chart: { … } }
```

- **`datasets.<name>`:** a path (relative to the `.base`), or `{data, facets, filters, tree, rollup}`. The default
  dataset is named by its `datasets` entry when one names the same file, else by its file stem (`tracks.json` → `tracks`).
- **`links`:** `{from: <dataset>.<property>, to: <dataset>.<property>}`. Links are undirected for filtering and may
  chain (`kpis → tracks → runs`). A list cell links each value (`.contains`).
- **`view.from`:** the view's dataset (default: the default dataset). **`view.select: <property>`:** a click on that
  view (a mark, a card, a row, a pivot cell) selects the clicked rows' values of that property. It toggles: clicking
  the same thing again clears it.
- **`layout.panels[]`:** `{view: <name>}` or `{views: [<names>]}` or `{text: <markdown>}`, each with `w` (columns,
  default 12), `h` (row units, default 4; text panels size to their text), `title`, `toolbar: none | compact | full`
  (default: compact, which shows tabs and ⋯; full adds Layout, Group, Sort, Filter, Properties and search).

## 5. Semantics (frozen with the code; each has a check)

1. **The rail.** Each dataset's facets (the top-level `facets:` for the default one) edit that dataset's rail filter
   (its `filters:` to start), with the same kinds, counts and URL form as `<data-facets>` on a `<data-views>`. The
   rail's counts include every other restriction (selections and links), so they say what a tick would leave.
2. **What a panel shows.** For a panel on dataset D: D's rail filter; every selection made on D by *another* panel;
   and for every other dataset S that is restricted, a semi-join through the link path S → D (the keys of S's rows
   passing S's own rail and selections, carried along each link). Datasets with no link path to D never filter it.
   The view's own `filters:` still apply. **The emitting panel ignores its own selection** (Superset, Mosaic), so you
   can click another bar.
3. **Links filter, never add columns.** A semi-join reaches the panel as a Bases filter on the link column, so the
   panel's Filter menu shows exactly why a row is missing.
4. **Roll-ups are derived and say so.** A roll-up cell is `{value, basis: "derived", n, note}`: "Sum of passed over
   14 rows of this track and its 3 child tracks · from rows". It sums the `from` dataset's rows that pass that
   dataset's own rail and selections (so a date range on runs moves it), then optionally only the newest per
   `latest.per`. It never reads the rolled-up dataset's own filters (no cycle). A headline KPI stays the producer's
   number (SPEC §4.4); a roll-up is a view number with its basis shown.
5. **The URL holds the whole state:** each dataset's rail as readable params (the default's unprefixed,
   `?health=green`; others prefixed, `?runs.kind=tests`), custom rail clauses as `#f.<dataset>=`, selections as
   `#s.<panel>=<property>:<v1>,<v2>`, a panel's open tab as `#p.<panel>=<view>`. Reload and back restore it.
6. **Drill-down:** a click on a panel without `select:` opens one side peek for the whole dashboard (PEP 0006's single
   drill container, Notion's side peek), resizable and remembered like every side panel.
7. **The rail is resizable** (`--data-panel-width`, remembered under `data-ui/panel-width/dash-rail:<id>`).

## 6. Consequences

- `dist/dashboard.js` (about 9 KB gzipped) loads only on a page with a dashboard; it imports the page's one core.
- `<data-views>` is unchanged: the dashboard drives it through its public properties (`data`, `base`, `filters`),
  events and an instance-level `openPeek`, so peer lanes' work on the toolbar and open modes passes through.
- The checker knows the new keys: an unknown dataset in `from:`, a link to a missing property and a panel naming a
  missing view are errors with line numbers (tests in tests/unit/dashboard.test.mjs).

## 7. What this does not do (the gap list is in the report)

Time bucketing (week, month) for pivots; overlaying time series from different datasets on one axis; image and
video panels beyond the cards view; live updates (a dashboard re-reads its files on `reload()`, not on a push);
drag-to-arrange panels; text blocks with live numbers in them (Evidence's inline values); pivot `Ratio`.
