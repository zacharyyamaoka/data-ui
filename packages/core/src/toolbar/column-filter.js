/* A column's filter by hand (docs/CONTRACT.md §40), Notion's way: no query to write, a control fitted to the column's type. A select is a
   choice list, a checkbox checked or not, a number or a date a range, words a contains box, and any column can be asked for what is
   empty. In View and Edit alike. It keeps no state: it reads and writes the one all-views filter (sheet.js columnFilter and
   setColumnFilter, the rail's own forms), so its pills, the query box, the rail and the URL all follow. */

import { esc } from '../format.js';
import { kindOf, columnFilter, setColumnFilter, choicesOf } from '../sheet.js';

const CHECKBOX = [[true, 'Checked'], [false, 'Not checked']];

/** Open the filter of property `id` under `anchor`. */
export function openColumnFilter(el, id, anchor) {
  const p = el._model.columns[id];
  if (!p) return;
  const kind = kindOf(p);
  const state = columnFilter(el.filters, id);
  const words = !['number', 'date', 'select', 'checkbox', 'list'].includes(kind);
  const list = kind === 'checkbox' ? CHECKBOX : kind === 'select' || kind === 'list' ? choicesOf(el.data.rows, p).map((v) => [v, p.labels && p.labels[v] !== undefined ? String(p.labels[v]) : String(v)]) : null;
  const ticked = new Set(state.values.map(String));
  const type = kind === 'date' ? 'date' : 'number';
  const body = list
    ? `<div class="dv-filter-values" data-filter-values role="group" aria-label="${esc(p.label)}: values">${list.map(([v, label]) => `<label><input type="checkbox" value="${esc(String(v))}"${ticked.has(String(v)) ? ' checked' : ''}> ${esc(label)}</label>`).join('') || '<p class="dv-hint">No values yet.</p>'}</div>`
    : words ? `<label>Contains <input type="text" data-filter-text value="${esc(state.match === 'contains' && state.values.length ? String(state.values[0]) : '')}" autocomplete="off" aria-label="${esc(p.label)} contains"></label>`
      : `<label>From <input type="${type}" step="any" data-filter-min value="${esc(state.min ?? '')}" aria-label="${esc(p.label)} from"></label><label>To <input type="${type}" step="any" data-filter-max value="${esc(state.max ?? '')}" aria-label="${esc(p.label)} to"></label>`;
  const html = `<form class="dv-col-form" data-filter-form novalidate><h4>Filter: ${esc(p.label)}</h4>${body}
      <label class="dv-filter-empty"><input type="checkbox" data-filter-empty${state.empty ? ' checked' : ''}> Is empty</label>
      <div class="dv-col-acts"><button type="button" class="dv-col-act" data-filter-clear>Clear this filter</button></div></form>`;
  const byText = new Map((list || []).map(([v]) => [String(v), v]));
  el.closeMenu();
  el._pop(anchor, html, (node) => {
    const pop = el.$('.dv-pop');
    pop._back = () => {
      if (anchor && anchor.isConnected && anchor.matches('button')) anchor.focus({ preventScroll: true });
      else if (el._plugin && el._plugin.focusColumn) el._plugin.focusColumn(id);
    };
    const $ = (sel) => node.querySelector(sel);
    const read = () => {
      const number = (box) => { if (!box || box.value === '') return null; return kind === 'number' ? Number(box.value) : box.value; };
      const text = $('[data-filter-text]');
      const values = list ? [...node.querySelectorAll('[data-filter-values] input:checked')].map((i) => byText.get(i.value)) : text && text.value.trim() ? [text.value.trim()] : [];
      return { empty: $('[data-filter-empty]').checked, values, match: words || kind === 'list' ? 'contains' : 'equals', min: number($('[data-filter-min]')), max: number($('[data-filter-max]')) };
    };
    const lockout = () => { for (const i of node.querySelectorAll('input:not([data-filter-empty])')) i.disabled = $('[data-filter-empty]').checked; };
    const apply = () => { el.filters = setColumnFilter(el.filters, id, read()); };
    lockout();
    // WHY on the form: `node` is the one .dv-pop every menu reuses, so a listener on it would outlive this panel and go on writing its
    // column from the next panel's controls
    const form = node.querySelector('[data-filter-form]');
    form.addEventListener('submit', (e) => e.preventDefault());
    form.addEventListener('change', () => { lockout(); apply(); });
    // Enter on a box is done: applied, and shut. WHY by hand: a form of two inputs and no submit button has no implicit submission
    form.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || !e.target.matches('[data-filter-text], [data-filter-min], [data-filter-max]')) return;
      e.preventDefault();
      apply();
      const back = pop._back;
      el.closeMenu();
      if (back) back();
    });
    $('[data-filter-clear]').addEventListener('click', () => {
      el.filters = setColumnFilter(el.filters, id, {});
      const back = pop._back;
      el.closeMenu();
      if (back) back();
    });
  }, 'dv-colmenu dv-colfilter');
}
