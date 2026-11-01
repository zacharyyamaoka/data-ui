/* The dashboard editor: Edit mode with an outline, one options pane and a queue (docs/peps/0017-dashboard-editor.md).

   ONE STATE. The .base text in the session is the only thing edited. A drag on the canvas, a row dragged in the outline and
   a field in the options pane all end in apply(), a function of that text; outline, options, canvas and bar are drawn from
   it, so a change on one side is on the others at once, and Undo is the text before.

   THE CANVAS IS WHAT THE FILE DRAWS. A layout is a list read in order, with widths, not positions. So the grid runs in
   gridstack's `list` mode, where a drag reorders a list and the rows reflow under it (the preview is the outcome), and
   after every drop the panels are placed exactly where the file will draw them (place()): CSS grid's rows, each as tall
   as its tallest panel.

   A LAYOUT EDIT DRAWS NOTHING. The panels stay on the page (their charts, scroll and hover) and only move; anything else
   (a rename, a new type, a panel added) draws the dashboard again through its public load(). */

import { parseBase } from '../../../core/src/base.js';
import { packPanels, readingOrder, readDashboard } from '../model.js';
import { liveGrid } from '../arrange.js';
import css from './edit.css';
import { EditSession } from './session.js';
import { makePane } from './pane.js';
import { Outline } from './outline.js';
import { Options } from './options.js';
import { Queue } from './queue.js';
import { panelsOf, arrangeText, layoutOnly, insertPanel, addPanel, identity } from './ops.js';
import { icon, menu, confirmDialog } from './ui.js';

// WHY a measured width and not a media query: the room is the dashboard's, whatever the window (a dashboard in a host's
// narrow column); and WHY no container query: containment would make this element the box of its fixed drill peek
const NARROW = 700;  // px: under this, no grid to drag on: the panes stack, the panels stay one column
const ROOMY = 1060;  // px: under this, the options pane starts folded, so the grid keeps a useful width
const SHORT = ['kpi', 'gauge', 'bullet', 'barlist', 'tracker'];

function addStyle() {
  if (document.querySelector('style[data-ui-dash-edit]')) return;
  const s = document.createElement('style');
  s.dataset.uiDashEdit = '';
  s.textContent = css;
  document.head.append(s);
}

export class Editor {
  constructor(dash) {
    this.dash = dash;
    this.s = new EditSession(dash);
    this.sel = null; // the selected panel's key
    this.review = null; // {moved, copy, status} while the options pane shows the review
    this.note = '';
    this.gs = null;
    this.rows = {}; // grid rows of the panels with no h, by identity, measured as they were read
    this.sizes = {}; // what the grid shows, {key: {w, h}}: a size is written only when a reader changes it
    this.rev = 0;
    this.busy = Promise.resolve(true);
    this.railOpen = false;
    this.queue = new Queue(this);
    this.onKey = (e) => this.key(e);
    this.onPress = (e) => this.press(e);
    this.onMove = (e) => { if (this.east) this.east.x = e.clientX; };
    this.onLeave = (e) => { if (this.s.dirty) { e.preventDefault(); e.returnValue = ''; } };
    this.onVisible = () => { if (!document.hidden) this.queue.read().then(() => this.outline.draw()); };
    this.resized = new ResizeObserver(() => this.fit());
  }

  // ---------------------------------------------------------------- entering and leaving

  async enter() {
    const { dash } = this;
    addStyle();
    this.measure();
    await this.queue.read();
    dash._editor = this;
    dash.dataset.editing = '';
    this.narrow = dash.clientWidth < NARROW;
    dash.toggleAttribute('data-dde-narrow', this.narrow);
    const roomy = dash.clientWidth >= ROOMY;
    this.outlinePane = makePane(dash, { name: 'outline', side: 'left', min: 180, max: 480, label: 'the outline', heading: 'Outline' });
    this.optionsPane = makePane(dash, { name: 'options', side: 'right', min: 240, max: 520, label: 'the options', heading: 'Options' });
    if (this.narrow) { this.outlinePane.fold(true, { remember: false }); this.optionsPane.fold(true, { remember: false }); } else if (!roomy) this.optionsPane.fold(true, { remember: false });
    this.outline = new Outline(this, this.outlinePane);
    this.options = new Options(this, this.optionsPane);
    this.listen(true);
    this.resized.observe(dash);
    dash.load(parseBase(this.s.text), dash.datasets, { keepState: true });
    this.drawSides();
    this.outline.focus();
    dash.dispatchEvent(new CustomEvent('data-dashboard-edit', { bubbles: true, composed: true, detail: { editing: true } }));
  }

  /** Leave: asks when there are unsaved edits. Resolves whether the editor closed. */
  async exit() {
    if (this.s.dirty) {
      const what = await confirmDialog({ title: 'Unsaved changes', body: `Do you want to save your changes to ${this.s.title}?`,
        buttons: [{ label: 'Discard', value: 'discard' }, { label: 'Cancel', value: null }, { label: 'Save', value: 'save', primary: true }] });
      if (!what) return false;
      if (what === 'save') { this.openReview(); return false; }
    }
    this.close();
    return true;
  }

  close() {
    const { dash } = this;
    this.listen(false);
    this.resized.disconnect();
    this.stopGrid();
    this.queue.destroy();
    this.outline.destroy();
    this.outlinePane.destroy();
    this.optionsPane.destroy();
    dash._editor = null;
    delete dash.dataset.editing;
    delete dash.dataset.ddeGrid;
    dash.removeAttribute('data-dde-narrow');
    dash.removeAttribute('data-dde-filters');
    delete dash.dataset.ddeRev;
    dash.baseText = this.s.saved;
    dash.load(parseBase(this.s.saved), dash.datasets, { keepState: true });
    const edit = dash.querySelector('[data-act="edit"]');
    if (edit) edit.focus({ preventScroll: true });
    dash.dispatchEvent(new CustomEvent('data-dashboard-edit', { bubbles: true, composed: true, detail: { editing: false } }));
  }

  /** The page's listeners, while the element is on the page. */
  listen(on) {
    if (this.listening === on) return;
    this.listening = on;
    const go = on ? 'addEventListener' : 'removeEventListener';
    document[go]('keydown', this.onKey, true);
    document[go]('pointermove', this.onMove, true);
    document[go]('visibilitychange', this.onVisible);
    this.dash[go]('pointerdown', this.onPress, true);
    window[go]('beforeunload', this.onLeave);
  }

  /** The window or the column changed: below NARROW there is no grid to drag on. */
  fit() {
    const narrow = this.dash.clientWidth < NARROW;
    if (narrow === this.narrow) return;
    this.narrow = narrow;
    this.dash.toggleAttribute('data-dde-narrow', narrow);
    this.apply(() => this.s.text, 'fit', { force: true });
  }

  // ---------------------------------------------------------------- what index.js asks while it draws

  /** The dashboard redraws its own nodes between the panes (a redraw must not take a field being typed in off the page). */
  redrawBody(html) {
    const keep = [this.outlinePane, this.optionsPane].flatMap((p) => [p.el, p.ctl.handle]);
    for (const c of [...this.dash.children]) if (!keep.includes(c)) c.remove();
    const t = document.createElement('template');
    t.innerHTML = html;
    this.outlinePane.ctl.handle.after(...t.content.childNodes);
  }

  /** Where a panel draws its content: gridstack's box from the start (arrange.js liveGrid leaves it there). */
  box(sec) {
    if (this.narrow) return sec;
    const box = document.createElement('div');
    box.className = 'grid-stack-item-content';
    sec.append(box);
    return box;
  }

  drawn() {
    const { dash } = this;
    if (this.gs) this.stopGrid();
    if (!this.narrow) {
      for (const p of dash.dash.panels) {
        const sec = this.section(p.key);
        if (sec) sec.querySelector(':scope > .grid-stack-item-content').insertAdjacentHTML('afterbegin', `<div class="dde-grip" title="Drag to move">${icon('grip')}</div>`);
      }
      this.startGrid();
    }
    this.mark();
    this.queue.targets();
  }

  actionsHtml() {
    const rail = Object.values(this.dash.dash.datasets).some((x) => Array.isArray(x.facets) && x.facets.length && this.dash.datasets[x.name]);
    return `<span class="dde-status" role="status"></span>
      <button type="button" class="dd-act dde-tool" data-act="edit-undo" aria-label="Undo" title="Undo (Ctrl+Z)">${icon('undo')}</button>
      <button type="button" class="dd-act dde-tool" data-act="edit-redo" aria-label="Redo" title="Redo (Ctrl+Shift+Z)">${icon('redo')}</button>
      <button type="button" class="dd-act" data-act="edit-add" aria-haspopup="menu" aria-expanded="false">Add <span aria-hidden="true">▾</span></button>
      ${rail ? `<button type="button" class="dd-act" data-act="edit-filters" aria-pressed="${this.railOpen}">Filters</button>` : ''}
      <button type="button" class="dd-act" data-act="edit-exit">Exit edit</button>
      <button type="button" class="dd-act dde-primary" data-act="edit-save" title="Review and save (Ctrl+S)">Save</button>`;
  }

  act(act, btn) {
    if (act === 'edit-undo') this.step('undo');
    if (act === 'edit-redo') this.step('redo');
    if (act === 'edit-add') this.addMenu(btn);
    if (act === 'edit-exit') this.exit();
    if (act === 'edit-save') this.openReview();
    if (act === 'edit-filters') this.filters(btn);
  }

  // ---------------------------------------------------------------- the grid

  /** A panel's rows when its entry has no h: what it measured, else a guess by type until it has drawn. */
  rowsOf(p) {
    const known = this.rows[identity(p)];
    if (known) return known;
    if (p.text !== null) {
      const note = this.section(p.key)?.querySelector('.dd-text');
      return note ? this.toRows(note.getBoundingClientRect().height + 16) : 1;
    }
    const type = p.views[0] && p.views[0].type;
    return type === 'playback' ? 1 : SHORT.includes(type) ? 2 : 4;
  }

  toRows(px) {
    const cell = this.dash.dash.rowHeight + this.gap();
    return Math.max(1, Math.ceil((px + this.gap()) / cell));
  }

  gap() { return parseFloat(getComputedStyle(this.dash).getPropertyValue('--dd-gap')) || 12; }

  /** Every panel's height as read, before the editor moves it. */
  measure() {
    for (const p of this.dash.dash.panels) {
      const sec = this.section(p.key);
      if (!p.h && sec) this.rows[identity(p)] = this.toRows(sec.getBoundingClientRect().height);
    }
  }

  /** Where the file draws the panels of `text`: packed in reading order, each row as tall as its tallest panel (CSS grid's
      align-items: stretch). */
  items(text) {
    const panels = panelsOf(text).filter((p) => !p.hidden);
    const placed = packPanels(panels.map((p) => ({ key: p.key, w: p.w, h: Math.ceil(p.h || this.rowsOf(p)) })), this.dash.dash.columns);
    const tallest = new Map();
    for (const p of placed) tallest.set(p.y, Math.max(tallest.get(p.y) || 0, p.h));
    const out = placed.map((p) => ({ ...p, h: tallest.get(p.y) }));
    this.sizes = Object.fromEntries(out.map((p) => [p.key, { w: p.w, h: p.h }]));
    return out;
  }

  startGrid() {
    const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.gs = liveGrid(this.dash, this.items(this.s.text), {
      // WHY list: a layout is a list, so a drag reorders it and the preview is the outcome (gridstack 14's own word for it)
      mode: 'list', animate: !reduced,
      draggable: { handle: '.dde-grip', cancel: 'input,textarea,button,select,option,[contenteditable]' },
      resizable: { handles: 'e,s,se' },
    });
    this.dash.dataset.ddeGrid = '';
    const drop = () => this.dropped();
    this.gs.on('dragstop', drop);
    this.gs.on('resizestop', drop);
  }

  stopGrid() {
    if (!this.gs) return;
    try { this.gs.destroy(false); } catch { /* its nodes went with the redraw */ }
    this.gs = null;
  }

  /** A panel was dropped or resized: the grid's order and sizes become the text. */
  dropped() {
    const nodes = this.gs.engine.nodes.filter((n) => n.id).map((n) => ({ key: n.id, x: n.x, y: n.y, w: n.w, h: n.h }));
    // WHY: gridstack stops a width at the grid's right side, but a width is only a number in the file and the row wraps, so an
    // east edge dragged past that side asks for that width, and the panel lands on the next row
    const east = this.east;
    this.east = null;
    const n = east && nodes.find((x) => x.key === east.key);
    if (n) {
      const { columns } = this.dash.dash;
      const cell = this.dash.querySelector('.dd-grid').getBoundingClientRect().width / columns;
      n.w = Math.max(n.w, Math.min(columns, Math.round((east.x - this.section(n.key).getBoundingClientRect().left) / cell)));
    }
    const sizes = this.sizes;
    this.apply((t) => arrangeText(t, readingOrder(nodes), sizes), 'arrange');
  }

  /** The panels exactly where the file draws them. */
  place() {
    if (this.gs) this.gs.load(this.items(this.s.text).map(({ key, x, y, w, h }) => ({ id: key, x, y, w, h })), false);
  }

  // ---------------------------------------------------------------- the one way anything changes

  /** Change the text: `edit` is a function of it. Edits run one after another. `after(next)` runs with the new text before
      the sides are drawn. Resolves whether the text changed. An edit that throws changes nothing and is said. */
  apply(edit, label = '', opts = {}) {
    this.busy = this.busy.then(() => this.run(edit, label, opts)).catch((err) => { this.say(`Could not change it: ${err.message}`); return false; });
    return this.busy;
  }

  async run(edit, label, { after, force = false, undoing = false }) {
    const prev = this.s.text;
    let next;
    try { next = edit(prev); parseBase(next); } catch (err) { this.say(`Could not change it: ${err.message}`); this.place(); return false; }
    if (typeof next !== 'string' || (next === prev && !force)) { this.place(); return false; }
    const was = this.sel ? this.panel(this.sel) : null;
    if (next !== prev && !undoing) this.s.push(next);
    this.note = '';
    if (was) {
      const now = panelsOf(next);
      const same = now.find((p) => identity(p) === identity(was)) || (label === 'text' ? now.find((p) => p.i === was.i) : null);
      this.sel = same ? same.key : null;
    }
    if (after) after(next);
    await this.show(prev, next, force);
    return true;
  }

  /** The canvas shows `next`; the sides follow. */
  async show(prev, next, force = false) {
    const { dash } = this;
    dash.baseText = next;
    if (!force && this.gs && layoutOnly(prev, next)) {
      dash._adopt(parseBase(next));
      this.place();
    } else await this.redraw(next);
    this.mark();
    this.drawSides();
    this.rev += 1;
    dash.dataset.ddeRev = String(this.rev);
  }

  /** Draw `text` in the dashboard: the rails, selections, tabs and clock stay (load with keepState), and the page where it was. */
  async redraw(text) {
    const { dash } = this;
    const base = parseBase(text);
    await this.s.ensureData(base);
    const keys = new Set(readDashboard(base).panels.map((p) => p.key));
    for (const part of [dash.state.select, dash.state.tabs, dash.state.legend]) for (const k of Object.keys(part || {})) if (!keys.has(k)) delete part[k];
    // WHY hold the height: a redraw empties the panels for a moment, and the page would scroll a reader off their place
    const y = scrollY;
    dash.style.minHeight = `${dash.offsetHeight}px`;
    dash.load(base, dash.datasets, { keepState: true });
    scrollTo(scrollX, y);
    clearTimeout(this.hold);
    this.hold = setTimeout(() => { dash.style.minHeight = ''; }, 600);
  }

  step(way) {
    return this.apply(() => { const t = way === 'undo' ? this.s.undo() : this.s.redo(); return t === null ? this.s.text : t; }, way, { undoing: true }).then(() => {});
  }

  // ---------------------------------------------------------------- what is on screen

  section(key) { return this.dash.querySelector(`.dd-panel[data-panel="${CSS.escape(key)}"]`); }
  panel(key) { return panelsOf(this.s.text).find((p) => p.key === key) || null; }

  drawSides() {
    this.outline.draw();
    this.options.draw();
    this.syncBar();
  }

  syncBar() {
    const { dash, s } = this;
    const q = (a) => dash.querySelector(`[data-act="${a}"]`);
    const n = s.changes().length;
    const status = dash.querySelector('.dde-status');
    if (status) status.textContent = this.note || (s.dirty ? `Editing · ${n || 1} change${n === 1 || !n ? '' : 's'}` : 'Editing');
    if (q('edit-undo')) q('edit-undo').disabled = !s.canUndo;
    if (q('edit-redo')) q('edit-redo').disabled = !s.canRedo;
    if (q('edit-save')) q('edit-save').disabled = !s.dirty;
    if (q('edit-filters')) q('edit-filters').setAttribute('aria-pressed', String(this.railOpen));
  }

  say(text) { this.note = text; this.syncBar(); }

  mark() {
    for (const sec of this.dash.querySelectorAll('.dd-panel[data-dde-selected]')) delete sec.dataset.ddeSelected;
    const sec = this.sel && this.section(this.sel);
    if (sec) sec.dataset.ddeSelected = '';
  }

  select(key, { reveal = false } = {}) {
    this.sel = key;
    this.review = null;
    this.mark();
    this.outline.draw();
    this.options.draw();
    if (reveal) this.reveal();
  }

  /** The selected panel on screen, in the outline's row and on the grid. */
  reveal() {
    const sec = this.sel && this.section(this.sel);
    if (sec) sec.scrollIntoView({ block: 'nearest' });
    const row = this.sel && this.outline.rowOf(this.sel);
    if (row) row.scrollIntoView({ block: 'nearest' });
  }

  /** A press on a panel selects it; on the grid's empty space, nothing. The press goes on to the panel. */
  press(e) {
    const east = e.target.closest('.ui-resizable-e, .ui-resizable-se');
    this.east = east ? { key: east.closest('.dd-panel').dataset.panel, x: e.clientX } : null;
    if (e.target.closest('[data-dde-pane], .dd-bar, .dd-rail')) return;
    const sec = e.target.closest('.dd-panel');
    if (sec && this.dash.contains(sec)) { if (sec.dataset.panel !== this.sel) this.select(sec.dataset.panel); return; }
    if (e.target.closest('.dd-grid') && this.sel) this.select(null);
  }

  key(e) {
    // WHY: two editors can be open on a page; a key belongs to the one the focus is in (the page's body belongs to either)
    const at = document.activeElement;
    if (at && at !== document.body && !this.dash.contains(at) && !at.closest('.dde-menu, dialog')) return;
    const typing = e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
    const mod = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (mod && k === 's') { e.preventDefault(); this.openReview(); return; }
    if (mod && k === 'b') {
      e.preventDefault();
      const pane = e.altKey ? this.optionsPane : this.outlinePane;
      pane.fold(!pane.folded);
      return;
    }
    if (mod && k === 'z' && !typing) { e.preventDefault(); e.stopPropagation(); this.step(e.shiftKey ? 'redo' : 'undo'); return; }
    if (e.key === 'Escape' && !document.querySelector('dialog[open], .dde-menu, .dv-addpick')) {
      if (this.review) { e.preventDefault(); this.closeReview(); } else if (this.sel && !typing) { e.preventDefault(); this.select(null); }
    }
  }

  // ---------------------------------------------------------------- Add, Filters

  addMenu(btn) {
    const datasets = Object.values(this.dash.dash.datasets).filter((d) => !d.template);
    menu(btn, [
      ...datasets.map((d) => ({ label: `View of ${d.label || d.name}`, test: `add-view-${d.name}`, run: () => this.addView(d) })),
      ...(datasets.length ? [{ sep: true }] : []),
      { label: 'Note', test: 'add-note', run: () => this.addNote() },
    ], { label: 'Add' });
  }

  /** Run an edit that adds a panel, and select what it added (its view is the one the text did not have), or `pick(next)`. */
  addSelecting(edit, label, pick = null) {
    const before = new Set((parseBase(this.s.text).views || []).map((v) => v && v.name));
    return this.apply(edit, label, { after: (next) => {
      const name = ((parseBase(next).views || []).find((v) => v && !before.has(v.name)) || {}).name;
      const p = pick ? pick(next) : panelsOf(next).find((x) => x.views[0] && x.views[0].name === name);
      if (p) this.sel = p.key;
      return name;
    } }).then((ok) => { if (ok) this.reveal(); return ok; });
  }

  /** A view of `d` to start from: a time series where it has a time column, else a table; the options pane does the rest. */
  addView(d) {
    const cols = this.s.columns(d.name);
    const y = cols.numbers.find((c) => c !== 't');
    const view = cols.numbers.includes('t') && y ? { type: 'timeseries', name: 'New panel', timeseries: { x: 't', y } } : { type: 'table', name: 'New panel' };
    const spec = { kind: 'view', view, dataset: { name: d.name, data: new URL(d.data, this.s.url).href, label: d.label || undefined }, h: 3 };
    const at = this.sel ? this.panel(this.sel) : null;
    this.addSelecting((t) => addPanel(t, spec, { base: this.s.url, at: at ? at.i + 1 : null }), 'add');
  }

  addNote() {
    const at = this.sel ? this.panel(this.sel) : null;
    const spot = at ? at.i + 1 : null;
    this.addSelecting((t) => insertPanel(t, { text: 'A note' }, spot), 'add', (next) => panelsOf(next).filter((p) => p.text === 'A note').at(-1));
  }

  /** The filter rail folds away while editing (the grid needs the room); one press brings it back beside the grid. */
  filters() {
    this.railOpen = !this.railOpen;
    this.dash.toggleAttribute('data-dde-filters', this.railOpen);
    this.syncBar();
  }

  // ---------------------------------------------------------------- Save: the diff first, then the host

  async openReview() {
    if (!this.s.dirty || this.review) return;
    this.review = { moved: false, copy: false, status: '' };
    if (this.optionsPane.folded) this.optionsPane.fold(false, { remember: false });
    this.options.draw();
    const go = this.optionsPane.body.querySelector('[data-dde="save-go"]');
    if (go) go.focus({ preventScroll: true });
    this.optionsPane.el.scrollIntoView({ block: 'nearest' });
    // the file itself, read again: an agent may have written it while this reader edited
    const src = this.dash.getAttribute('src');
    if (!src) return;
    try {
      const r = await fetch(new URL(src, location.href), { cache: 'no-store' });
      const text = r.ok ? await r.text() : null;
      if (this.review && text !== null && text !== this.s.saved) { this.review.moved = true; this.options.drawReview(); }
    } catch { /* unread: the host still has `before` */ }
  }

  closeReview() {
    this.review = null;
    this.options.draw();
    this.outline.focus();
  }

  /** The review's Save, or Save as copy (`asCopy`: {title}). */
  async commit(asCopy = null) {
    const field = this.optionsPane.body.querySelector('[data-dde="save-message"]');
    const message = field ? field.value : '';
    this.review.status = 'Saving…';
    this.options.drawReview();
    const r = await this.s.save({ message, asCopy });
    if (!this.review) return;
    if (!r.ok) {
      this.review.status = `Could not save: ${r.reason}`;
      this.options.drawReview();
      return;
    }
    const drained = await this.queue.drain();
    this.review = null;
    this.note = r.via === 'clipboard' ? 'No host saves here: the .base text is on the clipboard' : asCopy ? `Saved a copy: ${asCopy.title}` : 'Saved';
    if (drained && !drained.ok) this.note += `; the queue's file was not saved: ${drained.reason}`;
    this.drawSides();
    this.outline.focus();
  }
}
