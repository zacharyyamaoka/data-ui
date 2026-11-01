// data-ui vendor <version|ref> --into <path>: the kit an app serves, built from a clean archive of one commit and checked
// byte for byte. It replaces the apps' own tools/vendor_data_ui.py (docs/migrations/).
//
//   data-ui vendor main --into site/static/data-ui
//   data-ui vendor 1.2.0 --into vendor/data-ui --views table,list,cards   (a version is its tag, v1.2.0)
//
//   --views a,b          only these view folders (each one's split chunks and assets come with it); the default is all
//   --without-views a,b  every view but these
//   --without x,y        leave out a file or a folder of the build: analysis.js, python/
//   --kit-dir dist       the kit in <into>/dist (VENDOR.json stays at <into>), for a host that keeps other files beside it
//   --also SRC[=DEST]    copy SRC from the same commit to <into>/DEST (default SRC); repeatable, a file or a folder
//   --keep-maps          keep the source maps (a debugger's; left out by default)
//   --node-modules DIR   the node_modules to build with (default: a worktree of the repo with this commit's exact lock)
//   --install            none of those exist: npm ci in the archive
//   --repo DIR           the data-ui repository (default: the one this file is in)
//
// What it does, in order, so an interrupted run leaves the old copy standing:
// 1. Exports the commit with `git archive` into a temporary folder and builds there. WHY never a worktree: robotparts'
//    copy was built from one, with a lane's uncommitted edits in it, and a checkout's dist/ says nothing about any commit.
// 2. Picks the files from dist/manifest.json, and refuses a file whose bytes differ from the manifest's sha256.
// 3. Writes the copy beside <into>, with VENDOR.json, swaps it in by rename, and reads every file back.
// VENDOR.json: the repo, ref, version, commit, its date and subject, whether it is on main, the manifest's sha256, each
// file's sha256, and what was left out and why. An app's own gate holds its copy to that file (docs/migrations/).
// WHY re-copied, never edited (docs/peps/0001-data-ui-shape.md §8): an app's contract with the kit is its .base files and
// data; the kit underneath is replaced whole.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

const run = (cmd, args, opts = {}) => {
  const r = spawnSync(cmd, args, { encoding: 'utf8', maxBuffer: 1 << 30, ...opts });
  if (r.status !== 0) throw new Error(`${cmd} ${args.slice(0, 4).join(' ')}: ${r.stderr || `exit ${r.status}`}`);
  return r.stdout;
};
const git = (repo, ...args) => run('git', ['-C', repo, ...args]).trim();

/** A version (1.2.0, its tag v1.2.0) or any ref, as {ref, commit, version}. */
export function resolveRef(repo, wanted) {
  const version = /^\d+\.\d+\.\d+(?:-[\w.]+)?$/.test(wanted) ? wanted : null;
  const ref = version ? `refs/tags/v${version}` : wanted;
  const r = spawnSync('git', ['-C', repo, 'rev-parse', '--verify', '--quiet', `${ref}^{commit}`], { encoding: 'utf8' });
  if (r.status !== 0) {
    const tags = git(repo, 'tag', '--list', 'v*').split('\n').filter(Boolean);
    throw new Error(version ? `no release ${version}: tags here are ${tags.join(', ') || 'none yet'}; a branch or commit works too` : `${wanted} is not a commit of ${repo}`);
  }
  return { ref: wanted, commit: r.stdout.trim(), version };
}

/** A node_modules installed for exactly this lock: the first worktree of `repo` that has one. */
export function nodeModulesFor(repo, lock) {
  for (const line of git(repo, 'worktree', 'list', '--porcelain').split('\n')) {
    if (!line.startsWith('worktree ')) continue;
    const tree = line.slice('worktree '.length);
    const modules = join(tree, 'node_modules');
    const theirs = join(tree, 'package-lock.json');
    if (existsSync(modules) && existsSync(theirs) && readFileSync(theirs).equals(lock)) return modules;
  }
  return null;
}

/** A private node_modules under the build, hard-linked. WHY not a symlink: esbuild resolves it to its real path and hashes
    input paths relative to the output, so a chunk's name, and every file that imports it, changed with how deep the
    temporary folder sat. The same commit came out as different bytes from two scripts (2026-10-30: cards-lightbox-2WWOLVAR.js
    in Vibe Tracks' copy, -3T25EGO2 here). Inside the tree the paths are the same everywhere. */
function linkModules(from, to) {
  const real = realpathSync(from);
  const linked = spawnSync('cp', ['-al', `${real}/.`, to], { encoding: 'utf8' });
  if (linked.status === 0) return;
  rmSync(to, { recursive: true, force: true });
  run('cp', ['-a', `${real}/.`, to]); // another filesystem: a real copy
}

/** The commit's files in `work`, built; returns the folder. */
export function buildCommit({ repo, commit, work, modules, install }) {
  const archive = spawnSync('git', ['-C', repo, 'archive', '--format=tar', commit], { maxBuffer: 2 ** 32 });
  if (archive.status !== 0) throw new Error(`git archive: ${archive.stderr}`);
  mkdirSync(work, { recursive: true });
  run('tar', ['-x', '-C', work], { input: archive.stdout, encoding: 'buffer' });
  const lockFile = join(work, 'package-lock.json');
  const lock = existsSync(lockFile) ? readFileSync(lockFile) : Buffer.alloc(0);
  const found = modules ? resolve(modules) : nodeModulesFor(repo, lock);
  if (install) run('npm', ['ci', '--no-fund', '--no-audit'], { cwd: work });
  else if (found) linkModules(found, join(work, 'node_modules'));
  else if (existsSync(join(work, 'package-lock.json')) && Object.keys(JSON.parse(lock.toString() || '{}').packages || {}).length > 1) {
    throw new Error(`no worktree of ${repo} has a node_modules for ${commit.slice(0, 7)}'s package-lock.json: pass --node-modules DIR or --install`);
  }
  run(process.execPath, ['build.mjs'], { cwd: work });
  return work;
}

/** Which files of the manifest to copy, and why each other one stayed behind. */
export function pickFiles({ manifest, sourceViews, views, withoutViews = [], without = [], keepMaps = false }) {
  const folders = [...new Set((manifest.views || []).map((v) => v.folder))].sort();
  const wanted = views || folders.filter((f) => !withoutViews.includes(f));
  const unknown = [...(views || []), ...withoutViews].filter((f) => !folders.includes(f));
  if (unknown.length) throw new Error(`no view folder ${unknown.join(', ')} in this build; it has ${folders.join(', ')}`);
  const ownedBy = (name) => {
    for (const folder of folders) {
      if (name === `views/${folder}.js` || (name.startsWith(`views/${folder}-`) && name.endsWith('.js'))) return folder;
      if ((sourceViews[folder] || []).includes(name)) return folder;
    }
    return null;
  };
  const kept = [];
  const skipped = {};
  if (!keepMaps) skipped['*.map'] = 'source maps: only a debugger asks for them';
  skipped['site/'] = "data-ui's own docs site and gallery (not in the manifest)";
  for (const name of Object.keys(manifest.files).sort()) {
    if (name === 'manifest.json') continue;
    if (!keepMaps && name.endsWith('.map')) continue;
    const owner = ownedBy(name);
    if (owner && !wanted.includes(owner)) { skipped[name] = `the ${owner} view was left out`; continue; }
    const dropped = without.find((w) => name === w || (w.endsWith('/') && name.startsWith(w)));
    if (dropped) { skipped[dropped] = 'left out with --without'; continue; }
    kept.push(name);
  }
  for (const w of without) if (!skipped[w]) throw new Error(`--without ${w}: no such file or folder in this build`);
  return { kept, skipped, views: wanted };
}

/** Each view folder's asset files as dist names (views/<to>), read from the commit's own view manifests. */
function viewAssets(tree) {
  const out = {};
  const dir = join(tree, 'packages', 'views');
  if (!existsSync(dir)) return out;
  for (const folder of readdirSync(dir)) {
    const file = join(dir, folder, 'manifest.json');
    if (existsSync(file)) out[folder] = (JSON.parse(readFileSync(file, 'utf8')).assets || []).map((a) => `views/${a.to}`);
  }
  return out;
}

const walk = (dir, out = []) => { for (const n of readdirSync(dir)) { const p = join(dir, n); if (statSync(p).isDirectory()) walk(p, out); else out.push(p); } return out; };

/** The folder `into` may be replaced: it is new, empty, or holds an earlier copy of the kit. */
function refuseStranger(into) {
  if (!existsSync(into) || !readdirSync(into).length) return;
  const marks = ['VENDOR.json', 'VERSION', 'VENDOR.md', 'manifest.json', 'dist/manifest.json'];
  if (!marks.some((m) => existsSync(join(into, m)))) throw new Error(`${into} holds files and none of ${marks.join(', ')}: it does not look like a vendored kit, so it is left alone`);
}

/** The whole command. Returns the record it wrote. */
export function vendor({ repo = ROOT, wanted, into, views, withoutViews, without, kitDir = '', also = [], keepMaps, modules, install, log = console.log }) {
  const target = resolve(into);
  refuseStranger(target);
  const { ref, commit, version } = resolveRef(repo, wanted);
  const work = mkdtempSync(join(tmpdir(), 'data-ui-vendor-'));
  const staged = `${target}.vendoring-${process.pid}`;
  try {
    const tree = buildCommit({ repo, commit, work: join(work, 'tree'), modules, install });
    const dist = join(tree, 'dist');
    const manifestBytes = readFileSync(join(dist, 'manifest.json'));
    const manifest = JSON.parse(manifestBytes);
    const { kept, skipped, views: chosen } = pickFiles({ manifest, sourceViews: viewAssets(tree), views, withoutViews, without, keepMaps });
    const files = {};
    mkdirSync(staged, { recursive: true });
    for (const name of kept) {
      const bytes = readFileSync(join(dist, name));
      if (sha256(bytes) !== manifest.files[name].sha256) throw new Error(`${name} does not match its manifest sha256: the build is not what its manifest says`);
      const out = join(staged, kitDir, name);
      mkdirSync(dirname(out), { recursive: true });
      writeFileSync(out, bytes);
      files[join(kitDir, name)] = manifest.files[name].sha256;
    }
    writeFileSync(join(staged, kitDir, 'manifest.json'), manifestBytes);
    files[join(kitDir, 'manifest.json')] = sha256(manifestBytes);
    for (const spec of also) {
      const [source, dest = source] = spec.split('=');
      const from = join(tree, source);
      if (!existsSync(from)) throw new Error(`--also ${source}: not in ${commit.slice(0, 7)}`);
      const to = join(staged, dest);
      mkdirSync(dirname(to), { recursive: true });
      cpSync(from, to, { recursive: true });
      const copied = statSync(from).isDirectory() ? walk(to) : [to];
      for (const p of copied) files[relative(staged, p)] = sha256(readFileSync(p));
    }
    const parents = git(repo, 'log', '-1', '--format=%P', commit).split(' ').filter(Boolean);
    const onMain = spawnSync('git', ['-C', repo, 'merge-base', '--is-ancestor', commit, 'main']).status === 0;
    const record = {
      what: 'data-ui as this app serves it: re-vendor with data-ui vendor, never edit',
      repo, ref, version: version || manifest.version, commit, on_main: onMain,
      commit_date: git(repo, 'show', '-s', '--format=%cI', commit), subject: git(repo, 'show', '-s', '--format=%s', commit),
      ...(parents.length > 1 ? { parents: parents.map((sha) => ({ commit: sha, subject: git(repo, 'show', '-s', '--format=%s', sha) })) } : {}),
      built_with: `node build.mjs on a git archive of the commit (data-ui vendor, Node ${process.version})`,
      manifest_sha256: sha256(manifestBytes), kit_dir: kitDir || '.', views: chosen, skipped,
      files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))),
    };
    writeFileSync(join(staged, 'VENDOR.json'), `${JSON.stringify(record, null, 1)}\n`);
    for (const [name, hash] of Object.entries(files)) {
      if (sha256(readFileSync(join(staged, name))) !== hash) throw new Error(`${name} changed while copying`);
    }
    // WHY a rename: a server reading the folder sees the old kit or the new one, never a half-copied mix
    if (existsSync(target)) { const old = `${target}.old-${process.pid}`; renameSync(target, old); renameSync(staged, target); rmSync(old, { recursive: true, force: true }); } else renameSync(staged, target);
    const total = kept.reduce((sum, name) => sum + manifest.files[name].bytes, 0);
    log(`vendored data-ui ${record.version} ${commit.slice(0, 7)} ${onMain ? 'on main' : `NOT on main (${ref})`}: ${Object.keys(files).length} files, ${(total / 1e6).toFixed(2)} MB -> ${target}`);
    return record;
  } finally {
    rmSync(work, { recursive: true, force: true });
    rmSync(staged, { recursive: true, force: true });
  }
}

const USAGE = 'usage: data-ui vendor <version|ref> --into <path> [--views a,b] [--without-views a,b] [--without x,y] [--kit-dir d] [--also SRC[=DEST]] [--keep-maps] [--node-modules DIR] [--install] [--repo DIR]';

/** The command line, from bin/data-ui.mjs. Returns the exit status. */
export function main(argv) {
  const value = (flag) => { const i = argv.indexOf(flag); return i >= 0 ? argv[i + 1] : undefined; };
  const list = (flag) => { const v = value(flag); return v ? v.split(',').map((s) => s.trim()).filter(Boolean) : undefined; };
  const takesValue = new Set(['--into', '--views', '--without-views', '--without', '--kit-dir', '--also', '--node-modules', '--repo']);
  const wanted = argv.find((a, i) => !a.startsWith('--') && !takesValue.has(argv[i - 1]));
  const into = value('--into');
  if (!wanted || !into) { console.error(USAGE); return 2; }
  try {
    vendor({ repo: resolve(value('--repo') || ROOT), wanted, into, views: list('--views'), withoutViews: list('--without-views'), without: list('--without'), kitDir: value('--kit-dir') || '',
      also: argv.flatMap((a, i) => (a === '--also' ? [argv[i + 1]] : [])), keepMaps: argv.includes('--keep-maps'), modules: value('--node-modules'), install: argv.includes('--install') });
    return 0;
  } catch (e) {
    console.error(`data-ui vendor: ${e.message}`);
    return 1;
  }
}

