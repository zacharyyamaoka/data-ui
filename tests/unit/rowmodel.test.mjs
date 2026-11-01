// The ONE row model (packages/core/src/rowmodel.js). Oracle: the views-catalog lane's independent lift of the same
// pipeline (docs/views/demo/core.mjs, on the table lane's own grammar.js), on robotparts' 1,149 actuators.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { rowModel, properties, treeSpec, treeRows } from '../../packages/core/src/rowmodel.js';
import { parseBase } from '../../packages/core/src/base.js';
import { cellValue } from '../../packages/core/src/grammar.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples', 'robotparts-actuators');
const actuators = JSON.parse(readFileSync(join(EX, 'actuators.json'), 'utf8'));
const base = parseBase(readFileSync(join(EX, 'views.base'), 'utf8'));
const DEMO = join(ROOT, 'docs', 'views', 'demo', 'core.mjs');
const haveDemo = existsSync(DEMO) && existsSync(join(ROOT, 'docs', 'views', 'node_modules', '@tanstack', 'table-core'));
const ids = (rows) => rows.map((r) => r.id);

test('the same rows, in the same order and groups, as the demo\'s independent lift (every table preset)', { skip: !haveDemo && 'docs/views/demo or its node_modules is absent' }, async () => {
  const demo = await import(pathToFileURL(DEMO).href);
  // the demo predates rich cells: hand it the plain values
  const plain = { ...actuators, rows: actuators.rows.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, cellValue(v)]))) };
  let compared = 0;
  for (const view of base.views.filter((v) => v.type === 'table')) {
    const ours = rowModel(actuators, base, view);
    const theirs = demo.rowModel(plain, { filters: base.filters }, { ...view, subGroupBy: undefined, limit: undefined });
    if (view.subGroupBy) {
      // the demo groups one level; compare the top level's membership
      assert.deepEqual(ours.groups.map((g) => [g.key, g.rows.length]), theirs.groups.map((g) => [g.key, g.rows.length]), view.name);
    } else {
      assert.deepEqual(ids(ours.rows), ids(theirs.rows), view.name);
      if (theirs.groups) assert.deepEqual(ours.groups.map((g) => [g.key, ids(g.rows)]), theirs.groups.map((g) => [g.key, ids(g.rows)]), view.name);
    }
    compared++;
  }
  // WHY counted from the file, not a constant: open modes (5e7bfb1) added two table presets and this read 7 !== 5 in
  // every checkout with docs/views/node_modules (lane worktrees skip the test, so it hid); every table preset is compared
  assert.equal(compared, base.views.filter((v) => v.type === 'table').length);
  assert.ok(compared >= 7, `${compared} table presets`);
});

test('filters: the file\'s AND the view\'s; the rail\'s override replaces the file\'s; errors are reported, not thrown', () => {
  const view = base.views.find((v) => v.name === 'Geared CAN under $150');
  const m = rowModel(actuators, base, view);
  assert.ok(m.rows.length > 0 && m.rows.length < 100, `${m.rows.length} rows`);
  assert.ok(m.rows.every((r) => r.drivetrain === 'geared' && r.buses.includes('can') && r.price < 150));
  const narrowed = rowModel(actuators, base, view, { filters: 'brand == "Steadywin"' });
  assert.ok(narrowed.rows.every((r) => r.brand === 'Steadywin'));
  const broken = rowModel(actuators, base, { ...view, filters: 'price <' });
  assert.match(broken.error, /unexpected end/);
  assert.equal(broken.total, 1149);
});

test('groupOrder orders the groups, and a named group with no rows still shows', () => {
  const view = { type: 'table', name: 'g', groupBy: { property: 'form' }, groupOrder: ['wheel hub', 'no such form', 'hobby servo'] };
  const m = rowModel(actuators, base, view);
  assert.deepEqual(m.groups.slice(0, 3).map((g) => [g.key, g.rows.length > 0]), [['wheel hub', true], ['no such form', false], ['hobby servo', true]]);
  assert.equal(m.groups.reduce((s, g) => s + g.rows.length, 0), 1149);
  assert.deepEqual(ids(m.rows), m.groups.flatMap((g) => ids(g.rows)), 'rows are in group order');
});

test('subGroupBy nests one level; limit keeps the first rows in drawn order', () => {
  const view = base.views.find((v) => v.name === 'Brand › form');
  const m = rowModel(actuators, base, view);
  const steadywin = m.groups.find((g) => g.key === 'Steadywin');
  assert.ok(steadywin.groups.length >= 1);
  assert.equal(steadywin.groups.reduce((s, g) => s + g.rows.length, 0), steadywin.rows.length);
  const limited = rowModel(actuators, base, { ...view, limit: 7 });
  assert.equal(limited.rows.length, 7);
  assert.deepEqual(ids(limited.rows), ids(m.rows).slice(0, 7));
  assert.equal(limited.matched, 1149);
});

test('sort reads rich cells as numbers; empty values sort last', () => {
  const m = rowModel(actuators, base, { type: 'table', name: 's', sort: [{ property: 'mass', direction: 'ASC' }] });
  const masses = m.rows.map((r) => cellValue(r.mass));
  const filled = masses.filter((x) => x !== null && x !== undefined);
  assert.deepEqual(filled, [...filled].sort((a, b) => a - b));
  assert.ok(masses.slice(filled.length).every((x) => x === null || x === undefined), 'missing masses come last');
  assert.ok(masses.includes(140), 'the AKE40-6 KV90 weighs 140 g');
});

test('search over the visible properties', () => {
  const m = rowModel(actuators, base, { type: 'table', name: 'q', order: ['model', 'brand'] }, { query: 'gim43' });
  assert.ok(m.rows.length >= 1 && m.rows.every((r) => /gim43/i.test(r.model + r.brand)));
});

test('pivot: groups x split columns, one summary per cell, the records behind it', () => {
  const view = base.views.find((v) => v.name === 'Brand × form');
  const m = rowModel(actuators, base, view);
  assert.ok(m.pivot.columns.length >= 5);
  const total = m.pivot.rows.reduce((s, r) => s + m.pivot.columns.reduce((t, c) => t + (r[c.id] ? r[c.id].v : 0), 0), 0);
  assert.equal(total, actuators.rows.filter((r) => r.form).length, 'every record with a form is counted once');
  const cell = m.pivot.rows.find((r) => r.brand === 'Steadywin')[m.pivot.columns[0].id];
  assert.ok(!cell || cell.records.every((r) => r.brand === 'Steadywin'));
  assert.equal(m.rows.length, 1149, 'rows stay the records, for every other view');
  const torque = rowModel(actuators, base, base.views.find((v) => v.name === 'Torque by drivetrain × form'));
  const geared = torque.pivot.rows.find((r) => r.drivetrain === 'geared');
  const servo = geared['@hobby servo'];
  const vals = servo.records.map((r) => cellValue(r.peak_torque)).filter((x) => typeof x === 'number').sort((a, b) => a - b);
  const mid = vals.length >> 1;
  assert.equal(servo.v, vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2, 'the cell is the median of its records');
});

test('properties take their labels from the .base file', () => {
  const p = properties(actuators, base);
  assert.equal(p.torque_density.label, 'Peak N·m/kg');
  assert.equal(p.url.label, 'url');
  assert.equal(p.mass.unitText, 'g');
});

// ---- tree: (docs/CONTRACT.md amendment 2026-10-26 (core pass)): the outline is TanStack's sub-rows, nested by the core
const outline = {
  id: 'outline', titleProperty: 'name',
  properties: { name: { type: 'text' }, parent: { type: 'text' }, kind: { type: 'text' }, n: { type: 'number' }, path: { type: 'text' } },
  rows: [
    { id: 'a', name: 'A', parent: null, kind: 'x', n: 3, path: 'act.steadywin.gim' },
    { id: 'b', name: 'B', parent: 'a', kind: 'y', n: 2, path: 'act.steadywin' },
    { id: 'c', name: 'C', parent: 'a', kind: 'x', n: 1, path: 'act.cubemars.ak' },
    { id: 'd', name: 'D', parent: 'c', kind: 'x', n: 5, path: 'act.cubemars.ak' },
    { id: 'e', name: 'E', parent: 'f', kind: 'y', n: 4, path: 'sensor' },
    { id: 'f', name: 'F', parent: 'e', kind: 'y', n: 6, path: '' },
  ],
};
const drawn = (m) => m.table.getRowModel().rows.map((r) => `${'  '.repeat(r.depth)}${r.getIsGrouped() ? `[${r.groupingValue}]` : r.original._heading !== undefined ? `#${r.original._heading}` : r.original.id}`);

test('tree: {parent}: children under their parent, sorted among their siblings, a cycle cut where it closes', () => {
  const m = rowModel(outline, {}, { type: 'table', name: 't', tree: { parent: 'parent' }, sort: [{ property: 'n', direction: 'ASC' }] });
  // e <-> f is a cycle: the first row whose chain closes on itself (e) starts at the top
  assert.deepEqual(drawn(m), ['a', '  c', '    d', '  b', 'e', '  f']);
  assert.deepEqual(ids(m.rows), ['a', 'c', 'd', 'b', 'e', 'f'], 'input.rows: every row, in outline order');
  const filtered = rowModel(outline, {}, { type: 'list', name: 't', tree: { parent: 'parent' }, filters: 'id != "a"' });
  assert.deepEqual(drawn(filtered).filter((x) => !x.startsWith(' ')), ['b', 'c', 'e'], 'a row whose parent is filtered out starts at the top');
  m.table.setExpanded({});
  assert.deepEqual(m.table.getRowModel().rows.map((r) => r.id), ['a', 'e'], 'folded: only the tops');
});

test('tree: {path}: missing ancestors are headings, never rows; a second row on one path is a sibling', () => {
  const m = rowModel(outline, {}, { type: 'list', name: 'p', tree: { path: 'path' } });
  // a (act.steadywin.gim) made the heading act.steadywin; row b's path is act.steadywin, so b takes its place; c and d
  // share act.cubemars.ak, so d is c's sibling, under the heading cubemars
  assert.deepEqual(drawn(m), ['#act', '  b', '    a', '  #cubemars', '    c', '    d', 'e', 'f']);
  assert.equal(m.rows.length, 6, 'headings are in input.table, not in input.rows');
  assert.ok(m.rows.every((r) => r._heading === undefined));
});

test('tree: with groupBy, a group holds the top of each tree; other view types ignore the key', () => {
  const m = rowModel(outline, {}, { type: 'table', name: 'g', tree: { parent: 'parent' }, groupBy: { property: 'kind' } });
  assert.deepEqual(m.groups.map((g) => [g.key, ids(g.rows)]), [['x', ['a', 'b', 'c', 'd']], ['y', ['e', 'f']]], 'b (kind y) follows its parent a into group x');
  const board = rowModel(outline, {}, { type: 'kanban', name: 'k', tree: { parent: 'parent' }, groupBy: { property: 'kind' } });
  assert.deepEqual(board.groups.map((g) => [g.key, g.rows.length]), [['x', 3], ['y', 3]]);
  assert.equal(treeSpec({ type: 'table', tree: { parent: 'nope' } }, outline.properties), null, 'a tree naming no property is no tree');
});

test('tree: on real data, Vibe Tracks\' feature tree nests every node under its parent', () => {
  const dir = join(ROOT, 'gallery', 'examples', 'vibetracks-feature-tree');
  const data = JSON.parse(readFileSync(join(dir, 'spec-tree.json'), 'utf8'));
  const vb = parseBase(readFileSync(join(dir, 'views.base'), 'utf8'));
  const m = rowModel(data, vb, vb.views[0]);
  const flat = m.table.getRowModel().rows;
  assert.equal(flat.length, data.rows.length);
  for (const r of flat) if (r.depth > 0) assert.equal(String(r.original.parent), r.parentId, `${r.id} sits under its parent`);
  assert.equal(treeRows(data.rows, { parent: 'parent' }).roots.length, flat.filter((r) => r.depth === 0).length);
});
