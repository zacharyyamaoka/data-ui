// PEP 0010 P2 (coverage), the pure half: trajectory3d's opacity: auto is exactly 1/n over a family's n paths with no
// floor (Zach's brief: dense regions read darker; the 0.04 floor is gone), and the coverage files each template writes
// are the trajectory contract's (gallery/robotics/CONTRACT.md; schemas/coverage_samples.schema.json and grid.schema.json):
// columns, types, units, required columns, weights, the 150,000-row budget, and the views that read them. The browser
// half is tests/browser/p2_checks.py. Written red, before the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { parseCSV } from '../../packages/core/src/data.js';
import { parseBase } from '../../packages/core/src/base.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
// bind.js imports '@data-ui/core': bundled here against the core's own modules (as scene3d-bind.test.mjs does)
const shim = `export { cellValue } from ${JSON.stringify(join(ROOT, 'packages/core/src/grammar.js'))};
export { mediaUrl } from ${JSON.stringify(join(ROOT, 'packages/core/src/format.js'))};
export { seriesColor } from ${JSON.stringify(join(ROOT, 'packages/core/src/clock.js'))};`;
const bundled = await build({
  stdin: { contents: `export * from './bind.js';`, resolveDir: join(ROOT, 'packages/views/scene3d/src') },
  bundle: true, write: false, format: 'esm', platform: 'node', logLevel: 'silent',
  plugins: [{ name: 'shim', setup(b) {
    b.onResolve({ filter: /^@data-ui\/core$/ }, () => ({ path: 'core', namespace: 'shim' }));
    b.onLoad({ filter: /^core$/, namespace: 'shim' }, () => ({ contents: shim, loader: 'js', resolveDir: ROOT }));
  } }],
});
const B = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const EX = join(ROOT, 'gallery', 'examples');
const SCHEMAS = join(ROOT, 'gallery', 'robotics', 'schemas');
const json = (path) => JSON.parse(readFileSync(path, 'utf8'));
const { suffixes, exceptions } = json(join(SCHEMAS, 'channels.json'));
const ENDS = Object.keys(suffixes).sort((a, b) => b.length - a.length);

test('opacity: auto is exactly 1/n over a family\'s n paths, with no floor', () => {
  assert.equal(B.autoOpacity(1), 1);
  assert.equal(B.autoOpacity(4), 0.25);
  assert.equal(B.autoOpacity(137), 1 / 137);
  assert.equal(B.autoOpacity(1001), 1 / 1001);
  const rows = [];
  for (let k = 0; k < 137; k++) for (let i = 0; i < 3; i++) rows.push({ t: i, run: `r${k}`, situation: 'real', source: 'real', body: 'tool0', frame: 'base', x_mm: i, y_mm: k, z_mm: 0 });
  const columns = Object.fromEntries(Object.keys(rows[0]).map((c) => [c, { id: c, type: typeof rows[0][c] === 'number' ? 'number' : 'text' }]));
  const m = B.bindTrajectory({ rows, columns, view: { type: 'trajectory3d', trajectory3d: {}, style: { families: { property: 'source', colors: { real: 1 } } } },
    tokens: { series: ['#s1', '#s2', '#s3', '#s4', '#s5', '#s6', '#s7', '#s8'], muted: '#mut' }, layers: {} });
  assert.equal(m.paths.length, 137);
  assert.ok(m.paths.every((p) => p.alpha === 1 / 137), `alphas ${[...new Set(m.paths.map((p) => p.alpha))]}`);
});

test('the Servo template\'s coverage file is the contract\'s coverage_samples: columns, types, units, weights, ≤ 150,000 rows', () => {
  const dir = join(EX, 'robotics-servo');
  const side = json(join(dir, 'coverage_samples.schema.json'));
  const rows = parseCSV(readFileSync(join(dir, 'coverage_samples.csv'), 'utf8'), { schema: side.schema });
  const contract = json(join(SCHEMAS, 'coverage_samples.schema.json'));
  const want = Object.fromEntries(contract.schema.fields.map((f) => [f.name, f]));
  const fields = side.schema.fields;
  for (const f of fields) {
    if (want[f.name]) {
      assert.equal(f.type, want[f.name].type, `${f.name}: the contract's type`);
      assert.equal(f.unit, want[f.name].unit, `${f.name}: the contract's unit`);
    } else if (f.type === 'number' && !exceptions.includes(f.name)) {
      const end = ENDS.find((e) => f.name.endsWith(e));
      assert.ok(end && f.unit === suffixes[end], `${f.name}: a number not in the contract ends in its unit`);
    }
  }
  for (const r of contract.required) assert.ok(fields.some((f) => f.name === r), `declares required ${r}`);
  assert.ok(rows.length > 1000 && rows.length <= 150000, `${rows.length} rows`);
  assert.ok(rows.every((r) => r.w === 0 || r.w === 1), 'weights 0 or 1');
  assert.ok(rows.every((r) => r.source === 'real' && r.situation === 'real'), 'real rack runs');
  assert.deepEqual([...new Set(rows.map((r) => r.device))].sort(), ['CAN 12', 'CAN 14']);
  assert.ok(typeof side.display_hz === 'number' && side.display_hz > 0, 'the sidecar names its display rate');
});

test('the Robot arm template\'s grid is the contract\'s (BAM Reach\'s map as rows) and its workspace is a glTF binary', () => {
  const dir = join(EX, 'robotics-arm');
  const grid = json(join(dir, 'grid.json'));
  const contract = json(join(SCHEMAS, 'grid.schema.json'));
  for (const r of contract.required) assert.ok(grid.schema.fields.some((f) => f.name === r), `grid declares required ${r}`);
  assert.ok(grid.rows.length > 100 && grid.rows.every((r) => contract.required.every((c) => typeof r[c] === 'number')), 'every cell has its centre and value');
  assert.ok(grid.cell_mm > 0 && typeof grid.frame === 'string' && grid.frame, 'cell_mm and frame at the top level');
  assert.ok(grid.rows.every((r) => r.value >= 0 && r.value <= 1), 'a reach fraction');
  const glb = readFileSync(join(dir, 'media', 'workspace.glb'));
  assert.equal(glb.toString('latin1', 0, 4), 'glTF');
  assert.equal(glb.readUInt32LE(4), 2);
});

test('the templates read their coverage unlinked (a run pick never empties it) and draw it in the coverage panels', () => {
  const servo = parseBase(readFileSync(join(EX, 'robotics-servo', 'views.base'), 'utf8'));
  const cov = servo.datasets.coverage;
  assert.ok(cov && /coverage_samples\.csv$/.test(typeof cov === 'string' ? cov : cov.data), 'servo: datasets.coverage reads coverage_samples.csv');
  assert.ok(!(servo.links || []).some((l) => /^coverage\./.test(l.from) || /^coverage\./.test(l.to)), 'servo: coverage is linked to nothing');
  assert.ok((cov.facets || []).some((f) => f.property === 'device' && f.as === 'select'), 'servo: the coverage rail picks a servo');
  const names = new Set(servo.views.map((v) => v.name));
  for (const n of ['Angle coverage', 'Velocity coverage', 'Phase space']) assert.ok(names.has(n), `servo view ${n}`);
  assert.ok(servo.views.filter((v) => ['Angle coverage', 'Velocity coverage', 'Phase space'].includes(v.name)).every((v) => v.from === 'coverage'));
  const arm = parseBase(readFileSync(join(EX, 'robotics-arm', 'views.base'), 'utf8'));
  const byName = Object.fromEntries(arm.views.map((v) => [v.name, v]));
  assert.equal(byName.Coverage && byName.Coverage.type, 'trajectory3d');
  assert.ok(byName.Coverage.trajectory3d.workspace && /workspace\.glb$/.test(byName.Coverage.trajectory3d.workspace.model));
  assert.equal(byName.Reach && byName.Reach.type, 'voxels');
  assert.ok(byName['Joint range'] && byName['Joint range'].type === 'chart');
  const from = (v) => arm.datasets[v.from];
  assert.ok(!(arm.links || []).some((l) => [byName.Coverage.from, byName['Joint range'].from].some((d) => l.from.startsWith(`${d}.`) || l.to.startsWith(`${d}.`))), 'arm: coverage reads unlinked copies');
  assert.ok(from(byName.Reach) && /grid\.json$/.test(typeof from(byName.Reach) === 'string' ? from(byName.Reach) : from(byName.Reach).data));
  assert.ok(existsSync(join(EX, 'robotics-servo', 'source', 'build_coverage.py')) && existsSync(join(EX, 'robotics-arm', 'source', 'build_coverage.py')));
});
