// data-ui vendor on a repository made here, with a stand-in build.mjs: what the four app scripts each promised, one test
// each. tools/vendor.mjs's real build is measured against the real repo in docs/CI.md; these need no node_modules.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pickFiles, resolveRef, vendor } from './vendor.mjs';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });

const BIN = join(dirname(fileURLToPath(import.meta.url)), '..', 'bin', 'data-ui.mjs');
const BUILD = `
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';

mkdirSync('dist/site', { recursive: true });
cpSync('src', 'dist', { recursive: true });
writeFileSync('dist/site/index.html', 'the docs site');
const files = {};
const walk = (d) => { for (const n of readdirSync(d)) { const p = join(d, n); if (p === 'dist/site') continue; if (statSync(p).isDirectory()) walk(p); else files[relative('dist', p)] = { bytes: statSync(p).size, sha256: process.env.BAD_MANIFEST ? '0' : createHash('sha256').update(readFileSync(p)).digest('hex') }; } };
walk('dist');
writeFileSync('dist/manifest.json', JSON.stringify({ name: 'data-ui', version: JSON.parse(readFileSync('package.json', 'utf8')).version,
  views: [{ type: 'table', folder: 'table' }, { type: 'pivot', folder: 'table' }, { type: 'cards', folder: 'cards' }, { type: 'map', folder: 'map' }], files }));
`;

function repo() {
  const dir = tempDir('vendor-repo-');
  const git = (...args) => { const r = spawnSync('git', ['-C', dir, ...args], { encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr); return r.stdout.trim(); };
  git('init', '-q', '-b', 'main');
  git('config', 'user.name', 'A');
  git('config', 'user.email', 'a@example.com');
  const write = (path, text) => { mkdirSync(dirname(join(dir, path)), { recursive: true }); writeFileSync(join(dir, path), text); };
  write('build.mjs', BUILD);
  write('package.json', '{"name":"data-ui","version":"1.2.0"}\n');
  write('package-lock.json', '{"packages":{"":{}}}\n');
  for (const f of ['data-ui.js', 'data-ui.css', 'data-ui.js.map', 'analysis.js', 'python/data_ui_base.py', 'views/table.js', 'views/cards.js', 'views/cards-lightbox-ABC.js', 'views/map.js', 'views/maplibre-gl-worker.mjs']) write(`src/${f}`, `// ${f}\n`);
  write('packages/views/map/manifest.json', '{"assets":[{"from":"x","to":"maplibre-gl-worker.mjs"}]}\n');
  write('packages/views/table/manifest.json', '{}\n');
  write('gallery/robotics/CONTRACT.md', 'the producers contract\n');
  git('add', '.');
  git('commit', '-q', '-m', 'the kit');
  return { dir, git, write };
}

const sha = (p) => createHash('sha256').update(readFileSync(p)).digest('hex');
const into = () => join(tempDir('vendor-into-'), 'data-ui');
const quiet = () => {};

test('it copies the commit, never the checkout: an uncommitted edit stays out', () => {
  const { dir, write } = repo();
  write('src/data-ui.js', '// a lane\'s uncommitted edit\n');
  const target = into();
  vendor({ repo: dir, wanted: 'main', into: target, log: quiet });
  assert.equal(readFileSync(join(target, 'data-ui.js'), 'utf8'), '// data-ui.js\n');
});

test('VENDOR.json names the commit and every file, maps and the docs site left out, on_main said', () => {
  const { dir, git } = repo();
  const target = into();
  const record = vendor({ repo: dir, wanted: 'HEAD', into: target, log: quiet });
  const onDisk = JSON.parse(readFileSync(join(target, 'VENDOR.json'), 'utf8'));
  assert.deepEqual(onDisk, JSON.parse(JSON.stringify(record)));
  assert.equal(record.commit, git('rev-parse', 'HEAD'));
  assert.equal(record.on_main, true);
  assert.equal(record.version, '1.2.0');
  assert.equal(record.manifest_sha256, sha(join(target, 'manifest.json')));
  assert.ok(!existsSync(join(target, 'data-ui.js.map')));
  assert.ok(!existsSync(join(target, 'site')));
  assert.ok(record.skipped['*.map'] && record.skipped['site/']);
  for (const [name, hash] of Object.entries(record.files)) assert.equal(sha(join(target, name)), hash, name);
  git('checkout', '-q', '-b', 'lane/x');
  git('commit', '-q', '--allow-empty', '-m', 'on a lane');
  assert.equal(vendor({ repo: dir, wanted: 'lane/x', into: target, log: quiet }).on_main, false);
});

test('--views: only those folders, with their split chunks and assets; the rest recorded as left out', () => {
  const { dir } = repo();
  const target = into();
  const record = vendor({ repo: dir, wanted: 'main', into: target, views: ['cards'], log: quiet });
  assert.deepEqual(readdirSync(join(target, 'views')).sort(), ['cards-lightbox-ABC.js', 'cards.js']);
  assert.match(record.skipped['views/table.js'], /table view/);
  assert.deepEqual(record.views, ['cards']);
});

test('--without-views takes a view and its asset; --without takes a file or a folder', () => {
  const { dir } = repo();
  const target = into();
  vendor({ repo: dir, wanted: 'main', into: target, withoutViews: ['map'], without: ['python/', 'analysis.js'], log: quiet });
  assert.ok(!existsSync(join(target, 'views/map.js')));
  assert.ok(!existsSync(join(target, 'views/maplibre-gl-worker.mjs')), 'the worker is the map view\'s asset');
  assert.ok(!existsSync(join(target, 'python')));
  assert.ok(!existsSync(join(target, 'analysis.js')));
  assert.ok(existsSync(join(target, 'views/table.js')));
});

test('a name the build does not have is refused, and says what it does have', () => {
  const manifest = { views: [{ folder: 'table' }], files: { 'data-ui.js': {} } };
  assert.throws(() => pickFiles({ manifest, sourceViews: {}, views: ['tabel'] }), /no view folder tabel in this build; it has table/);
  assert.throws(() => pickFiles({ manifest, sourceViews: {}, without: ['nope.js'] }), /--without nope\.js/);
});

test('a build that does not match its manifest is refused, and the old copy stands', () => {
  const { dir } = repo();
  const target = into();
  vendor({ repo: dir, wanted: 'main', into: target, log: quiet });
  const before = sha(join(target, 'VENDOR.json'));
  process.env.BAD_MANIFEST = '1';
  try { assert.throws(() => vendor({ repo: dir, wanted: 'main', into: target, log: quiet }), /does not match its manifest/); } finally { delete process.env.BAD_MANIFEST; }
  assert.equal(sha(join(target, 'VENDOR.json')), before);
  assert.deepEqual(readdirSync(dirname(target)), ['data-ui'], 'nothing half-made is left beside it');
});

test('a folder that is not a vendored kit is left alone', () => {
  const { dir } = repo();
  const target = into();
  mkdirSync(target);
  writeFileSync(join(target, 'my-thesis.txt'), 'years of work');
  assert.throws(() => vendor({ repo: dir, wanted: 'main', into: target, log: quiet }), /left alone/);
  assert.ok(existsSync(join(target, 'my-thesis.txt')));
});

test('a version is its tag; a version with no tag says which there are', () => {
  const { dir, git } = repo();
  assert.throws(() => resolveRef(dir, '1.2.0'), /no release 1\.2\.0: tags here are none yet/);
  git('tag', 'v1.2.0');
  assert.deepEqual(resolveRef(dir, '1.2.0'), { ref: '1.2.0', commit: git('rev-parse', 'HEAD'), version: '1.2.0' });
  assert.throws(() => resolveRef(dir, 'no-such-branch'), /not a commit/);
});

test('--kit-dir and --also: sim2real\'s shape, the kit in dist/ and files from the same commit beside it', () => {
  const { dir } = repo();
  const target = into();
  const record = vendor({ repo: dir, wanted: 'main', into: target, kitDir: 'dist', also: ['gallery/robotics'], log: quiet });
  assert.ok(existsSync(join(target, 'dist/data-ui.js')));
  assert.ok(existsSync(join(target, 'VENDOR.json')));
  assert.equal(readFileSync(join(target, 'gallery/robotics/CONTRACT.md'), 'utf8'), 'the producers contract\n');
  assert.ok(record.files['gallery/robotics/CONTRACT.md']);
  assert.equal(record.kit_dir, 'dist');
});

test('the command: usage and exit status', () => {
  const { dir } = repo();
  const none = spawnSync('node', [BIN, 'vendor', 'main'], { encoding: 'utf8' });
  assert.equal(none.status, 2);
  assert.match(none.stderr, /usage: data-ui vendor/);
  const target = into();
  const ok = spawnSync('node', [BIN, 'vendor', 'main', '--repo', dir, '--into', target, '--views', 'table'], { encoding: 'utf8' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.match(ok.stdout, /vendored data-ui 1\.2\.0 [0-9a-f]{7} on main/);
  assert.equal(spawnSync('node', [BIN, 'vendor', 'nope', '--repo', dir, '--into', target], { encoding: 'utf8' }).status, 1);
});
