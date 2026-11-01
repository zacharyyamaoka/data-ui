// npm run deploy: the only way data-ui.dev changes. Each step must pass before the next one runs:
//   1. a clean checkout of main: HEAD is refs/heads/main and `git status --porcelain` is empty (untracked files too),
//      and no tracked file matches the deny list (tools/deny-scan.mjs --tree)
//   2. npm test, the full suite (it builds dist/ and captures the gallery's thumbnails first)
//   3. tools/publish-site.mjs: dist/site -> dist/publish, home paths redacted, privacy scan, Cloudflare's limits
//   4. wrangler deploy (pinned in tools/deploy/, installed there on first use)
//   5. the live site answers with this commit's release.json, and its pages and gallery thumbnails return 200
//
//   npm --prefix ~/data-ui run deploy            everything
//   node tools/release-check.mjs --check                  step 1 only (exit 0 or say why not)
//
// WHY a clean main and not "whatever is on disk" (robotparts' release_check, 2026-10-22): what is live must be
// rebuildable from a commit anyone can check out; the site's release.json names that commit.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const LIVE = 'https://data-ui.dev';
const git = (...a) => { const r = spawnSync('git', ['-C', ROOT, ...a], { encoding: 'utf8' }); return r.status === 0 ? r.stdout.trim() : null; };
const run = (label, cmd, args, opts = {}) => {
  console.log(`\n== deploy: ${label}`);
  const r = spawnSync(cmd, args, { cwd: ROOT, stdio: 'inherit', ...opts });
  if (r.status !== 0) { console.error(`\nrefusing to deploy: ${label} failed (exit ${r.status})`); process.exit(1); }
};

function guard() {
  const found = [];
  const branch = git('symbolic-ref', '--quiet', '--short', 'HEAD');
  if (branch !== 'main') found.push(`HEAD is ${branch || 'detached'}, not main: deploy from a checkout of main`);
  const status = git('status', '--porcelain');
  if (status === null) found.push(`${ROOT} is not a git checkout`);
  else if (status) found.push(`the checkout is not clean (commit or stash first):\n${status}`);
  return found;
}

const found = guard();
if (found.length) { console.error(`refusing to deploy:\n${found.map((f) => `- ${f}`).join('\n')}`); process.exit(1); }
const commit = git('rev-parse', 'HEAD');
console.log(`deploy: main ${commit.slice(0, 7)}, a clean checkout`);
if (process.argv.includes('--check')) process.exit(0);

// the public-data gate on main's whole tree, not only on what the site uploads (customer data reached main through a
// bench scenario on 2026-10-26 and never through the site; tools/deny-scan.mjs, its list outside git)
run('deny list over the git tree', 'node', ['tools/deny-scan.mjs', '--tree']);
run('npm test (build, thumbnails, every suite)', 'npm', ['test']);
// the suite may not leave the tree dirty either: it would mean the build wrote into tracked files
const after = guard();
if (after.length) { console.error(`refusing to deploy: the test run changed the checkout:\n${after.join('\n')}`); process.exit(1); }
if (!existsSync(join(ROOT, 'site', '.thumbs', 'manifest.json'))) { console.error('refusing to deploy: no gallery thumbnails (site/capture-thumbs.py did not run)'); process.exit(1); }
run('publish (redact, scan, limits)', 'node', ['tools/publish-site.mjs', '--commit', commit]);
const wrangler = join(ROOT, 'tools', 'deploy', 'node_modules', '.bin', 'wrangler');
if (!existsSync(wrangler)) run('install pinned wrangler', 'npm', ['--prefix', join(ROOT, 'tools', 'deploy'), 'ci', '--no-fund', '--no-audit']);
run('wrangler deploy', wrangler, ['deploy']);

// ---- 5: the live site is this commit (Cloudflare's edge can take a few seconds to serve the new assets)
const thumbs = JSON.parse(readFileSync(join(ROOT, 'dist', 'publish', 'gallery', 'gallery.json'), 'utf8'));
const firstThumb = (Array.isArray(thumbs) ? thumbs : thumbs.rows || [])[0];
const paths = ['/', '/gallery/', '/views/', '/gallery/robotparts-actuators/', '/kit/data-ui.js'];
if (firstThumb && firstThumb.thumb) paths.push(`/gallery/${firstThumb.thumb}`);
let live = null;
for (let i = 0; i < 12; i++) {
  try {
    const r = await fetch(`${LIVE}/release.json`, { headers: { 'cache-control': 'no-cache' } });
    if (r.ok) { live = await r.json(); if (live.commit === commit) break; }
  } catch (e) { live = { error: String(e) }; }
  await new Promise((ok) => setTimeout(ok, 5000));
}
if (!live || live.commit !== commit) { console.error(`deployed, but ${LIVE}/release.json says ${JSON.stringify(live)}, not ${commit}`); process.exit(1); }
const bad = [];
for (const p of paths) {
  const r = await fetch(LIVE + p, { redirect: 'follow' }).catch((e) => ({ status: String(e) }));
  console.log(`live ${r.status} ${LIVE}${p}`);
  if (r.status !== 200) bad.push(p);
}
if (bad.length) { console.error(`deployed ${commit.slice(0, 7)}, but these do not answer 200: ${bad.join(', ')}`); process.exit(1); }
console.log(`\ndata-ui.dev is main ${commit.slice(0, 7)}`);
