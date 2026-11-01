// npm run bench [-- --scenario X[,Y] --runs N --label "…" --no-build]: build dist/, then the scenario bench
// (bench/runner.py) in headless Chromium through Playwright's Python, pinned to a fixed set of CPUs.
//   DATA_UI_PYTHON     the Python with Playwright (default the psu-atlas venv, as npm test uses)
//   DATA_UI_BENCH_CPUS the CPUs it may run on (default 4-11: eight cores, a mid laptop's worth; `taskset` syntax;
//                      "all" to not pin). WHY pin: a fixed budget of cores, so a run is comparable to the last one even
//                      while other agents' builds come and go on the rest of the machine.
// Publishing the result to Vibe Tracks is a separate step: bench/publish.py (bench/README.md).
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PY = process.env.DATA_UI_PYTHON || '~/psu-atlas/.venv/bin/python';
const CPUS = process.env.DATA_UI_BENCH_CPUS || '4-11';
const args = process.argv.slice(2);
const noBuild = args.includes('--no-build');
const pass = args.filter((a) => a !== '--no-build');

if (!existsSync(PY)) { console.error(`no Playwright Python at ${PY} (set DATA_UI_PYTHON)`); process.exit(2); }
if (!noBuild) {
  const b = spawnSync('node', ['build.mjs'], { cwd: ROOT, stdio: 'inherit' });
  if (b.status !== 0) process.exit(b.status ?? 1);
}
const pin = CPUS !== 'all' && existsSync('/usr/bin/taskset');
const [cmd, argv] = pin ? ['/usr/bin/taskset', ['-c', CPUS, PY, 'bench/runner.py', ...pass]] : [PY, ['bench/runner.py', ...pass]];
const r = spawnSync(cmd, argv, { cwd: ROOT, stdio: 'inherit' });
process.exitCode = r.status ?? 1;
