/* A <data-views> on a live dataset (docs/peps/0012-live-data.md §5, §8; docs/CONTRACT.md §26).

   `viewsEl.data = liveDataset` hands the element to a LiveFeed. The feed gives the element the rows at the clock's t
   (live/model.js: a Tail for a flat time-ordered view, the full way for the rest at most every 250 ms) and redraws the
   view through the frame loop (live/frame.js): at most once per animation frame, and only when something it shows
   changed. Paused (or replaying), only news at or before t can change what a view shows (pausedNews below): a version
   or row after t never redraws it (Rerun repaints for data at or before its time cursor).

   The tail (Datadog's Live Tail, RobotDx's Activity log): a table or list on an append dataset follows its newest end
   (the top under sort: t DESC, else the bottom); scrolled more than a row away from it, or with a row open in the peek,
   it holds its rows and says "N new · Resume". Only that panel holds; the clock keeps following.

   The element carries data-live="following | paused | held" and fires data-views-live {t, following, rows, ms, frame}
   after each live draw. */

import { isLiveDataset, parseDuration } from './store.js';
import { LiveClock, isLiveClock } from './clock.js';
import { markFeed, liveFrame } from './frame.js';
import { Tail, snapshotModel, LIVE_CAP } from './model.js';
import { clockFor } from '../clock.js';
import { tableModel, properties as labelled } from '../rowmodel.js';

/** Views that read the store themselves (input.live) and get no row objects. */
export const LIVE_NATIVE = new Set(['plot', 'levels']);
/** Views that read no rows at all: no live redraws. */
export const LIVE_IGNORE = new Set(['playback']);
const TAIL_TYPES = new Set(['table', 'list']);
const FULL_EVERY = 250;   // ms between full re-models of a grouped / tree / pivot live view

/** What a view shows at t (docs/peps/0012-live-data.md §5.1): its `at:`, else the default for its type and dataset. */
export function atOf(view, ds) {
  const at = view && view.at;
  if (at === 'latest' || at === 'all') return at;
  if (at !== undefined && at !== null && parseDuration(at) !== null) return parseDuration(at);
  if (ds && ds.keyed) return 'latest';
  if (view && LIVE_NATIVE.has(view.type)) return ds && ds.recorded ? 'all' : 30;
  return 'all';
}

/**
 * Paused at t, what one frame's news (a dataset's `change` detail) does to a view (docs/peps/0012-live-data.md §8):
 *   'draw'   the rows it shows at t can have changed: a row, version or removal written at or before t inside its
 *            window (a late one), retention taking a row it read at t (a plot or levels card: any sample in its span),
 *            a reset, the recording ending, or a drop log that no longer reaches back (it cannot tell)
 *   'count'  retention took rows at t that it did not read: only the status line's count moved
 *   null     nothing at t moved; above all, whatever arrived after t
 * WHY: RobotDx, 2026-10-27: paused at t, every upsert to a keyed dataset redrew its views at the same t, 230-440 ms
 * apart, though every new version lay after t (the old rule redrew on any upsert, removal or drop).
 *   drops     ds.dropsSince(the gen at the view's last look): [{stream, seqMin, seqMax, t0, t1}], or null
 *   at        atOf(view): 'latest' | 'all' | seconds — a window ends at t: (t − at, t]
 *   native    the view reads the store itself (plot, levels); `zoom` its clock's zoom window, which may reach past t
 *   read      the store's rows the view read at t (each with its hidden arrival number _seq); streamOf(row) → its stream
 *             (a keyed dataset's: the key)
 */
export function pausedNews(change, { drops = [], t, at = 'all', native = false, zoom = null, read = [], streamOf = () => '' } = {}) {
  if (!change || change.reset || change.recorded || drops === null) return 'draw';
  let lo = typeof at === 'number' ? t - at : -Infinity, hi = t;
  if (native && zoom) { lo = Math.min(lo, zoom[0]); hi = Math.max(hi, zoom[1]); }
  const wrote = (change.appended || 0) + (change.upserted || 0) + (change.removed || 0);
  // from / to: the oldest and newest time written this frame; all after hi, or all at or before the window's start
  // (a window is open there), and no row of it is at t
  if (wrote && !(change.from > hi) && !(change.to <= lo)) return 'draw';
  let count = false;
  for (const x of drops) {
    if (x.t0 > hi || x.t1 <= lo) continue;
    if (native) return 'draw';
    for (const r of read) {
      if (r._seq >= x.seqMin && r._seq <= x.seqMax && (x.stream === null || x.stream === undefined || streamOf(r) === x.stream)) return 'draw';
    }
    count = true;
  }
  return count ? 'count' : null;
}

/** The element's `data` setter calls this first: true when it took the dataset (a live one). */
export function liveData(el, d) {
  if (isLiveDataset(d)) {
    if (el._live && el._live.ds === d) { el._live.refresh(); return true; }
    if (el._live) el._live.detach();
    el._live = new LiveFeed(el, d);
    return true;
  }
  if (el._live) { el._live.detach(); el._live = null; }
  return false;
}

export class LiveFeed {
  constructor(el, ds) {
    this.el = el;
    this.ds = ds;
    this.clock = null;
    this.tail = null;
    this.tailKey = null;
    this.full = null;
    this.fullAt = 0;
    this.held = false;
    this.holdSeq = 0;
    this.lastT = null;
    this.lastFollowing = null;
    this.dirty = true;
    this._gen = ds.dropGen;      // the drop log as of this view's last look (pausedNews)
    // a row's stream, as the drop log names it: a keyed row's key (its id), else the stream property's value
    this._streamOf = ds.keyed ? (r) => r.id : ds.stream ? (r) => r[ds.stream] : () => '';
    this._onChange = (e) => this._changed(e.detail);
    this._onTime = () => this._mark();
    this._onState = () => this._mark();
    this._onScroll = () => this._scrolled();
    this._scroller = null;
    ds.addEventListener('change', this._onChange);
    // the element reads its rows from this plain dataset; its rows are the snapshot the view shows now
    el._data = { id: ds.id, title: ds.title, titleProperty: ds.titleProperty, linkProperty: ds.linkProperty, imageProperty: ds.imageProperty, properties: ds.properties, rows: [], url: ds.url || null, live: true };
    // the data as loaded is this snapshot too: a live dataset carries no multi-source cells (CONTRACT §36)
    el._raw = el._data; el._precInfo = null; el._prec = null;
    el._dataUrl = ds.url || null;
    el._byId = null;
    el._seed = null;
    el._dropWorker();
    el._revise();
    this.connect();
    if (el._started) el._render(); else el._start();
  }

  /** The clock this view follows: its dashboard's (a LiveClock), else one of its own (a lone <data-views>). */
  _clock() {
    let c = clockFor(this.el);
    if (!isLiveClock(c)) {
      // WHY on the element: clockFor() looks at the element itself first, so the cards inside it find this clock
      c = this.el.clock instanceof LiveClock ? this.el.clock : (this.el.clock = new LiveClock({ loop: false }));
    }
    return c;
  }

  connect() {
    if (this.clock || !this.el.isConnected) { if (this.clock) markFeed(this); return; }
    this.clock = this._clock();
    this.clock.bind(this.ds);
    this.clock.addEventListener('time', this._onTime);
    // WHY not 'live': it fires every frame the span grows; a view shows t, which only 'time' and 'state' move
    this.clock.addEventListener('state', this._onState);
    markFeed(this);
  }

  /** a8: a view showing an age (display: age) redraws once a second while following, with no new row; paused, its
      ages are the ages at t and hold. */
  _ages() {
    const view = this.view, props = this.ds.properties || {};
    const want = Object.values(view.display || {}).includes('age') || Object.keys(props).some((p) => props[p] && props[p].display === 'age' && !(view.display && view.display[p]));
    if (want && !this._ageTimer && this.el.isConnected) {
      this._ageTimer = setInterval(() => { if (this.following && !document.hidden && this.el.isConnected) this._mark(); }, 1000);
    } else if (!want && this._ageTimer) { clearInterval(this._ageTimer); this._ageTimer = null; }
  }

  disconnect() {
    if (this._ageTimer) { clearInterval(this._ageTimer); this._ageTimer = null; }
    if (!this.clock) return;
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('state', this._onState);
    this.clock = null;
    if (this._scroller) { this._scroller.removeEventListener('scroll', this._onScroll); this._scroller = null; }
  }

  detach() {
    this.disconnect();
    this.ds.removeEventListener('change', this._onChange);
    const pill = this.el.querySelector(':scope > .dv-live-new');
    if (pill) pill.remove();
    this.el.removeAttribute('data-live');
  }

  refresh() { this.tail = null; this.full = null; this._mark(); }

  // ---------------------------------------------------------------- what this view shows

  get view() { return this.el.view || {}; }
  get following() { return !!(this.clock && this.clock.following); }

  /** The t this view shows: the clock's once it has this dataset's span, else the newest data. */
  tNow() {
    const c = this.clock;
    if (c && c.datasets.includes(this.ds) && c.liveEnd !== null && Number.isFinite(c.t)) return c.t;
    return this.ds.end ?? Infinity;
  }

  /** input.live (CONTRACT §26): what a view needs to read the store itself. */
  input() {
    const t = this.tNow(), at = atOf(this.view, this.ds);
    const c = this.clock;
    return Object.freeze({
      dataset: this.ds, clock: c, t, following: this.following,
      at: at === 'latest' ? 'latest' : [at === 'all' ? (this.ds.start ?? t) : t - at, t],
      start: c ? c.start : this.ds.start, end: c ? c.end : this.ds.end,
    });
  }

  /** The element's _modelHere() asks here: the rows at t for this view. */
  model(base, view, { query = '', filters } = {}) {
    const ds = this.ds, t = this.tNow(), at = atOf(view, ds);
    if (LIVE_NATIVE.has(view.type) || LIVE_IGNORE.has(view.type)) {
      // WHY no rows: the plot and the levels card read typed arrays (input.live); a row object per sample is the
      // cost this tier exists to avoid
      const columns = labelled({ properties: ds.properties }, base);
      this.el._data.rows = [];
      return { rows: [], groups: null, total: ds.countAt(t, at), matched: 0, error: null, columns, table: tableModel([], columns, view), pivot: null, rolled: null };
    }
    if (Tail.fits(ds, base, view)) {
      const key = JSON.stringify([view.type, view.name, view.filters ?? null, view.sort ?? null, view.limit ?? null, at]);
      if (!this.tail || this.tailKey !== key || this.tail.base !== base) { this.tail = new Tail(ds, base, view, { at, query, filters, cap: LIVE_CAP }); this.tailKey = key; }
      this.tail.setQuery(query);
      this.tail.setFilters(filters);
      if (!this.held) this.tail.sync(t);
      this.el._data.rows = this.tail.rows;
      this.el._byId = null;
      return this.tail.model();
    }
    this.tail = null;
    const now = performance.now();
    const key = JSON.stringify([view, query, filters ?? null, t, at, ds.seq, ds.dropGen]);
    if (!this.held && (!this.full || this.fullKey !== key)) {
      this.full = snapshotModel(ds, base, view, { t, at, query, filters });
      this.fullKey = key;
      this.fullAt = now;
      this.el._data.rows = this.full.rows;
      this.el._byId = null;
    }
    return this.full;
  }

  // ---------------------------------------------------------------- when to draw

  _changed(d) {
    if (LIVE_IGNORE.has(this.view.type)) return;
    const ds = this.ds;
    const drops = ds.dropGen === this._gen ? [] : ds.dropsSince(this._gen);
    this._gen = ds.dropGen;
    if (this.following) { this._mark(); return; }
    const t = this.tNow(), at = atOf(this.view, ds), native = LIVE_NATIVE.has(this.view.type);
    const news = pausedNews(d, { drops, t, at, native, zoom: native && this.clock ? this.clock.window : null, read: this._read(), streamOf: this._streamOf });
    if (news === 'draw') this._mark();
    else if (news === 'count' && this.el._liveCount) this.el._liveCount(ds.countAt(t, at));
  }

  /** The store's rows this view read at its last draw (the tail's, or the full model's snapshot). */
  _read() {
    if (this.tail) return this.tail.rows;
    return (this.full && this.full.read) || [];
  }

  _mark() { this.dirty = true; markFeed(this); }

  /** The frame loop calls this (phase 3), at most once per frame. */
  _draw(frame) {
    const el = this.el;
    if (!this.dirty || !el.isConnected || !el._started || !this.clock) return;
    const type = this.view.type;
    const t = this.tNow(), following = this.following;
    // a row open in the peek holds the tail; closing it at the newest end lets go
    if (this._isTail()) {
      if (!this.held && el.peeked) this.hold();
      else if (this.held && !el.peeked && this._scroller && this._away() <= 2) this.resume();
    }
    this._attr();
    if (LIVE_IGNORE.has(type)) { this.dirty = false; return; }
    // a grouped / tree / pivot view re-models whole: at most every 250 ms while following
    if (!Tail.fits(this.ds, el._base, this.view) && !LIVE_NATIVE.has(type) && following && this.full && performance.now() - this.fullAt < FULL_EVERY) {
      markFeed(this);
      return;
    }
    if (this.held) {
      this._pill();
      // a held tail redraws nothing; it only counts what is waiting
      if (t === this.lastT && following === this.lastFollowing) { this.dirty = false; return; }
    }
    this.dirty = false;
    const t0 = performance.now();
    const out = el._liveDraw();
    const done = () => {
      this.lastT = t;
      this.lastFollowing = following;
      this._ages();
      this._watchScroll();
      if (following && !this.held) this._stick();
      el.dispatchEvent(new CustomEvent('data-views-live', { detail: { t, following, rows: el._model ? el._model.rows.length : 0, ms: performance.now() - t0, frame: frame ?? liveFrame() } }));
    };
    if (out && typeof out.then === 'function') out.then(done); else done();
  }

  _attr() {
    const state = this.held ? 'held' : this.following ? 'following' : 'paused';
    if (this.el.dataset.live !== state) this.el.dataset.live = state;
  }

  // ---------------------------------------------------------------- the tail

  _desc() { const s = (this.view.sort || []).filter(Boolean)[0]; return !!(s && s.property === this.ds.time && s.direction === 'DESC'); }

  _isTail() { return !this.ds.keyed && TAIL_TYPES.has(this.view.type); }

  _watchScroll() {
    if (!this._isTail()) return;
    const host = this.el.host;
    const sc = (host && host.scroller && host.scroller !== window ? host.scroller : null) || this.el.querySelector('.dv-stage .dv-scroll');
    if (sc === this._scroller) return;
    if (this._scroller) this._scroller.removeEventListener('scroll', this._onScroll);
    this._scroller = sc;
    if (sc) sc.addEventListener('scroll', this._onScroll, { passive: true });
  }

  /** How far the scroller is from the newest end, in px. */
  _away() {
    const sc = this._scroller;
    if (!sc) return 0;
    return this._desc() ? sc.scrollTop : Math.max(0, sc.scrollHeight - sc.clientHeight - sc.scrollTop);
  }

  _rowPx() {
    const v = parseFloat(getComputedStyle(this.el).getPropertyValue('--dv-row'));
    return Number.isFinite(v) && v > 0 ? v : 30;
  }

  /** Following: keep the newest end in view (the bottom of a time-ordered list grows under the reader). */
  _stick() {
    const sc = this._scroller;
    if (!sc || this._desc()) return;
    this._sticking = true;
    sc.scrollTop = sc.scrollHeight;
    requestAnimationFrame(() => { this._sticking = false; });
  }

  _scrolled() {
    if (this._sticking || !this._isTail()) return;
    const away = this._away();
    const peek = !!this.el.peeked;
    if (!this.held && (away > this._rowPx() || peek)) this.hold();
    else if (this.held && away <= 2 && !peek) this.resume();
  }

  hold() {
    if (this.held) return;
    this.held = true;
    this.holdSeq = this.ds.seq;
    this._attr();
    this._pill();
  }

  resume() {
    this.held = false;
    const sc = this._scroller;
    if (sc) { this._sticking = true; sc.scrollTop = this._desc() ? 0 : sc.scrollHeight; requestAnimationFrame(() => { this._sticking = false; }); }
    this._attr();
    this._pill();
    this._mark();
  }

  /** "N new · Resume" at the newest end while held. */
  _pill() {
    let pill = this.el.querySelector(':scope > .dv-live-new');
    if (!this.held) { if (pill) pill.hidden = true; return; }
    if (!pill) {
      pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'dv-live-new';
      pill.addEventListener('click', () => this.resume());
      this.el.append(pill);
    }
    // WHY throttled and capped: counting reads the new rows; four times a second and at most 10,000 is plenty for a note
    const now = performance.now();
    if (!pill.hidden && now - (this._pillAt || 0) < 250) return;
    this._pillAt = now;
    const keep = this.tail ? this.tail.keep : () => true;
    const fresh = this.ds.newRows(this.holdSeq, this.following ? Infinity : this.tNow(), 10000).filter(keep);
    const n = fresh.length;
    pill.classList.toggle('dv-live-new-top', this._desc());
    pill.textContent = `${n.toLocaleString('en-US')}${n >= 10000 ? '+' : ''} new · Resume`;
    pill.title = 'New rows arrived while you scrolled or opened a row; Resume shows them and follows again';
    pill.hidden = false;
  }
}
