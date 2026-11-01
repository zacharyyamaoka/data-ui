/* The row model's ORDER without TanStack's sort: the same answer as orderOf(rowModel()) (rowmodel-worker.js), from
   typed-array sort keys. The row-model worker runs it, and <data-views> runs it for a big page's first model.

   WHY (lane/perf-worker, 2026-10-26): at 100,000 rows TanStack's sorted row model compares rows through closures
   (getValue, isNum, String(), the collator) about n log n times per model. Here every sort column becomes one integer
   rank per dataset row, computed once and kept while the data is the same (a search key, a filter or a second sort
   on the same column pays nothing for it); a model is then one native sort of Float64 composite keys.

   The rules it reproduces, read from @tanstack/table-core 9.3.1 (createGroupedRowModel.js, createSortedRowModel.js)
   and rowmodel.js' tableModel() / collect():
     - rows are grouped BEFORE they are sorted: groups by `${accessor value}` in order of first appearance, a group's
       value for a grouping column at its level or above is its first row's (in data order), and undefined for every
       other column (no aggregation feature is registered)
     - each level is sorted on its own (groups among groups, rows within their group) by the sorting entries in turn:
       an entry where both values are undefined is skipped; one undefined value goes last whatever the direction
       (sortUndefined 'last' returns before desc is applied); otherwise data-ui's sortFn (groupOrder's rank on the
       first level's column; numbers before text, numbers by value, text by the one collator), negated when desc;
       a full tie falls back to the row's index (its place among its siblings before the sort), so the sort is stable
     - an entry's key here: rank for ascending, K-1-rank for descending, K for undefined; the composite key ends in
       the index, so equal keys never meet and any correct sort gives the one order
   Anything this does not model (a row with `_heading`, a pivot, a tree, a rollup, a time level) returns null; the
   caller falls back to orderOf() / rowModel(), the oracle.
   tests/unit/order.test.mjs holds it to orderOf(rowModel()) byte for byte. */

import { matchedRows, TEXT_ORDER, isEmpty, treeSpec, bareModel, numericSpan, withDefaultSort } from './rowmodel.js';
import { cellValue, timeGrain, viewPath } from './grammar.js';

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const LIMIT = 2 ** 53;

/** The accessor value tableModel() gives TanStack for a (non-pivot, non-heading) row. */
function accessor(row, id) {
  const x = cellValue(row[id]);
  if (isEmpty(x)) return undefined;
  return Array.isArray(x) ? x.join(', ') : x;
}

/**
 * One column's ranks over every dataset row: {rank: Uint32Array, size: K}; rank K means undefined. Ranks follow
 * data-ui's sortFn: with `named` (groupOrder's Map), the named rank; else numbers by value, then text by the
 * collator, equal under it sharing a rank.
 */
export function columnRanks(rows, id, named = null) {
  const n = rows.length;
  const rank = new Uint32Array(n);
  if (named) {
    // WHY above every assigned rank, not named.size + 1: a groupOrder that repeats a name maps it to its LAST index
    // (a Map), so indexes can reach past named.size and a real rank met the undefined sentinel; an empty group then
    // sorted beside a named one instead of last (judge r1, 2026-10-27: [null, 'B'] by ['A', 'A', 'A', 'B'])
    let top = named.size;
    for (const i of named.values()) if (i > top) top = i;
    const size = top + 1;
    for (let i = 0; i < n; i++) {
      const v = accessor(rows[i], id);
      rank[i] = v === undefined ? size : named.has(v) ? named.get(v) : named.size;
    }
    return { rank, size };
  }
  // pass 1: classify; numbers into a typed array, text into distinct strings. A list of numbers (its accessor value is
  // its joined text) is a number here, ranked by its low end and then its high end (rowmodel.js numericSpan, the
  // row model's sortFn), so plain numbers and ranges are one sequence
  const kind = new Uint8Array(n); // 0 undefined, 1 number, 2 text
  const numOf = new Float64Array(n);
  const nums = new Float64Array(n);
  const textId = new Uint32Array(n);
  const ids = new Map();
  const texts = [];
  let numCount = 0;
  let hiOf = null; // the high ends, made at the first numeric list (a plain number's high end is itself)
  for (let i = 0; i < n; i++) {
    const v = accessor(rows[i], id);
    if (v === undefined) continue;
    if (isNum(v)) { kind[i] = 1; numOf[i] = v; nums[numCount++] = v; if (hiOf) hiOf[i] = v; continue; }
    const span = typeof v === 'string' ? numericSpan(cellValue(rows[i][id])) : null;
    if (span) {
      if (!hiOf) { hiOf = new Float64Array(n); for (let k = 0; k < i; k++) if (kind[k] === 1) hiOf[k] = numOf[k]; }
      kind[i] = 1; numOf[i] = span[0]; hiOf[i] = span[1]; nums[numCount++] = span[0];
      continue;
    }
    kind[i] = 2;
    const s = String(v);
    let t = ids.get(s);
    if (t === undefined) { t = texts.length; ids.set(s, t); texts.push(s); }
    textId[i] = t;
  }
  if (hiOf) return spanRanks(rows, n, kind, numOf, hiOf, textId, texts);
  // numbers: their distinct values in order (a native typed-array sort); 0 and -0 are one value (x - y is 0)
  const sorted = nums.subarray(0, numCount).slice().sort();
  const uniq = new Float64Array(numCount);
  let u = 0;
  for (let k = 0; k < numCount; k++) if (u === 0 || sorted[k] !== uniq[u - 1]) uniq[u++] = sorted[k];
  // text: each distinct string ranked once with the model's own collator; strings it calls equal share a rank
  const order = texts.map((_, k) => k).sort((a, b) => TEXT_ORDER.compare(texts[a], texts[b]));
  const textRank = new Uint32Array(texts.length);
  let r = u - 1;
  for (let k = 0; k < order.length; k++) {
    if (k === 0 || TEXT_ORDER.compare(texts[order[k - 1]], texts[order[k]]) !== 0) r++;
    textRank[order[k]] = r;
  }
  const size = r + 1;
  for (let i = 0; i < n; i++) {
    if (kind[i] === 0) rank[i] = size;
    else if (kind[i] === 2) rank[i] = textRank[textId[i]];
    else {
      const v = numOf[i];
      let lo = 0, hi = u - 1;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (uniq[mid] < v) lo = mid + 1; else hi = mid; }
      rank[i] = lo;
    }
  }
  return { rank, size };
}

/** columnRanks' answer when a column holds numeric lists: the numbers (plain ones and lists) ranked by (low, high), equal
    pairs sharing a rank (x - y, so 0 and -0 are one value), then the text by the collator, then K for undefined. */
function spanRanks(rows, n, kind, lo, hi, textId, texts) {
  const at = [];
  for (let i = 0; i < n; i++) if (kind[i] === 1) at.push(i);
  at.sort((a, b) => lo[a] - lo[b] || hi[a] - hi[b]);
  const rank = new Uint32Array(n);
  let r = -1;
  for (let k = 0; k < at.length; k++) {
    const i = at[k];
    if (k === 0 || lo[i] - lo[at[k - 1]] !== 0 || hi[i] - hi[at[k - 1]] !== 0) r++;
    rank[i] = r;
  }
  const order = texts.map((_, k) => k).sort((a, b) => TEXT_ORDER.compare(texts[a], texts[b]));
  const textRank = new Uint32Array(texts.length);
  for (let k = 0; k < order.length; k++) {
    if (k === 0 || TEXT_ORDER.compare(texts[order[k - 1]], texts[order[k]]) !== 0) r++;
    textRank[order[k]] = r;
  }
  const size = r + 1;
  for (let i = 0; i < n; i++) if (kind[i] === 0) rank[i] = size; else if (kind[i] === 2) rank[i] = textRank[textId[i]];
  return { rank, size };
}

/** A cache of column ranks for one dataset at one revision (the worker keeps one; an edit starts a new one). */
export function rankCache(dataset) {
  const cache = new Map();
  return {
    dataset,
    get(id, named) {
      const key = named ? `${id}\u0000${JSON.stringify([...named.entries()])}` : id;
      let got = cache.get(key);
      if (!got) { got = columnRanks(dataset.rows, id, named); cache.set(key, got); }
      return got;
    },
  };
}

/** Sort `items` by the entries' keys (keyOf[j](item), each in 0..sizes[j]), ties by their place in `items`, which
    callers pass in TanStack's index order (rows in data order, groups in order of first appearance). */
function sortBy(items, keyOf, sizes) {
  const m = items.length;
  if (m < 2) return items;
  const e = keyOf.length;
  let span = m;
  for (const s of sizes) span *= s + 1;
  if (span < LIMIT) {
    // WHY one Float64Array: every key and the index fit in one exact double, so a native numeric sort (no
    // comparator call per pair) gives the order; the index makes every key distinct
    const comp = new Float64Array(m);
    for (let k = 0; k < m; k++) {
      const it = items[k];
      let c = 0;
      for (let j = 0; j < e; j++) c = c * (sizes[j] + 1) + keyOf[j](it);
      comp[k] = c * m + k;
    }
    comp.sort();
    const out = new Array(m);
    for (let k = 0; k < m; k++) out[k] = items[comp[k] % m];
    return out;
  }
  // too many keys for one double: the same order through a comparator over the integer keys
  const keys = keyOf.map((f) => Uint32Array.from(items, f));
  const at = new Uint32Array(m);
  for (let k = 0; k < m; k++) at[k] = k;
  at.sort((x, y) => {
    for (let j = 0; j < e; j++) { const d = keys[j][x] - keys[j][y]; if (d) return d; }
    return x - y;
  });
  return Array.from(at, (k) => items[k]);
}

/**
 * orderOf()'s answer ({rows, table, groups, total, matched, error}, Uint32Array indices into dataset.rows) for a
 * workerEligible view, without TanStack's sort. `cache` (rankCache) keeps column ranks between calls.
 */
export function fastOrder(dataset, base, view, opts = {}, cache = rankCache(dataset)) {
  const all = dataset.rows || [];
  view = withDefaultSort(dataset, base, view);
  const { rows: matched, columns: props, errors } = matchedRows(dataset, base, view, opts);
  view = bareModel(view, props); // the same bared names as rowModel() sorts and groups by (CONTRACT §24)
  if (view.type === 'pivot' || view.rollup || timeGrain(view.groupBy) || timeGrain(view.subGroupBy) || viewPath(view, view.groupBy) || viewPath(view, view.subGroupBy) || treeSpec(view, props) || matched.some((r) => r && r._heading !== undefined)) return null;
  // positions: a matched row's index among the matched rows (TanStack's row.index) and its dataset index
  const M = matched.length;
  const dsIndex = new Uint32Array(M);
  if (M === all.length) for (let k = 0; k < M; k++) dsIndex[k] = k;
  else { const at = new Map(all.map((r, i) => [r, i])); for (let k = 0; k < M; k++) dsIndex[k] = at.get(matched[k]); }

  // tableModel()'s levels, groupOrder ranks and sorting entries, as it computes them
  const levels = [view.groupBy, view.subGroupBy].filter((g) => g && props[g.property]);
  const named = levels.length && Array.isArray(view.groupOrder) && view.groupOrder.length
    ? new Map(view.groupOrder.map((k, i) => [Array.isArray(k) ? k.join(', ') : k === null ? undefined : k, i])) : null;
  const sorting = [
    ...levels.filter((g, i) => g.direction || (i === 0 && named)).map((g, i) => ({ id: g.property, desc: !(i === 0 && named) && g.direction === 'DESC' })),
    ...(view.sort || []).filter((s) => s && props[s.property]).map((s) => ({ id: s.property, desc: s.direction === 'DESC' })),
  ];
  const ranks = sorting.map((s) => cache.get(s.id, named && s.id === levels[0].property ? named : null));
  const sizes = ranks.map((r) => r.size);
  // a matched row's key for entry j: rank ascending, K-1-rank descending, K for undefined (last either way)
  const key = sorting.map((s, j) => {
    const { rank, size } = ranks[j];
    return s.desc ? (p) => { const r = rank[dsIndex[p]]; return r === size ? size : size - 1 - r; } : (p) => rank[dsIndex[p]];
  });
  const grouping = levels.map((g) => g.property);
  const positions = (n) => { const out = new Array(n); for (let k = 0; k < n; k++) out[k] = k; return out; };
  const sortLeaves = (ps) => sortBy(ps, key, sizes);

  // groups as TanStack makes them: `${value}`, first appearance, over the rows in data (matched) order
  const groupUp = (ps, depth) => {
    const id = grouping[depth];
    const map = new Map();
    for (const p of ps) {
      const k = `${accessor(matched[p], id)}`;
      let g = map.get(k);
      if (!g) { g = { first: p, members: [] }; map.set(k, g); }
      g.members.push(p);
    }
    const groups = [...map.values()];
    // a group row's value for entry j: its first row's, when the entry's column groups at this depth or above
    const gkey = sorting.map((s, j) => {
      const gi = grouping.indexOf(s.id);
      const { size } = ranks[j];
      return gi !== -1 && gi <= depth ? (g) => key[j](g.first) : () => size;
    });
    const sortedGroups = sortBy(groups, gkey, sizes);
    for (const g of sortedGroups) g.children = depth + 1 < grouping.length ? groupUp(g.members, depth + 1) : sortLeaves(g.members);
    return sortedGroups;
  };

  const limit = view.limit;
  const total = all.length;
  const error = errors.join('; ') || null;
  if (!grouping.length) {
    const leaves = sortLeaves(positions(M));
    const table = Uint32Array.from(leaves, (p) => dsIndex[p]);
    return { rows: limit ? table.slice(0, limit) : table, table, groups: null, total, matched: M, error };
  }
  const top = groupUp(positions(M), 0);
  // collect(): the flat row model walked in order (a group row, then what is under it), with limit
  const leavesOf = (g) => (g.children.length && g.children[0].children ? g.children.flatMap(leavesOf) : g.children);
  const leafKey = (g, property) => cellValue(matched[leavesOf(g)[0]][property]) ?? null;
  const table = [];
  const rows = [];
  const byKey = new Map();
  const take = (p, ...lists) => { table.push(dsIndex[p]); if (!limit || rows.length < limit) { rows.push(dsIndex[p]); for (const l of lists) l.push(dsIndex[p]); } };
  for (const g of top) {
    const g0 = { key: leafKey(g, grouping[0]), property: grouping[0], rows: [], ...(grouping[1] ? { groups: [] } : {}) };
    byKey.set(JSON.stringify(g0.key), g0);
    if (grouping[1]) {
      for (const s of g.children) {
        const g1 = { key: leafKey(s, grouping[1]), property: grouping[1], rows: [] };
        g0.groups.push(g1);
        for (const p of s.children) take(p, g0.rows, g1.rows);
      }
    } else for (const p of g.children) take(p, g0.rows);
  }
  const order = (view.groupOrder || []).map((k) => JSON.stringify(k));
  const namedGroups = order.map((k) => byKey.get(k) || { key: JSON.parse(k), property: grouping[0], rows: [], ...(grouping[1] ? { groups: [] } : {}) });
  const rest = [...byKey.entries()].filter(([k, g]) => !order.includes(k) && (!limit || g.rows.length)).map(([, g]) => g);
  const groups = [...namedGroups, ...rest];
  if (limit) for (const g of groups) if (g.groups) g.groups = g.groups.filter((s) => s.rows.length);
  const typed = (gs) => gs.map((g) => ({ key: g.key, property: g.property, rows: Uint32Array.from(g.rows), ...(g.groups ? { groups: typed(g.groups) } : {}) }));
  return { rows: Uint32Array.from(groups.flatMap((g) => g.rows)), table: Uint32Array.from(table), groups: typed(groups), total, matched: M, error };
}

