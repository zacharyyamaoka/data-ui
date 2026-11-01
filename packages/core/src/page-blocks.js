/* A record's page under a layout (docs/CONTRACT.md §46): the title, the property list, the blocks, the free text last.

   Zach, 2026-10-31: "If I saw each column is associated with an H1 then its simpler" and "thoose things move around as "blocks" so you cannot mix
   things together".
   A block is one <section>: its heading, its body, nothing shared with the next. Dragging one moves it among blocks; that is the layout's
   order, in the `.base`, and no note is touched (WHY: §46).

   Words are drawn as markdown and become a plain textarea on a click, as a page does; leaving it commits through propose, Esc puts back
   what the row says. A typed property drawn as a block keeps its typed control: it is a value under a heading, not a place to write. */

import { cellValue } from './grammar.js';
import { esc, isEmpty } from './format.js';
import { fieldHtml, lockedBecause, readEdits } from './form.js';
import { markdown } from './md.js';
import { replaceKeyInText, stringifyBase } from './base.js';
import { isBlock, layoutValue, moveEntry, stepEntry, withPlace, withVisible } from './page-layout.js';

const PLACE_NAME = { top: 'Property list', section: 'Section (an H1 on the page)' };
const text = (cell) => { const v = cellValue(cell); return isEmpty(v) ? '' : Array.isArray(v) ? v.join(', ') : String(v); };
const VIDEO = /\.(mp4|webm|mov)(?:[?#]|$)/i;
const grow = (ta) => { ta.style.height = 'auto'; ta.style.height = `${ta.scrollHeight + 2}px`; };

/** Whether a property is words a block can hold, or a typed value drawn under a heading. */
export function isWords(p) {
  return !!(p.section || p.long || p.pageBody || (p.display === 'media') || ((p.type === 'text' || !p.type) && !p.labels && !(p.constraints && p.constraints.enum) && p.display !== 'badge'));
}

/** A property's markdown as HTML; an image or a video is the page's own, with the row's path resolved by the host. */
function wordsHtml(el, row, value) {
  const image = (src, alt, embed) => {
    const url = typeof el.resolveMedia === 'function' ? el.resolveMedia(src, { row, embed }) : src;
    return VIDEO.test(src)
      ? `<video class="dv-page-media" src="${esc(url)}" controls preload="metadata" aria-label="${esc(alt)}"></video>`
      : `<img class="dv-page-media" data-page-zoom src="${esc(url)}" alt="${esc(alt)}" loading="lazy">`;
  };
  // a wikilink is the host's to place (el.resolveLink); with no place for it, a note of this table opens here, and anything else stays its words
  const wikilink = (target, alias) => {
    const words = esc(alias || target);
    const url = typeof el.resolveLink === 'function' ? el.resolveLink(target, { row }) : null;
    if (url) return `<a class="dv-page-link" href="${esc(url)}" data-page-wikilink="${esc(target)}">${words}</a>`;
    const note = target.split('#')[0];
    const hit = el.data.rows.find((r) => String(r[el.data.titleProperty]) === note);
    return hit ? `<a class="dv-page-link" href="#" data-page-note="${esc(hit.id)}" data-page-wikilink="${esc(target)}">${words}</a>` : `<span class="dv-page-nolink" data-page-wikilink="${esc(target)}">${words}</span>`;
  };
  return markdown(value, { image, wikilink, breaks: true });
}

// the record's title is the h2; a section is the next level down, drawn as the page's H1
const heading = (label) => `<h3 class="dv-page-h">${esc(label)}</h3>`;

function grip(label) { return `<button type="button" class="dv-page-grip" data-page-grip aria-label="Move ${esc(label)}: drag, or the up and down keys" title="Drag to move · ↑ ↓"><span aria-hidden="true">⠿</span></button>`; }

function propertyRow(el, row, e, p, read) {
  const locked = !el.editing || lockedBecause(p) || row._readOnly;
  const body = locked ? (isEmpty(cellValue(row[p.id])) ? '<span class="dv-page-empty">Empty</span>' : read(p)) : fieldHtml(row, p);
  return `<div class="dv-page-prop dv-peek-field" data-page-entry="${esc(p.id)}" data-p="${esc(p.id)}">${grip(p.label)}<button type="button" class="dv-page-name" data-page-menu aria-haspopup="menu">${esc(p.label)}</button><div class="dv-page-val"${locked ? '' : ' data-page-field'}>${body}</div></div>`;
}

function blockHtml(el, row, e, p, read) {
  const locked = !el.editing || lockedBecause(p) || row._readOnly;
  const value = text(row[p.id]);
  let body;
  if (!isWords(p)) body = `<div class="dv-page-val"${locked ? '' : ' data-page-field'}>${locked ? (isEmpty(cellValue(row[p.id])) ? '<span class="dv-page-empty">Empty</span>' : read(p)) : fieldHtml(row, p)}</div>`;
  else body = `<div class="dv-page-md dv-md"${locked ? '' : ' data-page-read tabindex="0" role="button" aria-label="Edit ' + esc(p.label) + '"'}>${value ? wordsHtml(el, row, value) : `<span class="dv-page-empty">${locked ? 'Empty' : 'Write here'}</span>`}</div>`;
  return `<section class="dv-page-sec dv-page-block dv-peek-field" data-page-entry="${esc(p.id)}" data-page-block="${esc(p.id)}" data-p="${esc(p.id)}"><div class="dv-page-head">${grip(p.label)}${heading(p.label)}<button type="button" class="dv-page-more" data-page-menu aria-haspopup="menu" aria-label="${esc(p.label)}: place on the page">⋯</button></div>${body}</section>`;
}

function freeHtml(el, row, p) {
  const locked = !el.editing || lockedBecause(p) || row._readOnly;
  const value = text(row[p.id]);
  return `<section class="dv-page-sec dv-page-free dv-peek-field" data-page-block="${esc(p.id)}" data-page-free data-p="${esc(p.id)}"><div class="dv-page-md dv-md"${locked ? '' : ` data-page-read tabindex="0" role="button" aria-label="Edit the page"`}>${value ? wordsHtml(el, row, value) : `<span class="dv-page-empty">${locked ? '' : 'Write anything on this page'}</span>`}</div></section>`;
}

/** The whole page's fields: `read(p)` draws a property's value for reading (the element's, so links, status and sources stay as they are). */
export function pageHtml(el, row, layout, props, read) {
  const known = layout.entries.filter((e) => props[e.id]);
  const list = known.filter((e) => !isBlock(e.place) && e.visible);
  const blocks = known.filter((e) => isBlock(e.place) && e.visible);
  const hidden = known.filter((e) => !e.visible);
  const open = !!el._pageHiddenOpen;
  const rows = list.map((e) => propertyRow(el, row, e, props[e.id], read)).join('');
  const more = hidden.length ? `<button type="button" class="dv-page-toggle" data-page-hidden aria-expanded="${open}">${hidden.length} hidden ${hidden.length === 1 ? 'property' : 'properties'}</button>${open ? `<div class="dv-page-hiddenlist">${hidden.map((e) => `<div class="dv-page-prop dv-page-off" data-page-entry="${esc(e.id)}"><span class="dv-page-grip dv-page-nogrip"></span><button type="button" class="dv-page-name" data-page-menu aria-haspopup="menu">${esc(props[e.id].label)}</button><div class="dv-page-val">${isEmpty(cellValue(row[e.id])) ? '<span class="dv-page-empty">Empty</span>' : read(props[e.id])}</div></div>`).join('')}</div>` : ''}` : '';
  const free = layout.free && props[layout.free] ? freeHtml(el, row, props[layout.free]) : '';
  return `<div class="dv-page-props" data-page-list>${rows}${more}</div><div class="dv-page-blocks" data-page-blocks>${blocks.map((e) => blockHtml(el, row, e, props[e.id], read)).join('')}</div>${free}<p class="dv-page-live" role="status" aria-live="polite"></p>`;
}

// ---------------------------------------------------------------- changing the layout
/** The `.base` text with this layout in it, and the `page:` value. */
function nextText(el, layout) {
  const value = layoutValue(layout);
  const was = typeof el.baseText === 'string' ? el.baseText : stringifyBase({ ...el._base });
  return { value, text: replaceKeyInText(was, 'page', value) };
}

function adopt(el, value, text) {
  el._base.page = value;
  if (typeof el.baseText === 'string' || text) el.baseText = text;
  el._redrawPage();
}

/** A change that is the layout's alone: the page redraws at once, and the file follows through persistView. */
async function keep(el, entries) {
  const layout = { ...el._pageLayout(), entries };
  const before = { page: el._base.page, text: el.baseText };
  const { value, text } = nextText(el, layout);
  adopt(el, value, text);
  if (typeof el.persistView !== 'function') return { ok: true };
  let answer;
  try { answer = await el.persistView({ text, name: null, kind: 'page', view: null, selected: null, filters: el.filters ?? null }); } catch (err) { answer = { ok: false, reason: err.message }; }
  if (!(answer && answer.ok)) { adopt(el, before.page, before.text); say(el, `Not saved: ${(answer && answer.reason) || 'the host refused it'}`); }
  el.dispatchEvent(new CustomEvent('data-views-persist', { detail: { name: null, text, result: answer } }));
  return answer;
}

const say = (el, msg) => { const m = el.querySelector('.dv-peek .dv-page-live'); if (m) m.textContent = msg; };

/** Step a block or a row, `delta` places among its own kind. */
export async function stepOnPage(el, id, delta) {
  const { entries } = el._pageLayout();
  const next = stepEntry(entries, id, delta);
  if (next === entries) return { ok: true, moved: false };
  await keep(el, next);
  const p = el._model.columns[id];
  say(el, `${p ? p.label : id} moved ${delta < 0 ? 'up' : 'down'}.`);
  return { ok: true, moved: true };
}

/** Put a block or a row at `index` of its own kind. */
export async function moveOnPage(el, id, index) {
  const { entries } = el._pageLayout();
  const next = moveEntry(entries, id, index);
  if (next !== entries) await keep(el, next);
}

export const showOnPage = (el, id, on) => keep(el, withVisible(el._pageLayout().entries, id, on));

/** What moving a property would do, nothing done: {ok, changes, total, note, reason}. No acceptPlace hook: only the layout changes. */
export async function previewPlace(el, id, to) { return askPlace(el, id, to, true); }

async function askPlace(el, id, to, dry) {
  const layout = el._pageLayout();
  const next = { ...layout, entries: withPlace(layout.entries, id, to) };
  const { value, text } = nextText(el, next);
  if (typeof el.acceptPlace !== 'function') return { ok: true, changes: 0, total: 0, layoutOnly: true, entries: next.entries, value, text };
  const from = (layout.entries.find((e) => e.id === id) || {}).place;
  let answer;
  try { answer = await el.acceptPlace({ property: id, from, to, dry, text, layout: value }); } catch (err) { answer = { ok: false, reason: err.message }; }
  return { ...(answer || { ok: false, reason: 'The host refused the change.' }), entries: next.entries, value, text };
}

/** Change a property's place: `acceptPlace` moves its data and writes the `.base`; with no hook it is a layout change. */
export async function setPlace(el, id, to) {
  const res = await askPlace(el, id, to, false);
  if (!res.ok) return res;
  if (typeof el.acceptPlace === 'function') adopt(el, res.value, res.text);
  else await keep(el, res.entries);
  const { entries, value, text, ...out } = res;
  el.dispatchEvent(new CustomEvent('data-views-place', { detail: { property: id, to, result: out } }));
  return out;
}

// ---------------------------------------------------------------- the menu on a property or a block
function menuHtml(el, e, p) {
  const places = Object.entries(PLACE_NAME).map(([place, name]) => `<button type="button" role="menuitemradio" class="dv-page-item" data-place-to="${place}" aria-checked="${e.place === place}">${esc(name)}</button>`).join('');
  return `<div role="menu" aria-label="${esc(p.label)}"><h4>${esc(p.label)}</h4>${places}<hr><button type="button" role="menuitem" class="dv-page-item" data-page-step="-1">Move up</button><button type="button" role="menuitem" class="dv-page-item" data-page-step="1">Move down</button><button type="button" role="menuitem" class="dv-page-item" data-page-show="${e.visible ? 0 : 1}">${e.visible ? 'Hide on the page' : 'Show on the page'}</button></div>`;
}

function openMenu(el, button, id) {
  const layout = el._pageLayout();
  const e = layout.entries.find((x) => x.id === id);
  const p = el._model.columns[id];
  if (!e || !p) return;
  el._pop(button, menuHtml(el, e, p), (pop) => {
    // WHY on the menu, not on .dv-pop: that element outlives every menu, and a listener left on it would answer for the next one too
    pop.firstElementChild.addEventListener('click', async (ev) => {
      // WHY stop it: the element closes its menu on a click outside .dv-pop, and this one's target is about to be replaced
      ev.stopPropagation();
      const t = ev.target.closest('button');
      if (!t) return;
      if (t.dataset.pageStep) { el.closeMenu(); await stepOnPage(el, id, Number(t.dataset.pageStep)); return; }
      if (t.dataset.pageShow) { el.closeMenu(); await showOnPage(el, id, t.dataset.pageShow === '1'); return; }
      if (t.dataset.placeTo) {
        const to = t.dataset.placeTo;
        if (to === e.place) { el.closeMenu(); return; }
        confirm(el, pop, id, to);
      }
    });
  }, 'dv-page-pop');
  fix(el);
}

/** WHY: in a full page the peek is fixed over everything, so its menu must be too, at the button's place on the screen. */
function fix(el) {
  const pop = el.$('.dv-pop');
  if (!el.classList.contains('dv-page-full') || !pop._for) return;
  const b = pop._for.getBoundingClientRect();
  pop.style.left = `${Math.max(8, Math.min(b.left, innerWidth - 300))}px`;
  pop.style.top = `${b.bottom + 6}px`;
}

async function confirm(el, pop, id, to) {
  const p = el._model.columns[id];
  pop.innerHTML = `<h4>${esc(p.label)} → ${esc(PLACE_NAME[to])}</h4><p class="dv-page-note">Working out what changes…</p>`;
  const res = await previewPlace(el, id, to);
  if (pop.hidden) return;
  const note = res.ok
    ? res.note || (res.layoutOnly ? `Only the page changes: ${p.label} draws ${to === 'top' ? 'in the property list' : 'as a section'}.` : `${res.changes} of ${res.total} change.`)
    : res.reason || 'The host refused the change.';
  pop.innerHTML = `<h4>${esc(p.label)} → ${esc(PLACE_NAME[to])}</h4><p class="dv-page-note${res.ok ? '' : ' dv-refused'}" data-place-note>${esc(note)}</p><div class="dv-page-actions">${res.ok ? `<button type="button" class="dv-btn dv-primary" data-place-go>${res.changes ? `Change ${res.changes} ${res.changes === 1 ? 'file' : 'files'}` : 'Apply'}</button>` : ''}<button type="button" class="dv-btn" data-place-no>Cancel</button></div>`;
  const first = pop.querySelector('[data-place-go], [data-place-no]');
  if (first) first.focus();
  const go = pop.querySelector('[data-place-go]');
  pop.querySelector('[data-place-no]').addEventListener('click', () => el.closeMenu());
  if (go) go.addEventListener('click', async () => {
    go.disabled = true;
    const done = await setPlace(el, id, to);
    if (done.ok) { el.closeMenu(); say(el, done.note || `${p.label} moved.`); return; }
    pop.querySelector('[data-place-note]').textContent = done.reason || 'The host refused the change.';
    go.disabled = false;
  });
}

// ---------------------------------------------------------------- the blocks' behaviour, delegated from the element
const live = (el) => { const id = el._peek && el._peek.id; const row = id !== undefined && el.row(id); return row ? { id, row } : null; };
const blockOf = (t) => (t && t.closest ? t.closest('[data-page-block]') : null);

function startEdit(el, block) {
  const at = live(el);
  if (!at || block.querySelector('textarea')) return;
  const id = block.dataset.pageBlock;
  const p = el._model.columns[id];
  const read = block.querySelector('[data-page-read]');
  if (!read) return;
  read.hidden = true;
  const box = document.createElement('div');
  box.className = 'dv-page-box';
  box.innerHTML = `<textarea name="${esc(id)}" rows="2" aria-label="${esc(p.label)}" spellcheck="true">${esc(text(at.row[id]))}</textarea><div class="dv-ed-foot"><span class="dv-ed-msg" role="alert"></span></div>`;
  read.after(box);
  const ta = box.querySelector('textarea');
  grow(ta);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}

async function commit(el, block) {
  const at = live(el);
  const ta = block.querySelector('textarea');
  if (!at || !ta) return;
  const id = block.dataset.pageBlock;
  if (ta.value === text(at.row[id])) { stopEdit(el, block); return; }
  const res = await el.propose({ id: at.id, set: { [id]: ta.value } });
  if (res && res.ok) { stopEdit(el, block, true); return; }
  const m = block.querySelector('.dv-ed-msg');
  if (m) m.textContent = `Not saved: ${(res && res.reason) || 'the host refused the edit'}`;
}

function stopEdit(el, block, redraw) {
  const box = block.querySelector('.dv-page-box');
  // WHY marked first: the box's blur must not commit what Esc just threw away
  if (box) { box.dataset.closing = '1'; box.querySelector('textarea').blur(); box.remove(); }
  const read = block.querySelector('[data-page-read]');
  if (read) read.hidden = false;
  if (redraw) el.refreshPeek();
}

async function insertFiles(el, block, files) {
  const at = live(el);
  if (!at) return;
  startEdit(el, block);
  const ta = block.querySelector('textarea');
  const msg = block.querySelector('.dv-ed-msg');
  if (!ta) return;
  for (const file of files) {
    if (msg) msg.textContent = 'attaching…';
    const res = await el.attachFile(file, { id: at.id, property: block.dataset.pageBlock });
    if (!res.ok || !res.attachment) { if (msg) msg.textContent = `Not attached: ${res.reason || 'the host refused it'}`; return; }
    const a = res.attachment;
    const line = a.embed || `![${(a.name || 'image').replace(/[[\]]/g, '')}](${a.ref || a.url})`;
    const from = ta.selectionStart, to = ta.selectionEnd;
    const before = ta.value.slice(0, from), after = ta.value.slice(to);
    const lead = !before || before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
    ta.value = `${before}${lead}${line}\n${after}`;
    ta.selectionStart = ta.selectionEnd = before.length + lead.length + line.length + 1;
    if (msg) msg.textContent = '';
    grow(ta);
  }
  ta.focus();
}

function wireDrag(el) {
  let drag = null;
  const items = (d) => [...d.host.querySelectorAll(':scope > [data-page-entry]')].filter((n) => !n.classList.contains('dv-page-off'));
  const spot = (d, y) => {
    const list = items(d).filter((n) => n !== d.node);
    let i = list.findIndex((n) => { const r = n.getBoundingClientRect(); return y < r.top + r.height / 2; });
    if (i < 0) i = list.length;
    return { i, list };
  };
  const drawLine = (d, y) => {
    const { i, list } = spot(d, y);
    const peek = el.$('.dv-peek');
    const line = d.line;
    const box = peek.getBoundingClientRect(), hostBox = d.host.getBoundingClientRect();
    const r = list[i] ? list[i].getBoundingClientRect().top - 2 : (list.length ? list[list.length - 1].getBoundingClientRect().bottom + 2 : hostBox.top);
    line.style.top = `${r - box.top + peek.scrollTop}px`;
    line.style.left = `${hostBox.left - box.left}px`;
    line.style.width = `${hostBox.width}px`;
  };
  const end = (e, cancel) => {
    const d = drag;
    drag = null;
    if (!d) return;
    d.node.classList.remove('dv-page-dragging');
    d.line?.remove();
    document.documentElement.classList.remove('dv-page-moving');
    if (cancel || !d.moved) return;
    const { i } = spot(d, e.clientY);
    moveOnPage(el, d.id, i);
  };
  el.addEventListener('pointerdown', (e) => {
    const g = e.target.closest && e.target.closest('[data-page-grip]');
    if (!g || e.button !== 0) return;
    const node = g.closest('[data-page-entry]');
    e.preventDefault();
    g.setPointerCapture(e.pointerId);
    drag = { id: node.dataset.pageEntry, node, host: node.parentElement, y: e.clientY, moved: false, g };
  });
  el.addEventListener('pointermove', (e) => {
    if (!drag) return;
    if (!drag.moved) {
      if (Math.abs(e.clientY - drag.y) < 4) return;
      drag.moved = true;
      drag.node.classList.add('dv-page-dragging');
      document.documentElement.classList.add('dv-page-moving');
      drag.line = document.createElement('div');
      drag.line.className = 'dv-page-dropline';
      el.$('.dv-peek').append(drag.line);
    }
    drawLine(drag, e.clientY);
  });
  el.addEventListener('pointerup', (e) => end(e, false));
  el.addEventListener('pointercancel', (e) => end(e, true));
  // a key during a drag is Escape's: the drag stops, nothing moved
  el.addEventListener('keydown', (e) => { if (drag && e.key === 'Escape') { e.stopPropagation(); end(e, true); } }, true);
}

/** Delegated from the element, as the §38 sections are: a redraw of the peek replaces the blocks, the listeners stay. */
export function wirePage(el) {
  wireDrag(el);
  el.addEventListener('click', (e) => {
    const t = e.target;
    if (!t.closest) return;
    const menu = t.closest('[data-page-menu]');
    if (menu) { e.stopPropagation(); openMenu(el, menu, menu.closest('[data-page-entry]').dataset.pageEntry); return; }
    if (t.closest('[data-page-hidden]')) { el._pageHiddenOpen = !el._pageHiddenOpen; el._redrawPage(); return; }
    const img = t.closest('[data-page-zoom]');
    if (img) {
      const list = [...img.closest('[data-page-block]').querySelectorAll('img[data-page-zoom]')];
      el.showMedia(list.map((n) => ({ url: n.src, kind: 'image', name: n.alt })), list.indexOf(img));
      return;
    }
    const note = t.closest('[data-page-note]');
    if (note) { e.preventDefault(); el._open.follow(note.dataset.pageNote); return; }
    if (t.closest('a, video')) return;
    const read = t.closest('[data-page-read]');
    if (read) startEdit(el, read.closest('[data-page-block]'));
  });
  el.addEventListener('keydown', (e) => {
    const t = e.target;
    const g = t.closest && t.closest('[data-page-grip]');
    if (g && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      e.stopPropagation();
      const id = g.closest('[data-page-entry]').dataset.pageEntry;
      stepOnPage(el, id, e.key === 'ArrowUp' ? -1 : 1).then(() => {
        const again = [...el.querySelectorAll('.dv-peek [data-page-entry]')].find((n) => n.dataset.pageEntry === id);
        const next = again && again.querySelector('[data-page-grip]');
        if (next) next.focus();
      });
      return;
    }
    if (t.matches && t.matches('[data-page-read]') && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); startEdit(el, t.closest('[data-page-block]')); return; }
    const block = blockOf(t);
    if (block && t.tagName === 'TEXTAREA' && e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); t.blur(); }
  });
  // WHY captured: the element's own Escape closes the peek, and a listener at the same level cannot stop it
  el.addEventListener('keydown', (e) => {
    const block = blockOf(e.target);
    if (!block || e.target.tagName !== 'TEXTAREA' || e.key !== 'Escape') return;
    e.stopPropagation();
    stopEdit(el, block);
    const read = block.querySelector('[data-page-read]');
    if (read) read.focus();
  }, true);
  el.addEventListener('input', (e) => { if (blockOf(e.target) && e.target.tagName === 'TEXTAREA') grow(e.target); });
  el.addEventListener('focusout', (e) => {
    const block = blockOf(e.target);
    if (block && e.target.tagName === 'TEXTAREA' && document.hasFocus() && !(e.relatedTarget && block.contains(e.relatedTarget)) && !e.target.closest('[data-closing]')) commit(el, block);
  });
  el.addEventListener('change', (e) => {
    const box = e.target.closest && e.target.closest('[data-page-field]');
    const at = box && live(el);
    if (!at) return;
    const set = readEdits(box, at.row, el._model.columns);
    if (Object.keys(set).length) el.propose({ id: at.id, set }).then((res) => { if (!(res && res.ok)) say(el, `Not saved: ${(res && res.reason) || 'the host refused the edit'}`); });
  });
  el.addEventListener('paste', (e) => {
    const block = blockOf(e.target);
    const files = [...((e.clipboardData && e.clipboardData.files) || [])];
    if (block && files.length && typeof el.acceptFile === 'function') { e.preventDefault(); insertFiles(el, block, files); }
  });
  el.addEventListener('dragover', (e) => {
    const block = blockOf(e.target);
    if (block && block.querySelector('[data-page-read]') && typeof el.acceptFile === 'function' && e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault();
  });
  el.addEventListener('drop', (e) => {
    const block = blockOf(e.target);
    const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
    if (block && files.length && block.querySelector('[data-page-read]') && typeof el.acceptFile === 'function') { e.preventDefault(); insertFiles(el, block, files); }
  });
}

/** A click on a derived cell (an outline) opens its section: there, in view, with its box open. */
export function revealBlock(el, column) {
  const block = [...el.querySelectorAll('.dv-peek [data-page-block]')].find((n) => n.dataset.pageBlock === column);
  if (!block) return;
  block.scrollIntoView({ block: 'start' });
  if (block.querySelector('[data-page-read]')) startEdit(el, block);
}

/** Size what is open once the peek is drawn. */
export function fitPage(peek) { for (const ta of peek.querySelectorAll('[data-page-block] textarea')) grow(ta); }
