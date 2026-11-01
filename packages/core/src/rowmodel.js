/* The ONE row model every view reads (docs/CONTRACT.md §2):

     dataset rows
       -> filter    the .base file's `filters` AND the view's `filters` (grammar.js, Bases' evaluator)
       -> search    the toolbar's search box, over the view's visible properties
       -> sort      the view's `sort` (a group level with a direction sorts first)
       -> group     `groupBy`, then `subGroupBy`; `groupOrder` orders the top level, and a named group with no rows
                    still shows (an empty column is information); a level with `by:` groups a date by its day, week,
                    month, quarter or year, in time order (`gaps: true` keeps the empty buckets between); a level with
                    `bins:` groups a number by its [min, max) bucket, ascending; `grouping: <id>` picks the levels
                    (and tiles) of one `groupings:` entry (CONTRACT §20)
       -> limit     the first `limit` rows, in that order
       -> rollup    `rollup: {keep, agg}`: one row per kept combination, the rest aggregated (CONTRACT §16); in a
                    pivot the kept dimensions are its row key and `agg` its cell summary
       -> pivot     for type: pivot, `splitBy` x `value` over the same rows, then sorted and grouped the same way

   Moved out of the table lane's <data-views> (_compute() in views.js, ab5ba92), where it ran inside the table, so
   every layout reads the same rows. WHY one model: a link, a saved view or an agent's edit means the same rows
   whichever view draws them (Zach, 2026-10-25: "1 dataset, 1 base file, many views"). Engine: TanStack Table
   (sorting, grouping, expanding), the same instance the table view draws. */

import * as T from '@tanstack/table-core';
import { storeReactivityBindings } from '@tanstack/table-core/store-reactivity-bindings';
import { storageOf } from './types.js';
import { PROPERTY_KEYS, bareView } from './bare.js';
import { cellValue, compileFilters, pivot as pivotRows, PIVOT_PREFIX, timeBucket, timeGrain, nextBucket, rollup, rollupKeep, rolledAway, summaryName, binsOf, binKey, effectiveView, viewPath, pathSegments } from './grammar.js';
import { groupBuckets, groupFacet } from './facets.js';
import { groupLabel, valueText } from './format.js';

/* WHY one collator: `a.localeCompare(b, undefined, options)` builds an Intl.Collator on every comparison (V8 caches only
   the no-option form), and a grouped sort makes thousands: the "By brand" model fell 116 -> 41 ms in the perf review
   (2026-10-26, item 2). ECMA-402 defines localeCompare(that, locales, options) as exactly
   `new Intl.Collator(locales, options).compare(this, that)`, so the order is the same, ties included
   (tests/unit/perf-oracle.test.mjs holds every gallery view and every property sorted both ways to it). */
export const TEXT_ORDER = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

const FEATURES = T.tableFeatures({
  coreReactivityFeature: storeReactivityBindings(),
  columnGroupingFeature: T.columnGroupingFeature,
  groupedRowModel: T.createGroupedRowModel(),
  rowExpandingFeature: T.rowExpandingFeature,
  expandedRowModel: T.createExpandedRowModel(),
  rowSortingFeature: T.rowSortingFeature,
  sortedRowModel: T.createSortedRowModel(),
});

// the id of a time level's twin column: the view's sort on the grouped date reads it (tableModel)
const TWIN = '\u0000sort:';
// the column of one segment of a path level: index, separator and the real property are in its id (grouped rows carry only that)
const PATH = '\u0000path\u0001';
/** A column id's path level, {at, sep, property}, or null. */
function pathLevel(id) {
  if (typeof id !== 'string' || !id.startsWith(PATH)) return null;
  const [at, sep, ...property] = id.slice(PATH.length).split('\u0001');
  return { at: Number(at), sep, property: property.join('\u0001') };
}

/** The view's group levels as TanStack's grouping columns: a path level is one column per segment, as deep as its rows go.
    WHY this and not `tree:`: grouping keeps what a group row already has (getLeafRows counts, summaries, the fold, sorting per
    depth), and only a row that runs out of segments needs saying: its deeper levels dissolve (settled, below). */
function groupLevels(view, props, rows) {
  const out = [];
  for (const g of [view.groupBy, view.subGroupBy]) {
    if (!g || !props[g.property]) continue;
    const sep = viewPath(view, g);
    if (!sep) { out.push(g); continue; }
    let depth = 1;
    for (const r of rows) depth = Math.max(depth, pathSegments(cellValue(r[g.property]), sep).length);
    for (let at = 0; at < depth; at++) out.push({ ...g, property: `${PATH}${at}\u0001${sep}\u0001${g.property}`, real: g.property, at, sep });
  }
  return out;
}

/** What a group row of a path level stands for: {at, property, key, path, title}, or null for any other row. */
export function pathGroup(row) {
  const l = row.getIsGrouped() ? pathLevel(row.groupingColumnId) : null;
  if (!l) return null;
  const first = row.getLeafRows().find((x) => !x.getIsGrouped());
  const path = first ? pathSegments(cellValue(first.original[l.property]), l.sep).slice(0, l.at + 1) : [];
  return { at: l.at, property: l.property, key: path[l.at] ?? null, path, title: path.join(l.sep) };
}

// a level below the first where its rows have no segment left: those rows belong to the level above, no group of their own
const dissolves = (row) => { const g = pathGroup(row); return !!g && g.at > 0 && g.key === null; };

/** Rows under one parent as they are drawn: its direct rows, then its groups, each dissolved level replaced by what it holds.
    WHY direct rows first: McMaster's rule for a section (CONTRACT §20), and a parent's own parameters read before its parts. */
function settled(rows) {
  const direct = [], groups = [];
  for (const r of rows) {
    if (dissolves(r)) direct.push(...settled(r.subRows));
    else (r.getIsGrouped() ? groups : direct).push(r);
  }
  return [...direct, ...groups];
}

/** A nested view's drawn rows, in order, each with its true depth: [{row, depth}]. A dissolved level is no row and no fold.
    `all` walks through folds, for a row model. */
export function pathRows(table, { all = false } = {}) {
  const out = [];
  const visit = (rows, depth) => {
    for (const row of settled(rows)) {
      out.push({ row, depth });
      if (row.getIsGrouped() && (all || row.getIsExpanded())) visit(row.subRows, depth + 1);
    }
  };
  visit(table.getPreExpandedRowModel().rows, 0);
  return out;
}

// a time level's group row -> its bucket key, or null (TanStack keys a group by its value as text: no bucket is 'undefined')
const bucketOf = (row) => (row.groupingValue === undefined || row.groupingValue === 'undefined' ? null : row.groupingValue);

export const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** A value's place in a numeric sort: [low, high], a number's own value twice, a list of numbers' smallest and largest;
    null for anything else (text, a list holding a non-number, NaN or Infinity, an empty list). WHY (2026-10-30): a range
    column (a datasheet's [15, 60] beside a plain 20) sorted every plain number ahead of every list, which it compared as
    its joined text, so it read 2, 32, -40…85, 15…30; now numbers and numeric lists are one sequence, by the low end, a
    tie by the high end. order.js ranks by the same span, so the big-data order is the same. */
export function numericSpan(v) {
  if (isNum(v)) return [v, v];
  if (!Array.isArray(v) || !v.length) return null;
  let lo = Infinity, hi = -Infinity;
  for (const x of v) {
    if (!isNum(x)) return null;
    if (x < lo) lo = x;
    if (x > hi) hi = x;
  }
  return [lo, hi];
}

/** The dataset's properties with labels: {id: {id, label, type, ...}}. A .base file's properties.<p>.displayName
    names a column (Bases' meaning); `note.<p>` and `<p>` are the same property. */
export function properties(dataset, base) {
  // WHY the whole entry, not just displayName (CONTRACT §28, property types): a .base property says its type (`kind`
  // here, beside the data's storage `type`, which filtering and sorting read), its icon, its description and its
  // type's options; they override the data's own meta, as displayName already did
  const meta = {};
  for (const [k, v] of Object.entries((base && base.properties) || {})) {
    if (!v || typeof v !== 'object') continue;
    // `formula.nominal` is Bases' name for a value with several sources, which the data names `nominal` (CONTRACT §36)
    const id = k.startsWith('note.') ? k.slice(5) : k.startsWith('formula.') && !(dataset.properties || {})[k] && (dataset.properties || {})[k.slice(8)] ? k.slice(8) : k;
    const { displayName, type, ...rest } = v;
    meta[id] = { ...rest, ...(displayName ? { label: displayName } : {}), ...(type ? { kind: type } : {}) };
  }
  const out = {};
  for (const [id, m] of Object.entries(dataset.properties || {})) {
    const own = meta[id];
    out[id] = own ? { id, type: 'text', ...m, ...own, label: own.label || (m && m.label) || id } : { id, type: 'text', ...m, label: (m && m.label) || id };
    // a property the .base file deleted (the column menu's Delete on a property the data keeps): gone from every view
    if (own && own.hidden === true) out[id].removed = true;
    // §46: a markdown property's cell summarises it, unless the view or the file says otherwise
    if (out[id].kind === 'markdown' && !out[id].display) out[id].display = out[id].summary === 'preview' ? 'preview' : 'outline';
  }
  // a source's column reads as its value does, whatever the file says of that value (CONTRACT §36); its label, width and word are its own
  for (const [id, c] of Object.entries(out)) {
    const own = c.of && meta[c.of];
    if (!own) continue;
    const { label, width, hidden, description, note, ...rest } = own;
    out[id] = c.display === 'source' ? c : { ...c, ...rest, ...(meta[id] || {}), label: (meta[id] && meta[id].label) || c.label };
  }
  // a property only the .base file has (the column menu's Insert or Duplicate): a typed column with no values of its
  // own ("—", and why), or one that reads another's values (`from`), stored as that one is
  for (const [id, own] of Object.entries(meta)) {
    if (out[id] || !(own.kind || own.from)) continue;
    const src = own.from && out[own.from];
    if (own.from && !src) continue;
    out[id] = { ...(src ? { ...src, kind: undefined, icon: undefined, description: undefined, removed: undefined } : { type: storageOf(own.kind) }), ...own, id, label: own.label || id, fileOnly: true,
      ...(src ? {} : { why: 'no value: this property is in the .base file, not the data' }) };
    for (const k of Object.keys(out[id])) if (out[id][k] === undefined) delete out[id][k];
  }
  return out;
}

/** The rows with each `from` property's values under its own id (a Duplicate): new row objects only when some column
    copies another, so a file without one costs nothing. */
export function withCopies(rows, columns) {
  const copies = Object.values(columns).filter((c) => c.from && columns[c.from]);
  if (!copies.length) return rows;
  return rows.map((r) => { const o = { ...r }; for (const c of copies) if (o[c.id] === undefined) o[c.id] = r[c.from]; return o; });
}

// The view types that nest rows by `tree:` (docs/CONTRACT.md, amendment 2026-10-26 (core pass)); elsewhere the key is
// ignored, so a board or a chart keeps its own grouping
const TREE_TYPES = new Set(['table', 'list']);

/** The tree spec of a view (`tree: {parent}` or `{path, separator}`), or null when it has none, names no property of
    the data, or its type does not nest. */
export function treeSpec(view, props) {
  const t = view && view.tree;
  if (!t || typeof t !== 'object' || !TREE_TYPES.has(view.type || 'table')) return null;
  if (t.parent && props[t.parent]) return { parent: t.parent };
  if (t.path && props[t.path]) return { path: t.path, separator: t.separator || '.' };
  return null;
}

/** A path's heading: a node with no row behind it (actuator, actuator.steadywin). Never in `rows`, never edited. */
export const isHeading = (original) => !!(original && original._heading !== undefined);

/**
 * rows -> {roots, children}: the top level and each node's children (a Map), for TanStack's getSubRows.
 * A row whose parent is not among the rows (filtered out, searched away, or never there) starts at the top level, so
 * a filter never hides a match; a parent cycle is cut where it closes. A path's missing ancestors become headings
 * ({id: '@a.b', _heading: 'b', _path, _first}); a second row on one path is its sibling, not its child.
 * Moved from the list view's own nesting (packages/views/tree, 2026-10-26): the order among siblings is the row
 * model's sort, which TanStack applies to every level.
 */
export function treeRows(rows, spec) {
  const children = new Map();
  const roots = [];
  const add = (parent, node) => { if (!parent) roots.push(node); else { if (!children.has(parent)) children.set(parent, []); children.get(parent).push(node); } };
  if (spec.parent) {
    const byId = new Map(rows.map((r) => [String(r.id), r]));
    const up = new Map();
    for (const r of rows) {
      const p = cellValue(r[spec.parent]);
      const pid = isEmpty(p) ? null : String(Array.isArray(p) ? p[0] : p);
      if (pid && pid !== String(r.id) && byId.has(pid)) up.set(r, byId.get(pid));
    }
    for (const r of cycleCuts(up)) up.delete(r);
    for (const r of rows) add(up.get(r) || null, r);
    return { roots, children };
  }
  const sep = spec.separator;
  const nodes = new Map();
  const ensure = (path, first) => {
    if (nodes.has(path)) return nodes.get(path);
    const parts = path.split(sep);
    const node = { id: `@${path}`, _heading: parts[parts.length - 1], _path: path, _first: first };
    nodes.set(path, node);
    add(parts.length > 1 ? ensure(parts.slice(0, -1).join(sep), first) : null, node);
    return node;
  };
  for (const r of rows) {
    const raw = cellValue(r[spec.path]);
    const path = isEmpty(raw) ? '' : String(raw).split(sep).filter(Boolean).join(sep);
    const parts = path ? path.split(sep) : [];
    const parent = parts.length > 1 ? ensure(parts.slice(0, -1).join(sep), r) : null;
    const at = nodes.get(path);
    if (at && isHeading(at)) {
      // the row is the node its path names: it takes the heading's place (and its children)
      const list = parent ? children.get(parent) : roots;
      list[list.indexOf(at)] = r;
      if (children.has(at)) { children.set(r, children.get(at)); children.delete(at); }
      nodes.set(path, r);
    } else {
      add(parent, r);
      if (path && !at) nodes.set(path, r);
    }
  }
  return { roots, children };
}

/**
 * The rows whose parent link a cycle cut removes. The rule: in row order, a row whose ancestor walk (over the links
 * still standing) meets a row twice loses its link. WHY not that walk itself: it restarts at every row, so a chain of
 * n rows costs n²/2 steps (4,000 rows: 649 ms, 2026-10-26 performance review). The same cuts in one pass:
 *   - a cycle loses only its first row in row order (that row's walk comes back to itself; once it is cut, every
 *     later walk ends there);
 *   - a row hanging off a cycle is cut when it comes before the cycle's first row and before every cut ancestor of
 *     its own (an earlier cut ends its walk first). So each row inherits a `bound`, the order it must come before.
 * tests/unit/tree-linear.test.mjs keeps the walk as its oracle.
 */
function cycleCuts(up) {
  const order = new Map();
  for (const r of up.keys()) order.set(r, order.size);
  // row -> null (its ancestors end at a root), {cycle: true, first} (on a cycle) or {bound, cut, at} (hangs off one)
  const fate = new Map();
  const onPath = new Set();
  const cuts = [];
  for (const start of up.keys()) {
    if (fate.has(start)) continue;
    const path = [];
    let at = start;
    while (up.has(at) && !fate.has(at) && !onPath.has(at)) { onPath.add(at); path.push(at); at = up.get(at); }
    let next = fate.get(at) || null;
    let end = path.length;
    if (onPath.has(at)) {
      end = path.indexOf(at);
      const ring = path.slice(end);
      const first = ring.reduce((a, b) => (order.get(b) < order.get(a) ? b : a));
      next = { cycle: true, first: order.get(first) };
      for (const r of ring) fate.set(r, next);
      cuts.push(first);
    }
    for (let k = end - 1; k >= 0; k--) {
      const r = path[k];
      if (next) {
        const bound = next.cycle ? next.first : next.cut ? next.at : next.bound;
        next = { bound, cut: order.get(r) < bound, at: order.get(r) };
        if (next.cut) cuts.push(r);
      }
      fate.set(r, next);
    }
    for (const r of path) onPath.delete(r);
  }
  return cuts;
}

/** A TanStack table over rows: sorted by the view's `sort`, grouped by `groupBy` › `subGroupBy`, and with `tree:`
    nested by TanStack's sub-rows (getSubRows; a group holds the top of each tree, children follow their parent).
    `expanded` is TanStack's expanded state (true = every group and parent open). */
export function tableModel(rows, props, view, { expanded = true } = {}) {
  const tree = treeSpec(view, props);
  const nest = tree ? treeRows(rows, tree) : null;
  const levels = groupLevels(view, props, rows);
  const grains = new Map(levels.filter(timeGrain).map((g) => [g.property, g.by]));
  // a binned level's buckets: the model's (rowModel marks its column), else made here from these rows
  const binned = new Map(levels.filter((g) => binsOf(g) && !grains.has(g.property)).map((g) => [g.property, levelBins(g, props, rows)]));
  // WHY groupOrder sorts the first level: it is the Bases key a board writes when a column is dragged, and the table
  // must draw the groups in the order every other view reads them; groups it does not name keep their order after
  const named = levels.length && Array.isArray(view.groupOrder) && view.groupOrder.length
    ? new Map(view.groupOrder.map((k, i) => [Array.isArray(k) ? k.join(', ') : k === null ? undefined : k, i])) : null;
  const rank = (v) => (named && named.has(v) ? named.get(v) : named ? named.size : 0);
  const column = (p, id = p.id) => ({
    id,
    // WHY a heading reads its first row: it has no cells of its own, but it must sort and group with the rows under it
    accessorFn: (r) => {
      const v = (isHeading(r) ? r._first : r)[p.id];
      if (p.pivot) return v && isNum(v.v) ? v.v : undefined;
      const x = cellValue(v);
      if (isEmpty(x)) return undefined;
      return Array.isArray(x) ? x.join(', ') : x;
    },
    sortUndefined: 'last',
    sortFn: (a, b, cid) => {
      const x = a.getValue(cid), y = b.getValue(cid);
      if (named && cid === levels[0].property) return rank(x) - rank(y);
      if (isNum(x) && isNum(y)) return x - y;
      // a list of numbers (the accessor joined it into text) sorts with the numbers: by its low end, then its high end
      const sx = isNum(x) ? [x, x] : typeof x === 'string' ? spanOf(a, p) : null;
      const sy = isNum(y) ? [y, y] : typeof y === 'string' ? spanOf(b, p) : null;
      if (sx && sy) return sx[0] - sy[0] || sx[1] - sy[1];
      if (!!sx !== !!sy) return sx ? -1 : 1;
      return TEXT_ORDER.compare(String(x), String(y));
    },
  });
  // the stored value behind a row's joined text, as a span (a group row reads its first row's, as its group value is)
  const spanOf = (row, p) => { const o = row.original; return o ? numericSpan(cellValue((isHeading(o) ? o._first : o)[p.id])) : null; };
  // A time level groups by its bucket and orders the buckets in time; its rows tie, so the view's own sort (on the
  // same date too) orders the rows inside a bucket. WHY the view's sort reads a twin column: TanStack applies every
  // sort entry at every depth, so a sort on the grouped column itself would rank the rows by bucket only.
  const timeColumn = (p, by) => ({
    ...column(p),
    getGroupingValue: (r) => timeBucket((isHeading(r) ? r._first : r)[p.id], by) ?? undefined,
    sortFn: (a, b) => {
      if (!a.getIsGrouped() || !b.getIsGrouped()) return 0;
      const x = bucketOf(a), y = bucketOf(b);
      return x === y ? 0 : x === null ? 1 : y === null ? -1 : x < y ? -1 : 1;
    },
  });
  // A binned level the same way: its group value is its bucket's key (text that sorts in the buckets' order), its rows
  // tie, and the view's sort (on the same number too) orders the rows inside a bucket through the twin column
  // (its leaves read their bucket too, so the rows of "No <property>" keep their order rather than the empty ones last)
  const binColumn = (p, buckets) => {
    const key = (r) => binKey((isHeading(r) ? r._first : r)[p.id], buckets) ?? undefined;
    return { ...timeColumn(p, null), accessorFn: key, getGroupingValue: key };
  };
  const twin = (id) => (grains.has(id) || binned.has(id) ? TWIN + id : id);
  // a path level's column reads one segment; the row's own property stays a column of its own (a sort, a cell)
  const pathColumn = (l) => {
    const seg = (r) => pathSegments(cellValue(r[l.real]), l.sep)[l.at];
    return { ...column(props[l.real], l.property), accessorFn: seg, getGroupingValue: seg };
  };
  const columns = [...Object.values(props).flatMap((p) => (grains.has(p.id) ? [timeColumn(p, grains.get(p.id)), column(p, TWIN + p.id)]
    : binned.has(p.id) ? [binColumn(p, binned.get(p.id)), column(p, TWIN + p.id)] : [column(p)])), ...levels.filter((l) => l.real).map(pathColumn)];
  const sorting = [
    // WHY only with a direction: a group level without one keeps the dataset's order (a datasheet's sections); a time
    // level is always in time order (oldest first unless DESC)
    ...levels.filter((g, i) => g.direction || (i === 0 && named) || grains.has(g.property) || binned.has(g.property)).map((g, i) => ({ id: g.property, desc: !(i === 0 && named && !grains.has(g.property) && !binned.has(g.property)) && g.direction === 'DESC' })),
    ...(view.sort || []).filter((s) => s && props[s.property]).map((s) => ({ id: twin(s.property), desc: s.direction === 'DESC' })),
  ];
  return T.constructTable({
    features: FEATURES, columns, data: nest ? nest.roots : rows, getRowId: (r, i) => String(r._id ?? r.id ?? i),
    ...(nest ? { getSubRows: (r) => nest.children.get(r) } : {}),
    groupedColumnMode: false,
    initialState: { grouping: levels.map((g) => g.property), sorting, expanded },
  });
}

/** A binned level's buckets: its column's when the row model marked it, else made from these rows' numbers. */
function levelBins(level, props, rows) {
  const p = props[level.property];
  if (p && Array.isArray(p.bins)) return p.bins;
  return groupBuckets(level, rows.map((r) => cellValue(r[level.property])), p && p.unitText);
}

function leafKey(row, property, by) {
  if (by) return bucketOf(row); // a time or binned level's key is its bucket
  const leaves = row.getLeafRows().filter((x) => !x.getIsGrouped());
  // WHY from a leaf: the engine hands an empty group's value back as undefined, which must read "No form"
  const first = leaves.length ? leaves[0].original : null;
  return first ? cellValue((isHeading(first) ? first._first : first)[property]) ?? null : null;
}

/** A time level's groups with `gaps: true`: every bucket from the first to the last, an empty one where no row fell
    (in the level's order; "No <date>" stays where it was, at the end). */
function withGaps(groups, level, make) {
  const by = timeGrain(level);
  if (!by || !level.gaps) return groups;
  const dated = groups.filter((g) => g.key !== null);
  if (dated.length < 2) return groups;
  const desc = dated[0].key > dated[dated.length - 1].key;
  const have = new Map(dated.map((g) => [g.key, g]));
  const ends = desc ? [dated[dated.length - 1].key, dated[0].key] : [dated[0].key, dated[dated.length - 1].key];
  const all = [];
  for (let k = ends[0]; k !== null && k <= ends[1]; k = nextBucket(k, by)) all.push(have.get(k) || make(k));
  if (desc) all.reverse();
  return [...all, ...groups.filter((g) => g.key === null)];
}

/** collect() for a view with a path level: groups nest as deep as the rows do, each group's `rows` holding everything under
    it in drawn order. A group with child groups and rows of its own lists those rows first, as {key: null, rows, direct: true}
    (sectionsOf draws a null-key sub straight under the title, the list view at the group's own depth). */
function collectPath(table, view, props, limit) {
  const specs = [view.groupBy, view.subGroupBy].filter(Boolean);
  let taken = 0;
  const fill = (list, path) => {
    const direct = [], groups = [];
    for (const r of settled(list)) {
      if (r.getIsGrouped()) groups.push(node(r, path));
      else if (!limit || taken < limit) { taken++; direct.push(r.original); }
    }
    return { direct, groups };
  };
  const node = (r, path) => {
    const at = pathGroup(r);
    const spec = at ? null : specs.find((g) => g.property === r.groupingColumnId);
    const grain = spec && timeGrain(spec);
    const key = at ? at.key : leafKey(r, r.groupingColumnId, grain || (spec && binsOf(spec) ? 'bins' : null));
    const here = at ? at.path : [...path, key];
    const { direct, groups } = fill(r.subRows, here);
    const out = { key, property: at ? at.property : r.groupingColumnId, ...(grain ? { by: grain } : {}), path: here, rows: [...direct, ...groups.flatMap((g) => g.rows)] };
    if (groups.length) out.groups = [...(direct.length ? [{ key: null, property: out.property, rows: direct, direct: true }] : []), ...groups];
    return out;
  };
  const top = fill(table.getPreExpandedRowModel().rows, []).groups;
  const order = (view.groupOrder || []).map((k) => JSON.stringify(k));
  const byKey = new Map(top.map((g) => [JSON.stringify(g.key), g]));
  const named = order.map((k) => byKey.get(k) || { key: JSON.parse(k), property: specs[0].property, path: [JSON.parse(k)], rows: [] });
  const groups = [...named, ...top.filter((g) => !order.includes(JSON.stringify(g.key)) && (!limit || g.rows.length))];
  return { rows: groups.flatMap((g) => g.rows), groups };
}

/** Flatten an all-open TanStack row model into {rows, groups} (groups nest one level for subGroupBy). */
function collect(table, view, props, limit) {
  const specs = [view.groupBy, view.subGroupBy].filter((g) => g && props[g.property]);
  if (specs.some((g) => viewPath(view, g))) return collectPath(table, view, props, limit);
  const levels = specs.map((g) => g.property);
  const grain = specs.map((g) => timeGrain(g));
  const keyed = specs.map((g, i) => grain[i] || (binsOf(g) ? 'bins' : null));
  const by = (i) => (grain[i] ? { by: grain[i] } : {});
  const flat = table.getRowModel().rows;
  const rows = [];
  if (!levels.length) {
    for (const r of flat) if (!isHeading(r.original) && (!limit || rows.length < limit)) rows.push(r.original);
    return { rows, groups: null };
  }
  const top = new Map();
  let g0 = null, g1 = null;
  for (const r of flat) {
    if (r.getIsGrouped()) {
      if (r.depth === 0) {
        g0 = { key: leafKey(r, levels[0], keyed[0]), property: levels[0], ...by(0), rows: [], ...(levels[1] ? { groups: [] } : {}) };
        top.set(JSON.stringify(g0.key), g0);
        g1 = null;
      } else {
        g1 = { key: leafKey(r, levels[1], keyed[1]), property: levels[1], ...by(1), rows: [] };
        g0.groups.push(g1);
      }
    } else if (g0 && !isHeading(r.original) && (!limit || rows.length < limit)) {
      rows.push(r.original);
      g0.rows.push(r.original);
      if (g1) g1.rows.push(r.original);
    }
  }
  // WHY groupOrder decides: it is the Bases key a board writes when a column is dragged; a group it does not name
  // follows in the engine's order, and a named group with no rows still shows
  const order = (view.groupOrder || []).map((k) => JSON.stringify(k));
  const named = order.map((k) => top.get(k) || { key: JSON.parse(k), property: levels[0], ...by(0), rows: [], ...(levels[1] ? { groups: [] } : {}) });
  const rest = [...top.entries()].filter(([k, g]) => !order.includes(k) && (!limit || g.rows.length)).map(([, g]) => g);
  const groups = withGaps([...named, ...rest], specs[0], (key) => ({ key, property: levels[0], ...by(0), rows: [], ...(levels[1] ? { groups: [] } : {}) }));
  if (limit) for (const g of groups) if (g.groups) g.groups = g.groups.filter((s) => s.rows.length);
  if (levels[1]) for (const g of groups) g.groups = withGaps(g.groups, specs[1], (key) => ({ key, property: levels[1], ...by(1), rows: [] }));
  return { rows: groups.flatMap((g) => g.rows), groups };
}

/** Search: rows where any of the view's visible properties contains the text (case-insensitive). */
export function search(rows, props, view, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return rows;
  const visible = (view.order && view.order.length ? view.order : Object.keys(props)).filter((id) => props[id] && !props[id].pivot && !id.startsWith(PIVOT_PREFIX));
  return rows.filter((r) => visible.some((id) => {
    const v = cellValue(r[id]);
    return !isEmpty(v) && String(Array.isArray(v) ? v.join(' ') : v).toLowerCase().includes(q);
  }));
}

/** The pivot's extra columns as properties (label, the column group above it, the value's unit). */
export function pivotProperties(props, view, columns) {
  const out = { ...props };
  const vp = view.value && props[view.value.property];
  for (const c of columns) {
    out[c.id] = {
      id: c.id, label: c.path.length ? c.path[c.path.length - 1] : c.id.slice(1),
      group: c.path.length > 1 ? c.path.slice(0, -1).join(' / ') : null, type: 'cell', pivot: true,
      unitText: vp ? vp.unitText : undefined, decimals: vp ? vp.decimals : undefined, digits: vp ? vp.digits : undefined, compact: vp ? vp.compact : undefined,
    };
  }
  return out;
}

/**
 * The view's rows. Returns
 *   {rows, groups, total, matched, error, columns, table, pivot}
 * rows     the records after filters, search and sort (and limit), in the order the table draws them
 * groups   null, or [{key, property, rows, groups?}] in groupOrder (subGroupBy nests one level)
 * total    every row of the dataset; matched: the rows before `limit`
 * error    the filter's error message (the rows are then unfiltered by that part), or null
 * columns  the properties, labelled from the .base file
 * table    the TanStack table behind rows and groups (all groups open)
 * pivot    for type: pivot, {rows, columns, properties, groups, table}: one row per group of records, one column per
 *          splitBy value; a cell is {v, values, records}
 * `filters` (option) replaces the file's top-level filters, which is what the rail edits; `query` is the search.
 */
/** Every view key rowModel reads (through tableModel, treeSpec, collect, search and grammar's pivot). A host that caches
    a model keys it on these; tests/unit/model-keys.test.mjs fails when this file or the pivot reads a key not listed. */
export const MODEL_KEYS = ['type', 'filters', 'order', 'sort', 'groupBy', 'subGroupBy', 'groupOrder', 'limit', 'tree', 'splitBy', 'value', 'rollup', '_carry', 'open', 'grouping', 'groupings'];

/** The rows a view matches before it is sorted and grouped (the file's or the rail's filters, the view's, then the
    search), its labelled properties and the filters' errors: rowModel()'s first steps (and, §15, `only`: the selection that narrows them), shared with order.js. */
export { PROPERTY_KEYS, bareView };

/** A view whose model keys say note.<p> for a column the data names <p> (Bases' meaning, CONTRACT §24): the same view
    with those names bared. WHY only these keys, by name: the model reads order (search), groupBy, subGroupBy and sort
    and nothing else of the view; MODEL_KEYS lists them and tests/unit/model-keys.test.mjs holds this file to that.
    The display keys (image, start, title, …) are bared for the view by bareView in bare.js. */
export function bareModel(view, columns) {
  if (!view || typeof view !== 'object') return view;
  const bare = (p) => (typeof p !== 'string' || columns[p] ? p : p.startsWith('note.') && columns[p.slice(5)] ? p.slice(5) : p.startsWith('formula.') && columns[p.slice(8)] ? p.slice(8) : p);
  let out = view;
  const set = (k, v) => { if (out === view) out = { ...view }; out[k] = v; };
  if (Array.isArray(view.order) && view.order.some((p) => bare(p) !== p)) set('order', view.order.map(bare));
  for (const [k, g] of [['groupBy', view.groupBy], ['subGroupBy', view.subGroupBy]]) {
    if (g && typeof g === 'object' && bare(g.property) !== g.property) set(k, { ...g, property: bare(g.property) });
  }
  if (Array.isArray(view.sort) && view.sort.some((x) => x && bare(x.property) !== x.property)) set('sort', view.sort.map((x) => (x ? { ...x, property: bare(x.property) } : x)));
  return out;
}

/** §46: `defaultSort` on a dataset orders a view that names no sort it can follow (a folder of notes: newest first). */
export function withDefaultSort(dataset, base, view) {
  if (!dataset.defaultSort || !view || (view.sort || []).some((s) => s && properties(dataset, base)[s.property])) return view;
  return { ...view, sort: dataset.defaultSort };
}

export function matchedRows(dataset, base, view, { query = '', filters, only = null, keep = null } = {}) {
  const columns = properties(dataset, base);
  // `grouping: <id>` names a `groupings:` entry whose levels replace the view's own (CONTRACT §20)
  view = bareModel(effectiveView(view), columns); // `groupBy: {property: note.type}` groups by type (Bases' meaning)
  // a time level's column carries its grain (`by`), so groupLabel writes "Week of 19 Oct 2026" from a key or a row;
  // a binned level's carries its buckets (`bins`, made once over the whole dataset, so they hold still while filtering)
  for (const g of [view.subGroupBy, view.groupBy]) {
    if (!g || !columns[g.property]) continue;
    if (timeGrain(g)) columns[g.property].by = g.by;
    else if (binsOf(g)) columns[g.property].bins = groupBuckets(g, (dataset.rows || []).map((r) => cellValue(r[g.property])), columns[g.property].unitText);
  }
  let rows = withCopies(dataset.rows || [], columns);
  const errors = [];
  for (const f of [filters !== undefined ? filters : base && base.filters, view.filters]) {
    try {
      const keep = compileFilters(f);
      if (keep) rows = rows.filter(keep);
    } catch (err) { errors.push(err.message); }
  }
  rows = search(rows, columns, view, query);
  // docs/CONTRACT.md §40: rows a reader has just edited stay where they are until the view refreshes, matching or not (Notion's way: a row
  // must not vanish under the hand that is editing it); `kept` counts the ones that no longer match
  let kept = 0;
  if (keep && keep.size) {
    const matching = new Set(rows);
    rows = (dataset.rows || []).filter((r) => { if (matching.has(r)) return true; if (!keep.has(String(r.id))) return false; kept++; return true; });
  }
  // docs/CONTRACT.md §15 "Show only selected": a set of row ids narrows the rows before sort and group, so the groups,
  // their counts and `matched` describe the selection; the filter itself is untouched. WHY here, in matchedRows: the
  // main-thread fast order (order.js) starts from these rows too, so both paths narrow the same way
  if (only) rows = rows.filter((r) => only.has(String(r.id)));
  return { rows, columns, errors, kept };
}

export function rowModel(dataset, base, view, opts = {}) {
  view = withDefaultSort(dataset, base, view);
  const matched = matchedRows(dataset, base, view, opts);
  const { columns, errors } = matched;
  // the sort and the groups read the same bared names, and the same `grouping:` levels, as matchedRows (CONTRACT §24: note.type is type)
  view = bareModel(effectiveView(view), columns);
  let rows = matched.rows;
  const out = { rows: [], groups: null, total: (dataset.rows || []).length, matched: 0, error: errors.join('; ') || null, columns, table: null, pivot: null, rolled: null, kept: matched.kept };
  // the open setting's page URL property (CONTRACT §13) rides along on a pivot row, so a model's name can link to its page
  // the view's own open setting, else the file's top level (CONTRACT §13's rule, field by field)
  const openOf = (o) => (o && typeof o === 'object' ? o.url : null);
  const urlProp = openOf(view.open) || openOf(base && base.open) || null;
  if (view.type === 'pivot') {
    let pv = urlProp ? { ...view, _carry: [urlProp] } : view;
    if (view.rollup) {
      const keep = rollupKeep(view, columns);
      const agg = (view.rollup.agg || {})[view.value && view.value.property];
      const levels = [view.groupBy, view.subGroupBy].filter(Boolean).map((g) => g.property);
      pv = { ...pv, order: keep.filter((k) => !(view.splitBy || []).includes(k) && !levels.includes(k)), value: { ...(view.value || {}), summary: summaryName(agg) || (view.value && view.value.summary) } };
      out.rolled = { from: rows.length, keep, away: rolledAway(rows, view, columns) };
    }
    const p = pivotRows(rows, pv, columns);
    const pprops = pivotProperties(columns, view, p.columns);
    const table = tableModel(p.rows, pprops, view);
    const flat = collect(table, view, pprops, view.limit);
    out.pivot = { rows: flat.rows, groups: flat.groups, columns: p.columns, properties: pprops, table, order: pv.order || view.order || [], urlProperty: urlProp };
    const recordTable = tableModel(rows, columns, { ...view, groupBy: undefined, subGroupBy: undefined });
    out.rows = recordTable.getRowModel().rows.map((r) => r.original);
    out.matched = out.rows.length;
    out.table = recordTable;
    return out;
  }
  if (view.rollup) {
    out.rolled = { from: rows.length, keep: rollupKeep(view, columns), away: rolledAway(rows, view, columns) };
    rows = rollup(rows, view, columns);
  }
  const table = tableModel(rows, columns, view);
  out.table = table;
  out.matched = rows.length;
  const flat = collect(table, view, columns, view.limit);
  out.rows = flat.rows;
  out.groups = flat.groups;
  return out;
}

// ---------------------------------------------------------------- the grouped gallery's sections (CONTRACT §20)
// WHY (Zach, 2026-10-27): "we can also support an H2 header as well … in McMaster you see Fastening & Joining, then
// Fasteners / Adhesives & Tape … But Pipe, Tubing, Hose & Fittings has no other layer of breakdown." A section's rows
// with no second-level value are drawn straight under its title, before the named sub-headers, so a section whose rows
// all lack it has no second layer at all.

/** A level's group in words: groupLabel, with each of a list key's values in its own label ("Pharmaceutical"). */
export function groupText(columns, property, key) {
  if (Array.isArray(key) && key.length) return key.map((x) => valueText(x, columns[property]) || String(x)).join(', ');
  return groupLabel(columns, property, key);
}

/** The model's groups as sections: [{key, property, label, rows, count, subs: [{key, property, label, rows, count}]}].
    A sub with no value (key null) has label null and comes first; a model with no subGroupBy gives each section one
    such sub holding all its rows. */
export function sectionsOf(groups, columns) {
  const sub = (s) => ({ key: s.key, property: s.property, label: isEmpty(s.key) ? null : groupText(columns, s.property, s.key), rows: s.rows, count: s.rows.length });
  return (groups || []).map((g) => {
    const subs = (g.groups || []).map(sub);
    const list = [...subs.filter((s) => s.label === null), ...subs.filter((s) => s.label !== null)];
    return { key: g.key, property: g.property, label: groupText(columns, g.property, g.key), rows: g.rows, count: g.rows.length,
      subs: list.length ? list : [{ key: null, property: null, label: null, rows: g.rows, count: g.rows.length }] };
  });
}

/** The groups a view draws at its top level, as a nav facet lists them: [{key, label, n, facet}] in the view's order,
    `n` its rows under `filters` (the all-views filter; the caller leaves the nav's own pick out, so every row keeps
    its count) and the view's own filters, `facet` the rail state that picks it (null when none can: "No …"). */
export function groupEntries(dataset, base, view, { filters } = {}) {
  const eff = effectiveView(view || {});
  if (!eff.groupBy) return [];
  const flat = { ...eff, type: 'table' };
  for (const k of ['subGroupBy', 'limit', 'rollup', 'tree', 'grouping', 'splitBy']) delete flat[k];
  // WHY whole values: a nav pick filters on what a cell holds, and "servo" does not match servo.fw (PEP 0020)
  if (flat.groupBy.path !== undefined) { flat.groupBy = { ...flat.groupBy }; delete flat.groupBy.path; }
  const m = rowModel(dataset, base, flat, { filters });
  return (m.groups || []).filter((g) => g.rows.length).map((g) => ({ key: g.key, label: groupText(m.columns, g.property, g.key), n: g.rows.length, facet: groupFacet(m.columns, g.property, g.key) }));
}
