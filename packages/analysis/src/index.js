/* <data-analysis> and <data-analyses>: data-ui's third tier (docs/peps/0007-analyses.md, CONTRACT §19).

     views       <data-views>      one dataset, many views of it
     dashboards  <data-dashboard>  many views over linked datasets, from one .base with layout:
     analyses    <data-analysis>   a report: prose, views and dashboards, a decision, from one Markdown file
                 <data-analyses>   the list of reports: a <data-views> over their frontmatter

   Zach, 2026-10-26: "I like how you use a data-ui table/gallery to view and organise the analysis pages, and the
   table of contents with the headers so I can quickly jump to sections. I actually feel this analysis format should
   be part of data-ui."

   <data-analysis src="x.md"> (or .text) draws: a contents column (the prose's headings, sticky, drag-resizable and
   remembered, CONTRACT §11), a header (status, question, the parts, the decision, the file and its actions), the body
   (format.js blocks: markdown() prose, <data-views> or <data-dashboard> for each ```base fence and ![[x.base]] embed,
   callouts), and the file's problems by line. A redraw (a new .text: an agent edited the file) reuses every block
   whose source did not change, so editing a sentence never reloads a view. Each embed has no-url: several views on
   one page never fight over the URL.

   A host plugs in what is its own (all optional):
     resolveLink(target) -> {name, url, photo?}   what [[target]] opens (a part, a note); also the header's part chips
     missingLink(target, label) -> string          what an unresolved [[target]] reads as (default: its label)
     readFile(path) -> Promise<string|null>        a relative path not on the web (a synced folder's files)
     source = {kind, label, note, path, rawUrl, filename}   the header's pill, its note and the file line
     dir (attribute or property)                   where relative paths start (default: the folder of src)
     embeds="dir dir"                              where else ![[x.base]] is looked for (after the analysis's own folder)
     heading="2"                                   the title's level when the page already has an h1
   Events: data-analysis-render {problems, embeds} after every draw.

   <data-analyses src="index.json"> (data_ui_analysis.build_index's file) or .rows: a <data-views> of one row per
   analysis (format.js analysisRow) with Gallery, Table and Board by status, or the presets of base="x.base". .data
   and .model pass through to the views, so a host or a check reads the list as it reads any <data-views>.

   Load: <link rel="stylesheet" href="data-ui.css"> and <script type="module" src="analysis.js"> (it imports the page's
   one core, ./data-ui.js, and loads ./dashboard.js on the first dashboard it meets). */

import { parseBase } from '../../core/src/base.js';
import { loadDataset, normalizeDataset, parseCSV, parseJSONL } from '../../core/src/data.js';
import { markdown } from '../../core/src/md.js';
import { makeResizable } from '../../core/src/resize.js';
import { STATUSES, listOf, readAnalysis, blocksOf, bindDoc, linkify, datasetsOf, analysisRow, slugify } from './format.js';
import css from './analysis.css';

export * from './format.js';

const STATUS_LABEL = { draft: 'Draft', open: 'Open', decided: 'Decided', superseded: 'Superseded' };
const CALLOUT_LABEL = { ai: 'AI', decision: 'Decision', illustrative: 'Illustrative', example: 'Example', note: 'Note', warning: 'Warning', tip: 'Tip', info: 'Info', question: 'Question' };
const LIST_TYPES = new Set(['table', 'cards', 'list']);
const isText = (v) => typeof v === 'string' && v.trim() !== '';

function addStyle() {
  if (typeof document === 'undefined' || document.querySelector('style[data-ui-analysis]')) return;
  const s = document.createElement('style');
  s.dataset.uiAnalysis = '';
  s.textContent = css;
  document.head.prepend(s); // WHY first: a host's own stylesheet (its skin) comes later and wins
}

function h(tag, attrs, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children || []) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

const join = (dir, name) => (dir ? `${dir.replace(/\/+$/, '')}/${name}` : name);
const dirOf = (path) => (String(path).includes('/') ? String(path).replace(/\/[^/]*$/, '') : '');
const isUrl = (p) => /^(\/|https?:|blob:|data:)/.test(p);
const urlCache = new Map();
const dashboard = () => import(new URL('./dashboard.js', import.meta.url).href);

function parseData(text, path) {
  if (/\.csv$/i.test(path)) return normalizeDataset(parseCSV(text));
  if (/\.jsonl$/i.test(path)) return normalizeDataset(parseJSONL(text));
  return normalizeDataset(JSON.parse(text));
}

export class DataAnalysis extends HTMLElement {
  static get observedAttributes() { return ['src']; }

  constructor() {
    super();
    this._text = null;
    this.resolveLink = null;
    this.missingLink = null;
    this.readFile = null;
    this.source = null;
  }

  connectedCallback() {
    addStyle();
    if (!this._built) this._build();
    if (this._text !== null) this._queue();
    else if (this.getAttribute('src')) this._load();
  }

  attributeChangedCallback(name, old, value) { if (old !== value && this.isConnected && name === 'src' && this._text === null) this._load(); }

  /** The file's text; setting it (an agent edited the file) redraws, keeping every unchanged block. */
  set text(value) { this._text = value === null || value === undefined ? null : String(value); if (this.isConnected) this._queue(); }
  get text() { return this._text; }
  get dir() { return this._dir ?? this.getAttribute('dir') ?? (this.getAttribute('src') ? dirOf(new URL(this.getAttribute('src'), location.href).pathname) : ''); }
  set dir(value) { this._dir = value; }
  get front() { return this._front || {}; }
  get problems() { return this._problems || []; }

  /** Re-read src (or redraw .text). */
  async reload() { if (this._text !== null && !this.getAttribute('src')) return this._queue(); return this._load(); }

  async _load() {
    const src = this.getAttribute('src');
    if (!src) return;
    try {
      const response = await fetch(new URL(src, location.href), { cache: 'no-cache' });
      if (!response.ok) throw new Error(`${response.status}`);
      this._fromSrc = true;
      this._text = await response.text();
      this._queue();
    } catch (err) {
      this._bodyEl.replaceChildren(h('p', { class: 'an-err', text: `data-ui could not read ${src}: ${err.message}` }));
      this._bodyEl.dataset.state = 'ready';
    }
  }

  _build() {
    this._built = true;
    const id = this.id || 'analysis';
    this.classList.add('data-ui');
    this.replaceChildren();
    this._toc = h('aside', { class: 'an-toc', id: `${id}-toc`, 'aria-label': 'Contents', 'data-resizable': this.hasAttribute('no-toc') ? 'off' : 'right',
      'data-resizable-min': '160', 'data-resizable-max': '440', 'data-resizable-key': `${id}-toc` }, [h('nav')]);
    this._bodyEl = h('div', { class: 'an-body', id: `${id}-body`, 'data-state': 'loading' }, [h('p', { class: 'an-mut', text: 'Reading the analysis…' })]);
    this._main = h('article', { class: 'an-main' }, [this._bodyEl]);
    const layout = h('div', { class: 'an-layout' }, [this.hasAttribute('no-toc') ? null : this._toc, this._main]);
    this.append(layout);
    if (!this.hasAttribute('no-toc')) makeResizable(this._toc, { label: 'the contents' });
  }

  _queue() {
    // WHY one draw at a time, the newest text winning: an agent can rewrite the file faster than views load
    this._wanted = (this._wanted || 0) + 1;
    const ticket = this._wanted;
    this._drawing = (this._drawing || Promise.resolve()).then(() => (ticket === this._wanted ? this._draw() : null));
    return this._drawing;
  }

  _link(target) {
    return this.resolveLink ? this.resolveLink(target) : null;
  }

  _linkify(text) {
    return linkify(text, (t) => this._link(t), { missing: this.missingLink || ((t, l) => l || t) });
  }

  async _readRelative(path) {
    if (isUrl(path)) {
      const response = await fetch(path, { credentials: 'same-origin' });
      return response.ok ? response.text() : null;
    }
    if (this.readFile) return this.readFile(path);
    if (this._fromSrc || this.getAttribute('src')) {
      const response = await fetch(new URL(path, new URL(this.getAttribute('src'), location.href)), { credentials: 'same-origin' });
      return response.ok ? response.text() : null;
    }
    return null;
  }

  /** A data path written in a .base that sits in `fromDir`: a URL path loads from the web (cached per page); anything
      else is a file beside it (readFile, or relative to src). */
  async _data(path, fromDir) {
    if (typeof path !== 'string' || !path) throw new Error('this view names no data: file');
    const target = isUrl(path) ? path : join(fromDir, path).replace(/\/\.\//g, '/');
    if (isUrl(target)) {
      // the dataset keeps its own URL (media paths in its cells resolve against it, CONTRACT §1 amendment)
      if (!urlCache.has(target)) urlCache.set(target, loadDataset(target).then((ds) => ({ ...ds, url: new URL(target, location.href).href })).catch((err) => { urlCache.delete(target); throw err; }));
      return urlCache.get(target);
    }
    const text = await this._readRelative(target);
    if (text === null || text === undefined) throw new Error(`${path}: no such file (looked for ${target})`);
    // WHY a url: a cell's media path and a dashboard's own files (posters, videos, rerun:) resolve against the data
    // file's URL (CONTRACT §1 amendment); without it they resolved against the analysis page and 404ed
    const abs = this._absolute(target);
    return abs ? { ...parseData(text, target), url: abs } : parseData(text, target);
  }

  /** A path relative to src as an absolute URL, or null when the analysis reads files through a host (no URL). */
  _absolute(path) {
    if (!this.getAttribute('src')) return null;
    try { return new URL(path, new URL(this.getAttribute('src'), location.href)).href; } catch { return null; }
  }

  /** The .base an ![[embed]] names: beside the analysis, then each embeds= folder. */
  async _findBase(name) {
    const places = [this.dir, ...(this.getAttribute('embeds') || '').split(/\s+/).filter(Boolean), ...(this._embeds || [])];
    for (const dir of places) {
      const path = join(dir, name);
      try {
        const text = await this._readRelative(path);
        if (text !== null && text !== undefined) return { text, dir: dirOf(path) };
      } catch { /* the next place */ }
    }
    return null;
  }

  set embeds(list) { this._embeds = list || []; }

  async _embed(box, text, fromDir, viewName) {
    let doc;
    try { doc = parseBase(text); } catch (err) { throw new Error(`the .base does not parse: ${err.message}`); }
    doc = bindDoc(doc, this.front);
    if (viewName) {
      const views = (doc.views || []).filter((v) => v && v.name === viewName);
      if (!views.length) throw new Error(`no view named "${viewName}" (it has ${(doc.views || []).map((v) => `"${v.name}"`).join(', ') || 'none'})`);
      doc.views = views;
    }
    if (doc.layout) {
      await dashboard();
      const sets = {};
      for (const { name, data } of datasetsOf(doc)) sets[name] = { ...(await this._data(data, fromDir)) };
      const el = h('data-dashboard', { 'no-url': true });
      // the .base's own folder, so its rerun: file (and any path it names) resolves where the .base is
      const dirUrl = this._absolute(`${fromDir ? fromDir.replace(/\/?$/, '/') : ''}`);
      if (dirUrl) el.baseUrl = dirUrl;
      box.replaceChildren(el);
      el.load(doc, sets);
      return el;
    }
    const data = await this._data(doc.data, fromDir);
    const first = ((doc.views || [])[0] || {}).type || 'table';
    // WHY page for lists: a short table grows to its rows instead of leaving an empty box; charts keep a fixed box
    const el = h('data-views', { 'no-url': true, toolbar: 'compact', frame: LIST_TYPES.has(first) ? 'page' : null });
    if (!LIST_TYPES.has(first)) el.style.setProperty('--data-height', first === 'compare' ? '380px' : '420px');
    box.replaceChildren(el);
    el.data = data;
    el.base = doc;
    return el;
  }

  _partChip(id, chosen) {
    const part = this._link(id);
    // WHY a slot only for a resolved part: a list of plain ids (motors, robots) reads as names, not as missing photos
    const img = part && part.photo ? h('img', { src: part.photo, alt: '', loading: 'lazy' }) : part ? h('span', { class: 'an-nophoto', 'aria-hidden': 'true' }) : null;
    const name = part && part.url ? h('a', { href: part.url, text: part.name || id }) : h('span', {}, [h('code', { text: id }), this.missingLink ? ` ${this.missingLink(id, null).replace(id, '').trim()}` : '']);
    return h('li', { class: `an-part${chosen ? ' an-chosen' : ''}`, 'data-part': id }, [img, h('span', { class: 'an-part-name' }, [name, chosen ? h('span', { class: 'an-pill an-pill-chosen', text: 'Chosen' }) : null])]);
  }

  _copyButton(label) {
    const button = h('button', { type: 'button', class: 'an-btn', text: label });
    button.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(this._text || ''); button.textContent = 'Copied'; } catch { button.textContent = 'Copy failed: use Download'; }
      setTimeout(() => { button.textContent = label; }, 1600);
    });
    return button;
  }

  _header(read) {
    const f = read.front;
    const source = this.source || {};
    const status = STATUSES.includes(f.status) ? f.status : 'draft';
    const ids = listOf(f.parts);
    const decision = f.decision === undefined || f.decision === null || f.decision === '' ? null : String(f.decision);
    const chosen = decision && this._link(decision);
    const meta = [h('span', { class: `an-status an-status-${status}`, text: STATUS_LABEL[status] })];
    if (source.label) meta.push(h('span', { class: `an-pill an-src-${source.kind || 'file'}`, text: source.label }));
    if (f.date) meta.push(h('span', { text: String(f.date) }));
    if (f.author) meta.push(h('span', { text: String(f.author) }));
    if (source.note) meta.push(h('span', { class: 'an-vis', text: source.note }));
    const src = this.getAttribute('src');
    const filename = source.filename || (src ? src.split('/').pop() : 'analysis.md');
    const path = source.path ?? (src ? [h('code', { text: src })] : null);
    const raw = source.rawUrl || src;
    const download = h('a', { class: 'an-btn', download: filename, href: URL.createObjectURL(new Blob([this._text || ''], { type: 'text/markdown' })), text: 'Download' });
    if (this._downloadUrl) URL.revokeObjectURL(this._downloadUrl);
    this._downloadUrl = download.href;
    return h('header', { class: 'an-head' }, [
      h('p', { class: 'an-meta' }, meta),
      h(this.getAttribute('heading') === '2' ? 'h2' : 'h1', { id: 'top', class: 'an-title', text: isText(f.title) ? f.title : filename }),
      isText(f.question) ? h('p', { class: 'an-q', text: f.question }) : null,
      ids.length ? h('ul', { class: 'an-parts', 'aria-label': 'Parts considered' }, ids.map((id) => this._partChip(id, id === decision))) : null,
      decision ? h('p', { class: 'an-verdict' }, ['Decision: ', chosen && chosen.url ? h('a', { href: chosen.url, text: chosen.name || decision }) : h('code', { text: decision })]) : null,
      h('div', { class: 'an-file' }, [path ? h('span', { class: 'an-file-path' }, Array.isArray(path) ? path : [path]) : null,
        h('span', { class: 'an-actions' }, [this._copyButton('Copy as Markdown'), download,
          raw ? h('a', { class: 'an-btn', href: raw, target: '_blank', rel: 'noopener', text: 'Open the file' }) : null])]),
    ]);
  }

  _callout(block) {
    const label = CALLOUT_LABEL[block.type] || block.type.charAt(0).toUpperCase() + block.type.slice(1);
    const title = block.title ? markdown(this._linkify(block.title)).replace(/^<p>|<\/p>$/g, '') : '';
    const body = h('div', { class: 'an-callout-body', html: markdown(this._linkify(block.text)) });
    const head = h('div', { class: 'an-callout-title' }, [h('span', { class: 'an-callout-label', text: label }), title ? h('span', { html: title }) : null]);
    const id = block.type === 'decision' ? 'decision' : null;
    if (block.fold) return h('details', { class: `an-callout an-callout-${block.type}`, open: block.fold === '+' ? true : null, id }, [h('summary', {}, [head]), body]);
    return h('aside', { class: `an-callout an-callout-${block.type}`, id, role: 'note' }, [head, body]);
  }

  async _draw() {
    const text = this._text ?? '';
    const read = readAnalysis(text);
    this._front = read.front;
    const body = this._bodyEl;
    body.dataset.state = 'drawing';
    const old = body._blocks || new Map();
    const next = new Map();
    const nodes = [];
    const problems = read.problems.map((p) => ({ line: p.line, message: p.message }));
    const embeds = [];
    const sig = this.dataSignature || '';
    let index = 0;
    for (const block of blocksOf(read.body, read.bodyLine)) {
      const key = block.kind === 'markdown' || block.kind === 'callout'
        ? `${block.kind}:${block.type || ''}:${block.title || ''}:${block.text}`
        : `${block.kind}:${block.text || ''}:${block.name || ''}:${block.view || ''}:${JSON.stringify(read.front)}:${sig}`;
      let node = old.get(key);
      if (node) old.delete(key);
      else if (block.kind === 'markdown') node = h('div', { class: 'an-md', html: markdown(this._linkify(block.text)) });
      else if (block.kind === 'callout') node = this._callout(block);
      else {
        node = h('figure', { class: 'an-embed' }, [h('div', { class: 'an-embed-box' }, [h('p', { class: 'an-mut', text: 'Loading the view…' })])]);
        if (block.kind === 'embed') node.append(h('figcaption', { class: 'an-embed-cap' }, [h('code', { text: `![[${block.name}${block.view ? ` · ${block.view}` : ''}]]` })]));
        embeds.push({ node, block });
      }
      node.dataset.line = String(block.line);
      if (block.kind === 'base' || block.kind === 'embed') node.dataset.embed = String(index++);
      next.set(key, node);
      nodes.push(node);
    }
    body._blocks = next;
    const head = this._header(read);
    const prior = this._main.querySelector(':scope > .an-head');
    if (prior) prior.replaceWith(head); else this._main.prepend(head);
    body.replaceChildren(...nodes);
    this._main.querySelector(':scope > .an-problems')?.remove();
    await Promise.all(embeds.map(async ({ node, block }) => {
      const target = node.querySelector('.an-embed-box');
      try {
        if (block.kind === 'base') await this._embed(target, block.text, this.dir, null);
        else {
          const found = await this._findBase(block.name);
          if (!found) throw new Error(`![[${block.name}]]: no such file (looked beside the analysis${(this.getAttribute('embeds') || (this._embeds || []).length) ? ' and in its embeds folders' : ''})`);
          await this._embed(target, found.text, found.dir, block.view);
        }
      } catch (err) {
        target.replaceChildren(h('p', { class: 'an-err', text: `line ${block.line}: ${err.message}` }));
        problems.push({ line: block.line, message: err.message });
      }
    }));
    this._problems = problems;
    if (problems.length) {
      head.after(h('div', { class: 'an-problems', role: 'alert' }, [h('strong', { text: `${problems.length} problem${problems.length === 1 ? '' : 's'} in this file` }),
        h('ul', {}, problems.map((p) => h('li', { text: `line ${p.line}: ${p.message}` })))]));
    }
    this._contents();
    body.dataset.state = 'ready';
    this.dispatchEvent(new CustomEvent('data-analysis-render', { detail: { problems, embeds: embeds.length } }));
  }

  /** The contents: the prose's headings and the decision (a dashboard's own headings are the view's, not the report's). */
  _contents() {
    const nav = this._toc.querySelector('nav');
    const used = new Set();
    const items = [];
    const found = [...this._bodyEl.querySelectorAll(':scope > .an-md > h2, :scope > .an-md > h3, :scope > .an-callout-decision')];
    // WHY relative: a file whose sections are all ## lists them flush, not all indented under a level it never uses
    const top = Math.min(...found.filter((x) => /^H\d$/.test(x.tagName)).map((x) => Number(x.tagName[1])), 9);
    for (const heading of found) {
      let id = heading.id || slugify(heading.textContent);
      while (used.has(id)) id += '-2';
      used.add(id);
      heading.id = id;
      const text = heading.classList.contains('an-callout-decision') ? 'Decision' : heading.textContent;
      items.push(h('li', { class: /^H\d$/.test(heading.tagName) && Number(heading.tagName[1]) > top ? 'an-toc-sub' : null }, [h('a', { href: `#${id}`, text })]));
    }
    nav.replaceChildren(h('p', { class: 'an-toc-h', text: 'Contents' }), h('ul', {}, [h('li', {}, [h('a', { href: '#top', text: 'Top' })]), ...items]));
  }
}

// ------------------------------------------------------------------ the list

/** The list's default presets: what a host gets with no base= (the robotparts /analysis/ list, without its skin). */
export const LIST_BASE = {
  facets: [{ as: 'current', label: 'Current filters' }, { property: 'status', as: 'values', label: 'Status' }, { property: 'tags', as: 'values', label: 'Tags' }],
  // WHY Table first: a card with no image puts its selection box over the title (a core cards issue); a host whose
  // rows carry a picture (robotparts' photo mosaic) puts its Gallery first with base=
  views: [
    { type: 'table', name: 'Table', order: ['title', 'status', 'decision', 'parts', 'question', 'date', 'author'], rowHeight: 'short', sort: [{ property: 'date', direction: 'DESC' }] },
    { type: 'cards', name: 'Gallery', order: ['title', 'question', 'status', 'decision', 'parts_count', 'date'], cardSize: 300,
      sort: [{ property: 'date', direction: 'DESC' }, { property: 'title', direction: 'ASC' }] },
    { type: 'kanban', name: 'Board by status', order: ['title', 'decision', 'date'], groupBy: { property: 'status' }, groupOrder: STATUSES },
  ],
  open: { mode: 'link', url: 'url' },
};

export const LIST_PROPERTIES = {
  title: { type: 'text', label: 'Analysis', width: 260 }, question: { type: 'text', label: 'Question', width: 320 },
  status: { type: 'text', label: 'Status', width: 100 }, parts: { type: 'list', label: 'Parts considered', width: 300 },
  part_ids: { type: 'list', hidden: true }, parts_count: { type: 'number', label: 'Parts', width: 70 },
  decision: { type: 'text', label: 'Decision', width: 200 }, decision_id: { type: 'text', hidden: true },
  date: { type: 'date', label: 'Date', width: 110 }, author: { type: 'text', label: 'Author', width: 160 },
  tags: { type: 'list', label: 'Tags', width: 160 }, visibility: { type: 'text', label: 'Visibility', width: 100 },
  url: { type: 'text', hidden: true }, path: { type: 'text', label: 'File', width: 300 },
};

export class DataAnalyses extends HTMLElement {
  connectedCallback() {
    addStyle();
    if (!this._views) {
      this._views = h('data-views', { toolbar: this.getAttribute('toolbar') || 'compact', 'aria-label': this.getAttribute('aria-label') || 'Analyses' });
      for (const attr of [...this.attributes]) if (attr.name.startsWith('data-') || attr.name === 'no-url' || attr.name === 'frame') this._views.setAttribute(attr.name, attr.value);
      this._started = this._start();
    }
  }

  get views() { return this._views; }
  get data() { return this._views && this._views.data; }
  set data(dataset) { this._pending = dataset; if (this._views && this._ready) this._views.data = dataset; }
  get model() { return this._views && this._views.model; }

  /** Rows from analysisRow (plus a host's own columns): the list shows exactly these. */
  set rows(rows) { this.data = { id: this.id || 'analyses', title: 'Analyses', titleProperty: 'title', linkProperty: 'url', properties: { ...LIST_PROPERTIES, ...(this._extraProps || {}) }, rows }; }
  set properties(extra) { this._extraProps = extra; }

  async _start() {
    const baseUrl = this.getAttribute('base');
    let doc = LIST_BASE;
    if (baseUrl) {
      const text = await (await fetch(new URL(baseUrl, location.href))).text();
      doc = parseBase(text);
      this._views.baseText = text;
    }
    let dataset = this._pending;
    const src = this.getAttribute('src');
    if (!dataset && doc.data && baseUrl) dataset = await loadDataset(new URL(doc.data, new URL(baseUrl, location.href)).href);
    if (!dataset && src) {
      const url = new URL(src, location.href);
      const index = await (await fetch(url)).json();
      const rows = (index.analyses || []).map((a) => ({ ...(a.row || {}), url: (a.row && a.row.url) || new URL(a.src, url).pathname }));
      dataset = { id: this.id || 'analyses', title: 'Analyses', titleProperty: 'title', linkProperty: 'url', properties: LIST_PROPERTIES, rows };
    }
    // WHY mirrored: a host (or the site's checks) reads which view is open from the list element itself
    this._views.addEventListener('data-views-render', () => { const v = this._views.getAttribute('data-view'); if (v) this.setAttribute('data-view', v); });
    this.replaceChildren(this._views);
    this._views.data = this._pending || dataset || { properties: LIST_PROPERTIES, rows: [] };
    this._views.base = doc;
    this._ready = true;
  }
}

/** The rows of an index.json (data_ui_analysis.build_index), as <data-analyses> builds them. */
export function rowsOf(index) {
  return (index.analyses || []).map((a) => a.row || analysisRow(a.src.replace(/\.md$/, ''), {}));
}

if (typeof customElements !== 'undefined') {
  if (!customElements.get('data-analysis')) customElements.define('data-analysis', DataAnalysis);
  if (!customElements.get('data-analyses')) customElements.define('data-analyses', DataAnalyses);
}
