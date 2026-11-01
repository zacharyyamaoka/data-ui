// Before a release: each app's main journey against a candidate data-ui build. data-ui's own suite cannot see what an app
// relies on, so until now an app's first test of a change was its next upgrade.
//
//   node tools/app-journeys.mjs --ref main [--only robotparts,vibetracks] [--out DIR] [--own-kit] [--repo DIR] [--node-modules DIR]
//
// For each app (robotparts, RobotDx, sim2real, Vibe Tracks, ObjectDB):
// 1. a temporary copy of the app at its HEAD (`git archive`), so the app's checkout, branches and running servers are
//    never touched; `git status` and HEAD are compared before and after, and a change is a failure of its own;
// 2. the candidate kit in that copy's vendor folder, built by tools/vendor.mjs the way that app vendors it;
// 3. the app's OWN journey, on free ports. Nothing here reimplements a check: when an app changes its journey, this runs it.
// Read-only data an app has generated (robotparts' site, sim2real's app/data, ObjectDB's export) is linked or copied in.
// --own-kit keeps the kit the app already has, so a red journey can be told from an app that was already red.
//
// A verdict per app:
// - pass: the app's journey ran, with checks in its output, and every one passed on the candidate.
// - fail: the candidate broke something. A red step runs again on the app's own kit, and a failure only there too is not
//   the candidate's: only a failure the app's own kit does not have makes a fail.
// - app-red: the journey is red on the app's own kit as well, and the candidate adds nothing to it. Not a pass: the app has
//   a problem to look at, and for now that journey protects nothing it already fails on.
// - missing: the journey could not run or ran nothing: no built site, no Playwright, a test that printed SKIP and exited 0,
//   an output with no checks in it. Never a pass.
// Exit status: 0 all pass, 1 any fail, 3 no fail but something app-red or missing. DATA_UI_JOURNEYS_SUMMARY=FILE writes the JSON.
import { spawn, spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { vendor } from './vendor.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const HOME = homedir();
const PLAYWRIGHT_PY = process.env.DATA_UI_PYTHON || join(HOME, 'psu-atlas/.venv/bin/python');
const PLAYWRIGHT_NODE = process.env.DATA_UI_PLAYWRIGHT_NODE || join(HOME, 'aruco-studio/web/node_modules/playwright');
const UV = join(HOME, '.local/bin/uv');
const SYSTEM_NODE = '/usr/bin/node';
const countLines = (re) => (text) => (text.match(re) || []).length;
const PASS_LINES = countLines(/^(PASS|ok)\b/gm);

const freePort = () => new Promise((done, fail) => {
  const s = createServer();
  s.on('error', fail);
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => done(port)); });
});

const git = (repo, ...args) => {
  const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', maxBuffer: 1 << 30 });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr}`);
  return r.stdout;
};

/** The app's HEAD in `tree`. */
function copyApp(repo, tree) {
  mkdirSync(tree, { recursive: true });
  const archive = spawnSync('git', ['-C', repo, 'archive', '--format=tar', 'HEAD'], { maxBuffer: 2 ** 32 });
  if (archive.status !== 0) throw new Error(`git archive ${repo}: ${archive.stderr}`);
  const untar = spawnSync('tar', ['-x', '-C', tree], { input: archive.stdout, maxBuffer: 2 ** 32 });
  if (untar.status !== 0) throw new Error(`tar: ${untar.stderr}`);
}

/** `site` with `from`'s entries linked in, and static/data-ui the kit in `kit`: a 1.8 GB site, one folder replaced. */
function overlaySite(from, site, kit) {
  mkdirSync(join(site, 'static'), { recursive: true });
  for (const name of readdirSync(from)) if (name !== 'static') symlinkSync(join(from, name), join(site, name));
  for (const name of readdirSync(join(from, 'static'))) if (name !== 'data-ui') symlinkSync(join(from, 'static', name), join(site, 'static', name));
  cpSync(kit, join(site, 'static', 'data-ui'), { recursive: true, filter: (p) => !p.endsWith('/python') });
}

const hasPlaywrightPython = () => existsSync(PLAYWRIGHT_PY) && spawnSync(PLAYWRIGHT_PY, ['-c', 'import playwright'], { stdio: 'ignore' }).status === 0;

/** sim2real's generated gates.json: the checkout's, else a worktree's. WHY: a rebuild in progress leaves the checkout's app/data
    half-written, and the journey only reads it. */
function sim2realData() {
  const lanes = join(HOME, 'sim2real-worktrees');
  const roots = [join(HOME, 'sim2real'), ...(existsSync(lanes) ? readdirSync(lanes).map((name) => join(lanes, name)) : [])];
  return roots.map((root) => join(root, 'app/data/one-dof-test-rack/gates.json')).find(existsSync) || null;
}

/** What each app is. `needs`: what must exist for the journey to mean anything; [path, why]. `steps(ctx)`: its own checks. */
export const APPS = [
  {
    app: 'robotparts',
    repo: join(HOME, 'robotparts'),
    into: 'site/static/data-ui',
    vendor: {},
    needs: () => [[join(HOME, 'robotparts/dist/site/index.html'), 'the built site (python3 build/all.py in robotparts)'],
      [PLAYWRIGHT_PY, 'a Python with Playwright (DATA_UI_PYTHON)']],
    steps: ({ tree, tmp, kitDir }) => {
      const site = join(tmp, 'site');
      overlaySite(join(HOME, 'robotparts/dist/site'), site, kitDir);
      const env = { ROBOTPARTS_SITE: site };
      return [
        { name: 'test_data_ui (the vendored kit, the pages on it)', cmd: 'python3', args: ['-m', 'unittest', 'discover', '-s', 'tests/site', '-t', 'tests/site', '-p', 'test_data_ui.py'], env, minutes: 10,
          count: (text) => Number((/^Ran (\d+) tests?/m.exec(text) || [])[1] || 0) },
        { name: 'browser_check (filter, presets, peek, every page type)', cmd: PLAYWRIGHT_PY, args: ['tests/site/browser_check.py', '--site', site, '--shots', join(tmp, 'shots')], minutes: 20,
          count: countLines(/^\s*"status": \d+,?$/gm) }, // it prints one JSON summary: a page visited has a status
      ];
    },
  },
  {
    app: 'robotdx',
    repo: join(HOME, 'io-diagnostics'),
    into: 'io_diagnostics/web/vendor/data-ui',
    vendor: { views: ['table', 'list', 'cards', 'kpi', 'live', 'playback', 'record', 'chart', 'media'], without: ['python/', 'analysis.js', 'sources.js', 'views/mesh.js'] },
    needs: () => [[PLAYWRIGHT_NODE, 'Playwright for Node (DATA_UI_PLAYWRIGHT_NODE)'], ['/usr/bin/google-chrome', 'Chrome, which the harness drives'], [UV, 'uv, which starts the fixture host']],
    // WHY: the Settings page fetches VERSION, and a 404 is a failed check; goes when docs/migrations/vendor-io-diagnostics.md lands
    adapt: ({ into, record }) => writeFileSync(join(into, 'VERSION'), `data-ui ${record.version}\nref       ${record.ref}\ncommit    ${record.commit}\n`),
    steps: () => [
      { name: 'test_dx_page (explorer, live, rewind, dashboards, rail, requests)', cmd: SYSTEM_NODE, args: ['tests/test_dx_page.js'], env: { IO_DIAG_PLAYWRIGHT: PLAYWRIGHT_NODE }, minutes: 25,
        count: (text) => Number((/^(\d+)\/\d+ checks passed/m.exec(text) || [])[1] || 0) },
    ],
  },
  {
    app: 'sim2real',
    repo: join(HOME, 'sim2real'),
    into: 'vendor/data-ui',
    vendor: { kitDir: 'dist', also: ['gallery/robotics/CONTRACT.md', 'gallery/robotics/schemas', 'gallery/robotics/fixture.py', 'gallery/robotics/fixtures/difference',
      'gallery/examples/sim-to-real/samples.json=gallery/sim-to-real/samples.json', 'gallery/examples/sim-to-real/media.json=gallery/sim-to-real/media.json',
      'gallery/examples/sim-to-real/media=gallery/sim-to-real/media', 'gallery/examples/sim-to-real/motors.json=gallery/sim-to-real/motors.json',
      'gallery/examples/sim-to-real/README.md=gallery/sim-to-real/README.md', 'gallery/examples/pid-tuning/media/ur5e_links.glb=gallery/pid-tuning/media/ur5e_links.glb'] },
    // its kit is gitignored, so --own-kit takes it from the checkout
    ownKit: join(HOME, 'sim2real/vendor/data-ui'),
    needs: () => [[sim2realData() || join(HOME, 'sim2real/app/data/one-dof-test-rack/gates.json'), "the app's generated data, gates.json included (tools/build_app.py in sim2real)"], [UV, 'uv, which provides Playwright']],
    steps: ({ tree }) => {
      symlinkSync(dirname(dirname(sim2realData())), join(tree, 'app/data'));
      return [{ name: 'test_app_flow (deployments, runs, a run, playback, gates)', cmd: UV, args: ['run', '--no-project', '--with', 'playwright', 'python', 'app/tests/test_app_flow.py'], minutes: 20 }];
    },
  },
  {
    app: 'vibetracks',
    repo: join(HOME, 'vibetracks'),
    into: 'vibetracks/home/static/vendor/data-ui',
    vendor: { withoutViews: ['map'] },
    needs: () => [[join(PLAYWRIGHT_NODE, 'index.mjs'), 'Playwright for Node (DATA_UI_PLAYWRIGHT_NODE); without it the journey prints SKIP and exits 0']],
    steps: ({ port }) => [
      { name: 'test_dataui_contract (the .base files mean what the app relies on)', cmd: 'python3', args: ['-m', 'unittest', 'tests.test_dataui_contract'], minutes: 5,
        count: (text) => Number((/^Ran (\d+) tests?/m.exec(text) || [])[1] || 0) },
      { name: 'track_kpis_dataui (the track page against an independent oracle)', cmd: SYSTEM_NODE, args: ['tests/browser/track_kpis_dataui.mjs'],
        env: { VT_PORT: String(port), VT_PLAYWRIGHT: join(PLAYWRIGHT_NODE, 'index.mjs') }, minutes: 15,
        count: (text) => Number((/(\d+) checks?/.exec(text) || [])[1] || 0) },
    ],
  },
  {
    app: 'objectdb',
    repo: join(HOME, 'object-database'),
    into: 'vendor/data-ui',
    vendor: { without: ['python/'] },
    needs: () => [[join(HOME, '.cache/object-database/site/index.html'), "ObjectDB's built site (site/build.py), the export this journey starts from"],
      [join(HOME, 'bam-waste-objects'), 'the library'], [PLAYWRIGHT_PY, 'a Python with Playwright (DATA_UI_PYTHON)'], [UV, 'uv, which runs the site']],
    steps: ({ tree, tmp, port }) => {
      const out = join(tmp, 'site');
      // a copy, not a link: serve.py rewrites the pages when the kit it publishes changed
      cpSync(join(HOME, '.cache/object-database/site'), out, { recursive: true });
      return [
        { name: 'serve the site on the candidate', serve: { cmd: UV, args: ['run', '--project', tree, '--extra', 'build', 'python', 'site/serve.py', '--out', out, '--port', String(port)], url: `http://127.0.0.1:${port}/`, minutes: 10 } },
        { name: 'browser_check (every claim the site makes)', cmd: PLAYWRIGHT_PY, args: ['site/browser_check.py', '--base', `http://127.0.0.1:${port}`, '--out', out, '--shots', join(tmp, 'shots')], minutes: 20 },
        { name: 'collection_check (the home page, data-ui\'s grouped gallery)', cmd: PLAYWRIGHT_PY, args: ['site/collection_check.py', '--base', `http://127.0.0.1:${port}`, '--out', out], minutes: 15 },
      ];
    },
  },
];

const tail = (text, n = 12) => text.split('\n').filter((l) => l.trim()).slice(-n).join('\n');

/** The named failures in a step's output, numbers out, so the same failure reads the same on two runs. */
export const failLines = (text) => [...new Set(text.split('\n').filter((l) => /^\s*(FAIL|not ok|ERROR)\b/.test(l))
  .map((l) => l.trim().replace(/\[.*$/, '').replace(/\d+(\.\d+)?/g, '#').replace(/\s+/g, ' ').trim().slice(0, 140)))];

/** Run one step, its whole output in `log`; {status, seconds, checks, why, failures}. */
function runStep(step, { tree, log }) {
  const started = Date.now();
  const env = { ...process.env, ...step.env };
  delete env.VIRTUAL_ENV;
  // WHY coreutils' timeout: it gives the step its own process group and ends all of it. spawnSync's own timeout ends only the
  // direct child, and a journey's server lived on after the first hang (2026-10-30, a robotparts http.server, two hours).
  const limit = `${Math.ceil((step.minutes || 20) * 60)}s`;
  const r = spawnSync('timeout', ['--kill-after=15s', limit, step.cmd, ...step.args], { cwd: tree, env, encoding: 'utf8', maxBuffer: 1 << 30 });
  const text = `${r.stdout || ''}\n${r.stderr || ''}`;
  writeFileSync(log, text);
  const seconds = Math.round((Date.now() - started) / 1000);
  const checks = (step.count || PASS_LINES)(text);
  if (r.status === 124 || r.status === 137) return { status: 'fail', seconds, checks, why: `timed out after ${step.minutes} min` };
  if (r.status !== 0) return { status: 'fail', seconds, checks, why: `exit ${r.status}: ${tail(text, 6)}`, failures: failLines(text) };
  if (/^SKIP\b/m.test(r.stdout || '') && !checks) return { status: 'missing', seconds, checks, why: `it skipped itself: ${tail(r.stdout, 2)}` };
  if (!checks) return { status: 'missing', seconds, checks, why: `exit 0 with no checks in its output: ${tail(text, 3)}` };
  return { status: 'pass', seconds, checks };
}

async function startServer(serve, { tree, log }) {
  const env = { ...process.env };
  delete env.VIRTUAL_ENV;
  const out = [];
  const child = spawn(serve.cmd, serve.args, { cwd: tree, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.on('data', (b) => out.push(b));
  child.stderr.on('data', (b) => out.push(b));
  const deadline = Date.now() + (serve.minutes || 10) * 60000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) break;
    const ok = await fetch(serve.url).then((r) => r.ok).catch(() => false);
    if (ok) return child;
    await new Promise((done) => setTimeout(done, 1000));
  }
  writeFileSync(log, Buffer.concat(out));
  stop(child);
  throw new Error(`the server did not answer at ${serve.url}: ${tail(Buffer.concat(out).toString(), 6)}`);
}

// WHY the process group: `uv run` starts the server as a child; this journey's own process, recorded here, is the only one stopped
const stop = (child) => { try { process.kill(-child.pid, 'SIGTERM'); } catch { /* gone */ } };

/** One app on one kit: the candidate, or with `ownKit` the one it has. */
async function runApp(spec, { ref, repo, where, ownKit, nodeModules }) {
  mkdirSync(where, { recursive: true });
  const result = { app: spec.app, status: 'pass', steps: [] };
  const unmet = spec.needs().filter(([path]) => !existsSync(path));
  if (unmet.length || !existsSync(join(spec.repo, '.git'))) {
    return { ...result, status: 'missing', why: unmet.length ? unmet.map(([, why]) => `needs ${why}`).join('; ') : `no repository at ${spec.repo}` };
  }
  if (spec.needs().some(([path]) => path === PLAYWRIGHT_PY) && !hasPlaywrightPython()) return { ...result, status: 'missing', why: `${PLAYWRIGHT_PY} has no Playwright` };
  const tmp = mkdtempSync(join(tmpdir(), `journey-${spec.app}-`));
  const tree = join(tmp, 'app');
  const servers = [];
  const before = [git(spec.repo, 'rev-parse', 'HEAD'), git(spec.repo, 'status', '--porcelain')];
  try {
    copyApp(spec.repo, tree);
    let kitDir = join(tree, spec.into);
    if (!ownKit) {
      const into = join(tree, spec.into);
      const record = vendor({ repo, wanted: ref, into, modules: nodeModules, ...spec.vendor, log: (line) => { result.kit = line.replace(/ -> .*/, ''); } });
      if (spec.adapt) spec.adapt({ into, record });
      if (spec.vendor.kitDir) kitDir = join(into, spec.vendor.kitDir);
    } else if (spec.ownKit) {
      cpSync(spec.ownKit, join(tree, spec.into), { recursive: true });
      if (spec.vendor.kitDir) kitDir = join(tree, spec.into, spec.vendor.kitDir);
    }
    const port = await freePort();
    for (const [i, step] of spec.steps({ tree, tmp, port, kitDir }).entries()) {
      const log = join(where, `${i + 1}.log`);
      if (step.serve) {
        try { servers.push(await startServer(step.serve, { tree, log })); } catch (e) { result.steps.push({ name: step.name, status: 'fail', why: e.message }); result.status = 'fail'; break; }
        continue;
      }
      console.log(`  ${spec.app}: ${step.name}`);
      const done = { name: step.name, log, ...runStep(step, { tree, log }) };
      result.steps.push(done);
      console.log(`  ${spec.app}: ${done.status} in ${done.seconds} s, ${done.checks} checks${done.why ? `: ${done.why.split('\n')[0]}` : ''}`);
      if (done.status !== 'pass' && result.status === 'pass') result.status = done.status;
      else if (done.status === 'fail') result.status = 'fail';
    }
  } catch (e) {
    result.status = 'fail';
    result.why = e.message;
  } finally {
    servers.forEach(stop);
    rmSync(tmp, { recursive: true, force: true });
  }
  const after = [git(spec.repo, 'rev-parse', 'HEAD'), git(spec.repo, 'status', '--porcelain')];
  if (before[0] !== after[0]) result.note = `the app's HEAD moved during the run (${before[0].slice(0, 7)} -> ${after[0].slice(0, 7)}): a peer, or this tool`;
  else if (before[1] !== after[1]) result.note = `the app's working tree changed during the run: a peer, or this tool (git status differs)`;
  return result;
}

/** One app's verdict. A red run is run again on the app's own kit, so a red that was already there is not called the candidate's. */
export async function journey(spec, { ref, repo, out, ownKit, nodeModules }) {
  const result = await runApp(spec, { ref, repo, where: join(out, spec.app), ownKit, nodeModules });
  if (result.status !== 'fail' || ownKit || !result.steps.length) return result;
  console.log(`  ${spec.app}: red on the candidate; the same journey on the app's own kit, to tell whose red it is`);
  const own = await runApp(spec, { ref, repo, where: join(out, `${spec.app}-own-kit`), ownKit: true, nodeModules });
  result.own_kit = own.status;
  for (const step of result.steps.filter((s) => s.status === 'fail')) {
    const theirs = own.steps.find((s) => s.name === step.name);
    if (!theirs || theirs.status !== 'fail') continue;
    step.new_failures = (step.failures || []).filter((f) => !(theirs.failures || []).includes(f));
    if (!step.new_failures.length) { step.status = 'app-red'; step.why = `red on the app's own kit too (${(theirs.failures || []).length} failures), nothing new on the candidate: ${(step.failures || []).slice(0, 3).join(' / ')}`; }
  }
  if (!result.steps.some((s) => s.status === 'fail')) result.status = 'app-red';
  return result;
}

async function main(args) {
  const value = (flag) => { const i = args.indexOf(flag); return i >= 0 ? args[i + 1] : undefined; };
  const ref = value('--ref') || 'HEAD';
  const repo = resolve(value('--repo') || ROOT);
  const only = value('--only') ? value('--only').split(',') : null;
  const out = resolve(value('--out') || mkdtempSync(join(tmpdir(), 'data-ui-journeys-')));
  const ownKit = args.includes('--own-kit');
  const unknown = (only || []).filter((name) => !APPS.some((a) => a.app === name));
  if (unknown.length) { console.error(`no app ${unknown.join(', ')}; there are ${APPS.map((a) => a.app).join(', ')}`); process.exit(2); }
  const apps = [];
  console.log(`app journeys: ${ownKit ? "each app's own kit" : `data-ui ${ref} (${git(repo, 'rev-parse', '--short', `${ref}^{commit}`).trim()})`}; logs in ${out}`);
  for (const spec of APPS) {
    if (only && !only.includes(spec.app)) continue;
    console.log(`\n== ${spec.app}`);
    apps.push(await journey(spec, { ref, repo, out, ownKit, nodeModules: value('--node-modules') }));
  }
  console.log('\n== summary');
  for (const a of apps) {
    const checks = a.steps.reduce((n, s) => n + (s.checks || 0), 0);
    console.log(`${a.status.padEnd(8)}${a.app}: ${checks} checks${a.why ? `, ${a.why}` : ''}${a.note ? ` (${a.note})` : ''}`);
    for (const s of a.steps.filter((x) => x.status !== 'pass')) console.log(`        ${s.name}: ${s.status}: ${(s.why || '').split('\n').slice(0, 4).join(' / ')}`);
  }
  const summary = { ref, own_kit: ownKit, apps };
  writeFileSync(join(out, 'summary.json'), `${JSON.stringify(summary, null, 1)}\n`);
  if (process.env.DATA_UI_JOURNEYS_SUMMARY) writeFileSync(process.env.DATA_UI_JOURNEYS_SUMMARY, `${JSON.stringify(summary, null, 1)}\n`);
  process.exitCode = apps.some((a) => a.status === 'fail') ? 1 : apps.some((a) => a.status !== 'pass') ? 3 : 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) await main(process.argv.slice(2));
