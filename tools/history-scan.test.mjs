// tools/history-scan.mjs on a repository made here: what a tree scan cannot see is the point, so every case is a thing
// that left the tree and stayed in history, or sits in a commit's own fields.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadRules, notAnEmail, scanHistory, scanWith, summarize } from './history-scan.mjs';

// every folder a test makes goes when the file is done
const made = [];
const tempDir = (prefix) => { const dir = mkdtempSync(join(tmpdir(), prefix)); made.push(dir); return dir; };
after(() => { for (const dir of made) rmSync(dir, { recursive: true, force: true }); });


// WHY assembled: this file goes through the public export's scan too, so it may hold no real-looking address of its own
const AT = '@';
const TOOL = join(dirname(fileURLToPath(import.meta.url)), 'history-scan.mjs');
const git = (repo, ...args) => {
  const env = { ...process.env, GIT_AUTHOR_NAME: 'A', GIT_AUTHOR_EMAIL: `owner${AT}private.test`, GIT_COMMITTER_NAME: 'A', GIT_COMMITTER_EMAIL: `owner${AT}private.test` };
  const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', env });
  assert.equal(r.status, 0, r.stderr);
  return r.stdout.trim();
};

function fixture() {
  const repo = tempDir('history-scan-');
  git(repo, 'init', '-q', '-b', 'main');
  writeFileSync(join(repo, 'data.json'), '{"tag":"acme-hospital"}\n');
  writeFileSync(join(repo, 'doc.md'), 'lives in /home/alice/work\n');
  git(repo, 'add', 'data.json', 'doc.md');
  git(repo, 'commit', '-q', '-m', 'first');
  const first = git(repo, 'rev-parse', 'HEAD');
  git(repo, 'rm', '-q', 'data.json');
  writeFileSync(join(repo, 'blob.bin'), Buffer.concat([Buffer.from([0, 1, 2]), Buffer.from('/home/alice/inside-a-binary')]));
  git(repo, 'add', 'blob.bin');
  git(repo, 'commit', '-q', '-m', 'drop the data; see /home/alice/notes');
  return { repo, first };
}

const denyFile = (dir, text) => { const p = join(dir, 'deny.txt'); writeFileSync(p, text); return p; };

test('a value gone from the tree is still a hit, marked history only, with the commit that wrote it', () => {
  const { repo, first } = fixture();
  const rules = loadRules(denyFile(repo, '(?i)acme-hospital\n'));
  const found = scanHistory({ repo, rules });
  const hit = found.findings.find((f) => f.rule === 'deny-list:1');
  assert.ok(hit, 'the deleted file was scanned');
  assert.equal(hit.atTip, false);
  assert.deepEqual(hit.paths, ['data.json']);
  assert.equal(hit.commit, first);
});

test('a name in a file name is a hit, whatever the file holds', () => {
  const { repo } = fixture();
  writeFileSync(join(repo, 'thumb-acme-hospital.txt'), 'nothing here\n');
  git(repo, 'add', 'thumb-acme-hospital.txt');
  git(repo, 'commit', '-q', '-m', 'a file');
  const found = scanHistory({ repo, rules: loadRules(denyFile(repo, '(?i)acme-hospital\n')) });
  assert.ok(found.findings.some((f) => f.inPath && f.paths[0] === 'thumb-acme-hospital.txt'));
});

test('a binary blob is read too, and a tip file counts as at the tip', () => {
  const { repo } = fixture();
  const rows = summarize(scanHistory({ repo, rules: loadRules(denyFile(repo, 'nothing-here\n')) }));
  const home = rows.find((r) => r.rule === 'home-path');
  assert.equal(home.tip.size, 2, 'doc.md and blob.bin are both at the tip');
});

test("a commit's author, committer and message are scanned: a clean tree can still carry an address on every commit", () => {
  const { repo } = fixture();
  const found = scanHistory({ repo, rules: loadRules(denyFile(repo, 'nothing-here\n')) });
  const fields = (rule) => found.commitFindings.filter((f) => f.rule === rule).map((f) => f.field).sort();
  assert.deepEqual(fields('any-email'), ['author', 'author', 'committer', 'committer']);
  assert.deepEqual(fields('home-path'), ['message']);
});

test('the command exits 1 on a hit, 0 when the refs are clean, 2 with no deny list', () => {
  const { repo } = fixture();
  const run = (env) => spawnSync('node', [TOOL, '--repo', repo, '--quiet'], { encoding: 'utf8', env: { ...process.env, ...env } });
  assert.equal(run({ DATA_UI_DENY: denyFile(repo, 'acme-hospital\n') }).status, 1);
  assert.equal(run({ DATA_UI_DENY: join(repo, 'no-such-list') }).status, 2);
  const clean = tempDir('history-scan-clean-');
  git(clean, 'init', '-q', '-b', 'main');
  writeFileSync(join(clean, 'a.txt'), 'nothing\n');
  git(clean, 'add', 'a.txt');
  const env = { ...process.env, GIT_AUTHOR_NAME: 'A', GIT_AUTHOR_EMAIL: 'a@example.com', GIT_COMMITTER_NAME: 'A', GIT_COMMITTER_EMAIL: 'a@example.com' };
  assert.equal(spawnSync('git', ['-C', clean, 'commit', '-q', '-m', 'one'], { env }).status, 0);
  const ok = spawnSync('node', [TOOL, '--repo', clean], { encoding: 'utf8', env: { ...process.env, DATA_UI_DENY: denyFile(repo, 'acme-hospital\n') } });
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
});

test('what is not an address, and the allow list, stay out of the findings', () => {
  assert.equal(notAnEmail('logo@2x.png', false), true);
  assert.equal(notAnEmail('pkg@1.2.3', false), true);
  assert.equal(notAnEmail('Q@B.csJ', true), true, 'short noise in compressed bytes');
  assert.equal(notAnEmail('Q@B.csJ', false), false, 'the same text in a text file is a hit');
  assert.equal(notAnEmail(`owner.name${AT}private.test`, true), false, 'a real address in a binary chunk is a hit');
  const rules = [{ id: 'any-email', re: /[a-z]+@[a-z.]+/g }];
  assert.equal(scanWith(rules, `a@example.com b${AT}private.test`, { allow: [/@example\.com$/] })[0].count, 1);
});
