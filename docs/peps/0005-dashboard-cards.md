# PEP 0005: dashboard cards, one clock, and dashboard styling

- **Status:** proposed 2026-10-26 on `lane/dashboard-cards` (not merged). The CONTRACT amendment is §25 (drafted as §20; §17 is dashboards, PEP 0004; §18 embedded chrome; §19 analyses, PEP 0007; §20-§24 were taken on main first).
- **Asked by:** Zach, 2026-10-26: "I want to see much more media rich with time series, videos, and for it to look
  much cleaner and professional." "We basically want a large list with all the types of 'cards' we can add to the
  dashboard." "The PID tuning results: I want to be able to play back videos, and see trajectories, and have all of
  those things synced. Also important is the video overlay card … Also a 3D card." "There are lots of stock shadcn
  components for this… we 100% don't need to reinvent the wheel."
- **Builds on:** PEP 0004 (a dashboard is a `.base` file with `layout:`), the prior-art sweep
  (reports/data-ui-dashboard-prior-art-2026-10-26.html; vault: *C - Dashboard card types and styling (prior art)*),
  and the tracking-run contract (vault: *Tracking-Run Data — data-ui vs Rerun (2026-10-26)*).

## 1. The answer

**A card is a view.** Every card in the catalog is an ordinary `type:` in `views:`, placed by `layout:` exactly as
PEP 0004 places a table or a chart. Nothing new is learned to place a card; only its own keys are new. A card reads
its own dataset (`from:`) or a shared one, so a video, a time series and a trajectory over the same samples are
linked by construction.

**Time is one more piece of dashboard state.** One clock per dashboard (`clock:` in the `.base`, `#t=` in the URL)
is the only thing that sets *t*. Every time-aware card follows it: a video seeks, a time series draws its playhead,
a trajectory and a 3D scene move their marker. The playback card (`type: playback`) is the clock's control, a
Rerun-style time panel placed in the layout like any card.

**The look is declared once.** `style:` sets about ten dashboard-wide knobs (surface, radius, padding, gap, titles,
theme, density, chart chrome, number format, palette); a panel may override any of them. The default is the
references' look: tiles on a quieter page, each title inside its tile, no boxes inside the tiles.

**Rerun is the backdoor.** `rerun:` names a `.rrd` written at build time from the same datasets
(`tools/rerun_export.py`, rerun-sdk as a `uv run` extra, never a runtime dependency); the dashboard's "Open in
Rerun" menu opens it in Rerun's hosted viewer, copies the native command, or downloads the file.

## 2. The catalog

| Card (`type:`) | Draws | Stock part | Time-aware |
|---|---|---|---|
| `kpi` | stat with delta ▲▼ coloured by `better`, + sparkline (exists; gains `format:`) | ours (SVG) | |
| `gauge` | progress bar or semicircle gauge against a target / gate | ours (SVG/CSS, Tremor's ProgressBar look) | |
| `bullet` | bullet chart: value bar, target tick, qualitative bands | ours (SVG) | |
| `barlist` | ranked bar list / leaderboard (Tremor BarList) | ours (CSS) | |
| `tracker` | tracker grid: one cell per row, coloured by a state property (Tremor Tracker; not `status`, which §18 made the status-line key) | ours (CSS) | |
| `timeseries` | multi-series line/area over t, bands, rules, annotations, log axis, brush-zoom, shared crosshair, playhead | Vega-Lite (the chart bundle) | yes |
| `chart` | bar, histogram, scatter (with y = x), heatmap: any Vega-Lite; `chrome: minimal` frameless | Vega-Lite | |
| `trajectory` | 2D path vs target (equal aspect, colour by error, trail to t, tolerance tube) | Vega-Lite | yes |
| `scene3d` | 3D paths, a moving marker, an optional stick robot from per-link positions | three.js, one shared WebGL context | yes |
| `video` | one video (native `<video>`), seeks to the clock | browser | yes |
| `video-compare` | two videos: onion skin (opacity), wipe slider, difference blend, side by side | browser + CSS | yes |
| `image` | an image or a strip of images from rows | browser | |
| `playback` | the clock's control: play/pause, scrub, speed, loop, step frame, range selection | ours | is the clock |
| `table`, `map`, `cards` (gallery) | as today, wearing the dashboard's surface | unchanged | |
| text panels (`text:`) | markdown, as PEP 0004 | md.js | |

## 2b. Each card's keys (frozen; the schema is schemas/view.schema.json)

Every card also takes the view keys it already has (`name`, `from`, `filters`, `select`, `sort`, `groupBy`,
`limit`) and `style:` (§5). Property names below are columns of the card's dataset.

```yaml
- type: timeseries
  timeseries:
    x: t                    # time column (seconds, or a date column: then no playhead)
    y: [q_target_deg, q_deg] # one or more columns
    series: situation       # optional split; with several y each series is "<value> · <column>"
    mark: line              # line | area | step
    scale: linear           # linear | log | symlog
    unit: mrad              # axis unit text (default: the column's unit)
    dash: [target]          # series names (or columns) drawn dashed; a series named "target" is dashed by default
    rules: [{y: 5, label: "gate ≤ 5 mrad"}]          # horizontal thresholds
    bands: [{y: [-5, 5], label: tolerance}, {x: [2, 3], label: hold}]   # shaded y or x bands
    annotations: [{x: 2.1, label: step}]             # vertical markers with a label
    legend: top             # top | none
    height: 220             # px (default: the panel's)
    interactive: false      # true: the Foxglove/Rerun plot (pan, zoom x/y/box, reset, cursor click, legend hide/isolate, ? help, maximise)
- type: trajectory
  trajectory:
    x: x_mm                 # path coordinates (equal aspect)
    y: z_mm
    series: situation
    target: target          # the series value drawn as the reference (dashed, muted)
    color: err_mm           # optional: colour the path by this column (sequential scale + legend)
    tolerance: 5            # optional: a tube of this half-width around the target path (x/y units)
    t: t                    # time column (default: the clock's) for the moving marker and the trail
    trail: true             # draw each path up to t solid, the rest faint
- type: scene3d
  scene3d:
    x: px                   # metres; z up (robotics convention)
    y: py
    z: pz
    series: situation
    target: target
    t: t
    skeleton: [[s0x, s0y, s0z], [s1x, s1y, s1z]]   # optional stick robot: joint origins base → tool, per row
    up: z                   # z | y
    robot:                  # optional: a meshed robot (a GLB with one node per link), posed per row
      model: media/ur5e_links.glb
      links: [base, shoulder_link, upper_arm_link, forearm_link, wrist_1_link, wrist_2_link, wrist_3_link]
      ghost: target         # drawn translucent; columns <link>_x/_y/_z and <link>_qw/_qx/_qy/_qz (wxyz) per row
                            # exact at the rows; between rows lerp/slerp (UR5e at 25 Hz: ≤ 1.34 mm (max 1.335 mm over 104,804 link samples; 95th percentile 0.42 mm) from true FK)
- type: video
  video:
    src: src                # the media column (default src); the card shows the first row its filters leave
    label: situation        # caption column
    primary: false          # true: this video's frames drive the clock while it plays
- type: video-compare
  overlay:
    by: situation           # the property that tells the two clips apart
    a: tuned                # its value for clip A (default: the first row)
    b: factory              # for clip B (default: the second row)
    mode: wipe              # wipe | onion | difference | side   (the card's switch changes it; setView keeps it)
    split: 0.5              # wipe position / onion opacity, 0..1
- type: image
  image: poster            # Bases' own key: the image property (as on cards); not an object
  caption: [note]          # data-ui's cards key: the properties under the picture
- type: gauge
  gauge:
    value: { property: pass_rate, summary: Average }   # as kpi.value
    min: 0
    max: 1                  # a number or a property
    target: 0.95
    shape: bar              # bar | arc
    better: higher
    bands: [{to: 0.8, tone: bad}, {to: 0.95, tone: warn}, {tone: good}]
- type: bullet
  bullet: { value: {property: rms_mrad}, target: floor_mrad, max: 5, label: rung, better: lower,
            bands: [1, 2, 4] }   # one bullet per row (or per group)
- type: barlist
  barlist: { label: track_title, value: {property: runs, summary: Sum}, limit: 10, better: higher }
- type: tracker
  tracker:
    state: verdict          # the column whose value colours the cell
    label: day              # hover / caption column
    tones: { pass: good, fail: bad, partial: warn, none: muted }   # value → tone (good | warn | bad | muted | neutral)
    # with groupBy: one tracker row per group (Tremor's Tracker), cells in sort order
- type: playback
  playback:
    speeds: [0.25, 0.5, 1, 2, 4]
    range: true             # the loop/selection handles on the track
    readout: true           # "3.20 / 7.93 s"
    variant: bar            # bar | rerun | rerun-streams | youtube | tracks | foxglove | range (§4b)
    switcher: false         # true: a drop-down on the card to try the variants live
- type: chart               # bar, histogram, scatter, heatmap: plain Vega-Lite; style.chrome minimal applies
  chart: { … }
```

## 3. Data shapes (the contract with producers)

Built against the tracking-run contract: a **situation** is one way of playing the target (target, factory, tuned,
real, twin…); a **channel** is a named series in SI; missing is `null` with a reason, never 0.

**Samples** (time series, trajectories): a tidy table, one row per sample per situation.

```json
{"t": 1.25, "situation": "tuned", "joint": "shoulder_pan", "q": 0.512, "q_target": 0.515, "err_mrad": -3.1,
 "px": 0.41, "py": -0.12, "pz": 0.33}
```

- `t` in seconds from the target's start (the clock's time). Other columns are channels; units in the schema.
- A card picks series by **columns** (`y: [q_target, q]`) and/or by **a splitting property** (`series: situation`).
- Producers may decimate for display; metrics are computed on each situation's own samples upstream.

**Media**: one row per clip.

```json
{"id": "tuned-video", "situation": "tuned", "src": "media/ur5e_tuned.mp4", "poster": "media/ur5e_tuned.jpg",
 "t0": 0.0, "fps": 30, "duration": 7.9, "basis": "sim-render", "note": "MuJoCo 3.17 render of the replay"}
```

- `t0`: the clock time at the clip's frame 0 (the manifest's `t_offset_s`). `basis` says what made it:
  `real-camera`, `sim-render`, `screen-capture`, `illustrative`. A card prints it; an illustrative clip says so.
- `src` resolves against the data file's URL (CONTRACT §1 amendment).

**Links** (`link`, `rerun`, `replay`) are ordinary text columns.

## 4. The clock

> One video drives t, chosen by `clock.primary`, else the first `video.primary: true` card; a wrong name is a
> checker error. The decision and its reasons: docs/peps/0008-one-clock-driver.md.

```yaml
clock:
  data: samples        # the dataset whose `time` column spans the clock (default: the first time-aware panel's)
  time: t              # its time property (seconds)
  rate: 1              # 0.25 · 0.5 · 1 · 2 · 4
  loop: true
  fps: 30              # the step size for ←/→ (default: the primary video's fps, else 30)
  primary: Tuned video # optional: the video panel whose frames drive t while playing
```

- **One writer.** `Clock` (packages/core/src/clock.js) holds `t, start, end, playing, rate, loop, range, window,
  hover`. Only its methods change them; every card listens to its events.
- **Playing.** Without a primary video, a requestAnimationFrame loop advances `t += dt × rate`. With one, that
  video's `requestVideoFrameCallback` sets *t* (`mediaTime + t0`), and every other video follows (LeRobot's
  visualizer): more than 0.1 s off, it jumps; 0.04–0.1 s off, its playbackRate is nudged ±5 %. HTMLMediaElement's
  mediaGroup is not used (removed from browsers).
- **Paused.** `seek(t)` sets every video's currentTime exactly, and every playhead and marker is placed in the same
  task: all agree within one frame.
- **Range.** `range: [a, b]` is the loop / selection (Rerun's loop selection, `[` and `]` set its ends). `window:
  [a, b]` is the zoomed x-domain every time series shows (a brush on any time series sets it, a double-click
  clears it).
- **Hover.** `hover: t | null` is the shared crosshair: moving over one time series draws a rule on all of them.
- **Keys** (when the dashboard has focus): Space play/pause, ←/→ one frame, Shift+←/→ one second, J/K/L
  (back, pause, forward), `[`/`]` range ends, Home/End.
- **URL.** `#t=3.20` (and `#tr=a,b` for a range). Reload and a shared link land on the same instant.
- **Outside a dashboard** a page gets one document clock, so a lone `<data-views>` with a video and a time series
  still syncs.
- **Addendum 2026-10-27 (judge round 1: reports/media/audits/2026-10-27-dashboards-judge-r1.md; additive):**
  - *One driver.* The dashboard resolves exactly one video per clock, `clock.setDriver(<driver key>)` (a card instance
    since round 2, below): the video card
    `clock.primary` names, else the first video card in layout order with `video.primary: true`, else none (wall
    time). `drive()` from any other id is ignored. Outside a dashboard the first `primary: true` card claims the
    page's clock (`driverId` undefined until then).
  - *Ownership.* From its first presented frame the driver owns t while the clock plays: buffering, waiting or
    seeking holds t (no wall-time advance). It hands t back by `clock.release(id)` (its clip ended, failed, left t's
    span, or its card was removed), or after `STALL` (3 s) without a frame: `clock.fallback` turns true, wall time
    runs t, the clip jumps to t, and its next frame ends the fallback. t never moves backward while it plays inside
    one seek generation: a frame behind t holds t until the video passes it.
  - *Seek generations.* Every seek (user, URL, step, range, loop, a restart) bumps `clock.gen`; a frame callback
    passes the generation it was armed in, `drive(t, id, gen)` ignores a stale one, and the clip re-arms on `seeked`.
  - *Paused is exact.* A follower is re-seeked whenever the target changes, also under 1 ms.
  - *Range.* `setRange([a, b])` is intersected with the span; an empty intersection is no range, and a range asked
    for before the span is known is re-intersected as the span lands (`setSpan`, `extent`).
  - *URL.* A fragment edited after load (`hashchange`, `popstate`) applies its t and tr. With several dashboards on a
    page each writes `#t.<key>=` / `#tr.<key>=` (key: the element's id, else a slug of its src) and reads a plain
    `#t=` / `#tr=` when its own is absent; a page with one dashboard keeps plain `#t=` / `#tr=`.
- **Addendum 2026-10-28 (judge round 2: reports/media/audits/2026-10-28-dashboards-judge-r2.md; additive):**
  - *A loop wrap is a seek.* Every wrap (wall time, a fallback, the driver at the end) fires `time` with source
    `loop` and bumps `clock.gen`, so a frame callback armed before it cannot pull t back; the clip seeks to the wrap
    point and re-arms on `seeked`.
  - *The driver is one card instance.* `setDriver` takes a driver key, `<panel key>/<view name>` (core's
    `driverKey`); the dashboard designates `driverInstance(primaryDriver(clock, views), panels)`, the first panel in
    layout order that shows the chosen view, so one view on two panels is one driver and one follower. Outside a
    dashboard a card's key is its own instance number.
  - *Navigation is a fresh load.* Back / Forward or an edited fragment leave the clock as a fresh load of that URL:
    an absent t is `clock.home()` (where a fresh clock sits), an absent or empty tr is no range, a malformed value
    leaves that part as it is (core's `clockNavigation`), and applying it writes nothing back to the URL.
  - *Scopes never depend on position* (round 3, the coordinator's call 2026-10-28; replaces round 2's `-2`, `-3`
    numbering, which re-pointed saved links when a dashboard was inserted above). With several dashboards, a
    dashboard's key is its id as written, else a slug of its src when no other dashboard on the page has that key.
    Repeated or slug-colliding sources must have explicit unique ids: without one, and for a repeated id, the clock
    stays out of the URL, the dashboard lists the problem on every parse (a reload included) and the console warns
    once; `data-ui check page.html` reports each such tag at its line.
- **Addendum 2026-10-28, round 3** (reports/media/audits/2026-10-28-dashboards-judge-r3.md):
  - *One placement rule.* Until something asks for an instant, t is `clock.home()`, re-placed on every extent,
    `setSpan` and range change; a seek or a link's t is kept and re-clamped as the span grows. A fresh load and a
    navigation both call `clock.restore(clockNavigation(...))`; the URL leaves t out while the clock is at home.
  - *The driver is on screen.* Only a panel whose open tab shows the chosen video is eligible
    (`driverInstance(name, panels, shown)`); the dashboard re-resolves on every tab change. When no open tab shows
    it, nothing drives, the clock runs on wall time, and `clock.note` says so on the playback card (else the
    dashboard's bar).

## 4b. Playback variants (proposals, Zach 2026-10-26)

Five proposals for the clock's control, one `playback.variant` each, all driving the same clock:
- **P1 `rerun` / `rerun-streams`:** Rerun's time panel copied: play/pause, step, loop mode, the timeline picker, a speed
  field and a time field; the streams variant adds the STREAMS tree (one row per dataset and series) with its event
  bars on a time ruler and the playhead. Rerun's step menu and keys: ←/→ 0.1 s, Shift ±1 s, Ctrl previous/next event,
  Ctrl+Shift start/end.
- **P2 `youtube`:** a scrub bar with a hover thumbnail (a real frame of the dashboard's video at that t), chapters or
  markers, the buffered range, speed in a settings menu, keys J/K/L, ←/→ and , / . (frame).
- **P3-P5 `tracks`, `foxglove`, `range`:** a video editor's multi-track timeline, Foxglove's playback bar, and a
  Grafana-style overview with a brushed range (prior art in the lane's README).

## 5. Styling

```yaml
style:
  theme: dark            # auto (default: the page's) | light | dark
  surface: filled        # filled (default: tiles on a quieter page) | transparent | outline
  radius: 12             # px, the card corner
  pad: 16                # px, inside a card
  gap: 12                # px, between cards
  title: inside          # inside (default) | top | none
  density: comfortable   # comfortable | compact
  chrome: minimal        # minimal (default: no domain, ticks or vertical grid; faint horizontal grid) | full
  numbers: { digits: 3, compact: true }
  palette: { target: "#9aa0a6", factory: "#e87ba4", tuned: "#2a78d6" }   # a fixed colour per series name
```

Every key may also sit on a layout panel's `style:` (`{view: X, style: {surface: filled, title: none}}`) or a view's own `style:`. The palette is the dashboard's
and reaches every card through `seriesColor(el, name)`; a name it does not list gets a stable slot (`hueOf`). Number
format: `numbers:` is the default for every card (none by default: rounding a stored value is declared, never
silent); a property's `digits/compact` and a card's `format:` win (§14's
declared rounding). Dark: page `#111`-ish, card `#1c1c1f`, border `#2a2a2e`, no shadows (the prior art's values,
from the tokens).

## 6. Live data, arranging, Rerun

- **`datasets.<name>.refresh: 10s`** re-fetches that file on the interval (and on `reload()`); panels get the new
  rows in place, keeping their view, scroll, selections, the clock and the rail.
- **Arrange.** An "Arrange" toggle turns the grid into gridstack.js (MIT, framework-free): drag and resize panels.
  The new order and sizes are kept for this reader (localStorage) and offered back as the `.base` text ("Copy
  layout"); an editable host gets `host.propose`-style `data-dashboard-layout` event with the new `layout:`.
- **`rerun: {rrd: rerun/pid-tuning.rrd, sdk: 0.40.0}`**: "Open in Rerun" opens
  `https://app.rerun.io/version/<sdk>/index.html?url=<absolute rrd URL>`, copies `uvx --from rerun-sdk==<sdk> rerun
  <rrd URL>`, or downloads the file. The `.rrd` is generated (never hand-edited) by `tools/rerun_export.py <base>`
  from the same datasets, with a blueprint mirroring the layout.

## 7. What this does not do

- No new layout grammar; no React; no second chart engine (time series and trajectories are Vega-Lite types in the
  chart bundle).
- No resampling for metrics; the cards draw what the producer wrote.
- No fake media: a missing camera stays a declared gap.
