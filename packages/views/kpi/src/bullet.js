/* type: bullet — one bullet chart per row, or per group (docs/peps/0005-dashboard-cards.md §2b; Stephen Few's bullet,
   as a Tremor-style list).

     bullet:
       value:  {property, summary?, per?} (or a property name), read per row (the cell as written) or, with groupBy,
               per group (summarised when a summary is given, else the group's newest row)
       target: a number or a property (read per row): the tick
       max:    a number or a property (the largest of them across the rows); the scale is 0..max, one scale for every
               row so the bars compare; with none, the next tidy number above every value and target
       label:  the column that names a row (else the dataset's title)
       better: higher | lower: which side of the target is good (colours the value text, never the bar)
       bands:  [numbers] upper bounds of 2-3 grey zones, the worst the darkest; the last runs to max

   A value past max fills the track and is marked (data-clipped, a chevron) instead of being drawn to a length it
   does not have. WHY the value column's width is set once (--dv-bullet-vw, in ch): every row's track must start and
   end at the same x, or the bars cannot be compared by eye. */

import { esc, isNum, groupLabel } from '@data-ui/core';
import { StatView, valueSpec, readValue, numberOf, formatter, exact, rowLabel } from './stat.js';
import { fraction, niceMax, bandSegments, againstTarget, shadeLevels } from './stat-model.js';

const pct = (f) => `${(f * 100).toFixed(3).replace(/\.?0+$/, '')}%`;

export default class BulletView extends StatView {
  update(input) {
    const b = input.view.bullet || {};
    const { rows, columns } = input;
    if (!rows.length) return this._note('No rows match this view.');
    const spec = valueSpec(b.value);
    // one entry per group, else one per row
    const entries = (input.groups && input.groups.length
      ? input.groups.map((g) => ({ label: groupLabel(columns, g.property, g.key), rows: g.rows }))
      : rows.map((r) => ({ label: rowLabel(r, b.label, input), rows: [r] }))).filter((e) => e.rows.length);
    for (const e of entries) {
      e.read = readValue(e.rows, spec, columns);
      e.target = numberOf(b.target, e.rows, columns);
    }
    const column = columns[spec.property];
    const computed = entries.some((e) => e.read.computed);
    const fmt = formatter(input, column, { computed });
    const better = b.better === 'lower' ? 'lower' : 'higher';
    const maxes = typeof b.max === 'string' ? entries.map((e) => numberOf(b.max, e.rows, columns)).filter(isNum) : [];
    const top = Math.max(0, ...entries.flatMap((e) => [e.read.value, e.target]).filter(isNum));
    const max = isNum(b.max) ? b.max : maxes.length ? Math.max(...maxes) : niceMax(top);
    const segs = bandSegments((b.bands || []).filter(isNum).map((to) => ({ to })), 0, max);
    const levels = shadeLevels(segs.length, better);
    const texts = entries.map((e) => (isNum(e.read.value) ? fmt(e.read.value) : '—'));
    const unit = entries.find((e) => e.read.unit)?.read.unit || '';
    const vw = Math.max(...texts.map((t) => t.length)) + (unit ? unit.length + 1 : 0);

    this._targets = entries.map((e) => ({ rows: e.rows, title: e.label }));
    const bands = segs.map((s, i) => `<span class="dv-bullet-band dv-bullet-shade-${levels[i]}" style="left:${pct(s.f0)};width:${pct(s.f1 - s.f0)}" title="${esc(`${exact(s.from)} to ${exact(s.to)}`)}"></span>`).join('');
    const items = entries.map((e, i) => {
      const pos = fraction(e.read.value, 0, max);
      const tpos = fraction(e.target, 0, max);
      const against = againstTarget(e.read.value, e.target, better);
      const clipped = pos && pos.clipped === 'high';
      const tone = against ? (against.good ? 'good' : 'bad') : '';
      const title = isNum(e.read.value) ? `${exact(e.read.value)}${e.read.unit ? ' ' + e.read.unit : ''}${isNum(e.target) ? `; target ${exact(e.target)}` : ''}${clipped ? `; beyond the scale (max ${exact(max)})` : ''}` : e.read.why;
      return `<div class="dv-bullet-row" role="listitem" tabindex="0" data-hit="${i}" data-clipped="${clipped ? 'true' : 'false'}" data-tone="${tone}" title="${esc(title)}">
        <span class="dv-bullet-label" title="${esc(e.label)}">${esc(e.label)}</span>
        <div class="dv-bullet-track">${bands}${pos ? `<span class="dv-bullet-bar${clipped ? ' dv-bullet-clipped' : ''}" style="width:${pct(pos.f)}"></span>` : ''}${tpos ? `<span class="dv-bullet-target" style="left:${pct(tpos.f)}"></span>` : ''}</div>
        <span class="dv-bullet-value${tone ? ` dv-tone-text-${tone}` : ''}">${esc(texts[i])}${isNum(e.read.value) && e.read.unit ? `<span class="dv-bullet-unit"> ${esc(e.read.unit)}</span>` : ''}</span>
      </div>`;
    }).join('');
    const from = computed ? entries[0].read.from : '';
    const targetNote = entries.some((e) => isNum(e.target)) ? `target tick${entries.every((e) => e.target === entries[0].target) ? ` ${fmt(entries[0].target)}` : ''}` : '';
    const foot = [`scale 0 to ${fmt(max)}${unit ? ' ' + unit : ''}`, targetNote, from].filter(Boolean).join(' · ');
    this.el.innerHTML = `<div class="dv-bullet" role="list" style="--dv-bullet-vw:${vw + 1}ch">${items}<p class="dv-bullet-foot">${esc(foot)}</p></div>`;
  }
}
