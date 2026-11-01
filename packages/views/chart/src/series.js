/* The pure parts of the time series and trajectory cards (docs/peps/0005-dashboard-cards.md §2b): series naming,
   colour and dash, windowing, min/max decimation, nearest sample, interpolation along t and equal-aspect domains.
   No DOM, no Vega and no core import, so tests/unit/timeseries.test.mjs runs them in Node as they are. */

export const TARGET = 'target';
// WHY 3000: past about one sample per pixel column a line is ink, not information; drawing min and max per column
// keeps every peak (the eye's envelope) at a few thousand points however long the run
export const DENSE = 3000;

const num = (v) => typeof v === 'number' && Number.isFinite(v);

/** The long rows of a time series: one {x, value, series} per sample per y column, and the series in the order
    they first appear. Names: the split value; with several y columns "<value> · <column label>"; with no split the
    column's label. `read(row, field)` gives a cell's value; `label(field)` a column's label; `time(v)` an x as a
    number (seconds, or ms for a date). A sample without a numeric x or value is left out (missing is never 0). */
export function longRows(rows, { x, y, series }, { read, label, time = (v) => v }) {
  const ys = Array.isArray(y) ? y : [y];
  const several = ys.length > 1;
  const list = [];
  const byName = new Map();
  const points = [];
  for (const row of rows) {
    const xv = time(read(row, x));
    if (!num(xv)) continue;
    const split = series ? read(row, series) : undefined;
    for (const col of ys) {
      const v = read(row, col);
      if (!num(v)) continue;
      const value = series ? (split === null || split === undefined || split === '' ? '—' : String(split)) : null;
      const name = series ? (several ? `${value} · ${label(col)}` : value) : label(col);
      if (!byName.has(name)) { const s = { name, value, column: col, points: [] }; byName.set(name, s); list.push(s); }
      const p = { x: xv, value: v, series: name };
      byName.get(name).points.push(p);
      points.push(p);
    }
  }
  for (const s of list) s.points.sort((a, b) => a.x - b.x);
  return { list, points };
}

/** Each series' colour and dash. Dashed: a series named (or split by the value) "target", or listed in `dash` by
    name, value or column. Colour: the palette by name (then by split value); a dashed series it does not list is
    muted; anything else takes `slot(name)`, the stable series slot. */
export function seriesStyles(list, { palette = {}, dash = [], slot, muted }) {
  const listed = new Set((dash || []).map(String));
  return list.map((s) => {
    const dashed = s.name === TARGET || s.value === TARGET || listed.has(s.name) || (s.value !== null && listed.has(String(s.value))) || (s.column && listed.has(s.column));
    const own = (palette && (palette[s.name] || (s.value !== null && palette[s.value]))) || null;
    return { ...s, dashed, color: own || (dashed ? muted : slot(s.name)) };
  });
}

/** The index of the first point with x >= at (points sorted by x). */
export function lowerBound(points, at, key = (p) => p.x) {
  let lo = 0, hi = points.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (key(points[m]) < at) lo = m + 1; else hi = m; }
  return lo;
}

/** The points inside [x0, x1] plus one neighbour on each side, so a line runs to the plot's edges. */
export function windowed(points, x0, x1) {
  const a = Math.max(0, lowerBound(points, x0) - 1);
  let b = lowerBound(points, x1);
  while (b < points.length && points[b].x <= x1) b++;   // past every point at x1 itself
  b = Math.min(points.length, b + 1);
  return a === 0 && b === points.length ? points : points.slice(a, b);
}

/** Min/max decimation per pixel column, for drawing only: under DENSE points nothing changes; above, each of
    `columns` columns over [x0, x1] keeps its first, lowest, highest and last point, in x order. */
export function decimate(points, x0, x1, columns, limit = DENSE) {
  if (points.length <= limit || !(x1 > x0) || !(columns > 0)) return points;
  const out = [];
  let col = null, first, lo, hi, last;
  const flush = () => {
    if (col === null) return;
    const keep = [first, lo, hi, last].filter((p, i, a) => a.indexOf(p) === i).sort((a, b) => a.x - b.x);
    out.push(...keep);
  };
  const k = columns / (x1 - x0);
  for (const p of points) {
    const c = Math.floor((p.x - x0) * k);
    if (c !== col) { flush(); col = c; first = lo = hi = last = p; continue; }
    if (p.value < lo.value) lo = p;
    if (p.value > hi.value) hi = p;
    last = p;
  }
  flush();
  return out;
}

/** The point nearest x (points sorted by x), or null outside their span. */
export function nearest(points, x) {
  if (!points.length || x < points[0].x || x > points[points.length - 1].x) return null;
  const i = lowerBound(points, x);
  if (i <= 0) return points[0];
  if (i >= points.length) return points[points.length - 1];
  return x - points[i - 1].x <= points[i].x - x ? points[i - 1] : points[i];
}

/** [x, y] at time t along a path sampled at ts (sorted), linearly interpolated; clamped to its ends. */
export function along(ts, xs, ys, t) {
  const n = ts.length;
  if (!n) return null;
  if (t <= ts[0]) return [xs[0], ys[0], 0];
  if (t >= ts[n - 1]) return [xs[n - 1], ys[n - 1], n - 1];
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
  const f = ts[hi] === ts[lo] ? 0 : (t - ts[lo]) / (ts[hi] - ts[lo]);
  return [xs[lo] + (xs[hi] - xs[lo]) * f, ys[lo] + (ys[hi] - ys[lo]) * f, lo];
}

/** Domains for an equal-aspect plot w × h px: the same data units per px on x and y, the data centred and padded
    by `pad` of its larger span. Returns {x: [a, b], y: [c, d], unit} where unit is px per data unit. */
export function equalAspect([x0, x1], [y0, y1], w, h, pad = 0.06) {
  const sx = Math.max(x1 - x0, 0), sy = Math.max(y1 - y0, 0);
  const span = Math.max(sx, sy) || 1;
  const px = sx + 2 * pad * span, py = sy + 2 * pad * span;
  const per = Math.max(px / w, py / h);   // data units per px
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  return { x: [cx - (per * w) / 2, cx + (per * w) / 2], y: [cy - (per * h) / 2, cy + (per * h) / 2], unit: 1 / per };
}
