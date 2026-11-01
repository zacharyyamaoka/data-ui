/* type: summary and <data-summary for="views-id">: one rounded card holding a few metrics side by side, each a label
   with a dotted underline whose tooltip is the metric's definition, the value under it, and, only when the cell has a
   series to draw, its sparkline and its change against the bucket before. Cells are divided by hairlines.
   docs/CONTRACT.md §43. The cells' keys are src/model.js's header.

   WHY a card of cells and not more kpi cards: Zach, 2026-10-28, on Tycoon's Shopify-like shell ("when I look at this I
   essentially just see a dashboard with 2 primary card elements"): the summary card and the table card. Shopify's
   metric strip is one card divided by hairlines, not a grid of tiles, and its numbers are plain counts of the rows
   below, so they are computed here from the same rows (src/model.js), never typed in.

   Two ways to place it:
     - `type: summary` with a `summary:` entry: a view like any other (a dashboard panel, a tab). It counts the view's
       rows (its filters, the rail, the search), as every view does.
     - `<data-summary for="orgs">` above a `<data-views id="orgs">`: an app's index page (Shopify's admin, Tycoon S6).
       It reads the top-level `summary:` of that element's `.base` file (the open view's own `summary:`, if it has one,
       wins while it is open, as a view's `facets:` wins over the file's) and counts the file's rows (`scope: all`) or
       the rows the all-views filter leaves (`scope: filtered`); never the search, which narrows the table, not the
       totals. WHY its own element and not a view in the file: the table card's view chip lists the file's views,
       and the totals are not one of them (Shopify's chip lists saved table views only).

   A click (or Enter) on a cell opens the rows behind it in the shared peek. STOCK PARTS: none (an SVG polyline). */

import { rowModel, compileFilters, summarize, summaryName, cellValue, timeBucket, nextBucket, bucketLabel, esc, fmtNum, numOpts, shortDate, isNum } from '@data-ui/core';
import css from './summary.css';
import { cellSpecs, cellOf } from './model.js';

export { css };
export { cellOf, cellSpecs } from './model.js';

const H = { compileFilters, summarize, summaryName, cellValue, timeBucket, nextBucket, bucketLabel };

// WHY the stylesheet here too: a page that only places <data-summary> never opens a `type: summary` view, so the
// registry never adds it (the kpi bundle does the same for <data-kpi>)
if (typeof document !== 'undefined' && !document.querySelector('style[data-ui-view="summary"]')) {
  const style = document.createElement('style');
  style.dataset.uiView = 'summary';
  style.textContent = css;
  document.head.append(style);
}

let uid = 0;

/** The card's markup for computed cells. */
export function summaryHtml(cells, { now = new Date() } = {}) {
  const id = `dv-sum-${++uid}`;
  return `<div class="dv-summary-card" role="list">${cells.map((c, i) => {
    const tip = c.note ? `<span class="dv-summary-tip" role="tooltip" id="${id}-${i}">${esc(c.note)}</span>` : '';
    let value, title = '';
    if (c.error) { value = '<span class="dv-summary-none">—</span>'; title = c.error; }
    else if (c.value == null) { value = '<span class="dv-summary-none">—</span>'; title = c.rows.length ? 'no value in these rows' : 'no rows'; }
    else if (c.kind === 'date') { value = esc(shortDate(c.value, now) || c.value); title = String(c.value); }
    else if (c.kind === 'number') { value = esc(String(fmtNum(c.value, undefined, numOpts(c.format)))); title = String(c.value) + (c.unit ? ` ${c.unit}` : ''); }
    else { value = esc(String(c.value)); title = String(c.value); }
    const unit = c.unit && c.value != null ? `<span class="dv-summary-unit">${esc(c.unit)}</span>` : '';
    const delta = c.delta ? `<span class="dv-summary-delta" title="${esc(`${c.delta.at}: ${fmtNum(c.series[c.series.length - 1].y)} against ${fmtNum(c.series[c.series.length - 2].y)} in ${c.delta.against}`)}">${c.delta.value > 0 ? '+' : c.delta.value < 0 ? '−' : '±'}${esc(String(fmtNum(Math.abs(c.delta.value), undefined, { digits: 3 })))} vs ${esc(c.delta.against)}</span>` : '';
    return `<div class="dv-summary-cell" role="listitem" data-i="${i}"${c.rows.length ? ' tabindex="0"' : ''}${c.note ? ` aria-describedby="${id}-${i}"` : ''}${c.error ? ' data-error' : ''}>`
      + `<span class="dv-summary-label${c.note ? ' dv-summary-defined' : ''}">${esc(c.label)}</span>${tip}`
      + `<span class="dv-summary-line"><span class="dv-summary-value" title="${esc(title)}">${value}${unit}</span>${c.series ? sparkSvg(c.series) : ''}${delta}</span></div>`;
  }).join('')}</div>`;
}

/** The cell's history as a small line; null buckets lift the pen. */
function sparkSvg(series) {
  const ys = series.map((p) => p.y);
  const nums = ys.filter(isNum);
  if (nums.length < 2) return '';
  const W = 64, Hh = 20, pad = 2;
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const x = (i) => pad + ((W - 2 * pad) * i) / (ys.length - 1);
  const y = (v) => (hi > lo ? Hh - pad - ((Hh - 2 * pad) * (v - lo)) / (hi - lo) : Hh / 2);
  let d = '', pen = false;
  ys.forEach((v, i) => { if (!isNum(v)) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
  const label = `${series.length} ${series.length === 1 ? 'bucket' : 'buckets'}, ${series[0].label} to ${series[series.length - 1].label}: ${fmtNum(lo)} to ${fmtNum(hi)}`;
  return `<svg class="dv-summary-spark" viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title><path d="${d}"></path></svg>`;
}

/** Wire a card's clicks: a cell opens its rows through `open(id, {records, title})`. */
function wire(root, cells, open) {
  const go = (e) => {
    const cell = e.target.closest && e.target.closest('.dv-summary-cell[tabindex]');
    if (!cell || !root.contains(cell)) return;
    const c = cells()[Number(cell.dataset.i)];
    if (c && c.rows.length) open(c.rows[0].id, { records: c.rows, title: c.label });
  };
  root.addEventListener('click', go);
  root.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { if (e.target.matches('.dv-summary-cell[tabindex]')) { e.preventDefault(); go(e); } } });
}

export default class SummaryView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.cells = [];
    el.innerHTML = '<div class="dv-summary-wrap"></div>';
    wire(el, () => this.cells, (id, opts) => host.open(id, opts));
  }

  destroy() { this.host.setStatus(''); this.el.innerHTML = ''; }

  update(input) {
    const specs = cellSpecs(input.view.summary);
    this.cells = specs.map((c) => cellOf(input.rows, input.columns, c, H));
    const wrap = this.el.querySelector('.dv-summary-wrap');
    wrap.innerHTML = specs.length ? summaryHtml(this.cells) : '<p class="dv-summary-empty">No cells: this view needs <code>summary: {cells: [{label, value?, filters?, when?}]}</code>.</p>';
    const bad = this.cells.filter((c) => c.error);
    this.host.setStatus(bad.length ? `<span class="dv-err">${esc(bad.map((c) => `${c.label}: ${c.error}`).join(' · '))}</span>` : '');
  }
}

/** <data-summary for="views-id">: the summary card of a <data-views>' file, outside its box (above the table card). */
export class DataSummary extends HTMLElement {
  connectedCallback() { customElements.whenDefined('data-views').then(() => this._attach()); }

  disconnectedCallback() {
    if (this._target) for (const t of ['data-views-change', 'data-views-render']) this._target.removeEventListener(t, this._onChange);
  }

  get target() { return this._target || null; }
  /** The computed cells (what the card shows): [{label, note, kind, value, rows, error?, series?, delta?}]. */
  get cells() { return this._cells || []; }

  _attach() {
    if (!this.isConnected) return;
    const id = this.getAttribute('for');
    const target = id ? document.getElementById(id) : null;
    if (!target) { requestAnimationFrame(() => this._attach()); return; }
    if (this._target) for (const t of ['data-views-change', 'data-views-render']) this._target.removeEventListener(t, this._onChange);
    this._target = target;
    this._onChange = () => this._draw();
    for (const t of ['data-views-change', 'data-views-render']) target.addEventListener(t, this._onChange);
    if (!this._wired) {
      this._wired = true;
      wire(this, () => this.cells, (rowId, opts) => this._target && this._target.openPeek(rowId, opts));
    }
    this._draw();
  }

  _draw() {
    const t = this._target;
    if (!t || !t.data || !t.base) return;
    const spec = (t.view && t.view.summary) || t.base.summary;
    const specs = cellSpecs(spec);
    // the key: a redraw only when what the cells read changed (data revision, the filter if it is followed, the spec)
    const filtered = spec && spec.scope === 'filtered';
    const key = JSON.stringify([t.dataRevision, filtered ? t.filters ?? null : null, spec || null]);
    if (key === this._key && t.data === this._data) return;
    this._key = key;
    this._data = t.data;
    const model = rowModel(t.data, t.base, { type: 'table', name: 'summary' }, { filters: filtered ? t.filters : undefined });
    this._cells = specs.map((c) => cellOf(model.rows, model.columns, c, H));
    this.innerHTML = specs.length ? summaryHtml(this._cells) : '';
    this.hidden = !specs.length;
    this.dispatchEvent(new CustomEvent('data-summary-render', { detail: { cells: this._cells.map(({ label, value, kind, rows, error }) => ({ label, value, kind, n: rows.length, error })) }, bubbles: true }));
  }
}

if (typeof customElements !== 'undefined' && !customElements.get('data-summary')) customElements.define('data-summary', DataSummary);
