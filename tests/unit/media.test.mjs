// The media cards' pure parts (packages/views/media/src/model.js): row picking, the wipe's clip-path, the basis text.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { basisText, pairBasis, pickPair, clampSplit, wipeClip, splitAt, MODES } from '../../packages/views/media/src/model.js';

const cellValue = (v) => (v !== null && typeof v === 'object' && !Array.isArray(v) && 'value' in v ? v.value : v);
const rows = [
  { id: 'r1', situation: 'target', src: 'a.mp4' },
  { id: 'r2', situation: 'factory', src: 'b.mp4' },
  { id: 'r3', situation: { value: 'tuned', basis: 'measured' }, src: 'c.mp4' },
];

test('pickPair: by/a/b pick rows A and B by value (rich cells read through cellValue)', () => {
  const { a, b } = pickPair(rows, { by: 'situation', a: 'tuned', b: 'factory' }, cellValue);
  assert.equal(a.id, 'r3');
  assert.equal(b.id, 'r2');
});
test('pickPair: without values A is the first row and B the second', () => {
  const { a, b } = pickPair(rows, {}, cellValue);
  assert.deepEqual([a.id, b.id], ['r1', 'r2']);
  const only = pickPair(rows, { by: 'situation' }, cellValue);
  assert.deepEqual([only.a.id, only.b.id], ['r1', 'r2']);
});
test('pickPair: a given A and a default B takes the first other row', () => {
  const { a, b } = pickPair(rows, { by: 'situation', a: 'factory' }, cellValue);
  assert.deepEqual([a.id, b.id], ['r2', 'r1']);
});
test('pickPair: a value no row has is null (the card says which), never a stand-in row', () => {
  const { a, b } = pickPair(rows, { by: 'situation', a: 'tuned', b: 'real' }, cellValue);
  assert.equal(a.id, 'r3');
  assert.equal(b, null);
  assert.deepEqual(pickPair([], {}, cellValue), { a: null, b: null });
  assert.deepEqual(pickPair([rows[0]], {}, cellValue), { a: rows[0], b: null });
});
test('pickPair: A and B are never the same row, even when a equals b', () => {
  const { a, b } = pickPair(rows, { by: 'situation', a: 'factory', b: 'factory' }, cellValue);
  assert.equal(a.id, 'r2');
  assert.equal(b, null);
});
test('pickPair: values compare as text (a number column against a .base number)', () => {
  const n = [{ id: 1, run: 7 }, { id: 2, run: 8 }];
  const { a, b } = pickPair(n, { by: 'run', a: '8', b: 7 });
  assert.deepEqual([a.id, b.id], [2, 1]);
});

test('wipeClip: A keeps the left split of the picture; the right inset is (1 - split) * 100%', () => {
  assert.equal(wipeClip(0.5), 'inset(0 50% 0 0)');
  assert.equal(wipeClip(0.25), 'inset(0 75% 0 0)');
  assert.equal(wipeClip(1), 'inset(0 0% 0 0)');
  assert.equal(wipeClip(0), 'inset(0 100% 0 0)');
  assert.equal(wipeClip(1 / 3), 'inset(0 66.6667% 0 0)');
});
test('clampSplit and wipeClip: out of range is clamped, a broken split is the middle', () => {
  assert.equal(clampSplit(-0.2), 0);
  assert.equal(clampSplit(1.7), 1);
  assert.equal(clampSplit('0.3'), 0.3);
  assert.equal(clampSplit(undefined), 0.5);
  assert.equal(clampSplit('half'), 0.5);
  assert.equal(wipeClip(2), 'inset(0 0% 0 0)');
});
test('splitAt: a pointer x over the picture gives its fraction, clamped at the edges', () => {
  assert.equal(splitAt(150, 100, 200), 0.25);
  assert.equal(splitAt(50, 100, 200), 0);
  assert.equal(splitAt(400, 100, 200), 1);
  assert.equal(splitAt(10, 0, 0), 0.5);
});

test('basisText: what made a clip, in words', () => {
  assert.equal(basisText('real-camera'), 'real camera');
  assert.equal(basisText('sim-render'), 'sim render');
  assert.equal(basisText('screen-capture'), 'screen capture');
  assert.equal(basisText('illustrative'), 'illustrative');
  assert.equal(basisText('lab-rig'), 'lab rig');
  assert.equal(basisText(null), null);
  assert.equal(basisText(''), null);
});
test('pairBasis: one phrase when both clips agree, "x vs y" when they differ', () => {
  assert.equal(pairBasis('sim-render', 'sim-render'), 'sim render');
  assert.equal(pairBasis('sim-render', 'real-camera'), 'sim render vs real camera');
  assert.equal(pairBasis('real-camera', null), 'real camera vs basis not given');
  assert.equal(pairBasis(null, undefined), null);
});
test('MODES: the four overlay modes, in the switch order', () => {
  assert.deepEqual(MODES, ['wipe', 'onion', 'difference', 'side']);
});
