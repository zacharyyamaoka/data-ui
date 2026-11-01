/* scene3d's pure parts (no DOM, no three): a series' value at the clock's t, and the camera that frames the data.
   Kept apart from the view so node --test runs them as they are (tests/unit/scene3d.test.mjs). */

const finite = (v) => typeof v === 'number' && Number.isFinite(v);

/** One series' samples → at(t): every column linearly interpolated between the two samples around t, clamped to the
    first / last sample outside the span. `read(row, column)` gives a cell's number (rich cells: cellValue). A column
    missing on either neighbour is null at t (never 0, never the other neighbour's value). */
export function sampler(rows, tcol, cols, read = (r, c) => r[c]) {
  const pts = [];
  for (const r of rows) {
    const t = read(r, tcol);
    if (finite(t)) pts.push({ t, v: cols.map((c) => { const x = read(r, c); return finite(x) ? x : null; }) });
  }
  pts.sort((a, b) => a.t - b.t);
  const n = pts.length;
  return {
    n,
    t0: n ? pts[0].t : null,
    t1: n ? pts[n - 1].t : null,
    points: pts,
    at(t) {
      if (!n || !finite(t)) return cols.map(() => null);
      if (t <= pts[0].t) return pts[0].v.slice();
      if (t >= pts[n - 1].t) return pts[n - 1].v.slice();
      let lo = 0, hi = n - 1;   // the last sample at or before t
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid].t <= t) lo = mid; else hi = mid; }
      const a = pts[lo], b = pts[hi];
      if (t === a.t) return a.v.slice();   // on a sample: its own values, whatever its neighbour lacks
      const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
      return a.v.map((x, i) => (x === null || b.v[i] === null ? null : x + (b.v[i] - x) * f));
    },
    /** The two samples around t and how far t is between them ({a, b, f}: values, values, 0..1), as at() picks them;
        null without samples. at(t) is a + (b − a)·f per column; poseAt() slerps the orientations instead. */
    around(t) {
      if (!n || !finite(t)) return null;
      if (t <= pts[0].t) return { a: pts[0].v, b: pts[0].v, f: 0 };
      if (t >= pts[n - 1].t) return { a: pts[n - 1].v, b: pts[n - 1].v, f: 0 };
      let lo = 0, hi = n - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid].t <= t) lo = mid; else hi = mid; }
      const a = pts[lo], b = pts[hi];
      if (t === a.t) return { a: a.v, b: a.v, f: 0 };
      return { a: a.v, b: b.v, f: b.t === a.t ? 0 : (t - a.t) / (b.t - a.t) };
    },
  };
}

/** Spherical linear interpolation between two quaternions in MuJoCo's [w, x, y, z] order, each normalised first and
    taken the short way round (q and −q are one rotation); null when either is missing or zero. */
export function slerp(qa, qb, f) {
  if (!qa || !qb || qa.some((c) => !finite(c)) || qb.some((c) => !finite(c))) return null;
  const la = Math.hypot(...qa), lb = Math.hypot(...qb);
  if (!la || !lb) return null;
  const a = qa.map((c) => c / la);
  let b = qb.map((c) => c / lb);
  let d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  if (d < 0) { b = b.map((c) => -c); d = -d; }
  if (d > 1 - 1e-12) return a;   // the same rotation (to 1e-12): nothing to turn through
  const theta = Math.acos(Math.min(1, d)), s = Math.sin(theta);
  const wa = Math.sin((1 - f) * theta) / s, wb = Math.sin(f * theta) / s;
  return [wa * a[0] + wb * b[0], wa * a[1] + wb * b[1], wa * a[2] + wb * b[2], wa * a[3] + wb * b[3]];
}

/** The columns a meshed robot reads per link (docs/peps/0005-dashboard-cards.md §2b scene3d.robot): its origin in
    metres, then its orientation in MuJoCo's wxyz order. */
export const linkColumns = (link) => ['x', 'y', 'z', 'qw', 'qx', 'qy', 'qz'].map((c) => `${link}_${c}`);

/** Every link's pose at t from a sampler whose columns hold linkColumns(link) for `count` links from column `offset`:
    [{p: [x, y, z], q: [w, x, y, z]}], positions linear and orientations slerped between the two samples around t.
    null when a link lacks a value on either sample (the robot is not drawn at t, never posed from a stale row). */
export function poseAt(smp, t, offset, count) {
  const span = smp.around(t);
  if (!span) return null;
  const { a, b, f } = span;
  const out = [];
  for (let k = 0; k < count; k++) {
    const o = offset + k * 7;
    const p = [0, 1, 2].map((i) => (a[o + i] === null || b[o + i] === null ? null : a[o + i] + (b[o + i] - a[o + i]) * f));
    const q = slerp(a.slice(o + 3, o + 7), b.slice(o + 3, o + 7), f);
    if (p.includes(null) || !q) return null;
    out.push({ p, q });
  }
  return out;
}

/** The axis-aligned box around points ([x, y, z], non-finite ones skipped); null when there are none. */
export function bbox(points) {
  let min = null, max = null;
  for (const p of points) {
    if (!p || !finite(p[0]) || !finite(p[1]) || !finite(p[2])) continue;
    if (!min) { min = p.slice(0, 3); max = p.slice(0, 3); continue; }
    for (let i = 0; i < 3; i++) { if (p[i] < min[i]) min[i] = p[i]; if (p[i] > max[i]) max[i] = p[i]; }
  }
  return min ? { min, max } : null;
}

/** A perspective camera that frames the box: looking at its centre from direction `dir` (with `up` the screen's up),
    at the nearest distance where all eight corners fall inside both fields of view, shrunk by `margin`. */
export function fit(box, fovDeg, aspect, dir, up = [0, 0, 1], margin = 1.1) {
  const center = [0, 1, 2].map((i) => (box.min[i] + box.max[i]) / 2);
  // WHY a floor: one point (or a flat or straight path seen edge on) has no size; frame at least a 3 cm cube
  const half = [0, 1, 2].map((i) => Math.max((box.max[i] - box.min[i]) / 2, 0.015));
  const radius = Math.hypot(...half);
  const unit = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const d = unit(dir);                       // centre → camera
  const right = unit(cross(d.map((c) => -c), up));
  const screenUp = cross(right, d.map((c) => -c));
  const tanV = Math.tan((fovDeg * Math.PI) / 360) / margin;
  const tanH = tanV * aspect;
  // a corner q (from the centre) is in frame when |q·right| ≤ (D − q·d)·tanH and |q·up| ≤ (D − q·d)·tanV
  let distance = radius * 0.5;
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) {
    const q = [sx * half[0], sy * half[1], sz * half[2]];
    distance = Math.max(distance, dot(q, d) + Math.abs(dot(q, right)) / tanH, dot(q, d) + Math.abs(dot(q, screenUp)) / tanV);
  }
  // never inside the box's sphere: the near plane needs room in front of the camera
  distance = Math.max(distance, radius * 1.05);
  const position = center.map((c, i) => c + d[i] * distance);
  return { center, radius, distance, position };
}

/** A tidy grid step for a span: 1, 2 or 5 × 10^k, about `cells` cells across. */
export function niceStep(span, cells = 10) {
  const raw = Math.max(span, 1e-6) / cells;
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

// ------------------------------------------------------------------------------------------------ the stage (CONTRACT §32)

/** traj_compare's density rule (viewer3d.js markerIndices): markers at samples 0, s, 2s, … with s = ⌊n / density⌋
    (at least 1), plus the last sample. 564 samples at density 20: stride 28, 22 markers. */
export function markerIndices(n, density) {
  if (!(n > 0)) return [];
  const s = Math.max(1, Math.floor(n / Math.max(1, density || 1)));
  const out = [];
  for (let i = 0; i < n; i += s) out.push(i);
  if (out[out.length - 1] !== n - 1) out.push(n - 1);
  return out;
}

/** traj_compare's log dial (viewer3d.js): a 0-100 slider position ↔ 4 … 400 markers per path. */
export const densityOfDial = (v) => Math.round(4 * 100 ** (Math.min(100, Math.max(0, v)) / 100));
export const dialOfDensity = (d) => Math.min(100, Math.max(0, (100 * Math.log(Math.max(4, d) / 4)) / Math.log(100)));

/** The six faces for `up: z` (CONTRACT §32): the direction the camera looks and the screen's up. */
const FACES_Z = {
  top: { dir: [0, 0, -1], up: [0, 1, 0] },
  bottom: { dir: [0, 0, 1], up: [0, 1, 0] },
  front: { dir: [0, 1, 0], up: [0, 0, 1] },
  back: { dir: [0, -1, 0], up: [0, 0, 1] },
  left: { dir: [1, 0, 0], up: [0, 0, 1] },
  right: { dir: [-1, 0, 0], up: [0, 0, 1] },
};
export const FACE_NAMES = Object.keys(FACES_Z);
// with up: y each face is turned by the standard (x, y, z) → (x, z, −y): top looks along −y, front along −z, right
// along −x, as three's ViewHelper names them
const turnY = ([x, y, z]) => [x, z, -y];
const clean = (v) => v.map((c) => (Object.is(c, -0) ? 0 : c));

/** A face of the scene: {dir, up}; null for a name that is none. */
export function faceOf(name, up = 'z') {
  const f = FACES_Z[name];
  if (!f) return null;
  return up === 'y' ? { dir: clean(turnY(f.dir)), up: clean(turnY(f.up)) } : { dir: [...f.dir], up: [...f.up] };
}

/** The face a click on a view-cube ball names: the camera goes to that ball's side, so it looks along minus the ball's
    axis. `type` is ViewHelper's sprite type (posX … negZ). */
export function faceOfBall(type, up = 'z') {
  const axis = { posX: [1, 0, 0], negX: [-1, 0, 0], posY: [0, 1, 0], negY: [0, -1, 0], posZ: [0, 0, 1], negZ: [0, 0, -1] }[type];
  if (!axis) return null;
  const dir = axis.map((c) => -c || 0);
  return FACE_NAMES.find((n) => faceOf(n, up).dir.every((c, i) => c === dir[i])) || null;
}

const unitV = (v) => { const l = Math.hypot(...v); return l > 1e-12 ? v.map((c) => c / l) : null; };
const crossV = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dotV = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** The projection key read (CONTRACT §32): {name, ortho, dir, up} with dir and up unit and perpendicular, or the
    perspective default. `{dir, up}`: up defaults to the scene's up axis, or +y when dir lies along it; up is made
    perpendicular to dir. Anything unreadable is perspective (the checkers refuse it at the file). */
export function projectionOf(p, up = 'z') {
  if (typeof p === 'string' && FACES_Z[p]) return { name: p, ortho: true, ...faceOf(p, up) };
  if (p && typeof p === 'object' && Array.isArray(p.dir) && p.dir.length === 3 && p.dir.every(Number.isFinite)) {
    const d = unitV(p.dir);
    if (d) {
      const scene = up === 'y' ? [0, 1, 0] : [0, 0, 1];
      let u = Array.isArray(p.up) && p.up.length === 3 && p.up.every(Number.isFinite) ? p.up : scene;
      if (Math.abs(dotV(unitV(u) || scene, d)) > 1 - 1e-9) u = Math.abs(dotV(scene, d)) > 1 - 1e-9 ? [0, 1, 0] : scene;
      // Gram-Schmidt: the screen's up is the asked up, made perpendicular to the direction the camera looks
      const k = dotV(u, d);
      const uu = unitV(u.map((c, i) => c - k * d[i]));
      if (uu) return { name: 'dir', ortho: true, dir: d, up: uu };
    }
  }
  return { name: 'perspective', ortho: false, dir: null, up: null };
}

/** Whether a projection's screen axes are world axes (a face, or a {dir} along one): its axes can carry ticks. */
export function faceAligned(proj) {
  if (!proj || !proj.ortho) return false;
  const along = (v) => v.filter((c) => Math.abs(c) > 1e-9).length === 1;
  return along(proj.dir) && along(proj.up);
}

/** The screen's right for a camera looking along `dir` with screen up `up`. */
export const rightOf = (dir, up) => crossV(dir, up);

/** An orthographic framing of a box seen along `dir` with screen up `up`, into a plot rectangle inside a canvas
    (CSS px): the world size of one pixel `s` and the world point at the canvas's centre. Equal scale by construction:
    one `s` for both screen axes. `margin` leaves room around the data. */
export function fit2d(box, dir, up, canvas, plot, margin = 1.08) {
  const right = rightOf(dir, up);
  let r0 = Infinity, r1 = -Infinity, u0 = Infinity, u1 = -Infinity, d0 = Infinity, d1 = -Infinity;
  for (const x of [box.min[0], box.max[0]]) for (const y of [box.min[1], box.max[1]]) for (const z of [box.min[2], box.max[2]]) {
    const p = [x, y, z];
    const r = dotV(p, right), u = dotV(p, up), d = dotV(p, dir);
    r0 = Math.min(r0, r); r1 = Math.max(r1, r); u0 = Math.min(u0, u); u1 = Math.max(u1, u); d0 = Math.min(d0, d); d1 = Math.max(d1, d);
  }
  // WHY a floor: one point, or a path seen edge on, has no extent along a screen axis
  const span = Math.max(r1 - r0, u1 - u0, 1e-9);
  const wr = Math.max(r1 - r0, span * 0.02), wu = Math.max(u1 - u0, span * 0.02);
  const s = Math.max(wr / Math.max(1, plot.w), wu / Math.max(1, plot.h)) * margin;
  // the data's centre goes to the plot's centre; the camera sits on the canvas's centre
  const pr = (r0 + r1) / 2 - (plot.x + plot.w / 2 - canvas.w / 2) * s;
  const pu = (u0 + u1) / 2 + (plot.y + plot.h / 2 - canvas.h / 2) * s;
  const depth = Math.max(d1 - d0, span) * 2 + 1e-6;
  const dc = (d0 + d1) / 2;
  const center = [0, 1, 2].map((i) => pr * right[i] + pu * up[i] + dc * dir[i]);
  return { s, center, depth, right };
}

/** A tick label's text: the step's decimals, a true minus sign (U+2212, as the mocks write it). */
export function fmtTick(v, step) {
  const dec = Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
  const text = v.toFixed(dec);
  // a value that rounds to zero is "0", never "−0.0"
  return (Number(text) === 0 ? text.replace('-', '') : text).replace(/^-/, '−');
}

/** The +Z column of a wxyz quaternion's rotation (normalised first); null when it has none. */
export function zAxisOf(q) {
  if (!q || q.some((c) => c === null || !Number.isFinite(c))) return null;
  const l = Math.hypot(...q);
  if (!l) return null;
  const [w, x, y, z] = q.map((c) => c / l);
  return [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)];
}

/** The three axis columns (x, y, z) of a wxyz quaternion's rotation; null when it has none. */
export function axesOf(q) {
  if (!q || q.some((c) => c === null || !Number.isFinite(c))) return null;
  const l = Math.hypot(...q);
  if (!l) return null;
  const [w, x, y, z] = q.map((c) => c / l);
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)],
    [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)],
    [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)],
  ];
}

/** traj_compare's Z-arc (viewer3d.js): from the own Z to the reference Z, `steps` chords along their normalised
    linear interpolation, each point `length` from the origin; [[x, y, z]…] of steps + 1 directions. */
export function arcDirections(own, ref, steps = 10) {
  const out = [];
  for (let k = 0; k <= steps; k++) {
    const f = k / steps;
    const v = [0, 1, 2].map((i) => own[i] * (1 - f) + ref[i] * f);
    const l = Math.hypot(...v) || 1;
    out.push(v.map((c) => c / l));
  }
  return out;
}

/** Natural order of names ("real 2" before "real 10"), for a family's members (CONTRACT §32). */
export const naturalCompare = (a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
