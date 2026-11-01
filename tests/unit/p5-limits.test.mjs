// PEP 0010 P5's threshold_band: `limits: {warn: [lo, hi], error: [lo, hi]}` (packages/core/src/guides.js `limitGuides`,
// the time series' compiler; docs/CONTRACT.md §35). RobotDx's Limits as data (the diagnostic row's warn_lo, warn_hi,
// error_lo, error_hi): each end a number, a property read per series from the drawn rows (a device's own limit), or null
// (no limit on that side). Per series: a rule at each limit present (warn in the warn tone, error in the bad tone, "! warn"
// and "✕ error"), and the zones beyond them (between a warn and an error limit in the warn tone; from an error limit, or a
// warn limit with nothing beyond it, to the plot's edge: an end of null). A constant spans the drawn rows' x; a limit that
// changes is a step line; a missing value is skipped, never 0; a series the legend hides draws none; series drawing the
// same line share it. The browser half (each device's own limits within 1 px) is tests/browser/p5_checks.py.
// Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { limitGuides } from '../../packages/core/src/guides.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (r, c) => r[c];
const L4 = { warn: ['warn_lo', 'warn_hi'], error: ['error_lo', 'error_hi'] };

function rows(spec) {
  // spec: {series: [[t, warn_lo, warn_hi, error_lo, error_hi]…]}
  const out = [];
  for (const [s, list] of Object.entries(spec)) for (const [t, wl, wh, el, eh] of list) out.push({ t, device: s, value: 1, warn_lo: wl, warn_hi: wh, error_lo: el, error_hi: eh });
  return out;
}
const find = (list, guide, series) => list.find((g) => g.guide === guide && g.series === series);

test('two devices, each its own warn and error limits: rules at each, the warn zone between, the error zone to the edge', () => {
  const r = rows({ A: [[0, null, 60, null, 70], [1, null, 60, null, 70], [2, null, 60, null, 70]], B: [[0, null, 50, null, 55], [1, null, 50, null, 55], [2, null, 50, null, 55]] });
  const g = limitGuides(r, L4, { x: 't', series: 'device', read });
  assert.deepEqual(g.rules.map((x) => [x.guide, x.series, x.tone, x.label, x.constant, x.points]), [
    ['limit:warn_hi', 'A', 'warn', '! warn', 60, [[0, 60], [2, 60]]],
    ['limit:warn_hi', 'B', 'warn', '! warn', 50, [[0, 50], [2, 50]]],
    ['limit:error_hi', 'A', 'bad', '✕ error', 70, [[0, 70], [2, 70]]],
    ['limit:error_hi', 'B', 'bad', '✕ error', 55, [[0, 55], [2, 55]]],
  ]);
  const wa = find(g.zones, 'zone:warn_hi', 'A'), ea = find(g.zones, 'zone:error_hi', 'A'), wb = find(g.zones, 'zone:warn_hi', 'B'), eb = find(g.zones, 'zone:error_hi', 'B');
  assert.deepEqual([wa.tone, wa.lo, wa.hi], ['warn', [[0, 60], [2, 60]], [[0, 70], [2, 70]]]);
  assert.deepEqual([ea.tone, ea.lo, ea.hi], ['bad', [[0, 70], [2, 70]], [[0, null], [2, null]]]);
  assert.deepEqual([wb.lo, wb.hi, eb.lo, eb.hi], [[[0, 50], [2, 50]], [[0, 55], [2, 55]], [[0, 55], [2, 55]], [[0, null], [2, null]]]);
  assert.equal(g.zones.length, 4);
  // no rule or zone on the lower side: every lower limit is null
  assert.ok(!g.rules.some((x) => /_lo$/.test(x.guide)) && !g.zones.some((x) => /_lo$/.test(x.guide)));
});

test('a warn limit with no error limit beyond it: its zone runs to the edge, in the warn tone', () => {
  const r = rows({ A: [[0, null, 60, null, null], [3, null, 60, null, null]] });
  const g = limitGuides(r, { warn: [null, 'warn_hi'] }, { x: 't', series: 'device', read });
  assert.deepEqual(g.rules.map((x) => x.guide), ['limit:warn_hi']);
  const z = find(g.zones, 'zone:warn_hi', 'A');
  assert.deepEqual([g.zones.length, z.tone, z.lo, z.hi], [1, 'warn', [[0, 60], [3, 60]], [[0, null], [3, null]]]);
});

test('the lower side mirrors it: the warn zone between error_lo and warn_lo, the error zone from the edge up to error_lo', () => {
  const r = rows({ A: [[0, 0, null, -10, null], [2, 0, null, -10, null]] });
  const g = limitGuides(r, L4, { x: 't', series: 'device', read });
  assert.deepEqual(g.rules.map((x) => [x.guide, x.constant]), [['limit:warn_lo', 0], ['limit:error_lo', -10]]);
  const w = find(g.zones, 'zone:warn_lo', 'A'), e = find(g.zones, 'zone:error_lo', 'A');
  assert.deepEqual([w.tone, w.lo, w.hi], ['warn', [[0, -10], [2, -10]], [[0, 0], [2, 0]]]);
  assert.deepEqual([e.tone, e.lo, e.hi], ['bad', [[0, null], [2, null]], [[0, -10], [2, -10]]]);
});

test('a number is the same limit for every series: one shared rule', () => {
  const r = rows({ A: [[0, null, null, null, null], [1, null, null, null, null]], B: [[0, null, null, null, null], [2, null, null, null, null]] });
  const g = limitGuides(r, { error: [null, 70] }, { x: 't', series: 'device', read });
  assert.equal(g.rules.length, 1);
  assert.deepEqual([g.rules[0].guide, g.rules[0].constant, g.rules[0].shared, g.rules[0].points], ['limit:error_hi', 70, ['A', 'B'], [[0, 70], [2, 70]]]);
});

test('a limit that changes over time is a step line through its values; a missing value is skipped, never 0', () => {
  const r = rows({ A: [[0, null, 60, null, null], [1, null, 65, null, null], [2, null, 65, null, null]] });
  const g = limitGuides(r, { warn: [null, 'warn_hi'] }, { x: 't', series: 'device', read });
  assert.deepEqual([g.rules[0].constant, g.rules[0].points], [null, [[0, 60], [1, 65], [2, 65]]]);
  const gap = limitGuides(rows({ A: [[0, null, 60, null, null], [1, null, null, null, null], [2, null, 60, null, null]] }), { warn: [null, 'warn_hi'] }, { x: 't', series: 'device', read });
  assert.deepEqual([gap.rules[0].constant, gap.rules[0].points], [60, [[0, 60], [2, 60]]]);
});

test('a series the legend hides draws no limit; series drawing the same line share one', () => {
  const r = rows({ A: [[0, null, 60, null, null], [2, null, 60, null, null]], B: [[0, null, 50, null, null], [4, null, 50, null, null]], C: [[0, null, 60, null, null], [2, null, 60, null, null]] });
  const g = limitGuides(r, { warn: [null, 'warn_hi'] }, { x: 't', series: 'device', read, hidden: ['B'] });
  assert.deepEqual(g.rules.map((x) => [x.series, x.shared, x.points]), [['A', ['A', 'C'], [[0, 60], [2, 60]]]]);
  assert.ok(!g.zones.some((z) => z.series === 'B'));
});

test('no series column: one series (null); no limits: nothing', () => {
  const r = rows({ A: [[0, null, 60, null, 70], [2, null, 60, null, 70]] });
  const g = limitGuides(r, L4, { x: 't', series: null, read });
  assert.deepEqual(g.rules.map((x) => [x.guide, x.series]), [['limit:warn_hi', null], ['limit:error_hi', null]]);
  assert.deepEqual(limitGuides(r, {}, { x: 't', series: 'device', read }), { rules: [], zones: [] });
  assert.deepEqual(limitGuides([], L4, { x: 't', series: 'device', read }), { rules: [], zones: [] });
});

// the time series' compiler, bundled against the core's own modules (as timeseries.test.mjs does)
const shim = `export { cellValue } from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { esc, fmtNum, numOpts, isNum } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { clockFor, fmtTime, seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};
export { SeriesLegend } from ${JSON.stringify(join(ROOT, 'packages/core/src/legend.js'))};`;
const out = await build({
  stdin: { contents: `export { compileTimeseries } from './timeseries.js';`, resolveDir: join(ROOT, 'packages/views/chart/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onResolve({ filter: /^vega-embed$/ }, () => ({ path: 'embed', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    b.onLoad({ filter: /^embed$/, namespace: 'shim' }, () => ({ contents: 'export default () => { throw new Error("no Vega in unit tests"); };', loader: 'js' }));
  } }],
});
const { compileTimeseries } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);
const tokens = { fg: '#111', muted: '#777', rule: '#eee', bg: '#fff', good: '#0a0', warn: '#c80', bad: '#c00', series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'], css: {}, font: 'sans-serif', tone: { good: '#1a8a5a', warn: '#c98a0c', bad: '#d1453b', muted: '#ccc', neutral: '#999' } };

test('the time series draws them: the guides dataset holds every limit\'s points and every zone\'s, an edge as null', () => {
  const r = rows({ A: [[0, null, 60, null, 70], [2, null, 60, null, 70]], B: [[0, null, 50, null, 55], [2, null, 50, null, 55]] });
  const columns = Object.fromEntries(Object.keys(r[0]).map((k) => [k, { id: k, label: k, type: k === 'device' ? 'text' : 'number' }]));
  const c = compileTimeseries({ rows: r, columns, tokens, view: { type: 'timeseries', name: 'Temp', style: {}, timeseries: { x: 't', y: 'value', series: 'device', limits: L4 } } });
  const g = c.datasets.guides || [];
  const lim = (guide, series) => g.filter((d) => d.guide === guide && d.series === series).map((d) => [d.x, d.value]);
  assert.deepEqual(lim('limit:warn_hi', 'A'), [[0, 60], [2, 60]]);
  assert.deepEqual(lim('limit:error_hi', 'B'), [[0, 55], [2, 55]]);
  const edge = g.filter((d) => d.guide === 'zone:error_hi' && d.series === 'A');
  assert.deepEqual(edge.map((d) => [d.x, d.lo, d.hi]), [[0, 70, null], [2, 70, null]]);
  // the layers that draw them read the guides dataset
  const layers = JSON.stringify(c.spec.layer);
  for (const name of ['limit:warn_hi', 'limit:error_hi', 'zone:warn_hi', 'zone:error_hi']) assert.ok(layers.includes(name), name);
});
