/* type: record — one row as a property sheet, the record page every view's peek is a narrow copy of (docs/VIEWS.md
   "Record / peek / detail page"); with `edit: true` the same sheet as a form (the core's form.js).

   The host's side peek (host.open, in the core) shows one row's fields in 540 px beside any view. This is that sheet
   at full width, generalised: sections from `record.sections`, each value with its unit, basis mark and provenance
   line, every value behind it (dataset.detail) with the clicked field's entries marked, the row's image and link. With
   more than one row the rows are listed beside it (a select on a phone), so the sheet steps through a view's rows.
   The side peek reads the same `record.sections` and `edit` (the core's peek, amendment 2026-10-26 (core pass)), so
   the narrow and the wide sheet show one record one way.

   Keys: data-ui's `record {sections: [{name, properties}], visibility}`, `edit`; Bases' `order` (the fields when there are no
   sections, the rest behind "N more properties": the inspector, CONTRACT §44), plus every view's filters, sort, groupBy
   (headings in the row list) and limit.
   STOCK PARTS: none (docs/VIEWS.md: no framework-free sheet worth taking); the form is the core's (form.js). Writes
   back only through the host: propose({id, set}) from the form. */

import { cellValue, cellText, linkCell, esc, isEmpty, valueHtml, mediaUrl, groupLabel, BASIS, fieldHtml, readEdits, lockedBecause, sourcesAttr, isMultiSource, agreement, formulaView, inspectorProperties, moreHtml, visibilityButton, addPropertyHtml } from '@data-ui/core';
import css from './record.css';

export { css };

export function options() {
  return [{ type: 'toggle', key: 'edit', displayName: 'Edit fields (a form)' }];
}

export default class RecordView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._sel = null;
    this._column = null;
    this._msg = null;
    el.innerHTML = `<div class="dv-record">
      <nav class="dv-record-list" aria-label="Rows"></nav>
      <div class="dv-record-main"><label class="dv-record-pick"><span class="dv-sr">Row</span><select></select></label><article class="dv-record-sheet"></article></div>
    </div>`;
    this.$ = (s) => el.querySelector(s);
    this._wire();
  }

  destroy() { this.el.innerHTML = ''; }

  update(input) {
    this.input = input;
    const ids = input.rows.map((r) => String(r.id));
    if (this._sel === null || !ids.includes(this._sel)) { this._sel = ids[0] ?? null; this._column = null; }
    this._drawList();
    this._drawSheet();
  }

  _row() {
    return this.input.rows.find((r) => String(r.id) === this._sel) || null;
  }

  _titleOf(r) {
    const t = cellValue(r[this.input.dataset.titleProperty]);
    return isEmpty(t) ? String(r.id) : cellText(r[this.input.dataset.titleProperty]) ?? (Array.isArray(t) ? t.join(', ') : String(t));
  }

  _drawList() {
    const { rows, groups, columns } = this.input;
    const many = rows.length > 1;
    this.el.querySelector('.dv-record').classList.toggle('dv-record-one', !many);
    const item = (r) => `<li><button type="button" class="dv-record-item${String(r.id) === this._sel ? ' dv-on' : ''}" data-id="${esc(r.id)}"${String(r.id) === this._sel ? ' aria-current="true"' : ''}>${esc(this._titleOf(r))}</button></li>`;
    const head = (g) => `<li class="dv-record-group">${esc(groupLabel(columns, g.property, g.key))} <span class="dv-count">${g.rows.length}</span></li>`;
    const flat = groups ? groups.flatMap((g) => (g.groups ? g.groups.flatMap((s) => [s, ...s.rows]) : [g, ...g.rows])) : rows;
    this.$('.dv-record-list').innerHTML = many ? `<ol>${flat.map((x) => (x.rows ? head(x) : item(x))).join('')}</ol>` : '';
    this.$('.dv-record-pick select').innerHTML = many ? rows.map((r) => `<option value="${esc(r.id)}"${String(r.id) === this._sel ? ' selected' : ''}>${esc(this._titleOf(r))}</option>`).join('') : '';
    const on = this.$('.dv-record-item.dv-on');
    if (on) on.scrollIntoView({ block: 'nearest' });
  }

  /** The sheet: {sections, more}. record.sections, else one section of what the inspector shows (CONTRACT §44, the side peek's rule,
      from one function), `more` waiting behind "N more properties"; a form lists every field, where the row is written. */
  _sections(r) {
    const { view, columns, dataset } = this.input;
    const given = view.record && Array.isArray(view.record.sections) ? view.record.sections : null;
    const edit = !!view.edit && !this.input.viewOnly;
    const lists = given ? given.map((s) => ({ name: s.name, ids: (s.properties || []).filter((id) => columns[id]) })) : null;
    const plan = inspectorProperties({ view, columns, titleProperty: dataset.titleProperty, row: r, listed: lists ? lists.flatMap((s) => s.ids) : null, exclude: dataset.detail ? [dataset.detail.property] : [] });
    if (edit) return { sections: lists || [{ name: null, ids: [...plan.shown, ...plan.more] }], more: [] };
    return { sections: lists ? lists.map((s) => ({ ...s, ids: s.ids.filter((id) => plan.shown.includes(id)) })) : [{ name: null, ids: plan.shown }], more: plan.more };
  }

  _drawSheet() {
    const sheet = this.$('.dv-record-sheet');
    const r = this._row();
    if (!r) { sheet.innerHTML = '<p class="dv-empty dv-record-empty">No rows match this view.</p>'; return; }
    const { view, columns, dataset, rows } = this.input;
    // CONTRACT §40: in View an edit-toggle page's record is words, not a form
    const edit = !!view.edit && !this.input.viewOnly;
    const at = rows.findIndex((x) => String(x.id) === this._sel);
    const link = dataset.linkProperty && !isEmpty(cellValue(r[dataset.linkProperty])) ? `<a class="dv-peeklink" href="${esc(cellValue(r[dataset.linkProperty]))}" rel="noopener">Open page ↗</a>` : '';
    const steps = rows.length > 1 ? `<span class="dv-record-steps"><button type="button" class="dv-btn" data-step="-1" aria-label="Previous row"${at <= 0 ? ' disabled' : ''}>‹</button><span class="dv-count">${at + 1} of ${rows.length}</span><button type="button" class="dv-btn" data-step="1" aria-label="Next row"${at >= rows.length - 1 ? ' disabled' : ''}>›</button></span>` : '';
    const img = dataset.imageProperty && cellValue(r[dataset.imageProperty]);
    const image = !isEmpty(img) && !Array.isArray(img) ? `<figure class="dv-record-image"><img src="${esc(mediaUrl(img, dataset))}" alt="${esc(this._titleOf(r))}" loading="lazy"></figure>` : '';
    const unitOf = (p) => (p.unit ? r[p.unit] : undefined);
    const fieldRow = (id) => {
      const p = columns[id];
      const hot = id === this._column ? ' dv-active' : '';
      // CONTRACT §36: the agree / differs fact stays with the value, as in the side peek; its sources are the field's right-click
      const pr = this.input.precedence;
      const facts = pr && !edit && isMultiSource(r[id]) ? agreement(r[id], formulaView(pr, pr, id), r.id) : null;
      const body = edit ? fieldHtml(r, p, { unit: unitOf(p) }) : `${this._valueCell(r, p, unitOf(p))}${facts ? `<span class="dv-src-note">${esc(facts.text)}</span>` : ''}`;
      const label = edit && !lockedBecause(p) ? `<label for="dv-f-${esc(id)}">${esc(p.label)}</label>` : esc(p.label);
      // CONTRACT §36, the source popover: a value two or more sources state marks its field, a tab stop so the menu key
      // reaches it (the sheet's fields are none otherwise); its item menu lists the sources. Not in the form
      const src = edit ? '' : sourcesAttr(r[id], r.id, id, { focusable: true });
      const vis = edit ? '' : visibilityButton(el, id, p.label);
      return `<tr class="dv-record-field${hot}" data-p="${esc(id)}"${src}><th scope="row" title="${esc(p.note || '')}">${label}${vis}</th><td>${body}</td></tr>`;
    };
    const el = this.host.element;
    const plan = this._sections(r);
    const list = plan.sections.filter((s) => s.ids.length).map((s) => `<section class="dv-record-section">${s.name ? `<h3>${esc(s.name)}</h3>` : ''}<table class="dv-fields"><tbody>${s.ids.map(fieldRow).join('')}</tbody></table></section>`).join('');
    const sections = list + moreHtml(plan.more.map(fieldRow).join(''), plan.more.length, !!el._propMore) + (edit ? '' : addPropertyHtml(el));
    const msg = this._msg && this._msg.id === this._sel ? `<p class="dv-form-msg${this._msg.ok ? '' : ' dv-refused'}" role="${this._msg.ok ? 'status' : 'alert'}">${esc(this._msg.text)}</p>` : '<p class="dv-form-msg" role="status"></p>';
    const body = edit
      ? `<form class="dv-form" novalidate>${sections}<div class="dv-form-bar"><button type="submit" class="dv-btn dv-primary">Save changes</button><button type="reset" class="dv-btn">Revert</button>${msg}</div></form>`
      : sections;
    // §44, the slot: what is not one property of the record goes under them, the host's own part (peekExtra) last, as in the peek
    const extra = typeof el.peekExtra === 'function' ? el.peekExtra(r) : '';
    sheet.innerHTML = `<header class="dv-record-head"><h2>${esc(this._titleOf(r))}</h2>${link}${steps}</header>${image}${body}<div class="dv-peek-slot">${this._behind(r)}${extra ? `<div class="dv-peek-extra">${extra}</div>` : ''}</div>`;
  }

  /** A value on the record page: the value with its unit and basis mark, then its provenance in words. */
  _valueCell(r, p, unit) {
    const cell = r[p.id];
    const view = this.input.view;
    const display = (view.display && view.display[p.id]) || p.display;
    const v = cellValue(cell);
    let html;
    if (display === 'image' && !isEmpty(v) && !Array.isArray(v)) html = `<img class="dv-record-thumb" src="${esc(mediaUrl(v, this.input.dataset))}" alt="" loading="lazy">`;
    else if (display === 'link' && !isEmpty(v) && !Array.isArray(v)) html = linkCell(cell);
    else html = valueHtml(cell, p, { unit, dataset: this.input.dataset });
    const rich = cell !== null && typeof cell === 'object' && !Array.isArray(cell) ? cell : null;
    if (!rich) return html;
    const basis = rich.basis ? (BASIS[rich.basis] ? BASIS[rich.basis].label : rich.basis) : '';
    const meta = [basis, rich.source, rich.asOf ? `as of ${rich.asOf}` : '', rich.n != null ? `n = ${rich.n}` : '', rich.note, isEmpty(rich.value) && rich.why ? rich.why : '']
      .filter((x) => !isEmpty(x)).map((x) => `<span>${esc(x)}</span>`).join('');
    return meta ? `${html}<div class="dv-record-meta">${meta}</div>` : html;
  }

  /** Every value behind the row (dataset.detail), the selected field's entries marked; the peek's list, at full width. */
  _behind(r) {
    const d = this.input.dataset.detail;
    if (!d || !Array.isArray(r[d.property]) || !r[d.property].length) return '';
    const entries = r[d.property];
    const want = this._column && d.columnKinds ? d.columnKinds[this._column] : null;
    const line = d.columns.filter((c) => !c.block);
    const blocks = d.columns.filter((c) => c.block);
    const val = (x, c) => (c.link && x[c.link] ? `<a href="${esc(x[c.link])}" rel="noopener">${esc(x[c.id] ?? '')}</a>` : esc(x[c.id] ?? ''));
    return `<section class="dv-record-section"><h3>Every value behind it <span class="dv-count">${entries.length}</span></h3><ol class="dv-entries">${entries.map((x) => `<li class="dv-entry${want && x[d.kind] === want ? ' dv-active' : ''}"><div class="dv-entry-line">${line.filter((c) => !isEmpty(x[c.id])).map((c, i) => `<span class="${i === 0 ? 'dv-entry-kind' : ''}" title="${esc(c.label)}">${val(x, c)}</span>`).join('')}</div>${blocks.filter((c) => !isEmpty(x[c.id])).map((c) => `<p><span class="dv-entry-label">${esc(c.label)}</span> ${val(x, c)}</p>`).join('')}</li>`).join('')}</ol></section>`;
  }

  _select(id) {
    if (id === this._sel) return;
    this._sel = String(id);
    this._column = null;
    this._drawList();
    this._drawSheet();
    this.$('.dv-record-main').scrollTop = 0;
  }

  _wire() {
    this.el.addEventListener('click', (e) => {
      const item = e.target.closest('.dv-record-item');
      if (item) { this._select(item.dataset.id); return; }
      const step = e.target.closest('[data-step]');
      if (step) {
        const rows = this.input.rows;
        const at = rows.findIndex((x) => String(x.id) === this._sel) + Number(step.dataset.step);
        if (rows[at]) this._select(rows[at].id);
        return;
      }
 // the inspector's own buttons are the element's (core inspector.js)
      if (e.target.closest('[data-prop-vis], [data-prop-more], [data-prop-add]')) return;
      const field = e.target.closest('.dv-record-field');
      if (field && (!this.input.view.edit || this.input.viewOnly) && !e.target.closest('a')) {
        // WHY a click marks the field and its entries instead of opening the side peek: this page is the peek, wide
        this._column = this._column === field.dataset.p ? null : field.dataset.p;
        this._drawSheet();
        const hot = this.el.querySelector('.dv-entry.dv-active');
        if (hot) hot.scrollIntoView({ block: 'nearest' });
      }
    });
    this.$('.dv-record-pick select').addEventListener('change', (e) => this._select(e.target.value));
    this.el.addEventListener('keydown', (e) => {
      const item = e.target.closest && e.target.closest('.dv-record-item');
      if (!item || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return;
      e.preventDefault();
      const all = [...this.el.querySelectorAll('.dv-record-item')];
      const next = all[all.indexOf(item) + (e.key === 'ArrowDown' ? 1 : -1)];
      if (next) { this._select(next.dataset.id); this.el.querySelector(`.dv-record-item[data-id="${CSS.escape(next.dataset.id)}"]`).focus(); }
    });
    this.el.addEventListener('input', (e) => {
      const tr = e.target.closest && e.target.closest('.dv-record-field');
      if (tr) tr.classList.add('dv-changed');
    });
    this.el.addEventListener('reset', () => {
      this._msg = null;
      requestAnimationFrame(() => this._drawSheet());
    });
    this.el.addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const r = this._row();
      if (!r) return;
      const msg = form.querySelector('.dv-form-msg');
      if (!form.reportValidity()) return;
      const set = readEdits(form, r, this.input.columns);
      if (!Object.keys(set).length) { msg.className = 'dv-form-msg'; msg.textContent = 'Nothing changed.'; return; }
      const id = this._sel;
      const result = await this.host.propose({ id: r.id, set });
      const n = Object.keys(set).length;
      this._msg = { id, ok: !!(result && result.ok), text: result && result.ok ? `Saved ${n} ${n === 1 ? 'field' : 'fields'}.` : `Not saved: ${(result && result.reason) || 'the host refused the edit.'}` };
      // WHY redraw only on ok: the host re-rendered with the edited rows; a refusal keeps what was typed
      if (this._msg.ok) this._drawSheet();
      else { msg.className = 'dv-form-msg dv-refused'; msg.setAttribute('role', 'alert'); msg.textContent = this._msg.text; }
    });
  }
}
