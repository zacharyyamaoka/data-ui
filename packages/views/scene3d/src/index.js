/* type: scene3d and type: trajectory3d (docs/CONTRACT.md §25, §32; docs/peps/0010-robotics-playback.md §5).

   Layer 1, scene3d: 3D primitives drawn from any columns (layers: points, lines, frames, arrows, arcs, meshes, boxes,
   named as Rerun's archetypes are), on a stage both views share (unit, up, projection, the view cube, axes, the trail,
   density, workspace). PEP 0005's path keys stay a binding onto it, drawn as before:

     scene3d:
       x, y, z:  the path's columns; series splits it; target is the reference (dashed, muted, the ghost robot)
       t:        the time column (default t); each marker sits on its series at the clock's t, interpolated
       skeleton: [[s0x, s0y, s0z], …]: per row, the joint origins base → tool; at t a stick robot per series
       robot:    {model, links, ghost}: a meshed robot instead of the stick (a GLB relative to the data file)
       up:       z (default) | y
       layers:   [{primitive, data, color, t, density, opacity, …}] (CONTRACT §32)
       unit, projection, axes, show, decay, fade, density, workspace: the stage (CONTRACT §32)

   Layer 2, trajectory3d: "a very particular viewer for a very particular dataclass" (Zach, 2026-10-28): the
   trajectory contract (gallery/robotics/CONTRACT.md) bound onto Layer 1 (bind.js), plus its controls (controls.js):
   per-trajectory display modes, compare, decay, the cube and projections, robots per trajectory.

   The card follows the dashboard's one clock (clockFor): a seek moves every marker and robot in the same task, and
   primitives draw at clock.hover ?? clock.t (a time series hover previews that instant here, traj_compare's preview).

   STOCK PARTS: three 0.186.1 (WebGLRenderer through the page's one shared context, src/gl.js; LineSegments2 /
   LineMaterial, Points, InstancedMesh for the primitives, src/primitives/; OrbitControls, OrthographicCamera,
   ViewHelper for the stage, src/stage.js; GridHelper; GLTFLoader for robots and workspaces, src/robot.js). OURS: the
   bindings (bind.js), the trail's shader lines (primitives/window.js), the face table and 2D fit (math.js), the
   projected marker overlay, render on demand.

   WHY render on demand, never a loop: a dashboard holds many cards and most of the time nothing moves; a frame is
   drawn when t, the camera, the size or the theme changes, and WebGL starts only when the card nears the viewport.
   WHY a tick touches no geometry: the window is two uniforms (primitives/window.js), so a clock at 150,000 vertices
   moves in well under 2 ms (the P1b check). */

import {
  Scene, Group, Mesh, SphereGeometry, CylinderGeometry, BoxGeometry, EdgesGeometry, LineSegments, LineBasicMaterial,
  MeshBasicMaterial, MeshStandardMaterial, HemisphereLight, DirectionalLight, GridHelper, Vector3, Color, Quaternion,
  InstancedMesh, Matrix4, Box3, TubeGeometry, CurvePath, LineCurve3,
} from 'three';
import { esc, clockFor, seriesColor, fmtTime, mediaUrl, SeriesLegend } from '@data-ui/core';
import { sharedGL } from './gl.js';
import { sampler, bbox, niceStep, linkColumns, poseAt } from './math.js';
import { loadModel, instance, linkBoxes, linkNode } from './robot.js';
import { Stage, FOV } from './stage.js';
import { Controls, swatch } from './controls.js';
import { bindTrajectory, bindLayers, stageOf, num, text, DASH, UNIT_SCALE, listText } from './bind.js';
import { windowUniforms, timeWindow } from './primitives/window.js';
import { linesPrim, pointsPrim, framesPrim, arrowsPrim, arcsPrim, boxesPrim } from './primitives/index.js';
import { voxelsModel, buildScene, rampHtml, sliceHtml, sliceFor, colourOf, fmtValue } from './voxels/view.js';
import { twoColorRamp } from './voxels/ramp.js';
import { AXES, centreOf, cellIndex } from './voxels/grid.js';
import css from './scene3d.css';

export { css };

const Y = new Vector3(0, 1, 0);
const nameOf = (v) => text(v) ?? '—';
// stage keys and robots' looks never rebuild geometry: the camera, the window uniforms and the materials take them
const STAGE_ONLY = ['projection', 'show', 'decay', 'fade', 'axes', 'up', 'workspace', 'unit'];
let rowsIds = new WeakMap(), nextRowsId = 1;
const rowsId = (rows) => { if (!rows || typeof rows !== 'object') return 0; if (!rowsIds.has(rows)) rowsIds.set(rows, nextRowsId++); return rowsIds.get(rows); };
const hex = (c) => `#${c.getHexString()}`;

/** A path's position at t: linear between the two samples around t, clamped outside its span; null where a
    coordinate is missing on either side (never 0, never the other neighbour's value). */
function pathAt(path, t) {
  const n = path.n;
  if (!n || !Number.isFinite(t)) return null;
  let i;
  if (t <= path.t[0]) i = -1; else if (t >= path.t[n - 1]) i = n - 1;
  else { let lo = 0, hi = n - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (path.t[mid] <= t) lo = mid; else hi = mid; } i = lo; }
  if (i < 0 || i === n - 1 || path.t[i] === t) { const k = Math.max(0, i); const p = [path.p[3 * k], path.p[3 * k + 1], path.p[3 * k + 2]]; return p.every(Number.isFinite) ? p : null; }
  const f = (t - path.t[i]) / (path.t[i + 1] - path.t[i]);
  const out = [0, 1, 2].map((k) => path.p[3 * i + k] + (path.p[3 * (i + 1) + k] - path.p[3 * i + k]) * f);
  return out.every(Number.isFinite) ? out : null;
}

/** The path_overlay ramp (CONTRACT §35): series 1 to the warn tone. tokens.tone is the theme's status tones; tokens.warn
    only if a host's tokens predate them. */
const overlayRamp = (tokens) => twoColorRamp((tokens.series || [])[0] || tokens.muted, (tokens.tone && tokens.tone.warn) || tokens.warn);

/** A path's points in runs of consecutive samples with numbers, each of two or more distinct points (a repeated point
    would be a zero-length segment, whose tangent a tube cannot take). */
function finiteRuns(path) {
  const runs = [];
  let run = [];
  const flush = () => { if (run.length >= 2) runs.push(run); run = []; };
  for (let i = 0; i < path.n; i++) {
    const p = [path.p[3 * i], path.p[3 * i + 1], path.p[3 * i + 2]];
    if (!p.every(Number.isFinite)) { flush(); continue; }
    const last = run[run.length - 1];
    if (last && last[0] === p[0] && last[1] === p[1] && last[2] === p[2]) continue;
    run.push(p);
  }
  flush();
  return runs;
}

export default class Scene3dView {
  constructor(host, el) {
    // WHY a switch here: this bundle registers scene3d, trajectory3d and voxels (one three.js per page, as the chart
    // bundle registers three types), and the registry constructs the module's default class for each
    if (new.target === Scene3dView && el.classList.contains('dv-view-voxels')) return new VoxelsView(host, el);
    this.host = host;
    this.el = el;
    el.innerHTML = `<div class="dv-scene3d">
        <svg class="dv-scene3d-grid" aria-hidden="true"></svg>
        <canvas class="dv-scene3d-canvas" role="img" aria-label="3D view: drag to orbit, scroll to zoom, double-click to reset"></canvas>
        <div class="dv-scene3d-overlay">
          <div class="dv-scene3d-legend"></div>
          <div class="dv-scene3d-markers"></div>
          <div class="dv-scene3d-axes" hidden></div>
          <div class="dv-scene3d-cubebox">
            <div class="dv-scene3d-cube" data-cube role="button" tabindex="0" title="View cube: click a ball to look along that axis (orthographic)" aria-label="View cube"></div>
            <div class="dv-scene3d-cubebar"><select data-face aria-label="Projection">${['perspective', 'top', 'bottom', 'front', 'back', 'left', 'right'].map((f) => `<option value="${f}">${f === 'perspective' ? '3D' : f}</option>`).join('')}<option value="dir" hidden>oblique</option></select><span class="dv-scene3d-dot">·</span><button type="button" data-fit title="Fit the data (double-click does too)">Fit</button><span class="dv-scene3d-dot">·</span><button type="button" data-perspective title="Back to the 3D view">3D</button></div>
          </div>
          <div class="dv-scene3d-foot"><span class="dv-scene3d-t"></span><span class="dv-scene3d-note" hidden></span><span class="dv-scene3d-compare" data-compare-label hidden></span><span class="dv-scene3d-hint">Drag to orbit · scroll to zoom · double-click to reset</span></div>
        </div>
        <div class="dv-scene3d-poster"><span>3D view</span></div>
      </div>
      <div class="dv-scene3d-controls" hidden></div>`;
    this.root = el.querySelector('.dv-scene3d');
    this.canvas = el.querySelector('.dv-scene3d-canvas');
    this.$legend = el.querySelector('.dv-scene3d-legend');
    // every chart's legend (src/legend.js): a click hides a series' path, markers and robot, a double-click or Alt +
    // click shows only it. WHY the camera stays: a 3D view has no y axis to rescale; double-click on the scene refits it
    this.legend = new SeriesLegend(this.$legend, { host, keyClass: 'dv-scene3d-key', onChange: () => this._visibility() });
    this.$markers = el.querySelector('.dv-scene3d-markers');
    this.$t = el.querySelector('.dv-scene3d-t');
    this.$poster = el.querySelector('.dv-scene3d-poster');
    this.$note = el.querySelector('.dv-scene3d-note');
    this.$compare = el.querySelector('[data-compare-label]');
    this.$hint = el.querySelector('.dv-scene3d-hint');
    this.$face = el.querySelector('[data-face]');
    this.$controls = el.querySelector('.dv-scene3d-controls');
    this.controls = new Controls(this.$controls, host);
    this.uniforms = windowUniforms();
    this.stage = new Stage({ canvas: this.canvas, cube: el.querySelector('[data-cube]'), axes: el.querySelector('.dv-scene3d-axes'), grid: el.querySelector('.dv-scene3d-grid'),
      changed: () => this._cameraMoved(), picked: (face) => this._goFace(face) });
    this.scene = null;
    this.series = [];      // legacy series (scene3d x/y/z): sampler, marker, stick, robot
    this.paths = [];       // trajectory3d / layers paths with a "now" marker: {path, marker: {position, visible, scale}, dot, mesh, index}
    this.prims = [];       // primitive objects (primitives/index.js Prim)
    this.rigs = [];        // trajectory3d / meshes robots: {name, sampler, nodes, material, stick}
    this.renders = 0;
    this.builds = 0;
    this.near = false;
    this.t = null;
    this._raf = 0;
    this._fitKey = null;
    this._buildKey = null;
    this.robot = null;   // the GLB: {url, links, ghostKey, state: idle | loading | ready | failed, model, boxes, error, readyMs}
    this.problem = null;
    this._markerMeshes = [];   // the paths' "now" markers: one InstancedMesh per look (solid, the target's)
    this._tubes = [];          // path_overlay's tolerance tubes: {mesh, geometry, curve, points, tubular, radial} per target path run
    this._calls = null;        // renderer.info.render.calls of the last frame (the P2 checks' draw-call budget)

    this.clock = clockFor(host.element);
    this._onTime = () => this._place(this._now());
    this._onHover = () => this._place(this._now());
    this.clock.addEventListener('time', this._onTime);
    this.clock.addEventListener('hover', this._onHover);

    // WHY near, not visible: WebGL and the first frame start a little before the card scrolls in, so it never shows
    // its poster to a reader who is scrolling at reading pace
    this._io = new IntersectionObserver((entries) => {
      const near = entries.some((e) => e.isIntersecting);
      if (near === this.near) return;
      this.near = near;
      if (near) { this._loadRobot(); this._schedule(); }
    }, { rootMargin: '200px 0px' });
    this._io.observe(this.root);
    this._ro = new ResizeObserver(() => this._resized());
    this._ro.observe(this.root);
    this._onDbl = () => this._fit();
    this.canvas.addEventListener('dblclick', this._onDbl);
    this._onBar = (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.hasAttribute('data-fit')) this._fit();
      else if (b.hasAttribute('data-perspective')) this._goFace('perspective');
    };
    el.querySelector('.dv-scene3d-cubebar').addEventListener('click', this._onBar);
    this._onFace = () => { const v = this.$face.value; if (v !== 'dir') this._goFace(v); };
    this.$face.addEventListener('change', this._onFace);
    this._onCubeKey = (e) => {
      // the cube by keyboard: Enter / Space steps through the faces, as the select under it does
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      const order = ['perspective', 'top', 'front', 'right', 'back', 'left', 'bottom'];
      this._goFace(order[(order.indexOf(this.stage.proj.name) + 1) % order.length] || 'top');
    };
    el.querySelector('[data-cube]').addEventListener('keydown', this._onCubeKey);

    const view = this;
    this.root.scene3d = this._hook(view);
  }

  destroy() {
    this.clock.removeEventListener('time', this._onTime);
    this.clock.removeEventListener('hover', this._onHover);
    this._io.disconnect();
    this._ro.disconnect();
    this.canvas.removeEventListener('dblclick', this._onDbl);
    this.legend.destroy();
    this.controls.destroy();
    this.stage.destroy();
    cancelAnimationFrame(this._raf);
    this._dispose();
    for (const g of [this._sphere, this._rod]) if (g) g.dispose();
    if (this.gl) this.gl.unregister(this);
    this.robot = null;   // a GLB still on its way finds no card to attach to
    delete this.root.scene3d;
    this.el.innerHTML = '';
  }

  // ------------------------------------------------------------------------------------------------ input
  update(input) {
    this.input = input;
    const type = input.view.type === 'trajectory3d' ? 'trajectory3d' : 'scene3d';
    this.type = type;
    const spec = (input.view[type] && typeof input.view[type] === 'object' ? input.view[type] : {}) || {};
    const stage = stageOf(spec, type);
    this.stageKeys = stage;
    const rows = input.rows || [];
    this._robotSpec(type === 'scene3d' ? spec : null, input);
    // the camera refits when the data or the binding changes, never for a stage key (a projection, a decay)
    const bare = Object.fromEntries(Object.entries(spec).filter(([k]) => !STAGE_ONLY.includes(k) && k !== 'robots' && k !== 'modes' && k !== 'density' && k !== 'compare'));
    const fitKey = JSON.stringify([type, bare, rows.length, rows[0] && rows[0].id, rows.length && rows[rows.length - 1].id]);
    if (fitKey !== this._fitKey) this.stage.fitted = false;
    this._fitKey = fitKey;
    this.stage.setUp(stage.up);
    this.stage.unit = stage.unit;
    this.stage.axesMode = stage.axes;
    this.legend.sync(input);
    const problem = this._build(input, spec, stage);
    this.problem = problem;
    this.$poster.hidden = !problem && this.renders > 0;
    this.$poster.firstElementChild.textContent = problem || '3D view';
    this.root.toggleAttribute('data-empty', !!problem);
    this.stage.want(stage.projection);
    this._spans();
    this._resized();
    this._place(this._now());
    this._loadRobot();
  }

  /** The instant drawn: the shared crosshair's while a time series is hovered, else the clock's. */
  _now() { return this.clock.hover ?? this.clock.t; }

  /** The clock spans every path, robot and item time this card reads. */
  _spans() {
    let lo = Infinity, hi = -Infinity;
    const m = this.model;
    for (const s of this.series) if (s.sampler.n) { lo = Math.min(lo, s.sampler.t0); hi = Math.max(hi, s.sampler.t1); }
    // every path, marker path and item: a layer of points, frames, arrows, arcs or boxes alone spans the clock too
    for (const p of m ? [...m.paths, ...m.points, ...m.frames, ...m.framesZ] : []) if (p.n) { lo = Math.min(lo, p.t[0]); hi = Math.max(hi, p.t[p.n - 1]); }
    for (const it of m ? [...m.arrows, ...m.arcs, ...m.boxes] : []) if (Number.isFinite(it.t)) { lo = Math.min(lo, it.t); hi = Math.max(hi, it.t); }
    for (const g of this.rigs) if (g.sampler.n) { lo = Math.min(lo, g.sampler.t0); hi = Math.max(hi, g.sampler.t1); }
    if (Number.isFinite(lo) && Number.isFinite(hi)) this.clock.extent(lo, hi);
    this.t0 = Number.isFinite(lo) ? lo : 0;
  }

  // ------------------------------------------------------------------------------------------------ the robot (GLB)
  /** scene3d.robot / trajectory3d.robots / a meshes layer → this.robot (kept across updates while its model URL and
      links stay the same). */
  _robotSpec(spec, input) {
    let url = null, links = [], ghost = null;
    if (spec && spec.robot && typeof spec.robot.model === 'string' && spec.robot.model && Array.isArray(spec.robot.links)) {
      links = spec.robot.links.filter((l) => typeof l === 'string' && l);
      url = mediaUrl(spec.robot.model, input.dataset);
      ghost = spec.robot.ghost !== undefined && spec.robot.ghost !== null ? String(spec.robot.ghost) : null;
    }
    this._robotLinks = links;
    if (!url || !links.length) { this.robot = this._rigRobot || null; return; }
    if (this.robot && this.robot.url === url && this.robot.links.join('\n') === links.join('\n')) { this.robot.ghostKey = ghost; return; }
    this.robot = { url, links, ghostKey: ghost, state: 'idle', model: null, error: null, readyMs: null };
    this._robotDrawn = false;
  }

  /** Start the GLB once the card is near the viewport (the module caches it per URL, so N cards fetch it once). */
  _loadRobot() {
    const r = this.robot;
    if (!r || r.state !== 'idle' || !this.near) return;
    r.state = 'loading';
    loadModel(r.url).then((model) => {
      if (this.robot !== r) return;
      const missing = r.links.filter((l) => !linkNode(model.root, l));
      if (missing.length) throw new Error(`no node named ${missing.join(', ')} in the model`);
      r.model = model;
      r.boxes = linkBoxes(model, r.links);
      r.state = 'ready';
      this._attachRobots();
      this._attachRigs();
    }).catch((err) => {
      if (this.robot !== r) return;
      r.state = 'failed';
      r.error = String((err && err.message) || err);
      this._note();
      this._place(this._now());
    });
    this._note();
  }

  _note() {
    const r = this.robot;
    const failed = r && r.state === 'failed';
    const notes = [...((this.model && this.model.notes) || [])];
    if (failed) notes.unshift('Robot model unavailable: stick figure');
    this.$note.hidden = !notes.length;
    // WHY say so: a stick standing where a meshed arm was asked for is a fallback, and the reader should know why
    this.$note.textContent = notes.join(' · ');
    this.$note.title = failed ? `${r.url}: ${r.error}` : notes.join('\n');
    this._compareLabel();
  }

  /** "arrows ×20": compare's scale lengthens the arrows only, never the data, and the card says so wherever it is read
      (PEP 0010 §5.2). WHY its own label, not the hint: the hint folds away on a narrow card, and an arrow drawn twenty
      times its length must never pass for a true one. */
  _compareLabel() {
    const m = this.model;
    const cmp = m && m.compare;
    const scale = cmp ? cmp.scale : 1;
    const on = !!cmp && cmp.pairs.length > 0 && scale !== 1 && m.arrows.length > 0 && !m.problem;
    this.$compare.hidden = !on;
    this.$compare.textContent = on ? `arrows ×${scale}` : '';
    this.$compare.title = on ? `Compare's arrows are drawn ${scale} times as long as the difference (display only)` : '';
  }

  /** A clone of the loaded model per legacy series (the ghost's translucent), in place of the stick; then refit. */
  _attachRobots() {
    const r = this.robot;
    if (!r || r.state !== 'ready' || !this.scene || this._rigRobot === r) return;
    const tokens = (this.input && this.input.tokens) || {};
    for (const s of this.series) {
      if (s.robot || s.robotOffset === undefined || !s.sampler.n) continue;
      let material = null;
      if (s.isGhost) {
        // WHY a lit, see-through ghost: the reference pose is there to compare against, so it reads as a shape (lit)
        // behind the arms that ran, never as a second solid robot
        material = new MeshStandardMaterial({ color: s.color, transparent: true, opacity: tokens.dark ? 0.2 : 0.24, depthWrite: false,
          roughness: 0.7, metalness: 0, flatShading: true });
        s.materials.push(material);
      }
      s.robot = instance(r.model, r.links, material);
      if (s.isGhost) s.robot.root.renderOrder = 1;   // after the solid robots, so they show through it
      s.group.add(s.robot.root);
      for (const o of [...s.joints, ...s.links]) o.visible = false;
    }
    // the box the camera frames grows to hold every link's mesh box, posed at every row (traj_compare's bounds)
    const pts = [], c = new Vector3(), q = new Quaternion();
    for (const s of this.series) {
      if (!s.robot) continue;
      for (const pt of s.sampler.points) r.links.forEach((l, k) => {
        const o = s.robotOffset + k * 7, b = r.boxes[l];
        const v = pt.v.slice(o, o + 7);
        if (!b || v.includes(null)) return;
        q.set(v[4], v[5], v[6], v[3]).normalize();
        for (const x of [b[0][0], b[1][0]]) for (const y of [b[0][1], b[1][1]]) for (const z of [b[0][2], b[1][2]]) {
          c.set(x, y, z).applyQuaternion(q);
          pts.push([c.x + v[0], c.y + v[1], c.z + v[2]]);
        }
      });
    }
    this._growBox(pts);
  }

  /** Grow the framed box to hold `pts`; the camera refits unless the reader moved it (in 2D only when `refit`: a
      workspace that loads after the first frame must be framed, a robot's meshes in a face view need not be). */
  _growBox(pts, { refit = false } = {}) {
    if (!pts.length || !this.box) return;
    const grown = bbox([this.box.min, this.box.max, ...pts]);
    if (grown) { this.box = grown; this.stage.setBox(grown); }
    if (!this.stage.userCam && (refit || !this.stage.proj.ortho)) this.stage.fitted = false;
    this._resized();
    this._place(this._now());
  }

  // ------------------------------------------------------------------------------------------------ the scene
  _build(input, spec, stage) {
    const tokens = input.tokens || {};
    const cs = getComputedStyle(this.el);
    const px = (name, d) => { const v = parseFloat(cs.getPropertyValue(name)); return Number.isFinite(v) ? v : d; };
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const look = { line: px('--dv-s3-line', 2), target: px('--dv-s3-target-line', 1.5), frame: px('--dv-s3-frame', 1.5), point: px('--dv-s3-point', 5),
      axis: ['--dv-s3-axis-x', '--dv-s3-axis-y', '--dv-s3-axis-z'].map((n, i) => cs.getPropertyValue(n).trim() || ['#e5484d', '#30a46c', '#3e63dd'][i]),
      workspace: cs.getPropertyValue('--dv-s3-workspace').trim() || tokens.muted || '#71717a' };

    // the binding: what to draw
    const isLegacy = this.type === 'scene3d' && spec.x && spec.y && spec.z;
    const hasLayers = this.type === 'scene3d' && Array.isArray(spec.layers) && spec.layers.length;
    let model;
    if (this.type === 'trajectory3d') model = bindTrajectory(input);
    else if (hasLayers) model = bindLayers(input);
    else model = { kind: 'scene3d', stage, series: [], paths: [], lines: [], targetLines: [], points: [], frames: [], framesZ: [], arrows: [], arcs: [], boxes: [], robots: null, legend: [], notes: [], problem: null, frame: null };
    this.model = model;
    this.stage.frame = model.frame;
    if (!isLegacy && !hasLayers && this.type === 'scene3d') { this._dispose(); this.legend.draw([]); this.$controls.hidden = true; return 'scene3d needs x, y and z columns, or layers'; }

    // geometry is rebuilt only when what it holds changed: rows, the binding, the colours (a theme), never a clock tick
    const layerIds = Object.entries(input.layers || {}).map(([k, v]) => [k, rowsId(v.rows)]);
    const block = Object.fromEntries(Object.entries(spec).filter(([k]) => !STAGE_ONLY.includes(k) && k !== 'robots'));
    const buildKey = JSON.stringify([this.type, block, rowsId(input.rows), input.rows ? input.rows.length : 0, layerIds, tokens.dark, (tokens.series || []).join(), tokens.muted, tokens.tone || null,
      (input.view.style && [input.view.style.palette, input.view.style.families]) || null, look, dpr, stage.unit]);
    // a robot shown again (the menu) whose series had none at the last build needs its rig: rebuild
    const rigless = model.robots && model.robots.series.some((r) => !(this._rigNames || new Set()).has(r.series));
    const rebuild = buildKey !== this._buildKey || !this.scene || rigless;
    if (rebuild) {
      this._dispose();
      this._buildKey = buildKey;
      this.scene = new Scene();
      this.scene.add(new HemisphereLight(0xffffff, tokens.dark ? 0x30343c : 0x8d8a84, tokens.dark ? 1.7 : 2));
      const key = new DirectionalLight(0xffffff, 1.8);
      key.position.set(...(stage.up === 'z' ? [1.5, -2, 3] : [1.5, 3, 2]));   // from above, front-right: the camera's side
      this.scene.add(key);
      this.series = [];
      this.paths = [];
      this.prims = [];
      this.rigs = [];
      this.$markers.innerHTML = '';
    }

    const keys = [];
    let box = null;
    if (isLegacy) {
      const r = this._legacy(input, spec, stage, tokens, dpr, look, rebuild, keys);
      if (typeof r === 'string') { model.problem = r; }
      else box = r;
    }
    if (model.problem) {
      this._clearPrims();
      this._overlayRamp(null);
      this.legend.draw([]);
      this.$controls.hidden = true;
      this._note();
      return model.problem;
    }

    // the box every frame of the data lives in: every path point, item and robot link at every t
    const pts = [];
    if (box) pts.push(box.min, box.max);
    for (const p of model.paths) for (let i = 0; i < p.n; i++) pts.push([p.p[3 * i], p.p[3 * i + 1], p.p[3 * i + 2]]);
    for (const p of [...model.points, ...model.frames, ...model.framesZ]) for (let i = 0; i < p.n; i++) pts.push([p.p[3 * i], p.p[3 * i + 1], p.p[3 * i + 2]]);
    for (const a of model.arrows) pts.push(a.from);
    for (const a of model.arcs) pts.push(a.at);
    for (const b of model.boxes) pts.push(b.min, b.max);
    if (model.robots) for (const r of model.robots.series) for (const row of r.rows) for (const l of model.robots.links) pts.push([num(row[`${l}_x`]), num(row[`${l}_y`]), num(row[`${l}_z`])]);
    if (stage.workspace && Array.isArray(stage.workspace.box)) pts.push(...stage.workspace.box);
    const full = bbox(pts);
    if (!full) {
      this._overlayRamp(null);
      this.legend.draw([]);
      this.$controls.hidden = true;
      return this.type === 'trajectory3d' ? `No poses to draw in ${model.columns.x}, ${model.columns.y}, ${model.columns.z} for these rows` : 'No numbers to draw for these rows';
    }
    if (rebuild || !this.box) { this.box = full; this.stage.setBox(full); }
    const size = Math.max(Math.hypot(full.max[0] - full.min[0], full.max[1] - full.min[1], full.max[2] - full.min[2]) / 2, 1e-9);
    this._size = size;
    this.uniforms.dvDashUnit.value = size * 0.006;

    if (rebuild) {
      this.tOrigin = this._origin(model);
      const ctx = { uniforms: this.uniforms, tOrigin: this.tOrigin, lineWidth: look.line * dpr, frameWidth: look.frame * dpr, pointSize: look.point * dpr,
        size, length: size * 0.08, density: stage.density, axisColors: look.axis.map((c) => new Color(c)), muted: new Color(tokens.muted || '#71717a') };
      const col = (p) => ({ ...p, color: new Color(p.css) });
      ctx.overlayColor = this._overlayColor(model, tokens);
      // each layer's object names its role, for the checks' draw-call count (hook drawables())
      const add = (prim, role) => { if (!prim) return; this.builds++; prim.object.userData.role = role; if (prim.cones) prim.cones.userData.role = 'arrow-heads'; this.prims.push(prim); this.scene.add(prim.object); };
      add(linesPrim(model.lines.map(col), ctx), 'line');
      // WHY the target on top, pulled toward the camera: a run that tracks well lies within a millimetre of it, and a
      // reference drawn underneath would vanish; dashed over the run, both stay readable (the robot still hides it)
      add(linesPrim(model.targetLines.map(col), ctx, { linewidth: look.target * dpr, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -8 }), 'target');
      add(pointsPrim(model.points.map(col), ctx), 'points');
      add(framesPrim(model.frames.map(col), ctx, 'xyz'), 'frames');
      add(framesPrim(model.framesZ.map(col), ctx, 'z'), 'frames-z');
      const cmpScale = model.compare ? model.compare.scale : 1;
      add(arrowsPrim(model.arrows.map(col), ctx, model.arrows.length && model.arrows[0].scale ? model.arrows[0].scale : cmpScale), 'arrows');
      add(arcsPrim(model.arcs.map(col), ctx), 'arcs');
      add(boxesPrim(model.boxes.map(col), ctx), 'boxes');
      this._tube(model);
      this._grid(full, stage, tokens);
      this._workspace(stage, input, tokens, look);
      this._markers(model, size);
      this._rigs(model, tokens, size);
    } else {
      this._restyleRigs(model, tokens);
    }
    // the legend: legacy series, or the model's entries (a dash pattern drawn as it is on the path)
    const entries = isLegacy ? keys : model.legend.map((e) => ({ name: e.name, swatch: swatch(e.css, e.dash), extra: e.extra ? `<span class="dv-scene3d-extra">${esc(e.extra)}</span>` : '' }));
    this.legend.draw(entries);
    this._xyzKey(model);
    this._overlayRamp(model, input, tokens);
    if (this.type === 'trajectory3d') {
      this.$controls.hidden = false;
      this.controls.draw(input, model, { rate: this._rate(model), preview: (name, op) => this._previewRig(name, op) });
    } else this.$controls.hidden = true;
    this._visibility(false);
    if (this.robot && this.robot.state === 'ready') { this._attachRobots(); this._attachRigs(); }
    this._note();
    return null;
  }

  /** The "now" marker of every drawn path (the target's too): one InstancedMesh per look, solid and the target's
      translucent, so 137 runs' markers are two draw calls, not 137 (PEP 0010 P2, "≤ 1 draw call per layer"). Each path
      keeps a plain {position, visible, scale} the hook and the overlay read; _syncMarkers() writes them to the GPU. */
  _markers(model, size) {
    const sphere = this._sphere || (this._sphere = new SphereGeometry(1, 20, 14));
    // one mesh per look and alpha: a path drawn at opacity auto's 1/n has its marker at 1/n too, so 137 runs' markers
    // stacked where every run is at t read as one dot, and a lone run's as faint as its path (never 137 opaque balls)
    const looks = new Map();
    for (const p of model.paths) {
      const isTarget = p.dash === DASH.target;
      const alpha = Number.isFinite(p.alpha) ? Math.min(1, Math.max(0, p.alpha)) : 1;
      const k = `${isTarget ? 'target-markers' : 'markers'}\n${alpha}`;
      if (!looks.has(k)) looks.set(k, { role: isTarget ? 'target-markers' : 'markers', isTarget, alpha, list: [] });
      looks.get(k).list.push(p);
    }
    for (const { role, isTarget, alpha, list } of looks.values()) {
      const opacity = (isTarget ? 0.8 : 1) * alpha;
      const material = new MeshBasicMaterial({ toneMapped: false, transparent: opacity < 1, opacity, depthWrite: opacity >= 1 });
      const mesh = new InstancedMesh(sphere, material, list.length);
      mesh.userData.role = role;
      // WHY no culling: the instances move with t, and the mesh's bounds would be where they first stood
      mesh.frustumCulled = false;
      list.forEach((p, index) => {
        mesh.setColorAt(index, new Color(p.css));
        const dot = document.createElement('span');
        dot.className = 'dv-scene3d-marker';
        dot.dataset.marker = '';
        dot.dataset.series = p.seriesName;
        dot.dataset.path = p.key;
        dot.style.setProperty('--c', p.css);
        this.$markers.append(dot);
        this.paths.push({ path: p, marker: { position: new Vector3(), visible: false, scale: size * (isTarget ? 0.02 : 0.026) }, dot, mesh, index });
      });
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      this.scene.add(mesh);
      this._markerMeshes.push({ mesh, material });
    }
  }

  /** Each marker's place and size (0 when hidden or off its path) into its instance matrix. */
  _syncMarkers() {
    if (!this._markerMeshes.length) return;
    const m = new Matrix4(), q = new Quaternion(), s = new Vector3();
    for (const p of this.paths) {
      const k = p.marker.visible && !p.hidden ? p.marker.scale : 0;
      p.mesh.setMatrixAt(p.index, m.compose(p.marker.position, q, s.set(k, k, k)));
    }
    for (const { mesh } of this._markerMeshes) mesh.instanceMatrix.needsUpdate = true;
  }

  /** The time origin the shaders hold times against (float32 keeps a run's seconds to a microsecond). */
  _origin(model) {
    let lo = Infinity;
    for (const p of model.paths) if (p.n) lo = Math.min(lo, p.t[0]);
    for (const p of [...model.points, ...model.frames, ...model.framesZ]) if (p.n) lo = Math.min(lo, p.t[0]);
    for (const it of [...model.arrows, ...model.arcs, ...model.boxes]) lo = Math.min(lo, it.t);
    for (const s of this.series) if (s.sampler.n) lo = Math.min(lo, s.sampler.t0);
    return Number.isFinite(lo) ? lo : 0;
  }

  /** The rate the decay's sample count is written at: the median step of the first path with samples. */
  _rate(model) {
    const p = model.paths.find((x) => x.n > 2);
    if (!p) return null;
    const d = [];
    for (let i = 1; i < Math.min(p.n, 2001); i++) { const s = p.t[i] - p.t[i - 1]; if (s > 0) d.push(s); }
    if (!d.length) return null;
    d.sort((a, b) => a - b);
    return 1 / d[d.length >> 1];
  }

  /** path_overlay color (CONTRACT §35): a value on the ramp from series 1 to the warn tone over the drawn [min, max], as a
      three Color (cached by hex: a path has 150,000 vertices and a ramp a few hundred distinct colours). WHY
      series 1 and the warn tone: the 2D card's sequential ramp, so a path that stays on its own hue is within its limit
      and one that turns warn is not. A flat range (min = max) is the low end: nothing has drifted from the others. */
  _overlayColor(model, tokens) {
    const { color, min, max } = model.overlay || {};   // only trajectory3d's model has one
    if (!color || min === null || min === undefined) return null;
    const ramp = overlayRamp(tokens);
    const cache = new Map();
    return (v) => {
      const css = ramp.at(max > min ? (v - min) / (max - min) : 0);
      if (!cache.has(css)) cache.set(css, new Color(css));
      return cache.get(css);
    };
  }

  /** The ramp's bar in the card (the legend's last row), titled with the column's label and unit, its two ends the
      drawn min and max; `model` null removes it. */
  _overlayRamp(model, input, tokens) {
    let el = this.$legend.querySelector('.dv-scene3d-ramp');
    const o = model && model.overlay;
    if (!o || !o.color || o.min === null) { if (el) el.remove(); return; }
    const ramp = overlayRamp(tokens);
    const col = (input.columns && input.columns[o.color]) || {};
    const title = `${col.label || o.color}${col.unitText ? ` (${col.unitText})` : ''}`;
    const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => `${ramp.at(t)} ${t * 100}%`).join(', ');
    if (!el) { el = document.createElement('div'); el.className = 'dv-scene3d-ramp'; el.dataset.ramp = ''; }
    el.innerHTML = `<span class="dv-voxels-ramp-title">${esc(title)}</span><span class="dv-voxels-ramp-scale"><span class="dv-voxels-ramp-lo" data-ramp-lo>${esc(fmtValue(o.min))}</span>`
      + `<i class="dv-voxels-ramp-bar" style="background:linear-gradient(to right, ${esc(stops)})"></i><span class="dv-voxels-ramp-hi" data-ramp-hi>${esc(fmtValue(o.max))}</span></span>`;
    this.$legend.append(el);
  }

  /** path_overlay tolerance (CONTRACT §35): the target's path again as a translucent tube of the tolerance's radius,
      three's TubeGeometry along a CurvePath of LineCurve3 through the path's points (one tube per run of points with
      numbers, never joined across a gap). WHY a tube and not a ribbon: from a face (orthographic) it projects to a band
      2 × tolerance wide for free, and from 3D it is the volume the run is meant to stay inside. Opacity low and depthWrite
      off so the dashed target and the runs inside it stay readable; drawn first (renderOrder) so they paint over it. */
  _tube(model) {
    const tube = model.tube;
    if (!tube) return;
    const target = model.series.find((s) => s.isTarget);
    const material = new MeshBasicMaterial({ color: new Color(target.css), transparent: true, opacity: 0.16, depthWrite: false, toneMapped: false });
    this._tubeMaterial = material;
    for (const path of tube.paths) {
      for (const points of finiteRuns(path)) {
        const curve = new CurvePath();
        for (let i = 0; i + 1 < points.length; i++) curve.add(new LineCurve3(new Vector3(...points[i]), new Vector3(...points[i + 1])));
        const tubular = Math.min(2000, Math.max(16, 2 * points.length)), radial = 12;
        const geometry = new TubeGeometry(curve, tubular, tube.radius, radial, false);
        const mesh = new Mesh(geometry, material);
        mesh.userData.role = 'tolerance-tube';
        mesh.renderOrder = -0.5;
        this.scene.add(mesh);
        this._tubes.push({ mesh, geometry, curve, points, tubular, radial, series: target.legendName });
      }
    }
  }

  /** The legend's static key for full frames: X Y Z in their colours (frame axes are always labelled, never a series). */
  _xyzKey(model) {
    let key = this.$legend.parentElement.querySelector('.dv-scene3d-xyz');
    const want = model.frames.length > 0;
    if (!want) { if (key) key.remove(); return; }
    if (!key) {
      key = document.createElement('span');
      key.className = 'dv-scene3d-xyz';
      key.setAttribute('aria-label', 'Frame axes: X red, Y green, Z blue');
      key.innerHTML = '<b>X</b><b>Y</b><b>Z</b>';
    }
    this.$legend.append(key);
  }

  _hint() {
    const model = this.model || { notes: [] };
    const parts = [];
    if (this.stage.proj.ortho) parts.push('Drag to pan · scroll to zoom · double-click to fit');
    else parts.push('Drag to orbit · scroll to zoom · double-click to reset');
    if (model.robots && model.robots.series.some((r) => r.runs > 1)) parts.unshift('robots: first run of each');
    this.$hint.textContent = parts.join(' · ');
  }

  /** PEP 0005's path keys (x, y, z, series, target, skeleton, robot), as built: one path per series, a marker at t,
      a stick or meshed robot. Returns the data box, or a problem. */
  _legacy(input, spec, stage, tokens, dpr, look, rebuild, keys) {
    const { x, y, z } = spec;
    const tcol = stage.t;
    const skeleton = (Array.isArray(spec.skeleton) ? spec.skeleton : []).filter((p) => Array.isArray(p) && p.length === 3 && p.every((c) => typeof c === 'string'));
    const robot = this.robot && this._robotLinks.length ? this.robot : null;
    const robotOffset = 3 + skeleton.length * 3;
    const cols = [x, y, z, ...skeleton.flat(), ...(robot ? robot.links.flatMap(linkColumns) : [])];
    const read = (r, c) => num(r[c]);
    const groups = new Map();
    for (const r of input.rows || []) {
      const name = spec.series ? nameOf(r[spec.series]) : (input.view.name || 'path');
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(r);
    }
    // WHY a series named "target" is the reference by default: the time series card's rule (PEP 0005 §2b, dash:)
    const target = spec.target !== undefined && spec.target !== null ? String(spec.target) : groups.has('target') ? 'target' : null;
    const names = [...groups.keys()].sort((a, b) => (b === target) - (a === target));
    const ghost = robot ? (robot.ghostKey !== null ? robot.ghostKey : target) : null;
    const all = [];
    for (const rows of groups.values()) for (const r of rows) {
      all.push([read(r, x), read(r, y), read(r, z)]);
      for (const [a, b, c] of skeleton) all.push([read(r, a), read(r, b), read(r, c)]);
      if (robot) for (const l of robot.links) all.push([read(r, `${l}_x`), read(r, `${l}_y`), read(r, `${l}_z`)]);
    }
    const box = bbox(all);
    if (!box) return `No numbers in ${x}, ${y}, ${z} for these rows`;
    const size = Math.max(Math.hypot(box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2]) / 2, 0.025);
    const lines = this.model.lines, targetLines = this.model.targetLines;
    if (rebuild) {
      const sphere = this._sphere || (this._sphere = new SphereGeometry(1, 20, 14));
      const rod = this._rod || (this._rod = new CylinderGeometry(1, 1, 1, 14));
      for (const name of names) {
        const isTarget = name === target;
        const colorText = seriesColor(name, input);
        const color = new Color(colorText);
        const smp = sampler(groups.get(name), tcol, cols, read);
        const s = { name, isTarget, color, colorText, sampler: smp, group: new Group(), joints: [], links: [], marker: null, dot: null, materials: [],
          robot: null, robotOffset: robot ? robotOffset : undefined, isGhost: name === ghost };
        // the path: the sampler's points in time order, a missing value a break (lines never join across one)
        const n = smp.n;
        const path = { series: name, seriesName: name, key: name, css: colorText, alpha: 1, dash: isTarget ? DASH.target : DASH.solid, n, t: new Float64Array(n), p: new Float64Array(3 * n), q: null };
        smp.points.forEach((pt, i) => { path.t[i] = pt.t; for (let k = 0; k < 3; k++) path.p[3 * i + k] = pt.v[k] === null ? NaN : pt.v[k]; });
        (isTarget ? targetLines : lines).push(path);
        if (smp.n) {
          const mm = new MeshBasicMaterial({ color, toneMapped: false, transparent: isTarget, opacity: isTarget ? 0.8 : 1 });
          s.materials.push(mm);
          s.marker = new Mesh(sphere, mm);
          s.marker.scale.setScalar(size * (isTarget ? 0.02 : 0.026));
          s.group.add(s.marker);
          const dot = document.createElement('span');
          dot.className = 'dv-scene3d-marker';
          dot.dataset.marker = '';
          dot.dataset.series = name;
          dot.style.setProperty('--c', colorText);
          this.$markers.append(dot);
          s.dot = dot;
        }
        // the stick robot: joint spheres and a rod between each pair, base → tool; the target is a translucent ghost
        if (smp.n && skeleton.length >= 2) this._stick(s, skeleton.length, size, isTarget, tokens);
        this.scene.add(s.group);
        this.series.push(s);
      }
    } else {
      // the same series, only re-sorted lines lists: the paths come from the kept samplers
      for (const s of this.series) {
        const n = s.sampler.n;
        const path = { series: s.name, seriesName: s.name, key: s.name, css: s.colorText, alpha: 1, dash: s.isTarget ? DASH.target : DASH.solid, n, t: new Float64Array(n), p: new Float64Array(3 * n), q: null };
        s.sampler.points.forEach((pt, i) => { path.t[i] = pt.t; for (let k = 0; k < 3; k++) path.p[3 * i + k] = pt.v[k] === null ? NaN : pt.v[k]; });
        (s.isTarget ? targetLines : lines).push(path);
      }
    }
    for (const s of this.series) keys.push({ name: s.name, swatch: `<i class="${s.isTarget ? 'dv-scene3d-dash' : ''}" style="--c:${esc(s.colorText)}"></i>` });
    return box;
  }

  _stick(s, joints, size, isTarget, tokens) {
    const sphere = this._sphere, rod = this._rod || (this._rod = new CylinderGeometry(1, 1, 1, 14));
    const color = s.color;
    // WHY a ghost: the reference pose is there to compare against, so it sits behind the robots that ran
    const body = isTarget
      ? new MeshBasicMaterial({ color, transparent: true, opacity: tokens.dark ? 0.22 : 0.28, depthWrite: false })
      : new MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05 });
    const joint = isTarget ? body : new MeshStandardMaterial({ color: color.clone().lerp(new Color(tokens.dark ? '#ffffff' : '#000000'), 0.18), roughness: 0.5, metalness: 0.05 });
    s.materials.push(body, joint);
    for (let k = 0; k < joints; k++) {
      const j = new Mesh(sphere, joint);
      j.scale.setScalar(size * (k === joints - 1 ? 0.014 : 0.022));
      j.userData.joint = k;
      s.joints.push(j);
      s.group.add(j);
      if (k) { const l = new Mesh(rod, body); s.links.push(l); s.group.add(l); }
    }
    s.rod = size * 0.012;
  }

  // ------------------------------------------------------------------------------------------------ robots per series
  /** trajectory3d's robots (and a meshes layer's models): one rig per series, posed at t from its link rows; the stick
      through the link origins stands in while the GLB loads, and for good if it fails. */
  _rigs(model, tokens, size) {
    const rb = model.robots;
    if (!rb) { this._rigRobot = null; return; }
    if (!this._rigRobot || this._rigRobot.url !== rb.url || this._rigRobot.links.join('\n') !== rb.links.join('\n')) {
      this._rigRobot = { url: rb.url, links: rb.links, ghostKey: null, state: 'idle', model: null, error: null, readyMs: null };
      this._robotDrawn = false;
    }
    if (!this._robotLinks || !this._robotLinks.length) this.robot = this._rigRobot;
    this._rigNames = new Set(rb.series.map((r) => r.series));
    for (const r of rb.series) {
      const smp = sampler(r.rows, rb.t, rb.cols, (row, c) => num(row[c]));
      if (!smp.n) continue;
      const rig = { name: r.series, legendName: r.legendName, sampler: smp, color: new Color(r.color), css: r.color, opacity: r.opacity, isTarget: r.isTarget,
        group: new Group(), joints: [], links: [], robot: null, material: null, materials: [], color0: r.color };
      this._stick(rig, rb.links.length, size, false, tokens);
      for (const m of rig.materials) { m.transparent = r.opacity < 1; m.opacity = r.opacity; m.depthWrite = r.opacity >= 1; }
      this.scene.add(rig.group);
      this.rigs.push(rig);
    }
    this._rigScale = rb.scale;
  }

  _rigMaterial(rig) {
    return new MeshStandardMaterial({ color: rig.color, transparent: rig.opacity < 1, opacity: rig.opacity, depthWrite: rig.opacity >= 1, roughness: 0.6, metalness: 0.05, flatShading: true });
  }

  /** The GLB is in: a clone per rig in its own material (its colour and opacity, CONTRACT §32 robots.series). */
  _attachRigs() {
    const r = this._rigRobot;
    if (!r || r.state !== 'ready' || !this.scene) return;
    let added = false;
    for (const rig of this.rigs) {
      if (rig.robot) continue;
      rig.material = this._rigMaterial(rig);
      rig.robot = instance(r.model, r.links, rig.material, this._rigScale || 1);
      if (rig.opacity < 1) rig.robot.root.renderOrder = 1;
      rig.group.add(rig.robot.root);
      for (const o of [...rig.joints, ...rig.links]) o.visible = false;
      added = true;
    }
    if (!added) return;
    // the fitted box grows to hold every link's mesh box at every row
    const pts = [], c = new Vector3(), q = new Quaternion();
    const k = this._rigScale || 1;
    for (const rig of this.rigs) for (const pt of rig.sampler.points) r.links.forEach((l, i) => {
      const b = r.boxes[l], v = pt.v.slice(i * 7, i * 7 + 7);
      if (!b || v.includes(null)) return;
      q.set(v[4], v[5], v[6], v[3]).normalize();
      for (const x of [b[0][0], b[1][0]]) for (const y of [b[0][1], b[1][1]]) for (const z of [b[0][2], b[1][2]]) {
        c.set(x * k, y * k, z * k).applyQuaternion(q);
        pts.push([c.x + v[0], c.y + v[1], c.z + v[2]]);
      }
    });
    this._growBox(pts);
  }

  /** A robot's colour or opacity changed (the menu, a link): its material, no rebuild. */
  _restyleRigs(model, tokens) {
    if (!model.robots) return;
    const by = new Map(model.robots.series.map((r) => [r.series, r]));
    for (const rig of this.rigs) {
      const r = by.get(rig.name);
      if (!r) { rig.group.visible = false; rig.off = true; continue; }
      rig.off = false;
      rig.color.set(r.color);
      rig.css = r.color;
      rig.opacity = r.opacity;
      const mats = [...rig.materials, ...(rig.material ? [rig.material] : [])];
      for (const m of mats) {
        m.color.set(r.color);
        m.opacity = r.opacity;
        m.transparent = r.opacity < 1;
        m.depthWrite = r.opacity >= 1;
        m.needsUpdate = true;
      }
      if (rig.robot) rig.robot.root.renderOrder = r.opacity < 1 ? 1 : 0;
    }
  }

  _previewRig(name, opacity) {
    const rig = this.rigs.find((g) => g.name === name);
    if (!rig) return;
    for (const m of [...rig.materials, ...(rig.material ? [rig.material] : [])]) { m.opacity = opacity; m.transparent = opacity < 1; m.depthWrite = opacity >= 1; m.needsUpdate = true; }
    this._schedule();
  }

  // ------------------------------------------------------------------------------------------------ ground, workspace
  _grid(box, stage, tokens) {
    // the ground: a faint grid on z = 0 (y = 0 with up: y) under the data's footprint, in 3D only
    this.gridColor = new Color(tokens.border || '#d4d4d8');
    const up = stage.up;
    const g = up === 'z' ? [0, 1] : [0, 2];
    const span = Math.max(box.max[g[0]] - box.min[g[0]], box.max[g[1]] - box.min[g[1]]) * 1.4 || 1;
    const step = niceStep(span, 12);
    const cells = Math.max(2, Math.ceil(span / step / 2) * 2);
    const grid = new GridHelper(cells * step, cells, this.gridColor, this.gridColor);
    grid.material.transparent = true;
    grid.material.opacity = tokens.dark ? 0.9 : 1;
    grid.material.depthWrite = false;
    const cx = Math.round((box.min[g[0]] + box.max[g[0]]) / 2 / step) * step, cy = Math.round((box.min[g[1]] + box.max[g[1]]) / 2 / step) * step;
    if (up === 'z') { grid.rotation.x = Math.PI / 2; grid.position.set(cx, cy, 0); } else grid.position.set(cx, 0, cy);
    grid.renderOrder = -1;
    grid.userData.role = 'grid';
    this.ground = grid;
    this.scene.add(grid);
  }

  /** The reachable volume (CONTRACT §32 workspace): a translucent fill and its edges, a box or a glTF model. A model is
      framed with the data once it loads (the workspace is part of what the camera fits: Zach, "draw an outline of the
      robot's workspace… so you can literally see exactly what the coverage is"). */
  _workspace(stage, input, tokens, look) {
    const ws = stage.workspace;
    this._wsState = ws ? 'loading' : 'none';
    if (!ws) return;
    const color = new Color(look.workspace);
    const opacity = typeof ws.opacity === 'number' ? ws.opacity : 0.12;
    const fill = new MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, toneMapped: false });
    const edge = new LineBasicMaterial({ color, transparent: true, opacity: Math.min(1, opacity * 4 + 0.2), toneMapped: false });
    this._wsMaterials = [fill, edge];
    const group = new Group();
    group.renderOrder = 2;
    this.scene.add(group);
    this._ws = group;
    if (Array.isArray(ws.box) && ws.box.length === 2) {
      const [a, b] = ws.box;
      const geo = new BoxGeometry(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]), Math.abs(b[2] - a[2]));
      const m = new Mesh(geo, fill);
      m.position.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2);
      m.userData.role = 'workspace-fill';
      const e = new LineSegments(new EdgesGeometry(geo), edge);
      e.position.copy(m.position);
      e.userData.role = 'workspace-edges';
      group.add(m, e);
      this._wsGeometries = [geo, e.geometry];
      this._wsState = 'ready';
    } else if (typeof ws.model === 'string') {
      const url = mediaUrl(ws.model, input.dataset);
      const k = UNIT_SCALE[stage.unit] || 1;
      loadModel(url).then((model) => {
        if (this._ws !== group) return;
        const root = model.root.clone(true);
        root.scale.setScalar(k);
        const geos = [];
        const meshes = [];
        root.traverse((o) => { if (o.isMesh) meshes.push(o); });
        for (const o of meshes) {
          o.material = fill;
          o.userData.role = 'workspace-fill';
          const e = new LineSegments(new EdgesGeometry(o.geometry, 30), edge);
          e.userData.role = 'workspace-edges';
          o.add(e);
          geos.push(e.geometry);
        }
        this._wsGeometries = geos;
        group.add(root);
        this._wsState = 'ready';
        // its bounds join the framed box, and the camera refits to them unless the reader moved it
        group.updateMatrixWorld(true);
        const b = new Box3().setFromObject(root);
        if (!b.isEmpty()) {
          const corners = [];
          for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) corners.push([x, y, z]);
          this._growBox(corners, { refit: true });
        }
        this._schedule();
      }).catch(() => { this._wsState = 'failed'; if (this.model && this.model.notes) this.model.notes.push(`workspace: ${url} did not load`); this._note(); });
    }
  }

  // ------------------------------------------------------------------------------------------------ visibility
  /** Each series' paths, items, markers and robot shown as the legend says, then one frame. */
  _visibility(draw = true) {
    const hidden = new Set(this.legend.hidden || []);
    for (const s of this.series) s.group.visible = this.legend.shows(s.name);
    for (const p of this.prims) p.setHidden(hidden);
    for (const m of this.paths) m.hidden = hidden.has(m.path.series);
    for (const t of this._tubes) t.mesh.visible = !hidden.has(t.series);
    this._syncMarkers();
    for (const r of this.rigs) r.group.visible = !r.off && !hidden.has(r.legendName) && !hidden.has(r.name);
    if (!draw) return;
    this._project();
    this._schedule();
  }

  _clearPrims() {
    for (const p of this.prims) { if (this.scene) this.scene.remove(p.object); p.dispose(); }
    this.prims = [];
  }

  _dispose() {
    for (const s of this.series) for (const m of new Set(s.materials)) m.dispose();
    for (const r of this.rigs) { for (const m of new Set(r.materials)) m.dispose(); if (r.material) r.material.dispose(); }
    for (const { mesh, material } of this._markerMeshes) { material.dispose(); mesh.dispose(); }
    this._markerMeshes = [];
    for (const t of this._tubes) t.geometry.dispose();
    if (this._tubeMaterial) this._tubeMaterial.dispose();
    this._tubes = [];
    this._tubeMaterial = null;
    this._clearPrims();
    if (this.scene) this.scene.traverse((o) => { if (o.isGridHelper) { o.geometry.dispose(); o.material.dispose(); } });
    for (const m of this._wsMaterials || []) m.dispose();
    for (const g of this._wsGeometries || []) g.dispose();
    this._wsMaterials = this._wsGeometries = null;
    this._ws = null;
    this.series = [];
    this.paths = [];
    this.rigs = [];
    this.scene = null;
    this.$markers.innerHTML = '';
  }

  // ------------------------------------------------------------------------------------------------ time
  /** Every marker and robot at t, the window's uniforms to [t − decay, t], then the overlay and one frame. Nothing
      here builds geometry: a clock tick is uniform writes and a few binary searches. */
  _place(t) {
    this.t = t;
    const st = this.stageKeys || { show: 'all' };
    const w = timeWindow(st, t, this.t0);
    const o = this.tOrigin || 0;
    this.uniforms.dvWin.value.set(w.lo === null ? -1e30 : w.lo - o, w.hi === null ? 1e30 : w.hi - o);
    this.uniforms.dvFade.value.set(w.fadeFrom - o, w.fadeSpan, w.fade ? 1 : 0);
    this.window = w;
    const tmp = new Vector3(), q = new Quaternion();
    for (const s of this.series) {
      if (!s.marker) continue;
      const v = s.sampler.at(t);
      const ok = v[0] !== null && v[1] !== null && v[2] !== null;
      s.marker.visible = ok;
      if (ok) s.marker.position.set(v[0], v[1], v[2]);
      if (s.robot) {
        // each link node to its row pose at t: origins lerped, orientations slerped (MuJoCo's wxyz → three's xyzw)
        const poses = poseAt(s.sampler, t, s.robotOffset, s.robot.nodes.length);
        s.robot.root.visible = !!poses;
        if (poses) poses.forEach(({ p, q: r }, k) => { const n = s.robot.nodes[k]; n.position.set(p[0], p[1], p[2]); n.quaternion.set(r[1], r[2], r[3], r[0]); });
        continue;   // the meshes stand in for the stick
      }
      this._poseStick(s, v.slice(3), tmp, q);
    }
    for (const m of this.paths) {
      const p = pathAt(m.path, t);
      m.marker.visible = !!p;
      if (p) m.marker.position.set(p[0], p[1], p[2]);
    }
    this._syncMarkers();
    for (const rig of this.rigs) {
      if (rig.robot) {
        const poses = poseAt(rig.sampler, t, 0, rig.robot.nodes.length);
        rig.robot.root.visible = !!poses;
        if (poses) poses.forEach(({ p, q: r }, k) => { const n = rig.robot.nodes[k]; if (n) { n.position.set(p[0], p[1], p[2]); n.quaternion.set(r[1], r[2], r[3], r[0]); } });
      } else {
        // the stick through the link origins while the GLB loads (or for good when it failed)
        const v = rig.sampler.at(t);
        const origins = [];
        for (let k = 0; k * 7 < v.length; k++) origins.push(v[k * 7], v[k * 7 + 1], v[k * 7 + 2]);
        this._poseStick(rig, origins, tmp, q);
      }
    }
    const hasMarkers = this.series.some((s) => s.marker) || this.paths.length;
    this.$t.textContent = typeof t === 'number' && hasMarkers ? `t ${fmtTime(t)}${this.clock.hover !== null && this.clock.hover !== undefined ? ' (hover)' : ''}` : '';
    this._project();
    this._schedule();
  }

  _poseStick(s, flat, tmp, q) {
    for (let k = 0; k < s.joints.length; k++) {
      const p = flat.slice(k * 3, k * 3 + 3);
      const j = s.joints[k];
      j.visible = p.length === 3 && p.every((c) => c !== null && c !== undefined);
      if (j.visible) j.position.set(p[0], p[1], p[2]);
      if (k) {
        const a = s.joints[k - 1], l = s.links[k - 1];
        l.visible = a.visible && j.visible;
        if (!l.visible) continue;
        tmp.subVectors(j.position, a.position);
        const len = tmp.length();
        l.visible = len > 1e-9;
        if (!l.visible) continue;
        l.position.addVectors(a.position, j.position).multiplyScalar(0.5);
        l.quaternion.copy(q.setFromUnitVectors(Y, tmp.divideScalar(len)));
        l.scale.set(s.rod, len, s.rod);
      }
    }
  }

  /** Each [data-marker] onto its sphere's projection, in CSS px over the canvas. */
  _project() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    const cam = this.stage.camera;
    cam.updateMatrixWorld();
    const v = new Vector3();
    const place = (marker, dot, shown) => {
      v.copy(marker.position).project(cam);
      const out = !shown || !w || v.z > 1 || Math.abs(v.x) > 1.05 || Math.abs(v.y) > 1.05;
      dot.hidden = out;
      if (!out) dot.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px)`;
    };
    for (const s of this.series) if (s.dot) place(s.marker, s.dot, s.marker.visible && s.group.visible);
    for (const m of this.paths) place(m.marker, m.dot, m.marker.visible && !m.hidden);
  }

  // ------------------------------------------------------------------------------------------------ camera
  _cameraMoved() {
    this.root.toggleAttribute('data-ortho', !!this.stage.proj.ortho);
    this.$face.value = this.stage.proj.name;
    this.stage.drawAxes();
    this.root.toggleAttribute('data-axes', !this.stage.axesEl.hidden);
    if (this.ground) this.ground.visible = !this.stage.proj.ortho;
    this._hint();
    this._project();
    this._schedule();
  }

  _fit() { if (this.stage.fit()) { this._project(); this._schedule(); } }

  /** A cube ball, the projection menu or "3D": turn there, then write the projection to the view (host.setView), so
      it rides in the URL and Save view. */
  _goFace(name) {
    const commit = (projection) => {
      this.stage.wanted = projection;
      const spec = (this.input && this.input.view[this.type]) || {};
      if (spec.projection === projection || (projection === 'perspective' && spec.projection === undefined)) { this._cameraMoved(); return; }
      this.host.setView({ [this.type]: { ...spec, projection } });
    };
    this.stage.go(name, commit);
  }

  _resized() {
    this.stage.resized();
    this._project();
    this._schedule();
  }

  // ------------------------------------------------------------------------------------------------ drawing
  _schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._render(); });
  }

  _render() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!this.near || !this.scene || !w || !h) return;   // drawn when it comes near (the observer schedules it)
    if (!this.gl) { this.gl = sharedGL(); this.gl.register(this); }
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    for (const p of this.prims) for (const m of p.materials) if (m.isLineMaterial) m.resolution.set(w * dpr, h * dpr);
    if (!this.gl.draw(this.canvas, this.scene, this.stage.camera, w * dpr, h * dpr)) return;
    this.renders++;
    // read before the cube's overlay renders (each render() resets three's info)
    const info = this.gl.sharedRenderer().info.render;
    this._triangles = info.triangles;
    this._calls = info.calls;
    if ((this.robot && this.series.some((s) => s.robot && s.robot.root.visible)) || this.rigs.some((r) => r.robot && r.robot.root.visible)) {
      this._robotDrawn = true;
      const r = this.robot || this._rigRobot;
      if (r && r.readyMs === null) r.readyMs = performance.now();
    }
    if (!this.problem) this.stage.drawCube(this.gl, dpr);
    this.$poster.hidden = !this.problem;
  }

  // ------------------------------------------------------------------------------------------------ the hook
  /** The browser checks' hook: what the card drew, in its own numbers (tests/browser/p1b_checks.py lists it). */
  _hook(view) {
    const win = () => (view.window ? [view.window.lo, view.window.hi] : [null, null]);
    return {
      camera: () => view.stage.info(),
      markers: () => Object.fromEntries([
        ...view.series.filter((s) => s.marker && s.marker.visible && s.group.visible).map((s) => [s.name, s.marker.position.toArray()]),
        ...view.paths.filter((m) => m.marker.visible && !m.hidden).map((m) => [m.path.key, m.marker.position.toArray()]),
      ]),
      // the series the scene draws now (the legend hides the rest)
      visible: () => Object.fromEntries([...view.series.filter((s) => s.group.visible).map((s) => [s.name, true]),
        ...(view.model ? view.model.legend.filter((e) => view.legend.shows(e.name)).map((e) => [e.name, true]) : [])]),
      joints: () => Object.fromEntries(view.series.filter((s) => s.joints.length).map((s) => [s.name, s.joints.filter((j) => j.visible).map((j) => j.position.toArray())])),
      colors: () => {
        const series = Object.fromEntries(view.series.map((s) => [s.name, hex(s.color)]));
        // as drawn: the colour of the first item a series has in a primitive's buffers
        for (const p of view.prims) {
          // full frames wear the axis colours and an arc's reference Z is muted: neither is the series' hue
          if (p.kind === 'frames' || p.kind === 'arcs') continue;
          const attr = p.object.geometry.attributes.instanceColorStart || p.object.geometry.attributes.color;
          if (!attr) continue;
          for (let i = 0; i < p.series.length; i++) {
            const name = p.series[i];
            const real = view.model && view.model.series.find((s) => s.legendName === name && !series[s.name]);
            const key = real ? real.name : name;
            if (series[key] !== undefined) continue;
            series[key] = hex(new Color().setRGB(attr.getX(i), attr.getY(i), attr.getZ(i)));
          }
        }
        if (view.model) for (const s of view.model.series) if (series[s.name] === undefined) series[s.name] = hex(new Color(s.css));
        return { grid: view.gridColor ? hex(view.gridColor) : null, series };
      },
      renders: () => view.renders,
      // path_overlay color (CONTRACT §35): every painted line segment of the non-target paths, its series, the number at its
      // start sample and its start vertex's colour read back from the GPU buffer (sRGB hex, as colors() reads)
      overlay: () => {
        const o = (view.model && view.model.overlay) || {};
        const segments = [];
        for (const p of view.prims) {
          if (p.kind !== 'line' || !p.values) continue;
          const attr = p.object.geometry.attributes.instanceColorStart;
          for (let i = 0; i < p.series.length; i++) {
            segments.push({ series: p.nameOf[i], value: Number.isFinite(p.values[i]) ? p.values[i] : null, color: hex(new Color().setRGB(attr.getX(i), attr.getY(i), attr.getZ(i))) });
          }
        }
        return { color: o.color ?? null, min: o.min ?? null, max: o.max ?? null, segments };
      },
      // path_overlay tolerance: the tube's radius, the target path's points (the first run's; `paths` holds every run's) and
      // its rings, each cross-section of the TubeGeometry: its centre on the curve and its points from the position buffer
      tube: () => {
        const tubes = view._tubes;
        if (!tubes.length) return { radius: null, path: [], paths: [], rings: [] };
        const rings = [];
        for (const t of tubes) {
          const pos = t.geometry.attributes.position, per = t.radial + 1;
          for (let i = 0; i <= t.tubular; i++) {
            const points = [];
            for (let j = 0; j < per; j++) points.push([pos.getX(i * per + j), pos.getY(i * per + j), pos.getZ(i * per + j)]);
            rings.push({ center: t.curve.getPointAt(i / t.tubular).toArray(), points });
          }
        }
        return { radius: view.model.tube.radius, path: tubes[0].points, paths: tubes.map((t) => t.points), rings };
      },
      robot() {
        const r = view.robot || view._rigRobot;
        if (!r) return { state: 'none' };
        const links = {};
        const p = new Vector3(), q = new Quaternion();
        const owners = [...view.series.filter((s) => s.robot && s.robot.root.visible).map((s) => [s.name, s.robot]), ...view.rigs.filter((g) => g.robot && g.robot.root.visible).map((g) => [g.name, g.robot])];
        for (const [name, robot] of owners) {
          robot.root.updateWorldMatrix(true, true);
          links[name] = Object.fromEntries(r.links.map((l, k) => {
            const n = robot.nodes[k];
            if (!n) return [l, null];
            n.getWorldPosition(p);
            n.getWorldQuaternion(q);
            return [l, { p: p.toArray(), q: [q.w, q.x, q.y, q.z] }];
          }));
        }
        return { state: r.state, url: r.url, error: r.error || null, drawn: !!view._robotDrawn, readyMs: r.readyMs ?? null,
          series: [...view.series.filter((s) => s.robot).map((s) => s.name), ...view.rigs.map((g) => g.name)], ghost: (view.series.find((s) => s.isGhost) || {}).name ?? null,
          triangles: view._triangles ?? null, links };
      },
      window: () => { const w = view.window || {}; const st = view.stageKeys || {}; return { t: view.t, lo: w.lo ?? null, hi: w.hi ?? null, show: st.show, decay: st.decay, fade: st.fade }; },
      drawn: () => {
        const [lo, hi] = win();
        const out = {};
        for (const p of view.prims) {
          if (p.kind !== 'line') continue;
          for (let i = 0; i < p.series.length; i++) {
            if (!p.shows(i, lo, hi)) continue;
            const name = p.series[i];
            // a segment's samples inside the window, as the fragment shader cuts it
            for (const tt of [p.t[2 * i], p.t[2 * i + 1]]) {
              if ((lo !== null && tt < lo) || (hi !== null && tt > hi)) continue;
              const o = out[name] || (out[name] = { first: tt, last: tt, n: 0 });
              o.first = Math.min(o.first, tt); o.last = Math.max(o.last, tt);
            }
          }
        }
        for (const m of view.paths) {
          const o = out[m.path.series];
          if (!o) continue;
          let n = 0;
          for (let i = 0; i < m.path.n; i++) if ((lo === null || m.path.t[i] >= lo) && (hi === null || m.path.t[i] <= hi)) n++;
          o.n += n;
        }
        return out;
      },
      builds: () => view.builds,
      size: () => ({ items: view.prims.reduce((n, p) => n + p.items, 0) }),
      counts: () => {
        const [lo, hi] = win();
        const out = {};
        const key = { line: 'line', points: 'points', frames: 'frames', 'frames-z': 'frames-z', arrows: 'arrows', arcs: 'arcs', boxes: 'boxes' };
        for (const p of view.prims) for (const [name, n] of Object.entries(p.count(lo, hi))) {
          const o = out[name] || (out[name] = { line: 0, points: 0, frames: 0, 'frames-z': 0, arrows: 0, arcs: 0 });
          o[key[p.kind]] = (o[key[p.kind]] || 0) + n;
        }
        return out;
      },
      geometry: (series, mode) => {
        const [lo, hi] = win();
        const kind = mode === 'line' ? 'line' : mode;
        const items = [], times = [];
        for (const p of view.prims) {
          if (p.kind !== kind) continue;
          const g = p.geometry(series, lo, hi);
          items.push(...g.items);
          times.push(...g.times);
        }
        return mode === 'points' ? { points: items.map((x) => x.point), times } : { segments: items.map((x) => x.segment), times };
      },
      // compare (PEP 0010 P1d): every arrow drawn now, its numbers as read (float64) and its shaft from the GPU buffer
      arrows: () => {
        const [lo, hi] = win();
        const out = [];
        for (const p of view.prims) {
          if (p.kind !== 'arrows' || !p.arrows) continue;
          p.arrows.forEach((a, i) => {
            if (!p.shows(i, lo, hi)) return;
            const s = p.read(i).segment;
            out.push({ series: a.series, t: a.t, from: a.from, to: a.to, tip: a.tip, drawn: { from: s[0], tip: s[1] } });
          });
        }
        return out;
      },
      // every Z-arc drawn now: its anchor and quaternions as read, and from the buffer the own Z, the reference Z and
      // the arc's points, own tip to reference tip
      arcs: () => {
        const [lo, hi] = win();
        const out = [];
        for (const p of view.prims) {
          if (p.kind !== 'arcs' || !p.arcs) continue;
          p.arcs.forEach((a, k) => {
            const i = k * p.per;
            if (!p.shows(i, lo, hi)) return;
            const seg = (j) => p.read(i + j).segment;
            const chords = Array.from({ length: p.per - 2 }, (_, j) => seg(2 + j));
            out.push({ series: a.series, t: a.t, at: a.at, own: a.own, ref: a.ref,
              drawn: { own: seg(0), ref: seg(1), arc: [...chords.map((c) => c[0]), chords[chords.length - 1][1]] } });
          });
        }
        return out;
      },
      robots: () => Object.fromEntries(view.rigs.map((g) => {
        const mats = g.material ? [g.material] : [...new Set(g.materials)];
        const m = mats[0];
        return [g.name, { color: m ? hex(m.color) : g.css, opacity: m ? m.opacity : g.opacity, visible: g.group.visible && (!!g.robot ? g.robot.root.visible : true), state: g.robot ? 'mesh' : 'stick' }];
      })),
      problem: () => view.problem || null,
      // PEP 0010 P2: the draw calls of the card's last frame (renderer.info.render.calls, before the cube is drawn) and
      // the scene's visible drawn objects, each with its role, so a check can hold the calls to "≤ 1 per layer"
      calls: () => view._calls,
      drawables: () => {
        const out = [];
        if (!view.scene) return out;
        view.scene.traverseVisible((o) => {
          if (!(o.isMesh || o.isLine || o.isPoints || o.isSprite)) return;
          let role = o.userData.role;
          for (let q = o.parent; !role && q; q = q.parent) role = q.userData.role;
          const g = o.geometry;
          const items = o.isInstancedMesh ? o.count : g && g.attributes.instanceStart ? g.attributes.instanceStart.count : g && g.attributes.position ? g.attributes.position.count : 0;
          out.push({ role: role || o.type, kind: o.type, items });
        });
        return out;
      },
      // draw now (a check that changed the DOM under the card, e.g. hid the cube); the number of frames drawn
      frame: () => { cancelAnimationFrame(view._raf); view._raf = 0; view._render(); return view.renders; },
      // the paths each series' line layers draw (trajectory3d's run: one per run and body), by series name
      paths: () => {
        const out = {};
        for (const p of view.prims) {
          if (p.kind !== 'line' || !p.pathOf) continue;
          const by = new Map();
          for (let i = 0; i < p.series.length; i++) {
            if (!p.shows(i, null, null)) continue;
            const s = p.nameOf[i];
            if (!by.has(s)) by.set(s, new Set());
            by.get(s).add(p.pathOf[i]);
          }
          for (const [s, keys] of by) out[s] = (out[s] || 0) + keys.size;
        }
        return out;
      },
      // each path's alpha as the shader multiplies it: the line material's opacity × the path's dvAlpha, read back
      // from the uploaded Float32Array (opacity: auto is exactly 1/n, PEP 0010 P2)
      opacity: () => {
        const out = {};
        for (const p of view.prims) {
          if (p.kind !== 'line' || !p.pathOf) continue;
          const attr = p.alphaAttrs[0].array, mat = p.materials[0];
          for (let i = 0; i < p.series.length; i++) {
            if (p.hidden.has(p.series[i]) || !(attr[i] > 0)) continue;
            const s = p.nameOf[i];
            const o = out[s] || (out[s] = { paths: new Set(), material: mat.opacity, attribute: new Set(), alpha: new Set() });
            o.paths.add(p.pathOf[i]);
            o.attribute.add(attr[i]);
            o.alpha.add(mat.opacity * attr[i]);
          }
        }
        return Object.fromEntries(Object.entries(out).map(([s, o]) => [s, { paths: o.paths.size, material: o.material, attribute: [...o.attribute], alpha: [...o.alpha] }]));
      },
      // the workspace outline as drawn: its fill's and its edges' vertices in world units (unit scale applied)
      workspace: () => {
        const fill = [], edges = [];
        if (view._ws) {
          view._ws.updateMatrixWorld(true);
          const v = new Vector3();
          view._ws.traverse((o) => {
            const role = o.userData.role;
            if ((role !== 'workspace-fill' && role !== 'workspace-edges') || !o.geometry) return;
            const pos = o.geometry.attributes.position;
            for (let i = 0; i < pos.count; i++) (role === 'workspace-fill' ? fill : edges).push(v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld).toArray());
          });
        }
        return { state: view._wsState || 'none', fill, edges };
      },
    };
  }
}

/* type: voxels (docs/CONTRACT.md §32; PEP 0010 §5.3): scene3d's stage (camera, view cube, projection, unit, axes,
   workspace, render on demand through the page's one WebGL context) around its own scene, the grid's boxes in 3D or
   the slice's image heatmap in 2D (src/voxels/). It has no time: the clock never redraws it. */
class VoxelsView extends Scene3dView {
  constructor(host, el) {
    super(host, el);
    this.root.classList.add('dv-voxels');
    this.controls.destroy();   // the strip under the stage is the slice's here, not trajectory3d's
    this.$ramp = document.createElement('div');
    this.$ramp.className = 'dv-voxels-ramp';
    this.$ramp.dataset.ramp = '';
    this.$legend.after(this.$ramp);
    this._onSlice = (e) => this._sliceEvent(e);
    this.$controls.addEventListener('click', this._onSlice);
    this.$controls.addEventListener('change', this._onSlice);
    this._onHoverMove = (e) => this._hoverCell(e);
    this._onHoverLeave = () => this._hoverCell(null);
    this.canvas.addEventListener('pointermove', this._onHoverMove);
    this.canvas.addEventListener('pointerleave', this._onHoverLeave);
  }

  destroy() {
    this.$controls.removeEventListener('click', this._onSlice);
    this.$controls.removeEventListener('change', this._onSlice);
    this.canvas.removeEventListener('pointermove', this._onHoverMove);
    this.canvas.removeEventListener('pointerleave', this._onHoverLeave);
    super.destroy();
  }

  update(input) {
    this.input = input;
    this.type = 'voxels';
    const spec = input.view.voxels && typeof input.view.voxels === 'object' ? input.view.voxels : {};
    this.spec = spec;
    const stage = stageOf(spec, 'voxels');
    this.stageKeys = { ...stage, show: 'all' };
    const rows = input.rows || [];
    // refit when the data or the binding changes, never for the slice, the projection or a stage key
    const fitKey = JSON.stringify(['voxels', spec.x, spec.y, spec.z, spec.cell, spec.value, spec.summary, spec.min, rows.length, rows[0] && rows[0].id, rows.length && rows[rows.length - 1].id]);
    if (fitKey !== this._fitKey) this.stage.fitted = false;
    this._fitKey = fitKey;
    this.stage.setUp(stage.up);
    this.stage.unit = stage.unit;
    this.stage.axesMode = stage.axes;
    this.legend.draw([]);
    const problem = this._buildVoxels(input, spec, stage);
    this.problem = problem;
    this.$poster.hidden = !problem && this.renders > 0;
    this.$poster.firstElementChild.textContent = problem || '3D view';
    this.root.toggleAttribute('data-empty', !!problem);
    this.root.dataset.mode = this.vox && this.vox.mode ? this.vox.mode : '';
    this.stage.want(stage.projection);
    this._resized();
    this._schedule();
  }

  _buildVoxels(input, spec, stage) {
    const tokens = input.tokens || {};
    this._dispose();
    this.scene = new Scene();
    const model = voxelsModel(input, spec, stage);
    this.vox = model;
    // a frame column with one value names the frame on the axes ("x (mm) · frame: base")
    const frames = new Set();
    for (const r of input.rows || []) { const f = r.frame; if (f !== undefined && f !== null && f !== '') frames.add(String(f)); if (frames.size > 1) break; }
    this.stage.frame = frames.size === 1 ? [...frames][0] : null;
    this.$ramp.innerHTML = model.problem ? '' : rampHtml(model, spec, input.columns);
    this.$controls.hidden = !!model.problem;
    const strip = model.problem ? '' : sliceHtml(model, stage.unit);
    if (strip !== this._strip) {
      // WHY keep the focus: ▶ pressed from the keyboard redraws the strip, and the next Enter must step again
      const a = document.activeElement;
      const attr = a && this.$controls.contains(a) ? ['data-slice-step', 'data-slice', 'data-slice-all', 'data-slice-axis'].find((n) => a.hasAttribute(n)) : null;
      const sel = attr === 'data-slice-step' ? `[data-slice-step="${a.getAttribute(attr)}"]` : attr ? `[${attr}]` : null;
      this.$controls.innerHTML = strip;
      this._strip = strip;
      const again = sel && this.$controls.querySelector(sel);
      if (again) again.focus();
    }
    if (model.problem) return model.problem;
    const box = buildScene(this, model, spec);
    const pts = [box.min, box.max];
    if (stage.workspace && Array.isArray(stage.workspace.box)) pts.push(...stage.workspace.box);
    const full = bbox(pts);
    this.box = full;
    this.stage.setBox(full);
    this._size = Math.max(Math.hypot(full.max[0] - full.min[0], full.max[1] - full.min[1], full.max[2] - full.min[2]) / 2, 1e-9);
    const cs = getComputedStyle(this.el);
    const look = { workspace: cs.getPropertyValue('--dv-s3-workspace').trim() || tokens.muted || '#71717a' };
    if (model.mode === '3d') this._grid(full, stage, tokens);
    this._workspace(stage, input, tokens, look);
    this._hint();
    return null;
  }

  _dispose() {
    for (const { mesh, material } of this._voxObjects || []) { material.dispose(); if (mesh.isInstancedMesh) mesh.dispose(); }
    for (const g of this._voxGeometries || []) g.dispose();
    for (const t of this._voxTextures || []) t.dispose();
    this._voxObjects = this._voxGeometries = this._voxTextures = null;
    this.ground = null;
    super._dispose();
  }

  // the clock does not move voxels: a tick redraws nothing
  _place() {}

  _hint() {
    const m = this.vox;
    const parts = [this.stage.proj.ortho ? 'Drag to pan · scroll to zoom · double-click to fit' : 'Drag to orbit · scroll to zoom · double-click to reset'];
    if (m && m.mode === '2d') parts.unshift('slice ◀ ▶ one cell');
    this.$hint.textContent = parts.join(' · ');
  }

  /** The strip: ◀ ▶ step one cell, the range picks one, All shows the projection, the axis (3D) picks the slice's axis;
      each writes the view entry's `slice` (host.setView: the URL, Save view). */
  _sliceEvent(e) {
    const m = this.vox;
    if (!m || !m.grid || m.problem) return;
    const t = e.target;
    let next = null;
    if (e.type === 'click') {
      const b = t.closest('button');
      if (!b || !this.$controls.contains(b)) return;
      if (b.hasAttribute('data-slice-step')) next = sliceFor(m, 'step', Number(b.dataset.sliceStep));
      else if (b.hasAttribute('data-slice-all')) next = sliceFor(m, 'all');
    } else if (t.matches('[data-slice]')) next = sliceFor(m, 'k', t.value);
    else if (t.matches('[data-slice-axis]')) next = sliceFor(m, 'axis', t.value);
    if (!next) return;
    const spec = (this.input && this.input.view.voxels) || {};
    this.host.setView({ voxels: { ...spec, slice: next } });
  }

  /** In 2D, the cell under the pointer: its ranges on the plane's two axes and its value, in the card's foot. */
  _hoverCell(e) {
    const m = this.vox;
    if (!e || !m || m.mode !== '2d' || !m.plane || !this.stage.proj.ortho) { if (this.$t.textContent) this.$t.textContent = ''; return; }
    const r = this.canvas.getBoundingClientRect();
    const v = new Vector3(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1, 0);
    const cam = this.stage.camera;
    cam.updateMatrixWorld();
    v.unproject(cam);
    const P = m.plane, g = m.flat || m.grid;
    const u = AXES.indexOf(P.plane[0]), w = AXES.indexOf(P.plane[1]);
    const i = cellIndex(v.getComponent(u), g.cell, g.origin[u]), j = cellIndex(v.getComponent(w), g.cell, g.origin[w]);
    const val = P.values[j - P.j0] ? P.values[j - P.j0][i - P.i0] : undefined;
    if (val === undefined) { this.$t.textContent = ''; return; }
    const range = (a, k) => `${AXES[a]} ${fmtValue(g.origin[a] + k * g.cell)}–${fmtValue(g.origin[a] + (k + 1) * g.cell)}`;
    const what = m.grid.value === 'property' ? m.grid.summary.toLowerCase() : { count: 'rows', time: 's', runs: 'runs' }[m.grid.value];
    this.$t.textContent = `${range(u, i)} · ${range(w, j)} ${this.stage.unit} · ${val === null ? 'empty' : `${fmtValue(val)} ${what}`}`;
  }

  _hook(view) {
    return {
      ...super._hook(view),
      // every cell holding rows, as binned: {cell, origin, value, cells: [[i, j, k, value]…]}
      cells: () => {
        const g = view.vox && view.vox.grid;
        if (!g) return null;
        return { cell: g.cell, origin: [...g.origin], value: g.property || g.value, cells: g.cells.map((c) => [c.i, c.j, c.k, c.value]) };
      },
      // the slice as drawn: in 2D the texture's plane, in 3D the solid one
      slice: () => {
        const m = view.vox;
        if (!m || !m.slice) return null;
        const s = { axis: m.slice.axis, at: m.slice.at, k: m.slice.k, all: !!m.slice.all, mode: m.mode };
        if (m.mode === '2d' && m.plane) Object.assign(s, { plane: m.plane.plane, i0: m.plane.i0, j0: m.plane.j0, width: m.plane.width, height: m.plane.height, values: m.plane.values });
        return s;
      },
      ramp: () => {
        const m = view.vox;
        if (!m || !m.ramp) return null;
        return { lo: m.ramp.lo, hi: m.ramp.hi, domain: [...m.domain], family: m.family };
      },
      // each cell's box, read back from its instance matrix (3D)
      boxes: () => {
        const out = [];
        const mtx = new Matrix4(), p = new Vector3(), q = new Quaternion(), s = new Vector3();
        for (const { mesh } of view._voxObjects || []) {
          if (!mesh.isInstancedMesh) continue;
          for (let i = 0; i < mesh.count; i++) {
            mesh.getMatrixAt(i, mtx);
            mtx.decompose(p, q, s);
            out.push({ c: p.toArray(), s: s.toArray(), solid: mesh.userData.role === 'voxels-solid' });
          }
        }
        return out;
      },
      // every drawn cell with the colour it was drawn in, read back from the GPU's side of the scene (sRGB hex, as colors()
      // reads): 3D, the instance colour buffer of the cell's box; 2D, the texel of its pixel. [i, j, k, value, '#rrggbb']; in
      // 2D the plane's own axis holds the slice's k (null for the projection through all of it)
      cellColours: () => {
        const m = view.vox;
        const out = [];
        if (!m || m.problem) return out;
        if (m.mode === '3d') {
          for (const { mesh } of view._voxObjects || []) {
            const cells = mesh.userData.cells;
            if (!mesh.isInstancedMesh || !cells || !mesh.instanceColor) continue;
            const buf = mesh.instanceColor;
            cells.forEach((c, n) => out.push([c.i, c.j, c.k, c.value, hex(new Color().setRGB(buf.getX(n), buf.getY(n), buf.getZ(n)))]));
          }
          return out;
        }
        const P = m.plane, a = AXES.indexOf(P.axis), u = AXES.indexOf(P.plane[0]), w = AXES.indexOf(P.plane[1]);
        const shown = (v) => !(typeof view.spec.min === 'number' && Number.isFinite(view.spec.min)) || v >= view.spec.min;
        for (let r = 0; r < P.height; r++) for (let c = 0; c < P.width; c++) {
          const val = P.values[r][c];
          if (val === null || !shown(val)) continue;
          const o = (r * P.width + c) * 4, d = m.texture.data;
          const idx = [null, null, null];
          idx[u] = P.i0 + c; idx[w] = P.j0 + r; idx[a] = m.slice.k;
          out.push([...idx, val, `#${[d[o], d[o + 1], d[o + 2]].map((x) => x.toString(16).padStart(2, '0')).join('')}`]);
        }
        return out;
      },
      colour: (v) => (view.vox && view.vox.ramp ? colourOf(view.vox, v) : null),
      centre: (i, j, k) => (view.vox ? [centreOf(view.vox.grid, 0, i), centreOf(view.vox.grid, 1, j), centreOf(view.vox.grid, 2, k)] : null),
    };
  }
}
