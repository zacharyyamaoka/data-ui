// The view grammar (packages/core/src/grammar.js): the lane's evaluator plus the two fixes the SPEC found
// (negative literals, note["…"] keys) and rich cells. The lane's own copy is the oracle where it can read the input.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import * as G from '../../packages/core/src/grammar.js';

const LANE_GRAMMAR = '~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25/views/src/grammar.js';
const keep = (src, row) => G.compileExpression(src)(row);

test('negative literals: the lane read `temp_min > -20` as an error', () => {
  assert.equal(keep('temp_min > -20', { temp_min: -10 }), true);
  assert.equal(keep('temp_min > -20', { temp_min: -30 }), false);
  assert.equal(keep('delta >= -5.5 && delta <= 5.5', { delta: -5.5 }), true);
  assert.equal(keep('-x < 0', { x: 3 }), true);
  assert.equal(keep('x == -1', { x: -1 }), true);
  assert.equal(keep('x > -1e3', { x: -999 }), true);
});

test('note["…"]: hyphenated vault properties, also before a method', () => {
  const row = { 'vibe-status': 'done', 'Parent DP': ['a', 'b'], brand: 'KST' };
  assert.equal(keep('note["vibe-status"] == "done"', row), true);
  assert.equal(keep("note['vibe-status'] != 'done'", row), false);
  assert.equal(keep('note["Parent DP"].contains("b")', row), true);
  assert.equal(keep('!note["missing-key"].isEmpty()', row), false);
  assert.equal(keep('note.brand == "KST" && brand == "KST"', row), true);
  assert.throws(() => G.compileExpression('note[brand]'), /quoted name/);
});

test('rich cells read as their value in filters, summaries and pivots', () => {
  const rows = [{ id: 'a', t: { value: 12, basis: 'datasheet' }, g: 'x' }, { id: 'b', t: { value: 3, basis: 'seller' }, g: 'y' }, { id: 'c', t: { value: null, why: 'not measured' }, g: 'x' }];
  assert.deepEqual(rows.filter(G.compileFilters('t >= 10')).map((r) => r.id), ['a']);
  assert.deepEqual(rows.filter(G.compileFilters('t.isEmpty()')).map((r) => r.id), ['c']);
  assert.equal(G.summarize(rows.map((r) => r.t), 'Max'), 12);
  assert.equal(G.summarize(rows.map((r) => r.t), 'Filled'), 2);
  const p = G.pivot(rows, { order: ['g'], splitBy: [], value: { property: 't', summary: 'Median' } }, { g: {}, t: {} });
  assert.deepEqual(p.rows.map((r) => r['@Median'].v), [12, 3]);
});

test('expressionProperties reads names from the evaluator\'s own tokens', () => {
  assert.deepEqual(G.expressionProperties('!torque_density.isEmpty() && note["vibe-status"] == "x"'), ['torque_density', 'vibe-status']);
  assert.deepEqual(G.expressionProperties('file.name.contains("x") || this.file == y'), ['file.name', 'y']);
  assert.deepEqual(G.expressionProperties('price < -5 && note.brand == "KST"'), ['price', 'brand']);
});

test('errors name the place they fail', () => {
  assert.throws(() => G.compileExpression('price <'), /unexpected end/);
  assert.throws(() => G.compileExpression('price # 3'), /cannot read the filter/);
  assert.throws(() => G.compileExpression('x.nope()'), /unknown method \.nope\(\)/);
  assert.throws(() => G.compileFilters({ AND: ['x == 1'] }), /expected and \/ or \/ not/);
});

test('the lane\'s semantics are unchanged on what it could read (oracle: the lane\'s own grammar.js)', { skip: !existsSync(LANE_GRAMMAR) && 'the lane is not on disk' }, async () => {
  const L = await import(pathToFileURL(LANE_GRAMMAR).href);
  const rows = [
    { a: 1, b: 'x', c: ['p', 'q'], d: null }, { a: 5, b: 'Y', c: [], d: 'z' }, { a: null, b: '', c: ['q'], d: 0 }, { a: 2.5, b: 'xy', c: null, d: 'Z' },
  ];
  const exprs = ['a > 1', 'a >= 2.5 && b != "x"', 'b.contains("x") || c.contains("q")', '!d.isEmpty()', 'b.startsWith("X")', 'a == 1 || (a > 2 && !c.isEmpty())',
    'd == 0', 'a < 3', 'b == ""', 'note.a > 1', '!(a > 1)', 'c.isEmpty()', 'a != null', 'd == "z"', 'true', 'a'];
  for (const e of exprs) assert.deepEqual(rows.map(G.compileExpression(e)), rows.map(L.compileExpression(e)), e);
  const view = { order: ['b'], splitBy: ['d'], value: { property: 'a', summary: 'Sum' } };
  assert.deepEqual(JSON.stringify(G.pivot(rows, view, { a: {}, b: {}, d: {} })), JSON.stringify(L.pivot(rows, view, { a: {}, b: {}, d: {} })));
  const v = { type: 'pivot', name: 'P', splitBy: ['x'], value: { property: 'a', summary: 'Median' }, filters: { and: ['a > 1'] } };
  assert.equal(G.toBaseYaml(v), L.toBaseYaml(v));
  assert.equal(G.encodeView(v), L.encodeView(v));
});
