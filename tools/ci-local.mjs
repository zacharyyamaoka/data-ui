// The CI run, here: a clean copy of a tree in a container shaped like a GitHub runner, with nothing of this machine in
// it. /archive, ~/ and psu-atlas's venv are not there, so a test that leans on them fails here first.
//
//   node tools/ci-local.mjs --ref main [--out DIR] [--cpus 4] [--memory 16g] [--image IMAGE]
//   node tools/ci-local.mjs --tree DIR    a folder instead of a ref: a public-export mirror (docs/PUBLIC-REPO.md)
//
// WHY a container and not the workflow: there is no remote yet, and when there is, a run here costs no CI minutes and can
// be repeated to measure flakiness. The shape (4 CPUs, 16 GB) is GitHub's standard Linux runner for a public repository.
// It runs tools/ci/steps.sh, the same last line as .github/workflows/ci.yml, as the invoking user.
// OUT gets test-all.log and summary.json. Exit status: the suite's.
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { homedir, tmpdir, userInfo } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const one = (flag, fallback) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : fallback; };
const versions = Object.fromEntries(readFileSync(join(ROOT, 'tools', 'ci', 'versions.env'), 'utf8').trim().split('\n').map((l) => l.split('=')));
const image = one('--image', `mcr.microsoft.com/playwright/python:v${versions.PLAYWRIGHT_VERSION}-noble`);
const out = resolve(one('--out', mkdtempSync(join(tmpdir(), 'data-ui-ci-'))));
mkdirSync(out, { recursive: true });

const run = (cmd, argv, opts = {}) => {
  const r = spawnSync(cmd, argv, { stdio: 'inherit', ...opts });
  if (r.status !== 0 && !opts.mayFail) { console.error(`${cmd} ${argv.slice(0, 3).join(' ')}: exit ${r.status}`); process.exit(1); }
  return r;
};

/** The pinned Node, taken out of its official image once. WHY not the host's: PATH here finds a Node that is not the pin. */
function pinnedNode() {
  const dir = join(homedir(), '.cache', 'data-ui-ci', `node-${versions.NODE_VERSION}`);
  if (existsSync(join(dir, 'bin', 'node'))) return dir;
  const made = spawnSync('docker', ['create', `node:${versions.NODE_VERSION}-slim`], { encoding: 'utf8' });
  if (made.status !== 0) { console.error(made.stderr); process.exit(1); }
  const id = made.stdout.trim();
  mkdirSync(join(dir, 'bin'), { recursive: true });
  mkdirSync(join(dir, 'lib'), { recursive: true });
  run('docker', ['cp', `${id}:/usr/local/bin/node`, join(dir, 'bin', 'node')]);
  run('docker', ['cp', `${id}:/usr/local/lib/node_modules`, join(dir, 'lib')]);
  run('docker', ['rm', id], { stdio: 'ignore' });
  run('ln', ['-s', '../lib/node_modules/npm/bin/npm-cli.js', join(dir, 'bin', 'npm')]);
  return dir;
}

/** The fonts tools/ci/fonts.conf names, from this machine. WHY mounted: the workflow installs them with apt, which needs root, and
    this container runs as the invoking user so that it leaves no root-owned files behind. */
const fontMounts = () => ['/usr/share/fonts/truetype/noto', '/usr/share/fonts/truetype/dejavu'].filter(existsSync).flatMap((dir) => ['-v', `${dir}:${dir}:ro`]);

const work = mkdtempSync(join(tmpdir(), 'data-ui-ci-tree-'));
const tree = join(work, 'tree');
if (args.includes('--tree')) {
  cpSync(resolve(one('--tree')), tree, { recursive: true, filter: (p) => !/\/\.git(\/|$)/.test(p) });
} else {
  mkdirSync(tree);
  const archive = spawnSync('git', ['-C', ROOT, 'archive', '--format=tar', one('--ref', 'HEAD')], { maxBuffer: 2 ** 32 });
  if (archive.status !== 0) { console.error(String(archive.stderr)); process.exit(1); }
  run('tar', ['-x', '-C', tree], { input: archive.stdout, stdio: ['pipe', 'inherit', 'inherit'] });
}
// a git repository of its own: some tools ask git who they are, and a runner's checkout is one
const quiet = { stdio: 'ignore' };
run('git', ['-C', tree, 'init', '-q'], quiet);
run('git', ['-C', tree, '-c', 'user.name=ci', '-c', 'user.email=ci@example.com', 'add', '.'], quiet);
run('git', ['-C', tree, '-c', 'user.name=ci', '-c', 'user.email=ci@example.com', 'commit', '-q', '-m', 'ci'], quiet);

const node = pinnedNode();
const { uid, gid } = userInfo();
const started = Date.now();
const inner = 'mkdir -p /tmp/home && tools/ci/steps.sh 2>&1 | tee /out/test-all.log; exit ${PIPESTATUS[0]}';
const result = run('docker', ['run', '--rm', '--cpus', one('--cpus', '4'), '--memory', one('--memory', '16g'), '--shm-size', '2g',
  '--user', `${uid}:${gid}`, '-e', 'CI=true', '-e', 'HOME=/tmp/home', '-e', 'TZ=America/Vancouver', '-e', 'LANG=C.UTF-8', '-e', 'DATA_UI_TEST_SUMMARY=/out/summary.json',
  '-e', 'npm_config_cache=/tmp/home/.npm', '-e', 'PATH=/opt/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
  '-e', 'FONTCONFIG_FILE=/work/tools/ci/fonts.conf', ...fontMounts(),
  '-v', `${tree}:/work`, '-v', `${out}:/out`, '-v', `${node}:/opt/node:ro`, '-w', '/work', image, 'bash', '-c', inner], { mayFail: true });
const minutes = ((Date.now() - started) / 60000).toFixed(1);
console.log(`\nci-local: exit ${result.status} after ${minutes} min; log and summary in ${out}`);
rmSync(work, { recursive: true, force: true });
process.exit(result.status ?? 1);
