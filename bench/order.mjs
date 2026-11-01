// The row model's order at 100,000 rows, three ways, timed in Node (lane/perf-worker, step 3):
//
//   taskset -c 0-3 node --expose-gc bench/order.mjs [CHECKOUT] [--rows 100000] [--runs 7]
//
//   orderOf      the worker's original answer: the real rowModel() (TanStack's sorted row model), as indices
//   fastOrder    order.js: typed-array sort keys; "cold" ranks every sort column first, "warm" reuses the ranks
//                (a second sort, a search key or a filter on data the worker already ranked)
//   ranks        the parts of a cold fastOrder: one number column (Float64 sort + binary search), one text column
//                (each distinct string ranked once with the model's collator)
//   top 50       a partial sort for the first page only (not shipped: footers, group counts and the scroll extent read
//                the whole model; measured to know what it would buy)
// Rows: robotparts' actuators bootstrapped to N, each `model` made unique ("<model> #<i>"), as bench/scenarios/
// large-table/generate.py does; views: large-table's Table (text sort), Grouped (brand, then a number), a number sort.
import { readFileSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? Number(args[i + 1]) : d; };
const root = resolve(args.find((a, i) => !a.startsWith('--') && !args[i - 1]?.startsWith('--')) || join(HERE, '..'));
const N = opt('--rows', 100000), RUNS = opt('--runs', 7);
const src = (f) => import(pathToFileURL(join(root, 'packages', 'core', 'src', f)).href);
const [{ parseBase }, { normalizeDataset }, rm, rw, od] = await Promise.all(['base.js', 'data.js', 'rowmodel.js', 'rowmodel-worker.js', 'order.js'].map(src));

const act = normalizeDataset(JSON.parse(readFileSync(join(HERE, 'scenarios', 'robotparts-actuators', 'actuators.json'), 'utf8')));
const data = { ...act, rows: Array.from({ length: N }, (_, i) => { const r = act.rows[i % act.rows.length]; return { ...r, id: `${r.id}-${i}`, model: `${r.model} #${i}` }; }) };
const base = parseBase(readFileSync(join(HERE, 'scenarios', 'large-table', 'views.base'), 'utf8'));
const views = [base.views[0], base.views[1], { ...base.views[0], name: 'Number', sort: [{ property: 'peak_torque', direction: 'DESC' }] }];
const indexOf = new Map(data.rows.map((r, i) => [r, i]));

function time(fn, runs = RUNS) {
  const ms = [];
  for (let i = 0; i < runs; i++) { if (globalThis.gc) globalThis.gc(); const t = performance.now(); fn(); ms.push(performance.now() - t); }
  ms.sort((a, b) => a - b);
  return +ms[ms.length >> 1].toFixed(1);
}

function top50(view) {
  // the first page of a flat one-key sort by selection: one pass with a small sorted buffer (exact for that page only)
  const s = view.sort[0];
  const { rows } = rm.matchedRows(data, base, view, {});
  const val = (r) => { const v = rm.isEmpty(r[s.property]) ? undefined : (r[s.property] && r[s.property].value !== undefined ? r[s.property].value : r[s.property]); return v; };
  const cmp = (a, b) => { const x = val(a), y = val(b); if (x === undefined || y === undefined) return x === y ? 0 : x === undefined ? 1 : -1; const d = typeof x === 'number' && typeof y === 'number' ? x - y : rm.TEXT_ORDER.compare(String(x), String(y)); return s.direction === 'DESC' ? -d : d; };
  const buf = [];
  for (const r of rows) {
    if (buf.length < 50) { buf.push(r); if (buf.length === 50) buf.sort(cmp); continue; }
    if (cmp(r, buf[49]) >= 0) continue;
    let lo = 0, hi = 49; while (lo < hi) { const m = (lo + hi) >> 1; if (cmp(buf[m], r) <= 0) lo = m + 1; else hi = m; }
    buf.splice(lo, 0, r); buf.pop();
  }
  return buf;
}

const out = { rows: N, checkout: root, views: {} };
for (const view of views) {
  const v = {};
  v.rowModel = time(() => rm.rowModel(data, base, view).table.getRowModel());
  v.orderOf = time(() => rw.orderOf(data, base, view, {}, indexOf));
  v.fastCold = time(() => od.fastOrder(data, base, view, {}, od.rankCache(data)));
  const warm = od.rankCache(data);
  od.fastOrder(data, base, view, {}, warm);
  v.fastWarm = time(() => od.fastOrder(data, base, view, {}, warm));
  v.fastWarmSearch = time(() => od.fastOrder(data, base, view, { query: 'ak' }, warm));
  const o = od.fastOrder(data, base, view, {}, warm);
  v.rebuildOnMain = time(() => rw.modelFromOrder(data, base, view, o).table.getRowModel(), 3);
  v.fastModelOnMain = time(() => rw.modelFromOrder(data, base, view, od.fastOrder(data, base, view, {}, od.rankCache(data))).table.getRowModel(), 3);
  if (!view.groupBy) v.top50 = time(() => top50(view));
  out.views[view.name] = v;
}
out.ranks = { number: time(() => od.columnRanks(data.rows, 'peak_torque')), textUnique: time(() => od.columnRanks(data.rows, 'model')), textFew: time(() => od.columnRanks(data.rows, 'brand')) };
console.log(JSON.stringify(out, null, 1));
