/* Analyses, data-ui's third tier (docs/peps/0007-analyses.md, CONTRACT §19): views -> dashboards -> analyses.

   Zach, 2026-10-26: "I actually feel this analysis format should be part of data-ui. I definitely see me reusing this in
   many apps, particularly apps using data-ui. So data-ui now has the normal dataset views, then the dashboards, and now
   the analysis pages."

   An analysis is one Markdown file: YAML frontmatter (title, question, status, parts, decision, date, author, …), prose,
   ```base fences and ![[x.base]] / ![[x.base#View]] embeds (Obsidian's own forms; a .base with layout: is a dashboard),
   and > [!type] callouts ([!decision] the verdict, [!illustrative] what is assumed). Born in robotparts.dev as its
   PEP 0002 and moved here unchanged in shape. This module is the format's reader: pure, no DOM, so node --test, the
   checker (src/check.js) and the elements (src/index.js) read files the same way; data_ui_analysis.py is its Python
   twin for build scripts. */

import { parseBase } from '../../core/src/base.js';
import { bindThis, bindFilters } from '../../core/src/sections.js';

export const STATUSES = ['draft', 'open', 'decided', 'superseded'];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const isText = (v) => typeof v === 'string' && v.trim() !== '';
const isEmptyValue = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0);
export const listOf = (v) => (Array.isArray(v) ? v : isEmptyValue(v) ? [] : [v]).map((x) => String(x).trim()).filter(Boolean);
const base = (path) => String(path).split('/').pop();


/** {yaml, body, bodyLine}: the frontmatter's text (null when the file has none), the rest, and the body's first line. */
export function splitFrontmatter(text) {
  const src = String(text ?? '').replace(/^﻿/, '').replace(/\r\n?/g, '\n');
  const m = /^---[ \t]*\n([\s\S]*?\n)?---[ \t]*(?:\n|$)/.exec(src);
  if (!m) return { yaml: null, body: src, bodyLine: 1 };
  const yaml = m[1] || '';
  const lines = yaml ? yaml.split('\n').length - 1 : 0;
  return { yaml, body: src.slice(m[0].length), bodyLine: lines + 3 };
}

/** {front, body, bodyLine, problems: [{line, message}]}: the file read with the kit's parser (`parseBase`), and what
    PEP 0002 §4 asks of the frontmatter. The checker (build/site_analysis.py) says the same things with the same words. */
export function readAnalysis(text, parse = parseBase) {
  const { yaml, body, bodyLine } = splitFrontmatter(text);
  if (yaml === null) return { front: {}, body, bodyLine, problems: [{ line: 1, message: 'no frontmatter: the file must start with --- and a title:' }] };
  let front;
  try {
    front = yaml.trim() ? parse(yaml) : {};
    if (!front || typeof front !== 'object' || Array.isArray(front)) throw new Error('it is not a list of key: value lines');
  } catch (err) {
    return { front: {}, body, bodyLine, problems: [{ line: 1 + (Number(err && err.line) || 1), message: `frontmatter does not parse: ${err && err.message ? err.message : err}` }] };
  }
  const lines = yaml.split('\n');
  const at = (key) => { const i = lines.findIndex((l) => new RegExp(`^${key}\\s*:`).test(l)); return i < 0 ? 1 : i + 2; };
  const problems = [];
  for (const key of ['title', 'question']) if (!isText(front[key])) problems.push({ line: at(key), message: `${key}: is required` });
  if (!isEmptyValue(front.status) && !STATUSES.includes(front.status)) {
    problems.push({ line: at('status'), message: `status: must be one of ${STATUSES.join(', ')} (it is ${front.status})` });
  }
  if (!isEmptyValue(front.parts) && !Array.isArray(front.parts)) problems.push({ line: at('parts'), message: 'parts: must be a list of part ids' });
  if (!isEmptyValue(front.decision) && !listOf(front.parts).includes(String(front.decision))) {
    problems.push({ line: at('decision'), message: `decision: ${front.decision} is not one of parts:` });
  }
  if (!isEmptyValue(front.date) && !DATE_RE.test(String(front.date))) {
    problems.push({ line: at('date'), message: `date: must be YYYY-MM-DD (it is ${front.date})` });
  }
  return { front, body, bodyLine, problems };
}

/** The body as blocks, in reading order, each with its first line in the file:
      {kind: 'markdown', text, line}                     prose (data-ui's markdown(), after linkify)
      {kind: 'base', text, line}                         a ```base fence: an inline .base document
      {kind: 'embed', name, view, line}                  ![[name.base]] or ![[name.base#View]] on a line of its own
      {kind: 'callout', type, fold, title, text, line}   > [!type]± Title, then its > lines
    A fence of any other language and a plain > quote stay prose. */
export function blocksOf(body, startLine = 1) {
  const lines = String(body ?? '').split('\n');
  const out = [];
  let prose = [], proseLine = 0;
  const flush = () => {
    if (prose.length && prose.some((l) => l.trim())) out.push({ kind: 'markdown', text: prose.join('\n').replace(/^\n+|\n+$/g, ''), line: proseLine });
    prose = [];
  };
  const addProse = (line, n) => { if (!prose.length) proseLine = startLine + n; prose.push(line); };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^\s*(`{3,}|~{3,})\s*([\w-]*)\s*$/.exec(line);
    if (fence) {
      const [, mark, lang] = fence;
      const close = new RegExp(`^\\s*${mark[0] === '`' ? '`' : '~'}{${mark.length},}\\s*$`);
      let j = i + 1;
      while (j < lines.length && !close.test(lines[j])) j++;
      if (lang.toLowerCase() === 'base') {
        flush();
        out.push({ kind: 'base', text: lines.slice(i + 1, j).join('\n'), line: startLine + i });
      } else {
        for (let k = i; k <= Math.min(j, lines.length - 1); k++) addProse(lines[k], k);
      }
      i = j;
      continue;
    }
    const embed = /^\s*!\[\[([^\]|#]+?\.base)(?:#([^\]|]+))?(?:\|[^\]]*)?\]\]\s*$/.exec(line);
    if (embed) {
      flush();
      out.push({ kind: 'embed', name: embed[1].trim(), view: embed[2] ? embed[2].trim() : null, line: startLine + i });
      continue;
    }
    const callout = /^>\s*\[!([\w-]+)\]([+-]?)\s*(.*)$/.exec(line);
    if (callout) {
      flush();
      const text = [];
      let j = i + 1;
      while (j < lines.length && /^>/.test(lines[j])) { text.push(lines[j].replace(/^>\s?/, '')); j++; }
      out.push({ kind: 'callout', type: callout[1].toLowerCase(), fold: callout[2] || '', title: callout[3].trim(), text: text.join('\n'), line: startLine + i });
      i = j - 1;
      continue;
    }
    addProse(line, i);
  }
  flush();
  return out;
}

// WHY from the core: the side peek binds `this` to the peeked row by the same rule (docs/CONTRACT.md §35), so one
// function serves both; it moved there unchanged
export { bindThis };

/** A parsed .base document with `this` bound in every filter: the file's, each view's and each dataset's. */
export function bindDoc(doc, front = {}) {
  const copy = JSON.parse(JSON.stringify(doc || {}));
  if (copy.filters !== undefined) copy.filters = bindFilters(copy.filters, front);
  for (const view of Array.isArray(copy.views) ? copy.views : []) if (view && view.filters !== undefined) view.filters = bindFilters(view.filters, front);
  for (const set of Object.values(copy.datasets || {})) if (set && typeof set === 'object' && set.filters !== undefined) set.filters = bindFilters(set.filters, front);
  return copy;
}

/** Prose with [[wikilinks]] made Markdown links: a part id opens its page (`lookup(id)` -> {name, url}), another
    analysis's slug opens it (`isAnalysis(slug)`), anything else stays text marked "not in this release". `[[id\|x]]`

/** A dashboard's datasets as [{name, data}], named as data-ui names them (PEP 0004 §4): each `datasets:` entry, and
    the top-level `data:` by its file's stem when no entry names the same file. */
export function datasetsOf(doc) {
  const out = Object.entries((doc && doc.datasets) || {}).map(([name, d]) => ({ name, data: typeof d === 'string' ? d : d && d.data }));
  if (doc && typeof doc.data === 'string' && !out.some((d) => d.data === doc.data)) {
    out.push({ name: base(doc.data).replace(/\.[^.]+$/, ''), data: doc.data });
  }
  return out;
}

/** Prose with [[wikilinks]] made Markdown links. `resolve(target)` -> {name, url} (the host decides what a target is:
    a part, another analysis, a note); an unresolved one becomes `missing(target, label)` (default: the label, or the
    target, as plain text). `[[x\\|label]]` (Obsidian's pipe escape inside a table) works. Code spans, fences and
    ![[embeds]] are left alone. */
export function linkify(text, resolve = () => null, { missing = (target, label) => label || target } = {}) {
  const parts = String(text ?? '').split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/);
  return parts.map((part, n) => (n % 2 ? part : part.replace(/(?<!!)\[\[([^\]|\\]+?)(?:\\?\|([^\]]*))?\]\]/g, (_, target, label) => {
    const id = target.trim();
    const shown = label !== undefined && label.trim() ? label.trim() : null;
    const found = resolve && resolve(id);
    if (found && found.url) return `[${shown || found.name || id}](${found.url})`;
    return missing(id, shown);
  }))).join('');
}

/** A list row for one analysis (the <data-analyses> dataset's properties): the frontmatter, with `lookup(id)` -> {name}
    naming the parts. A host adds its own columns beside these (robotparts: who owns it, the part photos). */
export function analysisRow(slug, front = {}, { lookup = () => null, url = null, path = null } = {}) {
  const ids = listOf(front.parts);
  const decision = isEmptyValue(front.decision) ? null : String(front.decision);
  const chosen = decision && lookup(decision);
  return {
    id: slug,
    title: isText(front.title) ? front.title : slug,
    question: isText(front.question) ? front.question : null,
    status: STATUSES.includes(front.status) ? front.status : 'draft',
    parts: ids.map((id) => { const p = lookup(id); return (p && p.name) || id; }),
    part_ids: ids,
    parts_count: ids.length,
    decision: decision ? (chosen && chosen.name) || decision : null,
    decision_id: decision,
    date: isEmptyValue(front.date) ? null : String(front.date),
    author: isText(front.author) ? front.author : null,
    tags: listOf(front.tags),
    visibility: front.visibility === 'public' ? 'public' : 'private',
    url: url || null,
    path: path || null,
  };
}

export function slugify(text) {
  return String(text).toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'section';
}

/** The headings of rendered prose (data-ui's markdown(): # -> h2, ## -> h3), as the table of contents lists them:
    [{level, text, id}], ids unique within the document. */
export function outline(html) {
  const used = new Set();
  const out = [];
  for (const m of String(html).matchAll(/<h([23])>([\s\S]*?)<\/h\1>/g)) {
    const text = m[2].replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();
    let id = slugify(text), n = 2;
    while (used.has(id)) id = `${slugify(text)}-${n++}`;
    used.add(id);
    out.push({ level: Number(m[1]), text, id });
  }
  return out;
}
