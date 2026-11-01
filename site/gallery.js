// The Examples index (gallery/index.html): a picture per case, compact filters and search, a column slider, two
// groupings (view type, Vega-Lite's way, or app) and five layouts behind a temporary switcher (bottom right). The kit
// itself is loaded by site.js.
// WHY five layouts, each a UI or data-viz library's examples page: Zach, 2026-10-26: "For me the more relevant prior
// art is other UI libraries and how they do their galleries"; switchable in the page, never a URL flag, remembered.
// reports/data-ui-gallery-2026-10-26.html shows each beside its library.
import { makeResizable } from '../kit/data-ui.js';

const main = document.querySelector('main.gallery');
const rows = JSON.parse(document.getElementById('gallery-data').textContent);
const bySlug = new Map(rows.map((r) => [r.slug, r]));
const store = {
  get(k) { try { return localStorage.getItem('data-ui-gallery/' + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem('data-ui-gallery/' + k, String(v)); } catch { /* private window: lasts this visit */ } },
};
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// each layout: its library, its default columns, the narrowest a tile may get, and which side panels it has
// WHY Index first: Zach, 2026-10-26: "OK go ahead with Index as the default" (round one's Observable-style grid),
// with Vega-Lite's contents by view type on top; the others stay behind the switcher
export const LAYOUTS = {
  index: { label: 'Index', art: 'Index: Observable grid + Vega-Lite contents', cols: 5, min: 150 },
  shadcn: { label: 'shadcn', art: 'shadcn/ui blocks: live preview + .base', cols: 2, min: 380 },
  echarts: { label: 'ECharts', art: 'Apache ECharts examples', cols: 5, min: 150, rail: true },
  antd: { label: 'Ant Design', art: 'Ant Design components overview', cols: 5, min: 170 },
  storybook: { label: 'Storybook', art: 'Storybook docs (sidebar, canvas, Docs)', cols: 4, min: 160, rail: true, docs: true },
};
const DEFAULT_LAYOUT = 'index';
const MAX_COLS = 8;
let layout = DEFAULT_LAYOUT;
let groupBy = store.get('group') === 'app' ? 'app' : 'type';
let chosen = 5;

// ---- grouping: the cards move between the view-type sections and the app sections
const cards = [...main.querySelectorAll('.card')];
const sections = (kind) => [...main.querySelectorAll(kind === 'app' ? '.app-group' : '.type-group')];
function regroup() {
  const target = new Map(sections(groupBy).map((s) => [s.dataset.group, s.querySelector('.cards')]));
  for (const row of rows) {
    const card = main.querySelector(`#case-${CSS.escape(row.slug)}`);
    target.get(groupBy === 'app' ? row.app : row.category).append(card);
  }
  main.dataset.groupBy = groupBy;
  for (const b of main.querySelectorAll('.group-by button')) b.setAttribute('aria-pressed', String(b.dataset.groupBy === groupBy));
}
main.querySelector('.group-by').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-group-by]');
  if (!b) return;
  groupBy = b.dataset.groupBy;
  store.set('group', groupBy);
  regroup();
  applyFilters();
});

// ---- filters and search (the chips' choice is in the URL: ?app=robotparts&type=graph)
const filters = main.querySelector('.filters');
const search = main.querySelector('.g-search');
const want = { app: '', type: '', q: '' };
try { const q = new URLSearchParams(location.search); want.app = q.get('app') || ''; want.type = q.get('type') || ''; } catch { /* no URL state */ }
const haystack = new Map(rows.map((r) => [r.slug, [r.title, r.summary, r.app, r.category, ...r.views.map((v) => `${v.name} ${v.type}`)].join(' ').toLowerCase()]));
function applyFilters() {
  let shown = 0;
  const words = want.q.toLowerCase().split(/\s+/).filter(Boolean);
  for (const c of cards) {
    const text = haystack.get(c.dataset.slug);
    const ok = (!want.app || c.dataset.app === want.app) && (!want.type || c.dataset.types.split(' ').includes(want.type)) && words.every((w) => text.includes(w));
    c.hidden = !ok;
    if (ok) shown++;
  }
  for (const g of main.querySelectorAll('.group')) {
    const n = g.querySelectorAll('.card:not([hidden])').length;
    g.hidden = !n;
    g.querySelector('h2 .n').textContent = String(n);
  }
  for (const chips of filters.querySelectorAll('.chips')) {
    for (const b of chips.querySelectorAll('.chip')) b.setAttribute('aria-pressed', String(b.dataset.value === want[chips.dataset.filter]));
  }
  main.querySelector('.filter-count span').textContent = String(shown);
  main.querySelector('.empty-note').hidden = shown > 0;
  try {
    const q = new URLSearchParams();
    if (want.app) q.set('app', want.app);
    if (want.type) q.set('type', want.type);
    history.replaceState(null, '', `${location.pathname}${q.toString() ? '?' + q : ''}`);
  } catch { /* a sandboxed frame: the filter still works */ }
  drawToc();
  if (LAYOUTS[layout].docs && (!inspected || inspected.hidden)) inspect(cards.find((c) => !c.hidden));
}
filters.addEventListener('click', (e) => {
  const b = e.target.closest('.chip');
  if (!b) return;
  want[b.closest('.chips').dataset.filter] = b.dataset.value;
  applyFilters();
});
search.addEventListener('input', () => { want.q = search.value; applyFilters(); });
main.querySelector('[data-clear]').addEventListener('click', () => { want.app = ''; want.type = ''; want.q = ''; search.value = ''; applyFilters(); });

// ---- the table of contents: Vega-Lite's nested outline, ECharts' category list, Storybook's tree
const toc = main.querySelector('.toc');
function drawToc() {
  const groups = sections(groupBy).filter((s) => !s.hidden);
  const visible = (s) => [...s.querySelectorAll('.card:not([hidden])')].map((c) => bySlug.get(c.dataset.slug));
  if (layout === 'storybook') {
    toc.innerHTML = groups.map((s) => `<details open><summary><a href="#${s.id}">${escapeHtml(s.dataset.group)}</a></summary><ul>${visible(s).map((r) => `<li><details><summary><a href="#case-${r.slug}" data-case="${r.slug}">${escapeHtml(r.title)}</a></summary><ul>${r.views.map((v, i) => `<li><a href="${r.href}${i ? `#view=${v.slug}` : ''}"><code>${v.type}</code> ${escapeHtml(v.name)}</a></li>`).join('')}</ul></details></li>`).join('')}</ul></details>`).join('');
  } else if (layout === 'index') {
    toc.innerHTML = `<ul>${groups.map((s) => `<li><a class="toc-group" href="#${s.id}">${escapeHtml(s.dataset.group)}</a><ul>${visible(s).map((r) => `<li><a href="#case-${r.slug}">${escapeHtml(r.title)}</a></li>`).join('')}</ul></li>`).join('')}</ul>`;
  } else {
    toc.innerHTML = `<ul>${groups.map((s) => `<li><a class="toc-group" href="#${s.id}" data-section="${s.id}">${escapeHtml(s.dataset.group)} <span class="n">${visible(s).length}</span></a></li>`).join('')}</ul>`;
  }
  spy();
}
toc.addEventListener('click', (e) => {
  const a = e.target.closest('a[href^="#"]');
  if (!a) return;
  e.preventDefault();
  const el = document.getElementById(a.getAttribute('href').slice(1));
  if (!el) return;
  el.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  if (a.dataset.case) inspect(el);
});
// ECharts' sidebar marks the section on screen
let spyObserver = null;
function spy() {
  if (spyObserver) spyObserver.disconnect();
  if (layout !== 'echarts') return;
  spyObserver = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) for (const a of toc.querySelectorAll('a[data-section]')) a.classList.toggle('on', a.dataset.section === e.target.id);
  }, { rootMargin: '-120px 0px -60% 0px' });
  for (const s of sections(groupBy)) spyObserver.observe(s);
}

// ---- columns: the slider is the chosen count; the grid draws as many of those as fit (a phone gets fewer)
const range = main.querySelector('.cols-range');
const out = main.querySelector('.cols-out');
const groupsEl = main.querySelector('.g-groups');
function fit() {
  const width = groupsEl.getBoundingClientRect().width || innerWidth;
  const gap = parseFloat(getComputedStyle(main).getPropertyValue('--gap')) || 12;
  return Math.max(1, Math.floor((width + gap) / (LAYOUTS[layout].min + gap)));
}
function drawCols() {
  const n = Math.min(chosen, fit());
  main.style.setProperty('--cols', String(n));
  main.dataset.cols = String(n);
  range.value = String(chosen);
  range.setAttribute('aria-valuetext', n < chosen ? `${chosen} columns, ${n} fit` : `${chosen} columns`);
  out.textContent = n < chosen ? `${n} of ${chosen}` : String(chosen);
}
function setCols(n) {
  chosen = Math.max(1, Math.min(MAX_COLS, Math.round(n)));
  store.set('cols/' + layout, chosen);
  drawCols();
}
range.addEventListener('input', () => setCols(Number(range.value)));
for (const b of main.querySelectorAll('.cols-step')) b.addEventListener('click', () => setCols(chosen + Number(b.dataset.step)));
new ResizeObserver(() => drawCols()).observe(groupsEl);
// ctrl/⌘ + wheel (a trackpad pinch arrives as one) and a two-finger pinch zoom the grid, as a photo grid does
let wheelAcc = 0;
groupsEl.addEventListener('wheel', (e) => {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  wheelAcc += e.deltaY;
  if (Math.abs(wheelAcc) >= 40) { setCols(chosen + Math.sign(wheelAcc)); wheelAcc = 0; }
}, { passive: false });
const touches = new Map();
let pinch0 = 0;
const spread = () => { const [a, b] = [...touches.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
groupsEl.addEventListener('pointerdown', (e) => { if (e.pointerType !== 'touch') return; touches.set(e.pointerId, { x: e.clientX, y: e.clientY }); if (touches.size === 2) pinch0 = spread(); });
groupsEl.addEventListener('pointermove', (e) => {
  if (!touches.has(e.pointerId)) return;
  touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (touches.size !== 2 || !pinch0) return;
  const ratio = spread() / pinch0;
  if (ratio > 1.25 || ratio < 0.8) { setCols(chosen + (ratio > 1 ? -1 : 1)); pinch0 = spread(); }
});
const lift = (e) => { touches.delete(e.pointerId); if (touches.size < 2) pinch0 = 0; };
groupsEl.addEventListener('pointerup', lift);
groupsEl.addEventListener('pointercancel', lift);

// ---- a picture per view: hover (or the view tabs) flips the card to another view; the link opens that view
function viewImages(card, i) {
  const row = bySlug.get(card.dataset.slug);
  const v = row.views[i];
  for (const img of card.querySelectorAll('.shot img.t')) {
    const theme = img.classList.contains('t-dark') ? 'dark' : 'light';
    const p = `${v.thumb}-${theme}`;
    img.srcset = `${p}-480.webp 480w, ${p}-960.webp 960w`;
    img.src = `${p}-480.webp`;
  }
  const href = row.href + (i ? `#view=${v.slug}` : '');
  for (const a of card.querySelectorAll('.card-link, .cap h3 a, .open')) a.href = href;
  card.querySelector('.shot-view').textContent = v.name;
  card.querySelectorAll('.scrub i').forEach((d, j) => d.classList.toggle('on', j === i));
  card.querySelectorAll('.tabs [role=tab]').forEach((t, j) => t.setAttribute('aria-selected', String(j === i)));
  card.dataset.at = String(i);
  if (card.querySelector('.live-slot data-views')) mountLive(card, true);
}
for (const card of cards) {
  const shot = card.querySelector('.shot');
  const n = Number(shot.dataset.n);
  shot.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch' || layout === 'shadcn') return;
    const r = shot.getBoundingClientRect();
    const i = Math.min(n - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * n)));
    if (String(i) !== (card.dataset.at || '0')) viewImages(card, i);
  });
  shot.addEventListener('pointerleave', () => { if (layout !== 'shadcn' && card.dataset.at && card.dataset.at !== '0') viewImages(card, 0); });
  card.querySelector('.tabs').addEventListener('click', (e) => { const t = e.target.closest('[role=tab]'); if (t) viewImages(card, Number(t.dataset.i)); });
  card.querySelector('.pv-bar .seg').addEventListener('click', (e) => { const t = e.target.closest('[data-pane]'); if (t) pane(card, t.dataset.pane); });
  // a picture not captured yet (site/capture-thumbs.py) is drawn live instead, as the landing page's thumbnails are
  for (const img of shot.querySelectorAll('img.t')) img.addEventListener('error', () => liveFallback(card), { once: true });
}
function liveViews(row, at, interactive) {
  const el = document.createElement('data-views');
  el.setAttribute('src', `${row.slug}/views.base`);
  el.setAttribute('view', row.views[at].name);
  el.setAttribute('no-url', '');
  el.setAttribute('toolbar', 'none');
  if (!interactive) el.inert = true;
  return el;
}
function liveFallback(card) {
  if (card.querySelector('.shot-live')) return;
  const box = document.createElement('div');
  box.className = 'shot-live';
  box.setAttribute('aria-hidden', 'true');
  box.append(liveViews(bySlug.get(card.dataset.slug), Number(card.dataset.at || 0), false));
  card.querySelector('.shot').append(box);
  card.classList.add('live');
}

// ---- shadcn: Preview is the live kit (mounted when the card scrolls near), .base is the source beside it
function mountLive(card, again = false) {
  const slot = card.querySelector('.live-slot');
  if (slot.firstChild && !again) return;
  slot.replaceChildren(liveViews(bySlug.get(card.dataset.slug), Number(card.dataset.at || 0), true));
  card.classList.add('is-live');
}
function unmountLive() {
  for (const card of cards) { card.querySelector('.live-slot').replaceChildren(); card.classList.remove('is-live'); pane(card, 'preview'); }
}
const liveObserver = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting && layout === 'shadcn') mountLive(e.target);
}, { rootMargin: '100px 0px' });
async function pane(card, which) {
  const src = card.querySelector('.src-pane');
  card.querySelectorAll('.pv-bar [data-pane]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.pane === which)));
  src.hidden = which !== 'base';
  card.classList.toggle('show-base', which === 'base');
  if (which === 'base' && !src.dataset.loaded) {
    src.dataset.loaded = '1';
    const code = src.querySelector('code');
    try { code.textContent = await (await fetch(`${card.dataset.slug}/views.base`)).text(); } catch (err) { code.textContent = `Could not read views.base: ${err}`; }
  }
}
// (Copy in the .base pane is site.js's own Copy button: the pane is a .file)

// ---- Storybook's Docs panel: the case under the pointer or focus, its views and its whole summary
const inspector = main.querySelector('.g-inspector');
let inspected = null;
function inspect(card) {
  if (!card || card === inspected) return;
  inspected = card;
  const r = bySlug.get(card.dataset.slug);
  inspector.innerHTML = `<div class="panel-head"><span>Docs</span><button type="button" class="fold" data-fold="inspector" aria-label="Fold the Docs panel">›</button></div>
  <div class="insp-body"><p class="insp-app"><span class="pill pill-app">${escapeHtml(r.app)}</span> ${escapeHtml(r.category)} · ${r.views.length} views</p>
  <h2>${escapeHtml(r.title)}</h2><p class="insp-summary">${escapeHtml(r.summary)}</p>
  ${r.shows ? `<h3>What it shows</h3><p class="insp-summary">${escapeHtml(r.shows)}</p>` : ''}
  <h3>Views</h3><ul class="insp-views">${r.views.map((v, i) => `<li><a href="${r.href}${i ? `#view=${v.slug}` : ''}"><img class="t t-light" src="${v.thumb}-light-480.webp" loading="lazy" alt=""><img class="t t-dark" src="${v.thumb}-dark-480.webp" loading="lazy" alt=""><span>${escapeHtml(v.name)} <code>${v.type}</code></span></a></li>`).join('')}</ul>
  <p><a class="button primary" href="${r.href}">Open the example</a></p></div>`;
}
for (const card of cards) {
  card.addEventListener('pointerenter', () => { if (LAYOUTS[layout].docs) inspect(card); });
  card.addEventListener('focusin', () => { if (LAYOUTS[layout].docs) inspect(card); });
}

// ---- side panels: dragged, remembered, folded (Zach's resizable-panels rule, .claude/feedback.md)
const rail = main.querySelector('.g-rail');
let panels = [];
const folded = (k) => store.get('fold/' + k) === '1';
if (!rail.querySelector('.panel-head')) rail.insertAdjacentHTML('afterbegin', '<div class="panel-head"><span>Examples</span><button type="button" class="fold" data-fold="rail" aria-label="Fold the sidebar">‹</button></div>');
main.addEventListener('click', (e) => {
  const b = e.target.closest('[data-fold]');
  if (!b) return;
  const k = b.dataset.fold;
  const on = !main.classList.contains(`fold-${k}`);
  main.classList.toggle(`fold-${k}`, on);
  store.set('fold/' + k, on ? '1' : '0');
});
function sidePanels() {
  for (const p of panels) p && p.destroy();
  panels = [];
  const l = LAYOUTS[layout];
  main.classList.toggle('fold-rail', !!l.rail && folded('rail'));
  main.classList.toggle('fold-inspector', !!l.docs && folded('inspector'));
  if (l.rail) panels.push(makeResizable(rail, { edge: 'right', key: 'examples-sidebar', label: 'the sidebar', keep: 480 }));
  if (l.docs) {
    panels.push(makeResizable(inspector, { edge: 'left', key: 'examples-docs', label: 'the Docs panel', keep: 480 }));
    if (!inspected) inspect(cards.find((c) => !c.hidden));
  }
}

// ---- the temporary layout switcher, bottom right
function setLayout(name, save = true) {
  const was = layout;
  layout = LAYOUTS[name] ? name : DEFAULT_LAYOUT;
  main.dataset.layout = layout;
  if (save) store.set('layout', layout);
  const saved = Number(store.get('cols/' + layout));
  chosen = saved >= 1 && saved <= MAX_COLS ? saved : LAYOUTS[layout].cols;
  for (const card of cards) if (card.dataset.at && card.dataset.at !== '0') viewImages(card, 0);
  if (was === 'shadcn' && layout !== 'shadcn') unmountLive();
  liveObserver.disconnect();
  if (layout === 'shadcn') for (const card of cards) liveObserver.observe(card);
  sidePanels();
  drawCols();
  drawToc();
  if (select) select.value = layout;
}
const switcher = document.createElement('div');
switcher.className = 'layout-switch';
switcher.innerHTML = `<label><span>Examples layout</span> <select aria-label="Examples layout">${Object.entries(LAYOUTS).map(([k, l], i) => `<option value="${k}">${i + 1}. ${l.art}${k === DEFAULT_LAYOUT ? ' (default)' : ''}</option>`).join('')}</select></label>`;
document.body.append(switcher);
const select = switcher.querySelector('select');
select.addEventListener('change', () => setLayout(select.value));

regroup();
setLayout(store.get('layout') || DEFAULT_LAYOUT, false);
applyFilters();
window.dataUiGallery = { setLayout, setCols, get layout() { return layout; }, get cols() { return chosen; }, get groupBy() { return groupBy; }, LAYOUTS };
