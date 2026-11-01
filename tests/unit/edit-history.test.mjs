// CONTRACT §40: the undo and redo stacks. What the host took moves between them, what it refused stays, so the stacks never
// claim what did not happen; a host's new id is followed everywhere; a new gesture ends redo.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EditHistory } from '../../packages/core/src/edit-history.js';

const edit = (id) => ({ type: 'edit', id, before: { a: 1 }, absent: [], after: { a: 2 } });
const step = (...ops) => ({ label: 'Edit', ops });

test('a new history can do nothing', () => {
  const h = new EditHistory();
  assert.equal(h.canUndo, false);
  assert.equal(h.canRedo, false);
  assert.equal(h.top('undo'), null);
  assert.equal(h.top('redo'), null);
});

test('a step with no ops is no step', () => {
  const h = new EditHistory();
  h.push(step());
  assert.equal(h.canUndo, false);
});

test('undo moves a step to redo, redo moves it back, in order', () => {
  const h = new EditHistory();
  const a = step(edit('a')), b = step(edit('b'));
  h.push(a);
  h.push(b);
  assert.equal(h.top('undo'), b);
  h.settle('undo', b.ops, []);
  assert.equal(h.top('undo'), a);
  assert.deepEqual(h.top('redo').ops, b.ops);
  h.settle('redo', b.ops, []);
  assert.deepEqual(h.top('undo').ops, b.ops);
  assert.equal(h.canRedo, false);
});

test('a new gesture ends redo', () => {
  const h = new EditHistory();
  const a = step(edit('a'));
  h.push(a);
  h.settle('undo', a.ops, []);
  assert.equal(h.canRedo, true);
  h.push(step(edit('b')));
  assert.equal(h.canRedo, false);
});

test('a refusal changes nothing: the step stays, redo is not touched', () => {
  const h = new EditHistory();
  const a = step(edit('a'));
  h.push(a);
  h.settle('undo', [], a.ops);
  assert.equal(h.undo.length, 1);
  assert.deepEqual(h.top('undo').ops, a.ops);
  assert.equal(h.canRedo, false);
});

test('a part taken and a part refused split the step: each stack holds what is true of it', () => {
  const h = new EditHistory();
  const x = edit('x'), y = edit('y'), z = edit('z');
  h.push(step(x, y, z));
  h.settle('undo', [x, z], [y]);
  assert.deepEqual(h.top('undo').ops, [y]);
  assert.deepEqual(h.top('redo').ops, [x, z]);
  assert.equal(h.top('redo').label, 'Edit');
});

test('an op dropped by both lists (its row is gone) leaves the stacks', () => {
  const h = new EditHistory();
  const a = step(edit('a'));
  h.push(a);
  h.settle('undo', [], []);
  assert.equal(h.canUndo, false);
  assert.equal(h.canRedo, false);
});

test('the stack is capped, oldest first', () => {
  const h = new EditHistory(3);
  for (const id of ['a', 'b', 'c', 'd']) h.push(step(edit(id)));
  assert.equal(h.undo.length, 3);
  assert.equal(h.undo[0].ops[0].id, 'b');
});

test('remap follows a host that answers another id, through both stacks and a row kept for later', () => {
  const h = new EditHistory();
  const del = { type: 'delete', rows: [{ row: { id: 'old', a: 1 }, index: 2 }] };
  const a = step(edit('old')), b = step(del);
  h.push(a);
  h.push(b);
  h.push(step(edit('other')));
  h.settle('undo', h.top('undo').ops, []);
  h.remap('old', 'new');
  assert.equal(h.undo[0].ops[0].id, 'new');
  assert.equal(h.undo[1].ops[0].rows[0].row.id, 'new');
  assert.equal(h.redo[0].ops[0].id, 'other');
});
