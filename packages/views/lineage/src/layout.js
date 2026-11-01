/* type: lineage, the pure half: rows + the view's `lineage:` block -> a laid-out tree of life. No DOM.

   Ported from Brandbook's v3-phylogeny (src/variants/v3-phylogeny/layout.ts, React + d3-hierarchy, one brand at a
   time) and made generic: any rows, any parents property, any ordinal x.

   STOCK PARTS: d3-hierarchy 3.1.2 (`hierarchy` + `cluster`: the leaf spacing and the parent-at-the-mean placement),
   d3-shape 3.2.0 (`linkHorizontal` / `linkRadial`: every link's curve). OURS: which parent is the tree parent, alive vs
   extinct, folding extinct fans into "+N", the x column, the radial rings.

   Rules (docs/CONTRACT.md §21):
   - Edges come only from `lineage.parents`, a property listing other rows' ids (feedback_do_not_invent_undefined_
     relationships). An id no shown row has is dropped and counted (`missing`); nothing joins the roots: the forest's
     roots hang from an undrawn root, and no line is drawn to it.
   - The first listed parent is the tree parent; every further one is a splice. Every link is the same curve; only a
     splice is dashed, because that is data (a second parent), not decoration. A parent
     cycle is cut where it closes (in row order), as the table's tree: is (§10).
   - The trunk ("golden path") is `focus` and every ancestor over all parents.
   - With `kept: {property: [values]}`, a row is alive when it is kept, on the trunk, or has an alive child (over any
     parent); otherwise extinct. Without `kept` nothing is extinct. `extinct: collapse` folds a node's extinct
     children (and their subtrees, which are extinct too) into one "+N"; `show` draws them as thin stubs.
   - x: one column per distinct value of `lineage.x` (numbers in numeric order, text in natural order); a row with no
     value sits one column right of its tree parent. Without `x`, the column is the depth. */

import { cluster, hierarchy } from 'd3-hierarchy';
import { linkHorizontal, linkRadial } from 'd3-shape';

// WHY injected, not imported: this file stays free of the host so node --test can load it (tests/unit/lineage.test.mjs);
// the view hands it the core's own readers (useCore in index.js), so there is still one copy at run time. The
// defaults are the core's definitions (grammar.js cellValue, format.js isEmpty).
let cellValue = (v) => (v !== null && typeof v === 'object' && !Array.isArray(v) && 'value' in v ? v.value : v);
let isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
export function useCore(core) { ({ cellValue, isEmpty } = core); }

export const ROW = 26; // px: the pitch between neighbouring leaves (rectangular)
export const COL = 132; // px: the pitch between columns (rectangular)
const GAP = 0.8; // radians left open at 3 o'clock for the ring labels (radial)
const A0 = Math.PI / 2 + GAP / 2;
const A1 = Math.PI / 2 + 2 * Math.PI - GAP / 2;
const R0 = 120; // px: the first ring's radius
export const ROOT = '__root';

const str = (v) => (typeof v === 'string' && v ? v : null);
const list = (v) => { const x = cellValue(v); return isEmpty(x) ? [] : Array.isArray(x) ? x : [x]; };
const natural = (a, b) => (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true }));

/** The view's `lineage:` block, with its defaults. */
export function lineageSpec(view) {
  const l = (view && typeof view.lineage === 'object' && view.lineage) || {};
  let kept = null;
  if (l.kept && typeof l.kept === 'object' && !Array.isArray(l.kept)) {
    kept = {};
    for (const [p, v] of Object.entries(l.kept)) kept[p] = (Array.isArray(v) ? v : [v]).map(String);
    if (!Object.keys(kept).length) kept = null;
  }
  return {
    parents: str(l.parents), x: str(l.x), xLabel: str(l.xLabel), image: str(l.image), label: str(l.label),
    focus: l.focus == null || l.focus === '' ? null : String(l.focus), kept,
    extinct: l.extinct === 'show' ? 'show' : 'collapse',
    layout: l.layout === 'radial' ? 'radial' : 'rectangular',
  };
}

/** Parents, the tree parent, children, the trunk and alive, from the rows alone. */
export function analyse(rows, spec) {
  const ids = rows.map((r) => String(r.id));
  const idSet = new Set(ids);
  const byId = new Map(rows.map((r) => [String(r.id), r]));
  const parents = new Map();
  let missing = 0;
  for (const r of rows) {
    const id = String(r.id);
    const out = [];
    for (const p of spec.parents ? list(r[spec.parents]) : []) {
      const pid = String(p);
      if (!idSet.has(pid)) { missing++; continue; }
      if (pid !== id && !out.includes(pid)) out.push(pid);
    }
    parents.set(id, out);
  }
  // the tree parent: the first listed; a cycle of tree parents is cut at its first row (in row order)
  const primary = new Map(ids.map((id) => [id, parents.get(id)[0] ?? null]));
  let cut = 0;
  for (const id of ids) {
    const seen = new Set([id]);
    for (let p = primary.get(id); p != null; p = primary.get(p)) {
      if (p === id) { parents.set(id, parents.get(id).filter((x) => x !== primary.get(id))); primary.set(id, null); cut++; break; }
      if (seen.has(p)) break;
      seen.add(p);
    }
  }
  const kids = new Map(); // tree children, '' = the roots
  const anyKids = new Map();
  for (const id of ids) {
    const k = primary.get(id) ?? '';
    if (!kids.has(k)) kids.set(k, []);
    kids.get(k).push(id);
    for (const p of parents.get(id)) { if (!anyKids.has(p)) anyKids.set(p, []); anyKids.get(p).push(id); }
  }
  const golden = new Set();
  if (spec.focus != null && idSet.has(spec.focus)) {
    const todo = [spec.focus];
    golden.add(spec.focus);
    while (todo.length) for (const p of parents.get(todo.pop())) if (!golden.has(p)) { golden.add(p); todo.push(p); }
  }
  const keptRow = (r) => Object.entries(spec.kept).some(([p, vals]) => list(r[p]).some((v) => vals.includes(String(v))));
  let alive;
  if (!spec.kept) alive = new Set(ids);
  else {
    alive = new Set();
    const memo = new Map();
    const walk = (id, stack) => {
      if (memo.has(id)) return memo.get(id);
      if (stack.has(id)) return false;
      stack.add(id);
      const on = keptRow(byId.get(id)) || golden.has(id) || (anyKids.get(id) || []).some((c) => walk(c, stack));
      stack.delete(id);
      memo.set(id, on);
      return on;
    };
    for (const id of ids) if (walk(id, new Set())) alive.add(id);
  }
  return { ids, idSet, byId, parents, primary, kids, anyKids, golden, alive, missing, cut };
}

/** The laid-out tree: nodes (root, row, group), tree edges, splices, column ticks, rings, bounds and counts. */
export function buildLineage(rows, spec, opts = {}) {
  const extinctMode = opts.extinct || spec.extinct;
  const kind = opts.layout || spec.layout;
  const an = analyse(rows, spec);

  // columns
  const idxOf = new Map();
  const ticks = [];
  if (spec.x) {
    const values = [];
    const seen = new Set();
    for (const r of rows) { const v = cellValue(r[spec.x]); if (!isEmpty(v) && !Array.isArray(v) && !seen.has(String(v))) { seen.add(String(v)); values.push(v); } }
    values.sort(natural);
    const col = new Map(values.map((v, i) => [String(v), i + 1]));
    const labels = new Map();
    for (const r of rows) {
      const v = cellValue(r[spec.x]);
      if (isEmpty(v) || Array.isArray(v)) continue;
      const lab = spec.xLabel ? cellValue(r[spec.xLabel]) : null;
      const k = String(v);
      const text = isEmpty(lab) ? String(v) : String(lab);
      labels.set(k, labels.has(k) && labels.get(k) !== text ? String(v) : text);
    }
    const place = (id, guard = 0) => {
      if (idxOf.has(id)) return idxOf.get(id);
      const v = cellValue(an.byId.get(id)[spec.x]);
      const p = an.primary.get(id);
      const i = !isEmpty(v) && !Array.isArray(v) ? col.get(String(v)) : p != null && guard < 1e4 ? place(p, guard + 1) + 1 : 1;
      idxOf.set(id, i);
      return i;
    };
    for (const id of an.ids) place(id);
    values.forEach((v, i) => ticks.push({ idx: i + 1, value: v, label: labels.get(String(v)) }));
  } else {
    const depth = (id) => { if (idxOf.has(id)) return idxOf.get(id); const p = an.primary.get(id); const d = p == null ? 1 : depth(p) + 1; idxOf.set(id, d); return d; };
    for (const id of an.ids) depth(id);
  }
  const nCols = Math.max(1, ...idxOf.values(), ...ticks.map((t) => t.idx));
  // WHY from the stage's width when the view knows it: x is ordinal, so the columns may share the width the reader has
  // (a fixed pitch over 18 rounds fitted a 900 px stage at a third of the size, marks 7 px across)
  // label marks need room for their text; picture marks only for the picture
  const COLX = opts.width ? Math.max(spec.image ? 56 : 96, Math.min(200, (opts.width - 60) / (nCols + 1))) : COL;
  if (!spec.x) for (let i = 1; i <= nCols; i++) ticks.push({ idx: i, value: i, label: String(i) });

  // the hierarchy: visible children, the heaviest in the middle, folded fans as "+N"
  const subtree = new Map();
  const size = (id) => { if (subtree.has(id)) return subtree.get(id); const n = 1 + (an.kids.get(id) || []).reduce((s, c) => s + size(c), 0); subtree.set(id, n); return n; };
  const rowsUnder = (id) => [id, ...(an.kids.get(id) || []).flatMap(rowsUnder)];
  const visible = (id) => extinctMode === 'show' || an.alive.has(id);
  const groups = new Map();
  // WHY the heaviest child in the middle and the lighter ones dealt to either side (the donor's rule): a cluster layout
  // puts a parent at the mean of its children, so the surviving line stays nearly level instead of a tall bus
  const middle = (items) => {
    const sorted = [...items].sort((a, b) => b.w - a.w);
    const heavy = sorted.shift();
    if (!heavy) return [];
    const left = [];
    const right = [];
    sorted.forEach((k, i) => (i % 2 === 0 ? left : right).push(k.d));
    return [...left.reverse(), heavy.d, ...right];
  };
  // WHY hoisting: a child in its parent's own column (three M4 models in a chain, all rung 4) would sit exactly on its
  // parent, since a cluster puts an only child at its parent's height. It is placed as its parent's sibling instead, so
  // the column stacks them; its edge is still drawn from its real parent (below), so nothing about the data changes.
  const colOf = (id) => (id === ROOT ? 0 : idxOf.get(id));
  const datum = (id) => {
    const all = an.kids.get(id === ROOT ? '' : id) || [];
    const shownKids = all.filter(visible).map(datum);
    const hidden = all.filter((c) => !visible(c));
    const blocks = [];
    const up = [];
    for (const c of shownKids) {
      if (id !== ROOT && colOf(c.d.id) <= colOf(id)) up.push(c.d, ...c.up);
      else blocks.push({ d: c.d, w: c.w, extra: c.up });
    }
    const out = middle(blocks).flatMap((b) => [b, ...blocks.find((x) => x.d === b).extra]);
    if (hidden.length) {
      const gid = `+${id}`;
      const hiddenRows = hidden.flatMap(rowsUnder);
      groups.set(gid, { parentId: id === ROOT ? null : id, rows: hiddenRows, count: hidden.reduce((s, c) => s + size(c), 0) });
      out.push({ id: gid, kids: [] });
    }
    const w = 1 + blocks.reduce((s, k) => s + k.w + k.extra.length, 0) + (hidden.length ? 1 : 0);
    return { d: { id, kids: out }, w, up };
  };
  const top = datum(ROOT);
  const root = hierarchy(top.d, (d) => d.kids);
  cluster().nodeSize([ROW, 1]).separation((a, b) => (a.parent === b.parent ? 1 : 1.4))(root);
  const all = root.descendants();
  const bx = all.map((d) => d.x);
  const xmin = Math.min(...bx);
  const xmax = Math.max(...bx);
  const leafCount = all.filter((d) => !d.children).length;

  const rNeeded = (leafCount * ROW * 1.15) / (A1 - A0);
  const step = Math.max(46, (rNeeded - R0) / Math.max(1, nCols - 1));
  const angPer = xmax > xmin ? (A1 - A0) / (xmax - xmin) : 0;
  // each ring at least far enough out that its two closest marks are MIN_ARC apart, and 46 beyond the ring inside it.
  // WHY per ring: a parent sits at the mean of its children, so an inner ring can hold two marks far closer in angle
  // than one leaf pitch; one radius for every ring (the donor's) drew those marks 1 px across
  const MIN_ARC = 14;
  const angleOf = (d) => (xmax > xmin ? A0 + (d.x - xmin) * angPer : (A0 + A1) / 2);
  const idxOfDatum = (d) => {
    const id = d.data.id;
    if (id === ROOT) return 0;
    const g = groups.get(id);
    return g ? Math.min(nCols + 1, (g.parentId == null ? 0 : idxOf.get(g.parentId)) + 1) : idxOf.get(id);
  };
  const byRing = new Map();
  for (const d of all) { const i = idxOfDatum(d); if (i) { if (!byRing.has(i)) byRing.set(i, []); byRing.get(i).push(angleOf(d)); } }
  const radii = [0];
  for (let i = 1; i <= nCols + 1; i++) {
    const as = (byRing.get(i) || []).sort((p, q) => p - q);
    let gap = Infinity;
    for (let k = 1; k < as.length; k++) if (as[k] - as[k - 1] > 1e-9) gap = Math.min(gap, as[k] - as[k - 1]);
    const need = Number.isFinite(gap) ? MIN_ARC / gap : 0;
    radii[i] = Math.max(i === 1 ? R0 : radii[i - 1] + 46, R0 + (i - 1) * step, need);
  }
  const ringR = (idx) => radii[idx] ?? 0;
  const pt = (a, r) => [r * Math.sin(a), -r * Math.cos(a)];

  const nodes = [];
  const byId = new Map();
  for (const d of all) {
    const id = d.data.id;
    const isRoot = id === ROOT;
    const g = groups.get(id);
    const idx = isRoot ? 0 : g ? Math.min(nCols + 1, (g.parentId == null ? 0 : idxOf.get(g.parentId)) + 1) : idxOf.get(id);
    const a = xmax > xmin ? A0 + (d.x - xmin) * angPer : (A0 + A1) / 2;
    const r = ringR(idx);
    const [x, y] = kind === 'rectangular' ? [idx * COLX, d.x - xmin] : pt(a, r);
    const n = {
      id, kind: isRoot ? 'root' : g ? 'group' : 'row', row: an.byId.get(id) || null, idx,
      col: isRoot ? null : g ? null : (ticks.find((t) => t.idx === idx) || {}).value ?? idx,
      x, y, a, r,
      size: ROW - 4,
      alive: isRoot || (!g && an.alive.has(id)), golden: an.golden.has(id), focus: id === spec.focus,
      count: g ? g.count : 0, rows: g ? g.rows : null, parentId: g ? g.parentId : null, parent: null,
    };
    if (g) n.col = idx;
    nodes.push(n);
    byId.set(id, n);
  }
  for (const d of all) if (d.parent) byId.get(d.data.id).parent = byId.get(d.parent.data.id);
  // a mark's size: at most ROW - 4, and never more than 85 % of the gap to its nearest neighbour in its column (ring).
  // WHY measured per mark: a parent sits at the mean of its children, so two parents can be closer than one leaf
  // pitch, and on an inner ring the arc between neighbours is short
  const breadth = new Map(all.map((d) => [d.data.id, d.x]));
  const cols = new Map();
  for (const n of nodes) if (n.kind !== 'root') { if (!cols.has(n.idx)) cols.set(n.idx, []); cols.get(n.idx).push(n); }
  for (const list of cols.values()) {
    list.sort((a, b) => breadth.get(a.id) - breadth.get(b.id));
    list.forEach((n, i) => {
      const gaps = [list[i - 1], list[i + 1]].filter(Boolean).map((m) => Math.max(Math.abs(m.x - n.x), Math.abs(m.y - n.y))); // the marks are upright squares: the larger axis gap is what keeps two apart
      n.size = Math.min(ROW - 4, ...gaps.map((g) => g * 0.85));
    });
  }

  // WHY one curve for every link (tree edge, "+N" stub and splice alike): Zach, 2026-10-28, on the brand lineage: "I am
  // just not a fan of how you are using different line shapes like straight vs curved." The tree edges were right-angle
  // elbows and the splices bezier curves. A curve wins over the elbow because a splice (the one link that must read as
  // its own) drawn as an elbow runs back along its sibling edge's horizontal, where a dashed line hides under a solid
  // one; and a vertical elbow bar strikes through the labels of the marks it passes. Stock d3-shape links, so rectangular
  // and radial share one shape in both layouts.
  const hLine = linkHorizontal();
  const rLine = linkRadial().angle((d) => d.a).radius((d) => d.r);
  const linkPath = (p, c) => (kind === 'rectangular' ? hLine({ source: [p.x, p.y], target: [c.x, c.y] }) : rLine({ source: p, target: c }));
  // tree edges: never from the undrawn root (no inferred edge)
  // a "+N" hangs from its parent by a stub: drawn, but not an edge of the data (it stands for several)
  const edges = [];
  const stubs = [];
  for (const n of nodes) {
    // the drawn parent is the data's (the tree parent, or a group's), never the hierarchy's: a hoisted row's
    // hierarchy parent is its grandparent
    const p = n.kind === 'group' ? (n.parentId == null ? null : byId.get(n.parentId)) : n.kind === 'row' ? byId.get(an.primary.get(n.id)) : null;
    if (!p) continue;
    if (n.kind === 'group') { stubs.push({ id: `${p.id}>${n.id}`, from: p.id, to: n.id, d: linkPath(p, n) }); continue; }
    const type = !n.alive ? 'extinct' : n.golden && p.golden ? 'golden' : 'branch';
    edges.push({ id: `${p.id}>${n.id}`, from: p.id, to: n.id, type, d: linkPath(p, n) });
  }
  const rank = { extinct: 0, branch: 1, golden: 2 };
  edges.sort((a, b) => rank[a.type] - rank[b.type]);

  const splices = [];
  for (const n of nodes) {
    if (n.kind !== 'row') continue;
    const prim = an.primary.get(n.id);
    for (const pid of an.parents.get(n.id)) {
      const p = byId.get(pid);
      if (pid === prim || !p || p.kind !== 'row') continue;
      const d = linkPath(p, n);
      splices.push({ id: `${pid}~${n.id}`, from: pid, to: n.id, golden: p.golden && n.golden, extinct: !p.alive || !n.alive, d });
    }
  }

  const ys = nodes.map((n) => n.y);
  const R = ringR(nCols) + 30;
  const bounds = kind === 'rectangular'
    ? { x0: -20, x1: (nCols + 1) * COLX, y0: Math.min(...ys) - 44, y1: Math.max(...ys) + 20 }
    : { x0: -R - 20, x1: R + 90, y0: -R - 20, y1: R + 20 };
  for (const t of ticks) Object.assign(t, kind === 'rectangular' ? { x: t.idx * COLX, y: bounds.y0 + 16 } : { x: ringR(t.idx) + 4, y: 0, r: ringR(t.idx) });
  const rowNodes = nodes.filter((n) => n.kind === 'row');
  const groupNodes = nodes.filter((n) => n.kind === 'group');
  return {
    kind, extinct: extinctMode, colPx: kind === 'rectangular' ? COLX : null, nodes, byId, edges, stubs, splices, ticks, bounds, analysis: an, cut: an.cut,
    counts: { rows: rows.length, shown: rowNodes.length, groups: groupNodes.length, hidden: groupNodes.reduce((s, g) => s + g.count, 0),
      extinct: rows.length - an.alive.size, edges: edges.length, splices: splices.length, missing: an.missing, cut: an.cut },
  };
}
