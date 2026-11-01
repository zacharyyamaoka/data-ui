// Source columns (docs/CONTRACT.md §36, docs/peps/0021-source-columns.md), the pure half. FROZEN: written before the code, red first.
// Zach, 2026-10-31: "its just like a column roll up where the left most take precencde", "The roll up itsself is also then just like
// a formula.. almost like FIRST Value(of cells, x, y, ...)", "Desired is notions: pattern where you have 1 property per cell".
//
// The formula's truth table below is not this repo's opinion: it is what real Obsidian Bases drew on 2026-10-31, in an isolated
// headless instance (the headless-obsidian skill), on notes with exactly these properties. Bases has no coalesce; its documented
// functions make `[a, b].filter(!value.isEmpty())[0]`, and that spelling errors on a boolean ("Cannot find function "isEmpty" on type
// Boolean"), so the kit reads a second spelling that Obsidian runs on every type.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseCoalesce, coalesceText, cellValue } from '../../packages/core/src/grammar.js';
import { precedenceOf, unfoldDataset, resolveDataset, columnId, slotOrder, orderAfter, inPlace, ownColumns, sourcesView, setSourceValue, foldEdit, sourceRows, isMultiSource } from '../../packages/core/src/precedence.js';
import { checkText, datasetProperties } from '../../packages/core/src/check.js';

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), 'utf8'));
const PART = read('../browser/fixtures/source-precedence/part.json');
const PARTS = read('../browser/fixtures/source-popover/parts.json');
const JMC = read('../browser/fixtures/source-columns/jmc.json');
const LONG = '[a, b].filter(value.isType("boolean") || !value.isEmpty())[0]';
const SHORT = '[a, b].filter(!value.isEmpty())[0]';

/** The dataset as a reader sees it, under the default precedence or `state`. */
function shown(dataset, base = null, state = null) {
  const info = precedenceOf(dataset, base);
  return resolveDataset(unfoldDataset(dataset, info, base), state || (info ? { order: info.default, ov: {} } : {}), info);
}

test('parseCoalesce: the two spellings Obsidian runs, any way a property is named; a list of property ids', () => {
  assert.deepEqual(parseCoalesce(SHORT), ['a', 'b']);
  assert.deepEqual(parseCoalesce(LONG), ['a', 'b']);
  assert.deepEqual(parseCoalesce('[note.a, note["b c"], note["nominal@bench"], d].filter(!value.isEmpty())[0]'), ['a', 'b c', 'nominal@bench', 'd']);
  assert.deepEqual(parseCoalesce("[note['x-y']].filter(!value.isEmpty())[0]"), ['x-y']);
  assert.deepEqual(parseCoalesce(' [ a,b ] . filter( !value.isEmpty() ) [ 0 ] '), ['a', 'b'], 'spaces mean nothing');
});

test('parseCoalesce: anything else is not this formula: null, never a throw and never a guess', () => {
  for (const s of ['a', 'a + b', 'price * 2', 'if(a.isEmpty(), b, a)', 'coalesce(a, b)', '[a, b].filter(value > 2)[0]', '[a, b].filter(!value.isEmpty())[1]', '[a, b].filter(!value.isEmpty())',
    '[a, b].filter(!value.isEmpty()).slice(0, 1)', '[a, 1].filter(!value.isEmpty())[0]', '[formula.x, b].filter(!value.isEmpty())[0]', '[file.name, b].filter(!value.isEmpty())[0]',
    '[].filter(!value.isEmpty())[0]', '[a, b].filter(value.isTruthy())[0]', '[a, b', '', null, undefined, 12]) {
    assert.equal(parseCoalesce(s), null, String(s));
  }
});

test('coalesceText: a list back into the file, bare where Bases reads a bare name, kept in the spelling it had', () => {
  assert.equal(coalesceText(['a', 'b']), LONG, 'with no spelling to keep, the one that runs on every type');
  assert.equal(coalesceText(['b', 'a'], SHORT), '[b, a].filter(!value.isEmpty())[0]');
  assert.equal(coalesceText(['b', 'a'], LONG), '[b, a].filter(value.isType("boolean") || !value.isEmpty())[0]');
  assert.equal(coalesceText(['nominal@bench', 'b c', 'ok_1']), '[note["nominal@bench"], note["b c"], ok_1].filter(value.isType("boolean") || !value.isEmpty())[0]');
  // a name the expression language keeps for itself cannot be written bare: it would read as something else
  assert.equal(coalesceText(['value', 'note', 'file', 'formula', 'true', 'null', 'this']), `[${['value', 'note', 'file', 'formula', 'true', 'null', 'this'].map((x) => `note["${x}"]`).join(', ')}].filter(value.isType("boolean") || !value.isEmpty())[0]`);
  for (const ids of [['a'], ['x y', 'z'], ['manufacturer:jmc-motion.com:for 60ASM400-5-1024C-H', 'q"uote'], ['value']]) assert.deepEqual(parseCoalesce(coalesceText(ids)), ids, 'round trip');
});

test('the formula, on the notes real Obsidian Bases drew: first non-empty wins; 0 and false are values, "", [], null and absent are not', () => {
  const dataset = {
    id: 'notes', titleProperty: 'file', properties: { file: { type: 'text' }, a: { type: 'text' }, b: { type: 'text' }, 'with@sign': { type: 'number' } },
    rows: [
      { id: 'N01', file: 'N01', a: 3.1, b: 3.8 },
      { id: 'N02', file: 'N02', b: 3.8 },
      { id: 'N03', file: 'N03', a: '', b: 0 },
      { id: 'N04', file: 'N04', a: [], b: false },
      { id: 'N05', file: 'N05', a: 0, b: 5 },
      { id: 'N06', file: 'N06' },
      { id: 'N07', file: 'N07', a: false, b: 7 },
      { id: 'N08', file: 'N08', a: [15, 60], b: 1 },
      { id: 'N10', file: 'N10', 'with@sign': 11, b: 2 },
      { id: 'N11', file: 'N11', a: null, b: 'text' },
    ],
  };
  const want = { N01: 3.1, N02: 3.8, N03: 0, N04: false, N05: 0, N06: null, N07: false, N08: [15, 60], N10: 2, N11: 'text' };
  const base = { formulas: { f: LONG, g: '[note["with@sign"], b].filter(!value.isEmpty())[0]' } };
  const out = shown(dataset, base);
  assert.deepEqual(Object.fromEntries(out.rows.map((r) => [r.id, cellValue(r['formula.f']) ?? null])), want);
  assert.equal(cellValue(out.rows.find((r) => r.id === 'N10')['formula.g']), 11, 'note["with@sign"]');
  assert.equal(cellValue(out.rows.find((r) => r.id === 'N01')['formula.g']), 3.8, 'a property the row lacks is empty');
  assert.ok(out.properties['formula.f'], 'a formula is a property of the shown dataset');
  assert.deepEqual(Object.keys(dataset.rows[0]), ['id', 'file', 'a', 'b'], 'the dataset as loaded is not touched');
});

test('the formula cell keeps the winner exactly as stated, provenance and all, and is itself a multi-source cell of the columns it read', () => {
  const dataset = { id: 'd', properties: { name: {}, x: { type: 'number', label: 'X' }, y: { type: 'number', label: 'Y' } }, rows: [{ id: 'r', name: 'R', x: { value: 3, text: '3.0', source: 'Maker', sourceUrl: 'https://example.com/m', note: 'p. 2', basis: 'datasheet' }, y: 4 }] };
  const cell = shown(dataset, { formulas: { n: '[x, y].filter(!value.isEmpty())[0]' } }).rows[0]['formula.n'];
  assert.equal(cell.value, 3);
  assert.equal(cell.text, '3.0');
  assert.equal(cell.source, 'Maker', 'the winner\'s own source, not the column it sat in');
  assert.equal(cell.sourceUrl, 'https://example.com/m');
  assert.equal(cell.note, 'p. 2');
  assert.ok(isMultiSource(cell), 'so the pill, the popover and a pick read it as they read any value with several sources');
  assert.deepEqual(cell.sources.map((e) => [e.source, e.value]), [['x', 3], ['y', 4]]);
});

test('columnId: <property>@<source>; the column that names the winner never takes a source\'s place', () => {
  assert.equal(columnId('nominal', 'bench'), 'nominal@bench');
  assert.equal(columnId('nominal', 'manufacturer:jmc-motion.com:for 60ASM400-5-1024C-H'), 'nominal@manufacturer:jmc-motion.com:for 60ASM400-5-1024C-H');
  assert.equal(columnId('nominal'), 'nominal@source', 'no source: the "<label> source" column');
  assert.notEqual(columnId('nominal', 'source'), columnId('nominal'), 'a source that is really called "source" keeps a column of its own');
});

test('unfold: one property per source, after nothing changes in the file; an ordinary typed column a view may name', () => {
  const before = JSON.stringify(PART);
  const out = shown(PART);
  assert.equal(JSON.stringify(PART), before, 'never mutates what was loaded');
  const p = out.properties['nominal@bench'];
  assert.equal(p.label, 'Bench test 1');
  assert.equal(p.type, PART.properties.nominal.type, 'typed as its value');
  assert.equal(p.unit, 'unit', 'and it reads its unit the way its value does');
  assert.equal(p.hidden, true, 'no view shows it unless it says so');
  assert.equal(p.offered, true, 'but Property visibility and the inspector offer it, as a hidden: true property is not');
  assert.equal(p.of, 'nominal');
  assert.equal(p.source, 'bench');
  assert.equal(out.properties['nominal@source'].label, 'Nominal source');
  assert.equal(out.properties['nominal@source'].hidden, true);
  for (const id of Object.keys(PART.properties)) assert.ok(out.properties[id], `${id} stays`);
  const peak = out.rows.find((r) => r.id === 'peak_torque');
  assert.equal(cellValue(peak['nominal@bench']), 3.1);
  assert.equal(peak['nominal@chat'].text, '3.8 Nm', 'the entry\'s own words');
  assert.equal(peak['nominal@bench'].source, 'Bench test 1', 'a §22 cell, its source named, as the popover reads it');
  assert.equal(peak['nominal@bench'].sourceUrl, 'https://example.com/lab/bench-1', 'the source\'s address where the entry has none');
  assert.equal(peak.nominal.value, 3.1);
  assert.equal(peak.nominal.sources, PART.rows[0].nominal.sources, 'every entry still on the nominal, the same objects');
  const none = out.rows.find((r) => r.id === 'kt');
  assert.equal(none['nominal@bench'] ?? null, null, 'a source with no entry is an empty cell');
  const encoder = out.rows.find((r) => r.id === 'encoder');
  assert.equal(cellValue(encoder['nominal@datasheet']), '14-bit magnetic', 'a plain §22 cell sits under the source its name is');
  assert.equal(encoder.nominal.value, '14-bit magnetic', 'and stays the value of its row');
});

test('unfold: two values with several sources: a column per value and source, labels that read apart', () => {
  const out = shown(PARTS);
  assert.ok(out.properties['torque@maker'] && out.properties['mass@maker']);
  assert.notEqual(out.properties['torque@maker'].label, out.properties['mass@maker'].label);
  assert.equal(cellValue(out.rows[0]['torque@bench']), 10.5);
  assert.equal(cellValue(out.rows[0]['mass@bench']), 492);
  assert.equal(out.properties['torque@shop'], undefined, 'no column for a source that states nothing of this value');
});

test('no sources: the same dataset object, and no columns; only a declared sourceColumn adds its one column', () => {
  const plain = { id: 'd', properties: { a: {}, b: {} }, rows: [{ id: '1', a: { value: 1, source: 'x' }, b: 2 }] };
  assert.equal(shown(plain), plain, 'data with no multi-source cell is the same object, so nothing changes for it');
  assert.equal(precedenceOf(plain), null);
  const declared = { ...plain, sourceColumn: true };
  const out = shown(declared);
  assert.equal(precedenceOf(declared), null, 'one-source data has no precedence');
  assert.equal(out.rows[0]['a@source'].value, 'x', 'and its one column names each row\'s source');
  assert.deepEqual(Object.keys(out.properties), ['a', 'b', 'a@source']);
  const off = shown({ ...PART, sourceColumn: false });
  assert.ok(off.properties['nominal@source'], 'sourceColumn: false only stops it being drawn unasked; it stays a column a view may name');
});

test('a derived value names what it came from: the column says so, and follows the value shown', () => {
  const data = { id: 'd', sourceColumn: true, properties: { name: {}, v: { type: 'number' } }, rows: [
    { id: '1', name: 'A', v: { value: 5, basis: 'derived', source: 'Selection list' } },
    { id: '2', name: 'B', v: { value: 6, basis: 'derived', sourceUrl: 'https://example.com/list' } },
    { id: '3', name: 'C', v: 7 },
  ] };
  const rows = shown(data).rows;
  assert.equal(rows[0]['v@source'].value, 'Selection list');
  assert.equal(rows[0]['v@source'].derived, true);
  assert.equal(rows[1]['v@source'].url, 'https://example.com/list', 'named only by its address');
  assert.equal(cellValue(rows[2]['v@source']) ?? null, null, 'nothing named: an empty cell, "—", never a made-up name');
  const jmc = shown(JMC).rows;
  assert.equal(jmc.find((r) => r.id === 'pole_pairs')['nominal@source'].derived, true);
  assert.notEqual(jmc.find((r) => r.id === 'peak_torque')['nominal@source'].derived, true);
});

test('inPlace: the wanted items, in their new order, in the places they held; everything else stays', () => {
  assert.deepEqual(inPlace(['a', 'b', 'c', 'd'], ['c', 'a']), ['c', 'b', 'a', 'd']);
  assert.deepEqual(inPlace(['a', 'b', 'c', 'd'], ['d', 'b', 'a']), ['d', 'b', 'c', 'a']);
  assert.deepEqual(inPlace(['a', 'b'], ['a', 'b']), ['a', 'b']);
  assert.deepEqual(inPlace(['a', 'b'], []), ['a', 'b']);
  const list = ['a', 'b'];
  inPlace(list, ['b', 'a']);
  assert.deepEqual(list, ['a', 'b'], 'never mutates');
});

test('slotOrder: the columns a formula reads sit in its order, wherever a view placed them; left-most is always the winner', () => {
  const info = precedenceOf(PART);
  const order = ['chat', 'bench', 'datasheet', 'listing'];
  assert.deepEqual(slotOrder(['field', 'nominal@bench', 'nominal', 'nominal@chat', 'unit'], info, order), ['field', 'nominal@chat', 'nominal', 'nominal@bench', 'unit']);
  assert.deepEqual(slotOrder(['field', 'nominal'], info, order), ['field', 'nominal'], 'no column of it: nothing to do');
  assert.deepEqual(slotOrder(['field', 'nominal@source', 'nominal'], info, order), ['field', 'nominal@source', 'nominal'], 'the source column reads no source');
  const two = precedenceOf(PARTS);
  assert.deepEqual(slotOrder(['torque@bench', 'mass@bench', 'torque@maker', 'mass@maker'], two, ['maker', 'bench', 'shop']), ['torque@maker', 'mass@maker', 'torque@bench', 'mass@bench'], 'each value\'s columns in their own slots');
});

test('orderAfter: a reorder of the same columns is the precedence; a hide or a show is not; a hidden source keeps its place', () => {
  const info = precedenceOf(PART);
  const order = ['bench', 'datasheet', 'listing', 'chat'];
  const v = (...s) => s.map((x) => `nominal@${x}`);
  assert.deepEqual(orderAfter(['field', ...v('bench', 'datasheet', 'chat')], ['field', ...v('chat', 'bench', 'datasheet')], info, order), ['chat', 'bench', 'listing', 'datasheet'], 'listing is hidden: it stays third');
  assert.deepEqual(orderAfter(v('bench', 'chat'), v('chat'), info, order), order, 'a hide changes nothing');
  assert.deepEqual(orderAfter(v('bench'), v('bench', 'chat'), info, order), order, 'a show changes nothing, wherever it landed');
  assert.deepEqual(orderAfter(v('bench', 'listing'), v('listing', 'chat'), info, order), order, 'one in, one out: no reorder of the same columns');
  assert.deepEqual(orderAfter(['a', ...v('bench', 'chat'), 'b'], ['b', ...v('bench', 'chat'), 'a'], info, order), order, 'moving other columns changes nothing');
  assert.deepEqual(orderAfter(['nominal', ...v('bench', 'chat')], [...v('bench', 'chat'), 'nominal'], info, order), order, 'moving the value past its sources changes nothing');
  assert.equal(orderAfter(v('bench', 'chat'), v('bench', 'chat'), info, order), order, 'no change: the same array');
});

test('the default: the ladder; a file\'s formula states it; else a view\'s left to right; either way the rest keep their ladder places', () => {
  assert.deepEqual(precedenceOf(PART).default, ['bench', 'datasheet', 'listing', 'chat']);
  const f = { formulas: { nominal: '[note["nominal@chat"], note["nominal@datasheet"]].filter(!value.isEmpty())[0]' } };
  assert.deepEqual(precedenceOf(PART, f).default, ['bench', 'chat', 'listing', 'datasheet']);
  const v = { views: [{ type: 'table', name: 'A', order: ['field', 'nominal'] }, { type: 'table', name: 'B', order: ['nominal@listing', 'nominal@bench'] }, { type: 'table', name: 'C', order: ['nominal@chat', 'nominal@bench'] }] };
  assert.deepEqual(precedenceOf(PART, v).default, ['listing', 'datasheet', 'bench', 'chat'], 'the first view that names two of them');
  assert.deepEqual(precedenceOf(PART, { ...v, ...f }).default, ['bench', 'chat', 'listing', 'datasheet'], 'the formula is the text that says it; it wins');
  const plain = { id: 'd', properties: { x: {}, y: {}, z: {} }, rows: [{ id: '1', x: 1, y: 2 }] };
  const g = precedenceOf(plain, { formulas: { n: '[y, x, z].filter(!value.isEmpty())[0]' } });
  assert.deepEqual(g.default, ['y', 'x', 'z']);
  assert.deepEqual(g.properties, ['formula.n']);
  assert.equal(g.sources.y.name, 'y', 'a column stands for a source, under its own label');
  assert.equal(precedenceOf(plain, { formulas: { n: 'x * 2' } }), null, 'no formula data-ui runs: nothing rolls up');
});

test('a formula data-ui does not run is a column that says so, not a value and not a silence', () => {
  const plain = { id: 'd', properties: { x: {} }, rows: [{ id: '1', x: 1 }] };
  const out = shown(plain, { formulas: { n: 'x * 2' } });
  assert.ok(out.properties['formula.n'], 'the view that names it has a column');
  assert.match(out.properties['formula.n'].why, /Obsidian/);
  assert.equal(out.rows[0]['formula.n'] ?? null, null, 'and no value is made up');
});

test('ownColumns: an existing .base keeps "<label> source" after its value, and only an existing one', () => {
  const info = precedenceOf(PART);
  const order = info.default;
  const own = (view, data = PART, i = info) => ownColumns({ type: 'table', ...view }, data, i, order).order;
  assert.deepEqual(own({ order: ['field', 'nominal', 'unit'] }), ['field', 'nominal', 'nominal@source', 'unit'], 'as it always was');
  assert.deepEqual(own({ order: ['field', 'formula.nominal'] }), ['field', 'nominal', 'nominal@source'], 'formula.nominal is Bases\' name for the same column');
  assert.deepEqual(own({ order: ['field', 'nominal', 'nominal@source'] }), ['field', 'nominal', 'nominal@source'], 'named: left where it is');
  assert.deepEqual(own({ order: ['nominal@source', 'field', 'nominal'] }), ['nominal@source', 'field', 'nominal'], 'wherever it is');
  assert.deepEqual(own({ order: ['field', 'nominal', 'nominal@bench'] }), ['field', 'nominal', 'nominal@bench'], 'a view that names a column of the value says what it wants');
  assert.deepEqual(own({ order: ['field', 'nominal'], sourceColumn: false }), ['field', 'nominal'], 'a hide kept in a file: the view says no');
  assert.deepEqual(own({ order: ['field'] }), ['field'], 'a view without the value has no column for it');
  assert.deepEqual(own({ order: ['field', 'nominal'] }, { ...PART, sourceColumn: false }), ['field', 'nominal'], 'dataset sourceColumn: false');
  assert.deepEqual(own({ order: ['field', 'nominal', 'nominal@*'] }), ['field', 'nominal', 'nominal@bench', 'nominal@datasheet', 'nominal@listing', 'nominal@chat'], 'p@* is every source of it, best first');
  assert.deepEqual(own({ order: ['nominal@*', 'field'] }).slice(-1), ['field']);
  assert.deepEqual(own({}), ['id', 'field', 'section', 'nominal', 'nominal@source', 'unit'].filter((x) => x !== 'id'), 'no order: the table\'s default columns, with the column it always added');
  assert.equal(ownColumns({ type: 'cards', name: 'C' }, PART, info, order).order, undefined, 'another view type with no order has none');
  assert.deepEqual(ownColumns({ type: 'cards', order: ['field', 'nominal'] }, PART, info, order).order, ['field', 'nominal'], 'only a table draws the column');
  assert.deepEqual(ownColumns({ type: 'pivot', order: ['field', 'nominal'] }, PART, info, order).order, ['field', 'nominal']);
  const plain = { id: 'd', properties: { a: {} }, rows: [{ id: '1', a: 1 }] };
  const view = { type: 'table', order: ['a'] };
  assert.equal(ownColumns(view, plain, null, null), view, 'nothing to do: the same view');
});

test('ownColumns: sourceColumn: true on one-source data: after the first column that names a source; else the first after the title', () => {
  const sc = { id: 'd', titleProperty: 'f', sourceColumn: true, properties: { f: {}, s: {}, n: {} }, rows: [{ id: '1', f: 'A', s: 'x', n: { value: 1, source: 'm' } }] };
  assert.deepEqual(ownColumns({ type: 'table', order: ['f', 's', 'n'] }, sc, null, null).order, ['f', 's', 'n', 'n@source']);
  const none = { ...sc, rows: [{ id: '1', f: 'A', s: 'x', n: 1 }] };
  assert.deepEqual(ownColumns({ type: 'table', order: ['f', 's', 'n'] }, none, null, null).order, ['f', 's', 's@source', 'n']);
  assert.ok(shown(none).properties['s@source'], 'the column exists to be drawn');
});

test('sourcesView: the saved view that takes Manage sources\' place: the file\'s view with the sources shown, and only when the file has none', () => {
  const info = precedenceOf(PART);
  const views = [{ type: 'cards', name: 'K', order: ['field', 'nominal'] }, { type: 'table', name: 'Datasheet', order: ['field', 'nominal', 'unit'], groupBy: { property: 'section' }, units: 'inline' }];
  const out = sourcesView(views, info);
  assert.equal(out.name, 'Sources');
  assert.equal(out.type, 'table');
  assert.deepEqual(out.order, ['field', 'nominal', 'nominal@*', 'unit'], 'in place of "<label> source", best first when opened');
  assert.deepEqual(out.groupBy, { property: 'section' }, 'that view, with its columns shown: its groups and units stay');
  assert.equal(out.units, 'inline');
  assert.equal(sourcesView([...views, { type: 'table', name: 'Mine', order: ['nominal@bench'] }], info), null, 'a file that names a source column has made its own');
  assert.equal(sourcesView([...views, { type: 'table', name: 'Mine', order: ['nominal@*'] }], info), null);
  assert.equal(sourcesView([...views, { type: 'cards', name: 'Sources' }], info), null, 'the name is taken');
  assert.equal(sourcesView([{ type: 'cards', name: 'K' }], info), null, 'no table to show them in');
  assert.equal(sourcesView([{ type: 'table', name: 'T', order: ['field'] }], info), null, 'no table that shows the value');
  assert.equal(sourcesView([], info), null);
  assert.equal(sourcesView(views, null), null);
  const general = precedenceOf({ id: 'd', properties: { x: {}, y: {} }, rows: [{ id: '1', x: 1 }] }, { formulas: { n: '[x, y].filter(!value.isEmpty())[0]' } });
  assert.equal(sourcesView([{ type: 'table', name: 'T', order: ['formula.n'] }], general), null, 'a file\'s formula reads columns the file already has');
});

test('setSourceValue: an edit lands on that source\'s statement; nothing beside it moves, and nothing is lost', () => {
  const cell = { unit: 'N', why: 'kept', sources: [{ source: 'a', value: 1, text: '1.0', note: 'p. 2', asOf: '2026-10-01' }, { source: 'b', value: 2 }] };
  const before = JSON.stringify(cell);
  const out = setSourceValue(cell, 'a', 5);
  assert.deepEqual(out, { unit: 'N', why: 'kept', sources: [{ source: 'a', value: 5, note: 'p. 2', asOf: '2026-10-01' }, { source: 'b', value: 2 }] }, 'its old `text` goes: it would contradict the value');
  assert.equal(JSON.stringify(cell), before, 'never mutates');
  assert.deepEqual(setSourceValue(cell, 'c', 9).sources, [...cell.sources, { source: 'c', value: 9 }], 'a source with no statement yet: a new one, last');
  assert.deepEqual(setSourceValue(cell, 'a', '').sources[0], { source: 'a', value: null, note: 'p. 2', asOf: '2026-10-01' }, 'cleared: it states nothing, and what it said about itself stays');
  assert.deepEqual(setSourceValue(cell, 'a', null).sources[0].value, null);
  assert.ok(isMultiSource(setSourceValue({ sources: [{ source: 'a', value: 1 }] }, 'a', null)), 'still a list, so its column stays');
});

test('setSourceValue on a plain cell: its own source is that cell; any other keeps it as a statement of its own', () => {
  const sources = { d: { name: 'Datasheet' } };
  const rich = { value: 1, text: '1.0', source: 'Datasheet', sourceUrl: 'https://example.com/d', note: 'n' };
  assert.deepEqual(setSourceValue(rich, 'd', 2, sources), { value: 2, source: 'Datasheet', sourceUrl: 'https://example.com/d', note: 'n' }, 'by its name');
  assert.deepEqual(setSourceValue({ value: 1, source: 'd' }, 'd', 2, sources), { value: 2, source: 'd' }, 'by its id');
  const both = setSourceValue(rich, 'bench', 7, sources);
  assert.deepEqual(both.sources, [{ value: 1, text: '1.0', source: 'd', sourceUrl: 'https://example.com/d', note: 'n' }, { source: 'bench', value: 7 }], 'the value that was there stays, under its source');
  const unnamed = setSourceValue({ value: 1, unit: 'N' }, 'bench', 7, sources);
  assert.equal(unnamed.sources.length, 2, 'a value with no source is not dropped either');
  assert.equal(unnamed.sources[0].value, 1);
  assert.equal(unnamed.sources[0].unit, 'N');
  assert.deepEqual(unnamed.sources[1], { source: 'bench', value: 7 });
  assert.equal(setSourceValue(3, 'bench', 7, sources).sources[0].value, 3, 'nor a bare number');
  assert.deepEqual(setSourceValue(null, 'bench', 7, sources), { sources: [{ source: 'bench', value: 7 }] }, 'an empty cell: the one statement');
  assert.deepEqual(setSourceValue(undefined, 'bench', 7, sources), { sources: [{ source: 'bench', value: 7 }] });
});

test('foldEdit: an edit of source columns becomes the stored property, whole, so a host and undo see the cell the file holds', () => {
  const info = precedenceOf(PART);
  const row = PART.rows[0];
  const out = foldEdit({ 'nominal@bench': 3.3, 'nominal@chat': 4, field: 'Peak' }, row, info);
  assert.deepEqual(Object.keys(out).sort(), ['field', 'nominal']);
  assert.equal(out.field, 'Peak', 'everything else as given');
  assert.equal(out.nominal.sources.find((e) => e.source === 'bench').value, 3.3);
  assert.equal(out.nominal.sources.find((e) => e.source === 'chat').value, 4, 'two columns of one cell in one edit');
  assert.equal(out.nominal.sources.find((e) => e.source === 'listing').text, '3.8');
  const set = { field: 'x' };
  assert.equal(foldEdit(set, row, info), set, 'no source column: the same object');
  assert.equal(foldEdit(set, row, null), set);
  assert.equal(info.columns.nominal.length, 4);
});

test('a file\'s columns: the checker knows the columns a list of sources unfolds to, and what a formula may be', () => {
  const props = datasetProperties(new URL('../browser/fixtures/source-precedence/part.json', import.meta.url).pathname);
  for (const id of ['nominal@bench', 'nominal@chat', 'nominal@source', 'nominal@*']) assert.ok(props.has(id), id);
  const words = (text) => JSON.stringify(checkText(text, { properties: props }));
  const view = (order, extra = '') => `views:\n  - type: table\n    name: V\n    order: ${order}\n${extra}`;
  assert.ok(!/error/.test(words(view('[field, nominal, nominal@bench, nominal@source, nominal@*]'))), words(view('[field, nominal@bench]')));
  assert.ok(!/error/.test(words(view('[field, formula.nominal]'))), 'a value with several sources is a formula with no text: formula.<it> is its name');
  assert.match(words(view('[field, nominal@nope]')), /nominal@nope/);
  assert.ok(!/error/.test(words(view('[field, nominal]', '    sourceColumn: false\n'))), 'a view key');
  assert.match(words(`formulas:\n  n: 'price * 2'\n${view('[field]')}`), /warning.*Obsidian|Obsidian.*warning/, 'a formula data-ui does not run is said at its line');
  assert.ok(!/Obsidian/.test(words(`formulas:\n  n: '[a, b].filter(!value.isEmpty())[0]'\n${view('[field]')}`)));
  const kpi = `formulas:\n  n: '[a, b].filter(!value.isEmpty())[0]'\nviews:\n  - type: kpi\n    name: K\n    kpi:\n      value: { property: formula.n }\n`;
  assert.match(JSON.stringify(checkText(kpi, {})), /error.*producer|producer.*error/, 'a headline KPI stays the producer\'s');
});

test('the popover reads a formula over plain columns as it reads a list of sources', () => {
  const dataset = { id: 'd', properties: { name: {}, x: { type: 'number', label: 'Exes' }, y: { type: 'number', label: 'Whys' } }, rows: [{ id: 'r', name: 'R', x: 3, y: 4 }] };
  const base = { formulas: { n: '[x, y].filter(!value.isEmpty())[0]' } };
  const info = precedenceOf(dataset, base);
  const cell = shown(dataset, base).rows[0]['formula.n'];
  const { rows, shown: on } = sourceRows(cell, { order: info.default, ov: {} }, 'r', info);
  assert.equal(on, 'x');
  assert.deepEqual(rows.map((r) => [r.name, r.state]), [['Exes', 'shown'], ['Whys', 'differs']]);
});
