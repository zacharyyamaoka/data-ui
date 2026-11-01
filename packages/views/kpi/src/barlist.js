/* type: barlist — a ranked bar list (docs/peps/0005-dashboard-cards.md §2b; Tremor's BarList).

     barlist:
       label:  the column naming a row (else the dataset's title); rows that share a label are one entry
       value:  {property, summary?, per?} (or a property name): per entry, summarised over its rows when a summary is
               given, else the entry's newest row as written
       limit:  rows shown; the rest are one "+N more" line that opens them
       better: higher (default: the list runs largest first) | lower (smallest first)

   A bar's width is value / max over ALL the entries (a limit never rescales the bars), drawn as a light accent fill
   behind the label's text; the value sits right-aligned in tabular figures. WHY no minimum bar width: a bar is its
   value's length, so a tiny one is nearly invisible rather than a lie (the number beside it is the truth). */

import { esc, isNum } from '@data-ui/core';
import { StatView, valueSpec, readValue, formatter, exact, rowLabel } from './stat.js';
import { barlistRows } from './stat-model.js';

const pct = (f) => `${(f * 100).toFixed(3).replace(/\.?0+$/, '')}%`;

export default class BarlistView extends StatView {
  update(input) {
    const b = input.view.barlist || {};
    const { rows, columns } = input;
    if (!rows.length) return this._note('No rows match this view.');
    const spec = valueSpec(b.value);
    const byLabel = new Map();
    for (const r of rows) {
      const name = rowLabel(r, b.label, input);
      if (!byLabel.has(name)) byLabel.set(name, []);
      byLabel.get(name).push(r);
    }
    const entries = [...byLabel].map(([name, rs]) => ({ label: name, rows: rs, read: readValue(rs, spec, columns) }))
      .map((e) => ({ ...e, value: isNum(e.read.value) ? e.read.value : null }));
    const computed = entries.some((e) => e.read.computed);
    const fmt = formatter(input, columns[spec.property], { computed });
    const { rows: shown, rest } = barlistRows(entries, { limit: b.limit, better: b.better === 'lower' ? 'lower' : 'higher' });
    const unit = entries.find((e) => e.read.unit)?.read.unit || '';
    const texts = shown.map((e) => (e.value === null ? '—' : fmt(e.value)));
    const vw = Math.max(1, ...texts.map((t) => t.length)) + (unit ? unit.length + 1 : 0);
    this._targets = shown.map((e) => ({ rows: e.rows, title: e.label }));
    if (rest.length) this._targets.push({ rows: rest.flatMap((e) => e.rows), title: `${rest.length} more` });

    const items = shown.map((e, i) => `<div class="dv-barlist-row" role="listitem" tabindex="0" data-hit="${i}" title="${esc(e.value === null ? e.read.why : `${e.label}: ${exact(e.value)}${e.read.unit ? ' ' + e.read.unit : ''}${e.read.computed ? ` (${e.read.from})` : ''}`)}">
        <div class="dv-barlist-track"><span class="dv-barlist-bar" style="width:${pct(e.frac)}"></span><span class="dv-barlist-label">${esc(e.label)}</span></div>
        <span class="dv-barlist-value" title="${esc(e.value === null ? e.read.why : exact(e.value))}">${esc(texts[i])}${e.value !== null && e.read.unit ? `<span class="dv-barlist-unit"> ${esc(e.read.unit)}</span>` : ''}</span>
      </div>`).join('');
    const more = rest.length ? `<button type="button" class="dv-barlist-more" data-hit="${shown.length}">+${rest.length.toLocaleString('en-US')} more</button>` : '';
    const from = computed ? `<p class="dv-barlist-from">${esc(entries.find((e) => e.read.from).read.from)}</p>` : '';
    this.el.innerHTML = `<div class="dv-barlist" style="--dv-barlist-vw:${vw + 1}ch"><div class="dv-barlist-list" role="list">${items}</div>${more}${from}</div>`;
  }
}
