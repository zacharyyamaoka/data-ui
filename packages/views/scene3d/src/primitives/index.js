/* Layer 1: the 3D primitives (docs/CONTRACT.md §32; docs/peps/0010-robotics-playback.md §5.1). Pure functions from
   paths and items (numbers already read from the rows, see ../bind.js) to three.js objects, one draw call per layer:

     lines   LineStrips3D     LineSegments2 (pixel width): a segment between each two consecutive samples of a path,
                              broken at a missing value, never joined across one
     points  Points3D         Points: the path's markers (the density rule, math.js markerIndices)
     frames  TransformAxes3D  LineSegments2: at each marker the X, Y, Z axes (red, green, blue), or Z alone in the
                              series' colour (traj_compare's z-vector)
     arrows  Arrows3D         LineSegments2 shafts + one InstancedMesh of cones (traj_compare's construction)
     arcs    traj_compare's Z-arc: own Z in colour, the reference Z muted, the normalised-lerp arc between them
     boxes   Boxes3D          LineSegments2: each row's box edges
   (meshes, Asset3D, are robots posed at t: ../robot.js and the view.)

   Every item carries its time (the trail, primitives/window.js), its series (the legend hides a series by zeroing its
   items' alpha: an attribute write, never a rebuild) and its alpha (opacity: auto, opacity). A Prim keeps a CPU copy
   of what it uploaded, so the card's hook reads back exactly what the buffers hold.

   STOCK PARTS: three 0.186.1 LineSegments2 + LineSegmentsGeometry + LineMaterial, Points, InstancedMesh +
   ConeGeometry. OURS: the item lists, the density rule, the Z-arc's chords (math.js). */

import { BufferGeometry, Float32BufferAttribute, InstancedBufferAttribute, Points, InstancedMesh, ConeGeometry, Matrix4, Quaternion, Vector3, Color } from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { lineMaterial, pointsMaterial, instanceMaterial } from './window.js';
import { markerIndices, axesOf, zAxisOf, arcDirections } from '../math.js';

const SOLID = [0, 0, 0, 0];
const ARC_STEPS = 10;   // traj_compare's ARC_STEPS

/** What one primitive object drew: its items' series, times, alphas, and a readback of its buffers. */
export class Prim {
  constructor({ kind, object, series, t, alpha, alphaAttrs, per = 1, read, materials = [], geometries = [] }) {
    this.kind = kind;            // line | points | frames | frames-z | arrows | arcs | boxes
    this.object = object;
    this.series = series;        // per item
    this.t = t;                  // Float64Array: per item [start, end] (absolute times)
    this.base = alpha;           // Float32Array: per item, as built
    this.alphaAttrs = alphaAttrs;
    this.per = per;              // items per drawn unit (a triad is 3 segments, an arc 12)
    this.read = read;            // (i) => {points: [x, y, z]} | {segment: [[x, y, z], [x, y, z]]}
    this.materials = materials;
    this.geometries = geometries;
    this.hidden = new Set();
  }

  get items() { return this.series.length; }

  /** Zero the alpha of every item of a hidden series, restore the rest (an attribute write; nothing is rebuilt). */
  setHidden(hidden) {
    const next = new Set(hidden || []);
    if (next.size === this.hidden.size && [...next].every((s) => this.hidden.has(s))) return;
    this.hidden = next;
    for (const attr of this.alphaAttrs) {
      const a = attr.array;
      for (let i = 0; i < this.series.length; i++) a[i] = next.has(this.series[i]) ? 0 : this.base[i];
      attr.needsUpdate = true;
    }
  }

  /** Whether item i is drawn under the window [lo, hi] (null: unbounded): its time span meets the window, as the
      shader tests it, and its series is shown. */
  shows(i, lo, hi) {
    if (this.hidden.has(this.series[i]) || !(this.base[i] > 0)) return false;
    const a = this.t[2 * i], b = this.t[2 * i + 1];
    return (lo === null || b >= lo) && (hi === null || a <= hi);
  }

  /** {series: drawn units} under the window. */
  count(lo, hi) {
    const out = {};
    for (let i = 0; i < this.series.length; i += this.per) if (this.shows(i, lo, hi)) out[this.series[i]] = (out[this.series[i]] || 0) + 1;
    return out;
  }

  /** The items of one series drawn under the window, read back from the buffers, with their times. */
  geometry(series, lo, hi) {
    const out = [], times = [];
    for (let i = 0; i < this.series.length; i++) {
      if (this.series[i] !== series || !this.shows(i, lo, hi)) continue;
      out.push(this.read(i));
      times.push(this.t[2 * i]);
    }
    return { items: out, times };
  }

  dispose() {
    for (const g of this.geometries) g.dispose();
    for (const m of this.materials) m.dispose();
  }
}

/** Typed arrays for n line items: positions (6 per item), colours (6), times (2), alpha (1), dash (4), dist (2). */
function lineBuffers(n) {
  return { pos: new Float32Array(6 * n), col: new Float32Array(6 * n), time: new Float32Array(2 * n), abs: new Float64Array(2 * n),
    alpha: new Float32Array(n), dash: new Float32Array(4 * n), dist: new Float32Array(2 * n), series: new Array(n), n: 0 };
}

function pushSegment(B, a, b, ta, tb, color, alpha, dash, da, db, series, origin, colorEnd = color) {
  const i = B.n++;
  B.pos.set(a, 6 * i); B.pos.set(b, 6 * i + 3);
  B.col[6 * i] = color.r; B.col[6 * i + 1] = color.g; B.col[6 * i + 2] = color.b;
  B.col[6 * i + 3] = colorEnd.r; B.col[6 * i + 4] = colorEnd.g; B.col[6 * i + 5] = colorEnd.b;
  B.time[2 * i] = ta - origin; B.time[2 * i + 1] = tb - origin;
  B.abs[2 * i] = ta; B.abs[2 * i + 1] = tb;
  B.alpha[i] = alpha;
  B.dash.set(dash || SOLID, 4 * i);
  B.dist[2 * i] = da; B.dist[2 * i + 1] = db;
  B.series[i] = series;
}

/** One LineSegments2 from the buffers (trimmed to the items pushed), on the shared window uniforms. */
function segmentsPrim(kind, B, ctx, { per = 1, width = ctx.lineWidth, material = {} } = {}) {
  if (!B.n) return null;
  const n = B.n;
  const geo = new LineSegmentsGeometry();
  geo.setPositions(B.pos.subarray(0, 6 * n));
  geo.setColors(B.col.subarray(0, 6 * n));
  geo.setAttribute('dvTime', new InstancedBufferAttribute(B.time.slice(0, 2 * n), 2));
  const alpha = new InstancedBufferAttribute(B.alpha.slice(0, n), 1);
  geo.setAttribute('dvAlpha', alpha);
  geo.setAttribute('dvDash', new InstancedBufferAttribute(B.dash.slice(0, 4 * n), 4));
  geo.setAttribute('dvDist', new InstancedBufferAttribute(B.dist.slice(0, 2 * n), 2));
  const mat = lineMaterial(ctx.uniforms, { linewidth: width, ...material });
  const obj = new LineSegments2(geo, mat);
  const pos = geo.attributes.instanceStart.data.array;
  return new Prim({ kind, object: obj, series: B.series.slice(0, n), t: B.abs.slice(0, 2 * n), alpha: B.alpha.slice(0, n), alphaAttrs: [alpha], per,
    read: (i) => ({ segment: [[pos[6 * i], pos[6 * i + 1], pos[6 * i + 2]], [pos[6 * i + 3], pos[6 * i + 4], pos[6 * i + 5]]] }),
    materials: [mat], geometries: [geo] });
}

const finite3 = (p, i) => Number.isFinite(p[3 * i]) && Number.isFinite(p[3 * i + 1]) && Number.isFinite(p[3 * i + 2]);
const at3 = (p, i) => [p[3 * i], p[3 * i + 1], p[3 * i + 2]];
const at4 = (q, i) => (q ? [q[4 * i], q[4 * i + 1], q[4 * i + 2], q[4 * i + 3]] : null);

/** lines: each path's consecutive samples joined, broken at a missing value. `material` for the layer (the target's
    polygon offset). Dashes run on the path's own length (dvDist), in units of ctx.dashUnit.
    A path with `values` (path_overlay, CONTRACT §35) is painted per vertex by ctx.overlayColor(value) → Color: each
    segment runs from its start vertex's colour to its end vertex's (the shader interpolates), and the Prim keeps each
    segment's start value (`values`) for the hook. A vertex with no number wears the path's own colour. */
export function linesPrim(paths, ctx, material = {}) {
  let total = 0;
  for (const p of paths) total += Math.max(0, p.n - 1);
  const B = lineBuffers(total);
  // per segment, the path it belongs to and its series' own name (a family of four or more shares one legend name):
  // what the hook's paths() and opacity() count by
  const pathOf = new Array(total), nameOf = new Array(total);
  const painted = paths.some((p) => p.values) && ctx.overlayColor;
  const startValue = painted ? new Float64Array(total) : null;
  for (const p of paths) {
    let dist = 0;
    const paint = painted && p.values ? (v) => (Number.isFinite(v) ? ctx.overlayColor(v) : p.color) : null;
    for (let i = 0; i + 1 < p.n; i++) {
      if (!finite3(p.p, i) || !finite3(p.p, i + 1)) continue;
      const a = at3(p.p, i), b = at3(p.p, i + 1);
      const len = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
      pathOf[B.n] = p.key;
      nameOf[B.n] = p.seriesName ?? p.series;
      if (startValue) startValue[B.n] = p.values ? p.values[i] : NaN;
      pushSegment(B, a, b, p.t[i], p.t[i + 1], paint ? paint(p.values[i]) : p.color, p.alpha, p.dash, dist, dist + len, p.series, ctx.tOrigin, paint ? paint(p.values[i + 1]) : undefined);
      dist += len;
    }
  }
  const prim = segmentsPrim('line', B, ctx, { width: material.linewidth || ctx.lineWidth, material });
  if (prim) { prim.pathOf = pathOf.slice(0, B.n); prim.nameOf = nameOf.slice(0, B.n); if (startValue) prim.values = startValue.slice(0, B.n); }
  return prim;
}

/** points: a dot at each marker sample of each path (the density rule), in the path's colour. */
export function pointsPrim(paths, ctx) {
  const pos = [], col = [], tt = [], abs = [], alpha = [], series = [];
  for (const p of paths) {
    for (const i of markerIndices(p.n, p.density || ctx.density)) {
      if (!finite3(p.p, i)) continue;
      pos.push(...at3(p.p, i));
      col.push(p.color.r, p.color.g, p.color.b);
      tt.push(p.t[i] - ctx.tOrigin);
      abs.push(p.t[i], p.t[i]);
      alpha.push(p.alpha);
      series.push(p.series);
    }
  }
  if (!series.length) return null;
  const geo = new BufferGeometry();
  geo.setAttribute('position', new Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new Float32BufferAttribute(col, 3));
  geo.setAttribute('dvT', new Float32BufferAttribute(tt, 1));
  const a = new Float32BufferAttribute(alpha, 1);
  geo.setAttribute('dvA', a);
  const mat = pointsMaterial(ctx.uniforms, { size: ctx.pointSize });
  const obj = new Points(geo, mat);
  const P = geo.attributes.position.array;
  return new Prim({ kind: 'points', object: obj, series, t: Float64Array.from(abs), alpha: Float32Array.from(alpha), alphaAttrs: [a],
    read: (i) => ({ point: [P[3 * i], P[3 * i + 1], P[3 * i + 2]] }), materials: [mat], geometries: [geo] });
}

/** frames: at each marker sample, the X, Y, Z axes of its orientation (`axes: xyz`, red, green, blue: RGB = XYZ), or
    the Z axis alone in the path's colour (`axes: z`, traj_compare's z-vector). `length` in the scene's unit. */
export function framesPrim(paths, ctx, axes = 'xyz', length = ctx.length) {
  const kind = axes === 'z' ? 'frames-z' : 'frames';
  let total = 0;
  for (const p of paths) total += markerIndices(p.n, p.density || ctx.density).length * (axes === 'z' ? 1 : 3);
  const B = lineBuffers(total);
  for (const p of paths) {
    for (const i of markerIndices(p.n, p.density || ctx.density)) {
      if (!finite3(p.p, i)) continue;
      const o = at3(p.p, i);
      if (axes === 'z') {
        const z = zAxisOf(at4(p.q, i));
        if (!z) continue;
        pushSegment(B, o, o.map((c, k) => c + z[k] * length), p.t[i], p.t[i], p.color, p.alpha, SOLID, 0, 0, p.series, ctx.tOrigin);
      } else {
        const cols = axesOf(at4(p.q, i));
        if (!cols) continue;
        for (let k = 0; k < 3; k++) pushSegment(B, o, o.map((c, j) => c + cols[k][j] * length), p.t[i], p.t[i], ctx.axisColors[k], p.alpha, SOLID, 0, 0, p.series, ctx.tOrigin);
      }
    }
  }
  return segmentsPrim(kind, B, ctx, { per: axes === 'z' ? 1 : 3, width: ctx.frameWidth });
}

/** arrows: from each item's `from` to `to`, drawn `scale` times as long (display only), a shaft and a cone at the
    head. Items are thinned per path by the density rule before they get here (bind.js). The Prim keeps each drawn
    arrow's numbers as read (`arrows`: from, to, tip, float64), so a check can hold the buffer against them. */
export function arrowsPrim(items, ctx, scale = 1) {
  const B = lineBuffers(items.length);
  const heads = [];
  const drawn = [];
  const coneH = ctx.size * 0.035;
  for (const it of items) {
    // WHY `to` itself at scale 1: from + (to − from) can miss to by an ulp, and the arrow must end on b(t) exactly
    const to = scale === 1 ? it.to.slice() : it.from.map((c, k) => c + (it.to[k] - c) * scale);
    const d = [to[0] - it.from[0], to[1] - it.from[1], to[2] - it.from[2]];
    const len = Math.hypot(...d);
    if (!(len > 1e-9)) continue;
    pushSegment(B, it.from, to, it.t, it.t, it.color, it.alpha, SOLID, 0, 0, it.series, ctx.tOrigin);
    heads.push({ to, dir: d.map((c) => c / len), len, it });
    drawn.push({ series: it.series, t: it.t, from: it.from.slice(), to: it.to.slice(), tip: to });
  }
  const shafts = segmentsPrim('arrows', B, ctx, { width: ctx.frameWidth });
  if (!shafts) return null;
  shafts.arrows = drawn;
  shafts.scale = scale;
  // the heads: one InstancedMesh of cones, each at most half its arrow's length (traj_compare's rule)
  const geo = new ConeGeometry(coneH * 0.35, coneH, 8);
  const mat = instanceMaterial(ctx.uniforms);
  const mesh = new InstancedMesh(geo, mat, heads.length);
  const m = new Matrix4(), q = new Quaternion(), yUp = new Vector3(0, 1, 0), v = new Vector3(), s = new Vector3();
  const tt = new Float32Array(heads.length), aa = new Float32Array(heads.length);
  heads.forEach((h, i) => {
    v.set(...h.dir);
    q.setFromUnitVectors(yUp, v);
    const height = Math.min(coneH, h.len * 0.5);
    const k = height / coneH;
    m.compose(new Vector3(h.to[0] - h.dir[0] * height / 2, h.to[1] - h.dir[1] * height / 2, h.to[2] - h.dir[2] * height / 2), q, s.set(k, k, k));
    mesh.setMatrixAt(i, m);
    mesh.setColorAt(i, h.it.color);
    tt[i] = h.it.t - ctx.tOrigin;
    aa[i] = h.it.alpha;
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  geo.setAttribute('dvT', new InstancedBufferAttribute(tt, 1));
  const headAlpha = new InstancedBufferAttribute(aa, 1);
  geo.setAttribute('dvA', headAlpha);
  shafts.object.add(mesh);
  // one hide writes both: the shafts' alpha and the heads' (one item each, in the same order)
  shafts.alphaAttrs.push(headAlpha);
  shafts.materials.push(mat);
  shafts.geometries.push(geo);
  shafts.cones = mesh;
  return shafts;
}

/** arcs (traj_compare's Z-arc): at each item's `at`, the own Z (`own` quaternion) in the item's colour, the reference
    Z (`ref`) muted, and the normalised-lerp arc between their tips, ARC_STEPS chords, `length` from `at`. */
export function arcsPrim(items, ctx, length = ctx.length) {
  const B = lineBuffers(items.length * (2 + ARC_STEPS));
  const drawn = [];
  for (const it of items) {
    const own = zAxisOf(it.own), ref = zAxisOf(it.ref);
    if (!own || !ref) continue;
    const tip = (d) => it.at.map((c, k) => c + d[k] * length);
    pushSegment(B, it.at, tip(own), it.t, it.t, it.color, it.alpha, SOLID, 0, 0, it.series, ctx.tOrigin);
    pushSegment(B, it.at, tip(ref), it.t, it.t, ctx.muted, it.alpha, SOLID, 0, 0, it.series, ctx.tOrigin);
    const dirs = arcDirections(own, ref, ARC_STEPS);
    for (let k = 0; k < ARC_STEPS; k++) pushSegment(B, tip(dirs[k]), tip(dirs[k + 1]), it.t, it.t, it.color, it.alpha, SOLID, 0, 0, it.series, ctx.tOrigin);
    drawn.push({ series: it.series, t: it.t, at: it.at.slice(), own: it.own.slice(), ref: it.ref.slice() });
  }
  const prim = segmentsPrim('arcs', B, ctx, { per: 2 + ARC_STEPS, width: ctx.frameWidth });
  // each drawn arc's numbers as read (its anchor, a's and b's quaternions), one per 2 + ARC_STEPS items, in order
  if (prim) prim.arcs = drawn;
  return prim;
}

/** boxes: each item's twelve edges, min to max corner (Rerun's Boxes3D). */
export function boxesPrim(items, ctx) {
  const B = lineBuffers(items.length * 12);
  for (const it of items) {
    const [x0, y0, z0] = it.min, [x1, y1, z1] = it.max;
    const c = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]];
    for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]) {
      pushSegment(B, c[a], c[b], it.t, it.t, it.color, it.alpha, SOLID, 0, 0, it.series, ctx.tOrigin);
    }
  }
  return segmentsPrim('boxes', B, ctx, { per: 12, width: ctx.frameWidth });
}

/** A CSS colour as three's (linear) Color, which a vertex colour holds. */
export const colorOf = (css) => new Color(css);
