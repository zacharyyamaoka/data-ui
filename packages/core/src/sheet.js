/* What a table needs to know about its cells to take a block from a spreadsheet (docs/CONTRACT.md §40). Pure, so
   tests/unit/sheet-paste.test.mjs holds it.

   WHY the CSV reader's scanner and no parser of its own: stock part first; Excel, Sheets and Notion all write RFC 4180's quoting on
   the clipboard, and data.js already reads it. Its strict mode is the one difference: a pasted `"hello" world` is words.
   WHY nothing here rewrites a value it cannot read: Zach's truthful-rendering rule. A word in a number column stays that word, drawn
   as written; only a value that plainly is the column's type becomes it. */

import { parseRecords } from './data.js';
import { cellValue } from './grammar.js';
import { isEmpty, withValue } from './format.js';
import { toRail, fromRail, railConfig, ref } from './facets.js';

/** A clipboard's text as rows of cell text. A last line break adds no row (Excel ends with one). */
export function parseBlock(text) {
  return parseRecords(text, { sep: '\t', strict: true }).map((r) => r.cells);
}

/** Whether a paste is a block of cells rather than words. A tab; or several lines with an HTML table beside them, which is how a
    spreadsheet's single column arrives. WHY not any several lines: a paragraph pasted into a notes cell must stay one cell. */
export function isBlock(text, html = '') {
  const t = String(text || '');
  if (!t) return false;
  const block = parseBlock(t);
  if (block.length === 1 && block[0].length === 1) return false;
  return block.length > 1 ? t.includes('\t') || /<table[\s>]/i.test(String(html || '')) : true;
}

const BOOLEAN = { true: true, yes: true, 1: true, '✓': true, false: false, no: false, 0: false };

/** A cell's text as what the property stores. What does not read as the column's type is kept as written. */
function stored(text, p) {
  const s = String(text);
  const t = s.trim();
  if (t === '') return null;
  if (p.type === 'number') return Number.isFinite(Number(t)) ? Number(t) : s;
  if (p.type === 'boolean') return BOOLEAN[t.toLowerCase()] ?? s;
  if (p.type === 'list') return t.split(',').map((x) => x.trim()).filter(Boolean);
  if (p.labels) { const key = Object.keys(p.labels).find((k) => String(p.labels[k]) === t); if (key !== undefined) return key; }
  return s;
}

/** The new cell for a pasted text: its value, and a rich cell's other keys kept, as the form does (form.js). */
export function coerceCell(text, p, cell) {
  const value = stored(text, p);
  if (cell === null || typeof cell !== 'object' || Array.isArray(cell) || !('value' in cell)) return value;
  return withValue(cell, value);
}

const same = (a, b) => JSON.stringify(cellValue(a) ?? null) === JSON.stringify(cellValue(b) ?? null);

/** Where a block lands, cell by cell, by position. `rows`: the drawn records in order; `leaves`: the drawn columns; `at`: {row, leaf}
    indexes of the anchor; `can(row, leaf)`: that cell takes an edit; `takes(leaf)`: a new row takes that column; `canAdd`: the block may
    grow the table. Returns {edits: [{id, set}], adds: [{set, at: 'end'}], filled, locked, pastColumn, pastRow}. WHY by position: a
    locked column consumes its value, as Notion's do; shifting the rest left would put them under the wrong headings. */
export function planPaste({ block, rows, leaves, at, can, takes, canAdd }) {
  const out = { edits: [], adds: [], filled: 0, locked: 0, pastColumn: 0, pastRow: 0 };
  block.forEach((line, r) => {
    const row = rows[at.row + r];
    const set = {};
    let changed = false;
    line.forEach((text, c) => {
      const leaf = leaves[at.leaf + c];
      if (!leaf) { out.pastColumn++; return; }
      if (!row && !canAdd) { out.pastRow++; return; }
      if (row ? !can(row, leaf) : !takes(leaf)) { out.locked++; return; }
      const next = coerceCell(text, leaf.p, row ? row[leaf.id] : undefined);
      if (!row && isEmpty(next)) return; // a new row has nothing there to clear
      out.filled++;
      if (row && same(row[leaf.id], next)) return;
      set[leaf.id] = next;
      changed = true;
    });
    if (!changed) return;
    if (row) out.edits.push({ id: row.id, set });
    else out.adds.push({ set, at: 'end' });
  });
  return out;
}

// ------------------------------------------------------------------ a column's kind
/** What the header menu offers (CONTRACT §40). WHY a word above the data's `type`: "checkbox" and "select" are what a reader picks;
    each is a definition the kit already draws, so no view learns anything new but the checkbox's box. */
export const KINDS = ['text', 'number', 'date', 'select', 'checkbox', 'link', 'media'];
export const KIND_LABEL = { text: 'Text', number: 'Number', date: 'Date', select: 'Select', checkbox: 'Checkbox', link: 'Link', media: 'Media' };
const DEFINITION = { text: { type: 'text' }, number: { type: 'number' }, date: { type: 'date' }, select: { type: 'text', display: 'badge' },
  checkbox: { type: 'boolean', display: 'checkbox' }, link: { type: 'text', display: 'link' }, media: { type: 'text', display: 'media' } };

/** A property as the menu names it; a type the menu has no word for reads as itself. */
export function kindOf(p) {
  if (p.type === 'number') return 'number';
  if (p.type === 'date') return 'date';
  if (p.type === 'boolean') return 'checkbox';
  if (p.type && p.type !== 'text') return p.type;
  if (p.display === 'link') return 'link';
  if (p.display === 'media') return 'media';
  return p.display === 'badge' || p.labels || (p.constraints && p.constraints.enum) ? 'select' : 'text';
}

/** The definition of a kind: a new property's, or `old` retyped. A retype changes the definition and nothing stored. It keeps what is the
    column's own (its label, a note, a number's range) and lets go of what belonged to the old kind. WHY asWritten: a number under a text
    heading must draw as stored, not as the thousands-grouped number the table writes for a number column. */
export function definitionFor(kind, old = null) {
  if (!DEFINITION[kind]) throw new Error(`no such kind: ${kind}`);
  if (!old) return { ...DEFINITION[kind] };
  if (kindOf(old) === kind) return JSON.parse(JSON.stringify(old));
  const { type, display, labels, colors, cycle, constraints, asWritten, ...rest } = old;
  const next = { ...rest, ...DEFINITION[kind] };
  const { enum: choices, ...range } = constraints || {};
  if (Object.keys(range).length) next.constraints = range;
  if (kind !== 'number') next.asWritten = true;
  return next;
}

/** A stored key from a display name: lower case with underscores, unique among `taken`, and never the row's `id`. */
export function propertyKey(name, taken) {
  const used = new Set([...taken, 'id']);
  const words = String(name).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'property';
  const stem = /^[0-9]/.test(words) ? `p_${words}` : words;
  let key = stem;
  for (let n = 2; used.has(key); n++) key = `${stem}_${n}`;
  return key;
}

/** Whether a stored value can sit in its column's own control. WHY it matters: <input type=number> reads "soon" as empty, so a
    cell opened and left would be erased; such a cell opens in a text box, as written. */
export function fits(p, v) {
  if (isEmpty(v)) return true;
  if (p.type === 'number') return typeof v === 'number';
  if (p.type === 'date') return /^\d{4}-\d{2}-\d{2}$/.test(String(v));
  if (p.type === 'boolean') return typeof v === 'boolean';
  return true;
}

const MAPS = ['columnSize', 'display', 'summaries'];
const LEVELS = ['groupBy', 'subGroupBy'];

/** Take a property out of every key of a view that names it, in place; what was there, for restoreToView. */
export function dropFromView(view, id) {
  const saved = {};
  if (Array.isArray(view.order) && view.order.includes(id)) { saved.order = view.order.indexOf(id); view.order = view.order.filter((x) => x !== id); }
  if (Array.isArray(view.sort) && view.sort.some((s) => s.property === id)) {
    saved.sort = view.sort.map((s, i) => [i, s]).filter(([, s]) => s.property === id);
    view.sort = view.sort.filter((s) => s.property !== id);
  }
  for (const k of LEVELS) if (view[k] && view[k].property === id) { saved[k] = view[k]; delete view[k]; }
  for (const k of MAPS) {
    if (!view[k] || !(id in view[k])) continue;
    (saved.maps ||= {})[k] = view[k][id];
    delete view[k][id];
    if (!Object.keys(view[k]).length) delete view[k];
  }
  return saved;
}

/** Put back what dropFromView took; a place past the end of a list changed since is its end. */
export function restoreToView(view, id, saved) {
  if (saved.order !== undefined && Array.isArray(view.order) && !view.order.includes(id)) view.order.splice(Math.min(saved.order, view.order.length), 0, id);
  if (saved.sort) { view.sort = view.sort || []; for (const [i, s] of saved.sort) view.sort.splice(Math.min(i, view.sort.length), 0, s); }
  for (const k of LEVELS) if (saved[k] && !view[k]) view[k] = saved[k];
  for (const [k, v] of Object.entries(saved.maps || {})) view[k] = { ...(view[k] || {}), [id]: v };
}

// ------------------------------------------------------------------ one column's part of the one filter
/* WHY no state of its own: the hand filter reads and writes the all-views filter (el.filters), through the rail's own forms, so its
   pills, the query box, the URL and the rail all see it, and it can never disagree with them (Zach: a filter, not a second system). */
const emptyClause = (id) => `${ref(id)}.isEmpty()`;
const oneColumn = (id) => railConfig([{ property: id, as: 'values', exclude: true }, { property: id, as: 'range' }, { as: 'has', properties: [id] }]);

/** What the all-views filter says of one column: {empty, values, match, min, max}. */
export function columnFilter(filters, id) {
  const { facets, rest } = toRail(filters, oneColumn(id));
  const f = facets[id] || {};
  return { empty: rest.includes(emptyClause(id)), values: f.values || [], match: f.match || null, min: f.min ?? null, max: f.max ?? null };
}

/** The all-views filter with one column's part replaced; every other clause stays as written. */
export function setColumnFilter(filters, id, { empty = false, values = [], match = 'equals', min = null, max = null } = {}) {
  const rail = toRail(filters, oneColumn(id));
  const rest = rail.rest.filter((node) => node !== emptyClause(id));
  delete rail.facets[id];
  if (empty) rest.push(emptyClause(id));
  else {
    const f = {};
    if (values.length) { f.values = values; f.match = match; }
    if (min !== null && min !== '') f.min = min;
    if (max !== null && max !== '') f.max = max;
    if (Object.keys(f).length) rail.facets[id] = f;
  }
  return fromRail(rail.facets, rest);
}

/** The values a column's filter offers: the data's declared list first, in its order, then what the rows hold, as they hold it. A list
    column's items each count. So a value typed a moment ago is a choice the next time the control opens. */
export function choicesOf(rows, p) {
  const out = new Map();
  const add = (v) => { if (!isEmpty(v) && !out.has(String(v))) out.set(String(v), v); };
  for (const v of (p.labels ? Object.keys(p.labels) : (p.constraints && p.constraints.enum) || [])) add(v);
  for (const r of rows) { const v = cellValue(r[p.id]); if (Array.isArray(v)) v.forEach(add); else add(v); }
  return [...out.values()];
}
