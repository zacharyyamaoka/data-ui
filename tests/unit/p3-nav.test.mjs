// PEP 0010 P3, navigation: the dashboard model's half (packages/dashboard/src/model.js; docs/peps/0010-robotics-playback.md
// §8, §11 P3; sim2real gaps #7 and #8). Written red, before the code; the browser half is tests/browser/p3_checks.py.
//   one-way links   {from, to, direction: one-way}: the from side's picks narrow the to side, never the other way
//                   (Power BI's single cross-filter direction); two-way stays the default, so no dashboard changes
//   per-pick files  a dataset whose data: names a placeholder (runs/{run}.json) reads the one file its links leave: the
//                   placeholder filled with the one value the other datasets' picks carry to that column, as one URL path
//                   segment (CONTRACT §24's origin.url rule); none or two or more: no file. Its rows narrow no other
//                   dataset (they are one run's, not every run's)
//   presets         a view's `selected: first | <value> | [values]` beside its select: (gap #7): the selection the page
//                   opens with, in layout order (first: the view's first row under its sort and its panel's filter); an
//                   empty s.<panel>= in the URL says the reader cleared it
//   pickers         a select: on a property its dataset's rail picks one value of (as: select) moves that pick, and the
//                   panel lists every value the rest of the rail leaves (the robotics templates' runs tables)
// Oracles are written out by hand from the fixtures below, never from the model.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readDashboard, panelFilter, keep, linkPath, templateFile, fillPath, presetSelections, readHash, writeHash, pickRail } from '../../packages/dashboard/src/model.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const base = {
  data: 'runs.json',
  datasets: {
    deployments: 'deployments.json',
    runs: { data: 'runs.json', facets: [{ property: 'run', as: 'select', label: 'Run' }, { property: 'station', label: 'Station' }] },
    samples: { data: 'runs/{run}.json', facets: [{ property: 'situation', label: 'Show' }] },
    notes: 'notes.json',
  },
  links: [
    { from: 'deployments.deployment', to: 'runs.deployment', direction: 'one-way' },
    { from: 'runs.run', to: 'samples.run', direction: 'one-way' },
    { from: 'notes.run', to: 'runs.run' },
  ],
  layout: { panels: [{ view: 'Deployments' }, { view: 'Runs' }, { view: 'Angle' }, { view: 'Notes' }] },
  views: [
    { type: 'table', name: 'Deployments', from: 'deployments', select: 'deployment' },
    { type: 'table', name: 'Runs', from: 'runs', select: 'run', sort: [{ property: 'started', direction: 'DESC' }] },
    { type: 'timeseries', name: 'Angle', from: 'samples', timeseries: { x: 't', y: 'q_deg', series: 'situation' } },
    { type: 'table', name: 'Notes', from: 'notes', select: 'run' },
  ],
};
const data = () => ({
  deployments: normalizeDataset({ properties: { deployment: {}, title: {} }, rows: [
    { id: 'rack', deployment: 'rack', title: 'Rack' }, { id: 'arm', deployment: 'arm', title: 'Arm' },
  ] }),
  runs: normalizeDataset({ properties: { run: {}, deployment: {}, station: {}, started: { type: 'date' } }, rows: [
    { id: 'r1', run: 'r1', deployment: 'rack', station: 'S1', started: '2026-10-29T08:00:00-07:00' },
    { id: 'r2', run: 'r2', deployment: 'rack', station: 'S1', started: '2026-10-29T09:00:00-07:00' },
    { id: 'r3', run: 'r3', deployment: 'rack', station: 'S2', started: '2026-10-29T10:00:00-07:00' },
    { id: 'r4', run: 'r4', deployment: 'arm', station: 'J1', started: '2026-10-29T11:00:00-07:00' },
  ] }),
  // a per-pick dataset holds one run's rows: here r2's
  samples: normalizeDataset({ properties: { run: {}, situation: {}, t: { type: 'number' } }, rows: [
    { id: 's1', run: 'r2', situation: 'real', t: 0 }, { id: 's2', run: 'r2', situation: 'target', t: 0 },
  ] }),
  notes: normalizeDataset({ properties: { run: {}, text: {} }, rows: [{ id: 'n1', run: 'r1', text: 'a' }, { id: 'n3', run: 'r3', text: 'b' }] }),
});
const ids = (rows) => rows.map((r) => r.id).sort();
const kept = (d, x, state, ds, key = null) => ids(keep(x[ds].rows, panelFilter(d, x, state, ds, key)));

// ------------------------------------------------------------------------------------------------- one-way links
test('readDashboard: a link\'s direction (one-way marks it; two-way, or none, is both ways, as before)', () => {
  const d = readDashboard(base);
  assert.deepEqual(d.problems, []);
  assert.deepEqual(d.links.map((l) => [`${l.a.ds}.${l.a.col}`, `${l.b.ds}.${l.b.col}`, l.oneWay]),
    [['deployments.deployment', 'runs.deployment', true], ['runs.run', 'samples.run', true], ['notes.run', 'runs.run', false]]);
  assert.equal(readDashboard({ ...base, links: [{ from: 'notes.run', to: 'runs.run', direction: 'two-way' }] }).links[0].oneWay, false);
  const bad = readDashboard({ ...base, links: [{ from: 'notes.run', to: 'runs.run', direction: 'sideways' }] }).problems;
  assert.ok(bad.some((p) => p.startsWith('links[0].direction') && /one-way/.test(p) && /two-way/.test(p)), bad.join('\n'));
});

const pair = (direction) => ({
  data: 'runs.json',
  datasets: { runs: { data: 'runs.json', facets: ['station'] }, notes: { data: 'notes.json', facets: ['text'] } },
  links: [{ from: 'runs.run', to: 'notes.run', ...(direction ? { direction } : {}) }],
  layout: { panels: [{ view: 'Runs' }, { view: 'Notes' }] },
  views: [{ type: 'table', name: 'Runs', from: 'runs' }, { type: 'table', name: 'Notes', from: 'notes' }],
});

test('one-way: a pick on the from side narrows the to side', () => {
  for (const direction of ['one-way', 'two-way', null]) {
    const d = readDashboard(pair(direction)), x = data();
    assert.deepEqual(kept(d, x, { rail: { runs: 'station == "S1"' }, select: {} }, 'notes'), ['n1'], `${direction}: r1 is S1, r3 is not`);
  }
});

test('one-way: a pick on the to side never narrows the from side (two-way, the default, still does)', () => {
  const state = { rail: { notes: 'text == "b"' }, select: {} };
  const one = readDashboard(pair('one-way')), x = data();
  assert.equal(panelFilter(one, x, state, 'runs'), undefined, 'one-way: the runs panel gets no clause');
  assert.deepEqual(kept(one, x, state, 'runs'), ['r1', 'r2', 'r3', 'r4']);
  for (const direction of ['two-way', null]) assert.deepEqual(kept(readDashboard(pair(direction)), x, state, 'runs'), ['r3'], `${direction}: note b is r3's`);
  // a selection made on the to side is a pick there too
  const sel = { rail: {}, select: { notes: { dataset: 'notes', property: 'text', values: ['a'] } } };
  assert.deepEqual(kept(one, x, sel, 'runs'), ['r1', 'r2', 'r3', 'r4']);
  assert.deepEqual(kept(readDashboard(pair()), x, sel, 'runs'), ['r1']);
});

test('one-way: a chain is followed forward only (the fewest hops along the links\' directions)', () => {
  const chain = { ...pair('one-way'), datasets: { ...pair().datasets, deployments: { data: 'deployments.json', facets: ['title'] } },
    links: [{ from: 'deployments.deployment', to: 'runs.deployment', direction: 'one-way' }, { from: 'runs.run', to: 'notes.run', direction: 'one-way' }] };
  const d = readDashboard(chain), x = data();
  assert.deepEqual(kept(d, x, { rail: { deployments: 'title == "Arm"' }, select: {} }, 'notes'), [], 'Arm has only r4, which has no note');
  assert.deepEqual(kept(d, x, { rail: { deployments: 'title == "Rack"' }, select: {} }, 'notes'), ['n1', 'n3']);
  assert.equal(panelFilter(d, x, { rail: { notes: 'text == "a"' }, select: {} }, 'deployments'), undefined, 'nothing flows back up the chain');
  assert.deepEqual(linkPath(d.links, 'deployments', 'notes', { directed: true }).map((s) => `${s.from.ds}>${s.to.ds}`), ['deployments>runs', 'runs>notes']);
  assert.equal(linkPath(d.links, 'notes', 'deployments', { directed: true }), null);
  assert.deepEqual(linkPath(d.links, 'notes', 'deployments').map((s) => `${s.from.ds}>${s.to.ds}`), ['notes>runs', 'runs>deployments'], 'undirected (a roll-up\'s join) still crosses it');
});

// ------------------------------------------------------------------------------------------------- per-pick files
test('readDashboard: a dataset\'s placeholders (template); the default data is never one', () => {
  const d = readDashboard(base);
  assert.deepEqual(d.datasets.samples.template, ['run']);
  assert.equal(d.datasets.runs.template, null);
  assert.deepEqual(readDashboard({ ...base, datasets: { ...base.datasets, samples: 'data/{deployment}/runs/{run}/samples.json' } }).datasets.samples.template, ['deployment', 'run']);
  const top = readDashboard({ data: 'runs/{run}.json', views: [] }).problems;
  assert.ok(top.some((p) => p.startsWith('data:')), top.join('\n'));
});

test('fillPath: each placeholder as one URL path segment (encodeURIComponent, as origin.url fills one), null while one has no value', () => {
  assert.equal(fillPath('runs/{run}.json', { run: 'r2' }), 'runs/r2.json');
  assert.equal(fillPath('runs/{run}.json', { run: '10-24/s01 a' }), 'runs/10-24%2Fs01%20a.json');
  assert.equal(fillPath('data/{deployment}/runs/{run}/samples.json', { deployment: 'rack', run: 'r1' }), 'data/rack/runs/r1/samples.json');
  assert.equal(fillPath('runs/{run}.json', {}), null);
  assert.equal(fillPath('runs/{run}.json', { run: '' }), null);
});

test('templateFile: nothing picked, no file (the placeholder\'s choices unknown)', () => {
  const d = readDashboard(base), x = data();
  assert.deepEqual(templateFile(d, x, { rail: {}, select: {} }, 'samples'), { path: null, values: null, choices: { run: null } });
});

test('templateFile: one run picked (the rail, or a selection that reaches it through a link) names its file', () => {
  const d = readDashboard(base), x = data();
  assert.deepEqual(templateFile(d, x, { rail: { runs: 'run == "r2"' }, select: {} }, 'samples'), { path: 'runs/r2.json', values: { run: 'r2' }, choices: { run: ['r2'] } });
  // the notes' selection reaches samples.run through runs (notes ↔ runs two-way, runs → samples one-way)
  const sel = { rail: {}, select: { notes: { dataset: 'notes', property: 'run', values: ['r3'] } } };
  assert.deepEqual(templateFile(d, x, sel, 'samples').path, 'runs/r3.json');
});

test('templateFile: two runs picked, no file; both are the choices, in the from side\'s row order', () => {
  const d = readDashboard(base), x = data();
  const got = templateFile(d, x, { rail: { runs: { or: ['run == "r2"', 'run == "r1"'] } }, select: {} }, 'samples');
  assert.deepEqual(got, { path: null, values: null, choices: { run: ['r1', 'r2'] } });
});

test('templateFile: picks that leave no run (a deployment and a run that do not meet), no file and no choice', () => {
  const d = readDashboard(base), x = data();
  const state = { rail: { runs: 'run == "r4"' }, select: { deployments: { dataset: 'deployments', property: 'deployment', values: ['rack'] } } };
  assert.deepEqual(templateFile(d, x, state, 'samples'), { path: null, values: null, choices: { run: [] } });
  // the same deployment and a run of it: the chain and the run pick meet on r3
  assert.equal(templateFile(d, x, { ...state, rail: { runs: 'run == "r3"' } }, 'samples').path, 'runs/r3.json');
});

test('a per-pick dataset narrows no other dataset (it holds one run\'s rows), even through a link written two-way', () => {
  const two = readDashboard({ ...base, links: [{ from: 'runs.run', to: 'samples.run' }] }), x = data();
  const state = { rail: { samples: 'situation == "real"' }, select: {} };
  assert.equal(panelFilter(two, x, state, 'runs'), undefined);
  assert.deepEqual(kept(two, x, state, 'runs'), ['r1', 'r2', 'r3', 'r4']);
  // and the runs' pick still narrows it
  assert.deepEqual(kept(two, x, { rail: { runs: 'run == "r1"' }, select: {} }, 'samples'), []);
});

// ------------------------------------------------------------------------------------------------- presets
const presetBase = {
  data: 'runs.json',
  datasets: { deployments: 'deployments.json', runs: 'runs.json', notes: 'notes.json' },
  links: [{ from: 'deployments.deployment', to: 'runs.deployment', direction: 'one-way' }, { from: 'runs.run', to: 'notes.run', direction: 'one-way' }],
  layout: { panels: [{ view: 'Deployments' }, { view: 'Runs' }, { view: 'Notes' }, { view: 'Literal' }] },
  views: [
    { type: 'table', name: 'Deployments', from: 'deployments', select: 'deployment', selected: 'first' },
    { type: 'table', name: 'Runs', from: 'runs', select: 'run', selected: 'first', sort: [{ property: 'started', direction: 'DESC' }] },
    { type: 'table', name: 'Notes', from: 'notes', select: 'run', selected: ['r3', 'r1'] },
    { type: 'table', name: 'Literal', from: 'notes', select: 'text', selected: ['first'] },
  ],
};

test('readDashboard: a view\'s selected: is its panel\'s preset; selected: with no select: is a problem', () => {
  const d = readDashboard(presetBase);
  assert.deepEqual(d.problems, []);
  assert.deepEqual(d.panels.map((p) => [p.key, p.preset && p.preset.property, p.preset && p.preset.values]),
    [['deployments', 'deployment', 'first'], ['runs', 'run', 'first'], ['notes', 'run', ['r3', 'r1']], ['literal', 'text', ['first']]]);
  const bad = readDashboard({ ...presetBase, views: [{ type: 'table', name: 'Deployments', from: 'deployments', selected: 'first' }, ...presetBase.views.slice(1)] }).problems;
  assert.ok(bad.some((p) => p.startsWith('views[0].selected') && /select:/.test(p)), bad.join('\n'));
});

test('presetSelections: first is the view\'s first row (its sort, its panel\'s filter), in layout order; a list or a value is literal', () => {
  const d = readDashboard(presetBase), x = data();
  // r4 is the newest run, but the deployments preset (rack, its first row) comes first and leaves r1-r3: r3 is the first
  assert.deepEqual(presetSelections(d, x, { rail: {}, select: {} }), {
    deployments: { dataset: 'deployments', property: 'deployment', values: ['rack'] },
    runs: { dataset: 'runs', property: 'run', values: ['r3'] },
    notes: { dataset: 'notes', property: 'run', values: ['r3', 'r1'] },
    literal: { dataset: 'notes', property: 'text', values: ['first'] },
  });
  const one = readDashboard({ ...presetBase, views: presetBase.views.map((v) => (v.name === 'Runs' ? { ...v, selected: 'r1' } : v)) });
  assert.deepEqual(presetSelections(one, x, { rail: {}, select: {} }).runs.values, ['r1']);
});

test('presetSelections: a panel the URL already names (a selection, or s.<panel>= cleared) gets no preset', () => {
  const d = readDashboard(presetBase), x = data();
  const state = { rail: {}, select: { runs: { dataset: 'runs', property: 'run', values: ['r1'] } } };
  const got = presetSelections(d, x, state, ['notes']);
  assert.deepEqual(Object.keys(got).sort(), ['deployments', 'literal']);
});

test('writeHash / readHash: a preset panel with no selection is written s.<panel>= and read back as cleared, never as its preset', () => {
  const d = readDashboard(presetBase);
  const h = writeHash('', { select: { runs: { dataset: 'runs', property: 'run', values: ['r2'] } }, tabs: {}, legend: {} }, d.panels);
  assert.equal(h.get('s.runs'), 'run:r2');
  assert.equal(h.get('s.deployments'), '');
  assert.equal(h.get('s.notes'), '');
  const back = readHash(h.toString(), d.panels);
  assert.deepEqual(back.select.runs.values, ['r2']);
  assert.deepEqual([...back.cleared].sort(), ['deployments', 'literal', 'notes']);
  // a panel with no preset and no selection writes nothing, as before
  assert.equal(writeHash('', { select: {}, tabs: {}, legend: {} }, readDashboard(base).panels).has('s.runs'), false);
});

// ------------------------------------------------------------------------------------------------- pickers
test('pickers: a select: on a property its dataset\'s rail picks one of (as: select) makes the panel a picker', () => {
  const d = readDashboard(base);
  assert.deepEqual(d.panels.map((p) => [p.key, p.picks || null]), [['deployments', null], ['runs', 'run'], ['angle', null], ['notes', null]]);
});

test('pickers: the picker panel lists every run the rest of the rail leaves (its own pick left out); other panels keep the pick', () => {
  const d = readDashboard(base), x = data();
  const state = { rail: { runs: { and: ['run == "r1"', 'station == "S1"'] } }, select: {} };
  assert.deepEqual(kept(d, x, state, 'runs', 'runs'), ['r1', 'r2']);
  assert.deepEqual(kept(d, x, state, 'runs', null), ['r1']);
  assert.deepEqual(templateFile(d, x, state, 'samples').path, 'runs/r1.json');
});

test('pickRail: a click on a picker sets that one pick on its dataset\'s rail and keeps the rail\'s other picks', () => {
  const d = readDashboard(base), x = data();
  const f = pickRail(d, x, { and: ['run == "r1"', 'station == "S1"'] }, 'runs', 'run', 'r2');
  assert.deepEqual(ids(keep(x.runs.rows, f)), ['r2']);
  assert.deepEqual(ids(keep(x.runs.rows, pickRail(d, x, undefined, 'runs', 'run', 'r3'))), ['r3']);
  // a parent's pick settles its children (CONTRACT §7, parent:): the run moves to the station's first listed run
  const nested = readDashboard({ ...base, datasets: { ...base.datasets, runs: { data: 'runs.json', facets: [{ property: 'station', as: 'select' }, { property: 'run', as: 'select', parent: 'station' }] } },
    views: base.views.map((v) => (v.name === 'Runs' ? { ...v, select: 'station' } : v)) });
  assert.deepEqual(ids(keep(x.runs.rows, pickRail(nested, x, { and: ['station == "S1"', 'run == "r1"'] }, 'runs', 'station', 'S2'))), ['r3']);
});
