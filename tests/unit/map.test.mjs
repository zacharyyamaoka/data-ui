// The map view's pure half (packages/views/map/src/analysis.js, plan.js; docs/CONTRACT.md §42). Every oracle here is
// written out by hand (distances on the equator, where one degree of longitude is 111.19 km by Turf's mean radius;
// counts by eye), never computed with the module's own helpers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as h3 from 'h3-js';
import * as A from '../../packages/views/map/src/analysis.js';
import { mapSpec, buildPlan, LAYER_TYPES } from '../../packages/views/map/src/plan.js';

const KM_PER_DEG = 111.19; // Turf's earth radius 6371.0088 km × π / 180
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} vs ${b} (±${tol})`);

test('position: [lat, lng] and "lat, lng" become GeoJSON [lng, lat]; out of range, empty and local metres', () => {
  assert.deepEqual(A.position([49.28, -123.12]), [-123.12, 49.28]);
  assert.deepEqual(A.position('49.28, -123.12'), [-123.12, 49.28]);
  assert.equal(A.position([123, 10]), null, 'latitude past 90');
  assert.equal(A.position(null), null);
  assert.equal(A.position([1, 'x']), null);
  // local: [x, y] metres -> degrees near (0, 0), 111,320 m per degree both ways
  assert.deepEqual(A.position([111320, 55660], 'local'), [1, 0.5]);
  assert.deepEqual(A.lngLatToLocal(A.localToLngLat([12.5, 3])), [12.5, 3]);
});

test('classify: quantile, equal, jenks, manual and unique breaks; a value on a break falls in the lower class', () => {
  const v = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const eq = A.classify(v, { method: 'equal', count: 3 });
  assert.deepEqual(eq.breaks, [4, 7]);
  assert.equal(A.classOf(4, eq), 0);
  assert.equal(A.classOf(4.01, eq), 1);
  assert.equal(A.classOf(10, eq), 2);
  const q = A.classify(v, { method: 'quantile', count: 2 });
  assert.deepEqual(q.breaks, [5.5]);
  // jenks (ckmeans) on two clumps puts the break between them
  const j = A.classify([1, 1.1, 1.2, 9, 9.5, 10], { method: 'jenks', count: 2 });
  assert.deepEqual(j.breaks, [1.2]);
  const m = A.classify(v, { method: 'manual', breaks: [5, 2] });
  assert.deepEqual(m.breaks, [2, 5]);
  assert.equal(m.count, 3);
  // fewer distinct values than classes: one class per value
  const u = A.classify([3, 3, 7], { count: 5 });
  assert.equal(u.method, 'unique');
  assert.equal(u.count, 2);
});

test('missing is never 0: no-data values get class -1 and their own legend count', () => {
  const values = [10, null, 20, undefined, 30, NaN];
  const cls = A.classify(values, { method: 'equal', count: 2 });
  assert.equal(A.classOf(null, cls), -1);
  assert.equal(A.classOf(NaN, cls), -1);
  const leg = A.legendRows(values, cls, ['a', 'b'], String);
  assert.equal(leg.none, 3);
  assert.deepEqual(leg.rows.map((r) => r.n), [2, 1]);
  assert.equal(cls.min, 10, 'the smallest value is 10, not a 0 standing in for the missing ones');
});

test('proportional symbols: circle AREA is proportional to the value', () => {
  const r1 = A.symbolRadius(25, 100, 20), r4 = A.symbolRadius(100, 100, 20);
  near(r4 / r1, 2, 1e-9, 'four times the value, twice the radius');
  assert.equal(A.symbolRadius(null, 100), null);
  assert.equal(A.symbolRadius(-1, 100), null);
});

test('joinRegions: rows meet features by key; several rows fold by summary; unmatched keys are listed', () => {
  const geo = { type: 'FeatureCollection', features: [
    { type: 'Feature', properties: { code: 'a', name: 'A' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } },
    { type: 'Feature', properties: { code: 'b', name: 'B' }, geometry: { type: 'Polygon', coordinates: [[[2, 0], [3, 0], [3, 1], [2, 0]]] } },
  ] };
  const rows = [{ k: 'a', v: 1 }, { k: 'a', v: 5 }, { k: 'z', v: 9 }];
  const j = A.joinRegions(geo, rows, { key: 'code', join: (r) => r.k, value: (r) => r.v, summary: 'sum' });
  assert.equal(j.features[0].properties._v, 6);
  assert.equal(j.features[1].properties._v, null, 'a region with no row has no value, not 0');
  assert.deepEqual(j.features[0].properties._rows, [0, 1]);
  assert.deepEqual(j.unmatched, ['z']);
  assert.equal(j.multi, 1);
  assert.equal(A.joinRegions(geo, rows, { key: 'code', join: (r) => r.k, value: (r) => r.v, summary: 'max' }).features[0].properties._v, 5);
});

test('hexbin: every point lands in exactly one H3 cell, and the counts add up', () => {
  const rows = [[49.28, -123.12], [49.2801, -123.1201], [49.25, -123.0], [49.1, -122.8]];
  const { fc } = A.pointFeatures(rows, (r) => A.position(r));
  const bins = A.hexbin(h3, fc, 8);
  assert.equal(bins.cells.reduce((n, c) => n + c.rows.length, 0), 4);
  assert.equal(bins.cells.length, 3, 'the two points 15 m apart share a cell');
  const shared = bins.cells.find((c) => c.rows.length === 2);
  assert.deepEqual(shared.rows.sort(), [0, 1]);
  assert.equal(bins.fc.features[0].geometry.coordinates[0].length, 7, 'a closed hexagon ring');
});

test('rings: each demand point counts once, in the smallest ring of its NEAREST site', () => {
  const sites = [{ i: 0, at: [0, 0] }, { i: 1, at: [10, 0] }];
  // 0.05° (5.6 km) from site 0; 0.2° (22 km) from site 0; 0.05° from site 1; 2° (222 km) from both
  const demand = [{ i: 2, at: [0.05, 0] }, { i: 3, at: [0.2, 0] }, { i: 4, at: [9.95, 0] }, { i: 5, at: [5, 2] }];
  const r = A.rings(sites, [25, 10], demand);
  assert.deepEqual(r.bands.map((b) => [b.km, b.n]), [[10, 2], [25, 1]]);
  assert.equal(r.outside, 1);
  assert.deepEqual(r.beyond, [5]);
  assert.equal(r.fc.features.length, 4, 'two rings around each of two sites');
});

test('catchments (Voronoi): a demand point belongs to its nearest site; within: the distance test', () => {
  const sites = [{ i: 0, at: [0, 0] }, { i: 1, at: [1, 0] }];
  const demand = [{ i: 2, at: [0.2, 0.1] }, { i: 3, at: [0.4, -0.2] }, { i: 4, at: [0.9, 0] }];
  const c = A.catchments(sites, demand);
  assert.deepEqual(c.counts.map((x) => [x.site, x.n]), [[0, 2], [1, 1]]);
  assert.equal(c.fc.features.length, 2);
  // the boundary between the two cells is x = 0.5 (the perpendicular bisector)
  for (const f of c.fc.features) {
    const xs = f.geometry.coordinates[0].map((p) => p[0]);
    if (f.properties._site === 0) near(Math.max(...xs), 0.5, 1e-6, 'cell 0 ends at the bisector');
    else near(Math.min(...xs), 0.5, 1e-6, 'cell 1 starts at the bisector');
  }
  const w = A.within(sites, demand, 0.15 * KM_PER_DEG);
  assert.deepEqual(w.each.map((e) => e.inside), [false, false, true], 'only the point 0.1° from site 1 is within 0.15°');
  near(w.each[2].km, 0.1 * KM_PER_DEG, 0.05);
  assert.equal(w.inside, 1);
});

test('insidePolygon, arcs and path length', () => {
  const { fc } = A.pointFeatures([[0.5, 0.5], [2, 2], [0.1, 0.9]], (r) => A.position(r));
  const square = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] };
  assert.deepEqual(A.insidePolygon(fc, square), [0, 2]);
  const a = A.arc([0, 0], [1, 0]);
  const c = a.geometry.coordinates;
  assert.deepEqual(c[0], [0, 0]);
  assert.deepEqual(c[c.length - 1], [1, 0]);
  assert.ok(c.some((p) => p[1] < -0.05), 'the arc bows to the right of travel (south, going east)');
  near(A.pathKm([[0, 0], [1, 0], [2, 0]]), 2 * KM_PER_DEG, 0.1);
  assert.equal(A.pathOf([[0, 0]]), null, 'one point is not a path');
});

test('bivariate grid: low-low is the surface, high-high the darkest; ramps go from surface to ink', () => {
  const g = A.bivariateGrid(3, 'rgb(200, 0, 0)', 'rgb(0, 0, 200)', 'rgb(255, 255, 255)');
  const lum = (c) => A.rgbOf(c).reduce((a, b) => a + b, 0);
  assert.ok(lum(g[0][0]) > lum(g[1][1]) && lum(g[1][1]) > lum(g[2][2]));
  const r = A.ramp(4, 'rgb(0, 0, 0)', 'rgb(255, 255, 255)');
  assert.equal(r[3], 'rgb(0, 0, 0)');
  assert.ok(lum(r[0]) > lum(r[1]));
});

test('mapSpec: no layers is the Bases Maps markers; unknown layer types are reported, not drawn', () => {
  assert.deepEqual(mapSpec({}).layers, [{ type: 'markers' }]);
  const s = mapSpec({ layers: [{ type: 'points' }, { type: 'sparkles' }], space: 'local', time: 'at', legend: false });
  assert.deepEqual(s.layers.map((l) => l.type), ['points']);
  assert.deepEqual(s.unknown, ['sparkles']);
  assert.equal(s.space, 'local');
  assert.deepEqual(s.time, { property: 'at' });
  assert.equal(s.legend, 'off');
  assert.ok(LAYER_TYPES.includes('catchments'));
});

// the helpers a view passes to buildPlan, reduced to plain rows {id, ...}
const T = { bg: 'rgb(255, 255, 255)', fg: 'rgb(0, 0, 0)', muted: 'rgb(120, 120, 120)', subtle: 'rgb(240, 240, 240)', border: 'rgb(200, 200, 200)', accent: 'rgb(0, 0, 255)', onAccent: 'rgb(255, 255, 255)', series: ['rgb(10, 10, 200)', 'rgb(200, 10, 10)', 'rgb(10, 200, 10)', 'rgb(1, 1, 1)', 'rgb(2, 2, 2)', 'rgb(3, 3, 3)', 'rgb(4, 4, 4)', 'rgb(5, 5, 5)'] };
const helpers = (geometry = null, view = {}) => ({
  view, tokens: T, h3, state: {}, titleProperty: 'name',
  value: (r, p) => (p ? r[p] : null), raw: (r, p) => (p ? r[p] : null), text: (r, p) => (p && r[p] != null ? String(r[p]) : null), cellText: (r, p) => String(r[p] ?? '—'),
  match: (expr) => { const [k, v] = expr.split(' == '); return (r) => String(r[k.trim()]) === v.trim().replace(/"/g, ''); },
  isProperty: (p) => ['kind', 'year'].includes(p), colourOf: () => T.series[0], unit: (p) => (p === 'v' ? 'kg' : ''), colour: (c) => c,
  label: (p) => p, fmt: (v) => String(v), featureName: (f, L, list) => (f.properties._rows.length ? list[f.properties._rows[0]].name : f.properties.name),
  geometry: () => geometry, why: () => {},
});
const squares = { type: 'FeatureCollection', features: ['a', 'b', 'c'].map((k, i) => ({ type: 'Feature', properties: { code: k, name: k.toUpperCase() }, geometry: { type: 'Polygon', coordinates: [[[i, 0], [i + 1, 0], [i + 1, 1], [i, 0]]] } })) };

test('buildPlan regions: classes over the rows, a region with no value is hatched no-data, the answer names the highest', () => {
  const rows = [{ id: 'r1', code: 'a', name: 'Alpha', v: 10 }, { id: 'r2', code: 'b', name: 'Beta', v: null }, { id: 'r3', code: 'c', name: 'Gamma', v: 30 }];
  const spec = mapSpec({ layers: [{ type: 'regions', geometry: 'x.geojson', key: 'code', join: 'code', value: 'v', classes: { method: 'equal', count: 2 } }] });
  const plan = buildPlan(spec, rows, helpers(squares));
  const fc = plan.sources[0].data;
  assert.deepEqual(fc.features.map((f) => f.properties._k), [0, -1, 1]);
  assert.equal(plan.legend[0].none, 1);
  assert.equal(plan.legend[0].unit, 'kg');
  // two distinct values and two classes: one class per value (classify's rule), said as such in the legend
  assert.match(plan.legend[0].method, /one colour per value, 2 classes/);
  assert.equal(plan.answer, 'Highest: Gamma · 30 kg');
  assert.ok(plan.layers.some((l) => l.paint && l.paint['fill-pattern'] === 'dv-hatch'), 'a hatched no-data layer');
  assert.deepEqual(plan.bounds, [0, 0, 3, 1]);
});

test('buildPlan on a subset (a small multiple, a swipe side) speaks in the FULL rows\' indexes, with the shared classes', () => {
  const rows = [{ id: 'r1', code: 'a', name: 'A2000', v: 1, year: 2000 }, { id: 'r2', code: 'a', name: 'A2024', v: 9, year: 2024 }, { id: 'r3', code: 'b', name: 'B2024', v: 5, year: 2024 }];
  const spec = mapSpec({ layers: [{ type: 'regions', geometry: 'x.geojson', key: 'code', join: 'code', value: 'v', classes: { method: 'equal', count: 2 } }] });
  const h = helpers(squares);
  const all = buildPlan(spec, rows, h);
  const sub = buildPlan(spec, rows.filter((r) => r.year === 2024), h, all.classes, rows);
  const a = sub.sources[0].data.features.find((f) => f.properties.code === 'a');
  assert.deepEqual(a.properties._rows, [1], 'row 1 of the full list, not row 0 of the subset');
  assert.equal(sub.answer, 'Highest: A2024 · 9 kg');
  assert.deepEqual(sub.classes, all.classes, 'the same breaks on every panel');
});

test('buildPlan points: size by value, clusters, colour legend counts; within and rings sections', () => {
  const rows = [{ id: 'p1', name: 'One', at: [0, 0], kind: 'x', v: 4 }, { id: 'p2', name: 'Two', at: [0, 1], kind: 'y', v: 16 }, { id: 'p3', name: 'Three', at: null, kind: 'x', v: 1 }];
  const plan = buildPlan(mapSpec({ coordinates: 'at', layers: [{ type: 'points', size: { property: 'v', max: 20 }, color: 'kind' }] }), rows, { ...helpers(), view: { coordinates: 'at' } });
  const f = plan.sources[0].data.features;
  assert.equal(f.length, 2);
  assert.equal(plan.missing, 1);
  near(f[1].properties._r / f[0].properties._r, 2, 1e-9, '16 is 4 × 4: twice the radius');
  assert.equal(plan.answer, 'Largest: Two · 16 kg');
  const sites = [{ id: 's', name: 'S', at: [0, 0], kind: 'site' }, { id: 'h1', name: 'H1', at: [0, 0.05], kind: 'h' }, { id: 'h2', name: 'H2', at: [0, 1], kind: 'h' }];
  const w = buildPlan(mapSpec({ coordinates: 'at', layers: [{ type: 'within', of: 'kind == site', count: 'kind == h', km: 10 }] }), sites, { ...helpers(), view: { coordinates: 'at' } });
  assert.equal(w.answer, '1 of 2 rows within 10 km');
  assert.equal(w.sections[0].kind, 'within');
});
