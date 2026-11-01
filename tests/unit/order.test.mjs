// fastOrder() (packages/core/src/order.js): the row model's order from typed-array sort keys, held byte for byte to
// orderOf(rowModel()) (TanStack's own sort, the oracle). Every view of the actuators matrix, on 1,149 and 12,000 rows,
// with search and the rail's filters; and a corpus built to hit TanStack's edge rules: undefined last in both
// directions, numbers before text, text the collator calls equal ("a" / "A", "x2" / "x02"), 0 and -0, arrays joined,
// booleans and NaN as text, groupOrder with null, arrays and a duplicate, a grouping column also sorted, a sub-group
// on the same property, limit, and keys too many for one double (the comparator path).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { orderOf, workerEligible } from '../../packages/core/src/rowmodel-worker.js';
import { properties } from '../../packages/core/src/rowmodel.js';
import { fastOrder, rankCache } from '../../packages/core/src/order.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples', 'robotparts-actuators');
const actuators = JSON.parse(readFileSync(join(EX, 'actuators.json'), 'utf8'));
const base = parseBase(readFileSync(join(EX, 'views.base'), 'utf8'));
const grow = (src, n) => ({ ...src, rows: Array.from({ length: n }, (_, i) => ({ ...src.rows[i % src.rows.length], id: `r${i}` })) });
const big = grow(actuators, 12000);

const plain = (o) => o && { rows: [...o.rows], table: [...o.table], groups: groupsOf(o.groups), total: o.total, matched: o.matched, error: o.error };
const groupsOf = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: [...g.rows], ...(g.groups ? { groups: groupsOf(g.groups) } : {}) }));
function same(dataset, b, view, opts = {}, label = view.name, cache = undefined) {
  const indexOf = new Map(dataset.rows.map((r, i) => [r, i]));
  const want = plain(orderOf(dataset, b, view, opts, indexOf));
  const got = plain(fastOrder(dataset, b, view, opts, cache));
  assert.deepEqual(got, want, label);
}

const matrix = [
  { type: 'table', name: 'number desc', sort: [{ property: 'peak_torque', direction: 'DESC' }] },
  { type: 'table', name: 'number asc', sort: [{ property: 'mass', direction: 'ASC' }] },
  { type: 'table', name: 'text asc, then number', sort: [{ property: 'brand', direction: 'ASC' }, { property: 'mass', direction: 'ASC' }] },
  { type: 'table', name: 'text desc', sort: [{ property: 'model', direction: 'DESC' }] },
  { type: 'table', name: 'no sort' },
  { type: 'table', name: 'group, no direction', groupBy: { property: 'form' }, sort: [{ property: 'price', direction: 'DESC' }] },
  { type: 'table', name: 'group desc', groupBy: { property: 'brand', direction: 'DESC' }, sort: [{ property: 'peak_torque', direction: 'ASC' }] },
  { type: 'table', name: 'groupOrder with a missing group', groupBy: { property: 'form' }, groupOrder: ['wheel hub', 'no such form', 'direct drive'] },
  { type: 'table', name: 'groupOrder and a direction', groupBy: { property: 'brand', direction: 'DESC' }, groupOrder: ['CubeMars', null], sort: [{ property: 'mass', direction: 'DESC' }] },
  { type: 'table', name: 'group › subgroup', groupBy: { property: 'drivetrain', direction: 'ASC' }, subGroupBy: { property: 'form', direction: 'DESC' }, sort: [{ property: 'mass', direction: 'ASC' }] },
  { type: 'table', name: 'subgroup only sorted', groupBy: { property: 'drivetrain' }, subGroupBy: { property: 'form', direction: 'ASC' } },
  { type: 'table', name: 'view filter', filters: 'peak_torque > 20', sort: [{ property: 'peak_torque', direction: 'DESC' }] },
  { type: 'table', name: 'limit', limit: 50, groupBy: { property: 'brand', direction: 'ASC' }, sort: [{ property: 'mass', direction: 'DESC' }] },
  { type: 'table', name: 'limit flat', limit: 7, sort: [{ property: 'price', direction: 'ASC' }] },
  { type: 'cards', name: 'cards', sort: [{ property: 'model', direction: 'ASC' }] },
  { type: 'table', name: 'an unknown property', sort: [{ property: 'nope', direction: 'ASC' }], groupBy: { property: 'nope' } },
  { type: 'table', name: 'a broken filter', filters: 'peak_torque >', sort: [{ property: 'mass', direction: 'ASC' }] },
];

test('fastOrder = orderOf(rowModel()): every actuators preset and the matrix (1,149 rows)', () => {
  for (const view of base.views.filter((v) => v.type !== 'pivot')) same(actuators, base, view);
  for (const view of matrix) same(actuators, base, view);
});

test('fastOrder = orderOf(rowModel()): search, the rail\'s filters, and one rank cache across them (1,149 and 12,000 rows)', () => {
  for (const data of [actuators, big]) {
    const cache = rankCache(data);
    for (const view of matrix) {
      same(data, base, view, {}, `${data.rows.length} ${view.name}`, cache);
      same(data, base, view, { query: 'gim' }, `${data.rows.length} ${view.name} search`, cache);
      same(data, base, view, { filters: { and: ['brand == "CubeMars"'] } }, `${data.rows.length} ${view.name} rail`, cache);
    }
  }
});

// the edge corpus: every value class TanStack's sortFn and accessor distinguish, many ties
const VALUES = [undefined, null, '', [], 0, -0, 1, 2, 10, -3.5, 1e9, 'a', 'A', 'b', 'B', 'x2', 'x02', 'x10', 'é', 'e', ' a', true, false, NaN,
  Infinity, ['p', 'q'], 'p, q', '10', { value: 3, unit: 'N·m' }, { value: null }, 'Ä', 'z'];
const edgeProps = { a: { type: 'text' }, b: { type: 'text' }, c: { type: 'number' }, d: { type: 'text' } };
const edge = { id: 'edge', properties: edgeProps, rows: Array.from({ length: 3000 }, (_, i) => ({
  id: `e${i}`, a: VALUES[(i * 7) % VALUES.length], b: VALUES[(i * 13 + 5) % VALUES.length], c: VALUES[(i * 3 + 1) % VALUES.length], d: `t${(i * 31) % 997}`,
})) };
const eb = { views: [] };
const edgeViews = [];
for (const p of ['a', 'b', 'c']) for (const dir of ['ASC', 'DESC']) edgeViews.push({ type: 'table', name: `${p} ${dir}`, sort: [{ property: p, direction: dir }] });
edgeViews.push(
  { type: 'table', name: 'a asc, b desc, c asc', sort: [{ property: 'a', direction: 'ASC' }, { property: 'b', direction: 'DESC' }, { property: 'c', direction: 'ASC' }] },
  { type: 'table', name: 'group a desc, sort b', groupBy: { property: 'a', direction: 'DESC' }, sort: [{ property: 'b', direction: 'ASC' }] },
  { type: 'table', name: 'group a, no direction, sort a desc', groupBy: { property: 'a' }, sort: [{ property: 'a', direction: 'DESC' }, { property: 'c', direction: 'ASC' }] },
  { type: 'table', name: 'group a › b, both sorted, sort c', groupBy: { property: 'a', direction: 'ASC' }, subGroupBy: { property: 'b', direction: 'DESC' }, sort: [{ property: 'c', direction: 'DESC' }] },
  { type: 'table', name: 'group a › a', groupBy: { property: 'a', direction: 'ASC' }, subGroupBy: { property: 'a', direction: 'DESC' } },
  { type: 'table', name: 'sub-group sorted, group not', groupBy: { property: 'b' }, subGroupBy: { property: 'c', direction: 'ASC' }, sort: [{ property: 'a', direction: 'ASC' }] },
  { type: 'table', name: 'groupOrder: null, an array, a duplicate, a number', groupBy: { property: 'a' }, groupOrder: [null, ['p', 'q'], 'b', 'b', 2, 'nothing'], sort: [{ property: 'c', direction: 'DESC' }] },
  { type: 'table', name: 'groupOrder and sort on its column', groupBy: { property: 'a', direction: 'DESC' }, groupOrder: ['A', 1], sort: [{ property: 'a', direction: 'DESC' }] },
  { type: 'table', name: 'groupOrder, sub-group, limit', groupBy: { property: 'b' }, subGroupBy: { property: 'a', direction: 'ASC' }, groupOrder: ['B', 'z'], limit: 40 },
  { type: 'table', name: 'keys too many for one double, with ties', sort: ['ASC', 'DESC', 'ASC', 'DESC', 'ASC'].map((direction) => ({ property: 'd', direction })) },
  { type: 'table', name: 'keys too many for one double', sort: [{ property: 'd', direction: 'ASC' }, { property: 'b', direction: 'DESC' }, { property: 'a', direction: 'ASC' }, { property: 'd', direction: 'DESC' }, { property: 'c', direction: 'DESC' }, { property: 'd', direction: 'ASC' }] },
);

test('fastOrder = orderOf(rowModel()): the edge corpus (undefined, mixed types, collator ties, groupOrder, limit, many keys)', () => {
  const cache = rankCache(edge);
  for (const view of edgeViews) {
    same(edge, eb, view, {}, view.name, cache);
    same(edge, eb, view, { query: 'x' }, `${view.name} search`, cache);
  }
});

test('fastOrder declines what it does not model (pivot, tree, a row with _heading): null, so the caller uses orderOf', () => {
  assert.equal(fastOrder(big, base, { type: 'pivot', splitBy: ['form'] }), null);
  assert.equal(fastOrder(big, base, { type: 'table', tree: { parent: 'brand' } }), null);
  assert.equal(fastOrder({ ...edge, rows: [...edge.rows, { id: 'h', _heading: 'x' }] }, eb, edgeViews[0]), null);
  // a rollup's rows are made, not the dataset's; a time level groups by a bucket: neither is modelled, and neither
  // goes to the worker
  const rolled = { type: 'table', name: 'r', rollup: { keep: ['brand'] } };
  const weekly = { type: 'table', name: 'w', groupBy: { property: 'listed', by: 'week' } };
  const monthlyUnder = { type: 'table', name: 'm', groupBy: { property: 'brand' }, subGroupBy: { property: 'listed', by: 'month' } };
  for (const v of [rolled, weekly, monthlyUnder]) {
    assert.equal(fastOrder(big, base, v), null, v.name);
    assert.equal(workerEligible(big, v, properties(big, base)), false, v.name);
  }
  assert.equal(workerEligible(big, matrix[0], properties(big, base)), true);
});

test('fastOrder = orderOf(rowModel()) at 100,000 rows: a text sort, a grouped sort and a two-key sort', () => {
  const huge = grow(actuators, 100000);
  for (const r of huge.rows) r.model = `${r.model} #${r.id}`;
  const cache = rankCache(huge);
  for (const view of [matrix[3], matrix[6], matrix[2]]) same(huge, base, view, {}, `100k ${view.name}`, cache);
});

// judge r1 finding 1 (2026-10-27): a groupOrder that repeats a name sizes the named ranks above named.size (a Map keeps
// the last index), so a real rank met the undefined sentinel and an empty group sorted before a named one
test('fastOrder = orderOf(rowModel()): groupOrder repeating a name keeps the empty group last ([null, B] by [A, A, A, B])', () => {
  const data = { id: 'dup', properties: { g: { type: 'text' } }, rows: [{ id: 'r0', g: null }, { id: 'r1', g: 'B' }] };
  same(data, eb, { type: 'table', name: 'dup', groupBy: { property: 'g' }, groupOrder: ['A', 'A', 'A', 'B'] }, {}, 'judge case');
});

test('fastOrder = orderOf(rowModel()): 2,000 generated groupOrders with repeated names, empties and unnamed groups', () => {
  let seed = 7;
  const rnd = (k) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % k; };
  const names = ['A', 'B', 'C', 'D', null, ''];
  for (let c = 0; c < 2000; c++) {
    const rows = Array.from({ length: 2 + rnd(9) }, (_, i) => ({ id: `r${i}`, g: names[rnd(names.length)], s: rnd(5) }));
    const groupOrder = Array.from({ length: 1 + rnd(6) }, () => ['A', 'A', 'B', 'C', 'X', null][rnd(6)]);
    const view = { type: 'table', name: `gen ${c}`, groupBy: { property: 'g', ...(rnd(2) ? { direction: rnd(2) ? 'ASC' : 'DESC' } : {}) }, groupOrder,
      ...(rnd(2) ? { sort: [{ property: 's', direction: rnd(2) ? 'ASC' : 'DESC' }] } : {}) };
    same({ id: 'gen', properties: { g: { type: 'text' }, s: { type: 'number' } }, rows }, eb, view, {}, `${view.name} ${JSON.stringify(groupOrder)} ${JSON.stringify(rows.map((r) => r.g))}`);
  }
});
