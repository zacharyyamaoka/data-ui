/* The Sheet: a markdown cell's raw text, edited in a side panel that follows the cell you are on (docs/CONTRACT.md §46).

   WHY (Zach, 2026-10-31, chose it from five: "Ok go ahead with Sheet it shall work for now!"): selection, not a mode. The table stays
   fully interactive; a click on a section cell shows that cell's raw markdown in the panel, a click on another cell (in any row) moves
   the panel to it without closing, and what is typed saves by itself a moment after the typing stops, so there is no save step.
   The panel is the kit's own: resizable on its left edge, the width remembered (src/resize.js, Zach's standing rule for side panels).

   WHY autosave is safe, in two parts:
   - a save names one property (`propose({id, set: {property: text}})`), so a host that writes a note changes that section's bytes only;
   - the panel remembers the text it loaded (and each text it saved). When the row now holds anything else, somebody else changed it, and
     the panel refuses to save over it: it says so and offers "Use theirs" (take their text, drop mine) or "Keep mine" (save over theirs).
     A host that checks `was` itself (tools/serve-md.mjs) refuses the same way, and its words are shown as given. A refused save keeps
     what was typed.

   One piece, replaceable as a whole: `el.cellSurface = 'grow'` (or a function, cell-surface.js) edits in the cell instead. */

import { esc, cellValue, isEmpty, makeResizable } from '@data-ui/core';

const IDLE = 700; // ms after the last key before a save
const norm = (s) => String(s ?? '').replace(/\r\n/g, '\n').trim();
const textOf = (cell) => { const v = cellValue(cell); return isEmpty(v) ? '' : String(v); };

export class CellSheet {
  constructor(view) {
    this.v = view;
    this.el = null;      // the <aside>, made on first use
    this.t = null;       // {id, leaf} the panel is on
    this.sent = '';      // the text the panel last loaded or saved: dirty is the box differing from it
    this.seen = new Set(); // every normalised value this panel knew the row to hold; the row holding anything else is somebody else's
    this.timer = 0;
    this.saving = null;  // the save in flight
    this.resizer = null;
    this._onHide = () => { if (document.visibilityState === 'hidden') void this.flush(); };
  }

  get open() { return !!this.t; }
  get box() { return this.el && this.el.querySelector('textarea'); }
  get dirty() { return !!this.box && this.box.value !== this.sent; }
  get element() { return this.v.host.element; }

  _row() { return this.t ? this.element.row(this.t.id) : null; }

  _make() {
    if (this.el) return this.el;
    const aside = document.createElement('aside');
    aside.className = 'dv-cellsheet';
    aside.setAttribute('aria-label', 'Edit section');
    aside.hidden = true;
    aside.innerHTML = '<header class="dv-cs-head"><span class="dv-cs-note"></span><span class="dv-cs-state" role="status" aria-live="polite"></span>'
      + '<button type="button" class="dv-cs-x" aria-label="Close panel" title="Close panel (Esc)">✕</button></header>'
      + '<nav class="dv-cs-tabs" aria-label="Sections"></nav>'
      + '<div class="dv-cs-body"><textarea spellcheck="true" aria-label="Section text"></textarea></div>'
      + '<footer class="dv-cs-foot"><span class="dv-ed-msg" role="alert"></span><span class="dv-cs-acts"></span><button type="button" class="dv-mc-add" data-cs-pick tabindex="-1" hidden>+ image or video</button></footer>';
    this.element.append(aside);
    this.el = aside;
    this._wire(aside);
    const id = this.element.id || this.v.input.dataset.id || 'data-views';
    this.resizer = makeResizable(aside, { edge: 'left', min: 280, max: 1000, keep: 160, key: `cell-sheet:${id}`, label: 'the section panel' });
    document.addEventListener('visibilitychange', this._onHide);
    return aside;
  }

  _wire(aside) {
    const box = aside.querySelector('textarea');
    box.addEventListener('input', () => { this._state(this.dirty ? 'Editing…' : 'Saved'); this._say(''); this._later(); });
    // WHY no Enter-to-save: the text is many lines, and nothing needs saving by hand. Cmd/Ctrl+Enter saves now, as a note does.
    box.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.isComposing) return;
      if (e.key === 'Escape') { e.preventDefault(); void this.close(); return; }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void this.flush(); }
    });
    aside.addEventListener('keydown', (e) => e.stopPropagation());
    // leaving the panel for the table saves at once: the next click may be another cell, or the page
    aside.addEventListener('focusout', (e) => { if (!aside.contains(e.relatedTarget)) void this.flush(); });
    aside.addEventListener('click', (e) => {
      if (e.target.closest('.dv-cs-x')) { void this.close(); return; }
      const tab = e.target.closest('[data-cs-leaf]');
      if (tab) { const leaf = this.v._model.leaves.find((l) => l.key === tab.dataset.csLeaf); if (leaf && this.t) void this.show(this.t.id, leaf); return; }
      const act = e.target.closest('[data-cs-act]');
      if (act) { void this[act.dataset.csAct === 'theirs' ? '_useTheirs' : '_keepMine'](); return; }
      if (e.target.closest('[data-cs-pick]')) this._choose();
    });
    aside.addEventListener('mousedown', (e) => { if (e.target.closest('button')) e.preventDefault(); });
    box.addEventListener('paste', (e) => {
      const files = [...((e.clipboardData && e.clipboardData.files) || [])];
      if (files.length && this.v.input.canAttach) { e.preventDefault(); void this._attach(files); }
    });
    box.addEventListener('dragover', (e) => { if (this.v.input.canAttach && e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
    box.addEventListener('drop', (e) => {
      const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
      if (files.length && this.v.input.canAttach) { e.preventDefault(); void this._attach(files); }
    });
  }

  // ------------------------------------------------------------------ following the cell
  /** Show this cell's section. Saves the one it was on first; a refusal keeps the panel where it was. */
  async show(id, leaf) {
    id = String(id);
    const same = this.t && this.t.id === id && this.t.leaf.key === leaf.key;
    if (same) { this.box.focus({ preventScroll: true }); return true; }
    if (this.t && !(await this.flush())) return false;
    const row = this.element.row(id);
    if (!row) return false;
    const aside = this._make();
    this.t = { id, leaf };
    const text = textOf(row[leaf.p.id]);
    this.sent = text;
    this.seen = new Set([norm(text)]);
    this.box.value = text;
    this._say('');
    this._acts(false);
    this._head(row);
    this._tabs(row);
    this.box.placeholder = leaf.p.label;
    aside.querySelector('[data-cs-pick]').hidden = !this.v.input.canAttach;
    this._state('Saved');
    this._room(true);
    this.mark();
    const td = this.v._cellOf(id, leaf.key);
    if (td) td.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    this.box.focus({ preventScroll: true });
    const n = this.box.value.length;
    this.box.setSelectionRange(n, n);
    return true;
  }

  _head(row) {
    const title = this.v.input.dataset.titleProperty;
    const name = (title && textOf(row[title])) || String(row.id);
    const note = this.el.querySelector('.dv-cs-note');
    note.textContent = name;
    note.title = name;
  }

  /** One tab for each section column of this table that this row can edit, the one shown marked. */
  _tabs(row) {
    const leaves = this.v._model.leaves.filter((l) => l.p.kind === 'markdown' && this.v._editor.can(row, l));
    const nav = this.el.querySelector('.dv-cs-tabs');
    nav.hidden = leaves.length < 2;
    nav.innerHTML = leaves.map((l) => `<button type="button" data-cs-leaf="${esc(l.key)}"${l.key === this.t.leaf.key ? ' class="dv-cs-on" aria-current="true"' : ''}>${esc(l.p.label)}</button>`).join('');
  }

  _room(on) {
    const el = this.element;
    el.classList.toggle('dv-sheeted', on);
    this.el.hidden = !on;
    if (!on) { el.style.removeProperty('--dv-sheet-w'); if (this._ro) { this._ro.disconnect(); this._ro = null; } return; }
    // the table gives up the panel's width, so the cell it edits is never behind it
    const size = () => el.style.setProperty('--dv-sheet-w', `${Math.round(this.el.getBoundingClientRect().width)}px`);
    size();
    if (!this._ro && typeof ResizeObserver === 'function') { this._ro = new ResizeObserver(size); this._ro.observe(this.el); }
  }

  /** The cell the panel is on, marked on the drawn rows (rows are rebuilt from strings, so every draw asks again). */
  mark() {
    for (const td of this.v.el.querySelectorAll('td.dv-cs-on')) td.classList.remove('dv-cs-on');
    if (!this.t) return;
    const td = this.v._cellOf(this.t.id, this.t.leaf.key);
    if (td) td.classList.add('dv-cs-on');
  }

  /** After each draw of the rows: the row may have changed under the panel. */
  sync() {
    this.mark();
    if (!this.t || this.saving) return;
    const row = this._row();
    if (!row) { this._say('This record is gone. What is in the panel is kept until you close it.'); return; }
    this._head(row);
    const now = textOf(row[this.t.leaf.p.id]);
    if (this.seen.has(norm(now))) return;
    if (!this.dirty) { this._adopt(now); return; }
    this._conflict(now);
  }

  _adopt(text) {
    const box = this.box, at = box.selectionStart;
    this.sent = text;
    this.seen = new Set([norm(text)]);
    box.value = text;
    box.setSelectionRange(Math.min(at, text.length), Math.min(at, text.length));
    this._acts(false);
    this._say('');
    this._state('Saved');
  }

  // ------------------------------------------------------------------ saving
  _later() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.timer = 0; void this.save(); }, IDLE);
  }

  /** Save now what is waiting. True when nothing is left unsaved; false when a refusal kept it. */
  async flush() {
    clearTimeout(this.timer);
    this.timer = 0;
    return this.save();
  }

  async save() {
    if (this.saving) { await this.saving; }
    if (!this.t || !this.dirty) return true;
    const { id, leaf } = this.t;
    const row = this._row();
    if (!row) { this._say('This record is gone, so this cannot be saved.'); return false; }
    const now = textOf(row[leaf.p.id]);
    if (!this.seen.has(norm(now))) { this._conflict(now); return false; }
    const text = this.box.value;
    // WHY trimmed, and empty as null: what the old in-cell editor sent (form.js read()), and a note keeps a section without the blank lines around it
    const sends = text.trim();
    this._state('Saving…');
    this.saving = Promise.resolve(this.v.host.propose({ id, set: { [leaf.p.id]: sends === '' ? null : sends } }));
    let res;
    try { res = await this.saving; } finally { this.saving = null; }
    if (!this.t || this.t.id !== id || this.t.leaf.key !== leaf.key) return !!(res && res.ok);
    if (res && res.ok) {
      this.sent = text;
      this.seen.add(norm(text));
      this._say('');
      this._acts(false);
      if (this.dirty) { this._state('Editing…'); this._later(); } else this._state('Saved');
      return true;
    }
    this._state('Not saved');
    this._say((res && res.reason) || 'The host refused the edit.');
    // WHY the host's own stale refusal gets the same two ways out: its words say what is on disk, and what to do with it is the reader's
    if (res && /changed on disk|changed since/i.test(res.reason || '')) this._acts(true);
    return false;
  }

  _conflict(theirs) {
    this._state('Not saved');
    const head = String(theirs).replace(/\s+/g, ' ').trim().slice(0, 80);
    this._say(`${this.t.leaf.p.label} changed since this panel opened it, so your edit was not saved over it. It now reads: ${head ? `“${head}${String(theirs).length > 80 ? '…' : ''}”` : '(empty)'}`);
    this._acts(true);
  }

  _acts(on) {
    this.el.querySelector('.dv-cs-acts').innerHTML = on
      ? '<button type="button" class="dv-btn" data-cs-act="theirs">Use theirs</button><button type="button" class="dv-btn dv-primary" data-cs-act="mine">Keep mine</button>' : '';
  }

  /** Their text replaces mine in the box. */
  async _useTheirs() {
    const row = this._row();
    if (row) this._adopt(textOf(row[this.t.leaf.p.id]));
  }

  /** Mine goes over theirs: their text is now one the panel knows, and the save goes ahead. */
  async _keepMine() {
    const row = this._row();
    if (row) this.seen.add(norm(textOf(row[this.t.leaf.p.id])));
    this._say('');
    this._acts(false);
    await this.save();
  }

  // ------------------------------------------------------------------ files
  async _attach(files) {
    const t = this.t;
    if (!t) return;
    const box = this.box;
    for (const file of files) {
      this._say('attaching…');
      const res = await this.v.host.attach(file, { id: t.id, property: t.leaf.id });
      if (this.t !== t) return;
      if (!res.ok || !res.attachment) { this._say(`Not attached: ${res.reason || 'the host refused it'}`); return; }
      const a = res.attachment;
      const line = a.embed || `![${a.name || ''}](${a.ref || a.url})`;
      box.setRangeText(`${box.selectionStart ? '\n\n' : ''}${line}\n`, box.selectionStart, box.selectionEnd, 'end');
      this._say('');
    }
    this._state('Editing…');
    this._later();
  }

  _choose() {
    let input = this._chooser;
    if (!input) {
      input = this._chooser = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*,video/*'; input.multiple = true; input.hidden = true;
      input.addEventListener('change', () => void this._attach([...input.files]));
      this.element.append(input);
    }
    input.value = '';
    input.click();
  }

  // ------------------------------------------------------------------ words
  _say(text) { const m = this.el && this.el.querySelector('.dv-ed-msg'); if (m) m.textContent = text; }
  _state(text) { const s = this.el && this.el.querySelector('.dv-cs-state'); if (s) s.textContent = text; }

  /** Save, then go. False when a refusal keeps the panel open. */
  async close() {
    if (!this.t) return true;
    if (!(await this.flush())) return false;
    this.t = null;
    this._room(false);
    this.mark();
    return true;
  }

  /** The table is going away: what is waiting is sent on its way, the panel removed. */
  destroy() {
    clearTimeout(this.timer);
    if (this.t && this.dirty) void this.save();
    document.removeEventListener('visibilitychange', this._onHide);
    if (this._ro) this._ro.disconnect();
    if (this.resizer) this.resizer.destroy();
    if (this._chooser) this._chooser.remove();
    if (this.el) { this.element.classList.remove('dv-sheeted'); this.element.style.removeProperty('--dv-sheet-w'); this.el.remove(); }
    this.el = null;
    this.t = null;
  }
}
