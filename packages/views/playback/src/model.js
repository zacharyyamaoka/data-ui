/* The playback variants' arithmetic (docs/peps/0005-dashboard-cards.md §4b): what the proposals read out of the
   dashboard's datasets (event times, streams, chapters, sparklines) and the text they print. Pure: no DOM, no clock,
   no imports, so tests/unit/playback.test.mjs runs it as it is. */

const num = (v) => typeof v === 'number' && Number.isFinite(v);
const VIDEO = /\.(mp4|webm|m4v|mov|ogv)(\?|#|$)/i;

/** A cell's plain value: the kit's cells may be {value, …} objects (data.js); this module stays free of core. */
export function plain(v) {
  return v && typeof v === 'object' && !Array.isArray(v) && 'value' in v ? v.value : v;
}

/** About n "nice" tick values over [a, b] (1, 2, 5 × 10^k steps). */
export function niceTicks(a, b, n = 8) {
  if (!(b > a)) return [a];
  const raw = (b - a) / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(a / step - 1e-9) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

/** The step between nice ticks over [a, b] for about n ticks (the ruler's minor ticks divide it by 5). */
export function niceStep(a, b, n = 8) {
  const t = niceTicks(a, b, n);
  return t.length > 1 ? +(t[1] - t[0]).toFixed(10) : 1;
}

/** Is this row a video clip (a src that names a video file)? */
export function isClip(row) {
  const src = plain(row && row.src);
  return typeof src === 'string' && VIDEO.test(src);
}

/** The distinct sample times of every time-aware dataset ({name: {rows}}), sorted: Rerun's "events". A dataset is
    time-aware when its rows carry a number in the clock's time column. */
export function eventTimes(datasets, timeCol = 't') {
  const set = new Set();
  for (const d of Object.values(datasets || {})) {
    for (const r of (d && d.rows) || []) { const v = plain(r[timeCol]); if (num(v)) set.add(v); }
  }
  return [...set].sort((a, b) => a - b);
}

/** The first event after t (eps: what counts as "at t"), else null. events sorted ascending. */
export function nextEvent(events, t, eps = 1e-9) {
  let lo = 0, hi = events.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (events[m] > t + eps) hi = m; else lo = m + 1; }
  return lo < events.length ? events[lo] : null;
}

/** The last event before t, else null. */
export function prevEvent(events, t, eps = 1e-9) {
  let lo = 0, hi = events.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (events[m] < t - eps) lo = m + 1; else hi = m; }
  return lo > 0 ? events[lo - 1] : null;
}

/** Rerun's STREAMS: one node per time-aware dataset, children per numeric column (its channels); a dataset of video
    clips gets one child per clip spanning [t0, t0 + duration]. Each node: {name, kind, t0, t1, times}.
    `label` names a clip (default: its situation, else its id). */
export function streamsOf(datasets, timeCol = 't') {
  const out = [];
  for (const [name, d] of Object.entries(datasets || {})) {
    const rows = (d && d.rows) || [];
    if (rows.length && rows.every(isClip)) {
      const kids = [];
      for (const r of rows) {
        const t0 = num(plain(r.t0)) ? plain(r.t0) : 0, dur = plain(r.duration);
        if (!num(dur)) continue;
        kids.push({ name: String(plain(r.situation) ?? plain(r.label) ?? r.id ?? kids.length), kind: 'clip', t0, t1: t0 + dur, times: [t0, t0 + dur] });
      }
      if (kids.length) out.push({ name, kind: 'video', t0: Math.min(...kids.map((k) => k.t0)), t1: Math.max(...kids.map((k) => k.t1)), times: [...new Set(kids.flatMap((k) => k.times))].sort((a, b) => a - b), children: kids });
      continue;
    }
    const times = new Set(), cols = new Map();
    for (const r of rows) {
      const t = plain(r[timeCol]);
      if (!num(t)) continue;
      times.add(t);
      for (const k of Object.keys(r)) {
        if (k === timeCol || k === 'id' || k.startsWith('_')) continue;
        if (!num(plain(r[k]))) continue;
        let c = cols.get(k);
        if (!c) cols.set(k, (c = new Set()));
        c.add(t);
      }
    }
    if (!times.size) continue;
    const sorted = (s) => [...s].sort((a, b) => a - b);
    const all = sorted(times);
    out.push({ name, kind: 'table', t0: all[0], t1: all[all.length - 1], times: all,
      children: [...cols].map(([k, s]) => { const ts = sorted(s); return { name: k, kind: 'column', t0: ts[0], t1: ts[ts.length - 1], times: ts }; }) });
  }
  return out;
}

/** Event ticks to draw at a pixel width: the distinct pixel columns of `times` over [a, b], or null when they are so
    dense (more than one per `gap` px on average) that the bar reads as solid (Rerun merges them the same way). */
export function tickColumns(times, a, b, width, gap = 3) {
  if (!(b > a) || !(width > 0)) return [];
  const cols = new Set();
  for (const t of times) cols.add(Math.round(((t - a) / (b - a)) * width));
  return cols.size > width / gap ? null : [...cols].sort((x, y) => x - y);
}

/** At most ~2n points of [[t, v], …] (sorted by t): the min and the max of each of n buckets, in t order, so a
    sparkline keeps its spikes. */
export function decimate(points, n = 200) {
  if (points.length <= 2 * n) return points;
  const a = points[0][0], b = points[points.length - 1][0], w = (b - a) / n || 1;
  const out = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    const end = i === n - 1 ? Infinity : a + (i + 1) * w;
    let lo = null, hi = null;
    for (; k < points.length && points[k][0] < end; k++) {
      const p = points[k];
      if (!lo || p[1] < lo[1]) lo = p;
      if (!hi || p[1] > hi[1]) hi = p;
    }
    if (lo) { if (lo === hi) out.push(lo); else out.push(...(lo[0] <= hi[0] ? [lo, hi] : [hi, lo])); }
  }
  return out;
}

/** An SVG path of [[t, v], …] in a 1000 × 100 box over x [a, b] and y [lo, hi] (y up); a null value breaks it. */
export function sparkPath(points, a, b, lo, hi) {
  const sx = (t) => (((t - a) / ((b - a) || 1)) * 1000).toFixed(1);
  const sy = (v) => (100 - ((v - lo) / ((hi - lo) || 1)) * 100).toFixed(1);
  let d = '', pen = false;
  for (const [t, v] of points) {
    if (!num(v)) { pen = false; continue; }
    d += `${pen ? 'L' : 'M'}${sx(t)} ${sy(v)}`;
    pen = true;
  }
  return d;
}

/** Chapters from a held-then-moved signal (a step target): a chapter starts at span start and at each moment the
    value starts moving after holding still for at least `hold` seconds. [{t0, t1, title}] over [a, b].
    eps: the change between samples that counts as still. */
export function chaptersOf(points, a, b, { eps = 1e-6, hold = 0.2, title = (i) => `Move ${i + 1}` } = {}) {
  const starts = [a];
  let still = null;   // when the current still stretch began
  for (let i = 1; i < points.length; i++) {
    const [t0, v0] = points[i - 1], [t1, v1] = points[i];
    if (!num(v0) || !num(v1)) { still = null; continue; }
    if (Math.abs(v1 - v0) <= eps) { if (still === null) still = t0; continue; }
    if (still !== null && t0 - still >= hold && t0 > starts[starts.length - 1] + 1e-9) starts.push(t0);
    still = null;
  }
  return starts.filter((t) => t < b).map((t, i, s) => ({ t0: t, t1: i + 1 < s.length ? s[i + 1] : b, title: title(i) }));
}

/** The chapter that holds t, else null. */
export function chapterAt(chapters, t) {
  return (chapters || []).find((c) => t >= c.t0 && t < c.t1) || (chapters && chapters.length && t >= chapters[chapters.length - 1].t1 - 1e-9 ? chapters[chapters.length - 1] : null);
}

// ---------------------------------------------------------------- the text each proposal prints

/** Rerun's time field: "+3.20s" (seconds since the timeline's zero). */
export const rerunTime = (t) => (num(t) ? `${t < 0 ? '−' : '+'}${Math.abs(t).toFixed(2)}s` : '—');
/** Rerun's speed field: "1.00x". */
export const rerunSpeed = (r) => `${Number(r).toFixed(2)}x`;

/** A typed time ("+3.2s", "3.2", "-1", "1:02.5") → seconds, else null. */
export function parseTime(text) {
  const s = String(text ?? '').trim().replace(/^\+/, '').replace(/−/g, '-').replace(/\s*s(ec)?$/i, '');
  const m = /^(-?)(\d+):(\d+(?:\.\d+)?)$/.exec(s);
  if (m) return (m[1] ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
  if (!/^-?(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  return Number(s);
}

/** A typed speed ("1.5x", "2×", "0.25") → a rate > 0, else null. */
export function parseSpeed(text) {
  const s = String(text ?? '').trim().replace(/\s*[x×]$/i, '');
  if (!/^(\d+\.?\d*|\.\d+)$/.test(s)) return null;
  const r = Number(s);
  return r > 0 ? r : null;
}

/** YouTube's clock: "0:03", "1:02", "1:02:03". */
export function ytTime(t) {
  if (!num(t)) return '—';
  const a = Math.max(0, Math.floor(t + 1e-9)), h = Math.floor(a / 3600), m = Math.floor((a % 3600) / 60), s = a % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

/** An editor's timecode: "00:00:03:06" (hours, minutes, seconds, frames at fps). */
export function timecode(t, fps = 30) {
  if (!num(t)) return '—';
  const f = Math.max(0, Math.round(t * fps)), F = Math.round(fps);
  const fr = f % F, s = Math.floor(f / F) % 60, m = Math.floor(f / F / 60) % 60, h = Math.floor(f / F / 3600);
  return [h, m, s, fr].map((x) => String(x).padStart(2, '0')).join(':');
}

/** Foxglove's time display: seconds ("3.200") or elapsed since the start ("00:03.200"). */
export function foxTime(t, start = 0, format = 'seconds') {
  if (!num(t)) return '—';
  if (format === 'seconds') return t.toFixed(3);
  const e = Math.max(0, t - (num(start) ? start : 0)), m = Math.floor(e / 60);
  return `${String(m).padStart(2, '0')}:${(e - m * 60).toFixed(3).padStart(6, '0')}`;
}

/** A range readout: "1.20 – 3.40 s (2.20 s)". */
export function spanText(a, b) {
  return num(a) && num(b) ? `${a.toFixed(2)} – ${b.toFixed(2)} s (${(b - a).toFixed(2)} s)` : '—';
}
