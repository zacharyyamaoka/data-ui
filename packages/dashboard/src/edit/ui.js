/* Small shared parts of the editor: its icons, a menu, the one modal it asks with (Exit's question), and a diff as a
   reviewer reads it. Colours are the kit's --dv-* tokens, by way of edit.css. */

import { esc } from '../../../core/src/format.js';
import { hunks, TYPE_NAMES } from './ops.js';

// 16 px strokes, the kit's toolbar weight
const PATHS = {
  timeseries: '<path d="M2 12 L6 7 L9 9.5 L14 4"/>',
  chart: '<path d="M3 13V8M8 13V4M13 13V10"/>',
  table: '<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><path d="M2.5 6.5h11M6.5 6.5V13"/>',
  kpi: '<path d="M2.5 11.5a5.5 5.5 0 0 1 11 0"/><path d="M8 11.5l2.6-3.2"/>',
  list: '<path d="M5 4h8M5 8h8M5 12h8M2.5 4h.01M2.5 8h.01M2.5 12h.01"/>',
  playback: '<path d="M5 3.5v9l7-4.5z"/>',
  text: '<path d="M3 4h10M8 4v9M5.5 13h5"/>',
  grip: '<path d="M6 4h.01M10 4h.01M6 8h.01M10 8h.01M6 12h.01M10 12h.01"/>',
  eye: '<path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="1.8"/>',
  eyeoff: '<path d="M2 2l12 12M6.6 6.7a2 2 0 0 0 2.7 2.7M4.1 4.6C2.5 5.8 1.5 8 1.5 8s2.4 4.5 6.5 4.5c1.4 0 2.6-.5 3.6-1.1M7 3.6c.3 0 .7-.1 1-.1 4.1 0 6.5 4.5 6.5 4.5s-.5 1-1.5 2.1"/>',
  out: '<path d="M9 4h4.5v8.5H9M2.5 8h7M7 5.5 9.5 8 7 10.5"/>',
  undo: '<path d="M5 3L2 6l3 3"/><path d="M2 6h7a4 4 0 0 1 0 8H6"/>',
  redo: '<path d="M11 3l3 3-3 3"/><path d="M14 6H7a4 4 0 0 0 0 8h3"/>',
  left: '<path d="M10 3.5 5.5 8l4.5 4.5"/>',
  right: '<path d="M6 3.5 10.5 8 6 12.5"/>',
  up: '<path d="M8 13V3.5M4 7.5l4-4 4 4"/>',
  down: '<path d="M8 3v9.5M4 8.5l4 4 4-4"/>',
};

export const icon = (name) => `<svg class="dde-ico" viewBox="0 0 16 16" aria-hidden="true">${PATHS[name] || PATHS.table}</svg>`;
export const typeIcon = (type) => icon(PATHS[type] ? type : 'table');
export const typeName = (type) => TYPE_NAMES[type] || (type ? type[0].toUpperCase() + type.slice(1) : 'Table');

let openMenu = null;

/** A menu beside `anchor`: items [{label, run, sep?}]. A press outside, Escape or a pick closes it; ↑/↓ move between items. */
export function menu(anchor, items, { label = 'Menu' } = {}) {
  if (openMenu) openMenu();
  const node = document.createElement('div');
  node.className = 'dde-menu data-ui';
  node.setAttribute('role', 'menu');
  node.setAttribute('aria-label', label);
  node.innerHTML = items.map((it, i) => (it.sep ? '<div class="dde-sep" role="separator"></div>' : `<button type="button" role="menuitem" class="dde-mi" data-i="${i}"${it.test ? ` data-dde="${esc(it.test)}"` : ''}>${esc(it.label)}</button>`)).join('');
  document.body.append(node);
  const r = anchor.getBoundingClientRect();
  const m = node.getBoundingClientRect();
  node.style.left = `${Math.max(8, Math.min(r.right - m.width, innerWidth - m.width - 8))}px`;
  node.style.top = `${r.bottom + m.height + 12 > innerHeight ? Math.max(8, r.top - m.height - 4) : r.bottom + 4}px`;
  const close = (refocus = false) => {
    node.remove();
    document.removeEventListener('pointerdown', away, true);
    document.removeEventListener('keydown', key, true);
    anchor.setAttribute('aria-expanded', 'false');
    openMenu = null;
    if (refocus) anchor.focus();
  };
  const away = (e) => { if (!node.contains(e.target) && !anchor.contains(e.target)) close(); };
  const key = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const btns = [...node.querySelectorAll('.dde-mi')];
    btns[(btns.indexOf(document.activeElement) + (e.key === 'ArrowDown' ? 1 : -1) + btns.length) % btns.length].focus();
  };
  node.addEventListener('click', (e) => {
    const b = e.target.closest('.dde-mi');
    if (!b) return;
    close();
    items[Number(b.dataset.i)].run();
  });
  document.addEventListener('pointerdown', away, true);
  document.addEventListener('keydown', key, true);
  anchor.setAttribute('aria-expanded', 'true');
  openMenu = close;
  node.querySelector('.dde-mi').focus();
}

/** Exit's question: resolves the value of the button pressed, or null on Escape. */
export function confirmDialog({ title, body, buttons }) {
  return new Promise((resolve) => {
    const d = document.createElement('dialog');
    d.className = 'dde-dialog data-ui';
    d.innerHTML = `<h3>${esc(title)}</h3><p>${esc(body)}</p><div class="dde-actions">${buttons.map((b, i) => `<button type="button" class="dde-btn${b.primary ? ' dde-primary' : ''}" data-i="${i}" data-dde="${esc(b.value || 'cancel')}">${esc(b.label)}</button>`).join('')}</div>`;
    document.body.append(d);
    const done = (value) => { d.close(); d.remove(); resolve(value); };
    d.addEventListener('click', (e) => { const b = e.target.closest('[data-i]'); if (b) done(buttons[Number(b.dataset.i)].value); });
    d.addEventListener('cancel', (e) => { e.preventDefault(); done(null); });
    d.showModal();
  });
}

/** The changed lines with two lines of context, numbered as the new file is (old numbers for removed lines). */
export function diffHtml(diff) {
  const rows = hunks(diff, 2);
  if (!rows.length) return '<p class="dde-note">No changes.</p>';
  return `<pre class="dde-diff" tabindex="0" aria-label="Changes to the .base file">${rows.map((d) => (d.op === '…' ? '<span class="dde-dl dde-dgap">⋯</span>'
    : `<span class="dde-dl dde-d${d.op === '+' ? 'add' : d.op === '-' ? 'del' : 'ctx'}" data-line="${esc(d.line)}"><i>${d.op === '-' ? d.a : d.b}</i><b>${d.op === ' ' ? ' ' : d.op}</b><span>${esc(d.line)}</span></span>`)).join('')}</pre>`;
}

/** The change list as a reader reads it: one line per change. */
export function changesHtml(changes) {
  return changes.length ? `<ul class="dde-changes">${changes.map((c) => `<li data-kind="${esc(c.kind)}">${esc(c.detail)}</li>`).join('')}</ul>` : '';
}
