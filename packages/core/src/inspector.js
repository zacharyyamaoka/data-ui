/* The inspector's property list (docs/CONTRACT.md §44, docs/peps/0019-inspector.md): one record's properties, one a row, the side
   peek and the record view alike.

   Zach, 2026-10-31: "I don't like how when I look at the inspector menu its not a 1:1 coorespondance with the fields I am seeing";
   "Desired is notions: pattern where you have 1 property per cell"; "And then you have control over what property visibilty in the
   inspector or in the row". Hence: the visible columns, in their order, under the labels they have in the table (the title is
   the heading, so not a row); then the rest behind "N more properties". `record.visibility` sets the inspector apart from the row.
   STOCK PARTS: none; Notion's model, in the kit's own popover. */

import { cellValue } from './grammar.js';
import { esc, isEmpty } from './format.js';
import { hasContent } from './sections.js';
import { openColumnAdd } from './toolbar/column-menu.js';

export const VISIBILITY = ['show', 'hideEmpty', 'hide'];

const VISIBILITY_WORDS = { show: 'Always show', hideEmpty: 'Hide when empty', hide: 'Always hide' };

/** The view's word for a property, or null (none, or not one of the three): the property then follows its column. */
export function visibilityOf(view, id) {
  const map = view && view.record && view.record.visibility;
  const word = map && typeof map === 'object' ? map[id] : null;
  return VISIBILITY.includes(word) ? word : null;
}

/** The properties a view draws as columns, as ids, when the view plugin does not say: its `order`, else every property the
    data does not hide. WHY the plugin's word wins (`drawn`): a table adds columns of its own and takes some out, and the inspector
    has to be what the reader is looking at. */
export function columnIds(view, columns) {
  const order = view && Array.isArray(view.order) ? view.order.filter((id) => columns[id]) : [];
  if (order.length) return order;
  const units = new Set(Object.values(columns).map((p) => p.unit).filter(Boolean));
  return Object.keys(columns).filter((id) => !columns[id].hidden && !columns[id].pivot && !units.has(id));
}

/** {shown: [id], more: [id]}: the rows, and what waits behind "N more properties".
    `drawn`: the columns as the view plugin draws them, [{id, …}], or null. `listed`: the ids record.sections lays out, which stand for
    the columns when the view has sections. `exclude`: what is drawn elsewhere (dataset.detail's list). A property `hidden: true` is
    not offered, as Property visibility does not offer it, and neither is a unit column no view draws: its value is the unit
    beside the number. WHY an empty value keeps its row: 1:1 with the columns, whose cell is a dash too; a view says hideEmpty to drop it. */
export function inspectorProperties({ view, columns, titleProperty, row = null, drawn = null, listed = null, exclude = [] }) {
  const first = listed || (drawn ? drawn.map((c) => c.id) : columnIds(view, columns));
  const units = new Set(Object.values(columns).map((p) => p.unit).filter(Boolean));
  // `offered`: a source's column (CONTRACT §36), which no view shows unless it names it, and every reader may reach
  const rest = Object.keys(columns).filter((id) => (!columns[id].hidden || columns[id].offered) && !columns[id].pivot && !units.has(id));
  const out = { shown: [], more: [] };
  for (const id of new Set([...first, ...rest])) {
    if (id === titleProperty || exclude.includes(id)) continue;
    const word = visibilityOf(view, id);
    const on = word === 'show' || (word === 'hideEmpty' ? hasContent(row ? row[id] : null) : word === null && first.includes(id));
    (on ? out.shown : out.more).push(id);
  }
  return out;
}

/** Notion's words: "1 more property", and once open, "Hide 1 property". */
export function moreLabel(n, open = false) {
  const noun = n === 1 ? 'property' : 'properties';
  return open ? `Hide ${n} ${noun}` : `${n} more ${noun}`;
}

const CHEVRON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg>';
const EYE = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="1.8"/></svg>';

/** The rows behind "N more properties", then the button under them. WHY in the DOM, hidden: it opens in place, with nothing redrawn,
    and a hidden row's value is still there for a script or a find. '' with nothing to hide. */
export function moreHtml(rows, count, open) {
  if (!count) return '';
  return `<table class="dv-fields dv-prop-rest"${open ? '' : ' hidden'}><tbody>${rows}</tbody></table>
    <button type="button" class="dv-prop-more" data-prop-more data-n="${count}" aria-expanded="${open}">${CHEVRON}<span>${esc(moreLabel(count, open))}</span></button>`;
}

/** Whether this element's reader can change a view: an embedded element with no toolbar has nowhere to keep it. */
export function canSetVisibility(el) {
  return el.getAttribute('toolbar') !== 'none' && el.getAttribute('controls') !== 'off';
}

/** A row's visibility button, in its label cell; '' where the reader cannot change the view. */
export function visibilityButton(el, id, label) {
  if (!canSetVisibility(el)) return '';
  return `<button type="button" class="dv-prop-vis" data-prop-vis="${esc(id)}" aria-haspopup="dialog" aria-label="Where ${esc(label)} shows" title="Where this property shows">${EYE}</button>`;
}

/** "Add a property", only where the page can take one (Zach's brief: the host has acceptProperty) and the page is not in View. */
export function addPropertyHtml(el) {
  if (typeof el.acceptProperty !== 'function' || el._viewOnly()) return '';
  return '<button type="button" class="dv-prop-add" data-prop-add><span aria-hidden="true">+</span> Add a property</button>';
}

/** A view's record.visibility with one word set. */
const withWord = (view, id, word) => ({ ...(view.record || {}), visibility: { ...((view.record || {}).visibility || {}), [id]: word } });

/** The word in force: the view's, else what its column gives. */
export const wordOf = (view, id, isColumn) => visibilityOf(view, id) || (isColumn ? 'show' : 'hide');

export function setVisibility(el, id, word) {
  el.update((x) => { x.record = withWord(x, id, word); });
}

const drawnIds = (el) => {
  const plugin = el._plugin && el._plugin.drawnColumns ? el._plugin.drawnColumns() : null;
  return plugin ? plugin.map((c) => c.id) : columnIds(el.view, el._model.columns);
};

/** The menu of a property: where it shows in the inspector, and whether it is a column in the row. Notion's "Property visibility",
    with the row beside it, because they are one decision made twice (Zach's third picture: Text out of the table, Files out of the page). */
function openVisibility(el, id, anchor) {
  const p = el._model.columns[id];
  const ids = drawnIds(el);
  const isColumn = ids.includes(id);
  const word = wordOf(el.view, id, isColumn);
  const radio = (w) => `<button type="button" class="dv-vis-item" role="menuitemradio" aria-checked="${w === word}" data-vis="${w}">${esc(VISIBILITY_WORDS[w])}</button>`;
  // a column the view adds itself has no place in `order` to take away: its own switch is the view's
  const row = p ? `<h5>In the row</h5><button type="button" class="dv-vis-item" role="menuitemcheckbox" aria-checked="${isColumn}" data-vis-row>Show as a column</button>` : '';
  const html = `<div class="dv-vis" role="menu" aria-label="Where this property shows"><h5>In the inspector</h5>${VISIBILITY.map(radio).join('')}${row}</div>`;
  el.closeMenu();
  el._pop(anchor, html, (node) => {
    for (const b of node.querySelectorAll('[data-vis]')) b.addEventListener('click', () => { el.closeMenu(); setVisibility(el, id, b.dataset.vis); });
    const toggle = node.querySelector('[data-vis-row]');
    if (toggle) toggle.addEventListener('click', () => {
      el.closeMenu();
      const order = [...drawnIds(el)].filter((x) => el._model.columns[x]);
      el.update((x) => { x.order = isColumn ? order.filter((c) => c !== id) : [...order, id]; });
    });
  }, 'dv-colmenu');
}

/** The inspector's controls, delegated from the element, so the peek and the record view share them and a redraw keeps them. */
export function wireInspector(el) {
  el.addEventListener('click', (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    const more = t.closest('[data-prop-more]');
    if (more) {
      const open = more.getAttribute('aria-expanded') !== 'true';
      // WHY kept on the element: stepping to the next record keeps what the reader opened
      el._propMore = open;
      more.setAttribute('aria-expanded', String(open));
      more.querySelector('span').textContent = moreLabel(Number(more.dataset.n), open);
      more.previousElementSibling.hidden = !open;
      return;
    }
    const vis = t.closest('[data-prop-vis]');
    if (vis) { e.stopPropagation(); openVisibility(el, vis.dataset.propVis, vis); return; }
    const add = t.closest('[data-prop-add]');
    if (add) { e.stopPropagation(); openColumnAdd(el, add); }
  });
}

/** What the open inspector depends on besides its record; when it changes the open record is drawn again. */
export function inspectorKey(el) {
  const v = el.view || {};
  return JSON.stringify([v.order, v.record && v.record.visibility, el._plugin && el._plugin.drawnColumns ? (el._plugin.drawnColumns() || []).map((c) => [c.id, c.label]) : null]);
}
