/* Editing in the table (docs/CONTRACT.md §37), excel-like: a click on a cell of an editable property opens an editor over
   it, Enter or leaving it commits through host.propose, Esc cancels, Tab moves on. And the add row: the same cells above the
   rows, filing through host.add.

   WHY an overlay and not an input in the <td>: the rows are virtualised and rebuilt from strings on every update, so an
   input in a row dies with any redraw (a push from the host, a scroll), taking the typing and the focus with it; and a cell
   that grows while it is typed in moves every row under the pointer. The overlay is a sibling of the table inside the
   scroller: a redraw never touches it, the sheet does not move, and it can be wider and taller than its cell, as Excel's and
   Sheets' editors are. The add row stays one <tr> in the <thead> across redraws for the same reason (index.js keeps it).

   A media cell (display: media) is words plus any number of images and videos in one cell: `{value, attachments}`. Its file
   goes through host.attach (paste, drop or the quiet "+ image or video"); data-ui stores no bytes. */

import { esc, cellValue, isEmpty, fieldHtml, readEdits, lockedBecause, attachmentsOf, mediaUrl, fits, coerceCell, kindOf, isDerivedCell, withValue } from '@data-ui/core';

import { growInPlace, surfaceOf } from './cell-surface.js';

export const ADD_MEDIA = '+ image or video';

/** The choices a `cycle: true` column steps through (its labels' keys, else constraints.enum), or null. */
export function cycleOf(p) {
  if (!p.cycle) return null;
  const list = p.labels ? Object.keys(p.labels) : p.constraints && p.constraints.enum;
  return Array.isArray(list) && list.length ? list.map(String) : null;
}

/** What a media or text box holds of its files, each with its remove button. */
function draftThumbs(list, dataset) {
  if (!list.length) return '';
  return `<div class="dv-ed-thumbs">${list.map((a, i) => `<span class="dv-ed-thumb">${a.kind === 'video' ? '<span class="dv-ed-video">video</span>' : a.url ? `<img src="${esc(mediaUrl(a.url, dataset))}" alt="" draggable="false">` : '<span class="dv-ed-video">away</span>'}<button type="button" class="dv-ed-x" data-unattach="${i}" aria-label="Remove this attachment" title="Remove">×</button></span>`).join('')}</div>`;
}

/** §46: a list cell ("a, b, c") suggests what the column already holds, for the word being typed: the browser's own datalist, each option the
    whole text so far. WHY the whole text: a datalist completes the input, not its last word. */
function listHints(form, p, rows) {
  const input = p.type === 'list' ? form.querySelector('input[type="text"]') : null;
  if (!input) return;
  const named = [...(p.options || []).map((o) => (o && o.name) || o), ...((p.constraints && p.constraints.enum) || [])];
  const known = [...new Set([...named, ...rows.flatMap((r) => (Array.isArray(r[p.id]) ? r[p.id] : []))])].filter(Boolean).map(String).sort();
  const list = document.createElement('datalist');
  list.id = `dv-dl-${p.id}`;
  form.append(list);
  input.setAttribute('list', list.id);
  input.autocomplete = 'off';
  const fill = () => {
    const parts = input.value.split(',').map((x) => x.trim());
    const word = parts.pop().toLowerCase();
    const head = parts.filter(Boolean);
    const before = head.length ? `${head.join(', ')}, ` : '';
    list.innerHTML = known.filter((k) => !head.includes(k) && k.toLowerCase().startsWith(word)).slice(0, 30).map((k) => `<option value="${esc(before + k)}"></option>`).join('');
  };
  input.addEventListener('input', fill);
  fill();
}

/** The box his sheet shows: a white rounded box, the word, and a quiet "+ image or video" at its bottom right. */
function boxHtml({ name, value, placeholder, media, attach, dataset, msg = '' }) {
  const foot = attach ? `<button type="button" class="dv-mc-add dv-ed-pick" data-pick tabindex="-1">${ADD_MEDIA}</button>` : '';
  return `<div class="dv-ed-box"><textarea name="${esc(name)}" rows="1" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" spellcheck="true">${esc(value)}</textarea>${draftThumbs(media, dataset)}<div class="dv-ed-foot"><span class="dv-ed-msg" role="alert">${esc(msg)}</span>${foot}</div></div>`;
}

const grow = (ta) => { ta.style.height = 'auto'; ta.style.height = `${ta.scrollHeight + 2}px`; };
const filesOf = (data) => [...((data && data.files) || [])];

export class CellEditor {
  constructor(view) {
    this.v = view;
    this.s = null;       // {id, leaf, row, media, form}
    this.pending = null; // a commit on its way
    this._chooser = null;
  }

  get open() { return !!this.s; }
  get host() { return this.v.host; }

  /** Whether this row's cell edits in place. */
  can(row, leaf) {
    const v = this.v;
    if (!v._editCells || !leaf || leaf.part || leaf.p.pivot || !row || row._rollup || row._readOnly) return false;
    if (!(leaf.id in v._model.props) || lockedBecause(leaf.p)) return false;
    const raw = row[leaf.id];
    // CONTRACT §46: an outline is drawn from its section, so there is nothing here to edit: the click opens the section on the page
    if (isDerivedCell(raw, leaf.display) && leaf.p.kind !== 'markdown') return false;
    return !(raw && typeof raw === 'object' && !Array.isArray(raw) && raw.rolled);
  }

  /** A click, F2 or Tab on a cell. A two-way column flips at once; everything else opens the editor. */
  async start(id, leaf, { pick = false, files = null, flip = true } = {}) {
    await this.finish(true);
    const row = this.host.element.row(id);
    if (!row || !this.can(row, leaf)) return;
    const p = leaf.p;
    // §46: a markdown cell edits in the Sheet, the side panel that follows the cell (cell-sheet.js), unless the page chose another surface
    if (p.kind === 'markdown' && surfaceOf(this.host.element) === 'sheet') { await this.v._cellSheet().show(row.id, leaf); return; }
    const steps = cycleOf(p);
    if (flip && (steps || p.type === 'boolean')) {
      const now = cellValue(row[p.id]);
      const next = steps ? steps[(steps.indexOf(String(now)) + 1) % steps.length] : !now;
      const res = await this.host.propose({ id: row.id, set: { [p.id]: next } });
      if (res && !res.ok) this.v._cellNote(id, leaf, res.reason);
      return;
    }
    const media = leaf.display === 'media';
    const form = document.createElement('form');
    form.className = 'dv-celledit';
    form.noValidate = true;
    const list = attachmentsOf(row[p.id]).map((a) => ({ ...a }));
    const value = cellValue(row[p.id]);
    const raw = fieldHtml(row, p, { unit: '' });
    // §40: a value its column's own control cannot hold opens in a text box, as written. WHY: <input type=number> reads "soon" as empty,
    // so a cell opened and left would be erased (Zach's truthful-rendering rule). In Edit only: `editable` alone stays §37
    const tools = this.v._tools;
    const asWritten = tools && !media && !fits(p, value);
    const text = media || asWritten || /^<(input type="text"|textarea)/.test(raw);
    const written = isEmpty(value) ? '' : Array.isArray(value) ? value.join(', ') : String(value);
    const free = tools && !asWritten && !media && kindOf(p) === 'select' && text;
    // §46: a list's line is an <input>: the browser's datalist, which suggests what the column holds, takes nothing else
    const hinted = text && !free && !media && !asWritten && p.type === 'list';
    form.innerHTML = free ? this._selectHtml(p, written)
      : hinted ? `<div class="dv-ed-box dv-ed-field"><input type="text" name="${esc(p.id)}" value="${esc(written)}" aria-label="${esc(p.label)}"><div class="dv-ed-foot"><span class="dv-ed-msg" role="alert"></span></div></div>`
      : text ? boxHtml({ name: p.id, value: written, placeholder: p.label, media: list, attach: media && this.v.input.canAttach, dataset: this.v.input.dataset })
        : `<div class="dv-ed-box dv-ed-field">${raw}<div class="dv-ed-foot"><span class="dv-ed-msg" role="alert"></span></div></div>`;
    listHints(form, p, this.host.element.data.rows);
    this.s = { id: String(row.id), leaf, row, media: list, form, isMedia: media, attachments: JSON.stringify(list), asWritten, written };
    this._wire(form);
    this.v._layer().append(form);
    // §46: a markdown cell that edits in its cell makes room for its raw text; how is one swappable piece (cell-surface.js)
    if (p.kind === 'markdown') {
      const make = typeof this.host.element.cellSurface === 'function' ? this.host.element.cellSurface : growInPlace;
      const box = form.querySelector('textarea');
      if (box) this.s.surface = make({ cell: () => this.v._cellOf(String(row.id), leaf.key), form, box, row, property: p.id, measure: (td) => this.v._measureRow(td) });
    }
    this.place();
    const control = form.querySelector('textarea, input, select');
    if (control) {
      control.focus({ preventScroll: true });
      if (control.tagName === 'TEXTAREA') { grow(control); const n = control.value.length; control.setSelectionRange(n, n); }
      if (this.s && this.s.surface) this.s.surface.fit();
      if (control.select && control.tagName === 'INPUT' && control.type !== 'date') control.select();
    }
    form.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (pick) this.choose();
    if (files) this.attach(files);
  }

  /** A select with no list of its own: its words, with the column's values offered (a native <datalist>; §40). */
  _selectHtml(p, value) {
    const seen = new Set();
    for (const r of this.host.element.data.rows) { const v = cellValue(r[p.id]); if (!isEmpty(v) && !Array.isArray(v)) seen.add(String(v)); }
    const list = `dv-dl-${esc(p.id)}`;
    return `<div class="dv-ed-box dv-ed-field"><input type="text" name="${esc(p.id)}" value="${esc(value)}" list="${list}" autocomplete="off" aria-label="${esc(p.label)}"><datalist id="${list}">${[...seen].slice(0, 200).map((v) => `<option value="${esc(v)}"></option>`).join('')}</datalist><div class="dv-ed-foot"><span class="dv-ed-msg" role="alert"></span></div></div>`;
  }

  /** Lay the editor over its cell (after a draw, a resize). A cell scrolled out of the window: it stays where it was. */
  place() {
    const s = this.s;
    if (!s) return;
    const td = this.v._cellOf(s.id, s.leaf.key);
    if (!td) return;
    const box = this.v._scroll, a = td.getBoundingClientRect(), b = box.getBoundingClientRect();
    const width = Math.min(Math.max(a.width, 240), box.clientWidth - 8);
    const left = Math.min(a.left - b.left + box.scrollLeft, box.scrollLeft + box.clientWidth - width - 4);
    s.form.style.left = `${Math.max(0, Math.round(left))}px`;
    s.form.style.top = `${Math.round(a.top - b.top + box.scrollTop)}px`;
    s.form.style.width = `${Math.round(width)}px`;
    s.form.style.minHeight = s.surface ? '' : `${Math.round(a.height)}px`;
    if (s.surface) s.surface.fit();
  }

  /** What the editor asks to change: {property: cell}, or null when nothing did. */
  read() {
    const s = this.s, p = s.leaf.p;
    if (s.asWritten) {
      const text = s.form.querySelector('textarea').value;
      return text === s.written ? null : { [p.id]: coerceCell(text, p, s.row[p.id]) };
    }
    if (s.isMedia) {
      const text = s.form.querySelector('textarea').value;
      const cell = s.row[p.id];
      const before = cellValue(cell);
      if (text === (isEmpty(before) ? '' : String(before)) && JSON.stringify(s.media) === s.attachments) return null;
      const rest = cell !== null && typeof cell === 'object' && !Array.isArray(cell) ? cell : {};
      return { [p.id]: { ...withValue(rest, text), attachments: s.media } };
    }
    const set = readEdits(s.form, s.row, this.v._model.props);
    return Object.keys(set).length ? set : null;
  }

  /** Commit (save) or cancel. A refusal keeps the editor open, what was typed in it, and says why. */
  finish(save, then = null) {
    if (this.pending) return this.pending.then(() => (then ? this.finish(save, then) : undefined));
    const s = this.s;
    if (!s) { if (then) then(); return Promise.resolve(); }
    const set = save ? this.read() : null;
    if (!set) { this._close(); if (then) then(); else this.v._focusRow(s.id); return Promise.resolve(); }
    s.form.classList.add('dv-ed-busy');
    this.pending = Promise.resolve(this.host.propose({ id: s.id, set })).then((res) => {
      this.pending = null;
      if (this.s !== s) return;
      s.form.classList.remove('dv-ed-busy');
      if (res && res.ok) { this._close(); if (then) then(); else this.v._focusRow(s.id); return; }
      this._say((res && res.reason) || 'The host refused the edit.');
      const control = s.form.querySelector('textarea, input, select');
      if (control) control.focus({ preventScroll: true });
    });
    return this.pending;
  }

  _close() {
    const s = this.s;
    this.s = null;
    if (s) s.form.remove();
    if (s && s.surface) s.surface.close();
  }

  _say(text) { const m = this.s && this.s.form.querySelector('.dv-ed-msg'); if (m) m.textContent = text; }

  /** The next editable cell after this one: along its row, then the next rows (a Tab); Shift walks back. */
  _next(dir) {
    const v = this.v, s = this.s;
    const leaves = v._model.leaves;
    const flat = v._model.flat;
    let i = flat.findIndex((r) => !r.getIsGrouped() && String(r.original.id) === s.id);
    let l = leaves.findIndex((x) => x.key === s.leaf.key);
    for (let n = 0, end = leaves.length * flat.length; n < end; n++) {
      l += dir;
      if (l < 0 || l >= leaves.length) { i += dir; l = dir > 0 ? 0 : leaves.length - 1; }
      if (i < 0 || i >= flat.length) return null;
      const r = flat[i];
      // §40: in Edit a checkbox or a two-way column is a stop too, or the keyboard could never reach it
      if (!r.getIsGrouped() && (v._tools || (!cycleOf(leaves[l].p) && leaves[l].p.type !== 'boolean')) && this.can(r.original, leaves[l])) return { index: i, id: r.original.id, leaf: leaves[l] };
    }
    return null;
  }

  // ------------------------------------------------------------------ a media cell's files
  async attach(files) {
    const s = this.s;
    if (!s || !s.isMedia || !this.v.input.canAttach) return;
    for (const file of files) {
      this._say('attaching…');
      const res = await this.host.attach(file, { id: s.id, property: s.leaf.id });
      if (this.s !== s) return;
      if (!res.ok || !res.attachment) { this._say(`Not attached: ${res.reason || 'the host refused it'}`); return; }
      if (!s.media.some((a) => a.url === res.attachment.url)) s.media.push(res.attachment);
      this._say('');
    }
    this._drawThumbs();
  }

  /** §46: a file taken by a markdown cell: stored by the host, and said in the text at the caret, the way the note will hold it. */
  async attachText(files) {
    const s = this.s;
    const box = s && s.form.querySelector('textarea');
    if (!box) return;
    for (const file of files) {
      this._say('attaching…');
      const res = await this.host.attach(file, { id: s.id, property: s.leaf.id });
      if (this.s !== s) return;
      if (!res.ok || !res.attachment) { this._say(`Not attached: ${res.reason || 'the host refused it'}`); return; }
      const a = res.attachment;
      const line = a.embed || `![${a.name || ''}](${a.ref || a.url})`;
      box.setRangeText(`${box.selectionStart ? '\n\n' : ''}${line}\n`, box.selectionStart, box.selectionEnd, 'end');
      grow(box);
      if (s.surface) s.surface.fit();
      this._say('');
    }
  }

  _drawThumbs() {
    const s = this.s;
    const was = s.form.querySelector('.dv-ed-thumbs');
    if (was) was.remove();
    s.form.querySelector('.dv-ed-foot').insertAdjacentHTML('beforebegin', draftThumbs(s.media, this.v.input.dataset));
  }

  /** The hidden file picker, for this cell. WHY one kept input, outside the form: the OS dialog takes the window's focus, and
      a click on the form's own input would read as leaving the cell. */
  choose() {
    let input = this._chooser;
    if (!input) {
      input = this._chooser = chooser((files) => { if (this._onChosen) this._onChosen(files); });
      this.v.el.append(input);
    }
    this._onChosen = (files) => this.attach(files);
    input.value = '';
    input.click();
  }

  _wire(form) {
    const s = this.s;
    for (const ta of form.querySelectorAll('textarea')) ta.addEventListener('input', () => { grow(ta); if (this.s && this.s.surface) this.s.surface.fit(); });
    form.addEventListener('submit', (e) => { e.preventDefault(); this.finish(true); });
    form.addEventListener('click', (e) => {
      const un = e.target.closest('[data-unattach]');
      if (un) { s.media.splice(Number(un.dataset.unattach), 1); this._drawThumbs(); return; }
      if (e.target.closest('[data-pick]')) this.choose();
    });
    // WHY mousedown: a press on the picker or a remove button must not take the focus away, which would commit the cell
    form.addEventListener('mousedown', (e) => { if (e.target.closest('button')) e.preventDefault(); });
    form.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.isComposing) return;
      if (e.key === 'Escape') { e.preventDefault(); this.finish(false); return; }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.finish(true); return; }
      if (e.key === 'Tab') {
        e.preventDefault();
        const to = this._next(e.shiftKey ? -1 : 1);
        this.finish(true, () => { if (to) this.v._editAt(to); else this.v._focusRow(s.id); });
      }
    });
    // WHY a select commits on change: a dropdown is done the moment it is picked, as in a sheet
    form.addEventListener('change', (e) => { if (e.target.matches('select')) this.finish(true); });
    form.addEventListener('paste', (e) => {
      const files = filesOf(e.clipboardData);
      if (files.length && s.isMedia) { e.preventDefault(); this.attach(files); }
      else if (files.length && s.leaf.p.kind === 'markdown' && this.v.input.canAttach) { e.preventDefault(); this.attachText(files); }
    });
    form.addEventListener('dragover', (e) => { if (s.isMedia && e.dataTransfer && [...e.dataTransfer.types].includes('Files')) { e.preventDefault(); form.classList.add('dv-ed-over'); } });
    form.addEventListener('dragleave', () => form.classList.remove('dv-ed-over'));
    form.addEventListener('drop', (e) => {
      form.classList.remove('dv-ed-over');
      const files = filesOf(e.dataTransfer);
      if (files.length && s.isMedia) { e.preventDefault(); this.attach(files); }
    });
    // leaving the cell commits it; the OS file dialog keeps document.activeElement, so it is not leaving
    form.addEventListener('focusout', () => {
      setTimeout(() => { if (this.s === s && !s.form.contains(document.activeElement) && document.hasFocus()) this.finish(true, () => {}); }, 0);
    });
  }

  destroy() { this._close(); }
}

function chooser(take) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*,video/*';
  input.multiple = true;
  input.hidden = true;
  input.className = 'dv-ed-chooser';
  input.addEventListener('change', () => take([...input.files]));
  return input;
}

// ------------------------------------------------------------------ the add row
/** A column the add row has a cell for: not locked, and not `addRow: false` on the property (what a row gets later, not at birth). */
export const takes = (l) => !l.part && !l.p.pivot && !lockedBecause(l.p) && l.p.addRow !== false;

export class AddRow {
  constructor(view) {
    this.v = view;
    this.tr = null;
    this.key = null;
    this.values = {};   // property -> text
    this.media = {};    // property -> attachments
    this.steps = {};    // property -> a cycle column's pick
    this.msg = '';
    this.busy = false;
    this._chooser = null;
  }

  /** The row's cells: a box for each editable property, the column's stepper, nothing under a locked one. */
  html(leaves, selectable) {
    const v = this.v, attach = v.input.canAttach, dataset = v.input.dataset;
    const editable = takes;
    const go = leaves.findIndex((l) => !editable(l));
    const at = go >= 0 ? go : leaves.length - 1;
    const send = `<button type="button" class="dv-btn dv-add-go" data-add-go>Add</button><span class="dv-ed-msg dv-add-msg" role="alert">${esc(this.msg)}</span>`;
    const cell = (l, i) => {
      const extra = i === at ? send : '';
      if (!editable(l)) return `<td class="dv-addc">${extra}</td>`;
      const p = l.p;
      const steps = cycleOf(p);
      if (steps) {
        const now = this.steps[p.id] ?? String(p.addDefault ?? steps[0]);
        const label = p.labels && p.labels[now] !== undefined ? p.labels[now] : now;
        const hue = p.colors && p.colors[now] != null ? p.colors[now] : 0;
        return `<td class="dv-addc dv-addcyc"><button type="button" class="dv-cycle dv-badge dv-h${esc(hue)}" data-add-step="${esc(p.id)}" aria-label="${esc(p.label)}: ${esc(label)}" title="Click to switch">${esc(label)}</button>${extra}</td>`;
      }
      if (p.type === 'boolean') return `<td class="dv-addc"><input type="checkbox" name="${esc(p.id)}" aria-label="${esc(p.label)}"${this.values[p.id] ? ' checked' : ''}>${extra}</td>`;
      // a column of choices is its dropdown here too; WHY fieldHtml's: one list of what a property may hold
      const control = l.display === 'media' ? '' : fieldHtml({ [p.id]: this.values[p.id] ?? null }, p, { unit: '' });
      if (control.startsWith('<select')) return `<td class="dv-addc" data-add-col="${esc(p.id)}"><div class="dv-ed-box dv-ed-field">${control}</div>${extra}</td>`;
      return `<td class="dv-addc" data-add-col="${esc(p.id)}">${boxHtml({ name: p.id, value: this.values[p.id] || '', placeholder: p.label, media: this.media[p.id] || [], attach: l.display === 'media' && attach, dataset })}${extra}</td>`;
    };
    return `${selectable ? '<td class="dv-selcol"></td>' : ''}${leaves.map(cell).join('')}`;
  }

  /** Keep the row across redraws: the same <tr> (focus and typing stay) until its columns change. */
  draw(thead, leaves, selectable) {
    const key = JSON.stringify([leaves.map((l) => [l.key, l.p.type, l.display]), selectable, this.v.input.canAttach]);
    if (this.tr && this.key === key) { thead.append(this.tr); return; }
    if (!this.tr) { this.tr = document.createElement('tr'); this.tr.className = 'dv-addrow'; this._wire(this.tr); }
    this.key = key;
    this._leaves = leaves;
    this.tr.innerHTML = this.html(leaves, selectable);
    thead.append(this.tr);
    for (const ta of this.tr.querySelectorAll('textarea')) grow(ta);
  }

  redraw() {
    const had = document.activeElement && this.tr.contains(document.activeElement) ? document.activeElement.name : null;
    this.tr.innerHTML = this.html(this._leaves, !!this.tr.querySelector('.dv-selcol'));
    for (const ta of this.tr.querySelectorAll('textarea')) grow(ta);
    if (had) { const el = this.tr.querySelector(`[name="${CSS.escape(had)}"]`); if (el) el.focus({ preventScroll: true }); }
    this.v._rowsMoved();
  }

  /** Whatever is filled in, as the row's cells; null when nothing is. */
  set() {
    const set = {};
    let any = false;
    for (const l of this._leaves) {
      const p = l.p;
      if (!takes(l)) continue;
      const steps = cycleOf(p);
      if (steps) { set[p.id] = this.steps[p.id] ?? String(p.addDefault ?? steps[0]); continue; }
      const text = this.values[p.id] ?? '';
      const media = this.media[p.id] || [];
      if (l.display === 'media') {
        if (text.trim() !== '' || media.length) { set[p.id] = { value: text, attachments: media }; any = true; }
      } else if (p.type === 'boolean') { if (this.values[p.id]) { set[p.id] = true; any = true; } }
      else if (String(text).trim() !== '') {
        // §40: in Edit a word in a number's box stays that word; WHY not Number(): NaN is stored as null, a silent loss of what was typed
        set[p.id] = this.v._tools ? coerceCell(text, p) : p.type === 'number' ? Number(text) : p.type === 'list' ? text.split(',').map((x) => x.trim()).filter(Boolean) : text;
        any = true;
      }
    }
    return any ? set : null;
  }

  async submit() {
    const set = this.set();
    if (!set || this.busy) return;
    this.busy = true;
    const res = await this.v.host.add(set);
    this.busy = false;
    if (res && res.ok) {
      this.values = {}; this.media = {}; this.msg = '';
      this.redraw();
      const first = this.tr.querySelector('textarea, input');
      if (first) first.focus({ preventScroll: true });
    } else { this.msg = (res && res.reason) || 'The host refused the row.'; this.redraw(); }
  }

  async attach(property, files) {
    if (!this.v.input.canAttach) return;
    for (const file of files) {
      const res = await this.v.host.attach(file, { id: null, property });
      if (!res.ok || !res.attachment) { this.msg = `Not attached: ${res.reason || 'the host refused it'}`; this.redraw(); return; }
      const list = this.media[property] || (this.media[property] = []);
      if (!list.some((a) => a.url === res.attachment.url)) list.push(res.attachment);
    }
    this.redraw();
  }

  _wire(tr) {
    const colOf = (el) => { const td = el.closest && el.closest('[data-add-col]'); return td ? td.dataset.addCol : null; };
    tr.addEventListener('input', (e) => {
      const t = e.target;
      if (t.name) this.values[t.name] = t.type === 'checkbox' ? t.checked : t.value;
      if (t.tagName === 'TEXTAREA') { grow(t); this.v._rowsMoved(); }
    });
    tr.addEventListener('change', (e) => { if (e.target.type === 'checkbox' || e.target.tagName === 'SELECT') this.values[e.target.name] = e.target.type === 'checkbox' ? e.target.checked : e.target.value; });
    tr.addEventListener('mousedown', (e) => { if (e.target.closest('button')) e.preventDefault(); });
    tr.addEventListener('click', (e) => {
      const t = e.target;
      const step = t.closest('[data-add-step]');
      if (step) {
        const p = this.v._model.props[step.dataset.addStep];
        const steps = cycleOf(p);
        const now = this.steps[p.id] ?? String(p.addDefault ?? steps[0]);
        this.steps[p.id] = steps[(steps.indexOf(now) + 1) % steps.length];
        this.redraw();
        return;
      }
      if (t.closest('[data-add-go]')) { this.submit(); return; }
      const un = t.closest('[data-unattach]');
      if (un) { (this.media[colOf(un)] || []).splice(Number(un.dataset.unattach), 1); this.redraw(); return; }
      if (t.closest('[data-pick]')) {
        const property = colOf(t);
        if (!this._chooser) { this._chooser = chooser((files) => this.attach(this._for, files)); this.v.el.append(this._chooser); }
        this._for = property;
        this._chooser.value = '';
        this._chooser.click();
      }
    });
    tr.addEventListener('keydown', (e) => {
      if (e.isComposing || e.target.tagName !== 'TEXTAREA') return;
      e.stopPropagation();
      if (e.key === 'Escape') { e.target.blur(); return; }
      if (e.key !== 'Enter' || e.shiftKey) return;
      e.preventDefault();
      // Enter walks the boxes, as Tab does, and files from the last one
      const boxes = [...tr.querySelectorAll('textarea')];
      const at = boxes.indexOf(e.target);
      if (at < boxes.length - 1) boxes[at + 1].focus();
      else this.submit();
    });
    tr.addEventListener('paste', (e) => {
      const files = filesOf(e.clipboardData), p = colOf(e.target);
      if (files.length && p && e.target.closest('.dv-ed-box').querySelector('[data-pick]')) { e.preventDefault(); this.attach(p, files); }
    });
    tr.addEventListener('dragover', (e) => { const p = colOf(e.target); if (p && e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
    tr.addEventListener('drop', (e) => {
      const files = filesOf(e.dataTransfer), p = colOf(e.target);
      if (files.length && p) { e.preventDefault(); this.attach(p, files); }
    });
  }
}
