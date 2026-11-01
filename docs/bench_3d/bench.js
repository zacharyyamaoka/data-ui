// Bench modes (?mode=percard|mv|sprite&n=40): each fills a grid with N of the case's real-scan models and reports
// window.__result. Data and meshes come from the object-db-shelf case (same origin).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const q = new URLSearchParams(location.search);
const mode = q.get('mode') || 'percard';
const N = Number(q.get('n') || 40);
const CASE = '../gallery/object-db-shelf/';
const t0 = performance.now();
const grid = document.getElementById('grid');
const heap = () => (performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null);

const data = await (await fetch(CASE + 'objects.json')).json();
const rows = data.rows.filter((r) => r.mesh && r.geometry === 'real scan').slice(0, N);

function frameCamera(object, camera) {
  const box = new THREE.Box3().setFromObject(object);
  const c = box.getCenter(new THREE.Vector3());
  const r = box.getBoundingSphere(new THREE.Sphere()).radius;
  object.position.sub(c);
  const d = r / Math.sin((15 * Math.PI) / 180) * 1.08;
  camera.position.set(d * 0.53, d * 0.37, d * 0.76);
  camera.near = d / 100; camera.far = d * 4;
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
}
function sceneWith(object) {
  const s = new THREE.Scene();
  s.add(new THREE.HemisphereLight(0xffffff, 0x8d8a84, 1.9));
  const k = new THREE.DirectionalLight(0xffffff, 2.2); k.position.set(2, 3, 2.5); s.add(k);
  s.add(object);
  return s;
}
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);

if (mode === 'percard') {
  // the naive way: every card its own canvas, renderer and WebGL context
  let drawn = 0;
  await Promise.all(rows.map(async (r) => {
    const cell = document.createElement('div'); cell.className = 'cell'; grid.append(cell);
    const canvas = document.createElement('canvas'); cell.append(canvas);
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setSize(160, 160, false);
    const g = await loader.loadAsync(CASE + r.mesh);
    const cam = new THREE.PerspectiveCamera(30, 1, 0.001, 100);
    frameCamera(g.scene, cam);
    renderer.render(sceneWith(g.scene), cam);
    drawn++;
  }));
  await new Promise((res) => setTimeout(res, 500));
  const blank = [...grid.querySelectorAll('canvas')].filter((c) => { const gl = c.getContext('webgl2') || c.getContext('webgl'); return !gl || gl.isContextLost(); }).length;
  window.__result = { mode, n: rows.length, ms: Math.round(performance.now() - t0), contexts: window.__gl.made, lost: window.__gl.lost, cardsLostTheirPicture: blank, heapMB: heap() };
}

if (mode === 'mv') {
  // Google's <model-viewer>: one shared renderer, per-element poster + lazy reveal
  await import('./model-viewer.min.js');
  let loaded = 0;
  const done = new Promise((res) => {
    for (const r of rows) {
      const cell = document.createElement('div'); cell.className = 'cell'; grid.append(cell);
      const mv = document.createElement('model-viewer');
      mv.setAttribute('src', CASE + r.mesh);
      mv.setAttribute('poster', CASE + r.thumbnail);
      mv.setAttribute('loading', 'lazy');
      mv.setAttribute('reveal', 'auto');
      mv.setAttribute('interaction-prompt', 'none');
      mv.addEventListener('load', () => { if (++loaded === rows.length) res(); }, { once: true });
      mv.addEventListener('error', () => { if (++loaded === rows.length) res(); }, { once: true });
      cell.append(mv);
    }
  });
  await Promise.race([done, new Promise((res) => setTimeout(res, 30000))]);
  await new Promise((res) => setTimeout(res, 500));
  window.__result = { mode, n: rows.length, loaded, ms: Math.round(performance.now() - t0), contexts: window.__gl.made, lost: window.__gl.lost, heapMB: heap() };
}

if (mode === 'sprite') {
  // a turntable sprite per object, 24 frames at 160 px, rendered here with ONE renderer and encoded as WebP:
  // what a build step would ship; then hover scrubs background-position (no WebGL at view time)
  const F = 24;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setSize(160, 160, false);
  const strip = document.createElement('canvas'); strip.width = 160 * F; strip.height = 160;
  const sctx = strip.getContext('2d');
  let bytes = 0, renderMs = 0;
  const sizes = [];
  for (const r of rows) {
    const g = await loader.loadAsync(CASE + r.mesh);
    const cam = new THREE.PerspectiveCamera(30, 1, 0.001, 100);
    frameCamera(g.scene, cam);
    const scene = sceneWith(new THREE.Group().add(g.scene));
    const holder = scene.children[scene.children.length - 1];
    sctx.clearRect(0, 0, strip.width, strip.height);
    const ts = performance.now();
    for (let i = 0; i < F; i++) { holder.rotation.y = (i / F) * Math.PI * 2; renderer.render(scene, cam); sctx.drawImage(renderer.domElement, i * 160, 0); }
    renderMs += performance.now() - ts;
    const blob = await new Promise((res) => strip.toBlob(res, 'image/webp', 0.8));
    bytes += blob.size; sizes.push(blob.size);
    const cell = document.createElement('div'); cell.className = 'cell'; grid.append(cell);
    const sp = document.createElement('div'); sp.className = 'sprite'; sp.style.backgroundImage = `url(${URL.createObjectURL(blob)})`; cell.append(sp);
    cell.addEventListener('pointermove', (e) => { const f = Math.floor((e.offsetX / 160) * F) % F; sp.style.backgroundPosition = `${(f / (F - 1)) * 100}% 0`; });
  }
  sizes.sort((a, b) => a - b);
  window.__result = { mode, n: rows.length, frames: F, ms: Math.round(performance.now() - t0), renderMsPerObject: +(renderMs / rows.length).toFixed(1),
    spriteKBMedian: +(sizes[sizes.length >> 1] / 1024).toFixed(1), spriteKBTotal: Math.round(bytes / 1024), contexts: window.__gl.made, heapMB: heap() };
}
