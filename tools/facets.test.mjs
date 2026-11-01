// node --test tools/   (no dependencies)
// Proves docs/SPEC.md §6: the McMaster rail is a lossless view of the facet-shaped part of a Bases filters tree.
// The last test uses an independent oracle when it is on disk: the table lane's own Bases evaluator (robotparts,
// lane/tables @ ab5ba92) on its 1,149 real actuator rows. Override the paths with DATA_UI_LANE_GRAMMAR and
// DATA_UI_ACTUATORS; without them the test is skipped, never faked.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { toRail, fromRail, parseClause, matchesRail, facetCounts } from './facets.mjs';

const LANE = '~/robotparts/.claude/worktrees/lane-tables/design/tables-2026-10-25';
const GRAMMAR = process.env.DATA_UI_LANE_GRAMMAR || `${LANE}/views/src/grammar.js`;
const ACTUATORS = process.env.DATA_UI_ACTUATORS || `${LANE}/site/data/actuators.json`;

test('the clause shapes the rail understands, and the ones it leaves alone', () => {
  assert.deepEqual(parseClause('brand == "Steadywin"'), { property: 'brand', kind: 'eq', value: 'Steadywin' });
  assert.deepEqual(parseClause('note.level == 4'), { property: 'level', kind: 'eq', value: 4 });
  assert.deepEqual(parseClause('buses.contains("can")'), { property: 'buses', kind: 'contains', value: 'can' });
  assert.deepEqual(parseClause('price < 150'), { property: 'price', kind: 'max', value: 150, open: true });
  assert.deepEqual(parseClause('peak_torque >= 10'), { property: 'peak_torque', kind: 'min', value: 10, open: false });
  assert.deepEqual(parseClause('!photo.isEmpty()'), { property: 'photo', kind: 'has' });
  for (const custom of ['brand != "KST"', 'peak_torque > 10 || mass < 1', 'file.hasTag("x")', 'price < mass', '(brand == "A")'])
    assert.equal(parseClause(custom), null, custom);
});

test('hyphenated vault properties use Bases\' bracket form both ways; negative bounds parse', () => {
  // Projects/Obsidian Vibe Kanban/Kanban cards.base writes note["vibe-kanban"] == "issue"
  assert.deepEqual(parseClause('note["vibe-kanban"] == "issue"'), { property: 'vibe-kanban', kind: 'eq', value: 'issue' });
  const tree = fromRail({ 'vibe-status': { values: ['done', 'review'], match: 'equals' }, delta: { min: -5 } });
  assert.deepEqual(tree, { and: [{ or: ['note["vibe-status"] == "done"', 'note["vibe-status"] == "review"'] }, 'delta >= -5'] });
  assert.deepEqual(toRail(tree).facets, { 'vibe-status': { values: ['done', 'review'], match: 'equals' }, delta: { min: -5 } });
});

test('the lane\'s own preset filters project onto the rail and back without change', () => {
  // presets/actuators.base, view "Geared CAN under $150", verbatim
  const stored = { and: ['drivetrain == "geared"', 'buses.contains("can")', 'price < 150'] };
  const { facets, rest } = toRail(stored);
  assert.deepEqual(rest, []);
  assert.deepEqual(facets, {
    drivetrain: { values: ['geared'], match: 'equals' },
    buses: { values: ['can'], match: 'contains' },
    price: { max: 150, maxOpen: true },
  });
  assert.deepEqual(fromRail(facets, rest), stored);
});

test('ticking more values makes an or-group; a range is two bounds; empty means every row', () => {
  const tree = fromRail({ brand: { values: ['Steadywin', 'CubeMars'], match: 'equals' }, mass: { min: 100, max: 500 } });
  assert.deepEqual(tree, { and: [{ or: ['brand == "Steadywin"', 'brand == "CubeMars"'] }, 'mass >= 100', 'mass <= 500'] });
  assert.deepEqual(toRail(tree).facets, { brand: { values: ['Steadywin', 'CubeMars'], match: 'equals' }, mass: { min: 100, max: 500 } });
  assert.equal(fromRail({}), undefined);
  assert.deepEqual(toRail(undefined), { facets: {}, rest: [] });
});

test('custom clauses survive a rail edit, verbatim and in order', () => {
  const stored = { and: ['brand == "KST"', 'peak_torque > 10 || mass < 1', { not: ['form == "servo"'] }, 'brand != "X"'] };
  const { facets, rest } = toRail(stored);
  assert.deepEqual(rest, ['peak_torque > 10 || mass < 1', { not: ['form == "servo"'] }, 'brand != "X"']);
  facets.brand.values.push('Steadywin'); // the user ticks a second brand in the rail
  assert.deepEqual(fromRail(facets, rest), {
    and: [{ or: ['brand == "KST"', 'brand == "Steadywin"'] }, 'peak_torque > 10 || mass < 1', { not: ['form == "servo"'] }, 'brand != "X"'],
  });
});

test('what the rail cannot draw stays custom: a top-level or, and two value clauses on one property', () => {
  const either = { or: ['brand == "A"', 'form == "servo"'] };
  assert.deepEqual(toRail(either), { facets: {}, rest: [either] });
  const both = { and: ['brand == "A"', 'brand == "B"'] }; // no row can match; the meaning must not change
  assert.deepEqual(toRail(both), { facets: { brand: { values: ['A'], match: 'equals' } }, rest: ['brand == "B"'] });
  assert.deepEqual(fromRail(toRail(both).facets, toRail(both).rest), both);
});

test('disjunctive counts: a facet ignores its own selection, every other facet applies', () => {
  const rows = [
    { brand: 'A', form: 'servo', mass: 100 }, { brand: 'A', form: 'motor', mass: 200 },
    { brand: 'B', form: 'servo', mass: 300 }, { brand: 'C', form: 'servo', mass: null },
  ];
  const facets = { brand: { values: ['A'], match: 'equals' }, form: { values: ['servo'], match: 'equals' } };
  const counts = facetCounts(rows, facets, { brand: 'values', form: 'values', mass: 'range' });
  assert.deepEqual(counts.brand, { A: 1, B: 1, C: 1 }); // form = servo applies, brand's own tick does not
  assert.deepEqual(counts.form, { motor: 1, servo: 1 }); // brand = A applies
  assert.deepEqual(counts.mass, { n: 1, min: 100, max: 100 }); // both apply; the null mass is not a value
  assert.equal(rows.filter((r) => matchesRail(r, facets)).length, 1);
});

// ------------------------------------------------------------------ the independent oracle, on real data
function rng(seed) { // mulberry32: the same 300 selections every run
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

const haveOracle = existsSync(GRAMMAR) && existsSync(ACTUATORS);
test('rail selections pick exactly the rows the lane\'s Bases evaluator picks (1,149 real actuators)', { skip: !haveOracle && 'the lane\'s grammar.js or actuators.json is not on disk' }, async () => {
  const G = await import(pathToFileURL(GRAMMAR).href);
  const rows = JSON.parse(readFileSync(ACTUATORS, 'utf8')).rows;
  assert.equal(rows.length, 1149);
  const random = rng(20261025);
  const pick = (list) => list[Math.floor(random() * list.length)];
  const distinct = (p) => [...new Set(rows.flatMap((r) => (Array.isArray(r[p]) ? r[p] : [r[p]])).filter((v) => v !== null && v !== undefined && v !== ''))];
  const values = { brand: distinct('brand'), form: distinct('form'), drivetrain: distinct('drivetrain'), level: distinct('level'), buses: distinct('buses') };
  const numbers = (p) => rows.map((r) => r[p]).filter((v) => typeof v === 'number').sort((a, b) => a - b);
  const ranges = { peak_torque: numbers('peak_torque'), mass: numbers('mass'), price: numbers('price') };
  let nonEmpty = 0;
  for (let i = 0; i < 300; i++) {
    const facets = {};
    for (const p of Object.keys(values)) {
      if (random() < 0.35) {
        const chosen = [...new Set(Array.from({ length: 1 + Math.floor(random() * 3) }, () => pick(values[p])))];
        facets[p] = { values: chosen, match: p === 'buses' ? 'contains' : 'equals' };
      }
    }
    for (const p of Object.keys(ranges)) {
      if (random() < 0.3) {
        const q = ranges[p];
        const f = {};
        if (random() < 0.7) { f.min = q[Math.floor(random() * q.length * 0.6)]; if (random() < 0.3) f.minOpen = true; }
        if (random() < 0.7) { f.max = q[Math.floor(q.length * 0.4 + random() * q.length * 0.6)]; if (random() < 0.3) f.maxOpen = true; }
        if (Object.keys(f).length) facets[p] = f;
      }
    }
    if (random() < 0.15) facets.torque_density = { has: true };
    const tree = fromRail(facets);
    const keep = G.compileFilters(tree) || (() => true);
    const byLane = rows.filter(keep).map((r) => r.id);
    const byRail = rows.filter((r) => matchesRail(r, facets)).map((r) => r.id);
    assert.deepEqual(byRail, byLane, JSON.stringify(tree));
    assert.deepEqual(toRail(tree), { facets, rest: [] }, 'the projection round-trips');
    if (byLane.length) nonEmpty++;
  }
  assert.ok(nonEmpty > 100, `the oracle must see real selections, not only empty ones (${nonEmpty} of 300 non-empty)`);
});
