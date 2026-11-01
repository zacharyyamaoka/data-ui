/* bench/live.py's in-page driver (docs/peps/0012-live-data.md §8): a live dashboard of M plot panels, each drawing 5
   synthetic streams, fed at `rate` samples a second per stream (N = M × 5 × rate samples a second; M = 12 at 1 kHz is
   Rerun's published reference load, 60,000 samples a second), plus the probes the bench reads:
     frames    rAF intervals, long tasks, the live frame loop's own cost (liveStats), draws per frame
     latency   append → the frame that shows it: each batch's append time, matched to the first plot draw whose t reaches
               the batch's newest sample, then the task after that frame (the harness's "painted": rAF, then a task)
     scrub     clock.seek(t) → every plot drawn at that t → painted
     goLive    clock.goLive() after a pause → every plot drawn at the newest data → painted
     engines   the same min/max columns pushed into uPlot (setData) and into Vega (view.data + runAsync), frame by frame
   It never touches a host: every row is made here. */

import * as kit from '/dist/data-ui.js';
import '/dist/dashboard.js';

const dash = document.getElementById('dash');
const L = (window.__live = { ready: false, errors: [] });
addEventListener('error', (e) => L.errors.push(String(e.message || e.error)));
addEventListener('unhandledrejection', (e) => L.errors.push(String((e.reason && e.reason.message) || e.reason)));

const now = () => performance.now();
const afterPaint = () => new Promise((res) => requestAnimationFrame(() => setTimeout(() => res(now()), 0)));
const pct = (xs, p) => { const v = xs.filter((x) => x !== null && Number.isFinite(x)).sort((a, b) => a - b); return v.length ? v[Math.max(0, Math.ceil((p / 100) * v.length) - 1)] : null; };

let producer = null, ds = null, batches = [], draws = [], frames = [];
// WHY only while measuring: these probe arrays grow by a dozen records a frame, and a 10-minute heap run that kept them
// measured the bench, not the tier (+27 MB over 7 minutes, measured 2026-10-27)
L.recording = false;
const tick = (t) => { if (L.recording) frames.push(t); requestAnimationFrame(tick); };
requestAnimationFrame(tick);

/** Build the dashboard: M plot panels × 5 streams each, a playback bar; the retention budget in MB. */
L.setup = async ({ M = 12, rate = 1000, at = '10s', budgetMB = 256, engine = 'plot' } = {}) => {
  kit.setLiveBudget(budgetMB * 2 ** 20);
  ds = new kit.LiveDataset({ id: 'samples', title: 'Samples', time: 't', stream: 's',
    properties: { t: { type: 'number', unit: 's' }, s: { type: 'text' }, v: { type: 'number' } } });
  ds.setStatus('live', 'bench');
  L.ds = ds;
  L.streams = [];
  const views = [{ type: 'playback', name: 'Timeline' }], panels = [{ view: 'Timeline', w: 12, h: 1 }];
  for (let m = 0; m < M; m++) {
    const only = [0, 1, 2, 3, 4].map((k) => `d${m}c${k}`);
    L.streams.push(...only);
    views.push({ type: engine, name: `Device ${m}`, from: 'samples', at, plot: { y: ['v'], series: 's', only, legend: 'none' } });
    panels.push({ view: `Device ${m}`, w: M === 1 ? 12 : 4, h: 2 });
  }
  const base = { data: 'samples.json', datasets: { samples: { data: 'samples.json' } }, layout: { columns: 12, rowHeight: 110, panels }, views };
  dash.load(base, { samples: ds });
  await new Promise((r) => setTimeout(r, 50));
  for (const el of dash.querySelectorAll('data-views')) {
    el.addEventListener('data-views-live', (e) => {
      const at = now();
      if (L.recording) draws.push({ at, id: el.id, t: e.detail.t, ms: e.detail.ms, frame: e.detail.frame, rows: e.detail.rows });
      // the first plot drawn with data, then the frame that shows it (the harness's "painted")
      if (L.startAt !== undefined && L.firstPaintAt === undefined && !el.id.endsWith('-timeline')) { L.firstPaintAt = null; afterPaint().then((p) => { L.firstPaintAt = p; }); }
    });
  }
  L.rate = rate;
  L.readyAt = now();
  L.ready = true;
};

/** Stream at L.rate per stream: one columnar batch per stream every 8 ms (a host flushing its batches about twice a
    frame; the prior-art note's wire flushes every 16 ms). */
L.start = () => {
  L.startAt = now();
  let last = Date.now() / 1000;
  producer = setInterval(() => {
    const t1 = Date.now() / 1000;
    const n = Math.floor((t1 - last) * L.rate);
    if (n < 1) return;
    const stamp = now();
    const ts = new Float64Array(n);
    for (let i = 0; i < n; i++) ts[i] = last + ((i + 1) * (t1 - last)) / n;
    for (let k = 0; k < L.streams.length; k++) {
      const v = new Float64Array(n);
      for (let i = 0; i < n; i++) v[i] = Math.sin(ts[i] * (1 + (k % 7)) + k) + 0.05 * Math.sin(ts[i] * 97 + k * 3);
      ds.appendColumns({ t: ts, v }, { stream: L.streams[k] });
    }
    if (L.recording) batches.push({ stamp, t: ts[n - 1], samples: n * L.streams.length });
    last = ts[n - 1];
  }, 8);
};
L.stop = () => { clearInterval(producer); producer = null; };

/** Measure for `ms` while streaming: frame intervals, long tasks, the live loop's cost, draws per frame, latency. */
L.measure = async (ms) => {
  frames = []; draws = []; batches = [];
  const f0 = 0, d0 = 0, b0 = 0, s0 = kit.liveStats().length ? kit.liveStats().at(-1).frame : 0;
  const longs = [];
  const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) longs.push(e.duration); });
  try { po.observe({ type: 'longtask' }); } catch { /* unsupported */ }
  L.recording = true;
  await new Promise((r) => setTimeout(r, ms));
  L.recording = false;
  po.disconnect();
  const fr = frames.slice(f0), ds_ = draws.slice(d0), bs = batches.slice(b0);
  const gaps = fr.slice(1).map((x, i) => x - fr[i]);
  const live = kit.liveStats().filter((s) => s.frame > s0);
  const per = new Map();
  let worst = 0;
  for (const d of ds_) { const k = `${d.id}:${d.frame}`; per.set(k, (per.get(k) || 0) + 1); worst = Math.max(worst, per.get(k)); }
  // latency: the first plot draw whose t reaches the batch's newest sample, then the task after that frame
  const plotDraws = ds_.filter((d) => !d.id.endsWith('-timeline'));
  const lat = [];
  let j = 0;
  for (const b of bs) {
    while (j < plotDraws.length && plotDraws[j].t < b.t - 1e-9) j++;
    if (j >= plotDraws.length) break;
    const d = plotDraws[j];
    // the frame that showed it is presented after its rAF; the next frame mark after the draw is that moment's bound
    const shown = fr.find((x) => x > d.at);
    if (shown !== undefined) lat.push(shown - b.stamp);
  }
  const samples = bs.reduce((n, b) => n + b.samples, 0);
  return {
    seconds: ms / 1000, samplesPerSecond: Math.round(samples / (ms / 1000)), frames: fr.length, fps: Math.round((fr.length / ms) * 1000 * 10) / 10,
    frameP50: pct(gaps, 50), frameP95: pct(gaps, 95), frameMax: Math.max(0, ...gaps), dropped: gaps.filter((g) => g > 25).length,
    longTasks: longs.length, longTaskMs: Math.round(longs.reduce((a, b) => a + b, 0)),
    liveFrameP50: pct(live.map((s) => s.ms), 50), liveFrameP95: pct(live.map((s) => s.ms), 95),
    drawP50: pct(ds_.map((d) => d.ms), 50), drawP95: pct(ds_.map((d) => d.ms), 95), worstDrawsPerViewPerFrame: worst,
    latencyP50: pct(lat, 50), latencyP95: pct(lat, 95), latencyN: lat.length,
    bufferMB: Math.round((ds.bytes / 2 ** 20) * 10) / 10, rows: ds.rowCount,
  };
};

/** Scrub: seek to n points inside the buffer (each leaves following); time to every plot drawn at that t, painted. */
L.scrub = async (n = 30) => {
  const c = dash.clock, out = [];
  const plots = [...dash.querySelectorAll('data-views')].filter((el) => !el.id.endsWith('-timeline'));
  for (let i = 0; i < n; i++) {
    const t = c.liveStart + (c.liveEnd - c.liveStart) * (0.2 + 0.6 * ((i * 7919) % 100) / 100);
    const seen = new Set();
    const t0 = now();
    const done = new Promise((res) => {
      const on = (e) => { if (Math.abs(e.detail.t - c.t) < 1e-9) { seen.add(e.target.id); if (seen.size === plots.length) { for (const p of plots) p.removeEventListener('data-views-live', on); res(); } } };
      for (const p of plots) p.addEventListener('data-views-live', on);
    });
    c.seek(t);
    await Promise.race([done, new Promise((r) => setTimeout(r, 2000))]);
    out.push((await afterPaint()) - t0);
    await new Promise((r) => setTimeout(r, 30));
  }
  return { n, p50: pct(out, 50), p95: pct(out, 95), max: Math.max(...out) };
};

/** Back to live after a pause of `pauseMs`: goLive → every plot drawn at the newest data, painted. */
L.goLive = async (n = 10, pauseMs = 2000) => {
  const c = dash.clock, out = [], lags = [];
  const plots = [...dash.querySelectorAll('data-views')].filter((el) => !el.id.endsWith('-timeline'));
  for (let i = 0; i < n; i++) {
    c.toggle();   // Space: pause at t
    await new Promise((r) => setTimeout(r, pauseMs));
    lags.push(c.lag);
    const seen = new Set();
    const t0 = now();
    const done = new Promise((res) => {
      const on = (e) => { if (e.detail.following) { seen.add(e.target.id); if (seen.size === plots.length) { for (const p of plots) p.removeEventListener('data-views-live', on); res(); } } };
      for (const p of plots) p.addEventListener('data-views-live', on);
    });
    c.goLive();
    await Promise.race([done, new Promise((r) => setTimeout(r, 2000))]);
    out.push((await afterPaint()) - t0);
  }
  return { n, pauseMs, lagP50: pct(lags, 50), p50: pct(out, 50), p95: pct(out, 95), max: Math.max(...out) };
};

/** First paint: navigation → the dashboard ready (its .base drawn, empty), and the first rows → their plot painted. The
    sum leaves out the gap while the bench itself starts the stream (a Python round trip), which a host does not have. */
L.firstPaint = () => (typeof L.firstPaintAt === 'number' ? {
  navToReadyMs: Math.round(L.readyAt), firstRowsToPaintMs: Math.round(L.firstPaintAt - L.startAt),
  navToPaintMs: Math.round(L.readyAt + L.firstPaintAt - L.startAt),
} : null);

/**
 * The engines, side by side on the same work: each frame the window ending at the newest sample is reduced once
 * (min/max per pixel column, alignSeries) and pushed into uPlot (setData, synchronous) and into Vega (the timeseries
 * card's View: view.data('series', rows) + runAsync(), its change-set path, no re-embed). `series` streams at `rate`.
 */
L.engines = async ({ frames: nf = 240, series = 5, rate = 12000, windowS = 10, width = 860 } = {}) => {
  // a static dataset of points for the Vega card to compile its spec against, and a live one for the uPlot card
  const kv = await import('/dist/views/chart.js');
  const host = document.createElement('div');
  host.style.cssText = 'position:absolute;left:0;top:0;width:900px;height:260px;opacity:0.99';
  document.body.append(host);
  const vegaEl = document.createElement('data-views');
  vegaEl.setAttribute('no-url', '');
  vegaEl.setAttribute('toolbar', 'none');
  vegaEl.style.cssText = 'display:block;height:260px;width:900px';
  host.append(vegaEl);
  const pts = [];
  for (let k = 0; k < series; k++) for (let i = 0; i < 100; i++) pts.push({ id: `${k}:${i}`, t: i / 10, s: `c${k}`, v: Math.sin(i / 5 + k) });
  vegaEl.base = { views: [{ type: 'timeseries', name: 'Vega', timeseries: { x: 't', y: ['v'], series: 's', legend: 'none' } }] };
  vegaEl.data = { id: 'pts', properties: { t: { type: 'number' }, s: { type: 'text' }, v: { type: 'number' } }, rows: pts };
  const until = async (fn, ms = 20000) => { const end = now() + ms; while (!fn()) { if (now() > end) throw new Error('timed out'); await new Promise((r) => setTimeout(r, 20)); } };
  await until(() => vegaEl.querySelector('.dv-view-timeseries') && vegaEl.querySelector('.dv-view-timeseries').vegaView);
  const vegaView = vegaEl.querySelector('.dv-view-timeseries').vegaView;
  const plotEl = document.createElement('data-views');
  plotEl.setAttribute('no-url', '');
  plotEl.setAttribute('toolbar', 'none');
  plotEl.style.cssText = 'display:block;height:260px;width:900px';
  host.append(plotEl);
  plotEl.base = { views: [{ type: 'plot', name: 'uPlot', plot: { x: 't', y: ['v'], series: 's', legend: 'none' } }] };
  plotEl.data = { id: 'pts2', properties: { t: { type: 'number' }, s: { type: 'text' }, v: { type: 'number' } }, rows: pts };
  await until(() => plotEl.querySelector('.dv-view-plot') && plotEl.querySelector('.dv-view-plot').uplot);
  const u = plotEl.querySelector('.dv-view-plot').uplot, pv = plotEl.querySelector('.dv-view-plot').plotView;
  // the signal: `series` streams at `rate`, held as typed arrays (what the store's range() hands a card)
  const n = Math.round(rate * windowS);
  const make = (t0) => Array.from({ length: series }, (_, k) => {
    const t = new Float64Array(n), v = new Float64Array(n);
    for (let i = 0; i < n; i++) { t[i] = t0 + i / rate; v[i] = Math.sin(t[i] * (1 + k)) + 0.05 * Math.sin(t[i] * 131 + k); }
    return { name: `c${k}`, column: 'v', parts: [{ t, cols: { v } }] };
  });
  const reduceMs = [], uplotMs = [], vegaMs = [], frameGap = [];
  let t0 = 1761566400, last = now();
  for (let f = 0; f < nf; f++) {
    await new Promise((r) => requestAnimationFrame(r));
    const fnow = now();
    frameGap.push(fnow - last);
    last = fnow;
    const list = make(t0);
    t0 += 1 / 60;
    const a = list[0].parts[0].t[0], b = list[0].parts[0].t[n - 1];
    const r0 = now();
    const data = kit.alignSeries(list, a, b, width);
    reduceMs.push(now() - r0);
    const u0 = now();
    // the plot card's own path: its x range is the window, setData draws inside batch() (synchronously)
    pv._xr = [a, b];
    u.batch(() => u.setData(data));
    uplotMs.push(now() - u0);
    // Vega reads long rows: one {x, value, series} per drawn point (the timeseries card's own shape)
    const rows = [];
    for (let k = 0; k < series; k++) { const ys = data[k + 1]; for (let i = 0; i < data[0].length; i++) if (ys[i] !== null) rows.push({ x: data[0][i], value: ys[i], series: `c${k}` }); }
    const v0 = now();
    vegaView.data('series', rows).signal('xmin', a).signal('xmax', b);
    await vegaView.runAsync();
    vegaMs.push(now() - v0);
  }
  host.remove();
  const points = Math.round((kit.alignSeries(make(t0), t0, t0 + windowS, width)[0].length) * series);
  return {
    load: { series, rateHz: rate, samplesPerSecond: series * rate, windowS, samplesInWindow: n * series, pointsDrawn: points, widthPx: width, frames: nf },
    reduce: { p50: pct(reduceMs, 50), p95: pct(reduceMs, 95) },
    uplot: { p50: pct(uplotMs, 50), p95: pct(uplotMs, 95), max: Math.max(...uplotMs) },
    vega: { p50: pct(vegaMs, 50), p95: pct(vegaMs, 95), max: Math.max(...vegaMs) },
  };
};

L.loaded = true;
