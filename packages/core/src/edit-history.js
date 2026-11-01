/* The undo and redo stacks of an edit session (docs/CONTRACT.md §40). Pure, so tests/unit/edit-history.test.mjs holds it.

   A step is one reader's gesture: {label, ops}. An op is what one change did and what it takes to undo it, in the order it
   happened. WHY settle() takes two lists: a host may take part of a step and refuse the rest, and the stacks must say what is true
   of each part afterwards. What it took moves to the other stack, what it refused stays; an op in neither (its row has gone) leaves. */

export class EditHistory {
  constructor(limit = 100) {
    this.limit = limit;
    this.undo = []; // oldest first
    this.redo = [];
  }

  get canUndo() { return this.undo.length > 0; }
  get canRedo() { return this.redo.length > 0; }

  /** A new gesture: on top, and whatever was undone can no longer be reached. */
  push(step) {
    if (!step.ops.length) return;
    this.undo.push(step);
    if (this.undo.length > this.limit) this.undo.shift();
    this.redo = [];
  }

  /** The step an undo or a redo would replay, or null. */
  top(dir) {
    const list = dir === 'undo' ? this.undo : this.redo;
    return list.length ? list[list.length - 1] : null;
  }

  /** A replay of the top step has ended: `done` (ops, in their order) crosses over, `left` stays, the rest leave. */
  settle(dir, done, left) {
    const from = dir === 'undo' ? this.undo : this.redo;
    const to = dir === 'undo' ? this.redo : this.undo;
    const step = from.pop();
    if (left.length) from.push({ ...step, ops: left });
    if (done.length) to.push({ ...step, ops: done });
  }

  /** A host answered another id for a row: every step names the new one from now on. */
  remap(from, to) {
    const a = String(from), b = String(to);
    for (const step of [...this.undo, ...this.redo]) {
      for (const op of step.ops) {
        if (String(op.id) === a) op.id = b;
        for (const r of op.rows || []) if (String(r.row.id) === a) r.row.id = b;
      }
    }
  }
}
