// treeRows({parent}) in linear time, with the same output as before. The parent-cycle cut used to walk every row's
// ancestors from scratch, so a chain of n rows cost n²/2 steps (1,000 / 2,000 / 4,000 rows: 47 / 151 / 649 ms in the
// 2026-10-26 performance review). Oracle: that walk, verbatim, kept below; compared on the gallery's real trees and on
// random parent graphs full of cycles. The cost is counted in Map lookups, not milliseconds, so machine load cannot
// flip it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { treeRows, treeSpec, properties } from '../../packages/core/src/rowmodel.js';
import { parseBase } from '../../packages/core/src/base.js';
import { normalizeDataset } from '../../packages/core/src/data.js';
import { cellValue } from '../../packages/core/src/grammar.js';
import { isEmpty } from '../../packages/core/src/format.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

// the parent branch of treeRows as it was at main 0dbc3d4: the oracle
function oracle(rows, spec) {
  const children = new Map();
  const roots = [];
  const add = (parent, node) => { if (!parent) roots.push(node); else { if (!children.has(parent)) children.set(parent, []); children.get(parent).push(node); } };
  const byId = new Map(rows.map((r) => [String(r.id), r]));
  const up = new Map();
  for (const r of rows) {
    const p = cellValue(r[spec.parent]);
    const pid = isEmpty(p) ? null : String(Array.isArray(p) ? p[0] : p);
    if (pid && pid !== String(r.id) && byId.has(pid)) up.set(r, byId.get(pid));
  }
  for (const r of [...up.keys()]) {
    const seen = new Set([r]);
    for (let at = up.get(r); at; at = up.get(at)) { if (seen.has(at)) { up.delete(r); break; } seen.add(at); }
  }
  for (const r of rows) add(up.get(r) || null, r);
  return { roots, children };
}

// rows are objects; name them by their place in `rows` so two outputs compare even with repeated ids
const shape = (rows, { roots, children }) => {
  const at = new Map(rows.map((r, i) => [r, i]));
  return { roots: roots.map((r) => at.get(r)), children: [...children].map(([p, list]) => [at.get(p), list.map((r) => at.get(r))]) };
};

function lookups(fn) {
  const get = Map.prototype.get;
  let n = 0;
  Map.prototype.get = function (k) { n++; return get.call(this, k); };
  try { fn(); } finally { Map.prototype.get = get; }
  return n;
}

const chain = (n) => Array.from({ length: n }, (_, i) => ({ id: `n${i}`, parent: i ? `n${i - 1}` : null }));

test('the gallery\'s real trees (dataclass-viewer, vibetracks-feature-tree): every tree view, the same roots and children as before', () => {
  let compared = 0;
  for (const name of ['dataclass-viewer', 'vibetracks-feature-tree']) {
    const dir = join(ROOT, 'gallery', 'examples', name);
    const base = parseBase(readFileSync(join(dir, 'views.base'), 'utf8'));
    const data = normalizeDataset(JSON.parse(readFileSync(join(dir, base.data), 'utf8')));
    const props = properties(data, base);
    for (const view of base.views) {
      const spec = treeSpec({ type: 'table', ...view }, props);
      if (!spec || !spec.parent) continue;
      const want = shape(data.rows, oracle(data.rows, spec));
      assert.deepEqual(shape(data.rows, treeRows(data.rows, spec)), want, `${name} / ${view.name}`);
      assert.ok(want.children.length > 0, `${name} / ${view.name} nests`);
      compared++;
    }
  }
  assert.ok(compared >= 4, `${compared} tree views compared`);
});

test('random parent graphs with cycles, self-parents, missing parents and repeated ids: the same output as before (2,000 graphs)', () => {
  let seed = 7;
  const rand = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  let cut = 0;
  for (let g = 0; g < 2000; g++) {
    const n = 1 + Math.floor(rand() * 40);
    const ids = Math.max(1, Math.floor(n * (0.7 + rand() * 0.5)));
    const rows = Array.from({ length: n }, () => {
      const x = rand();
      return { id: `k${Math.floor(rand() * ids)}`, parent: x < 0.15 ? null : x < 0.2 ? 'gone' : x < 0.25 ? [`k${Math.floor(rand() * ids)}`] : `k${Math.floor(rand() * ids)}` };
    });
    const spec = { parent: 'parent' };
    const want = shape(rows, oracle(rows, spec));
    assert.deepEqual(shape(rows, treeRows(rows, spec)), want, JSON.stringify(rows));
    cut += want.roots.length;
  }
  assert.ok(cut > 2000, 'the graphs have roots to compare');
});

test('a chain\'s cost grows linearly: 4,000 rows take about 4x the Map lookups of 1,000 (it was 16x), and the output is the chain', () => {
  const spec = { parent: 'parent' };
  const cost = (n) => lookups(() => treeRows(chain(n), spec));
  const [a, b] = [cost(1000), cost(4000)];
  assert.ok(b < 5 * a && b < 40 * 4000, `1,000 rows: ${a} lookups; 4,000 rows: ${b}`);
  const rows = chain(4000);
  const out = treeRows(rows, spec);
  assert.deepEqual(out.roots, [rows[0]]);
  assert.equal(out.children.get(rows[3998])[0], rows[3999]);
});

test('a 150,000-row chain and a 150,000-row cycle nest without a deep recursion', () => {
  const rows = chain(150000);
  assert.equal(treeRows(rows, { parent: 'parent' }).children.size, 149999);
  rows[0].parent = 'n149999';
  const out = treeRows(rows, { parent: 'parent' });
  // the cycle is cut where it closes: the first row in row order loses its parent
  assert.deepEqual(out.roots, [rows[0]]);
  assert.equal(out.children.size, 149999);
});
