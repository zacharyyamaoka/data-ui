// PEP 0010 P3, navigation: the checkers' half (docs/CONTRACT.md §33). Both checkers accept every key P3 adds (a link's
// `direction`, a dataset whose data: names a placeholder, a view's `selected:`) and refuse what an agent gets wrong, each
// at its line:
//   - a direction that is not one-way or two-way (did you mean);
//   - selected: on a view with no select: (it presets what a click selects);
//   - a per-pick dataset (data: runs/{run}.json) whose placeholder no link reaches (nothing can pick its run), or that is
//     read on a timer (refresh:), or the file's own top-level data: written as one (it is read before anything is picked);
//   - a link into a per-pick dataset written two-way: a warning (its rows are one run's, so they narrow nothing back);
//   - with the files beside it (the Node CLI): the per-pick dataset's columns are the first file its template names (a
//     placeholder that is not one of them is an error; no file at all, a warning), and a literal selected: value that the
//     view's dataset does not hold is a warning.
// The fixture is tests/fixtures/p3/ (nav.base and its files); each variant is a copy of the folder with one line swapped.
// tools/test_check_p3.py asks the Python checker the same. Written red, before the schema and the checkers changed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'tests', 'fixtures', 'p3');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;

/** A copy of the fixture folder with nav.base's text rewritten by `edit`; the copied file's path. */
function variant(edit = (t) => t) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-p3-'));
  cpSync(FIX, dir, { recursive: true });
  const path = join(dir, 'nav.base');
  writeFileSync(path, edit(readFileSync(path, 'utf8')));
  return path;
}
const swap = (from, to) => (text) => {
  assert.equal(text.split(from).length, 2, `'${from}' is in the fixture exactly once`);
  return text.replace(from, to);
};
const lineOf = (path, needle) => readFileSync(path, 'utf8').split('\n').findIndex((l) => l.includes(needle)) + 1;

function node(path) {
  const r = spawnSync('node', [CLI, 'check', path, '--json'], { cwd: ROOT, maxBuffer: 64 << 20 });
  return JSON.parse(r.stdout.toString());
}
function python(path) {
  const r = spawnSync('python3', [join(ROOT, 'tools', 'check_views.py'), path], { cwd: ROOT });
  const out = r.stdout.toString();
  const m = /(\d+) errors, (\d+) warnings/.exec(out);
  assert.ok(m, out + r.stderr.toString());
  return { errors: Number(m[1]), warnings: Number(m[2]), out };
}
const show = (v) => v.problems.map((p) => `${p.line}: ${p.level}: ${p.path.join('.')}: ${p.message}`).join('\n');
const at = (v, level, line, re) => v.problems.some((p) => p.level === level && p.line === line && re.test(p.message));

test('nav.base, every key P3 adds: 0 errors, 0 warnings in both checkers', () => {
  const path = join(FIX, 'nav.base');
  const v = node(path);
  assert.equal(v.errors + v.warnings, 0, show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.equal(py.errors + py.warnings, 0, py.out);
  }
});

test('a link\'s direction is one-way or two-way; a misspelt one is an error at its line, with did you mean', () => {
  const path = variant(swap('{ from: runs.run, to: samples.run, direction: one-way }', '{ from: runs.run, to: samples.run, direction: oneway }'));
  const line = lineOf(path, 'direction: oneway');
  const v = node(path);
  assert.ok(at(v, 'error', line, /did you mean 'one-way'/), show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.errors >= 1 && py.out.includes(`nav.base:${line}: error:`) && py.out.includes("did you mean 'one-way'"), py.out);
  }
});

test('selected: with no select: is an error at its line (it presets what a click on the view selects)', () => {
  const path = variant(swap('    select: deployment\n    selected: first', '    selected: first'));
  const line = lineOf(path, 'selected: first');
  const v = node(path);
  assert.ok(at(v, 'error', line, /select:/), show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.out.includes(`nav.base:${line}: error: views[0].selected:`) && py.out.includes('select:'), py.out);
  }
});

test('a literal selected: value the view\'s dataset does not hold is a warning (Node, with the files)', () => {
  const path = variant(swap('    selected: first', '    selected: [nowhere]'));
  const line = lineOf(path, 'selected: [nowhere]');
  const v = node(path);
  assert.ok(at(v, 'warning', line, /'nowhere'/) && at(v, 'warning', line, /deployment/), show(v));
  assert.equal(v.errors, 0, show(v));
  if (HAS_PY) assert.equal(python(path).errors, 0);
});

test('a link into a per-pick dataset written two-way is a warning: write it one-way', () => {
  const path = variant(swap('{ from: runs.run, to: samples.run, direction: one-way }', '{ from: runs.run, to: samples.run }'));
  const line = lineOf(path, '{ from: runs.run, to: samples.run }');
  const v = node(path);
  assert.ok(at(v, 'warning', line, /one-way/), show(v));
  assert.equal(v.errors, 0, show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.errors === 0 && py.out.includes(`nav.base:${line}: warning: links[1]:`) && py.out.includes('one-way'), py.out);
  }
});

test('a placeholder no link reaches is an error at the dataset\'s data: (nothing can pick its run)', () => {
  const path = variant(swap('  - { from: runs.run, to: samples.run, direction: one-way }\n', ''));
  const line = lineOf(path, "data: 'runs/{run}.json'");
  const v = node(path);
  assert.ok(at(v, 'error', line, /link/) && at(v, 'error', line, /\brun\b/), show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.out.includes(`nav.base:${line}: error: datasets.samples.data:`) && py.out.includes('link'), py.out);
  }
});

test('a placeholder that is no column of the first file the template names is an error (Node, with the files)', () => {
  const path = variant(swap("data: 'runs/{run}.json'", "data: 'runs/{rnu}.json'"));
  const line = lineOf(path, "data: 'runs/{rnu}.json'");
  const v = node(path);
  assert.ok(at(v, 'error', line, /'rnu'/), show(v));
  if (HAS_PY) assert.ok(python(path).errors >= 1, 'no link ends at samples.rnu either');
});

test('a template no file matches yet is a warning (Node, with the files): its views are not checked against its columns', () => {
  const path = variant(swap("data: 'runs/{run}.json'", "data: 'trials/{run}.json'"));
  const line = lineOf(path, "data: 'trials/{run}.json'");
  const v = node(path);
  assert.ok(at(v, 'warning', line, /no file/), show(v));
  assert.equal(v.errors, 0, show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.equal(py.errors + py.warnings, 0, py.out);
  }
});

test('the file\'s own data: written as a template is an error (it is read before anything is picked)', () => {
  const path = variant(swap('data: runs.json\nclock:', "data: 'runs/{run}.json'\nclock:"));
  const line = lineOf(path, "data: 'runs/{run}.json'\nclock:".split('\n')[0]);
  const v = node(path);
  assert.ok(v.problems.some((p) => p.level === 'error' && p.line === line && p.path[0] === 'data'), show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.out.includes(`nav.base:${line}: error: data:`), py.out);
  }
});

test('a per-pick dataset read on a timer (refresh:) is an error at its line', () => {
  const path = variant(swap("    data: 'runs/{run}.json'\n", "    data: 'runs/{run}.json'\n    refresh: 10s\n"));
  const line = lineOf(path, 'refresh: 10s');
  const v = node(path);
  assert.ok(at(v, 'error', line, /refresh/), show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.ok(py.out.includes(`nav.base:${line}: error: datasets.samples.refresh:`), py.out);
  }
});
