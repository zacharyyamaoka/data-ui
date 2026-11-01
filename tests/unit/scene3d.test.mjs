// scene3d's pure parts (docs/peps/0005-dashboard-cards.md §2b): the value of a series at the clock's t, and the
// camera that frames the data. The fit is checked through three's own projection (an oracle outside our maths).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PerspectiveCamera, Vector3 } from 'three';
import { sampler, bbox, fit, niceStep } from '../../packages/views/scene3d/src/math.js';

const rows = [
  { t: 0.2, x: 2, y: 20 },
  { t: 0.0, x: 0, y: 10 },     // out of order on purpose: the sampler sorts by t
  { t: 0.4, x: 6, y: null },
  { t: 'n/a', x: 99, y: 99 },  // no time: never a sample
];

test('sampler: exact at a sample, linear between samples, clamped outside the span', () => {
  const s = sampler(rows, 't', ['x', 'y']);
  assert.equal(s.n, 3);
  assert.deepEqual([s.t0, s.t1], [0, 0.4]);
  assert.deepEqual(s.at(0.2), [2, 20]);
  assert.deepEqual(s.at(0.1), [1, 15]);
  assert.ok(Math.abs(s.at(0.05)[0] - 0.5) < 1e-12);
  assert.deepEqual(s.at(-3), [0, 10]);
  assert.deepEqual(s.at(9), [6, null]);
});

test('sampler: a column missing on either neighbour is null at t, never 0', () => {
  const s = sampler(rows, 't', ['x', 'y']);
  const [x, y] = s.at(0.3);
  assert.ok(Math.abs(x - 4) < 1e-12);
  assert.equal(y, null);
});

test('sampler: reads cells through the accessor (rich cells), and an empty series gives nulls', () => {
  const rich = [{ t: { value: 0 }, x: { value: 1 } }, { t: { value: 1 }, x: { value: 3 } }];
  const s = sampler(rich, 't', ['x'], (r, c) => r[c] && r[c].value);
  assert.deepEqual(s.at(0.5), [2]);
  assert.deepEqual(sampler([], 't', ['x']).at(1), [null]);
});

test('sampler: binary search lands on the right pair over a long series', () => {
  const long = Array.from({ length: 1000 }, (_, i) => ({ t: i * 0.02, x: Math.sin(i * 0.02) }));
  const s = sampler(long, 't', ['x']);
  const t = 7.913;
  const i = Math.floor(t / 0.02);
  const f = (t - i * 0.02) / 0.02;
  const want = long[i].x + (long[i + 1].x - long[i].x) * f;
  assert.ok(Math.abs(s.at(t)[0] - want) < 1e-12);
});

test('bbox: the box around finite points only; null for none', () => {
  assert.deepEqual(bbox([[1, 2, 3], [-1, 5, 0], [NaN, 9, 9], null, [0, 0, 4]]), { min: [-1, 0, 0], max: [1, 5, 4] });
  assert.equal(bbox([]), null);
  assert.equal(bbox([[null, 1, 2]]), null);
});

function corners(box) {
  const out = [];
  for (const x of [box.min[0], box.max[0]]) for (const y of [box.min[1], box.max[1]]) for (const z of [box.min[2], box.max[2]]) out.push([x, y, z]);
  return out;
}

for (const [aspect, dir, up] of [[1.6, [0.55, -1, 0.5], [0, 0, 1]], [0.5, [1, 0.8, 1.3], [0, 1, 0]], [3, [0, -1, 0.2], [0, 0, 1]]]) {
  test(`fit: every corner of the box projects inside the frame, and fills it on one axis (aspect ${aspect})`, () => {
    // the dashboard-cards case's UR5e tool path and stick robot, roughly
    const box = { min: [-0.72, -0.3, 0], max: [0, 0.07, 0.6] };
    const f = fit(box, 35, aspect, dir, up);
    const cam = new PerspectiveCamera(35, aspect, 0.01, 100);
    cam.up.set(...up);
    cam.position.set(...f.position);
    cam.lookAt(...f.center);
    cam.updateMatrixWorld();
    const ndc = corners(box).map((p) => new Vector3(...p).project(cam));
    for (const p of ndc) assert.ok(Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1, `corner outside the frame: ${p.x}, ${p.y}`);
    // tight: on one axis the box spans the frame less the margin (1 / 1.1 of the half-frame), no more, no less
    const reach = Math.max(...ndc.map((p) => Math.max(Math.abs(p.x), Math.abs(p.y))));
    assert.ok(reach > 0.85 && reach < 1, `the box reaches ${reach} of the half-frame`);
    assert.ok(Math.abs(Math.hypot(...f.position.map((c, i) => c - f.center[i])) - f.distance) < 1e-9);
  });
}

test('fit: a single point still gets a camera at a distance', () => {
  const f = fit({ min: [1, 1, 1], max: [1, 1, 1] }, 35, 1, [1, 1, 1]);
  assert.ok(f.distance > 0.05 && Number.isFinite(f.distance));
});

test('niceStep: 1, 2 or 5 × 10^k', () => {
  assert.equal(niceStep(1, 10), 0.1);
  assert.equal(niceStep(2.2, 10), 0.2);
  assert.equal(niceStep(0.04, 10), 0.005);
  assert.equal(niceStep(70, 10), 5);
});
