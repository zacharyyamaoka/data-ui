// npm test: everything, in order, and the real result of each. Exit 1 if any part fails.
//   1. npm run build (the browser checks read dist/)
//   2. node --test: tests/unit/ (core, checker, gallery) and tools/facets.test.mjs (the SPEC's rail proof)
//   3. python3 -m unittest: tools/ (the Python checker) and packages/core/python/ (the stdlib .base reader)
//   4. the browser checks, tests/browser/checks.py, frame_checks.py, chrome_checks.py, lifecycle_checks.py, perf_views_checks.py, legend_checks.py, with Playwright's Python (DATA_UI_PYTHON, default the
//      psu-atlas venv); skipped, and said so, when that Python is missing. `--browser-only` runs 1 and 4.
// --strict (CI, tools/release.mjs): a suite that did not run is a failure, unless NEEDS below says why it cannot run here.
// WHY: without it a missing Playwright skipped every browser check and exited 0, the green that means nothing.
// DATA_UI_TEST_SUMMARY=FILE writes the run as JSON: what ran, how long, what was skipped and why.
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PY = process.env.DATA_UI_PYTHON || '~/psu-atlas/.venv/bin/python';
const browserOnly = process.argv.includes('--browser-only');
const strict = process.argv.includes('--strict') || process.env.CI === 'true';
// The suites whose oracle is a file git cannot hold: the rack's full-rate logs, private and tens of GB. On a machine
// without them the suite has nothing to compare with, so it is skipped by name, with this reason, in every summary.
// tests/browser/p2_checks.py and p4_checks.py each report a missing archive as a failure of their own.
const RACK = process.env.RACK || '/archive/datasets/bam_rig';
// WHY the notes too: gallery/md-pages is Zach's real feedback, so tools/public-export.mjs keeps it out of a public copy,
// and these suites read it. Here they run; there they are skipped by name.
const NOTES = join(ROOT, 'gallery', 'md-pages');
const NOTES_TESTS = ['md-notes.test.mjs', 'serve-md.test.mjs'];
const NEEDS = {
  'P2 checks': [RACK, `needs the rack's raw logs at ${RACK}: its numpy oracles read them, and they are private and not in git`],
  'P4 checks': [RACK, `needs the rack's raw logs at ${RACK}: its numpy oracles read them, and they are private and not in git`],
  'md-pages unit tests': [NOTES, 'needs gallery/md-pages: real notes, private, kept out of a public copy (tools/public-export.mjs)'],
  'md-pages checks': [NOTES, 'needs gallery/md-pages: real notes, private, kept out of a public copy (tools/public-export.mjs)'],
};
// The Node the golden digests were written on. WHY it matters (2026-10-30): V8 13's `**` differs from V8 12's in the last
// bits for 2 of the 24 log-histogram edges in filters-gallery, so tests/unit/perf-oracle.golden.json's rail digest is
// d5d5e895 on Node 22 and d311b16f on Node 24, every run. This machine has both (`node` on PATH decides), which is why it
// looked intermittent. docs/CI.md has the measurement.
const PINNED = /^NODE_VERSION=(.+)$/m.exec(readFileSync(join(ROOT, 'tools', 'ci', 'versions.env'), 'utf8'))[1];
if (process.version !== `v${PINNED}`) console.log(`warning: Node ${process.version} on ${process.execPath}, CI pins v${PINNED}; the perf oracle's rail digest only matches on Node 22`);
const results = [];
const seconds = {};
const step = (name, cmd, args) => {
  const need = NEEDS[name];
  if (need && !existsSync(need[0])) { console.log(`\n== ${name}: skipped: ${need[1]}`); results.push([name, `SKIPPED: ${need[1]}`]); return; }
  console.log(`\n== ${name}: ${[cmd, ...args].join(' ')}`);
  const started = Date.now();
  // WHY execPath: every step runs on the Node this run started on, not whichever `node` PATH finds first
  const r = spawnSync(cmd === 'node' ? process.execPath : cmd, args, { cwd: ROOT, stdio: 'inherit' });
  seconds[name] = Math.round((Date.now() - started) / 1000);
  results.push([name, r.status === 0 ? 'pass' : `FAIL (exit ${r.status})`]);
};

// WHY first: a dashboard's "Open in Rerun" serves a generated .rrd (gitignored; docs/RERUN.md), and the build copies it
// into the site. rerun-sdk is a build-time extra run by uv, never a runtime dependency; without uv the step says so and
// the Rerun checks see the button's disabled state instead
{
  const uv = spawnSync('uv', ['--version'], { stdio: 'ignore' }).status === 0;
  const bases = readdirSync(join(ROOT, 'gallery', 'examples')).map((d) => join('gallery', 'examples', d, 'views.base'))
    .filter((f) => existsSync(join(ROOT, f)) && /^rerun:/m.test(readFileSync(join(ROOT, f), 'utf8')));
  if (!uv) results.push(['rerun exports', 'SKIPPED: no uv on PATH (the .rrd files are a uv build-time extra)']);
  else for (const f of bases) step(`rerun export ${f.split('/')[2]}`, 'uv', ['run', '--script', 'tools/rerun_export.py', f]);
}
step('build', 'node', ['build.mjs']);
// WHY here, before any browser check: the gallery index draws a captured picture per case (site/.thumbs/, gitignored)
// and falls back to drawing every case live when one is missing, which the site checks cannot wait out; capture is
// incremental (a case whose files hash the same is skipped), so a warm run costs seconds. The deploy uploads these.
if (existsSync(PY)) step('gallery thumbnails', PY, ['site/capture-thumbs.py']);
if (!browserOnly) {
  const unit = readdirSync(join(ROOT, 'tests', 'unit')).filter((f) => f.endsWith('.test.mjs') && !NOTES_TESTS.includes(f)).map((f) => `tests/unit/${f}`);
  const toolTests = readdirSync(join(ROOT, 'tools')).filter((f) => f.endsWith('.test.mjs')).map((f) => `tools/${f}`);
  step('unit (node --test)', 'node', ['--test', ...unit, ...toolTests]);
  step('md-pages unit tests', 'node', ['--test', ...NOTES_TESTS.map((f) => `tests/unit/${f}`)]);
  step('python checker', 'python3', ['-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py']);
  step('python .base reader', 'python3', ['-m', 'unittest', 'discover', '-s', 'packages/core/python', '-p', 'test_*.py']);
}
if (existsSync(PY)) step('browser checks', PY, ['tests/browser/checks.py']);
else results.push(['browser checks', `SKIPPED: no Playwright Python at ${PY} (set DATA_UI_PYTHON)`]);
// frame="…" (docs/CONTRACT.md §12): its own file, so lanes editing checks.py never meet it
// the gate numbers the browser checks measured (CONTRACT §29's outline error) into Vibe Tracks' data-ui track; it never
// fails the run (no producer folder, or DATA_UI_KPI_PUBLISH=0: said and skipped)
if (existsSync(PY)) step('publish gate KPIs', 'python3', ['tools/publish_checks.py']);
if (existsSync(PY)) step('frame checks', PY, ['tests/browser/frame_checks.py']);
if (existsSync(PY)) step('chrome checks', PY, ['tests/browser/chrome_checks.py']);
// removal, re-adding and late async work (the 2026-10-26 review's RISK findings): its own file, as the frame checks
if (existsSync(PY)) step('lifecycle checks', PY, ['tests/browser/lifecycle_checks.py']);
// the view-side performance changes (lane/perf-views): keyed table rows against a full redraw, the lazy lightbox and
// the KPI history after the headline; its own file, as the two above
if (existsSync(PY)) step('perf-views checks', PY, ['tests/browser/perf_views_checks.py']);
// the core's performance changes (lane/perf-core): the rail counts after the rows paint and only when its inputs change,
// the row model is reused while its inputs are the same, search keys coalesce; its own file, as the ones above
if (existsSync(PY)) step('perf-core checks', PY, ['tests/browser/perf_core_checks.py']);
if (existsSync(PY)) step('perf-map checks', PY, ['tests/browser/perf_map_checks.py']);
// property types, the column menu and the table's lines (lane/types, CONTRACT §28): its own file, as the ones above
if (existsSync(PY)) step('types checks', PY, ['tests/browser/types_checks.py']);

// the bar's open tab and the query box's suggestions from 360 to 1280 px (robotparts 2026.10.26.12's two defects); its own file, as the ones above
if (existsSync(PY)) step('toolbar polish checks', PY, ['tests/browser/toolbar_polish_checks.py']);

// the right-click "where this value comes from" popover (docs/CONTRACT.md §22); its own file, as the ones above
if (existsSync(PY)) step('sources checks', PY, ['tests/browser/sources_checks.py']);

// the lineage view's first view: the whole tree when it fits at 0.5x or more, else 0.6x on the focus (docs/CONTRACT.md §21); its own file
if (existsSync(PY)) step('lineage fit checks', PY, ['tests/browser/lineage_fit_checks.py']);

// the lineage view's one link shape (a tree edge, a "+N" stub and a splice are the same curve) and extinct lines folded by default (docs/CONTRACT.md §21); its own file
if (existsSync(PY)) step('lineage links checks', PY, ['tests/browser/lineage_links_checks.py']);

// the app rail's three styles, toggle, persistence and resize, measured on the built kit (docs/CONTRACT.md §27); its own file
if (existsSync(PY)) step('rail checks', PY, ['tests/browser/rail_checks.py']);

// every chart's legend toggles its series (packages/core/src/legend.js; Zach, 2026-10-28); its own file, as the ones above
if (existsSync(PY)) step('legend checks', PY, ['tests/browser/legend_checks.py']);

// a property's declared digits / compact reach every cell that writes it (CONTRACT §17 "Declared rounding"): table cells,
// peek fields and embedded tables, groups, summaries, the rail, KPI ranges, hover cards and chips; their own files
if (existsSync(PY)) step('digits checks', PY, ['tests/browser/digits_checks.py']);
if (existsSync(PY)) step('digits sweep checks', PY, ['tests/browser/digits_sweep_checks.py']);

// the gallery index (site/gallery.js): pictures, the column slider, filters, the five layouts; its own file, as the ones above
if (existsSync(PY)) step('gallery checks', PY, ['tests/browser/gallery_checks.py']);
// the Views, Dashboards and Docs pages (site/docs-pages.mjs): live demos, the resizable sidebar, phone widths; its own file
if (existsSync(PY)) step('docs-site checks', PY, ['tests/browser/site_docs_checks.py']);
// the table view's drawn HTML against a golden from before its speed work (lane/perf-table)
if (existsSync(PY)) step('table oracle', PY, ['tests/browser/table_oracle_checks.py']);
// live data and rewind (docs/peps/0012-live-data.md, lane/live): following, scrub, back to live, the byte budget, the
// tail, SSE resume; its own file, with its own server (an SSE feed beside the files)
if (existsSync(PY)) step('live checks', PY, ['tests/browser/live_checks.py']);
// PEP 0010's P0 blockers (sim2real's gaps #1, #9, #13, #14 and the table's unreachable last rows), measured on
// tests/browser/fixtures/p0/; its own file, as the ones above
if (existsSync(PY)) step('P0 checks', PY, ['tests/browser/p0_checks.py']);
// a table with no rows says "No rows match this view.", not "No columns to show" (RobotParts' regression from the P0 table fix); its own file
if (existsSync(PY)) step('empty-table checks', PY, ['tests/browser/empty_table_checks.py']);
// the editable sheet (CONTRACT §37): cells edited in place, media cells, the add row, view changes kept through a reload by
// storage and by the page's hook, measured with the real mouse and keyboard; its own file, as the ones above
if (existsSync(PY)) step('editable-cells checks', PY, ['tests/browser/editable_cells_checks.py']);
// the notion table (CONTRACT §40, PEP 0016): the Edit / View switch, deleting rows, undo and redo, a pasted block, the column menu,
// measured with the real mouse, keyboard and clipboard on tests/browser/fixtures/notion-table/; its own file, as the ones above
if (existsSync(PY)) step('notion-table checks', PY, ['tests/browser/notion_table_checks.py']);
// notes as a table and as pages (CONTRACT §46): tools/serve-md.mjs over a copy of gallery/md-pages, the real mouse and keyboard, the
// result read from the files on disk; its own file, with its own server, as the live checks
if (existsSync(PY)) step('md-pages checks', PY, ['tests/browser/md_pages_checks.py']);
// a rich cell's `text` (CONTRACT §22): the producer's display string drawn in every view, the peek and the right-click
// popover, while sorting, filtering and Copy keep the value; its own file, as the ones above
if (existsSync(PY)) step('cell-text checks', PY, ['tests/browser/cell_text_checks.py']);
// `display: link` (CONTRACT §22): an http(s) URL or a relative path is an <a> labelled by the cell's text; another scheme,
// a bare id or javascript: is its label as plain text, in every view, the peek and the right-click popover; its own file
if (existsSync(PY)) step('link-text checks', PY, ['tests/browser/link_text_checks.py']);
// source precedence (CONTRACT §36, PEP 0015): a made-up part's datasheet with four sources and conflicts, the Nominal
// source column and its dropdown, Manage sources (a column per source, drag to reorder), the URL and storage state,
// light and dark at 1280 and 390 px, measured against an oracle over the fixture's JSON; its own file
if (existsSync(PY)) step('source-precedence checks', PY, ['tests/browser/source_precedence_checks.py']);
// the popover that lists every source of a value several sources state (CONTRACT §36, "the source popover"): a right-click,
// the menu key or a long-press in the table, the cards, the record page and the side peek; a pick through
// setPrecedence({ov}); today's menus for one source or none; light and dark at 1280 and 390 px; measured against an
// oracle over the fixtures' JSON and precedence.js pick() / conflict(); its own file, as the ones above
if (existsSync(PY)) step('source-popover checks', PY, ['tests/browser/source_popover_checks.py']);
// the Nominal source column on one-source data (CONTRACT §36): sourceColumn: true draws it, false never, undeclared as
// before; each row's one source under §22's link rule; measured on tests/browser/fixtures/source-column/; its own file
// the inspector (docs/CONTRACT.md "the inspector"): one property per row, 1:1 with the table's columns, N more properties, the two
// visibilities saved in the view; measured with the real mouse on three gallery cases and tests/browser/fixtures/inspector/; its own file
if (existsSync(PY)) step('inspector checks', PY, ['tests/browser/inspector_checks.py']);
if (existsSync(PY)) step('source-column checks', PY, ['tests/browser/source_column_checks.py']);
// a derived nominal names its source (CONTRACT §36): the Nominal source column names what a derived value came from, with
// a quiet "derived" mark, "—" only where nothing names one; measured on tests/browser/fixtures/source-column/derived.json
if (existsSync(PY)) step('source-derived checks', PY, ['tests/browser/source_derived_checks.py']);
// source columns (CONTRACT §36, PEP 0021): one property per source, Nominal a formula over them, a drag its precedence, hiding them only
// a view; a formula in Bases' syntax, editing, the inspector and robotparts' real datasheet, against an oracle over the fixtures' JSON
if (existsSync(PY)) step('source-columns checks', PY, ['tests/browser/source_columns_checks.py']);
// what the RobotParts agent found adopting the kit (CONTRACT §37, §28): persist="page" across pages that share a data id, and a header's
// words setting no floor, measured on its real source names at 1280 px
if (existsSync(PY)) step('robotparts-adoption checks', PY, ['tests/browser/robotparts_adoption_checks.py']);
// PEP 0010's P1b: scene3d's stage and Layer 1 primitives and trajectory3d (CONTRACT §32), measured on
// tests/browser/fixtures/p1b/, plus the old 3D cases through their own checks; its own file, as the ones above
if (existsSync(PY)) step('P1b checks', PY, ['tests/browser/p1b_checks.py']);
// PEP 0010's P1c: the Servo and Robot arm templates (gallery/examples/robotics-*) and their use-case group on the docs
// site, measured on dist/site against the cases' own files; its own file, as the ones above
if (existsSync(PY)) step('P1c checks', PY, ['tests/browser/p1c_checks.py']);
// PEP 0010's P1d: compare (arrows and Z-arcs from the difference rows against gallery/robotics/fixtures/difference, the
// display scale and its label, the templates' error panels, a rail hide in every panel); its own file, as the ones above
if (existsSync(PY)) step('P1d checks', PY, ['tests/browser/p1d_checks.py']);
// PEP 0010's P4: the BLDC driver, camera and arm + gripper templates (gallery/examples/robotics-driver, -camera,
// -arm-gripper), measured against numpy over the rack's archive (/archive/datasets/bam_rig) and the cases' own files;
// its own file, as the ones above
if (existsSync(PY)) step('P4 checks', PY, ['tests/browser/p4_checks.py']);
// PEP 0010's P2: coverage (voxels against numpy.histogramdd, opacity: auto exactly 1/n, the workspace outline, rules and
// bands from a property, the templates' coverage panels and a rail click at the deployment's 150,000 rows), measured on
// tests/browser/fixtures/p2/ and dist/site against numpy oracles and the rack's own npz; its own file, as the ones above
if (existsSync(PY)) step('P2 checks', PY, ['tests/browser/p2_checks.py']);
// the kit gaps the PEP 0010 template lanes found (P4, P2): aggregates after a swap, annotations from data and their labels,
// time charts on the clock, levels over a recording, colours of muted and null cells, a facet's parent, media empty text;
// measured on tests/browser/fixtures/kit_gaps/ and dist/site against numpy and the cases' files; its own file
if (existsSync(PY)) step('kit gaps checks', PY, ['tests/browser/kit_gaps_checks.py']);
// PEP 0010's P3: navigation (a per-run dataset loaded when one run is picked, one-way links, a selection preset in the
// .base, Back and Forward, the templates' runs tables picking a run), measured on gallery/examples/robotics-deployments,
// the templates and tests/browser/fixtures/p3/ against their files; its own file, as the ones above
if (existsSync(PY)) step('P3 checks', PY, ['tests/browser/p3_checks.py']);
// Add to dashboard (docs/CONTRACT.md §34): the menu item on every view, a KPI card, a legend's series and a peek field;
// the panel appended to a dashboard's text and drawn there with the same rows, below every panel; dedup and rename; the
// clipboard with no host; light and dark at 1280 and 390 px; measured on tests/browser/fixtures/add_to_dashboard/
if (existsSync(PY)) step('add-to-dashboard checks', PY, ['tests/browser/add_to_dashboard_checks.py']);
// RobotDx's five asks (RobotDx PEP 0001 §17.1; CONTRACT §26, §31, §34): the live plot's legend, the file a dashboard
// declares, a panel pinned on live data, the picker through a reload of its dashboard, t as a clock time; measured on
// tests/browser/fixtures/dx_asks/; its own file, with its own server (a host's PUT)
if (existsSync(PY)) step('dx asks checks', PY, ['tests/browser/dx_asks_checks.py']);
// Arrange keeps every panel its rows tall (packages/dashboard/src/arrange.js): a one-row Playback panel and a note were
// 0 px while arranging; measured on tests/browser/fixtures/arrange_fix/ after pressing Arrange and after a drag; its own file
if (existsSync(PY)) step('arrange checks', PY, ['tests/browser/arrange_checks.py']);
// the dashboard editor: Edit on the grid, the outline, one options pane, the queue, Save with its diff, every side panel, the
// keyboard alone, light and dark at 1280 and 390 px; real mouse and keys, measured against the text of
// tests/browser/fixtures/dash_editor/servo.base and a golden from before the editor; its own file, as the ones above
if (existsSync(PY)) step('dash editor checks', PY, ['tests/browser/dash_editor_checks.py']);
// the editor's paths that ruler does not walk: Add, a note, Duplicate, Plots, Visible, the rail, a per-pick dashboard, two on a page, a host's load()
if (existsSync(PY)) step('dash editor more checks', PY, ['tests/browser/dash_editor_more_checks.py']);
// RobotDx's second round (RobotDx PEP 0001 §18.4; CONTRACT §17, §26, §35): a live plot's limits from the store as of t, the
// roll-up as of t, no empty peek sections, a unit on a typed number column; measured on tests/browser/fixtures/dx_asks_2/
// against oracles over its files; its own file, with its own server
if (existsSync(PY)) step('dx asks 2 checks', PY, ['tests/browser/dx_asks_2_checks.py']);
// PEP 0010's P5: the diagnostics and gates overlay (gate matrices, status cells, the peek's evidence, limits, the roll-up
// tree, KPI trends, a keyed live dataset, the path overlay and verdict voxels; CONTRACT §35), measured on the six
// gallery/examples/robotics-*-gates twins and tests/browser/fixtures/p5/ against their files; its own file, as the ones above
if (existsSync(PY)) step('P5 checks', PY, ['tests/browser/p5_checks.py']);
// a map that picks (docs/CONTRACT.md §39): a marker, a table row and a card are one pick, marked in all three; a counted
// marker asks which; a preset settles after a pick upstream; the URL, Back and Forward, keyboard, light and dark at 1280 and
// 390 px, measured with a real mouse on gallery/examples/robotics-fleet against its files; its own file, as the ones above
if (existsSync(PY)) step('fleet map checks', PY, ['tests/browser/fleet_map_checks.py']);
// a preset settles on a pick, never on a word in a search facet (docs/CONTRACT.md §39); its own file, as the ones above
if (existsSync(PY)) step('settle search checks', PY, ['tests/browser/settle_search_checks.py']);
// select: on every clickable map layer (docs/CONTRACT.md §39, §42): a real click picks the rows behind a feature, the feature is
// marked in the pixels and comes back when cleared, wherever the pick came from; clusters, heatmaps, small multiples, the
// swipe, legends and a time bar on a clock; measured on tests/browser/fixtures/map_select/; its own file, as the ones above
if (existsSync(PY)) step('map select checks', PY, ['tests/browser/map_select_checks.py']);
// OpenStreetMap's credit on the map itself (docs/MAP-DATA.md): on every map that draws its data, on screen, unfolded after a drag,
// legible, at 1280 and 390 px, light and dark; the other map cases do not claim it; its own file, as the ones above
if (existsSync(PY)) step('map credit checks', PY, ['tests/browser/map_credit_checks.py']);
// column resize and nested groups on every table (docs/CONTRACT.md, PEP): a real mouse, measured, on
// tests/browser/fixtures/table-groups/ against its JSON; its own file, as the ones above
if (existsSync(PY)) step('table groups checks', PY, ['tests/browser/table_groups_checks.py']);
console.log('\n== summary');
// WHY below the heading: lanes add their steps above it, and this block stays out of their merges
if (strict) {
  for (const row of results) if (row[1].startsWith('SKIP') && !NEEDS[row[0]]) row[1] = `FAIL (--strict: ${row[1]})`;
  if (!existsSync(PY)) results.push(['browser suites', `FAIL (--strict: no Playwright Python at ${PY}, so none of them ran)`]);
}
for (const [name, r] of results) console.log(`${r.startsWith('pass') ? 'ok  ' : r.startsWith('SKIP') ? 'skip' : 'FAIL'} ${name}: ${r}${seconds[name] === undefined ? '' : ` (${seconds[name]} s)`}`);
const total = Object.values(seconds).reduce((a, b) => a + b, 0);
const skipped = results.filter(([, r]) => r.startsWith('SKIP'));
console.log(`node ${process.version}, ${results.length} parts, ${skipped.length} skipped, ${total} s in steps`);
if (process.env.DATA_UI_TEST_SUMMARY) {
  writeFileSync(process.env.DATA_UI_TEST_SUMMARY, JSON.stringify({ node: process.version, strict, total_seconds: total, results: results.map(([name, result]) => ({ name, result, seconds: seconds[name] ?? null })) }, null, 1) + '\n');
}
process.exitCode = results.some(([, r]) => r.startsWith('FAIL')) ? 1 : 0;
