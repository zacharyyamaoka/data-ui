// The peek's trail (packages/core/src/open.js; docs/CONTRACT.md amendment 2026-10-26 (time groups and peek trail)):
// which properties are relations a reader can follow inside the peek. The gestures, the URL and the layouts are browser
// checks (gallery/examples/rack-wiring/checks.py "peek trail", tests/browser/lifecycle_checks.py).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { relationProps } from '../../packages/core/src/open.js';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset, fieldToProperty } from '../../packages/core/src/data.js';
import { properties } from '../../packages/core/src/rowmodel.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');

test('a relation is declared, never guessed: the file\'s graph edges or tree parent, or `relation: true` in the data', () => {
  // the rack: its graph views name `feeds` as their edges, so the peek follows a wire to the part it feeds
  const rack = normalizeDataset(JSON.parse(read('gallery/examples/rack-wiring/rack.json')));
  const base = parseBase(read('gallery/examples/rack-wiring/views.base'));
  assert.deepEqual([...relationProps(base, properties(rack, base))], ['feeds']);
  // a tree's parent is one too; a property the data does not have is not
  const cols = { name: { id: 'name' }, parent: { id: 'parent' }, next: { id: 'next', relation: true } };
  assert.deepEqual([...relationProps({ views: [{ type: 'list', tree: { parent: 'parent' } }, { type: 'graph', edges: { property: 'gone' } }] }, cols)].sort(), ['next', 'parent']);
  // a column of ids that nothing declares stays a plain value (feedback_do_not_invent_undefined_relationships)
  assert.deepEqual([...relationProps({ views: [{ type: 'table' }] }, { name: { id: 'name' }, parent: { id: 'parent' } })], []);
  assert.deepEqual([...relationProps(null, {})], []);
  // a field schema may say so: Table Schema's field passes `relation` through
  assert.equal(fieldToProperty({ name: 'next', type: 'string', relation: true }).relation, true);
});
