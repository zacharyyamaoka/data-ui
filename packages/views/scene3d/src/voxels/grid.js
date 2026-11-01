/* The voxel grid (docs/CONTRACT.md §32, type: voxels; docs/peps/0010-robotics-playback.md §5.3): rows binned into
   cells. Numbers in, numbers out, no three.js and no import (tests/unit/voxels.test.mjs; the browser checks hold the
   drawn cells to numpy.histogramdd, tests/browser/p2_checks.py).

   Raw rows (value: count | time | runs) bin on cells anchored at the frame's origin: along each axis cell k spans
   [k·cell, (k + 1)·cell), the edges being the float64 products k·cell, so a value on an edge is in the cell it starts
   (numpy.histogramdd's rule). WHY the origin: two views of one frame share their cells, and a cell reads "x 100-125 mm".
   Pre-gridded rows (value: <property>; BAM Reach's map, the contract's grid.json) are cells already: they bin on their
   own lattice (origin = the smallest centre − cell / 2), so each row's centre stays its cell's centre.

   value: count   rows per cell (the default)
          time    Σ w ÷ hz: the seconds spent there (w, default column `w`, is 1 on the time grid and 0 on a run's kept
                  extremes, PEP 0010 §4.4; a row without one weighs 1)
          runs    distinct values of `run` per cell: how many runs passed here (the exact count 1/n opacity cannot give)
          <prop>  the rows' own value, summarised per cell by Bases' names (Average by default, Median, Min, Max, Sum)
   `drop` bins with one axis dropped: slice `at: all`, a 2D histogram of the projection (count and time sum through the
   depth; runs counts a run once per column, which a sum of the cells' counts would not). */

export const AXES = ['x', 'y', 'z'];
export const SUMMARIES = ['Average', 'Median', 'Min', 'Max', 'Sum'];

const finite = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** The cell holding v: the k with origin + k·cell ≤ v < origin + (k + 1)·cell, the edges as float64 computes them. */
export function cellIndex(v, cell, origin = 0) {
  let k = Math.floor((v - origin) / cell);
  // WHY step: (v − origin) / cell rounds, and the edges are the products, not the quotient; numpy compares v with them
  while (k > -1e15 && origin + k * cell > v) k--;
  while (k < 1e15 && origin + (k + 1) * cell <= v) k++;
  return k;
}

/** What the view's keys ask for: {kind: count | time | runs | property, property, summary, w, run, hz}. */
export function valueOf(spec) {
  const v = spec && spec.value;
  const kind = v === undefined || v === null || v === '' || v === 'count' ? 'count' : v === 'time' ? 'time' : v === 'runs' ? 'runs' : 'property';
  return {
    kind, property: kind === 'property' ? String(v) : null,
    summary: SUMMARIES.includes(spec && spec.summary) ? spec.summary : 'Average',
    w: (spec && spec.w) || 'w', run: (spec && spec.run) || 'run', hz: spec && typeof spec.hz === 'number' ? spec.hz : null,
  };
}

const summarise = {
  Average: (xs) => { let s = 0; for (const x of xs) s += x; return s / xs.length; },
  Sum: (xs) => { let s = 0; for (const x of xs) s += x; return s; },
  Min: (xs) => { let m = Infinity; for (const x of xs) if (x < m) m = x; return m; },
  Max: (xs) => { let m = -Infinity; for (const x of xs) if (x > m) m = x; return m; },
  Median: (xs) => { const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; },
};

/** Rows → {cell, origin, value, property, summary, drop, cells: [{i, j, k, value, n}] (by k, j, i), lo, hi (index
    bounds), domain: [min(0, smallest), largest], rows (binned), skipped (a coordinate missing), problem}. `read(row,
    column)` reads a cell (the view passes the core's cellValue, so a rich {value} cell reads as its number). */
export function voxelGrid(rows, spec, { drop = null, read = (r, c) => r[c] } = {}) {
  const val = valueOf(spec);
  const cell = spec && typeof spec.cell === 'number' ? spec.cell : NaN;
  const out = { cell, origin: [0, 0, 0], value: val.kind, property: val.property, summary: val.summary, drop: AXES.includes(drop) ? drop : null,
    cells: [], lo: null, hi: null, domain: [0, 0], rows: 0, skipped: 0, problem: null };
  if (!(cell > 0)) { out.problem = 'voxels needs cell: the edge of a cell, in the scene\'s unit'; return out; }
  if (val.kind === 'time' && !(val.hz > 0)) { out.problem = 'value: time needs hz, the rows\' display rate (seconds = Σ w ÷ hz)'; return out; }
  const cols = [spec.x, spec.y, spec.z];
  if (cols.some((c) => typeof c !== 'string' || !c)) { out.problem = 'voxels needs x, y and z columns'; return out; }
  const kept = [];
  for (const r of rows || []) {
    const p = [finite(read(r, cols[0])), finite(read(r, cols[1])), finite(read(r, cols[2]))];
    if (p[0] === null || p[1] === null || p[2] === null) { out.skipped++; continue; }
    kept.push([p, r]);
  }
  out.rows = kept.length;
  // a pre-gridded file's own lattice: its smallest centre is a cell's centre
  if (val.kind === 'property' && kept.length) {
    for (let a = 0; a < 3; a++) {
      let m = Infinity;
      for (const [p] of kept) if (p[a] < m) m = p[a];
      out.origin[a] = m - cell / 2;
    }
  }
  const d = out.drop ? AXES.indexOf(out.drop) : -1;
  const acc = new Map();
  for (const [p, r] of kept) {
    const idx = [0, 1, 2].map((a) => (a === d ? 0 : cellIndex(p[a], cell, out.origin[a])));
    const key = `${idx[0]},${idx[1]},${idx[2]}`;
    let c = acc.get(key);
    if (!c) acc.set(key, (c = { i: idx[0], j: idx[1], k: idx[2], n: 0, w: 0, runs: null, xs: null }));
    c.n++;
    if (val.kind === 'time') { const w = finite(read(r, val.w)); c.w += w === null ? 1 : w; }
    else if (val.kind === 'runs') { const run = read(r, val.run); if (run !== null && run !== undefined && run !== '') (c.runs || (c.runs = new Set())).add(String(run)); }
    else if (val.kind === 'property') { const v = finite(read(r, val.property)); if (v !== null) (c.xs || (c.xs = [])).push(v); }
  }
  const cells = [];
  for (const c of acc.values()) {
    let value;
    if (val.kind === 'count') value = c.n;
    else if (val.kind === 'time') value = c.w / val.hz;
    else if (val.kind === 'runs') value = c.runs ? c.runs.size : 0;
    else { if (!c.xs) continue; value = summarise[val.summary](c.xs); }
    cells.push({ i: c.i, j: c.j, k: c.k, value, n: c.n });
  }
  cells.sort((a, b) => a.k - b.k || a.j - b.j || a.i - b.i);
  out.cells = cells;
  if (cells.length) {
    out.lo = [Infinity, Infinity, Infinity];
    out.hi = [-Infinity, -Infinity, -Infinity];
    let vmin = Infinity, vmax = -Infinity;
    for (const c of cells) {
      const ix = [c.i, c.j, c.k];
      for (let a = 0; a < 3; a++) { if (ix[a] < out.lo[a]) out.lo[a] = ix[a]; if (ix[a] > out.hi[a]) out.hi[a] = ix[a]; }
      if (c.value < vmin) vmin = c.value;
      if (c.value > vmax) vmax = c.value;
    }
    out.domain = [Math.min(0, vmin), vmax];
  }
  return out;
}

/** The cell index along `axis` that holds the coordinate `at`. */
export function kOf(grid, axis, at) {
  const a = AXES.indexOf(axis);
  return cellIndex(at, grid.cell, grid.origin[a]);
}

/** The plane of cells with index `k` along `axis`, over the grid's whole extent on the other two axes (so stepping keeps
    the image's size): {axis, k, plane: [u, v] (the in-plane axes in x, y, z order), i0, j0, width, height, values:
    height rows of width (row 0 at j0, the low end of v), null where no cell}. A grid binned with `drop` is its own
    plane at k 0. */
export function planeOf(grid, axis, k) {
  const a = AXES.indexOf(axis);
  const [u, v] = [0, 1, 2].filter((x) => x !== a);
  if (!grid.cells.length) return { axis, k, plane: [AXES[u], AXES[v]], i0: 0, j0: 0, width: 0, height: 0, values: [] };
  const i0 = grid.lo[u], j0 = grid.lo[v];
  const width = grid.hi[u] - i0 + 1, height = grid.hi[v] - j0 + 1;
  const values = Array.from({ length: height }, () => new Array(width).fill(null));
  for (const c of grid.cells) {
    const ix = [c.i, c.j, c.k];
    if (ix[a] !== k) continue;
    values[ix[v] - j0][ix[u] - i0] = c.value;
  }
  return { axis, k, plane: [AXES[u], AXES[v]], i0, j0, width, height, values };
}

/** A cell's centre along one axis. */
export const centreOf = (grid, a, index) => grid.origin[a] + (index + 0.5) * grid.cell;
