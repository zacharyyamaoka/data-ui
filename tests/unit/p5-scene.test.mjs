// PEP 0010 P5 in the 3D bundle (docs/CONTRACT.md §35), pure: path_overlay's binding (`trajectory3d.color` puts each
// non-target path's own numbers on its vertices, in time order, with the drawn min..max; `tolerance` names the target's
// paths for the tube) and its ramp (series 1 to the warn tone, OKLab); `voxels.scale: verdict` (bad through warn to good
// over the domain, `better: higher` by default, `lower` flips it; ✕ and ✓ at the bar's ends). bind.js and voxels/view.js
// import '@data-ui/core'; they are bundled here against the core's own modules (as scene3d-bind.test.mjs does). The
// browser half (the vertex colours and the tube's radius read back from the GPU buffers) is tests/browser/p5_checks.py.
// Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verdictRamp, twoColorRamp, parseColor } from '../../packages/views/scene3d/src/voxels/ramp.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const shim = `export { cellValue } from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { mediaUrl, esc } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};`;
async function bundle(entry) {
  const out = await build({
    stdin: { contents: entry, resolveDir: join(ROOT, 'packages/views/scene3d/src') },
    bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
    plugins: [{ name: 'shim', setup(b) {
      b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
      b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    } }],
  });
  return import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);
}
const B = await bundle(`export * from './bind.js';`);

const near = (a, b, tol = 1) => { const x = parseColor(a), y = parseColor(b); return !!x && !!y && x.every((c, i) => Math.abs(c - y[i]) <= tol); };
const tokens = { series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'], muted: '#71717a', css: {},
  tone: { good: '#1a8a5a', warn: '#c98a0c', bad: '#d1453b', muted: '#d4d4d8', neutral: '#a1a1aa' } };
const FAMILIES = { property: 'source', colors: { real: 1, sim: 2, target: 'muted' } };
function poses() {
  const out = [];
  for (const [situation, source] of [['real', 'real'], ['twin', 'sim'], ['target', 'target']]) {
    for (let k = 0; k < 6; k++) out.push({ t: k / 10, run: 'r1', situation, source, body: 'tool0', frame: 'base', x_mm: 10 * k, y_mm: situation === 'target' ? 0 : 1, z_mm: 0,
      quat_w: 1, quat_x: 0, quat_y: 0, quat_z: 0, err_mm: situation === 'target' ? 0 : (situation === 'real' ? k : 2 * k) + 0.5 });
  }
  return out.reverse();   // file order is not time order: the binding sorts
}
const input = (block) => { const r = poses(); return { rows: r, columns: Object.fromEntries(Object.keys(r[0]).map((k) => [k, { id: k, type: typeof r[0][k] === 'number' ? 'number' : 'text' }])), tokens, layers: {},
  view: { type: 'trajectory3d', name: 'T', from: 'poses', style: { families: FAMILIES }, trajectory3d: block }, dataset: { url: 'http://x/poses.json' } }; };

test('trajectory3d.color: each non-target path carries its own numbers per vertex, in time order; the overlay its min..max', () => {
  const m = B.bindTrajectory(input({ color: 'err_mm' }));
  const byName = Object.fromEntries(m.lines.map((p) => [p.seriesName, p]));
  assert.deepEqual(Array.from(byName.real.values), [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]);
  assert.deepEqual(Array.from(byName.twin.values), [0.5, 2.5, 4.5, 6.5, 8.5, 10.5]);
  assert.ok(!m.targetLines[0].values, 'the target is not painted');
  assert.deepEqual([m.overlay.color, m.overlay.min, m.overlay.max], ['err_mm', 0.5, 10.5]);
  // without color: no numbers
  const plain = B.bindTrajectory(input({}));
  assert.ok(plain.lines.every((p) => !p.values) && (!plain.overlay || plain.overlay.color == null));
});

test('trajectory3d.tolerance: the tube\'s radius and the target\'s paths; none without a target or a tolerance', () => {
  const m = B.bindTrajectory(input({ tolerance: 5 }));
  assert.equal(m.tube.radius, 5);
  assert.deepEqual(m.tube.paths.map((p) => [p.seriesName, p.n]), [['target', 6]]);
  assert.equal(B.bindTrajectory(input({})).tube, null);
  // a tolerance that is not a positive number draws no tube
  assert.equal(B.bindTrajectory(input({ tolerance: 0 })).tube, null);
});

test('twoColorRamp: OKLab between two colours, the ends exact to a unit; path_overlay\'s is series 1 to the warn tone', () => {
  const r = twoColorRamp('#2a78d6', '#c98a0c');
  assert.ok(near(r.at(0), '#2a78d6') && near(r.at(1), '#c98a0c'), `${r.at(0)} ${r.at(1)}`);
  assert.ok(near(r.at(-1), '#2a78d6') && near(r.at(2), '#c98a0c'), 'clamped');
  assert.notEqual(r.at(0.5), r.at(0));
});

test('verdictRamp: bad through warn to good, higher better by default; lower flips it', () => {
  const t = tokens.tone;
  const hi = verdictRamp({ bad: t.bad, warn: t.warn, good: t.good });
  assert.ok(near(hi.at(0), t.bad) && near(hi.at(0.5), t.warn) && near(hi.at(1), t.good), `${hi.at(0)} ${hi.at(0.5)} ${hi.at(1)}`);
  const lo = verdictRamp({ bad: t.bad, warn: t.warn, good: t.good, better: 'lower' });
  assert.ok(near(lo.at(0), t.good) && near(lo.at(1), t.bad));
  assert.ok(near(hi.lo, t.bad) && near(hi.hi, t.good));
});

const V = await bundle(`export * from './voxels/view.js';`);
test('voxels scale: verdict: the model\'s ramp is the verdict ramp from the tone tokens; the bar carries ✕ and ✓', () => {
  const rows = [0, 1, 2, 3, 4].map((i) => ({ x_mm: 25 * i + 12.5, y_mm: 12.5, z_mm: 12.5, value: i / 4 }));
  const spec = { x: 'x_mm', y: 'y_mm', z: 'z_mm', cell: 25, value: 'value', scale: 'verdict' };
  const inp = { rows, columns: {}, tokens, view: { type: 'voxels', name: 'R', style: {}, voxels: spec } };
  const m = V.voxelsModel(inp, spec, { projection: 'perspective', up: 'z' });
  assert.ok(near(V.colourOf(m, m.domain[0]), tokens.tone.bad) && near(V.colourOf(m, m.domain[1]), tokens.tone.good), `${V.colourOf(m, m.domain[0])} ${V.colourOf(m, m.domain[1])}`);
  const bar = V.rampHtml(m, spec, {});
  assert.ok(bar.includes('✕') && bar.includes('✓') && bar.indexOf('✕') < bar.indexOf('✓'), bar);
  const lower = { ...spec, better: 'lower' };
  const ml = V.voxelsModel({ ...inp, view: { ...inp.view, voxels: lower } }, lower, { projection: 'perspective', up: 'z' });
  assert.ok(near(V.colourOf(ml, ml.domain[0]), tokens.tone.good) && near(V.colourOf(ml, ml.domain[1]), tokens.tone.bad));
  // sequential stays as it was: never the tones
  const seq = V.voxelsModel({ ...inp, view: { ...inp.view, voxels: { ...spec, scale: 'sequential' } } }, { ...spec, scale: 'sequential' }, { projection: 'perspective', up: 'z' });
  assert.ok(!near(V.colourOf(seq, seq.domain[1]), tokens.tone.good, 12));
});
