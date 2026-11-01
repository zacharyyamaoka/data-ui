// The object-database prototype page: five proposals, one at a time, picked from the bottom-right switch.
// WHY a remembered switch and never a URL flag: Zach's standing rule for gated prototypes (memory
// feedback_prototype_switch_in_app). Every view is a plain .base file; this file only lays panels out and, for the
// taxonomy stage and the stream board, passes a selection from one <data-views> to another.

import { autoResize } from '../../../kit/data-ui.js';

const KEY = 'object-db/proposal';
const CASES = '../..'; // dist/site/gallery/<case>/ from here

const P = [
  {
    id: 'shelf', short: 'Shelf', title: 'Gallery-first · the 3D shelf',
    pitch: 'Every object as a card with its own poster; hover turns the real mesh, click opens a peek with an orbit viewer. One WebGL renderer for the page.',
    facts: { 'Lead view': 'cards (by type)', '3D in': 'card + peek', '.base': 'new (seeded by the dataset’s Cards view)' },
    layout: () => rail('p1', `${CASES}/object-db-shelf/views.base`),
  },
  {
    id: 'ledger', short: 'Ledger', title: 'Table-first · the dataset’s own Bases files',
    pitch: 'The six .base files Obsidian already shows, read by data-ui with a data: line added. Tables lead; 3D lives in the peek.',
    facts: { 'Lead view': 'table', '3D in': 'peek only', '.base': 'reused (object-db bases output)' },
    layout: () => tabs([
      ['Objects', `${CASES}/object-db-ledger/views.base`],
      ['Types', `${CASES}/object-db-ledger/types.base`],
      ['Materials', `${CASES}/object-db-ledger/materials.base`],
      ['Mixes', `${CASES}/object-db-ledger/mixes.base`],
    ]),
  },
  {
    id: 'tree', short: 'Tree', title: 'Taxonomy-first · the family tree',
    pitch: 'Family → material → type as a React Flow graph and an outline. Selecting a type puts its representative object on a full-height 3D stage.',
    facts: { 'Lead view': 'graph', '3D in': 'full pane (stage) + peek', '.base': 'new' },
    layout: () => stage(),
  },
  {
    id: 'streams', short: 'Streams', title: 'Mix-first · the stream board',
    pitch: 'Pick a waste stream: its composition, its share table and the objects sampled for it, with mass min / median / max. A dashboard of two .base files.',
    facts: { 'Lead view': 'chart + cards', '3D in': 'card (click) + peek', '.base': 'new (two files, one picker)' },
    layout: () => streams(),
  },
  {
    id: 'lab', short: 'Lab', title: 'Material-first · the material lab',
    pitch: 'Materials by density, their measured reflectance spectra (350–2500 nm), and every object on an Ashby chart of mass against volume.',
    facts: { 'Lead view': 'charts', '3D in': 'peek only', '.base': 'new (three files)' },
    layout: () => lab(),
  },
];

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const views = (id, src, extra = '') => `<data-views id="${id}" src="${src}" no-url frame="flush" ${extra}></data-views>`;

function rail(id, src) {
  return `<div class="proto-rail-layout"><aside class="proto-rail"><data-facets for="${id}"></data-facets></aside>${views(id, src)}</div>`;
}

function tabs(list) {
  const buttons = list.map(([name], i) => `<button type="button" role="tab" aria-selected="${i === 0}" data-tab="${i}">${esc(name)}</button>`).join('');
  const panels = list.map(([, src], i) => `<section role="tabpanel" data-panel="${i}"${i ? ' hidden' : ''}>${i ? '' : views(`p2-${i}`, src)}</section>`).join('');
  queueMicrotask(() => {
    const root = $('#stage');
    root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-tab]');
      if (!b) return;
      const i = Number(b.dataset.tab);
      root.querySelectorAll('[data-tab]').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      root.querySelectorAll('[data-panel]').forEach((p) => {
        p.hidden = Number(p.dataset.panel) !== i;
        // WHY made on first open: five <data-views> loading five data files at once would slow the first paint
        if (!p.hidden && !p.firstElementChild) p.innerHTML = views(`p2-${i}`, list[i][1]);
      });
    });
  });
  return `<div class="proto-tabs" role="tablist" aria-label="The dataset's .base files">${buttons}<span class="proto-note">Each tab is one of <code>~/bam-waste-objects/views/*.base</code>, with a <code>data:</code> line</span></div><div class="proto-tabbed">${panels}</div>`;
}

function stage() {
  queueMicrotask(() => {
    const el = $('#p3');
    const show = (row) => {
      if (!row || !row.mesh) return;
      const s = $('#p3-stage');
      const url = new URL(row.mesh, el.dataUrl).href;
      const poster = row.thumbnail ? new URL(row.thumbnail, el.dataUrl).href : '';
      s.querySelector('data-mesh').setAttribute('poster', poster);
      s.querySelector('data-mesh').setAttribute('src', url);
      s.querySelector('data-mesh').setAttribute('alt', row.example || row.name);
      s.querySelector('h2').textContent = row.name;
      s.querySelector('p').innerHTML = `${esc(row.kind)} · <b>${Number(row.instances || 0).toLocaleString()}</b> objects in the library${row.example ? ` · shown: ${esc(row.example)}` : ''}`;
    };
    el.addEventListener('data-views-open', (e) => show(e.detail.row));
    el.addEventListener('data-views-render', () => {
      if ($('#p3-stage').dataset.started) return;
      // the biggest node that has a model (the default view may hold families and materials only)
      const first = el.model && el.model.rows.filter((r) => r.mesh).sort((a, b) => b.instances - a.instances)[0];
      if (first) { $('#p3-stage').dataset.started = '1'; show(first); }
    });
  });
  return `<div class="proto-stage-layout"><div class="proto-stage-main"><aside class="proto-rail proto-rail-thin"><data-facets for="p3"></data-facets></aside>${views('p3', `${CASES}/object-db-taxonomy/views.base`)}</div>
  <section class="proto-stage" id="p3-stage" data-resizable="left" data-resizable-min="260" data-resizable-max="900" data-resizable-key="object-db-stage" aria-label="The selected type in 3D">
    <data-mesh interact="orbit"></data-mesh><h2>Pick a type</h2><p>Click a type node: its representative object turns here.</p>
    <p class="proto-hint">Drag to turn · scroll to zoom · double-click to reset</p></section></div>`;
}

function streams() {
  queueMicrotask(async () => {
    const mixesEl = $('#p4-mix');
    const objectsEl = $('#p4-obj');
    const pick = $('#p4-pick');
    const res = await fetch(`${CASES}/object-db-shelf/mix_list.json`);
    const list = (await res.json()).rows;
    pick.innerHTML = list.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
    let saved = null;
    try { saved = localStorage.getItem('object-db/stream'); } catch { /* this visit only */ }
    if (saved && list.some((m) => m.id === saved)) pick.value = saved;
    const apply = () => {
      const m = list.find((x) => x.id === pick.value);
      try { localStorage.setItem('object-db/stream', m.id); } catch { /* this visit only */ }
      mixesEl.filters = { and: [`mix == ${JSON.stringify(m.id)}`] };
      objectsEl.filters = { and: [`mixes.contains(${JSON.stringify(m.id)})`] };
      $('#p4-about').innerHTML = `<b>${m.measured ? 'Measured' : 'Assumed'}</b> shares by ${esc(m.basis)} · ${esc(m.types)} types · ${esc((m.description || '').slice(0, 220))}${(m.description || '').length > 220 ? '…' : ''}`;
    };
    pick.addEventListener('change', apply);
    apply();
    objectsEl.addEventListener('data-views-render', () => {
      const rows = (objectsEl.model ? objectsEl.model.rows : []);
      const mass = rows.map((r) => (r.mass_g && typeof r.mass_g === 'object' ? r.mass_g.value : r.mass_g)).filter((v) => typeof v === 'number').sort((a, b) => a - b);
      const len = rows.map((r) => r.length_mm).filter((v) => typeof v === 'number').sort((a, b) => a - b);
      const fmt = (v, u) => (v == null ? '—' : `${v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1)} ${u}`);
      const med = (a) => (a.length ? a[Math.floor(a.length / 2)] : null);
      // WHY labelled "of N sampled": these are view summaries over the rows shown, not the stream's measured figures
      $('#p4-kpis').innerHTML = [
        ['Objects sampled', rows.length.toLocaleString(), ''],
        ['Mass min / median / max', `${fmt(mass[0], 'g')} · ${fmt(med(mass), 'g')} · ${fmt(mass[mass.length - 1], 'g')}`, `of ${mass.length} with a mass`],
        ['Longest side min / max', `${fmt(len[0], 'mm')} · ${fmt(len[len.length - 1], 'mm')}`, `of ${len.length} sampled`],
      ].map(([k, v, n]) => `<div class="proto-kpi"><span>${esc(k)}</span><b>${esc(v)}</b><small>${esc(n)}</small></div>`).join('');
    });
  });
  return `<div class="proto-streams"><div class="proto-streams-bar"><label>Stream <select id="p4-pick"></select></label><p id="p4-about"></p></div>
  <div class="proto-kpis" id="p4-kpis"></div>
  <div class="proto-grid-2"><div class="proto-panel">${views('p4-mix', `${CASES}/object-db-streams/views.base`)}</div><div class="proto-panel">${views('p4-obj', `${CASES}/object-db-streams/objects.base`)}</div></div></div>`;
}

function lab() {
  return `<div class="proto-lab"><div class="proto-panel proto-lab-a"><aside class="proto-rail proto-rail-thin"><data-facets for="p5-mat"></data-facets></aside>${views('p5-mat', `${CASES}/object-db-materials/views.base`)}</div>
  <div class="proto-panel proto-lab-b">${views('p5-spec', `${CASES}/object-db-materials/spectra.base`)}</div>
  <div class="proto-panel proto-lab-c">${views('p5-obj', `${CASES}/object-db-materials/objects.base`)}</div></div>`;
}

// ------------------------------------------------------------------------------------------------ the switch
function current() {
  let id = null;
  try { id = localStorage.getItem(KEY); } catch { /* the choice lasts this visit */ }
  return P.find((p) => p.id === id) || P[0];
}

function show(p) {
  try { localStorage.setItem(KEY, p.id); } catch { /* the choice lasts this visit */ }
  const i = P.indexOf(p);
  document.body.dataset.proposal = p.id;
  $('#kicker').textContent = `Proposal ${i + 1} of ${P.length}`;
  $('#title').textContent = p.title;
  $('#pitch').textContent = p.pitch;
  $('#facts').innerHTML = Object.entries(p.facts).map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
  $('#stage').innerHTML = p.layout();
  // a host panel marked data-resizable gets its drag handle (docs/CONTRACT.md §11); the kit's own rails and peeks get theirs
  queueMicrotask(() => autoResize($('#stage')));
  document.querySelectorAll('#switch button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.id === p.id)));
  window.dispatchEvent(new CustomEvent('object-db-proposal', { detail: { id: p.id } }));
}

$('#switch').innerHTML = P.map((p, i) => `<button type="button" data-id="${p.id}" title="${esc(p.title)}"><b>${i + 1}</b> ${esc(p.short)}</button>`).join('');
$('#switch').addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (b) show(P.find((p) => p.id === b.dataset.id)); });

const root = document.documentElement;
const themeLabel = () => { $('#theme').textContent = `Theme: ${root.dataset.theme || 'system'}`; };
$('#theme').addEventListener('click', () => {
  const order = ['system', 'light', 'dark'];
  const next = order[(order.indexOf(root.dataset.theme || 'system') + 1) % 3];
  if (next === 'system') delete root.dataset.theme; else root.dataset.theme = next;
  try { if (next === 'system') localStorage.removeItem('data-ui-site-theme'); else localStorage.setItem('data-ui-site-theme', next); } catch { /* this visit only */ }
  themeLabel();
});
themeLabel();
show(current());
