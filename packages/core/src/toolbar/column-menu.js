/* The column menu (docs/CONTRACT.md §40): a table header's name, type, Hide, Delete and Add a property, in Edit. Notion's property menu,
   in the element's own popover (.dv-pop), so Esc, an outside click and the phone width are the ones every other menu has, and no
   side panel. Every change goes through el.editProperty: a refusal stays here, with what was typed and the host's reason. */

import { esc } from '../format.js';
import { KINDS, KIND_LABEL, kindOf } from '../sheet.js';
import { lockedBecause } from '../form.js';
import { openColumnFilter } from './column-filter.js';

const kindOptions = (selected) => {
  const list = KINDS.includes(selected) ? KINDS : [selected, ...KINDS];
  return list.map((k) => `<option value="${esc(k)}"${k === selected ? ' selected' : ''}>${esc(KIND_LABEL[k] || k)}</option>`).join('');
};

/** Open the menu of property `id` under `anchor`. */
export function openColumnMenu(el, id, anchor) {
  const p = el._model.columns[id];
  if (!p) return;
  const locked = lockedBecause(p);
  const title = id === el._data.titleProperty;
  const noDelete = locked ? `This column is ${locked}.` : title ? 'The title column names each record, so it stays.' : '';
  const noHide = el._session.lastColumn(id) ? 'A table keeps at least one column.' : '';
  const html = `<form class="dv-col-form" data-col-form>
      <label>Name <input data-col-name value="${esc(p.label)}" autocomplete="off" aria-label="Column name"></label>
      <label>Type <select data-col-type aria-label="Column type"${locked ? ` disabled title="This column is ${esc(locked)}."` : ''}>${kindOptions(kindOf(p))}</select></label>
    </form>
    <p class="dv-col-msg" data-col-msg role="alert"></p>
    <div class="dv-col-acts">
      <button type="button" class="dv-col-act" data-col-filter>Filter by this column</button>
      <button type="button" class="dv-col-act" data-col-hide${noHide ? ` disabled title="${esc(noHide)}"` : ''}>Hide in this view</button>
      <button type="button" class="dv-col-act" data-col-delete${noDelete ? ` disabled title="${esc(noDelete)}"` : ''}>Delete property</button>
      <button type="button" class="dv-col-act" data-col-add>Add a property</button>
    </div>`;
  const pop = el.$('.dv-pop');
  const back = () => { if (el._plugin && el._plugin.focusColumn) el._plugin.focusColumn(id); };
  // WHY shut first: the button that opened it is redrawn with the header, so a second press must open it, not read as a toggle
  el.closeMenu();
  el._pop(anchor, html, (node) => {
    pop._back = back;
    const say = (text) => { node.querySelector('[data-col-msg]').textContent = text || ''; };
    const done = (res, then = back) => {
      if (!res.ok) { say(res.reason || 'The host refused.'); return; }
      el.closeMenu();
      then();
    };
    const name = node.querySelector('[data-col-name]');
    name.select();
    let current = p.label;
    const rename = async (close) => {
      const label = name.value.trim();
      if (label === current && !close) return;
      if (label === current) { el.closeMenu(); back(); return; }
      const res = await el.editProperty({ op: 'rename', property: id, label });
      if (res.ok) current = label;
      if (close || !res.ok) done(res);
    };
    node.querySelector('[data-col-form]').addEventListener('submit', (e) => { e.preventDefault(); rename(true); });
    name.addEventListener('change', () => rename(false));
    node.querySelector('[data-col-type]').addEventListener('change', async (e) => {
      const res = await el.editProperty({ op: 'retype', property: id, kind: e.target.value });
      say(res.ok ? '' : res.reason);
    });
    node.querySelector('[data-col-filter]').addEventListener('click', () => openColumnFilter(el, id, el.querySelector(`.dv-stage thead th[data-sort="${CSS.escape(id)}"]`) || anchor));
    node.querySelector('[data-col-hide]').addEventListener('click', async () => done(await el.editProperty({ op: 'hide', property: id }), () => {}));
    node.querySelector('[data-col-delete]').addEventListener('click', async () => done(await el.editProperty({ op: 'delete', property: id }), () => {}));
    node.querySelector('[data-col-add]').addEventListener('click', () => addForm(el, node, id, back));
  }, 'dv-colmenu');
}

/** Add a property from a table with no column to open a menu on (CONTRACT §40). */
export function openColumnAdd(el, anchor) {
  el.closeMenu();
  el._pop(anchor, '', (node) => addForm(el, node, null, () => {}), 'dv-colmenu');
}

/** The menu's second page: a name and a type. */
function addForm(el, node, after, back) {
  node.innerHTML = `<form class="dv-col-form" data-col-addform>
      <label>Name <input name="name" autocomplete="off" aria-label="New property's name"></label>
      <label>Type <select name="kind" aria-label="New property's type">${kindOptions('text')}</select></label>
      <div class="dv-col-acts"><button type="submit" class="dv-btn dv-primary">Add</button></div>
    </form>
    <p class="dv-col-msg" data-col-msg role="alert"></p>`;
  const form = node.querySelector('[data-col-addform]');
  form.querySelector('[name="name"]').focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await el.editProperty({ op: 'add', label: form.querySelector('[name="name"]').value.trim(), kind: form.querySelector('[name="kind"]').value, after });
    if (!res.ok) { node.querySelector('[data-col-msg]').textContent = res.reason; return; }
    el.closeMenu();
    if (el._plugin && el._plugin.focusColumn) el._plugin.focusColumn(res.property);
    else back();
  });
}
