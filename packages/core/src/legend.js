/* The series legend every data-ui chart draws (Zach, 2026-10-28, on a sim2real card with 8 servo lines: "where there
   is a legend there is like no reason to not make that legend interactive… ensure this feature is in data-ui charts by
   default"). One rule and one control for type: chart, the time series cards (simple and interactive), trajectory,
   scene3d and the playback range's overview:

     a click shows or hides a series (hidden: greyed and struck through); a double-click or Alt + click shows only it,
     and again on the one left shows them all; a quiet Reset beside the legend while anything is hidden; each entry a
     <button aria-pressed> (pressed = shown), so Tab, Enter and Space work as on any button.

   A hidden series leaves the DRAWING only: rows, counts, the status line and the other series' readouts are unchanged.
   The hidden set is a list of series names (the legend's labels), held by the host (input.hiddenSeries,
   host.setHiddenSeries; docs/CONTRACT.md §31) and kept in the URL: `l=<name>,<name>` on a <data-views>, `l.<panel>=`
   in a <data-dashboard>, `l.<dashboard>.<panel>=` with several dashboards on a page (the clock's scoping).

   The pure parts run in Node (tests/unit/legend.test.mjs); SeriesLegend is the DOM part. */

import { esc } from './format.js';

/** The legend's rule (Rerun's): a click shows or hides that series; Alt + click shows only it, or, when it is already
    the only one shown, shows them all again. `shown` is one boolean per series; returns the new array. */
export function legendClick(shown, i, alt = false) {
  if (!alt) return shown.map((s, k) => (k === i ? !s : s));
  const only = shown[i] && shown.every((s, k) => k === i || !s);
  return shown.map((_s, k) => (only ? true : k === i));
}

/** One press on entry `i`: {shown, before, i} -> the next state. `detail` is the click's count (0 from the keyboard).
    WHY `before`: a double-click arrives as click (detail 1), click (detail 2), dblclick; the first click toggles at once
    (a single click never waits out the double-click delay), and the second isolates from the state before the pair, so
    the net effect is isolate, never a toggle left behind. */
export function legendPress(state, i, { alt = false, detail = 1 } = {}) {
  const { shown } = state;
  if (detail >= 2 && state.before && state.i === i) return { shown: legendClick(state.before, i, true), before: state.before, i };
  return { shown: legendClick(shown, i, alt), before: shown, i };
}

/** The hidden set after a click on entry `i` (Alt: isolate), over names: `names` this legend's entries, `hidden` the
    set before. A name this legend does not show now (a filter took its rows) keeps its state; all shown is empty. */
export function nextHidden(names, hidden, i, { alt = false } = {}) {
  return hiddenAfter(names, hidden, legendClick(names.map((n) => !(hidden || []).includes(n)), i, alt));
}

/** The hidden set once `names` are shown as `shown` says (nextHidden's rule for any next state). */
export function hiddenAfter(names, hidden, shown) {
  if (shown.every(Boolean)) return [];
  const here = new Set(names);
  return [...(hidden || []).filter((n) => !here.has(n)), ...names.filter((_n, k) => !shown[k])];
}

/** A hidden set as one URL value: each name URI-encoded, comma-joined (a comma inside a name is %2C). */
export function encodeHidden(names) {
  return (names || []).map((n) => encodeURIComponent(String(n))).join(',');
}

/** The URL value back to names; a malformed escape keeps the text as written. */
export function decodeHidden(text) {
  if (text === null || text === undefined || text === '') return [];
  return String(text).split(',').filter((x) => x !== '').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
}

/** The URL key: `l` (a <data-views>), `l.<panel>` (a dashboard's panel), `l.<scope>.<panel>` (several dashboards). */
export function legendKey(scope = null, panel = null) {
  if (panel === null || panel === undefined) return 'l';
  return scope ? `l.${scope}.${panel}` : `l.${panel}`;
}

/** Each panel's hidden set from URL params ({panel: names}; a panel with none is absent). `scope` as the clock's key:
    null plain, a string scoped (falling back to the plain key), false not in the URL. */
export function readLegendParams(params, panels, scope = null) {
  const out = {};
  if (scope === false) return out;
  for (const p of panels) {
    const own = legendKey(scope, p), plain = legendKey(null, p);
    const text = scope && params.has(own) ? params.get(own) : params.get(plain);
    const names = decodeHidden(text);
    if (names.length) out[p] = names;
  }
  return out;
}

/** Write each panel's hidden set into `params` (and return it). Scoped, an empty set over a plain key writes an empty
    scoped key, so a reload does not bring the plain one back (the clock's rule, writeClockParams). */
export function writeLegendParams(params, legend, panels, scope = null) {
  if (scope === false) return params;
  for (const p of panels) {
    const key = legendKey(scope, p);
    const names = (legend && legend[p]) || [];
    if (names.length) params.set(key, encodeHidden(names));
    else if (scope && params.has(legendKey(null, p))) params.set(key, '');
    else params.delete(key);
  }
  return params;
}

/** The hidden set a view draws with: the host's (input.hiddenSeries), else the view's own (a host without the call). */
export function hiddenOf(input, local = []) {
  return input && Array.isArray(input.hiddenSeries) ? input.hiddenSeries : local;
}

/** The legend control: one <button aria-pressed> per series inside `box`, and Reset. `onChange(hidden)` is called on
    every press with the new hidden set; the view redraws with it and the control tells the host
    (host.setHiddenSeries). draw() keeps the buttons (and the focus) when the names have not changed. */
export class SeriesLegend {
  /** keyClass: the view's own class for an entry (its swatch styles); title: the legend's label, if any. */
  constructor(box, { host = null, onChange = () => {}, keyClass = '' } = {}) {
    this.box = box;
    this.host = host;
    this.onChange = onChange;
    this.keyClass = keyClass;
    this.names = [];
    this.hidden = [];
    this._press = null;
    box.classList.add('dv-legend');
    if (!box.hasAttribute('role')) box.setAttribute('role', 'group');
    this._onClick = (e) => {
      const reset = e.target.closest('.dv-legend-reset');
      if (reset && box.contains(reset)) { this.set([], true); return; }
      const b = e.target.closest('.dv-legend-key');
      if (!b || !box.contains(b)) return;
      const i = this.names.indexOf(b.dataset.legendSeries);
      if (i < 0) return;
      const shown = this.names.map((n) => !this.hidden.includes(n));
      this._press = legendPress({ ...(this._press || {}), shown }, i, { alt: e.altKey, detail: e.detail });
      this.set(hiddenAfter(this.names, this.hidden, this._press.shown), true);
    };
    // the double-click itself was handled by its second click (legendPress); keep the browser from selecting the label
    this._onDbl = (e) => { if (e.target.closest('.dv-legend-key')) e.preventDefault(); };
    this._onDown = (e) => { if (e.detail > 1 && e.target.closest('.dv-legend-key')) e.preventDefault(); };
    box.addEventListener('click', this._onClick);
    box.addEventListener('dblclick', this._onDbl);
    box.addEventListener('mousedown', this._onDown);
  }

  /** Draw the entries ([{name, swatch, extra?}]: swatch and extra are HTML) with this hidden set; title labels the group. */
  draw(entries, hidden = this.hidden, { title = '' } = {}) {
    const names = entries.map((e) => String(e.name));
    const html = entries.map((e) => `${e.swatch || ''}${esc(String(e.name))}${e.extra || ''}`);
    const same = names.length === this.names.length && names.every((n, k) => n === this.names[k]) && this._html && html.every((h, k) => h === this._html[k]);
    this.names = names;
    this._html = html;
    this.hidden = [...(hidden || [])];
    if (title) this.box.setAttribute('aria-label', title); else if (!this.box.getAttribute('aria-label')) this.box.setAttribute('aria-label', 'Series');
    if (!same) {
      this._press = null;
      const focused = this.box.contains(document.activeElement) ? document.activeElement.dataset.legendSeries : null;
      this.box.innerHTML = `${title ? `<span class="dv-legend-title">${esc(title)}</span>` : ''}${entries.map((e, k) => `<button type="button" class="dv-legend-key${this.keyClass ? ` ${this.keyClass}` : ''}" data-legend-series="${esc(names[k])}" aria-pressed="true" title="Click: hide or show · double-click or Alt + click: only this one">${html[k]}</button>`).join('')}<button type="button" class="dv-legend-reset" hidden title="Show every series">Reset</button>`;
      if (focused !== null && focused !== undefined) { const b = this._button(focused); if (b) b.focus(); }
    }
    this._pressed();
  }

  /** The hidden set to draw with, from a view's input: the host's when it changed since the host last said
      (input.hiddenSeries; Back / Forward, a shared link), else this legend's own (a press the host has not echoed yet, or
      a host without the call). Returns the set. */
  sync(input) {
    const h = input && Array.isArray(input.hiddenSeries) ? input.hiddenSeries : null;
    if (h && !(this._hostSaid && h.length === this._hostSaid.length && h.every((n, k) => n === this._hostSaid[k]))) {
      this._hostSaid = [...h];
      this.hidden = [...h];
      this._pressed();
    }
    return this.hidden;
  }

  /** Set the hidden set (from a press, Reset, or the host on Back / Forward); `fromPress` reports it. */
  set(hidden, fromPress = false) {
    this.hidden = [...(hidden || [])];
    this._pressed();
    if (!fromPress) return;
    this.onChange(this.hidden);
    if (this.host && typeof this.host.setHiddenSeries === 'function') this.host.setHiddenSeries(this.hidden);
  }

  /** Whether a series is shown. */
  shows(name) { return !this.hidden.includes(String(name)); }

  _button(name) {
    for (const b of this.box.querySelectorAll('.dv-legend-key')) if (b.dataset.legendSeries === name) return b;
    return null;
  }

  _pressed() {
    for (const b of this.box.querySelectorAll('.dv-legend-key')) b.setAttribute('aria-pressed', String(!this.hidden.includes(b.dataset.legendSeries)));
    const reset = this.box.querySelector('.dv-legend-reset');
    // WHY only for an entry drawn here: a name a filter took off this legend is still hidden, but nothing on screen is
    if (reset) reset.hidden = !this.names.some((n) => this.hidden.includes(n));
  }

  destroy() {
    this.box.removeEventListener('click', this._onClick);
    this.box.removeEventListener('dblclick', this._onDbl);
    this.box.removeEventListener('mousedown', this._onDown);
  }
}
