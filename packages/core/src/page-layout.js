/* The page layout (docs/CONTRACT.md §46): which properties a record's page shows, in what order, and where: in the property list
   (`top`) or as a block under its H1 (`section`). Pure: no DOM. The `.base` file's top-level `page:` key holds it.

   Zach, 2026-10-31: "Important the visibiliy and order of the properties on the page doesn't nessarily need to be the same as on
   the table! (by default can be but then you get full control to customize)". So a property the key does not name follows the
   table: its column order, and shown when the table shows it. The exception is a section, a property the data says is written
   under a heading: it is always shown, because a heading someone typed into a note is words someone means to read.

   The free text (`pageBody: true` on a property) is never in the list: it is always last, as Zach's "page property". */

import { isLong } from './page-section.js';

export const PLACES = ['top', 'section'];
export const isBlock = (place) => place !== 'top';

/** The property holding the page's free text, or null. */
export function freeProperty(props) {
  for (const p of Object.values(props || {})) if (p && p.pageBody) return p.id ?? null;
  return null;
}

/** Whether records draw as laid-out pages: the file has a `page:` key, or the data has a free-text property. */
export function pageOn(base, props) { return !!base && Array.isArray(base.page) || freeProperty(props) !== null; }

/** {entries: [{id, place, visible}], free, unknown}: the layout in force. `order`: the table's columns. `unknown`: entries that name
    no property of this data, kept so that writing the layout back never drops them. */
export function pageLayout(base, props, { order = null, title = null, view = null } = {}) {
  const free = freeProperty(props);
  const skip = (id) => id === title || id === free;
  const entries = [];
  const unknown = [];
  const seen = new Set();
  for (const e of (base && Array.isArray(base.page) ? base.page : [])) {
    if (!e || typeof e !== 'object' || typeof e.property !== 'string' || seen.has(e.property)) continue;
    seen.add(e.property);
    if (!props[e.property]) { unknown.push(e); continue; }
    if (skip(e.property)) continue;
    entries.push({ id: e.property, place: PLACES.includes(e.place) ? e.place : 'top', visible: e.visible !== false });
  }
  const shown = new Set(order || Object.keys(props));
  for (const id of [...(order || []), ...Object.keys(props)]) {
    const p = props[id];
    if (!p || seen.has(id) || skip(id) || p.hidden) continue;
    seen.add(id);
    entries.push({ id, place: p.section || isLong(p, view) ? 'section' : 'top', visible: !!p.section || shown.has(id) });
  }
  return { entries, free, unknown };
}

/** The layout as the `page:` key's value. */
export function layoutValue({ entries, unknown }) {
  const list = entries.map((e) => ({ property: e.id, ...(e.place === 'top' ? {} : { place: e.place }), ...(e.visible ? {} : { visible: false }) }));
  return [...list, ...unknown];
}

const sameGroup = (a, b) => a.visible === b.visible && isBlock(a.place) === isBlock(b.place);

/** The entries with `id` moved `delta` steps among its own kind (blocks among blocks, list rows among list rows). WHY only those: a
    block is one unit, and a row of the list is not a block. Same list when it is already at that end. */
export function stepEntry(entries, id, delta) {
  const e = entries.find((x) => x.id === id);
  if (!e) return entries;
  const group = entries.filter((x) => sameGroup(x, e));
  const at = group.indexOf(e);
  return moveEntry(entries, id, at + delta);
}

/** The entries with `id` placed at position `index` of its own kind. */
export function moveEntry(entries, id, index) {
  const e = entries.find((x) => x.id === id);
  if (!e) return entries;
  const group = entries.filter((x) => sameGroup(x, e));
  const from = group.indexOf(e);
  const to = Math.max(0, Math.min(group.length - 1, index));
  if (from === to) return entries;
  const rest = group.filter((x) => x !== e);
  const out = entries.filter((x) => x !== e);
  const anchor = rest[to];
  out.splice(anchor ? out.indexOf(anchor) : out.indexOf(rest[rest.length - 1]) + 1, 0, e);
  return out;
}

/** The entries with one property's place or visibility changed.  */
export function withPlace(entries, id, place) { return entries.map((e) => (e.id === id ? { ...e, place, visible: true } : e)); }
export function withVisible(entries, id, visible) { return entries.map((e) => (e.id === id ? { ...e, visible } : e)); }
