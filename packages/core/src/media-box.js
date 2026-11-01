/* A thumbnail, large: the kit's viewer for a media cell (docs/CONTRACT.md §37). A native <dialog>, so the modal focus trap,
   Esc and the top layer are the browser's. A host with its own viewer takes data-views-media and this never opens.
   list: [{url, kind, caption?, name?}], urls already resolved. */

import { esc } from './format.js';

export function openMediaBox(el, list, index = 0) {
  if (!list.length) return null;
  const dialog = document.createElement('dialog');
  dialog.className = 'dv-mediabox';
  dialog.setAttribute('aria-label', 'Media viewer');
  let at = Math.max(0, Math.min(list.length - 1, index));
  const draw = () => {
    const a = list[at];
    const word = a.caption || a.name || (a.kind === 'video' ? 'Video' : 'Image');
    const body = a.kind === 'video' ? `<video src="${esc(a.url)}" controls playsinline aria-label="${esc(word)}"></video>` : `<img src="${esc(a.url)}" alt="${esc(word)}">`;
    dialog.innerHTML = `<div class="dv-mb-bar"><span class="dv-mb-n">${at + 1} / ${list.length}</span><span class="dv-mb-cap">${esc(word)}</span><button type="button" class="dv-btn dv-mb-close" aria-label="Close">✕</button></div><div class="dv-mb-stage">${list.length > 1 ? '<button type="button" class="dv-btn dv-mb-nav" data-go="-1" aria-label="Previous">‹</button>' : ''}${body}${list.length > 1 ? '<button type="button" class="dv-btn dv-mb-nav" data-go="1" aria-label="Next">›</button>' : ''}</div>`;
  };
  const go = (d) => { at = (at + d + list.length) % list.length; draw(); };
  dialog.addEventListener('click', (e) => {
    const nav = e.target.closest('[data-go]');
    if (nav) go(Number(nav.dataset.go));
    else if (e.target.closest('.dv-mb-close') || e.target === dialog) dialog.close();
  });
  dialog.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' && list.length > 1) { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft' && list.length > 1) { e.preventDefault(); go(-1); }
  });
  dialog.addEventListener('close', () => dialog.remove());
  draw();
  el.append(dialog);
  dialog.showModal();
  return dialog;
}
