// The fleet map (docs/CONTRACT.md §39): the case's files and the dashboard model's half. Written red, before the code; never
// edited after. The browser half is tests/browser/fleet_map_checks.py.
//   the case       one panel with Map, Table and Cards tabs over one dataset, each picking `deployment`; the rack is real and
//                  says so, everything else is synthetic and says so, on every row; the columns that count runs agree with
//                  runs.json; the rack's run files are its files
//   a preset again a panel with `selected:` whose selection names no row it still draws (a pick upstream left none of its
//                  values) picks again by its preset, in layout order. WHY (measured on main d5ede93): the second robot
//                  picked on a map left the first robot's run selected, and the playback said "the picks leave no run"
// Oracles are the case's own files, or written out by hand from the fixture below; never the model's own answer.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset } from '../../packages/core/src/data.js';
import * as model from '../../packages/dashboard/src/model.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const HERE = join(ROOT, 'gallery', 'examples', 'robotics-fleet');
const RACK_CASE = join(ROOT, 'gallery', 'examples', 'robotics-deployments');
const json = (...path) => JSON.parse(readFileSync(join(...path), 'utf8'));
const base = parseBase(readFileSync(join(HERE, 'views.base'), 'utf8'));
const deployments = json(HERE, 'deployments.json');
const runs = json(HERE, 'runs.json');
const fleet = deployments.rows;
const REAL = 'one-dof-test-rack';

const caseDash = () => model.readDashboard(base);
const caseData = () => ({ deployments: normalizeDataset(deployments), runs: normalizeDataset(runs), samples: normalizeDataset({ rows: [] }) });
const newestOf = (deployment) => runs.rows.filter((r) => r.deployment === deployment).sort((a, b) => (a.started < b.started ? 1 : -1))[0].run;

test('the case: one Deployments panel with tabs Map, Table, Cards, the map first, each view picking deployment', () => {
  const dash = caseDash();
  assert.deepEqual(dash.problems, []);
  const panel = dash.panels.find((p) => p.title === 'Deployments');
  assert.deepEqual(panel.views.map((v) => [v.name, v.type]), [['Map', 'map'], ['Table', 'table'], ['Cards', 'cards']]);
  assert.ok(panel.views.every((v) => v.select === 'deployment' && v.from === 'deployments'));
  assert.equal(panel.views[0].coordinates, 'coordinates');
  assert.equal(panel.views[0].markerColor, 'status');
  assert.deepEqual(dash.panels.filter((p) => p.views.length).map((p) => p.views[0].name), ['Map', 'Runs', 'Playback', 'Angle', 'Velocity']);
  assert.equal(base.datasets.samples.data, 'runs/{run}.json');
});

test('the rows: about 12 robots, every column on every row, sites in BC, across Canada and in a few US cities', () => {
  assert.ok(fleet.length >= 10 && fleet.length <= 14, `${fleet.length} robots`);
  for (const row of fleet) for (const column of ['name', 'robot_model', 'site', 'city', 'status', 'last_run', 'runs', 'coordinates', 'basis']) assert.ok(row[column] !== undefined && row[column] !== null, `${row.name}: ${column}`);
  const cities = new Set(fleet.map((r) => r.city));
  for (const city of ['Vancouver', 'Victoria', 'Toronto', 'Seattle']) assert.ok(cities.has(city), city);
  for (const row of fleet) {
    const [lat, lng] = row.coordinates;
    assert.ok(lat > 24 && lat < 60 && lng > -130 && lng < -60, `${row.name} is in Canada or the US: ${row.coordinates}`);
  }
  assert.ok(new Set(fleet.map((r) => r.status)).size >= 3, 'status has something to say on a map');
  for (const status of new Set(fleet.map((r) => r.status))) assert.ok(deployments.properties.status.colors[status] !== undefined, `${status} has a colour slot`);
});

test('real and synthetic: the rack is real, everything else says synthetic, in the data, the README and the page', () => {
  assert.deepEqual(fleet.filter((r) => r.basis === 'real').map((r) => r.deployment), [REAL]);
  assert.ok(fleet.filter((r) => r.deployment !== REAL).every((r) => r.basis === 'synthetic'));
  assert.ok(runs.rows.every((r) => r.basis === (r.deployment === REAL ? 'real' : 'synthetic')), 'every run says which it is');
  const readme = readFileSync(join(HERE, 'README.md'), 'utf8');
  assert.match(readme, /\*\*Synthetic/i, 'the README says synthetic');
  const text = caseDash().panels.find((p) => p.text);
  assert.match(text.text, /synthetic/i, 'the page says synthetic');
  assert.match(readFileSync(join(HERE, 'source', 'build.py'), 'utf8'), /random\.Random\(SEED\)/, 'seeded');
});

test('the rack keeps its real name and its first row, no site names a customer', () => {
  const rack = json(RACK_CASE, 'deployments.json').rows[0];
  assert.equal(fleet[0].deployment, rack.deployment);
  assert.equal(fleet[0].name, rack.title);
  for (const row of fleet) assert.match(row.site, /^(Test bench|(Hospital|Food court|Materials) site [A-Z]|Transfer station [A-Z])$/, row.site);
});

test('two robots at one site: rows at one point exist, so the map has a counted marker', () => {
  const at = new Map();
  for (const row of fleet) at.set(row.coordinates.join(), [...(at.get(row.coordinates.join()) || []), row]);
  assert.ok([...at.values()].some((rows) => rows.length > 1));
});

test('runs and last_run are what runs.json holds', () => {
  for (const row of fleet) {
    const mine = runs.rows.filter((r) => r.deployment === row.deployment);
    assert.equal(row.runs, mine.length, `${row.name}'s run count`);
    assert.equal(row.last_run, mine.map((r) => r.started).sort().at(-1).slice(0, 10), `${row.name}'s last run`);
  }
  assert.ok(runs.rows.every((r) => fleet.some((d) => d.deployment === r.deployment)), 'every run names a robot');
  assert.equal(new Set(runs.rows.map((r) => r.run)).size, runs.rows.length, 'a run id is one run');
});

test('the rack\'s run files are its real files, byte for byte; a synthetic file holds its run and says synthetic', () => {
  const names = readdirSync(join(HERE, 'runs')).sort();
  assert.deepEqual(names, runs.rows.map((r) => `${r.run}.json`).sort(), 'one file per run, no other');
  const rackRuns = json(RACK_CASE, 'runs.json').rows.map((r) => r.run);
  for (const r of runs.rows) {
    const text = readFileSync(join(HERE, 'runs', `${r.run}.json`));
    if (r.basis === 'real') {
      assert.ok(rackRuns.includes(r.run), `${r.run} is one of the rack's`);
      assert.ok(text.equals(readFileSync(join(RACK_CASE, 'runs', `${r.run}.json`))), `${r.run} is the rack's file`);
    } else {
      const doc = JSON.parse(text);
      assert.match(doc.source, /SYNTHETIC/);
      assert.deepEqual([...new Set(doc.rows.map((x) => x.run))], [r.run]);
      assert.deepEqual([...new Set(doc.rows.map((x) => x.situation))].sort(), ['synthetic', 'target']);
    }
  }
});

test('a pick upstream leaves a preset panel\'s selection naming no row: it picks again, the new robot\'s newest run', () => {
  assert.equal(typeof model.settledSelections, 'function', 'model.js exports settledSelections');
  const dash = caseDash();
  const data = caseData();
  const pick = fleet[3].deployment;
  const before = { rail: {}, tabs: {}, legend: {}, select: {
    deployments: { dataset: 'deployments', property: 'deployment', values: [pick] },
    runs: { dataset: 'runs', property: 'run', values: [newestOf(REAL)] },
  } };
  const frozen = JSON.stringify(before);
  const settled = model.settledSelections(dash, data, before);
  assert.deepEqual(settled.runs, { dataset: 'runs', property: 'run', values: [newestOf(pick)] });
  assert.deepEqual(settled.deployments, before.select.deployments, 'the pick itself stands');
  assert.equal(JSON.stringify(before), frozen, 'the state is not changed');
});

test('a selection that still names a row stays: an added robot leaves the run alone', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const dash = caseDash();
  const state = { rail: {}, tabs: {}, legend: {}, select: {
    deployments: { dataset: 'deployments', property: 'deployment', values: [REAL, fleet[3].deployment] },
    runs: { dataset: 'runs', property: 'run', values: [newestOf(REAL)] },
  } };
  assert.deepEqual(model.settledSelections(dash, caseData(), state), state.select);
});

test('an older run of the picked robot stays picked: only a selection naming no drawn row moves', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const older = runs.rows.filter((r) => r.deployment === REAL).sort((a, b) => (a.started < b.started ? -1 : 1))[0].run;
  assert.notEqual(older, newestOf(REAL));
  const state = { rail: {}, tabs: {}, legend: {}, select: {
    deployments: { dataset: 'deployments', property: 'deployment', values: [REAL] },
    runs: { dataset: 'runs', property: 'run', values: [older] },
  } };
  assert.deepEqual(model.settledSelections(caseDash(), caseData(), state), state.select);
});

test('no selection is not a stale one: a panel the reader cleared stays cleared', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const state = { rail: {}, tabs: {}, legend: {}, select: { deployments: { dataset: 'deployments', property: 'deployment', values: [fleet[3].deployment] } } };
  assert.deepEqual(model.settledSelections(caseDash(), caseData(), state), state.select);
});

// three levels, hand-written: site → robot → run, each `selected: first` but one
const chain = () => ({
  dash: model.readDashboard({
    data: 'sites.json',
    datasets: { sites: 'sites.json', robots: 'robots.json', runs: 'runs.json' },
    links: [{ from: 'sites.site', to: 'robots.site', direction: 'one-way' }, { from: 'robots.robot', to: 'runs.robot', direction: 'one-way' }],
    layout: { panels: [{ view: 'Sites' }, { view: 'Robots' }, { view: 'Runs' }] },
    views: [
      { type: 'table', name: 'Sites', from: 'sites', select: 'site' },
      { type: 'table', name: 'Robots', from: 'robots', select: 'robot', selected: 'first' },
      { type: 'table', name: 'Runs', from: 'runs', select: 'run', selected: 'first', sort: [{ property: 'n', direction: 'DESC' }] },
    ],
  }),
  data: {
    sites: normalizeDataset({ rows: [{ id: 's1', site: 's1' }, { id: 's2', site: 's2' }] }),
    robots: normalizeDataset({ rows: [{ id: 'a', robot: 'a', site: 's1' }, { id: 'b', robot: 'b', site: 's2' }, { id: 'c', robot: 'c', site: 's2' }] }),
    runs: normalizeDataset({ rows: [{ id: 'a1', run: 'a1', robot: 'a', n: 1 }, { id: 'b1', run: 'b1', robot: 'b', n: 1 }, { id: 'b2', run: 'b2', robot: 'b', n: 2 }, { id: 'c1', run: 'c1', robot: 'c', n: 3 }] }),
  },
});

test('the presets settle in layout order: a robot that moves carries its run with it', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const { dash, data } = chain();
  const state = { rail: {}, tabs: {}, legend: {}, select: {
    sites: { dataset: 'sites', property: 'site', values: ['s2'] },
    robots: { dataset: 'robots', property: 'robot', values: ['a'] },
    runs: { dataset: 'runs', property: 'run', values: ['a1'] },
  } };
  const settled = model.settledSelections(dash, data, state);
  assert.deepEqual(settled.robots.values, ['b'], 's2\'s first robot');
  assert.deepEqual(settled.runs.values, ['b2'], 'b\'s newest run: the run settles against the robot just picked');
});

test('a panel with no preset keeps what it has, as before: only `selected:` says the panel holds a pick when it can', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const { dash, data } = chain();
  const noPreset = { ...dash, panels: dash.panels.map((p) => ({ ...p, preset: null })) };
  const state = { rail: {}, tabs: {}, legend: {}, select: {
    sites: { dataset: 'sites', property: 'site', values: ['s2'] },
    robots: { dataset: 'robots', property: 'robot', values: ['a'] },
  } };
  assert.deepEqual(model.settledSelections(noPreset, data, state), state.select);
});

test('a literal preset that names no row left is dropped, not written back', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const { dash, data } = chain();
  const literal = { ...dash, panels: dash.panels.map((p) => (p.key === 'robots' ? { ...p, preset: { ...p.preset, values: ['a'] } } : p)) };
  const state = { rail: {}, tabs: {}, legend: {}, select: {
    sites: { dataset: 'sites', property: 'site', values: ['s2'] },
    robots: { dataset: 'robots', property: 'robot', values: ['a'] },
  } };
  const settled = model.settledSelections(literal, data, state);
  assert.equal(settled.robots, undefined, 'robot a is not at s2, so nothing is selected');
  assert.deepEqual(settled.sites, state.select.sites);
});

test('a rail that leaves the selection naming no row settles it too', () => {
  assert.equal(typeof model.settledSelections, 'function');
  const { dash, data } = chain();
  const state = { rail: { robots: 'robot != "a"' }, tabs: {}, legend: {}, select: { robots: { dataset: 'robots', property: 'robot', values: ['a'] } } };
  assert.deepEqual(model.settledSelections(dash, data, state).robots.values, ['b']);
});
