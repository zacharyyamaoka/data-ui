// The input contract (packages/core/src/data.js): every accepted form becomes the runtime shape.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeDataset, parseCSV, parseJSONL, inferProperties } from '../../packages/core/src/data.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('a Table Schema sidecar plus rows: types, units, labels and data-ui\'s six keys', () => {
  const sidecar = JSON.parse(readFileSync(join(ROOT, 'examples', 'actuators.schema.json'), 'utf8'));
  const d = normalizeDataset(sidecar, { rows: [{ id: 'a', name: 'A', mass: 140, buses: ['can'] }] });
  assert.equal(d.properties.mass.type, 'number');
  assert.equal(d.properties.mass.unitText, 'g');
  assert.equal(d.properties.mass.facet, 'range');
  assert.equal(d.properties.buses.type, 'list');
  assert.equal(d.properties.photo.media, 'image');
  assert.equal(d.properties.torque_density.basis, 'derived');
  assert.equal(d.titleProperty, 'name');
  assert.equal(d.rows[0].id, 'a');
});

test('a bare list infers types and ids; one object becomes a property sheet', () => {
  const d = normalizeDataset([{ a: 1, b: 'x', c: [1] }, { a: null, b: 'y', c: [] }]);
  assert.deepEqual(Object.fromEntries(Object.entries(d.properties).map(([k, v]) => [k, v.type])), { a: 'number', b: 'text', c: 'list' });
  assert.deepEqual(d.rows.map((r) => r.id), ['0', '1']);
  const sheet = normalizeDataset({ kt: 0.05, mass: 140 });
  assert.deepEqual(sheet.rows.map((r) => [r.property, r.value]), [['kt', 0.05], ['mass', 140]]);
  assert.equal(inferProperties([{ v: { value: 3, basis: 'measured' } }]).v.type, 'number', 'rich cells infer from their value');
});

test('CSV: quotes, empty cells are null, numbers by column, lists from the schema; JSONL', () => {
  const rows = parseCSV('name,mass,note,buses\n"GIM, 43",140,"said ""hi""",can;rs485\nX,,,\n', { schema: { fields: [{ name: 'buses', type: 'array' }] } });
  assert.deepEqual(rows, [{ name: 'GIM, 43', mass: 140, note: 'said "hi"', buses: ['can', 'rs485'] }, { name: 'X', mass: null, note: null, buses: null }]);
  assert.deepEqual(parseCSV('a\tb\n1\tx\n', { sep: '\t' }), [{ a: 1, b: 'x' }]);
  assert.deepEqual(parseJSONL('{"a":1}\n\n{"a":2}\n'), [{ a: 1 }, { a: 2 }]);
});
