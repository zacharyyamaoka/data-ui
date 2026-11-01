// Row selection and the bulk actions (docs/CONTRACT.md §15): click / shift / toggle / shift+toggle ranges in drawn
// order, set() modes, the default actions and their min/max, the cancelable action event, and RFC 4180 CSV.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Selection, DEFAULT_ACTIONS, resolveActions, runAction } from '../../packages/core/src/toolbar/selection.js';
import { csvField, toCsv } from '../../packages/core/src/toolbar/csv.js';

const ORDER = Array.from({ length: 20 }, (_, i) => `r${i + 1}`);

test('click: plain replaces, shift takes the range from the anchor in drawn order, toggle adds or removes one', () => {
  const s = new Selection(null);
  assert.equal(s.click('r3', {}, ORDER), true);
  assert.deepEqual([...s.ids], ['r3']);
  s.click('r8', { shift: true }, ORDER);
  assert.deepEqual([...s.ids].sort(), ORDER.slice(2, 8).sort());
  assert.equal(s.ids.size, 6);
  s.click('r12', { toggle: true }, ORDER);
  assert.equal(s.ids.size, 7);
  s.click('r15', { shift: true, toggle: true }, ORDER);
  assert.equal(s.ids.size, 10);
  assert.deepEqual(ORDER.filter((id) => s.ids.has(id)), [...ORDER.slice(2, 8), 'r12', 'r13', 'r14', 'r15']);
  // a plain shift range replaces what was there; the anchor stays at the last plain or toggle click (r12), as in Finder
  s.click('r13', { shift: true }, ORDER);
  assert.deepEqual(ORDER.filter((id) => s.ids.has(id)), ['r12', 'r13']);
  assert.equal(s.click('r15', { toggle: true }, ORDER), true);
  assert.deepEqual(ORDER.filter((id) => s.ids.has(id)), ['r12', 'r13', 'r15']);
  s.click('r12', { toggle: true }, ORDER);
  assert.deepEqual(ORDER.filter((id) => s.ids.has(id)), ['r13', 'r15']);
  assert.equal(s.click('r15', {}, ORDER), true);
  assert.equal(s.click('r15', {}, ORDER), false, 'no change returns false');
  // a shift-click with no anchor in the drawn rows is a plain click
  const t = new Selection(null);
  t.click('r5', { shift: true }, ORDER);
  assert.deepEqual([...t.ids], ['r5']);
});

test('set: replace, add, toggle, remove; retain drops ids a filter hid', () => {
  const s = new Selection(null);
  s.set(['a', 'b'], 'replace');
  s.set(['c'], 'add');
  s.set(['a', 'd'], 'toggle');
  assert.deepEqual([...s.ids].sort(), ['b', 'c', 'd']);
  s.set(['c'], 'remove');
  s.retain(new Set(['b', 'x']));
  assert.deepEqual([...s.ids], ['b']);
  s.clear();
  assert.equal(s.ids.size, 0);
});

test('the default actions, and resolveActions: strings name a default, objects are the host\'s, min / max disable with a reason', () => {
  assert.deepEqual(DEFAULT_ACTIONS.map((a) => a.id), ['compare', 'copy-ids', 'export-csv', 'clear']);
  const cmp = DEFAULT_ACTIONS.find((a) => a.id === 'compare');
  assert.deepEqual([cmp.min, cmp.max], [2, 6]);
  assert.deepEqual(resolveActions(null).map((a) => a.id), ['compare', 'copy-ids', 'export-csv', 'clear']);
  const mine = { id: 'tag', label: 'Tag', run() {} };
  const list = resolveActions(['export-csv', mine, 'nope', 'compare'], 1);
  assert.deepEqual(list.map((a) => a.id), ['export-csv', 'tag', 'compare']);
  assert.equal(list[2].disabled, true);
  assert.match(list[2].reason, /2/);
  assert.equal(list[0].disabled, false);
  assert.equal(resolveActions(['compare'], 7)[0].disabled, true);
  assert.match(resolveActions(['compare'], 7)[0].reason, /6/);
  assert.equal(resolveActions(['compare'], 3)[0].disabled, false);
});

test('compare switches the current view to a compare of the ids, through el.update (so Reset brings the view back)', () => {
  let view = { type: 'table', name: 'Rows', order: ['model'] };
  const el = { update(change) { const next = JSON.parse(JSON.stringify(view)); change(next); view = next; } };
  DEFAULT_ACTIONS.find((a) => a.id === 'compare').run([{ id: 'a' }, { id: 'b' }, { id: 'c' }], el);
  assert.deepEqual(view, { type: 'compare', name: 'Rows', order: ['model'], compare: { rows: ['a', 'b', 'c'] } });
});

test('runAction dispatches the cancelable data-views-action first; preventDefault skips run', () => {
  const seen = [];
  const make = (cancel) => ({
    selection: ['a', 'b'], selectedRows: [{ id: 'a' }, { id: 'b' }],
    dispatchEvent(e) { seen.push([e.type, e.detail.id, e.detail.ids, e.cancelable]); if (cancel) e.preventDefault(); return !e.defaultPrevented; },
  });
  let ran = 0;
  const action = { id: 'tag', label: 'Tag', run(rows) { ran += rows.length; } };
  assert.equal(runAction(make(false), action), true);
  assert.equal(runAction(make(true), action), false);
  assert.equal(ran, 2);
  assert.deepEqual(seen, [['data-views-action', 'tag', ['a', 'b'], true], ['data-views-action', 'tag', ['a', 'b'], true]]);
  assert.equal(runAction(make(false), { ...action, disabled: true }), false, 'a disabled action never runs');
});

test('CSV: RFC 4180 quoting, CRLF lines, units in headers, lists joined, missing empty', () => {
  assert.equal(csvField('plain'), 'plain');
  assert.equal(csvField('a,b'), '"a,b"');
  assert.equal(csvField('say "hi"'), '"say ""hi"""');
  assert.equal(csvField('two\nlines'), '"two\nlines"');
  assert.equal(csvField(' lead'), ' lead');
  assert.equal(csvField(null), '');
  assert.equal(csvField(3.5), '3.5');
  const columns = {
    model: { id: 'model', label: 'Model' }, peak_torque: { id: 'peak_torque', label: 'Peak torque', unitText: 'N·m' },
    buses: { id: 'buses', label: 'Bus', type: 'list' }, note: { id: 'note', label: 'Note, free' },
  };
  const rows = [
    { id: 'a', model: 'GIM "4305"', peak_torque: { value: 3.82, basis: 'seller' }, buses: ['can', 'rs485'], note: null },
    { id: 'b', model: 'AK80', peak_torque: 12, buses: [], note: 'x\r\ny' },
  ];
  assert.equal(toCsv(rows, columns, ['model', 'peak_torque', 'buses', 'note']),
    'Model,Peak torque (N·m),Bus,"Note, free"\r\n"GIM ""4305""",3.82,"can, rs485",\r\nAK80,12,,"x\r\ny"\r\n');
});
