/* The input contract (docs/SPEC.md §4, docs/CONTRACT.md §3): any data that reads as records.

   Accepted forms, all normalised to the runtime shape {id, title, titleProperty, linkProperty?, imageProperty?,
   properties: {id: {label, type, unitText?, ...}}, rows: [...]}:
     - the runtime shape itself (what robotparts' build writes);
     - a field schema in Frictionless Table Schema vocabulary plus data-ui's six keys (unit, display, facet, media,
       basis, derived), as {schema: {fields}, rows} or as a sidecar whose `path` names the rows;
     - a bare list of objects (types inferred);
     - CSV / TSV / JSONL text, with an optional schema;
     - one object (a property sheet): one record per key.
   Rules: numbers are numbers, dates are ISO 8601 text, lists are arrays, missing is null (never 0, never "").
   A cell may be rich, {value, unit?, basis?, source?, sourceUrl?, sourcePage?, asOf?, record?, low?, high?, n?, note?, text?}; views filter, sort and group
   on .value (grammar.js cellValue).

   Provenance (docs/CONTRACT.md §24): every normalised dataset carries `raw` ({url, format, bytes}: the file its rows
   were read from, as it was read) and `originOf(row)` ({kind, line?, text, header?, idAssigned}: the record as it sits
   in that file), both non-enumerable. WHY no second copy: a CSV / TSV / JSONL keeps its text once plus three numbers
   per row (start, end, line); a JSON row keeps the parsed object only where normalisation replaced it (an id added). */

import { cellValue } from './grammar.js';

const TYPES = { number: 'number', integer: 'number', array: 'list', boolean: 'boolean', date: 'date', datetime: 'date', string: 'text', object: 'text' };

/** One Table Schema field -> a runtime property. */
export function fieldToProperty(field) {
  const p = { type: TYPES[field.type] || 'text' };
  if (field.title) p.label = field.title;
  if (field.unit) p.unitText = field.unit;
  if (field.description) p.note = field.description;
  for (const k of ['display', 'facet', 'media', 'basis', 'derived', 'decimals', 'digits', 'compact', 'labels', 'better', 'hidden', 'format', 'constraints', 'width', 'values', 'colors', 'align', 'relation', 'tones']) {
    if (field[k] !== undefined) p[k] = field[k];
  }
  return p;
}

function inferType(values) {
  const filled = values.map(cellValue).filter((v) => v !== null && v !== undefined && v !== '');
  if (!filled.length) return 'text';
  if (filled.every((v) => Array.isArray(v))) return 'list';
  if (filled.every((v) => typeof v === 'number')) return 'number';
  if (filled.every((v) => typeof v === 'boolean')) return 'boolean';
  return 'text';
}

/** Properties inferred from rows (the fallback when there is no schema). */
export function inferProperties(rows) {
  const keys = new Set();
  for (const r of rows.slice(0, 500)) for (const k of Object.keys(r)) if (!k.startsWith('_')) keys.add(k);
  const out = {};
  for (const k of keys) out[k] = { type: inferType(rows.map((r) => r[k])) };
  return out;
}

// rows whose id the core made up (the record had none): the source view marks them (docs/CONTRACT.md §24)
const ASSIGNED = new WeakSet();
const withId = (r, i) => {
  const out = { id: String(i), ...r };
  if (!('id' in r) || ASSIGNED.has(r)) ASSIGNED.add(out);
  return out;
};

/** Give a normalised dataset its provenance: `raw` ({url, format, bytes}, frozen) and `originOf(row)`, the record as it
    sits in the file (`at(i)` for the i-th row). Non-enumerable, so a spread or a JSON copy of the dataset never carries
    a stale one. */
export function withOrigin(dataset, raw, at) {
  let index = null;
  const originOf = (row) => {
    if (!index) index = new Map(dataset.rows.map((r, i) => [r, i]));
    const i = index.get(row);
    if (i === undefined) return null;
    // WHY assign, not spread: `text` may be a getter, made only when read (a view asks idAssigned per drawn row)
    return Object.assign(at(i), { idAssigned: ASSIGNED.has(row) });
  };
  Object.defineProperty(dataset, 'raw', { value: Object.freeze({ url: null, format: null, bytes: null, ...raw }), configurable: true, writable: true });
  Object.defineProperty(dataset, 'originOf', { value: originOf, configurable: true, writable: true });
  return dataset;
}

const pretty = (v) => JSON.stringify(v, null, 2);

/** Any accepted form -> the runtime shape. `rows` may be given separately (a sidecar schema plus its data). */
export function normalizeDataset(input, { rows: given, id } = {}) {
  if (Array.isArray(input)) return normalizeDataset({ rows: input }, { id });
  if (!input || typeof input !== 'object') throw new Error('a dataset is a list of records or an object with rows');
  const rows = given || input.rows || input.data || null;
  const url = typeof input.url === 'string' ? input.url : null;
  // the record as parsed, before an id was added (the same object when it had one)
  const json = (i) => ({ kind: 'json', get text() { return pretty(rows[i]); } });
  if (input.properties && rows) {
    const d = { ...input, id: input.id || id || 'data', rows: rows.map((r, i) => ('id' in r ? r : withId(r, i))) };
    // a dataset loadDataset made, handed on (el.data = await loadDataset(url)): its rows keep the file they came from
    if (typeof input.originOf === 'function' && input.raw) return withOrigin(d, input.raw, (i) => input.originOf(rows[i]) || json(i));
    return withOrigin(d, { url, format: 'runtime' }, json);
  }
  if (input.schema && Array.isArray(input.schema.fields)) {
    const properties = {};
    for (const f of input.schema.fields) properties[f.name] = fieldToProperty(f);
    const key = input.primaryKey || (properties.id ? 'id' : null);
    const list = (rows || []).map((r, i) => (key && r[key] !== undefined ? { ...r, id: String(r[key]) } : withId(r, i)));
    const d = {
      id: input.name || input.id || id || 'data', title: input.title || input.name || id || 'Data',
      titleProperty: input.titleProperty || (properties.name ? 'name' : Object.keys(properties)[0]),
      linkProperty: input.linkProperty, imageProperty: input.imageProperty, origin: input.origin, attribution: input.attribution, properties, rows: list,
    };
    return withOrigin(d, { url, format: 'frictionless' }, json);
  }
  if (rows) {
    const properties = inferProperties(rows);
    const list = rows.map((r, i) => ('id' in r ? r : withId(r, i)));
    const d = { id: input.id || id || 'data', title: input.title || id || 'Data', titleProperty: input.titleProperty || Object.keys(properties)[0], origin: input.origin, attribution: input.attribution, properties, rows: list };
    return withOrigin(d, { url, format: 'list' }, json);
  }
  // one object: a property sheet, one record per key
  const entries = Object.entries(input);
  const sheet = entries.map(([k, v], i) => ({ id: k, property: k, value: v, order: i }));
  const d = { id: id || 'record', title: id || 'Record', titleProperty: 'property', properties: { property: { type: 'text', label: 'Property' }, value: { type: inferType(sheet.map((r) => r.value)), label: 'Value' } }, rows: sheet };
  return withOrigin(d, { url, format: 'object' }, (i) => ({ kind: 'json', get text() { return pretty({ [entries[i][0]]: entries[i][1] }); } }));
}

/** CSV (or TSV with sep '\t'), RFC 4180 quoting, the first line the header. Types come from the schema when there
    is one; otherwise a column whose every filled cell is a number reads as numbers. Empty cells are null. */
export function parseCSV(text, { sep = ',', schema } = {}) {
  return delimited(text, { sep, schema }).rows;
}

/** A quote at a cell's start, in strict mode: does it close before a separator, a line end or the end of the text? */
function closesCell(src, from, sep) {
  for (let i = from + 1; i < src.length; i++) {
    if (src[i] !== '"') continue;
    if (src[i + 1] === '"') { i++; continue; }
    const after = src[i + 1];
    return after === undefined || after === sep || after === '\n' || after === '\r';
  }
  return false;
}

/** The scanner under parseCSV: every line of a delimited text as {cells, start, end, line}, RFC 4180 quoting, blank lines included
    (offsets into the text; a quoted field may span lines, so a record's end is its last line's). `strict` (CONTRACT §40, a pasted
    block): a quote opens a quoted cell only when it closes the whole cell; anywhere else it is the words as written. */
export function parseRecords(text, { sep = ',', strict = false } = {}) {
  const src = String(text);
  const records = [];
  let row = [], cell = '', quoted = false, start = 0, line = 1, first = 1;
  const close = (end) => { row.push(cell); records.push({ cells: row, start, end, line: first }); row = []; cell = ''; };
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (quoted) {
      if (c === '"') { if (src[i + 1] === '"') { cell += '"'; i++; } else quoted = false; }
      // a line break inside quotes is one '\n' in the value, whichever the file uses
      else if (c === '\r') { cell += '\n'; if (src[i + 1] === '\n') i++; line++; }
      else { if (c === '\n') line++; cell += c; }
    } else if (c === '"' && cell === '' && (!strict || closesCell(src, i, sep))) quoted = true;
    else if (c === sep) { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      close(i);
      if (c === '\r' && src[i + 1] === '\n') i++;
      line++;
      start = i + 1;
      first = line;
    } else cell += c;
  }
  if (cell !== '' || row.length) close(src.length);
  return records;
}

/** parseCSV's rows plus where each record sits in the text: {rows, src, head: {start, end, line}, starts, ends, lines}
    (offsets into `src`, the text as given; a quoted field may span lines, so a record's end is its last line's). */
function delimited(text, { sep = ',', schema } = {}) {
  const src = String(text);
  const records = parseRecords(src, { sep });
  const kept = records.filter((r) => r.cells.length > 1 || r.cells[0] !== '');
  const [headRec = { cells: [], start: 0, end: 0, line: 1 }, ...bodyRecs] = kept;
  const head = headRec.cells;
  const body = bodyRecs.map((r) => r.cells);
  const fields = schema && schema.fields ? Object.fromEntries(schema.fields.map((f) => [f.name, f])) : {};
  const numeric = head.map((h, k) => (fields[h] ? ['number', 'integer'].includes(fields[h].type) : body.every((r) => r[k] === undefined || r[k] === '' || Number.isFinite(Number(r[k])))));
  const list = head.map((h) => fields[h] && fields[h].type === 'array');
  const rows = body.map((r) => Object.fromEntries(head.map((h, k) => {
    const raw = r[k];
    if (raw === undefined || raw === '') return [h, null];
    if (numeric[k]) return [h, Number(raw)];
    if (list[k]) return [h, raw.split(';').map((s) => s.trim()).filter(Boolean)];
    return [h, raw];
  })));
  return {
    rows, src, head: { start: headRec.start, end: headRec.end, line: headRec.line },
    starts: Uint32Array.from(bodyRecs, (r) => r.start), ends: Uint32Array.from(bodyRecs, (r) => r.end), lines: Uint32Array.from(bodyRecs, (r) => r.line),
  };
}

export function parseJSONL(text) {
  return jsonLines(text).rows;
}

/** parseJSONL's rows plus each one's line: {rows, src, starts, ends, lines}. A blank line is skipped. */
function jsonLines(text) {
  const src = String(text);
  const rows = [], starts = [], ends = [], lines = [];
  for (let start = 0, line = 1; start <= src.length; line++) {
    let end = src.indexOf('\n', start);
    if (end < 0) end = src.length;
    const at = src[end - 1] === '\r' ? end - 1 : end; // the line's own text ends before its CR
    const l = src.slice(start, at);
    if (l.trim()) { rows.push(JSON.parse(l)); starts.push(start); ends.push(at); lines.push(line); }
    start = end + 1;
  }
  return { rows, src, starts: Uint32Array.from(starts), ends: Uint32Array.from(ends), lines: Uint32Array.from(lines) };
}

/** The UTF-8 size of a text: the bytes of the file as it was read (no copy of it). */
function utf8Bytes(s) {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0x80) n += 1;
    else if (c < 0x800) n += 2;
    else if (c >= 0xd800 && c < 0xdc00 && i + 1 < s.length) { n += 4; i++; } else n += 3;
  }
  return n;
}

/** Where the i-th row of a parsed CSV / TSV / JSONL file sits, as originOf returns it. */
function textOrigin(kind, parsed) {
  const { src, starts, ends, lines } = parsed;
  if (kind === 'jsonl') return (i) => ({ kind, line: lines[i], get text() { return pretty(JSON.parse(src.slice(starts[i], ends[i]))); } });
  const header = { line: parsed.head.line, text: src.slice(parsed.head.start, parsed.head.end) };
  return (i) => ({ kind, line: lines[i], get text() { return src.slice(starts[i], ends[i]); }, header });
}

/** Fetch a dataset by URL: .json (any form above), .csv / .tsv / .jsonl (with `<name>.schema.json` beside it when
    present), or a schema sidecar whose `path` names the rows. Relative paths resolve against the file that names them. */
export async function loadDataset(url, { fetch: get = globalThis.fetch } = {}) {
  const href = String(url);
  const text = async (u) => { const r = await get(u); if (!r.ok) throw new Error(`cannot load ${u}: ${r.status}`); return r.text(); };
  const ext = href.split('?')[0].split('.').pop().toLowerCase();
  const schemaFor = async () => {
    try { return JSON.parse(await text(href.replace(/\.(csv|tsv|jsonl)(\?.*)?$/i, '.schema.json'))); } catch { return null; }
  };
  if (ext === 'csv' || ext === 'tsv' || ext === 'jsonl') {
    // WHY together: the schema sidecar and the rows do not depend on each other (perf review 2026-10-26, item 6)
    const [sidecar, body] = await Promise.all([schemaFor(), text(href)]);
    const parsed = ext === 'jsonl' ? jsonLines(body) : delimited(body, { sep: ext === 'tsv' ? '\t' : ',', schema: sidecar && sidecar.schema });
    const { rows } = parsed;
    const d = normalizeDataset(sidecar && sidecar.schema ? sidecar : { rows }, { rows, id: href.split('/').pop().replace(/\.\w+$/, '') });
    return withOrigin(d, { url: href, format: ext, bytes: utf8Bytes(body) }, textOrigin(ext, parsed));
  }
  const body = await text(href);
  const json = JSON.parse(body);
  if (json && json.schema && json.path && !json.rows) {
    const rowsUrl = new URL(json.path, new URL(href, globalThis.location ? globalThis.location.href : 'file:///')).href;
    const inner = await loadDataset(rowsUrl, { fetch: get });
    const d = normalizeDataset(json, { rows: inner.rows });
    // the rows came from the file `path` names: that file is their source, the sidecar only typed them
    return withOrigin(d, { ...inner.raw, schema: href }, (i) => inner.originOf(inner.rows[i]));
  }
  const d = normalizeDataset(json, { id: href.split('/').pop().replace(/\.\w+$/, '') });
  const { originOf } = d;
  return withOrigin(d, { ...d.raw, url: href, bytes: utf8Bytes(body) }, (i) => originOf(d.rows[i]));
}
