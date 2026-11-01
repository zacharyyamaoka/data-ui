/* A record's long properties as a page (docs/CONTRACT.md §38): Notion's side page. Short properties stay rows at the top; a
   media or long-text property is a full-width section under them, its name a heading, written in right there.

   Zach, 2026-10-30: "yes you can kinda like open each of thoose rows and look at them individually in detail" and "mabye are
   best done with like H1 headers on a page". WHY the section is the editor, always, with no click to open one: on a page you
   just type. Leaving it commits through propose, as the table's cell does; Esc puts back what the row says. Enter is a new line,
   as it is on a page; Cmd or Ctrl + Enter commits. */

import { cellValue } from './grammar.js';
import { esc, isEmpty, attachmentsOf, thumbsHtml, mediaUrl, withValue } from './format.js';
import { lockedBecause } from './form.js';

/** Whether a property is a section of the page, not a row: `display: media` (the view's or its own), or `long: true`. */
export function isLong(p, view) {
  return !!p && (p.long === true || ((view && view.display && view.display[p.id]) || p.display) === 'media');
}

const text = (cell) => { const v = cellValue(cell); return isEmpty(v) ? '' : Array.isArray(v) ? v.join(', ') : String(v); };
const draft = (list, base) => list.map((a, i) => `<span class="dv-ed-thumb">${a.kind === 'video' ? '<span class="dv-ed-video">video</span>' : `<img src="${esc(mediaUrl(a.url, base))}" alt="" draggable="false">`}<button type="button" class="dv-ed-x" data-page-unattach="${i}" aria-label="Remove this attachment" title="Remove">×</button></span>`).join('');

/** One section: read-only, the words and thumbnails; on an editable row, the box itself. '' when it is empty and locked. */
export function sectionHtml(el, row, p, view) {
  const cell = row[p.id];
  const locked = !el.editing || lockedBecause(p) || row._readOnly || view.edit === true;
  const media = attachmentsOf(cell);
  const base = { url: el.dataUrl };
  const head = `<h2 class="dv-page-h">${esc(p.label)}</h2>`;
  const body = locked
    ? `<div class="dv-page-text">${esc(text(cell))}</div><span class="dv-peek-media" data-peek-media="${esc(p.id)}">${thumbsHtml(cell, base)}</span>`
    : `<div class="dv-page-box"><textarea name="${esc(p.id)}" rows="2" placeholder="${esc(p.label)}" aria-label="${esc(p.label)}" spellcheck="true">${esc(text(cell))}</textarea><div class="dv-ed-thumbs">${draft(media.filter((a) => a.url && !a.missing), base)}</div><div class="dv-ed-foot"><span class="dv-ed-msg" role="alert"></span>${typeof el.acceptFile === 'function' && isMedia(p, view) ? '<button type="button" class="dv-mc-add" data-page-pick>+ image or video</button>' : ''}</div></div>`;
  if (locked && !text(cell) && !media.length) return '';
  return `<section class="dv-page-sec dv-peek-field" data-page-sec="${esc(p.id)}" data-p="${esc(p.id)}">${head}${body}</section>`;
}

const isMedia = (p, view) => ((view && view.display && view.display[p.id]) || p.display) === 'media';
const grow = (ta) => { ta.style.height = 'auto'; ta.style.height = `${ta.scrollHeight + 2}px`; };

/** The sections' behaviour, delegated from the element: a redraw of the peek replaces them, the listeners stay. */
export function wireSections(el) {
  const secOf = (t) => (t && t.closest ? t.closest('[data-page-sec]') : null);
  const live = (sec) => { const id = el._peek && el._peek.id; return id !== undefined && el.row(id) ? { id, row: el.row(id), p: sec.dataset.pageSec } : null; };
  const state = new WeakMap();
  const media = (sec, at) => {
    if (!state.has(sec)) state.set(sec, attachmentsOf(at.row[at.p]).map((a) => ({ ...a })));
    return state.get(sec);
  };
  const say = (sec, msg) => { const m = sec.querySelector('.dv-ed-msg'); if (m) m.textContent = msg; };
  const paint = (sec, at) => { sec.querySelector('.dv-ed-thumbs').innerHTML = draft(media(sec, at).filter((a) => a.url && !a.missing), { url: el.dataUrl }); };
  const commit = async (sec) => {
    const at = live(sec);
    const ta = sec.querySelector('textarea');
    if (!at || !ta) return;
    const cell = at.row[at.p];
    const list = media(sec, at);
    const was = attachmentsOf(cell);
    if (ta.value === text(cell) && JSON.stringify(list) === JSON.stringify(was)) return;
    const rest = cell !== null && typeof cell === 'object' && !Array.isArray(cell) ? cell : {};
    const next = isMedia(el._model.columns[at.p], el.view) ? { ...withValue(rest, ta.value), attachments: list } : ta.value;
    const res = await el.propose({ id: at.id, set: { [at.p]: next } });
    say(sec, res && res.ok ? '' : `Not saved: ${(res && res.reason) || 'the host refused the edit'}`);
  };
  const take = async (sec, files) => {
    const at = live(sec);
    if (!at) return;
    for (const file of files) {
      say(sec, 'attaching…');
      const res = await el.attachFile(file, { id: at.id, property: at.p });
      if (!res.ok || !res.attachment) { say(sec, `Not attached: ${res.reason || 'the host refused it'}`); return; }
      media(sec, at).push(res.attachment);
      say(sec, '');
    }
    paint(sec, at);
    commit(sec);
  };
  el.addEventListener('input', (e) => { if (secOf(e.target) && e.target.tagName === 'TEXTAREA') grow(e.target); });
  el.addEventListener('focusout', (e) => {
    const sec = secOf(e.target);
    if (sec && e.target.tagName === 'TEXTAREA' && !sec.contains(e.relatedTarget) && document.hasFocus()) commit(sec);
  });
  el.addEventListener('keydown', (e) => {
    const sec = secOf(e.target);
    if (!sec || e.target.tagName !== 'TEXTAREA') return;
    if (e.key === 'Escape') {
      e.stopPropagation();
      const at = live(sec);
      if (at) { e.target.value = text(at.row[at.p]); grow(e.target); }
      e.target.blur();
    } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.target.blur(); }
  });
  el.addEventListener('mousedown', (e) => { if (secOf(e.target) && e.target.closest('button')) e.preventDefault(); });
  el.addEventListener('click', (e) => {
    const sec = secOf(e.target);
    if (!sec) return;
    const un = e.target.closest('[data-page-unattach]');
    const at = live(sec);
    if (un && at) { media(sec, at).splice(Number(un.dataset.pageUnattach), 1); paint(sec, at); commit(sec); return; }
    if (e.target.closest('[data-page-pick]')) {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*,video/*'; input.multiple = true;
      input.addEventListener('change', () => take(sec, [...input.files]));
      input.click();
    }
  });
  el.addEventListener('paste', (e) => {
    const sec = secOf(e.target);
    const files = [...((e.clipboardData && e.clipboardData.files) || [])];
    if (sec && files.length && sec.querySelector('[data-page-pick]')) { e.preventDefault(); take(sec, files); }
  });
  el.addEventListener('dragover', (e) => { const sec = secOf(e.target); if (sec && sec.querySelector('[data-page-pick]') && e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
  el.addEventListener('drop', (e) => {
    const sec = secOf(e.target);
    const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
    if (sec && files.length && sec.querySelector('[data-page-pick]')) { e.preventDefault(); take(sec, files); }
  });
}

/** Size the boxes once the peek is drawn. */
export function fitSections(peek) { for (const ta of peek.querySelectorAll('[data-page-sec] textarea')) grow(ta); }
