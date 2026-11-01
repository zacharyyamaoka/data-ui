// seriesColor's family lookup (docs/CONTRACT.md §32 style.families; PEP 0010 P1b): the palette wins; else the
// series' family (its rows' value of the property, read through the view's series column, or given by the caller)
// picks its colors entry: a slot 1-8, muted or 0, a var(--data-…) token, or a CSS colour; an unlisted family or a
// series with two families is muted, never a hashed slot. Without style.families nothing changes.
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { seriesColor } = await import('../../packages/core/src/clock.js');

const tokens = { series: ['#s1', '#s2', '#s3', '#s4', '#s5', '#s6', '#s7', '#s8'], muted: '#mu', css: { 'data-series-3': '#s3' } };
const families = { property: 'source', colors: { real: 1, sim: 2, target: 'muted', x: 'var(--data-series-3)', y: '#123456', z: 0, w: '4' } };
const rows = [
  { situation: 'real', source: 'real' }, { situation: 'twin', source: 'sim' }, { situation: 'target', source: 'target' },
  { situation: 'replay', source: 'replay' }, { situation: 'mix', source: 'real' }, { situation: 'mix', source: 'sim' },
  { situation: 'rich', source: { value: 'sim', note: 'a rich cell' } },
];
const input = (view) => ({ tokens, rows, view: { style: { families }, ...view } });

test('families through the view\'s series column (trajectory3d: situation by default)', () => {
  const i = input({ type: 'trajectory3d', trajectory3d: {} });
  assert.equal(seriesColor('real', i), '#s1');
  assert.equal(seriesColor('twin', i), '#s2');
  assert.equal(seriesColor('target', i), '#mu');
  assert.equal(seriesColor('replay', i), '#mu');   // unlisted: muted, never a hashed slot
  assert.equal(seriesColor('mix', i), '#mu');      // two families: unclassified
  assert.equal(seriesColor('rich', i), '#s2');     // a rich cell reads its value
  assert.equal(seriesColor('nobody', i), '#mu');
});

test('families through another card\'s series key (timeseries.series, a chart\'s colour field), and a series named as its family', () => {
  assert.equal(seriesColor('twin', input({ type: 'timeseries', timeseries: { series: 'situation' } })), '#s2');
  assert.equal(seriesColor('twin', input({ type: 'chart', chart: { encoding: { color: { field: 'situation' } } } })), '#s2');
  assert.equal(seriesColor('sim', input({ type: 'chart', chart: { encoding: { color: { field: 'source' } } } })), '#s2');
  assert.equal(seriesColor('sim', input({ type: 'chart', chart: {} })), '#s2');   // no series column: the name is the family
});

test('a family the caller gives: slots, muted / 0, a token, a CSS colour', () => {
  const i = input({ type: 'chart' });
  assert.equal(seriesColor('any', i, 'sim'), '#s2');
  assert.equal(seriesColor('any', i, null), '#mu');
  assert.equal(seriesColor('any', i, 'x'), '#s3');
  assert.equal(seriesColor('any', i, 'y'), '#123456');
  assert.equal(seriesColor('any', i, 'z'), '#mu');
  assert.equal(seriesColor('any', i, 'w'), '#s4');
});

test('the palette still wins, and without families the stable slot is unchanged', () => {
  const i = input({ type: 'trajectory3d', style: { families, palette: { real: '#abcdef' } } });
  assert.equal(seriesColor('real', i), '#abcdef');
  const plain = { tokens, rows, view: { type: 'trajectory3d' } };
  assert.equal(seriesColor('real', plain), seriesColor('real', { tokens }));
  assert.ok(tokens.series.includes(seriesColor('real', plain)));
});
