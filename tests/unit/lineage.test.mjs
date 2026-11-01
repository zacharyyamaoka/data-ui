// The lineage view's pure half (packages/views/lineage/src/layout.js): rows + the view's lineage: block -> a laid-out
// tree of life. The oracle here is written out by hand per case, never computed with the module's own helpers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lineageSpec, analyse, buildLineage } from '../../packages/views/lineage/src/layout.js';

const row = (id, parents, extra = {}) => ({ id, parents, ...extra });
// a      b (kept)       z (a second root)
// ├─ c   └─ d
// │  └─ e (parents: c, d: a splice)
// └─ f (extinct leaf)   └─ g (extinct leaf, its parent is extinct too: z)
const ROWS = [
  row('a', [], { gen: 1, status: 'neutral' }),
  row('b', [], { gen: 1, status: 'liked' }),
  row('z', [], { gen: 1, status: 'neutral' }),
  row('c', ['a'], { gen: 2, status: 'neutral' }),
  row('d', ['b'], { gen: 2, status: 'neutral' }),
  row('f', ['a'], { gen: 2, status: 'rejected' }),
  row('g', ['z'], { gen: 2, status: 'neutral' }),
  row('e', ['c', 'd', 'nope'], { gen: 3, status: 'picked' }),
];
const VIEW = { lineage: { parents: 'parents', x: 'gen', focus: 'e', kept: { status: ['picked', 'liked'] }, extinct: 'collapse' } };
const pairs = (list) => list.map((e) => `${e.from}>${e.to}`).sort();

test('lineageSpec: defaults and the keys as written', () => {
  const s = lineageSpec({ lineage: { parents: 'p' } });
  assert.equal(s.parents, 'p');
  assert.equal(s.layout, 'rectangular');
  assert.equal(s.extinct, 'collapse');
  assert.equal(s.kept, null);
  assert.equal(lineageSpec({ lineage: { parents: 'p', layout: 'radial', extinct: 'show' } }).layout, 'radial');
  assert.equal(lineageSpec({}).parents, null);
});

test('analyse: parents only from the property; ids not among the rows are dropped and counted', () => {
  const an = analyse(ROWS, lineageSpec(VIEW));
  assert.deepEqual(an.parents.get('e'), ['c', 'd']);
  assert.equal(an.missing, 1);
  assert.equal(an.primary.get('e'), 'c');
  assert.equal(an.primary.get('a'), null);
});

test('analyse: the trunk is the focus and every ancestor over all parents; alive = kept, trunk or an alive descendant', () => {
  const an = analyse(ROWS, lineageSpec(VIEW));
  assert.deepEqual([...an.golden].sort(), ['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual([...an.alive].sort(), ['a', 'b', 'c', 'd', 'e']);
  const noKept = analyse(ROWS, lineageSpec({ lineage: { parents: 'parents' } }));
  assert.equal(noKept.alive.size, ROWS.length, 'no kept: nothing is extinct');
});

test('analyse: a parent cycle is cut where it closes, and both rows still draw', () => {
  const an = analyse([row('p', ['q']), row('q', ['p'])], lineageSpec({ lineage: { parents: 'parents' } }));
  const primaries = ['p', 'q'].map((id) => an.primary.get(id));
  assert.equal(primaries.filter((p) => p === null).length, 1);
  const t = buildLineage([row('p', ['q']), row('q', ['p'])], lineageSpec({ lineage: { parents: 'parents' } }));
  assert.equal(t.nodes.filter((n) => n.kind === 'row').length, 2);
  assert.equal(t.edges.length + t.splices.length, 1, 'the closing edge is not drawn');
  assert.equal(t.cut, 1);
});

test('buildLineage, show: every row is a node; edges are exactly the parent pairs; the splice is the extra parent', () => {
  const t = buildLineage(ROWS, lineageSpec(VIEW), { extinct: 'show' });
  assert.deepEqual(t.nodes.filter((n) => n.kind === 'row').map((n) => n.id).sort(), ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'z']);
  assert.deepEqual(pairs(t.edges), ['a>c', 'a>f', 'b>d', 'c>e', 'z>g']);
  assert.deepEqual(pairs(t.splices), ['d>e']);
  assert.deepEqual(pairs(t.edges.filter((e) => e.type === 'golden')), ['a>c', 'b>d', 'c>e']);
  assert.deepEqual(pairs(t.edges.filter((e) => e.type === 'extinct')), ['a>f', 'z>g']);
  assert.equal(t.splices[0].golden, true);
});

test('buildLineage, collapse: extinct rows fold into "+N" under their parent; the counts add up', () => {
  const t = buildLineage(ROWS, lineageSpec(VIEW));
  assert.deepEqual(t.nodes.filter((n) => n.kind === 'row').map((n) => n.id).sort(), ['a', 'b', 'c', 'd', 'e']);
  const groups = t.nodes.filter((n) => n.kind === 'group').map((n) => [n.parentId, n.count, n.rows.slice().sort()]).sort();
  // f folds under a; z (an extinct root) and its g fold into one "+2" at the top
  assert.deepEqual(groups, [[null, 2, ['g', 'z']], ['a', 1, ['f']]]);
  assert.equal(t.counts.hidden, 3);
  assert.deepEqual(pairs(t.edges), ['a>c', 'b>d', 'c>e'], 'no edge to a folded row and none to a group');
});

test('buildLineage, rectangular: x is one column per distinct x value, in order', () => {
  const t = buildLineage(ROWS, lineageSpec(VIEW), { extinct: 'show' });
  const at = (id) => t.nodes.find((n) => n.id === id);
  assert.equal(at('a').x, at('b').x);
  assert.ok(at('c').x > at('a').x && at('e').x > at('c').x);
  assert.equal(at('c').col, 2);
  assert.deepEqual(t.ticks.map((k) => k.value), [1, 2, 3]);
});

test('buildLineage, no x: the column is the depth in the tree', () => {
  const t = buildLineage(ROWS, lineageSpec({ lineage: { parents: 'parents' } }));
  const at = (id) => t.nodes.find((n) => n.id === id);
  assert.equal(at('a').idx, 1);
  assert.equal(at('e').idx, 3);
});

test('buildLineage, radial: a ring per column around the root, radius growing outward', () => {
  const t = buildLineage(ROWS, lineageSpec({ lineage: { ...VIEW.lineage, layout: 'radial', extinct: 'show' } }));
  const r = (n) => Math.hypot(n.x, n.y);
  const byIdx = new Map();
  for (const n of t.nodes.filter((x) => x.kind === 'row')) byIdx.set(n.idx, [...(byIdx.get(n.idx) || []), r(n)]);
  const rings = [...byIdx.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
  for (const v of rings) assert.ok(Math.max(...v) - Math.min(...v) < 1e-6);
  assert.ok(rings[0][0] < rings[1][0] && rings[1][0] < rings[2][0]);
  assert.ok(t.splices[0].d.startsWith('M'));
});

test('buildLineage: rows in any order lay out the same', () => {
  const a = buildLineage(ROWS, lineageSpec(VIEW), { extinct: 'show' });
  const b = buildLineage([...ROWS].reverse(), lineageSpec(VIEW), { extinct: 'show' });
  assert.deepEqual(pairs(a.edges), pairs(b.edges));
  assert.deepEqual(pairs(a.splices), pairs(b.splices));
});

test('buildLineage: a chain inside one column stacks (no two marks on one spot); its edges stay parent to child', () => {
  const rows = [row('m2', [], { r: 2 }), row('m4', ['m2'], { r: 4 }), row('c1', ['m4'], { r: 4 }), row('soft', ['c1', 'm2'], { r: 4 })];
  for (const layout of ['rectangular', 'radial']) {
    const t = buildLineage(rows, lineageSpec({ lineage: { parents: 'parents', x: 'r', layout } }));
    const at = t.nodes.filter((n) => n.kind === 'row').map((n) => `${n.x.toFixed(3)},${n.y.toFixed(3)}`);
    assert.equal(new Set(at).size, 4, `${layout}: ${at}`);
    assert.deepEqual(pairs(t.edges), ['c1>soft', 'm2>m4', 'm4>c1']);
    assert.deepEqual(pairs(t.splices), ['m2>soft']);
    assert.equal(t.nodes.find((n) => n.id === 'c1').idx, t.nodes.find((n) => n.id === 'm4').idx);
  }
});

// WHY signatures, not shapes: Zach, 2026-10-28, "I am just not a fan of how you are using different line shapes like
// straight vs curved." A link's shape is the sequence of SVG path commands that draws it, so a tree edge (was M V H),
// a "+N" stub and a splice (was a bezier) must all be the same one.
const commands = (d) => d.replace(/[-\d.,e\s]+/g, '');
test('buildLineage: every link (tree edge, "+N" stub, splice) is the same curve, in both layouts', () => {
  for (const layout of ['rectangular', 'radial']) {
    for (const extinct of ['show', 'collapse']) {
      const t = buildLineage(ROWS, lineageSpec({ lineage: { ...VIEW.lineage, layout, extinct } }));
      const links = [...t.edges, ...t.stubs, ...t.splices];
      assert.ok(t.edges.length && t.splices.length, `${layout}/${extinct}: has edges and a splice`);
      if (extinct === 'collapse') assert.ok(t.stubs.length, `${layout}/${extinct}: has a stub`);
      const shapes = new Set(links.map((l) => commands(l.d)));
      assert.deepEqual([...shapes], ['MC'], `${layout}/${extinct}: one move and one cubic curve each, got ${[...shapes]}`);
    }
  }
});

test('lineageSpec and buildLineage: extinct lines are folded into "+N" unless the view says show (Zach, 2026-10-28)', () => {
  const noExtinctKey = { lineage: { parents: 'parents', x: 'gen', focus: 'e', kept: { status: ['picked', 'liked'] } } };
  assert.equal(lineageSpec(noExtinctKey).extinct, 'collapse');
  assert.equal(lineageSpec({ lineage: { ...noExtinctKey.lineage, extinct: 'nonsense' } }).extinct, 'collapse');
  const t = buildLineage(ROWS, lineageSpec(noExtinctKey));
  assert.equal(t.extinct, 'collapse');
  assert.equal(t.counts.groups, 2);
  assert.equal(t.counts.hidden, 3);
  assert.deepEqual(t.nodes.filter((n) => n.kind === 'row').map((n) => n.id).sort(), ['a', 'b', 'c', 'd', 'e'], 'no extinct row is a mark');
  assert.equal(buildLineage(ROWS, lineageSpec({ lineage: { ...noExtinctKey.lineage, extinct: 'show' } })).counts.groups, 0);
});
