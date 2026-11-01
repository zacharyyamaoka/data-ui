/* <data-dashboard src="x.base">: many views and KPI cards of one or more linked datasets on one page (PEP 0004).

   Zach, 2026-10-26: "we have the ability to have a single view of a lot of data with the table, but to make this work
   for Vibe Tracks we may need to extend the functionality a bit." A dashboard is a .base file with `layout:`; each
   panel is a plain <data-views> (one view, or several as tabs) that this element drives through its public surface
   only: `data`, `base`, `filters`, the `data-views-change` event and an instance-level `openPeek`. So every view
   plugin, menu and peer lane's change to <data-views> passes through untouched.

   What it adds (the rules are model.js's; docs/peps/0004-dashboards.md §5):
     the rail     one <data-facets> per dataset that has facets, each bound to a hidden <data-dashboard-source>
                  that looks to the rail like a <data-views> (data, base, view, filters, model, events)
     cross-filter a view with `select: <property>`: a click selects the clicked rows' values; every other panel
                  narrows (through links), the emitting panel does not; chips above the grid clear them
     links        semi-joins, handed to each panel as an ordinary Bases filter on the link column
     layers       a 3D view's layers may read other datasets (docs/CONTRACT.md §32): each is filtered as a panel on
                  that dataset would be and handed to the panel's <data-views> as `layers` (its view's input.layers)
     roll-ups     computed columns of a dataset through its tree, recomputed on every change, drawn as derived
     drill-down   one side peek for the whole dashboard (a <data-views class="dd-drill">), resizable, remembered
     URL          rails as readable params (other datasets prefixed), selections, tabs and each panel's hidden legend
                  series in the hash (l.<panel>=, core's legend.js); a pick (a rail, a selection) is one history entry,
                  and Back / Forward give what a fresh load of that URL gives (CONTRACT §33)
     navigation   a link may be one-way; a dataset whose data: names a placeholder (runs/{run}.json) reads the one file
                  the picks leave, fetched once and kept, and its panels say "Pick one run" until one run is picked; a
                  view's selected: presets its selection; a select: on its rail's one-choice facet picks there
                  (CONTRACT §33, docs/peps/0013-navigation.md)
     add          every panel's ⋯ menu adds its view to the bottom of a dashboard the host lists (the host saves the
                  text; CONTRACT §34); a layout panel's t: pins it at an instant, on a clock of its own paused
                  there (a LiveClock, so it stays there on live data)
     edit         with the `editor` attribute, Edit in the bar (in place of Arrange) turns the dashboard into its own
                  editor: edit/ in dist/dashboard-edit.js, loaded on that press; the host saves the text (as above)
   Load: <link rel="stylesheet" href="data-ui.css"> and <script type="module" src="dashboard.js"> (it imports the
   page's one core, ./data-ui.js). */

import { parseBase } from '../../core/src/base.js';
import { loadDataset } from '../../core/src/data.js';
import { facetSpecs, railConfig, toRail, fromRail, railParams, paramsRail } from '../../core/src/facets.js';
import { properties as labelled } from '../../core/src/rowmodel.js';
import { esc, slug, fmtNum, numOpts, cellText } from '../../core/src/format.js';
import { encodeView, decodeView, cellValue } from '../../core/src/grammar.js';
import { makeResizable } from '../../core/src/resize.js';
import { readDashboard, panelFilter, panelFilters, layerFilters, keep, applyRollups, readHash, writeHash, valuesOf, resolveStyle, arrangeLayout, layoutText, clockScopes, clockSpan, templateFile, declaredFile, presets, settledSelections, pickRail, railPicks } from './model.js';
import { normalizeDataset } from '../../core/src/data.js';
import { stringifyBase } from '../../core/src/base.js';
import { primaryDriver, driverInstance, writeClockParams, clockNavigation, fmtTime } from '../../core/src/clock.js';
import { isLiveDataset, LiveClock } from '../../core/src/live.js';
import { markdown } from './md.js';
import { sectionSources } from '../../core/src/sections.js';
import { liveDatasets, openLive, closeLive, makeClock, bindLive, liveKey, liveHash, liveBar, liveNavigation, rollupTime } from './live.js';
import css from './dashboard.css';

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// CONTRACT §39: the views that draw a panel's picks themselves, through selected(set); a table's are the panel's stylesheet
const MARK_THEMSELVES = new Set(['map', 'cards']);

function addStyle() {
  if (typeof document === 'undefined' || document.querySelector('style[data-ui-dashboard]')) return;
  const s = document.createElement('style');
  s.dataset.uiDashboard = '';
  s.textContent = css;
  document.head.append(s);
}

/** What a <data-facets for=…> rail needs from its target, for one dataset of a dashboard. */
export class DashboardSource extends HTMLElement {
  get data() { return this._data; }
  get base() { return this._base; }
  get view() { return this._view; }
  get model() { return this._model; }
  get dataUrl() { return this._data && this._data.url; }
  /** Bumped whenever the dashboard re-feeds this source (a rail's counts cache on it, as on a <data-views>). */
  get dataRevision() { return this._rev || 0; }
  get filters() { return this._dash ? this._dash.state.rail[this._name] : undefined; }
  set filters(f) { if (this._dash) this._dash.setRail(this._name, f === null || f === '' ? undefined : f); }
  openMenu() { /* the rail's "Edit" for custom clauses: a dashboard's custom rail clauses live in the file */ }
}
if (!customElements.get('data-dashboard-source')) customElements.define('data-dashboard-source', DashboardSource);

export class DataDashboard extends HTMLElement {
  constructor() {
    super();
    this.state = { rail: {}, select: {}, tabs: {}, legend: {} };
    this.datasets = {};
    this.panelEls = {};
    this.sources = {};
    // CONTRACT §33: the per-pick files read so far (href → dataset, the newest last), the fetches under way, and what
    // each per-pick dataset reads now ({path, values, choices, href, status: pick | loading | ok | error, error})
    this._fileCache = new Map();
    this._inflight = new Map();
    this._files = {};
    this._blanks = {};
  }

  static get observedAttributes() { return ['src', 'editor']; }
  /** WHY any change while on the page (sim2real gap #13, 2026-10-28): this reloaded only after a first load, so a host
      that made the element, put it on the page and then set src (or swapped one file for another) got nothing. Off the
      page, connectedCallback loads it when the element is put back. */
  attributeChangedCallback(name, old, value) {
    if (name === 'src' && old !== value && value && this.isConnected) this._load();
    // the bar offers Edit from the moment the attribute is there
    if (name === 'editor' && (old === null) !== (value === null) && this.dash && !this._editor) {
      const bar = this.querySelector('.dd-actions');
      if (bar) { bar.innerHTML = this._actionsHtml(); this._wireActions(); }
    }
  }

  /** Is the editor on? (the `editor` attribute offers it; Edit or edit() turns it on) */
  get editing() { return !!this._editor; }

  /** Turn the editor on, or off with edit(false), which asks about unsaved changes. It needs the file's text (`baseText`:
      a dashboard loaded from `src` has it, a host that calls load() itself sets it). WHY a separate bundle: gridstack and
      the editor load on this call, so a dashboard nobody edits never pays for them. */
  async edit(on = true) {
    if (!on) return this._editor ? this._editor.exit() : true;
    if (this._editor || !this._canEdit()) return !!this._editor;
    const mod = await import(/* @vite-ignore */ new URL('./dashboard-edit.js', import.meta.url).href);
    await mod.startEditing(this);
    return true;
  }

  _canEdit() { return this.hasAttribute('editor') && typeof this.baseText === 'string'; }

  /** The .base file, as the `src` attribute is written; setting it loads that file, as setting the attribute does. */
  get src() { return this.getAttribute('src') || ''; }
  set src(value) { if (value === null || value === undefined || value === '') this.removeAttribute('src'); else this.setAttribute('src', String(value)); }

  disconnectedCallback() {
    if (this._editor) this._editor.listen(false);
    if (this._waitRO) this._waitRO.disconnect();
    this._stopRefresh();
    closeLive(this);
    if (this.clock && !this.clock.live) this.clock.pause();
    // a pinned panel's clock lets go of its live data (its views bind it again when the element is put back)
    for (const kept of (this._pins && this._pins.values()) || []) for (const ds of kept.clock.datasets || []) kept.clock.unbind(ds);
    if (this._onHash) { removeEventListener('hashchange', this._onHash); removeEventListener('popstate', this._onHash); }
  }

  connectedCallback() {
    // a `src` property set before this element was defined is an own property that hides the setter: hand it over
    if (Object.prototype.hasOwnProperty.call(this, 'src')) { const v = this.src; delete this.src; this.src = v; }
    // WHY captured here: _draw gives an id-less dashboard a generated id, and every dashboard's URL scope is computed
    // from the ids the page wrote (clockScopes), so a later draw must not change another dashboard's scope
    if (this._idAttr === undefined) this._idAttr = this.getAttribute('id') || null;
    if (!this._keysWired) {
      this._keysWired = true;
      this.addEventListener('keydown', (e) => this._key(e));
      this.addEventListener('click', (e) => {
        const b = e.target.closest('.dd-act');
        if (b && this.contains(b)) { this._onAction(b.dataset.act, b); return; }
        // CONTRACT §34: a panel's own menu (⋯) and its Add to dashboard…
        const pm = e.target.closest('.dd-panel-menu');
        if (pm && this.contains(pm)) { this._panelMenu(pm); return; }
        const add = e.target.closest('.dd-panel-pop [data-add-dashboard]');
        if (add && this.contains(add)) { this._addPanel(add.closest('.dd-panel')); return; }
        if (!e.target.closest('.dd-panel-pop')) this._panelMenu(null);
        const item = e.target.closest('[data-rr=copy]');
        if (item) { navigator.clipboard?.writeText(this._rerunCommand || '').catch(() => {}); item.querySelector('small').textContent = 'Copied: ' + this._rerunCommand; }
        if (!e.target.closest('.dd-menu')) for (const pop of this.querySelectorAll('.dd-pop')) pop.hidden = true;
      });
    }
    if (this._loadedFrom && this.dash) { this._startRefresh(); openLive(this); }
    if (this._editor) this._editor.listen(true);
    // a per-pick file that arrived while the element was off the page (CONTRACT §33): it is cached; draw it now
    if (this._loadedFrom && this.dash && Object.values(this._files).some((f) => f.status === 'loading' && !this._inflight.has(f.href))) this._update();
    // WHY listen: a #t= edited (or navigated back to) after load moves the clock, as a shared link does (judge r1 #5);
    // the panels' hidden legend series follow the URL the same way
    // and the picks (CONTRACT §33): a pick is a history entry, so Back and Forward land on the URL of the pick before
    if (!this._onHash) this._onHash = () => this._navigate();
    addEventListener('hashchange', this._onHash);
    addEventListener('popstate', this._onHash);
    // focusable, so the clock's keys work after a click anywhere on the dashboard
    if (!this.hasAttribute('tabindex')) this.tabIndex = 0;
    addStyle();
    this.classList.add('data-ui');
    // a src set while the element was off the page (or never loaded) loads now; the same src put back stays as drawn
    const src = this.getAttribute('src');
    if (src && this._loadedFrom !== src) this._load();
  }

  /** Re-read the .base file and every dataset (an agent edited them); the rails, selections and tabs stay. */
  reload() { this._loadedFrom = null; return this._load(); }

  async _load() {
    const src = this.getAttribute('src');
    this._loadedFrom = src;
    // WHY a number per load: a src set while another file is still loading must win, whichever answers last (#13)
    const mine = (this._loadNo = (this._loadNo || 0) + 1);
    try {
      const url = new URL(src, location.href).href;
      const text = await (await fetch(url)).text();
      if (mine !== this._loadNo) return;
      // WHY the draft: a reload while editing re-reads the data; the text being edited stays what is drawn (the file
      // that moved underneath is said at review, before anything is replaced)
      const drawn = this._editor ? this.baseText : text;
      const base = parseBase(drawn);
      const dash = readDashboard(base);
      // WHY not a per-pick dataset (CONTRACT §33): its file is the one a pick names, read once the picks are known
      const entries = await Promise.all(Object.values(dash.datasets).filter((d) => !d.template).map(async (d) => {
        const href = new URL(d.data, url).href;
        const ds = await loadDataset(href);
        return [d.name, { ...ds, url: href }];
      }));
      if (mine !== this._loadNo) return;
      this.baseText = drawn;
      this._srcUrl = url;
      // re-read means re-read: an agent may have rewritten the per-pick files too
      this._fileCache.clear();
      this._files = {};
      this._blanks = {};
      // the same file again keeps the reader's rails, selections, tabs and clock (reload); another file is a new
      // document: its own defaults, the URL read as a fresh load reads it, and its own clock (sim2real gap #13)
      const again = !!this.dash && this._docSrc === src;
      this._docSrc = src;
      // datasets.<name>.live: a LiveDataset whose source connects now (docs/peps/0012-live-data.md §7.2)
      const loaded = liveDatasets(this, base, Object.fromEntries(entries), url);
      for (const d of Object.values(dash.datasets)) if (d.template) loaded[d.name] = this._blank(d.name);
      this.load(base, loaded, { keepState: again });
    } catch (err) {
      if (mine !== this._loadNo) return;
      this.innerHTML = `<p class="dv-err">data-ui could not load the dashboard ${esc(src)}: ${esc(err.message)}</p>`;
    }
  }

  /** Draw a parsed .base document over datasets already loaded ({name: dataset}); hosts without src call this. */
  load(base, datasets, { keepState = false, arranged = false } = {}) {
    if (!arranged) this._fileBase = base;
    // a reader's own arrangement (Arrange → Done) is kept in this browser and drawn over the file's layout; WHY not with an
    // editor: there the file is the one truth, and what Edit shows must be what Save writes
    const saved = this.hasAttribute('editor') ? null : this._savedArrangement();
    this._arranged = !!saved;
    if (saved) base = { ...this._fileBase, layout: arrangeLayout(this._fileBase.layout, readDashboard(this._fileBase).panels, saved) };
    this.base = base;
    this.dash = readDashboard(base);
    this.datasets = datasets;
    // a host that hands a per-pick dataset in (load(base, datasets)) keeps it: no file is read for it
    for (const d of Object.values(this.dash.datasets)) if (d.template && !this.datasets[d.name]) this.datasets[d.name] = this._blank(d.name);
    if (!keepState) {
      this.state = { rail: {}, select: {}, tabs: {}, legend: {} };
      for (const d of Object.values(this.dash.datasets)) this.state.rail[d.name] = clone(d.filters);
      this._readUrl();
      // CONTRACT §33 (sim2real gap #7): the views' selected: presets, where the URL names no selection of that panel
      this._applyPresets();
    }
    // WHY after the state (gap #1): the clock spans the rows the rails, selections and links leave; a new document
    // (no kept state) gets a new clock with its own rate, loop, fps and span (gap #13)
    this._setupClock(!keepState);
    // WHY here, after the tabs are known and before any card draws: the driver is a card on screen (judge r3 #4)
    this._resolveDriver();
    this._draw();
    this._showClockNote();
    this._update();
  }

  // ------------------------------------------------------------------ public state changes

  /** Set one dataset's rail filter (the rails call this through their source element). A pick is a history entry
      (CONTRACT §33); typing in a search facet replaces the entry it is on, so a word is not a dozen entries. */
  setRail(name, filter) {
    const was = this.state.rail[name];
    this.state.rail[name] = clone(filter);
    // CONTRACT §39: a tick that hides a preset panel's pick moves it; WHY not a word: it is gone as soon as the word is
    const ticks = this._ticks(name, was);
    if (ticks === null || ticks !== this._ticks(name, this.state.rail[name])) this.state.select = settledSelections(this.dash, this.datasets, this.state);
    this._push = !this._onlyText(name, was, this.state.rail[name]);
    this._update();
  }

  /** Select `values` of `property` from a panel (what a click does); an empty list clears it. A history entry. */
  select(panelKey, property, values) {
    const p = this.dash.panels.find((x) => x.key === panelKey);
    if (!p) return;
    if (values && values.length) this.state.select[panelKey] = { dataset: p.dataset, property, values: [...values] };
    else delete this.state.select[panelKey];
    // CONTRACT §39: a pick that leaves a preset panel's selection naming no row moves that panel with it, in this one entry
    this.state.select = settledSelections(this.dash, this.datasets, this.state);
    this._push = true;
    this._update();
  }

  clearSelections() { this.state.select = {}; this._push = true; this._update(); }

  /** A rail as its ticks and ranges, its search words left out: a facet holding only words is no facet. null when it cannot
      be told. WHY not _onlyText: that one answers for history, where the first letter of a search is an entry of its own. */
  _ticks(name, filter) {
    try {
      const { facets, rest } = toRail(filter, this._railUrl(name).config);
      const kept = Object.entries(facets).map(([key, { text, textIn, textMatch, ...others }]) => [key, others]).filter(([, others]) => Object.keys(others).length);
      return JSON.stringify([Object.fromEntries(kept), rest]);
    } catch { return null; }
  }

  /** Did a rail change only a search facet's text? (its search params are typed letter by letter) */
  _onlyText(name, a, b) {
    try {
      const { config } = this._railUrl(name);
      const strip = (f) => JSON.stringify(Object.fromEntries(Object.entries(toRail(f, config).facets).map(([k, v]) => [k, { ...v, text: undefined, textIn: undefined, textMatch: undefined }])));
      const ra = toRail(a, config), rb = toRail(b, config);
      return JSON.stringify(ra.rest) === JSON.stringify(rb.rest) && strip(a) === strip(b) && JSON.stringify(ra.facets) !== JSON.stringify(rb.facets);
    } catch { return false; }
  }

  /** The filter each panel has now (for tests and for hosts that want to show it). */
  panelFilters() { return panelFilters(this.dash, this.datasets, this.state); }

  /** The filter each layer dataset of each panel has now, {<panel key>: {<dataset>: filter}} (CONTRACT §32): the one a
      panel on that dataset with the same key would have. Panels whose views read no other dataset are left out. */
  layerFilters() {
    return Object.fromEntries(this.dash.panels.filter((p) => p.layers && p.layers.length).map((p) => [p.key, layerFilters(this.dash, this.datasets, this.state, p)]));
  }

  /** Hand a panel's <data-views> its layer datasets (CONTRACT §32) when a layer's filter or a dataset changed since
      the last time (a refetch replaces the dataset; a roll-up rewrote its cells: `force`). */
  _handLayers(p, el, force = false) {
    if (!p.layers || !p.layers.length) return;
    const filters = layerFilters(this.dash, this.datasets, this.state, p);
    const key = JSON.stringify(Object.entries(filters).map(([name, f]) => [name, f ?? null]));
    const sets = Object.keys(filters).map((name) => this.datasets[name]);
    const was = (this._layerKeys ||= {})[p.key];
    if (!force && was && was.key === key && was.sets.length === sets.length && was.sets.every((d, i) => d === sets[i])) return;
    this._layerKeys[p.key] = { key, sets };
    el.layers = Object.fromEntries(Object.entries(filters).map(([name, f]) => [name, { dataset: this.datasets[name], rows: keep(this.datasets[name].rows, f) }]));
  }

  // ------------------------------------------------------------------ the clock (docs/peps/0005-dashboard-cards.md §4)

  /** One clock for the whole dashboard, kept across reloads of the same document (`fresh`: a new one); its span is
      `clock: {data, time}` over the rows the filters leave (_spanClock). */
  _setupClock(fresh = false) {
    const c = this.dash.clock || {};
    // WHY read the link first and hold writes: setting the span fires `state`, whose listener writes the URL, and at
    // t = 0 that write erased #t= before it was read (a shared link always opened at the start)
    let link = null;
    if (!this.hasAttribute('no-url')) {
      const key = this._clockKey();
      if (key !== false) try { const p = new URLSearchParams(location.hash.slice(1)); link = liveNavigation(clockNavigation(p, key), p, key); } catch { /* a malformed link starts at home */ }
    }
    this._clockSetup = true;
    // WHY a new clock for a new document (gap #13): the kept one held the last file's rate, loop, fps and declared
    // span, which a file without clock: data could never move again
    if (this.clock && fresh) this._retireClock();
    if (!this.clock) {
      // a LiveClock: exactly a Clock until a live dataset is bound (docs/peps/0012-live-data.md §4)
      const clock = (this.clock = makeClock(this, c));
      // WHY the URL only on a pause or a seek: replaceState at 60 Hz while playing is a page-wide stall
      this._onClockChange = () => { if (this.clock === clock && !clock.playing && !this._clockSetup) this._writeUrl(); };
      clock.addEventListener('time', this._onClockChange);
      clock.addEventListener('state', this._onClockChange);
    }
    const name = c.data || null, prop = c.time || 't';
    // the clock's time column (clock.time, default t): a chart whose x is it follows the clock (CONTRACT §25, kit gap 3)
    this.clock.timeColumn = prop;
    const ds = name ? this.datasets[name] : null;
    if (ds && isLiveDataset(ds)) {
      // a live dataset spans what it holds (LiveClock binds it, CONTRACT §26): as before, every row it has now
      let lo = Infinity, hi = -Infinity;
      for (const r of ds.rows) { const v = cellValue(r[prop]); if (typeof v === 'number' && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
      if (lo <= hi) this.clock.setSpan(lo, hi);
    } else this._spanClock();
    // the live datasets before the link: a link to a moment pauses there, #t=live (or none) follows (LiveClock.restore)
    bindLive(this);
    // WHY restore, the same call as Back / Forward (_readClockUrl): one rule for a link's t and tr however the cards'
    // spans arrive later (judge r3 #2)
    if (link) this.clock.restore(link);
    this._clockSetup = false;
  }

  /** The last document's clock goes: paused, its live datasets let go, its frame loop stopped. Its cards go with the
      panels the next draw replaces. */
  _retireClock() {
    const old = this.clock;
    if (!old) return;
    old.pause();
    if (this._onClockChange) { old.removeEventListener('time', this._onClockChange); old.removeEventListener('state', this._onClockChange); }
    for (const d of old.datasets || []) old.unbind(d);
    old.destroy();
    this.clock = null;
    this._spanKey = null;
  }

  /** The clock's span is the rows its filters leave (sim2real gap #1; model.js clockSpan): `clock.data`'s rows under
      its rail, every selection and the links, read again whenever one of them changes (each _update). No row left: an
      empty span. A live clock dataset keeps the live tier's own span (_setupClock). The caller writes the URL. */
  _spanClock() {
    const c = this.dash && this.dash.clock;
    const ds = this.clock && c && c.data ? this.datasets[c.data] : null;
    // WHY not on a live clock: once a live dataset is bound the live tier owns start and end (they follow the data while
    // it plays and hold still while it is paused, CONTRACT §26); a re-span here would move a paused live clock's span
    if (!ds || isLiveDataset(ds) || this.clock.live) return;
    const filter = panelFilter(this.dash, this.datasets, this.state, c.data, null);
    // WHY a key: _update runs on every click, and most clicks (another dataset's rail, a tab) leave this filter as it was
    const key = JSON.stringify([filter ?? null, c.time || 't']);
    const k = this._spanKey;
    if (k && k.key === key && k.rows === ds.rows && k.clock === this.clock) return;
    this._spanKey = { key, rows: ds.rows, clock: this.clock };
    const span = clockSpan(this.dash, this.datasets, this.state, filter);
    const held = this._clockSetup;
    this._clockSetup = true;
    try { if (span) this.clock.setSpan(span[0], span[1]); else this.clock.setSpan(null, null); } finally { this._clockSetup = held; }
  }

  /** The one video that drives t (docs/peps/0008-one-clock-driver.md): the .base's choice (primaryDriver: clock.primary,
      else the first `video.primary: true` card; judge r1 #3) on the first panel, in layout order, whose OPEN tab
      shows it (driverInstance: one card instance, judge r2 #2; a closed tab is not eligible, judge r3 #4). Re-resolved
      when a tab changes. When no open tab shows it the clock runs on wall time and its bar says so (clock.setNote). */
  _resolveDriver() {
    if (!this.clock || !this.dash) return;
    const panels = this.dash.panels;
    const choice = primaryDriver(this.dash.clock || {}, panels.flatMap((p) => p.views));
    // a panel pinned at an instant (CONTRACT §34) reads a clock of its own: its video never drives the dashboard's
    const key = driverInstance(choice, panels.filter((p) => p.t === null || p.t === undefined), (p) => this._shownView(p));
    this.clock.setDriver(key);
    this.clock.setNote(choice && !key ? `${choice} drives this clock, but no open tab shows it: playing on wall time` : null);
    this._showClockNote();
  }

  /** The name of the view a panel shows: its open tab (state.tabs, the URL's p.<key>=), else its first view. */
  _shownView(p) {
    const open = this.state.tabs[p.key];
    const v = (open && p.views.find((x) => slug(x.name) === open)) || p.views[0];
    return v ? v.name : null;
  }

  /** The clock's note on the dashboard's own bar, only when no playback card is on the layout to carry it. */
  _showClockNote() {
    const bar = this.querySelector(':scope .dd-bar');
    if (!bar) return;
    let el = bar.querySelector('.dd-clock-note');
    const text = this.clock && this.clock.note;
    const carried = this.dash.panels.some((p) => p.views.some((v) => v.type === 'playback'));
    if (!text || carried) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement('span'); el.className = 'dd-clock-note'; el.setAttribute('role', 'status'); bar.insertBefore(el, bar.querySelector('.dd-actions')); }
    el.textContent = text;
  }

  /** The clock's URL scope: null on a page with one dashboard (plain #t= / #tr=), a string (#t.<key>=) with several,
      or false when the page gives this dashboard no unique key (a repeated src without ids, a repeated id: model.js
      clockScopes), so its clock stays out of the URL and the problem is listed. */
  _clockKey() {
    if (this._idAttr === undefined) this._idAttr = this.getAttribute('id') || null;
    const all = [...document.querySelectorAll('data-dashboard')].filter((d) => !d.hasAttribute('no-url'));
    const me = all.indexOf(this);
    if (me < 0 || all.length <= 1) return null;
    const { scopes, problems } = clockScopes(all.map((d) => ({ id: d._idAttr !== undefined ? d._idAttr : d.getAttribute('id') || null, src: d.getAttribute('src') || '' })));
    const mine = problems.find(([i]) => i === me);
    if (mine) this._scopeProblem(mine[1]);
    return scopes[me];
  }

  /** WHY two parts (judge r3 #5): the problem belongs to each parse of the .base — a reload replaces dash.problems, and
      a cached "already reported" flag left the reloaded dashboard without it — while the console warning is once per
      message for the page. */
  _scopeProblem(message) {
    if (!(this._warned ||= new Set()).has(message)) {
      this._warned.add(message);
      console.warn(`<data-dashboard src="${this.getAttribute('src') || ''}">: ${message}`);
    }
    if (this.dash && !this.dash.problems.includes(message)) { this.dash.problems.push(message); this._showProblems(); }
  }

  /** The problems list at the top of the dashboard, redrawn (a page-level problem found after the first draw). */
  _showProblems() {
    let ul = this.querySelector(':scope > .dd-problems');
    if (!this.dash || !this.dash.problems.length || !this.querySelector(':scope > .dd-body')) return;
    if (!ul) { ul = document.createElement('ul'); ul.className = 'dd-problems'; ul.setAttribute('role', 'alert'); this.prepend(ul); }
    ul.innerHTML = this.dash.problems.map((p) => `<li>${esc(p)}</li>`).join('');
  }

  /** The fragment changed after load (an edit, Back / Forward): the clock becomes what a fresh load of this URL gives
      (judge r2 #3): an absent t is the clock's home, an absent or empty tr no range; a malformed value leaves that
      part as it is (core's clockNavigation). WHY no write while applying it: the URL is the one navigated to, and a
      write here rewrote #t=3 to #t=3&tr=2,6, so Back and a fresh load of the same URL disagreed. */
  _readClockUrl() {
    if (!this.clock || !this.dash || this.hasAttribute('no-url')) return;
    let nav;
    const key = this._clockKey();
    if (key === false) return;   // no unique key on this page: the URL is not this clock's (clockScopes)
    try { const p = new URLSearchParams(location.hash.slice(1)); nav = liveNavigation(clockNavigation(p, key), p, key); } catch { return; }
    this._clockSetup = true;
    try { this.clock.restore(nav); } finally { this._clockSetup = false; }
  }

  /** The clock's keys (Rerun / Foxglove / YouTube): Space play-pause, ←/→ a frame, Shift+←/→ a second, J/K/L back,
      pause, forward, [ and ] the range's ends at t, Home/End. Not while typing, and not when a dashboard has no clock:. */
  _key(e) {
    if (e.key === 'Escape' && this.querySelector('.dd-panel-pop:not([hidden])')) { e.stopPropagation(); this._panelMenu(null, true); return; }
    // the editor's panes sit inside this element, and their keys are their own
    if (this._editor && e.target.closest('[data-dde-pane]')) return;
    if (!this.dash || !this.clock || (!this.dash.clock && !this.clock.live)) return;
    // WHY not on a legend entry: it is a button, and Space / Enter there show or hide its series (src/legend.js); nor in a
    // panel's menu, an item menu or the Add to dashboard picker (CONTRACT §34), whose keys are their own; nor on a map's
    // marker or chooser (CONTRACT §39), where Space picks and the arrows are the map's
    if (e.target.closest('input, select, textarea, [contenteditable], .dv-pb-track, .dv-legend, .dd-panel-pop, .dd-panel-menu, .dv-addpick, .dv-itemmenu, .dv-map-marker, .dv-map-choose')) return;
    // End and Ctrl/Cmd+Shift+→ go live, Ctrl/Cmd+Shift+← to the oldest data (Rerun's keys; live.js)
    if (liveKey(e, this.clock)) { e.preventDefault(); e.stopPropagation(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const c = this.clock, k = e.key;
    const done = () => { e.preventDefault(); e.stopPropagation(); };
    if (k === ' ' || k === 'k' || k === 'K') { done(); if (k === ' ') c.toggle(); else c.pause(); }
    else if (k === 'ArrowRight' || k === 'ArrowLeft') {
      if (e.target.closest('data-views table, .dv-pb-lane')) return;   // a table's own row keys win inside it
      done(); const s = k === 'ArrowRight' ? 1 : -1;
      if (e.shiftKey) c.seek(c.t + s); else c.step(s);
    }
    else if (k === 'l' || k === 'L') { done(); c.seek(c.t + 1); }
    else if (k === 'j' || k === 'J') { done(); c.seek(c.t - 1); }
    else if (k === '[') { done(); const b = c.range ? c.range[1] : c.end; if (b > c.t) c.setRange([c.t, b]); }
    else if (k === ']') { done(); const a = c.range ? c.range[0] : c.start; if (c.t > a) c.setRange([a, c.t]); }
    else if (k === 'Home') { done(); c.seek(c.bounds[0]); }
    else if (k === 'End') { done(); c.seek(c.bounds[1]); }
  }

  // ------------------------------------------------------------------ drawing
  _draw() {
    const d = this.dash;
    const id = this.id || (this.id = `dash-${Math.random().toString(36).slice(2, 8)}`);
    this._applyStyle(this, resolveStyle(d.style));
    const rails = Object.values(d.datasets).filter((x) => Array.isArray(x.facets) && x.facets.length && this.datasets[x.name]);
    // WHY forget the drill peek: the redraw below takes it off the page, and a kept reference opened the next drill on
    // a detached element (found on #13: after a reload or a new src, a row click opened nothing)
    this._drillEl = null;
    const body = `
      ${d.problems.length ? `<ul class="dd-problems" role="alert">${d.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
      <div class="dd-body${rails.length ? ' dd-has-rail' : ''}">
        ${rails.length ? '<aside class="dd-rail" aria-label="Filters for every panel"></aside>' : ''}
        <div class="dd-main">
          <div class="dd-bar"><div class="dd-chips" aria-live="polite" data-empty="${esc(this._hint())}"></div><div class="dd-actions">${this._actionsHtml()}</div></div>
          <div class="dd-grid" style="--dd-cols:${d.columns}"></div>
        </div>
      </div>`;
    // WHY the panes stay: a redraw must not take the field being typed in, or the outline's scroll, off the page
    if (this._editor) this._editor.redrawBody(body); else this.innerHTML = body;
    liveBar(this);
    this.sources = {};
    const rail = this.querySelector('.dd-rail');
    for (const r of rails) {
      const src = document.createElement('data-dashboard-source');
      src.id = `${id}-rail-${r.name}`;
      src._dash = this;
      src._name = r.name;
      this._feedSource(src, r);
      this.append(src);
      this.sources[r.name] = src;
      if (rails.length > 1) rail.insertAdjacentHTML('beforeend', `<h3 class="dd-rail-h">${esc(r.label || r.name.replace(/[-_]/g, ' ').replace(/^./, (c) => c.toUpperCase()))}</h3>`);
      const f = document.createElement('data-facets');
      f.setAttribute('for', src.id);
      f.dataset.dataset = r.name;
      rail.append(f);
    }
    if (rail) {
      // WHY: Zach always wants resizable, remembered side panels (memory feedback_resizable_panels); the rail is the
      // dashboard's one side panel, and the drill peek gets its own handle from <data-views>
      rail.dataset.resizable = 'right';
      this._railResize = makeResizable(rail, { edge: 'right', min: 180, max: 480, keep: 360, key: `dash-rail:${id}`, label: 'the filters' });
    }
    const grid = this.querySelector('.dd-grid');
    this.panelEls = {};
    this._layerKeys = {};
    this._prunePins(d.panels);
    for (const p of d.panels) {
      const sec = document.createElement('section');
      sec.className = 'dd-panel';
      sec.dataset.panel = p.key;
      sec.style.setProperty('--dd-w', String(p.w));
      if (p.h) { sec.style.setProperty('--dd-h', `${p.h * d.rowHeight}px`); sec.dataset.sized = ''; }
      if (p.views.length) sec.dataset.type = p.views[0].type || 'table';
      const pst = resolveStyle(d.style, p.style);
      this._applyStyle(sec, pst, true);
      grid.append(sec);
      // while editing, a panel draws inside gridstack's box from the start (moving a <data-views> in remakes its plugin)
      const box = this._editor ? this._editor.box(sec) : sec;
      // WHY in the capture phase: a view calls host.open after its own click handler has read the event, and the
      // dashboard's selection needs to know a ctrl / cmd-click adds a pick (Power BI's multi-select, CONTRACT §33)
      sec.addEventListener('click', (e) => { this._addPick = !!(e.ctrlKey || e.metaKey); }, true);
      sec.addEventListener('keydown', () => { this._addPick = false; }, true);
      if (p.text !== null) {
        sec.classList.add('dd-panel-text');
        box.innerHTML = `<div class="dd-text">${markdown(p.text)}</div>`;
        continue;
      }
      const title = p.title || (p.views.length === 1 ? p.views[0].name : null);
      // CONTRACT §34: a panel pinned at an instant says so beside its title (it does not follow the clock), t written as
      // the playback bar writes it (fmtTime: a wall-clock time on a live clock's Unix seconds), the exact seconds in its
      // title. WHY (RobotDx PEP 0001 §17.1, ask 5): "at t = 1792631514.923 s" said nothing a reader could place
      const at = p.t !== null && p.t !== undefined ? `<span class="dd-at" title="This panel stands at this instant, t = ${esc(String(p.t))} s; it does not follow the dashboard's clock">at t = ${esc(fmtTime(p.t))}</span>` : '';
      if (title && pst.title !== 'none') box.insertAdjacentHTML('beforeend', `<h3 class="dd-panel-h"><span>${esc(title)}</span>${at}<span class="dd-sel"></span></h3>`);
      else if (at) box.insertAdjacentHTML('beforeend', `<p class="dd-panel-h dd-at-only">${at}</p>`);
      sec.setAttribute('aria-label', title || p.views.map((v) => v.name).join(', '));
      // CONTRACT §34: the panel's own menu (Add to dashboard…), unless its toolbar's ⋯ already holds it where no title
      // row leaves room; never on the playback bar (a control, not a view of data)
      // WHY compact for editToggle (CONTRACT §40): the switch needs a toolbar to live in
      const toolbar = p.toolbar || (p.views.length > 1 || p.editToggle ? 'compact' : 'none');
      if (p.views[0].type !== 'playback' && (box.querySelector('.dd-panel-h') || toolbar === 'none')) {
        box.insertAdjacentHTML('beforeend', `<button type="button" class="dd-panel-menu" aria-label="Panel menu" aria-haspopup="menu" aria-expanded="false" title="Panel menu"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="3.5" cy="8" r="1.1"/><circle cx="8" cy="8" r="1.1"/><circle cx="12.5" cy="8" r="1.1"/></svg></button>
          <div class="dd-panel-pop" role="menu" aria-label="Panel" hidden><button type="button" role="menuitem" class="dd-item" data-add-dashboard>Add to dashboard…</button></div>`);
      }
      // a pinned panel's views find this clock first (clockFor walks up from the view): paused at t, its span theirs
      if (p.t !== null && p.t !== undefined) sec.clock = this._pinnedClock(p);
      const el = document.createElement('data-views');
      el.id = `${id}-${p.key}`;
      // a video card here keys its clip `<panel key>/<view name>` (core's driverKey), what setDriver designates above
      el.clockScope = p.key;
      el.setAttribute('no-url', '');
      el.setAttribute('toolbar', toolbar);
      if (p.editToggle) el.setAttribute('edit-toggle', '');
      if (pst.theme === 'light' || pst.theme === 'dark') el.setAttribute('theme', pst.theme);
      const tab = this.state.tabs[p.key] && p.views.find((v) => slug(v.name) === this.state.tabs[p.key]);
      if (tab) el.setAttribute('view', tab.name);
      el.filters = panelFilter(d, this.datasets, this.state, p.dataset, p.key);
      // CONTRACT §31: the panel's hidden legend series (the URL's l.<panel>=), before its first draw; else its view's
      // hiddenSeries (CONTRACT §34: a series added from a legend opens with the others hidden)
      const shown = (tab || p.views[0]);
      el.hiddenSeries = (this.state.legend && this.state.legend[p.key]) || (Array.isArray(shown.hiddenSeries) ? shown.hiddenSeries.map(String) : []);
      // CONTRACT §34: where this panel's view comes from, for Add to dashboard (the view as written, not the style
      // resolved below; the dataset's name, label and the panel's height)
      // and `file`, the file this dashboard declares for the panel's dataset, read when asked (a per-pick dataset's moves
      // with the picks): WHY (RobotDx PEP 0001 §17.1, ask 2) a host may hand one dataset object to several declared files
      const dash = this;
      el.dashboardPanel = { key: p.key, title: p.title, dataset: p.dataset, label: (d.datasets[p.dataset] && d.datasets[p.dataset].label) || null, h: p.h, views: p.views,
        get file() { return dash._declaredFile(p.dataset); } };
      // every view sees its resolved style (dashboard, then panel, then its own): docs/CONTRACT.md §25
      el.base = { properties: (this.base && this.base.properties) || {}, views: p.views.map((v) => ({ ...clone(v), style: resolveStyle(d.style, p.style, v.style) })) };
      // CONTRACT §32: the other datasets its 3D layers read, before its first draw
      this._handLayers(p, el, true);
      el.data = this.datasets[p.dataset];
      // WHY an instance openPeek: every view opens records through host.open → el.openPeek; a dashboard turns that
      // click into a selection (select:) or the one dashboard-wide drill-down, without touching <data-views>' code
      const own = el.openPeek.bind(el);
      el.openPeek = (rowId, opts = {}) => this._clicked(p, el, rowId, opts, own);
      el.addEventListener('data-views-legend', (e) => {
        const now = e.detail.hidden || [];
        if (same(now, (this.state.legend && this.state.legend[p.key]) || [])) return;
        if (now.length) this.state.legend[p.key] = [...now]; else delete this.state.legend[p.key];
        this._writeUrl();
      });
      el.addEventListener('data-views-change', (e) => {
        const s = slug(e.detail.name || '');
        const first = slug(p.views[0].name);
        const was = this.state.tabs[p.key];
        if (s === first) delete this.state.tabs[p.key]; else this.state.tabs[p.key] = s;
        if (was !== this.state.tabs[p.key]) { this._markPanels(); this._writeUrl(); this._resolveDriver(); }
      });
      box.append(el);
      this.panelEls[p.key] = el;
    }
    this._markPanels();
    // the gallery's generic case check (and any host) waits for data-view, as on a <data-views>
    this.dataset.view = 'dashboard';
    this._wireActions();
    this._startRefresh();
    if (this._editor) this._editor.drawn();
  }

  /** A layout the editor's grid has placed already: the same panels, moved or resized, so nothing is drawn again. */
  _adopt(base) {
    this._fileBase = base;
    this.base = base;
    this.dash = readDashboard(base);
    this._resolveDriver();
  }

  // ------------------------------------------------------------------ styling (docs/peps/0005-dashboard-cards.md §5)

  /** Put a resolved style on the dashboard (or one panel): data attributes the CSS reads, and its numbers as vars. */
  _applyStyle(node, st, panel = false) {
    node.dataset.surface = st.surface;
    node.dataset.title = st.title;
    node.dataset.density = st.density;
    node.style.setProperty(panel ? '--dd-p-radius' : '--dd-radius', `${Number(st.radius) || 0}px`);
    node.style.setProperty(panel ? '--dd-p-pad' : '--dd-pad', `${Number(st.pad) || 0}px`);
    if (!panel) node.style.setProperty('--dd-gap', `${Number(st.gap) || 0}px`);
    if (!panel) {
      if (st.theme === 'light' || st.theme === 'dark') this.setAttribute('theme', st.theme);
      else this.removeAttribute('theme');
    }
  }

  // ------------------------------------------------------------------ add to dashboard (docs/CONTRACT.md §34)

  /** A panel's own clock, paused at its `t:` (kept per panel key across redraws; a new instant, a new clock). A
      LiveClock, exactly a Clock while nothing live is bound, restored at t before its views bind their live data, so it
      stays paused at t when they do (CONTRACT §26's LiveClock.restore). WHY (RobotDx PEP 0001 §17.1, ask 3): a plain
      Clock is no clock to a view of live data (live/feed.js makes a LiveClock of its own that follows), so a panel added
      "At this moment" from a live dashboard said "at t = …" and drew the newest data. */
  _pinnedClock(p) {
    const kept = (this._pins ||= new Map()).get(p.key);
    if (kept && kept.at === p.t) return kept.clock;
    if (kept) this._dropPin(p.key);
    const clock = new LiveClock({ loop: false });
    // restore, as a link's t: the instant is kept and re-placed as the panel's views report their spans
    clock.restore({ t: p.t });
    this._pins.set(p.key, { at: p.t, clock });
    return clock;
  }

  /** A pinned clock goes: paused, its live data let go, stopped. */
  _dropPin(key) {
    const kept = this._pins && this._pins.get(key);
    if (!kept) return;
    this._pins.delete(key);
    kept.clock.pause();
    for (const ds of kept.clock.datasets || []) kept.clock.unbind(ds);
    kept.clock.destroy();
  }

  /** Before a draw: a panel no longer pinned at the same instant lets its clock go, and a kept clock lets go of live
      data this dashboard no longer holds (a reload made new datasets; its views bind the new ones). */
  _prunePins(panels) {
    if (!this._pins) return;
    const held = new Set(Object.values(this.datasets || {}));
    for (const [key, kept] of [...this._pins]) {
      const p = panels.find((x) => x.key === key);
      if (!p || p.t !== kept.at) { this._dropPin(key); continue; }
      for (const ds of kept.clock.datasets || []) if (!held.has(ds)) kept.clock.unbind(ds);
    }
  }

  /** Open a panel's menu (its ⋯ button), or close every one (null); `refocus` puts focus back on its button. */
  _panelMenu(btn, refocus = false) {
    for (const pop of this.querySelectorAll('.dd-panel-pop:not([hidden])')) {
      if (btn && pop.previousElementSibling === btn) continue;
      pop.hidden = true;
      const owner = pop.previousElementSibling;
      if (owner) { owner.setAttribute('aria-expanded', 'false'); if (refocus) owner.focus(); }
    }
    if (!btn) return;
    const pop = btn.nextElementSibling;
    const opening = pop.hidden;
    pop.hidden = !opening;
    btn.setAttribute('aria-expanded', String(opening));
    if (opening) {
      const first = pop.querySelector('button');
      if (first) first.focus();
      // a press anywhere else closes it (the dashboard's own clicks close it above)
      const away = (e) => { if (!pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) { this._panelMenu(null); document.removeEventListener('pointerdown', away, true); } };
      document.addEventListener('pointerdown', away, true);
    }
  }

  /** The panel's Add to dashboard…: the picker of its <data-views>, beside the panel's ⋯. */
  _addPanel(sec) {
    if (!sec) return;
    const btn = sec.querySelector('.dd-panel-menu');
    this._panelMenu(null);
    const el = sec.querySelector('data-views');
    if (el && typeof el.addToDashboard === 'function') el.addToDashboard({ kind: 'view' }, { anchor: btn });
  }

  // ------------------------------------------------------------------ arranging (dist/dashboard-arrange.js)

  _arrangeKey() { return `data-ui/dash-layout:${new URL(this.getAttribute('src') || this.id || 'dashboard', location.href).pathname}`; }

  _savedArrangement() {
    try { const v = JSON.parse(localStorage.getItem(this._arrangeKey()) || 'null'); return Array.isArray(v) && v.length ? v : null; } catch { return null; }
  }

  /** Re-order and re-size the panels ([{key, w, h}], reading order), remember it for this reader, redraw. */
  setArrangement(arr) {
    try { if (arr && arr.length) localStorage.setItem(this._arrangeKey(), JSON.stringify(arr)); else localStorage.removeItem(this._arrangeKey()); } catch { /* private mode: this page only */ }
    this.load(this._fileBase, this.datasets, { keepState: true, arranged: true });
  }

  /** The .base text with the layout as drawn now (what Copy layout puts on the clipboard). */
  layoutText() { return layoutText(this.baseText || '', this.base.layout, stringifyBase); }

  // ------------------------------------------------------------------ the bar: Open in Rerun, Arrange

  _actionsHtml() {
    const d = this.dash, out = [];
    if (d.rerun) {
      out.push(`<div class="dd-menu dd-rerun"><button type="button" class="dd-act" data-act="rerun" aria-haspopup="menu" aria-expanded="false" title="Load this dashboard's data into Rerun (a backdoor: same data, Rerun's blueprint)">Open in Rerun <span aria-hidden="true">▾</span></button>
        <div class="dd-pop" role="menu" hidden>
          <a role="menuitem" class="dd-item" data-rr="web" target="_blank" rel="noopener">Open in Rerun's web viewer <small>app.rerun.io · no account</small></a>
          <button type="button" role="menuitem" class="dd-item" data-rr="copy">Copy the native command <small>uvx --from rerun-sdk==${esc(d.rerun.sdk || '0.40.0')} rerun …</small></button>
          <a role="menuitem" class="dd-item" data-rr="download" download>Download the .rrd</a>
        </div></div>`);
    }
    // with an editor, Edit stands where Arrange stood: the editor drags on the same grid, and writes the file
    if (this._editor) { out.push(this._editor.actionsHtml()); return out.join(''); }
    if (this._canEdit()) { out.push('<button type="button" class="dd-act" data-act="edit" title="Edit this dashboard: move, resize, add and change panels, then save">Edit</button>'); return out.join(''); }
    if (d.arrange && this._arranged) {
      out.push('<button type="button" class="dd-act" data-act="copy-layout" title="Copy the .base with this arrangement as its layout:">Copy layout</button>');
      out.push('<button type="button" class="dd-act" data-act="reset-layout" title="Forget this browser\'s arrangement and draw the file\'s layout">Reset layout</button>');
    }
    if (d.arrange) out.push('<button type="button" class="dd-act" data-act="arrange" aria-pressed="false" title="Drag and resize the panels; your arrangement is kept in this browser and offered back as the .base\'s layout:">Arrange</button>');
    return out.join('');
  }

  _rerunUrl() {
    const d = this.dash;
    // baseUrl: a host that loads the .base itself (an analysis) says where it lives; else src, else the page
    try { return new URL(d.rerun.rrd, this.baseUrl || new URL(this.getAttribute('src') || location.href, location.href)).href; } catch { return null; }
  }

  _wireActions() {
    const bar = this.querySelector('.dd-actions');
    if (!bar) return;
    const d = this.dash;
    if (d.rerun) {
      const url = this._rerunUrl(), sdk = d.rerun.sdk || '0.40.0';
      const pop = bar.querySelector('.dd-rerun .dd-pop');
      // WHY the hosted viewer by link, never embedded: its wasm is 54 MB and lives on another origin; a link the
      // reader clicks loads nothing into this page (vault: Tracking-Run Data — data-ui vs Rerun, § Launching it)
      pop.querySelector('[data-rr=web]').href = `https://app.rerun.io/version/${sdk}/index.html?url=${encodeURIComponent(url)}`;
      pop.querySelector('[data-rr=download]').href = url;
      this._rerunCommand = `uvx --from rerun-sdk==${sdk} rerun ${url}`;
      // a generated file may be missing on a fresh clone (tools/rerun_export.py writes it): say so instead of a 404
      fetch(url, { method: 'HEAD' }).then((r) => { if (!r.ok) this._rerunMissing(bar); }).catch(() => this._rerunMissing(bar));
    }
  }

  _rerunMissing(bar) {
    const b = bar.querySelector('[data-act=rerun]');
    if (!b) return;
    b.disabled = true;
    b.title = `No .rrd yet: run  uv run --script tools/rerun_export.py ${this.getAttribute('src') || '<views.base>'}  (it writes ${this.dash.rerun.rrd})`;
  }

  async _onAction(act, btn) {
    if (act === 'edit') {
      btn.disabled = true;
      try { await this.edit(); } catch (err) { console.error('data-ui: the dashboard editor did not load', err); } finally { btn.disabled = false; }
      return;
    }
    if (this._editor && act.startsWith('edit-')) { this._editor.act(act, btn); return; }
    if (act === 'rerun') {
      const pop = btn.parentElement.querySelector('.dd-pop');
      const open = pop.hidden;
      pop.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      return;
    }
    if (act === 'copy-layout') {
      const text = this.layoutText();
      navigator.clipboard?.writeText(text).catch(() => {});
      btn.textContent = 'Copied';
      this.dispatchEvent(new CustomEvent('data-dashboard-layout', { detail: { layout: this.base.layout, text } }));
      return;
    }
    if (act === 'reset-layout') { this.setArrangement(null); return; }
    if (act === 'arrange') {
      const on = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? 'Done' : 'Arrange';
      // WHY a separate bundle: gridstack is only needed by the reader who rearranges (dist/dashboard-arrange.js)
      const mod = await import(/* @vite-ignore */ new URL('./dashboard-arrange.js', import.meta.url).href);
      await mod.arrange(this, on);
    }
  }

  // ------------------------------------------------------------------ live data (datasets.<name>.refresh)

  _startRefresh() {
    this._stopRefresh();
    const src = this.getAttribute('src');
    if (!src) return;
    for (const d of Object.values(this.dash.datasets)) {
      if (!d.refresh) continue;
      const href = new URL(d.data, new URL(src, location.href)).href;
      const timer = setInterval(() => this._refetch(d.name, href), d.refresh);
      (this._refreshers ||= []).push(timer);
    }
  }

  _stopRefresh() { for (const t of this._refreshers || []) clearInterval(t); this._refreshers = []; }

  /** Re-read one dataset; when its rows changed, every panel on it gets them in place (view, scroll, selections, the
      rails, the clock and the drill-down stay). */
  async _refetch(name, href) {
    if (typeof document !== 'undefined' && document.hidden) return;   // a background tab does not poll
    try {
      const res = await fetch(href, { cache: 'no-store' });
      if (!res.ok) return;
      const text = await res.text();
      if (this._lastText && this._lastText[name] === text) return;
      (this._lastText ||= {})[name] = text;
      // the body already fetched answers the data file; a sidecar (schema) is fetched fresh
      const ds = await loadDataset(href, { fetch: (u) => (u === href ? Promise.resolve(new Response(text)) : fetch(u, { cache: 'no-store' })) });
      this.datasets[name] = { ...ds, url: href };
      for (const p of this.dash.panels) if (p.dataset === name && this.panelEls[p.key]) this.panelEls[p.key].data = this.datasets[name];
      this.dataset.refreshed = String((Number(this.dataset.refreshed) || 0) + 1);
      this._update();
      this.dispatchEvent(new CustomEvent('data-dashboard-refresh', { detail: { dataset: name, rows: ds.rows.length } }));
    } catch { /* a failed poll keeps the last rows */ }
  }

  _hint() {
    const n = this.dash.panels.filter((p) => p.views.some((v) => v.select)).length;
    return n ? `Click a mark, card or row in a panel marked "click to filter" to filter the whole dashboard.` : '';
  }

  _markPanels() {
    for (const p of this.dash.panels) {
      const sec = this.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"]`);
      const el = this.panelEls[p.key];
      if (!sec || !el) continue;
      const view = (el.view && p.views.find((v) => v.name === el.view.name)) || p.views[0];
      // a picker's click moves its rail's pick (CONTRACT §33): it says "click to pick", not "click to filter"
      if (view && view.select && p.picks === view.select) { sec.dataset.pick = view.select; delete sec.dataset.select; }
      else if (view && view.select) { sec.dataset.select = view.select; delete sec.dataset.pick; }
      else { delete sec.dataset.select; delete sec.dataset.pick; }
    }
  }

  _feedSource(src, d) {
    const data = this.datasets[d.name];
    src._data = data;
    src._rev = (src._rev || 0) + 1;
    src._base = { facets: d.facets, properties: (this.base && this.base.properties) || {}, filters: d.filters };
    // the rail's counts see every restriction except its own rail: selections and the other datasets, through links
    const without = { ...this.state, rail: { ...this.state.rail, [d.name]: undefined } };
    src._view = { filters: panelFilter(this.dash, this.datasets, without, d.name, null) };
    src._model = { matched: keep(data.rows, panelFilter(this.dash, this.datasets, this.state, d.name, null)).length, total: data.rows.length };
    // WHY: a rail waits for its target's first draw (data-views' data-view); this source is ready as soon as it is fed
    if (!src.dataset.view) { src.dataset.view = d.name; src.dispatchEvent(new CustomEvent('data-views-render')); }
  }

  /** Recompute roll-ups and every panel's filter, then the rails, the chips and the URL. */
  _update() {
    const d = this.dash;
    if (!d) return;
    // CONTRACT §33: the per-pick files first, so the filters, the layers, the rails and the clock below read the run
    // the picks name now (a file read before swaps in here; a new one is fetched and arrives in a later _update)
    const swapped = this._resolveFiles();
    const rolled = new Set(Object.values(d.datasets).filter((x) => x.rollup).map((x) => x.name));
    // on live data, the rows as of the clock's t (CONTRACT §17 addendum; live.js watchRollups keeps them so as t moves)
    applyRollups(d, this.datasets, this.state, { t: rollupTime(this) });
    for (const p of d.panels) {
      const el = this.panelEls[p.key];
      if (!el) continue;
      const f = panelFilter(d, this.datasets, this.state, p.dataset, p.key);
      // CONTRACT §32: its layers first; <data-views> redraws for them after this task, so a click that also changes the
      // filter below draws the panel once
      this._handLayers(p, el, (p.layers || []).some((name) => rolled.has(name) || swapped.has(name)));
      // WHY always for a rolled-up dataset: its cells changed in place, so the panel must redraw even when its filter
      // did not
      if (rolled.has(p.dataset)) {
        // the roll-up rewrote cells in place: hand the data over again (data-views' rule: a host that changes rows
        // gives new data), so its cached row model (perf core 5) is rebuilt; then the filter
        el.filters = f;
        el.data = this.datasets[p.dataset];
      } else if (!same(f, el.filters)) el.filters = f;
      const sel = this.state.select[p.key];
      const label = this.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"] .dd-sel`);
      if (label) label.textContent = sel ? `selected: ${sel.values.map((v) => this._valueText(p.dataset, sel.property, v)).join(', ')}` : '';
    }
    // the clock spans what the filters now leave (gap #1); the URL below then holds its t as placed
    this._spanClock();
    for (const [name, src] of Object.entries(this.sources)) {
      this._feedSource(src, d.datasets[name]);
      src.dispatchEvent(new CustomEvent('data-views-change', { detail: { filters: clone(this.state.rail[name]) } }));
    }
    this._drawChips();
    this._showWaits();
    this._markRows();
    this._writeUrl();
    this.dispatchEvent(new CustomEvent('data-dashboard-change', { detail: { state: clone(this.state) } }));
  }

  // ------------------------------------------------------------------ per-pick files (docs/CONTRACT.md §33)

  /** Where a per-pick file is resolved from: the .base's URL (src), else the host's baseUrl, else the page. */
  _baseHref() { return this._srcUrl || (this.baseUrl ? new URL(this.baseUrl, location.href).href : location.href); }

  /** The file this dashboard declares for dataset `name`, as a URL (model.js declaredFile; CONTRACT §34): its data:
      resolved by the rule above (a host that draws a .base itself with load() says where it lives in baseUrl), a
      per-pick dataset's the one file its picks read; null while that is none. */
  _declaredFile(name) {
    const f = this._files && this._files[name];
    return declaredFile(this.dash, name, { base: this._baseHref(), picked: f && f.status === 'ok' ? f.href : null });
  }

  /** A per-pick dataset with no rows: what its panels hold while no run (or two) is picked, or a file is on its way.
      The same object until a file teaches it the dataset's columns, so a panel is not redrawn for nothing. */
  _blank(name) {
    if (!this._blanks[name]) {
      const d = this.dash && this.dash.datasets[name];
      this._blanks[name] = { ...normalizeDataset({ properties: {}, rows: [] }, { id: name }), title: (d && d.label) || name, url: null };
    }
    return this._blanks[name];
  }

  /** Hand a dataset object to everything that reads it (its panels; the rail, layers and clock read this.datasets). */
  _swapData(name, ds) {
    if (this.datasets[name] === ds) return false;
    this.datasets[name] = ds;
    for (const p of this.dash.panels) if (p.dataset === name && this.panelEls[p.key]) this.panelEls[p.key].data = ds;
    return true;
  }

  /** For every per-pick dataset: the file its picks name now (model.js templateFile), from the files read before, or
      fetched once (in flight: the same fetch). Returns the names whose dataset object changed. */
  _resolveFiles() {
    const swapped = new Set();
    for (const ds of Object.values(this.dash.datasets)) {
      if (!ds.template || (this.datasets[ds.name] && this.datasets[ds.name] !== this._blanks[ds.name] && !this._files[ds.name])) continue;
      const f = templateFile(this.dash, this.datasets, this.state, ds.name);
      const cur = this._files[ds.name];
      // the same file: drawn already, said why not, or on its way (a fetch in flight answers it); one that arrived
      // while the element was off the page is in the cache and swaps in below. WHY a failed file stays failed for its
      // path: every click would fetch it again; picking another run and back asks once more
      if (cur && cur.path === f.path && (cur.status !== 'loading' || this._inflight.has(cur.href))) { cur.choices = f.choices; continue; }
      const want = { ...f, href: f.path ? new URL(f.path, this._baseHref()).href : null, status: f.path ? 'loading' : 'pick', error: null };
      this._files[ds.name] = want;
      const hit = want.href && this._fileCache.get(want.href);
      if (hit) {
        // the newest last: the cache keeps the files read most recently
        this._fileCache.delete(want.href);
        this._fileCache.set(want.href, hit);
        want.status = 'ok';
        if (this._swapData(ds.name, hit)) swapped.add(ds.name);
        continue;
      }
      if (this._swapData(ds.name, this._blank(ds.name))) swapped.add(ds.name);
      if (want.href) this._fetchFile(ds.name, want);
    }
    return swapped;
  }

  _fetchFile(name, want) {
    let job = this._inflight.get(want.href);
    if (!job) {
      job = loadDataset(want.href).then((ds) => {
        const out = { ...ds, url: want.href };
        this._fileCache.set(want.href, out);
        // WHY a bound: a reader flipping through runs keeps the last few in memory, not every run of a deployment
        while (this._fileCache.size > 12) this._fileCache.delete(this._fileCache.keys().next().value);
        return out;
      }).finally(() => this._inflight.delete(want.href));
      this._inflight.set(want.href, job);
    }
    job.then((ds) => {
      // the picks moved on while it loaded, or the element left the page (it swaps in from the cache when put back)
      if (this._files[name] !== want || !this.dash || !this.isConnected) return;
      want.status = 'ok';
      // the blank learns the file's columns, so the next "Pick one run" keeps the rail's and the views' columns
      this._blanks[name] = { ...normalizeDataset({ properties: ds.properties || {}, rows: [] }, { id: name }), title: ds.title || name, url: null };
      this._swapData(name, ds);
      this._update();
    }, (err) => {
      if (this._files[name] !== want || !this.dash) return;
      want.status = 'error';
      want.error = (err && err.message) || String(err);
      this._update();
    });
  }

  /** The line a panel on a per-pick dataset shows in place of its view while it has no file: "Pick one run" (none
      picked, two or more, or picks that leave none), "Loading run …", or why the file did not load. */
  _waitText(name, f) {
    const d = this.dash.datasets[name];
    const ps = (d && d.template) || [];
    const word = (p) => String(p).replace(/_/g, ' ');
    if (f.status === 'loading') return `<b>Loading ${esc(word(ps[0]))} ${esc(ps.map((p) => this._choiceName(name, p, f.values[p])).join(' · '))}…</b>`;
    if (f.status === 'error') return `<b>Could not load ${esc(f.path || d.data)}</b><span>${esc(f.error || '')}</span>`;
    const p = ps.find((x) => !Array.isArray(f.choices[x]) || f.choices[x].length !== 1) || ps[0];
    const c = f.choices[p];
    const why = c === null || c === undefined ? 'none is picked'
      : !c.length ? `the picks leave no ${word(p)}`
        : `${c.length} are picked: ${c.slice(0, 3).map((v) => this._choiceName(name, p, v)).join(', ')}${c.length > 3 ? ', …' : ''}`;
    return `<b>Pick one ${esc(word(p))}</b><span>${esc(why)}</span>`;
  }

  /** A placeholder's value as the reader knows it: named on the far side of the link that carries it (a run's label). */
  _choiceName(name, p, v) {
    const l = this.dash.links.find((x) => x.b.ds === name && x.b.col === p && x.a.ds !== name) || this.dash.links.find((x) => !x.oneWay && x.a.ds === name && x.a.col === p && x.b.ds !== name);
    if (!l) return String(v);
    const end = l.b.ds === name ? l.a : l.b;
    return this._valueText(end.ds, end.col, v);
  }

  /** Each panel on a per-pick dataset that has no file yet shows _waitText over its view (the view is hidden). */
  _showWaits() {
    for (const p of this.dash.panels) {
      const sec = this.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"]`);
      if (!sec) continue;
      const ds = p.dataset && this.dash.datasets[p.dataset];
      const f = ds && ds.template ? this._files[p.dataset] : null;
      const box = this._boxOf(sec);
      let w = box.querySelector(':scope > .dd-wait');
      if (!f || f.status === 'ok') {
        if (w) w.remove();
        delete sec.dataset.wait;
        continue;
      }
      if (!w) {
        w = document.createElement('div');
        w.className = 'dd-wait';
        w.setAttribute('role', 'status');
        box.append(w);
      }
      sec.dataset.wait = f.status;
      const html = this._waitText(p.dataset, f);
      if (w.innerHTML !== html) w.innerHTML = html;
      this._placeWait(sec, w);
      if (typeof ResizeObserver !== 'undefined') {
        this._waitRO ||= new ResizeObserver((entries) => { for (const e of entries) { const wait = this._boxOf(e.target).querySelector(':scope > .dd-wait'); if (wait) this._placeWait(e.target, wait); } });
        this._waitRO.observe(sec);
      }
    }
  }

  /** Where a panel's content sits: the panel, or gridstack's box inside it while arranging or editing. */
  _boxOf(sec) { return sec.querySelector(':scope > .grid-stack-item-content') || sec; }

  /** The wait line covers the panel's view exactly (its title stays): the view's own box, measured. */
  _placeWait(sec, w) {
    const el = this._boxOf(sec).querySelector(':scope > data-views');
    if (!el) return;
    w.style.left = `${el.offsetLeft}px`;
    w.style.top = `${el.offsetTop}px`;
    w.style.width = `${el.offsetWidth}px`;
    w.style.height = `${el.offsetHeight}px`;
  }

  /** The rows a panel picked (its selection, or a picker's rail pick) are marked in its table (CONTRACT §33), on its map
      and on its cards (§39). WHY a bound: a selection of a value thousands of rows share is a filter, not a row to find
      again; it goes unmarked. */
  _markRows() {
    for (const p of this.dash.panels) {
      const sec = this.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"]`);
      if (!sec) continue;
      const sel = this.state.select[p.key];
      const prop = p.picks || (sel && sel.property);
      const table = p.views.some((v) => (v.type || 'table') === 'table');
      const themselves = p.views.some((v) => MARK_THEMSELVES.has(v.type));
      const values = !table && !themselves ? [] : p.picks ? railPicks(this.dash, this.datasets, p.dataset, this.state.rail[p.dataset], p.picks) : sel ? sel.values : [];
      const ds = this.datasets[p.dataset];
      const want = new Set((values || []).map(String));
      let ids = prop && want.size && ds ? ds.rows.filter((r) => { const v = cellValue(r[prop]); return Array.isArray(v) ? v.some((x) => want.has(String(x))) : want.has(String(v)); }).map((r) => r.id) : [];
      if (ids.length > 500) ids = [];
      // WHY on the element, not the view: the picks outlive a tab switch, and a new view reads them in input.selected
      if (themselves && this.panelEls[p.key]) this.panelEls[p.key].picked = ids;
      let st = sec.querySelector(':scope > style[data-dd-marks]');
      if (!table || !ids.length) { if (st) st.remove(); continue; }
      if (!st) { st = document.createElement('style'); st.dataset.ddMarks = ''; sec.prepend(st); }
      const scope = `.dd-panel[data-panel="${CSS.escape(p.key)}"]`;
      const css = `${ids.map((id) => `${scope} tbody tr[data-id="${CSS.escape(String(id))}"] > td`).join(',\n')} { background: var(--dd-mark); }`;
      if (st.textContent !== css) st.textContent = css;
    }
  }

  /** The views' selected: presets (CONTRACT §33), for the panels the URL names no selection of (the URL's cleared
      ones too): selections, and a picker's preset as a pick on its rail when the rail picks nothing there yet. */
  _applyPresets() {
    const got = presets(this.dash, this.datasets, this.state, this._cleared || []);
    Object.assign(this.state.select, got.select);
    Object.assign(this.state.rail, got.rail);
  }

  /** Where a key column's values are named: the row's own title for its id, or the title of the row a link points
      at (runs.track → tracks.id → "Vibe Tracks"). null when the values are their own names. */
  _namer(dataset, property) {
    const ds = this.datasets[dataset];
    if (ds && property === 'id' && ds.titleProperty) return { ds, col: 'id' };
    // WHY a key only (found with P3's deployments → runs → samples): a value names a row only where it is that row's
    // own key; through a link to a column many rows share (runs.deployment, a run's samples) it named the first such
    // row ("selected: CAN 12 · waypoints · s14" for the rack, "selected: 0" for a run)
    const key = (d, col) => { const seen = new Set(); for (const r of d.rows) { const v = String(cellValue(r[col])); if (seen.has(v)) return false; seen.add(v); } return true; };
    if (ds && ds.titleProperty && ds.titleProperty !== property && ds.rows.length && key(ds, property)) return { ds, col: property };
    for (const l of this.dash.links) {
      for (const [x, y] of [[l.a, l.b], [l.b, l.a]]) {
        const other = this.datasets[y.ds];
        if (x.ds === dataset && x.col === property && other && other.titleProperty && key(other, y.col)) return { ds: other, col: y.col, name: y.ds };
      }
    }
    return null;
  }

  _valueText(dataset, property, v) {
    // a selection on a key reads as the row's title ("Five-Bar Arm Regression", not "fivebar")
    const n = this._namer(dataset, property);
    if (n) {
      const row = n.ds.rows.find((r) => String(cellValue(r[n.col])) === String(v));
      if (row) return cellText(row[n.ds.titleProperty]) ?? String(cellValue(row[n.ds.titleProperty]) ?? v);
    }
    // WHY the property's declared rounding: a chip or a "selected:" label reads the number as the cells it came from do
    if (typeof v !== 'number') return String(v);
    const p = this.datasets[dataset] ? labelled(this.datasets[dataset], this.base)[property] : null;
    return String(fmtNum(v, undefined, numOpts(p)));
  }

  _propText(dataset, property) {
    const own = labelled(this.datasets[dataset], this.base)[property];
    if (own && own.label !== property) return own.label;
    const n = this._namer(dataset, property);
    if (n) { const t = labelled(n.ds, this.base)[n.ds.titleProperty]; if (t) return t.label; }
    return (own && own.label) || property;
  }

  _drawChips() {
    const box = this.querySelector('.dd-chips');
    if (!box) return;
    const chips = Object.entries(this.state.select).map(([key, s]) => {
      const p = this.dash.panels.find((x) => x.key === key);
      const label = this._propText(s.dataset, s.property);
      const vals = s.values.map((v) => this._valueText(s.dataset, s.property, v));
      return `<button type="button" class="dd-chip" data-clear="${esc(key)}" title="From ${esc((p && (p.title || p.views[0].name)) || key)}: click to clear"><span>${esc(label)}</span> <b>${esc(vals.slice(0, 4).join(', '))}${vals.length > 4 ? ` +${vals.length - 4}` : ''}</b><span class="dd-x" aria-hidden="true">✕</span><span class="dv-sr">clear</span></button>`;
    });
    box.innerHTML = chips.length ? `${chips.join('')}${chips.length > 1 ? '<button type="button" class="dv-link dd-clear-all">Clear all</button>' : ''}` : '';
    if (!this._chipsWired) {
      this._chipsWired = true;
      this.addEventListener('click', (e) => {
        const chip = e.target.closest('.dd-chip');
        if (chip && this.contains(chip)) { this.select(chip.dataset.clear, null, []); return; }
        if (e.target.closest('.dd-clear-all')) this.clearSelections();
      });
    }
  }

  // ------------------------------------------------------------------ clicks: select or drill
  _clicked(p, el, rowId, opts, own) {
    const view = (el.view && p.views.find((v) => v.name === el.view.name)) || el.view || {};
    const prop = view.select;
    const add = this._addPick;
    this._addPick = false;
    if (prop) {
      const rows = opts.records && opts.records.length ? opts.records : [opts.row || el.row(rowId)].filter(Boolean);
      const values = [...new Map(valuesOf(rows, prop).map((v) => [String(v), v])).values()];
      // a picker (CONTRACT §33): the click moves its rail's one pick, as the rail's own radio does
      if (p.picks === prop) {
        if (values.length) this.setRail(p.dataset, pickRail(this.dash, this.datasets, this.state.rail[p.dataset], p.dataset, prop, values[0]));
        return;
      }
      const cur = this.state.select[p.key];
      // a ctrl / cmd-click adds what it clicked to the selection, or takes it out (Power BI's multi-select)
      if (add && cur && cur.property === prop) {
        const next = [...cur.values];
        for (const v of values) {
          const i = next.findIndex((x) => String(x) === String(v));
          if (i >= 0) next.splice(i, 1); else next.push(v);
        }
        this.select(p.key, prop, next);
        return;
      }
      const toggleOff = cur && cur.property === prop && same([...cur.values].map(String).sort(), values.map(String).sort());
      this.select(p.key, prop, toggleOff ? [] : values);
      return;
    }
    // WHY not while editing: a click there selects the panel; a peek opening over the panes would answer another question
    if (!this._editor) this.drill(p, el, rowId, opts);
  }

  /** Open a row (or a group's records) in the dashboard's one side peek. */
  drill(p, el, rowId, opts = {}) {
    let drill = this._drillEl;
    if (!drill) {
      drill = this._drillEl = document.createElement('data-views');
      drill.className = 'dd-drill';
      drill.id = `${this.id}-drill`;
      drill.setAttribute('no-url', '');
      drill.setAttribute('toolbar', 'none');
      this.append(drill);
    }
    const view = clone(el.view || p.views[0]);
    drill._ds = p.dataset;
    drill.filters = undefined;
    // the drill's one view is the panel's current one as a table, so its record sections and edit keys apply
    drill.data = this.datasets[p.dataset];
    // CONTRACT §35: the datasets the view's record sections embed (the evidence), as their files hold them
    drill.sections = Object.fromEntries(sectionSources(view).filter((n) => this.datasets[n]).map((n) => [n, this.datasets[n]]));
    drill.base = { properties: (this.base && this.base.properties) || {}, views: [{ ...view, type: 'table', name: view.name || 'Details' }] };
    drill.openPeek(rowId, opts);
  }

  // ------------------------------------------------------------------ the URL
  _railUrl(name) {
    const d = this.dash.datasets[name];
    const data = this.datasets[name];
    const props = labelled(data, this.base);
    const specs = facetSpecs({ facets: d.facets }, null, props);
    const known = new Set();
    for (const s of specs) for (const q of [s.property, ...(s.levels || []), ...(s.properties || [])]) if (q) known.add(q);
    return { props, specs, known, config: railConfig(specs), prefix: name === this.dash.defaultName ? '' : `${name}.` };
  }

  _owns(key, name) {
    const { known, prefix } = this._railUrl(name);
    if (prefix && !key.startsWith(prefix)) return false;
    if (!prefix && Object.keys(this.dash.datasets).some((n) => n !== name && key.startsWith(`${n}.`))) return false;
    const k = key.slice(prefix.length);
    if (k === 'has' || k === 'hasany') return true;
    return known.has(/[!~^]$/.test(k) ? k.slice(0, -1) : k);
  }

  _readUrl() {
    if (this.hasAttribute('no-url')) return;
    try {
      const q = new URLSearchParams(location.search);
      const h = new URLSearchParams(location.hash.slice(1));
      for (const name of Object.keys(this.sourcesWanted())) {
        const { props, known, config, prefix } = this._railUrl(name);
        const entries = [...q.entries()].filter(([k]) => this._owns(k, name)).map(([k, v]) => [k.slice(prefix.length), v]);
        const facets = paramsRail(entries, props, known, config);
        const custom = h.get(`f.${name}`) ? decodeView(h.get(`f.${name}`)) : null;
        if (Object.keys(facets).length || custom) {
          const file = toRail(this.dash.datasets[name].filters, config);
          this.state.rail[name] = fromRail(Object.keys(facets).length ? facets : file.facets, custom ? custom.rest : file.rest);
        }
      }
      const { select, tabs, legend, cleared } = readHash(location.hash.slice(1), this.dash.panels, this._legendKey());
      this.state.select = select;
      this.state.tabs = tabs;
      this.state.legend = legend;
      // CONTRACT §33: a preset the reader cleared (s.<panel>=) stays cleared
      this._cleared = cleared;
    } catch { /* a malformed link draws the file's own state */ }
  }

  /** Back / Forward or an edited fragment (CONTRACT §33): the rails, selections, tabs, clock and legend become what a
      fresh load of this URL gives (presets where it names no selection), and nothing is written back. WHY the picks
      first: the clock's span is the rows they leave, so t is placed after them (a file read before swaps in at once; a
      new one arrives later and the clock re-places t from the URL's instant, as a link does). */
  _navigate() {
    if (!this.dash || this.hasAttribute('no-url')) return;
    this._navigating = true;
    try {
      const before = JSON.stringify([this.state.rail, this.state.select, this.state.tabs]);
      for (const d of Object.values(this.dash.datasets)) this.state.rail[d.name] = clone(d.filters);
      this.state.select = {};
      this.state.tabs = {};
      this._cleared = [];
      this._readUrl();
      this._applyPresets();
      if (JSON.stringify([this.state.rail, this.state.select, this.state.tabs]) !== before) {
        this._applyTabs();
        this._update();
      }
      this._readClockUrl();
      this._readLegendUrl();
    } finally {
      this._navigating = false;
    }
  }

  /** Each panel shows the tab its state names (a navigation). */
  _applyTabs() {
    for (const p of this.dash.panels) {
      const el = this.panelEls[p.key];
      if (!el || p.views.length < 2) continue;
      const want = (this.state.tabs[p.key] && p.views.find((v) => slug(v.name) === this.state.tabs[p.key])) || p.views[0];
      if (el.view && el.view.name !== want.name && typeof el.selectView === 'function') el.selectView(want.name);
    }
    this._markPanels();
    this._resolveDriver();
  }

  /** The legend's URL scope: the clock's key (null: one dashboard on the page, a string with several, false: no unique
      key, so not in the URL; _clockKey), the same for a dashboard without a clock. */
  _legendKey() {
    return this.hasAttribute('no-url') ? false : this._clockKey();
  }

  /** Back / Forward or an edited fragment: each panel's hidden series become the URL's (no write back, as the clock). */
  _readLegendUrl() {
    if (!this.dash || this.hasAttribute('no-url')) return;
    const key = this._legendKey();
    if (key === false) return;
    let legend;
    try { legend = readHash(location.hash.slice(1), this.dash.panels, key).legend; } catch { return; }
    this.state.legend = legend;
    for (const [k, el] of Object.entries(this.panelEls)) {
      const want = legend[k] || [];
      if (!same(want, el.hiddenSeries)) el.hiddenSeries = want;
    }
  }

  sourcesWanted() {
    return Object.fromEntries(Object.values(this.dash.datasets).filter((x) => Array.isArray(x.facets) && x.facets.length && this.datasets[x.name]).map((x) => [x.name, x]));
  }

  _writeUrl() {
    // CONTRACT §33: a pick pushes one history entry; everything else (t, a tab, the legend, a file arriving) replaces
    // the entry it is on, and a navigation being applied writes nothing
    const push = this._push;
    this._push = false;
    if (this.hasAttribute('no-url') || this._navigating) return;
    try {
      const q = new URLSearchParams(location.search);
      const h = writeHash(location.hash.slice(1), this.state, this.dash.panels, this._legendKey());
      const key = this.clock && (this.dash.clock || this.clock.live) ? this._clockKey() : false;
      if (key !== false) {
        writeClockParams(h, this.clock, key);
        // a live clock writes t=live while following, so a shared link lands live, and its t while paused even at
        // the start, since no t follows live (docs/peps/0012-live-data.md §4)
        const lt = liveHash(this.clock);
        if (lt !== null) h.set(key ? `t.${key}` : 't', lt);
      }
      for (const name of Object.keys(this.sourcesWanted())) {
        const { config, prefix } = this._railUrl(name);
        for (const k of [...q.keys()]) if (this._owns(k, name)) q.delete(k);
        const now = toRail(this.state.rail[name], config);
        const file = toRail(this.dash.datasets[name].filters, config);
        if (!same(now.facets, file.facets)) for (const [k, v] of railParams(now.facets)) q.append(prefix + k, v);
        // WHY a blob for the rest: a custom clause (an ||, a !=) has no readable form; the facet part keeps one
        if (!same(now.rest, file.rest)) h.set(`f.${name}`, encodeView({ rest: now.rest })); else h.delete(`f.${name}`);
      }
      const search = q.toString().replace(/%2C/gi, ',').replace(/%21/g, '!').replace(/%7E/gi, '~').replace(/%5E/gi, '^');
      const hash = h.toString().replace(/%2C/gi, ',').replace(/%3A/gi, ':').replace(/%7E/gi, '~');
      const next = `${location.pathname}${search ? '?' + search : ''}${hash ? '#' + hash : ''}`;
      if (push && next !== `${location.pathname}${location.search}${location.hash}`) history.pushState(history.state, '', next);
      else history.replaceState(history.state, '', next);
    } catch { /* a sandboxed frame without history: the dashboard still works, unshared */ }
  }
}

if (!customElements.get('data-dashboard')) customElements.define('data-dashboard', DataDashboard);
