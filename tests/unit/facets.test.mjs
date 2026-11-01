// The standard filter kinds (docs/CONTRACT.md §7, amendment 2026-10-26 (filters)): each kind's projection both ways,
// their counts, their URL, the fallback for an unknown kind, what stays custom, and a mutation run that proves the
// laws in facets-suite.mjs go red when one projection breaks. Data: the Filters case's 1,149 real actuators.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import * as F from '../../packages/core/src/facets.js';
import { compileFilters } from '../../packages/core/src/grammar.js';
import { checkText } from '../../packages/core/src/check.js';
import { suite, throughUrl, SPEC_LIST, STATES } from './facets-suite.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SRC = join(ROOT, 'packages', 'core', 'src', 'facets.js');
const DATA = JSON.parse(readFileSync(join(ROOT, 'gallery', 'examples', 'filters-gallery', 'actuators.json'), 'utf8'));
const PROPS = Object.fromEntries(Object.entries(DATA.properties).map(([k, v]) => [k, { id: k, type: 'text', ...v, label: k }]));
const SPECS = F.facetSpecs({ facets: SPEC_LIST }, null, PROPS);
const CFG = F.railConfig(SPECS);

test('every kind: rail -> tree -> rail is the identity, the rail picks the rows grammar.js picks, the URL round-trips', () => {
  assert.equal(DATA.rows.length, 1149);
  assert.deepEqual(suite(F, DATA), []);
});

test('the wide forms each kind writes, as Bases expressions', () => {
  assert.deepEqual(F.fromRail(STATES.values), { and: [{ or: ['brand == "Steadywin"', 'brand == "CubeMars"'] }, { not: ['brand == "KST"'] }] });
  assert.deepEqual(F.fromRail(STATES['has any']), { and: [{ or: ['!photo.isEmpty()', '!price.isEmpty()'] }] });
  assert.deepEqual(F.fromRail(STATES.date), { and: ['listed >= "2026-10-19"'] });
  assert.deepEqual(F.fromRail(STATES['date older']), { and: ['listed < "2026-10-12"'] });
  assert.deepEqual(F.fromRail(STATES.search), { and: [{ or: ['model.contains("steadywin")', 'name.contains("steadywin")'] }] });
  assert.deepEqual(F.fromRail(STATES.buckets), { and: ['torque_density >= 20', 'torque_density < 50'] });
  assert.deepEqual(F.fromRail({ model: { text: 'AK', textIn: ['model'], textMatch: 'startsWith' } }), { and: ['model.startsWith("AK")'] });
});

test('what this rail cannot draw stays custom, verbatim and in order', () => {
  const tree = { and: ['drivetrain == "geared"', { or: ['drivetrain == "motor"', 'drivetrain == "geared"'] }, 'level <= 3', 'level >= 2', { not: ['form == "wheel hub"'] }, 'rated_torque > 1', 'in_stock == "no"'] };
  const { facets, rest } = F.toRail({ and: tree.and.slice(1) }, CFG);
  // two values under a single-choice facet; a max under "& up"; an exclude where the facet has no exclude: true;
  // a property no facet stands over; a toggle's off value
  assert.deepEqual(rest, [{ or: ['drivetrain == "motor"', 'drivetrain == "geared"'] }, 'level <= 3', { not: ['form == "wheel hub"'] }, 'rated_torque > 1', 'in_stock == "no"']);
  assert.deepEqual(facets, { level: { min: 2 } });
  assert.deepEqual(F.fromRail(facets, rest).and.length, 6, 'nothing dropped');
  // without a config, the original normal form only: the not stays custom (tools/facets.test.mjs pins the rest)
  assert.deepEqual(F.toRail({ and: [{ not: ['brand == "KST"'] }] }).rest, [{ not: ['brand == "KST"'] }]);
});

test('counts: a tree level applies the levels above it; has, popular, date presets and histograms', () => {
  const specs = F.facetSpecs({ facets: [{ property: 'form', as: 'tree', levels: ['form', 'brand'] }, { as: 'popular', options: ['price < 100', 'buses.contains("can")'] },
    { property: 'listed', as: 'date', presets: ['7d'], older: ['14d'] }, { property: 'peak_torque', as: 'slider-histogram', log: true }] }, null, PROPS);
  const state = { form: { values: ['hobby servo'], match: 'equals' } };
  const c = F.railCounts(DATA.rows, state, specs, () => true, { now: new Date('2026-10-26T12:00:00') });
  const servos = DATA.rows.filter((r) => r.form === 'hobby servo');
  assert.equal(c.form[0]['integrated actuator'], DATA.rows.filter((r) => r.form === 'integrated actuator').length, 'level 0 ignores its own pick');
  assert.equal(Object.values(c.form[1]).reduce((a, b) => a + b, 0), servos.length, 'level 1 counts only hobby servos');
  const [cheap, can] = c['@popular1'];
  assert.equal(cheap, servos.filter(compileFilters('price < 100')).length);
  assert.equal(can, servos.filter(compileFilters('buses.contains("can")')).length);
  const d = c.listed;
  assert.equal(d.presets[0].min, '2026-10-19');
  assert.equal(d.presets[0].n, servos.filter(compileFilters('listed >= "2026-10-19"')).length);
  assert.equal(d.older[0].n, servos.filter(compileFilters('listed < "2026-10-12"')).length);
  const h = c.peak_torque;
  assert.equal(h.bins.reduce((a, b) => a + b.n, 0), h.n, 'every servo with a positive torque lands in one bar');
  assert.ok(h.binsAll.reduce((a, b) => a + b.n, 0) > h.n, 'the faint layer is every row');
});

test('URL: readable, and the old links still read the same', () => {
  const q = new URLSearchParams(throughUrl(F.railParams({ ...STATES.values, ...STATES.buckets, ...STATES.search, ...STATES.date })));
  assert.equal(q.toString().replace(/%2C/gi, ','), 'brand=Steadywin,CubeMars&brand%21=KST&torque_density=20..%3C50&model%7E=steadywin&listed=2026-10-19..');
  const old = [['brand', 'Steadywin,CubeMars'], ['peak_torque', '10..20'], ['has', 'torque_density']];
  assert.deepEqual(F.paramsRail(old, PROPS, F.railProperties(SPECS), CFG), {
    brand: { values: ['Steadywin', 'CubeMars'], match: 'equals' }, peak_torque: { min: 10, max: 20 }, torque_density: { has: true } });
  const comma = { brand: { values: ['A, Inc.', 'B'], match: 'equals' } };
  assert.deepEqual(F.paramsRail(throughUrl(F.railParams(comma)), PROPS, new Set(['brand']), CFG), comma, 'a comma inside a value survives');
});

test('an unknown kind falls back to values, says so, and the checker names the close one', () => {
  const [s] = F.facetSpecs({ facets: [{ property: 'brand', as: 'slidr' }] }, null, PROPS);
  assert.equal(s.as, 'values');
  assert.equal(s.unknown, 'slidr');
  const problems = checkText('facets:\n  - { property: brand, as: slidr }\n  - { property: price, as: buckets, bukets: [1, 10] }\n  - { property: brand, as: slider }\n  - { as: tree }\nviews:\n  - type: table\n    name: A\n  - type: table\n    name: B\n    facets: [{ property: price, as: rating, styl: stars }]\n',
    { properties: new Set(Object.keys(PROPS)), types: Object.fromEntries(Object.entries(PROPS).map(([k, v]) => [k, v.type])), datasetName: 'actuators.json' });
  const text = problems.map((p) => `${p.level} ${p.path.join('.')}: ${p.message}`);
  assert.ok(text.some((t) => t.includes("facets.0.as") && t.includes("did you mean 'slider'")), text.join('\n'));
  assert.ok(text.some((t) => t.includes("unknown key 'bukets'") && t.includes("did you mean 'buckets'")), text.join('\n'));
  assert.ok(text.some((t) => t.startsWith('error facets.2.as') && t.includes("'slider' needs a number property; 'brand' is text")), text.join('\n'));
  assert.ok(text.some((t) => t.startsWith('error facets.3') && t.includes("a tree facet needs 'property' or 'levels'")), text.join('\n'));
  assert.ok(text.some((t) => t.includes("views.1.facets.0") && t.includes("unknown key 'styl'") && t.includes("did you mean 'style'")), text.join('\n'));
});

// ------------------------------------------------------------------ mutation: break one projection, the laws go red
const MUTANTS = [
  ['an inclusive min written exclusive', "and.push(`${p} ${f.minOpen ? '>' : '>='} ${lit(f.min)}`)", "and.push(`${p} > ${lit(f.min)}`)"],
  ['exclude dropped on the way to the tree', 'if (f.exclude && f.exclude.length) and.push', 'if (false) and.push'],
  ['a text bound read as a number', "f.min = clauses[0].value;", "f.min = Number(clauses[0].value);"],
  ['has any written as all', "and.push({ or: f.hasAny.map((x) => `!${ref(x)}.isEmpty()`) })", "and.push(...f.hasAny.map((x) => `!${ref(x)}.isEmpty()`))"],
  ['the URL forgets an exclusive max', "${f.maxOpen ? '<' : ''}${f.max ?? ''}", "${f.max ?? ''}"],
  ['search matches one property only', 'const hit = ins.some((x) => {', 'const hit = ins.slice(0, 1).some((x) => {'],
  ['counts apply their own facet', 'rows.filter((r) => rest(r) && matchesRail(r, facets, except))', 'rows.filter((r) => rest(r) && matchesRail(r, facets))'],
];

test('mutation run: each broken projection turns at least one law red; the real module passes all', async () => {
  const text = readFileSync(SRC, 'utf8');
  const dir = mkdtempSync(join(tmpdir(), 'data-ui-mutants-'));
  try {
    const caught = [];
    for (const [i, [name, from, to]] of MUTANTS.entries()) {
      assert.ok(text.includes(from), `mutation '${name}' still matches the source`);
      const file = join(dir, `m${i}.mjs`);
      writeFileSync(file, text.replace(from, to).replace("from './grammar.js'", `from ${JSON.stringify(pathToFileURL(join(ROOT, 'packages', 'core', 'src', 'grammar.js')).href)}`));
      const red = suite(await import(pathToFileURL(file).href), DATA);
      caught.push([name, red.length]);
    }
    assert.deepEqual(caught.filter(([, n]) => n === 0), [], `mutants no law caught: ${JSON.stringify(caught)}`);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
