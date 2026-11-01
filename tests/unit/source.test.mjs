// The raw source view (docs/CONTRACT.md §24): the core's provenance (originOf for JSON, JSONL, CSV / TSV, the bytes and
// the format), the view's literal cell text and its RFC 4180 CSV, and both checkers knowing `type: source`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeDataset, loadDataset, parseCSV, parseJSONL } from '../../packages/core/src/data.js';
import { checkText } from '../../packages/core/src/check.js';
import { literal, columnsOf, csvField, toCSV, fillTemplate } from '../../packages/views/source/src/literal.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/** A fetch over a few in-memory files (404 for the rest). */
const files = (map) => async (url) => {
  const name = url.split('/').pop();
  return name in map ? { ok: true, status: 200, text: async () => map[name] } : { ok: false, status: 404, text: async () => '' };
};

test('originOf, CSV: the header and the record verbatim, a quoted field over two lines, CRLF kept; line numbers; ids the core assigned', async () => {
  const csv = 'name,price,note\r\n"Bolt, M3",1.50,plain\r\n  padded  ,0.25,"two\r\nlines"\r\n\r\nX,2,""\r\n';
  const d = await loadDataset('http://h/x/parts.csv', { fetch: files({ 'parts.csv': csv }) });
  assert.deepEqual({ ...d.raw }, { url: 'http://h/x/parts.csv', format: 'csv', bytes: Buffer.byteLength(csv) });
  assert.deepEqual(d.rows.map((r) => r.name), ['Bolt, M3', '  padded  ', 'X'], 'the parsed values are unchanged (spaces kept)');
  assert.equal(d.rows[1].note, 'two\nlines', 'a line break inside quotes is one \\n in the value');
  const o = d.originOf(d.rows[1]);
  assert.equal(o.kind, 'csv');
  assert.equal(o.line, 3);
  assert.equal(o.text, '  padded  ,0.25,"two\r\nlines"', 'the record, byte for byte, both its lines');
  assert.deepEqual(o.header, { line: 1, text: 'name,price,note' });
  assert.equal(o.idAssigned, true, 'a CSV with no id column: the core assigned it');
  assert.equal(d.originOf(d.rows[2]).line, 6, 'a blank line is skipped, and still counted');
  assert.equal(d.originOf(d.rows[2]).text, 'X,2,""');
  assert.equal(d.originOf({ id: 'stranger' }), null, 'a row that is not the dataset\'s has no origin');
});

test('originOf, TSV and a schema sidecar: a column typed string keeps "1.50"; the sidecar names the dataset', async () => {
  const tsv = 'sku\tprice\nA-1\t1.50\nA-2\t0.80\n';
  const schema = JSON.stringify({ name: 'parts', schema: { fields: [{ name: 'sku', type: 'string' }, { name: 'price', type: 'string' }] }, origin: { url: 'notes/{sku}.md' } });
  const d = await loadDataset('http://h/parts.tsv', { fetch: files({ 'parts.tsv': tsv, 'parts.schema.json': schema }) });
  assert.equal(d.id, 'parts');
  assert.equal(d.raw.format, 'tsv');
  assert.deepEqual(d.rows.map((r) => r.price), ['1.50', '0.80']);
  assert.deepEqual(d.origin, { url: 'notes/{sku}.md' }, 'the dataset\'s origin key passes through normalisation');
  assert.deepEqual(d.originOf(d.rows[1]), { kind: 'tsv', line: 3, text: 'A-2\t0.80', header: { line: 1, text: 'sku\tprice' }, idAssigned: true });
});

test('originOf, JSONL: the line number and the object as parsed (pretty JSON); a blank line counts', async () => {
  const jsonl = '{"id":"a","v":1.5}\n\n{"v":"  x  "}\r\n';
  const d = await loadDataset('http://h/runs.jsonl', { fetch: files({ 'runs.jsonl': jsonl }) });
  assert.equal(d.raw.format, 'jsonl');
  const a = d.originOf(d.rows[0]);
  assert.equal(a.line, 1);
  assert.equal(a.idAssigned, false);
  assert.equal(a.text, '{\n  "id": "a",\n  "v": 1.5\n}');
  const b = d.originOf(d.rows[1]);
  assert.equal(b.line, 3);
  assert.equal(b.text, '{\n  "v": "  x  "\n}', 'the object before the core added its id');
  assert.equal(b.idAssigned, true);
  assert.deepEqual(parseJSONL(jsonl), [{ id: 'a', v: 1.5 }, { v: '  x  ' }], 'parseJSONL is unchanged');
});

test('originOf, JSON: the runtime shape, a bare list, a Frictionless file, one object; bytes and url from the file', async () => {
  const text = JSON.stringify({ id: 'objs', properties: { name: { type: 'text' } }, origin: { url: 'sources/{id}.md' }, rows: [{ id: 'k', name: 'é', _x: '' }, { name: 'no id' }] });
  const d = await loadDataset('http://h/objs.json', { fetch: files({ 'objs.json': text }) });
  assert.deepEqual({ ...d.raw }, { url: 'http://h/objs.json', format: 'runtime', bytes: Buffer.byteLength(text) }, 'bytes are UTF-8 bytes (é is two)');
  assert.deepEqual(d.origin, { url: 'sources/{id}.md' });
  assert.equal(d.originOf(d.rows[0]).text, '{\n  "id": "k",\n  "name": "é",\n  "_x": ""\n}');
  assert.equal(d.originOf(d.rows[1]).text, '{\n  "name": "no id"\n}', 'the record as parsed, before the core added an id');
  assert.equal(d.originOf(d.rows[1]).idAssigned, true);
  assert.equal(d.originOf(d.rows[0]).idAssigned, false);
  assert.equal(normalizeDataset([{ a: 1 }]).raw.format, 'list');
  assert.equal(normalizeDataset({ schema: { fields: [{ name: 'a', type: 'number' }] }, rows: [{ a: 1 }] }).raw.format, 'frictionless');
  const sheet = normalizeDataset({ kt: 0.05 });
  assert.equal(sheet.raw.format, 'object');
  assert.equal(sheet.originOf(sheet.rows[0]).text, '{\n  "kt": 0.05\n}');
  // a sidecar whose path names the rows: the rows' file is the source, the sidecar its schema
  const side = JSON.stringify({ path: 'rows.csv', schema: { fields: [{ name: 'a', type: 'string' }] } });
  const s = await loadDataset('http://h/d/side.json', { fetch: files({ 'side.json': side, 'rows.csv': 'a\n01\n' }) });
  assert.deepEqual({ ...s.raw }, { url: 'http://h/d/rows.csv', format: 'csv', bytes: 5, schema: 'http://h/d/side.json' });
  assert.equal(s.originOf(s.rows[0]).text, '01');
  // handed on: el.data = await loadDataset(url) keeps the file the rows came from
  const again = normalizeDataset(d);
  assert.equal(again.raw.url, 'http://h/objs.json');
  assert.equal(again.originOf(again.rows[1]).text, '{\n  "name": "no id"\n}');
  // provenance never rides along in a copy of the dataset
  assert.equal('raw' in JSON.parse(JSON.stringify(d)), false);
  assert.equal(Object.keys(d).includes('originOf'), false);
});

test('parseCSV is unchanged: quotes, CR LF, a lone CR, empty cells null', () => {
  assert.deepEqual(parseCSV('a,b\r\n"x\r\ny",1\rz,\n'), [{ a: 'x\ny', b: 1 }, { a: 'z', b: null }]);
});

test('literal: each stored value as the grid writes it', () => {
  const row = { s: '  padded  ', e: '', n: null, u: undefined, num: 1.5, int: 1, neg: -0, big: 1e21, t: true, f: false, list: ['a', 'b'], rich: { value: 3, unit: 'g', basis: 'measured' }, line: 'two\nlines' };
  const got = Object.fromEntries(Object.keys(row).map((k) => [k, literal(row, k)]));
  assert.deepEqual(got.s, { text: '  padded  ', kind: 'string' }, 'spaces kept');
  assert.deepEqual(got.e, { text: '""', kind: 'empty' });
  assert.deepEqual(got.n, { text: 'null', kind: 'null' });
  assert.deepEqual(got.u, { text: 'undefined', kind: 'null' });
  assert.deepEqual(got.num, { text: '1.5', kind: 'number' });
  assert.equal(got.int.text, '1');
  assert.equal(got.neg.text, '-0', 'the sign of -0 is stored, so it shows');
  assert.equal(got.big.text, '1e+21', 'String(v): no locale, no rounding');
  assert.deepEqual([got.t.text, got.f.text], ['true', 'false']);
  assert.deepEqual(got.list, { text: '["a","b"]', kind: 'json' });
  assert.equal(got.rich.text, '{"value":3,"unit":"g","basis":"measured"}', 'a rich cell is its JSON, no unit or basis mark');
  assert.equal(got.line.text, 'two\nlines');
  assert.deepEqual(literal(row, 'missing'), { text: '', kind: 'absent' });
  assert.deepEqual(literal(Object.create({ inherited: 1 }), 'inherited'), { text: '', kind: 'absent' }, 'only own keys');
});

test('columnsOf: the union of keys in first-seen order (hidden, _ and undeclared keys included)', () => {
  assert.deepEqual(columnsOf([{ id: '0', b: 1 }, { id: '1', _x: 2, b: 3 }, { c: null }]), ['id', 'b', '_x', 'c']);
});

test('CSV out: RFC 4180 quoting, values as the grid shows them, CRLF between lines', () => {
  assert.equal(csvField('plain'), 'plain');
  assert.equal(csvField('a, b'), '"a, b"');
  assert.equal(csvField('say "hi"'), '"say ""hi"""');
  assert.equal(csvField('two\nlines'), '"two\nlines"');
  assert.equal(csvField('  padded  '), '"  padded  "', 'edge spaces are quoted, so a reader that trims keeps them');
  assert.equal(csvField('""'), '""""""', 'the grid writes an empty string as "", and so does its CSV');
  const rows = [{ id: '0', a: 'x, y', b: null }, { id: '1', a: '', c: [1, 2] }];
  const out = toCSV(columnsOf(rows), rows);
  assert.equal(out, 'id,a,b,c\r\n0,"x, y",null,\r\n1,"""""",,"[1,2]"');
  // the oracle: the core's own RFC 4180 reader gets back the header and the grid's text, row for row
  assert.deepEqual(parseCSV(out, { schema: { fields: ['id', 'a', 'b', 'c'].map((name) => ({ name, type: 'string' })) } }), [
    { id: '0', a: 'x, y', b: 'null', c: null }, { id: '1', a: '""', b: null, c: '[1,2]' }]);
});

test('fillTemplate: {property} from the row, one path segment each; null when a placeholder has no value', () => {
  assert.equal(fillTemplate('sources/{id}.md', { id: 'can_liner' }), 'sources/can_liner.md');
  assert.equal(fillTemplate('notes/{id}.md', { id: 'a/b c' }), 'notes/a%2Fb%20c.md');
  assert.equal(fillTemplate('{kind}/{id}.md', { kind: { value: 'x', basis: 'measured' }, id: 7 }), 'x/7.md');
  assert.equal(fillTemplate('sources/{id}.md', { name: 'x' }), null);
});

test('both checkers know type: source and its rows key (read from the schema)', () => {
  const ok = checkText('views:\n  - { type: source, name: Raw }\n  - { type: source, name: Shown, rows: filtered }\n', { properties: new Set(['a']), datasetName: 'd' });
  assert.deepEqual(ok, []);
  const bad = checkText('views:\n  - { type: source, name: Raw, rows: some }\n', { properties: new Set(['a']), datasetName: 'd' });
  assert.equal(bad.filter((p) => p.level === 'error').length, 1, JSON.stringify(bad));
  const py = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), join(ROOT, 'gallery', 'examples', 'raw-source', 'views.base')], { encoding: 'utf8' });
  assert.equal(py.status, 0, py.stdout + py.stderr);
  assert.match(py.stdout, /0 errors, 0 warnings/);
});
