// The map view's plan for picks and legends (docs/CONTRACT.md §39, §42): what a mark needs from a plan, and a marker map's
// legend. Written red, before the code. The oracles are written out by hand from the rows below, never computed with the
// module's own helpers. The browser half is tests/browser/map_select_checks.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as h3 from 'h3-js';
import { buildPlan, mapSpec, featureRows } from '../../packages/views/map/src/plan.js';

const tokens = { bg: 'rgb(255, 255, 255)', fg: 'rgb(0, 0, 0)', muted: 'rgb(120, 120, 120)', subtle: 'rgb(240, 240, 240)', border: 'rgb(200, 200, 200)', accent: 'rgb(0, 0, 200)', onAccent: 'rgb(255, 255, 255)', series: ['rgb(1, 0, 0)', 'rgb(2, 0, 0)', 'rgb(3, 0, 0)', 'rgb(4, 0, 0)', 'rgb(5, 0, 0)', 'rgb(6, 0, 0)', 'rgb(7, 0, 0)', 'rgb(8, 0, 0)'] };
const helpers = (view, rows) => ({
  view, tokens, h3, state: {}, titleProperty: 'name',
  value: (r, p) => (p ? r[p] : null), raw: (r, p) => (p ? r[p] : null),
  text: (r, p) => (p && r[p] != null ? String(r[p]) : null),
  match: () => () => true, isProperty: (p) => typeof p === 'string' && rows.some((r) => p in r),
  colourOf: (r, p) => ({ running: 'rgb(6, 0, 0)', fault: 'rgb(8, 0, 0)', idle: 'rgb(1, 0, 0)' }[r[p]] || tokens.muted),
  colour: (c) => c, label: (p) => (p === 'status' ? 'Status' : p), unit: () => '', fmt: (v) => String(v),
  featureName: () => '—', geometry: () => null, why: () => {},
});
const plan = (view, rows) => buildPlan(mapSpec(view), rows, helpers(view, rows));

const fleet = [
  { id: 'a', name: 'A', status: 'running', at: [49, -123] },
  { id: 'b', name: 'B', status: 'fault', at: [49, -123] },     // at A's point: one counted marker, two values
  { id: 'c', name: 'C', status: 'running', at: [50, -120] },
  { id: 'd', name: 'D', status: 'idle', at: [51, -114] },
  { id: 'e', name: 'E', status: 'idle', at: null },            // no position: not on the map, so not in the legend
];

test('a marker map coloured by a property has a legend: its title, each value with its colour and count, the rows behind it', () => {
  const p = plan({ coordinates: 'at', markerColor: 'status' }, fleet);
  assert.equal(p.markers, true);
  assert.equal(p.legend.length, 1);
  const [g] = p.legend;
  assert.equal(g.title, 'Status');
  assert.deepEqual(g.rows.map((r) => [r.label, r.colour, r.n, r.rows]), [
    ['running', 'rgb(6, 0, 0)', 2, [0, 2]],
    ['fault', 'rgb(8, 0, 0)', 1, [1]],
    ['idle', 'rgb(1, 0, 0)', 1, [3]],
  ]);
});

test('the legend says when a counted marker hides a value: it takes its most common value\'s colour', () => {
  const [g] = plan({ coordinates: 'at', markerColor: 'status' }, fleet).legend;
  assert.match(g.note, /1 point holds several values/);
  const [one] = plan({ coordinates: 'at', markerColor: 'status' }, fleet.filter((r) => r.id !== 'b')).legend;
  assert.equal(one.note, undefined, 'no point holds two values: nothing to say');
});

test('the marker legend leads with its answer when it has a few values', () => {
  assert.equal(plan({ coordinates: 'at', markerColor: 'status' }, fleet).answer, '2 running · 1 fault · 1 idle');
});

test('a marker map with one colour has no legend: nothing to explain', () => {
  assert.deepEqual(plan({ coordinates: 'at' }, fleet).legend, []);
  assert.deepEqual(plan({ coordinates: 'at', markerColor: 'var(--data-series-2)' }, fleet).legend, []);
});

test('a marker map with no row on it has no legend: a heading over nothing says nothing', () => {
  assert.deepEqual(plan({ markerColor: 'status' }, fleet).legend, [], 'no coordinates: key');
  assert.deepEqual(plan({ coordinates: 'at', markerColor: 'status' }, fleet.filter((r) => r.id === 'e')).legend, [], 'no row has a position');
});

test('featureRows: the rows behind a feature, whichever way the plan wrote them', () => {
  assert.deepEqual(featureRows({ _i: 4 }), [4]);
  assert.deepEqual(featureRows({ _rows: [1, 2] }), [1, 2]);
  assert.deepEqual(featureRows({ _rows: [1, 2], _site: 7 }), [1, 2, 7], 'a catchment is marked by its site too');
  assert.deepEqual(featureRows({ _i: 0 }), [0], 'row 0 is a row');
  assert.deepEqual(featureRows({ _km: 10 }), [], 'a ring is nobody\'s row');
  assert.deepEqual(featureRows(null), []);
});

test('a layer that can hide a row keeps a mark layer over it: a cluster, and a heatmap', () => {
  const clustered = plan({ coordinates: 'at', layers: [{ type: 'points', cluster: true }] }, fleet.slice(0, 4));
  assert.deepEqual(clustered.overlays, [{ source: 'dvl-0', mark: 'dvl-0-m' }]);
  const order = clustered.layers.map((l) => l.id);
  assert.ok(order.indexOf('dvl-0-m') > order.indexOf('dvl-0'), `the mark draws on top: ${order}`);
  const mark = clustered.layers.find((l) => l.id === 'dvl-0-m');
  assert.equal(mark.source, 'dvl-0-m');
  assert.deepEqual(clustered.sources.find((s) => s.id === 'dvl-0-m').data.features, [], 'it starts empty: nothing is marked');
  assert.equal(clustered.sources.find((s) => s.id === 'dvl-0-m').cluster, undefined, 'a mark is never clustered itself');
  assert.ok(clustered.clicks.every((c) => c.layer !== 'dvl-0-m'), 'a mark is not a click target');
  const heat = plan({ coordinates: 'at', layers: [{ type: 'heatmap' }] }, fleet.slice(0, 4));
  assert.deepEqual(heat.overlays, [{ source: 'dvl-0', mark: 'dvl-0-m' }]);
  const plain = plan({ coordinates: 'at', layers: [{ type: 'points' }] }, fleet.slice(0, 4));
  assert.deepEqual(plain.overlays, [], 'a plain point marks itself');
});

test('a timed layer\'s mark is timed with it', () => {
  const rows = fleet.slice(0, 4).map((r, i) => ({ ...r, when: `2026-10-1${i}T00:00:00Z` }));
  const view = { coordinates: 'at', time: 'when', layers: [{ type: 'points', cluster: true }] };
  assert.ok(plan(view, rows).timed.includes('dvl-0-m'));
});

test('the layers a pick can mark read the feature-state: within\'s dots too', () => {
  const rows = [
    { id: 's', name: 'S', kind: 'site', at: [49, -123] },
    { id: 'd', name: 'D', kind: 'demand', at: [49.1, -123] },
  ];
  const view = { coordinates: 'at', layers: [{ type: 'within', of: 'kind == "site"', km: 20 }] };
  const h = helpers(view, rows);
  h.match = () => (r) => r.kind === 'site';
  const p = buildPlan(mapSpec(view), rows, h);
  for (const id of ['dvl-0', 'dvl-0-s']) {
    const spec = JSON.stringify(p.layers.find((l) => l.id === id).paint);
    assert.match(spec, /feature-state/, `${id} draws a mark`);
  }
});
