// The column menu's .base writes (packages/core/src/propedit.js, docs/CONTRACT.md §28): every other line and comment
// stays as written; Insert, Duplicate and Delete change the file, never the data.
import test from 'node:test';
import assert from 'node:assert/strict';
import { propertiesInText, patchProperties, freshId, editProperty } from '../../packages/core/src/propedit.js';
import { parseBase } from '../../packages/core/src/base.js';
import { properties, rowModel } from '../../packages/core/src/rowmodel.js';

const TEXT = `# a comment on top
data: rows.json
properties:
  # the model's name
  model: { displayName: Model }
  mass: { displayName: Mass }
views:
  - type: table
    name: All
    order: [model, mass]
`;

test('propertiesInText: replace one entry, add one, remove one; comments and other lines stay', () => {
  const out = propertiesInText(TEXT, { mass: { displayName: 'Mass', type: 'number', icon: 'weight' }, status: { displayName: 'Status', type: 'status' }, model: null });
  // the deleted model takes the comment that was about it (judge r2 #2); every other line stays
  assert.match(out, /^# a comment on top\ndata: rows\.json\nproperties:\n  mass:/);
  assert.doesNotMatch(out, /the model's name/);
  assert.doesNotMatch(out, /model: \{ displayName: Model \}/);
  assert.match(out, /  mass: \{ displayName: Mass, type: number, icon: weight \}\n  status: \{ displayName: Status, type: status \}\nviews:/);
  const doc = parseBase(out);
  assert.deepEqual(Object.keys(doc.properties), ['mass', 'status']);
  assert.deepEqual(doc.views[0].order, ['model', 'mass']);
});

test('propertiesInText: a file without properties: gets the block before views:', () => {
  const out = propertiesInText('data: x.json\nviews:\n  - type: table\n    name: A\n', { a: { type: 'rating' } });
  assert.equal(out, 'data: x.json\nproperties:\n  a: { type: rating }\nviews:\n  - type: table\n    name: A\n');
});

test('patchProperties: null removes a key; a null patch removes the entry; note. keys are found', () => {
  assert.deepEqual(patchProperties({ a: { displayName: 'A', icon: 'star' } }, 'a', { icon: null, type: 'select' }), { a: { displayName: 'A', type: 'select' } });
  assert.deepEqual(patchProperties({ a: { x: 1 }, b: {} }, 'a', null), { b: {} });
  assert.deepEqual(patchProperties({ 'note.a': { x: 1 } }, 'a', { y: 2 }), { 'note.a': { x: 1, y: 2 } });
  assert.equal(freshId(['property', 'property_2'], 'property'), 'property_3');
});

// a stand-in element: what editProperty reads (base, data, view, model.columns, el.editing)
const el = (editable = true) => {
  const data = { properties: { model: { type: 'text' }, mass: { type: 'number' } }, rows: [{ id: 1, model: 'A', mass: 3 }] };
  const base = parseBase(TEXT);
  return { editing: editable, base, data, view: base.views[0], model: { columns: properties(data, base) } };
};

test('editProperty: insert left/right, duplicate (reads the same values), delete (file-only gone, data property hidden)', () => {
  assert.throws(() => editProperty(el(false), { action: 'set', id: 'mass', patch: { type: 'number' } }), /read-only/);
  const ins = editProperty(el(), { action: 'insert', at: 'mass', side: 'left', type: 'status' });
  assert.equal(ins.id, 'property');
  assert.deepEqual(ins.order, ['model', 'property', 'mass']);
  assert.deepEqual(ins.properties.property, { displayName: 'Property', type: 'status' });
  assert.deepEqual(editProperty(el(), { action: 'insert', at: 'mass', side: 'right' }).order, ['model', 'mass', 'property']);
  const dup = editProperty(el(), { action: 'duplicate', id: 'mass' });
  assert.equal(dup.id, 'mass_copy');
  assert.deepEqual(dup.properties.mass_copy, { displayName: 'Mass (copy)', from: 'mass' });
  assert.deepEqual(dup.order, ['model', 'mass', 'mass_copy']);
  const data = el().data;
  const cols = properties(data, { properties: dup.properties });
  assert.equal(cols.mass_copy.type, 'number');
  const m = rowModel(data, { properties: dup.properties }, { type: 'table', order: dup.order });
  assert.equal(m.rows[0].mass_copy, 3); // the copy reads the source's value
  assert.equal(data.rows[0].mass_copy, undefined); // the data is never written
  const del = editProperty(el(), { action: 'delete', id: 'mass' });
  assert.deepEqual(del.properties.mass, { displayName: 'Mass', hidden: true });
  assert.deepEqual(del.order, ['model']);
  assert.equal(properties(data, { properties: del.properties }).mass.removed, true);
  const e2 = el();
  e2.base = { ...e2.base, properties: ins.properties };
  const gone = editProperty(e2, { action: 'delete', id: 'property' });
  assert.equal(gone.properties.property, undefined);
  assert.equal(gone.changes.property, null);
});

test('a .base-only typed property is a column with no values of its own, and says why', () => {
  const cols = properties({ properties: { a: { type: 'text' } } }, { properties: { stage: { displayName: 'Stage', type: 'status' } } });
  assert.equal(cols.stage.kind, 'status');
  assert.equal(cols.stage.type, 'text');
  assert.equal(cols.stage.fileOnly, true);
  assert.match(cols.stage.why, /not the data/);
});

// ---- judge r2 #1-#3: the write-back is syntax-aware (block, flow, multi-line flow, empty), keeps every comment it
// did not have to touch, writes the view's new order into the same text, and checks the whole document before it
// hands anything back
import { fileEdit } from '../../packages/core/src/propedit.js';

const views = 'views:\n  - type: table\n    name: All\n    order: [name, mass]\n';
const parsedProps = (t) => parseBase(t).properties;

test('r2 #1: an empty properties: {} takes an insert and still parses', () => {
  const out = fileEdit(`data: x.json\nproperties: {}\n${views}`, { property: { displayName: 'Property', type: 'text' } });
  assert.deepEqual(parsedProps(out), { property: { displayName: 'Property', type: 'text' } });
  assert.equal(parseBase(out).data, 'x.json');
});

test('r2 #1: a flow-style properties: { … } takes an edit in place; data: stays first', () => {
  const text = `data: x.json\nproperties: { mass: { displayName: Mass }, model: { displayName: Model } }  # both\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', icon: 'weight' } });
  assert.ok(out.startsWith('data: x.json\n'), out);
  assert.deepEqual(parsedProps(out), { mass: { displayName: 'Mass', icon: 'weight' }, model: { displayName: 'Model' } });
  assert.match(out, /# both/);
});

test('r2 #1: a multi-line flow property is rewritten whole, never leaving a stray brace', () => {
  const text = `properties:\n  mass: {\n    displayName: Mass,\n    type: number }\n  model: { displayName: Model }\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', type: 'number', icon: 'weight' } });
  assert.deepEqual(parsedProps(out), { mass: { displayName: 'Mass', type: 'number', icon: 'weight' }, model: { displayName: 'Model' } });
  assert.doesNotMatch(out.replace(/\{[^{}]*\}/g, ''), /[{}]/);
});

test('r2 #2: editing a block property patches the changed field only: every comment stays', () => {
  const text = `properties:\n  # the mass comment\n  mass:   # key comment\n    displayName: Mass  # label comment\n    # inner explanation\n    type: number\n  model: { displayName: Model }  # model's\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', type: 'number', icon: 'weight' } });
  for (const c of ['# the mass comment', '# key comment', '# label comment', '# inner explanation', "# model's"]) assert.ok(out.includes(c), c);
  assert.deepEqual(parsedProps(out).mass, { displayName: 'Mass', type: 'number', icon: 'weight' });
  const out2 = fileEdit(text, { mass: { displayName: 'Weight', type: 'number' } });
  assert.match(out2, /    displayName: Weight  # label comment\n/);
  const out3 = fileEdit(text, { mass: { displayName: 'Mass' } });
  assert.doesNotMatch(out3, /type: number/);
  assert.ok(out3.includes('# inner explanation') && out3.includes('# label comment'));
});

test('r2 #2: a flow entry keeps its trailing comment; a deleted entry takes its own comment line with it', () => {
  const text = `properties:\n  # about model\n  model: { displayName: Model }  # model's\n  mass: { displayName: Mass }\n${views}`;
  const out = fileEdit(text, { model: { displayName: 'Model', icon: 'cpu' } });
  assert.match(out, /  model: \{ displayName: Model, icon: cpu \}  # model's\n/);
  const del = fileEdit(text, { model: null });
  assert.doesNotMatch(del, /about model|model:/);
  assert.deepEqual(parsedProps(del), { mass: { displayName: 'Mass' } });
});

test('r2 #3: Insert and Duplicate write the view\'s new order into the same text', () => {
  const text = `properties:\n  mass: { displayName: Mass }\n${views}`;
  const out = fileEdit(text, { property: { displayName: 'Property', type: 'text' } }, { viewIndex: 0, order: ['name', 'property', 'mass'] });
  assert.deepEqual(parseBase(out).views[0].order, ['name', 'property', 'mass']);
  const noOrder = 'properties:\n  mass: {}\nviews:\n  - type: table\n    name: All  # first\n';
  const out2 = fileEdit(noOrder, {}, { viewIndex: 0, order: ['mass'] });
  assert.deepEqual(parseBase(out2).views[0].order, ['mass']);
  assert.match(out2, /# first/);
  const block = 'views:\n  - type: table\n    name: All\n    order:\n      - name\n      - mass\n    sort: []\n';
  const out3 = fileEdit(block, {}, { viewIndex: 0, order: ['mass', 'name'] });
  assert.deepEqual(parseBase(out3).views[0], { type: 'table', name: 'All', order: ['mass', 'name'], sort: [] });
});

test('r2 #1: the whole document is checked before anything is handed back; an unplaceable edit throws', () => {
  assert.throws(() => fileEdit('properties: [\n', { a: { type: 'text' } }), /could not|YAML|line/i);
  // every other top-level key, view and comment is as it was
  const text = `# head\nfilters: 'a > 1'\nproperties:\n  a: { type: number }\n${views}`;
  const out = fileEdit(text, { a: { type: 'percent' } });
  const before = parseBase(text), after = parseBase(out);
  assert.deepEqual({ ...after, properties: null }, { ...before, properties: null });
  assert.ok(out.startsWith('# head\n'));
});

// ---- judge r3 #1: a flow mapping or a multi-line flow entry that is rewritten keeps every comment in it, on the
// entry it was about; a comment above a deleted entry goes only when it names that entry
const comments = (t) => t.split('\n').map((l) => { const i = l.indexOf('#'); return i < 0 ? null : l.slice(i).trim(); }).filter(Boolean);

test('r3 #1: a multi-line flow properties: mapping keeps all of its comments when one entry changes', () => {
  const text = `properties: {  # the properties\n  mass: { displayName: Mass },  # mass label\n  # about the model\n  model: { displayName: Model }  # model label\n}  # end\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', icon: 'weight' } });
  assert.deepEqual(parsedProps(out), { mass: { displayName: 'Mass', icon: 'weight' }, model: { displayName: 'Model' } });
  for (const c of comments(text)) assert.ok(out.includes(c), `${c} kept:\n${out}`);
  // the model's comments stay with the model
  const lines = out.split('\n');
  const m = lines.findIndex((l) => /^\s+model:/.test(l));
  assert.ok(lines[m].includes('# model label') && lines[m - 1].includes('# about the model'), out);
});

test('r3 #1: a multi-line flow entry keeps its key and field comments', () => {
  const text = `properties:\n  mass: {  # the mass\n    displayName: Mass,  # its label\n    type: number }  # a number\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', type: 'number', icon: 'weight' } });
  assert.deepEqual(parsedProps(out).mass, { displayName: 'Mass', type: 'number', icon: 'weight' });
  for (const c of comments(text)) assert.ok(out.includes(c), `${c} kept:\n${out}`);
  assert.match(out, /displayName: Mass\s+# its label/);
});

test('r3 #1: deleting an entry keeps a comment above it that is not about it', () => {
  const text = `properties:\n  # ---- friction terms ----\n  coulomb: { displayName: Coulomb }\n  # the viscous term\n  viscous: { displayName: Viscous }\n${views}`;
  const out = fileEdit(text, { coulomb: null });
  assert.ok(out.includes('# ---- friction terms ----'), out);
  const out2 = fileEdit(text, { viscous: null });
  assert.ok(!out2.includes('# the viscous term'), out2); // it names the entry: it goes with it
});

// ---- judge r3 #2: every valid layout takes the edit
test('r3 #2: an existing empty properties: (block, no entries) takes an insert under it, no second key', () => {
  const text = `data: x.json\nproperties:  # none yet\n${views}`;
  const out = fileEdit(text, { status: { type: 'status' } });
  assert.deepEqual(parsedProps(out), { status: { type: 'status' } });
  assert.equal(out.match(/^properties:/gm).length, 1);
  assert.match(out, /^properties:  # none yet$/m);
});

test('r3 #2: deleting the last property leaves properties: {} (an empty mapping, not null)', () => {
  const text = `properties:  # keep me\n  mass: { displayName: Mass }\n${views}`;
  const out = fileEdit(text, { mass: null });
  assert.deepEqual(parseBase(out).properties, {});
  assert.match(out, /^properties: \{\}  # keep me$/m);
});

test('r3 #2: a flow view - { type: table, … order: […] } takes the new order, with its comment', () => {
  const text = 'properties:\n  mass: {}\nviews:\n  - { type: table, name: All, order: [name, mass] }  # the one view\n';
  const out = fileEdit(text, { property: { type: 'text' } }, { viewIndex: 0, order: ['name', 'property', 'mass'] });
  assert.deepEqual(parseBase(out).views[0], { type: 'table', name: 'All', order: ['name', 'property', 'mass'] });
  assert.match(out, /# the one view/);
  const multi = 'views:\n  - {\n      type: table,  # a table\n      name: All,\n      order: [name] }\n';
  const out2 = fileEdit(multi, {}, { viewIndex: 0, order: ['name', 'mass'] });
  assert.deepEqual(parseBase(out2).views[0].order, ['name', 'mass']);
  assert.match(out2, /# a table/);
});

test('r3 #2: order: as the first field after the dash is replaced in place; a view whose first field is its name gets order after it', () => {
  const text = 'views:\n  - order: [name, mass]  # cols\n    type: table\n    name: All\n';
  const out = fileEdit(text, {}, { viewIndex: 0, order: ['mass', 'name'] });
  assert.deepEqual(parseBase(out).views[0], { order: ['mass', 'name'], type: 'table', name: 'All' });
  assert.match(out, /^ {2}- order: \[mass, name\]  # cols$/m);
  const named = 'views:\n  - name: All\n    type: table\n';
  assert.deepEqual(parseBase(fileEdit(named, {}, { viewIndex: 0, order: ['a'] })).views[0], { name: 'All', type: 'table', order: ['a'] });
  const only = 'views:\n  - type: table\n';
  assert.deepEqual(parseBase(fileEdit(only, {}, { viewIndex: 0, order: ['a'] })).views[0], { type: 'table', order: ['a'] });
});

// ---- judge r4 #1: every comment in a replaced span survives, on what it was about; mapping-level comments stay the
// mapping's; a preceding comment shared with another entry is never deleted
const lineOf = (t, re) => t.split('\n').findIndex((l) => re.test(l));

test('r4 #1: replacing a block order: keeps all of its comments on their items', () => {
  const text = 'views:\n  - type: table\n    name: All\n    order:  # the columns\n      # the name first\n      - name  # title\n      - mass  # weight\n    sort: []\n';
  const out = fileEdit(text, {}, { viewIndex: 0, order: ['name', 'property', 'mass'] });
  assert.deepEqual(parseBase(out).views[0].order, ['name', 'property', 'mass']);
  for (const c of ['# the columns', '# the name first', '# title', '# weight']) assert.ok(out.includes(c), `${c}:\n${out}`);
  assert.match(out, /- name\s+# title/);
  assert.match(out, /- mass\s+# weight/);
  assert.equal(lineOf(out, /# the name first/) + 1, lineOf(out, /- name/));
});

test('r4 #1: recolouring an option keeps the options list\'s comments, each on its item', () => {
  const text = 'properties:\n  priority:\n    type: select\n    options:  # the choices\n      # most urgent first\n      - { value: High, color: red }  # red for urgent\n      - { value: Low, color: green }\n' + views;
  const out = fileEdit(text, { priority: { type: 'select', options: [{ value: 'High', color: 'purple' }, { value: 'Low', color: 'green' }] } });
  assert.deepEqual(parsedProps(out).priority.options, [{ value: 'High', color: 'purple' }, { value: 'Low', color: 'green' }]);
  for (const c of ['# the choices', '# most urgent first', '# red for urgent']) assert.ok(out.includes(c), `${c}:\n${out}`);
  assert.match(out, /value: High, color: purple \}\s+# red for urgent/);
});

test('r4 #1: in a flow mapping a comment above an entry stays above it, the closing comment stays the mapping\'s; then a delete', () => {
  const text = `properties: {  # the properties\n  mass: { displayName: Mass },  # mass label\n  # about the model\n  model: { displayName: Model }\n}  # end\n${views}`;
  const out = fileEdit(text, { mass: { displayName: 'Mass', icon: 'weight' } });
  const L = out.split('\n');
  const m = L.findIndex((l) => /^\s+model:/.test(l));
  assert.ok(L[m - 1].includes('# about the model'), out);
  assert.ok(!L[m].includes('# end'), out);
  assert.ok(out.includes('# end'));
  const del = fileEdit(out, { model: null });
  assert.deepEqual(parsedProps(del), { mass: { displayName: 'Mass', icon: 'weight' } });
  for (const c of ['# the properties', '# mass label', '# end']) assert.ok(del.includes(c), `${c} kept after the delete:\n${del}`);
  assert.ok(!del.includes('# about the model'), del); // about the model alone: it goes with it
});

test('r4 #1: a comment above a deleted entry that names another entry too is shared: it stays', () => {
  const text = `properties:\n  model: { displayName: Model }\n  # Model and mass share a calibration source\n  mass: { displayName: Mass }\n${views}`;
  const out = fileEdit(text, { mass: null });
  assert.ok(out.includes('# Model and mass share a calibration source'), out);
  assert.deepEqual(parsedProps(out), { model: { displayName: 'Model' } });
});

// ---- judge r4 #5: a document written as one root flow mapping takes edits
test('r4 #5: a root flow mapping {properties: …, views: […]} takes a property edit and an order, its comments kept', () => {
  const text = '# a whole file in flow style\n{properties: {mass: {type: number}}, views: [{type: table, name: All}]}  # one line\n';
  const out = fileEdit(text, { mass: { type: 'number', icon: 'weight' } }, { viewIndex: 0, order: ['mass'] });
  const doc = parseBase(out);
  assert.deepEqual(doc.properties, { mass: { type: 'number', icon: 'weight' } });
  assert.deepEqual(doc.views, [{ type: 'table', name: 'All', order: ['mass'] }]);
  for (const c of ['# a whole file in flow style', '# one line']) assert.ok(out.includes(c), out);
});

// ---- judge r5 #1: no comment the writer did not emit is lost; a mapping's comment stays the mapping's; a comment
// inside a list item stays with that item
const allComments = (t) => t.split('\n').map((l) => { const i = l.indexOf('#'); return i < 0 ? null : l.slice(i).trim(); }).filter(Boolean);

test('r5 #1: a flow order: [ # start … ] # end keeps both comments, start on the key, end after the items', () => {
  const text = 'views:\n  - type: table\n    name: All\n    order: [ # start columns\n      name, mass\n    ] # end columns\n';
  const out = fileEdit(text, {}, { viewIndex: 0, order: ['mass', 'name'] });
  assert.deepEqual(parseBase(out).views[0].order, ['mass', 'name']);
  for (const c of ['# start columns', '# end columns']) assert.ok(out.includes(c), `${c}:\n${out}`);
  assert.ok(lineOf(out, /# start columns/) < lineOf(out, /# end columns/), out);
});

test('r5 #1: recolouring a single-option flow list keeps its closing comment', () => {
  const text = 'properties:\n  priority:\n    type: select\n    options: [ # the one option\n      { value: High, color: red }\n    ] # only High\n' + views;
  const out = fileEdit(text, { priority: { type: 'select', options: [{ value: 'High', color: 'purple' }] } });
  assert.deepEqual(parsedProps(out).priority.options, [{ value: 'High', color: 'purple' }]);
  for (const c of ['# the one option', '# only High']) assert.ok(out.includes(c), `${c}:\n${out}`);
});

test('r5 #1: a one-line flow mapping\'s trailing comment is the mapping\'s: editing then deleting mass keeps it', () => {
  const text = `properties: { mass: { displayName: Mass }, model: { displayName: Model } }  # calibration for all properties\n${views}`;
  const edited = fileEdit(text, { mass: { displayName: 'Mass', icon: 'weight' } });
  assert.ok(edited.includes('# calibration for all properties'), edited);
  const massLine = edited.split('\n').find((l) => /^\s+mass:/.test(l));
  assert.ok(!massLine.includes('# calibration'), edited);
  const deleted = fileEdit(edited, { mass: null });
  assert.ok(deleted.includes('# calibration for all properties'), deleted);
  assert.deepEqual(parsedProps(deleted), { model: { displayName: 'Model' } });
});

test('r5 #1: a comment inside a block option stays with that option, never moving to the next one', () => {
  const text = 'properties:\n  priority:\n    type: select\n    options:\n      - value: High\n        # urgent work\n        color: red\n      - value: Low\n        color: green\n' + views;
  // reordered, so the comment's owner shows: it must travel with High, after it, not stay above whichever comes next
  const out = fileEdit(text, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }] } });
  assert.deepEqual(parsedProps(out).priority.options, [{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }]);
  assert.ok(out.includes('# urgent work'), out);
  assert.ok(lineOf(out, /# urgent work/) > lineOf(out, /value: High/) && lineOf(out, /# urgent work/) > lineOf(out, /value: Low/), out);
  const del = fileEdit(out, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }] } });
  assert.deepEqual(parsedProps(del).priority.options, [{ value: 'Low', color: 'green' }]);
  assert.ok(del.includes('# urgent work'), del); // a comment is never dropped silently
});

test('r5 #1: whatever the layout, every comment in the input is somewhere in the output (all fixtures of this file)', () => {
  const cases = [
    ['views:\n  - type: table\n    name: All\n    order: [ # a\n      name, # b\n      mass ] # c\n', {}, { viewIndex: 0, order: ['mass'] }],
    ['properties: {  # h\n  mass: { displayName: Mass }, # m\n  # above model\n  model: {} # mo\n} # t\n' + views, { mass: null }, {}],
  ];
  for (const [text, ch, o] of cases) {
    const out = fileEdit(text, ch, o);
    for (const c of allComments(text)) assert.ok(out.includes(c), `${c} lost:\n${out}`);
  }
});

// ---- judge r5 #3: a document marker before a root flow mapping
test('r5 #3: --- before a root flow mapping: property and order edits', () => {
  const text = '---\n{properties: {mass: {type: number}}, views: [{type: table, name: All}]}\n';
  const out = fileEdit(text, { mass: { type: 'number', icon: 'weight' } }, { viewIndex: 0, order: ['mass'] });
  assert.ok(out.startsWith('---\n'), out);
  assert.deepEqual(parseBase(out), { properties: { mass: { type: 'number', icon: 'weight' } }, views: [{ type: 'table', name: 'All', order: ['mass'] }] });
});

// every real .base file in the gallery: an icon added to each property, the first view's order reversed; every
// comment of the file survives and the edit reads back exactly (fileEdit checks the document; this checks comments)
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
test('every gallery .base file: per-property edits and an order change keep every comment', () => {
  const EX = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'gallery', 'examples');
  let files = 0, edits = 0;
  for (const d of readdirSync(EX)) {
    const f = join(EX, d, 'views.base');
    if (!existsSync(f)) continue;
    const text = readFileSync(f, 'utf8');
    const doc = parseBase(text);
    files++;
    let cur = text;
    for (const [k, v] of Object.entries(doc.properties || {})) {
      if (!v || typeof v !== 'object') continue;
      cur = fileEdit(cur, { [k]: { ...v, icon: 'star' } });
      edits++;
    }
    const views = parseBase(cur).views || [];
    const i = views.findIndex((v) => Array.isArray(v.order) && v.order.length > 1);
    if (i >= 0) { cur = fileEdit(cur, {}, { viewIndex: i, order: [...views[i].order].reverse() }); edits++; }
    const bag = (t) => t.split('\n').map((l) => { const at = l.indexOf(' #'); return l.trim().startsWith('#') ? l.trim() : at >= 0 ? l.slice(at + 1).trim() : null; }).filter(Boolean).sort();
    const lost = bag(text).filter((c) => !cur.includes(c));
    assert.deepEqual(lost, [], `${d}: comments lost`);
  }
  assert.ok(files > 20 && edits > 100, `${files} files, ${edits} edits`);
});

// ---- judge r6 #1: comment ownership is recursive — a comment inside a nested flow mapping or list item stays on its
// owner through a recolour, a reorder and a delete (placement, not just survival)
const on = (t, comment, re) => { const L = t.split('\n'); const i = L.findIndex((l) => l.includes(comment)); return i >= 0 && re.test(L[i]); };
const optsText = (body) => `properties:\n  priority:\n    type: select\n    options: [\n${body}    ]\n${views}`;

test('r6 #1: flow options with a comment after each item: each comment stays on its option through recolour, reorder and delete', () => {
  const text = optsText('      { value: High, color: red }, # High guidance\n      { value: Low, color: green } # Low guidance\n');
  const recol = fileEdit(text, { priority: { type: 'select', options: [{ value: 'High', color: 'purple' }, { value: 'Low', color: 'green' }] } });
  assert.deepEqual(parsedProps(recol).priority.options, [{ value: 'High', color: 'purple' }, { value: 'Low', color: 'green' }]);
  assert.ok(on(recol, '# High guidance', /value: High/), recol);
  assert.ok(on(recol, '# Low guidance', /value: Low/), recol);
  assert.ok(lineOf(recol, /# High guidance/) > lineOf(recol, /options:/), `nothing moves above options:\n${recol}`);
  const reord = fileEdit(recol, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }] } });
  assert.ok(on(reord, '# High guidance', /value: High/) && on(reord, '# Low guidance', /value: Low/), reord);
  assert.ok(lineOf(reord, /value: Low/) < lineOf(reord, /value: High/), reord);
  // the same reorder straight from the flow text
  const reord0 = fileEdit(text, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }, { value: 'High', color: 'red' }] } });
  assert.ok(on(reord0, '# High guidance', /value: High/) && on(reord0, '# Low guidance', /value: Low/), reord0);
  const del = fileEdit(text, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }] } });
  assert.deepEqual(parsedProps(del).priority.options, [{ value: 'Low', color: 'green' }]);
  assert.ok(on(del, '# Low guidance', /value: Low/), del);
  assert.ok(del.includes('# High guidance') && lineOf(del, /# High guidance/) > lineOf(del, /options:/), `kept, inside the list:\n${del}`);
});

test('r6 #1: a comment line above a flow item and a comment inside its mapping travel with that item', () => {
  const text = optsText('      # urgent work first\n      { value: High, # the top option\n        color: red },\n      { value: Low, color: green }\n');
  const out = fileEdit(text, { priority: { type: 'select', options: [{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }] } });
  assert.deepEqual(parsedProps(out).priority.options, [{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }]);
  assert.ok(on(out, '# the top option', /value: High/), out);
  const high = lineOf(out, /value: High/);
  assert.ok(lineOf(out, /# urgent work first/) === high - 1, `the line above High's item:\n${out}`);
  assert.ok(high > lineOf(out, /value: Low/), out);
});

test('r6 #1: --- and a root flow mapping: mass and model keep their own comments through an edit, an order and a delete', () => {
  const text = '---\n{\n  properties: {\n    mass: { type: number }, # mass calibration\n    model: { type: text } # model note\n  },\n  views: [ { type: table, name: All } ]\n}\n';
  const out = fileEdit(text, { mass: { type: 'number', icon: 'weight' } });
  assert.deepEqual(parseBase(out).properties, { mass: { type: 'number', icon: 'weight' }, model: { type: 'text' } });
  assert.ok(on(out, '# mass calibration', /^\s+mass:/), out);
  assert.ok(on(out, '# model note', /^\s+model:/), out);
  assert.ok(!/properties:.*#/.test(out), `nothing flattened onto properties:\n${out}`);
  const ord = fileEdit(out, {}, { viewIndex: 0, order: ['model', 'mass'] });
  assert.ok(on(ord, '# mass calibration', /^\s+mass:/) && on(ord, '# model note', /^\s+model:/), ord);
  const del = fileEdit(text, { mass: null });
  assert.deepEqual(parseBase(del).properties, { model: { type: 'text' } });
  assert.ok(on(del, '# model note', /^\s+model:/), del);
  assert.ok(del.includes('# mass calibration') && !on(del, '# mass calibration', /properties:|model:/), del);
});

test('r6 #1: comments on the fields of a nested flow entry stay on those fields', () => {
  const text = `properties: {\n  mass: {\n    type: number, # kg on the datasheet\n    icon: weight # the scale icon\n  },\n  model: { type: text } # model note\n}\n${views}`;
  const out = fileEdit(text, { mass: { type: 'number', icon: 'scale' } });
  assert.deepEqual(parsedProps(out), { mass: { type: 'number', icon: 'scale' }, model: { type: 'text' } });
  assert.ok(on(out, '# kg on the datasheet', /type: number/), out);
  assert.ok(on(out, '# the scale icon', /icon: scale/), out);
  assert.ok(on(out, '# model note', /model:/), out);
});

test('r6 #1: a flow view\'s order list keeps a comment on its item when the order changes', () => {
  const text = 'views:\n  - { type: table, name: All, # the main view\n      order: [ name, # title first\n        mass ] }\n';
  const out = fileEdit(text, {}, { viewIndex: 0, order: ['mass', 'name'] });
  assert.deepEqual(parseBase(out).views[0].order, ['mass', 'name']);
  assert.ok(on(out, '# title first', /- name\b/), out);
  assert.ok(out.includes('# the main view'), out);
});

test('r6 #1: placement table — each comment names its owner (#@x on x\'s line, #^x right above it) and stays there through recolour, reverse and delete', () => {
  const place = (t, gone = []) => {
    const L = t.split('\n');
    for (const [i, l] of L.entries()) {
      for (const m of l.matchAll(/#([@^])(\w+)/g)) {
        const [, how, who] = m;
        if (gone.includes(who)) continue;
        const target = how === '@' ? l : L.slice(i + 1).find((x) => x.trim() && !x.trim().startsWith('#')) || '';
        assert.ok(new RegExp(`\\b${who}\\b`).test(target.replace(/#.*/, '')), `${m[0]} is not on ${who}'s line:\n${t}`);
      }
    }
  };
  const opts = (list) => ({ priority: { type: 'select', options: list } });
  const H = { value: 'High', color: 'red' }, M = { value: 'Mid', color: 'yellow' }, Lo = { value: 'Low', color: 'green' };
  const fixtures = [
    optsText('      #^High\n      { value: High, color: red }, #@High\n      { value: Mid, color: yellow }, #@Mid\n      #^Low\n      { value: Low, color: green } #@Low\n'),
    optsText('      { value: High, #@High\n        color: red }, #@red\n      { value: Mid, color: yellow }, #@Mid\n      { value: Low, color: green } #@Low\n'),
    `properties: {\n  priority: {\n    type: select, #@type\n    options: [ { value: High, color: red }, #@High\n      { value: Mid, color: yellow }, #@Mid\n      { value: Low, color: green } ] #@Low\n  }\n}\n${views}`,
  ];
  for (const text of fixtures) {
    place(text);
    const recol = fileEdit(text, opts([{ ...H, color: 'purple' }, M, Lo]));
    assert.deepEqual(parsedProps(recol).priority.options, [{ ...H, color: 'purple' }, M, Lo]);
    place(recol.replace(/\bpurple\b/, 'red'));
    const rev = fileEdit(text, opts([Lo, M, H]));
    assert.deepEqual(parsedProps(rev).priority.options, [Lo, M, H]);
    place(rev);
    const del = fileEdit(text, opts([H, Lo]));
    assert.deepEqual(parsedProps(del).priority.options, [H, Lo]);
    place(del, ['Mid']);
    for (const c of allComments(text)) assert.ok(del.includes(c), `${c} kept:\n${del}`);
  }
});

// ---- judge r7 #4: a no-op edit is the file, byte for byte; the file's newlines are kept
test('r7 #4: a no-op returns the original bytes — a root flow document, a CRLF file, an edit that sets what is already there', () => {
  const flow = '{properties: {mass: {type: number}}, views: [{type: table, name: All}]}  # one line\n';
  assert.equal(fileEdit(flow, {}), flow);
  assert.equal(fileEdit(flow, { mass: { type: 'number' } }), flow);
  const crlf = 'properties:\r\n  mass: { type: number }  # kg\r\nviews:\r\n  - type: table\r\n    name: All\r\n    order: [mass]\r\n';
  assert.equal(fileEdit(crlf, {}), crlf);
  assert.equal(fileEdit(crlf, { mass: { type: 'number' } }), crlf);
  assert.equal(fileEdit(crlf, {}, { viewIndex: 0, order: ['mass'] }), crlf);
  const edited = fileEdit(crlf, { mass: { type: 'number', icon: 'weight' } });
  assert.ok(!/[^\r]\n/.test(edited) && edited.includes('\r\n'), `every line ends CRLF:\n${JSON.stringify(edited)}`);
  assert.deepEqual(parseBase(edited).properties, { mass: { type: 'number', icon: 'weight' } });
  assert.ok(edited.includes('# kg'), edited);
});

// placement: the owner must be in the line's own content, not in the comment's words ("# inner a" names a)
const onBody = (t, comment, re) => { const L = t.split('\n'); const i = L.findIndex((l) => l.includes(comment)); return i >= 0 && re.test(L[i].slice(0, L[i].indexOf(comment))); };
// ---- judge r7 #1: ownership survives SEQUENTIAL edits — each step edits the previous step's output; after every step
// every comment is present and on its owner
const opts = (list) => ({ priority: { type: 'select', options: list } });
const serial = (start, steps) => {
  let text = start;
  const all = allComments(start);
  steps.forEach(([label, change, check]) => {
    text = fileEdit(text, change);
    for (const c of all) assert.ok(text.includes(c), `${label}: ${c} lost:\n${text}`);
    check(text, label);
  });
  return text;
};

test('r7 #1: a flow option\'s field comments stay on their fields through recolour -> reverse -> recolour -> delete, each on the last output', () => {
  const text = optsText('      {value: High, # High guidance\n       color: red, # colour guidance\n       group: todo},\n      {value: Low, color: green}\n');
  const H = (color) => ({ value: 'High', color, group: 'todo' }), L = { value: 'Low', color: 'green' };
  const placed = (t, label) => {
    assert.ok(onBody(t, '# High guidance', /value: High/), `${label}: High guidance off its line:\n${t}`);
    assert.ok(onBody(t, '# colour guidance', /color: (red|purple|blue)/), `${label}: colour guidance off the color field:\n${t}`);
  };
  serial(text, [
    ['recolour', opts([H('purple'), L]), (t, l) => { placed(t, l); assert.deepEqual(parsedProps(t).priority.options, [H('purple'), L]); }],
    ['reverse', opts([L, H('purple')]), (t, l) => { placed(t, l); assert.ok(lineOf(t, /value: Low/) < lineOf(t, /value: High/), t); }],
    ['recolour again', opts([L, H('blue')]), (t, l) => { placed(t, l); assert.ok(onBody(t, '# colour guidance', /color: blue/), t); }],
    ['delete Low', opts([H('blue')]), (t, l) => { placed(t, l); assert.deepEqual(parsedProps(t).priority.options, [H('blue')]); }],
  ]);
});

test('r7 #1: a comment on an item of a nested list stays on that item through reorder -> edit -> delete, each on the last output', () => {
  const text = `properties:\n  grid:\n    type: text\n    levels: [\n      [a, # inner a\n       b],\n      [c, d] # the cd pair\n    ]\n${views}`;
  const G = (levels, type = 'text') => ({ grid: { type, levels } });
  serial(text, [
    ['reorder', G([['c', 'd'], ['a', 'b']]), (t, l) => {
      assert.ok(onBody(t, '# inner a', /\ba\b/) && !onBody(t, '# inner a', /\bc\b/), `${l}: inner a off a:\n${t}`);
      assert.ok(onBody(t, '# the cd pair', /\bc\b/), `${l}: cd pair off c:\n${t}`);
      assert.deepEqual(parsedProps(t).grid.levels, [['c', 'd'], ['a', 'b']]);
    }],
    ['edit another field', G([['c', 'd'], ['a', 'b']], 'select'), (t, l) => {
      assert.ok(onBody(t, '# inner a', /\ba\b/) && onBody(t, '# the cd pair', /\bc\b/), `${l}:\n${t}`);
    }],
    ['delete cd', G([['a', 'b']], 'select'), (t, l) => {
      assert.ok(onBody(t, '# inner a', /\ba\b/), `${l}:\n${t}`);
      assert.deepEqual(parsedProps(t).grid.levels, [['a', 'b']]);
    }],
  ]);
});

test('r7 #1: block options written by hand keep field comments through reverse -> recolour, each on the last output', () => {
  const text = 'properties:\n  priority:\n    type: select\n    options:\n      # urgent first\n      - value: High  # High guidance\n        color: red  # colour guidance\n      - value: Low\n        color: green  # calm\n' + views;
  serial(text, [
    ['reverse', opts([{ value: 'Low', color: 'green' }, { value: 'High', color: 'red' }]), (t, l) => {
      assert.ok(onBody(t, '# High guidance', /value: High/) && onBody(t, '# colour guidance', /color: red/) && onBody(t, '# calm', /color: green/), `${l}:\n${t}`);
      assert.equal(lineOf(t, /# urgent first/) + 1, lineOf(t, /value: High/), `${l}: urgent first right above High:\n${t}`);
    }],
    ['recolour', opts([{ value: 'Low', color: 'green' }, { value: 'High', color: 'purple' }]), (t, l) => {
      assert.ok(onBody(t, '# colour guidance', /color: purple/) && onBody(t, '# calm', /color: green/), `${l}:\n${t}`);
    }],
  ]);
});
