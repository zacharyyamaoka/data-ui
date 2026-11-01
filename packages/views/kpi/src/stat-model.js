/* The arithmetic of the stat cards (gauge, bullet, barlist, status), pure and free of imports so node --test runs it as
   is (tests/unit/stat.test.mjs): fractions of a scale, band segments, an arc as an SVG path, the bar list's order and
   widths, the tracker's tones. The views (gauge.js, bullet.js, barlist.js, status.js) do the reading of rows and the
   drawing; nothing here touches the DOM or a cell. */

export const TONES = ['good', 'warn', 'bad', 'muted', 'neutral'];

const finite = (x) => typeof x === 'number' && Number.isFinite(x);

/** Where `value` sits on [min, max] as 0..1; clipped, and `clipped` says it was outside. null on a scale that is not one. */
export function fraction(value, min, max) {
  if (!finite(value) || !finite(min) || !finite(max) || max <= min) return null;
  const f = (value - min) / (max - min);
  return { f: Math.min(1, Math.max(0, f)), clipped: f > 1 ? 'high' : f < 0 ? 'low' : null };
}

/** A tidy upper end for a scale that has none: the next of 1, 2, 2.5, 5, 10 x 10^k at or above x. */
export function niceMax(x) {
  if (!finite(x) || x <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(x));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((c) => c >= x * 0.999999) || 10 * p;
}

/** Bands [{to?, tone}] over [min, max] as segments {from, to, tone, f0, f1}; the last band (or one without `to`) runs to max. */
export function bandSegments(bands, min, max) {
  if (!Array.isArray(bands) || !bands.length || !(max > min)) return [];
  const out = [];
  let from = min;
  bands.forEach((b, i) => {
    const last = i === bands.length - 1;
    const to = last || !finite(b.to) ? max : Math.min(max, Math.max(from, b.to));
    if (to > from) out.push({ from, to, tone: b.tone || 'neutral', f0: (from - min) / (max - min), f1: (to - min) / (max - min) });
    from = to;
  });
  return out;
}

/** The tone of the band holding `value` (a value on a band's `to` belongs to that band); null with no bands. */
export function bandTone(bands, value) {
  if (!Array.isArray(bands) || !bands.length || !finite(value)) return null;
  for (let i = 0; i < bands.length; i++) if (i === bands.length - 1 || !finite(bands[i].to) || value <= bands[i].to) return bands[i].tone || 'neutral';
  return null;
}

/** On which side of `target` is `value`, and is that the better one? {dir: 'over'|'under'|'on', diff, good}. */
export function againstTarget(value, target, better = 'higher') {
  if (!finite(value) || !finite(target)) return null;
  const diff = value - target;
  if (diff === 0) return { dir: 'on', diff: 0, good: true };
  return { dir: diff > 0 ? 'over' : 'under', diff: Math.abs(diff), good: (diff > 0) === (better !== 'lower') };
}

/** The point at fraction f of a semicircle drawn left (f = 0) over the top to right (f = 1): centre (cx, cy), radius r. */
export function arcPoint(cx, cy, r, f) {
  const a = Math.PI * (1 - f);
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
}

/** The SVG path of the arc between fractions f0 and f1 of that semicircle ('' when empty). */
// WHY large-arc 0 always: a semicircle's arc never spans more than 180°; the old "> 0.5 → 1" drew any gauge over half
// the long way round, outside the gauge (found by the Vibe Tracks rebuild, 2026-10-26)
export function arcPath(cx, cy, r, f0 = 0, f1 = 1) {
  if (!(f1 > f0)) return '';
  const [x0, y0] = arcPoint(cx, cy, r, f0);
  const [x1, y1] = arcPoint(cx, cy, r, f1);
  return `M${x0.toFixed(2)},${y0.toFixed(2)}A${r},${r} 0 0 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
}

/** Bar list: entries [{label, value, ...}] ordered by value (descending; ascending when better is lower), a missing
    value last, cut to `limit`; each shown row gets frac = value / max over ALL entries (so a limit never rescales the
    bars). Returns {rows, rest: entries past the limit, max}. WHY ties keep their input order: a stable sort, so the
    list does not shuffle between draws. */
export function barlistRows(entries, { limit, better = 'higher' } = {}) {
  const has = (e) => finite(e.value);
  const sign = better === 'lower' ? 1 : -1;
  const sorted = entries.map((e, i) => ({ e, i })).sort((a, b) => {
    if (has(a.e) !== has(b.e)) return has(a.e) ? -1 : 1;
    return has(a.e) ? sign * (a.e.value - b.e.value) || a.i - b.i : a.i - b.i;
  }).map((x) => x.e);
  const max = sorted.reduce((m, e) => (has(e) && e.value > m ? e.value : m), 0);
  const cut = Number.isInteger(limit) && limit > 0 && limit < sorted.length ? limit : sorted.length;
  return { rows: sorted.slice(0, cut).map((e) => ({ ...e, frac: has(e) && max > 0 ? Math.max(0, e.value) / max : 0 })), rest: sorted.slice(cut), max };
}

/** Band shade levels for a bullet's bands: 0 (lightest) .. n-1 (darkest). The worst band is the darkest (Stephen Few's
    bullet): the first for `higher` is better, the last for `lower`. */
export function shadeLevels(n, better = 'higher') {
  return Array.from({ length: n }, (_v, i) => (better === 'lower' ? i : n - 1 - i));
}

/** A tracker cell's tone for a state value: the declared tone, `muted` for a missing state, `neutral` for one not listed. */
export function stateTone(state, tones = {}) {
  if (state === null || state === undefined || state === '') return 'muted';
  const t = tones[state] ?? tones[String(state)];
  return TONES.includes(t) ? t : 'neutral';
}

/** The gate matrix (docs/CONTRACT.md §35; sim2real gap #11): `lines` [{key, label, rows}] (the groups, in order) →
    {columns, rows: [{key, label, cells: [{column, rows, n, state, na}]}]}. The columns are the ones asked for (`columns`)
    first, in that order, then every other value of `column` in the order the rows first show them, so nothing is
    hidden; a row with no column value lands in a null column, last. A cell no row reaches is n/a; a cell several rows
    reach is the worst of them by `order` (best first; a value it does not hold ranks best, so an unexpected word never
    hides a known problem). `read(row, column)` reads a cell (the view passes the core's cellValue). */
export function matrixCells(lines, { column, columns = null, state, order = [], read = (r, c) => r[c] } = {}) {
  const key = (v) => (v === null || v === undefined || v === '' ? null : String(v));
  const cols = [];
  const seen = new Set();
  for (const c of Array.isArray(columns) ? columns : []) { const k = key(c); if (k !== null && !seen.has(k)) { seen.add(k); cols.push(c); } }
  let nulls = false;
  for (const line of lines || []) {
    for (const r of line.rows || []) {
      const v = read(r, column);
      const k = key(v);
      if (k === null) { nulls = true; continue; }
      if (!seen.has(k)) { seen.add(k); cols.push(v); }
    }
  }
  if (nulls) cols.push(null);
  const worst = (values) => {
    let best = null, rank = -2;
    for (const v of values) {
      if (v === null || v === undefined || v === '') continue;
      const r = order.indexOf(String(v));
      if (r > rank) { rank = r; best = v; }
    }
    return best;
  };
  const rows = (lines || []).map((line) => {
    const by = new Map();
    for (const r of line.rows || []) {
      const k = key(read(r, column));
      if (!by.has(k)) by.set(k, []);
      by.get(k).push(r);
    }
    const cells = cols.map((c) => {
      const rs = by.get(key(c)) || [];
      return { column: c, rows: rs, n: rs.length, na: rs.length === 0, state: rs.length ? worst(rs.map((r) => read(r, state))) : null };
    });
    return { key: line.key, label: line.label, cells };
  });
  return { columns: cols, rows };
}

/** A KPI's target (docs/CONTRACT.md §35, kpi_trend): a number as written; a property, the newest row's value of it (as the
    gauge reads min, max and target); else null. */
export function targetValue(target, latest, read = (r, c) => r[c]) {
  if (typeof target === 'number') return Number.isFinite(target) ? target : null;
  if (typeof target !== 'string' || !target || !latest) return null;
  const v = read(latest, target);
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
