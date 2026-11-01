// The Nominal source column on data whose values have one source each (docs/CONTRACT.md §36, its amendment "the
// source column on one-source data"): a dataset may declare `sourceColumn: true` (draw it, beside the first column
// whose values name a source) or `false` (never). Undeclared, it follows a value with several sources only, as before,
// so no other table changes. precedence.js sourcedProperties() says which columns name a source and sourceColumnOf()
// reads the declaration; both are measured here against an oracle over the fixtures' own JSON.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { sourcedProperties, sourceColumnOf } from '../../packages/core/src/precedence.js';

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), 'utf8'));
const SERVO = read('../browser/fixtures/source-column/servo.json');
const PART = read('../browser/fixtures/source-precedence/part.json');
const PARTS = read('../browser/fixtures/source-popover/parts.json');

// ---------------------------------------------------------------- the oracle, from the JSON alone
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const filled = (v) => v !== null && v !== undefined && v !== '';
/** A cell names a source: a list of sources (several, CONTRACT §36), or a §22 rich cell with a source, its URL or its page. */
const names = (c) => isObj(c) && ((Array.isArray(c.sources) && c.sources.length > 0) || filled(c.source) || filled(c.sourceUrl) || filled(c.sourcePage));
function sourced(data) {
  const declared = Object.keys(data.properties || {});
  const met = [];
  for (const r of data.rows) for (const [k, v] of Object.entries(r)) if (names(v) && !met.includes(k)) met.push(k);
  return [...declared.filter((k) => met.includes(k)), ...met.filter((k) => !declared.includes(k))];
}

test('sourcedProperties: the columns whose values name a source, in the properties\' order, then any other as first met', () => {
  for (const [name, data] of [['servo.json (one source per value)', SERVO], ['part.json (several)', PART], ['parts.json (two such columns)', PARTS]]) {
    assert.deepEqual(sourcedProperties(data), sourced(data), name);
  }
  assert.deepEqual(sourcedProperties(SERVO), ['nominal'], 'the servo: only its Nominal names sources (Section and Unit are plain)');
  const mixed = {
    properties: { a: { type: 'number' }, b: { type: 'number' }, c: { type: 'number' }, d: { type: 'number' } },
    rows: [
      { id: '1', a: { value: 1, sourceUrl: 'https://example.com/a' }, b: { value: 2 }, c: 3, d: { value: 4, source: '' }, e: { value: 5, source: 'memo' } },
      { id: '2', b: { value: null, why: 'not stated', sourcePage: 'notes/b.md' }, c: { value: 3, sources: [{ source: 'x', value: 3 }] } },
    ],
  };
  assert.deepEqual(sourcedProperties(mixed), ['a', 'b', 'c', 'e'], 'a URL or a page names a source; a list of sources does; an empty source does not; a column the properties lack comes last');
  assert.deepEqual(sourcedProperties({ properties: { a: {} }, rows: [{ id: '1', a: 1 }, { id: '2', a: { value: 2, basis: 'measured' } }] }), [], 'no cell names a source: none');
  assert.deepEqual(sourcedProperties(null), []);
  assert.deepEqual(sourcedProperties({ rows: [] }), []);
});

test('sourceColumnOf: undeclared is null (as before); false is off; true is on, with the columns whose values name a source', () => {
  assert.deepEqual(sourceColumnOf(SERVO), { on: true, properties: ['nominal'] });
  assert.equal(sourceColumnOf(PART), null, 'part.json declares nothing: its column follows its values with several sources, as before');
  assert.equal(sourceColumnOf({ ...SERVO, sourceColumn: undefined }), null);
  assert.deepEqual(sourceColumnOf({ ...PART, sourceColumn: false }), { on: false, properties: [] });
  assert.deepEqual(sourceColumnOf({ ...PART, sourceColumn: true }), { on: true, properties: ['nominal'] });
  assert.deepEqual(sourceColumnOf({ sourceColumn: true, properties: { field: {}, note: {} }, rows: [{ id: '1', field: 'A', note: 'x' }] }), { on: true, properties: [] }, 'declared with no source anywhere: on, beside no column in particular');
  for (const v of ['true', 1, 'yes', null, {}]) assert.equal(sourceColumnOf({ ...SERVO, sourceColumn: v }), null, `only a boolean declares it (${JSON.stringify(v)})`);
  assert.equal(sourceColumnOf(null), null);
  const before = JSON.stringify(SERVO);
  sourceColumnOf(SERVO);
  sourcedProperties(SERVO);
  assert.equal(JSON.stringify(SERVO), before, 'reading the declaration changes nothing');
});
