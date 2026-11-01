/* type: cards — Bases' cards view (cardSize, image, imageFit, imageAspectRatio) on TanStack Virtual's `lanes`.

   Stock: @tanstack/virtual-core (already in the table's bundle, so cards add no library bytes). Ours: the card
   markup and the lane arithmetic. WHY lanes: TanStack Virtual places each card in the shortest lane, so the same
   code does a fixed grid now and masonry (laneAssignmentMode 'measured') when a card's height varies.
   `sketch` is a demo extension: a to-scale side view drawn from two dimension properties, in place of a photo
   robotparts does not host (its product photos are linked, not licensed). */

import { Virtualizer, elementScroll, observeElementOffset, observeElementRect } from '@tanstack/virtual-core';
import { esc, fmt, propLabel } from './shared.mjs';

const GAP = 12;

export default class CardsView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    el.innerHTML = `<div class="du-cards-bar"><label>Card size <input type="range" min="160" max="360" step="10" data-size></label>
      <span class="du-muted" data-count></span></div><div class="du-cards-scroll"><div class="du-cards-inner"></div></div>`;
    this.scroll = el.querySelector('.du-cards-scroll');
    this.inner = el.querySelector('.du-cards-inner');
    this.size = el.querySelector('[data-size]');
    // WHY the slider writes the view, not local state: cardSize is a Bases key, so the change is the .base file's
    this.size.addEventListener('change', () => host.setView({ cardSize: Number(this.size.value) }));
    this.inner.addEventListener('click', (e) => {
      const card = e.target.closest('[data-id]');
      if (card) host.open(card.dataset.id);
    });
    this.virt = new Virtualizer({
      count: 0, getScrollElement: () => this.scroll, estimateSize: () => 200, overscan: 3, lanes: 1,
      scrollToFn: elementScroll, observeElementRect, observeElementOffset, onChange: () => this.draw(),
    });
    this.unmount = this.virt._didMount();
    this.ro = new ResizeObserver(() => this.layout());
    this.ro.observe(this.scroll);
  }

  update(input) {
    this.input = input;
    this.size.value = input.view.cardSize || 200;
    this.el.querySelector('[data-count]').textContent = `${input.rows.length.toLocaleString()} cards`;
    this.extent = sketchExtent(input.rows, input.view.sketch);
    this.layout();
  }

  layout() {
    if (!this.input) return;
    const width = this.scroll.clientWidth - GAP;
    const want = this.input.view.cardSize || 200;
    this.lanes = Math.max(1, Math.floor((width + GAP) / (want + GAP)));
    this.cardW = (width - GAP * (this.lanes - 1)) / this.lanes;
    const shown = (this.input.view.order || []).slice(2, 5).length;
    this.cardH = (this.input.view.sketch ? 96 : 0) + 58 + shown * 20;
    this.virt.setOptions({ ...this.virt.options, count: this.input.rows.length, lanes: this.lanes, estimateSize: () => this.cardH + GAP });
    this.virt._willUpdate();
    this.virt.measure();
    this.draw();
  }

  draw() {
    if (!this.input) return;
    const { rows, view, columns } = this.input;
    this.inner.style.height = `${this.virt.getTotalSize()}px`;
    const [titleProp, subProp, ...rest] = view.order || [];
    const shown = rest.slice(0, 3);
    let html = '';
    for (const it of this.virt.getVirtualItems()) {
      const r = rows[it.index];
      const left = it.lane * (this.cardW + GAP);
      html += `<article class="du-card" data-id="${esc(r.id)}" style="transform:translate(${left}px,${it.start}px);width:${this.cardW}px;height:${this.cardH}px">
        ${view.sketch ? sketchSvg(r, view.sketch, this.extent, this.cardW) : ''}
        <div class="du-card-title" title="${esc(r[titleProp])}">${esc(r[titleProp] ?? '—')}</div>
        <div class="du-card-sub">${esc(r[subProp] ?? '—')}</div>
        ${shown.map((p) => `<div class="du-card-prop"><span>${esc(propLabel(columns, p))}</span><b>${fmt(r[p], columns[p])}</b></div>`).join('')}
      </article>`;
    }
    this.inner.innerHTML = html;
  }

  destroy() {
    this.unmount && this.unmount();
    this.ro.disconnect();
    this.el.innerHTML = '';
  }
}

function sketchExtent(rows, sketch) {
  if (!sketch) return null;
  let d = 0, l = 0;
  for (const r of rows) {
    if (r[sketch.diameter] > 0) d = Math.max(d, r[sketch.diameter]);
    if (r[sketch.length] > 0) l = Math.max(l, r[sketch.length]);
  }
  return { d, l };
}

/** A side view to one scale across every card: length across, diameter up. Missing dimensions say so. */
function sketchSvg(r, sketch, ext, cardW) {
  const d = r[sketch.diameter], l = r[sketch.length];
  const H = 84, W = cardW - 24;
  if (!(d > 0 && l > 0) || !ext || !ext.d || !ext.l) {
    return `<div class="du-sketch du-sketch-none" style="height:${H}px">no published OD × length</div>`;
  }
  // WHY one scale for all cards: a 30 mm servo must look small next to a 120 mm hub motor
  const k = Math.min((W - 8) / ext.l, (H - 8) / ext.d);
  const w = Math.max(2, l * k), h = Math.max(2, d * k);
  const x = (W - w) / 2, y = (H - h) / 2;
  return `<svg class="du-sketch" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${d} mm OD by ${l} mm long, to scale`)}">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${Math.min(4, h / 6)}"/>
    <line x1="${x + w * 0.82}" y1="${y}" x2="${x + w * 0.82}" y2="${y + h}"/>
    <text x="${W - 2}" y="${H - 3}" text-anchor="end">${fmt(d)} × ${fmt(l)} mm</text></svg>`;
}
