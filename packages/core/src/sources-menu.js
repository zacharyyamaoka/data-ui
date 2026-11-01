/* "Where this value comes from": a right-click (or long-press, or Shift+F10) popover for anything that carries
   `data-provenance` (docs/CONTRACT.md §22).

     <script type="module" src="vendor/data-ui/sources.js"></script>        auto-attaches to the document
     <html data-sources-menu="off">                                         opts a page out of the auto-attach

   The attribute holds JSON: {value, unit, basis, source, sourceUrl, sourcePage, asOf, record, note}, every key
   optional. valueHtml writes it on a rich cell's `.dv-value`; a host writes it on a photo, a file link, a figure.
   Shift + right-click always gives the browser's own menu. Everything is drawn with DOM text, never innerHTML, and
   only http(s) addresses become links, so a provenance object from a data file cannot inject markup or script. */

import { BASIS, isLinkTarget } from './format.js';
import css from '../styles/sources.css';

const GUTTER = 8;
const PHONE = 480;
const LONG_PRESS_MS = 550;
const LONG_PRESS_SLOP = 10;
const URL_CHARS = 40;
// robotparts' words for how sure a value is (docs/SPEC.md §9.2): Stated (the maker or seller said it), Measured, Derived
const HUMAN = { datasheet: 'Stated', seller: 'Stated', claimed: 'Stated', measured: 'Measured', derived: 'Derived', estimate: 'Derived' };
// CONTRACT §36, the source popover: a value two or more sources state is marked [data-src-row] by the view that drew it,
// and <data-views> lists every source in its own item menu. This popover leaves that value's right-click and menu keys to
// that menu, and hands it a long-press as a contextmenu at the press (WHY: iOS fires no contextmenu on one, so without
// the hand-over a phone could not open it; a browser that fires its own too still gets one menu, <data-views> keeps it)
const OWNED = '[data-src-row]';
const owned = (n) => !!(n && n.nodeType === 1 && n.closest && n.closest(OWNED));

/** The provenance of an element: its closest [data-provenance], parsed; null when there is none or it is not an object. */
export function provenanceOf(el) {
  const host = el && el.closest ? el.closest('[data-provenance]') : null;
  return host ? parse(host) : null;
}

function parse(host) {
  try {
    const p = JSON.parse(host.getAttribute('data-provenance'));
    return p && typeof p === 'object' && !Array.isArray(p) ? p : null;
  } catch { return null; }
}

const has = (v) => v !== undefined && v !== null && v !== '';
const text = (v) => (has(v) ? String(v) : '');

/** An address safe to put in an href: an http(s) URL or a relative path, query or fragment (format.js isLinkTarget, the
    rule `display: link` follows), resolved against the page. '' otherwise: another scheme, a bare id (a private source,
    a supplier chat, has no address), so its row reads as a plain label (CONTRACT §22). */
function safeUrl(v) {
  if (!has(v) || !isLinkTarget(String(v))) return '';
  try {
    const u = new URL(String(v), document.baseURI);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : '';
  } catch { return ''; }
}

/** The citation text the Copy button writes: `{value}{ unit} — {source}, {sourceUrl}, accessed {asOf}. Record {record}.` */
export function citation(p) {
  const head = text(p.value) ? text(p.value) + (text(p.unit) ? ' ' + text(p.unit) : '') : '';
  const parts = [text(p.source), text(p.sourceUrl), text(p.asOf) ? `accessed ${text(p.asOf)}` : ''].filter(Boolean);
  let out = head;
  if (parts.length) out += (head ? ' — ' : '') + parts.join(', ');
  if (out) out += '.';
  if (text(p.record)) out += (out ? ' ' : '') + `Record ${text(p.record)}.`;
  return out;
}

function daysAgo(asOf) {
  if (!/^\d{4}-\d{2}-\d{2}/.test(asOf)) return '';
  const t = Date.parse(asOf);
  if (Number.isNaN(t)) return '';
  const n = Math.floor((Date.now() - t) / 864e5);
  if (n < 0) return '';
  return n === 0 ? ' (today)' : n === 1 ? ' (1 day ago)' : ` (${n} days ago)`;
}

function shortUrl(href) {
  let s = href;
  try { const u = new URL(href); s = u.host + (u.pathname === '/' && !u.search ? '' : u.pathname + u.search); } catch { /* keep as given */ }
  return s.length > URL_CHARS ? s.slice(0, URL_CHARS - 1) + '…' : s;
}

function el(tag, cls, content) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (content !== undefined) e.textContent = content;
  return e;
}

function link(href, content, extra = {}) {
  const a = el('a', extra.cls, content);
  a.href = href;
  if (extra.blank) { a.target = '_blank'; a.rel = 'noopener'; }
  if (extra.title) a.title = extra.title;
  return a;
}

// one popover at a time, across every attached root
let current = null;

function ensureStyle() {
  if (document.querySelector('style[data-ui-sources]')) return;
  const style = document.createElement('style');
  style.dataset.uiSources = '';
  style.textContent = css;
  document.head.append(style);
}

function legacyCopy(value, restore) {
  const area = document.createElement('textarea');
  area.value = value;
  area.setAttribute('readonly', '');
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
  document.body.append(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { /* blocked */ }
  area.remove();
  if (restore) restore.focus({ preventScroll: true });
  return ok;
}

function build(p) {
  const box = el('div', 'dv-srcmenu');
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-label', 'Where this value comes from');
  box.tabIndex = -1;

  if (has(p.value)) box.append(el('p', 'dv-srcmenu-value', (has(p.text) ? text(p.text) : text(p.value)) + (text(p.unit) ? ' ' + text(p.unit) : '')));

  if (has(p.basis)) {
    const b = BASIS[p.basis];
    const line = el('p', 'dv-srcmenu-basis');
    const word = HUMAN[p.basis];
    if (word) { line.append(el('span', 'dv-srcmenu-word', word), ' · '); }
    if (b) { line.append(el('span', 'dv-srcmenu-mark', b.mark), ` ${b.label} — ${b.means}`); } else line.append(text(p.basis));
    box.append(line);
  }

  const rows = el('dl', 'dv-srcmenu-rows');
  const row = (label, node) => { rows.append(el('dt', '', label)); const dd = el('dd'); dd.append(node); rows.append(dd); };
  const pageUrl = safeUrl(p.sourcePage);
  const sourceUrl = safeUrl(p.sourceUrl);
  if (has(p.source)) row('Source', pageUrl ? link(pageUrl, text(p.source)) : document.createTextNode(text(p.source)));
  if (has(p.sourceUrl)) row('URL', sourceUrl ? link(sourceUrl, shortUrl(sourceUrl), { cls: 'dv-srcmenu-url', blank: true, title: sourceUrl }) : document.createTextNode(text(p.sourceUrl)));
  if (has(p.asOf)) row('Accessed', document.createTextNode(text(p.asOf) + daysAgo(text(p.asOf))));
  if (has(p.record)) row('Record', el('code', '', text(p.record)));
  if (has(p.note)) row('Note', document.createTextNode(text(p.note)));
  if (rows.children.length) box.append(rows);

  const actions = el('div', 'dv-srcmenu-actions');
  if (sourceUrl) actions.append(link(sourceUrl, 'Open URL ↗', { cls: 'dv-srcmenu-act', blank: true }));
  if (pageUrl) actions.append(link(pageUrl, 'Source page', { cls: 'dv-srcmenu-act' }));
  const copy = el('button', 'dv-srcmenu-act', 'Copy citation');
  copy.type = 'button';
  copy.addEventListener('click', async () => {
    const value = citation(p);
    let ok = false;
    try { if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(value); ok = true; } } catch { /* fall back */ }
    if (!ok) ok = legacyCopy(value, copy);
    if (!ok) return;
    copy.textContent = 'Copied';
    clearTimeout(copy._reset);
    copy._reset = setTimeout(() => { copy.textContent = 'Copy citation'; }, 1500);
  });
  actions.append(copy);
  box.append(actions);

  box.append(el('p', 'dv-srcmenu-foot', "Shift + right-click for the browser's menu"));
  return box;
}

function place(box, x, y) {
  const vw = document.documentElement.clientWidth || window.innerWidth;
  const vh = document.documentElement.clientHeight || window.innerHeight;
  if (vw < PHONE) {
    box.style.left = '16px';
    box.style.width = `${vw - 32}px`;
  }
  box.style.maxHeight = `${vh - 2 * GUTTER}px`;
  const r = box.getBoundingClientRect();
  let left = vw < PHONE ? 16 : x;
  if (left + r.width > vw - GUTTER) left = vw - GUTTER - r.width;
  left = Math.max(GUTTER, left);
  let top = y;
  if (top + r.height > vh - GUTTER) top = y - r.height >= GUTTER ? y - r.height : vh - GUTTER - r.height;
  top = Math.max(GUTTER, top);
  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
}

/** Attach the popover to `root` (default the document). `opts.resolve(el) -> provenance | null` supplies provenance for an
    element with no data-provenance of its own. Returns {close, destroy}. */
export function attachSourcesMenu(root = document, opts = {}) {
  ensureStyle();
  const doc = root.ownerDocument || document;
  const lookup = (node) => {
    if (owned(node)) return null;
    const own = provenanceOf(node);
    if (own) return { p: own, host: node.closest('[data-provenance]') };
    const given = opts.resolve && node && node.nodeType === 1 ? opts.resolve(node) : null;
    return given && typeof given === 'object' ? { p: given, host: node } : null;
  };
  const elementOf = (n) => (n && n.nodeType === 1 ? n : n && n.parentElement);
  // keyboard: the closest provenance, else the first descendant that has one
  const around = (node) => {
    const e = elementOf(node);
    if (!e) return null;
    const found = lookup(e);
    if (found) return found;
    const first = e.querySelector ? e.querySelector('[data-provenance]') : null;
    return first ? lookup(first) : null;
  };

  let box = null;
  let returnTo = null;
  let openedAt = 0;
  let openHost = null;
  let keyAt = -1e9;
  let swallowClick = false;
  let press = null;
  const cleanups = [];

  const close = ({ restore = true } = {}) => {
    if (!box) return;
    const back = returnTo;
    box.remove();
    box = null;
    returnTo = null;
    for (const off of cleanups.splice(0)) off();
    if (current === api) current = null;
    if (restore && back && back.isConnected && typeof back.focus === 'function') back.focus({ preventScroll: true });
  };

  const open = (found, x, y, byKeyboard) => {
    if (current && current !== api) current.close({ restore: false });
    close({ restore: false });
    const { p, host } = found;
    returnTo = doc.activeElement && doc.activeElement !== doc.body ? doc.activeElement : null;
    box = build(p);
    doc.body.append(box);
    place(box, x, y);
    current = api;
    openedAt = performance.now();
    openHost = host;
    const on = (target, type, fn, o) => { target.addEventListener(type, fn, o); cleanups.push(() => target.removeEventListener(type, fn, o)); };
    const mine = box;
    on(doc, 'pointerdown', (e) => { if (!mine.contains(e.target)) close({ restore: false }); }, true);
    on(window, 'resize', () => close({ restore: false }));
    on(window, 'scroll', (e) => { if (!(e.target instanceof Node && mine.contains(e.target))) close({ restore: false }); }, true);
    on(mine, 'keydown', (e) => {
      const acts = [...mine.querySelectorAll('.dv-srcmenu-act')];
      const i = acts.indexOf(doc.activeElement);
      let next = -1;
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % acts.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (i - 1 + acts.length) % acts.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = acts.length - 1;
      else if (e.key === 'Tab') next = e.shiftKey ? (i <= 0 ? acts.length - 1 : i - 1) : (i === acts.length - 1 ? 0 : i + 1);
      if (next >= 0) { e.preventDefault(); acts[next].focus({ preventScroll: true }); }
    });
    // Escape also closes it when focus never moved in (a mouse open)
    on(doc, 'keydown', (e) => { if (e.key === 'Escape' && !mine.contains(e.target)) close(); }, true);
    const first = mine.querySelector('.dv-srcmenu-act');
    if (byKeyboard && first) first.focus({ preventScroll: true });
    host.dispatchEvent(new CustomEvent('data-sources-open', { bubbles: true, detail: p }));
  };

  const inside = (node) => root === doc || root.contains(node);

  const onContextMenu = (e) => {
    // a keyboard-opened popover already took this event's keydown; the contextmenu that key press also raises (Shift+F10
    // carries shiftKey, a mouse right-click has button 2) follows within a frame, and is swallowed once
    if (e.button === 0 && performance.now() - keyAt < 150) { keyAt = -1e9; e.preventDefault(); return; }
    if (e.shiftKey) return; // Shift + right-click: the browser's own menu, always
    const found = e.target && e.target.nodeType === 1 ? lookup(e.target) : null;
    if (!found) return;
    e.preventDefault();
    // a touch long-press fires both our timer and the browser's contextmenu: one popover, not two
    if (box && openHost === found.host && performance.now() - openedAt < 700) return;
    open(found, e.clientX, e.clientY, false);
  };

  // WHY compare the selection with its state at the last focus move, not event times: focusin is delivered at once and
  // selectionchange as a later task, so their timestamps can arrive out of order (found at merge: each of the two
  // order checks failed 1 run in 3 to 5). The selection's ends are current at any moment; if they differ from what they
  // were when focus last moved, the selection is the newer act.
  const ends = (s) => (s ? [s.anchorNode, s.anchorOffset, s.focusNode, s.focusOffset] : null);
  let atFocus = null;
  const onFocusIn = () => { atFocus = ends(doc.getSelection ? doc.getSelection() : null); };
  const onKeyDown = (e) => {
    const menuKey = e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey);
    if (!menuKey) return;
    if (box) { e.preventDefault(); return; }
    // WHY whichever came last: selecting text and then pressing the menu key means that text; but a right-click leaves
    // a word selected in Chromium, and tabbing to another element afterwards means that element
    const sel = doc.getSelection ? doc.getSelection() : null;
    const focus = doc.activeElement && doc.activeElement !== doc.body ? doc.activeElement : null;
    const movedSinceFocus = sel && (!atFocus || ends(sel).some((x, i) => x !== atFocus[i]));
    const selected = sel && sel.anchorNode && !sel.isCollapsed && (!focus || movedSinceFocus) ? around(sel.anchorNode) : null;
    let found = selected || (focus ? around(focus) : null);
    if (!found || !inside(found.host)) return;
    e.preventDefault();
    keyAt = performance.now();
    const r = found.host.getBoundingClientRect();
    open(found, r.left, r.bottom + 4, true);
  };

  const cancelPress = () => { if (press) { clearTimeout(press.timer); press = null; } };
  const onPointerDown = (e) => {
    cancelPress();
    if (e.pointerType !== 'touch' && e.pointerType !== 'pen') return;
    if (owned(e.target)) {
      const target = e.target, at = { x: e.clientX, y: e.clientY };
      press = { at, timer: setTimeout(() => {
        press = null;
        swallowClick = true;
        target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, composed: true, clientX: at.x, clientY: at.y, button: 2 }));
      }, LONG_PRESS_MS) };
      return;
    }
    const found = e.target && e.target.nodeType === 1 ? lookup(e.target) : null;
    if (!found) return;
    const at = { x: e.clientX, y: e.clientY };
    press = { at, timer: setTimeout(() => {
      press = null;
      swallowClick = true;
      open(found, at.x, at.y, false);
    }, LONG_PRESS_MS) };
  };
  const onPointerMove = (e) => {
    if (press && Math.hypot(e.clientX - press.at.x, e.clientY - press.at.y) > LONG_PRESS_SLOP) cancelPress();
  };
  const onPointerEnd = () => {
    cancelPress();
    // the click that ends a long-press would follow a link or open a row; it is swallowed once, then forgotten
    if (swallowClick) setTimeout(() => { swallowClick = false; }, 400);
  };
  const onClick = (e) => {
    if (!swallowClick) return;
    swallowClick = false;
    e.preventDefault();
    e.stopPropagation();
  };

  const listen = (target, type, fn, o) => { target.addEventListener(type, fn, o); return () => target.removeEventListener(type, fn, o); };
  const offs = [
    listen(root, 'contextmenu', onContextMenu),
    listen(root, 'keydown', onKeyDown),
    listen(root, 'focusin', onFocusIn),
    listen(root, 'pointerdown', onPointerDown),
    listen(root, 'pointermove', onPointerMove),
    listen(root, 'pointerup', onPointerEnd),
    listen(root, 'pointercancel', onPointerEnd),
    listen(root, 'click', onClick, true),
    listen(window, 'scroll', cancelPress, true),
  ];
  const api = {
    close: () => close(),
    destroy() { close({ restore: false }); cancelPress(); for (const off of offs.splice(0)) off(); },
  };
  return api;
}

// WHY auto-attach: a page that only wants the popover loads this one file and writes no JS. <html data-sources-menu="off"> opts out.
if (typeof document !== 'undefined' && document.documentElement.dataset.sourcesMenu !== 'off') {
  const start = () => attachSourcesMenu(document);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
}
