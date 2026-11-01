# bench: data-ui's speed on real scenarios

`npm run bench` loads data-ui on real data from Zach's apps and times it in headless Chromium. It drives the real
interactions, writes a results JSON, and (with `publish.py`) feeds the `data-ui` track in Vibe Tracks. The KPIs, their
budgets and their reasoning are in [`KPIS.md`](KPIS.md).

```bash
npm --prefix ~/data-ui run bench                                          # every scenario (builds dist/ first)
npm --prefix ~/data-ui run bench -- --scenario robotparts-actuators --runs 3
npm --prefix ~/data-ui run bench -- --scenario large-table@100000,actuator-pivot --no-build
python3 ~/data-ui/bench/publish.py --to ~/vt/zach/producers/data-ui --event "after X"   # latest result → Vibe Tracks
```

- `--runs N`: cold and warm loads per scenario (default 7).
- `--label`: a note stored with the run.
- `--out DIR`: where the results go (default `bench/.out/`, not in git). The run writes `results-<stamp>.json` and
  `latest.json` there.
- `--dist DIR --sha SHA`: measure another build, for example main at a newer commit built in scratch, recorded as that
  commit. `publish.py --sha` labels a result with the data-ui commit it measured.
- **FAILED, never fast.** Each load, and the page after the interactions, is health-checked: no page error, the
  view the `.base` asks for (no fallback, no error box), and a drawn rail when the page has one. A scenario that
  fails makes the run exit 1, and `publish.py` writes its KPI points as null with `labels.verdict: FAILED`.
  WHY: at 150,000 rows on 0dbc3d4 the rail threw and drew nothing while the table painted, so every paint number
  would have passed.
- **Noisy machine vs unstable app** are two verdicts (`bench/trust.py`, [`KPIS.md`](KPIS.md) Trust and Stability). A
  noisy machine (slow calibration, loaded CPUs) keeps a scenario's timings out of the KPI series; its bytes, DOM
  counts and heap are published anyway, and the `timing_valid` gate fails for this build, so the last fast number
  never stands as its result. An app whose own cold paints spread (CV over 0.5) on a quiet machine is published as
  measured and fails the `stable_samples` gate.
- `--no-interactions`, `--headed`: as named.
- Environment:
  - `DATA_UI_PYTHON`: the Python with Playwright (default the psu-atlas venv, as `npm test` uses).
  - `DATA_UI_BENCH_CPUS`: the CPUs to pin to (default `4-11`; `all` to not pin). The browser inherits the pinning,
    and the trust verdict judges these CPUs and their SMT siblings (`trust.pressure` in the results), not the host's
    load average. So a lane that runs `npm test` beside a bench should pin away from both: 4-11's siblings are 16-23,
    and `taskset -c 12-19` shares cores 4-7 with the bench.
- The runner serves `dist/` and the scenarios from a server inside its own process, and stops that server and its
  browser before it exits.

## The live tier: `bench/live.py`

Its own script (docs/peps/0012-live-data.md §8, §9): a live dashboard of M uPlot plot panels over synthetic streams
(bench/live/driver.js makes every row in the page), measured in headless Chromium on the GPU when the box has one
(software otherwise; each result names its renderer). No Vibe Tracks publishing from here.

```bash
~/psu-atlas/.venv/bin/python ~/data-ui/bench/live.py                 # short, about 4 minutes
~/psu-atlas/.venv/bin/python ~/data-ui/bench/live.py --mode long     # + 10 minutes into the 256 MB buffer
```

- **sweep**: frame time while streaming N samples/s into M panels (5 streams each), M × rate in (1, 4, 12) × (100 Hz,
  1 kHz); 12 × 1 kHz is Rerun's published load, 60,000 samples a second.
- **ingest to pixel** p50 / p95: a batch's append to the frame that shows its newest sample (rAF, then a task).
- **scrub** and **back to live**: `clock.seek(t)` / `clock.goLive()` to every plot drawn and painted.
- **heap** after a GC with the buffer at its cap (64 MB short, 256 MB for 10 minutes long), beside the buffer's own byte
  count (typed arrays live outside the JS heap).
- **first paint**: navigation to the dashboard ready, plus the first rows to their plot painted.
- **engines**: the coordinator's decided bench (2026-10-27): the same min/max columns of a 60 kHz window pushed into
  uPlot and into Vega (the timeseries card's View), frame by frame.
Output: `bench/.out/live-<stamp>.json` and `live-latest.json`; a run is `noisy` by runner.py's rules (calibration over
1.3× this host's best, or load per CPU over 1.0), kept and labelled.

## Scenarios

One folder each in `scenarios/<id>/`: `views.base`, the data copied from the app (frozen, so the bench never drifts
when the gallery changes), `scenario.json` (rows, provenance with sha256, and the interactions to drive) and a README.
The page is a bare host: the kit's css and js, a `<data-facets>` rail when the `.base` has `facets:`, and the
`<data-views>`, as robotparts' part page ships it.

| id | app | rows | views | what it stresses |
|---|---|---|---|---|
| `robotparts-actuators` | robotparts | 1,149 | grouped table, pivot | **the headline**: rich cells, 48 brand groups, nine facets |
| `robotparts-catalog` | robotparts | 2,068 | table, grouped | the part catalog |
| `object-database` | object database | 2,196 | table, cards (2,196 thumbnails) | images |
| `vibetracks-runs` | Vibe Tracks | 700 | table, pivot, chart | real producer runs |
| `vibetracks-kpis` | Vibe Tracks | 161 | KPI cards, chart | the KPI view |
| `vibetracks-board` | Vibe Tracks | 76 | kanban | the board |
| `rack-model-runs` | robotparts models | 623 | KPI, leaderboard table, pivot, chart | 15 presets on one dataset |
| `actuator-charts` | robotparts | 1,149 | Ashby charts | Vega (the 850 KB bundle) |
| `actuator-pivot` | robotparts | 1,149 | pivot | the pivot |
| `robotparts-photos` | robotparts | 175 | cards with photos | the media grid |
| `robotparts-timeline` | robotparts | 30 | timeline | vis-timeline |
| `robotparts-sellers-map` | robotparts | 322 | map | MapLibre |
| `systemsketch-blocks` | SystemSketch | 8 | graph | React Flow |
| `robotparts-calendar` | robotparts | 172 | calendar | EventCalendar |
| `large-table@N` | synthetic | 1k, 10k, 100k, 150k | table, grouped, pivot | scaling (sampled from the real actuators; `generate.py`, seeded) |

Not covered yet: `<data-dashboard>`, which is on `lane/dashboards` and not merged. Add a scenario when it lands.

## What data-ui itself contributes

Three marks and three measures in the browser's timeline (`packages/core/src/perf.js`, tested in
`tests/unit/perf.test.mjs`):

- **Marks:**
  - `data-ui:data`: the data was fetched and parsed.
  - `data-ui:start`: the toolbar is in the DOM.
  - `data-ui:first-render`: the first view has drawn.
- **Measures:**
  - `data-ui:model`: one row-model build.
  - `data-ui:render`: model, toolbar and the view's `update()`.
  - `data-ui:rail`: one rail count-and-draw.

They cost a few microseconds and show in DevTools' Performance panel, so the same names work when profiling by hand.

## Files

- `run.mjs`: npm's entry point. It builds `dist/`, then runs the runner pinned to the bench's CPUs.
- `runner.py`: the bench.
- `harness.js`: the in-page listener, injected before the page's own scripts.
- `publish.py`: turns a results file into Vibe Tracks producer files (`vt-kpi/1`).
- `trust.py`: the machine (trust) and app (stability) verdicts, as pure functions both scripts share, and the
  200 ms pressure sampler each sample is judged against.
- `inject_interference.py`: deliberate interference (busy loops pinned to the bench's CPUs) and a `check` that says
  which samples the bench caught; how the trust thresholds are validated.
- `kpi_catalog.json`: the KPI definitions.
- `KPIS.md`: the reasoning behind the KPIs.
- `scenarios/`: the scenario folders described above.
