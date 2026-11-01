# Vibe Tracks · track overview dashboard

Vibe Tracks' home as one dashboard: every real track with its headline KPI and history, the check runs rolled up
through child tracks, and the newest runs. Three linked datasets in one `.base` file; one rail for all of them; a click
on a card, a bar or a track narrows every panel.

- **App:** Vibe Tracks
- **Replaces:** the home's track rows and KPI tiles (`vibetracks~/views.js`, `cards.js`, `kpi-panel.js`)
  and the hand-written roll-up in `vt state` (`rollup`), for reading; Vibe Tracks keeps computing its own state.
- **Shows:** `layout:` placing a text block, a KPI strip, a tree table, a bar chart and a tabbed runs panel; `datasets:`
  and `links:` (tracks ↔ KPI points ↔ check runs) so one rail (area, health, state; run kind and date) filters all of
  them; `select:` cross-filtering from the KPI cards, the tracks and the bars; a `rollup:` of each track's newest run
  per suite through its children (Passing, Checks, Pass rate, drawn as derived); the drill-down peek on a run.
- **Data:** `tracks.json` (18 tracks), `kpis.json` (473 KPI points, newest 30 per L0/L1 KPI) and `runs.json` (86 check
  runs: tests, checks, goldens, gates), written by `source/build.py` from Zach's Vibe Tracks owner bundle
  (`~/.vibetracks/bundle`, vt-state/1) and its producer folders, read 2026-10-26. Real. Grasping keeps its row, but its
  figures are left out (data-ui SPEC §13): its headline is "—" with the reason.
- **Skin:** `skin.css`, Vibe Tracks' tokens (Claude Desktop's) mapped onto `--data-*`.

## Data (round 2)

Written by `source/build_series.py` (`python3 -I gallery/examples/vibetracks-dashboard/source/build_series.py`), from
the same owner bundle and producer folders as `build.py`, read 2026-10-26. Real. Grasping contributes nothing.

- `series.json` (471 rows): every whole-bench point (no slice) of eight KPIs with 20 or more points: Trajectory
  Generation's waypoint length / Pro (L0), p2p and waypoint planning time / Pro (L1), the common-waypoint and both
  Python planning-time ratios (L2), and Vibe Tracks' checks passing (L0) and tests with a purpose (L1).
  `better` from the catalog's direction; `t` converted to UTC (the producers mix offsets); values to 5 significant
  digits.
- `runs_daily.json` (390 rows): per public track per local day (Vancouver), 2026-09-27 to 2026-10-26, every day
  present: `runs`, `judged_runs` (runs that carry the producer's own pass/fail verdict), `passed_runs`, `pass_rate`
  (null with the reason on a day without verdicts).
- **Missing:** no other track has 20 whole-bench points yet (Pyblocks' runnable goldens 13, the rack twin's stations
  12, data-ui's first paint 4, and data-ui's producer is not referenced by any track). Every ruckig run's verdict
  (`labels.ok`) is false and every Pyblocks run has red goldens, so their pass rate is 0 every day: that is the
  producers' verdict, not a gap. The fivebar runs' `media/hero.mp4` is one byte-identical clip copied into all six
  runs (a MuJoCo render of the five-bar, not of any run), so it is not used as a "latest run" tile.

## Layout (round 2: KPI dashboard, no clock)

Klipfolio-style rows, every card on the files above (PEP 0005 cards; one palette per run kind and per KPI):

1. **Headlines**: one KPI tile per track with a headline (12), the producer's newest point to 3 significant figures,
   ▲▼ against its previous point, a sparkline.
2. **Judged runs passing** (gauge, Σ passed runs / Σ judged runs over the 30 days) beside **Last 30 days** (a tracker
   row per public track, a block per day coloured pass / mixed / fail / none from `days.json`).
3. **Runs per week** (a line per run kind, from `runs.json`) beside **Producer runs per track** (bar list, Σ runs over
   the 30 days, from `days.json`: every producer run, benches included, so it differs from the check runs).
4. **KPI history** as lines on a date axis from `series.json`: Trajectory Generation's three × Pro ratios (L0/L1, with
   the `= Pro` line), Vibe Tracks' checks passing, its tests with a purpose. The L2 ratios are left out (their labels
   are raw KPI ids).
5. The tracks tree with its roll-up, the check runs by track, and the runs table / pivot, as before.

`days.json` is `runs_daily.json` plus one derived column, `verdict`, written by `source/build_days.py`
(`python3 -I gallery/examples/vibetracks-dashboard/source/build_days.py`). **Live data:** the `runs` dataset has
`refresh: 5s`; the checks serve the real file, then the same file plus one synthetic test-only row, and measure the
panels update in place (selection chip, the runs table's scroll, the rail and the page scroll unchanged; one
`data-dashboard-refresh`). `vt_measure.py` holds the measurements the three Vibe Tracks cases' checks share.
