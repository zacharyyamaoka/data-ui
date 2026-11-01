/* Rules and bands from a property (docs/peps/0010-robotics-playback.md §5.4 and §10's threshold_band; sim2real gap #6:
   "Reference lines can't come from a property, so per-device floors are emitted as extra rows"). Shared by the
   timeseries card (Vega-Lite), its interactive form (uPlot) and the live plot (uPlot).

     rules: [{y: <number> | <property>, label, tone}]
     bands: [{y: [<number> | <property>, <number> | <property>], label, tone}]

   A number is the plain rule or band it always was (the views draw those themselves; this returns none). A property is
   read from the rows the view draws, per series, so a device's own limit follows the rail's device pick and a series
   split by device draws each device's own. One value over a series' rows is a constant, drawn across the data's x
   (both ends at the drawn rows' x extent); a value that changes is a step line through it (step-after: the first
   point, each change, the last x), which is how a limit that changes over time reads. Series that draw the same line
   share one (a run's real, twin and target rows carry one device limit). A missing value is skipped, never a 0; a
   series the legend hides draws none. No import: rows in, points out (tests/unit/guides.test.mjs). */

const finite = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const isProp = (v) => typeof v === 'string' && v !== '';
const textOf = (v) => (v === null || v === undefined || v === '' ? null : String(v));

/** A step line through (x, value…) pairs in x order: the first, each change, the last x. `same(a, b)` compares values. */
function steps(pairs, same) {
  const out = [];
  for (const p of pairs) if (!out.length || !same(out[out.length - 1][1], p[1])) out.push(p);
  const last = pairs[pairs.length - 1];
  if (out.length && last && out[out.length - 1][0] !== last[0]) out.push(last);
  return out;
}

/** rows → {rules: [{guide: 'rule:<i>', series, shared, label, tone, constant: v | null, points: [[x, v]…]}], bands:
    [{guide: 'band:<i>', series, shared, label, tone, constant: [lo, hi] | null, lo: [[x, v]…], hi: [[x, v]…]}]}, for
    the rules and bands whose bounds name a property. `read(row, column)` reads a cell (a view passes the core's
    cellValue); `series` the column that splits the series (null: one); `hidden` the series the legend hides. */
export function guidesFrom(rows, { rules = [], bands = [] } = {}, { x = 't', series = null, read = (r, c) => r[c], hidden = [] } = {}) {
  const off = new Set((hidden || []).map(String));
  const groups = new Map();
  let x0 = Infinity, x1 = -Infinity;
  for (const r of rows || []) {
    const s = series ? textOf(read(r, series)) : null;
    if (s !== null && off.has(s)) continue;
    const xv = finite(read(r, x));
    if (xv === null) continue;
    if (xv < x0) x0 = xv;
    if (xv > x1) x1 = xv;
    if (!groups.has(s)) groups.set(s, []);
    groups.get(s).push([xv, r]);
  }
  // each series in x order (stable: rows at one x keep file order)
  for (const g of groups.values()) g.sort((a, b) => a[0] - b[0]);
  const out = { rules: [], bands: [] };
  if (!groups.size) return out;
  const valueOf = (r, y) => (isProp(y) ? finite(read(r, y)) : finite(y));
  (Array.isArray(rules) ? rules : []).forEach((rule, i) => {
    if (!rule || !isProp(rule.y)) return;
    const seen = new Map();
    for (const [s, g] of groups) {
      const pairs = [];
      for (const [xv, r] of g) { const v = valueOf(r, rule.y); if (v !== null) pairs.push([xv, v]); }
      if (!pairs.length) continue;
      const pts = steps(pairs, (a, b) => a === b);
      const constant = pts.every((p) => p[1] === pts[0][1]) ? pts[0][1] : null;
      const points = constant !== null ? [[x0, constant], [x1, constant]] : pts;
      const key = JSON.stringify(points);
      if (seen.has(key)) { seen.get(key).shared.push(s); continue; }
      const g2 = { guide: `rule:${i}`, series: s, shared: [s], label: rule.label || null, tone: rule.tone || null, constant, points };
      seen.set(key, g2);
      out.rules.push(g2);
    }
  });
  (Array.isArray(bands) ? bands : []).forEach((band, i) => {
    if (!band || !Array.isArray(band.y) || band.y.length !== 2 || !band.y.some(isProp)) return;
    const seen = new Map();
    for (const [s, g] of groups) {
      const pairs = [];
      for (const [xv, r] of g) {
        const lo = valueOf(r, band.y[0]), hi = valueOf(r, band.y[1]);
        if (lo !== null && hi !== null) pairs.push([xv, [lo, hi]]);
      }
      if (!pairs.length) continue;
      const pts = steps(pairs, (a, b) => a[0] === b[0] && a[1] === b[1]);
      const fixed = pts.every((p) => p[1][0] === pts[0][1][0] && p[1][1] === pts[0][1][1]);
      const constant = fixed ? [pts[0][1][0], pts[0][1][1]] : null;
      const lo = fixed ? [[x0, constant[0]], [x1, constant[0]]] : pts.map((p) => [p[0], p[1][0]]);
      const hi = fixed ? [[x0, constant[1]], [x1, constant[1]]] : pts.map((p) => [p[0], p[1][1]]);
      const key = JSON.stringify([lo, hi]);
      if (seen.has(key)) { seen.get(key).shared.push(s); continue; }
      const g2 = { guide: `band:${i}`, series: s, shared: [s], label: band.label || null, tone: band.tone || null, constant, lo, hi };
      seen.set(key, g2);
      out.bands.push(g2);
    }
  });
  return out;
}

/** Whether a rule or band list names a property anywhere (the views keep their old drawing when none does). */
export const guidesNameProperty = ({ rules = [], bands = [] } = {}) =>
  (rules || []).some((r) => r && isProp(r.y)) || (bands || []).some((b) => b && Array.isArray(b.y) && b.y.some(isProp));

// ------------------------------------------------------------------------------------------------ limits (threshold_band)
/* `limits: {warn: [lo, hi], error: [lo, hi]}` (docs/CONTRACT.md §35; PEP 0010 §10's threshold_band, P5 for warn and
   error): RobotDx's Limits as data, the diagnostic row's warn_lo, warn_hi, error_lo and error_hi. Each end is a number, a
   property read per series from the drawn rows (a device's own limit follows the rail's pick; a split by device draws
   each device's own), or null: no limit on that side. Per series: a rule at each limit present, and the zones beyond
   them: between a warn and an error limit in the warn tone, from an error limit (or a warn limit with nothing beyond it)
   to the plot's edge, which an end of null stands for. WHY Grafana's thresholds "as filled regions" and "as lines" both:
   a line alone says where the limit is, a zone says which side is the bad one. */
const BOUNDS = ['warn_lo', 'warn_hi', 'error_lo', 'error_hi'];
const LIMIT_LOOK = { warn_lo: ['warn', '! warn'], warn_hi: ['warn', '! warn'], error_lo: ['bad', '✕ error'], error_hi: ['bad', '✕ error'] };

/** rows → {rules: [{guide: 'limit:<bound>', bound, series, shared, tone, label, constant, points: [[x, v]…]}], zones:
    [{guide: 'zone:<bound>', bound, series, shared, tone, lo: [[x, v | null]…], hi: [[x, v | null]…]}]}: rules in the
    bounds' order (warn_lo, warn_hi, error_lo, error_hi) then the series', zones likewise (a zone is named for the limit it
    starts from). A constant spans the drawn rows' x; a limit that changes is a step line; a missing value is skipped; a
    hidden series draws none; series drawing the same line share it (the first names it, `shared` lists them all). */
export function limitGuides(rows, limits, { x = 't', series = null, read = (r, c) => r[c], hidden = [] } = {}) {
  const out = { rules: [], zones: [] };
  if (!limits || typeof limits !== 'object') return out;
  const end = { warn_lo: null, warn_hi: null, error_lo: null, error_hi: null };
  for (const side of ['warn', 'error']) {
    const pair = limits[side];
    if (!Array.isArray(pair)) continue;
    end[`${side}_lo`] = pair[0] === undefined ? null : pair[0];
    end[`${side}_hi`] = pair[1] === undefined ? null : pair[1];
  }
  const live = BOUNDS.filter((b) => isProp(end[b]) || finite(end[b]) !== null);
  if (!live.length) return out;
  const off = new Set((hidden || []).map(String));
  const groups = new Map();
  let x0 = Infinity, x1 = -Infinity;
  for (const r of rows || []) {
    const s = series ? textOf(read(r, series)) : null;
    if (s !== null && off.has(s)) continue;
    const xv = finite(read(r, x));
    if (xv === null) continue;
    if (xv < x0) x0 = xv;
    if (xv > x1) x1 = xv;
    if (!groups.has(s)) groups.set(s, []);
    groups.get(s).push([xv, r]);
  }
  if (!groups.size) return out;
  for (const g of groups.values()) g.sort((a, b) => a[0] - b[0]);
  const valueOf = (r, b) => (isProp(end[b]) ? finite(read(r, end[b])) : finite(end[b]));
  /** pairs [[x, v]] → a constant spanning [x0, x1], or the step line. */
  const shape = (pairs, same) => {
    const pts = steps(pairs, same);
    const fixed = pts.every((p) => same(p[1], pts[0][1]));
    return { constant: fixed ? pts[0][1] : null, points: fixed ? [[x0, pts[0][1]], [x1, pts[0][1]]] : pts };
  };
  // which limits each series has at all: a zone runs to the next limit the series has, else to the edge
  const present = new Map();
  for (const [s, g] of groups) present.set(s, new Set(live.filter((b) => g.some(([, r]) => valueOf(r, b) !== null))));
  for (const b of live) {
    const seen = new Map();
    for (const [s, g] of groups) {
      const pairs = [];
      for (const [xv, r] of g) { const v = valueOf(r, b); if (v !== null) pairs.push([xv, v]); }
      if (!pairs.length) continue;
      const { constant, points } = shape(pairs, (a, c) => a === c);
      const key = JSON.stringify(points);
      if (seen.has(key)) { seen.get(key).shared.push(s); continue; }
      const [tone, label] = LIMIT_LOOK[b];
      const rule = { guide: `limit:${b}`, bound: b, series: s, shared: [s], tone, label, constant, points };
      seen.set(key, rule);
      out.rules.push(rule);
    }
  }
  // the zones: [lo end, hi end] per row, null for the plot's edge
  const zoneOf = {
    warn_hi: (has) => ({ lo: 'warn_hi', hi: has.has('error_hi') ? 'error_hi' : null, tone: 'warn' }),
    error_hi: () => ({ lo: 'error_hi', hi: null, tone: 'bad' }),
    warn_lo: (has) => ({ lo: has.has('error_lo') ? 'error_lo' : null, hi: 'warn_lo', tone: 'warn' }),
    error_lo: () => ({ lo: null, hi: 'error_lo', tone: 'bad' }),
  };
  for (const b of live) {
    const seen = new Map();
    for (const [s, g] of groups) {
      const has = present.get(s);
      if (!has.has(b)) continue;
      const z = zoneOf[b](has);
      const pairs = [];
      for (const [xv, r] of g) {
        const lo = z.lo === null ? null : valueOf(r, z.lo), hi = z.hi === null ? null : valueOf(r, z.hi);
        if ((z.lo !== null && lo === null) || (z.hi !== null && hi === null)) continue;
        pairs.push([xv, [lo, hi]]);
      }
      if (!pairs.length) continue;
      const { points } = shape(pairs, (a, c) => a[0] === c[0] && a[1] === c[1]);
      const lo = points.map((p) => [p[0], p[1][0]]), hi = points.map((p) => [p[0], p[1][1]]);
      const key = JSON.stringify([lo, hi]);
      if (seen.has(key)) { seen.get(key).shared.push(s); continue; }
      const zone = { guide: `zone:${b}`, bound: b, series: s, shared: [s], tone: z.tone, lo, hi };
      seen.set(key, zone);
      out.zones.push(zone);
    }
  }
  return out;
}
