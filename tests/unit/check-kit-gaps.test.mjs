// The kit gaps the PEP 0010 template lanes found, the checkers' half (docs/CONTRACT.md §7, §25, §26, §32): both
// checkers accept every key the fixes add and refuse what an agent gets wrong, each at its line.
//   gap 2   timeseries annotations from a dataset (`data:`, read as a layer: §32) or from the view's own rows (`x:` names
//           a column, `label:` too); the columns are checked against the dataset that holds them
//   gap 5   a chart field that a transform creates (calculate, window, joinaggregate, bin, fold, timeUnit, aggregate,
//           stack, density, quantile, and every name after a pivot) is no missing column, in the scope the transform
//           runs in: the chart's own transform reaches every layer, a layer's only that layer
//   gap 8   a facet nested under another facet of its rail (`parent:`)
//   gap 9   a view's text for when it has no rows (`empty:`)
// The fixtures are tests/fixtures/kit_gaps/: dashboard.base (every key, its datasets beside it, so the Node CLI checks each
// column against the dataset that holds it) and plain.base (no datasets:, against --data samples.json). Each refused
// variant is a copy of the folder with one line swapped. tools/test_check_kit_gaps.py asks the Python checker the same.
// Written red, before the schema and the checkers changed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'tests', 'fixtures', 'kit_gaps');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;

/** A copy of the fixture folder with one file's text rewritten by `edit`; the copied file's path. */
function variant(file, edit = (t) => t) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-kit-gaps-'));
  cpSync(FIX, dir, { recursive: true });
  const path = join(dir, file);
  writeFileSync(path, edit(readFileSync(path, 'utf8')));
  return path;
}
const swap = (from, to) => (text) => {
  assert.equal(text.split(from).length, 2, `'${from}' is in the fixture exactly once`);
  return text.replace(from, to);
};
const lineOf = (path, needle) => readFileSync(path, 'utf8').split('\n').findIndex((l) => l.includes(needle)) + 1;
// The swapped line, when the same text is also written legitimately above it (orchestrator fix: gap 5's fixture has
// `x2: { field: t_end }` in the first layer, where t_end is made, and the swap puts it in the second).
const lastLineOf = (path, needle) => readFileSync(path, 'utf8').split('\n').findLastIndex((l) => l.includes(needle)) + 1;

/** The Node CLI's verdict: {errors, warnings, problems: [{level, line, path, message}]}. */
function node(path, ...args) {
  const r = spawnSync('node', [CLI, 'check', path, ...args, '--json'], { cwd: ROOT, maxBuffer: 64 << 20 });
  return JSON.parse(r.stdout.toString());
}
/** The Python checker's counts and its printed lines. */
function python(path, ...args) {
  const r = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), path, ...args], { cwd: ROOT });
  const out = r.stdout.toString();
  const m = /(\d+) errors, (\d+) warnings/.exec(out);
  assert.ok(m, out + r.stderr.toString());
  return { errors: Number(m[1]), warnings: Number(m[2]), out };
}
const errorsOf = (v) => v.problems.filter((p) => p.level === 'error');
const warningsOf = (v) => v.problems.filter((p) => p.level === 'warning');
const show = (v) => v.problems.map((p) => `${p.line}: ${p.level}: ${p.path.join('.')}: ${p.message}`).join('\n');
const SAMPLES = join(FIX, 'samples.json');

test('the dashboard with every new key passes the Node checker: no error, no warning, each column checked in its own dataset', () => {
  const v = node(join(FIX, 'dashboard.base'));
  assert.equal(v.errors, 0, show(v));
  assert.equal(v.warnings, 0, show(v));
});

test('the plain file passes the Node checker against --data samples.json: no error, no warning', () => {
  const v = node(join(FIX, 'plain.base'), '--data', SAMPLES);
  assert.equal(v.errors, 0, show(v));
  assert.equal(v.warnings, 0, show(v));
});

test('the Python checker passes both files: no error, no warning', { skip: !HAS_PY && 'no PyYAML / jsonschema' }, () => {
  const a = python(join(FIX, 'plain.base'), '--data', SAMPLES);
  assert.deepEqual([a.errors, a.warnings], [0, 0], a.out);
  const b = python(join(FIX, 'dashboard.base'));
  assert.deepEqual([b.errors, b.warnings], [0, 0], b.out);
});

// ---- gap 5: a field a transform makes is known in the scope it runs in, and only there
test('gap 5: a field one layer\'s transform makes, read by another layer, is a missing column there (one error, at its line)', () => {
  const path = variant('dashboard.base', swap('x2: { field: iq_bin_end }', 'x2: { field: t_end }'));
  const v = node(path);
  const errs = errorsOf(v);
  assert.equal(errs.length, 1, show(v));
  assert.equal(errs[0].line, lastLineOf(path, 'x2: { field: t_end }'), show(v));
  assert.match(errs[0].message, /'t_end' is not a property of samples\.json/, show(v));
});

test('gap 5: a misspelt column beside created fields is still an error, with "did you mean"', () => {
  const path = variant('dashboard.base', swap('color: { field: mode, type: nominal }', 'color: { field: mod, type: nominal }'));
  const v = node(path);
  const errs = errorsOf(v);
  assert.equal(errs.length, 1, show(v));
  assert.match(errs[0].message, /'mod' is not a property of samples\.json \(did you mean 'mode'\?\)/, show(v));
});

test('gap 5: a field nothing makes is an error in both checkers (the plain file, one transform chain)', () => {
  const path = variant('plain.base', swap('size: { field: q, type: quantitative }', 'size: { field: qq, type: quantitative }'));
  const v = node(path, '--data', SAMPLES);
  assert.equal(errorsOf(v).length, 1, show(v));
  assert.equal(errorsOf(v)[0].line, lineOf(path, "field: qq"), show(v));
  if (HAS_PY) {
    const p = python(path, '--data', SAMPLES);
    assert.equal(p.errors, 1, p.out);
    assert.match(p.out, new RegExp(`:${lineOf(path, 'field: qq')}: error: .*'qq' is not a property of samples\\.json`), p.out);
  }
});

// ---- gap 2: annotations from data
test('gap 2: an annotation naming a dataset the dashboard does not have is an error at its line', () => {
  const path = variant('dashboard.base', swap('{ data: events, x: t, label: label, tone: warn }', '{ data: evnts, x: t, label: label, tone: warn }'));
  const v = node(path);
  const errs = errorsOf(v);
  assert.ok(errs.some((e) => e.line === lineOf(path, 'data: evnts') && /no dataset 'evnts'/.test(e.message)), show(v));
});

test('gap 2: an annotation\'s label column is checked against its own dataset (events.json), with "did you mean"', () => {
  const path = variant('dashboard.base', swap('{ data: events, x: t, label: label, tone: warn }', '{ data: events, x: t, label: lable, tone: warn }'));
  const v = node(path);
  const errs = errorsOf(v);
  assert.equal(errs.length, 1, show(v));
  assert.equal(errs[0].line, lineOf(path, 'label: lable'), show(v));
  assert.match(errs[0].message, /'lable' is not a property of events\.json \(did you mean 'label'\?\)/, show(v));
});

test('gap 2: an annotation from the view\'s own rows names its columns in the view\'s dataset (both checkers)', () => {
  const path = variant('plain.base', swap('- { x: t, label: event }', '- { x: t, label: evnt }'));
  const v = node(path, '--data', SAMPLES);
  assert.equal(errorsOf(v).length, 1, show(v));
  assert.match(errorsOf(v)[0].message, /'evnt' is not a property of samples\.json \(did you mean 'event'\?\)/, show(v));
  if (HAS_PY) {
    const p = python(path, '--data', SAMPLES);
    assert.equal(p.errors, 1, p.out);
    assert.match(p.out, /'evnt' is not a property of samples\.json \(did you mean 'event'\?\)/, p.out);
  }
});

test('gap 2: in a file with no datasets an annotation naming a dataset draws nothing, and both checkers warn', () => {
  const path = variant('plain.base', swap('- { x: 0.25, label: fixed }', '- { x: 0.25, label: fixed }\n        - { data: events, x: t, label: label }'));
  const v = node(path, '--data', SAMPLES);
  assert.equal(v.errors, 0, show(v));
  const w = warningsOf(v);
  assert.equal(w.length, 1, show(v));
  assert.match(w[0].message, /names a dashboard dataset/, show(v));
  if (HAS_PY) {
    const p = python(path, '--data', SAMPLES);
    assert.deepEqual([p.errors, p.warnings], [0, 1], p.out);
    assert.match(p.out, /names a dashboard dataset/, p.out);
  }
});

// ---- gap 8: a facet nested under another facet of its rail
test('gap 8: parent naming no facet of the rail is an error at its line, with "did you mean" (both checkers)', () => {
  const path = variant('dashboard.base', swap('parent: device }', 'parent: devise }'));
  const v = node(path);
  const errs = errorsOf(v);
  assert.equal(errs.length, 1, show(v));
  assert.equal(errs[0].line, lineOf(path, 'parent: devise'), show(v));
  assert.match(errs[0].message, /did you mean 'device'\?/, show(v));
  if (HAS_PY) {
    const p = python(path);
    assert.equal(p.errors, 1, p.out);
    assert.match(p.out, new RegExp(`:${lineOf(path, 'parent: devise')}: error: .*did you mean 'device'\\?`), p.out);
  }
});

test('gap 8: a facet cannot be its own parent (both checkers)', () => {
  const path = variant('dashboard.base', swap('parent: device }', 'parent: run }'));
  const v = node(path);
  assert.equal(errorsOf(v).length, 1, show(v));
  assert.match(errorsOf(v)[0].message, /own parent/, show(v));
  if (HAS_PY) {
    const p = python(path);
    assert.equal(p.errors, 1, p.out);
    assert.match(p.out, /own parent/, p.out);
  }
});
