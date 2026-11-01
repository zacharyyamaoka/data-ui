/* One filter model, two editors (docs/SPEC.md §6).

   The stored filter is an Obsidian Bases `filters` value: an expression string, or {and | or | not: [...]} of them.
   The Obsidian-style builder edits any tree. The McMaster-style left rail edits only its facet-shaped part, the
   "facet normal form":

     {and: [clause, ...]} where each clause is one of
       p == v                         one value of p              (rail: one ticked value)
       {or: [p == v1, p == v2, ...]}  any of these values of p    (rail: several ticked values)
       p.contains(v), or an {or:} of them, for a list-valued p (buses: ["can", "rs485"])
       p >= a, p > a, p <= b, p < b   a numeric range             (rail: the min and max boxes)
       !p.isEmpty()                   p has a value               (rail: "has p")

   Anything else (p != v, an || inside one string, a top-level or/not, a second value clause on the same p) stays in
   `rest`, verbatim and in order. The rail shows "+N custom filters · Edit" for it and never drops it.

   One string of clauses joined by && at its top level (`run_set == "held-out" && device == "J3 elbow"`) is read as
   those clauses (conjuncts below): each one the rail can draw is the rail's, the others stay custom one by one, and a
   string none of whose clauses the rail can draw stays whole, as written. WHY (sim2real gap #9, 2026-10-28): the
   string read as one custom clause, so the rail counted every facet under both picks and a picker listed only the
   value already chosen. `a && b` and {and: [a, b]} mean the same rows, so the rail writes the latter back.

   The standard filter kinds (docs/CONTRACT.md §7, amendment 2026-10-26 (filters)) widen the normal form, but only
   when toRail is given the rail's config (railConfig(specs)), because what the rail can draw depends on its facets:
       {not: [p == v1, p == v2]}            none of these values of p     (a values facet with exclude: true)
       p >= "2026-10-19", p < "2026-09-26"  a date range (ISO text)       (date)
       {or: [!a.isEmpty(), !b.isEmpty()]}   a or b has a value            (has, match any)
       p.contains("x"), {or: [p.contains("x"), q.contains("x")]}, p.startsWith("x")    (search over p, q)
   and with a config a clause no facet of the rail can draw (a value of a property the rail has no facet for, two
   values where the only facet is a single choice, a max bound under a "Level ≥ N" rating) stays custom too. Without a
   config, toRail reads exactly the first form, as it always has.

   WHY a projection and not two filter models: one stored tree means the table, the cards and the chart all see the
   same rows, and a link or a saved view means the same thing whichever editor made it. The rail is a lossless view
   of part of the tree, the way a form is a view of part of a record.

   Pure functions. Moved here from tools/facets.mjs (the SPEC's proof), which now re-exports it.
   tools/facets.test.mjs proves the round trip and, when the table lane's grammar.js and its actuators dataset are
   on disk, that rail selections pick exactly the rows the lane's own Bases evaluator picks; tests/unit/facets.test.mjs
   proves every kind both ways, their counts and their URL. */

import { cellValue, compileFilters, binsOf, effectiveView, bucketStart, nextBucket } from './grammar.js';

const STR = String.raw`"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'`;
// WHY the bracket form: vault notes use hyphenated properties, written note["vibe-status"] in Bases (Zach's own
// Projects/Obsidian Vibe Kanban/Kanban cards.base does).
const PROP = String.raw`(?:(?:note\.)?(?<pid>[A-Za-z_][A-Za-z0-9_]*)|note\[\s*(?<pq>${STR})\s*\])`;
const NUM = String.raw`-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?`;
const LIT = `${STR}|${NUM}|true|false`;

const EQ = new RegExp(String.raw`^\s*${PROP}\s*==\s*(?<lit>${LIT})\s*$`);
const RANGE = new RegExp(String.raw`^\s*${PROP}\s*(?<op>>=|>|<=|<)\s*(?<num>${NUM})\s*$`);
const RANGE_TEXT = new RegExp(String.raw`^\s*${PROP}\s*(?<op>>=|>|<=|<)\s*(?<str>${STR})\s*$`);
const CONTAINS = new RegExp(String.raw`^\s*${PROP}\.contains\(\s*(?<lit>${LIT})\s*\)\s*$`);
const STARTS = new RegExp(String.raw`^\s*${PROP}\.startsWith\(\s*(?<lit>${STR})\s*\)\s*$`);
const HAS = new RegExp(String.raw`^\s*!\s*${PROP}\.isEmpty\(\)\s*$`);

function literal(text) {
  if (text === 'true') return true;
  if (text === 'false') return false;
  if (text[0] === '"' || text[0] === "'") return text.slice(1, -1).replace(/\\(.)/g, '$1');
  return Number(text);
}

const propertyOf = (groups) => (groups.pid !== undefined ? groups.pid : literal(groups.pq));

/** How a property is written in an expression: bare when it is an identifier, note["…"] otherwise. */
export function ref(property) {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(property) ? property : `note[${JSON.stringify(property)}]`;
}

/** One expression string as a facet clause, or null when the rail cannot show it. `wide` (the rail's config mode)
    also reads a text bound (a date) and .startsWith(). */
export function parseClause(source, { wide = false } = {}) {
  if (typeof source !== 'string') return null;
  let m;
  if ((m = EQ.exec(source))) return { property: propertyOf(m.groups), kind: 'eq', value: literal(m.groups.lit) };
  if ((m = CONTAINS.exec(source))) return { property: propertyOf(m.groups), kind: 'contains', value: literal(m.groups.lit) };
  if ((m = RANGE.exec(source))) {
    const low = m.groups.op[0] === '>';
    return { property: propertyOf(m.groups), kind: low ? 'min' : 'max', value: Number(m.groups.num), open: m.groups.op.length === 1 };
  }
  if ((m = HAS.exec(source))) return { property: propertyOf(m.groups), kind: 'has' };
  if (!wide) return null;
  if ((m = RANGE_TEXT.exec(source))) {
    const low = m.groups.op[0] === '>';
    return { property: propertyOf(m.groups), kind: low ? 'min' : 'max', value: literal(m.groups.str), open: m.groups.op.length === 1 };
  }
  if ((m = STARTS.exec(source))) return { property: propertyOf(m.groups), kind: 'starts', value: literal(m.groups.lit) };
  return null;
}

// ------------------------------------------------------------------ the kinds

/** Every facet kind (`facets: [{property, as: <kind>}]`), each with the one site it copies (docs/CONTRACT.md §7). */
export const KINDS = {
  values: 'checkbox list with counts, "show N more", in-list search (Algolia refinementList)',
  select: 'one value or Any (Algolia menu / menuSelect)',
  toggle: 'one value on or off, "In stock only" (Algolia toggleRefinement)',
  has: 'has a value, any of / all of (Datasette facet on null, Tableau "Special")',
  range: 'min and max boxes (Algolia rangeInput; Zillow min/max dropdowns with choices:)',
  slider: 'a two-thumb slider (Algolia rangeSlider)',
  'slider-histogram': 'a histogram above a two-thumb slider (Airbnb price filter)',
  buckets: 'preset ranges as chips (Amazon price bands, Algolia numericMenu)',
  rating: '"N & up" stars (Amazon, Algolia ratingMenu)',
  'min-level': '"Level ≥ N" steps (Algolia ratingMenu, drawn as steps)',
  date: 'a date range with relative presets and "older than" (Tableau relative dates)',
  chips: 'tag chips for a list property (Linear labels)',
  swatch: 'colour or logo swatches with counts (Shopify Search & Discovery swatches)',
  gallery: 'picture tiles in columns (McMaster-Carr "Drive Style")',
  'picture-list': 'a small drawing beside each value (McMaster-Carr "Threading")',
  grid: 'compact multi-column values, no checkboxes (McMaster-Carr "Thread Pitch")',
  listbox: 'a multi-select list (Digi-Key parametric columns)',
  tree: 'a hierarchical menu over levels (Algolia hierarchicalMenu)',
  search: 'a text box over chosen properties (Algolia searchBox; Tableau wildcard match)',
  popular: 'named shortcut filters with counts (Booking.com "Popular filters")',
  current: 'the current refinements as removable chips, and Clear all (Algolia currentRefinements + clearRefinements)',
  nav: 'one row per group of the view, picked alone, a click again gives every group back (McMaster-Carr "Choose a Category")',
};
const MULTI = new Set(['values', 'chips', 'swatch', 'gallery', 'picture-list', 'grid', 'listbox']);
const SINGLE = new Set(['select', 'toggle', 'tree']);
const BOUNDS = new Set(['range', 'slider', 'slider-histogram', 'buckets', 'date']);
const RATING = new Set(['rating', 'min-level']);
export const VALUE_KINDS = new Set([...MULTI, ...SINGLE]);
export const NUMBER_KINDS = new Set(['range', 'slider', 'slider-histogram', 'buckets', 'rating', 'min-level']);

const asList = (x) => (x === undefined || x === null ? [] : Array.isArray(x) ? x : [x]);

/** The rail of a view: the view's own `facets:` when it has one (a recipe), else the file's, else the fields whose
    schema says `facet:`. Each entry is {key, property, as, label, prop, options…, unknown?}; an entry the data cannot
    serve is left out, an unknown kind is drawn as values and says so. */
export function facetSpecs(base, view, props) {
  const fromView = view && Array.isArray(view.facets);
  const list = fromView ? view.facets : base && base.facets && base.facets.length ? base.facets : Object.keys(props).filter((p) => props[p].facet && props[p].facet !== 'none');
  const out = [];
  list.forEach((entry, i) => {
    const f = typeof entry === 'string' ? { property: entry } : entry && typeof entry === 'object' ? { ...entry } : null;
    if (!f) return;
    let as = f.as;
    const first = f.property || (f.levels && f.levels[0]) || (f.properties && f.properties[0]);
    const p = first ? props[first] : null;
    if (!as) as = p && p.facet && p.facet !== 'none' ? p.facet : p && p.type === 'number' && !p.labels ? 'range' : 'values';
    let unknown = null;
    if (!KINDS[as]) { unknown = as; as = 'values'; }
    if (as === 'current') { out.push({ ...f, key: `@current${i}`, as, label: f.label || 'Current filters' }); return; }
    if (as === 'popular') {
      const options = asList(f.options).map((o) => (typeof o === 'string' ? { label: o, filter: o } : o)).filter((o) => o && typeof o.filter === 'string');
      out.push({ ...f, key: `@popular${i}`, as, label: f.label || 'Popular filters', options });
      return;
    }
    if (as === 'nav') {
      // WHY the view's own level (docs/CONTRACT.md §20): Zach, 2026-10-27, "The left bar should work more like a filter,
      // actually, instead of going to the position on the screen. That is how McMaster does it! If you unclick it, all
      // the different areas come back." With no property (or `follow: groupBy`) it lists the groups the view draws now,
      // so switching the grouping switches the rail
      const level = navLevel(f, view);
      const np = level && props[level.property];
      if (!np) return;
      const key = out.some((x) => x.key === level.property) ? `${level.property}@${i}` : level.property;
      out.push({ ...f, key, property: level.property, as, label: f.label || `Choose a ${np.label}`, prop: np, level });
      return;
    }
    if (!p) return;
    // WHY a key apart from the property: two facets may stand over one property (brand as logos and as a list);
    // they share its state in the filter but each draws from its own counts
    const key = out.some((x) => x.key === first) ? `${first}@${i}` : first;
    const spec = { ...f, key, property: first, as, label: f.label || p.label, prop: p };
    if (as === 'tree') spec.levels = asList(f.levels || f.property).filter((l) => props[l]);
    if (as === 'has' || as === 'search') spec.properties = asList(f.properties || f.property).filter((l) => props[l]);
    if (unknown) spec.unknown = unknown;
    out.push(spec);
  });
  return out;
}

/** The group level a nav facet lists: the view's effective groupBy when it names no property or `follow: groupBy`;
    else its property, with the view's own level when that groups the same property (its bins or grain). */
function navLevel(f, view) {
  const own = view ? effectiveView(view).groupBy : null;
  if (f.property && f.follow !== 'groupBy') return own && own.property === f.property ? own : { property: f.property };
  return own && own.property ? own : null;
}

/** What a rail can draw, for toRail: which kinds stand over each property. */
export function railConfig(specs) {
  const by = new Map();
  const add = (p, k) => { if (!by.has(p)) by.set(p, new Set()); by.get(p).add(k); };
  const cfg = { by, exclude: new Set(), on: new Map(), has: [], search: [], popular: [] };
  for (const s of specs) {
    if (s.as === 'current') continue;
    if (s.as === 'popular') {
      for (const o of s.options) { const c = parseClause(o.filter, { wide: true }); if (c) cfg.popular.push(c); }
      continue;
    }
    if (s.as === 'tree') { for (const l of s.levels) add(l, 'tree'); continue; }
    if (s.as === 'has') { cfg.has.push(s.properties); for (const l of s.properties) add(l, 'has'); continue; }
    if (s.as === 'search') { cfg.search.push({ properties: s.properties, match: s.match === 'startsWith' ? 'startsWith' : 'contains' }); continue; }
    add(s.property, s.as);
    if (s.exclude) cfg.exclude.add(s.property);
    if (s.as === 'toggle') cfg.on.set(s.property, s.value === undefined ? true : s.value);
  }
  return cfg;
}

/** The union of every rail in a file (the top-level one and each view's), so the URL can carry any of them. A nav
    facet that follows the grouping stands over every grouping's property, and a view's tiles (and its second level)
    are values a tile's drill writes (docs/CONTRACT.md §20), so ?bbox_volume_ml=250..<1000 or ?type_name=… reads back
    whichever grouping the page opens on. */
export function allSpecs(base, props) {
  const out = [...facetSpecs(base, null, props)];
  for (const v of (base && base.views) || []) if (v && Array.isArray(v.facets)) out.push(...facetSpecs(base, v, props));
  for (const v of (base && base.views) || []) {
    if (!v || typeof v !== 'object') continue;
    const ways = [v, ...(Array.isArray(v.groupings) ? v.groupings : []).filter((g) => g && g.id).map((g) => ({ ...v, grouping: g.id }))];
    for (const w of ways) {
      out.push(...facetSpecs(base, w, props).filter((s) => s.as === 'nav'));
      const e = effectiveView(w);
      if (e.tiles && typeof e.tiles === 'object') {
        for (const p of [e.tiles.property, e.subGroupBy && e.subGroupBy.property]) if (p && props[p]) out.push({ key: `@drill:${p}`, property: p, as: 'values', label: props[p].label, prop: props[p] });
      }
    }
  }
  return out;
}

// ------------------------------------------------------------------ tree -> rail

function place(facets, clauses) {
  const { property: p, kind } = clauses[0];
  const f = { ...(facets.get(p) || {}) };
  if (kind === 'eq' || kind === 'contains') {
    // WHY refuse a second value clause on p: "brand == A and brand == B" is an AND the rail cannot draw; it stays
    // in rest, so the stored meaning (no rows) survives.
    if (f.values) return false;
    f.values = clauses.map((c) => c.value);
    f.match = kind === 'contains' ? 'contains' : 'equals';
  } else if (kind === 'min') {
    if (f.min !== undefined) return false;
    f.min = clauses[0].value;
    if (clauses[0].open) f.minOpen = true;
  } else if (kind === 'max') {
    if (f.max !== undefined) return false;
    f.max = clauses[0].value;
    if (clauses[0].open) f.maxOpen = true;
  } else if (kind === 'has') {
    if (f.has) return false;
    f.has = true;
  } else return false;
  facets.set(p, f);
  return [[p, kind === 'eq' || kind === 'contains' ? 'values' : kind]];
}

const isOr = (node) => node && typeof node === 'object' && !Array.isArray(node) && Object.keys(node).length === 1 && Array.isArray(node.or);
const isNot = (node) => node && typeof node === 'object' && !Array.isArray(node) && Object.keys(node).length === 1 && Array.isArray(node.not);
const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

function searchOf(cfg, properties, match) {
  return cfg.search.find((s) => s.match === match && sameList(s.properties, properties));
}

function absorbWide(facets, node, cfg) {
  if (typeof node === 'string') {
    const c = parseClause(node, { wide: true });
    if (!c) return false;
    // a text search on one property: p.contains("x") where p has a search facet and no list of values to tick
    if ((c.kind === 'contains' || c.kind === 'starts') && typeof c.value === 'string') {
      const match = c.kind === 'starts' ? 'startsWith' : 'contains';
      const kinds = cfg.by.get(c.property);
      if (searchOf(cfg, [c.property], match) && !(kinds && [...kinds].some((k) => VALUE_KINDS.has(k)))) {
        const f = { ...(facets.get(c.property) || {}) };
        if (f.text !== undefined) return false;
        Object.assign(f, { text: c.value, textIn: [c.property] }, match === 'startsWith' ? { textMatch: 'startsWith' } : {});
        facets.set(c.property, f);
        return [[c.property, 'text']];
      }
    }
    if (c.kind === 'starts') return false;
    return place(facets, [c]);
  }
  if (isNot(node)) {
    const cs = node.not.map((x) => parseClause(x, { wide: true }));
    if (!cs.length || cs.some((c) => !c)) return false;
    const { property: p, kind } = cs[0];
    if ((kind !== 'eq' && kind !== 'contains') || !cs.every((c) => c.property === p && c.kind === kind)) return false;
    const f = { ...(facets.get(p) || {}) };
    if (f.exclude) return false;
    f.exclude = cs.map((c) => c.value);
    f.excludeMatch = kind === 'contains' ? 'contains' : 'equals';
    facets.set(p, f);
    return [[p, 'exclude']];
  }
  if (isOr(node)) {
    const cs = node.or.map((x) => parseClause(x, { wide: true }));
    if (!cs.length || cs.some((c) => !c)) return false;
    const props = cs.map((c) => c.property);
    if (cs.every((c) => c.kind === 'has') && new Set(props).size === props.length && props.length > 1) {
      const f = { ...(facets.get(props[0]) || {}) };
      if (f.hasAny) return false;
      f.hasAny = props;
      facets.set(props[0], f);
      return [[props[0], 'hasAny']];
    }
    if (cs.every((c) => (c.kind === 'contains' || c.kind === 'starts') && c.kind === cs[0].kind && typeof c.value === 'string' && c.value === cs[0].value) && new Set(props).size === props.length && props.length > 1) {
      const match = cs[0].kind === 'starts' ? 'startsWith' : 'contains';
      if (!searchOf(cfg, props, match)) return false;
      const f = { ...(facets.get(props[0]) || {}) };
      if (f.text !== undefined) return false;
      Object.assign(f, { text: cs[0].value, textIn: props }, match === 'startsWith' ? { textMatch: 'startsWith' } : {});
      facets.set(props[0], f);
      return [[props[0], 'text']];
    }
    const { property, kind } = cs[0];
    if (kind !== 'eq' && kind !== 'contains') return false;
    if (!cs.every((c) => c.property === property && c.kind === kind)) return false;
    return place(facets, cs);
  }
  return false;
}

function absorb(facets, node) {
  if (typeof node === 'string') {
    const clause = parseClause(node);
    return clause ? place(facets, [clause]) : false;
  }
  if (isOr(node)) {
    const clauses = node.or.map((x) => parseClause(x));
    if (!clauses.length || clauses.some((c) => !c)) return false;
    const { property, kind } = clauses[0];
    if (kind !== 'eq' && kind !== 'contains') return false;
    if (!clauses.every((c) => c.property === property && c.kind === kind)) return false;
    return place(facets, clauses);
  }
  return false;
}

const FIELDS = { values: ['values', 'match'], exclude: ['exclude', 'excludeMatch'], min: ['min', 'minOpen'], max: ['max', 'maxOpen'], has: ['has'], hasAny: ['hasAny'], text: ['text', 'textIn', 'textMatch'] };

function popularHas(cfg, p, kind, value, open) {
  return cfg.popular.some((c) => c.property === p && c.kind === kind && c.value === value && !!c.open === !!open);
}

/** Can some facet of the rail draw this part of p's state? */
function drawable(cfg, p, f, field) {
  const kinds = cfg.by.get(p) || new Set();
  const any = (set) => [...kinds].some((k) => set.has(k));
  switch (field) {
    case 'values': {
      if (any(MULTI)) return true;
      if (f.values.length !== 1) return false;
      if (kinds.has('select') || kinds.has('tree') || kinds.has('nav')) return true;
      if (kinds.has('toggle') && f.values[0] === cfg.on.get(p)) return true;
      return popularHas(cfg, p, f.match === 'contains' ? 'contains' : 'eq', f.values[0]);
    }
    case 'exclude': return cfg.exclude.has(p);
    case 'min': case 'max':
      if (any(BOUNDS) || kinds.has('nav')) return true; // a nav row of a binned (or dated) level is its range
      if (field === 'min' && any(RATING) && !f.minOpen && f.max === undefined) return true;
      return popularHas(cfg, p, field, f[field], f[field + 'Open']) && (field === 'min' ? f.max === undefined : f.min === undefined);
    case 'has': return kinds.has('has') || popularHas(cfg, p, 'has');
    case 'hasAny': return cfg.has.some((g) => f.hasAny.every((x) => g.includes(x)));
    case 'text': return !!searchOf(cfg, f.textIn, f.textMatch === 'startsWith' ? 'startsWith' : 'contains');
    default: return false;
  }
}

/** The index of the bracket closing the one at `at` (quotes skipped), or -1 when it never closes. */
function closing(s, at) {
  let depth = 0;
  for (let i = at; i < s.length; i++) {
    const ch = s[i];
    if (ch === '"' || ch === "'") { i = quoteEnd(s, i); if (i < 0) return -1; continue; }
    if (ch === '(' || ch === '[') depth++;
    else if ((ch === ')' || ch === ']') && --depth === 0) return i;
  }
  return -1;
}

/** The index of the quote closing the string that opens at `at` (a backslash escapes), or -1. */
function quoteEnd(s, at) {
  for (let i = at + 1; i < s.length; i++) {
    if (s[i] === '\\') i++;
    else if (s[i] === s[at]) return i;
  }
  return -1;
}

/** One expression string's clauses joined by && at its top level (outside quotes, brackets and parentheses), each
    trimmed, a string wrapped whole in ( ) read inside them, nested the same way. [text] as it is when there is no such
    &&, when a || stands at the top level (it binds looser than &&, so a split would change the meaning), or when the
    string does not scan (an open quote or bracket, an empty side of an &&): the evaluator reports those, never the rail. */
export function conjuncts(text) {
  if (typeof text !== 'string') return [text];
  let s = text.trim();
  while (s[0] === '(' && closing(s, 0) === s.length - 1) s = s.slice(1, -1).trim();
  const cuts = [];
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '"' || ch === "'") { i = quoteEnd(s, i); if (i < 0) return [text]; continue; }
    if (ch === '(' || ch === '[') depth++;
    else if (ch === ')' || ch === ']') { if (--depth < 0) return [text]; }
    else if (depth === 0 && s.startsWith('||', i)) return [text];
    else if (depth === 0 && s.startsWith('&&', i)) { cuts.push(i); i++; }
  }
  if (depth !== 0 || !cuts.length) return [text];
  const parts = cuts.map((c, k) => s.slice(k ? cuts[k - 1] + 2 : 0, c).trim()).concat(s.slice(cuts[cuts.length - 1] + 2).trim());
  if (parts.some((p) => !p)) return [text];
  return parts.flatMap(conjuncts);
}

/** A Bases filters value -> {facets: {property: {values?, match?, exclude?, excludeMatch?, min?, minOpen?, max?,
    maxOpen?, has?, hasAny?, text?, textIn?, textMatch?}}, rest: [...]}. With `config` (railConfig(specs)) it reads
    the wide form and keeps custom whatever this rail cannot draw; without, the original normal form only. A string of
    && clauses is read clause by clause (conjuncts); one none of whose clauses the rail draws goes back whole. */
export function toRail(filters, config = null) {
  const facets = new Map();
  const rest = [];
  if (filters === undefined || filters === null || filters === '') return { facets: {}, rest };
  let top;
  if (typeof filters === 'string') top = [filters];
  else if (filters && typeof filters === 'object' && Object.keys(filters).length === 1 && Array.isArray(filters.and)) top = filters.and;
  else return { facets: {}, rest: [filters] }; // a top-level or / not: all of it is custom
  // each node is one clause: a string's && clauses apart, `from` the top-level node it came from
  const nodes = top.flatMap((node, from) => { const parts = conjuncts(node); return parts.map((part) => ({ node: part, from, whole: node, of: parts.length })); });
  const owners = [];
  nodes.forEach(({ node }, i) => {
    const got = config ? absorbWide(facets, node, config) : absorb(facets, node);
    if (!got) rest.push([i, node]);
    else for (const [p, field] of got) owners.push({ i, node, p, field });
  });
  if (config) {
    // WHY after reading all of it: whether a ticked value is drawable can depend on its neighbours (a second value
    // under a single-choice facet), so the decision is made on p's whole state, then the clause goes back verbatim
    for (const o of owners) {
      const f = facets.get(o.p);
      if (!f || drawable(config, o.p, f, o.field)) continue;
      for (const k of FIELDS[o.field === 'min' || o.field === 'max' ? o.field : o.field]) delete f[k];
      if (!Object.keys(f).length) facets.delete(o.p);
      rest.push([o.i, o.node]);
    }
    rest.sort((a, b) => a[0] - b[0]);
  }
  // a string of && clauses none of which the rail drew stays one custom clause, written as it was
  const custom = new Set(rest.map(([i]) => i));
  const out = [];
  for (const [i, node] of rest) {
    const n = nodes[i];
    if (n.of > 1 && nodes.every((m, j) => m.from !== n.from || custom.has(j))) {
      if (nodes.findIndex((m) => m.from === n.from) === i) out.push(n.whole);
      continue;
    }
    out.push(node);
  }
  return { facets: Object.fromEntries(facets), rest: out };
}

function lit(v) {
  return typeof v === 'string' ? JSON.stringify(v) : String(v);
}

/** The rail's state (and any custom clauses) -> the canonical Bases filters tree, or undefined for "every row". */
export function fromRail(facets, rest = []) {
  const and = [];
  for (const [property, f] of Object.entries(facets)) {
    const p = ref(property);
    if (f.values && f.values.length) {
      const one = (v) => (f.match === 'contains' ? `${p}.contains(${lit(v)})` : `${p} == ${lit(v)}`);
      and.push(f.values.length === 1 ? one(f.values[0]) : { or: f.values.map(one) });
    }
    if (f.exclude && f.exclude.length) and.push({ not: f.exclude.map((v) => (f.excludeMatch === 'contains' ? `${p}.contains(${lit(v)})` : `${p} == ${lit(v)}`)) });
    if (f.min !== undefined && f.min !== null) and.push(`${p} ${f.minOpen ? '>' : '>='} ${lit(f.min)}`);
    if (f.max !== undefined && f.max !== null) and.push(`${p} ${f.maxOpen ? '<' : '<='} ${lit(f.max)}`);
    if (f.has) and.push(`!${p}.isEmpty()`);
    if (f.hasAny && f.hasAny.length) and.push({ or: f.hasAny.map((x) => `!${ref(x)}.isEmpty()`) });
    if (f.text !== undefined && f.text !== '') {
      const one = (x) => `${ref(x)}.${f.textMatch === 'startsWith' ? 'startsWith' : 'contains'}(${JSON.stringify(String(f.text))})`;
      const ins = f.textIn && f.textIn.length ? f.textIn : [property];
      and.push(ins.length === 1 ? one(ins[0]) : { or: ins.map(one) });
    }
  }
  and.push(...rest);
  return and.length ? { and } : undefined;
}

// ------------------------------------------------------------------ matching rows (the rail's own semantics)
// These follow the table lane's evaluator (design/tables-2026-10-25/views/src/grammar.js): == compares numbers as
// numbers and anything else as text; .contains() is list membership on a list and a case-insensitive substring on
// text; a range never matches an empty value.

const isEmpty = (v) => v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

function equals(a, b) {
  if (isEmpty(a) && isEmpty(b)) return true;
  if (isEmpty(a) || isEmpty(b)) return false;
  return isNum(a) && isNum(b) ? a === b : String(a) === String(b);
}

function contains(v, x) {
  if (Array.isArray(v)) return v.map(String).includes(String(x));
  return !isEmpty(v) && String(v).toLowerCase().includes(String(x).toLowerCase());
}

// a text bound (a date) compares as grammar.js compares: numbers as numbers, anything else as text
function bound(v, b, op) {
  if (typeof b !== 'string') {
    if (!isNum(v)) return false;
    return op === '>' ? v > b : op === '>=' ? v >= b : op === '<' ? v < b : v <= b;
  }
  if (isEmpty(v)) return false;
  const [x, y] = isNum(v) && isNum(b) ? [v, b] : [String(v), b];
  return op === '>' ? x > y : op === '>=' ? x >= y : op === '<' ? x < y : x <= y;
}

export function matchesFacet(row, p, f) {
  const v = cellValue(row[p]);
  if (f.values && f.values.length) {
    const hit = f.match === 'contains' ? f.values.some((x) => contains(v, x)) : f.values.some((x) => equals(v, x));
    if (!hit) return false;
  }
  if (f.exclude && f.exclude.length && (f.excludeMatch === 'contains' ? f.exclude.some((x) => contains(v, x)) : f.exclude.some((x) => equals(v, x)))) return false;
  if (f.min !== undefined && f.min !== null && !bound(v, f.min, f.minOpen ? '>' : '>=')) return false;
  if (f.max !== undefined && f.max !== null && !bound(v, f.max, f.maxOpen ? '<' : '<=')) return false;
  if (f.has && isEmpty(v)) return false;
  if (f.hasAny && f.hasAny.length && !f.hasAny.some((x) => !isEmpty(cellValue(row[x])))) return false;
  if (f.text !== undefined && f.text !== '') {
    const t = String(f.text);
    const ins = f.textIn && f.textIn.length ? f.textIn : [p];
    const hit = ins.some((x) => {
      const w = cellValue(row[x]);
      return f.textMatch === 'startsWith' ? !isEmpty(w) && String(w).toLowerCase().startsWith(t.toLowerCase()) : contains(w, t);
    });
    if (!hit) return false;
  }
  return true;
}

/** {property: [its descendants' properties]} over the facets' `parent:` links (kit gap 8): a facet's children name it as
    their parent, and theirs name them. A cycle is cut where it closes (the checkers refuse one). */
export function descendants(specs) {
  const kids = new Map();
  for (const s of specs) if (s && typeof s.parent === 'string' && s.parent && s.property && s.parent !== s.property) {
    if (!kids.has(s.parent)) kids.set(s.parent, []);
    kids.get(s.parent).push(s.property);
  }
  const out = new Map();
  for (const p of kids.keys()) {
    const seen = new Set();
    const walk = (q) => { for (const c of kids.get(q) || []) if (c !== p && !seen.has(c)) { seen.add(c); walk(c); } };
    walk(p);
    out.set(p, [...seen]);
  }
  return out;
}

/** A parent's new pick, settled into its children (kit gap 8, CONTRACT §7; Grafana's chained variables, Kibana's parent
    control): each facet naming `changed` as its parent keeps its pick while some row (passing `rest` and every other
    pick) still has it; a single pick (select, toggle) that no row has any more moves to the facet's first listed value
    that one has (its `order`, else its counts' order: most rows first), a multi-value pick keeps the values that one has
    (none left: no pick). Then its own children, the same way. Returns a new facets object; the one handed in is not
    changed. WHY move and not clear: a run picker defaults to the newest run (PEP 0010 §6), so picking another board
    lands on that board's newest run, not on every run of it. */
export function settleChildren(rows, facets, specs, changed, rest = () => true) {
  const out = Object.fromEntries(Object.entries(facets || {}).map(([k, f]) => [k, f && typeof f === 'object' ? { ...f, ...(Array.isArray(f.values) ? { values: [...f.values] } : {}) } : f]));
  const queue = [changed];
  const done = new Set();
  while (queue.length) {
    const parent = queue.shift();
    if (done.has(parent)) continue;
    done.add(parent);
    for (const s of specs || []) {
      if (!s || s.parent !== parent || !s.property || s.property === parent) continue;
      const p = s.property;
      const f = out[p];
      queue.push(p);
      if (!f || !Array.isArray(f.values) || !f.values.length) continue;
      const pool = rows.filter((r) => rest(r) && matchesRail(r, out, [p]));
      const counts = valueCounts(pool, p);
      const fits = f.values.filter((v) => counts[String(v)] > 0);
      if (fits.length === f.values.length) continue;
      if (SINGLE.has(s.as)) {
        const listed = Object.keys(counts);
        if (Array.isArray(s.order)) listed.sort((a, b) => orderRank(s.order, a) - orderRank(s.order, b));
        const first = listed[0];
        const typed = first === undefined ? undefined : pool.map((r) => cellValue(r[p])).flat().find((v) => String(v) === first);
        if (first === undefined) { delete f.values; delete f.match; } else f.values = [typed];
      } else if (fits.length) f.values = fits;
      else { delete f.values; delete f.match; }
      if (!Object.keys(f).some((k) => ['values', 'exclude', 'min', 'max', 'has', 'hasAny', 'text'].includes(k))) delete out[p];
    }
  }
  return out;
}
const orderRank = (order, v) => { const i = order.map(String).indexOf(String(v)); return i < 0 ? order.length : i; };

/** `except`: a property, or a list / Set of them, whose own selection is left out (disjunctive counts). */
export function matchesRail(row, facets, except = null) {
  const skip = except === null || except === undefined ? null : typeof except === 'string' ? new Set([except]) : new Set(except);
  for (const [p, f] of Object.entries(facets)) if (!(skip && skip.has(p)) && !matchesFacet(row, p, f)) return false;
  return true;
}

/* A rail state compiled once for a count pass: the same answer as matchesRail(row, facets, except), without making a
   Set of `except` and scanning every ticked value per row. WHY: the rail counts every facet against every row; the
   per-row Set and `values.some(equals)` were most of a 100,000-row recount (perf review 2026-10-26, item 3). A facet
   with only values / exclude is a Set lookup; any other clause (bounds, has, text) still goes through matchesFacet, so
   one function keeps those rules. `except` (a property, a list or null) is planned once per distinct list. */
const FAST_KEYS = new Set(['values', 'match', 'exclude', 'excludeMatch']);
function valueTest(xs, how) {
  if (how === 'contains') {
    const exact = new Set(xs.map(String));
    const lower = xs.map((x) => String(x).toLowerCase());
    return (v) => (Array.isArray(v) ? v.some((y) => exact.has(String(y))) : !isEmpty(v) && lower.some((x) => String(v).toLowerCase().includes(x)));
  }
  // equals(): two empties match; otherwise numbers by value and the rest as text, which for finite numbers is the same
  // as comparing their String() (0 and -0 both read "0")
  const empty = xs.some(isEmpty);
  const keys = new Set(xs.filter((x) => !isEmpty(x)).map(String));
  return (v) => (isEmpty(v) ? empty : keys.has(String(v)));
}
function compileFacet(p, f) {
  if (!Object.keys(f).every((k) => FAST_KEYS.has(k))) return (row) => matchesFacet(row, p, f);
  const hit = f.values && f.values.length ? valueTest(f.values, f.match === 'contains' ? 'contains' : 'equals') : null;
  const miss = f.exclude && f.exclude.length ? valueTest(f.exclude, f.excludeMatch === 'contains' ? 'contains' : 'equals') : null;
  return (row) => {
    const v = cellValue(row[p]);
    return (!hit || hit(v)) && !(miss && miss(v));
  };
}
export function compileRail(facets) {
  const tests = Object.entries(facets).map(([p, f]) => [p, compileFacet(p, f)]);
  const plans = new Map();
  const plan = (except) => {
    let got = plans.get(except);
    if (!got) {
      const skip = except === null || except === undefined ? null : typeof except === 'string' ? new Set([except]) : new Set(except);
      got = tests.filter(([p]) => !(skip && skip.has(p))).map(([, t]) => t);
      plans.set(except, got);
    }
    return got;
  };
  return (row, _facets, except = null) => {
    const ts = plan(except);
    for (let i = 0; i < ts.length; i++) if (!ts[i](row)) return false;
    return true;
  };
}

/** Disjunctive counts for the rail (McMaster, Algolia): each facet's counts apply every OTHER facet's selection but
    not its own, so ticking one brand still shows how many parts every other brand has. `rest(row)` applies the
    custom clauses (the engine's evaluator); `kinds` says which properties are values facets and which are ranges. */
export function facetCounts(rows, facets, kinds, rest = () => true) {
  const matchesRail = compileRail(facets); // the compiled form of the exported one, same contract (compileRail)
  const out = {};
  for (const [p, kind] of Object.entries(kinds)) {
    const subset = rows.filter((r) => rest(r) && matchesRail(r, facets, p));
    if (kind === 'range') {
      const nums = subset.map((r) => cellValue(r[p])).filter(isNum);
      out[p] = { n: nums.length, ...span(nums) };
    } else out[p] = valueCounts(subset, p);
  }
  return out;
}

function valueCounts(rows, p) {
  const counts = new Map();
  for (const r of rows) {
    const cell = cellValue(r[p]);
    for (const v of Array.isArray(cell) ? cell : [cell]) if (!isEmpty(v)) counts.set(String(v), (counts.get(String(v)) || 0) + 1);
  }
  return Object.fromEntries([...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

// ------------------------------------------------------------------ numbers: histograms, slider scales, buckets

// WHY a fold, not Math.min(...nums): spreading 150,000 rows into one call overflows the stack (2026-10-26 review)
const least = (nums, from = Infinity) => nums.reduce((a, b) => Math.min(a, b), from);
const most = (nums, from = -Infinity) => nums.reduce((a, b) => Math.max(a, b), from);
const span = (nums) => (nums.length ? { min: least(nums), max: most(nums) } : { min: null, max: null });

/** Round to 3 significant figures, for a slider thumb's value (12.3456 -> 12.3, 4321 -> 4320). */
export function nice(v) {
  if (!isNum(v) || v === 0) return v;
  const e = Math.floor(Math.log10(Math.abs(v))) - 2;
  const f = 10 ** e;
  return Number((Math.round(v / f) * f).toPrecision(12));
}

/** A slider's scale over [min, max]: position 0..1000 <-> value; `log` for a domain spanning decades. */
export function sliderScale(min, max, log = false) {
  const useLog = log && min > 0 && max > 0;
  const lo = useLog ? Math.log10(min) : min, hi = useLog ? Math.log10(max) : max;
  const span = hi - lo || 1;
  return {
    log: useLog,
    toPos: (v) => Math.round(Math.max(0, Math.min(1000, (((useLog ? Math.log10(Math.max(v, min)) : v) - lo) / span) * 1000))),
    toValue: (pos) => { if (pos <= 0) return min; if (pos >= 1000) return max; const x = lo + (pos / 1000) * span; return nice(useLog ? 10 ** x : x); },
  };
}

/** [{x0, x1, n}] over the domain: `bins` equal steps (in log space with `log`); a value on the top edge falls in the
    last bin. Non-positive values have no place on a log axis and are left out (said by n's sum). */
export function histogram(values, { min, max, bins = 24, log = false }) {
  const s = sliderScale(min, max, log);
  const edges = Array.from({ length: bins + 1 }, (_, i) => (s.log ? 10 ** (Math.log10(min) + ((Math.log10(max) - Math.log10(min)) * i) / bins) : min + ((max - min) * i) / bins));
  const out = edges.slice(0, -1).map((x0, i) => ({ x0, x1: edges[i + 1], n: 0 }));
  if (min === null || max === null) return [];
  for (const v of values) {
    if (!isNum(v) || v < min || v > max || (s.log && v <= 0)) continue;
    const at = max === min ? 0 : Math.min(bins - 1, Math.floor((s.toPos(v) / 1000) * bins));
    out[at].n++;
  }
  return out;
}

/** Bucket edges -> [{label, min?, max?, maxOpen?}] with the last one open-ended: [1, 10, 100] reads "< 1", "1–10",
    "10–100", "≥ 100". Each bucket is p >= a and p < b, so they never overlap. */
export function bucketsFrom(edges, fmt = String) {
  const e = [...edges].filter(isNum).sort((a, b) => a - b);
  if (!e.length) return [];
  const out = [{ label: `< ${fmt(e[0])}`, max: e[0], maxOpen: true }];
  for (let i = 0; i < e.length - 1; i++) out.push({ label: `${fmt(e[i])}–${fmt(e[i + 1])}`, min: e[i], max: e[i + 1], maxOpen: true });
  out.push({ label: `≥ ${fmt(e[e.length - 1])}`, min: e[e.length - 1] });
  return out;
}

/** Nice edges for a domain: decades (1, 10, 100) when it spans more than two of them, else 1-2-5 steps; at most 4. */
export function autoEdges(values, { log } = {}) {
  const nums = values.filter(isNum);
  if (!nums.length) return [];
  const sorted = [...nums].sort((a, b) => a - b);
  const q = (t) => sorted[Math.min(sorted.length - 1, Math.floor(t * sorted.length))];
  const lo = q(0.05), hi = q(0.95);
  const decades = lo > 0 && hi > 0 ? Math.log10(hi) - Math.log10(lo) : 0;
  if (log !== false && (log || decades > 2) && lo > 0) {
    const edges = [];
    for (let k = Math.ceil(Math.log10(lo)); k <= Math.floor(Math.log10(hi)); k++) edges.push(10 ** k);
    while (edges.length > 4) edges.splice(1, 1);
    if (edges.length) return edges.map(nice);
  }
  const raw = (hi - lo) / 4 || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const within = (step) => { const e = []; for (let x = Math.ceil(lo / step) * step; x < hi && e.length < 6; x += step) if (x > sorted[0]) e.push(nice(x)); return e; };
  // the 1-2-5 step whose edges inside the middle 90 % come closest to four
  const tries = [0.5, 1, 2, 5, 10].map((m) => within(m * mag));
  return tries.reduce((best, e) => (Math.abs(e.length - 3.5) < Math.abs(best.length - 3.5) ? e : best), tries[0]).slice(0, 4);
}

export function bucketsOf(spec, values, fmt = String) {
  const b = spec.buckets;
  if (Array.isArray(b) && b.length && b.every((x) => x && typeof x === 'object')) return b.map((x) => ({ label: x.label || `${x.min ?? ''}–${x.max ?? ''}`, ...('min' in x ? { min: x.min } : {}), ...('max' in x ? { max: x.max, maxOpen: x.maxOpen !== false } : {}) }));
  if (Array.isArray(b) && b.length) return bucketsFrom(b, fmt);
  return bucketsFrom(autoEdges(values, { log: spec.log }), fmt);
}

// every stored digit and thousands separators, as format.js' fmtNum writes a number with no `decimals`
const PLAIN = new Intl.NumberFormat('en-US', { maximumFractionDigits: 20 });

/* A unit's ladder, smallest first, as factors of the first: a bin's edge is written in the largest step it reaches
   ("1 L", not "1,000 mL"), so a label reads like the catalogue's ("250 mL – 1 L"). A unit on no ladder is written as
   given. */
const UNIT_LADDERS = [
  [['mL', 1], ['L', 1e3], ['m³', 1e6]],
  [['mg', 1], ['g', 1e3], ['kg', 1e6], ['t', 1e9]],
  [['mm', 1], ['m', 1e3], ['km', 1e6]],
  [['ms', 1], ['s', 1e3]],
  [['mN', 1], ['N', 1e3], ['kN', 1e6]],
  [['mW', 1], ['W', 1e3], ['kW', 1e6]],
];

/** A number with its unit, scaled along the unit's ladder: (1000, 'mL') -> '1 L', (250, 'mL') -> '250 mL',
    (0.5, 'L') -> '500 mL'; no unit: the number alone. */
export function fmtUnit(v, unit = '') {
  if (!isNum(v)) return String(v ?? '');
  const clean = (x) => PLAIN.format(Number(x.toPrecision(12)));
  const ladder = unit ? UNIT_LADDERS.find((l) => l.some(([u]) => u === unit)) : null;
  if (!ladder) return unit ? `${clean(v)} ${unit}` : String(clean(v));
  const base = v * ladder.find(([u]) => u === unit)[1];
  let step = ladder[0];
  for (const s of ladder) if (Math.abs(base) >= s[1]) step = s;
  return `${clean(base / step[1])} ${step[0]}`;
}

/** A group level's buckets for `bins:` (docs/CONTRACT.md §20): the rail's own bucket machinery (bucketsFrom over the
    given edges, or autoEdges over `values` for `auto`, `log` as the buckets kind reads it; labelled buckets as given),
    ascending, each with a text key that sorts in that order and a label in the level's `unit` (default `unit`, the
    column's): "< 250 mL", "250 mL – 1 L", "≥ 50 L". [] when the level has no bins. */
export function groupBuckets(level, values, unit = '') {
  const spec = binsOf(level);
  if (!spec) return [];
  const u = level.unit !== undefined && level.unit !== null ? String(level.unit) : unit || '';
  const fmt = (v) => fmtUnit(v, u);
  const labelled = Array.isArray(spec) && spec.every((x) => x && typeof x === 'object');
  const raw = labelled
    ? spec.map((x) => ({ ...(x.label ? { label: String(x.label) } : {}), ...(isNum(x.min) ? { min: x.min } : {}), ...(isNum(x.max) ? { max: x.max, maxOpen: x.maxOpen !== false } : {}) }))
      .sort((a, b) => (a.min ?? -Infinity) - (b.min ?? -Infinity))
    : bucketsOf({ buckets: spec === 'auto' ? undefined : spec, log: level.log }, values.filter(isNum)).map(({ label, ...b }) => b);
  return raw.map((b, i) => ({
    key: `${String(i).padStart(2, '0')}:${b.min ?? ''}..${b.max ?? ''}`,
    label: b.label || (b.min === undefined ? `< ${fmt(b.max)}` : b.max === undefined ? `≥ ${fmt(b.min)}` : `${fmt(b.min)} – ${fmt(b.max)}`),
    ...(b.min !== undefined ? { min: b.min } : {}), ...(b.max !== undefined ? { max: b.max, maxOpen: b.maxOpen !== false } : {}),
  }));
}

/** The rail state that picks one group of a level, or null when no facet can say it (no value; a list row's several
    values at once): a value -> {values: [v], match}; a bin -> its range {min, max, maxOpen}; a time bucket -> its days
    (`p >= "2026-10-01"`, `p < "2026-11-01"`). `columns` are the model's (they carry a level's bins and grain). What a
    nav row and a tile's drill write through host.setFacet (docs/CONTRACT.md §20). */
export function groupFacet(columns, property, key) {
  if (isEmpty(key)) return null;
  const col = columns[property] || {};
  if (Array.isArray(col.bins)) {
    const b = col.bins.find((x) => x.key === key);
    if (!b) return null;
    return { ...(b.min !== undefined ? { min: b.min } : {}), ...(b.max !== undefined ? { max: b.max, ...(b.maxOpen !== false ? { maxOpen: true } : {}) } : {}) };
  }
  if (col.by) {
    const min = bucketStart(key, col.by), next = nextBucket(key, col.by);
    return min ? { min, ...(next ? { max: bucketStart(next, col.by), maxOpen: true } : {}) } : null;
  }
  if (Array.isArray(key)) return key.length === 1 ? { values: [key[0]], match: 'contains' } : null;
  return { values: [key], match: col.type === 'list' ? 'contains' : 'equals' };
}

/** Is the facet's state exactly this bucket? */
export function isBucket(f, b) {
  return !!f && f.min === b.min && f.max === b.max && !!f.maxOpen === !!b.maxOpen && !f.minOpen;
}

// ------------------------------------------------------------------ dates

const DAY = 86400000;
const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

/** '7d', '4w', '6m', '1y', 'year' (since January 1st) -> the ISO date that many days before `now`. */
export function dateBefore(preset, now = new Date()) {
  if (preset === 'year') return `${now.getFullYear()}-01-01`;
  const m = /^(\d+)\s*([dwmy])$/.exec(String(preset));
  if (!m) return null;
  const n = Number(m[1]);
  const days = { d: 1, w: 7, m: 30, y: 365 }[m[2]] * n;
  return iso(new Date(now.getTime() - days * DAY));
}

/** The bounds the rail's date presets have now ([key, from-bounds, older-bounds] per date facet; [] without one): what
    a cached count of them depends on besides the rows. WHY (judge r1, 2026-10-27): the counts were cached on the data
    and the filters only, so "Last 7 days" kept yesterday's bound (and its count) past midnight. */
export function dateBounds(specs, now = new Date()) {
  return specs.filter((s) => s.as === 'date').map((s) => [s.key,
    asList(s.presets || DATE_PRESETS).map((x) => dateBefore(x, now)), asList(s.older || DATE_OLDER).map((x) => dateBefore(x, now))]);
}

/** When the next of the date presets' bounds moves (ms since the epoch), or null without a date facet. A preset of D
    (7d: 7 x 24 h) reads the local date of now - D, so it moves when now - D crosses a local midnight: at that midnight
    plus D. WHY not "at midnight": across a DST change that is 23:00 or 01:00 local (judge r2, 2026-10-27: Last 7 days
    in Vancouver on 2026-11-01 moves at 23:00). 'year' moves at the next local January 1. */
export function nextDateChange(specs, now = new Date()) {
  const t = now.getTime();
  let next = null;
  const at = (preset) => {
    if (preset === 'year') return new Date(now.getFullYear() + 1, 0, 1).getTime();
    const m = /^(\d+)\s*([dwmy])$/.exec(String(preset));
    if (!m) return null;
    const span = { d: 1, w: 7, m: 30, y: 365 }[m[2]] * Number(m[1]) * DAY;
    const back = new Date(t - span);
    return new Date(back.getFullYear(), back.getMonth(), back.getDate() + 1).getTime() + span;
  };
  for (const s of specs) {
    if (s.as !== 'date') continue;
    for (const p of [...asList(s.presets || DATE_PRESETS), ...asList(s.older || DATE_OLDER)]) {
      const x = at(p);
      if (x !== null && x > t && (next === null || x < next)) next = x;
    }
  }
  return next;
}

export function presetLabel(preset, older = false) {
  if (preset === 'year') return 'This year';
  const m = /^(\d+)\s*([dwmy])$/.exec(String(preset));
  if (!m) return String(preset);
  const unit = { d: 'day', w: 'week', m: 'month', y: 'year' }[m[2]];
  const words = `${m[1]} ${unit}${m[1] === '1' ? '' : 's'}`;
  return older ? `Older than ${words}` : `Last ${words}`;
}

export const DATE_PRESETS = ['7d', '30d', 'year'];
export const DATE_OLDER = ['30d', '1y'];

// ------------------------------------------------------------------ what each facet needs to draw

/** The counts and extents every facet of a rail draws from, keyed by spec.key. Disjunctive throughout: a facet's
    numbers leave out its own selection and apply the rest (a tree's level applies the levels above it). `rows` are
    the view's rows before the rail; `rest(row)` the custom clauses. */
export function railCounts(rows, facets, specs, rest = () => true, { now = new Date() } = {}) {
  const matchesRail = compileRail(facets); // the compiled form of the exported one, same contract (compileRail)
  const out = {};
  // a parent's counts leave out its children's picks too (kit gap 8): the device lists every board while a run is picked
  const below = descendants(specs);
  const memo = new Map();
  const subset = (except) => {
    const key = [...except].sort().join('\u0000');
    if (!memo.has(key)) memo.set(key, rows.filter((r) => rest(r) && matchesRail(r, facets, except)));
    return memo.get(key);
  };
  for (const s of specs) {
    const p = s.property;
    if (s.as === 'current') continue;
    if (s.as === 'popular') {
      out[s.key] = s.options.map((o) => {
        const c = parseClause(o.filter, { wide: true });
        if (!c) return null;
        const probe = { [c.property]: c.kind === 'eq' || c.kind === 'contains' ? { values: [c.value], match: c.kind === 'contains' ? 'contains' : 'equals' } : c.kind === 'has' ? { has: true } : { [c.kind]: c.value, ...(c.open ? { [c.kind + 'Open']: true } : {}) } };
        return subset([c.property]).filter((r) => matchesFacet(r, c.property, probe[c.property])).length;
      });
      continue;
    }
    if (s.as === 'tree') {
      out[s.key] = s.levels.map((l, i) => valueCounts(subset(s.levels.slice(i)), l));
      continue;
    }
    if (s.as === 'has') {
      const sub = subset(s.properties);
      out[s.key] = Object.fromEntries(s.properties.map((x) => [x, sub.filter((r) => !isEmpty(cellValue(r[x]))).length]));
      continue;
    }
    if (s.as === 'search') { out[s.key] = { n: subset(s.properties).length }; continue; }
    // a nav facet's rows are the view's own groups (rowmodel.js groupEntries, which <data-facets> asks with the rail's
    // other picks); here only how many rows its own pick leaves out of
    if (s.as === 'nav') { out[s.key] = { n: subset([p]).length }; continue; }
    const sub = subset([p, ...(below.get(p) || [])]);
    if (VALUE_KINDS.has(s.as)) { out[s.key] = { counts: valueCounts(sub, p), n: sub.length }; continue; }
    if (s.as === 'date' || (s.as === 'range' && s.prop && s.prop.type === 'date')) {
      const vals = sub.map((r) => cellValue(r[p])).filter((v) => !isEmpty(v)).map(String).sort();
      const all = rows.map((r) => cellValue(r[p])).filter((v) => !isEmpty(v)).map(String).sort();
      const count = (fn) => vals.filter(fn).length;
      out[s.key] = {
        n: vals.length, min: vals[0] ?? null, max: vals[vals.length - 1] ?? null, domain: { min: all[0] ?? null, max: all[all.length - 1] ?? null },
        presets: s.as !== 'date' ? [] : asList(s.presets || DATE_PRESETS).map((x) => { const d = dateBefore(x, now); return { preset: x, min: d, n: d ? count((v) => v >= d) : 0 }; }),
        older: s.as !== 'date' ? [] : asList(s.older || DATE_OLDER).map((x) => { const d = dateBefore(x, now); return { preset: x, max: d, n: d ? count((v) => v < d) : 0 }; }),
      };
      continue;
    }
    const nums = sub.map((r) => cellValue(r[p])).filter(isNum);
    const allNums = rows.map((r) => cellValue(r[p])).filter(isNum);
    const domain = span(allNums);
    const o = { n: nums.length, ...span(nums), domain };
    if (s.as === 'slider-histogram' && domain.min !== null) {
      const log = !!s.log && domain.min > 0;
      o.bins = histogram(nums, { ...domain, bins: s.bins || 24, log });
      o.binsAll = histogram(allNums, { ...domain, bins: s.bins || 24, log });
    }
    if (s.as === 'buckets') o.buckets = bucketsOf(s, allNums).map((b) => ({ ...b, n: nums.filter((v) => (b.min === undefined || v >= b.min) && (b.max === undefined || (b.maxOpen ? v < b.max : v <= b.max))).length }));
    if (RATING.has(s.as)) {
      const top = s.max || most(allNums.filter((v) => Number.isInteger(v)), 1);
      const bottom = s.min !== undefined ? s.min : 1;
      o.levels = [];
      for (let k = top; k >= bottom; k--) o.levels.push({ level: k, n: nums.filter((v) => v >= k).length });
    }
    out[s.key] = o;
  }
  return out;
}

/** What a rail counts from, as <data-facets> computes it: the rail's config, its state read out of the all-views
    filter, the view's rows before the rail (its own `filters` applied) and the custom clauses as one test. One function
    for the rail and the row-model worker, so both count the same rows (rowmodel-worker.js, 'counts'). */
export function railInputs(dataset, view, filters, specs) {
  const cfg = railConfig(specs);
  const rail = toRail(filters, cfg);
  let viewKeep = null, restKeep = null;
  try { viewKeep = compileFilters((view || {}).filters); } catch { viewKeep = null; }
  try { restKeep = compileFilters(rail.rest.length ? { and: rail.rest } : null); } catch { restKeep = null; }
  const rows = viewKeep ? dataset.rows.filter(viewKeep) : dataset.rows;
  return { cfg, rail, rows, rest: restKeep || (() => true) };
}

// ------------------------------------------------------------------ the readable URL
// ?brand=Steadywin,CubeMars&peak_torque=10..<100&listed=2026-10-19..&brand!=KST&model~=ak80&has=photo&hasany=a,b
//   p=a,b          the ticked values (any of)          p!=a,b        none of these values (exclude)
//   p=a..b         a range: `>` before a, `<` before b make a bound exclusive; either side may be empty
//   p~=text        a search (p^= for "starts with"); over several properties, keyed by the first
//   has=p,q        p and q have a value                 hasany=p,q    p or q has a value
// WHY this shape (Datasette's col=value, Shopify's comma lists): a link someone pastes reads as the filter it is.

const enc = (vals) => vals.map((x) => encodeURIComponent(String(x))).join(',');
const dec = (raw) => raw.split(',').map(decodeURIComponent);

/** The rail's state as [key, value] search params. */
export function railParams(facets) {
  const out = [];
  const has = [];
  for (const [p, f] of Object.entries(facets)) {
    if (f.values && f.values.length) out.push([p, enc(f.values)]);
    if (f.exclude && f.exclude.length) out.push([`${p}!`, enc(f.exclude)]);
    if ((f.min !== undefined && f.min !== null) || (f.max !== undefined && f.max !== null)) {
      out.push([p, `${f.minOpen ? '>' : ''}${f.min ?? ''}..${f.maxOpen ? '<' : ''}${f.max ?? ''}`]);
    }
    if (f.has) has.push(p);
    if (f.hasAny && f.hasAny.length) out.push(['hasany', f.hasAny.map(encodeURIComponent).join(',')]);
    if (f.text !== undefined && f.text !== '') out.push([`${p}${f.textMatch === 'startsWith' ? '^' : '~'}`, String(f.text)]);
  }
  if (has.length) out.push(['has', has.map(encodeURIComponent).join(',')]);
  return out;
}

/** Is this search-param key one the rail writes, for one of these properties? */
export function isRailParam(key, known) {
  if (key === 'has' || key === 'hasany') return true;
  const p = /[!~^]$/.test(key) ? key.slice(0, -1) : key;
  return known.has(p);
}

const RANGE_PARAM = /^(>?)([^,]*?)\.\.(<?)([^,]*)$/;

/** [key, value] search params -> the rail's state. `props` types the values (a number property reads numbers);
    `known` (a Set) is every property some rail of the file has; `config` names a search's other properties. */
export function paramsRail(entries, props, known, config = null) {
  const facets = {};
  const at = (p) => (facets[p] = facets[p] || {});
  const typed = (p, x) => ((props[p] || {}).type === 'number' && x !== '' && !Number.isNaN(Number(x)) ? Number(x) : x);
  for (const [k, raw] of entries) {
    if (k === 'has') { for (const p of dec(raw)) if (props[p]) at(p).has = true; continue; }
    if (k === 'hasany') { const ps = dec(raw).filter((p) => props[p]); if (ps.length > 1) at(ps[0]).hasAny = ps; continue; }
    const mark = /[!~^]$/.test(k) ? k.slice(-1) : '';
    const p = mark ? k.slice(0, -1) : k;
    if (!props[p] || !known.has(p)) continue;
    const list = props[p].type === 'list';
    if (mark === '!') { Object.assign(at(p), { exclude: dec(raw).map((x) => typed(p, x)), excludeMatch: list ? 'contains' : 'equals' }); continue; }
    if (mark === '~' || mark === '^') {
      const match = mark === '^' ? 'startsWith' : 'contains';
      const s = config && config.search.find((x) => x.properties[0] === p && x.match === match);
      Object.assign(at(p), { text: raw, textIn: s ? s.properties : [p] }, match === 'startsWith' ? { textMatch: 'startsWith' } : {});
      continue;
    }
    const range = RANGE_PARAM.exec(raw);
    const bounded = props[p].type === 'number' || props[p].type === 'date' || (config && [...(config.by.get(p) || [])].some((x) => BOUNDS.has(x) || RATING.has(x)));
    if (range && bounded) {
      const f = at(p);
      const num = props[p].type === 'number';
      if (range[2] !== '') { f.min = num ? Number(range[2]) : decodeURIComponent(range[2]); if (range[1]) f.minOpen = true; }
      if (range[4] !== '') { f.max = num ? Number(range[4]) : decodeURIComponent(range[4]); if (range[3]) f.maxOpen = true; }
      continue;
    }
    Object.assign(at(p), { values: dec(raw).map((x) => typed(p, x)), match: list ? 'contains' : 'equals' });
  }
  return facets;
}

/** Every property some rail of the file stands over (the URL keys it may own). */
export function railProperties(specs) {
  const out = new Set();
  for (const s of specs) {
    for (const p of [s.property, ...(s.levels || []), ...(s.properties || [])]) if (p) out.add(p);
    for (const o of s.options || []) { const c = parseClause(o.filter, { wide: true }); if (c) out.add(c.property); }
  }
  return out;
}
