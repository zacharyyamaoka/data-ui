// The core's hot functions timed in Node, on the bench's real actuators: the low-noise half of a before/after, next
// to the browser bench (bench/runner.py). It imports the kit from any checkout, so one command times the parent and
// the change:
//
//   node --expose-gc bench/micro.mjs [CHECKOUT] [--json] [--only fmt40,model]
//
// WHY next to the browser bench, not instead of it: the browser numbers are what Zach feels, but on this shared
// machine they move ±30% with load; a pure function timed 15 times (median, GC outside the timing) shows whether an
// item changed the work at all. The perf review (2026-10-26) took its "15.4 → 1.7 ms" and "116 → 41 ms" this way.
import { readFileSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const json = args.includes('--json');
const onlyAt = args.indexOf('--only');
const only = onlyAt >= 0 ? new Set(args[onlyAt + 1].split(',')) : null;
const root = resolve(args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--only') || join(HERE, '..'));
const src = (f) => import(pathToFileURL(join(root, 'packages', 'core', 'src', f)).href);
const [{ parseBase }, { normalizeDataset }, rm, fmt, gr, fc] = await Promise.all(
  ['base.js', 'data.js', 'rowmodel.js', 'format.js', 'grammar.js', 'facets.js'].map(src));

// the data is always this checkout's bench copy, so both sides of a before/after time the same rows
const SC = join(HERE, 'scenarios', 'robotparts-actuators');
const base = parseBase(readFileSync(join(SC, 'views.base'), 'utf8'));
const data = normalizeDataset(JSON.parse(readFileSync(join(SC, base.data), 'utf8')));
const byBrand = base.views[0];
const props = rm.properties(data, base);

function grow(n) {
  const rows = [];
  for (let i = 0; i < n; i++) { const r = data.rows[i % data.rows.length]; rows.push({ ...r, id: `${r.id}~${i}` }); }
  return { ...data, rows };
}
const d10k = grow(10000), d100k = grow(100000);

function time(fn, { warm = 3, runs = 15 } = {}) {
  for (let i = 0; i < warm; i++) fn();
  const ms = [];
  for (let i = 0; i < runs; i++) {
    if (globalThis.gc) globalThis.gc();
    const t = performance.now(); fn(); ms.push(performance.now() - t);
  }
  ms.sort((a, b) => a - b);
  return { median: +ms[ms.length >> 1].toFixed(2), min: +ms[0].toFixed(2), max: +ms[ms.length - 1].toFixed(2) };
}

const first40 = rm.rowModel(data, base, byBrand).rows.slice(0, 40);
const specs = fc.facetSpecs(base, byBrand, props);
const v100k = d100k.rows.map((r) => r.peak_torque);

const CASES = {
  // a first table page: 40 rows x the view's columns, as the table view writes each cell
  fmt40: () => { let s = ''; for (const r of first40) for (const id of byBrand.order) s += fmt.valueHtml(r[id], props[id]); return s.length; },
  // every cell of the dataset
  fmtAll: () => { let s = 0; for (const r of data.rows) for (const id in props) s += fmt.valueHtml(r[id], props[id]).length; return s; },
  // the headline view's model: 1,149 rows grouped by brand, sorted by peak torque
  model: () => rm.rowModel(data, base, byBrand).rows.length,
  model10kGrouped: () => rm.rowModel(d10k, base, byBrand).rows.length,
  model100kSorted: () => rm.rowModel(d100k, base, { type: 'table', sort: [{ property: 'peak_torque', direction: 'DESC' }] }).rows.length,
  // a table footer at 100k: Count, Min, Max, Sum, Average (Median sorts, by definition)
  summaries100k: () => ['Count', 'Min', 'Max', 'Sum', 'Average', 'Filled', 'Empty'].map((s) => gr.summarize(v100k, s)),
  // the rail: nine facets, nothing chosen, then one brand chosen (disjunctive counts)
  rail: () => fc.railCounts(data.rows, {}, specs),
  railBrand: () => fc.railCounts(data.rows, { brand: { values: ['Feetech'] } }, specs),
  rail100k: () => fc.railCounts(d100k.rows, { brand: { values: ['Feetech'] } }, specs),
};

const out = { checkout: root, node: process.version };
for (const [name, fn] of Object.entries(CASES)) {
  if (only && !only.has(name)) continue;
  const big = /100k|10k/.test(name);
  out[name] = time(fn, big ? { warm: 1, runs: 7 } : {});
  if (!json) console.log(`${name.padEnd(16)} median ${String(out[name].median).padStart(8)} ms  (min ${out[name].min}, max ${out[name].max})`);
}
if (json) console.log(JSON.stringify(out));
