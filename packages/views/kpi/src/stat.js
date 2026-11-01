/* What the stat cards (gauge, bullet, barlist, status) share: reading a number out of rows the way kpi does, writing it
   with the dashboard's number format, the base class that turns a click into host.open. The arithmetic is stat-model.js. */

import { cellValue, esc, fmtNum, numOpts, isNum, isEmpty, summarize, valueText } from '@data-ui/core';

/** A summary over rows; Ratio is Σproperty / Σper over the rows that have both. */
export function summarizeRows(rows, property, summary, per) {
  if (summary === 'Ratio') {
    let num = 0, den = 0, n = 0;
    for (const r of rows) {
      const a = cellValue(r[property]), b = cellValue(r[per]);
      if (isNum(a) && isNum(b)) { num += a; den += b; n++; }
    }
    return n && den ? num / den : null;
  }
  return summarize(rows.map((r) => r[property]), summary);
}

const label = (columns, id) => (columns[id] ? columns[id].label : id);

/** `value: price` and `value: {property, summary?, per?}` are the same key. */
export const valueSpec = (v) => (typeof v === 'string' ? { property: v } : v && typeof v === 'object' ? v : {});

/** The number a card shows for `rows`: {value, unit, computed, from, why, column}.
    No summary: the newest row's cell as written (the producer's number); a summary: computed here over the rows. */
export function readValue(rows, spec, columns) {
  const column = spec.property ? columns[spec.property] : null;
  if (!spec.property || !column) return { value: null, unit: '', computed: false, from: '', why: spec.property ? `no property "${spec.property}"` : 'no value property', column };
  if (spec.summary) {
    const v = summarizeRows(rows, spec.property, spec.summary, spec.per);
    const value = isNum(v) ? v : null;
    return { value, unit: spec.summary === 'Ratio' ? '' : column.unitText || '', computed: true, column,
      from: `${spec.summary === 'Ratio' ? `Σ ${label(columns, spec.property)} / Σ ${label(columns, spec.per)}` : `${spec.summary} of ${label(columns, spec.property)}`} over ${rows.length.toLocaleString('en-US')} row${rows.length === 1 ? '' : 's'}`,
      why: value === null ? 'nothing to summarise' : '' };
  }
  const row = rows[rows.length - 1];
  const cell = row ? row[spec.property] : null;
  const value = cellValue(cell);
  return { value: isEmpty(value) ? null : value, unit: (cell && typeof cell === 'object' && cell.unit) || column.unitText || '', computed: false, column,
    from: '', why: isEmpty(value) ? (cell && typeof cell === 'object' && cell.why) || 'no value' : '' };
}

/** A number-or-property key (max, min, target): the number, or the property's value on the newest of `rows`; null if neither. */
export function numberOf(key, rows, columns) {
  if (isNum(key)) return key;
  if (typeof key === 'string' && columns[key] && rows.length) {
    const v = cellValue(rows[rows.length - 1][key]);
    return isNum(v) ? v : null;
  }
  return null;
}

/** How this card writes a number: the dashboard's `style.numbers` under the property's own digits/compact and the card's
    `format:`. A computed number defaults to 4 significant figures (a quotient is float noise, not a stored value). */
export function formatter(input, column, { computed = false, format } = {}) {
  const style = input.view && input.view.style;
  const opts = { ...(computed ? { digits: 4 } : {}), ...numOpts(style && style.numbers, column, format) };
  return (v) => (isNum(v) ? String(fmtNum(v, column && column.decimals, opts)) : String(v ?? ''));
}

/** The exact stored text of a number (the hover under a rounded one). */
export const exact = (v) => (isNum(v) ? String(fmtNum(v)) : '');

/** An entry's label: the label column's cell as text, else the dataset's title, else the row id. */
export function rowLabel(row, property, input) {
  const col = property ? input.columns[property] : null;
  const text = property ? valueText(row[property], col) : '';
  if (text) return text;
  const tp = input.dataset && input.dataset.titleProperty;
  return (tp && valueText(row[tp], input.columns[tp])) || String(row.id);
}

export { esc, label };

/** Shared by the four cards: one click target list, one place that calls host.open (the dashboard turns that into a
    selection when the panel has `select:`, else its side peek). */
export class StatView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._targets = [];
    el.addEventListener('click', (e) => this._hit(e));
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') this._hit(e, true); });
  }

  destroy() {
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  /** The `data-hit` element under an event opens its target: {rows, title}; the newest row names the peek. */
  _hit(e, key = false) {
    const el = e.target.closest && e.target.closest('[data-hit]');
    const t = el && this._targets[Number(el.dataset.hit)];
    if (!t || !t.rows.length) return;
    if (key) e.preventDefault();
    this.host.open(t.rows[t.rows.length - 1].id, { records: t.rows, title: t.title });
  }

  /** Draw `html` and say, in place of the card, why there is nothing to draw. */
  _note(text) {
    this._targets = [];
    this.el.innerHTML = `<p class="dv-stat-note">${esc(text)}</p>`;
  }
}
