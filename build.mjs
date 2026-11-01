// npm run build: every package into dist/, plus the docs site into dist/site/.
//
//   dist/data-ui.js        the core (elements, grammar, row model, registry; TanStack Table + Virtual inside)
//   dist/data-ui.css       tokens + the core's chrome
//   dist/resize.js         resizable side panels alone, for a page with no <data-views> (its css inside)
//   dist/sources.js        the "where this value comes from" popover alone (right-click, long-press, Shift+F10; its css inside)
//   dist/rowmodel-worker.js the row model in a Web Worker (<data-views> at 5,000+ rows; packages/core/src/rowmodel-worker.js)
//   dist/views/<folder>.js one lazy bundle per packages/views/<folder> (it imports ../data-ui.js; its css inside), plus
//                          views/<folder>-<name>-<hash>.js for what a `split: true` view loads on first use
//   dist/python/           data_ui_base.py, the stdlib .base reader for Python-built pages
//   dist/LICENSES.md       the licence of every npm package bundled, read from the bundles themselves
//   dist/manifest.json     version, and the sha256 of every file (what a host vendors, re-copies, never edits)
//   dist/site/             the landing page, the gallery (one page per gallery/examples/<case>) and the views list
// Nothing loads from another origin at runtime: everything a page needs is in dist/.
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildSite } from './site/build-site.mjs';

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, 'dist');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const started = Date.now();

rmSync(DIST, { recursive: true, force: true });
mkdirSync(join(DIST, 'views'), { recursive: true });

// ---- the views: one folder each, registered from its manifest.json
const viewsDir = join(ROOT, 'packages', 'views');
const folders = readdirSync(viewsDir).filter((f) => existsSync(join(viewsDir, f, 'manifest.json'))).sort();
const manifests = folders.map((folder) => ({ folder, ...JSON.parse(readFileSync(join(viewsDir, folder, 'manifest.json'), 'utf8')) }));
const registered = manifests.flatMap((m) => m.views.map((v) => ({ type: v.type, name: v.name, icon: v.icon || null, summary: v.summary || '', status: m.status || 'built', folder: m.folder })));
const seen = new Set();
for (const v of registered) {
  if (seen.has(v.type)) throw new Error(`two view folders register type '${v.type}'`);
  seen.add(v.type);
}

const viewsModule = {
  name: 'data-ui-views',
  setup(b) {
    b.onResolve({ filter: /^data-ui:views$/ }, () => ({ path: 'views', namespace: 'data-ui' }));
    b.onLoad({ filter: /.*/, namespace: 'data-ui' }, () => ({ contents: `export default ${JSON.stringify(registered)};`, loader: 'js' }));
  },
};
// WHY external: a view bundle imports the page's one core (the registry, TanStack, the helpers), never a copy
const coreExternal = {
  name: 'data-ui-core',
  setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: '../data-ui.js', external: true }));
    // a pure module that also runs in Node as it is imports the core by path (plotkit.js: the legend's rule); it is the
    // same one core in the browser, as the dashboard's imports are (coreBesideMe, below)
    b.onResolve({ filter: /\/core\/src\/[\w-]+\.js$/ }, () => ({ path: '../data-ui.js', external: true }));
  },
};

const common = { bundle: true, format: 'esm', minify: true, target: 'es2022', legalComments: 'none', sourcemap: 'linked', metafile: true, logLevel: 'warning',
  define: { 'process.env.NODE_ENV': '"production"' } };
const core = await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'core', 'src', 'index.js')], outfile: join(DIST, 'data-ui.js'), plugins: [viewsModule],
  banner: { js: `/* data-ui ${pkg.version} · MIT · bundles listed in LICENSES.md */` },
});
const metas = [core.metafile];
for (const m of manifests) {
  // WHY `split` (review 2026-10-26 item 8): a view with a feature most readers never open (the cards' lightbox) loads it
  // with import(); split: true makes that its own file beside the bundle, fetched on first use. Without it esbuild
  // inlines the import, so every other view keeps exactly one file.
  const where = m.split
    ? { entryPoints: { [m.folder]: join(viewsDir, m.folder, m.entry || 'src/index.js') }, outdir: join(DIST, 'views'), splitting: true, chunkNames: `${m.folder}-[name]-[hash]` }
    : { entryPoints: [join(viewsDir, m.folder, m.entry || 'src/index.js')], outfile: join(DIST, 'views', `${m.folder}.js`) };
  const out = await build({
    ...common, ...where,
    plugins: [coreExternal], loader: { '.css': 'text', '.jsx': 'jsx' }, jsx: 'automatic',
    banner: { js: `/* data-ui ${pkg.version} · view: ${m.views.map((v) => v.type).join(', ')} · bundles listed in ../LICENSES.md */` },
  });
  metas.push(out.metafile);
}
// WHY assets: some libraries load a file beside their bundle at run time (MapLibre's worker); a manifest lists them as
// {"from": "<path under the repo>", "to": "<path under dist/views>"} and they are copied as-is (docs/CONTRACT.md §1)
for (const m of manifests) for (const a of m.assets || []) {
  mkdirSync(join(DIST, 'views', a.to, '..'), { recursive: true });
  cpSync(join(ROOT, a.from), join(DIST, 'views', a.to));
}
// the version string, written once
const coreJs = join(DIST, 'data-ui.js');
writeFileSync(coreJs, readFileSync(coreJs, 'utf8').replace('DATA_UI_VERSION', pkg.version));

// ---- css: tokens, then the core's chrome
await build({
  stdin: { contents: ['tokens.css', 'core.css', 'types.css', 'notes.css', 'resize.css', 'frame.css', 'open.css', 'toolbar.css', 'query.css', 'select.css', 'mesh.css', 'rail.css', 'add.css', 'sheet.css'].map((f) => readFileSync(join(ROOT, 'packages', 'core', 'styles', f), 'utf8')).join('\n'), loader: 'css', resolveDir: ROOT },
  outfile: join(DIST, 'data-ui.css'), minify: true, logLevel: 'warning', banner: { css: `/* data-ui ${pkg.version} · tokens + chrome (docs/CONTRACT.md §4) */` },
});

// ---- dist/resize.js: resizable side panels for a page that loads nothing else of the kit (its css inside)
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'core', 'src', 'resize-page.js')], outfile: join(DIST, 'resize.js'), loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · resizable side panels (docs/CONTRACT.md §11) */` },
})).metafile);

// ---- dist/dashboard.js: <data-dashboard> (docs/peps/0004-dashboards.md), loaded only by a page that has one.
// WHY every core import maps to ./data-ui.js: the dashboard's source imports the core's modules by path (so node
// --test runs it as is), and the bundle must use the page's one core, never a second copy of the grammar
const coreBesideMe = {
  name: 'data-ui-core-beside',
  setup(b) { b.onResolve({ filter: /\/core\/src\/[\w-]+\.js$/ }, () => ({ path: './data-ui.js', external: true })); },
};
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'dashboard', 'src', 'index.js')], outfile: join(DIST, 'dashboard.js'),
  plugins: [coreBesideMe], loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · <data-dashboard> (docs/peps/0004-dashboards.md) · imports ./data-ui.js */` },
})).metafile);

// ---- dist/dashboard-arrange.js: drag-to-arrange (gridstack), loaded by <data-dashboard> only when a reader presses
// Arrange (docs/peps/0005-dashboard-cards.md §6); its core imports are the page's one core, as above
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'dashboard', 'src', 'arrange.js')], outfile: join(DIST, 'dashboard-arrange.js'),
  plugins: [coreBesideMe], loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · dashboard Arrange (gridstack, MIT) · imports ./data-ui.js */` },
})).metafile);

// ---- dist/dashboard-edit.js: the dashboard editor (packages/dashboard/src/edit/), loaded by <data-dashboard> when a reader
// presses Edit. Pragmatic drag and drop inside; gridstack is the Arrange bundle's: WHY ./dashboard-arrange.js external, one
// grid path and one copy of gridstack. WHY base.js bundled, not the page's core: the edits write YAML with base.js's
// yamlFlow and yamlScalar, which the core does not export, and an editor is no reason to widen the core's API (base.js is
// pure: a second copy shares no state)
const editorBeside = {
  name: 'data-ui-editor-beside',
  setup(b) {
    b.onResolve({ filter: /\/core\/src\/[\w-]+\.js$/ }, (a) => (/\/base\.js$/.test(a.path) ? undefined : { path: './data-ui.js', external: true }));
    b.onResolve({ filter: /\/arrange\.js$/ }, () => ({ path: './dashboard-arrange.js', external: true }));
  },
};
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'dashboard', 'src', 'edit', 'index.js')], outfile: join(DIST, 'dashboard-edit.js'),
  plugins: [editorBeside], loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · the dashboard editor (Pragmatic drag and drop, Apache-2.0) · imports ./data-ui.js and ./dashboard-arrange.js */` },
})).metafile);

// ---- dist/analysis.js: <data-analysis> and <data-analyses> (docs/peps/0007-analyses.md), data-ui's third tier, loaded
// only by a page that has one; like the dashboard, every core import is the page's one ./data-ui.js, and it loads
// ./dashboard.js itself on the first dashboard an analysis embeds
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'analysis', 'src', 'index.js')], outfile: join(DIST, 'analysis.js'),
  plugins: [coreBesideMe], loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · <data-analysis>, <data-analyses> (docs/peps/0007-analyses.md) · imports ./data-ui.js */` },
})).metafile);

// ---- dist/sources.js: the right-click "where this value comes from" popover, for any page that marks values with data-provenance
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'core', 'src', 'sources-menu.js')], outfile: join(DIST, 'sources.js'), loader: { '.css': 'text' },
  banner: { js: `/* data-ui ${pkg.version} · where this value comes from (docs/CONTRACT.md §22) */` },
})).metafile);

// ---- dist/rowmodel-worker.js: the row model off the main thread for 10k-100k+ rows (packages/core/src/rowmodel-worker.js;
// <data-views> makes one at 5,000 rows and up). Its own copy of the row model and TanStack, since a worker cannot share the page's.
metas.push((await build({
  ...common, entryPoints: [join(ROOT, 'packages', 'core', 'src', 'rowmodel.worker.js')], outfile: join(DIST, 'rowmodel-worker.js'),
  banner: { js: `/* data-ui ${pkg.version} · row-model worker · bundles listed in LICENSES.md */` },
})).metafile);

// ---- python
mkdirSync(join(DIST, 'python'), { recursive: true });
cpSync(join(ROOT, 'packages', 'core', 'python', 'data_ui_base.py'), join(DIST, 'python', 'data_ui_base.py'));
cpSync(join(ROOT, 'packages', 'analysis', 'python', 'data_ui_analysis.py'), join(DIST, 'python', 'data_ui_analysis.py'));

// ---- licences: the npm packages the bundles actually contain
const bundled = new Set();
for (const meta of metas) {
  for (const input of Object.keys(meta.inputs)) {
    const m = /node_modules\/((?:@[^/]+\/)?[^/]+)\//.exec(input);
    if (m) bundled.add(m[1]);
  }
}
const licenceOf = (name) => {
  const dir = join(ROOT, 'node_modules', name);
  const p = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'));
  const file = readdirSync(dir).find((f) => /^licen[cs]e/i.test(f));
  return { name, version: p.version, licence: p.license || '(see file)', text: file ? readFileSync(join(dir, file), 'utf8').trim() : '(no licence file in the package)' };
};
const inBundles = [...bundled].sort().map(licenceOf);
const forLanes = Object.keys(pkg.dependencies).filter((n) => !bundled.has(n)).sort().map(licenceOf);
writeFileSync(join(DIST, 'LICENSES.md'), `# Licences

data-ui ${pkg.version} is MIT. Read from the bundles' own inputs at build time (build.mjs).

## Bundled in dist/

${inBundles.map((l) => `- ${l.name}@${l.version} (${l.licence})`).join('\n')}

## Installed for the views not built yet (bundled when their view lands)

${forLanes.map((l) => `- ${l.name}@${l.version} (${l.licence})`).join('\n')}

${[...inBundles, ...forLanes].map((l) => `## ${l.name}@${l.version} (${l.licence})\n\n${l.text}\n`).join('\n')}`);

// ---- the site (it copies the kit it runs on into dist/site/kit/)
const site = await buildSite({ root: ROOT, dist: DIST, registered, manifests, version: pkg.version });

// ---- the manifest a host vendors against
const files = [];
const walk = (dir) => { for (const f of readdirSync(dir)) { const p = join(dir, f); if (statSync(p).isDirectory()) { if (p !== join(DIST, 'site')) walk(p); } else files.push(p); } };
walk(DIST);
const sha = (p) => createHash('sha256').update(readFileSync(p)).digest('hex');
writeFileSync(join(DIST, 'manifest.json'), JSON.stringify({
  name: 'data-ui', version: pkg.version, views: registered.map(({ type, folder, status }) => ({ type, folder, status })),
  files: Object.fromEntries(files.sort().map((p) => [relative(DIST, p), { bytes: statSync(p).size, sha256: sha(p) }])),
}, null, 1) + '\n');

const kb = (p) => (statSync(p).size / 1024).toFixed(1);
console.log(`built dist/ in ${Date.now() - started} ms: data-ui.js ${kb(coreJs)} KB, ${manifests.map((m) => `views/${m.folder}.js ${kb(join(DIST, 'views', `${m.folder}.js`))} KB`).join(', ')}; ` +
  `site: ${site.pages} pages, ${site.examples} gallery examples; bundled: ${[...bundled].sort().join(', ')}`);
