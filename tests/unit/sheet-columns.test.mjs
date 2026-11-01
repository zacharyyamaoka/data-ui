// CONTRACT §40: a column's kind and what it asks of the data: a retype changes the definition and nothing stored; a new key comes from
// the name; a deleted column's view keys come back with it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { KINDS, kindOf, definitionFor, propertyKey, fits, dropFromView, restoreToView } from '../../packages/core/src/sheet.js';

test('the seven kinds, in the menu\'s order', () => {
  assert.deepEqual(KINDS, ['text', 'number', 'date', 'select', 'checkbox', 'link', 'media']);
});

test('kindOf reads a property as the menu names it', () => {
  assert.equal(kindOf({ type: 'text' }), 'text');
  assert.equal(kindOf({}), 'text');
  assert.equal(kindOf({ type: 'number' }), 'number');
  assert.equal(kindOf({ type: 'date' }), 'date');
  assert.equal(kindOf({ type: 'boolean' }), 'checkbox');
  assert.equal(kindOf({ type: 'text', display: 'link' }), 'link');
  assert.equal(kindOf({ type: 'text', display: 'media' }), 'media');
  assert.equal(kindOf({ type: 'text', display: 'badge' }), 'select');
  assert.equal(kindOf({ type: 'text', constraints: { enum: ['a'] } }), 'select');
  assert.equal(kindOf({ type: 'text', labels: { a: 'A' } }), 'select');
  assert.equal(kindOf({ type: 'list' }), 'list', 'a type the menu has no word for reads as itself');
});

test('definitionFor: a new property of each kind', () => {
  assert.deepEqual(definitionFor('text'), { type: 'text' });
  assert.deepEqual(definitionFor('number'), { type: 'number' });
  assert.deepEqual(definitionFor('date'), { type: 'date' });
  assert.deepEqual(definitionFor('select'), { type: 'text', display: 'badge' });
  assert.deepEqual(definitionFor('checkbox'), { type: 'boolean', display: 'checkbox' });
  assert.deepEqual(definitionFor('link'), { type: 'text', display: 'link' });
  assert.deepEqual(definitionFor('media'), { type: 'text', display: 'media' });
  assert.throws(() => definitionFor('nope'));
});

test('definitionFor: a retype keeps the label and a range; what belonged to the old kind goes', () => {
  const old = { type: 'text', label: 'Status', display: 'badge', labels: { a: 'A' }, colors: { a: 2 }, cycle: true, constraints: { enum: ['a'], minimum: 1 }, note: 'kept' };
  const next = definitionFor('number', old);
  assert.equal(next.type, 'number');
  assert.equal(next.label, 'Status');
  assert.equal(next.note, 'kept');
  assert.deepEqual(next.constraints, { minimum: 1 });
  for (const k of ['display', 'labels', 'colors', 'cycle']) assert.ok(!(k in next), k);
});

test('definitionFor: away from number a column draws its values as written', () => {
  assert.equal(definitionFor('text', { type: 'number' }).asWritten, true);
  assert.equal(definitionFor('date', { type: 'text' }).asWritten, true);
  assert.ok(!('asWritten' in definitionFor('number', { type: 'text' })));
});

test('definitionFor: the same kind is the same definition; the input is not touched', () => {
  const old = { type: 'text', display: 'badge', constraints: { enum: ['a'] } };
  const seen = JSON.stringify(old);
  assert.deepEqual(definitionFor('select', old), old);
  definitionFor('number', old);
  assert.equal(JSON.stringify(old), seen);
});

test('propertyKey: from the name, in lower case with underscores', () => {
  assert.equal(propertyKey('Due date', []), 'due_date');
  assert.equal(propertyKey('  Ünit Cost (USD) ', []), 'unit_cost_usd');
});

test('propertyKey: unique; never id; never a bare number; something for a name of symbols', () => {
  assert.equal(propertyKey('Owner', ['owner']), 'owner_2');
  assert.equal(propertyKey('Owner', ['owner', 'owner_2']), 'owner_3');
  assert.equal(propertyKey('ID', []), 'id_2');
  assert.equal(propertyKey('2031 plan', []), 'p_2031_plan');
  assert.equal(propertyKey('???', []), 'property');
});

test('fits: whether a value can sit in the column\'s own control', () => {
  assert.equal(fits({ type: 'number' }, 3), true);
  assert.equal(fits({ type: 'number' }, 'soon'), false);
  assert.equal(fits({ type: 'number' }, null), true);
  assert.equal(fits({ type: 'date' }, '2031-03-02'), true);
  assert.equal(fits({ type: 'date' }, 'soon'), false);
  assert.equal(fits({ type: 'date' }, 12), false);
  assert.equal(fits({ type: 'boolean' }, true), true);
  assert.equal(fits({ type: 'boolean' }, 'yes'), false);
  assert.equal(fits({ type: 'text' }, 12), true);
});

test('dropFromView takes a property out of every key that names it; restoreToView puts each back where it was', () => {
  const view = () => ({ name: 'V', order: ['a', 'x', 'b'], sort: [{ property: 'a', direction: 'ASC' }, { property: 'x', direction: 'DESC' }, { property: 'b', direction: 'ASC' }], groupBy: { property: 'x' }, subGroupBy: { property: 'b' }, columnSize: { a: 90, x: 120 }, display: { x: 'bar' }, summaries: { x: 'Sum', a: 'Max' } });
  const v = view();
  const saved = dropFromView(v, 'x');
  assert.deepEqual(v.order, ['a', 'b']);
  assert.deepEqual(v.sort.map((s) => s.property), ['a', 'b']);
  assert.ok(!('groupBy' in v));
  assert.deepEqual(v.subGroupBy, { property: 'b' });
  assert.deepEqual(v.columnSize, { a: 90 });
  assert.ok(!('display' in v), 'an emptied map goes');
  assert.deepEqual(v.summaries, { a: 'Max' });
  restoreToView(v, 'x', JSON.parse(JSON.stringify(saved)));
  assert.deepEqual(v, view());
});

test('a view that does not name the property is left alone, both ways', () => {
  const v = { name: 'V', order: ['a'] };
  restoreToView(v, 'x', dropFromView(v, 'x'));
  assert.deepEqual(v, { name: 'V', order: ['a'] });
});

test('restoreToView survives a view changed since: a place past the end is the end', () => {
  const v = { order: ['a', 'b', 'x'] };
  const saved = dropFromView(v, 'x');
  v.order = ['a'];
  restoreToView(v, 'x', saved);
  assert.deepEqual(v.order, ['a', 'x']);
});
