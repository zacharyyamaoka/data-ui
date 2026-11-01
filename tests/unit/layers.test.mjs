// PEP 0010 P1a (docs/CONTRACT.md §32): what a view receives as input.layers. <data-dashboard> hands each panel's
// <data-views> its layer datasets ({<dataset>: {dataset, rows}}, the rows already filtered by model.js), and the element
// passes them to the view's update() as input.layers through packages/core/src/layers.js. Written red, before that
// module existed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDataset } from '../../packages/core/src/data.js';

const L = () => import('../../packages/core/src/layers.js');

const diff = () => {
  const d = normalizeDataset({ schema: { fields: [
    { name: 't', type: 'number', unit: 's' }, { name: 'situation', type: 'string' }, { name: 'x_mm', type: 'number', unit: 'mm' },
  ] }, rows: [{ t: 0, situation: 'real', x_mm: 1 }, { t: 0.1, situation: 'real', x_mm: 2 }, { t: 0, situation: 'twin', x_mm: 3 }] });
  return { ...d, url: 'https://example.test/run/diff_poses.json' };
};

test('input.layers: each dataset\'s filtered rows (the same objects), its columns as input.columns has them, its total and URL', async () => {
  const { layersInput } = await L();
  const ds = diff();
  const out = layersInput({ diff: { dataset: ds, rows: [ds.rows[0], ds.rows[2]] } }, { properties: { x_mm: { displayName: 'x' } } });
  assert.deepEqual(Object.keys(out), ['diff']);
  assert.equal(out.diff.rows.length, 2);
  assert.equal(out.diff.rows[0], ds.rows[0], 'never a copy: views read rows, never write them');
  assert.equal(out.diff.rows[1], ds.rows[2]);
  assert.equal(out.diff.total, 3);
  assert.equal(out.diff.url, 'https://example.test/run/diff_poses.json');
  assert.equal(out.diff.columns.x_mm.label, 'x', "the .base's displayName, as input.columns");
  assert.equal(out.diff.columns.x_mm.unitText, 'mm', "the sidecar's unit");
  assert.equal(out.diff.columns.t.type, 'number');
  assert.ok(Object.isFrozen(out) && Object.isFrozen(out.diff), 'frozen, as input.view is');
});

test('input.layers: an entry without rows is every row; an entry without a dataset is left out; none at all is {}', async () => {
  const { layersInput } = await L();
  const ds = diff();
  const all = layersInput({ diff: { dataset: ds }, ghost: { rows: [] } }, null);
  assert.deepEqual(Object.keys(all), ['diff']);
  assert.equal(all.diff.rows.length, 3);
  for (const empty of [layersInput(null, null), layersInput(undefined, {}), layersInput({}, {})]) {
    assert.deepEqual(empty, {});
    assert.ok(Object.isFrozen(empty));
  }
});
