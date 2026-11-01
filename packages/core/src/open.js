/* How a record opens: one setting per view, `open: expand | side | link` (docs/CONTRACT.md amendment 2026-10-26
   (open modes); WHY three modes and not five: docs/peps/0003-open-modes.md).

     expand  a click (or Space) unfolds a band under the row, several at once; a card grows in place
     side    the side peek: docked beside the list from `splitAt` px of the element's width (a split view), over it
             below that, full screen on a phone; ↑/↓ (j/k) step through the rows, Esc closes, `peek=<id>` is in the URL
     link    the row is a link to the record's page; a checkbox in the title cell selects without navigating

   In every mode, when the record has a page URL (`open.url`, else the dataset's linkProperty), its title is a real
   <a href> and a double-click or Enter opens the page; with none there is no link and no "Open page". Ported from
   the open-patterns prototype (data-ui lane/open-patterns @ fd607ff, src/elements/open-patterns.js): its rich peek,
   expand band, split docking, title link and double-click handling; its Quick Look, in-kit record page and switcher
   are gone.

   The host (data-views.js) builds one OpenModes per element and calls opened() / closed() from openPeek() /
   closePeek(), peekHtml() for a record's peek and statusHtml() for the status line. A table or cards view reads
   host.opener (this controller while its view is a table or cards, else null) for titleHtml(), rowClass(),
   bandHeight() / setBandHeight() / bandHtml() (table), cardExtra() / cardMoreHtml() (cards), and may define
   openMarks() (a band opened or closed: re-measure) and reveal(id) (scroll a record into view). The rest listens on
   the element in the capture phase and stops what it handles, so the view's own click never runs for it.

   The trail (docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail)): a relation in a record (relationProps)
   or a link to another record's page, clicked inside the side peek, opens that record in the same peek and adds it to
   the trail drawn over the title, "Supply › Regen clamp › XT30 junction", as Notion's side peek keeps the path of pages
   opened from inside it. A crumb jumps back; Escape and ‹ Back step back one record before they close; the URL holds
   peek=<current>&trail=<before>…; ⤢ opens the current record's page. */

import { cellValue } from './grammar.js';
import { esc, valueHtml, valueText, cellText, linkCell, mediaUrl, hueOf, isEmpty, isNum, BASIS } from './format.js';

export const OPEN_MODES = ['expand', 'side', 'link'];
export const SPLIT_AT = 1100; // px of the <data-views> element's own width
const RECORD_VIEWS = new Set(['table', 'cards']);
// WHY the viewport, not the element: a phone's detail covers the screen, whatever the element's width
const PHONE = '(max-width: 640px)';
const BAND = 220; // px: a band's height until it has been drawn once
const CARD_LINE = 19; // px: one spec line in a grown card (the cards view's LINE)
const CONTROLS = '[data-open-step], [data-open-clear], [data-open-crumb], [data-page-full], .dv-open-back';
const typing = (t) => !!(t && t.closest && t.closest('input, textarea, select, [contenteditable]'));
/** True when a key event's target is a control of its own inside `row` (a cell's URL, email or phone link, a button, a
 * field) rather than the row itself. WHY (judge r5 #6): Enter on a focused link is the link's — the row must not open
 * or cancel it — so a row's key handler leaves these to the control. */
export const fromControl = (t, row) => !!(t && t !== row && t.closest && row && row.contains(t)
  && t.closest('a[href], button, input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role=button], [role=checkbox], [role=link]'));

/** The setting in force, {mode, splitAt, url}: the file's top-level `open:`, then the element's `open` attribute, then
    the view's `open:`, each overriding the one before it field by field; default side at 1100 px. Short form
    `open: side`; long form `open: {mode, splitAt, url}`. */
export function openSetting(view, base, attr) {
  const out = { mode: 'side', splitAt: SPLIT_AT, url: null };
  for (const o of [base && base.open, attr || null, view && view.open]) {
    if (typeof o === 'string') { if (OPEN_MODES.includes(o)) out.mode = o; continue; }
    if (!o || typeof o !== 'object') continue;
    if (OPEN_MODES.includes(o.mode)) out.mode = o.mode;
    if (o.splitAt !== null && o.splitAt !== '' && Number.isFinite(Number(o.splitAt))) out.splitAt = Number(o.splitAt);
    if (typeof o.url === 'string' && o.url) out.url = o.url;
  }
  return out;
}

/** The properties whose values name other records of the same data, which the peek follows: a column the data marks
    `relation: true`, and a view's `edges.property`, `tree.parent` or `lineage.parents` (§21) anywhere in the .base file. WHY declared, never
    guessed from values that happen to match ids: feedback_do_not_invent_undefined_relationships; the file that
    draws `feeds` as a graph's edges has already said what they mean. */
export function relationProps(base, columns) {
  const out = new Set();
  for (const [id, p] of Object.entries(columns || {})) if (p && p.relation) out.add(id);
  for (const v of (base && Array.isArray(base.views) ? base.views : [])) {
    for (const id of [v && v.edges && v.edges.property, v && v.tree && v.tree.parent, v && v.lineage && v.lineage.parents]) if (typeof id === 'string' && columns && columns[id]) out.add(id);
  }
  return out;
}

export class OpenModes {
  constructor(el) {
    this.el = el;
    this._trail = []; // the record ids opened in the peek from inside it, oldest first; the last is the one shown
    this._intent = null; // the trail the next openPeek() lands on (a followed relation, a crumb, the URL)
    this.expanded = new Set(); // record ids with a band open (expand); never in the URL
    this.bands = new Map(); // record id -> the band's drawn height (px)
    this.selected = new Set(); // record ids ticked (link)
    this._shown = null; // the record id the peek shows (null: closed, or a pivot cell's records)
    this._pushed = false; // the current history entry is one this controller pushed (peek=)
    this._quiet = 0; // > 0 while the URL is being followed, not written
    this._setting = openSetting(null, null, null);
    this._phone = typeof matchMedia === 'function' ? matchMedia(PHONE) : null;
    this._wire();
  }

  // ------------------------------------------------------------------ the setting
  /** The mode a click gets in the current view: expand and link shape a table or cards view; every other view opens
      the side peek. link with no URL falls back to side. */
  get mode() {
    const s = this._setting;
    if (!this.el.view || !RECORD_VIEWS.has(this.el.view.type)) return 'side';
    return s.mode === 'link' && !this._urlProp() ? 'side' : s.mode;
  }

  /** This controller while the current view is a table or cards (host.opener); else null. */
  forView() { return this.el.view && RECORD_VIEWS.has(this.el.view.type) ? this : null; }

  _urlProp() { return this._setting.url || (this.el.data && this.el.data.linkProperty) || null; }

  /** A record's page URL, or null. A relative one resolves against the data file's URL, as a photo's path does
      (docs/CONTRACT.md §1 amendment). */
  url(r) {
    const p = this._urlProp();
    const v = p && r ? cellValue(r[p]) : null;
    if (isEmpty(v) || typeof v === 'object') return null;
    return mediaUrl(String(v), { url: this.el.dataUrl });
  }

  _go(url) {
    // WHY location.assign, not a click on the link: the same path for Enter, a double-click and a forwarded row
    // click, and Back returns to this list where it was
    try { location.assign(url); } catch { /* a sandboxed frame: the link is still there to click */ }
  }

  // ------------------------------------------------------------------ what a view plugin asks while it draws
  /** The title cell's (or a card title's) content: a real <a href> when the record has a page, after a select box in
      link mode. */
  titleHtml(r, html) {
    const url = this.url(r);
    if (!url) return html;
    const check = this.mode === 'link' ? `<input type="checkbox" class="dv-open-check" tabindex="-1" aria-label="Select"${this.selected.has(String(r.id)) ? ' checked' : ''}>` : '';
    // WHY a real <a href>: ⌘/Ctrl/middle-click and "copy link" park a record in a tab (NN/g, page parking), which a
    // click handler on a row can never offer; a plain click is still routed by the mode. tabindex -1 because the
    // row is the tab stop and the arrows move between rows.
    return `${check}<a class="dv-open-link" href="${esc(url)}" tabindex="-1">${html}</a>`;
  }

  rowClass(id) {
    const k = String(id);
    return (this.selected.has(k) ? ' dv-open-sel' : '') + (this.mode === 'expand' && this.expanded.has(k) ? ' dv-open-on' : '');
  }

  bandHeight(id) {
    const k = String(id);
    return this.mode === 'expand' && this.expanded.has(k) ? this.bands.get(k) || BAND : 0;
  }

  /** Record a band's drawn height; true when it differs from what the virtualiser was told. */
  setBandHeight(id, px) {
    const k = String(id);
    const h = Math.round(px);
    if (!h || this.bands.get(k) === h) return false;
    const was = this.bands.get(k) || BAND;
    this.bands.set(k, h);
    return was !== h;
  }

  bandHtml(r, ncol) {
    if (!this.bandHeight(r.id)) return '';
    return `<tr class="dv-open-band" data-band="${esc(r.id)}"><td colspan="${ncol}"><div class="dv-open-bandin">${this._bandBody(r)}</div></td></tr>`;
  }

  /** A grown card's extra height: one line per property the card does not show, and the Open page link. */
  cardExtra(r) {
    if (this.mode !== 'expand' || !this.expanded.has(String(r.id))) return 0;
    return this._cardMore().length * CARD_LINE + 12 + (this.url(r) ? 32 : 0);
  }

  _cardMore() {
    const shown = new Set(this._order());
    return this._allProps().filter((p) => !shown.has(p.id));
  }

  cardMoreHtml(r) {
    if (!this.cardExtra(r)) return '';
    const url = this.url(r);
    const lines = this._cardMore().map((p) => `<div><dt>${esc(p.label)}</dt><dd>${this._val(r, p)}</dd></div>`).join('');
    return `<div class="dv-open-more"><dl class="dv-open-list">${lines}</dl>${url ? `<a class="dv-btn dv-open-page" href="${esc(url)}">Open page ↗</a>` : ''}</div>`;
  }

  // ------------------------------------------------------------------ what the host calls
  /** The side peek's content for a record: the rich header (photo, title, kind, ‹ n of N ›, Open page) over the
      inspector (`body`: its properties, then the slot under them; §44), or null to keep the host's (a pivot cell's or a
      group's records). WHY no key-spec chips and no Specs / Sources tabs: "its not a 1:1 coorespondance with the fields
      I am seeing" (Zach, 2026-10-31): the chips were a second list of the same properties, and the tabs hid the first. */
  peekHtml(r, id, opts, name, body) {
    if (opts.records || opts.title || r !== this.el.row(id)) return null;
    // the trail: as asked (a followed relation, a crumb, the URL), the same one when the record is drawn again (a
    // saved form), else a fresh one; this record is its last step
    const k = String(id);
    this._trail = this._intent || (this._trail[this._trail.length - 1] === k ? this._trail : [k]);
    this._intent = null;
    const url = this.url(r);
    const sub = this._sub(r);
    // §46: where else this record can be opened, the host's to say; nothing is drawn when it says nowhere
    const out = typeof this.el.openElsewhere === 'function' ? this.el.openElsewhere(r) : null;
    const elsewhere = out && out.href ? `<a class="dv-btn dv-open-else" href="${esc(out.href)}" data-open-elsewhere>Open in ${esc(out.label)}</a>` : '';
    return `<div class="dv-open-rec" data-id="${esc(r.id)}">
      <header><button type="button" class="dv-btn dv-open-back" aria-label="${this._trail.length > 1 ? 'Back to the previous record' : 'Back to the list'}">‹ Back</button>${this._photo(r, 'dv-open-thumb')}<div class="dv-open-titles">${this._trailHtml()}<h2>${url ? `<a class="dv-open-link" href="${esc(url)}">${esc(name)}</a>` : esc(name)}</h2>${sub ? `<p class="dv-open-sub">${esc(sub)}</p>` : ''}</div>${url ? `<a class="dv-btn dv-open-expand" href="${esc(url)}" aria-label="Open as page" title="Open as page">⤢</a>` : this.el._pageLayout() ? '<button type="button" class="dv-btn dv-open-expand" data-page-full aria-label="Open as a full page" title="Open as a full page">⤢</button>' : ''}<button class="dv-btn dv-close" aria-label="Close details">✕</button></header>
      <div class="dv-open-actions">${this._navHtml(id)}${url ? `<a class="dv-btn dv-open-page" href="${esc(url)}">Open page ↗</a>` : ''}${elsewhere}</div>
      ${body}</div>`;
  }

  /** The peek opened (openPeek): lay it out, and put a record's peek in the URL. */
  opened(peek) {
    const real = !!peek && !peek.opts.records && !peek.opts.title && peek.row === this.el.row(peek.id);
    const was = this._shown;
    this._shown = real ? peek.id : null;
    this._intent = null;
    if (!real) this._trail = [];
    this._layout();
    if (this._quiet) return;
    // WHY wait: a close just popped this controller's entry with history.back(), which lands later; pushed now, the
    // new peek= would be the entry that Back pops. The popstate handler pushes it once Back has landed.
    if (this._popping) { this._repush = real; return; }
    if (!real) { if (was) this._url((h) => h.delete('peek')); return; }
    // WHY pushed once, then replaced: Back closes the peek, as NN/g and Baymard find people expect of anything that
    // looks like a new place; stepping between records inside it replaces, so Back is not a record-by-record undo
    if (was) this._url((h) => this._params(h));
    else this._url((h) => this._params(h), true);
  }

  /** peek=<the record shown>&trail=<each record before it>, oldest first. */
  _params(h) {
    h.set('peek', this._shown);
    h.delete('trail');
    for (const t of this._trail.slice(0, -1)) h.append('trail', t);
  }

  /** The peek closed (closePeek): give the list its width back, and take the peek out of the URL. */
  closed(was) {
    const shown = this._shown;
    this._shown = null;
    this._trail = [];
    this._layout();
    if (!was || !shown || this._quiet) return;
    // the entry this controller pushed is popped, so Back from here leaves the list, not re-opens the peek
    if (this._pushed && this._hash().get('peek') === shown) {
      this._pushed = false;
      try { history.back(); this._popping = true; } catch { /* no history */ }
    }
    else this._url((h) => { h.delete('peek'); h.delete('trail'); });
    const node = this._node(shown);
    if (node && this._stageFocused()) node.focus({ preventScroll: true });
  }

  statusHtml() {
    if (this.mode !== 'link' || !this.selected.size) return '';
    return ` · <span class="dv-open-selected">${this.selected.size.toLocaleString('en-US')} selected <button type="button" class="dv-link" data-open-clear>Clear</button></span>`;
  }

  // ------------------------------------------------------------------ gestures
  /** Open a related record in the peek, one step further down the trail (back to its crumb if it is already on it). */
  follow(id) {
    const k = String(id);
    const at = this._trail.indexOf(k);
    this._intent = at >= 0 ? this._trail.slice(0, at + 1) : [...this._trail, k];
    this.el.openPeek(k);
    this._keepFocus();
  }

  /** A crumb: back to the trail's i-th record, the steps after it dropped. */
  jump(i) {
    const k = this._trail[i];
    if (k === undefined) return;
    this._intent = this._trail.slice(0, i + 1);
    this.el.openPeek(k);
    this._keepFocus();
  }

  /** Escape and ‹ Back: one record back along the trail; false when the peek shows its first record (the caller closes). */
  back() {
    if (!this._shown || this._trail.length < 2) return false;
    this.jump(this._trail.length - 2);
    return true;
  }

  /** WHY: the click's button was redrawn away, so the focus would fall to the page and the next Escape would miss the peek */
  _keepFocus() {
    const peek = this._peekEl();
    if (peek && !peek.hidden && !peek.contains(document.activeElement)) peek.focus({ preventScroll: true });
  }

  toggleBand(id) {
    const k = String(id);
    if (this.expanded.has(k)) this.expanded.delete(k); else this.expanded.add(k);
    this._plugin('openMarks');
    this._refocus(k);
  }

  _toggleSelect(id, on = !this.selected.has(String(id))) {
    const k = String(id);
    if (on) this.selected.add(k); else this.selected.delete(k);
    this._marks();
  }

  /** Selection marks on the drawn rows and cards, without a redraw (a redraw would drop the focused row). */
  _marks() {
    for (const node of this.el.querySelectorAll('.dv-stage [data-id]')) {
      const on = this.selected.has(node.dataset.id);
      node.classList.toggle('dv-open-sel', on);
      const box = node.querySelector('.dv-open-check');
      if (box) box.checked = on;
    }
    this.el._drawStatus();
  }

  /** ‹ › and ↑/↓ (j/k) in the side peek: the next record in the view's order, the row's focus following. */
  _step(delta) {
    const from = this._shown;
    const pool = this._ids();
    const i = pool.indexOf(from);
    const next = i >= 0 ? pool[i + delta] : null;
    if (!next) return;
    const onRow = !!this._record(document.activeElement);
    const peek = this._peekEl();
    const inPeek = peek && peek.contains(document.activeElement);
    this.el.openPeek(next);
    this._plugin('reveal', next);
    if (onRow) requestAnimationFrame(() => requestAnimationFrame(() => this._refocus(next, true)));
    else if (inPeek) this._peekEl().focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ the URL
  _hash() {
    try { return new URLSearchParams(location.hash.slice(1)); } catch { return new URLSearchParams(); }
  }

  _url(change, push = false) {
    if (this.el.hasAttribute('no-url')) return;
    try {
      const h = this._hash();
      change(h);
      const url = `${location.pathname}${location.search}#${h}`;
      if (push) { history.pushState(null, '', url); this._pushed = true; } else history.replaceState(null, '', url);
    } catch { /* a sandboxed frame without history: the peek still opens, unshared */ }
  }

  /** Back, Forward or the first draw: the peek follows the URL's peek=<id>. */
  _fromUrl() {
    if (this.el.hasAttribute('no-url') || !this.el.model) return;
    const h = this._hash();
    const id = h.get('peek');
    this._quiet++;
    try {
      if (id && this.mode === 'side' && this.el.row(id)) {
        // the trail comes back with the record (a reload, Back to an entry); a step that names no row is dropped
        const want = [...h.getAll('trail').filter((t) => t !== id && this.el.row(t)), id];
        if (this._shown !== id || want.join('\n') !== this._trail.join('\n')) { this._intent = want; this.el.openPeek(id); }
      }
      else if (this._shown) this.el.closePeek();
    } finally { this._quiet--; }
  }

  // ------------------------------------------------------------------ layout: split, overlay, full screen
  _layout() {
    const el = this.el;
    const peek = this._peekEl();
    const open = !!peek && !peek.hidden;
    const phone = open && !!(this._phone && this._phone.matches);
    // WHY split only when the list still fits beside the pane: Material 3's list-detail and Windows' list/details
    // show both side by side on a wide window and stack them on a narrow one; a pane over a list that has room for
    // both hides rows for nothing, and a pane beside a list too narrow to read is worse than an overlay
    const split = open && !phone && el.getBoundingClientRect().width >= this._setting.splitAt;
    el.classList.toggle('dv-full', phone);
    el.classList.toggle('dv-split', split);
    const scroller = this._scroller();
    this._follow(split && scroller ? scroller : null);
    if (split) {
      const stage = el.$ && el.$('.dv-stage');
      if (scroller) this._dock();
      else if (stage) el.style.setProperty('--dv-open-top', `${stage.offsetTop}px`);
      el.style.setProperty('--dv-open-pane', `${peek.getBoundingClientRect().width}px`);
    }
  }

  /** What scrolls the rows when it is not the view's own box: the page's scroller under frame="page|bleed"
      (host.scroller, docs/CONTRACT.md §12), read each time since a frame may change on a live element; else null. */
  _scroller() {
    const host = this.el.host;
    return (host && host.scroller) || null;
  }

  /** Under a page scroller the split pane is fixed to the viewport (frame.css), so its top is the band's bottom as the
      band is now: under the stuck band while the page scrolls, under the toolbar before it sticks, never above the
      scroller's visible top. */
  _dock() {
    const el = this.el;
    const sc = this._scroller();
    if (!sc || !el.classList.contains('dv-split')) return;
    const band = [el.$('.dv-status'), el.$('.dv-head')].filter((n) => n && n.offsetParent !== null).map((n) => n.getBoundingClientRect().bottom);
    const port = sc === window ? 0 : sc.getBoundingClientRect().top;
    el.style.setProperty('--dv-open-top', `${Math.round(Math.max(port, 0, ...band))}px`);
  }

  /** Re-dock the split pane as the page scrolls (only while it is split under a page scroller). */
  _follow(scroller) {
    if (!this._armed) scroller = null;
    if (this._following === scroller) return;
    if (this._following) this._following.removeEventListener('scroll', this._onScroll);
    this._following = scroller;
    if (!scroller) return;
    if (!this._onScroll) this._onScroll = () => { if (!this._docking) this._docking = requestAnimationFrame(() => { this._docking = 0; this._dock(); }); };
    scroller.addEventListener('scroll', this._onScroll, { passive: true });
  }

  // ------------------------------------------------------------------ events
  _wire() {
    const el = this.el;
    el.addEventListener('click', (e) => this._onClick(e), true);
    el.addEventListener('auxclick', (e) => this._onAux(e), true);
    el.addEventListener('keydown', (e) => this._onKey(e), true);
    el.addEventListener('mousedown', (e) => this._onMouseDown(e), true);
    el.addEventListener('pointerdown', () => { this._downAt = performance.now(); }, true);
    el.addEventListener('data-views-change', () => this._sync());
    el.addEventListener('data-views-render', () => { if (!this._synced) { this._synced = true; this._fromUrl(); } });
    this._onPop = () => {
      if (this.el.hasAttribute('no-url')) return;
      if (this._popping) {
        // the Back a close asked for has landed; a peek opened since then goes into the URL now
        this._popping = false;
        if (this._repush && this._shown) this._url((h) => this._params(h), true);
        this._repush = false;
        if (this.el._started) this.el._writeUrl();
        return;
      }
      this._pushed = false;
      this._fromUrl();
      // WHY rewrite: the entry Back landed on may carry an older view's state; the element shows the current one
      if (this.el._started) this.el._writeUrl();
    };
    this._onPhone = () => this._layout();
    // the element's width decides split or overlay; the pane's (dragged) width is what the list gives up
    this._onSize = () => { if (this._shown !== null || el.classList.contains('dv-peeking')) this._layout(); };
  }

  /** The element is in the page (connectedCallback): listen to the window's Back, the phone query and the element's
      width, and follow a page scroller. Once; a second call does nothing. */
  connect() {
    if (this._armed) return;
    this._armed = true;
    if (typeof addEventListener === 'function') addEventListener('popstate', this._onPop);
    if (this._phone) this._phone.addEventListener('change', this._onPhone);
    if (typeof ResizeObserver !== 'undefined') {
      this._ro = new ResizeObserver(this._onSize);
      this._ro.observe(this.el);
    }
    this._paneFor = undefined;
    this._watchPane();
    this._layout();
  }

  /** The element left the page (disconnectedCallback): let go of everything outside it, so the window, the media
      query, the observers and a page scroller hold nothing of it. WHY: the 2026-10-26 performance review's rule, that
      a removed <data-views> keeps nothing alive; connect() makes them again when it is put back. */
  disconnect() {
    if (!this._armed) return;
    this._armed = false;
    if (typeof removeEventListener === 'function') removeEventListener('popstate', this._onPop);
    if (this._phone) this._phone.removeEventListener('change', this._onPhone);
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    if (this._paneRo) { this._paneRo.disconnect(); this._paneRo = null; }
    this._paneFor = undefined;
    this._follow(null);
    if (this._docking) { cancelAnimationFrame(this._docking); this._docking = 0; }
  }

  /** A render: the setting may have changed (a new view, the attribute); a new view starts with no bands or ticks. */
  _sync() {
    const el = this.el;
    this._setting = openSetting(el.view, el.base, el.getAttribute('open'));
    const key = el.origin ? `${el.origin.kind}:${el.origin.name}` : '';
    if (key !== this._viewKey) { this._viewKey = key; this.expanded.clear(); this.selected.clear(); }
    el.dataset.open = this.mode;
    this._orderFor = null;
    if (this._paneFor !== this._peekEl()) this._watchPane();
  }

  _watchPane() {
    const peek = this._peekEl();
    this._paneFor = peek;
    if (this._paneRo) { this._paneRo.disconnect(); this._paneRo = null; }
    if (!this._armed) return;
    // focusable from script, so the arrows keep stepping after ‹ › redraws the button that had the focus
    if (peek && !peek.hasAttribute('tabindex')) peek.tabIndex = -1;
    if (!peek || typeof ResizeObserver === 'undefined') return;
    // WHY measured: the pane's width is the pane's own (dragged, remembered; src/resize.js); the list gives way
    this._paneRo = new ResizeObserver(() => { if (this.el.classList.contains('dv-split')) this.el.style.setProperty('--dv-open-pane', `${peek.getBoundingClientRect().width}px`); });
    this._paneRo.observe(peek);
  }

  _record(t) {
    if (!this.forView() || !t || !t.closest) return null;
    const node = t.closest('tr.dv-row[data-id], .dv-cards-card[data-id]');
    return node && this.el.contains(node) && node.closest('.dv-stage') ? node : null;
  }

  /** The record in the open peek under a target (not its buttons, links or form), or null. */
  _peekRecord(t) {
    const peek = this._peekEl();
    if (!t || !t.closest || !peek || !peek.contains(t) || t.closest('button, a, input, select, textarea, label')) return null;
    return t.closest('.dv-open-rec');
  }

  _onClick(e) {
    const t = e.target;
    if (!t || !t.closest) return;
    const ctl = t.closest(CONTROLS);
    if (ctl && this.el.contains(ctl)) { this._control(ctl, e); return; }
    const to = this._related(t, e);
    if (to) { e.preventDefault(); e.stopPropagation(); this.follow(to); return; }
    // WHY the same record twice: a browser counts any two quick clicks near each other (a tap on a tab, then on a
    // row) as detail 2; only a second click on the record the first one hit is a double-click
    const last = this._last;
    const twice = (id) => e.detail >= 2 && !!last && last.id === id && e.timeStamp - last.at < 800;
    // WHY the same spot counts: when the first click opens the side peek over the cell the pointer is on, the second
    // lands on the peek, not the record; a second click within 4 px of the first is still that record's double-click
    // (found when a column grew 17 px to fit its numbers and its centre moved under the peek)
    // limited (judge r3 #6): only the peek that click opened (it still shows that record), and only its background: an
    // input, a button, a link or anything a reader acts on in the peek keeps its own click
    const peek = t.closest('.dv-peek');
    if (e.detail === 2 && last && last.row && peek && e.timeStamp - last.at < 800 && Math.abs(e.clientX - last.x) < 4 && Math.abs(e.clientY - last.y) < 4
      && !this._record(t) && this.el._peek && String(this.el._peek.id) === String(last.id)
      && !t.closest('a, button, input, select, textarea, label, summary, [contenteditable], [role=button], [role=link], [tabindex]:not([tabindex="-1"])')) {
      const url = this.url(this.el.row(last.id));
      if (url) { e.preventDefault(); e.stopPropagation(); this._unselect(); this._go(url); return; }
    }
    // a double-click on the record in the peek opens its page, as Enter there does (also when the first click opened
    // the peek right under the pointer)
    const rec = this._peekRecord(t);
    if (rec) {
      const id = rec.dataset.id;
      const url = this.url(this.el.row(id));
      if (twice(id) && e.detail === 2 && url) { e.stopPropagation(); this._unselect(); this._go(url); }
      this._last = { id, at: e.timeStamp };
      return;
    }
    const node = this._record(t);
    if (!node || t.closest('[data-toggle], [data-zoom]')) return; // a tree's fold and the lightbox stay the view's
    // the element's row selection (selectable, CONTRACT §15) is the view's: its checkbox never opens or toggles a record
    if (t.closest('.dv-selbox, .dv-selcol, .dv-cards-check')) return;
    const link = t.closest('a');
    if (link && !link.classList.contains('dv-open-link')) return; // a link in a cell goes where it says
    if (t.closest('.dv-open-more')) { e.stopPropagation(); return; } // a grown card's own specs fold nothing
    const id = node.dataset.id;
    const url = this.url(this.el.row(id));
    const mode = this.mode;
    const double = twice(id);
    this._last = { id, at: e.timeStamp, x: e.clientX, y: e.clientY, row: true };
    if (t.closest('.dv-open-check')) { e.stopPropagation(); this._toggleSelect(id, t.checked); return; }
    // a modified click on the title link is the browser's: a new tab, a new window, a download
    if (link && (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)) { e.stopPropagation(); return; }
    // WHY the second click of a double-click opens the page and the first does the mode's own thing: a double-click
    // is only an accelerator, since it has no keyboard or touch equivalent (WCAG 2.1.1); Enter is the keyboard's way
    // to the page. Skipping detail >= 2 in the single-click path keeps a band or a peek from flickering.
    if (double) {
      e.stopPropagation();
      if (link) e.preventDefault();
      if (e.detail === 2 && url) { this._unselect(); this._go(url); }
      return;
    }
    if (mode === 'link') {
      e.stopPropagation();
      if (link) return; // a real link: the browser follows it
      // WHY ignore a drag: selecting a part number to copy it must not navigate (a press over 200 ms that left text
      // selected)
      const text = typeof getSelection === 'function' ? String(getSelection()) : '';
      if (text && performance.now() - (this._downAt || 0) > 200) return;
      if (e.metaKey || e.ctrlKey) window.open(url, '_blank', 'noopener');
      else this._go(url);
      return;
    }
    if (mode === 'expand') {
      e.stopPropagation();
      if (link) e.preventDefault();
      this.el.closeMenu();
      this.toggleBand(id);
      return;
    }
    // side: the view's own click opens the peek (host.open with the column); a click on the title link does too
    if (link) {
      e.preventDefault();
      e.stopPropagation();
      this.el.closeMenu();
      const td = t.closest('td[data-col]');
      this.el.openPeek(id, { column: td ? td.dataset.col : null });
    }
  }

  _onAux(e) {
    if (this.mode !== 'link' || e.button !== 1) return;
    const node = this._record(e.target);
    if (!node || e.target.closest('a, input')) return;
    const url = this.url(this.el.row(node.dataset.id));
    if (!url) return;
    e.preventDefault();
    window.open(url, '_blank', 'noopener');
  }

  /** The record a plain click inside the peek opens there: a relation link, or a link to another record's page. A
      modified or middle click is the browser's (a new tab on the page, or on the record's peek). */
  _related(t, e) {
    const peek = this._peekEl();
    const a = t.closest && t.closest('a[href]');
    if (!a || !this._shown || !peek || !peek.contains(a) || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return null;
    if (a.dataset.openRel !== undefined) return this.el.row(a.dataset.openRel) ? a.dataset.openRel : null;
    if (a.matches('.dv-open-link, .dv-open-page, .dv-open-expand')) return null; // this record's own page
    const id = this._byUrl().get(a.href);
    return id !== undefined && id !== this._shown ? id : null;
  }

  /** Every record's page URL -> its id (once per dataset). */
  _byUrl() {
    const d = this.el.data;
    if (this._urlsFor !== d || this._urlsProp !== this._urlProp()) {
      this._urls = new Map();
      for (const r of d.rows) { const u = this.url(r); if (u && !this._urls.has(u)) this._urls.set(u, String(r.id)); }
      this._urlsFor = d;
      this._urlsProp = this._urlProp();
    }
    return this._urls;
  }

  _control(ctl, e) {
    e.stopPropagation();
    if (ctl.matches('[data-open-step]')) { this._step(Number(ctl.dataset.openStep)); return; }
    if (ctl.matches('[data-open-clear]')) { this.selected.clear(); this._marks(); return; }
    if (ctl.matches('[data-open-crumb]')) { this.jump(Number(ctl.dataset.openCrumb)); return; }
    if (ctl.matches('[data-page-full]')) { this.el.pageFull = !this.el.pageFull; return; }
    if (ctl.matches('.dv-open-back') && !this.back()) this.el.closePeek();
  }

  _onKey(e) {
    const t = e.target;
    const k = e.key;
    const plain = !e.altKey && !e.metaKey && !e.ctrlKey;
    const pop = this.el.$ && this.el.$('.dv-pop');
    // §46: a grip's arrows move its block, and a Space on a section's words starts writing
    if ((pop && !pop.hidden) || typing(t) || !plain || (t.closest && t.closest('[data-page-grip], [data-page-read]'))) return;
    const stop = () => { e.preventDefault(); e.stopPropagation(); };
    const peek = this._peekEl();
    const inPeek = !!peek && !peek.hidden && peek.contains(t);
    const node = this._record(t);
    const onRow = !!node && t === node;
    // the peek showing a record: ↑/↓ and j/k step through the rows, from the peek or from the list
    if (this._shown && (inPeek || onRow) && ['ArrowDown', 'ArrowUp', 'j', 'k'].includes(k)) {
      stop();
      this._step(k === 'ArrowDown' || k === 'j' ? 1 : -1);
      return;
    }
    if (inPeek && k === 'Enter' && !t.closest('button, a') && this._shown) {
      const url = this.url(this.el.row(this._shown));
      if (url) { stop(); this._go(url); }
      return;
    }
    if (!onRow) return;
    const id = node.dataset.id;
    const url = this.url(this.el.row(id));
    const mode = this.mode;
    if (k === 'Enter') {
      stop();
      if (url) this._go(url);
      else if (mode === 'expand') this.toggleBand(id);
      else this.el.openPeek(id);
      return;
    }
    if (k !== ' ') return;
    stop();
    if (mode === 'expand') this.toggleBand(id);
    else if (mode === 'link') this._toggleSelect(id);
    else if (this._shown === id) this.el.closePeek();
    else this.el.openPeek(id);
  }

  /** WHY: a double-click's second press selects the word under it; on a row, a card or the peek's record that press
      is an open, so its default is dropped. A drag starts from a first press, so selecting text still works. */
  _onMouseDown(e) {
    if (e.detail < 2 || typing(e.target)) return;
    if (this._record(e.target) || this._peekRecord(e.target)) e.preventDefault();
  }

  // ------------------------------------------------------------------ helpers
  _peekEl() { return this.el.$ ? this.el.$('.dv-peek') : null; }
  _plugin(name, ...args) { const pl = this.el._plugin; if (pl && typeof pl[name] === 'function') pl[name](...args); }
  _unselect() { try { getSelection().removeAllRanges(); } catch { /* nothing selected */ } }
  _node(id) { return this.el.querySelector(`.dv-stage [data-id="${CSS.escape(String(id))}"]`); }

  _stageFocused() {
    const a = document.activeElement;
    const stage = this.el.$ && this.el.$('.dv-stage');
    return !a || a === document.body || !!(stage && stage.contains(a)) || !!(this._peekEl() && this._peekEl().contains(a));
  }

  _refocus(id, always = false) {
    const node = this._node(id);
    if (node && document.activeElement !== node && (always || this._stageFocused())) node.focus({ preventScroll: true });
  }

  /** The view's records in the order the reader sees them (the row model's rows are in draw order, groups too). */
  _ids() {
    const m = this.el.model;
    if (!m) return [];
    if (this._orderFor !== m) {
      this._orderIds = [...new Set(m.rows.map((r) => String(r.id)))];
      this._orderFor = m;
    }
    return this._orderIds;
  }

  _navHtml(id) {
    const pool = this._ids();
    const i = pool.indexOf(String(id));
    if (i < 0) return '<span class="dv-open-nav"><span class="dv-open-pos">not in these rows</span></span>';
    return `<span class="dv-open-nav"><button type="button" class="dv-btn" data-open-step="-1" aria-label="Previous record"${i <= 0 ? ' disabled' : ''}>‹</button><span class="dv-open-pos">${(i + 1).toLocaleString('en-US')} of ${pool.length.toLocaleString('en-US')}</span><button type="button" class="dv-btn" data-open-step="1" aria-label="Next record"${i >= pool.length - 1 ? ' disabled' : ''}>›</button></span>`;
  }

  _cols() { return (this.el.model && this.el.model.columns) || {}; }

  _relations() {
    const cols = this._cols();
    if (this._relFor !== cols || this._relBase !== this.el.base) { this._rel = relationProps(this.el.base, cols); this._relFor = cols; this._relBase = this.el.base; }
    return this._rel;
  }

  _title(r) {
    const d = this.el.data;
    return (r && valueText(r[d.titleProperty], this._cols()[d.titleProperty])) || String(r ? r.id : '');
  }

  /** A relation's value in the peek: each record it names as a link (the record's page, else its peek) that opens the
      record in the same peek; an id no row has stays as written. null when the property is not a relation. */
  relationHtml(r, p) {
    if (!p || !this._relations().has(p.id)) return null;
    const x = cellValue(r[p.id]);
    if (isEmpty(x)) return null;
    return (Array.isArray(x) ? x : [x]).map((v) => {
      const to = this.el.row(v);
      if (!to) return esc(valueText(v, p));
      const href = this.url(to) || this._peekHref(to.id);
      return `<a class="dv-open-rel" href="${esc(href)}" data-open-rel="${esc(String(to.id))}">${esc(this._title(to))}</a>`;
    }).join(', ');
  }

  /** This page with a record's peek open (where a relation with no page URL points, for a new tab). */
  _peekHref(id) {
    if (this.el.hasAttribute('no-url')) return '#';
    const h = this._hash();
    h.set('peek', String(id));
    h.delete('trail');
    return `#${h}`;
  }

  /** The trail over the title: every record before this one a button (a crumb), this one current. None for one record.
      A long title ends in an ellipsis; the whole of it is the crumb's tooltip. */
  _trailHtml() {
    if (this._trail.length < 2) return '';
    const last = this._trail.length - 1;
    const items = this._trail.map((k, i) => {
      const name = this._title(this.el.row(k));
      return `<li>${i === last ? `<span aria-current="page" title="${esc(name)}">${esc(name)}</span>` : `<button type="button" class="dv-open-crumb" data-open-crumb="${i}" title="${esc(name)}">${esc(name)}</button>`}</li>`;
    });
    return `<nav class="dv-open-trail" aria-label="Trail"><ol>${items.join('<li class="dv-open-sep" aria-hidden="true">›</li>')}</ol></nav>`;
  }

  /** Low-cardinality text properties (brand, form): the first is the record's kind under its title. */
  _kinds() {
    const d = this.el.data;
    if (this._kindsFor === d) return this._kindsList;
    const cols = this._cols();
    const limit = Math.max(12, Math.floor(d.rows.length / 10));
    this._kindsList = Object.values(cols).filter((p) => !p.hidden && p.type === 'text' && p.id !== d.titleProperty && p.display !== 'image' && p.id !== this._urlProp()).filter((p) => {
      const seen = new Set();
      for (const r of d.rows) {
        const v = cellValue(r[p.id]);
        if (!isEmpty(v)) seen.add(String(v));
        if (seen.size > limit) return false;
      }
      return seen.size > 1 && seen.size < d.rows.length;
    }).map((p) => p.id);
    this._kindsFor = d;
    return this._kindsList;
  }

  _sub(r) {
    const k = this._kinds()[0];
    return k ? valueText(r[k], this._cols()[k]) : '';
  }

  _unitCols() { return new Set(Object.values(this._cols()).map((p) => p.unit).filter(Boolean)); }

  _order() {
    const v = this.el.view || {};
    const cols = this._cols();
    return (v.order && v.order.length ? v.order : Object.keys(cols).filter((id) => !cols[id].hidden)).filter((id) => cols[id]);
  }

  /** The key specs: up to six visible properties of the view's order after its title column (not its kind, image or
      a unit column). */
  _keyProps() {
    const d = this.el.data;
    const v = this.el.view || {};
    const cols = this._cols();
    const kind = this._kinds()[0];
    const units = this._unitCols();
    return this._order().filter((id, i) => i > 0 && !cols[id].hidden && id !== d.titleProperty && id !== kind && id !== v.image && !units.has(id)).slice(0, 6).map((id) => cols[id]);
  }

  /** Every visible property: the view's order first, then the rest of the dataset's. */
  _allProps() {
    const d = this.el.data;
    const cols = this._cols();
    const units = this._unitCols();
    const ids = [...new Set([...this._order(), ...Object.keys(cols)])];
    return ids.map((id) => cols[id]).filter((p) => p && !p.hidden && !p.pivot && p.id !== d.titleProperty && !units.has(p.id));
  }

  /** A value as plain text with its unit: the title over a value that may end in an ellipsis. */
  _valTitle(r, p) {
    const text = valueText(r[p.id], p);
    const unit = p.unit ? r[p.unit] : p.unitText;
    return text && unit && !Array.isArray(cellValue(r[p.id])) ? `${text} ${unit}` : text;
  }

  /** A value the way the table writes it: its unit, its basis mark, a badge where the view draws one. */
  _val(r, p, inPeek = false) {
    const rel = inPeek ? this.relationHtml(r, p) : null;
    if (rel) return rel;
    const v = this.el.view || {};
    const display = (v.display && v.display[p.id]) || p.display;
    const cell = r[p.id];
    const x = cellValue(cell);
    if (!isEmpty(x) && (display === 'badge' || p.type === 'list')) {
      // WHY one chip: a rich cell's `text` is the producer's display of the whole value (CONTRACT §22)
      const shown = cellText(cell);
      if (shown !== null) return `<span class="dv-badge dv-h${hueOf(shown)}">${esc(shown)}</span>`;
      return (Array.isArray(x) ? x : [x]).map((y) => `<span class="dv-badge dv-h${p.colors && p.colors[y] != null ? p.colors[y] : hueOf(y)}">${esc(valueText(y, p))}</span>`).join(' ');
    }
    if (!isEmpty(x) && display === 'link' && !Array.isArray(x)) return linkCell(cell);
    return valueHtml(cell, p, { unit: p.unit ? r[p.unit] : undefined });
  }

  _source(text) {
    const s = String(text);
    if (!/^https?:\/\//.test(s)) return esc(s);
    let label = s;
    try { label = new URL(s).hostname.replace(/^www\./, ''); } catch { /* a source in words */ }
    return `<a href="${esc(s)}" rel="noopener" target="_blank">${esc(label)}</a>`;
  }

  /** The record's photo (the view's image, else the dataset's imageProperty); a placeholder when it has none, or ''
      with `bare` (the band does not keep an empty square). */
  _photo(r, cls, bare = false) {
    const d = this.el.data;
    const v = this.el.view || {};
    const prop = v.image && this._cols()[v.image] ? v.image : d.imageProperty;
    const src = prop ? cellValue(r[prop]) : null;
    if (!prop) return '';
    if (isEmpty(src) || Array.isArray(src)) return bare ? '' : `<div class="${cls} dv-open-nophoto" aria-hidden="true"></div>`;
    return `<img class="${cls}" src="${esc(mediaUrl(src, { url: this.el.dataUrl }))}" alt="" loading="lazy">`;
  }

  _chips(r, inPeek = false) {
    const chips = this._keyProps().map((p) => `<div class="dv-open-chip"><dt title="${esc(p.label)}">${esc(p.label)}</dt><dd title="${esc(this._valTitle(r, p))}">${this._val(r, p, inPeek)}</dd></div>`).join('');
    return chips ? `<dl class="dv-open-chips">${chips}</dl>` : '';
  }

  /** The slot's pane of every field that carries its own basis or source, folded; '' when none does (or in a form). WHY
      folded under the properties: it was the Sources tab, and "Every value behind it" usually says it in full already. */
  sourcesPane(r) {
    const list = this.el.view && this.el.view.edit ? '' : this._sources(r);
    return list ? `<details class="dv-peek-pane"><summary>Sources <span class="dv-count">${(list.match(/<li>/g) || []).length}</span></summary>${list}</details>` : '';
  }

  _sources(r) {
    const rich = this._allProps().filter((p) => { const c = r[p.id]; return c && typeof c === 'object' && !Array.isArray(c) && (c.basis || c.source); });
    if (!rich.length) return '';
    return `<ol class="dv-open-sources">${rich.map((p) => {
      const c = r[p.id];
      const basis = c.basis ? BASIS[c.basis] : null;
      const parts = [c.basis ? `${esc(basis ? basis.label : c.basis)}${basis ? ` (${esc(basis.means)})` : ''}` : '', isNum(c.n) ? `n = ${c.n}` : '',
        c.source ? this._source(c.source) : '', c.asOf ? `as of ${esc(String(c.asOf).slice(0, 10))}` : '', c.note ? esc(c.note) : ''].filter(Boolean);
      return `<li><span class="dv-open-srcfield">${esc(p.label)}</span> ${valueHtml(c, p)}<div class="dv-open-prov">${parts.join(' · ')}</div></li>`;
    }).join('')}</ol>`;
  }

  /** The expand band: photo, title and kind, key specs, every property in a compact grid, Open page. */
  _bandBody(r) {
    const url = this.url(r);
    const sub = this._sub(r);
    const d = this.el.data;
    const title = valueText(r[d.titleProperty], this._cols()[d.titleProperty]) || String(r.id);
    // WHY a title on every label and value: in a narrow box they end in an ellipsis, and the full text stays a hover
    // away (Zach's truthful rendering: never clipped without one)
    const grid = this._allProps().map((p) => `<div><dt title="${esc(p.label)}">${esc(p.label)}</dt><dd title="${esc(this._valTitle(r, p))}">${this._val(r, p)}</dd></div>`).join('');
    return `${this._photo(r, 'dv-open-bandphoto', true)}<div class="dv-open-bandmain"><div class="dv-open-bandtop"><b title="${esc(title)}">${esc(title)}</b>${sub ? `<span class="dv-open-sub" title="${esc(sub)}">${esc(sub)}</span>` : ''}${url ? `<a class="dv-btn dv-open-page" href="${esc(url)}">Open page ↗</a>` : ''}</div>${this._chips(r)}<dl class="dv-open-grid">${grid}</dl></div>`;
  }
}
