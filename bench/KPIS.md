# data-ui speed KPIs

What `npm run bench` measures, why each number is defined the way it is, and the budget it is held to. The machine
version is `bench/kpi_catalog.json` (Vibe Tracks' `vt-kpi-catalog/1`); this file is the reasoning.

Zach, 2026-10-26: "It's important we are writing code that is fast, particularly as you are loading the data. One
thing here as well is 'first pane' speed: even if the other stuff takes long to load you can do it in a lazy way."
So the headline is the first pane, and every other number either explains it or guards what comes after it.

## The rules every KPI follows

- **Lower is better**, for all of them.
- **Measured by the browser, not by data-ui.** Headless Chromium through Playwright. The numbers come from
  PerformanceObserver (`paint`, `largest-contentful-paint`, `longtask`, `event`), resource timing, CDP's heap metric
  and data-ui's own User Timing marks (`packages/core/src/perf.js`). A mark is a milestone the browser records. A
  number is never computed from data-ui's word alone.
- **"Painted" means the frame after the work, not the work.** `data-views-render` fires when the view's `update()`
  returns, before style, layout and paint. The bench waits for the next presented frame (a task posted from a
  requestAnimationFrame callback). WHY: Codex's review found the old `< 100 ms` checks stopped at `data-views-render`,
  so they flattered the kit.
- **Cold vs warm.**
  - **Cold** is a new browser context: empty HTTP cache, a new renderer process.
  - **Warm** is the same page reloaded in that context: compiled code is warm, and files come back as 304s.
  - Each scenario runs N of each (default 7). Variants of 100,000 rows or more run half as many, and at least 3.
- **Percentiles are nearest-rank p50 / p95.** With 7 loads, p95 is the slowest load, said plainly. Interactions give
  more samples (each scenario does about 25 per run).
- **Per host.** Every point carries the hostname, CPU, Chromium version, viewport (1440×900, DPR 1) and the CPUs the
  run was pinned to (`taskset`, default 8 cores, 4-11). A host that was not measured is null, never 0.
- **Renderer, for WebGL.** The map (MapLibre) draws with WebGL, and headless Chromium's default WebGL is SwiftShader,
  a CPU rasteriser. So a map scenario runs in a browser on the GPU (ANGLE on Vulkan) when that browser really gets a
  hardware renderer, checked by its WebGL renderer string, and on SwiftShader otherwise. Its points carry
  `labels.renderer` (`gpu` or `software`) and `labels.renderer_string`. WHY: a software number read as a GPU one
  would blame the map for the test machine. Map points published before 2026-10-26 were SwiftShader.
- **Trust: the machine, and only the machine.** The machine is shared with other agents. Each scenario records,
  apart from anything the app does:
  - a fixed-work calibration loop in the browser, before and after. It runs in the same browser as the page, so with
    the page's CPU affinity: `trust.browser_cpus` is what the browser's processes had while it ran (they inherit
    `run.mjs`'s `taskset`; anything else is `noisy`);
  - `trust.pressure`: `/proc/stat` per CPU in three windows (0.5 s before the scenario, the whole scenario, 0.5 s
    after), less the CPU time of the bench's own process tree (runner, Playwright's driver, every Chromium process).
    Each window gives the CPUs' worth of other work on the assigned CPUs (`foreign_cpus`, `foreign_share`), how busy
    their SMT siblings outside the set were (`siblings_busy_share`; 4-11's are 16-23, the same physical cores) and the
    whole host's share, for context;
  - the load average, before and after, as context only;
  - `trust.timeline`: the same pressure every 200 ms through the scenario (`[t0, t1, foreign_share,
    siblings_busy_share]`), from a sampler thread, on the clock (`time.monotonic()`) every sample carries as `t0`/`t1`.

  **Each sample is judged by its own time.** A cold load, a warm load or an interaction is not `clean` when any
  200 ms window over it had other work taking over half the assigned CPUs' time, or their SMT siblings over half
  busy; a scroll run is judged frame by frame. Unclean samples carry `pressure` and `interference` and are left out of
  the timing KPIs (bytes, DOM counts and heap still count every load). A timing set (cold loads, warm loads,
  interactions, scroll frames) with fewer clean samples than half, or than two, is suppressed whole (`trust.timing`).
  The scenario-wide windows are then context only; the calibration still judges the whole scenario (over 1.3× this
  host's best ever, `~/.local/share/data-ui-bench/calibration.json`, suppresses every set), since it sees what CPU
  time cannot (memory bandwidth, thermal limits). WHY per sample (judge r2, finding 4, 2026-10-27): one second of full
  saturation in a 20 s scenario averaged to 5 % over the scenario and read quiet, while it could own a p95; and
  interference seen only after the samples suppressed them all. WHY the assigned CPUs (Codex, finding 7): the old
  rule divided the host's load average by the host's 24 CPUs, so eight saturated assigned CPUs (load 8) read as
  quiet, while a build on the other sixteen (load 40) read as noisy though the bench's CPUs were idle.

  Validated on this box, 2026-10-27, with `bench/inject_interference.py` (eight busy loops pinned to 4-11 for 1 s in
  the middle of a 5-run scenario): the samples that overlapped the injection were caught (cold and warm, 2 of 2 in
  each of two runs, none missed). On the loaded box, the samples flagged outside it were 13-40 % slower than the
  clean ones of the same interaction kind, so the flags are interference, not false alarms; and spawning two busy
  children of the bench's own tree does not raise the measured foreign share (median 0.20 with them, 0.25 idle).

  Only a suppressed timing set routes
  a point away from the KPI series (to `kpi_diagnostics.jsonl`; `publish.py --include-noisy` publishes it, drawn
  hollow), and only a point a busy CPU can move: each KPI says so in the catalog's `cpu_sensitive`. Bytes
  (`load_kb`), DOM counts (`dom_added`) and the heap after a forced GC (`heap_mb`) are `false`: the same on a loaded
  machine, so they are always published, labelled `trust: quiet` and `machine: noisy`. WHY: the "1,149 rows in under
  100 ms" check flaked at 122 ms under load 32. A bare number cannot tell the reader that; a trust label can. And
  Vibe Tracks' headline is the newest point whatever its trust, so a noisy timing must not be the headline.
- **Stability: the app's own samples, a result.** A scenario whose cold first paints spread with a CV over 0.5 on a
  quiet machine is `unstable`. That is a finding about the app, never noise: its points are published as measured
  (with `labels.stability: unstable`), and the gate `stable_samples` fails for it. Measured under interference it is
  `pending` (the gate's `pass` is null) whatever the CV: an additive slowdown raises the mean and so lowers the CV
  (`[100, 100, 100, 100, 1000]` is 1.437; add 1,000 ms to each and it is 0.314), so a low CV there certifies nothing.
  WHY (Codex, finding 6, 2026-10-27): the spread used to be one of the `noisy` reasons, so cold paints of 100, 100,
  100, 100 and 1,000 ms on a quiet machine were filed as noise, the real 1,000 ms p95 went to the diagnostics, and
  the old headline stayed. WHY pending under interference (judge r2, finding 3): an earlier version called samples
  that agree on a noisy machine stable, on the wrong premise that interference only widens a spread.
- **Timing validity: a suppressed timing is still a result for this build.** When a scenario's timings are kept out
  of the series, the gate `timing_valid` fails for it and for the whole bench, carrying `labels.code_sha` and
  `labels.why`. WHY (judge r2, finding 3): Vibe Tracks' headline skips null points, so a run whose timings were all
  suppressed left the previous build's fast number as the last word while `no_page_errors` and `stable_samples`
  passed. In `vt brief` a failing `timing_valid` is the next leg: re-measure this build on a quiet machine.

  The rules are pure functions in `bench/trust.py` (`tools/test_bench_stability.py`, `test_bench_timing_valid.py`).
- **Missing is null with a reason** (`labels.why`). A scenario that throws (for example, the 150,000-row rail
  overflow) is a finding, not a zero.

## The KPIs

Each KPI is a p95 over its runs unless the definition column says otherwise.

| Level | id | What | Definition | Budget (target) | Why this budget |
|---|---|---|---|---|---|
| **L0** | `first_paint_ms` | **First useful paint, cold, on robotparts' 1,149 actuators** | navigation start → the frame after `data-ui:first-render` | **1,000 ms** | RAIL: "load in under 1 s" is where a page stops feeling like a wait. Loopback has no network, so this budget is generous on purpose; FCP's "good" is 1.8 s on a real network. |
| L1 | `first_paint_warm_ms` | the same, warm | as above, reloaded | 500 ms | A returning visitor: no download, so only parse and draw are left |
| L1 | `first_paint_worst_ms` | the slowest real scenario's cold first paint | max over real scenarios | 1,000 ms | Catches a chart, map or board regression the table cannot see |
| L1 | `interactive_ms` | time to interactive, cold | end of the last long task before a 500 ms quiet window that starts at or after first paint (Lighthouse's TTI uses 5 s) | 1,500 ms | A reader clicks within a second or two of seeing rows |
| L1 | `blocking_ms` | total blocking time, cold | Σ (long task − 50 ms) between FCP and TTI | 200 ms | Lighthouse's "good" |
| L1 | `interaction_ms` | **interaction latency** | trusted input → the frame after the redraw, on every interaction (below) | **100 ms** | RAIL's response budget. INP's "good" is 200 ms. 100 ms is the existing checks' bar. |
| L1 | `scroll_frame_ms` | scroll frame time on 10,000 rows | rAF interval while scrolling 120 px a frame for 2 s; dropped frames (> 25 ms) beside it | 16.7 ms | 60 frames a second |
| L1 | `load_kb` | bytes on first load | Σ gzip −6 size of every file the cold load fetched (page, core, css, the view bundles actually loaded, `.base`, data); raw bytes in the run too | 200 KB | Codex counted about 149 KB for the actuators; the budget holds it there while views are added |
| L1 | `first_paint_100k_ms` | first paint at 100,000 rows | as L0, on `large-table@100000` | 2,000 ms | Where scaling bites: the 100k model alone took 619 ms in Node (Codex) |
| L2 | `model_ms` | row-model build inside each interaction | Σ `data-ui:model` | (diagnostic) | where `Intl.Collator` caching shows |
| L2 | `render_ms` | model + toolbar + view `update()` inside each interaction | Σ `data-ui:render` | (diagnostic) | `render − model` is the view's own draw: `Intl.NumberFormat` caching and the tbody rebuild |
| L2 | `rail_ms` | the rail's recount inside each interaction | Σ `data-ui:rail` | (diagnostic) | "facet counts on every redraw": a sort or a keystroke recounts today |
| L2 | `heap_mb` | JS heap after load (after a forced GC) | CDP `JSHeapUsedSize`, p50 | (diagnostic) | the 100k model's 74 MiB |
| L2 | `dom_added` | DOM nodes inserted per interaction | MutationObserver, p50 | (diagnostic) | a full tbody rebuild shows here even when the rows did not change |

**The gate `no_page_errors`** (pass/fail, never averaged): every scenario loads, draws and takes its interactions
with no uncaught exception, draws the view its `.base` asks for (no fallback notice, no error box) and, when it has
a rail, draws the rail. The runner checks this on every load and again after the interactions. A scenario that
fails is **FAILED**: the run exits 1, and `publish.py` writes that scenario's KPI points as null with
`labels.verdict: FAILED` and the reason, never as a number. WHY a gate beside the KPIs: at 150,000 rows the rail's `Math.min(...nums)` overflows the
stack. Chromium's spread limit is about 125,000 arguments, lower than Node's, where Codex saw it at 150,000. The rail
then renders empty while the table still paints, so every paint KPI passes. Only a gate says the page is broken.

**The gate `stable_samples`** (pass/fail per scenario, null when pending): the CV of the scenario's cold first useful
paints, at most 0.5, as the Stability rule above says. The whole-bench line is the worst judged CV, `false` when any
scenario is unstable and null when any is pending. It is published whatever the machine, as `no_page_errors` is.

**The gate `timing_valid`** (pass/fail per scenario, null when the scenario FAILED): how many of the scenario's timing
sample sets (cold loads, warm loads, interactions, scroll) were suppressed, which must be 0, as the Timing validity
rule above says. The whole-bench line is the sum, `false` when any scenario's timings were suppressed; it names them
(`labels.suppressed`) and says when the headline scenario was one (`labels.headline`). It is published whatever the
machine, and `--include-noisy` does not pass it: the timings are then in the series, hollow, but still measured
under interference. The gates come in this order in the catalog, which is the order Vibe Tracks reads for its next
leg: a page that throws comes before an unstable app, which comes before a re-measure.

**Scaling** is not a separate KPI: every KPI is also published per scenario, and the synthetic `large-table` runs at
1,000, 10,000, 100,000 and 150,000 rows. The `rows` slice therefore draws each KPI against row count.

**The first-paint chain** is recorded on every load, beside the KPIs: when the core, the `.base`, the data and the
view bundle each arrived, against `data-ui:data`, `data-ui:start` and `data-ui:first-render`. Codex's review found
"the model is computed before the view bundle is even requested". The chain shows that gap on every scenario. It also
shows the fix when it lands: the view bundle's request moves before the model.

### A correctness gate published beside the timings

- **`mesh_first_frame_outline_pct` · 3D first-frame vs thumbnail outline error (%)**, lower is better, gate 3 %. Not a
  bench timing: `npm test` measures it (object-db-shelf's `camera_match`: 10 cards, frame 0 under reduced motion, the
  live silhouette's box against the poster's) and `tools/publish_checks.py` appends the point on every run. The spec is
  docs/CONTRACT.md §29.

## The interactions (all real input unless the scenario's view has no control for it)

| Kind | Input | Ends at |
|---|---|---|
| filter | the rail's checkbox for `interactions.filter` (property = value), ticked then unticked, 3 times | the frame after `data-views-render` (the rail's own redraw is in that frame) |
| sort | the table's column header clicked 4 times (asc, desc, …); `setView({sort})` on a view with no header | same |
| search | each keystroke of `interactions.search`, then select-all + Backspace | same |
| peek | a table row clicked (rows 1, 6 and 13), Escape between; `openPeek(id)` on a non-table view | the frame after `data-views-open` |
| preset | each tab in `interactions.presets`, then back to the first view, twice (the first visit pays the view's lazy bundle) | the frame after `data-views-render` |
| scroll | the view's scroller, 120 px a frame for 2 s | per-frame intervals |

t0 is the input event's own `timeStamp`, not the moment the bench noticed it. A non-real input is labelled in the
run (`how: setView`, `how: openPeek`, `how: el.filters`).

## Prior art used

- **Core Web Vitals / Lighthouse:** FCP, LCP, INP, TBT, TTI. LCP is recorded beside first useful paint, but it is not
  the headline: on a table the largest paint can be a header cell, before any row is readable.
- **RAIL:** the 100 ms response, 16 ms frame and 1 s load budgets.
- **TanStack Table / AG Grid:** they benchmark sort, filter and group over 10k-100k synthetic rows and scroll frame
  time. Those benches time the model in isolation; this bench times input to paint in the real element, and splits
  out the model (`model_ms`) so both readings are available.
