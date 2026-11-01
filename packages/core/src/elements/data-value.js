/* <data-value>: one value with its unit and provenance (docs/SPEC.md §4.3, §9.2).

     <data-value value="3.82" unit="N·m" basis="datasheet" source="steadywin.cn" as-of="2026-10-22">3.82 N·m</data-value>
     <data-value why="not measured"></data-value>

   The text content is the no-JS truth (a server writes it; tests and search engines read it). With JavaScript the
   element redraws it in the shared markup (format.js valueHtml): the number at 4 significant figures, the unit,
   the basis mark, a range (low, high), and source, as-of, n and note on hover. Without a `value` attribute it keeps
   its text and adds only the mark and the hover. Attributes: value, unit, basis, source, as-of, low, high, n,
   note, why, decimals, and (for the right-click popover, CONTRACT §22) source-url, source-page, record. Property `cell` takes a rich cell object directly. */

import { valueHtml, provenanceAttr, BASIS, esc } from '../format.js';

const num = (s) => (s === null || s === '' || Number.isNaN(Number(s)) ? s : Number(s));

export class DataValue extends HTMLElement {
  static get observedAttributes() { return ['value', 'unit', 'basis', 'source', 'as-of', 'low', 'high', 'n', 'note', 'why', 'decimals', 'source-url', 'source-page', 'record']; }

  set cell(c) { this._cell = c; this._draw(); }
  get cell() { return this._cell || this._fromAttributes(); }

  connectedCallback() { this._draw(); }

  attributeChangedCallback() { if (this.isConnected) this._draw(); }

  _fromAttributes() {
    const a = (n) => this.getAttribute(n);
    const has = this.hasAttribute('value');
    const cell = { value: has ? num(a('value')) : this._text || null };
    for (const [attr, key] of [['basis', 'basis'], ['source', 'source'], ['as-of', 'asOf'], ['source-url', 'sourceUrl'], ['source-page', 'sourcePage'], ['record', 'record'], ['note', 'note'], ['why', 'why'], ['unit', 'unit']]) if (a(attr) !== null) cell[key] = a(attr);
    for (const k of ['low', 'high', 'n']) if (a(k) !== null) cell[k] = num(a(k));
    if (this.hasAttribute('why') && !has) cell.value = null;
    return cell;
  }

  _draw() {
    // WHY here: an upgraded element hears its attributes before connectedCallback; the server's text comes first
    if (this._text === undefined) this._text = this.textContent.trim();
    const cell = this.cell;
    const decimals = this.hasAttribute('decimals') ? Number(this.getAttribute('decimals')) : undefined;
    if (!this.hasAttribute('value') && !this._cell && cell.value) {
      // keep the server's text; add the basis mark and the hover only
      const b = cell.basis ? BASIS[cell.basis] : null;
      const title = [cell.basis && `${cell.basis}${b ? ': ' + b.means : ''}`, cell.source && `source: ${cell.source}`, cell.asOf && `as of ${cell.asOf}`, cell.note].filter(Boolean).join('\n');
      this.innerHTML = `<span class="dv-value"${title ? ` title="${esc(title)}"` : ''}${provenanceAttr(cell, this._text, cell.unit || '')}>${esc(this._text)}${cell.basis ? `<span class="dv-basis dv-basis-${esc(cell.basis)}" aria-label="${esc(cell.basis)}">${esc(b ? b.mark : '?')}</span>` : ''}</span>`;
      return;
    }
    this.innerHTML = valueHtml(cell, { decimals }, {});
  }
}

if (!customElements.get('data-value')) customElements.define('data-value', DataValue);
