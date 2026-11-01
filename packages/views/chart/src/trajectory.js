/* type: trajectory — 2D paths against a target (docs/peps/0005-dashboard-cards.md §2b, docs/CONTRACT.md §25).

     trajectory: {x, y, series, target, color, tolerance, t, trail}

   Equal aspect: one data unit is the same number of px on x and y (a circle stays a circle), so the domains are
   fitted to the plot's own size after Vega lays out its axes. The target is dashed and muted; `tolerance` draws it
   again behind, as a translucent tube 2 × tolerance wide on that same scale. `color` colours the other paths by a
   column (sequential, with its legend). Start (ring) and end (dot) marks on every path.

   Time-aware with a `t` column (default: a column named t): the card reports its span to the clock, and a
   [data-marker] dot per series sits at the clock's t, interpolated along t; `trail: true` draws each path faint and
   its part up to t solid. Markers and trails are positioned SVG/DOM over the canvas, redrawn per tick through the
   scales Vega already computed (no Vega run per tick).

   The legend is the core's (SeriesLegend, src/legend.js): a click hides a path (its line, ends, marker and trail), a
   double-click or Alt + click shows only it, Reset shows all. WHY both axes refit to the paths still shown: one data
   unit is the same px on x and y here, so y cannot rescale alone; refitting keeps a hidden outlier from shrinking the
   rest, which is the rule's reason (CONTRACT §31).

   STOCK PARTS: Vega-Lite (this bundle's one engine). Ours: the equal-aspect domains and the overlay. */

import embed from 'vega-embed';
import { cellValue, esc, clockFor, seriesColor, isNum, SeriesLegend } from '@data-ui/core';
import { theme } from './theme.js';
import { seriesStyles, along, equalAspect } from './series.js';
import { plotBox, unitOf, COMPACT } from './overlay.js';

const EMBED = { actions: false, renderer: 'canvas', tooltip: false, mode: 'vega-lite', logLevel: 1 };
const DASH = [5, 4];

/** The view's rows and entry -> {spec (no data), datasets, key, meta}. `dom` ({x, y, unit}) are the equal-aspect
    domains (null: estimated from the size); they live in signals, so fitting them never re-embeds. `hidden`: the paths
    the legend hides, left out of the drawn data and the fitted extent (meta.series keeps every path). Exported for tests. */
export function compileTrajectory(input, { width = 480, height = 360, dom = null, hidden = [] } = {}) {
  const { rows, view, columns, tokens } = input;
  const tj = view.trajectory || {};
  const x = tj.x, y = tj.y;
  const tcol = tj.t || (columns.t ? 't' : null);
  const split = tj.series && columns[tj.series] ? tj.series : null;
  const label = (f) => (columns[f] ? columns[f].label : f);
  const byName = new Map();
  const list = [];
  rows.forEach((row, i) => {
    const px = cellValue(row[x]), py = cellValue(row[y]);
    if (!isNum(px) || !isNum(py)) return;
    const v = split ? cellValue(row[split]) : null;
    const name = split ? (v === null || v === undefined || v === '' ? '—' : String(v)) : label(y);
    if (!byName.has(name)) { const s = { name, value: split ? name : null, column: y, points: [] }; byName.set(name, s); list.push(s); }
    const t = tcol ? cellValue(row[tcol]) : i;
    byName.get(name).points.push({ x: px, y: py, t: isNum(t) ? t : i, c: tj.color ? cellValue(row[tj.color]) : null });
  });
  for (const s of list) s.points.sort((a, b) => a.t - b.t);
  const target = tj.target !== undefined ? String(tj.target) : null;
  const styles = seriesStyles(list, { palette: view.style && view.style.palette, dash: target ? [target] : [], slot: (n) => seriesColor(n, input), muted: tokens.muted });
  for (const s of styles) s.target = s.name === target;

  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  const tol = isNum(tj.tolerance) ? tj.tolerance : 0;
  const off = new Set(hidden);
  const shown = styles.filter((s) => !off.has(s.name));
  for (const s of shown) {
    const pad = s.target ? tol : 0;
    for (const p of s.points) { x0 = Math.min(x0, p.x - pad); x1 = Math.max(x1, p.x + pad); y0 = Math.min(y0, p.y - pad); y1 = Math.max(y1, p.y + pad); }
  }
  if (!(x1 >= x0)) { x0 = 0; x1 = 1; y0 = 0; y1 = 1; }
  // before Vega has laid out its axes: about 44 px of labels on the left and 34 below
  const d = dom || equalAspect([x0, x1], [y0, y1], Math.max(40, width - 44), Math.max(40, height - 34));
  const tLo = Math.min(...styles.map((s) => (s.points.length ? s.points[0].t : Infinity)));
  const tHi = Math.max(...styles.map((s) => (s.points.length ? s.points[s.points.length - 1].t : -Infinity)));
  const timed = !!(tcol && columns[tcol] && columns[tcol].type !== 'date' && isNum(tLo) && isNum(tHi));
  const trail = !!(tj.trail && timed);
  const colorBy = tj.color && columns[tj.color] && columns[tj.color].type === 'number' ? tj.color : null;

  const paths = [], ends = [], segs = [];
  for (const s of shown) {
    s.points.forEach((p, i) => paths.push({ x: p.x, y: p.y, i, series: s.name }));
    if (s.points.length) {
      ends.push({ x: s.points[0].x, y: s.points[0].y, series: s.name, kind: 'start' });
      ends.push({ x: s.points[s.points.length - 1].x, y: s.points[s.points.length - 1].y, series: s.name, kind: 'end' });
    }
    if (colorBy && !s.target) {
      for (let i = 1; i < s.points.length; i++) {
        const a = s.points[i - 1], b = s.points[i];
        if (isNum(b.c)) segs.push({ x: a.x, y: a.y, x2: b.x, y2: b.y, c: b.c, series: s.name });
      }
    }
  }
  const names = styles.map((s) => s.name);
  const minimal = !view.style || view.style.chrome !== 'full';
  const font = tokens.font || 'system-ui, sans-serif';
  const unitIn = (f) => (unitOf(columns[f]) ? ` (${unitOf(columns[f])})` : '');
  const axis = (f, n) => ({ title: `${label(f)}${unitIn(f)}`, titleColor: tokens.muted, titleFontWeight: 400, titleFontSize: 11, titleFont: font, labelColor: tokens.muted,
    labelFontSize: 11, labelFont: font, grid: false, domain: !minimal, ticks: !minimal, tickCount: n, labelExpr: COMPACT, labelFlush: true, labelOverlap: true });
  const xEnc = { field: 'x', type: 'quantitative', scale: { domainMin: { expr: 'xmin' }, domainMax: { expr: 'xmax' }, nice: false, zero: false }, axis: axis(x, Math.max(2, Math.floor(width / 110))) };
  const yEnc = { field: 'y', type: 'quantitative', scale: { domainMin: { expr: 'ymin' }, domainMax: { expr: 'ymax' }, nice: false, zero: false }, axis: axis(y, Math.max(2, Math.floor(height / 70))) };
  const color = { field: 'series', type: 'nominal', scale: { domain: names, range: styles.map((s) => s.color) }, legend: null };
  // WHY faint until t: with trail, the overlay draws each moving path solid up to the clock's t (Rerun's time cursor)
  const opacity = { field: 'series', type: 'nominal', scale: { domain: names, range: styles.map((s) => (s.target ? 0.9 : trail || colorBy ? 0.28 : 1)) }, legend: null };
  const order = { field: 'i', type: 'quantitative' };
  const layer = [];
  const targetStyle = styles.find((s) => s.target);
  if (tol > 0 && targetStyle) {
    layer.push({ data: { name: 'paths' }, name: 'tolerance', transform: [{ filter: { field: 'series', equal: targetStyle.name } }],
      mark: { type: 'line', stroke: targetStyle.color, strokeOpacity: 0.16, strokeWidth: { expr: 'tube' }, strokeCap: 'round', strokeJoin: 'round', clip: true },
      encoding: { x: xEnc, y: yEnc, order } });
  }
  layer.push({ data: { name: 'paths' }, name: 'paths', mark: { type: 'line', strokeWidth: 1.5, strokeJoin: 'round', strokeCap: 'round', clip: true },
    encoding: { x: xEnc, y: yEnc, order, color, opacity,
      strokeDash: { field: 'series', type: 'nominal', scale: { domain: names, range: styles.map((s) => (s.dashed ? DASH : [])) }, legend: null } } });
  if (colorBy) {
    layer.push({ data: { name: 'segs' }, mark: { type: 'rule', strokeWidth: 2, strokeCap: 'round', clip: true },
      encoding: { x: xEnc, y: yEnc, x2: { field: 'x2' }, y2: { field: 'y2' },
        color: { field: 'c', type: 'quantitative', scale: { range: [tokens.series[0], tokens.warn] }, title: `${label(colorBy)}${unitIn(colorBy)}`,
          legend: { orient: 'top', direction: 'horizontal', gradientLength: Math.min(160, width / 3), gradientThickness: 6, titleOrient: 'left' } } } });
  }
  layer.push({ data: { name: 'ends' }, transform: [{ filter: "datum.kind === 'start'" }], mark: { type: 'point', shape: 'circle', size: 30, filled: false, strokeWidth: 1.5, opacity: 1, clip: true }, encoding: { x: xEnc, y: yEnc, color } });
  layer.push({ data: { name: 'ends' }, transform: [{ filter: "datum.kind === 'end'" }], mark: { type: 'point', shape: 'circle', size: 30, filled: true, opacity: 1, clip: true }, encoding: { x: xEnc, y: yEnc, color } });

  const spec = {
    width, height, autosize: { type: 'fit', contains: 'padding' },
    padding: { left: 2, right: 10, top: 8, bottom: 2 },
    params: [{ name: 'xmin', value: d.x[0] }, { name: 'xmax', value: d.x[1] }, { name: 'ymin', value: d.y[0] }, { name: 'ymax', value: d.y[1] }, { name: 'tube', value: 2 * tol * d.unit }],
    layer,
    ...(colorBy ? { resolve: { scale: { color: 'independent' } } } : {}),
    config: theme(tokens, { narrow: width < 560, chrome: minimal ? 'minimal' : 'full' }),
  };
  const key = JSON.stringify({ ...spec, width: undefined, height: undefined, params: 'xy' });
  return {
    // WHY segs only with a colour column: Vega registers only the datasets a layer reads, and a redraw that swaps data on
    // the drawn view (a legend click, a refresh) failed on "Unrecognized data set: segs" for every path without colour
    spec, key, datasets: { paths, ends, ...(colorBy ? { segs } : {}) },
    meta: { series: styles, extent: { x: [x0, x1], y: [y0, y1] }, tolerance: tol, unit: unitOf(columns[x]), timed, trail, t: timed ? [tLo, tHi] : null, drawn: paths.length,
      aria: `trajectory of ${label(y)} against ${label(x)}: ${styles.length} paths${target ? `, ${target} as the target` : ''}` },
  };
}

export class TrajectoryView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._key = null;
    this._job = Promise.resolve();
    el.innerHTML = `<div class="dv-trajectory-head"><div class="dv-trajectory-legend" role="group" aria-label="Paths"></div></div>
      <div class="dv-trajectory-plot" role="img">
        <div class="dv-trajectory-canvas"></div>
        <svg class="dv-trajectory-svg" aria-hidden="true"></svg>
        <div class="dv-trajectory-markers"></div>
      </div>`;
    this.$ = (sel) => el.querySelector(sel);
    this.plot = this.$('.dv-trajectory-plot');
    this.legend = new SeriesLegend(this.$('.dv-trajectory-legend'), { host, keyClass: 'dv-trajectory-key', onChange: () => this._queue() });
    this.clock = clockFor(host.element || el);
    this._onTime = () => this._place();
    this.clock.addEventListener('time', this._onTime);
    this._resize = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => { if (this.input) this._queue(); }, 80);
    });
    this._resize.observe(this.plot);
  }

  destroy() {
    this._dead = true;
    this.clock.removeEventListener('time', this._onTime);
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

  _queue() {
    if (this._waiting) return this._waiting;
    this._job = this._waiting = this._job.then(() => { this._waiting = null; return this._dead ? undefined : this._draw(); }).catch((err) => this._fail(err));
    return this._job;
  }

  async _draw() {
    const input = this.input;
    const width = Math.max(200, Math.floor(this.plot.clientWidth || this.el.clientWidth || 480));
    const height = Math.max(140, Math.floor(this.plot.clientHeight || 360));
    const out = compileTrajectory(input, { width, height, hidden: this.legend.hidden });
    const meta = out.meta;
    this._meta = meta;
    this._legend(meta);
    if (meta.timed) this.clock.extent(meta.t[0], meta.t[1]);
    let view;
    if (out.key === this._key && this.result) {
      view = this.result.view;
      for (const [name, values] of Object.entries(out.datasets)) view.data(name, values);
      view.width(width).height(height).resize();
      await view.runAsync();
    } else {
      if (this.result) this.result.finalize();
      this.result = null;
      const result = await embed(this.$('.dv-trajectory-canvas'), { ...out.spec, datasets: out.datasets }, EMBED);
      if (this._dead) { result.finalize(); return; }
      this.result = result;
      this._key = out.key;
      view = result.view;
    }
    if (this._dead) return;
    // equal aspect on the plot Vega actually laid out: its axes take a width that depends on the labels, which
    // depend on the domains, so fit again until one unit is the same px on both axes (two passes in practice)
    for (let pass = 0; pass < 4; pass++) {
      const d = equalAspect(meta.extent.x, meta.extent.y, view.width(), view.height());
      view.signal('xmin', d.x[0]).signal('xmax', d.x[1]).signal('ymin', d.y[0]).signal('ymax', d.y[1]).signal('tube', 2 * meta.tolerance * d.unit);
      await view.runAsync();
      if (this._dead) return;
      const ux = view.scale('x')(1) - view.scale('x')(0), uy = view.scale('y')(0) - view.scale('y')(1);
      if (Math.abs(ux - uy) <= 0.002 * ux) break;
    }
    this.el.vegaView = view;
    this._box = plotBox(view, this.plot);
    this._paths();
    this.el.dataset.drawn = String(meta.drawn);
    this.plot.setAttribute('aria-label', meta.aria);
    this.host.setStatus(`<span class="dv-chart-status">${meta.series.length} paths</span>`);
    this._place();
  }

  _fail(err) {
    if (this._dead) return;
    this._key = null;
    this.$('.dv-trajectory-canvas').innerHTML = `<p class="dv-err dv-chart-err">This trajectory could not be drawn: ${esc(err && err.message ? err.message : err)}</p>`;
    this.host.setStatus('');
  }

  _legend(meta) {
    this.legend.draw(meta.series.map((s) => ({ name: s.name, swatch: `<i class="${s.dashed ? 'dv-trajectory-dash' : ''}" style="--dv-ts-c:${esc(s.color)}"></i>`,
      extra: s.target && meta.tolerance ? ` <small>± ${esc(String(meta.tolerance))}${meta.unit ? ` ${esc(meta.unit)}` : ''}</small>` : '' })));
  }

  /** After each Vega run: every path in overlay px (the trail's vertices), a marker and a trail element per series. */
  _paths() {
    const b = this._box, meta = this._meta;
    const svg = this.$('.dv-trajectory-svg');
    const box = this.$('.dv-trajectory-markers');
    this._series = [];
    if (!b || !meta.timed) { svg.innerHTML = ''; box.innerHTML = ''; return; }
    let svgHtml = '', dots = '';
    for (const s of meta.series) {
      const pts = s.points;
      const off = !this.legend.shows(s.name);
      const one = {
        name: s.name, ts: pts.map((p) => p.t), xs: pts.map((p) => p.x), ys: pts.map((p) => p.y),
        vertex: pts.map((p) => `${(b.x + b.sx(p.x)).toFixed(1)},${(b.y + b.sy(p.y)).toFixed(1)}`),
        trail: meta.trail && !s.target && !(this.input.view.trajectory || {}).color,
      };
      this._series.push(one);
      if (one.trail && off) one.trail = false;
      if (one.trail) svgHtml += `<path data-trail data-series="${esc(s.name)}" fill="none" stroke="${esc(s.color)}" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"></path>`;
      dots += `<span class="dv-trajectory-marker${s.target ? ' dv-trajectory-ghost' : ''}" data-marker data-series="${esc(s.name)}" style="--dv-ts-c:${esc(s.color)}" title="${esc(s.name)}"${off ? ' hidden' : ''}></span>`;
    }
    svg.innerHTML = svgHtml;
    box.innerHTML = dots;
    for (const one of this._series) {
      one.path = svg.querySelector(`[data-trail][data-series="${CSS.escape(one.name)}"]`);
      one.dot = box.querySelector(`[data-marker][data-series="${CSS.escape(one.name)}"]`);
    }
  }

  /** On every clock tick: each marker at its interpolated (x, y), each trail up to t. */
  _place() {
    const b = this._box;
    if (!b || !this._series) return;
    const t = this.clock.t;
    for (const one of this._series) {
      const at = along(one.ts, one.xs, one.ys, t);
      if (!at) continue;
      const px = b.x + b.sx(at[0]), py = b.y + b.sy(at[1]);
      one.dot.style.transform = `translate(${px}px, ${py}px)`;
      if (one.path) one.path.setAttribute('d', `M${one.vertex.slice(0, at[2] + 1).join('L')}L${px.toFixed(1)},${py.toFixed(1)}`);
    }
  }
}
