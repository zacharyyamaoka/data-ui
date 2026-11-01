# CI

`.github/workflows/ci.yml` runs the full suite on every push to `main` and every night. `tools/ci-local.mjs` runs the same thing
here, in a container shaped like a GitHub runner, with nothing of this machine in it. That is how a hermetic problem shows
before it costs a CI minute, and the only way to measure flakiness without a remote.

```
node tools/ci-local.mjs --ref main                 # a clean copy of a ref: 4 CPUs, 16 GB, no /archive, no ~/
node tools/ci-local.mjs --tree DIR                 # a public-export mirror (docs/PUBLIC-REPO.md)
node tools/test-all.mjs --strict                   # here, where a suite that did not run is a failure
```

## What is pinned, and why

`tools/ci/versions.env` holds Node, Playwright and uv; `tools/ci/requirements.txt` the Python packages; the workflow's actions are
pinned to full commits. `tools/ci.test.mjs` keeps those together.

- **Node 22.18.0.** `tests/unit/perf-oracle.golden.json`'s rail digest is Node-version specific. V8 13's `**` differs from V8 12's in
  the last bits for 2 of the 24 log-histogram edges (`packages/core/src/facets.js` `histogram`, in `filters-gallery`):
  `88.40608194091345` on Node 22, `88.40608194091347` on Node 24. So the digest is `d5d5e895` on Node 22 and `d311b16f` on Node 24,
  on every run, and it was never intermittent or about ICU. This machine has both: `/usr/bin/node` is 24 and a balena CLI's Node 22
  comes first on some PATHs, so which one a shell found decided the digest. `tools/test-all.mjs` warns off the pin and runs every step
  on the Node it started with. The real fix is to digest those edges rounded, outside this lane's write set.
- **Fonts.** The default sans on a runner is WenQuanYi Zen Hei, wider than this machine's Noto Sans, and a 390 px layout check is
  sensitive to that. `tools/ci/fonts.conf` pins Noto Sans. The overflow it hides on a wider font is listed below.

- **Time zone America/Vancouver.** `gallery/examples/robotparts-calendar/checks.py` finds an event by the local time it draws, so under
  UTC it timed out, and the crash took the 528 checks after it in `tests/browser/checks.py` with it.

## What a run costs

Measured 2026-10-30 with `tools/ci-local.mjs`: 4 CPUs, 16 GB, no cache, Node 22.18.0, Playwright 1.63, with other work on the machine.

| Run | Wall clock | Checks passed | Failed | Skipped parts |
|---|---|---|---|---|
| Clean container, lane on `main` | 37.6 min | 4,691 | 0 | P2, P4 |
| This machine, 24 CPUs, `--strict` | 33.5 min | 5,524 | 0 | None |

The slowest parts are `tests/browser/checks.py` (16 min) and the gallery thumbnails (6 min, cached between runs in CI). Nothing is
flaky so far: three clean-container runs of the same checks failed only on what the fixes above removed. That is few runs, so a flake
may still turn up. A public repository's Actions minutes are free. On a private one a run costs about 45 minutes of a 2,000-minute
free month, so nightly alone is two thirds of it.

## What a run does not cover

`node tools/test-all.mjs --strict` prints these in every summary, and they stay listed on the job's summary page.

| Suite | Why it skips |
|---|---|
| P2 checks | Its numpy oracles read the rack's full-rate logs in `/archive/datasets/bam_rig`, which are private and not in git |
| P4 checks | The same |

Both run on Zach's machine, and `tools/release.mjs` refuses a release that skipped them unless someone names the skip.

Seven single tests also skip themselves, each with its reason in the run's output, because their oracle is a local file:

| Test | Reason it gives |
|---|---|
| `tests/unit/check.test.mjs`: every Bases file in the vault has 0 errors; `tools/test_check_views.py`: the same in Python | The vault is not on this machine |
| `tests/unit/grammar.test.mjs`: the lane's semantics are unchanged; `tools/facets.test.mjs`: rail selections pick the lane's rows | The table lane's `grammar.js` or `actuators.json` is not on disk |
| `tools/test_check_views.py`: two checks over the table lane's built data | The same |
| `tests/unit/rowmodel.test.mjs`: the same rows as the demo's independent lift | `docs/views/demo` or its `node_modules` is absent, on this machine too |

## A red run

- The commit gets a red X, and GitHub mails whoever pushed it.
- The `red-flag` job opens one issue, `CI is red on main`, with the run's link; later red runs comment on it, and a green run closes it.
  A nightly failure nobody was watching for stays visible.
- The job's summary page lists what failed, what was skipped and the slowest suites (`tools/ci-summary.mjs`).
- A failed run keeps its log and the suites' JSON for 14 days.

## Firefox and WebKit

`tools/cross-browser-smoke.py` loads a table, a map and a dashboard from the built site, filters each and opens a record. It has its
own job and never fails the suite: each red line is a finding to read.

Firefox runs headed under Xvfb with Mesa's software GL, because headless Firefox has no WebGL at all and the map needs WebGL2. Without
it the view says so in its own place ("WebGL2 is required to display this map"), and the smoke lists that as its own line.

Measured 2026-10-30 in Playwright 1.63's image on `main` d5ede93: Firefox 14 of 14 steps, WebKit 14 of 14. It is a smoke: it says the
kit works there, not that all of it does. The 4,000 browser checks are Chromium's.
