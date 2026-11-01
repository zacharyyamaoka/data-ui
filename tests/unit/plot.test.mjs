// The interactive time series' pure parts (packages/views/chart/src/plotkit.js): wheel gestures, pan and zoom on linear,
// log and symlog scales, the legend's hide / isolate rule, the help list, and series alignment through uPlot.join.
import { test } from 'node:test';
import assert from 'node:assert/strict';

const K = await import('../../packages/views/chart/src/plotkit.js');
const { default: uPlot } = await import('uplot');

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps * Math.max(1, Math.abs(b)), `${a} != ${b}`);

test('wheelAction: Rerun\'s modifiers; a plain wheel stays the page\'s scroll', () => {
  assert.equal(K.wheelAction({}), null);
  assert.equal(K.wheelAction({ shiftKey: true }), 'pan-x');
  assert.equal(K.wheelAction({ ctrlKey: true }), 'zoom');
  assert.equal(K.wheelAction({ metaKey: true }), 'zoom');
  assert.equal(K.wheelAction({ ctrlKey: true, shiftKey: true }), 'zoom-x');
  assert.equal(K.wheelAction({ ctrlKey: true, altKey: true }), 'zoom-y');
  assert.equal(K.wheelAction({ altKey: true }), null);
  assert.equal(K.wheelAction({ ctrlKey: true, shiftKey: true, altKey: true }), null);
});

test('wheelDelta: whichever axis carries it, lines and pages in px', () => {
  assert.equal(K.wheelDelta({ deltaY: 40 }), 40);
  assert.equal(K.wheelDelta({ deltaX: -30, deltaY: 0 }), -30);   // Shift + wheel in Chrome on Linux
  assert.equal(K.wheelDelta({ deltaY: 3, deltaMode: 1 }), 48);
  assert.ok(K.zoomFactor(100) > 1 && K.zoomFactor(-100) < 1);
  close(K.zoomFactor(100) * K.zoomFactor(-100), 1);
});

test('zoomRange keeps the anchor fixed and scales the span, on linear, log and symlog', () => {
  const [a, b] = K.zoomRange([0, 10], 4, 0.5);
  close(a, 2); close(b, 7);
  // the anchor's fraction along the range is unchanged
  close((4 - a) / (b - a), (4 - 0) / (10 - 0));
  const [c, d] = K.zoomRange([1, 1000], 10, 0.5, 3);
  close(Math.log10(d) - Math.log10(c), 1.5);
  close((Math.log10(10) - Math.log10(c)) / (Math.log10(d) - Math.log10(c)), 1 / 3);
  const [e, f] = K.zoomRange([-100, 100], 0, 2, 4);
  close(e, -f); close(Math.asinh(f), 2 * Math.asinh(100));
});

test('panRange moves by a fraction of the span; valueAt reads a fraction along it', () => {
  assert.deepEqual(K.panRange([2, 6], 0.25), [3, 7]);
  const [a, b] = K.panRange([1, 100], 0.5, 3);
  close(a, 10); close(b, 1000);
  close(K.valueAt([0, 8], 0.25), 2);
  close(K.valueAt([1, 100], 0.5, 3), 10);
});

test('legendClick: click toggles one; Alt + click isolates, and again shows all', () => {
  assert.deepEqual(K.legendClick([true, true, true], 1), [true, false, true]);
  assert.deepEqual(K.legendClick([true, false, true], 1), [true, true, true]);
  assert.deepEqual(K.legendClick([true, true, true], 2, true), [false, false, true]);
  assert.deepEqual(K.legendClick([false, false, true], 2, true), [true, true, true]);
  // isolating a hidden series shows it alone
  assert.deepEqual(K.legendClick([true, false, true], 1, true), [false, true, false]);
});

test('sameRange: an echo within a millionth of the span is the same view', () => {
  assert.ok(K.sameRange([0, 10], [0, 10 + 1e-8]));
  assert.ok(!K.sameRange([0, 10], [0.1, 10]));
  assert.ok(K.sameRange(null, null));
  assert.ok(!K.sameRange(null, [0, 1]));
});

test('CONTROLS lists Rerun\'s ten controls', () => {
  assert.deepEqual(K.CONTROLS.map(([what]) => what), ['Pan', 'Horizontal pan', 'Zoom', 'Zoom X-axis', 'Zoom Y-axis', 'Zoom to selection',
    'Move time cursor', 'Reset view', 'Hide/show series', 'Hide/show other series']);
});

test('tablesOf + uPlot.join: series with different x align on the union, the gaps spanned (never 0)', () => {
  const series = [
    { name: 'a', points: [{ x: 0, value: 1 }, { x: 1, value: 2 }, { x: 2, value: 3 }] },
    { name: 'b', points: [{ x: 0.5, value: 10 }, { x: 2, value: 30 }] },
  ];
  const data = uPlot.join(K.tablesOf(series));
  assert.deepEqual([...data[0]], [0, 0.5, 1, 2]);
  assert.deepEqual(data[1], [1, undefined, 2, 3]);
  assert.deepEqual(data[2], [undefined, 10, undefined, 30]);
  // identical x columns take uPlot's cheap path: one x, the y columns side by side
  const same = uPlot.join(K.tablesOf([series[0], { name: 'c', points: series[0].points.map((p) => ({ x: p.x, value: -p.value })) }]));
  assert.deepEqual([...same[0]], [0, 1, 2]);
  assert.deepEqual(same[2], [-1, -2, -3]);
});
