/* One reversible edit session (docs/CONTRACT.md §40, docs/peps/0016-notion-table.md): what makes a table safe to edit quickly.
   Every write of the notion table funnels through here, so the host stays the owner of the data (each write goes through its
   hook when there is one) and any of them can be taken back. One per <data-views>; on a page with no edit-toggle it only carries a
   script's deleteRows, batch and editProperty, and keeps no history.

   WHY the element and not the table: a page section, a form, a cycle flip and the kanban all write through the element, and a
   history in the table would miss them.

   An op is what one change did, with what it takes to undo it; a step is the ops of one reader's gesture (edit-history.js):
     {type: 'edit', id, before: {p: cell}, absent: [p], after: {p: cell}}   `absent`: properties the row did not have
     {type: 'add', id, set, rows: [{row, index}]}                            `rows`: the row as it left, for a redo
     {type: 'delete', rows: [{row, index}]}                                  one row each, newest index first, so an undo (which
                                                                             walks a step backwards) puts them back lowest first
     {type: 'column', change: {op, property, …}, …}                          a column's add, rename, retype, delete; what brings it back
     {type: 'hide', property, view, before, after}                           `order` of the named view
   Undo is old values through the same hooks, so the host stays the owner of the data. */

import { esc } from './format.js';
import { EditHistory } from './edit-history.js';
import { textField } from './toolbar/bar.js';
import { lockedBecause } from './form.js';
import { isMultiSource } from './precedence.js';
import { KINDS, kindOf, definitionFor, propertyKey, dropFromView, restoreToView } from './sheet.js';

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const TOAST_MS = 8000;
const REFUSED = 'The host refused.';
const has = (el, hook) => typeof el[hook] === 'function';
// WHY a module's: with the focus on the page itself, the key belongs to the one sheet edited last
let lastEdited = null;

/** A row's cells as a hook gets them back: everything but its id. */
const cellsOf = (row) => { const { id, ...cells } = row; return clone(cells); };

export class EditSession {
  constructor(el) {
    this.el = el;
    this.history = new EditHistory();
    this._timer = 0;
    this._busy = false; // a replay is waiting on a host
  }

  /** The rows as loaded (an edit lands there; CONTRACT §36). */
  get rows() { const el = this.el; return (el._raw || el._data).rows; }

  // ------------------------------------------------------------------ the toast
  /** One line at the foot of the window: what just happened, Undo when it can be taken back. WHY a toast, no dialog: Notion's
      way, and the reason a delete can be one click. It stays while the pointer or the focus is on it. */
  toast(text, { undo = false, bad = false } = {}) {
    const el = this.el;
    let node = el.querySelector(':scope > .dv-toast');
    if (!node) {
      node = document.createElement('div');
      node.className = 'dv-toast';
      node.setAttribute('role', 'status');
      node.setAttribute('aria-live', 'polite');
      node.addEventListener('pointerenter', () => clearTimeout(this._timer));
      node.addEventListener('pointerleave', () => this._fade(node));
      node.addEventListener('focusin', () => clearTimeout(this._timer));
      node.addEventListener('focusout', () => this._fade(node));
      el.append(node);
    }
    node.classList.toggle('dv-toast-bad', bad);
    node.innerHTML = `<span class="dv-toast-text">${esc(text)}</span>${undo ? '<button type="button" class="dv-toast-undo" data-toast-undo>Undo</button>' : ''}`;
    node.hidden = false;
    this._fade(node);
  }

  _fade(node) {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => { node.hidden = true; }, TOAST_MS);
  }

  hideToast() {
    clearTimeout(this._timer);
    const node = this.el.querySelector(':scope > .dv-toast');
    if (node) node.hidden = true;
  }

  // ------------------------------------------------------------------ the rows the element holds
  /** {row, index} of each id, in the data's order: what it takes to put them back where they were. */
  snapshot(ids) {
    const want = new Set(ids.map(String));
    const out = [];
    this.rows.forEach((row, index) => { if (want.has(String(row.id))) out.push({ row: clone(row), index }); });
    return out;
  }

  /** Draw again after a step. `moved`: rows or columns came or went, so the shown rows and the row-model worker's copy are stale; an
      edit has told the worker already (el._editWorker). */
  _changed(moved = true) {
    const el = this.el;
    if (moved) {
      if (el._raw && el._data !== el._raw) el._data = el._shown();
      el._byId = null;
      el._dropWorker();
    }
    el._revise();
    el._render();
    if (el._peek && !el.row(el._peek.id)) el.closePeek();
  }

  drop(ids) {
    const gone = new Set(ids.map(String));
    const rows = this.rows;
    for (let i = rows.length - 1; i >= 0; i--) if (gone.has(String(rows[i].id))) rows.splice(i, 1);
    this.el._byId = null;
  }

  /** Put a row back where it was, unless a host has handed it in already. */
  put(row, index, id = row.id) {
    if (this.el.row(id)) return;
    const rows = this.rows;
    rows.splice(Math.min(index, rows.length), 0, { ...clone(row), id });
    this.el._byId = null;
  }

  // ------------------------------------------------------------------ deleting rows
  async deleteRows(ids) {
    const el = this.el;
    const list = [...new Set((Array.isArray(ids) ? ids : [ids]).map(String))];
    const refused = this._refuseDelete(list);
    if (refused && el._editTools()) this.toast(`Not deleted: ${refused}`, { bad: true });
    const result = refused ? { ok: false, reason: refused } : await this._deleteThrough(list);
    el.dispatchEvent(new CustomEvent('data-views-delete', { detail: { ids: list, result } }));
    return result;
  }

  _refuseDelete(list) {
    const el = this.el;
    if (!list.length) return 'No rows to delete.';
    if (el._viewOnly()) return el._viewRefuses;
    const missing = list.find((id) => !el.row(id));
    if (missing !== undefined) return `No row has the id ${missing}.`;
    const locked = list.filter((id) => el.row(id)._readOnly).length;
    // WHY the whole selection refuses: half of a delete is a state nobody asked for
    if (locked) return list.length === 1 ? 'This row is read-only.' : `${locked} of these rows ${locked === 1 ? 'is' : 'are'} read-only, so none were deleted.`;
    if (typeof el.acceptDelete !== 'function' && !el.editing) return 'This page is read-only: the data changes at its source.';
    return null;
  }

  async _deleteThrough(list) {
    const el = this.el;
    const rows = this.snapshot(list); // before the hook: a host may hand in new data while it answers
    const next = this._nextRow(list);
    const answer = await this._take(list);
    const tools = el._editTools();
    if (!answer.ok) {
      if (tools) this.toast(`Not deleted: ${answer.reason || 'the host refused.'}`, { bad: true });
      return answer;
    }
    this._changed();
    if (tools) {
      // WHY none when no hook can bring them back: an Undo that only draws a row the host has deleted would be a lie
      const back = !has(el, 'acceptDelete') || has(el, 'acceptAdd');
      if (back) this.push('Delete', [...rows].reverse().map((r) => ({ type: 'delete', rows: [r] })));
      this.toast(`Deleted ${list.length} ${list.length === 1 ? 'row' : 'rows'}`, { undo: back });
      this._focus(next);
    }
    return answer;
  }

  /** Take rows out: through acceptDelete when the page has it; then from what the element holds. */
  async _take(ids) {
    const el = this.el;
    let answer = { ok: true };
    if (has(el, 'acceptDelete')) {
      try { answer = (await el.acceptDelete({ ids: [...ids] })) || { ok: false, reason: REFUSED }; } catch (err) { answer = { ok: false, reason: err.message }; }
    }
    if (answer.ok) this.drop(ids);
    return answer;
  }

  _focus(id) {
    const plugin = this.el._plugin;
    if (id !== null && id !== undefined && this.el.row(id) && plugin && plugin.revealRow) plugin.revealRow(id);
  }

  /** The row the focus goes to once these have left: the one after them in the drawn order, else the one before. */
  _nextRow(list) {
    const el = this.el;
    const order = el._model ? el._model.rows.map((r) => String(r.id)) : [];
    const gone = new Set(list);
    const last = order.reduce((k, id, i) => (gone.has(id) ? i : k), -1);
    if (last < 0) return null;
    for (let i = last + 1; i < order.length; i++) if (!gone.has(order[i])) return order[i];
    for (let i = last - 1; i >= 0; i--) if (!gone.has(order[i])) return order[i];
    return null;
  }

  // ------------------------------------------------------------------ one step of many writes
  /** Edits, new rows and deletes as one undo step. {edits: [{id, set}], adds: [{set, at?}], deletes: [id]}. With acceptBatch one call,
      all or nothing, applied on its ok; else each through its own hook, and what a host refuses is left out of the step and
      reported. Returns {ok, reason, landed, refused}: how many items landed, how many did not. */
  async batch({ edits = [], adds = [], deletes = [] } = {}, { label = 'Edit' } = {}) {
    const el = this.el;
    if (el._viewOnly()) return { ok: false, reason: el._viewRefuses, landed: 0, refused: edits.length + adds.length + deletes.length };
    let reason = null;
    const open = this._unsourced(edits.map((e) => el._folded(e)));
    const asked = open.edits.filter((e) => { const no = el._refuseEdit(e); if (no) reason = no; return !no; });
    let refused = open.edits.length - asked.length;
    const was = asked.map((e) => this.before(e));
    const rows = this.snapshot(deletes);
    const ops = [];
    if (has(el, 'acceptBatch')) {
      const answer = await this._askBatch({ edits: asked.map(({ id, set }) => ({ id: String(id), set: clone(set) })), adds: adds.map((a) => clone(a)), deletes: [...deletes].map(String) });
      if (!answer.ok) return { ok: false, reason: answer.reason || REFUSED, landed: 0, refused: edits.length + adds.length + deletes.length, skipped: open.skipped };
      asked.forEach((e, i) => { this._landCells(e); if (was[i]) ops.push(this._editOp(e, was[i])); });
      adds.forEach((a, i) => {
        const id = (answer.ids && answer.ids[i]) ?? a.id;
        if (id === undefined || id === null) return; // nothing to name it by: the host hands it in, and it cannot be undone
        this.put({ ...a.set, id }, this.rows.length);
        ops.push({ type: 'add', id: String(id), set: clone(a.set), rows: [] });
      });
      this.drop(deletes);
    } else {
      for (let i = 0; i < asked.length; i++) {
        const res = await el._decide(asked[i], { quiet: true });
        el._told(asked[i], res);
        if (res.ok) { if (was[i]) ops.push(this._editOp(asked[i], was[i])); } else { refused++; reason = res.reason || REFUSED; }
      }
      for (const a of adds) {
        const res = await el._fileRow(a.set, { at: a.at || null, quiet: true });
        if (!res.ok) { refused++; reason = res.reason || REFUSED; continue; }
        if (res.id !== undefined && res.id !== null) ops.push({ type: 'add', id: String(res.id), set: clone(a.set), rows: [] });
      }
      if (deletes.length) {
        const answer = await this._take(deletes);
        if (!answer.ok) { refused += deletes.length; reason = answer.reason || REFUSED; }
      }
    }
    const gone = rows.filter((r) => !el.row(r.row.id));
    this.push(label, [...ops, ...[...gone].reverse().map((r) => ({ type: 'delete', rows: [r] }))]);
    this._changed(adds.length > 0 || deletes.length > 0);
    const total = open.edits.length + adds.length + deletes.length;
    return { ok: !refused, reason, landed: total - refused, refused, skipped: open.skipped };
  }

  /** Edits without the cells whose value comes from their sources, and how many those were. WHY left out and not a refusal: a paste or
      an undo is many cells, and one that comes from its sources is a locked cell among them (CONTRACT §40). */
  _unsourced(edits) {
    const el = this.el;
    let skipped = 0;
    const out = [];
    for (const e of edits) {
      const keys = Object.keys(e.set || {});
      const keep = keys.filter((p) => !el.isSourced(e.id, p) || isMultiSource(e.set[p]));
      skipped += keys.length - keep.length;
      if (keep.length) out.push({ ...e, set: Object.fromEntries(keep.map((p) => [p, e.set[p]])) });
    }
    return { edits: out, skipped };
  }

  async _askBatch(plan) {
    try { return (await this.el.acceptBatch(plan)) || { ok: false, reason: REFUSED }; } catch (err) { return { ok: false, reason: err.message }; }
  }

  _editOp(edit, was) { return { type: 'edit', id: String(edit.id), before: was.cells, absent: was.absent, after: clone(edit.set) }; }

  /** An edit a host has taken in a batch, in what the element holds. */
  _landCells({ id, set }) {
    const el = this.el;
    const row = el._rawRow(id);
    if (!row) return;
    Object.assign(row, clone(set));
    el._resolveAgain(set);
    el._revise();
    el._editWorker(row);
  }

  /** A block from the table (planPaste's): one step, and the toast says what became of every cell. */
  async paste(plan) {
    const res = await this.batch({ edits: plan.edits, adds: plan.adds }, { label: 'Paste' });
    const n = plan.filled;
    const skipped = [plan.locked ? `${plan.locked} locked` : '', plan.pastColumn ? `${plan.pastColumn} past the last column` : '', plan.pastRow ? `${plan.pastRow} past the last row` : ''].filter(Boolean);
    const rest = skipped.length ? ` · skipped ${skipped.join(', ')}` : '';
    const moved = plan.edits.length + plan.adds.length;
    if (!res.landed && moved) this.toast(`Not pasted: ${res.reason || REFUSED}`, { bad: true });
    else if (res.refused) this.toast(`Pasted ${res.landed} of ${moved} rows: ${res.reason || REFUSED}${rest}`, { undo: true, bad: true });
    else if (!n) this.toast(`Nothing pasted${rest}`, { bad: true });
    else this.toast(`Pasted ${n} ${n === 1 ? 'cell' : 'cells'}${rest}`, { undo: moved > 0 });
    const first = plan.edits[0] ? plan.edits[0].id : null;
    this._focus(first);
    return res;
  }

  // ------------------------------------------------------------------ columns
  /** The properties as loaded (the shown data shares them). */
  get defs() { const el = this.el; return (el._raw || el._data).properties; }

  /** A column change from the header menu or a script: {op: add | rename | retype | hide | delete, property, label?, kind?, after?}.
      The page's acceptProperty decides; an editable page with no hook does it in memory; on ok the element applies it to what it holds.
      Hide is the view's, not the data's, so no hook hears it. */
  async editProperty(change) {
    const el = this.el;
    const refused = this._refuseProperty(change || {});
    let result;
    if (refused) result = { ok: false, reason: refused };
    else if (change.op === 'hide') result = this._hide(change.property);
    else result = await this._changeColumn(change);
    const property = (result.ok && result.property) || (change && change.property);
    el.dispatchEvent(new CustomEvent('data-views-property', { detail: { op: change && change.op, property, result } }));
    return result;
  }

  _refuseProperty({ op, property, label, kind }) {
    const el = this.el;
    if (el._viewOnly()) return el._viewRefuses;
    if (typeof el.acceptProperty !== 'function' && !el.editing) return 'This page is read-only: the data changes at its source.';
    if (!['add', 'rename', 'retype', 'hide', 'delete'].includes(op)) return `There is no column change called ${op}.`;
    if ((op === 'add' || op === 'rename') && !String(label || '').trim()) return 'A column needs a name.';
    if ((op === 'add' || op === 'retype') && !KINDS.includes(kind)) return `There is no type called ${kind}.`;
    if (op === 'add') return null;
    const p = el._model.columns[property];
    if (!p || !(property in this.defs)) return `${property} is not a property of this data.`;
    const locked = lockedBecause(p);
    if (locked && (op === 'retype' || op === 'delete')) return `${p.label} is ${locked}.`;
    if (op === 'delete' && property === el._data.titleProperty) return `${p.label} names each record, so it stays.`;
    if (op === 'hide' && this.lastColumn(property)) return 'A table keeps at least one column.';
    return null;
  }

  /** Whether this is the only column the view draws. WHY it matters: a table with none is a dead end, with no header to reach a menu from. */
  lastColumn(id) {
    const columns = this.el._model.columns;
    return !this._order().some((x) => x !== id && columns[x]);
  }

  async _ask(payload) {
    const el = this.el;
    if (typeof el.acceptProperty !== 'function') return { ok: true };
    try { return (await el.acceptProperty(clone(payload))) || { ok: false, reason: REFUSED }; } catch (err) { return { ok: false, reason: err.message }; }
  }

  async _changeColumn(change) {
    const el = this.el;
    const { op, property: id } = change;
    const p = id ? el._model.columns[id] : null;
    if (op === 'add') {
      const definition = definitionFor(change.kind);
      const label = change.label.trim();
      const property = propertyKey(label, Object.keys(this.defs));
      const payload = { op: 'add', property, label, kind: change.kind, definition, after: change.after ?? null };
      const answer = await this._ask(payload);
      if (!answer.ok) return answer;
      const key = answer.property ?? property;
      const record = { type: 'column', change: { ...payload, property: key }, view: el.origin.name };
      this._landAdd(key, { ...definition, label }, label, change.after, record);
      this.push('Add property', [record]);
      this._changed();
      return { ok: true, property: key };
    }
    if (op === 'rename') {
      const label = change.label.trim();
      const answer = await this._ask({ op, property: id, label, from: p.label });
      if (!answer.ok) return answer;
      const record = { type: 'column', change: { op, property: id, label, from: p.label }, entry: this._entry(id) };
      this._setName(id, label);
      this.push('Rename', [record]);
      this._changed();
      return { ok: true };
    }
    if (op === 'retype') {
      const from = clone(this.defs[id]);
      const definition = definitionFor(change.kind, from);
      const answer = await this._ask({ op, property: id, kind: change.kind, definition, from });
      if (!answer.ok) return answer;
      const record = { type: 'column', change: { op, property: id, kind: change.kind, definition, from }, view: el.origin.name };
      this._landRetype(id, definition, record);
      this.push('Change type', [record]);
      this._changed();
      return { ok: true };
    }
    const answer = await this._ask({ op: 'delete', property: id });
    if (!answer.ok) return answer;
    const record = { type: 'column', change: { op: 'delete', property: id, label: p.label }, view: el.origin.name };
    this._landDelete(id, record);
    this.push('Delete property', [record]);
    this._changed();
    if (el._editTools()) this.toast(`Deleted the property ${p.label}`, { undo: true });
    return { ok: true };
  }

  /** The view's `order` as drawn. */
  _order() {
    const el = this.el, columns = el._model.columns;
    return el.view.order && el.view.order.length ? [...el.view.order] : Object.keys(columns).filter((k) => !columns[k].hidden && !columns[k].pivot);
  }

  /** A view's order stays the reader's: the new column goes beside the one it was asked from. */
  _landAdd(id, definition, label, after, record) {
    const el = this.el;
    this._putDef(id, definition, record.index);
    this._setName(id, label);
    // the first column of a table built from nothing names its records
    const held = el._raw || el._data;
    if (!held.titleProperty) held.titleProperty = id;
    if (record.values) for (const row of this.rows) if (String(row.id) in record.values) row[id] = clone(record.values[String(row.id)]);
    if (record.saved) el.update((x) => restoreToView(x, id, clone(record.saved)));
    else if (el.view.order && el.view.order.length) el.update((x) => { const at = x.order.indexOf(after); x.order.splice(at < 0 ? x.order.length : at + 1, 0, id); });
  }

  _landDelete(id, record) {
    const el = this.el;
    record.index = Object.keys(this.defs).indexOf(id);
    record.definition = clone(this.defs[id]);
    record.entry = this._entry(id);
    record.values = {};
    for (const row of this.rows) if (id in row) { record.values[String(row.id)] = clone(row[id]); delete row[id]; }
    delete this.defs[id];
    this._setEntry(id, undefined);
    let saved = null;
    el.update((x) => { saved = dropFromView(x, id); });
    record.saved = saved;
  }

  _landRetype(id, definition, record) {
    const el = this.el;
    this.defs[id] = clone(definition);
    // WHY the view's own display goes: it would go on drawing the old kind
    record.display = el.view.display && el.view.display[id];
    if (record.display !== undefined) el.update((x) => { delete x.display[id]; if (!Object.keys(x.display).length) delete x.display; });
  }

  /** Put a definition back at its place in the list, so a view with no `order` draws its column where it was. */
  _putDef(id, definition, index) {
    const defs = this.defs;
    const entries = Object.entries(defs);
    entries.splice(index === undefined ? entries.length : Math.min(index, entries.length), 0, [id, clone(definition)]);
    for (const k of Object.keys(defs)) delete defs[k];
    for (const [k, v] of entries) defs[k] = v;
  }

  _baseKey(id) { const b = this.el._base.properties || {}; return `note.${id}` in b ? `note.${id}` : id; }
  _entry(id) { const b = this.el._base.properties || {}; return clone(b[this._baseKey(id)]); }
  _setEntry(id, entry) {
    const el = this.el;
    const next = { ...(el._base.properties || {}) };
    const key = this._baseKey(id);
    if (entry === undefined) delete next[key]; else next[key] = entry;
    el._base.properties = next;
    el._propsRev = (el._propsRev || 0) + 1;
  }
  _setName(id, label) { this._setEntry(id, { ...(this._entry(id) || {}), displayName: label }); }

  _hide(id) {
    const el = this.el;
    const before = this._order();
    const after = before.filter((x) => x !== id);
    el.update((x) => { x.order = after; });
    this.push('Hide', [{ type: 'hide', property: id, view: el.origin.name, before, after }]);
    return { ok: true };
  }

  /** A column's step, back or forward: through acceptProperty with the old values, as a row's edit is through acceptEdit. */
  async _replayColumn(op, undoing) {
    const c = op.change, id = c.property;
    if (c.op === 'rename') {
      const label = undoing ? c.from : c.label;
      const answer = await this._ask({ op: 'rename', property: id, label, from: undoing ? c.label : c.from });
      if (!answer.ok) return answer;
      if (undoing) this._setEntry(id, op.entry); else this._setName(id, label);
      return { ok: true };
    }
    if (c.op === 'retype') {
      const definition = undoing ? c.from : c.definition;
      const from = undoing ? c.definition : c.from;
      const answer = await this._ask({ op: 'retype', property: id, kind: kindOf(definition), definition, from });
      if (!answer.ok) return answer;
      if (undoing) {
        this.defs[id] = clone(definition);
        if (op.display !== undefined) this.el.update((x) => { x.display = { ...(x.display || {}), [id]: op.display }; });
      } else this._landRetype(id, definition, op);
      return { ok: true };
    }
    // an add undone and a delete redone take the column away; an add redone and a delete undone bring it back
    if ((c.op === 'add') === undoing) {
      const answer = await this._ask({ op: 'delete', property: id });
      if (!answer.ok) return answer;
      this._landDelete(id, op);
      return { ok: true };
    }
    const definition = op.definition || { ...c.definition, label: c.label };
    const label = c.label;
    const answer = await this._ask({ op: 'restore', property: id, definition, label, values: op.values || {} });
    if (!answer.ok) return answer;
    this._landAdd(id, definition, label, c.after, op);
    if (op.entry !== undefined) this._setEntry(id, op.entry);
    return { ok: true };
  }

  /** A hide comes back in its own view; WHY not any open view: `order` is one view's, and writing it into another would be a lie. */
  _replayHide(op, undoing) {
    const el = this.el;
    if (el.origin.name !== op.view) return { ok: false, reason: `Open the view ${op.view} to change that.` };
    const order = undoing ? op.before : op.after;
    el.update((x) => { x.order = [...order]; });
    return { ok: true };
  }

  // ------------------------------------------------------------------ what a step records
  /** One reader's gesture onto the stack. Only on an edit-toggle page in Edit: `editable` alone keeps no stack (§37). */
  push(label, ops) {
    if (!this.el._editTools()) return;
    this.history.push({ label, ops });
    this.el._keepRows(ops.filter((op) => op.id !== undefined).map((op) => op.id));
    lastEdited = this.el;
    this.hideToast();
  }

  /** What an edit is about to replace, as the row holds it; null when nothing is recording. */
  before(edit) {
    const el = this.el;
    if (!el._editTools() || !edit || !edit.set) return null;
    const row = el._rawRow(edit.id);
    if (!row) return null;
    const cells = {}, absent = [];
    for (const p of Object.keys(edit.set)) {
      if (p in row) cells[p] = clone(row[p]);
      else { cells[p] = null; absent.push(p); }
    }
    return { cells, absent };
  }

  edited(edit, was) {
    if (was) this.push('Edit', [this._editOp(edit, was)]);
  }

  /** WHY no id, no step: with no id there is nothing a hook could be told to take back, and the stack must not promise it. */
  added(set, id) {
    if (id !== undefined && id !== null) this.push('Add', [{ type: 'add', id: String(id), set: clone(set), rows: [] }]);
  }

  // ------------------------------------------------------------------ taking it back
  get canUndo() { return this.history.canUndo; }
  get canRedo() { return this.history.canRedo; }
  undo() { return this.replay('undo'); }
  redo() { return this.replay('redo'); }

  /** Ctrl/Cmd+Z, with Shift for redo. True when the key was taken. WHY only outside a text field: an open editor's undo of what
      was just typed is the browser's, and taking it would take back a whole committed cell instead of a word. */
  key(e) {
    const el = this.el;
    if (!el._editTools() || e.defaultPrevented || textField(document.activeElement)) return false;
    const page = e.target === document.body || e.target === document.documentElement;
    if (!el.contains(e.target) && !(page && lastEdited === el)) return false;
    e.preventDefault();
    if (e.shiftKey) this.redo(); else this.undo();
    return true;
  }

  /** Replay the top step, each op through its hook. What the host took crosses to the other stack and what it refused stays, so the
      stacks never claim what did not happen; an op whose row has gone leaves, and the toast says so. */
  async replay(dir) {
    const el = this.el;
    if (!el._editTools()) return { ok: false, reason: el._viewRefuses };
    const step = this.history.top(dir);
    if (!step) return { ok: false, reason: `Nothing to ${dir}.` };
    if (this._busy) return { ok: false, reason: 'One moment: the last one is still on its way.' };
    this._busy = true;
    el._keepRows(step.ops.filter((op) => op.id !== undefined).map((op) => op.id));
    const undoing = dir === 'undo';
    const results = new Map();
    let focus = null, skipped = 0;
    try {
      // a cell that has come to have sources since is a locked cell now: it leaves the step, counted
      for (const op of step.ops) if (op.type === 'edit') { skipped += this._dropSourced(op); if (!Object.keys(op.before).length) results.set(op, { ok: false, gone: true, skipped: true }); }
      // a step walks backwards to undo, forwards to redo; rows that leave go in one call, as a bulk delete did
      const ops = (undoing ? [...step.ops].reverse() : step.ops).filter((op) => !results.has(op));
      for (const op of ops) {
        if (op.type === 'column') results.set(op, await this._replayColumn(op, undoing));
        else if (op.type === 'hide') results.set(op, this._replayHide(op, undoing));
      }
      const rowOps = ops.filter((op) => op.type === 'edit' || op.type === 'add' || op.type === 'delete');
      const leaving = rowOps.filter((op) => op.type !== 'edit' && (op.type === 'add') === undoing);
      if (!rowOps.length) { /* a column's step: done above */ } else if (has(el, 'acceptBatch')) focus = await this._replayBatch(rowOps, leaving, undoing, results);
      else {
        for (const op of rowOps) if (op.type === 'edit') { results.set(op, await this._replayEdit(op, undoing)); focus = op.id; }
        if (leaving.length) await this._replayLeaving(leaving, results);
        for (const op of rowOps) if (op.type !== 'edit' && !results.has(op)) { const res = await this._replayBack(op); results.set(op, res); if (res.ok) focus = res.id; }
      }
    } finally { this._busy = false; }
    const of = (test) => step.ops.filter((op) => test(results.get(op)));
    this.history.settle(dir, of((r) => r.ok), of((r) => !r.ok && !r.gone));
    lastEdited = el;
    this._changed(step.ops.some((op) => op.type !== 'edit'));
    this.hideToast();
    const refused = [...results.values()].find((r) => !r.ok && !r.gone);
    const gone = [...results.values()].some((r) => r.gone && !r.skipped);
    const verb = undoing ? 'undone' : 'redone';
    const counted = skipped ? ` · skipped ${skipped} locked` : '';
    if (refused) this.toast(`Not ${verb}: ${refused.reason || REFUSED}${counted}`, { bad: true });
    else if (gone) this.toast(`Could not be ${verb}: its row has gone.${counted}`, { bad: true });
    else if (skipped) this.toast(`${undoing ? 'Undone' : 'Redone'}${counted}`, { bad: true });
    this._focus(focus);
    return refused ? { ok: false, reason: refused.reason, skipped } : gone ? { ok: false, reason: 'Its row has gone.', skipped } : { ok: true, skipped };
  }

  /** Take the cells that now come from their sources out of an edit op; how many there were. */
  _dropSourced(op) {
    let n = 0;
    for (const p of Object.keys(op.before)) {
      if (!this.el.isSourced(op.id, p) || isMultiSource(op.after[p])) continue;
      delete op.before[p];
      delete op.after[p];
      op.absent = op.absent.filter((x) => x !== p);
      n++;
    }
    return n;
  }

  /** A step as one call to acceptBatch: its edits with their old values, the rows coming back, the rows leaving. All or nothing. */
  async _replayBatch(ops, leaving, undoing, results) {
    const el = this.el;
    const edits = ops.filter((op) => op.type === 'edit');
    const back = ops.filter((op) => op.type !== 'edit' && !leaving.includes(op));
    const home = (op) => op.rows[0] || { row: { ...op.set, id: op.id }, index: 0 };
    const set = (op) => clone(undoing ? op.before : op.after);
    const live = edits.filter((op) => { const here = !!el.row(op.id); if (!here) results.set(op, { ok: false, gone: true }); return here; });
    const list = leaving.flatMap((op) => (op.type === 'add' ? [op.id] : op.rows.map((r) => String(r.row.id))));
    const rows = this.snapshot(list);
    const answer = await this._askBatch({ edits: live.map((op) => ({ id: op.id, set: set(op) })), adds: back.map((op) => ({ set: cellsOf(home(op).row), id: home(op).row.id, restore: true, index: home(op).index })), deletes: list });
    for (const op of [...live, ...back, ...leaving]) results.set(op, answer.ok ? { ok: true } : { ok: false, reason: answer.reason || REFUSED });
    if (!answer.ok) return null;
    for (const op of live) {
      this._landCells({ id: op.id, set: set(op) });
      if (undoing) { const row = el._rawRow(op.id); if (row) for (const p of op.absent) delete row[p]; }
    }
    for (const op of leaving) if (op.type === 'add') op.rows = rows.filter((r) => String(r.row.id) === op.id);
    this.drop(list);
    back.forEach((op, i) => {
      const { row, index } = home(op);
      const id = (answer.ids && answer.ids[i]) ?? row.id;
      this.put(row, index, id);
      if (String(id) !== String(row.id)) this.history.remap(row.id, id);
    });
    return live.length ? live[live.length - 1].id : null;
  }

  async _replayEdit(op, undoing) {
    const el = this.el;
    if (!el.row(op.id)) return { ok: false, gone: true };
    const edit = { id: op.id, set: clone(undoing ? op.before : op.after) };
    const res = await el._decide(edit, { quiet: true });
    el._told(edit, res);
    // in memory the row goes back to having no such key; a host keeps what it was told (null)
    if (res.ok && undoing && !has(el, 'acceptEdit')) { const row = el._rawRow(op.id); if (row) for (const p of op.absent) delete row[p]; }
    return res;
  }

  /** Rows that left through a step's undo (an add) or redo (a delete): one call to the host. */
  async _replayLeaving(ops, results) {
    const el = this.el;
    const ids = (op) => (op.type === 'add' ? [op.id] : op.rows.map((r) => String(r.row.id)));
    // WHY refuse: with no acceptDelete the row would leave this page and stay at the host
    if (has(el, 'acceptAdd') && !has(el, 'acceptDelete')) { for (const op of ops) results.set(op, { ok: false, reason: 'This page takes no deletes, so that add cannot be undone.' }); return; }
    // a host may hold a row it has not handed in yet, so only with no hook does "not here" mean gone
    const here = has(el, 'acceptDelete') ? ops : ops.filter((op) => { const ok = ids(op).every((id) => el.row(id)); if (!ok) results.set(op, { ok: false, gone: true }); return ok; });
    if (!here.length) return;
    const list = here.flatMap(ids);
    const rows = this.snapshot(list);
    const answer = await this._take(list);
    for (const op of here) {
      if (answer.ok && op.type === 'add') op.rows = rows.filter((r) => String(r.row.id) === op.id);
      results.set(op, answer);
    }
    if (answer.ok) el.dispatchEvent(new CustomEvent('data-views-delete', { detail: { ids: list, result: answer } }));
  }

  /** A row that comes back through a step's undo (a delete) or redo (an add): acceptAdd with its old cells, its id and restore: true.
      A host that answers another id is followed through both stacks. */
  async _replayBack(op) {
    const el = this.el;
    const { row, index } = op.rows[0] || { row: { ...op.set, id: op.id }, index: 0 };
    let answer = { ok: true, id: row.id };
    if (has(el, 'acceptAdd')) {
      try { answer = (await el.acceptAdd({ set: cellsOf(row), id: row.id, restore: true, index })) || { ok: false, reason: REFUSED }; } catch (err) { answer = { ok: false, reason: err.message }; }
    }
    if (!answer.ok) return { ok: false, reason: answer.reason || REFUSED };
    const id = answer.id ?? row.id;
    this.put(row, index, id);
    if (String(id) !== String(row.id)) this.history.remap(row.id, id);
    return { ok: true, id };
  }
}
