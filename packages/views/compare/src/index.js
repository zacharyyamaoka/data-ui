/* type: compare — 2 to 6 rows side by side: one column per row, one line per property, the better value marked by
   each property's direction, "differences only", and a photo pair as a slider (docs/VIEWS.md "Compare").

   Keys: data-ui's `compare {rows: [ids] | "selection", better: {property: higher | lower}, diffOnly}`; Bases' `order`
   (the properties, top to bottom). With no `rows`, the view's first four rows; with "selection", the rows you pick
   here. Adding or removing a column writes `compare.rows` (host.setView), so a pick is a view you can save.

   STOCK PARTS: @tanstack/table-core 9.3.1 (the page's one copy, through @data-ui/core's tableModel) on the transposed
   rows: one row per property, one column per record. img-comparison-slider 8.0.7 (MIT, a 4 KB web component) for the
   photo pair. OURS: the transpose, best-value marks, diff-only, the column picker. */

import 'img-comparison-slider';
import sliderCss from 'img-comparison-slider/dist/styles.css';
import { tableModel, cellValue, cellText, linkCell, esc, valueHtml, valueText, mediaUrl, hueOf, isEmpty, isNum } from '@data-ui/core';
import compareCss from './compare.css';

export const css = `${sliderCss}\n${compareCss}`;

const MAX = 6;
const DEFAULT = 4;

export function options() {
  return [{ type: 'toggle', key: 'compare.diffOnly', displayName: 'Differences only' }];
}

export default class CompareView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._picked = [];
    this._pair = [0, 1];
    el.innerHTML = '<div class="dv-cmp-bar"></div><div class="dv-scroll dv-cmp-scroll" tabindex="-1"><table class="dv-cmp"><thead></thead><tbody></tbody></table></div>';
    this.$ = (s) => el.querySelector(s);
    this._wire();
  }

  destroy() { this.el.innerHTML = ''; }

  _conf() { return this.input.view.compare || {}; }

  /** The ids being compared, in column order. */
  _ids() {
    const c = this._conf();
    if (Array.isArray(c.rows)) return c.rows.map(String);
    if (c.rows === 'selection') return this._picked;
    return this.input.rows.slice(0, DEFAULT).map((r) => String(r.id));
  }

  _titleOf(r) {
    const t = cellValue(r[this.input.dataset.titleProperty]);
    return isEmpty(t) ? String(r.id) : cellText(r[this.input.dataset.titleProperty]) ?? (Array.isArray(t) ? t.join(', ') : String(t));
  }

  _imageProp() {
    const { dataset, columns, view } = this.input;
    if (dataset.imageProperty && columns[dataset.imageProperty]) return dataset.imageProperty;
    return Object.keys(columns).find((id) => ((view.display && view.display[id]) || columns[id].display) === 'image' || columns[id].media === 'image') || null;
  }

  update(input) {
    this.input = input;
    const { columns, dataset, view } = input;
    // a pick belongs to the view it was made in: another preset starts from its own compare.rows
    if (view.name !== this._viewName) { this._picked = []; this._pair = [0, 1]; this._viewName = view.name; }
    const byId = new Map(input.rows.map((r) => [String(r.id), r]));
    const ids = this._ids();
    this._records = ids.map((id) => byId.get(id)).filter(Boolean);
    this._missing = ids.filter((id) => !byId.has(id));
    const image = this._imageProp();
    const unitCols = new Set(Object.values(columns).map((p) => p.unit).filter(Boolean));
    const skip = new Set([dataset.titleProperty, image, dataset.linkProperty]);
    const props = (view.order && view.order.length ? view.order : Object.keys(columns).filter((id) => !columns[id].hidden))
      .filter((id) => columns[id] && !skip.has(id) && !unitCols.has(id));
    // the transpose: one row per property, a column c<i> per record; TanStack keeps the order and is where a sort
    // or a grouping of properties would go
    const recs = this._records;
    const tRows = props.map((id) => ({ id, ...Object.fromEntries(recs.map((r, i) => [`c${i}`, r[id]])) }));
    const tProps = { id: { id: 'id', type: 'text', label: 'Property' }, ...Object.fromEntries(recs.map((r, i) => [`c${i}`, { id: `c${i}`, type: 'text', label: this._titleOf(r) }])) };
    this._table = tableModel(tRows, tProps, {});
    this._image = image;
    this._render();
  }

  _better(id) {
    const c = this._conf();
    const dir = (c.better && c.better[id]) || this.input.columns[id].better;
    return dir === 'higher' || dir === 'lower' ? dir : null;
  }

  _cellHtml(r, p) {
    const view = this.input.view;
    const display = (view.display && view.display[p.id]) || p.display || 'text';
    const raw = r[p.id];
    const v = cellValue(raw);
    if (!isEmpty(v) && display === 'badge' && cellText(raw) !== null) return `<span class="dv-badge dv-h${hueOf(cellText(raw))}">${esc(cellText(raw))}</span>`;
    if (!isEmpty(v) && display === 'badge') return (Array.isArray(v) ? v : [v]).map((x) => `<span class="dv-badge dv-h${p.colors && p.colors[x] != null ? p.colors[x] : hueOf(x)}">${esc(x)}</span>`).join(' ');
    if (!isEmpty(v) && display === 'link' && !Array.isArray(v)) return linkCell(raw);
    return valueHtml(raw, p, { unit: p.unit ? r[p.unit] : undefined });
  }

  _render() {
    const { columns, rows, dataset } = this.input;
    const c = this._conf();
    const recs = this._records;
    const ids = recs.map((r) => String(r.id));
    const rest = rows.filter((r) => !ids.includes(String(r.id)));
    const add = recs.length < MAX && rest.length
      ? `<label class="dv-cmp-add"><span class="dv-sr">Add a row</span><select data-add><option value="">+ Add a row…</option>${rest.slice(0, 500).map((r) => `<option value="${esc(r.id)}">${esc(this._titleOf(r))}</option>`).join('')}</select></label>` : '';
    const missing = this._missing.length ? `<span class="dv-cmp-note">Not in this view's rows: ${this._missing.map(esc).join(', ')}</span>` : '';
    this.$('.dv-cmp-bar').innerHTML = `<span class="dv-count">${recs.length < 2 ? `${recs.length} picked` : `${recs.length} side by side`}</span>${add}<button type="button" class="dv-btn${c.diffOnly ? ' dv-on' : ''}" data-diff aria-pressed="${!!c.diffOnly}">Differences only</button>${missing}`;
    this.el.classList.toggle('dv-cmp-few', recs.length < 2);
    if (recs.length < 2) {
      this.$('thead').innerHTML = '';
      this.$('tbody').innerHTML = `<tr><td class="dv-empty">Pick 2 to ${MAX} rows to compare${recs.length ? ` (${esc(this._titleOf(recs[0]))} so far)` : ''}.</td></tr>`;
      return;
    }
    const link = (r) => (dataset.linkProperty && !isEmpty(cellValue(r[dataset.linkProperty])) ? ` <a class="dv-cmp-link" href="${esc(cellValue(r[dataset.linkProperty]))}" rel="noopener" aria-label="Open the page of ${esc(this._titleOf(r))}">↗</a>` : '');
    const head = recs.map((r, i) => `<th scope="col" data-r="${i}"><div class="dv-cmp-h"><button type="button" class="dv-link dv-cmp-open" data-open="${esc(r.id)}">${esc(this._titleOf(r))}</button>${link(r)}<button type="button" class="dv-btn dv-x" data-remove="${esc(r.id)}" aria-label="Remove ${esc(this._titleOf(r))}">✕</button></div></th>`).join('');
    this.$('thead').innerHTML = `<tr><th scope="col" class="dv-cmp-prop">Property</th>${head}</tr>`;
    let body = '';
    const img = this._image;
    if (img) {
      const srcs = recs.map((r) => { const s = cellValue(r[img]); return isEmpty(s) || Array.isArray(s) ? s : mediaUrl(s, dataset); });
      const withImg = srcs.map((s, i) => (isEmpty(s) || Array.isArray(s) ? null : i)).filter((i) => i !== null);
      body += `<tr class="dv-cmp-photos"><th scope="row">${esc(columns[img].label)}</th>${srcs.map((s) => `<td>${isEmpty(s) || Array.isArray(s) ? '<span class="dv-none" title="no photo">—</span>' : `<img src="${esc(s)}" alt="" loading="lazy">`}</td>`).join('')}</tr>`;
      if (withImg.length >= 2) {
        const [a, b] = this._pair.every((i) => withImg.includes(i)) && this._pair[0] !== this._pair[1] ? this._pair : [withImg[0], withImg[1]];
        this._pair = [a, b];
        const pick = (k, cur) => `<select data-pair="${k}" aria-label="${k ? 'Right' : 'Left'} photo">${withImg.map((i) => `<option value="${i}"${i === cur ? ' selected' : ''}>${esc(this._titleOf(recs[i]))}</option>`).join('')}</select>`;
        body += `<tr class="dv-cmp-slide"><th scope="row">Slide<div class="dv-cmp-pair">${pick(0, a)}<span>vs</span>${pick(1, b)}</div></th><td colspan="${recs.length}"><img-comparison-slider class="dv-cmp-slider" tabindex="0"><img slot="first" src="${esc(srcs[a])}" alt="${esc(this._titleOf(recs[a]))}"><img slot="second" src="${esc(srcs[b])}" alt="${esc(this._titleOf(recs[b]))}"></img-comparison-slider><div class="dv-cmp-sliderlabels"><span>${esc(this._titleOf(recs[a]))}</span><span>${esc(this._titleOf(recs[b]))}</span></div></td></tr>`;
      }
    }
    let same = 0;
    for (const row of this._table.getRowModel().rows) {
      const id = row.original.id;
      const p = columns[id];
      const values = recs.map((r) => cellValue(r[id]));
      const texts = values.map((v) => valueText(v, p));
      const alike = texts.every((t) => t === texts[0]);
      if (alike) same++;
      if (alike && c.diffOnly) continue;
      const dir = this._better(id);
      const nums = values.filter(isNum);
      let best = null;
      if (dir && nums.length >= 2 && Math.min(...nums) !== Math.max(...nums)) best = dir === 'higher' ? Math.max(...nums) : Math.min(...nums);
      const unit = p.unitText && !p.unit ? ` <span class="dv-unit">${esc(p.unitText)}</span>` : '';
      const cells = recs.map((r, i) => {
        const on = best !== null && values[i] === best;
        const num = p.type === 'number' ? ' dv-num' : '';
        return `<td class="${on ? 'dv-cmp-best' : ''}${num}" data-r="${i}"${on ? ` title="Best of ${nums.length}: ${dir} is better"` : ''}>${this._cellHtml(r, p)}${on ? '<span class="dv-sr"> (best)</span>' : ''}</td>`;
      }).join('');
      body += `<tr class="dv-cmp-row${alike ? ' dv-cmp-same' : ''}" data-p="${esc(id)}"><th scope="row" title="${esc((p.note || '') + (dir ? `${p.note ? ' · ' : ''}${dir} is better` : ''))}">${esc(p.label)}${unit}${dir ? `<span class="dv-cmp-dir" aria-label="${dir} is better">${dir === 'higher' ? '↑' : '↓'}</span>` : ''}</th>${cells}</tr>`;
    }
    if (c.diffOnly && same) body += `<tr class="dv-cmp-hidden"><td colspan="${recs.length + 1}">${same} ${same === 1 ? 'property is' : 'properties are'} the same on every row, hidden (Differences only).</td></tr>`;
    this.$('tbody').innerHTML = body;
    this.$('.dv-cmp').style.setProperty('--dv-cmp-n', recs.length);
  }

  _write(ids) {
    const c = this._conf();
    this._picked = ids;
    // WHY 'selection' below two: the grammar allows 2-6 ids; one pick is kept here until it has a partner
    this.host.setView({ compare: { ...c, rows: ids.length >= 2 ? ids.slice(0, MAX) : 'selection' } });
  }

  _wire() {
    this.el.addEventListener('click', (e) => {
      const rm = e.target.closest('[data-remove]');
      if (rm) { this._write(this._records.map((r) => String(r.id)).filter((id) => id !== rm.dataset.remove)); return; }
      const open = e.target.closest('[data-open]');
      if (open) { this.host.open(open.dataset.open); return; }
      if (e.target.closest('[data-diff]')) this.host.setView({ compare: { ...this._conf(), diffOnly: !this._conf().diffOnly } });
    });
    this.el.addEventListener('change', (e) => {
      const add = e.target.closest('[data-add]');
      if (add && add.value) { this._write([...this._records.map((r) => String(r.id)), add.value]); return; }
      const pair = e.target.closest('[data-pair]');
      if (pair) {
        this._pair[Number(pair.dataset.pair)] = Number(pair.value);
        this._render();
      }
    });
  }
}
