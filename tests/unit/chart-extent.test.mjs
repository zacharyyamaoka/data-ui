// The chart view's two P2 fixes, found by PEP 0010 P2's coverage checks (tests/browser/p2_checks.py):
//  1. a min or a max stays stale after a filter: Vega 6.4's TupleStore memoises a cell's extent under its accessor
//     alone, so from the second swap of a view's rows on, the fast path (view.data) read whiskers back from the memo.
//     The chart now empties its datasets first when its spec aggregates an extent (extentAggregates).
//  2. a histogram's empty bins were missing bars: a one-series bar histogram now bins with explicit transforms that
//     impute 0 in every empty bin between the first and the last (zeroBins), so its bins are contiguous.
// The upstream behaviour is asserted too: when Vega fixes its memo, the first test fails and says the workaround can go.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as vega from 'vega';
import * as vl from 'vega-lite';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const shim = `export * from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { esc, fmtNum, numOpts, isNum, isEmpty, valueHtml, valueText, mediaUrl, groupLabel, hueOf } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { clockFor, fmtTime, seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};
export { SeriesLegend } from ${JSON.stringify(join(ROOT, 'packages/core/src/legend.js'))};
export const loadView = () => null;`;
const out = await build({
  stdin: { contents: `export { compile, extentAggregates } from './index.js';`, resolveDir: join(ROOT, 'packages/views/chart/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent', loader: { '.css': 'text' },
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onResolve({ filter: /^vega-embed$/ }, () => ({ path: 'embed', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    b.onLoad({ filter: /^embed$/, namespace: 'shim' }, () => ({ contents: 'export default () => { throw new Error("no embed in unit tests"); };', loader: 'js' }));
  } }],
});
const C = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);

const box = vl.compile({ data: { name: 'rows' }, mark: { type: 'boxplot', extent: 'min-max' }, encoding: { x: { field: 'k', type: 'nominal' }, y: { field: 'v', type: 'quantitative' } } }).spec;
const A = () => [{ k: 's', v: -998 }, { k: 's', v: 993 }, { k: 's', v: 0.1 }];
const B = () => [{ k: 's', v: -3035 }, { k: 's', v: 3037 }, { k: 's', v: 0.04 }];
const whiskers = (view) => view.data('data_0').map((d) => [d.lower_whisker_v, d.upper_whisker_v, d.mid_box_v]);

test('upstream: Vega 6.4 reads a stale extent back after the second swap of the rows (what the chart works around)', async () => {
  const view = new vega.View(vega.parse(box), { renderer: 'none' });
  for (const rows of [A(), A(), B()]) { view.data('rows', rows); await view.runAsync(); }
  assert.deepEqual(whiskers(view), [[-998, 993, 0.04]], 'Vega fixed its extent memo: the empty-first swap in chart/src/index.js can go');
});

test('emptying the rows before the swap gives every extent afresh', async () => {
  const view = new vega.View(vega.parse(box), { renderer: 'none' });
  for (const rows of [A(), A(), B(), A()]) {
    view.data('rows', []); await view.runAsync();
    view.data('rows', rows); await view.runAsync();
  }
  assert.deepEqual(whiskers(view), [[-998, 993, 0.1]]);
  view.data('rows', []); await view.runAsync(); view.data('rows', B()); await view.runAsync();
  assert.deepEqual(whiskers(view), [[-3035, 3037, 0.04]]);
});

test('extentAggregates: a boxplot, an errorbar, a min or max aggregate; never a sum or a count', () => {
  assert.equal(C.extentAggregates({ mark: { type: 'boxplot' } }), true);
  assert.equal(C.extentAggregates({ layer: [{ mark: 'errorbar' }] }), true);
  assert.equal(C.extentAggregates({ encoding: { x: { aggregate: 'max', field: 'q' } } }), true);
  assert.equal(C.extentAggregates({ transform: [{ aggregate: [{ op: 'argmin', field: 'q', as: 'a' }] }] }), true);
  assert.equal(C.extentAggregates({ encoding: { y: { aggregate: 'sum', field: 'w' } } }), false);
});

test('a one-series bar histogram draws every bin from the first to the last, an empty one as 0 (Vega\'s own bins)', async () => {
  const rows = [0.4, 0.6, 1.2, 9.5, 9.9].map((q, i) => ({ id: String(i), q, w: 1 }));
  const columns = { q: { id: 'q', type: 'number', label: 'q' }, w: { id: 'w', type: 'number', label: 'w' } };
  const view = { type: 'chart', name: 'h', chart: { mark: 'bar', encoding: { x: { field: 'q', bin: { maxbins: 10 } }, y: { aggregate: 'sum', field: 'w' } } } };
  const tokens = { series: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666', '#777777', '#888888'], muted: '#999999', fg: '#000', rule: '#eee', border: '#ddd', css: {} };
  const o = C.compile({ rows, view, columns, tokens, hiddenSeries: [] }, { width: 300, height: 200 });
  const spec = vl.compile({ ...o.spec, datasets: o.datasets }).spec;
  const v = new vega.View(vega.parse(spec), { renderer: 'none' });
  await v.runAsync();
  const bins = [];
  const walk = (n) => { for (const i of n.items || []) { if (n.marktype === 'rect' && i.datum && i.datum.sum_w !== undefined) bins.push([i.datum.bin_maxbins_10_q, i.datum.bin_maxbins_10_q_end, i.datum.sum_w, Number.isFinite(i.x) && Number.isFinite(i.x2)]); if (i.items) walk(i); } };
  walk(v.scenegraph().root);
  bins.sort((a, b) => a[0] - b[0]);
  assert.deepEqual(bins.map((b) => b[2]), [2, 1, 0, 0, 0, 0, 0, 0, 0, 2], JSON.stringify(bins));
  for (let i = 1; i < bins.length; i++) assert.ok(Math.abs(bins[i][0] - bins[i - 1][1]) < 1e-12, 'contiguous');
  assert.ok(bins.every((b) => b[3]), 'every bar has an x and an x2 (square ends: Vega-Lite drops a ranged bar\'s x under a corner radius)');
});

// The rewrite must be invisible to every reader of a bin: found by merging PEP 0010 P4 (its driver's i_q histogram), whose
// oracle reads a bin as the one key with a <key>_end partner, and whose hover card never showed. The oracle for the
// datum is Vega-Lite's own one-series binned aggregate, compiled straight from the spec as written.
const histogram = () => {
  const rows = [0.4, 0.6, 1.2, 9.5, 9.9].map((q, i) => ({ id: String(i), q, w: 1 }));
  const columns = { q: { id: 'q', type: 'number', label: 'q' }, w: { id: 'w', type: 'number', label: 'w' } };
  const view = { type: 'chart', name: 'h', chart: { mark: 'bar', encoding: { x: { field: 'q', bin: { maxbins: 10 } }, y: { aggregate: 'sum', field: 'w' } } } };
  const tokens = { series: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666', '#777777', '#888888'], muted: '#999999', fg: '#000', rule: '#eee', border: '#ddd', css: {} };
  return { rows, o: C.compile({ rows, view, columns, tokens, hiddenSeries: [] }, { width: 300, height: 200 }) };
};
const barData = async (spec) => {
  const v = new vega.View(vega.parse(spec), { renderer: 'none' });
  await v.runAsync();
  const out = [];
  const walk = (n) => { for (const i of n.items || []) { if (n.marktype === 'rect' && n.role === 'mark' && i.datum) out.push(i.datum); if (i.items) walk(i); } };
  walk(v.scenegraph().root);
  return out;
};

test('a rewritten histogram\'s datum is Vega-Lite\'s own: the bin, its end and the sum, never a stack\'s start and end', async () => {
  const { rows, o } = histogram();
  const own = vl.compile({ data: { values: rows }, mark: 'bar', encoding: { x: { field: 'q', type: 'quantitative', bin: { maxbins: 10 } }, y: { aggregate: 'sum', field: 'w', type: 'quantitative' } } }).spec;
  const keys = (data) => [...new Set(data.map((d) => Object.keys(d).sort().join(',')))];
  const mine = await barData(vl.compile({ ...o.spec, datasets: o.datasets }).spec), ownKeys = keys(await barData(own));
  assert.deepEqual(keys(mine.filter((d) => !d._impute)), ownKeys);
  // an empty bin (one Vega-Lite's own draws no bar for) is the same datum, marked by Vega's impute as _impute
  assert.deepEqual(keys(mine.filter((d) => d._impute).map(({ _impute, ...d }) => d)), ownKeys);
});

test('the hover card and the click read a rewritten bin as written: its range, its sum and exactly its own rows', async () => {
  const { rows, o } = histogram();
  const data = (await barData(vl.compile({ ...o.spec, datasets: o.datasets }).spec)).filter((d) => d.sum_w > 0);
  assert.equal(data.length, 3);
  for (const d of data) {
    const lo = d.bin_maxbins_10_q, hi = d.bin_maxbins_10_q_end;
    const mine = rows.filter((r) => r.q >= lo && r.q < hi).map((r) => r.id);
    assert.deepEqual((o.meta.recordsOf(d, rows) || []).map((r) => r.id), mine, `the rows of bin ${lo}–${hi}`);
    const fields = o.meta.datumFields(d);
    assert.equal(fields.length, 2, JSON.stringify(fields));
    assert.ok(fields.every(([label]) => typeof label === 'string' && label && label !== 'undefined'), JSON.stringify(fields));
    assert.ok(String(fields[0][1]).includes('–') && String(fields[0][1]).startsWith(String(lo)), `the bin's range first: ${JSON.stringify(fields)}`);
    assert.equal(fields[1][1], d.sum_w);
  }
});
