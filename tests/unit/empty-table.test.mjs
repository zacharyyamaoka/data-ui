// What a table with no column to draw says (packages/views/table/src/columns.js noColumnsText). RobotParts' regression:
// lane/p0-blockers 2ea9d70 ("a table with no column says so") read the rows to decide the columns were missing, so a
// table with zero rows said "No columns to show" though its columns exist. The rule: that message only when the data
// has rows or declares its columns, and none of the view's columns is among them; otherwise the ordinary empty state
// ("No rows match this view."), which is the table saying nothing about columns (null from noColumnsText).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { leafColumns, noColumnsText } from '../../packages/views/table/src/columns.js';
import { rowModel } from '../../packages/core/src/rowmodel.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const ORDER = ['seller', 'variant', 'price'];
const FIELDS = [{ name: 'seller', type: 'string' }, { name: 'variant', type: 'string' }, { name: 'price', type: 'number' }];
const OFFERS = [{ seller: 'A', variant: 'x', price: 5 }, { seller: 'B', variant: 'y', price: 9 }];

// what the table is handed for a dataset and a view, as TableView.update() reads it, and what it says with no cell to draw
function says(input, view, base = {}) {
  const dataset = normalizeDataset(input);
  const model = rowModel(dataset, base, view);
  const props = model.columns;
  const order = (view.order || []).filter((id) => props[id]);
  const leaves = leafColumns(order, props, view, model.rows);
  return { text: noColumnsText(view, props, leaves, model.total), leaves: leaves.length, rows: model.rows.length };
}

test('zero rows, columns declared by properties: the ordinary empty state, not "No columns"', () => {
  const r = says({ properties: { seller: { type: 'text' }, variant: { type: 'text' }, price: { type: 'number' } }, rows: [] }, { type: 'table', order: ORDER });
  assert.deepEqual([r.rows, r.leaves, r.text], [0, 3, null]);
});

test('zero rows, columns declared by a schema: the ordinary empty state', () => {
  const r = says({ schema: { fields: FIELDS }, rows: [] }, { type: 'table', order: ORDER });
  assert.deepEqual([r.rows, r.leaves, r.text], [0, 3, null]);
});

test('zero rows and nothing declared (a bare []): the ordinary empty state, since nothing says a column is missing', () => {
  const r = says([], { type: 'table', order: ORDER }, { properties: { seller: { displayName: 'Seller' } } });
  assert.deepEqual([r.rows, r.text], [0, null]);
});

test('rows that a filter leaves zero of: the ordinary empty state', () => {
  const r = says({ schema: { fields: FIELDS }, rows: OFFERS }, { type: 'table', order: ORDER, filters: 'price > 100' });
  assert.deepEqual([r.rows, r.leaves, r.text], [0, 3, null]);
  const bare = says(OFFERS, { type: 'table', order: ORDER, filters: 'price > 100' });
  assert.deepEqual([bare.rows, bare.leaves, bare.text], [0, 3, null]);
});

test('rows, none of the view\'s columns among them: says which columns it lacks', () => {
  const r = says(OFFERS, { type: 'table', order: ['servo', 'ff_fraction'] });
  assert.equal(r.leaves, 0);
  assert.equal(r.text, "No columns to show: this view's columns (servo, ff_fraction) are not in its data.");
});

test('zero rows but columns declared, none the view\'s: still says which columns it lacks', () => {
  const r = says({ schema: { fields: FIELDS }, rows: [] }, { type: 'table', order: ['servo'] });
  assert.equal(r.text, "No columns to show: this view's columns (servo) are not in its data.");
});

test('a table with columns to draw never says it has none', () => {
  const r = says(OFFERS, { type: 'table', order: ['seller', 'servo'] });
  assert.deepEqual([r.leaves, r.text], [1, null]);
});

test('a view that hides every property of data that has rows says so', () => {
  const r = says({ properties: { seller: { type: 'text', hidden: true } }, rows: OFFERS }, { type: 'table' });
  assert.equal(r.leaves, 0);
  assert.equal(r.text, 'No columns to show: this view hides every property of its data.');
});

test('the missing list stops at six names', () => {
  const order = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
  assert.equal(says(OFFERS, { type: 'table', order }).text, "No columns to show: this view's columns (a, b, c, d, e, f, … (2 more)) are not in its data.");
});
