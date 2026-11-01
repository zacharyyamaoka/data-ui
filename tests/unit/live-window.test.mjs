// The plot's reduction (docs/peps/0012-live-data.md §6.2) and the levels card's bins (§6.3), pure functions.
// Committed before the code (lane/live, Step 2). The oracle for a min/max column is a plain loop over the raw samples.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { minMaxColumns, alignSeries } from '../../packages/core/src/live/window.js';
import { levelBins, worstOf } from '../../packages/views/live/src/levels-model.js';

const part = (t, v) => ({ t: Float64Array.from(t), cols: { v: Float64Array.from(v) } });

test('minMaxColumns: at most two points per pixel column, each column\'s true min and max, a one-sample spike kept', () => {
  const n = 100000, a = 0, b = 1, width = 500;
  const t = new Float64Array(n), v = new Float64Array(n);
  for (let i = 0; i < n; i++) { t[i] = (i + 0.5) / n; v[i] = Math.sin(i / 300); }
  v[54321] = 25;   // one spike
  const out = minMaxColumns([part(t, v)], 'v', a, b, width);
  assert.ok(out.x.length <= 2 * width, `${out.x.length} points`);
  assert.equal(out.x.length, out.y.length);
  let max = -Infinity;
  for (const y of out.y) if (y > max) max = y;
  assert.equal(max, 25, 'the spike survives');
  // oracle: per column, the raw min and max
  const dx = (b - a) / width;
  for (let c = 0; c < width; c += 37) {
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < n; i++) if (Math.min(width - 1, Math.floor((t[i] - a) / dx)) === c) { lo = Math.min(lo, v[i]); hi = Math.max(hi, v[i]); }
    const ys = [];
    for (let k = 0; k < out.x.length; k++) if (Math.min(width - 1, Math.floor((out.x[k] - a) / dx)) === c) ys.push(out.y[k]);
    assert.deepEqual([Math.min(...ys), Math.max(...ys)], [lo, hi], `column ${c}`);
  }
  for (let k = 1; k < out.x.length; k++) assert.ok(out.x[k] >= out.x[k - 1], 'x in order');
});

test('minMaxColumns: a column with no samples is a gap (null), never a value', () => {
  const t = [], v = [];
  for (let i = 0; i < 1000; i++) { const x = i / 1000; if (x > 0.4 && x < 0.6) continue; t.push(x); v.push(1); }
  const out = minMaxColumns([part(t, v)], 'v', 0, 1, 100);
  const gaps = [];
  for (let k = 0; k < out.x.length; k++) if (out.y[k] === null || Number.isNaN(out.y[k])) gaps.push(out.x[k]);
  assert.ok(gaps.length > 0, 'the hole shows as a gap');
  assert.ok(gaps.every((x) => x > 0.39 && x < 0.61), gaps.slice(0, 5).join(', '));
});

test('alignSeries: sparse series keep their own samples, aligned on one x array with nulls between', () => {
  const s1 = { name: 'a', parts: [part([1, 2, 3], [10, 20, 30])], column: 'v' };
  const s2 = { name: 'b', parts: [part([1.5, 2.5], [5, 6])], column: 'v' };
  const data = alignSeries([s1, s2], 0, 4, 400);
  assert.deepEqual(Array.from(data[0]), [1, 1.5, 2, 2.5, 3]);
  assert.deepEqual(Array.from(data[1], (x) => (Number.isNaN(x) ? null : x)), [10, null, 20, null, 30]);
  assert.deepEqual(Array.from(data[2], (x) => (Number.isNaN(x) ? null : x)), [null, 5, null, 6, null]);
});

test('alignSeries: dense series share the column grid (two x per column), so one setData draws them all', () => {
  const n = 50000, t = new Float64Array(n), v = new Float64Array(n), w = new Float64Array(n);
  for (let i = 0; i < n; i++) { t[i] = i / n; v[i] = i % 100; w[i] = -(i % 50); }
  const data = alignSeries([{ name: 'a', parts: [part(t, v)], column: 'v' }, { name: 'b', parts: [{ t, cols: { v: w } }], column: 'v' }], 0, 1, 300);
  assert.equal(data.length, 3);
  assert.ok(data[0].length <= 600);
  assert.equal(data[1].length, data[0].length);
  assert.equal(data[2].length, data[0].length);
});

test('levels: the worst level held in each bin (a bin is (start, end], so the newest reading at t is in the last one), the level in force carried in, no data an empty bin', () => {
  const order = ['ok', 'warn', 'unknown', 'stale', 'error'];
  assert.equal(worstOf(['ok', 'error', 'warn'], order), 'error');
  // changes at t: 1 ok, 2 warn, 2.5 ok, 7 error; nothing before t = 1
  const changes = [{ t: 1, level: 'ok' }, { t: 2, level: 'warn' }, { t: 2.5, level: 'ok' }, { t: 7, level: 'error' }];
  const bins = levelBins(changes, null, 0, 10, 10, order);
  assert.deepEqual(bins, ['ok', 'warn', 'warn', 'ok', 'ok', 'ok', 'error', 'error', 'error', 'error']);
  // nothing in force and no change: an empty bin
  assert.deepEqual(levelBins([{ t: 8.5, level: 'warn' }], null, 0, 10, 5, order), [null, null, null, null, 'warn']);
  // a level in force before the window starts carries into the first bins
  const carried = levelBins([{ t: 5, level: 'ok' }], 'stale', 0, 10, 5, order);
  assert.deepEqual(carried, ['stale', 'stale', 'stale', 'ok', 'ok']);
});

test('ColumnCache: frame after frame of a sliding window, the cached columns equal a fresh reduction on the same grid', async () => {
  const { ColumnCache } = await import('../../packages/core/src/live/window.js');
  const { LiveDataset } = await import('../../packages/core/src/live/store.js');
  const ds = new LiveDataset({ properties: { t: { type: 'number' }, s: { type: 'text' }, v: { type: 'number' } }, time: 't', stream: 's' });
  const cache = new ColumnCache();
  const list = ['a', 'b'].map((s) => ({ name: s, ds, stream: s, column: 'v' }));
  let t = 1000, k = 0;
  const W = 200, span = 4;
  // 4 s already at 2 kHz: the window is dense (more than two samples a column) from the first frame
  const pre = [];
  for (let i = 0; i < 8000; i++) { t += 0.0005; k++; pre.push({ t, s: 'a', v: Math.sin(k / 50) }, { t: t - 0.01, s: 'b', v: -Math.sin(k / 50) }); }
  ds.append(pre);
  const modes = new Set();
  for (let frame = 0; frame < 120; frame++) {
    // two streams, out of step: b lags a by up to 30 ms, both at 2 kHz, with a spike now and then
    const rows = [];
    for (let i = 0; i < 33; i++) { t += 0.0005; k++; rows.push({ t, s: 'a', v: Math.sin(k / 50) + (k % 997 === 0 ? 9 : 0) }); }
    ds.append(rows);
    ds.append(rows.filter((_, i) => i % 2 === 0).map((r) => ({ t: r.t - 0.03 * (frame % 3) / 3, s: 'b', v: -r.v })));
    const b = t, a = b - span;
    const got = cache.data(list, a, b, W);
    modes.add(cache.mode);
    // the oracle: every sample of (a, b] binned on the same absolute grid
    const dx = span / W, k0 = Math.floor(a / dx);
    for (const [j, s] of list.entries()) {
      const want = new Map();
      for (const p of ds.range(a, b, { stream: s.stream, columns: ['v'] })) for (let i = 0; i < p.t.length; i++) {
        const kk = Math.floor(p.t[i] / dx), c = want.get(kk);
        if (!c) want.set(kk, [p.cols.v[i], p.cols.v[i]]); else { c[0] = Math.min(c[0], p.cols.v[i]); c[1] = Math.max(c[1], p.cols.v[i]); }
      }
      const ys = got[j + 1];
      for (let i = 0; i < ys.length; i += 2) {
        const kk = k0 + i / 2, w = want.get(kk);
        const pair = ys[i] === null ? null : [Math.min(ys[i], ys[i + 1]), Math.max(ys[i], ys[i + 1])];
        assert.deepEqual(pair, w || null, `frame ${frame}, series ${s.name}, column ${kk}`);
      }
    }
  }
  assert.deepEqual([...modes].sort(), ['cached', 'rebuilt'], 'built once, then reused frame after frame');
});
