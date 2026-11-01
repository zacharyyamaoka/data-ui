// Kit gap 3, a follow-up found while sweeping the gallery: a chart follows the clock when its x is the clock's own time
// column (a dashboard's clock.time, else t), never because a column is in seconds. ml-experiments' "Compute vs success"
// plots compute_mean_s, a duration in seconds per run: it must keep its own axis and draw no playhead.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const core = (f) => JSON.stringify(join(ROOT, 'packages/core/src', f));
const shim = `export * from ${core('grammar.js')}; export * from ${core('format.js')}; export * from ${core('clock.js')};
export * from ${core('legend.js')}; export * from ${core('guides.js')}; export * from ${core('facets.js')};
export const loadView = () => null;`;
const out = await build({
  stdin: { contents: `export { compile } from './index.js';`, resolveDir: join(ROOT, 'packages/views/chart/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent', loader: { '.css': 'text' },
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onResolve({ filter: /^vega-embed$/ }, () => ({ path: 'embed', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
    b.onLoad({ filter: /^embed$/, namespace: 'shim' }, () => ({ contents: 'export default () => null;', loader: 'js' }));
  } }],
});
const { compile } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`);

const tokens = { series: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666', '#777777', '#888888'], muted: '#999999', fg: '#000', rule: '#eee', border: '#ddd', css: {}, font: 'system-ui' };
const columns = {
  compute_mean_s: { id: 'compute_mean_s', type: 'number', label: 'Compute per run', unitText: 's' },
  success: { id: 'success', type: 'number', label: 'Success' },
  time_s: { id: 'time_s', type: 'number', label: 'Time', unitText: 's' },
  t: { id: 't', type: 'number', label: 't', unitText: 'ms' },
};
const rows = [1, 2, 3].map((i) => ({ id: `r${i}`, compute_mean_s: i * 10, success: i / 4, time_s: i, t: i * 1000 }));
const chart = (x) => ({ type: 'chart', name: 'c', chart: { mark: 'point', encoding: { x: { field: x }, y: { field: 'success' } } } });

test('a duration in seconds is no time on the clock: no meta.time, no clock domain', () => {
  const o = compile({ rows, view: chart('compute_mean_s'), columns, tokens }, { width: 400, height: 200 });
  assert.equal(o.meta.time, null);
  assert.ok(!JSON.stringify(o.spec).includes('dvXmin'));
});

test('the clock\'s own column follows it: a dashboard\'s clock.time names it', () => {
  const o = compile({ rows, view: chart('time_s'), columns, tokens }, { width: 400, height: 200, timeColumn: 'time_s' });
  assert.deepEqual(o.meta.time, { extent: [1, 3], domain: [1, 3] });
});

test('a t in another unit than seconds (ms) does not follow the clock, which counts seconds', () => {
  const o = compile({ rows, view: chart('t'), columns, tokens }, { width: 400, height: 200 });
  assert.equal(o.meta.time, null);
});
