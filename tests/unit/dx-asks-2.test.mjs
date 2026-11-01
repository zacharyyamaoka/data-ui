// RobotDx's second round of asks of data-ui (RobotDx PEP 0001 §18.4, found drawing each stock diagnostic in its view;
// docs/CONTRACT.md §17, §26, §35): the halves that run in Node. Written red, before the code; never edited after. The
// browser half is tests/browser/dx_asks_2_checks.py. Every oracle is the input rows themselves (the plain path over the
// same rows) or written out by hand from the tiny inputs here, never from the code under test.
//   ask 1: a live plot's limits from the store as of t: core live/window.js guideRows(ds, streams, a, b, columns,
//          {x, series}) hands guides.js the rows of a window, a few per run of each guide column's values, and the
//          guides drawn from them are the guides drawn from every row in (a, b]
//   ask 2: §17's roll-up reads the rows as of t: dashboard model.js applyRollups(dash, data, state, {t}) on live data
//   ask 3: an empty peek section is not drawn: core sections.js peekSections(view, props, row, {rowsOf})
//   ask 4: a typed number column keeps a cell's unit: core live/store.js
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { LiveDataset } = await import('../../packages/core/src/live/store.js');
const { guideRows } = await import('../../packages/core/src/live/window.js');
const { limitGuides, guidesFrom } = await import('../../packages/core/src/guides.js');
const { cellValue } = await import('../../packages/core/src/grammar.js');
const { peekSections } = await import('../../packages/core/src/sections.js');
const { parseBase } = await import('../../packages/core/src/base.js');
const { normalizeDataset } = await import('../../packages/core/src/data.js');
const M = await import('../../packages/dashboard/src/model.js');

const T0 = 1792631000;
const read = (r, c) => cellValue(r[c]);

// ------------------------------------------------------------------------------------------- ask 1: guide rows of a window

const LPROPS = { t: { type: 'number' }, check: { type: 'text' }, value: { type: 'number' }, warn_lo: { type: 'number' }, warn_hi: { type: 'number' },
  error_lo: { type: 'number' }, error_hi: { type: 'number' }, cap: {} };
const L4 = { warn: ['warn_lo', 'warn_hi'], error: ['error_lo', 'error_hi'] };

/** Three checks over 40 s at 10 Hz (several sealed chunks each): warn_hi steps 60 → 65 → 62, with a gap of nulls;
    error_hi constant; warn_lo only for `c`; `cap` an untyped column of rich cells that changes once. */
function readings() {
  const rows = [];
  for (let i = 0; i < 400; i++) {
    const t = T0 + i * 0.1;
    rows.push({ t, check: 'a', value: 40 + Math.sin(i / 9), warn_lo: null, warn_hi: i < 120 ? 60 : i < 200 ? 65 : i < 230 ? null : 62, error_lo: null, error_hi: 70, cap: { value: i < 300 ? 5 : 6, unit: 'A' } });
    rows.push({ t, check: 'b', value: 24 + Math.cos(i / 7), warn_lo: null, warn_hi: 26, error_lo: null, error_hi: 28, cap: { value: 5, unit: 'A' } });
    rows.push({ t, check: 'c', value: 3 + Math.sin(i / 5), warn_lo: i % 50 < 25 ? 1 : 1.5, warn_hi: null, error_lo: 0, error_hi: null, cap: null });
  }
  return rows;
}
const inWindow = (rows, a, b, streams) => rows.filter((r) => r.t > a && r.t <= b && (!streams || streams.includes(r.check)));
const live = (rows) => { const ds = new LiveDataset({ id: 'measures', properties: LPROPS, time: 't', stream: 'check' }); ds.append(rows); return ds; };
const COLS = ['warn_lo', 'warn_hi', 'error_lo', 'error_hi'];

test('guideRows: the limits drawn from a window\'s guide rows are the limits drawn from every row in (a, b], for windows that cut chunks anywhere', () => {
  const rows = readings();
  const ds = live(rows);
  const opts = { x: 't', series: 'check', read };
  for (const [a, b] of [[T0 - 1, T0 + 50], [T0 + 3.05, T0 + 13.05], [T0 + 11.95, T0 + 20.15], [T0 + 9.95, T0 + 10.05], [T0 + 21, T0 + 24], [T0 + 25.5, T0 + 39.9], [T0 + 10, T0 + 30]]) {
    const streams = ['a', 'b', 'c'];
    const got = limitGuides(guideRows(ds, streams, a, b, COLS, { x: 't', series: 'check' }), L4, opts);
    const want = limitGuides(inWindow(rows, a, b, streams), L4, opts);
    assert.deepEqual(got, want, `window (${a - T0}, ${b - T0}]`);
  }
});

test('guideRows: rules and bands from a property (guidesFrom) too, an untyped column of rich cells included', () => {
  const rows = readings();
  const ds = live(rows);
  const spec = { rules: [{ y: 'warn_hi', label: 'warn' }, { y: 'cap' }, { y: 99 }], bands: [{ y: ['error_lo', 'warn_lo'] }, { y: ['warn_hi', 'error_hi'] }] };
  for (const [a, b] of [[T0, T0 + 40], [T0 + 25, T0 + 35]]) {
    const got = guidesFrom(guideRows(ds, ['a', 'b', 'c'], a, b, ['warn_hi', 'cap', 'error_lo', 'warn_lo', 'error_hi'], { x: 't', series: 'check' }), spec, { x: 't', series: 'check', read });
    const want = guidesFrom(inWindow(rows, a, b), spec, { x: 't', series: 'check', read });
    assert.deepEqual(got, want, `window (${a - T0}, ${b - T0}]`);
  }
});

test('guideRows: a few rows per run, not one per sample; only the streams asked; none outside the window', () => {
  const rows = readings();
  const ds = live(rows);
  const got = guideRows(ds, ['b'], T0, T0 + 40, COLS, { x: 't', series: 'check' });
  // b's limits never change: its first and last sample in the window carry everything
  assert.ok(got.length <= 4, `${got.length} rows for 399 samples of constant limits`);
  assert.ok(got.every((r) => r.check === 'b' && r.t > T0 && r.t <= T0 + 40));
  assert.deepEqual([got[0].t, got[got.length - 1].t], [T0 + 0.1, T0 + 39.9].map((x) => rows.find((r) => r.check === 'b' && Math.abs(r.t - x) < 1e-9).t));
  // a's warn_hi changes three times (and has a gap): still a handful of rows
  const a = guideRows(ds, ['a'], T0, T0 + 40, COLS, { x: 't', series: 'check' });
  assert.ok(a.length <= 12, `${a.length} rows for a's three changes`);
  assert.deepEqual(guideRows(ds, ['a'], T0 + 100, T0 + 200, COLS, { x: 't', series: 'check' }), []);
});

test('guideRows: numbers only (no column) is each stream\'s first and last sample, so a number limit spans the drawn x', () => {
  const rows = readings();
  const ds = live(rows);
  const [a, b] = [T0 + 5.05, T0 + 15.05];
  const got = guideRows(ds, ['a', 'b'], a, b, [], { x: 't', series: 'check' });
  assert.ok(got.length <= 4);
  const lim = { warn: [null, 50], error: [null, 55] };
  assert.deepEqual(limitGuides(got, lim, { x: 't', series: 'check', read }), limitGuides(inWindow(rows, a, b, ['a', 'b']), lim, { x: 't', series: 'check', read }));
});

test('guideRows: [null] reads every stream as one series (rows without a series)', () => {
  const rows = readings();
  const ds = live(rows);
  const [a, b] = [T0 + 1.05, T0 + 31.05];
  const got = guideRows(ds, [null], a, b, COLS, { x: 't', series: null });
  assert.deepEqual(limitGuides(got, L4, { x: 't', series: null, read }), limitGuides(inWindow(rows, a, b), L4, { x: 't', series: null, read }));
});

test('guideRows: still the window\'s limits after rows arrive in the open chunk, out of order too', () => {
  const rows = readings();
  const ds = live(rows.slice(0, 600));   // up to T0 + 19.9 s
  const opts = { x: 't', series: 'check', read };
  const first = limitGuides(guideRows(ds, ['a', 'b', 'c'], T0, T0 + 50, COLS, { x: 't', series: 'check' }), L4, opts);
  assert.deepEqual(first, limitGuides(inWindow(rows.slice(0, 600), T0, T0 + 50), L4, opts));
  ds.append(rows.slice(600));
  // a late reading of a, placed in time order inside a's open chunk, with a limit no other row of a has
  const late = { t: T0 + 39.85, check: 'a', value: 41, warn_lo: null, warn_hi: 64, error_lo: null, error_hi: 70, cap: null };
  ds.append([late]);
  const all = [...rows, late];
  for (const [a, b] of [[T0, T0 + 50], [T0 + 30.05, T0 + 39.95]]) {
    assert.deepEqual(limitGuides(guideRows(ds, ['a', 'b', 'c'], a, b, COLS, { x: 't', series: 'check' }), L4, opts), limitGuides(inWindow(all, a, b), L4, opts), `window (${a - T0}, ${b - T0}]`);
  }
});

test('guideRows: a keyed dataset\'s versions in the window, by key', () => {
  const ds = new LiveDataset({ id: 'latest', properties: LPROPS, time: 't', key: 'check' });
  const rows = readings().filter((r) => r.check !== 'c');
  ds.upsert(rows);
  const [a, b] = [T0 + 8.05, T0 + 22.05];
  const got = guideRows(ds, ['a', 'b'], a, b, COLS, { x: 't', series: 'check' });
  assert.deepEqual(limitGuides(got, L4, { x: 't', series: 'check', read }), limitGuides(inWindow(rows, a, b), L4, { x: 't', series: 'check', read }));
});

// ------------------------------------------------------------------------------------------- ask 2: the roll-up as of t

const ROLL = `data: gates.json
datasets:
  gates:
    data: gates.json
    live: { time: t, key: id }
  components:
    data: components.json
    tree: { parent: parent }
    rollup: { from: gates, values: { worst: { property: rank, summary: Max } } }
  nodes:
    data: nodes.json
    live: { time: t, key: id }
    tree: { parent: parent }
    rollup: { from: gates, values: { worst: { property: rank, summary: Max } } }
links:
  - { from: gates.device, to: components.id }
  - { from: gates.device, to: nodes.id }
views:
  - { type: table, name: Components, from: components, tree: { parent: parent } }
  - { type: table, name: Nodes, from: nodes, tree: { parent: parent } }
`;
const TREE = [['rack', null], ['plate1', 'rack'], ['plate2', 'rack'], ['stationA', 'plate1'], ['stationB', 'plate1'], ['stationC', 'plate2']];
const TPROPS = { id: { type: 'text' }, t: { type: 'number' }, parent: { type: 'text' }, worst: { type: 'number' } };
const GPROPS = { id: { type: 'text' }, t: { type: 'number' }, device: { type: 'text' }, rank: { type: 'number' } };
// each a new version of its station's one gate: A, B, C pass at 1 s; B warns at 10 s; C fails at 20 s; B passes again at 30 s
const GATES = [[1, 'stationA', 0], [1, 'stationB', 0], [1, 'stationC', 0], [10, 'stationB', 1], [20, 'stationC', 4], [30, 'stationB', 0]]
  .map(([dt, d, rank]) => ({ id: `${d}#temp`, t: T0 + dt, device: d, rank }));

function rollData() {
  const gates = new LiveDataset({ id: 'gates', properties: GPROPS, time: 't', key: 'id' });
  const nodes = new LiveDataset({ id: 'nodes', properties: TPROPS, time: 't', key: 'id', rows: TREE.map(([id, parent]) => ({ id, t: T0, parent })) });
  const components = normalizeDataset({ id: 'components', properties: TPROPS, rows: TREE.map(([id, parent]) => ({ id, parent })) });
  gates.upsert(GATES);
  nodes.upsert([{ id: 'stationC', t: T0 + 25, parent: 'plate1' }]);   // station C moves under plate 1 at 25 s
  return { gates, nodes, components };
}
const worst = (out, name) => Object.fromEntries(Object.entries(out[name].worst).map(([id, c]) => [id, c.value]));

test('applyRollups at t: each node\'s worst is the gates\' newest versions at t under it, on a file\'s tree and on a live tree as of t (hand-computed)', () => {
  const dash = M.readDashboard(parseBase(ROLL));
  const data = rollData();
  const state = { rail: {}, select: {} };
  const at = (dt) => M.applyRollups(dash, data, state, { t: T0 + dt });
  let out = at(5.5);
  assert.deepEqual(worst(out, 'components'), { rack: 0, plate1: 0, plate2: 0, stationA: 0, stationB: 0, stationC: 0 });
  assert.deepEqual(worst(out, 'nodes'), { rack: 0, plate1: 0, plate2: 0, stationA: 0, stationB: 0, stationC: 0 });
  out = at(15.5);
  assert.deepEqual(worst(out, 'components'), { rack: 1, plate1: 1, plate2: 0, stationA: 0, stationB: 1, stationC: 0 });
  out = at(22.5);
  assert.deepEqual(worst(out, 'components'), { rack: 4, plate1: 1, plate2: 4, stationA: 0, stationB: 1, stationC: 4 });
  assert.deepEqual(worst(out, 'nodes'), { rack: 4, plate1: 1, plate2: 4, stationA: 0, stationB: 1, stationC: 4 });
  out = at(27.5);
  // the live tree at 27.5 s: station C is under plate 1, so plate 2 has no gate under it
  assert.deepEqual(worst(out, 'nodes'), { rack: 4, plate1: 4, plate2: null, stationA: 0, stationB: 1, stationC: 4 });
  assert.equal(out.nodes.worst.plate2.why, 'no gates rows');
  out = at(0.5);
  assert.deepEqual(worst(out, 'components'), { rack: null, plate1: null, plate2: null, stationA: null, stationB: null, stationC: null }, 'before any gate');
  // back to a later t: it moves forward again (nothing is left over from an earlier t)
  out = at(35);
  assert.deepEqual(worst(out, 'components'), { rack: 4, plate1: 0, plate2: 4, stationA: 0, stationB: 0, stationC: 4 });
  assert.deepEqual(worst(out, 'nodes'), { rack: 4, plate1: 4, plate2: null, stationA: 0, stationB: 0, stationC: 4 });
});

test('applyRollups at t writes its cells onto the rows the views read at t (a file\'s rows; a live tree\'s versions at t)', () => {
  const dash = M.readDashboard(parseBase(ROLL));
  const data = rollData();
  M.applyRollups(dash, data, { rail: {}, select: {} }, { t: T0 + 15.5 });
  assert.equal(cellValue(data.components.rows.find((r) => r.id === 'rack').worst), 1);
  const nodesAt = data.nodes.snapshot(T0 + 15.5, { at: 'all', limit: Infinity });
  assert.equal(cellValue(nodesAt.find((r) => r.id === 'plate1').worst), 1);
  assert.equal(nodesAt.find((r) => r.id === 'plate1').worst.basis, 'derived');
  M.applyRollups(dash, data, { rail: {}, select: {} }, { t: T0 + 27.5 });
  const later = data.nodes.snapshot(T0 + 27.5, { at: 'all', limit: Infinity });
  assert.equal(cellValue(later.find((r) => r.id === 'plate1').worst), 4, 'the tree as of 27.5 s: C is under plate 1');
  assert.equal(cellValue(later.find((r) => r.id === 'stationC').worst), 4, 'C\'s own version at 27.5 s carries the cell');
});

test('applyRollups without t on live data reads the newest rows, as before; a file reads its rows whatever t is', () => {
  const dash = M.readDashboard(parseBase(ROLL));
  const data = rollData();
  const out = M.applyRollups(dash, data, { rail: {}, select: {} });
  assert.deepEqual(worst(out, 'components'), { rack: 4, plate1: 0, plate2: 4, stationA: 0, stationB: 0, stationC: 4 });
  // a plain source and a plain target: t changes nothing
  const plain = { gates: normalizeDataset({ id: 'gates', properties: GPROPS, rows: GATES.slice(0, 3) }), components: data.components, nodes: data.nodes };
  const a = M.applyRollups(dash, plain, { rail: {}, select: {} }, { t: T0 - 100 });
  assert.deepEqual(worst(a, 'components'), { rack: 0, plate1: 0, plate2: 0, stationA: 0, stationB: 0, stationC: 0 });
});

test('applyRollups at t: an append source reads its rows at or before t', () => {
  const dash = M.readDashboard(parseBase(ROLL.replace('    live: { time: t, key: id }\n  components', '    live: { time: t, stream: device }\n  components')));
  const gates = new LiveDataset({ id: 'gates', properties: GPROPS, time: 't', stream: 'device' });
  gates.append(GATES);
  const data = { ...rollData(), gates };
  const out = M.applyRollups(dash, data, { rail: {}, select: {} }, { t: T0 + 15.5 });
  // every row at or before 15.5 s (an append dataset keeps them all): B's warn at 10 s is the worst under plate 1
  assert.deepEqual(worst(out, 'components'), { rack: 1, plate1: 1, plate2: 0, stationA: 0, stationB: 1, stationC: 0 });
});

// ------------------------------------------------------------------------------------------- ask 3: empty peek sections

const PEEK_VIEW = { record: { sections: [
  { name: 'Level', properties: ['level', 'message'] },
  { name: 'Measured', properties: ['metric', 'value', 'unit'] },
  { name: 'Evidence', properties: ['t0', 't1', 'run'], view: { type: 'table', from: 'parts', filters: 'check == this.id' } },
  { name: 'Stock diagnostic', properties: ['diagnostic', 'hint', 'role'] },
  { name: 'Notes', properties: ['note'] },
] } };
const PPROPS = Object.fromEntries(['level', 'message', 'metric', 'value', 'unit', 't0', 't1', 'run', 'diagnostic', 'hint', 'role', 'note'].map((id) => [id, { id, label: id }]));
const EMPTY = { metric: null, value: null, unit: null, t0: null, t1: null, run: null, diagnostic: null, hint: null, role: null, note: null };
const PEEK_ROWS = {
  stock: { id: 'stock', level: 'warn', message: 'above', metric: 'board_temp', value: 61.2, unit: 'Cel', t0: 1, t1: 2, run: 'r1', diagnostic: 'driver.board_temp', hint: 'threshold_band', role: 'health', note: 'ok' },
  plain: { id: 'plain', level: 'ok', message: 'alive', ...EMPTY, note: { value: null, why: 'not measured on this host' } },
  evidence: { id: 'evidence', level: 'ok', message: 'within', ...EMPTY, value: '', run: [] },
};
// how many rows each bound evidence view shows, written out by hand (parts: three for stock, two for evidence)
const PARTS = { 'check == "stock"': 3, 'check == "evidence"': 2, 'check == "plain"': 0 };
const rowsOf = (view) => PARTS[view.filters] ?? 0;
const names = (s) => s.map((x) => x.name);

test('peekSections with rowsOf: a section with no field value and no row in its view is left out; a reason is a value', () => {
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.plain, { rowsOf })), ['Level', 'Notes'], 'the plain check: its level, and a note saying why it has none');
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.stock, { rowsOf })), ['Level', 'Measured', 'Evidence', 'Stock diagnostic', 'Notes']);
  // no evidence fields ('' and [] are no value either), but its view has two rows: the section stays
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.evidence, { rowsOf })), ['Level', 'Evidence']);
});

test('peekSections: a view whose rows cannot be told (rowsOf null) keeps its section; without rowsOf every section stays, as before', () => {
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.plain, { rowsOf: () => null })), ['Level', 'Evidence', 'Notes']);
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.plain)), ['Level', 'Measured', 'Evidence', 'Stock diagnostic', 'Notes']);
  // a section kept keeps every field it lists, empty ones too (drawn "—")
  const s = peekSections(PEEK_VIEW, PPROPS, PEEK_ROWS.evidence, { rowsOf });
  assert.deepEqual(s.find((x) => x.name === 'Evidence').list.map((p) => p.id), ['t0', 't1', 'run']);
  assert.equal(s.find((x) => x.name === 'Evidence').view.filters, 'check == "evidence"');
});

test('peekSections: 0 and false are values', () => {
  const row = { id: 'z', level: 'ok', message: null, ...EMPTY, value: 0, diagnostic: false };
  assert.deepEqual(names(peekSections(PEEK_VIEW, PPROPS, row, { rowsOf })), ['Level', 'Measured', 'Stock diagnostic']);
});

// ------------------------------------------------------------------------------------------- ask 4: a unit on a typed number column

const UPROPS = { t: { type: 'number' }, check: { type: 'text' }, reading: { type: 'number' }, note: { type: 'text' } };

test('a rich cell in a typed number column keeps its unit (and the rest of it) in an append dataset; range() reads its value', () => {
  const ds = new LiveDataset({ id: 'm', properties: UPROPS, time: 't', stream: 'check' });
  const cell = { value: 0.5, unit: '%', basis: 'measured', n: 3 };
  ds.append([{ t: T0, check: 'a', reading: cell }, { t: T0 + 1, check: 'a', reading: 0.7 }, { t: T0 + 2, check: 'a', reading: { value: null, why: 'not measured' } }, { t: T0 + 3, check: 'a', reading: { value: 0.9, unit: '%' } }]);
  const rows = ds.snapshot(Infinity, { limit: 10 }).reverse();
  assert.deepEqual(rows.map((r) => r.reading), [cell, 0.7, { value: null, why: 'not measured' }, { value: 0.9, unit: '%' }]);
  assert.deepEqual(ds.latestAt(T0 + 0.5, 'a').reading, cell);
  assert.deepEqual(ds.newRows(0).map((r) => cellValue(r.reading)), [0.5, 0.7, null, 0.9]);
  const [part] = ds.range(T0 - 1, T0 + 10, { stream: 'a', columns: ['reading'] });
  assert.deepEqual(Array.from(part.cols.reading).map((v) => (Number.isNaN(v) ? null : v)), [0.5, 0.7, null, 0.9]);
});

test('a typed number column\'s rich cells stay with their rows through growing, sealing, an out-of-order row and appendColumns', () => {
  const ds = new LiveDataset({ id: 'm', properties: UPROPS, time: 't', stream: 'check' });
  const rows = [];
  for (let i = 0; i < 300; i++) rows.push({ t: T0 + i * 0.1, check: 'a', reading: i % 3 ? i : { value: i, unit: i % 2 ? 'V' : 'mV' } });
  ds.append(rows);   // 30 s: sealed chunks (10 s each) and an open one, grown past its first 16 slots
  const late = { t: T0 + 29.75, check: 'a', reading: { value: -1, unit: 'kV' } };
  ds.append([late]);   // inside the open chunk, before its newest rows
  const want = [...rows, late].sort((x, y) => x.t - y.t).map((r) => r.reading);
  assert.deepEqual(ds.snapshot(Infinity, { limit: 1000 }).reverse().map((r) => r.reading), want);
  ds.appendColumns({ t: [T0 + 40, T0 + 41], reading: [{ value: 7, unit: 'A' }, 8] }, { stream: 'a' });
  assert.deepEqual(ds.snapshot(Infinity, { limit: 2 }).reverse().map((r) => r.reading), [{ value: 7, unit: 'A' }, 8]);
});

test('a keyed dataset\'s range() reads a number column\'s values, never its cell objects (its rows keep the cells, as before)', () => {
  const ds = new LiveDataset({ id: 'k', properties: UPROPS, time: 't', key: 'check' });
  ds.upsert([{ t: T0, check: 'a', reading: { value: 0.5, unit: '%' } }, { t: T0 + 1, check: 'a', reading: { value: 0.6, unit: '%' } }, { t: T0 + 1, check: 'b', reading: 2 }]);
  const parts = ds.range(T0 - 1, T0 + 5, { columns: ['reading'] });
  assert.deepEqual(parts.map((p) => [p.stream, Array.from(p.cols.reading)]), [['a', [0.5, 0.6]], ['b', [2]]]);
  assert.deepEqual(ds.latestAt(Infinity, 'a').reading, { value: 0.6, unit: '%' });
});
