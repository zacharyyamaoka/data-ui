// PEP 0010 P1a (docs/CONTRACT.md §32): both checkers accept every key the robotics amendment adds (scene3d's layers and
// stage, trajectory3d, voxels, style.families) and refuse the three typos the PEP names, `projection: diagonal`,
// `decay: -1` and `primitive: arow`, each once, at its line, with "did you mean". Written red, before the schema and the
// checkers changed; tools/test_check_robotics.py asks the Python checker the same questions on the same files.
//
// The fixtures are tests/fixtures/robotics/: dashboard.base (every key, with the datasets' field lists beside it, so
// the Node CLI also checks each column against the dataset that holds it) and plain.base (no datasets:, checked against
// --data poses.json). Each refused variant is a copy of the folder with one line swapped.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FIX = join(ROOT, 'tests', 'fixtures', 'robotics');
const CLI = join(ROOT, 'bin', 'data-ui.mjs');
const HAS_PY = spawnSync('python3', ['-c', 'import yaml, jsonschema'], { stdio: 'ignore' }).status === 0;

/** A copy of the fixture folder with one file's text rewritten by `edit`; the copied file's path. */
function variant(file, edit = (t) => t) {
  const dir = mkdtempSync(join(tmpdir(), 'dui-robotics-'));
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
const show = (v) => v.problems.map((p) => `${p.line}: ${p.level}: ${p.path.join('.')}: ${p.message}`).join('\n');

test('the dashboard with every new key passes the Node checker: no error, no warning, columns checked per dataset', () => {
  const v = node(join(FIX, 'dashboard.base'));
  assert.equal(v.errors, 0, show(v));
  assert.equal(v.warnings, 0, show(v));
});

test('the plain .base passes against --data poses.json: no error, no warning', () => {
  const v = node(join(FIX, 'plain.base'), '--data', join(FIX, 'poses.json'));
  assert.equal(v.errors, 0, show(v));
  assert.equal(v.warnings, 0, show(v));
});

// the three refusals PEP 0010 §11 P1a names: one error each, at the swapped line, with "did you mean"
const REFUSED = [
  { name: 'projection: diagonal', from: 'projection: perspective', to: 'projection: diagonal', path: 'trajectory3d.projection', hint: /did you mean .*dir/ },
  { name: 'decay: -1', from: 'decay: 0.5', to: 'decay: -1', path: 'trajectory3d.decay', hint: /did you mean inf\b/ },
  { name: 'primitive: arow', from: 'primitive: arrows', to: 'primitive: arow', path: 'scene3d.layers.3.primitive', hint: /did you mean 'arrows'\?/ },
];

for (const r of REFUSED) {
  test(`Node refuses ${r.name}: one error, at its line, with did you mean`, () => {
    const file = variant('dashboard.base', swap(r.from, r.to));
    const v = node(file);
    const errors = errorsOf(v);
    assert.equal(errors.length, 1, show(v));
    assert.equal(v.warnings, 0, show(v));
    assert.equal(errors[0].line, lineOf(file, r.to), show(v));
    assert.ok(errors[0].path.join('.').endsWith(r.path), show(v));
    assert.match(errors[0].message, r.hint);
  });
}

// past the PEP's three: the YAML 1.1 traps, a layer's dataset, the projection's vectors, a column per dataset
const MORE = [
  { name: 'axes: off (YAML 1.1 reads it as false)', from: 'axes: none', to: 'axes: off', hint: /did you mean 'none'/ },
  { name: 'decay: .inf (a float to YAML 1.1, a word to the page)', from: 'decay: inf', to: 'decay: .inf', hint: /did you mean inf\b/ },
  { name: "a layer's data: naming no dataset", from: 'data: diff, from:', to: 'data: dif, from:', hint: /no dataset 'dif'/ },
  { name: 'projection.dir all zero', from: 'projection: { dir: [-1, -1, -1], up: [0, 0, 1] }', to: 'projection: { dir: [0, 0, 0] }', hint: /dir/ },
  { name: 'projection.up parallel to dir', from: 'projection: { dir: [-1, -1, -1], up: [0, 0, 1] }', to: 'projection: { dir: [0, 0, -1], up: [0, 0, 1] }', hint: /parallel/ },
];

for (const r of MORE) {
  test(`Node refuses ${r.name}: one error at its line`, () => {
    const file = variant('dashboard.base', swap(r.from, r.to));
    const v = node(file);
    const errors = errorsOf(v);
    assert.equal(errors.length, 1, show(v));
    assert.equal(errors[0].line, lineOf(file, r.to), show(v));
    assert.match(errors[0].message, r.hint);
  });
}

test("Node checks a layer's columns against the layer's own dataset (poses.json for the view's, diff_poses.json for data: diff)", () => {
  const own = variant('dashboard.base', swap('x: x_mm, y: y_mm, z: z_mm, density: 20', 'x: x_m, y: y_mm, z: z_mm, density: 20'));
  let v = node(own);
  assert.equal(errorsOf(v).length, 1, show(v));
  assert.equal(errorsOf(v)[0].message, "'x_m' is not a property of poses.json (did you mean 'x_mm'?)");
  assert.equal(errorsOf(v)[0].line, lineOf(own, 'x: x_m, y:'));
  const other = variant('dashboard.base', swap('to: [ref_x_mm', 'to: [ref_x_m'));
  v = node(other);
  assert.equal(errorsOf(v).length, 1, show(v));
  assert.equal(errorsOf(v)[0].message, "'ref_x_m' is not a property of diff_poses.json (did you mean 'ref_x_mm'?)");
});

test('plain .base: a misspelt column and a voxels property are errors; a layer naming a dataset is a warning', () => {
  const data = ['--data', join(FIX, 'poses.json')];
  let file = variant('plain.base', swap('{ primitive: lines, x: x_mm,', '{ primitive: lines, x: x_m,'));
  let v = node(file, ...data);
  assert.equal(v.errors, 1, show(v));
  assert.equal(errorsOf(v)[0].message, "'x_m' is not a property of poses.json (did you mean 'x_mm'?)");
  file = variant('plain.base', swap('value: count', 'value: reach'));
  v = node(file, ...data);
  assert.equal(v.errors, 1, show(v));
  assert.match(errorsOf(v)[0].message, /^'reach' is not a property of poses\.json/);
  file = variant('plain.base', swap('{ primitive: frames, x:', '{ primitive: frames, data: diff, x:'));
  v = node(file, ...data);
  assert.equal(v.errors, 0, show(v));
  assert.equal(v.warnings, 1, show(v));
  assert.match(v.problems[0].message, /diff/);
});

test('the Python checker gives the same counts on every file and variant', { skip: !HAS_PY && 'PyYAML / jsonschema absent' }, () => {
  const cases = [
    [join(FIX, 'dashboard.base')],
    [join(FIX, 'plain.base'), '--data', join(FIX, 'poses.json')],
    ...[...REFUSED, ...MORE].map((r) => [variant('dashboard.base', swap(r.from, r.to))]),
    [variant('plain.base', swap('{ primitive: lines, x: x_mm,', '{ primitive: lines, x: x_m,')), '--data', join(FIX, 'poses.json')],
    [variant('plain.base', swap('value: count', 'value: reach')), '--data', join(FIX, 'poses.json')],
    [variant('plain.base', swap('{ primitive: frames, x:', '{ primitive: frames, data: diff, x:')), '--data', join(FIX, 'poses.json')],
  ];
  for (const args of cases) {
    const n = node(...args), p = python(...args);
    // WHY not on the dashboard's column checks: the Python proof checks names only against --data (it has no
    // dashboard model), and every dashboard variant here keeps its columns right
    assert.deepEqual([p.errors, p.warnings], [n.errors, n.warnings], `${args[0]}\nnode:\n${show(n)}\npython:\n${p.out}`);
  }
});
