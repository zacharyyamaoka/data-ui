/* search="expand": Shopify admin's "Search and filter" (docs/CONTRACT.md §43; not landed).

   At rest the query box is a quiet line, "Search and filter", beside the view chip. A click (or "/") opens it: the box
   gets its border and reads "Searching all <noun>", a Cancel button takes Display's place at the right, and a row of
   filter chips opens under the bar, one "+ <facet>" per facet of the file (its `facets:`): Polaris' IndexFilters, the
   bar Zach's Tycoon S6 shell copies (screenshots 1 and 2, 2026-10-28). A chip opens that property's values with their
   counts; a tick writes the one all-views filter (el.filters), so the rail, the pills, the URL and the query box read
   the same state. A set chip reads "Organization: A, B" with its ✕. Cancel clears the words and the facet filters and
   closes the mode; it stays open while words or facet filters remain.

   Light DOM classes: .dv-search-expand and .dv-search-active on .dv-bar, .dv-qcancel, .dv-fchips, .dv-fchip, .dv-fchip-x,
   .dv-fchip-menu. Colours only from tokens. */

import { esc, isEmpty } from '../format.js';
import { cellValue } from '../grammar.js';
import { toRail, fromRail, facetSpecs, railConfig, facetCounts } from '../facets.js';
import { valueLabel } from './query.js';
import { icon } from './icons.js';

// the facet kinds a chip can pick values for: the categorical ones (a range or a date keeps the Filter menu)
const PICKABLE = new Set(['values', 'select', 'chips', 'swatch', 'listbox', 'gallery', 'picture-list', 'grid']);

const on = (el) => el.getAttribute('search') === 'expand';

/** The noun "Searching all …" names: the `search-noun` attribute, else the data's title, else "rows". */
export function searchNoun(el) {
  const n = el.getAttribute('search-noun') || (el.data && el.data.title) || 'rows';
  return String(n).toLowerCase();
}

export function mountExpand(el) {
  const bar = el.$('.dv-bar');
  const slot = el.$('.dv-bar-query');
  const sub = el.$('.dv-subbar');
  if (!bar || !slot || !sub) return null;
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'dv-qcancel';
  cancel.textContent = 'Cancel';
  cancel.hidden = true;
  slot.after(cancel);
  const chips = document.createElement('div');
  chips.className = 'dv-fchips';
  chips.setAttribute('role', 'group');
  chips.setAttribute('aria-label', 'Filters');
  chips.hidden = true;
  sub.prepend(chips);
  let open = false, menuFor = null, key = null;

  const input = () => slot.querySelector('.dv-qinput');
  const specs = () => (el._model && el.base ? facetSpecs(el.base, el.view, el._model.columns).filter((s) => s.property && PICKABLE.has(s.as)) : []);
  const rail = () => toRail(el.filters, railConfig(facetSpecs(el.base, el.view, el._model.columns)));
  const set = () => { const r = rail(); return specs().some((s) => r.facets[s.property] && r.facets[s.property].values && r.facets[s.property].values.length); };

  function activate(yes) {
    open = !!yes;
    bar.classList.toggle('dv-search-active', open);
    cancel.hidden = !open;
    chips.hidden = !open || !specs().length;
    const box = input();
    if (box) box.placeholder = open ? `Searching all ${searchNoun(el)}` : 'Search and filter';
    if (!open) closeMenu();
    draw();
  }

  function draw() {
    if (!open || !el._model) return;
    const r = rail();
    const cols = el._model.columns;
    const list = specs();
    const k = JSON.stringify([list.map((s) => s.property), list.map((s) => r.facets[s.property] && r.facets[s.property].values)]);
    if (k === key) return;
    key = k;
    chips.innerHTML = list.map((s) => {
      const vals = (r.facets[s.property] && r.facets[s.property].values) || [];
      const name = s.label || (cols[s.property] ? cols[s.property].label : s.property);
      return vals.length
        ? `<span class="dv-fchip dv-fchip-on"><button type="button" class="dv-fchip-body" data-p="${esc(s.property)}" aria-haspopup="dialog" aria-expanded="false">${esc(name)}: ${esc(vals.map((v) => valueLabel(cols, s.property, v)).join(', '))}</button><button type="button" class="dv-fchip-x" data-x="${esc(s.property)}" aria-label="Remove the filter on ${esc(name)}">${icon('x')}</button></span>`
        : `<span class="dv-fchip"><button type="button" class="dv-fchip-body" data-p="${esc(s.property)}" aria-haspopup="dialog" aria-expanded="false">${icon('plus')}<span>${esc(name)}</span></button></span>`;
    }).join('');
  }

  function closeMenu() {
    const m = sub.querySelector('.dv-fchip-menu');
    if (m) m.remove();
    for (const b of chips.querySelectorAll('[aria-expanded="true"]')) b.setAttribute('aria-expanded', 'false');
    menuFor = null;
  }

  /** The values of one facet with their counts under the other filters (the rail's disjunctive counts). */
  function openMenu(button, p) {
    closeMenu();
    menuFor = p;
    button.setAttribute('aria-expanded', 'true');
    const r = rail();
    const others = { ...r.facets };
    delete others[p];
    const rows = (el.data && el.data.rows) || [];
    const counts = facetCounts(rows, others, { [p]: 'values' })[p] || {};
    // the stored value behind each counted text, so a number or a list item is written back as it is stored
    const raw = new Map();
    for (const row of rows) { const c = cellValue(row[p]); for (const v of Array.isArray(c) ? c : [c]) if (!isEmpty(v)) raw.set(String(v), v); }
    const picked = new Set(((r.facets[p] && r.facets[p].values) || []).map(String));
    const cols = el._model.columns;
    const menu = document.createElement('div');
    menu.className = 'dv-fchip-menu';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('aria-label', cols[p] ? cols[p].label : p);
    menu.innerHTML = Object.keys(counts).length
      ? `<ul>${Object.entries(counts).map(([v, n]) => `<li><label><input type="checkbox" value="${esc(v)}"${picked.has(v) ? ' checked' : ''}><span class="dv-fchip-v">${esc(valueLabel(cols, p, raw.has(v) ? raw.get(v) : v))}</span><span class="dv-fchip-n">${n}</span></label></li>`).join('')}</ul>`
      : '<p class="dv-fchip-empty">No values</p>';
    const at = button.getBoundingClientRect(), box = sub.getBoundingClientRect();
    menu.style.left = `${Math.max(0, at.left - box.left)}px`;
    sub.append(menu);
    menu.addEventListener('change', (e) => {
      const t = e.target;
      if (!t.matches('input[type=checkbox]')) return;
      const now = toRail(el.filters, railConfig(facetSpecs(el.base, el.view, el._model.columns)));
      const f = now.facets[p] || (now.facets[p] = {});
      const vals = new Set((f.values || []).map(String));
      if (t.checked) vals.add(t.value); else vals.delete(t.value);
      f.values = [...vals].map((v) => (raw.has(v) ? raw.get(v) : v));
      if (rows.some((row) => Array.isArray(cellValue(row[p])))) f.match = 'contains'; // a list property: "tags contains x"
      if (!f.values.length) delete now.facets[p];
      el.filters = fromRail(now.facets, now.rest);
    });
    const first = menu.querySelector('input');
    if (first) first.focus();
  }

  const onFocus = () => { if (on(el) && !open) activate(true); };
  const onDown = (e) => {
    if (!open) return;
    if (menuFor && !e.target.closest('.dv-fchip-menu, .dv-fchip')) closeMenu();
    // a click outside the bar and its filter row closes an empty search, as Polaris' does
    if (!bar.contains(e.target) && !sub.contains(e.target) && !hasWords() && !set()) activate(false);
  };
  const hasWords = () => !!(el.query || (input() && input().value.trim()));
  const onCancel = () => {
    const r = rail();
    for (const s of specs()) delete r.facets[s.property];
    el.search('');
    const box = input();
    if (box) box.value = '';
    el.filters = fromRail(r.facets, r.rest);
    activate(false);
    if (box) box.blur();
  };
  const onChips = (e) => {
    const x = e.target.closest('[data-x]');
    if (x) {
      const r = rail();
      delete r.facets[x.dataset.x];
      el.filters = fromRail(r.facets, r.rest);
      return;
    }
    const b = e.target.closest('[data-p]');
    if (!b) return;
    if (menuFor === b.dataset.p) closeMenu(); else openMenu(b, b.dataset.p);
  };
  const onKey = (e) => { if (e.key === 'Escape' && menuFor) { e.stopPropagation(); const p = menuFor; closeMenu(); const b = chips.querySelector(`[data-p="${CSS.escape(p)}"]`); if (b) b.focus(); } };
  slot.addEventListener('focusin', onFocus);
  cancel.addEventListener('click', onCancel);
  chips.addEventListener('click', onChips);
  sub.addEventListener('keydown', onKey, true);
  document.addEventListener('pointerdown', onDown, true);

  return {
    /** After every render: the mode follows the attribute (read live), the chips follow the filter. */
    update() {
      const want = on(el);
      bar.classList.toggle('dv-search-expand', want);
      if (!want) { if (open) activate(false); cancel.hidden = true; chips.hidden = true; return; }
      if (!open && (hasWords() || set())) { activate(true); return; }
      const box = input();
      if (box) box.placeholder = open ? `Searching all ${searchNoun(el)}` : 'Search and filter';
      key = null;
      draw();
    },
    get open() { return open; },
    destroy() {
      document.removeEventListener('pointerdown', onDown, true);
      slot.removeEventListener('focusin', onFocus);
      bar.classList.remove('dv-search-expand', 'dv-search-active');
      cancel.remove();
      chips.remove();
      closeMenu();
    },
  };
}
