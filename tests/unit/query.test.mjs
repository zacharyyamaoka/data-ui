// The query bar's grammar (docs/CONTRACT.md §15): every clause shape -> its Bases expression, the round-trip law
// parseQuery(formatQuery(filters, words)) == (filters' clauses, words), the rail's normal form (facets.js fromRail)
// formatting to a token and parsing back to the identical expression, errors, and suggest()'s properties, operators
// and values with counts checked against a hand count. Data: the toolbar-bar case's 1,149 actuators.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseQuery, formatQuery, clauseToken, suggest, valueLabel } from '../../packages/core/src/toolbar/query.js';
import { fromRail } from '../../packages/core/src/facets.js';
import { compileFilters } from '../../packages/core/src/grammar.js';
import { parseBase } from '../../packages/core/src/base.js';
import { properties } from '../../packages/core/src/rowmodel.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DATA = JSON.parse(readFileSync(join(ROOT, 'gallery', 'examples', 'robotparts-actuators', 'actuators.json'), 'utf8'));
const BASE = parseBase(readFileSync(join(ROOT, 'gallery', 'examples', 'toolbar-bar', 'views.base'), 'utf8'));
// a date property and a hyphenated one, so the text-bound and note["…"] forms are covered too
const COLS = { ...properties(DATA, BASE), listed: { id: 'listed', type: 'date', label: 'Listed' }, 'vibe-status': { id: 'vibe-status', type: 'text', label: 'Vibe status' } };
const ROWS = DATA.rows;
const value = (c) => (c !== null && typeof c === 'object' && !Array.isArray(c) && 'value' in c ? c.value : c);

const SHAPES = [
  ['brand:Steadywin', ['brand == "Steadywin"']],
  ['Brand:Steadywin', ['brand == "Steadywin"']],
  ['BRAND:Steadywin', ['brand == "Steadywin"']],
  ['brand:Steadywin,CubeMars', [{ or: ['brand == "Steadywin"', 'brand == "CubeMars"'] }]],
  ['buses:can', ['buses.contains("can")']],
  ['buses:can,rs485', [{ or: ['buses.contains("can")', 'buses.contains("rs485")'] }]],
  ['-brand:KST', [{ not: ['brand == "KST"'] }]],
  ['-brand:KST,CubeMars', [{ not: ['brand == "KST"', 'brand == "CubeMars"'] }]],
  ['peak_torque:>10', ['peak_torque > 10']],
  ['peak_torque:>=10', ['peak_torque >= 10']],
  ['peak_torque:<10', ['peak_torque < 10']],
  ['peak_torque:<=10.5', ['peak_torque <= 10.5']],
  ['"Peak torque":>10', ['peak_torque > 10']],
  ['peak_torque:10..20', ['peak_torque >= 10', 'peak_torque <= 20']],
  ['peak_torque:10..<20', ['peak_torque >= 10', 'peak_torque < 20']],
  ['peak_torque:>10..<20', ['peak_torque > 10', 'peak_torque < 20']],
  ['peak_torque:10..', ['peak_torque >= 10']],
  ['peak_torque:..20', ['peak_torque <= 20']],
  ['peak_torque:-5..5', ['peak_torque >= -5', 'peak_torque <= 5']],
  ['level:4', ['level == 4']],
  ['has:photo', ['!photo.isEmpty()']],
  ['model~:ak', ['model.contains("ak")']],
  ['model^:AK', ['model.startsWith("AK")']],
  ['brand:"T-Motor AK"', ['brand == "T-Motor AK"']],
  ['brand:"say \\"hi\\""', ['brand == "say \\"hi\\""']],
  ['listed:>=2026-10-19', ['listed >= "2026-10-19"']],
  ['vibe-status:done', ['note["vibe-status"] == "done"']],
  ['(peak_torque > 10 || mass < 100)', ['peak_torque > 10 || mass < 100']],
  ['`brand != "KST"`', ['brand != "KST"']],
  ['(brand == "a (b)")', ['brand == "a (b)"']],
  ['has:photo OR has:price', [{ or: ['!photo.isEmpty()', '!price.isEmpty()'] }]],
  ['model~:ak OR model~:gim', [{ or: ['model.contains("ak")', 'model.contains("gim")'] }]],
];

test('every clause shape parses to the Bases expression the rail and the Filter menu write', () => {
  for (const [text, clauses] of SHAPES) {
    const q = parseQuery(text, COLS);
    assert.deepEqual(q.errors, [], text);
    assert.deepEqual(q.clauses, clauses, text);
    assert.equal(q.words, '', text);
    for (const c of clauses) assert.doesNotThrow(() => compileFilters(c), text);
  }
});

test('free words are the search; clauses anywhere among them come out', () => {
  const q = parseQuery('  gim  brand:Steadywin 4305   peak_torque:>2 ', COLS);
  assert.deepEqual(q.clauses, ['brand == "Steadywin"', 'peak_torque > 2']);
  assert.equal(q.words, 'gim 4305');
  assert.deepEqual(parseQuery('OR', COLS), { clauses: [], words: 'OR', errors: [] });
  assert.equal(parseQuery('foo OR brand:KST', COLS).words, 'foo OR');
});

test('a clause that does not parse is an error with its reason and place, and is not applied', () => {
  const cases = [
    ['nope:1', /no property/i],
    ['peak_torque:>abc', /number/i],
    ['brand:', /value/i],
    ['(peak_torque > )', /./],
    ['has:nope', /no property/i],
    ['peak_torque:20..10', /low|order|less/i],
  ];
  for (const [text, reason] of cases) {
    const q = parseQuery(`gim ${text} kst`, COLS);
    assert.deepEqual(q.clauses, [], text);
    assert.equal(q.words, 'gim kst', text);
    assert.equal(q.errors.length, 1, text);
    assert.match(q.errors[0].reason, reason, text);
    assert.equal(`gim ${text} kst`.slice(q.errors[0].start, q.errors[0].end), text, text);
  }
  // an open quote or parenthesis runs to the end of the text (it may hold spaces), and is one error
  for (const [text, reason] of [['brand:"T-Motor AK', /quote/i], ['(peak_torque > 10', /parenthes/i]]) {
    const q = parseQuery(`gim ${text}`, COLS);
    assert.deepEqual([q.clauses, q.words, q.errors.length], [[], 'gim', 1], text);
    assert.match(q.errors[0].reason, reason, text);
  }
});

test('round trip: parseQuery(formatQuery(filters, words)) gives the same clauses and words, for every shape', () => {
  const all = SHAPES.flatMap(([, c]) => c);
  for (const [, clauses] of SHAPES) {
    const text = formatQuery({ and: clauses }, 'gim 4305', COLS);
    const back = parseQuery(text, COLS);
    assert.deepEqual(back.clauses, clauses, text);
    assert.equal(back.words, 'gim 4305', text);
  }
  const text = formatQuery({ and: all }, '', COLS);
  assert.deepEqual(parseQuery(text, COLS).clauses, all);
  // the other forms a filters value takes: a lone string, none, an expression the bar has no token for
  assert.deepEqual(parseQuery(formatQuery('brand == "KST"', '', COLS), COLS).clauses, ['brand == "KST"']);
  assert.equal(formatQuery(undefined, 'gim', COLS), 'gim');
  for (const odd of ['brand != "KST"', 'note["vibe-status"] != "done"', 'peak_torque > -20', '!torque_density.isEmpty() && price < 150']) {
    const t = formatQuery({ and: [odd] }, '', COLS);
    assert.deepEqual(parseQuery(t, COLS).clauses, [odd], t);
  }
});

test('the rail normal form: every clause fromRail writes formats to a token (not a raw expression) and parses back identically', () => {
  const states = [
    { brand: { values: ['Steadywin'], match: 'equals' } },
    { brand: { values: ['Steadywin', 'CubeMars'], match: 'equals' } },
    { buses: { values: ['can'], match: 'contains' } },
    { buses: { values: ['can', 'ethercat'], match: 'contains' } },
    { brand: { exclude: ['KST'], excludeMatch: 'equals' } },
    { brand: { exclude: ['KST', 'MyActuator'], excludeMatch: 'equals' } },
    { peak_torque: { min: 10 } },
    { peak_torque: { min: 10, max: 20 } },
    { peak_torque: { min: 10, minOpen: true, max: 100, maxOpen: true } },
    { peak_torque: { max: 5.5 } },
    { photo: { has: true } },
    { photo: { hasAny: ['photo', 'price'] } },
    { model: { text: 'ak', textIn: ['model'] } },
    { model: { text: 'ak', textIn: ['model', 'name'] } },
    { model: { text: 'AK', textIn: ['model'], textMatch: 'startsWith' } },
    { listed: { min: '2026-10-19', max: '2026-10-26', maxOpen: true } },
    { level: { values: [4], match: 'equals' } },
    { 'vibe-status': { values: ['done'], match: 'equals' } },
    { brand: { values: ['T-Motor', 'a,b'], match: 'equals' }, peak_torque: { min: 1 }, photo: { has: true } },
  ];
  for (const s of states) {
    const tree = fromRail(s);
    const text = formatQuery(tree, '', COLS);
    assert.deepEqual(parseQuery(text, COLS).clauses, tree.and, `${JSON.stringify(s)} -> ${text}`);
    for (const c of tree.and) {
      const tok = clauseToken(c, COLS);
      assert.ok(!/^[(`]/.test(tok.text), `${JSON.stringify(c)} has a token form, got ${tok.text}`);
      assert.deepEqual(parseQuery(tok.text, COLS).clauses, [c], tok.text);
    }
  }
});

test('clauseToken labels read as words', () => {
  const label = (c) => clauseToken(c, COLS).label;
  assert.equal(label('brand == "Steadywin"'), 'Brand is Steadywin');
  assert.equal(label({ or: ['brand == "Steadywin"', 'brand == "CubeMars"'] }), 'Brand is Steadywin or CubeMars');
  assert.equal(label({ not: ['brand == "KST"'] }), 'Brand is not KST');
  assert.equal(label('peak_torque > 20'), 'Peak torque > 20');
  assert.equal(label('!photo.isEmpty()'), 'Has photo');
  assert.equal(label('model.contains("ak")'), 'Model contains ak');
  assert.equal(label('buses.contains("can")'), 'Bus has can');
  assert.equal(clauseToken('brand == "Steadywin"', COLS).text, 'brand:Steadywin');
  assert.deepEqual(clauseToken('mass > 2 || brand == "KST"', COLS), { text: '(mass > 2 || brand == "KST")', label: 'mass > 2 || brand == "KST"' });
});

const ctx = (filters) => ({ columns: COLS, rows: ROWS, filters });
const handCount = (rows, prop) => {
  const n = new Map();
  for (const r of rows) for (const v of [].concat(value(r[prop]) ?? [])) if (v !== null && v !== '') n.set(String(v), (n.get(String(v)) || 0) + 1);
  return n;
};

test('suggest: properties on an empty or partial word, with a type, a sample and a hint line', () => {
  const s = suggest('', 0, ctx());
  const props = s.items.filter((i) => i.kind === 'property');
  assert.ok(props.length >= 10, `${props.length} properties`);
  assert.ok(props.every((p) => p.insert.endsWith(':') && p.icon && p.detail !== undefined), JSON.stringify(props[0]));
  assert.ok(!props.some((p) => p.insert === 'name:'), 'a hidden property is not offered');
  assert.ok(s.items.some((i) => i.kind === 'hint'));
  assert.deepEqual([s.from, s.to], [0, 0]);
  const b = suggest('gim bra', 7, ctx());
  assert.equal(b.items[0].kind, 'property');
  assert.equal(b.items[0].insert, 'brand:');
  assert.deepEqual([b.from, b.to], [4, 7]);
  // a label with a space is typed quoted, as the grammar reads it
  const byLabel = suggest('"peak t', 7, ctx());
  assert.equal(byLabel.items[0].insert, 'peak_torque:', 'the label matches too');
  // after a complete clause: the next property
  const next = suggest('brand:KST ', 10, ctx());
  assert.equal(next.items[0].kind, 'property');
  assert.deepEqual([next.from, next.to], [10, 10]);
});

test('suggest: after prop: the values with counts under the current filters (that one clause left out), top 12', () => {
  const s = suggest('brand:', 6, ctx());
  const vals = s.items.filter((i) => i.kind === 'value');
  const hand = handCount(ROWS, 'brand');
  assert.equal(vals.length, Math.min(12, hand.size));
  for (const v of vals) assert.equal(v.count, hand.get(v.label), v.label);
  const sorted = [...hand.values()].sort((a, b) => b - a).slice(0, 12);
  assert.deepEqual(vals.map((v) => v.count), sorted);
  assert.ok(vals[0].insert.startsWith('brand:'));
  assert.deepEqual([s.from, s.to], [0, 6]);
  // the current filters count; brand's own clause does not (disjunctive, as the rail counts)
  const filters = { and: ['form == "integrated actuator"', 'brand == "KST"'] };
  const under = suggest('brand:', 6, ctx(filters)).items.filter((i) => i.kind === 'value');
  const handUnder = handCount(ROWS.filter((r) => r.form === 'integrated actuator'), 'brand');
  for (const v of under) assert.equal(v.count, handUnder.get(v.label), v.label);
  // filtered as you type
  const ste = suggest('brand:ste', 9, ctx()).items.filter((i) => i.kind === 'value');
  assert.deepEqual(ste.map((v) => v.label), ['Steadywin']);
  assert.equal(ste[0].insert, 'brand:Steadywin');
  // a list property counts each element
  const bus = suggest('buses:', 6, ctx()).items.filter((i) => i.kind === 'value');
  const hb = handCount(ROWS, 'buses');
  for (const v of bus) assert.equal(v.count, hb.get(v.label), v.label);
  // a negated clause suggests the same values
  assert.ok(suggest('-brand:', 7, ctx()).items.some((i) => i.kind === 'value' && i.insert.startsWith('-brand:')));
});

test('suggest: a number property offers its operators and its range', () => {
  const s = suggest('peak_torque:', 12, ctx());
  const ops = s.items.filter((i) => i.kind === 'operator').map((i) => i.insert);
  assert.ok(['peak_torque:>', 'peak_torque:<'].every((x) => ops.includes(x)), ops.join(' '));
  assert.ok(ops.some((x) => /^peak_torque:[\d.]+\.\.[\d.]+$/.test(x)), ops.join(' '));
  const nums = ROWS.map((r) => value(r.peak_torque)).filter((v) => typeof v === 'number');
  const range = s.items.find((i) => i.kind === 'operator' && i.insert.includes('..'));
  assert.equal(range.insert, `peak_torque:${Math.min(...nums)}..${Math.max(...nums)}`);
  const has = suggest('has:ph', 6, ctx()).items;
  assert.equal(has[0].insert, 'has:photo');
  assert.equal(has[0].count, ROWS.filter((r) => r.photo).length);
});

// robotparts stores a slug and labels it: brand: "steadywin", properties.brand.labels: {steadywin: "Steadywin"}
const slugOf = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-');
const LABELS = Object.fromEntries([...new Set(ROWS.map((r) => r.brand))].map((b) => [slugOf(b), b]));
const LCOLS = { ...COLS, brand: { ...COLS.brand, labels: LABELS } };
const LROWS = ROWS.map((r) => ({ ...r, brand: slugOf(r.brand) }));
const lctx = (filters) => ({ columns: LCOLS, rows: LROWS, filters });

test('labels: suggestions, tokens and valueLabel show a labelled value\'s label; the text and the expression keep the stored value', () => {
  assert.equal(valueLabel(LCOLS, 'brand', 'steadywin'), 'Steadywin');
  assert.equal(valueLabel(LCOLS, 'brand', 'nolabel'), 'nolabel');
  assert.equal(valueLabel(LCOLS, 'peak_torque', 3.5), '3.5');
  const vals = suggest('brand:', 6, lctx()).items.filter((i) => i.kind === 'value');
  assert.ok(vals.length && vals.every((v) => v.label === LABELS[v.insert.slice('brand:'.length)]), JSON.stringify(vals.slice(0, 2)));
  assert.equal(vals.find((v) => v.label === 'Steadywin').insert, 'brand:steadywin');
  // typing the label's start finds it
  assert.deepEqual(suggest('brand:Stead', 11, lctx()).items.filter((i) => i.kind === 'value').map((v) => v.label), ['Steadywin']);
  assert.deepEqual(clauseToken('brand == "steadywin"', LCOLS), { text: 'brand:steadywin', label: 'Brand is Steadywin' });
  assert.equal(clauseToken({ or: ['brand == "steadywin"', 'brand == "cubemars"'] }, LCOLS).label, 'Brand is Steadywin or CubeMars');
  assert.equal(clauseToken({ not: ['brand == "kst"'] }, LCOLS).label, 'Brand is not KST');
});

test('labels: typing the label (any case) is the stored value, so it filters to the rows the rail tick picks', () => {
  for (const typed of ['brand:Steadywin', 'brand:STEADYWIN', 'brand:steadywin', 'brand:"Steadywin"']) {
    assert.deepEqual(parseQuery(typed, LCOLS).clauses, ['brand == "steadywin"'], typed);
  }
  assert.deepEqual(parseQuery('brand:Steadywin,CubeMars', LCOLS).clauses, [{ or: ['brand == "steadywin"', 'brand == "cubemars"'] }]);
  const keep = compileFilters({ and: parseQuery('brand:Steadywin', LCOLS).clauses });
  const rail = compileFilters(fromRail({ brand: { values: ['steadywin'], match: 'equals' } }));
  assert.deepEqual(LROWS.filter(keep).map((r) => r.id), LROWS.filter(rail).map((r) => r.id));
  assert.ok(LROWS.filter(keep).length > 50);
  // the round trip still holds with labels
  const tree = fromRail({ brand: { values: ['steadywin', 'kst'], match: 'equals', exclude: undefined } });
  assert.deepEqual(parseQuery(formatQuery(tree, '', LCOLS), LCOLS).clauses, tree.and);
});
