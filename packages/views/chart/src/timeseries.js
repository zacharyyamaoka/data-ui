/* type: timeseries — one or more series over t (docs/peps/0005-dashboard-cards.md §2b, docs/CONTRACT.md §25).

     timeseries: {x, y: col | [cols], series, mark: line|area|step, scale: linear|log|symlog, unit, dash: [names],
                  rules: [{y, label, tone}], bands: [{y: [a, b] | x: [a, b], label, tone}],
                  limits: {warn: [lo, hi], error: [lo, hi]},
                  annotations: [{x: <number>, label, tone} | {data, x: <column>, label: <column>, tone}],
                  legend: top|none, height}

   An annotation is a vertical mark at a time: as written (x a number, label its text), or one per row (x names a time
   column, label a text column): of `data`, another dataset of the dashboard handed in as a layer (CONTRACT §32: filtered
   as a panel on it, so a run pick moves its marks), else of the view's own rows (kit gap 2: a driver's mode and fault
   changes, a gripper's contact, grasp and release, read from events.json). Their labels are staggered into up to three
   rows so none overlaps another (labelRows, measured as Vega measures); a label with no room is left off the plot and
   read in the hover readout at its mark (kit gap 7).

   `limits` (docs/CONTRACT.md §35, PEP 0010 §10's threshold_band): RobotDx's warn and error limits, each end a number, a
   property (per series: a device's own) or null; a dashed rule at each limit in its status tone ("! warn", "✕ error") and
   the zones beyond them, an open zone to the plot's edge (core guides.js limitGuides). Their points are the `guides`
   dataset's `limit:<bound>` and `zone:<bound>` rows (an edge is null there), and they set the y domain: the drawn values
   and every limit, padded, so a limit is always on the plot and an open zone ends at the edge.

   A rule's y, or a band's y bounds, may name a property instead of giving a number (sim2real gap #6; core
   guides.js): read from the drawn rows per series, a constant (a device's own limit, which follows the rail's pick)
   is drawn across the data's x and a value that changes is a step line through it. Those points are the Vega dataset
   `guides` ({guide: 'rule:<i>' | 'band:<i>', series, x, value | lo, hi}).

   The legend is the core's (SeriesLegend, src/legend.js): a click hides a series, a double-click or Alt + click shows
   only it, Reset shows all; a hidden series leaves the drawing (its samples are not sent to Vega, so y fits the rest)
   and the crosshair readout, never the rows or the status line.

   The look is Klipfolio's and Tremor's time series: thin 1.5 px lines without points, a faint horizontal grid, no
   axis lines or ticks (style.chrome minimal), muted 11 px labels in compact numbers, the legend on top as dots, and a
   crosshair readout instead of a tooltip. A series named "target" (or listed in dash:) is dashed and muted.

   Time-aware when x is a number of seconds: the card reports its span to the clock, draws the clock's t as a
   playhead, shares the crosshair (clock.hover), takes clock.window as its x domain (a horizontal drag sets it, a
   double-click clears it) and seeks on a click. A date x is a plain time series: no clock, no playhead.

   STOCK PARTS: Vega-Lite (this bundle's one engine). Ours: the long-format compile, min/max decimation past 3,000
   points a series, and the positioned playhead / crosshair over the canvas (overlay.js). */

import embed from 'vega-embed';
import { cellValue, esc, fmtNum, numOpts, clockFor, fmtTime, seriesColor, SeriesLegend, isNum } from '@data-ui/core';
import { theme } from './theme.js';
import { longRows, seriesStyles, windowed, decimate, nearest } from './series.js';
import { plotBox, toneColor, unitOf, COMPACT, GUTTER, TIME_PAD } from './overlay.js';
// WHY the source path, not '@data-ui/core': a pure helper shared with the live bundle, bundled into each (as plotkit.js
// takes legendClick), so this bundle's unit tests keep their small core shim
import { guidesFrom, limitGuides } from '../../../core/src/guides.js';

const DASH = [5, 4];
const EMBED = { actions: false, renderer: 'canvas', tooltip: false, mode: 'vega-lite', logLevel: 1 };
const LABEL_SIZE = 10;     // px: an annotation's label
const LABEL_ROW = 13;      // px between label rows (a 10 px label's box is about 12 px tall)
const LABEL_ROWS = 3;      // rows a label may take before it is left to the readout
const LABEL_GAP = 6;       // px kept clear between two labels of a row
const LABEL_NEAR = 6;      // px: a mark this close to the pointer is read in the readout
// a cell with nothing in it (format.js's isEmpty, kept here: this file's unit tests bundle it against a small core shim)
const blank = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length);

/** An annotation's rows (kit gap 2, CONTRACT §25 addendum): [{x, label, tone}] in time order. As written (x a number), or
    one per row whose x is a time (and whose label, when named, is not empty): of `data` (input.layers[data], CONTRACT
    §32; the view's own dataset is its own rows), else of the view's own rows. A dataset not handed in draws nothing (a
    plain <data-views>, which both checkers warn of). A date x reads ISO dates. */
export function annotationRows(input) {
  const view = (input && input.view) || {};
  const ts = view.timeseries || {};
  const list = Array.isArray(ts.annotations) ? ts.annotations : [];
  const columns = (input && input.columns) || {};
  const xcol = columns[ts.x || 't'];
  const temporal = !!(xcol && xcol.type === 'date');
  const time = (v) => (temporal ? (blank(v) ? null : Date.parse(v)) : v);
  const out = [];
  list.forEach((a, k) => {
    if (!a || typeof a !== 'object') return;
    const tone = typeof a.tone === 'string' && a.tone ? a.tone : 'muted';
    if (typeof a.x !== 'string') {
      const x = time(a.x);
      if (isNum(x)) out.push({ x, label: a.label === undefined || a.label === null ? '' : String(a.label), tone, k });
      return;
    }
    const own = !a.data || a.data === view.from;
    const src = own ? { rows: input.rows, columns } : input.layers && input.layers[a.data];
    if (!src || !Array.isArray(src.rows)) return;
    const named = typeof a.label === 'string' && a.label ? a.label : null;
    const lcol = named && src.columns ? src.columns[named] : null;
    for (const r of src.rows) {
      const x = time(cellValue(r[a.x]));
      if (!isNum(x)) continue;
      let label = '';
      if (named) {
        const v = cellValue(r[named]);
        if (blank(v)) continue;
        label = lcol && lcol.labels && lcol.labels[v] !== undefined ? String(lcol.labels[v]) : String(v);
      }
      out.push({ x, label, tone, k });
    }
  });
  out.sort((p, q) => p.x - q.x || p.k - q.k);
  return out.map(({ x, label, tone }) => ({ x, label, tone }));
}

/** Where each annotation's label goes (kit gap 7): [{row, x0, x1, align}] beside `marks` ([{x, label}] in time order),
    over a plot `width` px wide showing `domain`. A label starts 4 px right of its mark (or ends 4 px left of it when it
    would run past the plot's right edge) in the first of `rows` rows whose last label ends LABEL_GAP px before it;
    `row` null when no row has room (or it has no text, or its mark is off the plot). `measure(text)` is its width in px.
    Greedy by time: Grafana's annotation markers, staggered as matplotlib's adjustText does for close labels. */
export function labelRows(marks, { domain, width, measure, rows = LABEL_ROWS, gap = LABEL_GAP }) {
  const [d0, d1] = domain;
  const span = d1 - d0 || 1;
  const ends = new Array(rows).fill(-Infinity);
  const order = marks.map((m, i) => i).sort((a, b) => marks[a].x - marks[b].x || a - b);
  const out = new Array(marks.length);
  for (const i of order) {
    const m = marks[i];
    const px = ((m.x - d0) / span) * width;
    const none = { row: null, x0: px, x1: px, align: 'left' };
    if (!m.label || !(px >= 0 && px <= width)) { out[i] = none; continue; }
    const w = measure(m.label);
    let box = { x0: px + 4, x1: px + 4 + w, align: 'left' };
    if (box.x1 > width) box = { x0: px - 4 - w, x1: px - 4, align: 'right' };
    if (box.x0 < 0) { out[i] = none; continue; }
    const r = ends.findIndex((e) => e + gap <= box.x0);
    if (r < 0) { out[i] = none; continue; }
    ends[r] = box.x1;
    out[i] = { row: r, ...box };
  }
  return out;
}

let measurer = null;
/** A label's width as Vega measures it (canvas measureText, the same font string); an estimate where there is no canvas. */
function measureWith(font) {
  if (!measurer && typeof document !== 'undefined') {
    try { measurer = (typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(1, 1) : document.createElement('canvas')).getContext('2d'); } catch { measurer = null; }
  }
  if (!measurer) return (s) => String(s).length * LABEL_SIZE * 0.62;
  return (s) => { measurer.font = `${LABEL_SIZE}px ${font}`; return measurer.measureText(String(s)).width; };
}

/** The view's rows and entry -> {spec (no data), datasets, key, meta}. `win` is the clock's window ([a, b] or null);
    the key does not change with it, so a zoom swaps data and two signals instead of re-embedding. `hidden`: the series
    names the legend hides, left out of the drawn samples only (meta.series keeps every series). Exported for tests. */
export function compileTimeseries(input, { width = 640, height = 220, win = null, hidden = [] } = {}) {
  const { rows, view, columns, tokens } = input;
  const ts = view.timeseries || {};
  const x = ts.x || 't';
  const ys = (Array.isArray(ts.y) ? ts.y : [ts.y]).filter((f) => f && columns[f]);
  const xcol = columns[x];
  const temporal = !!(xcol && xcol.type === 'date');
  const label = (f) => (columns[f] ? columns[f].label : f);
  const read = (row, f) => cellValue(row[f]);
  const time = temporal ? (v) => (v === null || v === undefined || v === '' ? null : Date.parse(v)) : (v) => v;
  const { list } = longRows(rows, { x, y: ys, series: ts.series && columns[ts.series] ? ts.series : null }, { read, label, time });
  const log = ts.scale === 'log';
  if (log) for (const s of list) s.points = s.points.filter((p) => p.value > 0);
  const styles = seriesStyles(list.filter((s) => s.points.length), { palette: view.style && view.style.palette, dash: ts.dash, slot: (n) => seriesColor(n, input), muted: tokens.muted });

  let lo = Infinity, hi = -Infinity;
  for (const s of styles) { lo = Math.min(lo, s.points[0].x); hi = Math.max(hi, s.points[s.points.length - 1].x); }
  if (!(hi >= lo)) { lo = 0; hi = 1; }
  if (hi === lo) hi = lo + 1;
  const domain = !temporal && win ? [win[0], win[1]] : [lo, hi];
  const drawn = [];
  let decimated = false;
  const off = new Set(hidden);
  for (const s of styles) {
    // WHY the samples, not an opacity: y fits the series still shown, so a hidden outlier no longer flattens the rest
    // (Plotly's, Grafana's and uPlot's default); x stays on the whole span (xmin / xmax below), and the colour and
    // dash scales keep every name, so no colour moves
    if (off.has(s.name)) continue;
    const inside = temporal ? s.points : windowed(s.points, domain[0], domain[1]);
    const few = decimate(inside, domain[0], domain[1], width);
    if (few !== inside) decimated = true;
    for (const p of few) drawn.push({ x: p.x, value: p.value, series: s.name });
  }

  // limits (CONTRACT §35): computed here, before the y scale, because they set its domain
  const seriesCol0 = ts.series && columns[ts.series] ? ts.series : null;
  const limits = ts.limits && typeof ts.limits === 'object'
    ? limitGuides(rows, ts.limits, { x, series: seriesCol0, read: (r, c) => (c === x ? time(read(r, c)) : read(r, c)), hidden }) : null;
  const hasLimits = !!limits && (limits.rules.length > 0 || limits.zones.length > 0);
  let yDomain = null;
  if (hasLimits && !log) {
    // WHY an explicit domain: Vega-Lite's area cannot end at the plot's edge in pixels, so an open zone ends at the
    // domain's edge, which is known only when it is set here: the drawn values, every limit and every numeric rule or
    // band, padded by 6 % (nice off, so the edges are where the zones end)
    let a = Infinity, b = -Infinity;
    const take = (v) => { if (typeof v === 'number' && Number.isFinite(v)) { if (v < a) a = v; if (v > b) b = v; } };
    for (const d of drawn) take(d.value);
    for (const g of limits.rules) for (const [, v] of g.points) take(v);
    for (const r of ts.rules || []) if (r) take(r.y);
    for (const bd of ts.bands || []) if (bd && Array.isArray(bd.y)) bd.y.forEach(take);
    if (b >= a) { const pad = (b - a) * 0.06 || Math.abs(a) * 0.06 || 1; yDomain = [a - pad, b + pad]; }
  }

  const names = styles.map((s) => s.name);
  const minimal = !view.style || view.style.chrome !== 'full';
  const font = tokens.font || 'system-ui, sans-serif';
  const axisBase = { title: null, labelColor: tokens.muted, labelFontSize: 11, labelFont: font, domain: !minimal, ticks: !minimal, labelPadding: 6 };
  // WHY a date x gets the whole span as its domain while a series is hidden: x stays put, only y rescales to what is
  // shown (a date x has no window signals, so this one case re-embeds on a legend click)
  const xEnc = {
    field: 'x', type: temporal ? 'temporal' : 'quantitative',
    scale: temporal ? { nice: false, ...(off.size ? { domain: [lo, hi] } : {}) } : { domainMin: { expr: 'xmin' }, domainMax: { expr: 'xmax' }, nice: false, zero: false },
    // WHY labelBound: a label past the plot's end is left off rather than narrowing the plot (a chart on the clock does
    // the same, so the two line up whatever their ticks; kit gap 3)
    axis: { ...axisBase, grid: false, tickCount: Math.max(2, Math.floor(width / 90)), labelFlush: true, labelOverlap: true, labelBound: 0.5,
      ...(temporal ? {} : { labelExpr: "format(datum.value, '~r') + ' s'" }) },
  };
  const yEnc = {
    field: 'value', type: 'quantitative',
    scale: { type: log ? 'log' : ts.scale === 'symlog' ? 'symlog' : 'linear', zero: false, ...(yDomain ? { domain: yDomain, nice: false } : { nice: true }) },
    // WHY minExtent: GUTTER px for the y labels at least, as a chart over the same time keeps (kit gap 3)
    axis: { ...axisBase, grid: true, gridColor: tokens.rule, tickCount: Math.max(2, Math.floor(height / 48)), labelExpr: COMPACT, minExtent: GUTTER },
  };
  const color = { field: 'series', type: 'nominal', scale: { domain: names, range: styles.map((s) => s.color) }, legend: null };
  const strokeDash = { field: 'series', type: 'nominal', scale: { domain: names, range: styles.map((s) => (s.dashed ? DASH : [])) }, legend: null };
  const interpolate = ts.mark === 'step' ? 'step-after' : 'linear';

  const one = { values: [{}] };
  const back = [], front = [];
  for (const b of ts.bands || []) {
    const fill = toneColor(b.tone || 'muted', tokens);
    if (Array.isArray(b.y)) {
      back.push({ data: one, mark: { type: 'rect', fill, fillOpacity: 0.09, clip: true }, encoding: { y: { datum: b.y[0], type: 'quantitative' }, y2: { datum: b.y[1] }, x: { value: 0 }, x2: { value: 'width' } } });
      if (b.label) back.push({ data: one, mark: { type: 'text', fill, fontSize: 10, font, align: 'left', baseline: 'top', dx: 4, dy: 3, clip: true }, encoding: { y: { datum: Math.max(b.y[0], b.y[1]), type: 'quantitative' }, x: { value: 0 }, text: { value: b.label } } });
    } else if (Array.isArray(b.x)) {
      back.push({ data: one, mark: { type: 'rect', fill, fillOpacity: 0.09, clip: true }, encoding: { x: { datum: b.x[0], type: xEnc.type }, x2: { datum: b.x[1] }, y: { value: 0 }, y2: { value: 'height' } } });
      if (b.label) back.push({ data: one, mark: { type: 'text', fill, fontSize: 10, font, align: 'left', baseline: 'top', dx: 4, dy: 3, clip: true }, encoding: { x: { datum: Math.min(b.x[0], b.x[1]), type: xEnc.type }, y: { value: 0 }, text: { value: b.label } } });
    }
  }
  for (const r of ts.rules || []) {
    if (typeof r.y !== 'number') continue;   // a property's rule is a guide line (below)
    const stroke = toneColor(r.tone || 'muted', tokens);
    back.push({ data: one, mark: { type: 'rule', stroke, strokeDash: [3, 3], strokeWidth: 1, opacity: 0.85, clip: true }, encoding: { y: { datum: r.y, type: 'quantitative' } } });
    if (r.label) front.push({ data: one, mark: { type: 'text', fill: stroke, fontSize: 10, font, align: 'right', baseline: 'bottom', dx: -2, dy: -3, clip: true }, encoding: { y: { datum: r.y, type: 'quantitative' }, x: { value: 'width' }, text: { value: r.label } } });
  }
  // rules and bands from a property: step lines (a constant is two points across the data's x) on the shared scales
  const seriesCol = ts.series && columns[ts.series] ? ts.series : null;
  const prop = guidesFrom(rows, { rules: ts.rules, bands: ts.bands }, { x, series: seriesCol, read: (r, c) => (c === x ? time(read(r, c)) : read(r, c)), hidden });
  const guideRows = [];
  for (const g of prop.rules) for (const [gx, v] of g.points) guideRows.push({ guide: g.guide, series: g.series, x: gx, value: v });
  for (const g of prop.bands) g.lo.forEach(([gx, lo], k) => guideRows.push({ guide: g.guide, series: g.series, x: gx, lo, hi: g.hi[k][1] }));
  const isProp = (v) => typeof v === 'string' && v !== '';
  const only = (name) => [{ filter: `datum.guide === '${name}'` }];
  (Array.isArray(ts.bands) ? ts.bands : []).forEach((b, i) => {
    if (!b || !Array.isArray(b.y) || !b.y.some(isProp)) return;
    const fill = toneColor(b.tone || 'muted', tokens);
    back.push({ data: { name: 'guides' }, transform: only(`band:${i}`), mark: { type: 'area', interpolate: 'step-after', fill, fillOpacity: 0.09, clip: true },
      encoding: { x: xEnc, y: { ...yEnc, field: 'lo' }, y2: { field: 'hi' }, detail: { field: 'series', type: 'nominal' } } });
  });
  (Array.isArray(ts.rules) ? ts.rules : []).forEach((r, i) => {
    if (!r || !isProp(r.y)) return;
    const stroke = toneColor(r.tone || 'muted', tokens);
    back.push({ data: { name: 'guides' }, transform: only(`rule:${i}`), mark: { type: 'line', interpolate: 'step-after', stroke, strokeDash: [3, 3], strokeWidth: 1, opacity: 0.85, clip: true },
      encoding: { x: xEnc, y: yEnc, detail: { field: 'series', type: 'nominal' } } });
    // the label at each line's last point (a constant's: the data's right end)
    if (r.label) front.push({ data: { name: 'guides' }, transform: [...only(`rule:${i}`), { window: [{ op: 'row_number', as: 'dv_n' }], groupby: ['series'], sort: [{ field: 'x', order: 'descending' }] }, { filter: 'datum.dv_n === 1' }],
      mark: { type: 'text', fill: stroke, fontSize: 10, font, align: 'right', baseline: 'bottom', dx: -2, dy: -3, clip: true }, encoding: { x: xEnc, y: yEnc, text: { value: r.label } } });
  });
  // limits (CONTRACT §35): the zones behind, then a dashed rule per limit in its status tone with its glyph and word at
  // the line's end; one layer per limit and per zone, so each is its own mark (an edge drawn at the domain's)
  if (hasLimits) {
    const tone = (t) => (tokens.tone && tokens.tone[t]) || toneColor(t, tokens);
    // WHY one set of rows per series even when series share a line: a limit is each device's own, and the data says so
    // (identical lines draw on top of each other, so the picture is the same)
    for (const g of limits.rules) for (const s of g.shared) for (const [gx, v] of g.points) guideRows.push({ guide: g.guide, series: s, x: gx, value: v });
    for (const g of limits.zones) g.lo.forEach(([gx, lv], k) => guideRows.push({ guide: g.guide, series: g.series, x: gx, lo: lv, hi: g.hi[k][1] }));
    const zoneNames = [...new Map(limits.zones.map((z) => [z.guide, z.tone])).entries()];
    for (const [name, zt] of zoneNames) {
      const open = limits.zones.some((z) => z.guide === name && [...z.lo, ...z.hi].some((q) => q[1] === null));
      if (open && !yDomain) continue;   // a log scale has no edge to end an open zone at
      const edge = yDomain || [0, 0];
      back.push({ data: { name: 'guides' }, transform: [...only(name), { calculate: `datum.lo === null ? ${edge[0]} : datum.lo`, as: 'dv_lo' }, { calculate: `datum.hi === null ? ${edge[1]} : datum.hi`, as: 'dv_hi' }],
        mark: { type: 'area', interpolate: 'step-after', fill: tone(zt), fillOpacity: zt === 'bad' ? 0.11 : 0.09, clip: true },
        encoding: { x: xEnc, y: { ...yEnc, field: 'dv_lo' }, y2: { field: 'dv_hi' }, detail: { field: 'series', type: 'nominal' } } });
    }
    const ruleNames = [...new Map(limits.rules.map((r) => [r.guide, r])).values()];
    for (const r of ruleNames) {
      const stroke = tone(r.tone);
      back.push({ data: { name: 'guides' }, transform: only(r.guide), mark: { type: 'line', interpolate: 'step-after', stroke, strokeDash: [4, 3], strokeWidth: 1.2, opacity: 0.95, clip: true },
        encoding: { x: xEnc, y: yEnc, detail: { field: 'series', type: 'nominal' } } });
      front.push({ data: { name: 'guides' }, transform: [...only(r.guide), { window: [{ op: 'row_number', as: 'dv_n' }], groupby: ['series'], sort: [{ field: 'x', order: 'descending' }] }, { filter: 'datum.dv_n === 1' }],
        mark: { type: 'text', fill: stroke, fontSize: 10, font, align: 'right', baseline: r.guide.endsWith('_lo') ? 'top' : 'bottom', dx: -2, dy: r.guide.endsWith('_lo') ? 3 : -3, clip: true }, encoding: { x: xEnc, y: yEnc, text: { value: r.label } } });
    }
  }
  // annotations (kit gaps 2, 7): one rule layer and two label layers (left and right of their marks) over the dataset
  // `marks`, whichever kind wrote them; the layers stand whenever the view has annotations, so a pick swaps data only
  const marks = [];
  if (Array.isArray(ts.annotations) && ts.annotations.length) {
    const rows = annotationRows(input);
    // WHY the plot's width estimated narrow (the y labels at GUTTER + 16 px): a label placed on a narrower plot only
    // has more room on the real one, so the stagger never lets two overlap
    const plotW = Math.max(40, width - TIME_PAD.left - TIME_PAD.right - GUTTER - 16);
    const where = labelRows(rows, { domain: temporal ? [lo, hi] : domain, width: plotW, measure: measureWith(font) });
    rows.forEach((m, i) => {
      const w = where[i];
      marks.push({ x: m.x, label: m.label, tone: m.tone, color: toneColor(m.tone, tokens), row: w.row, align: w.align, ly: w.row === null ? null : 2 + w.row * LABEL_ROW });
    });
    const shown = (align) => [{ filter: `datum.row !== null && datum.align === '${align}'` }];
    back.push({ data: { name: 'marks' }, mark: { type: 'rule', strokeWidth: 1, opacity: 0.6, clip: true },
      encoding: { x: xEnc, color: { field: 'color', type: 'nominal', scale: null, legend: null } } });
    for (const align of ['left', 'right']) {
      front.push({ data: { name: 'marks' }, transform: shown(align), mark: { type: 'text', fontSize: LABEL_SIZE, font, align, baseline: 'top', dx: align === 'left' ? 4 : -4, clip: true },
        encoding: { x: xEnc, y: { field: 'ly', type: 'quantitative', scale: null }, text: { field: 'label' }, color: { field: 'color', type: 'nominal', scale: null, legend: null } } });
    }
  }
  const series = [];
  if (ts.mark === 'area') {
    series.push({ data: { name: 'series' }, mark: { type: 'area', interpolate, fillOpacity: 0.1, clip: true }, encoding: { x: xEnc, y: { ...yEnc, stack: null }, color: { ...color } } });
  }
  series.push({ data: { name: 'series' }, name: 'series', mark: { type: 'line', interpolate, strokeWidth: 1.5, strokeJoin: 'round', strokeCap: 'round', clip: true }, encoding: { x: xEnc, y: yEnc, color, strokeDash } });
  // drawn in order: bands and rules behind the lines, labels in front; every layer shares the x and y scales
  const layer = [...back, ...series, ...front];

  const datasets = { series: drawn };
  if (guideRows.length || back.some((l) => l.data && l.data.name === 'guides')) datasets.guides = guideRows;
  if (back.some((l) => l.data && l.data.name === 'marks')) datasets.marks = marks;
  const spec = {
    width, height, autosize: { type: 'fit', contains: 'padding' },
    padding: { ...TIME_PAD },
    ...(temporal ? {} : { params: [{ name: 'xmin', value: domain[0] }, { name: 'xmax', value: domain[1] }] }),
    layer,
    config: theme(tokens, { narrow: width < 560, chrome: minimal ? 'minimal' : 'full', grid: 'y' }),
  };
  const key = JSON.stringify({ ...spec, width: undefined, height: undefined, params: temporal ? undefined : 'x' });
  const ycol = columns[ys[0]];
  return {
    spec, key, datasets,
    meta: {
      temporal, extent: [lo, hi], domain, series: styles, drawn: drawn.length, decimated, ys, marks,
      unit: ts.unit !== undefined ? ts.unit : ys.length === 1 ? unitOf(ycol) : '',
      aria: `time series of ${ys.map(label).join(', ')}: ${styles.length} series, ${drawn.length} samples drawn`,
    },
  };
}

export class TimeseriesView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._key = null;
    this._job = Promise.resolve();
    el.innerHTML = `<div class="dv-timeseries-head"><div class="dv-timeseries-legend" role="group" aria-label="Series"></div><span class="dv-timeseries-zoom" hidden>zoomed · double-click to reset</span><span class="dv-timeseries-unit"></span></div>
      <div class="dv-timeseries-plot" role="img">
        <div class="dv-timeseries-canvas"></div>
        <div class="dv-timeseries-brush" hidden></div>
        <div class="dv-timeseries-hover" data-hover hidden><div class="dv-timeseries-read"></div></div>
        <div class="dv-timeseries-playhead" data-playhead hidden></div>
      </div>`;
    this.$ = (sel) => el.querySelector(sel);
    this.plot = this.$('.dv-timeseries-plot');
    this.legend = new SeriesLegend(this.$('.dv-timeseries-legend'), { host, keyClass: 'dv-timeseries-key', onChange: () => this._queue() });
    this.clock = clockFor(host.element || el);
    this._onTime = () => this._place();
    this._onHover = () => this._crosshair();
    this._onState = () => {
      const w = this.clock.window;
      if (this._meta && !this._meta.temporal && JSON.stringify(w) !== JSON.stringify(this._win)) this._queue();
    };
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('hover', this._onHover);
    this.clock.addEventListener('state', this._onState);
    this._pointer();
    this._resize = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => { if (this.input) this._queue(); }, 80);
    });
    this._resize.observe(this.plot);
  }

  destroy() {
    this._dead = true;
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('hover', this._onHover);
    this.clock.removeEventListener('state', this._onState);
    this._resize.disconnect();
    clearTimeout(this._resizeTimer);
    this.legend.destroy();
    if (this.result) this.result.finalize();
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    this.legend.sync(input);
    return this._queue();
  }

  // the chart view's queue: draw in order, only the newest input
  _queue() {
    if (this._waiting) return this._waiting;
    this._job = this._waiting = this._job.then(() => { this._waiting = null; return this._dead ? undefined : this._draw(); }).catch((err) => this._fail(err));
    return this._job;
  }

  async _draw() {
    const input = this.input;
    const ts = input.view.timeseries || {};
    this.plot.style.height = ts.height ? `${ts.height}px` : '';
    this.$('.dv-timeseries-head').hidden = false;
    const width = Math.max(200, Math.floor(this.plot.clientWidth || this.el.clientWidth || 640));
    const height = Math.max(100, Math.floor(this.plot.clientHeight || 220));
    const win = this.clock.window;
    const out = compileTimeseries(input, { width, height, win, hidden: this.legend.hidden });
    this._meta = out.meta;
    this._win = out.meta.temporal ? null : win;
    this._head(out.meta, ts);
    if (!out.meta.temporal) this.clock.extent(out.meta.extent[0], out.meta.extent[1]);
    if (out.key === this._key && this.result) {
      const view = this.result.view;
      for (const [name, values] of Object.entries(out.datasets)) view.data(name, values);
      if (!out.meta.temporal) view.signal('xmin', out.meta.domain[0]).signal('xmax', out.meta.domain[1]);
      view.width(width).height(height).resize();
      await view.runAsync();
      if (this._dead) return;
    } else {
      if (this.result) this.result.finalize();
      this.result = null;
      const result = await embed(this.$('.dv-timeseries-canvas'), { ...out.spec, datasets: out.datasets }, EMBED);
      if (this._dead) { result.finalize(); return; }
      this.result = result;
      this._key = out.key;
    }
    this.el.vegaView = this.result.view;
    this._box = plotBox(this.result.view, this.plot);
    this.el.dataset.drawn = String(out.meta.drawn);
    this.plot.setAttribute('aria-label', out.meta.aria);
    const n = out.meta.series.length;
    this.host.setStatus(`<span class="dv-chart-status">${n} series${out.meta.decimated ? ' · min/max per pixel' : ''}</span>`);
    this._place();
    this._crosshair();
  }

  _fail(err) {
    if (this._dead) return;
    this._key = null;
    this.$('.dv-timeseries-canvas').innerHTML = `<p class="dv-err dv-chart-err">This time series could not be drawn: ${esc(err && err.message ? err.message : err)}</p>`;
    this.host.setStatus('');
  }

  /** The legend (dots, a dash for a dashed series; buttons, src/legend.js) and the unit, as HTML over the plot. */
  _head(meta, ts) {
    const legend = ts.legend !== 'none' && meta.series.length > 0;
    this.legend.draw(legend ? meta.series.map((s) => ({ name: s.name, swatch: `<i class="${s.dashed ? 'dv-timeseries-dash' : ''}" style="--dv-ts-c:${esc(s.color)}"></i>` })) : []);
    this.$('.dv-timeseries-unit').textContent = meta.unit || '';
    this.$('.dv-timeseries-zoom').hidden = !this._win;
    this.$('.dv-timeseries-head').hidden = !legend && !meta.unit && !this._win;
  }

  /** The playhead at the clock's t: a transform on one element, through the scale Vega already computed. */
  _place() {
    const ph = this.$('[data-playhead]');
    const b = this._box;
    if (!b || !this._meta || this._meta.temporal) { ph.hidden = true; return; }
    const t = this.clock.t;
    const [a, z] = b.sx.domain();
    if (!(t >= a && t <= z)) { ph.hidden = true; return; }
    ph.hidden = false;
    ph.style.height = `${b.h}px`;
    ph.style.transform = `translate(${b.x + b.sx(t) - 0.5}px, ${b.y}px)`;
  }

  /** The shared crosshair: a rule at clock.hover and each series' nearest sample there. */
  _crosshair() {
    const rule = this.$('[data-hover]');
    const b = this._box, m = this._meta;
    const t = this.clock.hover;
    if (!b || !m || m.temporal || t === null) { rule.hidden = true; return; }
    const [a, z] = b.sx.domain();
    if (!(t >= a && t <= z)) { rule.hidden = true; return; }
    const { columns, view } = this.input;
    const style = view.style || {};
    const lines = m.series.map((s) => {
      if (!this.legend.shows(s.name)) return '';
      const p = nearest(s.points, t);
      const col = columns[s.column] || {};
      const v = p ? p.value : null;
      const text = v === null ? '—' : fmtNum(v, col.decimals, numOpts(style.numbers, col));
      return `<div class="dv-timeseries-line" data-series="${esc(s.name)}"><i style="--dv-ts-c:${esc(s.color)}"></i><span>${esc(s.name)}</span><b${v === null ? ' title="no sample at this t"' : ` title="${esc(String(v))}"`}>${esc(text)}</b></div>`;
    }).join('');
    // the annotations at the pointer (kit gap 7): every mark within LABEL_NEAR px, so a label with no room on the plot is
    // one hover away, never lost
    const px = b.sx(t);
    const near = (m.marks || []).filter((k) => k.label && Math.abs(b.sx(k.x) - px) <= LABEL_NEAR);
    const marks = near.map((k) => `<div class="dv-timeseries-mark"><i style="--dv-ts-c:${esc(k.color)}"></i><span>${esc(k.label)}</span><b>${esc(fmtTime(k.x))}</b></div>`).join('');
    const read = this.$('.dv-timeseries-read');
    read.innerHTML = `<div class="dv-timeseries-t">${esc(fmtTime(t))}${m.unit ? ` · ${esc(m.unit)}` : ''}</div>${lines}${marks}`;
    rule.hidden = false;
    const x = b.x + b.sx(t);
    rule.style.height = `${b.h}px`;
    rule.style.transform = `translate(${x - 0.5}px, ${b.y}px)`;
    // the readout sits right of the rule, or left of it near the right edge
    read.classList.toggle('dv-timeseries-left', x + 12 + read.offsetWidth > this.plot.clientWidth);
  }

  /** Pointer: hover sets clock.hover; a horizontal drag sets clock.window; a click seeks; a double-click un-zooms. */
  _pointer() {
    const brush = this.$('.dv-timeseries-brush');
    let start = null;
    const at = (e) => {
      const b = this._box;
      if (!b || !this._meta || this._meta.temporal) return null;
      const r = this.plot.getBoundingClientRect();
      const px = e.clientX - r.left - b.x;
      return { px: Math.min(b.w, Math.max(0, px)), inside: px >= 0 && px <= b.w && e.clientY - r.top >= b.y && e.clientY - r.top <= b.y + b.h, b };
    };
    this.plot.addEventListener('pointermove', (e) => {
      const p = at(e);
      if (!p) return;
      this.clock.setHover(p.inside || start ? p.b.sx.invert(p.px) : null);
      if (start) {
        const lo = Math.min(start.px, p.px), hi = Math.max(start.px, p.px);
        brush.hidden = hi - lo < 4;
        brush.style.transform = `translate(${p.b.x + lo}px, ${p.b.y}px)`;
        brush.style.width = `${hi - lo}px`;
        brush.style.height = `${p.b.h}px`;
      }
    });
    this.plot.addEventListener('pointerleave', () => { if (!start) this.clock.setHover(null); });
    this.plot.addEventListener('pointerdown', (e) => {
      const p = at(e);
      if (!p || !p.inside || e.button !== 0) return;
      start = p;
      this.plot.setPointerCapture(e.pointerId);
    });
    const end = (e) => {
      if (!start) return;
      const p = at(e);
      const s = start;
      start = null;
      brush.hidden = true;
      if (!p) return;
      if (Math.abs(p.px - s.px) >= 4) {
        const a = p.b.sx.invert(Math.min(s.px, p.px)), z = p.b.sx.invert(Math.max(s.px, p.px));
        this.clock.setWindow([a, z]);
      } else this.clock.seek(p.b.sx.invert(p.px));
      if (!p.inside) this.clock.setHover(null);
    };
    this.plot.addEventListener('pointerup', end);
    this.plot.addEventListener('pointercancel', () => { start = null; brush.hidden = true; });
    this.plot.addEventListener('dblclick', () => { if (this._meta && !this._meta.temporal) this.clock.setWindow(null); });
  }
}

// The interactive plot (timeseries.interactive: true, src/plot.js) is uPlot, loaded the first time a card asks for it,
// once per page (its few layout rules are in chart.css, so the chunk is JavaScript only)
let plotModule = null;
function loadPlot() {
  plotModule = plotModule || import('./plot.js').catch((err) => { plotModule = null; throw err; });
  return plotModule;
}

/** type: timeseries as the registry constructs it: the simple Vega card, or the interactive uPlot card when the entry
    says interactive: true (decided on each update, so a setView can switch it). */
export class TimeseriesCard {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.impl = null;
    this.kind = null;
    this._job = Promise.resolve();
  }

  update(input) {
    this.input = input;
    this._job = this._job.then(() => this._apply()).catch((err) => {
      if (this._dead) return;
      this.el.innerHTML = `<p class="dv-err dv-chart-err">This time series could not be drawn: ${esc(err && err.message ? err.message : err)}</p>`;
      this.impl = null;
      this.kind = null;
    });
    return this._job;
  }

  async _apply() {
    if (this._dead) return undefined;
    const input = this.input;
    const kind = input.view.timeseries && input.view.timeseries.interactive ? 'plot' : 'vega';
    if (kind !== this.kind) {
      if (this.impl) this.impl.destroy();
      this.impl = null;
      const View = kind === 'plot' ? (await loadPlot()).PlotView : TimeseriesView;
      if (this._dead) return undefined;
      this.impl = new View(this.host, this.el);
      this.kind = kind;
    }
    return this.impl.update(this.input);
  }

  destroy() {
    this._dead = true;
    if (this.impl) this.impl.destroy();
    this.impl = null;
  }
}
