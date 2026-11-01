// Nested groups (docs/peps/, CONTRACT): `groupBy: {property, path: dotted}`. The oracle is the fixture's own JSON, walked by
// hand here: rows sit at their whole path, a group counts everything under it, direct rows come before child groups.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { rowModel, sectionsOf, groupEntries } from '../../packages/core/src/rowmodel.js';
import { workerEligible } from '../../packages/core/src/rowmodel-worker.js';
import { fastOrder } from '../../packages/core/src/order.js';
import { parseBase } from '../../packages/core/src/base.js';
import { checkText } from '../../packages/core/src/check.js';
import { normalizeDataset } from '../../packages/core/src/data.js';

const url = new URL('../browser/fixtures/table-groups/', import.meta.url);
const data = normalizeDataset(JSON.parse(readFileSync(new URL('params.json', url), 'utf8')));
const base = parseBase(readFileSync(new URL('views.base', url), 'utf8'));
const view = (name) => base.views.find((v) => v.name === name);
const shape = (gs) => gs.map((g) => [g.key, g.rows.map((r) => r.id), ...(g.groups ? [shape(g.groups)] : [])]);
const under = (pred) => data.rows.filter(pred).map((r) => r.id);

test('a dotted path nests to any depth; counts roll up; direct rows lead', () => {
  const m = rowModel(data, base, view('Nested'));
  const servo = m.groups.find((g) => g.key === 'servo');
  assert.deepEqual(m.groups.map((g) => g.key), ['servo', 'motor', null]);
  assert.equal(servo.rows.length, under((r) => String(r.section).split('.')[0] === 'servo').length);
  assert.deepEqual(servo.groups.map((g) => g.key), [null, 'fw', 'pid_position']);
  assert.deepEqual(servo.groups[0].rows.map((r) => r.id), under((r) => r.section === 'servo'));
  assert.equal(servo.groups[0].direct, true);
  const pid = servo.groups[2];
  assert.equal(pid.rows.length, 4);
  assert.deepEqual(pid.groups[0].rows.map((r) => r.id), ['kp', 'ki', 'kd']);
  assert.deepEqual(pid.groups[1].key, 'limits');
  assert.deepEqual(pid.groups[1].path, ['servo', 'pid_position', 'limits']);
  assert.equal(new Set(m.rows.map((r) => r.id)).size, data.rows.length, 'every row once');
});

test('rows come out in drawn order: what shift-select and the peek step through', () => {
  const m = rowModel(data, base, view('Nested'));
  assert.deepEqual(m.rows.map((r) => r.id).slice(0, 8), ['bus_voltage', 'max_current', 'encoder_note', 'fw_version', 'fw_build', 'kp', 'ki', 'kd']);
  assert.equal(m.rows[8].id, 'clamp');
});

test('a list cell is a declared path, the same tree', () => {
  const a = rowModel(data, base, view('Nested')), b = rowModel(data, base, view('Declared'));
  assert.deepEqual(shape(b.groups), shape(a.groups));
});

test('a literal separator', () => {
  const rows = [{ id: 1, s: 'a/b' }, { id: 2, s: 'a' }, { id: 3, s: 'a.b' }];
  const m = rowModel({ rows, properties: { s: { type: 'text' } } }, null, { type: 'table', groupBy: { property: 's', path: '/' } });
  assert.deepEqual(m.groups.map((g) => g.key), ['a', 'a.b']);
  assert.deepEqual(m.groups[0].groups.map((g) => g.key), [null, 'b']);
});

test('backward compatible: no path, the whole value is one group', () => {
  const m = rowModel(data, base, view('Flat'));
  assert.deepEqual(m.groups.map((g) => g.key).sort((a, b) => String(a).localeCompare(String(b))), ['motor', null, 'servo', 'servo.fw', 'servo.pid_position', 'servo.pid_position.limits'].sort((a, b) => String(a).localeCompare(String(b))));
  assert.ok(m.groups.every((g) => !g.groups));
});

test('a kanban keeps whole values: a drop writes the column it lands on', () => {
  const m = rowModel(data, base, view('Board'));
  assert.ok(m.groups.some((g) => g.key === 'servo.fw'));
  assert.ok(m.groups.every((g) => !g.groups));
});

test('sections: H1 the top level, H2 the next, deeper rolled into it, direct rows first', () => {
  const m = rowModel(data, base, view('Sections'));
  const [servo] = sectionsOf(m.groups, m.columns);
  assert.equal(servo.count, 9);
  assert.deepEqual(servo.subs.map((s) => [s.label, s.count]), [[null, 3], ['fw', 2], ['pid_position', 4]]);
});

test('a nav facet lists whole values: a pick filters on what the cell holds', () => {
  const e = groupEntries(data, base, view('Nested'));
  assert.ok(e.some((x) => x.key === 'servo.pid_position' && x.n === 3));
});

test('a path view is built by rowModel, never the fast order', () => {
  const big = { ...data, rows: Array.from({ length: 6000 }, (_, i) => ({ id: i, name: `p${i}`, section: `a.b${i % 3}`, value: i })) };
  assert.equal(workerEligible(big, view('Nested'), data.properties), false);
  assert.equal(fastOrder(big, null, view('Nested')), null);
});

test('the checker: path is valid on a level, and says no beside by or bins', () => {
  const src = (level) => `views:\n  - type: table\n    name: A\n    groupBy: ${level}\n`;
  const errs = (level) => checkText(src(level)).filter((p) => p.level === 'error');
  assert.deepEqual(errs('{ property: s, path: dotted }').map((p) => p.message), []);
  assert.ok(errs('{ property: n, path: dotted, bins: auto }').length > 0);
});
