// PEP 0010 P2, sim2real gap #6: rules and bands from a property (packages/core/src/guides.js, shared by the timeseries
// card, its interactive uPlot form and the live plot). A rule's `y`, or a band's bounds, may name a property instead of
// giving a number: the value comes from the rows the view draws, per series. One value over a series' rows is a constant
// (drawn across the data's x); a value that changes is a step line through it (its first point, each change, the last
// x). Series that draw the same line share it. A number stays the plain rule it was. Written red, before the code.
// The browser half is tests/browser/p2_checks.py (rules and bands).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { guidesFrom } from '../../packages/core/src/guides.js';

const rows = [];
for (const [device, lim, caps] of [['A', 40, [30, 45]], ['B', 60, [50, 65]]]) {
  for (let i = 0; i < 100; i++) {
    const t = Math.round(i) / 10;
    for (const situation of ['real', 'target']) rows.push({ t, device, situation, q: Math.sin(t), hi: lim, lo: -lim, cap: t < 5 ? caps[0] : caps[1] });
  }
}
const read = (r, c) => r[c];
const A = rows.filter((r) => r.device === 'A');

test('a rule from a property with one value over the rows is a constant across the data\'s x', () => {
  const g = guidesFrom(A, { rules: [{ y: 'hi', label: 'limit', tone: 'bad' }] }, { x: 't', series: 'situation', read });
  assert.equal(g.rules.length, 1);   // real and target carry the same limit: one line
  const r = g.rules[0];
  assert.equal(r.guide, 'rule:0');
  assert.equal(r.constant, 40);
  assert.equal(r.label, 'limit');
  assert.equal(r.tone, 'bad');
  assert.deepEqual(r.points, [[0, 40], [9.9, 40]]);
});

test('a property that changes is a step line through its values: the first point, each change, the last x', () => {
  const g = guidesFrom(A, { rules: [{ y: 'cap' }] }, { x: 't', series: 'situation', read });
  assert.equal(g.rules.length, 1);
  assert.equal(g.rules[0].constant, null);
  assert.deepEqual(g.rules[0].points, [[0, 30], [5, 45], [9.9, 45]]);
});

test('per series: each series draws its own value (a device\'s own limit); a number is left to the plain rule', () => {
  const g = guidesFrom(rows, { rules: [{ y: 'hi' }, { y: 12 }] }, { x: 't', series: 'device', read });
  assert.deepEqual(g.rules.map((r) => [r.guide, r.series, r.constant]), [['rule:0', 'A', 40], ['rule:0', 'B', 60]]);
});

test('bands from properties: [lo, hi] each a property or a number; a constant pair and a stepped one', () => {
  const g = guidesFrom(A, { bands: [{ y: ['lo', 'hi'], tone: 'warn' }, { y: [0, 'cap'] }] }, { x: 't', series: 'situation', read });
  assert.equal(g.bands.length, 2);
  assert.equal(g.bands[0].guide, 'band:0');
  assert.deepEqual(g.bands[0].constant, [-40, 40]);
  assert.deepEqual(g.bands[0].lo, [[0, -40], [9.9, -40]]);
  assert.deepEqual(g.bands[0].hi, [[0, 40], [9.9, 40]]);
  assert.equal(g.bands[1].guide, 'band:1');
  assert.equal(g.bands[1].constant, null);
  assert.deepEqual(g.bands[1].lo, [[0, 0], [5, 0], [9.9, 0]]);
  assert.deepEqual(g.bands[1].hi, [[0, 30], [5, 45], [9.9, 45]]);
});

test('missing values are skipped, a property no row holds draws nothing, hidden series are left out', () => {
  const some = A.map((r, i) => (i % 3 ? r : { ...r, hi: null }));
  assert.equal(guidesFrom(some, { rules: [{ y: 'hi' }] }, { x: 't', series: 'situation', read }).rules[0].constant, 40);
  assert.equal(guidesFrom(A, { rules: [{ y: 'nope' }] }, { x: 't', series: 'situation', read }).rules.length, 0);
  const g = guidesFrom(rows, { rules: [{ y: 'hi' }] }, { x: 't', series: 'device', read, hidden: ['A'] });
  assert.deepEqual(g.rules.map((r) => r.series), ['B']);
  // no series column: the rows are one series
  assert.equal(guidesFrom(A, { rules: [{ y: 'hi' }] }, { x: 't', series: null, read }).rules[0].constant, 40);
});
