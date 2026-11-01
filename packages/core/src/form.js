/* form: one row's fields as native inputs over the dataset's property schema (docs/VIEWS.md "Form / editor"). Not a
   view type: `type: record` with `edit: true` draws it, and so does the host's side peek when the view has
   `edit: true` (moved into the core from packages/views/form, docs/CONTRACT.md amendment 2026-10-26 (core pass)).

     text      <input> (a long value: <textarea>); with `labels` or `constraints.enum`: <select>
     number    <input type=number step=any>, the unit after it; bounds from the property's constraints.minimum /
               maximum, else the cell's own low / high (a Value(1.2, "m", low=0.6, high=1.85))
     list      <input>, comma-separated
     date      <input type=date>
     boolean   <input type=checkbox>
     derived / readOnly properties are shown, never inputs: the host would refuse them anyway (CONTRACT §1).

   A submit reads only what changed and proposes it (host.propose); the host decides. Constraint validation is the
   browser's (form.reportValidity()). A rich cell keeps its unit, basis and source: only its value is replaced. */

import { cellValue } from './grammar.js';
import { esc, isEmpty, isNum, valueHtml, valueText, withValue } from './format.js';

/** Why a property cannot be edited here, or null. */
export function lockedBecause(p) {
  if (p.derived) return `derived (${p.derived === true ? 'computed' : p.derived})`;
  if (p.readOnly) return 'read-only';
  return null;
}

function choices(p) {
  if (p.labels && typeof p.labels === 'object') return Object.entries(p.labels).map(([value, label]) => [value, String(label)]);
  const e = p.constraints && Array.isArray(p.constraints.enum) ? p.constraints.enum : null;
  return e ? e.map((x) => [String(x), String(x)]) : null;
}

function bounds(p, cell) {
  const c = p.constraints || {};
  const rich = cell && typeof cell === 'object' && !Array.isArray(cell) ? cell : {};
  const min = isNum(c.minimum) ? c.minimum : isNum(rich.low) ? rich.low : null;
  const max = isNum(c.maximum) ? c.maximum : isNum(rich.high) ? rich.high : null;
  return `${min !== null ? ` min="${min}"` : ''}${max !== null ? ` max="${max}"` : ''}`;
}

/** One field's control. `unit` is the unit text drawn after a number. */
export function fieldHtml(row, p, { unit } = {}) {
  const cell = row[p.id];
  const v = cellValue(cell);
  const id = `dv-f-${esc(p.id)}`;
  const locked = lockedBecause(p);
  if (locked) return `<span class="dv-form-locked" title="${esc(locked)}">${valueHtml(cell, p, { unit })}</span> <span class="dv-form-why" title="${esc(locked)}">${p.derived ? 'derived' : 'read-only'}</span>`;
  const name = `name="${esc(p.id)}" id="${id}"`;
  const u = unit !== undefined ? unit : (cell && typeof cell === 'object' && !Array.isArray(cell) && cell.unit) || p.unitText || '';
  if (p.type === 'boolean') return `<input type="checkbox" ${name}${v === true ? ' checked' : ''}>`;
  if (p.type === 'number') {
    // the cell's own evidence stays in sight while it is edited: its range, basis and source
    const rich = cell && typeof cell === 'object' && !Array.isArray(cell) ? cell : {};
    const hint = [isNum(rich.low) || isNum(rich.high) ? `${rich.low ?? ''}–${rich.high ?? ''}${u ? ' ' + u : ''}` : '', rich.basis, rich.source].filter((x) => !isEmpty(x)).join(' · ');
    return `<span class="dv-form-num"><input type="number" step="any" inputmode="decimal" ${name} value="${isNum(v) ? v : ''}"${bounds(p, cell)}>${u ? `<span class="dv-u">${esc(u)}</span>` : ''}</span>${hint ? `<div class="dv-form-range">${esc(hint)}</div>` : ''}`;
  }
  if (p.type === 'date') return `<input type="date" ${name} value="${esc(isEmpty(v) ? '' : String(v).slice(0, 10))}">`;
  // WHY not a list: a <select> holds one value, so choosing in it would silently replace all of a list's but one (§46)
  const opts = p.type === 'list' ? null : choices(p);
  if (opts) {
    const cur = isEmpty(v) ? '' : String(v);
    const known = opts.some(([value]) => value === cur);
    // WHY the current value stays an option even when the schema does not list it: the form must show what is stored
    return `<select ${name}><option value=""${cur === '' ? ' selected' : ''}>—</option>${opts.map(([value, label]) => `<option value="${esc(value)}"${value === cur ? ' selected' : ''}>${esc(label)}</option>`).join('')}${!known && cur ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : ''}</select>`;
  }
  const text = isEmpty(v) ? '' : p.type === 'list' || Array.isArray(v) ? (Array.isArray(v) ? v.join(', ') : String(v)) : valueText(v);
  if (text.length > 80 || text.includes('\n')) return `<textarea ${name} rows="3">${esc(text)}</textarea>`;
  return `<input type="text" ${name} value="${esc(text)}"${p.type === 'list' ? ' placeholder="a, b, c"' : ''}>`;
}

/** The value a control holds, in the data's own form (numbers are numbers, lists arrays, missing null). */
function read(control, p) {
  if (control.type === 'checkbox') return control.checked;
  const s = control.value.trim();
  if (s === '') return null;
  if (p.type === 'number') return Number(s);
  if (p.type === 'list') return s.split(',').map((x) => x.trim()).filter(Boolean);
  return s;
}

const same = (a, b) => JSON.stringify(isEmpty(a) ? null : a) === JSON.stringify(isEmpty(b) ? null : b);

/** The edit a form asks for: {property: newCell} over the fields that changed (a rich cell keeps its other keys). */
export function readEdits(form, row, props) {
  const set = {};
  for (const control of form.querySelectorAll('[name]')) {
    const p = props[control.name];
    if (!p || lockedBecause(p)) continue;
    const next = read(control, p);
    const cell = row[p.id];
    if (same(cellValue(cell), next)) continue;
    const rich = cell !== null && typeof cell === 'object' && !Array.isArray(cell) && 'value' in cell;
    if (!rich) { set[p.id] = next; continue; }
    set[p.id] = withValue(cell, next);
  }
  return set;
}
