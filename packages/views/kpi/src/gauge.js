/* type: gauge — one number against a scale (docs/peps/0005-dashboard-cards.md §2b; Tremor's ProgressBar / ProgressCircle).

     gauge:
       value:  {property, summary?, per?} (or a property name), as kpi.value: no summary = the newest row's cell as
               written; a summary (Bases' names, or Ratio = Σproperty / Σper) is computed over the view's rows
       min, max, target:  a number or a property (its value on the newest row); min 0 by default; with no max the
               scale ends at the next tidy number above the value and the target
       shape:  bar | arc (a semicircle)
       better: higher | lower, which side of the target is good (default higher)
       bands:  [{to, tone}] the track's colour zones, the last without `to`; the fill wears the tone of the band the
               value is in, else good/bad by the target, else the accent
       label:  muted caption under the gauge

   WHY one SVG path for the arc's track and one for its fill, not a stroke-dasharray trick: the fraction is then a
   length anyone can measure (getTotalLength), and the target tick is a real line at a real point of the track. */

import { esc, isNum } from '@data-ui/core';
import { StatView, valueSpec, readValue, numberOf, formatter, exact, label } from './stat.js';
import { fraction, niceMax, bandSegments, bandTone, againstTarget, arcPath, arcPoint } from './stat-model.js';

const CX = 100, CY = 100, R = 84, STROKE = 16;
const pct = (f) => `${(f * 100).toFixed(3).replace(/\.?0+$/, '')}%`;

export default class GaugeView extends StatView {
  update(input) {
    const g = input.view.gauge || {};
    const { rows, columns } = input;
    if (!rows.length) return this._note('No rows match this view.');
    const spec = valueSpec(g.value);
    const read = readValue(rows, spec, columns);
    const min = numberOf(g.min, rows, columns) ?? 0;
    const target = numberOf(g.target, rows, columns);
    let max = numberOf(g.max, rows, columns);
    if (!isNum(max)) max = niceMax(Math.max(isNum(read.value) ? read.value : 0, isNum(target) ? target : 0, min + 1e-9));
    const fmt = formatter(input, read.column, { computed: read.computed });
    const fmtScale = formatter(input, read.column, {});
    const better = g.better === 'lower' ? 'lower' : 'higher';
    const pos = fraction(read.value, min, max);
    const tpos = fraction(target, min, max);
    const against = againstTarget(read.value, target, better);
    const bands = bandSegments(g.bands, min, max);
    // the fill's tone: the band the value is in, else the target's verdict, else the accent
    const tone = bandTone(g.bands, read.value) || (against ? (against.good ? 'good' : 'bad') : 'accent');
    const shape = g.shape === 'arc' ? 'arc' : 'bar';
    const unit = read.unit;

    const number = isNum(read.value)
      ? `<span class="dv-gauge-num" title="${esc(exact(read.value))}${unit ? ' ' + esc(unit) : ''}${read.computed ? ' (computed)' : ''}">${esc(fmt(read.value))}</span>${unit ? `<span class="dv-gauge-unit">${esc(unit)}</span>` : ''}`
      : `<span class="dv-gauge-none" title="${esc(read.why)}">—</span>`;
    const arrow = against && against.dir === 'over' ? '▲' : against && against.dir === 'under' ? '▼' : '●';
    const delta = against
      ? `<span class="dv-gauge-delta dv-tone-${against.good ? 'good' : 'bad'}" title="${esc(`${exact(read.value)} against a target of ${exact(target)}; ${better} is better`)}"><span aria-hidden="true">${arrow}</span> ${against.dir === 'on' ? 'on target' : `${esc(fmt(against.diff))} ${against.dir} target`}</span>`
      : '';
    const caption = [g.label ? `<span class="dv-gauge-label">${esc(g.label)}</span>` : '', read.from ? `<span class="dv-gauge-from">${esc(read.from)}</span>` : ''].filter(Boolean).join('');
    const scale = `<div class="dv-gauge-scale"><span>${esc(fmtScale(min))}</span><span>${esc(fmtScale(max))}</span></div>`;
    const tick = tpos ? `target ${fmtScale(target)}` : '';

    let meter;
    if (shape === 'arc') {
      const bandPaths = bands.map((b) => `<path class="dv-gauge-band dv-tone-${esc(b.tone)}" d="${arcPath(CX, CY, R, b.f0, b.f1)}"></path>`).join('');
      const fill = pos && pos.f > 0 ? `<path class="dv-gauge-fill dv-tone-${esc(tone)}" d="${arcPath(CX, CY, R, 0, pos.f)}"></path>` : '';
      let mark = '';
      if (tpos) {
        const [x0, y0] = arcPoint(CX, CY, R - STROKE / 2 - 3, tpos.f), [x1, y1] = arcPoint(CX, CY, R + STROKE / 2 + 3, tpos.f);
        mark = `<line class="dv-gauge-target" x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}"><title>${esc(tick)}</title></line>`;
      }
      meter = `<div class="dv-gauge-arc"><svg viewBox="0 0 200 112" role="img" aria-label="${esc(g.label || 'gauge')}">
          <path class="dv-gauge-track" d="${arcPath(CX, CY, R, 0, 1)}"></path>${bandPaths}${fill}${mark}</svg>
        <div class="dv-gauge-center">${number}</div></div>${scale}`;
    } else {
      const bandEls = bands.map((b) => `<span class="dv-gauge-band dv-tone-${esc(b.tone)}" style="left:${pct(b.f0)};width:${pct(b.f1 - b.f0)}"></span>`).join('');
      const fill = pos && pos.f > 0 ? `<span class="dv-gauge-fill dv-tone-${esc(tone)}" style="width:${pct(pos.f)}"></span>` : '';
      const mark = tpos ? `<span class="dv-gauge-target" style="left:${pct(tpos.f)}"><span class="dv-gauge-target-label${tpos.f > 0.8 ? ' dv-gauge-end' : tpos.f < 0.2 ? ' dv-gauge-start' : ''}">${esc(tick)}</span></span>` : '';
      meter = `<div class="dv-gauge-head">${number}${delta}</div>
        <div class="dv-gauge-meter"><div class="dv-gauge-track">${bandEls}${fill}</div>${mark}</div>${scale}`;
    }
    this._targets = [{ rows, title: g.label || input.view.name || label(columns, spec.property) }];
    this.el.innerHTML = `<div class="dv-gauge" data-shape="${shape}" data-tone="${esc(tone)}" data-hit="0" role="button" tabindex="0" aria-label="${esc(`${g.label || input.view.name}: ${isNum(read.value) ? fmt(read.value) : 'no value'}`)}">
      ${meter}${shape === 'arc' ? `<div class="dv-gauge-foot">${delta}</div>` : ''}<div class="dv-gauge-caption">${caption}</div></div>`;
  }
}
