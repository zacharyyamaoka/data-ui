// Write the Filters case's kinds.html: every facet kind with the site it copies, what it does, its options and its
// .base snippet (cut from ../views.base, so the page never drifts from the file the case runs), and a link that opens
// the case with that kind already in use.
//   node gallery/examples/filters-gallery/source/kinds.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { KINDS } from '../../../../packages/core/src/facets.js';

const CASE = join(dirname(fileURLToPath(import.meta.url)), '..');
const { accessed, kinds, seen } = JSON.parse(readFileSync(join(CASE, 'source', 'kinds.json'), 'utf8'));
const base = readFileSync(join(CASE, 'views.base'), 'utf8').split('\n');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// the top-level facets: entries, each "  - …" plus its deeper lines
const entries = [];
let inFacets = false;
for (const line of base) {
  if (/^facets:/.test(line)) { inFacets = true; continue; }
  if (inFacets && /^\S/.test(line)) break;
  if (!inFacets) continue;
  if (/^ {2}- /.test(line)) entries.push([line]);
  else if (entries.length) entries[entries.length - 1].push(line);
}
const snippet = (kind) => {
  const test = kind === 'values + exclude' ? /exclude: true/ : kind === 'diagram (any kind)' ? /diagram:/ : new RegExp(`as: ${kind.replace(/[-]/g, '\\-')}\\b(?!-)`);
  const hit = entries.find((e) => test.test(e.join('\n')));
  return hit ? `facets:\n${hit.join('\n')}` : '';
};

const known = new Set(Object.keys(KINDS));
const missing = [...known].filter((k) => !kinds.some((x) => x.kind === k));
if (missing.length) throw new Error(`kinds.json lacks ${missing.join(', ')}`);

const rows = kinds.map((k) => `<section class="kind" id="${k.kind.replace(/[^a-z-]+/g, '-').replace(/-+$/, '')}">
  <h2><code>${esc(k.kind)}</code> <span class="copies">copies <a href="${esc(k.url)}">${esc(k.copies)}</a></span></h2>
  <p>${esc(k.what)}. <span class="muted">Options: ${esc(k.options)}.</span> <a class="try" href="index.html${esc(k.try)}">Try it: <code>${esc(decodeURIComponent(k.try))}</code></a></p>
  <pre><code>${esc(snippet(k.kind))}</code></pre>
</section>`).join('\n');

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Filter kinds · data-ui gallery</title>
<link rel="stylesheet" href="../../kit/data-ui.css">
<link rel="stylesheet" href="../../site.css">
<script>try { const t = localStorage.getItem('data-ui-site-theme'); if (t) document.documentElement.dataset.theme = t; } catch {}</script>
<style>
  .kind { border-top: 1px solid var(--border, #e5e5e5); padding: 14px 0 6px; }
  .kind h2 { font-size: 16px; margin: 0 0 4px; display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
  .kind .copies { font-size: 13px; font-weight: 400; color: var(--muted-foreground, #666); }
  .kind p { margin: 0 0 8px; max-width: 80ch; }
  .kind pre { margin: 0; overflow-x: auto; font-size: 12px; padding: 8px 10px; border-radius: 6px; background: var(--muted, #f4f4f5); }
  .muted { color: var(--muted-foreground, #666); }
  .try { white-space: nowrap; }
  table.seen { border-collapse: collapse; font-size: 13px; width: 100%; }
  table.seen td { border-top: 1px solid var(--border, #e5e5e5); padding: 6px 8px 6px 0; vertical-align: top; }
</style>
</head>
<body>
<main class="wrap">
<p class="crumbs"><a href="../index.html">Gallery</a> › <a href="index.html">Filters</a> › Kinds</p>
<h1>Filter kinds</h1>
<p class="lede">Each kind is one <code>facets:</code> entry, <code>{property, as: &lt;kind&gt;, …options}</code>, and every kind edits the same Bases <code>filters</code> tree, so a pick shows in every view and what the rail cannot draw stays as a custom clause. An unknown kind draws as <code>values</code> with a warning. Options common to all: <code>label</code>, <code>info</code> (the ⓘ), <code>diagram</code>, <code>collapsed</code>. The snippets below are cut from this case's <code>views.base</code>. Sites accessed ${esc(accessed)}.</p>
${rows}
<h2>Also looked at</h2>
<table class="seen"><tbody>${seen.map((s) => `<tr><td>${s.url ? `<a href="${esc(s.url)}">${esc(s.site)}</a>` : esc(s.site)}</td><td>${esc(s.copy)}</td></tr>`).join('')}</tbody></table>
</main>
</body>
</html>
`;
writeFileSync(join(CASE, 'kinds.html'), html);
console.log(`kinds.html: ${kinds.length} kinds, ${(html.length / 1024).toFixed(0)} KB`);
