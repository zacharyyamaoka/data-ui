/* type: cards — Bases' cards view (Obsidian 1.14: cardSize, image, imageFit, imageAspectRatio), and with
   `lightbox: true` the media grid (docs/VIEWS.md: "not a new view: the cards view plus a lightbox").

   STOCK PARTS: @tanstack/virtual-core 3.19.7 (the page's one copy, from @data-ui/core) with `lanes`, so 1,149 cards
   keep a few dozen in the DOM; PhotoSwipe 5.4.4 for the lightbox (zoom, pan, swipe, keyboard). OURS: the card
   markup, the lane arithmetic, group headings inside the lanes, the caption with its source.
   Moved from the views report's demo (docs/views/demo/views/cards.mjs, 112 lines); its `sketch` stays a demo.
   With `selectable` on the element (docs/CONTRACT.md §15) each card has a check (on hover, and on every card once
   one is selected): a check toggles, shift adds the range; ctrl/cmd-click on a card toggles it, shift-click takes the
   range. `maxColumns` caps the lanes however wide the view is.
   Writes back only through the host: setView(Layout menu options), open(id), select(id). How a record opens (`open:`)
   is the host's (host.opener, core src/open.js): this view draws the title link, the marks and expand's grown card, as
   a taller item of its lane.

   The grouped gallery (docs/CONTRACT.md §20): with `sections: true` or `tiles:`, groupBy draws as a section title (H1)
   and subGroupBy as a sub-header (H2), the rows with no second-level value straight under the title; with `tiles:` a
   section holds one tile per sub-category (a value of tiles.property) instead of a card per row, and a tile's click
   filters to its rows through host.setFacet. `switcher:` draws a "Group by" control over `groupings:`. Headings and
   tiles are items of the same virtualiser's lanes, as the group headings always were. */

import { Virtualizer, elementScroll, observeElementOffset, observeElementRect, windowScroll, observeWindowOffset, observeWindowRect, scrollOptions, syncMargin, scrollToStart, cellValue, cellText, linkCell, esc, valueHtml, valueText, mediaUrl, groupLabel, hueOf, isEmpty, sectionsOf, groupFacet, toRail, sourcesAttr } from '@data-ui/core';
import ownCss from './cards.css';

export const css = ownCss;

// PhotoSwipe loads the first time a photo is opened, once per page; its css goes into the document beside ours
let lightboxModule = null;
function loadLightbox() {
  lightboxModule = lightboxModule || import('./lightbox.js').then((mod) => {
    if (typeof document !== 'undefined' && !document.querySelector('style[data-ui-view="cards-lightbox"]')) {
      const style = document.createElement('style');
      style.setAttribute('data-ui-view', 'cards-lightbox');
      style.textContent = mod.css;
      document.head.appendChild(style);
    }
    return mod;
  }).catch((err) => { lightboxModule = null; throw err; });
  return lightboxModule;
}

const GAP = 12;
const HEAD = 34; // px: a group heading
const SECTION = 50; // px: a section title (H1), its 22 px text and the rule under it
const SUBHEAD = 30; // px: a sub-header (H2)
const TILE_TEXT = 44; // px: a tile's label, two lines of 16 px, and its padding
const LINE = 19; // px: one property line
const SWITCHERS = new Set(['tabs', 'segmented', 'dropdown']);
const ORDER = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const VIDEO = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;

/** The cards' settings, shown in the Layout menu (Obsidian's own four, then data-ui's lightbox; the 3D model's two
    only when the data has a `media: mesh` property or the view names one: a photo grid has no use for them). */
export function options(view, columns) {
  const meshy = (view && view.mesh) || Object.values(columns || {}).some((c) => c && c.media === 'mesh');
  return [
    { type: 'property', key: 'image', displayName: 'Image property', none: 'none' },
    { type: 'dropdown', key: 'imageFit', displayName: 'Image fit', default: 'cover', options: { cover: 'cover', contain: 'contain' } },
    { type: 'slider', key: 'imageAspectRatio', displayName: 'Image aspect ratio', min: 0.25, max: 2.5, step: 0.05, default: 1 },
    // WHY default 12 on the slider: unset means no cap; 12 is the slider's top, the nearest it can show to "none"
    { type: 'slider', key: 'maxColumns', displayName: 'Max columns', min: 1, max: 12, step: 1, default: 12, none: 'no cap' },
    { type: 'slider', key: 'cardSize', displayName: 'Card size', min: 50, max: 800, step: 10, default: 200 },
    { type: 'toggle', key: 'lightbox', displayName: 'Open images full screen' },
    ...(meshy ? [
      { type: 'property', key: 'mesh', displayName: '3D model property', none: 'none' },
      { type: 'dropdown', key: 'meshInteract', displayName: '3D model turns on', default: 'hover', options: { hover: 'hover', click: 'click', none: 'never (peek only)' } },
      { type: 'dropdown', key: 'meshBackground', displayName: '3D background', default: 'match', options: { match: 'match the thumbnail', light: 'white', theme: 'theme' } },
    ] : []),
  ];
}

/** "source · accessed date" for a media cell that carries provenance ({value, source, asOf}); '' when it has none. */
export function provenance(cell) {
  if (!cell || typeof cell !== 'object' || Array.isArray(cell)) return '';
  const parts = [];
  if (cell.source) {
    let label = String(cell.source);
    try { label = new URL(label).hostname.replace(/^www\./, ''); } catch { /* a source named in words */ }
    parts.push(/^https?:\/\//.test(cell.source) ? `<a href="${esc(cell.source)}" rel="noopener" target="_blank">${esc(label)}</a>` : esc(label));
  }
  if (cell.asOf) parts.push(`accessed ${esc(String(cell.asOf).slice(0, 10))}`);
  return parts.join(' · ');
}

export default class CardsView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this._nodes = new Map(); // virtual key -> drawn element, so a scroll moves cards instead of re-making them
    this._peekId = null;
    this._sizes = new Map(); // image url -> {w, h}, learnt from the cards' own <img> and from the lightbox
    this._sel = new Set();
    el.innerHTML = '<div class="dv-cards-switch" hidden></div><div class="dv-cards-scroll" tabindex="-1"><div class="dv-cards-inner" role="list"></div></div>';
    this.switchBox = el.querySelector('.dv-cards-switch');
    this.scroll = el.querySelector('.dv-cards-scroll');
    this.inner = el.querySelector('.dv-cards-inner');
    this.virt = new Virtualizer({
      // WHY scrollOptions: under frame="page|bleed" the page scrolls the cards, not this box (core src/frame.js)
      count: 0, ...scrollOptions(host, () => this.scroll, { elementScroll, observeElementRect, observeElementOffset, windowScroll, observeWindowRect, observeWindowOffset }),
      estimateSize: (i) => this._sizeOf(i), overscan: 2, lanes: 1, gap: GAP, onChange: () => this._draw(),
    });
    this._unmount = this.virt._didMount();
    this._ro = new ResizeObserver(() => { if (this.input && this.scroll.clientWidth !== this._width) this._layout(); });
    this._ro.observe(this.scroll);
    this._wire();
  }

  destroy() {
    this._dead = true; // a lightbox still loading never opens on a removed view
    if (this._unmount) this._unmount();
    this._ro.disconnect();
    if (this.pswp) this.pswp.destroy();
    this.el.innerHTML = '';
  }

  /** The element's selection changed: repaint the drawn cards' marks, no redraw. */
  selected(set) {
    this._sel = set || new Set();
    this.el.classList.toggle('dv-cards-selecting', this._selectable && this._sel.size > 0);
    for (const node of this._nodes.values()) {
      if (!node.dataset.id) continue;
      const on = this._sel.has(node.dataset.id);
      node.classList.toggle('dv-sel', on);
      // WHY only when selectable: a dashboard's pick marks a card too (CONTRACT §39), and a plain listitem has no aria-selected
      if (this._selectable) node.setAttribute('aria-selected', String(on));
      const box = node.querySelector('.dv-selbox');
      if (box) box.checked = on;
    }
  }

  peeked(peek) {
    this._peekId = peek ? String(peek.id) : null;
    for (const node of this._nodes.values()) if (node.dataset.id) node.classList.toggle('dv-active', node.dataset.id === this._peekId);
  }

  /** A card grew or shrank (open: expand): its lane is laid out again. */
  openMarks() {
    this._clear();
    this._layout();
  }

  /** Scroll a record's card into view (the peek's ‹ › and ↑/↓). */
  reveal(id) {
    const i = this._items ? this._items.findIndex((it) => it.kind === 'card' && String(it.row.id) === String(id)) : -1;
    if (i >= 0) this.virt.scrollToIndex(i, { align: 'auto' });
  }

  update(input) {
    this.input = input;
    this._op = this.host.opener || null;
    const { view, columns, dataset } = input;
    const order = (view.order && view.order.length ? view.order : [dataset.titleProperty]).filter((p) => columns[p]);
    this._title = order[0] || dataset.titleProperty;
    this._props = order.slice(1).filter((p) => p !== view.image);
    this._image = view.image && columns[view.image] ? view.image : null;
    this._media = view.media && columns[view.media] ? view.media : this._image;
    // WHY the 3D model rides in the image well: the image is its poster, so a card looks the same until it is hovered
    // (docs/CONTRACT.md §23: one shared renderer, at most a few live)
    this._mesh = view.mesh && columns[view.mesh] ? view.mesh : null;
    this._meshInteract = ['hover', 'click', 'none'].includes(view.meshInteract) ? view.meshInteract : 'hover';
    this._meshView = view.meshView && columns[view.meshView] ? view.meshView : null;
    this._meshBg = ['match', 'light', 'theme'].includes(view.meshBackground) ? view.meshBackground : 'match';
    this._fit = view.imageFit === 'contain' ? 'contain' : 'cover';
    this._ratio = Math.min(2.5, Math.max(0.25, Number(view.imageAspectRatio) || 1));
    this._caption = (view.caption || []).filter((p) => columns[p]);
    this._selectable = !!input.selectable;
    this._sel = input.selected || new Set();
    this.el.classList.toggle('dv-cards-selectable', this._selectable);
    this.el.classList.toggle('dv-cards-selecting', this._selectable && this._sel.size > 0);
    // the grouped gallery: sections when asked (or implied by tiles); tiles unless the filter already picks the tiles'
    // property (a tile's drill reached its rows, so the rows are what is drawn)
    this._tiles = view.tiles && typeof view.tiles === 'object' && columns[view.tiles.property] ? view.tiles : null;
    this._sectioned = !!(view.sections || this._tiles);
    const picked = this._tiles ? (toRail(input.filters).facets[this._tiles.property] || {}).values : null;
    this._tileMode = !!(this._sectioned && this._tiles && !(picked && picked.length));
    this._drawSwitcher(view);
    // WHY back to the top on a new preset, sort or grouping: the first cards are the answer the reader just asked for
    // (and in a catalogue, on a new pick in the rail, which leaves other sections)
    const topKey = JSON.stringify([view.name, view.sort, view.groupBy, view.grouping, this._sectioned ? input.filters ?? null : null]);
    if (this._topKey !== undefined && topKey !== this._topKey) scrollToStart(this.host, this.scroll);
    this._topKey = topKey;
    this._slides = null;
    this._clear();
    this._layout();
  }

  // ------------------------------------------------------------------ layout: cards, group headings, lanes
  _layout() {
    const { rows, groups, view } = this.input;
    const width = Math.max(120, this.scroll.clientWidth - 2 * GAP);
    this._width = this.scroll.clientWidth;
    const want = this._tileMode ? Math.min(400, Math.max(40, Number(this._tiles.size) || 120)) : Math.min(800, Math.max(50, Number(view.cardSize) || 200));
    // WHY floor, as Obsidian's grid does: a card is never drawn smaller than the size the view asks for
    const cap = Math.round(Number(view.maxColumns));
    const lanes = Math.max(1, Math.min(cap >= 1 ? cap : Infinity, Math.floor((width + GAP) / (want + GAP))));
    this._lanes = lanes;
    this._cardW = (width - GAP * (lanes - 1)) / lanes;
    // the well sits inside the card's 1 px borders, so its ratio is of the inner width (it read 1.83 for 1.8 at 150 px)
    this._imgH = this._image || this._mesh ? Math.round((this._cardW - 2) * this._ratio) : 0;
    this._cardH = this._imgH + 2 + 16 + 20 + this._props.length * LINE; // borders, body padding, title, one line per property
    // a tile: a picture well (a monogram where there is no picture) over its label and count
    this._tileImgH = Math.round(Math.min(this._cardW, 160) * 0.62);
    this._tileH = this._tileImgH + TILE_TEXT + 2;
    // WHY headings and fillers as items of the lanes: TanStack's lanes put item i in the shortest lane, so a heading
    // repeated once per lane and each group padded to a whole row keep every lane level; group n's cards then start
    // on a fresh row under its heading, and one virtualiser still serves the whole grid
    const items = [];
    const pad = () => { while (items.length % lanes) items.push({ kind: 'fill' }); };
    this._tileList = [];
    // WHY a filler as tall as the row it ends: a tile is not a card's height, and a heading's first copy goes in the
    // shortest lane, so a short filler would put the next heading over the row's last tile
    const level = () => { const last = items[items.length - 1]; while (items.length % lanes) items.push({ kind: 'fill', like: last }); };
    if (groups && this._sectioned) this._sections(items, level, lanes);
    else if (groups) {
      for (const g of groups) {
        pad();
        for (let l = 0; l < lanes; l++) items.push({ kind: 'head', group: g, first: l === 0 });
        for (const r of g.rows) items.push({ kind: 'card', row: r });
        // a named group with no rows still shows (rowmodel.js): its heading, then one line across every lane
        if (!g.rows.length) for (let l = 0; l < lanes; l++) items.push({ kind: 'empty', group: g, first: l === 0 });
      }
    } else for (const r of rows) items.push({ kind: 'card', row: r });
    this._items = items;
    this.virt.setOptions({ ...this.virt.options, count: items.length, lanes, gap: GAP, paddingStart: GAP, paddingEnd: GAP,
      getItemKey: (i) => this._keyOf(i) });
    syncMargin(this.host, this.virt, this.inner, 0);
    this.virt._willUpdate();
    this.virt.measure();
    this._draw();
  }

  /** The grouped gallery's items: per section an H1 (lanes copies, one drawn full width), the rows with no
      second-level value straight under it, then each named sub-group under its H2; tiles or cards inside. WHY a
      section's no-value rows first and unlabelled (Zach, 2026-10-27): "in McMaster you see Fastening & Joining, then
      Fasteners / Adhesives & Tape … But Pipe, Tubing, Hose & Fittings has no other layer of breakdown." */
  _sections(items, pad, lanes) {
    const { groups, columns } = this.input;
    const sections = sectionsOf(groups, columns);
    const many = sections.length > 1;
    const heading = (level, sec, sub, text, count) => { pad(); for (let l = 0; l < lanes; l++) items.push({ kind: 'head', level, sec, sub, text, count, first: l === 0 }); };
    for (const sec of sections) {
      heading(1, sec, null, sec.label, sec.count);
      for (const sub of sec.subs) {
        if (sub.label !== null) heading(2, sec, sub, sub.label, sub.count);
        else pad();
        if (this._tileMode) for (const tile of this._tilesOf(sec, sub, many)) { tile.n = this._tileList.length; this._tileList.push(tile); items.push({ kind: 'tile', tile }); }
        else for (const r of sub.rows) items.push({ kind: 'card', row: r });
      }
      if (!sec.count) for (let l = 0; l < lanes; l++) items.push({ kind: 'empty', group: sec, first: l === 0 });
    }
  }

  /** One (sub)group's tiles: "All <group>" first (`all`), a tile per value of tiles.property with its row count, most
      rows first (then by label), and with `limit` while several sections show, the first N and "Every <property> (M)".
      WHY a tile per sub-category (Zach, 2026-10-27): "I think it's just the Gallery View, but showing headers and
      subheaders." A section a reader has drilled into (the only one left) shows every tile. */
  _tilesOf(sec, sub, many) {
    const { columns } = this.input;
    const t = this._tiles;
    const col = columns[t.property];
    const image = t.image && columns[t.image] ? t.image : this._image;
    const byValue = new Map();
    for (const r of sub.rows) {
      const v = cellValue(r[t.property]);
      for (const x of Array.isArray(v) && v.length ? v : [v]) {
        const k = isEmpty(x) ? null : x;
        const key = JSON.stringify(k);
        if (!byValue.has(key)) byValue.set(key, { kind: 'value', value: k, label: k === null ? groupLabel(columns, t.property, null) : valueText(k, col) || String(k), rows: [] });
        byValue.get(key).rows.push(r);
      }
    }
    const values = [...byValue.values()].sort((a, b) => b.rows.length - a.rows.length || ORDER.compare(a.label, b.label));
    const picture = (rows) => {
      if (!image) return null;
      const r = rows.find((x) => !isEmpty(cellValue(x[image])));
      const v = r ? cellValue(r[image]) : null;
      return r ? mediaUrl(Array.isArray(v) ? v[0] : v, this.input.dataset) : null;
    };
    const link = t.link && columns[t.link] ? t.link : null;
    const out = [];
    const group = sub.label !== null ? sub.label : sec.label;
    // the rows with no second-level value stand for their whole section: "All Plastics" is every plastic (and drills
    // to the section), as a named sub-header's "All Medical" is its own rows
    const whole = sub.label === null ? sec : sub;
    if (t.all) out.push({ kind: 'all', label: `All ${group}`, count: whole.count, sec, sub, src: picture(whole.rows) });
    const limit = Number(t.limit) > 0 && many ? Number(t.limit) : 0;
    for (const v of limit ? values.slice(0, limit) : values) {
      const first = v.rows[0];
      const href = link && !isEmpty(cellValue(first[link])) ? mediaUrl(String(cellValue(first[link])), this.input.dataset) : null;
      out.push({ ...v, count: v.rows.length, sec, sub, src: picture(v.rows), href });
    }
    if (limit && values.length > limit) out.push({ kind: 'every', label: `Every ${col.label}`, count: values.length, sec, sub, src: null });
    return out;
  }

  _keyOf(i) {
    const it = this._items[i];
    if (!it) return i;
    if (it.kind === 'card') return 'c:' + it.row.id;
    if (it.kind === 'head' && it.level) return `h${it.level}:` + JSON.stringify([it.sec.key, it.sub ? it.sub.key : null]) + ':' + (it.first ? 0 : i);
    if (it.kind === 'head') return 'h:' + JSON.stringify(it.group.key) + ':' + (it.first ? 0 : i);
    if (it.kind === 'tile') return 't:' + JSON.stringify([it.tile.sec.key, it.tile.sub.key, it.tile.kind, it.tile.value ?? null]);
    return it.kind + ':' + i;
  }

  _sizeOf(i) {
    const it = this._items && this._items[i];
    if (!it) return this._cardH || 200;
    if (it.kind === 'head') return it.level === 1 ? SECTION : it.level === 2 ? SUBHEAD : HEAD;
    if (it.kind === 'tile') return this._tileH;
    if (it.kind === 'fill' && it.like) return it.like.kind === 'tile' ? this._tileH : it.like.kind === 'card' ? this._cardH + (this._op ? this._op.cardExtra(it.like.row) : 0) : it.like.kind === 'head' ? (it.like.level === 1 ? SECTION : SUBHEAD) : 40;
    if (it.kind === 'empty') return 40;
    // WHY a grown card is a taller item of its lane: TanStack's lanes then stack the cards under it, so the grid stays
    // virtualised and nothing overlaps
    return this._cardH + (this._op ? this._op.cardExtra(it.row) : 0);
  }

  _clear() {
    for (const node of this._nodes.values()) node.remove();
    this._nodes.clear();
  }

  _draw() {
    if (!this._items) return;
    if (this.host.scroller) syncMargin(this.host, this.virt, this.inner, 0);
    const margin = this.virt.options.scrollMargin || 0; // a page frame's offset of the grid in the page; else 0
    this.inner.style.height = `${this.virt.getTotalSize()}px`;
    const live = new Set();
    for (const v of this.virt.getVirtualItems()) {
      const it = this._items[v.index];
      if (!it || it.kind === 'fill' || ((it.kind === 'head' || it.kind === 'empty') && !it.first)) continue;
      const key = String(v.key);
      live.add(key);
      let node = this._nodes.get(key);
      if (!node) {
        node = it.kind === 'card' ? this._card(it.row, v.index) : it.kind === 'tile' ? this._tile(it.tile, v.index) : it.kind === 'head' ? (it.level ? this._heading(it) : this._head(it.group)) : this._empty();
        this._nodes.set(key, node);
        this.inner.append(node);
      }
      const full = it.kind !== 'card' && it.kind !== 'tile';
      const left = full ? GAP : GAP + v.lane * (this._cardW + GAP);
      node.style.transform = `translate(${left}px, ${v.start - margin}px)`;
      node.style.width = `${full ? this._lanes * this._cardW + (this._lanes - 1) * GAP : this._cardW}px`;
      node.style.height = `${v.size}px`;
      node.dataset.i = v.index;
    }
    for (const [key, node] of this._nodes) if (!live.has(key)) { node.remove(); this._nodes.delete(key); }
  }

  _head(group) {
    const { columns } = this.input;
    const node = document.createElement('div');
    node.className = 'dv-cards-head';
    node.setAttribute('role', 'heading');
    node.setAttribute('aria-level', '3');
    node.innerHTML = `<span class="dv-cards-gname">${esc(groupLabel(columns, group.property, group.key))}</span><span class="dv-cards-count">${group.rows.length.toLocaleString()}</span>`;
    return node;
  }

  /** A section title (H1, aria-level 2) or sub-header (H2, aria-level 3), with its row count. The name ends in an
      ellipsis when it cannot fit, its whole text the tooltip. */
  _heading(it) {
    const node = document.createElement('div');
    node.className = it.level === 1 ? 'dv-cards-head dv-cards-sec' : 'dv-cards-head dv-cards-sub';
    node.setAttribute('role', 'heading');
    node.setAttribute('aria-level', String(it.level + 1));
    node.innerHTML = `<span class="dv-cards-gname" title="${esc(it.text)}">${esc(it.text)}</span><span class="dv-cards-count">${it.count.toLocaleString()}</span>`;
    return node;
  }

  /** A tile: a link when `tiles.link` gives its value a page, else a button that drills (host.setFacet). */
  _tile(t, index) {
    const cell = document.createElement('div');
    cell.className = 'dv-cards-cell';
    cell.setAttribute('role', 'listitem');
    const tag = t.href ? 'a' : 'button';
    const well = t.src
      ? `<img src="${esc(t.src)}" alt="" loading="lazy" decoding="async">`
      : `<span class="dv-cards-mono" aria-hidden="true">${t.kind === 'every' ? '⋯' : t.kind === 'all' ? 'All' : esc(initials(t.label))}</span>`;
    cell.innerHTML = `<${tag} class="dv-cards-tile dv-cards-${t.kind}"${t.href ? ` href="${esc(t.href)}"` : ' type="button"'} data-t="${t.n}" data-i="${index}">`
      + `<span class="dv-cards-twell" style="height:${this._tileImgH}px">${well}</span>`
      + `<span class="dv-cards-tbody"><span class="dv-cards-ttext"><span class="dv-cards-tlabel">${esc(t.label)}</span> <span class="dv-cards-tcount">(${t.count.toLocaleString()})</span></span></span></${tag}>`;
    return cell;
  }

  /** A tile's drill: filter to its rows through the host's facet seam (the section's group, a sub-header's group for
      "All …" and "Every …", and the tile's value), so the page shows only those rows. */
  _drill(t) {
    const set = (p, f) => { if (p && f && this.host.setFacet) this.host.setFacet(p, f); };
    const { columns } = this.input;
    set(t.sec.property, groupFacet(columns, t.sec.property, t.sec.key));
    if (t.kind !== 'value' && t.sub.label !== null) set(t.sub.property, groupFacet(columns, t.sub.property, t.sub.key));
    if (t.kind === 'value' && t.value !== null) set(this._tiles.property, groupFacet(columns, this._tiles.property, t.value));
  }

  /** "Group by": one entry per `groupings` item, for a page that draws no switcher of its own; it only calls
      host.setView({grouping}). */
  _drawSwitcher(view) {
    const box = this.switchBox;
    const list = (Array.isArray(view.groupings) ? view.groupings : []).filter((g) => g && g.id);
    const kind = SWITCHERS.has(view.switcher) ? view.switcher : null;
    if (!kind || !list.length) { box.hidden = true; box.innerHTML = ''; return; }
    const cur = view.grouping;
    const name = (g) => esc(g.label || g.id);
    const id = `dv-cards-switch-${(this._uid = this._uid || Math.random().toString(36).slice(2, 8))}`;
    const label = `<span class="dv-cards-switch-label" id="${id}">Group by</span>`;
    let html;
    if (kind === 'dropdown') html = `<label class="dv-cards-switch-label">Group by <select data-grouping-select>${cur && list.some((g) => g.id === cur) ? '' : '<option value="" selected>—</option>'}${list.map((g) => `<option value="${esc(g.id)}" data-grouping="${esc(g.id)}"${g.id === cur ? ' selected' : ''}>${name(g)}</option>`).join('')}</select></label>`;
    else if (kind === 'tabs') html = `${label}<div class="dv-cards-tabs" role="tablist" aria-labelledby="${id}">${list.map((g) => `<button type="button" role="tab" aria-selected="${g.id === cur}" data-grouping="${esc(g.id)}">${name(g)}</button>`).join('')}</div>`;
    else html = `${label}<div class="dv-cards-seg" role="group" aria-labelledby="${id}">${list.map((g) => `<button type="button" aria-pressed="${g.id === cur}" data-grouping="${esc(g.id)}">${name(g)}</button>`).join('')}</div>`;
    const focus = box.contains(document.activeElement) ? document.activeElement.dataset.grouping : null;
    box.innerHTML = html;
    box.hidden = false;
    if (focus) { const again = box.querySelector(`[data-grouping="${CSS.escape(focus)}"]`); if (again && again.tagName === 'BUTTON') again.focus(); }
  }

  _empty() {
    const node = document.createElement('div');
    node.className = 'dv-cards-empty';
    node.textContent = 'No cards in this group.';
    return node;
  }

  _card(r, index) {
    const { columns, view } = this.input;
    const node = document.createElement('article');
    const on = this._sel.has(String(r.id));
    // dv-cards-bare: a selectable card with no image block, whose check sits in the title's row (cards.css)
    node.className = 'dv-cards-card' + (this._peekId === String(r.id) ? ' dv-active' : '') + (on ? ' dv-sel' : '') + (this._selectable && !this._image ? ' dv-cards-bare' : '') + (this._op ? this._op.rowClass(r.id) : '');
    node.dataset.id = r.id;
    node.tabIndex = 0;
    node.setAttribute('role', 'listitem');
    const title = valueText(r[this._title], columns[this._title]) || '—';
    node.setAttribute('aria-label', title);
    let img = '';
    const model = this._mesh ? cellValue(r[this._mesh]) : null;
    if (this._mesh && !isEmpty(model)) {
      const poster = this._image ? cellValue(r[this._image]) : null;
      const url = (x) => mediaUrl(Array.isArray(x) ? x[0] : x, this.input.dataset);
      img = `<div class="dv-cards-img dv-cards-3d" style="height:${this._imgH}px"><data-mesh src="${esc(url(model))}"${isEmpty(poster) ? '' : ` poster="${esc(url(poster))}"`} fit="${this._fit}" interact="${this._meshInteract}" background="${this._meshBg}"${this._meshViewAttr(r)} alt="${esc(title)}"></data-mesh></div>`;
    } else if (this._image) {
      const url = cellValue(r[this._image]);
      const style = `height:${this._imgH}px`;
      if (isEmpty(url)) img = `<div class="dv-cards-img dv-cards-noimg" style="${style}" aria-hidden="true"></div>`;
      else {
        const src = mediaUrl(Array.isArray(url) ? url[0] : url, this.input.dataset);
        const tag = VIDEO.test(src)
          ? `<video src="${esc(src)}" muted playsinline preload="metadata" style="object-fit:${this._fit}"></video>`
          : `<img src="${esc(src)}" alt="" loading="lazy" decoding="async" style="object-fit:${this._fit}">`;
        img = view.lightbox
          ? `<button type="button" class="dv-cards-img dv-cards-zoom" style="${style}" data-zoom aria-label="${esc(`Open ${title} full screen`)}">${tag}</button>`
          : `<div class="dv-cards-img" style="${style}">${tag}</div>`;
      }
    }
    // CONTRACT §36, the source popover: a value two or more sources state marks its line (a right-click on it, or the
    // menu key on the card, lists them); every other line is as it was
    const lines = this._props.map((p) => `<div class="dv-cards-prop"${sourcesAttr(r[p], r.id, p)}><span class="dv-cards-label">${esc(columns[p].label)}</span><span class="dv-cards-value">${this._valueHtml(r, p)}</span></div>`).join('');
    if (this._selectable) node.setAttribute('aria-selected', String(on));
    const check = this._selectable ? `<label class="dv-cards-check"><input type="checkbox" class="dv-selbox" tabindex="-1" aria-label="Select ${esc(title)}"${on ? ' checked' : ''}></label>` : '';
    const op = this._op;
    node.innerHTML = `${check}${img}<div class="dv-cards-body"><div class="dv-cards-title" title="${esc(title)}">${op ? op.titleHtml(r, esc(title)) : esc(title)}</div>${lines}${op ? op.cardMoreHtml(r) : ''}</div>`;
    const im = node.querySelector('img');
    if (im) im.addEventListener('load', () => { if (im.naturalWidth) this._sizes.set(im.currentSrc || im.src, { w: im.naturalWidth, h: im.naturalHeight }); }, { once: true });
    return node;
  }

  /** ` view="…"`: the poster's camera for this row (CONTRACT §23 meshView), or nothing. */
  _meshViewAttr(r) {
    const v = this._meshView ? cellValue(r[this._meshView]) : null;
    return v && typeof v === 'object' ? ` view="${esc(JSON.stringify(v))}"` : typeof v === 'string' && v ? ` view="${esc(v)}"` : '';
  }

  _valueHtml(r, p) {
    const { columns, view } = this.input;
    const col = columns[p];
    const cell = r[p];
    const v = cellValue(cell);
    const display = (view.display && view.display[p]) || col.display;
    if (isEmpty(v)) return valueHtml(cell, col);
    if (display === 'image') return `<img class="dv-cards-inline" src="${esc(mediaUrl(Array.isArray(v) ? v[0] : v, this.input.dataset))}" alt="${esc(col.label)}" loading="lazy">`;
    if (display === 'badge' || col.type === 'list') {
      // WHY one chip: a rich cell's `text` is the producer's display of the whole value (CONTRACT §22)
      const shown = cellText(cell);
      if (shown !== null) return `<span class="dv-badge dv-h${hueOf(shown)}">${esc(shown)}</span>`;
      return (Array.isArray(v) ? v : [v]).map((x) => `<span class="dv-badge dv-h${col.colors && col.colors[x] != null ? col.colors[x] : hueOf(x)}">${esc(valueText(x, col))}</span>`).join(' ');
    }
    if (display === 'link') return linkCell(cell) || esc(String(v));
    return valueHtml(cell, col);
  }

  // ------------------------------------------------------------------ events: open, lightbox, keyboard
  _wire() {
    // WHY on mousedown: a shift-click would otherwise flash a text selection across the cards it spans
    this.inner.addEventListener('mousedown', (e) => { if (this._selectable && e.shiftKey) e.preventDefault(); });
    this.switchBox.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-grouping]');
      if (b && b.dataset.grouping !== (this.input && this.input.view.grouping)) this.host.setView({ grouping: b.dataset.grouping });
    });
    this.switchBox.addEventListener('change', (e) => { if (e.target.matches('[data-grouping-select]') && e.target.value) this.host.setView({ grouping: e.target.value }); });
    this.inner.addEventListener('click', (e) => {
      const tile = e.target.closest('.dv-cards-tile');
      if (tile) {
        // a link tile is the browser's; a button drills
        if (tile.tagName === 'BUTTON') { const t = this._tileList[Number(tile.dataset.t)]; if (t) this._drill(t); }
        return;
      }
      const card = e.target.closest('.dv-cards-card');
      if (!card || e.target.closest('a')) return;
      if (this._selectable) {
        if (e.target.closest('.dv-selbox')) { this.host.select(card.dataset.id, { shift: e.shiftKey, toggle: true }); return; }
        if (e.target.closest('.dv-cards-check')) return;
        if (e.ctrlKey || e.metaKey || e.shiftKey) { this.host.select(card.dataset.id, { shift: e.shiftKey, toggle: e.ctrlKey || e.metaKey }); return; }
      }
      if (e.target.closest('[data-zoom]')) { this.openLightbox(card.dataset.id); return; }
      this.host.open(card.dataset.id);
    });
    this.inner.addEventListener('keydown', (e) => {
      const card = e.target.closest('.dv-cards-card, .dv-cards-tile');
      if (!card) return;
      if (card.classList.contains('dv-cards-card') && e.target === card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); this.host.open(card.dataset.id); return; }
      const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: this._lanes, ArrowUp: -this._lanes }[e.key];
      if (!step) return;
      e.preventDefault();
      this._focusCard(Number(card.dataset.i), step);
    });
  }

  /** Move focus to the next card `step` items away (headings and fillers skipped), scrolling it into view. */
  _focusCard(from, step) {
    let i = from + step;
    while (i >= 0 && i < this._items.length && this._items[i].kind !== 'card' && this._items[i].kind !== 'tile') i += Math.sign(step);
    if (i < 0 || i >= this._items.length) return;
    this.virt.scrollToIndex(i, { align: 'auto' });
    // the next item is usually drawn already: focus it now; else once the scroll has drawn it
    const near = this.inner.querySelector(`.dv-cards-card[data-i="${i}"], .dv-cards-tile[data-i="${i}"]`);
    if (near) { near.focus({ preventScroll: true }); return; }
    requestAnimationFrame(() => {
      const next = this.inner.querySelector(`.dv-cards-card[data-i="${i}"], .dv-cards-tile[data-i="${i}"]`);
      if (next) next.focus({ preventScroll: true });
    });
  }

  /** The lightbox's slides: every row in view order that has a media value. */
  _slideList() {
    if (this._slides) return this._slides;
    const { columns } = this.input;
    const slides = [];
    for (const r of this.input.rows) {
      const cell = r[this._media];
      const url = cellValue(cell);
      if (isEmpty(url)) continue;
      const src = mediaUrl(Array.isArray(url) ? url[0] : url, this.input.dataset);
      const title = valueText(r[this._title], columns[this._title]);
      const extra = this._caption.map((p) => { const t = valueText(r[p], columns[p]); return t && columns[p].unitText ? `${t} ${columns[p].unitText}` : t; }).filter(Boolean);
      const from = provenance(cell);
      const caption = `<b>${esc(title)}</b>${extra.length ? ` · ${extra.map(esc).join(' · ')}` : ''}${from ? `<span class="dv-cards-source">${from}</span>` : ''}`;
      slides.push({ id: String(r.id), src, alt: title, caption, video: VIDEO.test(src) });
    }
    this._slides = slides;
    return slides;
  }

  /** Open the lightbox on a row's image (the media grid: `lightbox: true`). */
  async openLightbox(id) {
    const slides = this._slideList();
    const index = slides.findIndex((s) => s.id === String(id));
    if (index < 0) return;
    // the first open fetches PhotoSwipe: the photo's button says it is busy meanwhile, and a failure is said in the
    // status line (the card stays as it was)
    const button = this.inner.querySelector(`.dv-cards-card[data-id="${CSS.escape(String(id))}"] [data-zoom]`);
    const ticket = (this._lbTicket = (this._lbTicket || 0) + 1);
    let PhotoSwipe;
    try {
      if (button) button.setAttribute('aria-busy', 'true');
      ({ PhotoSwipe } = await loadLightbox());
    } catch (err) {
      if (!this._dead) this.host.setStatus(`<span class="dv-err">The photo viewer did not load: ${esc(err.message)}</span>`);
      return;
    } finally {
      if (button) button.removeAttribute('aria-busy');
    }
    // the view was destroyed, or another photo was asked for, while it loaded
    if (this._dead || ticket !== this._lbTicket) return;
    if (this.pswp) this.pswp.destroy();
    const sizes = this._sizes;
    const pswp = new PhotoSwipe({
      dataSource: slides, index, appendToEl: this.host.element, bgOpacity: 0.96, showHideAnimationType: 'fade',
      closeTitle: 'Close (Esc)', zoomTitle: 'Zoom', arrowPrevTitle: 'Previous', arrowNextTitle: 'Next', errorMsg: 'The image did not load.',
      mainClass: 'dv-cards-pswp',
    });
    // WHY sizes learnt, not required: PhotoSwipe wants each image's size up front and a .base file's data rarely has
    // it; a card's own <img> knows it once loaded, and any other slide is measured as it loads, then redrawn
    pswp.addFilter('itemData', (item, i) => {
      const s = slides[i];
      if (s.video) {
        return { ...item, type: 'html', html: `<div class="dv-cards-video"><video src="${esc(s.src)}" controls autoplay muted loop playsinline></video></div>` };
      }
      const known = sizes.get(s.src);
      if (known) return { ...item, width: known.w, height: known.h };
      const probe = new Image();
      probe.onload = () => {
        sizes.set(s.src, { w: probe.naturalWidth, h: probe.naturalHeight });
        if (this.pswp === pswp) pswp.refreshSlideContent(i);
      };
      probe.src = s.src;
      return { ...item, width: 1600, height: 1200 };
    });
    pswp.on('uiRegister', () => {
      pswp.ui.registerElement({
        name: 'dv-caption', order: 9, isButton: false, appendTo: 'root', html: '',
        onInit: (el) => {
          el.className = 'dv-cards-caption';
          el.setAttribute('aria-live', 'polite');
          const set = () => { const s = slides[pswp.currIndex]; el.innerHTML = s ? s.caption : ''; };
          pswp.on('change', set);
          set();
        },
      });
    });
    pswp.on('destroy', () => {
      if (this.pswp === pswp) this.pswp = null;
      const card = this.inner.querySelector(`.dv-cards-card[data-id="${CSS.escape(slides[pswp.currIndex] ? slides[pswp.currIndex].id : id)}"] [data-zoom]`);
      if (card) card.focus({ preventScroll: true });
    });
    this.pswp = pswp;
    pswp.init();
  }
}

/** A value's monogram for a tile with no picture: two initials ("Pill bottle" -> "PB"). */
function initials(text) {
  const w = String(text).split(/[\s_/-]+/).filter(Boolean);
  return (w.length > 1 ? w[0][0] + w[1][0] : String(text).slice(0, 2)).toUpperCase();
}
