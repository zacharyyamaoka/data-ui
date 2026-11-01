// PEP 0010 P5, the diagnostics and gates overlay: the checkers' half (docs/CONTRACT.md §35). Both checkers accept every
// key P5 adds (`display: status`, the tracker's matrix keys `column`, `columns` and `order`, `limits` on a time series
// and a plot, a property `kpi.target`, `trajectory3d.color` and `tolerance`, `voxels.better` beside `scale: verdict`, a
// record section's embedded `view`) and refuse what an agent gets wrong, each at its line:
//   - a display that is no display (`statuss`: did you mean 'status');
//   - a `limits` side that is neither warn nor error (`warning`), or not a pair;
//   - `better` outside higher | lower;
//   - a record section with neither properties nor a view.
// With the files beside it (the Node CLI), the columns each new key reads: a tracker's column, a limits end, a property
// target, the path's colour, an embedded view's own columns (in its from: dataset) and a `this.<column>` the outer
// view's dataset lacks.
// The fixture is tests/fixtures/p5/ (gates.base and its files); each variant is a copy of the folder with one line
// swapped. tools/test_check_p5.py asks the Python checker the same. Written red, before the schema and the checkers.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'tests', 'fixtures', 'p5');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;

/** A copy of the fixture folder with gates.base's text rewritten by `edit`; the copied file's path. */
function variant(edit = (t) => t) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-p5-'));
  cpSync(FIX, dir, { recursive: true });
  const path = join(dir, 'gates.base');
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
/** The Python checker's output has an error at `line` whose text matches `re`. */
const pyAt = (py, line, re) => py.out.split('\n').some((l) => l.includes(`:${line}: error:`) && re.test(l));

test('gates.base, every key P5 adds: 0 errors, 0 warnings in both checkers', () => {
  const path = join(FIX, 'gates.base');
  const v = node(path);
  assert.equal(v.errors + v.warnings, 0, show(v));
  if (HAS_PY) {
    const py = python(path);
    assert.equal(py.errors + py.warnings, 0, py.out);
  }
});

test('display: a misspelt status is refused at its line, with did you mean status (both checkers)', () => {
  const path = variant(swap('display: { verdict: status }', 'display: { verdict: statuss }'));
  const line = lineOf(path, 'statuss');
  const v = node(path);
  assert.ok(at(v, 'error', line, /did you mean 'status'/), show(v));
  if (HAS_PY) assert.ok(pyAt(python(path), line, /did you mean 'status'/), python(path).out);
});

test('limits: a side that is neither warn nor error is refused at its line (both checkers)', () => {
  const path = variant(swap('limits: { warn: [warn_lo, warn_hi]', 'limits: { warning: [warn_lo, warn_hi]'));
  const line = lineOf(path, 'warning:');
  const v = node(path);
  assert.ok(at(v, 'error', line, /warning/), show(v));
  if (HAS_PY) assert.ok(pyAt(python(path), line, /warning/), python(path).out);
});

test('limits: a side that is not a pair is refused at its line (both checkers)', () => {
  const path = variant(swap('limits: { error: [error_lo, error_hi] }', 'limits: { error: [error_hi] }'));
  const line = lineOf(path, 'limits: { error: [error_hi] }');
  const v = node(path);
  assert.ok(v.problems.some((p) => p.level === 'error' && p.line === line), show(v));
  if (HAS_PY) assert.ok(pyAt(python(path), line, /./), python(path).out);
});

test('voxels: better outside higher | lower is refused at its line (both checkers)', () => {
  const path = variant(swap('scale: verdict, better: higher', 'scale: verdict, better: up'));
  const line = lineOf(path, 'better: up');
  const v = node(path);
  assert.ok(at(v, 'error', line, /higher|lower/), show(v));
  if (HAS_PY) assert.ok(pyAt(python(path), line, /higher|lower/), python(path).out);
});

test('record: a section with neither properties nor a view is refused at its line (both checkers)', () => {
  const path = variant(swap('- { name: Verdict, properties: [verdict, value, warn_hi, error_hi, message] }', '- { name: Verdict }'));
  const line = lineOf(path, '- { name: Verdict }');
  const v = node(path);
  assert.ok(v.problems.some((p) => p.level === 'error' && p.line === line), show(v));
  if (HAS_PY) assert.ok(pyAt(python(path), line, /./), python(path).out);
});

test('files: a tracker column the dataset lacks is an error at its line (Node, with the files)', () => {
  const path = variant(swap('column: title, columns:', 'column: titel, columns:'));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'column: titel'), /titel/), show(v));
});

test('files: a limits end the dataset lacks is an error at its line (Node, with the files)', () => {
  const path = variant(swap('error: [null, error_hi] }', 'error: [null, error_hie] }'));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'error_hie'), /error_hie/), show(v));
});

test('files: a property kpi.target the dataset lacks is an error at its line (Node, with the files)', () => {
  const path = variant(swap('target: target,', 'target: targett,'));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'targett'), /targett/), show(v));
});

test('files: a trajectory3d colour column the poses lack is an error at its line (Node, with the files)', () => {
  const path = variant(swap('color: err_mm', 'color: err_mmm'));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'err_mmm'), /err_mmm/), show(v));
});

test('files: an embedded section view is checked against its own from: dataset (Node, with the files)', () => {
  const path = variant(swap("timeseries: { x: t, 'y': q_deg, series: situation }", "timeseries: { x: t, 'y': q_degg, series: situation }"));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'q_degg'), /q_degg/), show(v));
});

test('files: a this.<column> the outer view\'s dataset lacks is an error at its line (Node, with the files)', () => {
  const path = variant(swap('run == this.run && title == this.title', 'run == this.runn && title == this.title'));
  const v = node(path);
  assert.ok(at(v, 'error', lineOf(path, 'this.runn'), /runn/), show(v));
});
