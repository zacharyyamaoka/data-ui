// tools/release.mjs: the arithmetic, and each refusal, on a repository made here with a stand-in suite.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bumpLock, nextVersion, rollChangelog } from './release.mjs';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });


const TOOL = join(dirname(fileURLToPath(import.meta.url)), 'release.mjs');
const LOG = '# Changelog\n\nIntro.\n\n## Unreleased\n\n- a change\n\n## 0.1.0 (2026-10-30)\n\n- the start\n';

test('nextVersion: the three bumps, and an explicit version must be higher', () => {
  assert.equal(nextVersion('0.1.0', 'patch'), '0.1.1');
  assert.equal(nextVersion('0.1.3', 'minor'), '0.2.0');
  assert.equal(nextVersion('0.9.3', 'major'), '1.0.0');
  assert.equal(nextVersion('0.1.0', '1.0.0'), '1.0.0');
  assert.throws(() => nextVersion('1.2.0', '1.2.0'), /not higher/);
  assert.throws(() => nextVersion('1.2.0', 'banana'), /not a version/);
});

test('rollChangelog: Unreleased becomes the release, empty above it, older sections stay', () => {
  assert.equal(rollChangelog(LOG, '0.2.0', '2026-11-01'), '# Changelog\n\nIntro.\n\n## Unreleased\n\n## 0.2.0 (2026-11-01)\n\n- a change\n\n## 0.1.0 (2026-10-30)\n\n- the start\n');
  assert.throws(() => rollChangelog('# Changelog\n\n## Unreleased\n\n## 0.1.0 (x)\n', '0.2.0', 'd'), /empty/);
  assert.throws(() => rollChangelog('# Changelog\n', '0.2.0', 'd'), /no "## Unreleased"/);
  assert.match(rollChangelog('## Unreleased\n\n- only\n', '1.0.0', 'd'), /## 1\.0\.0 \(d\)\n\n- only\n/);
});

test('bumpLock moves both fields and nothing else', () => {
  const lock = JSON.parse(bumpLock('{"name":"x","version":"0.1.0","packages":{"":{"version":"0.1.0"},"node_modules/a":{"version":"9.9.9"}}}', '1.0.0'));
  assert.equal(lock.version, '1.0.0');
  assert.equal(lock.packages[''].version, '1.0.0');
  assert.equal(lock.packages['node_modules/a'].version, '9.9.9');
});

function repo() {
  const dir = tempDir('release-');
  const git = (...args) => { const r = spawnSync('git', ['-C', dir, ...args], { encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr); return r.stdout.trim(); };
  git('init', '-q', '-b', 'main');
  git('config', 'user.name', 'A');
  git('config', 'user.email', 'a@example.com');
  writeFileSync(join(dir, 'package.json'), '{\n  "name": "x",\n  "version": "0.1.0"\n}\n');
  writeFileSync(join(dir, 'package-lock.json'), '{"name":"x","version":"0.1.0","packages":{"":{"version":"0.1.0"}}}\n');
  writeFileSync(join(dir, 'CHANGELOG.md'), LOG);
  writeFileSync(join(dir, 'green.mjs'), 'process.exit(0)\n');
  writeFileSync(join(dir, 'red.mjs'), 'process.exit(1)\n');
  writeFileSync(join(dir, 'skips.mjs'), "import { writeFileSync } from 'node:fs'; writeFileSync(process.env.DATA_UI_TEST_SUMMARY, JSON.stringify({ results: [{ name: 'P2 checks', result: 'SKIPPED: no archive' }] }));\n");
  writeFileSync(join(dir, 'missing.mjs'), "import { writeFileSync } from 'node:fs'; writeFileSync(process.env.DATA_UI_JOURNEYS_SUMMARY, JSON.stringify({ apps: [{ app: 'objectdb', status: 'missing' }] })); process.exit(3);\n");
  git('add', '.');
  git('commit', '-q', '-m', 'start');
  return { dir, git };
}

const run = (dir, args, { suite = 'green', journeys = 'green' } = {}) => spawnSync('node', [TOOL, ...args], {
  encoding: 'utf8',
  env: { ...process.env, DATA_UI_RELEASE_ROOT: dir, DATA_UI_RELEASE_SUITE: `node ${suite}.mjs`, DATA_UI_RELEASE_JOURNEYS: `node ${journeys}.mjs` },
});

test('green on a clean main: one commit with the three files, the version moved, no tag unless asked', () => {
  const { dir, git } = repo();
  const r = run(dir, ['minor']);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(git('log', '-1', '--format=%s'), 'release: 0.2.0');
  assert.deepEqual(git('show', '--name-only', '--format=').split('\n').sort(), ['CHANGELOG.md', 'package-lock.json', 'package.json']);
  assert.equal(JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8')).version, '0.2.0');
  assert.equal(git('tag'), '');
  const tagged = run(dir, ['patch', '--tag']);
  assert.equal(tagged.status, 1, 'Unreleased is empty again, so a second release has nothing to say');
  assert.match(tagged.stderr, /empty/);
});

test('--tag tags, and --dry-run changes nothing', () => {
  const { dir, git } = repo();
  assert.equal(run(dir, ['major', '--dry-run']).status, 0);
  assert.equal(git('log', '--format=%s'), 'start');
  assert.equal(run(dir, ['major', '--tag']).status, 0);
  assert.equal(git('tag'), 'v1.0.0');
});

test('refuses: a dirty tree, another branch, a red suite, a skipped suite, a red journey, a missing journey', () => {
  const dirty = repo();
  writeFileSync(join(dirty.dir, 'new.txt'), 'x');
  assert.match(run(dirty.dir, ['patch']).stderr, /not clean/);

  const branch = repo();
  branch.git('checkout', '-q', '-b', 'lane/x');
  assert.match(run(branch.dir, ['patch']).stderr, /not main/);

  const red = repo();
  assert.match(run(red.dir, ['patch'], { suite: 'red' }).stderr, /suite is red/);
  assert.equal(red.git('log', '--format=%s'), 'start');
  assert.match(run(red.dir, ['patch'], { suite: 'skips' }).stderr, /skipped P2 checks/);
  assert.equal(run(red.dir, ['patch', '--allow-skip', 'P2 checks'], { suite: 'skips' }).status, 0);

  const apps = repo();
  assert.match(run(apps.dir, ['patch'], { journeys: 'red' }).stderr, /journey is red/);
  assert.match(run(apps.dir, ['patch'], { journeys: 'missing' }).stderr, /no green journey for objectdb \(missing\)/);
  assert.equal(run(apps.dir, ['patch', '--allow-missing', 'objectdb'], { journeys: 'missing' }).status, 0);
});
