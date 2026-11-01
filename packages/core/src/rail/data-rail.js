/* <data-rail>: an app's left navigation, in three styles (docs/CONTRACT.md §27, docs/peps/0009-app-rail.md).

     <data-rail id="app-rail" brand="RobotDx" search="Search" search-keys="Ctrl K" current="fleet">
       <a href="#fleet" data-id="fleet" data-group="Monitor"><svg>…</svg>Fleet</a>
       <a href="#settings" data-id="settings" data-end><svg>…</svg>Settings</a>
     </data-rail>

   The links are the no-JS truth; with JavaScript the element reads them once and draws them in the style `mode` names:
   collapsed (icons only), expanded (Figma's: the label centred under the icon) or wide (Shopify's: icon and label in a
   row, a header with a collapse button and a search field). State is rail/model.js; the wide style is a side panel, so
   its edge is resize.js's splitter (§11), not a second helper. Light DOM, like the other elements, drawn with dv-rail-*
   classes and styles/rail.css. */

import { makeResizable } from '../resize.js';
import { esc } from '../format.js';
import { createRail, isRailMode, RAIL_MODE_OPTIONS } from './model.js';

const SVG = (body) => `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
const ICON_CLOSE = SVG('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>');
const ICON_OPEN = SVG('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>');
const ICON_SEARCH = SVG('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>');

const slug = (s) => String(s).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const num = (v, fallback) => (v !== undefined && v !== null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : fallback);

/** A label with a <wbr> at each camelCase seam (and after an underscore), so the 72px rail's narrow label column breaks
    "CalibrationRuns" as "Calibration / Runs" and not "Calibrati / onRuns". WHY a break hint and not a shorter name:
    <wbr> adds no character, so every authored letter still renders (CONTRACT §27, truthful labels). */
const labelHtml = (label) => String(label).split(/(?<=[a-z0-9])(?=[A-Z])|(?<=_)/).map(esc).join('<wbr>');

/** Does keydown `e` match a spec like "mod+alt+r"? mod is Ctrl or Cmd; alt and shift must match exactly. */
function matchesHotkey(e, spec) {
  const parts = String(spec).toLowerCase().split('+').map((p) => p.trim());
  const key = parts.pop();
  const has = (p) => parts.includes(p);
  if (has('mod') ? !(e.ctrlKey || e.metaKey) : e.ctrlKey !== has('ctrl') || e.metaKey !== has('meta')) return false;
  if (e.altKey !== has('alt') || e.shiftKey !== has('shift')) return false;
  return e.code === `Key${key.toUpperCase()}` || e.code === `Digit${key}` || String(e.key).toLowerCase() === key;
}

/** Normalise one destination from markup or script. `icon` is trusted markup (starts with "<") or text. */
function destination(raw) {
  const label = String(raw.label ?? '').trim();
  const icon = raw.icon ? String(raw.icon) : label.charAt(0).toUpperCase();
  return { id: raw.id ? String(raw.id) : slug(label), label, href: raw.href || '', icon, group: raw.group || '', end: !!raw.end,
    badge: raw.badge != null && raw.badge !== '' ? String(raw.badge) : '', parent: raw.parent ? String(raw.parent) : '' };
}

export class DataRail extends HTMLElement {
  static get observedAttributes() { return ['mode', 'current', 'brand', 'label', 'search', 'search-keys']; }

  /** The style: collapsed | expanded | wide. An unknown one is collapsed. */
  get mode() { return this._state().mode; }
  set mode(value) { this._change(value); }

  /** The open style the toggle returns to. */
  get lastOpen() { return this._state().lastOpen; }

  /** The `data-id` of the current destination (aria-current="page"). */
  get current() { return this.getAttribute('current') || ''; }
  set current(value) { if (value) this.setAttribute('current', value); else this.removeAttribute('current'); }

  get destinations() { return (this._dests || this._read()).map((d) => ({ ...d })); }
  set destinations(list) { this._dests = (list || []).map(destination); if (this._started) this._draw(); }

  /** Collapsed <-> the last open style. Returns the new mode. */
  toggle() { this._change(this._state().mode === 'collapsed' ? this._state().lastOpen : 'collapsed'); return this.mode; }

  connectedCallback() {
    // WHY wait: a module that defines the element before the parser reached its links would read none
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => this._start(), { once: true });
    else this._start();
  }

  disconnectedCallback() {
    document.removeEventListener('keydown', this._onKey);
    removeEventListener('pagehide', this._onHide);
    if (this._resize) { this._resize.destroy(); this._resize = null; }
    this._started = false;
  }

  attributeChangedCallback(name, was, value) {
    if (!this._started || was === value) return;
    if (name === 'mode') { if (!this._reflecting) this._change(value); } else if (name === 'current') this._markCurrent();
    else this._draw();
  }

  _state() {
    if (!this._rail) this._rail = createRail({ key: this.getAttribute('storage-key') || this.id || 'rail', mode: this.getAttribute('mode'), openMode: this.getAttribute('open-mode') });
    return this._rail;
  }

  /** The destinations as the light DOM wrote them (the first time), else as script set them. */
  _read() {
    const brand = this.querySelector(':scope > [data-brand-icon]');
    this._brandIcon = brand ? brand.innerHTML.trim() : (this._brandIcon || '');
    return [...this.querySelectorAll(':scope > a')].map((a) => {
      const art = a.querySelector(':scope > svg, :scope > img');
      const copy = a.cloneNode(true);
      copy.querySelectorAll('svg, img').forEach((n) => n.remove());
      return destination({ id: a.dataset.id, label: copy.textContent, href: a.getAttribute('href'), icon: art ? art.outerHTML : a.dataset.icon, group: a.dataset.group, end: a.hasAttribute('data-end'), badge: a.dataset.badge, parent: a.dataset.parent });
    });
  }

  _start() {
    if (this._started || !this.isConnected) return;
    this._started = true;
    if (!this._dests) this._dests = this._read();
    this._state();
    this._draw();
    this._apply(false);
    this.addEventListener('click', this._onClick = this._onClick || ((e) => this._click(e)));
    this.addEventListener('keydown', this._onNavKey = this._onNavKey || ((e) => this._navKey(e)));
    document.addEventListener('keydown', this._onKey = this._onKey || ((e) => this._hotkey(e)));
    addEventListener('pagehide', this._onHide = this._onHide || (() => this._state().flush()));
    // WHY the §11 splitter on the wide style only: it is a side panel; the two narrow styles are fixed widths on purpose
    // (a 72px Figma rail with a draggable edge would stop being Figma's). The handle is hidden, not removed, in those.
    if (!this.closest('[data-resizable="off"]')) {
      this._resize = makeResizable(this, { edge: 'right', min: num(this.dataset.resizableMin, 200), max: num(this.dataset.resizableMax, 400), keep: 320, key: `app-rail:${this.getAttribute('storage-key') || this.id || 'rail'}`, label: 'the sidebar' });
      this._apply(false);
    }
  }

  _dest(d) {
    const icon = d.icon.trimStart().startsWith('<') ? d.icon : `<span class="dv-rail-glyph">${esc(d.icon)}</span>`;
    const tag = d.href ? 'a' : 'button';
    // data-badge and data-parent (CONTRACT §43): a count at the row's end (Shopify's "Orders
    // 4"), and a sub-destination drawn under its parent, without an icon, while the parent or one of its siblings is
    // current (Shopify's Customers › Segments). The narrow styles show neither: a count there is the badge's title.
    const badge = d.badge ? `<span class="dv-rail-badge" aria-label="${esc(d.badge)}">${esc(d.badge)}</span>` : '';
    const sub = d.parent ? ` data-parent="${esc(d.parent)}"` : '';
    return `<li${d.parent ? ' class="dv-rail-sub"' : ''}${sub}><${tag} class="dv-rail-dest" ${d.href ? `href="${esc(d.href)}"` : 'type="button"'} data-id="${esc(d.id)}" aria-label="${esc(d.label)}${d.badge ? ` (${esc(d.badge)})` : ''}"><span class="dv-rail-icon" data-rail-icon aria-hidden="true">${icon}</span><span class="dv-rail-label" title="${esc(d.label)}">${labelHtml(d.label)}</span>${badge}</${tag}></li>`;
  }

  _draw() {
    const brand = this.getAttribute('brand') || '';
    const mark = this._brandIcon || (brand ? `<span class="dv-rail-glyph">${esc(brand.charAt(0).toUpperCase())}</span>` : '');
    const main = this._dests.filter((d) => !d.end), end = this._dests.filter((d) => d.end);
    // consecutive destinations with the same group share a group; a label heads it in the wide style, a hairline sets it apart in the narrow two
    const groups = [];
    for (const d of main) {
      const last = groups[groups.length - 1];
      if (last && last.name === d.group) last.items.push(d); else groups.push({ name: d.group, items: [d] });
    }
    const search = this.hasAttribute('search')
      ? `<div class="dv-rail-search-wrap">${ICON_SEARCH}<input class="dv-rail-search" type="text" readonly role="button" aria-haspopup="dialog" placeholder="${esc(this.getAttribute('search') || 'Search')}" aria-label="${esc(this.getAttribute('search') || 'Search')}">${this.getAttribute('search-keys') ? `<kbd class="dv-rail-search-keys">${esc(this.getAttribute('search-keys'))}</kbd>` : ''}</div>`
      : '';
    this.innerHTML = `<div class="dv-rail-head">${mark || brand ? `<div class="dv-rail-brand"${brand ? ` title="${esc(brand)}"` : ''}><span class="dv-rail-brand-mark" aria-hidden="true">${mark}</span>${brand ? `<span class="dv-rail-brand-name">${esc(brand)}</span>` : ''}</div>` : ''}<button type="button" class="dv-rail-collapse" aria-label="Collapse sidebar" title="Collapse sidebar">${ICON_CLOSE}</button></div>${search}`
      + `<nav class="dv-rail-nav" aria-label="${esc(this.getAttribute('label') || brand || 'Main')}"><div class="dv-rail-scroll">`
      + groups.map((g) => `<div class="dv-rail-group"${g.name ? ` role="group" aria-label="${esc(g.name)}"` : ''}>${g.name ? `<div class="dv-rail-group-label" aria-hidden="true">${esc(g.name)}</div>` : ''}<ul>${g.items.map((d) => this._dest(d)).join('')}</ul></div>`).join('')
      + `</div><div class="dv-rail-foot">${end.length ? `<ul class="dv-rail-end">${end.map((d) => this._dest(d)).join('')}</ul>` : ''}<button type="button" class="dv-rail-toggle" aria-label="Expand sidebar" title="Expand sidebar">${ICON_OPEN}</button></div></nav>`;
    this._markCurrent();
    this._apply(false);
  }

  _markCurrent() {
    const current = this.current;
    for (const a of this.querySelectorAll('.dv-rail-dest')) {
      if (current && a.dataset.id === current) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    }
    // the section that is open: the current destination's parent, or the current destination when it has children
    const dests = this._dests || [];
    const cur = dests.find((d) => d.id === current);
    const section = cur ? cur.parent || (dests.some((d) => d.parent === cur.id) ? cur.id : '') : '';
    for (const li of this.querySelectorAll('li.dv-rail-sub')) li.hidden = li.dataset.parent !== section;
    for (const a of this.querySelectorAll('.dv-rail-dest')) a.classList.toggle('dv-rail-section', !!section && a.dataset.id === section);
  }

  /** Make the DOM say what the state says: the attribute (CSS keys on it, never on a data-state), the tooltips only the
      icon rail needs, the toggle's words, the splitter's presence. */
  _apply(announce, previous) {
    const { mode, lastOpen } = this._state();
    const active = document.activeElement;
    const hadButton = active && this.contains(active) && active.matches('.dv-rail-collapse, .dv-rail-toggle');
    this._reflecting = true;
    if (this.getAttribute('mode') !== mode) this.setAttribute('mode', mode);
    this._reflecting = false;
    for (const a of this.querySelectorAll('.dv-rail-dest')) {
      // WHY the title on the link only while collapsed: with no label drawn the tooltip is the only name a mouse gets
      if (mode === 'collapsed') a.setAttribute('title', a.getAttribute('aria-label')); else a.removeAttribute('title');
    }
    const toggle = this.querySelector('.dv-rail-toggle');
    if (toggle) {
      const words = mode === 'collapsed' ? 'Expand sidebar' : 'Collapse sidebar';
      toggle.setAttribute('aria-label', words);
      toggle.setAttribute('title', words);
      toggle.innerHTML = mode === 'collapsed' ? ICON_OPEN : ICON_CLOSE;
    }
    if (this._resize) this._resize.handle.toggleAttribute('data-rail-fixed', mode !== 'wide');
    // WHY: the button that was just pressed hides with the style change; focus would fall to the page
    if (hadButton) (mode === 'wide' ? this.querySelector('.dv-rail-collapse') : toggle)?.focus();
    if (announce) this.dispatchEvent(new CustomEvent('data-rail-mode-change', { detail: { mode, previous, lastOpen }, bubbles: true, composed: true }));
  }

  _change(value) {
    const state = this._state();
    const previous = state.mode;
    const changed = state.setMode(value);
    if (this._started) this._apply(changed, previous);
    return changed;
  }

  _click(e) {
    const dest = e.target.closest('.dv-rail-dest');
    if (dest) {
      // a new-tab click is the browser's: no event, nothing marked
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const detail = { id: dest.dataset.id, href: dest.getAttribute('href') || '', label: dest.getAttribute('aria-label'), event: e };
      const go = this.dispatchEvent(new CustomEvent('data-rail-navigate', { detail, bubbles: true, composed: true, cancelable: true }));
      if (!go) e.preventDefault();
      this.current = detail.id;
      return;
    }
    if (e.target.closest('.dv-rail-collapse, .dv-rail-toggle')) { this.toggle(); return; }
    if (e.target.closest('.dv-rail-search')) this._search('click');
  }

  _search(via) { this.dispatchEvent(new CustomEvent('data-rail-search', { detail: { via }, bubbles: true, composed: true })); }

  _navKey(e) {
    // WHY Enter and Space, never focus: opening on focus would trap Tab inside a dialog that hands focus back to the field
    if (e.target.matches('.dv-rail-search')) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this._search('key'); }
      return;
    }
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || !['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
    const all = [...this.querySelectorAll('.dv-rail-dest')].filter((x) => !x.closest('li[hidden]'));
    const at = all.indexOf(e.target.closest('.dv-rail-dest'));
    if (at < 0) return;
    e.preventDefault();
    const to = e.key === 'Home' ? 0 : e.key === 'End' ? all.length - 1 : Math.max(0, Math.min(all.length - 1, at + (e.key === 'ArrowDown' ? 1 : -1)));
    all[to].focus();
  }

  _hotkey(e) {
    const spec = this.getAttribute('hotkey') ?? 'mod+alt+r';
    if (spec === 'off' || e.defaultPrevented || !matchesHotkey(e, spec)) return;
    e.preventDefault();
    this.toggle();
  }
}

if (!customElements.get('data-rail')) customElements.define('data-rail', DataRail);

/** A settings <select> for a rail: fills an empty one with RAIL_MODE_OPTIONS, shows the rail's style, sets it on change
    (an unknown value is collapsed) and follows the rail when something else changes it. `rail` defaults to the element
    named by the select's data-rail. Returns a function that unbinds. */
export function bindRailSelect(select, rail) {
  let off = () => {};
  const target = rail || document.getElementById(select.dataset.rail || '');
  if (!target) return off;
  if (!select.options.length) for (const o of RAIL_MODE_OPTIONS) select.append(new Option(o.label, o.value));
  const sync = () => { select.value = isRailMode(target.mode) ? target.mode : 'collapsed'; };
  const change = () => { target.mode = select.value; sync(); };
  const bind = () => {
    select.addEventListener('change', change);
    target.addEventListener('data-rail-mode-change', sync);
    off = () => { select.removeEventListener('change', change); target.removeEventListener('data-rail-mode-change', sync); };
    sync();
  };
  // an element not upgraded yet has no mode to show
  if ('mode' in target) bind(); else customElements.whenDefined('data-rail').then(bind);
  return () => off();
}
