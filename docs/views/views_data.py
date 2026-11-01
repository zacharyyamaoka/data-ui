"""The master table: every view data-ui supports, every library considered for it, the one selected, and why.

One source for docs/VIEWS.md and reports/data-ui-views-2026-10-25.html (docs/views/build.py renders both).
Versions, dates and licences come from docs/views/measurements.json (npm registry, 2026-10-25); sizes are measured
there too (esbuild + gzip -9). Scores 1-5 against CRITERIA; `maint` and `size` are derived from those facts unless a
candidate overrides them. Citations are ⟦key⟧ markers resolved against SOURCES."""

ACCESSED = '2026-10-25'

# key -> (title, url). Order is the Source Index order.
SOURCES = [
    ('zach-1025', 'Zach, 2026-10-25, the brief: "1 dataset, 1 base file, many views" and "for graphs please use reactflow" (relayed by the dispatcher)', None),
    ('lane', 'Table lane report: One table, one grammar for robotparts.dev (TanStack Table v9 + <data-views>, 2026-10-25)', 'file://~/robotparts/reports/robotparts-tables-2026-10-25.html'),
    ('lane-proto', 'Table lane: design/tables-2026-10-25/build_prototypes.py (ACT_COLUMNS: mass factor 1000) on lane/tables @ ab5ba92', 'file://~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25/build_prototypes.py'),
    ('lane-src', 'Table lane source: design/tables-2026-10-25/views/src (views.js, grammar.js) on lane/tables @ ab5ba92', 'file://~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25/views/src/'),
    ('survey', 'Reusable Components Across Zach\'s Apps (2026-10-25), vault note and report', 'obsidian://open?vault=zach_brain&file=Projects%2FBAM%20Robotics%2FNotes%2FReusable%20Components%20Across%20Zach%27s%20Apps%20(2026-10-25)'),
    ('spec', 'data-ui SPEC.md (the SPEC agent\'s, commit a2a0e70): §5.5 seven layouts, §8 chart, §9 KPI, §10 --data-* tokens, §11 first slice', 'file://~/data-ui/docs/SPEC.md'),
    ('spec-schema', 'data-ui schemas/view.schema.json (the SPEC agent\'s, commit a2a0e70)', 'file://~/data-ui/schemas/view.schema.json'),
    ('obs-app', 'Obsidian 1.14.5 app.js (local install, read for the Bases view ids and option keys: table, cards, list, kanban)', 'file://~/.config/obsidian/obsidian-1.14.5.asar'),
    ('obs-dts', 'obsidian.d.ts: registerBasesView, BasesViewRegistration, BasesView, BasesViewConfig, BasesQueryResult (@since 1.10.0)', 'https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts'),
    ('obs-guide', 'Obsidian developer docs: Build a Bases view (obsidian-developer-docs PR #203, merged 2025-10-07)', 'https://github.com/obsidianmd/obsidian-developer-docs/pull/203'),
    ('obs-views', 'Obsidian Help: Bases views (table, list, cards, kanban, map; map "Requires the Maps plugin")', 'https://obsidian.md/help/bases/views'),
    ('obs-syntax', 'Obsidian Help: Bases syntax', 'https://obsidian.md/help/bases/syntax'),
    ('obs-changelog', 'Obsidian changelog: 1.14.0 "a new kanban layout to display files in ordered columns"', 'https://obsidian.md/changelog'),
    ('obs-maps', 'obsidianmd/obsidian-maps: package.json (maplibre-gl 5.24.0) and src/map-view.ts (the map view\'s option keys)', 'https://github.com/obsidianmd/obsidian-maps'),
    ('vault-kanban', 'Research - Bases Kanban prior art (2026-07-17): a custom Bases view gets the result after filters, sort and limit', 'obsidian://open?vault=zach_brain&file=Projects%2FObsidian%20Vibe%20Kanban%2FResearch%20-%20Bases%20Kanban%20prior%20art'),
    ('vault-vl', 'Vega-Lite (SOFTWARE), chosen 2026-10-05 as the chart layer of the BAM model canvas', 'obsidian://open?vault=zach_brain&file=Sources%2FNotes%2FVega-Lite%20(SOFTWARE)'),
    ('vault-canvas', 'Model Canvas Charts — Prior Art and Five Proposals (2026-10-05)', 'obsidian://open?vault=zach_brain&file=Projects%2FBAM%20Robotics%2FNotes%2FModel%20Canvas%20Charts%20%E2%80%94%20Prior%20Art%20and%20Five%20Proposals%20(2026-10-05)'),
    ('vault-rf', 'Block View Canvas Substrate — React Flow vs Excalidraw (2026-07-25)', 'obsidian://open?vault=zach_brain&file=Projects%2Flike%20keras%2FBlock%20View%20Canvas%20Substrate%20%E2%80%94%20React%20Flow%20vs%20Excalidraw%20(2026-07-25)'),
    ('npm', 'npm registry metadata for every package (latest version, publish date, licence, peers), saved in docs/views/measurements.json', 'https://registry.npmjs.org/'),
    ('measure', 'Own measurement: esbuild 0.25.12 bundle of each documented entry, minified, gzip -9, React external (docs/views/measure.py)', 'file://~/data-ui/docs/views/measure.py'),
    ('schema2', 'robotparts SCHEMA2.md §3: levels are "derived, never hand-set"; every actuator is level 1', 'file://~/robotparts/SCHEMA2.md'),
    ('vl-docs', 'Vega-Lite docs: scale (log), mark (boxplot), bin, facet, selection params, legend binding, line (interpolate linear-closed)', 'https://vega.github.io/vega-lite/docs/'),
    ('altair', 'Altair: Chart.to_json() writes a Vega-Lite v6 spec', 'https://altair-viz.github.io/user_guide/saving_charts.html'),
    ('vega-interp', 'vega-interpreter: expressions without eval, for CSP-strict pages', 'https://github.com/vega/vega/tree/main/packages/vega-interpreter'),
    ('echarts6', 'Apache ECharts 6 features: chart.setTheme() dynamic theme switching', 'https://echarts.apache.org/handbook/en/basics/release-note/v6-feature/'),
    ('plot-hull', 'Observable Plot: hull mark ("Draws a convex hull around the points")', 'https://github.com/observablehq/plot/blob/main/docs/marks/delaunay.md'),
    ('uplot', 'uPlot README: 166,650 points in 25 ms; time series, lines, areas, bars; no aggregation', 'https://github.com/leeoniya/uPlot'),
    ('gw', 'Graphic Walker 0.5.3 package: dist/vanilla.d.ts (embedGraphicWalker), interfaces.d.ts (askviz, vlChat), calls to api.kanaries.net/vis/chat', 'https://github.com/Kanaries/graphic-walker'),
    ('tv-lanes', 'TanStack Virtual API: lanes ("The number of lanes the list is divided into")', 'https://tanstack.com/virtual/latest/docs/api/virtualizer'),
    ('fc-pricing', 'FullCalendar pricing: Premium = Timeline View, Vertical Resource View, Printer-friendly rendering; from $480', 'https://fullcalendar.io/pricing'),
    ('sx-premium', 'Schedule-X: drag-and-drop "is a premium plugin which requires an active license"; resize, drag-to-create, resource views also premium', 'https://schedule-x.dev/docs/calendar/plugins/drag-and-drop'),
    ('tui-archived', 'nhn/tui.calendar: repository archived 2026-09-02', 'https://github.com/nhn/tui.calendar'),
    ('ec', 'vkurko/calendar (Event Calendar): standalone @event-calendar/build, resource and timeline views free', 'https://github.com/vkurko/calendar'),
    ('dhtmlx', 'DHTMLX Gantt: Community edition MIT since 10.0 (LICENSE.md in the 10.0.3 package); PRO adds auto-scheduling, resources, critical path, baselines, export', 'https://dhtmlx.com/docs/products/dhtmlxGantt/'),
    ('svar', 'SVAR Gantt pricing: MIT core, PRO from $749/developer (baselines, critical path, auto-scheduling, export)', 'https://svar.dev/react/gantt/pricing/'),
    ('frappe', 'frappe/gantt', 'https://github.com/frappe/gantt'),
    ('vis-timeline', 'visjs/vis-timeline (Apache-2.0 OR MIT; peer dependency on moment)', 'https://github.com/visjs/vis-timeline'),
    ('lightgallery', 'lightGallery licence: GPLv3 or a paid commercial licence', 'https://www.lightgalleryjs.com/license/'),
    ('fancybox', 'Fancybox: free for non-commercial use, paid for commercial use', 'https://fancyapps.com/fancybox/'),
    ('photoswipe', 'dimsemenov/PhotoSwipe', 'https://github.com/dimsemenov/PhotoSwipe'),
    ('grid-lanes', 'display: grid-lanes status (Safari 26.4 only; Chrome, Firefox behind flags) — secondary source', 'https://pawelgrzybek.com/masonry-aka-waterfall-aka-collapse-aka-pack-aka-pinterest-style-layout-display-grid-lanes-cheatsheet-for-my-future-self/'),
    ('pragmatic', 'atlassian/pragmatic-drag-and-drop ("any tech stack"; Apache-2.0 LICENSE.md in the 4.0.0 package)', 'https://github.com/atlassian/pragmatic-drag-and-drop'),
    ('dndkit', 'clauderic/dnd-kit (@dnd-kit/dom 0.5.1, framework-agnostic, pre-1.0)', 'https://github.com/clauderic/dnd-kit'),
    ('kanban-stale', 'asseinfo/react-kanban (archived), rcdexta/react-trello (last push 2024-08), riktar/jkanban (last push 2023-10)', 'https://github.com/asseinfo/react-kanban'),
    ('tremor', 'Tremor: "Tremor is joining Vercel"; paid Premium Blocks; React + Tailwind + Recharts', 'https://www.tremor.so/'),
    ('ag', 'AG Grid licence and pricing: row grouping, pivot, tree data, integrated charts are Enterprise', 'https://www.ag-grid.com/license-pricing/'),
    ('jsonforms', 'JSON Forms renderer sets (React Material, React Vanilla, Angular, Vue): no framework-free renderer', 'https://jsonforms.io/docs/renderer-sets/'),
    ('rf-layout', 'React Flow: Layouting ("We have not implemented our own layouting solution"; dagre recommended for trees; elkjs ~1.4 MB)', 'https://reactflow.dev/learn/layouting/layouting'),
    ('xyflow', 'xyflow monorepo: @xyflow/react, @xyflow/svelte and @xyflow/system ("Shared helper library"); MIT', 'https://github.com/xyflow/xyflow'),
    ('react19', 'React 19: full support for custom elements', 'https://react.dev/blog/2024/12/05/react-19'),
    ('perspective', 'Perspective (now @perspective-dev/*, 5.6.1, Apache-2.0)', 'https://github.com/finos/perspective'),
    ('img-cmp', 'sneas/img-comparison-slider (MIT web component)', 'https://github.com/sneas/img-comparison-slider'),
    ('npm-search', 'npm search "comparison table": only React/Bootstrap one-offs, none maintained and framework-free', 'https://www.npmjs.com/search?q=comparison%20table'),
]

USE_CASES = {
    'rp': 'robotparts catalog',
    'vt': 'Vibe Tracks KPIs + runs',
    'ml': 'ML experiment tracking',
    'rack': 'rack model comparisons',
    'gal': 'galleries',
    'money': 'Money',
    'other': 'other',
}

CRITERIA = [
    # key, label, weight, what a 5 means
    ('fit', 'Does the view\'s job', 20, 'covers every behaviour in the view\'s "what it shows" (a gap we fill in under 100 lines 4; part of the job 2-3; a helper only 1)'),
    ('maint', 'Stock and maintained', 15, 'the lower of stock share (the library does the view, under 50 lines of ours 5; under 150 lines 4; the engine is stock but the surface ours 3; all ours 2) and release age (auto from npm: ≤6 months 5, ≤12 4, ≤24 3, ≤36 2, older or archived 1)'),
    ('licence', 'Licence', 10, 'MIT / BSD / Apache / ISC with nothing we need behind a paid tier (open-core where we would hit the paywall 2-3; GPL, commercial or proprietary 1)'),
    ('fw', 'Framework-free or island-able', 15, 'plain ESM, no framework runtime (a framework compiled inside 4; a React island 2-3; needs a React app 1)'),
    ('rows', 'Reads the shared row model', 10, 'takes our filtered rows as they are (a thin mapping 4; keeps its own data store we sync 3; owns data and query 2)'),
    ('cfg', 'Agent-editable config', 15, 'the whole view is declarative JSON an agent writes into the .base entry (a small option object we map 4; callbacks needed 3; JS calls or its own verbose spec 2)'),
    ('css', 'CSS-variable theming', 5, 'ships CSS custom properties, or is headless so our CSS draws it (a theme object we fill from resolved tokens 3; class-based CSS only 2)'),
    ('size', 'Size (min+gz, lazy per view)', 10, 'auto from the measured bundle: ≤15 KB 5, ≤50 4, ≤120 3, ≤300 2, more 1; already in the shared bundle 5'),
]

# Each view: id, name, type (the .base `type:`), bases (True when Obsidian has the same type), priority,
# what, uses {use-case key: why}, keys (config keys: Bases ones and data-ui ones), selected (candidate id), why,
# ours (lines, honest), ours_note, packages (exact npm pins for the build), candidates [...].
# A candidate: id, name, pkg (npm, for version/date/licence) or None, size (measurement key | number KB | 0 = already
# in the bundle | None = not measured), extra (KB added on top, e.g. React), scores {fw, rows, cfg, css, licence?,
# maint?}, note, flags.

VIEWS = [
    {
        'id': 'table', 'name': 'Table', 'type': 'table', 'bases': True, 'priority': 'now',
        'what': 'Rows × properties in single-line rows under a sticky header: two group levels with fold, multi-sort, filters, '
                'column order, visibility and width, group summaries, a display per column (number, bar, dist, sparkline, badge), '
                'units in the header or inline, and the side peek.',
        'uses': {'rp': 'every category table and the GIM4305-10 datasheet', 'vt': 'runs and the KPI catalogue', 'ml': 'runs × params and metrics',
                 'rack': 'measured vs datasheet, field by field', 'money': 'transactions'},
        'keys': {'bases': ['order', 'sort', 'groupBy', 'groupOrder', 'columnSize', 'rowHeight (short | medium | tall | extra)', 'summaries', 'limit', 'filters'],
                 'ours': ['subGroupBy', 'display', 'units', 'fold', 'tree (see Tree)']},
        'selected': 'tanstack',
        'why': 'Decided and proven by the table lane: a headless engine (grouping, expanding, sorting, column state) under a '
               '1,059-line surface that is ours, 36 KB gzipped in all, 22 of 22 behaviour checks passing.⟦lane⟧ Its row model '
               'is what every other view reads.',
        'ours': 1059, 'built': True, 'ours_note': 'built on lane/tables: views.js 782 + grammar.js 277 lines; ~110 of them move into the shared core',
        'packages': ['@tanstack/table-core', '@tanstack/virtual-core'],
        'candidates': [
            {'id': 'tanstack', 'name': 'TanStack Table v9 + Virtual', 'pkg': '@tanstack/table-core', 'size': 36.0, 'size_note': 'the lane\'s whole views.js, ours included',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 4, 'css': 5}, 'note': 'headless; the lane maps every Bases key onto its state'},
            {'id': 'perspective', 'name': 'Perspective', 'pkg': '@perspective-dev/viewer', 'size': 4270, 'size_note': 'WebAssembly, ~1% smaller gzipped (lane)',
             'scores': {'fw': 4, 'rows': 2, 'cfg': 4, 'css': 3}, 'note': 'everything stock incl. pivot, but a module worker and the UI Zach called "super technical"⟦lane⟧'},
            {'id': 'tabulator', 'name': 'Tabulator', 'pkg': 'tabulator-tables', 'size': 'tabulator',
             'scores': {'fw': 5, 'rows': 4, 'cfg': 3, 'css': 2}, 'note': 'most UI in the box; no pivot; dark mode is a second theme file, not variables (0 custom properties measured)'},
            {'id': 'aggrid', 'name': 'AG Grid Community', 'pkg': 'ag-grid-community', 'size': None,
             'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5, 'licence': 2}, 'flags': ['open-core'], 'note': 'row grouping, pivot and tree data are Enterprise ($999/developer)⟦ag⟧'},
            {'id': 'datatables', 'name': 'DataTables', 'pkg': 'datatables.net', 'size': None,
             'scores': {'fw': 3, 'rows': 4, 'cfg': 3, 'css': 2}, 'note': 'jQuery heritage; RowGroup cannot collapse (lane)⟦lane⟧'},
        ],
    },
    {
        'id': 'pivot', 'name': 'Pivot', 'type': 'pivot', 'bases': False, 'priority': 'now',
        'what': 'Rows grouped by one or two properties, columns split by the values of others, each cell a summary of one value over its '
                'records (number, bar or distribution); a click lists the records behind the cell.',
        'uses': {'rack': 'models × benches, median q RMS (the one Zach keeps rebuilding)', 'ml': 'configs × metrics', 'vt': 'KPI × week',
                 'money': 'category × month', 'rp': 'brand × form counts'},
        'keys': {'bases': ['groupBy', 'order', 'sort', 'filters'], 'ours': ['splitBy', 'value {property, summary, display, per}', 'subGroupBy', 'fold']},
        'selected': 'lane-pivot',
        'why': 'A pivot is a transform before the table, so the same group-by, sort, fold, column menu and drill-down serve both: 70 lines, '
               'no new library.⟦lane⟧',
        'ours': 70, 'built': True, 'ours_note': 'built: grammar.pivot()',
        'packages': ['@tanstack/table-core'],
        'candidates': [
            {'id': 'lane-pivot', 'name': 'grammar.pivot() + TanStack', 'pkg': None, 'ours': True, 'size': 0,
             'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'Perspective\'s split_by vocabulary, Bases\' summaries'},
            {'id': 'perspective', 'name': 'Perspective', 'pkg': '@perspective-dev/viewer', 'size': 4270,
             'scores': {'fw': 4, 'rows': 2, 'cfg': 4, 'css': 3}, 'note': 'native group_by / split_by, million-row speed; same costs as for the table'},
            {'id': 'pivottable', 'name': 'PivotTable.js', 'pkg': 'pivottable', 'size': 'pivottable(+jquery)',
             'scores': {'fw': 3, 'rows': 4, 'cfg': 3, 'css': 2}, 'note': 'jQuery; last release 2018'},
            {'id': 'webdatarocks', 'name': 'WebDataRocks', 'pkg': 'webdatarocks', 'size': None,
             'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 2, 'licence': 1}, 'flags': ['proprietary'], 'note': 'free but proprietary licence; Flexmonster\'s paid sibling'},
            {'id': 'flexmonster', 'name': 'Flexmonster', 'pkg': 'flexmonster', 'size': None,
             'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 2, 'licence': 1}, 'flags': ['commercial'], 'note': 'commercial'},
        ],
    },
    {
        'id': 'list', 'name': 'List', 'type': 'list', 'bases': True, 'priority': 'later',
        'what': 'One line per row: the title, then properties inline (bullets, numbers or none), under group headings. The phone layout of a table.',
        'uses': {'rp': 'search results and every table at phone width', 'vt': 'the runs feed', 'ml': 'recent runs', 'money': 'recent transactions'},
        'keys': {'bases': ['markers (bullet | number | none)', 'indentProperties', 'separator (default ", ")', 'order', 'sort', 'groupBy', 'limit', 'filters'], 'ours': ['subGroupBy', 'tree']},
        'selected': 'tv-list',
        'why': 'TanStack Virtual is already in the table\'s bundle; a list is its row renderer with a different template.',
        'ours': 120, 'ours_note': 'estimate',
        'packages': ['@tanstack/virtual-core'],
        'candidates': [
            {'id': 'tv-list', 'name': 'TanStack Virtual', 'pkg': '@tanstack/virtual-core', 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 4, 'css': 5}, 'note': 'headless; 0 KB extra'},
            {'id': 'virtua', 'name': 'virtua', 'pkg': 'virtua', 'size': 'virtua-core', 'scores': {'fw': 4, 'rows': 5, 'cfg': 4, 'css': 5, 'maint': 4},
             'note': 'its framework-free core is exported as virtua/unstable_core'},
            {'id': 'clusterize', 'name': 'Clusterize.js', 'pkg': 'clusterize.js', 'size': None, 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 5}, 'note': 'takes HTML strings, not rows'},
            {'id': 'cv-auto', 'name': 'Plain DOM + content-visibility: auto', 'pkg': None, 'ours': True, 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 4, 'css': 5},
             'note': 'no virtualisation; fine to ~2,000 rows'},
        ],
    },
    {
        'id': 'cards', 'name': 'Cards / gallery', 'type': 'cards', 'bases': True, 'priority': 'now',
        'what': 'A grid of cards: an image (or a to-scale drawing), the title and a few properties; group headings; masonry when card heights vary.',
        'uses': {'rp': 'parts as cards with a to-scale side view (its photos are linked, not hosted)', 'gal': 'babble variants and logo rounds',
                 'vt': 'track cards', 'ml': 'sample predictions'},
        'keys': {'bases': ['cardSize (50–800, default 200)', 'image (a property)', 'imageFit (cover | contain)', 'imageAspectRatio (0.25–2.5, default 1)', 'order', 'sort', 'groupBy', 'limit', 'filters'],
                 'ours': ['masonry', 'sketch {diameter, length} (demo extension)', 'hover']},
        'selected': 'tv-lanes',
        'why': 'TanStack Virtual\'s `lanes` put each card in the shortest column, so one virtualiser does the grid now and masonry later, '
               'for 0 KB extra.⟦tv-lanes⟧ The masonry libraries are stale and do not virtualise. Running in the demo below on 1,149 actuators.',
        'ours': 150, 'ours_note': 'demo cards.mjs is 112 lines',
        'packages': ['@tanstack/virtual-core'],
        'candidates': [
            {'id': 'tv-lanes', 'name': 'TanStack Virtual (lanes) + CSS', 'pkg': '@tanstack/virtual-core', 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'Bases\' own cards view virtualises the same way'},
            {'id': 'masonry', 'name': 'Masonry (desandro)', 'pkg': 'masonry-layout', 'size': 'masonry-layout', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 5}, 'note': 'lays out DOM it is given; no virtualisation'},
            {'id': 'muuri', 'name': 'Muuri', 'pkg': 'muuri', 'size': 'muuri', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 5}, 'note': 'filter, sort and drag animations; last release 2021'},
            {'id': 'grid-lanes', 'name': 'CSS display: grid-lanes', 'pkg': None, 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5, 'maint': 2, 'licence': 5},
             'note': 'native masonry; stable only in Safari 26.4, so progressive enhancement at most⟦grid-lanes⟧'},
            {'id': 'masonic', 'name': 'masonic', 'pkg': 'masonic', 'size': None, 'scores': {'fw': 2, 'rows': 5, 'cfg': 4, 'css': 5}, 'note': 'virtualised masonry, React only'},
        ],
    },
    {
        'id': 'media', 'name': 'Image / media grid', 'type': 'cards', 'bases': True, 'priority': 'soon',
        'what': 'A cards view whose card is the image or video, opening a full-screen lightbox with zoom, pan and swipe and a caption from properties.',
        'uses': {'gal': 'screenshots, babble variants, logo contact sheets, hero videos', 'ml': 'failure cases and predictions', 'vt': 'run captures',
                 'rp': 'only files robotparts may host (SCHEMA2 §4)'},
        'keys': {'bases': ['image', 'imageFit', 'imageAspectRatio', 'cardSize'], 'ours': ['lightbox: true', 'media (a property holding an image or video URL)', 'caption [properties]']},
        'selected': 'photoswipe',
        'why': 'Not a new view: the cards view plus a lightbox. PhotoSwipe is the mature MIT one, framework-free, themed by 12 CSS custom properties; '
               'video is ~20 lines of its custom-content hook. lightGallery (GPL) and Fancybox (paid commercially) fail the licence.',
        'ours': 60, 'ours_note': 'estimate, on top of cards',
        'packages': ['photoswipe'],
        'candidates': [
            {'id': 'photoswipe', 'name': 'PhotoSwipe', 'pkg': 'photoswipe', 'size': 'photoswipe', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'gestures and zoom are the best of the set; last release May 2024, low churn'},
            {'id': 'glightbox', 'name': 'GLightbox', 'pkg': 'glightbox', 'size': 'glightbox', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 2}, 'note': 'video built in; no CSS variables'},
            {'id': 'lightgallery', 'name': 'lightGallery', 'pkg': 'lightgallery', 'size': 'lightgallery', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 2, 'licence': 1}, 'flags': ['GPL-3.0 or commercial'], 'note': '⟦lightgallery⟧'},
            {'id': 'fancybox', 'name': 'Fancybox', 'pkg': '@fancyapps/ui', 'size': 'fancybox', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5, 'licence': 1}, 'flags': ['paid for commercial use'], 'note': '⟦fancybox⟧'},
            {'id': 'justified', 'name': 'justified-layout (Flickr)', 'pkg': 'justified-layout', 'size': 'justified-layout', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'only the row-packing maths; a helper if Zach wants justified rows'},
            {'id': 'dialog', 'name': 'Native <dialog>', 'pkg': None, 'ours': True, 'size': 0, 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'no zoom, pan or swipe'},
        ],
    },
    {
        'id': 'chart', 'name': 'Chart', 'type': 'chart', 'bases': False, 'priority': 'now',
        'what': 'Any Vega-Lite chart of the view\'s rows: scatter, line, bar, histogram (bin), box plot, heatmap, small multiples (facet). '
                'Presets: Ashby log-log with family envelopes and an index line.',
        'uses': {'rp': 'Ashby torque vs mass; price vs torque', 'ml': 'loss curves, metric vs hyperparameter, histograms', 'rack': 'error per bench as box plots',
                 'vt': 'runs over time', 'money': 'spend by month'},
        'keys': {'bases': ['filters', 'sort'], 'ours': ['chart (a Vega-Lite spec minus data, datasets, $schema, config)', 'guides [rule | envelope {property, shape} | indexLine {slope, through}]', 'hover']},
        'selected': 'vegalite',
        'why': 'The `chart:` block is a Vega-Lite spec, so the grammar an agent edits is the one it already knows, the one Altair writes from '
               'Python⟦altair⟧ and the one Zach picked for the model canvas on Oct 5.⟦vault-vl⟧ It covers every chart type asked for (log scales, '
               'boxplot, bin, facet, selections).⟦vl-docs⟧ The cost is size: 283 KB gzipped, so it loads only when a chart view opens. The SPEC '
               'reached the same pick on its own criteria.⟦spec,spec-schema⟧ Running in the demo below.',
        'ours': 250, 'ours_note': 'demo chart.mjs is 146 lines (rows in, theme from tokens, types from the schema, envelopes, index line)',
        'packages': ['vega', 'vega-lite', 'vega-embed'],
        'candidates': [
            {'id': 'vegalite', 'name': 'Vega-Lite + vega-embed', 'pkg': 'vega-lite', 'size': 'vega+vega-lite+vega-embed', 'size_note': 'vega 181 + vega-lite compiler ~81 + embed ~20',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 3}, 'note': 'colours resolved from tokens into its config (SVG/canvas cannot read var()); no hull, so envelopes are ours'},
            {'id': 'gw', 'name': 'Graphic Walker', 'pkg': '@kanaries/graphic-walker', 'size': 'graphic-walker', 'extra': 67.3,
             'scores': {'fw': 2, 'rows': 4, 'cfg': 2, 'css': 3}, 'note': 'Tableau-like shelves on Vega-Lite; its own IChart spec, not Vega-Lite; embedGraphicWalker() mounts React inside; '
                                                                      'its NL box posts to api.kanaries.net unless `askviz` is given your own function, so Zach\'s agent could drive it⟦gw⟧'},
            {'id': 'plot', 'name': 'Observable Plot', 'pkg': '@observablehq/plot', 'size': 'observable-plot',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 2, 'css': 4}, 'note': 'the only one with a built-in hull mark⟦plot-hull⟧, but a spec is JS calls, not JSON; no release since Feb 2025'},
            {'id': 'echarts', 'name': 'Apache ECharts 6', 'pkg': 'echarts', 'size': 'echarts-subset', 'size_note': 'scatter, line, bar, boxplot, custom + components; full build 374',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 3, 'css': 3}, 'note': 'already in Vibe Tracks and the atlases; option JSON is verbose and formatters want functions; setTheme() for dark⟦echarts6⟧'},
            {'id': 'uplot', 'name': 'uPlot', 'pkg': 'uplot', 'size': 'uplot', 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 2},
             'note': 'the fastest for dense time series (166,650 points in 25 ms) but no aggregation, box or histogram⟦uplot⟧; columnar arrays'},
            {'id': 'chartjs', 'name': 'Chart.js', 'pkg': 'chart.js', 'size': 'chart.js-auto', 'scores': {'fw': 5, 'rows': 4, 'cfg': 3, 'css': 3}, 'note': 'box plot is a plugin; config takes callbacks'},
            {'id': 'plotly', 'name': 'Plotly.js', 'pkg': 'plotly.js-dist-min', 'size': 'plotly.js-dist-min', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 2}, 'note': 'JSON figures, but 1.4 MB gzipped'},
        ],
    },
    {
        'id': 'kpi', 'name': 'KPI card / stat', 'type': 'kpi', 'bases': False, 'priority': 'soon',
        'what': 'One stat card per KPI, or per group: the value with unit and basis, a direction-aware delta, a sparkline, the target or gate, and '
                '"computed from N runs".',
        'uses': {'vt': 'track KPIs (the card in Zach\'s screenshot)', 'ml': 'best metric per experiment', 'rack': 'twin tracking error vs its gate',
                 'rp': 'catalog counts per evidence level', 'money': 'cash and burn'},
        'keys': {'bases': ['groupBy (one card per group)', 'filters'], 'ours': ['kpi {label, value {property, summary, per}, compare {against, better, neutral}, spark {x, y, window}, target, gate}']},
        'selected': 'datakpi',
        'why': 'The survey\'s KPI kit, folded into data-ui by the SPEC as `<data-kpi>`, `<data-value>` and `<data-sparkline>`: framework-free elements '
               'extracted from Vibe Tracks, the vocabulary after Evidence\'s BigValue, the sparkline a ~60-line SVG.⟦spec,survey⟧ It drops the survey\'s '
               'ECharts history element: a full history is a `chart` view, so a page loads one chart engine. Tremor is React, Tailwind and Recharts, '
               'and its npm package has not released since Jan 2025.⟦tremor⟧',
        'ours': 660, 'ours_note': 'estimate: ~600 lines mostly moved out of Vibe Tracks\' kpi-chart.js (survey), + ~60 for the view',
        'packages': [],
        'candidates': [
            {'id': 'datakpi', 'name': '<data-kpi> + <data-value> + <data-sparkline>', 'pkg': None, 'ours': True, 'size': 5, 'size_note': 'card, value and SVG sparkline; no chart engine',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5, 'maint': 3}, 'note': 'SPEC §9; not built yet; Vibe Tracks\' tiles are the source'},
            {'id': 'bamkpi', 'name': 'The survey\'s kit with <bam-kpi-history> on ECharts 6', 'pkg': 'echarts', 'size': 'echarts-subset',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 3, 'css': 3}, 'note': 'a second chart engine beside Vega-Lite; the SPEC keeps ECharts only in Vibe Tracks\' drill-down⟦spec⟧'},
            {'id': 'tremor', 'name': 'Tremor', 'pkg': '@tremor/react', 'size': 'tremor-react', 'extra': 67.3, 'scores': {'fw': 1, 'rows': 4, 'cfg': 3, 'css': 3}, 'flags': ['paid blocks'],
             'note': 'React + Tailwind + Recharts'},
            {'id': 'bigvalue', 'name': 'Evidence BigValue', 'pkg': None, 'size': None, 'scores': {'fw': 1, 'rows': 3, 'cfg': 5, 'css': 3, 'maint': 2, 'licence': 5}, 'note': 'a spec to copy, not a part: Svelte inside the Evidence framework'},
            {'id': 'shadcn-cards', 'name': 'shadcn dashboard-01 SectionCards', 'pkg': None, 'size': None, 'scores': {'fw': 1, 'rows': 2, 'cfg': 2, 'css': 5, 'maint': 4, 'licence': 5}, 'note': 'four hard-coded React cards, no sparkline'},
        ],
    },
    {
        'id': 'kanban', 'name': 'Kanban / board', 'type': 'kanban', 'bases': True, 'priority': 'soon',
        'what': 'Columns are the values of `groupBy` in `groupOrder`, cards are rows. Dragging a card proposes a data edit; dragging a column reorders '
                'the view. Swimlanes come from `subGroupBy`.',
        'uses': {'vt': 'tracks by status, legs by state', 'rp': 'parts by evidence level (read-only: level is derived) and parts to ingest',
                 'ml': 'experiments by stage', 'money': 'to-categorise → categorised'},
        'keys': {'bases': ['groupBy (the columns)', 'groupOrder', 'columnWidth (200–500, default 280)', 'image', 'imageFit', 'imageAspectRatio (default 0.5)', 'order', 'sort', 'filters'],
                 'ours': ['subGroupBy (swimlanes)']},
        'selected': 'pragmatic',
        'why': 'Obsidian made kanban a core Bases layout in 1.14,⟦obs-changelog,obs-app⟧ so the type and keys are Bases\'. Pragmatic drag and drop '
               'is headless and framework-free (7 KB): it reports what was dropped where and never moves a node, so a card moves only when the host '
               'accepts the edit and a virtualised column of 1,147 cards keeps working. SortableJS moves the DOM itself. Running in the demo below.',
        'ours': 250, 'ours_note': 'demo kanban.mjs is 126 lines (columns, virtual cards, card and column drags)',
        'packages': ['@atlaskit/pragmatic-drag-and-drop', '@atlaskit/pragmatic-drag-and-drop-hitbox', '@tanstack/virtual-core'],
        'candidates': [
            {'id': 'pragmatic', 'name': 'Pragmatic drag and drop (+ hitbox)', 'pkg': '@atlaskit/pragmatic-drag-and-drop', 'size': 'pragmatic-dnd(element+hitbox+autoscroll)',
             'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'Atlassian\'s (Trello, Jira); drop indicators and keyboard moves are ours'},
            {'id': 'sortable', 'name': 'SortableJS', 'pkg': 'sortablejs', 'size': 'sortablejs', 'scores': {'fw': 5, 'rows': 2, 'cfg': 4, 'css': 5},
             'note': 'least code for a plain board, but it moves DOM nodes itself, which fights virtualisation and the propose-then-redraw rule'},
            {'id': 'dndkit-dom', 'name': '@dnd-kit/dom', 'pkg': '@dnd-kit/dom', 'size': 'dnd-kit-dom', 'scores': {'fw': 5, 'rows': 5, 'cfg': 4, 'css': 5, 'maint': 3}, 'note': 'framework-agnostic but 0.5.1, pre-1.0⟦dndkit⟧'},
            {'id': 'dndkit', 'name': '@dnd-kit/core', 'pkg': '@dnd-kit/core', 'size': 'dnd-kit-core(react)', 'extra': 67.3, 'scores': {'fw': 2, 'rows': 5, 'cfg': 4, 'css': 5}, 'note': 'React; best keyboard support'},
            {'id': 'pangea', 'name': '@hello-pangea/dnd', 'pkg': '@hello-pangea/dnd', 'size': 'hello-pangea-dnd(react)', 'extra': 67.3, 'scores': {'fw': 2, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'React fork of react-beautiful-dnd'},
            {'id': 'jkanban', 'name': 'jKanban', 'pkg': 'jkanban', 'size': 'jkanban', 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 2}, 'note': 'stale; react-trello and @asseinfo/react-kanban are stale or archived too⟦kanban-stale⟧'},
        ],
    },
    {
        'id': 'calendar', 'name': 'Calendar', 'type': 'calendar', 'bases': False, 'priority': 'later',
        'what': 'Rows with a date, or a start and end, on month, week, day and list grids; resources (rows from `groupBy`) optional.',
        'uses': {'vt': 'runs per day', 'money': 'transactions and bills by date', 'ml': 'runs per day', 'rack': 'bench sessions', 'rp': 'price observations'},
        'keys': {'bases': ['groupBy (resources)', 'filters'], 'ours': ['start', 'end', 'title', 'calendarView (month | week | day | list | resourceTimeline)']},
        'selected': 'eventcal',
        'why': 'Event Calendar ships a standalone, framework-free bundle (Svelte compiled inside), is MIT with its resource and timeline views free, '
               'is themed by 29 CSS custom properties and released today.⟦ec⟧ FullCalendar keeps timeline and resource views in Premium,⟦fc-pricing⟧ '
               'Schedule-X charges for drag-and-drop,⟦sx-premium⟧ TOAST UI was archived in September.⟦tui-archived⟧',
        'ours': 100, 'ours_note': 'estimate: rows → events, the view keys, click → peek',
        'packages': ['@event-calendar/build'],
        'candidates': [
            {'id': 'eventcal', 'name': 'Event Calendar (vkurko)', 'pkg': '@event-calendar/build', 'size': 'event-calendar-build', 'scores': {'fw': 4, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'FullCalendar-like options; events are a thin mapping from rows'},
            {'id': 'fullcalendar', 'name': 'FullCalendar 7', 'pkg': 'fullcalendar', 'size': 'fullcalendar7(daygrid+timegrid+list+interaction+classic)', 'extra': 20.0,
             'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5, 'licence': 3}, 'flags': ['open-core'], 'note': 'standard views MIT; timeline and resource views Premium; + temporal-polyfill 20 KB'},
            {'id': 'schedulex', 'name': 'Schedule-X', 'pkg': '@schedule-x/calendar', 'size': 'schedule-x-calendar(+preact)', 'extra': 20.0,
             'scores': {'fw': 4, 'rows': 4, 'cfg': 4, 'css': 5, 'licence': 2}, 'flags': ['open-core'], 'note': 'drag-and-drop, resize and resource views are premium'},
            {'id': 'tui', 'name': 'TOAST UI Calendar', 'pkg': '@toast-ui/calendar', 'size': 'toast-ui-calendar', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 2, 'maint': 1}, 'flags': ['archived'], 'note': 'archived 2026-09-02'},
        ],
    },
    {
        'id': 'timeline', 'name': 'Timeline / Gantt', 'type': 'timeline', 'bases': False, 'priority': 'later',
        'what': 'Rows as bars (start → end) or points on a zoomable time axis, in lanes from `groupBy`, nested from `subGroupBy`. A Gantt adds dependencies and progress.',
        'uses': {'vt': 'agent runs per track over time', 'ml': 'training runs per GPU or host', 'rack': 'test campaigns', 'rp': 'release history'},
        'keys': {'bases': ['groupBy (lanes)', 'filters', 'sort'], 'ours': ['start', 'end', 'title', 'subGroupBy (nested lanes)', 'color', 'zoom {min, max}']},
        'selected': 'vistimeline',
        'why': 'Zach\'s timelines are lanes of runs (many items, grouped, zoomed), which is vis-timeline\'s whole job; it is dual Apache/MIT, framework-free '
               'and released today.⟦vis-timeline⟧ It is heavy (160 KB, moment.js inside) but lazy. Dependency arrows are not its thing: if a real Gantt is '
               'ever needed, Frappe Gantt (13 KB, MIT) is the fallback. DHTMLX and SVAR keep scheduling in PRO.⟦dhtmlx,svar⟧',
        'ours': 120, 'ours_note': 'estimate',
        'packages': ['vis-timeline'],
        'candidates': [
            {'id': 'vistimeline', 'name': 'vis-timeline', 'pkg': 'vis-timeline', 'size': 'vis-timeline-standalone', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 2}, 'note': 'items go into its DataSet; class-based CSS (0 custom properties)'},
            {'id': 'frappe', 'name': 'Frappe Gantt', 'pkg': 'frappe-gantt', 'size': 'frappe-gantt', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'dependencies and progress; one row per task, no lanes'},
            {'id': 'dhtmlx', 'name': 'DHTMLX Gantt', 'pkg': 'dhtmlx-gantt', 'size': 'dhtmlx-gantt', 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 5, 'licence': 3}, 'flags': ['open-core'], 'note': 'MIT since 10.0; PRO: auto-scheduling, resources, critical path, baselines, export'},
            {'id': 'svar', 'name': 'SVAR Gantt', 'pkg': '@svar-ui/react-gantt', 'size': 'svar-react-gantt', 'extra': 67.3, 'scores': {'fw': 2, 'rows': 4, 'cfg': 4, 'css': 5, 'licence': 3}, 'flags': ['open-core'], 'note': 'React/Svelte; PRO from $749/developer'},
            {'id': 'bryntum', 'name': 'Bryntum Gantt', 'pkg': None, 'size': None, 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 3, 'licence': 1, 'maint': 5}, 'flags': ['commercial'], 'note': 'commercial only'},
        ],
    },
    {
        'id': 'map', 'name': 'Map', 'type': 'map', 'bases': True, 'priority': 'later',
        'what': 'Rows with coordinates as markers on a basemap; marker colour and icon from properties; clusters; a click opens the record.',
        'uses': {'rp': 'where a part\'s sellers ship to (listings carry ships_to)', 'money': 'merchant locations (low value)', 'other': 'BAM / Tycoon CRM sites: hospitals, food courts, aggregators'},
        'keys': {'bases': ['coordinates', 'markerIcon', 'markerColor', 'center', 'defaultZoom', 'minZoom', 'maxZoom', 'mapHeight', 'mapTiles', 'mapTilesDark'], 'ours': []},
        'selected': 'maplibre',
        'why': 'Obsidian\'s own Maps plugin registers `map` on MapLibre GL, so the engine and its ten option keys are Bases\' as-is.⟦obs-maps⟧ '
               'The no-CDN rule changes one thing: the basemap is a self-hosted PMTiles file, not Obsidian\'s default OpenFreeMap tiles.',
        'ours': 150, 'ours_note': 'estimate, plus a basemap extract built once',
        'packages': ['maplibre-gl', 'pmtiles'],
        'candidates': [
            {'id': 'maplibre', 'name': 'MapLibre GL + PMTiles', 'pkg': 'maplibre-gl', 'size': 'maplibre-gl', 'extra': 7.4, 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 3}, 'note': 'WebGL vector tiles; the style is JSON we fill from tokens'},
            {'id': 'leaflet', 'name': 'Leaflet', 'pkg': 'leaflet', 'size': 'leaflet', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 2}, 'note': 'last stable 1.9.4 (May 2023); 2.0 in alpha; raster tiles'},
            {'id': 'ol', 'name': 'OpenLayers', 'pkg': 'ol', 'size': 'openlayers(Map+View+Tile+Vector)', 'scores': {'fw': 5, 'rows': 4, 'cfg': 2, 'css': 3}, 'note': 'capable, but an imperative object API'},
            {'id': 'vl-geo', 'name': 'Vega-Lite geoshape', 'pkg': 'vega-lite', 'size': 0, 'size_note': 'already loaded by a chart view', 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 3}, 'note': 'choropleths and dot maps with no tiles: a chart preset, not a map'},
        ],
    },
    {
        'id': 'tree', 'name': 'Tree / hierarchy', 'type': 'table', 'bases': True, 'priority': 'soon',
        'what': 'Rows nested under a parent (or by a dotted path) as an expandable tree-table or outline; group summaries roll up.',
        'uses': {'rp': 'category → brand → part (its import paths, actuator.steadywin.gim4305_10)', 'vt': 'track → leg → run', 'ml': 'experiment → run → checkpoint',
                 'money': 'the category hierarchy'},
        'keys': {'bases': ['(on a table or list view)', 'summaries', 'sort'], 'ours': ['tree {parent: property} | {path: property, separator}', 'fold']},
        'selected': 'tanstack-sub',
        'why': 'Not a new type: TanStack Table\'s sub-rows (getSubRows + the expanding feature already bundled) on the table and list views. '
               '@headless-tree stays the sidebar tree in Clank and pyblocks, where rename, drag and keyboard focus matter more than columns.⟦survey⟧',
        'ours': 80, 'ours_note': 'estimate: parent or path → subRows, indent',
        'packages': ['@tanstack/table-core'],
        'candidates': [
            {'id': 'tanstack-sub', 'name': 'TanStack Table sub-rows', 'pkg': '@tanstack/table-core', 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': '0 KB extra'},
            {'id': 'headless-tree', 'name': 'Headless Tree', 'pkg': '@headless-tree/core', 'size': 'headless-tree-core', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'framework-agnostic core; a tree, not a tree-table'},
            {'id': 'arborist', 'name': 'react-arborist', 'pkg': 'react-arborist', 'size': 'react-arborist(react)', 'extra': 67.3, 'scores': {'fw': 2, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'React + react-dnd'},
            {'id': 'wa-tree', 'name': 'Web Awesome <wa-tree>', 'pkg': '@awesome.me/webawesome', 'size': 'webawesome-tree', 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 5}, 'note': 'a web component tree for vanilla pages'},
            {'id': 'd3h', 'name': 'd3-hierarchy', 'pkg': 'd3-hierarchy', 'size': 'd3-hierarchy', 'scores': {'fw': 5, 'rows': 4, 'cfg': 3, 'css': 5, 'maint': 3}, 'note': 'layouts for a later treemap / sunburst chart preset'},
        ],
    },
    {
        'id': 'graph', 'name': 'Graph / network', 'type': 'graph', 'bases': False, 'priority': 'soon',
        'what': 'Rows as nodes; edges from a property that lists other rows\' ids; an automatic layout; pan and zoom; a click opens the record.',
        'uses': {'rack': 'the model ladder M1 → M5 and which bench feeds which model', 'rp': 'actuator ↔ driver ↔ PSU compatibility, same_as links',
                 'vt': 'track and leg dependencies', 'ml': 'run → checkpoint → fine-tune lineage'},
        'keys': {'bases': ['order (fields on a node)', 'groupBy (sub-flows or colour)', 'filters'], 'ours': ['edges {property, label} (required: no edge is ever inferred)', 'layout {algorithm: dagre, direction: LR | TB}']},
        'selected': 'reactflow',
        'why': 'Zach\'s call (2026-10-25: "I love react flow").⟦zach-1025⟧ It is also his Block View chassis, where nodes are arbitrary UI with real ports.⟦vault-rf⟧ '
               'The scores below favour Cytoscape on framework-free and size; React Flow wins where Zach\'s graphs live: tens to hundreds of nodes, each '
               'a small card. It mounts as a React island (below); layout is dagre, the one React Flow recommends for trees and DAGs.⟦rf-layout⟧',
        'ours': 200, 'ours_note': 'estimate: island wrapper ~60, rows → nodes and edges ~40, node card ~60, dagre ~40',
        'packages': ['@xyflow/react', 'react', 'react-dom', '@dagrejs/dagre'],
        'candidates': [
            {'id': 'reactflow', 'name': 'React Flow (@xyflow/react)', 'pkg': '@xyflow/react', 'size': 'xyflow-react+react island', 'extra': 16.6, 'size_note': '@xyflow/react 61 + React 19 67, + dagre 17',
             'scores': {'fw': 3, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'custom nodes are components; 37 CSS custom properties; DOM nodes, so ~1-2k nodes at most'},
            {'id': 'cytoscape', 'name': 'Cytoscape.js', 'pkg': 'cytoscape', 'size': 'cytoscape', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 3}, 'note': 'framework-free, layouts built in, JSON stylesheet; canvas, so nodes are not HTML'},
            {'id': 'sigma', 'name': 'Sigma + graphology', 'pkg': 'sigma', 'size': 'sigma+graphology', 'scores': {'fw': 5, 'rows': 3, 'cfg': 3, 'css': 3}, 'note': 'WebGL for 10k+ nodes; the right swap if a graph ever gets that big'},
            {'id': 'visnetwork', 'name': 'vis-network', 'pkg': 'vis-network', 'size': 'vis-network-standalone', 'scores': {'fw': 5, 'rows': 3, 'cfg': 4, 'css': 2}, 'note': 'physics layout; canvas'},
            {'id': 'forcegraph', 'name': 'force-graph', 'pkg': 'force-graph', 'size': 'force-graph', 'scores': {'fw': 5, 'rows': 4, 'cfg': 3, 'css': 3}, 'note': 'd3-force on canvas; no hierarchy layout'},
            {'id': 'xysystem', 'name': '@xyflow/system', 'pkg': '@xyflow/system', 'size': 'xyflow-system', 'scores': {'fw': 5, 'rows': 4, 'cfg': 3, 'css': 5, 'maint': 4},
             'note': 'the "shared helper library" under React Flow and Svelte Flow⟦xyflow⟧: pan/zoom, drag, edge paths, but no renderer, so a vanilla flow would be ours'},
        ],
    },
    {
        'id': 'record', 'name': 'Record / peek / detail page', 'type': 'record', 'bases': False, 'priority': 'now',
        'what': 'One row as a property sheet: label, value with unit and basis, the records behind a value. It opens from every view as a side peek, or as '
                'its own page (the datasheet is one record transposed into rows).',
        'uses': {'rp': 'the part page and the datasheet', 'vt': 'run detail', 'ml': 'run detail: params, metrics, artefacts', 'rack': 'the measurements behind a value',
                 'money': 'a transaction'},
        'keys': {'bases': ['order (the fields)'], 'ours': ['record {sections: [{name, properties}]}', 'hover', 'open: expand | side | link (every view; how a record opens)']},
        'selected': 'peek',
        'why': 'The lane already built the peek (all the measurements behind a value, highlighted, Esc closes). Generalised, it becomes the one record '
               'surface every view opens; a standalone record page is that same sheet at full width.⟦lane⟧ Native <dialog> and the Popover API cover the chrome.',
        'ours': 150, 'ours_note': 'built in the lane; generalising it is ~50 more',
        'packages': [],
        'candidates': [
            {'id': 'peek', 'name': 'The lane\'s peek, generalised', 'pkg': None, 'ours': True, 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'every view calls host.open(id)'},
            {'id': 'wa-drawer', 'name': 'Web Awesome <wa-drawer>', 'pkg': '@awesome.me/webawesome', 'size': None, 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'chrome only; the sheet is still ours'},
            {'id': 'sheet', 'name': 'shadcn Sheet', 'pkg': None, 'size': None, 'scores': {'fw': 1, 'rows': 4, 'cfg': 4, 'css': 5, 'maint': 5, 'licence': 5}, 'note': 'React apps only'},
        ],
    },
    {
        'id': 'form', 'name': 'Form / editor', 'type': 'record', 'bases': False, 'priority': 'later',
        'what': 'Edit one row: inputs made from the dataset\'s property schema (text, number with unit and bounds, enum, list, date, bool). Submitting '
                'proposes an edit, which the host accepts or refuses.',
        'uses': {'vt': 'set a KPI target or gate', 'rack': 'the dataclass viewer\'s Value(1.2, "m", low=…) inputs', 'rp': 'an Ingestor part.json entry',
                 'money': 'categorise a transaction, edit a rule', 'ml': 'a launch config'},
        'keys': {'bases': ['order (the fields)'], 'ours': ['edit: true (on a record view or the peek)']},
        'selected': 'native-form',
        'why': 'No stock option is framework-free and themable: JSON Forms\' renderers need React, Angular or Vue,⟦jsonforms⟧ json-editor brings '
               'Bootstrap-era themes, and react-hook-form and RJSF are React. The schema is already the dataset\'s `properties` (type, unit, bounds, '
               'labels), so the form is native inputs over it, and a submit goes through host.propose().',
        'ours': 200, 'ours_note': 'estimate',
        'packages': [],
        'candidates': [
            {'id': 'native-form', 'name': 'Native inputs over the property schema', 'pkg': None, 'ours': True, 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'constraint validation is the browser\'s'},
            {'id': 'jsonforms', 'name': 'JSON Forms', 'pkg': '@jsonforms/core', 'size': 'jsonforms-core', 'extra': 101.1, 'scores': {'fw': 2, 'rows': 4, 'cfg': 5, 'css': 3}, 'note': 'core is framework-free; renderers are not (+ React vanilla renderers 34 + React 67)'},
            {'id': 'jsoneditor', 'name': 'json-editor', 'pkg': '@json-editor/json-editor', 'size': 'json-editor', 'scores': {'fw': 5, 'rows': 4, 'cfg': 5, 'css': 2}, 'note': 'vanilla; themes are Bootstrap / Spectre / Tailwind class sets'},
            {'id': 'rhf', 'name': 'react-hook-form', 'pkg': 'react-hook-form', 'size': 'react-hook-form(react)', 'extra': 67.3, 'scores': {'fw': 1, 'rows': 4, 'cfg': 2, 'css': 5}, 'note': 'state only; fields are yours'},
            {'id': 'rjsf', 'name': 'react-jsonschema-form', 'pkg': '@rjsf/core', 'size': 'rjsf-core(react)', 'extra': 67.3, 'scores': {'fw': 1, 'rows': 4, 'cfg': 5, 'css': 3}, 'note': 'React; includes AJV'},
        ],
    },
    {
        'id': 'compare', 'name': 'Compare (side by side)', 'type': 'compare', 'bases': False, 'priority': 'soon',
        'what': '2-6 chosen rows side by side: one column per row, one line per property, the better value marked by each property\'s direction, a '
                '"differences only" switch; an image pair as a slider.',
        'uses': {'rp': 'actuators side by side (the catalog\'s `comparisons`)', 'rack': 'model A vs B per bench; measured vs datasheet', 'ml': 'run A vs run B: params diff, metric delta',
                 'gal': 'variant A vs B', 'vt': 'two runs'},
        'keys': {'bases': ['order (the properties)'], 'ours': ['compare {rows: [ids] | "selection", better: {property: higher | lower}, diffOnly}']},
        'selected': 'transpose',
        'why': 'No maintained compare component exists outside React and Bootstrap one-offs.⟦npm-search⟧ It is the table on transposed rows (one column per '
               'record), so the engine is the one already there; img-comparison-slider is a 4 KB web component for image pairs.⟦img-cmp⟧',
        'ours': 120, 'ours_note': 'estimate',
        'packages': ['@tanstack/table-core', 'img-comparison-slider'],
        'candidates': [
            {'id': 'transpose', 'name': 'TanStack Table on transposed rows', 'pkg': '@tanstack/table-core', 'size': 0, 'scores': {'fw': 5, 'rows': 5, 'cfg': 5, 'css': 5}, 'note': 'ours: transpose, best-value marks, diff-only'},
            {'id': 'imgcmp', 'name': 'img-comparison-slider', 'pkg': 'img-comparison-slider', 'size': 'img-comparison-slider', 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'helper for image pairs'},
            {'id': 'jsdiff', 'name': 'jsdiff', 'pkg': 'diff', 'size': None, 'scores': {'fw': 5, 'rows': 4, 'cfg': 4, 'css': 5}, 'note': 'helper if long text values need a word diff'},
            {'id': 'perspective', 'name': 'Perspective', 'pkg': '@perspective-dev/viewer', 'size': 4270, 'scores': {'fw': 4, 'rows': 2, 'cfg': 4, 'css': 3}, 'note': 'no transposed view'},
        ],
    },
]

# Where no good stock option exists, or the stock part is only a helper and the view is ours.
NO_STOCK = ['pivot', 'record', 'form', 'compare']

# One line for the summary table.
SHORT = {
    'table': 'Decided by the table lane: headless engine, Notion-like surface ours, 36 KB gz, 22/22 checks.',
    'pivot': 'A transform before the table: same menus and drill-down, no new library.',
    'list': 'Same virtualiser as the table, another row template; 0 KB extra.',
    'cards': '`lanes` give grid now and masonry later in one virtualiser; 0 KB extra. Live below.',
    'media': 'Cards plus a lightbox; the mature MIT one, 12 CSS variables. lightGallery is GPL, Fancybox paid.',
    'chart': 'The `chart:` block is Vega-Lite: the grammar agents and Altair already write; every chart type asked. 283 KB gz, lazy. Live below.',
    'kpi': 'The survey\'s kit as the SPEC renamed it; a 60-line SVG sparkline, no chart engine. Tremor is React + Tailwind and stale.',
    'kanban': 'Bases\' own type since 1.14. Headless drag (7 KB) that never moves a node, so edits are proposals and columns virtualise. Live below.',
    'calendar': 'Framework-free, MIT, resource and timeline views free, 29 CSS variables. FullCalendar and Schedule-X paywall what we\'d use.',
    'timeline': 'Lanes of runs on a zoomable axis is its whole job; dual Apache/MIT. Frappe Gantt only if dependencies are ever needed.',
    'map': 'The engine Obsidian\'s own Maps plugin uses, with its ten keys as-is; basemap self-hosted (PMTiles), never a tile CDN.',
    'tree': 'TanStack sub-rows on the table and list views; 0 KB extra. Not a new type.',
    'graph': 'Zach\'s call; also his Block View chassis. A React island: 128 KB gz with React, 61 KB where React is already loaded.',
    'record': 'The lane\'s peek, generalised into the one record surface every view opens.',
    'form': 'No framework-free stock form fits; native inputs over the dataset\'s own property schema, submits as proposals.',
    'compare': 'No maintained compare component exists; it is the table on transposed rows, plus a 4 KB image slider.',
}

# Judgement for the two criteria the candidate literals above leave out. FIT: does the view's job. STOCK: how much of
# the view the library does (5: under 50 lines of ours ... 2: all ours); maint = min(STOCK, release-age score).
FIT = {
    'table': {'tanstack': 5, 'perspective': 4, 'tabulator': 4, 'aggrid': 2, 'datatables': 2},
    'pivot': {'lane-pivot': 4, 'perspective': 5, 'pivottable': 4, 'webdatarocks': 5, 'flexmonster': 5},
    'list': {'tv-list': 5, 'virtua': 5, 'clusterize': 3, 'cv-auto': 3},
    'cards': {'tv-lanes': 5, 'masonry': 3, 'muuri': 4, 'grid-lanes': 3, 'masonic': 5},
    'media': {'photoswipe': 5, 'glightbox': 4, 'lightgallery': 5, 'fancybox': 5, 'justified': 1, 'dialog': 2},
    'chart': {'vegalite': 5, 'gw': 4, 'plot': 4, 'echarts': 5, 'uplot': 2, 'chartjs': 3, 'plotly': 5},
    'kpi': {'datakpi': 5, 'bamkpi': 5, 'tremor': 4, 'bigvalue': 3, 'shadcn-cards': 2},
    'kanban': {'pragmatic': 4, 'sortable': 4, 'dndkit-dom': 4, 'dndkit': 5, 'pangea': 5, 'jkanban': 3},
    'calendar': {'eventcal': 5, 'fullcalendar': 4, 'schedulex': 3, 'tui': 4},
    'timeline': {'vistimeline': 5, 'frappe': 2, 'dhtmlx': 3, 'svar': 3, 'bryntum': 5},
    'map': {'maplibre': 5, 'leaflet': 4, 'ol': 5, 'vl-geo': 2},
    'tree': {'tanstack-sub': 5, 'headless-tree': 3, 'arborist': 3, 'wa-tree': 3, 'd3h': 2},
    'graph': {'reactflow': 5, 'cytoscape': 4, 'sigma': 4, 'visnetwork': 4, 'forcegraph': 3, 'xysystem': 1},
    'record': {'peek': 5, 'wa-drawer': 2, 'sheet': 2},
    'form': {'native-form': 4, 'jsonforms': 5, 'jsoneditor': 4, 'rhf': 3, 'rjsf': 5},
    'compare': {'transpose': 5, 'imgcmp': 1, 'jsdiff': 1, 'perspective': 1},
}
STOCK = {
    'table': {'tanstack': 3, 'perspective': 5, 'tabulator': 4, 'aggrid': 4, 'datatables': 4},
    'list': {'tv-list': 4, 'virtua': 4, 'clusterize': 4},
    'cards': {'tv-lanes': 4, 'masonry': 4, 'muuri': 4, 'grid-lanes': 4, 'masonic': 4},
    'chart': {'vegalite': 4, 'gw': 5, 'plot': 4, 'echarts': 3, 'uplot': 3, 'chartjs': 4, 'plotly': 4},
    'kanban': {'pragmatic': 3, 'sortable': 4, 'dndkit-dom': 3, 'dndkit': 3, 'pangea': 4, 'jkanban': 5},
    'map': {'maplibre': 4, 'leaflet': 4, 'ol': 4, 'vl-geo': 4},
    'tree': {'tanstack-sub': 4, 'headless-tree': 4, 'arborist': 4, 'wa-tree': 4, 'd3h': 3},
    'graph': {'reactflow': 4, 'cytoscape': 4, 'sigma': 4, 'visnetwork': 4, 'forcegraph': 4, 'xysystem': 2},
    'record': {'wa-drawer': 3, 'sheet': 3},
    'form': {'jsonforms': 3, 'rhf': 3},
    'compare': {'transpose': 3},
}
