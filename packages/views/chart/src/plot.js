/* timeseries.interactive: true — the Foxglove/Rerun plot (docs/peps/0005-dashboard-cards.md §2b): pan, zoom (both
   axes, x, y, to a box), double-click reset, a click moves the time cursor, a legend that hides a series on click and
   isolates one on a double-click or Alt + click (the core's SeriesLegend, every chart's), a "?" popover listing the
   controls, and a maximise button (Esc restores).

   Zach, 2026-10-26: "the simple chart is fine, but also support a Foxglove/Rerun-style interactive plot"; "we 100%
   don't need to build any of these views from scratch." STOCK PART: uPlot 1.6.32 (MIT): the canvas, scales, axes,
   series paths (its own per-pixel decimation), uPlot.join for alignment and setSelect for the box. Ours: the gestures
   (uPlot's own drag is a left-button box only), the clock wiring and the HTML legend, help and maximise.
   WHY uPlot and not Vega-Lite here (packages/views/chart/README.md has the numbers): a pan redraw of 4 × 10,000 points
   is about 1 ms in uPlot against about 58 ms in Vega, and Vega-Lite binds one interval per scale, so per-axis zoom on
   modifiers cannot be declared. It is the dense-time-series exception to PEP 0001's one chart engine per page (as
   React Flow is for graphs), and it loads only when a card says interactive: true (this file is a lazy chunk).

   Still a card on the dashboard clock: the [data-playhead] follows clock.t by a transform (never a redraw), a click
   seeks, hover sets clock.hover and every time series shows the rule, the x range is clock.window both ways. */

import uPlot from 'uplot';
import { cellValue, esc, fmtNum, numOpts, clockFor, fmtTime, seriesColor, SeriesLegend } from '@data-ui/core';
import { longRows, seriesStyles, nearest } from './series.js';
import { toneColor, unitOf } from './overlay.js';
import { annotationRows, labelRows } from './timeseries.js';
import { CONTROLS, wheelAction, wheelDelta, zoomFactor, zoomRange, panRange, valueAt, sameRange, tablesOf } from './plotkit.js';
import { guidesFrom } from '../../../core/src/guides.js';

const DASH = [5, 4];
const CLICK = 3;   // px: a press that moves less than this is a click (seek), not a drag
const BOX = 6;     // px: a box shorter than this zooms x alone
const DISTR = { linear: 1, log: 3, symlog: 4 };
const ICON_MAX = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';
const ICON_MIN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/></svg>';
const numFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 });
const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumSignificantDigits: 3 });
const tick = (v) => (v === null || v === undefined ? '' : Math.abs(v) >= 1000 ? compact.format(v) : numFmt.format(v));

/** The view's rows and entry -> the series (series.js naming and colours), the aligned uPlot data and its x span. */
export function plotSeries(input) {
  const { rows, view, columns, tokens } = input;
  const ts = view.timeseries || {};
  const x = ts.x || 't';
  const ys = (Array.isArray(ts.y) ? ts.y : [ts.y]).filter((f) => f && columns[f]);
  const temporal = !!(columns[x] && columns[x].type === 'date');
  const label = (f) => (columns[f] ? columns[f].label : f);
  const time = temporal ? (v) => (v === null || v === undefined || v === '' ? null : Date.parse(v)) : (v) => v;
  const { list } = longRows(rows, { x, y: ys, series: ts.series && columns[ts.series] ? ts.series : null }, { read: (row, f) => cellValue(row[f]), label, time });
  if (ts.scale === 'log') for (const s of list) s.points = s.points.filter((p) => p.value > 0);
  const styles = seriesStyles(list.filter((s) => s.points.length), { palette: view.style && view.style.palette, dash: ts.dash, slot: (n) => seriesColor(n, input), muted: tokens.muted });
  const data = styles.length ? uPlot.join(tablesOf(styles)) : [[]];
  const xs = data[0];
  const extent = xs.length ? [xs[0], xs[xs.length - 1] === xs[0] ? xs[0] + 1 : xs[xs.length - 1]] : [0, 1];
  return { styles, data, extent, temporal, ys, unit: ts.unit !== undefined ? ts.unit : ys.length === 1 ? unitOf(columns[ys[0]]) : '' };
}

let plots = 0;   // uPlot instances made on this page (each card's count is in data-plots, for the "never re-created" check)

export class PlotView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.u = null;
    this._key = null;
    this._yLock = null;    // [min, max] once the reader pans or zooms y (egui_plot's rule: a user zoom turns auto-fit off)
    this._following = false;
    el.innerHTML = `<div class="dv-plot">
        <div class="dv-timeseries-head dv-plot-head">
          <div class="dv-timeseries-legend dv-plot-legend" role="group" aria-label="Series"></div>
          <span class="dv-timeseries-unit"></span>
          <span class="dv-plot-tools">
            <button type="button" class="dv-plot-btn" data-plot-help aria-label="Plot controls" aria-expanded="false" title="Controls">?</button>
            <button type="button" class="dv-plot-btn" data-plot-max aria-label="Maximise" aria-pressed="false" title="Maximise">${ICON_MAX}</button>
          </span>
        </div>
        <div class="dv-plot-area" role="img">
          <div class="dv-plot-canvas"></div>
          <div class="dv-timeseries-hover" data-hover hidden><div class="dv-timeseries-read"></div></div>
          <div class="dv-plot-playhead" data-playhead hidden></div>
        </div>
        <div class="dv-plot-help" popover="auto" role="dialog" aria-label="Plot controls">
          <div class="dv-plot-help-h">Time series view</div>
          <dl>${CONTROLS.map(([what, how], i) => `${i === 8 ? '<hr>' : ''}<div><dt>${esc(what)}</dt><dd>${how.split(' or ').map((alt) => alt.split(' + ').map((k) => `<kbd>${esc(k)}</kbd>`).join('<span>+</span>')).join('<span>or</span>')}</dd></div>`).join('')}</dl>
        </div>
      </div>`;
    this.$ = (sel) => el.querySelector(sel);
    this.box = this.$('.dv-plot');
    this.area = this.$('.dv-plot-area');
    this.help = this.$('.dv-plot-help');
    this.legend = new SeriesLegend(this.$('.dv-plot-legend'), { host, keyClass: 'dv-timeseries-key dv-plot-key', onChange: () => this._shown() });
    this.clock = clockFor(host.element || el);
    this._onTime = () => this._place();
    this._onHover = () => this._crosshair();
    this._onState = () => this._follow();
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('hover', this._onHover);
    this.clock.addEventListener('state', this._onState);
    this._chrome();
    this._resize = new ResizeObserver(() => this._fit());
    this._resize.observe(this.area);
  }

  destroy() {
    this._dead = true;
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('hover', this._onHover);
    this.clock.removeEventListener('state', this._onState);
    this._resize.disconnect();
    document.removeEventListener('keydown', this._onKey);
    cancelAnimationFrame(this._raf);
    this.legend.destroy();
    if (this.u) this.u.destroy();
    this.u = null;
    delete this.el.uplot;
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    if (this._dead) return;
    this.legend.sync(input);
    try { this._draw(); } catch (err) { this._fail(err); }
  }

  _draw() {
    const input = this.input;
    const { view, tokens } = input;
    const ts = view.timeseries || {};
    const out = plotSeries(input);
    this._meta = out;
    // rules and bands from a property (sim2real gap #6; core guides.js), read from the rows, per series
    const xcol = ts.x || 't';
    const read = (r, c) => { const v = cellValue(r[c]); return c === xcol && out.temporal ? (v === null || v === undefined || v === '' ? null : Date.parse(v)) : v; };
    this._prop = guidesFrom(input.rows, { rules: ts.rules, bands: ts.bands }, { x: xcol, series: ts.series && input.columns[ts.series] ? ts.series : null, read, hidden: this.legend.hidden });
    const gv = [...this._prop.rules.flatMap((g) => g.points.map((q) => q[1])), ...this._prop.bands.flatMap((g) => [...g.lo, ...g.hi].map((q) => q[1]))];
    this._propRange = gv.length ? [Math.min(...gv), Math.max(...gv)] : null;
    // annotations as written or from rows (kit gap 2): the Vega card's own reading, drawn on uPlot's canvas below
    this._marks = annotationRows(input);
    this.area.style.height = ts.height ? `${ts.height}px` : '';
    if (!out.temporal) this.clock.extent(out.extent[0], out.extent[1]);
    const minimal = !view.style || view.style.chrome !== 'full';
    const key = JSON.stringify({ s: out.styles.map((s) => [s.name, s.color, s.dashed]), t: [tokens.muted, tokens.rule, tokens.fg, tokens.border, tokens.font, tokens.good, tokens.warn, tokens.bad],
      minimal, scale: ts.scale, mark: ts.mark, temporal: out.temporal, rules: ts.rules, bands: ts.bands, annotations: ts.annotations });
    if (key === this._key && this.u) {
      // the same plot with new rows (a filter, a refresh): data only; the reader's zoom stays
      this.u.setData(out.data, false);
      this._applyX();
    } else {
      if (this.u) this.u.destroy();
      this.u = new uPlot(this._opts(out, ts, tokens, minimal), out.data, this.$('.dv-plot-canvas'));
      this._key = key;
      this.el.uplot = this.u;
      this.el.dataset.plots = String(++plots);
      this._gestures();
      this._applyX();
    }
    this._legend(ts);
    this._shown();
    this.$('.dv-timeseries-unit').textContent = out.unit || '';
    this.area.setAttribute('aria-label', `interactive time series of ${out.ys.map((f) => (input.columns[f] ? input.columns[f].label : f)).join(', ')}: ${out.styles.length} series`);
    this.host.setStatus(`<span class="dv-chart-status">${out.styles.length} series · ${out.data[0].length} samples</span>`);
  }

  _fail(err) {
    if (this._dead) return;
    this._key = null;
    this.$('.dv-plot-canvas').innerHTML = `<p class="dv-err dv-chart-err">This time series could not be drawn: ${esc(err && err.message ? err.message : err)}</p>`;
    this.host.setStatus('');
  }

  /** uPlot's options: Tremor's look under style.chrome minimal (no axis lines, ticks or x grid; a faint y grid). */
  _opts(out, ts, t, minimal) {
    const font = `11px ${t.font || 'system-ui, sans-serif'}`;
    const distr = DISTR[ts.scale] || 1;
    const { width, height } = this._size();
    const axis = { stroke: t.muted, font, ticks: { show: !minimal, stroke: t.border, width: 1, size: 4 }, border: { show: !minimal, stroke: t.border, width: 1 }, gap: 6 };
    const step = ts.mark === 'step' ? uPlot.paths.stepped({ align: 1 }) : null;
    const fill = (c) => c.replace(/^rgb\((.*)\)$/, 'rgba($1, 0.1)').replace(/^#([0-9a-f]{6})$/i, (_m, h) => `#${h}1a`);
    return {
      width, height,
      ...(out.temporal ? { ms: 1 } : {}),
      padding: [10, 12, 0, 2],
      legend: { show: false },
      // WHY no uPlot cursor: the crosshair is the dashboard's (clock.hover), drawn by every time series the same way
      cursor: { show: false, drag: { x: false, y: false, setScale: false } },
      select: { show: true, over: true },
      scales: {
        x: { time: out.temporal, auto: false, range: (_u, a, b) => [a, b] },
        y: {
          distr, ...(distr === 3 ? { log: 10 } : {}), ...(distr === 4 ? { asinh: 1 } : {}),
          auto: () => !this._yLock,
          range: (_u, a, b) => {
            if (this._yLock) return this._yLock.slice();
            // a limit from a property is part of what y shows (a floor far below the data is the point of drawing it)
            if (this._propRange && a !== null && b !== null) { a = Math.min(a, this._propRange[0]); b = Math.max(b, this._propRange[1]); }
            if (a === null || b === null || !(b >= a)) return [0, 1];
            return distr === 3 ? uPlot.rangeLog(a, b, 10, false) : distr === 4 ? uPlot.rangeAsinh(a, b, 10, false) : uPlot.rangeNum(a, b, 0.1, true);
          },
        },
      },
      axes: [
        { ...axis, grid: { show: !minimal, stroke: t.rule, width: 1 }, space: 70,
          ...(out.temporal ? {} : { values: (_u, splits) => splits.map((v) => (v === null ? '' : `${tick(v)} s`)) }) },
        { ...axis, grid: { show: true, stroke: t.rule, width: 1 }, space: 36, values: (_u, splits) => splits.map(tick),
          size: (_u, values) => (values ? Math.ceil(Math.max(2, ...values.map((v) => String(v).length)) * 6.6 + 12) : 40) },
      ],
      series: [{}, ...out.styles.map((s) => ({
        label: s.name, show: this.legend.shows(s.name), stroke: s.color, width: 1.5, spanGaps: true, points: { show: false },
        ...(s.dashed ? { dash: DASH } : {}), ...(step ? { paths: step } : {}), ...(ts.mark === 'area' ? { fill: fill(s.color) } : {}),
      }))],
      hooks: {
        drawAxes: [(u) => this._guides(u, ts, t, false)],
        draw: [(u) => this._guides(u, ts, t, true)],
        setScale: [(u, key) => { if (key === 'x') this._xChanged(); }],
        setSize: [() => { this._measure(); this._place(); this._crosshair(); }],
      },
    };
  }

  /** Rules, bands and annotations (PEP 0005 §2b) on uPlot's canvas: shapes behind the lines, labels in front. */
  _guides(u, ts, t, front) {
    const { ctx, bbox } = u;
    const pr = uPlot.pxRatio;
    ctx.save();
    ctx.beginPath();
    ctx.rect(bbox.left, bbox.top, bbox.width, bbox.height);
    ctx.clip();
    ctx.font = `${10 * pr}px ${t.font || 'system-ui, sans-serif'}`;
    const X = (v) => u.valToPos(v, 'x', true), Y = (v) => u.valToPos(v, 'y', true);
    for (const b of ts.bands || []) {
      if (Array.isArray(b.y) && !b.y.every((v) => typeof v === 'number')) continue;   // a property's band: below
      const c = toneColor(b.tone || 'muted', t);
      const r = Array.isArray(b.y) ? [bbox.left, Math.min(Y(b.y[0]), Y(b.y[1])), bbox.width, Math.abs(Y(b.y[0]) - Y(b.y[1]))]
        : Array.isArray(b.x) ? [Math.min(X(b.x[0]), X(b.x[1])), bbox.top, Math.abs(X(b.x[1]) - X(b.x[0])), bbox.height] : null;
      if (!r) continue;
      if (!front) { ctx.globalAlpha = 0.09; ctx.fillStyle = c; ctx.fillRect(...r); ctx.globalAlpha = 1; }
      else if (b.label) { ctx.fillStyle = c; ctx.textBaseline = 'top'; ctx.fillText(b.label, r[0] + 4 * pr, r[1] + 3 * pr); }
    }
    // rules and bands from a property: step lines through their points (a constant spans the data's x)
    const P = this._prop || { rules: [], bands: [] };
    const stepTo = (pts, first) => pts.forEach(([x, v], i) => { if (!i) { if (first) ctx.moveTo(X(x), Y(v)); else ctx.lineTo(X(x), Y(v)); } else { ctx.lineTo(X(x), Y(pts[i - 1][1])); ctx.lineTo(X(x), Y(v)); } });
    for (const g of P.bands) {
      if (front) continue;
      ctx.beginPath();
      stepTo(g.hi, true);
      const back = [...g.lo].reverse();
      back.forEach(([x, v], i) => { ctx.lineTo(X(x), Y(v)); if (i + 1 < back.length) ctx.lineTo(X(x), Y(back[i + 1][1])); });
      ctx.closePath();
      ctx.globalAlpha = 0.09; ctx.fillStyle = toneColor(g.tone || 'muted', t); ctx.fill(); ctx.globalAlpha = 1;
    }
    for (const g of P.rules) {
      const c = toneColor(g.tone || 'muted', t);
      if (!front) { ctx.strokeStyle = c; ctx.lineWidth = pr; ctx.setLineDash([3 * pr, 3 * pr]); ctx.beginPath(); stepTo(g.points, true); ctx.stroke(); ctx.setLineDash([]); }
      else if (g.label) { const [x, v] = g.points[g.points.length - 1]; ctx.fillStyle = c; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillText(g.label, Math.min(X(x), bbox.left + bbox.width) - 2 * pr, Y(v) - 3 * pr); ctx.textAlign = 'left'; }
    }
    for (const r of ts.rules || []) {
      if (typeof r.y !== 'number') continue;
      const c = toneColor(r.tone || 'muted', t), y = Y(r.y);
      if (!front) { ctx.strokeStyle = c; ctx.lineWidth = pr; ctx.setLineDash([3 * pr, 3 * pr]); ctx.beginPath(); ctx.moveTo(bbox.left, y); ctx.lineTo(bbox.left + bbox.width, y); ctx.stroke(); ctx.setLineDash([]); }
      else if (r.label) { ctx.fillStyle = c; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillText(r.label, bbox.left + bbox.width - 2 * pr, y - 3 * pr); ctx.textAlign = 'left'; }
    }
    // annotations (kit gaps 2, 7): a rule per mark, the labels staggered so none overlaps another (labelRows)
    const marks = this._marks || [];
    const where = front && marks.length ? labelRows(marks, { domain: [u.scales.x.min, u.scales.x.max], width: bbox.width / pr, measure: (text) => ctx.measureText(text).width / pr }) : null;
    marks.forEach((a, i) => {
      const x = X(a.x), c = toneColor(a.tone || 'muted', t);
      if (!front) { ctx.strokeStyle = c; ctx.globalAlpha = 0.6; ctx.lineWidth = pr; ctx.beginPath(); ctx.moveTo(x, bbox.top); ctx.lineTo(x, bbox.top + bbox.height); ctx.stroke(); ctx.globalAlpha = 1; }
      else if (a.label && where[i].row !== null) {
        const right = where[i].align === 'right';
        ctx.fillStyle = c; ctx.textBaseline = 'top'; ctx.textAlign = right ? 'right' : 'left';
        ctx.fillText(a.label, x + (right ? -4 : 4) * pr, bbox.top + (2 + where[i].row * 13) * pr);
        ctx.textAlign = 'left';
      }
    });
    ctx.restore();
  }

  _size() {
    return { width: Math.max(200, Math.floor(this.area.clientWidth || this.el.clientWidth || 640)), height: Math.max(100, Math.floor(this.area.clientHeight || 220)) };
  }

  _fit() {
    if (!this.u) return;
    const { width, height } = this._size();
    if (width !== this.u.width || height !== this.u.height) this.u.setSize({ width, height });
  }

  /** Where uPlot's plot rectangle (.u-over) sits in the area: measured after a draw or resize, never per tick. */
  _measure() {
    if (!this.u) return;
    const a = this.area.getBoundingClientRect(), o = this.u.over.getBoundingClientRect();
    this._ox = o.left - a.left;
    this._oy = o.top - a.top;
    this._oh = o.height;
  }

  // ---- the x range and the clock's window

  _full() { return this._meta.extent; }

  /** Take the clock's window (or the data's span) as x. */
  _applyX() {
    const w = this._meta.temporal ? null : this.clock.window;
    const want = w || this._full();
    this._following = true;
    if (!sameRange([this.u.scales.x.min, this.u.scales.x.max], want)) this.u.setScale('x', { min: want[0], max: want[1] });
    this._following = false;
    this._measure();
    this._place();
    this._crosshair();
  }

  _follow() {
    if (!this.u || !this._meta || this._meta.temporal) return;
    const w = this.clock.window || this._full();
    if (!sameRange([this.u.scales.x.min, this.u.scales.x.max], w)) this._applyX();
  }

  _xChanged() {
    this._place();
    this._crosshair();
    if (this._following || this._meta.temporal) return;
    // a pan or zoom here is the dashboard's window: every time series follows (one write per frame while dragging)
    cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(() => {
      if (!this.u) return;
      const x = [this.u.scales.x.min, this.u.scales.x.max];
      this.clock.setWindow(sameRange(x, this._full()) ? null : x);
    });
  }

  /** Set x (and y, when given) from a gesture. y given locks it; x alone keeps y where it is (a user zoom ends auto-fit). */
  _view(x, y) {
    const u = this.u;
    this._yLock = y ? y.slice() : [u.scales.y.min, u.scales.y.max];
    u.batch(() => {
      if (x) u.setScale('x', { min: x[0], max: x[1] });
      u.setScale('y', { min: this._yLock[0], max: this._yLock[1] });
    });
  }

  _reset() {
    this._yLock = null;
    this.u.batch(() => {
      const [a, b] = this._full();
      this._following = true;
      this.u.setScale('x', { min: a, max: b });
      this._following = false;
      this.u.setScale('y', { min: null, max: null });
    });
    if (!this._meta.temporal) this.clock.setWindow(null);
  }

  // ---- overlays: the playhead and the shared crosshair, positioned through uPlot's own scale

  _place() {
    const ph = this.$('[data-playhead]');
    if (!this.u || !this._meta || this._meta.temporal || this._ox === undefined) { ph.hidden = true; return; }
    const t = this.clock.t, { min, max } = this.u.scales.x;
    if (!(t >= min && t <= max)) { ph.hidden = true; return; }
    ph.hidden = false;
    ph.style.height = `${this._oh}px`;
    ph.style.transform = `translate(${this._ox + this.u.valToPos(t, 'x') - 0.5}px, ${this._oy}px)`;
  }

  _crosshair() {
    const rule = this.$('[data-hover]');
    const m = this._meta, t = this.clock.hover;
    if (!this.u || !m || m.temporal || t === null || this._ox === undefined) { rule.hidden = true; return; }
    const { min, max } = this.u.scales.x;
    if (!(t >= min && t <= max)) { rule.hidden = true; return; }
    const { columns, view } = this.input;
    const style = view.style || {};
    const lines = m.styles.map((s, i) => {
      if (!this.u.series[i + 1].show) return '';
      const p = nearest(s.points, t);
      const col = columns[s.column] || {};
      const v = p ? p.value : null;
      const text = v === null ? '—' : fmtNum(v, col.decimals, numOpts(style.numbers, col));
      return `<div class="dv-timeseries-line" data-series="${esc(s.name)}"><i style="--dv-ts-c:${esc(s.color)}"></i><span>${esc(s.name)}</span><b${v === null ? ' title="no sample at this t"' : ` title="${esc(String(v))}"`}>${esc(text)}</b></div>`;
    }).join('');
    const read = this.$('.dv-timeseries-read');
    read.innerHTML = `<div class="dv-timeseries-t">${esc(fmtTime(t))}${m.unit ? ` · ${esc(m.unit)}` : ''}</div>${lines}`;
    rule.hidden = false;
    const x = this._ox + this.u.valToPos(t, 'x');
    rule.style.height = `${this._oh}px`;
    rule.style.transform = `translate(${x - 0.5}px, ${this._oy}px)`;
    read.classList.toggle('dv-timeseries-left', x + 12 + read.offsetWidth > this.area.clientWidth);
  }

  // ---- the legend: a click hides or shows, a double-click or Alt + click isolates (Rerun's; src/legend.js)

  _legend(ts) {
    const m = this._meta;
    this.legend.draw(ts.legend === 'none' ? [] : m.styles.map((s) => ({ name: s.name, swatch: `<i class="${s.dashed ? 'dv-timeseries-dash' : ''}" style="--dv-ts-c:${esc(s.color)}"></i>` })));
  }

  /** Each series shown as the legend says. WHY setSeries: uPlot re-ranges y over the series still shown (unless the
      reader zoomed y, _yLock), so a hidden outlier no longer flattens the rest; x is the clock's and stays. */
  _shown() {
    const u = this.u;
    if (!u || !this._meta) return;
    u.batch(() => this._meta.styles.forEach((s, k) => { const on = this.legend.shows(s.name); if (u.series[k + 1] && u.series[k + 1].show !== on) u.setSeries(k + 1, { show: on }); }));
    this._crosshair();
  }

  // ---- the head's buttons and keys (wired once)

  _chrome() {
    const helpBtn = this.$('[data-plot-help]');
    helpBtn.addEventListener('click', () => this.help.togglePopover());
    this.help.addEventListener('beforetoggle', (e) => {
      if (e.newState !== 'open') return;
      // under the button, right-aligned with it, kept inside the viewport (the popover is in the top layer: fixed px)
      const r = helpBtn.getBoundingClientRect();
      this.help.style.visibility = 'hidden';
      requestAnimationFrame(() => {
        const w = this.help.offsetWidth, h = this.help.offsetHeight;
        const left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w));
        const top = r.bottom + 6 + h > innerHeight - 8 ? Math.max(8, r.top - 6 - h) : r.bottom + 6;
        this.help.style.left = `${left}px`;
        this.help.style.top = `${top}px`;
        this.help.style.visibility = '';
      });
    });
    this.help.addEventListener('toggle', (e) => {
      this._helpOpen = e.newState === 'open';
      helpBtn.setAttribute('aria-expanded', String(this._helpOpen));
    });
    this.$('[data-plot-max]').addEventListener('click', () => this._maximise(!this._max));
    // WHY Esc only while maximised and the help is closed: Esc on an open help closes the help (the popover's own rule)
    this._onKey = (e) => { if (e.key === 'Escape' && this._max && !this._helpOpen) { e.preventDefault(); this._maximise(false); } };
  }

  /** Fill the viewport (the top layer, so no ancestor's overflow or transform clips it); Esc or the button restores. */
  _maximise(on) {
    if (on === !!this._max) return;
    this._max = on;
    const btn = this.$('[data-plot-max]');
    if (on) {
      this.box.setAttribute('popover', 'manual');
      this.box.showPopover();
      document.addEventListener('keydown', this._onKey);
    } else {
      if (this.box.matches(':popover-open')) this.box.hidePopover();
      this.box.removeAttribute('popover');
      document.removeEventListener('keydown', this._onKey);
    }
    btn.setAttribute('aria-pressed', String(on));
    btn.setAttribute('aria-label', on ? 'Restore (Esc)' : 'Maximise');
    btn.title = on ? 'Restore (Esc)' : 'Maximise';
    btn.innerHTML = on ? ICON_MIN : ICON_MAX;
    this._fit();
  }

  // ---- gestures on uPlot's plot rectangle (wired per plot: .u-over is the plot's own)

  _gestures() {
    const u = this.u, over = u.over;
    const at = (e) => { const r = over.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height }; };
    const distrY = () => u.scales.y.distr || 1;
    let press = null;
    over.addEventListener('contextmenu', (e) => e.preventDefault());
    over.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 && e.button !== 2) return;
      const p = at(e);
      press = { ...p, box: e.button === 2 || e.shiftKey, moved: false, x0: [u.scales.x.min, u.scales.x.max], y0: [u.scales.y.min, u.scales.y.max] };
      over.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    over.addEventListener('pointermove', (e) => {
      const p = at(e);
      if (!press) {
        const inside = p.x >= 0 && p.x <= p.w && p.y >= 0 && p.y <= p.h;
        if (!this._meta.temporal) this.clock.setHover(inside ? u.posToVal(p.x, 'x') : null);
        return;
      }
      const dx = p.x - press.x, dy = p.y - press.y;
      if (!press.moved && Math.hypot(dx, dy) < CLICK) return;
      press.moved = true;
      if (press.box) {
        const l = Math.max(0, Math.min(press.x, p.x)), r = Math.min(p.w, Math.max(press.x, p.x));
        const tall = Math.abs(dy) >= BOX;
        const t = tall ? Math.max(0, Math.min(press.y, p.y)) : 0, b = tall ? Math.min(p.h, Math.max(press.y, p.y)) : p.h;
        u.setSelect({ left: l, top: t, width: r - l, height: b - t }, false);
      } else {
        // pan: the data under the pointer stays under it, on both axes (Rerun's drag)
        this._view(panRange(press.x0, -dx / p.w), panRange(press.y0, dy / p.h, distrY()));
      }
    });
    const end = (e) => {
      if (!press) return;
      const s = press;
      press = null;
      if (!s.moved) {
        if (e.type === 'pointerup' && e.button === 0 && !this._meta.temporal) this.clock.seek(u.posToVal(s.x, 'x'));
        return;
      }
      if (!s.box) return;
      const sel = { ...u.select };
      u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
      if (e.type !== 'pointerup' || sel.width < 2) return;
      const x = [u.posToVal(sel.left, 'x'), u.posToVal(sel.left + sel.width, 'x')];
      const tall = sel.height < u.over.clientHeight - 0.5;
      this._view(x, tall ? [u.posToVal(sel.top + sel.height, 'y'), u.posToVal(sel.top, 'y')] : null);
    };
    over.addEventListener('pointerup', end);
    over.addEventListener('pointercancel', end);
    over.addEventListener('pointerleave', () => { if (!press && !this._meta.temporal) this.clock.setHover(null); });
    over.addEventListener('dblclick', (e) => { e.preventDefault(); this._reset(); });
    over.addEventListener('wheel', (e) => {
      const act = wheelAction(e);
      if (!act) return;   // a plain wheel scrolls the page, as every card on it does
      e.preventDefault();
      const p = at(e), d = wheelDelta(e);
      const x = [u.scales.x.min, u.scales.x.max], y = [u.scales.y.min, u.scales.y.max];
      if (act === 'pan-x') { this._view(panRange(x, d / p.w)); return; }
      const f = zoomFactor(d);
      const ax = valueAt(x, p.x / p.w), ay = valueAt(y, 1 - p.y / p.h, distrY());
      this._view(act === 'zoom-y' ? null : zoomRange(x, ax, f), act === 'zoom-x' ? null : zoomRange(y, ay, f, distrY()));
    }, { passive: false });
  }
}
