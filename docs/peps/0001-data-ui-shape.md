# PEP 0001: the shape of data-ui

- **Status:** accepted, 2026-10-25 (phase 0, the barrier every view lane builds on)
- **Decided by:** Zach (2026-10-25: "data-ui"; "a drop-in shadcn-type thing for my applications"; "for graphs please
  use reactflow"), on docs/SPEC.md (§1, §3, §16) and docs/VIEWS.md (§1-§4)
- **Code:** packages/core/ (the core), packages/views/table/ (the reference view), docs/CONTRACT.md (the frozen API)

## Context

Every app Zach builds views data: robotparts' catalog and datasheets, Vibe Tracks' runs and KPIs, the rack's models
x benches, Money, the atlases. Five partial copies of "data, views on that data, filters on that data" existed
(the table lane's `<data-views>`, robotparts' `site.js`, Vibe Tracks' views and pivot, Clank's `clank.base`, the
survey's KPI kit). Zach: "There's a set number of things I can learn and then reuse for the rest of my days." The
data views live in Python-built static pages and vanilla apps as much as in React, and Zach does not want another
standalone app: "I don't think I'll ever use it as a standalone application."

## Decision

1. **Custom elements, framework-free, light DOM.** `<data-views>`, `<data-facets>`, `<data-value>` (and later
   `<data-kpi>`, `<data-sparkline>`), one `data-` prefix, `--data-*` tokens. They run in a Python-built static page,
   a vanilla app and React 19 alike; light DOM keeps the page's fonts and the server's no-JS `<table>` inside.
2. **Obsidian Bases' grammar is the view grammar.** A page's views are one `.base` file; every Bases file is a
   data-ui file (the vault's 109 parse and check with 0 errors), and Obsidian keeps data-ui's extra keys. One
   grammar for every view, read by one evaluator (`grammar.js`) in the browser, the Node checker and, through the
   stdlib reader `data_ui_base.py`, Python builds.
3. **One row model, many registered views.** filter -> search -> sort -> group -> limit -> pivot runs once, in the
   core, on TanStack Table; a view is a lazy plugin registered by type (Obsidian's `registerBasesView` shape, with a
   lazy `load()`, edits as `host.propose()` proposals, and tokens resolved to colours). The table is one view among
   the rest. Each view's library is chosen in docs/VIEWS.md and loads only when that view opens.
4. **Vega-Lite is the one chart engine.** Inside `chart:` the vocabulary is Vega-Lite's, the grammar agents and
   Altair already write, with a published schema. ECharts stays only inside Vibe Tracks' fixed drill-down. A page
   never loads two chart engines. (React Flow draws graphs, as a React island; that is a graph, not a chart.)
5. **`--data-*` tokens that default to shadcn's names.** A shadcn app needs zero lines; a vanilla app maps one block;
   the kit's own CSS reads private `--dv-*` resolved from the chain, so `--accent`'s two meanings never collide.
6. **Files are the agent interface; there is no AI inside.** The `.base` file, its data and its field schema are
   what Claude Code or Codex edit; `schemas/view.schema.json` and `data-ui check` make that safe (one line per
   mistake, with a suggestion); the page re-renders when the file changes.
7. **Clank and Obsidian are thin hosts, later.** data-ui is neither a Clank plugin nor an app; a Clank viewer and an
   Obsidian Bases view plugin wrap the same elements when they are built. The docs site (landing + gallery of real
   cases) is the kit's docs and its test suite, not a product.
8. **Vendored, never from a CDN.** `npm run build` writes `dist/` with a sha manifest; hosts copy it and re-copy to
   update, and never edit it in place (the drift that froze Clank's copies).

## Consequences

- A new view is a folder (`packages/views/<x>/`) plus a gallery case; four lanes can build in parallel because the
  contract (docs/CONTRACT.md), the dependencies and the schema's keys were frozen first.
- The core bundle carries TanStack Table and Virtual (about 40 KB gzipped); views share them through the core.
- Bases features that need Obsidian (`file.*`, `this`, `link()`, formulas) are warnings in the checker and errors on
  a data-ui page's filter line, not silently dropped.
- Changing the contract, the tokens or the grammar is a barrier: it lands alone, first.

## Alternatives considered

A Clank plugin (53/100), a standalone app (54), a shadcn React registry only (67) and the kit (94): SPEC §16.1.
Chart engines (Vega-Lite 79-89, ECharts 70-80, Plot, Graphic Walker, Perspective): SPEC §8.2, VIEWS.md §5.
Perspective as the whole suite: VIEWS.md §7 (4.3 MB of WebAssembly, "super technical", no cards or board).
