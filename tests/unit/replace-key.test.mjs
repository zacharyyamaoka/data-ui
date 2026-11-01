// replaceKeyInText (docs/CONTRACT.md §37): one top-level key of a .base file's text changes; every other line stays as written
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseBase, replaceKeyInText, replaceViewInText } from '../../packages/core/src/base.js';

const FILE = `# a comment a person wrote
filters: type == "feedback"
properties:
  note: { displayName: Note }   # and this one
views:
  - type: table
    name: Table
  - type: table
    name: Open
`;

test('a new key goes above views:, the rest as written', () => {
  const out = replaceKeyInText(FILE, 'defaultView', 'Open');
  assert.equal(parseBase(out).defaultView, 'Open');
  assert.deepEqual(out.split('\n').filter((l) => !l.startsWith('defaultView')), FILE.split('\n'));
  assert.ok(out.indexOf('defaultView') < out.indexOf('views:'));
});

test('an existing key is replaced in place, and a removal takes only its lines', () => {
  const once = replaceKeyInText(FILE, 'defaultView', 'Open');
  const twice = replaceKeyInText(once, 'defaultView', 'Table');
  assert.equal(parseBase(twice).defaultView, 'Table');
  assert.equal(replaceKeyInText(twice, 'defaultView', null), FILE);
});

test('a value on several lines goes whole, and a block value takes its place', () => {
  const block = FILE.replace('filters: type == "feedback"', 'filters:\n  and:\n    - a == 1\n    - b == 2');
  const out = replaceKeyInText(block, 'filters', 'c == 3');
  assert.equal(parseBase(out).filters, 'c == 3');
  assert.deepEqual(parseBase(out).properties, parseBase(FILE).properties);
  assert.equal(parseBase(replaceKeyInText(FILE, 'filters', { and: ['a == 1', 'b == 2'] })).filters.and.length, 2);
});

test('with replaceViewInText, the comments stay', () => {
  const out = replaceViewInText(replaceKeyInText(FILE, 'defaultView', 'Open'), 1, { type: 'table', name: 'Open', columnSize: { note: 300 } });
  assert.ok(out.startsWith('# a comment a person wrote'));
  assert.ok(out.includes('# and this one'));
  assert.equal(parseBase(out).views[1].columnSize.note, 300);
});
