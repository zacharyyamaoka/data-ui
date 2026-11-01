/* Add to dashboard (docs/CONTRACT.md §34): the pure half, Node-safe. A reader adds a panel from any view of the data to
   a dashboard; it goes to the BOTTOM of that dashboard's layout, to be arranged later.

   Zach, 2026-10-29: "Dashboards are built with data-ui. Humans curate, AI builds." ... "like the amazon thing of adding
   to a saved list" ... "This is a standard feature you can support in data-ui, shouldn't be specific to robotdx."

   WHY the host writes, never data-ui (as host.propose): the .base file is the host's (a repo, a vault, a server); the kit
   hands it the new text and the panel, and says what the host answered. appendPanel is how that text is made, and a
   host may call it itself (on a file it reads its own way, or to put a new dashboard elsewhere).

   WHY lines are only inserted: a dashboard is a file people and agents both edit; its comments, blank lines and the order
   of its blocks are theirs (SPEC §5.1, as replaceViewInText keeps them). A block written in flow style is the one
   exception: YAML has no way to add an entry to `{a: x}` without changing that line, so that block is rewritten in block
   style, its entries as they were. */

import { parseBaseWithLines, parseBase, stringifyBase, yamlScalar, yamlFlow } from './base.js';
import { slug } from './format.js';

const num = (v) => typeof v === 'number' && Number.isFinite(v);
const isQuiet = (s) => s.trim() === '' || s.trim().startsWith('#');
const isComment = (s) => s.trim().startsWith('#');
const indentOf = (s) => /^ */.exec(s)[0].length;
const stem = (path) => decodeSafe(String(path).split(/[?#]/)[0].split('/').pop() || '').replace(/\.[^.]+$/, '');
const decodeSafe = (s) => { try { return decodeURIComponent(s); } catch { return s; } };
const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
// WHY a dummy origin: with no base, two paths compare as paths from one root ('runs.json' and './runs.json' agree)
const NOWHERE = 'http://data-ui.invalid/';

// ------------------------------------------------------------------ filters (the panel's rows, as a Bases filter)

/** A property in an expression: a bare name when it is one, else note["…"] (the grammar's quoted form). */
export const ref = (p) => (/^[A-Za-z_]\w*$/.test(p) ? p : `note[${JSON.stringify(p)}]`);
/** A literal in an expression: numbers and booleans as written, text quoted. */
export const lit = (v) => (typeof v === 'number' || typeof v === 'boolean' ? String(v) : JSON.stringify(String(v)));

/** One filter from several (each a Bases filter: text, {and}, {or}, {not}, or nothing): their AND, nested ands
    flattened, empty parts dropped; undefined when nothing is left. */
export function andFilters(...parts) {
  const out = [];
  const add = (f) => {
    if (f === undefined || f === null || f === '') return;
    if (isMap(f) && Array.isArray(f.and) && Object.keys(f).length === 1) { f.and.forEach(add); return; }
    if (isMap(f) && Object.keys(f).length === 0) return;
    out.push(f);
  };
  parts.forEach(add);
  return out.length === 0 ? undefined : out.length === 1 ? out[0] : { and: out };
}

/** Rows whose `property` is one of `values` (a list cell: contains one of them); an empty list keeps nothing. */
export function inClause(property, values, { list = false } = {}) {
  const vals = [...new Map(values.filter((v) => v !== null && v !== undefined && v !== '').map((v) => [typeof v === 'number' ? `n${v}` : `s${v}`, v])).values()];
  const one = (v) => (list ? `${ref(property)}.contains(${lit(v)})` : `${ref(property)} == ${lit(v)}`);
  if (!vals.length) return 'false';
  return vals.length === 1 ? one(vals[0]) : { or: vals.map(one) };
}

/** The search box's words as a filter: the same rows rowmodel.js' search keeps where every visible property is a
    scalar (`.contains` is case-insensitive on text, as the search is). The caller checks it keeps the same rows (a list
    property searches its joined text, which `.contains` cannot say) and falls back to the rows' ids. */
export function searchClause(query, visible) {
  const q = String(query || '').trim();
  if (!q || !visible.length) return undefined;
  const parts = visible.map((p) => `${ref(p)}.contains(${lit(q)})`);
  return parts.length === 1 ? parts[0] : { or: parts };
}

// ------------------------------------------------------------------ paths

/** `target` as a path from the directory of `base` when both are on one origin ('../data/runs.json'), else the
    absolute URL. A path with no base is returned as written. */
export function relativePath(base, target) {
  let b, t;
  try { b = new URL(base); t = new URL(target, b); } catch { return String(target); }
  if (b.origin !== t.origin || b.protocol !== t.protocol) return t.href;
  const from = b.pathname.split('/').slice(0, -1);
  const to = t.pathname.split('/');
  let i = 0;
  while (i < from.length && i < to.length - 1 && from[i] === to[i]) i++;
  const rest = to.slice(i).map(decodeSafe).join('/');
  return `${'../'.repeat(from.length - i)}${rest}${t.search}${t.hash}`;
}

/** A name not in `taken`: as given, else with a suffix (style `_`: runs_2; style ` (`: Runs (2)). */
export function uniqueName(name, taken, style = '_') {
  const has = (n) => taken.has(n);
  if (!has(name)) return name;
  for (let n = 2; ; n++) {
    const next = style === '_' ? `${name}_${n}` : `${name} (${n})`;
    if (!has(next)) return next;
  }
}

/** A dataset name a link and a URL can carry (`<dataset>.<property>`): letters, digits, `_` and `-`. */
function datasetName(name) {
  return String(name || '').trim().replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'data';
}

// ------------------------------------------------------------------ appendPanel

/** The new text of a dashboard with `panel` added at the bottom of its layout (docs/CONTRACT.md §34).

    panel: {view, dataset: {name, data, label?}, title?, h?, t?, properties?} — what <data-views>.panelSpec() returns:
      view       the view entry (its name may take a suffix here; `from` is set here)
      dataset    the data it reads: `data` the file (absolute, from the site's root, or relative to `base`)
      title      the panel's title (written when it is not the view's name); h its height in rows; t the instant it
                 stands at (seconds; its views read a clock of their own); properties: `properties:` entries for its columns
    options: title — a new dashboard's title (a comment on its first line; only when the text is empty), base — the
      dashboard file's own URL: the file is matched against its datasets and written relative to it.
    Rules: every line of `text` is kept, unchanged and in order (a flow-style block is rewritten in block style); a
    dataset is found by its file (the top level's data: counts), never added twice, and a new one whose name another
    file holds is renamed name_2; a view whose name is taken is renamed "Name (2)"; a panel whose key would be taken
    writes a key of its own; the panel has no w (full width, so it sits below every panel). Throws on a text that is not
    a .base file, never returns a broken one. */
export function appendPanel(text, panel, { title = null, base = null } = {}) {
  if (!panel || !isMap(panel.view)) throw new Error('appendPanel(text, panel): the panel has no view entry (panel.view)');
  const file = panel.dataset && panel.dataset.data;
  if (typeof file !== 'string' || !file) throw new Error('appendPanel(text, panel): the panel names no data file (panel.dataset.data)');
  const raw = text === null || text === undefined ? '' : String(text);
  let parsed;
  try { parsed = parseBaseWithLines(raw); } catch (err) { throw new Error(`the dashboard is not a .base file this kit can read: ${err.message}`); }
  const { doc, lines: at } = parsed;
  if (doc !== null && !isMap(doc)) throw new Error('the dashboard is not a .base file: its top level is not a mapping of keys');
  const d = doc || {};
  for (const [k, ok] of [['views', (v) => Array.isArray(v)], ['layout', isMap], ['datasets', isMap], ['properties', isMap]]) {
    if (d[k] !== undefined && d[k] !== null && !ok(d[k])) throw new Error(`the dashboard's ${k}: is not a ${k === 'views' ? 'list' : 'mapping'}, so nothing can be added to it`);
  }
  if (isMap(d.layout) && d.layout.panels !== undefined && d.layout.panels !== null && !Array.isArray(d.layout.panels)) throw new Error('the dashboard\'s layout.panels is not a list');

  const crlf = /\r\n/.test(raw);
  const eol = crlf ? '\r' : '';
  const src = raw === '' ? [] : raw.split('\n');
  const endsOpen = raw !== '' && !raw.endsWith('\n');
  // the position past the last line (before the empty string a final newline leaves)
  const END = endsOpen || raw === '' ? src.length : src.length - 1;
  const lineAt = (path) => at.get(JSON.stringify(path));
  const edits = []; // {at, seq, lines} insertions before src[at]; {from, to, seq, lines} replace src[from..to]
  const insert = (pos, seq, lines) => edits.push({ at: pos, seq, lines });

  /** The text lines of the node at `path`: [first, last] (0-based; its key line through its last line that is not blank
      or a comment). Its end is the next sibling's line, else its parent's end. */
  const extent = (path) => {
    const first = lineAt(path) - 1;
    const parentPath = path.slice(0, -1);
    const parent = parentPath.reduce((o, k) => (o == null ? o : o[k]), d);
    const keys = Array.isArray(parent) ? parent.map((_, i) => i) : Object.keys(parent);
    const k = keys.indexOf(path[path.length - 1]);
    let stop;
    for (let j = k + 1; j < keys.length; j++) { const l = lineAt([...parentPath, keys[j]]); if (l && l - 1 > first) { stop = l - 1; break; } }
    if (stop === undefined) stop = parentPath.length ? extent(parentPath)[1] + 1 : END;
    let last = stop - 1;
    while (last > first && isQuiet(src[last])) last--;
    return [first, Math.max(first, last)];
  };
  /** Whether the key at `path` writes its value in flow style on its own line ({…} or […]). */
  const flowAt = (path) => {
    const l = lineAt(path);
    if (!l) return false;
    const line = src[l - 1].replace(/\r$/, '');
    const key = String(path[path.length - 1]);
    const i = line.indexOf(':', line.indexOf(key) >= 0 ? line.indexOf(key) + key.length - 1 : 0);
    return i >= 0 && /^\s*[[{]/.test(line.slice(i + 1));
  };
  /** Where a new top-level block goes: before the key `before` names (and the comments right above it), else the end;
      a blank line follows it when the file separates its blocks with one there. */
  const topSpot = (...before) => {
    for (const key of before) {
      const l = lineAt([key]);
      if (!l) continue;
      let pos = l - 1;
      while (pos > 0 && isComment(src[pos - 1])) pos--;
      return { pos, gap: pos > 0 && src[pos - 1].trim() === '' };
    }
    return { pos: END, gap: false };
  };
  const childIndent = (path, fallback) => {
    const v = path.reduce((o, k) => (o == null ? o : o[k]), d);
    const firstKey = Array.isArray(v) ? 0 : isMap(v) ? Object.keys(v)[0] : undefined;
    const l = firstKey === undefined ? null : lineAt([...path, firstKey]);
    return l ? indentOf(src[l - 1]) : fallback;
  };
  const withEol = (lines) => lines.map((l) => l + eol);

  // ---- the dataset: found by its file, else a new entry
  // WHY base made absolute first: a host may pass the dashboard's path from the site's root ('/dash/x.base'), which
  // URL() will not resolve against; on the dummy origin its files still compare as paths
  let home = NOWHERE;
  try { if (base) home = new URL(String(base), NOWHERE).href; } catch { home = NOWHERE; }
  const resolve = (p) => { try { return new URL(String(p), home).href; } catch { return String(p); } };
  const want = resolve(file);
  const datasets = isMap(d.datasets) ? d.datasets : {};
  const fileOf = (entry) => (typeof entry === 'string' ? entry : isMap(entry) ? entry.data : null);
  let defaultName = null;
  if (typeof d.data === 'string') defaultName = Object.keys(datasets).find((k) => fileOf(datasets[k]) === d.data) || stem(d.data);
  let dsName = Object.keys(datasets).find((k) => { const f = fileOf(datasets[k]); return typeof f === 'string' && !/\{[^{}]+\}/.test(f) && resolve(f) === want; });
  if (!dsName && typeof d.data === 'string' && resolve(d.data) === want) dsName = defaultName;
  if (!dsName) {
    const taken = new Set([...Object.keys(datasets), ...(defaultName ? [defaultName] : [])]);
    dsName = uniqueName(datasetName(panel.dataset.name || stem(file)), taken, '_');
    const path = base ? relativePath(home, file) : file;
    const label = panel.dataset.label;
    const entry = `${yamlScalar(dsName)}: ${label ? yamlFlow({ data: path, label }) : yamlScalar(path)}`;
    addEntry('datasets', entry, 1, () => (label ? { data: path, label } : path));
  }

  // ---- properties: entries the dashboard lacks (its own stay as written)
  const props = isMap(panel.properties) ? panel.properties : {};
  const have = isMap(d.properties) ? d.properties : {};
  const missing = Object.entries(props).filter(([p, v]) => !Object.prototype.hasOwnProperty.call(have, p) && isMap(v) && Object.keys(v).length);
  if (missing.length) {
    for (const [p, v] of missing) addEntry('properties', `${yamlScalar(p)}: ${yamlFlow(v)}`, 2, () => v, p);
  }

  /** Add one `key: value` entry to the top-level mapping `block` (datasets, properties): after its last entry, under
      its key when it has none, as a new block when it is absent, by rewriting it when it is written in flow style. */
  function addEntry(block, line, seq, value, key = dsName) {
    const l = lineAt([block]);
    if (!l) {
      const spot = topSpot(...(block === 'datasets' ? ['properties', 'views', 'layout'] : ['views', 'layout']));
      const existing = edits.find((e) => e.block === block);
      if (existing) { existing.lines.splice(existing.lines.length - (existing.gap ? 1 : 0), 0, `  ${line}${eol}`); return; }
      const lines = withEol([`${block}:`, `  ${line}`, ...(spot.gap ? [''] : [])]);
      edits.push({ at: spot.pos, seq, lines, block, gap: spot.gap });
      return;
    }
    if (flowAt([block])) {
      const [first, last] = extent([block]);
      const prior = edits.find((e) => e.block === block && e.from !== undefined);
      const merged = prior ? prior.value : { ...(d[block] || {}) };
      merged[key] = value();
      const lines = withEol([`${block}:`, ...Object.entries(merged).map(([k, v]) => `  ${yamlScalar(k)}: ${typeof v === 'string' ? yamlScalar(v) : yamlFlow(v)}`)]);
      if (prior) { prior.lines = lines; return; }
      edits.push({ from: first, to: last, seq, lines, block, value: merged });
      return;
    }
    const v = d[block];
    const pad = ' '.repeat(childIndent([block], indentOf(src[l - 1]) + 2));
    const after = isMap(v) && Object.keys(v).length ? extent([block])[1] : l - 1;
    const existing = edits.find((e) => e.block === block && e.at === after + 1);
    if (existing) { existing.lines.push(`${pad}${line}${eol}`); return; }
    edits.push({ at: after + 1, seq, lines: [`${pad}${line}${eol}`], block });
  }

  // ---- the view: a name of its own, reading the dataset
  const views = Array.isArray(d.views) ? d.views : [];
  const names = new Set(views.map((v) => (isMap(v) ? v.name : null)).filter((n) => typeof n === 'string'));
  const name = uniqueName(String(panel.view.name || panel.title || 'View'), names, ' (');
  const { type, name: _n, from: _f, ...rest } = panel.view;
  const entry = { type: type || 'table', name, from: dsName, ...rest };
  for (const k of Object.keys(entry)) if (entry[k] === undefined) delete entry[k];
  const item = stringifyBase([entry], 'views').replace(/\n$/, '').split('\n');
  if (!lineAt(['views'])) {
    const spot = topSpot('layout');
    insert(spot.pos, 3, withEol(['views:', ...item.map((x) => `  ${x}`), ...(spot.gap ? [''] : [])]));
  } else if (flowAt(['views'])) {
    const [first, last] = extent(['views']);
    const all = stringifyBase({ views: [...views, entry] }).replace(/\n$/, '').split('\n');
    edits.push({ from: first, to: last, seq: 3, lines: withEol(all) });
  } else if (views.length) {
    const dash = indentOf(src[lineAt(['views', 0]) - 1]);
    insert(extent(['views'])[1] + 1, 3, withEol(item.map((x) => ' '.repeat(dash) + x)));
  } else {
    const l = lineAt(['views']);
    insert(l, 3, withEol(item.map((x) => ' '.repeat(indentOf(src[l - 1]) + 2) + x)));
  }

  // ---- the panel: at the bottom, full width, a key of its own when its derived one is taken
  const layout = isMap(d.layout) ? d.layout : null;
  const panels = layout && Array.isArray(layout.panels) ? layout.panels : [];
  const keys = new Set();
  panels.forEach((p, i) => {
    if (!isMap(p)) return;
    const listed = p.views || (p.view ? [p.view] : []);
    if (!listed.length && typeof p.text !== 'string') return;
    let k = slug(p.key || p.title || listed[0] || `text-${i + 1}`) || `panel-${i + 1}`;
    while (keys.has(k)) k += '-2';
    keys.add(k);
  });
  const ptitle = panel.title && String(panel.title) !== name ? String(panel.title) : null;
  const pentry = { view: name };
  if (ptitle) pentry.title = ptitle;
  if (num(panel.h) && panel.h >= 1) pentry.h = panel.h;
  if (num(panel.t)) pentry.t = panel.t;
  const derived = slug(ptitle || name) || 'panel';
  if (keys.has(derived)) { let n = 2; while (keys.has(`${derived}-${n}`)) n++; pentry.key = `${derived}-${n}`; }
  const pline = yamlFlow(pentry);
  if (!lineAt(['layout'])) {
    insert(END, 4, withEol(['layout:', '  panels:', `    - ${pline}`]));
  } else if (flowAt(['layout'])) {
    const [first, last] = extent(['layout']);
    const lines = ['layout:'];
    for (const [k, v] of Object.entries({ ...(layout || {}), panels: [...panels, pentry] })) {
      if (k === 'panels') { lines.push('  panels:'); for (const p of v) lines.push(`    - ${yamlFlow(p)}`); }
      else lines.push(`  ${yamlScalar(k)}: ${yamlFlow(v)}`);
    }
    edits.push({ from: first, to: last, seq: 4, lines: withEol(lines) });
  } else if (!layout) {
    const l = lineAt(['layout']);
    insert(l, 4, withEol(['  panels:', `    - ${pline}`].map((x) => ' '.repeat(indentOf(src[l - 1])) + x)));
  } else if (!lineAt(['layout', 'panels'])) {
    const pad = ' '.repeat(childIndent(['layout'], indentOf(src[lineAt(['layout']) - 1]) + 2));
    insert(extent(['layout'])[1] + 1, 4, withEol([`${pad}panels:`, `${pad}  - ${pline}`]));
  } else if (flowAt(['layout', 'panels'])) {
    const [first, last] = extent(['layout', 'panels']);
    const pad = ' '.repeat(indentOf(src[first]));
    edits.push({ from: first, to: last, seq: 4, lines: withEol([`${pad}panels:`, ...[...panels, pentry].map((p) => `${pad}  - ${yamlFlow(p)}`)]) });
  } else if (panels.length) {
    const dash = indentOf(src[lineAt(['layout', 'panels', 0]) - 1]);
    insert(extent(['layout', 'panels'])[1] + 1, 4, withEol([`${' '.repeat(dash)}- ${pline}`]));
  } else {
    const l = lineAt(['layout', 'panels']);
    insert(l, 4, withEol([`${' '.repeat(indentOf(src[l - 1]) + 2)}- ${pline}`]));
  }

  // ---- a new dashboard's title: a comment on its first line
  if (doc === null && title) insert(0, 0, withEol([`# ${String(title).replace(/[\r\n]+/g, ' ').trim()}`]));

  // ---- apply: insertions before src[at] in their order, replacements in place
  const before = new Map();
  const replaced = new Map();
  for (const e of edits) {
    if (e.from !== undefined) { replaced.set(e.from, e); continue; }
    if (!before.has(e.at)) before.set(e.at, []);
    before.get(e.at).push(e);
  }
  const out = [];
  const emit = (pos) => { for (const e of (before.get(pos) || []).sort((a, b) => a.seq - b.seq)) out.push(...e.lines); };
  for (let i = 0; i < src.length; i++) {
    emit(i);
    const r = replaced.get(i);
    if (r) { out.push(...r.lines); i = r.to; continue; }
    out.push(src[i]);
  }
  emit(src.length);
  if (raw === '' || (!endsOpen && !src.length)) out.push('');
  const result = out.join('\n');

  // never hand out a broken file: the result must read, and its last panel must be this view on this dataset
  let check;
  try { check = parseBase(result); } catch (err) { throw new Error(`appendPanel wrote text it cannot read back (${err.message}); nothing was added`); }
  const last = check && check.layout && Array.isArray(check.layout.panels) ? check.layout.panels[check.layout.panels.length - 1] : null;
  const view = check && Array.isArray(check.views) ? check.views.find((v) => v && v.name === name) : null;
  if (!last || last.view !== name || !view || view.from !== dsName) throw new Error('appendPanel could not place the panel at the bottom of the layout; nothing was added');
  return result;
}
