// scene3d / trajectory3d's bindings (packages/views/scene3d/src/bind.js; docs/CONTRACT.md §32): from a view's input to
// paths, items, robots and the legend, with no three.js. The trajectory contract's defaults, families and their member
// dash patterns, opacity: auto, modes routing, frames never mixed, compare's default pairs read from the difference
// rows, robots' colours, and a layer split by its colour column. bind.js imports '@data-ui/core'; it is bundled here
// against the core's own modules (as timeseries.test.mjs bundles the chart's compilers).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const shim = `export { cellValue } from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { mediaUrl } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};`;
const out = await build({
  stdin: { contents: `export * from './bind.js';`, resolveDir: join(ROOT, 'packages/views/scene3d/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
  } }],
});
const B = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);

const tokens = { series: ['#s1', '#s2', '#s3', '#s4', '#s5', '#s6', '#s7', '#s8'], muted: '#mu', css: {} };
const FAMILIES = { property: 'source', colors: { real: 1, sim: 2, target: 'muted' } };

function rows(spec) {
  // spec: [[situation, source, run, n, frame?]] → poses rows on a line, 10 Hz
  const out = [];
  for (const [situation, source, run, n, frame = 'base'] of spec) {
    for (let k = 0; k < n; k++) out.push({ t: k / 10, run, situation, source, body: 'tool0', frame, x_mm: k, y_mm: 2 * k, z_mm: 100, quat_w: 1, quat_x: 0, quat_y: 0, quat_z: 0 });
  }
  return out;
}
const input = (r, block = {}, style = { families: FAMILIES }, layers = {}) => ({
  rows: r, columns: Object.fromEntries(Object.keys(r[0] || {}).map((k) => [k, { id: k }])), tokens, layers,
  view: { type: 'trajectory3d', name: 'T', from: 'poses', style, trajectory3d: block }, dataset: { url: 'http://x/data/poses.json' },
});

test('trajectory3d defaults: the contract\'s columns, mm, one path per situation, run and body, in time order', () => {
  const m = B.bindTrajectory(input(rows([['real', 'real', 'r1', 5], ['target', 'target', 'r1', 5]]).reverse()));
  assert.equal(m.stage.unit, 'mm');
  assert.equal(m.stage.show, 'all');
  assert.equal(m.stage.decay, 'inf');
  assert.equal(m.stage.density, 20);
  assert.deepEqual(m.series.map((s) => s.name).sort(), ['real', 'target']);
  const real = m.paths.find((p) => p.seriesName === 'real');
  assert.deepEqual([...real.t], [0, 0.1, 0.2, 0.3, 0.4]);   // sorted, although the rows came reversed
  assert.equal(real.key, 'real');
  assert.equal(m.frame, 'base');
});

test('families: real slot 1, sim slot 2, target muted; an unlisted family and a two-family series are unclassified (muted, dotted)', () => {
  const r = rows([['real', 'real', 'r1', 3], ['twin', 'sim', 'r1', 3], ['target', 'target', 'r1', 3], ['replay', 'replay', 'r1', 3], ['mix', 'real', 'r1', 2], ['mix', 'sim', 'r2', 2]]);
  const m = B.bindTrajectory(input(r));
  const by = Object.fromEntries(m.series.map((s) => [s.name, s]));
  assert.equal(by.real.css, '#s1');
  assert.equal(by.twin.css, '#s2');
  assert.equal(by.target.css, '#mu');
  assert.equal(by.replay.css, '#mu');
  assert.equal(by.mix.css, '#mu');
  assert.deepEqual(by.target.dash, B.DASH.target);
  assert.deepEqual(by.replay.dash, B.DASH.dotted);
  assert.equal(by.replay.classified, false);
  assert.equal(by.real.classified, true);
  const legend = Object.fromEntries(m.legend.map((e) => [e.name, e.extra]));
  assert.match(legend.replay, /unclassified/);
  assert.equal(legend.real, '');
});

test('a family\'s members in natural order: solid, long dash 8 4, dash-dot 8 3 2 3; four or more: one hue, one legend entry', () => {
  const three = B.bindTrajectory(input(rows([['real 2', 'real', 'r1', 2], ['real', 'real', 'r1', 2], ['real 10', 'real', 'r1', 2]])));
  const d = Object.fromEntries(three.series.map((s) => [s.name, s.dash]));
  assert.deepEqual(d.real, B.DASH.solid);
  assert.deepEqual(d['real 2'], B.DASH.long);
  assert.deepEqual(d['real 10'], B.DASH.dashdot);
  const four = B.bindTrajectory(input(rows([['a', 'sim', 'r1', 2], ['b', 'sim', 'r1', 2], ['c', 'sim', 'r1', 2], ['d', 'sim', 'r1', 2]])));
  assert.ok(four.series.every((s) => s.css === '#s2' && s.legendName === 'sim' && s.dash === B.DASH.solid));
  assert.equal(four.legend.length, 1);
  assert.match(four.legend[0].extra, /4 series/);
  assert.ok(four.paths.every((p) => Math.abs(p.alpha - 0.25) < 1e-12));   // opacity auto over the family's 4 paths
});

test('opacity: auto is exactly 1/n over a family\'s n paths, no floor (PEP 0010 P2); a number is that opacity', () => {
  const many = [];
  for (let k = 0; k < 40; k++) many.push(['real', 'real', `r${k}`, 2]);
  const m = B.bindTrajectory(input(rows(many)));
  assert.equal(m.paths.length, 40);
  // WHY 1/40, not P1b's 0.04: Zach's brief for P2 removed the floor, so a region crossed by more runs reads darker
  assert.ok(m.paths.every((p) => p.alpha === 1 / 40));
  assert.equal(B.autoOpacity(10), 0.1);
  const fixed = B.bindTrajectory(input(rows([['real', 'real', 'r1', 2], ['real', 'real', 'r2', 2]]), { opacity: 0.7 }));
  assert.ok(fixed.paths.every((p) => p.alpha === 0.7));
  // a series with several paths names each marker "<series> · <run>"
  assert.deepEqual(fixed.paths.map((p) => p.key).sort(), ['real · r1', 'real · r2']);
});

test('modes route each path: line (the target to its own, on-top layer), points, frames, frames-z', () => {
  const m = B.bindTrajectory(input(rows([['real', 'real', 'r1', 3], ['twin', 'sim', 'r1', 3], ['target', 'target', 'r1', 3]]),
    { modes: { real: ['line', 'points', 'frames-z'], twin: ['frames'] } }));
  const names = (list) => list.map((p) => p.seriesName).sort();
  assert.deepEqual(names(m.lines), ['real']);
  assert.deepEqual(names(m.targetLines), ['target']);
  assert.deepEqual(names(m.points), ['real']);
  assert.deepEqual(names(m.frames), ['twin']);
  assert.deepEqual(names(m.framesZ), ['real']);
});

test('frames are never mixed: rows in two frames draw nothing and the problem names both', () => {
  const m = B.bindTrajectory(input(rows([['real', 'real', 'r1', 3, 'base'], ['real', 'real', 'r2', 3, 'belt']])));
  assert.ok(m.problem && /base/.test(m.problem) && /belt/.test(m.problem));
  assert.equal(m.paths.length, 0);
});

test('compare: arrows from a(t) to b(t) read from the difference rows (never computed here), at the density; Z-arcs where a draws frames-z', () => {
  const diff = [];
  for (let k = 0; k < 40; k++) diff.push({ t: k / 10, run: 'r1', situation: 'real', source: 'real', reference: 'target', body: 'tool0', frame: 'base',
    x_mm: k, y_mm: 0, z_mm: 0, ref_x_mm: k, ref_y_mm: 3, ref_z_mm: 0, quat_w: 1, quat_x: 0, quat_y: 0, quat_z: 0, ref_quat_w: 1, ref_quat_x: 0, ref_quat_y: 0, ref_quat_z: 0 });
  for (let k = 0; k < 40; k++) diff.push({ ...diff[k], situation: 'twin', source: 'sim', reference: 'real' });
  const layers = { diff: { rows: diff, url: 'http://x/data/diff.json' } };
  const r = rows([['real', 'real', 'r1', 40], ['twin', 'sim', 'r1', 40], ['target', 'target', 'r1', 40]]);
  const m = B.bindTrajectory(input(r, { compare: { data: 'diff' }, modes: { real: ['line', 'frames-z'] } }, { families: FAMILIES }, layers));
  // the default pairs: every pair present whose b is the target (twin → real is present but not drawn by default)
  assert.deepEqual(m.compare.pairs, [['real', 'target']]);
  assert.equal(m.arrows.length, 21);   // 40 samples at density 20: stride 2, 0 … 38 (20), then the last, 39
  assert.deepEqual(m.arrows[1].from, [2, 0, 0]);
  assert.deepEqual(m.arrows[1].to, [2, 3, 0]);
  assert.equal(m.arcs.length, 21);
  const both = B.bindTrajectory(input(r, { compare: { data: 'diff', pairs: [['twin', 'real']], scale: 20 } }, { families: FAMILIES }, layers));
  assert.ok(both.arrows.every((a) => a.series === 'twin'));
  assert.equal(both.compare.scale, 20);
  const none = B.bindTrajectory(input(r, { compare: { data: 'nowhere' } }));
  assert.ok(none.notes.some((n) => /nowhere/.test(n)));
});

test('robots: one per series from its link rows (its first run), colour series | muted | slot | CSS, opacity, show; the model relative to the link file', () => {
  const link = (situation, run, k) => ({ t: k / 10, run, situation, source: 'x', base_x: 0, base_y: 0, base_z: 0, base_qw: 1, base_qx: 0, base_qy: 0, base_qz: 0 });
  const lrows = [];
  for (const s of ['real', 'twin', 'target']) for (const run of ['r1', 'r2']) for (let k = 0; k < 3; k++) lrows.push(link(s, run, k));
  const r = rows([['real', 'real', 'r1', 3], ['twin', 'sim', 'r1', 3], ['target', 'target', 'r1', 3]]);
  const m = B.bindTrajectory(input(r, { robots: { data: 'links', model: '../media/arm.glb', links: ['base'],
    series: { twin: { color: 5, opacity: 0.5 }, target: { color: 'muted', opacity: 0.2 }, real: { show: true } } } }, { families: FAMILIES }, { links: { rows: lrows, url: 'http://x/data/links/links.json' } }));
  const by = Object.fromEntries(m.robots.series.map((x) => [x.series, x]));
  assert.equal(m.robots.url, 'http://x/data/media/arm.glb');
  assert.equal(m.robots.scale, 1000);
  assert.equal(by.real.color, '#s1');
  assert.equal(by.real.opacity, 1);
  assert.equal(by.twin.color, '#s5');
  assert.equal(by.twin.opacity, 0.5);
  assert.equal(by.target.color, '#mu');
  assert.equal(by.real.rows.length, 3);    // its first run only
  assert.equal(by.real.runs, 2);
  assert.equal(B.robotColor('#123456', '#s1', tokens), '#123456');
  assert.equal(B.robotColor(0, '#s1', tokens), '#mu');
  const off = B.bindTrajectory(input(r, { robots: { data: 'links', model: 'a.glb', links: ['base'], series: { twin: { show: false } } } }, { families: FAMILIES }, { links: { rows: lrows } }));
  assert.ok(!off.robots.series.some((x) => x.series === 'twin'));
});

test('stage keys: their defaults (scene3d m, trajectory3d mm) and only the contract\'s values', () => {
  assert.equal(B.stageOf({}, 'scene3d').unit, 'm');
  assert.equal(B.stageOf({ decay: 0.5 }).decay, 0.5);
  assert.equal(B.stageOf({ decay: -1 }).decay, 'inf');
  assert.equal(B.stageOf({ show: 'trail' }).show, 'trail');
  assert.equal(B.stageOf({ show: 'nope' }).show, 'all');
  assert.equal(B.stageOf({ axes: 'none' }).axes, 'none');
  assert.equal(B.stageOf({ density: 0 }).density, 20);
  assert.equal(B.listText(['base', 'belt']), 'base and belt');
  assert.equal(B.listText(['a', 'b', 'c']), 'a, b and c');
});

test('scene3d.layers: one primitive per layer; a layer reads another dataset (input.layers) or the view\'s rows; its colour column splits its groups', () => {
  const r = rows([['real', 'real', 'r1', 4], ['twin', 'sim', 'r1', 4]]);
  const diff = r.map((x) => ({ ...x, ref_x_mm: x.x_mm + 1, ref_y_mm: x.y_mm, ref_z_mm: x.z_mm }));
  const view = { type: 'scene3d', name: 'L', from: 'poses', scene3d: { unit: 'mm', layers: [
    { primitive: 'lines', x: 'x_mm', y: 'y_mm', z: 'z_mm', by: 'run', color: 'situation' },
    { primitive: 'boxes', data: 'diff', min: ['x_mm', 'y_mm', 'z_mm'], max: ['ref_x_mm', 'ref_y_mm', 'ref_z_mm'], color: 'situation' },
    { primitive: 'arrows', data: 'missing', from: ['x_mm', 'y_mm', 'z_mm'], to: ['ref_x_mm', 'ref_y_mm', 'ref_z_mm'] },
  ] } };
  const m = B.bindLayers({ rows: r, tokens, view, layers: { diff: { rows: diff } }, dataset: {} });
  // lines by run, coloured by situation: one path per (run, situation), never a path through both
  assert.deepEqual(m.lines.map((p) => p.series).sort(), ['real', 'twin']);
  assert.equal(m.boxes.length, 8);
  assert.deepEqual([...new Set(m.boxes.map((b) => b.series))].sort(), ['real', 'twin']);
  assert.ok(m.notes.some((n) => /missing/.test(n)));
  assert.deepEqual(m.legend.map((e) => e.name), ['real', 'twin']);
});
