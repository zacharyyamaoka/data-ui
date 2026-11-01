/* type: chart — the view's `chart:` block IS a Vega-Lite spec minus data (docs/SPEC.md §8, docs/CONTRACT.md §5).

   data-ui adds what a file cannot say: the view's filtered rows, each channel's type and title from the field schema,
   the theme from the page's resolved tokens, Show Me defaults for what the view leaves out (§8.5), and the `guides:`
   Vega-Lite cannot say in one line (rules, Ashby envelopes, index lines), each compiled to an ordinary layer (§8.8).
   Around the plot: the Encode menu (writes `chart:` back through host.setView), the hover card (the row's photo,
   title and values with their basis), click to open the record, and Rows: the same rows as the table, one click.

   STOCK PARTS: vega 6.4.0 + vega-lite 6.5.0 + vega-embed 7.3.0 (BSD-3-Clause), in this bundle only, so a page pays
   for them when a chart first shows. The table under the chart is the table view itself (loadView('table')).
   Grown from the views lane's demo (docs/views/demo/views/chart.mjs: tokens -> config, envelopes, index line).
   Writes back only through the host: setView({chart | hover}), open(id), setStatus(the drawn count),
   setHiddenSeries(the legend's hidden set).

   The colour legend is the core's HTML button legend (SeriesLegend, src/legend.js), not Vega's: a click hides a series,
   a double-click or Alt + click shows only it, Reset shows all, Tab / Enter / Space work, and the hidden set is in the
   URL. WHY not Vega-Lite's legend-bound selection (params: [{select: {type: point, fields: [colour]}, bind: legend}]),
   the stock path: Vega draws its legend on the canvas, so its entries are not buttons, take no focus and carry no
   aria-pressed, and its selection has no double-click isolate or Reset; it also only dims (opacity), so y would keep the
   hidden series' range. So the hidden set drives a Vega param (dvHidden) that a `filter` transform on every series
   layer reads (y rescales; the rows are untouched), set with view.signal(...).runAsync(), never a re-embed. */

import embed from 'vega-embed';
// WHY from 'vega': it re-exports vega-statistics' bin (the same function), and vega is a declared dependency
import { bin as vegaBin } from 'vega';
import { cellValue, esc, fmtNum, numOpts, valueHtml, valueText, mediaUrl, groupLabel, hueOf, isNum, isEmpty, loadView, seriesColor, clockFor, TIME_GRAINS, timeBucket, bucketLabel, nextBucket, SeriesLegend } from '@data-ui/core';
import css from './chart.css';
import { theme } from './theme.js';
import { plotBox, GUTTER, TIME_PAD } from './overlay.js';
import { TimeseriesCard } from './timeseries.js';
import { TrajectoryView } from './trajectory.js';

export { css, theme };
export { compileTimeseries } from './timeseries.js';
export { compileTrajectory } from './trajectory.js';

const TYPE = { number: 'quantitative', text: 'nominal', list: 'nominal', boolean: 'nominal', date: 'temporal' };
const POINTS = new Set(['point', 'circle', 'square']);
const MARKS = ['point', 'circle', 'square', 'line', 'bar', 'tick', 'area'];
// WHY these four draw hollow: Vibe Tracks' convention, "filled marks are measured, hollow ones estimates or stand-ins";
// a datasheet or seller value is a published number, not a guess, so it stays filled
const HOLLOW = new Set(['estimate', 'stand-in', 'assumed', 'claimed']);
// WHY 8: the validated categorical palette has eight hues (--data-series-1..8); a ninth category would repeat a
// colour, so past eight the commonest seven keep theirs and the rest read "Other" (the hover card keeps the truth)
const HUES = 8;
// the legend's invisible layer: every row's x and colour while a series is hidden, so neither scale moves (see compile)
const GHOST = 'dv_legend_ghost';
const ENCODE = [['x', 'X'], ['y', 'Y'], ['color', 'Colour'], ['size', 'Size'], ['opacity', 'Opacity'], ['shape', 'Shape'], ['column', 'Small multiples']];

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));

/* The aggregate ops whose cells Vega cannot update in place exactly (vega 6.4, vega-transforms 5.2), measured against a
   fresh view of the same rows for every Vega-Lite op, composite mark and transform (tests/unit/kit-gaps.test.mjs):
   - the ones read from a cell's value store: median, q1, q3, ci0, ci1, and min, max, argmin, argmax once a removal
     reaches the extreme. WHY stale: TupleStore memoises its extent, its quartiles and its bootstrap CI under ONE key, the
     field's accessor; values() clears that key once per pulse, the first statistic recomputed sets it back, and every
     other statistic of the same field then reads its memo from before the swap (a boxplot's quartiles move, its
     whiskers stay: P4's CAN 13 whiskers on CAN 12's page). Unchanged on vega main, 2026-10-29.
   - product: updated by dividing out what leaves, so a 0 that leaves is 0 / 0, NaN for good.
   The composite marks compile into these. */
const STORE_OPS = new Set(['median', 'q1', 'q2', 'q3', 'ci0', 'ci1', 'min', 'max', 'argmin', 'argmax', 'product']);
const COMPOSITE = new Set(['boxplot', 'errorbar', 'errorband']);

/** Whether a Vega-Lite spec aggregates with an op Vega cannot update in place (STORE_OPS, or a composite mark): the charts
    whose rows swapData empties before it swaps them, so every cell is built afresh from its rows. */
export function freshCells(spec) {
  let fresh = false;
  const walk = (node) => {
    if (fresh || !node || typeof node !== 'object') return;
    if (Array.isArray(node)) { for (const x of node) walk(x); return; }
    for (const [k, v] of Object.entries(node)) {
      if (k === 'mark' && COMPOSITE.has(markType(v))) fresh = true;
      // an encoding's aggregate (a name, or {argmin: field}); a transform's aggregate, joinaggregate or window op
      else if (k === 'aggregate' && ((typeof v === 'string' && STORE_OPS.has(v)) || (v && typeof v === 'object' && !Array.isArray(v) && ('argmin' in v || 'argmax' in v)))) fresh = true;
      else if (k === 'op' && typeof v === 'string' && STORE_OPS.has(v)) fresh = true;
      else walk(v);
      if (fresh) return;
    }
  };
  walk(spec);
  return fresh;
}
// the name P2 gave the narrower test (min, max, argmin, argmax and the composites); the same seam
export const extentAggregates = freshCells;

/** The fast path's swap (ChartView._draw): the same spec, new rows. Sets every dataset of `datasets` on the view; when
    the spec aggregates with an op Vega cannot update in place (freshCells), it first empties them and runs, so every
    cell is dropped and the new rows build fresh ones. The caller runs the view after (with its signals and size).
    WHY here and not a re-embed: parsing the spec again costs ~100 ms (docs/SPEC.md §8.11); one extra pulse costs only
    the downstream operators of an empty dataset. */
export async function swapData(view, datasets, spec) {
  if (freshCells(spec)) {
    for (const name of Object.keys(datasets)) view.data(name, []);
    await view.runAsync();
  }
  for (const [name, values] of Object.entries(datasets)) view.data(name, values);
}

/** The clock's time column, as a chart reads it: a number column in seconds (no unit, or s). WHY the column's name and not
    its unit alone: a duration in seconds (ml-experiments' compute per run) is no time on the clock; the clock's own
    column is (a dashboard's clock.time, else t: the trajectory contract's and every time series' default). */
const SECONDS = new Set(['', 's', 'sec', 'secs', 'second', 'seconds']);
const isClockTime = (col, field, timeColumn) => !!(col && field === timeColumn && col.type === 'number' && SECONDS.has(String(col.unitText || '').trim().toLowerCase()));

/** A one-series bar histogram (x binned by maxbins, y a sum or count) as explicit transforms whose empty bins are
    imputed 0. The bins are Vega's own: vega-statistics' bin() over the drawn values with Vega-Lite's defaults (nice),
    then fixed (extent, step) so the impute's keys, sequence(start, stop, step), are the bins' own starts. The field
    names are the ones Vega-Lite gives an encoding bin (bin_maxbins_<n>_<field>, …_end, <op>_<field>). WHY only bars
    of one series: a colour split imputes per group, and a line's step needs its own placing (left for later). */
function zeroBins(u, drawn) {
  const x = u.encoding.x, y = u.encoding.y;
  if (markType(u.mark) !== 'bar' || u.transform || !x || !x.field || !x.bin || (typeof x.bin === 'object' && (x.bin.binned || x.bin.extent || x.bin.step || x.bin.steps || x.bin.anchor))) return;
  if (!y || !['sum', 'count'].includes(y.aggregate) || (y.aggregate === 'sum' && !y.field)) return;
  if (['color', 'detail', 'column', 'row', 'facet', 'x2', 'y2'].some((ch) => u.encoding[ch])) return;
  const opts = typeof x.bin === 'object' ? x.bin : {};
  let lo = Infinity, hi = -Infinity;
  for (const d of drawn) { const v = d[x.field]; if (typeof v === 'number' && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
  if (!(hi >= lo)) return;
  const maxbins = opts.maxbins || 10;
  const b = vegaBin({ extent: [lo, hi], maxbins, ...(opts.base ? { base: opts.base } : {}), ...(opts.divide ? { divide: opts.divide } : {}), ...(opts.minstep ? { minstep: opts.minstep } : {}), ...(opts.nice === false ? { nice: false } : {}) });
  const { step } = b, start = b.start, stop = start + Math.ceil((b.stop - start) / step) * step;
  const A = `bin_maxbins_${maxbins}_${x.field}`, E = `${A}_end`;
  const S = y.aggregate === 'count' ? `__count` : `${y.aggregate}_${y.field}`;
  u.transform = [
    { bin: { extent: [start, stop], step, nice: false }, field: x.field, as: [A, E] },
    { aggregate: [y.aggregate === 'count' ? { op: 'count', as: S } : { op: y.aggregate, field: y.field, as: S }], groupby: [A, E] },
    { impute: S, key: A, keyvals: { start, stop, step }, value: 0 },
    { calculate: `datum['${E}'] != null ? datum['${E}'] : datum['${A}'] + ${step}`, as: E },
  ];
  const { aggregate, ...yRest } = y;
  // WHY square ends: Vega-Lite 6.5 drops x and x2 from a ranged bar (binned x + x2) when any corner radius applies,
  // the theme's cornerRadiusEnd included, and draws every bar the plot's full width
  u.mark = { ...(typeof u.mark === 'object' ? u.mark : { type: 'bar' }), cornerRadiusEnd: 0 };
  u.encoding.x = { ...x, field: A, type: 'quantitative', bin: { binned: true, step } };
  u.encoding.x2 = { field: E };
  // WHY stack: null: Vega-Lite never stacks its own one-series binned aggregate (whatever y.stack says), but stacks a
  // pre-aggregated bar by default, which adds <S>_start and <S>_end to every datum; a reader that takes a bin as the key
  // with a <key>_end partner (P4's oracle) then saw two bins in each bar
  u.encoding.y = { ...yRest, field: S, type: 'quantitative', stack: null };
  return true;
}
/** The names a chart's transforms read (its own and each unit's): every `field`, `groupby`, `fold`, `flatten`, `pivot`,
    `value`, `key`, `on` and the regression / loess / density / quantile field, and each `datum.<name>` or
    `datum['<name>']` of a calculate or filter expression. The caller keeps the ones that are columns. */
function transformColumns(chart, units) {
  const out = new Set();
  const expr = (text) => {
    if (typeof text !== 'string') return;
    for (const m of text.matchAll(/datum\.([A-Za-z_]\w*)/g)) out.add(m[1]);
    for (const m of text.matchAll(/datum\[\s*(['"])(.+?)\1\s*\]/g)) out.add(m[2]);
  };
  const walk = (node, key) => {
    if (Array.isArray(node)) { for (const x of node) walk(x, key); return; }
    if (node && typeof node === 'object') { for (const [k, v] of Object.entries(node)) walk(v, k); return; }
    if (typeof node !== 'string') return;
    if (['field', 'groupby', 'fold', 'flatten', 'pivot', 'value', 'key', 'on', 'regression', 'loess', 'density', 'quantile', 'impute'].includes(key)) out.add(node);
    if (['calculate', 'filter', 'test', 'expr'].includes(key)) expr(node);
  };
  for (const t of [...(Array.isArray(chart.transform) ? chart.transform : []), ...units.flatMap((u) => (Array.isArray(u.transform) ? u.transform : []))]) walk(t, null);
  return out;
}

// a channel's field, and the field its sort reads (sort: {field, op}), both go into every datum
const fieldsOf = (enc) => Object.values(enc || {}).flatMap((c) => (Array.isArray(c) ? c : [c])).flatMap((c) => [c && c.field, c && c.sort && c.sort.field]).filter(Boolean);
// "Peak torque" reads "peak torque" mid-sentence; "q RMS" and "OD" keep their capitals
const lower = (s) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const median = (xs) => { const s = xs.filter(isNum).sort((a, b) => a - b); if (!s.length) return null; const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

export default class ChartView {
  constructor(host, el) {
    // WHY a switch here: this bundle registers chart, timeseries and trajectory (one Vega engine per page, PEP 0005
    // §7), and the registry constructs the module's default class for each; the element's class says which it is
    if (el.classList.contains('dv-view-timeseries')) return new TimeseriesCard(host, el);
    if (el.classList.contains('dv-view-trajectory')) return new TrajectoryView(host, el);
    this.host = host;
    this.el = el;
    // WHY a bare mode: the kpi view draws its headline's history with this view, without the bar, rows or status
    this.bare = el.hasAttribute('data-bare');
    this.showRows = false;
    this._peekId = null;
    this._key = null;
    this._job = Promise.resolve();
    el.innerHTML = `${this.bare ? '' : `<div class="dv-chart-bar">
        <button class="dv-btn dv-chart-encode" aria-haspopup="dialog" aria-expanded="false">Encode</button>
        <button class="dv-btn dv-chart-rowsbtn" aria-pressed="false">Rows</button>
        <span class="dv-chart-hint">Hover for its card · click to open</span>
      </div>`}
      <div class="dv-chart-legend" hidden></div>
      <div class="dv-chart-plot" role="img"><div class="dv-chart-canvas"></div><div class="dv-chart-playhead" data-playhead hidden></div></div>
      ${this.bare ? '' : '<div class="dv-chart-rows" hidden></div><div class="dv-chart-pop" role="dialog" aria-label="Encode" hidden></div>'}
      <div class="dv-chart-hover" hidden></div>`;
    this.$ = (sel) => el.querySelector(sel);
    this.plot = this.$('.dv-chart-plot');
    this.card = this.$('.dv-chart-hover');
    this.legend = new SeriesLegend(this.$('.dv-chart-legend'), { host, keyClass: 'dv-chart-key', onChange: () => this._applyHidden() });
    this.plot.addEventListener('mouseleave', () => this._hide());
    this._wire();
    this._resize = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => { if (this.input) this._queue(); }, 80);
    });
    this._resize.observe(this.plot);
    // the clock, from the first draw whose x is a time in seconds (CONTRACT §25 addendum): its t is a playhead, its
    // zoom window the x domain, as on a time series
    this.clock = null;
    this._win = null;
    this._onTime = () => this._place();
    this._onState = () => { if (this._meta && this._meta.time && JSON.stringify(this.clock.window) !== JSON.stringify(this._win)) this._queue(); };
  }

  /** Follow the clock (once): a chart whose x is a time in seconds, never a bare one (a KPI's history). */
  _follow() {
    if (this.clock || this.bare) return this.clock;
    this.clock = clockFor(this.host.element || this.el);
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('state', this._onState);
    return this.clock;
  }

  /** The playhead at the clock's t: a transform on one element, through the x scale Vega already computed (the time
      series' rule: never a Vega run per tick). */
  _place() {
    const ph = this.$('.dv-chart-playhead');
    const b = this._box;
    if (!ph) return;
    if (!b || !this._meta || !this._meta.time || !this.clock) { ph.hidden = true; return; }
    const t = this.clock.t;
    const [a, z] = b.sx.domain();
    if (!(t >= a && t <= z)) { ph.hidden = true; return; }
    ph.hidden = false;
    ph.style.height = `${b.h}px`;
    ph.style.transform = `translate(${b.x + b.sx(t) - 0.5}px, ${b.y}px)`;
  }

  destroy() {
    this._dead = true; // a queued draw never starts; one in flight stops at its next await (_draw)
    if (this.clock) { this.clock.removeEventListener('time', this._onTime); this.clock.removeEventListener('state', this._onState); }
    this._resize.disconnect();
    clearTimeout(this._resizeTimer);
    if (this._onDoc) document.removeEventListener('pointerdown', this._onDoc);
    this.legend.destroy();
    if (this.result) this.result.finalize();
    if (this.table) { try { this.table.destroy(); } catch { /* the table's own cleanup must not block ours */ } }
    if (!this.bare) this.host.setStatus('');
    this.el.innerHTML = '';
  }

  /** The host's peek opened ({id}) or closed (null): ring the dot. */
  peeked(peek) {
    this._peekId = peek ? peek.id : null;
    if (this.result && this._meta && this._meta.selectable) {
      this.result.view.data('sel', this._selection());
      this.result.view.runAsync();
    }
    if (this.table && this.table.peeked) this.table.peeked(peek);
  }

  update(input) {
    this.input = input;
    this.legend.sync(input);
    return this._queue();
  }

  /** The legend's hidden set on the drawn chart: two signals and one run (the filter reads dvHidden; dvPin turns on the
      layer that holds x and the colours still). */
  async _applyHidden() {
    if (!this.result || !this._meta || !this._meta.legend) return;
    const hidden = this.legend.hidden;
    const view = this.result.view;
    view.signal('dvHidden', hidden).signal('dvPin', hidden.length > 0);
    await view.runAsync();
  }

  /** The colour legend as buttons, before the plot is measured (its height is the plot's to give); the swatches are the
      colours Vega drew (its scale), once there is a view. */
  _drawLegend(meta) {
    const box = this.$('.dv-chart-legend');
    const lg = meta.legend;
    box.hidden = !lg;
    if (!lg) { this.legend.draw([]); return; }
    let names = lg.names, colors = lg.colors;
    const scale = this.result && this._key === meta.key ? this.result.view.scale('color') : null;
    if (scale && typeof scale.domain === 'function') { names = scale.domain().map(String); colors = scale.domain().map((d) => scale(d)); }
    this.legend.draw(names.map((n, i) => ({ name: n, swatch: `<i style="--dv-ts-c:${esc(colors[i] || '')}"></i>` })), this.legend.hidden, { title: lg.title || '' });
  }

  // WHY a queue: a filter can change while the last chart is still embedding; draw in order, and only the newest.
  // WHY one waiting draw: it reads this.input when it starts, so updates that arrive before then join it (20
  // synchronous updates drew 20 times, each from the same latest input; 2026-10-26 performance review)
  _queue() {
    if (this._waiting) return this._waiting;
    this._job = this._waiting = this._job.then(() => { this._waiting = null; return this._dead ? undefined : this._draw(); }).catch((err) => this._fail(err));
    return this._job;
  }

  async _draw() {
    const input = this.input;
    // WHY no Encode / Rows bar under style.chrome minimal (a dashboard's default): a dashboard card is a frameless
    // figure in Zach's references (Klipfolio, Tremor), not an editor; the same view outside a dashboard keeps its bar
    if (!this.bare) this.el.classList.toggle('dv-chart-minimal', !!(input.view.style && input.view.style.chrome === 'minimal'));
    const data = this.host.element && this.host.element.data;
    const base = this.host.element && this.host.element.base;
    const size = () => {
      // WHY layout sizes, not the bounding box: inside a scaled container (the landing page's thumbnails draw a view at
      // twice its box, scaled by half) the box is the scaled size, and the chart must lay out at its own CSS size
      const w = this.plot.clientWidth, h = this.plot.clientHeight;
      return [Math.max(240, Math.floor(w || this.el.clientWidth || 640)), Math.max(120, Math.floor(h || 360))];
    };
    // WHY no rail facets when bare: Show Me's colour default would split a KPI's one history line by model
    let win = this.clock ? this.clock.window : null;
    // the clock's time column: a dashboard's clock.time (its clock says), else t (what clockFor finds without a dashboard)
    const near = this.bare ? null : this.clock || clockFor(this.host.element || this.el);
    const timeColumn = (near && near.timeColumn) || 't';
    const compileAt = ([w, h]) => compile(input, { width: w, height: h, whole: data && data.rows, facets: (!this.bare && base && base.facets) || [], peekId: this._peekId, hidden: this.legend.hidden, win: this.bare ? null : win, timeColumn: this.bare ? null : timeColumn });
    // small multiples keep the trim their last draw needed, so a filter swaps data instead of re-embedding twice
    const run = ([w, h]) => { const o = compileAt([w, h]); return !o.size && this._trim && this._trim[0] === `${w}x${h}` ? compileAt([w, h - this._trim[1]]) : o; };
    let [width, height] = size();
    let out = run([width, height]);
    // a time on x: the first draw finds the clock; a zoom window it already has is the domain
    if (out.meta.time && !this.clock && this._follow() && this.clock.window) { win = this.clock.window; out = run([width, height]); }
    // WHY the status (and the legend) first: its line can wrap and take the plot's height; measure the plot after it
    // settles (a resize that returns to its last size within one frame never reaches the ResizeObserver)
    this._status(out.meta);
    this._drawLegend(out.meta);
    const [w2, h2] = size();
    if (w2 !== width || h2 !== height) { [width, height] = [w2, h2]; out = run([width, height]); }
    this._meta = out.meta;
    this._rowsDrawn = input.rows;
    if (out.key === this._key && this.result) {
      // the fast path: same spec, new rows (a filter, a search). WHY: re-embedding parses the spec again (~100+ ms);
      // swapping the named datasets is what keeps a filter under 100 ms on 1,149 dots (docs/SPEC.md §8.11)
      const view = this.result.view;
      // WHY swapData (freshCells): an aggregate Vega cannot update in place (a boxplot's whiskers, a median beside a
      // max, a bootstrap CI, a product) is rebuilt from the new rows, never read back from a cell of the old ones
      await swapData(view, out.datasets, out.spec);
      if (this._dead) return;
      if (out.meta.legend) view.signal('dvHidden', this.legend.hidden).signal('dvPin', this.legend.hidden.length > 0);
      if (out.meta.time) view.signal('dvXmin', out.meta.time.domain[0]).signal('dvXmax', out.meta.time.domain[1]);
      // WHY resize(): under autosize fit the legend and axes are re-measured only when the view is told to
      if (out.size) view.width(out.size[0]).height(out.size[1]).resize();
      await view.runAsync();
      if (this._dead) return;
    } else {
      if (this.result) this.result.finalize();
      this.result = null;
      const spec = { ...out.spec, datasets: out.datasets };
      const result = await embed(this.$('.dv-chart-canvas'), spec, { actions: false, renderer: 'canvas', tooltip: false, mode: 'vega-lite', logLevel: 1 });
      if (this._dead) { result.finalize(); return; }
      this.result = result;
      this._key = out.key;
      this._listen(this.result.view);
      this.el.vegaView = this.result.view;
    }
    // WHY a second pass: autosize fit underestimates a bottom legend that wraps (phones), and small multiples are sized
    // from an estimate of their headers and axes, so the canvas can outgrow the plot; shrink by exactly the overflow, once
    const canvas = this.plot.querySelector('canvas');
    const over = canvas ? Math.ceil(canvas.offsetHeight - height) : 0;
    if (over > 1 && out.size) {
      const view = this.result.view;
      view.height(Math.max(80, view.height() - over)).resize();
      await view.runAsync();
      if (this._dead) return;
    } else if (over > 1) {
      this._trim = [`${width}x${height}`, over + ((this._trim && this._trim[0] === `${width}x${height}`) ? this._trim[1] : 0)];
      const again = compileAt([width, height - this._trim[1]]);
      this.result.finalize();
      const result = await embed(this.$('.dv-chart-canvas'), { ...again.spec, datasets: again.datasets }, { actions: false, renderer: 'canvas', tooltip: false, mode: 'vega-lite', logLevel: 1 });
      if (this._dead) { result.finalize(); return; }
      this.result = result;
      this._listen(this.result.view);
      this.el.vegaView = this.result.view;
      this._key = again.key;
    }
    this.el.dataset.drawn = String(out.meta.drawn);
    this.plot.setAttribute('aria-label', out.meta.aria);
    out.meta.key = this._key;
    // a time on x: the span of its rows is the clock's (a time series' rule), its playhead at t
    this._win = out.meta.time ? win : null;
    if (out.meta.time && this.clock) this.clock.extent(out.meta.time.extent[0], out.meta.time.extent[1]);
    this._box = out.meta.time ? plotBox(this.result.view, this.plot) : null;
    this._place();
    this._drawLegend(out.meta);
    if (!this.bare) this._drawPop();
    if (this.showRows) await this._drawRows();
  }

  _fail(err) {
    if (this._dead) return;
    this._key = null;
    this.$('.dv-chart-canvas').innerHTML = `<p class="dv-err dv-chart-err">This chart could not be drawn: ${esc(err && err.message ? err.message : err)}</p>`;
    if (!this.bare) this.host.setStatus('');
  }

  _status(meta) {
    if (this.bare) return;
    const n = (x) => x.toLocaleString('en-US');
    const lost = meta.dropped ? ` · ${n(meta.dropped)} without ${meta.droppedWhy}` : '';
    const what = meta.aggregated ? `${n(meta.drawn)} rows drawn as ${meta.mark === 'bar' ? 'bars' : 'marks'}` : `${n(meta.drawn)} dots`;
    const notes = meta.notes.length ? ` · ${meta.notes.map(esc).join(' · ')}` : '';
    this.host.setStatus(`<span class="dv-chart-status">${what}${lost}${notes}</span>`);
  }

  _selection() {
    const m = this._meta;
    if (!m || !m.selectable || this._peekId === null) return [];
    const i = this._rowsDrawn.findIndex((r) => String(r.id) === this._peekId);
    return i < 0 ? [] : m.datumOf(this._rowsDrawn[i], i).filter(Boolean);
  }

  // ------------------------------------------------------------------ hover card and click
  _listen(view) {
    view.addEventListener('mousemove', (event, item) => this._hover(event, item));
    view.addEventListener('mouseout', (event, item) => { if (!item || !this._rowOf(item)) this._hide(); });
    view.addEventListener('click', (event, item) => this._click(item));
  }

  _rowOf(item) {
    const d = item && item.datum;
    // WHY not lines or areas: their hit item is the whole path, whose datum is only its first row; nor the legend's
    // invisible layer (GHOST), which only holds the scales while a series is hidden
    if (!d || typeof d !== 'object' || (item.mark && ['line', 'area', 'trail'].includes(item.mark.marktype))) return null;
    if (item.mark && String(item.mark.name || '').startsWith(GHOST)) return null;
    if (isNum(d._row) && this._rowsDrawn[d._row]) return { row: this._rowsDrawn[d._row] };
    if (d._g !== undefined || d._guide) return null;
    const records = this._meta && this._meta.recordsOf(d, this._rowsDrawn);
    return records && records.length ? { datum: d, records } : null;
  }

  _hover(event, item) {
    const hit = this._rowOf(item);
    if (!hit) { this._hide(); this.plot.style.cursor = ''; return; }
    this.plot.style.cursor = 'pointer';
    const key = hit.row ? `r${hit.row.id}` : JSON.stringify(hit.datum);
    if (key !== this._cardKey) {
      this._cardKey = key;
      this.card.innerHTML = hit.row ? this._cardHtml(hit.row) : this._aggHtml(hit.datum, hit.records);
    }
    this.card.hidden = false;
    const host = this.el.getBoundingClientRect();
    const w = this.card.offsetWidth, h = this.card.offsetHeight;
    let x = event.clientX - host.left + 14, y = event.clientY - host.top + 14;
    if (x + w > host.width - 4) x = Math.max(4, event.clientX - host.left - w - 14);
    if (y + h > host.height - 4) y = Math.max(4, event.clientY - host.top - h - 14);
    this.card.style.transform = `translate(${x}px, ${y}px)`;
  }

  _hide() {
    this.card.hidden = true;
    this._cardKey = null;
  }

  /** The hover card for one row: `hover: {image, title, fields}`, else the dataset's image and title and the
      encoded fields. Values go through valueHtml, so each keeps its unit and basis mark. */
  _cardHtml(row) {
    const { view, columns, dataset } = this.input;
    const hover = view.hover || {};
    const imageProp = hover.image || dataset.imageProperty;
    const titleProp = hover.title || dataset.titleProperty;
    const src = imageProp ? cellValue(row[imageProp]) : null;
    const title = titleProp ? valueText(row[titleProp], columns[titleProp]) : String(row.id);
    const fields = (hover.fields && hover.fields.length ? hover.fields : this._meta.fields).filter((f) => columns[f] && f !== titleProp && f !== imageProp);
    const lines = fields.map((f) => `<tr><th scope="row">${esc(columns[f].label)}</th><td>${valueHtml(row[f], columns[f])}</td></tr>`).join('');
    const img = imageProp ? (src ? `<div class="dv-chart-img"><img src="${esc(mediaUrl(src, dataset))}" alt="" decoding="async"></div>` : '<div class="dv-chart-noimg">no photo</div>') : '';
    return `${img}<div class="dv-chart-card-body"><b>${esc(title)}</b><table>${lines}</table><p class="dv-chart-cardhint">Click to open</p></div>`;
  }

  /** The hover card for an aggregate (a bar of a median, a histogram bin): what it summarises and how many rows. */
  _aggHtml(datum, records) {
    const lines = this._meta.datumFields(datum).map(([label, value, col]) => `<tr><th scope="row">${esc(label)}</th><td>${col ? valueHtml(value, col) : esc(isNum(value) ? fmtNum(value) : value)}</td></tr>`).join('');
    return `<div class="dv-chart-card-body"><table>${lines}</table><p class="dv-chart-cardhint">${records.length.toLocaleString('en-US')} rows · click to list them</p></div>`;
  }

  _click(item) {
    const hit = this._rowOf(item);
    if (!hit) return;
    this._hide();
    if (hit.row) { this.host.open(hit.row.id, { column: this._meta.x || null }); return; }
    const fields = this._meta.datumFields(hit.datum);
    const title = fields.map(([, v, col]) => (col ? valueText(v, col) : isNum(v) ? fmtNum(v) : v)).join(' · ');
    const row = { id: `chart:${title}` };
    for (const [, v, col] of fields) if (col) row[col.id] = v;
    this.host.open(row.id, { row, records: hit.records, title });
  }

  // ------------------------------------------------------------------ the bar: Encode and Rows
  _wire() {
    if (this.bare) return;
    this.$('.dv-chart-encode').addEventListener('click', () => {
      const pop = this.$('.dv-chart-pop');
      pop.hidden = !pop.hidden;
      this.$('.dv-chart-encode').setAttribute('aria-expanded', String(!pop.hidden));
      this.$('.dv-chart-encode').classList.toggle('dv-on', !pop.hidden);
      if (!pop.hidden) { this._drawPop(); const first = pop.querySelector('select'); if (first) first.focus(); }
    });
    this.$('.dv-chart-rowsbtn').addEventListener('click', () => this.toggleRows());
    this.el.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !this.$('.dv-chart-pop').hidden) { e.stopPropagation(); this._closePop(); }
    });
    // WHY on the document: a click outside the Encode menu closes it, as the host's own menus do
    this._onDoc = (e) => {
      const pop = this.$('.dv-chart-pop');
      if (pop && !pop.hidden && !pop.contains(e.target) && !e.target.closest('.dv-chart-encode')) this._closePop();
    };
    document.addEventListener('pointerdown', this._onDoc);
  }

  _closePop() {
    const pop = this.$('.dv-chart-pop');
    pop.hidden = true;
    this.$('.dv-chart-encode').setAttribute('aria-expanded', 'false');
    this.$('.dv-chart-encode').classList.remove('dv-on');
  }

  /** Rows: the same filtered rows as the table view, under the chart (Tableau's View Data; docs/SPEC.md §8.7). */
  async toggleRows(on = !this.showRows) {
    this.showRows = on;
    this.$('.dv-chart-rowsbtn').setAttribute('aria-pressed', String(on));
    this.$('.dv-chart-rowsbtn').classList.toggle('dv-on', on);
    this.el.classList.toggle('dv-chart-with-rows', on);
    const box = this.$('.dv-chart-rows');
    box.hidden = !on;
    if (on) await this._drawRows();
  }

  async _drawRows() {
    if (!this.table) {
      const { View } = await loadView('table');
      if (this._dead) return;
      const el = document.createElement('div');
      el.className = 'dv-view dv-view-table';
      this.$('.dv-chart-rows').replaceChildren(el);
      const host = this.host;
      // WHY a proxy host: the table's sort and column edits land in this view's own entry; its fold links stay out
      // of the status line, which belongs to the chart
      this.table = new View(Object.freeze({
        setView: (patch) => host.setView(patch), propose: (edit) => host.propose(edit), open: (id, opts) => host.open(id, opts),
        setStatus: () => {}, get element() { return host.element; },
      }), el);
    }
    const input = this.input;
    const { columns, view } = input;
    const first = this._meta ? this._meta.fields : [];
    const order = view.order && view.order.length ? view.order : [...new Set([...first, ...Object.keys(columns).filter((id) => !columns[id].hidden)])].filter((id) => columns[id] && !columns[id].hidden);
    this.table.update({ ...input, view: Object.freeze({ ...clone(view), type: 'table', order }) });
  }

  /** The Encode menu: mark, the channels, log or linear per axis and the hover card's fields. Every change is a
      host.setView({chart}) (or {hover}), so the view reads "changed" and Save writes the grammar an agent writes. */
  _drawPop() {
    const pop = this.$('.dv-chart-pop');
    if (!pop || pop.hidden || !this._meta) return;
    const { columns, view } = this.input;
    const m = this._meta;
    const enc = m.encoding;
    const props = Object.values(columns).filter((p) => !p.hidden);
    const opts = (cur, { none, numeric, nominal } = {}) => (none ? `<option value="">${esc(none)}</option>` : '')
      + props.filter((p) => (!numeric || p.type === 'number') && (!nominal || p.type !== 'number')).map((p) => `<option value="${esc(p.id)}"${p.id === cur ? ' selected' : ''}>${esc(p.label)}</option>`).join('');
    const scale = (ch) => {
      const c = enc[ch];
      if (!c || !c.field || !columns[c.field] || columns[c.field].type !== 'number') return '';
      const set = m.explicitScale[ch];
      const now = c.scale && c.scale.type ? c.scale.type : 'linear';
      return `<select data-scale="${ch}" aria-label="${ch.toUpperCase()} scale"><option value=""${!set ? ' selected' : ''}>auto (${esc(now)})</option><option value="linear"${set === 'linear' ? ' selected' : ''}>linear</option><option value="log"${set === 'log' ? ' selected' : ''}>log</option></select>`;
    };
    const rows = ENCODE.map(([ch, label]) => {
      const c = enc[ch];
      const cur = c && c.field ? c.field : '';
      const none = ch === 'x' || ch === 'y' ? (cur ? null : 'none') : 'none';
      const kind = ch === 'size' || ch === 'opacity' ? { numeric: true } : ch === 'shape' || ch === 'column' ? { nominal: true } : {};
      return `<label><span>${label}</span><span class="dv-chart-pair"><select data-ch="${ch}" aria-label="${label}">${opts(cur, { none, ...kind })}</select>${ch === 'x' || ch === 'y' ? scale(ch) : ''}</span></label>`;
    }).join('');
    const hoverFields = (view.hover && view.hover.fields) || m.fields;
    const checks = props.filter((p) => p.id !== ((view.hover && view.hover.title) || this.input.dataset.titleProperty) && p.id !== (view.hover && view.hover.image))
      .map((p) => `<label class="dv-chart-check"><input type="checkbox" data-hover="${esc(p.id)}"${hoverFields.includes(p.id) ? ' checked' : ''}> ${esc(p.label)}</label>`).join('');
    pop.innerHTML = `<h4>Encode</h4>
      <label><span>Mark</span><select data-mark aria-label="Mark">${MARKS.map((k) => `<option${k === m.mark ? ' selected' : ''}>${k}</option>`).join('')}</select></label>
      ${rows}
      <details class="dv-chart-hoverset"><summary>Hover card shows</summary><div class="dv-chart-checks">${checks}</div></details>
      <p class="dv-hint">Each change edits this view's <code>chart:</code> block. Reset undoes it; Save view keeps it.</p>`;
    pop.querySelector('[data-mark]').addEventListener('change', (e) => this._edit((u) => { u.mark = typeof u.mark === 'object' && u.mark ? { ...u.mark, type: e.target.value } : e.target.value; if (e.target.value !== 'line' && u.mark && typeof u.mark === 'object') delete u.mark.point; }));
    pop.querySelectorAll('[data-ch]').forEach((s) => s.addEventListener('change', () => this._edit((u) => {
      const ch = s.dataset.ch;
      u.encoding = u.encoding || {};
      const old = u.encoding[ch] || (m.encoding[ch] && m.encoding[ch].field ? { field: m.encoding[ch].field } : {});
      if (!s.value) { delete u.encoding[ch]; return; }
      const numeric = columns[s.value] && columns[s.value].type === 'number';
      const next = { field: s.value };
      if (numeric && old.aggregate) next.aggregate = old.aggregate;
      if (numeric && old.scale) next.scale = old.scale;
      if (numeric && old.bin) next.bin = old.bin;
      u.encoding[ch] = next;
      if (ch === 'column') { delete u.encoding.row; delete u.encoding.facet; }
    })));
    pop.querySelectorAll('[data-scale]').forEach((s) => s.addEventListener('change', () => this._edit((u) => {
      const ch = s.dataset.scale;
      u.encoding = u.encoding || {};
      const c = u.encoding[ch] || { field: m.encoding[ch].field };
      const sc = { ...(c.scale || {}) };
      if (s.value) sc.type = s.value; else delete sc.type;
      if (Object.keys(sc).length) c.scale = sc; else delete c.scale;
      u.encoding[ch] = c;
    })));
    pop.querySelectorAll('[data-hover]').forEach((c) => c.addEventListener('change', () => {
      const fields = [...pop.querySelectorAll('[data-hover]')].filter((x) => x.checked).map((x) => x.dataset.hover);
      this.host.setView({ hover: { ...(this.input.view.hover || {}), fields } });
    }));
  }

  /** Edit the view's main unit spec (the chart itself, or its first layer with an x or y) and write it back. */
  _edit(change) {
    const chart = clone(this.input.view.chart || {});
    const layered = Array.isArray(chart.layer);
    const at = layered ? Math.max(0, chart.layer.findIndex((l) => l.encoding && (l.encoding.x || l.encoding.y))) : -1;
    const unit = layered ? chart.layer[at] : chart;
    change(unit);
    this.host.setView({ chart });
  }
}

// ------------------------------------------------------------------ the compiler: a view entry -> Vega-Lite

const resolveVars = (spec, tokens) => JSON.parse(JSON.stringify(spec), (_k, v) => (typeof v === 'string' && /^var\(--[\w-]+\)$/.test(v) ? tokens.css[v.slice(6, -1)] || v : v));
const markType = (mark) => (mark && typeof mark === 'object' ? mark.type : mark) || null;

/** The view's rows, entry and tokens -> {spec (no data), datasets, key, meta}. The key changes only when the spec
    does, so the view can swap datasets instead of re-embedding. Exported for tests. */
export function compile(input, { width = 640, height = 400, whole = null, facets = [], peekId = null, hidden = [], win = null, timeColumn = 't' } = {}) {
  const { rows, view, columns, tokens } = input;
  const all = whole || input.rows;
  const chart = resolveVars(view.chart || {}, tokens);
  const notes = [];
  // WHY safe names: Vega-Lite reads a dot or a bracket in a field as a path; a point selection on an escaped dotted
  // name records nothing (vault, Oct 5), so every field goes in under a name with neither
  const names = new Map();
  const safe = (f) => {
    if (!names.has(f)) {
      let s = String(f).replace(/[^\w]/g, '_');
      while ([...names.values()].includes(s)) s += '_';
      names.set(f, s);
    }
    return names.get(f);
  };
  const typeOf = (f) => (columns[f] ? TYPE[columns[f].type] || 'nominal' : 'nominal');
  const label = (f) => (columns[f] ? columns[f].label : f);
  const titleOf = (f, c) => {
    const p = columns[f];
    const unit = p && p.unitText ? ` (${p.unitText})` : '';
    const name = `${label(f)}${unit}`;
    return c && c.aggregate ? `${String(c.aggregate)[0].toUpperCase()}${String(c.aggregate).slice(1)} of ${name}` : name;
  };

  // ---- the main units: the chart, or its layers
  const layered = Array.isArray(chart.layer);
  const units = layered ? chart.layer.map((l) => ({ ...l })) : [{ mark: chart.mark, encoding: chart.encoding || {}, transform: chart.transform, params: chart.params }];
  for (const u of units) { u.encoding = clone(u.encoding || {}); if (!u.transform) delete u.transform; if (!u.params) delete u.params; }
  const main = units.find((u) => u.encoding.x || u.encoding.y) || units[0];
  const enc = main.encoding;
  // the user's own channels, before any default fills in: the Encode menu shows "auto" for the rest
  const explicitScale = { x: enc.x && enc.x.scale && enc.x.scale.type, y: enc.y && enc.y.scale && enc.y.scale.type };
  for (const ch of Object.keys(enc)) if (enc[ch] === null || (enc[ch] && typeof enc[ch] === 'object' && !Array.isArray(enc[ch]) && 'field' in enc[ch] && !enc[ch].field)) delete enc[ch];
  if (!enc.x && !enc.y && !layered) {
    const nums = Object.values(columns).filter((p) => p.type === 'number' && !p.hidden);
    if (nums[0]) enc.x = { field: nums[0].id };
    if (nums[1]) enc.y = { field: nums[1].id };
  }
  // a date channel with `by:` plots each row in its bucket, the buckets a group level's `by:` makes (ISO weeks from
  // Monday; docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail)): one band per bucket, every bucket from
  // the data's first to its last in time order, so a week with no rows is an empty band (Tableau's discrete date).
  // WHY not Vega-Lite's timeUnit: its weeks start on Sunday and it reads a date in the viewer's zone, so its buckets
  // would differ from the table's.
  const grains = new Map(), gapsOf = new Map();
  for (const u of units) {
    for (const c of Object.values(u.encoding)) {
      for (const d of Array.isArray(c) ? c : [c]) {
        if (!d || !d.field || !columns[d.field] || !TIME_GRAINS.includes(d.by)) continue;
        const by = d.by;
        if (d.gaps !== undefined) { gapsOf.set(d.field, !!d.gaps); delete d.gaps; }
        if (!grains.has(d.field)) {
          const keys = [...new Set(all.map((r) => timeBucket(r[d.field], by)).filter(Boolean))].sort();
          const domain = [];
          for (let k = keys[0]; k && k <= keys[keys.length - 1]; k = nextBucket(k, by)) domain.push(bucketLabel(k, by));
          grains.set(d.field, { by, domain });
        }
        d.type = 'ordinal';
        d.scale = { ...(d.scale || {}), domain: grains.get(d.field).domain };
        if (d.title === undefined) d.title = `${titleOf(d.field)} (${by})`;
        delete d.by;
      }
    }
  }
  // a cell as the chart plots it: a bucketed date is its bucket's label ("Week of 21 Sep 2026"), a row with no date none
  const at = (r, f) => (grains.has(f) ? bucketLabel(r[f], grains.get(f).by) : r[f]);
  for (const u of units) {
    for (const [ch, c] of Object.entries(u.encoding)) {
      for (const d of Array.isArray(c) ? c : [c]) {
        // a field the data does not have (one a transform calculates) is left to Vega-Lite
        if (!d || !d.field || !columns[d.field]) continue;
        if (!d.type) d.type = d.bin && typeOf(d.field) !== 'quantitative' ? 'quantitative' : typeOf(d.field);
        if (d.title === undefined && ch !== 'tooltip') d.title = titleOf(d.field, d);
      }
    }
  }

  // ---- Show Me defaults (docs/SPEC.md §8.5): only what the view leaves out
  const xT = enc.x && enc.x.type, yT = enc.y && enc.y.type;
  const distinct = (f, list = all) => new Set(list.map((r) => plain(at(r, f), columns[f]))).size;
  // WHY a line over time by default (Zach, 2026-10-26): "Showing how things change by week is likely best done with a
  // line chart (and runs per week), whenever we want to show how things change over time." A date x or a time bucket
  // (by: day|week|month|quarter|year) with a number or an aggregate on y draws a line, with points while sparse; a
  // count over buckets is 0 in an empty bucket (true: no rows), and with gaps: true, or any other aggregate, the line
  // breaks there. Bars stay one `mark: bar` away.
  let imputed = null;
  const bucketX = enc.x && enc.x.field && grains.has(enc.x.field);
  const timeX = xT === 'temporal' || bucketX;
  const numY = enc.y && (yT === 'quantitative' || !!enc.y.aggregate);
  if (!main.mark && timeX && numY) {
    const n = bucketX ? grains.get(enc.x.field).domain.length : new Set(rows.map((r) => String(cellValue(r[enc.x.field])))).size;
    main.mark = { type: 'line', point: n <= 40 };
    // a count (or other aggregate) over buckets: every bucket of the axis gets a value (below, after field renaming)
    if (bucketX && enc.y.aggregate) imputed = { x: enc.x.field, y: enc.y.field || null, op: enc.y.aggregate, color: enc.color && enc.color.field ? enc.color.field : null,
      gaps: gapsOf.get(enc.x.field) === true || enc.y.aggregate !== 'count', domain: grains.get(enc.x.field).domain };
  }
  if (!main.mark) {
    if (enc.x && enc.y) {
      const q = (t) => t === 'quantitative';
      if (q(xT) && q(yT)) main.mark = 'point';
      else if ((q(xT) && !q(yT) && yT !== 'temporal') || (q(yT) && !q(xT) && xT !== 'temporal')) {
        const [cat, num] = q(yT) ? ['x', 'y'] : ['y', 'x'];
        if (distinct(enc[cat].field, rows) <= 20) {
          main.mark = 'bar';
          if (!enc[num].aggregate) { enc[num].aggregate = 'median'; enc[num].title = titleOf(enc[num].field, enc[num]); }
        } else main.mark = 'tick';
      } else if ((xT === 'temporal' && q(yT)) || (yT === 'temporal' && q(xT))) main.mark = rows.length < 10 ? 'point' : { type: 'line', point: true };
      else main.mark = 'point';
    } else if (enc.x || enc.y) {
      const ch = enc.x ? 'x' : 'y', other = ch === 'x' ? 'y' : 'x';
      main.mark = 'bar';
      if (enc[ch].type === 'quantitative' && !enc[ch].bin && !enc[ch].aggregate) enc[ch].bin = true;
      if (!enc[other]) enc[other] = { aggregate: 'count', type: 'quantitative', title: 'Rows' };
    } else main.mark = 'point';
  }
  const mark = markType(main.mark);
  const pointish = POINTS.has(mark) || (mark === 'line' && typeof main.mark === 'object' && main.mark.point);
  const aggregated = units.some((u) => Object.values(u.encoding).some((c) => c && !Array.isArray(c) && (c.aggregate || c.bin)));
  // log only where the positive values span two decades over the WHOLE data, so the axis never flips while filtering
  for (const ch of ['x', 'y']) {
    const c = enc[ch];
    if (!c || c.type !== 'quantitative' || c.aggregate || c.bin || explicitScale[ch] || !(pointish || mark === 'tick') || (c.scale && c.scale.type)) continue;
    const pos = all.map((r) => cellValue(r[c.field])).filter((v) => isNum(v) && v > 0);
    // WHY a fold, not Math.max(...pos): spreading 150,000 rows into one call overflows the stack (2026-10-26 review)
    if (pos.length > 2 && pos.reduce((a, b) => Math.max(a, b), -Infinity) / pos.reduce((a, b) => Math.min(a, b), Infinity) >= 100) c.scale = { ...(c.scale || {}), type: 'log' };
  }
  // colour: the first rail facet with 10 or fewer values, for dots and lines only
  if (!enc.color && !layered && (pointish || mark === 'line')) {
    for (const f of facets) {
      const p = typeof f === 'string' ? f : f && f.property;
      const as = typeof f === 'object' && f ? f.as : null;
      if (!columns[p] || columns[p].type === 'number' || as === 'range' || as === 'has') continue;
      if (distinct(p) <= 10) { enc.color = { field: p, type: 'nominal', title: titleOf(p) }; break; }
    }
  }
  // a line with points is two layers, so the points hover, ring and draw hollow like any dot
  for (let i = units.length - 1; i >= 0; i--) {
    const u = units[i];
    if (markType(u.mark) === 'line' && typeof u.mark === 'object' && u.mark.point) {
      const { point, ...line } = u.mark;
      const dots = { mark: { type: 'point', filled: true, size: 44, ...(typeof point === 'object' ? point : {}) }, encoding: clone(u.encoding) };
      units.splice(i, 1, { ...u, mark: line }, dots);
    }
  }
  const mains = units;
  const dotUnits = mains.filter((u) => POINTS.has(markType(u.mark)));

  // ---- facets: row / column / facet hoist to the facet operator (a layered chart cannot carry them)
  const facet = {};
  for (const ch of ['row', 'column', 'facet']) {
    if (enc[ch]) { facet[ch] = enc[ch]; for (const u of mains) delete u.encoding[ch]; }
  }
  const facetFields = Object.values(facet).map((c) => c.field).filter(Boolean);

  // ---- the fields every datum carries, and which rows are drawn
  const xF = enc.x && enc.x.field, yF = enc.y && enc.y.field;
  // WHY the columns the transforms read too: a datum carries only the fields it is given, so an aggregate over a column
  // no channel names (argmin of qd beside a median) read nothing (kit gap 5)
  const used = [...new Set([...mains.flatMap((u) => fieldsOf(u.encoding)), ...facetFields, ...transformColumns(chart, mains),
    ...(view.guides || []).map((g) => g.envelope).filter(Boolean)])].filter((f) => columns[f]);
  const tooltip = mains.flatMap((u) => { const t = u.encoding.tooltip; delete u.encoding.tooltip; return (Array.isArray(t) ? t : t ? [t] : []).map((c) => (typeof c === 'string' ? c : c.field)); }).filter((f) => columns[f]);
  const raw = (ch) => enc[ch] && enc[ch].type === 'quantitative' && !enc[ch].aggregate && !enc[ch].bin;
  const logOf = (ch) => !!(enc[ch] && enc[ch].scale && enc[ch].scale.type === 'log');
  // WHY columns only: a field a transform makes (calculate, window, bin as…) is not in the rows yet; reading it here
  // dropped every row, so the chart drew nothing (kit gap 5). Vega-Lite reads it after its transforms
  const needs = ['x', 'y'].filter((ch) => enc[ch] && enc[ch].field && columns[enc[ch].field] && (raw(ch) || enc[ch].type === 'temporal' || grains.has(enc[ch].field)));
  const colorF = enc.color && enc.color.field && enc.color.type === 'nominal' ? enc.color.field : null;
  // the colour of a value: the column's `colors` (the badges' colours: a slot 1-8, muted or 0, a token, a CSS colour),
  // else the palette in order of count. A null cell is muted, whatever the map or the palette say (kit gap 6): its label
  // ("No fault") is a sentence about absence, never a category, so it never takes a hue, hashed or listed
  let colorMap = null;
  const palette = (view.style && view.style.palette) || {};
  const nullLabel = colorF ? plain(null, columns[colorF]) : null;
  if (colorF && !(enc.color.scale && (enc.color.scale.domain || enc.color.scale.range || enc.color.scale.scheme))) {
    const p = columns[colorF];
    // the drawn rows' values: a palette colour is fixed by name, so the legend lists only what is on the plot
    const values = [...new Set(rows.map((r) => plain(r[colorF], p)))];
    if (values.some((v) => v !== nullLabel && palette[v])) {
      // the dashboard's palette names these values (style.palette): every card colours "tuned" alike; a value it does
      // not name takes its stable slot (seriesColor), in the order the rows first show it
      enc.color.scale = { domain: values, range: values.map((v) => (v === nullLabel ? tokens.muted : seriesColor(v, input))) };
    } else if (p.colors) {
      const domain = [...new Set(all.map((r) => plain(r[colorF], p)))].sort();
      enc.color.scale = { domain, range: domain.map((v) => (v === nullLabel ? tokens.muted : mapColor(p.colors[v] != null ? p.colors[v] : hueOf(v), tokens))) };
    } else colorMap = true;
  }
  const yBasis = yF && raw('y') ? yF : null;
  let dropped = 0;
  const why = new Set();
  const drawn = [];
  const keep = [];
  // an aggregate of nothing draws no mark, only an empty category: a row without the aggregated value is counted out
  const measured = aggregated ? [...new Set(mains.flatMap((u) => Object.values(u.encoding)).filter((c) => c && !Array.isArray(c) && c.field && c.aggregate && c.aggregate !== 'count').map((c) => c.field))] : [];
  rows.forEach((r, i) => {
    if (measured.length && measured.every((f) => !isNum(cellValue(r[f])))) { dropped++; why.add(measured.map((f) => lower(label(f))).join(' or ')); return; }
    for (const ch of needs) {
      const v = cellValue(at(r, enc[ch].field));
      const bad = enc[ch].type === 'temporal' || grains.has(enc[ch].field) ? isEmpty(v) : !isNum(v) || (logOf(ch) && v <= 0);
      if (bad) { dropped++; why.add(logOf(ch) && isNum(v) ? `a positive ${lower(label(enc[ch].field))}` : lower(label(enc[ch].field))); return; }
    }
    keep.push(i);
  });
  const counts = new Map();
  let nulls = 0;
  if (colorMap) for (const i of keep) { const v = plain(rows[i][colorF], columns[colorF]); if (v === nullLabel) nulls++; else counts.set(v, (counts.get(v) || 0) + 1); }
  let other = null;
  if (colorMap && counts.size > HUES) {
    const top = new Set([...counts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))).slice(0, HUES - 1).map(([v]) => v));
    const rest = counts.size - top.size;
    other = { top, label: `Other (${rest})` };
    const domain = [...top, other.label, ...(nulls ? [nullLabel] : [])];
    enc.color.scale = { domain, range: [...tokens.series.slice(0, HUES - 1), tokens.muted, ...(nulls ? [tokens.muted] : [])] };
  } else if (colorMap && nulls) {
    // Vega-Lite's own order for the rest (ascending, the theme's slots in turn); the null last, muted
    const asc = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
    const domain = [...counts.keys()].sort(asc);
    enc.color.scale = { domain: [...domain, nullLabel], range: [...domain.map((_v, i) => tokens.series[i % tokens.series.length]), tokens.muted] };
  }
  const datumOf = (r, i) => {
    const d = { _row: i, _id: r.id };
    for (const f of used) d[safe(f)] = plain(at(r, f), columns[f]);
    if (other && d[safe(colorF)] !== nullLabel && !other.top.has(d[safe(colorF)])) d[safe(colorF)] = other.label;
    if (yBasis) { const c = r[yBasis]; d._hollow = !!(c && typeof c === 'object' && HOLLOW.has(c.basis)); }
    return d;
  };
  for (const i of keep) drawn.push(datumOf(rows[i], i));

  // ---- the clock's time on x (kit gap 3, CONTRACT §25 addendum): the chart follows the clock as a time series does.
  // Its x domain is its rows' time, exact, or the clock's zoom window (`win`), set through two signals so a zoom swaps
  // them and never the spec; ChartView draws the clock's t on it and reports the span to the clock
  const xc = enc.x;
  let time = null;
  if (xc && xc.field && isClockTime(columns[xc.field], xc.field, timeColumn) && (xc.type || 'quantitative') === 'quantitative' && !xc.aggregate && !xc.bin && !xc.timeUnit && !Object.keys(facet).length) {
    let lo = Infinity, hi = -Infinity;
    for (const i of keep) { const v = cellValue(rows[i][xc.field]); if (isNum(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    if (hi >= lo) {
      if (hi === lo) hi = lo + 1;
      time = { extent: [lo, hi], domain: win && isNum(win[0]) && isNum(win[1]) && win[1] > win[0] ? [win[0], win[1]] : [lo, hi] };
    }
  }

  const hollow = drawn.some((d) => d._hollow);

  // ---- rename fields to their safe names, and hollow marks for estimates
  for (const u of mains) renameFields(u.encoding, safe);
  if (time) {
    const sxf = safe(xc.field);
    for (const u of mains) {
      const x = u.encoding.x;
      if (!x || x.field !== sxf || x.aggregate || x.bin) continue;
      const sc = x.scale || {};
      // a domain the author wrote stays theirs (the playhead still draws on it)
      if (sc.domain !== undefined || sc.domainMin !== undefined || sc.domainMax !== undefined) continue;
      x.scale = { ...sc, domainMin: { expr: 'dvXmin' }, domainMax: { expr: 'dvXmax' }, nice: false, zero: false };
    }
  }
  // a histogram's empty bins are bars of 0, not missing bars (PEP 0010 P2, the coverage histograms): every bin from the
  // first to the last is a datum, so its 0 is read (a hover, a check against numpy.histogram) like any other bin.
  // WHY the hover card and the click keep the encoding as written (asWritten): the rewrite is how the bins are drawn,
  // not what a bin is, and its datum is Vega-Lite's own (the bin, its end, the aggregate); read through the rewrite, x2
  // looked like a category no row has, so the card and the click never showed
  const asWritten = new Map();
  for (const u of mains) { const written = { ...u.encoding }; if (zeroBins(u, drawn)) asWritten.set(u, written); }
  for (const c of Object.values(facet)) if (c.field) c.field = safe(c.field);
  if (hollow) {
    for (const u of dotUnits) {
      u.mark = { ...(typeof u.mark === 'object' ? u.mark : { type: u.mark }), filled: true, strokeWidth: 1.5 };
      u.encoding.fillOpacity = { condition: { test: 'datum._hollow', value: 0 }, value: 0.9 };
      if (u.encoding.color && !u.encoding.stroke) u.encoding.stroke = { ...clone(u.encoding.color), legend: null };
      else if (!u.encoding.stroke) u.mark.stroke = tokens.series[0];
    }
  }
  // the bucketed count as a line (SPEC §8.5): aggregate per bucket (and colour), then impute every bucket of the axis,
  // 0 for a count (no rows that week is a true 0) or null where gaps: true (or a mean of nothing) breaks the line.
  // WHY transforms, not the encoding's impute: Vega-Lite's encoding impute cannot sit on an aggregate without a field
  if (imputed) {
    const xs = safe(imputed.x), cs = imputed.color ? safe(imputed.color) : null;
    for (const u of mains) {
      const y = u.encoding.y;
      if (!y || !y.aggregate || !['line', 'point', 'circle'].includes(markType(u.mark))) continue;
      const op = { op: imputed.op, as: '__y', ...(imputed.y ? { field: safe(imputed.y) } : {}) };
      u.transform = [...(u.transform || []), { aggregate: [op], groupby: cs ? [xs, cs] : [xs] },
        { impute: '__y', key: xs, keyvals: imputed.domain, value: imputed.gaps ? null : 0, ...(cs ? { groupby: [cs] } : {}) }];
      u.encoding.y = { field: '__y', type: 'quantitative', title: y.title, ...(y.scale ? { scale: y.scale } : {}), ...(y.axis ? { axis: y.axis } : {}) };
    }
  }
  for (const u of mains) {
    if (typeof u.mark === 'string') u.mark = { type: u.mark };
    if (u.mark && !u.mark.cursor) u.mark.cursor = 'pointer';
  }

  // ---- guides, each its own layer (docs/SPEC.md §8.8)
  const datasets = { rows: drawn };
  const back = [], front = [];
  const sx = xF ? safe(xF) : null, sy = yF ? safe(yF) : null;
  const xEnc = enc.x ? { field: sx, type: enc.x.type, scale: enc.x.scale } : null;
  const yEnc = enc.y ? { field: sy, type: enc.y.type, scale: enc.y.scale } : null;
  const facetKeys = facetFields.map(safe);
  const facetVals = facetKeys.length ? [...new Map(drawn.map((d) => [facetKeys.map((k) => d[k]).join('\u0001'), Object.fromEntries(facetKeys.map((k) => [k, d[k]]))])).values()] : [{}];
  const guideDatum = (extra) => facetVals.map((f) => ({ ...f, _guide: true, ...extra }));
  for (const [i, g] of (view.guides || []).entries()) {
    if (g.rule) {
      for (const ch of ['x', 'y']) {
        if (!isNum(g.rule[ch]) || !enc[ch]) continue;
        const name = `rule${i}${ch}`;
        datasets[name] = guideDatum({});
        back.push({ data: { name }, mark: { type: 'rule', stroke: tokens.muted, strokeDash: [5, 4], strokeWidth: 1.2 }, encoding: { [ch]: { datum: g.rule[ch], type: enc[ch].type === 'temporal' ? 'temporal' : 'quantitative' } } });
        if (g.label) {
          // WHY an x rule's label runs up its own line: rules sit close together (a floor and 1.5 x it), and a level
          // label would overprint the next rule or run off a phone's plot
          front.push({ data: { name }, mark: { type: 'text', fill: tokens.muted, fontSize: 11, ...(ch === 'y' ? { align: 'right', baseline: 'bottom', dy: -3 } : { angle: -90, align: 'right', baseline: 'bottom', dx: -4, dy: -3 }) },
            encoding: ch === 'y' ? { y: { datum: g.rule.y, type: 'quantitative' }, x: { value: 'width' }, text: { value: g.label } } : { x: { datum: g.rule.x, type: 'quantitative' }, y: { value: 0 }, text: { value: g.label } } });
        }
      }
    } else if (g.envelope && sx && sy && raw('x') && raw('y')) {
      const prop = g.envelope;
      if (!columns[prop]) { notes.push(`envelope: ${prop} is not a property`); continue; }
      const { hulls, labels, skipped } = envelopes(drawn, safe(prop), sx, sy, logOf('x'), logOf('y'), g.shape || 'hull', facetKeys);
      datasets[`env${i}`] = hulls;
      datasets[`envlabel${i}`] = labels;
      if (skipped) notes.push(`${skipped} ${lower(label(prop))} group${skipped === 1 ? '' : 's'} under 3 dots: no envelope`);
      const byColour = colorF === prop;
      // WHY a closed, filled line: Vega-Lite has no polygon mark, but a line with interpolate linear-closed draws a
      // closed path and fills it (proved in this lane: Vega 6.4 writes the path's fill and fill-opacity); so the
      // envelopes are Granta's tinted bubbles, outlined, each in its family's colour when colour is the family
      back.push({ data: { name: `env${i}` }, mark: { type: 'line', interpolate: 'linear-closed', fillOpacity: 0.1, strokeOpacity: 0.55, strokeWidth: 1, ...(byColour ? {} : { fill: tokens.muted, stroke: tokens.muted }) },
        encoding: { x: xEnc, y: yEnc, order: { field: '_o', type: 'quantitative' }, detail: { field: '_g', type: 'nominal' },
          ...(byColour ? { color: { field: safe(prop), type: 'nominal' }, fill: { field: safe(prop), type: 'nominal' } } : {}) } });
      front.push({ data: { name: `envlabel${i}` }, mark: { type: 'text', fontSize: 11, fontWeight: 600, fill: tokens.fg, opacity: 0.75, dy: -8 },
        encoding: { x: xEnc, y: yEnc, text: { field: '_g', type: 'nominal' } } });
    } else if (g.indexLine && sx && sy && raw('x') && raw('y')) {
      const line = indexLine(drawn, sx, sy, g.indexLine, rows);
      if (!line) continue;
      datasets[`idx${i}`] = facetVals.flatMap((f) => line.map((p) => ({ ...f, ...p, _guide: true })));
      datasets[`idxlabel${i}`] = facetVals.map((f) => ({ ...f, ...line[1], _guide: true }));
      back.push({ data: { name: `idx${i}` }, mark: { type: 'line', stroke: tokens.accent, strokeDash: [6, 4], strokeWidth: 1.3, opacity: 0.85 }, encoding: { x: xEnc, y: yEnc, detail: facetKeys.length ? { field: facetKeys[0], type: 'nominal' } : undefined } });
      front.push({ data: { name: `idxlabel${i}` }, mark: { type: 'text', align: 'right', dx: -4, dy: -8, fontSize: 11, fill: tokens.accent },
        encoding: { x: xEnc, y: yEnc, text: { value: g.label || `index: y / x^${g.indexLine.slope}` } } });
    }
  }
  for (const l of [...back, ...front]) if (l.encoding.detail === undefined) delete l.encoding.detail;

  // ---- the colour legend as buttons (src/legend.js): Vega's own is off; the hidden set filters every series layer
  // WHY a filter, not opacity: the y axis rescales to the series still shown, so a hidden outlier no longer flattens the
  // rest (Plotly's, Grafana's and uPlot's default); the rows, counts and status line are untouched. WHY the GHOST layer:
  // while anything is hidden it draws nothing (size 0, opacity 0) but holds every row's x and colour, so x stays put and
  // no colour moves (an implicit colour domain would shrink to the series left)
  const sc = colorF ? safe(colorF) : null;
  const legend = sc && enc.color.legend !== null ? { field: sc, title: enc.color.title || label(colorF) } : null;
  if (legend) {
    const test = `indexof(dvHidden, toString(datum[${JSON.stringify(sc)}])) < 0`;
    const held = [];
    for (const u of [...mains, ...back]) {
      const chs = ['color', 'fill', 'stroke'].filter((ch) => u.encoding[ch] && u.encoding[ch].field === sc);
      if (!chs.length && !mains.includes(u)) continue;
      for (const ch of chs) { u.encoding[ch] = { ...u.encoding[ch], legend: null }; if (!held.some(([c]) => c === ch)) held.push([ch, u.encoding[ch]]); }
      u.transform = [{ filter: test }, ...(u.transform || [])];
    }
    for (const l of front) if (l.data && /^envlabel\d+$/.test(l.data.name || '') && colorF === (view.guides || [])[Number(l.data.name.slice(8))]?.envelope) l.transform = [{ filter: `indexof(dvHidden, toString(datum._g)) < 0` }, ...(l.transform || [])];
    const xPin = enc.x && enc.x.field && !enc.x.aggregate ? { x: clone(enc.x) } : {};
    if (xPin.x) delete xPin.x.axis;
    back.unshift({ name: GHOST, transform: [{ filter: 'dvPin' }], mark: { type: 'point', size: 0, opacity: 0, filled: true },
      encoding: { ...xPin, ...Object.fromEntries(held.map(([ch, c]) => [ch, clone(c)])) } });
    const dom = enc.color.scale && enc.color.scale.domain;
    if (dom) {
      legend.names = dom.map(String);
      legend.colors = (enc.color.scale.range || []).slice();
    } else {
      // Vega-Lite's own default for a nominal domain: the drawn values, ascending; the theme's category range in order
      const asc = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
      legend.names = [...new Set(drawn.map((d) => d[sc]))].sort(asc).map(String);
      legend.colors = legend.names.map((_n, i) => tokens.series[i % tokens.series.length]);
    }
  }

  // ---- the ring around the peeked dot
  const selectable = !aggregated && !!(sx && sy) && dotUnits.length > 0;
  if (selectable) {
    const i = peekId === null ? -1 : rows.findIndex((r) => String(r.id) === peekId);
    datasets.sel = i >= 0 && keep.includes(i) ? [datumOf(rows[i], i)] : [];
    front.push({ data: { name: 'sel' }, mark: { type: 'point', size: 220, strokeWidth: 2, stroke: tokens.accent, filled: false }, encoding: { x: xEnc, y: yEnc } });
  }

  // ---- size, legend, theme
  const narrow = width < 560;
  const nFacet = (ch) => (facet[ch] ? new Set(drawn.map((d) => d[facet[ch].field])).size || 1 : 1);
  const cols = facet.facet ? facet.facet.columns || Math.min(narrow ? 2 : 4, nFacet('facet')) : nFacet('column');
  const rowsN = facet.facet ? Math.ceil(nFacet('facet') / cols) : nFacet('row');
  const faceted = facetFields.length > 0;
  // the colour legend is HTML above the plot (legend, above), so only a size / shape / opacity legend takes Vega's room
  const legendRoom = narrow || !((enc.color && !legend) || enc.size || enc.shape || enc.opacity) ? 0 : 150;
  const layer = [...back, ...mains, ...front];
  let spec, size = null;
  if (faceted) {
    const cw = Math.max(110, Math.floor((width - legendRoom - 60) / cols) - 12);
    // per row of cells: its header (~24 px) and, under the last, the x axis and its title (~44 px)
    const ch = Math.max(100, Math.floor((height - 44 - (narrow && enc.color && !legend ? 64 : 0)) / rowsN) - 34);
    // a wrapped facet (encoding.facet) takes `columns`; row and column take one header each
    const wrap = facet.facet ? (({ columns: _c, ...def }) => def)(facet.facet) : null;
    spec = { data: { name: 'rows' }, ...(layered && chart.transform ? { transform: chart.transform } : {}), facet: wrap || { ...(facet.row ? { row: facet.row } : {}), ...(facet.column ? { column: facet.column } : {}) },
      ...(wrap ? { columns: cols } : {}), spec: { width: cw, height: ch, layer }, autosize: { type: 'pad' } };
  } else {
    // WHY the chart's own transform here when it has layers: it runs before every layer's (Vega-Lite's order); it used
    // to be left out, so a field it made (a run's end) was missing in each layer (kit gap 5)
    spec = { data: { name: 'rows' }, ...(layered && chart.transform ? { transform: chart.transform } : {}), width, height, autosize: { type: 'fit', contains: 'padding' }, layer };
    size = [width, height];
  }
  if (chart.title) spec.title = chart.title;
  if (chart.resolve) spec.resolve = chart.resolve;
  // style.chrome (the dashboard's, docs/peps/0005-dashboard-cards.md §5): minimal is frameless, with a faint
  // horizontal grid for line charts only
  spec.config = theme(tokens, { narrow, chrome: view.style && view.style.chrome, grid: ['line', 'area', 'trail'].includes(mark) ? 'y' : 'none' });
  spec.padding = { left: 6, right: 10, top: 10, bottom: 6 };
  if (time) {
    // WHY the time series' padding and y gutter: a strip under a time series in a dashboard column puts each t at the
    // same x (kit gap 3); with no y axis the gutter is padding. WHY labelBound: an x label that would run past the plot's
    // end (a tick at 4.5 of a 4.57 s run) is left off, as the time series' fewer ticks leave it, instead of autosize
    // narrowing the plot by its overhang (3 px at 390 px). WHY clip: a zoom puts spans outside the plot, and autosize
    // fit would shrink the plot to hold them (to 0 px wide)
    const yAxis = mains.some((u) => u.encoding.y && u.encoding.y.axis !== null);
    spec.padding = { ...TIME_PAD, left: TIME_PAD.left + (yAxis ? 0 : GUTTER) };
    spec.config = { ...spec.config, axisY: { ...(spec.config.axisY || {}), minExtent: GUTTER }, axisX: { ...(spec.config.axisX || {}), labelFlush: true, labelBound: 0.5 } };
    for (const u of mains) if (u.mark && typeof u.mark === 'object') u.mark.clip = true;
  }
  const params = [...(legend ? [{ name: 'dvHidden', value: [...hidden] }, { name: 'dvPin', value: hidden.length > 0 }] : []),
    ...(time ? [{ name: 'dvXmin', value: time.domain[0] }, { name: 'dvXmax', value: time.domain[1] }] : [])];
  if (params.length) spec.params = params;
  // the hidden set is two signals (ChartView._applyHidden): never part of the key, so hiding never re-embeds
  const key = JSON.stringify({ ...spec, width: undefined, height: undefined, params: params.length ? `${legend ? 'legend' : ''}|${time ? 'time' : ''}` : undefined });

  // ---- what the view needs back: the hover's fields, and how an aggregate maps to its rows
  const unsafe = new Map([...names.entries()].map(([k, v]) => [v, k]));
  const SKIP = new Set(['order', 'detail', 'fillOpacity', 'stroke', 'key']);
  const channels = (u) => Object.entries(asWritten.get(u) || u.encoding).filter(([ch, c]) => c && !Array.isArray(c) && !SKIP.has(ch));
  const fields = [...new Set([...tooltip, ...mains.flatMap((u) => channels(u).map(([, c]) => unsafe.get(c.field))), ...facetFields])].filter((f) => f && columns[f]);
  // an aggregate's rows: the ones sharing its categories (and inside its bin)
  const groupKeys = [...new Set([...mains.flatMap((u) => channels(u).filter(([, c]) => c.field && !c.aggregate && !c.bin && c.type !== 'quantitative').map(([, c]) => c.field)), ...facetKeys])];
  const binFields = [...new Set(mains.flatMap((u) => channels(u).filter(([, c]) => c.bin && c.field).map(([, c]) => c.field)))];
  const binKey = (d, b) => Object.keys(d).find((k) => k.startsWith('bin_') && k.endsWith(`_${b}`));
  const recordsOf = (d, list) => {
    if (!aggregated) return null;
    const keys = groupKeys.filter((k) => d[k] !== undefined);
    return keep.map((i) => list[i]).filter((r) => keys.every((k) => {
      const f = unsafe.get(k);
      let v = plain(at(r, f), columns[f]);
      if (other && f === colorF && !other.top.has(v)) v = other.label;
      // a bucketed date comes back from Vega-Lite as a time: compare it as one
      return String(v) === String(d[k]);
    }) && binFields.every((b) => {
      const k = binKey(d, b);
      const lo = k ? d[k] : null, hi = k ? d[`${k}_end`] : null;
      const v = cellValue(r[unsafe.get(b)]);
      return !isNum(lo) || (isNum(v) && v >= lo && v < hi);
    }));
  };
  const datumFields = (d) => {
    const out = [];
    for (const [, c] of channels(main)) {
      if (c.aggregate === 'count' && !c.field) { const k = Object.keys(d).find((x) => x.startsWith('__count')); if (k) out.push(['Rows', d[k], null]); continue; }
      if (!c.field) continue;
      const f = unsafe.get(c.field);
      const k = c.aggregate ? `${c.aggregate}_${c.field}` : c.bin ? binKey(d, c.field) : c.field;
      if (!k || d[k] === undefined) continue;
      if (c.bin) out.push([c.title || label(f), `${fmtNum(d[k], undefined, numOpts(columns[f]))}–${fmtNum(d[`${k}_end`], undefined, numOpts(columns[f]))}`, null]);
      else out.push([c.title || label(f), d[k], columns[f] ? { ...columns[f], id: f } : null]);
    }
    for (const k of facetKeys) { const f = unsafe.get(k); out.push([label(f), d[k], columns[f] ? { ...columns[f], id: f } : null]); }
    return out;
  };
  const ax = (ch) => (enc[ch] && enc[ch].field ? label(enc[ch].field) : ch);
  return {
    spec, datasets, key, size,
    meta: {
      mark, encoding: enc, explicitScale, x: xF, y: yF, drawn: drawn.length, dropped, droppedWhy: [...why].join(' or '),
      aggregated, notes, fields, selectable, recordsOf, datumFields, datumOf: (r, i) => [datumOf(r, i)], legend, time,
      aria: `${mark} chart of ${ax('y')} against ${ax('x')}: ${drawn.length} rows${dropped ? `, ${dropped} not drawn` : ''}`,
    },
  };
}

/** A cell as the chart reads it: the value; a list joined; an empty one labelled ("No form"), never "null". */
function plain(cell, col) {
  const v = cellValue(cell);
  const type = col ? col.type : null;
  if (type === 'number') return isNum(v) ? v : null;
  if (type === 'date') return isEmpty(v) ? null : v;
  if (isEmpty(v)) return col ? groupLabel({ [col.id]: col }, col.id, null) : null;
  if (Array.isArray(v)) return v.join(', ');
  return col && col.labels && col.labels[v] !== undefined ? String(col.labels[v]) : typeof v === 'boolean' ? String(v) : v;
}

function renameFields(enc, safe) {
  for (const c of Object.values(enc)) {
    for (const d of Array.isArray(c) ? c : [c]) {
      if (d && d.field) d.field = safe(d.field);
      if (d && d.condition && d.condition.field) d.condition.field = safe(d.condition.field);
      if (d && d.sort && typeof d.sort === 'object' && !Array.isArray(d.sort) && d.sort.field) d.sort = { ...d.sort, field: safe(d.sort.field) };
    }
  }
}

/** A colors entry as a colour (kit gap 6; families.colors' rule in clock.js): 1-8 a series slot, 0 or `muted` the muted
    token, `var(--data-…)` that token resolved, any other text a CSS colour as written. */
function mapColor(pick, tokens) {
  if (pick === undefined || pick === null || pick === 0 || pick === '0' || pick === 'muted') return tokens.muted;
  const n = typeof pick === 'number' ? pick : /^\d+$/.test(String(pick)) ? Number(pick) : null;
  if (n !== null) return tokens.series[(n - 1 + tokens.series.length) % tokens.series.length];
  const m = /^var\(\s*--([\w-]+)\s*\)$/.exec(String(pick));
  if (m) return (tokens.css && tokens.css[m[1]]) || tokens.muted;
  return String(pick);
}

/** One envelope per value of a property, around its dots, computed where the axes are drawn (log space on log
    axes): a convex hull padded 6 % from its centre (Granta's "bubble"), or the 2-sigma covariance ellipse. */
function envelopes(data, key, x, y, logx, logy, shape, facetKeys) {
  const fx = logx ? Math.log10 : (v) => v, fy = logy ? Math.log10 : (v) => v;
  const gx = logx ? (v) => 10 ** v : (v) => v, gy = logy ? (v) => 10 ** v : (v) => v;
  const groups = new Map();
  for (const d of data) {
    const k = [...facetKeys.map((f) => d[f]), d[key]];
    const id = JSON.stringify(k);
    if (!groups.has(id)) groups.set(id, { k, pts: [] });
    groups.get(id).pts.push([fx(d[x]), fy(d[y])]);
  }
  const hulls = [], labels = [];
  let skipped = 0;
  for (const { k, pts } of groups.values()) {
    if (pts.length < 3) { skipped++; continue; }
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    let ring;
    if (shape === 'ellipse') {
      let sxx = 0, syy = 0, sxy = 0;
      for (const [a, b] of pts) { sxx += (a - cx) ** 2; syy += (b - cy) ** 2; sxy += (a - cx) * (b - cy); }
      sxx /= pts.length; syy /= pts.length; sxy /= pts.length;
      const tr = sxx + syy, det = sxx * syy - sxy * sxy, l1 = tr / 2 + Math.sqrt(Math.max(0, tr * tr / 4 - det)), l2 = Math.max(1e-9, tr - l1);
      const th = Math.atan2(l1 - sxx, sxy || 1e-12);
      ring = Array.from({ length: 48 }, (_v, i) => {
        const t = (2 * Math.PI * i) / 48, ex = 2 * Math.sqrt(l1) * Math.cos(t), ey = 2 * Math.sqrt(l2) * Math.sin(t);
        return [cx + ex * Math.cos(th) - ey * Math.sin(th), cy + ex * Math.sin(th) + ey * Math.cos(th)];
      });
    } else {
      ring = convexHull(pts).map(([a, b]) => [cx + (a - cx) * 1.06, cy + (b - cy) * 1.06]);
    }
    const facetPart = Object.fromEntries(facetKeys.map((f, j) => [f, k[j]]));
    const g = k[k.length - 1];
    ring.forEach(([a, b], o) => hulls.push({ ...facetPart, [x]: gx(a), [y]: gy(b), [key]: g, _o: o, _g: JSON.stringify(k), _guide: true }));
    const top = ring.reduce((m, p) => (p[1] > m[1] ? p : m), ring[0]);
    labels.push({ ...facetPart, [x]: gx(top[0]), [y]: gy(top[1]), _g: g, _guide: true });
  }
  return { hulls, labels, skipped };
}

/** Andrew's monotone chain. */
function convexHull(points) {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (const q of p.reverse()) { while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** Ashby's performance index: on log-log axes, y = C·x^slope. `through`: 'median' (C is the median of y / x^slope
    over the drawn dots), a row id (through that row), or C itself. Two points span the drawn x range. */
function indexLine(data, x, y, { slope = 1, through = 'median' }, rows) {
  let C;
  if (isNum(through)) C = through;
  else if (through && through !== 'median') {
    const d = data.find((p) => String(rows[p._row].id) === String(through));
    C = d ? d[y] / d[x] ** slope : null;
  } else C = median(data.map((d) => d[y] / d[x] ** slope).filter((v) => v > 0));
  if (!isNum(C) || !data.length) return null;
  let lo = Infinity, hi = -Infinity;
  for (const d of data) { if (d[x] < lo) lo = d[x]; if (d[x] > hi) hi = d[x]; }
  return [{ [x]: lo, [y]: C * lo ** slope }, { [x]: hi, [y]: C * hi ** slope }];
}
