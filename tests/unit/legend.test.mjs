// The series legend every data-ui chart draws (packages/core/src/legend.js): Rerun's hide / isolate rule, the
// double-click path (two clicks arrive first), the hidden set over series names, and its place in the URL
// (l=<name>,<name>; l.<panel>= in a dashboard, l.<dashboard>.<panel>= with several on a page).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const L = await import('../../packages/core/src/legend.js');
const K = await import('../../packages/views/chart/src/plotkit.js');

test('legendClick lives in core; plotkit re-exports the same function', () => {
  assert.equal(typeof L.legendClick, 'function');
  assert.equal(K.legendClick, L.legendClick, 'one rule everywhere: plotkit re-exports core\'s');
  const src = readFileSync(new URL('../../packages/core/src/index.js', import.meta.url), 'utf8');
  const line = src.split('\n').find((l) => /from '\.\/legend\.js'/.test(l)) || '';
  for (const name of ['legendClick', 'legendPress', 'nextHidden', 'encodeHidden', 'decodeHidden', 'legendKey', 'readLegendParams', 'writeLegendParams', 'SeriesLegend']) {
    assert.match(line, new RegExp(`\\b${name}\\b`), `${name} is not exported from legend.js in index.js: ${line}`);
  }
});

test('legendClick: a click toggles one; Alt + click isolates, and again on the isolated one shows all', () => {
  assert.deepEqual(L.legendClick([true, true, true], 1), [true, false, true]);
  assert.deepEqual(L.legendClick([true, false, true], 1), [true, true, true]);
  assert.deepEqual(L.legendClick([true, true, true], 2, true), [false, false, true]);
  assert.deepEqual(L.legendClick([false, false, true], 2, true), [true, true, true]);
  assert.deepEqual(L.legendClick([true, false, true], 1, true), [false, true, false]);
});

test('legendPress: a double-click isolates (its two clicks do not leave a toggle behind), and again restores all', () => {
  const all = [true, true, true, true];
  // a double-click is click (detail 1), click (detail 2), dblclick: the net effect is isolate, from the state before it
  let s = L.legendPress({ shown: all }, 2, { detail: 1 });
  assert.deepEqual(s.shown, [true, true, false, true], 'the first click toggles at once (no lag on a single click)');
  s = L.legendPress(s, 2, { detail: 2 });
  assert.deepEqual(s.shown, [false, false, true, false], 'the second click of the pair isolates from the state before the pair');
  // a double-click on the isolated one restores everything
  s = L.legendPress(s, 2, { detail: 1 });
  assert.deepEqual(s.shown, [false, false, false, false]);
  s = L.legendPress(s, 2, { detail: 2 });
  assert.deepEqual(s.shown, all, 'double-click on the only one shown shows them all again');
  // Alt + click isolates on its own; keyboard (detail 0) is a plain toggle
  assert.deepEqual(L.legendPress({ shown: all }, 0, { alt: true, detail: 1 }).shown, [true, false, false, false]);
  assert.deepEqual(L.legendPress({ shown: all }, 3, { detail: 0 }).shown, [true, true, true, false]);
  // a second click on another entry is not a double-click on the first: a plain toggle there
  const other = L.legendPress(L.legendPress({ shown: all }, 0, { detail: 1 }), 1, { detail: 2 });
  assert.deepEqual(other.shown, [false, false, true, true]);
});

test('nextHidden: the hidden set over names; names not in this legend keep their state; all shown is empty', () => {
  const names = ['CAN 1', 'CAN 4', 'CAN 11'];
  assert.deepEqual(L.nextHidden(names, [], 1), ['CAN 4']);
  assert.deepEqual(L.nextHidden(names, ['CAN 4'], 1), []);
  assert.deepEqual(L.nextHidden(names, [], 0, { alt: true }), ['CAN 4', 'CAN 11']);
  // a name a filter removed from this legend stays hidden across a toggle of another
  assert.deepEqual(L.nextHidden(names, ['CAN 99'], 2), ['CAN 99', 'CAN 11']);
  // restore-all (isolate again) clears it, as Reset does
  assert.deepEqual(L.nextHidden(names, ['CAN 99', 'CAN 4', 'CAN 11'], 0, { alt: true }), []);
});

test('encodeHidden / decodeHidden: each name URI-encoded and comma-joined; commas, spaces and unicode survive', () => {
  const names = ['CAN 14', 'a,b', 'ünï ✓', 'x%y', 'c:d', '50 %'];
  const text = L.encodeHidden(names);
  assert.equal(text.split(',').length, names.length, 'one comma per separator: a comma inside a name is encoded');
  assert.deepEqual(L.decodeHidden(text), names);
  assert.equal(L.encodeHidden([]), '');
  assert.deepEqual(L.decodeHidden(''), []);
  assert.deepEqual(L.decodeHidden(null), []);
  // through URLSearchParams (every hash writer round-trips the whole hash through one) and back, unchanged
  const h = new URLSearchParams('view=x');
  h.set('l', text);
  const again = new URLSearchParams(h.toString().replace(/%2C/gi, ','));
  assert.deepEqual(L.decodeHidden(again.get('l')), names);
  // a malformed escape keeps the text as written rather than throwing
  assert.deepEqual(L.decodeHidden('CAN%2'), ['CAN%2']);
});

test('legendKey: l for a <data-views>; l.<panel> in a dashboard; l.<dashboard>.<panel> with several on a page', () => {
  assert.equal(L.legendKey(), 'l');
  assert.equal(L.legendKey(null, 'twin-error'), 'l.twin-error');
  assert.equal(L.legendKey('left', 'twin-error'), 'l.left.twin-error');
});

test('readLegendParams / writeLegendParams: scoped like the clock (a scoped key falls back to the plain one, and shadows it when empty)', () => {
  const panels = ['ts', 'chart'];
  const h = new URLSearchParams('view=x&l.ts=old');
  L.writeLegendParams(h, { ts: ['CAN 1', 'a,b'], chart: [] }, panels, null);
  assert.equal(h.get('view'), 'x', 'other keys survive');
  assert.deepEqual(L.decodeHidden(h.get('l.ts')), ['CAN 1', 'a,b']);
  assert.equal(h.has('l.chart'), false, 'all shown: no key');
  assert.deepEqual(L.readLegendParams(h, panels, null), { ts: ['CAN 1', 'a,b'] });
  // scoped: written under l.<key>.<panel>; the plain one stays for another dashboard
  const s = new URLSearchParams('l.ts=plain');
  L.writeLegendParams(s, { ts: ['CAN 4'] }, panels, 'left');
  assert.deepEqual(L.decodeHidden(s.get('l.left.ts')), ['CAN 4']);
  assert.equal(s.get('l.ts'), 'plain');
  assert.deepEqual(L.readLegendParams(s, panels, 'left'), { ts: ['CAN 4'] });
  assert.deepEqual(L.readLegendParams(new URLSearchParams('l.ts=plain'), panels, 'right'), { ts: ['plain'] }, 'a scoped read falls back to the plain key');
  // all shown again under a scope with a plain key present: an empty scoped key shadows it
  L.writeLegendParams(s, { ts: [] }, panels, 'left');
  assert.equal(s.get('l.left.ts'), '');
  assert.deepEqual(L.readLegendParams(s, panels, 'left'), {});
  // false: not in the URL, nothing written or read
  const f = new URLSearchParams('l.ts=plain');
  L.writeLegendParams(f, { ts: ['CAN 4'] }, panels, false);
  assert.equal(f.toString(), 'l.ts=plain');
  assert.deepEqual(L.readLegendParams(f, panels, false), {});
});

test('the dashboard\'s hash writer and reader carry each panel\'s hidden set beside s. and p. (model.js)', async () => {
  const { writeHash, readHash } = await import('../../packages/dashboard/src/model.js');
  const panels = [{ key: 'ts', dataset: 'runs', views: [{ name: 'A' }] }, { key: 'chart', dataset: 'models', views: [{ name: 'B' }] }];
  const state = { select: {}, tabs: {}, legend: { ts: ['CAN 1', 'ünï, ✓'], chart: [] } };
  const h = writeHash('view=x&l.ts=stale', state, panels);
  assert.equal(h.get('view'), 'x');
  assert.deepEqual(L.decodeHidden(h.get('l.ts')), ['CAN 1', 'ünï, ✓']);
  assert.equal(h.has('l.chart'), false);
  const text = h.toString().replace(/%2C/gi, ',').replace(/%3A/gi, ':');
  assert.deepEqual(readHash(text, panels).legend, { ts: ['CAN 1', 'ünï, ✓'] });
  // several dashboards on a page: l.<dashboard>.<panel>; false keeps the legend out of the URL
  const scoped = writeHash('', state, panels, 'left');
  assert.deepEqual(L.decodeHidden(scoped.get('l.left.ts')), ['CAN 1', 'ünï, ✓']);
  assert.equal(scoped.has('l.ts'), false);
  assert.deepEqual(readHash(scoped.toString(), panels, 'left').legend, { ts: ['CAN 1', 'ünï, ✓'] });
  assert.equal(writeHash('', state, panels, false).toString(), '');
  assert.deepEqual(readHash('l.ts=CAN%201', panels, false).legend, {});
});
