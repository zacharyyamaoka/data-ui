# PEP 0012: live data and rewind

- **Status:** proposed 2026-10-27 on `lane/live` (not merged). The CONTRACT amendment is §26 (drafted as §21; §20-§25,
  §27 and §29-§31 were taken on main or in this merge first). Renumbered PEP 0012 at merge (drafted as PEP 0008, which
  lane/dashboard-cards' one-clock-driver record also took; 0010 and 0011 are claimed by lane/robotics-plan and lane/map). Builds on PEP 0004
  (dashboards) and PEP 0005 (cards and the one clock), both merged into `lane/live`.
- **Asked by:** Zach, 2026-10-26, for RobotDx: "reimplement robotdx using data-ui … One big difference here is that it is
  LIVE data … with foxglove you can do playback (which is like the static dataset) or you can do streaming. actually I
  really like rerun.. you kinda do streaming but at any moment you can just kinda like 'rewind' and just go back in time
  … (rewind) I would say is my primary prior art reference. Things to think about here are performance."
- **Read for this:** the prior-art note (vault: *C - Live data with rewind (prior art)*; report
  `io-diagnostics/reports/live-data-prior-art-2026-10-27.html`), RobotDx's inventory (io-diagnostics `lane/robotdx-data-ui`,
  `docs/peps/0001-robotdx-on-data-ui.md` §5a, §5b, §8), data-ui's clock (`packages/core/src/clock.js`) and playback card.

## 1. The answer

- **A live dataset is a dataset that is still growing.** The same views draw it; there is no "live table" or "live
  chart" type. A view draws the dataset **as of the clock's time t**: a table the rows up to t, a KPI the newest value
  at t, a plot the window ending at t. A finished recording is the same object with its end fixed (`recorded: true`).
- **Rerun's clock.** The one clock (PEP 0005) gains a second state: **following** (t is pinned to the newest data) or
  **paused at t**. Any scrub, step, seek or loop leaves following; one control goes back ("● LIVE", End,
  Ctrl/Cmd+Shift+→); Space never jumps to live. While paused, data keeps arriving underneath and the clock shows how
  far behind it is.
- **Memory is a ring with a byte budget.** 256 MB per page by default. The oldest data goes first; the newest chunk of
  every stream and the newest version of every record always stay.
- **At most one draw per view per animation frame, and none when nothing it shows changed.** Rows arrive at any rate;
  views draw on the next frame. A paused view does not redraw because data arrived after its t: only a row or version
  at or before t (a late one), or retention taking something it shows, can change it (§8).
- **Hosts feed it three ways:** push rows from JavaScript (`dataset.append(rows)`, `dataset.upsert(rows)`), a
  server-sent-events URL (the browser resumes with `Last-Event-ID`), or a polling URL. data-ui never writes to a host.

### Decided (coordinator, 2026-10-27, taking the prior-art note's defaults)

1. **uPlot draws the live time series** (`type: plot`, §6.2), after a Vega-vs-uPlot bench at 60 kHz (numbers in §9).
   Every other chart stays Vega-Lite. This is the second chart engine PEP 0005 §7 ruled out, allowed for dense live
   signals only, as React Flow is allowed for graphs.
2. **The browser buffer defaults to 256 MB per page**, set by `retention:` in the `.base` (top level for the page,
   per dataset for that dataset) or `setLiveBudget(bytes)` in JavaScript.
3. **A replay that catches up with the newest data rejoins live.** Rerun stops at the end; we follow, because
   "rewind, then carry on" is the mental model asked for.

## 2. Words used here

| Word | Means |
|---|---|
| **t** | the clock's time, in seconds on the producer's clock (Unix seconds for a host such as RobotDx) |
| **end** / **start** | the newest / oldest time any live dataset on the clock holds |
| **following** | the clock's t is pinned to end and moves with it |
| **lag** | end − t, shown as "−12.4 s" when paused |
| **append dataset** | rows that grow with time: samples, events, level changes |
| **keyed dataset** | rows replaced by a key (`key:`): a tree, checks, configuration. Each replacement is a **version** at a time |
| **stream** | the rows of an append dataset that share a value of its `stream:` property (one joint, one signal) |
| **chunk** | up to 4,096 rows of one stream in time order, kept as typed arrays (one per column) |
| **snapshot** | the rows a row-reading view gets at t (§5) |
| **tail** | a table or list following the newest rows, which pauses while you scroll or open a row (§5.3) |

## 3. The data model

**One class, two kinds.** `LiveDataset` (`packages/core/src/live/store.js`) is an append dataset unless it has a
`key:`, then it is keyed.

- **Append.** Each stream holds sealed chunks and one open chunk. A chunk seals at 4,096 rows (Rerun's compaction
  threshold) or once it spans 10 s, so a slow stream still seals and `age` retention is exact to 10 s; sealing trims
  its arrays to the rows they hold. (The prior-art note said 250 ms of wall time; at 1 Hz that is a chunk per row.) Numbers are `Float64Array` (a missing number is `NaN` inside, `null` when read); everything else is a plain
  array. Rows must arrive in time order per stream: a row older than its stream's sealed history is dropped and
  counted (`dataset.late`); a row older than the open chunk's newest is placed in order.
- **Keyed.** Each key holds its versions in time order; `remove(keys)` writes a removal version. The record at t is its
  newest version at or before t, unless that version is a removal.
- **Time.** `time:` names the time property. A row without one gets its arrival time (`Date.now() / 1000`), which is
  Foxglove's rule for live data. The axis is the producer's clock, never the page's (RobotDx PEP 0001 §5c8).
- **Two questions answer every view** (Rerun's query model): `latestAt(t)` (per stream, or per key) and `range(a, b)`
  (chunk slices, no copy). Row objects are made only for the rows a view reads, and kept per chunk while it lives.
- **A row's id** is its own `id`, else its key (keyed), else its arrival number (append), as text.

**Retention.** A page-wide budget (default 256 MB) and optional per-dataset caps (`bytes`, `age`). Over a cap the
store drops the oldest sealed chunk of any live dataset, then the next. It never drops the newest chunk of a stream or
the newest version of a key (Rerun's `protect_latest`), and it skips chunks under a paused clock's view (the 60 s
before t) while any other chunk can go: the budget wins only when nothing else is left. Typed arrays are counted
exactly; text and objects by estimate (2 bytes a character, 16 per value, 64 per row object).

## 4. The clock: following, paused, replaying

`LiveClock` (`packages/core/src/live/clock.js`) extends PEP 0005's `Clock`; a dashboard makes one whenever it has a
live dataset. With no live dataset bound it behaves exactly as `Clock`. **`clock.js` itself changes in one place:**
`fmtTime(t)` writes a wall-clock time (`14:03:21.40`) for t ≥ 10⁹ s, where it used to write `28333333:20.00`.

| Event | Result |
|---|---|
| A live dataset is bound (page opens) | following: t = end on every arrival |
| Scrub, step (←/→), click a time in a plot, Home, a loop range (`[`, `]`, the range lane), typing a time, `#t=<number>` | paused at t; data keeps arriving. A scrub that starts while following ends paused, even on a card that resumes play after a drag |
| Zoom or pan a plot (`clock.window`) | no change: following stays following (Rerun 0.40) |
| Space while following | pause at t (never jumps) |
| Space while paused | replay from t at the speed; reaching end rejoins following (decided, §1) |
| ● LIVE, End, Ctrl/Cmd+Shift+→, `#t=live`, `clock.goLive()` | following |
| Every source closed or recorded | end stops growing; the readout says so; the clock never invents progress |

- **States:** `clock.following` (pinned), `clock.playing` (following or replaying), `clock.live` (a live dataset that is
  not recorded is bound), `clock.lag`.
- **The span holds still while paused.** `clock.start` / `clock.end` are the span the playback bar and the cards draw:
  they follow the data while the clock plays (following or replaying) and hold while it is paused, so the time cursor
  and the track do not slide under the reader while rows keep arriving (Rerun's time panel does not re-fit while
  paused). The data's own span is `clock.liveStart` / `clock.liveEnd`; `lag = liveEnd − t`. Going live or playing
  takes the span up again.
- **Events:** `time` (`source: 'live'` while following), `state` (play, follow, rate, loop, range, window), and a new
  **`live`** event (`{following, lag, start, end, status}`) whenever the span grows or the connection changes. WHY a new
  event: `state` writes the URL, and a span that grows every frame must not.
- **Keys** (the dashboard's, added to PEP 0005 §4's): End and Ctrl/Cmd+Shift+→ go live; Home and Ctrl/Cmd+Shift+← go to
  the oldest data.
- **URL:** `#t=live` while following (so a shared link lands live), `#t=<seconds>` while paused.
- **Playback card:** while the clock is live the bar shows a **● LIVE** pill (filled while following; hollow with the
  lag while paused, "−12.4 s"; grey with the connection state while a source is down) and one click goes live. The
  track spans start to end, so scrubbing it is rewinding. Its readout and ticks write wall-clock times.

## 5. What a view shows at t

### 5.1 `at:`

Every view on a live dataset says what it shows at t with one key, **`at: latest | all | <duration>`**:

| `at:` | Append dataset | Keyed dataset |
|---|---|---|
| `latest` | the newest row of each stream at or before t | the record of each key at t |
| `<duration>` (`30s`, `5m`) | the rows in (t − duration, t] | the versions in that window (a change log) |
| `all` | every retained row at or before t | as `latest` |

Defaults: a keyed dataset `latest`; `plot` and `levels` `30s` (`all` on a recording: Foxglove's "last 30 s live,
the full range recorded"); every other view `all`. A row-reading view (table, list, cards, KPI, gauge, chart, …) gets
the newest rows at t that pass its filters, at most its `limit`, else 2,000, **in time order** (oldest first, as a
file's rows are, so a KPI's "newest row" is the last one as always); its own `sort:` orders them, and a log that wants
the newest on top says `sort: [{property: t, direction: DESC}]`. High-rate history belongs in `plot`, which reads the
typed arrays and never makes row objects.

| Card | Shows at t | Notes |
|---|---|---|
| `table`, `list`, `cards` | rows at t, newest first (a `sort:` changes it) | the tail (§5.3) |
| `kpi`, `gauge`, `bullet`, `barlist`, `status` | their own summary of the rows at t: the KPI's number is the newest row's at t | unchanged code: latest-at comes from the snapshot |
| `plot` (§6.2) | the window ending at t, min and max per pixel column | follows live at 60 frames a second |
| `levels` (§6.3) | the worst level per time bin in the window ending at t | |
| `timeseries`, `trajectory`, `scene3d`, `video` | the snapshot (a recording's whole range) and the playhead at t | unchanged (PEP 0005) |

### 5.2 Incremental models

A live view's rows are updated, not rebuilt, when its view is flat (no `groupBy`, `tree`, `rollup`, pivot) and sorted
by time (or not sorted): arrivals are filtered and searched once each and put at the newest end, rows past the cap or
outside the window leave at the other, and the table gets a TanStack table built over rows already in order (building
one costs < 0.2 ms; its row model is never asked for on a flat table). Measured in Node on 8,000 rows, a full
`rowModel()` sorted by time costs 22 ms, so a tail at 60 frames a second cannot afford one per frame. Any other view
shape gets a full `rowModel()` of its snapshot, at most every 250 ms. `tests/unit/live-model.test.mjs` holds the two
equal: for random appends, removals and windows, the incremental rows are exactly `rowModel()`'s over the same
snapshot.

### 5.3 The tail

A table or list on an append dataset follows the newest rows while its newest end is in view (the top when it sorts
by time descending, else the bottom). Scrolling away from it (more than one row) or opening a row pauses that view's
rows (the clock keeps following; only this panel holds still) and shows **"N new · Resume"** at the newest end.
Resume, or scrolling back, catches up. RobotDx's Activity log (`activity/log.js`) works this way.

## 6. Cards added

### 6.1 Where they live

`packages/views/live/` (one lazy bundle, `dist/views/live.js`, with uPlot inside it): a page that shows only live
plots never loads Vega's 880 KB bundle.

### 6.2 `type: plot`

Foxglove's Plot panel and PlotJuggler's plot: dense signals over time.

```yaml
- type: plot
  from: samples
  at: 30s                       # the window ending at t (default 30s live, all recorded)
  plot:
    x: t                        # the time property (default the dataset's time)
    y: [position, velocity]     # one or more number properties
    series: joint               # optional split (default the dataset's stream property)
    only: [shoulder]            # optional: draw these series only
    unit: rad
    dash: [target]              # series drawn dashed
    rules: [{y: 1.2, label: limit, tone: bad}]
    legend: top                 # top | none
    height: 200
```

- **Drawing:** uPlot 1.6.32. Past two samples per pixel column a series is reduced to its minimum and maximum in each
  column, in time order (so a one-sample spike still shows); a column with no samples breaks the line. On a live
  dataset the columns are kept between frames on an absolute time grid (`ColumnCache`): a frame reads only the samples
  that arrived since the last one, and a dense signal does not shimmer as the window slides. One `setData` per frame
  while the window moves, drawn inside uPlot's `batch()`; nothing while it does not.
- **On the clock:** the right edge is t (following: end), `[data-playhead]` marks t, a click seeks (leaves following),
  a drag sets `clock.window` (stays following), a double-click clears it, hover sets `clock.hover`.
- **Static data too:** on a plain dataset it draws `rows` (a recording); the uPlot path is the same.
- **Convergence:** lane/dc-plot is building `timeseries.interactive: true` on uPlot (pan, zoom, legend isolate). The
  two should become one uPlot card once both land; `packages/core/src/live/window.js` (the min/max columns) is the
  shared part.

### 6.3 `type: levels`

Grafana's Status history and RobotDx's health bar: one strip per stream, one bar per time bin.

```yaml
- type: levels
  from: checks_history
  at: 60s
  levels:
    state: level                # the level property
    by: name                    # one strip per value (default the dataset's stream property)
    order: [ok, warn, unknown, stale, error]   # worst last
    tones: { ok: good, warn: warn, unknown: muted, stale: muted, error: bad }
    bar: 3                      # px, with a 2 px gap; the bin count follows the width
```

A bin shows the worst level held in it: the level in force when the bin starts and every change inside it. A bin is
(start, end], so the newest reading at t lands in the last bin. A bin with no data is an empty outline, never a level.

### 6.4 `<data-live-status>`

One line: "● Live · 3 sources · last data 0.1 s ago", "Reconnecting · try 3 · last data 12 s ago", "Stale · no data
for 8 s", "Paused by the host: tview has the port", "Recorded". The dashboard puts one in its bar when it has a live
dataset; a host may place its own (`<data-live-status for="dashboard-id">`). It ticks once a second while visible
(the age is time-derived: it changes with no new row).

## 7. Feeding a live dataset

### 7.1 JavaScript (the whole API)

```js
import { LiveDataset, connectSSE, connectPoll, setLiveBudget } from './data-ui.js';
const ds = new LiveDataset({ id, title, properties, time: 't', stream: 'joint' /* or key: 'path' */,
  retention: { bytes: 64e6, age: 900 }, stale: 5 });
ds.append(rows);                  // append: row objects, in time order per stream
ds.appendColumns({ t: [...], position: [...] }, { stream: 'shoulder' });   // columnar: no row objects
ds.upsert(rows); ds.remove(keys); // keyed
ds.setStatus('live' | 'connecting' | 'reconnecting' | 'paused' | 'closed', detail);
ds.finish();                      // a finished recording: no more rows, end is fixed
dashboard.datasets.samples;       // the LiveDataset the .base declared; or: viewsElement.data = ds
const src = connectSSE(ds, url, { events: ['rows'], map: (data, type) => rows });     // src.close()
const src = connectPoll(ds, url, { every: 250, since: 'since', cursor: (body) => body.cursor, rows: (body) => [...] });
```

`change` fires once per frame (`{start, end, appended, upserted, removed, dropped}`); `status` on every connection
change. `clock.goLive()`, `clock.following`, `clock.lag` on the dashboard's `clock`.

### 7.2 The `.base`

```yaml
retention: { bytes: 256MB }       # this page's buffer (default 256MB)
datasets:
  samples:
    data: samples.json            # the properties, and any rows already recorded (a backlog)
    live: { time: t, stream: joint }                            # the page pushes rows (source: host)
  events:
    data: events.json
    live: { sse: /api/live/events, events: [rows], time: t }    # EventSource
  checks:
    data: checks.json
    live: { poll: /api/v1/checks, every: 1s, since: since, cursor: cursor, rows: checks, key: path, time: received }
  run:
    data: run-0420.json
    live: { time: t, recorded: true }   # a recording: the same views, rewound and replayed
```

`live:` keys: `time` (required), `stream` or `key`, `sse` + `events`, or `poll` + `every`, `since`, `cursor`, `rows`
(a dotted path; an array on the way is flattened), `retention {bytes, age}`, `stale` (default 5 s), `recorded`.

### 7.3 The server-sent-events wire

One event per batch. `data` is JSON: `{"rows": [...]}` (append, or upsert on a keyed dataset), `{"remove": [keys]}`,
`{"status": "paused", "detail": "tview has the port"}`, or a bare array of rows. `id:` is the host's cursor: the
browser sends it back as `Last-Event-ID` when it reconnects (WHATWG HTML §9.2), so a host that keeps a ring resumes
without a gap. A host that cannot resume sends `event: reset`, and the dataset clears and re-reads `data:`.

### 7.4 Connection state

`connecting` → `live` → (`stale`: no data for `stale` seconds) → `reconnecting` (try n, with the last data's age) →
`live`; or `paused` (the host says why) or `closed`. A polling source backs off (every × 2ⁿ, at most 10 s) and pauses
while the tab is hidden; its `since` cursor catches the gap up when it shows again. An SSE source is the browser's
own retry.

## 8. Performance

- **One frame loop** (`packages/core/src/live/frame.js`). Appends are synchronous into the store; the first one after a
  draw asks for one `requestAnimationFrame`. In it: each dataset publishes what changed, each clock moves (following),
  then each view that shows something that changed draws once. Background tabs get no frames, so they draw nothing
  and catch up in one frame when shown.
- **Paused, a view draws only when what it shows at t can change** (`pausedNews` in `live/feed.js`; added 2026-10-27
  after RobotDx found every upsert to a keyed dataset redrawing its paused views at the same t, 230-440 ms apart).
  Per frame of news: a row, version or removal written at or before t inside the view's window draws it (a window is
  `(t − at, t]`; a plot's span also takes in its zoom); retention taking a row the view read at t draws it (a plot or
  levels card: any sample in its span), checked against the drop log by stream (a keyed dataset's: the key) and arrival
  number; retention taking rows at t it did not read changes only the status line's count; a reset or the recording
  ending draws. Everything after t waits for t. The view's own inputs (filters, search, size, theme) redraw it as
  before. A late row then reaches the readers that read only what is new: the store logs a row that went in before
  newer rows of its stream (`reordersSince`), and the tail reads its rows at t again, the plot's column cache folds
  that stream again from there; a chunk retention takes inside a plot's window rebuilds its columns.
  `tests/unit/live-paused.test.mjs`; `tests/browser/live_checks.py` counts draws per panel (RobotDx's three shapes).
- **KPIs** (RobotDx PEP 0001 §8 and the prior-art note's budgets), measured by `bench/live.py` in headless Chromium:
  ingest-to-pixel latency p50/p95, frame time while streaming (N points/s × M panels), JS heap at the retention cap,
  scrub latency, time back to live, first paint.

## 9. Numbers

`bench/live.py` (bench/README.md), 2026-10-27, on this box (Ryzen 9 7900X, the bench pinned to CPUs 4-11, load 16-21 on
24 CPUs from other agents). "GPU" draws through ANGLE on Vulkan (the RTX 4080), as a desktop browser does; "CPU" is
headless Chromium's default software raster. The load is 12 plot panels of 5 streams each at 1 kHz, **60,000 samples a
second**, Rerun's published test shape. Three runs: the long one (10 minutes into the 256 MB buffer, at 4a49b6f plus the
bench's own probe fix; trusted), a short one on the GPU (ebd4534; labelled noisy, calibration 1.35x this host's best),
and a short one on the CPU (ebd4534; trusted).

| KPI | Budget | GPU, long (trusted) | GPU, short | CPU, short |
|---|---|---|---|---|
| frame rate while following | 60 fps, p95 ≤ 16.7 ms | **58.8 fps**, p95 16.8 ms | 59.8 fps, 16.7 ms | 50 fps, 33.4 ms |
| the live frame loop's own JS, p50 / p95 | ≤ 8 ms | p95 11.6 ms | 6.2 / 8.5 ms | 6.6 / 9.8 ms |
| ingest to pixel, p50 / p95 | p95 ≤ 50 ms (Rerun < 30) | **22.4 / 28.0 ms** | 23.6 / 26.9 ms | 24.3 / 40.9 ms |
| draws per view per frame (most) | 1 | 1 | 1 | 1 |
| scrub to painted, p95 | ≤ 50 ms (RobotDx K5) | **23.2 ms** | 31.8 ms | 44.8 ms |
| back to live after a 2 s pause, p95 | 1 frame of work | 41.6 ms | 44 ms | 112 ms |
| first paint: navigation → ready, + first rows → painted | ≤ 1.5 s (K7) | **155 ms** | 159 ms | 247 ms |
| memory at the buffer's cap | ≤ budget | 256 MB buffer: **JS heap 41.5 MB** + 254 MB of typed arrays, **flat for 10 minutes** (41.5-42.7 MB, 8.37 M samples kept) | 64 MB buffer: 18.5 + 63.9 MB | 17.2 + 63.6 MB |

- **Back to live is one frame of work:** traced frame by frame, all 12 panels redraw in the first animation frame after
  `goLive()`; the rest of the measured time is the frame being presented (and, on the CPU, frames 33-50 ms apart).
- **Lighter loads** (GPU): 1 panel at 5,000 samples a second, 60 fps, live loop p95 3.0 ms; 4 panels at 20,000, 60 fps,
  3.2 ms; 12 panels at 6,000 (100 Hz streams), 60 fps, 7.0 ms.
- **Misses:** the live loop's p95 is 8.5-11.6 ms against 8 ms at the full load (its p50 is 6 ms); the CPU raster
  cannot hold 60 fps with twelve canvases.
- **No leak:** the first long run's heap grew 6 MB a minute; it was the bench's own probe arrays (a dozen records a
  frame), which now record only while a measurement runs. Without them the heap holds flat at the cap for 10 minutes. What would close it, not done: the reduction in a worker (transferable arrays, prior-art note §Q4),
  and redrawing a plot's axes only when its labels change.
- **What got it here** (measured in the commits): the column cache (only new samples are read; was a full reduction of
  the window every frame, 4.5 / 6.2 ms per 600,000 samples), uPlot drawing inside `batch()`, no layout read per plot per
  frame (a forced layout per plot), the status line at most four times a second.

**Vega or uPlot (the decided bench).** The same min / max columns of a 60 kHz window (5 series × 12 kHz, 10 s, 600,000
samples, 8,600 points a frame at 860 px) pushed into each engine for 240 frames: **uPlot** (`setData` inside `batch()`,
drawn) p50 / p95 **0.6 / 1.1 ms** (the trusted long run; 0.7 / 1.3 on the CPU, 0.9 / 4.9 on the noisy GPU run);
**Vega** (the timeseries card's View: `data()` + `runAsync()`, its change-set path, no re-embed) **24.3 / 44.7 ms**
(28.2 / 52.9; 31.1 / 62.9). One Vega panel spends two to three frames per update, so it cannot follow at 60 fps; uPlot
is about 40 times faster on the same points. Decision 1
stands: uPlot for the live time series, Vega-Lite for everything else.

**Bundles.** The core (`dist/data-ui.js`) grows from 87.8 to 102.4 KB gzipped: +14.6 KB on every page, live or not (a
lazy `dist/live.js` would take it back; not done). `dist/views/live.js` (uPlot and both cards) is 30.2 KB gzipped,
against the chart bundle's 310 KB that a live page no longer loads. The dashboard grows 0.9 KB, the playback card 1.1 KB.

## 10. What this does not do (yet)

- **RobotDx's other MISSING items** (its PEP 0001 §5): a level-strip *cell* in a table (b1; `levels` is a card), the
  level display with shapes and a worst-by-rank roll-up (b2, b3), a presence dot (b4), a time-range brush that
  *filters* other panels (b5; a plot's drag zooms the clock's window), a subtree scope (b6), pinned rows, "Show N
  hidden", tab badges and step-into chips (b7) and a value-vs-expected cell (b9). The interactive plot (b10) is
  lane/dc-plot's. (The ticking "heard 2 s ago" cell, a8, is `display: age`.)
- **A lazy live bundle:** the tier adds 14.6 KB gzipped to every page's core (§9).
- **The reduction in a worker** (transferable arrays): the live loop's p95 is 8.5-9.8 ms at 60,000 samples a second
  over 12 panels, against 8 ms (§9).
- **Rails, links and roll-ups on a live dataset** read its newest 2,000 rows (`LiveDataset.rows`), not the rows at t.

- **Rewind past the browser's buffer** (a range fetch from the host's ring, Rerun 0.30's on-demand streaming): a seek
  before `start` clamps to it. Step B of RobotDx PEP 0001 §9 decision 3.
- **The tree's structure at a past t** needs the host to record its row states (RobotDx step B); the keyed dataset
  already answers "as of t" once versions arrive with times.
- **Frames:** an `image` card stays latest-only; frame history is a host change.
- **Binary transport** (Arrow, WebSocket) and a SharedArrayBuffer ring: not until a measured parse cost asks for them.
- **The worker:** a live snapshot is capped (2,000 rows) and updated incrementally, so the row-model worker (5,000+
  rows) is not used by live views; a grouped live table over a larger `limit` re-models on the main thread at most
  every 250 ms.

## 11. Rejected

- **Embedding Rerun's web viewer:** 51.8 MiB of wasm, no data-ui views, no diagnostics tree; "Open in Rerun" stays the
  backdoor (PEP 0005 §6).
- **A live variant of every card:** every card built twice. One snapshot at t serves them all.
- **`refresh:` for live data:** re-fetching a whole file every interval is today's 63 KB/s problem (RobotDx §8).
- **WebSocket:** the host is stdlib-only and SSE already resumes; writes are rare POSTs the host owns.
