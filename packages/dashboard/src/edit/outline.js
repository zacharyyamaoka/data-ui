/* The outline: the dashboard's layout as a tree, in the file's order (Rerun's blueprint panel, Shopify's section tree,
   Grafana's content outline). A row selects its panel; dragged, it reorders; dropped onto another row, the two become one
   panel of tabs. The eye hides a panel: its row stays, greyed, where it is. It draws from the session's text, as the
   canvas does, so a change on either side is here at once.

   STOCK PART: Pragmatic drag and drop (Apache-2.0, the kanban's) with its list-item hitbox for reorder-before,
   reorder-after and combine. Keyboard: ↑ / ↓ select, Alt+↑ / Alt+↓ move the selected row. */

import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine';
import { attachInstruction, extractInstruction } from '@atlaskit/pragmatic-drag-and-drop-hitbox/list-item';
import { esc } from '../../../core/src/format.js';
import { panelsOf, movePanel, groupPanels, ungroupPanel, hidePanel } from './ops.js';
import { icon, typeIcon } from './ui.js';

const noteName = (p) => `${String(p.text).replace(/[*_`#\n]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 30)}…`;

function row(p, sel, roving) {
  const kids = p.views.length > 1 ? p.views : [];
  const type = p.views[0] ? p.views[0].type || 'table' : 'text';
  const name = p.text !== null ? noteName(p) : p.name;
  return `<div class="dde-row" role="treeitem" tabindex="${roving ? 0 : -1}" aria-selected="${p.key === sel}" data-key="${esc(p.key)}"${p.hidden ? ' data-hidden' : ''}${kids.length ? ' aria-expanded="true"' : ''}>
      ${icon('grip')}${typeIcon(type)}<span class="dde-tl">${esc(name)}</span>
      <button type="button" class="dde-ra" data-dde-hide tabindex="-1" aria-label="${p.hidden ? 'Show' : 'Hide'} ${esc(name)}" title="${p.hidden ? 'Show it' : 'Hide it: it stays in the file'}">${icon(p.hidden ? 'eyeoff' : 'eye')}</button></div>
    ${kids.length ? `<div role="group" class="dde-kids">${kids.map((v) => `<div class="dde-row dde-kid" role="treeitem" aria-selected="false" data-tab="${esc(v.name)}" data-of="${esc(p.key)}">${typeIcon(v.type || 'table')}<span class="dde-tl">${esc(v.name)}</span>
      <button type="button" class="dde-ra" data-dde-ungroup tabindex="-1" aria-label="Take ${esc(v.name)} out of the tabs" title="Take it out: a panel of its own">${icon('out')}</button></div>`).join('')}</div>` : ''}`;
}

export class Outline {
  constructor(ed, pane) {
    this.ed = ed;
    this.pane = pane;
    this.drags = [];
    this.stop = monitorForElements({ canMonitor: ({ source }) => source.data.dde === 'row', onDrop: ({ source, location }) => this.dropped(source, location) });
    pane.body.addEventListener('click', (e) => this.click(e));
    pane.body.addEventListener('keydown', (e) => this.key(e));
  }

  destroy() { this.stop(); for (const c of this.drags) c(); }

  draw() {
    const { ed, pane } = this;
    for (const c of this.drags) c();
    const had = pane.body.contains(document.activeElement) ? document.activeElement.dataset.key || null : null;
    const scroll = pane.body.scrollTop;
    const panels = panelsOf(ed.s.text);
    const roving = ed.sel && panels.some((p) => p.key === ed.sel) ? ed.sel : panels[0] && panels[0].key;
    pane.body.innerHTML = `<div class="dde-tree" role="tree" aria-label="The dashboard's layout">${panels.map((p) => row(p, ed.sel, p.key === roving)).join('') || '<p class="dde-note">No panels yet: Add one, or place one from the list.</p>'}</div>${ed.queue.html()}`;
    pane.body.scrollTop = scroll;
    this.drags = [...pane.body.querySelectorAll('.dde-row[data-key]')].map((el) => this.wire(el));
    ed.queue.wire(pane.body);
    if (had) { const r = this.rowOf(had); if (r) r.focus(); }
  }

  rowOf(key) { return this.pane.body.querySelector(`.dde-row[data-key="${CSS.escape(key)}"]`); }

  /** Focus the row a keyboard reader is on. */
  focus() {
    const r = (this.ed.sel && this.rowOf(this.ed.sel)) || this.pane.body.querySelector('.dde-row[data-key]');
    if (r) r.focus();
  }

  wire(el) {
    const key = el.dataset.key;
    return combine(
      draggable({ element: el, getInitialData: () => ({ dde: 'row', key }) }),
      dropTargetForElements({
        element: el,
        canDrop: ({ source }) => source.data.dde === 'row' && source.data.key !== key,
        getData: ({ input, element, source }) => attachInstruction({ key }, { input, element, operations: { 'reorder-before': 'available', 'reorder-after': 'available', combine: this.canGroup(source.data.key, key) ? 'available' : 'not-available' } }),
        onDrag: ({ self }) => { const ins = extractInstruction(self.data); el.dataset.drop = ins && !ins.blocked ? ins.operation : ''; },
        onDragLeave: () => { delete el.dataset.drop; },
        onDrop: () => { delete el.dataset.drop; },
      }),
    );
  }

  /** Tabs of one panel read one dataset, and a note or the playback bar is no tab. */
  canGroup(from, to) {
    const a = this.ed.panel(from), b = this.ed.panel(to);
    const ok = (p) => p && p.views.length && p.views[0].type !== 'playback';
    return !!(ok(a) && ok(b) && a.dataset === b.dataset);
  }

  dropped(source, location) {
    const target = location.current.dropTargets[0];
    if (!target) return;
    const ins = extractInstruction(target.data);
    const from = this.ed.panel(source.data.key), to = this.ed.panel(target.data.key);
    if (!ins || ins.blocked || !from || !to) return;
    const { ed } = this;
    if (ins.operation === 'combine') { ed.apply((t) => groupPanels(t, from.i, to.i), 'group'); return; }
    let at = to.i + (ins.operation === 'reorder-after' ? 1 : 0);
    if (from.i < at) at -= 1;
    if (at !== from.i) ed.apply((t) => movePanel(t, from.i, at), 'move');
  }

  click(e) {
    const { ed } = this;
    const hide = e.target.closest('[data-dde-hide]');
    if (hide) { const p = ed.panel(hide.closest('.dde-row').dataset.key); if (p) ed.apply((t) => hidePanel(t, p.i, !p.hidden), 'hide'); return; }
    const out = e.target.closest('[data-dde-ungroup]');
    if (out) { const r = out.closest('.dde-row'); const p = ed.panel(r.dataset.of); if (p) ed.apply((t) => ungroupPanel(t, p.i, r.dataset.tab), 'ungroup'); return; }
    const r = e.target.closest('.dde-row[data-key]');
    if (r) ed.select(r.dataset.key, { reveal: true });
  }

  /** ↑ / ↓ select (focus goes with them), Alt+↑ / Alt+↓ move. The first press with nothing selected selects the row in focus. */
  async key(e) {
    if (!e.target.classList.contains('dde-row') || !['ArrowUp', 'ArrowDown', 'Enter', ' '].includes(e.key)) return;
    e.preventDefault();
    e.stopPropagation();
    const { ed } = this;
    const here = e.target.dataset.key;
    if (e.key === 'Enter' || e.key === ' ') { if (here) ed.select(here, { reveal: true }); return; }
    const rows = [...this.pane.body.querySelectorAll('.dde-row[data-key]')];
    const i = rows.indexOf(e.target);
    const d = e.key === 'ArrowUp' ? -1 : 1;
    if (e.altKey) {
      if (ed.sel !== here) ed.select(here);
      const p = ed.panel(here);
      const to = p && p.i + d;
      if (p && to >= 0 && to < rows.length) await ed.apply((t) => movePanel(t, p.i, to), 'move');
      this.focus();
      return;
    }
    const next = ed.sel ? rows[i + d] : e.target;
    if (next) { ed.select(next.dataset.key, { reveal: true }); this.focus(); }
  }
}
