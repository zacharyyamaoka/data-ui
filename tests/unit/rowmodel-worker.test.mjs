// The row model off the main thread (packages/core/src/rowmodel-worker.js, review 2026-10-26 item 10).
// Oracle: the synchronous rowModel() itself. For every view of a matrix (each actuators preset, then sorts, groups,
// groupOrder with a missing group, subGroupBy, filters, the rail's filters, search and limit, on the real 1,149 rows
// and on 12,000 bootstrapped ones), the model rebuilt from the worker's index order must equal rowModel()'s: the same
// rows in the same order, the same groups (keys, nesting, members), the same counts and error, and the same TanStack
// row model the views draw (every group row and leaf, its depth, grouping value and leaf count, folded or open).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rowModel, properties } from '../../packages/core/src/rowmodel.js';
import { parseBase } from '../../packages/core/src/base.js';
import { orderOf, modelFromOrder, transferables, workerEligible, WORKER_ROWS } from '../../packages/core/src/rowmodel-worker.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples', 'robotparts-actuators');
const actuators = JSON.parse(readFileSync(join(EX, 'actuators.json'), 'utf8'));
const base = parseBase(readFileSync(join(EX, 'views.base'), 'utf8'));

// 12,000 rows: the real ones repeated with new ids (so ties and duplicates of every value are plentiful)
const big = { ...actuators, rows: Array.from({ length: 12000 }, (_, i) => ({ ...actuators.rows[i % actuators.rows.length], id: `r${i}` })) };

const ids = (rows) => rows.map((r) => r.id);
const groupsOf = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: ids(g.rows), ...(g.groups ? { groups: groupsOf(g.groups) } : {}) }));
// what a view draws from input.table: each row of the row model, as it would be drawn
const drawn = (table) => table.getRowModel().rows.map((r) => (r.getIsGrouped()
  ? ['group', r.depth, r.groupingColumnId, JSON.stringify(r.groupingValue ?? null), r.getLeafRows().length, r.getIsExpanded()]
  : ['row', r.depth, r.original.id]));

function same(dataset, view, opts = {}, label = view.name) {
  const want = rowModel(dataset, base, view, opts);
  const indexOf = new Map(dataset.rows.map((r, i) => [r, i]));
  const order = orderOf(dataset, base, view, opts, indexOf);
  // the answer crosses a thread boundary: it must survive a structured clone, and its buffers must be transferable
  const sent = structuredClone(order, { transfer: transferables(order) });
  const got = modelFromOrder(dataset, base, view, sent);
  assert.deepEqual(ids(got.rows), ids(want.rows), `${label}: rows`);
  assert.deepEqual(groupsOf(got.groups), groupsOf(want.groups), `${label}: groups`);
  assert.deepEqual([got.total, got.matched, got.error], [want.total, want.matched, want.error], `${label}: counts`);
  assert.deepEqual(drawn(got.table), drawn(want.table), `${label}: the table's row model`);
  // folded: the same group rows stay, their leaves go
  if (view.groupBy) {
    want.table.setExpanded({}); got.table.setExpanded({});
    assert.deepEqual(drawn(got.table), drawn(want.table), `${label}: folded`);
  }
  return want.rows.length;
}

const tables = base.views.filter((v) => v.type !== 'pivot');
const matrix = [
  { type: 'table', name: 'number desc', sort: [{ property: 'peak_torque', direction: 'DESC' }] },
  { type: 'table', name: 'text asc, then number', sort: [{ property: 'brand', direction: 'ASC' }, { property: 'mass', direction: 'ASC' }] },
  { type: 'table', name: 'no sort' },
  { type: 'table', name: 'group, no direction', groupBy: { property: 'form' }, sort: [{ property: 'price', direction: 'DESC' }] },
  { type: 'table', name: 'group desc', groupBy: { property: 'brand', direction: 'DESC' }, sort: [{ property: 'peak_torque', direction: 'ASC' }] },
  { type: 'table', name: 'groupOrder with a missing group', groupBy: { property: 'form' }, groupOrder: ['wheel hub', 'no such form', 'direct drive'] },
  { type: 'table', name: 'group › subgroup', groupBy: { property: 'drivetrain', direction: 'ASC' }, subGroupBy: { property: 'form', direction: 'DESC' }, sort: [{ property: 'mass', direction: 'ASC' }] },
  { type: 'table', name: 'view filter', filters: 'peak_torque > 20', sort: [{ property: 'peak_torque', direction: 'DESC' }] },
  { type: 'table', name: 'limit', limit: 50, groupBy: { property: 'brand', direction: 'ASC' }, sort: [{ property: 'mass', direction: 'DESC' }] },
  { type: 'cards', name: 'cards', sort: [{ property: 'model', direction: 'ASC' }] },
  { type: 'table', name: 'an unknown property', sort: [{ property: 'nope', direction: 'ASC' }], groupBy: { property: 'nope' } },
];

test('worker order rebuilds rowModel() exactly: every actuators preset (1,149 rows)', () => {
  let n = 0;
  for (const view of tables) { same(actuators, view); n++; }
  assert.ok(n >= 7, `${n} presets compared`);
});

test('worker order rebuilds rowModel() exactly: sorts, groups, groupOrder, subgroups, filters, limit (1,149 rows)', () => {
  for (const view of matrix) same(actuators, view);
});

test('worker order rebuilds rowModel() exactly: search and the rail\'s filters (1,149 rows)', () => {
  const view = matrix[4];
  same(actuators, view, { query: 'gim' }, 'search');
  same(actuators, view, { filters: { and: ['brand == "CubeMars"'] } }, 'rail filter');
  same(actuators, view, { query: 'zzzz-nothing' }, 'search, no match');
});

test('worker order rebuilds rowModel() exactly on 12,000 rows (every matrix view)', () => {
  for (const view of matrix) same(big, view, {}, `12k ${view.name}`);
});

test('worker eligibility: by size, never a pivot or a tree', () => {
  const props = properties(big, base);
  assert.equal(WORKER_ROWS, 5000);
  assert.equal(workerEligible(actuators, matrix[0], properties(actuators, base)), false, '1,149 rows stay synchronous');
  assert.equal(workerEligible(big, matrix[0], props), true);
  assert.equal(workerEligible(big, { type: 'pivot', splitBy: ['form'] }, props), false);
  assert.equal(workerEligible(big, { type: 'table', tree: { parent: 'brand' } }, props), false);
});
