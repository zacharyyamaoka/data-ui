// A rich cell's `text` (docs/CONTRACT.md §22): a display string the producer wrote, shown exactly as written wherever the
// cell is drawn, while sorting, filtering, grouping, summaries, the rail, Copy and the hover title keep `value`.
// RobotParts stores a range as a list ({value: [15, 60], text: "15 to 60"}) and redrew those cells after render.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { valueHtml, valueText, cellText } from '../../packages/core/src/format.js';
import { rowModel } from '../../packages/core/src/rowmodel.js';
import { summarize, cellValue } from '../../packages/core/src/grammar.js';
import { toCsv } from '../../packages/core/src/toolbar/csv.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const RANGE = { value: [15, 60], text: '15 to 60' };
const attrOf = (html) => {
  const m = /data-provenance="([^"]*)"/.exec(html);
  return m ? JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')) : null;
};

// the text of a cell's visible part: the markup stripped of tags, entities left alone
const visible = (html) => html.replace(/<[^>]*>/g, '');

test('valueText of a rich cell with text is the text, exactly as written; the same list without text still joins its items', () => {
  assert.equal(valueText(RANGE, { type: 'list' }), '15 to 60');
  assert.equal(valueText({ value: [15, 60] }, { type: 'list' }), '15, 60');
  assert.equal(valueText([15, 60], { type: 'list' }), '15, 60');
  assert.equal(valueText({ value: 15, text: '  fifteen  ' }, {}), '  fifteen  ', 'never trimmed or normalised');
  assert.equal(valueText({ value: 1234.5, text: 'about 1.2k' }, { decimals: 0 }), 'about 1.2k', 'never rounded or reformatted');
});

test('a value that is not a rich cell is never touched: group keys, filter values and plain cells', () => {
  assert.equal(valueText(15, {}), '15');
  assert.equal(valueText('15 to 60', {}), '15 to 60');
  assert.equal(valueText(['a', 'b'], { type: 'list' }), 'a, b');
  assert.equal(valueText({ value: 15 }, {}), '15');
  assert.equal(valueText({ text: 'no value key' }, {}), '[object Object]', 'an object with no value key is not a rich cell');
});

test('cellText is the string, or null: a non-string text is refused, and so is an empty one', () => {
  assert.equal(cellText(RANGE), '15 to 60');
  for (const bad of [5, true, ['15 to 60'], { a: 1 }, null, undefined, '']) {
    assert.equal(cellText({ value: [15, 60], text: bad }), null, JSON.stringify(bad));
    assert.equal(valueText({ value: [15, 60], text: bad }, { type: 'list' }), '15, 60', `valueText ignores ${JSON.stringify(bad)}`);
    assert.equal(visible(valueHtml({ value: [15, 60], text: bad }, { type: 'list' })), '15, 60', `valueHtml ignores ${JSON.stringify(bad)}`);
  }
  for (const plain of [15, '15', [15, 60], null, undefined, { value: 1 }]) assert.equal(cellText(plain), null);
});

test('valueHtml draws the text; the hover title keeps the stored value on its first line', () => {
  const html = valueHtml(RANGE, { type: 'list' });
  assert.equal(visible(html), '15 to 60');
  assert.match(html, /<span class="dv-value" title="15, 60"/);
  const plain = valueHtml({ value: [15, 60] }, { type: 'list' });
  assert.equal(visible(plain), '15, 60');
});

test('the text is escaped, never normalised: markup stays text, spaces and case stay as written', () => {
  const html = valueHtml({ value: 1, text: '<b>1</b> & "2"  ' }, {});
  assert.doesNotMatch(html, /<b>/);
  assert.match(html, /&lt;b&gt;1&lt;\/b&gt; &amp; &quot;2&quot;  </);
});

test('the unit still follows the text; a range, a basis mark and the unit column are unchanged', () => {
  const html = valueHtml({ value: [15, 60], text: '15 to 60', unit: 'mm', basis: 'datasheet' }, { type: 'list' });
  assert.match(html, /15 to 60 <span class="dv-u">mm<\/span>/);
  assert.match(html, /dv-basis-datasheet/);
  assert.match(html, /title="15, 60 mm\ndatasheet/);
});

test('an empty value stays "—" with its reason: text decorates a value, it never makes one', () => {
  const html = valueHtml({ value: null, text: 'n/a', why: 'not measured' }, {});
  assert.match(html, /class="dv-none" title="not measured">—</);
  assert.equal(valueText({ value: null, text: 'n/a' }, {}), '');
});

test('data-provenance keeps value as the stored value and adds text; no text, no key', () => {
  const p = attrOf(valueHtml({ ...RANGE, source: 'datasheet p3' }, { type: 'list' }));
  assert.deepEqual(p, { value: '15, 60', text: '15 to 60', source: 'datasheet p3' });
  assert.deepEqual(attrOf(valueHtml({ value: [15, 60], source: 'datasheet p3' }, { type: 'list' })), { value: '15, 60', source: 'datasheet p3' });
  assert.equal(attrOf(valueHtml(RANGE, { type: 'list' })), null, 'text alone is not a provenance trigger');
});

// ---- what keeps using the value --------------------------------------------------------------------------------------

const ROWS = [
  { id: 'a', power: { value: 100, text: 'one hundred' }, range: { value: [100, 200], text: '100 to 200' }, kind: { value: 'x', text: 'Ex' } },
  { id: 'b', power: { value: 3, text: 'three' }, range: { value: [5, 20], text: '5 to 20' }, kind: { value: 'x', text: 'Ex' } },
  { id: 'c', power: { value: 20, text: 'twenty' }, range: { value: [15, 60], text: '15 to 60' }, kind: { value: 'y', text: 'Why' } },
];
const PROPS = { power: { type: 'number' }, range: { type: 'list' }, kind: { type: 'text' } };
const model = (view) => rowModel(normalizeDataset({ properties: PROPS, rows: ROWS }), {}, { type: 'table', name: 't', ...view });
const ids = (m) => m.rows.map((r) => r.id);

test('sorting orders by value, not by text (text order would be a, c, b ... "one hundred" < "three" < "twenty")', () => {
  assert.deepEqual(ids(model({ sort: [{ property: 'power', direction: 'ASC' }] })), ['b', 'c', 'a']);
  assert.deepEqual(ids(model({ sort: [{ property: 'power', direction: 'DESC' }] })), ['a', 'c', 'b']);
});

test('a list sorts as it does without text', () => {
  const plain = rowModel(normalizeDataset({ properties: PROPS, rows: ROWS.map((r) => ({ ...r, range: cellValue(r.range) })) }), {}, { type: 'table', name: 't', sort: [{ property: 'range', direction: 'ASC' }] });
  assert.deepEqual(ids(model({ sort: [{ property: 'range', direction: 'ASC' }] })), ids(plain));
});

test('a filter matches the value, not the text', () => {
  assert.deepEqual(ids(model({ filters: 'power >= 20' })).sort(), ['a', 'c']);
  assert.deepEqual(ids(model({ filters: 'power == 3' })), ['b']);
  assert.deepEqual(ids(model({ filters: 'kind == "x"' })).sort(), ['a', 'b']);
  assert.deepEqual(ids(model({ filters: 'kind == "Ex"' })), [], 'the text is not a value');
});

test('a group is its value; summaries read values', () => {
  const m = model({ groupBy: { property: 'kind' } });
  assert.deepEqual(m.groups.map((g) => g.key).sort(), ['x', 'y']);
  assert.equal(summarize(ROWS.map((r) => r.power), 'Sum'), 123);
  assert.equal(summarize(ROWS.map((r) => r.power), 'Max'), 100);
});

test('Copy (the CSV export) writes the value: a list joined, a number as stored', () => {
  const m = model({});
  const csv = toCsv(m.rows, m.columns, ['power', 'range']);
  assert.match(csv, /\r\n100,"100, 200"\r\n/);
  assert.doesNotMatch(csv, /to 200|hundred/);
});
