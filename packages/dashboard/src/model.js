/* The dashboard's model, pure (no DOM): read a .base file's dashboard keys, then, for any state (each dataset's rail
   filter and the panels' selections), say which filter each panel gets and what each roll-up is. docs/peps/0004.

   The rules (PEP 0004 §5), in one place so the browser, the checker and the unit tests agree:
   - a panel on dataset D gets: D's rail filter, every selection made on D by ANOTHER panel, and a semi-join clause
     for each other restricted dataset S linked to D (the keys of S's rows passing S's own filters, carried along the
     link): one clause per link when S and D are linked directly, else one along the fewest-hops path; the emitting
     panel ignores its own selection (Superset's and Mosaic's crossfilter rule);
   - links filter, they never add a column: a semi-join is an ordinary Bases filter on the link column;
   - a roll-up is a summary of another dataset's rows (those passing that dataset's own filters), through a tree,
     drawn as a derived cell that says how it was made;
   - a layer dataset (CONTRACT §32: a 3D view's layer reading another dataset) is filtered exactly as a panel on that
     dataset with the layer's panel's key would be;
   - navigation (CONTRACT §33, PEP 0010 P3; docs/peps/0013-navigation.md): a link may be one-way (its from side's picks
     narrow its to side, never back); a dataset whose data: names a placeholder (runs/{run}.json) reads the one file the
     other datasets' picks leave and narrows no other dataset; a view's `selected:` presets its selection; a select: on a
     property its dataset's rail picks one value of (as: select) moves that pick (a picker). */

import { compileFilters, cellValue, summarize } from '../../core/src/grammar.js';
import { isNum, slug } from '../../core/src/format.js';
import { readLegendParams, writeLegendParams } from '../../core/src/legend.js';
import { facetSpecs, railConfig, toRail, fromRail, settleChildren } from '../../core/src/facets.js';
import { rowModel } from '../../core/src/rowmodel.js';

const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const stem = (path) => String(path).split('/').pop().replace(/\.[^.]+$/, '');

// ------------------------------------------------------------------ reading the file

/** Each URL-bearing dashboard's clock scope, in document order (docs/peps/0005-dashboard-cards.md §4,
    docs/peps/0008-one-clock-driver.md): null on a page with one (plain #t= / #tr=); else its id as written, else a slug
    of its src when no other dashboard on the page has that key. WHY no position (judge r3 #6, the coordinator's call
    2026-10-28): round 2 numbered repeated sources -2, -3 … in document order, so inserting a dashboard above another
    re-pointed a saved #t.views-base-2=. Now a repeated or slug-colliding src without ids, a src whose key is another
    dashboard's id, and a repeated id get `false` — their clock stays out of the URL — and a problem each, which the
    page lists and `data-ui check page.html` reports at the tag's line. list: [{id, src}] → {scopes, problems: [[i, msg]]} */
export function clockScopes(list) {
  if (list.length <= 1) return { scopes: list.map(() => null), problems: [] };
  const key = (d) => slug(d.src || '') || 'dashboard';
  const ids = new Map(), autos = new Map();
  for (const d of list) {
    if (d.id) ids.set(d.id, (ids.get(d.id) || 0) + 1);
    else autos.set(key(d), (autos.get(key(d)) || 0) + 1);
  }
  const scopes = [], problems = [];
  const unkept = 'until then its time and range are not kept in the URL';
  list.forEach((d, i) => {
    if (d.id) {
      const n = ids.get(d.id);
      if (n === 1) { scopes.push(d.id); return; }
      scopes.push(false);
      problems.push([i, `id '${d.id}' is used by ${n} dashboards on this page: give each its own id; ${unkept}`]);
      return;
    }
    const k = key(d);
    if (autos.get(k) === 1 && !ids.has(k)) { scopes.push(k); return; }
    scopes.push(false);
    const why = autos.get(k) > 1 ? 'which more than one dashboard on this page has' : "which is another dashboard's id";
    problems.push([i, `src '${d.src || ''}' gives the URL key '${k}', ${why}: give each an id (<data-dashboard id="…">); ${unkept}`]);
  });
  return { scopes, problems };
}

/** `data-ui check page.html`: the <data-dashboard> tags of an HTML page, by clockScopes' rule (the one the page applies
    at runtime); a problem is an error at the tag's line. Tags with no-url are not in the URL and are left out. */
export function checkPage(text) {
  const tags = [];
  const TAG = /<data-dashboard\b([^>]*)>/gi;
  const ATTR = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  for (let m; (m = TAG.exec(text));) {
    const attrs = {};
    for (let a; (a = ATTR.exec(m[1]));) attrs[a[1].toLowerCase()] = a[2] ?? a[3] ?? a[4] ?? '';
    if ('no-url' in attrs) continue;
    tags.push({ id: attrs.id || null, src: attrs.src || '', line: text.slice(0, m.index).split('\n').length });
  }
  const { problems } = clockScopes(tags);
  return problems.map(([i, message]) => ({ level: 'error', line: tags[i].line, message }));
}

/** "10s" / "500ms" / "1m" -> ms (never under 250 ms: a poll is not an animation); anything else -> null. */
export function refreshMs(text) {
  const m = /^(\d+(?:\.\d+)?)(ms|s|m)$/.exec(String(text ?? '').trim());
  if (!m) return null;
  return Math.max(250, Number(m[1]) * { ms: 1, s: 1000, m: 60000 }[m[2]]);
}

// WHY these defaults: Zach's references (Klipfolio) are one surface, transparent cards, rounded numbers, frameless
// charts; "the default should already look like the references" (2026-10-26). docs/peps/0005-dashboard-cards.md §5
// WHY filled + inside: Zach's references (Klipfolio) are tiles on a quieter page with the title inside each tile, one
// surface with no inner boxes; transparent and outline stay one key away
export const STYLE_DEFAULTS = Object.freeze({ theme: 'auto', surface: 'filled', radius: 12, pad: 16, gap: 12, title: 'inside',
  density: 'comfortable', chrome: 'minimal', numbers: Object.freeze({}), palette: Object.freeze({}) });
// WHY numbers {} by default: rounding a stored value is the author's declared choice (truthful rendering); every
// rebuilt dashboard declares `style.numbers` in its .base

/** The style a panel's view sees: defaults, then the dashboard's, the panel's, the view's own (palette and numbers
    merge key by key; families' property is replaced and its colors merge key by key, CONTRACT §32). */
export function resolveStyle(...layers) {
  const out = { ...STYLE_DEFAULTS, numbers: { ...STYLE_DEFAULTS.numbers }, palette: {} };
  for (const l of layers) {
    if (!l || typeof l !== 'object') continue;
    for (const [k, v] of Object.entries(l)) {
      if (v === undefined || v === null) continue;
      if (k === 'palette' || k === 'numbers') out[k] = { ...out[k], ...(typeof v === 'object' ? v : {}) };
      // WHY merged, not replaced: a panel that recolours one family (sim: 3) keeps the dashboard's property and the
      // other families, as a palette entry does
      else if (k === 'families') {
        if (typeof v !== 'object') continue;
        const was = out.families || {};
        out.families = { ...was, ...v, colors: { ...(was.colors || {}), ...(v.colors && typeof v.colors === 'object' ? v.colors : {}) } };
      } else out[k] = v;
    }
  }
  return out;
}

/** The dashboard keys of a parsed .base document: {datasets, defaultName, links, panels, hidden, rowHeight, columns,
    problems}. A dataset is {name, data, facets, filters, tree, rollup}; a panel is {key, title, views, text, w, h,
    toolbar, t}; `hidden` lists the panels the layout keeps but does not draw. `problems` are readable strings (the
    checker reports them with lines). */
export function readDashboard(base) {
  const problems = [];
  const datasets = {};
  const given = (base && base.datasets) || {};
  let defaultName = null;
  // WHY first: the file's own data: is read before anything is picked, so it can never wait for a pick (CONTRACT §33)
  if (base && typeof base.data === 'string' && placeholders(base.data)) {
    problems.push(`data: the file's data: is read before anything is picked, so it names one file; a file read per pick (${base.data}) belongs in a datasets: entry`);
  }
  for (const [name, entry] of Object.entries(given)) {
    const d = typeof entry === 'string' ? { data: entry } : { ...(entry || {}) };
    if (!d.data) { problems.push(`datasets.${name}: needs data: (a file next to the .base)`); continue; }
    const template = typeof d.data === 'string' ? placeholders(d.data) : null;
    datasets[name] = { name, label: d.label || null, data: d.data, facets: d.facets || null, filters: d.filters, tree: d.tree || null, rollup: d.rollup || null,
      refresh: template ? null : refreshMs(d.refresh), template };
    if (d.refresh !== undefined && refreshMs(d.refresh) === null) problems.push(`datasets.${name}.refresh: write an interval such as 10s, 500ms or 1m`);
    // WHY not both: a per-pick dataset is one run's file, read when the pick names it; a timer or a stream re-reads one
    // file for every run (the dashboard has no run to re-read until a pick names it)
    if (template && d.refresh !== undefined) problems.push(`datasets.${name}.refresh: ${name} is read one ${template[0]} at a time (data: ${d.data}), when a pick names it, so it cannot also refresh on a timer`);
    if (template && d.live !== undefined) problems.push(`datasets.${name}.live: ${name} is read one ${template[0]} at a time (data: ${d.data}), when a pick names it; it cannot also be live`);
    if (base.data && d.data === base.data) defaultName = name;
  }
  if (base && base.data && !defaultName) {
    defaultName = stem(base.data);
    if (datasets[defaultName]) problems.push(`datasets.${defaultName}: the default data (${base.data}) is named by its file stem, and another file has that name`);
    datasets[defaultName] = { name: defaultName, label: null, data: base.data, facets: null, filters: undefined, tree: null, rollup: null, refresh: null, template: null };
  }
  if (defaultName) {
    const d = datasets[defaultName];
    if (!d.facets && base.facets) d.facets = base.facets;
    if (d.filters === undefined && base.filters !== undefined) d.filters = base.filters;
  }
  const links = [];
  for (const [i, l] of ((base && base.links) || []).entries()) {
    const a = parseEnd(l && l.from), b = parseEnd(l && l.to);
    if (!a || !b) { problems.push(`links[${i}]: a link is {from: <dataset>.<property>, to: <dataset>.<property>}`); continue; }
    for (const end of [a, b]) if (!datasets[end.ds]) problems.push(`links[${i}]: no dataset '${end.ds}' (datasets: ${Object.keys(datasets).join(', ')})`);
    const direction = l.direction === undefined || l.direction === null ? 'two-way' : l.direction;
    if (direction !== 'one-way' && direction !== 'two-way') problems.push(`links[${i}].direction: '${l.direction}' is neither one-way (the from side's picks narrow the to side, never back) nor two-way (the default)`);
    links.push({ a, b, oneWay: direction === 'one-way' });
  }
  // a per-pick dataset's placeholder is filled through a link that ends on it (CONTRACT §33): without one nothing can pick
  for (const d of Object.values(datasets)) {
    for (const p of d.template || []) {
      const reached = links.some((l) => (l.b.ds === d.name && l.b.col === p && l.a.ds !== d.name) || (!l.oneWay && l.a.ds === d.name && l.a.col === p && l.b.ds !== d.name));
      if (!reached) problems.push(`datasets.${d.name}.data: nothing can pick the '${p}' that ${d.data} is read for: no link ends at ${d.name}.${p} (write one from the dataset that is picked, e.g. {from: runs.${p}, to: ${d.name}.${p}, direction: one-way})`);
    }
  }
  const views = (base && base.views) || [];
  const byName = new Map(views.map((v) => [v.name, v]));
  for (const [i, v] of views.entries()) if (v.from && !datasets[v.from]) problems.push(`views[${i}].from: no dataset '${v.from}'`);
  // CONTRACT §33: selected: presets the selection a click on the view makes, so it needs the view's select:
  for (const [i, v] of views.entries()) {
    if (v && v.selected !== undefined && (typeof v.select !== 'string' || !v.select)) problems.push(`views[${i}].selected: it presets what a click on this view selects, and the view has no select: (add select: <property>)`);
  }
  // CONTRACT §32: a 3D layer may read another dataset of the dashboard; it must be one
  for (const [i, v] of views.entries()) {
    for (const [path, name] of layerRefs(v)) {
      if (!datasets[name]) problems.push(`views[${i}].${pathText(path)}: no dataset '${name}' (datasets: ${Object.keys(datasets).join(', ')})`);
    }
  }
  const layout = (base && base.layout) || {};
  const columns = Number(layout.columns) || 12;
  const rowHeight = Number(layout.rowHeight) || 110;
  const panels = [];
  const hidden = [];
  const keys = new Set();
  for (const [i, p] of (layout.panels || []).entries()) {
    if (!p || typeof p !== 'object') continue;
    const names = p.views || (p.view ? [p.view] : []);
    const list = names.map((n) => byName.get(n)).filter(Boolean);
    for (const n of names) if (!byName.has(n)) problems.push(`layout.panels[${i}]: no view named '${n}'`);
    const dss = new Set(list.map((v) => v.from || defaultName));
    if (dss.size > 1) problems.push(`layout.panels[${i}]: the views of one panel read one dataset (${[...dss].join(', ')})`);
    if (!list.length && typeof p.text !== 'string') continue;
    let key = slug(p.key || p.title || (list[0] && list[0].name) || `text-${i + 1}`) || `panel-${i + 1}`;
    while (keys.has(key)) key += '-2';
    keys.add(key);
    const dataset = list.length ? list[0].from || defaultName : null;
    // the editor's Hide (CONTRACT §41): the entry stays in the file, in its place, not drawn
    (p.hidden === true ? hidden : panels).push({ key, i, title: p.title || null, views: list, text: typeof p.text === 'string' ? p.text : null,
      w: Math.max(1, Math.min(columns, Number(p.w) || columns)), h: p.h === undefined ? null : Number(p.h) || null,
      toolbar: p.toolbar || null, style: p.style && typeof p.style === 'object' ? p.style : null,
      // CONTRACT §40: the panel's data-views gets the Edit / View switch
      editToggle: p.editToggle === true,
      // CONTRACT §32: the other datasets its views' layers read (every tab's, each once)
      dataset, layers: [...new Set(list.flatMap((v) => layerNames(v, dataset)))],
      // CONTRACT §33: the selection its view presets, and the rail pick it moves (a picker)
      preset: presetOf(list), picks: picksOf(list, datasets[dataset]),
      // CONTRACT §34: the instant the panel stands at (seconds): its views read a clock of their own, paused there
      t: typeof p.t === 'number' && Number.isFinite(p.t) ? p.t : null });
  }
  const style = base && base.style && typeof base.style === 'object' ? base.style : {};
  const clock = base && base.clock && typeof base.clock === 'object' ? base.clock : null;
  if (clock && clock.data && !datasets[clock.data]) problems.push(`clock.data: no dataset '${clock.data}'`);
  // WHY an error, not a fall-through: clock.primary chooses the ONE video that drives t (docs/peps/0008-one-clock-driver.md);
  // a typo used to leave the dashboard on wall time with no word about it
  if (clock && clock.primary !== undefined) {
    const videos = [...new Set([...panels, ...hidden].flatMap((p) => p.views).filter((v) => v && v.type === 'video' && v.name).map((v) => v.name))];
    if (typeof clock.primary !== 'string' || !videos.includes(clock.primary)) {
      problems.push(`clock.primary: '${clock.primary}' is not a video card on the layout (${videos.length ? `video cards: ${videos.map((n) => `'${n}'`).join(', ')}` : 'it has no video card'})`);
    }
  }
  const rerun = base && base.rerun && typeof base.rerun === 'object' && base.rerun.rrd ? base.rerun : null;
  return { datasets, defaultName, links, panels, hidden, columns, rowHeight, problems, style, clock, rerun, arrange: layout.arrange !== false };
}

function parseEnd(text) {
  if (typeof text !== 'string') return null;
  const i = text.indexOf('.');
  if (i <= 0 || i === text.length - 1) return null;
  return { ds: text.slice(0, i), col: text.slice(i + 1) };
}

// ------------------------------------------------------------------ navigation (docs/CONTRACT.md §33)

const PLACEHOLDER = /\{([^{}]+)\}/g;

/** The placeholders a dataset's data: names (`runs/{run}.json` → ['run']), each once in the order written; null when
    it names none (a plain file). */
export function placeholders(path) {
  const out = [];
  for (const m of String(path ?? '').matchAll(PLACEHOLDER)) if (!out.includes(m[1])) out.push(m[1]);
  return out.length ? out : null;
}

/** A per-pick path with each {p} filled from `values` as one URL path segment (encodeURIComponent: CONTRACT §24's
    origin.url rule), or null while some placeholder has no value. */
export function fillPath(path, values) {
  let missing = false;
  const out = String(path).replace(PLACEHOLDER, (_, p) => {
    const v = values ? values[p] : undefined;
    if (v === null || v === undefined || v === '' || typeof v === 'object') { missing = true; return ''; }
    return encodeURIComponent(String(v));
  });
  return missing ? null : out;
}

/** A panel's preset (CONTRACT §33, sim2real gap #7): the first of its views that says both select: and selected:
    → {view, property, values: 'first' | [values]} (a single value is a list of one; `[first]` is the literal). */
function presetOf(views) {
  const v = views.find((x) => x && typeof x.select === 'string' && x.select && x.selected !== undefined && x.selected !== null);
  if (!v) return null;
  return { view: v.name, property: v.select, values: v.selected === 'first' ? 'first' : Array.isArray(v.selected) ? [...v.selected] : [v.selected] };
}

/** The property a panel picks on its dataset's rail (a picker), or null: a view's select: on a property that rail
    stands over with one choice (as: select). WHY only a single choice: a selection under a rail that already picks
    one value could only repeat it or empty the panels; several values (as: values) and a selection inside them still
    mean what they meant. */
function picksOf(views, dataset) {
  const facets = dataset && Array.isArray(dataset.facets) ? dataset.facets : [];
  for (const v of views) {
    if (!v || typeof v.select !== 'string') continue;
    if (facets.some((f) => f && typeof f === 'object' && f.property === v.select && f.as === 'select')) return v.select;
  }
  return null;
}

/** The facet specs and config of one dataset's rail, as its <data-facets> reads them. */
function railTools(dash, data, name) {
  const d = dash.datasets[name];
  const props = (data && data[name] && data[name].properties) || {};
  const specs = facetSpecs({ facets: (d && Array.isArray(d.facets) ? d.facets : []) }, null, props);
  return { specs, config: railConfig(specs) };
}

/** A rail filter without its pick on `property` (what a picker panel lists under: every value the rest leaves). */
function unpicked(dash, data, name, rail, property) {
  if (rail === undefined || rail === null || rail === '') return rail;
  const { config } = railTools(dash, data, name);
  const { facets, rest } = toRail(rail, config);
  if (!facets[property]) return rail;
  delete facets[property];
  return fromRail(facets, rest);
}

/** The values a dataset's rail picks for `property` ([] when it picks none). */
export function railPicks(dash, data, name, rail, property) {
  if (rail === undefined || rail === null || rail === '') return [];
  const { config } = railTools(dash, data, name);
  const f = toRail(rail, config).facets[property];
  return f && Array.isArray(f.values) ? [...f.values] : [];
}

/** A picker's click (CONTRACT §33): the dataset's rail with `property` picking `value` alone, the rail's other picks
    kept, and the facets nested under it settled (CONTRACT §7, parent:). Returns the new rail filter. */
export function pickRail(dash, data, rail, name, property, value) {
  const { specs, config } = railTools(dash, data, name);
  const { facets, rest } = toRail(rail, config);
  const list = ((data[name] && data[name].properties && data[name].properties[property]) || {}).type === 'list';
  facets[property] = { values: [value], match: list ? 'contains' : 'equals' };
  const settled = specs.some((s) => s.parent === property) ? settleChildren((data[name] && data[name].rows) || [], facets, specs, property) : facets;
  return fromRail(settled, rest);
}

/** Can a link carry rows of dataset `s` to dataset `d`? A two-way link either way, a one-way link from its from. */
const carriesTo = (l, s, d) => (l.a.ds === s && l.b.ds === d) || (!l.oneWay && l.b.ds === s && l.a.ds === d);
const sameTemplate = (dash, s, d) => {
  const a = dash.datasets[s] && dash.datasets[s].template, b = dash.datasets[d] && dash.datasets[d].template;
  return !!a && !!b && JSON.stringify(a) === JSON.stringify(b);
};

/** The link paths that carry dataset `s`'s picks to dataset `d`: when the two are linked directly, each direct link
    that carries that way (one path each; a one-way link from d to s carries none, and no detour stands in for it);
    else the fewest hops along the links' directions; [] when none. */
function carriers(dash, s, d) {
  const between = dash.links.filter((l) => (l.a.ds === s && l.b.ds === d) || (l.b.ds === s && l.a.ds === d));
  if (between.length) return between.filter((l) => carriesTo(l, s, d)).map((l) => [l.a.ds === s ? { from: l.a, to: l.b } : { from: l.b, to: l.a }]);
  const path = linkPath(dash.links, s, d, { directed: true });
  return path ? [path] : [];
}

/** The file a per-pick dataset reads now (CONTRACT §33): {path, values, choices}. `choices[p]` is the values of p the
    other datasets' picks leave (each restricted dataset's rows that pass its own filter, carried along the links that
    end on <name>.p, met; the first's row order), or null when nothing restricts p; `path` is data: with each {p} filled
    (fillPath) when every placeholder has exactly one value, else null (and `values` null). */
export function templateFile(dash, data, state, name) {
  const d = dash.datasets[name];
  const ps = (d && d.template) || [];
  const choices = {};
  for (const p of ps) choices[p] = templateChoices(dash, data, state, name, p);
  if (!ps.length || !ps.every((p) => Array.isArray(choices[p]) && choices[p].length === 1)) return { path: null, values: null, choices };
  const values = Object.fromEntries(ps.map((p) => [p, choices[p][0]]));
  return { path: fillPath(d.data, values), values, choices };
}

/** The file a dashboard declares for dataset `name` (CONTRACT §34), as a URL: its `data:` resolved against `base`, where
    the .base lives (the top level's data: is declared under its stem's name, §17); for a per-pick dataset the one file
    its picks read now (`picked`: its href, null while none is read). null for a dataset the dashboard does not declare.
    WHY the declared file and not the dataset object's url (RobotDx PEP 0001 §17.1, ask 2): a host may hand one dataset
    object to several declared files (/dx/ hands every board one config dataset), so the object's url is whichever
    binding made it first, and a panel added from another board would read that board's settings. */
export function declaredFile(dash, name, { base, picked = null } = {}) {
  const d = dash && dash.datasets && dash.datasets[name];
  if (!d || typeof d.data !== 'string') return null;
  if (d.template) return picked || null;
  try { return new URL(d.data, base).href; } catch { return null; }
}

function templateChoices(dash, data, state, name, p) {
  let keys = null;
  const meet = (m) => { keys = keys === null ? m : new Map([...keys].filter(([k]) => m.has(k))); };
  for (const s of Object.keys(dash.datasets)) {
    // WHY not another per-pick dataset: its rows are one pick's, so they can never say which file to read
    if (s === name || !data[s] || dash.datasets[s].template) continue;
    const f = ownFilter(dash, data, state, s, null);
    if (f === undefined) continue;
    const paths = carriers(dash, s, name).filter((path) => path[path.length - 1].to.col === p);
    if (!paths.length) continue;
    const rows = keep(data[s].rows, f);
    for (const path of paths) meet(carry(path, rows, data));
  }
  // a selection another panel made on this dataset's own column
  for (const sel of Object.values(state.select || {})) {
    if (sel && sel.dataset === name && sel.property === p && sel.values && sel.values.length) meet(new Map(sel.values.map((v) => [String(v), v])));
  }
  return keys === null ? null : [...keys.values()];
}

/** The values a panel's preset selects (CONTRACT §33): a literal list as written; `first`, the first row its view draws
    (its sort and groups, its own filters) under the panel's filter in `state`. null when there is no such row. */
export function presetValues(dash, data, state, panel) {
  if (!panel || !panel.preset) return null;
  if (panel.preset.values !== 'first') return [...panel.preset.values];
  const ds = data[panel.dataset];
  if (!ds) return null;
  const view = panel.views.find((v) => v.name === panel.preset.view) || panel.views[0];
  const filters = panelFilter(dash, data, state, panel.dataset, panel.key);
  let model;
  try { model = rowModel(ds, { properties: {} }, view, { filters }); } catch { return null; }
  const row = model.rows[0];
  if (!row) return null;
  const v = cellValue(row[panel.preset.property]);
  if (Array.isArray(v)) return v.length ? [v[0]] : null;
  return isEmpty(v) ? null : [v];
}

/** Every preset a page opens with (CONTRACT §33), in layout order, each applied before the next is resolved (a
    deployment's `first` narrows the runs a later `first` picks from): {select: {<panel>: {dataset, property, values}},
    rail: {<dataset>: filter}} (a picker's preset picks on its rail, when the rail picks nothing on that property yet).
    `skip`: the panels the URL already names (cleared with s.<panel>=); a panel already selected keeps its selection. */
export function presets(dash, data, state, skip = []) {
  const work = { ...state, rail: { ...(state.rail || {}) }, select: { ...(state.select || {}) } };
  const out = { select: {}, rail: {} };
  const skipped = new Set(skip);
  for (const p of dash.panels) {
    if (!p.preset || skipped.has(p.key)) continue;
    if (p.picks) {
      if (railPicks(dash, data, p.dataset, work.rail[p.dataset], p.picks).length) continue;
      const values = presetValues(dash, data, work, p);
      if (!values || !values.length) continue;
      out.rail[p.dataset] = work.rail[p.dataset] = pickRail(dash, data, work.rail[p.dataset], p.dataset, p.picks, values[0]);
      continue;
    }
    const cur = work.select[p.key];
    if (cur && cur.values && cur.values.length) continue;
    const values = presetValues(dash, data, work, p);
    if (!values || !values.length) continue;
    out.select[p.key] = work.select[p.key] = { dataset: p.dataset, property: p.preset.property, values: [...values] };
  }
  return out;
}

/** presets(…).select: the selections the page opens with. */
export function presetSelections(dash, data, state, skip = []) {
  return presets(dash, data, state, skip).select;
}

/** Does a panel still draw a row holding one of `values` of `property`, under its filter in `state`? */
function drawsValue(dash, data, state, panel, property, values) {
  const want = new Set(values.map(String));
  return keep(data[panel.dataset].rows, panelFilter(dash, data, state, panel.dataset, panel.key)).some((r) => {
    const v = cellValue(r[property]);
    return Array.isArray(v) ? v.some((x) => want.has(String(x))) : want.has(String(v));
  });
}

/** The selections once a pick has settled (CONTRACT §39): in layout order, a panel with a preset whose selection names no
    row it still draws (a pick or a rail upstream left none of its values) picks again by its preset, or holds nothing when
    the preset names no row either. Returns the new {<panel>: selection}; `state` is left as it was.
    WHY only a preset's panel: `selected:` is the author saying this panel holds a pick when it can. Any other panel keeps
    what it has, as before. WHY in layout order, one panel at a time: a robot that moves carries its run with it, so each
    panel settles against the one above it as it now stands (measured on robotics-fleet: the second robot picked left the
    first robot's run selected, and the playback said "the picks leave no run"). */
export function settledSelections(dash, data, state) {
  const work = { ...state, select: { ...(state.select || {}) } };
  for (const p of dash.panels) {
    const cur = work.select[p.key];
    // WHY not a per-pick or a live dataset: neither holds what its panel draws in .rows, so "names no row" cannot be told
    if (!p.preset || p.picks || !cur || !cur.values || !cur.values.length || !data[p.dataset] || dash.datasets[p.dataset].template || isLive(data[p.dataset])) continue;
    if (drawsValue(dash, data, work, p, cur.property, cur.values)) continue;
    delete work.select[p.key];
    const values = presetValues(dash, data, work, p);
    if (values && values.length && drawsValue(dash, data, work, p, p.preset.property, values)) work.select[p.key] = { dataset: p.dataset, property: p.preset.property, values: [...values] };
  }
  return work.select;
}

// a key path as the checker prints it: scene3d.layers[2].data
const pathText = (path) => path.map((p) => (typeof p === 'number' ? `[${p}]` : `.${p}`)).join('').slice(1);

// ------------------------------------------------------------------ layer datasets (docs/CONTRACT.md §32)

/** Where a view names a layer dataset (CONTRACT §32): [path, name] for each `data:` of a scene3d view's layers, for a
    trajectory3d view's `compare.data` and `robots.data`, and for a timeseries' annotations (kit gap 2: a driver's mode
    and fault changes, a gripper's grasps, read from events.json), in the order written; paths are relative to the view
    entry. A block on a view of another type is never drawn, so it names nothing. */
export function layerRefs(view) {
  const out = [];
  if (!view || typeof view !== 'object') return out;
  const named = (x) => x && typeof x === 'object' && typeof x.data === 'string' && x.data !== '';
  const s = view.type === 'scene3d' && view.scene3d && typeof view.scene3d === 'object' ? view.scene3d : null;
  if (s && Array.isArray(s.layers)) s.layers.forEach((l, j) => { if (named(l)) out.push([['scene3d', 'layers', j, 'data'], l.data]); });
  const tr = view.type === 'trajectory3d' && view.trajectory3d && typeof view.trajectory3d === 'object' ? view.trajectory3d : null;
  if (tr) for (const k of ['compare', 'robots']) if (named(tr[k])) out.push([['trajectory3d', k, 'data'], tr[k].data]);
  const ts = view.type === 'timeseries' && view.timeseries && typeof view.timeseries === 'object' ? view.timeseries : null;
  if (ts && Array.isArray(ts.annotations)) ts.annotations.forEach((a, j) => { if (named(a)) out.push([['timeseries', 'annotations', j, 'data'], a.data]); });
  return out;
}

/** The datasets a view reads as layers: each once, in the order written, without `own` (the view's own dataset,
    whose rows the view already gets as input.rows). */
export function layerNames(view, own = null) {
  return [...new Set(layerRefs(view).map(([, name]) => name))].filter((name) => name !== own);
}

// ------------------------------------------------------------------ clauses

const ref = (p) => (/^[A-Za-z_]\w*$/.test(p) ? p : `note[${JSON.stringify(p)}]`);
const lit = (v) => (typeof v === 'number' || typeof v === 'boolean' ? String(v) : JSON.stringify(String(v)));

/** A Bases filter that keeps rows whose `property` is one of `values` (a list cell: contains one of them). An empty
    list keeps nothing. */
export function inClause(property, values, { list = false } = {}) {
  const vals = [...new Set(values.filter((v) => !isEmpty(v)).map((v) => (typeof v === 'number' ? v : String(v))))];
  const one = (v) => (list ? `${ref(property)}.contains(${lit(v)})` : `${ref(property)} == ${lit(v)}`);
  if (!vals.length) return 'false';
  if (vals.length === 1) return one(vals[0]);
  return { or: vals.map(one) };
}

const and = (list) => {
  const out = list.filter((f) => f !== undefined && f !== null && f !== '' && !(f.and && !f.and.length));
  return out.length === 0 ? undefined : out.length === 1 ? out[0] : { and: out };
};

/** The values of `property` among rows (list cells spread). */
export function valuesOf(rows, property) {
  const out = [];
  for (const r of rows) {
    const v = cellValue(r[property]);
    if (Array.isArray(v)) out.push(...v); else if (!isEmpty(v)) out.push(v);
  }
  return out;
}

// ------------------------------------------------------------------ links

/** The link path from dataset `from` to dataset `to` (breadth first, fewest hops): [{from: {ds, col}, to: {ds, col}}],
    [] when they are the same dataset, null when no path joins them. `directed`: a one-way link is crossed only from
    its from side to its to side (how picks flow, CONTRACT §33); without it every link is crossed both ways (a roll-up's
    join, a chip's name). */
export function linkPath(links, from, to, { directed = false } = {}) {
  if (from === to) return [];
  const seen = new Set([from]);
  const queue = [[from, []]];
  while (queue.length) {
    const [at, path] = queue.shift();
    for (const l of links) {
      for (const [x, y] of directed && l.oneWay ? [[l.a, l.b]] : [[l.a, l.b], [l.b, l.a]]) {
        if (x.ds !== at || seen.has(y.ds)) continue;
        const next = [...path, { from: x, to: y }];
        if (y.ds === to) return next;
        seen.add(y.ds);
        queue.push([y.ds, next]);
      }
    }
  }
  return null;
}

/** Carry rows of the path's first dataset along it: the keys left at the last step's column, as a Map from their
    text to the value as written (so a number stays a number in the clause). */
export function carry(path, rows, datasets) {
  let current = rows;
  let keys = new Map();
  for (const [i, step] of path.entries()) {
    keys = new Map(valuesOf(current, step.from.col).map((v) => [String(v), v]));
    if (i === path.length - 1) break;
    const next = datasets[step.to.ds];
    current = next.rows.filter((r) => { const v = cellValue(r[step.to.col]); return Array.isArray(v) ? v.some((x) => keys.has(String(x))) : !isEmpty(v) && keys.has(String(v)); });
  }
  return keys;
}

// ------------------------------------------------------------------ the state -> each panel's filter

/** state: {rail: {<dataset>: filter}, select: {<panel key>: {dataset, property, values}}}; data: {<dataset>:
    normalized dataset}. The filter a panel on `dataset` gets, leaving out the selection of `panelKey` (its own). */
export function panelFilter(dash, data, state, dataset, panelKey = null) {
  const own = (ds) => ownFilter(dash, data, state, ds, panelKey);
  // a picker panel (CONTRACT §33) lists every value its rail's pick could be: its own pick is left out of its own filter
  const picker = panelKey ? dash.panels.find((p) => p.key === panelKey && p.dataset === dataset && p.picks) : null;
  const parts = [picker ? ownFilter(dash, data, state, dataset, panelKey, { unpick: picker.picks }) : own(dataset)];
  const listCol = (ds, col) => ((data[ds] && data[ds].properties && data[ds].properties[col]) || {}).type === 'list';
  for (const s of Object.keys(dash.datasets)) {
    if (s === dataset || !data[s]) continue;
    // WHY (CONTRACT §33): a per-pick dataset holds one run's rows, not every run's, so its picks narrow only a dataset read
    // for the same pick; a link written two-way into it carries nothing back
    if (dash.datasets[s].template && !sameTemplate(dash, s, dataset)) continue;
    const f = own(s);
    if (f === undefined) continue;
    // WHY every direct link (PEP 0010 P1a, CONTRACT §32): two datasets that share several key columns (a run, a device,
    // a situation) are linked once per column, and each link filters. PEP 0004's one path carried only the first link,
    // so a device pick on a samples rail left every device's rows in a panel on diff_samples. A dataset with no direct
    // link joins along the fewest-hops path, as before; with one link per pair nothing changes. A one-way link carries
    // only from its from side (CONTRACT §33, sim2real gap #8).
    const paths = carriers(dash, s, dataset);
    if (!paths.length) continue;
    const rows = keep(data[s].rows, f);
    for (const path of paths) {
      const keys = carry(path, rows, data);
      const last = path[path.length - 1].to;
      // WHY the target's own values: a link may join a number column to a text one ("14" vs 14), and the grammar's ==
      // compares numbers as numbers, so the clause names each key the way the target dataset writes it
      const want = new Set(keys.keys());
      const written = new Map();
      for (const v of valuesOf(data[dataset].rows, last.col)) if (want.has(String(v))) written.set(String(v), v);
      parts.push(inClause(last.col, [...written.values()], { list: listCol(dataset, last.col) }));
    }
  }
  return and(parts);
}

/** Every panel's filter, {<panel key>: filter}: what <data-dashboard>.panelFilters() returns (panels with views). */
export function panelFilters(dash, data, state) {
  return Object.fromEntries(dash.panels.filter((p) => p.views.length).map((p) => [p.key, panelFilter(dash, data, state, p.dataset, p.key)]));
}

/** One panel's layer datasets' filters (CONTRACT §32), {<dataset>: filter}: each is the filter a panel on that dataset
    with this panel's key gets (its rail, every OTHER panel's selections, the links), so a layer hears exactly what a
    panel there would and the panel that made a selection does not narrow its own layers. Datasets not loaded in `data`
    are left out. */
export function layerFilters(dash, data, state, panel) {
  const out = {};
  for (const name of (panel && panel.layers) || []) if (data[name]) out[name] = panelFilter(dash, data, state, name, panel.key);
  return out;
}

/** One panel's layer datasets, {<dataset>: {filter, rows}}: the rows are the dataset's own row objects that pass, in
    file order (what <data-dashboard> hands the panel's <data-views> as `layers`). */
export function panelLayers(dash, data, state, panel) {
  return Object.fromEntries(Object.entries(layerFilters(dash, data, state, panel)).map(([name, filter]) => [name, { filter, rows: keep(data[name].rows, filter) }]));
}

/** A dataset's own filter: its rail (without its pick on `unpick`, for a picker panel), and the selections made on it
    (except one panel's). */
export function ownFilter(dash, data, state, dataset, panelKey = null, { unpick = null } = {}) {
  const rail = state.rail && state.rail[dataset];
  const parts = [unpick ? unpicked(dash, data, dataset, rail, unpick) : rail];
  for (const [key, s] of Object.entries(state.select || {})) {
    if (key === panelKey || s.dataset !== dataset || !s.values || !s.values.length) continue;
    const list = ((data[dataset] && data[dataset].properties && data[dataset].properties[s.property]) || {}).type === 'list';
    parts.push(inClause(s.property, s.values, { list }));
  }
  return and(parts);
}

/** The span the dashboard's clock plays (CONTRACT §25; sim2real gap #1): [min, max] of `clock.time` (default `t`) over
    the rows of `clock.data` that pass the filter a panel on that dataset gets with every selection applied — its rail,
    the selections and the links (panelFilter with no panel of its own: the clock is no panel, so no selection is its
    own). null when no such row has a numeric time; undefined when the dashboard names no clock dataset (the cards'
    extents span the clock then). WHY the filtered rows: a picked 4.5 s run played on the 36 s staircase's clock.
    `filter` may be handed in when the caller has it already. */
export function clockSpan(dash, data, state, filter = undefined) {
  const c = dash && dash.clock;
  const name = c && c.data;
  const ds = name && data ? data[name] : null;
  if (!ds) return undefined;
  const prop = c.time || 't';
  const f = filter === undefined ? panelFilter(dash, data, state, name, null) : filter;
  let test = null;
  try { test = f === undefined ? null : compileFilters(f); } catch { test = null; } // a bad expression keeps every row, as keep() does
  let lo = Infinity, hi = -Infinity;
  for (const r of ds.rows) {
    if (test && !test(r)) continue;
    const v = cellValue(r[prop]);
    if (typeof v === 'number' && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }
  return lo <= hi ? [lo, hi] : null;
}

/** Rows passing a filter (a bad expression keeps every row and is reported by the panel that draws it). */
export function keep(rows, filter) {
  if (filter === undefined) return rows;
  let test = null;
  try { test = compileFilters(filter); } catch { return rows; }
  return test ? rows.filter(test) : rows;
}

// ------------------------------------------------------------------ roll-ups

/** Children by parent id, for a dataset with `tree: {parent}`. */
function childrenOf(rows, parent) {
  const kids = new Map();
  for (const r of rows) {
    const p = cellValue(r[parent]);
    if (isEmpty(p)) continue;
    if (!kids.has(String(p))) kids.set(String(p), []);
    kids.get(String(p)).push(String(r.id));
  }
  return kids;
}

/** A row's id and every descendant's (a cycle is cut where it closes). */
export function subtree(id, kids) {
  const out = [];
  const seen = new Set();
  const walk = (x) => { if (seen.has(x)) return; seen.add(x); out.push(x); for (const k of kids.get(x) || []) walk(k); };
  walk(String(id));
  return out;
}

/** Σproperty / Σper over the rows that have both (the kpi view's rule), else a Bases summary. */
export function summaryOf(rows, { property, summary = 'Sum', per }) {
  if (summary === 'Ratio') {
    let num = 0, den = 0, n = 0;
    for (const r of rows) {
      const a = cellValue(r[property]), b = cellValue(r[per]);
      if (isNum(a) && isNum(b)) { num += a; den += b; n++; }
    }
    return n && den ? num / den : null;
  }
  if (summary === 'Count') return rows.length;
  return summarize(rows.map((r) => r[property]), summary);
}

/** The newest row per group: `latest: {by, per}` keeps, for each (link key, per…) the row with the largest `by`. */
export function latestRows(rows, key, latest) {
  if (!latest || !latest.by) return rows;
  const per = [].concat(latest.per || []);
  const best = new Map();
  for (const r of rows) {
    const k = JSON.stringify([cellValue(r[key]), ...per.map((p) => cellValue(r[p]))]);
    const cur = best.get(k);
    if (!cur || String(cellValue(r[latest.by]) ?? '') > String(cellValue(cur[latest.by]) ?? '')) best.set(k, r);
  }
  return rows.filter((r) => best.get(JSON.stringify([cellValue(r[key]), ...per.map((p) => cellValue(r[p]))])) === r);
}

// a live dataset (core live/store.js isLiveDataset, by its shape: this module imports no live code)
const isLive = (d) => !!(d && d.live === true && typeof d.snapshot === 'function');
const ROLLUP_ROWS = 2000;   // an append dataset's newest rows a roll-up reads at t: what its own `rows` hands a dashboard

/** The rows a roll-up reads of a dataset (CONTRACT §17 addendum): a file's rows; a live dataset's as of t, each key's
    newest version at t (every key) or an append dataset's newest 2,000 rows at or before t, in time order; with no t, a
    live dataset's newest rows, as before. WHY at t: a roll-up on live data read its newest rows, so it could not rewind
    with the clock (RobotDx PEP 0001 §18.4, ask 2). */
export function rowsAsOf(ds, t) {
  if (!ds) return [];
  if (!isLive(ds) || typeof t !== 'number' || !Number.isFinite(t)) return ds.rows || [];
  if (ds.keyed) return ds.snapshot(t, { at: 'all', limit: Infinity });
  return ds.snapshot(t, { at: 'all', limit: ROLLUP_ROWS }).reverse();
}

/** The roll-ups that read live data (their dataset or their source is live): what the dashboard computes again as its
    clock moves (live.js watchRollups). */
export function liveRollups(dash, data) {
  return Object.values(dash.datasets).filter((d) => d.rollup && data[d.name] && data[d.rollup.from] && (isLive(data[d.name]) || isLive(data[d.rollup.from]))).map((d) => d.name);
}

/** Compute every roll-up of the dashboard into its dataset's rows (in place: the panels hold the same row objects)
    and properties. Returns {<dataset>: {<column>: {<row id>: cell}}} for tests. `t`: the clock's time, which a roll-up
    on live data reads its rows at (rowsAsOf), writing its cells onto the target's rows at t (a live tree's versions
    then); `only`: the names of the roll-ups to compute (default every one). */
export function applyRollups(dash, data, state, { t, only = null } = {}) {
  const out = {};
  for (const d of Object.values(dash.datasets)) {
    const spec = d.rollup;
    if (!spec || !data[d.name] || !data[spec.from]) continue;
    if (only && !only.includes(d.name)) continue;
    const target = data[d.name];
    const path = linkPath(dash.links, spec.from, d.name);
    if (!path || path.length !== 1) continue; // the checker reports it: a roll-up needs one direct link
    const fk = path[0].from.col, key = path[0].to.col;
    const source = data[spec.from];
    const targetRows = rowsAsOf(target, t);
    const fromRows = latestRows(keep(rowsAsOf(source, t), ownFilter(dash, data, state, spec.from)), fk, spec.latest);
    const byKey = new Map();
    for (const r of fromRows) {
      const v = cellValue(r[fk]);
      for (const x of Array.isArray(v) ? v : [v]) {
        if (isEmpty(x)) continue;
        if (!byKey.has(String(x))) byKey.set(String(x), []);
        byKey.get(String(x)).push(r);
      }
    }
    const parent = (d.tree && d.tree.parent) || null;
    const kids = parent ? kidsByKey(childrenOf(targetRows, parent), targetRows, key) : new Map();
    const fromLabel = (source.title || spec.from).toLowerCase();
    const result = (out[d.name] = {});
    for (const [col, v] of Object.entries(spec.values || {})) {
      const meta = target.properties[col] || {};
      target.properties[col] = { type: 'number', ...meta, derived: meta.derived || describe(v, spec, parent), readOnly: true, basis: 'derived' };
      result[col] = {};
    }
    for (const row of targetRows) {
      const ids = parent ? subtree(cellValue(row[key]) ?? row.id, kids) : [String(cellValue(row[key]))];
      const rows = ids.flatMap((id) => byKey.get(id) || []);
      const below = ids.length - 1;
      for (const [col, v] of Object.entries(spec.values || {})) {
        const value = rows.length ? summaryOf(rows, v) : null;
        const how = `${v.summary === 'Ratio' ? `Σ ${v.property} / Σ ${v.per}` : `${v.summary || 'Sum'} of ${v.property}`} over ${rows.length} ${spec.latest ? 'newest ' : ''}${fromLabel.includes('run') ? 'runs' : 'rows'}${parent ? ` of this row and its ${below} ${below === 1 ? 'child' : 'children'}` : ''} · from rows`;
        const cell = value === null || value === undefined
          ? { value: null, why: rows.length ? 'no value in those rows' : `no ${spec.from} rows` }
          : { value: v.summary === 'Ratio' ? Math.round(value * 10000) / 10000 : value, basis: 'derived', n: rows.length, note: how, source: `roll-up of ${spec.from}` };
        row[col] = cell;
        result[col][row.id] = cell;
      }
    }
  }
  return out;
}

// a tree keyed by `key` (usually id): map the parent ids, which name rows by id, onto key values
function kidsByKey(kids, rows, key) {
  if (key === 'id') return kids;
  const keyOf = new Map(rows.map((r) => [String(r.id), String(cellValue(r[key]))]));
  const out = new Map();
  for (const [p, list] of kids) out.set(keyOf.get(p) ?? p, list.map((x) => keyOf.get(x) ?? x));
  return out;
}

function describe(v, spec, parent) {
  const what = v.summary === 'Ratio' ? `Σ ${v.property} / Σ ${v.per}` : `${v.summary || 'Sum'} of ${v.property}`;
  return `${what} over ${spec.latest ? `the newest ${spec.from} row per ${[].concat(spec.latest.per || []).join(', ') || 'key'}` : `the ${spec.from} rows`}${parent ? ', through every child' : ''} (a dashboard roll-up)`;
}

// ------------------------------------------------------------------ the URL

/** Selections, tabs and hidden series in the hash: s.<panel>=<property>:<v1>,<v2>, p.<panel>=<view slug> and
    l.<panel>=<name>,<name> (l.<scope>.<panel> with several dashboards on a page; `scope` is the clock's key, false keeps
    the legend out of the URL: core's legend.js). Values are URI-encoded one by one, so a comma inside a value survives.
    A panel with a preset (CONTRACT §33) and no selection is written s.<panel>= (empty): the reader cleared it, and a
    reload must not bring the preset back. */
export function writeHash(hash, state, panels, scope = null) {
  const h = new URLSearchParams(hash);
  for (const k of [...h.keys()]) if (/^[sp]\./.test(k)) h.delete(k);
  for (const [key, s] of Object.entries(state.select || {})) {
    if (s.values && s.values.length) h.set(`s.${key}`, `${s.property}:${s.values.map((v) => encodeURIComponent(typeof v === 'number' ? `#${v}` : String(v))).join(',')}`);
  }
  for (const p of panels) if (p.preset && !p.picks && !h.has(`s.${p.key}`)) h.set(`s.${p.key}`, '');
  for (const p of panels) if (state.tabs && state.tabs[p.key] && p.views.length > 1 && state.tabs[p.key] !== slug(p.views[0].name)) h.set(`p.${p.key}`, state.tabs[p.key]);
  writeLegendParams(h, state.legend || {}, panels.map((p) => p.key), scope);
  return h;
}

/** The hash's selections, tabs and hidden series (writeHash's form); `cleared`: the panels whose s.<panel>= is present
    and names no value (a preset the reader cleared, CONTRACT §33). */
export function readHash(hash, panels, scope = null) {
  const h = new URLSearchParams(hash);
  const select = {}, tabs = {}, cleared = [];
  for (const p of panels) {
    const s = h.get(`s.${p.key}`);
    if (s && s.includes(':')) {
      const i = s.indexOf(':');
      const values = s.slice(i + 1).split(',').filter((x) => x !== '').map((x) => { const v = decodeURIComponent(x); return /^#-?\d/.test(v) ? Number(v.slice(1)) : v; });
      if (values.length) select[p.key] = { dataset: p.dataset, property: s.slice(0, i), values };
      else cleared.push(p.key);
    } else if (s !== null) cleared.push(p.key);
    const t = h.get(`p.${p.key}`);
    if (t) tabs[p.key] = t;
  }
  return { select, tabs, legend: readLegendParams(h, panels.map((p) => p.key), scope), cleared };
}

// ------------------------------------------------------------------ arranging (docs/peps/0005-dashboard-cards.md §6)

/** Place panels in reading order on a grid of `columns` (what CSS grid does with spans): [{key, x, y, w, h}]. */
export function packPanels(items, columns) {
  const tops = new Array(columns).fill(0);
  let x = 0, rowTop = 0, rowBottom = 0;
  const out = [];
  for (const it of items) {
    const w = Math.max(1, Math.min(columns, it.w || columns));
    if (x + w > columns) { x = 0; rowTop = rowBottom; }
    out.push({ ...it, x, y: rowTop, w, h: it.h || 1 });
    rowBottom = Math.max(rowBottom, rowTop + (it.h || 1));
    x += w;
    for (let i = 0; i < columns; i++) tops[i] = rowBottom;
  }
  return out;
}

/** Grid positions back to reading order: top to bottom, then left to right. */
export function readingOrder(nodes) {
  return [...nodes].sort((a, b) => a.y - b.y || a.x - b.x);
}

/** A layout: block re-ordered and re-sized by `arr` [{key, w, h}] (keys are the panels' keys); panels it does not name
    keep their place at the end. Returns a new layout object (the file's other keys are kept). */
export function arrangeLayout(layout, panels, arr) {
  const byKey = new Map(panels.map((p) => [p.key, p]));
  const src = (layout && layout.panels) || [];
  const used = new Set();
  const out = [];
  for (const a of arr) {
    const p = byKey.get(a.key);
    if (!p || !src[p.i]) continue;
    used.add(p.i);
    const entry = { ...src[p.i] };
    if (a.w) entry.w = a.w;
    if (a.h && p.text === null) entry.h = a.h;
    out.push(entry);
  }
  src.forEach((e, i) => { if (!used.has(i)) out.push(e); });
  return { ...(layout || {}), panels: out };
}

/** The .base text with its top-level layout: block replaced by `layout` (the rest of the file byte for byte). */
export function layoutText(text, layout, stringify) {
  const yaml = stringify({ layout }).replace(/\n+$/, '\n');
  const lines = String(text).split('\n');
  const start = lines.findIndex((l) => /^layout:/.test(l));
  if (start < 0) return `${String(text).replace(/\n*$/, '\n')}${yaml}`;
  let end = start + 1;
  while (end < lines.length && (lines[end] === '' || /^[\s#]/.test(lines[end]))) end++;
  // keep trailing blank lines / comments that belong to the next block
  while (end > start + 1 && (lines[end - 1] === '' || /^#/.test(lines[end - 1]))) end--;
  return [...lines.slice(0, start), ...yaml.replace(/\n$/, '').split('\n'), ...lines.slice(end)].join('\n');
}
