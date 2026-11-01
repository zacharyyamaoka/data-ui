/* type: kanban — Bases' kanban view (Obsidian 1.14: columns = groupBy values in groupOrder, columnWidth, image,
   imageFit, imageAspectRatio) on Atlassian's Pragmatic drag and drop, one TanStack Virtual list per column.

   WHY Pragmatic and not SortableJS: Pragmatic only reports what was dropped where; it never moves a DOM node. The
   board redraws from the row model, so a card moves only when the host accepts the edit, and a virtualised column
   keeps working. SortableJS moves the node itself, before anyone has said yes (docs/VIEWS.md, Kanban).
   Two drags, two kinds of write (docs/CONTRACT.md §1):
     a column header -> host.setView({groupOrder})       view config, always allowed; a file host writes the .base
     a card          -> host.propose({id, set: {p: key}}) a data edit; the host decides. A derived or read-only
                                                         group property locks the cards (Vibe Tracks VT-025:
                                                         "derived columns still refuse drops: state is derived,
                                                         never claimed"), and the host refuses it anyway.
   The keyboard does both without a mouse: Alt+←/→ on a card or a header, or the card's ⋯ menu (also the phone's
   way, where HTML drag and drop does not run on touch).
   Moved from the views report's demo (docs/views/demo/views/kanban.mjs, 126 lines). */

import { Virtualizer, elementScroll, observeElementOffset, observeElementRect, cellValue, cellText, esc, valueHtml, valueText, mediaUrl, groupLabel, hueOf, isEmpty } from '@data-ui/core';
import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine';
import { attachClosestEdge, extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge';
import css from './kanban.css';

export { css };

const GAP = 8;  // px between cards
const LINE = 18; // px: one property line
let boards = 0;

/** The board's settings, shown in the Layout menu (Obsidian's kanban options). */
export function options() {
  return [
    { type: 'slider', key: 'columnWidth', displayName: 'Column width', min: 200, max: 500, step: 10, default: 280 },
    { type: 'property', key: 'image', displayName: 'Image property', none: 'none' },
    { type: 'dropdown', key: 'imageFit', displayName: 'Image fit', default: 'cover', options: { cover: 'cover', contain: 'contain' } },
    { type: 'slider', key: 'imageAspectRatio', displayName: 'Image aspect ratio', min: 0.25, max: 2.5, step: 0.05, default: 0.5 },
  ];
}

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export default class KanbanView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.board = `dv-kanban-${++boards}`;
    this.columns = [];
    el.innerHTML = '<div class="dv-kanban-msg" role="status" hidden></div><div class="dv-kanban-board" role="list"></div><div class="dv-kanban-menu" role="menu" hidden></div>';
    this.$board = el.querySelector('.dv-kanban-board');
    this.$msg = el.querySelector('.dv-kanban-msg');
    this.$menu = el.querySelector('.dv-kanban-menu');
    this.monitor = monitorForElements({
      canMonitor: ({ source }) => source.data.board === this.board,
      onDragStart: ({ source }) => { this.el.dataset.dragging = source.data.type; },
      onDrop: (e) => { delete this.el.dataset.dragging; this._drop(e); },
    });
    this._wire();
  }

  destroy() {
    this._teardown();
    this.monitor();
    this.host.setStatus('');
    this.el.innerHTML = '';
  }

  peeked(peek) {
    this._peekId = peek ? String(peek.id) : null;
    for (const card of this.el.querySelectorAll('.dv-kanban-card')) card.classList.toggle('dv-active', card.dataset.id === this._peekId);
  }

  // ------------------------------------------------------------------ the row model -> columns
  update(input) {
    this.input = input;
    const { view, groups, columns, rows, dataset } = input;
    // WHY kept across redraws: an accepted move redraws the board, and the reader must stay where they were
    const scrolls = new Map(this.columns.map((c) => [JSON.stringify(c.group.key ?? null), c.scroll.scrollTop]));
    const left = this.$board.scrollLeft;
    this._teardown();
    this._closeMenu(false);
    const prop = view.groupBy && columns[view.groupBy.property] ? view.groupBy.property : null;
    const meta = prop ? columns[prop] : null;
    this.prop = prop;
    this.lock = !prop ? 'Choose a Group by in Layout to make columns.'
      : meta.derived ? `${meta.label} is derived (${meta.derived}), so cards cannot move between its columns.`
      : meta.readOnly ? `${meta.label} is read-only, so cards cannot move between its columns.` : null;
    this.el.classList.toggle('dv-kanban-locked', !!this.lock);
    this.host.setStatus(this.lock ? `<span class="dv-kanban-lock">${esc(this.lock)}</span>` : '');
    this.groups = groups || [{ key: null, property: null, rows, all: true }];
    const order = (view.order && view.order.length ? view.order : [dataset.titleProperty]).filter((p) => columns[p]);
    this._title = order[0] || dataset.titleProperty;
    this._props = order.slice(1).filter((p) => p !== prop && p !== view.image);
    this._image = view.image && columns[view.image] ? view.image : null;
    this._fit = view.imageFit === 'contain' ? 'contain' : 'cover';
    const width = Math.min(500, Math.max(200, Number(view.columnWidth) || 280));
    const inner = width - 2 * GAP - 2;
    this._imgH = this._image ? Math.round(inner * Math.min(2.5, Math.max(0.25, Number(view.imageAspectRatio) || 0.5))) : 0;
    this._cardH = this._imgH + 2 + 14 + 20 + this._props.length * LINE;
    this.$board.innerHTML = this.groups.map((g, i) => {
      const label = g.all ? 'All rows' : groupLabel(columns, prop, g.key);
      return `<section class="dv-kanban-col" data-col="${i}" style="width:${width}px" role="listitem" aria-label="${esc(`${label}, ${g.rows.length} cards`)}">
        <header class="dv-kanban-head" tabindex="0" title="Drag, or Alt+← / Alt+→, to reorder the columns (writes groupOrder)">
          <span class="dv-kanban-name">${esc(label)}</span><span class="dv-kanban-count">${g.rows.length.toLocaleString()}</span></header>
        <div class="dv-kanban-scroll"><div class="dv-kanban-inner" role="list"></div>${g.rows.length ? '' : '<p class="dv-kanban-empty">No cards</p>'}</div>
      </section>`;
    }).join('');
    this.columns = this.groups.map((g, i) => this._column(g, i));
    for (const c of this.columns) { const top = scrolls.get(JSON.stringify(c.group.key ?? null)); if (top) c.scroll.scrollTop = top; }
    this.$board.scrollLeft = left;
    if (this._focusAfter) { const id = this._focusAfter; this._focusAfter = null; this._focusId(id); }
  }

  _column(group, i) {
    const section = this.$board.querySelector(`[data-col="${i}"]`);
    const scroll = section.querySelector('.dv-kanban-scroll');
    const inner = section.querySelector('.dv-kanban-inner');
    const head = section.querySelector('.dv-kanban-head');
    const col = { group, index: i, section, scroll, inner, head, nodes: new Map() };
    col.virt = new Virtualizer({
      count: group.rows.length, getScrollElement: () => scroll, estimateSize: () => this._cardH, overscan: 4, gap: GAP,
      paddingStart: 2, paddingEnd: GAP, getItemKey: (k) => String(group.rows[k].id),
      scrollToFn: elementScroll, observeElementRect, observeElementOffset, onChange: () => this._drawColumn(col),
    });
    col.unmount = col.virt._didMount();
    col.virt._willUpdate();
    const key = group.key;
    const board = this.board;
    col.cleanup = combine(
      draggable({ element: head, getInitialData: () => ({ board, type: 'column', key }) }),
      dropTargetForElements({
        element: section,
        canDrop: ({ source }) => source.data.board === board && (source.data.type === 'column' || !this.lock),
        getData: ({ input, element }) => attachClosestEdge({ type: 'column', key }, { input, element, allowedEdges: ['left', 'right'] }),
        onDrag: ({ self, source }) => {
          const over = source.data.type === 'column' ? (same(source.data.key, key) ? '' : extractClosestEdge(self.data) || '') : same(source.data.from, key) ? '' : 'card';
          if (section.dataset.over !== over) section.dataset.over = over;
        },
        onDragLeave: () => { delete section.dataset.over; },
        onDrop: () => { delete section.dataset.over; },
      }),
    );
    this._drawColumn(col);
    return col;
  }

  _drawColumn(col) {
    col.inner.style.height = `${col.virt.getTotalSize()}px`;
    const live = new Set();
    for (const v of col.virt.getVirtualItems()) {
      const r = col.group.rows[v.index];
      if (!r) continue;
      const key = String(r.id);
      live.add(key);
      let node = col.nodes.get(key);
      if (!node) {
        node = this._card(r, col);
        col.nodes.set(key, node);
        col.inner.append(node);
      }
      node.style.transform = `translateY(${v.start}px)`;
      node.style.height = `${this._cardH}px`;
      node.dataset.i = v.index;
    }
    for (const [key, node] of col.nodes) if (!live.has(key)) { node._dnd(); node.remove(); col.nodes.delete(key); }
  }

  _card(r, col) {
    const { columns } = this.input;
    const node = document.createElement('article');
    node.className = 'dv-kanban-card' + (this._peekId === String(r.id) ? ' dv-active' : '');
    node.dataset.id = r.id;
    node.tabIndex = 0;
    node.setAttribute('role', 'listitem');
    const title = valueText(r[this._title], columns[this._title]) || '—';
    node.setAttribute('aria-label', title);
    let img = '';
    if (this._image) {
      const url = cellValue(r[this._image]);
      img = isEmpty(url) ? `<div class="dv-kanban-img dv-kanban-noimg" style="height:${this._imgH}px"></div>`
        : `<div class="dv-kanban-img" style="height:${this._imgH}px"><img src="${esc(mediaUrl(Array.isArray(url) ? url[0] : url, this.input.dataset))}" alt="" loading="lazy" style="object-fit:${this._fit}"></div>`;
    }
    const lines = this._props.map((p) => `<div class="dv-kanban-prop"><span class="dv-kanban-label">${esc(columns[p].label)}</span><span class="dv-kanban-value">${this._valueHtml(r, p)}</span></div>`).join('');
    const move = this.lock ? '' : `<button type="button" class="dv-kanban-move" data-move aria-label="${esc(`Move ${title} to another column`)}" title="Move to… (M)">⋯</button>`;
    node.innerHTML = `${img}<div class="dv-kanban-body"><div class="dv-kanban-title" title="${esc(title)}">${esc(title)}</div>${lines}</div>${move}`;
    const board = this.board;
    const from = col.group.key;
    node._dnd = draggable({
      element: node, canDrag: () => !this.lock,
      getInitialData: () => ({ board, type: 'card', id: String(r.id), from }),
      onDragStart: () => node.classList.add('dv-dragging'),
      onDrop: () => node.classList.remove('dv-dragging'),
    });
    return node;
  }

  _valueHtml(r, p) {
    const { columns, view } = this.input;
    const col = columns[p];
    const cell = r[p];
    const v = cellValue(cell);
    const display = (view.display && view.display[p]) || col.display;
    if (!isEmpty(v) && (display === 'badge' || col.type === 'list')) {
      // WHY one chip: a rich cell's `text` is the producer's display of the whole value (CONTRACT §22)
      const shown = cellText(cell);
      if (shown !== null) return `<span class="dv-badge dv-h${hueOf(shown)}">${esc(shown)}</span>`;
      return (Array.isArray(v) ? v : [v]).map((x) => `<span class="dv-badge dv-h${col.colors && col.colors[x] != null ? col.colors[x] : hueOf(x)}">${esc(valueText(x, col))}</span>`).join(' ');
    }
    return valueHtml(cell, col);
  }

  _teardown() {
    for (const c of this.columns) {
      for (const node of c.nodes.values()) node._dnd();
      c.cleanup();
      if (c.unmount) c.unmount();
    }
    this.columns = [];
  }

  // ------------------------------------------------------------------ the two writes
  _drop({ source, location }) {
    const target = location.current.dropTargets[0];
    if (!target || !this.input) return;
    if (source.data.type === 'card') {
      if (same(target.data.key, source.data.from)) return;
      this.move(source.data.id, target.data.key);
    } else if (source.data.type === 'column') {
      const keys = this.groups.map((g) => g.key ?? null);
      const from = keys.findIndex((k) => same(k, source.data.key));
      if (from < 0 || same(source.data.key, target.data.key)) return;
      const edge = extractClosestEdge(target.data);
      const [moved] = keys.splice(from, 1);
      const to = keys.findIndex((k) => same(k, target.data.key));
      keys.splice(edge === 'right' ? to + 1 : to, 0, moved);
      this.reorder(keys);
    }
  }

  /** Write a new column order: the view's groupOrder (Bases' key; the .base file on a file host). */
  reorder(keys) {
    if (!this.prop) return;
    this.host.setView({ groupOrder: keys });
  }

  /** Propose moving a card to another column: the group property's new value. Drawn only once the host says yes. */
  async move(id, key) {
    const { columns } = this.input;
    const row = this.input.rows.find((r) => String(r.id) === String(id));
    const title = row ? valueText(row[this._title], columns[this._title]) || String(id) : String(id);
    if (this.lock) { this._say(this.lock, true); return { ok: false, reason: this.lock }; }
    const label = groupLabel(columns, this.prop, key);
    this._focusAfter = String(id);
    const result = await this.host.propose({ id: String(id), set: { [this.prop]: key ?? null } });
    if (result && result.ok) this._say(`Moved ${title} to ${label}.`);
    else {
      this._focusAfter = null;
      this._say(`${title} stays put: ${(result && result.reason) || 'the host refused the edit.'}`, true);
      this._focusId(String(id));
    }
    return result;
  }

  _say(text, refused = false) {
    this.$msg.hidden = false;
    this.$msg.classList.toggle('dv-kanban-refused', refused);
    this.$msg.innerHTML = `<span>${esc(text)}</span><button type="button" class="dv-btn dv-x" data-hush aria-label="Dismiss">✕</button>`;
  }

  // ------------------------------------------------------------------ keyboard and the move menu
  _wire() {
    this.el.addEventListener('click', (e) => {
      const t = e.target;
      if (t.closest('[data-hush]')) { this.$msg.hidden = true; return; }
      const choice = t.closest('[data-to]');
      if (choice) { const { id } = this.$menu.dataset; const to = this.groups[Number(choice.dataset.to)]; this._closeMenu(false); if (to) this.move(id, to.key); return; }
      if (!t.closest('.dv-kanban-menu')) this._closeMenu(false);
      const card = t.closest('.dv-kanban-card');
      if (!card) return;
      if (t.closest('[data-move]')) { this._openMenu(card); return; }
      this.host.open(card.dataset.id);
    });
    this.el.addEventListener('keydown', (e) => {
      if (e.target.closest('.dv-kanban-menu')) { this._menuKey(e); return; }
      const head = e.target.closest('.dv-kanban-head');
      if (head && e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        e.preventDefault();
        const i = Number(head.closest('[data-col]').dataset.col);
        const j = i + (e.key === 'ArrowLeft' ? -1 : 1);
        if (j < 0 || j >= this.groups.length) return;
        const keys = this.groups.map((g) => g.key ?? null);
        [keys[i], keys[j]] = [keys[j], keys[i]];
        this._focusHead = j;
        this.reorder(keys);
        requestAnimationFrame(() => { const h = this.$board.querySelector(`[data-col="${this._focusHead}"] .dv-kanban-head`); if (h) h.focus({ preventScroll: true }); });
        return;
      }
      const card = e.target.closest('.dv-kanban-card');
      if (!card || e.target !== card) return;
      const ci = Number(card.closest('[data-col]').dataset.col);
      const i = Number(card.dataset.i);
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.host.open(card.dataset.id); return; }
      if (e.key === 'm' || e.key === 'M' || e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); this._openMenu(card); return; }
      if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        e.preventDefault();
        const to = this.groups[ci + (e.key === 'ArrowLeft' ? -1 : 1)];
        if (to) this.move(card.dataset.id, to.key);
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); this._focusAt(ci, i + (e.key === 'ArrowDown' ? 1 : -1)); return; }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); this._focusAt(ci + (e.key === 'ArrowLeft' ? -1 : 1), i); }
    });
  }

  /** Focus the card at (column, index), clamped, scrolling it into view first. */
  _focusAt(ci, i) {
    const col = this.columns[ci];
    if (!col || !col.group.rows.length) return;
    const k = Math.max(0, Math.min(col.group.rows.length - 1, i));
    col.virt.scrollToIndex(k, { align: 'auto' });
    // WHY by hand, not scrollIntoView: that would scroll the page too, and the board is one element on someone's page
    const b = this.$board, s = col.section;
    if (s.offsetLeft < b.scrollLeft) b.scrollLeft = s.offsetLeft - GAP;
    else if (s.offsetLeft + s.offsetWidth > b.scrollLeft + b.clientWidth) b.scrollLeft = s.offsetLeft + s.offsetWidth - b.clientWidth + GAP;
    requestAnimationFrame(() => { const card = col.inner.querySelector(`.dv-kanban-card[data-i="${k}"]`); if (card) card.focus({ preventScroll: true }); });
  }

  _focusId(id) {
    for (const col of this.columns) {
      const k = col.group.rows.findIndex((r) => String(r.id) === id);
      if (k >= 0) { this._focusAt(col.index, k); return; }
    }
  }

  _openMenu(card) {
    if (this.lock) { this._say(this.lock, true); return; }
    const ci = Number(card.closest('[data-col]').dataset.col);
    const { columns } = this.input;
    this.$menu.dataset.id = card.dataset.id;
    this.$menu.innerHTML = `<p class="dv-kanban-menuhead">Move to</p>${this.groups.map((g, j) => `<button type="button" role="menuitem" data-to="${j}"${j === ci ? ' disabled aria-disabled="true"' : ''}>${esc(groupLabel(columns, this.prop, g.key))}<span class="dv-kanban-count">${g.rows.length.toLocaleString()}</span></button>`).join('')}`;
    this.$menu.hidden = false;
    const box = this.el.getBoundingClientRect();
    const at = card.getBoundingClientRect();
    const w = this.$menu.offsetWidth, h = this.$menu.offsetHeight;
    this.$menu.style.left = `${Math.max(8, Math.min(at.right - box.left - w, box.width - w - 8))}px`;
    this.$menu.style.top = `${Math.max(8, Math.min(at.top - box.top + 24, box.height - h - 8))}px`;
    this._menuFrom = card.dataset.id;
    const first = this.$menu.querySelector('button:not([disabled])');
    if (first) first.focus({ preventScroll: true });
  }

  _closeMenu(refocus = true) {
    if (this.$menu.hidden) return;
    this.$menu.hidden = true;
    if (refocus && this._menuFrom) this._focusId(this._menuFrom);
    this._menuFrom = null;
  }

  _menuKey(e) {
    const items = [...this.$menu.querySelectorAll('button:not([disabled])')];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this._closeMenu(true); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const n = items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]; if (n) n.focus(); }
    else if (e.key === 'Tab') this._closeMenu(false);
  }
}
