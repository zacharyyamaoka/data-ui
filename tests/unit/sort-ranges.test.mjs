// A sort over a column that mixes plain numbers and numeric lists (a range [lo, hi], a list of runs) reads as ONE
// sequence: a numeric list sorts by its low end (its smallest number), a tie by its high end (its largest), and a plain
// number is its own low and high end. WHY (orchestrator, 2026-10-30): the sort put every plain number ahead of every list
// (it compared a list as its joined text), so a range column read 2, 32, −40…85, 15…30. Text, booleans and lists that
// are not all numbers sort as before (numbers first, then text by the collator), and an empty value is last both ways.
// rowModel (TanStack's sort, the oracle) and fastOrder (order.js, the big-data path) must give the same order.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { rowModel } from '../../packages/core/src/rowmodel.js';
import { orderOf } from '../../packages/core/src/rowmodel-worker.js';
import { fastOrder, rankCache } from '../../packages/core/src/order.js';

const props = { name: { type: 'text' }, range: { type: 'list' }, kind: { type: 'text' } };
const data = (cells) => ({ id: 'ranges', properties: props, rows: cells.map(([id, range, kind = 'k']) => ({ id, name: id, range, kind })) });
const ids = (ds, view) => rowModel(ds, { views: [] }, view).rows.map((r) => r.id);
const sortBy = (direction) => ({ type: 'table', name: 'T', sort: [{ property: 'range', direction }] });

test('a range column reads as one sequence: -40…85, 2, 15…30, 32 (it was 2, 32, -40…85, 15…30)', () => {
  const ds = data([['two', 2], ['thirtytwo', 32], ['wide', [-40, 85]], ['mid', [15, 30]]]);
  assert.deepEqual(ids(ds, sortBy('ASC')), ['wide', 'two', 'mid', 'thirtytwo']);
  assert.deepEqual(ids(ds, sortBy('DESC')), ['thirtytwo', 'mid', 'two', 'wide'], 'descending is the same sequence reversed');
});

test('a tie on the low end goes to the high end; a plain number is its own high end, so it leads its ties', () => {
  const ds = data([['r60', [15, 60]], ['n15', 15], ['r30', [15, 30]], ['r20', [15, 20]], ['n14', 14], ['n16', 16]]);
  assert.deepEqual(ids(ds, sortBy('ASC')), ['n14', 'n15', 'r20', 'r30', 'r60', 'n16']);
  assert.deepEqual(ids(ds, sortBy('DESC')), ['n16', 'r60', 'r30', 'r20', 'n15', 'n14']);
});

test('the low and high ends are the smallest and largest numbers, whatever order the list is written in', () => {
  const ds = data([['b', [60, 15]], ['a', [10, 40, 20]], ['c', [15, 59.5]], ['d', [7]]]);
  // a: 10..40, d: 7..7, c: 15..59.5, b: 15..60
  assert.deepEqual(ids(ds, sortBy('ASC')), ['d', 'a', 'c', 'b']);
});

test('decimals and negatives compare as numbers, not as text (1.25 before 1.5, -3 before -2.5)', () => {
  const ds = data([['p', [1.5, 2]], ['q', [1.25, 3]], ['r', [-2.5, 0]], ['s', [-3, 9]]]);
  assert.deepEqual(ids(ds, sortBy('ASC')), ['s', 'r', 'q', 'p']);
});

test('a rich cell sorts by its value: {value: [15, 60], text: "15 to 60"} is the range 15..60', () => {
  const ds = data([['t', { value: [15, 60], text: '15 to 60' }], ['u', { value: 20, unit: 'kHz' }], ['v', { value: [-40, 85], text: '−40 to 85' }]]);
  assert.deepEqual(ids(ds, sortBy('ASC')), ['v', 't', 'u']);
});

test('text, lists that are not all numbers, and empty values keep their places: numbers first, then text, empty last', () => {
  const ds = data([['txt', 'n/a'], ['mix', ['a', 1]], ['nan', [1, NaN]], ['inf', [1, Infinity]], ['none', null], ['empty', []], ['r', [5, 9]], ['n', 3]]);
  const asc = ids(ds, sortBy('ASC'));
  assert.deepEqual(asc.slice(0, 2), ['n', 'r'], 'the number and the range lead, as one sequence');
  assert.deepEqual(asc.slice(-2).sort(), ['empty', 'none'], 'empty values are last');
  assert.deepEqual(new Set(asc.slice(2, -2)), new Set(['txt', 'mix', 'nan', 'inf']), 'a list with a non-number, NaN or Infinity is text, after the numbers');
  const desc = ids(ds, sortBy('DESC'));
  assert.deepEqual(desc.slice(-2).sort(), ['empty', 'none'], 'empty values are last when descending too');
  assert.deepEqual(desc.slice(-4, -2), ['r', 'n'], 'descending: the text first, then the numeric sequence reversed');
});

test('-0 and 0 are one value inside a list, as they are as plain numbers: equal keys keep the data order', () => {
  const ds = data([['x', [-0, 1]], ['y', [0, 1]], ['z', [0, 1]]]);
  assert.deepEqual(ids(ds, sortBy('ASC')), ['x', 'y', 'z']);
  assert.deepEqual(ids(ds, sortBy('DESC')), ['x', 'y', 'z']);
});

test('groups over a range column order by the same rule when the level has a direction', () => {
  const ds = data([['a', [15, 30]], ['b', 2], ['c', [-40, 85]], ['d', [15, 30]], ['e', 32]]);
  const m = rowModel(ds, { views: [] }, { type: 'table', name: 'G', groupBy: { property: 'range', direction: 'ASC' } });
  assert.deepEqual(m.groups.map((g) => g.rows.map((r) => r.id)), [['c'], ['b'], ['a', 'd'], ['e']]);
});

// fastOrder (order.js) must answer exactly as TanStack's sort does, on a corpus with every case above and many ties
const VALUES = [2, 32, [-40, 85], [15, 30], 15, [15, 60], [15, 20], [60, 15], [7], [1.5, 2], [1.25, 3], [-0, 1], [0, 1], -0,
  { value: [15, 60], text: '15 to 60' }, { value: 20 }, 'n/a', ['a', 1], [1, NaN], [1, Infinity], null, [], undefined, 'b', [3, 3], 3];
const corpus = { id: 'corpus', properties: { a: { type: 'list' }, b: { type: 'list' }, c: { type: 'text' } }, rows: Array.from({ length: 2400 }, (_, i) => ({
  id: `r${i}`, a: VALUES[(i * 7) % VALUES.length], b: VALUES[(i * 11 + 3) % VALUES.length], c: `t${(i * 13) % 97}`,
})) };
const plain = (o) => o && { rows: [...o.rows], table: [...o.table], groups: groupsOf(o.groups), total: o.total, matched: o.matched };
const groupsOf = (gs) => gs && gs.map((g) => ({ key: g.key, property: g.property, rows: [...g.rows], ...(g.groups ? { groups: groupsOf(g.groups) } : {}) }));

test('fastOrder = orderOf(rowModel()) over numbers and numeric lists: flat, grouped, two keys, both directions', () => {
  const cache = rankCache(corpus);
  const indexOf = new Map(corpus.rows.map((r, i) => [r, i]));
  const views = [];
  for (const p of ['a', 'b']) for (const direction of ['ASC', 'DESC']) views.push({ type: 'table', name: `${p} ${direction}`, sort: [{ property: p, direction }] });
  views.push(
    { type: 'table', name: 'a asc, b desc', sort: [{ property: 'a', direction: 'ASC' }, { property: 'b', direction: 'DESC' }] },
    { type: 'table', name: 'group a asc, sort b', groupBy: { property: 'a', direction: 'ASC' }, sort: [{ property: 'b', direction: 'ASC' }] },
    { type: 'table', name: 'group c, sort a desc', groupBy: { property: 'c', direction: 'DESC' }, sort: [{ property: 'a', direction: 'DESC' }] },
  );
  for (const view of views) {
    const want = plain(orderOf(corpus, { views: [] }, view, {}, indexOf));
    const got = plain(fastOrder(corpus, { views: [] }, view, {}, cache));
    assert.deepEqual(got, want, view.name);
  }
  // and the rule itself, on the fast path: the first rows of `a ASC` are the most negative low ends
  const first = fastOrder(corpus, { views: [] }, { type: 'table', name: 'x', sort: [{ property: 'a', direction: 'ASC' }] }, {}, cache).rows.slice(0, 1);
  assert.deepEqual(corpus.rows[first[0]].a, [-40, 85]);
});
