/* type: voxels (docs/CONTRACT.md §32; docs/peps/0010-robotics-playback.md §5.3): the discretised space. Zach,
   2026-10-28: "the other is to discretize the space … in 2D those heatmaps then become like 2D slices and look exactly
   like image heatmaps!" Registered from the scene3d bundle (manifest.json) and drawn on scene3d's stage (camera, view
   cube, projection, unit, axes, workspace, the page's one WebGL context): index.js's VoxelsView calls these.

     voxels:
       x, y, z, cell   the columns and the cell's edge in `unit` (required)
       value           count (default) | time (Σ w ÷ hz) | runs (distinct `run` per cell) | <property> (pre-gridded rows)
       summary         a property's summary: Average (default) | Median | Min | Max | Sum (Bases' names)
       slice           {axis: x | y | z, at: <coordinate> | all}
       min             cells below it are not drawn
       w, run, hz      the weight column (default w), the run column (default run), the rows' display rate (time needs it)
       scale           sequential (default) | verdict (the gates overlay's, CONTRACT §35: bad through warn to good tone)
       better          higher (default) | lower: which end of the values is good, for scale: verdict
       unit, up, projection, axes, workspace: the stage (CONTRACT §32)

   3D (perspective, or an oblique {dir}): one box per cell at 0.8 × the cell, two InstancedMeshes: the slice's cells
   solid, every other cell faded (all solid without a numeric slice). 2D (a face): the plane through the slice
   perpendicular to the view, as a DataTexture with NearestFilter on one quad, so the cells are crisp pixels of an image
   heatmap with the stage's axes in `unit`; without a slice on that axis (or with at: all) the plane is the projection
   along the view, a 2D histogram (grid.js `drop`). A face pick or the projection menu chooses the plane; the strip
   under the stage steps the slice one cell at a time (◀ ▶, a range, All), written to the view entry with
   host.setView, so it rides in the URL and Save view (BAM Reach's README: "iterate through").

   Colour (CONTRACT §32): one sequential ramp over the grid's [min(0, smallest), largest] (the projection's own with
   at: all), so stepping keeps colours comparable; one family in the rows (style.families' property) takes that
   family's hue, any other set grey; never red or green outside `scale: verdict` (ramp.js), whose bar carries ✕ at its bad
   end and ✓ at its good end. The legend is the ramp's bar with its two ends. Hover (2D) reads a cell: its range on both axes and its value.

   STOCK PARTS: three 0.186.1 InstancedMesh + BoxGeometry, DataTexture (NearestFilter) on a quad, MeshBasicMaterial
   (unlit: a cell's colour is its value, never shaded). Rerun's VoxelGridMap is the model. OURS: the binning
   (grid.js, checked against numpy.histogramdd), the ramp (ramp.js), the slice strip. */

import {
  InstancedMesh, BoxGeometry, MeshBasicMaterial, Matrix4, Quaternion, Vector3, Color, DataTexture, RGBAFormat,
  UnsignedByteType, NearestFilter, SRGBColorSpace, ClampToEdgeWrapping, BufferGeometry, Float32BufferAttribute, Mesh,
  DoubleSide,
} from 'three';
import { esc, cellValue, seriesColor } from '@data-ui/core';
import { voxelGrid, planeOf, kOf, AXES, centreOf } from './grid.js';
import { sequentialRamp, verdictRamp, parseColor } from './ramp.js';
import { projectionOf, faceAligned } from '../math.js';

const FADED = 0.14;   // the cells off the slice, in 3D: there to be seen through, never mistaken for the slice
const BOX = 0.8;      // a box's side in cells (PEP 0010 §5.3): the gaps tell one cell from the next
const read = (r, c) => cellValue(r[c]);
const text = (v) => { const x = cellValue(v); return x === null || x === undefined || x === '' ? null : String(x); };
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const dominant = (v) => { let k = 0; for (let i = 1; i < 3; i++) if (Math.abs(v[i]) > Math.abs(v[k])) k = i; return k; };
const KIND = { count: 'rows per cell', time: 's per cell', runs: 'runs per cell' };

/** A number for the legend and the readout: integers as they are, else 3 significant digits. */
export function fmtValue(v) {
  if (!finite(v)) return '—';
  if (Number.isInteger(v)) return v.toLocaleString('en-US');
  const a = Math.abs(v);
  return a >= 1000 ? Math.round(v).toLocaleString('en-US') : String(Number(v.toPrecision(3)));
}

/** The ramp's family: the one value of style.families' property the rows hold, when the map lists it (else null). */
function familyOf(input) {
  const fam = input.view && input.view.style && input.view.style.families;
  if (!fam || typeof fam.property !== 'string' || !fam.property) return null;
  const values = new Set();
  for (const r of input.rows || []) { const v = text(r[fam.property]); if (v !== null) values.add(v); if (values.size > 1) return null; }
  if (values.size !== 1) return null;
  const f = [...values][0];
  return fam.colors && typeof fam.colors === 'object' && Object.prototype.hasOwnProperty.call(fam.colors, f) ? f : null;
}

/** The view's whole state for one input: the grid, the mode, the plane or the boxes, the ramp. No three.js. */
export function voxelsModel(input, spec, stage) {
  const grid = voxelGrid(input.rows || [], spec, { read });
  const model = { grid, problem: grid.problem, mode: '3d', plane: null, flat: null, slice: null, ramp: null, family: null, domain: grid.domain, solidK: null,
    scale: 'sequential', better: null };
  if (model.problem) return model;
  if (!grid.cells.length) { model.problem = `No cells: no row has numbers in ${spec.x}, ${spec.y} and ${spec.z}`; return model; }
  const family = familyOf(input);
  model.family = family;
  const dark = !!(input.tokens && input.tokens.dark);
  if (spec.scale === 'verdict') {
    // WHY the tones and not the family's hue: a verdict is good or bad, whoever's rows these are (CONTRACT §35); tokens.tone is
    // the theme's, and tokens.bad / warn / good only for a host whose tokens predate it
    const tokens = input.tokens || {}, tone = tokens.tone || {};
    model.scale = 'verdict';
    model.better = spec.better === 'lower' ? 'lower' : 'higher';
    model.family = null;
    model.ramp = verdictRamp({ bad: tone.bad || tokens.bad, warn: tone.warn || tokens.warn, good: tone.good || tokens.good, better: model.better, dark });
  } else {
    model.ramp = sequentialRamp({ base: family ? seriesColor(family, input, family) : null, dark });
  }
  const proj = projectionOf(stage.projection, stage.up);
  const sl = spec.slice && typeof spec.slice === 'object' && AXES.includes(spec.slice.axis) ? spec.slice : null;
  const at = sl && finite(sl.at) ? sl.at : null;
  if (proj.ortho && faceAligned(proj)) {
    model.mode = '2d';
    const axis = AXES[dominant(proj.dir)];
    if (sl && sl.axis === axis && at !== null) {
      const k = kOf(grid, axis, at);
      model.plane = planeOf(grid, axis, k);
      model.slice = { axis, at, k, all: false };
    } else {
      // the projection along the view: count and time sum through the depth, runs counts a run once per column
      const flat = voxelGrid(input.rows || [], spec, { read, drop: axis });
      model.flat = flat;
      model.plane = planeOf(flat, axis, 0);
      model.domain = flat.domain;
      model.slice = { axis, at: 'all', k: null, all: true };
    }
  } else {
    model.mode = '3d';
    if (sl && at !== null) { model.solidK = kOf(grid, sl.axis, at); model.slice = { axis: sl.axis, at, k: model.solidK, all: false }; }
    else model.slice = { axis: sl ? sl.axis : 'z', at: 'all', k: null, all: true };
  }
  return model;
}

/** The colour of a value on the model's ramp: '#rrggbb'. */
export function colourOf(model, v) {
  const [a, b] = model.domain;
  return model.ramp.at(b > a ? (v - a) / (b - a) : 1);
}

/** Build the scene for the model: the boxes (3D) or the textured plane (2D), into view.scene. Returns the data's box. */
export function buildScene(view, model, spec) {
  const g = model.grid;
  const min = finite(spec.min) ? spec.min : null;
  const shown = (v) => min === null || v >= min;
  const lo = g.lo.map((k, a) => g.origin[a] + k * g.cell), hi = g.hi.map((k, a) => g.origin[a] + (k + 1) * g.cell);
  const objects = [];
  if (model.mode === '3d') {
    const geo = new BoxGeometry(1, 1, 1);
    const solid = [], faded = [];
    const ax = model.slice && !model.slice.all ? AXES.indexOf(model.slice.axis) : -1;
    for (const c of g.cells) {
      if (!shown(c.value)) continue;
      ((ax < 0 || [c.i, c.j, c.k][ax] === model.solidK) ? solid : faded).push(c);
    }
    const m4 = new Matrix4(), q = new Quaternion(), s = new Vector3().setScalar(BOX * g.cell), p = new Vector3(), col = new Color();
    for (const [list, role] of [[solid, 'voxels-solid'], [faded, 'voxels-faded']]) {
      const see = role === 'voxels-faded';
      const mat = new MeshBasicMaterial({ toneMapped: false, transparent: see, opacity: see ? FADED : 1, depthWrite: !see });
      const mesh = new InstancedMesh(geo, mat, Math.max(1, list.length));
      mesh.count = list.length;
      mesh.visible = list.length > 0;
      mesh.userData.role = role;
      if (see) mesh.renderOrder = 1;
      list.forEach((c, n) => {
        p.set(centreOf(g, 0, c.i), centreOf(g, 1, c.j), centreOf(g, 2, c.k));
        mesh.setMatrixAt(n, m4.compose(p, q, s));
        mesh.setColorAt(n, col.set(colourOf(model, c.value)));
      });
      mesh.userData.cells = list;   // instance n is cell list[n]: the hook reads each cell's colour back by it
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
      view.scene.add(mesh);
      objects.push({ mesh, material: mat });
    }
    view._voxGeometries = [geo];
  } else {
    const P = model.plane;
    const a = AXES.indexOf(P.axis), u = AXES.indexOf(P.plane[0]), v = AXES.indexOf(P.plane[1]);
    const grid = model.flat || g;
    const data = new Uint8Array(Math.max(1, P.width * P.height) * 4);
    for (let r = 0; r < P.height; r++) for (let c = 0; c < P.width; c++) {
      const val = P.values[r][c];
      if (val === null || !shown(val)) continue;
      const rgb = parseColor(colourOf(model, val));
      const o = (r * P.width + c) * 4;
      data[o] = rgb[0]; data[o + 1] = rgb[1]; data[o + 2] = rgb[2]; data[o + 3] = 255;
    }
    const tex = new DataTexture(data, Math.max(1, P.width), Math.max(1, P.height), RGBAFormat, UnsignedByteType);
    tex.colorSpace = SRGBColorSpace;
    tex.magFilter = tex.minFilter = NearestFilter;
    tex.generateMipmaps = false;
    tex.wrapS = tex.wrapT = ClampToEdgeWrapping;
    tex.needsUpdate = true;
    // the quad: the plane's cells on its two axes, at the slice's centre (the middle of the depth for the projection)
    const u0 = grid.origin[u] + P.i0 * g.cell, u1 = grid.origin[u] + (P.i0 + P.width) * g.cell;
    const v0 = grid.origin[v] + P.j0 * g.cell, v1 = grid.origin[v] + (P.j0 + P.height) * g.cell;
    const depth = model.slice.all ? (lo[a] + hi[a]) / 2 : centreOf(g, a, model.slice.k);
    const corner = (cu, cv) => { const pt = [0, 0, 0]; pt[u] = cu; pt[v] = cv; pt[a] = depth; return pt; };
    const geo = new BufferGeometry();
    geo.setAttribute('position', new Float32BufferAttribute([...corner(u0, v0), ...corner(u1, v0), ...corner(u1, v1), ...corner(u0, v1)], 3));
    geo.setAttribute('uv', new Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
    geo.setIndex([0, 1, 2, 0, 2, 3]);
    // WHY opaque with alphaTest, not transparent: an empty cell is discarded, and an opaque double-sided quad is one
    // draw call (three draws a transparent double-sided material twice, back faces then front)
    const mat = new MeshBasicMaterial({ map: tex, side: DoubleSide, alphaTest: 0.5, toneMapped: false });
    const mesh = new Mesh(geo, mat);
    mesh.userData.role = 'voxels-slice';
    view.scene.add(mesh);
    objects.push({ mesh, material: mat });
    view._voxGeometries = [geo];
    view._voxTextures = [tex];
    model.texture = { width: P.width, height: P.height, data };
  }
  view._voxObjects = objects;
  return { min: lo, max: hi };
}

/** The ramp's bar (the legend): its title, a gradient through five stops, the two ends. */
export function rampHtml(model, spec, columns) {
  if (!model.ramp) return '';
  const g = model.grid;
  const title = g.value === 'property'
    ? `${(columns && columns[g.property] && columns[g.property].label) || g.property} · ${g.summary}`
    : KIND[g.value];
  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => `${model.ramp.at(t)} ${t * 100}%`).join(', ');
  const fam = model.family ? ` · ${model.family}` : '';
  const all = model.slice && model.slice.all && model.mode === '2d' ? ` · through ${model.slice.axis}` : '';
  // a verdict's bar names its ends, never by colour alone: ✕ bad, ✓ good, at whichever end `better` puts them
  const glyph = (name, g) => (model.scale === 'verdict' ? `<b class="dv-voxels-ramp-glyph" title="${name}" aria-label="${name}">${g}</b>` : '');
  const [loGlyph, hiGlyph] = model.better === 'lower' ? [glyph('good', '✓'), glyph('bad', '✕')] : [glyph('bad', '✕'), glyph('good', '✓')];
  return `<span class="dv-voxels-ramp-title">${esc(title + fam + all)}</span><span class="dv-voxels-ramp-scale">${loGlyph}<span class="dv-voxels-ramp-lo" data-ramp-lo>${esc(fmtValue(model.domain[0]))}</span>`
    + `<i class="dv-voxels-ramp-bar" style="background:linear-gradient(to right, ${esc(stops)})"></i><span class="dv-voxels-ramp-hi" data-ramp-hi>${esc(fmtValue(model.domain[1]))}</span>${hiGlyph}</span>`;
}

/** The slice strip: the axis (3D only: in 2D the face is the axis), ◀ a range ▶ over the axis' cells, All, and where
    the slice is ("z 125–150 mm"). */
export function sliceHtml(model, unit) {
  const g = model.grid;
  if (!g || !g.cells.length || !model.slice) return '';
  const axis = model.slice.axis;
  const a = AXES.indexOf(axis);
  const lo = g.lo[a], hi = g.hi[a];
  const k = model.slice.all ? null : model.slice.k;
  const where = k === null ? `all ${axis}` : `${axis} ${fmtValue(g.origin[a] + k * g.cell)}–${fmtValue(g.origin[a] + (k + 1) * g.cell)} ${unit}`;
  const axisPick = model.mode === '3d'
    ? `<select data-slice-axis aria-label="Slice across">${AXES.map((x) => `<option value="${x}"${x === axis ? ' selected' : ''}>${x}</option>`).join('')}</select>`
    : `<span class="dv-vox-axis" title="The view looks along ${axis}: the slice is across it">${axis}</span>`;
  return `<div class="dv-vox-slice" role="group" aria-label="Slice">
    <span class="dv-vox-label">Slice</span>${axisPick}
    <button type="button" data-slice-step="-1" title="One cell back" aria-label="One cell back">◀</button>
    <input type="range" data-slice min="${lo}" max="${hi}" step="1" value="${k === null ? lo : k}" aria-label="Slice cell along ${axis}"${k === null ? ' data-all' : ''}>
    <button type="button" data-slice-step="1" title="One cell on" aria-label="One cell on">▶</button>
    <button type="button" data-slice-all aria-pressed="${k === null}" title="Every cell through ${axis}: ${model.mode === '2d' ? 'the projection, a 2D histogram' : 'every cell solid'}">All</button>
    <output data-slice-at>${esc(where)}</output>
  </div>`;
}

/** The slice the strip asks for, as the view entry's `slice`: {axis, at: the cell's centre | 'all'}. */
export function sliceFor(model, action, value) {
  const g = model.grid;
  const s = model.slice || { axis: 'z', k: null, all: true };
  let axis = s.axis;
  if (action === 'axis') return { axis: value, at: 'all' };
  const a = AXES.indexOf(axis);
  const lo = g.lo[a], hi = g.hi[a];
  if (action === 'all') return s.all ? { axis, at: centreOf(g, a, Math.round((lo + hi) / 2)) } : { axis, at: 'all' };
  let k;
  if (action === 'step') k = s.all || s.k === null ? (value > 0 ? lo : hi) : Math.min(hi, Math.max(lo, s.k + value));
  else k = Math.min(hi, Math.max(lo, Math.round(Number(value))));
  return { axis, at: centreOf(g, a, k) };
}
