// The docs site: a landing page, a Gallery that lists gallery/examples/* (each rendered live, with its .base and its
// data beside it), and the Views, Dashboards and Docs pages (site/docs-pages.mjs). Called by build.mjs; writes dist/site/.
// WHY static pages from case folders: the gallery is the docs, the catalogue an agent copies for case n+1, and the
// test suite (docs/SPEC.md §13); a new case is a new folder, nothing else.
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseBase } from '../packages/core/src/base.js';
import { BASIS } from '../packages/core/src/format.js';
import { buildDocsPages, tiersHtml } from './docs-pages.mjs';
import { railPage } from './rail-page.mjs';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** dist/site/_headers: Cloudflare static assets' headers rules (developers.cloudflare.com/workers/static-assets/headers/;
 * the Worker is assets-only, so they apply). WHY: Open in Rerun's hosted viewer fetches a dashboard's .rrd from
 * data-ui.dev (docs/RERUN.md); tools/serve.mjs grants the same locally. */
export const SITE_HEADERS = `/*.rrd
  Access-Control-Allow-Origin: https://app.rerun.io
`;

/** The small Markdown the READMEs use: # headings, paragraphs, - lists, `code`, **bold**, [links](url). */
/** One line of that Markdown (`code`, **bold**, [links](url)), escaped. */
export const inline = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

export function markdown(text) {
  const out = [];
  let list = null, para = [];
  const flush = () => {
    if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; }
    if (list) { out.push(`<ul>${list.map((x) => `<li>${inline(x)}</li>`).join('')}</ul>`); list = null; }
  };
  for (const line of String(text).split('\n')) {
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { flush(); out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`); continue; }
    const li = /^\s*-\s+(.*)$/.exec(line);
    if (li) { if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; } (list = list || []).push(li[1]); continue; }
    if (!line.trim()) { flush(); continue; }
    if (list && /^\s+\S/.test(line)) { list[list.length - 1] += ' ' + line.trim(); continue; }
    para.push(line.trim());
  }
  flush();
  return out.join('\n');
}

/** A README's bullets by their bold key: "- **Replaces:** …" -> {Replaces: '…'} (continuation lines joined). */
export function bullets(readme) {
  const out = {};
  let key = null;
  for (const line of String(readme).split('\n')) {
    const m = /^-\s+\*\*([^*:]+):\*\*\s*(.*)$/.exec(line);
    if (m) { key = m[1].trim(); out[key] = m[2]; continue; }
    if (key && /^\s+\S/.test(line)) { out[key] += ' ' + line.trim(); continue; }
    key = null;
  }
  return out;
}

/** A README's use case: "- **Use case:** Robotics · Playback" -> {group: 'Robotics', sub: 'Playback', text}; null
 * when it names none. WHY a bullet of its own: a template belongs to what it is used for (PEP 0010 §6, "Examples → Use
 * case: Robotics → Playback"), across the apps that feed it and the view types it is built from. */
export function useCaseOf(b) {
  const text = String((b && b['Use case']) || '').trim();
  if (!text) return null;
  const [group, ...rest] = text.split(/\s+·\s+/);
  return { group: group.trim(), sub: rest.length ? rest.join(' · ').trim() : null, text };
}

// The gallery's app groups, in this order (a case names its app in its README: "- **App:** robotparts"), and the
// view types in docs/VIEWS.md's order
const APP_ORDER = ['robotparts', 'Vibe Tracks', 'dataclass viewer', 'SystemSketch', 'Money', 'design work'];
// Where each app's code lives (the Replaces table names paths inside these); design work is robotparts' design/ and reports/
const APP_REPO = { robotparts: '~/robotparts', 'Vibe Tracks': '~/vibetracks', 'dataclass viewer': '~/py_dataclass_viewer',
  SystemSketch: '~/systemsketch', Money: '~/money', 'design work': '~/robotparts' };
const TYPE_ORDER = ['table', 'pivot', 'list', 'cards', 'chart', 'kpi', 'kanban', 'calendar', 'timeline', 'map', 'graph', 'record', 'compare', 'source'];
// The Examples page's sections, Vega-Lite-style by view type (Zach, 2026-10-26). A case sits in one: its README's
// "- **Category:**", else the table below, else its first view's type. 3D and the rest show up when a case names them.
const CATEGORIES = ['Table', 'Pivot', 'Cards', 'Charts', 'Time series', 'Dashboards', 'Analyses', 'Maps', 'Graphs', '3D'];
const CATEGORY_OF_TYPE = { table: 'Table', list: 'Table', record: 'Table', compare: 'Table', pivot: 'Pivot', cards: 'Cards', kanban: 'Cards',
  chart: 'Charts', calendar: 'Time series', timeline: 'Time series', kpi: 'Dashboards', dashboard: 'Dashboards', map: 'Maps', graph: 'Graphs', scene3d: '3D' };
// cases whose first view undersells them: a model benchmark and an experiment tracker are analyses, a side-by-side is too
const CATEGORY_OF_CASE = { 'ml-experiments': 'Analyses', 'robotparts-compare': 'Analyses' };

/** Every gallery case: {slug, title, summary, readme, bullets, app, base, baseText, data, files, skin}. */
export function readExamples(root) {
  const dir = join(root, 'gallery', 'examples');
  return readdirSync(dir).filter((f) => existsSync(join(dir, f, 'views.base'))).sort().map((slug) => {
    const here = join(dir, slug);
    const readme = existsSync(join(here, 'README.md')) ? readFileSync(join(here, 'README.md'), 'utf8') : `# ${slug}\n`;
    const title = (/^#\s+(.*)$/m.exec(readme) || [null, slug])[1];
    const summary = readme.split('\n\n').map((p) => p.trim()).find((p) => p && !p.startsWith('#') && !p.startsWith('-')) || '';
    const baseText = readFileSync(join(here, 'views.base'), 'utf8');
    const base = parseBase(baseText);
    if (!base.data) throw new Error(`gallery/examples/${slug}/views.base needs a data: key naming its data file`);
    const files = readdirSync(here).filter((f) => statSync(join(here, f)).isFile());
    const dirs = readdirSync(here).filter((f) => f !== 'source' && !f.startsWith('.') && statSync(join(here, f)).isDirectory());
    // WHY site.json: page options that are not view config, e.g. {"editable": true} so a board drag lands on the site
    const site = files.includes('site.json') ? JSON.parse(readFileSync(join(here, 'site.json'), 'utf8')) : {};
    const b = bullets(readme);
    return { slug, here, title, summary, readme, bullets: b, app: (b.App || 'other').trim(), base, baseText, data: base.data, files, dirs, site, skin: files.includes('skin.css') };
  });
}

/** docs/VIEWS.md §1, the master table, as rows: {view, priority, selected, npm, ours, types, plain}. */
export function readViewsTable(root) {
  const md = readFileSync(join(root, 'docs', 'VIEWS.md'), 'utf8');
  const start = md.indexOf('| View | Priority |');
  const lines = md.slice(start).split('\n');
  const rows = [];
  for (const line of lines.slice(2)) {
    if (!line.startsWith('|')) break;
    const cells = line.split(' | ').map((c) => c.replace(/^\|\s*|\s*\|$/g, '').trim());
    const [view, priority, uses, , selected, why, ours, type] = cells;
    const sel = selected.split('<br>');
    rows.push({
      view: view.replace(/\*\*/g, ''), priority, uses, why, ours,
      selected: sel[0].replace(/\*\*/g, '').replace(/`/g, ''), npm: (sel[1] || '').replace(/`/g, ''),
      types: [...type.matchAll(/`([a-z]+):?`/g)].map((m) => m[1]),
      plain: !type.includes('+') && !type.includes('/'),
      typeCell: type.replace(/`/g, ''),
    });
  }
  return rows;
}

// The top nav: the three tiers (Views → Dashboards → Analyses), then the examples. [href, label, the `nav` a page passes]
// WHY a key beside the label: a page names its section by key, so a label can change without touching every page
const NAV = [['index.html', 'Overview', 'Overview'], ['views/index.html', 'Views', 'Views'], ['dashboards/index.html', 'Dashboards', 'Dashboards'],
  ['analyses/index.html', 'Analyses', 'Analyses'], ['gallery/index.html', 'Examples', 'Examples']];

function page({ title, rel, nav, body, description, head = '', script = '' }) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description || 'data-ui: one dataset, one .base file, many views.')}">
<link rel="stylesheet" href="${rel}kit/data-ui.css">
<link rel="stylesheet" href="${rel}site.css">${head}
<script>try { const t = localStorage.getItem('data-ui-site-theme'); if (t) document.documentElement.dataset.theme = t; } catch {}</script>
</head>
<body>
<header class="top">
  <a class="logo" href="${rel}index.html"><span class="mark" aria-hidden="true">▦</span> data-ui</a>
  <nav aria-label="Site">${NAV.map(([href, label, key]) => `<a href="${rel}${href}"${nav === key ? ' aria-current="page"' : ''}>${label}</a>`).join('')}</nav>
  <button class="theme" type="button" aria-label="Theme">Theme: system</button>
</header>
${body}
<footer class="foot"><p>data-ui is a kit, not an app: custom elements, the Obsidian Bases grammar and <code>--data-*</code> tokens. MIT. Everything on this site loads from this site.</p></footer>
<script type="module" src="${rel}site.js"></script>${script ? `\n<script type="module" src="${script}"></script>` : ''}
</body>
</html>
`;
}

// WHY site.json attrs (CONTRACT §15): a case shows the bar and its variants as the element's own attributes
// ({"attrs": {"toolbar": "bar", "views": "auto", "selectable": true}}); true writes a bare attribute
function attrsOf(ex) {
  const a = (ex.site && ex.site.attrs) || {};
  return Object.entries(a).filter(([, v]) => v !== false && v != null).map(([k, v]) => (v === true ? ` ${esc(k)}` : ` ${esc(k)}="${esc(String(v))}"`)).join('');
}

// WHY a noscript picture (lane/map, 2026-10-28): without JS a case page showed an empty box above its files; the
// capture of its first view (site/capture-thumbs.py, light and dark) says what the view draws, and the .base and the
// data below it stay readable text
function noscript(ex, rel) {
  const src = (theme) => `${rel}gallery/thumbs/${ex.slug}/0-${theme}-960.webp`;
  return `<noscript><picture class="noscript-shot"><source srcset="${src('dark')}" media="(prefers-color-scheme: dark)"><img src="${src('light')}" alt="${esc(ex.title)}: its first view, as captured (JavaScript is off; the .base file and the data are below)" loading="lazy"></picture></noscript>`;
}

function demo(ex, { id, rel, height = '560px', urlState = true, skin = ex.skin }) {
  // a case with site.json {"analyses": true} is a list of analyses (docs/peps/0007-analyses.md): its views.base is the
  // list's presets over the analyses' frontmatter rows, and each <slug>.md has its own page beside it
  if (ex.site && ex.site.analyses) return `<div class="demo demo-analyses${skin ? ' data-ui-skin' : ''}"><data-analyses id="${id}" base="${rel}gallery/${ex.slug}/views.base"${urlState ? '' : ' no-url'} aria-label="${esc(ex.title)}"></data-analyses></div>`;
  // a .base with layout: is a dashboard (docs/peps/0004-dashboards.md): one element, its rails and panels inside it
  if (ex.base.layout) return `<div class="demo demo-dashboard${skin ? ' data-ui-skin' : ''}"><data-dashboard id="${id}" src="${rel}gallery/${ex.slug}/views.base"${urlState ? '' : ' no-url'}${attrsOf(ex)} aria-label="${esc(ex.title)}"></data-dashboard></div>`;
  const facets = ex.base.facets && ex.base.facets.length;
  // a file with a top-level summary: (CONTRACT §43) gets its summary card above the views
  const summary = ex.base.summary && Array.isArray(ex.base.summary.cells) ? `<script type="module" src="${rel}kit/views/summary.js"></script><data-summary for="${id}" class="summary"></data-summary>` : '';
  return `<div class="demo${facets ? ' has-rail' : ''}${summary ? ' has-summary' : ''}${skin ? ' data-ui-skin' : ''}" style="--demo-height:${height}">
  ${facets ? `<data-facets for="${id}" class="rail"></data-facets>` : ''}${summary}
  <data-views id="${id}" src="${rel}gallery/${ex.slug}/views.base"${urlState ? '' : ' no-url'}${ex.site && ex.site.editable ? ' editable' : ''}${attrsOf(ex)} aria-label="${esc(ex.title)}"></data-views>
</div>`;
}

// The landing page's thirteen views: each a live thumbnail of one gallery case's preset
const THUMBS = [
  { type: 'table', label: 'Table', slug: 'robotparts-actuators', view: 'By brand', blurb: 'Two group levels with fold and summaries, bars in cells, units in the header.' },
  { type: 'pivot', label: 'Pivot', slug: 'models-benches', view: 'Benchmarks', blurb: 'Groups × split columns, one value per cell, the records behind it.' },
  { type: 'list', label: 'List and tree', slug: 'vibetracks-feature-tree', view: 'Spec tree', blurb: 'One line per row; with tree:, an outline that folds.' },
  { type: 'record', label: 'Record and form', slug: 'robotparts-compare', view: 'Part page', blurb: 'One row as a sheet in sections; edit: true makes it a form.' },
  { type: 'compare', label: 'Compare', slug: 'robotparts-compare', view: 'Side by side', blurb: 'Rows in columns, the better value marked, a photo slider.' },
  { type: 'cards', label: 'Cards and media grid', slug: 'robotparts-photos', view: 'Actuators', blurb: "Bases' cards, virtualised; lightbox: true opens a media grid." },
  { type: 'kanban', label: 'Kanban', slug: 'vibetracks-board', view: 'By status', blurb: 'Columns from groupBy; a drag proposes an edit, the host decides.' },
  { type: 'chart', label: 'Chart', slug: 'actuator-charts', view: 'Ashby · torque vs mass', blurb: 'Vega-Lite inside chart:, Show Me defaults, Ashby envelopes.' },
  { type: 'kpi', label: 'KPI', slug: 'vibetracks-kpis', view: 'KPIs', blurb: 'The number, its basis, a delta coloured by which way is better.' },
  { type: 'calendar', label: 'Calendar', slug: 'robotparts-calendar', view: 'Month', blurb: 'Month, week and list grids; drag to propose a new date.' },
  { type: 'timeline', label: 'Timeline', slug: 'robotparts-timeline', view: 'Lanes by kind', blurb: 'Bars and points on a zoomable axis, in lanes from groupBy.' },
  { type: 'graph', label: 'Graph', slug: 'rack-wiring', view: 'Wiring', blurb: 'React Flow and dagre: edges from a property, groups as subflows.' },
  { type: 'map', label: 'Map', slug: 'robotparts-sellers-map', view: 'Where sellers ship', blurb: 'MapLibre on a bundled world map; no tile server.' },
];

const FEATURES = [
  ['Custom elements', '<code>&lt;data-views&gt;</code>, <code>&lt;data-facets&gt;</code>, <code>&lt;data-value&gt;</code>. Framework-free; React 19 uses the same tags. Light DOM, so the page\'s fonts and its no-JS table still apply.'],
  ['One grammar', 'Obsidian Bases <code>.base</code> files: <code>filters</code>, <code>order</code>, <code>sort</code>, <code>groupBy</code>, <code>summaries</code>, plus data-ui\'s keys. Every Bases file is a data-ui file; inside <code>chart:</code> the vocabulary is Vega-Lite\'s.'],
  ['Tokens, not theming knobs', 'Set <code>--data-*</code>, or nothing: each token falls back to shadcn\'s variable name, so a shadcn app needs zero lines and a vanilla app writes one block.'],
  ['Files are the agent interface', 'No AI inside. A JSON Schema and <code>data-ui check</code> make a <code>.base</code> file safe for Claude Code or Codex to write; the page re-renders when the file changes.'],
];

export async function buildSite({ root, dist, registered, manifests = [], version }) {
  const out = join(dist, 'site');
  mkdirSync(join(out, 'kit'), { recursive: true });
  // the kit the site runs on: exactly what a host vendors
  for (const f of ['data-ui.js', 'data-ui.js.map', 'data-ui.css', 'resize.js', 'resize.js.map', 'dashboard.js', 'dashboard.js.map', 'dashboard-arrange.js', 'dashboard-arrange.js.map', 'dashboard-edit.js', 'dashboard-edit.js.map', 'analysis.js', 'analysis.js.map', 'rowmodel-worker.js', 'rowmodel-worker.js.map', 'sources.js', 'sources.js.map', 'LICENSES.md']) if (existsSync(join(dist, f))) cpSync(join(dist, f), join(out, 'kit', f));
  cpSync(join(dist, 'views'), join(out, 'kit', 'views'), { recursive: true });
  cpSync(join(root, 'site', 'site.css'), join(out, 'site.css'));
  cpSync(join(root, 'site', 'site.js'), join(out, 'site.js'));
  // the gallery index's own layout and behaviour, kept out of site.css/site.js so the gallery lane meets no one there
  mkdirSync(join(out, 'gallery'), { recursive: true });
  for (const f of ['gallery.css', 'gallery.js']) cpSync(join(root, 'site', f), join(out, 'gallery', f));
  const examples = readExamples(root);
  const builtTypes = new Set(registered.filter((v) => v.status === 'built').map((v) => v.type));
  // WHY covers: a VIEWS.md row whose type cell is not one plain type ("`cards` + `lightbox:`") is marked built by name,
  // when a built view folder's manifest lists that row's View name in "covers" (docs/CONTRACT.md §1).
  const coveredNames = new Set(manifests.filter((m) => (m.status || 'built') === 'built').flatMap((m) => m.covers || []));
  let pages = 0;
  const write = (path, html) => { mkdirSync(join(out, path, '..'), { recursive: true }); writeFileSync(join(out, path), html); pages++; };

  // ---- each gallery case: its files, then its page
  // WHY beside the page, not in a files/ folder: a case may name a sibling's data (../robotparts-actuators/x.json),
  // which then resolves on the site exactly as it does on disk
  for (const ex of examples) {
    const dir = join(out, 'gallery', ex.slug);
    mkdirSync(dir, { recursive: true });
    for (const f of ex.files) cpSync(join(ex.here, f), join(dir, f));
    // WHY folders too: cases keep photos/SVGs/stills in subfolders; source/ holds only the scripts that rebuild the data
    for (const d of ex.dirs) cpSync(join(ex.here, d), join(dir, d), { recursive: true });
  }
  // ---- an analyses case: a page per analysis, <data-analysis src="<slug>.md"> (docs/peps/0007-analyses.md)
  for (const ex of examples.filter((e) => e.site && e.site.analyses)) {
    for (const f of ex.files.filter((n) => /^[a-z0-9][a-z0-9-]*\.md$/.test(n))) {
      const name = f.replace(/\.md$/, '');
      const front = (/^title:\s*(.+)$/m.exec(readFileSync(join(ex.here, f), 'utf8')) || [null, name])[1].replace(/^["']|["']$/g, '');
      write(`gallery/${ex.slug}/${name}.html`, page({
        title: `${front} · data-ui`, rel: '../../', nav: 'Gallery', description: `An analysis: ${front}`,
        body: `<main class="wrap analysis-page${ex.skin ? ' data-ui-skin' : ''}">
<p class="crumbs"><a href="../index.html">Gallery</a> › <a href="index.html">${esc(ex.title)}</a></p>
<data-analysis id="analysis" src="${f}"></data-analysis>
</main>`,
      }));
    }
  }
  const slugOf = (name) => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const typesOf = (ex) => [...new Set(ex.base.views.map((v) => v.type || 'table'))];
  const apps = [...new Set([...APP_ORDER.filter((a) => examples.some((ex) => ex.app === a)), ...examples.map((ex) => ex.app)])];
  const allTypes = TYPE_ORDER.filter((t) => examples.some((ex) => typesOf(ex).includes(t)));
  // ---- the Examples index (the section was "Gallery"; its URL stays gallery/ so links and the deploy's checks hold):
  // a picture per case, a column slider, compact filters, two groupings and five layouts (site/gallery.js)
  // WHY thumbnails: Zach, 2026-10-26: "in galleries it's about showing many different examples at a glance". Each
  // image is the case's real view, captured by site/capture-thumbs.py into site/.thumbs/ (gitignored, rebuilt by that
  // script); a missing one is drawn live instead, the way the landing page's thirteen thumbnails are.
  // WHY by view type first: Zach, 2026-10-26: "Vega-Lite calls it examples: those are the things we want to look at and
  // reference": its gallery is a nested table of contents by chart type over thumbnail sections. By app is one click away.
  const plain = (s) => String(s || '').replace(/`([^`]+)`/g, '$1').replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  // the caption's one line: the summary's first sentence (the card clamps it with a visible ellipsis; the whole
  // summary is the card's tooltip, the Docs panel's text and the case page's lede)
  const firstSentence = (s) => { const m = /^(.+?[.!?])(?=\s+[A-Z(]|$)/.exec(plain(s)); return m ? m[1] : plain(s); };
  const categoryOf = (ex) => {
    // a README's use case is its section ("- **Use case:** Robotics · Playback" sits under Robotics); else it may say
    // "- **Category:** Analyses"; else the case's first view's type decides
    const uc = useCaseOf(ex.bullets);
    if (uc) return uc.group;
    const named = (ex.bullets.Category || '').trim();
    if (CATEGORIES.includes(named)) return named;
    if (CATEGORY_OF_CASE[ex.slug]) return CATEGORY_OF_CASE[ex.slug];
    return CATEGORY_OF_TYPE[(ex.base.views[0] && ex.base.views[0].type) || 'table'] || 'Table';
  };
  const galleryRows = examples.map((ex) => ({
    id: ex.slug, slug: ex.slug, title: ex.title, app: ex.app, category: categoryOf(ex), useCase: useCaseOf(ex.bullets) ? useCaseOf(ex.bullets).text : null,
    summary: plain(ex.summary), line: firstSentence(ex.summary),
    types: typesOf(ex), data: ex.data, skin: ex.skin, href: `${ex.slug}/index.html`,
    views: ex.base.views.map((v, i) => ({ name: v.name, type: v.type || 'table', slug: slugOf(v.name), thumb: `thumbs/${ex.slug}/${i}` })),
    thumb: `thumbs/${ex.slug}/0-light-480.webp`, shows: plain(ex.bullets.Shows || ''),
  }));
  writeFileSync(join(out, 'gallery', 'gallery.json'), JSON.stringify({ rows: galleryRows }, null, 1));
  if (existsSync(join(root, 'site', '.thumbs'))) cpSync(join(root, 'site', '.thumbs'), join(out, 'gallery', 'thumbs'), { recursive: true });
  const img = (row, i, theme) => {
    const p = `${row.views[i].thumb}-${theme}`;
    // WHY sizes="auto": the column slider changes how wide a card is; the browser picks 480 or 960 from the laid-out width
    return `<img class="t t-${theme}" src="${p}-480.webp" srcset="${p}-480.webp 480w, ${p}-960.webp 960w" sizes="auto, 400px" width="960" height="600" loading="lazy" decoding="async" alt="">`;
  };
  const exampleCard = (row) => `<article class="card" id="case-${esc(row.slug)}" data-slug="${esc(row.slug)}" data-app="${esc(row.app)}" data-category="${esc(row.category)}" data-types="${esc(row.types.join(' '))}">
  <div class="cap"><h3><a href="${row.href}">${esc(row.title)}</a></h3><p class="line" title="${esc(row.summary)}">${esc(row.line)}</p></div>
  <div class="pv-bar"><div class="seg" role="tablist" aria-label="${esc(row.title)}"><button type="button" role="tab" data-pane="preview" aria-selected="true">Preview</button><button type="button" role="tab" data-pane="base" aria-selected="false">.base</button></div><a class="open" href="${row.href}">Open ↗</a></div>
  <div class="frame">
    <a class="card-link" href="${row.href}" title="${esc(row.summary)}" aria-label="${esc(row.title)}">
      <div class="shot" data-n="${row.views.length}">${img(row, 0, 'light')}${img(row, 0, 'dark')}<span class="scrub" aria-hidden="true">${row.views.map((v, i) => `<i${i ? '' : ' class="on"'}></i>`).join('')}</span><span class="shot-view" aria-hidden="true">${esc(row.views[0].name)}</span></div>
    </a>
    <div class="live-slot"></div>
    <div class="src-pane file" hidden><div class="file-bar"><a href="${row.slug}/views.base">views.base</a><button class="copy" type="button">Copy</button></div><pre><code></code></pre></div>
  </div>
  <div class="tabs" role="tablist" aria-label="${esc(row.title)}: views">${row.views.map((v, i) => `<button type="button" role="tab" data-i="${i}" aria-selected="${i === 0}">${esc(v.name)}</button>`).join('')}</div>
  <p class="meta"><span class="pill pill-app">${esc(row.app)}</span>${row.useCase && row.useCase.includes(' · ') ? `<span class="pill pill-use-case">${esc(row.useCase.split(' · ').slice(1).join(' · '))}</span>` : ''}<span class="nviews">${row.views.length} views</span>${row.types.map((t) => `<span class="pill">${esc(t)}</span>`).join('')}</p>
</article>`;
  const chips = (key, label, values, count) => `<div class="chips" role="group" aria-label="${esc(label)}" data-filter="${key}"><span class="chips-label">${esc(label)}</span><button type="button" class="chip" data-value="" aria-pressed="true">All <span class="n">${examples.length}</span></button>${values.map((v) => `<button type="button" class="chip" data-value="${esc(v)}" aria-pressed="false">${esc(v)} <span class="n">${count(v)}</span></button>`).join('')}</div>`;
  // WHY use cases after the view types: the page is Vega-Lite's table of contents by type first; a use case gathers
  // templates (Robotics: Playback, later Playback + Gates) that would otherwise scatter over Dashboards and 3D
  const useCases = [...new Set(examples.map((ex) => useCaseOf(ex.bullets)).filter(Boolean).map((u) => u.group))].filter((g) => !CATEGORIES.includes(g));
  const categories = [...CATEGORIES, ...useCases].filter((c) => galleryRows.some((r) => r.category === c));
  const subsOf = (c) => [...new Set(examples.filter((ex) => categoryOf(ex) === c).map((ex) => (useCaseOf(ex.bullets) || {}).sub).filter(Boolean))];
  const groupId = (kind, name) => `${kind}-${slugOf(name)}`;
  write('gallery/index.html', page({
    title: 'Examples · data-ui', rel: '../', nav: 'Examples', description: 'Real data from Zach\'s apps, each case one data file and one .base file.',
    head: '<link rel="stylesheet" href="gallery.css">',
    script: 'gallery.js',
    body: `<main class="wrap gallery" data-layout="index" data-group-by="type">
<div class="gallery-head">
  <h1>Examples</h1>
  <p class="lede">${examples.length} cases, each one data file and one <code>.base</code> file from Zach's apps; every picture is the real kit on the real data. Hover a picture to flip through its views.</p>
</div>
<div class="gallery-body">
<aside class="g-rail" id="gallery-rail" aria-label="Contents and filters" data-resizable-min="180" data-resizable-max="440">
  <input type="search" class="g-search" placeholder="Search ${examples.length} examples" aria-label="Search the examples">
  <nav class="toc" aria-label="Contents"></nav>
  <div class="filters">
    ${chips('app', 'App', apps, (a) => examples.filter((ex) => ex.app === a).length)}
    ${chips('type', 'View', allTypes, (t) => examples.filter((ex) => typesOf(ex).includes(t)).length)}
  </div>
</aside>
<div class="g-main">
  <div class="g-bar">
    <p class="filter-count" aria-live="polite"><span>${examples.length}</span> of ${examples.length} cases</p>
    <div class="group-by seg" role="group" aria-label="Group by"><span class="cols-label">Group</span><button type="button" data-group-by="type" aria-pressed="true">View type</button><button type="button" data-group-by="app" aria-pressed="false">App</button></div>
    <div class="cols" role="group" aria-label="Columns">
      <button type="button" class="cols-step" data-step="-1" aria-label="Fewer columns">−</button>
      <label><span class="cols-label">Columns</span> <input type="range" class="cols-range" min="1" max="8" step="1" value="5" aria-label="Columns"></label>
      <button type="button" class="cols-step" data-step="1" aria-label="More columns">+</button>
      <output class="cols-out">5</output>
    </div>
  </div>
  <div class="g-groups">
${categories.map((c) => `<section class="group type-group" id="${groupId('type', c)}" data-group="${esc(c)}"><h2>${esc(c)} <span class="n">${galleryRows.filter((r) => r.category === c).length}</span></h2>${subsOf(c).length ? `<p class="use-case-subs">${subsOf(c).map((u) => `<span class="pill pill-use-case">${esc(u)}</span>`).join(' ')}</p>` : ''}<div class="cards">${galleryRows.filter((r) => r.category === c).map(exampleCard).join('')}</div></section>`).join('\n')}
${apps.map((a) => `<section class="group app-group" id="${groupId('app', a)}" data-group="${esc(a)}" data-app="${esc(a)}" hidden><h2>${esc(a)} <span class="n">${examples.filter((ex) => ex.app === a).length}</span></h2><div class="cards"></div></section>`).join('\n')}
  </div>
  <p class="empty-note" hidden>No case matches. <button type="button" class="link-button" data-clear>Show every case</button></p>
</div>
<aside class="g-inspector" id="gallery-inspector" aria-label="Docs" data-resizable-min="260" data-resizable-max="560" aria-live="polite"></aside>
</div>
<script type="application/json" id="gallery-data">${JSON.stringify(galleryRows).replace(/</g, '\\u003c')}</script>
</main>`,
  }));
  // the page site/capture-thumbs.py screenshots: one view of one case, no toolbar, no rail, at a fixed size
  write('gallery/thumb.html', `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex">
<title>thumbnail · data-ui</title>
<link rel="stylesheet" href="../kit/data-ui.css">
<link rel="stylesheet" href="../site.css">
<script>try { const t = new URLSearchParams(location.search).get('theme'); if (t) document.documentElement.dataset.theme = t; } catch {}</script>
<style>body { margin: 0; } #stage { width: 720px; height: 450px; overflow: hidden; background: var(--background); } #stage data-views { --data-height: 450px; border: 0; } #stage .dv-status { display: none; }</style>
</head>
<body>
<div id="stage"></div>
<script type="module">
  import '../kit/data-ui.js';
  const q = new URLSearchParams(location.search);
  const slug = q.get('case'), stage = document.getElementById('stage');
  if (q.get('skin')) { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = slug + '/skin.css'; document.head.append(l); stage.classList.add('data-ui-skin'); }
  const el = document.createElement('data-views');
  el.setAttribute('src', slug + '/views.base');
  el.setAttribute('view', q.get('view') || '');
  el.setAttribute('no-url', '');
  el.setAttribute('toolbar', 'none');
  el.addEventListener('data-views-render', (e) => { window.__thumbRendered = (window.__thumbRendered || 0) + 1; window.__thumbType = e.detail.type; });
  stage.append(el);
</script>
</body>
</html>
`);
  for (const ex of examples) {
    const dataPath = join(ex.here, ex.data);
    let dataPreview = '';
    if (existsSync(dataPath)) {
      const raw = readFileSync(dataPath, 'utf8');
      try {
        const json = JSON.parse(raw);
        const rows = Array.isArray(json) ? json : json.rows;
        // WHY the schema first and only a few rows: the excerpt shows the shape an agent writes, not the whole table
        const head = Array.isArray(json) ? rows.slice(0, 3) : { ...json, rows: rows.slice(0, 3) };
        dataPreview = `// ${ex.data}: ${rows.length.toLocaleString('en-US')} rows, ${(raw.length / 1024).toFixed(0)} KB; the first 3\n` + JSON.stringify(head, null, 1);
      } catch { dataPreview = raw.split('\n').slice(0, 40).join('\n'); }
    }
    const extra = [];
    for (const f of ex.files.filter((x) => x.endsWith('.schema.json'))) extra.push([f, readFileSync(join(ex.here, f), 'utf8')]);
    if (ex.skin) extra.push(['skin.css', readFileSync(join(ex.here, 'skin.css'), 'utf8')]);
    extra.push(['README.md', ex.readme]);
    const file = (label, text, href = label) => `<div class="file"><div class="file-bar"><a href="${esc(href)}">${esc(label)}</a><button class="copy" type="button">Copy</button></div><pre><code>${esc(text)}</code></pre></div>`;
    const types = typesOf(ex);
    write(`gallery/${ex.slug}/index.html`, page({
      title: `${ex.title} · data-ui examples`, rel: '../../', nav: 'Examples', description: ex.summary,
      // a case's own page script beside it (site.json `script`): the live-robot case's in-page simulator
      script: ex.site && typeof ex.site.script === 'string' && /^[\w.-]+\.js$/.test(ex.site.script) ? ex.site.script : '',
      body: `<main class="wrap wide">
<p class="crumbs"><a href="../index.html">Examples</a> › ${useCaseOf(ex.bullets) ? `<a href="../index.html#type-${slugOf(useCaseOf(ex.bullets).group)}">${esc(useCaseOf(ex.bullets).group)}</a>${useCaseOf(ex.bullets).sub ? ` › ${esc(useCaseOf(ex.bullets).sub)}` : ''}` : `<a href="../index.html?app=${encodeURIComponent(ex.app)}">${esc(ex.app)}</a>`} › ${esc(ex.title)}</p>
<h1>${esc(ex.title)}</h1>
<p class="lede">${inline(ex.summary)}</p>
<p class="case-meta"><span class="pill pill-app">${esc(ex.app)}</span>${types.map((t) => `<a class="pill" href="../index.html?type=${t}">${esc(t)}</a>`).join('')}<span class="muted">${ex.base.layout ? `a dashboard: ${ex.base.views.length} views of ${1 + Object.values(ex.base.datasets || {}).filter((d) => (typeof d === 'string' ? d : d && d.data) !== ex.data).length} linked datasets` : `${ex.base.views.length} views of one <code>${esc(ex.data.split('/').pop())}</code>`}</span></p>
${ex.skin ? `<link rel="stylesheet" href="skin.css">` : ''}
<section class="live" aria-label="Live views">${demo(ex, { id: 'example', rel: '../../', height: 'min(78vh, 760px)' })}${noscript(ex, '../../')}</section>
<section class="case-files" aria-labelledby="files-h">
  <h2 id="files-h">The <code>.base</code> file and its data</h2>
  <p class="muted">Every tab above is one entry of this file; the views read these rows. ⋯ in the toolbar copies the current view as YAML.</p>
  <div class="side-by-side">${file('views.base', ex.baseText)}${dataPreview ? file(ex.data, dataPreview, ex.data) : ''}</div>
  <details class="more-files"><summary>${extra.map(([f]) => esc(f)).join(', ')}</summary>${extra.map(([f, text]) => file(f, text)).join('')}</details>
</section>
<section class="replaces-case" aria-labelledby="orig-h">
  <h2 id="orig-h">The original UI it replaces</h2>
  <div class="original">${markdown(ex.bullets.Replaces || 'Nothing: this case is new.')}</div>
  ${['Shows', 'Data', 'Skin'].filter((k) => ex.bullets[k]).map((k) => `<h3>${k === 'Shows' ? 'What it shows' : k}</h3><div class="readme">${markdown(ex.bullets[k])}</div>`).join('')}
</section>
</main>`,
    }));
  }

  // ---- the views list, the Dashboards page and the Docs pages: site/docs-pages.mjs (its own file, so the site lanes
  // meet in this one call)
  const table = readViewsTable(root);
  const statusOf = (r) => {
    const built = coveredNames.has(r.view) || (r.types.length && r.types.every((t) => builtTypes.has(t)) && r.plain);
    return built ? 'built' : 'planned';
  };
  buildDocsPages({ root, out, page, write, examples, registered, manifests, viewsTable: table, statusOf });

  // ---- a plain page: <data-kpi> and <data-sparkline> with no <data-views>, the way a Python-built report uses them
  // (docs/CONTRACT.md amendment 2026-10-26 (core pass); packages/views/kpi/README.md)
  write('plain/kpi.html', `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KPI cards on a plain page · data-ui</title>
<link rel="stylesheet" href="../kit/data-ui.css">
<script type="module" src="../kit/views/kpi.js"></script>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 0; padding: 24px 16px; max-width: 760px; margin-inline: auto; background: Canvas; color: CanvasText; }
  .strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
  p { color: GrayText; font-size: 13px; }
</style>
</head>
<body>
<h1>KPI cards on a plain page</h1>
<p>No <code>&lt;data-views&gt;</code>: this page loads <code>data-ui.css</code> and <code>views/kpi.js</code>, nothing else. The text inside each tag is what a reader without JavaScript sees.</p>
<div class="strip">
  <data-kpi label="Successful picks per minute" value="24.6" unit="picks/min" basis="measured" delta="+1.2 vs previous" tone="good" from="computed from 3 runs">24.6 picks/min</data-kpi>
  <data-kpi label="Computation time" value="182" unit="ms" basis="measured" delta="+14 ms vs previous" tone="bad" from="computed from 3 runs">182 ms</data-kpi>
  <data-kpi id="scripted">Grasp success: 61.2 %</data-kpi>
</div>
<p>A sparkline on its own, a reading not taken lifting the pen, an estimate hollow:</p>
<data-sparkline values="18.2,19.9,,21.4,23.4,24.6" bases="measured,measured,,estimate,measured,measured" width="240" height="40"></data-sparkline>
<script type="module">
  await customElements.whenDefined('data-kpi');
  document.getElementById('scripted').card = { label: 'Grasp success', value: { value: 61.2, unit: '%', basis: 'estimate', n: 3 },
    delta: { text: '−0.4 pts vs previous', tone: 'neutral' }, spark: [{ y: 55 }, { y: 58.1 }, { y: 61.6 }, { y: 61.2, basis: 'estimate' }], from: 'computed from 3 runs' };
</script>
</body>
</html>
`);

  // ---- a plain page: a host's own sidebar made resizable by resize.js alone (docs/CONTRACT.md §11)
  write('plain/resize.html', `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A resizable sidebar on a plain page · data-ui</title>
<script type="module" src="../kit/resize.js"></script>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 0; padding: 24px 16px; background: Canvas; color: CanvasText; }
  .layout { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 24px; }
  .side { width: var(--data-panel-width, 14rem); }
  .side ul { list-style: none; margin: 0; padding: 0; }
  .side li { padding: 6px 0; border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, Canvas); }
  p { color: GrayText; font-size: 13px; max-width: 60ch; }
  @media (max-width: 700px) { .layout { grid-template-columns: minmax(0, 1fr); } .side { width: auto; } }
</style>
</head>
<body>
<h1>A resizable sidebar on a plain page</h1>
<div class="layout">
  <nav class="side" id="side" aria-label="Categories" data-resizable="right" data-resizable-min="140" data-resizable-max="420">
    <ul><li>Actuators</li><li>Cameras</li><li>Power supplies</li><li>Motor drivers</li></ul>
  </nav>
  <main>
    <p>This page loads <code>resize.js</code> and nothing else of the kit. The sidebar says <code>data-resizable="right"</code>; its width is the page's own CSS, <code>width: var(--data-panel-width, 14rem)</code>. Drag its edge, use ← and → on the focused edge, double-click to reset. The width is remembered.</p>
  </main>
</div>
</body>
</html>
`);

  // ---- a plain page: the "where this value comes from" popover (dist/sources.js, docs/CONTRACT.md §22) on a <data-value>,
  // a host's own photo and file link, and a small table of rich cells
  const prov = (o) => esc(JSON.stringify(o));
  const photoSvg = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120" viewBox="0 0 160 120"><rect width="160" height="120" fill="#cfd8e6"/><circle cx="80" cy="60" r="34" fill="#4a6fa5"/><circle cx="80" cy="60" r="12" fill="#cfd8e6"/></svg>');
  const sourcesRows = [
    { id: 'a', model: 'GIM4305', peak_torque: { value: 1.9, unit: 'N·m', basis: 'datasheet', source: 'steadywin.cn', sourceUrl: 'https://www.steadywin.cn/en/product/gim4305-10', asOf: '2026-10-22', record: 'steadywin-gim4305 · specs.peak_torque_nm' }, mass: { value: 0.28, unit: 'kg', basis: 'measured', source: 'BAM bench scale', asOf: '2026-10-25', note: 'with the connector' } },
    { id: 'b', model: 'AiFitLab 8541', peak_torque: { value: 5.5, unit: 'N·m', basis: 'seller', source: 'aifitlab.com', sourceUrl: 'https://www.aifitlab.com/products/8541438771336', sourcePage: '../gallery/index.html', asOf: '2026-10-22', record: 'aifitlab-8541438771336 · specs.rated_torque_nm' }, mass: { value: 0.61, unit: 'kg', basis: 'estimate' } },
    { id: 'c', model: 'Plain row', peak_torque: 3.2, mass: 0.4 },
  ];
  mkdirSync(join(out, 'plain'), { recursive: true });
  writeFileSync(join(out, 'plain', 'sources.json'), JSON.stringify(sourcesRows, null, 1));
  writeFileSync(join(out, 'plain', 'sources.base'), `data: sources.json
properties:
  model: { displayName: Model }
  peak_torque: { displayName: Peak torque }
  mass: { displayName: Mass }
views:
  - type: table
    name: Table
    order: [model, peak_torque, mass]
`);
  write('plain/sources.html', `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Where a value comes from · data-ui</title>
<link rel="stylesheet" href="../kit/data-ui.css">
<script type="module" src="../kit/data-ui.js"></script>
<script type="module" src="../kit/sources.js"></script>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 0; padding: 24px 16px; max-width: 760px; margin-inline: auto; background: Canvas; color: CanvasText; }
  p, li { color: GrayText; font-size: 13px; }
  .row { display: flex; flex-wrap: wrap; gap: 24px; align-items: center; margin: 16px 0; }
  img { border-radius: 6px; display: block; }
  data-views { --data-height: 220px; }
</style>
</head>
<body>
<h1>Where a value comes from</h1>
<p>Right-click a value, a photo or a file link (or long-press on a phone, or focus one and press Shift+F10). The page loads <code>sources.js</code> beside the kit and writes no script of its own. Shift + right-click gives the browser's menu.</p>
<div class="row">
  <data-value id="torque" value="5.5" unit="N·m" basis="seller" source="aifitlab.com" source-url="https://www.aifitlab.com/products/8541438771336" source-page="../gallery/index.html" as-of="2026-10-22" record="aifitlab-8541438771336 · specs.rated_torque_nm" note="Listing says rated, not peak">5.5 N·m</data-value>
  <img id="photo" alt="A motor, photographed by the seller" width="160" height="120" src="${photoSvg}" data-provenance="${prov({ value: 'Photo of the AiFitLab 8541', source: 'aifitlab.com', sourceUrl: 'https://www.aifitlab.com/products/8541438771336', asOf: '2026-10-22', record: 'aifitlab-8541438771336 · photo' })}">
  <a id="datasheet" href="#datasheet" data-provenance="${prov({ value: 'GIM4305 datasheet (PDF)', basis: 'datasheet', source: 'steadywin.cn', sourceUrl: 'https://www.steadywin.cn/en/product/gim4305-10/datasheet.pdf', asOf: '2026-10-22' })}">GIM4305 datasheet</a>
  <span id="unmarked">A value with no source: the browser's own menu.</span>
</div>
<data-views id="parts" src="sources.base" no-url toolbar="none" aria-label="Actuators"></data-views>
</body>
</html>
`);
  // ---- the app rail's gallery page (docs/CONTRACT.md §27): site/rail-page.mjs
  railPage({ write, version });

  // ---- the landing page
  cpSync(join(root, 'site', 'hero.base'), join(out, 'hero.base'));
  const heroText = readFileSync(join(root, 'site', 'hero.base'), 'utf8');
  const heroBase = parseBase(heroText);
  const byCase = new Map(examples.map((ex) => [ex.slug, ex]));
  const thumbs = THUMBS.filter((t) => byCase.has(t.slug));
  const thumb = (t) => {
    const ex = byCase.get(t.slug);
    return `<a class="thumb" href="gallery/${t.slug}/index.html#view=${slugOf(t.view)}" data-src="gallery/${t.slug}/views.base" data-view="${esc(t.view)}">
      <div class="thumb-live" aria-hidden="true"></div>
      <div class="thumb-text"><h3>${esc(t.label)} <code>${esc(t.type)}</code></h3><p>${esc(t.blurb)}</p><p class="thumb-case">${esc(ex.title)} · ${esc(t.view)} →</p></div></a>`;
  };
  const replaceRows = examples.filter((ex) => ex.bullets.Replaces).sort((a, b) => APP_ORDER.indexOf(a.app) - APP_ORDER.indexOf(b.app) || a.title.localeCompare(b.title));
  write('index.html', page({
    title: 'data-ui · one dataset, one .base file, many views', rel: '', nav: 'Overview', head: '\n<link rel="stylesheet" href="docs.css">',
    body: `<main class="wrap">
<section class="hero">
  <p class="eyebrow">data-ui ${esc(version)}</p>
  <h1>One dataset, one <code>.base</code> file, many views.</h1>
  <p class="lede">A drop-in kit for viewing any data in your apps: framework-free custom elements, Obsidian's Bases grammar for the views, and tokens that default to shadcn's names. Not an app: you copy it into yours.</p>
  <p class="actions"><a class="button primary" href="gallery/index.html">Open the gallery</a><a class="button" href="#install">Drop it into an app</a></p>
</section>
${tiersHtml('')}
<section class="hero-demo" aria-label="Live demo">
  <div class="hero-bar">
    <div class="segmented" role="group" aria-label="Show the same rows as">${heroBase.views.map((v, i) => `<button type="button" data-name="${esc(v.name)}" aria-pressed="${i === 0}"><span class="seg-fill" aria-hidden="true"></span>${esc(v.name)}</button>`).join('')}</div>
    <button type="button" class="hero-play" aria-pressed="true">Pause</button>
  </div>
  <div class="hero-stage">
    <data-views id="hero" src="hero.base" no-url toolbar="none" aria-label="robotparts actuators"></data-views>
    <aside class="hero-file" aria-label="This view in the .base file"><div class="file-bar"><a href="hero.base">hero.base</a><span class="muted">this view's entry</span></div><pre><code class="hero-yaml"></code></pre></aside>
  </div>
  <p class="caption">Live: robotparts' 150 photographed actuators, one JSON file and one <code>.base</code> file. Every tab is the same rows; the panel shows the entry the tab draws. Hover a dot, drag a card, open a row.</p>
</section>

<section class="views-grid" aria-labelledby="views-h">
  <h2 id="views-h">Thirteen views, one row model</h2>
  <p class="lede">Each thumbnail is the kit running on a gallery case's real data. Filters, search, sort and grouping run once, in the core; a view only draws. Click one for its case.</p>
  <div class="thumbs">${thumbs.map(thumb).join('')}</div>
</section>

<section class="features">${FEATURES.map(([h, p]) => `<div class="feature"><h3>${h}</h3><p>${p}</p></div>`).join('')}</section>

<section class="install" id="install" aria-labelledby="install-h">
  <h2 id="install-h">Drop it into an app</h2>
  <div class="two">
    <div>
      <h3>Copy it in, pinned</h3>
      <p>shadcn/ui copies a component's <em>source</em> into your app, and from then on you own it and edit it. data-ui copies the <em>built kit</em> instead: <code>dist/</code> goes into your static folder whole, with <code>manifest.json</code> listing every file's sha256, and you never edit it there. To update, re-copy. You change data-ui from the outside: tokens for its look, <code>.base</code> files for its views, <code>registerView()</code> for a view of your own.</p>
      <p>Why not the shadcn way? Copies that apps edited are how Clank's views froze, one fork per app. A pinned copy is one version everywhere, and still nothing loads from a CDN. From a bundler, the same files are a pinned package: <code>import 'data-ui'</code>, <code>'data-ui/kpi'</code>.</p>
<pre><code>npm --prefix ~/data-ui run build
cp -r ~/data-ui/dist/{data-ui.js,data-ui.css,views,LICENSES.md,manifest.json} static/vendor/data-ui/</code></pre>
    </div>
    <div>
      <h3>Two tags, one file</h3>
<pre><code>${esc(`<link rel="stylesheet" href="/static/vendor/data-ui/data-ui.css">
<script type="module" src="/static/vendor/data-ui/data-ui.js"></script>

<data-facets for="parts"></data-facets>
<data-views id="parts" src="/data/actuators.base"></data-views>`)}</code></pre>
      <p>Only the core loads up front; each view's code loads the first time it shows. <code>&lt;data-kpi&gt;</code> and <code>&lt;data-sparkline&gt;</code> work on their own with <code>views/kpi.js</code> (<a href="plain/kpi.html">a plain page</a>).</p>
    </div>
  </div>
  <div class="two">
    <div>
      <h3>A <code>.base</code> file</h3>
<pre><code>${esc(`data: actuators.json          # JSON rows, CSV, JSONL or a field schema
filters: '!photo.isEmpty()'
views:
  - type: table
    name: Table
    order: [model, brand, peak_torque, mass]
    sort:
      - { property: peak_torque, direction: DESC }
  - type: chart                  # inside chart: it is Vega-Lite
    name: Chart
    chart:
      encoding:                  # no mark: Show Me picks one
        x: { field: mass, scale: { type: log } }
        y: { field: peak_torque }`)}</code></pre>
    </div>
    <div>
      <h3>Tokens, or nothing</h3>
      <p>Every colour, radius and font is a <code>--data-*</code> token that falls back to shadcn's variable, so a shadcn app maps nothing. Anything else maps one block, light and dark:</p>
<pre><code>${esc(`:root {
  --data-bg: var(--bg);       --data-fg: var(--ink);
  --data-muted: var(--ink2);  --data-border: var(--rule);
  --data-accent: var(--accent);
  --data-font: var(--sans);   --data-radius: 6px;
}`)}</code></pre>
    </div>
  </div>
  <div class="agent">
    <h3>Bring your own agent: the <code>.base</code> file is the API</h3>
    <p>data-ui has no AI and no agent protocol inside. Its agent interface is its files: the data, its field schema and one <code>.base</code> file of views, which <code>schemas/view.schema.json</code> describes and <code>data-ui check</code> verifies, one line per mistake with a suggestion an agent can act on. Your own Claude Code or Codex edits the file with your account; the page draws it on its next load, or at once when the host calls <code>reload()</code> on a file change. Going the other way, ⋯ copies the view a person built in the browser as YAML, and <code>#view=</code> carries it in a link. Live page state (what is selected, what is on screen) stays optional and never goes through a localhost socket (robotparts' agent-bridge proposals, 2026-10-25).</p>
<pre><code>node ~/data-ui/bin/data-ui.mjs check views.base --data actuators.json</code></pre>
  </div>
</section>

<section class="values">
  <h2>Every value says how sure it is</h2>
  <p class="lede">A cell can be a value with provenance, <code>{value, unit, basis, source, asOf}</code>. <code>&lt;data-value&gt;</code> draws it the same way in a table, a card or a report; its text is the no-JS truth. Hover a value.</p>
  <div class="value-grid">
    <div><span>Stall torque, SteadyWin's datasheet</span><data-value basis="datasheet" source="steadywin.cn" as-of="2026-10-22">3.82 N·m</data-value></div>
    <div><span>Coulomb friction, BAM's rack (CAN 14)</span><data-value value="0.0551" unit="N·m" basis="measured" source="BAM one-DoF rack, CAN 14" as-of="2026-10-25" note="Kt corrected x1.229">0.0551 N·m</data-value></div>
    <div><span>Peak torque, a seller's listing</span><data-value value="5.5" unit="N·m" basis="seller" source="aifitlab.com">5.5 N·m</data-value></div>
    <div><span>Rotor inertia</span><data-value why="not measured">—</data-value></div>
  </div>
  <p class="marks">${Object.entries(BASIS).map(([k, b]) => `<span title="${esc(b.means)}"><b>${esc(b.mark)}</b> ${esc(k)}</span>`).join('')}</p>
</section>

<section class="replaces" aria-labelledby="replaces-h">
  <h2 id="replaces-h">Replaces</h2>
  <p class="lede">Every gallery case rebuilds a screen someone hand-rolled in one of Zach's apps. Same data, a <code>.base</code> file instead of the code.</p>
  <div class="tablewrap"><table class="replaces-table">
    <thead><tr><th>App</th><th>Hand-rolled today</th><th>Rebuilt as</th></tr></thead>
    <tbody>${replaceRows.map((ex) => `<tr><td><span class="pill pill-app">${esc(ex.app)}</span>${APP_REPO[ex.app] ? `<div class="repo"><code>${esc(APP_REPO[ex.app])}</code></div>` : ''}</td><td>${markdown(ex.bullets.Replaces).replace(/^<p>|<\/p>$/g, '')}</td><td><a href="gallery/${ex.slug}/index.html">${esc(ex.title)}</a><div class="types">${typesOf(ex).map((t) => `<span class="pill">${esc(t)}</span>`).join(' ')}</div></td></tr>`).join('')}</tbody>
  </table></div>
</section>
</main>`,
  }));
  writeFileSync(join(out, '_headers'), SITE_HEADERS);
  return { pages, examples: examples.length };
}
