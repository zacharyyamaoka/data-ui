/* data-ui check: validate .base view files, for people and for agents (docs/SPEC.md §5.7, docs/CONTRACT.md §5).

   The Node port of tools/check_views.py, on the same grammar.js and base.js the page runs, so the browser and the
   checker never disagree about what a file or an expression means. Each problem is one line,
   `file:line: error|warning: path: message`, with "did you mean ...?" when a name is close to a real one:

     1. the file parses (base.js, the subset every .base file in Zach's vault uses);
     2. it matches schemas/view.schema.json (Bases keys plus data-ui's, every view type in docs/VIEWS.md);
     3. unknown keys and view types are warnings (Bases keeps keys it does not know);
     4. every filter expression compiles with grammar.js. What only Obsidian evaluates (file.*, this, functions such
        as link()) is a warning: data-ui v1 does not evaluate it (SPEC §5.6). Anything else that fails is an error;
     5. with data (--data, or the file's own `data:` key), every property a view names exists in it;
     6. the rail's own rules: a facet names what it filters, and its kind fits the property's type (facetProblems);
     7. `open:` (how a record opens): link with no URL anywhere falls back to side, and says so (openProblems);
     8. a group level's time grain (`by:`) on a property the data does not type as a date warns (timeProblems);
     9. the grouped gallery (CONTRACT §20): `grouping:` names a `groupings:` entry, ids are unique, a level groups by
        `bins:` or `by:` (not both), and bins on a property the data does not type as a number warn (groupingProblems);
    10. the 3D cards (CONTRACT §32): a refused projection, decay or axes says what was probably meant (sceneMessage), a
        projection's vectors make a view (sceneProblems), a layer names a dataset the dashboard has (model.js), and
        every column a layer, the trajectory binding (given or by default) and voxels read is a property of the dataset
        that layer reads (sceneNames).
    11. the diagnostics and gates overlay (CONTRACT §35): a tracker's column, a limits end, a property kpi target and a
        trajectory3d colour are properties of the dataset the view reads (referenced), and a record section's embedded
        view is checked as a view of its own: its keys, and its columns against ITS from: dataset (default the outer
        view's), with each `this.<column>` of its filters against the OUTER view's, the peeked row's (sectionNames).

   Node only (it uses Ajv); the page never loads this file. */

import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve, basename, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import { parseBaseWithLines, lineOf, BaseSyntaxError } from './base.js';
import { compileExpression, expressionProperties, parseCoalesce } from './grammar.js';
import { precedenceOf, sourceColumnOf, columnId } from './precedence.js';
import { readDashboard, layerRefs, placeholders } from '../../dashboard/src/model.js';
import { parseCSV, parseJSONL } from './data.js';
import { bindThis } from './sections.js';

const HERE = dirname(fileURLToPath(import.meta.url));
export const SCHEMA_PATH = resolve(HERE, '..', '..', '..', 'schemas', 'view.schema.json');
const SCHEMA = JSON.parse(readFileSync(SCHEMA_PATH, 'utf8'));

// datasets, links and layout: a dashboard (docs/peps/0004-dashboards.md, CONTRACT §17; cards, clock, style, rerun: PEP 0005, CONTRACT §25;
// retention: live data, docs/peps/0012-live-data.md, CONTRACT §26)
const TOP_KEYS = new Set(['filters', 'formulas', 'properties', 'summaries', 'views', 'display', 'newItemFolder', 'newItemTemplate', 'facets', 'data', 'open', 'datasets', 'links', 'layout', 'clock', 'style', 'rerun', 'retention', 'defaultView', 'sharedColumns', 'before', 'after', 'summary', 'page']);
export const VIEW_KEYS = new Set(Object.keys(SCHEMA.$defs.view.properties));
export const VIEW_TYPES = new Set(SCHEMA.$defs.view.properties.type.examples);

let validator = null;
function validate(doc) {
  if (!validator) {
    const ajv = new Ajv2020({ allErrors: true, strict: false, verbose: true });
    validator = ajv.compile(SCHEMA);
  }
  validator(doc);
  return validator.errors || [];
}

// ------------------------------------------------------------------------------------------------ messages

/** Python's difflib.get_close_matches, enough of it: the ratio of matching characters. */
function ratio(a, b) {
  const m = new Map();
  const lcs = (i, j) => {
    if (i >= a.length || j >= b.length) return 0;
    const k = i * 1000 + j;
    if (m.has(k)) return m.get(k);
    const v = a[i] === b[j] ? 1 + lcs(i + 1, j + 1) : Math.max(lcs(i + 1, j), lcs(i, j + 1));
    m.set(k, v);
    return v;
  };
  return (2 * lcs(0, 0)) / (a.length + b.length || 1);
}

export function suggest(word, choices) {
  const words = [...choices].map(String).sort();
  const w = String(word);
  let match = words.find((c) => c.toLowerCase() === w.toLowerCase());
  if (!match) {
    const scored = words.map((c) => [ratio(w, c), c]).filter(([r]) => r >= 0.72).sort((x, y) => y[0] - x[0]);
    match = scored.length ? scored[0][1] : null;
  }
  if (!match) match = words.find((c) => c.length >= 3 && w.toLowerCase().startsWith(c.toLowerCase()));
  return match ? ` (did you mean '${match}'?)` : '';
}

export function show(path) {
  let out = '';
  for (const part of path) out += typeof part === 'number' ? `[${part}]` : out ? `.${part}` : String(part);
  return out || '(file)';
}

const pointer = (p) => (p ? p.split('/').slice(1).map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~')).map((s) => (/^\d+$/.test(s) ? Number(s) : s)) : []);
const PRIORITY = { additionalProperties: 3, enum: 3, const: 3, required: 1, type: 0 };

/** Ajv's flat error list -> one error per problem, choosing for a oneOf/anyOf the branch error that says the most
    (an unknown key or a wrong choice, at the deepest path), as the Python checker does.
    WHY by position: Ajv pushes a composite's branch errors just before the composite's own error, and a branch
    reached through $ref reports the referenced schema's path, so the run of errors before it (at or below its
    instance path) is the branch list; schema paths alone would miss the $ref'd branches. */
function pickErrors(errors) {
  const composite = (e) => e.keyword === 'oneOf' || e.keyword === 'anyOf';
  const inside = (e, c) => e.instancePath === c.instancePath || (c.instancePath === '' ? true : e.instancePath.startsWith(c.instancePath + '/'));
  const owner = new Array(errors.length).fill(-1);
  for (let k = errors.length - 1; k >= 0; k--) {
    if (!composite(errors[k]) || owner[k] !== -1) continue;
    for (let j = k - 1; j >= 0 && owner[j] === -1 && inside(errors[j], errors[k]); j--) owner[j] = k;
  }
  const out = [];
  errors.forEach((e, k) => {
    if (owner[k] !== -1 || e.keyword === 'if') return;
    if (!composite(e)) { out.push(e); return; }
    const claimed = (j) => { let o = owner[j]; while (o !== -1 && o !== k) o = owner[o]; return o === k; };
    const leaves = errors.filter((x, j) => claimed(j) && !composite(x) && x.keyword !== 'if');
    const depth = pointer(e.instancePath).length;
    // every branch only says "needs <key>" (a chart's encoding, mark or layer): the composite's own sentence names all
    if (!leaves.length || leaves.every((x) => x.keyword === 'required' && pointer(x.instancePath).length === depth)) { out.push(e); return; }
    const score = (x) => [!(x.keyword === 'type' && pointer(x.instancePath).length === depth) ? 1 : 0, pointer(x.instancePath).length, PRIORITY[x.keyword] ?? 2];
    let best = leaves[0];
    for (const x of leaves.slice(1)) {
      const a = score(x), b = score(best);
      if (a[0] > b[0] || (a[0] === b[0] && (a[1] > b[1] || (a[1] === b[1] && a[2] > b[2])))) best = x;
    }
    out.push(best);
  });
  return out;
}

function schemaMessage(e) {
  const value = e.data;
  if (e.keyword === 'enum') return `${JSON.stringify(value)} is not one of ${e.params.allowedValues.join(', ')}${suggest(value, e.params.allowedValues)}`;
  if (e.keyword === 'const') return `${JSON.stringify(value)} must be ${JSON.stringify(e.params.allowedValue)}`;
  if (e.keyword === 'required') return `needs '${e.params.missingProperty}'`;
  if (e.keyword === 'additionalProperties') {
    let allowed = new Set(Object.keys((e.parentSchema && e.parentSchema.properties) || {}));
    if (allowed.size && [...allowed].every((k) => ['and', 'or', 'not'].includes(k))) allowed = new Set(['and', 'or', 'not']);
    const k = e.params.additionalProperty;
    return `unknown key '${k}'${suggest(k, allowed)}`;
  }
  if (e.keyword === 'type') return `must be ${e.params.type}, not ${Array.isArray(value) ? 'list' : value === null ? 'null' : typeof value === 'object' ? 'mapping' : typeof value}`;
  if (e.keyword === 'not') return 'a chart block must not carry data, datasets, $schema or config: data-ui supplies the rows and the theme';
  if (e.keyword === 'anyOf' && JSON.stringify(e.schema) === JSON.stringify([{ required: ['mark'] }, { required: ['layer'] }, { required: ['encoding'] }])) return 'a chart needs an encoding (Show Me picks the mark), a mark, or a layer of marks';
  if (e.keyword === 'anyOf' && JSON.stringify(e.schema) === JSON.stringify([{ required: ['x', 'y', 'z'] }, { required: ['layers'] }])) return 'a scene3d needs x, y and z (a path), or layers';
  if (e.keyword === 'anyOf' && JSON.stringify(e.schema) === JSON.stringify([{ required: ['properties'] }, { required: ['view'] }])) return "a record section needs 'properties' (its fields) or a 'view' (an inline view of the peeked row's evidence)";
  if ((e.keyword === 'minItems' || e.keyword === 'maxItems') && /limitPair/.test(e.schemaPath)) return 'a limits side is a pair [low, high]: a number, a property, or null for no limit on that end';
  if (e.keyword === 'oneOf' && /filters/.test(e.schemaPath)) return 'a filter is an expression string, or exactly one of and / or / not over a list of filters';
  return e.message;
}

// ------------------------------------------------------------------------------------------------ names in the file

/** The property names of a dataset file (the runtime shape, a field schema, or rows). */
/** A delimited or JSON-lines data file's own description (CONTRACT §3: `.csv` / `.tsv` / `.jsonl` with an optional
    `<name>.schema.json` beside it): the sidecar's {schema: {fields}} when there is one, else the header's (or the first
    rows' keys) as a bare field list, so the checker reads a CSV dataset as the browser does. */
function tableOf(path) {
  const side = path.replace(/\.(csv|tsv|jsonl)$/i, '.schema.json');
  if (existsSync(side)) { try { const d = JSON.parse(readFileSync(side, 'utf8')); if (d && d.schema && Array.isArray(d.schema.fields)) return d; } catch { /* the header below */ } }
  const text = readFileSync(path, 'utf8');
  if (/\.jsonl$/i.test(path)) {
    const keys = new Set();
    for (const line of text.split('\n').slice(0, 200)) { if (!line.trim()) continue; try { for (const k of Object.keys(JSON.parse(line))) keys.add(k); } catch { /* not a row */ } }
    return { schema: { fields: [...keys].map((name) => ({ name })) } };
  }
  const head = text.slice(0, text.search(/\r?\n|$/));
  const sep = /\.tsv$/i.test(path) ? '\t' : ',';
  return { schema: { fields: head.split(sep).map((h) => ({ name: h.trim().replace(/^"(.*)"$/, '$1') })).filter((f) => f.name) } };
}

/** Whether the checker can read a data file's columns: JSON, or CSV / TSV / JSON lines (with a sidecar or a header). */
export const isDataFile = (path) => /\.(json|csv|tsv|jsonl)$/i.test(path);

export function datasetProperties(path) {
  const data = /\.(csv|tsv|jsonl)$/i.test(path) ? tableOf(path) : JSON.parse(readFileSync(path, 'utf8'));
  return withSourceColumns(ownProperties(data), data);
}

/** The columns a dataset's lists of sources unfold to (CONTRACT §36): a .base may name them; `<p>@*` is every source of p. */
function withSourceColumns(names, data) {
  if (!data || !Array.isArray(data.rows)) return names;
  const info = precedenceOf(data);
  for (const [p, list] of Object.entries(info ? info.columns : {})) {
    for (const s of list) names.add(columnId(p, s));
    names.add(columnId(p));
    names.add(`${p}@*`);
  }
  const sc = sourceColumnOf(data);
  if (sc && sc.on) for (const p of sc.properties) names.add(columnId(p));
  return names;
}

function ownProperties(data) {
  if (data && !Array.isArray(data) && data.properties && typeof data.properties === 'object') return new Set(Object.keys(data.properties));
  if (data && data.schema && Array.isArray(data.schema.fields)) return new Set(data.schema.fields.map((f) => f.name));
  const rows = Array.isArray(data) ? data : (data && data.rows) || [];
  return new Set(rows.slice(0, 200).flatMap((r) => (r && typeof r === 'object' ? Object.keys(r) : [])));
}

/** The dataset file's linkProperty (each record's page URL): its name, or null when the file names none. */
export function datasetLink(path) {
  if (/\.(csv|tsv|jsonl)$/i.test(path)) return null;
  const data = JSON.parse(readFileSync(path, 'utf8'));
  return (data && !Array.isArray(data) && typeof data.linkProperty === 'string' && data.linkProperty) || null;
}

/** {property: type} of a dataset file, when it says (the runtime shape's properties, or a field schema). */
export function datasetTypes(path) {
  const data = /\.(csv|tsv|jsonl)$/i.test(path) ? tableOf(path) : JSON.parse(readFileSync(path, 'utf8'));
  if (data && data.schema && Array.isArray(data.schema.fields) && data.schema.fields.every((f) => !f.type)) return null;
  if (data && !Array.isArray(data) && data.properties && typeof data.properties === 'object') return Object.fromEntries(Object.entries(data.properties).map(([k, v]) => [k, (v && v.type) || 'text']));
  if (data && data.schema && Array.isArray(data.schema.fields)) {
    const map = { integer: 'number', number: 'number', array: 'list', boolean: 'boolean', date: 'date', datetime: 'date' };
    return Object.fromEntries(data.schema.fields.map((f) => [f.name, map[f.type] || 'text']));
  }
  return null;
}

/** The values a dataset file holds in one column, as text (a rich cell's value, each item of a list); [] when the file
    has no rows here. What a literal `selected:` is checked against (CONTRACT §33). */
export function datasetValues(path, column) {
  const rowsOf = (file) => {
    if (/\.(csv|tsv)$/i.test(file)) return parseCSV(readFileSync(file, 'utf8'), { sep: /\.tsv$/i.test(file) ? '\t' : ',', schema: tableOf(file).schema });
    if (/\.jsonl$/i.test(file)) return parseJSONL(readFileSync(file, 'utf8'));
    const data = JSON.parse(readFileSync(file, 'utf8'));
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.rows)) return data.rows;
    // a sidecar whose `path` names the rows (CONTRACT §3)
    if (data && typeof data.path === 'string') { const at = resolve(dirname(file), data.path); return existsSync(at) ? rowsOf(at) : []; }
    return [];
  };
  const out = new Set();
  for (const r of rowsOf(path)) {
    let v = r && typeof r === 'object' ? r[column] : undefined;
    if (v && typeof v === 'object' && !Array.isArray(v) && 'value' in v) v = v.value;
    for (const x of Array.isArray(v) ? v : [v]) if (x !== null && x !== undefined && x !== '') out.add(String(x));
  }
  return out;
}

const escapeRe = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The first file (sorted, folder by folder) a per-pick dataset's data: names under `dir` (CONTRACT §33): each
    {placeholder} matches any one path segment. null when none does. */
export function firstMatch(dir, template) {
  const parts = String(template).split('/');
  const walk = (at, i) => {
    if (i === parts.length) { try { return statSync(at).isFile() ? at : null; } catch { return null; } }
    const part = parts[i];
    if (!/\{[^{}]+\}/.test(part)) { const next = resolve(at, part); return existsSync(next) ? walk(next, i + 1) : null; }
    const re = new RegExp(`^${part.split(/\{[^{}]+\}/).map(escapeRe).join('[^/]+')}$`);
    let names;
    try { names = readdirSync(at).sort(); } catch { return null; }
    for (const n of names) {
      if (!re.test(n)) continue;
      const got = walk(join(at, n), i + 1);
      if (got) return got;
    }
    return null;
  };
  return walk(dir, 0);
}

function* filterStrings(node, path) {
  if (typeof node === 'string') yield [path, node];
  else if (node && typeof node === 'object' && !Array.isArray(node)) {
    for (const [k, v] of Object.entries(node)) if (Array.isArray(v)) for (let i = 0; i < v.length; i++) yield* filterStrings(v[i], [...path, k, i]);
  }
}

function* chartFields(node, path) {
  if (Array.isArray(node)) { for (let i = 0; i < node.length; i++) yield* chartFields(node[i], [...path, i]); return; }
  if (!node || typeof node !== 'object') return;
  for (const [k, v] of Object.entries(node)) {
    if (k === 'field' && typeof v === 'string') yield [[...path, k], v];
    else yield* chartFields(v, [...path, k]);
  }
}

const asList = (x) => (Array.isArray(x) ? x : x === undefined || x === null ? [] : [x]);
const PIVOTED = Symbol('pivot');
/** The names one Vega-Lite transform makes (kit gap 5): calculate, timeUnit, bin and stack `as` (a bin's or a stack's
    one name also makes <as>_end), aggregate, joinaggregate and window ops' `as`, fold (key, value), density (value,
    density), quantile (prob, value), lookup's `as` or its fields. A pivot makes a column per value: PIVOTED. */
export function transformMade(t) {
  if (!t || typeof t !== 'object') return [];
  if (t.pivot !== undefined) return [PIVOTED];
  const out = [];
  const pair = (as) => (typeof as === 'string' ? [as, `${as}_end`] : asList(as));
  if (t.calculate !== undefined || t.timeUnit !== undefined) out.push(...asList(t.as));
  if (t.bin !== undefined) out.push(...pair(t.as));
  if (t.stack !== undefined) out.push(...pair(t.as));
  for (const k of ['aggregate', 'joinaggregate', 'window']) for (const op of asList(t[k])) if (op && typeof op === 'object' && op.as) out.push(op.as);
  if (t.fold !== undefined) out.push(...(t.as ? asList(t.as) : ['key', 'value']));
  if (t.density !== undefined) out.push(...(t.as ? asList(t.as) : ['value', 'density']));
  if (t.quantile !== undefined) out.push(...(t.as ? asList(t.as) : ['prob', 'value']));
  if (t.loess !== undefined || t.regression !== undefined || t.flatten !== undefined) out.push(...asList(t.as));
  if (t.lookup !== undefined) out.push(...(t.as ? asList(t.as) : asList(t.from && t.from.fields)));
  return out.filter((x) => typeof x === 'string' || x === PIVOTED);
}

const CHILDREN = ['layer', 'hconcat', 'vconcat', 'concat'];
/** [path, field] for every column a chart block reads (kit gap 5): every `field:` of a spec (its encoding, its own
    transforms') that no transform in its scope makes. A spec's scope is its parent's and its own `transform`'s names: the
    chart's own transform reaches every layer (it runs first), a layer's reaches only that layer. After a pivot any name
    may be a column, so nothing in that scope is named. */
function* chartRefs(node, path, made = new Set()) {
  if (!node || typeof node !== 'object' || Array.isArray(node)) return;
  const here = new Set(made);
  for (const t of asList(node.transform)) for (const n of transformMade(t)) here.add(n);
  if (here.has(PIVOTED)) return;
  for (const [k, v] of Object.entries(node)) {
    if (CHILDREN.includes(k) && Array.isArray(v)) { for (let i = 0; i < v.length; i++) yield* chartRefs(v[i], [...path, k, i], here); continue; }
    if (k === 'spec' && v && typeof v === 'object') { yield* chartRefs(v, [...path, k], here); continue; }
    for (const [at, name] of chartFields(v, [...path, k])) if (!here.has(name)) yield [at, name];
  }
}

/** [path, property] for every property the file names, wherever it names one. */
export function* referenced(doc) {
  const str = (x) => typeof x === 'string' && x;
  yield* facetNames(doc.facets, ['facets']);
  if (doc.open && typeof doc.open === 'object' && str(doc.open.url)) yield [['open', 'url'], doc.open.url];
  for (const [path, src] of filterStrings(doc.filters, ['filters'])) for (const n of safeNames(src)) yield [path, n];
  yield* summaryNames(doc.summary, ['summary']);
  for (const [vi, view] of (doc.views || []).entries()) {
    if (!view || typeof view !== 'object') continue;
    yield* viewNames(view, ['views', vi]);
  }
}

/** [path, property] for every property one view entry names, at `b` (a top-level view, or a record section's embedded
    one). The properties of whatever dataset the view reads: the caller picks it. */
function* viewNames(view, b) {
  const str = (x) => typeof x === 'string' && x;
  for (const [i, n] of (view.order || []).entries()) yield [[...b, 'order', i], n];
  for (const [i, s] of (view.sort || []).entries()) yield [[...b, 'sort', i, 'property'], s && s.property];
  for (const k of ['groupBy', 'subGroupBy']) if (view[k] && typeof view[k] === 'object') yield [[...b, k, 'property'], view[k].property];
  yield* tileNames(view.tiles, [...b, 'tiles']);
  for (const [gi, g] of (Array.isArray(view.groupings) ? view.groupings : []).entries()) {
    if (!g || typeof g !== 'object') continue;
    for (const k of ['groupBy', 'subGroupBy']) if (g[k] && typeof g[k] === 'object') yield [[...b, 'groupings', gi, k, 'property'], g[k].property];
    yield* tileNames(g.tiles, [...b, 'groupings', gi, 'tiles']);
  }
  for (const [i, n] of (view.splitBy || []).entries()) yield [[...b, 'splitBy', i], n];
  for (const k of ['display', 'columnSize', 'summaries']) for (const n of Object.keys(view[k] || {})) yield [[...b, k, n], n];
  if (view.value && typeof view.value === 'object') for (const k of ['property', 'per']) if (view.value[k]) yield [[...b, 'value', k], view.value[k]];
  for (const k of ['image', 'media', 'mesh', 'meshView', 'start', 'end', 'title', 'color', 'coordinates']) if (str(view[k])) yield [[...b, k], view[k]];
  for (const [i, n] of (view.caption || []).entries()) yield [[...b, 'caption', i], n];
  for (const [k, sub] of [['edges', 'property'], ['edges', 'label'], ['tree', 'parent'], ['tree', 'path'], ['sketch', 'diameter'], ['sketch', 'length']]) {
    if (view[k] && typeof view[k] === 'object' && view[k][sub]) yield [[...b, k, sub], view[k][sub]];
  }
  // lineage (§21): every property-valued key of the block, and each kept: property
  const lin = view.lineage && typeof view.lineage === 'object' ? view.lineage : {};
  for (const k of ['parents', 'x', 'xLabel', 'image', 'label']) if (str(lin[k])) yield [[...b, 'lineage', k], lin[k]];
  for (const n of Object.keys(lin.kept && typeof lin.kept === 'object' && !Array.isArray(lin.kept) ? lin.kept : {})) yield [[...b, 'lineage', 'kept', n], n];
  const ru = view.rollup && typeof view.rollup === 'object' ? view.rollup : {};
  for (const k of ['keep', 'dims']) for (const [i, n] of (Array.isArray(ru[k]) ? ru[k] : []).entries()) yield [[...b, 'rollup', k, i], n];
  for (const n of Object.keys(ru.agg || {})) yield [[...b, 'rollup', 'agg', n], n];
  for (const [g, list] of Object.entries(view.columnGroups || {})) for (const [i, n] of (Array.isArray(list) ? list : []).entries()) yield [[...b, 'columnGroups', g, i], n];
  for (const n of Object.keys(view.stats || {})) yield [[...b, 'stats', n], n];
  for (const [si, s] of ((view.record || {}).sections || []).entries()) for (const [i, n] of ((s || {}).properties || []).entries()) yield [[...b, 'record', 'sections', si, 'properties', i], n];
  for (const n of Object.keys((view.record || {}).visibility || {})) if (!n.startsWith('@')) yield [[...b, 'record', 'visibility', n], n];
  for (const n of Object.keys((view.compare || {}).better || {})) yield [[...b, 'compare', 'better', n], n];
  const hover = view.hover || {};
  for (const k of ['image', 'title']) if (hover[k]) yield [[...b, 'hover', k], hover[k]];
  for (const [i, n] of (hover.fields || []).entries()) yield [[...b, 'hover', 'fields', i], n];
  yield* chartRefs(view.chart, [...b, 'chart']);
  for (const [i, g] of (view.guides || []).entries()) if (g && g.envelope) yield [[...b, 'guides', i, 'envelope'], g.envelope];
  const kpi = view.kpi || {};
  for (const k of ['property', 'per']) if ((kpi.value || {})[k]) yield [[...b, 'kpi', 'value', k], kpi.value[k]];
  for (const k of ['x', 'y']) if ((kpi.spark || {})[k]) yield [[...b, 'kpi', 'spark', k], kpi.spark[k]];
  // CONTRACT §35: a property target (the newest row's value); a number needs no column
  if (str(kpi.target)) yield [[...b, 'kpi', 'target'], kpi.target];
  const against = (kpi.compare || {}).against;
  if (against && against !== 'previous' && against !== 'target') yield [[...b, 'kpi', 'compare', 'against'], against];
  const better = (kpi.compare || {}).better;
  if (str(better) && better !== 'higher' && better !== 'lower') yield [[...b, 'kpi', 'compare', 'better'], better];
  for (const [path, src] of filterStrings(view.filters, [...b, 'filters'])) for (const n of safeNames(src)) yield [path, n];
  if (Array.isArray(view.facets)) yield* facetNames(view.facets, [...b, 'facets']);
  if (view.open && typeof view.open === 'object' && str(view.open.url)) yield [[...b, 'open', 'url'], view.open.url];
  // CONTRACT §35: the gate matrix's columns, a limits end that is a property (null and numbers need no column), the
  // path overlay's colour
  const tracker = view.tracker && typeof view.tracker === 'object' ? view.tracker : {};
  if (str(tracker.column)) yield [[...b, 'tracker', 'column'], tracker.column];
  for (const block of ['timeseries', 'plot']) {
    const limits = view[block] && typeof view[block] === 'object' && view[block].limits;
    if (!limits || typeof limits !== 'object') continue;
    for (const side of ['warn', 'error']) for (const [i, end] of (Array.isArray(limits[side]) ? limits[side] : []).entries()) if (str(end)) yield [[...b, block, 'limits', side, i], end];
  }
  const tr = view.trajectory3d && typeof view.trajectory3d === 'object' ? view.trajectory3d : {};
  if (str(tr.color)) yield [[...b, 'trajectory3d', 'color'], tr.color];
  yield* mapNames(view, b);
  // CONTRACT §43: the avatar's colour property and a summary view's cells
  if (view.avatar && typeof view.avatar === 'object' && str(view.avatar.color)) yield [[...b, 'avatar', 'color'], view.avatar.color];
  yield* summaryNames(view.summary, [...b, 'summary']);
}

/** The properties a `summary:` block's cells read (CONTRACT §43): each cell's filters, `when.property`, `value.property`
    and `spark.x`. */
function* summaryNames(summary, at) {
  const str = (x) => typeof x === 'string' && x;
  const cells = summary && typeof summary === 'object' && Array.isArray(summary.cells) ? summary.cells : [];
  for (const [i, c] of cells.entries()) {
    if (!c || typeof c !== 'object') continue;
    const b = [...at, 'cells', i];
    for (const [path, src] of filterStrings(c.filters, [...b, 'filters'])) for (const n of safeNames(src)) yield [path, n];
    if (c.when && typeof c.when === 'object' && str(c.when.property)) yield [[...b, 'when', 'property'], c.when.property];
    if (c.value && typeof c.value === 'object' && str(c.value.property)) yield [[...b, 'value', 'property'], c.value.property];
    if (c.spark && typeof c.spark === 'object' && str(c.spark.x)) yield [[...b, 'spark', 'x'], c.spark.x];
  }
}

/** The map view's property-valued keys (CONTRACT §42): each layer's row properties and the properties its filter,
    of: and count: expressions read, then time:, multiples.by, drawBy and drawSum. A region layer's label: and key:
    name the geometry file's feature properties, not the data's, so they are not checked here. */
function* mapNames(view, b) {
  const str = (x) => typeof x === 'string' && x;
  for (const [i, L] of (Array.isArray(view.layers) ? view.layers : []).entries()) {
    if (!L || typeof L !== 'object') continue;
    const at = [...b, 'layers', i];
    // join: id is every row's own id (CONTRACT §3), which a data file need not list among its properties
    for (const k of ['coordinates', 'weight', 'path', 'from', 'to', 'text', 'join']) if (str(L[k]) && !(k === 'join' && L[k] === 'id')) yield [[...at, k], L[k]];
    if (str(L.value)) yield [[...at, 'value'], L.value];
    for (const k of ['value', 'size', 'width']) if (L[k] && typeof L[k] === 'object' && str(L[k].property)) yield [[...at, k, 'property'], L[k].property];
    if (L.bivariate && typeof L.bivariate === 'object') for (const k of ['x', 'y']) if (str(L.bivariate[k])) yield [[...at, 'bivariate', k], L.bivariate[k]];
    if (L.type === 'points' && str(L.label)) yield [[...at, 'label'], L.label];
    for (const [j, d] of (Array.isArray(L.detail) ? L.detail : str(L.detail) ? [L.detail] : []).entries()) yield [[...at, 'detail', ...(Array.isArray(L.detail) ? [j] : [])], d];
    for (const k of ['filter', 'of', 'count']) if (str(L[k])) for (const n of safeNames(L[k])) yield [[...at, k], n];
  }
  const t = view.time;
  if (str(t)) yield [[...b, 'time'], t];
  else if (t && typeof t === 'object' && str(t.property)) yield [[...b, 'time', 'property'], t.property];
  if (view.multiples && typeof view.multiples === 'object' && str(view.multiples.by)) yield [[...b, 'multiples', 'by'], view.multiples.by];
  for (const k of ['drawBy', 'drawSum']) if (str(view[k])) yield [[...b, k], view[k]];
}

function* tileNames(tiles, at) {
  if (!tiles || typeof tiles !== 'object') return;
  for (const k of ['property', 'image', 'link']) if (typeof tiles[k] === 'string' && tiles[k]) yield [[...at, k], tiles[k]];
}

/** [path, view] for every inline view a record section carries (CONTRACT §35), in the file's top-level views. */
export function* embeddedViews(doc) {
  for (const [vi, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    const sections = view && typeof view === 'object' && view.record && Array.isArray(view.record.sections) ? view.record.sections : [];
    for (const [si, s] of sections.entries()) if (s && typeof s === 'object' && s.view && typeof s.view === 'object' && !Array.isArray(s.view)) yield [['views', vi, 'record', 'sections', si, 'view'], s.view];
  }
}

/** The columns an embedded view's typed block reads, which a top-level view's block is not checked for (the cards'
    own x, y and series). WHY only here: an embedded view is checked whole (CONTRACT §35). Yields [path, property]. */
function* blockNames(view, b) {
  const str = (x) => typeof x === 'string' && x;
  for (const block of ['timeseries', 'plot']) {
    const s = view[block];
    if (!s || typeof s !== 'object') continue;
    for (const k of ['x', 'series']) if (str(s[k])) yield [[...b, block, k], s[k]];
    for (const [i, n] of (Array.isArray(s.y) ? s.y : [s.y]).entries()) if (str(n)) yield [[...b, block, 'y', ...(Array.isArray(s.y) ? [i] : [])], n];
  }
  for (const block of ['tracker', 'levels']) {
    const s = view[block];
    if (s && typeof s === 'object') for (const k of ['state', 'label', 'by']) if (str(s[k])) yield [[...b, block, k], s[k]];
  }
}

/** The `this.<column>` names an expression binds (the peeked row's columns): bindThis's own scan, so a name inside
    quotes or after a dot is never one, run against a front that records what it is asked for. */
function thisNames(src) {
  const seen = new Set();
  bindThis(src, new Proxy({}, { get: (_, key) => { if (typeof key === 'string') seen.add(key); } }));
  return [...seen];
}

/** [path, property, dataset] for every column a record section's embedded view names (CONTRACT §35): its own keys, in
    the dataset its `from:` names, and each `this.<column>` of its filters, in the OUTER view's (the peeked row's).
    `dataset` undefined means the outer view's, which is also the default for an embedded view with no from:. */
export function* sectionNames(doc) {
  for (const [at, view] of embeddedViews(doc)) {
    const ds = typeof view.from === 'string' && view.from ? view.from : undefined;
    for (const [path, name] of viewNames(view, at)) yield [path, name, ds];
    for (const [path, name] of blockNames(view, at)) yield [path, name, ds];
    for (const [path, src] of filterStrings(view.filters, [...at, 'filters'])) for (const name of thisNames(src)) yield [path, name, undefined];
  }
}

/** The grouped gallery's rules, past the schema (CONTRACT §20): a view's `grouping` names one of its `groupings` (else
    the view's own groupBy is used: a warning), each id once, a level groups by `bins:` or by `by:` (not both), and
    with the data's types, bins on a property that is not a number warn. Yields [level, path, message]. */
export function* groupingProblems(doc, types = null) {
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    if (!view || typeof view !== 'object') continue;
    const list = Array.isArray(view.groupings) ? view.groupings : [];
    const ids = list.map((g) => (g && typeof g === 'object' ? g.id : undefined));
    for (const [j, id] of ids.entries()) if (typeof id === 'string' && ids.indexOf(id) !== j) yield ['error', ['views', i, 'groupings', j, 'id'], `id '${id}' is used twice: a grouping is picked by its id`];
    if (typeof view.grouping === 'string' && !ids.includes(view.grouping)) {
      yield ['warning', ['views', i, 'grouping'], `'${view.grouping}' names no groupings entry${suggest(view.grouping, ids.filter((x) => typeof x === 'string'))}; the view's own groupBy is used`];
    }
    const levels = [[view.groupBy, ['views', i, 'groupBy']], [view.subGroupBy, ['views', i, 'subGroupBy']]];
    for (const [j, g] of list.entries()) if (g && typeof g === 'object') for (const k of ['groupBy', 'subGroupBy']) levels.push([g[k], ['views', i, 'groupings', j, k]]);
    for (const [level, at] of levels) {
      // PEP 0020: `by` and `bins` make their own buckets, and a path has no meaning over them
      if (level && typeof level === 'object' && level.path !== undefined && (level.by !== undefined || level.bins !== undefined)) yield ['error', [...at, 'path'], `a level groups by path: or by ${level.by !== undefined ? 'by:' : 'bins:'}, not both`];
      if (!level || typeof level !== 'object' || level.bins === undefined) continue;
      if (level.by !== undefined) { yield ['error', [...at, 'bins'], 'a level groups by bins: (numbers) or by: (dates), not both']; continue; }
      const type = types && types[level.property];
      if (type && type !== 'number') yield ['warning', [...at, 'bins'], `'bins' groups numbers, and '${level.property}' is ${type}: every row falls in "No ${level.property}"`];
    }
  }
}

const openMode = (o) => (typeof o === 'string' ? o : o && typeof o === 'object' ? o.mode : undefined);
const openUrl = (o) => (o && typeof o === 'object' && typeof o.url === 'string' ? o.url : undefined);

/** `open:`'s own rule, past the schema: `link` needs a URL (the `url:` key, else the data's linkProperty); without one
    the page falls back to side. Only when the data is known to name no link (`link` null), since a page may set one
    from script. Yields [level, path, message]. */
export function* openProblems(doc, link) {
  if (link !== null) return;
  const top = doc.open;
  const say = 'link needs a URL: no url: here and the data names no linkProperty, so it falls back to side';
  if (openMode(top) === 'link' && !openUrl(top)) yield ['warning', ['open'], `open: ${say} (in every view that does not say)`];
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    if (!view || typeof view !== 'object' || openMode(view.open) !== 'link') continue;
    if (!openUrl(view.open) && !openUrl(top)) yield ['warning', ['views', i, 'open'], `open: ${say}`];
  }
}

/** [path, property] for every property a rail names: a facet's property, a tree's levels, a has or search group's
    properties, a gallery's image column, and the properties inside a popular filter's expressions. */
function* facetNames(list, at) {
  for (const [i, f] of (Array.isArray(list) ? list : []).entries()) {
    if (typeof f === 'string') { yield [[...at, i], f]; continue; }
    if (!f || typeof f !== 'object') continue;
    if (f.property) yield [[...at, i, 'property'], f.property];
    for (const k of ['levels', 'properties']) for (const [j, n] of (Array.isArray(f[k]) ? f[k] : []).entries()) yield [[...at, i, k, j], n];
    if (typeof f.image === 'string') yield [[...at, i, 'image'], f.image];
    for (const [path, src] of popularFilters(f, [...at, i])) for (const n of safeNames(src)) yield [path, n];
  }
}

function* popularFilters(f, at) {
  for (const [j, o] of (f && Array.isArray(f.options) ? f.options : []).entries()) {
    if (typeof o === 'string') yield [[...at, 'options', j], o];
    else if (o && typeof o.filter === 'string') yield [[...at, 'options', j, 'filter'], o.filter];
  }
}

/** A group level's `by:` buckets dates: on a property the data types otherwise (with `types`), say what happens.
    Yields [level, path, message]. */
export function* timeProblems(doc, types = null) {
  if (!types) return;
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    for (const k of ['groupBy', 'subGroupBy']) {
      const level = view && view[k];
      const type = level && typeof level === 'object' && level.by && types[level.property];
      if (type && type !== 'date') yield ['warning', ['views', i, k, 'by'], `'by: ${level.by}' groups dates, and '${level.property}' is ${type}: a value that is not an ISO date falls in "No ${level.property}"`];
    }
  }
}

const NUMBER_KINDS = new Set(['range', 'slider', 'slider-histogram', 'buckets', 'rating', 'min-level']);
const GROUP_KINDS = { tree: 'levels', has: 'properties', search: 'properties' };

/** The rail's own rules, past the schema: a facet names what it filters, and its kind fits the property's type (with
    `types`, {property: type} from the data). Yields [level, path, message]. */
export function* facetProblems(doc, types = null) {
  const lists = [[doc.facets, ['facets']], ...(Array.isArray(doc.views) ? doc.views : []).map((v, i) => [v && v.facets, ['views', i, 'facets']])];
  for (const [list, at] of lists) {
    const owned = (Array.isArray(list) ? list : []).map((f) => (typeof f === 'string' ? f : f && typeof f === 'object' ? f.property : undefined)).filter((p) => typeof p === 'string' && p);
    for (const [i, f] of (Array.isArray(list) ? list : []).entries()) {
      if (!f || typeof f !== 'object' || Array.isArray(f)) continue;
      const as = f.as || 'values';
      const path = [...at, i];
      // kit gap 8: parent names another facet of this rail, the one whose pick this facet's values nest under
      if (f.parent !== undefined) {
        if (f.parent === f.property) yield ['error', [...path, 'parent'], `'${f.parent}' cannot be its own parent: parent names another facet of this rail, the one this facet's values nest under`];
        else if (!owned.includes(f.parent)) yield ['error', [...path, 'parent'], `'${f.parent}' is no facet of this rail${suggest(String(f.parent), owned.filter((p) => p !== f.property))}: parent names the facet this facet's values nest under`];
      }
      if (as === 'popular') { if (!Array.isArray(f.options) || !f.options.length) yield ['error', path, "a popular facet needs 'options': filter expressions, or {label, filter}"]; continue; }
      if (as === 'current') continue;
      // a nav facet with no property lists the groups of the view's current groupBy (CONTRACT §20)
      if (as === 'nav' && !f.property) continue;
      const group = GROUP_KINDS[as];
      if (!f.property && !(group && Array.isArray(f[group]) && f[group].length)) { yield ['error', path, `a ${as} facet needs 'property'${group ? ` or '${group}'` : ''}`]; continue; }
      const p = f.property || f[group][0];
      const type = types && types[p];
      if (!type) continue;
      if (NUMBER_KINDS.has(as) && type !== 'number' && !(as === 'range' && type === 'date')) yield ['error', [...path, 'as'], `'${as}' needs a number property${as === 'range' ? ' or a date' : ''}; '${p}' is ${type} (did you mean 'values'?)`];
      if (as === 'date' && type !== 'date') yield ['warning', [...path, 'as'], `'date' reads ISO dates; '${p}' is ${type}, so its values compare as text`];
      if (as === 'chips' && type !== 'list') yield ['warning', [...path, 'as'], `'chips' is for a list property (tags); '${p}' is ${type}, so each row has one chip`];
    }
  }
}

function safeNames(src) {
  try { return expressionProperties(src); } catch { return []; }
}

const OBSIDIAN_ONLY = /(^|[^\w.])(file|this)\b|(^|[^\w.])[A-Za-z_]\w*\s*\(/;

function* expressions(doc) {
  yield* filterStrings(doc.filters, ['filters']);
  for (const [vi, view] of (doc.views || []).entries()) if (view && typeof view === 'object') yield* filterStrings(view.filters, ['views', vi, 'filters']);
  for (const [i, f] of (Array.isArray(doc.facets) ? doc.facets : []).entries()) yield* popularFilters(f, ['facets', i]);
  for (const [vi, view] of (doc.views || []).entries()) for (const [i, f] of (view && Array.isArray(view.facets) ? view.facets : []).entries()) yield* popularFilters(f, ['views', vi, 'facets', i]);
}

// ------------------------------------------------------------------------------------------------ 3D (CONTRACT §32)

const SCENE_BLOCKS = new Set(['scene3d', 'trajectory3d', 'voxels']);
/** A projection's names: perspective and the six faces, named from the scene's up axis (CONTRACT §32). */
export const FACES = ['perspective', 'top', 'bottom', 'front', 'back', 'left', 'right'];
const OBLIQUE = '{dir: [-1, -1, -1], up: [0, 0, 1]}';
// WHY a table, not only the spelling distance: the words CAD tools and drafting use for a view ("iso", "plan", "xz")
// are far from the face that shows it, and an agent writes them. A view no face has (diagonal, isometric) is a {dir}.
const PROJECTION_WORDS = {
  diagonal: OBLIQUE, oblique: OBLIQUE, iso: OBLIQUE, isometric: OBLIQUE, axonometric: OBLIQUE, corner: OBLIQUE, 'three-quarter': OBLIQUE, home: OBLIQUE,
  plan: 'top', above: 'top', overhead: 'top', xy: 'top', 'top-down': 'top', topdown: 'top', ortho: 'top', orthographic: 'top', '2d': 'top',
  below: 'bottom', underneath: 'bottom', under: 'bottom',
  xz: 'front', elevation: 'front',
  yz: 'right', side: 'right',
  '3d': 'perspective', persp: 'perspective', orbit: 'perspective', free: 'perspective',
};
const INF_WORDS = new Set(['inf', '.inf', '+inf', '+.inf', 'infinity', '+infinity', 'forever', 'unlimited', 'max']);

/** The sentence for a projection the schema refused. */
export function projectionMessage(value) {
  const choices = `${FACES.join(', ')}, or {dir: [x, y, z], up: [x, y, z]}`;
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const extra = Object.keys(value).filter((k) => k !== 'dir' && k !== 'up');
    if (extra.length) return `unknown key '${extra[0]}'${suggest(extra[0], ['dir', 'up'])}: a projection is ${choices}`;
    return `a projection {…} needs dir: [x, y, z], the direction the camera looks`;
  }
  if (typeof value !== 'string') return `a projection is ${choices}`;
  let hint = suggest(value, FACES);
  if (!hint) {
    const word = PROJECTION_WORDS[value.trim().toLowerCase().replace(/[\s_]+/g, '-')];
    if (word === OBLIQUE) hint = ` (did you mean ${OBLIQUE}, an oblique view?)`;
    else if (word) hint = ` (did you mean '${word}'?)`;
  }
  return `'${value}' is not a projection: ${choices}${hint}`;
}

/** The sentence for a decay the schema refused (or that YAML 1.1 read as a float infinity). WHY -1 → inf: -1 is the
    "no limit" sentinel of many trail settings; any other negative number is read as its size. */
export function decayMessage(value) {
  const finite = typeof value !== 'number' || Number.isFinite(value);
  const shown = typeof value === 'string' ? `'${value}'` : !finite ? `'${value > 0 ? '.inf' : value < 0 ? '-.inf' : '.nan'}'` : JSON.stringify(value);
  let hint = '';
  if (typeof value === 'number') {
    if (value === -1) hint = ' (did you mean inf, the whole past up to t?)';
    else if (!finite) hint = ' (did you mean inf?)';
    else if (value < 0) hint = ` (did you mean ${-value}?)`;
  } else if (typeof value === 'string') {
    const k = value.trim().toLowerCase();
    const m = /^(\d+(?:\.\d+)?)\s*(ms|s|sec|secs|second|seconds)$/.exec(k);
    if (INF_WORDS.has(k)) hint = ' (did you mean inf?)';
    else if (k === 'all') hint = ' (did you mean show: all, every time step?)';
    else if (m) hint = ` (did you mean ${m[2] === 'ms' ? Number(m[1]) / 1000 : Number(m[1])}?)`;
  }
  return `${shown} is not a decay: seconds behind t (0 or more), or inf${hint}`;
}

/** The sentence for an axes setting the schema refused. WHY off → none: YAML 1.1 (PyYAML, Obsidian's older readers)
    reads `off` as false, so the key says none, as legend: none and title: none do. */
export function axesMessage(value) {
  const shown = typeof value === 'string' ? `'${value}'` : JSON.stringify(value);
  const k = String(value).trim().toLowerCase();
  const hint = ['off', 'false', 'no', 'hide', 'hidden'].includes(k) ? " (did you mean 'none'?)"
    : ['on', 'true', 'yes', 'show'].includes(k) ? " (did you mean 'auto'?)" : suggest(value, ['auto', 'none']);
  return `${shown} is not an axes setting: auto (ticks on a face-aligned view) or none${hint}`;
}

/** A 3D key's own sentence for a schema error at that key (CONTRACT §32), or null for the schema's own. */
function sceneMessage(path, e) {
  const b = path.findIndex((p) => SCENE_BLOCKS.has(p));
  if (path[0] !== 'views' || b !== 2) return null;
  const rel = path.slice(b + 1);
  if (rel.length !== 1) return null;
  const [key] = rel;
  if (key === 'projection') return projectionMessage(e.data);
  if (key === 'decay') return decayMessage(e.data);
  if (key === 'axes') return axesMessage(e.data);
  if (key === 'workspace' && (e.keyword === 'oneOf' || e.keyword === 'required')) return 'a workspace is {model: <glb>} or {box: [[x0, y0, z0], [x1, y1, z1]]}, one of them';
  return null;
}

const isObj = (x) => !!x && typeof x === 'object' && !Array.isArray(x);
const isStr = (x) => typeof x === 'string' && x !== '';
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === 'number' && Number.isFinite(x));
const vecText = (v) => `[${v.join(', ')}]`;

/** The 3D blocks' own rules, past the schema (CONTRACT §32): a projection's dir is a direction and its up crosses it;
    a decay YAML 1.1 read as a float infinity; in a file with no datasets, a layer naming one (it draws nothing).
    `dashboard`: the file has datasets, links or layout (model.js names a layer's unknown dataset there). Yields
    [level, path, message]. */
export function* sceneProblems(doc, dashboard = false) {
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    if (!isObj(view)) continue;
    for (const block of SCENE_BLOCKS) {
      const s = view[block];
      if (!isObj(s)) continue;
      const at = ['views', i, block];
      const p = s.projection;
      if (isObj(p) && isVec(p.dir)) {
        const [a, b, c] = p.dir;
        if (Math.hypot(a, b, c) === 0) yield ['error', [...at, 'projection', 'dir'], 'dir is the direction the camera looks: it cannot be [0, 0, 0]'];
        else if (isVec(p.up)) {
          const [u, v, w] = p.up;
          const cross = Math.hypot(b * w - c * v, c * u - a * w, a * v - b * u);
          if (cross <= 1e-9 * Math.hypot(a, b, c) * Math.hypot(u, v, w)) {
            const along = Math.abs(c) >= 0.999 * Math.hypot(a, b, c);
            yield ['error', [...at, 'projection', 'up'], `up ${vecText(p.up)} is parallel to dir ${vecText(p.dir)}: the screen's up must cross the view (did you mean up: ${along ? '[0, 1, 0]' : '[0, 0, 1]'}?)`];
          }
        }
      }
      if (typeof s.decay === 'number' && !Number.isFinite(s.decay)) yield ['error', [...at, 'decay'], decayMessage(s.decay)];
    }
    if (!dashboard) {
      for (const [path, name] of layerRefs(view)) {
        yield ['warning', ['views', i, ...path], `'${name}' names a dashboard dataset, and this file has no datasets: (a plain <data-views> has only its own rows, so this draws nothing)`];
      }
    }
  }
}

// trajectory3d's defaults: the trajectory contract's own column names (gallery/robotics/CONTRACT.md)
const TRAJECTORY_POSES = { x: 'x_mm', y: 'y_mm', z: 'z_mm', frame: 'frame', body: 'body' };
const TRAJECTORY_BINDING = { series: 'situation', family: 'source', run: 'run', t: 't' };
const LINK_WHY = 'a link is posed from <link>_x/_y/_z and <link>_qw/_qx/_qy/_qz';
const COMPARE_WHY = "compare reads a's columns as poses names them, b's as ref_<column>, and reference";

/** [path, column, dataset, why] for every column the 3D cards read (CONTRACT §32): each scene3d layer's, the
    trajectory3d binding's (given, or the contract's name it defaults to; `why` then says so), compare's in its
    difference dataset, each robot link's first column, and voxels'. `dataset` is the layer dataset a column lives in,
    undefined for the view's own. */
export function* sceneNames(doc) {
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    if (!isObj(view)) continue;
    const s = view.type === 'scene3d' && isObj(view.scene3d) ? view.scene3d : null;
    for (const [j, l] of (s && Array.isArray(s.layers) ? s.layers : []).entries()) {
      if (!isObj(l)) continue;
      const at = ['views', i, 'scene3d', 'layers', j];
      const ds = isStr(l.data) ? l.data : undefined;
      for (const k of ['x', 'y', 'z', 'color', 't', 'by']) if (isStr(l[k])) yield [[...at, k], l[k], ds];
      for (const k of ['by', 'quat', 'from', 'to', 'at', 'min', 'max']) for (const [n, c] of (Array.isArray(l[k]) ? l[k] : []).entries()) if (isStr(c)) yield [[...at, k, n], c, ds];
      for (const [n, link] of (Array.isArray(l.links) ? l.links : []).entries()) if (isStr(link)) yield [[...at, 'links', n], `${link}_x`, ds, LINK_WHY];
    }
    if (view.type === 'trajectory3d') {
      const tr = isObj(view.trajectory3d) ? view.trajectory3d : {};
      const at = isObj(view.trajectory3d) ? ['views', i, 'trajectory3d'] : ['views', i, 'type'];
      const poses = isObj(tr.poses) ? tr.poses : {};
      const bound = (key, given, fallback, where) => (isStr(given) ? [where, given, undefined] : [at, fallback, undefined, `trajectory3d reads it for ${key} by default; name the column there`]);
      for (const [k, d] of Object.entries(TRAJECTORY_POSES)) yield bound(`poses.${k}`, poses[k], d, [...at, 'poses', k]);
      for (const [n, c] of (Array.isArray(poses.quat) ? poses.quat : []).entries()) if (isStr(c)) yield [[...at, 'poses', 'quat', n], c, undefined];
      for (const [k, d] of Object.entries(TRAJECTORY_BINDING)) yield bound(k, tr[k], d, [...at, k]);
      if (isObj(tr.compare) && isStr(tr.compare.data)) {
        const where = [...at, 'compare', 'data'];
        for (const k of ['x', 'y', 'z']) {
          const c = isStr(poses[k]) ? poses[k] : TRAJECTORY_POSES[k];
          yield [where, c, tr.compare.data, COMPARE_WHY];
          yield [where, `ref_${c}`, tr.compare.data, COMPARE_WHY];
        }
        yield [where, 'reference', tr.compare.data, COMPARE_WHY];
        yield [where, isStr(tr.series) ? tr.series : TRAJECTORY_BINDING.series, tr.compare.data, COMPARE_WHY];
      }
      if (isObj(tr.robots)) {
        const ds = isStr(tr.robots.data) ? tr.robots.data : undefined;
        for (const [n, link] of (Array.isArray(tr.robots.links) ? tr.robots.links : []).entries()) if (isStr(link)) yield [[...at, 'robots', 'links', n], `${link}_x`, ds, LINK_WHY];
      }
    }
    // kit gap 2: a timeseries' annotations from rows: its time and label columns, in `data` (a layer dataset) or its own
    const ts = view.type === 'timeseries' && isObj(view.timeseries) ? view.timeseries : null;
    for (const [j, a] of (ts && Array.isArray(ts.annotations) ? ts.annotations : []).entries()) {
      if (!isObj(a) || !isStr(a.x)) continue;
      const at = ['views', i, 'timeseries', 'annotations', j];
      const ds = isStr(a.data) ? a.data : undefined;
      yield [[...at, 'x'], a.x, ds];
      if (isStr(a.label)) yield [[...at, 'label'], a.label, ds];
    }
    const v = view.type === 'voxels' && isObj(view.voxels) ? view.voxels : null;
    if (v) {
      const at = ['views', i, 'voxels'];
      for (const k of ['x', 'y', 'z']) if (isStr(v[k])) yield [[...at, k], v[k], undefined];
      if (isStr(v.value) && !['time', 'runs', 'count'].includes(v.value)) yield [[...at, 'value'], v.value, undefined];
      if (isStr(v.w)) yield [[...at, 'w'], v.w, undefined];
      else if (v.value === 'time') yield [at, 'w', undefined, 'voxels sums it for value: time by default; name the column with w:'];
      if (isStr(v.run)) yield [[...at, 'run'], v.run, undefined];
      else if (v.value === 'runs') yield [at, 'run', undefined, 'voxels counts it for value: runs by default; name the column with run:'];
    }
  }
}

// ------------------------------------------------------------------------------------------------ the check

/** Check one file's text. Returns [{level, line, path, message}]. `properties` (a Set) enables the name checks. */
export function checkText(text, { properties = null, datasetName = '', types = null, link, datasets = null, perPick = null } = {}) {
  const out = [];
  let doc, lines;
  try {
    ({ doc, lines } = parseBaseWithLines(text));
  } catch (err) {
    if (!(err instanceof BaseSyntaxError)) throw err;
    return [{ level: 'error', line: err.line, path: [], message: `not valid YAML: ${err.reason}` }];
  }
  if (doc === null || doc === undefined) doc = {};
  if (typeof doc !== 'object' || Array.isArray(doc)) return [{ level: 'error', line: 1, path: [], message: 'a .base file is a mapping (filters, properties, views, ...)' }];
  const at = (path) => lineOf(lines, path);
  const errs = pickErrors(validate(doc)).map((e) => ({ e, path: pointer(e.instancePath) }));
  errs.sort((a, b) => (a.path.map(String).join('\u0000') < b.path.map(String).join('\u0000') ? -1 : a.path.map(String).join('\u0000') > b.path.map(String).join('\u0000') ? 1 : 0));
  for (const { e, path } of errs) out.push({ level: 'error', line: at(path), path, message: sceneMessage(path, e) || schemaMessage(e) });
  for (const key of Object.keys(doc)) {
    if (!TOP_KEYS.has(key)) out.push({ level: 'warning', line: at([key]), path: [key], message: `unknown top-level key '${key}'${suggest(key, TOP_KEYS)}; Bases keeps it, data-ui ignores it` });
  }
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    if (!view || typeof view !== 'object') continue;
    for (const key of Object.keys(view)) {
      if (!VIEW_KEYS.has(key)) out.push({ level: 'warning', line: at(['views', i, key]), path: ['views', i, key], message: `unknown view key '${key}'${suggest(key, VIEW_KEYS)}; Bases keeps it, data-ui ignores it` });
    }
    if (typeof view.type === 'string' && !VIEW_TYPES.has(view.type)) {
      out.push({ level: 'warning', line: at(['views', i, 'type']), path: ['views', i, 'type'], message: `data-ui cannot draw type '${view.type}'${suggest(view.type, VIEW_TYPES)} (a plugin's view? Obsidian needs that plugin too)` });
    }
  }
  // an embedded view is a view: the schema checks its type's block, and a key or type it does not know is a warning too
  for (const [path, view] of embeddedViews(doc)) {
    for (const key of Object.keys(view)) {
      if (!VIEW_KEYS.has(key)) out.push({ level: 'warning', line: at([...path, key]), path: [...path, key], message: `unknown view key '${key}'${suggest(key, VIEW_KEYS)}; Bases keeps it, data-ui ignores it` });
    }
    if (typeof view.type === 'string' && !VIEW_TYPES.has(view.type)) {
      out.push({ level: 'warning', line: at([...path, 'type']), path: [...path, 'type'], message: `data-ui cannot draw type '${view.type}'${suggest(view.type, VIEW_TYPES)} (a plugin's view? Obsidian needs that plugin too)` });
    }
  }
  for (const [path, src] of expressions(doc)) {
    try { compileExpression(src); } catch (err) {
      const obsidian = OBSIDIAN_ONLY.test(src);
      out.push({ level: obsidian ? 'warning' : 'error', line: at(path), path,
        message: obsidian ? `data-ui does not evaluate ${JSON.stringify(src)} (${err.message.replace(/ in .*$/, '')}); Obsidian does, a data-ui page shows the filter's error` : `the filter does not compile: ${err.message}` });
    }
  }
  // CONTRACT §36: the one formula data-ui runs, and what it is for. WHY only with data: a .base with none is Obsidian's own, where any
  // formula is right, and the vault's files stay clean
  for (const [name, text] of Object.entries((properties || doc.data) && doc.formulas && typeof doc.formulas === 'object' ? doc.formulas : {})) {
    if (!parseCoalesce(text)) out.push({ level: 'warning', line: at(['formulas', name]), path: ['formulas', name], message: `data-ui does not run formula '${name}' (only [a, b].filter(!value.isEmpty())[0], the first non-empty column): its column shows a dash here, and Obsidian runs it` });
  }
  for (const [i, view] of (Array.isArray(doc.views) ? doc.views : []).entries()) {
    const read = view && view.kpi && view.kpi.value && view.kpi.value.property;
    if (typeof read === 'string' && read.startsWith('formula.')) out.push({ level: 'error', line: at(['views', i, 'kpi', 'value', 'property']), path: ['views', i, 'kpi', 'value', 'property'], message: `'${read}': a headline KPI is the producer's number; a formula runs for a display column` });
  }
  for (const [level, path, message] of facetProblems(doc, types)) out.push({ level, line: at(path), path, message });
  for (const [level, path, message] of timeProblems(doc, types)) out.push({ level, line: at(path), path, message });
  for (const [level, path, message] of groupingProblems(doc, types)) out.push({ level, line: at(path), path, message });
  // WHY `link` undefined means "not known": with no data the checker cannot tell a file that needs a url: from one
  // whose data names its linkProperty
  for (const [level, path, message] of openProblems(doc, link)) out.push({ level, line: at(path), path, message });
  // a dashboard: its own structure, and each view's names checked against the dataset its `from:` picks
  const dash = doc.datasets || doc.layout || doc.links ? readDashboard(doc) : null;
  for (const [level, path, message] of sceneProblems(doc, !!dash)) out.push({ level, line: at(path), path, message });
  if (dash) for (const [level, path, message] of dashboardProblems(doc, dash, datasets, perPick)) out.push({ level, line: at(path), path, message });
  // an embedded view's from: names a dataset of the dashboard (model.js reads the top-level views' own)
  if (dash) {
    for (const [path, view] of embeddedViews(doc)) {
      if (typeof view.from === 'string' && view.from && !dash.datasets[view.from]) out.push({ level: 'error', line: at([...path, 'from']), path: [...path, 'from'], message: `no dataset '${view.from}'${suggest(view.from, Object.keys(dash.datasets))}` });
    }
  }
  // a view on a per-pick dataset no file of which is here yet (CONTRACT §33): its columns cannot be checked, and the
  // default dataset's are not its own (dashboardProblems says so once, at the dataset)
  const unread = (path) => {
    if (!dash || !perPick || path[0] !== 'views') return false;
    const view = doc.views[path[1]];
    const name = (view && view.from) || dash.defaultName;
    return Object.prototype.hasOwnProperty.call(perPick, name) && perPick[name] === null;
  };
  const scopeOf = (path) => {
    if (!dash || !datasets || path[0] !== 'views') return null;
    const view = doc.views[path[1]];
    const name = (view && view.from) || dash.defaultName;
    return datasets[name] ? { props: withRollups(datasets[name].props, dash, name), name: datasets[name].file } : null;
  };
  if (properties || (dash && datasets)) {
    const formulas = new Set(Object.keys(doc.formulas || {}));
    // one named property against the properties of the dataset it is read from
    const checkName = (path, name, props, named) => {
      if (!props) return;
      if (typeof name !== 'string' || !name || name.startsWith('@')) return; // "@…" names a pivot column
      if (name.startsWith('file.')) return; // the host provides file.* when rows are notes
      if (name.startsWith('formula.')) {
        // a value with several sources is a formula with no text: `formula.<it>` is Bases' name for its column
        if (!formulas.has(name.slice(8)) && !props.has(`${name.slice(8)}@*`)) out.push({ level: 'error', line: at(path), path, message: `'${name}' names a formula this file does not define` });
        return;
      }
      const bare = name.startsWith('note.') ? name.slice(5) : name;
      if (!props.has(bare)) out.push({ level: 'error', line: at(path), path, message: `'${name}' is not a property of ${named}${suggest(bare, props)}` });
    };
    for (const [path, name] of referenced(doc)) {
      if (unread(path)) continue;
      const scope = scopeOf(path);
      const props = scope ? scope.props : properties && dash && datasets && datasets[dash.defaultName] ? withRollups(properties, dash, dash.defaultName) : properties;
      checkName(path, name, props, scope ? scope.name : datasetName);
    }
    // CONTRACT §35: a record section's embedded view reads its own from: dataset (default the outer view's); its
    // filters' this.<column> is the peeked row's, so the outer view's
    for (const [path, name, own] of sectionNames(doc)) {
      const outer = doc.views[path[1]];
      const dsName = own || (outer && outer.from) || (dash && dash.defaultName);
      if (dash && datasets) {
        if (!dsName || !dash.datasets[dsName] || !datasets[dsName] || (perPick && Object.prototype.hasOwnProperty.call(perPick, dsName) && perPick[dsName] === null)) continue;
        checkName(path, name, withRollups(datasets[dsName].props, dash, dsName), datasets[dsName].file);
      } else if (!dash) checkName(path, name, properties, datasetName);
    }
  }
  // the 3D cards' columns (CONTRACT §32), each against the dataset it is read from: a layer's own `data:`, else the
  // view's. A layer dataset the dashboard does not have is model.js's problem; in a plain file it is sceneProblems'.
  for (const [path, name, layer, why] of sceneNames(doc)) {
    if (unread(path)) continue;
    const view = doc.views[path[1]];
    const own = (view && view.from) || (dash && dash.defaultName);
    let props = null, named = '';
    if (layer !== undefined && layer !== own) {
      if (!dash || !datasets || !datasets[layer]) continue;
      props = withRollups(datasets[layer].props, dash, layer);
      named = datasets[layer].file;
    } else if (dash && datasets) {
      const scope = scopeOf(path);
      if (!scope) continue;
      ({ props, name: named } = scope);
    } else if (properties && !dash) {
      props = properties;
      named = datasetName;
    }
    if (props && !props.has(name)) out.push({ level: 'error', line: at(path), path, message: `'${name}' is not a property of ${named}${suggest(name, props)}${why ? ` (${why})` : ''}` });
  }
  return out;
}

/** A dataset's properties plus the columns its `rollup:` computes (a view may name them). */
function withRollups(props, dash, name) {
  // every row has an id (data.js gives one to a row without), so a link or a select may name it
  const r = dash.datasets[name] && dash.datasets[name].rollup;
  return new Set([...props, 'id', ...(r && r.values ? Object.keys(r.values) : [])]);
}

const pathOf = (text) => text.replace(/\[(\d+)\]/g, '.$1').split('.').map((k) => (/^\d+$/.test(k) ? Number(k) : k));

/** A dashboard's own problems (docs/peps/0004-dashboards.md): what model.js's reader reports (an unknown dataset,
    view or link end), and with the datasets' names, every link column, roll-up property and dataset facet. `perPick`
    (CONTRACT §33): {<per-pick dataset>: the first file its data: names, or null when none is here}. */
export function* dashboardProblems(doc, dash, datasets = null, perPick = null) {
  for (const p of dash.problems) {
    const m = /^([\w.[\]-]+): (.*)$/.exec(p);
    // a link's direction the schema refuses already, with its did you mean
    if (m && /^links\[\d+\]\.direction$/.test(m[1])) continue;
    yield ['error', m ? pathOf(m[1]) : [], m ? m[2] : p];
  }
  // CONTRACT §33: a per-pick dataset holds one pick's rows, so a link that would carry them to another dataset carries
  // nothing (model.js panelFilter); say how to write it
  const templateOf = (name) => (dash.datasets[name] && dash.datasets[name].template) || null;
  for (const [i, l] of ((doc && Array.isArray(doc.links) ? doc.links : [])).entries()) {
    if (!l || typeof l.from !== 'string' || typeof l.to !== 'string') continue;
    const a = l.from.slice(0, l.from.indexOf('.')), b = l.to.slice(0, l.to.indexOf('.'));
    const ta = templateOf(a), tb = templateOf(b);
    if (!(ta || tb) || (ta && tb && JSON.stringify(ta) === JSON.stringify(tb))) continue;
    const one = l.direction === 'one-way';
    const [t, other, ph] = tb ? [b, a, tb[0]] : [a, b, ta[0]];
    if (!one) yield ['warning', ['links', i], `${t} is read one ${ph} at a time (data: ${dash.datasets[t].data}), so its rows narrow nothing back: write this link direction: one-way, from ${other} to ${t}`];
    else if (ta) yield ['warning', ['links', i], `${a} is read one ${ta[0]} at a time (data: ${dash.datasets[a].data}), so a link from it narrows nothing: turn it round, from ${b} to ${a} (direction: one-way)`];
  }
  if (!datasets) return;
  // a per-pick dataset's file (CONTRACT §33): the first its data: names stands for all of them
  for (const d of Object.values(dash.datasets)) {
    if (!d.template || !perPick || !Object.prototype.hasOwnProperty.call(perPick, d.name)) continue;
    const at = ['datasets', d.name, 'data'];
    if (perPick[d.name] === null) { yield ['warning', at, `no file matches ${d.data} yet, so the views reading ${d.name} are not checked against its columns`]; continue; }
    for (const p of d.template) {
      if (datasets[d.name] && !datasets[d.name].props.has(p)) yield ['error', at, `'${p}' is not a property of ${datasets[d.name].file}, the first file ${d.data} names: every row of a file read per pick carries the value it is read for${suggest(p, datasets[d.name].props)}`];
    }
  }
  // a literal selected: names values the view's dataset holds (first is the view's first row, never checked here)
  for (const [i, v] of ((doc && Array.isArray(doc.views) ? doc.views : [])).entries()) {
    if (!v || typeof v.select !== 'string' || v.selected === undefined || v.selected === null || v.selected === 'first') continue;
    const ds = datasets[v.from || dash.defaultName];
    if (!ds || typeof ds.values !== 'function') continue;
    const have = ds.values(v.select);
    for (const x of Array.isArray(v.selected) ? v.selected : [v.selected]) {
      if (!have.has(String(x))) yield ['warning', ['views', i, 'selected'], `'${x}' is not a value of ${v.select} in ${ds.file}: selected: picks it when the page opens, and no row has it${suggest(String(x), have)}`];
    }
  }
  const has = (ds, col) => datasets[ds] && withRollups(datasets[ds].props, dash, ds).has(col);
  for (const [i, l] of ((doc && doc.links) || []).entries()) {
    for (const k of ['from', 'to']) {
      const end = String((l && l[k]) || '');
      const dot = end.indexOf('.');
      const ds = end.slice(0, dot), col = end.slice(dot + 1);
      if (datasets[ds] && !has(ds, col)) yield ['error', ['links', i, k], `'${col}' is not a property of ${datasets[ds].file}${suggest(col, datasets[ds].props)}`];
    }
  }
  for (const d of Object.values(dash.datasets)) {
    const at = ['datasets', d.name];
    if (d.rollup) {
      const from = d.rollup.from;
      if (!dash.datasets[from]) { yield ['error', [...at, 'rollup', 'from'], `no dataset '${from}'`]; continue; }
      const links = dash.links.filter((l) => (l.a.ds === from && l.b.ds === d.name) || (l.b.ds === from && l.a.ds === d.name));
      if (links.length !== 1) yield ['error', [...at, 'rollup', 'from'], `a roll-up needs exactly one link between ${from} and ${d.name} (found ${links.length})`];
      for (const [col, v] of Object.entries(d.rollup.values || {})) {
        for (const k of ['property', 'per']) if (v && v[k] && datasets[from] && !datasets[from].props.has(v[k])) yield ['error', [...at, 'rollup', 'values', col, k], `'${v[k]}' is not a property of ${datasets[from].file}${suggest(v[k], datasets[from].props)}`];
        if (v && v.summary === 'Ratio' && !v.per) yield ['error', [...at, 'rollup', 'values', col], "a Ratio roll-up needs 'per' (Σproperty / Σper)"];
      }
      const latest = d.rollup.latest;
      for (const n of latest ? [latest.by, ...[].concat(latest.per || [])] : []) if (n && datasets[from] && !datasets[from].props.has(n)) yield ['error', [...at, 'rollup', 'latest'], `'${n}' is not a property of ${datasets[from].file}`];
      if (d.tree && d.tree.parent && datasets[d.name] && !datasets[d.name].props.has(d.tree.parent)) yield ['error', [...at, 'tree', 'parent'], `'${d.tree.parent}' is not a property of ${datasets[d.name].file}`];
    }
    const entry = doc.datasets && doc.datasets[d.name];
    if (entry && typeof entry === 'object' && Array.isArray(entry.facets) && datasets[d.name]) {
      for (const [path, name] of facetNames(entry.facets, [...at, 'facets'])) {
        if (typeof name === 'string' && !withRollups(datasets[d.name].props, dash, d.name).has(name)) yield ['error', path, `'${name}' is not a property of ${datasets[d.name].file}${suggest(name, datasets[d.name].props)}`];
      }
      for (const [level, path, message] of facetProblems({ facets: entry.facets }, datasets[d.name].types)) yield [level, [...at, ...path], message];
    }
  }
}

/** Check files; print one line per problem and a summary. Returns the exit status (1 on any error). */
export function main(argv, { log = console.log } = {}) {
  const files = [];
  let data = null, quiet = false, json = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--data') data = argv[++i];
    else if (a === '--quiet') quiet = true;
    else if (a === '--json') json = true;
    else if (a === '-h' || a === '--help') { log('usage: data-ui check FILE.base [FILE.base ...] [--data DATA.json] [--quiet] [--json]'); return 0; }
    else files.push(a);
  }
  if (!files.length) { log('usage: data-ui check FILE.base [FILE.base ...] [--data DATA.json] [--quiet] [--json]'); return 2; }
  const given = data ? { props: datasetProperties(data), types: datasetTypes(data), link: datasetLink(data), name: basename(data) } : null;
  let errors = 0, warnings = 0;
  const report = [];
  const against = new Set();
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    let dataset = given;
    if (!dataset) {
      // the file's own `data:` key names its data, relative to the file
      const m = /^data:\s*['"]?([^'"#\n]+?)['"]?\s*(#.*)?$/m.exec(text);
      const path = m && resolve(dirname(file), m[1].trim());
      if (path && existsSync(path) && isDataFile(path)) dataset = { props: datasetProperties(path), types: datasetTypes(path), link: datasetLink(path), name: basename(path) };
    }
    if (dataset) against.add(dataset.name);
    // a dashboard's datasets, each relative to the file (docs/peps/0004-dashboards.md)
    let datasets = null, perPick = null;
    try {
      const { doc } = parseBaseWithLines(text);
      if (doc && (doc.datasets || doc.layout)) {
        datasets = {};
        for (const d of Object.values(readDashboard(doc).datasets)) {
          // CONTRACT §33: a per-pick dataset's columns are the first file its data: names (any one stands for all)
          const path = d.template ? firstMatch(dirname(file), d.data) : resolve(dirname(file), d.data);
          if (d.template) (perPick ||= {})[d.name] = path && isDataFile(path) ? path : null;
          // WHY any data file, not only .json: a CSV dataset (the Servo template's coverage) was skipped, so its views
          // were checked against the default dataset's columns
          if (path && existsSync(path) && isDataFile(path)) {
            const name = d.template ? relative(dirname(file), path) : basename(path);
            datasets[d.name] = { props: datasetProperties(path), types: datasetTypes(path), file: name, values: (col) => datasetValues(path, col) };
            against.add(name);
          }
        }
      }
    } catch { /* checkText reports the syntax error */ }
    for (const p of checkText(text, { properties: dataset && dataset.props, types: dataset && dataset.types, link: dataset ? dataset.link : undefined, datasetName: dataset && dataset.name, datasets, perPick })) {
      if (p.level === 'error') errors++; else warnings++;
      report.push({ file, ...p });
      if (!quiet && !json) log(`${file}:${p.line}: ${p.level}: ${show(p.path)}: ${p.message}`);
    }
  }
  if (json) log(JSON.stringify({ errors, warnings, problems: report }, null, 1));
  else log(`checked ${files.length} ${files.length === 1 ? 'file' : 'files'}${against.size ? ` against ${[...against].join(', ')}` : ''}: ${errors} errors, ${warnings} warnings`);
  return errors ? 1 : 0;
}
