/* The 3D engine behind <data-mesh> (dist/views/mesh.js). The element itself is in the core
   (packages/core/src/elements/data-mesh.js): it draws the poster and loads this bundle the first time a model is
   needed (a hover, a click, an open peek), so a gallery of 2,000 cards pays for no 3D until someone reaches for it.

   STOCK PARTS: three 0.186.1 (WebGLRenderer, GLTFLoader + MeshoptDecoder, OBJLoader, STLLoader, PLYLoader). The
   pattern is three's own "multiple elements" example and <model-viewer>'s Renderer singleton: ONE WebGL context for
   the page, each live element rendered into a viewport of it, then copied (drawImage) into that element's own 2D
   canvas. OURS: the cap on live elements, the model cache, the turntable/orbit input, framing.

   WHY one renderer: browsers keep about 16 live WebGL contexts per page (Chromium: 16, then "the oldest context will
   be lost"), so a gallery cannot give each card its own; and a context costs tens of MB of GPU memory. Here the count
   is 1 whatever the gallery's size. WHY copy into a 2D canvas instead of one canvas behind the page: the cards are
   virtualised and scroll in their own box (or the page), and a 2D canvas keeps the last frame where the card is, so a
   card you spun keeps its angle, with nothing to re-sync on scroll. */

import {
  WebGLRenderer, Scene, PerspectiveCamera, HemisphereLight, DirectionalLight, Box3, Vector3, Sphere, Group, Mesh,
  MeshStandardMaterial, SRGBColorSpace, NeutralToneMapping, BufferGeometry, Matrix4, Color,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

/** How many elements may animate at once; the oldest live one freezes on its last frame when one more starts. */
export const MAX_LIVE = 4;
/** Models kept parsed (GPU buffers); the least recently used is disposed past this. */
export const MAX_MODELS = 48;
const FOV = 30;
const SPIN = 50; // degrees per second, a turntable's pace
const DEG = Math.PI / 180;

let renderer = null;
let lost = false;
const scene = new Scene();
const camera = new PerspectiveCamera(FOV, 1, 0.001, 100);
const rig = new Group();
scene.add(rig);
const models = new Map(); // url -> {promise, model, radius, center, used, bytes}
const live = new Set(); // elements animating now (<= MAX_LIVE)
const states = new WeakMap(); // element -> {yaw, pitch, zoom, auto, dragging, ...}
let raf = 0;
let last = 0;
const stats = { contexts: 0, contextsMade: 0, contextLost: 0, frames: 0, renderMs: 0, modelsLoaded: 0, bytes: 0, liveMax: 0, firstModelMs: null };

function lights(dark) {
  for (const c of [...scene.children]) if (c !== rig) scene.remove(c);
  scene.add(new HemisphereLight(0xffffff, dark ? 0x30343c : 0x8d8a84, dark ? 1.6 : 1.9));
  const key = new DirectionalLight(0xffffff, 2.2);
  key.position.set(2, 3, 2.5);
  scene.add(key);
  const fill = new DirectionalLight(0xffffff, 0.8);
  fill.position.set(-2.5, 1, -1.5);
  scene.add(fill);
}
lights(false);

function ensureRenderer() {
  if (renderer && !lost) return renderer;
  const canvas = document.createElement('canvas'); // never in the DOM: elements show copies of it
  canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); lost = true; stats.contextLost++; stats.contexts = 0; });
  canvas.addEventListener('webglcontextrestored', () => { lost = false; renderer = null; for (const m of models.values()) m.gpuStale = true; });
  renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(1); // sizes below are device pixels already
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = NeutralToneMapping;
  renderer.setClearColor(0x000000, 0);
  lost = false;
  stats.contexts = 1;
  stats.contextsMade++;
  return renderer;
}

// ------------------------------------------------------------------------------------------------ models
const gltf = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);

function neutral(object) {
  object.traverse((o) => {
    if (o.isMesh && (!o.material || (!o.material.map && !o.geometry.attributes.color))) {
      o.material = new MeshStandardMaterial({ color: o.material && o.material.color ? o.material.color : 0xb9b6ae, roughness: 0.75, metalness: 0 });
    }
  });
  return object;
}

async function parse(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  const buf = await res.arrayBuffer();
  stats.bytes += buf.byteLength;
  const ext = (/\.([a-z0-9]+)(?:[?#]|$)/i.exec(url) || [])[1]?.toLowerCase();
  const base = url.slice(0, url.lastIndexOf('/') + 1);
  let object;
  if (ext === 'obj') object = new OBJLoader().parse(new TextDecoder().decode(buf));
  else if (ext === 'stl' || ext === 'ply') {
    const geometry = (ext === 'stl' ? new STLLoader() : new PLYLoader()).parse(buf);
    if (!geometry.attributes.normal) geometry.computeVertexNormals();
    object = new Mesh(geometry, new MeshStandardMaterial({ color: 0xb9b6ae, roughness: 0.75, vertexColors: !!geometry.attributes.color }));
  } else object = (await gltf.parseAsync(buf, base)).scene; // glb / gltf (glTF is the default: it is the web's format)
  neutral(object);
  // framing: the bounding sphere around the box's centre (a turntable spins about the vertical axis through it)
  const box = new Box3().setFromObject(object);
  const center = box.getCenter(new Vector3());
  const radius = Math.max(1e-4, box.getBoundingSphere(new Sphere()).radius);
  object.position.sub(center);
  const holder = new Group();
  holder.add(object);
  return { model: holder, radius, bytes: buf.byteLength };
}

function model(url) {
  let entry = models.get(url);
  if (!entry) {
    const t0 = performance.now();
    entry = { promise: null, model: null, used: 0 };
    entry.promise = parse(url).then((m) => {
      Object.assign(entry, m);
      stats.modelsLoaded++;
      if (stats.firstModelMs == null) stats.firstModelMs = performance.now() - t0;
      evict();
      return entry;
    });
    entry.promise.catch(() => models.delete(url));
    models.set(url, entry);
  }
  entry.used = performance.now();
  return entry.promise;
}

function dispose(object) {
  object.traverse((o) => {
    if (o.geometry instanceof BufferGeometry) o.geometry.dispose();
    for (const m of [].concat(o.material || [])) {
      for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();
      m.dispose();
    }
  });
}

function evict() {
  if (models.size <= MAX_MODELS) return;
  const inUse = new Set([...live].map((el) => el.src));
  const old = [...models.entries()].filter(([u, e]) => e.model && !inUse.has(u)).sort((a, b) => a[1].used - b[1].used);
  while (models.size > MAX_MODELS && old.length) {
    const [u, e] = old.shift();
    dispose(e.model);
    models.delete(u);
  }
}

// ------------------------------------------------------------------------------------------------ drawing
/* The poster's camera (CONTRACT §23 `meshView`). WHY (Zach, 2026-10-26): "ideally the 3D view starts at the same
   location the thumbnail photo is taken from; right now it is often a bit smaller". A view is {dir, fov, box}: the
   camera's direction from the model's centre (glTF frame, +Y up), its vertical field of view in degrees, optionally
   its distance in metres (`dist`, when the poster is an uncropped render from a known camera), and optionally the
   poster's silhouette box [x0, y0, x1, y1] (0-1, y down: a cropped poster). The first frame looks along `dir` with `fov`, projects the
   model, and scales and shifts the projection so the model's silhouette lands on `box`: the poster's own framing,
   whatever crop or padding made the poster. Without a box the model is framed as a square poster is (contained). */
export const DEFAULT_VIEW = Object.freeze({ dir: [0.9, 0.8, 1.1], fov: 30 }); // object-db's scan posters (tools/render_thumbs.py)
const tmp = new Vector3();
const toNdc = new Matrix4();
const clear = new Color();

export function parseView(text) {
  if (!text) return DEFAULT_VIEW;
  try {
    const v = typeof text === 'string' ? JSON.parse(text) : text;
    const dir = Array.isArray(v.dir) && v.dir.length === 3 && v.dir.every(Number.isFinite) && Math.hypot(...v.dir) > 0 ? v.dir : DEFAULT_VIEW.dir;
    const fov = Number.isFinite(v.fov) && v.fov > 1 && v.fov < 170 ? v.fov : DEFAULT_VIEW.fov;
    const box = Array.isArray(v.box) && v.box.length === 4 && v.box.every(Number.isFinite) && v.box[2] > v.box[0] && v.box[3] > v.box[1] ? v.box : null;
    const dist = Number.isFinite(v.dist) && v.dist > 0 ? v.dist : null;
    return { dir, fov, box, dist };
  } catch { return DEFAULT_VIEW; }
}

/** The camera angles a view's direction means (yaw about +Y from +Z, pitch above the horizon). */
export function anglesOf(dir) {
  const n = Math.hypot(...dir);
  return { yaw: Math.atan2(dir[0], dir[2]), pitch: Math.asin(Math.max(-1, Math.min(1, dir[1] / n))) };
}

/** NDC scale and shift that put `from` (an NDC box [x0, y0, x1, y1], y up) onto `to`; one scale, so nothing stretches. */
export function fitBox(from, to) {
  const s = Math.sqrt(((to[2] - to[0]) / Math.max(1e-6, from[2] - from[0])) * ((to[3] - to[1]) / Math.max(1e-6, from[3] - from[1])));
  return { s, tx: (to[0] + to[2]) / 2 - s * (from[0] + from[2]) / 2, ty: (to[1] + to[3]) / 2 - s * (from[1] + from[3]) / 2 };
}

/** The poster's box in the element's NDC: the square poster contained (or covering) in a w x h box. */
export function posterNdc(box, w, h, fit = 'contain') {
  const S = fit === 'cover' ? Math.max(w, h) : Math.min(w, h);
  const ox = (w - S) / 2, oy = (h - S) / 2;
  const px = (u) => ((ox + u * S) / w) * 2 - 1;
  const py = (v) => 1 - ((oy + v * S) / h) * 2;
  return [px(box[0]), py(box[3]), px(box[2]), py(box[1])];
}

function stateOf(el) {
  let s = states.get(el);
  if (!s) {
    // WHY no turntable under reduced motion: the model still turns by drag, it just never moves on its own
    const still = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const view = parseView(el.getAttribute && el.getAttribute('view'));
    const a = anglesOf(view.dir);
    s = { view, home: a, yaw: a.yaw, pitch: a.pitch, zoom: 1, auto: !still, dragging: false, entry: null, frame: null, frameKey: '' };
    states.set(el, s);
  }
  return s;
}

/** The model's silhouette box in NDC from the current camera (sampled vertices; the model is a few thousand). */
function silhouette(model) {
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  model.updateMatrixWorld(true);
  model.traverse((o) => {
    const pos = o.isMesh && o.geometry && o.geometry.attributes.position;
    if (!pos) return;
    const step = Math.max(1, Math.ceil(pos.count / 6000));
    for (let i = 0; i < pos.count; i += step) {
      tmp.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld).project(camera);
      if (tmp.x < box[0]) box[0] = tmp.x;
      if (tmp.y < box[1]) box[1] = tmp.y;
      if (tmp.x > box[2]) box[2] = tmp.x;
      if (tmp.y > box[3]) box[3] = tmp.y;
    }
  });
  return Number.isFinite(box[0]) ? box : null;
}

function draw(el, s) {
  const r = ensureRenderer();
  const canvas = el.canvas;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(el.clientWidth * dpr));
  const h = Math.max(1, Math.round(el.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const gl = r.domElement;
  if (gl.width < w || gl.height < h) r.setSize(Math.max(gl.width, w), Math.max(gl.height, h), false);
  const H = gl.height;
  r.setViewport(0, 0, w, h);
  r.setScissor(0, 0, w, h);
  r.setScissorTest(true);
  // WHY a clear colour per element (Zach, 2026-10-26: "in the gallery the background is also white/lighter so it better
  // matches"): `background` match (the poster's own backdrop, sampled), light, or theme (transparent)
  const bg = el.background ? el.background() : null;
  if (bg) r.setClearColor(clear.set(bg), 1); else r.setClearColor(0x000000, 0);
  r.clear();
  const { model: m, radius } = s.entry;
  rig.add(m);
  camera.aspect = w / h;
  camera.fov = s.view.fov;
  // the poster's distance: the renderer's own (`dist`, metres: MuJoCo posters), else render_thumbs.py's rule (half the
  // box diagonal / sin(fov / 2) x 1.05); with a `box` the frame then lands the silhouette on the poster's
  const d = s.view.dist || radius / Math.sin((s.view.fov / 2) * DEG) * 1.05;
  camera.near = Math.max(radius / 100, d - radius * 4);
  camera.far = d + radius * 4;
  const place = (yaw, pitch) => {
    camera.position.set(d * Math.cos(pitch) * Math.sin(yaw), d * Math.sin(pitch), d * Math.cos(pitch) * Math.cos(yaw));
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    camera.updateProjectionMatrix();
  };
  const key = `${w}x${h}:${el.getAttribute('fit') || 'contain'}`;
  if (!s.frame || s.frameKey !== key) {
    // the frame is measured once per size, from the poster's direction: the turntable then keeps that scale
    place(s.home.yaw, s.home.pitch);
    const from = s.view.box ? silhouette(m) : null;
    s.frame = from ? fitBox(from, posterNdc(s.view.box, w, h, el.getAttribute('fit') || 'contain')) : { s: Math.min(1, w / h), tx: 0, ty: 0 };
    s.frameKey = key;
  }
  place(s.yaw, s.pitch);
  const z = s.frame.s * s.zoom;
  toNdc.set(z, 0, 0, s.frame.tx * s.zoom, 0, z, 0, s.frame.ty * s.zoom, 0, 0, 1, 0, 0, 0, 0, 1);
  camera.projectionMatrix.premultiply(toNdc);
  camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
  const t0 = performance.now();
  r.render(scene, camera);
  rig.remove(m);
  const ctx = el.ctx || (el.ctx = canvas.getContext('2d'));
  ctx.clearRect(0, 0, w, h);
  // WebGL's viewport (0, 0) is the canvas's bottom-left: the frame sits in the last h rows of the shared canvas
  ctx.drawImage(gl, 0, H - h, w, h, 0, 0, w, h);
  stats.renderMs = stats.renderMs * 0.9 + (performance.now() - t0) * 0.1;
  stats.frames++;
}

function tick(now) {
  raf = 0;
  const dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
  last = now;
  for (const el of [...live]) {
    if (!el.isConnected) { live.delete(el); continue; }
    const s = stateOf(el);
    if (!s.entry || !s.entry.model) continue;
    if (s.auto && !s.dragging && el.interact !== 'none') s.yaw += SPIN * DEG * dt;
    if (s.auto || s.dragging || s.dirty) { draw(el, s); s.dirty = false; }
  }
  if (live.size) raf = requestAnimationFrame(tick);
  else last = 0;
}

function kick() {
  if (!raf) raf = requestAnimationFrame(tick);
}

// ------------------------------------------------------------------------------------------------ the element's API
/** Start drawing `el` live (load its model first). Freezes the oldest live element past MAX_LIVE. */
export async function start(el) {
  const s = stateOf(el);
  s.want = true;
  const entry = await model(el.src);
  if (!s.want || !el.isConnected) return;
  s.entry = entry;
  if (!live.has(el)) {
    live.add(el);
    while (live.size > MAX_LIVE) {
      const oldest = live.values().next().value;
      live.delete(oldest);
      oldest.frozen();
    }
    stats.liveMax = Math.max(stats.liveMax, live.size);
  }
  draw(el, s); // the first frame now, so the poster can hide without a blank
  el.shown();
  kick();
}

/** Stop animating `el`; its canvas keeps the last frame. */
export function stop(el) {
  const s = states.get(el);
  if (s) s.want = false;
  live.delete(el);
}

/** Pointer and wheel input from the element: drag rotates (yaw, pitch); wheel zooms (orbit mode only). */
export function input(el, kind, a = 0, b = 0) {
  const s = stateOf(el);
  if (kind === 'down') { s.dragging = true; s.auto = false; }
  else if (kind === 'up') { s.dragging = false; s.dirty = true; if (el.interact === 'hover') s.auto = true; }
  else if (kind === 'drag') { s.yaw -= a * 0.6 * DEG; s.pitch = Math.max(-80 * DEG, Math.min(80 * DEG, s.pitch + b * 0.5 * DEG)); s.dirty = true; }
  else if (kind === 'zoom') { s.zoom = Math.max(0.6, Math.min(4, s.zoom * Math.exp(-a * 0.0015))); s.auto = false; s.dirty = true; }
  else if (kind === 'reset') { Object.assign(s, { yaw: s.home.yaw, pitch: s.home.pitch, zoom: 1, auto: true, dirty: true }); }
  kick();
}

/** The page's theme changed: relight (a dark page reads better with a darker ground bounce). */
export function theme(dark) {
  lights(!!dark);
  for (const el of live) { const s = states.get(el); if (s) s.dirty = true; }
  kick();
}

/** The element's view or size changed: measure the frame again on the next draw. */
export function reframe(el) {
  const s = states.get(el);
  if (!s) return;
  const view = parseView(el.getAttribute('view'));
  const a = anglesOf(view.dir);
  Object.assign(s, { view, home: a, yaw: a.yaw, pitch: a.pitch, zoom: 1, frame: null, dirty: true });
  kick();
}

/** Numbers for the KPI page and the browser checks. */
export function engineStats() {
  return { ...stats, live: live.size, models: models.size, maxLive: MAX_LIVE, maxModels: MAX_MODELS };
}
