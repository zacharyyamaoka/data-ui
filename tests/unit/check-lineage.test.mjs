// The checker knows `type: lineage` (docs/CONTRACT.md §21): its `lineage:` block is required, each property-valued key
// is checked against the data, and the enums say what they accept.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkText } from '../../packages/core/src/check.js';

const props = new Set(['name', 'parents', 'round', 'round_label', 'thumb', 'status']);
const opts = { properties: props, datasetName: 'd' };
const errs = (text, o = opts) => checkText(text, o).filter((p) => p.level === 'error').map((p) => `${p.line} ${p.path.join('.')} ${p.message}`);

test('lineage: a full block checks clean against the data', () => {
  const good = `views:
  - type: lineage
    name: Tree
    lineage:
      parents: parents
      x: round
      xLabel: round_label
      image: thumb
      label: name
      focus: r16-02
      kept: { status: [picked, liked] }
      extinct: collapse
      layout: radial
`;
  assert.deepEqual(checkText(good, opts), []);
});

test('lineage: the block is required, parents inside it is required', () => {
  assert.ok(errs('views:\n  - type: lineage\n    name: T\n').some((e) => /lineage/.test(e)), errs('views:\n  - type: lineage\n    name: T\n').join('\n'));
  assert.ok(errs('views:\n  - type: lineage\n    name: T\n    lineage: { x: round }\n').some((e) => /parents/.test(e)));
});

test('lineage: property-valued keys are checked against the data, with a suggestion', () => {
  const e = errs('views:\n  - type: lineage\n    name: T\n    lineage: { parents: parent, x: rund, kept: { stat: [a] } }\n');
  assert.ok(e.some((x) => /'parent' is not a property of d \(did you mean 'parents'\?\)/.test(x)), e.join('\n'));
  assert.ok(e.some((x) => /'rund' is not a property of d/.test(x)), e.join('\n'));
  assert.ok(e.some((x) => /'stat' is not a property of d/.test(x)), e.join('\n'));
});

test('lineage: extinct and layout are enums', () => {
  const e = errs('views:\n  - type: lineage\n    name: T\n    lineage: { parents: parents, extinct: hide, layout: circle }\n');
  assert.ok(e.some((x) => /extinct "hide" is not one of show, collapse/.test(x)), e.join('\n'));
  assert.ok(e.some((x) => /layout "circle" is not one of rectangular, radial/.test(x)), e.join('\n'));
});
