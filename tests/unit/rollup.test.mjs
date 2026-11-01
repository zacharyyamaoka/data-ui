// Roll-up (docs/CONTRACT.md §16): keep some dimensions, aggregate the rest per column; drill back to the records.
import test from 'node:test';
import assert from 'node:assert/strict';
import { rollup, rollupKeep, rollupDims, summaryName, summarize } from '../../packages/core/src/grammar.js';
import { rowModel } from '../../packages/core/src/rowmodel.js';

const props = {
  model: { id: 'model', type: 'text' }, actuator: { id: 'actuator', type: 'text' }, rung: { id: 'rung', type: 'text' },
  bench: { id: 'bench', type: 'text' }, err: { id: 'err', type: 'number' }, runs: { id: 'runs', type: 'list' },
};
const rows = [
  { id: 1, model: 'M2', actuator: 'CAN 1', rung: 'M2', bench: 'tape', err: 2, runs: [1, 3] },
  { id: 2, model: 'M2', actuator: 'CAN 4', rung: 'M2', bench: 'tape', err: 10, runs: [9] },
  { id: 3, model: 'M2', actuator: 'CAN 14', rung: 'M2', bench: 'sine', err: { value: 4, basis: 'measured' }, runs: [] },
  { id: 4, model: 'M4', actuator: 'CAN 14', rung: 'M4', bench: 'tape', err: 1, runs: [1] },
];

test('summary aliases map onto Bases names; Spread is max - min', () => {
  assert.equal(summaryName('median'), 'Median');
  assert.equal(summaryName('mean'), 'Average');
  assert.equal(summaryName('spread'), 'Spread');
  assert.equal(summaryName('Max'), 'Max');
  assert.equal(summaryName('bogus'), null);
  assert.equal(summarize([3, 9, 4], 'Spread'), 6);
});

test('rolling up across actuators: one row per kept combination, each number aggregated, records kept', () => {
  const out = rollup(rows, { rollup: { keep: ['model'] } }, props);
  assert.equal(out.length, 2);
  const m2 = out.find((r) => r.model === 'M2');
  assert.deepEqual(m2._records.map((r) => r.id), [1, 2, 3]);
  assert.equal(m2.err.value, 4); // median of 2, 10, 4 (a rich cell's .value counts)
  assert.equal(m2.err.n, 3);
  assert.equal(m2.err.low, 2);
  assert.equal(m2.err.high, 10);
  assert.equal(m2.err.basis, 'derived');
  assert.equal(m2.rung, 'M2'); // the same in every row: kept as is
  assert.equal(m2.actuator.value, null); // rolled away: no single value
  assert.equal(m2.actuator.rolled, 3);
  assert.match(m2.actuator.why, /rolled up: 3 values/);
  assert.deepEqual(m2.runs, [1, 3, 9]); // a list keeps every point
});

test('the aggregate is chosen per column', () => {
  const view = { rollup: { keep: ['model'], agg: { err: 'max' } } };
  assert.equal(rollup(rows, view, props).find((r) => r.model === 'M2').err.value, 10);
  view.rollup.agg.err = 'spread';
  assert.equal(rollup(rows, view, props).find((r) => r.model === 'M2').err.value, 8);
  view.rollup.agg.err = 'count';
  assert.equal(rollup(rows, view, props).find((r) => r.model === 'M2').err.value, 3);
  view.rollup.agg.err = 'mean';
  assert.equal(rollup(rows, view, props).find((r) => r.model === 'M2').err.value, 16 / 3);
});

test('group levels and the pivot columns are always kept; the menu offers dims or every text property', () => {
  assert.deepEqual(rollupKeep({ rollup: { keep: ['model'] }, groupBy: { property: 'rung' } }, props), ['model', 'rung']);
  assert.deepEqual(rollupKeep({ type: 'pivot', rollup: { keep: ['model'] }, splitBy: ['bench'] }, props), ['model', 'bench']);
  assert.deepEqual(rollupDims({ rollup: { dims: ['actuator', 'nope'] } }, props), ['actuator']);
  assert.deepEqual(rollupDims({}, props), ['model', 'actuator', 'rung', 'bench', 'runs']);
});

test('the row model rolls a table up and a pivot by its kept dimensions; no rollup leaves rows alone', () => {
  const dataset = { properties: props, rows };
  const t = rowModel(dataset, {}, { type: 'table', rollup: { keep: ['model', 'bench'] } });
  assert.equal(t.rows.length, 3);
  assert.deepEqual(t.rolled, { from: 4, keep: ['model', 'bench'], away: ['actuator', 'runs'] }); // rung is constant per model: not rolled away
  const plain = rowModel(dataset, {}, { type: 'table' });
  assert.equal(plain.rows.length, 4);
  assert.equal(plain.rolled, null);
  const pv = rowModel(dataset, {}, { type: 'pivot', order: ['model', 'actuator'], splitBy: ['bench'], value: { property: 'err', summary: 'Median' }, rollup: { keep: ['model'], agg: { err: 'max' } } });
  assert.equal(pv.pivot.rows.length, 2); // actuator rolled away: one row per model
  assert.deepEqual(pv.pivot.order, ['model']);
  const m2 = pv.pivot.rows.find((r) => r.model === 'M2');
  assert.equal(m2['@tape'].v, 10); // max over CAN 1 and CAN 4
  assert.equal(m2['@tape'].records.length, 2);
});
