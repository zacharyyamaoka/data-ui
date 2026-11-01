/* Arrange: drag and resize a dashboard's panels (docs/peps/0005-dashboard-cards.md §6). Loaded only when a reader
   presses Arrange or Edit (dist/dashboard-arrange.js), so a dashboard nobody rearranges never pays for it.

   liveGrid is the one gridstack path. Arrange keeps its arrangement in this browser; the editor (edit/editor.js,
   docs/peps/0017-dashboard-editor.md) comes through the same call and writes the file instead.

   Zach (2026-10-26): "Drag-to-arrange panels with the stock part: gridstack.js … The arrangement writes back to the
   layout: in the .base … A reader's local rearrangement is remembered."
   STOCK PART: gridstack 14.0.0 (MIT, framework-free): the drag, resize, collision and packing. Ours: turning the
   CSS-grid panels into its items and back, and the reading order it writes. */

import { GridStack } from 'gridstack';
import gridCss from 'gridstack/dist/gridstack.min.css';
import { stringifyBase } from '../../core/src/base.js';
import { packPanels, readingOrder, layoutText } from './model.js';

function addCss() {
  if (document.querySelector('style[data-ui-gridstack]')) return;
  const s = document.createElement('style');
  s.dataset.uiGridstack = '';
  s.textContent = `${gridCss}
data-dashboard .dd-grid.grid-stack { display: block; }
data-dashboard .grid-stack-item > .grid-stack-item-content { display: flex; flex-direction: column; gap: 8px; overflow: hidden; inset: calc(var(--dd-gap, 12px) / 2); border-radius: inherit; padding: inherit; background: inherit; }
/* WHY the cell height, not auto: gridstack writes an inline height only for h > 1, and leaves h = 1 to this rule; auto
   collapsed a one-row panel (the Playback bar, a note) to 0 px while arranging */
data-dashboard .dd-grid.grid-stack > .dd-panel.grid-stack-item { padding: 0; height: var(--gs-cell-height); outline: 2px dashed color-mix(in srgb, var(--dv-accent) 55%, transparent); outline-offset: -4px; cursor: grab; }
data-dashboard .grid-stack-item.ui-draggable-dragging { cursor: grabbing; }
data-dashboard .grid-stack-placeholder > .placeholder-content { background: color-mix(in srgb, var(--dv-accent) 14%, transparent); border-radius: 12px; }`;
  document.head.append(s);
}

/** A function that scrolls the window back so `el`'s top is where it is now on screen. WHY: turning the grid into
    gridstack's (and back) lays every panel out again, and for that moment the grid has no height, so a dashboard lower on
    its page jumped to the page's top and the panel being arranged left the screen (found by the Add to dashboard checks,
    CONTRACT §34: Arrange a panel just added at the bottom). */
function keepPlace(el) {
  const top = el.getBoundingClientRect().top;
  return () => { const now = el.getBoundingClientRect().top; if (Math.abs(now - top) >= 1) scrollBy(0, now - top); };
}

/** The dashboard's panels as gridstack's items, and the grid started: `items` [{key, x, y, w, h}] says where each one goes;
    a panel already drawn inside gridstack's box stays in it (moving a <data-views> remakes its plugin, so the editor
    draws them there), one that is not is put in it. `options` are gridstack's, over the dashboard's columns and rows. */
export function liveGrid(dash, items, options = {}) {
  addCss();
  const grid = dash.querySelector('.dd-grid');
  const d = dash.dash;
  grid.classList.add('grid-stack');
  for (const p of items) {
    const sec = grid.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"]`);
    if (!sec) continue;
    if (!sec.querySelector(':scope > .grid-stack-item-content')) {
      const box = document.createElement('div');
      box.className = 'grid-stack-item-content';
      box.append(...sec.childNodes);
      sec.append(box);
    }
    sec.classList.add('grid-stack-item');
    Object.entries({ 'gs-x': p.x, 'gs-y': p.y, 'gs-w': p.w, 'gs-h': p.h, 'gs-id': p.key }).forEach(([k, v]) => sec.setAttribute(k, String(v)));
  }
  const gap = parseFloat(getComputedStyle(dash).getPropertyValue('--dd-gap')) || 12;
  return GridStack.init({ column: d.columns, cellHeight: d.rowHeight + gap, margin: 0, ...options }, grid);
}

/** Turn arranging on or off for one <data-dashboard>. */
export async function arrange(dash, on) {
  addCss();
  const keep = keepPlace(dash);
  const grid = dash.querySelector('.dd-grid');
  const d = dash.dash;
  if (on) {
    const heights = {};
    for (const p of d.panels) {
      const sec = grid.querySelector(`.dd-panel[data-panel="${CSS.escape(p.key)}"]`);
      heights[p.key] = p.h || Math.max(1, Math.ceil((sec ? sec.getBoundingClientRect().height : d.rowHeight) / d.rowHeight));
    }
    const placed = packPanels(d.panels.map((p) => ({ key: p.key, w: p.w, h: heights[p.key] })), d.columns);
    dash._gridstack = liveGrid(dash, placed, { float: false, animate: true, columnOpts: { breakpoints: [{ w: 700, c: 1 }] } });
    dash.dataset.arranging = '';
    keep();
    return;
  }
  const gs = dash._gridstack;
  if (!gs) return;
  const nodes = gs.engine.nodes.map((n) => ({ key: n.id, x: n.x, y: n.y, w: n.w, h: n.h }));
  gs.destroy(false);
  dash._gridstack = null;
  delete dash.dataset.arranging;
  const order = readingOrder(nodes);
  dash.setArrangement(order.map(({ key, w, h }) => ({ key, w, h })));
  // the redrawn panels grow as their views draw: put the page back now, and again once they have
  keep();
  requestAnimationFrame(() => requestAnimationFrame(keep));
  dash.addEventListener('data-views-render', () => requestAnimationFrame(keep), { once: true, capture: true });
  const text = layoutText(dash.baseText || '', dash.base.layout, stringifyBase);
  dash._layoutText = text;
  dash.dispatchEvent(new CustomEvent('data-dashboard-layout', { detail: { layout: dash.base.layout, text } }));
}
