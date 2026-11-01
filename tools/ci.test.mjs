// CI's pins stay one set of numbers, and the workflow stays what docs/CI.md says it is.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });


const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');
const versions = Object.fromEntries(read('tools/ci/versions.env').trim().split('\n').map((l) => l.split('=')));
const workflow = read('.github/workflows/ci.yml');

test('the Playwright pin is one version: versions.env, requirements.txt', () => {
  assert.match(read('tools/ci/requirements.txt'), new RegExp(`^playwright==${versions.PLAYWRIGHT_VERSION.replace(/\./g, '\\.')}$`, 'm'));
});

test('every third-party action is pinned to a full commit, never a tag someone can move', () => {
  const uses = [...workflow.matchAll(/uses:\s*(\S+)/g)].map((m) => m[1]);
  assert.ok(uses.length >= 5);
  for (const use of uses) assert.match(use, /@[0-9a-f]{40}$/, use);
});

test('the workflow runs on every push to main and nightly, the full suite, strict', () => {
  assert.match(workflow, /push:\s*\n\s*branches:\s*\[main\]/);
  assert.match(workflow, /schedule:\s*\n\s*- cron:/);
  assert.match(workflow, /node tools\/test-all\.mjs --strict/);
});

test('a red run leaves a mark that stays: an issue, opened on failure and closed on green', () => {
  assert.match(workflow, /gh issue create/);
  assert.match(workflow, /gh issue close/);
});

test('the workflow installs the pins from versions.env before it uses them', () => {
  assert.ok(workflow.indexOf('tools/ci/versions.env') < workflow.indexOf('setup-node'), 'versions.env is read before setup-node');
  assert.match(workflow, /node-version: \$\{\{ env\.NODE_VERSION \}\}/);
});

test('the job summary says red first, lists every skip with its reason, and says when the suite never finished', () => {
  const file = join(tempDir('ci-summary-'), 'run.json');
  writeFileSync(file, JSON.stringify({ node: 'v22.18.0', total_seconds: 600, results: [
    { name: 'unit', result: 'pass', seconds: 30 },
    { name: 'browser checks', result: 'FAIL (exit 1)', seconds: 400 },
    { name: 'P2 checks', result: "SKIPPED: needs the rack's raw logs", seconds: null },
  ] }));
  const summary = spawnSync('node', [join(ROOT, 'tools/ci-summary.mjs'), file], { encoding: 'utf8' }).stdout;
  assert.match(summary, /^### RED: 1 failed · 2 ran, 1 skipped · 10 min · Node v22\.18\.0/);
  assert.match(summary, /\*\*browser checks\*\*: FAIL \(exit 1\)/);
  assert.match(summary, /P2 checks: needs the rack's raw logs/);
  assert.match(spawnSync('node', [join(ROOT, 'tools/ci-summary.mjs'), '/no/such/file'], { encoding: 'utf8' }).stdout, /did not finish/);
});
