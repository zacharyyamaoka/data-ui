// The inspector's property list (docs/CONTRACT.md, "the inspector: one property per row"): which properties a record shows and which
// wait behind "N more properties". Written before the code. Zach, 2026-10-31: "1 property per cell", "control over what property
// visibilty in the inspector or in the row".
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { inspectorProperties, moreLabel, visibilityOf } from '../../packages/core/src/inspector.js';
import { checkText } from '../../packages/core/src/check.js';

const col = (id, extra = {}) => [id, { id, label: id.toUpperCase(), type: 'text', ...extra }];
const columns = Object.fromEntries([col('name'), col('a'), col('b'), col('c'), col('d'), col('sys', { hidden: true })]);
const args = (view, row = { a: 1, b: 2, c: 3, d: 4 }, more = {}) => ({ view, columns, titleProperty: 'name', row, ...more });

test('the visible columns in their order, the title left out (it is the heading), then the hidden', () => {
  assert.deepEqual(inspectorProperties(args({ order: ['name', 'c', 'a'] })), { shown: ['c', 'a'], more: ['b', 'd'] });
});

test('no order: every column is visible, as the table draws them; a hidden: true property is no property at all', () => {
  assert.deepEqual(inspectorProperties(args({})), { shown: ['a', 'b', 'c', 'd'], more: [] });
});

test('an empty value in a visible column keeps its row: 1:1 with the columns', () => {
  assert.deepEqual(inspectorProperties(args({ order: ['a', 'b'] }, { a: null, b: '' })), { shown: ['a', 'b'], more: ['c', 'd'] });
});

test('record.visibility sets the inspector apart from the row, both ways', () => {
  const view = { order: ['a', 'b'], record: { visibility: { a: 'hide', c: 'show' } } };
  assert.deepEqual(inspectorProperties(args(view)), { shown: ['b', 'c'], more: ['a', 'd'] });
});

test('hideEmpty: the row shows only with a value; 0 and false are values; a reason it has none counts too', () => {
  const view = { order: ['a', 'b', 'c', 'd'], record: { visibility: { a: 'hideEmpty', b: 'hideEmpty', c: 'hideEmpty', d: 'hideEmpty' } } };
  assert.deepEqual(inspectorProperties(args(view, { a: null, b: 0, c: false, d: { value: null, why: 'not measured' } })), { shown: ['b', 'c', 'd'], more: ['a'] });
});

test('the columns a view really draws win over order: a column the view adds (a synthetic one) sits where it is drawn', () => {
  const drawn = [{ id: 'a', label: 'A' }, { id: '@extra', label: 'A extra' }, { id: 'b', label: 'B' }];
  assert.deepEqual(inspectorProperties(args({ order: ['a', 'b'] }, undefined, { drawn })), { shown: ['a', '@extra', 'b'], more: ['c', 'd'] });
});

test('a column the view adds can be hidden from the inspector like any other', () => {
  const drawn = [{ id: 'a', label: 'A' }, { id: '@extra', label: 'A extra' }];
  assert.deepEqual(inspectorProperties(args({ order: ['a'], record: { visibility: { '@extra': 'hide' } } }, undefined, { drawn })).more[0], '@extra');
});

test('a unit column another column points at is not a stray hidden property; a drawn one stays 1:1', () => {
  const cols = Object.fromEntries([col('name'), col('torque', { unit: 'unit' }), col('unit')]);
  assert.deepEqual(inspectorProperties({ view: { order: ['torque'] }, columns: cols, titleProperty: 'name', row: {} }), { shown: ['torque'], more: [] });
  assert.deepEqual(inspectorProperties({ view: { order: ['torque', 'unit'] }, columns: cols, titleProperty: 'name', row: {} }), { shown: ['torque', 'unit'], more: [] });
});

test('`exclude` keeps out what is drawn elsewhere (the detail list)', () => {
  assert.deepEqual(inspectorProperties(args({ order: ['a'] }, undefined, { exclude: ['b', 'c'] })), { shown: ['a'], more: ['d'] });
});

test('record.sections: the author\'s fields stay the sheet, in their sections; everything else is behind N more', () => {
  const view = { order: ['a'], record: { sections: [{ name: 'S', properties: ['b', 'a'] }] } };
  assert.deepEqual(inspectorProperties(args(view, undefined, { listed: ['b', 'a'] })), { shown: ['b', 'a'], more: ['c', 'd'] });
  const hid = { ...view, record: { ...view.record, visibility: { a: 'hide' } } };
  assert.deepEqual(inspectorProperties(args(hid, undefined, { listed: ['b', 'a'] })), { shown: ['b'], more: ['a', 'c', 'd'] });
});

test('a key with no such property does nothing; an unknown word reads as no setting', () => {
  assert.deepEqual(inspectorProperties(args({ order: ['a'], record: { visibility: { nope: 'show', b: 'sometimes' } } })), { shown: ['a'], more: ['b', 'c', 'd'] });
  assert.equal(visibilityOf({ record: { visibility: { b: 'sometimes' } } }, 'b'), null);
  assert.equal(visibilityOf({}, 'b'), null);
  assert.equal(visibilityOf({ record: { visibility: { b: 'hideEmpty' } } }, 'b'), 'hideEmpty');
});

test('moreLabel is Notion\'s wording, singular at 1', () => {
  assert.equal(moreLabel(1), '1 more property');
  assert.equal(moreLabel(3), '3 more properties');
  assert.equal(moreLabel(1, true), 'Hide 1 property');
  assert.equal(moreLabel(3, true), 'Hide 3 properties');
});

const check = (visibility) => checkText(`views:\n  - type: table\n    name: V\n    order: [name]\n    record:\n      visibility: ${JSON.stringify(visibility)}\n`, { properties: new Set(['name', 'a']) });

test('the checker takes the grammar, names a word that is not one, and names a property the data lacks', () => {
  const words = (r) => JSON.stringify(r);
  assert.ok(!/visibility/.test(words(check({ a: 'hide', name: 'show' }))), words(check({ a: 'hide' })));
  assert.match(words(check({ a: 'sometimes' })), /visibility/);
  assert.match(words(check({ nope: 'hide' })), /nope/);
  assert.ok(!/@source/.test(words(check({ '@source': 'hide' }))), 'a column the view adds is not a missing property');
});
