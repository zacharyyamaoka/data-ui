/* The stage both 3D views share (docs/CONTRACT.md §32; docs/peps/0010-robotics-playback.md §5.1): the camera, its
   projection, the view cube, the 2D axes.

   - perspective orbits (OrbitControls, as PEP 0005 built it); a face or a {dir} is orthographic: drag pans, the wheel
     zooms about the pointer, a double-click fits, nothing rotates, and the scale is equal by construction (one world
     size per pixel for both screen axes).
   - The view cube is three r186's ViewHelper (Q1's default), drawn through the page's one WebGL context into a corner
     of the card's own canvas (+0 contexts); a click on a ball turns the camera to that side and, at the end of the
     turn, makes it orthographic. "Fit" and "3D" sit under it.
   - On a face-aligned 2D view, axes in the scene's unit: tick labels at their values' projections, titled with the
     axis, the unit and the frame ("x (mm) · frame: base"), the grid behind the canvas.

   WHY our own turn and face table, not ViewHelper's handleClick/update: ViewHelper's targets are y-up (its +X ball
   leaves a z-up scene rolled 90°), and the contract names each face's screen up (top: +y; the four sides: the scene's
   up). ViewHelper still draws the cube and holds the balls a click is tested against.

   STOCK PARTS: three 0.186.1 PerspectiveCamera, OrthographicCamera, OrbitControls (orthographic zoom to the cursor),
   ViewHelper, Raycaster. OURS: the face table and the turn (math.js faceOf, faceOfBall), the 2D fit (math.js fit2d),
   the ticks (math.js niceStep, fmtTick). */

import { PerspectiveCamera, OrthographicCamera, Vector2, Vector3, Quaternion, Matrix4, Raycaster, MOUSE, TOUCH } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { ViewHelper } from 'three/examples/jsm/helpers/ViewHelper.js';
import { fit, fit2d, niceStep, fmtTick, projectionOf, faceAligned, faceOfBall, rightOf } from './math.js';
import { esc } from '@data-ui/core';

export const FOV = 35;
// WHY these directions: a three-quarter view from the front-right and above, the way RViz and MuJoCo's viewer open,
// so a robot reads as a robot (its reach in depth, its height up) on the first frame
export const VIEW = { z: [0.55, -1, 0.5], y: [0.55, 0.5, 1] };
export const UP = { z: [0, 0, 1], y: [0, 1, 0] };
const CUBE_PX = 128;   // ViewHelper's fixed viewport (its `dim`)
const TURN_MS = 380;
const AXES = ['x', 'y', 'z'];

export class Stage {
  /** canvas: the card's 2D canvas; cube: the [data-cube] element over the corner the cube is drawn in; axes: the
      labels' box; grid: the <svg> behind the canvas; changed(): the camera moved (redraw, re-project). */
  constructor({ canvas, cube, axes, grid, changed, picked }) {
    this.canvas = canvas;
    this.cubeEl = cube;
    this.axesEl = axes;
    this.gridEl = grid;
    this.changed = changed;
    this.picked = picked;
    this.persp = new PerspectiveCamera(FOV, 1, 0.001, 1000);
    this.ortho = new OrthographicCamera(-1, 1, 1, -1, 0, 1000);
    this.camera = this.persp;
    this.proj = projectionOf('perspective');
    this.up = 'z';
    this.box = null;
    this.fitted = false;
    this.userCam = false;
    this.animating = false;
    this.s2d = 1;          // world units per CSS px at zoom 1 (orthographic)
    this.unit = 'm';
    this.frame = null;
    this.axesMode = 'auto';
    this.margins = { left: 12, right: 12, top: 30, bottom: 12 };
    // the cube: ViewHelper renders into a fixed 128 px viewport at the left of the element it is given; a stand-in
    // element of exactly that size puts it at the corner overlay() copies from
    this.helper = new ViewHelper(this.camera, { offsetWidth: CUBE_PX, offsetHeight: CUBE_PX, getBoundingClientRect: () => ({ left: 0, top: 0 }) });
    this.helper.setLabels('X', 'Y', 'Z');
    this.cubeCam = new OrthographicCamera(-2, 2, 2, -2, 0, 4);
    this.cubeCam.position.set(0, 0, 2);
    this.cubeCam.updateMatrixWorld();
    this.ray = new Raycaster();
    this._onCube = (e) => {
      if (this.animating) return;
      const ball = this.pickBall(e.clientX, e.clientY);
      if (ball) this.picked(ball);
    };
    cube.addEventListener('click', this._onCube);
    this._controls();
  }

  destroy() {
    this.cubeEl.removeEventListener('click', this._onCube);
    if (this.controls) this.controls.dispose();
    cancelAnimationFrame(this._turnRaf);
    this.helper.dispose();
  }

  // ------------------------------------------------------------------------------------------------ controls
  _controls() {
    if (this.controls) this.controls.dispose();
    const cam = this.camera;
    // before OrbitControls: it reads the up axis once, when it is made
    cam.up.set(...(this.proj.ortho ? this.proj.up : UP[this.up]));
    const c = new OrbitControls(cam, this.canvas);
    c.enableDamping = false;   // damping needs a frame loop; without it every input renders once
    if (this.proj.ortho) {
      c.enableRotate = false;
      c.screenSpacePanning = true;
      c.zoomToCursor = true;
      c.minZoom = 0.02;
      c.maxZoom = 500;
      c.mouseButtons = { LEFT: MOUSE.PAN, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.PAN };
      c.touches = { ONE: TOUCH.PAN, TWO: TOUCH.DOLLY_PAN };
    }
    c.addEventListener('change', () => this.changed());
    c.addEventListener('start', () => { this.userCam = true; });
    // WHY pan-y: OrbitControls takes every touch (touch-action: none); on a phone a vertical swipe over the card must
    // still scroll the dashboard, so only a sideways drag orbits (or pans) there
    this.canvas.style.touchAction = 'pan-y';
    if (this.box && this.target) c.target.copy(this.target);
    this.controls = c;
  }

  setUp(up) {
    if (up === this.up) return;
    this.up = up;
    this.proj = projectionOf(this.wanted ?? 'perspective', up);
    this._switch();
  }

  /** The projection the view entry asks for (a face, {dir, up}, perspective); applied at once unless the camera is
      turning (the turn's end applies the latest). */
  want(projection) {
    this.wanted = projection;
    if (this.animating) return;
    const next = projectionOf(projection, this.up);
    if (sameProj(next, this.proj)) return;
    this.proj = next;
    this._switch();
  }

  _switch() {
    this.camera = this.proj.ortho ? this.ortho : this.persp;
    this.helper.camera = this.camera;
    this._controls();
    this.fitted = false;
    this.fit();
  }

  setBox(box) {
    this.box = box;
  }

  // ------------------------------------------------------------------------------------------------ fitting
  size() { return { w: this.canvas.clientWidth, h: this.canvas.clientHeight }; }

  /** The plot rectangle a 2D view frames its data in (CSS px): the canvas less room for the legend, the cube's row
      and the axes. */
  plot() {
    const { w, h } = this.size();
    const ticks = this.proj.ortho && this.axesMode !== 'none' && faceAligned(this.proj);
    const m = { left: ticks ? 52 : 12, right: 14, top: this.margins.top, bottom: ticks ? 40 : 12 };
    return { x: m.left, y: m.top, w: Math.max(20, w - m.left - m.right), h: Math.max(20, h - m.top - m.bottom) };
  }

  fit() {
    const { w, h } = this.size();
    if (!this.box || !w || !h) return false;
    this.userCam = false;
    if (this.proj.ortho) {
      const f = fit2d(this.box, this.proj.dir, this.proj.up, { w, h }, this.plot());
      this.s2d = f.s;
      const cam = this.ortho;
      cam.left = -w / 2 * f.s; cam.right = w / 2 * f.s; cam.top = h / 2 * f.s; cam.bottom = -h / 2 * f.s;
      cam.zoom = 1;
      cam.near = 0;
      cam.far = f.depth * 2;
      cam.up.set(...this.proj.up);
      cam.position.set(...f.center.map((c, i) => c - this.proj.dir[i] * f.depth));
      cam.lookAt(...f.center);
      cam.updateProjectionMatrix();
      this.target = new Vector3(...f.center);
      this.controls.target.copy(this.target);
      this.controls.update();
    } else {
      const f = fit(this.box, FOV, w / h, VIEW[this.up], UP[this.up], 1.2);   // room for the legend and the readout
      const cam = this.persp;
      cam.aspect = w / h;
      cam.near = Math.max(f.distance - f.radius * 4, f.distance / 200);
      cam.far = f.distance * 40;
      cam.up.set(...UP[this.up]);
      cam.position.set(...f.position);
      cam.updateProjectionMatrix();
      this.target = new Vector3(...f.center);
      this.controls.target.copy(this.target);
      this.controls.minDistance = f.radius * 0.2;
      this.controls.maxDistance = f.distance * 12;
      this.controls.update();
    }
    this.controls.saveState();
    this.fitted = true;
    this.changed();
    return true;
  }

  /** The canvas changed size: refit once there is room, else keep the view (the 2D scale per pixel, the aspect). */
  resized() {
    const { w, h } = this.size();
    if (!w || !h) return;
    if (!this.fitted) { this.fit(); return; }
    if (this.proj.ortho) {
      const cam = this.ortho;
      cam.left = -w / 2 * this.s2d; cam.right = w / 2 * this.s2d; cam.top = h / 2 * this.s2d; cam.bottom = -h / 2 * this.s2d;
      cam.updateProjectionMatrix();
    } else if (Math.abs(this.persp.aspect - w / h) > 1e-6) {
      this.persp.aspect = w / h;
      this.persp.updateProjectionMatrix();
    }
    this.changed();
  }

  // ------------------------------------------------------------------------------------------------ the cube
  /** Which ball of the cube is under a client point: ViewHelper's sprites, through its own ortho camera (−2 … 2). */
  pickBall(x, y) {
    const r = this.cubeEl.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    const m = new Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
    this.camera.updateMatrixWorld();
    this.helper.quaternion.copy(this.camera.quaternion).invert();
    this.helper.updateMatrixWorld();
    this.ray.setFromCamera(m, this.cubeCam);
    const hits = this.ray.intersectObjects(this.helper.children.filter((o) => o.isSprite), false);
    return hits.length ? faceOfBall(hits[0].object.userData.type, this.up) : null;
  }

  /** Draw the cube into the card's canvas at [data-cube]'s place (device px), through the shared renderer. */
  drawCube(gl, dpr) {
    if (this.cubeEl.hidden || !gl.overlay) return;
    const c = this.canvas.getBoundingClientRect(), r = this.cubeEl.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this.helper.camera = this.camera;
    gl.overlay(this.canvas, (renderer) => this.helper.render(renderer), CUBE_PX, [(r.left - c.left) * dpr, (r.top - c.top) * dpr, r.width * dpr, r.height * dpr]);
  }

  /** Turn the camera about its target until it looks along `dir` with `up` the screen's up, then `done()`. */
  turn(dir, up, done) {
    cancelAnimationFrame(this._turnRaf);
    const cam = this.camera;
    const c = this.controls.target.clone();
    const dist = Math.max(cam.position.distanceTo(c), 1e-9);
    const q0 = cam.quaternion.clone();
    const eye = c.clone().sub(new Vector3(...dir));
    const q1 = new Quaternion().setFromRotationMatrix(new Matrix4().lookAt(eye, c, new Vector3(...up)));
    this.animating = true;
    this.controls.enabled = false;
    const start = performance.now();
    const step = () => {
      const f = Math.min(1, (performance.now() - start) / TURN_MS);
      const e = f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;   // ease in-out
      cam.quaternion.copy(q0).slerp(q1, e);
      cam.position.copy(c).add(new Vector3(0, 0, dist).applyQuaternion(cam.quaternion));
      cam.updateMatrixWorld();
      this.changed();
      if (f < 1) { this._turnRaf = requestAnimationFrame(step); return; }
      this.animating = false;
      this.controls.enabled = true;
      done();
    };
    this._turnRaf = requestAnimationFrame(step);
  }

  /** A ball's face (or 3D): turn there, then switch the projection; `committed(projection)` writes it to the view. */
  go(name, committed) {
    if (this.animating) return;
    if (name === 'perspective') {
      if (!this.proj.ortho) { this.fit(); return; }
      const v = VIEW[this.up].map((x) => -x);
      this.turn(normal(v), UP[this.up], () => { this.proj = projectionOf('perspective', this.up); this._switch(); committed('perspective'); });
      return;
    }
    const next = projectionOf(name, this.up);
    if (!next.ortho) return;
    this.turn(next.dir, next.up, () => { this.proj = next; this._switch(); committed(name); });
  }

  // ------------------------------------------------------------------------------------------------ 2D axes
  /** Tick labels (HTML, at their values' projections) and grid lines (SVG, behind the canvas) on a face-aligned 2D
      view; nothing otherwise. */
  drawAxes() {
    if (!this.proj.ortho && this.axesMode !== 'none' && this.box) { this._axes3d(); return; }
    const show = this.proj.ortho && this.axesMode !== 'none' && faceAligned(this.proj) && this.box;
    this.axesEl.hidden = !show;
    this.axesEl.removeAttribute('data-3d');
    this.gridEl.style.display = show ? '' : 'none';
    if (!show) { this.axesEl.innerHTML = ''; this.gridEl.innerHTML = ''; return; }
    const { w, h } = this.size();
    const P = this.plot();
    const cam = this.ortho;
    cam.updateMatrixWorld();
    const right = rightOf(this.proj.dir, this.proj.up);
    const hAxis = dominant(right), vAxis = dominant(this.proj.up);
    const center = this.controls.target;
    const proj = (axis, value) => {
      const p = center.clone();
      p.setComponent(axis, value);
      p.project(cam);
      return [((p.x + 1) / 2) * w, ((1 - p.y) / 2) * h];
    };
    // the world value along an axis at a screen point (orthographic: linear in the screen coordinate)
    const span = (axis, a, b, k) => { const p0 = proj(axis, 0)[k], p1 = proj(axis, 1)[k]; const per = p1 - p0 || 1e-12; return [(a - p0) / per, (b - p0) / per]; };
    const out = [], lines = [];
    const unit = this.unit;
    for (const [axis, k] of [[hAxis, 0], [vAxis, 1]]) {
      const [a, b] = k === 0 ? span(axis, P.x, P.x + P.w, 0) : span(axis, P.y + P.h, P.y, 1);
      const lo = Math.min(a, b), hi = Math.max(a, b);
      const step = niceStep(hi - lo, Math.max(2, Math.round((k === 0 ? P.w : P.h) / (k === 0 ? 90 : 55))));
      for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
        const value = Math.abs(v) < step * 1e-9 ? 0 : Number(v.toPrecision(12));
        const [x, y] = proj(axis, value);
        if (k === 0) {
          if (x < P.x - 0.5 || x > P.x + P.w + 0.5) continue;
          out.push(`<span class="dv-scene3d-tick dv-scene3d-tick-h" data-tick data-axis="${AXES[axis]}" data-value="${value}" style="left:${x}px;top:${P.y + P.h + 5}px">${fmtTick(value, step)}</span>`);
          lines.push(`<line x1="${x}" y1="${P.y}" x2="${x}" y2="${P.y + P.h}"/><line class="dv-scene3d-tickmark" x1="${x}" y1="${P.y + P.h}" x2="${x}" y2="${P.y + P.h + 3}"/>`);
        } else {
          if (y < P.y - 0.5 || y > P.y + P.h + 0.5) continue;
          out.push(`<span class="dv-scene3d-tick dv-scene3d-tick-v" data-tick data-axis="${AXES[axis]}" data-value="${value}" style="left:${P.x - 6}px;top:${y}px">${fmtTick(value, step)}</span>`);
          lines.push(`<line x1="${P.x}" y1="${y}" x2="${P.x + P.w}" y2="${y}"/><line class="dv-scene3d-tickmark" x1="${P.x - 3}" y1="${y}" x2="${P.x}" y2="${y}"/>`);
        }
      }
    }
    const frame = this.frame ? ` · frame: ${this.frame}` : '';
    out.push(`<span class="dv-scene3d-axis-title dv-scene3d-axis-title-h" data-axis-title="${AXES[hAxis]}" style="left:${P.x + P.w / 2}px;top:${P.y + P.h + 21}px">${esc(`${AXES[hAxis]} (${unit})${frame}`)}</span>`);
    out.push(`<span class="dv-scene3d-axis-title dv-scene3d-axis-title-v" data-axis-title="${AXES[vAxis]}" style="left:${Math.max(2, P.x - 46)}px;top:${P.y + P.h / 2}px">${esc(`${AXES[vAxis]} (${unit})`)}</span>`);
    this.axesEl.innerHTML = out.join('');
    this.gridEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
    this.gridEl.innerHTML = `<rect class="dv-scene3d-plot" x="${P.x}" y="${P.y}" width="${P.w}" height="${P.h}"/>${lines.join('')}`;
  }

  /** In 3D, the arm mock's matplotlib-style axes: ticks along three edges of the data's box (x and y on the floor
      edges nearest the camera, the up axis on the vertical edge furthest right on screen), each label set off from the
      box outward, titled with the axis and the unit. Labels only (the ground grid stays the 3D grid); a 2D view's
      [data-tick] labels sit exactly on their ticks, these are [data-tick3d] beside theirs. */
  _axes3d() {
    const { w, h } = this.size();
    const box = this.box;
    const cam = this.camera;
    cam.updateMatrixWorld();
    this.gridEl.style.display = 'none';
    this.gridEl.innerHTML = '';
    const u = this.up === 'y' ? 1 : 2;
    const hs = [0, 1, 2].filter((i) => i !== u);
    const lo = box.min, hi = box.max;
    const at = (p) => { const v = new Vector3(...p).project(cam); return { x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h, z: v.z }; };
    const eye = cam.position;
    const dist = (p) => Math.hypot(p[0] - eye.x, p[1] - eye.y, p[2] - eye.z);
    const mid = [0, 1, 2].map((i) => (lo[i] + hi[i]) / 2);
    const c = at(mid);
    const edges = [];
    // the floor's two edges along each horizontal axis: the one nearer the camera
    for (const a of hs) {
      const b = hs.find((i) => i !== a);
      const pick = [lo[b], hi[b]].map((vb) => { const p = [...mid]; p[b] = vb; p[u] = lo[u]; return p; }).sort((p, q) => dist(p) - dist(q))[0];
      edges.push({ axis: a, base: pick });
    }
    // the up axis: the vertical edge furthest right on screen
    const corners = [];
    for (const x of [lo[hs[0]], hi[hs[0]]]) for (const y of [lo[hs[1]], hi[hs[1]]]) { const p = [0, 0, 0]; p[hs[0]] = x; p[hs[1]] = y; p[u] = mid[u]; corners.push(p); }
    edges.push({ axis: u, base: corners.sort((p, q) => at(q).x - at(p).x)[0] });
    const out = [];
    // WHY a greedy skip: an axis seen nearly end on (a shallow box's depth) puts its ticks a few pixels apart, and two
    // axes meet at a corner; a label that would overlap one already placed is left out (matplotlib thins the same way)
    const placed = [];
    const free = (x, y) => placed.every(([px, py]) => Math.abs(px - x) > 30 || Math.abs(py - y) > 13);
    for (const { axis, base } of edges) {
      const span = hi[axis] - lo[axis];
      if (!(span > 0)) continue;
      const step = niceStep(span, 4);
      const pts = [];
      for (let v = Math.ceil(lo[axis] / step) * step; v <= hi[axis] + step * 1e-9; v += step) {
        const value = Math.abs(v) < step * 1e-9 ? 0 : Number(v.toPrecision(12));
        const p = [...base];
        p[axis] = value;
        pts.push([value, at(p)]);
      }
      for (const [value, s] of pts) {
        if (s.z > 1 || s.x < 0 || s.x > w || s.y < 0 || s.y > h) continue;
        const dx = s.x - c.x, dy = s.y - c.y, l = Math.hypot(dx, dy) || 1;
        const x = s.x + (dx / l) * 14, y = s.y + (dy / l) * 14;
        if (!free(x, y)) continue;
        placed.push([x, y]);
        out.push(`<span class="dv-scene3d-tick3d" data-tick3d data-axis="${AXES[axis]}" data-value="${value}" style="left:${x}px;top:${y}px">${fmtTick(value, step)}</span>`);
      }
      // a floor axis is titled beyond its middle tick, outward; the up axis above its top end (its middle has a tick)
      const m = [...base];
      m[axis] = axis === u ? hi[axis] : (lo[axis] + hi[axis]) / 2;
      const s = at(m);
      if (s.z <= 1) {
        const dx = s.x - c.x, dy = s.y - c.y, l = Math.hypot(dx, dy) || 1;
        const [x, y] = axis === u ? [s.x + 6, s.y - 20] : [s.x + (dx / l) * 34, s.y + (dy / l) * 34];
        out.push(`<span class="dv-scene3d-axis3d" data-axis-title3d="${AXES[axis]}" style="left:${x}px;top:${y}px">${esc(`${AXES[axis]} (${this.unit})`)}</span>`);
      }
    }
    this.axesEl.hidden = false;
    this.axesEl.setAttribute('data-3d', '');
    this.axesEl.innerHTML = out.join('');
  }

  /** The camera, for the card's hook: matrices, canvas size, projection. */
  info() {
    const cam = this.camera;
    cam.updateMatrixWorld();
    const { w, h } = this.size();
    return { view: [...cam.matrixWorldInverse.elements], proj: [...cam.projectionMatrix.elements], width: w, height: h,
      position: cam.position.toArray(), projection: this.proj.name, ortho: !!this.proj.ortho, animating: this.animating };
  }
}

const dominant = (v) => { let k = 0; for (let i = 1; i < 3; i++) if (Math.abs(v[i]) > Math.abs(v[k])) k = i; return k; };
const normal = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
const sameProj = (a, b) => a.name === b.name && JSON.stringify(a.dir) === JSON.stringify(b.dir) && JSON.stringify(a.up) === JSON.stringify(b.up);
