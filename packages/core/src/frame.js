/* How a <data-views> sits in its page: the `frame` attribute (docs/CONTRACT.md §12; the look is styles/frame.css).

   Zach, 2026-10-26, on robotparts.dev/actuator/: "I don't like how the table and gallery seem like separate component.
   I think it's caused by the additional border etc. Maybe if borderless would feel smoother? Can you please show 5
   options for how to do this differently? We can support different versions you can choose between."

     boxed   (default) the bordered box with its own scroll: what every page had before this attribute
     flush   no border, no header band; the views keep their own scroll (Notion's inline database, an embedded Base)
     tabs    the view tabs read as the page's own nav, the toolbar a row under them, zebra rows (GitHub repo tabs, Linear)
     sheet   no line at all: a tinted header band and a tinted well behind the cards (Shopify admin's index table)
     page    the page is the table: no box, no inner scroll; the tabs, toolbar and column headers stick while the page
             scrolls the rows (McMaster's product tables, Notion's full-page database)
     bleed   `page`, edge to edge of the host's column, on a tinted header band, zebra rows (Airtable's grid, Linear)
     card    one rounded card as tall as its rows, the bar inside its top, a pager floating under it (Shopify admin's
             index table, Polaris' IndexTable in a Card; CONTRACT §43)

   The first four and `card` are CSS only. `page` and `bleed` move the vertical scroll from the view's own box to the page's
   scroller (the nearest scrolling ancestor, else the window), so this module does four things for them:
     1. scrollOptions(host, own): what a virtualising view passes to its TanStack Virtualizer, so 1,149 rows still draw
        about 40 while the page scrolls them (TanStack's window / scroll-margin virtualizer, the stock part)
     2. the column header stays under the sticky band: a CSS scroll-driven animation (view-timeline on the rows, run
        by the compositor, so it never lags the scroll); a scroll listener does the same where that is unsupported
     3. a wide table keeps its sideways scroll: its own scrollbar would sit at the bottom of a 34,000 px table, so a
        sticky scrollbar at the bottom of the page's viewport drives it (the "floating scrollbar" pattern)
     4. the menus and the side peek stay where the reader is: a menu follows its stuck button, and the peek is pinned
        to the scroller's visible box instead of the top of a table taller than the screen. */

import { viewPlugin } from './registry.js';

export const FRAMES = ['boxed', 'flush', 'tabs', 'sheet', 'page', 'bleed', 'card'];
// the views that scroll a long list, and so hand their scroll to the page; every other view fills the visible height
const LISTS = new Set(['table', 'pivot', 'cards', 'list']);
const PAGE_SCROLL = new Set(['page', 'bleed']);

/** The frame a <data-views> asked for (an unknown value is `boxed`, so a typo never breaks a page). */
export function frameOf(el) {
  const f = (el.getAttribute('frame') || '').trim().toLowerCase();
  return FRAMES.includes(f) ? f : 'boxed';
}

export const pageScrolls = (el) => PAGE_SCROLL.has(frameOf(el));

/** The element that scrolls `el` vertically: its nearest scrolling ancestor, or `window` (the document). */
export function scrollParent(el) {
  for (let e = el.parentElement; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
    const s = getComputedStyle(e);
    if (/(auto|scroll|overlay)/.test(s.overflowY) && e.scrollHeight >= e.clientHeight) return e;
  }
  return window;
}

/** Where `el`'s top sits in its scroller's content (what TanStack calls the scroll margin). */
export function offsetIn(el, scroller) {
  const top = el.getBoundingClientRect().top;
  if (scroller === window) return top + window.scrollY;
  return top - scroller.getBoundingClientRect().top - scroller.clientTop + scroller.scrollTop;
}

/**
 * Virtualizer options for a view: its own box (`own()`) normally, the page's scroller under a page frame.
 * `lib` is the core's re-export of @tanstack/virtual-core ({elementScroll, observeElementRect, ...}); passed in so a
 * view bundle and the core share one copy.
 */
export function scrollOptions(host, own, lib) {
  const scroller = host.scroller;
  if (scroller === window) {
    return { getScrollElement: () => window, scrollToFn: lib.windowScroll, observeElementRect: lib.observeWindowRect,
      observeElementOffset: lib.observeWindowOffset, initialOffset: () => window.scrollY };
  }
  return { getScrollElement: () => scroller || own(), scrollToFn: lib.elementScroll, observeElementRect: lib.observeElementRect,
    observeElementOffset: lib.observeElementOffset };
}

/**
 * Keep a virtualizer's scroll margin equal to where its first item sits: under a page frame that is the list's offset
 * in the page (it moves when the intro wraps, a notice shows or the band grows); otherwise `fallback` (a table's
 * header height, a grid's 0). Returns true when it changed. Cheap enough to call on every draw.
 */
export function syncMargin(host, virt, listEl, fallback = 0) {
  const scroller = host.scroller;
  const want = scroller ? Math.round(offsetIn(listEl, scroller)) : fallback;
  // WHY a scroll padding under a page frame: keyboard focus scrolls a row to the top of the page's viewport, which the
  // sticky band (and a table's pinned header, `fallback`) covers; the row stops just under them instead
  // (and a host's own sticky header above the scroller, --data-sticky-top: robotparts' and the docs site's)
  const pad = scroller ? Math.round(stickyTop(host.element) + (parseFloat(host.element.style.getPropertyValue('--dv-band-h')) || 0) + fallback) : 0;
  if (virt.options.scrollMargin === want && (virt.options.scrollPaddingStart || 0) === pad) return false;
  virt.setOptions({ ...virt.options, scrollMargin: want, scrollPaddingStart: pad });
  return true;
}

/** The height of a host's own sticky header above the page's scroller (--data-sticky-top, read as --dv-sticky-top). */
const stickyTop = (el) => parseFloat(getComputedStyle(el).getPropertyValue('--dv-sticky-top')) || 0;

/** "Back to the top" for a view (a new preset or sort): its own box, or the page only as far as the view's start. */
export function scrollToStart(host, own) {
  const scroller = host.scroller;
  if (!scroller) { own.scrollTop = 0; return; }
  const el = host.element;
  const band = (parseFloat(getComputedStyle(el).getPropertyValue('--dv-band-h')) || 0) + stickyTop(el);
  const at = offsetIn(el.querySelector('.dv-stage') || el, scroller) - band;
  const now = scroller === window ? window.scrollY : scroller.scrollTop;
  if (now > at) scroller === window ? window.scrollTo(0, at) : (scroller.scrollTop = at);
}

const timelines = typeof CSS !== 'undefined' && CSS.supports && CSS.supports('animation-timeline: view()');

/**
 * Wire a <data-views> for its frame. Called when it starts and whenever `frame` changes; returns a cleanup.
 * Under a non-page frame there is nothing to wire (CSS does it all).
 */
export function mountFrame(el) {
  const frame = frameOf(el);
  el.dataset.frame = frame;
  if (!PAGE_SCROLL.has(frame)) { el.removeAttribute('data-scroll'); return () => {}; }
  el.dataset.scroll = 'page';
  const scroller = scrollParent(el);
  const target = scroller === window ? window : scroller;
  let raf = 0;

  // a custom property written only when it changed (an unchanged write still invalidates style)
  const put = (node, prop, value) => { if (node.style.getPropertyValue(prop) !== value) node.style.setProperty(prop, value); };

  // the band's heights and the scroller's visible box, as custom properties the CSS reads
  // WHY every read before every write (review 2026-10-26 item 7): a read after a write forces a layout, and this ran
  // five of them (offsetHeight, getBoundingClientRect, getComputedStyle, scrollWidth) interleaved with the writes
  const measure = () => {
    // ---- reads
    const head = el.querySelector(':scope > .dv-head');
    const status = el.querySelector(':scope > .dv-status');
    // WHY the bar too: under toolbar="bar" (CONTRACT §15) the band is .dv-bar and .dv-subbar (the pills or the bulk
    // bar) and .dv-head is hidden; --dv-bar-h places the subbar under the stuck bar (styles/toolbar.css)
    const shown = (e) => (e && e.offsetParent !== null ? e.offsetHeight : 0);
    const bh = shown(el.querySelector(':scope > .dv-bar'));
    const hh = shown(head) + bh + shown(el.querySelector(':scope > .dv-subbar'));
    const sh = status ? status.offsetHeight : 0;
    const port = scroller === window ? { top: 0, bottom: innerHeight, right: innerWidth, height: innerHeight }
      : scroller.getBoundingClientRect();
    const portH = scroller === window ? innerHeight : scroller.clientHeight;
    const clientW = document.documentElement.clientWidth;
    // WHY: `top: 0` sticks at the scroller's content edge, so its top padding would show a strip of page above the band
    const padTop = scroller === window ? 0 : parseFloat(getComputedStyle(scroller).paddingTop) || 0;
    const rows = el.querySelector('.dv-scroll');
    const thead = rows && rows.querySelector('thead');
    const rowsH = rows && thead ? rows.offsetHeight : 0;
    const theadH = rows && thead ? thead.offsetHeight : 0;
    const bar = hbarRead(rows);
    const past = pinRead(rows, thead, hh + sh);
    // ---- writes
    put(el, '--dv-bar-h', bh + 'px');
    put(el, '--dv-head-h', hh + 'px');
    put(el, '--dv-band-h', hh + sh + 'px');
    put(el, '--dv-port-top', Math.max(0, port.top) + 'px');
    put(el, '--dv-port-bottom', Math.max(0, innerHeight - port.bottom) + 'px');
    put(el, '--dv-port-right', Math.max(0, clientW - port.right) + 'px');
    put(el, '--dv-port-h', portH + 'px');
    put(el, '--dv-pad-top', padTop + 'px');
    if (rows && thead) {
      put(rows, '--dv-rows-h', rowsH + 'px');
      put(rows, '--dv-thead-h', theadH + 'px');
    }
    hbarWrite(rows, bar);
    pinWrite(thead, past);
  };

  // 2. the column header under the band, where the browser has no scroll-driven animations
  const pinRead = (rows, thead, band) => {
    if (timelines || !thead) return null;
    const stickTop = (scroller === window ? 0 : scroller.getBoundingClientRect().top + scroller.clientTop)
      + (parseFloat(getComputedStyle(el).getPropertyValue('--dv-sticky-top')) || 0) + band;
    const r = rows.getBoundingClientRect();
    return Math.max(0, Math.min(stickTop - r.top, r.height - thead.offsetHeight));
  };
  const pinWrite = (thead, past) => { if (past !== null && thead) thead.style.transform = past ? `translateY(${past}px)` : ''; };
  const pin = () => {
    if (timelines) return;
    const rows = el.querySelector('.dv-scroll');
    const thead = rows && rows.querySelector('thead');
    pinWrite(thead, pinRead(rows, thead, parseFloat(el.style.getPropertyValue('--dv-band-h')) || 0));
  };

  // 3. the sticky sideways scrollbar for a table wider than its column
  const hbarRead = (rows) => {
    if (!rows) return null;
    const bar = el.querySelector('.dv-hbar');
    return { bar: bar && bar.previousElementSibling === rows ? bar : null, stale: bar, width: rows.scrollWidth, wide: rows.scrollWidth > rows.clientWidth + 1,
      left: rows.scrollLeft, barLeft: bar ? bar.scrollLeft : 0 };
  };
  const hbarWrite = (rows, seen) => {
    if (!rows) { const old = el.querySelector('.dv-hbar'); if (old) old.remove(); return; }
    let bar = seen.bar;
    if (!bar) {
      if (seen.stale) seen.stale.remove();
      bar = document.createElement('div');
      bar.className = 'dv-hbar';
      bar.setAttribute('aria-hidden', 'true');
      bar.innerHTML = '<div></div>';
      rows.after(bar);
      let from = null; // WHY a guard: each side's scroll event would otherwise echo the other's forever
      bar.addEventListener('scroll', () => { if (from === 'rows') { from = null; return; } from = 'bar'; rows.scrollLeft = bar.scrollLeft; }, { passive: true });
      rows.addEventListener('scroll', () => { if (from === 'bar') { from = null; return; } from = 'rows'; bar.scrollLeft = rows.scrollLeft; }, { passive: true });
    }
    if (bar.hidden !== !seen.wide) bar.hidden = !seen.wide;
    if (bar.firstElementChild.style.width !== seen.width + 'px') bar.firstElementChild.style.width = seen.width + 'px';
    if (seen.wide && (bar !== seen.bar || seen.barLeft !== seen.left)) bar.scrollLeft = seen.left;
  };

  // 4. a menu follows its stuck button while the page scrolls under it
  const pop = el.querySelector(':scope > .dv-pop');
  let popAt = null;
  const popWatch = new MutationObserver(() => {
    popAt = pop.hidden ? null : pop.getBoundingClientRect().top;
  });
  if (pop) popWatch.observe(pop, { attributes: true, attributeFilter: ['hidden', 'style'] });
  const follow = () => {
    if (popAt === null || pop.hidden) return;
    const want = popAt - el.getBoundingClientRect().top;
    popWatch.disconnect();
    pop.style.top = want + 'px';
    popWatch.observe(pop, { attributes: true, attributeFilter: ['hidden', 'style'] });
  };

  // which kind of view is coming (the event fires before its code loads): a list scrolls with the page, the rest fill
  const kind = (type) => el.toggleAttribute('data-fill', !LISTS.has(viewPlugin(type) ? type : 'table'));
  // WHY back to the view's start on a new tab: the old view's height went with it, so the page may now sit far below
  // the new one (a chart after 1,000 rows showed the page's footer); only when the reader is past its start
  let shown = el.origin && el.origin.name;
  let fresh = false;
  const onChange = (e) => {
    kind(e.detail && e.detail.view && e.detail.view.type);
    if (e.detail && e.detail.name !== shown) { shown = e.detail.name; fresh = true; }
  };
  const onRender = () => { if (fresh) { fresh = false; scrollToStart(el.host, null); } };
  el.addEventListener('data-views-change', onChange);
  el.addEventListener('data-views-render', onRender);
  if (el.view) kind(el.view.type);

  const onScroll = () => { follow(); if (!timelines && !raf) raf = requestAnimationFrame(() => { raf = 0; pin(); }); };
  const later = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; measure(); }); };
  // WHY: a host's layout may change who scrolls at a breakpoint (robotparts: the results pane from 768 px, else the
  // window), so a resize that changes the scroller re-makes the frame on the new one
  const onResize = () => { if (scrollParent(el) !== scroller && el._reframe) el._reframe(); else later(); };
  target.addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onResize);
  el.addEventListener('data-views-render', later);
  const ro = new ResizeObserver(later);
  ro.observe(el);
  if (scroller !== window) ro.observe(scroller);
  for (const band of el.querySelectorAll(':scope > :is(.dv-head, .dv-bar, .dv-subbar)')) ro.observe(band);
  measure();
  return () => {
    target.removeEventListener('scroll', onScroll);
    removeEventListener('resize', onResize);
    el.removeEventListener('data-views-render', later);
    el.removeEventListener('data-views-change', onChange);
    el.removeEventListener('data-views-render', onRender);
    el.removeAttribute('data-fill');
    ro.disconnect();
    popWatch.disconnect();
    if (raf) cancelAnimationFrame(raf);
    const bar = el.querySelector('.dv-hbar');
    if (bar) bar.remove();
    const thead = el.querySelector('.dv-scroll thead');
    if (thead) thead.style.transform = '';
    for (const p of ['--dv-head-h', '--dv-bar-h', '--dv-band-h', '--dv-pad-top', '--dv-port-top', '--dv-port-bottom', '--dv-port-right', '--dv-port-h']) el.style.removeProperty(p);
    el.removeAttribute('data-scroll');
  };
}
