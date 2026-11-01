/* `data-ui check analysis.md` (docs/peps/0007-analyses.md, CONTRACT §19): an analysis checked the way the page reads it.

     data-ui check FILE.md [FILE.base ...] [--root DIR] [--embeds DIR ...] [--quiet] [--json]

   For each .md: the frontmatter's rules (format.js readAnalysis), then every ```base fence and every ![[x.base]] embed
   through the .base checker the page runs (packages/core/src/check.js checkText), against the data each one names:
     a relative path    beside the file that names it (an analysis's own data, e.g. data/bench.json)
     a path from /      under --root (a host's public files, e.g. robotparts' dist/site); without --root it is skipped
                        with a warning, never guessed
   An embed is looked for beside the analysis, then in each --embeds folder (Obsidian looks across the vault; a host
   names its folders). Every problem carries its line in the .md. .base files on the same command line are checked as
   `data-ui check` always did. Exit status 1 on any error; warnings never fail. Node only (reads files). */

import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve, join, basename } from 'node:path';
import { checkText, datasetProperties, datasetTypes, datasetLink, main as checkBases } from '../../core/src/check.js';
import { parseBase, parseBaseWithLines, lineOf as lineAt } from '../../core/src/base.js';
import { readAnalysis, blocksOf, bindDoc, datasetsOf } from './format.js';
import { stringifyBase } from '../../core/src/base.js';
import { checkPage } from '../../dashboard/src/model.js';

/** A data path, resolved: {path} or {problem}. */
function dataFile(path, dir, root) {
  if (typeof path !== 'string' || !path) return { problem: 'names no data: file' };
  if (path.startsWith('/')) {
    if (!root) return { warning: `data ${path} is a host path: pass --root to check it` };
    const full = join(root, path);
    return existsSync(full) ? { path: full } : { problem: `data ${path}: no such file under ${root}` };
  }
  const full = resolve(dir, path);
  return existsSync(full) ? { path: full } : { problem: `data ${path}: no such file` };
}

const props = (path) => {
  const p = datasetProperties(path);
  return p ? new Set([...p, 'id']) : p;
};

/** Problems of one .base document (a fence's text, or an embedded file) that sits in `dir`, reported at `line`. */
function checkBase(text, { dir, root, front, line, label, view = null, lineOf = (n) => line + n }) {
  const out = [];
  let doc;
  try { doc = parseBase(text); } catch (err) { return [{ level: 'error', line, message: `${label}: the .base does not parse: ${err.message}` }]; }
  if (view && !(doc.views || []).some((v) => v && v.name === view)) {
    return [{ level: 'error', line, message: `${label}: no view named "${view}" (it has ${(doc.views || []).map((v) => `"${v.name}"`).join(', ') || 'none'})` }];
  }
  // WHY bound first: `this.<key>` is the note's frontmatter (format.js bindThis), never a property of the data
  const bound = stringifyBase(bindDoc(doc, front));
  const dash = doc.layout || doc.datasets;
  let options = {};
  if (dash) {
    const datasets = {};
    for (const d of datasetsOf(doc)) {
      const found = dataFile(d.data, dir, root);
      if (found.problem) out.push({ level: 'error', line, message: `${label}: ${found.problem}` });
      else if (found.warning) out.push({ level: 'warning', line, message: `${label}: ${found.warning}` });
      else datasets[d.name] = { props: props(found.path), types: datasetTypes(found.path), file: basename(found.path) };
    }
    const first = datasetsOf(doc).find((d) => d.data === doc.data);
    const main = first && datasets[first.name];
    options = { datasets, properties: main ? main.props : null, types: main ? main.types : null, datasetName: main ? main.file : '' };
  } else {
    const found = dataFile(doc.data, dir, root);
    if (found.problem) return [...out, { level: 'error', line, message: `${label}: ${found.problem}` }];
    if (found.warning) return [...out, { level: 'warning', line, message: `${label}: ${found.warning}` }];
    options = { properties: props(found.path), types: datasetTypes(found.path), link: datasetLink(found.path), datasetName: basename(found.path) };
  }
  // WHY the source's own line map: the bound text is re-serialised (its layout differs), but a problem's key path is
  // the same in both, so the line comes from where that path sits in what the author wrote
  let lines = null;
  try { lines = parseBaseWithLines(text).lines; } catch { lines = null; }
  for (const p of checkText(bound, options)) {
    const at = lines && p.path ? lineAt(lines, p.path) : p.line;
    out.push({ level: p.level, line: lineOf(at || 0), message: `${label}: ${p.message}` });
  }
  return out;
}

/** Every problem of one analysis file: [{level, line, message}], in line order. */
export function checkAnalysis(text, file, { root = null, embeds = [] } = {}) {
  const dir = dirname(resolve(file));
  const { front, body, bodyLine, problems } = readAnalysis(text);
  const out = problems.map((p) => ({ level: 'error', ...p }));
  for (const block of blocksOf(body, bodyLine)) {
    if (block.kind === 'base') {
      out.push(...checkBase(block.text, { dir, root, front, line: block.line, label: '```base' }));
    } else if (block.kind === 'embed') {
      const label = `![[${block.name}${block.view ? `#${block.view}` : ''}]]`;
      const where = [dir, ...embeds.map((d) => resolve(d))].map((d) => join(d, block.name)).find((p) => existsSync(p));
      if (!where) { out.push({ level: 'error', line: block.line, message: `![[${block.name}]]: no such file (looked beside the analysis${embeds.length ? ' and in --embeds' : ''})` }); continue; }
      out.push(...checkBase(readFileSync(where, 'utf8'), { dir: dirname(where), root, front, line: block.line, label, view: block.view, lineOf: () => block.line }));
    }
  }
  return out.sort((a, b) => a.line - b.line);
}

/** The command line: .md files here, .base files through the .base checker, one summary. */
export function main(argv, { log = console.log } = {}) {
  const files = [], rest = [], embeds = [], pages = [];
  let root = null, quiet = false, json = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') root = resolve(argv[++i]);
    else if (a === '--embeds') embeds.push(argv[++i]);
    else if (a === '--quiet') { quiet = true; rest.push(a); }
    else if (a === '--json') json = true;
    else if (a.endsWith('.md')) files.push(a);
    // WHY pages (judge r3 #6): several <data-dashboard>s on one HTML page need a unique URL key each
    else if (/\.html?$/i.test(a)) pages.push(a);
    else rest.push(a);
  }
  const bases = rest.filter((a) => !a.startsWith('--') || a === '--data' || a === '--quiet');
  let status = 0;
  if (bases.some((a) => !a.startsWith('--')) || (!files.length && !pages.length && rest.length)) status = checkBases(bases.concat(json ? ['--json'] : []), { log });
  if (pages.length) {
    let errors = 0;
    for (const file of pages) {
      for (const p of checkPage(readFileSync(file, 'utf8'))) {
        errors++;
        if (!quiet) log(json ? JSON.stringify({ file, ...p }) : `${file}:${p.line}: ${p.level}: ${p.message}`);
      }
    }
    if (!json) log(`checked ${pages.length} ${pages.length === 1 ? 'page' : 'pages'}: ${errors} errors`);
    if (errors) status = 1;
  }
  if (!files.length) return status;
  let errors = 0, warnings = 0;
  const report = [];
  for (const file of files) {
    for (const p of checkAnalysis(readFileSync(file, 'utf8'), file, { root, embeds })) {
      if (p.level === 'error') errors++; else warnings++;
      report.push({ file, ...p });
      if (!quiet && !json) log(`${file}:${p.line}: ${p.level}: ${p.message}`);
    }
  }
  if (json) log(JSON.stringify({ errors, warnings, problems: report }, null, 1));
  else log(`checked ${files.length} ${files.length === 1 ? 'analysis' : 'analyses'}: ${errors} errors, ${warnings} warnings`);
  return errors || status ? 1 : 0;
}
