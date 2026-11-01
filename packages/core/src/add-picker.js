/* Add to dashboard (docs/CONTRACT.md §34): the reader's half. The item menu (a right-click, long-press, the ContextMenu
   key or Shift+F10 on a legend's series, a KPI card or a field of the record peek), the picker (the dashboards the host
   offers, "New dashboard…", "At this moment"), and the event that hands the host the new text.

   Prior art, Amazon's "Add to List": your lists, then "Create a List"; the item goes in, and the page says where it went.
   Zach, 2026-10-29: "like the amazon thing of adding to a saved list"; the item goes to the bottom, arranged later.

   The host's half, all optional:
     dashboards()   a function on the element or any ancestor (a <data-dashboard>, <body>, <html>) that resolves
                    [{id, title, url?, text?}]: url is where the dashboard's .base is read from (and its data paths are
                    written relative to); text, when the host holds it already
     the event      `data-add-to-dashboard` (bubbles, composed, cancelable), detail {dashboard: {id, title, url, new},
                    panel, text, respondWith(promise)}. A host that saves calls respondWith with a promise of the save
                    while the event is dispatched; it resolves (anything, or {ok: true, title?, href?}) and the picker says
                    "Added to <title>", or rejects / resolves {ok: false, reason} and the picker says why. preventDefault()
                    alone: the host took it over, the picker closes. Neither: the text goes to the clipboard, and it says so.
   WHY respondWith (FetchEvent's): one listener both claims the add and reports how the save went, synchronously during
   dispatch, so the kit knows at once whether anyone is listening (the clipboard fallback) without a timeout.

   The picker outlives a redraw of the view it came from: a host that saved draws the dashboard again (reload(), or
   load() as RobotDx's /dx/ does), which makes every panel's <data-views> anew, so the picker waits off the page for the
   element drawn with the same id, moves into it where it was, and adds through it from then on (releaseAddUi /
   adoptAddUi, called by <data-views> as it leaves and joins the page). WHY (RobotDx PEP 0001 §17.1, ask 4): an add to the
   dashboard on screen lost its "Added to …" with the panel the picker lived in. */

import { esc } from './format.js';
import { appendPanel } from './add-to-dashboard.js';
import { icon } from './toolbar/icons.js';

const GUTTER = 8;
const PHONE = 480;
// ms a picker whose <data-views> left the page waits for one drawn in its place (a dashboard's redraw makes it in the
// same task; a host that replaces the whole dashboard may read its file first), then closes
const REDRAW_WAIT = 2000;
let open = null; // the one item menu or picker open on the page: {node, close, kind, ...}
let waiting = null; // that picker while its <data-views> is off the page: {handle, id, timer}

/** The host's dashboards() hook: on `el` or the nearest ancestor that has one, crossing shadow roots. */
export function dashboardsHook(el) {
  for (let n = el; n; n = n.parentElement || (n.getRootNode && n.getRootNode() !== n && n.getRootNode().host) || null) {
    if (typeof n.dashboards === 'function') return () => n.dashboards();
  }
  return null;
}

/** Close whatever item menu or picker is open (focus goes back where it was when `refocus`). */
export function closeAddUi(refocus = false) { if (open) open.close(refocus); }

/** `el` (a <data-views>) left the page: an item menu in it closes; a picker in it waits, off the page, for the element of
    the same id that a redraw makes (adoptAddUi), and closes if none comes. An element without an id closes it. */
export function releaseAddUi(el) {
  const h = open;
  // WHY its own host only: a view nested in it (a peek section's evidence view) leaves with it and says so itself
  if (!h || !el || h.host !== el || !el.contains(h.node)) return;
  if (h.kind !== 'picker' || !el.id) { h.close(false); return; }
  h.node.remove();
  if (waiting) clearTimeout(waiting.timer);
  waiting = { handle: h, id: el.id, timer: setTimeout(() => { if (waiting && waiting.handle === h) h.close(false); }, REDRAW_WAIT) };
}

/** `el` (a <data-views>) joined the page with its chrome drawn: the picker waiting for an element of its id moves into
    it, where it was, and adds through it from now on; the focus comes back into it when the redraw left it nowhere. */
export function adoptAddUi(el) {
  const w = waiting;
  if (!w || !el || !el.id || el.id !== w.id || !el.isConnected || open !== w.handle) return;
  waiting = null;
  clearTimeout(w.timer);
  const h = w.handle;
  el.append(h.node);
  h.rehost(el);
  h.place();
  const at = document.activeElement;
  if (!at || at === document.body || !at.isConnected) {
    const to = h.lastFocus && h.node.contains(h.lastFocus) && !h.lastFocus.disabled ? h.lastFocus : h.node;
    to.focus({ preventScroll: true });
    if (!h.node.contains(document.activeElement)) h.node.focus({ preventScroll: true });
  }
}

/** The anchor as it is now: an element, a point {x, y}, or a function that finds the element (WHY: a bar redraws its
    buttons, so the Display button a picker opened beside may be a new element a moment later). */
const live = (anchor) => (typeof anchor === 'function' ? anchor() : anchor);

/** Place a fixed box beside `anchor` (an element, a point {x, y}, or a function finding the element) inside the
    viewport, a sheet with 8 px gutters on a phone. */
function place(node, anchorOf) {
  const anchor = live(anchorOf);
  const vw = document.documentElement.clientWidth || innerWidth, vh = innerHeight;
  const phone = vw < PHONE;
  // the element it opened beside left the page (its view was drawn again): it stays where it is, inside the viewport
  const lost = node._placed && anchorOf && (typeof anchorOf === 'function' ? !(anchor && anchor.isConnected) : !!(anchor && anchor.getBoundingClientRect && !anchor.isConnected));
  if (lost) {
    node.style.maxHeight = `${vh - 2 * GUTTER}px`;
    const box = node.getBoundingClientRect();
    node.style.top = `${Math.round(Math.max(GUTTER, Math.min(box.top, vh - GUTTER - box.height)))}px`;
    if (!phone) node.style.left = `${Math.round(Math.max(GUTTER, Math.min(box.left, vw - GUTTER - box.width)))}px`;
    return;
  }
  node._placed = true;
  node.style.maxHeight = `${vh - 2 * GUTTER}px`;
  node.style.left = phone ? `${GUTTER}px` : '';
  node.style.right = phone ? `${GUTTER}px` : '';
  node.classList.toggle('dv-sheet', phone);
  const r = anchor && anchor.getBoundingClientRect && anchor.isConnected ? anchor.getBoundingClientRect()
    : anchor && Number.isFinite(anchor.x) ? { left: anchor.x, right: anchor.x, top: anchor.y, bottom: anchor.y } : { left: vw / 2, right: vw / 2, top: vh / 3, bottom: vh / 3 };
  const box = node.getBoundingClientRect();
  let top = r.bottom + 6;
  if (top + box.height > vh - GUTTER) top = r.top - 6 - box.height >= GUTTER ? r.top - 6 - box.height : Math.max(GUTTER, vh - GUTTER - box.height);
  node.style.top = `${Math.round(top)}px`;
  if (!phone) node.style.left = `${Math.round(Math.max(GUTTER, Math.min(r.left, vw - GUTTER - box.width)))}px`;
}

/** Open a box inside `host` beside `anchor`; it closes on Escape, a press outside it, or close(). Returns its handle
    (`kind`: 'menu' or 'picker'; `lastFocus`, the last element focused in it). */
function mount(host, node, anchor, { onKey, keyFirst, kind = 'menu' } = {}) {
  closeAddUi();
  const back = document.activeElement;
  host.append(node);
  place(node, anchor);
  let raf = 0;
  const follow = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (node.isConnected) place(node, anchor); }); };
  // off the page (waiting for its view to be drawn again), the page's keys and presses are not its own
  const key = (e) => {
    if (!node.isConnected) return;
    if (keyFirst && keyFirst(e)) { e.preventDefault(); e.stopPropagation(); return; }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); handle.close(true); return; }
    if (onKey && node.contains(e.target)) onKey(e);
  };
  const press = (e) => { if (node.isConnected && !node.contains(e.target)) handle.close(false); };
  node.addEventListener('focusin', (e) => { handle.lastFocus = e.target; });
  const handle = {
    node,
    kind,
    host,
    lastFocus: null,
    rehost(el) { handle.host = el; },
    close(refocus) {
      if (open === handle) open = null;
      if (waiting && waiting.handle === handle) { clearTimeout(waiting.timer); waiting = null; }
      document.removeEventListener('keydown', key, true);
      document.removeEventListener('pointerdown', press, true);
      removeEventListener('resize', follow);
      removeEventListener('scroll', follow, true);
      cancelAnimationFrame(raf);
      node.remove();
      const now = live(anchor);
      const to = now && now.focus && now.isConnected ? now : back;
      if (refocus && to && to.focus && to.isConnected) to.focus({ preventScroll: true });
    },
    place: () => { if (node.isConnected) place(node, anchor); },
  };
  document.addEventListener('keydown', key, true);
  document.addEventListener('pointerdown', press, true);
  addEventListener('resize', follow);
  addEventListener('scroll', follow, true);
  open = handle;
  return handle;
}

/** The item menu: [{label, attr, run(anchor)}] at `anchor` (the right-clicked point or element). Arrows, Home, End,
    Enter; Escape closes it. An item may instead carry `html` (markup the caller escaped), `role: 'menuitemradio'` with
    `checked`, and `cls`; `opts.title` heads the menu and `opts.label` names it (the Nominal source dropdown, CONTRACT §36).
    The source popover (CONTRACT §36) adds: an item with `href` is a link (a menuitem opening in a new tab; Enter or Space
    follows it, and the menu closes after), `{separator: true}` a rule between items, and `opts.note` a line under the
    title. The arrows move through every menu item, buttons and links alike. An item with `items` holds a submenu (Notion's
    "Open in ›", CONTRACT §46): it opens on hover, a click, Enter or →; ← or Escape comes back to its item. On a phone it opens
    under its item, in the sheet. */
export function openItemMenu(host, anchor, items, opts = {}) {
  const node = document.createElement('div');
  node.className = `dv-itemmenu${opts.cls ? ` ${opts.cls}` : ''}`;
  node.setAttribute('role', 'menu');
  if (opts.label) node.setAttribute('aria-label', opts.label);
  const item = (it, i) => {
    if (it.separator) return '<div role="separator" class="dv-itemmenu-sep"></div>';
    const extra = `${it.cls ? ` class="${esc(it.cls)}"` : ''}${it.attr ? ` ${it.attr}` : ''}`;
    const body = it.html !== undefined ? it.html : esc(it.label);
    if (it.items) return `<button type="button" role="menuitem" aria-haspopup="menu" aria-expanded="false" data-i="${i}" data-sub${extra}><span>${body}</span><span class="dv-itemmenu-chev" aria-hidden="true">›</span></button>`;
    // `app`: a link another app answers (obsidian://): a new tab would stay behind it, blank
    if (it.href) return `<a role="menuitem" href="${esc(it.href)}"${it.app ? '' : ' target="_blank" rel="noopener"'} data-i="${i}"${extra}>${body}</a>`;
    const role = it.role === 'menuitemradio' ? 'menuitemradio' : 'menuitem';
    const checked = role === 'menuitemradio' ? ` aria-checked="${it.checked ? 'true' : 'false'}"` : '';
    return `<button type="button" role="${role}"${checked} data-i="${i}"${extra}>${body}</button>`;
  };
  node.innerHTML = `${opts.title ? `<p class="dv-itemmenu-title">${esc(opts.title)}</p>` : ''}${opts.note ? `<p class="dv-itemmenu-note">${esc(opts.note)}</p>` : ''}${items.map(item).join('')}`;
  const entries = () => [...node.querySelectorAll(':scope > [role^="menuitem"]')];
  let sub = null;
  const closeSub = (refocus) => {
    if (!sub) return;
    const { el, from } = sub;
    sub = null;
    el.remove();
    from.setAttribute('aria-expanded', 'false');
    if (refocus) from.focus({ preventScroll: true });
  };
  const openSub = (from, focus) => {
    if (sub && sub.from === from) { if (focus) sub.el.querySelector('[role^="menuitem"]').focus({ preventScroll: true }); return; }
    closeSub(false);
    const it = items[Number(from.dataset.i)];
    const el = document.createElement('div');
    el.className = 'dv-itemmenu dv-itemmenu-sub';
    el.setAttribute('role', 'menu');
    el.setAttribute('aria-label', it.label || '');
    el.innerHTML = it.items.map(item).join('');
    if (node.classList.contains('dv-sheet')) from.after(el);
    else node.append(el);
    const r = from.getBoundingClientRect(), box = el.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    if (!node.classList.contains('dv-sheet')) {
      const right = r.right + box.width + GUTTER <= vw;
      el.style.left = `${Math.round(right ? r.right + 2 : Math.max(GUTTER, r.left - box.width - 2))}px`;
      el.style.top = `${Math.round(Math.min(r.top - 4, vh - GUTTER - box.height))}px`;
    }
    from.setAttribute('aria-expanded', 'true');
    sub = { el, from, items: it.items };
    if (focus) el.querySelector('[role^="menuitem"]').focus({ preventScroll: true });
  };
  const h = mount(host, node, anchor, {
    keyFirst(e) {
      // Escape inside a submenu leaves the submenu, not the menu
      if (e.key === 'Escape' && sub) { closeSub(true); return true; }
      return false;
    },
    onKey(e) {
      const at = document.activeElement;
      if (sub && sub.el.contains(at)) {
        if (e.key === ' ' && at.matches('a[data-i]')) { e.preventDefault(); at.click(); return; }
        if (e.key === 'ArrowLeft') { e.preventDefault(); closeSub(true); return; }
        const inner = [...sub.el.querySelectorAll('[role^="menuitem"]')], k = inner.indexOf(at);
        const to = { ArrowDown: k + 1, ArrowUp: k - 1, Home: 0, End: inner.length - 1 }[e.key];
        if (to !== undefined) { e.preventDefault(); inner[(to + inner.length) % inner.length].focus(); } else if (e.key === 'Tab') h.close(false);
        return;
      }
      if ((e.key === 'ArrowRight' || e.key === 'Enter' || e.key === ' ') && at && at.matches && at.matches('[data-sub]') && node.contains(at)) { e.preventDefault(); openSub(at, true); return; }
      // a link is a menu item too: Space follows it, as Enter does (a link's own key)
      if (e.key === ' ' && at && at.matches && at.matches('a[data-i]') && node.contains(at)) { e.preventDefault(); at.click(); return; }
      const list = entries(), i = list.indexOf(at);
      const go = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: list.length - 1 }[e.key];
      if (go === undefined) { if (e.key === 'Tab') h.close(false); return; }
      e.preventDefault();
      list[(go + list.length) % list.length].focus();
    },
  });
  // WHY over, not only a click: Notion's opens as the pointer reaches it. A pointer on any other item closes it again
  node.addEventListener('pointerover', (e) => {
    if (e.pointerType === 'touch') return;
    const b = e.target.closest && e.target.closest('[data-i]');
    if (!b || !node.contains(b) || (sub && sub.el.contains(b))) return;
    if (b.matches('[data-sub]')) openSub(b, false); else closeSub(false);
  });
  node.addEventListener('click', (e) => {
    const b = e.target.closest('[data-i]');
    if (!b || !node.contains(b)) return;
    e.stopPropagation();
    if (b.matches('[data-sub]')) { openSub(b, true); return; }
    // WHY after, never before: a link taken off the page opens nothing (it is followed once this click is done)
    if (b.tagName === 'A') { setTimeout(() => h.close(false), 0); return; }
    const inner = !!(sub && sub.el.contains(b));
    const it = (inner ? sub.items : items)[Number(b.dataset.i)];
    h.close(false);
    it.run(anchor);
  });
  const first = node.querySelector('[role^="menuitem"]');
  if (first) first.focus({ preventScroll: true });
  return h;
}

/** The picker. opts: {target, anchor, what (the line saying what is added), moment ({t, label, exact?}: offer "At this
    moment", its label as the clock writes t and the exact instant in its title), error (why nothing can be added from
    here)}. `host` is the <data-views> the panel comes from: its panelSpec(target, {t}) is the panel, and the event is
    fired on it; after a redraw, on the element drawn in its place (adoptAddUi). */
export function openPicker(host, { target = { kind: 'view' }, anchor = null, what = '', moment = null, error = null } = {}) {
  const node = document.createElement('div');
  node.className = 'dv-addpick';
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-label', 'Add to dashboard');
  node.innerHTML = `<div class="dv-addpick-head"><h4>Add to dashboard</h4><button type="button" class="dv-addpick-x" aria-label="Close">${icon('x')}</button></div>
    ${what ? `<p class="dv-addpick-what">${esc(what)}</p>` : ''}
    ${error ? `<p class="dv-addpick-msg dv-addpick-refused" role="alert">${esc(error)}</p>` : `
    ${moment ? `<label class="dv-addpick-at"><input type="checkbox" name="at-moment"> At this moment <span class="dv-addpick-t"${moment.exact ? ` title="${esc(moment.exact)}"` : ''}>t = ${esc(moment.label)}</span></label>` : ''}
    <div class="dv-addpick-list" role="group" aria-label="Dashboards"><p class="dv-addpick-msg">Loading dashboards…</p></div>
    <button type="button" class="dv-addpick-new" data-dashboard-new>${icon('plus')}<span>New dashboard…</span></button>
    <form class="dv-addpick-form" hidden><input name="dashboard-title" placeholder="Dashboard name" aria-label="New dashboard name" autocomplete="off"><button type="submit" data-dashboard-create>Create and add</button></form>`}
    <p class="dv-addpick-status" role="status" aria-live="polite" data-state=""></p>`;
  const h = mount(host, node, anchor, { kind: 'picker' });
  // the <data-views> the panel comes from: the one drawn in its place after a redraw of its dashboard (adoptAddUi)
  let from = host;
  h.rehost = (el) => { from = el; h.host = el; };
  // the dialog takes focus at once (a keyboard reader starts inside it); its first dashboard does once they are listed
  node.tabIndex = -1;
  node.focus({ preventScroll: true });
  node.querySelector('.dv-addpick-x').addEventListener('click', () => h.close(true));
  if (error) return h;

  const list = node.querySelector('.dv-addpick-list');
  const status = node.querySelector('.dv-addpick-status');
  const form = node.querySelector('.dv-addpick-form');
  const entries = new Map();
  let busy = false;
  const say = (state, text, href = null) => {
    status.dataset.state = state;
    status.classList.toggle('dv-addpick-refused', state === 'error');
    status.innerHTML = `${esc(text)}${href ? ` <a href="${esc(href)}">Open ↗</a>` : ''}`;
    h.place();
  };
  const lock = (on) => { busy = on; for (const b of node.querySelectorAll('.dv-addpick-list button, [data-dashboard-new], [data-dashboard-create]')) b.disabled = on; };

  const draw = (items) => {
    entries.clear();
    const ok = (Array.isArray(items) ? items : []).filter((d) => d && d.id !== undefined && d.id !== null && d.title);
    for (const d of ok) entries.set(String(d.id), d);
    list.innerHTML = ok.length ? ok.map((d) => `<button type="button" class="dv-addpick-item" data-dashboard-id="${esc(String(d.id))}">${icon('dashboard')}<span>${esc(String(d.title))}</span></button>`).join('')
      : '<p class="dv-addpick-msg">No dashboards are listed here yet.</p>';
    h.place();
    const first = list.querySelector('button') || node.querySelector('[data-dashboard-new]');
    if (first && (document.activeElement === node || !node.contains(document.activeElement))) first.focus({ preventScroll: true });
  };
  const hook = dashboardsHook(host);
  if (!hook) draw([]);
  else {
    Promise.resolve().then(hook).then(draw, (err) => {
      list.innerHTML = `<p class="dv-addpick-msg dv-addpick-refused">Could not list dashboards: ${esc((err && err.message) || String(err))}</p>`;
      h.place();
      if (document.activeElement === node) node.querySelector('[data-dashboard-new]').focus({ preventScroll: true });
    });
  }

  list.addEventListener('click', (e) => {
    const b = e.target.closest('[data-dashboard-id]');
    if (b && !busy) add(entries.get(b.dataset.dashboardId));
  });
  node.querySelector('[data-dashboard-new]').addEventListener('click', () => {
    form.hidden = false;
    h.place();
    form.querySelector('input').focus();
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const title = form.querySelector('input').value.trim();
    if (!title) { form.querySelector('input').focus(); return; }
    if (!busy) add({ id: null, title, new: true });
  });

  async function add(dash) {
    if (!dash) return;
    lock(true);
    say('adding', `Adding to ${dash.title}…`);
    try {
      const at = moment && node.querySelector('input[name=at-moment]').checked ? moment.t : undefined;
      const panel = from.panelSpec(target, { t: at });
      let current = null;
      if (dash.new) current = '';
      else if (typeof dash.text === 'string') current = dash.text;
      else if (dash.url) {
        // WHY no-store: the text a save wrote a moment ago, never an older copy the browser kept
        const res = await fetch(new URL(dash.url, document.baseURI), { cache: 'no-store' });
        if (!res.ok) throw new Error(`could not read ${dash.url} (${res.status})`);
        current = await res.text();
      }
      const base = !dash.new && dash.url ? new URL(dash.url, document.baseURI).href : undefined;
      const text = current === null ? null : appendPanel(current, panel, { title: dash.new ? dash.title : undefined, base });
      const answer = handOver(from, dash, panel, text);
      if (answer.kind === 'respond') {
        const r = await answer.promise;
        if (r && typeof r === 'object' && r.ok === false) throw new Error(r.reason || 'the host did not save it');
        say('added', `Added to ${(r && typeof r === 'object' && r.title) || dash.title}`, r && typeof r === 'object' && typeof r.href === 'string' ? r.href : null);
      } else if (answer.kind === 'taken') {
        h.close(true);
        return;
      } else {
        // no host: the text goes to the clipboard (a new dashboard's own, when the host gave nothing to append to)
        const copy = text !== null ? text : appendPanel('', panel, { title: dash.title });
        if (await clip(copy)) {
          say('copied', dash.new ? `Copied the new dashboard “${dash.title}” to the clipboard: save it as a .base file.`
            : text !== null ? `Copied ${dash.title}'s new text to the clipboard: paste it over its .base file.` : `Copied the panel, as a dashboard of its own, to the clipboard: put its entries in ${dash.title}.`);
        } else {
          shown(copy);
          say('error', 'The clipboard is not available here: select the text above and copy it.');
        }
      }
    } catch (err) {
      say('error', `Could not add to ${dash.title}: ${(err && err.message) || err}`);
    } finally {
      lock(false);
    }
  }

  function shown(text) {
    let ta = node.querySelector('.dv-addpick-text');
    if (!ta) { ta = document.createElement('textarea'); ta.className = 'dv-addpick-text'; ta.readOnly = true; ta.setAttribute('aria-label', 'The dashboard\'s text'); status.before(ta); }
    ta.value = text;
    ta.select();
  }
  return h;
}

/** Fire data-add-to-dashboard on `host`; what the host did: {kind: 'respond', promise} | {kind: 'taken'} | {kind: 'none'}. */
export function handOver(host, dash, panel, text) {
  let promise = null, live = true, ev = null;
  const detail = {
    dashboard: { id: dash.new ? null : dash.id, title: dash.title, url: dash.url == null ? null : dash.url, new: !!dash.new },
    panel,
    text,
    respondWith(p) {
      if (!live) throw new Error('respondWith(promise): call it while the data-add-to-dashboard event is dispatched');
      if (promise) throw new Error('respondWith(promise): it was called already for this add');
      promise = Promise.resolve(p);
      ev.preventDefault();
    },
  };
  ev = new CustomEvent('data-add-to-dashboard', { bubbles: true, composed: true, cancelable: true, detail });
  try { host.dispatchEvent(ev); } finally { live = false; }
  if (promise) return { kind: 'respond', promise };
  return { kind: ev.defaultPrevented ? 'taken' : 'none' };
}

async function clip(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}
