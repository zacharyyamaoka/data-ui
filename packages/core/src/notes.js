/* Text around a view (docs/CONTRACT.md §28): Markdown blocks before and after it, and a view's "About" note on demand.

   WHY (Zach, 2026-10-26, on the inline intro paragraph between the KPI cards and the rows: "I generally don't like how
   this text looks just there… super messy. If you want to add text, put it before or after, or support a Markdown block
   in the dashboard, or use tooltips"):
   - `before:` / `after:` (on the file's top level, or a view's own, which wins): a Markdown block drawn as a document
     (headings, lists, a readable measure) above the view's tabs or below its rows: text sits beside the view, never
     inside its chrome;
   - `intro.text` (CONTRACT §16) is no longer a paragraph in the view: it is the view's About note, one click away
     (ⓘ About in the status line), so the answer (the KPI cards, the rows) comes first and the reading guide on demand —
     the calm-UI rule (feedback_calm_ui_progressive_disclosure: one calm answer first, detail on demand);
   - a property's `description` is its header's tooltip (the table view). */

import { markdown } from './md.js';
import { esc } from './format.js';

/** Draw (or remove) the before and after blocks for the element's current view. */
export function drawNotes(el) {
  const view = el.view || {}, base = el.base || {};
  for (const where of ['before', 'after']) {
    const md = view[where] ?? base[where];
    let block = el.querySelector(`:scope > .dv-note-${where}`);
    if (!md) { if (block) block.remove(); continue; }
    if (!block) {
      block = document.createElement('section');
      block.className = `dv-note dv-note-${where} dv-md`;
      block.setAttribute('aria-label', where === 'before' ? 'Before this view' : 'After this view');
      if (where === 'before') el.prepend(block);
      else { const stage = el.querySelector(':scope > .dv-stage'); if (stage) stage.after(block); else el.append(block); }
    }
    if (block._md !== md) { block.innerHTML = markdown(String(md)); block._md = md; }
  }
}

/** The status line's About button, when the view has an intro text. */
export function aboutButton(view) {
  const text = view && view.intro && view.intro.text;
  return text ? `<button class="dv-link dv-about" data-about aria-haspopup="dialog" title="How to read this view">ⓘ About this view</button>` : '';
}

/** Wire the About button once: its popover is the element's own menu popover, with the note rendered as Markdown. */
export function mountNotes(el) {
  // once per element: _start re-runs on a new .base, and the element (where this listens) outlives its contents
  if (el._notesMounted) return;
  el._notesMounted = true;
  el.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-about]');
    if (!b || !el.contains(b)) return;
    const text = el.view && el.view.intro && el.view.intro.text;
    if (!text) return;
    el._pop(b, `<h4>${esc(el.view.name || 'About this view')}</h4><div class="dv-md dv-about-text">${markdown(String(text))}</div>`);
  });
}
