/* What a plot draws of a window (docs/peps/0012-live-data.md §6.2): at most two points per pixel column per series.

   WHY min and max per pixel column (Rerun's AggregationPolicy MinMax, Foxglove's plot, M4 in Jugel et al. 2014): a
   line drawn through the minimum and the maximum of every column covers every pixel the raw samples would, so a
   one-sample spike still shows, and the work is the width, not the sample rate. The two points of a column go in time
   order (the min first when it came first), so a rising edge stays a rising edge. A column with no samples is a gap.

   Pure functions over the store's typed-array slices (LiveDataset.range), shared by the plot card and whatever else
   draws a dense series (lane/dc-plot's interactive uPlot plot can read the same columns). */

const isGap = (y) => y === null || y === undefined || Number.isNaN(y);

/** One series' slices → {x, y}: per non-empty pixel column its min and max (time order), one null where a run of
    empty columns sits between data (a gap), nothing for empty columns at the ends. */
export function minMaxColumns(parts, column, a, b, width) {
  const W = Math.max(1, Math.floor(width));
  const dx = (b - a) / W;
  const lo = new Float64Array(W).fill(Infinity), hi = new Float64Array(W).fill(-Infinity);
  const tlo = new Float64Array(W), thi = new Float64Array(W);
  for (const p of parts) {
    const t = p.t, v = p.cols[column];
    if (!v) continue;
    for (let i = 0; i < t.length; i++) {
      const y = v[i];
      if (isGap(y) || t[i] < a || t[i] > b) continue;
      const c = Math.min(W - 1, Math.floor((t[i] - a) / dx));
      if (y < lo[c]) { lo[c] = y; tlo[c] = t[i]; }
      if (y > hi[c]) { hi[c] = y; thi[c] = t[i]; }
    }
  }
  const x = [], y = [];
  let seen = false, gap = -1;
  for (let c = 0; c < W; c++) {
    if (lo[c] === Infinity) { if (seen && gap < 0) gap = c; continue; }
    if (gap >= 0) { x.push(a + (gap + 0.5) * dx); y.push(null); gap = -1; }
    seen = true;
    if (lo[c] === hi[c]) { x.push(a + (c + 0.5) * dx); y.push(lo[c]); continue; }
    const minFirst = tlo[c] <= thi[c];
    x.push(a + (c + 0.25) * dx, a + (c + 0.75) * dx);
    y.push(minFirst ? lo[c] : hi[c], minFirst ? hi[c] : lo[c]);
  }
  return { x, y };
}

/**
 * Several series → uPlot's aligned data [xs, ys1, ys2, …].
 * Sparse (every series has at most two samples per column): the series' own samples on the union of their times,
 * null where a series has no sample at an x. Dense: a shared grid of two x per pixel column, each series' min and
 * max in time order there, null in an empty column. `data.sparse[i]` says that series i has fewer samples than columns
 * (its nulls are sampling, not gaps: the plot spans them).
 */
export function alignSeries(list, a, b, width) {
  const W = Math.max(1, Math.floor(width));
  const counts = list.map((s) => s.parts.reduce((n, p) => n + p.t.length, 0));
  const dense = counts.some((n) => n > 2 * W);
  let data;
  if (!dense) {
    const pts = [];
    list.forEach((s, k) => {
      for (const p of s.parts) {
        const v = p.cols[s.column];
        if (!v) continue;
        for (let i = 0; i < p.t.length; i++) if (p.t[i] >= a && p.t[i] <= b) pts.push(p.t[i], k, isGap(v[i]) ? null : v[i]);
      }
    });
    const order = [];
    for (let i = 0; i < pts.length; i += 3) order.push(i);
    order.sort((i, j) => pts[i] - pts[j]);
    const xs = [];
    const ys = list.map(() => []);
    for (const i of order) {
      const x = pts[i];
      if (!xs.length || xs[xs.length - 1] !== x) { xs.push(x); for (const col of ys) col.push(null); }
      ys[pts[i + 1]][xs.length - 1] = pts[i + 2];
    }
    data = [xs, ...ys];
  } else {
    const dx = (b - a) / W;
    const xs = new Array(2 * W);
    for (let c = 0; c < W; c++) { xs[2 * c] = a + (c + 0.25) * dx; xs[2 * c + 1] = a + (c + 0.75) * dx; }
    data = [xs];
    for (const s of list) {
      const lo = new Float64Array(W).fill(Infinity), hi = new Float64Array(W).fill(-Infinity);
      const tlo = new Float64Array(W), thi = new Float64Array(W);
      for (const p of s.parts) {
        const v = p.cols[s.column];
        if (!v) continue;
        for (let i = 0; i < p.t.length; i++) {
          const y = v[i];
          if (isGap(y) || p.t[i] < a || p.t[i] > b) continue;
          const c = Math.min(W - 1, Math.floor((p.t[i] - a) / dx));
          if (y < lo[c]) { lo[c] = y; tlo[c] = p.t[i]; }
          if (y > hi[c]) { hi[c] = y; thi[c] = p.t[i]; }
        }
      }
      const ys = new Array(2 * W);
      for (let c = 0; c < W; c++) {
        if (lo[c] === Infinity) { ys[2 * c] = ys[2 * c + 1] = null; continue; }
        const minFirst = tlo[c] <= thi[c];
        ys[2 * c] = minFirst ? lo[c] : hi[c];
        ys[2 * c + 1] = minFirst ? hi[c] : lo[c];
      }
      data.push(ys);
    }
  }
  data.sparse = counts.map((n) => n < W);
  return data;
}

/**
 * min / max columns kept between frames (Rerun's lesson, blog "primary query caching": cache and invalidate, do not
 * recompute). The columns sit on an absolute time grid (column k covers [k·dx, (k+1)·dx)), so a window that slides
 * by a frame reuses every column but the newest few and the one its start cuts into, and a dense signal does not
 * shimmer as the window moves (a window-relative grid re-bins every sample every frame). A new width or window
 * length, a jump back in time or a new set of series rebuilds.
 *   const cache = new ColumnCache();
 *   const data = cache.data(list, a, b, width);   // list: [{name, ds, stream, column}] → uPlot's aligned arrays
 * While the window holds no more than two samples per column it draws the samples themselves (alignSeries).
 * Reading only what is new at each stream's end misses two things, and the store's logs say when they happened:
 * retention taking a chunk inside the window (dropsSince: the columns are rebuilt), and a sample that went in before
 * samples already folded (reordersSince: its stream is folded again from there; min and max do not mind a sample
 * folded twice). Within LATE of a stream's newest that read-back happens every frame anyway.
 */
const LATE = 0.25;   // s a stream's rows may arrive behind its newest and still reach a cached column

export class ColumnCache {
  constructor() { this.reset(); }

  reset() { this.dx = null; this.series = new Map(); this.k0 = null; this.b = null; this.out = null; }

  /** The store's logs as of this frame (a different dataset, or none: everything is new). */
  _seen(ds) { this.ds = ds; this.dropGen = ds ? ds.dropGen : null; this.roGen = ds ? ds.reorderGen : null; }

  data(list, a, b, width) {
    const W = Math.max(1, Math.floor(width));
    const dx = (b - a) / W;
    let total = 0;
    for (const s of list) {
      for (const p of s.ds.range(a, b, { stream: s.stream, columns: [s.column] })) total += p.t.length;
      if (total > 2 * W) break;
    }
    const ds = list.length ? list[0].ds : null;
    if (total <= 2 * W) {
      this.reset();
      this.mode = 'sparse';
      this._seen(ds);
      return alignSeries(list.map((s) => ({ name: s.name, column: s.column, parts: s.ds.range(a, b, { stream: s.stream, columns: [s.column] }) })), a, b, W);
    }
    const k0 = Math.floor(a / dx), k1 = Math.floor(b / dx);
    const known = !!ds && this.ds === ds;
    const drops = known ? ds.dropsSince(this.dropGen) : null, ro = known ? ds.reordersSince(this.roGen) : null;
    // retention took samples inside the window: their columns must go, so the window is read again
    const gone = drops === null || ro === null || drops.some((x) => x.t1 > a && x.t0 <= b);
    const same = !gone && this.dx !== null && Math.abs(this.dx - dx) <= 1e-9 * Math.abs(dx) && this.series.size === list.length
      && list.every((s) => this.series.has(s.name)) && k0 >= this.k0 && b >= this.b;
    if (!same) { this.reset(); this.dx = dx; }
    const edge = (k0 + 1) * dx;
    for (const s of list) {
      let st = this.series.get(s.name);
      if (!st) { st = { cols: new Map(), last: -Infinity }; this.series.set(s.name, st); }
      // the columns the window slid past go, and the one its start cuts into is read again from a exactly
      for (const k of st.cols.keys()) if (k <= k0) st.cols.delete(k);
      this._fold(st, s, a, Math.min(b, edge));
      // then what is new since this series' newest folded sample (each stream's own: streams arrive out of step),
      // reaching back LATE seconds for rows that came in a little out of order, and further back to any sample of
      // this stream that went in before samples already folded (the store's reorder log)
      let from = st.last - Math.max(LATE, 2 * dx);
      if (same) for (const x of ro) if (x.t > edge && x.t <= b && x.t - dx < from && (s.stream === null || s.stream === undefined || x.stream === String(s.stream))) from = x.t - dx;
      this._fold(st, s, Math.max(from, edge), b);
    }
    this._seen(ds);
    this.k0 = k0;
    this.b = b;
    // the arrays uPlot draws, reused frame to frame: no garbage at 60 frames a second
    const n = 2 * (k1 - k0 + 1);
    const out = this.out && this.out.length === list.length + 1 ? this.out : (this.out = [[], ...list.map(() => [])]);
    for (const arr of out) arr.length = n;
    const xs = out[0];
    for (let k = k0, i = 0; k <= k1; k++, i += 2) { xs[i] = (k + 0.25) * dx; xs[i + 1] = (k + 0.75) * dx; }
    list.forEach((s, j) => {
      const cols = this.series.get(s.name).cols, ys = out[j + 1];
      for (let k = k0, i = 0; k <= k1; k++, i += 2) {
        const c = cols.get(k);
        if (!c) { ys[i] = ys[i + 1] = null; continue; }
        const minFirst = c[2] <= c[3];
        ys[i] = minFirst ? c[0] : c[1];
        ys[i + 1] = minFirst ? c[1] : c[0];
      }
    });
    out.sparse = list.map(() => false);
    this.mode = same ? 'cached' : 'rebuilt';
    return out;
  }

  /** Fold the samples of (lo, hi] into their columns (min, max and when each was). */
  _fold(st, s, lo, hi) {
    if (!(hi > lo)) return;
    const dx = this.dx;
    for (const p of s.ds.range(lo, hi, { stream: s.stream, columns: [s.column] })) {
      const t = p.t, v = p.cols[s.column];
      for (let i = 0; i < t.length; i++) {
        const y = v[i];
        if (y === null || y !== y) continue;   // null or NaN: no sample
        const k = Math.floor(t[i] / dx);
        const c = st.cols.get(k);
        if (!c) st.cols.set(k, [y, y, t[i], t[i]]);
        else { if (y < c[0]) { c[0] = y; c[2] = t[i]; } if (y > c[1]) { c[1] = y; c[3] = t[i]; } }
      }
      if (t.length && t[t.length - 1] > st.last) st.last = t[t.length - 1];
    }
  }
}

// ------------------------------------------------------------------ guide rows: a live plot's limits, rules and bands

/* A live plot holds no row objects (it reads the store's typed arrays), and the guides it draws from a property (§35's
   limits, rules and bands; core guides.js) are read from rows. guideRows hands guides.js the rows of a window that
   carry every change of a guide column: per stream, its first and last sample in (a, b] and both sides of every
   change of any of the columns. The guides drawn from them are the guides drawn from every row in the window (a step
   line goes through each change; a constant spans the drawn x), from a few rows instead of one per sample.
   WHY (RobotDx PEP 0001 §18.4, ask 1): a plot on live data drew no limit, since it had no rows to read them from.
   The changes inside a sealed chunk never change, so they are found once per chunk and its columns (RUNS); the open
   chunk, at most CHUNK_ROWS samples, is read again each time. */

const RUNS = new WeakMap();   // a sealed chunk → {<columns>: the indexes on either side of a change, in order}

/** A guide column's value as runs compare it: a rich cell's value; no value (null, undefined, NaN) is one value. */
function runValue(arr, i) {
  if (!arr) return null;
  let v = arr[i];
  if (v !== null && typeof v === 'object' && !Array.isArray(v) && 'value' in v) v = v.value;
  return v === undefined || v === null || (typeof v === 'number' && Number.isNaN(v)) ? null : v;
}
const same = (arrs, i, brr, j) => { for (let k = 0; k < arrs.length; k++) if (runValue(arrs[k], i) !== runValue(brr[k], j)) return false; return true; };

/** The indexes in [0, n) on either side of a change of any column, in order. */
function changes(arrs, n) {
  const out = [];
  for (let i = 1; i < n; i++) {
    if (same(arrs, i - 1, arrs, i)) continue;
    if (out[out.length - 1] !== i - 1) out.push(i - 1);
    out.push(i);
  }
  return out;
}

/** A slice's changes, as indexes into the slice: from the chunk's (cached once it is sealed), else from the slice. */
function sliceChanges(p, columns, arrs) {
  const c = p.chunk;
  if (!c || !c.sealed) return changes(arrs, p.t.length);
  let byCols = RUNS.get(c);
  if (!byCols) RUNS.set(c, (byCols = new Map()));
  const key = columns.join('\u0001');
  let idx = byCols.get(key);
  if (!idx) {
    idx = Int32Array.from(changes(columns.map((col) => c.num[col] || c.any[col] || null), c.n));
    byCols.set(key, idx);
  }
  const out = [];
  for (const i of idx) if (i >= p.from && i < p.to) out.push(i - p.from);
  return out;
}

/** One row of a slice: its time, its stream (when the rows carry one) and the guide columns' values (no value: null). */
function guideRow(p, i, columns, x, series) {
  const r = { [x]: p.t[i] };
  if (series) r[series] = p.stream;
  for (const col of columns) {
    const a = p.cols[col];
    const v = a ? a[i] : null;
    r[col] = v === undefined || (typeof v === 'number' && Number.isNaN(v)) ? null : v;
  }
  return r;
}

/**
 * The rows guides.js reads of a live window (a, b] (guidesFrom, limitGuides): per stream, the samples that begin or end
 * a run of the guide columns' values.
 *   streams  the plot's series: stream names (an append dataset's `stream:` values, a keyed one's keys), or [null] for
 *            every stream drawn as one series (its rows carry no series; several streams are merged by time first)
 *   columns  the properties the guides read (the limits' ends, the rules' and bands' bounds that name a property)
 *   x        the name the rows carry the time under (the plot's x); series the name they carry their stream under
 */
export function guideRows(ds, streams, a, b, columns, { x = ds.time, series = ds.stream } = {}) {
  const cols = [...new Set((columns || []).filter((c) => typeof c === 'string' && c))];
  const one = !streams.length || (streams.length === 1 && (streams[0] === null || streams[0] === undefined));
  if (one && ds.streams().length > 1) return mergedRows(ds, a, b, cols, x);
  const out = [];
  for (const s of one ? [null] : streams) {
    let prev = null, last = null;
    const take = (p, i) => {
      if (last && last.p === p && last.i === i) return;
      last = { p, i };
      out.push(guideRow(p, i, cols, x, one ? null : series));
    };
    for (const p of ds.range(a, b, { stream: s, columns: cols })) {
      const n = p.t.length;
      if (!n) continue;
      const arrs = cols.map((col) => p.cols[col] || null);
      // a slice's first sample begins a run when it is the window's first, or when it differs from the sample before it
      // (the last of the stream's previous chunk): then that one ends a run
      if (!prev) take(p, 0);
      else if (!same(prev.arrs, prev.i, arrs, 0)) { take(prev.p, prev.i); take(p, 0); }
      for (const i of sliceChanges(p, cols, arrs)) take(p, i);
      prev = { p, i: n - 1, arrs };
    }
    if (prev) take(prev.p, prev.i);
  }
  return out;
}

/** Every stream as one series: the window's samples merged by time (a tie in the streams' order), then its runs. */
function mergedRows(ds, a, b, cols, x) {
  const parts = ds.range(a, b, { stream: null, columns: cols });
  const order = new Map(ds.streams().map((s, k) => [String(s), k]));
  const at = [];
  parts.forEach((p, k) => { for (let i = 0; i < p.t.length; i++) at.push([p.t[i], order.get(String(p.stream)) ?? 0, k, i]); });
  at.sort((u, v) => u[0] - v[0] || u[1] - v[1] || u[2] - v[2] || u[3] - v[3]);
  const arrsOf = parts.map((p) => cols.map((col) => p.cols[col] || null));
  const out = [];
  at.forEach(([, , k, i], n) => {
    const before = n > 0 ? at[n - 1] : null, after = n + 1 < at.length ? at[n + 1] : null;
    const edge = !before || !after || !same(arrsOf[before[2]], before[3], arrsOf[k], i) || !same(arrsOf[k], i, arrsOf[after[2]], after[3]);
    if (edge) out.push(guideRow(parts[k], i, cols, x, null));
  });
  return out;
}
