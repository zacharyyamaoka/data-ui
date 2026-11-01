// §15 "Show only selected" meets the perf worker's main-thread fast order (merge of lane/toolbar-mix onto main,
// 2026-10-27): at WORKER_ROWS and up, <data-views> builds a page's model with fastOrder() (order.js), which starts from
// matchedRows(), not from rowModel(). `only` must narrow both the same way, or a big table's "Show only selected"
// would draw every row. Oracle: orderOf(rowModel()) with the same `only`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBase } from '../../packages/core/src/base.js';
import { orderOf, modelFromOrder, WORKER_ROWS } from '../../packages/core/src/rowmodel-worker.js';
import { rowModel, matchedRows } from '../../packages/core/src/rowmodel.js';
import { fastOrder } from '../../packages/core/src/order.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const EX = join(ROOT, 'gallery', 'examples', 'robotparts-actuators');
const actuators = JSON.parse(readFileSync(join(EX, 'actuators.json'), 'utf8'));
const base = parseBase(readFileSync(join(EX, 'views.base'), 'utf8'));
const n = Math.max(WORKER_ROWS, 12000);
const big = { ...actuators, rows: Array.from({ length: n }, (_, i) => ({ ...actuators.rows[i % actuators.rows.length], id: `r${i}` })) };
// a person's picks: every 37th row, plus an id that is not in the data (a stale pick must not invent a row)
const only = new Set([...big.rows.filter((_, i) => i % 37 === 0).map((r) => r.id), 'no-such-row']);

test('matchedRows: only keeps exactly the selected rows that the filters and search keep', () => {
  const all = matchedRows(big, base, { type: 'table' }, {});
  const sel = matchedRows(big, base, { type: 'table' }, { only });
  assert.deepEqual(sel.rows.map((r) => r.id), all.rows.filter((r) => only.has(String(r.id))).map((r) => r.id));
  assert.ok(sel.rows.length > 50 && sel.rows.length < all.rows.length, `${sel.rows.length} of ${all.rows.length}`);
});

test('fastOrder with only: the same rows, groups and counts as rowModel() with only (flat and grouped views)', () => {
  const indexOf = new Map(big.rows.map((r, i) => [r, i]));
  let compared = 0;
  for (const view of base.views.filter((v) => v.type === 'table' && !v.tree)) {
    const opts = { only, query: '' };
    const want = orderOf(big, base, view, opts, indexOf);
    const got = fastOrder(big, base, view, opts);
    if (!got) continue; // a view the fast path declines is built by rowModel() itself
    assert.deepEqual([...got.rows], [...want.rows], view.name);
    assert.equal(got.matched, want.matched, view.name);
    const model = modelFromOrder(big, base, view, got);
    const oracle = rowModel(big, base, view, opts);
    assert.deepEqual(model.rows.map((r) => r.id), oracle.rows.map((r) => r.id), view.name);
    assert.ok(model.rows.every((r) => only.has(String(r.id))), `${view.name}: a row outside the selection`);
    compared++;
  }
  assert.ok(compared >= 5, `${compared} views compared`);
});
