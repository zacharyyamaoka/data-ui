/* The page's ONE WebGL context, shared by every 3D card (scene3d now; <data-mesh>'s engine when lane/object-db lands).

   The pattern is lane/object-db's mesh engine (packages/views/mesh/src/index.js @ dddc0a6), which is three's own
   "multiple elements" example and <model-viewer>'s Renderer singleton: one WebGLRenderer on a canvas that is never in
   the DOM; a card renders its scene into a viewport of it, then copies that frame (drawImage) into its own 2D canvas.

   WHY one context: browsers keep about 16 live WebGL contexts per page (Chromium then drops the oldest), and each costs
   tens of MB of GPU memory; a dashboard of 3D cards would lose some. WHY a 2D canvas per card: the card keeps its last
   frame where it is, through scrolls and re-layouts, with nothing to re-sync, and draws again only when asked.

   WHY on globalThis: each view bundle carries its own copy of three, so a module-level singleton would be one per
   bundle. `globalThis.__dataUiGL` is the page's one; the first bundle that needs it makes it, every later one reuses
   it (check `.three` against your own REVISION before handing it scenes built by another copy).

     const gl = sharedGL();
     gl.draw(canvas2d, scene, camera, w, h)   // device pixels; renders and copies; counts a render
     gl.overlay(canvas2d, render, size, [dx, dy, dw, dh])
                                              // render(renderer) into a size × size corner of the shared canvas and
                                              // composite it onto canvas2d at that box (the view cube: three's
                                              // ViewHelper renders itself into a fixed 128 px viewport); not a render
     gl.register(owner) / gl.unregister(owner) // a live scene (stats().scenes)
     gl.stats()                                // {contexts, contextsMade, contextLost, scenes, renders, renderMs}
*/

import { WebGLRenderer, SRGBColorSpace, NeutralToneMapping, REVISION } from 'three';

const KEY = '__dataUiGL';

export function sharedGL() {
  const had = globalThis[KEY];
  // a page whose first 3D bundle made version 1 (no overlay): this bundle adds its overlay on that one renderer
  if (had && !had.overlay && had.sharedRenderer) had.overlay = makeOverlay(had);
  if (had) return had;
  let renderer = null;
  let lost = false;
  const owners = new Set();
  const stats = { contexts: 0, contextsMade: 0, contextLost: 0, renders: 0, renderMs: 0 };

  /** The one WebGLRenderer (made on first use, and again after a lost context is restored). */
  function sharedRenderer() {
    if (renderer && !lost) return renderer;
    const canvas = renderer ? renderer.domElement : document.createElement('canvas'); // never in the DOM
    if (!renderer) {
      canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); lost = true; stats.contextLost++; stats.contexts = 0; });
      canvas.addEventListener('webglcontextrestored', () => { lost = false; renderer = null; });
    }
    // the settings are object-db's engine's, so a model card and a scene card look the same through one renderer
    renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' });
    renderer.setPixelRatio(1); // callers pass device pixels
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = NeutralToneMapping;
    renderer.setClearColor(0x000000, 0);
    lost = false;
    stats.contexts = 1;
    stats.contextsMade++;
    return renderer;
  }

  /** Render `scene` through `camera` at w × h device pixels and copy the frame into `target` (a 2D canvas). */
  function draw(target, scene, camera, w, h) {
    if (lost) return false;
    const r = sharedRenderer();
    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));
    if (target.width !== w || target.height !== h) { target.width = w; target.height = h; }
    const gl = r.domElement;
    if (gl.width < w || gl.height < h) r.setSize(Math.max(gl.width, w), Math.max(gl.height, h), false);
    const H = gl.height;
    const t0 = performance.now();
    r.setViewport(0, 0, w, h);
    r.setScissor(0, 0, w, h);
    r.setScissorTest(true);
    r.clear();
    r.render(scene, camera);
    const ctx = target.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    // WebGL's viewport (0, 0) is the canvas's bottom-left: the frame sits in the last h rows of the shared canvas
    ctx.drawImage(gl, 0, H - h, w, h, 0, 0, w, h);
    stats.renderMs = stats.renderMs * 0.9 + (performance.now() - t0) * 0.1;
    stats.renders++;
    return true;
  }

  /** Render `render(renderer)` into the bottom-left size × size of the shared canvas, then draw that square onto
      `target` at [dx, dy, dw, dh] (device px) without clearing it: what a card composites over its frame. */
  function overlay(target, render, size, box) {
    if (lost) return false;
    const r = sharedRenderer();
    const gl = r.domElement;
    if (gl.width < size || gl.height < size) r.setSize(Math.max(gl.width, size), Math.max(gl.height, size), false);
    const H = gl.height;
    r.setViewport(0, 0, size, size);
    r.setScissor(0, 0, size, size);
    r.setScissorTest(true);
    r.clear();
    render(r);
    target.getContext('2d').drawImage(gl, 0, H - size, size, size, box[0], box[1], box[2], box[3]);
    return true;
  }

  const api = {
    version: 2,
    three: REVISION,
    sharedRenderer,
    draw,
    overlay,
    register(owner) { owners.add(owner); },
    unregister(owner) { owners.delete(owner); },
    stats: () => ({ ...stats, scenes: owners.size }),
  };
  globalThis[KEY] = api;
  return api;
}

/** overlay() for a shared renderer made by an older copy of this module (version 1). */
function makeOverlay(api) {
  return function overlay(target, render, size, box) {
    const r = api.sharedRenderer();
    if (!r) return false;
    const gl = r.domElement;
    if (gl.width < size || gl.height < size) r.setSize(Math.max(gl.width, size), Math.max(gl.height, size), false);
    const H = gl.height;
    r.setViewport(0, 0, size, size);
    r.setScissor(0, 0, size, size);
    r.setScissorTest(true);
    r.clear();
    render(r);
    target.getContext('2d').drawImage(gl, 0, H - size, size, size, box[0], box[1], box[2], box[3]);
    return true;
  };
}
