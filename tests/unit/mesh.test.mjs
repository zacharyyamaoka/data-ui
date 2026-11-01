// 3D models in views (docs/CONTRACT.md §23): the checker knows `mesh:` / `meshInteract:`, and a view's
// property-valued keys read `note.x` as `x` (Bases' meaning), so the object library's Obsidian-written
// Objects.base (`image: note.thumbnail`, `groupBy: type`) draws its cards with their images.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkText } from '../../packages/core/src/check.js';
import { rowModel, bareView } from '../../packages/core/src/rowmodel.js';
import { parseBase } from '../../packages/core/src/base.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

test('check: mesh names a property of the data; meshInteract is hover | click | none', () => {
  const props = new Set(['name', 'thumbnail', 'model']);
  const ok = checkText('views:\n  - { type: cards, name: C, image: thumbnail, mesh: model, meshInteract: click }', { properties: props, datasetName: 'd' });
  assert.equal(ok.filter((x) => x.level === 'error').length, 0, JSON.stringify(ok));
  const typo = checkText('views:\n  - { type: cards, name: C, mesh: modle }', { properties: props, datasetName: 'd' });
  assert.ok(typo.some((x) => x.level === 'error' && /mesh/.test(x.path || x.message || JSON.stringify(x)) && /modle/.test(JSON.stringify(x))), JSON.stringify(typo));
  const bad = checkText('views:\n  - { type: cards, name: C, mesh: model, meshInteract: spin }', { properties: props, datasetName: 'd' });
  assert.ok(bad.some((x) => x.level === 'error' && /meshInteract/.test(JSON.stringify(x))), JSON.stringify(bad));
});

test('bareView: note.x in image / mesh / order / groupBy / sort reads x, only where x is a column', () => {
  const columns = { thumbnail: {}, type: {}, name: {}, mesh: {} };
  const v = { type: 'cards', image: 'note.thumbnail', mesh: 'note.mesh', order: ['note.name', 'material'], groupBy: { property: 'note.type', direction: 'ASC' }, sort: [{ property: 'note.name', direction: 'ASC' }], start: 'note.nothere' };
  const out = bareView(v, columns);
  assert.equal(out.image, 'thumbnail');
  assert.equal(out.mesh, 'mesh');
  assert.deepEqual(out.order, ['name', 'material']);
  assert.equal(out.groupBy.property, 'type');
  assert.equal(out.sort[0].property, 'name');
  assert.equal(out.start, 'note.nothere', 'a key whose bare name is not a column is left as written');
  assert.equal(v.image, 'note.thumbnail', 'the entry itself is not changed');
  const same = { type: 'table', order: ['name'] };
  assert.equal(bareView(same, columns), same, 'nothing to change: the same object back');
});

test('the object library\'s own Objects.base groups and draws images through note.x (proposal 2)', () => {
  const dir = join(ROOT, 'gallery', 'examples');
  const base = parseBase(readFileSync(join(dir, 'object-db-ledger', 'views.base'), 'utf8'));
  const data = JSON.parse(readFileSync(join(dir, 'object-db-shelf', 'objects.json'), 'utf8'));
  const cards = base.views.find((v) => v.name === 'Cards');
  assert.equal(cards.image, 'note.thumbnail', 'the file keeps what Obsidian wrote');
  const m = rowModel(data, base, cards, {});
  assert.equal(m.rows.length, data.rows.length, 'kind == "instance" keeps every object row');
  assert.ok(m.groups && m.groups.length > 10, 'grouped by type');
  assert.equal(bareView(cards, m.columns).image, 'thumbnail');
  assert.equal(m.columns.mesh.media, 'mesh', 'the mesh field says media: mesh, so the peek draws the orbit viewer');
});

// The poster's camera (CONTRACT §23 meshView): the framing maths, without a GPU
const engine = await import('../../packages/views/mesh/src/index.js');

test('meshView: parseView keeps a valid {dir, fov, box, dist} and falls back to the scan posters\' camera', () => {
  const v = engine.parseView('{"dir":[0.6,0.5,0.6],"fov":45,"box":[0.1,0.2,0.9,0.8],"dist":0.3}');
  assert.deepEqual([v.dir, v.fov, v.box, v.dist], [[0.6, 0.5, 0.6], 45, [0.1, 0.2, 0.9, 0.8], 0.3]);
  assert.equal(engine.parseView('not json'), engine.DEFAULT_VIEW);
  assert.equal(engine.parseView('{"dir":[0,0,0],"fov":500,"box":[1,1,0,0]}').box, null, 'an empty box is no box');
});

test('meshView: anglesOf turns render_thumbs.py\'s direction into yaw 39.3 deg and pitch 29.4 deg', () => {
  const a = engine.anglesOf([0.9, 0.8, 1.1]);
  assert.ok(Math.abs(a.yaw * 180 / Math.PI - 39.29) < 0.05 && Math.abs(a.pitch * 180 / Math.PI - 29.39) < 0.05, JSON.stringify(a));
});

test('meshView: fitBox lands one NDC box on another with one scale, and posterNdc places a contained square poster', () => {
  const f = engine.fitBox([-0.5, -0.5, 0.5, 0.5], [0, 0, 1, 1]);
  assert.deepEqual([f.s, f.tx, f.ty], [1, 0.5, 0.5]);
  // a 200 x 100 box holds a 100 px square poster in its middle: the poster's full box is x -0.5..0.5, y -1..1
  assert.deepEqual(engine.posterNdc([0, 0, 1, 1], 200, 100), [-0.5, -1, 0.5, 1]);
  // y down in the poster, y up in NDC: the poster's top half is NDC's upper half
  assert.deepEqual(engine.posterNdc([0, 0, 1, 0.5], 100, 100), [-1, 0, 1, 1]);
});
