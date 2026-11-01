// The grouped gallery (docs/CONTRACT.md §20): numeric bins on a group level, the effective grouping, the sections a
// cards view draws (H1 / H2, the null subgroup first and unlabelled), and the nav facet's seam (a group -> a facet ->
// the filter tree -> the URL and back). Every count here is an oracle written with plain loops over the data file,
// never with the kit's own bucketing or grouping.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const grammar = await import('../../packages/core/src/grammar.js');
const rowmodel = await import('../../packages/core/src/rowmodel.js');
const facets = await import('../../packages/core/src/facets.js');
const format = await import('../../packages/core/src/format.js');
const { parseBase } = await import('../../packages/core/src/base.js');
const { checkText } = await import('../../packages/core/src/check.js');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const CASE = join(ROOT, 'gallery', 'examples', 'object-collection');
const data = JSON.parse(readFileSync(join(CASE, 'objects.json'), 'utf8'));
const base = parseBase(readFileSync(join(CASE, 'views.base'), 'utf8'));
// the case's own size bins (views.base), sized for its 366-object public sample: 78 / 135 / 113 / 40
const EDGES = [250, 1000, 5000];
const LABELS = ['< 250 mL', '250 mL – 1 L', '1 L – 5 L', '≥ 5 L'];
const sizeLevel = { property: 'bbox_volume_ml', bins: EDGES, unit: 'mL' };
// the boundary test's own synthetic rows keep their hand oracle on four edges (independent of the case's data)
const WIDE = [250, 1000, 5000, 50000];
const wideLevel = { property: 'bbox_volume_ml', bins: WIDE, unit: 'mL' };

const fn = (mod, name) => {
  assert.equal(typeof mod[name], 'function', `${name} is exported`);
  return mod[name];
};

// ---- the oracle: which bucket a number falls in is how many edges are at or below it ([min, max) buckets)
function bucketIndex(v) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  let i = 0;
  while (i < EDGES.length && v >= EDGES[i]) i++;
  return i;
}
function bucketCounts(rows) {
  const counts = new Array(EDGES.length + 1).fill(0);
  let none = 0;
  for (const r of rows) {
    const i = bucketIndex(r.bbox_volume_ml && typeof r.bbox_volume_ml === 'object' ? r.bbox_volume_ml.value : r.bbox_volume_ml);
    if (i === null) none++;
    else counts[i]++;
  }
  return { counts, none };
}

test('bins: one group per [min, max) bucket of bbox_volume_ml, ascending, counts equal a loop over the case rows', () => {
  const m = rowmodel.rowModel(data, null, { type: 'cards', name: 'size', groupBy: sizeLevel });
  const { counts, none } = bucketCounts(data.rows);
  const want = LABELS.map((l, i) => [l, counts[i]]).filter(([, n]) => n);
  if (none) want.push(['No bbox_volume_ml', none]);
  assert.deepEqual(m.groups.map((g) => [format.groupLabel(m.columns, g.property, g.key), g.rows.length]), want);
  assert.equal(m.groups.reduce((n, g) => n + g.rows.length, 0), data.rows.length);
  // a bucket's key is text that sorts in the buckets' order
  const keys = m.groups.map((g) => g.key).filter((k) => k !== null);
  assert.ok(keys.every((k) => typeof k === 'string'), JSON.stringify(keys));
  assert.deepEqual([...keys].sort(), keys);
  // every row sits in the bucket the oracle puts it in
  for (const g of m.groups) {
    const i = LABELS.indexOf(format.groupLabel(m.columns, g.property, g.key));
    for (const r of g.rows) assert.equal(bucketIndex(r.bbox_volume_ml), i, r.id);
  }
  // the dataset's own column is never marked
  assert.equal(data.properties.bbox_volume_ml.bins, undefined);
});

test('bins: a value on an edge goes to the upper bucket; empty buckets are left out; no value falls in "No …", last, also with DESC', () => {
  const rows = [249.99, 250, 999.5, 1000, 50000, 50001, null, 'big', { value: 1000, basis: 'measured' }, { value: null, why: 'not measured' }]
    .map((v, i) => ({ id: `r${i}`, name: `r${i}`, bbox_volume_ml: v }));
  const set = { id: 't', titleProperty: 'name', properties: { name: { type: 'text' }, bbox_volume_ml: { type: 'number', unitText: 'mL' } }, rows };
  const m = rowmodel.rowModel(set, { properties: { bbox_volume_ml: { displayName: 'Size' } } }, { type: 'cards', name: 's', groupBy: wideLevel });
  const got = m.groups.map((g) => [format.groupLabel(m.columns, g.property, g.key), g.rows.map((r) => r.id)]);
  // oracle by hand: 1000 (and the rich cell 1000) is in 1 L – 5 L, 250 in 250 mL – 1 L, 50000 in ≥ 50 L; no row in 5 L – 50 L
  assert.deepEqual(got, [
    ['< 250 mL', ['r0']],
    ['250 mL – 1 L', ['r1', 'r2']],
    ['1 L – 5 L', ['r3', 'r8']],
    ['≥ 50 L', ['r4', 'r5']],
    ['No size', ['r6', 'r7', 'r9']],
  ]);
  // a row's raw value labels as its bucket, as a time level's date does (groupLabel from a leaf)
  assert.equal(format.groupLabel(m.columns, 'bbox_volume_ml', 250), '250 mL – 1 L');
  assert.equal(format.groupLabel(m.columns, 'bbox_volume_ml', 1000), '1 L – 5 L');
  assert.equal(format.groupLabel(m.columns, 'bbox_volume_ml', null), 'No size');
  const desc = rowmodel.rowModel(set, null, { type: 'cards', name: 's', groupBy: { ...wideLevel, direction: 'DESC' } });
  assert.deepEqual(desc.groups.map((g) => format.groupLabel(desc.columns, g.property, g.key)), ['≥ 50 L', '1 L – 5 L', '250 mL – 1 L', '< 250 mL', 'No bbox_volume_ml']);
  // labelled buckets [{label, min, max}], and auto edges (facets.js' nice edges, here on a log scale) cover every row
  const named = rowmodel.rowModel(set, null, { type: 'cards', name: 's', groupBy: { property: 'bbox_volume_ml', bins: [{ label: 'Small', max: 1000 }, { label: 'Large', min: 1000 }] } });
  assert.deepEqual(named.groups.map((g) => [format.groupLabel(named.columns, g.property, g.key), g.rows.length]), [['Small', 3], ['Large', 4], ['No bbox_volume_ml', 3]]);
  const auto = rowmodel.rowModel(data, null, { type: 'cards', name: 's', groupBy: { property: 'bbox_volume_ml', bins: 'auto', log: true } });
  assert.ok(auto.groups.length >= 3, `${auto.groups.length} auto buckets`);
  assert.equal(auto.groups.reduce((n, g) => n + g.rows.length, 0), data.rows.length);
  const bins = auto.columns.bbox_volume_ml.bins;
  assert.ok(Array.isArray(bins) && bins.length >= auto.groups.length);
  for (const g of auto.groups) {
    const b = bins.find((x) => x.key === g.key);
    for (const r of g.rows) assert.ok((b.min === undefined || r.bbox_volume_ml >= b.min) && (b.max === undefined || r.bbox_volume_ml < b.max), `${r.bbox_volume_ml} in ${b.label}`);
  }
  // the helpers are the core's: grammar's binsOf / binKey, facets' groupBuckets (one copy of the bucket machinery)
  assert.deepEqual(fn(grammar, 'binsOf')(sizeLevel), EDGES);
  assert.equal(fn(grammar, 'binsOf')({ property: 'x' }), null);
  const buckets = fn(facets, 'groupBuckets')(sizeLevel, [1, 2, 3], 'mL');
  assert.deepEqual(buckets.map((b) => b.label), LABELS);
  assert.equal(fn(grammar, 'binKey')(1000, buckets), buckets[2].key);
  assert.equal(fn(grammar, 'binKey')('big', buckets), null);
  const index = readFileSync(join(ROOT, 'packages', 'core', 'src', 'index.js'), 'utf8');
  for (const name of ['binsOf', 'binKey', 'groupBuckets', 'effectiveView', 'sectionsOf', 'groupEntries', 'groupFacet']) assert.match(index, new RegExp(`\\b${name}\\b`), `@data-ui/core exports ${name}`);
});

test('nesting: H1 per family, H2 per area only where a family has one; the null subgroup is first and unlabelled', () => {
  const sectionsOf = fn(rowmodel, 'sectionsOf');
  const m = rowmodel.rowModel(data, base, { type: 'cards', name: 'n', groupBy: { property: 'family' }, subGroupBy: { property: 'area' } });
  const sections = sectionsOf(m.groups, m.columns);
  // the oracle: rows per family and per (family, area), by plain loops
  const fam = new Map(), area = new Map();
  for (const r of data.rows) {
    fam.set(r.family, (fam.get(r.family) || 0) + 1);
    const k = `${r.family}|${r.area}`;
    area.set(k, (area.get(k) || 0) + 1);
  }
  assert.deepEqual(new Map(sections.map((s) => [s.key, s.count])), fam);
  for (const s of sections) {
    assert.equal(s.label, format.groupLabel(m.columns, 'family', s.key));
    assert.equal(s.count, s.rows.length);
    assert.equal(s.subs.reduce((n, x) => n + x.rows.length, 0), s.count, `${s.key}: its subgroups hold every row`);
    const named = s.subs.filter((x) => x.key !== null);
    const want = [...area.keys()].filter((k) => k.startsWith(`${s.key}|`) && !k.endsWith('|null')).map((k) => [k.split('|')[1], area.get(k)]).sort();
    assert.deepEqual(named.map((x) => [x.label, x.count]).sort(), want, `${s.key}: its H2s`);
    const none = s.subs.filter((x) => x.key === null);
    if (area.has(`${s.key}|null`)) {
      assert.equal(s.subs[0].key, null, `${s.key}: the rows with no area come first`);
      assert.equal(s.subs[0].label, null, `${s.key}: and draw no H2`);
      assert.equal(s.subs[0].count, area.get(`${s.key}|null`));
    }
    assert.ok(none.length <= 1);
  }
  // Metals has no area at all: one unlabelled subgroup, so no second layer (McMaster's "Pipe, Tubing, Hose & Fittings")
  const metal = sections.find((s) => s.key === 'metal');
  assert.equal(metal.label, 'Metals');
  assert.deepEqual(metal.subs.map((x) => [x.key, x.label, x.count]), [[null, null, fam.get('metal')]]);
  // Plastics: the non-food rows first and unlabelled, then Medical and Food
  const plastic = sections.find((s) => s.key === 'plastic');
  assert.deepEqual(plastic.subs.map((x) => x.label), [null, ...plastic.subs.slice(1).map((x) => x.label)]);
  assert.deepEqual(plastic.subs.slice(1).map((x) => x.label).sort(), ['Food', 'Medical']);
  // with no subGroupBy every section is one unlabelled subgroup
  const flat = rowmodel.rowModel(data, base, { type: 'cards', name: 'f', groupBy: { property: 'family' } });
  assert.ok(sectionsOf(flat.groups, flat.columns).every((s) => s.subs.length === 1 && s.subs[0].label === null && s.subs[0].count === s.count));
});

test('groupings: grouping: <id> resolves to that entry\'s groupBy / subGroupBy / tiles; an unknown id falls back to the view\'s own', () => {
  const effectiveView = fn(grammar, 'effectiveView');
  const home = base.views.find((v) => v.name === 'Home');
  const view = { ...home, grouping: 'size' };
  const before = JSON.stringify(view);
  const eff = effectiveView(view);
  assert.equal(JSON.stringify(view), before, 'the view entry is not changed');
  const size = home.groupings.find((g) => g.id === 'size');
  assert.deepEqual(eff.groupBy, size.groupBy);
  assert.equal(eff.subGroupBy, undefined, 'the size grouping has no second level');
  assert.deepEqual(eff.tiles, size.tiles);
  const type = effectiveView({ ...home, grouping: 'type' });
  assert.deepEqual(type.groupBy, { property: 'type_name' });
  assert.equal(type.tiles, undefined, 'the type grouping draws the rows themselves');
  for (const g of [undefined, 'nope']) {
    const own = effectiveView({ ...home, grouping: g });
    assert.deepEqual([own.groupBy, own.subGroupBy, own.tiles], [home.groupBy, home.subGroupBy, home.tiles], `grouping ${g}`);
  }
  // the row model groups by the effective level (and so does every view: they read the model's groups)
  const m = rowmodel.rowModel(data, base, view);
  assert.ok(m.groups.every((g) => g.property === 'bbox_volume_ml' && !g.groups));
  assert.equal(m.groups.length, bucketCounts(data.rows).counts.filter(Boolean).length);
  const back = rowmodel.rowModel(data, base, { ...home, grouping: 'nope' });
  assert.ok(back.groups.every((g) => g.property === 'family' && Array.isArray(g.groups)));
  // a host caches the model on MODEL_KEYS, so switching the grouping must change the key
  for (const k of ['grouping', 'groupings']) assert.ok(rowmodel.MODEL_KEYS.includes(k), `MODEL_KEYS has ${k}`);
  // the Node checker: an unknown id warns, a good file is clean
  const text = readFileSync(join(CASE, 'views.base'), 'utf8');
  assert.deepEqual(checkText(text, { properties: new Set(Object.keys(data.properties)), types: Object.fromEntries(Object.entries(data.properties).map(([k, v]) => [k, v.type])) }), []);
  const bad = checkText(text.replace('grouping: material', 'grouping: materal'));
  assert.deepEqual(bad.map((p) => [p.level, p.path.join('.')]), [['warning', 'views.0.grouping']]);
  assert.match(bad[0].message, /did you mean 'material'/);
});

test('nav and setFacet\'s seam: a group -> its facet -> the filter tree -> ?family=metal / ?bbox_volume_ml=250..<1000 -> back', () => {
  const groupFacet = fn(facets, 'groupFacet');
  const groupEntries = fn(rowmodel, 'groupEntries');
  const props = rowmodel.properties(data, base);
  // a value
  const metal = groupFacet(props, 'family', 'metal');
  assert.deepEqual(metal, { values: ['metal'], match: 'equals' });
  const tree = facets.fromRail({ family: metal });
  assert.deepEqual(tree, { and: ['family == "metal"'] });
  assert.deepEqual(facets.toRail(tree).facets, { family: metal });
  const params = facets.railParams(facets.toRail(tree).facets);
  assert.deepEqual(params, [['family', 'metal']]);
  assert.deepEqual(facets.paramsRail(params, props, new Set(['family'])), { family: metal });
  assert.equal(data.rows.filter(grammar.compileFilters(tree)).length, data.rows.filter((r) => r.family === 'metal').length);
  // a bin's range: p >= a and p < b
  const m = rowmodel.rowModel(data, base, { type: 'cards', name: 's', groupBy: sizeLevel });
  const g = m.groups.find((x) => format.groupLabel(m.columns, x.property, x.key) === '250 mL – 1 L');
  const bin = groupFacet(m.columns, 'bbox_volume_ml', g.key);
  assert.deepEqual(bin, { min: 250, max: 1000, maxOpen: true });
  const binTree = facets.fromRail({ bbox_volume_ml: bin });
  assert.deepEqual(binTree, { and: ['bbox_volume_ml >= 250', 'bbox_volume_ml < 1000'] });
  const binParams = facets.railParams(facets.toRail(binTree).facets);
  assert.deepEqual(binParams, [['bbox_volume_ml', '250..<1000']]);
  assert.deepEqual(facets.paramsRail(binParams, props, new Set(['bbox_volume_ml'])), { bbox_volume_ml: bin });
  assert.equal(data.rows.filter(grammar.compileFilters(binTree)).length, bucketCounts(data.rows).counts[1]);
  assert.equal(data.rows.filter(grammar.compileFilters(binTree)).length, g.rows.length);
  // the open-ended buckets: "< 250 mL" is max only, "≥ 50 L" min only
  const lo = m.groups.find((x) => format.groupLabel(m.columns, x.property, x.key) === '< 250 mL');
  assert.deepEqual(groupFacet(m.columns, 'bbox_volume_ml', lo.key), { max: 250, maxOpen: true });
  assert.equal(groupFacet(m.columns, 'family', null), null, 'no value has no facet');
  // the nav facet: kind `nav`, following the view's effective groupBy, and the rail can draw what it writes
  assert.ok(facets.KINDS.nav, 'KINDS.nav');
  const home = base.views.find((v) => v.name === 'Home');
  const specs = facets.facetSpecs(base, home, props);
  assert.deepEqual(specs.map((s) => [s.as, s.property, s.label]), [['nav', 'family', 'Choose a Material']]);
  const sized = facets.facetSpecs(base, { ...home, grouping: 'size' }, props);
  assert.deepEqual(sized.map((s) => [s.as, s.property]), [['nav', 'bbox_volume_ml']]);
  assert.deepEqual(facets.toRail(tree, facets.railConfig(specs)), { facets: { family: metal }, rest: [] });
  assert.deepEqual(facets.toRail(binTree, facets.railConfig(sized)), { facets: { bbox_volume_ml: bin }, rest: [] });
  // the URL may carry any grouping's nav (allSpecs): a link to ?bbox_volume_ml=… works while the page groups by family
  const known = facets.railProperties(facets.allSpecs(base, props));
  for (const p of ['family', 'bbox_volume_ml', 'geometry_class', 'type_name', 'source']) assert.ok(known.has(p), `URL key ${p}`);
  // nav rows: the view's own top-level groups (its order and labels), disjunctive: counted without the nav's own pick
  const entries = groupEntries(data, base, home, {});
  const fam = new Map();
  for (const r of data.rows) fam.set(r.family, (fam.get(r.family) || 0) + 1);
  assert.deepEqual(new Map(entries.map((e) => [e.key, e.n])), fam);
  assert.deepEqual(entries.find((e) => e.key === 'metal'), { key: 'metal', label: 'Metals', n: fam.get('metal'), facet: metal });
  const home0 = rowmodel.rowModel(data, base, home);
  assert.deepEqual(entries.map((e) => e.key), home0.groups.map((x) => x.key), 'the rail lists the groups in the order the view draws them');
  const food = facets.fromRail({ grade: { values: ['food'], match: 'equals' } });
  const under = groupEntries(data, base, home, { filters: food });
  const want = new Map();
  for (const r of data.rows) if (r.grade === 'food') want.set(r.family, (want.get(r.family) || 0) + 1);
  assert.deepEqual(new Map(under.map((e) => [e.key, e.n])), want);
  const bins = groupEntries(data, base, { ...home, grouping: 'size' }, {});
  const { counts } = bucketCounts(data.rows);
  assert.deepEqual(bins.map((e) => [e.label, e.n]), LABELS.map((l, i) => [l, counts[i]]).filter(([, n]) => n));
  assert.deepEqual(bins[1].facet, bin);
});

test('both checkers: bins, tiles, groupings, switcher and nav are known; their mistakes are named alike', async () => {
  const { spawnSync } = await import('node:child_process');
  const { mkdtempSync, writeFileSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const dir = mkdtempSync(join(tmpdir(), 'collection-'));
  const types = { name: 'text', family: 'text', area: 'text', type_name: 'text', bbox_volume_ml: 'number', streams: 'list', source: 'text' };
  const properties = new Set(Object.keys(types));
  const good = `views:
  - type: cards
    name: Home
    groupBy: { property: family }
    sections: true
    tiles: { property: type_name, all: true, limit: 12, size: 96 }
    grouping: size
    keepFilter: true
    switcher: tabs
    groupings:
      - { id: size, label: Size, groupBy: { property: bbox_volume_ml, bins: [250, 1000], unit: mL } }
      - { id: auto, groupBy: { property: bbox_volume_ml, bins: auto, log: true } }
facets:
  - { as: nav, follow: groupBy, clear: true }
`;
  assert.deepEqual(checkText(good, { properties, types }), []);
  const cases = [
    [good.replace('switcher: tabs', 'switcher: pills'), 'error', 'views.0.switcher', /is not one of tabs, segmented, dropdown, none/],
    [good.replace('bins: auto', 'bins: sometimes'), 'error', 'views.0.groupings.1.groupBy.bins', /./],
    [good.replace('{ property: family }', '{ property: bbox_volume_ml, bins: [1, 10], by: week }'), 'error', 'views.0.groupBy.bins', /not both/],
    [good.replace('{ property: family }', '{ property: family, bins: [1, 10] }'), 'warning', 'views.0.groupBy.bins', /number/],
    [good.replace('tiles: { property: type_name', 'tiles: { property: type_nam'), 'error', 'views.0.tiles.property', /did you mean 'type_name'/],
    [good.replace('id: auto', 'id: size'), 'error', 'views.0.groupings.1.id', /twice|already/],
  ];
  for (const [text, level, path, message] of cases) {
    const got = checkText(text, { properties, types }).filter((p) => p.path.join('.') === path);
    assert.ok(got.some((p) => p.level === level && message.test(p.message)), `${path}: ${JSON.stringify(got)}`);
    // the Python checker says the same (its summary line)
    const file = join(dir, 'v.base');
    writeFileSync(file, text);
    writeFileSync(join(dir, 'd.json'), JSON.stringify({ properties: Object.fromEntries(Object.entries(types).map(([k, t]) => [k, { type: t }])), rows: [] }));
    const node = checkText(text, { properties, types });
    const py = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), file, '--data', join(dir, 'd.json')]).stdout.toString().trim().split('\n').at(-1);
    assert.match(py, new RegExp(`${node.filter((p) => p.level === 'error').length} errors, ${node.filter((p) => p.level === 'warning').length} warnings`), `${path}: python ${py}`);
  }
});
