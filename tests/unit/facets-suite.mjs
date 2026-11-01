// The rail's laws, as one function over a facets module, so tests/unit/facets.test.mjs can run them on the real
// packages/core/src/facets.js and on mutated copies of it (a law that a broken projection still passes is no law).
//   suite(F, rows) -> [failure messages]; empty means every law holds.
// The independent oracle is grammar.js's compileFilters: the evaluator every view runs on the stored tree.
import { compileFilters, cellValue } from '../../packages/core/src/grammar.js';
import assert from 'node:assert/strict';

/** One facet spec per kind, over the Filters case's columns (gallery/examples/filters-gallery). */
export const SPEC_LIST = [
  { property: 'brand', as: 'values', exclude: true }, { property: 'drivetrain', as: 'select' }, { property: 'in_stock', as: 'toggle', value: 'yes' },
  { property: 'photo', as: 'has', properties: ['photo', 'torque_density', 'price'] }, { property: 'price', as: 'range' },
  { property: 'mass', as: 'slider', log: true }, { property: 'peak_torque', as: 'slider-histogram', log: true },
  { property: 'torque_density', as: 'buckets', buckets: [20, 50] }, { property: 'level', as: 'rating' }, { property: 'level', as: 'min-level' },
  { property: 'listed', as: 'date' }, { property: 'buses', as: 'chips' }, { property: 'form', as: 'gallery' }, { property: 'voltage', as: 'listbox' },
  { property: 'gear_ratio', as: 'grid' }, { property: 'checks', as: 'picture-list' }, { property: 'model', as: 'search', properties: ['model', 'name'] },
  { property: 'od', as: 'swatch' }, { as: 'popular', options: ['length < 40'] }, { as: 'current' },
];

/** A state per kind, each the shape the rail writes when you use that kind. */
export const STATES = {
  values: { brand: { values: ['Steadywin', 'CubeMars'], match: 'equals', exclude: ['KST'], excludeMatch: 'equals' } },
  select: { drivetrain: { values: ['geared'], match: 'equals' } },
  toggle: { in_stock: { values: ['yes'], match: 'equals' } },
  has: { photo: { has: true }, torque_density: { has: true } },
  'has any': { photo: { hasAny: ['photo', 'price'] } },
  range: { price: { min: 50, max: 500 } },
  slider: { mass: { min: 120, max: 2500 } },
  'slider-histogram': { peak_torque: { min: 1.5 } },
  buckets: { torque_density: { min: 20, max: 50, maxOpen: true } },
  rating: { level: { min: 2 } },
  'min-level': { level: { min: 4 } },
  date: { listed: { min: '2026-10-19' } },
  'date older': { listed: { max: '2026-10-12', maxOpen: true } },
  chips: { buses: { values: ['can', 'ethercat'], match: 'contains' } },
  gallery: { form: { values: ['hobby servo'], match: 'equals' } },
  listbox: { voltage: { values: [24, 48], match: 'equals' } },
  grid: { gear_ratio: { values: [1, 9], match: 'equals' } },
  'picture-list': { checks: { values: ['cad'], match: 'contains' } },
  search: { model: { text: 'steadywin', textIn: ['model', 'name'] } },
  swatch: { od: { values: [53], match: 'equals' } },
  popular: { length: { max: 40, maxOpen: true } },
};

/** The URL the way <data-views> writes and reads it: append, toString with readable commas, parse again. */
export function throughUrl(params) {
  const q = new URLSearchParams();
  for (const [k, v] of params) q.append(k, v);
  return [...new URLSearchParams(q.toString().replace(/%2C/gi, ',')).entries()];
}

export function suite(F, data) {
  const fail = [];
  const rows = data.rows;
  const law = (name, fn) => { try { fn(); } catch (e) { fail.push(`${name}: ${e.message.split('\n')[0]}`); } };
  const props = Object.fromEntries(Object.entries(data.properties).map(([k, v]) => [k, { id: k, type: 'text', ...v, label: k }]));
  const specs = F.facetSpecs({ facets: SPEC_LIST }, null, props);
  const cfg = F.railConfig(specs);
  for (const [kind, state] of Object.entries(STATES)) {
    law(`${kind}: rail -> tree -> rail is the identity`, () => assert.deepEqual(F.toRail(F.fromRail(state), cfg), { facets: state, rest: [] }));
    law(`${kind}: the rail picks the rows the stored tree picks`, () => {
      const keep = compileFilters(F.fromRail(state));
      const picked = rows.filter(keep).map((r) => r.id);
      assert.ok(picked.length > 0 && picked.length < rows.length, `a real selection (${picked.length} of ${rows.length})`);
      assert.deepEqual(rows.filter((r) => F.matchesRail(r, state)).map((r) => r.id), picked);
    });
    law(`${kind}: state -> URL -> state is the identity`, () => assert.deepEqual(F.paramsRail(throughUrl(F.railParams(state)), props, F.railProperties(specs), cfg), state));
  }
  law('every kind at once round-trips', () => {
    const all = {};
    for (const [k, st] of Object.entries(STATES)) if (k !== 'has any' && k !== 'date older') for (const [p, f] of Object.entries(st)) all[p] = { ...(all[p] || {}), ...f };
    assert.deepEqual(F.toRail(F.fromRail(all), cfg).facets, all);
  });
  law('disjunctive counts: a values facet ignores its own ticks', () => {
    const c = F.railCounts(rows, STATES.values, specs);
    const brands = new Set(rows.map((r) => r.brand));
    assert.equal(Object.keys(c.brand.counts).length, brands.size);
    assert.equal(c.brand.counts.KST, rows.filter((r) => r.brand === 'KST').length);
    assert.ok(c.brand.n > rows.filter((r) => F.matchesRail(r, STATES.values)).length, 'the counts read past the brand ticks');
  });
  law('buckets count what each bucket would pick', () => {
    const c = F.railCounts(rows, {}, specs).torque_density;
    for (const b of c.buckets) assert.equal(b.n, rows.filter((r) => F.matchesFacet(r, 'torque_density', b)).length, b.label);
  });
  law('a rating level counts the rows at or above it', () => {
    const c = F.railCounts(rows, {}, specs).level;
    for (const { level, n } of c.levels) assert.equal(n, rows.filter((r) => typeof cellValue(r.level) === 'number' && cellValue(r.level) >= level).length);
  });
  return fail;
}
