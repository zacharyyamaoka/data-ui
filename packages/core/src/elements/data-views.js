/* <data-views>: the host. One dataset, the views of one .base file, one row model, any registered layout.

   Zach, 2026-10-25: "It's just data, views on that data and filters on that data, again and again." and "1 dataset,
   1 base file, many views". The table lane built this element around its table (robotparts lane/tables @ ab5ba92,
   views.js); here the toolbar, presets, URL, peek and row model stay in the element and the table became one
   registered view among the rest (packages/views/table). The contract is docs/CONTRACT.md; in short:

     el.data     a dataset in any accepted form (data.js), normalised to {id, title, titleProperty, properties, rows}
     el.base     the parsed .base document ({filters, properties, facets, views, ...}); el.presets = [view] also works
     el.baseText the file's text, when the host has it (⋯ then copies the whole file with this view in it)
     el.filters  the all-views filter the rail edits (starts as the file's top-level filters)
     el.hiddenSeries the series names a chart's legend hides (../legend.js); setting it redraws the view
     el.layers   the other datasets a 3D view's layers read, {<dataset>: {dataset, rows}} (docs/CONTRACT.md §32; a
                 <data-dashboard> sets it); the view gets them as input.layers
     attributes  src (a .base URL; its `data:` is loaded relative to it), data (a dataset URL), view (a view's name),
                 toolbar="full|bar|compact|none", no-url, editable, edit-toggle (§40), theme="light|dark",
                 open="expand|side|link" (how a record opens where the .base file does not say; ../open.js);
                 under toolbar="bar" (§15) views="auto|dropdown|tabs", filters="pills expanded query-tokens rail",
                 display="panel|popover", selectable, query (the bar itself is toolbar/bar.js; its View settings,
                 toolbar/settings.js)
     events      data-views-change {view, name, dirty, filters}   after every change
                 data-views-render {type, ms, rows}                after the view has drawn
                 data-views-open   {row, column, records}          when the peek opens
                 data-views-propose {id, set, row, result}         after the host decides on a data edit
                 data-views-legend {hidden}                        after a legend shows or hides a series
                 data-add-to-dashboard {dashboard, panel, text, respondWith}  a reader adds this view (or a series, a
                                                                   card, a field) to a dashboard (§34; ../add-picker.js)
     el.acceptAdd   async ({set}) => ({ok, id?, reason?}): files the table's add row (docs/CONTRACT.md §37)
     el.acceptPlace async ({property, from, to, dry, text, layout}) => ({ok, changes, total, note?, reason?}): moves a property's data
                    between the list and a heading, and writes the .base (§46); `dry` only says what it would do
     el.resolveMedia (src, {row, embed}) => url: where a page's `![](src)` is (§46)
     el.resolveLink  (target, {row}) => url | null: where a page's `[[target]]` opens (§46)
     el.openElsewhere (row) => ({label, href}) | null: another app for this record ("Obsidian"), on its page and in the row's Open in menu; null draws nothing (§46)
     el.cellSurface  'sheet' (default: a side panel that follows the cell and autosaves) | 'grow' | ({cell, form, box, row, property, measure}) => ({fit(), close()}): how a markdown cell is edited (§46)
     el.pageRenderer (host, {row, id, close}) => ({update?(row), destroy?()}) | void: draws a record's page in the side panel in the host's own style, kept across redraws (§46)
     el.acceptFile  async ({file, id, property}) => ({ok, attachment, reason?}): stores a file a media cell took; data-ui
                 keeps no bytes (§37); data-views-media {list, index}, cancelable, before a thumbnail opens large
     el.persistView async ({text, name, kind, view, selected, filters}) => ({ok, reason?}): a change to keep, as the .base
                 file's new text; a persist="local" attribute keeps it in this viewer's storage (§37)
     el.peekExtra   (row) => html, the host's own part at the foot of a record's side peek (§37)
     el.acceptBatch async ({edits, adds, deletes}) => ({ok, reason?, ids?}): one paste, undo or redo as one call (§40)
     el.acceptDelete async ({ids}) => ({ok, reason?}), el.acceptProperty async ({op, property, …}) => ({ok, reason?, property?}):
                 deleting rows and changing columns; an editable page with no hook does them in memory (§40)
     el.editing     with the edit-toggle attribute: whether Edit is on (setting it is the switch; data-views-edit-mode
                 {editing} after a change; docs/CONTRACT.md §40); else whether the page is `editable`
     el.precedence {order, default, ov, …} when a formula rolls columns up (docs/CONTRACT.md §36, ../precedence.js): a value
                 several sources state, or a .base's `formulas:`; setting {order?, ov?} changes it
     state       the current view in the URL hash (#view=<name>[&v=<changed view>][&f=<custom filters>][&l=<hidden
                 series>][&sources=<order>][&picks=<row>:<source>,…]), the rail's
                 facets as readable search params (?brand=A,B&peak_torque=10..<100&has=photo; facets.js), user presets in
                 localStorage under data-views/<data.id>. All read and written in try/catch.

   A view plugin gets update({rows, groups, columns, view, tokens, total, matched, table, pivot, dataset, query,
   filters, hiddenSeries, live, layers}) and may call host.setView(patch), host.propose({id, set}), host.open(id, opts),
   host.setStatus(html), host.setHiddenSeries(names), host.setFacet(property, facet | null) (docs/CONTRACT.md §20: a
   tile's drill). `view` is the effective one: with `grouping: <id>`, that groupings entry's groupBy, subGroupBy and
   tiles; the hash then carries `group=<id>`. */

import * as G from '../grammar.js';
import { resizeKit } from '../resize.js';
import { parseBase, replaceViewInText, replaceKeyInText, stringifyBase } from '../base.js';
import { normalizeDataset, loadDataset } from '../data.js';
import { rowModel, properties as labelled, isEmpty, MODEL_KEYS, bareView, search } from '../rowmodel.js';
import { markdown } from '../md.js';
import { viewPlugin, loadView, listViews } from '../registry.js';
import { resolveTokens } from '../tokens.js';
import { esc, fmtNum, numOpts, valueHtml, cellText, mediaUrl, slug, isNum, groupLabel, sourcesAttr, attachmentsOf, thumbsHtml } from '../format.js';
import { openMediaBox } from '../media-box.js';
import { isLong, sectionHtml, wireSections, fitSections } from '../page-section.js';
import { inspectorProperties, inspectorKey, moreHtml, visibilityButton, visibilityOf, addPropertyHtml, wireInspector, wordOf, setVisibility, columnIds } from '../inspector.js';
import './data-mesh.js';
import { fieldHtml, readEdits, lockedBecause } from '../form.js';
import { toRail, fromRail, allSpecs, railConfig, railProperties, railParams, paramsRail, isRailParam } from '../facets.js';
// docs/CONTRACT.md §15: the bar's query box and the selection are their own modules (lane B owns both files)
import { mountQuery, formatQuery, parseQuery } from '../toolbar/query.js';
import { Selection, mountBulk } from '../toolbar/selection.js';
// docs/CONTRACT.md §40: the notion table's writes, and what takes them back
import { EditSession } from '../edit-session.js';
import { openColumnMenu, openColumnAdd } from '../toolbar/column-menu.js';
import { openColumnFilter } from '../toolbar/column-filter.js';
// §15: the bar's views, tools and pills, and the View settings panel / popover (lane A)
import { mountBar, slashKey } from '../toolbar/bar.js';
import { mountExpand } from '../toolbar/expand.js';
import { mountSettings } from '../toolbar/settings.js';
import { mountFrame, pageScrolls, scrollParent } from '../frame.js';
import { OpenModes } from '../open.js';
import { mark, measure } from '../perf.js';
import { createRowModelWorker, workerEligible, recordingFetch, modelFromOrder, WORKER_ROWS } from '../rowmodel-worker.js';
import { liveData, atOf } from '../live/feed.js';
import { isLiveDataset } from '../live/store.js';
import { isLiveClock } from '../live/clock.js';
import { fastOrder, rankCache } from '../order.js';
import { encodeHidden, decodeHidden, hiddenAfter } from '../legend.js';
import { layersInput } from '../layers.js';
import { peekSections, linkHtml } from '../sections.js';
import { pageLayout, pageOn } from '../page-layout.js';
import { expandH1, liftH1 } from '../markdown-columns.js';
import { fitPage, moveOnPage, pageHtml, previewPlace, revealBlock, setPlace, showOnPage, stepOnPage, wirePage } from '../page-blocks.js';
// docs/CONTRACT.md §34: Add to dashboard (the panel a reader adds, the item menu and the picker)
import { andFilters, searchClause, inClause, ref, lit } from '../add-to-dashboard.js';
import { openPicker, openItemMenu, closeAddUi, releaseAddUi, adoptAddUi } from '../add-picker.js';
// docs/CONTRACT.md §36, the source popover: a value two or more sources state lists them in its item menu
import { sourcesMenu } from '../source-popover.js';
import { clockFor, fmtTime } from '../clock.js';
// docs/CONTRACT.md §36: a value several sources state, and which one is nominal (precedence.js is pure)
import { agreement, precedenceOf, unfoldDataset, resolveDataset, ownColumns, sourcesView, slotOrder, orderAfter, placeShown, foldEdit, formulaView, formulaText, fieldsOf, normalizeOrder, normalizePicks, changed as changedFields, held as heldFields, encodeOrder, decodeOrder, encodePicks, decodePicks, isMultiSource } from '../precedence.js';
import { drawNotes, aboutButton, mountNotes } from '../notes.js';
import { editProperty as applyProperty, fileEdit } from '../propedit.js';

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const VIEW_REFUSES = 'This page is in View mode: turn on Edit to change it.';
// a dataset this big paints the toolbar before its first model is built (_start)
const PAINT_FIRST_ROWS = 20000;
// rows per slice when the rows are cloned to the row-model worker (one task each; _ensureWorker)
const WORKER_SLICE = 2000;
const store = {
  get(key) { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window: presets last this visit */ } },
};

// Types docs/VIEWS.md selects that no plugin has registered yet: an unknown type draws the table with a notice.
// trajectory3d and voxels are CONTRACT §32's (PEP 0010; built in P1b and P2): the schema knows them before their views.
export const PLANNED_TYPES = ['table', 'pivot', 'list', 'cards', 'kanban', 'chart', 'kpi', 'calendar', 'timeline', 'map', 'graph', 'record', 'compare', 'trajectory3d', 'voxels'];
const PLANNED_IN = { trajectory3d: 'docs/CONTRACT.md §32', voxels: 'docs/CONTRACT.md §32' };

function setPath(obj, path, value) {
  const keys = path.split('.');
  let o = obj;
  for (let k = 0; k < keys.length - 1; k++) {
    const key = /^\d+$/.test(keys[k]) ? Number(keys[k]) : keys[k];
    if (o[key] === undefined || o[key] === null) o[key] = /^\d+$/.test(keys[k + 1]) ? [] : {};
    o = o[key];
  }
  const last = /^\d+$/.test(keys[keys.length - 1]) ? Number(keys[keys.length - 1]) : keys[keys.length - 1];
  if (Array.isArray(o)) {
    if (value === '' || value === null || value === undefined) o.splice(last, 1);
    else o[last] = value;
    for (let k = o.length - 1; k >= 0; k--) if (o[k] === undefined || o[k] === null || o[k] === '') o.splice(k, 1);
  } else o[last] = value === '' ? null : value;
}

function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? o : o[/^\d+$/.test(k) ? Number(k) : k]), obj);
}

export class DataViews extends HTMLElement {
  constructor() {
    super();
    this._data = null;
    this._base = null;
    this._filters = undefined;
    this.view = null;
    this.origin = null; // {kind: 'preset'|'user', name, view}
    this.query = '';
    this._peek = null;
    this._plugin = null;
    this._pluginType = null;
    this._renderId = 0;
    this._status = '';
    this._hidden = [];   // the series a chart's legend hides (../legend.js): drawing state, never the data's
    // CONTRACT §36: the data as loaded (_raw), with its columns (_unfolded: one property per source) and as the reader sees it
    // (_data: each formula its first non-empty column); all three the same object when nothing rolls up. The precedence {order, ov}
    this._raw = null;
    this._unfolded = null;
    this._precInfo = null;
    this._prec = null;
    this._selection = new Selection(this);
    this._picked = new Set();   // CONTRACT §39: the rows a host marks (a dashboard panel's picks), never the selection
    this._session = new EditSession(this);
    this._viewRefuses = VIEW_REFUSES;
    this._actions = null;
    const el = this;
    this._host = Object.freeze({
      setView: (patch) => el.setView(patch),
      propose: (edit) => el.propose(edit),
      open: (id, opts) => el.openPeek(id, opts),
      setStatus: (html) => { el._status = html || ''; el._drawStatus(); },
      // CONTRACT §37: the add row files through the page, a media cell's file goes to the page, a thumbnail opens large
      add: (set) => el.addRow(set),
      // CONTRACT §40
      deleteRows: (ids) => el.deleteRows(ids),
      batch: (plan, opts) => el.batch(plan, opts),
      isSourced: (id, property) => el.isSourced(id, property),
      columnMenu: (id, anchor) => openColumnMenu(el, id, anchor),
      columnAdd: (anchor) => openColumnAdd(el, anchor),
      paste: (plan) => el._session.paste(plan),
      attach: (file, where) => el.attachFile(file, where),
      showMedia: (list, index) => el.showMedia(list, index),
      // CONTRACT §31: a legend's hidden set; the view has drawn it already, the element keeps it (URL, event, next input)
      setHiddenSeries: (names) => el._setHidden(names, true),
      // CONTRACT §36: precedence for every row ({order}) and one row's pick ({ov: {<row>: <source> | null}}); null resets
      setPrecedence: (patch) => el.setPrecedence(patch),
      // CONTRACT §36: a value's pill opens the menu a right-click on it opens
      sourcesMenu: (pill) => el._sourcesMenu(pill),
      // §15: a view reports a click on a row's selector; the element owns the set (shift = range, toggle = ctrl/cmd)
      select: (id, mods) => { if (el._selection.click(id, mods || {}, el._model ? el._model.rows.map((r) => String(r.id)) : [])) el._selectionChanged(); },
      // one property's part of the all-views filter, as the rail writes it (docs/CONTRACT.md §20)
      setFacet: (property, facet) => el.setFacet(property, facet),
      get element() { return el; },
      // the element (or window) that scrolls the rows under frame="page|bleed"; null = the view's own box (src/frame.js)
      get scroller() { return el._scroller || null; },
      // how a record opens (`open:`, ../open.js): the controller while the view is a table or cards, else null
      get opener() { return el._open.forView(); },
      // CONTRACT §28: whether the column menu may change the .base file's properties, and the call that does
      // WHY el.editing, not the attribute: on an edit-toggle page (§40) View is read-only and Edit needs no `editable`
      get writable() { return el.editing; },
      editProperty: (edit) => el.editProperty(edit),
    });
    this._open = new OpenModes(this);
  }

  static get observedAttributes() { return ['src', 'data', 'theme', 'frame', 'open', 'status', 'controls', 'toolbar', 'views', 'filters', 'display', 'selectable', 'query', 'search', 'promote', 'labels', 'editable', 'add-row', 'view-counts', 'edit-toggle']; }

  // a LiveDataset goes to its feed (live/feed.js): the rows at the clock's t, redrawn at most once per frame
  set data(d) { if (liveData(this, d)) return; const had = this._unfolded !== this._raw; this._setRaw(d ? normalizeDataset(d) : null); this._dataUrl = (d && typeof d === 'object' && !Array.isArray(d) && d.url) || null; this._byId = null; this._seed = null; this._dropWorker(); this._revise(); if (this._started && (had || this._unfolded !== this._raw)) this._columnsAgain(); this._started ? this._render() : this._start(); }
  get data() { return this._data; }
  /** The data as loaded, then as shown (CONTRACT §36): `_data` is `_raw` with one property per source and each formula resolved
      under the precedence state, or `_raw` itself when nothing rolls up (so nothing changes for such data). */
  _setRaw(raw) {
    // §46: `columns: h1` on a markdown property: one column per H1 in it
    this._raw = expandH1(raw, this._base && this._base.properties);
    this._prec = null; // read again (URL, storage, default) for this data
    this._precNote = null; // what the last change did was about the data before
    this._unfold();
    this._data = this._shown();
  }
  _unfold() {
    const raw = this._raw;
    this._precInfo = raw ? precedenceOf(raw, this._base) : null;
    this._unfolded = raw ? unfoldDataset(raw, this._precInfo, this._base) : null;
  }
  _shown() {
    const raw = this._raw;
    if (!raw || this._unfolded === raw) return raw;
    if (this._precInfo && !this._prec) this._prec = this._readPrec();
    const out = resolveDataset(this._unfolded, this._prec || {}, this._precInfo);
    // a shown row's origin is its loaded row's (CONTRACT §24's source view, the source panel)
    const back = new Map();
    out.rows.forEach((r, i) => { if (r !== raw.rows[i]) back.set(r, raw.rows[i]); });
    const originOf = raw.originOf ? (row) => raw.originOf(back.get(row) || row) : undefined;
    if (raw.raw) Object.defineProperty(out, 'raw', { value: raw.raw, configurable: true, writable: true });
    if (originOf) Object.defineProperty(out, 'originOf', { value: originOf, configurable: true, writable: true });
    return out;
  }
  /** The row as loaded behind an id (an edit lands there, then the rows are resolved again). */
  _rawRow(id) {
    // WHY the map when they are the same rows: a pasted block asks once per cell (isSourced), and a scan would be rows × cells
    if (this._raw && this._data === this._raw) return this.row(id);
    const rows = (this._raw || this._data || { rows: [] }).rows;
    return rows.find((r) => String(r.id) === String(id)) || null;
  }

  // ------------------------------------------------------------------ CONTRACT §40: Edit and View
  /** The page has the switch: the attribute, on rows that can be edited (a live dataset's are its feed's). */
  _hasSwitch() { return this.hasAttribute('edit-toggle') && !this._live; }
  /** Edit on an edit-toggle page: what draws delete, paste and the column menu, and keeps undo. WHY not plain `editable`:
      a page with that alone behaves exactly as §37 says (Vibe Tracks depends on it). */
  _editTools() { return this._hasSwitch() && !!this._editOn; }
  /** View on an edit-toggle page: a read-only table, whatever hooks the page has. */
  _viewOnly() { return this._hasSwitch() && !this._editOn; }
  /** Whether a reader's edits go through here now: the switch on an edit-toggle page, else the `editable` attribute. */
  get editing() { return this._hasSwitch() ? !!this._editOn : this.hasAttribute('editable'); }
  set editing(on) { this.setEditing(on); }
  _editKey() { return `data-views/${(this._data && this._data.id) || 'data'}/edit`; }
  /** The link's word, else this viewer's memory, else View: where an edit-toggle page opens. */
  _readEdit() {
    if (!this.hasAttribute('no-url')) {
      try { const h = new URLSearchParams(location.hash.slice(1)); if (h.has('edit')) return h.get('edit') === '1'; } catch { /* an unreadable link: memory */ }
    }
    const kept = store.get(this._editKey());
    // edit-toggle="edit": a page made to be written in (a playground) opens in Edit for a viewer who has not chosen
    return kept === null ? this.getAttribute('edit-toggle') === 'edit' : kept === true;
  }
  /** Turn Edit on or off. Off commits what is open first; a refusal keeps the editor, what was typed and Edit on, so
      switching off never drops a reader's words. Returns whether Edit is on now. */
  async setEditing(on) {
    const next = !!on;
    if (!this._hasSwitch() || next === !!this._editOn) return this.editing;
    if (!next) {
      const open = document.activeElement, peek = this.$ && this.$('.dv-peek');
      if (open && peek && peek.contains(open)) open.blur();
      if (this._plugin && this._plugin.endEdit && !(await this._plugin.endEdit())) return this.editing;
    }
    this._applyEdit(next);
    return this.editing;
  }
  _applyEdit(next) {
    this._editOn = next;
    this._kept = null; // leaving Edit is a refresh: View shows what matches
    this._session.hideToast();
    store.set(this._editKey(), next);
    if (!this._started) return;
    this._render();
    // the open record reads as the page now does: its sections are editors in Edit, words in View
    if (this._peek && this.row(this._peek.id)) this.openPeek(this._peek.id, this._peek.opts);
    this.dispatchEvent(new CustomEvent('data-views-edit-mode', { detail: { editing: next } }));
  }

  // ------------------------------------------------------------------ CONTRACT §40: an edited row stays until the view refreshes
  /** What decides which rows match: when it changes, the view has refreshed. */
  _keepKey() { return JSON.stringify([this._filters ?? null, (this.view && this.view.filters) ?? null, this.query, this.origin && this.origin.name]); }
  /** Rows a reader has just edited. WHY (Notion's way): a row must not vanish under the hand editing it. Only while anything can hide a row. */
  _keepRows(ids) {
    if (!ids.length || (this._filters === undefined && !(this.view && this.view.filters) && !this.query)) return;
    const key = this._keepKey();
    if (!this._kept || this._keptKey !== key) { this._kept = new Set(); this._keptKey = key; }
    for (const id of ids) this._kept.add(String(id));
  }
  /** The rows to keep for this render, or null; a new filter, search or view has let them go. */
  _keeping() {
    if (!this._kept) return null;
    if (this._keptKey !== this._keepKey()) { this._kept = null; return null; }
    return this._kept;
  }
  /** Apply the filter to the rows again: the status line's Refresh. */
  refreshRows() { this._kept = null; this._render(); }

  // ------------------------------------------------------------------ CONTRACT §36: source precedence
  /** {order, default, ov, ids, sources, ladder, properties} (copies), or null when nothing rolls up. */
  get precedence() {
    const info = this._precInfo;
    if (!info) return null;
    if (!this._prec) this._prec = this._readPrec();
    return { order: [...this._prec.order], default: [...info.default], ov: { ...this._prec.ov }, ids: [...info.ids], sources: clone(info.sources), ladder: clone(info.ladder), properties: [...info.properties] };
  }
  set precedence(patch) { this.setPrecedence(patch); }
  _precKey() { return `data-ui/sources/${typeof location !== 'undefined' ? location.pathname : ''}/${(this._raw && this._raw.id) || 'data'}`; }
  _precFields() { return this._precInfo ? fieldsOf(this._unfolded.rows, this._precInfo.properties) : []; }
  /** The state as the link says (sources=, picks=), else as this viewer left it (localStorage), else the default. */
  _readPrec() {
    const info = this._precInfo;
    let order = null, ov = null;
    if (!this.hasAttribute('no-url')) {
      try {
        const h = new URLSearchParams(location.hash.slice(1));
        if (h.has('sources')) order = decodeOrder(h.get('sources'));
        if (h.has('picks')) ov = decodePicks(h.get('picks'));
      } catch { /* an unreadable link: storage, else the default */ }
    }
    if (order === null && ov === null) {
      const kept = store.get(this._precKey());
      if (kept && typeof kept === 'object') { order = Array.isArray(kept.order) ? kept.order : null; ov = kept.ov || null; }
    }
    return { order: normalizeOrder(order, info.ids, info.default), ov: normalizePicks(ov || {}, this._precFields()) };
  }
  /** Change the precedence: `order` replaces the order (null: the default); `ov` merges one row's picks (a null source
      removes that row's; `ov: null` removes every pick). Re-resolves the rows, keeps the state (URL and this viewer's
      storage), fires data-views-precedence {order, default, ov, changed, held} (row ids) and redraws. Returns the state. */
  setPrecedence(patch) {
    const info = this._precInfo;
    if (!info) return null;
    if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('setPrecedence({order?, ov?}): a patch object');
    if (!this._prec) this._prec = this._readPrec();
    const before = { order: [...this._prec.order], ov: { ...this._prec.ov } };
    const order = 'order' in patch ? normalizeOrder(patch.order === null ? info.default : patch.order, info.ids, info.default) : before.order;
    let ov = { ...before.ov };
    if ('ov' in patch) {
      if (patch.ov === null) ov = {};
      else if (patch.ov && typeof patch.ov === 'object') for (const [row, src] of Object.entries(patch.ov)) { if (src === null || src === undefined || src === '') delete ov[row]; else ov[row] = String(src); }
    }
    return this._applyPrec(before, { order, ov: normalizePicks(ov, this._precFields()) });
  }
  /** Take a precedence state (normalised): keep it, resolve the rows again, say what changed, redraw (`draw`: a caller that is about
      to). The views' source columns follow, in the places they have. */
  _applyPrec(before, after, { draw = true } = {}) {
    const info = this._precInfo;
    const { order, ov } = after;
    const fields = this._precFields();
    if (JSON.stringify(after) === JSON.stringify(before)) return this.precedence;
    this._prec = after;
    // WHY kept per viewer, beside the URL (Zach's spec: "kept in the URL plus per-viewer storage"): a reader's order and
    // picks come back on their next visit to this page; the default leaves nothing behind
    const isDefault = order.join('\u0000') === info.default.join('\u0000') && !Object.keys(ov).length;
    try { if (isDefault) localStorage.removeItem(this._precKey()); else store.set(this._precKey(), after); } catch { /* private window */ }
    this._data = this._shown();
    this._byId = null;
    this._revise();
    this._slot(this.view);
    if (this.origin) this._slot(this.origin.view);
    const ids = (list) => [...new Set(list.map((f) => f.id))];
    const ch = ids(changedFields(fields, before, after)), hd = ids(heldFields(fields, before, after));
    const moved = order.join('\u0000') !== before.order.join('\u0000');
    this._precNote = moved || ch.length ? { changed: ch.length, held: hd.length } : null;
    this.dispatchEvent(new CustomEvent('data-views-precedence', { detail: { order: [...order], default: [...info.default], ov: { ...ov }, changed: ch, held: hd } }));
    if (draw && this._started) {
      this._render();
      // the open peek shows the row as it now reads
      if (this._peek && this.row(this._peek.id)) this.openPeek(this._peek.id, this._peek.opts);
    }
    return this.precedence;
  }
  /** A view's source columns in precedence order, in its places. */
  _slot(view) {
    if (view && Array.isArray(view.order) && this._prec) view.order = slotOrder(view.order, this._precInfo, this._prec.order);
  }
  /** input.precedence for the views: null, or {properties, ids, sources, ladder, order, default, ov, members, lists}. */
  _precInput() {
    const p = this.precedence;
    return p && Object.freeze({ ...p, members: this._precInfo.members, lists: this._precInfo.lists });
  }
  /** The status line's precedence notes: the order changed from the default (Reset), the rows chosen by hand (Clear),
      what the last change did. */
  _precStatusHtml() {
    const p = this.precedence;
    if (!p) return '';
    const out = [];
    if (p.order.join('\u0000') !== p.default.join('\u0000')) out.push('<span class="dv-src-note">Precedence changed from default · <button type="button" class="dv-link" data-sources-reset>Reset</button></span>');
    const n = Object.keys(p.ov).length;
    if (n) out.push(`<span class="dv-src-note">${n} chosen by hand · <button type="button" class="dv-link" data-sources-clear>Clear</button></span>`);
    const note = this._precNote;
    if (note) out.push(`<span class="dv-src-note dv-src-effect">${note.changed} ${note.changed === 1 ? 'value' : 'values'} changed${note.held ? ` · ${note.held} kept by ${note.held === 1 ? 'its override' : 'their overrides'}` : ''}</span>`);
    return out.length ? ` · ${out.join(' · ')}` : '';
  }
  /** A number that changes whenever the rows may have: new data, or an edit (which changes a row in place, so the
      dataset's identity alone cannot tell). WHY: what caches work derived from the rows keys on it (the rail's counts;
      perf review 2026-10-26, items 3 and 5). Read-only; a host that changes rows gives new data (or goes through
      propose), as before. */
  get dataRevision() { return this._rev || 0; }
  _revise() { this._rev = (this._rev || 0) + 1; }
  set base(doc) { this._setBase(doc); }
  get base() { return this._base; }
  set presets(list) { this._setBase({ ...(this._base || {}), views: list || [] }); }
  /** The file's views, then the view that shows the sources when the file has none (CONTRACT §36). */
  get presets() {
    const views = (this._base && this._base.views) || [];
    const sources = this._precInfo ? sourcesView(views, this._precInfo) : null;
    return sources ? [...views, sources] : views;
  }
  set filters(f) { this._filtersSet = true; this._filters = f === null || f === '' ? undefined : clone(f); if (this._started) this._render(); }
  get filters() { return this._filters; }
  /** CONTRACT §31: the series the open view's legend hides (names); setting it redraws the view with them hidden. */
  get hiddenSeries() { return [...this._hidden]; }
  set hiddenSeries(names) { this._hiddenGiven = true; this._setHidden(names, false); }
  /** CONTRACT §32: the other datasets the view's layers read, {<dataset>: {dataset, rows}}, as a <data-dashboard> hands
      them (each filtered as a panel on that dataset would be); the view gets them as input.layers (../layers.js).
      WHY a redraw after the current task, not at once: a dashboard sets a panel's layers and its filters together on a
      click, and a 3D view rebuilt twice per click costs twice; any draw in between already carries the new layers. */
  get layers() { return this._layers || null; }
  set layers(v) {
    this._layers = v && typeof v === 'object' ? v : null;
    this._layersShaped = null;
    this._layersOwed = true;
    if (!this._started || this._layersQueued) return;
    this._layersQueued = true;
    queueMicrotask(() => { this._layersQueued = false; if (this._layersOwed && this._started && this._model) this._render(); });
  }
  /** input.layers for the next update: shaped once per (layers, .base) pair; reading it settles a pending redraw. */
  _layersInput() {
    this._layersOwed = false;
    const c = this._layersShaped;
    if (c && c.layers === this._layers && c.base === this._base) return c.value;
    const value = layersInput(this._layers, this._base);
    this._layersShaped = { layers: this._layers, base: this._base, value };
    return value;
  }
  get host() { return this._host; }
  /** The data file's URL, which a relative path in a cell resolves against (the page's URL when the data came from
      script without a `url`). */
  get dataUrl() { return this._dataUrl || (typeof document !== 'undefined' ? document.baseURI : null); }
  get model() { return this._model; }

  _setBase(doc) {
    const views = ((doc && doc.views) || []).map((v) => ({ type: 'table', ...v }));
    // CONTRACT §37: a file that now names another view opens on it; a change that does not touch defaultView stays where it is
    if (this._base && doc && doc.defaultView !== this._base.defaultView) this.origin = null;
    const was = this._base;
    this._base = { ...(doc || {}), views };
    if (this._raw) expandH1(this._raw, this._base.properties);
    // CONTRACT §36: a file's formulas, and a view that orders the sources, say what rolls up and in what order
    if (this._raw && (this._precInfo || this._base.formulas || (was && was.formulas))) this._setRaw(this._raw);
    if (!this._filtersSet) this._filters = clone(this._base.filters);
    if (this._started) { this._started = false; this._start(); } else this._start();
  }

  attributeChangedCallback(name, old, value) {
    if (old === value) return;
    if (name === 'theme') { this._tokens = null; if (this._started) this._render(); return; }
    // WHY not while starting: the View settings' kept Frame pick is set as the chrome mounts, and _start frames the
    // element once itself (_applyFrame), so the view is made once, not twice (and never before a view is chosen)
    if (name === 'frame') { if (this._started && !this._starting) this._reframe(); return; }
    if (name === 'open' || name === 'editable' || name === 'add-row' || name === 'view-counts') { if (this._started) this._render(); return; }
    // CONTRACT §40: the switch is part of the chrome, so it is drawn or taken away as `toolbar` does, the open view kept
    if (name === 'edit-toggle') { if (this._started) { this._keepView = { origin: clone(this.origin), view: clone(this.view) }; this._started = false; this._start(); } return; }
    // CONTRACT §18: an embedding host turns the status line or a view's control bar off and on, live
    if (name === 'status' || name === 'controls') { if (this._started) this._applyChrome(); return; }
    // §15: the chrome's attributes are read live; the view, filters, query and selection stay. Only `toolbar` rebuilds
    // the element's chrome (and keeps the open view, changes and all); the bar's own variants redraw the bar alone.
    if (name === 'toolbar') { if (this._started) { this._keepView = { origin: clone(this.origin), view: clone(this.view) }; this._started = false; this._start(); } return; }
    if (['views', 'filters', 'display', 'selectable', 'search', 'promote', 'labels'].includes(name)) {
      if (!this._started) return;
      if (name === 'filters' && this._queryUi) {
        this._queryUi.destroy();
        this._queryUi = mountQuery(this, this.$('.dv-bar-query'), { tokens: this._filterModes().includes('query-tokens') });
      }
      if (name === 'display' && this._settingsUi) this._settingsUi.close();
      if (this._barUi) this._barUi.configure();
      this._render();
      return;
    }
    if (name === 'query') { if (this._started) this.setQuery(value || ''); return; }
    if (this.isConnected) this._load();
  }

  connectedCallback() {
    // put back after its chrome was released (disconnectedCallback): start again, keeping the open view and its changes
    if (this._chromeGone && this._started) { this._chromeGone = false; this._keepView = { origin: clone(this.origin), view: clone(this.view) }; this._started = false; }
    if (this.getAttribute('src') || this.getAttribute('data')) this._load();
    this._start();
    this._watchTheme();
    this._listenDocument();
    this._listenLegend();
    if (this._started && !this._unframe) this._reframe(); // moved in the page (or put back): its scroller may be another one
    if (this._started && !this._resizers) this._resizers = resizeKit(this);
    this._open.connect();
    if (this._live) this._live.connect();
    // CONTRACT §34: the picker of the element this one replaces (same id) comes back here once the chrome is drawn
    if (this._started) adoptAddUi(this);
  }

  /** Re-read src and data (an agent edited the file): the view, the rail and the URL state stay. */
  reload() { this._loadedFrom = null; return this._load(); }

  disconnectedCallback() {
    this._flushPersist();
    // WHY release everything: the document's listeners hold this element, and the plugin may hold virtualizers, React
    // roots, maps and observers; a removed element must not keep them (2026-10-26 performance review). Put back, the
    // element makes them again: connectedCallback re-listens, re-watches and _reframe() makes a new plugin.
    if (this._themeObserver) { this._themeObserver.disconnect(); this._themeObserver = null; }
    if (this._searchFrame) { cancelAnimationFrame(this._searchFrame); this._searchFrame = 0; }
    if (this._unframe) { this._unframe(); this._unframe = null; }
    if (this._media) { this._media.removeEventListener('change', this._onTheme); this._media = null; }
    if (this._onDocClick) { document.removeEventListener('click', this._onDocClick); document.removeEventListener('keydown', this._onDocKey); this._docListening = false; }
    // the side panels' drag handles hold a window resize listener and observers (src/resize.js); open modes holds
    // popstate, the phone query and its observers (src/open.js): both let go here and are made again when put back
    for (const r of this._resizers || []) r.destroy();
    this._resizers = null;
    this._open.disconnect();
    if (this._onLegendNav) { removeEventListener('hashchange', this._onLegendNav); removeEventListener('popstate', this._onLegendNav); this._onLegendNav = null; }
    ++this._renderId; // a view still loading for this element must not be made after it left
    this._dropWorker(); // the row-model worker and its copy of the rows; put back, the next draw makes a new one
    if (this._plugin) { try { this._plugin.destroy(); } catch { /* the view's cleanup must not block the element's */ } }
    this._plugin = null;
    this._pluginType = null;
    // §15: the bar's parts hold document, window and ResizeObserver listeners (the bulk bar's outside click, the View
    // settings' scroll follow and drag handle, the bar's auto layout); they go too, and connectedCallback makes the
    // chrome again with the view kept as it was
    const chrome = ['_barUi', '_expandUi', '_queryUi', '_settingsUi', '_bulkUi'].filter((k) => this[k]);
    for (const k of chrome) { try { this[k].destroy(); } catch { /* one part's cleanup must not block the rest */ } this[k] = null; }
    if (chrome.length) this._chromeGone = true;
    if (this._live) this._live.disconnect(); // its clock's listeners; put back, connect() binds again
    // an item menu of this element holds the document's keys and presses (../add-picker.js): it goes too. A picker waits
    // for the element of this id that a redraw of its dashboard makes, and moves into it (CONTRACT §34)
    releaseAddUi(this);
  }

  /** Fetch src (a .base file) and its data, or the data attribute. */
  async _load() {
    const src = this.getAttribute('src');
    const dataUrl = this.getAttribute('data');
    // WHY once per source: an upgraded element hears its attributes and then connects; one fetch, not two
    const key = `${src}|${dataUrl}`;
    if (this._loadedFrom === key) return this._loading;
    this._loadedFrom = key;
    this._loading = this._fetch(src, dataUrl);
    return this._loading;
  }

  async _fetch(src, dataUrl) {
    // WHY a generation and an abort: src or data can change while the last files are still on their way; an older
    // answer arriving late must never replace newer data (2026-10-26 performance review)
    const gen = (this._fetchGen = (this._fetchGen || 0) + 1);
    if (this._abort) this._abort.abort();
    const { signal } = (this._abort = new AbortController());
    const get = (url) => fetch(url, { signal });
    const stale = () => gen !== this._fetchGen;
    try {
      let base = this._base, text = null;
      // WHY at once: an explicit data= URL does not depend on the .base, so both requests go out together, and the view's
      // code is requested as soon as the .base names it, while the data is still on its way (perf review 2026-10-26,
      // item 6: the chain was .base -> data -> parse -> model -> view code -> rows)
      const explicit = dataUrl ? new URL(dataUrl, location.href).href : null;
      // the data's responses are kept (recordingFetch) for the row-model worker to parse the same bytes (_ensureWorker)
      const rec = recordingFetch(get);
      const early = explicit ? loadDataset(explicit, { fetch: rec.fetch }) : null;
      if (early) early.catch(() => { /* reported where it is awaited, below */ });
      if (!src) this._prefetchView(this._base);
      if (src) {
        text = await (await get(src)).text();
        if (stale()) return;
        base = parseBase(text);
        this._prefetchView(base);
      }
      const from = explicit || (base && base.data && src ? new URL(base.data, new URL(src, location.href)).href : null);
      const data = early ? await early : from ? await loadDataset(from, { fetch: rec.fetch }) : this._data;
      if (stale()) return;
      this.baseText = text;
      if (data !== this._raw) this._dropWorker();
      this._setRaw(data);
      this._revise();
      // WHY only for big data: the response text is as big as the file; below WORKER_ROWS no worker will want it
      if (from && data.rows.length >= WORKER_ROWS) this._seed = { url: from, bodies: rec.bodies, data, rev: this._rev };
      else if (data !== (this._seed && this._seed.data)) this._seed = null;
      if (from) this._dataUrl = from;
      this._byId = null;
      mark('data-ui:data', { id: this.id || null });
      if (base) this._setBase(base); else this._start();
    } catch (err) {
      if (stale()) return; // superseded (or aborted): the newer request reports its own outcome
      this.innerHTML = `<p class="dv-err">data-ui could not load ${esc(src || dataUrl)}: ${esc(err.message)}</p>`;
    }
  }

  /** Ask for the code of the view this element will most likely open on (the view attribute, the link's #view= or v=,
      else the first preset), so it loads beside the data. A wrong guess costs one cached request, never a wrong view:
      _render still loads whatever view is chosen. */
  _prefetchView(base) {
    const views = (base && base.views) || [];
    if (!views.length) return;
    let want = this.getAttribute('view') ? slug(this.getAttribute('view')) : null;
    let type = null;
    if (!this.hasAttribute('no-url')) {
      try {
        const h = new URLSearchParams(location.hash.slice(1));
        if (h.get('view')) want = h.get('view');
        if (h.get('v')) type = (G.decodeView(h.get('v')) || {}).type || null;
      } catch { /* an unreadable link: guess from the presets */ }
    }
    const pick = (want && views.find((v) => slug(v.name || '') === want)) || views[0];
    type = type || (pick && pick.type) || 'table';
    if (!viewPlugin(type)) type = 'table';
    if (viewPlugin(type)) loadView(type).catch(() => { /* _render reports a view that fails to load */ });
  }

  _watchTheme() {
    if (this._themeObserver || typeof MutationObserver === 'undefined') return;
    // WHY watch the page: a host flips its tokens with a class or data-theme on <html>; charts and maps need the
    // new colours as values, so the view updates when they change (docs/CONTRACT.md §4)
    this._onTheme = () => { if (this._started) { const before = JSON.stringify(this._tokens); this._tokens = null; if (JSON.stringify(this.tokens()) !== before) this._render(); } };
    this._themeObserver = new MutationObserver(this._onTheme);
    for (const node of [document.documentElement, document.body].filter(Boolean)) this._themeObserver.observe(node, { attributes: true, attributeFilter: ['class', 'data-theme', 'style', 'theme'] });
    this._media = matchMedia('(prefers-color-scheme: dark)');
    this._media.addEventListener('change', this._onTheme);
  }

  /** The resolved tokens (cached until the theme changes). */
  tokens() {
    if (!this._tokens) this._tokens = resolveTokens(this);
    return this._tokens;
  }

  // ------------------------------------------------------------------ lifecycle
  _start() {
    if (!this.isConnected || !this._data || !this._base || this._started) return;
    this._started = true;
    this._starting = true;
    try { this._startChrome(); } finally { this._starting = false; }
    adoptAddUi(this);
  }

  _startChrome() {
    // the chrome is about to be drawn again: an item menu or picker open in it goes (CONTRACT §34)
    if (this.querySelector('.dv-addpick, .dv-itemmenu')) closeAddUi();
    if (this._plugin) { try { this._plugin.destroy(); } catch { /* the old view's cleanup must not block the new start */ } }
    this._plugin = null;
    this._pluginType = null;
    const keep = this.origin && this.origin.name;
    // WHY keep the host's own markup: a host (robotparts) server-renders the table inside <data-views> for readers
    // without JavaScript and crawlers; replacing it with "Loading…" here blanked the rows a reader already had until
    // the view's code arrived. It stays in the stage, as the only rows on the page, until the view draws its own
    // (then it is removed, so the page never has the rows twice). Only on the first start: later starts hold this
    // element's own markup.
    const served = !this._ownMarkup && this.firstChild ? [...this.childNodes] : null;
    this._ownMarkup = true;
    this.classList.add('dv');
    const bar = this.getAttribute('toolbar') === 'bar';
    this.classList.toggle('dv-has-bar', bar);
    // CONTRACT §40: read once per element; a re-start (a new .base) keeps the choice
    if (this._editOn === undefined && this._hasSwitch()) this._editOn = this._readEdit();
    // §15 toolbar="bar": the bar's slots (lane A draws views and tools; lane B's query box and bulk bar mount in theirs).
    // The full toolbar's buttons stay in the DOM, hidden, so every menu (openMenu) keeps one implementation.
    this.innerHTML = `${bar ? `
      <div class="dv-bar" role="toolbar" aria-label="View">
        <div class="dv-bar-views"></div>
        <div class="dv-bar-query"></div>
        <div class="dv-bar-tools"></div>
      </div>
      <div class="dv-subbar"><div class="dv-pills"></div></div>` : ''}
      <div class="dv-head" role="toolbar" aria-label="View"${bar ? ' hidden' : ''}>
        <div class="dv-tabs" role="tablist"></div>
        <div class="dv-tools">
          <label class="dv-search"><span class="dv-sr">Search</span><input type="search" placeholder="Search" aria-label="Search rows"></label>
          <button class="dv-btn" data-menu="layout" aria-haspopup="dialog">Layout</button>
          <button class="dv-btn" data-menu="group" aria-haspopup="dialog">Group</button>
          <button class="dv-btn" data-menu="rollup" aria-haspopup="dialog" hidden>Roll up</button>
          <button class="dv-btn" data-menu="sort" aria-haspopup="dialog">Sort</button>
          <button class="dv-btn" data-menu="filter" aria-haspopup="dialog">Filter</button>
          <button class="dv-btn" data-menu="properties" aria-haspopup="dialog">Properties</button>
          <button class="dv-btn dv-units" hidden aria-pressed="false">Units</button>
          <span class="dv-dirty" hidden><button class="dv-btn dv-reset">Reset</button><button class="dv-btn dv-primary" data-menu="save" aria-haspopup="dialog">Save view</button></span>
          ${this._hasSwitch() ? '<button type="button" class="dv-btn dv-editsw" data-edit-switch role="switch" aria-checked="false" aria-label="Edit" title="Edit: change the data here. View: read only."><span class="dv-switch" aria-hidden="true"></span><span class="dv-bar-label">Edit</span></button>' : ''}
          <button class="dv-btn dv-more" data-menu="more" aria-haspopup="dialog" aria-label="More">⋯</button>
        </div>
      </div>
      <section class="dv-intro" hidden aria-label="About this view"><div class="dv-intro-kpi"></div><div class="dv-intro-text dv-md"></div></section>
      <div class="dv-status" aria-live="polite"></div>
      <div class="dv-notice" role="note" hidden></div>
      ${bar ? '<div class="dv-bulk" hidden></div>' : ''}<div class="dv-stage"></div>
      <div class="dv-pop" role="dialog" hidden></div>
      <aside class="dv-peek" hidden aria-label="Details"></aside>`;
    this.$ = (sel) => this.querySelector(sel);
    if (served && served.some((n) => n.nodeType === 1 || (n.nodeType === 3 && n.textContent.trim()))) {
      const hold = document.createElement('div');
      hold.className = 'dv-served';
      hold.append(...served);
      const stage = this.$('.dv-stage');
      stage.append(hold);
      stage.setAttribute('aria-busy', 'true');
    }
    mark('data-ui:start', { id: this.id || null });
    if (this._queryUi) this._queryUi.destroy();
    if (this._bulkUi) this._bulkUi.destroy();
    if (this._barUi) this._barUi.destroy();
    if (this._expandUi) this._expandUi.destroy();
    if (this._settingsUi) this._settingsUi.destroy();
    this._queryUi = bar ? mountQuery(this, this.$('.dv-bar-query'), { tokens: this._filterModes().includes('query-tokens') }) : null;
    this._bulkUi = bar ? mountBulk(this, this.$('.dv-bulk')) : null;
    this._barUi = bar ? mountBar(this) : null;
    // search="expand" (CONTRACT §43): Shopify's Search and filter, its Cancel and facet chips
    this._expandUi = bar ? mountExpand(this) : null;
    this._settingsUi = bar ? mountSettings(this) : null;
    this._wire();
    mountNotes(this);
    // WHY: Zach always wants resizable, remembered side panels (memory feedback_resizable_panels); the peek and this
    // element's rails get a drag handle unless data-resizable="off" (src/resize.js)
    this._resizers = resizeKit(this);
    const fromUrl = this._readUrl();
    if (fromUrl && fromUrl.filters !== undefined) this._filters = fromUrl.filters;
    if (fromUrl) this._hidden = fromUrl.hidden;
    const users = this._userViews();
    // CONTRACT §37: the viewer's own (persist="local" or "page"), then the element's `view`, then the file's defaultView
    const kept = this._localState();
    if (fromUrl === null || fromUrl.filters === undefined) { const f = this._localFilters(kept); if (f !== undefined) this._filters = f; }
    const want = (fromUrl && fromUrl.name) || (keep && slug(keep)) || (kept && kept.selected && slug(kept.selected)) || (this.getAttribute('view') && slug(this.getAttribute('view'))) || (this._base.defaultView && slug(this._base.defaultView));
    const named = want && [...this.presets.map((v) => ['preset', v]), ...users.map((v) => ['user', v])].find(([kind, v]) => this._slugOf(kind, v.name) === want);
    const [kind, start] = named || ['preset', this.presets[0] || { type: 'table', name: 'Table', order: Object.keys(this._data.properties).filter((id) => !this._data.properties[id].of) }];
    if (fromUrl && fromUrl.query) this.query = fromUrl.query;
    else if (this.getAttribute('query') && !this._queryRead) { this._queryRead = true; const q = parseQuery(this.getAttribute('query'), labelled(this._data, this._base)); if (q.clauses.length) { this._filters = { and: q.clauses }; this._filtersSet = true; } this.query = q.words; }
    let changed = named && fromUrl && fromUrl.view;
    // #group=<id> picks one of the view's groupings (docs/CONTRACT.md §20); an id the view does not have is ignored
    const group = fromUrl && fromUrl.group;
    const into = changed || start;
    if (group && Array.isArray(into.groupings) && into.groupings.some((g) => g && g.id === group)) changed = { ...into, grouping: group };
    // CONTRACT §34: a view's hiddenSeries is its legend's hidden set when the element first opens and nothing named one
    // (no l= in the URL, none set by the host; a <data-dashboard> sets its panels' itself)
    if (!this._hiddenSeeded) {
      this._hiddenSeeded = true;
      const opening = changed || start;
      if (!this._hiddenGiven && !(fromUrl && fromUrl.hidden && fromUrl.hidden.length) && Array.isArray(opening && opening.hiddenSeries)) this._hidden = opening.hiddenSeries.map(String);
    }
    // a `toolbar` switch rebuilt the chrome: the open view stays exactly as it was, unsaved changes too (no-url pages
    // have no hash to carry them)
    // the frame first, so a toolbar switch (the kept-view return below) is framed too (src/frame.js)
    this._applyFrame();
    const held = this._keepView;
    this._keepView = null;
    if (held && held.origin) { this._select(held.origin.kind, held.origin.view, held.view); return; }
    // WHY paint first on big data: building 100,000 rows' model takes most of a second, in the same task as the
    // toolbar, so nothing at all reached the screen until it was done. On a big dataset the toolbar (and a host's own
    // rows, kept above) paint first, with the row count, and the model is built right after; small data stays one
    // task, since a frame would cost more than it buys (perf review 2026-10-26, item 6)
    const big = (this._data.rows || []).length >= PAINT_FIRST_ROWS;
    this._select(kind, start, changed, { afterPaint: big });
  }

  /** filters="pills expanded query-tokens rail" (§15), as a list; default pills. */
  _filterModes() {
    // §15: with no `filters` attribute the default follows the views (bar.js): tabs => pills, the chip => expanded
    if (this._barUi) return this._barUi.filterModes();
    return (this.getAttribute('filters') || 'pills').split(/\s+/).filter(Boolean);
  }

  // ------------------------------------------------------------------ §15: views, query and selection by script
  /** Open a preset or a user view by name; true if one has that name. */
  selectView(name) {
    const user = this._userViews().find((v) => v.name === name);
    const preset = this.presets.find((v) => v.name === name);
    if (preset) { this._select('preset', preset); return true; }
    if (user) { this._select('user', user); return true; }
    return false;
  }

  /** Save a new view entry as a user view and open it; returns its name ("<Type> N" when it has none). */
  addView(view = {}) {
    const type = view.type || 'table';
    const plugin = viewPlugin(type);
    const typeName = (plugin && plugin.name) || type;
    const taken = new Set([...this.presets, ...this._userViews()].map((v) => v.name));
    let name = view.name;
    for (let n = 1; !name || taken.has(name); n++) name = `${typeName} ${n}`;
    this._saveUser(name, { order: clone(this.view && this.view.order), ...clone(view), type, name });
    return name;
  }

  /** Save the current view as a user view (default: the open user view, else "<name> (mine)"). */
  saveView(name) {
    const n = name || (this.origin.kind === 'user' ? this.origin.name : `${this.origin.name} (mine)`);
    this._saveUser(n, this.view);
    return n;
  }

  /** The free-text words of the query (the old search box). */
  search(words) { this.query = String(words || '').trim(); this._render(); }

  /** The whole query: its clauses become the all-views filter, the rest is the search words. */
  setQuery(text) {
    const q = parseQuery(text, this._model ? this._model.columns : labelled(this._data, this._base));
    this._filtersSet = true;
    this._filters = q.clauses.length ? { and: q.clauses } : undefined;
    this.query = q.words;
    this._queryErrors = q.errors;
    this._render();
    return q;
  }

  /** The canonical query text of the current state (the filter's clauses as tokens, then the words). */
  get queryText() { return formatQuery(this._filters, this.query, this._model ? this._model.columns : labelled(this._data, this._base)); }

  get selection() {
    const order = this._model ? this._model.rows.map((r) => String(r.id)) : [];
    const ids = this._selection.ids;
    return [...order.filter((id) => ids.has(id)), ...[...ids].filter((id) => !order.includes(id))];
  }
  get selectedRows() { return this.selection.map((id) => this.row(id)).filter(Boolean); }
  select(ids, { mode = 'replace' } = {}) { this._selection.set(ids, mode); this._selectionChanged(); }
  selectAll() { this._selection.set(this._model.rows.map((r) => String(r.id)), 'replace'); this._selectionChanged(); }
  clearSelection() { if (!this._selection.ids.size) return; this._selection.clear(); this._selectionChanged(); }

  /** CONTRACT §39: the ids of the rows a host has picked (a <data-dashboard> panel's picks), which a view marks beside the
      selection through selected(set) and input.selected. WHY not el.select(): a panel's pick is the dashboard's, so it
      must draw no bulk bar with a Clear that cannot clear it, fire no data-views-select, narrow nothing, and redraw no view
      that has no selected(set). */
  get picked() { return [...this._picked]; }
  set picked(ids) {
    const next = new Set([...(ids || [])].map(String));
    if (next.size === this._picked.size && [...next].every((id) => this._picked.has(id))) return;
    this._picked = next;
    if (this._plugin && typeof this._plugin.selected === 'function') this._plugin.selected(this._marks());
  }
  /** What a view marks: the selection and the host's picks. */
  _marks() { return new Set([...this._selection.ids, ...this._picked]); }

  set actions(list) { this._actions = list || null; if (this._bulkUi) this._bulkUi.update(); }
  get actions() { return this._actions; }

  /** After any selection change: tell the page, redraw the bulk bar, and let the view repaint its marks. */
  _selectionChanged() {
    const bulk = this.$ && this.$('.dv-bulk');
    if (bulk) bulk.hidden = !this._selection.ids.size;
    if (this._bulkUi) this._bulkUi.update();
    // §15 note 2026-10-26: the bulk band lies over the view's header row (bar.js); the pill row stays under the bar
    if (this._barUi) this._barUi.placeBulk();
    if (this._plugin) {
      if (typeof this._plugin.selected === 'function') this._plugin.selected(this._marks());
      else if (this._model) this._plugin.update(this._input());
    }
    this.dispatchEvent(new CustomEvent('data-views-select', { detail: { ids: this.selection, rows: this.selectedRows } }));
  }

  /** frame="…" (src/frame.js): wire the page's scroller for page|bleed before a view is made, since a view's
      virtualizer reads host.scroller once, when it is constructed. */
  _applyFrame() {
    if (this._unframe) this._unframe();
    this._scroller = pageScrolls(this) ? scrollParent(this) : null;
    this._unframe = mountFrame(this);
  }

  /** The frame changed on a live element: re-make the view on the new scroller, keeping the view and its state. */
  _reframe() {
    if (this._plugin) { try { this._plugin.destroy(); } catch { /* the old view's cleanup must not block the new frame */ } }
    this._plugin = null;
    this._pluginType = null;
    this._applyFrame();
    this._render();
  }

  _select(kind, view, changed, { afterPaint = false, fresh = false } = {}) {
    // WHY first: a change a moment old belongs to the view being left, and origin is about to be another's
    if (this.origin && this._persistTimer) this._flushPersist();
    this.origin = { kind, name: view.name, view: this._columns(clone(view)) };
    // CONTRACT §37: a view this viewer changed comes back as they left it, unless the file changed that view since; Reset
    // (`fresh`) forgets it
    if (fresh) this._forgetLocal(view.name);
    this.view = this._columns(clone(changed || (fresh ? null : this._localView(view)) || view));
    this._status = '';
    this._precNote = null;
    this.closePeek();
    if (!afterPaint) { this._render(); return; }
    const n = (this._data.rows || []).length;
    this.$('.dv-status').innerHTML = `<span class="dv-count">Loading ${n.toLocaleString()} rows…</span>`;
    const id = this._renderId;
    // a frame, then a task: the toolbar has been painted; a render that happened meanwhile (a click) wins
    requestAnimationFrame(() => setTimeout(() => { if (this._started && id === this._renderId) this._render(); }, 0));
  }

  /** A view of this data with its columns said (CONTRACT §36, precedence.js ownColumns). */
  _columns(view) {
    if (this._precInfo && !this._prec) this._prec = this._readPrec();
    return ownColumns(view, this._unfolded || this._raw, this._precInfo, this._prec && this._prec.order);
  }

  /** New data has its own sources: the open view's columns are said again, from the view the file has (a reader's changes stay). */
  _columnsAgain() {
    if (!this.origin) return;
    const file = this.presets.find((v) => v.name === this.origin.name);
    if (this.origin.kind === 'preset' && !file) { this._select('preset', this.presets[0] || this.origin.view); return; }
    const was = this.dirty;
    const now = this._columns(clone(file || this.origin.view));
    this.origin = { ...this.origin, view: now };
    this.view = was ? this._columns(this.view) : clone(now);
  }

  /** Apply a change to the current view and redraw (every menu goes through here). */
  update(change) {
    this._precNote = null;
    const was = this.view;
    const next = clone(was);
    change(next);
    for (const k of Object.keys(next)) if (next[k] === null || next[k] === undefined) delete next[k];
    this._regrouped(was, next);
    this.view = next;
    this._columnsMoved(was, next);
    this._render();
  }

  /** CONTRACT §36: what a change of a view's columns means for what they roll up. WHY here, the one way a view changes: Zach, 2026-10-31,
      "its just like a column roll up where the left most take precencde": the drag is the ordinary one, from the header or Property
      visibility or a script, and the precedence follows it. A hide or a show moves nothing. */
  _columnsMoved(was, next) {
    const cols = this._unfolded && this._unfolded.properties;
    if (!cols || this._unfolded === this._raw) return;
    // a "<label> source" column hidden stays hidden: its view says so, and a kept view or a saved file carries it
    const ofSource = (v) => (v.order || []).filter((id) => cols[id] && cols[id].display === 'source');
    if (ofSource(was).some((id) => !ofSource(next).includes(id))) next.sourceColumn = false;
    else if (ofSource(next).length) delete next.sourceColumn;
    const info = this._precInfo;
    if (!info) return;
    if (!this._prec) this._prec = this._readPrec();
    const order = orderAfter(was.order, next.order, info, this._prec.order);
    if (order !== this._prec.order) this._applyPrec({ ...this._prec }, { order, ov: this._prec.ov }, { draw: false });
    if (Array.isArray(next.order)) next.order = placeShown(was.order, next.order, info, this._prec.order);
    this._slot(next);
  }

  /** A switch of `grouping` (docs/CONTRACT.md §20) clears a nav pick on the previous grouping's property, as McMaster
      resets its category page, unless the view says `keepFilter: true`. Only in a file whose rail has a nav facet. */
  _regrouped(was, next) {
    if (!was || next.keepFilter || (G.groupingOf(was) || {}).id === (G.groupingOf(next) || {}).id) return;
    const before = G.effectiveView(was).groupBy, after = G.effectiveView(next).groupBy;
    if (!before || (after && after.property === before.property)) return;
    const props = labelled(this._data, this._base);
    if (!allSpecs(this._base, props).some((s) => s.as === 'nav')) return;
    this._filters = this._facetFilters(before.property, null);
  }

  /** host.setFacet(property, facet | null): set (or clear) one property's facet-shaped part of the all-views filter,
      read and written through facets.js' toRail / fromRail as <data-facets> does; every other clause stays. The rail,
      the URL's search params and every view follow. `facet` is the rail's state of one property: {values, match},
      {min, max, minOpen, maxOpen}, {exclude}, {has}, {text}. Returns the new filter. */
  setFacet(property, facet) {
    if (typeof property !== 'string' || !property) throw new Error('setFacet(property, facet | null): property names a property');
    if (facet !== null && facet !== undefined && (typeof facet !== 'object' || Array.isArray(facet))) throw new Error('setFacet: facet is one property\'s rail state ({values, match}, {min, max, maxOpen}, …) or null');
    this.filters = this._facetFilters(property, facet || null);
    return clone(this._filters);
  }

  _facetFilters(property, facet) {
    // WHY a rail that can draw any facet of any property: a host's seam must replace a pick it made before (and one the
    // page's rail made), not stack a second clause beside it; anything not facet-shaped stays verbatim
    const props = labelled(this._data, this._base);
    const every = railConfig(Object.keys(props).flatMap((p) => [{ property: p, as: 'values', exclude: true }, { property: p, as: 'range' }, { as: 'has', properties: [p] }]));
    const rail = toRail(this._filters, every);
    if (facet && Object.keys(facet).length) rail.facets[property] = clone(facet);
    else delete rail.facets[property];
    return fromRail(rail.facets, rail.rest);
  }

  /** host.setView(patch): merge keys into this view's entry; a null or undefined value removes the key. */
  setView(patch) {
    if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('setView(patch): patch is an object of view keys');
    for (const k of ['data', 'datasets']) if (k in patch) throw new Error(`setView: a view cannot set '${k}'`);
    this.update((x) => { for (const [k, v] of Object.entries(patch)) x[k] = clone(v); });
    return clone(this.view);
  }

  /** A column-menu edit to the .base file's properties (CONTRACT §28), through el.editProperty({action}): {action: 'set', id,
      patch} | {action: 'insert', at, side, type} | {action: 'duplicate', id} | {action: 'delete', id}. It lands on el.base
      (every view redraws with it), on el.baseText (so ⋯ Copy the whole file carries it) and in a data-views-base event
      for a host that saves the file. Refused (throws) on a read-only element. Returns the id it touched or made. */
  _editBaseProperty(edit) {
    const r = applyProperty(this, edit);
    const orderChanged = edit.action !== 'set';
    const index = this.origin && this.origin.kind === 'preset' ? this._base.views.findIndex((v) => v.name === this.origin.name) : -1;
    // WHY the text first, and nothing caught (judge r2 #1, #3): the file's text is written, with the view's new order
    // when the view is one of the file's, and checked whole before anything changes; an edit it cannot place throws
    // here and leaves the element, the file and the view exactly as they were
    const text = this.baseText ? fileEdit(this.baseText, r.changes, orderChanged && index >= 0 ? { viewIndex: index, order: r.order } : {}) : null;
    const views = orderChanged && index >= 0 ? this._base.views.map((v, i) => (i === index ? { ...v, order: [...r.order] } : v)) : this._base.views;
    this._base = { ...this._base, properties: r.properties, views };
    if (text !== null) this.baseText = text;
    if (orderChanged && index >= 0) this.origin = { ...this.origin, view: { ...this.origin.view, order: [...r.order] } };
    if (!orderChanged) this._render();
    else this.update((x) => { x.order = r.order; });
    this.dispatchEvent(new CustomEvent('data-views-base', { detail: { action: edit.action, id: r.id, patch: edit.patch || null, properties: clone(r.properties), order: orderChanged ? [...r.order] : null, text } }));
    return r.id;
  }

  get dirty() { return G.viewKey(this.view) !== G.viewKey(this.origin.view); }

  // ------------------------------------------------------------------ keeping view changes (docs/CONTRACT.md §37)
  /* WHY in the element, once, not per host: width, order, sort, grouping, filters and the open view are one state, and a
     host without the URL (no-url: its hash is its router) lost them on reload. Three paths, any together: the URL (as
     before), this viewer's storage (persist="local"), and the page's hook, which gets the .base file's new text, so a
     file host keeps one plain file every viewer and agent shares. */
  _persists() { return this._keeps() || typeof this.persistView === 'function'; }
  /** persist="local": one state per data id. persist="page": per page and data id, the widths per data id. WHY a second word (robotparts: 2,103
      part pages, one data id): a preset chosen on one page opened the next on 0 of its 16 rows, while a column dragged wider is wanted on
      every page. The scope the precedence already has. */
  _keeps() { const p = this.getAttribute('persist'); return p === 'local' || p === 'page'; }
  _perPage() { return this.getAttribute('persist') === 'page'; }
  _dataKey() { return `data-views/${(this._data && this._data.id) || 'data'}`; }
  _stateKey() { return this._perPage() ? `data-views/${typeof location !== 'undefined' ? location.pathname : ''}/${(this._data && this._data.id) || 'data'}/state` : `${this._dataKey()}/state`; }
  _widthsKey() { return `${this._dataKey()}/widths`; }
  _localState() { return this._keeps() ? store.get(this._stateKey()) : null; }
  _localView(view) {
    const s = this._localState();
    const held = s && s.views && s.views[view.name];
    // WHY both: a view is kept against the entry as the page opened it, its columns said (§36); a state from before that names the bare entry
    const kept = held && [G.viewKey(view), G.viewKey(this._columns(clone(view)))].includes(held.from) ? held.view : null;
    const sized = this._perPage() ? (store.get(this._widthsKey()) || {})[view.name] : null;
    return sized ? { ...(kept || view), columnSize: sized } : kept;
  }
  _localFilters(s) {
    const held = s && s.filters;
    return held && held.from === JSON.stringify(this._base.filters ?? null) ? held.value ?? undefined : undefined;
  }
  _forgetLocal(name) {
    const s = this._localState();
    if (s && s.views && s.views[name]) { delete s.views[name]; store.set(this._stateKey(), s); }
    const sized = this._perPage() ? store.get(this._widthsKey()) : null;
    if (sized && sized[name]) { delete sized[name]; store.set(this._widthsKey(), sized); }
  }
  _persistKey() { return JSON.stringify([this.origin.kind, this.origin.name, this.view, this._filters ?? null, this._propsRev || 0, this._prec && this._prec.order]); }

  /** After a draw: anything to keep? The first draw over a file is the baseline, so opening a page writes nothing. */
  _persistChange() {
    if (!this._persists() || !this.origin) return;
    const key = this._persistKey();
    if (this._persistBase !== this._base || this._persisted === undefined) { this._persistBase = this._base; this._persisted = key; return; }
    if (key === this._persisted) return;
    clearTimeout(this._persistTimer);
    // WHY a short wait: a drag ends in one change, but the keys of a menu and a filter come in runs; one write per run
    this._persistTimer = setTimeout(() => this._flushPersist(), 200);
  }

  _flushPersist() {
    clearTimeout(this._persistTimer);
    this._persistTimer = 0;
    if (!this._persists() || !this.origin || !this._base) return;
    const key = this._persistKey();
    if (key === this._persisted) return;
    this._persisted = key;
    const { kind, name, view: origin } = this.origin;
    const view = clone(this.view);
    const filters = clone(this._filters);
    if (this._keeps()) {
      const s = store.get(this._stateKey()) || {};
      s.selected = name;
      s.views = s.views || {};
      s.views[name] = { from: G.viewKey(origin), view };
      s.filters = { from: JSON.stringify(this._base.filters ?? null), value: filters ?? null };
      store.set(this._stateKey(), s);
      if (this._perPage()) {
        const sized = store.get(this._widthsKey()) || {};
        if (view.columnSize) sized[name] = view.columnSize; else delete sized[name];
        store.set(this._widthsKey(), sized);
      }
    }
    if (typeof this.persistView === 'function') this._persistToHost(kind, name, view, filters);
  }

  /** The hook: the file's new text, each preset the view touched, the picked view, the all-views filter. Only what changed
      is rewritten; the rest of the text stays as written, comments and all. */
  async _persistToHost(kind, name, view, filters) {
    const presets = this._base.views;
    let text = typeof this.baseText === 'string' ? this.baseText : stringifyBase({ ...this._base });
    const at = kind === 'preset' ? presets.findIndex((v) => v.name === name) : -1;
    const write = (i, next) => { text = replaceViewInText(text, i, next); presets[i] = clone(next); };
    const propsWere = this._propsWritten || 0;
    try {
      // CONTRACT §40: a column's display name is the file's, and it travels with the rest of the change
      if (propsWere !== (this._propsRev || 0)) {
        const named = this._base.properties;
        text = replaceKeyInText(text, 'properties', named && Object.keys(named).length ? named : null);
        this._propsWritten = this._propsRev;
      }
      if (at >= 0 && G.viewKey(presets[at]) !== G.viewKey(view)) {
        write(at, view);
        // CONTRACT §37 sharedColumns: one sheet's columns in every table view of the file
        if (this._base.sharedColumns && (view.type || 'table') === 'table') {
          presets.forEach((v, i) => {
            if (i === at || (v.type || 'table') !== 'table') return;
            const next = { ...v };
            for (const k of ['order', 'columnSize']) { if (view[k] === undefined) delete next[k]; else next[k] = clone(view[k]); }
            if (G.viewKey(next) !== G.viewKey(v)) write(i, next);
          });
        }
        this.origin = { ...this.origin, view: clone(view) };
      }
      text = this._formulasInText(text);
      const first = presets[0] && presets[0].name;
      const pick = at >= 0 && name !== first ? name : null;
      if ((this._base.defaultView ?? null) !== pick) { text = replaceKeyInText(text, 'defaultView', pick); if (pick) this._base.defaultView = pick; else delete this._base.defaultView; }
      if (JSON.stringify(this._base.filters ?? null) !== JSON.stringify(filters ?? null)) { text = replaceKeyInText(text, 'filters', filters ?? null); if (filters === undefined) delete this._base.filters; else this._base.filters = clone(filters); }
    } catch (err) {
      // a file this reader cannot edit in place (a hand edit in progress): the page keeps the change and says so
      this._persistNote = `not saved: ${err.message}`;
      this._drawStatus();
      return;
    }
    if (text === this.baseText) return;
    const before = this.baseText;
    this.baseText = text;
    let answer;
    try { answer = await this.persistView({ text, name, kind, view, selected: name, filters: filters ?? null }); } catch (err) { answer = { ok: false, reason: err.message }; }
    if (!(answer && answer.ok)) {
      this.baseText = before;
      this._propsWritten = propsWere;
      this._persistNote = `not saved: ${(answer && answer.reason) || 'the host refused it'}`;
    } else { this._persistNote = ''; this._formulasKept(); }
    this._drawStatus();
    this._drawBar();
    this.dispatchEvent(new CustomEvent('data-views-persist', { detail: { name, text, result: answer } }));
  }

  /** The file's text with its formulas in the reader's order. WHY: Survey §13, "Dragging a header in Sources would rewrite the list inside
      `nominal`, so precedence stays visible text": the rest of the file stays as written, comments and all. A value with no formula in
      the file gains one; each only when its order moved. */
  _formulasInText(text) {
    const info = this._precInfo, order = this._prec && this._prec.order;
    this._formulasNew = null;
    if (!info || !order || order.join('\u0000') === info.default.join('\u0000')) return text;
    const all = { ...(this._base.formulas || {}) };
    let out = text, added = false;
    for (const id of info.properties) {
      const f = info.formulas[id];
      const was = f ? f.text : null;
      const now = formulaText(info, id, order);
      if (was === now) continue;
      all[f ? f.name : id] = now;
      if (was !== null && out.includes(was)) out = out.split(was).join(now); else added = true;
    }
    if (added) out = replaceKeyInText(out, 'formulas', all);
    this._formulasNew = all;
    return out;
  }

  /** The host took the file: its text is what holds the order now, so nothing is left for this viewer to keep. */
  _formulasKept() {
    if (!this._formulasNew) return;
    this._base = { ...this._base, formulas: this._formulasNew };
    this._formulasNew = null;
    const kept = this._prec;
    this._unfold();
    this._prec = kept;
    try { if (kept.order.join('\u0000') === this._precInfo.default.join('\u0000') && !Object.keys(kept.ov).length) localStorage.removeItem(this._precKey()); } catch { /* private window */ }
    this._drawStatus();
  }

  /** Draw the open record's peek again, new data and all; not while something in it is being written. */
  refreshPeek() {
    if (!this._peek || !this.row(this._peek.id)) return;
    const a = document.activeElement;
    if (a && this.$('.dv-peek').contains(a) && a.matches('input, textarea, select, [contenteditable]')) return;
    this.openPeek(this._peek.id, this._peek.opts);
  }

  /** §46: the host's page, one element kept across the panel's redraws so its editor keeps its place; a new one per record. */
  _holdPage(peek, row, id) {
    const slot = peek.querySelector('[data-page-host]');
    if (!slot) return;
    const held = this._pageHeld;
    if (held && held.id === id) {
      slot.replaceWith(held.el);
      if (held.handle && held.handle.update) held.handle.update(row);
      return;
    }
    this._dropPage();
    const el = document.createElement('div');
    el.className = 'dv-page-host';
    slot.replaceWith(el);
    this._pageHeld = { id, el, handle: this.pageRenderer(el, { row, id, close: () => this.closePeek() }) || null };
  }
  _dropPage() {
    const held = this._pageHeld;
    this._pageHeld = null;
    if (held && held.handle && held.handle.destroy) held.handle.destroy();
    if (held) held.el.remove();
  }

  /** The row behind an id. */
  row(id) {
    if (!this._byId) this._byId = new Map(this._data.rows.map((r) => [String(r.id), r]));
    return this._byId.get(String(id)) || null;
  }

  // ------------------------------------------------------------------ data edits (host.propose)
  async propose(given) {
    const edit = this._folded(given);
    const was = this._session.before(edit);
    // §40: before the edit draws, so the row never leaves
    if (was) this._keepRows([edit.id]);
    const result = await this._decide(edit || {});
    this._told(edit, result);
    if (result && result.ok) this._session.edited(edit, was);
    return result;
  }

  /** An edit of source columns, as the stored property (CONTRACT §36): WHY here, before anything records it: a host, the undo stack and
      the event all see the cell the row holds. */
  _folded(edit) {
    const row = edit && edit.set ? this._rawRow(edit.id) : null;
    const set = row ? foldEdit(edit.set, row, this._precInfo) : edit && edit.set;
    return row && set !== edit.set ? { ...edit, set } : edit;
  }

  /** Tell the page what became of an edit. */
  _told(edit, result) {
    this.dispatchEvent(new CustomEvent('data-views-propose', { detail: { ...edit, row: edit && this.row(edit.id), result } }));
  }

  /** `quiet`: the caller draws once when its run of edits is done (§40). */
  async _decide({ id, set: asked }, { quiet = false } = {}) {
    const refused = this._refuseEdit({ id, set: asked });
    if (refused) return { ok: false, reason: refused };
    const row = this.row(id);
    // §46: a cell an H1 column drew is the one property that holds the note: that is what the host is told, and what lands
    const { set, cells } = liftH1(asked, this._raw && this._raw.properties, row);
    // CONTRACT §36: the row as loaded takes the edit (the shown row is its resolved copy when a cell has several sources)
    const target = this._data === this._raw ? row : this._rawRow(id) || row;
    if (typeof this.acceptEdit === 'function') {
      const answer = await this.acceptEdit({ id, set, row: target });
      if (answer && answer.ok) { Object.assign(target, cells); this._resolveAgain(set); this._revise(); this._editWorker(target); if (!quiet) this._render(); }
      return answer || { ok: false, reason: 'The host refused the edit.' };
    }
    if (!this.editing) return { ok: false, reason: 'This page is read-only: the data changes at its source.' };
    Object.assign(target, clone(set), cells);
    this._resolveAgain(set);
    this._revise();
    this._editWorker(target);
    if (!quiet) this._render();
    return { ok: true };
  }

  /** Why an edit cannot even be asked, before any hook hears of it; null when it can. */
  _refuseEdit({ id, set }) {
    if (!this.row(id)) return `No row has the id ${id}.`;
    if (!set || typeof set !== 'object') return 'An edit is {id, set: {property: value}}.';
    if (this._viewOnly()) return VIEW_REFUSES;
    const props = labelled(this._data, this._base);
    for (const p of Object.keys(set)) {
      const meta = props[p];
      if (!meta) return `${p} is not a property of this data.`;
      if (meta.derived || meta.readOnly) return `${meta.label} is ${meta.derived ? `derived (${meta.derived})` : 'read-only'}, so no view may set it.`;
      // WHY refused, here, before any hook: the cell is a formula over its sources' columns, so a value set beside them resolves straight
      // back, and a host would save an edit the reader never sees. A new list of sources is no such edit: an edit of a source's own
      // column arrives as one (_folded), and undo puts one back
      if (this.isSourced(id, p) && !isMultiSource(set[p])) return `${meta.label} comes from its sources. Pick a source from its menu, or edit a source.`;
    }
    return null;
  }

  /** Whether a cell's value comes from its sources (CONTRACT §36): read from the row as loaded, because the shown row holds its nominal. */
  isSourced(id, property) {
    if (!this._precInfo) return false; // no cell of this data has sources: nearly every dataset
    const row = this._rawRow(id);
    return !!row && isMultiSource(row[property]);
  }

  /** After an edit of a row as loaded: the columns and the shown rows again, when anything rolls up (or now does). */
  _resolveAgain(set) {
    if (!this._raw || (this._unfolded === this._raw && !Object.values(set || {}).some(isMultiSource))) return;
    this._unfold();
    if (this._prec) this._prec = { ...this._prec, order: normalizeOrder(this._prec.order, this._precInfo ? this._precInfo.ids : [], this._precInfo ? this._precInfo.default : []) };
    this._data = this._shown();
    this._byId = null;
  }

  // ------------------------------------------------------------------ the add row and a media cell's files (CONTRACT §37)
  /** File a new row: the page's acceptAdd hook decides; an `editable` page with no hook keeps it in memory; else it refuses. */
  async addRow(given) {
    // §40: drawn once it is kept, so a row added under a filter it does not match stays; every other page draws as §37 says
    const quiet = this._editTools() && typeof this.acceptAdd !== 'function';
    const set = foldEdit(given, {}, this._precInfo);
    const result = await this._fileRow(set, { quiet });
    if (result.ok) this._session.added(set, result.id);
    if (quiet && result.ok) this._render();
    return result;
  }

  /** `at: 'end'` (a pasted block, CONTRACT §40) goes after the last row, not above the first; `quiet`: the caller draws once. */
  async _fileRow(set, { at = null, quiet = false } = {}) {
    if (!set || typeof set !== 'object') return { ok: false, reason: 'A new row is an object of properties.' };
    if (this._viewOnly()) return { ok: false, reason: VIEW_REFUSES };
    const props = labelled(this._data, this._base);
    for (const p of Object.keys(set)) {
      const meta = props[p];
      if (!meta) return { ok: false, reason: `${p} is not a property of this data.` };
      const locked = lockedBecause(meta);
      if (locked) return { ok: false, reason: `${meta.label} is ${locked}, so no view may set it.` };
    }
    let result;
    if (typeof this.acceptAdd === 'function') {
      result = (await this.acceptAdd(at ? { set: clone(set), at } : { set: clone(set) })) || { ok: false, reason: 'The host refused the row.' };
    } else if (this.editing) {
      const row = { ...clone(set), id: `new-${Date.now().toString(36)}-${(this._added = (this._added || 0) + 1)}` };
      const rows = (this._raw || this._data).rows;
      if (at === 'end') rows.push(row); else rows.unshift(row);
      if (this._data !== this._raw && this._raw) this._data = this._shown();
      this._byId = null;
      this._dropWorker();
      this._revise();
      if (!quiet) this._render();
      result = { ok: true, id: row.id };
    } else result = { ok: false, reason: 'This page is read-only: the data changes at its source.' };
    this.dispatchEvent(new CustomEvent('data-views-add', { detail: { set, result } }));
    return result;
  }

  /** CONTRACT §40: delete rows. The page's acceptDelete hook decides; an editable page with no hook deletes in memory. */
  deleteRows(ids) { return this._session.deleteRows(ids); }
  /** CONTRACT §40: edits, new rows and deletes as one step: one call to acceptBatch when the page has it, else each through its own hook. */
  batch(plan, opts) { return this._session.batch(plan, opts); }
  /** CONTRACT §40: a column's add, rename, retype, hide or delete. */
  /** A property edit. WHY one name for two: {op, property, …} (§40) changes the data's columns, through el.acceptProperty;
      {action, id, …} (§28) changes the .base file's `properties:`. Both are what the reader calls editing a column, and a
      caller says which by its verb, so neither shadows the other. */
  editProperty(edit) { return edit && edit.action ? this._editBaseProperty(edit) : this._session.editProperty(edit); }
  /** CONTRACT §40: this session's edits, adds, deletes and pastes, back and forth, through the same hooks with the old values. */
  undo() { return this._session.undo(); }
  redo() { return this._session.redo(); }
  get canUndo() { return this._session.canUndo; }
  get canRedo() { return this._session.canRedo; }

  /** Store one file for a media cell through the page's acceptFile hook; data-ui keeps no bytes. `where`: {id, property}. */
  async attachFile(file, { id = null, property = null } = {}) {
    if (typeof this.acceptFile !== 'function') return { ok: false, reason: 'This page takes no files.' };
    let answer;
    try { answer = await this.acceptFile({ file, id, property }); } catch (err) { answer = { ok: false, reason: err.message }; }
    return answer || { ok: false, reason: 'The host refused the file.' };
  }

  /** A thumbnail opens large: the page's own viewer if it takes data-views-media (preventDefault), else the kit's. */
  showMedia(list, index = 0) {
    const go = this.dispatchEvent(new CustomEvent('data-views-media', { detail: { list, index }, cancelable: true }));
    if (go) openMediaBox(this, list.map((a) => ({ ...a, url: mediaUrl(a.url, { url: this.dataUrl }) })), index);
  }

  // ------------------------------------------------------------------ the row-model worker (rowmodel-worker.js)
  /* WHY a worker at WORKER_ROWS and up: a model over 100,000 rows held the main thread for 0.6-1 s per sort, filter or
     search key, so the page froze with it. The worker computes the model's order while the previous rows stay on
     screen (stale-while-revalidate, _render); the main thread only rebuilds the table from that order. It holds its
     own copy of the rows: the bytes the page fetched (parsed there), or the rows cloned over in slices. */
  _ensureWorker() {
    if (this._rm || !this.isConnected || !this._started || typeof Worker === 'undefined') return;
    // WHY not for multi-source data (CONTRACT §36): the worker holds the rows as loaded (it parses the file itself), not
    // their nominals under this reader's precedence; such a dataset is a datasheet's dozens of rows, built here at once
    if (this._precInfo) return;
    const d = this._data;
    if (!d || !d.rows || d.rows.length < WORKER_ROWS) return;
    const seed = this._seed && this._seed.data === d && this._seed.rev === this._rev ? this._seed : null;
    this._seed = null; // the response text is as big as the file: let it go once the worker has it
    try {
      this._rm = createRowModelWorker(d, seed ? { url: seed.url, bodies: seed.bodies, rev: this._rev } : { rev: this._rev, slice: WORKER_SLICE });
    } catch { this._rm = null; /* a dataset that cannot be cloned (a host's functions in it): synchronous, as before */ }
  }

  _dropWorker() {
    if (this._rm) { try { this._rm.terminate(); } catch { /* already gone */ } }
    this._rm = null;
    this._pending = null;
    this._unbusy();
  }

  /** An edit changed `row` in place: the worker's copy gets the new row, so its next answer has it (messages keep
      their order); a row it cannot place (a host replaced it) retires the worker, and the models go synchronous. */
  _editWorker(row) {
    if (!this._rm) return;
    const i = this._data ? this._data.rows.indexOf(row) : -1;
    if (i < 0 || this._rm.dataset !== this._data) { this._dropWorker(); return; }
    try { this._rm.edit(i, row, this._rev); } catch { this._dropWorker(); }
  }

  /** The model built on the main thread. WHY order.js at WORKER_ROWS and up: a page's first model (and any before
      the worker is ready) has to be built here, and the order from typed-array keys plus the table rebuilt from it
      was ~0.45-0.6 s at 100,000 rows against ~0.7-1 s for rowModel() (bench/order.mjs, Node); the same rows, groups
      and table (tests/unit/order.test.mjs and rowmodel-worker.test.mjs). Smaller data and pivots/trees: rowModel(). */
  _modelHere(only = null) {
    const keep = this._keeping();
    const opts = { query: this.query, filters: this._filters, only, keep };
    if (this._live) return this._live.model(this._base, this.view, opts);
    const d = this._data;
    if (!keep && d.rows.length >= WORKER_ROWS && workerEligible(d, this.view, labelled(d, this._base))) {
      if (!this._ranks || this._ranks.dataset !== d || this._ranksRev !== this._rev) { this._ranks = rankCache(d); this._ranksRev = this._rev; }
      const order = fastOrder(d, this._base, this.view, opts, this._ranks);
      if (order) return modelFromOrder(d, this._base, this.view, order);
    }
    return rowModel(d, this._base, this.view, opts);
  }

  /** Ask the worker for the model behind `key`; false when it cannot answer (none yet, not holding this data and
      revision yet, or a pivot or tree view), and the caller builds it here. */
  _askWorker(key, t0, only = null) {
    const rm = this._rm;
    // WHY not while §15's "Show only selected" narrows the rows: the worker's protocol carries no selection; a selection
    // is a person's picks, small enough for the main thread
    if (only) return false;
    if (!rm || !rm.ready || rm.dataset !== this._data || rm.rev !== (this._rev || 0) || this._precInfo) return false;
    if (!workerEligible(this._data, this.view, labelled(this._data, this._base))) return false;
    const p = { key, data: this._data, base: this._base };
    this._pending = p;
    this._busy();
    this._drawBar(); // the toolbar shows the change at once; the rows follow when the model lands
    rm.model(this._base, this.view, { query: this.query, filters: this._filters }).then((m) => {
      if (this._pending !== p) return; // a newer render took over (its own model, a reuse, or the element left)
      this._pending = null;
      if (!m) { this._render(); return; }
      this._model = m;
      this._modelOnly = false;
      this._modelKey = key;
      this._modelData = p.data;
      this._modelBase = p.base;
      this._unbusy();
      this._draw(t0, false, true);
    }, () => {
      // a worker that failed or fell behind: retire it and build this model here
      if (rm === this._rm) this._dropWorker();
      if (this._pending === p || !this._pending) { this._pending = null; if (this._started) this._render(); }
    });
    return true;
  }

  /** The worker, for <data-facets>' counts (railCounts): only while it holds this data at this revision. */
  _countWorker() {
    const rm = this._rm;
    return rm && rm.ready && rm.dataset === this._data && rm.rev === (this._rev || 0) && !this._precInfo ? rm : null;
  }

  _busy() { this.classList.add('dv-computing'); const v = this.$('.dv-stage > .dv-view'); if (v) v.setAttribute('aria-busy', 'true'); }
  _unbusy() { this.classList.remove('dv-computing'); const v = this.$ && this.$('.dv-stage > .dv-view'); if (v) v.removeAttribute('aria-busy'); }

  // ------------------------------------------------------------------ the row model -> the view
  _input() {
    const m = this._model;
    return {
      // the effective view: with `grouping: <id>`, that entry's levels and tiles (the grouped gallery's amendment)
      rows: m.rows, groups: m.groups, columns: m.columns, view: Object.freeze(clone(bareView(G.effectiveView(this.view), m.columns))), tokens: this.tokens(),
      total: m.total, matched: m.matched, table: m.table, pivot: m.pivot, query: this.query, filters: clone(this._filters),
      selectable: this.hasAttribute('selectable'), selected: this._marks(),
      // CONTRACT §37: cells edit in place on an editable page; the add row and a media cell's files are the page's to take
      editable: this.editing, addRow: this.hasAttribute('add-row'), canAdd: this._hasSwitch() ? !!this._editOn : this.editing || typeof this.acceptAdd === 'function', canAttach: typeof this.acceptFile === 'function',
      // CONTRACT §40: Edit on an edit-toggle page (delete, paste, the column menu); View there (a form stands down)
      editTools: this._editTools(), viewOnly: this._viewOnly(),
      // raw, originOf and origin: where the rows came from (docs/CONTRACT.md §24, the source view)
      dataset: Object.freeze({ id: this._data.id, title: this._data.title, titleProperty: this._data.titleProperty, linkProperty: this._data.linkProperty, imageProperty: this._data.imageProperty, detail: this._data.detail, records: this._data.records, url: this.dataUrl, attribution: this._data.attribution ?? null,
        raw: this._data.raw || null, originOf: this._data.originOf || (() => null), origin: this._data.origin || null }),
      hiddenSeries: Object.freeze([...this._hidden]),
      // CONTRACT §26: the store, the clock and the window, for a view that reads a live dataset itself (null otherwise)
      live: this._live ? this._live.input() : null,
      // CONTRACT §32: the other datasets a 3D view's layers read ({} unless a host set el.layers)
      layers: this._layersInput(),
      // CONTRACT §36: what rolls up and the reader's precedence (null when nothing does)
      precedence: this._precInput(),
    };
  }

  _render() {
    if (!this._started) return;
    const t0 = performance.now();
    // §15 "Show only selected" (the bulk bar's toggle sets el._onlySelected): the model narrows to the selection, so the
    // view, its groups and the counts all describe it; an empty selection shows every row
    const only = this._onlySelected && this._selection.ids.size ? new Set(this._selection.ids) : null;
    // WHY reuse: units, column widths, theme, the open mode and a peek re-render the view but cannot change its rows;
    // rebuilding filtered, sorted and grouped everything again (~116 ms grouped at 1,149 rows, seconds at 100,000).
    // The key is every view key rowModel reads (MODEL_KEYS, held to rowmodel.js by a test), the search, the filters,
    // the data and .base objects, and dataRevision, since an edit changes a row in place (perf review 2026-10-26,
    // item 5); and (§15) the selection while it narrows the rows
    const keep = this._keeping();
    const key = JSON.stringify([this._rev || 0, this.query, this._filters ?? null, MODEL_KEYS.map((k) => this.view[k] ?? null), only ? [...only] : null, keep ? [...keep] : null]);
    const reuse = this._model && key === this._modelKey && this._data === this._modelData && this._base === this._modelBase;
    const p = this._pending;
    // WHY wait: a render while the worker computes this very model (units, theme, a peek) draws when it lands, with
    // whatever the view is by then; asking again would only queue the same work
    if (!reuse && p && p.key === key && p.data === this._data && p.base === this._base) { this._drawBar(); return; }
    this._pending = null; // anything else supersedes a model still on its way: it will draw nothing
    if (!reuse) {
      // WHY here: a new model is asked for, so every draw still on its way (a view whose code is loading, an update
      // that has not resolved) was started for an older one and must not mount it. A worker request draws nothing
      // until it lands, so without this an older draw passed its check and showed the old rows under the new filter
      // (judge r1, 2026-10-27: 27 rows of 5,000 under n > 4995 while the 4-row model was pending)
      ++this._renderId;
      if (this._askWorker(key, t0, only || keep)) return;
      this._model = this._modelHere(only);
      this._modelOnly = !!only;
      this._modelKey = key;
      this._modelData = this._data;
      this._modelBase = this._base;
    }
    this._unbusy();
    this._draw(t0, reuse, false);
  }

  /** A live dataset's news or the clock moved (live/feed.js, at most once per animation frame): the model again and
      the view's update, without the toolbar, the URL or the change event (docs/peps/0012-live-data.md §8). Returns
      the view's update() result (a promise for an async view). */
  _liveDraw() {
    if (!this._started || !this._plugin || this._pending || this._pluginType !== (viewPlugin(this.view.type) ? this.view.type : 'table')) return this._render();
    this._revise();
    this._model = this._modelHere();
    this._modelKey = null; // the next full render builds its own
    this._modelData = this._data;
    this._modelBase = this._base;
    this._liveStatus();
    return this._plugin.update(this._input());
  }

  /** A paused live view whose rows at t stayed and whose count did not (live/feed.js: retention took rows at t it does
      not read): the status line alone. */
  _liveCount(total) {
    const m = this._model;
    if (!m || m.total === total) return;
    m.total = total;
    this._liveStatus();
  }

  /** A live view's status line. WHY four times a second: the count changes with every row, and a status line
      rewritten 60 times a second per panel is DOM churn nobody can read; and once more after a burst, so the count
      that stays on screen is the last one. */
  _liveStatus() {
    const wait = 250 - (performance.now() - (this._liveStatusAt || 0));
    if (wait <= 0) {
      if (this._liveStatusTimer) { clearTimeout(this._liveStatusTimer); this._liveStatusTimer = null; }
      this._liveStatusAt = performance.now();
      this._drawStatus();
    } else if (!this._liveStatusTimer) {
      this._liveStatusTimer = setTimeout(() => { this._liveStatusTimer = null; if (this.isConnected && this._model) this._liveStatus(); }, wait);
    }
  }

  /** The model is in: the toolbar, status, URL, the change event and the view's update. */
  _draw(t0, reuse, worker) {
    measure('data-ui:model', t0, { id: this.id || null, type: this.view.type, rows: this._model.rows.length, reused: !!reuse, worker });
    // §15: whether the rows are narrowed to the selection, read from the model's own key (a worker model never is)
    this._model.onlySelected = !!this._modelOnly;
    // §15: rows a new filter hides leave the selection
    if (this._selection.ids.size) {
      const before = this._selection.ids.size;
      this._selection.retain(new Set(this._model.rows.map((r) => String(r.id))));
      if (this._selection.ids.size !== before) queueMicrotask(() => this._selectionChanged());
    }
    this._drawBar();
    if (this._queryUi) this._queryUi.update();
    if (this._expandUi) this._expandUi.update();
    if (this._bulkUi) this._bulkUi.update();
    this._drawStatus();
    this._drawIntro();
    drawNotes(this);
    this._writeUrl();
    this._persistChange();
    const id = ++this._renderId;
    const model = this._model; // the model this draw is for: checked again before it mounts and when it is done
    const wanted = this.view.type;
    const type = viewPlugin(wanted) ? wanted : viewPlugin('table') ? 'table' : null;
    const notice = this.$('.dv-notice');
    if (type !== wanted) {
      notice.hidden = false;
      notice.textContent = PLANNED_TYPES.includes(wanted)
        ? `The ${wanted} view is planned (${PLANNED_IN[wanted] || 'docs/VIEWS.md'}) but not built yet; showing the table.`
        : `data-ui has no '${wanted}' view; showing the table.`;
    } else notice.hidden = true;
    this.dispatchEvent(new CustomEvent('data-views-change', { detail: { view: clone(this.view), name: this.origin.name, dirty: this.dirty, filters: clone(this._filters), grouping: (G.groupingOf(this.view) || {}).id ?? null } }));
    if (!type) return;
    const done = () => {
      if (id !== this._renderId || this._model !== model) return;
      this._reveal();
      this.dataset.view = type;
      const detail = { id: this.id || null, type, rows: this._model.rows.length };
      measure('data-ui:render', t0, detail);
      if (!this._drawnOnce) { this._drawnOnce = true; mark('data-ui:first-render', detail); }
      // big data: the worker starts once the first rows are on screen (a frame, then a task), never before them
      if (!this._rm && this._data.rows.length >= WORKER_ROWS) requestAnimationFrame(() => setTimeout(() => this._ensureWorker(), 0));
      // §44: the columns changed under an open inspector (hide, reorder): it follows, not on the next record
      if (this._peek && this._peekKey !== inspectorKey(this)) this.refreshPeek();
      this.dispatchEvent(new CustomEvent('data-views-render', { detail: { type, ms: performance.now() - t0, rows: this._model.rows.length } }));
    };
    if (this._plugin && this._pluginType === type) {
      const plugin = this._plugin;
      // this draw's own job: a failure is judged against it (still current or not), never against the stage as it is
      const job = { id, model, el: plugin.el || null, plugin, fresh: false };
      let out;
      try { out = plugin.update(this._input()); } catch (err) { this._viewFailed(type, err, job); return; }
      if (out && typeof out.then === 'function') out.then(done, (err) => this._viewFailed(type, err, job)); else done();
      return;
    }
    const stage = this.$('.dv-stage');
    if (!this._plugin && !stage.querySelector(':scope > .dv-served')) stage.innerHTML = '<div class="dv-loading">Loading…</div>';
    const job = { id, model, el: null, plugin: null, fresh: true };
    loadView(type).then((mod) => {
      const { View } = mod;
      if (id !== this._renderId || this._model !== model) return;
      this._viewMod = mod;
      if (this._plugin) { try { this._plugin.destroy(); } catch { /* a view's own cleanup failing must not block the next */ } }
      this._plugin = null;
      this._pluginType = null;
      const el = document.createElement('div');
      el.className = `dv-view dv-view-${type}`;
      job.el = el;
      // WHY beside, not instead of, a host's own rows: they are the only rows on screen until the new view has drawn,
      // which is when its update() resolves (an async view draws later than its code loads). The view is laid out
      // (so it can measure) but hidden from sight and from screen readers, under the served rows, until then; a view
      // that throws or rejects leaves the served rows in place (judge r1, 2026-10-27, finding 3)
      const served = stage.querySelector(':scope > .dv-served');
      if (served) {
        el.style.visibility = 'hidden';
        el.setAttribute('aria-hidden', 'true');
        served.classList.add('dv-served-over');
        stage.replaceChildren(el, served);
      } else stage.replaceChildren(el);
      this._applyChrome();
      if (!served) stage.removeAttribute('aria-busy');
      const plugin = new View(this._host, el);
      job.plugin = plugin;
      this._plugin = plugin;
      this._pluginType = type;
      this._viewOptions = null;
      let out;
      try { out = plugin.update(this._input()); } catch (err) { this._viewFailed(type, err, job); return; }
      if (out && typeof out.then === 'function') out.then(done, (err) => this._viewFailed(type, err, job)); else done();
    }).catch((err) => this._viewFailed(type, err, job));
  }

  /** A view has drawn: a host's own rows that were kept on screen meanwhile go, and the view shows (see _draw). */
  _reveal() {
    const stage = this.$ && this.$('.dv-stage');
    if (!stage) return;
    const view = stage.querySelector(':scope > .dv-view');
    if (!view) return;
    const served = stage.querySelector(':scope > .dv-served');
    if (served) served.remove();
    view.style.visibility = '';
    view.removeAttribute('aria-hidden');
    stage.removeAttribute('aria-busy');
    for (const e of stage.querySelectorAll(':scope > .dv-err')) e.remove();
  }

  /** A view failed: it could not load, its constructor threw, or its update() threw or rejected. A host's own rows
      stay on screen under the message (they are still true); a view that never drew is removed; a view that had drawn
      before keeps its last rows, with the message above them. */
  _viewFailed(type, err, job) {
    const stage = this.$ && this.$('.dv-stage');
    if (!stage) return;
    // WHY judged by the job: a failure can arrive after a newer draw has succeeded (a view's code that fails to load
    // late, an update() that rejects late); it then owns nothing on screen, and wiping the stage erased the newer view
    // and left its plugin detached (judge r2, 2026-10-27). A stale job cleans up only what it made itself, if that is
    // not what is showing now, and says nothing.
    if (job.id !== this._renderId || job.model !== this._model) {
      if (job.plugin && job.plugin !== this._plugin) { try { job.plugin.destroy(); } catch { /* not ours to report */ } }
      if (job.el && job.el.isConnected && !(this._plugin && job.plugin === this._plugin)) job.el.remove();
      return;
    }
    const served = stage.querySelector(':scope > .dv-served');
    if (job.fresh) {
      if (job.plugin && this._plugin === job.plugin) {
        try { job.plugin.destroy(); } catch { /* the failed view's cleanup must not hide its error */ }
        this._plugin = null;
        this._pluginType = null;
      }
      if (job.el) job.el.remove();
      // what is left is a Loading… line (or nothing): the message replaces it; a host's own rows stay
      if (!served && !stage.querySelector(':scope > .dv-view')) stage.replaceChildren();
    }
    const fresh = job.fresh;
    for (const e of stage.querySelectorAll(':scope > .dv-err')) e.remove();
    if (served) served.classList.remove('dv-served-over');
    const msg = err && err.message ? err.message : String(err);
    stage.insertAdjacentHTML('afterbegin', `<p class="dv-err" style="padding:12px">The ${esc(type)} view failed${fresh ? ' to load' : ''}: ${esc(msg)}</p>`);
    stage.removeAttribute('aria-busy');
  }

  /** The view's answer first (CONTRACT §16 `intro:`): KPI cards and a few lines of markdown above the rows. The KPI
      block is an inline `type: kpi` view entry, drawn by the kpi view over the same data and the same rail filter. */
  _drawIntro() {
    const box = this.$('.dv-intro');
    const intro = this.view && this.view.intro;
    // WHY a class: an intro adds height above the rows instead of taking it from them (styles/core.css)
    // WHY no text here any more (CONTRACT §28, src/notes.js): the intro's text is the view's About note, on demand
    this.classList.toggle('dv-has-intro', !!(intro && intro.kpi));
    if (!intro || !intro.kpi) {
      box.hidden = true;
      if (this._introKpi) { try { this._introKpi.destroy(); } catch { /* ignore */ } this._introKpi = null; }
      return;
    }
    box.hidden = false;
    box.querySelector('.dv-intro-text').hidden = true;
    const slot = box.querySelector('.dv-intro-kpi');
    slot.hidden = !intro.kpi;
    if (!intro.kpi) return;
    const kv = { name: this.view.name, ...intro.kpi, type: 'kpi' };
    // WHY reused: the intro ran a whole synchronous rowModel() on every render (units, widths, theme, every frame of a
    // search), though its cards read only the data, the rail's filters and the kpi entry; the same key as the view's
    // own model reuse (MODEL_KEYS, dataRevision), so an edit or a tick still recounts it
    const ikey = JSON.stringify([this._rev || 0, this._filters ?? null, MODEL_KEYS.map((k) => kv[k] ?? null), intro.kpi]);
    const reuse = this._introModel && ikey === this._introModelKey && this._data === this._introData && this._base === this._introBase;
    const model = reuse ? this._introModel : rowModel(this._data, this._base, kv, { filters: this._filters });
    this._introModel = model;
    this._introModelKey = ikey;
    this._introData = this._data;
    this._introBase = this._base;
    const input = { ...this._input(), rows: model.rows, groups: model.groups, columns: model.columns, view: Object.freeze(clone(kv)), total: model.total, matched: model.matched, table: model.table, pivot: null };
    const key = this.origin.name;
    if (this._introKpi && this._introKey === key) { this._introKpi.update(input); return; }
    if (this._introKpi) { try { this._introKpi.destroy(); } catch { /* ignore */ } this._introKpi = null; }
    this._introKey = key;
    // the intro's own host: it opens the shared peek, but never writes the view or the status line
    const host = Object.freeze({ setView: () => this.view, propose: (edit) => this.propose(edit), open: (id, opts) => this.openPeek(id, opts),
      setStatus: () => {}, element: this, scroller: null, opener: null });
    loadView('kpi').then(({ View }) => {
      if (this._introKey !== key || this._introKpi) return;
      const el = document.createElement('div');
      el.className = 'dv-intro-cards'; // not .dv-view: that class is the view's own slot, which hosts and checks look for
      slot.replaceChildren(el);
      this._introKpi = new View(host, el);
      this._introKpi.update(input);
    });
  }

  /** CONTRACT §18 (embedded chrome): whether the status line and the view's own control bar show. Per key, the view's
      entry (`status:`, `controls:` in the .base) wins over the element's attribute (`status="off"`, `controls="off"`),
      which wins over the default, on. WHY first-class (Zach, 2026-10-26, on Vibe Tracks hiding them with CSS: "can you
      please provide first class support for this so we don't need to do hacky css"): a host that embeds one view as a
      part of its own page (a KPI head, a history strip) has its own words around it, and "119 of 119 rows" or an Encode
      button there is noise; a host reaching into .dv-status breaks the day the kit renames it. */
  chrome() {
    const v = this.view || {};
    const on = (key) => {
      const own = v[key];
      if (own !== undefined && own !== null) return !(own === false || own === 'off' || own === 'hide' || own === 'none');
      const attr = this.getAttribute(key);
      return !(attr === 'off' || attr === 'hide' || attr === 'none' || attr === 'false');
    };
    return { status: on('status'), controls: on('controls') };
  }

  /** Applies chrome(): the status line's `hidden`, and `data-controls` on the view's slot (each view hides its own bar
      under it: today the chart's Encode / Rows bar). Mirrored on the element as data-status / data-controls. */
  _applyChrome() {
    const c = this.chrome();
    const st = this.$('.dv-status');
    if (st) st.hidden = !c.status;
    this.dataset.status = c.status ? 'on' : 'off';
    this.dataset.controls = c.controls ? 'on' : 'off';
    const slot = this.$('.dv-stage > .dv-view');
    if (slot) slot.dataset.controls = c.controls ? 'on' : 'off';
  }

  _drawStatus() {
    const m = this._model;
    if (!m) return;
    this._applyChrome();
    const v = this.view;
    // WHY name what was rolled away: a rolled-up number is a different number, and the reader must see across what
    const props = m.columns;
    const away = m.rolled ? m.rolled.away.map((d) => props[d].label) : [];
    const across = away.length ? ` · <span class="dv-rolled-note">rolled up across ${esc(away.join(', '))}</span>` : '';
    const what = v.type === 'pivot' && m.pivot
      ? `${m.pivot.rows.length.toLocaleString()} rows × ${m.pivot.columns.length} columns · from ${m.matched.toLocaleString()} of ${m.total.toLocaleString()} records${across}`
      : m.rolled ? `${m.matched.toLocaleString()} rows from ${m.rolled.from.toLocaleString()} of ${m.total.toLocaleString()}${across}`
      : `${m.matched.toLocaleString()} of ${m.total.toLocaleString()} rows`;
    const groups = m.groups && v.type !== 'pivot' ? ` · ${m.groups.length} groups` : m.pivot && m.pivot.groups ? ` · ${m.pivot.groups.length} groups` : '';
    const limited = v.limit && m.rows.length < m.matched ? ` · first ${m.rows.length}` : '';
    const only = m.onlySelected ? ` · showing ${m.matched.toLocaleString()} selected` : '';
    // §40: rows kept after an edit say so, and the way to apply the filter again
    const kept = m.kept ? ` · <span class="dv-kept">${m.kept} edited ${m.kept === 1 ? 'row no longer matches' : 'rows no longer match'} <button type="button" class="dv-link" data-rows-refresh>Refresh</button></span>` : '';
    this.$('.dv-status').innerHTML = `<span class="dv-count">${what}${groups}${limited}${only}</span>${kept}${this._status ? ` · <span class="dv-status-view">${this._status}</span>` : ''}${this._precStatusHtml()}${m.error ? ` · <span class="dv-err">filter: ${esc(m.error)}</span>` : ''}${this._persistNote ? ` · <span class="dv-err">${esc(this._persistNote)}</span>` : ''}${this._open.statusHtml()}${aboutButton(v) ? ` · ${aboutButton(v)}` : ''}`;
  }

  /** view-counts (CONTRACT §37): how many rows a view's own filters and the all-views filter leave; null without the
      attribute, or for a filter that does not compile. Read once per data and filter. */
  _viewCount(v) {
    if (!this.hasAttribute('view-counts') || !this._data) return null;
    const stamp = JSON.stringify([this._rev || 0, this._filters ?? null]);
    if (this._countStamp !== stamp) { this._countStamp = stamp; this._counts = new Map(); }
    const key = JSON.stringify(v.filters ?? null);
    if (!this._counts.has(key)) {
      let n = null;
      try {
        const clauses = [this._filters, v.filters].filter((x) => x !== undefined && x !== null);
        const test = clauses.length ? G.compileFilters(clauses.length > 1 ? { and: clauses } : clauses[0]) : null;
        n = test ? this._data.rows.reduce((k, r) => k + (test(r) ? 1 : 0), 0) : this._data.rows.length;
      } catch { n = null; }
      this._counts.set(key, n);
    }
    return this._counts.get(key);
  }

  _drawBar() {
    const users = this._userViews();
    const tab = (kind, v) => {
      const on = this.origin.kind === kind && this.origin.name === v.name;
      const n = this._viewCount(v);
      return `<button role="tab" class="dv-tab${on ? ' dv-on' : ''}" aria-selected="${on}" data-kind="${kind}" data-name="${esc(v.name)}">${esc(v.name)}${n === null ? '' : ` <span class="dv-tabn">${n}</span>`}${kind === 'user' ? '<span class="dv-mine" title="Your view, saved in this browser">•</span>' : ''}</button>`;
    };
    this.$('.dv-tabs').innerHTML = this.presets.map((v) => tab('preset', v)).join('') + users.map((v) => tab('user', v)).join('');
    // WHY hidden with a hook: every change is already on its way into the file, so there is nothing to Reset to or Save
    this.$('.dv-dirty').hidden = !this.dirty || typeof this.persistView === 'function';
    const props = this._model.columns;
    const hasUnits = Object.values(props).some((p) => p.unit || p.unitText);
    const u = this.$('.dv-units');
    u.hidden = !hasUnits;
    const es = this.$('.dv-editsw');
    if (es) { es.setAttribute('aria-checked', String(this.editing)); es.classList.toggle('dv-on', this.editing); }
    u.setAttribute('aria-pressed', String((this.view.units || 'column') === 'inline'));
    u.textContent = (this.view.units || 'column') === 'inline' ? 'Units: next to values' : 'Units: in column';
    const v = this.view;
    const mark = (name, on, text) => { const b = this.$(`[data-menu="${name}"]`); b.classList.toggle('dv-set', !!on); b.textContent = text; };
    const label = (id) => (props[id] ? props[id].label : id);
    const plugin = viewPlugin(v.type);
    mark('layout', false, plugin ? plugin.name : v.type);
    const ru = this.$('[data-menu="rollup"]');
    ru.hidden = !(v.type === 'table' || v.type === 'pivot');
    const rolledAway = v.rollup && this._model.rolled ? this._model.rolled.away : [];
    mark('rollup', !!v.rollup, rolledAway.length ? 'Rolled up: ' + rolledAway.map(label).join(', ') : v.rollup ? 'Rolled up' : 'Roll up');
    const ev = G.effectiveView(v);
    const levels = [ev.groupBy, ev.subGroupBy].filter(Boolean);
    mark('group', levels.length, levels.length ? 'Group: ' + levels.map((g) => label(g.property) + (g.by ? ` by ${g.by}` : '')).join(' › ') : 'Group');
    mark('sort', (v.sort || []).length, (v.sort || []).length ? `Sort: ${label(v.sort[0].property)}${v.sort.length > 1 ? ' +' + (v.sort.length - 1) : ''}` : 'Sort');
    const nf = G.filterList(v.filters).length;
    mark('filter', nf, nf ? `Filter · ${nf}` : 'Filter');
    if (this._barUi) this._barUi.update();
    if (this._settingsUi) this._settingsUi.update();
  }

  // ------------------------------------------------------------------ the side peek: one record surface for every view
  /** host.open(id, {column, records, title, row}): a record's fields, every value behind it, and (for a pivot
      cell or a group) the records behind it. The current view's `record.sections` lay the fields out, and its
      `edit: true` makes them a form that proposes the changed fields, as the record view does (docs/CONTRACT.md
      amendment 2026-10-26 (core pass)). */
  openPeek(id, { column = null, records = null, title = null, row = null } = {}) {
    const d = this._data;
    const props = this._model.pivot ? this._model.pivot.properties : this._model.columns;
    const r = row || this.row(id);
    if (!r) return;
    const opts = { column, records, title, row };
    this._peek = { id: String(id), row: r, column, opts };
    const named = title ?? r[d.titleProperty] ?? r._label ?? 'Row';
    // WHY cellValue: a title in a rich cell (a media cell's words) reads as its words, not "[object Object]"
    const name = named !== null && typeof named === 'object' && !Array.isArray(named) ? G.cellValue(named) ?? 'Row' : named;
    const link = d.linkProperty && r[d.linkProperty] ? `<a class="dv-peeklink" href="${esc(r[d.linkProperty])}">Open page ↗</a>` : '';
    const unitOf = (p) => (p.unit ? r[p.unit] : undefined);
    const isUnitColumn = (p) => Object.values(props).some((q) => q.unit === p.id);
    const v = bareView(this.view || {}, this._model.columns);
    // WHY a form only for a real row: a pivot row or a group's summary is not a record anyone can edit
    // §40: in View an edit-toggle page's record is words, not a form
    const edit = !!v.edit && r === this.row(id) && !this._viewOnly();
    // a field the view displays as a link or a status (docs/CONTRACT.md §35): a real link, resolved against the data
    // file's URL; a badge with its glyph and word. Every other field as before
    const shown = (p) => {
      const d = v.display && v.display[p.id];
      if (d === 'link') return linkHtml(r[p.id], this.dataUrl);
      // CONTRACT §37: a media cell's words and thumbnails, as the table draws them; a thumbnail opens large from here too
      if (attachmentsOf(r[p.id]).length) return `<span class="dv-mc-text">${esc(G.cellValue(r[p.id]) ?? '')}</span><span class="dv-peek-media" data-peek-media="${esc(p.id)}">${thumbsHtml(r[p.id], { url: this.dataUrl })}</span>`;
      const said = valueHtml(r[p.id], d === 'status' ? { ...p, display: 'status' } : p, { unit: unitOf(p), detail: true, dataset: { url: this.dataUrl } });
      // CONTRACT §36: the agree / differs fact stays with the value; its sources are the field's right-click, and rows of their own here
      const facts = this._precInfo && isMultiSource(r[p.id]) ? agreement(r[p.id], formulaView(this._precInfo, this._prec, p.id), r.id) : null;
      return facts ? `${said}<span class="dv-src-note">${esc(facts.text)}</span>` : said;
    };
    const fieldRow = (p) => {
      const label = edit && !lockedBecause(p) ? `<label for="dv-f-${esc(p.id)}">${esc(p.label)}</label>` : esc(p.label);
      // a relation's records are links that open them in this peek (../open.js, the trail)
      const body = edit ? fieldHtml(r, p, { unit: unitOf(p) }) : this._open.relationHtml(r, p) ?? shown(p);
      // CONTRACT §36: a value two or more sources state is marked (and a tab stop, so the menu key reaches it): its item
      // menu lists them. Only a real record's: a pivot row or a group is no row anyone picks a source for
      const src = edit || r !== this.row(id) ? '' : sourcesAttr(r[p.id], r.id, p.id, { focusable: true });
      const vis = !edit && r === this.row(id) && !records ? visibilityButton(this, p.id, p.label) : '';
      return `<tr class="dv-peek-field${p.id === column ? ' dv-active' : ''}" data-p="${esc(p.id)}"${src}><th scope="row">${label}${vis}</th><td>${body}</td></tr>`;
    };
    // record.sections (sections.js): fields, and a view embedded under them with `this.` bound to this row (§35's evidence);
    // a section with nothing for this row is left out (RobotDx PEP 0001 §18.4, ask 3), except in the form, which edits
    // empty fields too
    // §38: a real record's long properties leave the rows and become the page under them, written in right there
    const real = !records && !title && r === this.row(id);
    const pageable = !edit && real;
    const given = peekSections(v, props, r, edit ? {} : { rowsOf: (bound) => this._sectionRows(bound) });
    // §44, the inspector: one property per row, 1:1 with the columns the reader sees, the rest behind "N more properties". WHY only a
    // real record: a pivot row or a group's summary has no columns of its own to match
    const drawn = real && this._plugin && this._plugin.drawnColumns ? this._plugin.drawnColumns() : null;
    const byId = new Map((drawn || []).map((c) => [c.id, c]));
    const plan = real ? inspectorProperties({ view: v, columns: props, titleProperty: d.titleProperty, row: r, drawn, listed: given ? given.flatMap((s) => s.list.map((p) => p.id)) : null, exclude: d.detail ? [d.detail.property] : [] }) : null;
    const propOf = (pid) => props[pid] || byId.get(pid);
    // WHY a form lists every field: it is where the row is written, and a required input behind a fold cannot report itself
    const fold = !!plan && !edit;
    const sections = given
      ? given.map((s) => ({ ...s, list: fold ? s.list.filter((p) => plan.shown.includes(p.id)) : s.list }))
      : [{ name: null, view: null, list: real ? (fold ? plan.shown : [...plan.shown, ...plan.more]).map(propOf) : Object.values(props).filter((p) => !p.pivot && !p.hidden && !isUnitColumn(p) && (edit ? p.id !== d.titleProperty : !isEmpty(G.cellValue(r[p.id])))) }];
    const moreProps = fold ? plan.more.map(propOf) : [];
    // §38: a real record's long properties leave the rows and become the page under them, written in right there; one the view
    // has not hidden stays on the page even with no column, as a Notion page's body does
    const isPage = (p) => !!p && pageable && isLong(p, v);
    // WHY the title too: it is no row, but a long title is the page's text, and §38 writes it there
    const longTitle = !given && isPage(props[d.titleProperty]) ? [props[d.titleProperty]] : [];
    const longs = [...longTitle, ...sections.flatMap((sec) => sec.list.filter(isPage)), ...(given ? [] : moreProps.filter((p) => isPage(p) && visibilityOf(v, p.id) !== 'hide'))];
    const rest = moreProps.filter((p) => !longs.includes(p));
    if (longs.length) for (const sec of sections) sec.list = sec.list.filter((p) => !isLong(p, v));
    const embeds = edit ? [] : sections.filter((sec) => sec.view).map((sec, i) => ({ ...sec, key: sec.name || `section ${i + 1}` }));
    const tables = sections.map((sec) => `${sec.name ? `<h3 class="dv-peek-section">${esc(sec.name)}</h3>` : ''}${sec.list.length ? `<table class="dv-fields"><tbody>${sec.list.map(fieldRow).join('')}</tbody></table>` : ''}${sec.view && !edit ? `<div class="dv-peek-view" data-section="${esc(embeds.find((e) => e.view === sec.view).key)}"></div>` : ''}`).join('');
    const more = moreHtml(rest.map(fieldRow).join(''), rest.length, !!this._propMore);
    const add = pageable ? addPropertyHtml(this) : '';
    const msg = this._peekMsg && this._peekMsg.id === String(id) ? this._peekMsg : null;
    // §46: under a page layout the fields are the property list, the blocks and the free text, in the layout's order
    const layout = pageable ? this._pageLayout() : null;
    const read = (p) => this._open.relationHtml(r, p) ?? shown(p);
    // §46: a host that draws records itself gets the panel's body; the panel, its handle and its ‹ › stay the kit's
    const hosted = typeof this.pageRenderer === 'function' && r === this.row(id);
    const fields = hosted ? '<div data-page-host></div>' : layout ? pageHtml(this, r, layout, props, read) : edit
      ? `<form class="dv-form dv-peek-form" novalidate>${tables}<div class="dv-form-bar"><button type="submit" class="dv-btn dv-primary">Save changes</button><button type="reset" class="dv-btn">Revert</button><p class="dv-form-msg${msg && !msg.ok ? ' dv-refused' : ''}" role="${msg && !msg.ok ? 'alert' : 'status'}">${msg ? esc(msg.text) : ''}</p></div></form>`
      : tables + more + add;
    const page = layout || hosted ? '' : longs.map((p) => sectionHtml(this, r, p, v)).join('');
    let behind = page;
    if (d.detail && Array.isArray(r[d.detail.property]) && r[d.detail.property].length) {
      const want = d.detail.columnKinds && d.detail.columnKinds[column];
      const cols = d.detail.columns;
      const entries = r[d.detail.property];
      const line = cols.filter((c) => !c.block);
      const blocks = cols.filter((c) => c.block);
      const val = (x, c) => (c.link && x[c.link] ? `<a href="${esc(x[c.link])}">${esc(x[c.id] ?? '')}</a>` : esc(x[c.id] ?? ''));
      // WHY a list of entries, not a table: a method or a source runs to a paragraph, and a 460 px peek cannot hold
      // seven columns of that; each entry keeps its short facts on one line and its long ones below, in full
      behind += `<h3>Every value behind it <span class="dv-count">${entries.length}</span></h3><ol class="dv-entries">${entries.map((x) => `<li class="dv-entry${want && x[d.detail.kind] === want ? ' dv-active' : ''}"><div class="dv-entry-line">${line.filter((c) => !isEmpty(x[c.id])).map((c, i) => `<span class="${i === 0 ? 'dv-entry-kind' : ''}" title="${esc(c.label)}">${val(x, c)}</span>`).join('')}</div>${blocks.filter((c) => !isEmpty(x[c.id])).map((c) => `<p><span class="dv-entry-label">${esc(c.label)}</span> ${val(x, c)}</p>`).join('')}</li>`).join('')}</ol>`;
    }
    const recs = records || r._records || null;
    if (recs) {
      const base = this._model.columns;
      const cols = (d.records && d.records.columns) || [...new Set(recs.flatMap((x) => Object.keys(x)))].filter((k) => !k.startsWith('_') && base[k] && !base[k].hidden).map((cid) => ({ id: cid, label: base[cid].label }));
      const where = column && props[column] && props[column].pivot ? ` in <b>${esc(props[column].group ? props[column].group + ' / ' : '')}${esc(props[column].label)}</b>` : '';
      behind += `<h3>The ${recs.length} records behind ${records && column ? 'this cell' : 'this row'}${where}</h3><div class="dv-peektable"><table><thead><tr>${cols.map((c) => `<th>${esc(c.label)}</th>`).join('')}</tr></thead><tbody>${recs.map((x) => `<tr>${cols.map((c) => { const v = G.cellValue(x[c.id]); return `<td class="${isNum(v) ? 'dv-num' : ''}">${esc(cellText(x[c.id]) ?? (Array.isArray(v) ? v.join(', ') : fmtNum(v, base[c.id] && base[c.id].decimals, numOpts(base[c.id])) ?? ''))}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    // a 3D model (a property whose field says media: mesh) is the peek's first thing: an orbit viewer, its poster the
    // view's image (docs/CONTRACT.md §13)
    const meshProp = (v.mesh && props[v.mesh]) || Object.values(props).find((p) => p.media === 'mesh' && !isEmpty(G.cellValue(r[p.id])));
    const model = meshProp ? G.cellValue(r[meshProp.id]) : null;
    let viewer = '';
    if (!isEmpty(model)) {
      const posterProp = v.image || d.imageProperty;
      const poster = posterProp ? G.cellValue(r[posterProp]) : null;
      const url = (x) => mediaUrl(Array.isArray(x) ? x[0] : x, { url: this.dataUrl });
      const camView = v.meshView ? G.cellValue(r[v.meshView]) : null;
      const camAttr = camView && typeof camView === 'object' ? ` view="${esc(JSON.stringify(camView))}"` : '';
      const bgMode = ['match', 'light', 'theme'].includes(v.meshBackground) ? v.meshBackground : 'match';
      viewer = `<data-mesh class="dv-peek-mesh" interact="orbit" background="${bgMode}"${camAttr} src="${esc(url(model))}"${isEmpty(poster) ? '' : ` poster="${esc(url(poster))}"`} alt="${esc(name)}"></data-mesh><p class="dv-peek-mesh-hint">Drag to turn · scroll to zoom · double-click to reset</p>`;
    }
    const peek = this.$('.dv-peek');
    // CONTRACT §37: the host's own controls for a real record, at the foot of its fields
    const extra = typeof this.peekExtra === 'function' && r === this.row(id) && !records ? this.peekExtra(r) : '';
    const foot = extra ? `<div class="dv-peek-extra">${extra}</div>` : '';
    // §44, the slot: everything that is not one property of the record lives under the properties, never between or beside them:
    // the page (§38), every value behind it, the records behind it, the sources, then the host's own (peekExtra)
    const slot = `<div class="dv-peek-slot">${behind}${real ? this._open.sourcesPane(r) : ''}${foot}</div>`;
    // a record's peek is the open modes' rich one (photo, ‹ n of N ›, Open page) around these same fields
    const rich = this._open.peekHtml(r, String(id), opts, String(name), viewer + fields + slot);
    peek.innerHTML = rich ?? `<header><h2>${esc(name)}</h2>${link}<button class="dv-btn dv-close" aria-label="Close details">✕</button></header>${viewer}${fields}${slot}`;
    peek.hidden = false;
    peek.classList.toggle('dv-peek-page', longs.length > 0 || !!layout);
    peek.classList.toggle('dv-peek-hosted', hosted);
    if (hosted) this._holdPage(peek, r, String(id)); else this._dropPage();
    fitSections(peek);
    fitPage(peek);
    this._syncPageFull(!!layout);
    // §46: a derived cell's click opens its section; once: the column leaves the peek's options, so a redraw does not open it again
    if (layout && column) { this._peek.column = null; this._peek.opts = { ...opts, column: null }; revealBlock(this, column); }
    this._mountSections(peek, embeds);
    this.classList.add('dv-peeking');
    this._peekKey = inspectorKey(this);
    this._open.opened(this._peek);
    // §15 beside open modes: an overlay or full-screen pane and View settings would cover each other; the record wins
    if (this._settingsUi && this._settingsUi.isOpen() && !this.classList.contains('dv-split')) this._settingsUi.close();
    if (this._plugin && this._plugin.peeked) this._plugin.peeked(this._peek);
    this.dispatchEvent(new CustomEvent('data-views-open', { detail: { row: r, column, records: recs } }));
  }

  /** The dataset a record section's view reads: this element's own (no `from:`, or the one it was handed as), else one a
      host handed in `el.sections`; null when there is none here. */
  _sectionData(view) {
    const from = view.from;
    return !from || from === this._ds ? this._data : (this.sections && this.sections[from]) || null;
  }

  /** How many rows a record section's view shows for the peeked row (its filters bound already; 0 or 1 is enough to
      tell), as the embedded view will draw it: a file's rows through its filters, a live dataset's at its clock's t in
      the view's window (live/feed.js atOf, tNow). null when that cannot be told here (no such dataset, a filter that
      does not compile): the section stays, and its view says why. */
  _sectionRows(view) {
    const data = this._sectionData(view);
    if (!data) return null;
    try {
      const test = G.compileFilters(view.filters);
      if (isLiveDataset(data)) {
        const c = clockFor(this);
        const t = isLiveClock(c) && c.datasets.includes(data) && c.liveEnd !== null && Number.isFinite(c.t) ? c.t : (data.end ?? Infinity);
        return data.snapshot(t, { at: atOf(view, data), limit: 1, filter: test || null }).length;
      }
      const rows = data.rows || [];
      return (test ? rows.some(test) : rows.length > 0) ? 1 : 0;
    } catch {
      return null;   // a filter that does not compile or run: the embedded view reports it
    }
  }

  /** The views record.sections embeds in the peek (docs/CONTRACT.md §35, PEP 0010 §10's evidence): each a bare
      <data-views> over its dataset's rows as the file holds them, its filters already bound to the peeked row. The
      dataset is this element's own (no `from:`, or the one it was handed as), else one a host handed in `el.sections`
      ({<dataset>: dataset}; a <data-dashboard> hands its drill peek the ones the view's sections name). WHY the file's
      rows and not the page's picks: the evidence is the row's, whatever the rail has picked. */
  _mountSections(peek, embeds) {
    for (const sec of embeds) {
      const slot = [...peek.querySelectorAll('.dv-peek-view[data-section]')].find((s) => s.dataset.section === sec.key);
      if (!slot) continue;
      const from = sec.view.from;
      const data = this._sectionData(sec.view);
      if (!data) { slot.innerHTML = `<p class="dv-note">No dataset '${esc(from)}' here to show.</p>`; continue; }
      const el = document.createElement('data-views');
      for (const [k, v] of [['no-url', ''], ['toolbar', 'none'], ['status', 'off'], ['controls', 'off']]) el.setAttribute(k, v);
      // WHY no peek inside the peek, and the keys kept inside: the outer peek steps records on ↑/↓ and closes on Escape
      el.openPeek = () => {};
      el.addEventListener('keydown', (e) => { if (e.key !== 'Escape') e.stopPropagation(); });
      // WHY the outer view's style: in a dashboard it is the panel's resolved one (families, palette, numbers), so the
      // evidence draws real, sim and target in the page's colours
      const style = sec.view.style || (this.view && this.view.style);
      el.base = { properties: (this.base && this.base.properties) || {}, views: [{ ...sec.view, name: sec.view.name || sec.key, ...(style ? { style } : {}) }] };
      el.data = data;
      slot.append(el);
    }
  }

  closePeek() {
    const was = this._peek;
    this._peek = null;
    this._peekMsg = null;
    // §44: "N more properties" stays open through the records, and folds again when the inspector closes
    this._propMore = false;
    const peek = this.$ && this.$('.dv-peek');
    if (peek) peek.hidden = true;
    this.classList.remove('dv-peeking');
    this._dropPage();
    if (this.pageFull) this.pageFull = false;
    this._open.closed(was);
    if (was && this._plugin && this._plugin.peeked) this._plugin.peeked(null);
  }

  get peeked() { return this._peek; }

  // ------------------------------------------------------------------ CONTRACT §46: a record's page, laid out apart from the table
  /** The layout in force for the open view, or null when records do not draw as laid-out pages. */
  _pageLayout() {
    const props = this._model && this._model.columns;
    if (!props || this._model.pivot || !pageOn(this._base, props)) return null;
    const view = this.view || {};
    return pageLayout(this._base, props, { order: Array.isArray(view.order) ? view.order : null, title: this._data.titleProperty, view });
  }
  _redrawPage() { if (this._peek && this.row(this._peek.id)) this.openPeek(this._peek.id, this._peek.opts); }
  /** The open record's page, full size, or the side panel again. In the link: `full=1`. */
  get pageFull() { return this.classList.contains('dv-page-full'); }
  set pageFull(on) {
    this.classList.toggle('dv-page-full', !!on);
    const b = this.$ && this.$('[data-page-full]');
    if (b) b.setAttribute('aria-pressed', String(!!on));
    this._open._url((h) => { if (on) h.set('full', '1'); else h.delete('full'); });
  }
  /** A link that says full=1 opens the page that way. */
  _syncPageFull(paged) {
    if (!paged || this.hasAttribute('no-url')) return;
    let asked = false;
    try { asked = new URLSearchParams(location.hash.slice(1)).get('full') === '1'; } catch { /* an unreadable link */ }
    if (asked && !this.pageFull) this.classList.add('dv-page-full');
  }
  setPlace(id, to) { return setPlace(this, id, to); }
  previewPlace(id, to) { return previewPlace(this, id, to); }
  movePage(id, index) { return moveOnPage(this, id, index); }
  stepPage(id, delta) { return stepOnPage(this, id, delta); }
  showOnPage(id, on = true) { return showOnPage(this, id, on); }

  // ------------------------------------------------------------------ menus
  _pop(button, html, bind, cls = '') {
    const pop = this.$('.dv-pop');
    if (!pop.hidden && pop._for === button) { this.closeMenu(); return; }
    pop.className = cls ? `dv-pop ${cls}` : 'dv-pop';
    pop.innerHTML = html;
    pop.hidden = false;
    pop._for = button;
    const b = button.getBoundingClientRect(), host = this.getBoundingClientRect();
    const left = Math.max(8, Math.min(b.left - host.left, host.width - Math.min(380, host.width - 16) - 8));
    pop.style.left = left + 'px';
    pop.style.top = b.bottom - host.top + 6 + 'px';
    button.setAttribute('aria-expanded', 'true');
    if (bind) bind(pop);
    const first = pop.querySelector('select, input, button');
    if (first) first.focus();
  }

  closeMenu() {
    const pop = this.$('.dv-pop');
    if (!pop) return;
    if (pop._for) pop._for.setAttribute('aria-expanded', 'false');
    pop.hidden = true;
    pop._for = null;
    pop._back = null;
  }

  /** Open a toolbar menu by name: layout, group, sort, filter, properties, save, more (the rail's "Edit" uses it);
      under toolbar="bar" also views, settings, query, add-view (§15), each anchored to the bar's own controls. */
  openMenu(name) {
    if (this._barUi && this._barUi.openMenu(name)) return;
    const b = this.$(`[data-menu="${name}"]`);
    if (b) { this.closeMenu(); this._openMenu(b); }
  }

  _refreshPop() {
    const pop = this.$('.dv-pop');
    if (pop.hidden || !pop._for) return;
    const button = pop._for;
    pop.hidden = true;
    pop._for = null;
    this._openMenu(button, { name: pop._name || button.dataset.menu });
  }

  _options(selected, { none = null, numeric = false } = {}) {
    const props = this._model.columns;
    // WHY the selected one even when hidden: a view may draw a property the table hides (the gallery's photo), and the
    // menu must say what the view does, not "none"
    const list = Object.values(props).filter((p) => (!p.hidden || p.offered || p.id === selected) && (!numeric || p.type === 'number'));
    return (none ? `<option value="">${esc(none)}</option>` : '') + list.map((p) => `<option value="${esc(p.id)}"${p.id === selected ? ' selected' : ''}>${esc(p.label)}</option>`).join('');
  }

  /** The current view's own settings (its plugin's options), as form rows bound to view keys. */
  _optionRows() {
    const plugin = viewPlugin(this.view.type);
    const decl = plugin && this._pluginType === this.view.type && this._pluginOptions();
    if (!decl || !decl.length) return '';
    const v = this.view;
    return decl.map((o, i) => {
      const cur = getPath(v, o.key);
      const name = esc(o.displayName || o.key);
      if (o.type === 'property') return `<label>${name} <select data-opt="${i}">${this._options(cur, { none: o.none || 'none', numeric: o.filter === 'number' })}</select></label>`;
      if (o.type === 'dropdown') return `<label>${name} <select data-opt="${i}">${Object.entries(o.options || {}).map(([val, text]) => `<option value="${esc(val)}"${String(cur ?? o.default ?? '') === val ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`;
      // a toggle's own isOn when one value of its key is not "on" (the table's wrap: a column list is not every cell)
      if (o.type === 'toggle') return `<label>${name} <input type="checkbox" data-opt="${i}"${(o.isOn ? o.isOn(cur ?? o.default) : (cur ?? o.default)) ? ' checked' : ''}></label>`;
      // a slider shows its value (or what unset means, `none`: "no cap"), as Obsidian's settings sliders do
      if (o.type === 'slider') return `<label>${name} <span class="dv-opt-slider"><input type="range" data-opt="${i}" min="${o.min ?? 0}" max="${o.max ?? 100}" step="${o.step ?? 1}" value="${esc(cur ?? o.default ?? o.min ?? 0)}"><output>${esc(cur ?? o.none ?? o.default ?? o.min ?? 0)}</output></span></label>`;
      return `<label>${name} <input data-opt="${i}" value="${esc(Array.isArray(cur) ? cur.join(', ') : cur ?? '')}" placeholder="${esc(o.placeholder || '')}"></label>`;
    }).join('');
  }

  _pluginOptions() {
    if (this._viewOptions && this._viewOptionsFor === this.view.type) return this._viewOptions;
    const plugin = viewPlugin(this.view.type);
    const fn = (plugin && plugin.options) || (this._viewMod && this._viewMod.options) || null;
    this._viewOptionsFor = this.view.type;
    this._viewOptions = typeof fn === 'function' ? fn(clone(this.view), this._model.columns) || [] : fn || [];
    return this._viewOptions;
  }

  _bindOptions(pop, refresh = () => this._refreshPop()) {
    const decl = this._viewOptions || [];
    pop.querySelectorAll('input[type=range][data-opt]').forEach((input) => input.addEventListener('input', () => {
      const out = input.parentElement.querySelector('output');
      if (out) out.textContent = input.value;
    }));
    pop.querySelectorAll('[data-opt]').forEach((input) => input.addEventListener('change', () => {
      const o = decl[Number(input.dataset.opt)];
      let value = input.type === 'checkbox' ? input.checked : input.value;
      // a numeric dropdown may also carry a property (the table's freeze: <property>, §28): that one stays a name
      if ((o.type === 'slider' || o.number) && value !== '' && !Number.isNaN(Number(value))) value = Number(value);
      if (o.type === 'multitext') value = String(value).split(',').map((s) => s.trim()).filter(Boolean);
      this.update((x) => setPath(x, o.key, value));
      this._viewOptions = null;
      refresh();
    }));
  }

  /** A toolbar menu's body. By default it pops up under `button`; with `into` ({show(html, bind), refresh(), close()},
      the bar's settings panel) the same body draws there as a sub-page (§15: one implementation of each menu). */
  _openMenu(button, { into = null, name = button && button.dataset.menu } = {}) {
    const show = into ? (html, bind) => into.show(html, bind) : (html, bind) => { this._pop(button, html, bind); this.$('.dv-pop')._name = name; };
    const refresh = into ? () => into.refresh() : () => this._refreshPop();
    const close = into ? () => into.close() : () => this.closeMenu();
    const v = this.view;
    const dir = (g, listed = false) => {
      const cur = g ? g.direction || (listed ? '' : 'ASC') : 'ASC';
      const opts = [...(listed ? [['', 'dataset order']] : []), ['ASC', 'A → Z, 0 → 9'], ['DESC', 'Z → A, 9 → 0']];
      return `<select data-k="dir">${opts.map(([val, text]) => `<option value="${val}"${val === cur ? ' selected' : ''}>${text}</option>`).join('')}</select>`;
    };
    const level = (g, k) => (g && g.property ? (k ? { property: g.property, direction: k } : { property: g.property }) : undefined);
    // a date's grain (`by:`, docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail)): offered when the level
    // groups a date property; Notion's "Group by date: day, week, month, year"
    const grains = [['', 'each date'], ['day', 'day'], ['week', 'week (from Monday)'], ['month', 'month'], ['quarter', 'quarter'], ['year', 'year']];
    const grain = (g, k) => {
      const p = g && this._model.columns[g.property];
      if (!p || (p.type !== 'date' && !g.by)) return '';
      return `<label>Dates by <select data-k="${k}">${grains.map(([val, text]) => `<option value="${val}"${val === (g.by || '') ? ' selected' : ''}>${text}</option>`).join('')}</select></label>`;
    };
    // PEP 0020: a level of text or lists can nest; the menu keeps a human and an agent on the same grammar
    const nest = (g, k) => {
      const p = g && this._model.columns[g.property];
      if (!p || g.by || g.bins || p.type === 'date' || p.type === 'number' || !G.viewPath({ type: v.type }, { path: 'dotted' })) return '';
      const cur = g.path === undefined || g.path === null ? '' : String(g.path);
      const opts = [['', 'whole values'], ['dotted', 'dotted paths'], ...(cur && cur !== 'dotted' ? [[cur, `paths split at ${cur}`]] : [])];
      return `<label>Nest <select data-k="${k}">${opts.map(([val, text]) => `<option value="${esc(val)}"${val === cur ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`;
    };
    if (name === 'layout') {
      const types = listViews().filter((t) => t.status !== 'planned');
      this._viewOptions = null;
      const rows = this._optionRows();
      show(`<h4>Layout</h4>
        <div class="dv-seg">${types.map((t) => `<button class="dv-btn${v.type === t.type ? ' dv-on' : ''}" data-type="${esc(t.type)}">${esc(t.name)}</button>`).join('')}</div>
        ${rows ? `<h5>${esc((viewPlugin(v.type) || {}).name || v.type)} settings</h5>${rows}` : ''}`, (pop) => {
        pop.querySelectorAll('[data-type]').forEach((b) => b.addEventListener('click', () => {
          this.update((x) => { x.type = b.dataset.type; if (x.type === 'pivot' && !x.splitBy) x.splitBy = []; });
          this._viewOptions = null;
          // the new view's options arrive with its code; reopen once it has drawn
          this.addEventListener('data-views-render', () => refresh(), { once: true });
          refresh();
        }));
        this._bindOptions(pop, refresh);
      });
    } else if (name === 'rollup') {
      // Roll-up (CONTRACT §16): tick the dimensions to keep; every other one is aggregated, per column
      const props = this._model.columns;
      const dims = G.rollupDims(v, props);
      const keep = v.rollup ? G.rollupKeep(v, props) : dims;
      const locked = new Set([v.groupBy, v.subGroupBy].filter(Boolean).map((g) => g.property).concat(v.type === 'pivot' ? v.splitBy || [] : []));
      const nums = v.type === 'pivot' ? [v.value && v.value.property].filter((id) => id && props[id])
        : (v.order && v.order.length ? v.order : Object.keys(props)).filter((id) => props[id] && props[id].type === 'number' && !props[id].hidden);
      const aggs = [['median', 'median'], ['mean', 'mean'], ['min', 'min'], ['max', 'max'], ['count', 'count'], ['spread', 'spread (max − min)']];
      const aggOf = (id) => { const a = v.rollup && v.rollup.agg && v.rollup.agg[id]; const n = G.summaryName(a); return n === 'Average' ? 'mean' : (n || 'Median').toLowerCase(); };
      // WHY show/refresh, not _pop: under the bar this menu is View settings' Roll up page (toolbar/settings.js `into`)
      show(`<h4>Roll up</h4><p class="dv-hint">Keep the dimensions you want to see; every other one is aggregated. Click a rolled-up row or cell for the rows behind it.</p>
        <ul class="dv-rollup-dims">${dims.map((d) => `<li><label><input type="checkbox" data-dim="${esc(d)}"${keep.includes(d) ? ' checked' : ''}${locked.has(d) ? ' disabled title="Used to group or split: always kept"' : ''}> ${esc(props[d].label)}</label></li>`).join('')}</ul>
        ${nums.length ? `<h5>Aggregate</h5>${nums.map((id) => `<label>${esc(props[id].label)} <select data-agg="${esc(id)}">${aggs.map(([k, t]) => `<option value="${k}"${aggOf(id) === k ? ' selected' : ''}>${t}</option>`).join('')}</select></label>`).join('')}` : ''}
        <div class="dv-seg"><button class="dv-btn" data-roll="none">Every row (no roll-up)</button></div>`, (pop) => {
        const write = () => this.update((x) => {
          const kept = [...pop.querySelectorAll('[data-dim]')].filter((c) => c.checked).map((c) => c.dataset.dim);
          const agg = {};
          pop.querySelectorAll('[data-agg]').forEach((sel) => { if (sel.value !== 'median') agg[sel.dataset.agg] = sel.value; });
          const prev = x.rollup || {};
          if (kept.length === dims.length && !Object.keys(agg).length) { delete x.rollup; return; }
          x.rollup = { keep: kept, ...(Object.keys(agg).length ? { agg } : {}), ...(prev.dims ? { dims: prev.dims } : {}) };
        });
        pop.querySelectorAll('[data-dim], [data-agg]').forEach((c) => c.addEventListener('change', () => { write(); refresh(); }));
        pop.querySelector('[data-roll=none]').addEventListener('click', () => { this.update((x) => { delete x.rollup; }); refresh(); });
      });
    } else if (name === 'group') {
      // with `grouping: <id>` the menu shows that entry's levels; changing them leaves the grouping for the view's own
      const v = G.effectiveView(this.view);
      show(`<h4>Group</h4>
        <label>Group by <select data-k="g0">${this._options(v.groupBy && v.groupBy.property, { none: 'none' })}</select></label>
        ${grain(v.groupBy, 'b0')}${nest(v.groupBy, 'p0')}<label class="dv-dir">${dir(v.groupBy, true).replace('data-k="dir"', 'data-k="d0"')}</label>
        <label>Sub-group by <select data-k="g1">${this._options(v.subGroupBy && v.subGroupBy.property, { none: 'none' })}</select></label>
        ${grain(v.subGroupBy, 'b1')}${nest(v.subGroupBy, 'p1')}<label class="dv-dir">${dir(v.subGroupBy, true).replace('data-k="dir"', 'data-k="d1"')}</label>
        <label>Groups start <select data-k="fold"><option value="open"${(v.fold || 'open') === 'open' ? ' selected' : ''}>unfolded</option><option value="closed"${v.fold === 'closed' ? ' selected' : ''}>folded</option></select></label>`, (pop) => {
        // a level keeps its grain (and gaps) while it groups the same property; a new property starts without one
        const timed = (was, next, k) => {
          const b = pop.querySelector(`[data-k=${k}]`);
          return next && was && was.property === next.property && b && b.value ? { ...next, by: b.value, ...(was.gaps ? { gaps: was.gaps } : {}) } : next;
        };
        // a level keeps its path while it groups the same property, as it keeps its grain
        const nested = (was, next, k) => {
          const s = pop.querySelector(`[data-k=${k}]`);
          return next && was && was.property === next.property && s && s.value ? { ...next, path: s.value } : next;
        };
        pop.querySelectorAll('select').forEach((s) => s.addEventListener('change', () => {
          this.update((x) => {
            const g0 = pop.querySelector('[data-k=g0]').value, g1 = pop.querySelector('[data-k=g1]').value;
            x.groupBy = nested(x.groupBy, timed(x.groupBy, g0 ? level({ property: g0 }, pop.querySelector('[data-k=d0]').value) : undefined, 'b0'), 'p0');
            x.subGroupBy = nested(x.subGroupBy, timed(x.subGroupBy, g0 && g1 && g1 !== g0 ? level({ property: g1 }, pop.querySelector('[data-k=d1]').value) : undefined, 'b1'), 'p1');
            x.fold = pop.querySelector('[data-k=fold]').value;
            if (x.grouping !== undefined) { if (G.groupingOf(x)) x.tiles = G.groupingOf(x).tiles; delete x.grouping; }
          });
          // a new property may be a date (or no longer one): the grain picker follows it
          if (s.dataset.k === 'g0' || s.dataset.k === 'g1') this._refreshPop();
        }));
      });
    } else if (name === 'sort') {
      const rules = v.sort || [];
      show(`<h4>Sort</h4>${rules.map((s, i) => `<div class="dv-rule" data-i="${i}"><select data-k="p">${this._options(s.property)}</select>${dir(s)}<button class="dv-btn dv-x" data-del="${i}" aria-label="Remove sort">✕</button></div>`).join('') || '<p class="dv-hint">No sort: rows keep the dataset order.</p>'}
        <button class="dv-btn" data-add>+ Add a sort</button><p class="dv-hint">Or click a column header; drag headers to reorder.</p>`, (pop) => {
        const sync = () => this.update((x) => { x.sort = [...pop.querySelectorAll('.dv-rule')].map((el) => ({ property: el.querySelector('[data-k=p]').value, direction: el.querySelector('[data-k=dir]').value })); });
        pop.querySelectorAll('select').forEach((s) => s.addEventListener('change', sync));
        pop.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => { this.update((x) => { x.sort.splice(Number(b.dataset.del), 1); }); refresh(); }));
        pop.querySelector('[data-add]').addEventListener('click', () => { this.update((x) => { x.sort = [...(x.sort || []), { property: (x.order || Object.keys(this._model.columns))[0], direction: 'ASC' }]; }); refresh(); });
      });
    } else if (name === 'filter') {
      const list = G.filterList(v.filters);
      const all = toRail(this._filters);
      const allList = G.filterList(this._filters);
      const ops = [['==', 'is'], ['!=', 'is not'], ['contains', 'contains'], ['>', '>'], ['<', '<'], ['>=', '≥'], ['<=', '≤'], ['isEmpty', 'is empty'], ['notEmpty', 'is not empty']];
      const row = (f, i, scope) => `<div class="dv-rule"><code>${esc(typeof f === 'string' ? f : JSON.stringify(f))}</code><button class="dv-btn dv-x" data-del="${i}" data-scope="${scope}" aria-label="Remove filter">✕</button></div>`;
      // §40: by hand, with no expression: pick a column, get the control that fits it
      const byHand = this._hasSwitch() ? `<label>Filter by <select data-filter-by aria-label="Filter by a column">${this._options(null, { none: 'a column…' })}</select></label>` : '';
      show(`<h4>Filter</h4>${byHand}
        <h5>This view</h5>${list.map((f, i) => row(f, i, 'view')).join('') || '<p class="dv-hint">No filter of its own.</p>'}
        <div class="dv-rule dv-new"><select data-k="p">${this._options(null)}</select><select data-k="op">${ops.map(([o, t]) => `<option value="${o}">${t}</option>`).join('')}</select><input data-k="val" placeholder="value" aria-label="Filter value"><button class="dv-btn" data-add>Add</button></div>
        <p class="dv-hint">Each filter is a Bases expression; all must hold. Type your own:</p>
        <div class="dv-rule"><input data-k="expr" placeholder='peak_torque > 10 && brand != "KST"' aria-label="Filter expression"><button class="dv-btn" data-addexpr>Add</button></div><p class="dv-err" hidden></p>
        <h5>All views${Object.keys(all.facets).length ? ' (the rail edits these)' : ''}</h5>${allList.map((f, i) => row(f, i, 'all')).join('') || '<p class="dv-hint">None: every row.</p>'}`, (pop) => {
        const by = pop.querySelector('[data-filter-by]');
        if (by) by.addEventListener('change', () => { if (by.value) openColumnFilter(this, by.value, button && button.isConnected ? button : this.$('.dv-stage')); });
        const err = pop.querySelector('.dv-err');
        const add = (expr) => {
          try { G.compileExpression(expr); } catch (e) { err.hidden = false; err.textContent = e.message; return; }
          this.update((x) => { x.filters = { and: [...G.filterList(x.filters), expr] }; });
          refresh();
        };
        pop.querySelector('[data-add]').addEventListener('click', () => {
          const p = pop.querySelector('[data-k=p]').value, op = pop.querySelector('[data-k=op]').value, raw = pop.querySelector('[data-k=val]').value.trim();
          const ref = /^[A-Za-z_]\w*$/.test(p) ? p : `note[${JSON.stringify(p)}]`;
          const lit = raw !== '' && !Number.isNaN(Number(raw)) ? raw : JSON.stringify(raw);
          add(op === 'isEmpty' ? `${ref}.isEmpty()` : op === 'notEmpty' ? `!${ref}.isEmpty()` : op === 'contains' ? `${ref}.contains(${JSON.stringify(raw)})` : `${ref} ${op} ${lit}`);
        });
        pop.querySelector('[data-addexpr]').addEventListener('click', () => add(pop.querySelector('[data-k=expr]').value.trim()));
        pop.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => {
          if (b.dataset.scope === 'all') {
            const l = G.filterList(this._filters);
            l.splice(Number(b.dataset.del), 1);
            this.filters = l.length ? { and: l } : undefined;
          } else this.update((x) => { const l = G.filterList(x.filters); l.splice(Number(b.dataset.del), 1); x.filters = l.length ? { and: l } : undefined; });
          refresh();
        }));
      });
    } else if (name === 'properties') {
      const props = this._model.columns;
      const order = (v.order || []).filter((id) => props[id]);
      const hidden = Object.keys(props).filter((id) => !order.includes(id) && (!props[id].hidden || props[id].offered));
      const isColumn = columnIds(v, props);
      const kinds = (p) => (p.type === 'number' ? ['number', 'bar', ...(p.values ? ['dist', 'sparkline'] : [])] : ['text', 'badge']);
      const row = (id, on) => {
        const p = props[id];
        const d = (v.display && v.display[id]) || p.display || (p.type === 'number' ? 'number' : 'text');
        return `<li class="dv-prop" draggable="${on}" data-id="${esc(id)}"><span class="dv-grip" aria-hidden="true">⋮⋮</span><label><input type="checkbox"${on ? ' checked' : ''}> ${esc(p.label)}</label>
          <select data-k="display" aria-label="Display ${esc(p.label)} as">${kinds(p).map((k) => `<option${k === d ? ' selected' : ''}>${k}</option>`).join('')}</select>
          ${id === this._data.titleProperty ? '' : `<select data-k="inspector" aria-label="${esc(p.label)} in the inspector" title="In the inspector (the checkbox is the row)">${[['show', 'Show'], ['hideEmpty', 'If set'], ['hide', 'Hide']].map(([k, word]) => `<option value="${k}"${k === wordOf(v, id, isColumn.includes(id)) ? ' selected' : ''}>${word}</option>`).join('')}</select>`}
          ${on ? `<button class="dv-btn dv-x" data-move="-1" aria-label="Move ${esc(p.label)} left">↑</button><button class="dv-btn dv-x" data-move="1" aria-label="Move ${esc(p.label)} right">↓</button>` : ''}</li>`;
      };
      const pivotNote = v.type === 'pivot' ? '<p class="dv-hint">In a pivot, the checked properties are the row labels.</p>' : '';
      show(`<h4>Properties</h4>${pivotNote}<p class="dv-hint">The box is the row; Show, If set and Hide are the inspector.</p><ul class="dv-props">${order.map((id) => row(id, true)).join('')}${hidden.map((id) => row(id, false)).join('')}</ul>
        <div class="dv-seg"><button class="dv-btn" data-all="1">Show all</button><button class="dv-btn" data-all="0">Hide all</button></div>`, (pop) => {
        const read = () => [...pop.querySelectorAll('.dv-prop')].filter((li) => li.querySelector('input').checked).map((li) => li.dataset.id);
        pop.querySelectorAll('.dv-prop input').forEach((c) => c.addEventListener('change', () => { this.update((x) => { x.order = read(); }); refresh(); }));
        pop.querySelectorAll('[data-k=inspector]').forEach((s) => s.addEventListener('change', () => setVisibility(this, s.closest('.dv-prop').dataset.id, s.value)));
        pop.querySelectorAll('[data-k=display]').forEach((s) => s.addEventListener('change', () => this.update((x) => {
          const id = s.closest('.dv-prop').dataset.id;
          const base = props[id].display || (props[id].type === 'number' ? 'number' : 'text');
          x.display = { ...(x.display || {}) };
          if (s.value === base) delete x.display[id]; else x.display[id] = s.value;
          if (!Object.keys(x.display).length) delete x.display;
        })));
        pop.querySelectorAll('[data-move]').forEach((b) => b.addEventListener('click', () => {
          const id = b.closest('.dv-prop').dataset.id;
          this.update((x) => { const o = x.order; const i = o.indexOf(id), j = i + Number(b.dataset.move); if (j >= 0 && j < o.length) { o.splice(i, 1); o.splice(j, 0, id); } });
          refresh();
        }));
        let drag = null;
        pop.querySelectorAll('.dv-prop[draggable=true]').forEach((li) => {
          li.addEventListener('dragstart', (e) => { drag = li.dataset.id; e.dataTransfer.effectAllowed = 'move'; });
          li.addEventListener('dragover', (e) => { e.preventDefault(); li.classList.add('dv-over'); });
          li.addEventListener('dragleave', () => li.classList.remove('dv-over'));
          li.addEventListener('drop', (e) => { e.preventDefault(); if (drag && drag !== li.dataset.id) { this.moveProperty(drag, li.dataset.id); refresh(); } });
        });
        pop.querySelectorAll('[data-all]').forEach((b) => b.addEventListener('click', () => {
          this.update((x) => { x.order = b.dataset.all === '1' ? [...(x.order || []), ...Object.keys(props).filter((id) => !(x.order || []).includes(id) && (!props[id].hidden || props[id].offered))] : (x.order || []).slice(0, 1); });
          refresh();
        }));
      });
    } else if (name === 'save') {
      const mine = this.origin.kind === 'user';
      show(`<h4>Save this view</h4>${mine ? `<button class="dv-btn dv-primary" data-update>Update “${esc(this.origin.name)}”</button><p class="dv-hint">or save a copy:</p>` : '<p class="dv-hint">The built-in views stay as they are. Save yours under a new name (kept in this browser):</p>'}
        <div class="dv-rule"><input data-k="name" value="${esc(this.origin.name + ' (mine)')}" aria-label="View name"><button class="dv-btn dv-primary" data-new>Save as new view</button></div>`, (pop) => {
        const upd = pop.querySelector('[data-update]');
        if (upd) upd.addEventListener('click', () => { this._saveUser(this.origin.name, this.view); close(); });
        pop.querySelector('[data-new]').addEventListener('click', () => { const n = pop.querySelector('[data-k=name]').value.trim(); if (n) { this._saveUser(n, this.view); close(); } });
      });
    } else if (name === 'more') {
      const yaml = this.viewYaml();
      const index = this._base.views.findIndex((p) => p.name === this.origin.name);
      const whole = this.baseText && this.origin.kind === 'preset' && index >= 0 ? () => replaceViewInText(this.baseText, index, this.view) : null;
      // CONTRACT §34: Add to dashboard… heads the ⋯ menu (Amazon's "Add to List" beside the item)
      show(`<div class="dv-seg dv-add-row"><button class="dv-btn" data-add-dashboard aria-haspopup="dialog">Add to dashboard…</button></div>
        <h4>This view as a .base entry</h4><pre class="dv-yaml">${esc(yaml)}</pre>
        <div class="dv-seg"><button class="dv-btn" data-copy>Copy</button>${whole ? '<button class="dv-btn" data-copyfile>Copy the whole file</button>' : ''}${this.origin.kind === 'user' ? '<button class="dv-btn" data-delete>Delete this view</button>' : ''}<button class="dv-btn" data-reset>Reset to “${esc(this.origin.name)}”</button></div>
        <p class="dv-hint">Paste it into the .base file, or tell your agent "make this the default preset".</p>`, (pop) => {
        const copy = (text, b) => { try { navigator.clipboard.writeText(text); b.textContent = 'Copied'; } catch { b.textContent = 'Select the text to copy'; } };
        pop.querySelector('[data-add-dashboard]').addEventListener('click', () => {
          // under the bar the Display button is redrawn as View settings closes: the picker finds it when it places itself
          const anchor = this._barUi ? () => this.querySelector('.dv-bar [data-bar=display]') : this.$('[data-menu="more"]');
          close();
          this.addToDashboard({ kind: 'view' }, { anchor });
        });
        pop.querySelector('[data-copy]').addEventListener('click', (e) => copy(yaml, e.target));
        const cf = pop.querySelector('[data-copyfile]');
        if (cf) cf.addEventListener('click', (e) => copy(whole(), e.target));
        const del = pop.querySelector('[data-delete]');
        if (del) del.addEventListener('click', () => { this._deleteUser(this.origin.name); close(); });
        pop.querySelector('[data-reset]').addEventListener('click', () => { this._select(this.origin.kind, this.origin.view, null, { fresh: true }); close(); });
      });
    }
  }

  /** The current view as a .base `views:` entry. */
  viewYaml() { return G.toBaseYaml(this.view); }

  // ------------------------------------------------------------------ add to dashboard (docs/CONTRACT.md §34)
  /** The panel a reader adds to a dashboard from this view, as appendPanel() takes it:
      {kind, title, view, dataset: {name, data, label?}, properties?, h?, t?}. What the reader sees is what is added:
      the view's entry with its own filters AND the all-views filter (the rail and the query's clauses; in a dashboard
      the panel's rail, the other panels' selections and the links) AND the words searched AND "Show only selected",
      and the legend's hidden series. target: {kind: 'view'}; {kind: 'series', name, names?} (the view with every other
      series of its legend hidden); {kind: 'value', group: i} (a KPI card: the view narrowed to its group);
      {kind: 'value', id, property} (a record's cell: a KPI card of a number, else a record of that one field). t: the
      instant it stands at (seconds; "At this moment"). Throws when the rows have no file a dashboard could read. */
  panelSpec(target = { kind: 'view' }, { t } = {}) {
    if (!this._started || !this._model || !this.view) throw new Error('the view has not drawn yet');
    const ctx = this.dashboardPanel && typeof this.dashboardPanel === 'object' ? this.dashboardPanel : null;
    // in a dashboard, the file its .base declares for this panel's dataset (dashboardPanel.file), else the file the rows
    // were read from. WHY (RobotDx PEP 0001 §17.1, ask 2): a host may hand one dataset object to several declared files,
    // so the object's url is whichever binding made it first, and the panel saved from another board read nobody's rows
    const declared = ctx && typeof ctx.file === 'string' && ctx.file ? this._siteFile(ctx.file) : null;
    const file = declared || this._dataFile();
    if (!file) throw new Error('This view\'s rows were handed in by the page, not read from a file, so a dashboard has nothing to read.');
    const columns = this._model.columns;
    const props = labelled(this._data, this._base);
    const rows = this._data.rows;
    // the view as written, with the reader's changes: keys only this page has go (a dashboard's resolved style, a preset
    // selection, the dataset this page names it by)
    const v = clone(this.view);
    for (const k of Object.keys(v)) if (k.startsWith('_')) delete v[k];
    delete v.from;
    delete v.selected;
    if (ctx) {
      const written = (ctx.views || []).find((x) => x && x.name === this.view.name);
      if (written && written.style !== undefined) v.style = clone(written.style); else delete v.style;
    }
    let words;
    if (this.query && this.query.trim()) {
      const visible = (v.order && v.order.length ? v.order : Object.keys(props)).filter((p) => props[p] && !props[p].pivot);
      const keep = new Set(search(rows, props, v, this.query).map((r) => String(r.id)));
      words = searchClause(this.query, visible);
      let test = null;
      try { test = words ? G.compileFilters(words) : null; } catch { test = null; }
      // WHY the ids when they differ: a list property searches its joined text, which .contains() cannot say
      if (!test || !rows.every((r) => !!test(r) === keep.has(String(r.id)))) words = inClause('id', [...keep]);
    }
    const only = this._onlySelected && this._selection.ids.size ? inClause('id', [...this._selection.ids]) : undefined;
    v.filters = andFilters(this.view.filters, this._filters, words, only);
    if (v.filters === undefined) delete v.filters;
    if (this._hidden.length) v.hiddenSeries = [...this._hidden]; else delete v.hiddenSeries;
    const kind = (target && target.kind) || 'view';
    let view = v, title = v.name || 'View';
    if (kind === 'series') {
      const name = String(target.name);
      const names = Array.isArray(target.names) && target.names.length ? target.names.map(String) : [name];
      // the legend's "show only this one" (Alt + click), kept: a series a filter took off this legend stays hidden
      v.hiddenSeries = hiddenAfter(names, this._hidden, names.map((n) => n === name));
      if (!v.hiddenSeries.length) delete v.hiddenSeries;
      title = v.name = `${v.name || 'View'} · ${name}`;
    } else if (kind === 'value' && target.group !== undefined) {
      const g = this._model.groups && this._model.groups[Number(target.group)];
      if (!g) throw new Error('That card is not drawn any more.');
      v.filters = andFilters(v.filters, this._groupClause(g));
      title = v.name = `${v.name || 'View'} · ${groupLabel(columns, g.property, g.key)}`;
    } else if (kind === 'value') {
      const row = this.row(target.id);
      if (!row) throw new Error(`No row has the id ${target.id}.`);
      const col = columns[target.property] || props[target.property] || { label: target.property };
      const tp = this._data.titleProperty;
      const named = tp && !isEmpty(G.cellValue(row[tp])) ? G.cellValue(row[tp]) : row.id;
      title = `${named} · ${col.label || target.property}`;
      const which = `id == ${lit(row.id)}`;
      view = col.type === 'number'
        ? { type: 'kpi', name: title, filters: which, kpi: { label: col.label || target.property, value: { property: target.property } } }
        : { type: 'record', name: title, filters: which, order: [target.property] };
    }
    const spec = { kind, title, view, dataset: { name: (ctx && ctx.dataset) || this._fileStem(file) || 'data', data: file } };
    if (ctx && ctx.label) spec.dataset.label = ctx.label;
    // the .base's properties: entries for this data's columns (labels a dashboard adds where it has none of its own)
    const entries = Object.entries((this._base && this._base.properties) || {}).filter(([p, e]) => this._data.properties && this._data.properties[p] && e && typeof e === 'object');
    if (entries.length) spec.properties = Object.fromEntries(entries.map(([p, e]) => [p, clone(e)]));
    if (ctx && isNum(ctx.h) && kind !== 'value') spec.h = ctx.h;
    if (isNum(t)) spec.t = Math.round(t * 1000) / 1000;
    return spec;
  }

  /** A model group as a filter: its value (a date bucket's span, "is empty" for no value, contains for a list), checked
      against the rows it holds; the rows' ids when it says other rows (numeric bins, a key the grammar cannot write). */
  _groupClause(g) {
    const p = g.property, col = (this._model.columns[p]) || {};
    let clause = null;
    if (g.key === null || g.key === undefined || g.key === '') clause = `${ref(p)}.isEmpty()`;
    else if (g.by) {
      const a = G.bucketStart(g.key, g.by), next = G.nextBucket(g.key, g.by), b = next && G.bucketStart(next, g.by);
      if (a && b) clause = `${ref(p)} >= ${lit(a)} && ${ref(p)} < ${lit(b)}`;
    } else if (col.type === 'list') clause = `${ref(p)}.contains(${lit(g.key)})`;
    else clause = `${ref(p)} == ${lit(g.key)}`;
    const want = new Set((g.rows || []).map((r) => String(r.id)));
    let test = null;
    try { test = clause ? G.compileFilters(clause) : null; } catch { test = null; }
    const same = test && this._model.rows.every((r) => !!test(r) === want.has(String(r.id)));
    return same ? clause : inClause('id', [...want]);
  }

  /** The data file as a dashboard names it: its path from the site's root when it is this page's origin, else its URL;
      null when the rows came from script with no url. */
  _dataFile() { return this._dataUrl ? this._siteFile(this._dataUrl) : null; }

  /** A file's URL as a dashboard names it: its path from the site's root on this page's origin, else the URL. */
  _siteFile(href) {
    try {
      const u = new URL(href, document.baseURI);
      return u.origin === location.origin ? u.pathname + u.search : u.href;
    } catch { return null; }
  }

  _fileStem(file) {
    const last = String(file).split(/[?#]/)[0].split('/').pop() || '';
    try { return decodeURIComponent(last).replace(/\.[^.]+$/, ''); } catch { return last.replace(/\.[^.]+$/, ''); }
  }

  /** Open the picker for `target` (panelSpec's): the host's dashboards, New dashboard…, and "At this moment" when the
      page has time. anchor: the element it opens beside, a point {x, y}, or a function that finds the element. */
  addToDashboard(target = { kind: 'view' }, { anchor = null } = {}) {
    this.closeMenu();
    let spec = null, error = null;
    try { spec = this.panelSpec(target); } catch (err) { error = err.message; }
    const kind = (target && target.kind) || 'view';
    const n = this._model ? this._model.rows.length : 0;
    const what = !spec ? '' : kind === 'view' ? `“${spec.title}” · ${n.toLocaleString('en-US')} row${n === 1 ? '' : 's'}` : `“${spec.title}”`;
    // "At this moment": the page's time, when it has one (a dashboard's clock, or the page's, with a span)
    let moment = null;
    // clockFor: an ancestor's (a <data-dashboard>'s, a pinned panel's), else the page's one
    const clock = clockFor(this);
    if (clock && clock.start !== null && clock.end !== null && isNum(clock.t)) {
      const t = Math.round(clock.t * 1000) / 1000;
      // written as the playback bar writes t (fmtTime: a wall-clock time on a live clock's Unix seconds), the exact
      // seconds one step away. WHY (RobotDx PEP 0001 §17.1, ask 5): "t = 1792631514.923 s" said nothing a reader could place
      moment = { t, label: fmtTime(t), exact: `t = ${t} s` };
    }
    return openPicker(this, { target, anchor: anchor || this, what, moment, error });
  }

  /** The item under a right-click or key: a legend's series, a KPI card, a field of the record peek; null otherwise. */
  _itemAt(t) {
    if (!t || !t.closest) return null;
    const mine = (node) => node && node.closest('data-views') === this;
    const key = t.closest('.dv-legend-key[data-legend-series]');
    if (mine(key)) {
      const box = key.closest('.dv-legend') || key.parentElement;
      const names = [...box.querySelectorAll('.dv-legend-key[data-legend-series]')].map((b) => b.dataset.legendSeries);
      const name = key.dataset.legendSeries;
      // a legend redraws its entries: the menu and the picker find this one again by its series (and its legend's place)
      const nth = [...this.querySelectorAll('.dv-legend')].indexOf(box);
      const find = () => { const b = this.querySelectorAll('.dv-legend')[nth]; return (b && [...b.querySelectorAll('.dv-legend-key')].find((k) => k.dataset.legendSeries === name)) || null; };
      return { el: key, find, items: [
        // the legend's own Alt + click, so the hidden set, the URL and the event are the legend's (../legend.js)
        { label: `Show only “${name}”`, attr: 'data-legend-only', run: () => (find() || key).dispatchEvent(new MouseEvent('click', { bubbles: true, altKey: true, detail: 1 })) },
        { label: `Add “${name}” to dashboard…`, attr: 'data-add-dashboard', run: (at) => this.addToDashboard({ kind: 'series', name, names }, { anchor: at }) },
      ] };
    }
    const card = t.closest('data-kpi[data-i]');
    if (mine(card) && card.closest('.dv-stage') && this.view && this.view.type === 'kpi') {
      const groups = this._model && this._model.groups;
      const i = Number(card.dataset.i);
      if (groups && groups.length && groups[i]) {
        const label = groupLabel(this._model.columns, groups[i].property, groups[i].key);
        return { el: card, find: () => this.querySelector(`.dv-stage data-kpi[data-i="${i}"]`), items: [{ label: `Add “${label}” to dashboard…`, attr: 'data-add-dashboard', run: (at) => this.addToDashboard({ kind: 'value', group: i }, { anchor: at }) }] };
      }
      return { el: card, find: () => this.querySelector(`.dv-stage data-kpi[data-i="${card.dataset.i}"]`), items: [{ label: 'Add this card to dashboard…', attr: 'data-add-dashboard', run: (at) => this.addToDashboard({ kind: 'view' }, { anchor: at }) }] };
    }
    // CONTRACT §40: a row of the table, in Edit; on a selected row, the whole selection. §46: and where else it opens
    const tr = t.closest('.dv-stage tbody tr[data-id]');
    if (mine(tr) && (this.view.type || 'table') === 'table') {
      const id = tr.dataset.id;
      const items = [];
      // §46: anywhere on the row, as Notion's; a box being typed in keeps the browser's menu (paste, spelling)
      if (t.closest('input, textarea, select, [contenteditable]')) return null;
      // WHY only when the host says a record opens somewhere: with neither hook a table keeps the menu it had (§36, §40: in View, the browser's)
      if (this.row(id) && (typeof this.openElsewhere === 'function' || typeof this.pageRenderer === 'function')) {
        const places = [{ label: 'Side peek', attr: 'data-row-peek', run: () => this.openPeek(id) }];
        const out = typeof this.openElsewhere === 'function' ? this.openElsewhere(this.row(id)) : null;
        if (out && out.href) places.push({ label: out.label, href: out.href, app: true, attr: 'data-row-elsewhere' });
        items.push({ label: 'Open in', items: places, attr: 'data-row-open-in' });
      }
      if (this._editTools()) {
        const ids = this._selection.ids.has(id) ? this.selection : [id];
        if (items.length) items.push({ separator: true });
        items.push({ label: ids.length > 1 ? `Delete ${ids.length} rows` : 'Delete row', attr: 'data-row-delete', run: () => this.deleteRows(ids) });
      }
      if (items.length) return { el: tr, find: () => this.querySelector(`.dv-stage tbody tr[data-id="${CSS.escape(id)}"]`), items };
    }
    const field = t.closest('.dv-peek-field[data-p]');
    // a record's own field: not the records behind a pivot cell or a group, nor a synthetic row (a pivot's)
    if (mine(field) && this._peek && !(this._peek.opts && this._peek.opts.records) && this.row(this._peek.id) === this._peek.row) {
      const p = field.dataset.p;
      const col = (this._model && this._model.columns[p]) || labelled(this._data, this._base)[p] || { label: p };
      const id = this._peek.id;
      return { el: field, find: () => [...this.querySelectorAll('.dv-peek .dv-peek-field')].find((f) => f.dataset.p === p) || null, items: [{ label: `Add “${col.label || p}” to dashboard…`, attr: 'data-add-dashboard', run: (at) => this.addToDashboard({ kind: 'value', id, property: p }, { anchor: at }) }] };
    }
    return null;
  }

  /** A value two or more sources state (CONTRACT §36, the source popover; a view marks it with sourcesAttr): its item —
      {el, find, items, opts}: every source in precedence order, then the element's own items (a peek field's Add to
      dashboard…) — or null. `keyboard`: the menu key on a focused row or card means its first such value. */
  _sourcesAt(t, keyboard) {
    const info = this._precInfo;
    if (!info || !t || !t.closest) return null;
    const mine = (n) => !!n && n.closest('data-views') === this;
    let el = t.closest('[data-src-row]');
    if (!mine(el)) el = keyboard && t.querySelectorAll ? [...t.querySelectorAll('[data-src-row]')].find(mine) || null : null;
    if (!el) return null;
    const id = el.dataset.srcRow, p = el.dataset.srcP;
    const pill = !!t.closest('button.dv-src-dd');
    const shown = this.row(id);
    if (!shown || !isMultiSource(shown[p])) return null;
    if (!this._prec) this._prec = this._readPrec();
    const column = (this._model && this._model.columns[p]) || labelled(this._data, this._base)[p] || { id: p, label: p };
    const tp = this._data.titleProperty;
    const named = tp ? (cellText(shown[tp]) ?? G.cellValue(shown[tp])) : null;
    const title = isEmpty(named) ? String(id) : Array.isArray(named) ? named.join(', ') : String(named);
    // the element the menu started from (its row, card or field: where the focus goes back), found again after a redraw
    // in the same place. WHY the place: the table behind an open peek draws the same row and property, earlier on the page
    const sel = `[data-src-row="${CSS.escape(id)}"][data-src-p="${CSS.escape(p)}"]`;
    const inPeek = !!el.closest('.dv-peek');
    const focusable = (n) => (n.matches('[tabindex]:not([tabindex="-1"])') ? n : n.closest('[tabindex]:not([tabindex="-1"])') || n);
    const find = () => {
      const n = el.isConnected ? el : [...this.querySelectorAll(sel)].find((x) => mine(x) && !!x.closest('.dv-peek') === inPeek);
      if (!n) return null;
      // a pill's menu gives the focus back to the pill
      return (pill && n.querySelector('button.dv-src-dd')) || focusable(n);
    };
    const unit = column.unit ? G.cellValue(shown[column.unit]) : null;
    const menu = sourcesMenu({
      cell: shown[p], view: formulaView(info, this._prec, p), info, id, column, rowUnit: unit, base: this.dataUrl, title,
      rowWide: info.properties.some((q) => q !== p && isMultiSource(shown[q])),
      // one row's pick, then the focus back where it was
      pick: (source) => {
        this.setPrecedence({ ov: { [id]: source } });
        const to = find();
        if (to && to.focus) to.focus({ preventScroll: true });
      },
    });
    if (!menu) return null;
    const own = this._itemAt(el);
    const items = own && own.items.length ? [...menu.items, { separator: true }, ...own.items] : menu.items;
    return { el, find, items, opts: menu.opts };
  }

  /** A value's pill: the menu a right-click on it opens, under the pill. */
  _sourcesMenu(pill) {
    const item = this._sourcesAt(pill, false);
    if (!item) return;
    pill.setAttribute('aria-expanded', 'true');
    const h = openItemMenu(this, pill, item.items, item.opts);
    const close = h.close;
    h.close = (refocus) => { pill.setAttribute('aria-expanded', 'false'); close(refocus); };
  }

  /** A contextmenu or its key on an item: the item menu. Shift + right-click is the browser's own menu; a value two or
      more sources state lists them (CONTRACT §36), and every other value with a source keeps its "where this value
      comes from" menu (§22). True when it opened a menu, or kept the one open. */
  _itemMenu(e) {
    const t = e.target;
    if (!t || !t.closest) return false;
    // CONTRACT §40: a header in Edit: the column's menu, under the header
    // and in View its filter: the one thing a reader may change there, reached with no new mark on the table (§40: View is a read-only
    // table to the byte)
    const head = this._hasSwitch() && t.closest('.dv-stage thead th[data-sort]');
    if (head && !(e.type === 'contextmenu' && e.shiftKey)) {
      if (this._editTools() && head.querySelector('[data-col-menu]')) { e.preventDefault(); openColumnMenu(this, head.dataset.sort, head); return true; }
      if (this._viewOnly()) { e.preventDefault(); openColumnFilter(this, head.dataset.sort, head); return true; }
    }
    const now = performance.now(), last = this._lastItem;
    const live = !!(last && last.handle && last.handle.node.isConnected);
    // the contextmenu a menu key can raise just after it (button 0) belongs to the menu that key opened: swallowed, so
    // the menu keeps its focus and its way back, and no browser menu opens over it (sources.js does the same)
    if (e.type === 'contextmenu' && live && last.key && e.button === 0 && now - last.at < 300) { e.preventDefault(); return true; }
    if (e.type === 'contextmenu' && e.shiftKey) return false;
    const keyboard = e.type !== 'contextmenu';
    const item = this._sourcesAt(t, keyboard) || (t.closest('[data-provenance]') ? null : this._itemAt(t));
    if (!item) return false;
    e.preventDefault();
    // a long-press raises two (sources.js hands its own over, and a browser that has one fires its contextmenu): one menu
    if (!keyboard && live && !last.key && last.el === item.el && now - last.at < 700) return true;
    // a pointer's menu opens where it pressed; a key's beside the item, found again whenever its view redraws it
    const point = !keyboard && (e.clientX || e.clientY) ? { x: e.clientX, y: e.clientY } : item.find;
    this._lastItem = { el: item.el, at: now, key: keyboard, handle: openItemMenu(this, point, item.items, item.opts) };
    return true;
  }

  /** Move a property in the view's order to just before another (the table's header drag uses it). */
  moveProperty(id, before) {
    this.update((x) => {
      const o = (x.order || []).filter((c) => c !== id);
      const at = o.indexOf(before);
      o.splice(at < 0 ? o.length : at, 0, id);
      x.order = o;
    });
  }

  // ------------------------------------------------------------------ user presets and the URL
  _key() { return `data-views/${this._data.id}`; }
  _userViews() { const s = store.get(this._key()); return (s && Array.isArray(s.views) ? s.views : []); }
  _saveUser(name, view) {
    // CONTRACT §37: with a file behind the page a saved view is a view of the file, not of this browser
    if (typeof this.persistView === 'function' && this.origin && this.origin.kind === 'preset') {
      const fresh = { ...clone(view), name };
      const text = typeof this.baseText === 'string' ? this.baseText : stringifyBase({ ...this._base });
      this.baseText = replaceViewInText(text, this._base.views.length, fresh);
      this._base.views.push(clone(fresh));
      this._select('preset', fresh);
      return;
    }
    const list = this._userViews().filter((v) => v.name !== name);
    const saved = { ...clone(view), name };
    list.push(saved);
    store.set(this._key(), { views: list });
    this._select('user', saved);
  }
  _deleteUser(name) {
    store.set(this._key(), { views: this._userViews().filter((v) => v.name !== name) });
    this._select('preset', this.presets[0]);
  }
  /** Rename a user view in place (the bar's Configure view and View settings); it stays open, changes and all. */
  _renameUser(from, to) {
    const list = this._userViews();
    const at = list.findIndex((v) => v.name === from);
    if (at < 0 || !to || list.some((v) => v.name === to)) return false;
    list[at] = { ...list[at], name: to };
    store.set(this._key(), { views: list });
    this._select('user', list[at], { ...clone(this.view), name: to });
    return true;
  }

  /** A view's name in the URL: its slug, made unique ('Brand › form' and 'Brand × form' are both brand-form). */
  _slugOf(kind, name) {
    const all = [...this.presets.map((v) => ['preset', v.name]), ...this._userViews().map((v) => ['user', v.name])];
    const s = slug(name);
    const same = all.filter(([, n]) => slug(n) === s);
    const k = same.findIndex(([kk, n]) => kk === kind && n === name);
    return k > 0 ? `${s}-${k + 1}` : s;
  }

  /** Every rail of the file (the top-level one and each view's `facets:`), as the URL's config: a link carries any
      of them, whichever view it opens on. */
  _railUrl() {
    const props = labelled(this._data, this._base);
    const specs = allSpecs(this._base, props);
    return { props, known: railProperties(specs), config: railConfig(specs) };
  }

  /** The legend's hidden set (CONTRACT §31). From the view (fromView): it has drawn it already; the URL and the page
      hear of it. From the page (el.hiddenSeries, Back / Forward): the view is updated with it. */
  _setHidden(names, fromView, { write = true } = {}) {
    const next = [...new Set((Array.isArray(names) ? names : []).map(String))];
    if (next.length === this._hidden.length && next.every((n, i) => n === this._hidden[i])) return;
    this._hidden = next;
    if (write && this._started && this.origin) this._writeUrl();
    this.dispatchEvent(new CustomEvent('data-views-legend', { detail: { hidden: [...next] } }));
    if (!fromView && this._plugin && this._model) this._plugin.update(this._input());
  }

  /** Back / Forward or an edited fragment: the hidden set becomes the URL's, as a fresh load of it gives (no write back:
      the URL is the one navigated to). */
  _listenLegend() {
    if (this._onLegendNav || typeof addEventListener !== 'function') return;
    this._onLegendNav = () => {
      if (this.hasAttribute('no-url') || !this._started) return;
      let names;
      try { names = decodeHidden(new URLSearchParams(location.hash.slice(1)).get('l')); } catch { return; }
      this._setHidden(names, false, { write: false });
      // CONTRACT §40: an edited fragment moves the switch
      if (this._hasSwitch()) {
        try { const h = new URLSearchParams(location.hash.slice(1)); if (h.has('edit') && (h.get('edit') === '1') !== !!this._editOn) this.setEditing(h.get('edit') === '1'); } catch { /* an unreadable fragment: the state stays */ }
      }
      // CONTRACT §36: an order or picks the fragment names now
      if (this._precInfo) {
        try {
          const h = new URLSearchParams(location.hash.slice(1));
          if (!h.has('sources') && !h.has('picks')) return;
          const info = this._precInfo;
          if (!this._prec) this._prec = this._readPrec();
          const order = normalizeOrder(h.has('sources') ? decodeOrder(h.get('sources')) : null, info.ids, info.default);
          const ov = normalizePicks(h.has('picks') ? decodePicks(h.get('picks')) : {}, this._precFields());
          this._applyPrec({ order: [...this._prec.order], ov: { ...this._prec.ov } }, { order, ov });
        } catch { /* an unreadable fragment: the state stays */ }
      }
    };
    addEventListener('hashchange', this._onLegendNav);
    addEventListener('popstate', this._onLegendNav);
  }

  _readUrl() {
    if (this.hasAttribute('no-url')) return null;
    try {
      const h = new URLSearchParams(location.hash.slice(1));
      const q = new URLSearchParams(location.search);
      const out = { name: h.get('view') || null, view: h.get('v') ? G.decodeView(h.get('v')) : null, query: h.get('q') || null, group: h.get('group') || null, hidden: decodeHidden(h.get('l')) };
      // the rail's part, readable: ?brand=A,B&peak_torque=10..<20&brand!=KST&model~=ak&has=photo (facets.js, railParams)
      const { props, known, config } = this._railUrl();
      const facets = paramsRail([...q.entries()], props, known, config);
      const custom = h.get('f') ? G.decodeView(h.get('f')) : null;
      if (custom && custom.all !== undefined) out.filters = custom.all ?? undefined;
      else if (Object.keys(facets).length || custom) {
        const file = toRail(this._base.filters, config);
        out.filters = fromRail(Object.keys(facets).length ? facets : file.facets, custom ? custom.rest : file.rest);
      }
      return out;
    } catch { return null; }
  }

  _writeUrl() {
    if (this.hasAttribute('no-url')) return;
    try {
      const h = new URLSearchParams(location.hash.slice(1));
      h.set('view', this._slugOf(this.origin.kind, this.origin.name));
      // WHY group= apart from v=: the grouping is the one change a catalogue reader makes most, and a link should say
      // it in words (#view=home&group=size); v= carries the rest of a changed view, as before (docs/CONTRACT.md §20)
      const bare = (x) => { const c = { ...x }; delete c.grouping; return c; };
      if (G.viewKey(bare(this.view)) !== G.viewKey(bare(this.origin.view))) h.set('v', G.encodeView(this.view)); else h.delete('v');
      const grouping = G.groupingOf(this.view);
      if (grouping) h.set('group', grouping.id); else h.delete('group');
      if (this.query) h.set('q', this.query); else h.delete('q');
      if (this._hidden.length) h.set('l', encodeHidden(this._hidden)); else h.delete('l');
      // CONTRACT §40: Edit is in the link; View, where a page opens, leaves it clean
      if (this._hasSwitch()) { if (this._editOn) h.set('edit', '1'); else h.delete('edit'); }
      // CONTRACT §36 (§31's readable pattern): the order when it is not the default, the rows chosen by hand
      if (this._precInfo && this._prec) {
        if (this._prec.order.join('\u0000') !== this._precInfo.default.join('\u0000')) h.set('sources', encodeOrder(this._prec.order)); else h.delete('sources');
        if (Object.keys(this._prec.ov).length) h.set('picks', encodePicks(this._prec.ov)); else h.delete('picks');
      }
      const q = new URLSearchParams(location.search);
      const { known, config } = this._railUrl();
      for (const k of [...q.keys()]) if (isRailParam(k, known)) q.delete(k);
      const now = toRail(this._filters, config);
      const file = toRail(this._base.filters, config);
      const sameFacets = JSON.stringify(now.facets) === JSON.stringify(file.facets);
      if (!sameFacets) for (const [k, v] of railParams(now.facets)) q.append(k, v);
      // WHY a blob for the rest: a custom clause (an ||, a !=) has no readable form; the facet part keeps one
      if (JSON.stringify(now.rest) !== JSON.stringify(file.rest)) h.set('f', G.encodeView({ rest: now.rest })); else h.delete('f');
      // WHY unescaped: the separators and the rail's key marks (brand!=KST, model~=ak) read as written; the URL
      // parser leaves , ! ~ ^ alone in a query (a < still shows as %3C)
      const search = q.toString().replace(/%2C/gi, ',').replace(/%21/g, '!').replace(/%7E/gi, '~').replace(/%5E/gi, '^');
      // the legend's names read as written, comma-separated (a comma inside a name stays %2C, legend.js)
      const hash = h.toString().replace(/(^|&)l=[^&]*/, (m) => m.replace(/%2C/gi, ',')).replace(/(^|&)(sources|picks)=[^&]*/g, (m) => m.replace(/%2C/gi, ',').replace(/%3A/gi, ':'));
      history.replaceState(null, '', `${location.pathname}${search ? '?' + search : ''}#${hash}`);
    } catch { /* a sandboxed frame without history: the view still works, unshared */ }
  }

  // ------------------------------------------------------------------ events
  /** The document's click and Esc, while the element is in the page (removed in disconnectedCallback). */
  _listenDocument() {
    if (!this._onDocClick || this._docListening || !this.isConnected) return;
    this._docListening = true;
    document.addEventListener('click', this._onDocClick);
    document.addEventListener('keydown', this._onDocKey);
  }

  _wire() {
    // WHY once: the element re-starts when its .base changes, but its own listeners must not double up
    if (this._wired) return;
    this._wired = true;
    this.addEventListener('click', (e) => {
      const t = e.target;
      const menu = t.closest('[data-menu]');
      if (menu && this.contains(menu) && !t.closest('.dv-pop')) { this._openMenu(menu); return; }
      const tab = t.closest('.dv-tab');
      if (tab) {
        const list = tab.dataset.kind === 'user' ? this._userViews() : this.presets;
        const v = list.find((x) => x.name === tab.dataset.name);
        if (v) this._select(tab.dataset.kind, v);
        return;
      }
      // CONTRACT §40: the full toolbar's switch (the bar's goes through its own act())
      if (t.closest('.dv-editsw')) { this.setEditing(!this._editOn); return; }
      if (t.closest('[data-toast-undo]')) { this._session.undo(); return; }
      if (t.closest('[data-rows-refresh]')) { this.refreshRows(); return; }
      if (t.closest('.dv-units')) { this.update((x) => { x.units = (x.units || 'column') === 'inline' ? 'column' : 'inline'; }); return; }
      // CONTRACT §36: the status line's Reset (the default order) and Clear (every row's pick)
      if (t.closest('[data-sources-reset]')) { this.setPrecedence({ order: null }); return; }
      if (t.closest('[data-sources-clear]')) { this.setPrecedence({ ov: null }); return; }
      if (t.closest('.dv-reset')) { this._select(this.origin.kind, this.origin.view, null, { fresh: true }); return; }
      if (t.closest('.dv-close')) { this.closePeek(); return; }
      const thumb = t.closest('.dv-peek-media [data-thumb]');
      if (thumb) { const box = thumb.closest('[data-peek-media]'); const list = attachmentsOf(this._peek && this._peek.row[box.dataset.peekMedia]); this.showMedia(list.filter((a) => a.url && !a.missing), list.filter((a, i) => a.url && !a.missing && i < Number(thumb.dataset.thumb)).length); return; }
      // §15: a bar control that opened a menu (or moved inside one) is not a click outside it; nor, under the bar, is a
      // click on a menu control that the menu's own redraw has just detached (composedPath still holds the menu)
      if (t.closest('[data-bar]')) return;
      // §40: a column's menu button has just opened its menu in the view's own click
      if (t.closest('[data-col-menu], [data-col-first], [data-prop-vis], [data-prop-add]')) return;
      if (this._barUi && e.composedPath().includes(this.$('.dv-pop'))) return;
      if (!t.closest('.dv-pop')) this.closeMenu();
    });
    // CONTRACT §34: a legend's series, a KPI card or a field of the record peek has an item menu (Add to dashboard…):
    // a right-click or a long-press (the browser's contextmenu), the ContextMenu key or Shift+F10 on it
    this.addEventListener('contextmenu', (e) => { this._itemMenu(e); });
    this.addEventListener('keydown', (e) => { if ((e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) && this._itemMenu(e)) e.stopPropagation(); });
    // §15 Escape order: an open menu, then the View settings (panel or popover), then the peek, then the selection
    const settingsOpen = () => !!(this._settingsUi && this._settingsUi.isOpen());
    // WHY (judge r6 #3): a related record's chip that Tab reaches may sit behind its cell's ellipsis; the chip row scrolls
    // it into view while it has focus (types.css drops the ellipsis then) and goes back to its start when focus leaves
    this.addEventListener('focusin', (e) => {
      const chip = e.target.closest && e.target.closest('.dv-rels > .dv-rel');
      if (!chip) return;
      const row = chip.parentElement;
      const c = chip.getBoundingClientRect(), r = row.getBoundingClientRect();
      if (c.right > r.right) row.scrollLeft += c.right - r.right;
      if (c.left < r.left) row.scrollLeft -= r.left - c.left;
    });
    this.addEventListener('focusout', (e) => {
      const row = e.target.closest && e.target.closest('.dv-rels');
      if (row && !row.contains(e.relatedTarget)) row.scrollLeft = 0;
    });
    this.addEventListener('keydown', (e) => {
      // §15 Escape order: a menu, View settings, then the peek (stepping back along its trail first, ../open.js), then the
      // selection
      // §38: Esc in a page section puts its words back (page-section.js); it does not close the record
      if (e.key === 'Escape' && e.target.closest && e.target.closest('[data-page-sec]')) return;
      // §40: a column's menu gives the focus back to its button, which its header's redraws have replaced
      if (e.key === 'Escape') { if (!this.$('.dv-pop').hidden) { const back = this.$('.dv-pop')._back; this.closeMenu(); if (back) back(); } else if (settingsOpen()) this._settingsUi.close(); else if (this._peek) { if (!this._open.back()) this.closePeek(); } else this.clearSelection(); }
    });
    this._onDocClick = (e) => {
      // §15: the View settings popover closes on a click outside it (settings.js decides from composedPath)
      if (this._settingsUi) this._settingsUi.outside(e);
      if (!this.contains(e.target) && !(this._barUi && e.composedPath().includes(this))) this.closeMenu();
    };
    // WHY on the document: a redraw replaces the focused row, so Esc must not depend on focus being inside
    this._onDocKey = (e) => {
      // CONTRACT §40: on the document, because a redraw takes the focused row away and the next key lands on the page itself
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'z' && this._session.key(e)) return;
      // §15: '/' focuses one bar's query box on the page (bar.js picks which)
      if (e.key === '/' && this._barUi && slashKey(this, e)) return;
      if (e.key === 'Escape' && !this.contains(e.target)) { if (!this.$('.dv-pop').hidden) this.closeMenu(); else if (settingsOpen()) this._settingsUi.close(); else if (this._peek && !this._open.back()) this.closePeek(); } };
    this._listenDocument();
    this.addEventListener('input', (e) => {
      // WHY a frame: the box echoes each key as it is typed (the browser draws it); the rows follow once per frame, so
      // keys typed while a large model rebuilds become one rebuild, not one each (perf review 2026-10-26, item 5)
      if (e.target.matches('.dv-search input')) {
        this.query = e.target.value.trim();
        if (!this._searchFrame) this._searchFrame = requestAnimationFrame(() => { this._searchFrame = 0; if (this._started) this._render(); });
        return;
      }
      const tr = e.target.closest && e.target.closest('.dv-peek-form .dv-peek-field');
      if (tr) tr.classList.add('dv-changed');
    });
    wireSections(this);
    wireInspector(this);
    wirePage(this);
    // the peek's form (a view with edit: true): propose what changed; the host decides, as for the record view's
    this.addEventListener('submit', async (e) => {
      const form = e.target.closest && e.target.closest('.dv-peek-form');
      if (!form || !this._peek) return;
      e.preventDefault();
      const { id, row } = this._peek;
      const msg = form.querySelector('.dv-form-msg');
      if (!form.reportValidity()) return;
      const set = readEdits(form, row, this._model.columns);
      if (!Object.keys(set).length) { msg.className = 'dv-form-msg'; msg.textContent = 'Nothing changed.'; return; }
      const result = await this.propose({ id: row.id, set });
      const n = Object.keys(set).length;
      const ok = !!(result && result.ok);
      const text = ok ? `Saved ${n} ${n === 1 ? 'field' : 'fields'}.` : `Not saved: ${(result && result.reason) || 'the host refused the edit.'}`;
      // WHY redraw only on ok: the host re-rendered with the edited rows; a refusal keeps what was typed
      if (ok && this._peek && this._peek.id === id) { this._peekMsg = { id, ok, text }; this.openPeek(id, this._peek.opts); }
      else { msg.className = 'dv-form-msg dv-refused'; msg.setAttribute('role', 'alert'); msg.textContent = text; }
    });
    this.addEventListener('reset', (e) => {
      if (!e.target.closest || !e.target.closest('.dv-peek-form')) return;
      this._peekMsg = null;
      requestAnimationFrame(() => { if (this._peek) this.openPeek(this._peek.id, this._peek.opts); });
    });
  }
}

if (!customElements.get('data-views')) customElements.define('data-views', DataViews);
