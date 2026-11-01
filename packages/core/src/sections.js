/* The side peek's sections (docs/CONTRACT.md §35, PEP 0010 §10's `evidence` hint): `record.sections[]: {name,
   properties?, view?}`. A section may embed a view, drawn in the peek over a dataset's rows as its file holds them, its
   filters' `this.<column>` bound to the peeked row (the analyses' rule, §19, moved here from packages/analysis so the peek
   and an analysis bind `this` with one function). WHY a view in the peek and not a link out: "one diagnostic: its value,
   limits, window and provenance, then the data" (PEP 0010 §10) is read where the cell was clicked, and the evidence
   link (`display: link`) still opens the playback at the window. Pure: the host (elements/data-views.js) mounts the views. */

import { cellValue } from './grammar.js';
import { esc, mediaUrl, isEmpty, linkCell } from './format.js';

const isEmptyValue = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0);
const listOf = (v) => (Array.isArray(v) ? v : isEmptyValue(v) ? [] : [v]).map((x) => String(x).trim()).filter(Boolean);
const literal = (v) => (v === undefined || v === null ? 'null' : typeof v === 'number' || typeof v === 'boolean' ? String(v) : JSON.stringify(String(v)));

/** A filter expression with `this.<key>` replaced from `front` (Obsidian binds `this` in an embedded base to the host
    note; the side peek binds it to the peeked row). this.k.contains(x) over a list becomes (x == "a" || x == "b"), or
    false for none; this.k.isEmpty() becomes true or false; this.k becomes its value. Text inside quotes is never touched. */
export function bindThis(expr, front = {}) {
  const src = String(expr);
  let out = '', i = 0, quote = null;
  while (i < src.length) {
    const c = src[i];
    if (quote) {
      out += c;
      if (c === '\\' && i + 1 < src.length) { out += src[i + 1]; i += 2; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (c === '"' || c === "'") { quote = c; out += c; i++; continue; }
    const m = /^this\.([A-Za-z_][\w-]*)/.exec(src.slice(i));
    if (m && !/[\w.]/.test(src[i - 1] || '')) {
      const value = front ? front[m[1]] : undefined;
      let j = i + m[0].length;
      const rest = src.slice(j);
      if (/^\.contains\(/.test(rest)) {
        // the argument, to its matching parenthesis (quotes and nested calls skipped)
        let k = j + '.contains('.length, depth = 1, q = null;
        const start = k;
        for (; k < src.length && depth; k++) {
          const ch = src[k];
          if (q) { if (ch === '\\') k++; else if (ch === q) q = null; continue; }
          if (ch === '"' || ch === "'") q = ch;
          else if (ch === '(') depth++;
          else if (ch === ')') depth--;
        }
        const arg = src.slice(start, k - 1).trim();
        const list = listOf(value);
        out += list.length ? `(${list.map((x) => `${arg} == ${literal(x)}`).join(' || ')})` : 'false';
        i = k;
        continue;
      }
      if (/^\.isEmpty\(\)/.test(rest)) { out += isEmptyValue(value) ? 'true' : 'false'; i = j + '.isEmpty()'.length; continue; }
      out += Array.isArray(value) ? literal(value[0]) : literal(value);
      i = j;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

/** A filter (a string, a list, or an and / or / not tree) with every clause bound. */
export function bindFilters(filters, front) {
  if (typeof filters === 'string') return bindThis(filters, front);
  if (Array.isArray(filters)) return filters.map((f) => bindFilters(f, front));
  if (filters && typeof filters === 'object') return Object.fromEntries(Object.entries(filters).map(([k, v]) => [k, bindFilters(v, front)]));
  return filters;
}

/** A row's values as `this` sees them: each rich cell by its value. */
const valuesOf = (row) => Object.fromEntries(Object.entries(row || {}).map(([k, v]) => [k, cellValue(v)]));

/** Whether a field has something to show: a value (0 and false are values), or a reason it has none ({value: null,
    why}: the producer said why, and the peek shows it on hover). */
export const hasContent = (cell) => !isEmptyValue(cellValue(cell)) || !!(cell && typeof cell === 'object' && !Array.isArray(cell) && cell.why);

/** The peek's sections for a row: [{name, list: [property], view: <entry, filters bound> | null}], or null when the view
    has no record.sections (the host then lays out every field, as before). A section keeps the properties the data has
    (a pivot's columns left out); one with neither properties nor a view is dropped. With `rowsOf(view, section)` (how
    many rows the section's view, its filters bound, shows; null when the host cannot tell), a section with nothing for
    this row is left out too: no field with a value (or a reason it has none) and no row in its view. A section that
    stays keeps every field it lists, empty ones drawn "—" as before. WHY (RobotDx PEP 0001 §18.4, ask 3): one table holds
    plain checks beside stock diagnostics, and a plain check's peek drew three sections of dashes and an empty table. */
export function peekSections(view, props, row, { rowsOf = null } = {}) {
  const given = view && view.record && Array.isArray(view.record.sections) ? view.record.sections : null;
  if (!given) return null;
  const values = valuesOf(row);
  const out = [];
  for (const sec of given) {
    if (!sec || typeof sec !== 'object') continue;
    const list = (Array.isArray(sec.properties) ? sec.properties : []).map((pid) => props[pid]).filter((p) => p && !p.pivot);
    let bound = null;
    if (sec.view && typeof sec.view === 'object') {
      bound = { ...sec.view };
      if (sec.view.filters !== undefined) bound.filters = bindFilters(sec.view.filters, values);
    }
    if (!list.length && !bound) continue;
    if (typeof rowsOf === 'function' && !list.some((p) => hasContent(row ? row[p.id] : null)) && !(bound && rowsOf(bound, sec) !== 0)) continue;
    out.push({ name: sec.name, list, view: bound });
  }
  return out;
}

/** The datasets a view's sections read (their `from:`), each once, in order: what a dashboard hands its drill peek. */
export function sectionSources(view) {
  const out = [];
  for (const sec of (view && view.record && Array.isArray(view.record.sections) ? view.record.sections : [])) {
    const from = sec && sec.view && typeof sec.view === 'object' ? sec.view.from : null;
    if (typeof from === 'string' && from && !out.includes(from)) out.push(from);
  }
  return out;
}

/** `display: link` in the peek: a real <a href>, resolved against the data file's URL as a photo's path is (CONTRACT §1
    amendment), its text the cell's `text` when it has one, else the value as written; a value that is no link target
    (another scheme, a bare id: format.js isLinkTarget) is its label as plain text (CONTRACT §22). */
export function linkHtml(value, base) {
  const v = cellValue(value);
  if (isEmpty(v)) return '<span class="dv-none" title="no value">—</span>';
  return linkCell(value, { cls: 'dv-peek-link', href: (x) => mediaUrl(x, { url: base }), strip: false, rel: false }) || esc(String(v));
}
