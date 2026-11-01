// scene3d's stage maths (docs/CONTRACT.md §32; PEP 0010 P1b): traj_compare's density rule and log dial, the six faces
// and the up: y turn, the view cube's ball → face, the projection key, the 2D fit's equal scale (through three's own
// orthographic camera, an oracle outside our maths), tick labels, the Z axis of a quaternion and the Z-arc.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { OrthographicCamera, Vector3 } from 'three';
import {
  markerIndices, densityOfDial, dialOfDensity, faceOf, faceOfBall, FACE_NAMES, projectionOf, faceAligned, fit2d, fmtTick,
  zAxisOf, axesOf, arcDirections, naturalCompare,
} from '../../packages/views/scene3d/src/math.js';

test('density: traj_compare\'s rule, samples 0, s, 2s, … with s = ⌊n / density⌋, plus the last (564 at 20: 22)', () => {
  const idx = markerIndices(564, 20);
  assert.equal(idx.length, 22);
  assert.deepEqual(idx.slice(0, 3), [0, 28, 56]);
  assert.deepEqual(idx.slice(-2), [560, 563]);
  assert.equal(markerIndices(564, 7).length, 9);              // stride 80: 0 … 560, then 563
  assert.deepEqual(markerIndices(5, 400), [0, 1, 2, 3, 4]);  // stride never below 1
  assert.deepEqual(markerIndices(561, 20), [...Array(20).keys()].map((k) => k * 28).concat([560]));  // 560 is the last: not twice
  assert.deepEqual(markerIndices(0, 20), []);
});

test('density dial: 0 … 100 on a log scale is 4 … 400, and traj_compare\'s default position 35 is 20', () => {
  assert.equal(densityOfDial(0), 4);
  assert.equal(densityOfDial(100), 400);
  assert.equal(densityOfDial(35), 20);
  for (const d of [4, 7, 20, 57, 400]) assert.equal(densityOfDial(dialOfDensity(d)), d);
});

test('faces for up: z (CONTRACT §32): top along −z with +y up; the four sides with +z up', () => {
  assert.deepEqual(faceOf('top'), { dir: [0, 0, -1], up: [0, 1, 0] });
  assert.deepEqual(faceOf('bottom'), { dir: [0, 0, 1], up: [0, 1, 0] });
  assert.deepEqual(faceOf('front'), { dir: [0, 1, 0], up: [0, 0, 1] });
  assert.deepEqual(faceOf('back'), { dir: [0, -1, 0], up: [0, 0, 1] });
  assert.deepEqual(faceOf('left'), { dir: [1, 0, 0], up: [0, 0, 1] });
  assert.deepEqual(faceOf('right'), { dir: [-1, 0, 0], up: [0, 0, 1] });
  assert.equal(faceOf('diagonal'), null);
});

test('faces for up: y are turned by (x, y, z) → (x, z, −y): top along −y, front along −z, right along −x', () => {
  assert.deepEqual(faceOf('top', 'y').dir, [0, -1, 0]);
  assert.deepEqual(faceOf('front', 'y').dir, [0, 0, -1]);
  assert.deepEqual(faceOf('right', 'y').dir, [-1, 0, 0]);
  assert.deepEqual(faceOf('front', 'y').up, [0, 1, 0]);
});

test('every face is a right-handed screen: right = dir × up is a unit world axis, up ⟂ dir', () => {
  for (const up of ['z', 'y']) for (const n of FACE_NAMES) {
    const { dir, up: u } = faceOf(n, up);
    assert.equal(dir[0] * u[0] + dir[1] * u[1] + dir[2] * u[2], 0, `${n} ${up}`);
  }
});

test('a cube ball puts the camera on that ball\'s side: it looks along minus the ball\'s axis', () => {
  const want = { posZ: 'top', negZ: 'bottom', posY: 'back', negY: 'front', posX: 'right', negX: 'left' };
  for (const [ball, face] of Object.entries(want)) assert.equal(faceOfBall(ball, 'z'), face, ball);
  assert.equal(faceOfBall('posY', 'y'), 'top');
  assert.equal(faceOfBall('posZ', 'y'), 'front');
  assert.equal(faceOfBall('nope'), null);
});

test('projection: a face, a {dir} (up defaults to the scene\'s up, or +y along it; made perpendicular), else perspective', () => {
  assert.equal(projectionOf('perspective').ortho, false);
  assert.equal(projectionOf(undefined).name, 'perspective');
  assert.deepEqual(projectionOf('top').dir, [0, 0, -1]);
  const iso = projectionOf({ dir: [-1, -1, -1], up: [0, 0, 1] });
  assert.equal(iso.name, 'dir');
  assert.ok(Math.abs(Math.hypot(...iso.dir) - 1) < 1e-12 && Math.abs(Math.hypot(...iso.up) - 1) < 1e-12);
  assert.ok(Math.abs(iso.dir[0] * iso.up[0] + iso.dir[1] * iso.up[1] + iso.dir[2] * iso.up[2]) < 1e-12);
  assert.deepEqual(projectionOf({ dir: [0, 0, -5] }).up, [0, 1, 0]);   // along z: +y
  assert.deepEqual(projectionOf({ dir: [0, -2, 0] }).up, [0, 0, 1]);  // the scene's up
  assert.equal(projectionOf({ dir: [0, 0, 0] }).name, 'perspective');
  assert.ok(faceAligned(projectionOf('front')));
  assert.ok(faceAligned(projectionOf({ dir: [0, 0, -3] })));
  assert.ok(!faceAligned(iso));
  assert.ok(!faceAligned(projectionOf('perspective')));
});

test('fit2d: equal scale by construction, the data inside the plot rectangle (three\'s OrthographicCamera projects it)', () => {
  const box = { min: [-170, -46, 200], max: [168, 48, 285] };
  for (const name of ['top', 'front', 'right']) {
    const { dir, up } = faceOf(name);
    const canvas = { w: 900, h: 420 }, plot = { x: 52, y: 30, w: 834, h: 350 };
    const f = fit2d(box, dir, up, canvas, plot);
    const cam = new OrthographicCamera(-canvas.w / 2 * f.s, canvas.w / 2 * f.s, canvas.h / 2 * f.s, -canvas.h / 2 * f.s, 0, f.depth * 2);
    cam.up.set(...up);
    cam.position.set(...f.center.map((c, i) => c - dir[i] * f.depth));
    cam.lookAt(...f.center);
    cam.updateMatrixWorld();
    cam.updateProjectionMatrix();
    const px = (p) => { const v = new Vector3(...p).project(cam); return [(v.x + 1) / 2 * canvas.w, (1 - v.y) / 2 * canvas.h, v.z]; };
    const o = px([0, 0, 0]), ex = px([100, 0, 0]), ey = px([0, 100, 0]), ez = px([0, 0, 100]);
    const len = (a) => Math.hypot(a[0] - o[0], a[1] - o[1]);
    const lens = [len(ex), len(ey), len(ez)].filter((l) => l > 1e-6);
    assert.equal(lens.length, 2, name);
    assert.ok(Math.abs(lens[0] - lens[1]) < 1e-6, `${name}: ${lens}`);
    for (const x of [box.min[0], box.max[0]]) for (const y of [box.min[1], box.max[1]]) for (const z of [box.min[2], box.max[2]]) {
      const [sx, sy, sz] = px([x, y, z]);
      assert.ok(sx >= plot.x - 1e-6 && sx <= plot.x + plot.w + 1e-6 && sy >= plot.y - 1e-6 && sy <= plot.y + plot.h + 1e-6, `${name}: corner at ${sx}, ${sy}`);
      assert.ok(sz > -1 && sz < 1, `${name}: inside near and far`);
    }
  }
});

test('tick labels: the step\'s decimals and a true minus; a value that rounds to zero is never −0', () => {
  assert.equal(fmtTick(-700, 100), '−700');
  assert.equal(fmtTick(0.25, 0.05), '0.25');
  assert.equal(fmtTick(-1e-9, 0.1), '0.0');
  assert.equal(fmtTick(1500, 500), '1500');
});

test('quaternions (wxyz): the Z column and the three axes, normalised first; null without one', () => {
  const h = Math.SQRT1_2;
  assert.deepEqual(zAxisOf([1, 0, 0, 0]), [0, 0, 1]);
  const z = zAxisOf([0, 2, 0, 0]);   // 180° about x, not unit: −z
  assert.ok(Math.abs(z[2] + 1) < 1e-12 && Math.abs(z[0]) < 1e-12);
  const a = axesOf([h, 0, 0, h]);    // 90° about z: x → y, y → −x
  assert.ok(Math.abs(a[0][1] - 1) < 1e-12 && Math.abs(a[1][0] + 1) < 1e-12 && Math.abs(a[2][2] - 1) < 1e-12);
  assert.equal(zAxisOf([NaN, 0, 0, 1]), null);
  assert.equal(zAxisOf(null), null);
});

test('Z-arc (traj_compare): from the own Z to the reference Z on the unit sphere, 11 directions for 10 chords', () => {
  const d = arcDirections([0, 0, 1], [1, 0, 0], 10);
  assert.equal(d.length, 11);
  assert.deepEqual(d[0], [0, 0, 1]);
  assert.deepEqual(d[10], [1, 0, 0]);
  for (const v of d) assert.ok(Math.abs(Math.hypot(...v) - 1) < 1e-12);
  assert.ok(Math.abs(d[5][0] - d[5][2]) < 1e-12);   // the middle is halfway
});

test('a family\'s members in natural order: "real 2" before "real 10"', () => {
  assert.deepEqual(['real 10', 'real', 'real 2'].sort(naturalCompare), ['real', 'real 2', 'real 10']);
});
