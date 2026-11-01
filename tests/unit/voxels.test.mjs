// PEP 0010 P2: the voxels view's grid and ramp, pure (packages/views/scene3d/src/voxels/grid.js and ramp.js: numbers in,
// numbers out, no three.js). The browser half, against numpy.histogramdd on 137 runs and on BAM Reach's map, is
// tests/browser/p2_checks.py. Written red, before the code.
//
// The grid (CONTRACT §32 reserved the keys; this pins what they mean): raw rows bin on cells anchored at the frame's
// origin, cell k spanning [k·cell, (k + 1)·cell) with the edges the float64 products k·cell (numpy.histogramdd's rule);
// pre-gridded rows (value: <property>) on their own lattice, origin = the smallest centre − cell / 2. count is rows per
// cell, time Σ w ÷ hz (w defaults to 1), runs the distinct runs, a property its summary (Bases' names, Average by
// default); a row missing a coordinate is skipped; `drop` bins with one axis dropped (slice at: all, the projection).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cellIndex, voxelGrid, planeOf, kOf } from '../../packages/views/scene3d/src/voxels/grid.js';
import { sequentialRamp } from '../../packages/views/scene3d/src/voxels/ramp.js';

const spec = (more = {}) => ({ x: 'x', y: 'y', z: 'z', cell: 10, ...more });
const byKey = (grid) => Object.fromEntries(grid.cells.map((c) => [`${c.i},${c.j},${c.k}`, c.value]));

test('cellIndex: a value on an edge is in the cell it starts; the edges are the float64 products k·cell', () => {
  assert.equal(cellIndex(0, 25), 0);
  assert.equal(cellIndex(24.999, 25), 0);
  assert.equal(cellIndex(25, 25), 1);
  assert.equal(cellIndex(-0.001, 25), -1);
  assert.equal(cellIndex(-25, 25), -1);
  assert.equal(cellIndex(-25.001, 25), -2);
  // 3 × 0.1 is 0.30000000000000004 in float64, so 0.3 lies below that edge: cell 2, as numpy.histogramdd puts it
  assert.equal(cellIndex(0.3, 0.1), 2);
  assert.equal(cellIndex(0.30000000000000004, 0.1), 3);
  // with an origin: edges origin + k·cell
  assert.equal(cellIndex(142.887, 150, -832.113), 6);
  assert.equal(cellIndex(-832.113, 150, -832.113), 0);
});

test('voxelGrid count: rows per cell; a missing coordinate skips the row (never a 0)', () => {
  const rows = [
    { x: 1, y: 1, z: 1 }, { x: 9.99, y: 0, z: 5 }, { x: 10, y: 0, z: 0 }, { x: -1, y: 0, z: 0 },
    { x: 1, y: null, z: 1 }, { x: 'n/a', y: 2, z: 2 }, { y: 1, z: 1 },
  ];
  const g = voxelGrid(rows, spec());
  assert.equal(g.value, 'count');
  assert.deepEqual(g.origin, [0, 0, 0]);
  assert.deepEqual(byKey(g), { '0,0,0': 2, '1,0,0': 1, '-1,0,0': 1 });
  assert.equal(g.skipped, 3);
  assert.deepEqual(g.domain, [0, 2]);
});

test('voxelGrid time: Σ w ÷ hz (w 1 when missing); runs: distinct runs per cell', () => {
  const rows = [
    { x: 1, y: 1, z: 1, w: 1, run: 'a' }, { x: 2, y: 1, z: 1, w: 0, run: 'a' }, { x: 3, y: 1, z: 1, w: 1, run: 'b' },
    { x: 11, y: 1, z: 1, run: 'c' },
  ];
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'time', hz: 20 }))), { '0,0,0': 2 / 20, '1,0,0': 1 / 20 });
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'runs' }))), { '0,0,0': 2, '1,0,0': 1 });
  assert.deepEqual(byKey(voxelGrid(rows.map((r) => ({ ...r, weight: r.w, w: undefined })), spec({ value: 'time', hz: 2, w: 'weight' }))), { '0,0,0': 1, '1,0,0': 0.5 });
  // time needs hz: a problem, no cells
  const bad = voxelGrid(rows, spec({ value: 'time' }));
  assert.ok(bad.problem && /hz/.test(bad.problem));
  assert.equal(bad.cells.length, 0);
});

test('voxelGrid property: pre-gridded rows on their own lattice, each Bases summary', () => {
  const rows = [
    { x: 5, y: 5, z: 5, v: 0.2 }, { x: 5, y: 5, z: 5, v: 0.6 }, { x: 5, y: 5, z: 5, v: 1.0 },
    { x: 15, y: 5, z: 5, v: 0.5 }, { x: 15, y: 5, z: 5, v: null },
  ];
  const g = voxelGrid(rows, spec({ value: 'v' }));
  assert.equal(g.value, 'property');
  assert.equal(g.property, 'v');
  assert.deepEqual(g.origin, [0, 0, 0]);   // the smallest centre (5) − cell / 2
  const avg = byKey(g);
  assert.ok(Math.abs(avg['0,0,0'] - 0.6) < 1e-15);
  assert.equal(avg['1,0,0'], 0.5);
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'v', summary: 'Median' }))), { '0,0,0': 0.6, '1,0,0': 0.5 });
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'v', summary: 'Min' }))), { '0,0,0': 0.2, '1,0,0': 0.5 });
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'v', summary: 'Max' }))), { '0,0,0': 1, '1,0,0': 0.5 });
  assert.ok(Math.abs(byKey(voxelGrid(rows, spec({ value: 'v', summary: 'Sum' })))['0,0,0'] - 1.8) < 1e-12);
  // a lattice off the origin: BAM Reach's z centres −757.113 + 150 k sit at their cells' centres
  const reach = [{ x: 0, y: 0, z: -757.113, v: 1 }, { x: 0, y: 0, z: 142.887, v: 0.5 }];
  const r = voxelGrid(reach, { x: 'x', y: 'y', z: 'z', cell: 150, value: 'v' });
  assert.deepEqual(r.origin, [-75, -75, -757.113 - 75]);
  assert.deepEqual(r.cells.map((c) => c.k).sort((a, b) => a - b), [0, 6]);
  assert.deepEqual(r.domain, [0, 1]);
});

test('voxelGrid drop: the projection along one axis (slice at: all): count sums through the depth, runs counts per column', () => {
  const rows = [
    { x: 1, y: 1, z: 1, run: 'a' }, { x: 1, y: 1, z: 15, run: 'a' }, { x: 1, y: 1, z: 25, run: 'b' }, { x: 11, y: 1, z: 1, run: 'a' },
  ];
  assert.deepEqual(byKey(voxelGrid(rows, spec(), { drop: 'z' })), { '0,0,0': 3, '1,0,0': 1 });
  // a run crossing three cells of one column counts once in the projection
  assert.deepEqual(byKey(voxelGrid(rows, spec({ value: 'runs' }), { drop: 'z' })), { '0,0,0': 2, '1,0,0': 1 });
  assert.deepEqual(byKey(voxelGrid(rows, spec(), { drop: 'x' })), { '0,0,0': 2, '0,0,1': 1, '0,0,2': 1 });
});

test('planeOf / kOf: the slice through a cell index, over the grid\'s whole extent on the other two axes', () => {
  const rows = [{ x: 1, y: 1, z: 1 }, { x: 1, y: 1, z: 1 }, { x: 21, y: 11, z: 1 }, { x: 1, y: 31, z: 12 }];
  const g = voxelGrid(rows, spec());
  assert.equal(kOf(g, 'z', 5), 0);
  assert.equal(kOf(g, 'z', 10), 1);
  const p = planeOf(g, 'z', 0);
  assert.deepEqual(p.plane, ['x', 'y']);
  assert.deepEqual([p.i0, p.j0, p.width, p.height], [0, 0, 3, 4]);
  assert.equal(p.values.length, 4);            // rows: y from j0 up
  assert.equal(p.values[0][0], 2);
  assert.equal(p.values[1][2], 1);
  assert.equal(p.values[3][0], null);          // that cell holds rows only at z = 1
  assert.equal(planeOf(g, 'z', 1).values[3][0], 1);
  const side = planeOf(g, 'x', 0);
  assert.deepEqual(side.plane, ['y', 'z']);
});

// OKLab, for the ramp's checks (Björn Ottosson's matrices)
const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
function oklab([r8, g8, b8]) {
  const [r, g, b] = [r8, g8, b8].map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
}
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const hue = (hex) => { const [, a, b] = oklab(rgbOf(hex)); return ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360; };
const chroma = (hex) => { const [, a, b] = oklab(rgbOf(hex)); return Math.hypot(a, b); };
const L = (hex) => oklab(rgbOf(hex))[0];
const gap = (a, b) => { const d = Math.abs(a - b) % 360; return Math.min(d, 360 - d); };

test('sequentialRamp: one hue, light to dark in a light theme and the other way in a dark one; grey with no family', () => {
  const light = sequentialRamp({ base: '#2a78d6', dark: false, bg: '#ffffff', fg: '#09090b' });
  const dark = sequentialRamp({ base: '#3987e5', dark: true, bg: '#09090b', fg: '#fafafa' });
  for (const r of [light, dark]) {
    assert.match(r.lo, /^#[0-9a-f]{6}$/);
    assert.match(r.hi, /^#[0-9a-f]{6}$/);
    assert.ok(gap(hue(r.hi), hue('#2a78d6')) <= 12, `${r.hi}'s hue ${hue(r.hi)}`);
    assert.ok(chroma(r.hi) >= 0.03, `${r.hi} is not grey`);
    assert.equal(r.at(0), r.lo);
    assert.equal(r.at(1), r.hi);
    // monotonic lightness along the ramp
    const ls = [0, 0.25, 0.5, 0.75, 1].map((t) => L(r.at(t)));
    for (let i = 1; i < ls.length; i++) assert.ok(r === light ? ls[i] < ls[i - 1] : ls[i] > ls[i - 1], `${r === light ? 'light' : 'dark'} step ${i}: ${ls}`);
  }
  assert.ok(L(light.lo) > 0.85, 'light: the low end recedes toward the surface');
  assert.ok(L(dark.lo) < 0.4, 'dark: the low end recedes toward the dark surface');
  const grey = sequentialRamp({ base: null, dark: false, bg: '#ffffff', fg: '#09090b' });
  assert.ok(chroma(grey.lo) < 0.02 && chroma(grey.hi) < 0.02, `${grey.lo} ${grey.hi} grey`);
  assert.ok(L(grey.lo) > L(grey.hi));
  const greyDark = sequentialRamp({ base: null, dark: true, bg: '#09090b', fg: '#fafafa' });
  assert.ok(chroma(greyDark.lo) < 0.02 && chroma(greyDark.hi) < 0.02 && L(greyDark.lo) < L(greyDark.hi));
});
