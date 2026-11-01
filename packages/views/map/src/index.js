/* type: map — rows on a map, and the analyses a map answers (docs/VIEWS.md, Map; Bases' Maps plugin keys; data-ui's
   `layers:`, `space:`, `time:`, `multiples:`, `swipe:`, `draw:`, docs/CONTRACT.md §42).

   STOCK PARTS: MapLibre GL JS 6.16.0 (BSD-3-Clause), the engine Obsidian's own Maps plugin uses: WebGL pan and zoom,
   the navigation and scale controls, HTML markers, GeoJSON sources with clustering, and the circle, heatmap, fill,
   fill-extrusion, line and symbol layers every layer type here is drawn with. PMTiles 4.5.0 + @protomaps/basemaps
   5.7.2 (BSD-3-Clause) for a self-hosted OpenStreetMap basemap (`mapTiles:`); img-comparison-slider 8.0.7 (MIT,
   the compare view's slider) for the swipe; Terra Draw 1.37.0 (MIT) for drawing an area; Turf, h3-js and simple-statistics for the
   analysis (./analysis.js). OURS: rows -> layers (./plan.js), the legend panel, the time bar, the glue.
   BASEMAP: assets/countries-110m.json, Natural Earth 1:110m countries (public domain), always bundled; a view's
   `mapTiles:` (a .pmtiles file on the same site, relative to the .base file) draws OpenStreetMap streets, water and
   places over it, and where that file has no tiles the bundled countries still show. Nothing from another origin
   (docs/CONTRACT.md §1): the label font (Noto Sans, OFL) ships beside this bundle in map-glyphs/.
   Writes back only through the host: open(id) on a row, open(id, {records, title}) on a region, hexagon, cluster
   or drawn area (a dashboard turns that into its `select:`), setView for the within-distance slider, setStatus. With
   `select:` (docs/CONTRACT.md §39) a counted marker first asks which row, through MapLibre's Popup, and open(id) is the
   pick; the marks come back through selected(set). */

import * as maplibre from 'maplibre-gl';
import * as core from '@data-ui/core';
import mapCss from 'maplibre-gl/dist/maplibre-gl.css';
import ownCss from './map.css';
import countries from '../assets/countries-110m.json';
import { mapSpec, buildPlan, featureRows } from './plan.js';

const { AttributionControl, Map: MapLibre, Marker, NavigationControl, Popup, ScaleControl, setWorkerUrl, addProtocol } = maplibre;
const { cellValue, esc, hueOf, isEmpty, compileFilters, fmtNum, makeResizable } = core;

export const css = `${mapCss}\n${ownCss}`;

// WHY: MapLibre tiles GeoJSON in a worker it loads from a URL; the worker ships beside this bundle in dist/views/
setWorkerUrl(new URL('./maplibre-gl-worker.mjs', import.meta.url).href);

/* WHY a glyph protocol: labels and cluster counts need MapLibre's SDF glyphs, and only Latin ranges ship beside the
   bundle (map-glyphs/, Noto Sans Regular: 0-255, 256-511, 8192-8447). Any other range (a Chinese place name on the
   basemap) answers empty instead of a 404, so the text falls back to MapLibre's local CJK font or draws nothing, and
   the page logs no error. Every font stack maps to the one font. */
const GLYPHS = new URL('./map-glyphs/noto-sans-regular/', import.meta.url).href;
const SHIPPED = new Set(['0-255', '256-511', '8192-8447']);
let glyphsReady = false;
function glyphProtocol() {
  if (glyphsReady) return;
  glyphsReady = true;
  addProtocol('dvglyphs', async (params) => {
    const range = /([0-9]+-[0-9]+)(\.pbf)?$/.exec(params.url);
    if (!range || !SHIPPED.has(range[1])) return { data: new ArrayBuffer(0) };
    const r = await fetch(`${GLYPHS}${range[1]}.pbf`);
    return { data: r.ok ? await r.arrayBuffer() : new ArrayBuffer(0) };
  });
}

export function options() {
  return [
    { type: 'property', key: 'coordinates', displayName: 'Coordinates' },
    { type: 'property', key: 'markerColor', displayName: 'Marker colour', none: 'one colour' },
    { type: 'slider', key: 'defaultZoom', displayName: 'Zoom', min: 0, max: 12, step: 0.5 },
  ];
}

/** [lat, lng] from a cell: a [lat, lng] list or 'lat, lng' text; null when empty or out of range. */
export function latLng(cell) {
  let v = cellValue(cell);
  if (isEmpty(v)) return null;
  if (typeof v === 'string') v = v.split(',').map((x) => Number(x.trim()));
  if (!Array.isArray(v) || v.length !== 2) return null;
  const [lat, lng] = v.map(Number);
  return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? [lat, lng] : null;
}

function slotOf(columns, property, value) {
  const colors = columns[property] && columns[property].colors;
  if (colors && Object.prototype.hasOwnProperty.call(colors, String(value))) return colors[String(value)];
  return isEmpty(value) ? 0 : hueOf(value);
}

/** The row model -> {points: [{key, lat, lng, rows, colour}], missing, whys: Map(reason -> rows)}. Rows at one point
    share a marker. */
export function toPoints(input) {
  const { rows, columns, view, tokens } = input;
  const colourBy = view.markerColor && columns[view.markerColor] ? view.markerColor : null;
  const fixed = !colourBy && view.markerColor ? resolveColour(view.markerColor, tokens) : tokens.series[0];
  const byKey = new Map();
  let missing = 0;
  const whys = new Map();
  for (const r of rows) {
    const at = view.coordinates ? latLng(r[view.coordinates]) : null;
    if (!at) {
      missing++;
      const cell = view.coordinates ? r[view.coordinates] : null;
      const why = (cell && typeof cell === 'object' && !Array.isArray(cell) && cell.why) || 'no coordinates';
      whys.set(why, (whys.get(why) || 0) + 1);
      continue;
    }
    const key = `${at[0].toFixed(4)},${at[1].toFixed(4)}`;
    if (!byKey.has(key)) byKey.set(key, { key, lat: at[0], lng: at[1], rows: [] });
    byKey.get(key).rows.push(r);
  }
  const points = [...byKey.values()];
  for (const p of points) {
    if (!colourBy) { p.colour = fixed; continue; }
    // a counted marker takes its most common value's colour
    const counts = new Map();
    for (const r of p.rows) { const v = cellValue(r[colourBy]); counts.set(v, (counts.get(v) || 0) + 1); }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
    const slot = slotOf(columns, colourBy, top);
    p.colour = slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted;
  }
  return { points, missing, whys };
}

/** One row's own marker colour, which a counted marker's is not (it takes its most common value's). */
function rowColour({ columns, view, tokens }, row, fallback) {
  if (!view.markerColor || !columns[view.markerColor]) return fallback;
  const slot = slotOf(columns, view.markerColor, cellValue(row[view.markerColor]));
  return slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted;
}

function resolveColour(text, tokens) {
  const m = /^var\(--(data-[a-z0-9-]+)\)$/.exec(String(text).trim());
  return m ? tokens.css[m[1]] || tokens.accent : String(text);
}

/** A data file's `attribution` (text, {text, url}, or a list of those) as the control's HTML. WHY on the data and not in the
    .base: the credit belongs to the rows, so every view of them carries it, however many .base files read the file. */
function creditHtml(attribution) {
  const one = (c) => (typeof c === 'string' ? { text: c } : c || {});
  return [].concat(attribution || []).map(one).filter((c) => c.text).map((c) => (/^https?:\/\//.test(c.url || '')
    ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.text)}</a>` : esc(c.text)));
}

/* WHY this exact string in the tiles' credit too: MapLibre drops an attribution that is a substring of another, so a map of
   OpenStreetMap rows over OpenStreetMap tiles credits it once. */
const OSM_CREDIT = creditHtml({ text: '© OpenStreetMap contributors', url: 'https://www.openstreetmap.org/copyright' })[0];

const credits = new WeakMap();   // a map's attribution control and what it says, kept across parking

/** The map's credit, always open. WHY `compact: false`: compact folds the text behind an (i) at the first drag, and OpenStreetMap
    must be credited on the map itself (docs/MAP-DATA.md); MapLibre's own docs say not to collapse what fits. */
function setCredit(map, html) {
  const key = html.join('\n');
  const had = credits.get(map);
  if (had && had.key === key) return;
  if (had) map.removeControl(had.control);
  const control = new AttributionControl({ compact: false, customAttribution: html });
  map.addControl(control, 'bottom-right');
  credits.set(map, { control, key });
}

/** The basemap: ocean, land and borders, coloured from tokens, plus the label font. No tiles are fetched. */
function style(tokens) {
  glyphProtocol();
  return {
    version: 8,
    glyphs: 'dvglyphs://{fontstack}/{range}',
    sources: { countries: { type: 'geojson', data: countries, attribution: 'Natural Earth' } },
    layers: [
      { id: 'ocean', type: 'background', paint: { 'background-color': tokens.subtle } },
      { id: 'land', type: 'fill', source: 'countries', paint: { 'fill-color': tokens.bg } },
      { id: 'borders', type: 'line', source: 'countries', paint: { 'line-color': tokens.border, 'line-width': 0.7 } },
    ],
  };
}

/* ------------------------------------------------------------------ parking: one map kept across view switches
   WHY: <data-views> destroys the view plugin and constructs a new one on every view switch (core's _render), and a
   new maplibregl.Map (WebGL context, style, the countries source tiled in the worker) cost 286-409 ms each time
   table -> map. So destroy() parks the map and its container here instead of map.remove(), and the next map view
   adopts it: moves the container into its own element, resize(), then update() recolours, re-frames and redraws the
   markers and layers from its own input, as on a fresh map.
   Bounded, so nothing leaks: at most `parking.max` maps wait (the oldest extra is removed), each is removed after
   `parking.ms` unused, and while parked it holds nothing on the page: its listeners on the document and window
   (MapLibre's drag tracking, blur, online) and its ResizeObserver are released, its markers (which call the old
   host) are gone, and its container is out of the document. `parking` is exported so a test can shorten the wait. */
export const parking = { max: 1, ms: 45000 };
// where a new map starts (and an adopted one is put back to): the whole world
const FRESH_CENTER = [0, 20];
const FRESH_ZOOM = 1;
const parked = [];

/** What a map holds outside its own container: [target, type, fn, options] for each document/window listener, or
    null when this MapLibre's internals are not the ones read here (then the map is removed, never parked). WHY
    internals: MapLibre has no public suspend; these are its own bindings in HandlerManager and Map (maplibre-gl
    6.16.0, pinned in manifest.json), released and restored exactly as it adds them. */
function pageBindings(map) {
  const h = map._handlers;
  if (!h || !Array.isArray(h._listeners) || !h._ownerDocument || !h._ownerWindow || typeof h.handleEvent !== 'function'
    || typeof h.handleWindowEvent !== 'function' || typeof map._onWindowOnline !== 'function' || !map._resizeObserver) return null;
  const outside = h._listeners.filter(([target]) => target === h._ownerDocument || target === h._ownerWindow)
    .map(([target, type, opts]) => [target, type, target === h._ownerDocument ? h.handleWindowEvent : h.handleEvent, opts]);
  return [...outside, [h._ownerWindow, 'online', map._onWindowOnline, false]];
}

function release(map, bindings) {
  for (const [target, type, fn, opts] of bindings) target.removeEventListener(type, fn, opts);
  map._resizeObserver.disconnect();
}

function restore(map, bindings) {
  for (const [target, type, fn, opts] of bindings) target.addEventListener(type, fn, opts);
  map._resizeObserver.observe(map.getContainer());
}

function drop(entry) {
  clearTimeout(entry.timer);
  const i = parked.indexOf(entry);
  if (i >= 0) parked.splice(i, 1);
  entry.map.remove();
}

function park(map, mount, ready) {
  const bindings = parking.max > 0 ? pageBindings(map) : null;
  if (!bindings) { map.remove(); mount.remove(); return; }
  release(map, bindings);
  mount.remove();
  const entry = { map, mount, ready, bindings, timer: 0 };
  entry.timer = setTimeout(() => drop(entry), parking.ms);
  parked.push(entry);
  while (parked.length > parking.max) drop(parked[0]);
}

function adopt() {
  const entry = parked.pop();
  if (!entry) return null;
  clearTimeout(entry.timer);
  return entry;
}

/* ------------------------------------------------------------------ lazily loaded parts (manifest split: true) */
const lazy = {};
const load = (name, fn) => (lazy[name] || (lazy[name] = fn()));
const H3 = () => load('h3', () => import('h3-js'));

/** A hatch for "no data" (never drawn as a value): diagonal lines in the muted token. */
function hatch(tokens) {
  const n = 8, data = new Uint8Array(n * n * 4);
  const [r, g, b] = (/(\d+)\D+(\d+)\D+(\d+)/.exec(tokens.muted) || [0, 128, 128, 128]).slice(1).map(Number);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const on = (x + y) % n < 1.5;
    data.set([r, g, b, on ? 170 : 26], (y * n + x) * 4);
  }
  return { width: n, height: n, data };
}

/** Paints a plan onto one MapLibre map and removes it again. Every source and layer it adds is `dvl-*`. */
class Painter {
  constructor(map, view, opts = {}) { this.map = map; this.view = view; this.layers = []; this.sources = []; this.handlers = []; this.callouts = []; this.opts = opts; this.sel = null; this.index = new Map(); this.marked = new Map(); this.overlays = []; }

  clear() {
    const map = this.map;
    for (const [type, layer, fn] of this.handlers) if (layer) map.off(type, layer, fn); else map.off(type, fn);
    this.handlers = [];
    for (const id of this.layers) if (map.getLayer(id)) map.removeLayer(id);
    for (const id of this.sources) if (map.getSource(id)) map.removeSource(id);
    for (const c of this.callouts) c.marker.remove();
    this.layers = []; this.sources = []; this.callouts = []; this.sel = null; this.index = new Map(); this.marked = new Map(); this.overlays = [];
  }

  paint(plan, tokens) {
    const map = this.map;
    this.clear();
    if (map.hasImage('dv-hatch')) map.updateImage('dv-hatch', hatch(tokens)); else map.addImage('dv-hatch', hatch(tokens));
    for (const s of plan.sources) {
      const { id, data, ...rest } = s;
      map.addSource(id, { type: 'geojson', data, ...rest });
      this.sources.push(id);
    }
    for (const l of plan.layers) {
      const spec = { ...l };
      if (spec.filter === true || spec.filter == null) delete spec.filter;
      map.addLayer(spec);
      this.layers.push(spec.id);
    }
    // WHY one handler, not one per layer: MapLibre fires every layer's click under the pointer, so a hospital dot over
    // its catchment opened both; the top-most clickable feature is the one the reader pointed at
    const rule = new Map();
    for (const c of plan.clicks) for (const layer of [c.layer, ...(c.also || [])]) rule.set(layer, c);
    if (rule.size) {
      const ids = [...rule.keys()];
      const fn = (e) => {
        const f = map.queryRenderedFeatures(e.point, { layers: ids.filter((id) => map.getLayer(id)) })[0];
        if (f) this.view._clicked(this, rule.get(f.layer.id), { features: [f], originalEvent: e.originalEvent });
      };
      const hover = (e) => { map.getCanvas().style.cursor = map.queryRenderedFeatures(e.point, { layers: ids.filter((id) => map.getLayer(id)) }).length ? 'pointer' : ''; };
      map.on('click', fn);
      map.on('mousemove', hover);
      this.handlers.push(['click', null, fn], ['mousemove', null, hover]);
    }
    for (const c of plan.callouts || []) this.callouts.push(this.view._callout(c, map));
    // row index -> the features it stands behind, so a pick reaches them without walking every feature
    this.overlays = plan.overlays || [];
    const over = new Map(this.overlays.map((o) => [o.source, o.mark]));
    for (const s of plan.sources) for (const f of (s.data && s.data.features) || []) {
      if (f.id == null) continue;
      for (const i of featureRows(f.properties)) {
        if (!this.index.has(i)) this.index.set(i, []);
        this.index.get(i).push({ source: s.id, feature: f, mark: over.get(s.id) });
      }
    }
  }

  /** The click's own highlight, on a view that does not pick: a feature wears `sel` for it or for a mark, so neither
      takes the other's away. */
  select(source, id) {
    const was = this.sel;
    this.sel = source != null && id != null ? { source, id } : null;
    if (was && !this.marked.has(`${was.source}\n${was.id}`)) this.map.setFeatureState(was, { sel: false });
    if (this.sel) this.map.setFeatureState(this.sel, { sel: true });
  }

  /** The picked rows, as indexes: each feature behind one wears `sel` (the paint reads it, a pure style change, so no
      source redraws), a row a density layer hides stands on its mark layer, and a callout says so. */
  mark(on) {
    const next = new Map(), hidden = new Map(this.overlays.map((o) => [o.mark, []]));
    for (const i of on) for (const t of this.index.get(i) || []) {
      if (t.mark) hidden.get(t.mark).push(t.feature);
      else next.set(`${t.source}\n${t.feature.id}`, { source: t.source, id: t.feature.id });
    }
    for (const [key, f] of this.marked) if (!next.has(key) && !(this.sel && this.sel.source === f.source && this.sel.id === f.id)) this.map.setFeatureState(f, { sel: false });
    for (const [key, f] of next) if (!this.marked.has(key)) this.map.setFeatureState(f, { sel: true });
    this.marked = next;
    for (const [mark, features] of hidden) {
      const src = this.map.getSource(mark);
      if (!src) continue;
      // a feature once: a heatmap and its points share one source
      src.setData({ type: 'FeatureCollection', features: [...new Set(features)] });
    }
    const picks = this.view.input && this.view.input.view.select;
    for (const c of this.callouts) {
      if (c.i == null) continue;
      c.button.classList.toggle('dv-sel', on.has(c.i));
      if (picks) c.button.setAttribute('aria-pressed', String(on.has(c.i)));
    }
  }

  filterTime(plan, t, trail) {
    for (const id of plan.timed) {
      if (!this.map.getLayer(id)) continue;
      const f = ['all', ['!=', ['get', '_t'], null], ['<=', ['get', '_t'], t]];
      if (trail) f.push(['>=', ['get', '_t'], t - trail]);
      this.map.setFilter(id, f);
    }
  }
}

function frameOf(map, plan, view, el) {
  const center = Array.isArray(view.center) ? view.center : typeof view.center === 'string' ? view.center.split(',').map(Number) : null;
  if (center && center.length === 2 && center.every(Number.isFinite)) {
    map.jumpTo({ center: view.space === 'local' ? [center[0] / 111320, center[1] / 111320] : [center[1], center[0]], zoom: view.defaultZoom ?? 2 });
  } else if (plan.bounds) {
    const [w, s, e, n] = plan.bounds;
    const pad = Math.min(48, Math.round(el.clientWidth / 10));
    const maxZoom = view.defaultZoom ?? (view.space === 'local' ? 22 : 12);
    if (w === e && s === n) map.jumpTo({ center: [w, s], zoom: Math.min(maxZoom, 10) });
    else map.fitBounds([[w, s], [e, n]], { padding: pad, maxZoom, duration: 0 });
  }
}

export default class MapView {
  constructor(host, el) {
    this.host = host;
    this.el = el;
    this.map = null;
    this.markers = [];
    this.peekId = null;
    this._sel = new Set();
    this._chooser = null;
    this._fitKey = null;
    this._adopted = false;
    this.state = { hidden: new Set(), withinKm: null, t: null, playing: false, drawn: null };
    this.geo = new Map();   // geometry files: url -> GeoJSON | Promise | null (failed)
    this.extra = [];        // small-multiple and swipe maps: {map, painter, mount}
    this.stage = document.createElement('div');
    this.stage.className = 'dv-map-stage';
    el.append(this.stage);
    const kept = adopt();
    if (kept) {
      this.mount = kept.mount;
      this.map = kept.map;
      this._ready = kept.ready;
      this._adopted = true;
      this.stage.append(this.mount);
      restore(this.map, kept.bindings);
    } else {
      this.mount = document.createElement('div');
      this.mount.className = 'dv-map-mount';
      this.stage.append(this.mount);
    }
  }

  destroy() {
    this.host.setStatus('');
    this._closeChooser();
    this._stop();
    if (this._clockOff) this._clockOff();
    // WHY markers first: each one's click calls this view's host; a parked map must never open a record in a
    // destroyed view
    for (const { marker } of this.markers) marker.remove();
    this.markers = [];
    if (this.painter) this.painter.clear();
    this.painter = null;
    this._dropExtra();
    if (this.draw) { try { this.draw.stop(); } catch { /* already stopped */ } this.draw = null; }
    if (this.resizer) this.resizer.destroy();
    if (this.map) {
      // a parked map keeps the basemap and countries; this view's own tiles source goes with it
      for (const id of this._basemapIds || []) if (this.map.getLayer(id)) this.map.removeLayer(id);
      if (this.map.getSource('dvb')) this.map.removeSource('dvb');
      for (const id of ['ocean', 'land', 'borders']) if (this.map.getLayer(id)) this.map.setLayoutProperty(id, 'visibility', 'visible');
      park(this.map, this.mount, this._ready);
    }
    this.map = null;
    this.el.dvMap = null;
  }

  peeked(peek) {
    this.peekId = peek ? String(peek.id) : null;
    for (const { el, ids } of this.markers) el.classList.toggle('dv-active', this.peekId !== null && ids.includes(this.peekId));
  }

  /** The rows to mark changed (the element's selection and a host's picks, CONTRACT §39): repaint, no redraw. */
  selected(set) {
    this._sel = set || new Set();
    this._paintSel();
  }

  _paintSel() {
    for (const { el, ids } of this.markers) {
      const on = ids.some((id) => this._sel.has(id));
      el.classList.toggle('dv-sel', on);
      // WHY only on a view that picks: with no select: a marker opens a record, so it is no toggle (it stays as it was)
      if (this.input.view.select) el.setAttribute('aria-pressed', String(on));
    }
    if (this._chooser) for (const b of this._chooser.rows) b.setAttribute('aria-pressed', String(this._sel.has(b.dataset.id)));
    const rows = this._marked();
    for (const p of [this.painter, ...this.extra.map((x) => x.painter)]) if (p) p.mark(rows);
    this._markLegend(rows);
  }

  /** The marks as indexes into the rows this view last drew, which every plan speaks in. */
  _marked() {
    const on = new Set();
    if (this._sel.size) (this.rows || []).forEach((r, i) => { if (this._sel.has(String(r.id))) on.add(i); });
    return on;
  }

  /** A legend entry that picks says so when all its rows are picked: a ring band has no feature of its own to mark. */
  _markLegend(on) {
    if (!this.panel || !this.plan) return;
    const picks = this.input.view.select;
    for (const node of this.panel.querySelectorAll('[data-rows]')) {
      const [gi, ri] = node.dataset.rows.split(':').map(Number);
      // a mark can arrive between a new plan and the panel drawn from it, which marks itself
      const entry = this.plan.legend[gi] && this.plan.legend[gi].rows && this.plan.legend[gi].rows[ri];
      if (!entry) continue;
      const idxs = entry.rows || [];
      const all = idxs.length > 0 && idxs.every((i) => on.has(i));
      node.classList.toggle('dv-sel', all);
      if (picks) node.setAttribute('aria-pressed', String(all));
    }
  }

  /* ---------------------------------------------------------------- helpers the plan reads cells through */
  _helpers(input, h3) {
    const { columns, tokens, view, dataset } = input;
    const isProperty = (p) => typeof p === 'string' && !!columns[p];
    const colourOf = (r, p) => {
      if (!r) return tokens.muted;
      const slot = slotOf(columns, p, cellValue(r[p]));
      return slot ? tokens.series[(slot - 1) % tokens.series.length] : tokens.muted;
    };
    const unit = (p) => (p && columns[p] && (columns[p].unitText || columns[p].unit)) || '';
    return {
      view, tokens, h3, state: this.state, titleProperty: dataset.titleProperty,
      value: (r, p) => (p ? cellValue(r[p]) : null),
      raw: (r, p) => (p ? cellValue(r[p]) : null),
      text: (r, p) => { const v = p ? cellValue(r[p]) : null; return v == null || v === '' ? null : Array.isArray(v) ? v.join(', ') : String(v); },
      cellText: (r, p) => { const v = cellValue(r[p]); return v == null ? '—' : typeof v === 'number' ? `${fmtNum(v, columns[p] && columns[p].decimals)}${unit(p) ? ` ${unit(p)}` : ''}` : String(v); },
      match: (expr) => { try { return compileFilters(expr); } catch { return () => false; } },
      isProperty, colourOf, unit,
      colour: (c) => (c ? resolveColour(c, tokens) : null),
      label: (p) => (p && columns[p] && columns[p].label) || p || '',
      fmt: (v, p) => (v == null ? '—' : fmtNum(v, p && columns[p] && columns[p].decimals != null ? columns[p].decimals : Math.abs(v) >= 100 || Number.isInteger(v) ? 0 : 1)),
      featureName: (f, L, list = input.rows) => {
        const rs = f.properties._rows || [];
        const t = rs.length && list[rs[0]] ? cellValue(list[rs[0]][L.labelProperty || dataset.titleProperty]) : null;
        return (L.label && f.properties[L.label]) ?? t ?? f.properties.name ?? f.properties[L.key || 'id'] ?? '—';
      },
      geometry: (file) => this._geometry(file, input),
      why: (rows, p, whys) => { for (const r of rows) { const c = p ? r[p] : null; if (latLng(c) || (Array.isArray(cellValue(c)) && view.space === 'local')) continue; const why = (c && typeof c === 'object' && !Array.isArray(c) && c.why) || 'no coordinates'; whys.set(why, (whys.get(why) || 0) + 1); } },
    };
  }

  /** A file named in the .base (geometry:, mapTiles:) as an absolute URL: relative to the .base file (this element's
      src, or its dashboard's), else to the data file. */
  _url(file, input) {
    const host = this.host.element;
    const dash = host && host.closest && host.closest('data-dashboard');
    const src = (host && host.getAttribute && host.getAttribute('src')) || (dash && dash.getAttribute('src'));
    const base = src ? new URL(src, location.href).href : (input.dataset.url || location.href);
    return new URL(file, base).href;
  }

  _geometry(file, input) {
    if (!file) return null;
    const url = this._url(file, input);
    const got = this.geo.get(url);
    if (got && !(got instanceof Promise)) return got;
    if (got === undefined) {
      const p = fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null).then((g) => {
        this.geo.set(url, g || null);
        if (this.input === input && this.map) this.update(this.input);
      });
      this.geo.set(url, p);
    }
    return null;
  }

  update(input) {
    this.input = input;
    this._sel = input.selected || new Set();
    const { view, tokens } = input;
    const spec = mapSpec(view);
    this.spec = spec;
    const local = spec.space === 'local';
    if (!this.map) {
      this.map = new MapLibre({
        container: this.mount, style: style(tokens), center: FRESH_CENTER, zoom: FRESH_ZOOM, minZoom: view.minZoom ?? 0, maxZoom: view.maxZoom ?? (local ? 24 : 16),
        attributionControl: false, dragRotate: false, pitchWithRotate: false, touchPitch: false, renderWorldCopies: false,
      });
      this.map.touchZoomRotate.disableRotation();
      this.map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
      this.map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left');
      this._ready = new Promise((resolve) => this.map.once('load', resolve));
    } else {
      if (this._adopted) {
        // an adopted map carries the last view's zoom limits, camera and old container size: take this view's, as a
        // fresh map would, then measure the new container before the frame fits the bounds to it
        this._adopted = false;
        this.map.setMinZoom(0);
        this.map.setMaxZoom(view.maxZoom ?? (local ? 24 : 16));
        this.map.setMinZoom(view.minZoom ?? 0);
        this.map.resize();
        this.map.jumpTo({ center: FRESH_CENTER, zoom: FRESH_ZOOM, bearing: 0, pitch: 0 });
        if (!this.map.getContainer().querySelector('.maplibregl-ctrl-scale')) this.map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left');
      } else {
        if (view.minZoom !== undefined) this.map.setMinZoom(view.minZoom);
        if (view.maxZoom !== undefined) this.map.setMaxZoom(view.maxZoom);
      }
    }
    this.el.classList.toggle('dv-dark', !!tokens.dark);
    this.el.classList.toggle('dv-map-local', local);
    setCredit(this.map, creditHtml(input.dataset.attribution));
    // the MapLibre instance on the view's own element: browser checks count rendered features and project points with it
    this.el.dvMap = this.map;
    const map = this.map;
    const needsH3 = spec.layers.some((l) => l.type === 'hexbin');
    const ready = Promise.all([this._ready, needsH3 ? H3() : null]).then(async ([, h3]) => {
      if (this.map !== map || this.input !== input) return; // destroyed or superseded before the style loaded
      this._recolour(tokens, local);
      await this._basemap(view, tokens, local);
      if (this.map !== map || this.input !== input) return;
      this._render(input, spec, h3);
    });
    return ready;
  }

  _recolour(tokens, local) {
    const map = this.map;
    const s = style(tokens).layers;
    map.setPaintProperty('ocean', 'background-color', local ? tokens.bg : s[0].paint['background-color']);
    map.setPaintProperty('land', 'fill-color', s[1].paint['fill-color']);
    map.setPaintProperty('borders', 'line-color', s[2].paint['line-color']);
    for (const id of ['land', 'borders']) map.setLayoutProperty(id, 'visibility', local ? 'none' : 'visible');
  }

  /** `mapTiles:` (a .pmtiles on this site): Protomaps' basemap layers, recoloured from tokens, over the bundled
      countries; `mapTilesDark:` in a dark theme when set. Any failure keeps the countries and says so. */
  async _basemap(view, tokens, local) {
    const map = this.map;
    const file = !local && (tokens.dark && view.mapTilesDark ? view.mapTilesDark : view.mapTiles);
    const key = file ? `${this._url(file, this.input)}|${tokens.dark ? 'dark' : 'light'}|${tokens.bg}` : null;
    if (key === this._basemapKey) return;
    for (const id of this._basemapIds || []) if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource('dvb')) map.removeSource('dvb');
    this._basemapIds = [];
    this._basemapKey = key;
    this._basemapNote = '';
    if (!file) return;
    try {
      const [{ Protocol, PMTiles }, basemaps] = await load('basemap', () => Promise.all([import('pmtiles'), import('@protomaps/basemaps')]));
      if (!lazy.protocol) { lazy.protocol = new Protocol(); addProtocol('pmtiles', lazy.protocol.tile); }
      const url = this._url(file, this.input);
      if (!lazy.archives) lazy.archives = new Set();
      if (!lazy.archives.has(url)) { lazy.protocol.add(new PMTiles(new RangeOrWhole(url))); lazy.archives.add(url); }
      await lazy.protocol.get(url).getHeader();
      if (this.map !== map) return;
      const flavor = { ...basemaps.namedFlavor(tokens.dark ? 'black' : 'grayscale') };
      // WHY tokens: the data is the figure and the basemap the ground; earth and water take the theme's own surfaces
      Object.assign(flavor, { background: tokens.subtle, earth: tokens.bg, water: tokens.subtle, boundaries: tokens.border, city_label: tokens.muted, city_label_halo: tokens.bg, subplace_label: tokens.muted, subplace_label_halo: tokens.bg, roads_label_minor: tokens.muted, roads_label_major: tokens.muted, roads_label_minor_halo: tokens.bg, roads_label_major_halo: tokens.bg, ocean_label: tokens.muted, state_label: tokens.muted, state_label_halo: tokens.bg, country_label: tokens.muted, address_label: tokens.muted, address_label_halo: tokens.bg });
      map.addSource('dvb', { type: 'vector', url: `pmtiles://${url}`, attribution: `<a href="https://protomaps.com">Protomaps</a> ${OSM_CREDIT}` });
      const before = map.getStyle().layers.find((l) => l.id.startsWith('dvl-'));
      for (const l of basemaps.layers('dvb', flavor, { lang: 'en' })) {
        // no sprite ships (POI icons), and the background would hide the bundled countries outside the extract
        if (l.type === 'background' || (l.layout && l.layout['icon-image'])) continue;
        const spec = { ...l, id: `dvb-${l.id}` };
        if (spec.layout && spec.layout['text-font']) spec.layout = { ...spec.layout, 'text-font': ['Noto Sans Regular'] };
        map.addLayer(spec, before && before.id);
        this._basemapIds.push(spec.id);
      }
    } catch (err) {
      this._basemapNote = `the basemap file could not be read (${esc(String(err.message || err))}): drawing the bundled Natural Earth countries`;
    }
  }

  /** A counted marker on a view that picks (`select:`, CONTRACT §39): its rows hold several values, so the reader says
      which. STOCK PART: MapLibre's Popup, which stands at the point, follows a pan and keeps inside the map. Each row goes
      through host.open, the path a single marker takes, so a dashboard picks, adds on ctrl / cmd and clears as for any
      click. WHY not the peek's list of these rows: a read-only table under one arbitrary row's fields, across the page
      from the point, and a pick needs the point's rows, not a record. */
  _choose(p, anchor, titleProp, byKeyboard) {
    const again = this._chooser && this._chooser.anchor === anchor;
    this._closeChooser();
    if (again) return;
    const box = document.createElement('div');
    box.className = 'dv-map-choose';
    box.tabIndex = -1;
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', `${p.rows.length} rows at this point: pick one`);
    const rows = p.rows.map((r) => {
      const name = String(cellValue(r[titleProp]) ?? r.id);
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'dv-map-choose-row';
      b.dataset.id = String(r.id);
      b.title = name;
      b.style.setProperty('--dv-pin', rowColour(this.input, r, p.colour));
      b.innerHTML = `<span class="dv-map-choose-dot" aria-hidden="true"></span><span class="dv-map-choose-name">${esc(name)}</span>`;
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!this.map) return;
        this.host.open(String(r.id));
        // WHY open on ctrl / cmd: a reader adding rows is not done, as in a table
        if (!e.ctrlKey && !e.metaKey) this._closeChooser(true);
      });
      return b;
    });
    box.append(...rows);
    box.addEventListener('keydown', (e) => {
      const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
      // WHY stopPropagation: these keys bubble to MapLibre's keyboard handler (it would pan), and Escape to the page's peek
      if (step) {
        e.preventDefault();
        e.stopPropagation();
        const at = rows.indexOf(document.activeElement);
        rows[at < 0 ? (step > 0 ? 0 : rows.length - 1) : (at + step + rows.length) % rows.length].focus();
      } else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this._closeChooser(true); }
    });
    const popup = new Popup({ closeButton: false, closeOnClick: true, focusAfterOpen: false, maxWidth: 'none', className: 'dv-map-chooser', offset: anchor.offsetWidth / 2 + 6 })
      .setLngLat([p.lng, p.lat]).setDOMContent(box).addTo(this.map);
    popup.on('close', () => {
      anchor.setAttribute('aria-expanded', 'false');
      if (this._chooser && this._chooser.popup === popup) this._chooser = null;
    });
    this._chooser = { popup, anchor, rows };
    anchor.setAttribute('aria-expanded', 'true');
    this._paintSel();
    // WHY the box after a click: a focused first row reads as already picked, and a click leaves focus nowhere (MapLibre
    // takes the mousedown), so the box holds it for Escape and the arrows
    (byKeyboard ? rows[0] : box).focus({ preventScroll: true });
  }

  _closeChooser(refocus = false) {
    const open = this._chooser;
    if (!open) return;
    open.popup.remove();
    if (refocus && open.anchor.isConnected) open.anchor.focus({ preventScroll: true });
  }

  _render(input, spec, h3) {
    const map = this.map;
    const h = this._helpers(input, h3);
    const plan = buildPlan(spec, input.rows, h);
    this.plan = plan;
    this.h = h;
    this.rows = input.rows;
    // the HTML markers (Bases' Maps behaviour) when the view has no layers or lists `type: markers`
    const m = plan.markers ? toPoints(input) : { points: [], missing: 0, whys: new Map() };
    this._drawMarkers(m.points, input.dataset.titleProperty);
    if (!this.painter) this.painter = new Painter(map, this);
    const main = spec.swipe ? buildPlan(spec, input.rows.filter(h.match(spec.swipe.left.filter)), h, plan.classes, input.rows) : plan;
    if (!spec.multiples) this.painter.paint(main, input.tokens);
    else this.painter.clear();
    this._hidden();
    this._extra(input, spec, h, plan);
    if (spec.time) this._timebar(input, spec, plan);
    else this._stop(true);
    if (spec.draw) this._drawTool(input, plan); else if (this.draw) { this.draw.stop(); this.draw = null; this._drawBar && this._drawBar.remove(); }
    const extrude = spec.layers.some((l) => l.extrude);
    if (extrude) { map.dragRotate.enable(); map.setMaxPitch(70); }
    // the legend first: it takes its width from the stage, and the frame below fits the bounds to what is left
    this._panel(input, spec, plan);
    if (spec.time && this._timeApply && this.state.t != null) this._timeApply(this.state.t);
    map.resize();
    // WHY a key: a new view or coordinate property re-frames the map; a filter or theme change keeps where you are
    const key = JSON.stringify([input.view.name, input.view.coordinates, input.view.center, input.view.defaultZoom, spec.space, plan.bounds ? 1 : 0, (input.view.layers || []).map((l) => l.geometry)]);
    if (key !== this._fitKey && (plan.bounds || m.points.length)) {
      if (!plan.bounds && m.points.length) plan.bounds = m.points.reduce((b, p) => [Math.min(b[0], p.lng), Math.min(b[1], p.lat), Math.max(b[2], p.lng), Math.max(b[3], p.lat)], [Infinity, Infinity, -Infinity, -Infinity]);
      else if (m.points.length) for (const p of m.points) { plan.bounds[0] = Math.min(plan.bounds[0], p.lng); plan.bounds[1] = Math.min(plan.bounds[1], p.lat); plan.bounds[2] = Math.max(plan.bounds[2], p.lng); plan.bounds[3] = Math.max(plan.bounds[3], p.lat); }
      frameOf(map, plan, { ...input.view, space: spec.space }, this.el);
      if (extrude) map.easeTo({ pitch: input.view.pitch ?? 50, duration: 0 });
      for (const x of this.extra) x.map.jumpTo({ center: map.getCenter(), zoom: map.getZoom(), pitch: map.getPitch() });
      this._fitKey = key;
    }
    // the camera, readable from outside (browser checks measure it; a host may show it)
    const cam = () => { if (this.map !== map) return; this.el.dataset.zoom = map.getZoom().toFixed(2); this.el.dataset.pitch = map.getPitch().toFixed(0); };
    cam();
    if (!this._camBound) { this._camBound = true; map.on('moveend', cam); }
    if (spec.swipe || spec.multiples) {
      // the "several rows per region" note is about the whole view's rows; each panel or side has one row per region
      for (const g of plan.legend) if (g.note) g.note = g.note.replace(/\d+ regions have several rows[^)]*\)\.\s*/, '').trim() || undefined;
      this._panel(input, spec, plan);
    }
    this._status(input, spec, plan, m);
    // WHY here too: painting replaced the sources, and feature-state goes with them
    this._paintSel();
  }

  /** Frame the map on marker points ({lng, lat}): the view's center/defaultZoom, else their bounds. Kept as the
      markers' framing (tests/browser/lifecycle_checks.py calls it on 150,000 points). */
  _frame(view, points) {
    if (!points.length) return frameOf(this.map, { bounds: null }, view, this.el);
    // WHY a fold, not Math.min(...lngs): spreading 150,000 points into one call overflows the stack (2026-10-26 review)
    const b = points.reduce((a, p) => [Math.min(a[0], p.lng), Math.min(a[1], p.lat), Math.max(a[2], p.lng), Math.max(a[3], p.lat)], [Infinity, Infinity, -Infinity, -Infinity]);
    frameOf(this.map, { bounds: b }, { ...view, defaultZoom: view.defaultZoom ?? 4 }, this.el);
  }

  _status(input, spec, plan, m) {
    const { view } = input;
    const parts = [];
    const missing = plan.markers ? m.missing : plan.missing;
    const whys = plan.markers ? m.whys : plan.whys;
    const anyPoints = plan.markers || spec.layers.some((l) => ['points', 'heatmap', 'hexbin'].includes(l.type) && !l.filter);
    if (plan.markers) parts.push(`${m.points.reduce((n, p) => n + p.rows.length, 0)} on the map at ${m.points.length} points`);
    else parts.push(`${input.rows.length.toLocaleString('en-US')} rows · ${spec.layers.map((l) => l.type).join(', ')}`);
    if (anyPoints && !view.coordinates && !spec.layers.some((l) => l.coordinates)) parts.push('<span class="dv-err">set <code>coordinates:</code>, the property holding [lat, lng]</span>');
    else if (missing) {
      // one reason is said; several are listed on hover, so no single row's reason stands for all of them
      const reasons = [...whys.entries()].sort((a, b) => b[1] - a[1]);
      const hover = reasons.map(([w, n]) => `${n}: ${w}`).join('\n');
      parts.push(`<span title="${esc(hover)}">${missing} without coordinates${reasons.length === 1 ? ` (${esc(reasons[0][0])})` : ` (${reasons.length} reasons)`}</span>`);
    }
    for (const n of plan.notes) parts.push(`<span class="dv-err">${esc(n)}</span>`);
    if (spec.unknown.length) parts.push(`<span class="dv-err">unknown layer type: ${esc(spec.unknown.join(', '))}</span>`);
    if (this._basemapNote) parts.push(this._basemapNote);
    this.host.setStatus(parts.join(' · '));
  }

  /* ---------------------------------------------------------------- clicks */
  _clicked(painter, c, e) {
    const f = e.features && e.features[0];
    if (!f || !this.map) return;
    e.originalEvent && e.originalEvent.stopPropagation && e.originalEvent.stopPropagation();
    const rows = this.input.rows;
    const tp = this.input.dataset.titleProperty;
    if (c.cluster) {
      const src = painter.map.getSource(c.cluster);
      Promise.resolve(src.getClusterExpansionZoom(f.properties.cluster_id)).then((z) => painter.map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.2 }));
      return;
    }
    if (c.points) {
      const r = rows[f.properties._i];
      if (r) this.host.open(String(r.id));
      return;
    }
    const idxs = Array.isArray(f.properties._rows) ? f.properties._rows : JSON.parse(f.properties._rows || '[]');
    // WHY not on a view that picks: the marks come back through selected(set), which also clears them; a highlight kept here
    // outlived the pick it stood for
    if (!this.input.view.select) painter.select(f.source, f.id);
    if (!idxs.length) return;
    const recs = idxs.map((i) => rows[i]).filter(Boolean);
    const name = c.name ? c.name(this.painter && painter === this.painter ? f : f) : 'This area';
    const title = recs.length === 1 ? String(cellValue(recs[0][tp]) ?? recs[0].id) : `${name} · ${recs.length} rows`;
    if (recs.length === 1) this.host.open(String(recs[0].id));
    else this.host.open(String(recs[0].id), { records: recs, title });
  }

  _callout(c, map) {
    const el = document.createElement('div');
    el.className = `dv-map-callout${c.note ? ' dv-map-note' : ''}`;
    const dx = c.dx || 0, dy = c.dy || -36;
    el.style.setProperty('--dx', `${dx}px`);
    el.style.setProperty('--dy', `${dy}px`);
    const len = Math.hypot(dx, dy), ang = Math.atan2(dy, dx);
    el.innerHTML = `<span class="dv-map-leader" style="width:${len}px;transform:rotate(${ang}rad)"></span><span class="dv-map-dot"></span><button type="button" class="dv-map-bubble"><b>${esc(c.text ?? '')}</b>${c.detail ? `<span>${esc(c.detail)}</span>` : ''}</button>`;
    const button = el.querySelector('button');
    if (c.i != null) button.addEventListener('click', (e) => { e.stopPropagation(); const r = this.input.rows[c.i]; if (r && this.map) this.host.open(String(r.id)); });
    return { marker: new Marker({ element: el, anchor: 'top-left', offset: [0, 0] }).setLngLat(c.at).addTo(map), button, i: c.i };
  }

  /* ---------------------------------------------------------------- the legend panel (resizable, foldable) */
  _panel(input, spec, plan) {
    // WHY not on a plain marker map: it has nothing to say, and an empty side panel takes a quarter of the view
    const silent = !plan.legend.length && !plan.sections.length && spec.layers.length < 2 && !spec.draw;
    if (spec.legend === 'off' || silent) {
      if (this.resizer) { this.resizer.destroy(); this.resizer = null; }
      if (this.panel) { this.panel.remove(); this.panel = null; }
      return;
    }
    if (!this.panel) {
      this.panel = document.createElement('aside');
      this.panel.className = 'dv-map-panel';
      this.panel.setAttribute('aria-label', 'Map legend');
      this.el.append(this.panel);
      const hostId = (this.host.element && this.host.element.id) || 'map';
      try {
        this.resizer = makeResizable(this.panel, { edge: 'left', min: 200, max: 520, key: `map-panel:${hostId}`, label: 'Resize the map legend' });
      } catch { this.resizer = null; }
      if (spec.legend === 'closed') this.el.classList.add('dv-map-folded');
    }
    const T = input.tokens;
    const sw = (c) => `<i class="dv-map-sw" style="--sw:${esc(c)}"></i>`;
    const count = (n) => (n == null ? '' : `<span class="dv-map-n">${Number(n).toLocaleString('en-US')}</span>`);
    const sections = plan.legend.map((g, gi) => {
      const head = `<h4>${esc(g.title)}${g.unit ? ` <span class="dv-map-unit">(${esc(g.unit)})</span>` : ''}${g.derived ? ' <span class="dv-map-derived" title="computed by the map from the rows: derived">~ derived</span>' : ''}</h4>`;
      let body = '';
      if (g.kind === 'classes') body = `<ul class="dv-map-classes">${g.rows.map((r) => `<li>${sw(r.colour)}<span>${esc(r.label)}</span>${count(r.n)}</li>`).join('')}${g.none ? `<li class="dv-map-none">${sw('transparent')}<span>No data</span>${count(g.none)}</li>` : ''}</ul><p class="dv-map-method">${esc(g.method)}</p>`;
      else if (g.kind === 'bands') body = `<table class="dv-map-bands"><tbody>${g.rows.map((r, i) => `<tr data-band="${i}" data-rows="${gi}:${i}" tabindex="0" role="button"><td>${sw(r.colour)}${esc(r.label)}</td><td>${count(r.n)}</td><td class="dv-map-cum">${r.cum != null ? `${r.cum.toLocaleString('en-US')} in all` : ''}</td></tr>`).join('')}</tbody></table>`;
      else if (g.kind === 'ramp') body = `<div class="dv-map-ramp" style="background:linear-gradient(90deg, ${g.ramp.join(', ')})"></div><div class="dv-map-ramp-ends"><span>${esc(g.from)}</span><span>${esc(g.to)}</span></div>`;
      else if (g.kind === 'bivariate') {
        const cells = [];
        for (let y = g.n - 1; y >= 0; y--) for (let x = 0; x < g.n; x++) cells.push(`<i style="background:${g.grid[y][x]}" title="${esc(g.x.label)} class ${x + 1}, ${esc(g.y.label)} class ${y + 1}"></i>`);
        body = `<div class="dv-map-bi"><span class="dv-map-bi-y">${esc(g.y.label)}${g.y.unit ? ` (${esc(g.y.unit)})` : ''} →</span><div class="dv-map-bi-grid" style="--n:${g.n}">${cells.join('')}</div><span class="dv-map-bi-x">${esc(g.x.label)}${g.x.unit ? ` (${esc(g.x.unit)})` : ''} →</span></div><p class="dv-map-method">${esc(g.method)}; breaks ${esc(g.x.label)}: ${esc(g.x.breaks.join(', '))}; ${esc(g.y.label)}: ${esc(g.y.breaks.join(', '))}${g.none ? ` · ${g.none} with no data (hatched)` : ''}</p>`;
      } else body = `<ul class="dv-map-classes">${(g.rows || []).map((r, i) => `<li${r.rows ? ` data-rows="${gi}:${i}" class="dv-map-pick" tabindex="0" role="button"` : ''}>${sw(r.colour)}<span>${esc(r.label)}</span>${count(r.n)}</li>`).join('')}</ul>`;
      if (g.size) body += `<div class="dv-map-size"><svg width="${g.size.max * 2 + 4}" height="${g.size.max * 2 + 4}" aria-hidden="true">${g.kind === 'flows' ? `<line x1="2" x2="${g.size.max * 2}" y1="${g.size.max}" y2="${g.size.max}" stroke="${T.fg}" stroke-width="${g.size.max}" stroke-opacity=".5"/>` : `<circle cx="${g.size.radius + 2}" cy="${g.size.radius + 2}" r="${g.size.radius}" fill="none" stroke="${T.fg}"/><circle cx="${g.size.radius + 2}" cy="${g.size.radius * 1.5 + 2}" r="${g.size.radius / 2}" fill="none" stroke="${T.fg}"/>`}</svg><span>${esc(g.size.property)}: largest ${esc(g.size.maxText)}${g.size.unit ? ` ${esc(g.size.unit)}` : ''} · ${esc(g.size.rule)}</span></div>`;
      if (g.note) body += `<p class="dv-map-note-text">${esc(g.note)}</p>`;
      return `<section>${head}${body}</section>`;
    });
    const within = plan.sections.find((s) => s.kind === 'within');
    const withinUi = within ? `<label class="dv-map-within">Within <output>${within.km}</output> km <input type="range" min="${within.min}" max="${within.max}" step="${within.step}" value="${within.km}" aria-label="Distance in km"></label>` : '';
    const drawn = this.state.drawn ? this._drawnHtml(input, plan) : '';
    const layers = spec.layers.length > 1 ? `<details class="dv-map-layers"><summary>Layers</summary>${spec.layers.map((l, i) => `<label><input type="checkbox" data-layer="${i}"${this.state.hidden.has(i) ? '' : ' checked'}> ${esc(l.title || l.type)}</label>`).join('')}</details>` : '';
    this.panel.innerHTML = `<div class="dv-map-panel-head"><p class="dv-map-answer">${esc(plan.answer || (input.view.name ?? 'Map'))}</p><button type="button" class="dv-map-fold" aria-label="Fold the legend" title="Fold the legend">›</button></div>${withinUi}${drawn}${sections.join('')}${layers}`;
    this.panel.querySelector('.dv-map-fold').addEventListener('click', () => { this.el.classList.add('dv-map-folded'); this.map && this.map.resize(); });
    if (!this.unfold) {
      this.unfold = document.createElement('button');
      this.unfold.type = 'button';
      this.unfold.className = 'dv-map-unfold';
      this.unfold.textContent = 'Legend';
      this.unfold.addEventListener('click', () => { this.el.classList.remove('dv-map-folded'); this.map && this.map.resize(); });
      this.stage.append(this.unfold);
    }
    for (const cb of this.panel.querySelectorAll('input[data-layer]')) cb.addEventListener('change', () => { const i = Number(cb.dataset.layer); if (cb.checked) this.state.hidden.delete(i); else this.state.hidden.add(i); this._hidden(); });
    const range = this.panel.querySelector('.dv-map-within input');
    if (range) {
      range.addEventListener('input', () => { range.previousElementSibling.textContent = range.value; });
      range.addEventListener('change', () => {
        this.state.withinKm = Number(range.value);
        // WHY setView: the distance is part of the view, so it rides in the URL and Save view like any other key
        const layers = (input.view.layers || []).map((l) => (l.type === 'within' ? { ...l, km: Number(range.value) } : l));
        this.host.setView({ layers });
      });
    }
    for (const li of this.panel.querySelectorAll('[data-rows]')) {
      const go = () => {
        const [gi, ri] = li.dataset.rows.split(':').map(Number);
        const idxs = plan.legend[gi].rows[ri].rows || [];
        const recs = idxs.map((i) => input.rows[i]).filter(Boolean);
        if (recs.length) this.host.open(String(recs[0].id), { records: recs, title: `${plan.legend[gi].rows[ri].label} · ${recs.length} rows` });
      };
      li.addEventListener('click', go);
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    }
    const open = this.panel.querySelector('.dv-map-drawn-open');
    if (open) open.addEventListener('click', () => { const recs = this.state.drawn.map((i) => input.rows[i]).filter(Boolean); if (recs.length) this.host.open(String(recs[0].id), { records: recs, title: `Drawn area · ${recs.length} rows` }); });
    this._markLegend(this._marked());
  }

  _hidden() {
    if (!this.painter || !this.plan) return;
    for (const p of [this.painter, ...this.extra.map((x) => x.painter)]) {
      for (const id of p.layers) {
        const li = Number(/^dvl-(\d+)/.exec(id)[1]);
        if (p.map.getLayer(id)) p.map.setLayoutProperty(id, 'visibility', this.state.hidden.has(li) ? 'none' : 'visible');
      }
    }
  }

  /* ---------------------------------------------------------------- small multiples and swipe: extra maps */
  _dropExtra() {
    for (const [m, fn] of this._swipeOff || []) m.off('move', fn);
    this._swipeOff = null;
    // the main map's mount goes back to the stage before a swipe's slider (which holds it) is removed
    if (this.mount.parentElement !== this.stage) this.stage.prepend(this.mount);
    for (const el of this.stage.querySelectorAll('.dv-map-side')) el.remove();
    for (const x of this.extra) { x.painter.clear(); x.map.remove(); x.mount.remove(); }
    this.extra = [];
    if (this.grid) { this.grid.remove(); this.grid = null; }
    this.mount.hidden = false;
  }

  _newMap(mount, input) {
    const map = new MapLibre({ container: mount, style: style(input.tokens), center: this.map.getCenter(), zoom: this.map.getZoom(), attributionControl: false, dragRotate: false, renderWorldCopies: false, maxZoom: this.map.getMaxZoom() });
    map.touchZoomRotate.disableRotation();
    // WHY only with a credit to give: the main map is hidden behind small multiples and clipped by a swipe, so a data file's
    // credit must be on these too; Natural Earth needs none
    const credit = creditHtml(input.dataset.attribution);
    if (credit.length) setCredit(map, credit);
    return map;
  }

  _extra(input, spec, h, plan) {
    const want = spec.multiples ? `m|${spec.multiples.by}` : spec.swipe ? 'swipe' : '';
    if (this._extraKind !== want) { this._dropExtra(); this._extraKind = want; }
    if (!want) return;
    if (spec.swipe) {
      const rightRows = input.rows.filter(h.match(spec.swipe.right.filter));
      const rightPlan = buildPlan(spec, rightRows, h, plan.classes, input.rows);
      const leftPlan = buildPlan(spec, input.rows.filter(h.match(spec.swipe.left.filter)), h, plan.classes, input.rows);
      // the headline of a swipe is each side's own answer, never one computed over both sides' rows
      plan.answer = [[spec.swipe.left, leftPlan], [spec.swipe.right, rightPlan]].map(([side, sp]) => `${side.label || side.filter}: ${sp.answer || '—'}`).join(' · ');
      if (!this.extra.length) {
        // STOCK: img-comparison-slider 8.0.7 (the compare view's slider): the left map in slot "first", the right one
        // in slot "second", clipped at the divider; `handle` makes only the divider drag, so both maps still pan and
        // zoom, and each move is copied to the other (one camera, two times).
        const slider = document.createElement('img-comparison-slider');
        slider.className = 'dv-map-swipe';
        slider.setAttribute('handle', '');
        slider.setAttribute('value', '50');
        const first = document.createElement('div');
        first.slot = 'first';
        first.className = 'dv-map-swipe-side';
        const second = document.createElement('div');
        second.slot = 'second';
        second.className = 'dv-map-swipe-side';
        const mount = document.createElement('div');
        mount.className = 'dv-map-mount dv-map-after';
        second.append(mount);
        this.stage.append(slider);
        slider.append(first, second);
        first.append(this.mount);
        this.map.resize();
        const map = this._newMap(mount, input);
        mount.dvMap = map;
        const x = { map, mount: slider, painter: new Painter(map, this), ready: new Promise((r) => map.once('load', r)), swipe: true };
        this.extra.push(x);
        const follow = (from, to) => (e) => { if (e.originalEvent) to.jumpTo({ center: from.getCenter(), zoom: from.getZoom(), pitch: from.getPitch(), bearing: from.getBearing() }); };
        this._swipeOff = [[this.map, follow(this.map, map)], [map, follow(map, this.map)]];
        for (const [m, fn] of this._swipeOff) m.on('move', fn);
        this._labels(spec);
        load('slider', () => import('img-comparison-slider')).then(() => {
          // WHY into its shadow root: the slider clips its first side with a child's clip-path and leaves two full-size parents
          // over the second side, so right of the divider nothing reached the right map: no pan, no click. No part or
          // custom property reaches them (8.0.7, pinned in manifest.json). They let hits through; the map and the handle take them
          const sheet = new CSSStyleSheet();
          sheet.replaceSync('.first, .first-overlay { pointer-events: none; } .first-overlay-container, .handle { pointer-events: auto; }');
          if (slider.shadowRoot) slider.shadowRoot.adoptedStyleSheets = [...slider.shadowRoot.adoptedStyleSheets, sheet];
          requestAnimationFrame(() => { if (this.map) this.map.resize(); map.resize(); });
        });
      }
      const x = this.extra[0];
      x.ready.then(() => { if (!this.extra.includes(x)) return; this._recolourOn(x.map, input.tokens); x.painter.paint(rightPlan, input.tokens); x.painter.mark(this._marked()); x.map.resize(); x.map.jumpTo({ center: this.map.getCenter(), zoom: this.map.getZoom() }); });
      return;
    }
    // small multiples: one map per value of `by`, every one against the same classes
    const by = spec.multiples.by;
    const values = [...new Set(input.rows.map((r) => h.text(r, by)).filter((v) => v != null))].sort((a, b) => (Number(a) - Number(b)) || String(a).localeCompare(String(b)));
    const shown = spec.multiples.values ? spec.multiples.values.map(String).filter((v) => values.includes(v)) : values.slice(0, spec.multiples.limit || 9);
    this.mount.hidden = true;
    if (!this.grid || this._gridKey !== shown.join('|')) {
      for (const x of this.extra) { x.painter.clear(); x.map.remove(); x.mount.remove(); }
      this.extra = [];
      if (this.grid) this.grid.remove();
      this.grid = document.createElement('div');
      this.grid.className = 'dv-map-grid';
      this.grid.style.setProperty('--cols', spec.multiples.columns || Math.ceil(Math.sqrt(shown.length)));
      this.stage.append(this.grid);
      this._gridKey = shown.join('|');
      for (const v of shown) {
        const cell = document.createElement('figure');
        cell.className = 'dv-map-cell';
        cell.innerHTML = `<figcaption>${esc(h.label(by))}: ${esc(v)}</figcaption>`;
        const mount = document.createElement('div');
        mount.className = 'dv-map-cell-mount';
        cell.append(mount);
        this.grid.append(cell);
        const map = this._newMap(mount, input);
        cell.dvMap = map;
        const x = { map, mount: cell, value: v, painter: new Painter(map, this), ready: new Promise((r) => map.once('load', r)) };
        // one camera for all: moving one moves the rest (Tufte's small multiples read only when they share a frame)
        map.on('move', (e) => { if (!e.originalEvent) return; for (const o of this.extra) if (o !== x) o.map.jumpTo({ center: map.getCenter(), zoom: map.getZoom() }); });
        this.extra.push(x);
      }
    }
    const answers = [];
    for (const x of this.extra) {
      const sub = input.rows.filter((r) => h.text(r, by) === x.value);
      const p = buildPlan(spec, sub, h, plan.classes, input.rows);
      answers.push([x.value, p.answer]);
      x.ready.then(() => {
        if (!this.extra.includes(x)) return;
        this._recolourOn(x.map, input.tokens);
        x.painter.paint(p, input.tokens);
        x.painter.mark(this._marked());
        x.map.resize();
        if (plan.bounds) frameOf(x.map, plan, { ...input.view, space: spec.space }, x.mount);
      });
    }
    // the headline of small multiples is the last panel's answer, said with its value (one panel, not all at once)
    const last = answers[answers.length - 1];
    if (last && last[1]) plan.answer = `${h.label(by)} ${last[0]}: ${last[1]}`;
  }

  _recolourOn(map, tokens) {
    const s = style(tokens).layers;
    map.setPaintProperty('ocean', 'background-color', s[0].paint['background-color']);
    map.setPaintProperty('land', 'fill-color', s[1].paint['fill-color']);
    map.setPaintProperty('borders', 'line-color', s[2].paint['line-color']);
  }

  _labels(spec) {
    for (const [side, cls] of [['left', 'dv-map-side-l'], ['right', 'dv-map-side-r']]) {
      let el = this.stage.querySelector(`.${cls}`);
      if (!el) { el = document.createElement('span'); el.className = `dv-map-side ${cls}`; this.stage.append(el); }
      el.textContent = spec.swipe[side].label || spec.swipe[side].filter;
    }
  }

  /* ---------------------------------------------------------------- time: a play bar, or the page's clock */
  _stop(remove) {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = 0;
    this.state.playing = false;
    // WHY the bar's closure goes with it: a clock's tick would write to the bar it no longer has
    if (remove && this.timebar) { this.timebar.remove(); this.timebar = null; this._timeApply = null; }
  }

  _timebar(input, spec, plan) {
    const ts = [];
    for (const s of plan.sources) for (const f of (s.data && s.data.features) || []) if (f.properties && f.properties._t != null) ts.push(f.properties._t);
    if (!ts.length) { this._stop(true); return; }
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const trail = spec.time.trail ? Number(spec.time.trail) * 1000 : 0;
    const speed = Number(spec.time.speed) || (t1 - t0) / 12000; // default: the whole span in 12 s
    if (this.state.t == null || this.state.t < t0 || this.state.t > t1) this.state.t = t1;
    const fmt = (t) => { const d = new Date(t); return spec.time.format === 'date' ? d.toISOString().slice(0, 10) : d.toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: spec.time.zone || undefined }); };
    if (!this.timebar) {
      this.timebar = document.createElement('div');
      this.timebar.className = 'dv-map-time';
      this.timebar.innerHTML = `<button type="button" class="dv-map-play" aria-label="Play">▶</button><input type="range" aria-label="Time"><output></output>`;
      this.stage.append(this.timebar);
    }
    const [btn, range, out] = this.timebar.children;
    range.min = String(t0); range.max = String(t1); range.step = String(Math.max(1, (t1 - t0) / 1000));
    const says = (playing) => { btn.textContent = playing ? '❚❚' : '▶'; btn.setAttribute('aria-label', playing ? 'Pause' : 'Play'); };
    const apply = (t, fromClock) => {
      this.state.t = t;
      range.value = String(t);
      out.textContent = fmt(t);
      const shown = ts.filter((x) => x <= t && (!trail || x >= t - trail)).length;
      out.title = `${shown} of ${ts.length} rows up to this time`;
      this.timebar.dataset.shown = String(shown);
      const ans = this.panel && this.panel.querySelector('.dv-map-answer');
      if (ans) ans.textContent = `${shown} of ${ts.length} rows ${trail ? `in the ${Math.round(trail / 60000)} min before` : 'by'} ${fmt(t)}`;
      this.painter && this.painter.filterTime(plan, t, trail);
      if (!fromClock && this.clock && typeof this.clock.seek === 'function') this.clock.seek((t - t0) / 1000);
    };
    /* WHY only a clock the dashboard declares: core's clockFor always answers, with the page's clock or an idle dashboard's,
       and following one of those plays a day of rows at one second a second. Alone, the bar plays by its own `speed:`. */
    const dash = this.host.element && this.host.element.closest && this.host.element.closest('data-dashboard');
    if (!this.clock && dash && dash.dash && dash.dash.clock) {
      const clock = core.clockFor(this.host.element);
      const onTime = (e) => { if (this._timeApply) this._timeApply(this._t0 + e.detail.t * 1000, true); };
      const onState = () => { if (this.timebar) this._says(clock.playing); };
      clock.addEventListener('time', onTime);
      clock.addEventListener('state', onState);
      this.clock = clock;
      this._clockOff = () => { clock.removeEventListener('time', onTime); clock.removeEventListener('state', onState); };
    }
    this._t0 = t0;
    this._says = says;
    if (this.clock) this.clock.extent(0, (t1 - t0) / 1000);
    btn.onclick = () => {
      if (this.clock) { if (this.clock.playing) this.clock.pause(); else this.clock.play(); return; }
      if (this.state.playing) { this._stop(); says(false); return; }
      if (this.state.t >= t1) apply(t0);
      this.state.playing = true;
      says(true);
      let last = performance.now();
      const tick = (now) => {
        const t = Math.min(t1, this.state.t + (now - last) * speed);
        last = now;
        apply(t);
        if (t >= t1) { this._stop(); says(false); return; }
        this._raf = requestAnimationFrame(tick);
      };
      this._raf = requestAnimationFrame(tick);
    };
    range.oninput = () => { this._stop(); if (!this.clock) says(false); apply(Number(range.value)); };
    this._timeApply = apply;
    apply(this.state.t);
  }

  /* ---------------------------------------------------------------- draw an area (Terra Draw) */
  _drawnHtml(input, plan) {
    const idxs = this.state.drawn;
    const L = this.spec.layers.find((l) => ['points', 'heatmap', 'hexbin'].includes(l.type)) || {};
    const by = this.spec.draw && input.view.drawBy;
    const sumP = input.view.drawSum;
    let html = `<section class="dv-map-drawn"><h4>Drawn area <span class="dv-map-derived">~ derived</span></h4><p class="dv-map-answer"><span class="dv-map-drawn-n">${idxs.length.toLocaleString('en-US')}</span> rows inside</p>`;
    if (sumP) {
      const s = idxs.reduce((a, i) => { const v = cellValue(input.rows[i][sumP]); return typeof v === 'number' ? { sum: a.sum + v, n: a.n + 1, none: a.none } : { ...a, none: a.none + 1 }; }, { sum: 0, n: 0, none: 0 });
      html += `<p>${esc(this.h.label(sumP))}: <b>${s.n ? esc(this.h.fmt(s.sum, sumP)) : '—'}</b> ${esc(this.h.unit(sumP))}${s.none ? ` <span class="dv-map-n">(${s.none} with no value, not counted)</span>` : ''}</p>`;
    }
    if (by) {
      const m = new Map();
      for (const i of idxs) { const v = this.h.text(input.rows[i], by) ?? '—'; m.set(v, (m.get(v) || 0) + 1); }
      html += `<ul class="dv-map-classes">${[...m.entries()].sort((a, b) => b[1] - a[1]).map(([v, n]) => `<li><span>${esc(v)}</span><span class="dv-map-n">${n.toLocaleString('en-US')}</span></li>`).join('')}</ul>`;
    }
    void L; void plan;
    return `${html}<button type="button" class="dv-map-drawn-open"${idxs.length ? '' : ' disabled'}>Open these rows</button></section>`;
  }

  async _drawTool(input, plan) {
    if (!this._drawBar) {
      this._drawBar = document.createElement('div');
      this._drawBar.className = 'dv-map-drawbar';
      this._drawBar.innerHTML = `<button type="button" class="dv-map-draw-btn" aria-pressed="false">Draw an area</button><button type="button" class="dv-map-draw-clear" hidden>Clear</button>`;
      this.stage.append(this._drawBar);
    }
    const map = this.map;
    const [btn, clear] = this._drawBar.children;
    const pointsSrc = plan.sources.find((s) => s.data && s.data.features && s.data.features.some((f) => f.geometry && f.geometry.type === 'Point' && f.properties && f.properties._i != null));
    const compute = async (poly) => {
      const A = await load('analysis', () => import('./analysis.js'));
      this.state.drawn = poly && pointsSrc ? A.insidePolygon(pointsSrc.data, poly) : null;
      this.state.drawnPoly = poly;
      this._panel(input, this.spec, this.plan);
      clear.hidden = !this.state.drawn;
    };
    this._recompute = compute;
    if (this.state.drawnPoly) compute(this.state.drawnPoly);
    btn.onclick = async () => {
      const [{ TerraDraw, TerraDrawPolygonMode }, { TerraDrawMapLibreGLAdapter }] = await load('draw', () => Promise.all([import('terra-draw'), import('terra-draw-maplibre-gl-adapter')]));
      if (this.map !== map) return;
      if (!this.draw) {
        const T = input.tokens;
        this.draw = new TerraDraw({ adapter: new TerraDrawMapLibreGLAdapter({ map }), modes: [new TerraDrawPolygonMode({ styles: { fillColor: T.accent.startsWith('rgb') ? rgbHex(T.accent) : T.accent, fillOpacity: 0.12, outlineColor: rgbHex(T.accent), outlineWidth: 2, closingPointColor: rgbHex(T.accent), closingPointOutlineColor: rgbHex(T.bg) } })] });
        this.draw.start();
        this.draw.on('finish', (id) => {
          const f = this.draw.getSnapshot().find((x) => x.id === id);
          for (const other of this.draw.getSnapshot()) if (other.id !== id) this.draw.removeFeatures([other.id]);
          compute(f);
          this.draw.setMode('static');
          btn.setAttribute('aria-pressed', 'false');
        });
      }
      this.draw.setMode('polygon');
      btn.setAttribute('aria-pressed', 'true');
    };
    clear.onclick = () => { if (this.draw) this.draw.clear(); compute(null); };
  }

  _drawMarkers(points, titleProp) {
    this._closeChooser();
    for (const { marker } of this.markers) marker.remove();
    const { select } = this.input.view;
    this.markers = points.map((p) => {
      const n = p.rows.length;
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `dv-map-marker${n > 1 ? ' dv-map-many' : ''}`;
      const size = Math.round(14 + 6 * Math.sqrt(n - 1));
      el.style.cssText = `--dv-pin: ${p.colour}; width: ${size}px; height: ${size}px;`;
      const name = String(cellValue(p.rows[0][titleProp]) ?? p.rows[0].id);
      el.title = n > 1 ? `${name} · ${n} rows` : name;
      el.setAttribute('aria-label', el.title);
      if (n > 1) el.textContent = String(n);
      const ids = p.rows.map((r) => String(r.id));
      if (this.peekId !== null && ids.includes(this.peekId)) el.classList.add('dv-active');
      // CONTRACT §39: rows that share one value of select: are one pick, with nothing to ask
      const asks = n > 1 && !!select && new Set(p.rows.map((r) => JSON.stringify(cellValue(r[select]) ?? null))).size > 1;
      if (asks) el.setAttribute('aria-expanded', 'false');
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!this.map) return; // this view was destroyed (its map parked or removed): its host is not ours to call
        if (n === 1) this.host.open(ids[0]);
        else if (asks) this._choose(p, el, titleProp, e.detail === 0);
        else this.host.open(ids[0], { records: p.rows, title: `${name} · ${n} rows at this point` });
      });
      const marker = new Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(this.map);
      return { marker, el, ids };
    });
    this._paintSel();
  }
}

/* A PMTiles source that reads by HTTP range, as PMTiles' own FetchSource does, and falls back to one whole-file read
   when the server ignores Range (python -m http.server, which serves the browser checks, answers 200 with the whole
   file): the body is then kept and sliced. WHY: a basemap must draw on any static host, ranges or not. */
class RangeOrWhole {
  constructor(url) { this.url = url; this.whole = null; }
  getKey() { return this.url; }
  async getBytes(offset, length, signal) {
    if (!this.whole) {
      const r = await fetch(this.url, { headers: { Range: `bytes=${offset}-${offset + length - 1}` }, signal });
      if (!r.ok) throw new Error(`${r.status} ${this.url}`);
      if (r.status === 206) return { data: await r.arrayBuffer(), etag: r.headers.get('etag') || undefined };
      this.whole = await r.arrayBuffer();
    }
    return { data: this.whole.slice(offset, offset + length) };
  }
}

function rgbHex(text) {
  const m = /(\d+)\D+(\d+)\D+(\d+)/.exec(text);
  if (!m) return '#3366cc';
  return `#${[m[1], m[2], m[3]].map((v) => Number(v).toString(16).padStart(2, '0')).join('')}`;
}
