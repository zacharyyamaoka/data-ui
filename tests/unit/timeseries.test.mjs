// The time series and trajectory cards' compilers (docs/peps/0005-dashboard-cards.md §2b): series naming, the
// palette and the dash rule, windowing and min/max decimation, nearest sample, interpolation along t, equal aspect.
// The pure parts run as they are; compileTimeseries / compileTrajectory are bundled with esbuild against the core's
// own modules (the chart bundle imports '@data-ui/core', which the browser build resolves to dist/data-ui.js).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const S = await import('../../packages/views/chart/src/series.js');
const { seriesColor } = await import('../../packages/core/src/clock.js');

// the chart bundle's compilers, with '@data-ui/core' pointed at the core's pure modules and Vega left out (only embed
// draws; the compilers return specs)
const shim = `export { cellValue } from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { esc, fmtNum, numOpts, isNum } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { clockFor, fmtTime, seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};
export { SeriesLegend } from ${JSON.stringify(join(ROOT, 'packages/core/src/legend.js'))};`;
const out = await build({
  stdin: { contents: `export { compileTimeseries } from './timeseries.js'; export { compileTrajectory } from './trajectory.js';`, resolveDir: join(ROOT, 'packages/views/chart/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onResolve({ filter: /^vega-embed$/ }, () => ({ path: 'embed', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    b.onLoad({ filter: /^embed$/, namespace: 'shim' }, () => ({ contents: 'export default () => { throw new Error("no Vega in unit tests"); };', loader: 'js' }));
  } }],
});
const { compileTimeseries, compileTrajectory } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);

const tokens = { fg: 'rgb(9, 9, 11)', muted: 'rgb(113, 113, 122)', rule: 'rgb(236, 236, 239)', border: 'rgb(228, 228, 231)', subtle: 'rgb(244, 244, 245)',
  accent: 'rgb(24, 24, 27)', bg: 'rgb(255, 255, 255)', good: 'rgb(113, 113, 122)', bad: 'rgb(113, 113, 122)', warn: 'rgb(180, 83, 9)', font: 'system-ui',
  series: ['#s1', '#s2', '#s3', '#s4', '#s5', '#s6', '#s7', '#s8'], css: {} };
const read = (row, f) => row[f];
const label = (f) => ({ q: 'Angle', q_target: 'Target' }[f] || f);
const palette = { target: '#8b9099', factory: '#e8743b', tuned: '#2a78d6' };

test('series names: the split value; several y columns "<value> · <label>"; no split, the column label', () => {
  const rows = [{ t: 0, s: 'tuned', q: 1, q_target: 1.1 }, { t: 1, s: 'factory', q: 2, q_target: 2.1 }, { t: 2, s: null, q: 3, q_target: null }];
  assert.deepEqual(S.longRows(rows, { x: 't', y: 'q', series: 's' }, { read, label }).list.map((s) => s.name), ['tuned', 'factory', '—']);
  assert.deepEqual(S.longRows(rows, { x: 't', y: ['q', 'q_target'], series: 's' }, { read, label }).list.map((s) => s.name),
    ['tuned · Angle', 'tuned · Target', 'factory · Angle', 'factory · Target', '— · Angle']);
  assert.deepEqual(S.longRows(rows, { x: 't', y: ['q', 'q_target'] }, { read, label }).list.map((s) => s.name), ['Angle', 'Target']);
  // a missing value is left out, never drawn as 0
  assert.equal(S.longRows(rows, { x: 't', y: ['q_target'] }, { read, label }).points.length, 2);
});

test('palette by series name, dashed "target" (or listed) and muted when the palette does not name it', () => {
  const list = ['target', 'factory', 'tuned', 'oracle', 'model'].map((name) => ({ name, value: name, column: 'q' }));
  const input = { tokens, view: { style: { palette } } };
  const got = S.seriesStyles(list, { palette, dash: ['model'], slot: (n) => seriesColor(n, input), muted: tokens.muted });
  assert.deepEqual(got.map((s) => [s.name, s.dashed, s.color]), [
    ['target', true, '#8b9099'], ['factory', false, '#e8743b'], ['tuned', false, '#2a78d6'],
    ['oracle', false, seriesColor('oracle', input)], ['model', true, tokens.muted]]);
  assert.ok(tokens.series.includes(got[3].color), 'a name the palette lacks takes a stable series slot');
  // a composite name keeps its split value's palette colour and dash, and a dash: entry may name a column
  const [a, b] = S.seriesStyles([{ name: 'target · Angle', value: 'target', column: 'q' }, { name: 'tuned · Target', value: 'tuned', column: 'q_target' }],
    { palette, dash: ['q_target'], slot: () => '#slot', muted: tokens.muted });
  assert.deepEqual([a.dashed, a.color, b.dashed, b.color], [true, '#8b9099', true, '#2a78d6']);
});

test('windowed keeps one neighbour each side; decimate keeps first, min, max, last per pixel column', () => {
  const pts = Array.from({ length: 10 }, (_v, i) => ({ x: i, value: i % 3 }));
  assert.deepEqual(S.windowed(pts, 3.5, 6.2).map((p) => p.x), [3, 4, 5, 6, 7]);
  assert.equal(S.decimate(pts, 0, 9, 2), pts, 'under the limit nothing changes');
  const n = 100000;
  const dense = Array.from({ length: n }, (_v, i) => ({ x: i / n, value: Math.sin(i / 50) + (i === 77777 ? 9 : 0) }));
  const few = S.decimate(dense, 0, 1, 200);
  assert.ok(few.length <= 800 && few.length >= 200, few.length);
  assert.ok(few.includes(dense[77777]), 'a one-sample spike survives');
  assert.deepEqual([few[0], few[few.length - 1]], [dense[0], dense[n - 1]]);
  for (let i = 1; i < few.length; i++) assert.ok(few[i].x >= few[i - 1].x, 'in x order');
  const lo = Math.min(...dense.map((p) => p.value)), hi = Math.max(...dense.map((p) => p.value));
  assert.deepEqual([Math.min(...few.map((p) => p.value)), Math.max(...few.map((p) => p.value))], [lo, hi]);
});

test('nearest sample and interpolation along t', () => {
  const pts = [{ x: 0, value: 1 }, { x: 1, value: 2 }, { x: 2, value: 5 }];
  assert.deepEqual([S.nearest(pts, 0.4).value, S.nearest(pts, 0.6).value, S.nearest(pts, 2).value, S.nearest(pts, 2.5)], [1, 2, 5, null]);
  assert.deepEqual(S.along([0, 1, 2], [0, 10, 10], [0, 0, 20], 1.25), [10, 5, 1]);
  assert.deepEqual(S.along([0, 1, 2], [0, 10, 10], [0, 0, 20], -3).slice(0, 2), [0, 0]);
  assert.deepEqual(S.along([0, 1, 2], [0, 10, 10], [0, 0, 20], 9).slice(0, 2), [10, 20]);
});

test('equal aspect: one data unit is the same px on x and y, the data centred and inside', () => {
  for (const [w, h] of [[500, 300], [300, 500], [400, 400]]) {
    const d = S.equalAspect([-0.72, -0.49], [0.30, 0.60], w, h);
    const ux = w / (d.x[1] - d.x[0]), uy = h / (d.y[1] - d.y[0]);
    assert.ok(Math.abs(ux - uy) < 1e-9 && Math.abs(ux - d.unit) < 1e-9, `${w}x${h}: ${ux} vs ${uy}`);
    assert.ok(d.x[0] < -0.72 && d.x[1] > -0.49 && d.y[0] < 0.30 && d.y[1] > 0.60);
    assert.ok(Math.abs((d.x[0] + d.x[1]) / 2 - -0.605) < 1e-12 && Math.abs((d.y[0] + d.y[1]) / 2 - 0.45) < 1e-12);
  }
});

const columns = {
  t: { id: 't', label: 't', type: 'number', unit: 's' }, s: { id: 's', label: 'Gains', type: 'text' },
  q: { id: 'q', label: 'Angle', type: 'number', unit: '°' }, day: { id: 'day', label: 'Day', type: 'date' },
  px: { id: 'px', label: 'px', type: 'number', unit: 'm' }, pz: { id: 'pz', label: 'pz', type: 'number', unit: 'm' },
};
const rowsOf = (n) => ['target', 'factory', 'tuned'].flatMap((s, k) => Array.from({ length: n }, (_v, i) => ({ t: i / 100, s, q: Math.sin(i / 30) + k, px: Math.cos(i / 40) * 0.1 + k * 0.01, pz: Math.sin(i / 40) * 0.05 })));

test('compileTimeseries: the palette and dashes ride an explicit scale; target dashed; the window is two signals', () => {
  const input = { rows: rowsOf(200), columns, tokens, view: { type: 'timeseries', style: { chrome: 'minimal', palette }, timeseries: { x: 't', y: 'q', series: 's', rules: [{ y: 1, label: 'gate', tone: 'bad' }] } } };
  const a = compileTimeseries(input, { width: 600, height: 200 });
  const line = a.spec.layer.find((l) => l.name === 'series');
  assert.deepEqual(line.encoding.color.scale, { domain: ['target', 'factory', 'tuned'], range: ['#8b9099', '#e8743b', '#2a78d6'] });
  assert.deepEqual(line.encoding.strokeDash.scale.range, [[5, 4], [], []]);
  assert.equal(line.mark.strokeWidth, 1.5);
  assert.equal(line.encoding.y.axis.grid, true);
  assert.equal(line.encoding.x.axis.grid, false);
  assert.deepEqual([line.encoding.x.axis.domain, line.encoding.x.axis.ticks, line.encoding.y.axis.domain, line.encoding.y.axis.ticks], [false, false, false, false]);
  assert.deepEqual(a.meta.extent, [0, 1.99]);
  assert.deepEqual(a.spec.params.map((p) => [p.name, p.value]), [['xmin', 0], ['xmax', 1.99]]);
  assert.equal(a.datasets.series.length, 600);
  assert.equal(a.meta.unit, '°');
  // a zoom: same key (no re-embed), new signal values and only the window's samples (+1 each side)
  const b = compileTimeseries(input, { width: 600, height: 200, win: [0.5, 0.6] });
  assert.equal(b.key, a.key);
  assert.deepEqual(b.spec.params.map((p) => p.value), [0.5, 0.6]);
  assert.equal(b.datasets.series.length, 3 * 13);
  // chrome full keeps the axis lines
  const c = compileTimeseries({ ...input, view: { ...input.view, style: { chrome: 'full' } } }, { width: 600, height: 200 });
  assert.equal(c.spec.layer.find((l) => l.name === 'series').encoding.x.axis.domain, true);
});

test('compileTimeseries: a date x has no window signals; dense series are decimated for drawing only', () => {
  const rows = Array.from({ length: 30 }, (_v, i) => ({ day: `2026-10-${String(i + 1).padStart(2, '0')}`, q: i }));
  const a = compileTimeseries({ rows, columns, tokens, view: { timeseries: { x: 'day', y: 'q' } } }, { width: 400, height: 200 });
  assert.equal(a.meta.temporal, true);
  assert.equal(a.spec.params, undefined);
  assert.equal(a.spec.layer.find((l) => l.name === 'series').encoding.x.type, 'temporal');
  const dense = compileTimeseries({ rows: rowsOf(5000), columns, tokens, view: { timeseries: { x: 't', y: 'q', series: 's' } } }, { width: 300, height: 200 });
  assert.ok(dense.meta.decimated && dense.datasets.series.length <= 3 * 4 * 301, dense.datasets.series.length);
  assert.equal(dense.meta.series[0].points.length, 5000, 'the readout keeps every sample');
});

test('compileTrajectory: equal-aspect domains, the tolerance tube 2 × tolerance in px, the target dashed', () => {
  const input = { rows: rowsOf(300), columns, tokens, view: { style: { palette }, trajectory: { x: 'px', y: 'pz', series: 's', target: 'target', t: 't', trail: true, tolerance: 0.005 } } };
  const a = compileTrajectory(input, { width: 500, height: 400 });
  const p = Object.fromEntries(a.spec.params.map((x) => [x.name, x.value]));
  const ux = (500 - 44) / (p.xmax - p.xmin), uy = (400 - 34) / (p.ymax - p.ymin);
  assert.ok(Math.abs(ux - uy) < 1e-9, `${ux} vs ${uy}`);
  assert.ok(Math.abs(p.tube - 2 * 0.005 * ux) < 1e-9);
  const tube = a.spec.layer.find((l) => l.name === 'tolerance');
  assert.deepEqual(tube.transform, [{ filter: { field: 'series', equal: 'target' } }]);
  assert.deepEqual(tube.mark.strokeWidth, { expr: 'tube' });
  const paths = a.spec.layer.find((l) => l.name === 'paths');
  assert.deepEqual(paths.encoding.strokeDash.scale.range, [[5, 4], [], []]);
  assert.deepEqual(paths.encoding.opacity.scale.range, [0.9, 0.28, 0.28], 'trail: the moving paths faint until the overlay draws them');
  assert.deepEqual(paths.encoding.order, { field: 'i', type: 'quantitative' }, 'a path in time order, not sorted by x');
  assert.deepEqual([a.meta.timed, a.meta.t, a.meta.unit], [true, [0, 2.99], 'm']);
});
