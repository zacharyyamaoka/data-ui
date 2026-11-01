# PEP 0008: one video drives a dashboard's clock

- **Status:** accepted 2026-10-27 on `lane/dashboard-cards` (with the cards, CONTRACT §25). A contract change to PEP
  0005 §4: `clock.primary` now chooses the driver, and a dashboard has at most one.
- **Amended 2026-10-28** by judge round 3 #4 (a closed tab is never the driver) and by judge round 2 (reports/media/audits/2026-10-28-dashboards-judge-r2.md, items 1–2): a loop
  wrap is a seek generation, and the driver is one card instance.
- **Why now:** Codex judge round 1 on the cards lane (reports/media/audits/2026-10-27-dashboards-judge-r1.md, items 1–3).
  The clock let any `video.primary: true` card call `drive(t)`. Two primaries could both drive, `clock.primary` was
  read by nothing, and a stalled driver lost the clock to wall time after 250 ms, so t ran on and then jumped back.

## The decision

**A dashboard's t has exactly one writer while it plays: the clock, paced by at most one designated video.**

1. **Choosing the driver** (`primaryDriver(spec, views)` in packages/core/src/clock.js), first match wins:
   - the video card `clock.primary` names;
   - else the first video card, in layout order, with `video.primary: true`;
   - else none: the clock advances on wall time.
   The choice is then resolved to ONE card instance (judge round 2 #2): `driverInstance(name, panels)` is the driver
   key `<panel key>/<view name>` (`driverKey`) of the first panel, in layout order, that shows that view. A video
   card keys its clip the same way (outside a dashboard, by its own instance number), so the same view on two panels
   is one driver and one follower, and the follower's `ended` cannot release the driver.
   Only a card on screen is eligible (judge round 3 #4): `driverInstance(name, panels, shown)` takes the first panel
   whose OPEN tab shows the view, and the dashboard re-resolves on every tab change. When no open tab shows it,
   nothing drives, the clock runs on wall time, and the clock bar shows a quiet note (`clock.note`).
2. **Enforcing it.** `clock.setDriver(key)` designates the driver; `drive(t, id)` from any other card is ignored, so
   two `primary: true` cards cannot fight.
3. **Ownership is held, not timed out.** While the driver is buffering (waiting, stalled, seeking, readyState < 3)
   the clock holds t. It is released only explicitly: `release(id)` on ended, error, removal or destroy, or a documented
   fallback after a 3 s stall, which never moves t backward.
4. **Seeks win over late frames.** Every seek bumps `clock.gen`; a frame callback armed before the seek is ignored,
   and the driver re-arms on `seeked`. A loop wrap is a seek (judge round 2 #1): the wall-time, fallback and
   driver-at-end wraps all fire source `loop` and bump `gen`. While the clock runs on wall time after a stall, the
   clip's jump to t also cancels its pending callback, so a pre-jump frame cannot end the fallback.
5. **A wrong name is an error, not a fall-through.** `readDashboard` reports a `clock.primary` that names no video
   card on the layout, so `data-ui check` gives the line and the page lists it under its problems.

## Options considered

| Option | For | Against |
|---|---|---|
| **One designated driver (chosen)** | matches Rerun and Foxglove: one time source; LeRobot's visualizer: one primary video, the rest follow; deterministic and testable | an author names it, or takes the first flagged card |
| Any primary may drive, last write wins | no new rule | two clips with different frame grids make t jitter between them (the judge reproduced it) |
| No video ever drives; wall clock only, videos follow | simplest | a video that buffers drifts, then every follower jumps; frame-accurate playback is lost |
| HTMLMediaElement `mediaGroup` | stock | removed from browsers |

## Consequences

- `clock.primary` keeps its meaning from PEP 0005 §4 and now does what it said.
- A `.base` that relied on two primaries driving gets the first one in layout order; the others follow.
- `primaryDriver`, `driverInstance`, `driverKey`, `readClockParams`, `writeClockParams` and `clockNavigation` are named
  exports of `@data-ui/core`.
- `clock.driverId` is a driver key (`<panel key>/<view name>`), no longer the bare view name (round 2). Nothing in the
  `.base` changes: `clock.primary` and `video.primary` still name views.
- Tests: tests/unit/clock.test.mjs (one driver, held ownership, seek generations), tests/unit/dashboard.test.mjs and
  tests/unit/check.test.mjs (`clock.primary` validation), gallery/examples/dashboard-cards/checks_dashboard.py (the
  playing check with participant counts and injected failures).
