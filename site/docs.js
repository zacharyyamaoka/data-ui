// The Views, Dashboards, Analyses and Docs pages' own behaviour (site/docs-pages.mjs writes their markup): Preview | Code
// tabs, each live demo started when it scrolls near, the switches and presets that set attributes on a demo, and the
// sidebar's menu on a phone. The sidebar's drag handle is the kit's own (data-resizable, docs/CONTRACT.md §11); the
// theme switch and the Copy buttons are site.js'.

// ---- Preview | Code: a tablist per block, arrows move between its tabs
const select = (tab) => {
  const list = tab.closest('[role=tablist]');
  for (const t of list.querySelectorAll('[role=tab]')) {
    const on = t === tab;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
  }
};
document.addEventListener('click', (e) => {
  const tab = e.target.closest('.dd-tabs [role=tab]');
  if (tab) select(tab);
});
document.addEventListener('keydown', (e) => {
  const tab = e.target.closest && e.target.closest('.dd-tabs [role=tab]');
  if (!tab || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
  const tabs = [...tab.closest('[role=tablist]').querySelectorAll('[role=tab]')];
  const next = tabs[(tabs.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  select(next);
  next.focus();
  e.preventDefault();
});

// ---- live demos: each starts when it scrolls near, so a page of twenty views loads one or two views' code at first
// WHY no-url on every demo: a page holds many <data-views>, and the hash (view=, peek=) can belong to only one
// A whole dashboard, an analysis or the list of analyses (data-kind) loads its element's file when it starts, as site.js
// does for a case page that has one (docs/peps/0004-dashboards.md, 0007-analyses.md); analysis.js loads dashboard.js
// itself for the first dashboard it meets.
const KINDS = {
  dashboard: { tag: 'data-dashboard', src: 'src', load: () => import('./kit/dashboard.js'), drawn: 'data-dashboard-change' },
  analysis: { tag: 'data-analysis', src: 'src', load: () => import('./kit/analysis.js'), drawn: 'data-analysis-render' },
  // the list's own <data-views> draws inside it; the list mirrors that as its data-view attribute
  analyses: { tag: 'data-analyses', src: 'base', load: () => import('./kit/analysis.js'), drawn: null },
};
const startKind = (box, kind) => {
  const el = document.createElement(kind.tag);
  el.id = box.dataset.id;
  el.setAttribute(kind.src, box.dataset.src);
  el.setAttribute('aria-label', box.dataset.label || '');
  // WHY heading="2": the analysis sits under this page's own h1
  if (kind.tag === 'data-analysis') el.setAttribute('heading', '2');
  else el.setAttribute('no-url', '');
  if (kind.drawn) el.addEventListener(kind.drawn, () => box.classList.add('drawn'), { once: true });
  else {
    const seen = new MutationObserver(() => { if (el.dataset.view) { box.classList.add('drawn'); seen.disconnect(); } });
    seen.observe(el, { attributes: true, attributeFilter: ['data-view'] });
  }
  box.querySelector('.demo').append(el);
  kind.load();
};
const start = (box) => {
  if (box.dataset.started) return;
  box.dataset.started = '1';
  if (KINDS[box.dataset.kind]) { startKind(box, KINDS[box.dataset.kind]); return; }
  const id = box.dataset.id;
  const wrap = box.querySelector('.demo');
  const views = document.createElement('data-views');
  views.id = id;
  views.setAttribute('src', box.dataset.src);
  views.setAttribute('view', box.dataset.view);
  views.setAttribute('no-url', '');
  views.setAttribute('toolbar', box.dataset.toolbar || 'none');
  views.setAttribute('aria-label', box.dataset.label || '');
  let attrs = {};
  try { attrs = JSON.parse(box.dataset.attrs || '{}'); } catch { /* none */ }
  for (const [k, v] of Object.entries(attrs)) views.setAttribute(k, v);
  if (wrap.classList.contains('has-rail')) {
    const rail = document.createElement('data-facets');
    rail.setAttribute('for', id);
    rail.className = 'rail';
    wrap.append(rail);
  }
  wrap.append(views);
  views.addEventListener('data-views-render', () => box.classList.add('drawn'), { once: true });
};
const boxes = document.querySelectorAll('.dd-preview[data-src]');
if (boxes.length) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); start(e.target); }
  }, { rootMargin: '200px 0px' });
  for (const b of boxes) io.observe(b);
}

// ---- switches: a segmented control that sets one attribute on one demo (frame=, open=) and on its HTML snippet
for (const group of document.querySelectorAll('[data-switch]')) {
  const box = document.querySelector(`.dd-preview[data-switch-id="${group.dataset.switch}"]`);
  const attr = group.dataset.attr;
  const code = group.dataset.snippet && document.getElementById(group.dataset.snippet);
  group.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b || !box) return;
    const value = b.dataset.value;
    for (const x of group.querySelectorAll('button')) x.setAttribute('aria-pressed', String(x === b));
    let attrs = {};
    try { attrs = JSON.parse(box.dataset.attrs || '{}'); } catch { /* none */ }
    attrs[attr] = value;
    box.dataset.attrs = JSON.stringify(attrs);
    const views = box.querySelector('data-views');
    if (views) views.setAttribute(attr, value);
    else start(box);
    if (code) code.textContent = code.textContent.replace(new RegExp(`${attr}="[^"]*"`), `${attr}="${value}"`);
  });
}

// ---- presets: a segmented control that sets several attributes on one demo at once (the toolbar's views= and
// promote=); a null value removes the attribute, so a preset can go back to the element's own default
for (const group of document.querySelectorAll('[data-preset]')) {
  const box = document.querySelector(`.dd-preview[data-switch-id="${group.dataset.preset}"]`);
  const code = group.dataset.snippet && document.getElementById(group.dataset.snippet);
  group.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-set]');
    if (!b || !box) return;
    let set = {};
    try { set = JSON.parse(b.dataset.set); } catch { return; }
    for (const x of group.querySelectorAll('button')) x.setAttribute('aria-pressed', String(x === b));
    let attrs = {};
    try { attrs = JSON.parse(box.dataset.attrs || '{}'); } catch { /* none */ }
    for (const [k, v] of Object.entries(set)) { if (v === null) delete attrs[k]; else attrs[k] = v; }
    box.dataset.attrs = JSON.stringify(attrs);
    const views = box.querySelector('data-views');
    if (views) for (const [k, v] of Object.entries(set)) { if (v === null) views.removeAttribute(k); else views.setAttribute(k, v); }
    else start(box);
    if (code && b.dataset.html) code.textContent = b.dataset.html;
  });
}

// ---- the sidebar on a phone: a Menu button over a closed list (the CSS shows the list whole above 768 px)
const side = document.querySelector('.docs-side');
const menu = side && side.querySelector('.docs-menu');
if (menu) {
  menu.addEventListener('click', () => {
    const open = !side.classList.contains('open');
    side.classList.toggle('open', open);
    menu.setAttribute('aria-expanded', String(open));
  });
  // a link to a place on this page closes the menu, so the reader sees where it went
  side.addEventListener('click', (e) => {
    if (e.target.closest('.docs-nav a') && side.classList.contains('open')) { side.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); }
  });
}
