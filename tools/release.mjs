// A release: the version moves, the changelog gets its section, and nothing happens unless the suite is green on a clean
// main.
//
//   node tools/release.mjs patch|minor|major|X.Y.Z [--dry-run] [--tag] [--allow-skip NAME ...] [--allow-missing APP ...]
//
// In order, stopping at the first refusal:
// 1. A clean main: HEAD is main, nothing uncommitted or untracked (the rule of tools/release-check.mjs, for the same reason:
//    a release must be rebuildable from a commit), and Unreleased in CHANGELOG.md is not empty.
// 2. The full suite, `node tools/test-all.mjs --strict`. A skipped suite refuses too: a release is cut on the machine that
//    can run all of it, unless --allow-skip names that suite.
// 3. Each app's journey, `node tools/app-journeys.mjs --ref HEAD`. A red journey refuses. A journey that is missing, or was
//    red on the app's own kit already, refuses unless --allow-missing names the app, so a gap is a decision somebody wrote
//    down.
// 4. The tree is still clean: a suite that wrote into tracked files is a bug to fix first.
// 5. package.json, package-lock.json and CHANGELOG.md change, and one commit `release: X.Y.Z` holds them.
// --tag adds the annotated tag vX.Y.Z. WHY opt-in: the tag is the published promise, and tagging 1.0 is its own decision.
// --dry-run stops after step 1 and prints what would change.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.DATA_UI_RELEASE_ROOT || join(dirname(fileURLToPath(import.meta.url)), '..');
const SUITE = process.env.DATA_UI_RELEASE_SUITE ? process.env.DATA_UI_RELEASE_SUITE.split(' ') : ['node', 'tools/test-all.mjs', '--strict'];
const JOURNEYS = process.env.DATA_UI_RELEASE_JOURNEYS ? process.env.DATA_UI_RELEASE_JOURNEYS.split(' ') : ['node', 'tools/app-journeys.mjs', '--ref', 'HEAD'];

/** The version after `current` for patch, minor, major, or an explicit X.Y.Z, which must be higher. */
export function nextVersion(current, bump) {
  const parse = (v) => { const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v); if (!m) throw new Error(`not a version: ${v}`); return m.slice(1).map(Number); };
  const [major, minor, patch] = parse(current);
  if (bump === 'major') return `${major + 1}.0.0`;
  if (bump === 'minor') return `${major}.${minor + 1}.0`;
  if (bump === 'patch') return `${major}.${minor}.${patch + 1}`;
  const next = parse(bump);
  const higher = next[0] - major || next[1] - minor || next[2] - patch;
  if (higher <= 0) throw new Error(`${bump} is not higher than ${current}`);
  return bump;
}

/** The changelog with Unreleased's body under a new `## X.Y.Z (date)` heading and an empty Unreleased above it. */
export function rollChangelog(text, version, date) {
  const m = /^## Unreleased[^\n]*\n([\s\S]*?)(?=^## |\s*$(?![\s\S]))/m.exec(text);
  if (!m) throw new Error('CHANGELOG.md has no "## Unreleased" section');
  const body = m[1].trim();
  if (!body) throw new Error('Unreleased in CHANGELOG.md is empty: say what this release changes');
  return `${text.slice(0, m.index)}## Unreleased\n\n## ${version} (${date})\n\n${body}\n\n${text.slice(m.index + m[0].length).replace(/^\s+/, '')}`;
}

/** package-lock.json's two version fields, moved. */
export function bumpLock(text, version) {
  const lock = JSON.parse(text);
  lock.version = version;
  if (lock.packages && lock.packages['']) lock.packages[''].version = version;
  return `${JSON.stringify(lock, null, 2)}\n`;
}

// WHY: `node` on PATH can be another version than the one running this (docs/CI.md), and the suite's digests are per version
const onThisNode = (cmd) => (cmd === 'node' ? process.execPath : cmd);
const git = (...args) => spawnSync('git', ['-C', ROOT, ...args], { encoding: 'utf8' });
const refuse = (why) => { console.error(`refusing to release: ${why}`); process.exit(1); };

function guard() {
  const found = [];
  const head = git('symbolic-ref', '--quiet', '--short', 'HEAD');
  if (head.stdout.trim() !== 'main') found.push(`HEAD is ${head.stdout.trim() || 'detached'}, not main`);
  const status = git('status', '--porcelain');
  if (status.status !== 0) found.push(`${ROOT} is not a git checkout`);
  else if (status.stdout.trim()) found.push(`the checkout is not clean:\n${status.stdout.trimEnd()}`);
  return found;
}

function main(args) {
  const bump = args.find((a) => !a.startsWith('--') && !['--allow-skip', '--allow-missing'].includes(args[args.indexOf(a) - 1]));
  if (!bump) { console.error('usage: release.mjs patch|minor|major|X.Y.Z [--dry-run] [--tag] [--allow-skip NAME ...] [--allow-missing APP ...]'); process.exit(2); }
  const many = (flag) => args.flatMap((a, i) => (a === flag ? [args[i + 1]] : []));
  const dry = args.includes('--dry-run');

  const found = guard();
  if (found.length) refuse(`\n- ${found.join('\n- ')}`);
  const pkgPath = join(ROOT, 'package.json');
  const lockPath = join(ROOT, 'package-lock.json');
  const logPath = join(ROOT, 'CHANGELOG.md');
  const pkgText = readFileSync(pkgPath, 'utf8');
  const pkg = JSON.parse(pkgText);
  let version, changelog;
  try {
    version = nextVersion(pkg.version, bump);
    changelog = rollChangelog(readFileSync(logPath, 'utf8'), version, new Date().toISOString().slice(0, 10));
  } catch (e) { refuse(e.message); }
  if (git('rev-parse', '--verify', '--quiet', `refs/tags/v${version}`).status === 0) refuse(`the tag v${version} already exists`);
  console.log(`release: ${pkg.version} -> ${version} on main ${git('rev-parse', '--short', 'HEAD').stdout.trim()}`);
  if (dry) { console.log('release: --dry-run stops here; nothing changed'); return; }

  const summaryFile = join(mkdtempSync(join(tmpdir(), 'data-ui-release-')), 'summary.json');
  console.log(`\n== release: the suite: ${SUITE.join(' ')}`);
  const suite = spawnSync(onThisNode(SUITE[0]), SUITE.slice(1), { cwd: ROOT, stdio: 'inherit', env: { ...process.env, DATA_UI_TEST_SUMMARY: summaryFile } });
  if (suite.status !== 0) refuse(`the suite is red (exit ${suite.status})`);
  if (existsSync(summaryFile)) {
    const allowed = new Set(many('--allow-skip'));
    const skipped = JSON.parse(readFileSync(summaryFile, 'utf8')).results.filter((r) => r.result.startsWith('SKIP') && !allowed.has(r.name));
    if (skipped.length) refuse(`the suite skipped ${skipped.map((r) => r.name).join(', ')}: run it where they can run, or say --allow-skip NAME`);
  }

  console.log(`\n== release: the apps' journeys: ${JOURNEYS.join(' ')}`);
  const journeyFile = join(dirname(summaryFile), 'journeys.json');
  const journeys = spawnSync(onThisNode(JOURNEYS[0]), JOURNEYS.slice(1), { cwd: ROOT, stdio: 'inherit', env: { ...process.env, DATA_UI_JOURNEYS_SUMMARY: journeyFile } });
  if (journeys.status === 1) refuse('an app\'s journey is red');
  if (journeys.status !== 0) {
    const allowed = new Set(many('--allow-missing'));
    const gaps = existsSync(journeyFile) ? JSON.parse(readFileSync(journeyFile, 'utf8')).apps.filter((a) => a.status !== 'pass' && !allowed.has(a.app)).map((a) => `${a.app} (${a.status})`) : ['(no summary)'];
    if (gaps.length) refuse(`no green journey for ${gaps.join(', ')}: fix it, or say --allow-missing APP`);
  }

  const after = guard();
  if (after.length) refuse(`the run changed the checkout:\n- ${after.join('\n- ')}`);
  writeFileSync(pkgPath, pkgText.replace(/("version":\s*")[^"]+(")/, `$1${version}$2`));
  writeFileSync(lockPath, bumpLock(readFileSync(lockPath, 'utf8'), version));
  writeFileSync(logPath, changelog);
  const add = git('add', 'package.json', 'package-lock.json', 'CHANGELOG.md');
  if (add.status !== 0) refuse(add.stderr);
  const commit = git('commit', '-q', '-m', `release: ${version}`);
  if (commit.status !== 0) refuse(commit.stderr);
  if (args.includes('--tag')) {
    const tag = git('tag', '-a', `v${version}`, '-m', `data-ui ${version}`);
    if (tag.status !== 0) refuse(tag.stderr);
  }
  console.log(`release: ${version} is ${git('rev-parse', '--short', 'HEAD').stdout.trim()}${args.includes('--tag') ? `, tagged v${version}` : '; not tagged (--tag does that)'}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main(process.argv.slice(2));
