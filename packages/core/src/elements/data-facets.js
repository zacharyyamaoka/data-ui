/* <data-facets for="views-id">: the McMaster-style rail for a <data-views> (docs/SPEC.md §6).

   One filter model, two editors: the rail edits the facet-shaped part of the all-views filter (el.filters, which
   starts as the .base file's top-level `filters`), so a tick survives switching from the table to the chart. What
   it cannot draw stays custom, verbatim: "+N custom filters · Edit" opens the Filter menu. Counts are disjunctive:
   a facet's counts apply every other facet's selection but not its own (McMaster, Algolia).
   The facets come from the current view's `facets:` (a recipe), else the .base file's `facets:` list (a property, or
   {property, as: <kind>, …options}), else from fields whose schema says `facet:`. A numeric property reads as a range
   unless told otherwise. The kinds and their options are docs/CONTRACT.md §7 (amendment 2026-10-26, filters); each
   copies one site's widget (KINDS in facets.js). An unknown kind draws as values and says so; it never breaks.

   Keyboard and screen readers: every control is a native one (checkbox, radio, switch, range, select, date, search)
   or a button with aria-pressed / aria-expanded, so Tab, Space, Enter and the arrow keys do what the platform does;
   each group is a labelled group, the match count is a polite live region, and a redraw puts focus back on the
   control that had it. */

import { measure } from '../perf.js';
import { toRail, fromRail, facetSpecs, railConfig, railCounts, railInputs, sliderScale, isBucket, parseClause, presetLabel, settleChildren, dateBounds, nextDateChange } from '../facets.js';
import { cellValue, effectiveView } from '../grammar.js';
import { properties as labelled, groupEntries } from '../rowmodel.js';
import { esc, fmtNum, numOpts, valueText, hueOf, mediaUrl } from '../format.js';

const SHOWN = 8;
const LIMIT = { grid: 12, gallery: 8, swatch: 12, chips: 12, listbox: 200 };
const ACTIVE = (f) => !!f && Object.keys(f).some((k) => ['values', 'exclude', 'min', 'max', 'has', 'hasAny', 'text'].includes(k));
const warned = new Set();
let rails = 0;

export class DataFacets extends HTMLElement {
  connectedCallback() {
    // WHY a prefix per rail for every radio name and id it writes (sim2real gap #14, 2026-10-28): a radio group is every
    // radio of one name in the document, so two rails over a `device` facet (a dashboard's servo and camera datasets)
    // shared "df-device", and checking the camera rail's default unchecked the servo rail's. Their headings' ids
    // collided the same way, so a group's aria-labelledby named the other rail's heading.
    if (!this._uid) this._uid = `df${++rails}`;
    this._open = new Set();
    this._find = {};
    this._folded = new Map();
    this._help = new Set();
    customElements.whenDefined('data-views').then(() => this._attach());
  }

  disconnectedCallback() {
    if (this._target) this._target.removeEventListener('data-views-change', this._onChange);
    if (this._frame) { cancelAnimationFrame(this._frame); this._frame = 0; }
    if (this._after) { clearTimeout(this._after); this._after = 0; }
    if (this._dayTimer) { clearTimeout(this._dayTimer); this._dayTimer = 0; }
    this._unwait();
  }

  /* WHY after the paint: the rows are what the reader came for. A frame callback runs BEFORE the browser paints, so a
     recount scheduled there held the first rows (and every tick's new rows) back by the count pass; a task queued from
     that frame runs after it has painted (perf review 2026-10-26, item 3). The rail then draws a frame later. */
  _later() {
    if (this._frame || this._after || this._waiting) return;
    const t = this._target;
    // WHY wait for the view's first draw: on a cold load the view's code is still on its way when the first change
    // event fires, so "after the next paint" would count before any row exists and, on a big table, hold the rows
    // back. The rail waits for data-views-render (or 3 s, should the view never draw) and then counts after the paint.
    // a target that never draws (a host's own source element) is waited for once, then counted: the 3 s fallback
    // must not re-arm itself forever (found landing dashboards, 2026-10-26: the pid-tuning rail never drew)
    if (t && !t.dataset.view && this._waitedFor !== t) {
      const go = () => { this._waitedFor = t; this._unwait(); this._later(); };
      this._waiting = { t, go, timer: setTimeout(go, 3000) };
      t.addEventListener('data-views-render', go, { once: true });
      return;
    }
    this._frame = requestAnimationFrame(() => {
      this._frame = 0;
      this._after = setTimeout(() => { this._after = 0; if (this.isConnected) this._draw(); }, 0);
    });
  }

  get target() { return this._target || null; }

  _attach() {
    if (!this.isConnected) return; // removed before the kit was defined, or while its target was missing
    const id = this.getAttribute('for');
    const target = id ? document.getElementById(id) : this.closest('data-views');
    if (!target) { requestAnimationFrame(() => this._attach()); return; }
    if (this._target) this._target.removeEventListener('data-views-change', this._onChange); // put back twice before the kit was defined
    this._unwait();
    this._target = target;
    // WHY a frame later: the change that triggers a redraw often comes from one of the rail's own inputs, and
    // replacing that input inside its own change or blur event throws
    this._onChange = () => this._later();
    target.addEventListener('data-views-change', this._onChange);
    // WHY once: the rail re-attaches each time it is put back in the page; its own listeners must not double up, or
    // one tick applies twice (2026-10-26 performance review)
    if (this._wired) { if (target.model) this._later(); return; }
    this._wired = true;
    this.addEventListener('change', (e) => this._changed(e));
    this.addEventListener('input', (e) => this._input(e));
    this.addEventListener('click', (e) => this._clicked(e));
    this.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && e.target.matches('[data-act=search]') && e.target.value) { e.preventDefault(); e.target.value = ''; this._search(e.target); }
    });
    if (target.model) this._later();
  }

  /** [{key, property, as, label, prop, …options}] for the rail, top to bottom (facetSpecs in facets.js). */
  facets() {
    const t = this._target;
    const props = labelled(t.data, t.base);
    const specs = facetSpecs(t.base, t.view, props);
    for (const s of specs) {
      if (s.unknown && !warned.has(s.unknown)) {
        warned.add(s.unknown);
        console.warn(`data-facets: unknown facet kind '${s.unknown}' on '${s.property}'; drawn as values (kinds: docs/CONTRACT.md §7)`);
      }
    }
    return specs;
  }

  _state(specs) {
    const t = this._target;
    return railInputs(t.data, t.view || {}, t.filters, specs);
  }

  _unwait() {
    const w = this._waiting;
    if (!w) return;
    this._waiting = null;
    clearTimeout(w.timer);
    w.t.removeEventListener('data-views-render', w.go);
  }

  /** Recount when what the counts read has changed, then paint. A change that leaves the counts and the match count
      as they were (units, column widths, theme, a sort, a group) draws nothing. */
  _draw() {
    const t = this._target;
    if (!t || !t.data || !t.base) return;
    const t0 = performance.now();
    const matched = t.model ? t.model.matched : null;
    const counted = this._recount();
    if (counted === 'pending') return; // the worker is counting: the rail paints when its counts land (_recount)
    if (!counted && matched === this._paintedMatched && this.querySelector('details')) return;
    this._paint();
    measure('data-ui:rail', t0, { id: t.id || null, facets: this._specs.length });
  }

  /** With a date facet, draw again just after its presets' bounds next move (nextDateChange: a local midnight, or 23:00
      / 01:00 across DST); a reconnect draws again anyway, and the key then sees the new bounds. */
  _armDay(specs) {
    if (this._dayTimer) { clearTimeout(this._dayTimer); this._dayTimer = 0; }
    if (!this.isConnected) return;
    const next = nextDateChange(specs);
    if (next === null) return;
    this._dayTimer = setTimeout(() => { this._dayTimer = 0; if (this.isConnected) this._later(); }, Math.max(250, next - Date.now() + 250));
  }

  /* WHY a key: the counts depend on the data (and its edits: data-views' dataRevision, since an edit changes a row in
     place), the .base file, the facets this view shows and the filters; nothing else. Sorting, grouping, units,
     widths, theme, help, folding, "Show more" and a list's own search used to recount all of it (perf review
     2026-10-26, item 3). Returns true when it counted. */
  _recount() {
    const t = this._target;
    const specs = this.facets();
    const view = t.view || {};
    // the date presets' bounds are part of the key: they move with the calendar day (judge r1 finding 4)
    const key = JSON.stringify([specs.map(({ prop, ...rest }) => rest), view.filters || null, t.filters || null, t.dataRevision || 0, dateBounds(specs)]);
    this._armDay(specs);
    if (this._counts && key === this._countKey && t.data === this._countData && t.base === this._countBase) { this._specs = specs; this._asked = null; return false; }
    const asked = this._asked;
    if (asked && asked.key === key && asked.data === t.data && asked.base === t.base) return 'pending';
    this._asked = null;
    // WHY the worker when <data-views> has one: at 100,000 rows the counts are tens of ms on the main thread; the
    // worker counts the same rows with the same function (railInputs + railCounts), and the rail keeps showing its
    // last counts until the new ones land. Returns 'pending' then.
    const rm = !this._noWorker && typeof t._countWorker === 'function' ? t._countWorker() : null;
    if (rm) {
      const req = { key, data: t.data, base: t.base, bounds: JSON.stringify(dateBounds(specs)) };
      this._asked = req;
      const t0 = performance.now();
      rm.counts(view, t.filters, specs).then((counts) => {
        if (this._asked !== req || !this.isConnected) return;
        this._asked = null;
        if (!counts) { this._draw(); return; }
        const { cfg, rail, rows, rest } = this._state(specs);
        Object.assign(this, { _specs: specs, _cfg: cfg, _rail: rail, _rows: rows, _rest: rest, _counts: counts, _countKey: key, _countData: req.data, _countBase: req.base, _countBounds: req.bounds });
        this._paint();
        measure('data-ui:rail', t0, { id: t.id || null, facets: specs.length, worker: true });
      }, () => {
        if (this._asked !== req) return;
        this._asked = null;
        this._noWorker = true; // counted here from now on
        this._draw();
      });
      return 'pending';
    }
    const { cfg, rail, rows, rest } = this._state(specs);
    this._countBounds = JSON.stringify(dateBounds(specs));
    this._specs = specs;
    this._cfg = cfg;
    this._rail = rail;
    this._rows = rows;
    this._rest = rest;
    this._counts = railCounts(rows, rail.facets, specs, rest);
    // a nav facet's rows are the view's own groups, in its order and words, counted under every other pick but its own
    // (disjunctive), so a picked row's neighbours keep their counts (docs/CONTRACT.md §20)
    for (const s of specs) {
      if (s.as !== 'nav') continue;
      const others = { ...rail.facets };
      delete others[s.property];
      const lens = { ...effectiveView(view), groupBy: s.level };
      delete lens.grouping;
      this._counts[s.key] = { ...this._counts[s.key], entries: groupEntries(t.data, t.base, lens, { filters: fromRail(others, rail.rest) ?? null }) };
    }
    this._countKey = key;
    this._countData = t.data;
    this._countBase = t.base;
    return true;
  }

  /** The rail's HTML from the last counts and this rail's own state (open, folded, help, a list's search). */
  _paint() {
    const t = this._target;
    if (!this._counts) { this._draw(); return; }
    // WHY the bounds first: a local repaint (fold, help, Show more, a list's own search) reuses the counts, but a date
    // preset's counts are only true for the bounds they were made for; once the clock has moved them, recount (the
    // key sees the new bounds) instead of painting yesterday's numbers (judge r2, 2026-10-27)
    if (this._countBounds !== undefined && this._specs && JSON.stringify(dateBounds(this._specs)) !== this._countBounds) { this._draw(); return; }
    const specs = this._specs;
    const rail = this._rail;
    const rows = this._rows;
    this._scales = {};
    const active = Object.keys(rail.facets).length;
    const matched = t.model ? t.model.matched : rows.length;
    this._paintedMatched = t.model ? t.model.matched : null;
    const groups = specs.map((s) => this._group(s)).join('');
    const custom = rail.rest.length ? `<div class="df-custom">+${rail.rest.length} custom filter${rail.rest.length > 1 ? 's' : ''} · <button class="dv-link" data-edit data-k="edit">Edit</button></div>` : '';
    const empty = specs.length ? '' : '<p class="df-none">No rail filters in this view; <button class="dv-link" data-edit data-k="edit2">Filter</button> edits the whole tree.</p>';
    const open = this._details ? this._details.open : !matchMedia('(max-width: 700px)').matches;
    const focus = document.activeElement && this.contains(document.activeElement) ? document.activeElement.dataset.k : null;
    const at = focus && document.activeElement.selectionStart !== undefined ? document.activeElement.selectionStart : null;
    this.innerHTML = `<details class="df-box"${open ? ' open' : ''}><summary><span>Filter <span class="df-n" aria-live="polite">${matched.toLocaleString()} match</span></span>${active ? '<button class="dv-link df-clear" data-clear data-k="clear">Clear all</button>' : ''}</summary>${groups}${empty}${custom}</details>`;
    this._details = this.querySelector('details');
    if (focus) {
      const again = this.querySelector(`[data-k="${CSS.escape(focus)}"]`);
      if (again) { again.focus(); if (at !== null && again.setSelectionRange && /text|search/.test(again.type)) try { again.setSelectionRange(at, at); } catch { /* not a text box */ } }
    }
  }

  // ------------------------------------------------------------------ one group

  _baseUrl() {
    const src = this._target.getAttribute('src');
    try { return src ? new URL(src, document.baseURI).href : this._target.dataUrl; } catch { return document.baseURI; }
  }

  /** A picture: a .svg is a line drawing, drawn in the text colour (a CSS mask), so it reads in light and dark; any
      other image is drawn as itself. */
  _picture(src, cls, alt = '') {
    if (!src) return '';
    let url;
    try { url = new URL(src, this._baseUrl()).href; } catch { return ''; }
    if (/\.svg(\?|#|$)/i.test(src)) return `<span class="df-ink ${cls}" role="img" aria-label="${esc(alt)}" style="--df-src:url(&quot;${esc(url)}&quot;)"></span>`;
    return `<img class="${cls}" src="${esc(url)}" alt="${esc(alt)}" loading="lazy" decoding="async">`;
  }

  _imageOf(s, value) {
    if (s.images && s.images[value] !== undefined) return s.images[value];
    if (s.image) {
      const row = this._rows.find((r) => String(cellValue(r[s.property])) === value && cellValue(r[s.image]));
      if (row) return mediaUrl(cellValue(row[s.image]), { url: this._target.dataUrl });
    }
    return null;
  }

  _unit(s) {
    const u = s.unit !== undefined ? s.unit : s.prop && s.prop.unitText;
    return u ? ` <span class="dv-u">${esc(u)}</span>` : '';
  }

  _num(s, v) {
    return typeof v === 'number' ? fmtNum(v, s.prop && s.prop.decimals, numOpts(s.prop)) : esc(String(v));
  }

  _label(s, k) {
    return esc(valueText(k, s.prop) || k);
  }

  _group(s) {
    const owned = s.as === 'tree' ? s.levels : s.as === 'has' || s.as === 'search' ? s.properties : s.property ? [s.property] : [];
    const state = this._rail.facets;
    const sel = (s.property && state[s.property]) || {};
    const on = owned.some((p) => ACTIVE(state[p]));
    const key = s.key;
    const folded = this._folded.has(key) ? this._folded.get(key) : !!s.collapsed;
    const units = ['range', 'slider', 'slider-histogram', 'buckets', 'date'].includes(s.as) ? this._unit(s) : '';
    const help = s.info || (this._target.base.properties && this._target.base.properties[s.property] && this._target.base.properties[s.property].description) || (s.prop && (s.prop.description || s.prop.note));
    const hid = `${this._uid}-h-${slugKey(key)}`;
    const head = `<h4 id="${hid}"><button class="df-fold" type="button" aria-expanded="${!folded}" data-act="fold" data-key="${esc(key)}" data-k="fold:${esc(key)}">${esc(s.label)}${units}</button>`
      + `${help ? `<button class="df-info" type="button" aria-expanded="${this._help.has(key)}" aria-label="About ${esc(s.label)}" data-act="info" data-key="${esc(key)}" data-k="info:${esc(key)}">ⓘ</button>` : ''}`
      + `${on && s.as !== 'current' ? `<button class="dv-link" data-reset="${esc(key)}" data-k="reset:${esc(key)}">Clear</button>` : ''}</h4>`;
    const helpHtml = help && this._help.has(key) ? `<p class="df-help">${esc(help)}</p>` : '';
    const warn = s.unknown ? `<p class="df-warn">Unknown kind '${esc(s.unknown)}': shown as values.</p>` : '';
    const diagram = s.diagram ? this._picture(s.diagram, 'df-diagram', `${s.label}: what it measures`) : '';
    let body = '';
    if (!folded) {
      const draw = {
        values: () => this._values(s, sel), select: () => this._select(s, sel), toggle: () => this._toggle(s, sel), has: () => this._has(s),
        range: () => this._range(s, sel), slider: () => this._slider(s, sel), 'slider-histogram': () => this._slider(s, sel, true),
        buckets: () => this._buckets(s, sel), rating: () => this._rating(s, sel), 'min-level': () => this._rating(s, sel),
        date: () => this._date(s, sel), chips: () => this._tiles(s, sel), swatch: () => this._tiles(s, sel), gallery: () => this._tiles(s, sel),
        'picture-list': () => this._tiles(s, sel), grid: () => this._tiles(s, sel), listbox: () => this._listbox(s, sel),
        tree: () => this._tree(s), search: () => this._searchBox(s), popular: () => this._popular(s), current: () => this._current(),
        nav: () => this._nav(s, sel),
      }[s.as];
      body = draw ? draw() : '';
    }
    return `<section class="df-group df-as-${esc(s.as)}" role="group" aria-labelledby="${hid}" data-p="${esc(s.property || '')}" data-key="${esc(key)}">${head}${helpHtml}${warn}${folded ? '' : diagram}${body}</section>`;
  }

  /** The entries of a value facet, sorted, found, limited: [[value, count]], plus the "Show N more" button. */
  _entries(s, sel, { limit = SHOWN } = {}) {
    const c = this._counts[s.key] || { counts: {} };
    const chosen = new Set([...(sel.values || []), ...(sel.exclude || [])].map(String));
    let entries = Object.entries(c.counts || {});
    for (const v of chosen) if (!entries.some(([k]) => k === v)) entries.push([v, 0]);
    if (s.sort === 'alpha') entries.sort((a, b) => valueText(a[0], s.prop).localeCompare(valueText(b[0], s.prop)));
    else if (s.sort === 'value') entries.sort((a, b) => (Number.isNaN(Number(a[0])) || Number.isNaN(Number(b[0])) ? a[0].localeCompare(b[0]) : Number(a[0]) - Number(b[0])));
    else if (Array.isArray(s.order)) entries.sort((a, b) => rank(s.order, a[0]) - rank(s.order, b[0]));
    const find = (this._find[s.key] || '').toLowerCase();
    if (find) entries = entries.filter(([k]) => valueText(k, s.prop).toLowerCase().includes(find) || chosen.has(k));
    const lim = s.limit || limit;
    const all = this._open.has(s.key) || find;
    const shown = all ? entries : entries.slice(0, lim).concat(entries.slice(lim).filter(([k]) => chosen.has(k)));
    const more = !all && entries.length > lim ? `<button class="dv-link df-more" data-more="${esc(s.key)}" data-k="more:${esc(s.key)}">Show ${entries.length - lim} more</button>` : '';
    const total = Object.keys(c.counts || {}).length;
    const searchable = s.searchable === true || (s.searchable !== false && ['values', 'picture-list', 'grid', 'listbox'].includes(s.as) && total > lim * 1.5);
    const findBox = searchable ? `<input class="df-find" type="search" data-p="${esc(s.key)}" data-k="find:${esc(s.key)}" placeholder="Find a ${esc(s.label.toLowerCase())}" aria-label="Find a ${esc(s.label.toLowerCase())}" value="${esc(this._find[s.key] || '')}">` : '';
    return { shown, more, findBox, chosen };
  }

  _values(s, sel) {
    const { shown, more, findBox, chosen } = this._entries(s, sel);
    const excluded = new Set((sel.exclude || []).map(String));
    const items = shown.map(([k, n]) => {
      const x = excluded.has(k);
      const ex = s.exclude ? `<button class="df-ex" type="button" aria-pressed="${x}" aria-label="${x ? 'Include' : 'Exclude'} ${this._label(s, k)}" title="${x ? 'Include again' : 'Exclude'}" data-act="exclude" data-p="${esc(s.property)}" data-value="${esc(k)}" data-k="ex:${esc(s.key)}:${esc(k)}">${x ? '↺' : '⊘'}</button>` : '';
      return `<li class="${n ? '' : 'df-zero'}${x ? ' df-excluded' : ''}"><label><input type="checkbox" data-value="${esc(k)}" data-p="${esc(s.property)}" data-k="v:${esc(s.key)}:${esc(k)}"${chosen.has(k) && !x ? ' checked' : ''}${x ? ' disabled' : ''}><span class="df-label">${this._label(s, k)}</span><span class="df-count">${n.toLocaleString()}</span></label>${ex}</li>`;
    }).join('');
    return `${findBox}<ul class="df-values">${items}</ul>${more}`;
  }

  _select(s, sel) {
    const c = this._counts[s.key] || { counts: {}, n: 0 };
    const cur = sel.values && sel.values.length === 1 ? String(sel.values[0]) : '';
    const name = `${this._uid}-${slugKey(s.key)}`;
    if (s.dropdown) {
      const opts = Object.entries(c.counts).map(([k, n]) => `<option value="${esc(k)}"${k === cur ? ' selected' : ''}>${this._label(s, k)} (${n.toLocaleString()})</option>`).join('');
      return `<select class="df-dropdown" data-act="select" data-p="${esc(s.property)}" data-k="sel:${esc(s.key)}" aria-label="${esc(s.label)}"><option value="">${esc(s.any || 'Any')}</option>${opts}</select>`;
    }
    const { shown, more } = this._entries(s, sel);
    const any = `<li><label><input type="radio" name="${name}" data-act="select" data-p="${esc(s.property)}" data-value="" data-k="sel:${esc(s.key)}:"${cur ? '' : ' checked'}><span class="df-label">${esc(s.any || 'Any')}</span><span class="df-count">${(c.n || 0).toLocaleString()}</span></label></li>`;
    const items = shown.map(([k, n]) => `<li class="${n ? '' : 'df-zero'}"><label><input type="radio" name="${name}" data-act="select" data-p="${esc(s.property)}" data-value="${esc(k)}" data-k="sel:${esc(s.key)}:${esc(k)}"${k === cur ? ' checked' : ''}><span class="df-label">${this._label(s, k)}</span><span class="df-count">${n.toLocaleString()}</span></label></li>`).join('');
    return `<ul class="df-values">${any}${items}</ul>${more}`;
  }

  _toggle(s, sel) {
    const onValue = s.value === undefined ? true : s.value;
    const c = this._counts[s.key] || { counts: {} };
    const n = c.counts[String(onValue)] || 0;
    const checked = sel.values && sel.values.length === 1 && String(sel.values[0]) === String(onValue);
    const text = s.text || `${s.label}: ${valueText(String(onValue), s.prop) || onValue} only`;
    return `<label class="df-switch"><input type="checkbox" role="switch" data-act="toggle" data-p="${esc(s.property)}" data-k="tog:${esc(s.key)}"${checked ? ' checked' : ''}><span class="df-track" aria-hidden="true"></span><span class="df-label">${esc(text)}</span><span class="df-count">${n.toLocaleString()}</span></label>`;
  }

  _has(s) {
    const c = this._counts[s.key] || {};
    const state = this._rail.facets;
    const anyList = (state[s.properties[0]] || {}).hasAny || [];
    const props = labelled(this._target.data, this._target.base);
    const items = s.properties.map((p) => {
      const on = (state[p] || {}).has || anyList.includes(p);
      return `<li><label><input type="checkbox" data-has="${esc(p)}" data-key="${esc(s.key)}" data-k="has:${esc(s.key)}:${esc(p)}"${on ? ' checked' : ''}><span class="df-label">${s.properties.length === 1 ? 'Has a value' : `Has ${esc((props[p] || {}).label || p)}`}</span><span class="df-count">${(c[p] || 0).toLocaleString()}</span></label></li>`;
    }).join('');
    const mode = s.properties.length > 1 ? (anyList.length ? 'any' : s.match === 'any' && !s.properties.some((p) => (state[p] || {}).has) ? 'any' : 'all') : null;
    const name = `${this._uid}-m-${slugKey(s.key)}`;
    const seg = mode ? `<div class="df-seg" role="radiogroup" aria-label="${esc(s.label)}: match"><label><input type="radio" name="${name}" data-act="hasmode" data-key="${esc(s.key)}" value="all" data-k="hm:${esc(s.key)}:all"${mode === 'all' ? ' checked' : ''}>All of</label><label><input type="radio" name="${name}" data-act="hasmode" data-key="${esc(s.key)}" value="any" data-k="hm:${esc(s.key)}:any"${mode === 'any' ? ' checked' : ''}>Any of</label></div>` : '';
    return `${seg}<ul class="df-values">${items}</ul>`;
  }

  _span(s, c) {
    return c && c.n ? `${this._num(s, c.min)} – ${this._num(s, c.max)} · ${c.n.toLocaleString()} with a value` : 'no values';
  }

  _range(s, sel) {
    const c = this._counts[s.key];
    const box = (side) => {
      const v = sel[side] ?? '';
      const label = `${s.label} ${side === 'min' ? 'at least' : 'at most'}`;
      if (Array.isArray(s.choices) && s.choices.length) {
        // WHY dropdown pairs (Zillow, Redfin): a price is picked from round numbers far more often than typed
        const opts = s.choices.map((x) => `<option value="${esc(x)}"${String(x) === String(v) ? ' selected' : ''}>${this._num(s, x)}</option>`).join('');
        return `<select data-${side}="${esc(s.property)}" aria-label="${esc(label)}" data-k="${side}:${esc(s.key)}"><option value="">${side === 'min' ? 'No min' : 'No max'}</option>${opts}${v !== '' && !s.choices.map(String).includes(String(v)) ? `<option value="${esc(v)}" selected>${this._num(s, v)}</option>` : ''}</select>`;
      }
      if (s.prop && s.prop.type === 'date') return `<input type="date" data-${side}="${esc(s.property)}" data-k="${side}:${esc(s.key)}" aria-label="${esc(label)}" value="${esc(String(v).slice(0, 10))}">`;
      return `<input type="number" inputmode="decimal" step="any" data-${side}="${esc(s.property)}" data-k="${side}:${esc(s.key)}" aria-label="${esc(label)}" placeholder="${side}" value="${esc(v)}">`;
    };
    const dates = s.prop && s.prop.type === 'date';
    return `<div class="df-range${dates ? ' df-dates' : ''}">${box('min')}<span>–</span>${box('max')}</div><div class="df-span">${dates ? (c && c.n ? `${esc(String(c.min).slice(0, 10))} – ${esc(String(c.max).slice(0, 10))} · ${c.n.toLocaleString()} with a date` : 'no dates') : this._span(s, c)}</div>`;
  }

  _slider(s, sel, hist = false) {
    const c = this._counts[s.key];
    if (!c || c.domain.min === null) return '<div class="df-span">no values</div>';
    const scale = sliderScale(c.domain.min, c.domain.max, !!s.log);
    this._scales[s.key] = scale;
    const lo = sel.min !== undefined ? scale.toPos(sel.min) : 0;
    const hi = sel.max !== undefined ? scale.toPos(sel.max) : 1000;
    const unit = s.unit !== undefined ? s.unit : (s.prop && s.prop.unitText) || '';
    const txt = (v) => `${fmtNum(v, s.prop && s.prop.decimals, numOpts(s.prop))}${unit ? ` ${unit}` : ''}`;
    const loV = sel.min !== undefined ? sel.min : c.domain.min, hiV = sel.max !== undefined ? sel.max : c.domain.max;
    let bars = '';
    if (hist && c.bins) {
      const top = Math.max(1, ...c.binsAll.map((b) => b.n));
      const w = 100 / c.bins.length;
      // WHY two layers: the faint bar is every row the view has; the solid one what the other filters leave, so the
      // slider shows where the parts are before you drag (Airbnb's price histogram)
      bars = `<svg class="df-hist" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">${c.bins.map((b, i) => {
        const inside = scale.toPos(b.x1) > lo && scale.toPos(b.x0) < hi;
        const hAll = (c.binsAll[i].n / top) * 32, h = (b.n / top) * 32;
        return `<g><title>${txt(nice2(b.x0))} – ${txt(nice2(b.x1))}: ${b.n.toLocaleString()}</title><rect class="df-bar-all" x="${(i * w).toFixed(3)}" y="${(32 - hAll).toFixed(2)}" width="${(w - 0.4).toFixed(3)}" height="${hAll.toFixed(2)}"></rect><rect class="df-bar${inside ? ' df-in' : ''}" x="${(i * w).toFixed(3)}" y="${(32 - h).toFixed(2)}" width="${(w - 0.4).toFixed(3)}" height="${h.toFixed(2)}"></rect></g>`;
      }).join('')}</svg>`;
    }
    const thumb = (side, pos, v) => `<input type="range" min="0" max="1000" step="1" value="${pos}" data-act="slider" data-side="${side}" data-key="${esc(s.key)}" data-p="${esc(s.property)}" data-k="sl:${esc(s.key)}:${side}" aria-label="${esc(s.label)}, ${side === 'min' ? 'minimum' : 'maximum'}" aria-valuetext="${esc(txt(v))}">`;
    return `<div class="df-slider${hist ? ' df-with-hist' : ''}" style="--lo:${lo / 10}%;--hi:${hi / 10}%">${bars}<div class="df-rail"><div class="df-fill"></div>${thumb('min', lo, loV)}${thumb('max', hi, hiV)}</div>`
      + `<div class="df-ends"><output data-out="min">${esc(txt(loV))}</output><span>${scale.log ? 'log scale' : ''}</span><output data-out="max">${esc(txt(hiV))}</output></div></div>`
      + `<div class="df-span">${c.n.toLocaleString()} with a value${sel.min !== undefined || sel.max !== undefined ? '' : ` · ${txt(c.domain.min)} – ${txt(c.domain.max)}`}</div>`;
  }

  _buckets(s, sel) {
    const c = this._counts[s.key];
    if (!c || !c.buckets) return '<div class="df-span">no values</div>';
    const unit = s.unit !== undefined ? s.unit : (s.prop && s.prop.unitText) || '';
    const custom = (sel.min !== undefined || sel.max !== undefined) && !c.buckets.some((b) => isBucket(sel, b));
    const chips = c.buckets.map((b, i) => {
      const on = isBucket(sel, b);
      return `<button type="button" class="df-chip${b.n ? '' : ' df-zero'}" aria-pressed="${on}" data-act="bucket" data-key="${esc(s.key)}" data-i="${i}" data-k="bk:${esc(s.key)}:${i}">${esc(b.label)}${unit ? ` <span class="dv-u">${esc(unit)}</span>` : ''} <span class="df-count">${b.n.toLocaleString()}</span></button>`;
    }).join('');
    const own = custom ? `<button type="button" class="df-chip" aria-pressed="true" data-reset="${esc(s.key)}" data-k="bkc:${esc(s.key)}">${sel.min !== undefined ? this._num(s, sel.min) : ''}–${sel.max !== undefined ? this._num(s, sel.max) : ''} ✕</button>` : '';
    return `<div class="df-chips">${chips}${own}</div>`;
  }

  _rating(s, sel) {
    const c = this._counts[s.key];
    if (!c || !c.levels) return '<div class="df-span">no values</div>';
    const steps = s.as === 'min-level' || s.style === 'steps';
    const top = c.levels.length ? c.levels[0].level : 5;
    const items = c.levels.map(({ level, n }) => {
      const on = sel.min === level && !sel.minOpen;
      const stars = steps ? `${esc(s.label)} ≥ ${level}` : `<span class="df-stars" aria-hidden="true">${'★'.repeat(level)}${'☆'.repeat(Math.max(0, top - level))}</span> <span>&amp; up</span>`;
      const aria = steps ? '' : ` aria-label="${level} or more"`;
      return `<li class="${n ? '' : 'df-zero'}"><button type="button" class="df-rate" aria-pressed="${on}"${aria} data-act="rating" data-p="${esc(s.property)}" data-level="${level}" data-k="rt:${esc(s.key)}:${level}">${stars}<span class="df-count">${n.toLocaleString()}</span></button></li>`;
    }).join('');
    return `<ul class="df-values df-ratings">${items}</ul>`;
  }

  _date(s, sel) {
    const c = this._counts[s.key] || { presets: [], older: [] };
    const box = (side) => `<input type="date" data-${side}="${esc(s.property)}" data-k="${side}:${esc(s.key)}" aria-label="${esc(s.label)} ${side === 'min' ? 'from' : 'until'}" value="${esc(typeof sel[side] === 'string' ? sel[side].slice(0, 10) : '')}"${c.domain && c.domain.min ? ` min="${esc(c.domain.min.slice(0, 10))}"` : ''}${c.domain && c.domain.max ? ` max="${esc(c.domain.max.slice(0, 10))}"` : ''}>`;
    const chip = (act, p, d, label, n, on) => `<button type="button" class="df-chip${n ? '' : ' df-zero'}" aria-pressed="${on}" data-act="${act}" data-p="${esc(s.property)}" data-date="${esc(d)}" data-k="${act}:${esc(s.key)}:${esc(p)}">${esc(label)} <span class="df-count">${n.toLocaleString()}</span></button>`;
    const presets = (c.presets || []).filter((x) => x.min).map((x) => chip('date-from', x.preset, x.min, presetLabel(x.preset), x.n, sel.min === x.min && sel.max === undefined && !sel.minOpen)).join('');
    const older = (c.older || []).filter((x) => x.max).map((x) => chip('date-older', x.preset, x.max, presetLabel(x.preset, true), x.n, sel.max === x.max && sel.maxOpen && sel.min === undefined)).join('');
    return `<div class="df-chips">${presets}${older}</div><div class="df-range df-dates">${box('min')}<span>–</span>${box('max')}</div><div class="df-span">${c.n ? `${esc(String(c.min).slice(0, 10))} – ${esc(String(c.max).slice(0, 10))} · ${c.n.toLocaleString()} with a date` : 'no dates'}</div>`;
  }

  /** chips, swatch, gallery, picture-list and grid: buttons that press, no checkboxes (each kind's own look). */
  _tiles(s, sel) {
    const { shown, more, findBox, chosen } = this._entries(s, sel, { limit: LIMIT[s.as] || SHOWN });
    const cols = s.columns || { gallery: 2, grid: 3, swatch: 3 }[s.as];
    const items = shown.map(([k, n]) => {
      const on = chosen.has(k);
      const label = this._label(s, k);
      const aria = `${valueText(k, s.prop) || k}, ${n.toLocaleString()}`;
      let inner;
      if (s.as === 'chips' || s.as === 'grid') inner = `<span class="df-label">${label}</span>${s.as === 'chips' ? ` <span class="df-count">${n.toLocaleString()}</span>` : ''}`;
      else {
        const src = this._imageOf(s, k);
        const color = s.colors && s.colors[k];
        const pic = src ? this._picture(src, s.as === 'picture-list' ? 'df-pic' : 'df-tile-img', '') : color ? `<span class="df-tile-img df-color" style="background:${esc(color)}"></span>` : `<span class="df-tile-img df-mono dv-h${hueOf(k)}" aria-hidden="true">${esc(initials(valueText(k, s.prop) || k))}</span>`;
        inner = `${pic}<span class="df-label">${label}</span><span class="df-count">${n.toLocaleString()}</span>`;
      }
      return `<li class="${n ? '' : 'df-zero'}"><button type="button" class="df-tile" aria-pressed="${on}" aria-label="${esc(aria)}" title="${esc(aria)}" data-act="value" data-p="${esc(s.property)}" data-value="${esc(k)}" data-k="t:${esc(s.key)}:${esc(k)}">${inner}</button></li>`;
    }).join('');
    return `${findBox}<ul class="df-tiles df-tiles-${esc(s.as)}"${cols ? ` style="--df-cols:${Number(cols) || 2}"` : ''}>${items}</ul>${more}`;
  }

  _listbox(s, sel) {
    const { shown, findBox, chosen } = this._entries(s, sel, { limit: LIMIT.listbox });
    const size = Math.max(4, Math.min(s.size || 8, shown.length));
    const opts = shown.map(([k, n]) => `<option value="${esc(k)}"${chosen.has(k) ? ' selected' : ''}>${this._label(s, k)}  (${n.toLocaleString()})</option>`).join('');
    return `${findBox}<select multiple size="${size}" class="df-listbox" data-act="listbox" data-p="${esc(s.property)}" data-k="lb:${esc(s.key)}" aria-label="${esc(s.label)} (Ctrl or Shift to pick several)">${opts}</select><div class="df-span">${chosen.size ? `${chosen.size} picked · ` : ''}Ctrl / Shift to pick several</div>`;
  }

  _tree(s) {
    const counts = this._counts[s.key] || [];
    const state = this._rail.facets;
    const level = (i) => {
      const p = s.levels[i];
      const chosen = state[p] && state[p].values && state[p].values.length === 1 ? String(state[p].values[0]) : null;
      const prop = labelled(this._target.data, this._target.base)[p] || {};
      let entries = Object.entries(counts[i] || {});
      if (s.sort === 'alpha') entries.sort((a, b) => a[0].localeCompare(b[0]));
      const lim = s.limit || SHOWN;
      const all = this._open.has(`${s.key}:${i}:${chosen}`);
      const shown = chosen ? entries.filter(([k]) => k === chosen) : all ? entries : entries.slice(0, lim);
      const more = !chosen && !all && entries.length > lim ? `<li><button class="dv-link df-more" data-more="${esc(`${s.key}:${i}:${chosen}`)}" data-k="more:${esc(s.key)}:${i}">Show ${entries.length - lim} more</button></li>` : '';
      const items = shown.map(([k, n]) => {
        const on = k === chosen;
        const deeper = on && i + 1 < s.levels.length ? level(i + 1) : '';
        return `<li><button type="button" class="df-node" aria-pressed="${on}"${i + 1 < s.levels.length ? ` aria-expanded="${on}"` : ''} data-act="tree" data-key="${esc(s.key)}" data-level="${i}" data-value="${esc(k)}" data-k="tr:${esc(s.key)}:${i}:${esc(k)}"><span class="df-caret" aria-hidden="true">${i + 1 < s.levels.length ? (on ? '▾' : '▸') : ''}</span><span class="df-label">${esc(valueText(k, prop) || k)}</span><span class="df-count">${n.toLocaleString()}</span></button>${deeper}</li>`;
      }).join('');
      return `<ul class="df-tree">${items}${more}</ul>`;
    };
    return level(0);
  }

  /** McMaster's "Choose a Category": one row per group the view draws, a link-styled name and its count; one pick at
      a time, the picked row marked (aria-current) and a click on it again giving every group back. `clear` adds an
      "All …" row at the top. A group no facet can pick ("No …") is not listed. */
  _nav(s, sel) {
    const rows = ((this._counts[s.key] || {}).entries || []).filter((e) => e.facet);
    const at = rows.findIndex((e) => sameFacet(sel, e.facet));
    const row = (i, label, n, on, extra = '') => `<li><button type="button" class="df-nav-row${extra}"${on ? ' aria-current="true"' : ''} data-act="nav" data-key="${esc(s.key)}" data-i="${i}" data-k="nav:${esc(s.key)}:${i}"><span class="df-label">${esc(label)}</span>${n === null ? '' : ` <span class="df-count">(${n.toLocaleString()})</span>`}</button></li>`;
    const clear = s.clear ? row(-1, typeof s.clear === 'string' ? s.clear : `All ${s.prop.label}`, null, at < 0, ' df-nav-clear') : '';
    return `<ul class="df-nav">${clear}${rows.map((e, i) => row(i, e.label, e.n, i === at)).join('')}</ul>`;
  }

  _searchBox(s) {
    const sel = this._rail.facets[s.properties[0]] || {};
    const props = labelled(this._target.data, this._target.base);
    const names = s.properties.map((p) => (props[p] || {}).label || p).join(', ');
    return `<input class="df-search" type="search" data-act="search" data-key="${esc(s.key)}" data-k="q:${esc(s.key)}" placeholder="${esc(s.placeholder || `Search ${names.toLowerCase()}`)}" aria-label="${esc(s.label)}: ${s.match === 'startsWith' ? 'starts with' : 'contains'}" value="${esc(sel.text || '')}"><div class="df-span">${s.match === 'startsWith' ? 'starts with' : 'contains'}, in ${esc(names)}</div>`;
  }

  _popular(s) {
    const counts = this._counts[s.key] || [];
    const items = s.options.map((o, i) => {
      const c = parseClause(o.filter, { wide: true });
      const on = c ? hasClause(this._rail.facets, c) : false;
      return `<li class="${counts[i] ? '' : 'df-zero'}"><label><input type="checkbox" data-act="popular" data-key="${esc(s.key)}" data-i="${i}" data-k="pop:${esc(s.key)}:${i}"${on ? ' checked' : ''}${c ? '' : ' disabled'}><span class="df-label">${esc(o.label)}</span><span class="df-count">${(counts[i] || 0).toLocaleString()}</span></label></li>`;
    }).join('');
    return `<ul class="df-values">${items}</ul>`;
  }

  _current() {
    const props = labelled(this._target.data, this._target.base);
    const chips = [];
    const chip = (label, attrs) => chips.push(`<li><button type="button" class="df-chip df-on" ${attrs} aria-label="Remove ${esc(label)}">${esc(label)} <span aria-hidden="true">✕</span></button></li>`);
    for (const [p, f] of Object.entries(this._rail.facets)) {
      const prop = props[p] || {};
      const name = prop.label || p;
      const u = prop.unitText ? ` ${prop.unitText}` : '';
      const n = (v) => (typeof v === 'number' ? fmtNum(v, prop.decimals, numOpts(prop)) : String(v).slice(0, 10));
      for (const v of f.values || []) chip(`${name}: ${valueText(String(v), prop) || v}`, `data-act="remove" data-p="${esc(p)}" data-field="values" data-value="${esc(String(v))}" data-k="cur:${esc(p)}:v:${esc(String(v))}"`);
      for (const v of f.exclude || []) chip(`${name}: not ${valueText(String(v), prop) || v}`, `data-act="remove" data-p="${esc(p)}" data-field="exclude" data-value="${esc(String(v))}" data-k="cur:${esc(p)}:x:${esc(String(v))}"`);
      if (f.min !== undefined || f.max !== undefined) {
        const text = f.min !== undefined && f.max !== undefined ? `${n(f.min)}–${n(f.max)}` : f.min !== undefined ? `${f.minOpen ? '>' : '≥'} ${n(f.min)}` : `${f.maxOpen ? '<' : '≤'} ${n(f.max)}`;
        chip(`${name}: ${text}${u}`, `data-act="remove" data-p="${esc(p)}" data-field="bounds" data-k="cur:${esc(p)}:b"`);
      }
      if (f.has) chip(`Has ${name}`, `data-act="remove" data-p="${esc(p)}" data-field="has" data-k="cur:${esc(p)}:h"`);
      if (f.hasAny) chip(`Has any of ${f.hasAny.map((x) => (props[x] || {}).label || x).join(', ')}`, `data-act="remove" data-p="${esc(p)}" data-field="hasAny" data-k="cur:${esc(p)}:ha"`);
      if (f.text) chip(`${name} ${f.textMatch === 'startsWith' ? 'starts with' : 'contains'} “${f.text}”`, `data-act="remove" data-p="${esc(p)}" data-field="text" data-k="cur:${esc(p)}:t"`);
    }
    const rest = this._rail.rest.length ? `<li><button type="button" class="df-chip" data-edit data-k="cur:rest">+${this._rail.rest.length} custom</button></li>` : '';
    if (!chips.length && !rest) return '<p class="df-span">No filters: every row.</p>';
    return `<ul class="df-chips df-current">${chips.join('')}${rest}</ul>${chips.length ? '<button class="dv-link df-clear" data-clear data-k="clear2">Clear all</button>' : ''}`;
  }

  // ------------------------------------------------------------------ writing back

  /** Write the rail's state back into the all-views filter; the custom part stays as it was. */
  _set(change) {
    const t = this._target;
    const rail = toRail(t.filters, this._cfg);
    const before = JSON.stringify(rail.facets);
    const was = JSON.parse(before);
    change(rail.facets);
    // a parent's new pick, settled into the facets nested under it (`parent:`, kit gap 8): a run no longer on the picked
    // board moves to that board's first listed run, in the same change (one filter, one redraw, one URL)
    const specs = this._specs || [];
    if (JSON.stringify(rail.facets) !== before && specs.some((s) => s.parent)) {
      const changed = [...new Set([...Object.keys(was), ...Object.keys(rail.facets)])].filter((p) => JSON.stringify(was[p]) !== JSON.stringify(rail.facets[p]) && specs.some((s) => s.parent === p));
      if (changed.length) {
        let settled = rail.facets;
        for (const p of changed) settled = settleChildren(this._rows || t.data.rows, settled, specs, p, this._rest || (() => true));
        // settleChildren returns a new object: the rail's own is emptied and refilled from it
        for (const k of Object.keys(rail.facets)) delete rail.facets[k];
        Object.assign(rail.facets, settled);
      }
    }
    for (const [k, f] of Object.entries(rail.facets)) {
      if (f.values && !f.values.length) { delete f.values; delete f.match; }
      if (f.exclude && !f.exclude.length) { delete f.exclude; delete f.excludeMatch; }
      if (f.min === null || f.min === '' || Number.isNaN(f.min)) { delete f.min; delete f.minOpen; }
      if (f.max === null || f.max === '' || Number.isNaN(f.max)) { delete f.max; delete f.maxOpen; }
      if (f.hasAny && f.hasAny.length < 2) { if (f.hasAny.length === 1) rail.facets[f.hasAny[0]] = { ...(rail.facets[f.hasAny[0]] || {}), has: true }; delete f.hasAny; }
      if (f.text === '' || f.text === undefined) { delete f.text; delete f.textIn; delete f.textMatch; }
      if (!ACTIVE(f)) delete rail.facets[k];
    }
    t.filters = fromRail(rail.facets, rail.rest);
  }

  _typed(p, raw) {
    const prop = this._target.data.properties[p] || {};
    if (prop.type === 'number' && raw !== '' && !Number.isNaN(Number(raw))) return Number(raw);
    if (prop.type === 'boolean' && (raw === 'true' || raw === 'false')) return raw === 'true';
    return raw;
  }

  _match(p) {
    return (this._target.data.properties[p] || {}).type === 'list' ? 'contains' : 'equals';
  }

  _tick(p, value, on) {
    this._set((facets) => {
      const f = facets[p] || {};
      f.match = f.match || this._match(p);
      const list = (f.values || []).filter((x) => String(x) !== String(value));
      if (on) list.push(value);
      f.values = list;
      facets[p] = f;
    });
  }

  _spec(key) { return (this._specs || []).find((s) => s.key === key); }

  _changed(e) {
    const el = e.target;
    if (!el.isConnected) return;
    const act = el.dataset.act;
    if (act === 'select') {
      const p = el.dataset.p;
      const raw = el.tagName === 'SELECT' ? el.value : el.dataset.value;
      this._set((facets) => { const f = facets[p] || {}; f.values = raw === '' ? [] : [this._typed(p, raw)]; f.match = this._match(p); facets[p] = f; });
    } else if (act === 'toggle') {
      const p = el.dataset.p;
      const s = (this._specs || []).find((x) => x.as === 'toggle' && x.property === p);
      const onValue = s && s.value !== undefined ? s.value : true;
      this._set((facets) => { const f = facets[p] || {}; f.values = el.checked ? [onValue] : []; f.match = this._match(p); facets[p] = f; });
    } else if (act === 'slider') {
      const key = el.dataset.key, p = el.dataset.p, side = el.dataset.side;
      const scale = this._scales[key];
      if (!scale) return;
      const pos = Number(el.value);
      this._set((facets) => {
        const f = facets[p] || {};
        if ((side === 'min' && pos <= 0) || (side === 'max' && pos >= 1000)) { delete f[side]; delete f[side + 'Open']; }
        else { f[side] = scale.toValue(pos); delete f[side + 'Open']; }
        facets[p] = f;
      });
    } else if (act === 'listbox') {
      const p = el.dataset.p;
      const picked = [...el.selectedOptions].map((o) => this._typed(p, o.value));
      const shown = new Set([...el.options].map((o) => o.value));
      this._set((facets) => {
        const f = facets[p] || {};
        // values the find box hid stay ticked
        f.values = [...(f.values || []).filter((x) => !shown.has(String(x))), ...picked];
        f.match = this._match(p);
        facets[p] = f;
      });
    } else if (act === 'popular') {
      const s = this._spec(el.dataset.key);
      const o = s && s.options[Number(el.dataset.i)];
      const c = o && parseClause(o.filter, { wide: true });
      if (c) this._set((facets) => applyClause(facets, c, el.checked, this._match(c.property)));
    } else if (act === 'hasmode') {
      const s = this._spec(el.dataset.key);
      if (!s) return;
      this._set((facets) => {
        const ticked = s.properties.filter((p) => (facets[p] || {}).has || ((facets[s.properties[0]] || {}).hasAny || []).includes(p));
        for (const p of s.properties) if (facets[p]) { delete facets[p].has; delete facets[p].hasAny; }
        if (el.value === 'any' && ticked.length > 1) facets[ticked[0]] = { ...(facets[ticked[0]] || {}), hasAny: ticked };
        else for (const p of ticked) facets[p] = { ...(facets[p] || {}), has: true };
      });
    } else if (el.dataset.value !== undefined && el.type === 'checkbox') {
      const p = el.dataset.p;
      this._tick(p, this._typed(p, el.dataset.value), el.checked);
    } else if (el.dataset.min !== undefined || el.dataset.max !== undefined) {
      const p = el.dataset.min ?? el.dataset.max;
      const side = el.dataset.min !== undefined ? 'min' : 'max';
      const num = (this._target.data.properties[p] || {}).type === 'number';
      this._set((facets) => {
        const f = facets[p] || {};
        if (el.value === '') delete f[side]; else f[side] = num ? Number(el.value) : el.value;
        delete f[side + 'Open'];
        facets[p] = f;
      });
    } else if (el.dataset.has !== undefined) {
      const p = el.dataset.has;
      const s = this._spec(el.dataset.key);
      this._set((facets) => {
        const group = s ? s.properties : [p];
        const anyList = (facets[group[0]] || {}).hasAny;
        if (anyList) {
          const next = el.checked ? [...anyList, p] : anyList.filter((x) => x !== p);
          delete facets[group[0]].hasAny;
          if (next.length) facets[next[0]] = { ...(facets[next[0]] || {}), hasAny: next };
        } else {
          facets[p] = { ...(facets[p] || {}), has: el.checked };
          if (!el.checked) delete facets[p].has;
          // "any of" chosen before a second tick: the ticks combine with or
          if (el.checked && s && s.match === 'any') {
            const ticked = group.filter((x) => (facets[x] || {}).has);
            if (ticked.length > 1) { for (const x of ticked) delete facets[x].has; facets[ticked[0]] = { ...(facets[ticked[0]] || {}), hasAny: ticked }; }
          }
        }
      });
    }
  }

  _input(e) {
    const el = e.target;
    if (el.matches('.df-find')) { this._find[el.dataset.p] = el.value; this._paint(); return; }
    if (el.dataset.act === 'search') { clearTimeout(this._typing); this._typing = setTimeout(() => this._search(el), 200); return; }
    if (el.dataset.act === 'slider') {
      // live: the thumb's value and the fill move while dragging; the filter changes on release (change)
      const box = el.closest('.df-slider');
      const scale = this._scales[el.dataset.key];
      const [a, b] = box.querySelectorAll('input[type=range]');
      if (Number(a.value) > Number(b.value)) { if (el === a) a.value = b.value; else b.value = a.value; }
      box.style.setProperty('--lo', `${a.value / 10}%`);
      box.style.setProperty('--hi', `${b.value / 10}%`);
      const s = this._spec(el.dataset.key);
      const unit = s && (s.unit !== undefined ? s.unit : (s.prop && s.prop.unitText)) || '';
      const v = scale.toValue(Number(el.value));
      const text = `${fmtNum(v, s && s.prop && s.prop.decimals, numOpts(s && s.prop))}${unit ? ` ${unit}` : ''}`;
      box.querySelector(`output[data-out="${el.dataset.side}"]`).textContent = text;
      el.setAttribute('aria-valuetext', text);
    }
  }

  _search(el) {
    const s = this._spec(el.dataset.key);
    if (!s) return;
    const text = el.value;
    this._set((facets) => {
      const p = s.properties[0];
      const f = facets[p] || {};
      if (text) Object.assign(f, { text, textIn: s.properties }, s.match === 'startsWith' ? { textMatch: 'startsWith' } : {});
      else { delete f.text; delete f.textIn; delete f.textMatch; }
      facets[p] = f;
    });
  }

  _clicked(e) {
    const t = e.target;
    const btn = t.closest('[data-act]');
    const act = btn && btn.tagName === 'BUTTON' ? btn.dataset.act : null;
    if (t.closest('[data-clear]')) { e.preventDefault(); this._set((facets) => { for (const k of Object.keys(facets)) delete facets[k]; }); }
    else if (t.closest('[data-reset]')) {
      const key = t.closest('[data-reset]').dataset.reset;
      const s = this._spec(key);
      const owned = s ? (s.as === 'tree' ? s.levels : s.as === 'has' || s.as === 'search' ? s.properties : [s.property]) : [key];
      this._set((facets) => { for (const p of owned) delete facets[p]; });
    } else if (t.closest('[data-more]')) { this._open.add(t.closest('[data-more]').dataset.more); this._paint(); }
    else if (t.closest('[data-edit]')) { this._target.openMenu('filter'); }
    else if (act === 'fold') { const k = btn.dataset.key; const s = this._spec(k); this._folded.set(k, !(this._folded.has(k) ? this._folded.get(k) : !!(s && s.collapsed))); this._paint(); }
    else if (act === 'info') { const k = btn.dataset.key; if (this._help.has(k)) this._help.delete(k); else this._help.add(k); this._paint(); }
    else if (act === 'value') { const p = btn.dataset.p; this._tick(p, this._typed(p, btn.dataset.value), btn.getAttribute('aria-pressed') !== 'true'); }
    else if (act === 'exclude') {
      const p = btn.dataset.p, v = this._typed(p, btn.dataset.value);
      const on = btn.getAttribute('aria-pressed') !== 'true';
      this._set((facets) => {
        const f = facets[p] || {};
        f.exclude = (f.exclude || []).filter((x) => String(x) !== String(v));
        if (on) { f.exclude.push(v); f.values = (f.values || []).filter((x) => String(x) !== String(v)); }
        f.excludeMatch = this._match(p);
        facets[p] = f;
      });
    } else if (act === 'bucket') {
      const s = this._spec(btn.dataset.key);
      const b = s && this._counts[s.key].buckets[Number(btn.dataset.i)];
      if (!b) return;
      const on = btn.getAttribute('aria-pressed') !== 'true';
      this._set((facets) => {
        const f = { ...(facets[s.property] || {}) };
        for (const k of ['min', 'minOpen', 'max', 'maxOpen']) delete f[k];
        if (on) { if (b.min !== undefined) f.min = b.min; if (b.max !== undefined) { f.max = b.max; if (b.maxOpen) f.maxOpen = true; } }
        facets[s.property] = f;
      });
    } else if (act === 'rating') {
      const p = btn.dataset.p, level = Number(btn.dataset.level);
      const on = btn.getAttribute('aria-pressed') !== 'true';
      this._set((facets) => { const f = { ...(facets[p] || {}) }; delete f.minOpen; if (on) f.min = level; else delete f.min; facets[p] = f; });
    } else if (act === 'date-from' || act === 'date-older') {
      const p = btn.dataset.p, d = btn.dataset.date;
      const on = btn.getAttribute('aria-pressed') !== 'true';
      this._set((facets) => {
        const f = { ...(facets[p] || {}) };
        for (const k of ['min', 'minOpen', 'max', 'maxOpen']) delete f[k];
        if (on && act === 'date-from') f.min = d;
        if (on && act === 'date-older') { f.max = d; f.maxOpen = true; }
        facets[p] = f;
      });
    } else if (act === 'nav') {
      const s = this._spec(btn.dataset.key);
      const i = Number(btn.dataset.i);
      const e = s && i >= 0 ? ((this._counts[s.key] || {}).entries || []).filter((x) => x.facet)[i] : null;
      if (!s) return;
      // single-select: the picked row again (or "All …") clears it, and every group comes back
      const again = btn.getAttribute('aria-current') === 'true';
      this._set((facets) => { delete facets[s.property]; if (e && !again) facets[s.property] = { ...e.facet }; });
    } else if (act === 'tree') {
      const s = this._spec(btn.dataset.key);
      const i = Number(btn.dataset.level);
      const on = btn.getAttribute('aria-pressed') !== 'true';
      const p = s.levels[i];
      const v = this._typed(p, btn.dataset.value);
      this._set((facets) => {
        for (const l of s.levels.slice(i + (on ? 1 : 0))) if (facets[l]) { delete facets[l].values; delete facets[l].match; }
        if (on) facets[p] = { ...(facets[p] || {}), values: [v], match: this._match(p) };
      });
    } else if (act === 'remove') {
      const p = btn.dataset.p, field = btn.dataset.field, v = btn.dataset.value;
      this._set((facets) => {
        const f = facets[p];
        if (!f) return;
        if (field === 'values' || field === 'exclude') f[field] = (f[field] || []).filter((x) => String(x) !== v);
        else if (field === 'bounds') for (const k of ['min', 'minOpen', 'max', 'maxOpen']) delete f[k];
        else if (field === 'text') { delete f.text; delete f.textIn; delete f.textMatch; }
        else delete f[field];
      });
    }
  }
}

/** Is the rail's state of a property exactly this one-group facet (a nav row's)? */
function sameFacet(sel, f) {
  if (!sel || !f) return false;
  if (f.values) return !!sel.values && sel.values.length === 1 && String(sel.values[0]) === String(f.values[0]) && !sel.min && !sel.max;
  return sel.min === f.min && sel.max === f.max && !!sel.maxOpen === !!f.maxOpen && !sel.minOpen && !(sel.values && sel.values.length);
}

function rank(order, v) { const i = order.map(String).indexOf(v); return i < 0 ? order.length : i; }
function slugKey(k) { return String(k).replace(/[^A-Za-z0-9_-]/g, '_'); }
function initials(text) { const w = String(text).split(/[\s_-]+/).filter(Boolean); return (w.length > 1 ? w[0][0] + w[1][0] : String(text).slice(0, 2)).toUpperCase(); }
function nice2(v) { return Math.abs(v) >= 100 ? Math.round(v) : Number(v.toPrecision(2)); }

/** Is a parsed clause part of the rail's state? (a popular filter's tick) */
function hasClause(facets, c) {
  const f = facets[c.property];
  if (!f) return false;
  if (c.kind === 'eq' || c.kind === 'contains') return (f.values || []).some((x) => String(x) === String(c.value));
  if (c.kind === 'min' || c.kind === 'max') return f[c.kind] === c.value && !!f[c.kind + 'Open'] === !!c.open;
  if (c.kind === 'has') return !!f.has;
  return false;
}

function applyClause(facets, c, on, match) {
  const f = facets[c.property] || {};
  if (c.kind === 'eq' || c.kind === 'contains') {
    const list = (f.values || []).filter((x) => String(x) !== String(c.value));
    if (on) list.push(c.value);
    f.values = list;
    f.match = c.kind === 'contains' ? 'contains' : match;
  } else if (c.kind === 'min' || c.kind === 'max') {
    delete f[c.kind]; delete f[c.kind + 'Open'];
    if (on) { f[c.kind] = c.value; if (c.open) f[c.kind + 'Open'] = true; }
  } else if (c.kind === 'has') { if (on) f.has = true; else delete f.has; }
  facets[c.property] = f;
}

if (!customElements.get('data-facets')) customElements.define('data-facets', DataFacets);
