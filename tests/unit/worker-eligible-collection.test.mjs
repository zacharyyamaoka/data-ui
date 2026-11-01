// The grouped gallery (CONTRACT §20) meets the row-model worker (perf worker): the worker and order.js's fast path
// build groups from the view's own groupBy / subGroupBy with no bins and no `grouping:` substitution, so a view that
// uses either must be built by rowModel() on the main thread. Found merging lane/collection-public onto main.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { workerEligible, WORKER_ROWS } from '../../packages/core/src/rowmodel-worker.js';

const n = Math.max(WORKER_ROWS, 6000);
const dataset = { properties: { name: { type: 'text' }, kind: { type: 'text' }, mass: { type: 'number' } },
  rows: Array.from({ length: n }, (_, i) => ({ id: 'r' + i, name: 'item ' + i, kind: ['a', 'b', 'c'][i % 3], mass: i % 500 })) };
const plain = { type: 'cards', groupBy: { property: 'kind', direction: 'ASC' } };

test('a plain grouped view of a big dataset still goes to the worker', () => {
  assert.equal(workerEligible(dataset, plain, null), true);
});

test('groupings, a grouping pick, or binned levels keep the model on the main thread', () => {
  const cases = {
    'groupings listed': { ...plain, groupings: [{ id: 'by-mass', groupBy: { property: 'mass', bins: 'auto' } }] },
    'grouping picked': { ...plain, grouping: 'by-mass', groupings: [{ id: 'by-mass', groupBy: { property: 'mass', bins: 'auto' } }] },
    'groupBy binned (auto)': { type: 'cards', groupBy: { property: 'mass', bins: 'auto' } },
    'groupBy binned (edges)': { type: 'table', groupBy: { property: 'mass', bins: [0, 100, 250, 500] } },
    'subGroupBy binned': { ...plain, subGroupBy: { property: 'mass', bins: 'auto' } },
  };
  for (const [name, view] of Object.entries(cases)) assert.equal(workerEligible(dataset, view, null), false, name);
});
