// The kit gaps the PEP 0010 template lanes found (gallery/examples/robotics-{servo,arm,driver,camera,arm-gripper}), the
// pure half. The browser half is tests/browser/kit_gaps_checks.py; the checkers' is check-kit-gaps.test.mjs. Written red,
// before the fixes.
//   gap 1  a chart's in-place row swap (the fast path) gives exactly what a fresh view of the same rows draws, for every
//          Vega-Lite aggregate op, composite mark and transform (the oracle: Vega's own first run of a new view)
//   gap 2  timeseries annotations from a dataset (input.layers, §32) or from the view's own rows, beside fixed ones
//   gap 3  a chart whose x is a time in seconds knows its time span and takes the clock's zoom window as its x domain
//   gap 6  a column's `colors` map takes `muted` (and 0, a slot, a token, a CSS colour); a null cell is muted, never the
//          hashed hue of its display label
//   gap 7  annotation labels are staggered so no two drawn ones overlap; a label with no room is not drawn
//   gap 8  a facet nested under another (`parent:`): the parent's counts ignore its children's picks, and a parent pick a
//          child's pick no longer fits moves the child to its first listed value that does (Grafana's chained variables)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as vega from 'vega';
import * as vl from 'vega-lite';
import { facetSpecs, railCounts, settleChildren } from '../../packages/core/src/facets.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const core = (f) => JSON.stringify(join(ROOT, 'packages/core/src', f));
// WHY every pure core module, not a list of names: the chart bundle may import any of their exports
const shim = `export * from ${core('grammar.js')}; export * from ${core('format.js')}; export * from ${core('clock.js')};
export * from ${core('legend.js')}; export * from ${core('guides.js')}; export * from ${core('facets.js')};
export const loadView = () => null;`;
const out = await build({
  stdin: { contents: `export { compile, swapData, freshCells, extentAggregates } from './index.js';
export { compileTimeseries, annotationRows, labelRows } from './timeseries.js';`, resolveDir: join(ROOT, 'packages/views/chart/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent', loader: { '.css': 'text' },
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onResolve({ filter: /^vega-embed$/ }, () => ({ path: 'embed', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    b.onLoad({ filter: /^embed$/, namespace: 'shim' }, () => ({ contents: 'export default () => { throw new Error("no embed in unit tests"); };', loader: 'js' }));
  } }],
});
const C = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);

const SERIES = ['#2a78d6', '#eb6834', '#19a979', '#9a5bd6', '#d6a12a', '#0f8a6a', '#c74bb0', '#d33d3d'];
const tokens = { series: SERIES, muted: '#71717a', fg: '#111111', bg: '#ffffff', rule: '#e4e4e7', border: '#e4e4e7', good: '#16a34a', warn: '#d97706', bad: '#dc2626',
  font: 'system-ui', css: { 'data-bad': '#cc0000', 'data-muted': '#71717a' } };

// ------------------------------------------------------------------------------------------------ gap 1: the row swap
const rand = (seed) => () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
const rowsOf = (seed, n, kinds) => {
  const r = rand(seed);
  return Array.from({ length: n }, (_, i) => ({ id: `${seed}-${i}`, k: kinds[i % kinds.length], g: i % 2 ? 'a' : 'b',
    v: Math.round((r() * 200 - 100) * 100) / 100, w: Math.round(r() * 4), t: i }));
};
// A, the same values as new rows, B (other kinds), A again, C (one kind): every swap a dashboard pick makes
const STEPS = [rowsOf(7, 40, ['s', 'c']), rowsOf(7, 40, ['s', 'c']).map((d) => ({ ...d, id: `${d.id}x` })), rowsOf(11, 60, ['s', 'w']), rowsOf(7, 40, ['s', 'c']), rowsOf(13, 25, ['s'])];
const COLS = { k: { id: 'k', type: 'text', label: 'k' }, g: { id: 'g', type: 'text', label: 'g' }, v: { id: 'v', type: 'number', label: 'v' },
  w: { id: 'w', type: 'number', label: 'w' }, t: { id: 't', type: 'number', label: 't' } };
const K = { field: 'k', type: 'nominal' };
const OPS = ['count', 'valid', 'missing', 'distinct', 'sum', 'product', 'mean', 'average', 'variance', 'variancep', 'stdev', 'stdevp', 'stderr', 'median', 'q1', 'q3', 'ci0', 'ci1', 'min', 'max'];
const CHARTS = {
  'boxplot min-max': { mark: { type: 'boxplot', extent: 'min-max' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'boxplot 1.5 IQR': { mark: { type: 'boxplot' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'errorbar stderr': { mark: { type: 'errorbar', extent: 'stderr' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'errorbar stdev': { mark: { type: 'errorbar', extent: 'stdev' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'errorbar ci': { mark: { type: 'errorbar', extent: 'ci' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'errorbar iqr': { mark: { type: 'errorbar', extent: 'iqr' }, encoding: { x: K, y: { field: 'v', type: 'quantitative' } } },
  'errorband ci': { mark: { type: 'errorband', extent: 'ci' }, encoding: { x: { field: 't', type: 'quantitative', bin: { maxbins: 4 } }, y: { field: 'v', type: 'quantitative' } } },
  'argmin beside a median': { mark: 'rule', encoding: { x: K, y: { aggregate: { argmin: 'v' }, field: 't', type: 'quantitative' }, y2: { aggregate: 'median', field: 't' } } },
  'transform aggregate: median, max, ci1, argmin': { transform: [{ aggregate: [{ op: 'median', field: 'v', as: 'm' }, { op: 'max', field: 'v', as: 'hi' }, { op: 'ci1', field: 'v', as: 'c' }, { op: 'argmin', field: 'v', as: 'a' }], groupby: ['k'] }, { calculate: 'datum.a.v', as: 'av' }],
    mark: 'point', encoding: { x: K, y: { field: 'hi', type: 'quantitative' }, size: { field: 'c', type: 'quantitative' }, opacity: { field: 'm', type: 'quantitative' }, color: { field: 'av', type: 'quantitative' } } },
  'joinaggregate: median and min': { transform: [{ joinaggregate: [{ op: 'median', field: 'v', as: 'm' }, { op: 'min', field: 'v', as: 'lo' }], groupby: ['k'] }],
    mark: 'point', encoding: { x: { field: 't', type: 'quantitative' }, y: { field: 'lo', type: 'quantitative' }, size: { field: 'm', type: 'quantitative' } } },
  'window ops': { transform: [{ window: [{ op: 'rank', as: 'r' }, { op: 'lag', field: 'v', as: 'p' }, { op: 'first_value', field: 'v', as: 'f' }, { op: 'cume_dist', as: 'cd' }, { op: 'max', field: 'v', as: 'wm' }], sort: [{ field: 't' }], groupby: ['k'] }],
    mark: 'point', encoding: { x: { field: 't', type: 'quantitative' }, y: { field: 'wm', type: 'quantitative' }, size: { field: 'cd', type: 'quantitative' }, opacity: { field: 'f', type: 'quantitative' } } },
  'quantile': { transform: [{ quantile: 'v', step: 0.25, groupby: ['k'] }], mark: 'point', encoding: { x: { field: 'prob', type: 'quantitative' }, y: { field: 'value', type: 'quantitative' } } },
  'density': { transform: [{ density: 'v', groupby: ['k'], extent: [-100, 100], steps: 20 }], mark: 'line', encoding: { x: { field: 'value', type: 'quantitative' }, y: { field: 'density', type: 'quantitative' } } },
  'regression': { transform: [{ regression: 'v', on: 't', groupby: ['k'] }], mark: 'line', encoding: { x: { field: 't', type: 'quantitative' }, y: { field: 'v', type: 'quantitative' } } },
  'loess': { transform: [{ loess: 'v', on: 't', groupby: ['k'] }], mark: 'line', encoding: { x: { field: 't', type: 'quantitative' }, y: { field: 'v', type: 'quantitative' } } },
  'histogram (sum of w)': { mark: 'bar', encoding: { x: { field: 'v', bin: { maxbins: 8 } }, y: { aggregate: 'sum', field: 'w' } } },
  'stacked sums': { mark: 'bar', encoding: { x: K, y: { aggregate: 'sum', field: 'w', type: 'quantitative' }, color: { field: 'g', type: 'nominal' } } },
  'impute': { mark: 'line', encoding: { x: { field: 't', type: 'quantitative' }, y: { field: 'v', type: 'quantitative', impute: { method: 'max' } }, detail: K } },
  'pivot': { transform: [{ pivot: 'k', value: 'v', groupby: ['g'], op: 'max' }], mark: 'point', encoding: { x: { field: 'g', type: 'nominal' }, y: { field: 's', type: 'quantitative' } } },
};
for (const op of OPS) CHARTS[`${op} beside a median`] = { mark: 'rule', encoding: { x: K, y: { aggregate: op, field: 'v', type: 'quantitative' }, y2: { aggregate: 'median', field: 'v' } } };
// w holds zeros: Vega updates a product by dividing out what leaves, and 0 / 0 is NaN for good
CHARTS['product of a column with zeros'] = { mark: 'bar', encoding: { x: K, y: { aggregate: 'product', field: 'w', type: 'quantitative' } } };

/** Every drawn item's datum, as text, sorted: what the reader sees. Nested rows (argmin) by id; numbers to 12 figures. */
function drawn(view) {
  const out = [];
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? Number(v.toPrecision(12)) : typeof v === 'number' ? String(v) : v);
  const walk = (n) => {
    if (n.marktype && n.role === 'mark') {
      for (const i of n.items || []) {
        const d = i.datum && typeof i.datum === 'object' ? Object.fromEntries(Object.entries(i.datum).map(([k, v]) => [k, v && typeof v === 'object' ? (v.id ?? JSON.stringify(v)) : num(v)])) : null;
        out.push(JSON.stringify([n.name, d]));
      }
    }
    for (const i of n.items || []) if (i.items) walk(i);
  };
  walk(view.scenegraph().root);
  return out.sort();
}
// WHY a seeded random: Vega's bootstrap CI (ci0, ci1, errorbar ci) resamples; both runs draw the same sequence
const seed = () => vega.setRandom(rand(42));
const viewOf = (o) => new vega.View(vega.parse(vl.compile({ ...o.spec, datasets: o.datasets }).spec, null), { renderer: 'none' });
const compileRows = (chart, rows) => C.compile({ rows, view: { type: 'chart', name: 'c', chart }, columns: COLS, tokens }, { width: 300, height: 200 });

test('gap 1: every aggregate, composite mark and transform draws after an in-place swap exactly what a fresh view of the same rows draws', async () => {
  const stale = [];
  for (const [name, chart] of Object.entries(CHARTS)) {
    let o = compileRows(chart, STEPS[0]);
    seed();
    let view = viewOf(o);
    await view.runAsync();
    for (const [i, rows] of STEPS.entries()) {
      if (!i) continue;
      const next = compileRows(chart, rows);
      if (next.key === o.key) {
        // the chart view's fast path (ChartView._draw): the same spec, new rows
        seed();
        await C.swapData(view, next.datasets, next.spec);
        seed();
        await view.runAsync();
      } else {
        seed();
        view = viewOf(next);
        await view.runAsync();
      }
      o = next;
      seed();
      const fresh = viewOf(next);
      await fresh.runAsync();
      if (JSON.stringify(drawn(view)) !== JSON.stringify(drawn(fresh))) stale.push(`${name} after swap ${i}`);
      fresh.finalize();
    }
    view.finalize();
  }
  assert.deepEqual(stale, [], `drawn from stale cells: ${stale.join('; ')}`);
});

test('gap 1: freshCells says which specs Vega cannot update in place (a value store or a division), so only those swap twice', () => {
  for (const name of ['boxplot min-max', 'boxplot 1.5 IQR', 'errorbar ci', 'errorband ci', 'argmin beside a median', 'transform aggregate: median, max, ci1, argmin', 'joinaggregate: median and min',
    'product beside a median', 'product of a column with zeros', 'ci0 beside a median', 'ci1 beside a median', 'min beside a median', 'q1 beside a median']) {
    assert.equal(C.freshCells(CHARTS[name]), true, name);
  }
  for (const spec of [{ mark: 'bar', encoding: { x: K, y: { aggregate: 'sum', field: 'w' } } }, { mark: 'bar', encoding: { x: K, y: { aggregate: 'count' } } },
    { mark: 'point', encoding: { x: { field: 't' }, y: { field: 'v' } } }, { mark: 'bar', encoding: { x: K, y: { aggregate: 'mean', field: 'v' } } }]) {
    assert.equal(C.freshCells(spec), false, JSON.stringify(spec));
  }
  // the name P2 gave it stays (tests/unit/chart-extent.test.mjs)
  assert.equal(C.extentAggregates({ mark: { type: 'boxplot' } }), true);
});

// ------------------------------------------------------------------------------------------------ gap 3: time x
const TCOLS = { t: { id: 't', type: 'number', label: 't', unitText: 's' }, mode: { id: 'mode', type: 'text', label: 'Mode' }, a: { id: 'a', type: 'number', label: 'a', unitText: 'A' } };
const TROWS = [0, 0.5, 1.25, 3, 4.5].map((t, i) => ({ id: `r${i}`, t, mode: i < 2 ? 'stopped' : 'position', a: i * 0.7 }));
const strip = (x) => ({ type: 'chart', name: 'm', chart: { mark: 'tick', encoding: { x, color: { field: 'mode', type: 'nominal' } } } });
const domainOf = async (o) => { const v = viewOf(o); await v.runAsync(); const d = v.scale('x').domain(); v.finalize(); return d; };

test('gap 3: a chart whose x is a time in seconds spans its rows\' time, exactly, and takes the clock\'s zoom window without a new spec', async () => {
  const o = C.compile({ rows: TROWS, view: strip({ field: 't', type: 'quantitative' }), columns: TCOLS, tokens }, { width: 400, height: 120 });
  assert.deepEqual(o.meta.time, { extent: [0, 4.5], domain: [0, 4.5] });
  assert.deepEqual(await domainOf(o), [0, 4.5]);
  const z = C.compile({ rows: TROWS, view: strip({ field: 't', type: 'quantitative' }), columns: TCOLS, tokens }, { width: 400, height: 120, win: [1, 2] });
  assert.deepEqual(z.meta.time, { extent: [0, 4.5], domain: [1, 2] });
  assert.equal(z.key, o.key, 'a zoom swaps the domain, never the spec (no re-embed)');
  assert.deepEqual(await domainOf(z), [1, 2]);
});

test('gap 3: a chart whose x is not seconds (another unit, binned, aggregated) does not follow the clock', () => {
  for (const x of [{ field: 'a', type: 'quantitative' }, { field: 't', type: 'quantitative', bin: true }, { field: 't', type: 'quantitative', aggregate: 'max' }]) {
    const o = C.compile({ rows: TROWS, view: strip(x), columns: TCOLS, tokens }, { width: 400, height: 120 });
    assert.equal(o.meta.time, null, JSON.stringify(x));
  }
});

// ------------------------------------------------------------------------------------------------ gap 6: colours
test('gap 6: a column\'s colors map takes muted, 0, a slot, a token and a CSS colour, and a null cell is muted', async () => {
  const cols = { k: COLS.k, v: COLS.v, state: { id: 'state', type: 'text', label: 'State', colors: { ok: 1, idle: 'muted', zero: 0, hot: 'var(--data-bad)', custom: '#123456', two: '2' } } };
  const rows = ['ok', 'idle', 'zero', 'hot', 'custom', 'two', null, null].map((state, i) => ({ id: `s${i}`, k: `k${i % 2}`, v: i + 1, state }));
  const o = C.compile({ rows, view: { type: 'chart', name: 'c', chart: { mark: 'point', encoding: { x: { field: 'v' }, y: { field: 'k' }, color: { field: 'state' } } } }, columns: cols, tokens }, { width: 300, height: 200 });
  const v = viewOf(o);
  await v.runAsync();
  const c = v.scale('color');
  const want = { ok: SERIES[0], idle: tokens.muted, zero: tokens.muted, hot: '#cc0000', custom: '#123456', two: SERIES[1], 'No state': tokens.muted };
  for (const [value, colour] of Object.entries(want)) assert.equal(String(c(value)).toLowerCase(), colour, `${value} -> ${colour}`);
  v.finalize();
});

test('gap 6: with no colors map the drawn values take the palette and a null cell is muted, never the hue of "No <label>"', async () => {
  const cols = { k: COLS.k, v: COLS.v, state: { id: 'state', type: 'text', label: 'State' } };
  const rows = ['a', 'b', 'a', null, 'c', null].map((state, i) => ({ id: `s${i}`, k: 'k', v: i + 1, state }));
  const o = C.compile({ rows, view: { type: 'chart', name: 'c', chart: { mark: 'point', encoding: { x: { field: 'v' }, y: { field: 'k' }, color: { field: 'state' } } } }, columns: cols, tokens }, { width: 300, height: 200 });
  const v = viewOf(o);
  await v.runAsync();
  const c = v.scale('color');
  assert.equal(String(c('No state')).toLowerCase(), tokens.muted);
  const others = ['a', 'b', 'c'].map((x) => String(c(x)).toLowerCase());
  assert.equal(new Set(others).size, 3, others.join());
  assert.ok(others.every((x) => SERIES.includes(x)), others.join());
  v.finalize();
});

// ------------------------------------------------------------------------------------------------ gaps 2 and 7: annotations
const SCOLS = { t: { id: 't', type: 'number', label: 't', unitText: 's' }, v: { id: 'v', type: 'number', label: 'v' }, situation: { id: 'situation', type: 'text', label: 'Situation' },
  event: { id: 'event', type: 'text', label: 'Event' } };
const SROWS = Array.from({ length: 50 }, (_, i) => ({ id: `p${i}`, t: i / 10, v: Math.sin(i / 5), situation: 'real', event: i === 12 ? 'slip' : null }));
const EVENTS = [{ id: 'e1', t: 4.97, label: 'release', kind: 'release' }, { id: 'e2', t: 1.61, label: 'contact', kind: 'contact' }, { id: 'e3', t: 1.91, label: 'grasp', kind: 'grasp' }, { id: 'e4', t: null, label: 'lost', kind: 'x' }];
const ECOLS = { t: { id: 't', type: 'number', label: 't', unitText: 's' }, label: { id: 'label', type: 'text', label: 'Label' }, kind: { id: 'kind', type: 'text', label: 'Kind' } };
const tsInput = (annotations) => ({ rows: SROWS, view: { type: 'timeseries', name: 'ts', timeseries: { x: 't', y: 'v', series: 'situation', annotations } }, columns: SCOLS, tokens,
  layers: { events: { rows: EVENTS, columns: ECOLS, total: EVENTS.length, url: null } } });

test('gap 2: annotations come from a dataset (each row with a time), from the view\'s own rows (each with a label) and as written, in time order', () => {
  const input = tsInput([{ x: 0.25, label: 'fixed' }, { data: 'events', x: 't', label: 'label', tone: 'warn' }, { x: 't', label: 'event' }]);
  assert.deepEqual(C.annotationRows(input), [
    { x: 0.25, label: 'fixed', tone: 'muted' }, { x: 1.2, label: 'slip', tone: 'muted' }, { x: 1.61, label: 'contact', tone: 'warn' },
    { x: 1.91, label: 'grasp', tone: 'warn' }, { x: 4.97, label: 'release', tone: 'warn' }]);
  // a dataset the view was not handed (a plain <data-views>) draws nothing
  assert.deepEqual(C.annotationRows(tsInput([{ data: 'nowhere', x: 't', label: 'label' }])), []);
  // the compiled card carries them as its `marks` dataset: one per annotation, at its time, with its label
  const o = C.compileTimeseries(input, { width: 600, height: 200 });
  assert.deepEqual(o.datasets.marks.map((m) => [m.x, m.label]), [[0.25, 'fixed'], [1.2, 'slip'], [1.61, 'contact'], [1.91, 'grasp'], [4.97, 'release']]);
});

const measure = (s) => String(s).length * 6;
const overlaps = (boxes) => {
  const bad = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.row !== null && a.row === b.row && a.x0 < b.x1 && b.x0 < a.x1) bad.push([i, j]);
  }
  return bad;
};

test('gap 7: close labels (contact and grasp 0.3 s apart) are staggered into rows, so none overlaps another; each stays in the plot', () => {
  const marks = [{ x: 1.61, label: 'contact' }, { x: 1.91, label: 'grasp' }, { x: 4.97, label: 'release' }];
  for (const width of [265, 403, 900]) {
    const rows = C.labelRows(marks, { domain: [0, 7.9], width, measure });
    assert.equal(rows.length, 3);
    assert.ok(rows.every((r) => r.row !== null), `every label has room at ${width} px: ${JSON.stringify(rows)}`);
    assert.deepEqual(overlaps(rows), [], `${width} px: ${JSON.stringify(rows)}`);
    assert.ok(rows.every((r) => r.x0 >= 0 && r.x1 <= width && r.x1 - r.x0 >= measure('grasp')), JSON.stringify(rows));
  }
  // at 265 px contact and grasp are 11 px apart: they cannot share a row
  const narrow = C.labelRows(marks, { domain: [0, 7.9], width: 265, measure });
  assert.notEqual(narrow[0].row, narrow[1].row);
});

test('gap 7: a dense run of marks draws the labels it has room for, at most three rows, never overlapping', () => {
  const marks = Array.from({ length: 12 }, (_, i) => ({ x: 2 + i * 0.04, label: `limiter ${i}` }));
  const rows = C.labelRows(marks, { domain: [0, 10], width: 300, measure });
  assert.equal(rows.length, 12);
  assert.deepEqual(overlaps(rows), [], JSON.stringify(rows));
  assert.ok(rows.every((r) => r.row === null || (r.row >= 0 && r.row <= 2)), JSON.stringify(rows));
  assert.ok(rows.some((r) => r.row === null), 'some labels have no room and are left to the readout');
  assert.ok(rows.filter((r) => r.row !== null).length >= 3, 'the first of each row is drawn');
});

// ------------------------------------------------------------------------------------------------ gap 8: a parent facet
const RUNS = [['r1', 'A'], ['r2', 'B'], ['r3', 'A'], ['r4', 'B'], ['r5', 'A'], ['r6', 'C']].map(([run, device], i) => ({ id: run, run, device, kind: i % 2 ? 'sine' : 'chirp' }));
const RPROPS = { run: { id: 'run', type: 'text', label: 'Run' }, device: { id: 'device', type: 'text', label: 'Device' }, kind: { id: 'kind', type: 'text', label: 'Kind' } };
const NEWEST = ['r6', 'r5', 'r4', 'r3', 'r2', 'r1'];
const specsOf = (as = 'select') => facetSpecs({ facets: [{ property: 'run', as, label: 'Run', order: NEWEST, parent: 'device' }, { property: 'device', as: 'select' }, { property: 'kind' }] }, null, RPROPS);
const pick = (...values) => ({ values, match: 'equals' });

test('gap 8: the parent\'s counts ignore its child\'s pick, so every device is listed while a run is picked; the child still follows the parent', () => {
  const specs = specsOf();
  const a = railCounts(RUNS, { run: pick('r5') }, specs);
  assert.deepEqual(a.device.counts, { A: 3, B: 2, C: 1 });
  assert.equal(Object.keys(a.run.counts).length, 6);
  const b = railCounts(RUNS, { run: pick('r5'), device: pick('B') }, specs);
  assert.deepEqual(b.device.counts, { A: 3, B: 2, C: 1 });
  assert.deepEqual(Object.keys(b.run.counts).sort(), ['r2', 'r4']);
  // another facet still counts under every pick (kind: the run's and the device's)
  assert.deepEqual(b.kind.counts, {});
  // without parent: nothing changes (a device is narrowed by the run, as before)
  const plain = facetSpecs({ facets: [{ property: 'run', as: 'select' }, { property: 'device', as: 'select' }] }, null, RPROPS);
  assert.deepEqual(railCounts(RUNS, { run: pick('r5') }, plain).device.counts, { A: 1 });
});

test('gap 8: a parent pick the child\'s pick no longer fits moves a select child to its first listed value that does; a fitting pick stays', () => {
  const specs = specsOf();
  const before = { run: pick('r5'), device: pick('B') };
  const after = settleChildren(RUNS, before, specs, 'device');
  assert.deepEqual(after.run.values, ['r4'], 'B\'s newest run (the run facet\'s own order)');
  assert.deepEqual(before.run.values, ['r5'], 'the state handed in is not changed');
  assert.deepEqual(settleChildren(RUNS, { run: pick('r5'), device: pick('A') }, specs, 'device').run.values, ['r5']);
  assert.deepEqual(settleChildren(RUNS, { run: pick('r5'), device: { values: [], match: 'equals' } }, specs, 'device').run.values, ['r5'], 'Any keeps the pick');
  assert.deepEqual(settleChildren(RUNS, { device: pick('C') }, specs, 'device').run, undefined, 'no pick, nothing to move');
  // a multi-value child keeps the values that fit, in its own order
  const multi = settleChildren(RUNS, { run: pick('r5', 'r4', 'r1'), device: pick('A') }, specsOf('values'), 'device');
  assert.deepEqual(multi.run.values.slice().sort(), ['r1', 'r5']);
});
