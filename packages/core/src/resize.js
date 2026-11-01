/* Resizable side panels: one drag handle on a panel's edge, for the kit's own panels and any host's
   (docs/CONTRACT.md §11).

   WHY on by default (Zach, 2026-10-26, memory feedback_resizable_panels): he always wants resizable, remembered side
   panels, asked for them before, and two releases still shipped fixed ones. So the peek and a <data-facets> rail get a
   handle unless a host opts out with data-resizable="off", and any host element gets one with data-resizable="left|right".

   The handle is a sibling of the panel, absolutely placed on its edge, not a child: a panel is usually its own scroll
   container (the peek, a rail), and a child would scroll away with the content. The width lands in a CSS custom
   property, --data-panel-width, on the panel, so the host's CSS owns the layout (a grid track, a flex basis, a width);
   the kit's own panels read it in styles/resize.css. No stored width means no property: the host's default stands. */

const STEP = 16;
const PREFIX = 'data-ui/panel-width/';
const PROP = '--data-panel-width';
const store = {
  get(key) { try { const v = Number(localStorage.getItem(PREFIX + key)); return v > 0 ? v : null; } catch { return null; } },
  set(key, value) { try { localStorage.setItem(PREFIX + key, String(value)); } catch { /* private window: the width lasts this visit */ } },
  drop(key) { try { localStorage.removeItem(PREFIX + key); } catch { /* nothing stored */ } },
};
const num = (v, fallback) => (v !== undefined && v !== null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : fallback);

/** The parent's content-box width: what a panel beside something shares, and what a stacked (phone) panel fills. */
function room(parent) {
  if (!parent) return 0;
  const s = getComputedStyle(parent);
  return parent.clientWidth - parseFloat(s.paddingLeft || 0) - parseFloat(s.paddingRight || 0);
}

/** Give `el` a drag handle on its `edge` ('left' or 'right'): pointer drag, ←/→ by 16 px, double-click resets, the
    width remembered in localStorage. Options (or the element's data-resizable-min|max|key attributes): min, max (px),
    keep (px the panel's neighbours keep, so a drag never covers them), key (the storage name; default the element's id),
    label (for screen readers). Returns {handle, width, set(px), reset(), destroy()}; a second call returns the same. */
export function makeResizable(el, opts = {}) {
  if (!el || !el.parentElement) return null;
  // WHY a property, not a WeakMap: a page may carry two copies of this module (data-ui.js and resize.js), and one
  // panel must still get one handle
  if (el._dvResize) return el._dvResize;
  const edge = (opts.edge || el.dataset.resizable) === 'left' ? 'left' : 'right';
  const min = num(opts.min ?? el.dataset.resizableMin, 160);
  const max = num(opts.max ?? el.dataset.resizableMax, 640);
  const keep = num(opts.keep, 240);
  const key = opts.key || el.dataset.resizableKey || el.id || el.localName;
  const label = opts.label || el.getAttribute('aria-label') || 'the panel';
  const handle = document.createElement('div');
  handle.className = `dv-splitter dv-splitter-${edge}`;
  handle.tabIndex = 0;
  handle.setAttribute('role', 'separator');
  handle.setAttribute('aria-orientation', 'vertical');
  handle.setAttribute('aria-label', `Resize ${label}`);
  handle.setAttribute('aria-valuemin', String(min));
  handle.title = 'Drag to resize · double-click to reset';
  handle.hidden = true;
  el.after(handle);
  el.classList.add('dv-resizable');

  const width = () => el.getBoundingClientRect().width;
  const limit = (w) => Math.round(Math.max(min, Math.min(max, room(el.parentElement) - keep, w)));
  let frame = 0;
  const place = () => {
    frame = 0;
    if (!el.isConnected || !handle.isConnected) { ctl.destroy(); return; }
    // WHY here: a stored width drawn smaller while the room was short comes back with the room: a page that lays its panel out narrow
    // first (a sheet kept by its host, a window made wider) must not lose what was dragged
    const want = drag ? null : store.get(key);
    if (want && room(el.parentElement) > 0) {
      const fit = limit(want);
      if (fit !== parseFloat(el.style.getPropertyValue(PROP))) { el.style.setProperty(PROP, `${fit}px`); el.classList.add('dv-sized'); }
    }
    const r = el.getBoundingClientRect();
    // WHY hidden when it fills its parent: on a phone the panel stacks above the content, and an edge to drag there
    // would only widen the page sideways
    const off = !r.width || el.hidden || r.width >= room(el.parentElement) - 1;
    handle.hidden = off;
    if (off) return;
    // where (0, 0) of the handle's containing block is, read from the handle itself, so any host layout works
    const was = { x: parseFloat(handle.style.left) || 0, y: parseFloat(handle.style.top) || 0 };
    const h = handle.getBoundingClientRect();
    const half = h.width / 2;
    handle.style.left = `${(edge === 'right' ? r.right : r.left) - (h.left - was.x) - half}px`;
    handle.style.top = `${r.top - (h.top - was.y)}px`;
    handle.style.height = `${r.height}px`;
    handle.setAttribute('aria-valuenow', String(Math.round(r.width)));
    handle.setAttribute('aria-valuemax', String(Math.max(min, Math.min(max, Math.round(room(el.parentElement) - keep)))));
  };
  const later = () => { if (!frame) frame = requestAnimationFrame(place); };
  const apply = (w) => { el.style.setProperty(PROP, `${w}px`); el.classList.add('dv-sized'); place(); };

  const ctl = {
    handle,
    get width() { return width(); },
    /** Set the width (clamped) and remember it. */
    set(w) { const v = limit(w); store.set(key, v); apply(v); return v; },
    /** Back to the host's default width; the stored one is forgotten. */
    reset() { el.style.removeProperty(PROP); el.classList.remove('dv-sized'); store.drop(key); place(); },
    destroy() {
      observer.disconnect();
      removeEventListener('resize', later);
      document.removeEventListener('scroll', later, { capture: true });
      if (frame) cancelAnimationFrame(frame);
      handle.remove();
      if (el._dvResize === ctl) delete el._dvResize;
    },
  };

  let drag = null;
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    drag = { x: e.clientX, w: width() };
    handle.classList.add('dv-splitter-drag');
    document.documentElement.classList.add('dv-splitting');
  });
  handle.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    apply(limit(edge === 'right' ? drag.w + dx : drag.w - dx));
  });
  const end = () => {
    if (!drag) return;
    drag = null;
    handle.classList.remove('dv-splitter-drag');
    document.documentElement.classList.remove('dv-splitting');
    store.set(key, limit(width()));
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
  handle.addEventListener('lostpointercapture', end);
  handle.addEventListener('dblclick', (e) => { e.preventDefault(); ctl.reset(); });
  handle.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    // the arrow moves the edge: → widens a right-edge panel and narrows a left-edge one
    const out = (e.key === 'ArrowRight') === (edge === 'right');
    ctl.set(width() + (out ? STEP : -STEP));
  });

  // WHY the parent and the page too: a panel moves when the content above it reflows, without changing its own size
  const observer = new ResizeObserver(later);
  for (const target of [el, el.parentElement, document.documentElement]) observer.observe(target);
  addEventListener('resize', later);
  // WHY scroll too, captured on the document: a sticky panel (a docs sidebar, the Examples rail) stays put while the
  // page scrolls under it, so a handle placed in the page's coordinates drifts away from its edge; capture also sees
  // a scroll inside any container (scroll events do not bubble). Re-placing is at most once per frame.
  document.addEventListener('scroll', later, { capture: true, passive: true });
  const saved = store.get(key);
  // a stored width larger than today's window is drawn smaller, and kept for the wider one
  if (saved) apply(room(el.parentElement) > 0 ? limit(saved) : Math.round(Math.max(min, Math.min(max, saved))));
  el._dvResize = ctl;
  later();
  return ctl;
}

/** Every [data-resizable="left|right"] under `root` (the document by default) gets its handle. */
export function autoResize(root = document) {
  return [...root.querySelectorAll('[data-resizable="left"], [data-resizable="right"]')].map((el) => makeResizable(el));
}

/** The kit's own panels for one <data-views>: its peek (left edge) and every <data-facets for=its-id> rail (right
    edge), unless the element or an ancestor says data-resizable="off". A rail inside a host's own resizable panel is
    left to that panel. */
export function resizeKit(views) {
  if (views.closest('[data-resizable="off"]')) return [];
  const made = [];
  const peek = views.querySelector(':scope > .dv-peek');
  if (peek) made.push(makeResizable(peek, { edge: 'left', min: 320, max: 1200, keep: 160, key: `peek:${views.id || 'data-views'}`, label: 'the details panel' }));
  if (views.id) {
    for (const rail of document.querySelectorAll(`data-facets[for="${CSS.escape(views.id)}"]`)) {
      if (rail.closest('[data-resizable]')) continue;
      made.push(makeResizable(rail, { edge: 'right', min: 180, max: 560, keep: 320, key: `rail:${views.id}`, label: 'the filters' }));
    }
  }
  return made.filter(Boolean);
}
