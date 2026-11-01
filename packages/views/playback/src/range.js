/* P5 `range` (docs/peps/0005-dashboard-cards.md §4b): an overview with a brushed range, as Grafana's time-range
   zoom, Highcharts Stock's navigator and uPlot's range selector do it (prior art in ../README.md).

   A minimap of the whole span with the main time series as sparklines (the first time series card's lines in their
   palette colours), a brushable window (drag across it to set clock.window: every time series zooms to it; drag the
   window to move it, its handles to resize it, double-click or "Zoom out" to clear), the area outside the window
   dimmed, the playhead, and a readout of t and the window. A click without a drag seeks. Its legend is every chart's
   (src/legend.js): a click hides a line from the overview, a double-click or Alt + click shows only it, and the
   sparklines' height fits the lines still shown.
   STOCK PARTS: none (SVG paths, pointer events). */

import { esc, SeriesLegend } from '@data-ui/core';
import { Variant, ICON } from './base.js';
import { niceTicks, sparkPath, spanText } from './model.js';

const DRAG = 4;   // px a pointer moves before a press is a brush, not a click

export class RangePlayback extends Variant {
  constructor(host, el, name, clock) {
    super(host, el, 'range', clock);
    el.innerHTML = `<div class="dv-rg" data-variant-root>
      <div class="dv-rg-row">
        <button type="button" class="dv-rg-btn dv-rg-play" data-act="play" title="Play / pause (Space)" aria-label="Play">${ICON.play}</button>
        <span class="dv-rg-now" title="The clock's time">—</span>
        <span class="dv-rg-flex"></span>
        <span class="dv-rg-win" title="The window every time series shows (clock.window)">Whole span</span>
        <button type="button" class="dv-rg-zoom" data-act="zoomout" title="Show the whole span (double-click the overview)" disabled>Zoom out</button>
      </div>
      <div class="dv-rg-map" data-scrub title="Drag to zoom every time series to a window · click to seek · double-click to zoom out">
        <svg class="dv-rg-spark" viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true"></svg>
        <div class="dv-rg-shade dv-rg-l"></div><div class="dv-rg-shade dv-rg-r"></div>
        <div class="dv-rg-brush" data-brush hidden><span class="dv-rg-h" data-h="0"></span><span class="dv-rg-h" data-h="1"></span></div>
        <div class="dv-rg-ph" data-playhead aria-hidden="true"></div>
        <div class="dv-rg-axis"></div>
      </div>
      <div class="dv-rg-legend"></div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this.legend = new SeriesLegend(this.$('.dv-rg-legend'), { host, keyClass: 'dv-rg-key', onChange: () => { if (this.input) this.draw(); } });
    this._off.push(() => this.legend.destroy());
    this.on(el, 'click', (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      if (b.dataset.act === 'play') this.clock.toggle();
      else if (b.dataset.act === 'zoomout') this.clock.setWindow(null);
    });
    this.wireMap();
  }

  wireMap() {
    const map = this.$('.dv-rg-map');
    let press = null;
    this.on(map, 'pointerdown', (e) => {
      if (e.button !== 0) return;
      const c = this.clock, t = this.tAt(e.clientX, map), h = e.target.closest('.dv-rg-h');
      const inWin = c.window && !h && e.target.closest('.dv-rg-brush');
      press = { x: e.clientX, t, moved: false, mode: h && c.window ? 'resize' : inWin ? 'move' : 'brush',
        anchor: h && c.window ? c.window[1 - Number(h.dataset.h)] : t, win: c.window ? [...c.window] : null };
      try { map.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    });
    this.on(map, 'pointermove', (e) => {
      if (!press) return;
      if (!press.moved && Math.abs(e.clientX - press.x) < DRAG) return;
      press.moved = true;
      const t = this.tAt(e.clientX, map), [a, b] = this.span();
      if (press.mode === 'move') {
        const w = press.win[1] - press.win[0];
        let lo = press.win[0] + (t - press.t);
        lo = Math.max(a, Math.min(b - w, lo));
        this.clock.setWindow([lo, lo + w]);
      } else if (Math.abs(t - press.anchor) > 1e-3) {
        this.clock.setWindow([Math.min(press.anchor, t), Math.max(press.anchor, t)]);
      }
    });
    const end = (e) => {
      if (!press) return;
      const p = press;
      press = null;
      if (!p.moved && e.type === 'pointerup') { this.clock.pause(); this.clock.seek(p.t); }
    };
    this.on(map, 'pointerup', end);
    this.on(map, 'pointercancel', end);
    this.on(map, 'dblclick', () => this.clock.setWindow(null));
  }

  update(input) {
    super.update(input);
    this.legend.sync(input);
    const key = this._key(this.data().datasets);
    if (key !== this._dataKey) { this._dataKey = key; this.main = this.seriesTracks(400)[0] || null; this._spanKey = null; }
    this.state();
  }

  draw() {
    const [a, b] = this.span(), m = this.main;
    const svg = this.$('.dv-rg-spark');
    if (!m) { svg.innerHTML = ''; this.legend.draw([]); this.$('.dv-rg-legend').textContent = 'No time series on this dashboard: the overview shows the span only'; return; }
    this.legend.draw(m.lines.map((l) => ({ name: l.name, swatch: `<i style="background:${esc(l.color)}"></i>` })), this.legend.hidden, { title: m.name });
    const lines = m.lines.filter((l) => this.legend.shows(l.name));
    let lo = Infinity, hi = -Infinity;
    for (const l of lines) for (const [, v] of l.points) if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    const pad = (hi - lo) * 0.08 || 1;
    svg.innerHTML = lines.map((l) => `<path data-series="${esc(l.name)}" d="${sparkPath(l.points, a, b, lo - pad, hi + pad)}" stroke="${esc(l.color)}" fill="none" stroke-width="1.25" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`).join('');
    const ticks = niceTicks(a, b, 8), dec = ticks.length > 1 && ticks[1] - ticks[0] < 1 ? 1 : 0;
    this.$('.dv-rg-axis').innerHTML = ticks.map((v) => `<span style="left:${this.frac(v) * 100}%">${esc(v.toFixed(dec))} s</span>`).join('');
  }

  state() {
    const c = this.clock, [a, b] = this.span();
    const key = `${a}|${b}|${this._dataKey}`;
    if (key !== this._spanKey && this.input) { this._spanKey = key; this.draw(); }
    const play = this.$('.dv-rg-play');
    play.innerHTML = c.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', c.playing ? 'Pause' : 'Play');
    play.classList.toggle('dv-on', c.playing);
    const w = c.window, br = this.$('[data-brush]');
    br.hidden = !w;
    const l = w ? this.frac(w[0]) : 0, r = w ? this.frac(w[1]) : 1;
    br.style.left = `${l * 100}%`; br.style.width = `${(r - l) * 100}%`;
    this.$('.dv-rg-l').style.width = w ? `${l * 100}%` : '0';
    this.$('.dv-rg-r').style.width = w ? `${(1 - r) * 100}%` : '0';
    this.$('.dv-rg-win').textContent = w ? spanText(w[0], w[1]) : `Whole span · ${spanText(a, b)}`;
    this.$('.dv-rg-zoom').disabled = !w;
    this.el.toggleAttribute('data-empty', c.start === null);
    this.time();
  }

  time() {
    const c = this.clock;
    this.el.style.setProperty('--dv-pb-f', String(this.frac(c.t)));
    this.$('.dv-rg-now').textContent = `${c.t.toFixed(2)} s`;
  }
}
