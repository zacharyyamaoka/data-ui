/* From a view's input to what the stage draws (docs/CONTRACT.md §32): the stage keys, the paths (one per series, run
   and body: the "now" markers, the lines, the markers' samples), the items of arrows, arcs and boxes, the robots, the
   legend. No three.js here: numbers in, numbers out (tests/unit/scene3d-bind.test.mjs).

   Three bindings onto one Layer 1:
     trajectory3d   the trajectory contract (gallery/robotics/CONTRACT.md): poses per situation, its family's hue, its
                    display modes, compare from the difference rows, a robot per situation. "a very particular viewer
                    for a very particular dataclass" (Zach, 2026-10-28), and nothing but this mapping. Its path_overlay
                    keys (CONTRACT §35): `color` puts a column's numbers on each non-target path's vertices, `tolerance`
                    names the target's paths for a tube.
     scene3d.layers any columns, one primitive per layer (Rerun's archetypes).
     scene3d x/y/z  PEP 0005's path keys (series, target, skeleton, robot), read as a binding, drawn as before.
   data-ui knows no robotics word: "situation", "source", "run", "frame" are the contract's default column names, and
   a .base names others. */

import { cellValue, seriesColor, mediaUrl } from '@data-ui/core';
import { naturalCompare, markerIndices, linkColumns } from './math.js';

export const num = (v) => {
  const x = cellValue(v);
  if (typeof x === 'number') return Number.isFinite(x) ? x : null;
  if (x === null || x === undefined || x === '' || typeof x === 'boolean') return null;
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
};
export const text = (v) => { const x = cellValue(v); return x === null || x === undefined || x === '' ? null : String(x); };
const nameOf = (v) => text(v) ?? '—';

/** Dash patterns in dash units (CONTRACT §32): a family's members solid, then long dash 8 4, then dash-dot 8 3 2 3;
    the target dashed 5 4; an unclassified family dotted. */
export const DASH = { solid: [0, 0, 0, 0], long: [8, 4, 0, 0], dashdot: [8, 3, 2, 3], target: [5, 4, 0, 0], dotted: [1.5, 3, 0, 0] };
const MEMBERS = [DASH.solid, DASH.long, DASH.dashdot];
/** opacity: auto is exactly 1/n over a family's n paths, with no floor. WHY no floor (Zach's brief for PEP 0010 P2):
    "draw all of the runs with 1/n opacity so you can see where they went most often"; a floor (the PEP's max(1/n, 0.04))
    saturates a region crossed by 25 of 137 runs as dark as one crossed by all 137. The known limit (measured, README):
    the shared renderer blends into an 8-bit canvas, so the stacked runs fall short from about 250 and draw nothing at
    1,001; `voxels` with value: runs counts instead of blending. */
export const autoOpacity = (n) => 1 / Math.max(1, n);
export const UNIT_SCALE = { m: 1, cm: 100, mm: 1000 };

/** The stage keys (CONTRACT §32), with their defaults; scene3d's unit is m, trajectory3d's mm. */
export function stageOf(block, kind) {
  const b = block && typeof block === 'object' ? block : {};
  const decay = b.decay === 'inf' ? 'inf' : typeof b.decay === 'number' && Number.isFinite(b.decay) && b.decay >= 0 ? b.decay : 'inf';
  return {
    unit: ['m', 'cm', 'mm'].includes(b.unit) ? b.unit : kind === 'trajectory3d' ? 'mm' : 'm',
    up: b.up === 'y' ? 'y' : 'z',
    projection: b.projection === undefined || b.projection === null ? 'perspective' : b.projection,
    axes: b.axes === 'none' ? 'none' : 'auto',
    t: typeof b.t === 'string' && b.t ? b.t : 't',
    show: b.show === 'trail' ? 'trail' : 'all',
    decay,
    fade: b.fade !== false,
    density: typeof b.density === 'number' && b.density >= 1 ? b.density : 20,
    workspace: b.workspace && typeof b.workspace === 'object' ? b.workspace : null,
  };
}

/** "a and b", "a, b and c". */
export const listText = (xs) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

/** A path: rows with a time, sorted by it (file order among equal times), as typed arrays; a missing coordinate is NaN
    (a line breaks there, a marker is skipped). `quat` (four columns, wxyz) is optional. */
export function makePath(rows, cols, meta = {}) {
  const pts = [];
  for (const r of rows) { const t = num(r[cols.t]); if (t !== null) pts.push([t, r]); }
  pts.sort((a, b) => a[0] - b[0]);
  const n = pts.length;
  const t = new Float64Array(n), p = new Float64Array(3 * n), q = cols.quat ? new Float64Array(4 * n) : null;
  for (let i = 0; i < n; i++) {
    const r = pts[i][1];
    t[i] = pts[i][0];
    p[3 * i] = num(r[cols.x]) ?? NaN; p[3 * i + 1] = num(r[cols.y]) ?? NaN; p[3 * i + 2] = num(r[cols.z]) ?? NaN;
    if (q) for (let k = 0; k < 4; k++) q[4 * i + k] = num(r[cols.quat[k]]) ?? NaN;
  }
  return { ...meta, n, t, p, q, rows: pts.map((x) => x[1]) };
}

/** Group rows by the values of `cols` (a column or a list), in first-appearance order: Map(key → {values, rows}). */
function groupBy(rows, cols) {
  const list = (Array.isArray(cols) ? cols : [cols]).filter(Boolean);
  const out = new Map();
  for (const r of rows) {
    const values = list.map((c) => nameOf(r[c]));
    const key = values.join('\u0000');
    if (!out.has(key)) out.set(key, { values, rows: [] });
    out.get(key).rows.push(r);
  }
  return out;
}

const distinct = (rows, col) => { const s = new Set(); for (const r of rows) { const v = text(r[col]); if (v !== null) s.add(v); } return [...s]; };

/** The rows a layer reads (CONTRACT §32): `data` names another dataset of the dashboard (input.layers[data]); the
    view's own dataset (or none) is input.rows. {rows, url, missing}. */
export function layerRows(input, data) {
  const own = { rows: input.rows || [], url: input.dataset && input.dataset.url, missing: null };
  if (!data || data === input.view.from) return own;
  const l = input.layers && input.layers[data];
  if (l && Array.isArray(l.rows)) return { rows: l.rows, url: l.url || null, missing: null };
  return { rows: [], url: null, missing: data };
}

/** A robot's colour key (CONTRACT §32 robots.series.<s>.color): series (the series' own, the default), muted, a slot
    1-8 (0 muted), or a CSS colour. */
export function robotColor(pick, seriesCss, tokens) {
  const t = tokens || {};
  if (pick === undefined || pick === null || pick === 'series') return seriesCss;
  if (pick === 'muted' || pick === 0 || pick === '0') return t.muted || seriesCss;
  const n = typeof pick === 'number' ? pick : /^\d+$/.test(String(pick)) ? Number(pick) : null;
  if (n !== null) return (t.series || [])[n - 1] || seriesCss;
  return String(pick);
}

// ------------------------------------------------------------------------------------------------ trajectory3d

/** The trajectory contract's names, or the binding's (CONTRACT §32 type: trajectory3d). */
export function trajectoryColumns(spec, view) {
  const poses = spec.poses && typeof spec.poses === 'object' ? spec.poses : {};
  const fam = view.style && view.style.families && typeof view.style.families.property === 'string' ? view.style.families.property : null;
  return {
    x: poses.x || 'x_mm', y: poses.y || 'y_mm', z: poses.z || 'z_mm',
    quat: Array.isArray(poses.quat) && poses.quat.length === 4 ? poses.quat : ['quat_w', 'quat_x', 'quat_y', 'quat_z'],
    frame: poses.frame || 'frame', body: poses.body || 'body',
    series: spec.series || 'situation', family: spec.family || fam || 'source', run: spec.run || 'run', t: spec.t || 't',
  };
}

const MODES = ['line', 'points', 'frames', 'frames-z'];

export function bindTrajectory(input) {
  const view = input.view;
  const spec = view.trajectory3d && typeof view.trajectory3d === 'object' ? view.trajectory3d : {};
  const stage = stageOf(spec, 'trajectory3d');
  const C = trajectoryColumns(spec, view);
  stage.t = C.t;
  const rows = input.rows || [];
  const model = { kind: 'trajectory3d', stage, columns: C, series: [], paths: [], lines: [], targetLines: [], points: [], frames: [], framesZ: [],
    arrows: [], arcs: [], boxes: [], robots: null, legend: [], problem: null, frame: null, notes: [],
    overlay: { color: null, min: null, max: null }, tube: null };

  // frames are declared, never guessed: rows in two frames are never mixed (gallery/robotics/CONTRACT.md §4)
  const frames = distinct(rows, C.frame);
  if (frames.length > 1) {
    model.problem = `Rows in ${frames.length} frames: ${listText(frames)}. Frames are never mixed, so nothing is drawn; filter to one frame (${C.frame}).`;
    model.frames = frames;
    return model;
  }
  model.frame = frames[0] || null;

  const tokens = input.tokens || {};
  const famSpec = view.style && view.style.families && typeof view.style.families === 'object' && view.style.families.property ? view.style.families : null;
  const listed = famSpec && famSpec.colors && typeof famSpec.colors === 'object' ? famSpec.colors : {};
  const groups = groupBy(rows, C.series);
  const names = [...groups.keys()];
  const familyOf = new Map(names.map((n) => { const f = distinct(groups.get(n).rows, C.family); return [n, f.length === 1 ? f[0] : null]; }));
  const target = spec.target !== undefined && spec.target !== null ? String(spec.target)
    : names.find((n) => familyOf.get(n) === 'target') ?? (groups.has('target') ? 'target' : null);

  // a family's members in natural order: solid, long dash, dash-dot; four or more draw one hue at opacity auto
  const famKey = (n) => (famSpec && familyOf.get(n) !== null && Object.prototype.hasOwnProperty.call(listed, familyOf.get(n)) ? `f:${familyOf.get(n)}` : `s:${n}`);
  const members = new Map();
  for (const n of [...names].sort(naturalCompare)) if (n !== target) { const k = famKey(n); if (!members.has(k)) members.set(k, []); members.get(k).push(n); }

  for (const name of names) {
    const family = familyOf.get(name);
    const classified = !famSpec || (family !== null && Object.prototype.hasOwnProperty.call(listed, family));
    const css = seriesColor(name, input, famSpec ? family : undefined);
    const team = members.get(famKey(name)) || [name];
    const k = team.indexOf(name);
    const collapsed = famSpec && classified && name !== target && team.length >= 4;
    const dash = name === target ? DASH.target : !classified ? DASH.dotted : collapsed ? DASH.solid : MEMBERS[Math.min(k, 2)] || DASH.solid;
    const modes = (spec.modes && Array.isArray(spec.modes[name]) ? spec.modes[name] : ['line']).filter((m) => MODES.includes(m));
    model.series.push({ name, css, family, classified, isTarget: name === target, dash, modes, legendName: collapsed ? family : name, collapsed });
  }

  // the paths: one per series, run and body, in time order
  const opacity = typeof spec.opacity === 'number' ? Math.min(1, Math.max(0, spec.opacity)) : 'auto';
  const quat = C.quat.every((c) => input.columns && input.columns[c]) || rows.some((r) => C.quat.every((c) => r[c] !== undefined)) ? C.quat : null;
  const perFamily = new Map();
  for (const s of model.series) {
    const parts = groupBy(groups.get(s.name).rows, [C.run, C.body]);
    s.paths = [];
    const bodies = new Set([...parts.values()].map((g) => g.values[1]));
    for (const g of parts.values()) {
      const label = parts.size === 1 ? s.name : `${s.name} · ${g.values[0]}${bodies.size > 1 ? ` · ${g.values[1]}` : ''}`;
      const path = makePath(g.rows, { t: C.t, x: C.x, y: C.y, z: C.z, quat }, { series: s.legendName, seriesName: s.name, key: label, run: g.values[0], body: g.values[1], css: s.css, dash: s.dash });
      s.paths.push(path);
      model.paths.push(path);
      const fk = s.isTarget ? `s:${s.name}` : famKey(s.name);
      perFamily.set(fk, (perFamily.get(fk) || 0) + 1);
    }
  }
  for (const s of model.series) {
    const fk = s.isTarget ? `s:${s.name}` : famKey(s.name);
    const alpha = opacity === 'auto' ? autoOpacity(perFamily.get(fk) || 1) : opacity;
    for (const p of s.paths) {
      p.alpha = alpha;
      p.density = stage.density;
      if (s.modes.includes('line')) (s.isTarget ? model.targetLines : model.lines).push(p);
      if (s.modes.includes('points')) model.points.push(p);
      if (s.modes.includes('frames')) model.frames.push(p);
      if (s.modes.includes('frames-z')) model.framesZ.push(p);
    }
  }

  // path_overlay (CONTRACT §35). color: each drawn non-target path carries its own rows' numbers per vertex, in time order,
  // and the overlay the drawn min..max. WHY the view only reads the number: the producer writes it (an error column is the
  // difference rows' err_mm, written onto the pose rows); a view that computed an error would be a second source of truth.
  const colorColumn = typeof spec.color === 'string' && spec.color ? spec.color : null;
  model.overlay.color = colorColumn;
  if (colorColumn) {
    let lo = Infinity, hi = -Infinity;
    for (const p of model.lines) {
      p.values = Float64Array.from(p.rows, (r) => num(r[colorColumn]) ?? NaN);
      for (const v of p.values) if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    if (Number.isFinite(lo)) { model.overlay.min = lo; model.overlay.max = hi; }
  }
  // tolerance: a tube of that radius (the stage's unit) along the target's paths; none without a target or a positive number
  const targetSeries = model.series.find((s) => s.isTarget);
  if (targetSeries && typeof spec.tolerance === 'number' && Number.isFinite(spec.tolerance) && spec.tolerance > 0 && targetSeries.paths.length) {
    model.tube = { radius: spec.tolerance, paths: targetSeries.paths };
  }

  // compare: arrows from a(t) to b(t), and Z-arcs where a draws frames-z, from the difference rows (never computed here)
  const cmp = spec.compare && typeof spec.compare === 'object' && spec.compare.data ? spec.compare : null;
  if (cmp) {
    const src = layerRows(input, cmp.data);
    if (src.missing) model.notes.push(`compare: no dataset '${src.missing}' here`);
    const present = [...groupBy(src.rows, [C.series, 'reference']).values()].map((g) => g.values);
    const pairs = Array.isArray(cmp.pairs) && cmp.pairs.length ? cmp.pairs.filter((p) => Array.isArray(p) && p.length === 2).map((p) => p.map(String))
      : present.filter(([, b]) => b === target);
    const scale = typeof cmp.scale === 'number' && cmp.scale > 0 ? cmp.scale : 1;
    model.compare = { pairs, scale, present };
    const byName = new Map(model.series.map((s) => [s.name, s]));
    const ref = (c) => `ref_${c}`;
    for (const [a, b] of pairs) {
      const s = byName.get(a);
      if (!s) continue;
      const rowsAB = src.rows.filter((r) => text(r[C.series]) === a && text(r.reference) === b);
      const parts = groupBy(rowsAB, [C.run, C.body]);
      for (const g of parts.values()) {
        const path = makePath(g.rows, { t: C.t, x: C.x, y: C.y, z: C.z, quat }, {});
        const to = makePath(g.rows, { t: C.t, x: ref(C.x), y: ref(C.y), z: ref(C.z), quat: quat ? C.quat.map(ref) : null }, {});
        const alpha = s.paths[0] ? s.paths[0].alpha : 1;
        for (const i of markerIndices(path.n, stage.density)) {
          const from = [path.p[3 * i], path.p[3 * i + 1], path.p[3 * i + 2]], tip = [to.p[3 * i], to.p[3 * i + 1], to.p[3 * i + 2]];
          if (from.some((c) => !Number.isFinite(c)) || tip.some((c) => !Number.isFinite(c))) continue;
          model.arrows.push({ series: s.legendName, css: s.css, alpha, t: path.t[i], from, to: tip });
          if (s.modes.includes('frames-z') && path.q && to.q) {
            model.arcs.push({ series: s.legendName, css: s.css, alpha, t: path.t[i], at: from,
              own: [0, 1, 2, 3].map((k) => path.q[4 * i + k]), ref: [0, 1, 2, 3].map((k) => to.q[4 * i + k]) });
          }
        }
      }
    }
  }

  // robots: one per series, posed at t from its link rows (the producer ran the forward kinematics)
  const rb = spec.robots && typeof spec.robots === 'object' && typeof spec.robots.model === 'string' && Array.isArray(spec.robots.links) && spec.robots.links.length ? spec.robots : null;
  if (rb) {
    const src = layerRows(input, rb.data);
    if (src.missing) model.notes.push(`robots: no dataset '${src.missing}' here`);
    const links = rb.links.filter((l) => typeof l === 'string' && l);
    const per = rb.series && typeof rb.series === 'object' ? rb.series : {};
    const bySeries = groupBy(src.rows, C.series);
    const robots = [];
    for (const s of model.series) {
      const conf = per[s.name] && typeof per[s.name] === 'object' ? per[s.name] : {};
      const g = bySeries.get(s.name);
      if (!g || conf.show === false) continue;
      // one robot per series: its first run in file order (the rail picks a run; several runs share one robot)
      const run = text(g.rows[0][C.run]);
      const rows1 = g.rows.filter((r) => text(r[C.run]) === run);
      const opacity = typeof conf.opacity === 'number' ? Math.min(1, Math.max(0, conf.opacity)) : s.isTarget ? 0.25 : 1;
      robots.push({ series: s.name, legendName: s.legendName, rows: rows1, run, runs: new Set(g.rows.map((r) => text(r[C.run]))).size,
        color: robotColor(conf.color, s.css, tokens), colorKey: conf.color ?? 'series', opacity, isTarget: s.isTarget });
    }
    model.robots = { url: mediaUrl(rb.model, { url: src.url }), links, scale: UNIT_SCALE[stage.unit], series: robots, cols: links.flatMap(linkColumns), t: C.t };
  }

  // the legend: one entry per series, or per family of four or more
  const seen = new Set();
  for (const s of model.series) {
    if (seen.has(s.legendName)) continue;
    seen.add(s.legendName);
    const team = s.collapsed ? model.series.filter((x) => x.legendName === s.legendName) : [s];
    const runs = new Set(team.flatMap((x) => x.paths.map((p) => p.run))).size;
    let extra = !s.classified ? ' · unclassified' : s.collapsed ? ` · ${team.length} series, ${runs} run${runs === 1 ? '' : 's'}` : '';
    if (s.isTarget && model.tube) extra += ` · ± ${model.tube.radius} ${stage.unit}`;
    model.legend.push({ name: s.legendName, css: s.css, dash: s.dash, extra, target: s.isTarget });
  }
  return model;
}

// ------------------------------------------------------------------------------------------------ scene3d.layers

const PRIMITIVES = ['points', 'lines', 'frames', 'arrows', 'arcs', 'meshes', 'boxes'];

export function bindLayers(input) {
  const view = input.view;
  const spec = view.scene3d || {};
  const stage = stageOf(spec, 'scene3d');
  const model = { kind: 'layers', stage, series: [], paths: [], lines: [], targetLines: [], points: [], frames: [], framesZ: [], arrows: [], arcs: [], boxes: [],
    meshes: [], robots: null, legend: [], problem: null, frame: null, notes: [] };
  const colors = new Map();   // the colour column's values, in first-appearance order: the legend
  const colorOfValue = (v) => {
    if (!colors.has(v)) colors.set(v, { name: v, css: seriesColor(v, input, undefined), dash: DASH.solid });
    return colors.get(v);
  };
  const layers = (Array.isArray(spec.layers) ? spec.layers : []).filter((l) => l && PRIMITIVES.includes(l.primitive));
  layers.forEach((L, li) => {
    const src = layerRows(input, L.data);
    if (src.missing) { model.notes.push(`layer ${li + 1}: no dataset '${src.missing}' here`); return; }
    const by = Array.isArray(L.by) ? L.by : L.by ? [L.by] : [];
    const colorCol = L.color || by[0] || null;
    const dashed = new Set(Array.isArray(L.dash) ? L.dash.map(String) : []);
    const t = L.t || stage.t;
    const density = typeof L.density === 'number' && L.density >= 1 ? L.density : stage.density;
    const alpha = typeof L.opacity === 'number' ? Math.min(1, Math.max(0, L.opacity)) : 1;
    // WHY the colour column splits groups too: one group draws in one colour, so rows of two colours (boxes of two
    // situations under one `by`, or no `by` at all) are never painted the first row's colour
    const split = [...by, ...(colorCol && !by.includes(colorCol) ? [colorCol] : [])];
    const groups = split.length ? groupBy(src.rows, split) : new Map([['', { values: [], rows: src.rows }]]);
    const cv = (rows) => (colorCol ? nameOf(rows[0][colorCol]) : view.name || 'layer');
    for (const g of groups.values()) {
      if (!g.rows.length) continue;
      const value = cv(g.rows);
      const c = colorOfValue(value);
      const meta = { series: value, seriesName: value, key: g.values.length ? g.values.slice(0, Math.max(1, by.length)).join(' · ') : value, css: c.css, alpha, density, dash: dashed.has(value) ? DASH.target : DASH.solid };
      if (L.primitive === 'lines' || L.primitive === 'points' || L.primitive === 'frames') {
        if (!L.x || !L.y || !L.z) continue;
        const quat = Array.isArray(L.quat) && L.quat.length === 4 ? L.quat : null;
        const path = makePath(g.rows, { t, x: L.x, y: L.y, z: L.z, quat }, meta);
        if (L.primitive === 'lines') { (dashed.has(value) ? model.targetLines : model.lines).push(path); model.paths.push(path); }
        else if (L.primitive === 'points') model.points.push(path);
        else (L.axes === 'z' ? model.framesZ : model.frames).push({ ...path, length: L.length });
      } else if (L.primitive === 'arrows' || L.primitive === 'arcs') {
        const at = L.primitive === 'arrows' ? L.from : L.at;
        if (!Array.isArray(at) || at.length < 3) continue;
        const quat = L.primitive === 'arcs' ? L.from : null;
        const path = makePath(g.rows, { t, x: at[0], y: at[1], z: at[2], quat: quat && quat.length === 4 ? quat : null }, meta);
        const toCols = L.to || [];
        const to = L.primitive === 'arrows' ? makePath(g.rows, { t, x: toCols[0], y: toCols[1], z: toCols[2], quat: null }, {})
          : makePath(g.rows, { t, x: at[0], y: at[1], z: at[2], quat: toCols.length === 4 ? toCols : null }, {});
        for (const i of markerIndices(path.n, density)) {
          const from = [path.p[3 * i], path.p[3 * i + 1], path.p[3 * i + 2]];
          if (from.some((x) => !Number.isFinite(x))) continue;
          if (L.primitive === 'arrows') {
            const tip = [to.p[3 * i], to.p[3 * i + 1], to.p[3 * i + 2]];
            if (tip.some((x) => !Number.isFinite(x))) continue;
            model.arrows.push({ series: value, css: c.css, alpha, t: path.t[i], from, to: tip, scale: L.scale });
          } else if (path.q && to.q) {
            model.arcs.push({ series: value, css: c.css, alpha, t: path.t[i], at: from, own: [0, 1, 2, 3].map((k) => path.q[4 * i + k]), ref: [0, 1, 2, 3].map((k) => to.q[4 * i + k]), length: L.length });
          }
        }
      } else if (L.primitive === 'boxes') {
        const lo = L.min || [], hi = L.max || [];
        for (const r of g.rows) {
          const min = lo.map((col) => num(r[col])), max = hi.map((col) => num(r[col]));
          const tt = num(r[t]);
          if (min.length !== 3 || max.length !== 3 || [...min, ...max].some((x) => x === null)) continue;
          model.boxes.push({ series: value, css: c.css, alpha, t: tt === null ? 0 : tt, min, max });
        }
      } else if (L.primitive === 'meshes') {
        const links = Array.isArray(L.links) ? L.links.filter((l) => typeof l === 'string' && l) : [];
        if (typeof L.model !== 'string' || !links.length) continue;
        model.meshes.push({ series: value, css: c.css, rows: g.rows, url: mediaUrl(L.model, { url: src.url }), links, cols: links.flatMap(linkColumns), t, opacity: alpha });
      }
    }
  });
  for (const c of colors.values()) model.legend.push({ name: c.name, css: c.css, dash: c.dash, extra: '' });
  model.series = [...colors.values()].map((c) => ({ name: c.name, css: c.css, legendName: c.name }));
  if (model.meshes.length) {
    model.robots = { url: model.meshes[0].url, links: model.meshes[0].links, scale: UNIT_SCALE[stage.unit], cols: model.meshes[0].cols, t: model.meshes[0].t,
      series: model.meshes.map((m) => ({ series: m.series, legendName: m.series, rows: m.rows, color: m.css, colorKey: 'series', opacity: m.opacity, isTarget: false, runs: 1 })) };
  }
  return model;
}
