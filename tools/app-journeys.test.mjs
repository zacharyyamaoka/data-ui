// tools/app-journeys.mjs's verdicts, on a data-ui and an app made here. The real journeys take half an hour and need the
// real apps; what can go wrong in the gate itself is calling something a pass that was not.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { APPS, failLines, journey } from './app-journeys.mjs';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });

const BUILD = `
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
mkdirSync('dist', { recursive: true });
cpSync('src/data-ui.js', 'dist/data-ui.js');
const b = readFileSync('dist/data-ui.js');
writeFileSync('dist/manifest.json', JSON.stringify({ name: 'data-ui', version: '1.0.0', views: [], files: { 'data-ui.js': { bytes: b.length, sha256: createHash('sha256').update(b).digest('hex') } } }));
`;

function gitRepo(prefix, files) {
  const dir = tempDir(prefix);
  const git = (...args) => { const r = spawnSync('git', ['-C', dir, ...args], { encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr); return r.stdout.trim(); };
  git('init', '-q', '-b', 'main');
  git('config', 'user.name', 'A');
  git('config', 'user.email', 'a@example.com');
  for (const [path, text] of Object.entries(files)) { mkdirSync(dirname(join(dir, path)), { recursive: true }); writeFileSync(join(dir, path), text); }
  git('add', '.');
  git('commit', '-q', '-m', 'start');
  return dir;
}

const kit = (marker) => gitRepo('journey-kit-', { 'build.mjs': BUILD, 'package.json': '{"name":"data-ui","version":"1.0.0"}\n', 'package-lock.json': '{"packages":{"":{}}}\n', 'src/data-ui.js': `// ${marker}\n` });
// an app whose journey reads the kit it was given
const CHECK = (extra = '') => `
import { readFileSync } from 'node:fs';
const kit = readFileSync('kit/data-ui.js', 'utf8');
if (kit.includes('good')) console.log('PASS the kit draws'); else { console.log('FAIL the kit draws [took 41 ms]'); process.exitCode = 1; }
${extra}
`;
const app = (check = CHECK()) => gitRepo('journey-app-', { 'check.mjs': check, 'kit/data-ui.js': '// good\n', 'kit/manifest.json': '{}\n', 'kit/VENDOR.json': '{}\n' });
const spec = (repo, over = {}) => ({ app: 'demo', repo, into: 'kit', vendor: {}, needs: () => [], steps: () => [{ name: 'the journey', cmd: process.execPath, args: ['check.mjs'], minutes: 1 }], ...over });
const out = () => tempDir('journey-out-');
const run = (repo, kitRepo, over) => journey(spec(repo, over), { ref: 'main', repo: kitRepo, out: out() });

test('the real list covers the five apps, and every one proves itself some way', () => {
  assert.deepEqual(APPS.map((a) => a.app), ['robotparts', 'robotdx', 'sim2real', 'vibetracks', 'objectdb']);
  for (const a of APPS) assert.ok(a.repo && a.into && a.needs, a.app);
});

test('pass: the candidate is fine and there were checks to see it', async () => {
  const r = await run(app(), kit('good'));
  assert.equal(r.status, 'pass');
  assert.equal(r.steps[0].checks, 1);
});

test('fail: green on the app\'s own kit, red on the candidate', async () => {
  const r = await run(app(), kit('broken'));
  assert.equal(r.status, 'fail');
  assert.equal(r.own_kit, 'pass');
  assert.equal(r.steps[0].status, 'fail');
});

test('app-red: the same failure on its own kit is not the candidate\'s, and is not a pass either', async () => {
  const red = CHECK("console.log('FAIL an old bug [took 12 ms]'); process.exitCode = 1;");
  const r = await run(app(red), kit('good'));
  assert.equal(r.status, 'app-red');
  assert.equal(r.steps[0].status, 'app-red');
  assert.deepEqual(r.steps[0].new_failures, []);
});

test('fail: a new failure on top of an old red is still the candidate\'s', async () => {
  const red = CHECK("console.log('FAIL an old bug'); process.exitCode = 1;");
  const r = await run(app(red), kit('broken'));
  assert.equal(r.status, 'fail');
  assert.deepEqual(r.steps[0].new_failures, ['FAIL the kit draws']);
});

test('missing: exit 0 proves nothing without checks, and a SKIP is not a pass', async () => {
  const nothing = await run(app("console.log('all done, I promise');"), kit('good'));
  assert.equal(nothing.status, 'missing');
  assert.match(nothing.steps[0].why, /no checks/);
  const skipped = await run(app("console.log('SKIP track_kpis: no Playwright'); process.exit(0);"), kit('good'));
  assert.equal(skipped.status, 'missing');
  assert.match(skipped.steps[0].why, /skipped itself/);
});

test('missing: what the journey needs is not there, and it says what', async () => {
  const r = await run(app(), kit('good'), { needs: () => [['/no/such/site', 'the built site']] });
  assert.equal(r.status, 'missing');
  assert.match(r.why, /needs the built site/);
  assert.deepEqual(r.steps, []);
});

test("the app's checkout is not touched: its kit is the old one after a red run", async () => {
  const repo = app();
  await run(repo, kit('broken'));
  assert.equal(readFileSync(join(repo, 'kit/data-ui.js'), 'utf8'), '// good\n');
  assert.equal(spawnSync('git', ['-C', repo, 'status', '--porcelain'], { encoding: 'utf8' }).stdout, '');
});

test('a hang is a fail that names the limit, and nothing the journey started outlives it', async () => {
  const pidFile = join(tempDir('journey-pid-'), 'server.pid');
  // a journey that starts a server of its own and then waits forever, as robotparts' browser_check did on a renamed event
  const hang = `
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
if (readFileSync('kit/data-ui.js', 'utf8').includes('good')) { console.log('PASS the kit draws'); process.exit(0); }
const server = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });
writeFileSync(${JSON.stringify(pidFile)}, String(server.pid));
setInterval(() => {}, 1000);
`;
  const r = await run(app(hang), kit('broken'), { steps: () => [{ name: 'the journey', cmd: process.execPath, args: ['check.mjs'], minutes: 0.03 }] });
  assert.equal(r.status, 'fail');
  assert.equal(r.own_kit, 'pass');
  assert.match(r.steps[0].why, /timed out after 0\.03 min/);
  const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
  assert.equal(alive(Number(readFileSync(pidFile, 'utf8'))), false);
});

test('--own-kit runs what the app has, so a red there is the app\'s own', async () => {
  const r = await journey(spec(app()), { ref: 'main', repo: kit('broken'), out: out(), ownKit: true });
  assert.equal(r.status, 'pass');
});

test('the same failure reads the same on two runs: measured numbers out', () => {
  assert.deepEqual(failLines('PASS a\nFAIL  the peek opens   812 ms [812]\n  not ok 3 - thing\nok b\n'), ['FAIL the peek opens # ms', 'not ok # - thing']);
  assert.deepEqual(failLines('FAIL x 1\nFAIL x 2\n'), ['FAIL x #']);
});
