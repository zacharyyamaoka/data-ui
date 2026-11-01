// The rail's counts from the row-model worker (rowmodel-worker.js 'counts'), held to railCounts() computed the way
// <data-facets> computed them before the worker (the view's filters, then the rail read out of the all-views filter,
// the custom clauses as one test; the code below is that old _state(), kept here as the oracle). Every faceted
// gallery example, every view, with no selection and with one ticked value per values facet and a range; and 100,000
// bootstrapped actuators under the large-table rail. The answer crosses the stand-in Worker's structured clone, so it
// must be the very object the rail would compute, not merely close.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset, loadDataset } from '../../packages/core/src/data.js';
import { properties } from '../../packages/core/src/rowmodel.js';
import { compileFilters } from '../../packages/core/src/grammar.js';
import { facetSpecs, railConfig, toRail, fromRail, railCounts } from '../../packages/core/src/facets.js';
import { workerServer, createRowModelWorker } from '../../packages/core/src/rowmodel-worker.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples');
// a fixed clock away from today, so a count dated by the worker's own clock instead of the page's would show
const NOW = new Date('2027-03-01T12:00:00Z').getTime();

class StandInWorker {
  constructor() {
    this.handle = workerServer((m, t) => { const c = structuredClone(m, { transfer: t || [] }); setTimeout(() => this.onmessage && this.onmessage({ data: c }), 0); });
  }
  postMessage(m, t) { const c = structuredClone(m, { transfer: t || [] }); setTimeout(() => this.handle(c), 0); }
  terminate() {}
}
const until = async (fn) => { for (let i = 0; i < 2000 && !fn(); i++) await new Promise((r) => setTimeout(r, 1)); assert.ok(fn()); };

// <data-facets>' _state() and _recount() as they were before the worker (ec3e52e): the oracle
function oracle(data, view, filters, specs) {
  const cfg = railConfig(specs);
  const rail = toRail(filters, cfg);
  let viewKeep = null, restKeep = null;
  try { viewKeep = compileFilters(view.filters); } catch { viewKeep = null; }
  try { restKeep = compileFilters(rail.rest.length ? { and: rail.rest } : null); } catch { restKeep = null; }
  const rows = viewKeep ? data.rows.filter(viewKeep) : data.rows;
  return railCounts(rows, rail.facets, specs, restKeep || (() => true), { now: new Date(NOW) });
}

// a selection on the rail: the first value of each values facet ticked, the first range narrowed to its upper half
function ticked(data, specs, base) {
  const counts = oracle(data, {}, base.filters, specs);
  const facets = {};
  for (const s of specs) {
    const c = counts[s.key];
    if (c && c.counts && Object.keys(c.counts).length && !facets[s.property]) facets[s.property] = { values: [Object.keys(c.counts)[0]] };
    else if (c && c.domain && c.domain.min !== null && typeof c.domain.min === 'number' && !facets[s.property]) facets[s.property] = { min: (c.domain.min + c.domain.max) / 2 };
  }
  return fromRail(facets, toRail(base.filters, railConfig(specs)).rest);
}

async function loadCase(dir) {
  const base = parseBase(readFileSync(join(dir, 'views.base'), 'utf8'));
  if (!base.data) return null;
  const file = join(dir, base.data);
  if (!existsSync(file)) return null;
  const get = async (u) => { const f = decodeURIComponent(new URL(u).pathname); return existsSync(f) ? new Response(readFileSync(f)) : new Response('', { status: 404 }); };
  const data = await loadDataset(new URL(`file://${file}`).href, { fetch: get });
  return { base, data };
}

test('worker counts = the rail\'s own railCounts(): every faceted gallery example, every view, with and without a selection', async () => {
  let compared = 0;
  for (const name of readdirSync(EX).sort()) {
    const dir = join(EX, name);
    if (!existsSync(join(dir, 'views.base')) || !readFileSync(join(dir, 'views.base'), 'utf8').includes('facets')) continue;
    const c = await loadCase(dir);
    if (!c) continue;
    const { base, data } = c;
    const props = properties(data, base);
    const w = createRowModelWorker(data, { Worker: StandInWorker });
    await until(() => w.ready);
    for (const view of (base.views || []).map((v) => ({ type: 'table', ...v }))) {
      const specs = facetSpecs(base, view, props);
      if (!specs.length) continue;
      // and a custom clause the rail cannot draw (an ||): it reaches the counts as the `rest` test
      // (it drops the commonest value of the first values facet, so it changes what every other facet counts)
      const plain = oracle(data, view, base.filters, specs);
      const vs = specs.find((s) => plain[s.key] && plain[s.key].counts && Object.keys(plain[s.key].counts).length) || specs[0];
      const p = JSON.stringify(vs.property);
      const top = plain[vs.key] && plain[vs.key].counts ? Object.keys(plain[vs.key].counts)[0] : 'zzz';
      const custom = { and: [...((base.filters && base.filters.and) || []), `note[${p}] != ${JSON.stringify(top)} || note[${p}] == "zzz"`] };
      for (const filters of [base.filters, ticked(data, specs, base), custom]) {
        const got = await w.counts(view, filters, specs, NOW);
        assert.deepEqual(got, oracle(data, view, filters, specs), `${name} / ${view.name}`);
        compared++;
        if (filters === custom) assert.ok(toRail(custom, railConfig(specs)).rest.length, `${name}: the clause is custom`);
      }
    }
    w.terminate();
  }
  assert.ok(compared >= 30, `${compared} rails compared`);
});

test('worker counts = railCounts() on 100,000 rows under the large-table rail (no selection, a ticked brand, a range)', async () => {
  const src = normalizeDataset(JSON.parse(readFileSync(join(EX, 'robotparts-actuators', 'actuators.json'), 'utf8')));
  const data = { ...src, rows: Array.from({ length: 100000 }, (_, i) => ({ ...src.rows[i % src.rows.length], id: `r${i}` })) };
  const base = parseBase(readFileSync(join(ROOT, 'bench', 'scenarios', 'large-table', 'views.base'), 'utf8'));
  const view = { type: 'table', ...base.views[0] };
  const specs = facetSpecs(base, view, properties(data, base));
  const w = createRowModelWorker(data, { Worker: StandInWorker, slice: 20000 });
  await until(() => w.ready);
  for (const filters of [base.filters, { and: ['brand == "CubeMars"'] }, ticked(data, specs, base)]) {
    assert.deepEqual(await w.counts(view, filters, specs, NOW), oracle(data, view, filters, specs), JSON.stringify(filters));
  }
  w.terminate();
});

test('worker counts: a newer count supersedes an older one; a model and a count in flight do not supersede each other', async () => {
  const src = normalizeDataset(JSON.parse(readFileSync(join(EX, 'robotparts-actuators', 'actuators.json'), 'utf8')));
  const base = parseBase(readFileSync(join(EX, 'robotparts-actuators', 'views.base'), 'utf8'));
  const view = { type: 'table', ...base.views[0] };
  const specs = facetSpecs(base, view, properties(src, base));
  const w = createRowModelWorker(src, { Worker: StandInWorker });
  await until(() => w.ready);
  const c1 = w.counts(view, base.filters, specs, NOW);
  const m = w.model(base, view, {});
  const c2 = w.counts(view, { and: ['brand == "CubeMars"'] }, specs, NOW);
  assert.equal(await c1, null);
  assert.ok((await m).rows.length > 0, 'the model still lands');
  assert.deepEqual(await c2, oracle(src, view, { and: ['brand == "CubeMars"'] }, specs));
  w.terminate();
});
