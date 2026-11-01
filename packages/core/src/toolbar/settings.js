/* View settings (docs/CONTRACT.md §15, display="panel|popover"): Notion's rows for the open view, from the bar's Display
   button. Zach, 2026-10-26, on Notion's side panel against Linear's Display popover: "I prefer the notion layout
   though its much cleaner than the linear one", so the panel is the default and the popover the option.

     the view's name · Layout › · Property visibility N › · Filter › · Sort › · Group › · Copy link to view ·
     Copy view as .base · Add to dashboard… (CONTRACT §34)

   The sub-pages are the toolbar's own menu bodies (data-views.js _openMenu with `into`), drawn here with a ‹ back:
   one implementation of each menu, whichever toolbar shows it. Layout › is the bar's type grid plus the layout's own
   settings, its plugin's options(), whatever they are (this file adds nothing view-specific).

   panel    a side panel inside the element's right edge, under the bar; resizable (§11: min 260, max 640, key
            data-ui/panel-width/settings:<id>, double-click resets); closes with ✕ or Escape
   popover  the same rows in a popover under the Display button; a click outside closes it
   Below 700 px either opens as a full-width sheet (styles/toolbar.css).

   mountSettings(el) -> {open(page, anchor), close(), toggle(anchor), isOpen(), update(), destroy()} */

import { esc } from '../format.js';
import { makeResizable } from '../resize.js';
import { FRAMES, frameOf } from '../frame.js';
import { icon, layoutName, layoutIcon } from './icons.js';
import { layoutGrid, renameView, copyText, filterCount } from './bar.js';

const TITLES = { layout: 'Layout', frame: 'Frame', properties: 'Property visibility', filter: 'Filter', sort: 'Sort', group: 'Group', rollup: 'Roll up' };

// The frames are frame.js's (docs/CONTRACT.md §12); the one-line hints say what each looks like, from §12's table.
const FRAME_HINTS = {
  boxed: 'A bordered box with a header band (the default look)',
  flush: 'No border and no header fill: the rows sit on the page',
  tabs: 'The views as the page\'s tabs, the tools in a row under them',
  sheet: 'A tinted well with pill tabs and white tiles',
  page: 'Scrolls with the page; the bar sticks to the top',
  bleed: 'Edge to edge, scrolls with the page, a tinted sticky band',
  card: 'One rounded card as tall as its rows, a pager under it (Shopify admin)',
};
const frameName = (f) => f.charAt(0).toUpperCase() + f.slice(1);
const frameKey = (el) => `data-ui/frame/${el.id || 'data-views'}`;
const frameStore = {
  get(el) { try { const f = localStorage.getItem(frameKey(el)); return FRAMES.includes(f) ? f : null; } catch { return null; } },
  set(el, f) { try { localStorage.setItem(frameKey(el), f); } catch { /* private window: the pick lasts this visit */ } },
  drop(el) { try { localStorage.removeItem(frameKey(el)); } catch { /* nothing stored */ } },
};
/** A host hides the reader's Frame row with settings-frame="off" (§15 note 2026-10-26); then a stored pick is ignored. */
const frameRowOn = (el) => el.getAttribute('settings-frame') !== 'off';

/** Put the reader's frame on the element, keeping the host's own value once so "Reset to page default" can return it. */
function setFrame(el, f) {
  if (el._frameHost === undefined) el._frameHost = el.getAttribute('frame');
  if (el.getAttribute('frame') !== f) el.setAttribute('frame', f);
}

function resetFrame(el) {
  frameStore.drop(el);
  if (el._frameHost === undefined) return;
  const host = el._frameHost;
  delete el._frameHost;
  if (host === null) el.removeAttribute('frame'); else el.setAttribute('frame', host);
}

export function mountSettings(el) {
  // WHY the reader's pick wins on start: robotparts defaults its pages to one frame and lets a reader choose another
  // (the coordinator's ask, 2026-10-26); the pick is per element and survives a reload
  const remembered = frameRowOn(el) ? frameStore.get(el) : null;
  if (remembered) setFrame(el, remembered);
  const node = document.createElement('section');
  node.className = 'dv-settings';
  node.hidden = true;
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-label', 'View settings');
  el.append(node);
  let pageName = null;
  let anchor = null;
  let ctl = null;
  const modeOf = () => (el.getAttribute('display') === 'popover' ? 'popover' : 'panel');

  // WHY the kit's own resizer: every side panel drags, remembers its width and resets on a double-click (Zach, memory
  // feedback_resizable_panels; .claude/feedback.md 2026-10-26); the popover is not a side panel, so it gets none
  function resizable(on) {
    if (on && !ctl && !el.closest('[data-resizable="off"]')) {
      ctl = makeResizable(node, { edge: 'left', min: 260, max: 640, keep: 160, key: `settings:${el.id || 'data-views'}`, label: 'the view settings' });
    } else if (!on && ctl) { ctl.destroy(); ctl = null; node.style.removeProperty('--data-panel-width'); node.classList.remove('dv-sized', 'dv-resizable'); }
  }

  function place() {
    const bar = el.$('.dv-bar');
    // the bar redraws its tools when the panel opens, so the button found at open time may be gone: find it again
    if (!anchor || !anchor.isConnected) anchor = el.querySelector('.dv-bar [data-bar=display]');
    const sheet = matchMedia('(max-width: 700px)').matches;
    // WHY the band's bottom (bar.js): the panel starts under the bar and its pill or bulk row, so none of their controls
    // is under it, and under frame="page|bleed" (the panel fixed to the window, as the peek is; CONTRACT §12) wherever
    // the band is as the page scrolls
    const band = el._barUi ? el._barUi.bandBottom() : bar ? bar.getBoundingClientRect().bottom : el.getBoundingClientRect().top;
    const inside = () => `${Math.round(band - el.getBoundingClientRect().top - el.clientTop)}px`;
    if (el.dataset.scroll === 'page' && bar && (modeOf() === 'panel' || sheet)) {
      const portTop = parseFloat(el.style.getPropertyValue('--dv-port-top')) || 0;
      node.style.top = modeOf() === 'panel' ? `${Math.round(Math.max(portTop, band))}px` : inside();
      node.style.left = '';
      return;
    }
    if (modeOf() === 'panel' || !anchor || sheet) {
      node.style.top = inside();
      node.style.left = '';
      return;
    }
    const b = anchor.getBoundingClientRect(), host = el.getBoundingClientRect();
    const w = node.getBoundingClientRect().width || 320;
    node.style.top = `${b.bottom - host.top + 6}px`;
    node.style.left = `${Math.max(8, Math.min(b.right - host.left - w, host.width - w - 8))}px`;
  }
  // while open under a page frame, the panel or popover follows the stuck bar as the page scrolls
  let follow = null;
  const scroller = () => (el.host && el.host.scroller) || null;
  function track(on) {
    const target = scroller();
    if (follow) { follow.target.removeEventListener('scroll', follow.fn); removeEventListener('resize', follow.fn); follow = null; }
    if (!on || !target) return;
    let raf = 0;
    const fn = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (!node.hidden) place(); }); };
    target.addEventListener('scroll', fn, { passive: true });
    addEventListener('resize', fn);
    follow = { target, fn };
  }

  // ---- pages
  const head = (title, back) => `<header class="dv-set-head">${back ? `<button type="button" class="dv-set-back" aria-label="Back to View settings">${icon('chevL')}</button>` : ''}<h3>${esc(title)}</h3><button type="button" class="dv-set-close" aria-label="Close view settings">${icon('x')}</button></header>`;

  function rootHtml() {
    const v = el.view;
    const cols = el._model.columns;
    const label = (id) => (cols[id] ? cols[id].label : id);
    const visible = (v.order || []).filter((id) => cols[id]).length;
    const sort = v.sort || [];
    const levels = [v.groupBy, v.subGroupBy].filter(Boolean);
    const n = filterCount(el);
    const row = (page, ic, text, value) => `<button type="button" class="dv-set-row" data-page="${page}">${icon(ic)}<span class="dv-set-label">${esc(text)}</span><span class="dv-set-value">${esc(value)}</span>${icon('chevR', 'dv-set-chev')}</button>`;
    const act = (name, ic, text) => `<button type="button" class="dv-set-row" data-act="${name}">${icon(ic)}<span class="dv-set-label">${esc(text)}</span></button>`;
    return `${head('View settings', false)}
      <div class="dv-set-name">${icon(layoutIcon(v.type))}<input class="dv-set-input" value="${esc(el.origin.name)}" aria-label="View name" title="${el.origin.kind === 'user' ? 'Rename this view' : 'A view of the .base file: a new name saves your own copy'}"></div>
      <div class="dv-set-rows">
        ${row('layout', layoutIcon(v.type), 'Layout', layoutName(v.type))}
        ${frameRowOn(el) ? row('frame', 'frame', 'Frame', frameName(frameOf(el))) : ''}
        ${row('properties', 'eye', 'Property visibility', visible)}
        ${row('filter', 'filter', 'Filter', n || '')}
        ${row('sort', 'sort', 'Sort', sort.length ? label(sort[0].property) + (sort.length > 1 ? ` +${sort.length - 1}` : '') : '')}
        ${row('group', 'group', 'Group', levels.map((g) => label(g.property) + (g.by ? ` by ${g.by}` : '')).join(' › '))}
        ${v.type === 'table' || v.type === 'pivot' ? row('rollup', 'pivot', 'Roll up', v.rollup && el._model.rolled ? el._model.rolled.away.map(label).join(', ') : '') : ''}
        <hr>
        ${act('copy-link', 'link', 'Copy link to view')}
        ${act('copy-base', 'code', 'Copy view as .base')}
        ${act('add-dashboard', 'addDash', 'Add to dashboard…')}
      </div>`;
  }

  function bindHead() {
    const back = node.querySelector('.dv-set-back');
    if (back) back.addEventListener('click', () => go('root'));
    node.querySelector('.dv-set-close').addEventListener('click', () => api.close());
  }

  function drawRoot() {
    node.innerHTML = rootHtml();
    bindHead();
    const name = node.querySelector('.dv-set-input');
    name.addEventListener('change', () => renameView(el, name.value));
    name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); name.blur(); } });
    node.querySelectorAll('[data-page]').forEach((b) => b.addEventListener('click', () => go(b.dataset.page)));
    node.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.act === 'copy-link') copyText(location.href, b);
      // CONTRACT §34: the picker opens beside Display; View settings closes, so the two never cover each other
      else if (b.dataset.act === 'add-dashboard') { api.close(); el.addToDashboard({ kind: 'view' }, { anchor: () => el.querySelector('.dv-bar [data-bar=display]') }); }
      else copyText(el.viewYaml(), b);
    }));
  }

  /** the `into` of data-views.js _openMenu: a menu body drawn as this page */
  const into = {
    show(html, bind) {
      node.innerHTML = `${head(TITLES[pageName] || pageName, true)}<div class="dv-set-body dv-set-${esc(pageName)}">${html}</div>`;
      bindHead();
      if (bind) bind(node.querySelector('.dv-set-body'));
    },
    refresh() { draw(); },
    close() { api.close(); },
  };

  function drawLayout() {
    el._viewOptions = null;
    const rows = el._optionRows();
    const type = el.view.type;
    // the layout's options() arrive with its code: a view not drawn yet gets this page again once it has drawn
    if (el._pluginType !== type) el.addEventListener('data-views-render', () => { if (pageName === 'layout') draw(); }, { once: true });
    into.show(`${layoutGrid(type)}${rows ? `<h5>${esc(layoutName(type))} settings</h5><div class="dv-set-opts">${rows}</div>` : ''}`, (body) => {
      body.querySelectorAll('.dv-layout:not([disabled])').forEach((b) => b.addEventListener('click', () => {
        if (b.dataset.type === el.view.type) return;
        el.update((x) => { x.type = b.dataset.type; if (x.type === 'pivot' && !x.splitBy) x.splitBy = []; });
        draw();
      }));
      el._bindOptions(body, () => draw());
    });
  }

  function drawFrame() {
    const cur = frameOf(el);
    const mine = frameStore.get(el);
    into.show(`<div class="dv-frames" role="radiogroup" aria-label="Frame">${FRAMES.map((f) => `<button type="button" class="dv-frame${f === cur ? ' dv-on' : ''}" role="radio" aria-checked="${f === cur}" data-frame="${f}"><span class="dv-frame-text"><span class="dv-frame-name">${frameName(f)}</span><span class="dv-frame-hint">${esc(FRAME_HINTS[f])}</span></span><span class="dv-frame-check">${f === cur ? icon('check') : ''}</span></button>`).join('')}</div>
      <button type="button" class="dv-frame-reset"${mine ? '' : ' disabled'}>Reset to page default</button>
      <p class="dv-hint">${mine ? 'Your pick, kept in this browser for this table.' : 'The page\'s own frame; a pick is kept in this browser.'}</p>`, (body) => {
      body.querySelectorAll('[data-frame]').forEach((b) => b.addEventListener('click', () => {
        setFrame(el, b.dataset.frame);
        frameStore.set(el, b.dataset.frame);
        draw();
      }));
      body.querySelector('.dv-frame-reset').addEventListener('click', () => { resetFrame(el); draw(); });
    });
  }

  function draw() {
    if (node.hidden || !el._model) return;
    const scroll = node.scrollTop;
    if (pageName === 'root') drawRoot();
    else if (pageName === 'layout') drawLayout();
    else if (pageName === 'frame') drawFrame();
    else {
      el._openMenu(null, { into, name: pageName });
      // the Filter page is also where the rail is shown or hidden (filters="… rail"): the same switch as the bar's Filter
      const rail = pageName === 'filter' && el._barUi && el._barUi.rail();
      const body = node.querySelector('.dv-set-body');
      if (rail && body) {
        body.insertAdjacentHTML('afterbegin', `<button type="button" class="dv-set-row dv-set-rail" aria-pressed="${rail.open}">${icon('rail')}<span class="dv-set-label">Filter rail</span><span class="dv-set-value">${rail.open ? 'Shown' : 'Hidden'}</span></button>`);
        body.querySelector('.dv-set-rail').addEventListener('click', () => { rail.toggle(); draw(); });
      }
    }
    node.scrollTop = scroll;
  }

  function go(name) {
    pageName = name;
    node.scrollTop = 0;
    draw();
    const first = node.querySelector(name === 'root' ? '.dv-set-row' : '.dv-set-body select, .dv-set-body input, .dv-set-body button, .dv-set-back');
    if (first) first.focus();
  }

  // a click outside a popover closes it (composedPath: a redraw may have detached the clicked control); the element's
  // document click handler calls it, so the settings add no document listener of their own
  const outside = (e) => {
    if (node.hidden || modeOf() !== 'popover') return;
    const path = e.composedPath();
    if (path.includes(node) || path.some((n) => n && n.dataset && n.dataset.bar === 'display')) return;
    api.close();
  };

  const api = {
    open(name = 'root', from = null) {
      const mode = modeOf();
      // WHY: the record pane (open modes, CONTRACT §13) is on the same right edge; split, the panel docks beside it
      // (toolbar.css); as an overlay or full screen the two would cover each other, so the newer one closes the other
      if (el._peek && !el.classList.contains('dv-split')) el.closePeek();
      anchor = from || el.querySelector('.dv-bar [data-bar=display]');
      node.classList.toggle('dv-settings-panel', mode === 'panel');
      node.classList.toggle('dv-settings-pop', mode === 'popover');
      resizable(mode === 'panel');
      node.hidden = false;
      place();
      go(name);
      place();
      track(true);
      if (el._barUi) el._barUi.update();
    },
    close() {
      if (node.hidden) return;
      const had = node.contains(document.activeElement);
      node.hidden = true;
      pageName = null;
      track(false);
      if (el._barUi) el._barUi.update();
      const display = el.querySelector('.dv-bar [data-bar=display]');
      if (had && display) display.focus();
    },
    /** A click anywhere on the page (the element's document click handler passes it on): outside a popover closes it. */
    outside(e) { outside(e); },
    toggle(from) { if (api.isOpen()) api.close(); else api.open('root', from); },
    isOpen() { return !node.hidden; },
    /** Put the panel or popover under the band again (the bar calls it when the band grows or shrinks). */
    place() { if (!node.hidden) place(); },
    /** Every render: keep what the panel shows true (the root's counts; a sub-page when the change came from elsewhere,
        e.g. a tick in the rail), without redrawing under a control being used in it. */
    update() {
      if (node.hidden) return;
      // a new frame may have moved the scroll to the page (or back): follow the scroller there is now
      if ((follow ? follow.target : null) !== scroller()) track(true);
      place();
      if (node.contains(document.activeElement)) return;
      draw();
    },
    destroy() {
      track(false);
      resizable(false);
      node.remove();
    },
  };
  return api;
}
