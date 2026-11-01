/* The queue: things waiting to be placed on the dashboard (Zach, 2026-10-29: "Cool idea how you kinda like queue up these
   things to be added to the dashboard"). Kept small on purpose: it reads one file and offers its panels.

   FILLED by Add to dashboard (CONTRACT §34): the host's dashboards() marks one entry `queue: true`, a .base it keeps like any
   other, and the picker adds to it as to any dashboard. WHY a file, and not a list inside this dashboard: a reader
   collects from anywhere, for whichever dashboard they open next, and §34 needs no new word for it.
   DRAINED by a click (after the selected panel, else at the bottom) or a drag onto the grid (before or after the panel
   it lands on: all a reading-order layout can say). An item leaves the file only when the dashboard is saved, so Undo
   and Discard give it back.

   STOCK PART: Pragmatic drag and drop (Apache-2.0, the kanban's) with its closest-edge hitbox. WHY not gridstack's own
   drag-in: GridStack.setupDragIn hung the page under Playwright's mouse in headless Chromium, on a bare page too (the babble
   found it, and this lane measured it again with gridstack 14; not tried by hand). */

import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { attachClosestEdge, extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge';
import { parseBase } from '../../../core/src/base.js';
import { dashboardsHook } from '../../../core/src/add-picker.js';
import { esc } from '../../../core/src/format.js';
import { panelsOf, panelSpec, addPanel, removePanel } from './ops.js';
import { typeIcon, typeName } from './ui.js';

const viewNames = (text) => new Set(((parseBase(text) || {}).views || []).map((v) => v && v.name));

export class Queue {
  constructor(ed) {
    this.ed = ed;
    this.entry = null; // the host's dashboards() entry marked queue: true, with its text and href
    this.items = []; // [{key, name, type, dataset, spec}]
    this.placed = new Map(); // item key → the view's name on this dashboard
    this.drags = [];
    this.drops = [];
    this.stop = monitorForElements({ canMonitor: ({ source }) => source.data.dde === 'queue', onDrop: ({ source, location }) => this.dropped(source, location) });
  }

  destroy() { this.stop(); for (const c of [...this.drags, ...this.drops]) c(); }

  /** Read the queue's file through the host's hook (none, or none marked: an empty queue). */
  async read() {
    const hook = dashboardsHook(this.ed.dash);
    let entry = null;
    if (hook) {
      try { entry = (await hook() || []).find((d) => d && d.queue) || null; } catch { entry = null; }
    }
    if (!entry) { this.entry = null; this.items = []; return; }
    const text = await this.fileText(entry);
    const href = entry.url ? new URL(entry.url, document.baseURI).href : null;
    this.entry = { id: entry.id, title: entry.title, url: entry.url, queue: true, text, href };
    let items = [];
    try { items = panelsOf(text || '').filter((p) => p.views.length).map((p) => ({ key: p.key, name: p.name, type: p.views[0].type || 'table', dataset: p.dataset, spec: panelSpec(text, p.i, { base: href }) })); } catch { items = []; }
    this.items = items;
  }

  async fileText(entry) {
    if (typeof entry.text === 'string') return entry.text;
    if (!entry.url) return null;
    try { const r = await fetch(new URL(entry.url, document.baseURI), { cache: 'no-store' }); return r.ok ? await r.text() : null; } catch { return null; }
  }

  /** The items still waiting: a placed one comes back when Undo takes its view off the draft. */
  waiting() {
    const on = viewNames(this.ed.s.text);
    return this.items.filter((it) => !(this.placed.has(it.key) && on.has(this.placed.get(it.key))));
  }

  html() {
    const items = this.waiting();
    if (!items.length) return '';
    const ds = (it) => { const d = this.ed.dash.dash.datasets[it.dataset]; return (d && d.label) || it.dataset || ''; };
    return `<section class="dde-queue" aria-label="To place">
      <h4>To place <span>${items.length}</span></h4>
      ${items.map((it) => `<div class="dde-q" role="button" tabindex="0" data-item="${esc(it.key)}" title="Click to place it after the selected panel, or drag it onto the grid">${typeIcon(it.type)}<span class="dde-tl">${esc(it.name)}</span><small>${esc(typeName(it.type))}${ds(it) ? ` · ${esc(ds(it))}` : ''}</small></div>`).join('')}
    </section>`;
  }

  /** The rows just drawn: each one drags, and a click or Enter places it. */
  wire(root) {
    for (const c of this.drags) c();
    this.drags = [...root.querySelectorAll('.dde-q')].map((el) => draggable({ element: el, getInitialData: () => ({ dde: 'queue', key: el.dataset.item }) }));
    root.querySelectorAll('.dde-q').forEach((el) => {
      const it = () => this.items.find((x) => x.key === el.dataset.item);
      el.addEventListener('click', () => { if (it()) this.place(it()); });
      el.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && it()) { e.preventDefault(); this.place(it()); } });
    });
  }

  /** Every panel on the grid takes a drop on its edges, and the grid's gaps at the end. */
  targets() {
    for (const c of this.drops) c();
    const dash = this.ed.dash;
    this.drops = [...dash.querySelectorAll('.dd-panel')].map((sec) => dropTargetForElements({
      element: sec,
      canDrop: ({ source }) => source.data.dde === 'queue',
      getData: ({ input, element }) => attachClosestEdge({ key: sec.dataset.panel }, { input, element, allowedEdges: ['top', 'bottom', 'left', 'right'] }),
      onDrag: ({ self }) => { sec.dataset.ddeDrop = extractClosestEdge(self.data) || ''; },
      onDragLeave: () => { delete sec.dataset.ddeDrop; },
      onDrop: () => { delete sec.dataset.ddeDrop; },
    }));
    const grid = dash.querySelector('.dd-grid');
    if (grid) this.drops.push(dropTargetForElements({ element: grid, canDrop: ({ source }) => source.data.dde === 'queue', getData: () => ({ grid: true }) }));
  }

  dropped(source, location) {
    const it = this.items.find((x) => x.key === source.data.key);
    const target = location.current.dropTargets[0];
    if (!it || !target) return;
    if (target.data.grid) { this.place(it, -1); return; }
    const p = this.ed.panel(target.data.key);
    if (!p) return;
    const edge = extractClosestEdge(target.data);
    this.place(it, p.i + (edge === 'bottom' || edge === 'right' ? 1 : 0));
  }

  /** Put an item on the dashboard: at list index `at`, -1 the bottom, null right after the selected panel or the bottom. */
  place(it, at = null) {
    const { ed } = this;
    const sel = at === null && ed.sel ? ed.panel(ed.sel) : null;
    const spot = sel ? sel.i + 1 : at === null || at < 0 ? null : at;
    const before = viewNames(ed.s.text);
    return ed.addSelecting((t) => {
      const next = addPanel(t, it.spec, { base: ed.s.url, at: spot });
      this.placed.set(it.key, [...viewNames(next)].find((n) => !before.has(n)));
      return next;
    }, 'place');
  }

  /** After a save: the items placed leave the queue's file, read again first, so what was added meanwhile stays. */
  async drain() {
    const on = viewNames(this.ed.s.text);
    const out = [...this.placed].filter(([, name]) => on.has(name)).map(([key]) => key);
    if (!out.length) return null;
    const names = new Map(this.items.map((x) => [x.key, x.name]));
    await this.read();
    if (!this.entry || typeof this.entry.text !== 'string') return null;
    const { text: fresh, ...target } = this.entry;
    let text = fresh;
    for (const key of out) {
      const p = panelsOf(text).find((x) => x.key === key || x.name === names.get(key));
      if (p) text = removePanel(text, p.i);
    }
    const r = text === fresh ? { ok: true } : await this.ed.s.save({ text, target, before: fresh });
    if (r.ok) { this.placed.clear(); await this.read(); }
    return r;
  }
}
