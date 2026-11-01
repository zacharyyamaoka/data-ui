/* type: kanban — Bases' kanban view (Obsidian 1.14: columns = groupBy, groupOrder, columnWidth, image…) on
   Atlassian's Pragmatic drag and drop, one TanStack Virtual list per column.

   WHY Pragmatic and not SortableJS: Pragmatic only reports what was dropped where; it never moves a DOM node. The
   board redraws from the row model, so a card moves only when the host accepts the edit, and a virtualised
   column (1,147 cards) keeps working. SortableJS moves the node itself, before anyone has said yes.
   Two drags, two kinds of write (docs/VIEWS.md §4):
     a column header -> host.setView({groupOrder})       view config, always allowed, lands in the .base file
     a card          -> host.propose({id, set: {...}})   a data edit; the host decides (derived and read-only
                                                         properties refuse; Obsidian's own board writes the
                                                         note's frontmatter in a transaction) */

import { Virtualizer, elementScroll, observeElementOffset, observeElementRect } from '@tanstack/virtual-core';
import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine';
import { attachClosestEdge, extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge';
import { esc, fmt, propLabel, groupLabel } from './shared.mjs';

const CARD = 74; // px per card slot, gap included

export default class KanbanView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.columns = [];
    this.monitor = monitorForElements({ onDrop: (e) => this.drop(e) });
    el.addEventListener('click', (e) => {
      const card = e.target.closest('[data-id]');
      if (card) host.open(card.dataset.id);
    });
  }

  update(input) {
    this.input = input;
    this.teardown();
    const { view, groups, columns } = input;
    const prop = view.groupBy.property;
    const width = view.columnWidth || 280;
    this.el.innerHTML = `<div class="du-board">${groups.map((g, i) => `
      <section class="du-col" data-col="${i}" style="width:${width}px">
        <header class="du-col-head" data-head="${i}" title="Drag to reorder columns (writes groupOrder)">
          <span>${esc(groupLabel(columns, prop, g.key))}</span><span class="du-count">${g.rows.length.toLocaleString()}</span></header>
        <div class="du-col-scroll"><div class="du-col-inner"></div></div>
      </section>`).join('')}</div>`;
    this.columns = groups.map((g, i) => this.column(g, i));
  }

  column(group, i) {
    const section = this.el.querySelector(`[data-col="${i}"]`);
    const scroll = section.querySelector('.du-col-scroll');
    const inner = section.querySelector('.du-col-inner');
    const col = { group, section, scroll, inner, cards: () => {} };
    col.virt = new Virtualizer({
      count: group.rows.length, getScrollElement: () => scroll, estimateSize: () => CARD, overscan: 6,
      scrollToFn: elementScroll, observeElementRect, observeElementOffset, onChange: () => this.drawColumn(col),
    });
    col.unmount = col.virt._didMount();
    col.virt._willUpdate();
    const key = group.key;
    col.cleanup = combine(
      draggable({ element: section.querySelector('.du-col-head'), getInitialData: () => ({ type: 'column', key }) }),
      dropTargetForElements({
        element: section,
        getData: ({ input, element }) => attachClosestEdge({ type: 'column', key }, { input, element, allowedEdges: ['left', 'right'] }),
        onDrag: ({ self, source }) => { section.dataset.over = source.data.type === 'column' ? extractClosestEdge(self.data) || '' : 'card'; },
        onDragLeave: () => { delete section.dataset.over; },
        onDrop: () => { delete section.dataset.over; },
      }),
    );
    this.drawColumn(col);
    return col;
  }

  drawColumn(col) {
    const { view, columns } = this.input;
    const [titleProp, subProp, ...rest] = view.order || [];
    col.inner.style.height = `${col.virt.getTotalSize()}px`;
    col.cards();
    const regs = [];
    let html = '';
    const items = col.virt.getVirtualItems();
    for (const it of items) {
      const r = col.group.rows[it.index];
      html += `<article class="du-kcard" data-id="${esc(r.id)}" style="transform:translateY(${it.start}px)">
        <div class="du-card-title">${esc(r[titleProp] ?? '—')}</div>
        <div class="du-card-sub">${esc(r[subProp] ?? '—')}${rest.slice(0, 2).map((p) => ` · ${fmt(r[p], columns[p])}`).join('')}</div></article>`;
    }
    col.inner.innerHTML = html;
    for (const card of col.inner.children) {
      const id = card.dataset.id;
      regs.push(draggable({ element: card, getInitialData: () => ({ type: 'card', id, from: col.group.key }) }));
    }
    col.cards = combine(...regs);
  }

  drop({ source, location }) {
    const target = location.current.dropTargets[0];
    if (!target || !this.input) return;
    const { view } = this.input;
    if (source.data.type === 'card') {
      if (JSON.stringify(target.data.key) === JSON.stringify(source.data.from)) return;
      this.host.propose({ id: source.data.id, set: { [view.groupBy.property]: target.data.key } });
    } else if (source.data.type === 'column') {
      const keys = this.input.groups.map((g) => g.key);
      const from = keys.findIndex((k) => JSON.stringify(k) === JSON.stringify(source.data.key));
      let to = keys.findIndex((k) => JSON.stringify(k) === JSON.stringify(target.data.key));
      if (from < 0 || to < 0 || from === to) return;
      const edge = extractClosestEdge(target.data);
      const [moved] = keys.splice(from, 1);
      to = keys.findIndex((k) => JSON.stringify(k) === JSON.stringify(target.data.key));
      keys.splice(edge === 'right' ? to + 1 : to, 0, moved);
      this.host.setView({ groupOrder: keys });
    }
  }

  teardown() {
    for (const c of this.columns) { c.cards(); c.cleanup(); c.unmount && c.unmount(); }
    this.columns = [];
  }

  destroy() {
    this.teardown();
    this.monitor();
    this.el.innerHTML = '';
  }
}
