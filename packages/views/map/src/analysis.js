/* The map view's analysis half (docs/CONTRACT.md §42): rows -> GeoJSON, classes, legends and the spatial answers
   (rings, catchments, within a distance, hexagons, a drawn area). Pure: no DOM, no MapLibre, nothing from
   @data-ui/core, so tests/unit/map.test.mjs runs it in Node. The view passes in how to read a cell (`value`), where a
   row is (`at`) and a filter compiler (`match`).

   STOCK PARTS: Turf.js 7.4.0 (MIT) for every geometric question: circle, voronoi, distance, booleanPointInPolygon,
   bezierSpline, bbox, centroid/pointOnFeature; h3-js 4.5.0 (Apache-2.0) for hexagon bins (Uber's H3 grid, the one
   kepler.gl and deck.gl's H3HexagonLayer use); simple-statistics 7.12.1 (ISC) for class breaks (ckmeans is its
   Jenks natural breaks, quantile, equalIntervalBreaks). OURS: the row <-> feature plumbing, the legend model, the
   token-derived colour ramps (a WebGL style cannot read var(), so colours are mixed here from input.tokens).

   TRUTHFUL RENDERING (Zach's rule): a missing value is never 0. A row or region with no value gets the "no data"
   class (drawn hatched-neutral, counted in the legend); every legend states its property, unit and how the classes
   were cut; a derived number (a hexagon's count, a catchment's count, a distance) says it is derived. */

import { bbox as turfBbox, bezierSpline, booleanPointInPolygon, circle, distance, featureCollection, lineString, point, pointOnFeature, voronoi } from '@turf/turf';
import { ckmeans, equalIntervalBreaks, quantile } from 'simple-statistics';

/* ------------------------------------------------------------------ space: geo, or local metres on a plan */

/** Degrees of longitude (= latitude, at the equator) per metre: a local plan in metres is drawn on the Web Mercator
    map just north-east of (0, 0), where one degree is 111,320 m both ways (within 0.1% inside 1 km), so MapLibre's
    scale bar, zoom and pan work in metres. WHY not a second engine: one map engine (Zach's 2026-10-10 decision), and
    MapLibre has no non-geographic CRS. */
export const M_PER_DEG = 111320;
export const localToLngLat = ([x, y]) => [x / M_PER_DEG, y / M_PER_DEG];
export const lngLatToLocal = ([lng, lat]) => [lng * M_PER_DEG, lat * M_PER_DEG];

/** [lng, lat] of a cell: [lat, lng] or 'lat, lng' in geo space, [x, y] metres in local space; null when unusable. */
export function position(raw, space = 'geo') {
  let v = raw;
  if (v == null || v === '') return null;
  if (typeof v === 'string') v = v.split(',').map((x) => Number(x.trim()));
  if (!Array.isArray(v) || v.length !== 2) return null;
  const [a, b] = v.map(Number);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  if (space === 'local') return localToLngLat([a, b]);
  return Math.abs(a) <= 90 && Math.abs(b) <= 180 ? [b, a] : null;
}

/** A GeoJSON geometry from a file, moved into map space (local plans: metres -> degrees). */
export function placeGeometry(geojson, space = 'geo') {
  if (space !== 'local') return geojson;
  const move = (c) => (typeof c[0] === 'number' ? localToLngLat(c) : c.map(move));
  return { ...geojson, features: (geojson.features || []).map((f) => ({ ...f, geometry: f.geometry && { ...f.geometry, coordinates: move(f.geometry.coordinates) } })) };
}

/* ------------------------------------------------------------------ colour: mixed from tokens */

export function rgbOf(text) {
  const m = /rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/.exec(String(text));
  if (m) return [+m[1], +m[2], +m[3]];
  const h = /^#([0-9a-f]{6})$/i.exec(String(text).trim());
  if (h) return [0, 2, 4].map((i) => parseInt(h[1].slice(i, i + 2), 16));
  return [128, 128, 128];
}
const css = ([r, g, b]) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
export const mix = (a, b, t) => { const x = rgbOf(a), y = rgbOf(b); return css(x.map((v, i) => v + (y[i] - v) * t)); };

/** n sequential colours from the surface towards `ink` (a series token): the first is light enough to read the
    basemap through, the last is the full colour. Light and dark both: the surface is the theme's own bg. */
export function ramp(n, ink, bg) {
  if (n <= 1) return [ink];
  return Array.from({ length: n }, (_, i) => mix(bg, ink, 0.18 + (0.82 * i) / (n - 1)));
}

/** A diverging ramp: `lo` ink - surface - `hi` ink, n colours (odd n has the neutral middle). */
export function diverging(n, lo, hi, bg) {
  return Array.from({ length: n }, (_, i) => {
    const t = n === 1 ? 0.5 : i / (n - 1);
    return t < 0.5 ? mix(bg, lo, 0.2 + 1.6 * (0.5 - t)) : t > 0.5 ? mix(bg, hi, 0.2 + 1.6 * (t - 0.5)) : mix(bg, lo, 0.12);
  });
}

/** The bivariate grid (Joshua Stevens' 3x3 scheme, built from two series tokens): grid[y][x], x and y 0..n-1. */
export function bivariateGrid(n, inkX, inkY, bg) {
  return Array.from({ length: n }, (_, y) => Array.from({ length: n }, (_, x) => {
    const tx = n === 1 ? 1 : x / (n - 1), ty = n === 1 ? 1 : y / (n - 1);
    const a = rgbOf(mix(bg, inkX, 0.1 + 0.9 * tx)), b = rgbOf(mix(bg, inkY, 0.1 + 0.9 * ty)), s = rgbOf(bg);
    // multiply the two tints over the surface: high-high is the darkest, low-low is the surface
    return css(a.map((v, i) => (v * b[i]) / Math.max(1, s[i])));
  }));
}

/* ------------------------------------------------------------------ classes */

export const METHODS = { quantile: 'quantiles', equal: 'equal intervals', jenks: 'natural breaks (Jenks, ckmeans)', manual: 'set breaks', unique: 'one colour per value' };

/** Class breaks of `values` (numbers only; nulls are counted apart): {method, breaks: [upper bound of each class
    but the last], count, min, max}. Fewer distinct values than classes: one class per value. */
export function classify(values, spec = {}) {
  const nums = values.filter((v) => typeof v === 'number' && Number.isFinite(v)).sort((a, b) => a - b);
  const method = METHODS[spec.method] ? spec.method : 'quantile';
  const want = Math.max(1, Math.min(9, Number(spec.count) || 5));
  const out = { method, count: want, min: nums[0] ?? null, max: nums[nums.length - 1] ?? null, breaks: [] };
  if (!nums.length) return { ...out, count: 0 };
  const distinct = [...new Set(nums)];
  if (method === 'manual' && Array.isArray(spec.breaks)) {
    out.breaks = spec.breaks.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    out.count = out.breaks.length + 1;
    return out;
  }
  if (distinct.length <= want) {
    out.breaks = distinct.slice(0, -1);
    out.count = distinct.length;
    out.method = 'unique';
    return out;
  }
  if (method === 'equal') out.breaks = equalIntervalBreaks(nums, want).slice(1, -1);
  else if (method === 'jenks') out.breaks = ckmeans(nums, want).slice(0, -1).map((c) => c[c.length - 1]);
  else out.breaks = Array.from({ length: want - 1 }, (_, i) => quantile(nums, (i + 1) / want));
  out.breaks = [...new Set(out.breaks)];
  out.count = out.breaks.length + 1;
  return out;
}

/** The class index of v (0..count-1), or -1 for no value. A value equal to a break falls in the lower class. */
export function classOf(v, cls) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return -1;
  let i = 0;
  while (i < cls.breaks.length && v > cls.breaks[i]) i++;
  return i;
}

/** Legend rows for classes: [{from, to, colour, n}] plus the no-data row's count. `fmt` formats a number. */
export function legendRows(values, cls, colours, fmt = String) {
  const n = new Array(cls.count).fill(0);
  let none = 0;
  for (const v of values) { const k = classOf(v, cls); if (k < 0) none++; else n[k]++; }
  const rows = [];
  for (let i = 0; i < cls.count; i++) {
    const lo = i === 0 ? cls.min : cls.breaks[i - 1], hi = i === cls.count - 1 ? cls.max : cls.breaks[i];
    const label = cls.method === 'unique' ? fmt(i === cls.count - 1 ? cls.max : cls.breaks[i]) : i === 0 ? `${fmt(lo)} – ${fmt(hi)}` : `> ${fmt(lo)} – ${fmt(hi)}`;
    rows.push({ label, colour: colours[i], n: n[i] });
  }
  return { rows, none };
}

/* ------------------------------------------------------------------ points */

/** Rows -> point features with `_i` (the row's index in rows) and the asked numeric/text props copied flat. Rows
    with no position are counted in `missing` with their reason. */
export function pointFeatures(rows, at, props = {}) {
  const features = [];
  let missing = 0;
  for (let i = 0; i < rows.length; i++) {
    const p = at(rows[i]);
    if (!p) { missing++; continue; }
    const properties = { _i: i };
    for (const [k, read] of Object.entries(props)) properties[k] = read(rows[i]);
    features.push({ type: 'Feature', id: i, geometry: { type: 'Point', coordinates: p }, properties });
  }
  return { fc: featureCollection(features), missing };
}

/** A proportional symbol's radius: area proportional to the value (Flannery's rule is not applied: true area). */
export function symbolRadius(v, maxValue, maxRadius = 24, minRadius = 2) {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || !(maxValue > 0)) return null;
  return Math.max(minRadius, maxRadius * Math.sqrt(v / maxValue));
}

/* ------------------------------------------------------------------ regions */

/** Join rows to region features by key. `summary` folds several rows on one region (sum, mean, min, max, first;
    default first, and `multi` says how many regions had several). Returns the features (each with `_v`, `_rows`
    indexes, `_label`) and the rows that found no region. */
export function joinRegions(geojson, rows, { key, join, value, summary = 'first', x, y }) {
  const byKey = new Map();
  for (let i = 0; i < rows.length; i++) {
    const k = join(rows[i]);
    if (k == null || k === '') continue;
    const s = String(k);
    if (!byKey.has(s)) byKey.set(s, []);
    byKey.get(s).push(i);
  }
  const used = new Set();
  let multi = 0;
  const fold = (idxs, read) => {
    const vs = idxs.map((i) => read(rows[i])).filter((v) => typeof v === 'number' && Number.isFinite(v));
    if (!vs.length) return null;
    if (summary === 'sum') return vs.reduce((a, b) => a + b, 0);
    if (summary === 'mean') return vs.reduce((a, b) => a + b, 0) / vs.length;
    if (summary === 'min') return Math.min(...vs);
    if (summary === 'max') return Math.max(...vs);
    return typeof read(rows[idxs[0]]) === 'number' ? read(rows[idxs[0]]) : null;
  };
  const features = (geojson.features || []).map((f, fi) => {
    const k = f.properties ? f.properties[key] : undefined;
    const idxs = k == null ? [] : byKey.get(String(k)) || [];
    if (idxs.length) used.add(String(k));
    if (idxs.length > 1) multi++;
    const properties = { ...f.properties, _f: fi, _rows: idxs, _n: idxs.length };
    if (value) properties._v = idxs.length ? fold(idxs, value) : null;
    if (x) properties._x = idxs.length ? fold(idxs, x) : null;
    if (y) properties._y = idxs.length ? fold(idxs, y) : null;
    return { ...f, id: fi, properties };
  });
  const unmatched = [...byKey.keys()].filter((k) => !used.has(k));
  return { features, unmatched, multi };
}

/** A label point per feature (Turf's pointOnFeature: inside the polygon, unlike a centroid of a C-shaped region). */
export function labelPoints(features, text) {
  return featureCollection(features.filter((f) => f.geometry).map((f) => {
    const p = pointOnFeature(f);
    return { type: 'Feature', id: f.id, geometry: p.geometry, properties: { _f: f.id, _label: text(f) } };
  }));
}

/* ------------------------------------------------------------------ hexagons (H3) */

/** Bin point features into H3 cells at `resolution`. `read(i)` gives row i's value for sum/mean/max. Returns
    {cells: [{h3, rows: [i], value}], toFeatures(h3js)}. h3 is passed in so this module stays light. */
export function hexbin(h3, fc, resolution, summary = 'count', read = null) {
  const cells = new Map();
  for (const f of fc.features) {
    const [lng, lat] = f.geometry.coordinates;
    const h = h3.latLngToCell(lat, lng, resolution);
    if (!cells.has(h)) cells.set(h, []);
    cells.get(h).push(f.properties._i);
  }
  const out = [];
  for (const [h, idxs] of cells) {
    let value = idxs.length;
    if (summary !== 'count' && read) {
      const vs = idxs.map(read).filter((v) => typeof v === 'number' && Number.isFinite(v));
      value = !vs.length ? null : summary === 'sum' ? vs.reduce((a, b) => a + b, 0) : summary === 'mean' ? vs.reduce((a, b) => a + b, 0) / vs.length : Math.max(...vs);
    }
    out.push({ h3: h, rows: idxs, value });
  }
  const features = out.map((c, i) => ({
    type: 'Feature', id: i,
    // WHY true: GeoJSON order is [lng, lat] (h3's default is [lat, lng]), and the ring comes back closed
    geometry: { type: 'Polygon', coordinates: [h3.cellToBoundary(c.h3, true)] },
    properties: { _h3: c.h3, _v: c.value, _n: c.rows.length },
  }));
  return { cells: out, fc: featureCollection(features) };
}

/* ------------------------------------------------------------------ flows and lines */

/** A curved arc from a to b ([lng, lat]), bowed to the right of travel by `bow` × its length, as a LineString. Two
    flows between the same pair in opposite directions bow apart, so both stay visible. */
export function arc(a, b, bow = 0.18) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  if (!dx && !dy) return lineString([a, b]);
  const mid = [(a[0] + b[0]) / 2 + dy * bow, (a[1] + b[1]) / 2 - dx * bow];
  return bezierSpline(lineString([a, mid, b]), { resolution: 2000, sharpness: 0.85 });
}

/** Path cells ([[lat, lng], ...] or [[x, y], ...] in local space) -> [lng, lat] coordinates; null when < 2 usable. */
export function pathOf(raw, space = 'geo') {
  if (!Array.isArray(raw)) return null;
  const pts = raw.map((p) => position(p, space)).filter(Boolean);
  return pts.length >= 2 ? pts : null;
}

/** Length of a [lng, lat] path in km (Turf's great-circle distance per leg). */
export function pathKm(coords) {
  let km = 0;
  for (let i = 1; i < coords.length; i++) km += distance(coords[i - 1], coords[i], { units: 'kilometers' });
  return km;
}

/* ------------------------------------------------------------------ rings, catchments, within */

/** Rings of `km` radii around each site; with demand points, how many fall in each band of each site's NEAREST
    rings (a point is counted once, in the smallest ring of its nearest site that holds it). */
export function rings(sites, kms, demand = []) {
  const sorted = [...kms].map(Number).filter((k) => k > 0).sort((a, b) => a - b);
  const features = [];
  for (const s of sites) for (const km of [...sorted].reverse()) {
    features.push(circle(s.at, km, { steps: 64, units: 'kilometers', properties: { _site: s.i, _km: km } }));
  }
  const bands = sorted.map((km) => ({ km, n: 0, rows: [] }));
  let outside = 0;
  const beyond = [];
  for (const d of demand) {
    const near = nearest(d.at, sites);
    const band = near ? bands.find((b) => near.km <= b.km) : null;
    if (band) { band.n++; band.rows.push(d.i); } else { outside++; beyond.push(d.i); }
  }
  return { fc: featureCollection(features), bands, outside, beyond };
}

/** The nearest site to a [lng, lat]: {site, km}, or null without sites. */
export function nearest(at, sites) {
  let best = null;
  for (const s of sites) {
    const km = distance(at, s.at, { units: 'kilometers' });
    if (!best || km < best.km) best = { site: s, km };
  }
  return best;
}

/** Voronoi catchments of sites (each the area closer to that site than to any other), clipped to a box around
    sites and demand, and each demand point assigned to its nearest site. Duplicate sites share one cell. */
export function catchments(sites, demand = [], pad = 0.5) {
  const all = [...sites, ...demand].map((s) => s.at);
  if (!sites.length) return { fc: featureCollection([]), counts: [] };
  const [w, s, e, n] = turfBbox(featureCollection(all.map((p) => point(p))));
  const box = [w - pad, s - pad, e + pad, n + pad];
  const seen = new Map();
  const uniq = [];
  for (const site of sites) { const k = site.at.map((v) => v.toFixed(6)).join(','); if (!seen.has(k)) { seen.set(k, uniq.length); uniq.push(site); } }
  const cells = voronoi(featureCollection(uniq.map((site) => point(site.at, { _site: site.i }))), { bbox: box });
  const counts = uniq.map((site) => ({ site: site.i, n: 0, rows: [], km: [] }));
  for (const d of demand) {
    const near = nearest(d.at, uniq);
    if (!near) continue;
    const c = counts[uniq.indexOf(near.site)];
    c.n++; c.rows.push(d.i); c.km.push(near.km);
  }
  const features = cells.features.map((f, i) => (f ? { ...f, id: i, properties: { _site: uniq[i].i, _n: counts[i].n, _v: counts[i].n } } : null)).filter(Boolean);
  return { fc: featureCollection(features), counts };
}

/** Demand points within `km` of their nearest site: [{i, km, inside}] and the totals. */
export function within(sites, demand, km) {
  const each = demand.map((d) => { const near = nearest(d.at, sites); return { i: d.i, km: near ? near.km : null, site: near ? near.site.i : null, inside: !!near && near.km <= km }; });
  const inside = each.filter((e) => e.inside).length;
  return { each, inside, outside: each.length - inside };
}

/* ------------------------------------------------------------------ a drawn area */

/** Rows (point features) inside a drawn polygon (GeoJSON Polygon feature or geometry). */
export function insidePolygon(fc, polygon) {
  return fc.features.filter((f) => booleanPointInPolygon(f.geometry.coordinates, polygon)).map((f) => f.properties._i);
}

/** Counts by a property's values (for the drawn-area and catchment summaries): [[value, n]] most first. */
export function countBy(idxs, read) {
  const m = new Map();
  for (const i of idxs) { const v = read(i); const k = v == null || v === '' ? null : String(v); m.set(k, (m.get(k) || 0) + 1); }
  return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

/** Sum of a numeric property over idxs, with how many had no value (never counted as 0). */
export function sumOf(idxs, read) {
  let sum = 0, n = 0, none = 0;
  for (const i of idxs) { const v = read(i); if (typeof v === 'number' && Number.isFinite(v)) { sum += v; n++; } else none++; }
  return { sum: n ? sum : null, n, none };
}
