// PEP 0010 P5: the gate matrix's model (packages/views/kpi/src/stat-model.js `matrixCells`; docs/CONTRACT.md §35,
// sim2real gap #11), a property KPI target (`targetValue`), and the levels card's default order, pure.
// The matrix: one row per group, one column per value of `column` (the columns asked for first, in that order, then
// every other value in the order the rows first show it, so nothing is hidden), a cell no row reaches is n/a, a cell
// several rows reach is the worst of them by the order given; a row whose column value is missing lands in a null
// column, last. The browser half (alignment, header text, glyphs, accessible names, the peek) is tests/browser/p5_checks.py.
// Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matrixCells, targetValue } from '../../packages/views/kpi/src/stat-model.js';
import { LEVELS, worstOf } from '../../packages/views/live/src/levels-model.js';
import { STATUS_ORDER } from '../../packages/core/src/status.js';

const read = (r, c) => (r[c] && typeof r[c] === 'object' && 'value' in r[c] ? r[c].value : r[c]);
const row = (id, gate, verdict) => ({ id, gate, verdict });
const opts = (more = {}) => ({ column: 'gate', state: 'verdict', order: STATUS_ORDER, read, ...more });
const states = (m) => m.rows.map((r) => r.cells.map((c) => (c.na ? 'n/a' : c.state)));

test('columns: the order the rows first show them, across the groups', () => {
  const lines = [{ key: 'A', label: 'A', rows: [row('1', 'T2', 'pass'), row('2', 'T1', 'fail')] }, { key: 'B', label: 'B', rows: [row('3', 'T1', 'pass'), row('4', 'T3', 'warn')] }];
  const m = matrixCells(lines, opts());
  assert.deepEqual(m.columns, ['T2', 'T1', 'T3']);
  assert.deepEqual(m.rows.map((r) => [r.key, r.label]), [['A', 'A'], ['B', 'B']]);
  assert.deepEqual(states(m), [['pass', 'fail', 'n/a'], ['n/a', 'pass', 'warn']]);
  // every cell names its column and the rows behind it
  assert.deepEqual(m.rows[0].cells.map((c) => [c.column, c.n, c.rows.map((r) => r.id)]), [['T2', 1, ['1']], ['T1', 1, ['2']], ['T3', 0, []]]);
});

test('columns: the ones asked for first, in that order (each drawn even with no row), then the rest as they appear', () => {
  const lines = [{ key: 'A', label: 'A', rows: [row('1', 'T2', 'pass'), row('2', 'T1', 'fail')] }];
  const m = matrixCells(lines, opts({ columns: ['T1', 'T9'] }));
  assert.deepEqual(m.columns, ['T1', 'T9', 'T2']);
  assert.deepEqual(states(m), [['fail', 'n/a', 'pass']]);
  assert.equal(m.rows[0].cells[1].na, true);
  assert.equal(m.rows[0].cells[0].na, false);
});

test('a cell several rows reach is the worst of them by the order given, with the count and every row', () => {
  const lines = [{ key: 'A', label: 'A', rows: [row('1', 'T1', 'pass'), row('2', 'T1', 'fail'), row('3', 'T1', 'warn')] }];
  const m = matrixCells(lines, opts());
  const c = m.rows[0].cells[0];
  assert.deepEqual([c.state, c.n, c.rows.map((r) => r.id), c.na], ['fail', 3, ['1', '2', '3'], false]);
  // RobotDx's rank: a check that did not run is worse than a warning
  assert.equal(matrixCells([{ key: 'A', label: 'A', rows: [row('1', 'T1', 'warn'), row('2', 'T1', 'not_run')] }], opts()).rows[0].cells[0].state, 'not_run');
  // a view's own order
  assert.equal(matrixCells([{ key: 'A', label: 'A', rows: [row('1', 'T1', 'a'), row('2', 'T1', 'b')] }], opts({ order: ['b', 'a'] })).rows[0].cells[0].state, 'a');
  // a rich cell is read through `read`
  assert.equal(matrixCells([{ key: 'A', label: 'A', rows: [{ id: '1', gate: { value: 'T1' }, verdict: { value: 'fail', basis: 'derived' } }] }], opts()).rows[0].cells[0].state, 'fail');
});

test('a row with no state is a cell with no state, not n/a; a row with no column value lands in a null column, last', () => {
  const lines = [{ key: 'A', label: 'A', rows: [row('1', 'T1', null), row('2', null, 'pass'), row('3', 'T2', 'pass')] }];
  const m = matrixCells(lines, opts());
  assert.deepEqual(m.columns, ['T1', 'T2', null]);
  const [t1, t2, none] = m.rows[0].cells;
  assert.deepEqual([t1.na, t1.state, t1.n], [false, null, 1]);
  assert.deepEqual([t2.state, none.state, none.column], ['pass', 'pass', null]);
});

test('no groups: one line; an empty line still lists every column as n/a', () => {
  const m = matrixCells([{ key: null, label: '', rows: [row('1', 'T1', 'pass')] }, { key: 'B', label: 'B', rows: [] }], opts());
  assert.deepEqual(states(m), [['pass'], ['n/a']]);
});

test('targetValue: a number as written; a property, the newest row\'s value; else null', () => {
  assert.equal(targetValue(70, { target: 1 }, read), 70);
  assert.equal(targetValue('target', { target: 1.5 }, read), 1.5);
  assert.equal(targetValue('target', { target: { value: 2.5, basis: 'chosen' } }, read), 2.5);
  assert.equal(targetValue('target', { target: null }, read), null);
  assert.equal(targetValue('target', null, read), null);
  assert.equal(targetValue('nope', {}, read), null);
  assert.equal(targetValue(undefined, { target: 1 }, read), null);
});

test('levels: the default order is the status vocabulary\'s, so a bin holding a warn and a fail shows the fail', () => {
  assert.deepEqual(LEVELS, STATUS_ORDER);
  assert.equal(worstOf(['warn', 'fail']), 'fail');
  assert.equal(worstOf(['pass', 'not_run']), 'not_run');
  assert.equal(worstOf(['partial', 'pass']), 'partial');
  // RobotDx's own levels keep their order
  assert.equal(worstOf(['error', 'stale', 'unknown', 'warn', 'ok']), 'error');
  assert.equal(worstOf(['ok', 'warn']), 'warn');
  assert.equal(worstOf(['warn', 'unknown']), 'unknown');
  assert.equal(worstOf(['unknown', 'stale']), 'stale');
});
