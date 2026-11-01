/* type: plot — dense signals over time (docs/peps/0012-live-data.md §6.2, docs/CONTRACT.md §26).

     plot: {x, y: col | [cols], series, only: [names], unit, dash: [names], rules: [{y, label, tone}],
            bands: [{y: [a, b], label, tone}], limits: {warn: [lo, hi], error: [lo, hi]}, legend: top|none, height}
     a rule's y or a band's bounds may name a property (sim2real gap #6; core guides.js): a device's own limit from the
     rows the view holds, a constant across x or a step line where it changes; on a live dataset, from the store as of
     t (each drawn stream's rows in the window, core live/window.js guideRows), so §35's limits draw and rewind with the
     clock there too; `el.plotView.guides` lists what is drawn
     at: 30s            the window ending at the clock's t (default 30 s live, the whole recording when recorded)

   Foxglove's Plot panel and PlotJuggler's plot, in Klipfolio's frameless look (the timeseries card's): 1.5 px lines,
   a faint horizontal grid, muted 11 px labels, the legend on top as dots, a crosshair readout instead of a tooltip.

   On a live dataset it reads the store's typed arrays (input.live), never row objects, and draws at most two points per
   pixel column per series (core live/window.js: min and max in time order, so a one-sample spike shows). Following,
   the right edge is t and the window slides one frame at a time; paused, nothing redraws while rows arrive after t.
   On the clock: [data-playhead] marks t, a click seeks (that leaves following), a horizontal drag sets clock.window
   (zoom; following stays following, the zoom keeps its width at the newest end), a double-click clears it, hover sets
   clock.hover and every time series shows the crosshair. On a plain dataset it draws the view's rows the same way.

   The legend is every chart's (the core's SeriesLegend, CONTRACT §31): a click hides a series, a double-click or Alt +
   click shows only it, Reset; y rescales to the series shown (uPlot's setSeries), x stays the clock's; the hidden set is
   the host's (l.<panel>= in a dashboard's URL, l= on a <data-views>), and a series' item menu offers Add to dashboard…
   (CONTRACT §34). WHY (RobotDx PEP 0001 §17.1, ask 1): this card drew a static key, so /dx/'s plots had no series to
   hide and nothing to add, the one gap §31's "every chart" left.

   STOCK PART: uPlot 1.6.32 (MIT): the canvas, the scales, the time axis, the paths. Decided 2026-10-27: uPlot for the
   live time series only (Vega's change sets were measured against it, bench/live.py); every other chart stays
   Vega-Lite. Ours: the reduction, the clock wiring, the HTML legend and readout. */

import uPlot from 'uplot';
import { esc, fmtNum, numOpts, cellValue, clockFor, fmtTime, seriesColor, alignSeries, ColumnCache, SeriesLegend, guideRows } from '@data-ui/core';
// WHY the source path: a pure helper the chart bundle bundles too (packages/core/src/guides.js)
import { guidesFrom, limitGuides } from '../../../core/src/guides.js';

const DASH = [5, 4];
const CLICK = 4;   // px: a press that moves less is a click (seek), not a drag (zoom)
const isTime = (v) => Math.abs(v) >= 1e9;
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumSignificantDigits: 3 });
const plain = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 4 });
const tickNum = (v) => (v === null || v === undefined ? '' : Math.abs(v) >= 10000 ? compact.format(v) : plain.format(v));
const TONE = { good: 'good', warn: 'warn', bad: 'bad', muted: 'muted', neutral: 'muted' };
const two = (n) => String(n).padStart(2, '0');
/** The properties a plot's guides read: its limits' ends, its rules' and bands' bounds that name one. */
function guideColumns(p) {
  const out = new Set();
  const take = (v) => { if (typeof v === 'string' && v) out.add(v); };
  for (const side of ['warn', 'error']) { const pair = p.limits && p.limits[side]; if (Array.isArray(pair)) pair.forEach(take); }
  for (const r of Array.isArray(p.rules) ? p.rules : []) if (r) take(r.y);
  for (const bd of Array.isArray(p.bands) ? p.bands : []) if (bd && Array.isArray(bd.y)) bd.y.forEach(take);
  return [...out];
}
/** A time tick: the reader's wall-clock time, tenths under a 10 s window, minutes past two hours. */
function timeTick(v, span) {
  const d = new Date(v * 1000);
  const hms = `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
  return span < 10 ? `${hms}.${Math.floor(d.getMilliseconds() / 100)}` : span < 7200 ? hms : `${two(d.getHours())}:${two(d.getMinutes())}`;
}

export class PlotView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = `<div class="dv-plot-head"><div class="dv-plot-legend" role="group" aria-label="Series"></div><span class="dv-plot-unit"></span></div>
      <div class="dv-plot-box" role="img">
        <div class="dv-plot-canvas"></div>
        <div class="dv-plot-brush" hidden></div>
        <div class="dv-plot-hover" data-hover hidden><div class="dv-plot-read"></div></div>
        <div class="dv-plot-playhead" data-playhead hidden></div>
        <div class="dv-plot-empty" hidden>No data in this window yet</div>
      </div>`;
    this.$ = (s) => el.querySelector(s);
    this.box = this.$('.dv-plot-box');
    this.canvas = this.$('.dv-plot-canvas');
    // a press redraws at once (the guides of a hidden series go too); the next live frame keeps the set (sync)
    this.legend = new SeriesLegend(this.$('.dv-plot-legend'), { host, keyClass: 'dv-plot-key', onChange: () => this._redraw() });
    this.clock = clockFor(host.element || el);
    this.u = null;
    this.key = null;
    this._xr = [0, 1];
    this._onHover = () => this._crosshair();
    // a plain dataset follows the clock here; a live one is redrawn by its feed (live/feed.js) on the same events
    this._onTime = () => { if (this.input && !this.input.live) this._place(); };
    this._onState = () => { if (this.input && !this.input.live) this._redraw(); };
    this.clock.addEventListener('hover', this._onHover);
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('state', this._onState);
    this._pointer();
    this._ro = new ResizeObserver(() => { if (this.input) this._redraw(); });
    this._ro.observe(this.box);
  }

  destroy() {
    this._dead = true;
    this.clock.removeEventListener('hover', this._onHover);
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('state', this._onState);
    this._ro.disconnect();
    this.legend.destroy();
    if (this.u) this.u.destroy();
    this.u = null;
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  update(input) {
    this.input = input;
    // the host's hidden set when it changed (a link, Back / Forward), else the legend's own (CONTRACT §31)
    this.legend.sync(input);
    this._redraw();
  }

  // ---------------------------------------------------------------- what to draw

  _opts() { return this.input.view.plot || {}; }

  /** The x window: the view's `at:` ending at t (live), the data's span (plain), clock.window when zoomed. */
  _window() {
    const input = this.input, c = this.clock, live = input.live;
    let a, b;
    if (live) {
      [a, b] = live.at === 'latest' ? [live.t - 30, live.t] : live.at;
      if (c && c.window) {
        // WHY following keeps the zoom's width at the newest end: Rerun 0.40 keeps following after a zoom
        if (live.following) a = b - (c.window[1] - c.window[0]); else [a, b] = c.window;
      }
    } else {
      [a, b] = this._extent || [0, 1];
      if (c && c.window) [a, b] = c.window;
    }
    if (!(Number.isFinite(a) && Number.isFinite(b))) { a = 0; b = 1; }
    if (b <= a) b = a + 1;
    return [a, b];
  }

  /** The series: [{name, column, parts, color, dashed}] (parts as LiveDataset.range returns them). */
  _series(a, b) {
    const input = this.input, p = this._opts(), cols = input.columns;
    const ys = (Array.isArray(p.y) ? p.y : [p.y]).filter((f) => f && cols[f]);
    const label = (f) => (cols[f] ? cols[f].label : f);
    const only = Array.isArray(p.only) && p.only.length ? new Set(p.only.map(String)) : null;
    const out = [];
    if (input.live) {
      const ds = input.live.dataset;
      const by = p.series || ds.stream;
      // WHY the stream only: the store keeps one stream per value of `stream:`, so a split is a range per stream;
      // a split by another column would read every row (plot.series names the dataset's stream property or nothing)
      const streams = by && by === ds.stream ? ds.streams().sort() : [null];
      for (const s of streams) {
        if (only && s !== null && !only.has(String(s))) continue;
        // no slices here: the column cache reads only what is new each frame (core live/window.js ColumnCache)
        for (const y of ys) out.push({ name: s === null ? label(y) : ys.length > 1 ? `${s} · ${label(y)}` : String(s), column: y, ds, stream: s, split: s === null ? null : String(s) });
      }
    } else {
      const x = p.x || 't', by = p.series && cols[p.series] ? p.series : null;
      const groups = new Map();
      let lo = Infinity, hi = -Infinity;
      for (const r of input.rows) {
        const t = cellValue(r[x]);
        if (typeof t !== 'number' || !Number.isFinite(t)) continue;
        const k = by ? String(cellValue(r[by]) ?? '') : '';
        if (only && by && !only.has(k)) continue;
        if (!groups.has(k)) groups.set(k, []);
        groups.get(k).push(r);
        if (t < lo) lo = t;
        if (t > hi) hi = t;
      }
      this._extent = lo <= hi ? [lo, hi] : null;
      if (this._extent) this.clock.extent(lo, hi);
      for (const [k, rows] of groups) {
        rows.sort((m, n) => cellValue(m[x]) - cellValue(n[x]));
        const t = Float64Array.from(rows, (r) => cellValue(r[x]));
        for (const y of ys) {
          const v = rows.map((r) => { const z = cellValue(r[y]); return typeof z === 'number' ? z : null; });
          out.push({ name: by ? (ys.length > 1 ? `${k} · ${label(y)}` : k) : label(y), column: y, parts: [{ t, cols: { [y]: v } }], split: by ? k : null });
        }
      }
    }
    const dash = new Set((p.dash || []).map(String));
    const pal = input.view.style && input.view.style.palette;
    for (const s of out) {
      s.color = (pal && pal[s.name]) || seriesColor(s.name, input);
      s.dashed = dash.has(s.name) || dash.has(s.column) || /(^|\W)target$/.test(s.name);
    }
    return out;
  }

  // ---------------------------------------------------------------- drawing

  _redraw() {
    if (this._dead || !this.input) return;
    const input = this.input, p = this._opts(), tokens = input.tokens;
    if (p.height) this.box.style.height = `${p.height}px`;
    const W = Math.max(80, Math.floor(this.box.clientWidth || 600));
    const H = Math.max(80, Math.floor(this.box.clientHeight || p.height || 200));
    // the series first (a plain dataset's extent comes from its rows), then the window
    if (!input.live) this._series(0, 0);
    const [a, b] = this._window();
    const list = this._series(a, b);
    this._xr = [a, b];
    const plotW = Math.max(20, W - 58);
    // rules and bands from a property, from the rows this view holds (on a live dataset, the snapshot at t)
    const xcol = p.x || (input.live && input.live.dataset && input.live.dataset.time) || 't';
    // a series the legend hides takes its own rules, bands and limits off the drawing too (and out of y), as the time
    // series cards do (CONTRACT §31)
    const hidden = this._hiddenSplits(list);
    const read = (r, c) => cellValue(r[c]);
    const src = this._guideSource(list, a, b, xcol);
    const prop = guidesFrom(src.rows, { rules: p.rules, bands: p.bands }, { x: xcol, series: src.series, read, hidden });
    this._prop = prop;
    // limits (docs/CONTRACT.md §35, threshold_band): RobotDx's warn and error limits per series (core guides.js)
    const lim = p.limits && typeof p.limits === 'object' ? limitGuides(src.rows, p.limits, { x: xcol, series: src.series, read, hidden }) : { rules: [], zones: [] };
    this._lim = lim;
    this.guides = [...prop.rules.map(({ guide, series, points, constant, label, tone }) => ({ guide, series, points, constant, label, tone })),
      ...prop.bands.map(({ guide, series, lo, hi, constant, tone }) => ({ guide, series, lo, hi, constant, tone })),
      ...lim.rules.map(({ guide, series, shared, points, constant, label, tone }) => ({ guide, series, shared, points, constant, label, tone })),
      ...lim.zones.map(({ guide, series, shared, lo, hi, tone }) => ({ guide, series, shared, lo, hi, tone }))];
    const gv = [...prop.rules.flatMap((g) => g.points.map((q) => q[1])), ...prop.bands.flatMap((g) => [...g.lo, ...g.hi].map((q) => q[1])),
      ...lim.rules.flatMap((g) => g.points.map((q) => q[1]))];
    // with limits drawn, y also takes in every numeric rule and band (the time series' rule, CONTRACT §35), so the lines
    // a reader set beside a limit are on the plot with it
    if (lim.rules.length || lim.zones.length) {
      for (const r of Array.isArray(p.rules) ? p.rules : []) if (r && typeof r.y === 'number' && Number.isFinite(r.y)) gv.push(r.y);
      for (const bd of Array.isArray(p.bands) ? p.bands : []) if (bd && Array.isArray(bd.y)) for (const v of bd.y) if (typeof v === 'number' && Number.isFinite(v)) gv.push(v);
    }
    this._propRange = gv.length ? [Math.min(...gv), Math.max(...gv)] : null;
    // live: min/max columns kept between frames on an absolute grid (only the new samples are read); plain rows: once
    const data = input.live ? (this._cache || (this._cache = new ColumnCache())).data(list, a, b, plotW) : alignSeries(list, a, b, plotW);
    const time = isTime(a);
    const key = JSON.stringify([list.map((s) => [s.name, s.color, s.dashed]), time, tokens.dark, tokens.muted, tokens.rule, p.rules || null, p.bands || null, p.limits || null, data.sparse]);
    const fresh = !this.u || key !== this.key;
    if (fresh) {
      if (this.u) this.u.destroy();
      this.u = new uPlot(this._uopts(list, data, { W, H, time, tokens, p }), data, this.canvas);
      // WHY an empty batch: uPlot lays its first frame out in a microtask; batch() commits it now, so _frame() below
      // measures the plotting area where it really is (measured before it, the playhead sat an axis width off)
      this.u.batch(() => {});
      this.key = key;
      this._head(list, p);
    } else {
      // WHY batch: uPlot commits a setData in a microtask; batch() draws now, so the playhead below reads the new
      // scale and a frame's measured cost includes the canvas work
      this.u.batch(() => {
        if (this.u.width !== W || this.u.height !== H) this.u.setSize({ width: W, height: H });
        this.u.setData(data);
        this._shown(list);
      });
    }
    // test and bench hooks (bench/live.py drives the engine through them)
    this.el.uplot = this.u;
    this.el.plotView = this;
    const n = data[0].length;
    if (this.el.dataset.points !== String(n)) this.el.dataset.points = String(n);
    const empty = this.$('.dv-plot-empty');
    if (empty.hidden !== n > 0) empty.hidden = n > 0;
    // WHY only when the box or the plot changed: _frame() reads layout, and reading it after the last frame's writes
    // forced a layout per plot per frame (12 plots, 12 layouts a frame at 60 kHz)
    if (fresh || this._frameW !== W || this._frameH !== H) { this._frame(); this._frameW = W; this._frameH = H; }
    this._place();
    if (this.clock.hover !== null) this._crosshair();
    else this.$('[data-hover]').hidden = true;
    // the label and the status say what is drawn; they change only with the series, so they are written only then
    const label = `plot of ${list.map((s) => s.name).join(', ')}: ${list.length} series, min/max per pixel column`;
    if (this.box.getAttribute('aria-label') !== label) this.box.setAttribute('aria-label', label);
    const status = `<span class="dv-chart-status">${list.length} series · min/max per pixel</span>`;
    if (status !== this._statusHtml) { this._statusHtml = status; this.host.setStatus(status); }
  }

  _uopts(list, data, { W, H, time, tokens, p }) {
    const font = `11px ${tokens.font || 'system-ui, sans-serif'}`;
    const axis = { stroke: tokens.muted, font, ticks: { show: false }, border: { show: false } };
    const rules = Array.isArray(p.rules) ? p.rules : [], bands = Array.isArray(p.bands) ? p.bands : [];
    const toneColor = (tone) => tokens[TONE[tone] || 'muted'] || tokens.muted;
    return {
      width: W, height: H, pxAlign: 0, legend: { show: false },
      cursor: { show: false, drag: { x: false, y: false, setScale: false } },
      // WHY 28 px on the right: the newest time tick sits on the right edge, and its label is centred on it
      padding: [8, 28, 0, 0],
      scales: {
        x: { time, range: () => this._xr },
        y: { range: (u, min, max) => {
          // a limit from a property is part of what y shows
          if (this._propRange && Number.isFinite(min) && Number.isFinite(max)) { min = Math.min(min, this._propRange[0]); max = Math.max(max, this._propRange[1]); }
          if (min === null || max === null || !Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
          if (min === max) return [min - 1, max + 1];
          const pad = (max - min) * 0.08;
          return [min - pad, max + pad];
        } },
      },
      axes: [
        { ...axis, grid: { show: false }, space: 90, values: time ? (u, vs) => vs.map((v) => timeTick(v, this._xr[1] - this._xr[0])) : (u, vs) => vs.map((v) => `${tickNum(v)} s`) },
        { ...axis, size: 50, grid: { stroke: tokens.rule, width: 1 }, values: (u, vs) => vs.map(tickNum) },
      ],
      series: [{}, ...list.map((s, i) => ({ label: s.name, show: this.legend.shows(s.name), stroke: s.color, width: 1.5, points: { show: false }, spanGaps: !!(data.sparse && data.sparse[i]), ...(s.dashed ? { dash: DASH } : {}) }))],
      hooks: {
        draw: [(u) => {
          const P = this._prop || { rules: [], bands: [] };
          const Lm = this._lim || { rules: [], zones: [] };
          if (!rules.length && !bands.length && !Lm.rules.length && !Lm.zones.length) return;
          const ctx = u.ctx, { left, top, width, height } = u.bbox;
          ctx.save();
          // rules and bands from a property: step lines through their points (a constant spans the data's x)
          const X = (v) => u.valToPos(v, 'x', true), Yp = (v) => u.valToPos(v, 'y', true);
          const stepTo = (pts) => pts.forEach(([x, v], i) => { if (!i) ctx.moveTo(X(x), Yp(v)); else { ctx.lineTo(X(x), Yp(pts[i - 1][1])); ctx.lineTo(X(x), Yp(v)); } });
          ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
          for (const g of P.bands) {
            ctx.beginPath();
            stepTo(g.hi);
            const back = [...g.lo].reverse();
            back.forEach(([x, v], i) => { ctx.lineTo(X(x), Yp(v)); if (i + 1 < back.length) ctx.lineTo(X(x), Yp(back[i + 1][1])); });
            ctx.closePath();
            ctx.fillStyle = toneColor(g.tone);
            ctx.globalAlpha = 0.09;
            ctx.fill();
            ctx.globalAlpha = 1;
          }
          for (const g of P.rules) {
            ctx.strokeStyle = toneColor(g.tone);
            ctx.globalAlpha = 0.85;
            ctx.setLineDash([3 * devicePixelRatio, 3 * devicePixelRatio]);
            ctx.lineWidth = devicePixelRatio;
            ctx.beginPath(); stepTo(g.points); ctx.stroke();
            ctx.setLineDash([]);
            ctx.globalAlpha = 1;
            if (g.label) { const [x, v] = g.points[g.points.length - 1]; ctx.fillStyle = ctx.strokeStyle; ctx.font = `${10 * devicePixelRatio}px ${tokens.font || 'system-ui'}`; ctx.textAlign = 'right'; ctx.fillText(g.label, Math.min(X(x), left + width) - 4, Yp(v) - 4); }
          }
          // limits (CONTRACT §35): each zone from its limit to the next, or to the plot's edge (an end of null); each limit
          // a dashed rule in its status tone with its glyph and word at its end
          const status = (tone) => (tokens.tone && tokens.tone[tone]) || toneColor(tone);
          const edgeY = (v, up) => (v === null ? (up ? top : top + height) : Yp(v));
          for (const z of Lm.zones) {
            ctx.beginPath();
            z.hi.forEach(([x, v], i) => { const yy = edgeY(v, true); if (!i) ctx.moveTo(X(x), yy); else { ctx.lineTo(X(x), edgeY(z.hi[i - 1][1], true)); ctx.lineTo(X(x), yy); } });
            const back = [...z.lo].reverse();
            back.forEach(([x, v], i) => { ctx.lineTo(X(x), edgeY(v, false)); if (i + 1 < back.length) ctx.lineTo(X(x), edgeY(back[i + 1][1], false)); });
            ctx.closePath();
            ctx.fillStyle = status(z.tone);
            ctx.globalAlpha = z.tone === 'bad' ? 0.11 : 0.09;
            ctx.fill();
            ctx.globalAlpha = 1;
          }
          // WHY on the pixel grid: a hairline at a fractional y spreads over two rows and, where it lies on a grid line (a
          // limit at a round value often does), blends with the grid's grey; snapped, a limit is one crisp row in its status
          // tone, at most half a pixel from its value (uPlot snaps its own lines so). Its zones keep the exact y
          const crisp = (y) => Math.round(y - ctx.lineWidth / 2) + ctx.lineWidth / 2;
          const stepCrisp = (pts) => pts.forEach(([x, v], i) => { const yy = crisp(Yp(v)); if (!i) ctx.moveTo(X(x), yy); else { ctx.lineTo(X(x), crisp(Yp(pts[i - 1][1]))); ctx.lineTo(X(x), yy); } });
          for (const g of Lm.rules) {
            ctx.strokeStyle = status(g.tone);
            ctx.globalAlpha = 0.95;
            ctx.setLineDash([4 * devicePixelRatio, 3 * devicePixelRatio]);
            ctx.lineWidth = devicePixelRatio;
            ctx.beginPath(); stepCrisp(g.points); ctx.stroke();
            ctx.setLineDash([]);
            ctx.globalAlpha = 1;
            const [x, v] = g.points[g.points.length - 1];
            ctx.fillStyle = ctx.strokeStyle; ctx.font = `${10 * devicePixelRatio}px ${tokens.font || 'system-ui'}`; ctx.textAlign = 'right';
            ctx.fillText(g.label, Math.min(X(x), left + width) - 4, crisp(Yp(v)) + (g.bound.endsWith('_lo') ? 12 : -4) * devicePixelRatio);
          }
          for (const band of bands) {
            if (!Array.isArray(band.y) || !band.y.every((v) => typeof v === 'number')) continue;
            const y0 = u.valToPos(band.y[0], 'y', true), y1 = u.valToPos(band.y[1], 'y', true);
            ctx.fillStyle = toneColor(band.tone);
            ctx.globalAlpha = 0.09;
            ctx.fillRect(left, Math.min(y0, y1), width, Math.abs(y1 - y0));
          }
          ctx.globalAlpha = 0.85;
          for (const r of rules) {
            if (typeof r.y !== 'number') continue;
            const y = u.valToPos(r.y, 'y', true);
            if (y < top || y > top + height) continue;
            ctx.strokeStyle = toneColor(r.tone);
            ctx.setLineDash([3 * devicePixelRatio, 3 * devicePixelRatio]);
            ctx.lineWidth = devicePixelRatio;
            ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + width, y); ctx.stroke();
            if (r.label) { ctx.fillStyle = ctx.strokeStyle; ctx.font = `${10 * devicePixelRatio}px ${tokens.font || 'system-ui'}`; ctx.textAlign = 'right'; ctx.fillText(r.label, left + width - 4, y - 4); }
          }
          ctx.restore();
        }],
      },
    };
  }

  _head(list, p) {
    const legend = p.legend !== 'none' && list.length > 0;
    // one <button aria-pressed> per series (src/legend.js); draw() keeps the buttons and their focus while the names stay
    this.legend.draw(legend ? list.map((s) => ({ name: s.name, swatch: `<i class="${s.dashed ? 'dv-plot-dash' : ''}" style="--dv-plot-c:${esc(s.color)}"></i>` })) : []);
    const cols = this.input.columns, ys = (Array.isArray(p.y) ? p.y : [p.y]).filter(Boolean);
    const unit = p.unit !== undefined ? p.unit : ys.length === 1 && cols[ys[0]] ? cols[ys[0]].unit || cols[ys[0]].unitText || '' : '';
    this.$('.dv-plot-unit').textContent = unit || '';
    this._series_ = list;
  }

  /** The rows the guides read, and the column that names their series. A plain dataset: the view's rows (of the series
      drawn, when `only` names them). A live one: the store as of t, each drawn stream's rows in the window [a, b] that
      begin or end a run of a guide column's values (core live/window.js guideRows), read only when a limit or a rule
      or band from a property asks. WHY (RobotDx PEP 0001 §18.4, ask 1): on live data the plot holds no rows (it reads
      typed arrays, live/feed.js LIVE_NATIVE), so it drew no §35 limit, by number or by property, and none rewound. */
  _guideSource(list, a, b, xcol) {
    const input = this.input, p = this._opts();
    const col = p.series && input.columns[p.series] ? p.series : null;
    if (!input.live) {
      const only = Array.isArray(p.only) && p.only.length && col ? new Set(p.only.map(String)) : null;
      const rows = input.rows || [];
      return { rows: only ? rows.filter((r) => only.has(String(cellValue(r[col]) ?? ''))) : rows, series: col };
    }
    const named = guideColumns(p);
    if (!(p.limits && typeof p.limits === 'object') && !named.length) return { rows: [], series: null };
    const ds = input.live.dataset;
    const streams = [...new Set(list.map((s) => (s.stream === undefined ? null : s.stream)))];
    // the series the plot draws: one per stream of `series` (default the dataset's stream), else one for every stream
    const series = !streams.length || (streams.length === 1 && streams[0] === null) ? null : (p.series || ds.stream);
    return { rows: guideRows(ds, streams, a, b, named, { x: xcol, series }), series };
  }

  /** Each series shown as the legend says, inside the caller's batch. WHY setSeries: uPlot re-ranges y over the series
      still shown, so a hidden outlier no longer flattens the rest; x is the clock's window and stays (CONTRACT §31). */
  _shown(list) {
    const u = this.u;
    list.forEach((s, k) => { const on = this.legend.shows(s.name); if (u.series[k + 1] && u.series[k + 1].show !== on) u.setSeries(k + 1, { show: on }); });
  }

  /** The split values whose every series the legend hides: their rules, bands and limits go with them (core guides.js
      takes the split column's values; with several y columns a value goes only when all of its series are hidden). */
  _hiddenSplits(list) {
    if (!this.legend.hidden.length) return [];
    const all = new Map();
    for (const s of list) if (s.split !== null && s.split !== undefined) all.set(s.split, (all.get(s.split) ?? true) && !this.legend.shows(s.name));
    return [...all].filter(([, off]) => off).map(([k]) => k);
  }

  /** Where the plotting area sits in the box (the playhead, the crosshair and the pointer map through it). */
  _frame() {
    const ob = this.u.over.getBoundingClientRect(), bb = this.box.getBoundingClientRect();
    this._ox = ob.left - bb.left;
    this._oy = ob.top - bb.top;
    this._ow = ob.width;
    this._oh = ob.height;
  }

  /** The playhead at the clock's t: one transform, through uPlot's own scale. */
  _place() {
    const ph = this.$('[data-playhead]');
    if (!this.u) { ph.hidden = true; return; }
    const t = this.input && this.input.live ? this.input.live.t : this.clock.t;
    const [a, b] = this._xr;
    if (!(t >= a && t <= b)) { ph.hidden = true; return; }
    ph.hidden = false;
    ph.style.height = `${this._oh}px`;
    ph.style.transform = `translate(${this._ox + this.u.valToPos(t, 'x') - 0.5}px, ${this._oy}px)`;
  }

  /** The shared crosshair: a rule at clock.hover and each series' value there (the nearest drawn point). */
  _crosshair() {
    const rule = this.$('[data-hover]');
    const t = this.clock.hover;
    const [a, b] = this._xr;
    if (!this.u || t === null || !(t >= a && t <= b)) { rule.hidden = true; return; }
    const xs = this.u.data[0];
    let lo = 0, hi = xs.length - 1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (xs[m] < t) lo = m + 1; else hi = m; }
    const style = this.input.view.style || {};
    const lines = (this._series_ || []).map((s, i) => {
      // a hidden series has no line to read (the interactive card's rule); the others read as before
      if (this.u.series[i + 1] && this.u.series[i + 1].show === false) return '';
      const ys = this.u.data[i + 1];
      let v = ys ? ys[lo] : null;
      if (v === null && ys && lo > 0) v = ys[lo - 1];
      const col = this.input.columns[s.column] || {};
      const text = v === null || v === undefined ? '—' : fmtNum(v, col.decimals, numOpts(style.numbers, col));
      return `<div class="dv-plot-line"><i style="--dv-plot-c:${esc(s.color)}"></i><span>${esc(s.name)}</span><b>${esc(text)}</b></div>`;
    }).join('');
    const read = this.$('.dv-plot-read');
    read.innerHTML = `<div class="dv-plot-t">${esc(fmtTime(t))}</div>${lines}`;
    const x = this._ox + this.u.valToPos(t, 'x');
    rule.hidden = false;
    rule.style.height = `${this._oh}px`;
    rule.style.transform = `translate(${x - 0.5}px, ${this._oy}px)`;
    read.classList.toggle('dv-plot-left', x + 16 + read.offsetWidth > this.box.clientWidth);
  }

  /** Pointer: hover sets clock.hover; a horizontal drag sets clock.window; a click seeks; a double-click un-zooms. */
  _pointer() {
    const box = this.box, brush = this.$('.dv-plot-brush');
    let start = null;
    const at = (e) => {
      if (!this.u) return null;
      const r = box.getBoundingClientRect();
      const px = e.clientX - r.left - this._ox, py = e.clientY - r.top - this._oy;
      return { px: Math.max(0, Math.min(this._ow, px)), inside: px >= 0 && px <= this._ow && py >= 0 && py <= this._oh };
    };
    const tAt = (px) => this.u.posToVal(px, 'x');
    box.addEventListener('pointermove', (e) => {
      const p = at(e);
      if (!p) return;
      this.clock.setHover(p.inside || start ? tAt(p.px) : null);
      if (start) {
        const lo = Math.min(start.px, p.px), hi = Math.max(start.px, p.px);
        brush.hidden = hi - lo < CLICK;
        brush.style.transform = `translate(${this._ox + lo}px, ${this._oy}px)`;
        brush.style.width = `${hi - lo}px`;
        brush.style.height = `${this._oh}px`;
      }
    });
    box.addEventListener('pointerleave', () => { if (!start) this.clock.setHover(null); });
    box.addEventListener('pointerdown', (e) => {
      const p = at(e);
      if (!p || !p.inside || e.button !== 0) return;
      start = p;
      box.setPointerCapture(e.pointerId);
    });
    box.addEventListener('pointerup', (e) => {
      if (!start) return;
      const p = at(e), s = start;
      start = null;
      brush.hidden = true;
      if (!p) return;
      if (Math.abs(p.px - s.px) >= CLICK) this.clock.setWindow([tAt(Math.min(s.px, p.px)), tAt(Math.max(s.px, p.px))]);
      else this.clock.seek(tAt(p.px));
      if (!p.inside) this.clock.setHover(null);
    });
    box.addEventListener('pointercancel', () => { start = null; brush.hidden = true; });
    box.addEventListener('dblclick', () => this.clock.setWindow(null));
  }
}
