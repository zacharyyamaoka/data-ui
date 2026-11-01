/* Dashboard edits as small changes to the .base text. Pure and Node-safe: every control of the editor ends here, on the
   canvas, in the outline or in the options pane, so a move, a resize, a rename or a new view type is the same minimal
   edit whichever side made it.

   WHY text, never a re-dump: a dashboard is a file people and agents both edit ("Humans curate, AI builds", Zach
   2026-10-29). Its comments, blank lines and the order of its blocks are theirs (SPEC §5.1, as appendPanel and
   replaceViewInText keep them, CONTRACT §34). An entry that moves or goes takes its own lines, with the comments right
   above it; a value that changes goes through yaml.js's patchAt, which touches only the tokens that differ. A list
   written in flow style is the one exception, rewritten in block style (YAML cannot edit `[a, b]` in place), as
   appendPanel's flow blocks are. */

import { parseBaseWithLines, parseBase, stringifyBase, yamlFlow } from '../../../core/src/base.js';
import { appendPanel } from '../../../core/src/add-to-dashboard.js';
import { slug } from '../../../core/src/format.js';
import { readDashboard } from '../model.js';
import { patchAt, NoPlace } from './yaml.js';

const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const indentOf = (s) => /^ */.exec(s)[0].length;
const isBlank = (s) => s.trim() === '';
const isComment = (s) => s.trim().startsWith('#');
const isQuiet = (s) => isBlank(s) || isComment(s);
const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const at = (doc, path) => path.reduce((o, k) => (o == null ? o : o[k]), doc);

// ------------------------------------------------------------------ the text of one block sequence, item by item

/** The items of the block sequence at `path` as line chunks. Each item runs from the comment lines right above its
    `- ` line (they move and go with it) to its last line (continuation lines indented past the dash); blank lines
    between items stay with the item below them. Returns {src, eol, items: [{from, head, to, value}], start, end,
    dash, flow} (0-based line numbers; start..end is every line the items take), or null when the path is no list. */
export function sequence(text, path) {
  const raw = String(text);
  const eol = /\r\n/.test(raw) ? '\r\n' : '\n';
  const src = raw.replace(/\r\n?/g, '\n').split('\n');
  const { doc, lines } = parseBaseWithLines(raw);
  const seq = at(doc, path);
  if (!Array.isArray(seq)) return null;
  const line = (p) => { const l = lines.get(JSON.stringify(p)); return l ? l - 1 : -1; };
  // the top-level block the list lives in (layout: for layout.panels), and its last line
  const top = line([path[0]]);
  let topEnd = top;
  for (let n = top + 1; n < src.length; n++) {
    if (isQuiet(src[n])) continue;
    if (indentOf(src[n]) <= indentOf(src[top])) break;
    topEnd = n;
  }
  const keyLine = line(path);
  const heads = seq.map((_, i) => line([...path, i]));
  // flow style anywhere on the way (`panels: [ … ]`, `layout: { panels: [ … ] }`): every item on a key's own line or
  // inside its brackets
  const flow = keyLine < 0 || /:\s*[[{]/.test(src[top].replace(/#.*$/, '')) || (!seq.length ? /:\s*\[/.test(src[keyLine] || '')
    : heads.some((h, i) => h < 0 || h <= keyLine || (i && h <= heads[i - 1]) || !/^\s*-(\s|$)/.test(src[h])));
  if (flow) return { src, eol, items: [], start: top, end: topEnd, dash: 2, flow: true, keyLine, top, topEnd, path, doc, value: seq };
  const dash = seq.length ? indentOf(src[heads[0]]) : indentOf(src[keyLine]) + 2;
  const items = [];
  for (let i = 0; i < seq.length; i++) {
    const head = heads[i];
    let from = head;
    while (from - 1 > (i ? heads[i - 1] : keyLine) && isComment(src[from - 1]) && indentOf(src[from - 1]) >= dash) from--;
    // a blank run between two items belongs to the one below it (it moves with it)
    if (i) while (from - 1 > heads[i - 1] && isBlank(src[from - 1])) from--;
    let to = head;
    const limit = i + 1 < seq.length ? heads[i + 1] : src.length;
    for (let n = head + 1; n < limit; n++) {
      if (isQuiet(src[n])) continue;
      if (indentOf(src[n]) <= dash) break;
      to = n;
    }
    items.push({ from, head, to, value: seq[i] });
  }
  // an item's chunk ends where the next one's starts: comments and blanks it owns end on its last line
  for (let i = 0; i + 1 < items.length; i++) items[i].to = Math.min(Math.max(items[i].to, items[i].head), items[i + 1].from - 1);
  return { src, eol, items, start: items.length ? items[0].from : keyLine + 1, end: items.length ? items[items.length - 1].to : keyLine, dash, flow: false, keyLine, top, topEnd, path, doc, value: seq };
}

/** A flow-style list's whole top-level block, written in block style with the list's new items (the one exception to
    editing in place, as appendPanel's): `views:` one view per block, a layout's keys one per line, panels in flow. */
function blockOf(s, next, style) {
  const [k0, k1] = s.path;
  const item = (v, pad) => (style === 'views'
    ? stringifyBase([v], 'views').replace(/\n$/, '').split('\n').map((x) => pad + x)
    : [`${pad}- ${yamlFlow(v)}`]);
  if (s.path.length === 1) return next.length ? [`${k0}:`, ...next.flatMap((v) => item(v, '  '))] : [`${k0}: []`];
  const out = [`${k0}:`];
  const parent = s.doc[k0] || {};
  const keys = Object.keys(parent).includes(k1) ? Object.keys(parent) : [...Object.keys(parent), k1];
  for (const k of keys) {
    if (k !== k1) { out.push(`  ${k}: ${yamlFlow(parent[k])}`); continue; }
    if (!next.length) out.push(`  ${k1}: []`);
    else out.push(`  ${k1}:`, ...next.flatMap((v) => item(v, '    ')));
  }
  return out;
}

/** One item's lines, new: a one-line flow entry stays one line (its trailing comment kept), a block entry is written as a
    block at the same dash, its comments above kept. */
function itemLines(s, item, value) {
  const pad = ' '.repeat(s.dash);
  const lead = s.src.slice(item.from, item.head);
  const head = s.src[item.head];
  const oneLine = item.to === item.head && /^\s*-\s*\{.*\}\s*(#.*)?$/.test(head);
  if (oneLine) {
    const note = /\}\s*(#.*)$/.exec(head);
    return [...lead, `${pad}- ${yamlFlow(value)}${note ? ` ${note[1]}` : ''}`];
  }
  const body = stringifyBase([value], 'panels').replace(/\n$/, '').split('\n').map((x) => pad + x);
  return [...lead, ...body];
}

/** The text with the sequence's items replaced by `next`: [{item?: original chunk, value}] in the new order (an entry
    with `item` and an unchanged value keeps its lines byte for byte). */
function rewrite(s, next) {
  if (s.flow) return [...s.src.slice(0, s.top), ...blockOf(s, next.map((n) => n.value), 'panels'), ...s.src.slice(s.topEnd + 1)].join(s.eol);
  const body = [];
  for (const n of next) {
    if (n.item && JSON.stringify(n.item.value) === JSON.stringify(n.value)) body.push(...s.src.slice(n.item.from, n.item.to + 1));
    else if (n.item) body.push(...itemLines(s, n.item, n.value));
    else body.push(...stringifyBase([n.value], 'panels').replace(/\n$/, '').split('\n').map((x) => ' '.repeat(s.dash) + x));
  }
  if (!next.length) {
    // an empty list is written `key: []` (a bare `key:` reads as null, which the schema refuses)
    const key = s.src[s.keyLine].replace(/:\s*$/, ': []');
    return [...s.src.slice(0, s.keyLine), key, ...s.src.slice(s.end + 1)].join(s.eol);
  }
  return [...s.src.slice(0, s.start), ...body, ...s.src.slice(s.end + 1)].join(s.eol);
}

/** Read the result back before handing it out: a broken file is never returned (appendPanel's rule). */
function readBack(text, what) {
  try { parseBase(text); } catch (err) { throw new Error(`${what} wrote text it cannot read back (${err.message}); nothing was changed`); }
  return text;
}

/** `text` with the value at `path` changed, by the smallest patch the text allows (yaml.js), else null. */
function patched(text, path, value) {
  try { return patchAt(text, path, value); } catch (err) { if (err instanceof NoPlace) return null; throw err; }
}

// ------------------------------------------------------------------ the layout's panels

/** The layout's panels as the dashboard reads them, in the file's order, each with its index in `layout.panels` (`i`), its
    entry as written and `hidden`. Text panels are listed too. */
export function panelsOf(text) {
  const base = parseBase(text) || {};
  const dash = readDashboard(base);
  const raw = (base.layout && Array.isArray(base.layout.panels)) ? base.layout.panels : [];
  const all = [...dash.panels.map((p) => ({ ...p, hidden: false })), ...dash.hidden.map((p) => ({ ...p, hidden: true }))].sort((a, b) => a.i - b.i);
  return all.map((p) => ({ ...p, entry: raw[p.i], name: p.title || (p.views[0] && p.views[0].name) || (p.text !== null ? 'Text' : p.key) }));
}

function layoutSeq(text) {
  const s = sequence(text, ['layout', 'panels']);
  if (!s) throw new Error('the dashboard has no layout.panels list to edit');
  return s;
}

/** Move layout.panels[from] to position `to` (0-based, in the list without it). */
export function movePanel(text, from, to) {
  const s = layoutSeq(text);
  const list = s.value.map((value, i) => ({ item: s.items[i], value }));
  if (from < 0 || from >= list.length) throw new Error(`no panel ${from} to move`);
  const [one] = list.splice(from, 1);
  list.splice(Math.max(0, Math.min(list.length, to)), 0, one);
  return readBack(rewrite(s, list), 'movePanel');
}

/** Put layout.panels in `order` (a permutation of their indices). */
export function orderPanels(text, order) {
  const s = layoutSeq(text);
  if (order.length !== s.value.length || new Set(order).size !== order.length) throw new Error('orderPanels: the order must name every panel once');
  return readBack(rewrite(s, order.map((i) => ({ item: s.items[i], value: s.value[i] }))), 'orderPanels');
}

/** Change keys of layout.panels[i]: `patch` sets each key (undefined or null removes it), new keys go last. */
export function updatePanel(text, i, patch) {
  const s = layoutSeq(text);
  if (i < 0 || i >= s.value.length) throw new Error(`no panel ${i} to change`);
  const value = { ...s.value[i] };
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined || v === null) delete value[k];
    else value[k] = v;
  }
  const out = patched(text, ['layout', 'panels', i], value);
  if (out !== null) return readBack(out, 'updatePanel');
  return readBack(rewrite(s, s.value.map((v, n) => ({ item: s.items[n], value: n === i ? value : v }))), 'updatePanel');
}

/** A panel's size: w columns (null: full width, the default) and h rows (null: its content's height). */
export function resizePanel(text, i, { w, h } = {}) {
  const patch = {};
  if (w !== undefined) patch.w = w === null ? undefined : Math.max(1, Math.round(w));
  if (h !== undefined) patch.h = h === null ? undefined : Math.max(1, Math.round(h));
  return updatePanel(text, i, patch);
}

/** A panel's title. WHY the key is pinned: a panel's URL state (selections, its tab, its hidden series) and a reader's
    arrangement are keyed by its derived key (its title's slug), so a rename writes the key it had (CONTRACT §34 writes a
    key of its own for the same reason). A title equal to the view's name is dropped (the default). */
export function renamePanel(text, i, title) {
  const p = panelsOf(text).find((x) => x.i === i);
  if (!p) throw new Error(`no panel ${i} to rename`);
  const clean = String(title || '').replace(/[\r\n]+/g, ' ').trim();
  const viewName = p.views[0] && p.views[0].name;
  const patch = { title: clean && clean !== viewName ? clean : undefined };
  const derived = slug(clean || viewName || '');
  if (!p.entry.key && derived !== p.key) patch.key = p.key;
  return updatePanel(text, i, patch);
}

/** Hide a panel (or show it again): one key on its entry, which stays where it is, with its size and its comments.
    Shopify's JSON templates keep a hidden section the same way: `disabled: true`, not rendered, still there. */
export function hidePanel(text, i, on = true) { return updatePanel(text, i, { hidden: on ? true : undefined }); }

/** The views a layout entry names. */
const namesOf = (entry) => (isMap(entry) ? (entry.views || (entry.view ? [entry.view] : [])) : []);

/** Take layout.panels[i] off the dashboard, with the comments right above it. Its views go too (`dropViews`, the default)
    when no other panel names them. */
export function removePanel(text, i, { dropViews = true } = {}) {
  const s = layoutSeq(text);
  if (i < 0 || i >= s.value.length) throw new Error(`no panel ${i} to remove`);
  const gone = namesOf(s.value[i]);
  const list = s.value.map((value, n) => ({ item: s.items[n], value })).filter((_, n) => n !== i);
  let out = readBack(rewrite(s, list), 'removePanel');
  if (dropViews) {
    const still = new Set(list.flatMap((n) => namesOf(n.value)));
    for (const name of gone) if (!still.has(name)) out = removeView(out, name);
  }
  return out;
}

/** Add a layout entry that names no new view (a text panel) at `at` (default the bottom). */
export function insertPanel(text, entry, at = null) {
  const s = layoutSeq(text);
  const list = s.value.map((value, n) => ({ item: s.items[n], value }));
  list.splice(at === null ? list.length : Math.max(0, Math.min(list.length, at)), 0, { value: entry });
  return readBack(rewrite(s, list), 'insertPanel');
}

/** A text panel's markdown. */
export function setPanelText(text, i, md) { return updatePanel(text, i, { text: String(md) }); }

/** Make layout.panels[from]'s views tabs of layout.panels[into] (the views of one panel read one dataset). The entry of
    `into` changes in place; a comment right above `from` moves up to it. */
export function groupPanels(text, from, into) {
  const s = layoutSeq(text);
  const a = s.value[from], b = s.value[into];
  if (!isMap(a) || !isMap(b) || from === into || !namesOf(a).length || !namesOf(b).length) throw new Error('groupPanels: two different panels with views');
  const doc = s.doc;
  const ds = (n) => { const v = (doc.views || []).find((x) => x && x.name === n); return (v && v.from) || null; };
  const names = [...namesOf(b), ...namesOf(a).filter((n) => !namesOf(b).includes(n))];
  if (new Set(names.map(ds)).size > 1) throw new Error('the views of one panel read one dataset');
  const merged = { ...b, views: names };
  delete merged.view;
  // the absorbed entry first (its line numbers are read before the other changes): it goes, its own comments with the group
  const lead = s.flow ? [] : s.src.slice(s.items[from].from, s.items[from].head).filter(isComment);
  const list = s.value.map((value, n) => ({ item: s.items[n], value })).filter((_, n) => n !== from);
  const without = readBack(rewrite(s, list), 'groupPanels');
  const at = from < into ? into - 1 : into;
  let out = updatePanel(without, at, { view: undefined, views: merged.views });
  if (lead.length) {
    const t = layoutSeq(out);
    const lines = [...t.src.slice(0, t.items[at].head), ...lead, ...t.src.slice(t.items[at].head)];
    out = lines.join(t.eol);
  }
  return readBack(out, 'groupPanels');
}

/** Take the tab `name` out of the panel at layout.panels[i]: it becomes a panel of its own right after, the same size. */
export function ungroupPanel(text, i, name) {
  const s = layoutSeq(text);
  const e = s.value[i];
  const left = namesOf(e).filter((n) => n !== name);
  if (!isMap(e) || !Array.isArray(e.views) || left.length === e.views.length || !left.length) throw new Error(`panel ${i} has no tab ${name} to take out`);
  const out = updatePanel(text, i, left.length === 1 ? { views: undefined, view: left[0] } : { views: left });
  const entry = { view: name };
  if (e.w !== undefined) entry.w = e.w;
  if (e.h !== undefined) entry.h = e.h;
  return insertPanel(out, entry, i + 1);
}

/** Add a panel (appendPanel's spec: {view, dataset: {name, data, label?}, title?, h?, t?, properties?}), then place it at
    `at` (an index in layout.panels; default the bottom) and give it `w`/`h`. `base`: the dashboard file's URL. */
export function addPanel(text, spec, { base = null, at = null, w, h } = {}) {
  let out = appendPanel(text, spec, { base });
  const n = parseBase(out).layout.panels.length;
  if (w !== undefined || h !== undefined) out = resizePanel(out, n - 1, { w, h });
  if (at !== null && at < n - 1) out = movePanel(out, n - 1, at);
  return out;
}

/** The panel at layout index i as appendPanel's spec, to add it to another dashboard: its first view, its dataset's
    file resolved against `base` (the file's own URL), its title and height. */
export function panelSpec(text, i, { base = null } = {}) {
  const doc = parseBase(text) || {};
  const dash = readDashboard(doc);
  const p = [...dash.panels, ...dash.hidden].find((x) => x.i === i);
  if (!p || !p.views.length) throw new Error(`panel ${i} has no view to add elsewhere`);
  const view = clone(p.views[0]);
  const d = dash.datasets[p.dataset];
  let data = d ? d.data : null;
  if (data && base) { try { data = new URL(data, base).href; } catch { /* as written */ } }
  delete view.from;
  return { kind: 'view', title: p.title || view.name, view, dataset: { name: p.dataset, data, label: d && d.label ? d.label : undefined }, h: p.h || undefined };
}

/** The text with its visible panels in `order` (grid nodes in reading order, [{key, w, h}]) and the sizes the reader
    changed: a panel whose w and h are what the grid gave it (`was`, {key: {w, h}}) keeps its entry as written, so no w or
    h appears that the file did not have. A hidden entry keeps its slot in the list. */
export function arrangeText(text, order, was) {
  const before = panelsOf(text);
  const byKey = new Map(before.map((p) => [p.key, p]));
  const seen = order.map((n) => byKey.get(n.key)).filter(Boolean);
  const shown = [...seen, ...before.filter((p) => !p.hidden && !seen.includes(p))];
  const slots = new Set(shown.map((p) => p.i));
  let next = 0;
  const placed = parseBase(text).layout.panels.map((_, i) => (slots.has(i) ? shown[next++].i : i));
  let out = placed.some((v, i) => v !== i) ? orderPanels(text, placed) : text;
  for (const n of order) {
    const p = byKey.get(n.key);
    const size = was[n.key];
    if (!p || !size) continue;
    const patch = {};
    if (n.w !== size.w) patch.w = n.w;
    if (n.h !== size.h && p.text === null) patch.h = n.h;
    if (!Object.keys(patch).length) continue;
    out = resizePanel(out, placed.indexOf(p.i), patch);
  }
  return out;
}

/** Does `b` differ from `a` only in the order and the sizes of its panels? Then nothing needs drawing again. WHY the keys
    too: a note's key is its place in the list, so moving one renames a panel. */
export function layoutOnly(a, b) {
  const read = (t) => {
    const doc = { ...(parseBase(t) || {}) };
    const panels = Object.fromEntries(panelsOf(t).map((p) => { const { w, h, ...rest } = p.entry; return [p.key, rest]; }));
    doc.layout = { ...(doc.layout || {}), panels: Object.keys(panels).sort().map((k) => [k, panels[k]]) };
    return JSON.stringify(doc);
  };
  try { return read(a) === read(b); } catch { return false; }
}

// ------------------------------------------------------------------ views

/** The views: list as line chunks (sequence) plus the index of the view named `name`. */
function viewAt(text, name) {
  const s = sequence(text, ['views']);
  if (!s) throw new Error('the dashboard has no views: list');
  const i = s.value.findIndex((v) => isMap(v) && v.name === name);
  if (i < 0) throw new Error(`no view named ${name}`);
  return { s, i };
}

/** The view named `name` becomes fn(a copy of it): only the keys that differ change, its comments stay. */
export function updateView(text, name, fn) {
  const { s, i } = viewAt(text, name);
  const next = fn(clone(s.value[i]));
  const out = patched(text, ['views', i], next);
  if (out !== null) return readBack(out, 'updateView');
  const list = s.value.map((value, n) => ({ item: s.items[n], value: n === i ? next : value }));
  // WHY 'views' style: one key per line, as the house style writes views (stringifyBase's BLOCK_KEYS)
  return readBack(rewriteViews(s, list), 'updateView');
}

function rewriteViews(s, next) {
  if (s.flow) return [...s.src.slice(0, s.top), ...blockOf(s, next.map((n) => n.value), 'views'), ...s.src.slice(s.topEnd + 1)].join(s.eol);
  const body = [];
  for (const n of next) {
    if (n.item && JSON.stringify(n.item.value) === JSON.stringify(n.value)) body.push(...s.src.slice(n.item.from, n.item.to + 1));
    else {
      const lead = n.item ? s.src.slice(n.item.from, n.item.head) : [];
      body.push(...lead, ...stringifyBase([n.value], 'views').replace(/\n$/, '').split('\n').map((x) => ' '.repeat(s.dash) + x));
    }
  }
  if (!next.length) return [...s.src.slice(0, s.keyLine), s.src[s.keyLine].replace(/:\s*$/, ': []'), ...s.src.slice(s.end + 1)].join(s.eol);
  return [...s.src.slice(0, s.start), ...body, ...s.src.slice(s.end + 1)].join(s.eol);
}

/** Remove the view named `name` from views: (its comments above go with it). */
export function removeView(text, name) {
  const { s, i } = viewAt(text, name);
  const list = s.value.map((value, n) => ({ item: s.items[n], value })).filter((_, n) => n !== i);
  return readBack(rewriteViews(s, list), 'removeView');
}

// ------------------------------------------------------------------ what a panel shows: its view type and its signal

/** The view types a panel can switch between, in a stable order (the current one is marked by the caller): a view of rows
    over time (its dataset has a time column t, or it is a time series) may be a time series, a chart, a table or a KPI;
    other rows a table, a list, a chart or a KPI. With no number column there is nothing to plot. A type this file has no
    conversion for (a 3D scene, a video, the playback bar) offers only itself: what cannot be drawn is never offered. */
export const TYPE_NAMES = { timeseries: 'Time series', chart: 'Chart', table: 'Table', kpi: 'KPI', list: 'List' };
export function typesFor(view, columns = null) {
  const t = (view && view.type) || 'table';
  if (!OWN[t]) return [t];
  const numbers = !columns || columns.numbers.length > 0;
  const timed = t === 'timeseries' || (columns && columns.numbers.includes('t'));
  const list = (timed ? ['timeseries', 'chart', 'table', 'kpi'] : ['table', 'list', 'chart', 'kpi']).filter((x) => numbers || x === 'table' || x === 'list');
  return list.includes(t) ? list : [t, ...list];
}

/** The numeric and the text columns of a dataset ({properties} as the kit normalises it, or a schema's fields). */
export function columnsOf(dataset) {
  const props = (dataset && dataset.properties) || {};
  const out = { numbers: [], texts: [], labels: {} };
  for (const [name, p] of Object.entries(props)) {
    const type = p && (p.type || p.kind);
    out.labels[name] = (p && (p.label || p.title || p.displayName)) || name;
    if (type === 'number' || type === 'integer') out.numbers.push(name);
    else if (type === 'text' || type === 'string' || type === 'select') out.texts.push(name);
  }
  return out;
}

/** The signal a view plots: a time series' y, a chart's y field, a KPI's value property. */
export function signalOf(view) {
  if (!view) return null;
  if (view.type === 'timeseries') { const y = view.timeseries && view.timeseries.y; return Array.isArray(y) ? y[0] : y || null; }
  if (view.type === 'chart') return (view.chart && view.chart.encoding && view.chart.encoding.y && view.chart.encoding.y.field) || null;
  if (view.type === 'kpi') return (view.kpi && view.kpi.value && view.kpi.value.property) || null;
  return null;
}

/** The columns a view can plot, what it plots now among them, first when it is no number column (a KPI that counts runs). */
export function signalChoices(columns, signal) {
  const numbers = columns.numbers.filter((c) => c !== 't');
  return signal === null || numbers.includes(signal) ? numbers : [signal, ...numbers];
}

/** Plot `y` instead (a time series, a chart or a KPI). */
export function setSignal(text, name, y) {
  return updateView(text, name, (v) => {
    if (v.type === 'timeseries') v.timeseries = { ...(v.timeseries || {}), y };
    else if (v.type === 'chart') { v.chart = v.chart || {}; v.chart.encoding = v.chart.encoding || {}; v.chart.encoding.y = { ...(v.chart.encoding.y || {}), field: y }; }
    else if (v.type === 'kpi') { v.kpi = v.kpi || {}; v.kpi.value = { ...(v.kpi.value || {}), property: y }; }
    else throw new Error(`a ${v.type} view plots no single signal`);
    return v;
  });
}

const OWN = { timeseries: ['timeseries'], chart: ['chart'], kpi: ['kpi'], table: ['order', 'sort'], list: ['order'] };

/** The view as another type, carrying what it plots: a time series' x / y / series become a chart's encoding or a
    table's columns, and back. `stash` holds what a type left behind ({`<name>:<type>`: keys}), so switching back
    restores it exactly (Grafana keeps a panel's options per visualization the same way). */
export function convertView(view, type, { columns = null, stash = {} } = {}) {
  const from = view.type || 'table';
  if (from === type) return { view, stash };
  const keep = {};
  for (const k of OWN[from] || []) if (view[k] !== undefined) keep[k] = view[k];
  const nextStash = { ...stash, [`${view.name}:${from}`]: keep };
  const out = {};
  for (const [k, v] of Object.entries(view)) if (!(OWN[from] || []).includes(k)) out[k] = v;
  out.type = type;
  const back = stash[`${view.name}:${type}`];
  // what the view plots now, in the old type's words
  const ts = from === 'timeseries' ? view.timeseries || {} : null;
  const enc = from === 'chart' ? (view.chart && view.chart.encoding) || {} : null;
  const x = ts ? ts.x : enc ? enc.x && enc.x.field : null;
  const y = signalOf(view) || (columns && columns.numbers.find((c) => c !== 't' && c !== x)) || null;
  const series = ts ? ts.series : enc ? enc.color && enc.color.field : null;
  if (back) Object.assign(out, clone(back));
  else if (type === 'table') {
    const order = [x, series, y].filter(Boolean);
    if (order.length) out.order = [...new Set(order)];
    if (x) out.sort = [{ property: x, direction: 'ASC' }];
  } else if (type === 'chart') {
    const encoding = {};
    if (x || (columns && columns.numbers.includes('t'))) encoding.x = { field: x || 't', type: 'quantitative' };
    else if (columns && columns.texts.length) encoding.x = { field: columns.texts[0], type: 'nominal' };
    if (y) encoding.y = { field: y, type: 'quantitative' };
    if (series) encoding.color = { field: series, type: 'nominal' };
    out.chart = { mark: x || series ? 'line' : 'bar', encoding };
  } else if (type === 'timeseries') {
    const tx = x || (columns && (columns.numbers.includes('t') ? 't' : columns.numbers[0])) || 't';
    out.timeseries = { x: tx, y: y || (columns && columns.numbers.find((c) => c !== tx)) || 'value' };
    if (series) out.timeseries.series = series;
  } else if (type === 'kpi') {
    out.kpi = { label: view.name, value: { property: y || (columns && columns.numbers[0]) || null, summary: 'Median' } };
  }
  return { view: out, stash: nextStash };
}

/** Show the view named `name` as `type`; returns {text, stash}. */
export function setViewType(text, name, type, opts = {}) {
  let stash = opts.stash || {};
  const out = updateView(text, name, (v) => { const r = convertView(v, type, { ...opts, stash }); stash = r.stash; return r.view; });
  return { text: out, stash };
}

// ------------------------------------------------------------------ what changed: a line diff and the human summary

/** A line diff (LCS): [{op: ' ' | '-' | '+', line, a, b}] with a / b the 1-based line in each text (null where absent). */
export function lineDiff(before, after) {
  const a = String(before).replace(/\r\n?/g, '\n').split('\n');
  const b = String(after).replace(/\r\n?/g, '\n').split('\n');
  // trim the common head and tail, so the table is only the middle
  let lo = 0;
  while (lo < a.length && lo < b.length && a[lo] === b[lo]) lo++;
  let ha = a.length, hb = b.length;
  while (ha > lo && hb > lo && a[ha - 1] === b[hb - 1]) { ha--; hb--; }
  const A = a.slice(lo, ha), B = b.slice(lo, hb);
  const L = Array.from({ length: A.length + 1 }, () => new Int32Array(B.length + 1));
  for (let i = A.length - 1; i >= 0; i--) for (let j = B.length - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  for (let i = 0; i < lo; i++) out.push({ op: ' ', line: a[i], a: i + 1, b: i + 1 });
  let i = 0, j = 0;
  while (i < A.length || j < B.length) {
    if (i < A.length && j < B.length && A[i] === B[j]) { out.push({ op: ' ', line: A[i], a: lo + i + 1, b: lo + j + 1 }); i++; j++; }
    else if (i < A.length && (j >= B.length || L[i + 1][j] >= L[i][j + 1])) { out.push({ op: '-', line: A[i], a: lo + i + 1, b: null }); i++; }
    else { out.push({ op: '+', line: B[j], a: null, b: lo + j + 1 }); j++; }
  }
  for (let k = 0; k < a.length - ha; k++) out.push({ op: ' ', line: a[ha + k], a: ha + k + 1, b: hb + k + 1 });
  return out;
}

/** The diff's changed lines with `context` lines around each change (hunks), for a compact review. */
export function hunks(diff, context = 2) {
  const keep = new Set();
  diff.forEach((d, i) => { if (d.op !== ' ') for (let k = i - context; k <= i + context; k++) keep.add(k); });
  const out = [];
  let last = -2;
  diff.forEach((d, i) => {
    if (!keep.has(i)) return;
    if (i !== last + 1 && out.length) out.push({ op: '…' });
    out.push(d);
    last = i;
  });
  return out;
}

/** Who a panel is across two texts: its first view's name (view names are unique in a file), else its text. */
export const identity = (p) => (p.views.length ? `v:${p.views[0].name}` : `t:${p.text}`);

/** What changed between two texts of one dashboard, in the reader's words: [{kind, id, key, label, detail}], kind one of
    added, removed, moved, resized, renamed, retyped, signal, text, settings, hidden, shown, grouped, ungrouped. */
export function changeList(before, after) {
  let a, b;
  try { a = panelsOf(before); b = panelsOf(after); } catch { return []; }
  const label = (p) => p.title || (p.views[0] && p.views[0].name) || 'the text';
  const textLabel = (p) => (p.text !== null ? `the note “${String(p.text).replace(/[*_`#]/g, '').slice(0, 28).trim()}…”` : label(p));
  const holds = (list, p) => list.find((x) => p.views.length && x.views.length > 1 && x.views.some((v) => v.name === p.views[0].name));
  const A = new Map(a.map((p) => [identity(p), p]));
  const B = new Map(b.map((p) => [identity(p), p]));
  const out = [];
  const say = (kind, p, detail) => out.push({ kind, id: identity(p), key: p.key, label: label(p), detail });
  for (const p of b) {
    if (A.has(identity(p))) continue;
    const group = holds(a, p);
    if (group) say('ungrouped', p, `Took ${label(p)} out of ${label(group)}`);
    else say('added', p, `Added ${p.text !== null ? 'a note' : label(p)}`);
  }
  for (const p of a) {
    if (B.has(identity(p))) continue;
    const group = holds(b, p);
    if (group) say('grouped', p, `Grouped ${label(p)} into ${label(group)} as a tab`);
    else say('removed', p, `Removed ${textLabel(p)}`);
  }
  // moved: the common panels off the longest common order
  const ca = a.filter((p) => B.has(identity(p))).map(identity);
  const cb = b.filter((p) => A.has(identity(p))).map(identity);
  const L = Array.from({ length: ca.length + 1 }, () => new Int32Array(cb.length + 1));
  for (let i = ca.length - 1; i >= 0; i--) for (let j = cb.length - 1; j >= 0; j--) L[i][j] = ca[i] === cb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const stay = new Set();
  for (let i = 0, j = 0; i < ca.length && j < cb.length;) { if (ca[i] === cb[j]) { stay.add(ca[i]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) i++; else j++; }
  // an added panel placed above others moves nothing: what it sits before is the news
  for (const id of cb) if (!stay.has(id)) { const p = B.get(id); say('moved', p, `Moved ${label(p)}`); }
  for (const p of b) {
    const q = A.get(identity(p));
    if (!q) {
      const next = b[b.indexOf(p) + 1];
      const line = out.find((c) => c.id === identity(p) && c.kind === 'added');
      if (line && next && A.has(identity(next))) line.detail += `, above ${label(next)}`;
      continue;
    }
    if (q.hidden !== p.hidden) say(p.hidden ? 'hidden' : 'shown', p, `${p.hidden ? 'Hid' : 'Showed'} ${label(p)}`);
    const w0 = q.w, w1 = p.w, h0 = q.h, h1 = p.h;
    if (w0 !== w1 || h0 !== h1) say('resized', p, `${label(p)}: ${w0 !== w1 ? `${w0} → ${w1} columns` : ''}${w0 !== w1 && h0 !== h1 ? ', ' : ''}${h0 !== h1 ? `${h0 || 'auto'} → ${h1 || 'auto'} rows` : ''}`);
    if (label(q) !== label(p)) say('renamed', p, `Renamed ${label(q)} to ${label(p)}`);
    const v0 = q.views[0], v1 = p.views[0];
    if (v0 && v1) {
      if ((v0.type || 'table') !== (v1.type || 'table')) say('retyped', p, `${label(p)}: ${TYPE_NAMES[v0.type || 'table'] || v0.type} → ${TYPE_NAMES[v1.type || 'table'] || v1.type}`);
      else if (signalOf(v0) !== signalOf(v1)) say('signal', p, `${label(p)} plots ${signalOf(v1)} (was ${signalOf(v0)})`);
      else if (JSON.stringify(v0) !== JSON.stringify(v1)) say('settings', p, `${label(p)}: settings changed`);
    }
    if (q.text !== null && p.text !== null && q.text !== p.text) say('text', p, 'Edited a note');
  }
  return out;
}
