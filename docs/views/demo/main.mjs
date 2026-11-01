/* The demo host: one dataset (robotparts' 1,149 actuators), one .base file, three view plugins.

   The host owns the row model, the .base file and the data. A plugin gets {rows, groups, columns, view, tokens}
   and may call back exactly three things (docs/VIEWS.md §4):
     host.setView(patch)     change ITS view entry (a Bases key or an extension key); lands in the .base file
     host.propose(edit)      ask for a data edit; the host decides (here: derived properties refuse, others apply
                             in memory, because robotparts.dev itself has no write path)
     host.open(id)           open the shared record peek
   The page passes window.__DU = {data, base, chunks} (gzipped, base64), written by docs/views/build.py. */

import { rowModel, registerView, viewPlugin, resolveTokens } from './core.mjs';
import { toBaseYaml } from './grammar.js';
import CardsView from './views/cards.mjs';
import KanbanView from './views/kanban.mjs';
import { esc, fmt } from './views/shared.mjs';

async function gunzip(b64) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
}

// The two eager plugins share the main bundle; the chart's 280 KB (gzipped) of Vega arrive when its tab opens.
registerView('cards', { name: 'Cards', icon: 'layout-grid', load: async () => CardsView });
registerView('kanban', { name: 'Board', icon: 'square-kanban', load: async () => KanbanView });
registerView('chart', {
  name: 'Chart', icon: 'chart-scatter',
  load: async () => {
    const t0 = performance.now();
    const text = await gunzip(window.__DU.chunks.chart);
    const mod = await import(URL.createObjectURL(new Blob([text], { type: 'text/javascript' })));
    log(`chart plugin loaded on first use: ${(text.length / 1024).toFixed(0)} KB of JS (vega, vega-lite, vega-embed) in ${Math.round(performance.now() - t0)} ms`);
    return mod.default;
  },
});

let root, dataset, base, active = 0, plugin = null, pluginType = null, byId;
const $ = (sel) => root.querySelector(sel);

function log(text, kind = '') {
  const li = document.createElement('li');
  li.className = kind;
  li.textContent = text;
  const list = root && root.querySelector('.du-log');
  if (!list) return;
  list.prepend(li);
  while (list.children.length > 8) list.lastChild.remove();
}

function toast(text, kind = '') {
  const t = $('.du-toast');
  t.textContent = text;
  t.className = `du-toast ${kind}`;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 4200);
}

const host = {
  setView(patch) {
    Object.assign(base.views[active], patch);
    log(`view written: ${Object.keys(patch).join(', ')} → the .base file`, 'view');
    render();
  },
  propose(edit) {
    const row = byId.get(edit.id);
    for (const [p, v] of Object.entries(edit.set)) {
      const meta = dataset.properties[p] || {};
      if (meta.derived) {
        const msg = `Refused: ${meta.label} is derived (${meta.derived}), so no view may set it. The card stays where it was.`;
        toast(msg, 'refused');
        log(`data edit refused: ${row.model} ${meta.label.toLowerCase()} → ${v}`, 'refused');
        return { ok: false, reason: msg };
      }
    }
    const before = Object.fromEntries(Object.keys(edit.set).map((p) => [p, row[p]]));
    Object.assign(row, edit.set);
    const what = Object.entries(edit.set).map(([p, v]) => `${dataset.properties[p].label.toLowerCase()} “${before[p] ?? '—'}” → “${v ?? '—'}”`).join(', ');
    toast(`Edit accepted by the host (in memory): ${row.model}, ${what}. Every view now reads it.`, 'ok');
    log(`data edit accepted: ${row.model}, ${what}`, 'ok');
    render();
    return { ok: true };
  },
  open(id) {
    const r = byId.get(id);
    if (!r) return;
    const props = dataset.properties;
    const peek = $('.du-peek');
    peek.innerHTML = `<header><b>${esc(r.name)}</b><button class="du-x" aria-label="Close">×</button></header>
      <dl>${Object.keys(props).filter((p) => !props[p].hidden).map((p) => `<dt>${esc(props[p].label)}</dt><dd>${fmt(r[p], props[p])}</dd>`).join('')}</dl>
      <p class="du-muted">The same record surface opens from every view: a card, a dot, a board card.</p>`;
    peek.hidden = false;
    peek.querySelector('.du-x').onclick = () => { peek.hidden = true; };
  },
};

function yaml() {
  const head = `# actuators.base · ${Object.keys(dataset.properties).length} properties (from the dataset) · rows: ${dataset.rows.length}\n`
    + (base.filters ? `filters: ${JSON.stringify(base.filters)}\n` : '');
  const blocks = base.views.map((v, i) => {
    const text = toBaseYaml(v).replace(/^views:\n/, '');
    return i === active ? `<mark>${esc(text)}</mark>` : esc(text);
  });
  return esc(head) + 'views:\n' + blocks.join('');
}

async function render() {
  const view = base.views[active];
  const t0 = performance.now();
  const model = rowModel(dataset, base, view);
  const ms = performance.now() - t0;
  $('.du-count').innerHTML = model.error
    ? `<span class="du-err">filter: ${esc(model.error)}</span>`
    : `${model.rows.length.toLocaleString()} of ${model.total.toLocaleString()} rows · row model ${ms.toFixed(0)} ms`;
  $('.du-yaml').innerHTML = yaml();
  const mark = $('.du-yaml mark'), side = $('.du-side');
  if (mark && side.scrollHeight > side.clientHeight) side.scrollTop = Math.max(0, mark.offsetTop - side.offsetTop - 40);
  root.querySelectorAll('.du-tab').forEach((b, i) => b.setAttribute('aria-selected', String(i === active)));
  if (pluginType !== view.type) {
    if (plugin) plugin.destroy();
    plugin = null;
    pluginType = view.type;
    const Plugin = await viewPlugin(view.type).load();
    if (pluginType !== view.type) return;
    plugin = new Plugin(host, $('.du-stage'));
  }
  const input = { rows: model.rows, groups: model.groups, columns: dataset.properties, view: structuredClone(view), tokens: resolveTokens(root), total: model.total };
  root.dataset.view = view.type;
  await plugin.update(input);
  root.dataset.ready = String(Date.now());
}

async function start() {
  root = document.querySelector('#du-demo');
  dataset = JSON.parse(await gunzip(window.__DU.data));
  base = JSON.parse(await gunzip(window.__DU.base));
  byId = new Map(dataset.rows.map((r) => [r.id, r]));
  root.innerHTML = `
    <div class="du-top">
      <div class="du-tabs" role="tablist">${base.views.map((v, i) => `<button class="du-tab" role="tab" data-i="${i}">${esc(v.name)} <small>type: ${esc(v.type)}</small></button>`).join('')}</div>
      <button class="du-theme" type="button" title="Switch the demo's tokens; every view re-reads them">Dark</button>
    </div>
    <div class="du-filter">
      <label for="du-f">filters <small>(the .base file's, so every view reads the same rows)</small></label>
      <input id="du-f" spellcheck="false" placeholder='e.g. drivetrain == "geared" && price < 150'>
      <span class="du-chips">${['drivetrain == "geared"', 'buses.contains("can")', 'price < 150', 'peak_torque >= 10', ''].map((f) => `<button data-f='${esc(f)}'>${f ? esc(f) : 'clear'}</button>`).join('')}</span>
      <span class="du-count du-muted"></span>
    </div>
    <div class="du-body">
      <div class="du-stage"></div>
      <aside class="du-side"><h4>The .base file, live</h4><pre class="du-yaml"></pre><h4>Writes</h4><ol class="du-log"></ol></aside>
    </div>
    <aside class="du-peek" hidden></aside>
    <div class="du-toast" role="status" hidden></div>`;
  root.querySelectorAll('.du-tab').forEach((b) => b.addEventListener('click', () => { active = Number(b.dataset.i); render(); }));
  const input = $('#du-f');
  const apply = (text) => {
    input.value = text;
    if (text) base.filters = text; else delete base.filters;
    log(`filters written: ${text || '(none)'} → the .base file`, 'view');
    render();
  };
  input.addEventListener('change', () => apply(input.value.trim()));
  root.querySelectorAll('[data-f]').forEach((b) => b.addEventListener('click', () => apply(b.dataset.f)));
  // WHY the effective theme: with no data-theme the demo follows the page, which follows the system
  const effective = () => root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  $('.du-theme').textContent = effective() === 'dark' ? 'Light' : 'Dark';
  $('.du-theme').addEventListener('click', (e) => {
    const dark = effective() !== 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    e.target.textContent = dark ? 'Light' : 'Dark';
    log(`tokens re-resolved for ${dark ? 'dark' : 'light'}; the chart redraws, the DOM views follow CSS`, 'view');
    render();
  });
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get('view')) active = Math.max(0, base.views.findIndex((v) => v.type === hash.get('view') || v.name === hash.get('view')));
  if (hash.get('theme') === 'dark') { root.dataset.theme = 'dark'; $('.du-theme').textContent = 'Light'; }
  render();
  window.__duHost = { host, render, get base() { return base; }, get active() { return active; }, set active(i) { active = i; } };
}

start();
