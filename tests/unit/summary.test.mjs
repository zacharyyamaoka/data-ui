// The summary card's cells (packages/views/summary/src/model.js), the date display (core format.js shortDate) and the
// avatar's initials (packages/views/table/src/columns.js). docs/CONTRACT.md §43.
import test from 'node:test';
import assert from 'node:assert/strict';
import { cellOf, cellSpecs, valueOf, isoToday } from '../../packages/views/summary/src/model.js';
import { compileFilters, summarize, summaryName, cellValue, timeBucket, nextBucket, bucketLabel } from '../../packages/core/src/grammar.js';
import { shortDate } from '../../packages/core/src/format.js';
import { initials } from '../../packages/views/table/src/columns.js';

const H = { compileFilters, summarize, summaryName, cellValue, timeBucket, nextBucket, bucketLabel };
const NOW = new Date(2026, 9, 28, 15, 0); // 28 Oct 2026, the reader's afternoon
const columns = { kind: { type: 'text' }, due: { type: 'date' }, value: { type: 'number', unitText: 'CAD' }, created: { type: 'date' } };
const rows = [
  { id: 'a', kind: 'Customer', due: '2026-11-05', value: 20, created: '2026-08-02' },
  { id: 'b', kind: 'Prospect', due: '2026-10-30', value: { value: 5, basis: 'estimate' }, created: '2026-09-10' },
  { id: 'c', kind: 'Prospect', due: '2026-10-01', value: null, created: '2026-09-21' },
  { id: 'd', kind: 'Competitor', due: null, value: 7, created: '2026-10-04' },
];

test('a cell counts rows by default, after its filters', () => {
  assert.equal(cellOf(rows, columns, { label: 'All' }, H, NOW).value, 4);
  const c = cellOf(rows, columns, { label: 'Prospects', filters: 'kind == "Prospect"' }, H, NOW);
  assert.deepEqual([c.kind, c.value, c.rows.map((r) => r.id)], ['number', 2, ['b', 'c']]);
});

test('when: a period against the reader\'s today, past and upcoming', () => {
  const v = (is) => cellOf(rows, columns, { label: 'x', when: { property: 'due', is } }, H, NOW).rows.map((r) => r.id);
  assert.deepEqual(v('this-month'), ['b', 'c']);
  assert.deepEqual(v('upcoming'), ['a', 'b']);
  assert.deepEqual(v('past'), ['c']);
  assert.deepEqual(v('today'), []);
  // a row due today is upcoming and today's, never past
  const t = [...rows, { id: 'e', due: '2026-10-28' }];
  const w = (is) => cellOf(t, columns, { label: 'x', when: { property: 'due', is } }, H, NOW).rows.map((r) => r.id);
  assert.deepEqual([w('today'), w('past'), w('upcoming')], [['e'], ['c'], ['a', 'b', 'e']]);
  assert.deepEqual(v('this-year'), ['a', 'b', 'c']);
  assert.match(cellOf(rows, columns, { label: 'x', when: { property: 'due', is: 'soon' } }, H, NOW).error, /^when:/);
});

test('value: Earliest / Latest of a date, a Bases summary of a number (rich cells read as their value)', () => {
  const next = cellOf(rows, columns, { label: 'Next due', value: { property: 'due', summary: 'Earliest' }, when: { property: 'due', is: 'upcoming' } }, H, NOW);
  assert.deepEqual([next.kind, next.value], ['date', '2026-10-30']);
  assert.deepEqual([valueOf(rows, columns, { property: 'due', summary: 'Latest' }, H).value], ['2026-11-05']);
  const sum = valueOf(rows, columns, { property: 'value', summary: 'Sum' }, H);
  assert.deepEqual([sum.kind, sum.value, sum.unit], ['number', 32, 'CAD']);
  assert.equal(valueOf(rows, columns, { property: 'value', summary: 'median' }, H).value, 7);
  assert.match(valueOf(rows, columns, { property: 'value', summary: 'Mode' }, H).error, /not a summary/);
  assert.match(valueOf(rows, columns, { property: 'nope' }, H).error, /no property "nope"/);
});

test('no rows: a count is 0, a date summary has no value (drawn "—", never 0)', () => {
  assert.equal(cellOf([], columns, { label: 'Won' }, H, NOW).value, 0);
  assert.equal(cellOf([], columns, { label: 'Next', value: { property: 'due', summary: 'Earliest' } }, H, NOW).value, null);
});

test('spark: one value per bucket, every bucket between the first and the last; a delta only with two or more', () => {
  const c = cellOf(rows, columns, { label: 'New', spark: { x: 'created', grain: 'month' } }, H, NOW);
  assert.deepEqual(c.series.map((p) => [p.x, p.y]), [['2026-08', 1], ['2026-09', 2], ['2026-10', 1]]);
  assert.deepEqual(c.delta, { value: -1, against: 'Sep 2026', at: 'Oct 2026' });
  // an empty month in a count is a real 0
  const holes = cellOf([rows[0], rows[3]], columns, { label: 'New', spark: { x: 'created', grain: 'month' } }, H, NOW);
  assert.deepEqual(holes.series.map((p) => p.y), [1, 0, 1]);
  const one = cellOf(rows.slice(3), columns, { label: 'New', spark: { x: 'created', grain: 'month' } }, H, NOW);
  assert.equal(one.series, undefined, 'one bucket is not a series: no line is drawn');
  // a summary other than a count leaves an empty bucket empty (the line lifts), not 0
  const gap = cellOf([rows[0], rows[3]], columns, { label: 'Value', value: { property: 'value', summary: 'Sum' }, spark: { x: 'created', grain: 'month' } }, H, NOW);
  assert.deepEqual(gap.series.map((p) => p.y), [20, null, 7]);
});

test('bad cells say why and never throw', () => {
  assert.match(cellOf(rows, columns, { label: 'x', filters: 'kind ==' }, H, NOW).error, /^filters:/);
  assert.deepEqual(cellSpecs({ cells: ['oops'] })[0].error, 'a cell is {label, value?, filters?, when?}');
  assert.deepEqual(cellSpecs(null), []);
  assert.equal(isoToday(NOW), '2026-10-28');
});

test('shortDate: Today / Yesterday / Tomorrow, "Apr 10" this year, "Jul 25, 2023" in another; a date-only text is that calendar day', () => {
  assert.equal(shortDate('2026-10-28', NOW), 'Today');
  assert.equal(shortDate('2026-10-27', NOW), 'Yesterday');
  assert.equal(shortDate('2026-10-29', NOW), 'Tomorrow');
  assert.equal(shortDate('2026-04-10', NOW), 'Apr 10');
  assert.equal(shortDate('2023-07-25', NOW), 'Jul 25, 2023');
  assert.equal(shortDate('2027-01-01', NOW), 'Jan 1, 2027');
  assert.equal(shortDate({ value: '2026-11-05' }, NOW), 'Nov 5');
  assert.equal(shortDate('not a date', NOW), null);
  assert.equal(shortDate(null, NOW), null);
});

test('initials: the first letters of the first two words, as written', () => {
  assert.deepEqual(['Acme Medical Waste', 'City of Larkspur', 'Stericycle', 'GFL Environmental', 'x', '', 'Ümlaut-werk'].map(initials), ['AM', 'CO', 'ST', 'GE', 'X', '', 'ÜW']);
});
