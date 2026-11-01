/* The map view's plan (docs/CONTRACT.md §42): a view entry + rows -> what to draw on a MapLibre map. Each layer of
   `layers:` becomes sources and MapLibre layer specs, a legend, the click rule and the one-line answer. Built once
   over ALL the view's rows (so classes are shared), then again per subset for small multiples and the two sides of a
   swipe with `shared` (the first plan's classes), so every panel is read against the same legend.

   Pure except for the injected helpers (`h`): {value(row, p), raw(row, p), match(expr) -> (row) -> bool, fmt(v, p),
   label(p), unit(p), colourOf(row, p) (series slot colour), tokens, h3 (or null), geometry(file) -> GeoJSON}. */

import * as A from './analysis.js';

export const LAYER_TYPES = ['markers', 'points', 'heatmap', 'hexbin', 'regions', 'flows', 'lines', 'rings', 'catchments', 'within', 'labels'];

/** The view's map keys, normalised: {space, layers: [{type, ...}], time, multiples, swipe, draw, legend}. With no
    `layers:` the view is today's HTML markers (Bases' Maps plugin behaviour, unchanged). */
export function mapSpec(view) {
  const layers = Array.isArray(view.layers) && view.layers.length ? view.layers.filter((l) => l && LAYER_TYPES.includes(l.type)) : [{ type: 'markers' }];
  const t = view.time;
  return {
    space: view.space === 'local' ? 'local' : 'geo',
    layers,
    unknown: Array.isArray(view.layers) ? view.layers.filter((l) => !l || !LAYER_TYPES.includes(l.type)).map((l) => (l && l.type) || '?') : [],
    time: t && (typeof t === 'string' ? { property: t } : t.property ? t : null),
    multiples: view.multiples && view.multiples.by ? { columns: 0, limit: 9, ...view.multiples } : null,
    swipe: view.swipe && view.swipe.left && view.swipe.right ? view.swipe : null,
    draw: view.draw === true || view.draw === 'polygon',
    legend: view.legend === false || view.legend === 'off' ? 'off' : view.legend === 'closed' ? 'closed' : 'open',
  };
}

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** The rows behind a feature, as indexes: a point's or a line's own row, the rows a region, hexagon or catchment holds, a
    catchment's site. A pick marks a feature when any of them is picked (§39: a counted marker when any of its rows is). */
export function featureRows(p) {
  if (!p) return [];
  return [...(p._i != null ? [p._i] : []), ...(Array.isArray(p._rows) ? p._rows : []), ...(p._site != null ? [p._site] : [])];
}

/** Build the plan. `rows` are the view's rows (input.rows) or a subset; `shared` the first plan's classes. */
export function buildPlan(spec, rows, h, shared = null, all = rows) {
  const T = h.tokens;
  // WHY a Map: rows.indexOf per row is n² on the 150,000 rows a deployment holds
  const rowAt = new Map(rows.map((r, i) => [r, i]));
  const plan = { sources: [], layers: [], legend: [], clicks: [], notes: [], answer: '', bounds: null, classes: {}, timed: [], sections: [], missing: 0, whys: new Map(), markers: false, drawn: rows.length, overlays: [] };
  const extend = (lng, lat) => {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
    const b = plan.bounds || (plan.bounds = [lng, lat, lng, lat]);
    b[0] = Math.min(b[0], lng); b[1] = Math.min(b[1], lat); b[2] = Math.max(b[2], lng); b[3] = Math.max(b[3], lat);
  };
  const extendFc = (fc) => { for (const f of fc.features) walk(f.geometry && f.geometry.coordinates); };
  const walk = (c) => { if (!c) return; if (typeof c[0] === 'number') extend(c[0], c[1]); else c.forEach(walk); };
  const at = (prop) => (r) => A.position(h.raw(r, prop), spec.space);
  const ink = (i) => T.series[i % T.series.length];
  const sel = (expr) => (expr ? h.match(expr) : () => true);
  /* WHY a layer of its own: a row inside a cluster, or under the heat below `pointsFrom`, has no drawn feature for a
     feature-state to mark, so a pick from a table or the URL would show nothing. This holds the picked rows, never
     clustered, as rings at their own points over whatever hides them, at every zoom. */
  const overlay = (source, radius, timed) => {
    const mark = `${source}-m`;
    plan.sources.push({ id: mark, data: { type: 'FeatureCollection', features: [] } });
    plan.layers.push({ id: mark, type: 'circle', source: mark, paint: { 'circle-radius': radius, 'circle-color': 'rgba(0, 0, 0, 0)', 'circle-stroke-width': 2.5, 'circle-stroke-color': T.accent } });
    plan.overlays.push({ source, mark });
    if (timed) plan.timed.push(mark);
  };

  spec.layers.forEach((L, li) => {
    const id = `dvl-${li}`;
    const coords = L.coordinates || h.view.coordinates;

    // ---------------------------------------------------------------- markers: HTML; a property's colours get a legend
    if (L.type === 'markers') {
      plan.markers = true;
      const by = h.view.markerColor;
      if (!h.isProperty(by)) return;
      const word = (i) => { const v = h.text(rows[i], by); return v == null || v === '' ? null : v; };
      const placed = [], spots = new Map();
      rows.forEach((r, i) => {
        const p = at(coords)(r);
        if (!p) return;
        placed.push(i);
        // the key toPoints groups a counted marker by (index.js)
        const key = `${p[1].toFixed(4)},${p[0].toFixed(4)}`;
        if (!spots.has(key)) spots.set(key, new Set());
        spots.get(key).add(word(i));
      });
      if (!placed.length) return;
      const entry = { title: L.title || h.label(by), kind: 'points', rows: A.countBy(placed, word).map(([v, n]) => {
        const held = placed.filter((i) => word(i) === v);
        return { label: v ?? `No ${h.label(by)}`, colour: v == null ? T.muted : h.colourOf(rows[held[0]], by), n, rows: held };
      }) };
      // truthful: a counted marker shows one colour, so a value it holds can read as absent from the map
      const mixed = [...spots.values()].filter((s) => s.size > 1).length;
      if (mixed) entry.note = `A counted marker takes its most common value's colour: ${mixed} ${mixed === 1 ? 'point holds' : 'points hold'} several values.`;
      plan.legend.push(entry);
      if (!plan.answer) plan.answer = entry.rows.length <= 4 ? entry.rows.map((r) => `${r.n.toLocaleString('en-US')} ${r.label}`).join(' · ') : `${placed.length.toLocaleString('en-US')} rows · most: ${entry.rows[0].label} (${entry.rows[0].n.toLocaleString('en-US')})`;
      return;
    }

    // ---------------------------------------------------------------- points, heatmap, hexbin: rows with a position
    if (L.type === 'points' || L.type === 'heatmap' || L.type === 'hexbin') {
      const rs = rows.filter(sel(L.filter));
      const props = {};
      const colourBy = L.color && h.isProperty(L.color) ? L.color : null;
      if (colourBy) props._col = (r) => h.colourOf(r, colourBy);
      if (L.size && L.size.property) props._s = (r) => num(h.value(r, L.size.property));
      if (L.weight) props._w = (r) => num(h.value(r, L.weight));
      if (L.label) props._label = (r) => h.text(r, L.label);
      if (spec.time) props._t = (r) => { const v = h.value(r, spec.time.property); const t = typeof v === 'number' ? v : Date.parse(v); return Number.isFinite(t) ? t : null; };
      const idx = rs.map((r) => rowAt.get(r));
      const { fc, missing } = A.pointFeatures(rs, at(coords), props);
      for (const f of fc.features) f.properties._i = idx[f.properties._i];
      if (!L.filter) { plan.missing += missing; if (missing) h.why(rs, coords, plan.whys); }
      extendFc(fc);
      const fixed = L.color && !colourBy ? h.colour(L.color) : ink(li === 0 ? 0 : li);

      if (L.type === 'points') {
        const src = { id, data: fc };
        let maxV = null;
        if (L.size && L.size.property) {
          maxV = shared && shared[id] ? shared[id].maxV : Math.max(0, ...fc.features.map((f) => f.properties._s).filter((v) => v != null));
          for (const f of fc.features) f.properties._r = A.symbolRadius(f.properties._s, maxV, L.size.max || 24);
          plan.classes[id] = { maxV };
        }
        if (L.cluster) Object.assign(src, { cluster: true, clusterRadius: (L.cluster && L.cluster.radius) || 44, clusterMaxZoom: (L.cluster && L.cluster.maxZoom) || 13 });
        plan.sources.push(src);
        const colour = colourBy ? ['coalesce', ['get', '_col'], T.muted] : fixed;
        const radius = L.size && L.size.property ? ['coalesce', ['get', '_r'], 0] : L.radius || 5;
        const filterOut = L.size && L.size.property ? ['!=', ['get', '_r'], null] : true;
        if (L.cluster) {
          plan.layers.push({ id: `${id}-c`, type: 'circle', source: id, filter: ['has', 'point_count'], paint: { 'circle-color': A.mix(T.bg, fixed, 0.75), 'circle-radius': ['step', ['get', 'point_count'], 13, 10, 17, 50, 22, 200, 28], 'circle-stroke-width': 1.5, 'circle-stroke-color': T.bg } });
          plan.layers.push({ id: `${id}-n`, type: 'symbol', source: id, filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-allow-overlap': true }, paint: { 'text-color': T.onAccent } });
          plan.clicks.push({ layer: `${id}-c`, cluster: id });
        }
        plan.layers.push({ id, type: 'circle', source: id, filter: L.cluster ? ['all', ['!', ['has', 'point_count']], filterOut] : filterOut, paint: {
          'circle-color': colour, 'circle-radius': radius, 'circle-opacity': L.opacity ?? (L.size ? 0.62 : 0.88),
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.5, 1], 'circle-stroke-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, T.bg],
        }, layout: L.size ? { 'circle-sort-key': ['-', 0, ['coalesce', ['get', '_r'], 0]] } : {} });
        if (L.label) plan.layers.push({ id: `${id}-l`, type: 'symbol', source: id, filter: L.cluster ? ['!', ['has', 'point_count']] : true, layout: { 'text-field': ['coalesce', ['get', '_label'], ''], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 1.1], 'text-anchor': 'top', 'text-optional': true }, paint: { 'text-color': T.fg, 'text-halo-color': T.bg, 'text-halo-width': 1.4 } });
        plan.clicks.push({ layer: id, points: true });
        if (spec.time) plan.timed.push(id, ...(L.label ? [`${id}-l`] : []));
        if (L.cluster) overlay(id, typeof radius === 'number' ? radius + 3 : ['+', ['coalesce', ['get', '_r'], 2], 3], !!spec.time);
        const entry = { title: L.title || (colourBy ? h.label(colourBy) : h.label(coords)), kind: 'points' };
        if (colourBy) entry.rows = A.countBy(fc.features.map((f) => f.properties._i), (i) => h.text(rows[i], colourBy)).map(([v, n]) => ({ label: v ?? `No ${h.label(colourBy)}`, colour: v == null ? T.muted : h.colourOf(rows.find((r) => h.text(r, colourBy) === v), colourBy), n }));
        else entry.rows = [{ label: L.title || `${fc.features.length.toLocaleString('en-US')} ${fc.features.length === 1 ? 'row' : 'rows'}`, colour: fixed, n: fc.features.length }];
        if (L.size && L.size.property) entry.size = { property: h.label(L.size.property), unit: h.unit(L.size.property), max: maxV, maxText: h.fmt(maxV, L.size.property), radius: L.size.max || 24, rule: 'circle area ∝ value' };
        if (L.cluster) entry.note = 'Circles with a number are clusters of nearby rows (MapLibre clustering): click one to zoom in.';
        plan.legend.push(entry);
        if (!plan.answer) {
          const n = fc.features.length;
          if (L.size && L.size.property) {
            const top = fc.features.filter((f) => f.properties._s != null).sort((a, b) => b.properties._s - a.properties._s)[0];
            if (top) plan.answer = `Largest: ${h.text(rows[top.properties._i], h.titleProperty) ?? h.text(rows[top.properties._i], L.label) ?? rows[top.properties._i].id} · ${h.fmt(top.properties._s, L.size.property)} ${h.unit(L.size.property)}`.trim();
          } else if (colourBy && entry.rows.length <= 4) plan.answer = entry.rows.map((r) => `${r.n.toLocaleString('en-US')} ${r.label}`).join(' · ');
          else if (colourBy) plan.answer = `${n.toLocaleString('en-US')} rows · most: ${entry.rows[0].label} (${entry.rows[0].n.toLocaleString('en-US')})`;
          else plan.answer = `${n.toLocaleString('en-US')} ${L.title ? L.title.toLowerCase() : 'rows'} on the map`;
        }
        return;
      }

      if (L.type === 'heatmap') {
        plan.sources.push({ id, data: fc });
        const maxW = L.weight ? Math.max(1e-9, ...fc.features.map((f) => f.properties._w ?? 0)) : 1;
        const ramp = A.ramp(5, ink(L.ink ?? 3), T.bg);
        plan.layers.push({ id, type: 'heatmap', source: id, paint: {
          'heatmap-weight': L.weight ? ['/', ['coalesce', ['get', '_w'], 0], maxW] : 1,
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 6, (L.radius || 18) / 2, 12, L.radius || 18, 15, (L.radius || 18) * 2],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 6, 0.6, 13, L.intensity || 1.4],
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, A.mix(T.bg, ramp[0], 0) .replace('rgb(', 'rgba(').replace(')', ', 0)'), 0.15, ramp[0], 0.35, ramp[1], 0.55, ramp[2], 0.8, ramp[3], 1, ramp[4]],
          'heatmap-opacity': L.opacity ?? 0.85,
        } });
        if (L.points !== false) plan.layers.push({ id: `${id}-p`, type: 'circle', source: id, minzoom: L.pointsFrom ?? 13, paint: { 'circle-radius': 3, 'circle-color': ink(L.ink ?? 3), 'circle-stroke-width': 0.8, 'circle-stroke-color': T.bg } });
        if (L.points !== false) plan.clicks.push({ layer: `${id}-p`, points: true });
        overlay(id, 6, false);
        if (!plan.answer) plan.answer = `${fc.features.length.toLocaleString('en-US')} rows as density: darker is denser`;
        plan.legend.push({ title: L.title || `Density of ${h.label(h.view.coordinates || coords)}`, kind: 'ramp', ramp, from: 'fewer', to: 'more', note: `Kernel density (MapLibre heatmap, radius ${L.radius || 18} px at zoom 12)${L.weight ? `, each row weighted by ${h.label(L.weight)}` : ', every row counts once'}. Relative, not a rate: zoom in for single rows.`, n: fc.features.length });
        return;
      }

      // hexbin (H3)
      if (!h.h3) { plan.notes.push('hexbin: the hexagon grid (h3-js) did not load'); return; }
      const res = Math.max(0, Math.min(12, Number(L.resolution ?? 7)));
      const summary = (L.value && L.value.summary) || 'count';
      const prop = L.value && L.value.property;
      const bins = A.hexbin(h.h3, fc, res, summary, prop ? (i) => num(h.value(rows[i], prop)) : null);
      const values = bins.fc.features.map((f) => f.properties._v);
      const cls = shared && shared[id] ? shared[id].cls : A.classify(values, L.classes);
      plan.classes[id] = { cls };
      const colours = A.ramp(cls.count, ink(L.ink ?? 1), T.bg);
      bins.fc.features.forEach((f, i) => { const k = A.classOf(f.properties._v, cls); f.properties._k = k; f.properties._col = k < 0 ? T.muted : colours[k]; f.properties._rows = bins.cells[i].rows; });
      const maxV = Math.max(1e-9, ...values.filter((v) => v != null));
      const extrude = L.extrude ? (typeof L.extrude === 'object' ? L.extrude : {}) : null;
      if (extrude) for (const f of bins.fc.features) f.properties._h = f.properties._v == null ? 0 : (extrude.max || 4000) * (f.properties._v / maxV);
      plan.sources.push({ id, data: bins.fc });
      if (extrude) plan.layers.push({ id, type: 'fill-extrusion', source: id, paint: { 'fill-extrusion-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, ['get', '_col']], 'fill-extrusion-height': ['get', '_h'], 'fill-extrusion-opacity': 0.88 } });
      else {
        plan.layers.push({ id, type: 'fill', source: id, paint: { 'fill-color': ['get', '_col'], 'fill-opacity': L.opacity ?? 0.78 } });
        plan.layers.push({ id: `${id}-o`, type: 'line', source: id, paint: { 'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, T.bg], 'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.5, 0.6] } });
      }
      plan.clicks.push({ layer: id, cells: true });
      const what = summary === 'count' ? 'rows per hexagon' : `${summary} of ${h.label(prop)} per hexagon`;
      const edgeKm = h.h3.getHexagonEdgeLengthAvg(res, 'km');
      const leg = A.legendRows(values, cls, colours, (v) => h.fmt(v, summary === 'count' ? null : prop));
      plan.legend.push({ title: L.title || `${what[0].toUpperCase()}${what.slice(1)}`, unit: summary === 'count' ? 'rows' : h.unit(prop), kind: 'classes', method: `${A.METHODS[cls.method]}, ${cls.count} ${cls.count === 1 ? 'class' : 'classes'}`, ...leg, derived: true,
        note: `H3 resolution ${res} hexagons (about ${edgeKm < 1 ? `${Math.round(edgeKm * 1000)} m` : `${edgeKm.toFixed(1)} km`} a side), ${bins.cells.length.toLocaleString('en-US')} with rows.${extrude ? ' Column height ∝ value.' : ''} Hexagons with no rows are not drawn.` });
      const top = bins.cells.reduce((a, c) => (c.value != null && (!a || c.value > a.value) ? c : a), null);
      if (top && !plan.answer) plan.answer = `Busiest hexagon: ${h.fmt(top.value, summary === 'count' ? null : prop)} ${summary === 'count' ? 'rows' : h.unit(prop) || ''}`.trim();
      return;
    }

    // ---------------------------------------------------------------- regions: a geometry file joined to rows
    if (L.type === 'regions') {
      const geo = h.geometry(L.geometry);
      if (!geo) { plan.notes.push(`regions: ${L.geometry || 'geometry:'} ${L.geometry ? 'is loading or could not be read' : 'is not set'}`); return; }
      const g = A.placeGeometry(geo, spec.space);
      const rs = rows.filter(sel(L.filter));
      const ri = rs.map((r) => rowAt.get(r));
      const bi = L.bivariate;
      const joined = A.joinRegions(g, rs, {
        key: L.key || 'id', join: (r) => h.text(r, L.join || L.key || 'id'), summary: L.summary,
        value: L.value ? (r) => num(h.value(r, L.value)) : null,
        x: bi ? (r) => num(h.value(r, bi.x)) : null, y: bi ? (r) => num(h.value(r, bi.y)) : null,
      });
      for (const f of joined.features) f.properties._rows = f.properties._rows.map((i) => ri[i]);
      extendFc({ features: joined.features });
      let entry;
      if (bi) {
        const n = Math.max(2, Math.min(4, Number(bi.count) || 3));
        const sx = shared && shared[id] ? shared[id].cx : A.classify(joined.features.map((f) => f.properties._x), { method: bi.method || 'quantile', count: n });
        const sy = shared && shared[id] ? shared[id].cy : A.classify(joined.features.map((f) => f.properties._y), { method: bi.method || 'quantile', count: n });
        plan.classes[id] = { cx: sx, cy: sy };
        const grid = A.bivariateGrid(n, ink(bi.inkX ?? 0), ink(bi.inkY ?? 1), T.bg);
        let none = 0;
        for (const f of joined.features) {
          const kx = A.classOf(f.properties._x, sx), ky = A.classOf(f.properties._y, sy);
          f.properties._k = kx < 0 || ky < 0 ? -1 : ky * n + kx;
          f.properties._col = f.properties._k < 0 ? T.subtle : grid[Math.min(ky, grid.length - 1)][Math.min(kx, n - 1)];
          if (f.properties._k < 0) none++;
        }
        const both = joined.features.filter((f) => f.properties._k === n * n - 1).map((f) => h.featureName(f, L, rows));
        if (!plan.answer) plan.answer = both.length ? `High on both: ${both.join(', ')}` : `No region is in the top class of both`;
        entry = { title: L.title || `${h.label(bi.x)} × ${h.label(bi.y)}`, kind: 'bivariate', grid, n, x: { label: h.label(bi.x), unit: h.unit(bi.x), breaks: sx.breaks.map((b) => h.fmt(b, bi.x)) }, y: { label: h.label(bi.y), unit: h.unit(bi.y), breaks: sy.breaks.map((b) => h.fmt(b, bi.y)) }, method: `${A.METHODS[sx.method]}, ${sx.count} × ${sy.count} classes`, none };
      } else if (L.value) {
        const values = joined.features.map((f) => f.properties._v);
        const cls = shared && shared[id] ? shared[id].cls : A.classify(values, L.classes);
        plan.classes[id] = { cls };
        const colours = L.classes && L.classes.scheme === 'diverging' ? A.diverging(cls.count, ink(L.classes.low ?? 1), ink(L.ink ?? 0), T.bg) : A.ramp(cls.count, ink(L.ink ?? 0), T.bg);
        for (const f of joined.features) { const k = A.classOf(f.properties._v, cls); f.properties._k = k; f.properties._col = k < 0 ? T.subtle : colours[k]; }
        const leg = A.legendRows(values, cls, colours, (v) => h.fmt(v, L.value));
        entry = { title: L.title || h.label(L.value), unit: h.unit(L.value), kind: 'classes', method: `${A.METHODS[cls.method]}, ${cls.count} ${cls.count === 1 ? 'class' : 'classes'}`, ...leg };
        const best = joined.features.filter((f) => f.properties._v != null).sort((a, b) => b.properties._v - a.properties._v)[0];
        if (best && !plan.answer) plan.answer = `Highest: ${h.featureName(best, L, rows)} · ${h.fmt(best.properties._v, L.value)} ${h.unit(L.value) || ''}`.trim();
      } else {
        // a plan or outline: colour by a feature property's value (kind) when asked, else one neutral fill
        const by = L.color;
        for (const f of joined.features) {
          const v = by ? f.properties[by] : null;
          f.properties._k = 0;
          f.properties._col = by && v != null ? ink(Math.abs(hashText(String(v))) % T.series.length) : T.subtle;
        }
        if (by) {
          const kinds = A.countBy(joined.features.map((_, i) => i), (i) => joined.features[i].properties[by]);
          entry = { title: L.title || by, kind: 'swatches', rows: kinds.map(([v, n]) => ({ label: v ?? '—', colour: v == null ? T.subtle : ink(Math.abs(hashText(String(v))) % T.series.length), n })) };
        }
      }
      if (L.extrude) {
        const ep = typeof L.extrude === 'string' ? L.extrude : L.extrude.property;
        const maxE = Math.max(1e-9, ...joined.features.map((f) => { const rs2 = f.properties._rows.map((i) => num(h.value(rows[i], ep))).filter((v) => v != null); return rs2.length ? rs2.reduce((a, b) => a + b, 0) : 0; }));
        for (const f of joined.features) { const vs = f.properties._rows.map((i) => num(h.value(rows[i], ep))).filter((v) => v != null); f.properties._h = vs.length ? ((L.extrude.max || 60000) * vs.reduce((a, b) => a + b, 0)) / maxE : 0; }
        if (entry) entry.note = `${entry.note ? `${entry.note} ` : ''}Height ∝ ${h.label(ep)}${h.unit(ep) ? ` (${h.unit(ep)})` : ''}; the tallest is ${h.fmt(maxE, ep)}.`;
      }
      const fc = { type: 'FeatureCollection', features: joined.features };
      plan.sources.push({ id, data: fc });
      const selW = ['case', ['boolean', ['feature-state', 'sel'], false], 3, 0.8];
      const selC = ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, L.value || bi ? T.bg : T.border];
      if (L.extrude) plan.layers.push({ id, type: 'fill-extrusion', source: id, paint: { 'fill-extrusion-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, ['get', '_col']], 'fill-extrusion-height': ['get', '_h'], 'fill-extrusion-opacity': 0.9 } });
      else {
        plan.layers.push({ id, type: 'fill', source: id, filter: ['>=', ['get', '_k'], 0], paint: { 'fill-color': ['get', '_col'], 'fill-opacity': L.opacity ?? (L.value || bi ? 0.85 : L.color ? 0.3 : 0.12) } });
        plan.layers.push({ id: `${id}-x`, type: 'fill', source: id, filter: ['<', ['get', '_k'], 0], paint: { 'fill-pattern': 'dv-hatch', 'fill-opacity': 0.9 } });
        plan.layers.push({ id: `${id}-o`, type: 'line', source: id, paint: { 'line-color': selC, 'line-width': selW } });
      }
      if (L.label) {
        const lp = A.labelPoints(joined.features, (f) => h.featureName(f, L, rows));
        plan.sources.push({ id: `${id}-lp`, data: lp });
        plan.layers.push({ id: `${id}-l`, type: 'symbol', source: `${id}-lp`, layout: { 'text-field': ['get', '_label'], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-max-width': 8, 'text-optional': true }, paint: { 'text-color': T.fg, 'text-halo-color': T.bg, 'text-halo-width': 1.4 } });
      }
      plan.clicks.push({ layer: L.extrude ? id : id, regions: true, also: L.extrude ? [] : [`${id}-x`], name: (f) => h.featureName(f, L, rows) });
      if (entry) {
        if (joined.multi && !L.summary) entry.note = `${entry.note ? `${entry.note} ` : ''}${joined.multi} regions have several rows: each shows its first row in the view's sort (set summary: sum, mean, min or max).`;
        if (joined.unmatched.length) entry.note = `${entry.note ? `${entry.note} ` : ''}${joined.unmatched.length} ${joined.unmatched.length === 1 ? 'key has' : 'keys have'} no shape: ${joined.unmatched.slice(0, 4).join(', ')}${joined.unmatched.length > 4 ? '…' : ''}.`;
        plan.legend.push(entry);
      }
      return;
    }

    // ---------------------------------------------------------------- flows: arcs from one position to another
    if (L.type === 'flows') {
      const rs = rows.filter(sel(L.filter));
      const feats = [];
      let skipped = 0;
      const maxW = shared && shared[id] ? shared[id].maxW : Math.max(1e-9, ...rs.map((r) => num(h.value(r, L.width && L.width.property)) ?? 0));
      plan.classes[id] = { maxW };
      for (const r of rs) {
        const a = A.position(h.raw(r, L.from), spec.space), b = A.position(h.raw(r, L.to), spec.space);
        if (!a || !b) { skipped++; continue; }
        const v = L.width && L.width.property ? num(h.value(r, L.width.property)) : null;
        const line = A.arc(a, b, L.bow ?? 0.18);
        line.id = feats.length;
        line.properties = { _i: rowAt.get(r), _v: v, _w: v == null ? 1 : 1 + ((L.width.max || 14) - 1) * Math.sqrt(v / maxW), _col: L.color && h.isProperty(L.color) ? h.colourOf(r, L.color) : h.colour(L.color) || ink(2) };
        feats.push(line);
        extend(...a); extend(...b);
      }
      plan.sources.push({ id, data: { type: 'FeatureCollection', features: feats }, lineMetrics: true });
      plan.layers.push({ id, type: 'line', source: id, layout: { 'line-cap': 'round' }, paint: { 'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, ['get', '_col']], 'line-width': ['get', '_w'], 'line-opacity': 0.78 } });
      plan.layers.push({ id: `${id}-a`, type: 'symbol', source: id, layout: { 'symbol-placement': 'line', 'symbol-spacing': 90, 'text-field': '›', 'text-font': ['Noto Sans Regular'], 'text-size': ['+', 12, ['get', '_w']], 'text-keep-upright': false, 'text-allow-overlap': true }, paint: { 'text-color': T.bg, 'text-opacity': 0.9 } });
      // the ends: where flows start (hollow) and end (filled)
      const ends = [];
      for (const f of feats) { const c = f.geometry.coordinates; ends.push({ type: 'Feature', geometry: { type: 'Point', coordinates: c[0] }, properties: { _end: 0 } }, { type: 'Feature', geometry: { type: 'Point', coordinates: c[c.length - 1] }, properties: { _end: 1 } }); }
      plan.sources.push({ id: `${id}-e`, data: { type: 'FeatureCollection', features: ends } });
      plan.layers.push({ id: `${id}-e`, type: 'circle', source: `${id}-e`, paint: { 'circle-radius': 5, 'circle-color': ['case', ['==', ['get', '_end'], 1], T.fg, T.bg], 'circle-stroke-color': T.fg, 'circle-stroke-width': 1.5 } });
      plan.clicks.push({ layer: id, points: true });
      const total = feats.reduce((s, f) => s + (f.properties._v || 0), 0);
      plan.legend.push({ title: L.title || `Flows by ${h.label(L.width && L.width.property)}`, kind: 'flows', unit: h.unit(L.width && L.width.property), rows: L.color && h.isProperty(L.color) ? A.countBy(feats.map((f) => f.properties._i), (i) => h.text(rows[i], L.color)).map(([v, n]) => ({ label: v ?? '—', colour: h.colourOf(rows.find((r) => h.text(r, L.color) === v), L.color), n })) : [],
        size: L.width && L.width.property ? { property: h.label(L.width.property), unit: h.unit(L.width.property), maxText: h.fmt(maxW, L.width.property), rule: 'line width ∝ √value', max: L.width.max || 14 } : null,
        note: `Hollow dot: where a flow starts; filled: where it ends; › points the way.${skipped ? ` ${skipped} ${skipped === 1 ? 'row has' : 'rows have'} no position at one end and ${skipped === 1 ? 'is' : 'are'} not drawn.` : ''}` });
      if (!plan.answer && total) plan.answer = `${feats.length} flows · ${h.fmt(total, L.width.property)} ${h.unit(L.width.property) || ''} in all`.trim();
      return;
    }

    // ---------------------------------------------------------------- lines: a path property
    if (L.type === 'lines') {
      const rs = rows.filter(sel(L.filter));
      const feats = [];
      for (const r of rs) {
        const p = A.pathOf(h.raw(r, L.path), spec.space);
        if (!p) continue;
        p.forEach((c) => extend(...c));
        feats.push({ type: 'Feature', id: feats.length, geometry: { type: 'LineString', coordinates: p }, properties: { _i: rowAt.get(r), _col: L.color && h.isProperty(L.color) ? h.colourOf(r, L.color) : h.colour(L.color) || ink(li), _km: A.pathKm(p) } });
      }
      plan.sources.push({ id, data: { type: 'FeatureCollection', features: feats } });
      plan.layers.push({ id: `${id}-h`, type: 'line', source: id, layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': T.bg, 'line-width': (L.width || 3) + 3, 'line-opacity': 0.8 } });
      plan.layers.push({ id, type: 'line', source: id, layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, ['get', '_col']], 'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], (L.width || 3) + 2, L.width || 3], ...(L.dashed ? { 'line-dasharray': [2, 1.5] } : {}) } });
      plan.clicks.push({ layer: id, points: true });
      if (!plan.answer && feats.length) plan.answer = `${feats.length} ${feats.length === 1 ? 'route' : 'routes'} · ${feats.reduce((a, f) => a + f.properties._km, 0).toFixed(1)} km in all`;
      plan.legend.push({ title: L.title || h.label(L.path), kind: 'swatches', rows: feats.map((f) => ({ label: `${h.text(rows[f.properties._i], h.titleProperty) ?? rows[f.properties._i].id} · ${f.properties._km.toFixed(1)} km`, colour: f.properties._col, n: null })), note: `Lengths are straight-line legs along the stored path (Turf distance), derived.${L.note ? ` ${L.note}` : ''}` });
      return;
    }

    // ---------------------------------------------------------------- rings, catchments, within: sites vs demand
    if (L.type === 'rings' || L.type === 'catchments' || L.type === 'within') {
      const isSite = sel(L.of), isDemand = L.count ? sel(L.count) : (r) => !isSite(r);
      const pos = at(coords);
      const sites = [], demand = [];
      rows.forEach((r, i) => { const p = pos(r); if (!p) return; if (isSite(r)) sites.push({ i, at: p }); else if (isDemand(r)) demand.push({ i, at: p }); });
      for (const s of [...sites, ...demand]) extend(...s.at);
      const dName = L.countLabel || 'rows', sName = L.ofLabel || 'sites';
      const one = (word) => word.replace(/ies$/, 'y').replace(/s$/, '');
      // a site with no name (withheld, untagged) reads as its kind, never as a raw id
      const siteName = (i) => h.text(rows[i], h.titleProperty) ?? (h.text(rows[i], 'kind') ? `an unnamed ${h.text(rows[i], 'kind')}` : String(rows[i].id));
      if (L.type === 'rings') {
        const kms = (Array.isArray(L.km) ? L.km : [L.km || 10]).map(Number);
        const r = A.rings(sites, kms, demand);
        const shades = A.ramp(kms.length, ink(L.ink ?? 0), T.bg).reverse();
        r.fc.features.forEach((f, i) => { f.id = i; f.properties._col = shades[kms.slice().sort((a, b) => a - b).indexOf(f.properties._km)]; });
        plan.sources.push({ id, data: r.fc });
        plan.layers.push({ id, type: 'fill', source: id, paint: { 'fill-color': ['get', '_col'], 'fill-opacity': 0.16 } });
        plan.layers.push({ id: `${id}-o`, type: 'line', source: id, paint: { 'line-color': ['get', '_col'], 'line-width': 1.2, 'line-dasharray': [3, 2] } });
        let cum = 0;
        plan.legend.push({ title: L.title || `${dName[0].toUpperCase()}${dName.slice(1)} by distance to the nearest of ${sites.length} ${sName}`, kind: 'bands', derived: true,
          rows: r.bands.map((b, i) => { cum += b.n; return { label: `within ${b.km} km`, colour: shades[i], n: b.n, cum, rows: b.rows }; }).concat([{ label: `beyond ${Math.max(...kms)} km`, colour: T.subtle, n: r.outside, rows: r.beyond }]),
          note: `Rings are geodesic circles (Turf circle) around each ${one(sName)}; each ${one(dName)} counts once, in the smallest ring of its nearest ${one(sName)}. Straight-line distance, not drive time.` });
        plan.sections.push({ kind: 'bands', id });
        if (!plan.answer && demand.length) plan.answer = `${r.bands[0].n} of ${demand.length} ${dName} within ${r.bands[0].km} km of a ${one(sName)}`;
        plan.siteLayer = { sites, demand };
      } else if (L.type === 'catchments') {
        const c = A.catchments(sites, demand);
        const values = c.fc.features.map((f) => f.properties._v);
        const cls = A.classify(values, L.classes || { method: 'quantile', count: 4 });
        const colours = A.ramp(cls.count, ink(L.ink ?? 4), T.bg);
        c.fc.features.forEach((f) => { const k = A.classOf(f.properties._v, cls); f.properties._k = k; f.properties._col = colours[k] || T.subtle; f.properties._rows = (c.counts.find((x) => x.site === f.properties._site) || { rows: [] }).rows; f.properties._name = siteName(f.properties._site); });
        plan.sources.push({ id, data: c.fc });
        plan.layers.push({ id, type: 'fill', source: id, paint: { 'fill-color': ['get', '_col'], 'fill-opacity': L.opacity ?? 0.38 } });
        plan.layers.push({ id: `${id}-o`, type: 'line', source: id, paint: { 'line-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, T.fg], 'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 3, 0.8], 'line-opacity': 0.7 } });
        plan.clicks.push({ layer: id, regions: true, name: (f) => `${f.properties._name}'s catchment` });
        const leg = A.legendRows(values, cls, colours, (v) => String(v));
        plan.legend.push({ title: L.title || `${dName[0].toUpperCase()}${dName.slice(1)} per catchment`, unit: dName, kind: 'classes', method: `${A.METHODS[cls.method]}, ${cls.count} classes`, ...leg, derived: true,
          note: `Each area is the land closer to one ${one(sName)} than to any other (a Voronoi diagram, Turf voronoi), straight-line. Click an area for its ${dName}.` });
        const top = c.counts.slice().sort((a, b) => b.n - a.n)[0];
        if (!plan.answer && top) plan.answer = `Largest catchment: ${siteName(top.site)} · ${top.n} ${dName}`;
      } else {
        const km = Number(h.state.withinKm ?? L.km ?? 10);
        const w = A.within(sites, demand, km);
        const spot = new Map(demand.map((d) => [d.i, d.at]));
        const feats = w.each.map((e) => ({ type: 'Feature', id: e.i, geometry: { type: 'Point', coordinates: spot.get(e.i) }, properties: { _i: e.i, _in: e.inside ? 1 : 0, _km: e.km } }));
        const r = A.rings(sites, [km], []);
        plan.sources.push({ id: `${id}-r`, data: r.fc });
        plan.layers.push({ id: `${id}-r`, type: 'fill', source: `${id}-r`, paint: { 'fill-color': ink(0), 'fill-opacity': 0.1 } });
        plan.layers.push({ id: `${id}-ro`, type: 'line', source: `${id}-r`, paint: { 'line-color': ink(0), 'line-width': 1, 'line-dasharray': [3, 2] } });
        plan.sources.push({ id, data: { type: 'FeatureCollection', features: feats } });
        plan.layers.push({ id, type: 'circle', source: id, paint: { 'circle-radius': 5, 'circle-color': ['case', ['==', ['get', '_in'], 1], ink(0), T.bg], 'circle-stroke-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, ['==', ['get', '_in'], 1], T.bg, T.muted], 'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.5, 1.5] } });
        const siteFc = { type: 'FeatureCollection', features: sites.map((s) => ({ type: 'Feature', id: s.i, geometry: { type: 'Point', coordinates: s.at }, properties: { _i: s.i } })) };
        plan.sources.push({ id: `${id}-s`, data: siteFc });
        plan.layers.push({ id: `${id}-s`, type: 'circle', source: `${id}-s`, paint: { 'circle-radius': 4, 'circle-color': T.fg, 'circle-stroke-color': ['case', ['boolean', ['feature-state', 'sel'], false], T.accent, T.bg], 'circle-stroke-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.5, 1.5] } });
        plan.clicks.push({ layer: id, points: true }, { layer: `${id}-s`, points: true });
        plan.legend.push({ title: L.title || `${dName[0].toUpperCase()}${dName.slice(1)} within ${km} km of a ${one(sName)}`, kind: 'swatches', derived: true,
          rows: [{ label: `within ${km} km`, colour: ink(0), n: w.inside, rows: w.each.filter((e) => e.inside).map((e) => e.i) }, { label: `farther`, colour: T.bg, n: w.outside, rows: w.each.filter((e) => !e.inside).map((e) => e.i) }, { label: sName, colour: T.fg, n: sites.length, rows: sites.map((s) => s.i) }],
          note: `Distance to the nearest ${one(sName)}, straight-line (Turf distance). Drag the slider to change it.` });
        plan.sections.push({ kind: 'within', id, km, min: L.min ?? 1, max: L.max ?? 100, step: L.step ?? 1, each: w.each });
        if (!plan.answer) plan.answer = `${w.inside} of ${demand.length} ${dName} within ${km} km`;
      }
      return;
    }

    // ---------------------------------------------------------------- labels and callouts (HTML, drawn by the view)
    if (L.type === 'labels') {
      plan.callouts = plan.callouts || [];
      if (!plan.answer && L.text) plan.answer = `${rows.length} ${rows.length === 1 ? 'figure' : 'figures'}, each at its place`;
      if (L.text) {
        for (let i = 0; i < rows.length; i++) {
          const p = at(coords)(rows[i]);
          if (!p) continue;
          extend(...p);
          // WHY staggered: callouts of nearby rows would stack on one spot; with no dx/dy property they fan out
          const k = plan.callouts.length;
          const detail = L.detail ? (Array.isArray(L.detail) ? L.detail : [L.detail]).map((d) => h.cellText(rows[i], d)).filter((t) => t && t !== '—').join(' ') : null;
          plan.callouts.push({ at: p, text: h.text(rows[i], L.text), detail, i, dx: num(h.value(rows[i], L.dx)) ?? (k % 2 ? 70 : -70), dy: num(h.value(rows[i], L.dy)) ?? -(30 + 34 * (k % 3)) });
        }
      }
      for (const n of Array.isArray(L.notes) ? L.notes : []) {
        const p = A.position(n.at, spec.space);
        if (!p) continue;
        extend(...p);
        plan.callouts.push({ at: p, text: String(n.text ?? ''), detail: n.detail ? String(n.detail) : null, i: null, dx: Number(n.dx) || 0, dy: Number(n.dy) || 0, note: true });
      }
    }
  });
  return all === rows ? plan : remap(plan, rows, all);
}

/** A plan built on a subset of the rows (a small multiple, a swipe side) speaks in indexes into that subset; the view
    reads every index against the full rows (clicks, names, the peek), so they are moved to the full list here. */
function remap(plan, rows, all) {
  const at = new Map(all.map((r, i) => [r, i]));
  const to = (i) => (i == null || rows[i] === undefined ? i : at.get(rows[i]));
  for (const s of plan.sources) for (const f of (s.data && s.data.features) || []) {
    const p = f.properties;
    if (!p) continue;
    if (p._i != null) p._i = to(p._i);
    if (p._site != null) p._site = to(p._site);
    if (Array.isArray(p._rows)) p._rows = p._rows.map(to);
  }
  for (const g of plan.legend) for (const r of g.rows || []) if (Array.isArray(r.rows)) r.rows = r.rows.map(to);
  for (const c of plan.callouts || []) if (c.i != null) c.i = to(c.i);
  for (const sec of plan.sections) for (const e of sec.each || []) e.i = to(e.i);
  return plan;
}

/** A stable small hash for colouring a feature property's values (the same hue for the same text). */
export function hashText(s) {
  let x = 0;
  for (let i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) | 0;
  return x;
}
