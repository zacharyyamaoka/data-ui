// Gap #9 (docs/peps/0010-robotics-playback.md §11 P0; reports/backlog-sim2real-gaps-2026-10-28.md): a dataset filter
// written as one string of && clauses, `run_set == "held-out" && device == "J3 elbow"` (sim2real's build.py joins its
// rail defaults that way), read as ONE custom clause, so the rail counted every facet under both picks and the device
// picker listed only the device already chosen. The rail must read each clause it can draw and keep the rest custom,
// with the meaning unchanged. Oracles are written out by hand from the tiny dataset below.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as F from '../../packages/core/src/facets.js';
import { compileFilters } from '../../packages/core/src/grammar.js';

const PROPS = {
  run_set: { id: 'run_set', type: 'text', label: 'Runs' },
  device: { id: 'device', type: 'text', label: 'Servo' },
  situation: { id: 'situation', type: 'text', label: 'Situation' },
  q: { id: 'q', type: 'number', label: 'q' },
  name: { id: 'name', type: 'text', label: 'name' },
};
const SPECS = F.facetSpecs({ facets: [{ property: 'run_set', as: 'select' }, { property: 'device', as: 'select' }, { property: 'q', as: 'range' }, { property: 'name', as: 'values' }] }, null, PROPS);
const CFG = F.railConfig(SPECS);
const TWO = 'run_set == "held-out" && device == "J3 elbow"';

// 2 run sets x 3 devices; counts below are by hand
const ROWS = [
  ['staircase', 'J3 elbow', 'real'], ['staircase', 'J3 elbow', 'twin'], ['staircase', 'J3 elbow', 'real'],
  ['held-out', 'J3 elbow', 'real'], ['held-out', 'J3 elbow', 'twin'],
  ['held-out', 'J4 wrist 1', 'real'], ['held-out', 'J4 wrist 1', 'twin'], ['held-out', 'J4 wrist 1', 'real'],
  ['held-out', 'J2 shoulder lift', 'real'],
  ['staircase', 'J2 shoulder lift', 'twin'],
].map(([run_set, device, situation], i) => ({ id: `r${i}`, run_set, device, situation, q: i, name: i % 2 ? 'a && b' : 'c' }));
const DATASET = { properties: PROPS, rows: ROWS };
const ids = (filters) => { const keep = compileFilters(filters); return ROWS.filter((r) => !keep || keep(r)).map((r) => r.id); };

test('a string of two facet clauses joined by && is two facet clauses, nothing custom (with and without the rail config)', () => {
  const want = { run_set: { values: ['held-out'], match: 'equals' }, device: { values: ['J3 elbow'], match: 'equals' } };
  assert.deepEqual(F.toRail(TWO, CFG), { facets: want, rest: [] });
  assert.deepEqual(F.toRail(TWO), { facets: want, rest: [] });
});

test('the meaning is unchanged: the rail written back picks exactly the rows the string picks', () => {
  const { facets, rest } = F.toRail(TWO, CFG);
  assert.deepEqual(ids(F.fromRail(facets, rest)), ids(TWO));
  assert.deepEqual(ids(TWO), ['r3', 'r4']);
});

test('the device picker counts every device under the run set pick (disjunctive), as with the clauses written apart', () => {
  const { rail, rows, rest } = F.railInputs(DATASET, {}, TWO, SPECS);
  const counts = F.railCounts(rows, rail.facets, SPECS, rest);
  assert.deepEqual(counts.device.counts, { 'J4 wrist 1': 3, 'J3 elbow': 2, 'J2 shoulder lift': 1 });
  assert.deepEqual(counts.run_set.counts, { staircase: 3, 'held-out': 2 });
  const apart = F.railInputs(DATASET, {}, { and: ['run_set == "held-out"', 'device == "J3 elbow"'] }, SPECS);
  assert.deepEqual(F.railCounts(apart.rows, apart.rail.facets, SPECS, apart.rest), counts);
});

test('&& inside a quoted value or inside parentheses is not a split; a parenthesised && string is', () => {
  assert.deepEqual(F.toRail('name == "a && b" && device == "J3 elbow"', CFG).facets, { name: { values: ['a && b'], match: 'equals' }, device: { values: ['J3 elbow'], match: 'equals' } });
  assert.deepEqual(F.toRail('(run_set == "held-out" && device == "J3 elbow")', CFG), F.toRail(TWO, CFG));
  const mixed = 'device == "J3 elbow" && (situation == "real" || situation == "twin")';
  assert.deepEqual(F.toRail(mixed, CFG), { facets: { device: { values: ['J3 elbow'], match: 'equals' } }, rest: ['(situation == "real" || situation == "twin")'] });
  assert.deepEqual(ids(F.fromRail(F.toRail(mixed, CFG).facets, F.toRail(mixed, CFG).rest)), ids(mixed));
});

test('a top-level || binds looser than &&: such a string is one custom clause, whole', () => {
  const s = 'run_set == "held-out" && device == "J3 elbow" || device == "J4 wrist 1"';
  assert.deepEqual(F.toRail(s, CFG), { facets: {}, rest: [s] });
  const negated = '!(run_set == "held-out" && device == "J3 elbow")';
  assert.deepEqual(F.toRail(negated, CFG), { facets: {}, rest: [negated] });
});

test('a string none of whose clauses the rail can draw stays one custom clause, as written', () => {
  const s = 'situation != "floor" && situation != "floor −"';
  assert.deepEqual(F.toRail(s, CFG), { facets: {}, rest: [s] });
});

test('clauses the rail cannot draw stay custom, each verbatim and in order; a range and a values facet read their parts', () => {
  const s = 'q >= 2 && situation != "floor" && device == "J4 wrist 1" && q < 8';
  assert.deepEqual(F.toRail(s, CFG), { facets: { q: { min: 2, max: 8, maxOpen: true }, device: { values: ['J4 wrist 1'], match: 'equals' } }, rest: ['situation != "floor"'] });
  assert.deepEqual(ids(F.fromRail(F.toRail(s, CFG).facets, F.toRail(s, CFG).rest)), ids(s));
});

test('inside a top-level and-list, each string\'s && clauses are read the same way', () => {
  const tree = { and: [TWO, 'q < 8'] };
  assert.deepEqual(F.toRail(tree, CFG), { facets: { run_set: { values: ['held-out'], match: 'equals' }, device: { values: ['J3 elbow'], match: 'equals' }, q: { max: 8, maxOpen: true } }, rest: [] });
});

test('a second value for a single-choice facet stays custom (no row can match, and that meaning survives)', () => {
  const s = 'device == "J3 elbow" && device == "J4 wrist 1"';
  const { facets, rest } = F.toRail(s, CFG);
  assert.deepEqual(facets, { device: { values: ['J3 elbow'], match: 'equals' } });
  assert.deepEqual(rest, ['device == "J4 wrist 1"']);
  assert.deepEqual(ids(F.fromRail(facets, rest)), []);
});

test('a malformed string (a dangling &&, an open quote) is left whole', () => {
  for (const s of ['device == "J3 elbow" &&', '&& device == "J3 elbow"', 'device == "J3 elbow && run_set == "x"']) {
    assert.deepEqual(F.toRail(s, CFG), { facets: {}, rest: [s] }, s);
  }
});
