/* data-ui core, as small as the demo needs: ONE row model and a view-plugin registry (docs/VIEWS.md §4).

   The row model is the table lane's pipeline lifted out of <data-views> so every view reads it:
     the .base file's filters AND the view's filters (the lane's Bases evaluator, grammar.js)
     -> TanStack Table: sort by the view's `sort`, group by its `groupBy` (groupOrder decides the order of groups)
     -> {rows, groups}: rows are the same objects the table draws, in the same order.
   WHY one model: a link, a saved view or an agent's edit means the same rows whichever view draws them
   (Zach, 2026-10-25: "1 dataset, 1 base file, many views"). */

import * as T from '@tanstack/table-core';
import { storeReactivityBindings } from '@tanstack/table-core/store-reactivity-bindings';
import { compileFilters } from './grammar.js';

const FEATURES = T.tableFeatures({
  coreReactivityFeature: storeReactivityBindings(),
  columnGroupingFeature: T.columnGroupingFeature,
  groupedRowModel: T.createGroupedRowModel(),
  rowExpandingFeature: T.rowExpandingFeature,
  expandedRowModel: T.createExpandedRowModel(),
  rowSortingFeature: T.rowSortingFeature,
  sortedRowModel: T.createSortedRowModel(),
});

const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** The view's rows: filtered, sorted and grouped exactly as the table view would draw them. */
export function rowModel(dataset, base, view) {
  let rows = dataset.rows;
  let error = null;
  try {
    for (const f of [base.filters, view.filters]) {
      const keep = compileFilters(f);
      if (keep) rows = rows.filter(keep);
    }
  } catch (err) { error = err.message; }
  const props = dataset.properties;
  const columns = Object.keys(props).map((id) => ({
    id,
    accessorFn: (r) => (isEmpty(r[id]) ? undefined : Array.isArray(r[id]) ? r[id].join(', ') : r[id]),
    sortUndefined: 'last',
    sortFn: (a, b, cid) => {
      const x = a.getValue(cid), y = b.getValue(cid);
      if (isNum(x) && isNum(y)) return x - y;
      if (isNum(x) !== isNum(y)) return isNum(x) ? -1 : 1;
      return String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: 'base' });
    },
  }));
  const group = view.groupBy && props[view.groupBy.property] ? view.groupBy.property : null;
  // WHY a group sorts only with a direction: Bases' groupBy without one keeps dataset order (the table lane's rule)
  const sorting = [
    ...(group && view.groupBy.direction ? [{ id: group, desc: view.groupBy.direction === 'DESC' }] : []),
    ...(view.sort || []).filter((s) => props[s.property]).map((s) => ({ id: s.property, desc: s.direction === 'DESC' })),
  ];
  const table = T.constructTable({
    features: FEATURES, columns, data: rows, getRowId: (r) => String(r.id),
    groupedColumnMode: false,
    initialState: { grouping: group ? [group] : [], sorting, expanded: true },
  });
  const flat = table.getRowModel().rows;
  const out = { rows: [], groups: null, total: dataset.rows.length, error };
  if (!group) {
    out.rows = flat.map((r) => r.original);
    return out;
  }
  const byKey = new Map();
  let current = null;
  for (const r of flat) {
    if (r.getIsGrouped()) {
      const leaves = r.getLeafRows().filter((x) => !x.getIsGrouped());
      const key = leaves.length ? leaves[0].original[group] ?? null : null;
      current = { key, rows: [] };
      byKey.set(JSON.stringify(key), current);
    } else if (current) {
      current.rows.push(r.original);
      out.rows.push(r.original);
    }
  }
  // WHY groupOrder decides: it is the Bases key a board writes when a column is dragged; a group it does not name
  // follows in dataset order, and a named group with no rows still shows (an empty column is information).
  const order = (view.groupOrder || []).map((k) => JSON.stringify(k));
  const named = order.map((k) => byKey.get(k) || { key: JSON.parse(k), rows: [] });
  const rest = [...byKey.entries()].filter(([k]) => !order.includes(k)).map(([, g]) => g);
  out.groups = [...named, ...rest];
  return out;
}

/* ------------------------------------------------------------------------------------------------ the registry
   A view plugin is {name, icon, load}: load() resolves to a class with update(input) and destroy().
   WHY load() and not the class: a page pays for a view's library only when that view is opened (the chart's
   Vega bundle is 280 KB gzipped; a robotparts part page never opens it). Mirrors Obsidian's
   registerBasesView(id, {name, icon, factory, options}). */

const registry = new Map();

export function registerView(type, plugin) {
  if (registry.has(type)) throw new Error(`a view is already registered for type: ${type}`);
  registry.set(type, plugin);
}

export function viewPlugin(type) {
  return registry.get(type) || null;
}

/** The page's --data-* tokens (SPEC §10), resolved to concrete colours for libraries that draw on canvas or SVG. */
export function resolveTokens(el) {
  const cs = getComputedStyle(el);
  const get = (name) => cs.getPropertyValue(name).trim();
  const names = ['data-bg', 'data-fg', 'data-muted', 'data-border', 'data-accent', 'data-warn', ...[1, 2, 3, 4, 5, 6, 7, 8].map((i) => `data-series-${i}`)];
  const css = Object.fromEntries(names.map((n) => [n, get(`--${n}`)]));
  return {
    css, bg: css['data-bg'], fg: css['data-fg'], muted: css['data-muted'], border: css['data-border'], accent: css['data-accent'],
    series: names.filter((n) => n.startsWith('data-series')).map((n) => css[n]).filter(Boolean),
    font: get('--data-font') || cs.fontFamily,
  };
}
