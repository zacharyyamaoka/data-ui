// Add to dashboard (docs/CONTRACT.md §34): appendPanel's half, pure, and both checkers on what it writes and on the two
// keys the feature adds. Zach, 2026-10-29: "Dashboards are built with data-ui. Humans curate, AI builds." A reader adds
// a panel from any view of the data, "like the amazon thing of adding to a saved list"; it goes to the BOTTOM of the
// chosen dashboard, to be arranged later. data-ui never writes the file: appendPanel(baseText, panel, {title, base})
// returns the new text and the host saves it.
//
// What is held here (tests/browser/add_to_dashboard_checks.py measures the same in the page):
//   - every line of the dashboard comes back as written and in order; only lines are inserted (a block written in flow
//     style is the one exception, rewritten in block style), CRLF stays CRLF, a missing final newline stays missing;
//   - the panel is the last of layout.panels, full width (no w), with the source's h, t and title;
//   - a dataset is found by its file (resolved against the dashboard's own URL), so the same file is never added twice;
//     a name taken by another file, and a view name taken, get a suffix; a panel whose key would be taken gets its own;
//   - an empty text is a new, valid dashboard (its title a comment on the first line);
//   - properties: entries the dashboard lacks are added, its own are kept;
//   - what is not a .base file is refused with a reason;
//   - data-ui check and tools/check_views.py accept the output, and both read hiddenSeries (a view's legend, hidden when
//     it opens) and a panel's t (the instant it stands at) from schemas/view.schema.json.
// The fixture is tests/browser/fixtures/add_to_dashboard/ (target.base and its data; source.base for the checkers).
// Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { appendPanel } from '../../packages/core/src/add-to-dashboard.js';
import { parseBase } from '../../packages/core/src/base.js';
import { readDashboard } from '../../packages/dashboard/src/model.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'tests', 'browser', 'fixtures', 'add_to_dashboard');
const TARGET = readFileSync(join(FIX, 'target.base'), 'utf8');
const SOURCE = readFileSync(join(FIX, 'source.base'), 'utf8');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;
// where the target dashboard is served from, and the fixture's folder from the site's root
const BASE = 'http://127.0.0.1:4610/tests/browser/fixtures/add_to_dashboard/target.base';
const DIR = '/tests/browser/fixtures/add_to_dashboard/';

// the panel a reader's "Add to dashboard…" hands over: the view entry, the dataset it reads and that dataset's file
const runsPanel = (over = {}) => ({
  kind: 'view', title: 'Runs',
  view: { type: 'table', name: 'Runs', order: ['run', 'robot', 'success'], filters: 'robot == "B"' },
  dataset: { name: 'runs', data: `${DIR}runs.json` },
  ...over,
});
const samplesPanel = (over = {}) => ({
  kind: 'view', title: 'Error by joint',
  view: { type: 'timeseries', name: 'Error by joint', filters: 'run == "r02"', timeseries: { x: 't', y: 'err_mm', series: 'joint' } },
  dataset: { name: 'samples', data: `${DIR}samples.json` },
  ...over,
});

/** Every line of `before` is in `after`, unchanged and in order (a subsequence); returns the lines `after` added. */
function inserted(before, after, eol = '\n') {
  const a = before.split(eol), b = after.split(eol);
  const added = [];
  let i = 0;
  for (const line of b) { if (i < a.length && line === a[i]) i++; else added.push(line); }
  assert.equal(i, a.length, `line ${i + 1} of the original ("${a[i]}") is not in the new text, unchanged and in order`);
  assert.equal(added.length, b.length - a.length);
  return added;
}
const lastPanel = (text) => { const d = readDashboard(parseBase(text)); return d.panels[d.panels.length - 1]; };
const rawPanels = (text) => parseBase(text).layout.panels;
const datasetsOf = (text) => Object.fromEntries(Object.entries(parseBase(text).datasets || {}).map(([k, v]) => [k, typeof v === 'string' ? v : v.data]));

test('appendPanel keeps every line of the dashboard as written and puts the panel last', () => {
  const before = readDashboard(parseBase(TARGET));
  const out = appendPanel(TARGET, runsPanel(), { base: BASE });
  const added = inserted(TARGET, out);
  assert.ok(added.some((l) => /^ {4}- \{.*view: Runs \(2\)/.test(l)), `the panel line is added: ${JSON.stringify(added)}`);
  const lines = out.split('\n');
  const after = lines.findIndex((l) => l.includes('- { view: Other samples, w: 6, h: 3 }'));
  assert.match(lines[after + 1], /view: Runs \(2\)/, 'the panel goes right after the last panel, before the comment that follows it');
  const dash = readDashboard(parseBase(out));
  assert.deepEqual(dash.problems, []);
  assert.equal(dash.panels.length, before.panels.length + 1);
  const last = dash.panels[dash.panels.length - 1];
  assert.equal(last.views.length, 1);
  assert.equal(last.views[0].name, 'Runs (2)', 'the target has a view called Runs: the added one takes a suffix');
  assert.equal(last.title, 'Runs', 'the panel keeps the title it had where it came from');
  assert.equal(last.views[0].type, 'table');
  assert.equal(last.views[0].filters, 'robot == "B"');
  assert.deepEqual(last.views[0].order, ['run', 'robot', 'success']);
  assert.equal(last.w, dash.columns, 'an added panel is full width, so it sits below every panel');
  assert.equal(rawPanels(out).at(-1).w, undefined, 'no w is written');
  // runs.json is the target's `fleet`: the same file, so no dataset is added and the view reads fleet
  assert.equal(last.views[0].from, 'fleet');
  assert.deepEqual(datasetsOf(out), datasetsOf(TARGET));
});

test('a dataset is matched by its file, not its name: a name another file holds gets a suffix', () => {
  const out = appendPanel(TARGET, samplesPanel(), { base: BASE });
  inserted(TARGET, out);
  const ds = datasetsOf(out);
  assert.equal(ds.samples, 'other-samples.json', 'the target\'s own samples stay as they were');
  assert.equal(ds.samples_2, 'samples.json', 'the source\'s samples come in under a name of their own, relative to the dashboard');
  assert.equal(Object.keys(ds).length, Object.keys(datasetsOf(TARGET)).length + 1);
  const last = lastPanel(out);
  assert.equal(last.views[0].from, 'samples_2');
  assert.equal(last.views[0].name, 'Error by joint');
  assert.equal(rawPanels(out).at(-1).title, undefined, 'a title equal to the view\'s name is not repeated');
  // the new dataset line sits under the datasets the file had, before the blank line that ends the block
  const lines = out.split('\n');
  const at = lines.findIndex((l) => /^ {2}samples_2: samples\.json$/.test(l));
  assert.ok(at > 0 && /other-samples\.json/.test(lines[at - 1]) && lines[at + 1] === '', lines.slice(at - 1, at + 2).join(' | '));
});

test('the file at the top level\'s data: is a dataset too: the same file is read through it', () => {
  const text = '# one dataset\ndata: runs.json\nviews:\n  - type: table\n    name: All runs\nlayout:\n  panels:\n    - { view: All runs }\n';
  const out = appendPanel(text, runsPanel(), { base: BASE });
  inserted(text, out);
  const last = lastPanel(out);
  const dash = readDashboard(parseBase(out));
  assert.equal(last.views[0].from, dash.defaultName, 'the view reads the default dataset (runs, by its file stem)');
  assert.equal(parseBase(out).datasets, undefined, 'no datasets: block is written for it');
});

test('adding the same panel twice: "Runs (3)", and still no second dataset for one file', () => {
  const once = appendPanel(TARGET, runsPanel(), { base: BASE });
  const twice = appendPanel(once, runsPanel(), { base: BASE });
  inserted(once, twice);
  const dash = readDashboard(parseBase(twice));
  assert.deepEqual(dash.panels.slice(-2).map((p) => p.views[0].name), ['Runs (2)', 'Runs (3)']);
  assert.deepEqual(datasetsOf(twice), datasetsOf(TARGET));
  const keys = dash.panels.map((p) => p.key);
  assert.equal(new Set(keys).size, keys.length, `every panel has its own key: ${keys}`);
});

test('an added panel whose key would be taken gets one of its own, so moving it never swaps two panels\' keys', () => {
  const out = appendPanel(TARGET, runsPanel(), { base: BASE });
  const doc = parseBase(out);
  const added = doc.layout.panels.at(-1);
  assert.equal(typeof added.key, 'string', 'the target has a panel keyed runs (its view Runs): the added one, titled Runs, says its key');
  const before = readDashboard(doc).panels.map((p) => [p.views[0].name, p.key]);
  // a reader arranges it first (Arrange writes the reading order): every panel keeps the key it had
  const moved = { ...doc, layout: { ...doc.layout, panels: [added, ...doc.layout.panels.slice(0, -1)] } };
  const after = readDashboard(moved).panels.map((p) => [p.views[0].name, p.key]);
  assert.deepEqual(Object.fromEntries(after), Object.fromEntries(before));
});

test('an empty text is a new dashboard: its title a comment on the first line, the dataset, the view and the panel', () => {
  const out = appendPanel('', runsPanel(), { title: 'Incidents', base: BASE });
  assert.equal(out.split('\n')[0], '# Incidents');
  const doc = parseBase(out);
  const dash = readDashboard(doc);
  assert.deepEqual(dash.problems, []);
  assert.equal(dash.panels.length, 1);
  assert.deepEqual(datasetsOf(out), { runs: 'runs.json' });
  assert.equal(dash.panels[0].views[0].name, 'Runs');
  assert.equal(dash.panels[0].views[0].from, 'runs');
  // with no base the file is named as the panel has it (from the site's root)
  const loose = appendPanel('', runsPanel(), { title: 'Incidents' });
  assert.deepEqual(datasetsOf(loose), { runs: `${DIR}runs.json` });
  // whitespace and comments only are empty too, and kept
  const lead = '# a note\n\n';
  const kept = appendPanel(lead, runsPanel(), { base: BASE });
  inserted(lead, kept);
  assert.equal(readDashboard(parseBase(kept)).panels.length, 1);
});

test('the file is written relative to the dashboard on the same origin, absolute on another', () => {
  const at = (data, base) => datasetsOf(appendPanel('', runsPanel({ dataset: { name: 'runs', data } }), { base })).runs;
  assert.equal(at('/a/data/runs.json', 'http://h.test/a/dash/x.base'), '../data/runs.json');
  assert.equal(at('/a/dash/runs.json', 'http://h.test/a/dash/x.base'), 'runs.json');
  assert.equal(at('/a/dash/sub/runs.json', 'http://h.test/a/dash/x.base'), 'sub/runs.json');
  assert.equal(at('http://h.test/a/runs.json', 'http://h.test/a/dash/x.base'), '../runs.json');
  assert.equal(at('https://other.test/runs.json', 'http://h.test/a/dash/x.base'), 'https://other.test/runs.json');
  assert.equal(at('/a/data/runs.json?v=2', 'http://h.test/a/dash/x.base'), '../data/runs.json?v=2');
});

test('blocks the file lacks are added; a block in flow style is rewritten, every other line kept', () => {
  // views, no datasets and no layout: datasets: before views:, layout: at the end
  const plain = 'data: other-samples.json\nviews:\n  - type: table\n    name: Other\n';
  const a = appendPanel(plain, samplesPanel(), { base: BASE });
  inserted(plain, a);
  assert.ok(a.indexOf('datasets:') < a.indexOf('views:'), a);
  assert.equal(lastPanel(a).views[0].from, 'samples');
  assert.deepEqual(rawPanels(a).map((p) => p.view), ['Error by joint'], 'a file with no layout gets one, holding the panel');
  // layout with no panels: panels: under layout:
  const bare = 'datasets:\n  fleet: runs.json\nviews:\n  - type: table\n    name: Runs\n    from: fleet\nlayout:\n  columns: 12\n';
  const b = appendPanel(bare, samplesPanel(), { base: BASE });
  inserted(bare, b);
  assert.equal(parseBase(b).layout.columns, 12);
  assert.deepEqual(rawPanels(b).map((p) => p.view), ['Error by joint']);
  // no views at all (a text panel): views: before layout:
  const text = 'datasets:\n  fleet: runs.json\nlayout:\n  panels:\n    - { text: "# Notes" }\n';
  const c = appendPanel(text, runsPanel(), { base: BASE });
  inserted(text, c);
  assert.ok(c.indexOf('views:') < c.indexOf('layout:'), c);
  assert.equal(lastPanel(c).views[0].from, 'fleet');
  // flow style: datasets on one line and panels as a flow list; only those lines change
  const flow = '# flow\ndatasets: { fleet: runs.json }\nviews:\n  - type: table\n    name: Runs\n    from: fleet\nlayout: { columns: 12, panels: [{ view: Runs }] }\n';
  const d = appendPanel(flow, samplesPanel(), { base: BASE });
  const dash = readDashboard(parseBase(d));
  assert.deepEqual(dash.problems, []);
  assert.deepEqual(datasetsOf(d), { fleet: 'runs.json', samples: 'samples.json' });
  assert.deepEqual(dash.panels.map((p) => p.views[0].name), ['Runs', 'Error by joint']);
  for (const line of ['# flow', 'views:', '  - type: table', '    name: Runs', '    from: fleet']) assert.ok(d.split('\n').includes(line), `kept: ${line}`);
});

test('line endings: CRLF stays CRLF, and a file that does not end in a newline still does not', () => {
  const crlf = TARGET.replace(/\n/g, '\r\n');
  const out = appendPanel(crlf, samplesPanel(), { base: BASE });
  inserted(crlf, out, '\r\n');
  assert.doesNotMatch(out.replace(/\r\n/g, ''), /\n/, 'no bare LF');
  const open = TARGET.replace(/\n+$/, '');
  const out2 = appendPanel(open, runsPanel(), { base: BASE });
  inserted(open, out2);
  assert.ok(!out2.endsWith('\n'), 'no newline is added at the end');
  assert.equal(lastPanel(out2).views[0].name, 'Runs (2)');
});

test('the panel carries its height, the instant it stands at and a title; the view its hidden series', () => {
  const panel = samplesPanel({ title: 'Error by joint · J2', h: 3, t: 1.25,
    view: { ...samplesPanel().view, name: 'Error by joint · J2', hiddenSeries: ['J1', 'J3'] } });
  const out = appendPanel(TARGET, panel, { base: BASE });
  inserted(TARGET, out);
  const raw = rawPanels(out).at(-1);
  assert.equal(raw.h, 3);
  assert.equal(raw.t, 1.25);
  assert.equal(raw.w, undefined);
  const last = lastPanel(out);
  assert.deepEqual(last.views[0].hiddenSeries, ['J1', 'J3']);
  assert.equal(last.views[0].name, 'Error by joint · J2');
});

test('properties: entries the dashboard lacks are added; its own are kept as written', () => {
  const out = appendPanel(TARGET, runsPanel({ properties: { robot: { displayName: 'Robot (from the source)' }, success: { displayName: 'Success rate' } } }), { base: BASE });
  inserted(TARGET, out);
  const props = parseBase(out).properties;
  assert.deepEqual(props.robot, { displayName: 'Robot' });
  assert.deepEqual(props.success, { displayName: 'Success rate' });
});

test('what is not a .base file is refused with a reason, never overwritten', () => {
  assert.throws(() => appendPanel('- a\n- b\n', runsPanel(), { base: BASE }), /mapping|\.base/i);
  assert.throws(() => appendPanel('views: [\n', runsPanel(), { base: BASE }), /line \d/);
  assert.throws(() => appendPanel(TARGET, { kind: 'view', title: 'x', dataset: { name: 'runs', data: 'runs.json' } }, { base: BASE }), /view/);
});

// ------------------------------------------------------------------ the checkers

/** A copy of the fixture folder with `name` written in it; the file's path. */
function written(name, text) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-a2d-'));
  cpSync(FIX, dir, { recursive: true });
  const path = join(dir, name);
  writeFileSync(path, text);
  return path;
}
function node(path) {
  const r = spawnSync('node', [CLI, 'check', path, '--json'], { cwd: ROOT, maxBuffer: 64 << 20 });
  return JSON.parse(r.stdout.toString());
}
function python(path) {
  const r = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), path], { cwd: ROOT });
  const out = r.stdout.toString();
  const m = /(\d+) errors, (\d+) warnings/.exec(out);
  assert.ok(m, out + r.stderr.toString());
  return { errors: Number(m[1]), warnings: Number(m[2]), out };
}
const swap = (text, from, to) => { assert.equal(text.split(from).length, 2, `'${from}' is in the fixture exactly once`); return text.replace(from, to); };
const lineOf = (text, needle) => text.split('\n').findIndex((l) => l.includes(needle)) + 1;

test('data-ui check and tools/check_views.py accept what appendPanel writes, and read the data it names', () => {
  const base = 'http://h.test/fix/out.base';
  const texts = [
    appendPanel(appendPanel(TARGET, runsPanel({ dataset: { name: 'runs', data: '/fix/runs.json' } }), { base }), samplesPanel({ dataset: { name: 'samples', data: '/fix/samples.json' } }), { base }),
    appendPanel('', runsPanel({ dataset: { name: 'runs', data: '/fix/runs.json' } }), { title: 'Incidents', base }),
  ];
  for (const text of texts) {
    const path = written('out.base', text);
    const r = node(path);
    assert.equal(r.errors, 0, JSON.stringify(r.problems));
    assert.ok(!r.problems.some((p) => /unknown|did you mean/i.test(p.message)), JSON.stringify(r.problems));
    // the views were checked against the files the text names (the summary lists each file it read)
    const summary = spawnSync('node', [CLI, 'check', path], { cwd: ROOT }).stdout.toString();
    assert.match(summary, /against [^\n]*runs\.json/, summary);
    if (HAS_PY) assert.equal(python(path).errors, 0, python(path).out);
  }
});

test('both checkers read hiddenSeries on a view and t on a panel from the schema, and refuse the wrong shapes at their line', () => {
  const view = '    timeseries: { x: t, y: err_mm, series: joint }';
  const panel = '    - { view: Tool paths, w: 6, h: 3 }';
  const good = swap(swap(SOURCE, view, `${view}\n    hiddenSeries: [J1, J3]`), panel, '    - { view: Tool paths, w: 6, h: 3, t: 1.5 }');
  const p = written('good.base', good);
  const r = node(p);
  assert.equal(r.errors, 0, JSON.stringify(r.problems));
  assert.equal(r.warnings, 0, JSON.stringify(r.problems));
  if (HAS_PY) { const q = python(p); assert.equal(q.errors + q.warnings, 0, q.out); }
  const notList = swap(SOURCE, view, `${view}\n    hiddenSeries: J3`);
  const r2 = node(written('a.base', notList));
  assert.ok(r2.problems.some((x) => x.level === 'error' && x.line === lineOf(notList, 'hiddenSeries: J3')), JSON.stringify(r2.problems));
  const notNum = swap(SOURCE, panel, '    - { view: Tool paths, w: 6, h: 3, t: soon }');
  const r3 = node(written('b.base', notNum));
  assert.ok(r3.problems.some((x) => x.level === 'error' && x.line === lineOf(notNum, 't: soon')), JSON.stringify(r3.problems));
  if (HAS_PY) {
    const a = written('a.base', notList), b = written('b.base', notNum);
    const qa = python(a), qb = python(b);
    assert.ok(qa.errors >= 1 && new RegExp(`a\\.base:${lineOf(notList, 'hiddenSeries: J3')}: error`).test(qa.out), qa.out);
    assert.ok(qb.errors >= 1 && new RegExp(`b\\.base:${lineOf(notNum, 't: soon')}: error`).test(qb.out), qb.out);
  }
});

test('@data-ui/core exports appendPanel (a host appends without the element)', () => {
  const src = readFileSync(join(ROOT, 'packages', 'core', 'src', 'index.js'), 'utf8');
  assert.match(src, /export \{[^}]*\bappendPanel\b[^}]*\} from '\.\/add-to-dashboard\.js'/);
});
