// Source precedence (docs/CONTRACT.md §36, docs/peps/0015-source-precedence.md): a cell whose value several sources
// state, `{sources: [{source, value, text?, …}, …]}` (each entry a §22 rich cell), reads as ONE nominal value: the row's
// override when its source states the cell, else the first source in the precedence order that does. The default order
// is the producer's evidence ladder. Truthful: nothing here edits, drops, merges, rounds or averages a stated value; an
// override only chooses which stated value is nominal.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isMultiSource, stated, conflict, differs, byPrecedence, pick, changed, held, ladderOrder, sourceIds,
  normalizeOrder, normalizePicks, resolveCell, resolveDataset, precedenceOf, encodeOrder, decodeOrder, encodePicks, decodePicks,
} from '../../packages/core/src/precedence.js';

const LADDER = [{ id: 'measured', label: 'Measured' }, { id: 'datasheet', label: "Maker's datasheet" }, { id: 'distributor', label: 'Distributor' },
  { id: 'listing', label: 'Listing' }, { id: 'chat', label: 'Chat' }];
// declared out of ladder order on purpose: the default order must come from the ladder, not from the declaration
const SOURCES = {
  chat: { name: 'Supplier chat', kind: 'Chat transcript', rung: 'chat', date: '2026-10-08', url: 'account:supplier-chat/7' },
  listing: { name: 'Shop listing', kind: "A seller's listing", rung: 'listing', date: '2026-10-02', url: 'https://example.com/shop' },
  datasheet: { name: 'Datasheet rev C', kind: "Maker's datasheet", rung: 'datasheet', date: '2026-09-14', url: 'https://example.com/ds.pdf' },
  bench: { name: 'Bench test', kind: 'Measured', rung: 'measured', date: '2026-10-20', url: 'https://example.com/bench', basis: 'measured' },
};
const cell = (...entries) => ({ unit: 'N·m', sources: entries.map(([source, value, extra]) => ({ source, value, ...extra })) });
const PEAK = cell(['chat', 3.8, { text: '3.8 Nm' }], ['listing', 3.8], ['datasheet', 3.8, { note: 'p. 2, peak' }], ['bench', 3.1, { asOf: '2026-10-21' }]);
const RATED = cell(['chat', 1.27], ['listing', 1.27], ['datasheet', 1.27]);
const ONE = cell(['datasheet', 0.14]);
const DEFAULT = ['bench', 'datasheet', 'listing', 'chat'];

test('isMultiSource: a rich cell with a non-empty sources list, nothing else', () => {
  assert.equal(isMultiSource(PEAK), true);
  assert.equal(isMultiSource(ONE), true);
  for (const c of [null, 3, 'x', [1, 2], { value: 3 }, { value: 3, source: 'a' }, { sources: [] }, { sources: 'a' }]) assert.equal(isMultiSource(c), false, JSON.stringify(c));
});

test('ladderOrder: the sources by their rung on the ladder, a tie in declaration order, a source off the ladder last', () => {
  assert.deepEqual(ladderOrder(Object.keys(SOURCES), SOURCES, LADDER), DEFAULT);
  const extra = { ...SOURCES, memo: { name: 'Memo' }, scan: { name: 'Scan', rung: 'datasheet' } };
  assert.deepEqual(ladderOrder(Object.keys(extra), extra, LADDER), ['bench', 'datasheet', 'scan', 'listing', 'chat', 'memo']);
  assert.deepEqual(ladderOrder(['b', 'a'], {}, null), ['b', 'a'], 'no ladder: declaration order');
});

test('sourceIds: the declared sources first, in declaration order, then any a cell names that is not declared', () => {
  const ds = { sources: SOURCES, rows: [{ id: 'r1', v: cell(['bench', 1], ['memo', 2]) }, { id: 'r2', v: cell(['scan', 3], ['chat', 4]) }] };
  assert.deepEqual(sourceIds(ds), ['chat', 'listing', 'datasheet', 'bench', 'memo', 'scan']);
});

test('stated and byPrecedence: the sources that state a value, in the order; a source the order lacks follows in the cell\'s order', () => {
  assert.deepEqual(stated(PEAK, DEFAULT), ['bench', 'datasheet', 'listing', 'chat']);
  assert.deepEqual(stated(PEAK, ['listing', 'bench']), ['listing', 'bench', 'chat', 'datasheet'], 'a stale order never hides a source');
  assert.equal(byPrecedence(PEAK, DEFAULT), 'bench');
  assert.equal(byPrecedence(RATED, DEFAULT), 'datasheet', 'the first source in the order that states it');
  assert.equal(byPrecedence(PEAK, []), 'chat', 'an empty order falls back to the cell\'s own order');
  const gaps = cell(['listing', null, { why: 'not on the listing' }], ['chat', ''], ['datasheet', 5]);
  assert.deepEqual(stated(gaps, DEFAULT), ['datasheet'], 'an entry with no value states nothing');
  assert.equal(byPrecedence(cell(['listing', null]), DEFAULT), null);
  const twice = cell(['chat', 1], ['chat', 2], ['bench', 9]);
  assert.deepEqual(stated(twice, ['chat']), ['chat', 'bench'], 'a source listed twice is one source (its first entry)');
});

test('conflict: the stated values disagree, by value and unit, whatever the order; text and empty entries are not a disagreement', () => {
  assert.equal(conflict(PEAK), true);
  assert.equal(conflict(RATED), false);
  assert.equal(conflict(ONE), false);
  assert.equal(conflict(cell(['chat', 3.8, { text: '3.80' }], ['listing', 3.8, { text: '3.8 N·m' }])), false, 'the same value written two ways agrees');
  assert.equal(conflict(cell(['chat', [24, 48], { text: '24 to 48' }], ['listing', [24, 48], { text: '24–48' }])), false, 'lists compare element by element');
  assert.equal(conflict(cell(['chat', [48, 24]], ['listing', [24, 48]])), true, 'a list is compared as stated, order included');
  assert.equal(conflict(cell(['chat', 3800, { unit: 'mN·m' }], ['listing', 3.8])), true, 'a different unit is a different statement (no conversion)');
  assert.equal(conflict(cell(['chat', 'IP54'], ['listing', 'ip54'])), true, 'text is compared as written');
  assert.equal(conflict(cell(['chat', 5], ['listing', null], ['bench', ''])), false, 'entries that state nothing never conflict');
  assert.equal(conflict(cell(['chat', 0], ['listing', -0])), false);
  assert.equal(differs(PEAK, 'bench', 'datasheet'), true);
  assert.equal(differs(PEAK, 'chat', 'listing'), false);
  assert.equal(differs(PEAK, 'chat', 'nobody'), false, 'a source that states nothing differs from nothing');
});

test('pick: the row\'s override when its source states the cell, else precedence; it reports which and what precedence alone picks', () => {
  assert.deepEqual(pick(PEAK, { order: DEFAULT, ov: {} }, 'peak'), { source: 'bench', via: 'precedence', prec: 'bench' });
  assert.deepEqual(pick(PEAK, { order: DEFAULT, ov: { peak: 'chat' } }, 'peak'), { source: 'chat', via: 'override', prec: 'bench' });
  assert.deepEqual(pick(PEAK, { order: DEFAULT, ov: { other: 'chat' } }, 'peak'), { source: 'bench', via: 'precedence', prec: 'bench' }, 'an override is one row\'s');
  assert.deepEqual(pick(RATED, { order: DEFAULT, ov: { rated: 'bench' } }, 'rated'), { source: 'datasheet', via: 'precedence', prec: 'datasheet' }, 'an override whose source states nothing here is ignored');
  assert.deepEqual(pick(cell(['listing', null]), { order: DEFAULT, ov: {} }, 'x'), { source: null, via: 'none', prec: null });
  assert.deepEqual(pick(PEAK, { order: ['listing', 'chat', 'datasheet', 'bench'] }, 'peak'), { source: 'listing', via: 'precedence', prec: 'listing' }, 'ov may be absent');
});

test('resolveCell: the picked entry exactly as stated, its source named, its provenance filled from the source only where the entry has none', () => {
  const view = { order: DEFAULT, ov: {} };
  const r = resolveCell(PEAK, view, 'peak', SOURCES);
  assert.equal(r.value, 3.1);
  assert.equal(r.source, 'Bench test', 'the source\'s name, as §22 writes it');
  assert.equal(r.asOf, '2026-10-21', 'the entry\'s own asOf wins over the source\'s date');
  assert.equal(r.sourceUrl, 'https://example.com/bench');
  assert.equal(r.basis, 'measured', 'the source\'s basis when the entry has none');
  assert.equal(r.unit, 'N·m', 'the cell\'s unit when the entry has none');
  assert.deepEqual(r.sources, PEAK.sources, 'every stated value rides along, untouched');
  const chat = resolveCell(PEAK, { order: DEFAULT, ov: { peak: 'chat' } }, 'peak', SOURCES);
  assert.equal(chat.value, 3.8);
  assert.equal(chat.text, '3.8 Nm', 'the text exactly as the source wrote it');
  assert.equal(chat.source, 'Supplier chat');
  assert.equal(chat.sourceUrl, 'account:supplier-chat/7', 'a private address is carried as written (it draws as a plain label)');
  assert.equal(chat.asOf, '2026-10-08');
  const ds = resolveCell(PEAK, { order: ['datasheet'], ov: {} }, 'peak', SOURCES);
  assert.equal(ds.note, 'p. 2, peak');
  const none = resolveCell(cell(['listing', null, { why: 'not on the listing' }]), view, 'x', SOURCES);
  assert.equal(none.value, null);
  assert.equal(typeof none.why, 'string');
  assert.ok(none.why.length > 0, 'no source states it: a reason, never 0');
  const undeclared = resolveCell(cell(['memo', 7]), view, 'x', {});
  assert.equal(undeclared.value, 7);
  assert.equal(undeclared.source, 'memo', 'an undeclared source is named by its id');
});

test('resolveCell never alters a stated value: the cell and its entries are not mutated, whatever the view', () => {
  const before = JSON.stringify(PEAK);
  for (const ov of [{}, { peak: 'chat' }, { peak: 'listing' }]) for (const order of [DEFAULT, [...DEFAULT].reverse(), []]) {
    const r = resolveCell(PEAK, { order, ov }, 'peak', SOURCES);
    const entry = PEAK.sources.find((e) => SOURCES[e.source] && SOURCES[e.source].name === r.source) || PEAK.sources.find((e) => e.source === r.source);
    assert.equal(r.value, entry.value, 'the nominal is one entry\'s value, exactly');
    if ('text' in entry) assert.equal(r.text, entry.text); else assert.equal('text' in r && r.text !== undefined, false, 'no text is invented');
  }
  assert.equal(JSON.stringify(PEAK), before);
});

const FIELDS = [{ id: 'peak', cell: PEAK }, { id: 'rated', cell: RATED }, { id: 'one', cell: ONE },
  { id: 'cur', cell: cell(['datasheet', 16, { text: '16.0' }], ['listing', 10], ['chat', 11]) }];

test('changed: the fields whose shown VALUE changes between two views (a switch between two agreeing sources is not a change)', () => {
  const a = { order: DEFAULT, ov: {} };
  const b = { order: ['chat', 'bench', 'datasheet', 'listing'], ov: {} };
  assert.deepEqual(changed(FIELDS, a, b).map((f) => f.id), ['peak', 'cur'], 'rated moves from the datasheet to the chat, which agree');
  assert.deepEqual(changed(FIELDS, a, a).map((f) => f.id), []);
  assert.deepEqual(changed(FIELDS, a, { order: DEFAULT, ov: { cur: 'listing' } }).map((f) => f.id), ['cur'], 'an override changes only its row');
});

test('held: the fields an override keeps while precedence alone would now show a different value', () => {
  const before = { order: DEFAULT, ov: { cur: 'datasheet' } };
  const after = { order: ['chat', 'bench', 'datasheet', 'listing'], ov: { cur: 'datasheet' } };
  assert.deepEqual(held(FIELDS, before, after).map((f) => f.id), ['cur']);
  assert.deepEqual(changed(FIELDS, before, after).map((f) => f.id), ['peak'], 'the held row did not change');
  assert.deepEqual(held(FIELDS, before, { ...after, ov: {} }).map((f) => f.id), [], 'no override, nothing held');
  assert.deepEqual(held(FIELDS, { order: DEFAULT, ov: { rated: 'chat' } }, { order: ['chat', 'datasheet'], ov: { rated: 'chat' } }).map((f) => f.id), [], 'precedence moved between agreeing sources: nothing to hold');
});

test('normalizeOrder and normalizePicks: a stored or linked state is read against this data; nothing unknown survives', () => {
  assert.deepEqual(normalizeOrder(['listing', 'ghost', 'listing', 'chat'], DEFAULT, DEFAULT), ['listing', 'chat', 'bench', 'datasheet'], 'unknown and repeated ids go; missing ones follow in the default order');
  assert.deepEqual(normalizeOrder(null, DEFAULT, DEFAULT), DEFAULT);
  const fields = FIELDS;
  assert.deepEqual(normalizePicks({ peak: 'chat', rated: 'bench', ghost: 'chat', cur: 'nobody' }, fields), { peak: 'chat' }, 'only a row that exists, picking a source that states it');
  assert.deepEqual(normalizePicks('junk', fields), {});
});

test('the URL forms: comma-joined ids, row:source pairs, every part URI-encoded both ways', () => {
  assert.equal(encodeOrder(['chat', 'bench']), 'chat,bench');
  assert.deepEqual(decodeOrder('chat,bench'), ['chat', 'bench']);
  const odd = ['a,b', 'c:d', 'é f', '%'];
  assert.deepEqual(decodeOrder(encodeOrder(odd)), odd);
  assert.equal(encodePicks({ rated_current: 'listing', peak: 'chat' }), 'rated_current:listing,peak:chat');
  assert.deepEqual(decodePicks('rated_current:listing,peak:chat'), { rated_current: 'listing', peak: 'chat' });
  const ov = { 'row,1': 'src:a', 'r é': 'x%y' };
  assert.deepEqual(decodePicks(encodePicks(ov)), ov);
  assert.deepEqual(decodeOrder(null), []);
  assert.deepEqual(decodePicks(''), {});
  assert.deepEqual(decodePicks('broken,also:ok'), { also: 'ok' }, 'a pair without a source is skipped');
});

test('precedenceOf: null for data with no multi-source cell; else the ids, the default order and the properties that carry sources', () => {
  assert.equal(precedenceOf({ properties: { a: {} }, rows: [{ id: 1, a: 1 }, { id: 2, a: { value: 2, source: 'x' } }] }), null);
  const ds = { sources: SOURCES, ladder: LADDER, properties: { field: {}, nominal: {} }, rows: [{ id: 'peak', field: 'Peak torque', nominal: PEAK }, { id: 'kt', field: 'Kt', nominal: ONE }] };
  const p = precedenceOf(ds);
  assert.deepEqual(p.ids, ['chat', 'listing', 'datasheet', 'bench']);
  assert.deepEqual(p.default, DEFAULT);
  assert.deepEqual(p.properties, ['nominal']);
  assert.equal(p.sources.bench.name, 'Bench test');
});

test('resolveDataset: rows with a multi-source cell become new rows with the nominal cell; every other row is the same object', () => {
  const plain = { id: 'kt2', field: 'Plain', nominal: { value: 1, source: 'somewhere' } };
  const ds = { id: 'part', sources: SOURCES, ladder: LADDER, properties: { field: {}, nominal: {} }, rows: [{ id: 'peak', field: 'Peak torque', nominal: PEAK }, plain] };
  const before = JSON.stringify(ds.rows);
  const out = resolveDataset(ds, { order: DEFAULT, ov: { peak: 'listing' } });
  assert.notEqual(out, ds);
  assert.equal(out.rows[1], plain, 'a row with no multi-source cell is the same object');
  assert.equal(out.rows[0].nominal.value, 3.8);
  assert.equal(out.rows[0].nominal.source, 'Shop listing');
  assert.equal(out.rows[0].field, 'Peak torque');
  assert.equal(JSON.stringify(ds.rows), before, 'the data as loaded is untouched');
  assert.equal(resolveDataset({ ...ds, rows: [plain] }, { order: DEFAULT, ov: {} }).rows[0], plain);
});
