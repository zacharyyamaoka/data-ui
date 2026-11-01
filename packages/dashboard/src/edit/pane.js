/* The editor's side panels: one component, so every one of them has what Zach's rule asks of a side panel (memory
   feedback_resizable_panels; CONTRACT §11; /rate bad 2026-10-26: "put it in every UI brief and enforce it in the component"):
   a boundary that drags, a width remembered per reader, a double-click that resets it, and a fold that gives the grid the
   room, by a button or a key, remembered too. Nothing else in edit/ makes an <aside> or calls makeResizable, and
   tests/browser/dash_editor_checks.py measures every [data-dde-pane] it finds on the page.

   WHY inside the element, not around it: moving a host's <data-dashboard> into a shell would disconnect it, and every
   panel's <data-views> with it. The panes are children the dashboard's redraw leaves alone (index.js _draw). */

import { makeResizable } from '../../../core/src/resize.js';
import { esc } from '../../../core/src/format.js';
import { icon } from './ui.js';

const key = (name) => `data-ui/dash-edit/folded/${name}`;
const read = (name) => { try { return localStorage.getItem(key(name)); } catch { return null; } };
const write = (name, on) => { try { localStorage.setItem(key(name), on ? '1' : '0'); } catch { /* private window: this visit only */ } };

/** A side panel of `dash`, on `side` of its body: {el, body, title(text), fold(on, {remember}), folded, destroy()}. */
export function makePane(dash, { name, side, min, max, label, heading }) {
  const el = document.createElement('aside');
  el.className = `dde-pane dde-pane-${side}`;
  el.dataset.ddePane = name;
  el.setAttribute('aria-label', label);
  const bodyId = `${dash.id}-dde-${name}`;
  el.innerHTML = `<header class="dde-pane-h"><h3>${esc(heading)}</h3><button type="button" class="dde-fold" aria-controls="${esc(bodyId)}"></button></header><div class="dde-pane-b" id="${esc(bodyId)}"></div>`;
  const anchor = dash.querySelector(':scope > .dd-body');
  if (side === 'left') anchor.before(el); else anchor.after(el);
  // the handle sits on the edge that faces the grid
  const edge = side === 'left' ? 'right' : 'left';
  el.dataset.resizable = edge;
  const ctl = makeResizable(el, { edge, min, max, keep: 320, key: `dash-edit-${name}`, label });
  const btn = el.querySelector('.dde-fold');
  const body = el.querySelector('.dde-pane-b');
  const paint = (on) => {
    btn.setAttribute('aria-expanded', String(!on));
    const verb = on ? 'Show' : 'Fold';
    btn.setAttribute('aria-label', `${verb} ${label}`);
    btn.title = `${verb} ${label}`;
    btn.innerHTML = icon(on === (side === 'left') ? 'right' : 'left');
  };
  const pane = {
    el, body, ctl,
    get folded() { return el.hasAttribute('data-folded'); },
    heading(text) { el.querySelector('.dde-pane-h h3').textContent = text; },
    fold(on, { remember = true } = {}) {
      el.toggleAttribute('data-folded', on);
      body.hidden = on;
      paint(on);
      if (remember) write(name, on);
    },
    destroy() { ctl.destroy(); el.remove(); },
  };
  btn.addEventListener('click', () => pane.fold(!pane.folded));
  pane.fold(read(name) === '1', { remember: false });
  return pane;
}
