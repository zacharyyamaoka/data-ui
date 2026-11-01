/* Row selection and the bulk action bar (docs/CONTRACT.md §15). OWNED BY LANE B (query + selection). Frozen seam:

   new Selection(el)                    one per <data-views>; el is the element
     .ids                               a Set of selected row ids (strings)
     .click(id, {shift, toggle}, order) a click in a view: plain = replace with [id]; toggle (ctrl/cmd) = add/remove id;
                                        shift = the range from the anchor to id in `order` (the drawn ids); shift+toggle
                                        = add that range. Returns true if the set changed.
     .set(ids, mode)                    mode 'replace' | 'add' | 'toggle' | 'remove'
     .clear(), .retain(idSet)           retain: drop ids no longer among the filtered rows
   DEFAULT_ACTIONS                      [{id, label, icon?, min?, max?, run(rows, el)}]: compare, copy-ids, export-csv, clear
   resolveActions(list, count?)         el.actions as given (strings name a default) -> action objects; with `count` each
                                        carries disabled and the reason (outside its min / max)
   runAction(el, action)                dispatches the cancelable data-views-action {id, ids, rows}, then runs it
   mountBulk(el, slot)                  -> {update(), destroy()}: draws the bulk bar into `slot` (shown by the element
                                        only while el.selection.length > 0)

   The element calls el._selectionChanged() after any change (it dispatches data-views-select and redraws).
   WHY Shopify's bar (Zach, 2026-10-26): "shift click for ranges, or shift control click to add to the current
   selection, and then you get a toolbar with actions that appears like in Shopify". */

import { toCsv } from './csv.js';
import { esc, slug } from '../format.js';

export class Selection {
  constructor(el) { this.el = el; this.ids = new Set(); this.anchor = null; }
  click(id, { shift = false, toggle = false } = {}, order = []) {
    id = String(id);
    const before = [...this.ids].join('\n');
    if (shift && this.anchor !== null && order.includes(this.anchor) && order.includes(id)) {
      const a = order.indexOf(this.anchor), b = order.indexOf(id);
      const range = order.slice(Math.min(a, b), Math.max(a, b) + 1);
      if (!toggle) this.ids = new Set(range); else range.forEach((x) => this.ids.add(x));
    } else if (toggle) { if (this.ids.has(id)) this.ids.delete(id); else this.ids.add(id); this.anchor = id; }
    else { this.ids = new Set([id]); this.anchor = id; }
    return before !== [...this.ids].join('\n');
  }
  set(ids, mode = 'replace') {
    const list = [...(ids || [])].map(String);
    if (mode === 'replace') this.ids = new Set(list);
    else if (mode === 'add') list.forEach((x) => this.ids.add(x));
    else if (mode === 'remove') list.forEach((x) => this.ids.delete(x));
    else if (mode === 'toggle') list.forEach((x) => (this.ids.has(x) ? this.ids.delete(x) : this.ids.add(x)));
    if (list.length) this.anchor = list[list.length - 1];
  }
  clear() { this.ids = new Set(); this.anchor = null; }
  retain(keep) { for (const id of [...this.ids]) if (!keep.has(id)) this.ids.delete(id); }
}

/** The visible properties of the current view, in its order (what export-csv writes). */
function visibleOrder(el) {
  const cols = (el.model && el.model.columns) || {};
  const order = el.view && el.view.order && el.view.order.length ? el.view.order : Object.keys(cols).filter((id) => !cols[id].hidden);
  return order.filter((id) => cols[id] && !cols[id].pivot && !id.startsWith('@'));
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* no clipboard permission: the old way */ }
  const area = document.createElement('textarea');
  area.value = text;
  area.style.cssText = 'position:fixed;opacity:0;left:-9999px';
  document.body.append(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  area.remove();
  return ok;
}

export const DEFAULT_ACTIONS = [
  {
    id: 'compare', label: 'Compare', icon: '⇆', min: 2, max: 6,
    // through el.update, so the view's Reset brings the table back
    run(rows, el) { const ids = rows.map((r) => String(r.id)); el.update((x) => { x.type = 'compare'; x.compare = { ...(x.compare || {}), rows: ids }; }); },
  },
  {
    id: 'copy-ids', label: 'Copy IDs', icon: '⧉', min: 1,
    async run(rows) { const ok = await copyText(rows.map((r) => String(r.id)).join('\n')); return ok ? `Copied ${rows.length} ${rows.length === 1 ? 'id' : 'ids'}` : 'Could not copy'; },
  },
  {
    id: 'export-csv', label: 'Export CSV', icon: '⤓', min: 1,
    run(rows, el) {
      const csv = toCsv(rows, el.model.columns, visibleOrder(el));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      a.download = `${slug((el.view && el.view.name) || 'rows') || 'rows'}.csv`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      return `Exported ${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`;
    },
  },
  { id: 'clear', label: 'Clear selection', icon: '✕', run(rows, el) { el.clearSelection(); } },
];

/** CONTRACT §40: Delete, in the bulk bar of a page in Edit; never a default, so a read-only page has none. */
export const DELETE_ACTION = { id: 'delete', label: 'Delete', icon: '⌫', min: 1, run(rows, el) { el.deleteRows(rows.map((r) => String(r.id))); } };

export function resolveActions(list, count = null) {
  const given = list || DEFAULT_ACTIONS.map((a) => a.id);
  const out = given.map((a) => (typeof a === 'string' ? DEFAULT_ACTIONS.find((d) => d.id === a) : a && typeof a === 'object' ? a : null)).filter(Boolean);
  if (count === null) return out;
  return out.map((a) => {
    const reason = a.min && count < a.min ? `Select at least ${a.min} rows` : a.max && count > a.max ? `Select at most ${a.max} rows` : '';
    return { ...a, disabled: !!reason, reason };
  });
}

/** Run one action on the selection: the page hears data-views-action first and may cancel it. */
export function runAction(el, action) {
  if (!action || action.disabled) return false;
  const ids = el.selection, rows = el.selectedRows;
  const ev = new CustomEvent('data-views-action', { detail: { id: action.id, ids, rows }, cancelable: true });
  if (!el.dispatchEvent(ev)) return false;
  return typeof action.run === 'function' ? action.run(rows, el) ?? true : true;
}

export function mountBulk(el, slot) {
  slot.setAttribute('role', 'toolbar');
  slot.setAttribute('aria-label', 'Selected rows');
  slot.innerHTML = `<div class="dv-bulk-lead">
      <input type="checkbox" class="dv-bulk-all" aria-label="Select all filtered rows">
      <button type="button" class="dv-bulk-count" aria-haspopup="menu" aria-expanded="false"><span class="dv-bulk-n">0</span> selected <span class="dv-bulk-caret" aria-hidden="true">▾</span></button>
      <div class="dv-bulk-menu" role="menu" hidden><button type="button" role="menuitem" data-bulk="all"></button><button type="button" role="menuitem" data-bulk="none">Select none</button></div>
    </div>
    <div class="dv-bulk-actions"></div>
    <div class="dv-bulk-morewrap" hidden><button type="button" class="dv-bulk-more" aria-label="More actions" aria-haspopup="menu" aria-expanded="false">⋯</button><div class="dv-bulk-menu dv-bulk-overflow" role="menu" hidden></div></div>
    <span class="dv-bulk-msg" role="status" aria-live="polite"></span>
    <button type="button" class="dv-bulk-only" role="switch" aria-checked="false"><span class="dv-switch" aria-hidden="true"></span>Show only selected</button>`;
  const $ = (s) => slot.querySelector(s);
  const all = $('.dv-bulk-all'), count = $('.dv-bulk-count'), menu = $('.dv-bulk-menu'), acts = $('.dv-bulk-actions'), morewrap = $('.dv-bulk-morewrap'),
    more = $('.dv-bulk-more'), overflow = $('.dv-bulk-overflow'), msg = $('.dv-bulk-msg'), only = $('.dv-bulk-only');
  let actions = [], key = null, msgTimer = 0;

  const pill = (a, i, item = false) => `<button type="button" class="${item ? '' : 'dv-bulk-act'}"${item ? ' role="menuitem"' : ''} data-act="${i}"${a.disabled ? ` disabled title="${esc(a.reason)}"` : ''}>${a.icon ? `<span class="dv-bulk-icon" aria-hidden="true">${esc(a.icon)}</span>` : ''}${esc(a.label)}</button>`;

  /** Pills that do not fit move into the ⋯ menu (Shopify). */
  function fit() {
    const pills = [...acts.children];
    pills.forEach((p) => { p.hidden = false; });
    morewrap.hidden = true;
    if (acts.scrollWidth <= acts.clientWidth + 1) { overflow.innerHTML = ''; return; }
    morewrap.hidden = false;
    const hidden = [];
    for (let k = pills.length - 1; k >= 0 && acts.scrollWidth > acts.clientWidth + 1; k--) { pills[k].hidden = true; hidden.unshift(Number(pills[k].dataset.act)); }
    overflow.innerHTML = hidden.map((i) => pill(actions[i], i, true)).join('');
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => { if (!slot.hidden) fit(); }) : null;
  if (ro) ro.observe(slot);

  const closeMenus = () => { for (const [m, b] of [[menu, count], [overflow, more]]) { m.hidden = true; b.setAttribute('aria-expanded', 'false'); } };
  const toggleMenu = (m, b) => { const show = m.hidden; closeMenus(); m.hidden = !show; b.setAttribute('aria-expanded', String(show)); if (show) { const first = m.querySelector('button:not([disabled])'); if (first) first.focus(); } };
  const onDoc = (e) => { if (!slot.contains(e.target)) closeMenus(); };
  document.addEventListener('click', onDoc);

  function say(text) {
    msg.textContent = text || '';
    clearTimeout(msgTimer);
    if (text) msgTimer = setTimeout(() => { msg.textContent = ''; }, 2500);
  }

  slot.addEventListener('click', async (e) => {
    const t = e.target;
    if (t === all) { if (el.selection.length && el.model && el.model.rows.every((r) => el._selection.ids.has(String(r.id)))) el.clearSelection(); else el.selectAll(); return; }
    if (t.closest('.dv-bulk-count')) { toggleMenu(menu, count); return; }
    if (t.closest('.dv-bulk-more')) { toggleMenu(overflow, more); return; }
    const b = t.closest('[data-bulk]');
    if (b) { closeMenus(); if (b.dataset.bulk === 'all') el.selectAll(); else el.clearSelection(); return; }
    const act = t.closest('[data-act]');
    if (act && !act.disabled) {
      closeMenus();
      const out = await runAction(el, actions[Number(act.dataset.act)]);
      if (typeof out === 'string') say(out);
      return;
    }
    if (t.closest('.dv-bulk-only')) {
      // lane A narrows the rows to the selection when el._onlySelected is set
      el._onlySelected = !el._onlySelected;
      only.setAttribute('aria-checked', String(!!el._onlySelected));
      el._render();
    }
  });
  slot.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (!menu.hidden || !overflow.hidden)) { e.preventDefault(); e.stopPropagation(); closeMenus(); count.focus(); }
  });

  return {
    update() {
      const n = el.selection.length;
      const rows = el.model ? el.model.rows : [];
      const ids = el._selection ? el._selection.ids : new Set(el.selection);
      const every = n > 0 && rows.length > 0 && rows.every((r) => ids.has(String(r.id)));
      all.checked = every;
      all.indeterminate = n > 0 && !every;
      $('.dv-bulk-n').textContent = n.toLocaleString();
      $('[data-bulk="all"]').textContent = `Select all ${rows.length.toLocaleString()} filtered`;
      if (!n && el._onlySelected) { el._onlySelected = false; queueMicrotask(() => el._render()); }
      only.setAttribute('aria-checked', String(!!el._onlySelected));
      actions = resolveActions(el.actions, n);
      if (el._editTools && el._editTools() && !actions.some((a) => a.id === 'delete')) {
        const [act] = resolveActions([DELETE_ACTION], n);
        const at = actions.findIndex((a) => a.id === 'clear');
        actions.splice(at < 0 ? actions.length : at, 0, act);
      }
      // WHY the reason too: a count can move an action from "at least 2" to "at most 4" while it stays disabled, and the
      // title must say the reason that holds now
      const k = JSON.stringify(actions.map((a) => [a.id, a.label, a.icon, a.disabled, a.reason]));
      if (k !== key) {
        key = k;
        acts.innerHTML = actions.map((a, i) => pill(a, i)).join('');
      }
      if (!slot.hidden) requestAnimationFrame(fit);
    },
    destroy() {
      if (ro) ro.disconnect();
      document.removeEventListener('click', onDoc);
      clearTimeout(msgTimer);
      slot.innerHTML = '';
    },
  };
}
