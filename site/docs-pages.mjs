// The docs site's Views, Dashboards and Docs pages, in shadcn's docs layout: a resizable sidebar beside the page, and
// blocks that pair a Preview (a gallery case's real view, started by site/docs.js when it scrolls near) with its Code
// (that view's entry, cut from the case's own .base file). Called by site/build-site.mjs; writes dist/site/views/,
// dashboards/ and docs/, plus docs.css and docs.js beside site.css.
// WHY the gallery cases are the demos: a block can only show what the kit really draws on real data, and a case
// changed in gallery/examples/ changes its block here with no second copy to keep in step.
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseBase } from '../packages/core/src/base.js';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Where the not-yet-merged parts come from. WHY copied in, not read with git at build time: a lane branch is deleted
// after it lands, and the build must not depend on one; the integrator swaps each [data-slot] for the live thing.
// Dashboards (§17), the toolbar (§15) and analyses (§19) have landed; the card catalog, the clock and Rerun have not.
const LANES = {
  cards: 'lane/dashboard-cards @ 4ceda4d (docs/peps/0005-dashboard-cards.md, gallery/examples/dashboard-cards)',
};

const BADGES = {
  live: ['Live', 'live'],
  cards: ['Lands with dashboard cards', 'soon'],
};
const badge = (kind) => `<span class="badge badge-${BADGES[kind][1]}">${BADGES[kind][0]}</span>`;

// The three tiers, one line each (the Overview's block near the top, and the Analyses page). All three are on main.
const TIERS = [
  ['views/index.html', 'Views', 'live', 'One dataset, many ways to see it: a table, a chart, a board, a map, all from one <code>.base</code> file.'],
  ['dashboards/index.html', 'Dashboards', 'live', 'Many views laid out on a grid over linked datasets: one rail filters them all, a click in one narrows the rest.'],
  ['analyses/index.html', 'Analyses', 'live', 'A report page that answers one question: prose with views and dashboards embedded, a sticky contents list and decision callouts.'],
];
export const tiersHtml = (rel) => `<section class="tiers" aria-labelledby="tiers-h">
  <h2 id="tiers-h">Three tiers: Views → Dashboards → Analyses</h2>
  <ol class="tier-list">${TIERS.map(([href, name, kind, line]) => `<li><a href="${rel}${href}"><span class="tier-head"><b>${name}</b>${badge(kind)}</span><span class="tier-line">${line}</span></a></li>`).join('')}</ol>
</section>`;

/** One entry of a .base file's views: list, as written (comments and all), checked against the parsed file so the
    Code tab never shows something other than what the Preview draws. */
export function viewEntryText(baseText, name) {
  const lines = baseText.split('\n');
  const start = lines.findIndex((l) => /^views:\s*$/.test(l));
  if (start < 0) throw new Error('no views: block');
  let end = lines.findIndex((l, i) => i > start && /^[A-Za-z_][\w-]*:/.test(l));
  if (end < 0) end = lines.length;
  const body = lines.slice(start + 1, end);
  const first = body.find((l) => /^\s*-\s/.test(l));
  const indent = /^(\s*)-/.exec(first)[1];
  const chunks = [];
  for (const l of body) {
    if (l.startsWith(indent + '- ')) chunks.push([l]);
    else if (chunks.length) chunks[chunks.length - 1].push(l);
  }
  const want = parseBase(baseText).views.find((v) => v.name === name);
  if (!want) throw new Error(`no view named ${name}`);
  for (const chunk of chunks) {
    while (chunk.length && (!chunk[chunk.length - 1].trim() || /^\s*#/.test(chunk[chunk.length - 1]))) chunk.pop();
    const got = parseBase(['views:', ...chunk].join('\n')).views[0];
    if (got && got.name === name) {
      if (!same(got, want)) throw new Error(`the entry cut for ${name} does not parse to the file's own entry`);
      return chunk.map((l) => l.slice(indent.length)).join('\n');
    }
  }
  throw new Error(`could not cut the entry for ${name}`);
}

/** A top-level key's block (facets:, open:), as written, checked the same way. */
export function topKeyText(baseText, key) {
  const lines = baseText.split('\n');
  const start = lines.findIndex((l) => l.startsWith(key + ':'));
  if (start < 0) return '';
  let end = lines.findIndex((l, i) => i > start && /^[A-Za-z_#][\w-]*:?/.test(l) && !/^\s/.test(l));
  if (end < 0) end = lines.length;
  const text = lines.slice(start, end).join('\n').trimEnd();
  if (!same(parseBase(text)[key], parseBase(baseText)[key])) throw new Error(`the ${key}: block does not parse to the file's own`);
  return text;
}

/** A file: its name (a link), Copy (site.js), and its text. The same markup as the case pages'. */
const file = (label, text, href, codeId) => `<div class="file"><div class="file-bar">${href ? `<a href="${esc(href)}">${esc(label)}</a>` : `<span class="file-name">${esc(label)}</span>`}<button class="copy" type="button">Copy</button></div><pre><code${codeId ? ` id="${codeId}"` : ''}>${esc(text)}</code></pre></div>`;

export function buildDocsPages({ root, out, page, write, examples, registered, manifests, viewsTable, statusOf }) {
  for (const f of ['docs.css', 'docs.js']) cpSync(join(root, 'site', f), join(out, f));
  const rel = '../';
  const byCase = new Map(examples.map((ex) => [ex.slug, ex]));
  const caseOf = (slug) => { const ex = byCase.get(slug); if (!ex) throw new Error(`docs: no gallery case ${slug}`); return ex; };
  const npmOf = (type) => { const r = registered.find((v) => v.type === type); const m = r && manifests.find((x) => x.folder === r.folder); return m ? m.npm || [] : []; };
  let demoN = 0;

  /** A live view, started by docs.js when it scrolls near: the case's own .base, one view, no URL state. */
  const preview = ({ slug, view, type, height = '420px', toolbar = 'none', rail = false, attrs = {}, id, switchId }) => {
    const ex = caseOf(slug);
    const want = ex.base.views.find((v) => v.name === view);
    if (!want) throw new Error(`docs: ${slug} has no view ${view}`);
    const box = id || `demo-${++demoN}`;
    return `<div class="dd-preview"${switchId ? ` data-switch-id="${switchId}"` : ''} data-id="${box}" data-src="${rel}gallery/${slug}/views.base" data-view="${esc(view)}" data-type="${esc(type || want.type || 'table')}" data-toolbar="${toolbar}" data-label="${esc(ex.title)}: ${esc(view)}"${Object.keys(attrs).length ? ` data-attrs="${esc(JSON.stringify(attrs))}"` : ''} style="--demo-height:${height}">
  <div class="demo${rail ? ' has-rail' : ''}" style="--demo-height:${height}"></div>
  <p class="dd-wait muted">The live view starts when it scrolls into sight.</p>
</div>`;
  };

  /** A block: title, badge, one line, Preview | Code, and where it comes from. `slot` keeps a landed block's
      [data-slot] (the pending block it replaced), so the checks and the integrator still find it. */
  const block = ({ id, slot, title, code, desc, kind = 'live', slug, view, type, height, toolbar, rail, attrs, switchId, foot = '', extra = '' }) => {
    const ex = caseOf(slug);
    const entry = viewEntryText(ex.baseText, view);
    return `<section class="dd-block" id="${id}"${slot ? ` data-slot="${slot}"` : ''} aria-labelledby="${id}-h">
  <div class="dd-head"><h3 id="${id}-h">${title}${code ? ` <code>${esc(code)}</code>` : ''}</h3>${badge(kind)}</div>
  ${desc ? `<p class="dd-desc">${desc}</p>` : ''}
  <div class="dd-tabs" role="tablist" aria-label="${esc(String(title).replace(/<[^>]+>/g, ''))}"><button type="button" role="tab" id="${id}-tp" aria-controls="${id}-p" aria-selected="true">Preview</button><button type="button" role="tab" id="${id}-tc" aria-controls="${id}-c" aria-selected="false" tabindex="-1">Code</button></div>
  <div class="dd-tabpanel" id="${id}-p" role="tabpanel" aria-labelledby="${id}-tp">${preview({ slug, view, type, height, toolbar, rail, attrs, switchId })}</div>
  <div class="dd-tabpanel" id="${id}-c" role="tabpanel" aria-labelledby="${id}-tc" hidden>${file(`gallery/${slug}/views.base · “${view}”`, entry, `${rel}gallery/${slug}/views.base`)}</div>
  ${extra}
  <p class="dd-foot">From the example <a href="${rel}gallery/${slug}/index.html">${esc(ex.title)}</a>${foot ? ` · ${foot}` : ''}</p>
</section>`;
  };

  /** A live element that is not one view: a whole <data-dashboard>, a <data-analysis> or a <data-analyses> list,
      started by docs.js when it scrolls near (it loads dashboard.js or analysis.js then, as site.js does for a case page). */
  const livePreview = ({ kind, src, label, height = '640px' }) => `<div class="dd-preview dd-preview-${kind}" data-kind="${kind}" data-id="demo-${++demoN}" data-src="${esc(src)}" data-label="${esc(label)}" style="--demo-height:${height}">
  <div class="demo"></div>
  <p class="dd-wait muted">The live ${kind === 'analyses' ? 'list' : kind} starts when it scrolls into sight.</p>
</div>`;

  /** A block around a live dashboard or analysis: Preview | Code, the Code being the keys of the file it draws.
      `slot` keeps the [data-slot] the pending block had, so the checks (and the integrator) still find it. */
  const liveBlock = ({ id, slot, title, code, desc, kind, src, label, height, codeLabel, codeText, codeHref, foot = '', extra = '' }) => `<section class="dd-block" id="${id}"${slot ? ` data-slot="${slot}"` : ''} aria-labelledby="${id}-h">
  <div class="dd-head"><h3 id="${id}-h">${title}${code ? ` <code>${esc(code)}</code>` : ''}</h3>${badge('live')}</div>
  ${desc ? `<p class="dd-desc">${desc}</p>` : ''}
  <div class="dd-tabs" role="tablist" aria-label="${esc(String(title).replace(/<[^>]+>/g, ''))}"><button type="button" role="tab" id="${id}-tp" aria-controls="${id}-p" aria-selected="true">Preview</button><button type="button" role="tab" id="${id}-tc" aria-controls="${id}-c" aria-selected="false" tabindex="-1">Code</button></div>
  <div class="dd-tabpanel" id="${id}-p" role="tabpanel" aria-labelledby="${id}-tp">${livePreview({ kind, src, label, height })}</div>
  <div class="dd-tabpanel" id="${id}-c" role="tabpanel" aria-labelledby="${id}-tc" hidden>${file(codeLabel, codeText, codeHref)}</div>
  ${extra}
  ${foot ? `<p class="dd-foot">${foot}</p>` : ''}
</section>`;
  /** Several entries of a views: list, cut as written, under one views: key. */
  const viewsText = (ex, names) => ['views:', ...names.map((n) => viewEntryText(ex.baseText, n).split('\n').map((l) => `  ${l}`).join('\n'))].join('\n');

  /** A block whose thing is not on main yet: the planned syntax, from the lane, in a [data-slot] for the integrator. */
  const pending = ({ id, slot, title, kind, desc, body = '', snippet, label }) => `<section class="dd-block dd-pending" id="${id}" data-slot="${slot}" aria-labelledby="${id}-h">
  <div class="dd-head"><h3 id="${id}-h">${title}</h3>${badge(kind)}</div>
  ${desc ? `<p class="dd-desc">${desc}</p>` : ''}
  ${body}
  ${snippet ? file(label || 'planned syntax', snippet) : ''}
  <p class="dd-foot">${snippet ? `Planned syntax, from ${esc(LANES[kind])}. ` : ''}Not on main yet: this block becomes live when ${snippet ? 'that lane' : esc(LANES[kind])} lands.</p>
</section>`;

  // ---- the sidebar: the same on every page here, so the reader's width (remembered) and place carry across
  const TYPE_BLOCKS = [
    { type: 'table', title: 'Table', slug: 'robotparts-actuators', view: 'By brand', height: '460px', foot: 'two group levels, summaries, bars in cells' },
    { type: 'pivot', title: 'Pivot', slug: 'models-benches', view: 'Benchmarks' },
    { type: 'list', title: 'List and tree', slug: 'vibetracks-feature-tree', view: 'Spec tree', foot: 'with <code>tree:</code>, an outline that folds' },
    { type: 'cards', title: 'Cards and media grid', slug: 'robotparts-photos', view: 'Actuators', height: '480px', foot: '<code>lightbox: true</code> opens each photo full screen' },
    { type: 'kanban', title: 'Kanban', slug: 'vibetracks-board', view: 'By status', height: '460px', foot: 'a drag proposes an edit; the host decides' },
    { type: 'chart', title: 'Chart', slug: 'actuator-charts', view: 'Ashby · torque vs mass', height: '460px', foot: 'inside <code>chart:</code> the vocabulary is Vega-Lite\'s' },
    { type: 'kpi', title: 'KPI', slug: 'vibetracks-kpis', view: 'KPIs', height: '360px', foot: 'the delta is coloured by which way is better' },
    { type: 'calendar', title: 'Calendar', slug: 'robotparts-calendar', view: 'Month', height: '520px' },
    { type: 'timeline', title: 'Timeline', slug: 'robotparts-timeline', view: 'Lanes by kind', height: '420px' },
    { type: 'map', title: 'Map', slug: 'robotparts-sellers-map', view: 'Where sellers ship', height: '440px', foot: 'a bundled world map, no tile server' },
    { type: 'graph', title: 'Graph', slug: 'rack-wiring', view: 'Wiring', height: '460px' },
    { type: 'record', title: 'Record and form', slug: 'robotparts-compare', view: 'Part page', height: '460px', foot: 'with <code>edit: true</code> the record is a form' },
    { type: 'compare', title: 'Compare', slug: 'robotparts-compare', view: 'Side by side', height: '460px' },
  ];
  const built = new Set(registered.filter((v) => v.status === 'built').map((v) => v.type));
  const typeBlocks = TYPE_BLOCKS.filter((b) => built.has(b.type));
  const DOCS = [
    { slug: 'filters-and-facets', title: 'Filters and facets', from: 'CONTRACT §7', line: 'The rail beside a view: its kinds, what each writes, and the URL it keeps.' },
    { slug: 'frames', title: 'Frames', from: 'CONTRACT §12', line: 'How a <code>&lt;data-views&gt;</code> sits in its page: boxed, flush, tabs, sheet, page, bleed.' },
    { slug: 'open-modes', title: 'Open modes', from: 'CONTRACT §13, PEP 0003', line: 'What a click on a row does: expand a band, open the side peek, or go to the page.' },
    { slug: 'resizable-panels', title: 'Resizable panels', from: 'CONTRACT §11', line: 'Every side panel drags, remembers its width and resets on a double-click.' },
    { slug: 'explain-the-data', title: 'Explain the data', from: 'CONTRACT §16', line: 'An answer above the rows, roll-ups, column groups and readable number cells.' },
    { slug: 'time-groups-and-peek-trail', title: 'Time groups and peek trail', from: 'CONTRACT §14', line: 'Group dates by day, week, month, quarter or year; follow relations inside the peek.' },
    { slug: 'performance', title: 'Performance', from: 'bench/KPIS.md', line: 'What the bench measures, the budgets, and where the numbers go.' },
    { slug: 'toolbar-presets', title: 'Toolbar presets', from: 'CONTRACT §15, PEP 0002', line: 'The one-row bar: the mix, and Shopify, Notion and Obsidian presets.' },
    { slug: 'embedded-chrome', title: 'Embedded chrome', from: 'CONTRACT §18', line: 'Turn off the status line and a view\'s own control bar when it is one part of your page.' },
    { slug: 'value-sources', title: 'Value sources', from: 'CONTRACT §22', line: 'Right-click a value, a photo or a file: where it comes from, and a citation to copy.', head: `\n<script type="module" src="${rel}kit/sources.js"></script>` },
    { slug: 'rerun-interop', title: 'Rerun interop', from: 'PEP 0005 §6', line: 'Open a dashboard\'s recording in Rerun.', kind: 'cards' },
    { slug: 'add-to-dashboard', title: 'Add to dashboard', from: 'CONTRACT §34', line: 'Add any view, a series or a card to the bottom of a dashboard; your page saves the file.' },
  ];
  const NAV = [
    { group: 'Views', items: [['views/index.html', 'Overview and status'], ...typeBlocks.map((b) => [`views/index.html#type-${b.type}`, b.title]),
      ['views/index.html#time-series', 'Time series'], ['views/index.html#explain', 'Explain the data']] },
    { group: 'Dashboards', items: [['dashboards/index.html', 'Dashboards'], ['dashboards/index.html#file', 'The dashboard file'],
      ['dashboards/index.html#datasets', 'Datasets, links and roll-ups'], ['dashboards/index.html#rail', 'One rail, click to filter'],
      ['dashboards/index.html#cards', 'Card catalog', 'soon'], ['dashboards/index.html#clock', 'Synced clock', 'soon']] },
    { group: 'Analyses', items: [['analyses/index.html', 'Analyses'], ['analyses/index.html#page', 'An analysis page'], ['analyses/index.html#embedded', 'Embedding views'],
      ['analyses/index.html#list', 'The list of analyses']] },
    { group: 'How it works', items: [['docs/index.html', 'Overview'], ...DOCS.map((d) => [`docs/${d.slug}.html`, d.title, d.kind ? 'soon' : ''])] },
  ];
  // WHY a place on a page shows only on that page: the sidebar lists every page, and the open page's own sections
  // under it (shadcn's docs sidebar), so the whole list fits a laptop's height
  const sidebar = (current) => `<aside class="docs-side" id="docs-side" aria-label="Documentation" data-resizable="right" data-resizable-min="180" data-resizable-max="420" data-resizable-key="docs-side">
  <button class="docs-menu" type="button" aria-expanded="false" aria-controls="docs-nav">Menu</button>
  <nav class="docs-nav" id="docs-nav" aria-label="Documentation">${NAV.map(({ group, items }) => `
    <h4>${group}</h4>
    <ul>${items.filter(([href]) => !href.includes('#') || href.split('#')[0] === current).map(([href, label, soon]) => `<li${href.includes('#') ? ' class="sub"' : ''}><a href="${rel}${href}"${href === current ? ' aria-current="page"' : ''}>${esc(label)}${soon ? ' <span class="soon-dot" title="Not on main yet">soon</span>' : ''}</a></li>`).join('')}</ul>`).join('')}
  </nav>
</aside>`;
  const head = `\n<link rel="stylesheet" href="${rel}docs.css">`;
  const docsPage = ({ path, title, nav, description, body, extraHead = '' }) => write(path, page({
    title: `${title} · data-ui`, rel, nav, description, head: head + extraHead, script: `${rel}docs.js`,
    body: `<div class="docs">
${sidebar(path)}
<main class="docs-main">
${body}
</main>
</div>`,
  }));
  const from = (text) => `<p class="dd-source">Comes from <b>${text}</b> in <code>docs/</code>.</p>`;

  // ======== Views
  const builtCount = viewsTable.filter((r) => statusOf(r) === 'built').length;
  const typeHtml = typeBlocks.map((b) => {
    const r = registered.find((v) => v.type === b.type);
    const m = manifests.find((x) => x.folder === r.folder);
    const npm = npmOf(b.type);
    const covers = (m && m.covers) || [];
    return block({ id: `type-${b.type}`, title: b.title, code: `type: ${b.type}`, desc: esc(r.summary), slug: b.slug, view: b.view, type: b.type, height: b.height,
      foot: [b.foot, npm.length ? `stock part <code>${esc(npm[0])}</code>` : 'no library: ours', covers.length ? `also covers ${covers.map(esc).join(', ')}` : ''].filter(Boolean).join(' · ') });
  }).join('\n');
  const grains = [['day', '2026-10-20', 'Tue 20 Oct 2026'], ['week', '2026-10-19', 'Week of 19 Oct 2026'], ['month', '2026-10', 'Oct 2026'], ['quarter', '2026-Q4', 'Q4 2026'], ['year', '2026', '2026']];
  docsPage({
    path: 'views/index.html', title: 'Views', nav: 'Views', description: 'Every view type data-ui draws, live on real data, with its .base entry.',
    body: `<p class="crumbs">Views</p>
<h1>Views</h1>
<p class="lede">Every view reads the same row model and the same <code>.base</code> file; <code>type:</code> picks one. ${builtCount} of ${viewsTable.length} are built; the rest are planned, each with its stock library already chosen and installed (docs/VIEWS.md). A planned type in a <code>.base</code> file draws the table with a one-line notice.</p>
<section id="status" aria-labelledby="status-h">
  <h2 id="status-h">Which views are built</h2>
  <div class="tablewrap"><table class="views">
  <thead><tr><th>View</th><th>.base type</th><th>Status</th><th>Stock part</th><th>Priority</th></tr></thead>
  <tbody>${viewsTable.map((r) => `<tr><td><b>${esc(r.view)}</b><div class="why">${esc(r.why)}</div></td><td><code>${esc(r.typeCell)}</code></td><td><span class="status status-${statusOf(r)}">${statusOf(r)}</span></td><td>${esc(r.selected)}${r.npm ? `<div class="npm"><code>${esc(r.npm)}</code></div>` : ''}</td><td>${esc(r.priority)}</td></tr>`).join('')}</tbody>
  </table></div>
</section>
<section id="types" aria-labelledby="types-h">
  <h2 id="types-h">Every view, live</h2>
  <p class="section-lede">Each block is one entry of an example's <code>.base</code> file. <b>Preview</b> runs the real kit on the example's real data (it starts when you scroll to it); <b>Code</b> is the entry that draws it, cut from the file as written.</p>
${typeHtml}
</section>
<section id="time-series" aria-labelledby="ts-h">
  <h2 id="ts-h">Time series</h2>
  <p class="section-lede">Dates are grouped in the core, so every view gets the same buckets: a group level takes <code>by: day | week | month | quarter | year</code>, and a chart's date channel takes the same <code>by:</code>. The date is the one written: a date-only value is never shifted, and a datetime is bucketed by the calendar date in its own offset, never the viewer's time zone. Weeks start on Monday. More in <a href="${rel}docs/time-groups-and-peek-trail.html">Time groups and peek trail</a>.</p>
  <div class="tablewrap"><table class="plain-table"><thead><tr><th><code>by:</code></th><th>Bucket key (sorts in time order)</th><th>Label</th></tr></thead>
  <tbody>${grains.map(([g, k, l]) => `<tr><td><code>${g}</code></td><td><code>${k}</code></td><td>${l}</td></tr>`).join('')}</tbody></table></div>
${block({ id: 'ts-group', title: 'Rows grouped by week', code: 'groupBy: {property, by: week}', desc: 'A table whose group level is a date bucket: one group per week, oldest first; the rows inside a week keep the view\'s sort. <code>gaps: true</code> would keep the empty weeks too.', slug: 'ml-experiments', view: 'Runs by week', height: '440px' })}
${block({ id: 'ts-axis', title: 'A time axis', code: 'x: {field, by: week}', desc: 'A chart whose x is a week: one band per bucket, labelled as the table labels it, every week from the first to the last, so an empty week is an empty band and the axis holds still while you filter. WHY not Vega-Lite\'s own <code>timeUnit</code>: its weeks start on Sunday and it reads dates in the viewer\'s zone.', slug: 'ml-experiments', view: 'Runs per week', height: '420px' })}
${block({ id: 'ts-timeline', title: 'Timeline', code: 'type: timeline', desc: 'Bars from <code>start</code> to <code>end</code> (or points), in lanes from <code>groupBy</code>, nested by <code>subGroupBy</code>; scroll to zoom within <code>zoom: {min, max}</code>.', slug: 'robotparts-timeline', view: 'By release', height: '440px' })}
${block({ id: 'ts-calendar', title: 'Calendar', code: 'calendarView: week', desc: 'The same dates on a week grid; <code>month</code>, <code>day</code> and <code>list</code> are the other grids. Dragging an event proposes a new date to the host.', slug: 'robotparts-calendar', view: 'Release week', height: '480px' })}
${block({ id: 'ts-kpi', title: 'KPI sparklines and gates', code: 'kpi: {spark, gate}', desc: 'One card per group, each with its history as a sparkline (<code>spark: {x, y}</code>) and a gate line; with <code>compare:</code> a card also shows its delta, coloured by which way is better.', slug: 'ml-experiments', view: 'Pooled success by model', height: '380px' })}
</section>
<section id="explain" aria-labelledby="ex-h">
  <h2 id="ex-h">Explain the data</h2>
  <p class="section-lede">A view can open with its answer and make its numbers readable: <code>intro:</code> puts markdown and KPI cards above the rows, <code>rollup:</code> collapses a dimension, <code>columnGroups:</code> adds a header over related columns, and the <code>stats</code>, <code>range</code>, <code>value</code>, <code>dist</code> and <code>markdown</code> displays draw a number with its spread. More in <a href="${rel}docs/explain-the-data.html">Explain the data</a>.</p>
${block({ id: 'ex-intro', title: 'An answer first, rolled up', code: 'intro: {text, kpi} · rollup:', desc: 'Markdown and KPI cards above the rows, then every model ranked with the actuators rolled away (each cell a median with its spread). <b>Roll up</b> in the toolbar of the full case brings them back.', slug: 'robotparts-models', view: 'Leaderboard', height: '560px' })}
${block({ id: 'ex-groups', title: 'Column groups', code: 'columnGroups:', desc: 'A header over related columns (Friction, Capture, Drivetrain, Driver); <code>display: value</code> puts the basis mark beside each number and its 95 % interval in the hover.', slug: 'robotparts-models', view: 'Parameters', height: '520px' })}
${block({ id: 'ex-stats', title: 'Sub-columns for a value and its interval', code: 'display: stats', desc: 'One property split into value, low, high and basis, each in its own column under the property\'s label, instead of the range squeezed into one cell.', slug: 'robotparts-models', view: 'Parameters · with CI', height: '480px' })}
${block({ id: 'ex-dist', title: 'Distributions on one scale', code: 'display: dist', desc: 'Every run as a dot, their median a tall tick, on one scale down the column with its ends drawn in the header, so rows compare at a glance.', slug: 'robotparts-models', view: 'What each rung adds', height: '520px' })}
</section>`,
  });

  // ======== Dashboards: <data-dashboard> is on main (docs/CONTRACT.md §17, docs/peps/0004-dashboards.md). Each live
  // block is a gallery case's own dashboard and its Code the keys it uses, cut from that file; the card catalog and the
  // synced clock are still on lane/dashboard-cards and keep their pending slots.
  const vt = caseOf('vibetracks-dashboard');
  const runsCase = caseOf('vibetracks-runs');
  const pid = caseOf('pid-tuning');
  const fromCase = (ex, more = '') => `From the example <a href="${rel}gallery/${ex.slug}/index.html">${esc(ex.title)}</a>${more ? ` · ${more}` : ''}`;
  // lane/dashboard-cards' gallery/examples/dashboard-cards/views.base
  const CARDS_SNIPPET = `views:
  - type: playback
    name: Playback
    playback: { speeds: [0.25, 0.5, 1, 2], range: true, readout: true }
  - type: timeseries
    name: Error over time
    filters: 'joint == "elbow_joint" && situation != "target"'
    timeseries:
      x: t
      y: err_mrad
      series: situation
      unit: mrad
      rules: [{ y: 5, label: "gate 5 mrad", tone: bad }, { y: -5, tone: bad }]
      bands: [{ y: [-5, 5], label: tolerance, tone: good }]
  - type: video-compare
    name: Overlay
    from: media
    overlay: { by: situation, a: tuned, b: factory, mode: wipe, split: 0.5 }
  - type: trajectory
    name: Tool path (XZ)
    from: tool
    trajectory: { x: px, y: pz, series: situation, target: target, t: t, trail: true, tolerance: 0.005 }`;
  const CLOCK_SNIPPET = `style:
  chrome: minimal
  numbers: { digits: 3, compact: true }
  palette: { target: "#8b9099", factory: "#e8743b", tuned: "#2a78d6", oracle: "#19a979" }
clock:
  data: samples
  time: t
  loop: true
  fps: 30`;
  const CARDS = [
    ['kpi', 'a stat with its delta, coloured by which way is better, and a sparkline', 'ours (exists today)', ''],
    ['gauge', 'a bar or semicircle against a target or gate', 'ours (SVG/CSS)', ''],
    ['bullet', 'a value bar, a target tick and qualitative bands', 'ours (SVG)', ''],
    ['barlist', 'a ranked bar list, a leaderboard', 'ours (CSS)', ''],
    ['status', 'one cell per row, coloured by a state (a tracker grid)', 'ours (CSS)', ''],
    ['timeseries', 'lines or areas over t: bands, rules, a log axis, brush-zoom, a shared crosshair, the playhead', 'Vega-Lite', 'yes'],
    ['chart', 'bar, histogram, scatter, heatmap: any Vega-Lite', 'Vega-Lite (exists today)', ''],
    ['trajectory', 'a 2D path against its target, equal aspect, coloured by error, a tolerance tube', 'Vega-Lite', 'yes'],
    ['scene3d', '3D paths, a moving marker, an optional stick robot', 'three.js', 'yes'],
    ['video', 'one video that seeks to the clock', 'the browser', 'yes'],
    ['video-compare', 'two videos: wipe, onion skin, difference or side by side', 'the browser + CSS', 'yes'],
    ['image', 'an image, or a strip of them from rows', 'the browser', ''],
    ['playback', 'the clock\'s control: play, scrub, speed, loop, step a frame, a range', 'ours', 'is the clock'],
  ];
  docsPage({
    path: 'dashboards/index.html', title: 'Dashboards', nav: 'Dashboards', description: 'A dashboard is a .base file with layout: — panels on a 12-column grid over linked datasets.',
    body: `<p class="crumbs">Dashboards</p>
<h1>Dashboards</h1>
<p class="lede">A dashboard is a <code>.base</code> file with a <code>layout:</code>. Every panel is an ordinary view of that file, placed on a 12-column grid; <code>datasets:</code> names more data files, <code>links:</code> says how their rows relate, one rail filters every panel, and a click in one panel can narrow the others. <code>&lt;data-dashboard src="x.base"&gt;</code> draws it.</p>
<div class="callout"><p><b>On main now:</b> <code>&lt;data-dashboard&gt;</code>, <code>layout:</code>, <code>datasets:</code>, <code>links:</code>, <code>select:</code> and <code>rollup:</code> (<code>dist/dashboard.js</code>, CONTRACT §17). Every block below is a real dashboard from the examples, live. The card catalog and the synced clock are still on lane/dashboard-cards: ${badge('cards')}</p></div>

<section id="file" aria-labelledby="file-h">
  <h2 id="file-h">The dashboard file</h2>
  <p class="section-lede"><code>layout:</code> sits next to <code>views:</code>. Panels are in reading order; <code>w</code> is the number of columns (of 12) and <code>h</code> the height in row units (110 px each). A panel is <code>{view}</code>, <code>{views: [...]}</code> (several views as tabs inside the panel) or <code>{text}</code> (markdown). Under 900 px the grid is one column. Obsidian opens the same file and shows the panels as tabs.</p>
${liveBlock({ id: 'dash-layout', slot: 'dashboard-live', title: 'A dashboard, live', code: 'layout:', kind: 'dashboard', src: `${rel}gallery/${vt.slug}/views.base`, label: vt.title, height: '900px',
    desc: 'Vibe Tracks\' track overview: a text panel, a strip of KPI cards, the track tree beside a bar chart, and one panel holding two views as tabs. <b>Code</b> is its <code>layout:</code>; every panel names a view of the same file.',
    codeLabel: `gallery/${vt.slug}/views.base · layout:`, codeText: topKeyText(vt.baseText, 'layout'), codeHref: `${rel}gallery/${vt.slug}/views.base`,
    extra: file('index.html', `<script type="module" src="/vendor/data-ui/data-ui.js"></script>\n<script type="module" src="/vendor/data-ui/dashboard.js"></script>\n\n<data-dashboard src="views.base"></data-dashboard>`),
    foot: fromCase(vt, 'a page without a dashboard never loads <code>dashboard.js</code>') })}
</section>

<section id="datasets" aria-labelledby="ds-h">
  <h2 id="ds-h">Several datasets, linked, and roll-ups</h2>
  <p class="section-lede"><code>datasets:</code> names each data file; a view picks one with <code>from:</code> (default: the file's own <code>data:</code>). <code>links:</code> says which property of one dataset holds the ids of another's rows. A link filters, it never adds a column: "show the runs of the tracks that pass the rail" reaches the runs panel as an ordinary filter on <code>track</code>, visible in that panel's Filter menu. Links work both ways and chain (kpis → tracks → runs).</p>
${liveBlock({ id: 'dash-datasets', slot: 'dashboard-datasets', title: 'Two datasets, one link, a roll-up', code: 'datasets: · links: · rollup:', kind: 'dashboard', src: `${rel}gallery/${runsCase.slug}/views.base`, label: runsCase.title, height: '1100px',
    desc: 'Vibe Tracks\' run explorer. The runs are the file\'s own <code>data:</code>; <code>tracks</code> is a second dataset, linked by <code>runs.track → tracks.id</code>. The <b>Leaderboard</b> panel reads <code>tracks</code>\' roll-up: each track\'s newest run per suite, summed through its child tracks. Hover a pass rate there: the cell says it is derived and from how many rows. Tick an area in the rail (a <code>tracks</code> facet) and the runs follow through the link.',
    codeLabel: `gallery/${runsCase.slug}/views.base · datasets: and links:`, codeText: `${topKeyText(runsCase.baseText, 'datasets')}\n${topKeyText(runsCase.baseText, 'links')}`, codeHref: `${rel}gallery/${runsCase.slug}/views.base`,
    foot: fromCase(runsCase) })}
  <ul class="rules">
    <li><b>A roll-up is a computed column</b> on a dataset with a <code>tree:</code>: <code>rollup: {from, latest: {by, per}, values: {&lt;column&gt;: {property, summary, per}}}</code>. It reads one direct link to <code>from</code>, keeps the newest row per <code>per</code> when <code>latest:</code> says so, and sums through the tree, so a parent shows its children's numbers.</li>
    <li><b><code>summary</code></b> is a Bases summary name, or <code>Ratio</code>: Σ<code>property</code> / Σ<code>per</code>, a ratio of sums, never a mean of ratios.</li>
    <li><b>Its cells say what they are:</b> <code>{value, basis: derived, n, note}</code>, drawn hollow like an estimate. A producer's own headline number is never recomputed.</li>
    <li><b>A roll-up reads only its source dataset's own filters,</b> so ticking a track in the rail does not shrink the totals it is ranked by.</li>
  </ul>
</section>

<section id="rail" aria-labelledby="rail-h">
  <h2 id="rail-h">One rail, click to filter</h2>
  <ul class="rules">
    <li><b>One rail.</b> Each dataset's <code>facets:</code> is its part of the rail. Its counts include every other restriction, so a count says what a tick would leave. The rail's edge drags, like every side panel.</li>
    <li><b>What a panel shows:</b> its dataset's rail filter, every selection other panels made on it, and a semi-join from every other restricted dataset that has a link path to it. Its own <code>filters:</code> still apply.</li>
    <li><b>Click to filter.</b> <code>select: &lt;property&gt;</code> on a view: a click on a bar, a card or a row selects that property's values for the whole dashboard; clicking again clears it. The panel you clicked ignores its own selection, so you can click another bar (Superset's and Mosaic's rule). Chips above the grid show each selection.</li>
    <li><b>Drill down.</b> A click on a panel without <code>select:</code> opens one side peek for the whole dashboard, resizable like every side panel.</li>
    <li><b>The URL holds it all:</b> <code>?health=green&amp;runs.kind=tests</code> for the rails, <code>#s.&lt;panel&gt;=track:a,b</code> for selections, <code>#p.&lt;panel&gt;=&lt;view&gt;</code> for a panel's tab. Reload and Back restore it. (The demos here are <code>no-url</code>, so they leave this page's address alone.)</li>
  </ul>
${liveBlock({ id: 'dash-select', slot: 'dashboard-select', title: 'Cross-filtering with select:', code: 'select:', kind: 'dashboard', src: `${rel}gallery/${pid.slug}/views.base`, label: pid.title, height: '1300px',
    desc: 'pidtuna\'s four-rung ladder on nine simulated robots. Click a KPI card or a point: <code>select: robot_id</code> narrows every panel over the gains to that robot, and a chip above the grid says so (click the chip to clear it). Click a bar in Error by rung to select a rung as well. The rack\'s data at the bottom has no link to the robots, so their rail and selections leave its two panels alone.',
    codeLabel: `gallery/${pid.slug}/views.base · the three views with select:`, codeText: viewsText(pid, ['Tuned against the oracle', 'Gain vs error', 'Error by rung']), codeHref: `${rel}gallery/${pid.slug}/views.base`,
    foot: fromCase(pid, 'simulated robots with illustrative parameters, and said so on the dashboard') })}
</section>

<section id="cards" aria-labelledby="cards-h">
  <h2 id="cards-h">The card catalog</h2>
  <p class="section-lede">A card is a view: every card is a <code>type:</code> in <code>views:</code>, placed by <code>layout:</code> like a table or a chart. Only its own keys are new.</p>
${pending({ id: 'dash-cards', slot: 'card-catalog', title: 'Every card type', kind: 'cards', body: `<div class="tablewrap"><table class="plain-table"><thead><tr><th><code>type:</code></th><th>Draws</th><th>Stock part</th><th>Follows the clock</th></tr></thead><tbody>${CARDS.map(([t, d, p, c]) => `<tr><td><code>${t}</code></td><td>${esc(d)}</td><td>${esc(p)}</td><td>${esc(c)}</td></tr>`).join('')}</tbody></table></div>`, snippet: CARDS_SNIPPET, label: 'gallery/dashboard-cards/views.base · four cards (planned syntax)' })}
</section>

<section id="clock" aria-labelledby="clock-h">
  <h2 id="clock-h">One clock, synced</h2>
  <p class="section-lede">Time is one more piece of dashboard state. One clock per dashboard sets <em>t</em>; every time-aware card follows it: a video seeks, a time series draws its playhead, a trajectory and a 3D scene move their marker. The <code>playback</code> card is its control. <code>#t=3.20</code> in the URL lands a shared link on the same instant.</p>
${pending({ id: 'dash-clock', slot: 'synced-clock', title: 'The clock and the dashboard\'s look', kind: 'cards', desc: 'Playing, a primary video drives the clock and the other videos follow it (a jump when more than 0.1 s off, a ±5 % nudge when close). Paused, a seek places every video, playhead and marker in the same task. Keys: Space, ← / → a frame, Shift+← / → a second, J / K / L, [ and ] for the range. <code>style:</code> sets about ten dashboard-wide knobs (surface, radius, gaps, titles, chart chrome, number format, a colour per series name); a panel may override any of them.', snippet: CLOCK_SNIPPET, label: 'gallery/dashboard-cards/views.base · style: and clock: (planned syntax)' })}
</section>`,
  });

  // ======== Analyses: <data-analysis> and <data-analyses> are on main (docs/CONTRACT.md §19, docs/peps/0007-analyses.md);
  // the blocks draw the analyses case's own files
  const an = caseOf('analyses');
  const anText = readFileSync(join(an.here, 'shoulder-actuator.md'), 'utf8');
  const fence = (/```base\n[\s\S]*?\n```/.exec(anText) || [''])[0];
  const embedLine = (/^!\[\[.+\]\]$/m.exec(anText) || [''])[0];
  const dashEmbed = (/^!\[\[.+\]\]$/m.exec(readFileSync(join(an.here, 'pid-gains.md'), 'utf8')) || [''])[0];
  // WHY a copy of the list's rows: each row's url is its page beside its .md (pid-gains.html), relative to the case's
  // folder; from this page that is ../gallery/analyses/, so the list here reads the same rows with those links
  const index = JSON.parse(readFileSync(join(an.here, 'analyses.json'), 'utf8'));
  const relUrl = (u) => (u && !/^([a-z][\w+.-]*:|\/)/i.test(u) ? `${rel}gallery/${an.slug}/${u}` : u);
  mkdirSync(join(out, 'analyses'), { recursive: true });
  writeFileSync(join(out, 'analyses', 'list.json'), JSON.stringify({ ...index, rows: index.rows.map((r) => ({ ...r, url: relUrl(r.url) })) }, null, 1));
  writeFileSync(join(out, 'analyses', 'list.base'), an.baseText.replace(/^data: .*$/m, 'data: list.json'));
  docsPage({
    path: 'analyses/index.html', title: 'Analyses', nav: 'Analyses', description: 'Report pages that mix markdown, embedded views and dashboards, with a sticky contents list and decision callouts.',
    body: `<p class="crumbs">Analyses</p>
<h1>Analyses</h1>
<p class="lede">An analysis is a page that answers one question, like a Weights &amp; Biases report: markdown prose, with views and dashboards embedded wherever the argument needs them, a contents list that stays in view as you scroll, and callouts that record what was decided and why. It is one Markdown file an agent can write.</p>
<div class="callout"><p><b>On main now:</b> <code>&lt;data-analysis&gt;</code> and <code>&lt;data-analyses&gt;</code> (<code>dist/analysis.js</code>, CONTRACT §19). The blocks below are the analyses example's own files, live.</p></div>
${tiersHtml(rel)}
<h2>How it builds on the other two</h2>
<ul class="rules">
  <li><b>It embeds, it does not copy.</b> A view in an analysis is the same <code>&lt;data-views&gt;</code> on the same <code>.base</code> file as everywhere else; a dashboard is the same <code>layout:</code>. Change the file and every analysis that embeds it shows the change.</li>
  <li><b>A sticky contents list</b> down the side, from the page's headings and its decision, so a long analysis stays easy to move around. Its edge drags.</li>
  <li><b>Decision callouts:</b> a boxed verdict (what was decided, and the evidence it rests on) that reads on its own when someone skims.</li>
  <li><b>A list of analyses,</b> as a table, a gallery of cards or a board by status, so past answers are easy to find again.</li>
</ul>
<section id="page" aria-labelledby="page-h">
  <h2 id="page-h">An analysis page</h2>
${liveBlock({ id: 'an-page', slot: 'analyses-live', title: 'An analysis, live', code: '<data-analysis src>', kind: 'analysis', src: `${rel}gallery/${an.slug}/shoulder-actuator.md`, label: 'Shoulder actuator for a 1-DOF arm', height: '1400px',
    desc: 'robotparts\' shoulder-actuator analysis, one Markdown file. On the left, the contents (sticky as you scroll; drag its edge). Then the header: status, question, the parts considered, the decision, Copy as Markdown and Download. Then the prose: an <code>[!illustrative]</code> load, a <code>```base</code> fence drawn as a table and a compare view, one embedded chart from another example, and the <code>[!decision]</code> callout.',
    codeLabel: `gallery/${an.slug}/shoulder-actuator.md`, codeText: anText, codeHref: `${rel}gallery/${an.slug}/shoulder-actuator.md`,
    extra: file('index.html', `<script type="module" src="/vendor/data-ui/data-ui.js"></script>\n<script type="module" src="/vendor/data-ui/analysis.js"></script>\n\n<data-analysis src="shoulder-actuator.md"></data-analysis>`),
    foot: `From the example <a href="${rel}gallery/${an.slug}/index.html">${esc(an.title)}</a> · <a href="${rel}gallery/${an.slug}/shoulder-actuator.html">its own page</a> · <code>analysis.js</code> fetches <code>dashboard.js</code> only for the first dashboard it meets` })}
</section>
<section id="embedded" aria-labelledby="embedded-h">
  <h2 id="embedded-h">Embedding views and dashboards</h2>
  <p class="section-lede">Two ways in, both drawn live where they stand in the prose. A <code>.base</code> with <code>layout:</code> is drawn as <code>&lt;data-dashboard&gt;</code>; any other as a <code>&lt;data-views&gt;</code> (no URL state, the compact toolbar).</p>
  <ul class="rules">
    <li><b>A <code>\`\`\`base</code> fence</b> is an inline <code>.base</code>: its <code>data:</code> is a path beside the analysis (or from <code>/</code>, a URL).</li>
    <li><b><code>![[name.base]]</code></b> on its own line embeds a file, looked for beside the analysis and then in each <code>embeds=</code> folder; <code>![[name.base#View]]</code> embeds one of its views.</li>
    <li><b><code>this.&lt;key&gt;</code></b> in any filter is the analysis' frontmatter, as Obsidian binds <code>this</code> in an embedded base: <code>this.parts.contains(id)</code> keeps the parts the note names.</li>
    <li><b>Callouts:</b> <code>&gt; [!decision] Title</code> is the verdict box, <code>[!illustrative]</code> marks what is assumed, <code>[!ai]</code> sets a judgement apart from the numbers; any other type is a plain callout.</li>
    <li><b><code>data-ui check x.md</code></b> checks the frontmatter, then every fence and embed against the data each names, with each problem at its line.</li>
  </ul>
  ${file(`gallery/${an.slug}/shoulder-actuator.md · a fence filtered by this.parts`, fence, `${rel}gallery/${an.slug}/shoulder-actuator.md`)}
  ${file('one view of another example, and a whole dashboard', `${embedLine}\n${dashEmbed}`)}
  <p class="dd-foot">The second line is from <a href="${rel}gallery/${an.slug}/pid-gains.html">Analytic or tuned gains, robot by robot</a>, which embeds the pid-tuning dashboard whole.</p>
</section>
<section id="list" aria-labelledby="list-h">
  <h2 id="list-h">The list of analyses</h2>
${liveBlock({ id: 'an-list', slot: 'analyses-list', title: 'Every analysis, as a table, a gallery or a board', code: '<data-analyses base>', kind: 'analyses', src: 'list.base', label: 'Analyses', height: '320px',
    desc: 'One row per analysis, from its frontmatter: the question, the status, the decision, the parts, when it was written. The tabs switch to a gallery of cards and a board by status; a click opens the analysis.',
    codeLabel: `gallery/${an.slug}/views.base`, codeText: an.baseText, codeHref: `${rel}gallery/${an.slug}/views.base`,
    foot: `From the example <a href="${rel}gallery/${an.slug}/index.html">${esc(an.title)}</a> · the rows are <code>analyses.json</code>, written by <code>source/build.py</code> with <code>data_ui_analysis.build_index</code>` })}
</section>`,
  });
  // ======== Docs
  const DOC_BODIES = {
    'filters-and-facets': () => {
      const ex = caseOf('filters-gallery');
      return `<p class="lede">The rail is <code>&lt;data-facets for="views-id"&gt;</code> beside a <code>&lt;data-views&gt;</code>. It draws the <code>.base</code> file's <code>facets:</code> list and edits one thing: the all-views filter, the same filter the Filter menu, the URL and an agent writing the file use. A tick in the rail shows in the table, the cards and the chart alike.</p>
${block({ id: 'filters-live', title: 'Every kind of facet', desc: 'robotparts\' 1,149 actuators with one facet of each kind. The tabs McMaster-style, Amazon-style, Digi-Key-style and Obsidian-style each carry their own <code>facets:</code>, so switching tab switches the rail.', slug: 'filters-gallery', view: 'Every kind', toolbar: 'full', rail: true, height: '640px' })}
<h2>Write it</h2>
<p>A facet is a property name, or <code>{property, as: &lt;kind&gt;, …options}</code>. Every kind also takes <code>label</code>, <code>info</code> (the ⓘ), <code>diagram</code> and <code>collapsed</code>. An unknown kind draws as <code>values</code> and warns; it never breaks the page.</p>
${file('gallery/filters-gallery/views.base · facets:', topKeyText(ex.baseText, 'facets'), `${rel}gallery/filters-gallery/views.base`)}
<h2>The kinds</h2>
<div class="tablewrap"><table class="plain-table"><thead><tr><th><code>as:</code></th><th>Draws</th><th>Writes</th></tr></thead><tbody>
${[['values', 'checkboxes with counts, Show N more, a find box', 'p == v, or {or:}; .contains on a list'], ['select', 'Any + radios, or a dropdown', 'one p == v'], ['toggle', 'a switch', 'p == <value>'],
  ['has', '"Has a value" per property', '!p.isEmpty(), all or any'], ['range', 'min / max boxes (dates on a date)', 'p >= a, p <= b'], ['slider / slider-histogram', 'two thumbs, the second over the distribution', 'p >= a, p <= b'],
  ['buckets', 'preset ranges as chips', 'p >= a, p < b'], ['rating / min-level', '"★★★☆ & up", "Level ≥ N"', 'p >= N'], ['date', 'from / until, presets, "Older than"', 'p >= "date", p < "date"'],
  ['chips, swatch, gallery, picture-list, grid', 'pressable values: tags, logos, colours, pictures', 'as values'], ['listbox', 'a native multi-select', 'as values'], ['tree', 'a hierarchical menu', 'one p == v per level'],
  ['search', 'a text box', 'p.contains("x"), over one or more properties'], ['popular', 'named shortcuts with counts', 'each option\'s clause'], ['current', 'every pick as a removable chip, Clear all', '(removes)']]
  .map(([k, d, w]) => `<tr><td><code>${esc(k)}</code></td><td>${esc(d)}</td><td><code>${esc(w)}</code></td></tr>`).join('')}
</tbody></table></div>
<h2>The URL</h2>
<p>The rail's part of the filter stays readable in the address: <code>?brand=A,B</code>, <code>brand!=A</code> (exclude), <code>price=50..&lt;100</code> (a range, <code>&lt;</code> marking an exclusive end), <code>model~=ak</code> (search), <code>has=photo</code>. A clause no facet can draw stays as a custom filter, shown in the rail as "+N custom filters · Edit".</p>
<h2>Keyboard and phone</h2>
<p>Native controls or buttons with <code>aria-pressed</code>, each group labelled, the match count a polite live region. Under 700 px the rail is a closed disclosure above the view. The rail's right edge drags (<a href="resizable-panels.html">Resizable panels</a>).</p>
${from('docs/CONTRACT.md §7 and its 2026-10-26 amendment (filters)')}`;
    },
    frames: () => {
      const FRAMES = [['boxed', '1 px box', 'header band', 'the box\'s own', 'today\'s look; the default'], ['flush', 'none', 'none', 'the box\'s own', 'no border, rules only'],
        ['tabs', 'none', 'none', 'the box\'s own', 'tabs as the page\'s nav, zebra rows'], ['sheet', 'none', 'tinted header and well', 'the box\'s own', 'pill tabs, white tiles on the tint'],
        ['page', 'none', 'none', 'the page\'s', 'a sticky band; scrolls with the page'], ['bleed', 'none', 'tinted sticky band', 'the page\'s', 'edge to edge across the column']];
      return `<p class="lede">How a <code>&lt;data-views&gt;</code> sits in its page. Zach, on robotparts.dev: "I don't like how the table and gallery seem like separate components… caused by the additional border." One attribute, <code>frame</code>, and nothing changes unless a host sets it.</p>
<div class="dd-switch"><span class="muted">frame =</span><div class="segmented" role="group" aria-label="frame" data-switch="frames-demo" data-attr="frame" data-snippet="frames-code">${FRAMES.map(([f], i) => `<button type="button" data-value="${f}" aria-pressed="${i === 0}">${f}</button>`).join('')}</div></div>
${block({ id: 'frames-live', title: 'One element, six frames', desc: 'The GIM4305 datasheet case with its whole toolbar. Pick a frame above: the element re-makes its view on the new scroller and keeps its view, filters and search.', slug: 'gim4305-datasheet', view: 'Datasheet', toolbar: 'full', height: '520px', attrs: { frame: 'boxed', style: '--data-sticky-top: 57px' }, switchId: 'frames-demo' })}
${file('index.html', '<data-views src="views.base" frame="boxed"></data-views>', '', 'frames-code')}
<h2>The six frames</h2>
<div class="tablewrap"><table class="plain-table"><thead><tr><th><code>frame</code></th><th>Border</th><th>Surface</th><th>Scrolls</th><th>Looks like</th></tr></thead><tbody>
${FRAMES.map(([f, b, s, sc, l]) => `<tr><td><code>${f}</code></td><td>${esc(b)}</td><td>${esc(s)}</td><td>${esc(sc)}</td><td>${esc(l)}</td></tr>`).join('')}
</tbody></table></div>
<h2><code>page</code> and <code>bleed</code> scroll with the page</h2>
<p>The element is as tall as its rows and the nearest scrolling ancestor (else the window) scrolls them. The band (tabs, toolbar, count) sticks to the top, the table's header sticks under it, a wide table's sideways scrollbar is pinned to the bottom, and the side peek is pinned to the visible box. Two optional host tokens: <code>--data-sticky-top</code> (the height of a host's own sticky header; this site sets 57 px) and <code>--data-bleed</code> (the side padding <code>bleed</code> reaches across).</p>
${from('docs/CONTRACT.md §12 (frame)')}`;
    },
    'open-modes': () => `<p class="lede">What touching a record does is one setting per view, with three modes: <b>expand</b> a band under the row, open the <b>side</b> peek, or <b>link</b> to the record's page. Like Notion's per-view "Open pages in", because one forced peek mode backfires (Atlassian had to add an opt-out to its preview panel).</p>
<div class="dd-switch"><span class="muted">open =</span><div class="segmented" role="group" aria-label="open" data-switch="open-demo" data-attr="open" data-snippet="open-code">${['side', 'expand', 'link'].map((m, i) => `<button type="button" data-value="${m}" aria-pressed="${i === 0}">${m}</button>`).join('')}</div></div>
${block({ id: 'open-live', title: 'Click a row', desc: 'robotparts\' actuators. <b>side</b>: a click opens the peek, ↑/↓ step through the rows, Escape closes. <b>expand</b>: a band with the photo and the key specs opens under the row, several at once. <b>link</b>: the whole row goes to the part\'s page on robotparts.dev.', slug: 'robotparts-actuators', view: 'All, flat', height: '520px', attrs: { open: 'side' }, switchId: 'open-demo' })}
${file('index.html', '<data-views src="views.base" open="side"></data-views>', '', 'open-code')}
<h2>Write it</h2>
${file('views.base', `open: side                          # the file's default for every view
views:
  - type: table
    name: Expand in place
    open: expand                    # this view's own mode
  - type: table
    name: Row links
    open: { mode: link, url: url }  # the page URL is the url property
  - type: cards
    name: Gallery
    open: { mode: side, splitAt: 1100 }`)}
<p>The view's key wins over the attribute, which wins over the file's top level; with nothing set it is <code>{mode: side, splitAt: 1100}</code>. The page URL is <code>open.url</code>, else the dataset's <code>linkProperty</code>. No URL, no drill-down: no title link and no "Open page".</p>
<h2>Every mode</h2>
<ul class="rules">
  <li><b>A real link underneath.</b> With a URL the title cell is a real <code>&lt;a href&gt;</code>: ⌘/Ctrl/middle click opens a tab, as it should. A double-click or Enter opens the page.</li>
  <li><b>side is responsive.</b> At least <code>splitAt</code> px wide, the pane docks on the right and the list narrows beside it; narrower, it overlays; on a phone it is full screen with ‹ Back.</li>
  <li><b>The peek is in the URL.</b> <code>#peek=&lt;id&gt;</code> is pushed when it opens, so Back closes it and a shared link reopens it.</li>
  <li><b>Keyboard.</b> ↑/↓ or j/k step to the next record with the pane open; Space opens the peek, toggles a band, or ticks the row in link mode; Escape closes.</li>
</ul>
${from('docs/CONTRACT.md §13 (open modes) and docs/peps/0003-open-modes.md')}`,
    'resizable-panels': () => `<p class="lede">Every side panel is resizable by dragging, on by default: the kit's own side peek and rail, and any panel of the host's that says <code>data-resizable</code>. The width is remembered, a double-click resets it, and ← / → move the focused edge 16 px. The sidebar on this page is one: drag its right edge.</p>
${block({ id: 'resize-live', title: 'A rail and a peek, both resizable', desc: 'Drag the line right of the rail. Click a run to open the peek, then drag its left edge. Both widths are stored per panel and come back on reload.', slug: 'ml-experiments', view: 'Runs', rail: true, height: '520px' })}
<h2>A host's own panel</h2>
<p>Put <code>data-resizable="left|right"</code> (the edge the handle sits on) on any element. The kit writes the width as <code>--data-panel-width</code> on the panel, only once one is set, so your CSS keeps the layout:</p>
${file('index.html', `<nav class="side" id="side" data-resizable="right"
     data-resizable-min="180" data-resizable-max="420">…</nav>

<style>
  .layout { display: grid; grid-template-columns: auto minmax(0, 1fr); }
  .side { width: var(--data-panel-width, 240px); }
</style>
<script type="module" src="/vendor/data-ui/resize.js"></script>`)}
<p><code>data-ui.js</code> gives every such element its handle when it loads; a page that loads nothing else of the kit loads <code>dist/resize.js</code> (about 5 KB, its stylesheet inside). From script: <code>makeResizable(el, {edge, min, max, keep, key, label})</code> returns <code>{handle, width, set(px), reset(), destroy()}</code>. See it alone on <a href="${rel}plain/resize.html">a plain page</a>.</p>
<h2>The kit's panels</h2>
<ul class="rules">
  <li><b>The side peek:</b> a handle on its left edge, 320 to 1200 px, stored under <code>data-ui/panel-width/peek:&lt;views id&gt;</code>.</li>
  <li><b>The rail:</b> a handle on its right edge, 180 to 560 px, under <code>…/rail:&lt;views id&gt;</code>.</li>
  <li><b>Opting out:</b> <code>data-resizable="off"</code> on the element or any ancestor.</li>
  <li><b>On a phone</b> the handle hides when the panel fills its parent, so it never widens the page sideways.</li>
</ul>
${from('docs/CONTRACT.md §11 (resizable side panels)')}`,
    'explain-the-data': () => `<p class="lede">Zach, on the actuator-models views: "with data-ui as the base it's really about making these dashboards that really explain the data." A view can open with its answer and make its numbers readable, without a second page.</p>
${block({ id: 'explain-live', title: 'Every model on every bench', desc: 'The whole robotparts-models case with its toolbar and rail. The pivot opens with its question, a strip of KPI cards and how to read it; its models are rolled up across actuators. Open <b>Roll up</b> to bring the actuators back, or switch tabs for column groups and sub-columns.', slug: 'robotparts-models', view: 'Benches', toolbar: 'full', rail: true, height: '680px' })}
<h2>The keys</h2>
<ul class="rules">
  <li><b><code>intro: {text, kpi}</code></b> on any view: <code>text</code> is markdown (headings, lists, code, tables, links); <code>kpi</code> is an inline <code>type: kpi</code> entry over the same data and rail filter. Drawn above the status line.</li>
  <li><b><code>rollup: {keep, agg, dims}</code></b> on a table or pivot: one row per combination of the kept dimensions, the rest aggregated. A number becomes a cell with its median (or <code>agg</code>: mean, min, max, count, spread, sum), its range and its count; text that disagrees reads "N values", never a made-up value. Click a rolled row for the rows behind it.</li>
  <li><b><code>columnGroups: {label: [properties]}</code></b> on a table: a header over its columns. A pivot's column groups draw the same way.</li>
  <li><b>Displays</b> (<code>display: {p: …}</code>): <code>stats</code> splits a property into sub-columns (median, min, max, n, runs; or value, low, high, basis); <code>range</code> puts low–high beside the value; <code>value</code> shows the basis mark with the range on hover; <code>dist</code> draws every value on one scale down the column, ends in the header; <code>markdown</code> renders text as a document in the peek.</li>
  <li><b>Fixed slots.</b> A number cell is <code>[number][range][mark][count]</code> with the column's slot widths, so digits and marks line up down a column whatever the value.</li>
  <li><b><code>Spread</code></b> (max − min) joins Bases' summaries, and lowercase names (<code>median</code>, <code>mean</code>, …) work wherever a summary does.</li>
</ul>
${file('gallery/robotparts-models/views.base · “Benches”', viewEntryText(caseOf('robotparts-models').baseText, 'Benches'), `${rel}gallery/robotparts-models/views.base`)}
${from('docs/CONTRACT.md §16 (explain the data)')}`,
    'time-groups-and-peek-trail': () => `<p class="lede">Two things that make time and relations first-class: a group level can bucket dates, and the side peek keeps the trail of records you followed from inside it.</p>
<h2>Time groups</h2>
<p>A group level (<code>groupBy</code>, <code>subGroupBy</code>, in every view and the pivot) may carry <code>by: day | week | month | quarter | year</code> and <code>gaps: true</code>. A time level is always in time order (newest first with <code>direction: DESC</code>); empty buckets are left out unless <code>gaps: true</code>. The Group menu offers "Dates by: each date | day | week (from Monday) | month | quarter | year" on a date property, and the button reads "Group: Started by week".</p>
${block({ id: 'tg-live', title: 'Runs by week', desc: 'With the whole toolbar: open <b>Group</b> and change the grain to month or quarter.', slug: 'ml-experiments', view: 'Runs by week', toolbar: 'full', height: '480px' })}
<ul class="rules">
  <li><b>The date is the one written.</b> <code>2026-09-30T23:30:00-07:00</code> is 30 Sep (1 Oct in UTC); it is never converted to the viewer's zone. A value that is not an ISO date falls in "No &lt;property&gt;", last.</li>
  <li><b>A chart's date channel</b> takes the same <code>by:</code> (<a href="${rel}views/index.html#ts-axis">see it live</a>).</li>
  <li><b>Both checkers</b> know it: <code>by: weekly</code> is an error, "did you mean 'week'?"</li>
</ul>
<h2>The peek's trail</h2>
<p>A relation is declared, never guessed: a column marked <code>relation: true</code>, or a property a view names as a graph's <code>edges.property</code> or a <code>tree.parent</code>. In the peek its values are links to those records; a click opens the record in the same peek and adds it to the trail (<code>Supply › Regen clamp › XT30 junction</code>). Every crumb before the current one jumps back. Escape and ‹ Back step back one record before they close the peek; ⤢ opens the record's own page when it has one.</p>
${block({ id: 'trail-live', title: 'Follow the wiring', desc: 'The rack\'s parts. Open a part, then click a name under "Wires to": the trail grows above the title.', slug: 'rack-wiring', view: 'Parts', height: '480px' })}
<p>In the URL the trail is <code>#peek=&lt;current&gt;&amp;trail=&lt;first&gt;&amp;trail=&lt;second&gt;</code>, replaced on every step, so a reload or a shared link reopens the same record with the same trail. (The demos on this page are <code>no-url</code>, so they leave the address alone.)</p>
${from('docs/CONTRACT.md §14 (time groups and peek trail)')}`,
    performance: () => {
      const scen = readFileSync(join(root, 'bench', 'README.md'), 'utf8').split('\n').filter((l) => /^\| `/.test(l)).map((l) => l.split(' | ').map((c) => c.replace(/^\|\s*|\s*\|$/g, '').trim()));
      return `<p class="lede">Zach: "It's important we are writing code that is fast, particularly as you are loading the data." <code>npm run bench</code> loads data-ui on real data from Zach's apps in headless Chromium, drives real input, and times it from the browser's own clock, never data-ui's word.</p>
<div class="callout"><p><b>Where the numbers are.</b> <code>bench/publish.py</code> writes each run to the <code>data-ui</code> producer in Vibe Tracks, which draws every KPI against its budget, per scenario and per host, with a noisy machine's points hollow. Vibe Tracks has no public page yet, so this page shows what is measured and the budgets, not the numbers.</p></div>
${docBlockCatalog()}
<h2>The rules every KPI follows</h2>
<ul class="rules">
  <li><b>Lower is better</b>, for all of them; each is a p95 over its runs unless it says otherwise.</li>
  <li><b>"Painted" means the frame after the work</b>: the bench waits for the next presented frame, not for data-ui's render event.</li>
  <li><b>Cold and warm:</b> a new browser context (empty cache) and the same page reloaded.</li>
  <li><b>Trust:</b> the machine is shared, so each scenario records the load and a calibration loop; a noisy point is published and drawn hollow, never hidden.</li>
  <li><b>FAILED, never fast:</b> a scenario with a page error, a fallback view or a missing rail publishes no numbers at all (the gate <code>no_page_errors</code>).</li>
</ul>
<h2>The scenarios</h2>
<div class="tablewrap"><table class="plain-table"><thead><tr><th>Scenario</th><th>App</th><th>Rows</th><th>Views</th><th>What it stresses</th></tr></thead><tbody>
${scen.map(([id, app, rows, views, what]) => `<tr><td><code>${esc(id.replace(/`/g, ''))}</code></td><td>${esc(app)}</td><td>${esc(rows)}</td><td>${esc(views)}</td><td>${esc(what.replace(/\*\*/g, ''))}</td></tr>`).join('')}
</tbody></table></div>
<h2>Run it</h2>
${file('terminal', `npm --prefix ~/data-ui run bench
npm --prefix ~/data-ui run bench -- --scenario robotparts-actuators --runs 3
python3 ~/data-ui/bench/publish.py --to ~/vt/zach/producers/data-ui --event "after X"`)}
<p>data-ui also leaves its own marks in the browser's timeline, so DevTools' Performance panel shows them: <code>data-ui:data</code>, <code>data-ui:start</code>, <code>data-ui:first-render</code>, and the measures <code>data-ui:model</code>, <code>data-ui:render</code>, <code>data-ui:rail</code>.</p>
${from('bench/KPIS.md, bench/kpi_catalog.json and bench/README.md')}`;
    },
    'toolbar-presets': () => {
      // WHY these four (docs/CONTRACT.md §15 note "promote"): the mix is Zach's pick ("Definitely yes I like the mix"),
      // and each app's difference is a preset of the same attributes, never a second bar
      const PRESETS = [
        ['mix', 'Mix (default)', { views: 'auto', promote: null }, 'the views decide (<code>auto</code>): tabs, the ones that do not fit in "N more…"; with <code>filters</code> set, only Filter is promoted'],
        ['shopify', 'Shopify', { views: 'dropdown', promote: '' }, 'three elements: the view chip, the search, Display'],
        ['notion', 'Notion', { views: 'tabs', promote: '' }, 'the view tabs (overflow into "N more…"), the search, Display'],
        ['obsidian', 'Obsidian', { views: 'dropdown', promote: 'sort group filter properties' }, 'the chip, then Sort · Group · Filter · Properties as words that say what is set'],
      ];
      const fixed = { filters: 'pills', display: 'panel', selectable: '' };
      const html = (set) => `<data-views src="views.base" toolbar="bar"${Object.entries({ ...set, ...fixed }).filter(([, v]) => v !== null).map(([k, v]) => (k === 'selectable' ? ' selectable' : ` ${k}="${v}"`)).join('')}></data-views>`;
      const attrsOfSet = (set) => Object.fromEntries(Object.entries(set).filter(([, v]) => v !== null));
      return `<p class="lede">The one-row bar: the view selector, a query bar, Filter and Display, with everything else inside Display. Zach's pick was the mix of the proposals ("Definitely yes I like the mix"), with the differences between apps kept as presets: each preset is two attributes on the same element.</p>
<div class="dd-switch"><span class="muted">preset =</span><div class="segmented" role="group" aria-label="Toolbar preset" data-preset="toolbar-demo" data-snippet="toolbar-code">${PRESETS.map(([k, label, set], i) => `<button type="button" data-value="${k}" data-set="${esc(JSON.stringify(set))}" data-html="${esc(html(set))}" aria-pressed="${i === 0}">${esc(label)}</button>`).join('')}</div></div>
${block({ id: 'toolbar-live', title: 'The bar and its presets', code: 'toolbar="bar"', desc: 'robotparts\' 1,149 actuators under <code>toolbar="bar"</code>. Pick a preset above: the element redraws its bar and keeps its view, its filters, its query and its selection. Type <code>brand:</code> in the query bar, tick a few rows, open Display.', slug: 'toolbar-bar', view: 'Rows', toolbar: 'bar', height: '520px', attrs: { ...attrsOfSet(PRESETS[0][2]), ...fixed }, switchId: 'toolbar-demo', slot: 'toolbar-presets', foot: 'every attribute is read live (CONTRACT §15)' })}
${file('index.html', html(PRESETS[0][2]), '', 'toolbar-code')}
<h2>The presets</h2>
<div class="tablewrap"><table class="plain-table"><thead><tr><th>Preset</th><th>Attributes</th><th>On the bar</th></tr></thead><tbody>
${PRESETS.map(([, label, set, what]) => `<tr><td><b>${esc(label)}</b></td><td><code>${esc(['toolbar="bar"', ...Object.entries(set).map(([k, v]) => (v === null ? '' : `${k}="${v}"`)).filter(Boolean)].join(' '))}</code></td><td>${what}</td></tr>`).join('')}
</tbody></table></div>
<p>The gallery has each one as its own example, with the rest of the bar's attributes: <a href="${rel}gallery/toolbar-bar/index.html">the mix</a> (<code>filters="pills rail"</code>: the one Filter button shows and hides the rail), <a href="${rel}gallery/toolbar-shopify/index.html">Shopify</a> (<code>display="popover"</code>), <a href="${rel}gallery/toolbar-notion/index.html">Notion</a> and <a href="${rel}gallery/toolbar-obsidian/index.html">Obsidian</a>.</p>
<h2>The attributes</h2>
<div class="tablewrap"><table class="plain-table"><thead><tr><th>Attribute</th><th>Values (default first)</th><th>Does</th></tr></thead><tbody>
${[['toolbar', 'full | bar | compact | none', '<code>bar</code> is the one-row chrome; <code>full</code> stays the default and draws what it drew.'],
  ['views', 'auto | dropdown | tabs', 'The view selector: one chip with Bases\' view menu, every view as a tab, or tabs while they fit (re-decided on resize).'],
  ['promote', 'a set of sort group filter properties', 'Which of Display\'s sections also sit on the bar, in that order; <code>""</code> promotes none. Absent: <code>filters="expanded"</code> promotes all four, any other <code>filters</code> promotes Filter, else the views decide (tabs ⇒ Filter, the chip ⇒ all four).'],
  ['filters', 'pills, expanded, query-tokens, rail', 'How the one all-views filter shows: removable pills under the bar, tokens in the query bar, a Filter button that shows and hides the linked rail.'],
  ['display', 'panel | popover', 'Where View settings opens: a resizable side panel inside the element, or a popover on the button.'],
  ['selectable', 'absent | present', 'A checkbox per row (shift-click a range, ctrl/cmd-click one); the bulk band lies over the header with "N selected", the actions and Show only selected.'],
  ['labels', 'auto | icons', '<code>auto</code> drops the tools\' labels first as the bar narrows, before anything moves into "…".'],
  ['query', 'text', 'The query bar\'s text, parsed as typing is; read back <code>el.queryText</code>.']]
  .map(([a, v, d]) => `<tr><td><code>${a}</code></td><td><code>${esc(v)}</code></td><td>${d}</td></tr>`).join('')}
</tbody></table></div>
<h2>How it behaves</h2>
<ul class="rules">
  <li><b>One row, always.</b> As the bar narrows, labels drop to icons, controls move into "…", the search folds to an icon and the tabs fold to the chip, in that order. The view selector and Display never leave the row.</li>
  <li><b>The query bar.</b> <code>/</code> focuses it. <code>brand:steadywin</code>, <code>-form:servo</code>, <code>peak_torque:&gt;10</code>, <code>price:50..150</code>, <code>has:photo</code> and any Bases expression in parentheses become filter clauses, the same ones the rail writes; other words are a free-text search. It suggests properties, operators and values with their counts.</li>
  <li><b>Selection and bulk actions.</b> <code>selectable</code> adds a checkbox per row; the bulk band shows "N selected", the actions (compare, copy ids, export CSV, the host's own through <code>el.actions</code>) and "Show only selected".</li>
  <li><b>Display holds everything:</b> layout, frame, property visibility, filter, sort, group and roll up; a promoted control is the same control, never a second one.</li>
</ul>
${from('docs/CONTRACT.md §15 and its notes, and docs/peps/0002-toolbar.md')}`;
    },
    'embedded-chrome': () => `<p class="lede">When one view is a part of your own page (a KPI head, a history strip beside your own words), the kit's status line ("119 of 119 rows · 9 groups") and a view's own control bar are noise. Two attributes turn them off, first-class, so no host reaches into the kit's class names. Zach, on Vibe Tracks hiding them with its own CSS: "can you please provide first class support for this so we don't need to do hacky css".</p>
<div class="dd-switch"><span class="muted">status =</span><div class="segmented" role="group" aria-label="status" data-switch="chrome-demo" data-attr="status" data-snippet="chrome-code">${['on', 'off'].map((v, i) => `<button type="button" data-value="${v}" aria-pressed="${i === 0}">${v}</button>`).join('')}</div>
<span class="muted">controls =</span><div class="segmented" role="group" aria-label="controls" data-switch="chrome-demo" data-attr="controls" data-snippet="chrome-code">${['on', 'off'].map((v, i) => `<button type="button" data-value="${v}" aria-pressed="${i === 0}">${v}</button>`).join('')}</div></div>
${block({ id: 'chrome-live', title: 'A chart, with and without its chrome', code: 'status · controls', desc: 'The Ashby chart of robotparts\' actuators with no toolbar. <b>status</b> is the line under the view; <b>controls</b> is the chart\'s own Encode / Rows bar. Turned off, each takes no space: the plot keeps its height and the bar\'s goes back to the page.', slug: 'actuator-charts', view: 'Ashby · torque vs mass', height: '460px', attrs: { status: 'on', controls: 'on' }, switchId: 'chrome-demo' })}
${file('index.html', '<data-views src="views.base" view="Ashby · torque vs mass" toolbar="none" status="on" controls="on"></data-views>', '', 'chrome-code')}
<h2>Where it is said</h2>
<ul class="rules">
  <li><b>Per key, first wins:</b> the view's entry in the <code>.base</code> (<code>status: false</code>, <code>controls: false</code>; a boolean, or <code>on | off | show | hide | none</code>), then the attribute on <code>&lt;data-views&gt;</code> (<code>status="off"</code>, <code>controls="off"</code>), then the default, on. Both attributes are observed: a change applies at once.</li>
  <li><b>status</b> is the status line: the row count, a view's own <code>setStatus</code> text, a filter error. Off, it is hidden under every <code>frame=</code>.</li>
  <li><b>controls</b> is the view's own control bar inside its slot (today the chart's Encode / Rows bar and its popover). A view type with no bar draws as before.</li>
  <li><b>Read back:</b> <code>el.chrome()</code> → <code>{status, controls}</code>; the element mirrors them as <code>data-status</code> and <code>data-controls</code>.</li>
  <li><b>Not touched:</b> <code>toolbar=</code> keeps its meaning. A bare part is <code>toolbar="none" status="off" controls="off"</code>; the side peek, the rail and the intro are not chrome here.</li>
</ul>
${file('views.base', `views:
  - type: chart
    name: History strip
    status: false        # no "N of N rows" under it
    controls: false      # no Encode / Rows bar
    chart: { mark: line, encoding: { x: { field: t }, y: { field: value } } }`)}
${from('docs/CONTRACT.md §18 (embedded chrome)')}`,
    'value-sources': () => `<p class="lede">Any value on the page should answer "where does this come from?" with a right-click, and the same for a photo or a file. Load <code>sources.js</code> beside the kit and every value with a source gets the popover: its basis, the source and its page, when it was read, the record, and a citation to copy. This page loads it.</p>
${block({ id: 'sources-live', title: 'Right-click a torque or a mass', code: 'sources.js', desc: 'robotparts\' actuators: every peak torque and mass is a rich cell, <code>{value, basis, source}</code>, read from a seller\'s or a maker\'s listing. Right-click one (long-press on a phone, or focus it and press Shift+F10). Shift + right-click gives the browser\'s own menu; a value with no source always does.', slug: 'robotparts-actuators', view: 'By brand', height: '460px' })}
${file('index.html', `<script type="module" src="/vendor/data-ui/data-ui.js"></script>
<script type="module" src="/vendor/data-ui/sources.js"></script>

<data-views src="views.base"></data-views>
<img src="motor.webp" alt="…" data-provenance='{"source": "aifitlab.com", "sourceUrl": "https://…", "asOf": "2026-10-22"}'>`)}
<h2>What carries a source</h2>
<ul class="rules">
  <li><b>A rich cell</b> <code>{value, unit, basis, source, sourceUrl, sourcePage, asOf, record, note}</code>: <code>sourceUrl</code> is the page the value was read from, <code>sourcePage</code> the host's own page about that source, <code>record</code> a record or field id. The kit writes them as one <code>data-provenance</code> attribute on the value (on the <code>&lt;td&gt;</code> for the table's number cells), only when the cell has any of them.</li>
  <li><b><code>&lt;data-value&gt;</code></b> reads them as attributes: <code>source</code>, <code>source-url</code>, <code>source-page</code>, <code>as-of</code>, <code>record</code>, <code>note</code>.</li>
  <li><b>Anything of yours</b> (an <code>&lt;img&gt;</code>, an <code>&lt;a&gt;</code>, a <code>&lt;figure&gt;</code>) says <code>data-provenance='{…}'</code>: that is how photos and files get their sources. See them on <a href="${rel}plain/sources.html">a plain page</a>.</li>
</ul>
<h2>The popover</h2>
<ul class="rules">
  <li><b>Opens</b> on a right-click on or inside an element with provenance, on a touch or pen press held 550 ms, and on the ContextMenu key or Shift+F10 for the focused element. Shift + right-click always gives the browser's menu.</li>
  <li><b>Shows</b> the value and unit, its basis (Stated, Measured or Derived, with its mark), then Source, URL, Accessed ("N days ago"), Record and Note, each only when there is one; the actions Open URL ↗, Source page and Copy citation.</li>
  <li><b>Closes</b> on Escape (focus goes back), a click outside, a scroll or a resize. One is open at a time; arrows and Tab move between its actions. It stays inside the viewport, full width less 16 px gutters on a phone.</li>
  <li><b>For hosts:</b> <code>attachSourcesMenu(root, {resolve})</code> supplies provenance for elements without the attribute; opening fires a bubbling <code>data-sources-open</code> event with the provenance; <code>&lt;html data-sources-menu="off"&gt;</code> turns it off.</li>
</ul>
${from('docs/CONTRACT.md §22 (sources of a value)')}`,
    'add-to-dashboard': () => `<p class="lede">Dashboards are built with data-ui: an agent writes them, people curate them. From any view of the data, ⋯ › <b>Add to dashboard…</b> lists the dashboards your page offers, like adding an item to a saved list, and the view goes to the <b>bottom</b> of the one you pick, to be arranged later. A legend's series and a KPI card have it too, on a right-click.</p>
${block({ id: 'add-live', title: 'Add this view to a dashboard', code: '⋯ › Add to dashboard…', desc: 'robotparts\' actuators with the full toolbar. Filter or sort it, then ⋯ › Add to dashboard… › New dashboard…: this page offers no dashboards and saves nothing, so the new dashboard\'s <code>.base</code> text goes to your clipboard. A page that saves (below) lists its dashboards here and writes the file.', slug: 'robotparts-actuators', view: 'By brand', height: '460px', toolbar: 'full' })}
<h2>Where it is</h2>
<ul class="rules">
  <li><b>Every view:</b> the ⋯ menu (and View settings under <code>toolbar="bar"</code>); every dashboard panel's own ⋯ at its top right.</li>
  <li><b>One series:</b> right-click (or long-press) a legend entry: <i>Show only</i>, or <i>Add “J2” to dashboard…</i>, which adds the view with every other series hidden.</li>
  <li><b>One value:</b> right-click a KPI card (the view narrowed to that card) or a field in the record peek (a card or a record of that one value).</li>
  <li><b>What you see is what is added:</b> the view with your sort and grouping, and a <code>filters:</code> that keeps exactly the rows you see: the rail, the query, the words searched, another panel's selection. With <i>At this moment</i>, the panel stands at the clock's instant.</li>
</ul>
<h2>What the file gets</h2>
<ul class="rules">
  <li><b>Only new lines:</b> the dataset (if the dashboard has no dataset on that file yet), the view and the panel, last in <code>layout.panels</code>, full width. Every comment, blank line and block stays as it was.</li>
  <li><b>No duplicates:</b> a dataset is found by its file; a name already taken gets a suffix (<code>samples_2</code>, <code>Runs (2)</code>).</li>
  <li><b>Arrange</b> moves it like any other panel.</li>
</ul>
${file('views.base · the panel added at the bottom', `views:
  …
  - type: timeseries
    name: Error by joint · J2
    from: samples_2
    timeseries: { x: t, y: err_mm, series: joint }
    hiddenSeries: [J1, J3]    # the series added; the others start hidden

layout:
  panels:
    …
    - { view: Error by joint · J2, t: 1.2 }   # "At this moment": pinned at t = 1.2 s`)}
<h2>Your page saves it</h2>
<p>data-ui never writes a file. Your page lists its dashboards and saves the text it is handed; with no listener the text goes to the clipboard.</p>
${file('index.html', `<script type="module">
  document.documentElement.dashboards = async () => [
    { id: 'fleet', title: 'Fleet overview', url: '/dashboards/fleet.base' },
  ];
  document.addEventListener('data-add-to-dashboard', (e) => {
    const { dashboard, text } = e.detail;   // text: the .base with the panel at the bottom
    e.detail.respondWith(fetch('/api/save', { method: 'POST', body: JSON.stringify({ id: dashboard.id, title: dashboard.title, text }) })
      .then((r) => (r.ok ? { ok: true } : { ok: false, reason: r.statusText })));
  });
</script>`)}
${from('docs/CONTRACT.md §34 (Add to dashboard)')}`,
    'rerun-interop': () => `<p class="lede">Rerun is the backdoor for robotics data that wants a real 3D and time-series viewer. A dashboard names a recording written from its own datasets; its "Open in Rerun" menu hands it over.</p>
${pending({ id: 'rerun-live', slot: 'rerun-interop', title: 'Open in Rerun', kind: 'cards', desc: '<code>rerun:</code> names a <code>.rrd</code> file written at build time from the same datasets by <code>tools/rerun_export.py</code>, with a blueprint that mirrors the layout. rerun-sdk is a <code>uv run</code> extra, never a runtime dependency of the kit. The menu offers three things: open the file in Rerun\'s hosted viewer, copy the native command, or download the file.', body: file('the menu\'s two links', `https://app.rerun.io/version/0.40.0/index.html?url=<absolute rrd URL>
uvx --from rerun-sdk==0.40.0 rerun <rrd URL>`), snippet: `rerun:
  rrd: rerun/dashboard-cards.rrd
  sdk: 0.40.0`, label: 'gallery/dashboard-cards/views.base · rerun: (planned syntax)' })}
<p>The <code>.rrd</code> is generated, never hand-edited. Opening the hosted viewer loads Rerun's own page from app.rerun.io, the one place a dashboard reaches another site, and only when the reader asks.</p>
${from('docs/peps/0005-dashboard-cards.md §6 on lane/dashboard-cards (not on main yet)')}`,
  };

  // the Performance page's KPI catalog, as data-ui draws it: bench/kpi_catalog.json turned into rows and a .base file
  const catalog = JSON.parse(readFileSync(join(root, 'bench', 'kpi_catalog.json'), 'utf8'));
  mkdirSync(join(out, 'docs'), { recursive: true });
  const kpiRows = catalog.kpis.map((k) => ({
    id: k.id, title: k.title, level: `L${k.level}`, parent: k.parent || null,
    target: k.target == null ? { value: null, why: 'diagnostic: no budget' } : { value: k.target, unit: k.unit },
    unit: k.unit, description: k.description, formula: k.formula,
  }));
  writeFileSync(join(out, 'docs', 'kpis.json'), JSON.stringify({ id: 'data-ui-bench-kpis', title: catalog.title, titleProperty: 'title', rows: kpiRows }, null, 1));
  const KPI_BASE = `# data-ui's speed KPIs: bench/kpi_catalog.json as rows (site/docs-pages.mjs writes kpis.json at build time)
data: kpis.json
properties:
  title: { displayName: KPI }
  level: { displayName: Level }
  target: { displayName: Budget }
  description: { displayName: What }
  formula: { displayName: Formula }
views:
  - type: table
    name: KPIs
    order: [title, level, target, description]
    tree: { parent: parent }
    columnSize: { title: 260, description: 560 }`;
  writeFileSync(join(out, 'docs', 'kpis.base'), KPI_BASE + '\n');
  function docBlockCatalog() {
    return `<section class="dd-block" id="kpi-catalog" aria-labelledby="kpi-catalog-h">
  <div class="dd-head"><h3 id="kpi-catalog-h">The KPIs and their budgets</h3>${badge('live')}</div>
  <p class="dd-desc">The catalog the bench publishes against, drawn by data-ui itself: a table with <code>tree: {parent}</code>, so each diagnostic sits under the KPI it explains. Click a KPI for its formula.</p>
  <div class="dd-tabs" role="tablist" aria-label="KPI catalog"><button type="button" role="tab" id="kpi-tp" aria-controls="kpi-p" aria-selected="true">Preview</button><button type="button" role="tab" id="kpi-tc" aria-controls="kpi-c" aria-selected="false" tabindex="-1">Code</button></div>
  <div class="dd-tabpanel" id="kpi-p" role="tabpanel" aria-labelledby="kpi-tp"><div class="dd-preview" data-id="demo-kpis" data-src="kpis.base" data-view="KPIs" data-type="table" data-toolbar="none" data-label="data-ui speed KPIs" style="--demo-height:520px"><div class="demo" style="--demo-height:520px"></div><p class="dd-wait muted">The live view starts when it scrolls into sight.</p></div></div>
  <div class="dd-tabpanel" id="kpi-c" role="tabpanel" aria-labelledby="kpi-tc" hidden>${file('kpis.base', KPI_BASE, 'kpis.base')}</div>
  <p class="dd-foot">From <code>bench/kpi_catalog.json</code> (Vibe Tracks' <code>vt-kpi-catalog/1</code>), ${catalog.kpis.length} KPIs and the gate <code>${esc(catalog.gates.map((g) => g.id).join(', '))}</code></p>
</section>`;
  }

  for (const d of DOCS) {
    docsPage({ path: `docs/${d.slug}.html`, title: d.title, nav: '', extraHead: d.head || '', description: d.line.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>'),
      body: `<p class="crumbs"><a href="index.html">How it works</a> › ${esc(d.title)}</p>
<div class="title-row"><h1>${esc(d.title)}</h1>${d.kind ? badge(d.kind) : ''}</div>
${DOC_BODIES[d.slug]()}` });
  }
  docsPage({
    path: 'docs/index.html', title: 'How it works', nav: '', description: 'How data-ui works, one short page per idea.',
    body: `<p class="crumbs">How it works</p>
<h1>How it works</h1>
<p class="lede">How data-ui works, one short page per idea: what it is, a live example where one exists on main, the <code>.base</code> or HTML you write, and the part of the contract it comes from.</p>
<div class="doc-cards">${DOCS.map((d) => `<a class="doc-card" href="${d.slug}.html"><span class="doc-card-head"><b>${esc(d.title)}</b>${d.kind ? badge(d.kind) : ''}</span><span class="doc-card-line">${d.line}</span><span class="doc-card-from">${esc(d.from)}</span></a>`).join('')}</div>`,
  });
  return { demos: demoN };
}
